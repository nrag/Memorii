"""Provider-owned publication of accepted managed candidate deliveries."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal, TypeVar

from pydantic import ValidationError

from memorii.core.harness_state.write_authority import HostCommandAuthorityError, ManagedHostCommandAuthority
from memorii.core.harness_state.writeback_decision import WritebackDecisionError, load_recorded_decision
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import (
    RecordAbsentPrecondition,
    _RuntimeCandidateWriteAuthorization,
    record_digest,
)
from memorii.core.persistence.contracts import InstallationControlState, RuntimePublicationState
from memorii.core.persistence.managed_delivery import (
    DeliveredDelivery,
    DeliveredEffect,
    DeliveryClaim,
    DeliveryContext,
    DeliveryTransitionError,
    ManagedDelivery,
    PendingDelivery,
    ProtectedSkillCandidateScope,
    RuntimeTargetReceipt,
    claim_delivery,
    complete_delivery,
    record_delivery_failure,
    recover_delivery_claim,
    reject_pending_delivery,
)
from memorii.core.persistence.runtime_api import (
    operation_origin_namespace,
    operation_origin_proof_digest,
    require_no_legacy_delivery,
)
from memorii.core.persistence.runtime_contracts import OperationOriginCoordinate, RuntimeSourceAdmissionReceipt
from memorii.core.persistence.runtime_repository import (
    RuntimeStateError,
    RuntimeStateRepository,
    publish_runtime_change,
)
from memorii.core.persistence.writeback_decisions import CandidateDeliveryEntry, RecordedWritebackDecision
from memorii.core.provider.runtime_candidate import (
    AcceptedCandidateOffer,
    CandidateStageError,
    ProtectedSkillCandidate,
    prepare_candidate_stage,
)
from memorii.core.storage_administration.revoked_identity_view import RefreshingRevokedIdentityView
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.core.storage_administration.writer_enrollment import WriterEnrollmentError, WriterEnrollmentRegistry
from memorii.domain.enums import MemoryRecordVisibility

_T = TypeVar("_T")
_Candidate = CanonicalMemoryRecord | ProtectedSkillCandidate
_Rejection = Literal["denied", "forgotten", "invalid_payload"]


class _CandidateRejected(RuntimeError):
    reason: _Rejection

    def __init__(self, reason: _Rejection) -> None:
        super().__init__(reason)
        self.reason = reason


class _CompletedCandidate(RuntimeError):
    """Abort a redundant publication after verifying its existing effect."""

    def __init__(self, receipt: RuntimeTargetReceipt) -> None:
        super().__init__("candidate already delivered")
        self.receipt = receipt


class ManagedCandidateDeliveryWorker:
    """Fence one local candidate effect behind a signed host acceptance."""

    def __init__(
        self,
        administration: StorageAdministrationService,
        *,
        worker_id: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._administration = administration
        self._worker_id = worker_id
        self._clock = clock or (lambda: datetime.now(UTC))
        control = administration.installation_root / "control"
        self._grants = ManagedHostCommandAuthority(administration)
        self._revoked = RefreshingRevokedIdentityView(control)
        self._writers = WriterEnrollmentRegistry(control / "writers")

    def claim(self, delivery_id: str) -> DeliveryClaim | None:
        def claim_entry(
            connection: sqlite3.Connection,
            repository: RuntimeStateRepository,
            entry: CandidateDeliveryEntry,
            state: InstallationControlState,
            context: DeliveryContext,
            finalized: RuntimePublicationState,
        ) -> DeliveryClaim | None:
            delivery = entry.delivery
            now = self._clock()
            if isinstance(delivery.progress, DeliveryClaim):
                updated = recover_delivery_claim(delivery, context=context, now=now)
            elif isinstance(delivery.progress, PendingDelivery):
                if (
                    isinstance(delivery.request.authority.scope, ProtectedSkillCandidateScope)
                    and not repository.partition.supports_runtime_history(connection)
                ):
                    raise DeliveryTransitionError("unavailable: protected skill target is not available")
                try:
                    self._candidate(connection, repository, entry, state, finalized, now)
                except _CandidateRejected as exc:
                    updated = reject_pending_delivery(delivery, context=context, reason=exc.reason)
                else:
                    updated = claim_delivery(
                        delivery, context=context, current_authority=delivery.request.authority,
                        worker_id=self._worker_id, now=now,
                    )
            else:
                raise DeliveryTransitionError("conflict: writeback delivery is terminal")
            self._update(connection, repository, entry, updated)
            return updated.progress if isinstance(updated.progress, DeliveryClaim) else None

        return self._publish(delivery_id, claim_entry)

    def publish(self, claim: DeliveryClaim) -> RuntimeTargetReceipt | None:
        if claim.worker_id != self._worker_id:
            raise DeliveryTransitionError("denied: claim belongs to another worker")

        def publish_effect(
            connection: sqlite3.Connection,
            repository: RuntimeStateRepository,
            entry: CandidateDeliveryEntry,
            state: InstallationControlState,
            context: DeliveryContext,
            finalized: RuntimePublicationState,
        ) -> RuntimeTargetReceipt | None:
            delivery = entry.delivery
            now = self._clock()
            try:
                candidate = self._candidate(connection, repository, entry, state, finalized, now)
            except _CandidateRejected as exc:
                if not isinstance(delivery.progress, DeliveryClaim):
                    raise DeliveryTransitionError("denied: writeback authority is no longer valid") from exc
                rejected = record_delivery_failure(
                    delivery, claim=claim, context=context, now=now, outcome=exc.reason,
                )
                self._update(connection, repository, entry, rejected)
                return None
            if isinstance(delivery.progress, DeliveredDelivery):
                if delivery.progress.completed_claim != claim:
                    raise DeliveryTransitionError("conflict: receipt requires the completed claim")
                receipt = delivery.progress.receipt
                self._verify_effect(connection, repository, candidate, receipt)
                raise _CompletedCandidate(receipt)

            if self._effect_digest(connection, repository, candidate) is not None or self._read_receipt(
                connection, repository, claim.delivery_id,
            ) is not None:
                unresolved = record_delivery_failure(
                    delivery, claim=claim, context=context, now=now, outcome="ambiguous_effect",
                )
                self._update(connection, repository, entry, unresolved)
                return None
            if isinstance(candidate, CanonicalMemoryRecord):
                revision = repository.partition.read_revision_state(connection)[0] + 1
                effect = DeliveredEffect(
                    record_id=candidate.memory_id, record_digest=record_digest(candidate), revision=revision,
                )
            else:
                effect = DeliveredEffect(
                    record_id=candidate.candidate_id, record_digest=candidate.digest(),
                    revision=repository.read_runtime_revision_in(connection),
                )
            receipt = RuntimeTargetReceipt(
                delivery_id=claim.delivery_id, target_kind="writeback_candidate",
                scope=delivery.request.authority.scope, request_digest=delivery.request.request_digest(),
                effect=effect, generation_id=context.generation_id,
            )
            completed = complete_delivery(
                delivery, claim=claim, context=context, current_authority=delivery.request.authority,
                now=now, receipt=receipt, effect=effect,
            )
            self._stage(connection, repository, candidate, effect)
            repository.partition.insert_delivery_record(
                connection, catalog="runtime_target_receipts", record_id=claim.delivery_id,
                record_json=receipt.model_dump_json(),
            )
            self._update(connection, repository, entry, completed)
            return receipt

        try:
            return self._publish(claim.delivery_id, publish_effect)
        except _CompletedCandidate as exc:
            return exc.receipt

    def _publish(
        self,
        delivery_id: str,
        apply: Callable[[
            sqlite3.Connection, RuntimeStateRepository, CandidateDeliveryEntry,
            InstallationControlState, DeliveryContext, RuntimePublicationState,
        ], _T],
    ) -> _T:
        verified: list[tuple[InstallationControlState, RuntimePublicationState]] = []
        results: list[_T] = []

        def validate(state: InstallationControlState, finalized: RuntimePublicationState) -> None:
            writer = self._writers.require_enrolled(self._worker_id)
            if writer.kind != "managed_writeback_candidate":
                raise WriterEnrollmentError("unsupported_configuration: incorrect writeback worker kind")
            if state.mode != "active":
                raise DeliveryTransitionError("unavailable: writeback delivery requires active mode")
            verified.append((state, finalized))

        def apply_verified(connection: sqlite3.Connection, repository: RuntimeStateRepository) -> None:
            state, finalized = verified[0]
            row = repository.partition.read_runtime_row(
                connection, table="runtime_outbox_deliveries", match=(("delivery_id", delivery_id),),
            )
            if row is None:
                raise DeliveryTransitionError("not_found: writeback delivery not found")
            try:
                entry = CandidateDeliveryEntry.model_validate_json(row["record_json"])
            except ValidationError as exc:
                require_no_legacy_delivery(delivery_id, row["record_json"])
                raise DeliveryTransitionError("integrity_error: invalid writeback queue record") from exc
            if entry.delivery.request.delivery_id != delivery_id:
                raise DeliveryTransitionError("integrity_error: mismatched writeback delivery ID")
            context = DeliveryContext(
                installation_id=finalized.installation_id,
                partition_id=finalized.repository_id,
                generation_id=finalized.data_generation_id,
                eligibility_epoch=state.eligibility_epoch + state.pending_epoch_increments,
                control_revision=state.control_revision,
                mode=state.mode,
            )
            if entry.delivery.generation_id != context.generation_id:
                raise DeliveryTransitionError("needs_reconciliation: writeback belongs to another generation")
            results.append(apply(connection, repository, entry, state, context, finalized))

        publish_runtime_change(self._administration, apply_verified, validate_authority=validate)
        return results[0]

    def _candidate(
        self,
        connection: sqlite3.Connection,
        repository: RuntimeStateRepository,
        entry: CandidateDeliveryEntry,
        state: InstallationControlState,
        finalized: RuntimePublicationState,
        now: datetime,
    ) -> _Candidate:
        try:
            decision = load_recorded_decision(connection, repository, entry.decision_output_id)
            if decision is None:
                raise DeliveryTransitionError("integrity_error: writeback acceptance is missing")
            decision.receipt(entry.delivery)
        except (WritebackDecisionError, ValueError) as exc:
            raise DeliveryTransitionError("integrity_error: writeback acceptance disagrees with its queue record") from exc
        self._verify_decision(connection, repository, decision, finalized)
        binding = decision.authority
        if self._revoked.is_revoked_task(decision.scope.task_id):
            raise _CandidateRejected("forgotten")
        task = repository.get_task_in(connection, decision.scope.task_id)
        if task is None or task.principal != binding.principal or task.project != binding.project_id:
            raise _CandidateRejected("denied")
        try:
            self._grants.resolve_persisted_writeback_in_verified_context(
                binding=binding, operation_id=decision.request.operation_id,
                state=state, finalized=finalized, now=now,
            )
        except HostCommandAuthorityError as exc:
            if str(exc).startswith("denied:"):
                raise _CandidateRejected("denied") from exc
            raise

        try:
            result = repository.get_consolidation_result_in(connection, decision.request.result_id)
        except (RuntimeStateError, ValidationError) as exc:
            raise DeliveryTransitionError("integrity_error: invalid writeback consolidation result") from exc
        if result is None:
            raise DeliveryTransitionError("integrity_error: writeback consolidation result is missing")
        origin = OperationOriginCoordinate(
            installation_id=finalized.installation_id, repository_id=finalized.repository_id,
            generation_id=finalized.data_generation_id, principal=binding.principal,
            client_namespace=binding.client_namespace, operation_id=result.origin.operation_id,
            request_digest=result.origin.request_digest,
        )
        result_receipt = repository.get_command_receipt_in(
            connection, operation_origin_namespace(origin), origin.operation_id,
        )
        if (
            result.origin.installation_id != origin.installation_id
            or result.origin.partition_id != origin.repository_id
            or result.origin.operation_generation != origin.generation_id
            or result.origin.client_namespace != origin.client_namespace
            or result_receipt is None
            or result_receipt.status != "committed"
            or result_receipt.operation_origin != origin
            or result_receipt.consolidation_result_id != result.result_id
            or result_receipt.current_revision != result.origin_revision
            or result_receipt.result_digest != sha256(result.canonical_bytes()).hexdigest()
        ):
            raise DeliveryTransitionError("integrity_error: writeback result lacks its exact origin receipt")
        if not binding.source_refs:
            raise _CandidateRejected("invalid_payload")
        from memorii.core.provider.runtime_source_release import get_current_source_release

        sources: list[CanonicalMemoryRecord] = []
        released: list[RuntimeSourceAdmissionReceipt] = []
        for ref in binding.source_refs:
            if self._revoked.is_revoked_source(ref.source_id) or self._revoked.is_revoked_record(ref.source_id):
                raise _CandidateRejected("forgotten")
            row = repository.partition.read_current_record_row(connection, ref.source_id)
            if row is None:
                raise _CandidateRejected("denied")
            try:
                source = CanonicalMemoryRecord.model_validate_json(row["record_json"])
            except ValidationError as exc:
                raise DeliveryTransitionError("integrity_error: invalid persisted source record") from exc
            if source.visibility == MemoryRecordVisibility.INTERNAL_CONTROL:
                scoped_source = get_current_source_release(
                    connection, repository, task_id=decision.scope.task_id, principal=binding.principal,
                    source_ref=ref, now=now, revoked=self._revoked,
                )
                if scoped_source is None:
                    raise _CandidateRejected("denied")
                released.append(scoped_source)
            else:
                sources.append(source)
        try:
            return prepare_candidate_stage(
                result=result,
                acceptance=AcceptedCandidateOffer(
                    decision_id=decision.decision_id, result_id=result.result_id,
                    output_id=decision.request.output_id, payload_digest=decision.request.expected_payload_digest,
                    accepted_at=decision.decided_at, target_scope=decision.scope,
                ),
                authority=binding, current_sources=tuple(sources), revoked=self._revoked, now=now,
                released_provider_sources=tuple(released),
            )
        except CandidateStageError as exc:
            if str(exc).startswith("integrity_error:"):
                raise DeliveryTransitionError(str(exc)) from exc
            raise _CandidateRejected("denied") from exc

    def _verify_decision(
        self,
        connection: sqlite3.Connection,
        repository: RuntimeStateRepository,
        decision: RecordedWritebackDecision,
        finalized: RuntimePublicationState,
    ) -> None:
        origin = decision.origin.coordinate
        receipt = repository.get_command_receipt_in(
            connection, operation_origin_namespace(origin), origin.operation_id,
        )
        if (
            decision.request.decision != "accept"
            or origin.installation_id != finalized.installation_id
            or origin.repository_id != finalized.repository_id
            or origin.generation_id != finalized.data_generation_id
            or not self._administration.verify_operation_origin(decision.origin)
            or receipt is None
            or receipt.status != "committed"
            or receipt.operation_origin != origin
            or receipt.origin_proof_digest != operation_origin_proof_digest(decision.origin)
            or receipt.result_digest != decision.decision_id
        ):
            raise DeliveryTransitionError("integrity_error: writeback decision lacks its exact origin receipt")

    def _stage(
        self,
        connection: sqlite3.Connection,
        repository: RuntimeStateRepository,
        candidate: _Candidate,
        effect: DeliveredEffect,
    ) -> None:
        if isinstance(candidate, ProtectedSkillCandidate):
            repository.partition.insert_delivery_record(
                connection, catalog="runtime_skill_candidates", record_id=candidate.candidate_id,
                record_json=candidate.model_dump_json(),
            )
            return
        self._administration.memory_plane_store().apply_batch_in_transaction(
            connection, (candidate,), expected_revision=None,
            expected_write_revision=effect.revision - 1,
            preconditions=(RecordAbsentPrecondition(memory_id=effect.record_id),),
            authorization=_RuntimeCandidateWriteAuthorization(effect.record_id, effect.record_digest),
        )

    @staticmethod
    def _effect_digest(
        connection: sqlite3.Connection, repository: RuntimeStateRepository, candidate: _Candidate,
    ) -> str | None:
        try:
            if isinstance(candidate, ProtectedSkillCandidate):
                raw = repository.partition.read_delivery_record(
                    connection, catalog="runtime_skill_candidates", record_id=candidate.candidate_id,
                )
                return None if raw is None else ProtectedSkillCandidate.model_validate_json(raw).digest()
            row = repository.partition.read_current_record_row(connection, candidate.memory_id)
            return None if row is None else record_digest(CanonicalMemoryRecord.model_validate_json(row["record_json"]))
        except ValidationError as exc:
            raise DeliveryTransitionError("integrity_error: invalid persisted writeback effect") from exc

    @staticmethod
    def _read_receipt(
        connection: sqlite3.Connection, repository: RuntimeStateRepository, delivery_id: str,
    ) -> RuntimeTargetReceipt | None:
        raw = repository.partition.read_delivery_record(
            connection, catalog="runtime_target_receipts", record_id=delivery_id,
        )
        try:
            return None if raw is None else RuntimeTargetReceipt.model_validate_json(raw)
        except ValidationError as exc:
            raise DeliveryTransitionError("integrity_error: invalid persisted target receipt") from exc

    def _verify_effect(
        self,
        connection: sqlite3.Connection,
        repository: RuntimeStateRepository,
        candidate: _Candidate,
        receipt: RuntimeTargetReceipt,
    ) -> None:
        candidate_id = candidate.candidate_id if isinstance(candidate, ProtectedSkillCandidate) else candidate.memory_id
        candidate_digest = candidate.digest() if isinstance(candidate, ProtectedSkillCandidate) else record_digest(candidate)
        if (
            receipt.effect.record_id != candidate_id
            or receipt.effect.record_digest != candidate_digest
            or receipt.effect.record_digest != self._effect_digest(connection, repository, candidate)
            or receipt != self._read_receipt(connection, repository, receipt.delivery_id)
        ):
            raise DeliveryTransitionError("integrity_error: writeback effect does not match its terminal receipt")

    @staticmethod
    def _update(
        connection: sqlite3.Connection, repository: RuntimeStateRepository,
        entry: CandidateDeliveryEntry, updated: ManagedDelivery,
    ) -> None:
        record = CandidateDeliveryEntry(decision_output_id=entry.decision_output_id, delivery=updated)
        repository.partition.upsert_runtime_row(
            connection, table="runtime_outbox_deliveries", keys=("delivery_id",),
            values=(entry.delivery.request.delivery_id,), record_json=record.model_dump_json(),
        )
