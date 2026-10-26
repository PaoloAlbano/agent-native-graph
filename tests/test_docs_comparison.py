import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from agent_native_graph.research import docs_comparison as module

ROOT = Path(__file__).resolve().parents[1]


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args]).decode().strip()


@pytest.fixture
def reference(tmp_path, monkeypatch):
    root = tmp_path / "ana"
    source = root / "docs/site"
    source.mkdir(parents=True)
    (source / "comparison.template.html").write_text(
        (ROOT / "docs/site/comparison.template.html").read_text()
    )
    repo = tmp_path / "external"
    repo.mkdir()
    git(repo, "init", "-q")
    records = [
        {
            "qid": f"q{i:03}",
            "nl_question": f"Question {i}",
            "gold_cypher": "RETURN 1",
            "matches_answer_json": True,
        }
        for i in range(100)
    ]
    for mode in ("single", "agentic"):
        folder = repo / f"results/model/profile/company/{mode}"
        folder.mkdir(parents=True)
        manifest = {
            "model": "test/model",
            "temperature": 0,
            "reasoning_enabled": False,
            "reasoning_effort": "medium",
            "domains": ["company"],
            "split": "test",
            "use_judge": True,
            "judge_mode": "self",
            "results": [{"domain": "company", "mode": mode, "total": 100, "correct": 100}],
        }
        (folder / "run.json").write_text(json.dumps(manifest))
        traces = [
            {
                "qid": r["qid"],
                "question": r["nl_question"],
                "gold_cypher": r["gold_cypher"],
                "domain": "company",
                "mode": mode,
                "correct": True,
            }
            for r in records
        ]
        (folder / "trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in traces))
        (folder / "calls.jsonl").write_text(
            json.dumps(
                {
                    "qid": "q000",
                    "domain": "company",
                    "mode": mode,
                    "agent": "query_generator",
                    "response": "RETURN 1",
                }
            )
            + "\n"
        )
    git(repo, "add", ".")
    git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-qm",
        "fixture",
    )
    commit = git(repo, "rev-parse", "HEAD")
    config = {
        "repository": "example/repo",
        "branch": "reference",
        "commit": commit,
        "qid_file": "qids.json",
    }
    (source / "comparison-source.json").write_text(json.dumps(config))
    qids = sorted(r["qid"] for r in records)
    (root / "qids.json").write_text(
        json.dumps(
            {"qids": qids, "qid_sha256": hashlib.sha256("\n".join(qids).encode()).hexdigest()}
        )
    )
    manifest = {
        "run_id": "ana-test",
        "model": "test/model",
        "temperature": 0,
        "reasoning": "none",
        "created_at": "2026-10-26",
        "source_file": "/private/file",
    }
    monkeypatch.setattr(
        module, "read_runs", lambda root: [{"manifest": manifest, "records": records}]
    )
    output = tmp_path / "out"
    output.mkdir()
    return root, repo, output, records


def test_comparison_uses_pinned_git_objects_not_dirty_worktree(reference):
    root, repo, output, _ = reference
    (repo / "results/model/profile/company/single/trace.jsonl").write_text("broken local edit")
    module.publish_comparison(root, output, repo)
    overview = (output / "comparison.html").read_text()
    assert "Query correctness and textual-answer judging are different metrics" in overview
    assert "re-executed exact match" not in overview
    assert "100/100" in overview
    assert "source judge" in overview
    assert len(list(output.glob("comparison-*.html"))) == 101
    provenance = json.loads((output / "data/comparison/provenance.json").read_text())
    assert provenance["count"] == 100
    assert len(provenance["artifacts"]) == 6
    meta = json.loads(
        (output / f"data/comparison/{module.key('ana-test')}/{module.key('q000')}.json").read_text()
    )
    assert "source_file" not in meta["ana"]["config"]
    detail = json.loads((output / meta["external"]["single"]["detail"]).read_text())
    assert detail["logs"]["calls.jsonl"][0]["response"] == "RETURN 1"
    assert detail["trace"]["correct"] is True


def test_without_external_repo_scores_are_not_invented(reference):
    root, _, output, _ = reference
    module.publish_comparison(root, output, None)
    text = (output / "comparison.html").read_text()
    assert "not included in this build" in text
    assert "100/100" not in text


def test_new_model_without_baseline_does_not_break_build(reference, monkeypatch):
    root, repo, output, _ = reference
    runs = module.read_runs(root)
    new = {
        **runs[0],
        "manifest": {**runs[0]["manifest"], "run_id": "new-run", "model": "new/model"},
    }
    monkeypatch.setattr(module, "read_runs", lambda root: [*runs, new])
    module.publish_comparison(root, output, repo)
    text = (output / "comparison.html").read_text()
    assert "matching baseline pair not available" in text
    assert "new-run" in text
    assert "100/100" in text


def test_trace_rejects_duplicate_qids_and_changed_questions(reference):
    _, _, _, records = reference
    gold = {r["qid"]: r for r in records}
    rows = [
        {
            "qid": r["qid"],
            "question": r["nl_question"],
            "gold_cypher": r["gold_cypher"],
            "domain": "company",
            "correct": True,
        }
        for r in records
    ]
    rows[-1] = rows[0]
    with pytest.raises(ValueError, match="100 unique"):
        module.validate_trace(rows, set(gold), gold)
    rows[-1] = {
        "qid": "q099",
        "question": "Changed",
        "gold_cypher": "RETURN 1",
        "domain": "company",
        "correct": True,
    }
    with pytest.raises(ValueError, match="Question text"):
        module.validate_trace(rows, set(gold), gold)


def test_mismatched_qid_hash_fails_closed(reference):
    root, repo, output, _ = reference
    data = json.loads((root / "qids.json").read_text())
    data["qid_sha256"] = "bad"
    (root / "qids.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Invalid pinned"):
        module.publish_comparison(root, output, repo)
