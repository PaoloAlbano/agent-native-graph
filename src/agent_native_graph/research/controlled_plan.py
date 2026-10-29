"""Prepare a local, offline study plan; never launch or authorize inference."""

import argparse
import hashlib
import json
import random
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import yaml

from agent_native_graph.application.result_policy import result_policy
from agent_native_graph.application.run_config import (
    digest,
    execution_identity,
    file_hash,
    task_signature,
)
from agent_native_graph.research.reference_adapters import RETRIEVAL_REFERENCE_COMMIT


def study_design(root):
    """Use the document's single YAML block as the source of study decisions."""
    document = root / "docs/controlled-company-protocol.md"
    blocks = re.findall(r"```yaml\n(.*?)```", document.read_text(), re.DOTALL)
    if len(blocks) != 1:
        raise ValueError("The protocol must contain exactly one YAML design")
    design = yaml.safe_load(blocks[0])
    if design["status"] != "design-only" or design["execution_authorized"] is not False:
        raise ValueError("This planner accepts only an unauthorized design draft")
    return design


def schedule(design, qids):
    """Counterbalance arms; reuse exactly the same question order within each cell."""
    matrix, seed = design["matrix"], design["schedule"]["seed"]
    orders = design["schedule"]["arm_orders"]
    arms = matrix["arms"]
    if len(orders) != matrix["replicas"] or any(
        len(order) != len(arms) or set(order) != set(arms) for order in orders
    ):
        raise ValueError("Invalid counterbalanced arm orders")
    blocks = []
    for replica, arm_order in enumerate(orders, start=1):
        profiles = matrix["profiles"] if replica % 2 else list(reversed(matrix["profiles"]))
        for profile in profiles:
            ordered = sorted(qids)
            random.Random(f"{seed}:{profile}:{replica}").shuffle(ordered)
            for model in matrix["models"]:
                for arm in arm_order:
                    blocks.append(
                        {
                            "model": model,
                            "profile": profile,
                            "replica": replica,
                            "arm": arm,
                            "qids": ordered[:],
                            "task_order_sha256": digest(ordered),
                        }
                    )
    expected = matrix["expected_runs"]
    if len(blocks) != expected or len(blocks) * len(qids) != matrix["expected_question_executions"]:
        raise ValueError("Declared study counts do not match the schedule")
    return blocks


def prepare_plan(root, tasks_file, graph_file, reference_repo):
    """Hash available inputs and expose missing launch gates without contacting services."""
    root = Path(root)
    design = study_design(root)
    scope, controls = design["scope"], design["controls"]
    if scope["graph"] != "company" or scope["split"] != "test":
        raise ValueError("Only the Company test study is supported")
    if controls["identity_mode"] != "property":
        raise ValueError("Controlled benchmarks retain historical property identity")
    if controls.get("verify_graph_block") is not True:
        raise ValueError("Controlled studies require before/after block verification")
    policy = result_policy(controls["result_policy"])
    if policy is None or (controls["result_row_cap"], controls["feedback_preview_rows"]) != (
        policy.max_rows,
        policy.preview_rows,
    ):
        raise ValueError("Protocol result bounds differ from the implemented policy")
    tasks = [json.loads(line) for line in Path(tasks_file).read_text().splitlines() if line.strip()]
    qids = [task["qid"] for task in tasks]
    if len(qids) != scope["questions_per_run"] or len(set(qids)) != len(qids):
        raise ValueError("Expected the complete unique Company QID set")
    if any(task.get("graph") != "company" for task in tasks):
        raise ValueError("Mixed or missing graph category in tasks")
    pin_path = root / scope["secondary_qid_file"]
    pinned = json.loads(pin_path.read_text())
    subset = pinned["qids"]
    if (
        len(subset) != 100
        or len(set(subset)) != 100
        or not set(subset) <= set(qids)
        or hashlib.sha256("\n".join(sorted(subset)).encode()).hexdigest() != pinned["qid_sha256"]
    ):
        raise ValueError("Pinned secondary QID set does not match these tasks")
    profiles = {}
    for name in design["matrix"]["profiles"]:
        path = root / "src/agent_native_graph/profiles" / f"{name}.yaml"
        if file_hash(path) != design["profile_sha256"][name]:
            raise ValueError(f"Profile changed since protocol design: {name}")
        settings = yaml.safe_load(path.read_text())
        if (
            settings["max_tokens"] != controls["max_tokens_per_generation"]
            or settings["tool_choice"] != "auto"
        ):
            raise ValueError("Profile conflicts with the frozen generation policy")
        profiles[name] = {"sha256": file_hash(path), "settings": settings}
    source = json.loads((root / "docs/site/comparison-source.json").read_text())
    if source["commit"] != design["reference_commit"]:
        raise ValueError("Reference revision differs from the protocol design")
    reference = subprocess.run(
        ["git", "-C", str(reference_repo), "rev-parse", "--verify", source["commit"] + "^{commit}"],
        capture_output=True,
        text=True,
        check=False,
    )
    reference_present = reference.returncode == 0 and reference.stdout.strip() == source["commit"]
    retrieval_supported = source["commit"] == RETRIEVAL_REFERENCE_COMMIT
    revision = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    dirty = bool(subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"]))
    return {
        "format": "ana-controlled-plan-v1",
        "status": "draft-not-launchable",
        "execution_authorized": False,
        "protocol": design,
        "protocol_sha256": file_hash(root / "docs/controlled-company-protocol.md"),
        "source": {
            "commit": revision,
            "dirty": dirty,
            **execution_identity(
                SimpleNamespace(
                    native_tools=True, enable_planning_tools=False, schema_entry="overview"
                ),
                root,
            ),
        },
        "inputs": {
            "tasks_sha256": file_hash(Path(tasks_file)),
            "task_contents_sha256": task_signature(tasks),
            "qid_set_sha256": digest(sorted(qids)),
            "graph_file_sha256": file_hash(Path(graph_file)),
            "secondary_qid_file_sha256": file_hash(pin_path),
        },
        "profiles": profiles,
        "reference": {"commit": source["commit"], "available_locally": reference_present},
        "implemented_gates": {
            "G7": "Retrieval-only variants tested for trajectory parity with the pinned controllers."
        }
        if retrieval_supported
        else {},
        "schedule": schedule(design, qids),
        "pending_gates": {
            "G1": "Freeze the final source revision, rendered prompts and adapter hashes; approve the exact cells.",
            "G5": "Result bounds and before/after block evidence implemented opt-in; equal explicit observation information remains pending.",
            "G6": "Enforce common global HTTP concurrency, deadlines and retry policy; establish a spending bound.",
            **(
                {"G7": "Retrieval variants are not validated for this reference revision."}
                if not retrieval_supported
                else {}
            ),
            "G8": "Complete fake-provider checks and an explicitly approved technical smoke before full inference.",
        },
        "live_graph_verified": False,
        "reference_tasks_verified": False,
        "rendered_prompts_frozen": False,
        "spending_bound_approved": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--tasks", type=Path, default=Path("data/tasks_company_test.jsonl"))
    parser.add_argument("--graph", type=Path, default=Path("downloads/company_simplekg.json"))
    parser.add_argument("--reference-repo", type=Path, default=Path("../multigraphrag"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    plan = prepare_plan(args.repo_root, args.tasks, args.graph, args.reference_repo)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as stream:
        json.dump(plan, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(
        f"Prepared {len(plan['schedule'])} proposed blocks: {args.out}. No inference authorized or executed."
    )


if __name__ == "__main__":
    main()
