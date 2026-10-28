import json
from unittest.mock import patch

import httpx
import pytest

from agent_native_graph.llm_providers import openai_compatible
from agent_native_graph.llm_providers.settings import LLMCallSettings


def provider(monkeypatch, settings):
    monkeypatch.setenv("TEST_LLM_KEY", "test-only-key")
    return openai_compatible.OpenAICompatibleProvider(
        base_url="https://example.invalid",
        model="test/model",
        api_key_env="TEST_LLM_KEY",
        api_key_file=None,
        settings=settings,
    )


def response(finish="stop"):
    return {
        "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
    }


def test_settings_reach_payload_and_http_client(monkeypatch):
    settings = LLMCallSettings(
        temperature=0.7,
        max_tokens=32000,
        top_p=0.9,
        seed=42,
        presence_penalty=0.1,
        frequency_penalty=0.2,
        stop=["END"],
        enable_thinking=True,
        thinking_effort="medium",
        tool_choice="required",
        timeout_s=120,
    )
    llm = provider(monkeypatch, settings)
    requests, timeouts = [], []

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=response())

    client_type = httpx.Client

    def client(**kwargs):
        timeouts.append(kwargs["timeout"])
        return client_type(transport=httpx.MockTransport(handle))

    with patch.object(openai_compatible.httpx, "Client", side_effect=client):
        llm.chat([{"role": "user", "content": "Q"}], tools=[])
    payload = requests[0]
    assert payload["model"] == "test/model" and payload["max_tokens"] == 32000
    assert payload["temperature"] == 0.7 and payload["top_p"] == 0.9
    assert payload["seed"] == 42 and payload["stop"] == ["END"]
    assert payload["presence_penalty"] == 0.1 and payload["frequency_penalty"] == 0.2
    assert payload["reasoning_effort"] == "medium" and payload["tool_choice"] == "required"
    assert payload["chat_template_kwargs"]["enable_thinking"] is True
    assert "timeout_s" not in payload and "max_attempts" not in payload
    assert timeouts == [120]


def test_default_request_keeps_legacy_generation_payload(monkeypatch):
    llm = provider(monkeypatch, LLMCallSettings())
    sent = []
    client_type = httpx.Client

    def handle(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=response())

    with patch.object(
        openai_compatible.httpx,
        "Client",
        side_effect=lambda **kw: client_type(transport=httpx.MockTransport(handle)),
    ):
        llm.chat([{"role": "user", "content": "Q"}], tools=[], tool_choice="auto")
    assert sent == [
        {
            "model": "test/model",
            "messages": [{"role": "user", "content": "Q"}],
            "temperature": 0.0,
            "max_tokens": 16000,
            "chat_template_kwargs": {"enable_thinking": False},
            "tools": [],
            "tool_choice": "auto",
        }
    ]


def test_profile_retry_limits_and_rate_limit_delay_are_applied(monkeypatch):
    llm = provider(monkeypatch, LLMCallSettings(max_attempts=2, rate_limit_retry_s=17))
    calls = []
    client_type = httpx.Client

    def handle(request):
        calls.append(request)
        return (
            httpx.Response(429, json={"error": "rate limit"})
            if len(calls) == 1
            else httpx.Response(200, json=response())
        )

    with (
        patch.object(
            openai_compatible.httpx,
            "Client",
            side_effect=lambda **kw: client_type(transport=httpx.MockTransport(handle)),
        ),
        patch.object(openai_compatible.time, "sleep") as sleep,
    ):
        result = llm.chat([])
    assert len(calls) == 2
    sleep.assert_called_once_with(17)
    assert result["__chat_meta"]["rate_limit_retries"] == 1


@pytest.mark.parametrize("enabled,expected_calls", [(True, 2), (False, 1)])
def test_low_effort_retry_is_configurable(monkeypatch, enabled, expected_calls):
    llm = provider(
        monkeypatch,
        LLMCallSettings(
            enable_thinking=True,
            thinking_effort="medium",
            retry_low_effort_on_length=enabled,
            max_tokens=32000,
        ),
    )
    sent = []
    client_type = httpx.Client

    def handle(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=response("length" if len(sent) == 1 else "stop"))

    with patch.object(
        openai_compatible.httpx,
        "Client",
        side_effect=lambda **kw: client_type(transport=httpx.MockTransport(handle)),
    ):
        result = llm.chat([])
    assert len(sent) == expected_calls
    assert all(p["max_tokens"] == 32000 for p in sent)
    if enabled:
        assert sent[1]["reasoning_effort"] == "low"
    assert result["__chat_meta"]["low_effort_retry"] == enabled
