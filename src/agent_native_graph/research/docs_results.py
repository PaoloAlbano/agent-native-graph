"""Publish read-only, validated projections of archived Company runs for the site."""

import hashlib
import json
import re
from html import escape
from pathlib import Path
from typing import Any

ARCHIVE = Path("results/cypherbench-company/full/runs")
PUBLIC_CONFIG = (
    "run_id",
    "model",
    "temperature",
    "reasoning",
    "created_at",
    "git_commit",
    "run_sha256",
    "tasks_sha256",
    "graph_sha256",
    "concurrency",
    "max_steps",
    "max_tokens",
    "tool_choice",
    "tool_mode",
    "approach",
    "benchmark",
    "category",
    "split",
)


def read_runs(root: Path) -> list[dict[str, Any]]:
    """Reject incomplete, inconsistent or corrupted evidence rather than publishing it."""
    runs = []
    reference = None
    for folder in sorted((root / ARCHIVE).iterdir()):
        if not folder.is_dir():
            continue
        manifest = json.loads((folder / "manifest.json").read_text())
        summary = json.loads((folder / "summary.json").read_text())
        payload = (folder / "run.jsonl").read_bytes()
        if hashlib.sha256(payload).hexdigest() != manifest["run_sha256"]:
            raise ValueError(f"Checksum mismatch: {folder.name}")
        records = [json.loads(line) for line in payload.splitlines() if line.strip()]
        questions = {r["qid"]: (r["nl_question"], r["gold_cypher"], r["expected"]) for r in records}
        if len(records) != 347 or len(questions) != 347:
            raise ValueError(f"Expected 347 unique Company questions: {folder.name}")
        if manifest["category"] != "company" or manifest["suite"] != "full":
            raise ValueError(f"Not a full Company run: {folder.name}")
        if manifest["run_id"] != folder.name or summary["run_id"] != folder.name:
            raise ValueError(f"Run identity mismatch: {folder.name}")
        if reference is not None and questions != reference:
            raise ValueError(f"Question/gold mismatch across runs: {folder.name}")
        reference = questions
        counts = {
            "total": len(records),
            "matches": sum(r["matches_answer_json"] is True for r in records),
            "ok": sum(r["ok"] is True for r in records),
        }
        for key, value in counts.items():
            if summary[key] != value:
                raise ValueError(f"Summary {key} mismatch: {folder.name}")
        for key, field in (
            ("avg_llm_calls", "llm_call_count"),
            ("avg_tool_calls", "tool_call_count"),
        ):
            actual = sum(r[field] for r in records) / len(records)
            if abs(summary[key] - actual) > 1e-9:
                raise ValueError(f"Summary {key} mismatch: {folder.name}")
        if abs(summary["accuracy"] - counts["matches"] / len(records)) > 1e-9:
            raise ValueError(f"Summary accuracy mismatch: {folder.name}")
        runs.append({"manifest": manifest, "summary": summary, "records": records})
    if not runs:
        raise ValueError("No complete Company runs found")
    return runs


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )


def render_page(
    template: str,
    *,
    heading: str,
    rows: str,
    navigation: str,
    run_index: str = "",
    explorer: str = "",
) -> str:
    """Only a dedicated run page receives the explorer scripts and data URL."""
    values = {
        "HEADING": escape(heading),
        "RUN_ROWS": rows,
        "MODEL_NAV": navigation,
        "RUN_INDEX": run_index,
        "EXPLORER": explorer,
        "SCRIPTS": (
            '<script defer src="assets/results-ui.js"></script>'
            '<script defer src="assets/results.js"></script>'
        )
        if run_index
        else "",
    }
    return re.sub(r"@@([A-Z_]+)@@", lambda match: values[match[1]], template)


def publish_results(root: Path, output: Path, repository_url: str) -> str:
    """Generate compact indices and lazy-loaded records; never write to results/."""
    runs = read_runs(root)
    template = (root / "docs/site/results.template.html").read_text()
    explorer = (root / "docs/site/run-explorer.html").read_text()
    index = {"runs": []}
    model_rows: dict[str, list[str]] = {}
    for run in runs:
        manifest, summary = run["manifest"], run["summary"]
        run_id = manifest["run_id"]
        # Content-derived paths are safe even if archive IDs contain punctuation.
        key = hashlib.sha256(run_id.encode()).hexdigest()[:16]
        questions = []
        for record in sorted(run["records"], key=lambda item: item["qid"]):
            record_key = hashlib.sha256(record["qid"].encode()).hexdigest()[:16]
            path = f"data/results/{key}/{record_key}.json"
            write_json(output / path, record)
            questions.append(
                {
                    field: record.get(field)
                    for field in (
                        "qid",
                        "nl_question",
                        "ok",
                        "matches_answer_json",
                        "failure_class",
                        "llm_call_count",
                        "tool_call_count",
                        "tool_error_count",
                        "elapsed_s",
                    )
                }
                | {"detail": path}
            )
        source = f"{repository_url}/tree/main/{ARCHIVE.as_posix()}/{run_id}"
        run_page = f"run-{key}.html"
        question_index = f"data/results/{key}/index.json"
        entry = {
            "config": {k: manifest[k] for k in PUBLIC_CONFIG if k in manifest},
            "summary": summary,
            "source": source,
            "page": run_page,
            "question_index": question_index,
        }
        index["runs"].append(entry)
        write_json(output / question_index, entry | {"questions": questions})
        label = (
            f"{manifest['model']} · Temperature {manifest['temperature']:g} · "
            f"Reasoning {manifest['reasoning']} · {manifest['created_at'][:19]}"
        )
        model = manifest["model"]
        model_page = f"model-{hashlib.sha256(model.encode()).hexdigest()[:16]}.html"
        row = (
            f'<tr><th scope="row"><a href="{run_page}">{escape(label)}</a>'
            '<br><span class="small-text">Explore all 347 questions</span>'
            f"<details><summary>Run ID</summary><code>{escape(run_id)}</code></details></th>"
            f"<td>{manifest['temperature']:g}</td><td>{escape(manifest['reasoning'])}</td>"
            f"<td>{summary['matches']}/347 <strong>({summary['matches'] / 347:.1%})</strong></td>"
            f"<td>{summary['ok']}/347</td><td>{347 - summary['ok']}</td>"
            f"<td>{summary['avg_llm_calls']:.2f}</td><td>{summary['avg_tool_calls']:.2f}</td></tr>"
        )
        model_rows.setdefault(model, []).append(row)
        navigation = (
            '<p><a href="results.html">All models</a> / '
            f'<a href="{model_page}">{escape(model)}</a> / This run</p>'
            f'<p class="run-label">Temperature {manifest["temperature"]:g} · '
            f"Reasoning {escape(manifest['reasoning'])} · {escape(manifest['created_at'])}</p>"
        )
        (output / run_page).write_text(
            render_page(
                template,
                heading=f"{model} — run analysis",
                rows=row,
                navigation=navigation,
                run_index=question_index,
                explorer=explorer,
            ),
            encoding="utf-8",
        )
    write_json(output / "data/results/index.json", index)
    cards = []
    grouped_rows = []
    for model, rows in sorted(model_rows.items()):
        model_page = f"model-{hashlib.sha256(model.encode()).hexdigest()[:16]}.html"
        configurations = "".join(
            "<li>"
            f"Temperature {run['manifest']['temperature']:g} · "
            f"Reasoning {escape(run['manifest']['reasoning'])} · "
            f"{escape(run['manifest']['created_at'][:19])}</li>"
            for run in runs
            if run["manifest"]["model"] == model
        )
        cards.append(
            '<article class="model-card">'
            f'<p class="eyebrow">{len(rows)} complete runs · Company</p>'
            f'<h3><a href="{model_page}">{escape(model)}</a></h3>'
            "<p>347 questions per run. Inspect answers, failures and every recorded tool call.</p>"
            f'<ul class="model-configurations">{configurations}</ul>'
            f'<a href="{model_page}">Explore this model →</a></article>'
        )
        grouped_rows.append(
            f'<tr class="model-group"><th colspan="8"><a href="{model_page}">{escape(model)}</a></th></tr>'
            + "".join(rows)
        )
        model_html = render_page(
            template,
            rows="".join(rows),
            navigation='<p><a href="results.html">← All models</a></p>',
            heading=model,
        )
        (output / model_page).write_text(model_html, encoding="utf-8")
    page = render_page(
        template,
        rows="".join(grouped_rows),
        navigation='<div class="model-grid">' + "".join(cards) + "</div>",
        heading="Company, in full.",
    )
    (output / "results.html").write_text(page, encoding="utf-8")
    return page
