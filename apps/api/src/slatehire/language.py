"""Plain word handling for the offline scorer. General English only: no resume, no rubric and no test set is encoded here.

What it gives the scorer: a small stemmer (so "reviewed", "reviews" and "reviewing" are one word), matching of a rubric term against a sentence (every content word of a
multi word term must be there, in any order and any form), and a handful of cues that describe how a sentence talks about work: is it a vague mention, a concrete duty,
does it show a number or a result, does it show ownership, is it sustained or does it reach other people. It is rules, NOT a language model, and it will misread sentences
that use words it does not know. Nothing here reads a name, a school or any demographic data: the scorer only ever gets redacted text.
"""

from __future__ import annotations

import re

TOKEN = re.compile(r"[a-z][a-z0-9+#]*(?:['’][a-z]+)?|\d+(?:[.,]\d+)*")
STOP = frozenset("a an the of to for in on at by with and or as is are was were be been it its this that these those from into over under per via my our their his her i we you they he she them us".split())
IRREGULAR = {"led": "lead", "built": "build", "wrote": "write", "written": "write", "ran": "run", "taught": "teach", "drove": "drive", "driven": "drive", "made": "make", "kept": "keep", "held": "hold",
             "sent": "send", "spoke": "speak", "spoken": "speak", "chose": "choose", "chosen": "choose", "sold": "sell", "won": "win", "grew": "grow", "grown": "grow", "began": "begin", "begun": "begin",
             "took": "take", "taken": "take", "gave": "give", "given": "give", "found": "find", "knew": "know", "known": "know", "saw": "see", "seen": "see", "met": "meet", "paid": "pay", "thought": "think",
             "brought": "bring", "bought": "buy", "caught": "catch", "dealt": "deal", "fell": "fall", "felt": "feel", "got": "get", "went": "go", "gone": "go", "left": "leave", "lost": "lose", "meant": "mean",
             "read": "read", "rose": "rise", "risen": "rise", "said": "say", "set": "set", "stood": "stand", "told": "tell", "understood": "understand", "worked": "work", "children": "child", "people": "person",
             "men": "man", "women": "woman", "analyses": "analysis", "data": "data", "staff": "staff", "series": "series", "process": "process", "address": "address", "business": "business", "access": "access"}
SUFFIXES = ("ations", "ation", "ingly", "ments", "ment", "ities", "ity", "ings", "ing", "ness", "ies", "ied", "ers", "ors", "er", "or", "ed", "es", "ly", "al", "s")


def stem(word: str) -> str:
    w = word.lower().replace("’", "'")
    if w.endswith("'s"):
        w = w[:-2]
    if w in IRREGULAR:
        return IRREGULAR[w]
    if len(w) <= 3 or not w.isalpha():
        return w
    for suf in SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            base = w[: -len(suf)]
            if suf in {"ies", "ied"}:
                base += "y"
            if len(base) >= 4 and base[-1] == base[-2] and base[-1] not in "sl":
                base = base[:-1]
            return base[:-1] if base.endswith("e") and len(base) > 3 else base
    return w[:-1] if w.endswith("e") and len(w) > 4 else w


def stems(text: str) -> list[str]:
    return [stem(t) for t in TOKEN.findall(text.lower())]


def content_stems(text: str) -> list[str]:
    return [stem(t) for t in TOKEN.findall(text.lower()) if t not in STOP]


def term_matches(sentence_stems: set[str], sentence_low: str, term: str) -> bool:
    """A term matches when its words start a word of the sentence in the old way (a plain prefix match), or when every content word of the term is in the sentence in any form."""
    t = term.lower().strip()
    if not t:
        return False
    if re.search(r"(?<![a-z])" + re.escape(t), sentence_low):
        return True
    ts = content_stems(t)
    if not ts or any(len(x) < 3 for x in ts) or len(ts) < len(re.findall(r"[a-z0-9+#]+", t)) - 2:
        return False  # a term made of tiny words (a/b, c++) matches only as written
    return all(x in sentence_stems or (len(x) >= 6 and any(s.startswith(x) or x.startswith(s) and len(s) >= 6 for s in sentence_stems)) for x in ts)


PLACEHOLDER = re.compile(r"\[[A-Z][A-Z\-]*\]")


def hits(sentence: str, terms: list[str]) -> list[str]:
    sentence = PLACEHOLDER.sub(" ", sentence)  # a redaction placeholder is not a word of the resume
    low = sentence.lower()
    ss = set(stems(sentence))
    return [t for t in terms if term_matches(ss, low, t)]


# ---------------------------------------------------------------- cues (general English)

NUMBER = re.compile(r"\d|%|\b(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|dozen|half|double[sd]?|triple[sd]?|twice)\b", re.I)
RESULT = re.compile(r"\b(?:reduc|cut(?:ting)?\b|improv|increas|rais(?:ed|ing)|grew|grow|sav(?:ed|ing)|faster|quicker|fewer|higher|lower|doubl|tripl|decreas|boost|eliminat|shorten|lift|gain|exceed|beat\b|achiev|record|zero\b|without (?:a |any )?(?:miss|incident|error|outage)|on time|on budget|per (?:day|week|month|year|hour|shift|quarter)|from [^.]{1,30} to [^.]{1,30})", re.I)
EXPOSURE = re.compile(r"\b(?:sat in|sit in|shadow|observ|watch(?:ed|ing)?\b|attend|read about|reading|course|class(?:es)?\b|familiar|aware|exposure|exposed|interest|knowledge of|understanding of|learn|studied|curious|opportunit|seen\b)", re.I)
HELPER = re.compile(r"\b(?:helped\b|helping\b|helps\b|help (?:with|to|out)\b|assist(?:ed|ing|s)?\b|supported\b|supporting\b|particip|involv|contribut|basic|some experience|part of|took part|alongside|occasional|sometimes|a little|when needed|as needed|on request|if needed)", re.I)
LEAD = re.compile(r"\b(?:led\b|lead(?:ing)?\b|own(?:ed|er|ership)?\b|built\b|build(?:ing)?\b|design|launch|establish|creat|found(?:ed)?\b|introduc|rewr|rebuil|architect|drove\b|spearhead|ran\b|manag|set up|defin|develop|implement|mentor|coach|train|taught|teach|negotiat|chair|head(?:ed)?\b|oversaw|supervis|direct(?:ed)?\b|organi[sz]|initiat|pioneer|standardi[sz]|automat|redesign|replac|responsible for|in charge|took charge|sole)", re.I)
SUSTAIN = re.compile(r"\b(?:weekly|daily|monthly|quarterly|nightly|every|each (?:day|week|month|shift|quarter|sprint|release)|over \w+ (?:years?|months?)|for \w+ (?:years?|months?)|since\b|ongoing|maintain|continu|still\b|team of|train(?:ed|ing)|mentor|coach|taught|onboard|others|colleagues|used by|adopted|rely|relie[sd]|rolled out|across|handed|on call|rota|rotation)", re.I)
ACTION = re.compile(r"\b(?:\w+ed|wrote|built|ran|led|made|kept|held|took|gave|sent|found|taught|told|drove|chose|grew|won|sold|began|met|set|put|cut|got|spoke|handled|answered|processed|prepared|checked|counted|loaded|served|cooked|treated|taught|planned|scheduled|reviewed|tested|fixed|deployed|designed|shipped)\b", re.I)
SKILLS_LABEL = re.compile(r"^\W*(?:key |core |technical |top |relevant )?(?:skills?|competenc\w+|technologies|technology|tools?|keywords?|expertise|proficienc\w+|tech stack|areas of expertise|specialt\w+|tags?|strengths|abilities|capabilities|software|systems)\s*[:\-\u2013]", re.I)
SENT_LIST_SEP = re.compile(r"[,;|/•·•]")


def is_list_line(line: str, term_hit: list[str]) -> bool:
    """A line that claims the words instead of showing work: a skills line, a run of short items, or the same words said again and again."""
    body = line.strip()
    if SKILLS_LABEL.match(body) and len([x for x in SENT_LIST_SEP.split(body.split(":", 1)[-1]) if x.strip()]) >= 3:
        return True
    items = [x.strip() for x in SENT_LIST_SEP.split(body) if x.strip()]
    if len(items) >= 5:
        short = sum(1 for x in items if len(x.split()) <= 4)
        long_items = sum(1 for x in items if len(x.split()) >= 7)
        if short / len(items) >= 0.7 and long_items <= 1 and not re.search(r"\b(?:I|we)\b", body):
            return True
        norm = [re.sub(r"\W+", " ", x.lower()).strip() for x in items]
        if len(norm) - len(set(norm)) >= 2 and long_items <= 1:
            return True
    toks = stems(body)
    content = [t for t in toks if t not in STOP]
    if len(content) >= 24 and len(set(content)) / len(content) < 0.5 and not re.search(r"[.!?]\s+[A-Z]", body):
        return True
    return False


def level_of(sentence: str, n_hits: int = 1) -> int:
    """How strongly one sentence shows the work, on the scale of the product: 1 has only seen it (exposure), 2 a vague mention or help, 3 a concrete duty, 4 a duty with a number or a
    result, 5 owned work with a result that is sustained or reaches other people. A sentence with no cue at all is a plain mention (2). A criterion with nothing but a keyword list is not
    scored at all (see `is_list_line`)."""
    words = len(TOKEN.findall(sentence.lower()))
    exposure = bool(EXPOSURE.search(sentence))
    helper = bool(HELPER.search(sentence))
    lead = bool(LEAD.search(sentence))
    number = bool(NUMBER.search(sentence))
    result = bool(RESULT.search(sentence))
    sustained = bool(SUSTAIN.search(sentence))
    concrete = bool(ACTION.search(sentence)) and words >= 6 or words >= 10
    if exposure and not lead:
        return 1 if not (number and result) else 2
    if helper and not lead:
        return 2 if not (number and result) else 3
    if exposure or helper:
        return 3 if not (number or result) else 4
    if not concrete and not lead:
        return 2
    base = 3
    if number or result:
        base = 4
    if base == 4 and lead and (sustained or (number and result)):
        base = 5
    return base


# ---------------------------------------------------------------- which language

# Common function words that belong to one language and are rare in English. A resume with many of them is not English, and the English word rules below would find
# "no evidence" in it for every criterion and put the person at the bottom of the board without anyone being told.
OTHER_LANGUAGE_WORDS = frozenset("""de la el en los las que por con para una del su sus pero como tambien anos trabajo experiencia empresa gestion
le les des du est dans pour avec une sur qui ans experience entreprise gestion aux ce cette
und der die das mit von fur nicht ist ein eine im zu auf den dem bei jahre erfahrung unternehmen
nao uma os as dos das em um experiencia empresa anos
che di il per nel della dei degli anni esperienza azienda sono
een het voor met niet zijn jaar ervaring""".split())
ENGLISH_FUNCTION_WORDS = frozenset("the and of to for with was were that this from by at my our is are have has had which their been will across into using also over within".split())
_LETTERS = re.compile(r"[^\W\d_]+")
_ACCENTS = str.maketrans("áàâäãéèêëíìîïóòôöõúùûüçñß", "aaaaaeeeeiiiiooooouuuucns")


def detect(text: str) -> str:
    """"en" (or something this check cannot tell apart from it), "other" when the resume is plainly written in another language or script, "unknown" when it is too short to tell.
    A rough count of function words, not a language model: it is wrong for a resume that mixes languages, and it is right to send those to a person."""
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 80:
        return "unknown"
    beyond_latin = sum(1 for c in letters if ord(c) > 0x024F)
    if beyond_latin / len(letters) > 0.3:
        return "other"
    words = [w.lower().translate(_ACCENTS) for w in _LETTERS.findall(text)]
    if len(words) < 40:
        return "en"
    foreign = sum(1 for w in words if w in OTHER_LANGUAGE_WORDS)
    english = sum(1 for w in words if w in ENGLISH_FUNCTION_WORDS)
    if foreign >= 8 and foreign / len(words) >= 0.12 and foreign > 2 * english:
        return "other"
    return "en"
