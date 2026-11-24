"""Rubric rules: shape checks, locking, versions. A locked rubric never changes; an edit is a new version that must be locked again."""

from __future__ import annotations

import hashlib
import json

SCALE = (1, 2, 3, 4, 5)
DEFAULT_ANCHORS = {"1": "Has seen this done but has not done it alone.", "3": "Has done this on their own, with a clear example.", "5": "Has led this, can show a measured result and can teach it."}


class RubricError(ValueError):
    pass


def validate(criteria: list[dict], *, need_terms: bool = True) -> list[str]:
    """Plain language problems. Empty means the rubric is fit to lock."""
    out: list[str] = []
    if not 2 <= len(criteria) <= 10:
        out.append("Use between 2 and 10 criteria.")
    seen: set[str] = set()
    for i, c in enumerate(criteria, 1):
        name = (c.get("name") or "").strip()
        if not name:
            out.append(f"Criterion {i} needs a name.")
        cid = c.get("id") or ""
        if cid in seen:
            out.append(f"{name or f'Criterion {i}'}: another criterion has the same name. Give each one its own name.")
        seen.add(cid)
        if not isinstance(c.get("weight"), int) or isinstance(c.get("weight"), bool) or not 1 <= c["weight"] <= 5:
            out.append(f"{name or i}: the weight must be a whole number from 1 to 5.")
        an = c.get("anchors") or {}
        for k in ("1", "3", "5"):
            if len((an.get(k) or "").strip()) < 8:
                out.append(f"{name or i}: write what a {k} looks like (at least a short sentence).")
        if need_terms and not [t for t in c.get("look_for", []) if str(t).strip()]:
            out.append(f"{name or i}: add at least one word or phrase to look for.")
    return out


def fingerprint(criteria: list[dict], blind: bool = True, redaction_version: str = "1") -> str:
    """The signature of a rubric: its criteria, whether identity is hidden, and the redaction version that prepares the text it scores."""
    return hashlib.sha256(json.dumps({"criteria": criteria, "blind": blind, "redaction": redaction_version}, sort_keys=True).encode()).hexdigest()[:16]


def total_weight(criteria: list[dict]) -> int:
    return sum(int(c["weight"]) for c in criteria)
