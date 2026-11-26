"""Recorded answers: replay for tests and demos, recording for the one time a live run is saved."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from sendora_core.llm_types import LLMBackend, LLMError, LLMResponse
from sendora_core.redaction import redact_text


_SPACES = re.compile(r"[ \t]+")


def _loose(text: str) -> str:
    """Runs of spaces and tabs count as one space and trailing spaces are ignored.

    Text laid out in columns (a PDF page read by position) can shift by one space between operating systems
    when a position sits on a rounding boundary. The key must not depend on that, or a recording made on one
    machine would miss on another (it did: the same test passed on macOS and failed on the Linux CI runner).
    """
    return "\n".join(_SPACES.sub(" ", line).rstrip() for line in text.replace("\r\n", "\n").split("\n"))


def fixture_key(model_kind: str, system: str, prompt: str) -> str:
    return hashlib.sha256(f"{model_kind}\n{_loose(system)}\n{_loose(prompt)}".encode()).hexdigest()[:16]


class FixtureLLM:
    """Replays recorded answers. Missing fixture: uses `default` when given, otherwise raises a clear error."""

    def __init__(self, directory: Path | None = None, answers: dict[str, str] | None = None, default: str | None = None):
        self.directory, self.answers, self.default = directory, dict(answers or {}), default
        self.calls: list[str] = []

    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int) -> LLMResponse:
        key = fixture_key(model, system, prompt)
        self.calls.append(key)
        text, tin, tout = self.answers.get(key), None, None
        if text is None and self.directory is not None:
            f = Path(self.directory) / f"{key}.json"
            if f.exists():
                rec = json.loads(f.read_text())
                text, tin, tout = rec["text"], rec.get("input_tokens"), rec.get("output_tokens")
        if text is None:
            text = self.default
        if text is None:
            raise LLMError(f"No recorded fixture for key {key}. Record one with LLM_RECORD=true on a live run or add a fixture file.")
        return LLMResponse(text, tin or max(1, len(prompt) // 4), tout or max(1, len(text) // 4), model)


class RecordingBackend:
    """Wraps a live backend and saves every answer as <key>.json so the same call can be replayed offline.

    The file holds the answer and token counts, plus a short redacted preview of the prompt to help a human find it.
    Never commit recordings made from real customer data: the answer text can contain what the model read.
    """

    def __init__(self, inner: LLMBackend, directory: Path, redact: bool = True):
        self.inner, self.directory, self.redact = inner, Path(directory), redact
        self.supports_json_schema = getattr(inner, "supports_json_schema", False)
        self.is_live = getattr(inner, "is_live", False)

    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int, **kw) -> LLMResponse:
        r = self.inner.complete(model=model, system=system, prompt=prompt, max_tokens=max_tokens, **kw)
        self.directory.mkdir(parents=True, exist_ok=True)
        preview = (redact_text(prompt) if self.redact else prompt)[:160]
        rec = {"text": r.text, "input_tokens": r.input_tokens, "output_tokens": r.output_tokens, "model": model, "prompt_preview": preview}
        (self.directory / f"{fixture_key(model, system, prompt)}.json").write_text(json.dumps(rec, indent=2))
        return r
