"""Append-only authenticated reader for conflict attention."""

from __future__ import annotations

import base64
import binascii
import fcntl
import hashlib
import hmac
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from secrets import token_hex
from threading import Event, Lock, Thread
from typing import TYPE_CHECKING, Literal, Protocol, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.conflict_attention import (
    INTEGRITY_ATTENTION_QUESTION,
    AgentClarificationProposal,
    ClarificationAttemptOutcome,
    ClarificationFailureClass,
    ClarificationSubmissionOutcome,
    ConflictAccessContext,
    ConflictAttention,
    ConflictAttentionPage,
    ConflictAudience,
    ConflictClarificationAttempt,
    ConflictClarificationAttemptResult,
    ConflictClarificationClaim,
    ConflictClarificationOperationReceipt,
    ConflictClarificationProcessingReceipt,
    ConflictClarificationSemanticPipeline,
    ConflictClarificationSubmissionResult,
    ConflictClarificationWork,
    ConflictKind,
    ConflictListingCursorClaims,
    ConflictListingSnapshot,
    ConflictListRequest,
    ConflictResolutionRequest,
    ConflictStateTransition,
    ConflictStatus,
    ConflictTransitionReason,
    VerifiedUserConfirmation,
    build_agent_clarification_proposal,
)

if TYPE_CHECKING:
    from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
    from memorii.core.memory_evolution.conflict_integrity import (
        ConflictIntegrityIncidentEvidence,
    )
from memorii.core.memory_evolution.ingestion_contracts import (
    decode_typed_value,
    encode_typed_value,
    normalize_delivery_id,
)

_CURSOR_DOMAIN = b"memorii.conflict-listing-cursor.v1\0"
_CONFLICT_ENTRY_DOMAIN = b"memorii.conflict-attention-ledger-entry.v1\0"
_SNAPSHOT_DOMAIN = b"memorii.conflict-listing-snapshot.v1\0"
_CLARIFICATION_GENERATION_DOMAIN = b"memorii.conflict-clarification-generation.v1\0"
_CLARIFICATION_OPERATION_RECEIPT_DOMAIN = b"memorii.conflict-clarification-operation-receipt.v1\0"
_CONFLICT_REVISION_DOMAIN = b"memorii.conflict-revision.v1\0"
_CONFLICT_TRANSITION_DOMAIN = b"memorii.conflict-state-transition.v1\0"
_PROCESSING_OPERATION_DOMAIN = b"memorii.conflict-clarification-processing-operation.v1\0"
_WORK_DOMAIN = b"memorii.conflict-clarification-work.v1\0"
_ATTEMPT_ID_DOMAIN = b"memorii.conflict-clarification-attempt-id.v1\0"
_ATTEMPT_DOMAIN = b"memorii.conflict-clarification-attempt.v1\0"
_ATTEMPT_RESULT_DOMAIN = b"memorii.conflict-clarification-attempt-result.v1\0"
_INTEGRITY_CONFLICT_ID_DOMAIN = b"memorii.storage-integrity-conflict-id.v1\0"
_INTEGRITY_SCOPE_DOMAIN = b"memorii.storage-integrity-attention-scope.v1\0"
_CURSOR_LIFETIME = timedelta(seconds=900)


@dataclass
class _ReplayState:
    introductions: dict[str, _ConflictLedgerEntry] = field(default_factory=dict)
    current: dict[str, ConflictAttention] = field(default_factory=dict)
    operations: dict[str, ConflictClarificationOperationReceipt] = field(default_factory=dict)
    proposals: dict[str, AgentClarificationProposal] = field(default_factory=dict)
    works: dict[str, ConflictClarificationWork] = field(default_factory=dict)
    attempts: dict[str, list[ConflictClarificationAttempt]] = field(default_factory=dict)
    results: dict[str, ConflictClarificationAttemptResult] = field(default_factory=dict)
    consumed_nonces: set[str] = field(default_factory=set)
    transition_count: int = 0


class ConflictAttentionReadError(ValueError):
    """Non-disclosing authenticated read failure."""


class ConflictClarificationError(ValueError):
    """Closed clarification mutation failure."""


class ClarificationPipelineError(RuntimeError):
    """An explicitly classified failure before a semantic receipt exists."""

    def __init__(self, failure_class: ClarificationFailureClass):
        self.failure_class = failure_class
        super().__init__(failure_class.value)


class ConflictCursorKey(BaseModel):
    key_id: str
    key_epoch: int = Field(ge=1)
    secret: bytes = Field(min_length=32, max_length=32)
    valid_from: datetime
    expires_at: datetime
    signing: bool
    revoked: bool = False

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_window(self) -> ConflictCursorKey:
        for value in (self.valid_from, self.expires_at):
            if value.tzinfo is None or value.utcoffset() is None or value.utcoffset() != timedelta(0):
                raise ValueError("cursor key instants must be UTC")
        if self.expires_at <= self.valid_from:
            raise ValueError("cursor key expiry must follow activation")
        return self


class ConflictAttentionRepository(Protocol):
    def list_conflicts(
        self,
        access: ConflictAccessContext,
        request: ConflictListRequest,
    ) -> ConflictAttentionPage: ...


class ConflictClarificationRepository(ConflictAttentionRepository, Protocol):
    def preflight_clarification(
        self,
        access: ConflictAccessContext,
        request: ConflictResolutionRequest,
        request_digest: str,
    ) -> ConflictClarificationSubmissionResult | None: ...

    def get_resolution_target(
        self,
        access: ConflictAccessContext,
        conflict_id: str,
    ) -> ConflictAttention: ...

    def submit_clarification(
        self,
        access: ConflictAccessContext,
        request: ConflictResolutionRequest,
        request_digest: str,
        proposal: AgentClarificationProposal,
        verified_confirmation: VerifiedUserConfirmation | None,
    ) -> ConflictClarificationSubmissionResult: ...


class _ConflictLedgerEntry(BaseModel):
    schema_version: Literal[1] = 1
    record_type: Literal["conflict"] = "conflict"
    scope_ids: tuple[str, ...]
    attention: ConflictAttention
    entry_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_entry(self) -> _ConflictLedgerEntry:
        if not self.scope_ids or tuple(sorted(set(self.scope_ids), key=lambda value: value.encode("utf-8"))) != self.scope_ids:
            raise ValueError("conflict scopes must be nonempty and canonical")
        for scope_id in self.scope_ids:
            normalize_delivery_id(scope_id)
        if self.attention.status != ConflictStatus.OPEN:
            raise ValueError("the listing ledger accepts only open conflict introductions")
        if self.entry_digest != _digest(_CONFLICT_ENTRY_DOMAIN, _conflict_entry_payload(self)):
            raise ValueError("conflict ledger entry digest mismatch")
        return self


class _SnapshotLedgerEntry(BaseModel):
    schema_version: Literal[1] = 1
    record_type: Literal["snapshot"] = "snapshot"
    snapshot: ConflictListingSnapshot

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_snapshot_digest(self) -> _SnapshotLedgerEntry:
        expected = _digest(_SNAPSHOT_DOMAIN, _snapshot_payload(self.snapshot))
        if self.snapshot.snapshot_digest != expected:
            raise ValueError("listing snapshot digest mismatch")
        return self


class _ClarificationGenerationEntry(BaseModel):
    schema_version: Literal[1] = 1
    record_type: Literal["clarification_generation"] = "clarification_generation"
    operation_receipt: ConflictClarificationOperationReceipt | None = None
    proposal: AgentClarificationProposal | None = None
    verified_confirmation: VerifiedUserConfirmation | None = None
    work: ConflictClarificationWork
    attempt: ConflictClarificationAttempt | None = None
    attempt_results: tuple[ConflictClarificationAttemptResult, ...] = ()
    transition: ConflictStateTransition | None = None
    generation_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_generation(self) -> _ClarificationGenerationEntry:
        submission = self.operation_receipt is not None
        if submission != (self.proposal is not None):
            raise ValueError("submission generation members must be complete")
        if submission and self.transition is None:
            raise ValueError("submission generation requires its transition")
        if submission and (self.attempt is not None or self.attempt_results):
            raise ValueError("submission generation cannot contain processing members")
        if not submission and self.verified_confirmation is not None:
            raise ValueError("processing generation cannot contain confirmation proof")
        if self.generation_digest != _digest(
            _CLARIFICATION_GENERATION_DOMAIN,
            self.model_dump(mode="json", exclude={"generation_digest"}),
        ):
            raise ValueError("clarification generation digest mismatch")
        return self


_LedgerEntry: TypeAlias = _ConflictLedgerEntry | _SnapshotLedgerEntry | _ClarificationGenerationEntry


class FileConflictAttentionRepository:
    """Process-safe JSONL carrier for typed conflict and listing-snapshot records."""

    def __init__(
        self,
        path: Path,
        *,
        keys: tuple[ConflictCursorKey, ...],
        now_provider: Callable[[], datetime] | None = None,
        repository_id: str = "conflict-attention",
        policy_fingerprint: str | None = None,
    ) -> None:
        self._path = path
        self._now = now_provider or (lambda: datetime.now(UTC))
        now = self._now()
        key_coordinates = {(key.key_id, key.key_epoch) for key in keys}
        if len(key_coordinates) != len(keys):
            raise ValueError("cursor key coordinates must be unique")
        signing = [key for key in keys if key.signing]
        if len(signing) != 1 or not self._key_may_sign(signing[0], now):
            raise ValueError("exactly one active cursor signing key is required")
        self._keys = {(key.key_id, key.key_epoch): key for key in keys}
        self._active = signing[0]
        self._repository_id = normalize_delivery_id(repository_id)
        self._policy_fingerprint = policy_fingerprint or hashlib.sha256(
            b"memorii.conflict-attention-policy.v1"
        ).hexdigest()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)

    def append_open(self, attention: ConflictAttention, *, scope_ids: tuple[str, ...]) -> None:
        payload = {
            "schema_version": 1,
            "record_type": "conflict",
            "scope_ids": scope_ids,
            "attention": attention.model_dump(mode="json"),
        }
        entry = _ConflictLedgerEntry(
            scope_ids=scope_ids,
            attention=attention,
            entry_digest=_digest(_CONFLICT_ENTRY_DOMAIN, payload),
        )
        self._append(entry)

    def append_storage_integrity_incident(
        self,
        evidence: ConflictIntegrityIncidentEvidence,
    ) -> ConflictAttention:
        """Publish one idempotent, sanitized operator item for retained incident evidence."""

        from memorii.core.memory_evolution.conflict_integrity import (
            ConflictIntegrityIncidentEvidence,
        )

        try:
            retained = ConflictIntegrityIncidentEvidence.model_validate(
                evidence.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise ConflictClarificationError("conflict_attention_corrupt") from exc
        return self.append_sanitized_storage_integrity_incident(
            repository_id=retained.repository_id,
            incident_evidence_digest=retained.evidence_digest,
            frozen_scope_ids=retained.frozen_partition_ids,
            recorded_at=retained.recorded_at,
        )

    def append_sanitized_storage_integrity_incident(
        self,
        *,
        repository_id: str,
        incident_evidence_digest: str,
        frozen_scope_ids: tuple[str, ...],
        recorded_at: datetime,
    ) -> ConflictAttention:
        """Publish sanitized pull attention from another durable incident owner."""

        repository_id = normalize_delivery_id(repository_id)
        if not re.fullmatch(r"[0-9a-f]{64}", incident_evidence_digest):
            raise ConflictClarificationError("conflict_attention_corrupt")
        scope_ids = tuple(sorted(set(frozen_scope_ids)))
        if not scope_ids or scope_ids != frozen_scope_ids:
            raise ConflictClarificationError("conflict_attention_corrupt")
        recorded_at = recorded_at.astimezone(UTC)
        conflict_id = _digest(
            _INTEGRITY_CONFLICT_ID_DOMAIN,
            {
                "repository_id": repository_id,
                "incident_evidence_digest": incident_evidence_digest,
            },
        )
        try:
            handle = self._path.open("r+", encoding="utf-8")
        except OSError as exc:
            raise ConflictClarificationError("conflict_attention_corrupt") from exc
        with handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                state = self._replay(self._decode_ledger_lines(tuple(handle)))
            except (TypeError, ValueError) as exc:
                raise ConflictClarificationError("conflict_attention_corrupt") from exc
            existing = state.introductions.get(conflict_id)
            if existing is not None:
                if (
                    existing.scope_ids != scope_ids
                    or existing.attention.conflict_revision != incident_evidence_digest
                    or existing.attention.kind != ConflictKind.STORAGE_INTEGRITY
                ):
                    raise ConflictClarificationError("conflict_attention_corrupt")
                return existing.attention
            creation_coordinate = 1 + max(
                (entry.attention.creation_coordinate for entry in state.introductions.values()),
                default=-1,
            )
            attention = ConflictAttention(
                conflict_id=conflict_id,
                conflict_revision=incident_evidence_digest,
                kind=ConflictKind.STORAGE_INTEGRITY,
                audience=ConflictAudience.OPERATOR,
                status=ConflictStatus.OPEN,
                question=INTEGRITY_ATTENTION_QUESTION,
                options=(),
                created_at=recorded_at,
                creation_coordinate=creation_coordinate,
                scope_digest=_digest(
                    _INTEGRITY_SCOPE_DOMAIN,
                    {"repository_id": repository_id, "scope_ids": scope_ids},
                ),
            )
            payload = {
                "schema_version": 1,
                "record_type": "conflict",
                "scope_ids": scope_ids,
                "attention": attention.model_dump(mode="json"),
            }
            self._append_locked(
                handle,
                _ConflictLedgerEntry(
                    scope_ids=scope_ids,
                    attention=attention,
                    entry_digest=_digest(_CONFLICT_ENTRY_DOMAIN, payload),
                ),
            )
            return attention

    def preflight_clarification(
        self,
        access: ConflictAccessContext,
        request: ConflictResolutionRequest,
        request_digest: str,
    ) -> ConflictClarificationSubmissionResult | None:
        records = self._read_all()
        state = self._replay(records)
        retained = state.operations.get(request.operation_id)
        if retained is None:
            return None
        introduction = state.introductions.get(retained.conflict_id)
        if introduction is None or not set(introduction.scope_ids) <= set(access.authorized_scope_ids):
            raise ConflictClarificationError("conflict_attention_authorization_required")
        if retained.request_digest != request_digest:
            raise ConflictClarificationError("conflict_operation_mismatch")
        return ConflictClarificationSubmissionResult(
            outcome=ClarificationSubmissionOutcome.IDEMPOTENT,
            operation_receipt=retained,
        )

    def get_resolution_target(
        self,
        access: ConflictAccessContext,
        conflict_id: str,
    ) -> ConflictAttention:
        state = self._replay(self._read_all())
        _, current = self._authorized_current(state, access, conflict_id)
        return current

    def submit_clarification(
        self,
        access: ConflictAccessContext,
        request: ConflictResolutionRequest,
        request_digest: str,
        proposal: AgentClarificationProposal,
        verified_confirmation: VerifiedUserConfirmation | None,
    ) -> ConflictClarificationSubmissionResult:
        try:
            handle = self._path.open("r+", encoding="utf-8")
        except OSError as exc:
            raise ConflictClarificationError("conflict_attention_corrupt") from exc
        with handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                records = self._decode_ledger_lines(tuple(handle))
                state = self._replay(records)
                retained = state.operations.get(request.operation_id)
                if retained is not None:
                    introduction = state.introductions.get(retained.conflict_id)
                    if introduction is None or not set(introduction.scope_ids) <= set(access.authorized_scope_ids):
                        raise ConflictClarificationError("conflict_attention_authorization_required")
                    if retained.request_digest != request_digest:
                        raise ConflictClarificationError("conflict_operation_mismatch")
                    return ConflictClarificationSubmissionResult(
                        outcome=ClarificationSubmissionOutcome.IDEMPOTENT,
                        operation_receipt=retained,
                    )
                introduction, current = self._authorized_current(state, access, request.conflict_id)
                if current.kind.value == "storage_integrity":
                    raise ConflictClarificationError("operator_action_required")
                if current.status != ConflictStatus.OPEN or current.conflict_revision != request.expected_conflict_revision:
                    return ConflictClarificationSubmissionResult(
                        outcome=ClarificationSubmissionOutcome.STALE_REVISION,
                        attention=current,
                    )
                candidate_ids = {option.candidate_id for option in current.options}
                if not set(request.selected_candidate_ids) <= candidate_ids:
                    raise ConflictClarificationError("invalid_conflict_resolution")
                if (
                    proposal.conflict_id != request.conflict_id
                    or proposal.conflict_revision != request.expected_conflict_revision
                    or proposal.operation_id != request.operation_id
                    or proposal.request_digest != request_digest
                    or proposal.agent_principal_id != access.principal_id
                    or proposal.scope_digest != current.scope_digest
                ):
                    raise ConflictClarificationError("invalid_conflict_resolution")
                expected_proposal = build_agent_clarification_proposal(
                    request,
                    source_user_event_digest=proposal.source_user_event_digest,
                    agent_principal_id=access.principal_id,
                    scope_digest=current.scope_digest,
                )
                if proposal != expected_proposal:
                    raise ConflictClarificationError("invalid_conflict_resolution")
                if verified_confirmation is not None:
                    self._validate_confirmation(
                        verified_confirmation,
                        access=access,
                        request=request,
                        request_digest=request_digest,
                        proposal=proposal,
                    )
                    if verified_confirmation.nonce in state.consumed_nonces:
                        raise ConflictClarificationError("invalid_user_confirmation_receipt")
                transition = self._transition(
                    current,
                    reason=ConflictTransitionReason.CLARIFICATION_SUBMITTED,
                    proposal_digest=proposal.proposal_digest,
                    coordinate=state.transition_count + 1,
                )
                processing_operation_id = _digest(
                    _PROCESSING_OPERATION_DOMAIN,
                    {
                        "repository_id": self._repository_id,
                        "conflict_revision": transition.resulting_conflict_revision,
                        "proposal_digest": proposal.proposal_digest,
                        "policy_fingerprint": self._policy_fingerprint,
                    },
                )
                work = self._work(
                    conflict_id=request.conflict_id,
                    conflict_revision=transition.resulting_conflict_revision,
                    proposal_digest=proposal.proposal_digest,
                    attempt_count=0,
                    owner_token=None,
                    ownership_epoch=0,
                    lease_expires_at=None,
                    last_failure_class=None,
                    processing_operation_id=processing_operation_id,
                    downstream_receipt_digest=None,
                    work_revision=1,
                    predecessor_work_digest=None,
                )
                proof_digest = None
                if verified_confirmation is not None:
                    proof_digest = _digest(
                        b"memorii.verified-user-confirmation.v1\0",
                        verified_confirmation.model_dump(mode="json"),
                    )
                receipt_payload = {
                    "operation_id": request.operation_id,
                    "conflict_id": request.conflict_id,
                    "conflict_revision": request.expected_conflict_revision,
                    "request_digest": request_digest,
                    "proposal_digest": proposal.proposal_digest,
                    "verified_confirmation_digest": proof_digest,
                }
                operation_receipt = ConflictClarificationOperationReceipt(
                    **receipt_payload,
                    receipt_digest=_digest(_CLARIFICATION_OPERATION_RECEIPT_DOMAIN, receipt_payload),
                )
                generation = self._generation(
                    operation_receipt=operation_receipt,
                    proposal=proposal,
                    verified_confirmation=verified_confirmation,
                    work=work,
                    transition=transition,
                )
                self._append_locked(handle, generation)
                return ConflictClarificationSubmissionResult(
                    outcome=ClarificationSubmissionOutcome.SUBMITTED,
                    operation_receipt=operation_receipt,
                )
            except ConflictClarificationError:
                raise
            except (TypeError, ValueError) as exc:
                raise ConflictClarificationError("conflict_attention_corrupt") from exc

    def claim_next_clarification(
        self,
        *,
        lease_duration: timedelta,
    ) -> ConflictClarificationClaim | None:
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        now = self._now()
        with self._path.open("r+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            records = self._decode_ledger_lines(tuple(handle))
            state = self._replay(records)
            eligible = sorted(
                (
                    work
                    for work in state.works.values()
                    if work.attempt_count < work.max_attempts
                    and state.current[work.conflict_id].status == ConflictStatus.CLARIFICATION_SUBMITTED
                    and state.current[work.conflict_id].conflict_revision == work.conflict_revision
                    and (work.owner_token is None or (work.lease_expires_at is not None and work.lease_expires_at <= now))
                ),
                key=lambda work: (state.current[work.conflict_id].creation_coordinate, work.conflict_id),
            )
            if not eligible:
                return None
            previous = eligible[0]
            prior_attempts = state.attempts.get(previous.processing_operation_id, [])
            expired_results: tuple[ConflictClarificationAttemptResult, ...] = ()
            if previous.owner_token is not None:
                prior = prior_attempts[-1]
                if prior.attempt_id in state.results:
                    raise ConflictClarificationError("conflict_attention_corrupt")
                expired_results = (
                    self._attempt_result(
                        prior,
                        outcome=ClarificationAttemptOutcome.LEASE_EXPIRED,
                        attempt_count_after=previous.attempt_count,
                        downstream_receipt_digest=None,
                        completed_at=now,
                    ),
                )
            token = token_hex(32)
            epoch = previous.ownership_epoch + 1
            lease_expires_at = now + lease_duration
            work = self._successor_work(
                previous,
                owner_token=token,
                ownership_epoch=epoch,
                lease_expires_at=lease_expires_at,
            )
            attempt = self._attempt(
                previous=previous,
                work=work,
                owner_token=token,
                claimed_at=now,
                lease_expires_at=lease_expires_at,
                predecessor_attempt_digest=prior_attempts[-1].attempt_digest if prior_attempts else None,
            )
            proposal = state.proposals.get(previous.proposal_digest)
            if proposal is None:
                raise ConflictClarificationError("conflict_attention_corrupt")
            generation = self._generation(
                work=work,
                attempt=attempt,
                attempt_results=expired_results,
            )
            self._append_locked(handle, generation)
            return ConflictClarificationClaim(proposal=proposal, work=work, attempt=attempt)

    def renew_clarification_claim(
        self,
        claim: ConflictClarificationClaim,
        *,
        lease_duration: timedelta,
    ) -> ConflictClarificationClaim:
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        with self._path.open("r+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            state = self._replay(self._decode_ledger_lines(tuple(handle)))
            current = self._fenced_work(state, claim)
            now = self._now()
            if current.lease_expires_at is None or current.lease_expires_at <= now:
                raise ConflictClarificationError("stale_clarification_owner")
            work = self._successor_work(current, lease_expires_at=now + lease_duration)
            self._append_locked(handle, self._generation(work=work))
            return ConflictClarificationClaim(proposal=claim.proposal, work=work, attempt=claim.attempt)

    def complete_clarification_claim(
        self,
        claim: ConflictClarificationClaim,
        receipt: ConflictClarificationProcessingReceipt,
    ) -> None:
        with self._path.open("r+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            state = self._replay(self._decode_ledger_lines(tuple(handle)))
            current = self._fenced_work(state, claim)
            self._validate_processing_receipt(current, receipt)
            if claim.attempt.attempt_id in state.results:
                raise ConflictClarificationError("stale_clarification_owner")
            outcome = ClarificationAttemptOutcome(receipt.committed_outcome)
            result = self._attempt_result(
                claim.attempt,
                outcome=outcome,
                attempt_count_after=current.attempt_count,
                downstream_receipt_digest=receipt.receipt_digest,
                completed_at=self._now(),
            )
            work = self._successor_work(
                current,
                owner_token=None,
                lease_expires_at=None,
                downstream_receipt_digest=receipt.receipt_digest,
            )
            reason = {
                ClarificationAttemptOutcome.ACCEPTED: ConflictTransitionReason.CLARIFICATION_ACCEPTED,
                ClarificationAttemptOutcome.REJECTED: ConflictTransitionReason.CLARIFICATION_REJECTED,
                ClarificationAttemptOutcome.INSUFFICIENT: ConflictTransitionReason.CLARIFICATION_INSUFFICIENT,
            }[outcome]
            transition = self._transition(
                state.current[current.conflict_id],
                reason=reason,
                proposal_digest=current.proposal_digest,
                coordinate=state.transition_count + 1,
            )
            self._append_locked(
                handle,
                self._generation(work=work, attempt_results=(result,), transition=transition),
            )

    def fail_clarification_claim(
        self,
        claim: ConflictClarificationClaim,
        failure_class: ClarificationFailureClass,
    ) -> None:
        with self._path.open("r+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            state = self._replay(self._decode_ledger_lines(tuple(handle)))
            current = self._fenced_work(state, claim)
            if claim.attempt.attempt_id in state.results:
                raise ConflictClarificationError("stale_clarification_owner")
            retryable = failure_class == ClarificationFailureClass.RETRYABLE
            attempt_count = current.attempt_count + 1 if retryable else current.attempt_count
            result = self._attempt_result(
                claim.attempt,
                outcome=(
                    ClarificationAttemptOutcome.RETRYABLE_FAILURE
                    if retryable
                    else ClarificationAttemptOutcome.TERMINAL_FAILURE
                ),
                attempt_count_after=attempt_count,
                downstream_receipt_digest=None,
                completed_at=self._now(),
            )
            work = self._successor_work(
                current,
                attempt_count=attempt_count,
                owner_token=None,
                lease_expires_at=None,
                last_failure_class=failure_class,
            )
            transition = None
            if attempt_count == current.max_attempts or not retryable:
                transition = self._transition(
                    state.current[current.conflict_id],
                    reason=(
                        ConflictTransitionReason.PROCESSING_EXHAUSTED
                        if retryable
                        else ConflictTransitionReason.CLARIFICATION_INSUFFICIENT
                    ),
                    proposal_digest=current.proposal_digest,
                    coordinate=state.transition_count + 1,
                )
            self._append_locked(
                handle,
                self._generation(work=work, attempt_results=(result,), transition=transition),
            )

    def list_conflicts(self, access: ConflictAccessContext, request: ConflictListRequest) -> ConflictAttentionPage:
        if request.cursor is None:
            scopes = request.scope_ids or access.authorized_scope_ids
            self._authorize_new_scope(access, scopes)
            records = self._read_all()
            members = self._open_members(records, scopes=scopes)
            snapshot = self._create_snapshot(access, scopes=scopes, members=members, watermark=len(records))
            self._append(_SnapshotLedgerEntry(snapshot=snapshot))
            start = 0
        else:
            # Cursor authentication and scope checks intentionally precede every ledger read.
            claims = self._decode_cursor(request.cursor, access)
            if request.scope_ids is not None and request.scope_ids != claims.listing_scope_ids:
                raise ConflictAttentionReadError("invalid_cursor_scope")
            snapshot, records = self._read_continuation_snapshot(claims=claims, access=access)
            members = self._snapshot_members(records, snapshot)
            start = self._continuation_start(members, claims.last_sort_key)

        selected = members[start : start + request.page_size]
        next_cursor = None
        if start + len(selected) < len(members):
            next_cursor = self._encode_cursor(access, snapshot, self._sort_key(selected[-1]))
        return ConflictAttentionPage(items=tuple(selected), total_pending=len(members), next_cursor=next_cursor)

    @staticmethod
    def _authorize_new_scope(access: ConflictAccessContext, scopes: tuple[str, ...]) -> None:
        if not set(scopes) <= set(access.authorized_scope_ids):
            raise ConflictAttentionReadError("invalid_conflict_scope")

    def _create_snapshot(
        self,
        access: ConflictAccessContext,
        *,
        scopes: tuple[str, ...],
        members: list[ConflictAttention],
        watermark: int,
    ) -> ConflictListingSnapshot:
        created_at = self._now()
        provisional = ConflictListingSnapshot(
            snapshot_id=token_hex(16),
            tenant_id=access.tenant_id,
            principal_id=access.principal_id,
            principal_binding_digest=access.principal_binding_digest,
            authorization_snapshot_digest=access.authorization_snapshot_digest,
            authorized_scope_ids=access.authorized_scope_ids,
            listing_scope_ids=scopes,
            scope_digest=access.scope_digest,
            conflict_ledger_watermark=watermark,
            canonical_member_ids=tuple(item.conflict_id for item in members),
            created_at=created_at,
            expires_at=created_at + _CURSOR_LIFETIME,
            snapshot_digest="0" * 64,
        )
        return ConflictListingSnapshot(
            snapshot_id=provisional.snapshot_id,
            tenant_id=provisional.tenant_id,
            principal_id=provisional.principal_id,
            principal_binding_digest=provisional.principal_binding_digest,
            authorization_snapshot_digest=provisional.authorization_snapshot_digest,
            authorized_scope_ids=provisional.authorized_scope_ids,
            listing_scope_ids=provisional.listing_scope_ids,
            scope_digest=provisional.scope_digest,
            conflict_ledger_watermark=provisional.conflict_ledger_watermark,
            canonical_member_ids=provisional.canonical_member_ids,
            created_at=provisional.created_at,
            expires_at=provisional.expires_at,
            snapshot_digest=_digest(_SNAPSHOT_DOMAIN, _snapshot_payload(provisional)),
        )

    def _validate_snapshot(
        self,
        snapshot: ConflictListingSnapshot,
        *,
        claims: ConflictListingCursorClaims,
        access: ConflictAccessContext,
    ) -> ConflictListingSnapshot:
        expected_digest = _digest(_SNAPSHOT_DOMAIN, _snapshot_payload(snapshot))
        snapshot_binding = (
            snapshot.snapshot_digest,
            snapshot.conflict_ledger_watermark,
            snapshot.tenant_id,
            snapshot.principal_id,
            snapshot.principal_binding_digest,
            snapshot.authorization_snapshot_digest,
            snapshot.authorized_scope_ids,
            snapshot.listing_scope_ids,
            snapshot.scope_digest,
        )
        claims_binding = (
            claims.snapshot_digest,
            claims.snapshot_watermark,
            claims.tenant_id,
            claims.principal_id,
            claims.principal_binding_digest,
            claims.authorization_snapshot_digest,
            claims.authorized_scope_ids,
            claims.listing_scope_ids,
            claims.scope_digest,
        )
        access_binding = (
            access.tenant_id,
            access.principal_id,
            access.principal_binding_digest,
            access.authorization_snapshot_digest,
            access.authorized_scope_ids,
            access.scope_digest,
        )
        retained_access_binding = (
            snapshot.tenant_id,
            snapshot.principal_id,
            snapshot.principal_binding_digest,
            snapshot.authorization_snapshot_digest,
            snapshot.authorized_scope_ids,
            snapshot.scope_digest,
        )
        if (
            snapshot.snapshot_digest != expected_digest
            or snapshot_binding != claims_binding
            or access_binding != retained_access_binding
            or not set(snapshot.listing_scope_ids) <= set(access.authorized_scope_ids)
            or self._now() >= snapshot.expires_at
        ):
            raise ConflictAttentionReadError("invalid_conflict_cursor")
        return snapshot

    def _read_continuation_snapshot(
        self,
        *,
        claims: ConflictListingCursorClaims,
        access: ConflictAccessContext,
    ) -> tuple[ConflictListingSnapshot, list[_LedgerEntry]]:
        """Validate retained metadata before decoding payloads from one locked image."""

        try:
            handle = self._path.open("r", encoding="utf-8")
        except OSError:
            raise ConflictAttentionReadError("invalid_conflict_cursor") from None
        with handle:
            fcntl.flock(handle, fcntl.LOCK_SH)
            lines = tuple(handle)
            try:
                matches: list[ConflictListingSnapshot] = []
                for line in lines:
                    wire = line.rstrip("\n")
                    if not wire:
                        continue
                    # Canonical snapshot records put record_type ahead of their
                    # snapshot payload. Conflict records are deliberately not
                    # decoded on this metadata-only path.
                    if '"record_type":"snapshot"' not in wire:
                        continue
                    entry = _SnapshotLedgerEntry.model_validate_json(wire)
                    if entry.snapshot.snapshot_id == claims.snapshot_id:
                        matches.append(entry.snapshot)
            except (TypeError, ValueError):
                raise ConflictAttentionReadError("invalid_conflict_cursor") from None
            if len(matches) != 1:
                raise ConflictAttentionReadError("invalid_conflict_cursor")
            snapshot = self._validate_snapshot(matches[0], claims=claims, access=access)
            try:
                records = self._decode_ledger_lines(lines)
            except (TypeError, ValueError) as exc:
                raise ConflictAttentionReadError("conflict_attention_corrupt") from exc
            return snapshot, records

    def _snapshot_members(
        self,
        records: list[_LedgerEntry],
        snapshot: ConflictListingSnapshot,
    ) -> list[ConflictAttention]:
        if snapshot.conflict_ledger_watermark > len(records):
            raise ConflictAttentionReadError("invalid_conflict_cursor")
        members = self._open_members(
            records[: snapshot.conflict_ledger_watermark],
            scopes=snapshot.listing_scope_ids,
        )
        if tuple(item.conflict_id for item in members) != snapshot.canonical_member_ids:
            raise ConflictAttentionReadError("conflict_attention_corrupt")
        return members

    def _open_members(
        self,
        records: list[_LedgerEntry],
        *,
        scopes: tuple[str, ...],
    ) -> list[ConflictAttention]:
        state = self._replay(records)
        visible = [
            attention
            for conflict_id, attention in state.current.items()
            if attention.status == ConflictStatus.OPEN
            and set(state.introductions[conflict_id].scope_ids) <= set(scopes)
        ]
        visible.sort(key=self._sort_key)
        return visible

    @classmethod
    def _continuation_start(cls, members: list[ConflictAttention], last_sort_key: tuple[int, int, str]) -> int:
        matches = [index for index, item in enumerate(members) if cls._sort_key(item) == last_sort_key]
        if len(matches) != 1:
            raise ConflictAttentionReadError("invalid_conflict_cursor")
        return matches[0] + 1

    def _encode_cursor(
        self,
        access: ConflictAccessContext,
        snapshot: ConflictListingSnapshot,
        last_sort_key: tuple[int, int, str],
    ) -> str:
        issued_at = self._now()
        if not self._key_may_sign(self._active, issued_at):
            raise ConflictAttentionReadError("conflict_cursor_key_unavailable")
        claims = ConflictListingCursorClaims(
            tenant_id=access.tenant_id,
            principal_id=access.principal_id,
            principal_binding_digest=access.principal_binding_digest,
            authorization_snapshot_digest=access.authorization_snapshot_digest,
            authorized_scope_ids=access.authorized_scope_ids,
            listing_scope_ids=snapshot.listing_scope_ids,
            scope_digest=access.scope_digest,
            snapshot_id=snapshot.snapshot_id,
            snapshot_digest=snapshot.snapshot_digest,
            snapshot_watermark=snapshot.conflict_ledger_watermark,
            last_sort_key=last_sort_key,
            key_id=self._active.key_id,
            key_epoch=self._active.key_epoch,
            issued_at=issued_at,
            expires_at=issued_at + _CURSOR_LIFETIME,
        )
        raw = encode_typed_value(claims.model_dump(mode="json"))
        mac = hmac.new(self._active.secret, _CURSOR_DOMAIN + raw, hashlib.sha256).digest()
        return f"v1.{self._b64(raw)}.{self._b64(mac)}"

    def _decode_cursor(self, cursor: str, access: ConflictAccessContext) -> ConflictListingCursorClaims:
        try:
            version, encoded, signature = cursor.split(".")
            if version != "v1" or "=" in cursor:
                raise ValueError
            raw = self._unb64(encoded)
            supplied = self._unb64(signature)
            if self._b64(raw) != encoded or self._b64(supplied) != signature or len(supplied) != 32:
                raise ValueError
            value = decode_typed_value(raw)
            if encode_typed_value(value) != raw:
                raise ValueError
            claims = ConflictListingCursorClaims.model_validate_json(
                json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            )
            key = self._keys[(claims.key_id, claims.key_epoch)]
            expected = hmac.new(key.secret, _CURSOR_DOMAIN + raw, hashlib.sha256).digest()
            now = self._now()
            if (
                not self._key_may_verify(key, claims=claims, now=now)
                or now >= claims.expires_at
                or not hmac.compare_digest(expected, supplied)
            ):
                raise ValueError
            retained_binding = (
                claims.tenant_id,
                claims.principal_id,
                claims.principal_binding_digest,
                claims.authorization_snapshot_digest,
                claims.authorized_scope_ids,
                claims.scope_digest,
            )
            current_binding = (
                access.tenant_id,
                access.principal_id,
                access.principal_binding_digest,
                access.authorization_snapshot_digest,
                access.authorized_scope_ids,
                access.scope_digest,
            )
            if retained_binding != current_binding or not set(claims.listing_scope_ids) <= set(access.authorized_scope_ids):
                raise ValueError
            return claims
        except (binascii.Error, KeyError, TypeError, ValueError):
            raise ConflictAttentionReadError("invalid_conflict_cursor") from None

    @staticmethod
    def _key_may_sign(key: ConflictCursorKey, now: datetime) -> bool:
        return not key.revoked and key.valid_from <= now and key.expires_at >= now + _CURSOR_LIFETIME

    @staticmethod
    def _key_may_verify(
        key: ConflictCursorKey,
        *,
        claims: ConflictListingCursorClaims,
        now: datetime,
    ) -> bool:
        return (
            not key.revoked
            and key.valid_from <= claims.issued_at < key.expires_at
            and claims.expires_at <= key.expires_at
            and claims.issued_at <= now
            and now < key.expires_at
        )

    def _read_all(self) -> list[_LedgerEntry]:
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                fcntl.flock(handle, fcntl.LOCK_SH)
                return self._decode_ledger_lines(tuple(handle))
        except (OSError, TypeError, ValueError) as exc:
            raise ConflictAttentionReadError("conflict_attention_corrupt") from exc

    def _replay(self, records: list[_LedgerEntry]) -> _ReplayState:
        state = _ReplayState()
        for entry in records:
            if isinstance(entry, _SnapshotLedgerEntry):
                continue
            if isinstance(entry, _ConflictLedgerEntry):
                conflict_id = entry.attention.conflict_id
                if conflict_id in state.introductions:
                    raise ValueError("duplicate conflict introduction")
                state.introductions[conflict_id] = entry
                state.current[conflict_id] = entry.attention
                continue

            work = entry.work
            previous_work = state.works.get(work.processing_operation_id)
            if previous_work is None:
                if work.work_revision != 1 or work.predecessor_work_digest is not None:
                    raise ValueError("missing initial work")
            elif (
                work.work_revision != previous_work.work_revision + 1
                or work.predecessor_work_digest != previous_work.work_digest
                or (work.conflict_id, work.conflict_revision, work.proposal_digest, work.policy_fingerprint)
                != (
                    previous_work.conflict_id,
                    previous_work.conflict_revision,
                    previous_work.proposal_digest,
                    previous_work.policy_fingerprint,
                )
            ):
                raise ValueError("noncontiguous work chain")

            if entry.operation_receipt is not None:
                receipt = entry.operation_receipt
                proposal = entry.proposal
                transition = entry.transition
                if proposal is None or transition is None:
                    raise ValueError("incomplete submission generation")
                current = state.current.get(proposal.conflict_id)
                if (
                    current is None
                    or current.status != ConflictStatus.OPEN
                    or proposal.conflict_revision != current.conflict_revision
                    or receipt.operation_id != proposal.operation_id
                    or receipt.conflict_id != proposal.conflict_id
                    or receipt.conflict_revision != proposal.conflict_revision
                    or receipt.request_digest != proposal.request_digest
                    or receipt.proposal_digest != proposal.proposal_digest
                    or work.conflict_id != proposal.conflict_id
                    or work.proposal_digest != proposal.proposal_digest
                ):
                    raise ValueError("submission generation binding mismatch")
                prior_receipt = state.operations.get(receipt.operation_id)
                if prior_receipt is not None:
                    raise ValueError("duplicate clarification operation")
                if proposal.proposal_digest in state.proposals:
                    raise ValueError("duplicate proposal digest")
                reconstructed_request = ConflictResolutionRequest(
                    conflict_id=proposal.conflict_id,
                    expected_conflict_revision=proposal.conflict_revision,
                    operation_id=proposal.operation_id,
                    action=proposal.action,
                    selected_candidate_ids=proposal.selected_candidate_ids,
                    validity_intervals=proposal.validity_intervals,
                    source_user_event_id=proposal.source_user_event_id,
                )
                expected_proposal = build_agent_clarification_proposal(
                    reconstructed_request,
                    source_user_event_digest=proposal.source_user_event_digest,
                    agent_principal_id=proposal.agent_principal_id,
                    scope_digest=proposal.scope_digest,
                )
                if proposal != expected_proposal:
                    raise ValueError("proposal digest mismatch")
                if entry.verified_confirmation is not None:
                    proof = entry.verified_confirmation
                    proof_digest = _digest(
                        b"memorii.verified-user-confirmation.v1\0",
                        proof.model_dump(mode="json"),
                    )
                    if receipt.verified_confirmation_digest != proof_digest or proof.nonce in state.consumed_nonces:
                        raise ValueError("confirmation proof replay or mismatch")
                    state.consumed_nonces.add(proof.nonce)
                elif receipt.verified_confirmation_digest is not None:
                    raise ValueError("missing retained confirmation proof")
                state.operations[receipt.operation_id] = receipt
                state.proposals[proposal.proposal_digest] = proposal

            for result in entry.attempt_results:
                attempts = [
                    attempt
                    for values in state.attempts.values()
                    for attempt in values
                    if attempt.attempt_id == result.attempt_id
                ]
                if len(attempts) != 1 or result.attempt_id in state.results:
                    raise ValueError("attempt result has no unique unfinished attempt")
                attempt = attempts[0]
                if (
                    result.attempt_digest != attempt.attempt_digest
                    or result.processing_operation_id != attempt.processing_operation_id
                    or result.ownership_epoch != attempt.ownership_epoch
                    or result.owner_token_digest != attempt.owner_token_digest
                ):
                    raise ValueError("attempt result binding mismatch")
                state.results[result.attempt_id] = result

            if entry.attempt is not None:
                attempt = entry.attempt
                prior_attempts = state.attempts.setdefault(attempt.processing_operation_id, [])
                if previous_work is None:
                    raise ValueError("attempt without predecessor work")
                expected_attempt_id = _digest(
                    _ATTEMPT_ID_DOMAIN,
                    {
                        "work_digest": previous_work.work_digest,
                        "processing_operation_id": work.processing_operation_id,
                        "ownership_epoch": work.ownership_epoch,
                    },
                )
                if (
                    attempt.attempt_id != expected_attempt_id
                    or attempt.processing_operation_id != work.processing_operation_id
                    or attempt.conflict_id != work.conflict_id
                    or attempt.conflict_revision != work.conflict_revision
                    or attempt.proposal_digest != work.proposal_digest
                    or attempt.ownership_epoch != work.ownership_epoch
                    or attempt.predecessor_attempt_digest
                    != (prior_attempts[-1].attempt_digest if prior_attempts else None)
                ):
                    raise ValueError("attempt chain mismatch")
                prior_attempts.append(attempt)

            if entry.transition is not None:
                transition = entry.transition
                current = state.current.get(transition.conflict_id)
                if current is None:
                    raise ValueError("transition without introduction")
                expected = self._transition(
                    current,
                    reason=transition.reason,
                    proposal_digest=transition.proposal_digest,
                    coordinate=state.transition_count + 1,
                    transitioned_at=transition.transitioned_at,
                )
                if transition != expected:
                    raise ValueError("noncontiguous or mismatched transition")
                state.current[transition.conflict_id] = current.model_copy(
                    update={
                        "conflict_revision": transition.resulting_conflict_revision,
                        "status": transition.to_status,
                    }
                )
                state.transition_count += 1
            if entry.operation_receipt is not None and (
                entry.transition is None or work.conflict_revision != entry.transition.resulting_conflict_revision
            ):
                raise ValueError("initial work must bind submitted revision")
            expected_processing_operation_id = _digest(
                _PROCESSING_OPERATION_DOMAIN,
                {
                    "repository_id": self._repository_id,
                    "conflict_revision": work.conflict_revision,
                    "proposal_digest": work.proposal_digest,
                    "policy_fingerprint": work.policy_fingerprint,
                },
            )
            if work.processing_operation_id != expected_processing_operation_id:
                raise ValueError("processing operation identity mismatch")
            state.works[work.processing_operation_id] = work
        return state

    @staticmethod
    def _authorized_current(
        state: _ReplayState,
        access: ConflictAccessContext,
        conflict_id: str,
    ) -> tuple[_ConflictLedgerEntry, ConflictAttention]:
        introduction = state.introductions.get(conflict_id)
        current = state.current.get(conflict_id)
        if introduction is None or current is None or not set(introduction.scope_ids) <= set(access.authorized_scope_ids):
            raise ConflictClarificationError("conflict_attention_authorization_required")
        return introduction, current

    def _validate_confirmation(
        self,
        confirmation: VerifiedUserConfirmation,
        *,
        access: ConflictAccessContext,
        request: ConflictResolutionRequest,
        request_digest: str,
        proposal: AgentClarificationProposal,
    ) -> None:
        now = self._now()
        if (
            confirmation.principal_id != access.principal_id
            or confirmation.scope_digest != proposal.scope_digest
            or confirmation.conflict_id != request.conflict_id
            or confirmation.conflict_revision != request.expected_conflict_revision
            or confirmation.action != request.action
            or confirmation.request_digest != request_digest
            or confirmation.source_user_event_id != proposal.source_user_event_id
            or confirmation.source_user_event_digest != proposal.source_user_event_digest
            or not confirmation.issued_at <= now < confirmation.expires_at
        ):
            raise ConflictClarificationError("invalid_user_confirmation_receipt")

    def _transition(
        self,
        current: ConflictAttention,
        *,
        reason: ConflictTransitionReason,
        proposal_digest: str,
        coordinate: int,
        transitioned_at: datetime | None = None,
    ) -> ConflictStateTransition:
        to_status = {
            ConflictTransitionReason.CLARIFICATION_SUBMITTED: ConflictStatus.CLARIFICATION_SUBMITTED,
            ConflictTransitionReason.CLARIFICATION_ACCEPTED: ConflictStatus.RESOLVED,
            ConflictTransitionReason.CLARIFICATION_REJECTED: ConflictStatus.OPEN,
            ConflictTransitionReason.CLARIFICATION_INSUFFICIENT: ConflictStatus.OPEN,
            ConflictTransitionReason.PROCESSING_EXHAUSTED: ConflictStatus.OPEN,
        }[reason]
        resulting_revision = _digest(
            _CONFLICT_REVISION_DOMAIN,
            {
                "conflict_id": current.conflict_id,
                "predecessor_conflict_revision": current.conflict_revision,
                "from_status": current.status,
                "to_status": to_status,
                "reason": reason,
                "proposal_digest": proposal_digest,
                "transition_coordinate": coordinate,
            },
        )
        payload = {
            "conflict_id": current.conflict_id,
            "predecessor_conflict_revision": current.conflict_revision,
            "resulting_conflict_revision": resulting_revision,
            "from_status": current.status,
            "to_status": to_status,
            "reason": reason,
            "proposal_digest": proposal_digest,
            "transition_coordinate": coordinate,
            "transitioned_at": transitioned_at or self._now(),
        }
        provisional = ConflictStateTransition.model_construct(**payload, transition_digest="0" * 64)
        return ConflictStateTransition(
            **payload,
            transition_digest=_digest(
                _CONFLICT_TRANSITION_DOMAIN,
                provisional.model_dump(mode="json", exclude={"transition_digest"}),
            ),
        )

    def _work(self, **values: object) -> ConflictClarificationWork:
        payload = {"max_attempts": 3, "policy_fingerprint": self._policy_fingerprint, **values}
        provisional = ConflictClarificationWork.model_construct(**payload, work_digest="0" * 64)
        return ConflictClarificationWork(
            **payload,
            work_digest=_digest(
                _WORK_DOMAIN,
                provisional.model_dump(mode="json", exclude={"work_digest"}),
            ),
        )

    def _successor_work(self, previous: ConflictClarificationWork, **changes: object) -> ConflictClarificationWork:
        values = previous.model_dump(mode="python", exclude={"work_digest"})
        values.update(changes)
        values["work_revision"] = previous.work_revision + 1
        values["predecessor_work_digest"] = previous.work_digest
        return self._work(**values)

    def _attempt(
        self,
        *,
        previous: ConflictClarificationWork,
        work: ConflictClarificationWork,
        owner_token: str,
        claimed_at: datetime,
        lease_expires_at: datetime,
        predecessor_attempt_digest: str | None,
    ) -> ConflictClarificationAttempt:
        attempt_id = _digest(
            _ATTEMPT_ID_DOMAIN,
            {
                "work_digest": previous.work_digest,
                "processing_operation_id": work.processing_operation_id,
                "ownership_epoch": work.ownership_epoch,
            },
        )
        payload = {
            "attempt_id": attempt_id,
            "processing_operation_id": work.processing_operation_id,
            "conflict_id": work.conflict_id,
            "conflict_revision": work.conflict_revision,
            "proposal_digest": work.proposal_digest,
            "attempt_ordinal": work.attempt_count + 1,
            "attempt_count_before": work.attempt_count,
            "ownership_epoch": work.ownership_epoch,
            "owner_token_digest": hashlib.sha256(owner_token.encode("utf-8")).hexdigest(),
            "claimed_at": claimed_at,
            "lease_expires_at": lease_expires_at,
            "predecessor_attempt_digest": predecessor_attempt_digest,
        }
        provisional = ConflictClarificationAttempt.model_construct(**payload, attempt_digest="0" * 64)
        return ConflictClarificationAttempt(
            **payload,
            attempt_digest=_digest(
                _ATTEMPT_DOMAIN,
                provisional.model_dump(mode="json", exclude={"attempt_digest"}),
            ),
        )

    @staticmethod
    def _attempt_result(
        attempt: ConflictClarificationAttempt,
        *,
        outcome: ClarificationAttemptOutcome,
        attempt_count_after: int,
        downstream_receipt_digest: str | None,
        completed_at: datetime,
    ) -> ConflictClarificationAttemptResult:
        payload = {
            "attempt_id": attempt.attempt_id,
            "attempt_digest": attempt.attempt_digest,
            "processing_operation_id": attempt.processing_operation_id,
            "ownership_epoch": attempt.ownership_epoch,
            "owner_token_digest": attempt.owner_token_digest,
            "outcome": outcome,
            "attempt_count_after": attempt_count_after,
            "downstream_receipt_digest": downstream_receipt_digest,
            "completed_at": completed_at,
        }
        provisional = ConflictClarificationAttemptResult.model_construct(**payload, result_digest="0" * 64)
        return ConflictClarificationAttemptResult(
            **payload,
            result_digest=_digest(
                _ATTEMPT_RESULT_DOMAIN,
                provisional.model_dump(mode="json", exclude={"result_digest"}),
            ),
        )

    @staticmethod
    def _generation(
        *,
        work: ConflictClarificationWork,
        operation_receipt: ConflictClarificationOperationReceipt | None = None,
        proposal: AgentClarificationProposal | None = None,
        verified_confirmation: VerifiedUserConfirmation | None = None,
        attempt: ConflictClarificationAttempt | None = None,
        attempt_results: tuple[ConflictClarificationAttemptResult, ...] = (),
        transition: ConflictStateTransition | None = None,
    ) -> _ClarificationGenerationEntry:
        payload = {
            "operation_receipt": operation_receipt,
            "proposal": proposal,
            "verified_confirmation": verified_confirmation,
            "work": work,
            "attempt": attempt,
            "attempt_results": attempt_results,
            "transition": transition,
        }
        provisional = _ClarificationGenerationEntry.model_construct(**payload, generation_digest="0" * 64)
        return _ClarificationGenerationEntry(
            **payload,
            generation_digest=_digest(
                _CLARIFICATION_GENERATION_DOMAIN,
                provisional.model_dump(mode="json", exclude={"generation_digest"}),
            ),
        )

    def _fenced_work(
        self,
        state: _ReplayState,
        claim: ConflictClarificationClaim,
    ) -> ConflictClarificationWork:
        current = state.works.get(claim.work.processing_operation_id)
        if (
            current is None
            or current.work_digest != claim.work.work_digest
            or current.owner_token != claim.work.owner_token
            or current.ownership_epoch != claim.work.ownership_epoch
            or current.owner_token is None
            or current.lease_expires_at is None
            or current.lease_expires_at <= self._now()
        ):
            raise ConflictClarificationError("stale_clarification_owner")
        return current

    @staticmethod
    def _validate_processing_receipt(
        work: ConflictClarificationWork,
        receipt: ConflictClarificationProcessingReceipt,
    ) -> None:
        if (
            receipt.processing_operation_id != work.processing_operation_id
            or receipt.conflict_id != work.conflict_id
            or receipt.conflict_revision != work.conflict_revision
            or receipt.proposal_digest != work.proposal_digest
            or receipt.policy_fingerprint != work.policy_fingerprint
        ):
            raise ConflictClarificationError("conflict_attention_corrupt")

    @staticmethod
    def _decode_ledger_lines(lines: tuple[str, ...]) -> list[_LedgerEntry]:
        entries: list[_LedgerEntry] = []
        for line in lines:
            wire = line.rstrip("\n")
            if not wire:
                raise ValueError("blank ledger line")
            decoded = json.loads(wire)
            canonical = json.dumps(decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if wire != canonical or not isinstance(decoded, dict):
                raise ValueError("noncanonical ledger line")
            record_type = decoded.get("record_type")
            if record_type == "conflict":
                entries.append(_ConflictLedgerEntry.model_validate_json(wire))
            elif record_type == "snapshot":
                entries.append(_SnapshotLedgerEntry.model_validate_json(wire))
            elif record_type == "clarification_generation":
                entries.append(_ClarificationGenerationEntry.model_validate_json(wire))
            else:
                raise ValueError("unknown ledger record")
        return entries

    def _append(self, value: BaseModel) -> None:
        wire = json.dumps(value.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self._path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            handle.write(wire + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _append_locked(handle: object, value: BaseModel) -> None:
        wire = json.dumps(value.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        handle.seek(0, os.SEEK_END)  # type: ignore[attr-defined]
        handle.write(wire + "\n")  # type: ignore[attr-defined]
        handle.flush()  # type: ignore[attr-defined]
        os.fsync(handle.fileno())  # type: ignore[attr-defined]

    @staticmethod
    def _sort_key(item: ConflictAttention) -> tuple[int, int, str]:
        return (0 if item.audience == ConflictAudience.USER else 1, item.creation_coordinate, item.conflict_id)

    @staticmethod
    def _b64(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _unb64(value: str) -> bytes:
        return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


class ConflictClarificationProcessingRepository(Protocol):
    """Canonical lifecycle authority needed by the processing scheduler only."""

    def claim_next_clarification(
        self, *, lease_duration: timedelta
    ) -> ConflictClarificationClaim | None: ...

    def renew_clarification_claim(
        self, claim: ConflictClarificationClaim, *, lease_duration: timedelta
    ) -> ConflictClarificationClaim: ...

    def fail_clarification_claim(
        self, claim: ConflictClarificationClaim, failure_class: ClarificationFailureClass
    ) -> object: ...

    def complete_clarification_claim(
        self, claim: ConflictClarificationClaim,
        receipt: ConflictClarificationProcessingReceipt,
    ) -> None: ...


class ConflictClarificationProcessor:
    """Lease-fenced adapter around the ordinary idempotent semantic pipeline."""

    def __init__(
        self,
        repository: ConflictClarificationProcessingRepository,
        pipeline: ConflictClarificationSemanticPipeline,
        *,
        lease_duration: timedelta = timedelta(minutes=5),
    ) -> None:
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        self._repository = repository
        self._pipeline = pipeline
        self._lease_duration = lease_duration

    def process_next(self) -> bool:
        claim = self._repository.claim_next_clarification(lease_duration=self._lease_duration)
        if claim is None:
            return False
        durable = self._pipeline.resolve_processing_receipt(claim.work.processing_operation_id)
        if durable is not None:
            self._repository.complete_clarification_claim(claim, durable)
            return True
        stop = Event()
        claim_lock = Lock()
        current_claim = [claim]
        renewal_failures: list[Exception] = []

        def renew() -> None:
            interval = max(self._lease_duration.total_seconds() / 3, 0.01)
            while not stop.wait(interval):
                try:
                    with claim_lock:
                        current_claim[0] = self._repository.renew_clarification_claim(
                            current_claim[0], lease_duration=self._lease_duration
                        )
                except (OSError, ValueError) as exc:
                    renewal_failures.append(exc)
                    return

        heartbeat = Thread(
            target=renew,
            name="memorii-conflict-clarification-lease-heartbeat",
            daemon=True,
        )
        heartbeat.start()
        try:
            returned = self._pipeline.process_clarification(
                claim.proposal,
                processing_operation_id=claim.work.processing_operation_id,
                policy_fingerprint=claim.work.policy_fingerprint,
                # The heartbeat replaces this image after every renewal.  The
                # adapter must obtain it immediately before its same-plane CAS.
                current_claim=lambda: self._current_claim(claim_lock, current_claim),
            )
        except Exception as exc:
            stop.set()
            heartbeat.join()
            with claim_lock:
                claim = current_claim[0]
            # A provider may raise after its semantic transaction commits. Resolve
            # the durable receipt again before deciding this was a failed attempt.
            durable = self._pipeline.resolve_processing_receipt(claim.work.processing_operation_id)
            if durable is not None:
                self._repository.complete_clarification_claim(claim, durable)
                return True
            if isinstance(exc, ClarificationPipelineError):
                self._repository.fail_clarification_claim(claim, exc.failure_class)
                return True
            raise
        finally:
            stop.set()
            heartbeat.join()
        with claim_lock:
            claim = current_claim[0]
        if isinstance(returned, ConflictClarificationAttemptResult):
            if (
                returned.outcome is not ClarificationAttemptOutcome.SUPERSEDED
                or returned.processing_operation_id
                != claim.work.processing_operation_id
                or returned.attempt_digest != claim.attempt.attempt_digest
                or returned.downstream_receipt_digest is not None
                or returned.superseded_by_conflict_revision is None
            ):
                raise ConflictClarificationError("conflict_attention_corrupt")
            # A natural projection won the same-plane race.  Its retained
            # terminal result is the complete no-op acknowledgement; no
            # receipt, failure result, or second pipeline invocation follows.
            return True
        if renewal_failures:
            durable = self._pipeline.resolve_processing_receipt(
                claim.work.processing_operation_id
            )
            if durable is None:
                raise renewal_failures[0]
        durable = self._pipeline.resolve_processing_receipt(claim.work.processing_operation_id)
        if durable is None or durable != returned:
            raise ConflictClarificationError("conflict_attention_corrupt")
        self._repository.complete_clarification_claim(claim, durable)
        return True

    @staticmethod
    def _current_claim(
        claim_lock: Lock, current_claim: list[ConflictClarificationClaim]
    ) -> ConflictClarificationClaim:
        with claim_lock:
            return current_claim[0]


class AtomicStoreConflictClarificationProcessingRepository:
    """Thin scheduler port over the memory-plane lifecycle authority.

    The file ledger is deliberately absent here: its listing projection cannot
    claim, renew, fail, or complete canonical clarification work.
    """

    def __init__(self, atomic_store: SemanticIngestionAtomicStore) -> None:
        self._store = atomic_store

    def claim_next_clarification(
        self, *, lease_duration: timedelta
    ) -> ConflictClarificationClaim | None:
        return self._store.claim_next_conflict_clarification(
            lease_duration=lease_duration
        )

    def renew_clarification_claim(
        self, claim: ConflictClarificationClaim, *, lease_duration: timedelta
    ) -> ConflictClarificationClaim:
        return self._store.renew_conflict_clarification_claim(
            claim, lease_duration=lease_duration
        )

    def fail_clarification_claim(
        self, claim: ConflictClarificationClaim, failure_class: ClarificationFailureClass
    ) -> object:
        return self._store.fail_conflict_clarification_claim(
            claim, retryable=failure_class == ClarificationFailureClass.RETRYABLE
        )

    def complete_clarification_claim(
        self,
        claim: ConflictClarificationClaim,
        receipt: ConflictClarificationProcessingReceipt,
    ) -> None:
        # Completion was already atomically written with the semantic receipt.
        # Re-resolve it to reject a substituted or partial lost-ack result,
        # without creating a second lifecycle generation.
        retained = self._store.resolve_conflict_clarification_receipt(
            claim.work.processing_operation_id
        )
        if retained != receipt:
            raise ConflictClarificationError("conflict_attention_corrupt")


def _conflict_entry_payload(entry: _ConflictLedgerEntry) -> dict[str, object]:
    return {
        "schema_version": entry.schema_version,
        "record_type": entry.record_type,
        "scope_ids": entry.scope_ids,
        "attention": entry.attention.model_dump(mode="json"),
    }


def _snapshot_payload(snapshot: ConflictListingSnapshot) -> dict[str, object]:
    return snapshot.model_dump(mode="json", exclude={"snapshot_digest"})


def _digest(domain: bytes, value: object) -> str:
    return hashlib.sha256(domain + encode_typed_value(value)).hexdigest()
