"""Process-local, lock-linearized host grants for scoped reads."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol
from uuid import uuid4

from memorii.domain.enums import MemoryDomain


@dataclass(frozen=True)
class ScopedNamespaceGrantRow:
    domain: MemoryDomain
    task_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    execution_node_id: str | None = None
    solver_run_id: str | None = None
    allowed_record_ids: frozenset[str] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.domain, MemoryDomain):
            raise ValueError("grant domain must be a memory domain")
        for value in (self.task_id, self.session_id, self.user_id, self.agent_id, self.execution_node_id, self.solver_run_id):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError("grant namespace values must be nonblank strings")
        if self.allowed_record_ids is not None and (
            type(self.allowed_record_ids) is not frozenset
            or not self.allowed_record_ids
            or any(not isinstance(value, str) or not value.strip() for value in self.allowed_record_ids)
        ):
            raise ValueError("allowed record IDs must be nonempty and nonblank")


@dataclass(frozen=True)
class ResolvedScopedReadGrant:
    handle_id: str
    host_task_id: str
    host_state_id: str
    authority_epoch: int
    expires_at: datetime
    rows: tuple[ScopedNamespaceGrantRow, ...]


@dataclass(frozen=True)
class ScopedAuthorityBindingReceipt:
    handle_id: str
    authority_epoch: int


class ScopedHostReadAuthority(Protocol):
    def resolve(self, handle: object, *, task_id: str, state_id: str) -> ResolvedScopedReadGrant | None: ...
    def authorize_release(self, grant: ResolvedScopedReadGrant) -> ScopedAuthorityBindingReceipt | None: ...


class InProcessScopedReadAuthority:
    def __init__(self, *, now_provider: Callable[[], datetime]) -> None:
        self._now_provider = now_provider
        self._lock = RLock()
        self._entries: dict[int, tuple[object, ResolvedScopedReadGrant]] = {}
        self._epoch = 0

    def provision(self, *, host_task_id: str, host_state_id: str, rows: tuple[ScopedNamespaceGrantRow, ...], expires_at: datetime) -> object:
        if (
            not isinstance(host_task_id, str) or not host_task_id.strip()
            or not isinstance(host_state_id, str) or not host_state_id.strip()
            or type(rows) is not tuple or not rows
            or expires_at.tzinfo is None or expires_at.utcoffset() != UTC.utcoffset(expires_at)
        ):
            raise ValueError("invalid scoped read grant")
        if len(rows) != len(set(rows)):
            raise ValueError("duplicate scoped namespace grant row")
        for row in rows:
            if all(getattr(row, field) is None for field in ("task_id", "session_id", "user_id", "agent_id", "execution_node_id", "solver_run_id")) and not row.allowed_record_ids:
                raise ValueError("all-null grant rows require finite record IDs")
            if row.allowed_record_ids is not None and (
                type(row.allowed_record_ids) is not frozenset
                or not row.allowed_record_ids
                or any(not isinstance(value, str) or not value.strip() for value in row.allowed_record_ids)
            ):
                raise ValueError("allowed record IDs must be nonblank")
        handle = object()
        with self._lock:
            self._epoch += 1
            self._entries[id(handle)] = (handle, ResolvedScopedReadGrant(str(uuid4()), host_task_id, host_state_id, self._epoch, expires_at, rows))
        return handle

    def revoke(self, handle: object) -> None:
        with self._lock:
            entry = self._entries.get(id(handle))
            if entry is not None and entry[0] is handle:
                del self._entries[id(handle)]

    def resolve(self, handle: object, *, task_id: str, state_id: str) -> ResolvedScopedReadGrant | None:
        with self._lock:
            entry = self._entries.get(id(handle))
            grant = entry[1] if entry is not None and entry[0] is handle else None
            return grant if self._valid(grant, task_id, state_id) else None

    def authorize_release(self, grant: ResolvedScopedReadGrant) -> ScopedAuthorityBindingReceipt | None:
        with self._lock:
            for _, entry in self._entries.values():
                if entry == grant and self._valid(entry, grant.host_task_id, grant.host_state_id):
                    return ScopedAuthorityBindingReceipt(entry.handle_id, entry.authority_epoch)
        return None

    def _valid(self, grant: ResolvedScopedReadGrant | None, task_id: str, state_id: str) -> bool:
        now = self._now_provider()
        if now.tzinfo is None or now.utcoffset() != UTC.utcoffset(now):
            raise ValueError("scoped authority clock must return UTC timestamps")
        return grant is not None and grant.host_task_id == task_id and grant.host_state_id == state_id and now < grant.expires_at
