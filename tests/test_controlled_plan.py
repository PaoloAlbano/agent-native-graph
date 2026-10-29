"""Plan preparation is local evidence collection, not a launch approval."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from agent_native_graph.research.controlled_plan import prepare_plan, schedule, study_design

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def inputs(tmp_path):
    pinned = json.loads((ROOT / "data/reference_company100_qids.json").read_text())
    tasks = [
        {
            "qid": qid,
            "graph": "company",
            "nl_question": "Question",
            "gold_cypher": "RETURN 1",
            "answer_json": "[[1]]",
        }
        for qid in [*pinned["qids"], *(f"synthetic-{i}" for i in range(247))]
    ]
    tasks_file, graph_file = tmp_path / "tasks.jsonl", tmp_path / "graph.json"
    tasks_file.write_text("".join(json.dumps(task) + "\n" for task in tasks))
    graph_file.write_text("{}")
    return tasks_file, graph_file, tasks


def test_offline_plan_never_certifies_or_authorizes_execution(inputs, tmp_path, monkeypatch):
    import httpx
    from neo4j import GraphDatabase

    def forbidden(*args, **kwargs):
        raise AssertionError("Offline preparation must not contact a service")

    monkeypatch.setattr(GraphDatabase, "driver", forbidden)
    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)
    plan = prepare_plan(ROOT, inputs[0], inputs[1], tmp_path / "missing-reference")
    assert plan["status"] == "draft-not-launchable" and plan["execution_authorized"] is False
    assert plan["reference"]["available_locally"] is False
    assert plan["protocol"]["controls"]["identity_mode"] == "property"
    for flag in (
        "live_graph_verified",
        "reference_tasks_verified",
        "rendered_prompts_frozen",
        "spending_bound_approved",
    ):
        assert plan[flag] is False
    assert set(plan["pending_gates"]) == {"G1", "G5", "G6", "G8"}
    assert set(plan["implemented_gates"]) == {"G7"}
    assert len(plan["schedule"]) == 18
    assert all(len(block["qids"]) == 347 for block in plan["schedule"])
    assert set(plan["profiles"]) == {"temp0-none", "temp1-medium"}
    serialized = json.dumps(plan)
    assert str(tmp_path) not in serialized
    assert '"gold_cypher":' not in serialized and '"answer_json":' not in serialized


def test_schedule_is_deterministic_and_matched_across_arms(inputs):
    design = study_design(ROOT)
    qids = [t["qid"] for t in inputs[2]]
    blocks = schedule(design, qids)
    assert blocks == schedule(design, list(reversed(qids)))
    for replica in range(1, 4):
        for profile in design["matrix"]["profiles"]:
            cell = [b for b in blocks if b["replica"] == replica and b["profile"] == profile]
            assert [b["arm"] for b in cell] == design["schedule"]["arm_orders"][replica - 1]
            assert len({b["task_order_sha256"] for b in cell}) == 1
            assert cell[0]["qids"] == cell[1]["qids"] == cell[2]["qids"]
    assert blocks[0]["profile"] != blocks[6]["profile"]


@pytest.mark.parametrize("change", ["duplicate", "missing", "mixed", "subset"])
def test_bad_task_sets_are_rejected(inputs, tmp_path, change):
    tasks_file, graph_file, tasks = inputs
    if change == "duplicate":
        tasks[-1] = tasks[0]
    elif change == "missing":
        tasks.pop()
    elif change == "mixed":
        tasks[0]["graph"] = "different"
    else:
        tasks[0]["qid"] = "not-the-pinned-qid"
    tasks_file.write_text("".join(json.dumps(task) + "\n" for task in tasks))
    with pytest.raises(ValueError):
        prepare_plan(ROOT, tasks_file, graph_file, tmp_path / "missing")


def test_schedule_rejects_inconsistent_design(inputs):
    design = deepcopy(study_design(ROOT))
    design["matrix"]["expected_runs"] += 1
    with pytest.raises(ValueError, match="counts"):
        schedule(design, [t["qid"] for t in inputs[2]])


def test_changed_profile_and_reference_pin_are_rejected(inputs, tmp_path, monkeypatch):
    from agent_native_graph.research import controlled_plan

    design = deepcopy(study_design(ROOT))
    monkeypatch.setattr(controlled_plan, "study_design", lambda root: design)
    design["profile_sha256"]["temp0-none"] = "0" * 64
    with pytest.raises(ValueError, match="Profile changed"):
        prepare_plan(ROOT, inputs[0], inputs[1], tmp_path / "missing")
    design.update(study_design(ROOT))
    design["reference_commit"] = "0" * 40
    with pytest.raises(ValueError, match="Reference revision"):
        prepare_plan(ROOT, inputs[0], inputs[1], tmp_path / "missing")


def test_retrieval_gate_is_not_claimed_for_an_unvalidated_revision(inputs, tmp_path, monkeypatch):
    from agent_native_graph.research import controlled_plan

    monkeypatch.setattr(controlled_plan, "RETRIEVAL_REFERENCE_COMMIT", "0" * 40)
    plan = prepare_plan(ROOT, inputs[0], inputs[1], tmp_path / "missing")
    assert "G7" in plan["pending_gates"] and not plan["implemented_gates"]
