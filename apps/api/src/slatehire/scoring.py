"""Rubric scoring. The offline scorer is a set of RULES, not a language model: it looks for the words the rubric lists, weighs how the
sentence describes the work, and quotes the resume. A live model can replace `propose` (the contract is the same shape); the code that
checks quotes and adds up the total does not change.

Nothing here reads the candidate's name, school, contact details or any demographic data: the input is the redacted text only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from slatehire import evidence, language
from slatehire.redaction import PLACEHOLDER_RE
from slatehire.untrusted import ATTACK, find_injection

SCORER = "offline rules v2 (not a language model)"
SPLIT = re.compile(r"(?<=[.;!?])\s+")


@dataclass(frozen=True)
class Sentence:
    start: int
    text: str


def sentences(text: str, blocked: list[tuple[int, int]]) -> list[Sentence]:
    out: list[Sentence] = []
    pos = 0
    for line in text.split("\n"):
        base = pos
        pos += len(line) + 1
        if any(a <= base < b for a, b in blocked):
            continue
        lead = len(line) - len(line.lstrip(" -*|•\t"))
        body = line[lead:].rstrip(" |")
        off = base + lead
        parts, cur = [], 0
        for m in SPLIT.finditer(body):
            parts.append((cur, body[cur:m.start() + 1]))
            cur = m.end()
        parts.append((cur, body[cur:]))
        for o, p in parts:
            if len(p.strip()) >= 12:
                out.append(Sentence(off + o, p))
    return out


def _hits(s: str, terms: list[str]) -> list[str]:
    return language.hits(s, terms)


def is_listed_only(s: str, terms: list[str]) -> bool:
    """A line that claims the words (a skills line, a run of short items, the same words said again and again) instead of showing the work."""
    return bool(language.is_list_line(s, _hits(s, terms)))


def strength(s: str, hits: list[str]) -> float:
    """How strongly one sentence shows the work (the product's 2 to 5 scale, see language.level_of), plus a small share for more matching terms so the best sentence is chosen."""
    return language.level_of(s, len(hits)) + min(len(hits), 3) * 0.1


def clause(s: Sentence, hits: list[str], limit: int = 240) -> tuple[int, str]:
    """The part of the sentence to quote: placeholder free, short enough, containing a hit."""
    pieces, cur = [], 0
    for m in PLACEHOLDER_RE.finditer(s.text):
        pieces.append((cur, s.text[cur:m.start()]))
        cur = m.end()
    pieces.append((cur, s.text[cur:]))
    pieces = [(o, p) for o, p in pieces if len(p.strip()) >= evidence.MIN_LEN]
    best = max(pieces, key=lambda x: (len(_hits(x[1], hits)), len(x[1])), default=(0, s.text))
    o, p = best
    lead = len(p) - len(p.lstrip())
    p = p.strip()
    if len(p) > limit:
        p = p[:limit].rsplit(" ", 1)[0]
    return s.start + o + lead, p


def propose(criterion: dict, sents: list[Sentence]) -> dict:
    terms = criterion.get("look_for", [])
    scored: list[tuple[float, Sentence, list[str], bool]] = []
    for s in sents:
        h = _hits(s.text, terms)
        if h:
            listed = is_listed_only(s.text, terms)
            scored.append((0.0 if listed else strength(s.text, h), s, h, listed))
    if not scored:
        return {"criterion_id": criterion["id"], "state": "not_found", "value": None, "quotes": [], "rationale": "No sentence in the resume matches this criterion."}
    scored.sort(key=lambda x: (-x[0], x[1].start))
    shown = [x for x in scored if not x[3]]
    if not shown:  # only a skills line or a run of keywords: a claim, not evidence of work
        return {"criterion_id": criterion["id"], "state": "not_found", "value": None, "quotes": [], "rationale": "Only a list of keywords, with no example of the work.", "listed_only": True}
    best = shown[0][0]
    value = max(1, min(5, int(best)))
    quotes = []
    for _, s, h, _l in shown[:3]:
        _o, q = clause(s, h)
        if q and q not in quotes:
            quotes.append(q)
    why = f"Best match: {len(shown[0][2])} matching term(s); {'a number or result is shown' if language.NUMBER.search(shown[0][1].text) else 'no number is shown'}."
    return {"criterion_id": criterion["id"], "state": "scored", "value": value, "quotes": quotes, "rationale": why, "listed_only": False}


def _check_model_item(c: dict, it: dict, sents: list[Sentence], flags: list[dict]) -> dict:
    """What the code checks about a model's answer, beyond that the quote exists. The quote must itself mention something the rubric looks for (so a resume cannot
    make the model cite any harmless sentence beside a top level), and a level two or more away from what the plain rules read is flagged for a person."""
    terms = c.get("look_for", [])
    if terms and not any(language.hits(q["text"], terms) for q in it["quotes"]):
        flags.append({"kind": "evidence_rejected", "detail": f"{c['name']}: the quote does not mention anything the rubric looks for", "criterion_id": c["id"]})
        return {**it, "state": "rejected", "value": None, "problem": "the quote does not mention anything the rubric looks for"}
    rules = propose(c, sents)
    rules_level = rules["value"] if rules["state"] == "scored" else 0
    if abs(int(it["value"]) - int(rules_level)) >= 2:
        flags.append({"kind": "model_level_differs", "detail": f"{c['name']}: the model gave {it['value']}, the plain rules read {rules_level or 'nothing'}. Look at the quote before you rely on it.", "criterion_id": c["id"]})
    return it


def score_resume(criteria: list[dict], redacted: str, scorer=None) -> dict:
    """Score a redacted resume against a locked rubric. Returns items (already verified), the weighted total and flags.

    `scorer` is None for the rules above, or a model scorer (`model_tasks.ModelScorer`) with the same call shape. Either way every quote is checked here against the redacted text, and
    the total is arithmetic done here: nothing a scorer says can skip the check or set the total."""
    inj = find_injection(redacted)
    blocked = [(f.start, f.end) for f in inj if f.level == ATTACK]  # only a line aimed at the reader is left out; one that merely has the words of an instruction is scored and flagged
    sents = sentences(redacted, blocked)
    items, flags = [], [{"kind": "instruction_in_resume" if f.level == ATTACK else "possible_instruction", "detail": f.why, "text": redacted[f.start:f.end][:160]} for f in inj]
    for c in criteria:
        raw = scorer(c, redacted, sents, blocked) if scorer is not None else propose(c, sents)
        it = evidence.verify_item(raw, redacted, blocked)
        if raw.get("via") == "model" and it["state"] == "scored":
            it = _check_model_item(c, it, sents, flags)
        if it.get("listed_only"):
            flags.append({"kind": "keyword_list", "detail": f"{c['name']}: only a run of keywords, counted as not shown", "criterion_id": c["id"]})
        if it["state"] == "rejected":
            flags.append({"kind": "evidence_rejected", "detail": f"{c['name']}: {it.get('problem')}", "criterion_id": c["id"]})
        items.append(it)
    flags += [{"kind": "model_note", "detail": n} for n in getattr(scorer, "notes", [])]
    used_model = any(it.get("via") == "model" for it in items)
    wsum = sum(int(c["weight"]) for c in criteria)
    got = sum(int(c["weight"]) * (it["value"] or 0) for c, it in zip(criteria, items))
    return {"items": items, "total": round(100 * got / (5 * wsum), 1), "covered": sum(1 for it in items if it["state"] == "scored"), "criteria": len(criteria), "flags": flags, "scorer": getattr(scorer, "name", SCORER) if used_model else SCORER}
