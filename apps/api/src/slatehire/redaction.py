"""Identity redaction. Everything the scorers see has passed through here first.

Input is the original resume text. Output is the redacted text plus the segments that map the redacted text back to the original
(so the recruiter can switch blind mode off, and so evidence quotes can be highlighted in either view).

Rules: pure code, no model, no lookup of anything outside the text. Placeholders are uniform per category (never numbered, never sized
to what they replaced), so two resumes that differ only in identity redact to byte identical text. Nothing here infers a protected
attribute: it only removes what the text itself states. Limits are listed in docs/14.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

VERSION = "1"
PLACEHOLDERS = {"name": "[NAME]", "email": "[EMAIL]", "phone": "[PHONE]", "address": "[ADDRESS]", "link": "[LINK]", "photo": "[PHOTO]", "dob_age": "[BIRTH-OR-AGE]", "grad_year": "[YEAR]",
                "pronoun": "[PRONOUN]", "title": "[TITLE]", "institution": "[SCHOOL]", "personal": "[PERSONAL]"}
CATEGORY_LABELS = {"name": "Name", "email": "Email address", "phone": "Phone number", "address": "Street address", "link": "Profile or web link", "photo": "Photo reference", "dob_age": "Birth date or age",
                   "grad_year": "Graduation year", "pronoun": "Pronoun", "title": "Gendered title", "institution": "School or college", "personal": "Personal details"}
PLACEHOLDER_RE = re.compile(r"\[(?:" + "|".join(re.escape(v[1:-1]) for v in PLACEHOLDERS.values()) + r")\]")
PRIORITY = {"photo": 101, "email": 100, "link": 95, "phone": 90, "personal": 88, "dob_age": 86, "address": 84, "grad_year": 80, "institution": 78, "name": 70, "title": 60, "pronoun": 55}

NEUTRAL = {"salesman": "salesperson", "saleswoman": "salesperson", "foreman": "supervisor", "forewoman": "supervisor", "chairman": "chair", "chairwoman": "chair", "waitress": "server", "waiter": "server",
           "businessman": "businessperson", "businesswoman": "businessperson", "policeman": "police officer", "policewoman": "police officer", "headmaster": "head teacher", "headmistress": "head teacher",
           "salesmen": "salespeople", "saleswomen": "salespeople", "stewardess": "flight attendant", "hostess": "host", "actress": "actor", "manageress": "manager", "spokesman": "spokesperson", "spokeswoman": "spokesperson"}

HEADINGS = {"resume", "curriculum", "vitae", "cv", "summary", "profile", "experience", "education", "skills", "contact", "page", "confidential", "references", "objective", "employment"}
COMMON_WORDS = {"will", "mark", "grant", "rose", "may", "bill", "art", "dean", "hope", "faith", "joy", "gray", "grey", "king", "young", "bell", "cook", "baker", "mason", "major", "chase", "frank", "miles", "reed", "case", "page"}
# Surnames and first names that are also everyday words. Such a token of the applicant's own name is removed where it is written as a name (Capitalised or
# in capitals), never where it is a plain lower case word: "Grant Cook" is redacted, "wrote grant proposals" is kept (a person called Grant must not
# lose every sentence about grants, and so a lower score).
ORDINARY_WORDS = COMMON_WORDS | {"porter", "driver", "banks", "bank", "fisher", "hunter", "archer", "carter", "butler", "cooper", "potter", "smith", "turner", "walker", "sage", "price", "long", "bishop", "church", "field", "fields",
                                 "ford", "hall", "lane", "park", "rice", "stone", "wood", "woods", "wright", "wise", "brown", "green", "white", "black", "gold", "hill", "lake", "marsh", "rich", "sharp", "swift", "winter", "summer",
                                 "rivers", "chambers", "cash", "carpenter", "gardner", "miller", "taylor", "weaver", "parker", "mayor", "judge", "knight", "steward", "marshall", "sailor", "shepherd", "thatcher", "tanner", "fox", "wolf", "lamb"}
# Words that make a first line a job title or a company, not a person: "Senior Data Analyst", "Acme Systems Ltd". Such a line is never taken for the applicant's name.
TITLE_WORDS = {"senior", "junior", "lead", "chief", "head", "principal", "staff", "associate", "assistant", "specialist", "analyst", "coordinator", "engineer", "developer", "designer", "consultant", "officer", "administrator", "representative",
               "technician", "supervisor", "manager", "director", "executive", "operator", "agent", "advisor", "adviser", "architect", "accountant", "nurse", "teacher", "clerk", "operations", "customer", "support", "service", "services",
               "sales", "marketing", "finance", "data", "software", "project", "product", "account", "human", "resources", "logistics", "warehouse", "quality", "research", "technical", "general", "inc", "ltd", "llc", "plc", "corp", "corporation",
               "company", "group", "systems", "solutions", "labs", "technologies", "partners", "associates", "holdings", "bank", "hospital", "clinic", "store", "stores"}
FUNCTION_WORDS = {"the", "and", "for", "with", "from", "that", "this", "these", "those", "are", "was", "were", "has", "had", "have", "not", "but", "its", "our", "his", "her", "their", "you", "your", "all", "any", "can", "who", "how", "why", "when", "where", "which", "into", "than", "then", "also", "per", "via", "off", "out", "one", "two", "she", "him", "them", "they", "will", "would", "could", "should"}
ZERO_WIDTH = {"​", "‌", "‍", "⁠", "﻿", "­"}


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    cat: str
    repl: str | None = None


@dataclass
class Redaction:
    redacted: str
    segments: list[dict]
    counts: dict[str, int] = field(default_factory=dict)
    version: str = VERSION


def _clean(text: str) -> tuple[str, list[int]]:
    """A copy used for finding things: invisible characters removed, accents and width variants folded, one character per original character."""
    out, idx = [], []
    for i, ch in enumerate(text):
        if ch in ZERO_WIDTH or unicodedata.category(ch) == "Cf":
            continue
        n = unicodedata.normalize("NFKC", ch)
        if len(n) == 1:
            ch = n
        d = unicodedata.normalize("NFD", ch)
        if len(d) > 1 and unicodedata.combining(d[1]) and d[0].isascii():
            ch = d[0]
        out.append(ch)
        idx.append(i)
    return "".join(out), idx

PHOTO_FILE = re.compile(r"\b[\w\-]{1,100}\.(?:jpe?g|png|gif|webp|heic)\b", re.I)


def _photo_file_lines(clean: str) -> list[Span]:
    """A line that names a photo file (name.jpg) is a photo reference as a whole. Found from the file name outward, never by scanning the line for it."""
    out: list[Span] = []
    done = -1
    for m in PHOTO_FILE.finditer(clean):
        if m.start() < done:
            continue
        start = clean.rfind("\n", 0, m.start()) + 1
        end = clean.find("\n", m.end())
        done = len(clean) if end < 0 else end
        out.append(Span(start, done, "photo"))
    return out


def _find(rx: str, text: str, cat: str, flags: int = re.I, group: int = 0) -> list[Span]:
    return [Span(m.start(group), m.end(group), cat) for m in re.finditer(rx, text, flags)]


# Every repeat in the address patterns has an upper bound and a match can only start where a word starts, so the work grows in step with the length of
# the text (a 60,000 character line of "a." used to take minutes). Limits come from the mail standards: a local part is at most 64 characters, a label 63.
# The tail of a link runs to the next space and is read once, because a match never starts inside an earlier one.
EMAIL = (r"(?<![\w+\-])(?:mailto:)?[\w+\-]{1,64}(?:(?:\.|\s{1,3}\.\s{1,3})[\w+\-]{1,64}){0,8}\s{0,3}(?:@|\[at\]|\(at\)|\{at\})\s{0,3}[\w\-]{1,63}(?:\s{0,3}(?:\.|\[dot\]|\(dot\)|\sdot\s)\s{0,3}[\w\-]{1,63}){1,10}"
         r"|(?<![\w.+\-])[\w.+\-]{1,64}\sat\s[\w\-]{1,63}(?:(?:\s{0,3}(?:\[dot\]|\(dot\)|\sdot\s)\s{0,3}|\.)[\w\-]{1,63}){1,10}(?<!\.)")  # the plain word "at" counts only with a spelled out dot or a dot with no space ("name at host dot example"), never "worked at Mercy. Led"
LINK = (r"(?:https?://|www\.)[^\s)>\]\"']+|\b(?:linkedin|github|gitlab|instagram|facebook|twitter|x|behance|dribbble|medium)\.(?:com|net|io)/[^\s)>\]\"']+"
        r"|(?<![\w\-])(?:[\w\-]{1,63}\.){1,10}(?:com|org|net|io|dev|test|me|co|app|ai|info|site)\b(?:/[^\s)>\]\"']*)?|(?<![\w@.])@[A-Za-z][\w.]{2,30}\b|(?<![\w/])\(?in/[\w\-]{3,}\)?")
DIGIT_WORDS = r"(?:zero|one|two|three|four|five|six|seven|eight|nine|oh)"
STREET_WORDS = r"(?:Street|St|Road|Rd|Lane|Ln|Avenue|Ave|Drive|Dr|Court|Ct|Way|Rise|Wharf|Row|Close|Terrace|Place|Pl|Boulevard|Blvd|Crescent|Square|Walk)"
EDU_WORDS = r"\b(?:b\.?a\.?|b\.?sc\.?|b\.?s\.?|m\.?a\.?|m\.?sc\.?|mba|ph\.?d|bachelor|master|diploma|degree|graduat\w*|class of|alumn\w*|studied|university|college|polytechnic|academy|institute|school of)\b"
HEADING_LINE = re.compile(r"^\W*(?P<h>[A-Za-z][A-Za-z &/]{2,30})\W*$")
NAME_SEQ = r"[A-Z][\w'’\-]+(?:[ \t]+[A-Z][\w'’\-]+){1,3}"
TITLE_RX = r"(?:(?:Dr|Prof|Mr|Mrs|Ms|Miss|Mx)\.?[ \t]+)?"
NOT_NAME_WORDS = {"available", "upon", "on", "furnished", "provided", "request", "none", "references", "reference", "contact", "details", "to", "from", "former", "current", "line", "senior", "manager", "director", "supervisor", "head"}
SECTION_NAMES = {"education": True, "training": True, "qualifications": True, "academic background": True, "experience": False, "work experience": False, "employment": False, "summary": False, "profile": False,
                 "skills": False, "projects": False, "certifications": False, "languages": False, "interests": False, "references": False, "professional experience": False}
SCHOOL_KW = r"(?:University|College|Institute|Polytechnic|Academy|Univ\.?)"
CAP = r"[A-Z][\w'’&\-]{0,40}"  # a capitalised word; the bound keeps a long run of capitals and dashes from being re read from every position
CAPS = rf"{CAP}(?:[ \t]+{CAP}){{0,3}}"
PARTICLES = r"(?:of|at|for|de|del|della|delle|degli|dei|di|du|des|der|van|von|do|da|das|dos|y|la|le|los|las|el|am|im)"
SCHOOL = rf"(?:{CAP}\s+){{0,4}}{SCHOOL_KW}(?:\s+(?:of|at|for)\s+(?:the\s+)?{CAPS}(?:\s+(?:of|at|for)\s+{CAPS})?)?"
FOREIGN_KW = r"(?:Universidad|Universidade|Universite|Universitat|Universitaet|Universiteit|Universita|Hochschule|Fachhochschule|Ecole|Escuela|Escola|Colegio|Instituto|Istituto|Institut|Politecnico|Lycee|Gymnasium|Akademie|Academia|Lyceum|Faculdade|Conservatoire|Conservatorio)"
FOREIGN_SCHOOL = rf"(?:{CAP}\s+){{0,3}}{FOREIGN_KW}(?:\s+{PARTICLES}\s+(?:{PARTICLES}\s+)?{CAPS}|\s+{CAPS})?"
SCHOOL_LEVEL = rf"(?:{CAP}\s+){{1,3}}(?:High|Grammar|Secondary|Primary|Elementary|Middle|Preparatory|Prep|Boarding)\s+School\b|\b(?:High|Grammar|Secondary|Primary|Elementary|Middle|Preparatory|Prep)\s+School\s+(?:of|at|for)\s+{CAPS}"
PERSONAL_LABEL = r"(?:marital status|nationality|citizenship|gender|sex|religion|religious (?:affiliation|views)|ethnicity|ethnic background|race|place of birth|birthplace|health|medical (?:condition|history)|disability|visa status|passport|children|kids|dependants|dependents|family status|family|spouse|partner|married|civil status|military status|military service|veteran status|date of birth|hobbies and religion|faith|church|sexual orientation|orientation|political (?:affiliation|views)|pregnancy|union membership|origin|born in)"


def _section_flags(text: str) -> list[bool]:
    """For each line: is it inside an education section."""
    flags, cur = [], False
    for line in text.split("\n"):
        m = HEADING_LINE.match(line.strip(" #*|-"))
        if m and m.group("h").strip().lower() in SECTION_NAMES:
            cur = SECTION_NAMES[m.group("h").strip().lower()]
        flags.append(cur)
    return flags


REFERENCE_LABEL = r"(?i:references?|referees?|reference contact|contact person|emergency contact|referred by|recommended by)"


def _plausible_name(words: list[str]) -> bool:
    return 2 <= len(words) <= 4 and not any(w.lower().strip(".,") in NOT_NAME_WORDS or w.lower().strip(".,") in HEADINGS for w in words) and not any(ch.isdigit() for w in words for ch in w)


ADDRESS_LABEL = r"(?i:address|adresse|direccion|indirizzo|adres|endereco|domicile|residence|wohnort|wohnadresse|home address|mailing address|postal address)"
STREET_FIRST = r"(?:Calle|Avenida|Rue|Via|Viale|Piazza|Rua|Plaza|Paseo|Carrer|Strada|Ulica|Largo|Travessa|Camino|Avenue|Boulevard|Chemin|Allee|Platz|Strasse|Weg)"
STREET_GLUED = r"(?:stra(?:ss|ß)e|gasse|weg|platz|allee|ring|damm|ufer|laan|straat|gatan|vagen|vejen|gade|veien|steig|pfad)"


def _international_addresses(clean: str) -> list[Span]:
    """Street and postcode forms used outside the US and UK: a labelled address line, a street word before or after the number, glued street names, postcode then city."""
    out: list[Span] = []
    out += _find(rf"(?m)^[ \t>*|\-•]*{ADDRESS_LABEL}[ \t]*[:\-\u2013][ \t]*([^\n]+)$", clean, "address", flags=0, group=1)
    out += _find(rf"\b\d{{1,4}}[A-Za-z]?,?[ \t]+(?:bis[ \t]+)?{STREET_FIRST}\b\.?[ \t]+(?:(?:{PARTICLES})[ \t]+)*{CAP}(?:[ \t]+{CAP}){{0,2}}(?:,?[ \t]*\d{{4,5}}(?:[ \t]+{CAP}(?:[ \t\-]{CAP})?)?)?", clean, "address", flags=0)
    out += _find(rf"\b{STREET_FIRST}[ \t]+(?:(?:{PARTICLES})[ \t]+)*{CAP}(?:[ \t]+{CAP}){{0,2}}[ \t]*,?[ \t]*(?:n[o°º]\.?[ \t]*)?\d{{1,4}}[A-Za-z]?\b(?:,?[ \t]*\d{{4,5}}(?:[ \t]+{CAP}(?:[ \t\-]{CAP})?)?)?", clean, "address", flags=0)
    out += _find(rf"\b[A-Z][a-z]+{STREET_GLUED}\.?[ \t]*\d{{1,4}}[A-Za-z]?\b(?:,?[ \t]*\d{{5}}[ \t]+{CAP}(?:[ \t\-]{CAP})?)?", clean, "address", flags=0)
    out += _find(rf"\b\d{{5}}[ \t]+{CAP}(?:[ \t\-]{CAP}){{0,2}}\b", clean, "address", flags=0)  # 75008 Paris, 10115 Berlin
    out += _find(rf"\b\d{{4}}[ \t]?[A-Z]{{2}}[ \t]+{CAP}\b", clean, "address", flags=0)  # 1011 AB Amsterdam
    out += _find(r"\b[A-Z]\d[A-Z][ \t]?\d[A-Z]\d\b", clean, "address", flags=0)  # K1A 0B1
    return out


def _reference_names(clean: str) -> list[Span]:
    """The person named as a reference is someone's identity too: after a label such as "Reference:", and at the start of a line inside a References section."""
    out: list[Span] = []
    for m in re.finditer(rf"(?m)^[ \t>*|\-•]*{REFERENCE_LABEL}[ \t]*(?:[:\-\u2013]|available from|from)[ \t]*{TITLE_RX}({NAME_SEQ})", clean):
        if _plausible_name(m.group(1).split()):
            out.append(Span(m.start(1), m.end(1), "name"))
    pos, in_refs = 0, False
    for line in clean.split("\n"):
        h = HEADING_LINE.match(line.strip(" #*|-"))
        if h:
            key = h.group("h").strip().lower()
            in_refs = key in {"references", "referees", "reference", "referee"} or (in_refs and key not in SECTION_NAMES)
        elif in_refs:
            m = re.match(rf"[ \t>*|\-•]*{TITLE_RX}({NAME_SEQ})(?=[ \t]*(?:[,(|:\-\u2013]|$))", line)
            if m and _plausible_name(m.group(1).split()):
                out.append(Span(pos + m.start(1), pos + m.end(1), "name"))
        pos += len(line) + 1
    return out


def _despace(line: str) -> str:
    parts = re.split(r"\s{3,}", line.strip())
    out = []
    for p in parts:
        toks = p.split(" ")
        out.append("".join(toks) if len(toks) >= 4 and all(len(t) == 1 for t in toks if t) else p)
    return " ".join(out)


def _looks_like_name(s: str) -> bool:
    words = [w for w in re.split(r"[\s,]+", s.strip()) if w]
    if not 2 <= len(words) <= 4 or any(w.lower().strip(".") in HEADINGS or w.lower().strip(".") in TITLE_WORDS for w in words):
        return False
    return all(re.fullmatch(r"[A-Z][A-Za-z'’\-]+|[A-Z]\.|[A-Z]{2,}[A-Za-z'’\-]*", w) for w in words) and not re.search(r"\d|@", s)


def _discover_names(clean: str, emails: list[str]) -> set[str]:
    found: set[str] = set()
    lines = [ln.strip(" #*|\t") for ln in clean.split("\n")]
    first = next((ln for ln in lines if ln), "")
    for cand in (first, _despace(first)):
        cand = re.sub(r"^(?:resume|cv|curriculum vitae)\s*[:\-]\s*", "", cand, flags=re.I)
        if _looks_like_name(cand):
            found.update(re.split(r"[\s,]+", cand))
    for m in re.finditer(r"(?im)^[^\w\n]*(?:full name|name|candidate|applicant)[ \t]*[:\-][ \t]*(.+)$", clean):
        found.update(re.split(r"[\s,]+", m.group(1).strip()))
    for m in re.finditer(r"(?im)^.*page\s*\d+\s*(?:of|/)\s*\d+.*$", clean):
        for seg in re.split(r"[|·•]", m.group(0)):
            if _looks_like_name(seg.strip()):
                found.update(seg.split())
    for m in re.finditer(r"(?i)(?:resume|cv|curriculum vitae)[_\s\-]+([A-Z][a-z]+)[_\s\-]+([A-Z][a-z]+)", clean):
        found.update(m.groups())
    for m in re.finditer(r"(?im)^[ \t]*(?:sincerely|regards|best regards|kind regards|yours truly|thank you|thanks)\s{0,20},?\s{0,20}([A-Z][a-z]+(?:\s{1,3}[A-Z][a-z]+)?)\s{0,20}$", clean):
        found.update(m.group(1).split())
    for m in re.finditer(r"(?:prepared|written|submitted) by ([A-Z][a-z]+(?:\s+[A-Z][\w\-']+)?)", clean):
        found.update(m.group(1).split())
    for e in emails:
        local = re.split(r"[\s@\[(]", re.sub(r"(?i)^mailto:", "", e))[0]
        for t in re.split(r"[._\-+]", local):
            if len(t) >= 3 and t.isalpha():
                found.add(t)
    return {t.strip(".,'’") for t in found if len(t.strip(".,'’")) >= 2}


def _name_rx(token: str, *, ordinary: bool = False) -> re.Pattern:
    """The token as a whole word. A token that is also an everyday word matches only as a name: Capitalised or in capitals, case sensitive."""
    def shape(t: str) -> str:
        return r"\s?".join(re.escape(c) for c in t) if len(t) >= 5 else re.escape(t)

    if ordinary:
        return re.compile(rf"(?<![A-Za-z])(?:{shape(token.capitalize())}|{shape(token.upper())})(?![A-Za-z])")
    return re.compile(rf"(?<![A-Za-z]){shape(token)}(?![A-Za-z])", re.I)


def detect(text: str, known_names: list[str] | None = None, known_schools: list[str] | None = None) -> list[Span]:
    clean, idx = _clean(text)
    spans: list[Span] = []
    emails = [m.group(0) for m in re.finditer(EMAIL, clean, re.I)]
    spans += _find(EMAIL, clean, "email")
    spans += _find(LINK, clean, "link")
    spans += _find(r"!\[[^\]]*\]\([^)]*\)|<img[^>]*>|\[image[^\]]*\]", clean, "photo")
    spans += _find(r"(?im)^[ \t>*|\-]*((?:photo|photograph|headshot|portrait|picture)\b[^\n]*)$", clean, "photo", group=1)
    spans += _photo_file_lines(clean)
    spans += _find(r"[\[(][^\])\n]{0,120}\b(?:photos?|photograph\w*|pictures?|headshots?|portraits?|selfie|passport[ \-]photo|image)\b[^\])\n]{0,120}[\])]", clean, "photo")
    for m in re.finditer(r"(?<![\w.])(?:tel:)?\+?\(?\d[\d \t().\-]{6,}\d(?!\w)", clean, re.I):
        n = len(re.sub(r"\D", "", m.group(0)))
        if 10 <= n <= 15:
            spans.append(Span(m.start(), m.end(), "phone"))
    spans += _find(rf"(?<![A-Za-z])(?:{DIGIT_WORDS}[\s,.\-]*){{7,}}", clean, "phone")
    spans += _find(rf"(?im)^[ \t>*|\-]*((?:{PERSONAL_LABEL})\s*[:\-][^\n]*)$", clean, "personal", group=1)
    spans += _find(r"\b(?:date of birth|dob|d\.o\.b\.?|birth ?date|born(?: on)?)\b[^\n]{0,60}", clean, "dob_age")
    spans += _find(r"\bage\s*[:\-]?\s*\d{2}\b|\b\d{2}\s*(?:years?\s*old|yrs?\s*old|y/o)\b|\bb\.\s*(?:19|20)\d{2}\b", clean, "dob_age")
    # addresses
    spans += _find(rf"(?:(?:Flat|Apt\.?|Apartment|Unit|Suite)\s+\w+,?\s*)?\b\d{{1,5}}\s+(?:{CAP}\s+){{1,3}}{STREET_WORDS}\b\.?(?:,?[ \t]*[^\n]*)?", clean, "address", flags=0)
    spans += _find(r"(?im)^[ \t]*(?:Flat|Apt\.?|Apartment|Unit|Suite)\s+\w+[ \t]*,?[^\n]*$", clean, "address")
    spans += _find(r"(?i:P\.?O\.?\s*Box)[ \t]*\d+(?:,[ \t]*[A-Z]\w+(?:[ \t][A-Z]\w+)?)?", clean, "address", flags=0)
    spans += _find(r"(?m)(?:[A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)?[ \t]+)?\b[A-Z]{1,2}\d[A-Z\d]?[ \t]*\d[A-Z]{2}\b", clean, "address", flags=0)
    spans += _find(r"\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b", clean, "address", flags=0)
    spans += _international_addresses(clean)
    # graduation years
    in_edu = _section_flags(clean)
    pos = 0
    for n, line in enumerate(clean.split("\n")):
        if in_edu[n] or re.search(EDU_WORDS, line, re.I):
            spans += [Span(pos + m.start(), pos + m.end(), "grad_year") for m in re.finditer(r"\b(?:19|20)\d{2}\b", line)]
        pos += len(line) + 1
    # schools
    spans += _find(SCHOOL, clean, "institution", flags=0)
    spans += _find(FOREIGN_SCHOOL, clean, "institution", flags=0)
    spans += _find(SCHOOL_LEVEL, clean, "institution", flags=0)
    for s in known_schools or []:
        spans += _find(re.escape(s), clean, "institution")
    # names
    emails_clean = emails
    toks: set[str] = set()
    for n in known_names or []:
        toks.update(t for t in re.split(r"[\s\-]+", _clean(n)[0]) if len(t) >= 2)
    heur = {t for t in _discover_names(clean, emails_clean) for t in re.split(r"[\s\-]+", t) if len(t) >= 3 and t.lower() not in COMMON_WORDS and t.lower() not in HEADINGS and t.lower() not in FUNCTION_WORDS}
    for t in sorted(toks | heur, key=len, reverse=True):
        spans += [Span(m.start(), m.end(), "name") for m in _name_rx(t, ordinary=t.lower() in ORDINARY_WORDS).finditer(clean)]
    spans += _reference_names(clean)
    # pronouns, titles
    spans += _find(r"(?im)\bpronouns?\s*:[^\n]*", clean, "pronoun")
    spans += _find(r"\(?\b(?:she|he|they|ze|xe)\s*/\s*(?:her|him|them|hir|zir|xem)(?:\s*/\s*\w+)?\b\)?", clean, "pronoun")
    spans += _find(r"\b(?:he|she|him|her|hers|his|himself|herself)\b", clean, "pronoun")
    spans += _find(r"\b(?:Mr|Mrs|Ms|Miss|Mx|Mme|Herr|Frau)\b\.?|\bSir\b\.?(?=\s+[A-Z])|\bMadam\b", clean, "title", flags=0)
    for m in re.finditer(r"\b(" + "|".join(NEUTRAL) + r")\b", clean, re.I):
        w = m.group(1)
        r = NEUTRAL[w.lower()]
        r = r.upper() if w.isupper() else r.capitalize() if w[0].isupper() else r
        spans.append(Span(m.start(), m.end(), "title", r))
    # initials next to a name
    named = [s for s in spans if s.cat == "name"]
    for s in named:
        m = re.search(r"\b[A-Z]\.?[ \t]*$", clean[max(0, s.start - 4):s.start])
        if m:
            spans.append(Span(max(0, s.start - 4) + m.start(), s.start, "name"))
        m2 = re.match(r"[ \t]+[A-Z]\.(?!\w)", clean[s.end:s.end + 4])
        if m2:
            spans.append(Span(s.end, s.end + m2.end(), "name"))
    # map to original coordinates
    out = []
    for s in spans:
        if s.end > s.start and s.end <= len(idx):
            out.append(Span(idx[s.start], idx[s.end - 1] + 1, s.cat, s.repl))
    return out


def _select(spans: list[Span], n: int) -> list[Span]:
    taken = [False] * n
    chosen: list[Span] = []
    for s in sorted(spans, key=lambda s: (-PRIORITY[s.cat], -(s.end - s.start), s.start)):
        if not any(taken[s.start:s.end]):
            for i in range(s.start, s.end):
                taken[i] = True
            chosen.append(s)
        elif s.repl is None:  # keep the free parts of a span that only partly overlaps a stronger one
            i = s.start
            while i < s.end:
                if taken[i]:
                    i += 1
                    continue
                j = i
                while j < s.end and not taken[j]:
                    j += 1
                if j - i >= 3:
                    for k in range(i, j):
                        taken[k] = True
                    chosen.append(Span(i, j, s.cat))
                i = j
    chosen.sort(key=lambda s: s.start)
    return chosen


GAP = re.compile(r"[ \t,.'’&/\-\u2013]{0,3}")
GAP_NAME = re.compile(r"[ \t,.'’&/\-\u2013]{0,12}")
GAP_ADDR = re.compile(r"\s{0,3}")


def _merge(spans: list[Span], text: str) -> list[Span]:
    out: list[Span] = []
    for s in spans:
        if out and out[-1].cat == s.cat and s.cat != "title":
            gap = text[out[-1].end:s.start]
            if (GAP_ADDR if s.cat == "address" else GAP_NAME if s.cat == "name" else GAP).fullmatch(gap):
                out[-1] = Span(out[-1].start, s.end, s.cat)
                continue
        out.append(s)
    return out


def redact(text: str, known_names: list[str] | None = None, known_schools: list[str] | None = None, *, institutions: bool = True) -> Redaction:
    spans = detect(text, known_names, known_schools)
    if not institutions:
        spans = [s for s in spans if s.cat != "institution"]
    spans = _merge(_select(spans, len(text)), text)
    segs: list[dict] = []
    counts: dict[str, int] = {}
    pos = 0

    def plain(a: int, b: int) -> None:
        if b > a:
            o = text[a:b]
            r = "".join(c for c in o if c not in ZERO_WIDTH and unicodedata.category(c) != "Cf")
            if segs and segs[-1].get("c") is None:
                segs[-1]["o"] += o
                segs[-1]["r"] += r
            else:
                segs.append({"c": None, "o": o, "r": r})

    for s in spans:
        plain(pos, s.start)
        segs.append({"c": s.cat, "o": text[s.start:s.end], "r": s.repl if s.repl else PLACEHOLDERS[s.cat]})
        counts[s.cat] = counts.get(s.cat, 0) + 1
        pos = s.end
    plain(pos, len(text))
    return Redaction("".join(g["r"] for g in segs), segs, counts)


def blind_segments(r: Redaction) -> list[dict]:
    """The same segments with the original text removed from identity pieces (what blind mode sends to the browser)."""
    return [{"c": g["c"], "r": g["r"], **({"o": g["o"]} if g["c"] is None else {})} for g in r.segments]
