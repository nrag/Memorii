"""Typed, user-scoped Preference records; deliberately separate from semantic facts."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import RecordAbsentPrecondition, RecordDigestPrecondition, record_digest
from memorii.core.user_context.preference_delegations import (
    PreferenceDelegationRecord,
    PreferenceDelegationRepository,
    new_preference_delegation,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility, TemporalValidityStatus

PreferenceTopicType = Literal["ProductService", "Asset", "Place"]
PreferenceState = Literal["candidate", "confirmed", "superseded", "expired", "rejected", "retracted"]
PreferenceOrigin = Literal["user_assertion", "explicit_user_form", "agent_summary", "inference", "third_party"]
PreferenceEventType = Literal["candidate_observed", "confirmed", "superseded", "expired", "rejected", "retracted"]


def _digest(value: object) -> str:
    payload = json.dumps(value, default=str, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(payload.encode("utf-8")).hexdigest()


def _normalized_key(value: str) -> str:
    return "_".join(value.strip().lower().split())


def preference_topic_id(topic_type: PreferenceTopicType, topic_quote: str) -> str:
    """Return the deterministic identity for a grounded preference topic."""
    normalized = " ".join(topic_quote.strip().split())
    if not normalized:
        raise ValueError("preference topic quote is empty")
    return "preference-topic:" + _digest((topic_type, normalized))


def preference_candidate_sentence(*, topic_quote: str, preference_key: str, value: str, valid_until: datetime | None = None) -> str:
    suffix = "" if valid_until is None else f" until {valid_until.astimezone(UTC).isoformat()}"
    return f"Preference: {topic_quote}; {preference_key}={value}{suffix}."


def preference_confirmation_sentence(*, topic_id: str, preference_key: str, value: str, source_digest: str) -> str:
    return f"Confirm preference: {topic_id}; {preference_key}={value}; source={source_digest}."


def preference_close_sentence(*, state: str, topic_id: str, preference_key: str, value: str, source_digest: str) -> str:
    return f"{state.capitalize()} preference: {topic_id}; {preference_key}={value}; source={source_digest}."


class PreferenceAccessGrant(BaseModel):
    holder_user_id: str = Field(min_length=1, max_length=128)
    agent_id: str = Field(min_length=1, max_length=128)
    delegated: bool = False
    model_config = ConfigDict(extra="forbid", frozen=True)


class PreferenceHolderAuthority(BaseModel):
    """The one agent that acts for a holder without a delegation grant."""

    holder_user_id: str = Field(min_length=1, max_length=128)
    primary_agent_id: str = Field(min_length=1, max_length=128)

    model_config = ConfigDict(extra="forbid", frozen=True)


class PreferenceWriteRequest(BaseModel):
    holder_user_id: str = Field(min_length=1, max_length=128)
    authenticated_author_id: str = Field(min_length=1, max_length=128)
    authenticated_source_id: str = Field(min_length=1, max_length=256)
    authenticated_agent_id: str = Field(min_length=1, max_length=128)
    holder_kind: Literal["Person"] = "Person"
    topic_type: PreferenceTopicType
    canonical_topic_id: str = Field(min_length=1, max_length=256)
    preference_key: str = Field(min_length=1, max_length=96)
    value: str = Field(min_length=1, max_length=512)
    source_id: str = Field(min_length=1, max_length=256)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    assertion_start: int = Field(ge=0)
    assertion_end: int = Field(gt=0)
    origin: PreferenceOrigin
    event_time: datetime
    valid_until: datetime | None = None

    @field_validator("preference_key")
    @classmethod
    def key_is_normalized(cls, value: str) -> str:
        normalized = _normalized_key(value)
        if not normalized or normalized != value:
            raise ValueError("preference_key must be normalized bounded text")
        return value

    @field_validator("event_time", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("preference times must be timezone-aware")
        return value.astimezone(UTC)


class PreferenceRecord(BaseModel):
    preference_id: str
    logical_key: str
    holder_user_id: str
    authenticated_author_id: str
    authenticated_source_id: str
    authenticated_agent_id: str
    topic_type: PreferenceTopicType
    canonical_topic_id: str
    preference_key: str
    value: str
    source_id: str
    source_digest: str
    assertion_start: int
    assertion_end: int
    event_time: datetime
    valid_until: datetime | None
    state: PreferenceState
    predecessor_id: str | None = None
    superseded_id: str | None = None
    record_digest: str
    model_config = ConfigDict(extra="forbid", frozen=True)


class PreferenceEvent(BaseModel):
    event_id: str
    preference_id: str
    holder_user_id: str
    event_type: PreferenceEventType
    actor_id: str
    occurred_at: datetime
    preference_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_source_id: str = Field(min_length=1)
    evidence_source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_start: int = Field(ge=0)
    evidence_end: int = Field(gt=0)
    event_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class PreferenceLogicalHead(BaseModel):
    logical_key: str
    revision: int = Field(ge=1)
    candidate_ids: tuple[str, ...]
    current_confirmed_id: str | None = None
    record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


def _preference_record_digest(record: PreferenceRecord) -> str:
    return _digest(record.model_dump(mode="json", exclude={"record_digest"}))


def _preference_event_digest(event: PreferenceEvent) -> str:
    return _digest(event.model_dump(mode="json", exclude={"event_digest"}))


def _preference_head_digest(head: PreferenceLogicalHead) -> str:
    return _digest(head.model_dump(mode="json", exclude={"record_digest"}))


class PreferenceReadRequest(BaseModel):
    holder_user_id: str
    agent_id: str
    canonical_topic_id: str | None = None
    preference_key: str | None = None
    history: bool = False
    model_config = ConfigDict(extra="forbid", frozen=True)


class PreferenceAccessPolicy:
    def __init__(
        self,
        *,
        holder_authorities: tuple[PreferenceHolderAuthority, ...],
        grants: tuple[PreferenceAccessGrant, ...],
        delegation_repository: PreferenceDelegationRepository | None = None,
    ) -> None:
        self._holder_authorities = {authority.holder_user_id: authority for authority in holder_authorities}
        self._grants = grants
        self._delegation_repository = delegation_repository

    def allows(self, *, holder_user_id: str, agent_id: str) -> bool:
        authority = self._holder_authorities.get(holder_user_id)
        if authority is None:
            return False
        if authority.primary_agent_id == agent_id:
            return True
        configured = any(
            grant.holder_user_id == holder_user_id and grant.agent_id == agent_id and grant.delegated
            for grant in self._grants
        )
        durable = self._delegation_repository is not None and self._delegation_repository.active(
            holder_user_id, agent_id
        )
        return configured or durable

    def is_primary(self, *, holder_user_id: str, agent_id: str) -> bool:
        authority = self._holder_authorities.get(holder_user_id)
        return authority is not None and authority.primary_agent_id == agent_id


class PreferenceService:
    """Canonical persistence/read owner for user preferences."""

    _KIND = "user_preference_v1"
    _EVENT_KIND = "user_preference_event_v1"
    _HEAD_KIND = "user_preference_logical_head_v1"

    def __init__(
        self,
        *,
        memory_plane: MemoryPlaneService,
        policy: PreferenceAccessPolicy,
        delegation_repository: PreferenceDelegationRepository | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._plane = memory_plane
        self._policy = policy
        self._delegations = delegation_repository
        self._now = now or (lambda: datetime.now(UTC))

    def set_delegation(
        self,
        *,
        holder_user_id: str,
        acting_agent_id: str,
        delegated_agent_id: str,
        state: Literal["active", "revoked"],
        evidence: tuple[str, str, int, int],
    ) -> PreferenceDelegationRecord | None:
        if self._delegations is None:
            return None
        if not self._policy.is_primary(holder_user_id=holder_user_id, agent_id=acting_agent_id):
            return None
        previous = self._delegations.load(holder_user_id, delegated_agent_id)
        if previous is not None and previous.state == state:
            return previous
        record = new_preference_delegation(
            holder_user_id=holder_user_id,
            primary_agent_id=acting_agent_id,
            delegated_agent_id=delegated_agent_id,
            state=state,
            evidence=evidence,
            occurred_at=self._now(),
            previous=previous,
        )
        self._delegations.write(record, previous=previous)
        return record

    @staticmethod
    def logical_key(request: PreferenceWriteRequest) -> str:
        return _digest((request.holder_user_id, request.canonical_topic_id, request.preference_key))

    def can_access(self, *, holder_user_id: str, agent_id: str) -> bool:
        return self._policy.allows(holder_user_id=holder_user_id, agent_id=agent_id)

    def create_candidate(self, request: PreferenceWriteRequest) -> PreferenceRecord | None:
        if (
            request.authenticated_author_id != request.holder_user_id
            or request.authenticated_source_id != request.source_id
            or request.origin
            not in {
                "user_assertion",
                "explicit_user_form",
            }
        ):
            return None
        if not self._policy.allows(holder_user_id=request.holder_user_id, agent_id=request.authenticated_agent_id):
            return None
        if request.assertion_end <= request.assertion_start:
            return None
        logical_key = self.logical_key(request)
        existing = self._by_logical_key(logical_key)
        duplicate = next((item for item in existing if item.source_digest == request.source_digest), None)
        if duplicate is not None:
            return duplicate
        current = next((item for item in existing if item.state == "confirmed"), None)
        record = self._new_record(
            request,
            logical_key=logical_key,
            state="candidate",
            predecessor_id=current.preference_id if current is not None else None,
        )
        self._write(
            record,
            predecessor=None,
            events=(self._event(record, event_type="candidate_observed", actor_id=request.authenticated_agent_id),),
        )
        return record

    def confirm(
        self,
        *,
        preference_id: str,
        holder_user_id: str,
        agent_id: str,
        preference_key: str,
        value: str,
        source_digest: str,
        approval_evidence: tuple[str, str, int, int] | None = None,
    ) -> PreferenceRecord | None:
        record = self._load(preference_id)
        if (
            record is None
            or approval_evidence is None
            or record.state != "candidate"
            or record.holder_user_id != holder_user_id
            or (record.preference_key, record.value, record.source_digest) != (preference_key, value, source_digest)
        ):
            return None
        if approval_evidence[:2] == (record.source_id, record.source_digest):
            return None
        if not self._policy.allows(holder_user_id=holder_user_id, agent_id=agent_id):
            return None
        prior = next((item for item in self._by_logical_key(record.logical_key) if item.state == "confirmed"), None)
        confirmed = self._with_state(record, state="confirmed")
        if prior is None:
            self._write(
                confirmed,
                predecessor=record,
                events=(self._event(confirmed, event_type="confirmed", actor_id=agent_id, occurred_at=self._now(), evidence=approval_evidence),),
            )
        else:
            retired = self._with_state(
                prior,
                state="superseded",
                superseded_id=confirmed.preference_id,
            )
            self._write(
                confirmed,
                predecessor=record,
                extra=(retired, prior),
                events=(
                    self._event(confirmed, event_type="confirmed", actor_id=agent_id, occurred_at=self._now(), evidence=approval_evidence),
                    self._event(
                        retired,
                        event_type="superseded",
                        actor_id=agent_id,
                        occurred_at=self._now(),
                        evidence=approval_evidence,
                    ),
                ),
            )
        return confirmed

    def close(
        self,
        *,
        preference_id: str,
        holder_user_id: str,
        agent_id: str,
        preference_key: str,
        value: str,
        source_digest: str,
        state: Literal["expired", "retracted", "rejected"],
        explicit: bool = True,
        evidence: tuple[str, str, int, int] | None = None,
    ) -> PreferenceRecord | None:
        record = self._load(preference_id)
        if (
            record is None
            or evidence is None
            or record.holder_user_id != holder_user_id
            or (record.preference_key, record.value, record.source_digest) != (preference_key, value, source_digest)
            or not explicit
            or not self._policy.allows(holder_user_id=holder_user_id, agent_id=agent_id)
        ):
            return None
        if evidence[:2] == (record.source_id, record.source_digest):
            return None
        if (
            (
                state == "expired"
                and (record.state != "confirmed" or record.valid_until is None or record.valid_until > self._now())
            )
            or (state == "rejected" and record.state != "candidate")
            or (state == "retracted" and record.state != "confirmed")
        ):
            return None
        closed = self._with_state(record, state=state)
        self._write(
            closed,
            predecessor=record,
            events=(self._event(closed, event_type=state, actor_id=agent_id, occurred_at=self._now(), evidence=evidence),),
        )
        return closed

    def read(self, request: PreferenceReadRequest) -> tuple[PreferenceRecord, ...]:
        if not self._policy.allows(holder_user_id=request.holder_user_id, agent_id=request.agent_id):
            return ()
        records = [item for item in self._all() if item.holder_user_id == request.holder_user_id]
        if request.canonical_topic_id:
            records = [item for item in records if item.canonical_topic_id == request.canonical_topic_id]
        if request.preference_key:
            records = [item for item in records if item.preference_key == request.preference_key]
        if not request.history:
            now = self._now()
            records = [
                item
                for item in records
                if item.state == "confirmed" and (item.valid_until is None or item.valid_until > now)
            ]
        return tuple(sorted(records, key=lambda item: item.preference_id))

    def read_events(self, request: PreferenceReadRequest) -> tuple[PreferenceEvent, ...]:
        if not self._policy.allows(holder_user_id=request.holder_user_id, agent_id=request.agent_id):
            return ()
        return tuple(
            sorted(
                (item for item in self._all_events() if item.holder_user_id == request.holder_user_id),
                key=lambda item: item.event_id,
            )
        )

    def _new_record(
        self,
        request: PreferenceWriteRequest,
        *,
        logical_key: str,
        state: PreferenceState,
        predecessor_id: str | None,
    ) -> PreferenceRecord:
        preference_id = "user-preference:" + _digest((logical_key, request.source_digest, request.value))
        body = dict(
            preference_id=preference_id,
            logical_key=logical_key,
            holder_user_id=request.holder_user_id,
            authenticated_author_id=request.authenticated_author_id,
            authenticated_source_id=request.authenticated_source_id,
            authenticated_agent_id=request.authenticated_agent_id,
            topic_type=request.topic_type,
            canonical_topic_id=request.canonical_topic_id,
            preference_key=request.preference_key,
            value=request.value,
            source_id=request.source_id,
            source_digest=request.source_digest,
            assertion_start=request.assertion_start,
            assertion_end=request.assertion_end,
            event_time=request.event_time,
            valid_until=request.valid_until,
            state=state,
            predecessor_id=predecessor_id,
        )
        record = PreferenceRecord(**body, record_digest="")
        return record.model_copy(update={"record_digest": _preference_record_digest(record)})

    @staticmethod
    def _with_state(
        record: PreferenceRecord,
        *,
        state: PreferenceState,
        superseded_id: str | None = None,
    ) -> PreferenceRecord:
        updated = record.model_copy(update={"state": state, "superseded_id": superseded_id, "record_digest": ""})
        return updated.model_copy(update={"record_digest": _preference_record_digest(updated)})

    @staticmethod
    def _event(
        preference: PreferenceRecord,
        *,
        event_type: PreferenceEventType,
        actor_id: str,
        occurred_at: datetime | None = None,
        evidence: tuple[str, str, int, int] | None = None,
    ) -> PreferenceEvent:
        occurred_at = occurred_at or preference.event_time
        evidence = evidence or (
            preference.source_id,
            preference.source_digest,
            preference.assertion_start,
            preference.assertion_end,
        )
        event_id = "user-preference-event:" + _digest(
            (preference.preference_id, event_type, preference.record_digest, occurred_at.isoformat())
        )
        event = PreferenceEvent(
            event_id=event_id,
            preference_id=preference.preference_id,
            holder_user_id=preference.holder_user_id,
            event_type=event_type,
            actor_id=actor_id,
            occurred_at=occurred_at,
            preference_record_digest=preference.record_digest,
            evidence_source_id=evidence[0],
            evidence_source_digest=evidence[1],
            evidence_start=evidence[2],
            evidence_end=evidence[3],
            event_digest="0" * 64,
        )
        return event.model_copy(update={"event_digest": _preference_event_digest(event)})

    def _record(self, preference: PreferenceRecord) -> CanonicalMemoryRecord:
        return CanonicalMemoryRecord(
            memory_id=preference.preference_id,
            domain=MemoryDomain.USER,
            text=preference.value,
            content={"kind": self._KIND, "preference": preference.model_dump(mode="json")},
            status=CommitStatus.COMMITTED,
            validity_status=TemporalValidityStatus.ACTIVE,
            source_kind=self._KIND,
            timestamp=preference.event_time,
            valid_from=preference.event_time,
            valid_to=preference.valid_until,
            user_id=preference.holder_user_id,
            agent_id=preference.authenticated_agent_id,
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )

    def _event_record(self, event: PreferenceEvent) -> CanonicalMemoryRecord:
        return CanonicalMemoryRecord(
            memory_id=event.event_id,
            domain=MemoryDomain.USER,
            text=event.event_type,
            content={"kind": self._EVENT_KIND, "event": event.model_dump(mode="json")},
            status=CommitStatus.COMMITTED,
            validity_status=TemporalValidityStatus.ACTIVE,
            source_kind=self._EVENT_KIND,
            timestamp=event.occurred_at,
            user_id=event.holder_user_id,
            agent_id=event.actor_id,
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )

    @staticmethod
    def _head_id(logical_key: str) -> str:
        return "user-preference-head:" + logical_key

    def _head_record(self, head: PreferenceLogicalHead) -> CanonicalMemoryRecord:
        return CanonicalMemoryRecord(
            memory_id=self._head_id(head.logical_key), domain=MemoryDomain.USER, text=head.logical_key,
            content={"kind": self._HEAD_KIND, "head": head.model_dump(mode="json")}, status=CommitStatus.COMMITTED,
            validity_status=TemporalValidityStatus.ACTIVE, source_kind=self._HEAD_KIND, timestamp=datetime(1970, 1, 1, tzinfo=UTC),
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )

    def _write(
        self,
        preference: PreferenceRecord,
        *,
        predecessor: PreferenceRecord | None,
        extra: tuple[PreferenceRecord, PreferenceRecord] | None = None,
        events: tuple[PreferenceEvent, ...],
        head_snapshot: PreferenceLogicalHead | None = None,
    ) -> None:
        prior_head = head_snapshot if head_snapshot is not None else self._load_head(preference.logical_key)
        candidates = set(prior_head.candidate_ids if prior_head is not None else ())
        if preference.state == "candidate":
            candidates.add(preference.preference_id)
        else:
            candidates.discard(preference.preference_id)
        current = prior_head.current_confirmed_id if prior_head is not None else None
        if preference.state == "confirmed":
            current = preference.preference_id
        elif current == preference.preference_id:
            current = None
        draft_head = PreferenceLogicalHead(
            logical_key=preference.logical_key, revision=(prior_head.revision + 1 if prior_head else 1),
            candidate_ids=tuple(sorted(candidates)), current_confirmed_id=current, record_digest="0" * 64,
        )
        head = draft_head.model_copy(update={"record_digest": _preference_head_digest(draft_head)})
        records = [self._record(preference), self._head_record(head), *(self._event_record(event) for event in events)]
        conditions = []
        if predecessor is None:
            conditions.append(RecordAbsentPrecondition(memory_id=preference.preference_id))
        else:
            conditions.append(
                RecordDigestPrecondition(
                    memory_id=predecessor.preference_id,
                    expected_digest=record_digest(self._record(predecessor)),
                )
            )
        if prior_head is None:
            conditions.append(RecordAbsentPrecondition(memory_id=self._head_id(preference.logical_key)))
        else:
            conditions.append(RecordDigestPrecondition(memory_id=self._head_id(preference.logical_key), expected_digest=record_digest(self._head_record(prior_head))))
        if extra is not None:
            records.append(self._record(extra[0]))
            conditions.append(
                RecordDigestPrecondition(
                    memory_id=extra[1].preference_id,
                    expected_digest=record_digest(self._record(extra[1])),
                )
            )
        conditions.extend(RecordAbsentPrecondition(memory_id=event.event_id) for event in events)
        self._plane.conditionally_write_records(tuple(records), preconditions=tuple(conditions))

    def _load(self, preference_id: str) -> PreferenceRecord | None:
        item = self._plane.get_record(preference_id)
        if item is None or item.domain != MemoryDomain.USER or item.source_kind != self._KIND:
            return None
        try:
            record = PreferenceRecord.model_validate(item.content["preference"])
            return record if record.record_digest == _preference_record_digest(record) else None
        except (KeyError, TypeError, ValueError):
            return None

    def _all(self) -> list[PreferenceRecord]:
        return [
            item
            for record in self._plane.list_records(domains=[MemoryDomain.USER], source_kind=self._KIND)
            if (item := self._load(record.memory_id)) is not None
        ]

    def _by_logical_key(self, key: str) -> list[PreferenceRecord]:
        return [item for item in self._all() if item.logical_key == key]

    def _load_head(self, logical_key: str) -> PreferenceLogicalHead | None:
        item = self._plane.get_record(self._head_id(logical_key))
        if item is None or item.source_kind != self._HEAD_KIND:
            return None
        try:
            head = PreferenceLogicalHead.model_validate(item.content["head"])
            return head if head.record_digest == _preference_head_digest(head) else None
        except (KeyError, TypeError, ValueError):
            return None

    def load_head(self, logical_key: str) -> PreferenceLogicalHead | None:
        """Return the verified persisted head for diagnostics and retry handling."""
        return self._load_head(logical_key)

    def load_preference(self, preference_id: str) -> PreferenceRecord | None:
        """Return one verified preference record for protected tool validation."""
        return self._load(preference_id)

    def _load_event(self, event_id: str) -> PreferenceEvent | None:
        item = self._plane.get_record(event_id)
        if item is None or item.domain != MemoryDomain.USER or item.source_kind != self._EVENT_KIND:
            return None
        try:
            event = PreferenceEvent.model_validate(item.content["event"])
            return event if event.event_digest == _preference_event_digest(event) else None
        except (KeyError, TypeError, ValueError):
            return None

    def _all_events(self) -> list[PreferenceEvent]:
        return [
            item
            for record in self._plane.list_records(domains=[MemoryDomain.USER], source_kind=self._EVENT_KIND)
            if (item := self._load_event(record.memory_id)) is not None
        ]
