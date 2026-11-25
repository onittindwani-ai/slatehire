"""Lines in a resume that talk to the scorer instead of describing the candidate. They are data: flagged, left out of scoring, never quoted."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# (pattern, what it does, direct). `direct` patterns name their own target ("this candidate", "me", "the AI") so a match is an attack by itself. The others use words an ordinary
# resume uses too (a compliance officer "cannot bypass the approval rules", a teacher "awarded full marks for every correct answer", an AI engineer wrote a "system prompt"), so a
# match counts as an attack only when the sentence is aimed at the reader: it opens with a command, or it names the reader (you, the scorer, the model, the assistant, the AI).
PATTERNS = [
    (r"\b(?:ignore|disregard|forget|override|bypass)\b[^\n.]{0,40}\b(?:rubric|instructions?|rules?|criteria|scoring|prompt|above|previous)\b", "tells the scorer to ignore its rules", False),
    (r"\b(?:give|assign|award|rate|score|mark)\b[^\n.]{0,40}\b(?:5|five|10|ten|full|top|max(?:imum)?|perfect|highest)\b[^\n.]{0,30}\b(?:everything|all|every|criteria|stars?|points?|marks?|out of)\b", "asks for top scores", False),
    (r"\b(?:hire|shortlist|advance|accept|interview)\s+(?:me|this candidate|this applicant|immediately)\b", "asks to be advanced", True),
    (r"\b(?:do not|don't|never)\s+(?:reject|screen out|filter(?: out)?)\s+(?:me|my\s+(?:resume|cv|application)|this\s+(?:candidate|applicant|resume|cv|application|profile|person)|the\s+(?:candidate|applicant))\b", "asks not to be rejected", True),
    (r"\b(?:system prompt|you are now|as an ai (?:model|assistant)|new instructions?|developer mode)\b", "pretends to be an instruction", False),
    (r"\b(?:5|five)\s*(?:/|out of)\s*(?:5|five)\b[^\n]{0,30}\b(?:everything|all)\b", "asks for top scores", False),
    (r"(?:^|[.!?:]\s{1,3})\W{0,5}(?:note|message|attention|instruction|reminder)s?\s+(?:to|for)\s+(?:the\s+)?(?:ai|a\.i\.|llm|model|assistant|bot|reviewers?|scorers?|graders?|evaluators?|screeners?|screening|recruiters?|hiring (?:manager|system|team)|automated|algorithm|ats)\b", "talks to the scorer", True),
    (r"\b(?:if|when)\s+you\s+are\s+(?:an?\s+)?(?:ai|llm|language model|bot|automated|assistant|algorithm|screening)\b", "talks to the scorer", True),
    (r"\b(?:rate|score|rank|grade|mark|evaluate|assess)\s+(?:this|the|my)\s+(?:candidate|applicant|resume|cv|application|profile)\s+(?:as\s+|at\s+|with\s+)?(?:the\s+)?(?:highest|top|best|excellent|perfect|outstanding|5|five|maximum|max|full)\b", "asks for top scores", True),
    (r"\b(?:this|the)\s+(?:candidate|applicant)\s+(?:must|should|has to|needs to)\s+be\s+(?:hired|shortlisted|advanced|interviewed|selected|ranked|scored|rated|given|accepted|moved)\b", "asks to be advanced", True),
    (r"\b(?:automatically|always)\s+(?:approve|advance|pass|accept|shortlist)\s+(?:me\b|(?:this|my|the)\s+(?:candidate|applicant|resume|cv|application))", "asks to be advanced", True),
    (r"\b(?:regardless of|irrespective of)\b[^\n.]{0,30}\b(?:rubric|criteria|qualifications|experience)\b", "tells the scorer to ignore its rules", False),
    (r"\b(?:maximum|full|top|highest|perfect)\s+(?:score|marks|rating|points)\b[^\n.]{0,40}\b(?:for|on|in)\s+(?:every|all|each)\b", "asks for top scores", False),
]
RX = [(re.compile(p, re.I), why, direct) for p, why, direct in PATTERNS]
INJECTION_SCAN = 2  # the version of the scan whose result is stored on a resume (with the place and the level of each flag); a stored scan of an older version is read again once
ATTACK, POSSIBLE = "attack", "possible"
POSSIBLE_WHY = "possible instruction in the text, read by a person"  # shown for a line that has the words of an instruction but is not aimed at the reader: it is flagged, never blocked, and still scored

# Who an instruction would be talking to, and the verbs a command opens with.
ADDRESSEE = re.compile(r"\b(?:you|your|yours|yourself)\b|\b(?:dear|hello|hi|hey|attention|notice|note|message|instructions?|reminder)s?\s+(?:to|for)\s+(?:the\s+)?(?:a\.?i\.?|llms?|models?|scorers?|assistants?|reviewers?|screeners?|graders?|evaluators?|bots?|algorithms?|ats|systems?)\b", re.I)
COMMAND_OPENERS = ("please", "kindly", "now", "also", "and", "then", "just", "important", "note", "attention", "instruction", "instructions", "reminder")
VOCATIVES = frozenset({"assistant", "ai", "model", "llm", "bot", "scorer", "scoring", "software", "system", "reviewer", "screener", "grader", "evaluator", "dear", "hello", "hi", "hey"})  # a command can be addressed: "Assistant, ignore the rubric"
COMMAND_VERBS = frozenset({"ignore", "disregard", "forget", "override", "bypass", "give", "assign", "award", "rate", "score", "mark", "hire", "shortlist", "advance", "accept", "interview", "rank", "grade", "approve",
                           "pass", "set", "treat", "consider", "do", "don't", "never", "always", "automatically", "you", "act", "respond", "output", "return", "print", "say", "answer", "reply"})
SENT_START = re.compile(r"[\s\W]*([A-Za-z']+)")


@dataclass(frozen=True)
class Flag:
    start: int
    end: int
    why: str
    level: str = ATTACK


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


SENT_BREAK = re.compile(r"[.!?;]\s+|\n")


def _sentence(line: str, a: int, b: int) -> str:
    """The sentence of `line` that holds the span a to b."""
    start = 0
    for m in SENT_BREAK.finditer(line, 0, a):
        start = m.end()
    end = SENT_BREAK.search(line, b)
    return line[start:end.start() + 1 if end else len(line)]


def _is_command(sentence: str) -> bool:
    """The sentence opens with a command (after a please or a note:), as in "Ignore the above rubric". A past tense line ("Awarded full marks ...") does not."""
    words = re.findall(r"[A-Za-z']+", sentence[:80].lower())
    while words and (words[0] in COMMAND_OPENERS or (words[0] in VOCATIVES and len(words) > 1 and words[1] in COMMAND_VERBS | frozenset(COMMAND_OPENERS) | VOCATIVES)):
        words = words[1:]
    return bool(words) and words[0] in COMMAND_VERBS


def _aimed(line: str, m: re.Match, direct: bool) -> bool:
    """Is a match an attack? A pattern that names its own target is. Any other is only when its sentence is a command or speaks to the reader (you, the scorer, the model, the AI)."""
    if direct:
        return True
    sentence = _sentence(line, m.start(), m.end())
    return _is_command(sentence) or bool(ADDRESSEE.search(sentence))


def _hit(rx_list, line: str, across: int | None = None) -> tuple[str, str] | None:
    """(what it does, ATTACK or POSSIBLE) for the strongest match in `line`, or None. With `across` (the length of the first of two joined lines) only a match that runs over the join counts."""
    weak: str | None = None
    for rx, why, direct in rx_list:
        for n, m in enumerate(rx.finditer(line)):
            if n >= 4:
                break
            if across is not None and not (m.start() < across < m.end()):
                continue
            if _aimed(line, m, direct):
                return why, ATTACK
            weak = weak or why
    return (POSSIBLE_WHY, POSSIBLE) if weak else None


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
    A line aimed at the reader (a command, or one that names the scorer, the model or the AI) is an ATTACK: it is left out of scoring and never quoted. A line with the same words that
    is not aimed at the reader ("cannot bypass the approval rules") is only POSSIBLE: it is flagged for a person and still scored.
    Every pattern is bounded and no pattern sees more than LINE_CAP characters at once, so a hostile file costs time in proportion to its length and no more."""
    clean, idx = _fold(text)
    units = _units(clean)
    spans: list[tuple[int, int, str, str]] = []
    for n, (pos, line) in enumerate(units):
        got = _hit(RX, line)
        end = pos + len(line)
        if (got is None or got[1] != ATTACK) and n + 1 < len(units) and units[n + 1][1].strip() and line.strip():
            joined = line + " " + units[n + 1][1]
            across = _hit(RX, joined, across=len(line))
            if across is not None and (got is None or across[1] == ATTACK):
                got = across
                end = min(pos + len(joined), units[n + 1][0] + len(units[n + 1][1]))  # both lines are the instruction
        if got is not None:
            spans.append((pos, end, got[0], got[1]))
    out: list[Flag] = []
    for a, b, why, level in sorted(spans):
        if b <= a or a >= len(idx):
            continue
        start, stop = idx[a], idx[min(b, len(idx)) - 1] + 1
        if out and start <= out[-1].end:  # a pair that overlaps the previous one is one flag, and an attack outranks a possible
            prev = out[-1]
            keep_level = ATTACK if ATTACK in (prev.level, level) else POSSIBLE
            out[-1] = Flag(prev.start, max(prev.end, stop), prev.why if prev.level == keep_level else why, keep_level)
        else:
            out.append(Flag(start, stop, why, level))
    return out


def attacks(flags: list[Flag]) -> list[Flag]:
    """The flags that are left out of scoring."""
    return [f for f in flags if f.level == ATTACK]


def entries(text: str, flags: list[Flag]) -> list[dict]:
    """The flags as stored on a resume: why, a short piece of the text, and where it sits (start and end in `text`), so the place never has to be searched for again."""
    return [{"why": f.why, "text": text[f.start:f.end][:160], "start": f.start, "end": f.end, "level": f.level} for f in flags]


def blocked_spans(stored: list[dict]) -> list[tuple[int, int]]:
    """Where, in the stored text, the lines that are left out of scoring sit: the attacks only. An entry from before levels existed counts as an attack."""
    return [(int(e["start"]), int(e["end"])) for e in stored if e.get("level", ATTACK) == ATTACK]
