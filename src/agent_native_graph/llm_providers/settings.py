"""Model-independent settings for one LLM call and its retry policy."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMCallSettings:
    temperature: float = 0.0
    max_tokens: int = 16000
    top_p: float | None = None
    seed: int | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    stop: str | list[str] | None = None
    enable_thinking: bool = False
    thinking_effort: str | None = None
    retry_low_effort_on_length: bool = True
    tool_choice: str = "auto"
    timeout_s: float = 60.0
    max_attempts: int = 3
    retry_base_s: float = 2.0
    rate_limit_retry_s: float = 30.0

    def __post_init__(self) -> None:
        for name, low, high in (
            ("temperature", 0, 2),
            ("top_p", 0, 1),
            ("presence_penalty", -2, 2),
            ("frequency_penalty", -2, 2),
        ):
            value = getattr(self, name)
            if value is None and name != "temperature":
                continue
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not math.isfinite(value)
                or not low <= value <= high
                or (name == "top_p" and value == 0)
            ):
                interval = "(0, 1]" if name == "top_p" else f"[{low}, {high}]"
                raise ValueError(f"Invalid {name}: expected a finite number in {interval}")
        for name in ("max_tokens", "max_attempts"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("timeout_s", "retry_base_s", "rate_limit_retry_s"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not math.isfinite(value)
                or value < 0
                or (name == "timeout_s" and value == 0)
            ):
                raise ValueError(
                    f"{name} must be finite and positive (zero allowed for retry delays)"
                )
        if (
            type(self.enable_thinking) is not bool
            or type(self.retry_low_effort_on_length) is not bool
        ):
            raise ValueError("Thinking and retry flags must be booleans")
        if self.thinking_effort not in (None, "low", "medium", "high") or (
            not self.enable_thinking and self.thinking_effort is not None
        ):
            raise ValueError("Use null/low/medium/high effort, and null when thinking is off")
        if self.tool_choice not in ("auto", "required", "none"):
            raise ValueError("tool_choice must be auto, required or none")
        if self.seed is not None and type(self.seed) is not int:
            raise ValueError("seed must be an integer or null")
        if self.stop is not None:
            stops = [self.stop] if isinstance(self.stop, str) else self.stop
            if (
                not isinstance(stops, list)
                or not 1 <= len(stops) <= 4
                or any(not isinstance(s, str) or not s for s in stops)
            ):
                raise ValueError("stop must be null, a nonempty string, or 1-4 nonempty strings")

    def generation_options(self) -> dict:
        """Omit unspecified options instead of changing provider defaults."""
        return {
            name: getattr(self, name)
            for name in ("top_p", "seed", "presence_penalty", "frequency_penalty", "stop")
            if getattr(self, name) is not None
        }
