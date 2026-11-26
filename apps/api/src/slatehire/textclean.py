"""Text that comes from outside (an email, a form, a file name) is cleaned before it is stored, shown or put into a document.

A name with a line break in it must never add a paragraph to an offer letter, and an over long Message-ID must never be the reason a whole batch is lost.
"""

from __future__ import annotations

import hashlib
import re

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACE = re.compile("[\\s\\u0085\\u2028\\u2029\\u200b-\\u200f\\u202a-\\u202e\\u2060\\ufeff]+")


def clean_text(value: str | None, limit: int | None = None) -> str:
    """Text safe to store: no NUL byte (Postgres cannot hold one) and no other control character except new line, return and tab."""
    text = _CONTROL.sub("", value or "")
    return text[:limit] if limit else text


def one_line(value: str | None, limit: int) -> str:
    """A name, title or file name: control characters and line breaks become single spaces, and it is cut to `limit` characters."""
    return _SPACE.sub(" ", _CONTROL.sub(" ", value or "")).strip()[:limit]


def safe_ref(value: str | None, limit: int = 120) -> str | None:
    """An outside reference (a Message-ID, an ATS id) that always fits its column. A long or odd value is replaced by a short hash of itself,
    so the same message always gets the same reference and the references stay unique."""
    raw = clean_text(value).strip()
    if not raw:
        return None
    if len(raw) <= limit and raw.isprintable() and "\n" not in raw:
        return raw
    return "h-" + hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:40]
