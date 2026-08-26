"""Bounded, operation-local reuse for validated canonical evidence with lifecycle ownership."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from hashlib import sha256
from secrets import token_hex
from threading import Lock
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel

MAX_ARENA_ENTRIES = 512
MAX_CANONICAL_BYTES_PER_ENTRY = 2_097_152
MAX_MEMBER_PATHS_PER_OPERATION = 32_768
MAX_OPERATION_RESERVED_BYTES = 16_777_216
MAX_PROCESS_RESERVED_BYTES = 67_108_864
MAX_ARENA_CHARGED_BYTES = MAX_OPERATION_RESERVED_BYTES
ENTRY_METADATA_CHARGE = 512
CANONICAL_PROFILE_REVISION = "semantic-ingestion-canonical-profile-v1"
CANONICAL_CODEC_REVISION = "semantic-contract-envelope-v1"

_OP_MODE_ENABLED = "enabled"
_OP_MODE_DISABLED = "disabled_full_path"
_OP_MODE_REFUSED = "capacity_rejected_full_path"

_TERMINAL_COMPLETED = "completed"
_TERMINAL_FEATURE_DISABLED = "feature-disabled"
_TERMINAL_CAPACITY_REFUSED = "capacity-refused"
_TERMINAL_VALIDATION_FAILED = "validation-failed"
_TERMINAL_EXCEPTION = "exception"
_TERMINAL_CANCELLED = "cancelled"

_ContractT = TypeVar("_ContractT", bound=BaseModel)

_STATE_NEW = "new"
_STATE_DISABLED = "disabled"
_STATE_RESERVED = "reserved"
_STATE_STAGING = "staging"
_STATE_SEALED = "sealed"
_STATE_CLOSING = "closing"
_STATE_REJECTED = "rejected"
_STATE_CLOSED = "closed"
_State = Literal[
    _STATE_NEW,
    _STATE_DISABLED,
    _STATE_RESERVED,
    _STATE_STAGING,
    _STATE_SEALED,
    _STATE_CLOSING,
    _STATE_REJECTED,
    _STATE_CLOSED,
]
_Mode = Literal[
    _OP_MODE_ENABLED,
    _OP_MODE_DISABLED,
    _OP_MODE_REFUSED,
]
_TerminalReason = Literal[
    _TERMINAL_COMPLETED,
    _TERMINAL_FEATURE_DISABLED,
    _TERMINAL_CAPACITY_REFUSED,
    _TERMINAL_VALIDATION_FAILED,
    _TERMINAL_EXCEPTION,
    _TERMINAL_CANCELLED,
]


@dataclass(frozen=True)
class CanonicalValidationScope:
    tenant: str
    operation: str
    generation: int
    fence: str
    writer: str


@dataclass(frozen=True)
class CanonicalBinding:
    issuer: object
    scope: CanonicalValidationScope


@dataclass(frozen=True)
class CanonicalMemberIndex:
    contract_type: str
    member_paths: int
    canonical_digest: str


@dataclass(frozen=True)
class CanonicalMemberEvidence:
    """Traversal-issued, path-addressable evidence for one exact root span.

    The owner deliberately accepts this only from the codec/validator handoff;
    callers cannot turn equal bytes into membership by searching a root.
    """

    path: tuple[str | int, ...]
    begin: int
    end: int
    member_digest: str
    member_type: str
    domain: bytes
    profile_revision: str
    codec_revision: str
    schema: str
    provenance: tuple[str, ...]


@dataclass(frozen=True)
class CanonicalCodecResult(Generic[_ContractT]):
    contract: _ContractT
    canonical_contract_bytes: bytes
    canonical_member_index: CanonicalMemberIndex
    validation_provenance: tuple[str, ...]
    member_evidence: tuple[CanonicalMemberEvidence, ...] = ()
    domain: bytes = b""


@dataclass(frozen=True)
class CanonicalEvidenceLease(Generic[_ContractT]):
    """Bounded immutable view returned only by a sealed scope lookup."""

    result: CanonicalCodecResult[_ContractT]
    _owner: CanonicalClosureScopeOwner
    _token: str
    _released: bool = False

    @property
    def scope(self) -> CanonicalValidationScope:
        return self._owner.scope

    def release(self) -> None:
        if self._released:
            raise RuntimeError("canonical evidence lease already released")
        object.__setattr__(self, "_released", True)
        self._owner.release_lease(self._token)


ValidatedCanonicalEvidenceResult = CanonicalCodecResult


@dataclass(frozen=True)
class ValidatedCanonicalClosure:
    mode: _Mode
    scope: CanonicalValidationScope
    binding: CanonicalBinding | None
    terminal_reason: _TerminalReason | None


@dataclass(frozen=True)
class CanonicalClosureTerminalSnapshot:
    mode: _Mode
    terminal_reason: _TerminalReason
    roots: int
    member_paths: int
    lookups: int
    hits: int
    misses: int
    capacity_refusals: int
    peak_charged_bytes: int
    reserved_bytes: int
    released: bool


@dataclass(frozen=True)
class CanonicalEvidenceArenaSnapshot:
    nonce: str
    state: _State
    mode: _Mode
    reservation_acquired: bool
    closed: bool
    entries: int
    charged_bytes: int
    hits: int
    misses: int
    lookups: int
    capacity_fallbacks: int
    terminal_reason: _TerminalReason | None
    member_paths: int
    peak_charged_bytes: int
    reserved_bytes: int
    released: bool


class CanonicalClosureObservabilityDispatcher:
    def record(
        self, snapshot: CanonicalClosureTerminalSnapshot
    ) -> Literal["recorded", "unavailable"]:
        return "recorded"


class RetainingCanonicalClosureObservabilityDispatcher(CanonicalClosureObservabilityDispatcher):
    """Repository-owned, content-free terminal snapshot sink."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._snapshots: list[CanonicalClosureTerminalSnapshot] = []

    @property
    def snapshots(self) -> tuple[CanonicalClosureTerminalSnapshot, ...]:
        with self._lock:
            return tuple(self._snapshots)

    def record(
        self, snapshot: CanonicalClosureTerminalSnapshot
    ) -> Literal["recorded", "unavailable"]:
        with self._lock:
            self._snapshots.append(snapshot)
        return "recorded"


class CanonicalClosureReservationCoordinator:
    def __init__(self) -> None:
        self._lock = Lock()
        self._reserved_bytes = 0

    def acquire(self) -> bool:
        with self._lock:
            if self._reserved_bytes + MAX_OPERATION_RESERVED_BYTES > MAX_PROCESS_RESERVED_BYTES:
                return False
            self._reserved_bytes += MAX_OPERATION_RESERVED_BYTES
            return True

    def release(self) -> None:
        with self._lock:
            if self._reserved_bytes < MAX_OPERATION_RESERVED_BYTES:
                raise RuntimeError("canonical closure reservation underflow")
            self._reserved_bytes -= MAX_OPERATION_RESERVED_BYTES


_PROCESS_RESERVATIONS = CanonicalClosureReservationCoordinator()
class CanonicalClosureScopeOwner:
    _VALID_TRANSITIONS = {
        (_STATE_NEW, "select_disabled", _STATE_DISABLED),
        (_STATE_NEW, "reserve_succeeded", _STATE_RESERVED),
        (_STATE_NEW, "reserve_refused", _STATE_REJECTED),
        (_STATE_RESERVED, "begin_staging", _STATE_STAGING),
        (_STATE_STAGING, "seal", _STATE_SEALED),
        (_STATE_STAGING, "capacity_refused", _STATE_REJECTED),
        (_STATE_RESERVED, "abort", _STATE_CLOSED),
        (_STATE_STAGING, "abort", _STATE_CLOSED),
        (_STATE_SEALED, "close_without_leases", _STATE_CLOSED),
        (_STATE_SEALED, "close_with_leases", _STATE_CLOSING),
        (_STATE_CLOSING, "last_lease_released", _STATE_CLOSED),
    }

    def __init__(
        self,
        *,
        coordinator: CanonicalClosureReservationCoordinator,
        scope: CanonicalValidationScope | None,
        observability_dispatcher: CanonicalClosureObservabilityDispatcher,
        enabled: bool,
    ) -> None:
        self._coordinator = coordinator
        self._lock = Lock()
        self._scope = scope
        self._observability_dispatcher = observability_dispatcher
        self._state: _State = _STATE_NEW
        self._mode: _Mode = _OP_MODE_ENABLED
        self._issuer = object()
        self._binding: CanonicalBinding | None = None
        self._terminal_reason: _TerminalReason | None = None
        self._terminal_snapshot: CanonicalClosureTerminalSnapshot | None = None
        self._pending_close_reason: _TerminalReason | None = None
        self._entries: dict[str, CanonicalCodecResult[BaseModel]] = {}
        self._leased_tokens: set[str] = set()
        self._leases = 0
        self._charge = 0
        self._peak_charge = 0
        self._roots = 0
        self._member_paths = 0
        self._lookups = 0
        self._hits = 0
        self._misses = 0
        self._capacity_refusals = 0
        self._held = False
        if not enabled:
            self._mode = _OP_MODE_DISABLED
            self._move("select_disabled", _STATE_DISABLED)
            self._finish(_TERMINAL_FEATURE_DISABLED)
            return
        if self._coordinator.acquire():
            self._held = True
            self._move("reserve_succeeded", _STATE_RESERVED)
            return
        self._mode = _OP_MODE_REFUSED
        self._capacity_refusals = 1
        self._move("reserve_refused", _STATE_REJECTED)
        self._finish(_TERMINAL_CAPACITY_REFUSED)

    @property
    def state(self) -> _State:
        return self._state

    @property
    def mode(self) -> _Mode:
        return self._mode

    @property
    def terminal_reason(self) -> _TerminalReason | None:
        return self._terminal_reason

    @property
    def terminal_snapshot(self) -> CanonicalClosureTerminalSnapshot | None:
        return self._terminal_snapshot

    @property
    def reservation_acquired(self) -> bool:
        return self._held

    @property
    def entries(self) -> int:
        return len(self._entries)

    @property
    def charge(self) -> int:
        return self._charge

    @property
    def peak_charge(self) -> int:
        return self._peak_charge

    @property
    def member_paths(self) -> int:
        return self._member_paths

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses

    @property
    def lookups(self) -> int:
        return self._lookups

    @property
    def capacity_refusals(self) -> int:
        return self._capacity_refusals

    @property
    def capability(self) -> CanonicalBinding | None:
        return self._binding

    @property
    def scope(self) -> CanonicalValidationScope:
        if self._scope is None:
            raise ValueError("canonical evidence scope is not bound")
        return self._scope

    def begin_staging(self) -> None:
        with self._lock:
            if self._state == _STATE_STAGING:
                return
            self._move("begin_staging", _STATE_STAGING)

    def look(
        self,
        *,
        concrete_contract_type: type[BaseModel],
        canonical_contract_bytes: bytes,
        profile_revision: str,
        codec_revision: str,
        domain: bytes,
    ) -> CanonicalCodecResult[BaseModel] | None:
        """Lookup is intentionally unavailable before sealing.

        A caller that lacks a sealed object-identity capability must execute the
        normal validator/codec path; staging is never a cache authority.
        """
        del concrete_contract_type, canonical_contract_bytes, profile_revision, codec_revision, domain
        raise ValueError("canonical evidence lookup requires sealed authority")

    def lookup_sealed(
        self,
        *,
        binding: CanonicalBinding,
        scope: CanonicalValidationScope,
        concrete_contract_type: type[BaseModel],
        canonical_contract_bytes: bytes,
        profile_revision: str,
        codec_revision: str,
        domain: bytes,
    ) -> CanonicalEvidenceLease[BaseModel] | None:
        with self._lock:
            if self._state != _STATE_SEALED:
                raise ValueError("lookup outside sealed state")
            if binding is not self._binding or binding.issuer is not self._issuer:
                raise ValueError("forged capability")
            if binding.scope != self._scope or scope != self._scope:
                raise ValueError("foreign scope")
            key = self._cache_key(
            concrete_contract_type=concrete_contract_type,
            profile_revision=profile_revision,
            codec_revision=codec_revision,
            domain=domain,
            canonical_contract_bytes=canonical_contract_bytes,
        )
            self._lookups += 1
            cached = self._entries.get(key)
            if cached is None:
                self._misses += 1
                return None
            self._hits += 1
            token = token_hex(32)
            self._leases += 1
            self._leased_tokens.add(token)
            return CanonicalEvidenceLease(result=cached, _owner=self, _token=token)

    def admit(
        self,
        *,
        concrete_contract_type: type[BaseModel],
        canonical_contract_bytes: bytes,
        profile_revision: str,
        codec_revision: str,
        domain: bytes,
        result: CanonicalCodecResult[BaseModel],
    ) -> bool:
        with self._lock:
            if self._state not in {_STATE_RESERVED, _STATE_STAGING}:
                return False
            if self._state == _STATE_RESERVED:
                self._move("begin_staging", _STATE_STAGING)
            key = self._cache_key(
            concrete_contract_type=concrete_contract_type,
            profile_revision=profile_revision,
            codec_revision=codec_revision,
            domain=domain,
            canonical_contract_bytes=canonical_contract_bytes,
        )
            if key in self._entries:
                return False
            candidate_bytes = len(canonical_contract_bytes)
            candidate_paths = result.canonical_member_index.member_paths
            if candidate_bytes > MAX_CANONICAL_BYTES_PER_ENTRY:
                return self._reject_capacity(_TERMINAL_CAPACITY_REFUSED)
            if self._roots + 1 > MAX_ARENA_ENTRIES:
                return self._reject_capacity(_TERMINAL_CAPACITY_REFUSED)
            if self._member_paths + candidate_paths > MAX_MEMBER_PATHS_PER_OPERATION:
                return self._reject_capacity(_TERMINAL_CAPACITY_REFUSED)
            # Compact index accounting: root bytes plus a fixed issued-record
            # charge, matching the frozen operation envelope.
            candidate_charge = candidate_bytes + ENTRY_METADATA_CHARGE + candidate_paths * 64
            if self._charge + candidate_charge > MAX_OPERATION_RESERVED_BYTES:
                return self._reject_capacity(_TERMINAL_CAPACITY_REFUSED)
            self._entries[key] = result
            self._roots += 1
            self._member_paths += candidate_paths
            self._charge += candidate_charge
            if self._charge > self._peak_charge:
                self._peak_charge = self._charge
            return True

    def seal(self) -> CanonicalBinding:
        with self._lock:
            if self._scope is None:
                raise ValueError("canonical evidence scope must be bound before sealing")
            self._move("seal", _STATE_SEALED)
            if self._binding is None:
                self._binding = CanonicalBinding(issuer=self._issuer, scope=self._scope)
            return self._binding

    def bind_and_seal(self, scope: CanonicalValidationScope) -> CanonicalBinding:
        with self._lock:
            if self._state != _STATE_STAGING or self._scope is not None:
                raise ValueError("canonical evidence scope may bind only once during staging")
            self._scope = scope
            self._move("seal", _STATE_SEALED)
            if self._binding is None:
                self._binding = CanonicalBinding(issuer=self._issuer, scope=self._scope)
            return self._binding

    def lease(self, *, binding: CanonicalBinding, scope: CanonicalValidationScope, key: str) -> bool:
        with self._lock:
            if self._state != _STATE_SEALED:
                raise ValueError("lookup outside sealed state")
            if binding is not self._binding or binding.issuer is not self._issuer:
                raise ValueError("forged capability")
            if binding.scope != self._scope or scope != self._scope:
                raise ValueError("foreign scope")
            self._lookups += 1
            if key not in self._entries:
                self._misses += 1
                return False
            self._hits += 1
            raise ValueError("raw key leasing is unavailable; use lookup_sealed")

    def release_lease(self, token: str) -> None:
        with self._lock:
            if token not in self._leased_tokens:
                raise RuntimeError("foreign, stale, or duplicate lease token")
            self._leased_tokens.remove(token)
            self._leases -= 1
            if self._state == _STATE_CLOSING and self._leases == 0:
                self._move("last_lease_released", _STATE_CLOSED)
                self._clear_payload()
                self._finish(self._pending_close_reason or _TERMINAL_COMPLETED)

    def close(self, reason: _TerminalReason = _TERMINAL_COMPLETED) -> None:
        with self._lock:
            if self._state in {_STATE_DISABLED, _STATE_REJECTED, _STATE_CLOSED, _STATE_CLOSING}:
                return
            # Latch the first linearized terminal cause before an outstanding
            # lease drains; later close/abort calls are idempotent.
            self._pending_close_reason = reason
            if self._state == _STATE_SEALED:
                if self._leases > 0:
                    self._move("close_with_leases", _STATE_CLOSING)
                else:
                    self._move("close_without_leases", _STATE_CLOSED)
                    self._clear_payload()
                    self._finish(reason)
                return
            if self._state in {_STATE_RESERVED, _STATE_STAGING}:
                self._move("abort", _STATE_CLOSED)
                self._clear_payload()
                self._finish(reason)

    def abort(self, reason: _TerminalReason) -> None:
        self.close(reason)

    def terminal(self) -> ValidatedCanonicalClosure:
        return ValidatedCanonicalClosure(
            mode=self._mode,
            scope=self._scope,
            binding=self._binding,
            terminal_reason=self._terminal_reason,
        )

    def _reject_capacity(self, reason: _TerminalReason) -> bool:
        if reason == _TERMINAL_CAPACITY_REFUSED:
            self._mode = _OP_MODE_REFUSED
        self._capacity_refusals += 1
        self._move("capacity_refused", _STATE_REJECTED)
        self._clear_payload()
        self._finish(reason)
        return False

    def _move(self, event: str, target: _State) -> None:
        if (self._state, event, target) not in self._VALID_TRANSITIONS:
            raise ValueError("invalid lifecycle transition")
        self._state = target

    def _finish(self, reason: _TerminalReason) -> None:
        if self._terminal_snapshot is not None:
            return
        self._binding = None
        if self._terminal_reason is None:
            self._terminal_reason = reason
        self._coordinator_release()
        self._emit()

    def _clear_payload(self) -> None:
        self._entries.clear()
        self._charge = 0

    def _emit(self) -> None:
        if self._terminal_snapshot is not None:
            return
        assert self._terminal_reason is not None
        snapshot = CanonicalClosureTerminalSnapshot(
            mode=self._mode,
            terminal_reason=self._terminal_reason,
            roots=self._roots,
            member_paths=self._member_paths,
            lookups=self._lookups,
            hits=self._hits,
            misses=self._misses,
            capacity_refusals=self._capacity_refusals,
            peak_charged_bytes=self._peak_charge,
            reserved_bytes=(
                MAX_OPERATION_RESERVED_BYTES if self._mode == _OP_MODE_ENABLED else 0
            ),
            released=not self._held,
        )
        self._terminal_snapshot = snapshot
        try:
            outcome = self._observability_dispatcher.record(snapshot)
        except Exception:
            outcome = "unavailable"
        # Observability is deliberately non-authoritative: a malformed or
        # unavailable sink has the same product outcome as an unavailable one.
        if outcome not in {"recorded", "unavailable"}:
            outcome = "unavailable"

    def _coordinator_release(self) -> None:
        if self._held:
            self._coordinator.release()
            self._held = False

    @staticmethod
    def _cache_key(
        *,
        concrete_contract_type: type[BaseModel],
        canonical_contract_bytes: bytes,
        profile_revision: str,
        codec_revision: str,
        domain: bytes,
    ) -> str:
        return sha256(
            domain
            + b"\0"
            + canonical_contract_bytes
            + b"\0"
            + concrete_contract_type.__qualname__.encode("utf-8")
            + b"\0"
            + profile_revision.encode("utf-8")
            + b"\0"
            + codec_revision.encode("utf-8")
        ).hexdigest()


class CanonicalEvidenceArena(AbstractContextManager["CanonicalEvidenceArena"]):
    """One invocation's immutable successful canonical-evidence entries."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        scope: CanonicalValidationScope | None = None,
        observability_dispatcher: CanonicalClosureObservabilityDispatcher | None = None,
    ) -> None:
        self._nonce = token_hex(32)
        self._scope = scope
        self._owner = CanonicalClosureScopeOwner(
            coordinator=_PROCESS_RESERVATIONS,
            scope=self._scope,
            observability_dispatcher=(
                observability_dispatcher
                or CanonicalClosureObservabilityDispatcher()
            ),
            enabled=enabled,
        )

    @property
    def nonce(self) -> str:
        return self._nonce

    @property
    def pydantic_context(self) -> dict[object, object]:
        """Compatibility context only; it carries no cache authority."""
        return {}

    @property
    def closed(self) -> bool:
        return self._owner.state in {_STATE_DISABLED, _STATE_REJECTED, _STATE_CLOSED}

    @property
    def scope(self) -> CanonicalValidationScope:
        return self._owner.scope

    @property
    def terminal_snapshot(self) -> CanonicalClosureTerminalSnapshot | None:
        return self._owner.terminal_snapshot

    @property
    def enabled(self) -> bool:
        return self._owner.mode == _OP_MODE_ENABLED

    def require_active_nonce(self, nonce: str) -> None:
        if (
            self._owner.state not in {_STATE_DISABLED, _STATE_REJECTED}
            and self._owner.state in {_STATE_CLOSED, _STATE_CLOSING}
        ) or nonce != self._nonce:
            raise ValueError("canonical evidence arena context is stale or substituted")

    def lookup(
        self,
        *,
        canonical_contract_bytes: bytes,
        concrete_contract_type: type[_ContractT],
        profile_revision: str,
        codec_revision: str,
        domain: bytes,
    ) -> CanonicalCodecResult[_ContractT] | None:
        # This compatibility method deliberately refuses the old pre-seal cache
        # protocol. New consumers use ``lookup_sealed`` with a capability.
        del canonical_contract_bytes, concrete_contract_type, profile_revision, codec_revision, domain
        raise ValueError("canonical evidence lookup requires sealed authority")

    def lookup_sealed(
        self,
        *,
        binding: CanonicalBinding,
        scope: CanonicalValidationScope,
        canonical_contract_bytes: bytes,
        concrete_contract_type: type[_ContractT],
        profile_revision: str,
        codec_revision: str,
        domain: bytes,
    ) -> CanonicalEvidenceLease[_ContractT] | None:
        return self._owner.lookup_sealed(
            binding=binding,
            scope=scope,
            canonical_contract_bytes=canonical_contract_bytes,
            concrete_contract_type=concrete_contract_type,
            profile_revision=profile_revision,
            codec_revision=codec_revision,
            domain=domain,
        )  # type: ignore[return-value]

    def admit_success(
        self,
        *,
        canonical_contract_bytes: bytes,
        concrete_contract_type: type[_ContractT],
        profile_revision: str,
        codec_revision: str,
        domain: bytes,
        result: ValidatedCanonicalEvidenceResult[_ContractT],
    ) -> bool:
        return self._owner.admit(
            canonical_contract_bytes=canonical_contract_bytes,
            concrete_contract_type=concrete_contract_type,
            profile_revision=profile_revision,
            codec_revision=codec_revision,
            domain=domain,
            result=result,
        )

    def seal(self) -> CanonicalBinding:
        return self._owner.seal()

    def bind_and_seal(self, scope: CanonicalValidationScope) -> CanonicalBinding:
        return self._owner.bind_and_seal(scope)

    def lease(
        self,
        *,
        binding: CanonicalBinding,
        scope: CanonicalValidationScope,
        key: str,
    ) -> bool:
        return self._owner.lease(binding=binding, scope=scope, key=key)

    def release_lease(self, token: str) -> None:
        self._owner.release_lease(token)

    def close(self) -> None:
        if self._owner.state == _STATE_CLOSED:
            return
        self._owner.close()

    def close_as_exception(self) -> None:
        if self._owner.state == _STATE_CLOSED:
            return
        self._owner.close(_TERMINAL_EXCEPTION)

    def abort(self, reason: _TerminalReason) -> None:
        if self._owner.state == _STATE_CLOSED:
            return
        self._owner.abort(reason)

    def snapshot(self) -> CanonicalEvidenceArenaSnapshot:
        terminal_snapshot = self._owner.terminal_snapshot
        return CanonicalEvidenceArenaSnapshot(
            nonce=self._nonce,
            state=self._owner.state,
            mode=self._owner.mode,
            reservation_acquired=self._owner.reservation_acquired,
            closed=self.closed,
            entries=self._owner.entries,
            charged_bytes=self._owner.charge,
            hits=self._owner.hits,
            misses=self._owner.misses,
            lookups=self._owner.lookups,
            capacity_fallbacks=self._owner.capacity_refusals,
            terminal_reason=self._owner.terminal_reason,
            member_paths=self._owner.member_paths,
            peak_charged_bytes=self._owner.peak_charge,
            reserved_bytes=(
                MAX_OPERATION_RESERVED_BYTES if self._owner.mode == _OP_MODE_ENABLED else 0
            ),
            released=terminal_snapshot.released if terminal_snapshot is not None else False,
        )

    def __enter__(self) -> CanonicalEvidenceArena:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        if exc_type is None:
            self.close()
        else:
            self.close_as_exception()
