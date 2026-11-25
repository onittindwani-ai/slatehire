"""Mailbox adapters: read application emails. Reading only; Slatehire never sends email."""

from __future__ import annotations

import imaplib
import ssl

from slatehire.config import is_loopback
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

    def fetch_new(self, limit: int = 50) -> list[tuple[str, bytes]]:
        m = self._open()
        try:
            _t, data = m.uid("SEARCH", None, "UNSEEN", "SUBJECT", f'"{APPLICATION_WORD}"')  # the server filters: a colleague's unread mail is never even fetched
            uids = (data[0] or b"").split()[:limit]
            out = []
            for u in uids:
                _t, parts = m.uid("FETCH", u, "(BODY.PEEK[])")  # PEEK: reading a message must not mark it read
                for p in parts:
                    if isinstance(p, tuple):
                        out.append((u.decode(), p[1]))
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
