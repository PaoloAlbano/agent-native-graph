"""Fail-closed evidence for one benchmark invocation, never a snapshot-isolation claim."""

import hashlib
import json
import re
from pathlib import Path
from tempfile import NamedTemporaryFile

from agent_native_graph.application.run_config import digest, file_hash


class GraphIntegrityError(ValueError):
    """A completed invocation cannot be archived as graph-verified evidence."""


def integrity_path(output):
    """Keep mutable block evidence separate from immutable run configuration."""
    return Path(output).with_suffix(".integrity.json")


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _snapshot_valid(snapshot):
    return isinstance(snapshot, dict) and all(
        isinstance(snapshot.get(kind), dict)
        and type(snapshot[kind].get("count")) is int
        and snapshot[kind]["count"] >= 0
        and _sha(snapshot[kind].get("sha256"))
        for kind in ("nodes", "edges")
    )


def run_coverage(path):
    """Hash exact raw bytes while retaining only question IDs in memory."""
    checksum, qids = hashlib.sha256(), []
    with Path(path).open("rb") as stream:
        for line in stream:
            checksum.update(line)
            if line.strip():
                qid = json.loads(line)["qid"]
                if not isinstance(qid, str) or not qid:
                    raise ValueError("Invalid result QID")
                qids.append(qid)
    return {
        "run_sha256": checksum.hexdigest(),
        "question_count": len(qids),
        "unique_question_count": len(set(qids)),
        "qid_set_sha256": digest(sorted(set(qids))),
    }


class GraphBlock:
    """Seal before/after fingerprints only after writers and question tasks settle."""

    def __init__(self, output, configuration, graph, preflight, qids):
        qids = list(qids)
        if (
            not qids
            or len(set(qids)) != len(qids)
            or any(not isinstance(q, str) or not q for q in qids)
        ):
            raise ValueError("Graph blocks require unique nonempty QIDs")
        self.output, self.configuration, self.graph = map(Path, (output, configuration, graph))
        self.path = integrity_path(output)
        self.database = preflight["database"]
        if (
            not isinstance(self.database, str)
            or not self.database.strip()
            or not _snapshot_valid(preflight["snapshot"])
            or not _sha(preflight["graph_sha256"])
        ):
            raise ValueError("Malformed graph preflight evidence")
        self.report = {
            "version": "ana-graph-integrity-v1",
            "scope": "graph-content-and-task-coverage",
            "status": "running",
            "database": self.database,
            "before": preflight["snapshot"],
            "after": None,
            "graph_sha256": preflight["graph_sha256"],
            "source_config_sha256": file_hash(self.configuration),
            "expected_question_count": len(qids),
            "expected_qid_set_sha256": digest(sorted(qids)),
        }
        self.report = json.loads(json.dumps(self.report))

    def start(self):
        """Reserve a fresh sidecar; never overwrite another run or resume an old block."""
        with self.path.open("x", encoding="utf-8") as stream:
            json.dump(self.report, stream, indent=2)
            stream.write("\n")

    def finish(self, after, *, run_failed=False, postcheck_error=None):
        """Keep invalid/incomplete diagnostics; no scores or raw records are rewritten."""
        report = {**self.report, "after": after, "issues": []}
        issues = report["issues"]
        if run_failed:
            issues.append("run_failed")
        if postcheck_error is not None or not _snapshot_valid(after):
            issues.append("postcheck_failed")
            report["postcheck_error_type"] = postcheck_error or "MissingSnapshot"
        elif after != report["before"]:
            issues.append("graph_changed")
        try:
            report["graph_sha256_after"] = file_hash(self.graph)
            report["source_config_sha256_after"] = file_hash(self.configuration)
            if report["graph_sha256_after"] != report["graph_sha256"]:
                issues.append("graph_file_changed")
            if report["source_config_sha256_after"] != report["source_config_sha256"]:
                issues.append("configuration_changed")
            report.update(run_coverage(self.output))
            if (
                report["question_count"] != report["expected_question_count"]
                or report["unique_question_count"] != report["question_count"]
                or report["qid_set_sha256"] != report["expected_qid_set_sha256"]
            ):
                issues.append("question_coverage_mismatch")
        except Exception as exc:
            issues.append("evidence_read_failed")
            report["evidence_error_type"] = type(exc).__name__
        invalid = {"graph_changed", "graph_file_changed", "configuration_changed"}
        report["status"] = (
            "invalid" if invalid.intersection(issues) else ("incomplete" if issues else "verified")
        )
        temporary = None
        try:
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, delete=False
            ) as stream:
                temporary = Path(stream.name)
                json.dump(report, stream, indent=2)
                stream.write("\n")
            temporary.replace(self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return report


def validate_integrity(report_path, output, *, configuration=None):
    """Validate both raw and archived evidence, including exact byte/QID coverage."""
    report = json.loads(Path(report_path).read_text())
    if (
        report.get("version") != "ana-graph-integrity-v1"
        or not isinstance(report.get("database"), str)
        or not report["database"].strip()
        or report.get("scope") != "graph-content-and-task-coverage"
        or report.get("status") != "verified"
        or report.get("issues") != []
        or not _snapshot_valid(report.get("before"))
        or not _sha(report.get("graph_sha256"))
        or not _sha(report.get("source_config_sha256"))
        or type(report.get("expected_question_count")) is not int
        or report["expected_question_count"] < 1
        or report.get("after") is None
        or report.get("before") != report.get("after")
        or report.get("graph_sha256") != report.get("graph_sha256_after")
        or report.get("source_config_sha256") != report.get("source_config_sha256_after")
    ):
        raise GraphIntegrityError("Graph block is not verified; do not publish this run")
    actual = run_coverage(output)
    if any(report.get(key) != value for key, value in actual.items()) or (
        actual["question_count"] != report.get("expected_question_count")
        or actual["unique_question_count"] != actual["question_count"]
        or actual["qid_set_sha256"] != report.get("expected_qid_set_sha256")
    ):
        raise GraphIntegrityError("Graph block result checksum or question coverage mismatch")
    if (
        configuration is not None
        and file_hash(Path(configuration)) != report["source_config_sha256"]
    ):
        raise GraphIntegrityError("Graph block configuration checksum mismatch")
    return report
