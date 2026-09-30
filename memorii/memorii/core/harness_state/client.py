"""Python runtime client: the same typed protocol as embedded calls.

The client speaks the sidecar's closed v1 request/response contract
with no hand-written schema drift: request and envelope models come
from the same owners, errors surface the closed error codes, and the
credential never appears in URLs or logs.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Literal

from memorii.core.harness_state.envelope import HarnessStateEnvelope
from memorii.core.harness_state.sidecar import SidecarRequest


class RuntimeClientError(RuntimeError):
    """Sidecar refused; the closed code and HTTP status are carried."""

    def __init__(self, code: str, status: int, detail: str | None) -> None:
        super().__init__(f"{status} {code}" + (f": {detail}" if detail else ""))
        self.code = code
        self.status = status
        self.detail = detail


class RuntimeStateClient:
    """Thin typed client for one loopback sidecar installation."""

    def __init__(self, base_url: str, *, credential: str, timeout: float = 10.0) -> None:
        if not base_url.startswith("http://127.0.0.1"):
            # Remote binding is disabled by the sidecar; refuse client-side.
            raise ValueError("runtime client only binds loopback sidecar URLs")
        self._base_url = base_url.rstrip("/")
        self._credential = credential
        self._timeout = timeout

    def get_state(
        self,
        task_id: str,
        *,
        view: Literal["execution", "solver", "summary", "history", "neighborhood"] = "summary",
    ) -> HarnessStateEnvelope:
        request = SidecarRequest(task_id=task_id, view=view)
        http_request = urllib.request.Request(
            self._base_url + "/v1/runtime/state",
            data=request.model_dump_json().encode("utf-8"),
            headers={"Authorization": f"Bearer {self._credential}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=self._timeout) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read()
            try:
                error = json.loads(body)
                raise RuntimeClientError(
                    error.get("code", "unavailable"),
                    exc.code,
                    error.get("detail"),
                ) from exc
            except json.JSONDecodeError:
                raise RuntimeClientError("unavailable", exc.code, None) from exc
        except urllib.error.URLError as exc:
            raise RuntimeClientError("unavailable", 0, str(exc.reason)) from exc
        return HarnessStateEnvelope.model_validate_json(payload)


__all__ = ["RuntimeClientError", "RuntimeStateClient"]
