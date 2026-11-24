"""A local fake of the Anthropic Messages endpoint, standard library only. It records every request so tests can
assert the request shape against the documented API. It is NOT the real API and proves nothing about live behaviour."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeAnthropic:
    def __init__(self):
        self.requests: list[dict] = []
        self.script: list[tuple[int, dict, dict | str]] = []  # (status, extra headers, body)
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("content-length", 0))
                raw = self.rfile.read(n)
                outer.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": json.loads(raw)})
                status, headers, body = outer.script.pop(0) if outer.script else (200, {}, ok("{}"))
                data = body if isinstance(body, str) else json.dumps(body)
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("request-id", "req_fake123")
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("content-length", str(len(data.encode())))
                self.end_headers()
                self.wfile.write(data.encode())

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.server.shutdown()
        self.server.server_close()


def ok(text: str, stop: str = "end_turn", tin: int = 120, tout: int = 40, model: str = "claude-sonnet-5-5") -> dict:
    return {"id": "msg_fake", "type": "message", "role": "assistant", "model": model, "stop_reason": stop,
            "content": [{"type": "thinking", "thinking": "hidden", "signature": "x"}, {"type": "text", "text": text}],
            "usage": {"input_tokens": tin, "output_tokens": tout}}


def err(kind: str, message: str = "nope") -> dict:
    return {"type": "error", "error": {"type": kind, "message": message}, "request_id": "req_fake123"}
