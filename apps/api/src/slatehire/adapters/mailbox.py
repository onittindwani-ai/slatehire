"""Mailbox adapters: read application emails. Reading only; Slatehire never sends email."""

from __future__ import annotations

import imaplib
import re
import ssl

from slatehire.config import is_loopback
from slatehire.ingest import sender_of
from sendora_core.adapters import AdapterError


class SeedMailbox:
    name = "seed"

    def __init__(self, settings):
        self.s = settings

    def fetch_new(self, limit: int = 50) -> list[tuple[str, bytes]]:
        return []

    def mark_seen(self, uid: str) -> None:
        return None

    def mark_seen_many(self, uids: list[str]) -> None:
        return None

    skipped: list[tuple[str, str, int]] = []

    def healthcheck(self):
        return True, "Offline demo adapter."


APPLICATION_WORD = "Application"  # the server is asked for unread mail whose subject has this word: every other message in a shared mailbox is never fetched, stored or marked read


class ImapMailbox:
    """IMAP (Gmail with an app password, Outlook, any host). Reads unseen messages whose subject has the word Application, WITHOUT marking them read (BODY.PEEK[], never RFC822, which sets the
    seen flag on the server the moment it is fetched), and marks them seen only after the caller stored them. The connection checks the server's certificate
    and host name; plain text is accepted only for a mail server on this same computer."""

    name = "imap"

    def __init__(self, settings):
        if not (settings.imap_host and settings.imap_user and settings.imap_password):
            raise AdapterError("IMAP_HOST, IMAP_USER and IMAP_PASSWORD must all be set.")
        self.s = settings

    def _open(self):
        s = self.s
        if not s.imap_use_ssl and not is_loopback(s.imap_host):
            raise AdapterError("IMAP_USE_SSL=false is only allowed for a mail server on this same computer (127.0.0.1). Turn it back on.")
        try:
            if s.imap_use_ssl:
                m = imaplib.IMAP4_SSL(s.imap_host, s.imap_port, ssl_context=ssl.create_default_context(), timeout=20)
            else:
                m = imaplib.IMAP4(s.imap_host, s.imap_port, timeout=20)
            m.login(s.imap_user, s.imap_password)
            m.select("INBOX")
            return m
        except ssl.SSLCertVerificationError as exc:
            raise AdapterError(f"The certificate of {s.imap_host} could not be verified, so the mailbox was not read. Check IMAP_HOST and the port.") from exc
        except (imaplib.IMAP4.error, OSError) as exc:
            raise AdapterError("Could not sign in to the mailbox. Check the host, port, user and password.") from exc

    skipped: list[tuple[str, str, int]] = []  # (uid, sender, size) of the unread application mails the last fetch_new did NOT download because they are over IMAP_MAX_MESSAGE_BYTES

    @staticmethod
    def _uids(data) -> list[bytes]:
        return (data[0] or b"").split() if data else []

    def _sizes(self, m, uids: list[bytes]) -> dict[bytes, int]:
        """The size of each message, asked of the server before any message is downloaded."""
        if not uids:
            return {}
        _t, parts = m.uid("FETCH", b",".join(uids).decode(), "(RFC822.SIZE)")
        out: dict[bytes, int] = {}
        for p in parts or []:
            line = p if isinstance(p, bytes) else p[0] if isinstance(p, tuple) else b""
            uid, size = re.search(rb"UID (\d+)", line), re.search(rb"RFC822\.SIZE (\d+)", line)
            if uid and size:
                out[uid.group(1)] = int(size.group(1))
        return out

    def fetch_new(self, limit: int = 50) -> list[tuple[str, bytes]]:
        """Unread application mails, smallest first in the order the server lists them. A message over IMAP_MAX_MESSAGE_BYTES is never downloaded (only its sender is read) and is listed in
        `skipped`; the bytes held in one run stop at IMAP_MAX_RUN_BYTES, and what is left waits, unread, for the next run."""
        max_one, max_run = int(self.s.imap_max_message_bytes), int(self.s.imap_max_run_bytes)
        m = self._open()
        self.skipped = []
        try:
            base = ("UNSEEN", "SUBJECT", f'"{APPLICATION_WORD}"')  # the server filters: a colleague's unread mail is never even fetched
            _t, small = m.uid("SEARCH", None, *base, "SMALLER", str(max_one + 1))
            _t, large = m.uid("SEARCH", None, *base, "LARGER", str(max_one))
            for u in self._uids(large)[:limit]:
                size = self._sizes(m, [u]).get(u, 0)
                _t, parts = m.uid("FETCH", u.decode(), "(BODY.PEEK[HEADER.FIELDS (FROM)])")  # the sender only, never the body
                head = next((p[1] for p in parts or [] if isinstance(p, tuple)), b"")
                self.skipped.append((u.decode(), sender_of(head), size))
            uids = self._uids(small)[:limit]
            sizes = self._sizes(m, uids)
            out, held = [], 0
            for u in uids:
                if out and held + sizes.get(u, 0) > max_run:
                    break  # the rest stays unread and is met on the next run
                _t, parts = m.uid("FETCH", u, "(BODY.PEEK[])")  # PEEK: reading a message must not mark it read
                for p in parts:
                    if isinstance(p, tuple):
                        out.append((u.decode(), p[1]))
                        held += len(p[1])
            return out
        except (imaplib.IMAP4.error, OSError) as exc:
            raise AdapterError("The mailbox could not be read.") from exc
        finally:
            try:
                m.logout()
            except Exception:  # noqa: BLE001
                pass

    def mark_seen(self, uid: str) -> None:
        self.mark_seen_many([uid])

    def mark_seen_many(self, uids: list[str]) -> None:
        if not uids:
            return
        m = self._open()
        try:
            for uid in uids:
                m.uid("STORE", uid, "+FLAGS", "(\\Seen)")
        except (imaplib.IMAP4.error, OSError) as exc:
            raise AdapterError("The mailbox did not accept the read marks.") from exc
        finally:
            m.logout()

    def healthcheck(self):
        try:
            self._open().logout()
            return True, "Connected."
        except AdapterError as exc:
            return False, str(exc)
