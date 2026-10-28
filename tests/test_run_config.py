import argparse
import json
from unittest.mock import patch

import httpx
import pytest

from agent_native_graph.application import neo4j_benchmark, run_config
from agent_native_graph.core.tool_specs import _tool_specs
from agent_native_graph.llm_providers import openai_compatible
from agent_native_graph.llm_providers.openai_compatible import chat_completions_url
from agent_native_graph.research import archive_result
from agent_native_graph.research.docs_results import read_runs

SHIPPED_PROFILE_DIR = run_config.PROFILE_DIR


def test_requested_task_timeout_is_saved_with_concurrency_above_one(experiment):
    root, args, tasks = experiment
    args.profile = None
    args.task_timeout_s = 15
    config = run_config.save_config(args, tasks, root)
    assert config["task_timeout_s"] == 15 and config["concurrency"] == 3


@pytest.fixture
def experiment(tmp_path, monkeypatch):
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "temp0-none.yaml").write_text(
        "temperature: 0.0\nenable_thinking: false\nthinking_effort: null\n"
    )
    (profiles / "temp1-medium.yaml").write_text(
        "temperature: 1.0\nenable_thinking: true\nthinking_effort: medium\n"
    )
    monkeypatch.setattr(run_config, "PROFILE_DIR", profiles)
    source = tmp_path / "src/agent_native_graph"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("# fixture")
    for name in ("uv.lock", "pyproject.toml"):
        (tmp_path / name).write_text("fixture")
    tasks = [
        {
            "qid": str(i),
            "graph": "company",
            "nl_question": "Q",
            "gold_cypher": "RETURN 1",
            "answer_json": "[[1]]",
        }
        for i in range(347)
    ]
    tasks_file = tmp_path / "tasks.jsonl"
    tasks_file.write_text("".join(json.dumps(t) + "\n" for t in tasks))
    for name in ("schema.json", "graph.json"):
        (tmp_path / name).write_text("{}")
    args = argparse.Namespace(
        out=tmp_path / "run.jsonl",
        tasks=tasks_file,
        schema_json=tmp_path / "schema.json",
        graph_file=tmp_path / "graph.json",
        resume=False,
        profile="temp0-none",
        model="test/model",
        provider_tag="test",
        limit=347,
        max_tokens=16000,
        max_steps=12,
        concurrency=3,
        tool_choice="auto",
        schema_entry="overview",
        enable_planning_tools=False,
        wrapper_planning=False,
        auto_fetch_on_done=False,
        evaluation_fetch_all_pages=False,
        enable_runner_guardrails=False,
        native_tools=False,
        neo4j_query_timeout_s=30,
        task_timeout_s=None,
        base_url="https://example.invalid",
        neo4j_uri="bolt://localhost:7687",
    )
    run_config.apply_profile(args)
    return tmp_path, args, tasks


def results(tasks):
    return [
        {
            "qid": t["qid"],
            "nl_question": t["nl_question"],
            "gold_cypher": t["gold_cypher"],
            "expected": [[1]],
            "rows": [[1]],
            "ok": True,
            "matches_answer_json": True,
            "llm_call_count": 1,
            "tool_call_count": 1,
        }
        for t in tasks
    ]


@pytest.mark.parametrize(
    "name,temperature,thinking,effort",
    [
        ("temp0-none", 0.0, False, None),
        ("temp0-medium", 0.0, True, "medium"),
        ("temp1-none", 1.0, False, None),
        ("temp1-medium", 1.0, True, "medium"),
    ],
)
def test_shipped_profile_matrix(name, temperature, thinking, effort):
    settings, checksum = run_config.load_profile(name)
    assert (settings["temperature"], settings["enable_thinking"], settings["thinking_effort"]) == (
        temperature,
        thinking,
        effort,
    )
    assert settings["max_tokens"] == 16000 and settings["tool_choice"] == "auto"
    assert len(checksum) == 64


def test_matrix_varies_only_temperature_and_thinking():
    names = ("temp0-none", "temp0-medium", "temp1-none", "temp1-medium")
    common = [
        {
            k: v
            for k, v in run_config.load_profile(name)[0].items()
            if k not in {"temperature", "enable_thinking", "thinking_effort"}
        }
        for name in names
    ]
    assert all(settings == common[0] for settings in common)


@pytest.mark.parametrize("name", ["temp0-none", "temp0-medium", "temp1-none", "temp1-medium"])
def test_profile_matrix_reaches_http_metadata_archive_and_site(experiment, monkeypatch, name):
    root, args, tasks = experiment
    monkeypatch.setattr(run_config, "PROFILE_DIR", SHIPPED_PROFILE_DIR)
    expected, checksum = run_config.load_profile(name)
    monkeypatch.chdir(root)
    monkeypatch.setenv("ANA_TEST_KEY", "test-only-key")
    specs = _tool_specs(enable_planning_tools=False)
    requests, timeouts = [], []
    client_type = httpx.Client

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "test-call",
                                    "type": "function",
                                    "function": {
                                        "name": "fetch",
                                        "arguments": '{"from":"h1"}',
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            },
        )

    def client(**kwargs):
        timeouts.append(kwargs["timeout"])
        return client_type(transport=httpx.MockTransport(respond))

    def synthetic_task(task, **kwargs):
        # Stub task reasoning and graph execution, not the runner/provider configuration.
        message = kwargs["llm"].chat(
            [{"role": "user", "content": task["nl_question"]}],
            tools=specs,
            tool_choice=kwargs["tool_choice"],
        )
        assert message["tool_calls"][0]["function"]["name"] == "fetch"
        row = results([task])[0]
        row["llm_call_metrics"] = [message["__chat_meta"]]
        return row

    monkeypatch.setattr(
        "sys.argv",
        [
            "runner",
            "--tasks",
            str(args.tasks),
            "--schema-json",
            str(args.schema_json),
            "--graph-file",
            str(args.graph_file),
            "--out",
            str(args.out),
            "--model",
            "test/model",
            "--base-url",
            "https://example.invalid/v1",
            "--api-key-env",
            "ANA_TEST_KEY",
            "--profile",
            name,
            "--concurrency",
            "1",
        ],
    )
    with (
        patch.object(neo4j_benchmark, "_verify_graph") as graph_check,
        patch.object(neo4j_benchmark, "_run_agent_task", side_effect=synthetic_task),
        patch.object(openai_compatible.httpx, "Client", side_effect=client),
    ):
        neo4j_benchmark.main()
    graph_check.assert_called_once()
    assert len(requests) == len(tasks) == 347
    assert timeouts == [expected["timeout_s"]] * len(tasks)
    for payload in requests:
        assert payload["tools"] == specs
        assert payload["model"] == "test/model"
        assert payload["temperature"] == expected["temperature"]
        assert payload["max_tokens"] == expected["max_tokens"] == 16000
        assert payload["tool_choice"] == expected["tool_choice"] == "auto"
        template = {"enable_thinking": expected["enable_thinking"]}
        if expected["enable_thinking"]:
            template["thinking_effort"] = "medium"
            assert payload["reasoning_effort"] == "medium"
        else:
            assert "reasoning_effort" not in payload
        assert payload["chat_template_kwargs"] == template
        assert not {"timeout_s", "max_attempts", "top_p", "seed", "stop"} & payload.keys()

    config = run_config.load_config(run_config.config_path(args.out))
    assert config["llm_settings"] == expected
    assert config["profile"] == name and config["profile_sha256"] == checksum
    assert config["identity"]["tools_sha256"] == run_config.digest(specs)
    monkeypatch.setattr("sys.argv", ["archive", "--run", str(args.out)])
    archive_result.main()
    archive = next((root / "results/cypherbench-company/full/runs").iterdir())
    assert {p.name for p in archive.iterdir()} == {
        "manifest.json",
        "run-config.json",
        "run.jsonl",
        "summary.json",
        "failures.jsonl",
    }
    public = json.loads((archive / "run-config.json").read_text())
    assert public["llm_settings"] == expected and public["profile_sha256"] == checksum
    for private in (str(root), "example.invalid", "test-only-key"):
        assert private not in json.dumps(public)
    archived = read_runs(root)[0]
    manifest, summary = archived["manifest"], archived["summary"]
    assert manifest["run_profile"] == name and manifest["profile_sha256"] == checksum
    assert manifest["temperature"] == expected["temperature"]
    assert manifest["reasoning"] == ("medium" if expected["enable_thinking"] else "none")
    assert summary["total"] == 347 and summary["llm_total_tokens"] == 347 * 3
    for row in archived["records"]:
        metric = row["llm_call_metrics"][0]
        assert metric["enable_thinking"] == expected["enable_thinking"]
        assert metric["thinking_effort"] == expected["thinking_effort"]
        assert metric["temperature"] == expected["temperature"]
        assert metric["max_tokens"] == expected["max_tokens"]
        assert metric["finish_reason"] == "tool_calls"
        assert metric["request_attempts"] == 1 and not metric["low_effort_retry"]
    assert (archive / "run.jsonl").read_bytes() == args.out.read_bytes()


def test_profile_is_applied_once_without_command_reconstruction(experiment):
    _, args, _ = experiment
    assert args.native_tools and args.evaluation_fetch_all_pages
    assert args.temperature == 0 and not args.enable_thinking
    args.profile = "temp1-medium"
    run_config.apply_profile(args)
    assert args.temperature == 1 and args.enable_thinking and args.thinking_effort == "medium"
    path = run_config.PROFILE_DIR / "temp1-medium.yaml"
    path.write_text(path.read_text() + "max_tokens: 32000\ntimeout_s: 120\nmax_attempts: 5\n")
    run_config.apply_profile(args)
    assert args.max_tokens == 32000 and args.llm_settings.timeout_s == 120
    assert args.llm_settings.max_attempts == 5
    args.max_steps = 8
    with pytest.raises(ValueError):
        run_config.apply_profile(args)


def test_metadata_is_saved_once_and_public_copy_has_no_local_details(experiment):
    root, args, tasks = experiment
    config = run_config.save_config(args, tasks, root)
    assert run_config.load_config(run_config.config_path(args.out)) == config
    public = run_config.public_config(config)
    text = json.dumps(public)
    assert str(root) not in text and args.base_url not in text and args.neo4j_uri not in text
    assert "runtime_identity" not in public
    assert config["profile_sha256"] == run_config.file_hash(
        run_config.PROFILE_DIR / "temp0-none.yaml"
    )
    args.resume = True
    assert run_config.save_config(args, tasks, root) == config


def test_new_yaml_profile_needs_no_python_registration(experiment):
    _, args, _ = experiment
    (run_config.PROFILE_DIR / "custom.yaml").write_text(
        "temperature: 0.6\nenable_thinking: true\nthinking_effort: low\n"
    )
    assert "custom" in run_config.profile_names()
    args.profile = "custom"
    run_config.apply_profile(args)
    assert (args.temperature, args.enable_thinking, args.thinking_effort) == (0.6, True, "low")


def test_resume_detects_yaml_edit_even_if_parameters_are_unchanged(experiment):
    root, args, tasks = experiment
    run_config.save_config(args, tasks, root)
    path = run_config.PROFILE_DIR / "temp0-none.yaml"
    path.write_text(path.read_text() + "# edited\n")
    args.resume = True
    run_config.apply_profile(args)
    with pytest.raises(ValueError, match="changed"):
        run_config.save_config(args, tasks, root)


@pytest.mark.parametrize(
    "content",
    [
        "[1, 2]",
        "max_tokens: 0",
        "temperature: 1\nenable_thinking: true\nthinking_effort: medium\napi_key: secret",
        "temperature: .nan\nenable_thinking: true\nthinking_effort: medium",
        "temperature: true\nenable_thinking: false\nthinking_effort: null",
        "temperature: 1\nenable_thinking: yes-please\nthinking_effort: null",
        "temperature: 1\nenable_thinking: false\nthinking_effort: medium",
        "temperature: 1\nenable_thinking: true\nthinking_effort: invented",
        "!!python/object/apply:os.system ['exit 0']",
        "temperature: [",
        "model: forbidden",
        "timeout_s: 0",
        "max_attempts: false",
        "top_p: 1.5",
        "seed: 'not an integer'",
        "presence_penalty: 3",
        "stop: []",
        "retry_low_effort_on_length: not-a-boolean",
    ],
)
def test_invalid_profiles_fail_before_inference(experiment, content):
    (run_config.PROFILE_DIR / "invalid.yaml").write_text(content)
    with pytest.raises(ValueError):
        run_config.load_profile("invalid")


def test_profile_names_cannot_escape_profile_directory(experiment):
    with pytest.raises(ValueError, match="Unknown"):
        run_config.load_profile("../other")


def test_full_call_settings_are_saved_from_profile(experiment):
    root, args, tasks = experiment
    path = run_config.PROFILE_DIR / "calls.yaml"
    path.write_text(
        "max_tokens: 32000\ntop_p: 0.8\nseed: 123\ntimeout_s: 120\nmax_attempts: 5\nretry_base_s: 4\nrate_limit_retry_s: 45\n"
    )
    args.profile = "calls"
    run_config.apply_profile(args)
    config = run_config.save_config(args, tasks, root)
    assert config["max_tokens"] == 32000
    assert config["llm_settings"]["seed"] == 123
    assert config["llm_settings"]["rate_limit_retry_s"] == 45
    assert config["llm_settings"] == run_config.public_config(config)["llm_settings"]


def test_runner_passes_yaml_settings_to_provider(experiment, monkeypatch):
    root, args, _ = experiment
    (run_config.PROFILE_DIR / "calls.yaml").write_text(
        "max_tokens: 32000\ntop_p: 0.8\ntimeout_s: 120\nmax_attempts: 5\n"
    )
    monkeypatch.chdir(root)
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner",
            "--tasks",
            str(args.tasks),
            "--schema-json",
            str(args.schema_json),
            "--graph-file",
            str(args.graph_file),
            "--out",
            str(args.out),
            "--profile",
            "calls",
            "--concurrency",
            "1",
        ],
    )
    with (
        patch.object(neo4j_benchmark, "_verify_graph"),
        patch.object(neo4j_benchmark, "ChatClient") as client,
        patch.object(
            neo4j_benchmark, "_run_agent_task", side_effect=lambda task, **kw: results([task])[0]
        ),
    ):
        neo4j_benchmark.main()
    settings = client.call_args.kwargs["settings"]
    assert settings.max_tokens == 32000 and settings.top_p == 0.8
    assert settings.timeout_s == 120 and settings.max_attempts == 5
    config = run_config.load_config(run_config.config_path(args.out))
    assert config["llm_settings"]["max_tokens"] == settings.max_tokens
    assert len(args.out.read_text().splitlines()) == 347


@pytest.mark.parametrize("change", ["model", "source", "input", "endpoint", "concurrency"])
def test_resume_rejects_changed_treatment(experiment, change):
    root, args, tasks = experiment
    run_config.save_config(args, tasks, root)
    args.resume = True
    if change == "source":
        (root / "src/agent_native_graph/__init__.py").write_text("# changed")
    elif change == "input":
        args.schema_json.write_text('{"changed":true}')
    elif change == "endpoint":
        args.base_url = "https://another.invalid"
    elif change == "concurrency":
        args.concurrency = 5
    else:
        args.model = "another/model"
    with pytest.raises(ValueError, match="changed"):
        run_config.save_config(args, tasks, root)


def test_resume_requires_original_metadata(experiment):
    root, args, tasks = experiment
    args.resume = True
    with pytest.raises(ValueError, match="original run metadata"):
        run_config.save_config(args, tasks, root)


def test_archiving_needs_only_output_and_can_happen_after_code_inputs_change(
    experiment, monkeypatch
):
    root, args, tasks = experiment
    config = run_config.save_config(args, tasks, root)
    args.out.write_text("".join(json.dumps(r) + "\n" for r in results(tasks)))
    args.tasks.unlink()
    args.graph_file.unlink()
    (run_config.PROFILE_DIR / "temp0-none.yaml").unlink()
    (root / "src/agent_native_graph/__init__.py").write_text("# newer code")
    monkeypatch.setattr(
        "sys.argv", ["archive", "--run", str(args.out), "--root", str(root / "results")]
    )
    archive_result.main()
    folders = list((root / "results/cypherbench-company/full/runs").iterdir())
    assert len(folders) == 1 and args.out.exists()
    manifest = json.loads((folders[0] / "manifest.json").read_text())
    assert manifest["model"] == "test/model" and manifest["temperature"] == 0
    assert manifest["configuration_sha256"] == config["configuration_sha256"]
    assert manifest["run_profile"] == "temp0-none"
    assert manifest["profile_sha256"] == config["profile_sha256"]
    assert str(root) not in (folders[0] / "run-config.json").read_text()


def test_archive_rejects_overrides_and_partial_or_foreign_results(experiment, monkeypatch):
    root, args, tasks = experiment
    config = run_config.save_config(args, tasks, root)
    rows = results(tasks)
    for bad in (
        rows[:-1],
        [*rows[:-1], rows[0]],
        [*rows[:-1], dict(rows[-1], nl_question="wrong")],
    ):
        with pytest.raises(ValueError):
            run_config.validate_results(bad, config)
    args.out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    monkeypatch.setattr("sys.argv", ["archive", "--run", str(args.out), "--model", "wrong"])
    with pytest.raises(ValueError, match="contradicts"):
        archive_result.main()
    metadata = run_config.config_path(args.out)
    saved = json.loads(metadata.read_text())
    saved["model"] = "tampered"
    metadata.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="Invalid run configuration"):
        run_config.load_config(metadata)


def test_lock_never_deletes_another_writers_lock(tmp_path):
    output = tmp_path / "run.jsonl"
    with run_config.run_lock(output):
        with pytest.raises(FileExistsError):
            with run_config.run_lock(output):
                pass
        assert output.with_suffix(".lock").exists()
    assert not output.with_suffix(".lock").exists()


def test_existing_output_not_deleted_by_runner(experiment, monkeypatch):
    _, args, _ = experiment
    args.out.write_text("existing results")
    monkeypatch.setattr(
        "sys.argv",
        ["runner", "--tasks", str(args.tasks), "--schema-json", "missing", "--out", str(args.out)],
    )
    with patch.object(neo4j_benchmark, "ChatClient") as client:
        with pytest.raises(ValueError, match="already exists"):
            neo4j_benchmark.main()
        client.assert_not_called()
    assert args.out.read_text() == "existing results"


def test_check_only_runs_no_database_or_inference(experiment, monkeypatch):
    root, args, _ = experiment
    monkeypatch.chdir(root)
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner",
            "--tasks",
            str(args.tasks),
            "--schema-json",
            str(args.schema_json),
            "--graph-file",
            str(args.graph_file),
            "--out",
            str(args.out),
            "--profile",
            "temp1-medium",
            "--check-only",
        ],
    )
    with (
        patch.object(neo4j_benchmark, "ChatClient") as client,
        patch.object(neo4j_benchmark, "_verify_graph") as database,
    ):
        neo4j_benchmark.main()
        client.assert_not_called()
        database.assert_not_called()
    assert run_config.load_config(run_config.config_path(args.out))["reasoning"] == "medium"
    assert not args.out.exists()


def test_runner_calls_existing_execution_directly_and_preserves_preflight(experiment, monkeypatch):
    root, args, _ = experiment
    monkeypatch.chdir(root)
    monkeypatch.setattr(
        "sys.argv",
        [
            "runner",
            "--tasks",
            str(args.tasks),
            "--schema-json",
            str(args.schema_json),
            "--graph-file",
            str(args.graph_file),
            "--out",
            str(args.out),
            "--profile",
            "temp0-none",
        ],
    )
    with (
        patch.object(neo4j_benchmark, "_verify_graph") as database,
        patch.object(neo4j_benchmark, "_execute") as execute,
    ):
        neo4j_benchmark.main()
        database.assert_called_once()
        execute.assert_called_once()


@pytest.mark.parametrize(
    "base,expected",
    [
        ("https://example.org", "https://example.org/v1/chat/completions"),
        ("https://example.org/v1/", "https://example.org/v1/chat/completions"),
        (
            "https://openrouter.ai/api/v1/chat/completions",
            "https://openrouter.ai/api/v1/chat/completions",
        ),
        ("https://openrouter.ai/api/", "https://openrouter.ai/api/v1/chat/completions"),
    ],
)
def test_provider_url_does_not_duplicate_v1(base, expected):
    assert chat_completions_url(base) == expected
