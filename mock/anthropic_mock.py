"""A local fake of the Anthropic Messages endpoint, standard library only. It records every request so a test can assert the
request shape, and it answers from a script or from a function.

It is NOT the real API and proves nothing about how a real model reads a reply. Live use stays UNVERIFIED.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def ok(text: str, model: str = "claude-haiku-5-5", stop: str = "end_turn", tin: int = 150, tout: int = 40) -> dict:
    return {"id": "msg_fake", "type": "message", "role": "assistant", "model": model, "stop_reason": stop,
            "content": [{"type": "text", "text": text}], "usage": {"input_tokens": tin, "output_tokens": tout}}


class FakeAnthropic:
    """`script` answers in order (status, headers, body). `responder(request_body) -> text` answers every call when the script is empty."""

    def __init__(self, responder: Callable[[dict], str] | None = None):
        self.requests: list[dict] = []
        self.script: list[tuple[int, dict, dict | str]] = []
        self.responder = responder
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 (name set by the standard library)
                raw = self.rfile.read(int(self.headers.get("content-length", 0)))
                body = json.loads(raw)
                outer.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
                if outer.script:
                    status, headers, payload = outer.script.pop(0)
                elif outer.responder:
                    status, headers, payload = 200, {}, ok(outer.responder(body), model=body.get("model", "claude-haiku-5-5"))
                else:
                    status, headers, payload = 200, {}, ok("{}")
                data = (payload if isinstance(payload, str) else json.dumps(payload)).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("request-id", "req_fake123")
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
