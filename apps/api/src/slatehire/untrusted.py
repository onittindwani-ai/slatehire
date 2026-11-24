"""Lines in a resume that talk to the scorer instead of describing the candidate. They are data: flagged, left out of scoring, never quoted."""

from __future__ import annotations

import re
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


def find_injection(text: str) -> list[Flag]:
    """Whole lines (or sentences in one long line) that match. Offsets are in `text`."""
    out: list[Flag] = []
    pos = 0
    for line in text.split("\n"):
        for rx, why in RX:
            if rx.search(line):
                out.append(Flag(pos, pos + len(line), why))
                break
        pos += len(line) + 1
    return out
