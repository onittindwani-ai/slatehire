"""Rubric rules: shape checks, locking, versions. A locked rubric never changes; an edit is a new version that must be locked again."""

from __future__ import annotations

import hashlib
import json
import re

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


# Words that stand in for age, origin, family, health or a school's name: a rubric must not look for them. A person can still choose to; the lock refuses until they are gone,
# and PROXY_TERMS adds the words your company or country needs.
PROXY_TERMS = ("young", "youthful", "digital native", "native speaker", "mother tongue", "recent graduate", "recent grad", "ivy league", "elite university", "top university", "top school", "prestigious",
               "maiden name", "marital", "married", "pregnan*", "gender", "male", "female", "race", "religion", "nationality", "citizenship", "accent", "culture fit", "cultural fit", "energetic", "under 30", "over 50", "years of age")


def _term_rx(term: str) -> str:
    """A whole word (or phrase), with an optional plural. A trailing star means any ending (pregnan* is pregnant and pregnancy)."""
    if term.endswith("*"):
        return rf"(?<![a-z]){re.escape(term[:-1])}"
    return rf"(?<![a-z]){re.escape(term)}(?:s|es)?(?![a-z])"


def _free_text(c: dict) -> str:
    """Every word a person wrote in a criterion (its name, description, question, look for words, anchors and anything else in it), except the id and the weight. The interview kit copies the question
    to every candidate, so it is held to the same rule as the rest."""
    parts: list[str] = []

    def walk(v) -> None:
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk({k: v for k, v in c.items() if k not in ("id", "weight")})
    return " ".join(parts).lower()


def proxy_problems(criteria: list[dict], extra: list[str] | None = None) -> list[str]:
    """Plain language problems for words in a rubric that point at a protected trait. Looks at everything written in a criterion: the name, the description, the question every
    candidate is asked, what is looked for and the anchors."""
    out: list[str] = []
    terms = [*PROXY_TERMS, *(t.lower() for t in (extra or []) if t)]
    for c in criteria:
        text = _free_text(c)
        hit = next((t for t in terms if re.search(_term_rx(t), text)), None)
        if hit:
            out.append(f"{(c.get('name') or c.get('id') or 'A criterion')}: \"{hit}\" can stand in for age, origin or another protected trait. Say what the work looks like instead.")
    return out


def fingerprint(criteria: list[dict], blind: bool = True, redaction_version: str = "1") -> str:
    """The signature of a rubric: its criteria, whether identity is hidden, and the redaction version that prepares the text it scores."""
    return hashlib.sha256(json.dumps({"criteria": criteria, "blind": blind, "redaction": redaction_version}, sort_keys=True).encode()).hexdigest()[:16]


def total_weight(criteria: list[dict]) -> int:
    return sum(int(c["weight"]) for c in criteria)
