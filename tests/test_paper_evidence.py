"""Keep the paper's frozen observations grounded in saved evidence, without inference."""

import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from agent_native_graph import get_tool_specs
from agent_native_graph.research.docs_comparison import git_bytes, profile
from agent_native_graph.research.evaluation_storage import EvaluationReader

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper"


def table_rows(section: str) -> list[list[str]]:
    """Read the simple, pipe-delimited tables used in this Markdown draft."""
    return [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in section.splitlines()
        if line.startswith("|") and not re.match(r"^\|[\s:-]+\|", line)
    ][1:]


@pytest.fixture(scope="module")
def evaluation():
    text = (PAPER / "07-results.md").read_text()
    link = re.search(r"\[complete evaluation manifest\]\(([^)]+)\)", text).group(1)
    path = PAPER / link
    return path.parent, json.loads(path.read_text())


@pytest.fixture(scope="module")
def observations():
    text = (PAPER / "07-results.md").read_text()
    section = text.split("## ANA Full-Split Observations", 1)[1].split("## External Comparison", 1)[
        0
    ]
    entries = {}
    for row in table_rows(section):
        match = re.fullmatch(r"\[([^]]+)\]\(([^)]+)\)", row[0])
        assert match is not None
        label, link = match.groups()
        manifest_path = (PAPER / link).resolve()
        assert manifest_path.is_relative_to(ROOT / "results/cypherbench-company/full/runs")
        manifest = json.loads(manifest_path.read_text())
        folder = manifest_path.parent
        assert label not in entries
        entries[label] = {
            "folder": folder,
            "table": row,
            "manifest": manifest,
            "summary": json.loads((folder / "summary.json").read_text()),
            "records": [json.loads(line) for line in (folder / "run.jsonl").open() if line.strip()],
        }
    assert len(entries) == 13  # This paper snapshot need not grow with every future contribution.
    return entries


def test_full_split_table_matches_each_linked_observation(observations):
    aliases = {
        "GPT-OSS-120B": "openai/gpt-oss-120b",
        "GPT-OSS-20B": "openai/gpt-oss-20b",
        "Qwen3.5-27B": "Qwen/Qwen3.5-27B",
    }
    for entry in observations.values():
        row, manifest, summary = entry["table"], entry["manifest"], entry["summary"]
        assert aliases[row[1]] == manifest["model"]
        assert float(row[2]) == manifest["temperature"]
        assert row[3] == manifest["reasoning"]
        assert row[4] == f"{summary['matches']}/347"
        assert row[5] == f"{summary['ok']}/347"
        assert row[6] == f"{summary['avg_llm_calls']:.2f}"
        assert row[7] == f"{summary['avg_tool_calls']:.2f}"
    scores = [entry["summary"]["accuracy"] for entry in observations.values()]
    abstract = (PAPER / "00-abstract.md").read_text()
    assert f"{min(scores):.1%}-{max(scores):.1%}" in abstract


def test_shared_question_table_uses_the_linked_common_evaluator(observations, evaluation):
    section = (PAPER / "07-results.md").read_text().split("## External Comparison", 1)[1]
    _, report = evaluation
    assert report["status"] == "complete"
    assert report["snapshot_before"] == report["snapshot_after"]
    rows = table_rows(section)
    assert {row[0] for row in rows} == set(observations)
    for row in rows:
        manifest = observations[row[0]]["manifest"]
        ana = report["ana"][manifest["run_id"]]
        assert ana["run_sha256"] == manifest["run_sha256"]
        baselines = {
            Path(path).name: entry
            for path, entry in report["baselines"].items()
            if profile(entry["config"], True) == profile(manifest)
        }
        scores = [ana, baselines["single"], baselines["agentic"]]
        assert all(score["total"] == 100 for score in scores)
        assert row[1:] == [f"{score['correct']}/100" for score in scores]


def test_qwen_error_table_separates_terminal_failures_from_recovered_timeouts(observations):
    text = (PAPER / "08-error-analysis.md").read_text()
    for row in table_rows(text):
        if row[0] == "Observation":
            continue
        records = observations[row[0]]["records"]
        exhausted = sum(
            not r["ok"] and r["failure_class"] == "no_final_fetch_or_max_steps" for r in records
        )
        parsing = sum(not r["ok"] and r["failure_class"] == "json_decode" for r in records)
        timed_out = []
        for record in records:
            for step in record["transcript"]:
                result = step.get("result")
                error = str(result.get("error") or "") if isinstance(result, dict) else ""
                if "timeout" in error.lower() or "timed out" in error.lower():
                    timed_out.append(record)
                    break
        assert row[1:] == [
            str(exhausted),
            str(parsing),
            str(len(timed_out)),
            str(sum(r["matches_answer_json"] for r in timed_out)),
        ]


def test_gptoss20_request_table_uses_same_pinned_subset(observations):
    text = (ROOT / "docs/multigraphrag-comparison.md").read_text()
    section = text.split("### GPT-OSS-20B Request Observability", 1)[1]
    pinned = json.loads((ROOT / "data/reference_company100_qids.json").read_text())
    qids = set(pinned["qids"])
    by_profile = {
        f"T{int(e['manifest']['temperature'])}/{e['manifest']['reasoning']}": e
        for e in observations.values()
        if e["manifest"]["model"] == "openai/gpt-oss-20b"
    }
    for row in table_rows(section):
        entry = by_profile[row[0]]
        records = [r for r in entry["records"] if r["qid"] in qids]
        assert len(records) == 100
        assert row[1:3] == [
            f"{sum(r[key] for r in records) / 100:.2f}"
            for key in ("llm_call_count", "tool_call_count")
        ]
        assert row[5] == str(
            sum(
                r["request_accounting"]["summary"]["observed_usage_totals"]["total_tokens"]
                for r in records
            )
        )


@pytest.mark.skipif(
    not (ROOT.parent / "multigraphrag/.git").exists(),
    reason="Pinned external call logs require the optional sibling checkout",
)
def test_gptoss20_logged_calls_match_pinned_source():
    text = (ROOT / "docs/multigraphrag-comparison.md").read_text()
    section = text.split("### GPT-OSS-20B Request Observability", 1)[1]
    source = json.loads((ROOT / "docs/site/comparison-source.json").read_text())
    qids = set(json.loads((ROOT / "data/reference_company100_qids.json").read_text())["qids"])
    for row in table_rows(section):
        temperature, reasoning = row[0][1:].split("/")
        setting = (
            f"temp{float(temperature):.1f}-reasoning-{'off' if reasoning == 'none' else 'medium'}"
        )
        for column, mode in ((3, "single"), (4, "agentic")):
            path = f"results/openai--gpt-oss-20b/{setting}/company/{mode}/calls.jsonl"
            payload = git_bytes(ROOT.parent / "multigraphrag", "show", f"{source['commit']}:{path}")
            calls = [
                call
                for call in map(json.loads, payload.splitlines())
                if call.get("qid") in qids
                and call.get("domain") == "company"
                and call.get("mode") == mode
            ]
            assert row[column] == f"{len(calls) / 100:.2f}"


def test_paper_catalog_uses_actual_default_tool_names():
    text = (PAPER / "05-tool-design.md").read_text().split("## Schema Discovery", 1)[0]
    names = [name for row in table_rows(text) for name in re.findall(r"`([^`]+)`", row[1])]
    assert len(names) == len(set(names)) == 35
    assert set(names) == {spec["function"]["name"] for spec in get_tool_specs()}


def test_paper_local_links_resolve_and_bibliography_is_present():
    for path in PAPER.glob("*.md"):
        for target in re.findall(r"\[[^]]*\]\(([^)]+)\)", path.read_text()):
            link = urlsplit(target)
            if not link.scheme and not link.netloc and link.path:
                assert (path.parent / unquote(link.path)).exists(), (path.name, target)
    bibliography = (PAPER / "references.bib").read_text()
    assert "2412.18702" in bibliography and "2511.08274" in bibliography
    assert "72fe7105310c85ebe6b1b3b7d4c6152ddb206393" in bibliography


@pytest.fixture(scope="module")
def worked_examples():
    text = (PAPER / "appendix-a-worked-examples.md").read_text()
    cases = [json.loads(block) for block in re.findall(r"```json\n(.*?)```", text, re.DOTALL)]
    queries = re.findall(r"```cypher\n(.*?)```", text, re.DOTALL)
    assert len(cases) == 2 and len(queries) == 4
    return cases, [query.strip() for query in queries]


def test_worked_example_selection_ignores_baseline_outcomes(
    observations, evaluation, worked_examples
):
    _, report = evaluation
    rows = observations["Q28-0M"]["records"]
    pinned = json.loads((ROOT / "data/reference_company100_qids.json").read_text())
    candidates = sorted(
        (
            r
            for r in rows
            if r["qid"] in pinned["qids"]
            and r["qid"] not in report["gold"]["non_reproduced_qids"]
            and len(r["transcript"]) <= 6
            and 1 <= len(r["expected"]) <= 5
            and r["tool_error_count"] == 0
        ),
        key=lambda row: row["qid"],
    )
    success = next(r for r in candidates if r["matches_answer_json"])
    mismatch = next(r for r in candidates if r["ok"] and r["failure_class"] == "semantic_mismatch")
    cases, _ = worked_examples
    assert [case["qid"] for case in cases] == [success["qid"], mismatch["qid"]]


def assert_literal_excerpt(excerpt, actual):
    """Allow omitted dictionary fields, but not rewritten values or shortened lists."""
    if isinstance(excerpt, dict):
        assert isinstance(actual, dict) and excerpt.keys() <= actual.keys()
        for key, value in excerpt.items():
            assert_literal_excerpt(value, actual[key])
    elif isinstance(excerpt, list):
        assert isinstance(actual, list) and len(excerpt) == len(actual)
        for value, original in zip(excerpt, actual, strict=True):
            assert_literal_excerpt(value, original)
    else:
        assert excerpt == actual


def test_worked_examples_preserve_every_call_and_argument(observations, worked_examples):
    cases, _ = worked_examples
    for case in cases:
        row = next(
            r for r in observations[case["observation"]]["records"] if r["qid"] == case["qid"]
        )
        assert len(case["calls"]) == len(row["transcript"])
        for field in ("expected", "rows", "ok", "matches_answer_json"):
            assert case[field] == row[field]
        for displayed, recorded in zip(case["calls"], row["transcript"], strict=True):
            assert displayed["action"] == recorded["action"]
            assert_literal_excerpt(displayed["result_excerpt"], recorded["result"])


def test_worked_example_queries_are_saved_queries_not_idealized_rewrites(
    observations, evaluation, worked_examples
):
    folder, report = evaluation
    cases, queries = worked_examples
    for index, case in enumerate(cases):
        observation = observations[case["observation"]]
        record = next(r for r in observation["records"] if r["qid"] == case["qid"])
        assert queries[index * 2] == record["gold_cypher"]
        baselines = [
            entry
            for entry in report["baselines"].values()
            if profile(entry["config"], True) == profile(observation["manifest"])
        ]
        assert len(baselines) == 2
        for baseline in baselines:
            row = next(
                r
                for r in map(
                    json.loads,
                    EvaluationReader(folder)
                    .read(baseline["file"], baseline["sha256"])
                    .splitlines(),
                )
                if r["qid"] == case["qid"]
            )
            assert queries[index * 2 + 1] == row["query"]
            assert row["ok"] and row["matches_answer_json"]
            assert row["rows"] == case["expected"]


def test_related_work_references_are_in_the_bibliography():
    text = (PAPER / "02-background-and-related-work.md").read_text()
    bibliography = (PAPER / "references.bib").read_text()
    for source in (
        "https://aclanthology.org/2023.emnlp-main.574/",
        "https://arxiv.org/abs/2210.03629v3",
        "https://arxiv.org/abs/2307.07697v6",
        "https://arxiv.org/html/2308.03688v3",
        "https://arxiv.org/abs/2304.11015v3",
    ):
        assert source in text and source in bibliography
