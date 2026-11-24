"""PII and secret redaction for logs and event payloads."""

from __future__ import annotations

import re
from typing import Any

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[email]"),
    (re.compile(r"\b(?:sk|pk|rk|xox[abp]|ghp|gho)[-_][A-Za-z0-9_-]{10,}\b"), "[secret]"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}=*", re.I), "Bearer [secret]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[id-number]"),
    (re.compile(r"(?<!\w)\+?\d[\d\s().-]{8,}\d(?!\w)"), "[phone]"),
]
_SECRET_KEYS = re.compile(r"(password|secret|token|api[_-]?key|authorization|cookie)", re.I)


def redact_text(text: str) -> str:
    for pat, repl in _PATTERNS:
        text = pat.sub(repl, text)
    return text


def redact_obj(obj: Any) -> Any:
    """Return a redacted copy. Values under secret looking keys are always replaced."""
    if isinstance(obj, dict):
        return {k: ("[secret]" if _SECRET_KEYS.search(str(k)) else redact_obj(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(redact_obj(v) for v in obj)
    if isinstance(obj, str):
        return redact_text(obj)
    return obj
