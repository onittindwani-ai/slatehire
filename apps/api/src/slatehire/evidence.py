"""Evidence quote verification. Independent of the scorer: it works for any scorer, including a language model.

A quote counts only when it is an exact piece of the stored redacted resume text, long enough to mean something, not made of redaction
placeholders, and not taken from a line flagged as an instruction aimed at the scorer. A criterion score with no valid quote is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass

from slatehire.redaction import PLACEHOLDER_RE

MIN_LEN = 12
MAX_LEN = 400


@dataclass(frozen=True)
class QuoteCheck:
    ok: bool
    reason: str = ""
    start: int = -1


def verify_quote(quote: object, text: str, blocked: list[tuple[int, int]] | None = None) -> QuoteCheck:
    if not isinstance(quote, str) or not quote:
        return QuoteCheck(False, "the quote is empty")
    if len(quote) < MIN_LEN:
        return QuoteCheck(False, f"the quote is shorter than {MIN_LEN} characters")
    if len(quote) > MAX_LEN:
        return QuoteCheck(False, f"the quote is longer than {MAX_LEN} characters")
    if PLACEHOLDER_RE.search(quote):
        return QuoteCheck(False, "the quote contains a redaction placeholder")
    if not quote.strip():
        return QuoteCheck(False, "the quote is blank")
    pos = text.find(quote)
    if pos < 0:
        return QuoteCheck(False, "the quote is not in the resume text")
    while pos >= 0:
        end = pos + len(quote)
        if not any(a < end and pos < b for a, b in (blocked or [])):
            return QuoteCheck(True, "", pos)
        pos = text.find(quote, pos + 1)
    return QuoteCheck(False, "the quote comes from a line that talks to the scorer")


def verify_item(item: dict, text: str, blocked: list[tuple[int, int]] | None = None) -> dict:
    """Return the item with a final state. scored needs at least one valid quote and every quote valid. not_found needs no quotes."""
    quotes = item.get("quotes") or []
    state = item.get("state")
    if state == "not_found":
        return {**item, "quotes": [], "value": None, "problem": None} if not quotes else {**item, "state": "rejected", "value": None, "problem": "a not found criterion cannot carry quotes"}
    if state != "scored" or not isinstance(item.get("value"), int) or not 1 <= item["value"] <= 5:
        return {**item, "state": "rejected", "value": None, "problem": "the score is not a whole number from 1 to 5"}
    if not quotes:
        return {**item, "state": "rejected", "value": None, "problem": "a score needs at least one quote from the resume"}
    checked, bad = [], []
    for q in quotes:
        c = verify_quote(q, text, blocked)
        (checked if c.ok else bad).append({"text": q, "start": c.start} if c.ok else {"text": str(q)[:80], "reason": c.reason})
    if bad:
        return {**item, "state": "rejected", "value": None, "quotes": [], "rejected_quotes": bad, "problem": bad[0]["reason"]}
    return {**item, "quotes": checked, "problem": None}
