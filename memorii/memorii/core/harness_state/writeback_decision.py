"""Authenticated host-only decision and signed enqueue on one partition."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal

from pydantic import ValidationError

from memorii.core.consolidation.runtime_outputs import EpisodicSummary, SemanticCandidate, SkillCandidate, UserCandidate
from memorii.core.harness_state.consolidation_read import ConsolidationReadError, ConsolidationReadService
from memorii.core.harness_state.credentials import SidecarCredentialStore
from memorii.core.harness_state.write_authority import HostCommandAuthorityError, ManagedHostCommandAuthority
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import record_digest
from memorii.core.persistence.contracts import InstallationControlState, RuntimePublicationState
from memorii.core.persistence.managed_delivery import (
    DeliveredDelivery,
    DeliveryAuthorityBinding,
    ManagedDelivery,
    ProtectedSkillCandidateScope,
    RuntimeTargetReceipt,
)
from memorii.core.persistence.runtime_api import operation_origin_namespace, operation_origin_proof_digest
from memorii.core.persistence.runtime_contracts import OperationOrigin, OperationOriginCoordinate, RuntimeCommandReceipt
from memorii.core.persistence.runtime_repository import (
    RuntimeStateError,
    RuntimeStateRepository,
    publish_runtime_change,
)
from memorii.core.persistence.writeback_decisions import (
    CandidateDeliveryEntry,
    CandidateScope,
    RecordedWritebackDecision,
    WritebackDecisionReceipt,
    WritebackDecisionRequest,
    candidate_scope,
)
from memorii.core.storage_administration.revoked_identity_view import RefreshingRevokedIdentityView
from memorii.core.storage_administration.service import StorageAdministrationService

WritebackErrorCode = Literal[
    "unauthenticated", "denied", "not_found", "conflict", "unavailable",
    "integrity_error", "unsupported_configuration", "needs_reconciliation",
]


class WritebackDecisionError(RuntimeError):
    code: WritebackErrorCode

    def __init__(self, code: WritebackErrorCode) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class _AuthorizedOffer:
    coordinate: OperationOriginCoordinate
    scope: CandidateScope
    binding: DeliveryAuthorityBinding


class _PreviousDecision(RuntimeError):
    def __init__(self, receipt: WritebackDecisionReceipt) -> None:
        self.receipt = receipt


def load_recorded_decision(
    connection: sqlite3.Connection, repository: RuntimeStateRepository, output_id: str,
) -> RecordedWritebackDecision | None:
    partition = repository.partition
    if partition.read_schema_version(connection) < 3:
        return None
    raw = partition.read_delivery_record(connection, catalog="writeback_decisions", record_id=output_id)
    if raw is None:
        return None
    try:
        recorded = RecordedWritebackDecision.model_validate_json(raw)
    except ValidationError as exc:
        raise WritebackDecisionError("integrity_error") from exc
    if recorded.request.output_id != output_id:
        raise WritebackDecisionError("integrity_error")
    return recorded


def read_candidate_delivery(
    connection: sqlite3.Connection, repository: RuntimeStateRepository, decision: RecordedWritebackDecision,
) -> ManagedDelivery | None:
    expected = decision.initial_delivery()
    if expected is None:
        return None
    row = repository.partition.read_runtime_row(
        connection, table="runtime_outbox_deliveries", match=(("delivery_id", expected.request.delivery_id),),
    )
    if row is None:
        raise WritebackDecisionError("integrity_error")
    try:
        entry = CandidateDeliveryEntry.model_validate_json(row["record_json"])
    except ValidationError as exc:
        raise WritebackDecisionError("integrity_error") from exc
    if (
        entry.decision_output_id != decision.request.output_id
        or entry.delivery.request != expected.request
        or entry.delivery.generation_id != expected.generation_id
    ):
        raise WritebackDecisionError("integrity_error")
    if isinstance(entry.delivery.progress, DeliveredDelivery):
        receipt = entry.delivery.progress.receipt
        partition = repository.partition
        raw_receipt = partition.read_delivery_record(
            connection, catalog="runtime_target_receipts", record_id=expected.request.delivery_id,
        )
        try:
            if raw_receipt is None or RuntimeTargetReceipt.model_validate_json(raw_receipt) != receipt:
                raise WritebackDecisionError("integrity_error")
            candidate_id = f"cand:runtime:{decision.request.output_id}"
            if receipt.effect.record_id != candidate_id:
                raise WritebackDecisionError("integrity_error")
            if isinstance(decision.scope, ProtectedSkillCandidateScope):
                from memorii.core.provider.runtime_candidate import ProtectedSkillCandidate

                skill = partition.read_delivery_record(
                    connection, catalog="runtime_skill_candidates", record_id=candidate_id,
                )
                digest = None if skill is None else ProtectedSkillCandidate.model_validate_json(skill).digest()
            else:
                candidate = partition.read_current_record_row(connection, candidate_id)
                digest = None if candidate is None else record_digest(
                    CanonicalMemoryRecord.model_validate_json(candidate["record_json"]),
                )
            if digest != receipt.effect.record_digest:
                raise WritebackDecisionError("integrity_error")
        except ValidationError as exc:
            raise WritebackDecisionError("integrity_error") from exc
    return entry.delivery


class WritebackDecisionService:
    def __init__(
        self, administration: StorageAdministrationService, credentials: SidecarCredentialStore, secret: str,
    ) -> None:
        self._administration = administration
        self._credentials = credentials
        self._secret = secret
        self._grants = ManagedHostCommandAuthority(administration)
        self._revoked = RefreshingRevokedIdentityView(administration.installation_root / "control")

    def prepare(self, request: WritebackDecisionRequest) -> OperationOrigin:
        with self._administration.verified_operation_context() as (state, finalized):
            if state.mode != "active":
                raise WritebackDecisionError("unavailable")
            repository = RuntimeStateRepository(self._administration.partition())
            with repository.partition.transaction(write=False) as connection:
                offer = self._authorize_offer(connection, repository, request, state, finalized)
                if request.expected_offer_version != 1:
                    raise WritebackDecisionError("conflict")
                self._previous(connection, repository, request, offer.coordinate)
                return self._administration.sign_operation_origin(offer.coordinate)

    def decide(self, request: WritebackDecisionRequest, *, operation_origin: OperationOrigin) -> WritebackDecisionReceipt:
        if (
            not self._administration.verify_operation_origin(operation_origin)
            or operation_origin.coordinate.request_digest != request.intent_digest()
        ):
            raise WritebackDecisionError("denied")
        previous = self._read_retry(request, operation_origin)
        if previous is not None:
            return previous

        context: list[tuple[InstallationControlState, RuntimePublicationState]] = []
        receipts: list[WritebackDecisionReceipt] = []

        def validate(state: InstallationControlState, finalized: RuntimePublicationState) -> None:
            if state.mode != "active":
                raise WritebackDecisionError("unavailable")
            self._require_generation(operation_origin, finalized)
            context.append((state, finalized))

        def apply(connection: sqlite3.Connection, repository: RuntimeStateRepository) -> None:
            state, finalized = context[0]
            offer = self._authorize_offer(connection, repository, request, state, finalized)
            if offer.coordinate != operation_origin.coordinate:
                raise WritebackDecisionError("denied")
            retry = self._previous(connection, repository, request, offer.coordinate, proof=operation_origin)
            if retry is not None:
                raise _PreviousDecision(retry)
            if request.expected_offer_version != 1:
                raise WritebackDecisionError("conflict")
            decision = RecordedWritebackDecision(
                request=request, origin=operation_origin, authority=offer.binding,
                decided_at=datetime.now(UTC), scope=offer.scope,
            )
            partition = repository.partition
            partition.insert_delivery_record(
                connection, catalog="writeback_decisions", record_id=request.output_id,
                record_json=decision.model_dump_json(),
            )
            delivery = decision.initial_delivery()
            if delivery is not None:
                self._enqueue(connection, repository, decision, delivery)
            revision = repository.read_runtime_revision_in(connection)
            repository.apply_command_receipt(
                connection,
                RuntimeCommandReceipt(
                    operation_id=request.operation_id, client_namespace=offer.coordinate.client_namespace,
                    request_digest=offer.coordinate.request_digest, status="committed",
                    base_revision=revision - 1, current_revision=revision, result_digest=decision.decision_id,
                    operation_origin=offer.coordinate, origin_proof_digest=operation_origin_proof_digest(operation_origin),
                ),
                lookup_namespace=operation_origin_namespace(offer.coordinate),
            )
            receipts.append(decision.receipt(delivery))

        try:
            publish_runtime_change(self._administration, apply, validate_authority=validate)
        except _PreviousDecision as exc:
            return exc.receipt
        return receipts[0]

    def _read_retry(
        self, request: WritebackDecisionRequest, proof: OperationOrigin,
    ) -> WritebackDecisionReceipt | None:
        with self._administration.verified_operation_context() as (state, finalized):
            if state.mode == "bypass":
                raise WritebackDecisionError("unavailable")
            self._require_generation(proof, finalized)
            repository = RuntimeStateRepository(self._administration.partition())
            with repository.partition.transaction(write=False) as connection:
                offer = self._authorize_offer(connection, repository, request, state, finalized)
                if offer.coordinate != proof.coordinate:
                    raise WritebackDecisionError("denied")
                return self._previous(connection, repository, request, offer.coordinate, proof=proof)

    @staticmethod
    def _require_generation(proof: OperationOrigin, finalized: RuntimePublicationState) -> None:
        coordinate = proof.coordinate
        if (
            coordinate.installation_id != finalized.installation_id
            or coordinate.repository_id != finalized.repository_id
        ):
            raise WritebackDecisionError("denied")
        if coordinate.generation_id != finalized.data_generation_id:
            raise WritebackDecisionError("needs_reconciliation")

    def _authorize_offer(
        self, connection: sqlite3.Connection, repository: RuntimeStateRepository,
        request: WritebackDecisionRequest, state: InstallationControlState, finalized: RuntimePublicationState,
    ) -> _AuthorizedOffer:
        self._credentials.verify_permissions()
        credential = self._credentials.credential_for(self._secret)
        if credential is None:
            raise WritebackDecisionError("unauthenticated")
        now = datetime.now(UTC)
        try:
            authority = self._grants.resolve_writeback_in_verified_context(
                credential=credential, request=request, state=state, finalized=finalized, now=now,
            )
        except HostCommandAuthorityError as exc:
            if str(exc).startswith("unsupported_configuration:"):
                raise WritebackDecisionError("unsupported_configuration") from exc
            raise WritebackDecisionError("denied") from exc
        if repository.partition.read_schema_version(connection) < 3:
            raise WritebackDecisionError("unsupported_configuration")
        task = repository.get_task_in(connection, request.task_id)
        if task is None or task.principal != authority.principal or self._revoked.is_revoked_task(request.task_id):
            raise WritebackDecisionError("denied")
        try:
            result = repository.get_consolidation_result_in(connection, request.result_id)
        except (RuntimeStateError, ValidationError) as exc:
            raise WritebackDecisionError("integrity_error") from exc
        if (
            result is None or result.origin.task_id != task.task_id
            or result.origin.client_namespace != authority.client_namespace
            or result.origin.operation_generation != finalized.data_generation_id
        ):
            raise WritebackDecisionError("not_found")
        origin_coordinate = OperationOriginCoordinate(
            installation_id=finalized.installation_id, repository_id=finalized.repository_id,
            generation_id=finalized.data_generation_id, principal=authority.principal,
            client_namespace=authority.client_namespace, operation_id=result.origin.operation_id,
            request_digest=result.origin.request_digest,
        )
        origin_receipt = repository.get_command_receipt_in(
            connection, operation_origin_namespace(origin_coordinate), origin_coordinate.operation_id,
        )
        if origin_receipt is None:
            raise WritebackDecisionError("not_found")
        if (
            result.origin.installation_id != finalized.installation_id
            or result.origin.partition_id != finalized.repository_id
            or origin_receipt.status != "committed" or origin_receipt.operation_origin != origin_coordinate
            or origin_receipt.consolidation_result_id != result.result_id
            or origin_receipt.current_revision != result.origin_revision
            or origin_receipt.result_digest != sha256(result.canonical_bytes()).hexdigest()
        ):
            raise WritebackDecisionError("integrity_error")
        output = next((item for item in result.outputs if item.output_id == request.output_id), None)
        if output is None:
            raise WritebackDecisionError("not_found")
        scope = candidate_scope(output, partition_id=finalized.repository_id, task_id=task.task_id)
        if scope is None or not authority.permits_writeback(scope):
            raise WritebackDecisionError("not_found")
        payload = output.payload
        if not isinstance(payload, EpisodicSummary | SemanticCandidate | SkillCandidate | UserCandidate):
            raise WritebackDecisionError("integrity_error")
        refs = payload.source_refs
        try:
            eligible = bool(refs) and all(ConsolidationReadService._source_is_current(
                connection, repository, ref, self._revoked, task.task_id, authority.principal, now,
                allow_protected=isinstance(payload, EpisodicSummary),
            ) for ref in refs)
        except ConsolidationReadError as exc:
            raise WritebackDecisionError("integrity_error") from exc
        if not eligible:
            raise WritebackDecisionError("not_found")
        if request.expected_payload_digest != output.payload_digest:
            raise WritebackDecisionError("conflict")
        coordinate = origin_coordinate.model_copy(update={
            "operation_id": request.operation_id, "request_digest": request.intent_digest(),
        })
        binding = DeliveryAuthorityBinding(
            installation_id=finalized.installation_id, principal=authority.principal,
            project_id=task.project, client_namespace=authority.client_namespace,
            host_binding_id=authority.client_namespace, credential_id=authority.credential_id,
            grant_id=authority.grant_id, grant_epoch=authority.grant_epoch, scope=scope, source_refs=refs,
        )
        return _AuthorizedOffer(coordinate, scope, binding)

    def _previous(
        self, connection: sqlite3.Connection, repository: RuntimeStateRepository,
        request: WritebackDecisionRequest, coordinate: OperationOriginCoordinate, *, proof: OperationOrigin | None = None,
    ) -> WritebackDecisionReceipt | None:
        command_receipt = repository.get_command_receipt_in(
            connection, operation_origin_namespace(coordinate), coordinate.operation_id,
        )
        decision = load_recorded_decision(connection, repository, request.output_id)
        if command_receipt is None and decision is None:
            return None
        if (
            decision is None or command_receipt is None or proof is None
            or decision.origin != proof or decision.request != request
            or command_receipt.operation_origin != coordinate
            or command_receipt.status != "committed"
            or command_receipt.origin_proof_digest != operation_origin_proof_digest(proof)
            or command_receipt.result_digest != decision.decision_id
        ):
            raise WritebackDecisionError("conflict")
        return decision.receipt(read_candidate_delivery(connection, repository, decision))

    @staticmethod
    def _enqueue(
        connection: sqlite3.Connection, repository: RuntimeStateRepository,
        decision: RecordedWritebackDecision, delivery: ManagedDelivery,
    ) -> None:
        delivery_id = delivery.request.delivery_id
        partition = repository.partition
        if partition.read_runtime_row(
            connection, table="runtime_outbox_deliveries", match=(("delivery_id", delivery_id),),
        ) is not None:
            raise WritebackDecisionError("integrity_error")
        entry = CandidateDeliveryEntry(decision_output_id=decision.request.output_id, delivery=delivery)
        partition.upsert_runtime_row(
            connection, table="runtime_outbox_deliveries", keys=("delivery_id",), values=(delivery_id,),
            record_json=entry.model_dump_json(),
        )
