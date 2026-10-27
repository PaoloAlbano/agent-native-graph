"""OpenAI-compatible chat-completions provider.

This adapter intentionally supports the gateway features used in our
investigation: native tool calls, max token control, temperature, 429 retry, and
optional reasoning/thinking hints for vLLM-style deployments.
"""

import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from agent_native_graph.llm_providers.settings import LLMCallSettings

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "Qwen/Qwen3.5-27B"
_DEFAULT_CALL_SETTINGS = LLMCallSettings()
LLM_HTTP_TIMEOUT_S = float(os.getenv("LLM_HTTP_TIMEOUT_S", str(_DEFAULT_CALL_SETTINGS.timeout_s)))
LLM_HTTP_MAX_ATTEMPTS = int(
    os.getenv("LLM_HTTP_MAX_ATTEMPTS", str(_DEFAULT_CALL_SETTINGS.max_attempts))
)
LLM_HTTP_RETRY_BASE_S = float(
    os.getenv("LLM_HTTP_RETRY_BASE_S", str(_DEFAULT_CALL_SETTINGS.retry_base_s))
)
LLM_RATE_LIMIT_RETRY_S = float(
    os.getenv("LLM_RATE_LIMIT_RETRY_S", str(_DEFAULT_CALL_SETTINGS.rate_limit_retry_s))
)


def chat_completions_url(base_url: str) -> str:
    """Accept a gateway root, /v1 base or complete chat-completions endpoint."""
    url = base_url.rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return url + "/chat/completions"
    return url + "/v1/chat/completions"


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key_env: str,
        api_key_file: Path | None,
        settings: LLMCallSettings,
    ) -> None:
        api_key = _load_api_key(api_key_env=api_key_env, api_key_file=api_key_file)
        if not api_key:
            raise RuntimeError(
                f"Missing API key. Set env var {api_key_env} or pass --api-key-file "
                "pointing to a local secret file."
            )
        self._url = chat_completions_url(base_url)
        self._model = model
        self._api_key = api_key
        self.settings = settings

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        chat_template_kwargs: dict[str, Any] = {"enable_thinking": self.settings.enable_thinking}
        if self.settings.thinking_effort:
            chat_template_kwargs["thinking_effort"] = self.settings.thinking_effort
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
            "chat_template_kwargs": chat_template_kwargs,
            **self.settings.generation_options(),
        }
        if self.settings.thinking_effort:
            payload["reasoning_effort"] = self.settings.thinking_effort
        if tools is not None:
            payload["tools"] = tools
            if tool_choice is None:
                tool_choice = self.settings.tool_choice
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        headers = {"Authorization": f"Bearer {self._api_key}"}
        last_error: Exception | None = None
        rate_limit_retries = 0
        http_retries = 0
        for attempt in range(self.settings.max_attempts):
            try:
                with httpx.Client(timeout=self.settings.timeout_s) as client:
                    response = client.post(self._url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    data, retry_meta = self._retry_low_effort_after_length_finish(
                        client=client,
                        headers=headers,
                        payload=payload,
                        data=data,
                    )
                break
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response.status_code == 429 and attempt < self.settings.max_attempts - 1:
                    rate_limit_retries += 1
                    print(
                        f"[llm] received 429 Too Many Requests; retrying in {self.settings.rate_limit_retry_s:g}s",
                        file=sys.stderr,
                    )
                    time.sleep(self.settings.rate_limit_retry_s)
                else:
                    http_retries += 1
                    time.sleep(self.settings.retry_base_s * (attempt + 1))
            except httpx.HTTPError as exc:
                last_error = exc
                http_retries += 1
                time.sleep(self.settings.retry_base_s * (attempt + 1))
        else:
            assert last_error is not None
            raise last_error
        message = dict(data["choices"][0]["message"])
        message["__chat_meta"] = self._response_meta(
            data=data,
            retry_meta=retry_meta,
            request_attempts=attempt + 1,
            rate_limit_retries=rate_limit_retries,
            http_retries=http_retries,
        )
        return message

    def _retry_low_effort_after_length_finish(
        self,
        *,
        client: httpx.Client,
        headers: dict[str, str],
        payload: dict[str, Any],
        data: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        retry_meta = {
            "low_effort_retry": False,
            "initial_finish_reason": self._finish_reason(data),
            "initial_usage": data.get("usage") or {},
            "final_thinking_effort": self.settings.thinking_effort,
        }
        if (
            not self.settings.retry_low_effort_on_length
            or not self.settings.enable_thinking
            or not self.settings.thinking_effort
        ):
            return data, retry_meta
        if self.settings.thinking_effort == "low":
            return data, retry_meta
        choice = (data.get("choices") or [{}])[0]
        if choice.get("finish_reason") != "length":
            return data, retry_meta
        retry_payload = dict(payload)
        retry_template_kwargs = dict(retry_payload.get("chat_template_kwargs") or {})
        retry_template_kwargs["thinking_effort"] = "low"
        retry_payload["chat_template_kwargs"] = retry_template_kwargs
        retry_payload["reasoning_effort"] = "low"
        print(
            "[llm] finish_reason=length with reasoning enabled; retrying with thinking_effort=low",
            file=sys.stderr,
        )
        response = client.post(self._url, headers=headers, json=retry_payload)
        response.raise_for_status()
        retry_meta["low_effort_retry"] = True
        retry_meta["final_thinking_effort"] = "low"
        return dict(response.json()), retry_meta

    def _response_meta(
        self,
        *,
        data: dict[str, Any],
        retry_meta: dict[str, Any],
        request_attempts: int,
        rate_limit_retries: int,
        http_retries: int,
    ) -> dict[str, Any]:
        return {
            "finish_reason": self._finish_reason(data),
            "initial_finish_reason": retry_meta.get("initial_finish_reason"),
            "low_effort_retry": bool(retry_meta.get("low_effort_retry")),
            "thinking_effort": self.settings.thinking_effort,
            "final_thinking_effort": retry_meta.get("final_thinking_effort"),
            "enable_thinking": self.settings.enable_thinking,
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
            "usage": data.get("usage") or {},
            "initial_usage": retry_meta.get("initial_usage") or {},
            "request_attempts": request_attempts,
            "rate_limit_retries": rate_limit_retries,
            "http_retries": http_retries,
        }

    @staticmethod
    def _finish_reason(data: dict[str, Any]) -> str | None:
        choice = (data.get("choices") or [{}])[0]
        finish_reason = choice.get("finish_reason")
        return str(finish_reason) if finish_reason is not None else None

    def complete(self, messages: list[dict[str, str]]) -> str:
        message = self.chat(messages)
        return str(message.get("content") or "")


def _load_api_key(*, api_key_env: str, api_key_file: Path | None) -> str | None:
    env_value = os.getenv(api_key_env)
    if env_value:
        return env_value.strip()
    if api_key_file is None:
        return None
    if not api_key_file.exists():
        raise RuntimeError(f"API key file does not exist: {api_key_file}")
    return api_key_file.read_text(encoding="utf-8").strip()


ChatClient = OpenAICompatibleProvider

__all__ = [
    "ChatClient",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "OpenAICompatibleProvider",
]
