"""Minimal ACP v1 stdio client for certification journeys.

Speaks line-delimited JSON-RPC 2.0 to an ``hermes-acp`` subprocess:
initialize, session/new, session/prompt, and session/load. Server-to-client
requests are answered with a canned error so turns never deadlock on
filesystem permission round-trips the journey does not need.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from queue import Empty, Queue


class AcpClient:
    def __init__(self, command: list[str], environment: dict[str, str]) -> None:
        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment,
            text=True,
            bufsize=1,
        )
        self._responses: Queue[dict] = Queue()
        self._notifications: list[dict] = []
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self._next_id = 0

    def _read_loop(self) -> None:
        assert self._process.stdout is not None
        for line in self._process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if "id" in message and ("result" in message or "error" in message):
                self._responses.put(message)
            elif "method" in message:
                if "id" in message:
                    self._send(
                        {
                            "jsonrpc": "2.0",
                            "id": message["id"],
                            "error": {"code": -32601, "message": "journey client has no methods"},
                        }
                    )
                else:
                    self._notifications.append(message)

    def _send(self, payload: dict) -> None:
        assert self._process.stdin is not None
        self._process.stdin.write(json.dumps(payload) + "\n")
        self._process.stdin.flush()

    def _request(self, method: str, params: dict, timeout: float = 240.0) -> dict:
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                message = self._responses.get(timeout=min(5, deadline - time.monotonic()))
            except Empty:
                if self._process.poll() is not None:
                    raise RuntimeError(f"acp server exited ({self._process.returncode}) during {method}")
                continue
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(f"{method} failed: {message['error']}")
                return message["result"]
        raise TimeoutError(f"{method} timed out")

    def initialize(self) -> dict:
        return self._request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}},
                "clientInfo": {"name": "memorii-journey", "version": "1.0.0"},
            },
        )

    def new_session(self, cwd: str) -> str:
        result = self._request("session/new", {"cwd": cwd, "mcpServers": []})
        return result["sessionId"]

    def load_session(self, session_id: str, cwd: str) -> dict:
        return self._request("session/load", {"sessionId": session_id, "cwd": cwd, "mcpServers": []})

    def prompt(self, session_id: str, text: str) -> dict:
        return self._request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": text}],
            },
        )

    def stop(self) -> None:
        self._process.terminate()
        try:
            self._process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self._process.kill()
