"""Durable, verified delegation records for user Preference access."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import RecordAbsentPrecondition, RecordDigestPrecondition, record_digest
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility, TemporalValidityStatus


def _digest(value: object) -> str:
    payload = json.dumps(value, default=str, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(payload.encode("utf-8")).hexdigest()


class PreferenceDelegationRecord(BaseModel):
    holder_user_id: str = Field(min_length=1, max_length=128)
    primary_agent_id: str = Field(min_length=1, max_length=128)
    delegated_agent_id: str = Field(min_length=1, max_length=128)
    state: Literal["active", "revoked"]
    evidence_source_id: str = Field(min_length=1, max_length=256)
    evidence_source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_start: int = Field(ge=0)
    evidence_end: int = Field(gt=0)
    occurred_at: datetime
    revision: int = Field(ge=1)
    record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


def new_preference_delegation(
    *,
    holder_user_id: str,
    primary_agent_id: str,
    delegated_agent_id: str,
    state: Literal["active", "revoked"],
    evidence: tuple[str, str, int, int],
    occurred_at: datetime,
    previous: PreferenceDelegationRecord | None = None,
) -> PreferenceDelegationRecord:
    if primary_agent_id == delegated_agent_id:
        raise ValueError("preference delegation cannot target the primary agent")
    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
        raise ValueError("preference delegation time must be timezone-aware")
    if previous is not None and (
        previous.holder_user_id,
        previous.primary_agent_id,
        previous.delegated_agent_id,
    ) != (holder_user_id, primary_agent_id, delegated_agent_id):
        raise ValueError("preference delegation identity is immutable")
    draft = PreferenceDelegationRecord(
        holder_user_id=holder_user_id,
        primary_agent_id=primary_agent_id,
        delegated_agent_id=delegated_agent_id,
        state=state,
        evidence_source_id=evidence[0],
        evidence_source_digest=evidence[1],
        evidence_start=evidence[2],
        evidence_end=evidence[3],
        occurred_at=occurred_at.astimezone(UTC),
        revision=1 if previous is None else previous.revision + 1,
        record_digest="0" * 64,
    )
    body = draft.model_dump(mode="json", exclude={"record_digest"})
    return draft.model_copy(update={"record_digest": _digest(body)})


class PreferenceDelegationRepository:
    _KIND = "user_preference_delegation_v1"

    def __init__(self, memory_plane: MemoryPlaneService) -> None:
        self._plane = memory_plane

    @staticmethod
    def record_id(holder_user_id: str, delegated_agent_id: str) -> str:
        return "user-preference-delegation:" + _digest((holder_user_id, delegated_agent_id))

    def load(self, holder_user_id: str, delegated_agent_id: str) -> PreferenceDelegationRecord | None:
        item = self._plane.get_record(self.record_id(holder_user_id, delegated_agent_id))
        if item is None or item.domain != MemoryDomain.USER or item.source_kind != self._KIND:
            return None
        try:
            record = PreferenceDelegationRecord.model_validate(item.content["delegation"])
            expected = _digest(record.model_dump(mode="json", exclude={"record_digest"}))
            return record if record.record_digest == expected else None
        except (KeyError, TypeError, ValueError):
            return None

    def active(self, holder_user_id: str, delegated_agent_id: str) -> bool:
        record = self.load(holder_user_id, delegated_agent_id)
        return record is not None and record.state == "active"

    def write(self, record: PreferenceDelegationRecord, *, previous: PreferenceDelegationRecord | None) -> None:
        item = self._record(record)
        conditions = (
            (RecordAbsentPrecondition(memory_id=item.memory_id),)
            if previous is None
            else (
                RecordDigestPrecondition(
                    memory_id=item.memory_id,
                    expected_digest=record_digest(self._record(previous)),
                ),
            )
        )
        self._plane.conditionally_write_records((item,), preconditions=conditions)

    def _record(self, record: PreferenceDelegationRecord) -> CanonicalMemoryRecord:
        return CanonicalMemoryRecord(
            memory_id=self.record_id(record.holder_user_id, record.delegated_agent_id),
            domain=MemoryDomain.USER,
            text=record.state,
            content={"kind": self._KIND, "delegation": record.model_dump(mode="json")},
            status=CommitStatus.COMMITTED,
            validity_status=TemporalValidityStatus.ACTIVE,
            source_kind=self._KIND,
            timestamp=record.occurred_at,
            user_id=record.holder_user_id,
            agent_id=record.primary_agent_id,
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )
