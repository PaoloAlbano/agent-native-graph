"""Re-score pinned saved Cypher on a content-verified Company graph, without LLMs."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from neo4j import READ_ACCESS, GraphDatabase, Query

from agent_native_graph.research.docs_comparison import git_bytes, key, profile, validate_trace
from agent_native_graph.research.docs_results import read_runs
from agent_native_graph.research.evaluation_storage import compact_evaluations
from agent_native_graph.research.load_simplekg_neo4j import load_simplekg
from agent_native_graph.research.read_only import execute_read_only as execute_read_only
from agent_native_graph.research_common import (
    add_neo4j_args,
    append_jsonl,
    normalize_answer_rows,
    result_matches_answer,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def item_hash(value) -> bytes:
    normalized = normalize_answer_rows([[value]])[0][0]
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).digest()


def fingerprint(items) -> dict:
    """Hash a sorted multiset of records, retaining duplicate multiplicity."""
    hashes = sorted(item_hash(item) for item in items)
    return {"count": len(hashes), "sha256": hashlib.sha256(b"".join(hashes)).hexdigest()}


def expected_snapshot(graph: Path) -> dict:
    normalized = load_simplekg(graph)

    def properties(props):
        # Neo4j does not persist null properties under SET +=.
        return {k: v for k, v in props.items() if v is not None}

    return {
        "nodes": fingerprint(
            [sorted(set(["Entity", *n["labels"]])), properties(n["properties"])]
            for n in normalized["nodes"]
        ),
        "edges": fingerprint(
            [e["source_id"], e["type"], e["target_id"], properties(e["properties"])]
            for e in normalized["edges"]
        ),
    }


def database_snapshot(driver, database: str) -> dict:
    with driver.session(
        database=database, default_access_mode=READ_ACCESS, fetch_size=2000
    ) as session:
        nodes = fingerprint(
            [sorted(r["labels"]), r["props"]]
            for r in session.run(
                Query("MATCH (n) RETURN labels(n) AS labels, properties(n) AS props", timeout=300)
            )
        )
        edges = fingerprint(
            [r["source"], r["type"], r["target"], r["props"]]
            for r in session.run(
                Query(
                    "MATCH (a)-[r]->(b) RETURN a.id AS source, type(r) AS type, b.id AS target, properties(r) AS props",
                    timeout=300,
                )
            )
        )
    return {"nodes": nodes, "edges": edges}


def summarize(rows: list[dict]) -> dict:
    return {
        "total": len(rows),
        "correct": sum(r["matches_answer_json"] for r in rows),
        "execution_ok": sum(r["ok"] for r in rows),
        "errors": sum(not r["ok"] for r in rows),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_neo4j_args(parser)
    parser.set_defaults(query_timeout_s=30.0)
    parser.add_argument("--database", default="neo4j")
    parser.add_argument("--reference-repo", type=Path, default=Path("../multigraphrag"))
    parser.add_argument("--graph", type=Path, default=Path("downloads/company_simplekg.json"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--storage",
        choices=("compact", "legacy"),
        default="compact",
        help="Seal complete evaluations in shared compact storage, or retain standalone JSONL files.",
    )
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError(
            "Output directory already exists; use a new directory to preserve evidence"
        )
    root = Path.cwd()
    source = json.loads((root / "docs/site/comparison-source.json").read_text())
    pinned = json.loads((root / source["qid_file"]).read_text())
    qids = set(pinned["qids"])
    if (
        len(qids) != 100
        or hashlib.sha256("\n".join(sorted(qids)).encode()).hexdigest() != pinned["qid_sha256"]
    ):
        raise ValueError("Invalid pinned QID set")
    runs = read_runs(root)
    graph_sha = sha256(args.graph)
    if any(r["manifest"].get("graph_sha256") != graph_sha for r in runs):
        raise ValueError("Graph file hash differs from the archived ANA manifests")
    gold = {r["qid"]: r for r in runs[0]["records"]}
    commit = source["commit"]
    wanted = {profile(r["manifest"]) for r in runs}
    files = (
        git_bytes(args.reference_repo, "ls-tree", "-r", "--name-only", commit, "results")
        .decode()
        .splitlines()
    )
    baselines = []
    for filename in files:
        parts = Path(filename).parts
        if (
            len(parts) != 6
            or parts[-3] != "company"
            or parts[-2] not in ("single", "agentic")
            or parts[-1] != "run.json"
        ):
            continue
        manifest = json.loads(git_bytes(args.reference_repo, "show", f"{commit}:{filename}"))
        if profile(manifest, True) not in wanted:
            continue
        trace_path = str(Path(filename).with_name("trace.jsonl"))
        payload = git_bytes(args.reference_repo, "show", f"{commit}:{trace_path}")
        traces = validate_trace(
            [json.loads(line) for line in payload.splitlines() if line.strip()], qids, gold
        )
        baselines.append(
            {
                "path": str(Path(filename).parent),
                "config": manifest,
                "trace_sha256": hashlib.sha256(payload).hexdigest(),
                "traces": traces,
            }
        )
    if len(baselines) != len(wanted) * 2 or {
        (*profile(b["config"], True), Path(b["path"]).name) for b in baselines
    } != {(*p, mode) for p in wanted for mode in ("single", "agentic")}:
        raise ValueError("Missing baseline profiles")
    print("Verifying full graph content against the ANA graph file...", flush=True)
    expected = expected_snapshot(args.graph)
    driver = GraphDatabase.driver(args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password))
    report = None
    try:
        before = database_snapshot(driver, args.database)
        if before != expected:
            raise ValueError(
                f"Graph content mismatch; no queries evaluated: expected={expected}, actual={before}"
            )
        args.out.mkdir(parents=True)
        report = {
            "status": "running",
            "created_at": datetime.now(UTC).isoformat(),
            "source": source,
            "qid_sha256": pinned["qid_sha256"],
            "graph_sha256": graph_sha,
            "snapshot_before": before,
            "query_timeout_s": args.query_timeout_s,
            "max_rows": 100000,
            "metric": "ana_exact_answer_json_on_reexecuted_cypher",
            "comparator_sha256": sha256(root / "src/agent_native_graph/research_common.py"),
            "ana": {},
            "baselines": {},
        }
        (args.out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
        gold_rows = []
        for i, qid in enumerate(sorted(qids), 1):
            task = gold[qid]
            execution = execute_read_only(
                driver, args.database, task["gold_cypher"], args.query_timeout_s
            )
            row = {
                "qid": qid,
                "query": task["gold_cypher"],
                "expected": task["expected"],
                **execution,
                "matches_answer_json": execution["ok"]
                and result_matches_answer(execution["rows"], task["expected"]),
            }
            append_jsonl(args.out / "gold.jsonl", row)
            gold_rows.append(row)
            if i % 20 == 0:
                print(f"Gold validation {i}/100", flush=True)
        report["gold"] = summarize(gold_rows)
        report["gold"]["non_reproduced_qids"] = [
            r["qid"] for r in gold_rows if not r["matches_answer_json"]
        ]
        if any(not r["ok"] for r in gold_rows):
            raise ValueError("Some golden queries failed to execute; evaluation is incomplete")
        valid = {r["qid"] for r in gold_rows if r["matches_answer_json"]}
        for run in runs:
            selected = [r for r in run["records"] if r["qid"] in qids]
            rescored = [
                dict(
                    r,
                    matches_answer_json=bool(r["ok"])
                    and result_matches_answer(r["rows"], r["expected"]),
                )
                for r in selected
            ]
            if any(
                a["matches_answer_json"] != b["matches_answer_json"]
                for a, b in zip(selected, rescored, strict=True)
            ):
                raise ValueError("Archived ANA verdict differs from current comparator")
            report["ana"][run["manifest"]["run_id"]] = {
                **summarize(rescored),
                "run_sha256": run["manifest"]["run_sha256"],
                "gold_reproduced": summarize([r for r in rescored if r["qid"] in valid]),
            }
        for baseline in baselines:
            name = baseline["path"]
            outfile = f"baseline-{key(name)}.jsonl"
            rows = []
            print(f"Evaluating {name}", flush=True)
            for i, qid in enumerate(sorted(qids), 1):
                query = baseline["traces"][qid].get("generated_cypher")
                execution = execute_read_only(driver, args.database, query, args.query_timeout_s)
                row = {
                    "qid": qid,
                    "query": query,
                    "expected": gold[qid]["expected"],
                    **execution,
                    "matches_answer_json": execution["ok"]
                    and result_matches_answer(execution["rows"], gold[qid]["expected"]),
                }
                append_jsonl(args.out / outfile, row)
                rows.append(row)
                if i % 20 == 0:
                    print(
                        f"  {i}/100; correct={sum(r['matches_answer_json'] for r in rows)}",
                        flush=True,
                    )
            report["baselines"][name] = {
                **summarize(rows),
                "file": outfile,
                "sha256": sha256(args.out / outfile),
                "trace_sha256": baseline["trace_sha256"],
                "config": baseline["config"],
                "gold_reproduced": summarize([r for r in rows if r["qid"] in valid]),
            }
        print("Checking graph content again after evaluation...", flush=True)
        report["snapshot_after"] = database_snapshot(driver, args.database)
        if report["snapshot_after"] != before:
            raise ValueError("Graph changed during evaluation; do not publish these scores")
        report["gold"]["sha256"] = sha256(args.out / "gold.jsonl")
        report["status"] = "complete"
        (args.out / "manifest.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        )
        if args.storage == "compact":
            compact_evaluations(args.out.parent, folders=[args.out])
        print(
            json.dumps(
                {
                    "gold": report["gold"],
                    "scores": {
                        k: {f: v[f] for f in ("correct", "total", "errors")}
                        for k, v in report["baselines"].items()
                    },
                },
                indent=2,
            ),
            flush=True,
        )
    except Exception as exc:
        if report is not None and report.get("status") != "complete":
            report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            (args.out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
        raise
    finally:
        driver.close()


if __name__ == "__main__":
    main()
