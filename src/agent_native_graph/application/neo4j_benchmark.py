import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_native_graph.application.agent_loop import (
    _benchmark_fetch_preview,
    _evaluation_fetch_all_pages,
    _guarded_action,
    _latest_fetchable_handle,
    _next_action,
)
from agent_native_graph.application.metrics import (
    _summarize_llm_metrics,
    _summarize_tool_metrics,
    _update_summary,
    classify_failure,
)
from agent_native_graph.application.result_policy import (
    collect_handle,
    completeness,
)
from agent_native_graph.application.result_policy import (
    result_policy as get_result_policy,
)
from agent_native_graph.application.run_config import (
    apply_profile,
    config_path,
    llm_settings_for_run,
    new_output,
    profile_names,
    result_signature,
    run_lock,
    save_config,
    task_signature,
)
from agent_native_graph.core.graph_utils import _requires_wrapper_planning
from agent_native_graph.core.tool_specs import SCHEMA_ENTRY_MODES
from agent_native_graph.llm_providers.accounting import RequestAccounting, account_requests
from agent_native_graph.llm_providers.execution import Deadline, TaskTimeoutError, deadline_scope
from agent_native_graph.research_common import (
    ChatClient,
    add_llm_args,
    add_neo4j_args,
    append_jsonl,
    completed_qids,
    limited_tasks,
    normalize_answer_rows,
    parse_answer_json,
    read_jsonl,
    result_matches_answer,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    add_neo4j_args(parser)
    add_llm_args(parser)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--schema-json", type=Path, required=True)
    parser.add_argument(
        "--shared-preflight",
        action="store_true",
        help="Verify the full graph and use the canonical live schema shared with baselines; new treatment",
    )
    parser.add_argument(
        "--database", help="Explicit database for --shared-preflight; defaults to neo4j"
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Existing path only with --resume; otherwise generated automatically",
    )
    parser.add_argument("--run-dir", type=Path, default=Path("/tmp/agent-native-graph-runs"))
    parser.add_argument(
        "--profile",
        choices=profile_names(),
        help="Name of a YAML file in agent_native_graph/profiles",
    )
    parser.add_argument("--provider-tag", default="openai-compatible")
    parser.add_argument("--graph-file", type=Path, default=Path("downloads/company_simplekg.json"))
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate inputs/save metadata, without Neo4j or LLM calls",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--task-timeout-s", type=int)
    parser.add_argument("--neo4j-query-timeout-s", type=int, default=30)
    parser.add_argument("--native-tools", action="store_true")
    parser.add_argument(
        "--tool-choice",
        choices=["auto", "required", "none"],
        default="auto",
        help=(
            "Native tool-call selection policy. Use auto for realistic agent runs; "
            "required forces a tool call but can make some providers generate very "
            "long pre-tool responses."
        ),
    )
    parser.add_argument("--enable-planning-tools", action="store_true")
    parser.add_argument("--wrapper-planning", action="store_true")
    parser.add_argument("--auto-fetch-on-done", action="store_true")
    parser.add_argument("--result-policy", choices=("bounded-v1",))
    parser.add_argument("--verify-graph-block", action="store_true")
    parser.add_argument(
        "--evaluation-fetch-all-pages",
        action="store_true",
        help=(
            "Benchmark-only mode: when the model fetches a paginated final handle, "
            "retrieve all rows for answer comparison. Keep disabled for agent-safe "
            "runtime behavior."
        ),
    )
    parser.add_argument(
        "--schema-entry",
        choices=SCHEMA_ENTRY_MODES,
        default="overview",
        help=(
            "Schema discovery profile for native tool runs. overview is the "
            "current full first call, overview_light returns a smaller first "
            "payload, targeted_first hides schema_overview and starts from "
            "schema_search, overview_expand_first keeps schema_overview but "
            "hides pattern_query to favor composable expand/project flows, "
            "overview_light_expand_first combines the smaller overview with "
            "the expand-first tool surface."
        ),
    )
    parser.add_argument(
        "--enable-runner-guardrails",
        action="store_true",
        help=(
            "Enable local runner interventions that can replace unsafe model "
            "tool calls. Keep disabled for clean tool-call quality benchmarks."
        ),
    )
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.verify_graph_block and (not args.shared_preflight or args.resume or args.check_only):
        parser.error(
            "--verify-graph-block requires --shared-preflight and does not support --resume/--check-only"
        )
    if args.database is not None and not args.shared_preflight:
        parser.error(
            "--database requires --shared-preflight; legacy database behavior is unchanged"
        )
    if args.shared_preflight and args.check_only:
        parser.error("--shared-preflight needs live graph verification; omit --check-only")
    apply_profile(args)
    if args.concurrency < 1:
        parser.error("--concurrency must be positive")
    if args.task_timeout_s is not None and args.task_timeout_s <= 0:
        parser.error("--task-timeout-s must be positive")
    if args.resume and args.out is None:
        parser.error("--resume requires the original --out path")
    args.out = args.out or new_output(args.run_dir, args.model, args.profile)
    _log(f"OUTPUT {args.out}")
    with run_lock(args.out):
        if (args.out.exists() or config_path(args.out).exists()) and not args.resume:
            raise ValueError("Output already exists; choose a new path or use --resume")
        tasks = limited_tasks(read_jsonl(args.tasks), args.limit)
        schema = json.loads(args.schema_json.read_text(encoding="utf-8"))
        if args.shared_preflight:
            args.shared_preflight_artifact = _prepare_shared_preflight(args)
            schema = args.shared_preflight_artifact["schema"]
        save_config(args, tasks, Path.cwd())
        if args.resume and args.out.exists():
            previous = read_jsonl(args.out)
            selected = {t["qid"]: t for t in tasks}
            qids = [r["qid"] for r in previous]
            if len(set(qids)) != len(qids) or not set(qids) <= selected.keys():
                raise ValueError("Cannot resume results with duplicate or foreign QIDs")
            if task_signature([selected[qid] for qid in qids]) != result_signature(previous):
                raise ValueError("Cannot resume results with different task contents")
        if args.check_only:
            print(json.dumps({"checked": str(args.out), "inference_started": False}))
            return
        if args.profile and not args.shared_preflight:
            _verify_graph(args)
        block = None
        if args.verify_graph_block:
            from agent_native_graph.research.graph_integrity import GraphBlock

            block = GraphBlock(
                args.out,
                config_path(args.out),
                args.graph_file,
                args.shared_preflight_artifact,
                [t["qid"] for t in tasks],
            )
            block.start()
        failed = True
        try:
            _execute(args, tasks, schema)
            failed = False
        finally:
            if block is not None:
                _finish_graph_block(args, block, failed)


def _finish_graph_block(args, block, failed):
    """Postcheck after worker shutdown; never mask a primary benchmark exception."""
    from neo4j import GraphDatabase

    from agent_native_graph.research.common_preflight import graph_snapshot
    from agent_native_graph.research.graph_integrity import GraphIntegrityError

    after, failure = None, None
    try:
        with GraphDatabase.driver(
            args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password)
        ) as driver:
            after = graph_snapshot(driver, block.database)
    except Exception as exc:
        failure = type(exc).__name__
    try:
        report = block.finish(after, run_failed=failed, postcheck_error=failure)
        if not failed and report["status"] != "verified":
            raise GraphIntegrityError("Graph block is not verified; inspect the integrity sidecar")
    except Exception:
        if not failed:
            raise


def _prepare_shared_preflight(args):
    """Opt-in only: the same verified graph and canonical schema as the baselines."""
    from neo4j import GraphDatabase

    from agent_native_graph.research.common_preflight import prepare_preflight

    with GraphDatabase.driver(
        args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password)
    ) as driver:
        return prepare_preflight(driver, args.database or "neo4j", args.graph_file)


def _verify_graph(args) -> None:
    from neo4j import GraphDatabase

    from agent_native_graph.research.reexecute_reference import database_snapshot, expected_snapshot

    expected = expected_snapshot(args.graph_file)
    with GraphDatabase.driver(
        args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password)
    ) as driver:
        if database_snapshot(driver, "neo4j") != expected:
            raise ValueError("Neo4j content differs from the Company graph; no inference started")


def _execute(args, tasks: list[dict], schema: dict) -> None:
    done_qids = completed_qids(args.out) if args.resume else set()
    llm = ChatClient(
        base_url=args.base_url,
        model=args.model,
        api_key_env=args.api_key_env,
        api_key_file=args.api_key_file,
        settings=llm_settings_for_run(args),
    )

    summary = {
        "total": 0,
        "tool_success": 0,
        "matches_answer_json": 0,
        "tool_calls": 0,
        "llm_calls": 0,
    }
    pending_tasks = []
    for task in tasks:
        if task["qid"] in done_qids:
            _log(f"SKIP  {task['qid']} (already done)")
        else:
            pending_tasks.append(task)

    common_kwargs = {
        "llm": llm,
        "schema": schema,
        "neo4j_uri": args.neo4j_uri,
        "neo4j_user": args.neo4j_user,
        "neo4j_password": args.neo4j_password,
        "neo4j_query_timeout_s": args.neo4j_query_timeout_s,
        "max_steps": args.max_steps,
        "native_tools": args.native_tools,
        "tool_choice": args.tool_choice,
        "enable_planning_tools": args.enable_planning_tools,
        "schema_entry": args.schema_entry,
        "wrapper_planning": args.wrapper_planning,
        "auto_fetch_on_done": args.auto_fetch_on_done,
        "evaluation_fetch_all_pages": args.evaluation_fetch_all_pages,
        "enable_runner_guardrails": args.enable_runner_guardrails,
        "task_timeout_s": args.task_timeout_s,
        "result_policy": getattr(args, "result_policy", None),
    }
    shared = getattr(args, "shared_preflight_artifact", None)
    if shared is not None:
        common_kwargs.update(schema_bootstrap=shared["schema_prompt"], database=shared["database"])
    if args.concurrency <= 1:
        for task in pending_tasks:
            row = _run_agent_task(task, **common_kwargs)
            append_jsonl(args.out, row)
            _update_summary(summary, row)
    else:
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = [
                executor.submit(_run_agent_task, task, **common_kwargs) for task in pending_tasks
            ]
            for future in as_completed(futures):
                row = future.result()
                append_jsonl(args.out, row)
                _update_summary(summary, row)
    if summary["total"]:
        summary["avg_tool_calls"] = summary["tool_calls"] / summary["total"]
        summary["avg_llm_calls"] = summary["llm_calls"] / summary["total"]
    print(json.dumps(summary, sort_keys=True))


def _run_agent_task(
    task: dict[str, Any],
    *,
    llm: ChatClient,
    schema: dict[str, Any],
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    neo4j_query_timeout_s: int | None,
    max_steps: int,
    native_tools: bool,
    tool_choice: str,
    enable_planning_tools: bool,
    schema_entry: str,
    wrapper_planning: bool,
    auto_fetch_on_done: bool,
    evaluation_fetch_all_pages: bool,
    enable_runner_guardrails: bool,
    task_timeout_s: int | None,
    schema_bootstrap: str | None = None,
    database: str | None = None,
    result_policy: str | None = None,
) -> dict[str, Any]:
    from agent_native_graph.backends.neo4j.backend import Neo4jGraphBackend

    _log(f"START {task['qid']} | {task['nl_question'][:80]}")
    deadline = Deadline(task_timeout_s)
    backend = Neo4jGraphBackend(
        neo4j_uri,
        neo4j_user,
        neo4j_password,
        schema,
        query_timeout_s=neo4j_query_timeout_s,
        schema_entry=schema_entry,
        **({"database": database} if database is not None else {}),
    )
    started = time.perf_counter()
    transcript: list[dict[str, Any]] = []
    llm_call_metrics: list[dict[str, Any]] = []
    error: str | None = None
    llm_call_count = 0
    accounting = RequestAccounting()
    policy = get_result_policy(result_policy)
    final_coverage = None
    planning_required = wrapper_planning and _requires_wrapper_planning(schema, task["nl_question"])
    planning_injected = False

    def call_tool(tool, args):
        nonlocal final_coverage
        deadline.remaining()
        effective = dict(args)
        if policy and tool == "fetch" and type(effective.get("limit")) is int:
            effective["limit"] = min(effective["limit"], policy.max_rows)
        result = backend.call(tool, effective)
        if tool == "fetch" and policy:
            final_coverage = None
            try:
                result = collect_handle(backend, {"args": args}, result, policy)
            except Exception as exc:
                final_coverage = completeness(
                    policy,
                    scope="stored_handle",
                    available=result.get("total_count"),
                    collected=0,
                    preview=0,
                    complete=False,
                    error=str(exc),
                )
                raise
            final_coverage = result["result_completeness"]
        deadline.remaining()
        return result

    try:
        for step_i in range(max_steps):
            deadline.remaining()
            llm_call_count += 1
            _log(f"  LLM call {llm_call_count} (step {step_i + 1}/{max_steps})")
            with (
                account_requests(accounting, role="agent"),
                deadline_scope(deadline if task_timeout_s is not None else None),
            ):
                bootstrap_options = (
                    {"schema_bootstrap": schema_bootstrap} if schema_bootstrap is not None else {}
                )
                action = _next_action(
                    llm,
                    task["nl_question"],
                    transcript,
                    native_tools=native_tools,
                    tool_choice=tool_choice,
                    enable_planning_tools=enable_planning_tools,
                    schema_entry=schema_entry,
                    enable_runner_guardrails=enable_runner_guardrails,
                    **bootstrap_options,
                )
            deadline.remaining()
            llm_meta = action.pop("_llm_meta", None)
            if isinstance(llm_meta, dict):
                llm_call_metrics.append(llm_meta)
            if enable_runner_guardrails:
                action = _guarded_action(task["nl_question"], transcript, action)
            tool = action.get("tool")
            _log(
                f"  -> tool={tool} args="
                f"{json.dumps(action.get('args') or {}, ensure_ascii=False)[:120]}"
            )
            if tool == "done":
                if policy is not None:
                    transcript.append(
                        {
                            "action": action,
                            "result": {
                                "status": "tool_error",
                                "error": "done_disabled: bounded-v1 requires an explicit fetch tool call.",
                            },
                        }
                    )
                    continue
                if backend.last_fetch is None:
                    handle = _latest_fetchable_handle(transcript)
                    if handle is not None:
                        fetch_action = {
                            "tool": "fetch",
                            "args": {"from": handle, "limit": 1000},
                            "auto": True,
                        }
                        _log(f"  -> auto tool=fetch args={{'from': '{handle}'}}")
                        try:
                            result = call_tool("fetch", dict(fetch_action["args"]))
                            if evaluation_fetch_all_pages and policy is None:
                                result = _evaluation_fetch_all_pages(
                                    backend,
                                    fetch_action,
                                    result,
                                )
                            result = _benchmark_fetch_preview(result)
                            deadline.remaining()
                            transcript.append({"action": fetch_action, "result": result})
                            _log("     auto ok matched=None")
                            break
                        except TaskTimeoutError:
                            raise
                        except Exception as tool_exc:
                            result = {
                                "status": "tool_error",
                                "error": f"{tool_exc.__class__.__name__}: {tool_exc}",
                            }
                            transcript.append({"action": fetch_action, "result": result})
                            _log(f"     auto error: {tool_exc.__class__.__name__}: {tool_exc}")
                        continue
                    result = {
                        "status": "tool_error",
                        "error": "done_disabled: fetch is the only supported finalization action, and no fetchable handle is available yet.",
                    }
                    transcript.append({"action": action, "result": result})
                    _log("     error: done_disabled_no_handle")
                    continue
                break
            try:
                result = call_tool(str(tool), dict(action.get("args") or {}))
                if tool == "fetch":
                    if evaluation_fetch_all_pages and policy is None:
                        result = _evaluation_fetch_all_pages(backend, action, result)
                    result = _benchmark_fetch_preview(result)
                deadline.remaining()
                matched = result.get("matched_count") if isinstance(result, dict) else None
                _log(f"     ok matched={matched}")
            except TaskTimeoutError:
                raise
            except Exception as tool_exc:
                _log(f"     error: {tool_exc.__class__.__name__}: {tool_exc}")
                result = {
                    "status": "tool_error",
                    "error": f"{tool_exc.__class__.__name__}: {tool_exc}",
                }
                transcript.append({"action": action, "result": result})
                continue
            transcript.append({"action": action, "result": result})
            if (
                native_tools
                and planning_required
                and not planning_injected
                and tool == "schema_inspect"
            ):
                plan_action = {
                    "tool": "draft_tool_plan",
                    "args": {"question": task["nl_question"], "max_steps": 6},
                    "auto": True,
                }
                _log("  -> auto tool=draft_tool_plan args={...}")
                try:
                    plan_result = call_tool("draft_tool_plan", dict(plan_action["args"]))
                    _log("     auto ok matched=None")
                except TaskTimeoutError:
                    raise
                except Exception as tool_exc:
                    _log(f"     auto error: {tool_exc.__class__.__name__}: {tool_exc}")
                    plan_result = {
                        "status": "tool_error",
                        "error": f"{tool_exc.__class__.__name__}: {tool_exc}",
                    }
                transcript.append({"action": plan_action, "result": plan_result})
                planning_injected = True
            if tool == "fetch":
                break
            if (
                policy is None
                and auto_fetch_on_done
                and step_i == max_steps - 1
                and backend.last_fetch is None
            ):
                handle = _latest_fetchable_handle(transcript)
                if handle is not None:
                    fetch_action = {
                        "tool": "fetch",
                        "args": {"from": handle, "limit": 1000},
                        "auto": True,
                        "reason": "max_steps_auto_fetch",
                    }
                    _log(f"  -> auto tool=fetch args={{'from': '{handle}'}} reason=max_steps")
                    try:
                        fetch_result = call_tool("fetch", dict(fetch_action["args"]))
                        if evaluation_fetch_all_pages and policy is None:
                            fetch_result = _evaluation_fetch_all_pages(
                                backend,
                                fetch_action,
                                fetch_result,
                            )
                        fetch_result = _benchmark_fetch_preview(fetch_result)
                        deadline.remaining()
                        _log("     auto ok matched=None")
                    except TaskTimeoutError:
                        raise
                    except Exception as tool_exc:
                        _log(f"     auto error: {tool_exc.__class__.__name__}: {tool_exc}")
                        fetch_result = {
                            "status": "tool_error",
                            "error": f"{tool_exc.__class__.__name__}: {tool_exc}",
                        }
                    transcript.append({"action": fetch_action, "result": fetch_result})
                    break
    except Exception as exc:
        error = f"{exc.__class__.__name__}: {exc}"
        _log(f"  EXCEPTION: {error}")
    finally:
        backend.close()

    expected = normalize_answer_rows(parse_answer_json(task.get("answer_json")))
    actual = backend.last_fetch or []
    matches = error is None and result_matches_answer(actual, expected)
    tool_call_count = len(transcript)
    tool_error_count = sum(
        1 for step in transcript if step.get("result", {}).get("status") == "tool_error"
    )
    llm_metric_summary = _summarize_llm_metrics(llm_call_metrics)
    tool_metric_summary = _summarize_tool_metrics(transcript)
    elapsed = time.perf_counter() - started
    ok = error is None and backend.last_fetch is not None
    if policy:
        final_coverage = final_coverage or completeness(
            policy,
            scope="stored_handle",
            available=None,
            collected=0,
            preview=0,
            complete=False,
            error=error or "no_final_fetch",
        )
        ok = ok and final_coverage["complete"]
        matches = ok and matches
    _log(
        f"END   {task['qid']} | ok={ok} "
        f"match={matches} tools={tool_call_count} errors={tool_error_count} "
        f"elapsed={elapsed:.1f}s"
    )
    row = {
        "qid": task["qid"],
        "approach": "agent_tools_neo4j",
        "nl_question": task["nl_question"],
        "gold_cypher": task["gold_cypher"],
        "transcript": transcript,
        "rows": actual,
        "expected": expected,
        "ok": ok,
        "matches_answer_json": matches,
        "tool_call_count": tool_call_count,
        "tool_error_count": tool_error_count,
        "llm_call_count": llm_call_count,
        "llm_call_metrics": llm_call_metrics,
        "llm_metric_summary": llm_metric_summary,
        "request_accounting": accounting.snapshot(),
        "tool_metric_summary": tool_metric_summary,
        "elapsed_s": elapsed,
        "error": error,
    }
    row["failure_class"] = classify_failure(row)
    if policy:
        row["result_completeness"] = final_coverage
    return row


def _log(message: str) -> None:
    timestamp = datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", file=sys.stderr, flush=True)
