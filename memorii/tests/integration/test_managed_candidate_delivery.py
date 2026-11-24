"""Signed accept, claim, and target publication against a real installation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Literal

import pytest
from memorii.core.consolidation.runtime_outputs import (
    ConsolidationOrigin,
    ConsolidationPayload,
    ConsolidationSourceReference,
    EpisodicSummary,
    SemanticCandidate,
    SkillCandidate,
    UserCandidate,
    build_consolidation_result,
)
from memorii.core.harness_state.credentials import SidecarCredentialStore
from memorii.core.harness_state.managed_ingress import authenticated_host_commands
from memorii.core.harness_state.write_authority import HostCommandGrantRequest, ManagedHostCommandAuthority
from memorii.core.harness_state.writeback_decision import WritebackDecisionService
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import MemoryPlaneGovernedWritePolicyRequiredError, record_digest
from memorii.core.persistence.managed_delivery import DeliveryTransitionError
from memorii.core.persistence.runtime_api import operation_origin_namespace, operation_origin_proof_digest
from memorii.core.persistence.runtime_contracts import OperationOrigin, RuntimeCommandReceipt, RuntimeCommandRequest
from memorii.core.persistence.runtime_repository import RuntimeStateRepository, publish_runtime_change
from memorii.core.persistence.writeback_decisions import (
    CandidateDeliveryEntry,
    WritebackDecisionReceipt,
    WritebackDecisionRequest,
    WritebackHostBinding,
    candidate_scope,
)
from memorii.core.promotion.context_builder import PromotionExecutionContextBuilder
from memorii.core.provider.runtime_candidate import ProtectedSkillCandidate
from memorii.core.provider.runtime_candidate_delivery import ManagedCandidateDeliveryWorker
from memorii.core.storage_administration.operator import (
    ModeChangeRequest,
    StorageAdministrationOperator,
    mint_owner_capability,
)
from memorii.core.storage_administration.service import InstallationQuarantinedError, StorageAdministrationService
from memorii.core.storage_administration.suppression_journal import (
    SuppressionCoordinate,
    SuppressionRecord,
    write_suppression_record,
)
from memorii.core.storage_administration.writer_enrollment import WriterEnrollmentError, WriterEnrollmentRegistry
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility

_WORKER = "candidate-publisher"


@dataclass(frozen=True)
class _Accepted:
    request: WritebackDecisionRequest
    proof: OperationOrigin
    receipt: WritebackDecisionReceipt
    service: WritebackDecisionService
    source: CanonicalMemoryRecord

    @property
    def delivery_id(self) -> str:
        assert self.receipt.delivery_id is not None
        return self.receipt.delivery_id

    @property
    def candidate_id(self) -> str:
        return f"cand:runtime:{self.request.output_id}"


def _accept(
    administration: StorageAdministrationService,
    kind: Literal["episodic", "semantic", "user", "skill"],
) -> _Accepted:
    administration.initialize()
    credentials = SidecarCredentialStore(administration.installation_root / "control" / "credentials")
    credential, secret = credentials.issue("principal")
    capability = mint_owner_capability(administration, "owner")
    grants = ManagedHostCommandAuthority(administration)
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    grants.issue(HostCommandGrantRequest(
        grant_id="start", credential_id=credential.credential_id, principal=credential.principal,
        allowed_kinds=("start_task",), client_namespace="host:start", expires_at=expires_at,
    ), capability=capability)
    commands = authenticated_host_commands(administration, credentials, secret)
    start = RuntimeCommandRequest(kind="start_task", operation_id="start", goal="candidate fixture")
    commands.dispatch(start, operation_origin=commands.prepare(start))
    task, = RuntimeStateRepository(administration.partition()).list_tasks()
    source = CanonicalMemoryRecord(
        memory_id="source", domain=MemoryDomain.TRANSCRIPT, text="retained source",
        status=CommitStatus.COMMITTED, task_id=task.task_id, user_id=credential.principal,
    )
    administration.publish_memory_plane_batch((source,))
    ref = ConsolidationSourceReference(source_id=source.memory_id, source_digest=record_digest(source))
    payloads: dict[str, ConsolidationPayload] = {
        "episodic": EpisodicSummary(summary="episode", source_refs=(ref,)),
        "semantic": SemanticCandidate(abstraction="abstraction", source_refs=(ref,)),
        "user": UserCandidate(preference="preference", source_refs=(ref,)),
        "skill": SkillCandidate(title="skill", summary="summary", steps=("step",), source_refs=(ref,)),
    }
    with administration.verified_operation_context() as (state, finalized):
        origin = ConsolidationOrigin(
            installation_id=state.installation_id, partition_id=finalized.repository_id,
            operation_generation=finalized.data_generation_id, task_id=task.task_id,
            client_namespace="host:candidate", operation_id="consolidate", request_digest="a" * 64,
        )
    results: list[WritebackDecisionRequest] = []

    def seed_sealed_result(connection, repository: RuntimeStateRepository) -> None:
        # Until source-backed producers are installed, seed the upstream
        # owner's typed output and receipt through the same signed publisher.
        revision = repository.read_runtime_revision_in(connection)
        result = build_consolidation_result(origin, origin_revision=revision, outputs=(payloads[kind],))
        (output,) = result.outputs
        repository.apply_consolidation_result(connection, result)
        from memorii.core.persistence.runtime_contracts import OperationOriginCoordinate

        coordinate = OperationOriginCoordinate(
            installation_id=origin.installation_id, repository_id=origin.partition_id,
            generation_id=origin.operation_generation, principal=credential.principal,
            client_namespace=origin.client_namespace, operation_id=origin.operation_id,
            request_digest=origin.request_digest,
        )
        proof = administration.sign_operation_origin(coordinate)
        repository.apply_command_receipt(
            connection,
            RuntimeCommandReceipt(
                operation_id=origin.operation_id, client_namespace=origin.client_namespace,
                request_digest=origin.request_digest, status="committed",
                base_revision=revision - 1, current_revision=revision,
                result_digest=sha256(result.canonical_bytes()).hexdigest(), consolidation_result_id=result.result_id,
                operation_origin=coordinate, origin_proof_digest=operation_origin_proof_digest(proof),
            ),
            lookup_namespace=operation_origin_namespace(coordinate),
        )
        results.append(WritebackDecisionRequest(
            host_binding=WritebackHostBinding(
                installation_id=origin.installation_id, client_namespace=origin.client_namespace, task_id=task.task_id,
            ),
            task_id=task.task_id, result_id=result.result_id, output_id=output.output_id,
            expected_offer_version=1, expected_payload_digest=output.payload_digest,
            operation_id="accept", decision="accept",
        ))

    publish_runtime_change(administration, seed_sealed_result)
    request = results[0]
    result = RuntimeStateRepository(administration.partition()).get_consolidation_result(request.result_id)
    assert result is not None
    scope = candidate_scope(result.outputs[0], partition_id=origin.partition_id, task_id=task.task_id)
    assert scope is not None
    grants.issue(HostCommandGrantRequest(
        grant_id="writeback", credential_id=credential.credential_id, principal=credential.principal,
        client_namespace=origin.client_namespace, allowed_writeback_scopes=(scope,), expires_at=expires_at,
    ), capability=capability)
    service = WritebackDecisionService(administration, credentials, secret)
    proof = service.prepare(request)
    return _Accepted(request, proof, service.decide(request, operation_origin=proof), service, source)


def _enroll(administration: StorageAdministrationService) -> None:
    WriterEnrollmentRegistry(administration.installation_root / "control" / "writers").enroll(
        _WORKER, kind="managed_writeback_candidate",
    )


@pytest.mark.parametrize("kind", ["episodic", "semantic", "user", "skill"])
def test_candidate_delivery_publishes_one_inert_effect_and_verified_receipt(tmp_path: Path, kind) -> None:
    root = tmp_path / "installation"
    with StorageAdministrationService(root) as administration:
        accepted = _accept(administration, kind)
        worker = ManagedCandidateDeliveryWorker(administration, worker_id=_WORKER)
        with pytest.raises(WriterEnrollmentError, match="not enrolled"):
            worker.claim(accepted.delivery_id)
        _enroll(administration)
        assert administration.memory_plane_store().get_record(accepted.candidate_id) is None
        before = administration.acquire_verified_snapshot()
        claim = worker.claim(accepted.delivery_id)
        assert claim is not None
        receipt = worker.publish(claim)
        assert receipt is not None and receipt.effect.record_id == accepted.candidate_id
        after = administration.acquire_verified_snapshot()
        assert after.vector.memory_data_revision == before.vector.memory_data_revision
        assert accepted.service.decide(accepted.request, operation_origin=accepted.proof).delivery_status == "delivered"

    with StorageAdministrationService(root) as reopened:
        worker = ManagedCandidateDeliveryWorker(reopened, worker_id=_WORKER)
        assert reopened.acquire_verified_snapshot() == after
        assert worker.publish(claim) == receipt
        assert reopened.acquire_verified_snapshot() == after
        if kind == "skill":
            assert after.vector.memory_write_revision == before.vector.memory_write_revision
            assert reopened.memory_plane_store().get_record(accepted.candidate_id) is None
            with reopened.partition().transaction(write=False) as connection:
                raw = reopened.partition().read_delivery_record(
                    connection, catalog="runtime_skill_candidates", record_id=accepted.candidate_id,
                )
            assert raw is not None
            assert ProtectedSkillCandidate.model_validate_json(raw).digest() == receipt.effect.record_digest
        else:
            assert after.vector.memory_write_revision == before.vector.memory_write_revision + 1
            store = reopened.memory_plane_store()
            candidate = store.get_record(accepted.candidate_id)
            assert candidate is not None and candidate.domain == kind
            assert candidate.status == CommitStatus.CANDIDATE
            assert candidate.visibility == MemoryRecordVisibility.INTERNAL_CONTROL
            assert record_digest(candidate) == receipt.effect.record_digest
            promotion = PromotionExecutionContextBuilder(memory_plane=MemoryPlaneService(record_store=store))
            assert promotion.list_staged_candidates() == []
            with pytest.raises(ValueError, match="not a staged candidate"):
                promotion.build(candidate_id=accepted.candidate_id)
            overwrite = candidate.model_copy(update={"source_kind": "forged", "text": "overwrite"})
            with pytest.raises(MemoryPlaneGovernedWritePolicyRequiredError):
                reopened.publish_memory_plane_batch((overwrite,))


def test_candidate_delivery_rechecks_source_and_mode_after_claim(tmp_path: Path) -> None:
    with StorageAdministrationService(tmp_path / "installation") as administration:
        accepted = _accept(administration, "semantic")
        _enroll(administration)
        operator = StorageAdministrationOperator(administration)
        capability = mint_owner_capability(administration, "owner")
        moment = datetime.now(UTC)
        worker = ManagedCandidateDeliveryWorker(administration, worker_id=_WORKER, clock=lambda: moment)
        claim = worker.claim(accepted.delivery_id)
        assert claim is not None
        paused = operator.change_mode(ModeChangeRequest(
            target_mode="read_only", expected_control_revision=operator.status().control_revision, reason="pause",
        ), capability=capability)
        with pytest.raises(InstallationQuarantinedError, match="read_only"):
            worker.publish(claim)
        operator.change_mode(ModeChangeRequest(
            target_mode="active", expected_control_revision=paused.control_revision, reason="resume",
        ), capability=capability)
        with pytest.raises(DeliveryTransitionError, match="stale"):
            worker.publish(claim)
        assert worker.claim(accepted.delivery_id) is None
        moment += timedelta(seconds=2)
        current = worker.claim(accepted.delivery_id)
        assert current is not None
        write_suppression_record(administration.installation_root / "control", SuppressionRecord(
            suppression_id="1" * 64, plan_digest="2" * 64, closure_digest="3" * 64,
            scope_note="suppressed source",
            suppressed=(SuppressionCoordinate(coordinate_kind="source", coordinate_id=accepted.source.memory_id),),
            applied_at_unix=1,
        ))
        assert worker.publish(current) is None
        partition = administration.partition()
        with partition.transaction(write=False) as connection:
            row = partition.read_runtime_row(
                connection, table="runtime_outbox_deliveries", match=(("delivery_id", accepted.delivery_id),),
            )
            assert row is not None
            progress = CandidateDeliveryEntry.model_validate_json(row["record_json"]).delivery.progress
            assert progress.model_dump() == {"status": "rejected", "reason": "forgotten"}
            assert partition.read_delivery_record(
                connection, catalog="runtime_target_receipts", record_id=accepted.delivery_id,
            ) is None
        assert administration.memory_plane_store().get_record(accepted.candidate_id) is None


def test_candidate_effect_and_receipt_share_the_runtime_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "installation"
    with StorageAdministrationService(root) as administration:
        accepted = _accept(administration, "semantic")
        _enroll(administration)
        worker = ManagedCandidateDeliveryWorker(administration, worker_id=_WORKER)
        claim = worker.claim(accepted.delivery_id)
        assert claim is not None
        before = administration.acquire_verified_snapshot()

        def before_receipt(connection, **kwargs) -> None:
            assert kwargs["catalog"] == "runtime_target_receipts"
            assert administration.partition().read_current_record_row(connection, accepted.candidate_id) is not None
            raise RuntimeError("target transaction interrupted before receipt")

        with monkeypatch.context() as cut:
            cut.setattr(administration.partition(), "insert_delivery_record", before_receipt)
            with pytest.raises(RuntimeError, match="interrupted before receipt"):
                worker.publish(claim)
        assert administration.acquire_verified_snapshot() == before
        assert administration.memory_plane_store().get_record(accepted.candidate_id) is None

        def before_finalization(_signed_state) -> None:
            raise RuntimeError("target transaction committed before acknowledgement")

        with monkeypatch.context() as cut:
            cut.setattr(administration, "_finalize_publication", before_finalization)
            with pytest.raises(RuntimeError, match="before acknowledgement"):
                worker.publish(claim)

    with StorageAdministrationService(root) as reopened:
        worker = ManagedCandidateDeliveryWorker(reopened, worker_id=_WORKER)
        recovered = reopened.acquire_verified_snapshot()
        receipt = worker.publish(claim)
        assert receipt is not None
        assert receipt.effect.record_id == accepted.candidate_id
        assert recovered.vector.memory_write_revision == before.vector.memory_write_revision + 1
        assert reopened.acquire_verified_snapshot() == recovered
