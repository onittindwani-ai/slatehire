"""A tiny mock SMTP and IMAP server for tests and the demo. Not a real mail server.

SMTP: EHLO, AUTH PLAIN, MAIL, RCPT, DATA, RSET, NOOP, QUIT. Accepted messages land in `MailStore.outbox`.
IMAP: CAPABILITY, LOGIN, SELECT, UID SEARCH (ALL, UNSEEN, SUBJECT "text", case blind like a real server), UID FETCH (RFC822), UID STORE (flags), NOOP, LOGOUT.
Messages in `MailStore.inbox` are what the IMAP client sees. It speaks only what Python's smtplib and imaplib send.
"""

from __future__ import annotations

import re
import socketserver
import threading
from dataclasses import dataclass, field


@dataclass
class MailStore:
    outbox: list[dict] = field(default_factory=list)  # accepted by SMTP: {"from","to","data"}
    inbox: list[dict] = field(default_factory=list)  # visible to IMAP: {"uid","raw","seen"}
    lock: threading.Lock = field(default_factory=threading.Lock)
    users: dict[str, str] = field(default_factory=lambda: {"demo": "demo-password"})

    def deliver(self, raw: bytes) -> int:
        with self.lock:
            uid = len(self.inbox) + 1
            self.inbox.append({"uid": uid, "raw": raw, "seen": False})
            return uid


def _subject(raw: bytes) -> str:
    """The Subject header of a stored message, decoded the way a mail server compares it."""
    from email import message_from_bytes, policy

    return str(message_from_bytes(raw, policy=policy.default).get("Subject", ""))


class _SMTP(socketserver.StreamRequestHandler):
    store: MailStore

    def _w(self, line: str) -> None:
        self.wfile.write((line + "\r\n").encode())
        self.wfile.flush()

    def handle(self) -> None:
        self._w("220 stub-smtp ready")
        mail_from, rcpts = "", []
        while True:
            line = self.rfile.readline().decode(errors="replace").rstrip("\r\n")
            if not line:
                return
            cmd = line.split(" ", 1)[0].upper()
            if cmd in ("EHLO", "HELO"):
                self.wfile.write(b"250-stub-smtp\r\n250 AUTH PLAIN\r\n")
                self.wfile.flush()
            elif cmd == "AUTH":
                self._w("235 ok")
            elif cmd == "MAIL":
                mail_from, rcpts = line.split(":", 1)[1].strip().strip("<>").split(">")[0], []
                self._w("250 ok")
            elif cmd == "RCPT":
                rcpts.append(line.split(":", 1)[1].strip().strip("<>").split(">")[0])
                self._w("250 ok")
            elif cmd == "DATA":
                self._w("354 end with a dot")
                chunks = []
                while True:
                    row = self.rfile.readline()
                    if row in (b".\r\n", b".\n", b""):
                        break
                    chunks.append(row[1:] if row.startswith(b"..") else row)
                with self.store.lock:
                    self.store.outbox.append({"from": mail_from, "to": list(rcpts), "data": b"".join(chunks).decode(errors="replace")})
                self._w("250 queued")
            elif cmd in ("RSET", "NOOP"):
                self._w("250 ok")
            elif cmd == "QUIT":
                self._w("221 bye")
                return
            else:
                self._w("502 not supported")


class _IMAP(socketserver.StreamRequestHandler):
    store: MailStore

    def _w(self, data: bytes) -> None:
        self.wfile.write(data)
        self.wfile.flush()

    def handle(self) -> None:
        self._w(b"* OK stub-imap ready\r\n")
        authed = False
        while True:
            raw = self.rfile.readline().decode(errors="replace").strip()
            if not raw:
                return
            tag, _, rest = raw.partition(" ")
            cmd, _, arg = rest.partition(" ")
            cmd = cmd.upper()
            if cmd == "CAPABILITY":
                self._w(b"* CAPABILITY IMAP4rev1\r\n" + tag.encode() + b" OK done\r\n")
            elif cmd == "LOGIN":
                m = re.findall(r'"([^"]*)"|(\S+)', arg)
                user, pw = (m[0][0] or m[0][1]), (m[1][0] or m[1][1])
                if self.store.users.get(user) == pw:
                    authed = True
                    self._w(tag.encode() + b" OK logged in\r\n")
                else:
                    self._w(tag.encode() + b" NO invalid credentials\r\n")
            elif cmd == "SELECT" and authed:
                n = len(self.store.inbox)
                self._w(f"* {n} EXISTS\r\n* 0 RECENT\r\n{tag} OK [READ-WRITE] selected\r\n".encode())
            elif cmd == "UID" and authed:
                sub, _, a2 = arg.partition(" ")
                sub = sub.upper()
                if sub == "SEARCH":
                    with self.store.lock:
                        want = re.search(r'SUBJECT\s+(?:"([^"]*)"|(\S+))', a2, re.I)
                        needle = ((want.group(1) if want.group(1) is not None else want.group(2)) if want else "").lower()
                        smaller = re.search(r"SMALLER\s+(\d+)", a2, re.I)
                        larger = re.search(r"LARGER\s+(\d+)", a2, re.I)
                        uids = [m["uid"] for m in self.store.inbox if ("UNSEEN" not in a2.upper() or not m["seen"]) and (not needle or needle in _subject(m["raw"]).lower())
                                and (smaller is None or len(m["raw"]) < int(smaller.group(1))) and (larger is None or len(m["raw"]) > int(larger.group(1)))]
                    self._w(("* SEARCH " + " ".join(map(str, uids))).strip().encode() + b"\r\n" + tag.encode() + b" OK done\r\n")
                elif sub == "FETCH" and "RFC822.SIZE" in a2.upper():
                    wanted = {int(x) for x in a2.split(" ", 1)[0].split(",") if x.isdigit()}
                    with self.store.lock:
                        rows = [(m["uid"], len(m["raw"])) for m in self.store.inbox if m["uid"] in wanted]
                    self._w("".join(f"* {u} FETCH (UID {u} RFC822.SIZE {n})\r\n" for u, n in rows).encode() + tag.encode() + b" OK done\r\n")
                elif sub == "FETCH":
                    uid = int(a2.split(" ", 1)[0])
                    with self.store.lock:
                        msg = next((m for m in self.store.inbox if m["uid"] == uid), None)
                    if msg is not None and "HEADER" in a2.upper():  # only the header lines, as BODY.PEEK[HEADER.FIELDS (...)] asks
                        head = msg["raw"].split(b"\r\n\r\n", 1)[0].split(b"\n\n", 1)[0] + b"\r\n\r\n"
                        self._w(f"* {uid} FETCH (UID {uid} BODY[HEADER.FIELDS (FROM)] {{{len(head)}}}\r\n".encode() + head + b")\r\n" + tag.encode() + b" OK done\r\n")
                    elif msg is None:
                        self._w(tag.encode() + b" OK done\r\n")
                    else:
                        body = msg["raw"]
                        peek = "PEEK" in a2.upper()
                        if not peek:  # RFC 3501 6.4.5: fetching RFC822 or BODY[] sets \\Seen on the server; only BODY.PEEK[] leaves the message unread
                            with self.store.lock:
                                msg["seen"] = True
                        label = "BODY[]" if "BODY" in a2.upper() else "RFC822"
                        self._w(f"* {uid} FETCH (UID {uid} {label} {{{len(body)}}}\r\n".encode() + body + b")\r\n" + tag.encode() + b" OK done\r\n")
                elif sub == "STORE":
                    uid = int(a2.split(" ", 1)[0])
                    with self.store.lock:
                        for m in self.store.inbox:
                            if m["uid"] == uid and "\\Seen" in a2:
                                m["seen"] = True
                    self._w(f"* {uid} FETCH (FLAGS (\\Seen))\r\n{tag} OK done\r\n".encode())
                else:
                    self._w(tag.encode() + b" BAD unsupported\r\n")
            elif cmd == "NOOP":
                self._w(tag.encode() + b" OK done\r\n")
            elif cmd == "LOGOUT":
                self._w(b"* BYE\r\n" + tag.encode() + b" OK bye\r\n")
                return
            else:
                self._w(tag.encode() + b" BAD unsupported\r\n")


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class StubMailServers:
    """Starts both servers on free local ports. Use as a context manager."""

    def __init__(self, store: MailStore | None = None, host: str = "127.0.0.1", smtp_port: int = 0, imap_port: int = 0):
        self.store = store or MailStore()
        smtp_h = type("SMTPH", (_SMTP,), {"store": self.store})
        imap_h = type("IMAPH", (_IMAP,), {"store": self.store})
        self._smtp, self._imap = _Server((host, smtp_port), smtp_h), _Server((host, imap_port), imap_h)
        self.host = host
        self.smtp_port, self.imap_port = self._smtp.server_address[1], self._imap.server_address[1]
        self._threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (self._smtp, self._imap)]

    def __enter__(self) -> StubMailServers:
        for t in self._threads:
            t.start()
        return self

    def __exit__(self, *exc) -> None:
        for s in (self._smtp, self._imap):
            s.shutdown()
            s.server_close()


if __name__ == "__main__":  # python -m mock.mail_servers
    with StubMailServers(smtp_port=2525, imap_port=1143) as srv:
        print(f"mock smtp on {srv.smtp_port}, mock imap on {srv.imap_port} (user demo, password demo-password). Ctrl C to stop.")
        threading.Event().wait()
