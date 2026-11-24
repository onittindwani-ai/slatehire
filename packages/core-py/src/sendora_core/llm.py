"""One wrapper for every model call: retries, structured output, cost tracking, budgets, recorded fixtures.

Three backends, chosen by LLM_BACKEND (or by LLM_MODE=live for older configs):
  offline    the default. No network, no key. Uses the stand in the system passes to build_llm, or recorded fixtures.
  fixture    replays recorded answers from LLM_FIXTURES_DIR and fails loudly when one is missing.
  anthropic  the real Anthropic Messages API (llm_anthropic.py). UNVERIFIED live: never run against the real API.

Text from outside (emails, tickets, resumes, web pages) goes in through `untrusted=` so it sits in a marked data block.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from sendora_core.costs import CostTracker
from sendora_core.llm_anthropic import AnthropicBackend, LLMAPIError
from sendora_core.llm_fixtures import FixtureLLM, RecordingBackend, fixture_key
from sendora_core.llm_types import LLMBackend, LLMBudgetError, LLMError, LLMResponse
from sendora_core.redaction import redact_text
from sendora_core.safety import UNTRUSTED_POLICY, KillSwitchError, wrap_untrusted
from sendora_core.settings import BaseAppSettings, LLMBackendKind

T = TypeVar("T", bound=BaseModel)
log = logging.getLogger("sendora_core.llm")

__all__ = [
    "LLM", "LLMBackend", "LLMResponse", "LLMError", "LLMBudgetError", "LLMAPIError", "FixtureLLM", "RecordingBackend",
    "AnthropicBackend", "CallBudget", "build_llm", "fixture_key", "reset_budgets",
]


class CallBudget:
    """Counts live calls in this process and, when asked, checks total tracked spend. Thread safe."""

    def __init__(self, max_calls: int | None = None, max_usd: float | None = None):
        self.max_calls, self.max_usd, self.calls = max_calls, max_usd, 0
        self._lock = threading.Lock()

    def charge(self, tracker: CostTracker | None) -> None:
        with self._lock:
            if self.max_calls is not None and self.calls >= self.max_calls:
                raise LLMBudgetError(f"The limit of {self.max_calls} live model calls is used up. Raise LLM_CALL_BUDGET to continue.")
            if self.max_usd is not None and tracker is not None and tracker.total_usd() >= self.max_usd:
                raise LLMBudgetError(f"The spend limit of {self.max_usd} USD is reached. Raise LLM_BUDGET_USD to continue.")
            self.calls += 1


_BUDGETS: dict[str, CallBudget] = {}
_BUDGETS_LOCK = threading.Lock()


def shared_budget(key: str, max_calls: int | None, max_usd: float | None) -> CallBudget | None:
    """One budget per app name for the whole process, so a new LLM object per request cannot reset the count."""
    if max_calls is None and max_usd is None:
        return None
    with _BUDGETS_LOCK:
        b = _BUDGETS.get(key)
        if b is None or (b.max_calls, b.max_usd) != (max_calls, max_usd):
            b = _BUDGETS[key] = CallBudget(max_calls, max_usd)
        return b


def reset_budgets() -> None:
    with _BUDGETS_LOCK:
        _BUDGETS.clear()


class LLM:
    def __init__(
        self, settings: BaseAppSettings, backend: LLMBackend, tracker: CostTracker | None = None,
        retries: int | None = None, sleep: Callable[[float], None] = time.sleep, budget: CallBudget | None = None,
    ):
        self.settings, self.backend, self.tracker, self.sleep, self.budget = settings, backend, tracker, sleep, budget
        self.retries = settings.llm_max_retries if retries is None else retries

    def _model(self, kind: str) -> str:
        return self.settings.model_for(kind)

    def _log_prompt(self, model: str, purpose: str, prompt: str) -> None:
        if not self.settings.llm_log_prompts:
            log.info("llm call model=%s purpose=%s prompt_chars=%d", model, purpose, len(prompt))
            return
        shown = redact_text(prompt) if self.settings.llm_redact else prompt
        log.info("llm call model=%s purpose=%s prompt=%r", model, purpose, shown[:500])

    def ask(
        self, prompt: str, *, purpose: str, kind: str = "hard", system: str = "", max_tokens: int | None = None,
        untrusted: Mapping[str, str] | None = None, schema: dict | None = None,
    ) -> str:
        """Ask the model. `untrusted` maps a source name to text from outside; it is appended in a marked data block.
        `schema` is a JSON schema for backends that support native structured output (others ignore it)."""
        model = self._model(kind)
        if untrusted:
            prompt = prompt + "\n\n" + "\n\n".join(wrap_untrusted(text, source=name) for name, text in untrusted.items())
        full_system = f"{system}\n\n{UNTRUSTED_POLICY}".strip()
        limit = max_tokens or self.settings.llm_max_tokens
        extra = {"schema": schema} if schema is not None and getattr(self.backend, "supports_json_schema", False) else {}
        live = getattr(self.backend, "is_live", False)
        if live and self.settings.kill_switch:
            raise KillSwitchError("Kill switch is on, so the live model was not called. Turn it off in settings to continue.")
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            if self.budget is not None and live:
                self.budget.charge(self.tracker)
            self._log_prompt(model, purpose, prompt)
            try:
                r = self.backend.complete(model=model, system=full_system, prompt=prompt, max_tokens=limit, **extra)
                if self.tracker:
                    self.tracker.record(model, purpose, r.input_tokens, r.output_tokens)
                return r.text
            except LLMAPIError as exc:
                if not exc.retryable or attempt == self.retries:
                    raise
                last = exc
                self.sleep(exc.retry_after if exc.retry_after is not None else 0.5 * 2**attempt)
            except LLMError:
                raise
            except Exception as exc:  # network and rate limit errors are retried with backoff
                last = exc
                if attempt < self.retries:
                    self.sleep(0.5 * 2**attempt)
        raise LLMError(f"Model call failed after {self.retries + 1} tries: {last}")

    def structured(
        self, prompt: str, schema: type[T], *, purpose: str, kind: str = "hard", system: str = "",
        untrusted: Mapping[str, str] | None = None,
    ) -> T:
        """Ask for JSON that matches `schema` (a Pydantic model). Parse, validate, one repair attempt, then a clear error."""
        schema_json = schema.model_json_schema()
        instruction = f"{prompt}\n\nReply with only JSON matching this schema:\n{json.dumps(schema_json)}"
        text = self.ask(instruction, purpose=purpose, kind=kind, system=system, untrusted=untrusted, schema=schema_json)
        for attempt in range(2):
            try:
                return schema.model_validate_json(_extract_json(text))
            except (ValidationError, ValueError) as exc:
                if attempt == 1:
                    raise LLMError(f"The model reply did not match the expected shape: {exc}") from exc
                text = self.ask(
                    f"{instruction}\n\nYour last reply was invalid ({exc}). Reply again with valid JSON only.",
                    purpose=purpose, kind=kind, system=system, untrusted=untrusted, schema=schema_json,
                )
        raise LLMError("unreachable")  # pragma: no cover


def _extract_json(text: str) -> str:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found")
    return text[start : end + 1]


def build_llm(
    settings: BaseAppSettings, tracker: CostTracker | None, fixtures_dir: Path | None = None, default: str | None = None,
    offline: LLMBackend | None = None, transport=None,
) -> LLM:
    """The one place a system gets its model. `offline` is the system's own stand in (used when the backend is offline)."""
    kind = settings.effective_llm_backend
    directory = Path(fixtures_dir or settings.llm_fixtures_dir) if (fixtures_dir or settings.llm_fixtures_dir) else None
    if kind is LLMBackendKind.ANTHROPIC:
        if not settings.anthropic_api_key:
            raise LLMError("The model backend is anthropic but ANTHROPIC_API_KEY is empty.")
        backend: LLMBackend = AnthropicBackend(
            settings.anthropic_api_key, base_url=settings.anthropic_base_url, version=settings.anthropic_version,
            timeout=settings.llm_timeout, thinking=settings.llm_thinking, transport=transport,
        )
        if settings.llm_record:
            if directory is None:
                raise LLMError("LLM_RECORD is on but LLM_FIXTURES_DIR is empty.")
            backend = RecordingBackend(backend, directory, redact=settings.llm_redact)
        budget = shared_budget(settings.app_name, settings.llm_call_budget, settings.llm_budget_usd)
        return LLM(settings, backend, tracker, budget=budget)
    if kind is LLMBackendKind.FIXTURE:
        if directory is None:
            raise LLMError("LLM_BACKEND is fixture but LLM_FIXTURES_DIR is empty.")
        return LLM(settings, FixtureLLM(directory), tracker)
    return LLM(settings, offline if offline is not None else FixtureLLM(directory, default=default), tracker)
