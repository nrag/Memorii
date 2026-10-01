"""Deterministic offline OpenAI-compatible provider for certification journeys.

Serves POST /v1/chat/completions (streaming and not) and GET /v1/models
with fixed responses, so pinned host CLIs run real turns with no keys and
byte-stable transcripts.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_MODEL_ID = "stub-model"
_REPLY = "stub reply: acknowledged and recorded."


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - http.server API
        if self.path == "/v1/models":
            body = json.dumps(
                {"object": "list", "data": [{"id": _MODEL_ID, "object": "model"}]}
            ).encode()
            self._serve(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        if self.path != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length") or 0)
        request = json.loads(self.rfile.read(length) or b"{}")
        message = {
            "role": "assistant",
            "content": _REPLY,
        }
        if request.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            chunk = {
                "id": "stub",
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": _REPLY}}],
            }
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            return
        body = json.dumps(
            {
                "id": "stub",
                "object": "chat.completion",
                "choices": [
                    {"index": 0, "message": message, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        ).encode()
        self._serve(body)

    def _serve(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return


def serve_stub_provider(port: int = 0) -> tuple[str, ThreadingHTTPServer]:
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{server.server_address[1]}", server


if __name__ == "__main__":  # pragma: no cover
    import sys

    url, server = serve_stub_provider(int(sys.argv[1]) if len(sys.argv) > 1 else 9911)
    print(url, flush=True)
    threading.Event().wait()
