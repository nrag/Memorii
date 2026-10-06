"""Authenticated continuation cursors for harness state paging.

A cursor binds the query (task, view, offset), the principal and its
grant identity/epoch, the runtime revision it was minted at, and an
expiry — authenticated with an installation-controlled key. A forged
cursor, a cursor from another query or principal, a cursor crossing a
runtime revision boundary, or an expired cursor is rejected; on revision
or authorization change the caller receives ``stale_cursor`` and must
restart paging. Cursors are never capabilities: every page is
reauthorized.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta

HARNESS_CURSOR_PURPOSE = "harness-continuation-cursor"
HARNESS_CURSOR_DOMAIN = b"memorii.harness-continuation-cursor.v1\x00"
DEFAULT_CURSOR_LIFETIME = timedelta(minutes=5)


class HarnessCursorError(RuntimeError):
    """Cursor refused; the closed reason carries the cause."""


class HarnessPageCodec:
    """Encode/decode one bound continuation cursor under a secret key."""

    def __init__(self, key: bytes) -> None:
        if len(key) < 32:
            raise ValueError("cursor authenticator key must be at least 32 bytes")
        self._key = key

    def encode(
        self,
        *,
        task_id: str,
        principal: str,
        grant_id: str,
        grant_epoch: int,
        runtime_revision: int,
        view: str,
        offset: int,
        expires_at: datetime,
    ) -> str:
        if expires_at.tzinfo is None:
            raise ValueError("cursor expiry must be timezone-aware")
        payload = self._payload(
            task_id=task_id,
            principal=principal,
            grant_id=grant_id,
            grant_epoch=grant_epoch,
            runtime_revision=runtime_revision,
            view=view,
            offset=offset,
            expires_at=expires_at.astimezone(UTC),
        )
        signature = hmac.new(self._key, payload, hashlib.sha256).hexdigest()
        return f"{payload.hex()}.{signature}"

    def decode(
        self,
        cursor: str,
        *,
        task_id: str,
        principal: str,
        grant_id: str,
        grant_epoch: int,
        runtime_revision: int,
        view: str,
        now: datetime,
    ) -> int:
        """Validate the cursor against the current page context.

        Returns the offset. Raises HarnessCursorError with a closed reason:
        forged/expired/mismatched principals, grants or queries reject
        outright; a revision change reports ``stale_cursor`` so the caller
        restarts paging.
        """
        try:
            encoded_payload, signature = cursor.rsplit(".", 1)
            payload = bytes.fromhex(encoded_payload)
        except ValueError as exc:
            raise HarnessCursorError("forged cursor: payload is malformed") from exc
        expected = hmac.new(self._key, payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HarnessCursorError("forged cursor: signature is invalid")
        parts = payload.decode("utf-8").split("\x00")
        if len(parts) != 8:
            raise HarnessCursorError("forged cursor: payload is malformed")
        (
            cursor_task,
            cursor_principal,
            cursor_grant,
            cursor_epoch,
            cursor_revision,
            cursor_view,
            offset_text,
            expiry_text,
        ) = parts
        if cursor_task != task_id or cursor_view != view:
            raise HarnessCursorError("forged cursor: bound to another query")
        if cursor_principal != principal:
            raise HarnessCursorError("forged cursor: bound to another principal")
        if cursor_grant != grant_id or int(cursor_epoch) != grant_epoch:
            raise HarnessCursorError(
                "stale_cursor: grant identity or epoch changed; restart paging"
            )
        if int(cursor_revision) != runtime_revision:
            raise HarnessCursorError(
                "stale_cursor: runtime revision changed; restart paging"
            )
        if now.tzinfo is None:
            raise ValueError("cursor verification time must be timezone-aware")
        expires_at = datetime.fromisoformat(expiry_text)
        if now.astimezone(UTC) >= expires_at:
            raise HarnessCursorError("expired cursor: re-read current state")
        offset = int(offset_text)
        if offset < 0:
            raise HarnessCursorError("forged cursor: offset is invalid")
        return offset

    @staticmethod
    def _payload(
        *,
        task_id: str,
        principal: str,
        grant_id: str,
        grant_epoch: int,
        runtime_revision: int,
        view: str,
        offset: int,
        expires_at: datetime,
    ) -> bytes:
        return "\x00".join(
            (
                task_id,
                principal,
                grant_id,
                str(grant_epoch),
                str(runtime_revision),
                view,
                str(offset),
                expires_at.isoformat(),
            )
        ).encode("utf-8")


def cursor_codec_for(partition: object) -> HarnessPageCodec:
    """Build the codec from the installation's protected-secret owner."""
    from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore

    key = SqliteMemoryPlaneStore(partition).load_or_create_protected_secret(
        purpose=HARNESS_CURSOR_PURPOSE, length=32
    )
    return HarnessPageCodec(key)


__all__ = [
    "DEFAULT_CURSOR_LIFETIME",
    "HARNESS_CURSOR_PURPOSE",
    "HarnessCursorError",
    "HarnessPageCodec",
    "cursor_codec_for",
]
