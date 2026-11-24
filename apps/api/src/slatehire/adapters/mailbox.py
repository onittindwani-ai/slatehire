"""Mailbox adapters: read application emails. Reading only; Slatehire never sends email."""

from __future__ import annotations

import imaplib

from sendora_core.adapters import AdapterError


class SeedMailbox:
    name = "seed"

    def __init__(self, settings):
        self.s = settings

    def fetch_new(self, limit: int = 50) -> list[tuple[str, bytes]]:
        return []

    def mark_seen(self, uid: str) -> None:
        return None

    def healthcheck(self):
        return True, "Offline demo adapter."


class ImapMailbox:
    """Plain IMAP (Gmail with an app password, Outlook, any host). Reads unseen messages, marks a message seen only after it was handled."""

    name = "imap"

    def __init__(self, settings):
        if not (settings.imap_host and settings.imap_user and settings.imap_password):
            raise AdapterError("IMAP_HOST, IMAP_USER and IMAP_PASSWORD must all be set.")
        self.s = settings

    def _open(self):
        s = self.s
        try:
            m = imaplib.IMAP4_SSL(s.imap_host, s.imap_port, timeout=20) if s.imap_use_ssl else imaplib.IMAP4(s.imap_host, s.imap_port, timeout=20)
            m.login(s.imap_user, s.imap_password)
            m.select("INBOX")
            return m
        except (imaplib.IMAP4.error, OSError) as exc:
            raise AdapterError("Could not sign in to the mailbox. Check the host, port, user and password.") from exc

    def fetch_new(self, limit: int = 50) -> list[tuple[str, bytes]]:
        m = self._open()
        try:
            _t, data = m.uid("SEARCH", None, "UNSEEN")
            uids = (data[0] or b"").split()[:limit]
            out = []
            for u in uids:
                _t, parts = m.uid("FETCH", u, "(RFC822)")
                for p in parts:
                    if isinstance(p, tuple):
                        out.append((u.decode(), p[1]))
            return out
        finally:
            try:
                m.logout()
            except Exception:  # noqa: BLE001
                pass

    def mark_seen(self, uid: str) -> None:
        m = self._open()
        try:
            m.uid("STORE", uid, "+FLAGS", "(\\Seen)")
        finally:
            m.logout()

    def healthcheck(self):
        try:
            self._open().logout()
            return True, "Connected."
        except AdapterError as exc:
            return False, str(exc)
