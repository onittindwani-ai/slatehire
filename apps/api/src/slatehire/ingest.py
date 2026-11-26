"""Turn files, CSV rows and email messages into applicant records. Pure parsing, no database."""

from __future__ import annotations

import csv
import email
import io
import re
import time
from dataclasses import dataclass, field
from email import policy

from slatehire import pdfink

MAX_TEXT = 60_000
MAX_ROWS = 2000
MAX_FILE_BYTES = 5_000_000
MAX_PDF_PAGES = 12
MAX_PDF_SECONDS = 6.0
# What stands in for a resume that could not be read (an image only PDF, a broken attachment, an empty email). The applicant still enters the process,
# flagged, so a person can ask for another file instead of the person silently never existing.
MISSING_RESUME = "[No readable resume was received. Ask the applicant for a text or PDF version.]"
LANGUAGE_NOTE = "Not scored: language. The resume does not look like English, and the scorer reads English words only, so it would show no evidence for everything. A person reads this resume and decides; it can be shortlisted without a score."
RESUME_MISSING_NOTE = "Resume missing: no readable resume arrived (an image only PDF, a damaged file, a Word or Pages file, which are not read here, or an empty email). Nothing was scored, and this applicant cannot be shortlisted until a readable resume is added: ask for a PDF or a plain text version and add the applicant again with it (decline this entry with a reason), or just decline. If a PDF came with the application, its original file is kept for a person to open."


class IngestError(ValueError):
    def __init__(self, message: str = "", original: bytes = b"") -> None:
        super().__init__(message)
        self.original = original  # a PDF that could not be read is still kept for a person to open


@dataclass
class Applicant:
    name: str
    email: str = ""
    phone: str = ""
    role_key: str = ""
    resume_text: str = ""
    filename: str = ""
    source: str = ""
    school: str = ""
    external_ref: str | None = None
    extra: dict = field(default_factory=dict)  # notes: what the reader of the file found (see note()); role_ambiguous, resume_missing
    original: bytes = b""  # the file the resume was read from, when it is a PDF small enough to keep (intake decides)


# What a resume can be. A file of any other kind (a signature picture, a vCard, a calendar invite) is never read as text, whatever its name says.
RESUME_EXTENSIONS = (".pdf", ".txt", ".text", ".md", ".markdown", ".rtf")
WORD_PROCESSOR_EXTENSIONS = (".doc", ".docx", ".odt", ".pages")  # a likely resume in a format that is not read: the person is told, not given junk
NOT_READ_WORD = "A Word or Pages file was attached, and those are not read. Ask the applicant for a PDF or a plain text version."
# The first bytes of files that are never text. A resume that starts like one of these is refused whatever it is called.
BINARY_MAGIC = (b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"PK\x03\x04", b"\xd0\xcf\x11\xe0", b"\x7fELF", b"RIFF", b"\x00\x00\x01\x00", b"II*\x00", b"MM\x00*", b"\x1f\x8b", b"Rar!", b"7z\xbc\xaf", b"OggS")
_TEXT_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_RTF_TOKEN = re.compile(r"\\([\\{}])|\\'([0-9a-fA-F]{2})|(\\\*)|\\([a-zA-Z]+)-?\d* ?|([{}])|([^\\{}]+)")
_RTF_SKIPPED = frozenset({"fonttbl", "colortbl", "stylesheet", "info", "pict", "header", "footer", "headerl", "headerr", "footerl", "footerr", "object", "themedata", "datastore"})


def is_resume_name(filename: str) -> bool:
    return (filename or "").lower().endswith(RESUME_EXTENSIONS)


def _rtf_to_text(data: bytes) -> str:
    """The words of an RTF file: control words, font tables and other hidden groups are dropped, \\par and \\line become line breaks."""
    out: list[str] = []
    depth, skip, opened = 0, None, False
    for m in _RTF_TOKEN.finditer(data.decode("latin-1")):
        esc, hexv, star, word, brace, text = m.groups()
        if brace == "{":
            depth, opened = depth + 1, True
            continue
        if brace == "}":
            if skip is not None and depth <= skip:
                skip = None
            depth, opened = max(0, depth - 1), False
            continue
        if skip is None and (star or (word in _RTF_SKIPPED and opened)):
            skip = depth
        opened = False
        if skip is not None:
            continue
        if esc:
            out.append(esc)
        elif hexv:
            out.append(bytes([int(hexv, 16)]).decode("cp1252", "replace"))
        elif word:
            out.append("\n" if word in {"par", "line", "row"} else "\t" if word == "tab" else " " if word in {"cell", "sect"} else "")
        elif text:
            out.append(text.replace("\r", "").replace("\n", ""))  # a line break in the file itself is not a line break in the text
    return "".join(out)


def _decode_text(data: bytes) -> str:
    """Bytes that really are text, or an IngestError. Never latin-1 on anything: a picture decoded that way becomes thousands of characters of nonsense that look like a resume."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):  # a text file saved as UTF-16 (Notepad can do this)
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError as exc:
            raise IngestError("The file is not readable text.") from exc
    head = data[:16]
    if any(head.startswith(m) for m in BINARY_MAGIC) or b"\x00" in data[:4096]:
        raise IngestError("The file is not text (it looks like a picture, an archive or another binary file).")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("cp1252", "replace")  # an older text file written on Windows
    if text.count("\ufffd") > max(3, len(text) // 50):
        raise IngestError("The file is not readable text.")
    if len(_TEXT_CONTROL.findall(text)) > max(2, len(text) // 100):
        raise IngestError("The file is not readable text.")
    return text


MAX_PAGE_CONTENT_BYTES = 1_000_000  # a page whose drawing instructions are larger than this is not read: a crafted page can take seconds to parse
PRIVATE_NOTE_CHARS = 400
KINDS = {"invisible": "invisible (drawn with no ink)", "white": "white, or too pale to read on what is behind it", "tiny": "too small to read", "off_page": "outside the page or clipped away", "layer_off": "in a layer that is switched off", "slow": "on a page that took too long to follow safely"}


def note(kind: str, detail: str, private: str = "") -> dict:
    """One thing a reader of the file found, as stored on the resume. `detail` is plain words with nothing personal in it, so it can be shown while identity is hidden;
    `private` (file names, the hidden text itself) is shown only when identity is not hidden."""
    return {"kind": kind, "detail": detail[:400], "private": private[:2000]}


@dataclass
class ResumeRead:
    """What reading one resume file gave: the visible text, the text that was hidden in it (and left out), and the file itself when it is a PDF."""
    text: str
    hidden: list[str] = field(default_factory=list)
    hidden_kinds: list[str] = field(default_factory=list)
    skipped_pages: int = 0
    original: bytes = b""
    ocr_chars: int = 0  # characters read from the invisible text layer of a scanned page

    def notes(self) -> list[dict]:
        out: list[dict] = []
        if self.hidden:
            chars = sum(len(h) for h in self.hidden)
            kinds = ", ".join(KINDS[k] for k in dict.fromkeys(self.hidden_kinds))
            out.append(note("hidden_text", f"Hidden text found in the PDF: {chars} characters that are {kinds}. A person reading the page would not see them, so they were left out of scoring. Open the original file to look.", " | ".join(self.hidden)[:PRIVATE_NOTE_CHARS]))
        if self.ocr_chars:
            out.append(note("ocr_layer", f"Text layer of a scan, read by a person: {self.ocr_chars} characters came from the invisible text that a scanner lays over the picture of a page. A person cannot see these words on the page, and the scanner can misread them, so open the original file and compare the picture with the text."))
        if self.skipped_pages:
            out.append(note("pdf_page_skipped", f"{self.skipped_pages} page(s) of the PDF were not read because their drawing instructions are too large to read safely. Open the original file."))
        return out


def read_resume(data: bytes, filename: str) -> ResumeRead:
    """The text of a resume file (and, for a PDF, any hidden text found and left out). Raises IngestError for a file that is not a readable resume; for a PDF the error carries the file."""
    name = filename.lower()
    if len(data) > MAX_FILE_BYTES:
        raise IngestError("The file is larger than 5 MB.")
    hidden: list[str] = []
    kinds: list[str] = []
    skipped = ocr = 0
    keep = b""
    is_pdf = data[:5] == b"%PDF-" or name.endswith(".pdf")
    if is_pdf:
        try:
            text, hidden, kinds, skipped, ocr = _pdf_read_full(data)
        except IngestError as exc:
            raise IngestError(str(exc), data) from exc
        keep = data
    elif name.endswith(WORD_PROCESSOR_EXTENSIONS):
        raise IngestError(NOT_READ_WORD)
    elif data[:5] == b"{\\rtf":
        text = _rtf_to_text(data)
    else:
        text = _decode_text(data)
    text = _CONTROL_OUT.sub("", text.replace("\r\n", "\n").replace("\r", "\n")).strip()
    if len(text) < 40:
        raise IngestError("The file has too little text to read. Scanned images are not read.", keep)
    return ResumeRead(text[:MAX_TEXT], hidden, kinds, skipped, keep, ocr)


def text_from_bytes(data: bytes, filename: str) -> str:
    return read_resume(data, filename).text


_CONTROL_OUT = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _page_bytes(page) -> int:
    """The size of a page's drawing instructions as they are stored in the file, without decoding them."""
    try:
        contents = page.get("/Contents")
        contents = contents.get_object() if contents is not None else None
        parts = contents if isinstance(contents, list) else [contents] if contents is not None else []
        total = 0
        for p in parts:
            obj = p.get_object()
            raw = getattr(obj, "_data", None)  # the stream as stored in the file (still compressed), counted without decoding it
            length = len(raw) if isinstance(raw, (bytes, bytearray)) else obj.get("/Length", 0)
            length = length.get_object() if hasattr(length, "get_object") else length
            total += int(length or 0)
        return total
    except Exception:  # noqa: BLE001 - an odd page is read, and the time limit still applies
        return 0


def _pdf_read_full(data: bytes) -> tuple[str, list[str], list[str], int, int]:
    """(the text, the hidden pieces left out, why each is hidden, pages skipped, characters of a scan's text layer). What counts as hidden is decided in pdfink.py."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        root = reader.trailer["/Root"]
        started, pages, hidden, why, skipped, ocr = time.monotonic(), [], [], [], 0, 0
        for page in reader.pages[:MAX_PDF_PAGES]:
            if time.monotonic() - started > MAX_PDF_SECONDS:  # a page that is slow to read stops the rest: the pages read so far are the resume
                break
            if _page_bytes(page) > MAX_PAGE_CONTENT_BYTES:
                skipped += 1
                continue
            got = pdfink.read_page(page, root)
            pages.append(got.text)
            hidden += got.hidden
            why += got.why
            ocr += got.ocr_chars
        return "\n".join(pages), hidden, why, skipped, ocr
    except Exception as exc:  # noqa: BLE001 - a bad file is a clean error, never a crash
        raise IngestError("The PDF could not be read.") from exc


def _pdf_read(data: bytes) -> tuple[str, list[str], list[str], int]:
    text, hidden, why, skipped, _ocr = _pdf_read_full(data)
    return text, hidden, why, skipped


def from_csv(data: bytes, resumes: dict[str, bytes] | None = None) -> list[Applicant]:
    """Columns: name, email, phone, role, resume_text or resume_file (looked up in `resumes`), source, school. Any other column is ignored."""
    try:
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise IngestError("The CSV could not be read as UTF-8 text.") from exc
    if len(rows) > MAX_ROWS:
        raise IngestError(f"Use at most {MAX_ROWS} rows per file.")
    out = []
    for i, r in enumerate(rows, 2):
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
        name = r.get("name") or ""
        if not name:
            raise IngestError(f"Row {i}: the name column is empty.")
        text, fname = r.get("resume_text", ""), r.get("resume_file", "")
        if not text and fname and resumes and fname in resumes:
            text = text_from_bytes(resumes[fname], fname)
        out.append(Applicant(name, r.get("email", ""), r.get("phone", ""), r.get("role", ""), text, fname, r.get("source", "csv"), r.get("school", "")))  # a code column is ignored: an outside reference taken from a file would let one file suppress another's applicants
    return out


SUBJECT_ROLE = re.compile(r"application(?:\s+for)?\s*[:\-]?\s*(.+)$", re.I)


def match_role(subject: str, role_titles: dict[str, str] | None) -> tuple[str, list[str]]:
    """The role a subject names: (key, []) for one clear match, ("", titles) when it fits more than one role (a person decides, nothing is guessed), ("", []) for none.
    A key or a whole title that is typed exactly wins over a longer title that merely contains the words."""
    m = SUBJECT_ROLE.search(subject or "")
    if not m or not role_titles:
        return "", []
    want = m.group(1).strip().lower()
    exact = [k for k, t in role_titles.items() if k.lower() == want or t.lower() == want]
    if len(exact) == 1:
        return exact[0], []
    loose = [k for k, t in role_titles.items() if want and (t.lower() in want or want in t.lower())]
    if len(loose) == 1:
        return loose[0], []
    return "", [role_titles[k] for k in loose]


def sender_of(raw: bytes) -> str:
    """The sender address of a message, or an empty string. Never raises: it is used to say who a message was from when the message itself cannot be read."""
    try:
        msg = email.message_from_bytes(raw, policy=policy.default)
        return email.utils.parseaddr(str(msg.get("From", "")))[1][:254]
    except Exception:  # noqa: BLE001 - a broken message must still be reported
        return ""


def _body_text(msg) -> str:
    body = msg.get_body(preferencelist=("plain",))
    if body is None:
        return ""
    try:
        return body.get_content().strip()
    except (LookupError, UnicodeError, ValueError):  # an unregistered character set: read the bytes as text instead of failing the whole message
        return (body.get_payload(decode=True) or b"").decode("utf-8", "replace").strip()


def _attachments(msg) -> list[tuple[str, bytes]]:
    out = []
    for part in msg.walk():
        fn = part.get_filename()
        if fn and not part.is_multipart():
            out.append((fn, part.get_payload(decode=True) or b""))
    return out


NAME_FIRST = re.compile(r"(?:^|[^a-z])(cv|resume|r[eé]sum[eé]|curriculum|vitae)(?:[^a-z]|$)", re.I)
NAME_LAST = re.compile(r"cover|letter|signature|sig\b|note|reference|portfolio|transcript|certificate|photo|logo|invite|vcard", re.I)
MAX_FILES_TRIED = 6  # a message with more attachments than this is read for its first six only


def _rank(fn: str) -> int:
    """0 for a file whose name says it is the resume, 2 for one whose name says it is something else (a cover letter, a signature), 1 for the rest."""
    base = fn.rsplit("/", 1)[-1]
    return 0 if NAME_FIRST.search(base) else 2 if NAME_LAST.search(base) else 1


def _resume_from_attachments(msg) -> tuple[ResumeRead | None, str, str, list[dict], bytes]:
    """(what was read, the file name, why nothing was readable, notes, the first PDF that could not be read). Only files that can be a resume are tried (at most six). Every readable one is read, and the one used is the one
    whose name says resume, cv or curriculum, then the largest text: a cover letter or a signature that comes first is never the resume just for being first. When more than one file
    was readable the choice is written down, with the reason, so a person can see which file was scored. Nothing that is not text is ever decoded as text."""
    unreadable, lost = "", b""
    readable: list[tuple[str, ResumeRead]] = []
    for fn, data in _attachments(msg):
        if not (is_resume_name(fn) or fn.lower().endswith(WORD_PROCESSOR_EXTENSIONS) or data[:5] == b"%PDF-"):
            continue
        if len(readable) + (1 if unreadable else 0) >= MAX_FILES_TRIED:
            break
        try:
            readable.append((fn, read_resume(data, fn)))
        except IngestError as exc:
            unreadable = unreadable or str(exc)
            lost = lost or exc.original  # an image only PDF is not read, but a person can open it
    if not readable:
        return None, "", unreadable, [], lost
    ranked = sorted(readable, key=lambda x: (_rank(x[0]), -len(x[1].text)))
    fn, got = ranked[0]
    notes: list[dict] = []
    if len(readable) > 1:
        why = "its name says it is the resume" if _rank(fn) == 0 else "its name does not say it is something else, and it has the most text" if _rank(fn) == 1 else "every file name looked like something else, so the one with the most text was used"
        others = [n for n, _r in ranked[1:]]
        notes.append(note("attachment_choice", f"{len(readable)} readable files came with this email. One was scored because {why}. The other {len(others)} were not read as the resume. Check that the right file was used.", f"Scored: {fn}. Not scored: {', '.join(others)}."))
    return got, fn, unreadable, notes, lost


def from_email(raw: bytes, role_titles: dict[str, str] | None = None, *, keep_unreadable: bool = False) -> Applicant:
    """An application email: sender is the applicant, the subject names the role, an attachment or the body is the resume.
    With `keep_unreadable` a message whose resume cannot be read still gives an applicant, marked with extra["resume_missing"], so a person sees it."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    name, addr = email.utils.parseaddr(str(msg.get("From", "")))
    if not addr:
        raise IngestError("The message has no sender.")
    role_key, ambiguous = match_role(str(msg.get("Subject", "")), role_titles)
    extra = {"role_ambiguous": ambiguous} if ambiguous else {}
    got, fname, unreadable, notes, lost = _resume_from_attachments(msg)
    ref = str(msg.get("Message-ID", "")) or None
    who = name or addr.split("@")[0]
    body = ""
    if got is None and not unreadable:  # nothing that could be a resume was attached: the body is the resume
        body = _body_text(msg)
        if len(body) >= 40:
            return Applicant(who, addr, "", role_key, body[:MAX_TEXT], "", "email", external_ref=ref, extra=extra)
    if got is None:
        if not keep_unreadable:
            raise IngestError(unreadable or "The email has no resume attached and too little text in the body.")
        body = body or _body_text(msg)
        if unreadable and len(body) >= 40:  # a file that cannot be read was attached AND the email has text: that text is not scored as the resume, but it is kept for a person to read
            notes = [*notes, note("body_not_used", f"The attached file could not be read and the email has {len(body)} characters of text. The email text was not scored as the resume, because a cover note is not a resume. Read it, and ask the applicant for a PDF or text version.", body[:2000])]
        return Applicant(who, addr, "", role_key, MISSING_RESUME, fname, "email", external_ref=ref, extra={**extra, "resume_missing": unreadable or "no resume", "notes": notes}, original=lost)
    return Applicant(who, addr, "", role_key, got.text[:MAX_TEXT], fname, "email", external_ref=ref, extra={**extra, "notes": [*got.notes(), *notes]}, original=got.original)
