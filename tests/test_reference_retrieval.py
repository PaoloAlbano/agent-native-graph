"""Pair the actual pinned workflows, changing only their final interpreter seam.

Opt in with ANA_TEST_REFERENCE=1; all providers and graph operations are fake.
"""

import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agent_native_graph.research.reference_adapters import build_profile_runner
from agent_native_graph.research.reference_source import reference_source

pytestmark = pytest.mark.skipif(
    os.environ.get("ANA_TEST_REFERENCE") != "1", reason="Opt-in pinned reference integration"
)
REFERENCE = Path(
    os.environ.get("ANA_REFERENCE_REPO", str(Path(__file__).resolve().parents[2] / "multigraphrag"))
)
COMMIT = "72fe7105310c85ebe6b1b3b7d4c6152ddb206393"


async def trajectory(mode, scenario):
    """Run the real controller with deterministic scripted observations and decisions."""
    from multigraphrag.config import Settings
    from multigraphrag.graph.models import QueryOutcome
    from multigraphrag.workflow.pipeline import GraphRAGPipeline
    from multigraphrag.workflow.single_pass import SinglePassRunner

    generation = 0
    graph_events = []

    async def chat(messages, *, response_format):
        nonlocal generation
        name = response_format["json_schema"]["name"]
        if name == "QueryGeneration":
            generation += 1
            response = {"cypher": f"RETURN {generation} AS n", "rationale": "A candidate"}
        elif name == "EvaluationResult":
            status = "accept"
            if scenario == "exhausted" or (scenario == "incorrect" and generation == 1):
                status = "incorrect"
            elif scenario.startswith("verify") and generation == 1:
                status = "error_or_empty"
            response = {"status": status, "feedback": "Inspect the candidate"}
        else:
            responses = {
                "ExtractedEntities": {
                    "node_labels": ["Asset"],
                    "node_property_values": [
                        {"label": "Asset", "property": "name", "value": "Alph"}
                    ]
                    if scenario == "verify_hallucination"
                    else [],
                    "pairwise_relationships": ["(:Asset)-[:LINK]->(:Asset)"],
                },
                "RankedSuggestion": {"best_candidate": "Alpha"},
                "FixInstructions": {"instructions": ["Correct the value"]},
                "AggregatedFeedback": {"instruction": "Refine this candidate"},
                "InterpretedAnswer": {"answer": "Original final prose"},
            }
            response = responses[name]
        return {"content": json.dumps(response)}

    class Graph:
        async def run_query(self, cypher, *, max_rows):
            graph_events.append(("run_query", cypher, max_rows))
            if scenario == "error_empty_recover":
                if generation == 1:
                    return QueryOutcome(success=False, error_message="Invalid candidate")
                if generation == 2:
                    return QueryOutcome(success=True, records=[])
            if scenario.startswith("verify") and generation == 1:
                return QueryOutcome(success=True, records=[])
            if scenario == "exhausted" and mode.startswith("single"):
                return QueryOutcome(success=False, error_message="Still invalid")
            return QueryOutcome(success=True, records=[{"n": generation}])

        async def label_exists(self, label):
            graph_events.append(("label_exists", label))
            return True

        async def relationship_pattern_exists(self, *pattern):
            graph_events.append(("relationship_pattern_exists", *pattern))
            return True

        async def property_value_exists(self, *value):
            graph_events.append(("property_value_exists", *value))
            return False

        async def get_all_property_values(self, *value):
            graph_events.append(("get_all_property_values", *value))
            return ["Alpha"]

    logger = MagicMock()
    settings = Settings(_env_file=None)
    runner = build_profile_runner(
        mode, settings, Graph(), SimpleNamespace(achat=chat, _model="fake"), logger
    )
    expected_type = SinglePassRunner if mode.startswith("single") else GraphRAGPipeline
    assert type(runner) is expected_type
    result = await runner.ask(question="Find a value", schema_text="(:Asset)-[:LINK]->(:Asset)")
    calls = [call.kwargs for call in logger.log.call_args_list]
    return result, calls, graph_events, settings.workflow.max_refinement_iterations


@pytest.mark.parametrize(
    "mode,scenario",
    [
        ("single", "success"),
        ("single", "error_empty_recover"),
        ("single", "exhausted"),
        ("agentic", "success"),
        ("agentic", "incorrect"),
        ("agentic", "verify_clean"),
        ("agentic", "verify_hallucination"),
        ("agentic", "exhausted"),
    ],
)
def test_retrieval_variant_preserves_every_decision_and_graph_observation(mode, scenario):
    with reference_source(REFERENCE, COMMIT):
        original, old_calls, old_graph, limit = asyncio.run(trajectory(mode, scenario))
        retrieval, new_calls, new_graph, _ = asyncio.run(trajectory(mode + "_retrieval", scenario))
    assert old_calls[-1]["agent"] == "interpreter"
    assert new_calls == old_calls[:-1]
    assert new_graph == old_graph
    assert retrieval.answer is None and original.answer == "Original final prose"
    for field in ("cypher", "accepted", "iterations", "records"):
        assert getattr(retrieval, field) == getattr(original, field)
    assert retrieval.cypher == f"RETURN {retrieval.iterations} AS n"
    roles = [call["agent"] for call in new_calls]
    assert "interpreter" not in roles
    if scenario == "exhausted":
        assert retrieval.iterations == limit and not retrieval.accepted
    elif scenario == "error_empty_recover":
        assert retrieval.iterations == 3 and roles == ["query_generator"] * 3
    elif scenario == "incorrect":
        assert roles == [
            "query_generator",
            "query_evaluator",
            "feedback_aggregator",
            "query_generator",
            "query_evaluator",
        ]
    elif scenario.startswith("verify"):
        assert "entity_extractor" in roles and "feedback_aggregator" in roles
        assert ("instructions_generator" in roles) == (scenario == "verify_hallucination")
        assert ("verification_ranker" in roles) == (scenario == "verify_hallucination")
