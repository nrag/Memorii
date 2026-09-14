"""Nonproduction feasibility model for store-owned observation-ledger ordering."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from json import dumps
from typing import Literal

TerminalKind = Literal["group", "source_finalization"]
GENESIS_REVISION = "genesis"
_AFTER_DOMAIN = b"memorii.observation-ledger.revision.v1\0"
_PAYLOAD_DOMAIN = b"memorii.observation-ledger.payload.v1\0"
_DELTA_DOMAIN = b"memorii.observation-ledger.delta.v1\0"
_ENTRY_DOMAIN = b"memorii.observation-ledger.entry.v1\0"


def _hash(domain: bytes, value: object) -> str:
    return sha256(domain + dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _digest(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


@dataclass(frozen=True, slots=True)
class SemanticPayload:
    source_id: str
    operation_fence_id: str
    transaction_group_id: str | None
    operation_ids: tuple[str, ...]
    precommit_result_digest: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_id, str) or not self.source_id
            or not isinstance(self.operation_fence_id, str) or not self.operation_fence_id
            or (self.transaction_group_id is not None and not isinstance(self.transaction_group_id, str))
            or not isinstance(self.operation_ids, tuple)
            or not _digest(self.precommit_result_digest)
            or any(not isinstance(operation_id, str) or not operation_id for operation_id in self.operation_ids)
            or self.operation_ids != tuple(sorted(set(self.operation_ids)))
        ):
            raise ValueError("semantic payload is not canonical")

    def commitment(self) -> str:
        return _hash(_PAYLOAD_DOMAIN, asdict(self))


@dataclass(frozen=True, slots=True)
class LedgerHead:
    generation: int
    revision: str
    last_entry_digest: str | None

    def __post_init__(self) -> None:
        if (
            type(self.generation) is not int
            or self.generation < 0
            or (self.generation == 0) != (self.last_entry_digest is None)
            or (self.generation == 0 and self.revision != GENESIS_REVISION)
            or (self.generation > 0 and not _digest(self.revision))
            or (self.last_entry_digest is not None and not _digest(self.last_entry_digest))
        ):
            raise ValueError("ledger head is invalid")


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    generation: int
    terminal_kind: TerminalKind
    stable_identity: str
    payload: SemanticPayload
    payload_commitment: str
    revision_before: str
    revision_after: str
    final_delta_digest: str
    result_locator: str
    result_digest: str
    prior_entry_digest: str | None
    entry_digest: str

    def __post_init__(self) -> None:
        replace(self.payload)
        expected_payload = self.payload.commitment()
        expected_after = _after_revision(
            self.revision_before, self.stable_identity, expected_payload
        )
        expected_delta = _final_delta_digest(
            self.terminal_kind, self.stable_identity, self.payload, self.revision_before,
            expected_after,
        )
        expected_entry = _entry_digest(
            self.generation, self.terminal_kind, self.stable_identity, expected_payload,
            self.revision_before, expected_after, expected_delta, self.result_locator,
            self.result_digest, self.prior_entry_digest,
        )
        if (
            type(self.generation) is not int
            or self.generation < 1
            or self.terminal_kind not in {"group", "source_finalization"}
            or not self.stable_identity
            or not self.result_locator
            or not _digest(self.result_digest)
            or (self.revision_before != GENESIS_REVISION and not _digest(self.revision_before))
            or not _digest(self.revision_after)
            or not _digest(self.final_delta_digest)
            or (self.prior_entry_digest is not None and not _digest(self.prior_entry_digest))
            or self.result_digest != _result_digest(self.terminal_kind, self.payload, expected_delta)
            or (self.terminal_kind == "group" and (
                not self.payload.transaction_group_id or not self.payload.operation_ids
            ))
            or (self.terminal_kind == "source_finalization" and self.payload.transaction_group_id is not None)
            or self.payload_commitment != expected_payload
            or self.revision_after != expected_after
            or self.final_delta_digest != expected_delta
            or self.entry_digest != expected_entry
        ):
            raise ValueError("ledger entry is invalid")


def _after_revision(before: str, identity: str, payload_commitment: str) -> str:
    return _hash(_AFTER_DOMAIN, (before, identity, payload_commitment))


def _final_delta_digest(
    kind: TerminalKind, identity: str, payload: SemanticPayload, before: str, after: str,
) -> str:
    return _hash(_DELTA_DOMAIN, (kind, identity, asdict(payload), before, after))


def _result_digest(kind: TerminalKind, payload: SemanticPayload, delta_digest: str) -> str:
    # Source canonical result precedes its delta; group receipt follows its delta.
    if kind == "source_finalization":
        return payload.precommit_result_digest
    return _hash(b"memorii.observation-ledger.group-result.v1\0", (
        payload.precommit_result_digest, delta_digest,
    ))


def _entry_digest(
    generation: int, kind: TerminalKind, identity: str, payload_commitment: str,
    before: str, after: str, delta_digest: str, locator: str, result_digest: str,
    prior_entry_digest: str | None,
) -> str:
    return _hash(_ENTRY_DOMAIN, (
        generation, kind, identity, payload_commitment, before, after, delta_digest,
        locator, result_digest, prior_entry_digest,
    ))


class ObservationLedger:
    """In-memory CAS model; callers supply no ledger revision or final delta."""

    def __init__(self) -> None:
        self._head = LedgerHead(0, GENESIS_REVISION, None)
        self._entries: tuple[LedgerEntry, ...] = ()

    @property
    def head(self) -> LedgerHead:
        return self._head

    @property
    def entries(self) -> tuple[LedgerEntry, ...]:
        return self._entries

    def append(
        self, *, expected_head: LedgerHead, terminal_kind: TerminalKind,
        stable_identity: str, payload: SemanticPayload, result_locator: str,
    ) -> LedgerEntry:
        _validate_append_input(terminal_kind, stable_identity, payload, result_locator)
        existing = next((entry for entry in self._entries if entry.stable_identity == stable_identity), None)
        if existing is not None:
            if (
                existing.terminal_kind != terminal_kind
                or existing.payload != payload
                or existing.result_locator != result_locator
            ):
                raise ValueError("duplicate identity has changed content")
            return existing
        if expected_head != self._head:
            raise ValueError("stale ledger head")
        payload_commitment = payload.commitment()
        after = _after_revision(self._head.revision, stable_identity, payload_commitment)
        delta = _final_delta_digest(
            terminal_kind, stable_identity, payload, self._head.revision, after,
        )
        entry = LedgerEntry(
            generation=self._head.generation + 1,
            terminal_kind=terminal_kind,
            stable_identity=stable_identity,
            payload=payload,
            payload_commitment=payload_commitment,
            revision_before=self._head.revision,
            revision_after=after,
            final_delta_digest=delta,
            result_locator=result_locator,
            result_digest=_result_digest(terminal_kind, payload, delta),
            prior_entry_digest=self._head.last_entry_digest,
            entry_digest=_entry_digest(
                self._head.generation + 1, terminal_kind, stable_identity,
                payload_commitment, self._head.revision, after, delta, result_locator,
                _result_digest(terminal_kind, payload, delta), self._head.last_entry_digest,
            ),
        )
        self._entries = (*self._entries, entry)
        self._head = LedgerHead(entry.generation, entry.revision_after, entry.entry_digest)
        return entry


def _validate_append_input(
    terminal_kind: TerminalKind, stable_identity: str, payload: SemanticPayload,
    result_locator: str,
) -> None:
    replace(payload)
    if terminal_kind not in {"group", "source_finalization"}:
        raise ValueError("unknown terminal kind")
    if not stable_identity or not result_locator:
        raise ValueError("append identity is incomplete")
    if terminal_kind == "group" and (
        not payload.transaction_group_id or not payload.operation_ids
    ):
        raise ValueError("group payload is incomplete")
    if terminal_kind == "source_finalization" and payload.transaction_group_id is not None:
        raise ValueError("source finalization has a group")


def replay(entries: tuple[LedgerEntry, ...], *, expected_head: LedgerHead | None = None) -> LedgerHead:
    head = LedgerHead(0, GENESIS_REVISION, None)
    seen: set[str] = set()
    for entry in entries:
        if entry.stable_identity in seen:
            raise ValueError("duplicate ledger identity")
        if (
            entry.generation != head.generation + 1
            or entry.revision_before != head.revision
            or entry.prior_entry_digest != head.last_entry_digest
        ):
            raise ValueError("ledger replay is not contiguous")
        # Reconstructing validates all commitments and final delta fields.
        LedgerEntry(
            generation=entry.generation,
            terminal_kind=entry.terminal_kind,
            stable_identity=entry.stable_identity,
            payload=entry.payload,
            payload_commitment=entry.payload_commitment,
            revision_before=entry.revision_before,
            revision_after=entry.revision_after,
            final_delta_digest=entry.final_delta_digest,
            result_locator=entry.result_locator,
            result_digest=entry.result_digest,
            prior_entry_digest=entry.prior_entry_digest,
            entry_digest=entry.entry_digest,
        )
        seen.add(entry.stable_identity)
        head = LedgerHead(entry.generation, entry.revision_after, entry.entry_digest)
    if expected_head is not None and head != expected_head:
        raise ValueError("ledger replay does not reach persisted head")
    return head
