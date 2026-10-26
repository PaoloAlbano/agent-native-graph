"""Build Company-only, provenance-pinned comparison pages without re-scoring prose."""

import hashlib
import json
import re
import subprocess
from collections import defaultdict
from html import escape
from pathlib import Path

from agent_native_graph.research.docs_reexecution import load_evaluation
from agent_native_graph.research.docs_results import read_runs, write_json


def key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def git_bytes(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args])


def profile(manifest: dict, external: bool = False) -> tuple:
    reasoning = manifest.get("reasoning")
    if external:
        enabled = manifest.get("reasoning_enabled")
        reasoning = (
            "none"
            if enabled is False
            else manifest.get("reasoning_effort")
            if enabled is True
            else "unknown"
        )
    return manifest["model"], manifest["temperature"], reasoning


def validate_trace(rows: list[dict], qids: set[str], gold: dict[str, dict]) -> dict[str, dict]:
    indexed = {r["qid"]: r for r in rows}
    if len(rows) != 100 or len(indexed) != 100 or set(indexed) != qids:
        raise ValueError("External Company trace must contain exactly the pinned 100 unique QIDs")
    for qid, row in indexed.items():
        if row.get("domain") != "company":
            raise ValueError("Only Company evidence is allowed")
        if row["question"] != gold[qid]["nl_question"]:
            raise ValueError(f"Question text mismatch: {qid}")
        if " ".join(row["gold_cypher"].split()) != " ".join(gold[qid]["gold_cypher"].split()):
            raise ValueError(f"Golden query mismatch: {qid}")
        if not isinstance(row.get("correct"), bool):
            raise ValueError(f"Missing external verdict: {qid}")
    return indexed


def page(root: Path, title: str, content: str, data: str = "") -> str:
    template = (root / "docs/site/comparison.template.html").read_text()
    values = {
        "TITLE": escape(title),
        "CONTENT": content,
        "DATA": data,
        "SCRIPTS": '<script defer src="assets/results-ui.js"></script><script defer src="assets/comparison.js"></script>'
        if data
        else "",
    }
    return re.sub(r"@@([A-Z_]+)@@", lambda m: values[m[1]], template)


def publish_comparison(root: Path, output: Path, reference_repo: Path | None) -> None:
    config = json.loads((root / "docs/site/comparison-source.json").read_text())
    if reference_repo is None:
        (output / "comparison.html").write_text(
            page(
                root,
                "Comparison evidence",
                "<p>External evidence is not included in this build. Rebuild with <code>--reference-repo PATH</code> pointing to the reference Git repository. No comparison scores are available without the pinned source.</p>",
            )
        )
        return
    commit = config["commit"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("The external source must be pinned to a full commit hash")
    git_bytes(reference_repo, "rev-parse", "--verify", f"{commit}^{{commit}}")
    pinned = json.loads((root / config["qid_file"]).read_text())
    qids = set(pinned["qids"])
    if (
        len(qids) != 100
        or len(pinned["qids"]) != 100
        or hashlib.sha256("\n".join(sorted(qids)).encode()).hexdigest() != pinned["qid_sha256"]
    ):
        raise ValueError("Invalid pinned Company QID set")
    ana_runs = read_runs(root)
    evaluation = load_evaluation(root, config, pinned, ana_runs)
    wanted = {profile(r["manifest"]) for r in ana_runs}
    gold = {r["qid"]: r for r in ana_runs[0]["records"]}
    if not qids <= gold.keys():
        raise ValueError("ANA runs do not cover the reference 100 QIDs")
    base = f"https://github.com/{config['repository']}/blob/{commit}"
    files = (
        git_bytes(reference_repo, "ls-tree", "-r", "--name-only", commit, "results")
        .decode()
        .splitlines()
    )
    baselines = {}
    provenance = {
        "source": config,
        "qid_sha256": pinned["qid_sha256"],
        "count": 100,
        "artifacts": {},
    }

    def read(path: str) -> bytes:
        payload = git_bytes(reference_repo, "show", f"{commit}:{path}")
        provenance["artifacts"][path] = hashlib.sha256(payload).hexdigest()
        return payload

    for filename in files:
        parts = Path(filename).parts
        if (
            len(parts) != 6
            or parts[-3] != "company"
            or parts[-2] not in ("single", "agentic")
            or parts[-1] != "run.json"
        ):
            continue
        manifest = json.loads(read(filename))
        if profile(manifest, True) not in wanted:
            continue
        if (
            manifest.get("domains") != ["company"]
            or manifest.get("split") != "test"
            or not manifest.get("use_judge")
        ):
            raise ValueError(f"Unsupported baseline scope or scoring: {filename}")
        folder = str(Path(filename).parent)
        trace_path = f"{folder}/trace.jsonl"
        traces = validate_trace(
            [json.loads(line) for line in read(trace_path).splitlines() if line.strip()], qids, gold
        )
        mode = parts[-2]
        if any(row.get("mode") != mode for row in traces.values()):
            raise ValueError(f"Mixed modes in external trace: {trace_path}")
        aggregate = next(
            r for r in manifest["results"] if r["domain"] == "company" and r["mode"] == mode
        )
        correct = sum(r["correct"] for r in traces.values())
        if aggregate["total"] != 100 or aggregate["correct"] != correct:
            raise ValueError(f"External summary mismatch: {filename}")
        logs = defaultdict(lambda: defaultdict(list))
        for logname in ("calls.jsonl", "judge_calls.jsonl", "judge_fixed_calls.jsonl"):
            path = f"{folder}/{logname}"
            if path not in files:
                continue
            for line in read(path).splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("qid") in qids:
                    if row.get("domain") != "company" or row.get("mode") != mode:
                        raise ValueError(f"Mixed scope in external call log: {path}")
                    logs[row["qid"]][logname].append(row)
        baseline = {
            "config": manifest,
            "correct": correct,
            "path": folder,
            "source": f"{base}/{filename}",
            "details": {},
        }
        executed = evaluation["baselines"].get(folder) if evaluation else None
        if executed and executed["trace_sha256"] != provenance["artifacts"][trace_path]:
            raise ValueError("Re-executed trace differs from the pinned source")
        if executed:
            baseline["execution_correct"] = executed["correct"]
        for qid, trace in traces.items():
            execution = executed["records"][qid] if executed else None
            if execution and execution["query"] != trace.get("generated_cypher"):
                raise ValueError("Re-executed query differs from the pinned source")
            detail = f"data/comparison/external-{key(folder)}/{key(qid)}.json"
            write_json(
                output / detail,
                {
                    "trace": trace,
                    "logs": dict(logs[qid]),
                    "source": f"{base}/{trace_path}",
                    "execution": execution,
                },
            )
            baseline["details"][qid] = {
                "path": detail,
                "correct": trace["correct"],
                "execution_correct": execution["matches_answer_json"] if execution else None,
                "logged_calls": len(logs[qid].get("calls.jsonl", [])),
            }
        identity = (*profile(manifest, True), mode)
        if identity in baselines:
            raise ValueError(f"Ambiguous baseline profile: {identity}")
        baselines[identity] = baseline

    overview = []
    exact_overview = []
    unavailable = []
    for ana in ana_runs:
        manifest = ana["manifest"]
        run_key = key(manifest["run_id"])
        matching = {
            mode: baselines.get((*profile(manifest), mode)) for mode in ("single", "agentic")
        }
        if not all(matching.values()):
            unavailable.append(
                f'<li><a href="run-{run_key}.html">{escape(manifest["run_id"])}</a>: matching baseline pair not available.</li>'
            )
            continue
        has_execution = bool(
            evaluation
            and manifest["run_id"] in evaluation["ana"]
            and all("execution_correct" in b for b in matching.values())
        )
        records = {r["qid"]: r for r in ana["records"]}
        score = sum(records[qid]["matches_answer_json"] for qid in qids)
        title = f"{manifest['model']} · Temperature {manifest['temperature']:g} · Reasoning {manifest['reasoning']} · {manifest['created_at'][:10]}"
        profile_page = f"comparison-{run_key}.html"
        overview.append(
            f'<tr><th><a href="{profile_page}">{escape(title)}</a></th><td>{score}/100</td><td>{matching["single"]["correct"]}/100</td><td>{matching["agentic"]["correct"]}/100</td></tr>'
        )
        if has_execution:
            exact_overview.append(
                f'<tr><th><a href="{profile_page}">{escape(title)}</a></th><td>{score}/100</td><td>{matching["single"]["execution_correct"]}/100</td><td>{matching["agentic"]["execution_correct"]}/100</td></tr>'
            )
        elif evaluation:
            unavailable.append(
                f'<li><a href="{profile_page}">{escape(title)}</a>: original metrics available; common-metric validation pending.</li>'
            )
        rows = []
        exact_rows = []
        for qid in sorted(qids):
            record = records[qid]
            qkey = key(qid)
            question_page = f"comparison-{run_key}-{qkey}.html"
            detail_path = f"data/comparison/{run_key}/{qkey}.json"
            evidence = {
                "question": record["nl_question"],
                "qid": qid,
                "ana": {
                    "config": manifest,
                    "detail": f"data/results/{run_key}/{qkey}.json",
                    "page": f"run-{run_key}.html#q={qid}",
                },
                "external": {
                    mode: {
                        "config": b["config"],
                        "detail": b["details"][qid]["path"],
                        "source": b["source"],
                    }
                    for mode, b in matching.items()
                },
                "commit": commit,
                "gold_reproduced": qid not in evaluation["gold"]["non_reproduced_qids"]
                if evaluation
                else None,
            }
            # Do not publish local invocation paths from manifests.
            evidence["ana"]["config"] = {k: v for k, v in manifest.items() if k != "source_file"}
            write_json(output / detail_path, evidence)
            content = f'<p><a href="{profile_page}">← All 100 questions in this comparison</a></p><p>{escape(title)}</p><h2>{escape(record["nl_question"])}</h2><p><code>{qid}</code></p><div id="comparison-detail" role="status">Loading this question only…</div><noscript>Enable JavaScript to inspect evidence, or follow the pinned source links on the comparison overview.</noscript>'
            (output / question_page).write_text(
                page(root, "Question evidence", content, detail_path), encoding="utf-8"
            )
            verdicts = ["Match" if record["matches_answer_json"] else "No match"] + [
                "Correct" if matching[m]["details"][qid]["correct"] else "Incorrect"
                for m in ("single", "agentic")
            ]
            rows.append(
                f'<tr><th><a href="{question_page}">{escape(record["nl_question"])}</a><br><small>{qid}</small></th>'
                + "".join(f"<td>{v}</td>" for v in verdicts)
                + "</tr>"
            )
            if has_execution:
                exact_verdicts = [
                    record["matches_answer_json"],
                    *[
                        matching[m]["details"][qid]["execution_correct"]
                        for m in ("single", "agentic")
                    ],
                ]
                exact_rows.append(
                    f'<tr><th><a href="{question_page}">{escape(record["nl_question"])}</a><br><small>{qid}</small></th>'
                    + "".join(
                        f"<td>{'Match' if verdict else 'No match'}</td>"
                        for verdict in exact_verdicts
                    )
                    + "</tr>"
                )
        configs = {
            "ANA": {
                k: manifest.get(k)
                for k in ("run_id", "max_tokens", "max_steps", "concurrency", "graph_sha256")
            },
            **{
                m: {
                    k: b["config"].get(k)
                    for k in (
                        "max_tokens",
                        "concurrency",
                        "graph_variant",
                        "judge_mode",
                        "reasoning_enabled",
                        "reasoning_effort",
                    )
                }
                for m, b in matching.items()
            },
        }
        content = (
            '<p><a href="comparison.html">← All comparisons</a></p><h2>Configuration differences</h2><pre>'
            + escape(json.dumps(configs, indent=2))
            + "</pre><p>No inference or judging is performed by this website. Repeated ANA runs are shown separately against the same baseline runs.</p>"
        )
        content += "".join(
            f'<p>{mode}: <a href="{b["source"]}">Pinned run manifest</a></p>'
            for mode, b in matching.items()
        )
        if has_execution:
            content += (
                "<h2>Common exact-result metric</h2><p>Saved baseline Cypher re-executed on the content-verified ANA graph; ANA uses archived returned rows. Open a question to inspect returned rows and errors.</p>"
                + table(exact_rows, "Question / QID", exact=True)
            )
        content += "<h2>Original source metrics</h2>" + table(rows, "Question / QID")
        (output / profile_page).write_text(page(root, title, content), encoding="utf-8")
    if evaluation:
        provenance["execution_evaluation"] = config["execution_evaluation"]
        provenance["execution_manifest_sha256"] = hashlib.sha256(
            (root / config["execution_evaluation"] / "manifest.json").read_bytes()
        ).hexdigest()
        write_json(
            output / "data/comparison/execution-manifest.json",
            json.loads((root / config["execution_evaluation"] / "manifest.json").read_text()),
        )
    write_json(output / "data/comparison/provenance.json", provenance)
    content = f'<p>Source branch: <code>{escape(config["branch"])}</code>, pinned commit <a href="https://github.com/{config["repository"]}/commit/{commit}"><code>{commit}</code></a>. The comparison uses exactly the pinned 100 Company QIDs, not the first 100 current task rows.</p>'
    content += "<p>Only matching model, temperature and requested reasoning profiles are paired. Single denotes the reference repository’s direct text-to-Cypher pipeline (including its interpreter), not necessarily one LLM call.</p>"
    if evaluation:
        content += f"<h2>Common exact-result metric</h2><p>Baseline queries were re-executed without LLM calls on a graph verified property-by-property against the ANA dataset. {evaluation['gold']['correct']}/100 golden queries reproduce the benchmark answers. Row order is ignored; duplicates and column order are preserved. Errors count as non-matches. This measures query-result correctness, not the quality of the final textual answer.</p>"
        content += table(exact_overview, "ANA run / matched profile", exact=True)
        content += (
            "<p>All 100 questions remain included. TODO: investigate golden-answer discrepancies for QIDs <code>"
            + escape(", ".join(evaluation["gold"]["non_reproduced_qids"]) or "none")
            + "</code>. No question is excluded from these tables.</p>"
        )
        content += '<p><a href="data/comparison/execution-manifest.json">Download execution protocol, graph fingerprints and scores</a></p>'
    content += "<h2>Original source metrics (different evaluators)</h2>" + table(
        overview, "ANA run / matched profile"
    )
    if unavailable:
        content += (
            "<h2>Comparisons not yet available</h2><p>These runs remain available in the ANA results section.</p><ul>"
            + "".join(unavailable)
            + "</ul>"
        )
    content += '<h2>Interpretation limits</h2><p>The original external metric evaluates textual answers with an LLM judge. Any separately labelled re-execution metric evaluates saved Cypher results instead. Historical query-generation conditions, schema prompts and token budgets still differ: this is not a controlled causal estimate of method improvement.</p><p>External call logs undercount some evaluator calls. We display logged calls only, separately from ANA runner counters; judge calls are separate. Missing reasoning or messages are not reconstructed.</p><p><a href="data/comparison/provenance.json">Download source revision, QID hash and artifact checksums</a></p>'
    (output / "comparison.html").write_text(
        page(root, "ANA and text-to-Cypher", content), encoding="utf-8"
    )


def table(rows: list[str], first: str, exact: bool = False) -> str:
    metric = "re-executed exact match" if exact else "source judge"
    return (
        '<div class="results-table"><table><thead><tr><th>'
        + first
        + f"</th><th>ANA · exact answer match</th><th>Direct Cypher · {metric}</th><th>Multi-agent · {metric}</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )
