"""Lines in a resume that talk to the scorer instead of describing the candidate. They are data: flagged, left out of scoring, never quoted."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

PATTERNS = [
    (r"\b(?:ignore|disregard|forget|override|bypass)\b[^\n.]{0,40}\b(?:rubric|instructions?|rules?|criteria|scoring|prompt|above|previous)\b", "tells the scorer to ignore its rules"),
    (r"\b(?:give|assign|award|rate|score|mark)\b[^\n.]{0,40}\b(?:5|five|10|ten|full|top|max(?:imum)?|perfect|highest)\b[^\n.]{0,30}\b(?:everything|all|every|criteria|stars?|points?|marks?|out of)\b", "asks for top scores"),
    (r"\b(?:hire|shortlist|advance|accept|interview)\s+(?:me|this candidate|this applicant|immediately)\b", "asks to be advanced"),
    (r"\b(?:do not|don't|never)\s+(?:reject|screen out|filter)\b", "asks not to be rejected"),
    (r"\b(?:system prompt|you are now|as an ai (?:model|assistant)|new instructions?|developer mode)\b", "pretends to be an instruction"),
    (r"\b(?:5|five)\s*(?:/|out of)\s*(?:5|five)\b[^\n]{0,30}\b(?:everything|all)\b", "asks for top scores"),
    (r"(?:^|[.!?:]\s+)\W*(?:note|message|attention|instruction|reminder)s?\s+(?:to|for)\s+(?:the\s+)?(?:ai|a\.i\.|llm|model|assistant|bot|reviewers?|scorers?|graders?|evaluators?|screeners?|screening|recruiters?|hiring (?:manager|system|team)|automated|algorithm|ats)\b", "talks to the scorer"),
    (r"\b(?:if|when)\s+you\s+are\s+(?:an?\s+)?(?:ai|llm|language model|bot|automated|assistant|algorithm|screening)\b", "talks to the scorer"),
    (r"\b(?:rate|score|rank|grade|mark|evaluate|assess)\s+(?:this|the|my)\s+(?:candidate|applicant|resume|cv|application|profile)\s+(?:as\s+|at\s+|with\s+)?(?:the\s+)?(?:highest|top|best|excellent|perfect|outstanding|5|five|maximum|max|full)\b", "asks for top scores"),
    (r"\b(?:this|the)\s+(?:candidate|applicant)\s+(?:must|should|has to|needs to)\s+be\s+(?:hired|shortlisted|advanced|interviewed|selected|ranked|scored|rated|given|accepted|moved)\b", "asks to be advanced"),
    (r"\b(?:automatically|always)\s+(?:approve|advance|pass|accept|shortlist)\s+(?:me\b|(?:this|my|the)\s+(?:candidate|applicant|resume|cv|application))", "asks to be advanced"),
    (r"\b(?:regardless of|irrespective of)\b[^\n.]{0,30}\b(?:rubric|criteria|qualifications|experience)\b", "tells the scorer to ignore its rules"),
    (r"\b(?:maximum|full|top|highest|perfect)\s+(?:score|marks|rating|points)\b[^\n.]{0,40}\b(?:for|on|in)\s+(?:every|all|each)\b", "asks for top scores"),
]
RX = [(re.compile(p, re.I), why) for p, why in PATTERNS]


@dataclass(frozen=True)
class Flag:
    start: int
    end: int
    why: str


ZERO_WIDTH = {"\u200b", "\u200c", "\u200d", "\u2060", "\ufeff", "\u00ad"}
# Letters from other alphabets that look like Latin ones. "ignоre" with a Cyrillic o is the same instruction to a model and a different string to a pattern.
LOOKALIKE = str.maketrans({"а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ѕ": "s", "ј": "j", "ԁ": "d", "һ": "h", "ɡ": "g", "ν": "v", "ο": "o", "α": "a", "ε": "e", "ι": "i", "κ": "k", "ρ": "p", "τ": "t", "υ": "u", "χ": "x"})


def _fold(text: str) -> tuple[str, list[int]]:
    """A copy used for finding instructions: invisible characters dropped, width variants and look alike letters folded, accents removed, runs of spaces made one.
    Returns the copy and, for each of its characters, the offset in the original, so a match can be reported where it really is."""
    out: list[str] = []
    idx: list[int] = []
    prev_space = False
    for i, ch in enumerate(text):
        if ch in ZERO_WIDTH or unicodedata.category(ch) == "Cf":
            continue
        n = unicodedata.normalize("NFKC", ch)
        if len(n) == 1:
            ch = n
        ch = ch.translate(LOOKALIKE)
        d = unicodedata.normalize("NFD", ch)
        if len(d) > 1 and unicodedata.combining(d[1]) and d[0].isascii():
            ch = d[0]
        if ch != "\n" and ch.isspace():
            if prev_space:
                continue
            ch, prev_space = " ", True
        else:
            prev_space = False
        out.append(ch)
        idx.append(i)
    return "".join(out), idx


def _hit(rx_list, line: str) -> str | None:
    return next((why for rx, why in rx_list if rx.search(line)), None)


def _hit_across(rx_list, line: str, joined: str) -> str | None:
    """A match in two lines joined that starts in the first line and ends in the second, so an instruction only counts here when the break really splits it."""
    for rx, why in rx_list:
        for m in rx.finditer(joined):
            if m.start() < len(line) < m.end():
                return why
    return None


def find_injection(text: str) -> list[Flag]:
    """Whole lines (or sentences in one long line) that match, found on a folded copy of the text (look alike letters, hidden characters and extra spaces do not hide an instruction)
    and also across a line break (an instruction split over two lines is still one). Offsets are in `text`."""
    clean, idx = _fold(text)
    lines = clean.split("\n")
    spans: list[tuple[int, int, str]] = []
    pos = 0
    for n, line in enumerate(lines):
        why = _hit(RX, line)
        end = pos + len(line)
        if why is None and n + 1 < len(lines) and lines[n + 1].strip() and line.strip():
            joined = line + " " + lines[n + 1]
            why = _hit_across(RX, line, joined)
            if why is not None:
                end = pos + len(joined)  # both lines are the instruction
        if why is not None:
            spans.append((pos, end, why))
        pos += len(line) + 1
    out: list[Flag] = []
    for a, b, why in spans:
        if b <= a or a >= len(idx):
            continue
        start, stop = idx[a], idx[min(b, len(idx)) - 1] + 1
        if out and start <= out[-1].end:  # a pair that overlaps the previous one is one flag
            out[-1] = Flag(out[-1].start, max(out[-1].end, stop), out[-1].why)
        else:
            out.append(Flag(start, stop, why))
    return out
