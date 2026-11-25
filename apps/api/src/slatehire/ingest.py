"""Turn files, CSV rows and email messages into applicant records. Pure parsing, no database."""

from __future__ import annotations

import csv
import email
import io
import re
from dataclasses import dataclass, field
from email import policy

MAX_TEXT = 60_000
MAX_ROWS = 2000
MAX_FILE_BYTES = 5_000_000
# What stands in for a resume that could not be read (an image only PDF, a broken attachment, an empty email). The applicant still enters the process,
# flagged, so a person can ask for another file instead of the person silently never existing.
MISSING_RESUME = "[No readable resume was received. Ask the applicant for a text or PDF version.]"
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


def text_from_bytes(data: bytes, filename: str) -> str:
    name = filename.lower()
    if len(data) > MAX_FILE_BYTES:
        raise IngestError("The file is larger than 5 MB.")
    if name.endswith(".pdf") or data[:5] == b"%PDF-":
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((p.extract_text() or "") for p in reader.pages[:12])
        except Exception as exc:  # noqa: BLE001 - a bad file is a clean error, never a crash
            raise IngestError("The PDF could not be read.") from exc
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) < 40:
        raise IngestError("The file has too little text to read. Scanned images are not read.")
    return text[:MAX_TEXT]


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


def from_email(raw: bytes, role_titles: dict[str, str] | None = None, *, keep_unreadable: bool = False) -> Applicant:
    """An application email: sender is the applicant, the subject names the role, an attachment or the body is the resume.
    With `keep_unreadable` a message whose resume cannot be read still gives an applicant, marked with extra["resume_missing"], so a person sees it."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    name, addr = email.utils.parseaddr(str(msg.get("From", "")))
    if not addr:
        raise IngestError("The message has no sender.")
    subject = str(msg.get("Subject", ""))
    role_key = ""
    m = SUBJECT_ROLE.search(subject)
    if m and role_titles:
        want = m.group(1).strip().lower()
        role_key = next((k for k, t in role_titles.items() if t.lower() in want or want in t.lower() or k == want), "")
    text, fname, unreadable = "", "", ""
    for part in msg.walk():
        fn = part.get_filename()
        if fn and not text:
            try:
                text, fname = text_from_bytes(part.get_payload(decode=True) or b"", fn), fn
            except IngestError as exc:
                unreadable = str(exc)
    if not text:
        text = _body_text(msg)
        if len(text) < 40:
            if not keep_unreadable:
                raise IngestError(unreadable or "The email has no resume attached and too little text in the body.")
            return Applicant(name or addr.split("@")[0], addr, "", role_key, MISSING_RESUME, fname, "email", external_ref=str(msg.get("Message-ID", "")) or None, extra={"resume_missing": unreadable or "no resume"})
    return Applicant(name or addr.split("@")[0], addr, "", role_key, text[:MAX_TEXT], fname, "email", external_ref=str(msg.get("Message-ID", "")) or None)
