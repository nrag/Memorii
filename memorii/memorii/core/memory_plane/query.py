"""Closed typed memory-plane reader contracts.

``MemoryPlaneQuery`` selects canonical records through bounded typed filters
— never SQL text, caller-selected tables or unbounded traversal — and
``MemoryPlanePage`` returns one bounded page with an opaque authenticated
cursor. The cursor binds the query digest, the partition revision state and
an expiry, and is authenticated with an installation-controlled key, so a
forged cursor, a replayed cursor from another query, or a cursor crossing a
publication boundary is rejected.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.domain.enums import CommitStatus, MemoryDomain

QUERY_CURSOR_PURPOSE = "memory-plane-query-cursor"
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500
DEFAULT_CURSOR_LIFETIME = timedelta(minutes=5)

QueryKind = Literal["record_lookup", "filtered_records"]


class MemoryPlaneQuery(BaseModel):
    """Closed typed selection over canonical memory-plane records."""

    kind: QueryKind
    memory_id: str | None = Field(default=None, min_length=1)
    domains: tuple[MemoryDomain, ...] = ()
    statuses: tuple[CommitStatus, ...] = ()
    source_kinds: tuple[str, ...] = ()
    page_size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def lookup_is_bounded(self) -> MemoryPlaneQuery:
        if self.kind == "record_lookup" and not self.memory_id:
            raise ValueError("record_lookup requires memory_id")
        return self

    def digest(self) -> str:
        payload = "|".join(
            (
                self.kind,
                self.memory_id or "",
                ",".join(sorted(domain.value for domain in self.domains)),
                ",".join(sorted(status.value for status in self.statuses)),
                ",".join(sorted(self.source_kinds)),
                str(self.page_size),
            )
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class MemoryPlanePage(BaseModel):
    """One bounded query result page with its continuation cursor."""

    records: tuple[CanonicalMemoryRecord, ...]
    next_cursor: str | None = None
    truncated: bool = False

    model_config = ConfigDict(extra="forbid", frozen=True)


class MemoryPlaneCursorError(RuntimeError):
    """A cursor is forged, expired, stale or bound to another query."""


class QueryCursorCodec:
    """Authenticate opaque cursors with an installation-controlled key."""

    def __init__(self, key: bytes) -> None:
        if len(key) < 32:
            raise ValueError("cursor authenticator key must be at least 32 bytes")
        self._key = key

    def encode(
        self,
        *,
        query_digest: str,
        write_revision: int,
        data_revision: int,
        offset: int,
        expires_at: datetime,
    ) -> str:
        if expires_at.tzinfo is None:
            raise ValueError("cursor expiry must be timezone-aware")
        payload = self._payload(
            query_digest=query_digest,
            write_revision=write_revision,
            data_revision=data_revision,
            offset=offset,
            expires_at=expires_at.astimezone(UTC),
        )
        signature = hmac.new(self._key, payload, hashlib.sha256).hexdigest()
        return f"{payload.hex()}.{signature}"

    def decode(
        self,
        cursor: str,
        *,
        query_digest: str,
        write_revision: int,
        data_revision: int,
        now: datetime,
    ) -> int:
        try:
            encoded_payload, signature = cursor.rsplit(".", 1)
            payload = bytes.fromhex(encoded_payload)
        except ValueError as exc:
            raise MemoryPlaneCursorError("cursor payload is malformed") from exc
        expected = hmac.new(self._key, payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise MemoryPlaneCursorError("cursor signature is invalid")
        parts = payload.decode("utf-8").split("\x00")
        if len(parts) != 5:
            raise MemoryPlaneCursorError("cursor payload is malformed")
        cursor_query, cursor_write, cursor_data, offset_text, expiry_text = parts
        if cursor_query != query_digest:
            raise MemoryPlaneCursorError("cursor is bound to another query")
        if (int(cursor_write), int(cursor_data)) != (write_revision, data_revision):
            raise MemoryPlaneCursorError("cursor is stale for the current revision")
        expires_at = datetime.fromisoformat(expiry_text)
        if now.tzinfo is None:
            raise ValueError("cursor verification time must be timezone-aware")
        if now.astimezone(UTC) >= expires_at:
            raise MemoryPlaneCursorError("cursor has expired")
        offset = int(offset_text)
        if offset < 0:
            raise MemoryPlaneCursorError("cursor offset is invalid")
        return offset

    @staticmethod
    def _payload(
        *,
        query_digest: str,
        write_revision: int,
        data_revision: int,
        offset: int,
        expires_at: datetime,
    ) -> bytes:
        return "\x00".join(
            (
                query_digest,
                str(write_revision),
                str(data_revision),
                str(offset),
                expires_at.isoformat(),
            )
        ).encode("utf-8")


__all__ = [
    "DEFAULT_CURSOR_LIFETIME",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "MemoryPlaneCursorError",
    "MemoryPlanePage",
    "MemoryPlaneQuery",
    "QUERY_CURSOR_PURPOSE",
    "QueryCursorCodec",
]
