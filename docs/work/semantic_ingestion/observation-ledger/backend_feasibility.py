"""Neutral backend-mechanics probe for MemoryPlane conditional batches.

This is not an observation-ledger implementation and does not admit semantic
records.  It only demonstrates that the existing durable MemoryPlane backend
can atomically replace one mutable head while creating immutable entry/result
records under the corresponding digest and absence preconditions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    MemoryPlaneRevisionConflictError,
    RecordAbsentPrecondition,
    RecordDigestPrecondition,
    record_digest,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility

_NEUTRAL_SOURCE_KIND = "backend_feasibility_neutral_mechanics"
_HEAD_ID = "backend-feasibility:neutral-head"
_TIMESTAMP = datetime(2026, 9, 6, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class NeutralAppendRequest:
    """Immutable input for a non-semantic backend conditional-batch probe."""

    source_id: str
    request_id: str
    payload: str

    def __post_init__(self) -> None:
        if not all(isinstance(value, str) and value for value in (self.source_id, self.request_id, self.payload)):
            raise ValueError("neutral backend request fields must be nonempty strings")


@dataclass(frozen=True, slots=True)
class PreparedNeutralAppend:
    request: NeutralAppendRequest
    expected_head_digest: str | None
    expected_generation: int


@dataclass(frozen=True, slots=True)
class NeutralAppendReceipt:
    entry: CanonicalMemoryRecord
    result: CanonicalMemoryRecord
    head: CanonicalMemoryRecord


class NeutralConditionalBatchProbe:
    """Uses the public service batch API without semantic-ingestion identities."""

    def __init__(self, plane: MemoryPlaneService) -> None:
        self._plane = plane

    def prepare(self, request: NeutralAppendRequest) -> PreparedNeutralAppend:
        head = self._plane.get_record(_HEAD_ID)
        if head is None:
            return PreparedNeutralAppend(request=request, expected_head_digest=None, expected_generation=0)
        return PreparedNeutralAppend(
            request=request,
            expected_head_digest=record_digest(head),
            expected_generation=_head_generation(head),
        )

    def append(self, prepared: PreparedNeutralAppend) -> NeutralAppendReceipt:
        request = prepared.request
        entry_id = _entry_id(request)
        existing_entry = self._plane.get_record(entry_id)
        if existing_entry is not None:
            return self._reload_exact(existing_entry, request)

        result = _result_record(request)
        entry = _entry_record(
            request=request,
            generation=prepared.expected_generation + 1,
            expected_head_digest=prepared.expected_head_digest,
            result=result,
        )
        head = _head_record(
            generation=prepared.expected_generation + 1,
            previous_head_digest=prepared.expected_head_digest,
            last_entry_id=entry.memory_id,
        )
        head_precondition = (
            RecordAbsentPrecondition(memory_id=_HEAD_ID)
            if prepared.expected_head_digest is None
            else RecordDigestPrecondition(
                memory_id=_HEAD_ID,
                expected_digest=prepared.expected_head_digest,
            )
        )
        self._plane.conditionally_write_records(
            (head, entry, result),
            preconditions=(
                head_precondition,
                RecordAbsentPrecondition(memory_id=entry.memory_id),
                RecordAbsentPrecondition(memory_id=result.memory_id),
            ),
        )
        return NeutralAppendReceipt(entry=entry, result=result, head=head)

    def _reload_exact(
        self,
        entry: CanonicalMemoryRecord,
        request: NeutralAppendRequest,
    ) -> NeutralAppendReceipt:
        expected_entry = _entry_record(
            request=request,
            generation=_entry_generation(entry),
            expected_head_digest=_entry_expected_head_digest(entry),
            result=_result_record(request),
        )
        if entry != expected_entry:
            raise ValueError("neutral backend request identity has changed immutable content")
        result = self._plane.get_record(_result_id(request))
        head = self._plane.get_record(_HEAD_ID)
        if result != _result_record(request) or head is None:
            raise ValueError("neutral backend batch cannot exactly reload committed records")
        return NeutralAppendReceipt(entry=entry, result=result, head=head)


def _record(
    *,
    memory_id: str,
    text: str,
    content: dict[str, object],
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=MemoryDomain.EXECUTION,
        text=text,
        content=content,
        status=CommitStatus.COMMITTED,
        source_kind=_NEUTRAL_SOURCE_KIND,
        timestamp=_TIMESTAMP,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _entry_id(request: NeutralAppendRequest) -> str:
    return f"backend-feasibility:entry:{request.source_id}:{request.request_id}"


def _result_id(request: NeutralAppendRequest) -> str:
    return f"backend-feasibility:result:{request.source_id}:{request.request_id}"


def _payload_digest(request: NeutralAppendRequest) -> str:
    return sha256(request.payload.encode("utf-8")).hexdigest()


def _result_record(request: NeutralAppendRequest) -> CanonicalMemoryRecord:
    return _record(
        memory_id=_result_id(request),
        text="neutral backend result",
        content={
            "source_id": request.source_id,
            "request_id": request.request_id,
            "payload_digest": _payload_digest(request),
        },
    )


def _entry_record(
    *,
    request: NeutralAppendRequest,
    generation: int,
    expected_head_digest: str | None,
    result: CanonicalMemoryRecord,
) -> CanonicalMemoryRecord:
    return _record(
        memory_id=_entry_id(request),
        text="neutral backend immutable entry",
        content={
            "source_id": request.source_id,
            "request_id": request.request_id,
            "generation": generation,
            "expected_head_digest": expected_head_digest,
            "result_id": result.memory_id,
            "result_digest": record_digest(result),
        },
    )


def _head_record(
    *,
    generation: int,
    previous_head_digest: str | None,
    last_entry_id: str,
) -> CanonicalMemoryRecord:
    return _record(
        memory_id=_HEAD_ID,
        text="neutral backend mutable head",
        content={
            "generation": generation,
            "previous_head_digest": previous_head_digest,
            "last_entry_id": last_entry_id,
        },
    )


def _head_generation(head: CanonicalMemoryRecord) -> int:
    generation = head.content.get("generation")
    if type(generation) is not int or generation < 0:
        raise ValueError("neutral backend head is invalid")
    return generation


def _entry_generation(entry: CanonicalMemoryRecord) -> int:
    generation = entry.content.get("generation")
    if type(generation) is not int or generation < 1:
        raise ValueError("neutral backend entry is invalid")
    return generation


def _entry_expected_head_digest(entry: CanonicalMemoryRecord) -> str | None:
    digest = entry.content.get("expected_head_digest")
    if digest is not None and (not isinstance(digest, str) or len(digest) != 64):
        raise ValueError("neutral backend entry has invalid head digest")
    return digest


__all__ = [
    "MemoryPlaneRevisionConflictError",
    "NeutralAppendReceipt",
    "NeutralAppendRequest",
    "NeutralConditionalBatchProbe",
    "PreparedNeutralAppend",
]
