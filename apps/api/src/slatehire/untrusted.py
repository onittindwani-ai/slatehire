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
    (r"(?:^|[.!?:]\s{1,3})\W{0,5}(?:note|message|attention|instruction|reminder)s?\s+(?:to|for)\s+(?:the\s+)?(?:ai|a\.i\.|llm|model|assistant|bot|reviewers?|scorers?|graders?|evaluators?|screeners?|screening|recruiters?|hiring (?:manager|system|team)|automated|algorithm|ats)\b", "talks to the scorer"),
    (r"\b(?:if|when)\s+you\s+are\s+(?:an?\s+)?(?:ai|llm|language model|bot|automated|assistant|algorithm|screening)\b", "talks to the scorer"),
    (r"\b(?:rate|score|rank|grade|mark|evaluate|assess)\s+(?:this|the|my)\s+(?:candidate|applicant|resume|cv|application|profile)\s+(?:as\s+|at\s+|with\s+)?(?:the\s+)?(?:highest|top|best|excellent|perfect|outstanding|5|five|maximum|max|full)\b", "asks for top scores"),
    (r"\b(?:this|the)\s+(?:candidate|applicant)\s+(?:must|should|has to|needs to)\s+be\s+(?:hired|shortlisted|advanced|interviewed|selected|ranked|scored|rated|given|accepted|moved)\b", "asks to be advanced"),
    (r"\b(?:automatically|always)\s+(?:approve|advance|pass|accept|shortlist)\s+(?:me\b|(?:this|my|the)\s+(?:candidate|applicant|resume|cv|application))", "asks to be advanced"),
    (r"\b(?:regardless of|irrespective of)\b[^\n.]{0,30}\b(?:rubric|criteria|qualifications|experience)\b", "tells the scorer to ignore its rules"),
    (r"\b(?:maximum|full|top|highest|perfect)\s+(?:score|marks|rating|points)\b[^\n.]{0,40}\b(?:for|on|in)\s+(?:every|all|each)\b", "asks for top scores"),
]
RX = [(re.compile(p, re.I), why) for p, why in PATTERNS]
INJECTION_SCAN = 1  # the version of the scan whose result is stored on a resume (with the place of each flag); a stored scan of an older version is read again once


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


LINE_CAP = 2000  # a longer line is read in pieces of at most this many characters, so no pattern ever works on more than a short stretch at a time
OVERLAP = 300  # when a single sentence is longer than LINE_CAP it is cut with this much shared, so an instruction on the cut is still whole in one piece
SENTENCE_END = re.compile(r"[.!?]\s+")


def _pieces(line: str) -> list[tuple[int, str]]:
    """A long line as (offset, text) pieces of at most LINE_CAP characters, cut at sentence ends where there are any."""
    if len(line) <= LINE_CAP:
        return [(0, line)]
    out: list[tuple[int, str]] = []
    start = last = 0
    for m in SENTENCE_END.finditer(line):
        if m.end() - start > LINE_CAP and last > start:
            out.append((start, line[start:last]))
            start = last
        last = m.end()
    out.append((start, line[start:]))
    final: list[tuple[int, str]] = []
    for off, text in out:  # a stretch with no sentence end at all is cut in overlapping pieces
        if len(text) <= LINE_CAP:
            final.append((off, text))
            continue
        i = 0
        while i < len(text):
            final.append((off + i, text[i:i + LINE_CAP]))
            if i + LINE_CAP >= len(text):
                break
            i += LINE_CAP - OVERLAP
    return final


def _units(clean: str) -> list[tuple[int, str]]:
    units: list[tuple[int, str]] = []
    pos = 0
    for line in clean.split("\n"):
        units.extend((pos + off, piece) for off, piece in _pieces(line))
        pos += len(line) + 1
    return units


def find_injection(text: str) -> list[Flag]:
    """Whole lines (or, in a very long line, the stretch of about 2,000 characters around the match) that match, found on a folded copy of the text (look alike letters, hidden
    characters and extra spaces do not hide an instruction) and also across a line break (an instruction split over two lines is still one). Offsets are in `text`.
    Every pattern is bounded and no pattern sees more than LINE_CAP characters at once, so a hostile file costs time in proportion to its length and no more."""
    clean, idx = _fold(text)
    units = _units(clean)
    spans: list[tuple[int, int, str]] = []
    for n, (pos, line) in enumerate(units):
        why = _hit(RX, line)
        end = pos + len(line)
        if why is None and n + 1 < len(units) and units[n + 1][1].strip() and line.strip():
            joined = line + " " + units[n + 1][1]
            why = _hit_across(RX, line, joined)
            if why is not None:
                end = min(pos + len(joined), units[n + 1][0] + len(units[n + 1][1]))  # both lines are the instruction
        if why is not None:
            spans.append((pos, end, why))
    out: list[Flag] = []
    for a, b, why in sorted(spans):
        if b <= a or a >= len(idx):
            continue
        start, stop = idx[a], idx[min(b, len(idx)) - 1] + 1
        if out and start <= out[-1].end:  # a pair that overlaps the previous one is one flag
            out[-1] = Flag(out[-1].start, max(out[-1].end, stop), out[-1].why)
        else:
            out.append(Flag(start, stop, why))
    return out


def entries(text: str, flags: list[Flag]) -> list[dict]:
    """The flags as stored on a resume: why, a short piece of the text, and where it sits (start and end in `text`), so the place never has to be searched for again."""
    return [{"why": f.why, "text": text[f.start:f.end][:160], "start": f.start, "end": f.end} for f in flags]
