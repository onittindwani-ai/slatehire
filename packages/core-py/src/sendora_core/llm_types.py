"""Small shared types of the model wrapper. Import them from sendora_core.llm."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LLMError(RuntimeError):
    pass


class LLMBudgetError(LLMError):
    """The call budget or the spend budget is used up. Raise the budget in settings to continue."""


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    stop_reason: str | None = None
    request_id: str | None = None


class LLMBackend(Protocol):
    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int) -> LLMResponse: ...
