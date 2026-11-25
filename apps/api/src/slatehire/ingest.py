"""Turn files, CSV rows and email messages into applicant records. Pure parsing, no database."""

from __future__ import annotations

import csv
import email
import io
import re
import time
from dataclasses import dataclass, field
from email import policy

MAX_TEXT = 60_000
MAX_ROWS = 2000
MAX_FILE_BYTES = 5_000_000
MAX_PDF_PAGES = 12
MAX_PDF_SECONDS = 10.0
# What stands in for a resume that could not be read (an image only PDF, a broken attachment, an empty email). The applicant still enters the process,
# flagged, so a person can ask for another file instead of the person silently never existing.
MISSING_RESUME = "[No readable resume was received. Ask the applicant for a text or PDF version.]"
LANGUAGE_NOTE = "Not scored: language. The resume does not look like English, and the scorer reads English words only, so it would show no evidence for everything. A person reads this resume and decides; it can be shortlisted without a score."
RESUME_MISSING_NOTE = "Resume missing: no readable resume arrived (an image only PDF, a damaged file or an empty email). Ask the applicant to send a text or PDF version. Nothing was scored."


class IngestError(ValueError):
    pass


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
    extra: dict = field(default_factory=dict)


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


def text_from_bytes(data: bytes, filename: str) -> str:
    name = filename.lower()
    if len(data) > MAX_FILE_BYTES:
        raise IngestError("The file is larger than 5 MB.")
    if data[:5] == b"%PDF-" or name.endswith(".pdf"):
        text = _pdf_text(data)
    elif name.endswith(WORD_PROCESSOR_EXTENSIONS):
        raise IngestError(NOT_READ_WORD)
    elif data[:5] == b"{\\rtf":
        text = _rtf_to_text(data)
    else:
        text = _decode_text(data)
    text = _CONTROL_OUT.sub("", text.replace("\r\n", "\n").replace("\r", "\n")).strip()
    if len(text) < 40:
        raise IngestError("The file has too little text to read. Scanned images are not read.")
    return text[:MAX_TEXT]


_CONTROL_OUT = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        started, pages = time.monotonic(), []
        for page in reader.pages[:MAX_PDF_PAGES]:
            if time.monotonic() - started > MAX_PDF_SECONDS:  # a page that is slow to read stops the rest: the pages read so far are the resume
                break
            pages.append(page.extract_text() or "")
        return "\n".join(pages)
    except Exception as exc:  # noqa: BLE001 - a bad file is a clean error, never a crash
        raise IngestError("The PDF could not be read.") from exc


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


def _resume_from_attachments(msg) -> tuple[str, str, str]:
    """(text, file name, why nothing was readable). Only files that can be a resume are tried, in order, and the first one that gives text wins: a signature picture or a calendar
    invite that comes first is passed over, and nothing that is not text is ever decoded as text."""
    unreadable = ""
    for fn, data in _attachments(msg):
        if not (is_resume_name(fn) or fn.lower().endswith(WORD_PROCESSOR_EXTENSIONS) or data[:5] == b"%PDF-"):
            continue
        try:
            return text_from_bytes(data, fn), fn, ""
        except IngestError as exc:
            unreadable = unreadable or str(exc)
    return "", "", unreadable


def from_email(raw: bytes, role_titles: dict[str, str] | None = None, *, keep_unreadable: bool = False) -> Applicant:
    """An application email: sender is the applicant, the subject names the role, an attachment or the body is the resume.
    With `keep_unreadable` a message whose resume cannot be read still gives an applicant, marked with extra["resume_missing"], so a person sees it."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    name, addr = email.utils.parseaddr(str(msg.get("From", "")))
    if not addr:
        raise IngestError("The message has no sender.")
    role_key, ambiguous = match_role(str(msg.get("Subject", "")), role_titles)
    extra = {"role_ambiguous": ambiguous} if ambiguous else {}
    text, fname, unreadable = _resume_from_attachments(msg)
    ref = str(msg.get("Message-ID", "")) or None
    who = name or addr.split("@")[0]
    if not text and not unreadable:  # nothing that could be a resume was attached: the body is the resume
        body = _body_text(msg)
        if len(body) >= 40:
            return Applicant(who, addr, "", role_key, body[:MAX_TEXT], "", "email", external_ref=ref, extra=extra)
    if not text:
        if not keep_unreadable:
            raise IngestError(unreadable or "The email has no resume attached and too little text in the body.")
        return Applicant(who, addr, "", role_key, MISSING_RESUME, fname, "email", external_ref=ref, extra={**extra, "resume_missing": unreadable or "no resume"})
    return Applicant(who, addr, "", role_key, text[:MAX_TEXT], fname, "email", external_ref=ref, extra=extra)
