"""Check a prospective document, not compliance of runners with an unbuilt protocol."""

import hashlib
import math
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs/controlled-company-protocol.md"


@pytest.fixture(scope="module")
def design():
    blocks = re.findall(r"```yaml\n(.*?)```", DOCUMENT.read_text(), re.DOTALL)
    assert len(blocks) == 1
    return yaml.safe_load(blocks[0])


def test_protocol_is_explicitly_not_an_executable_authorization(design):
    assert design["status"] == "design-only"
    assert design["execution_authorized"] is False
    assert design["scope"]["graph"] == "company"
    assert design["scope"]["split"] == "test"
    assert design["scope"]["questions_per_run"] == 347
    assert (ROOT / design["scope"]["secondary_qid_file"]).is_file()


def test_proposed_matrix_and_stages_have_consistent_work_counts(design):
    matrix = design["matrix"]
    expected = (
        math.prod(len(matrix[key]) for key in ("models", "profiles", "arms")) * matrix["replicas"]
    )
    assert matrix["expected_runs"] == expected
    assert matrix["expected_question_executions"] == expected * design["scope"]["questions_per_run"]
    assert sum(stage["runs"] for stage in design["stages"].values()) == expected
    assert {stage["profile"] for stage in design["stages"].values()} == set(matrix["profiles"])
    for stage in design["stages"].values():
        assert stage["runs"] == len(matrix["models"]) * len(matrix["arms"]) * matrix["replicas"]
        assert stage["question_executions"] == stage["runs"] * design["scope"]["questions_per_run"]
    assert design["controls"]["semantic_generation_budget_per_question"] is None
    assert design["controls"]["budget_policy"] == "observe-native-limits-first"
    assert design["controls"]["native_limits"] == {
        "ana_decision_turns": 12,
        "reference_query_generator_iterations": 5,
    }
    assert "no full run is approved" in DOCUMENT.read_text()


def test_counterbalance_contains_each_arm_in_each_position(design):
    arms = design["matrix"]["arms"]
    orders = design["schedule"]["arm_orders"]
    assert len(orders) == design["matrix"]["replicas"] == len(arms)
    assert all(len(order) == len(arms) and set(order) == set(arms) for order in orders)
    assert all({order[position] for order in orders} == set(arms) for position in range(len(arms)))


def test_draft_references_exact_unchanged_llm_profiles(design):
    assert set(design["profile_sha256"]) == set(design["matrix"]["profiles"])
    for name, digest in design["profile_sha256"].items():
        path = ROOT / "src/agent_native_graph/profiles" / f"{name}.yaml"
        payload = path.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == digest
        profile = yaml.safe_load(payload)
        assert profile["max_tokens"] == design["controls"]["max_tokens_per_generation"] == 16000
        assert profile["tool_choice"] == "auto"
        assert profile["rate_limit_retry_s"] == 30
    assert design["controls"]["automatic_final_fetch"] is False
    assert design["controls"]["wrapper_planning"] is False
    assert design["controls"]["runner_guardrails"] is False


def test_protocol_source_links_resolve():
    for target in re.findall(r"\[[^]]*\]\(([^)]+)\)", DOCUMENT.read_text()):
        link = urlsplit(target)
        if not link.scheme and not link.netloc and link.path:
            assert (DOCUMENT.parent / unquote(link.path)).exists(), target
