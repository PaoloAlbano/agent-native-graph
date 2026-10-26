"""Validate saved query re-execution evidence before publishing it in static docs."""

import hashlib
import json
from pathlib import Path

from agent_native_graph.research_common import result_matches_answer


def load_evaluation(root: Path, config: dict, pinned: dict, runs: list) -> dict | None:
    path = config.get("execution_evaluation")
    if not path:
        return None
    folder = root / path
    report = json.loads((folder / "manifest.json").read_text())
    if report["status"] != "complete" or report["snapshot_before"] != report["snapshot_after"]:
        raise ValueError("Query evaluation is incomplete or its graph changed")
    if any(report["source"][k] != config[k] for k in ("commit", "repository", "qid_file")):
        raise ValueError("Query evaluation source mismatch")
    if report["qid_sha256"] != pinned["qid_sha256"]:
        raise ValueError("Query evaluation QID mismatch")
    for run in runs:
        manifest = run["manifest"]
        if manifest["run_id"] not in report["ana"]:
            continue  # New contributions are not part of this saved evaluation.
        if (
            report["graph_sha256"] != manifest["graph_sha256"]
            or report["ana"][manifest["run_id"]]["run_sha256"] != manifest["run_sha256"]
        ):
            raise ValueError("Query evaluation ANA provenance mismatch")
    gold = {r["qid"]: r for r in runs[0]["records"]}
    for entry in [dict(report["gold"], file="gold.jsonl"), *report["baselines"].values()]:
        payload = (folder / entry["file"]).read_bytes()
        if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise ValueError("Query evaluation checksum mismatch")
        records = [json.loads(line) for line in payload.splitlines() if line.strip()]
        if len(records) != 100 or {r["qid"] for r in records} != set(pinned["qids"]):
            raise ValueError("Query evaluation must cover exactly 100 QIDs")
        for record in records:
            expected = gold[record["qid"]]["expected"]
            if record["expected"] != expected or record["matches_answer_json"] != (
                record["ok"] and result_matches_answer(record["rows"], expected)
            ):
                raise ValueError("Query evaluation verdict mismatch")
        if entry["correct"] != sum(r["matches_answer_json"] for r in records):
            raise ValueError("Query evaluation summary mismatch")
        entry["records"] = {r["qid"]: r for r in records}
    return report
