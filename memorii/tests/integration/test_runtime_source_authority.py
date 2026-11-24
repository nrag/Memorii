from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from memorii.core.consolidation.runtime_outputs import ArchivePackage, EpisodicSummary
from memorii.core.filesystem_storage.bundle import FilesystemStorageBundle
from memorii.core.harness_state.consolidation_read import (
    ConsolidationReadRequest,
    authenticated_consolidation_reader,
)
from memorii.core.harness_state.credentials import SidecarCredentialStore
from memorii.core.harness_state.managed_ingress import authenticated_host_commands, authenticated_provider_observations
from memorii.core.harness_state.service import RuntimeReadGrant
from memorii.core.harness_state.write_authority import HostCommandGrantRequest, ManagedHostCommandAuthority
from memorii.core.harness_state.writeback_decision import WritebackDecisionError, WritebackDecisionService
from memorii.core.memory_evolution.admission import SourceAdmissionAccepted
from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    AuthenticatedSemanticEgressGovernance,
    AuthenticatedSemanticSourceAuthority,
    DeliveryPrincipalBinding,
    RequiredOutcomeScopeSet,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.persistence.managed_delivery import MemoryPlaneCandidateScope
from memorii.core.persistence.runtime_api import RuntimeCommandError
from memorii.core.persistence.runtime_contracts import OperationOriginCoordinate, RuntimeCommandRequest
from memorii.core.persistence.runtime_repository import RuntimeStateRepository
from memorii.core.persistence.writeback_decisions import WritebackDecisionRequest, WritebackHostBinding
from memorii.core.provider.runtime_candidate_delivery import ManagedCandidateDeliveryWorker
from memorii.core.provider.runtime_source_authority import (
    RuntimeSourceAuthorityError,
    RuntimeSourceEvidence,
    RuntimeSourceTaskBinding,
    resolve_runtime_source,
)
from memorii.core.provider.runtime_source_release import RuntimeSourceReleaseAuthority
from memorii.core.semantic_ingestion.hermes_completed_turn_admission import (
    HermesCompletedTurnAdmissionRequest,
    HermesCompletedTurnAdmissionService,
    HermesCompletedTurnMessage,
    canonical_transcript_digest,
)
from memorii.core.storage_administration.operator import mint_owner_capability
from memorii.core.storage_administration.revoked_identity_view import RevokedIdentities, RevokedIdentityView
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.core.storage_administration.suppression_journal import (
    SuppressionCoordinate,
    SuppressionRecord,
    write_suppression_record,
)
from memorii.core.storage_administration.writer_enrollment import WriterEnrollmentRegistry
from memorii.domain.enums import SourceModality

_NOW = datetime(2026, 11, 23, tzinfo=UTC)


def _request(installation_id: str) -> HermesCompletedTurnAdmissionRequest:
    principal = DeliveryPrincipalBinding.create(
        principal_subject_id="operator:one", tenant_partition_id="tenant:one", provider_identity="hermes",
    )
    scopes = RequiredOutcomeScopeSet.create(
        tenant_partition_id="tenant:one", scopes={"session:session:one", "user:operator:one"},
    )
    messages = (
        HermesCompletedTurnMessage(role="user", content="The component is ready for review."),
        HermesCompletedTurnMessage(role="assistant", content="I will remember that."),
    )
    return HermesCompletedTurnAdmissionRequest(
        installation_id=installation_id, session_id="session:one", authenticated_author_id="operator:one",
        authenticated_agent_id="agent:one", project_task_namespace="project:one", turn_ordinal=1,
        canonical_transcript_digest=canonical_transcript_digest(messages), completed_messages=messages,
        completed_at=_NOW,
        ingress=AuthenticatedIngressContext(
            delivery_principal_binding=principal, required_outcome_scopes=scopes, current_authorized_scopes=scopes,
            language_declaration="en", language_evidence_kind="authenticated_host_declaration",
            language_evidence_trust="trusted", language_governance_agreement="agrees",
            semantic_egress_governance=AuthenticatedSemanticEgressGovernance(
                classification="trial", provider="test", model="test", region="local",
                retention_mode="store_false", training_use=False,
            ),
            semantic_source_authority=AuthenticatedSemanticSourceAuthority(
                authority_class="official", authenticated_provenance_class="authenticated_user",
                policy_revision="test", provenance_digest="b" * 64,
            ),
        ),
    )


@pytest.mark.parametrize("revoke_at", ["source_suppression", "pause", "decision", "effect", "delivered"])
def test_managed_runtime_source_requires_exact_provider_admission_and_live_scope(
    tmp_path: Path, revoke_at: str,
) -> None:
    root = tmp_path / "installation"
    with StorageAdministrationService(root) as administration:
        installation = administration.initialize()
        memory_plane = FilesystemStorageBundle.from_managed_root(root, administration).build_memory_plane_service()
        writers = SemanticWriterAdmissionStore(
            memory_plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: _NOW,
        )
        writer = writers.commit_binding(writers.create_initial_evidence_only(
            admission_id="source-writer", writer_implementation_fingerprint="test-writer",
            graph_schema_fingerprint="test-graph",
        ))
        owner = HermesCompletedTurnAdmissionService(
            atomic_store=SemanticIngestionAtomicStore(memory_plane, writers, now_provider=lambda: _NOW),
            writer_binding=writer,
        )
        request = _request(installation.installation_id)
        admitted = owner.admit(request)
        user, assistant = admitted.normalization_inputs.source_admissions
        credentials = SidecarCredentialStore(root / "control" / "credentials")
        credential, secret = credentials.issue("runtime:one")
        owner_capability = mint_owner_capability(administration, "runtime:one")
        grants = ManagedHostCommandAuthority(administration)
        expires_at = datetime.now(UTC) + timedelta(minutes=5)
        grants.issue(HostCommandGrantRequest(
            grant_id="start", credential_id=credential.credential_id, principal=credential.principal,
            client_namespace="host:start", allowed_kinds=("start_task",), expires_at=expires_at,
        ), capability=owner_capability)
        bootstrap = authenticated_host_commands(administration, credentials, secret)
        start = RuntimeCommandRequest(kind="start_task", operation_id="start", goal="Review captured evidence")
        bootstrap.dispatch(start, operation_origin=bootstrap.prepare(start))
        task, = RuntimeStateRepository(administration.partition()).list_tasks()
        grants.issue(HostCommandGrantRequest(
            grant_id="observe", credential_id=credential.credential_id, principal=credential.principal,
            client_namespace="host:one", allowed_kinds=("record_observation", "pause_task", "resume_task"),
            allowed_task_ids=(task.task_id,),
            allowed_writeback_scopes=(MemoryPlaneCandidateScope(
                partition_id=installation.repository_id, task_id=task.task_id, domain="episodic",
            ),),
            expires_at=expires_at,
        ), capability=owner_capability)
        origin = OperationOriginCoordinate(
            installation_id=installation.installation_id, repository_id=installation.repository_id,
            generation_id=installation.data_generation_id, principal="runtime:one",
            client_namespace="host:one", operation_id="observe", request_digest="1" * 64,
        )
        binding = RuntimeSourceTaskBinding(
            installation_id=origin.installation_id, repository_id=origin.repository_id,
            generation_id=origin.generation_id, runtime_task_id=task.task_id,
            runtime_principal=origin.principal, client_namespace=origin.client_namespace,
            provider_task_id=request.project_task_namespace, provider_session_id=request.session_id,
            provider_principal_binding_digest=request.ingress.delivery_principal_binding.binding_digest,
            delivery_key_digest=user.delivery_identity.delivery_key_digest,
        )

    # Prove the authorization is reconstructed from the signed partition after
    # the provider writer has closed, with a separately resolved current grant.
    with StorageAdministrationService(root) as reopened, reopened.verified_operation_context() as (_, finalized):
        partition = reopened.partition()
        with partition.transaction(write=False) as connection:
            def resolve(
                *,
                selected: SourceAdmissionAccepted = user,
                scope: RuntimeSourceTaskBinding = binding,
                runtime_task: str = task.task_id,
                digest: str | None = None,
                live: AuthenticatedIngressContext | None = request.ingress,
                revoked: RevokedIdentityView | None = None,
            ) -> RuntimeSourceEvidence:
                return resolve_runtime_source(
                    connection, partition, finalized=finalized, origin=origin, runtime_task_id=runtime_task,
                    source_digest=digest or selected.source_digest, operation_fence=selected.operation_fence_binding,
                    resolve_ingress=lambda: live, binding=scope, revoked=revoked or RevokedIdentityView.empty(),
                    now=_NOW,
                )

            evidence = resolve()
            assert evidence.source_ref.source_id == user.source_id
            assert evidence.source_digest == user.source_digest
            assert evidence.source_ref.source_digest != user.source_digest
            assert evidence.admission_index_digest == user.admission_index_digest
            assert evidence.modalities == (SourceModality.ASSERTION,)
            assert request.completed_messages[0].content not in evidence.model_dump_json()

            with pytest.raises(RuntimeSourceAuthorityError, match="governed runtime source is unavailable"):
                resolve(runtime_task="task:another")
            with pytest.raises(RuntimeSourceAuthorityError, match="governed runtime source is unavailable"):
                resolve(digest="2" * 64)
            with pytest.raises(RuntimeSourceAuthorityError, match="governed runtime source is unavailable"):
                resolve(live=None)
                with pytest.raises(RuntimeSourceAuthorityError, match="governed runtime source is unavailable"):
                    resolve(live=request.ingress.model_copy(update={
                        "current_authorized_scopes": RequiredOutcomeScopeSet.create(
                            tenant_partition_id="tenant:one", scopes={"user:operator:one"},
                        ),
                    }))
            with pytest.raises(RuntimeSourceAuthorityError, match="governed runtime source is unavailable"):
                resolve(revoked=RevokedIdentityView(RevokedIdentities(sources=frozenset({user.source_id}))))
            with pytest.raises(RuntimeSourceAuthorityError, match="governed runtime source is unavailable"):
                resolve(selected=assistant, scope=binding.model_copy(update={
                    "delivery_key_digest": assistant.delivery_identity.delivery_key_digest,
                }))

    with StorageAdministrationService(root) as reopened:
        command = RuntimeCommandRequest(
            kind="record_observation", operation_id="observe", task_id=task.task_id,
            expected_revision=task.version, source_digest=user.source_digest,
        )
        unmanaged_source = authenticated_host_commands(reopened, credentials, secret)
        with pytest.raises(RuntimeCommandError, match="unsupported_configuration"):
            unmanaged_source.prepare(command)
        ingress_is_current = True
        runtime = authenticated_provider_observations(
            reopened, credentials, secret, binding=binding,
            operation_fence=user.operation_fence_binding,
            resolve_ingress=lambda: request.ingress if ingress_is_current else None,
        )
        proof = runtime.prepare(command)
        before = reopened.acquire_verified_snapshot()
        ingress_is_current = False
        with pytest.raises(RuntimeCommandError, match="verified provider admission is unavailable"):
            runtime.dispatch(command, operation_origin=proof)
        assert reopened.acquire_verified_snapshot() == before
        ingress_is_current = True
        receipt = runtime.dispatch(command, operation_origin=proof)
        assert receipt.source_admission is not None
        assert receipt.source_admission.source_id == user.source_id
        assert receipt.source_admission.admission_index_digest == user.admission_index_digest
        assert receipt.source_admission.source_record_digest == evidence.source_ref.source_digest
        assert receipt.source_admission.source_write_revision == evidence.source_write_revision
        assert request.completed_messages[0].content not in receipt.model_dump_json()
        release_id = None
        if revoke_at != "source_suppression":
            release_id = RuntimeSourceReleaseAuthority(reopened).issue(
                capability=mint_owner_capability(reopened, "runtime:one"), observation_origin=proof,
                binding=binding, operation_fence=user.operation_fence_binding, resolve_ingress=lambda: request.ingress,
            ).grant_id
        observed = reopened.acquire_verified_snapshot()

    with StorageAdministrationService(root) as reopened:
        assert reopened.acquire_verified_snapshot() == observed
        if revoke_at != "source_suppression":
            assert release_id is not None
            _exercise_durable_offer(
                reopened, credentials, secret, task.task_id, task.version + 1,
                release_id, revoke_at, request.completed_messages[0].content,
            )
            return
        runtime = authenticated_provider_observations(
            reopened, credentials, secret, binding=binding,
            operation_fence=user.operation_fence_binding, resolve_ingress=lambda: request.ingress,
        )
        assert runtime.dispatch(command, operation_origin=proof) == receipt
        assert reopened.acquire_verified_snapshot() == observed
        write_suppression_record(root / "control", SuppressionRecord(
            suppression_id="1" * 64, plan_digest="2" * 64, closure_digest="3" * 64,
            scope_note="native source", suppressed=(SuppressionCoordinate(
                coordinate_kind="source", coordinate_id=user.source_id,
            ),), applied_at_unix=1,
        ))
        with pytest.raises(RuntimeCommandError, match="verified provider admission is unavailable"):
            runtime.dispatch(command, operation_origin=proof)
        assert reopened.acquire_verified_snapshot() == observed


def _exercise_durable_offer(
    administration: StorageAdministrationService,
    credentials: SidecarCredentialStore,
    secret: str,
    task_id: str,
    revision: int,
    grant_id: str,
    revoke_at: str,
    protected_text: str,
) -> None:
    """Run every later boundary after both the source writer and live ingress close."""
    runtime = authenticated_host_commands(administration, credentials, secret)
    owner = mint_owner_capability(administration, "runtime:one")
    releases = RuntimeSourceReleaseAuthority(administration)
    pause = RuntimeCommandRequest(
        kind="pause_task", operation_id="pause", task_id=task_id, expected_revision=revision, pause_reason="review",
    )
    proof = runtime.prepare(pause)
    if revoke_at == "pause":
        releases.revoke(capability=owner, grant_id=grant_id)
        before = administration.acquire_verified_snapshot()
        with pytest.raises(RuntimeCommandError, match="archive closure"):
            runtime.dispatch(pause, operation_origin=proof)
        assert administration.acquire_verified_snapshot() == before
        return

    runtime.dispatch(pause, operation_origin=proof)
    read_grant = RuntimeReadGrant(
        grant_id="read:episode", principal="runtime:one", epoch=1,
        allowed_task_ids=(task_id,), expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    reader = authenticated_consolidation_reader(
        administration, credentials, secret, lambda _: read_grant,
    )
    # Install the finite read epoch alongside its already scoped write grant.
    from memorii.core.harness_state.grant_registry import GrantEpochRegistry

    GrantEpochRegistry(administration.installation_root / "control" / "grants").verify_permissions()
    query = ConsolidationReadRequest(task_id=task_id, origin_operation_id="pause")
    page = reader.read(query)
    episode, = [item for item in page.outputs if isinstance(item.output.payload, EpisodicSummary)]
    assert any(isinstance(item.output.payload, ArchivePackage) for item in page.outputs)
    assert episode.offer is not None and protected_text not in page.model_dump_json()
    offer = episode.offer
    decision = WritebackDecisionRequest(
        host_binding=WritebackHostBinding(
            installation_id=proof.coordinate.installation_id, client_namespace="host:one", task_id=task_id,
        ),
        task_id=task_id, result_id=page.result_id, output_id=offer.output_id, expected_offer_version=offer.offer_version,
        expected_payload_digest=offer.payload_digest, operation_id="decide", decision="accept",
    )
    decisions = WritebackDecisionService(administration, credentials, secret)
    decision_proof = decisions.prepare(decision)
    if revoke_at == "decision":
        releases.revoke(capability=owner, grant_id=grant_id)
        with pytest.raises(WritebackDecisionError, match="not_found"):
            decisions.decide(decision, operation_origin=decision_proof)
    else:
        accepted = decisions.decide(decision, operation_origin=decision_proof)
        writer = "worker:episode"
        WriterEnrollmentRegistry(administration.installation_root / "control" / "writers").enroll(
            writer, kind="managed_writeback_candidate",
        )
        worker = ManagedCandidateDeliveryWorker(administration, worker_id=writer)
        assert accepted.delivery_id is not None
        claim = worker.claim(accepted.delivery_id)
        assert claim is not None
        if revoke_at == "effect":
            releases.revoke(capability=owner, grant_id=grant_id)
            assert worker.publish(claim) is None
        else:
            receipt = worker.publish(claim)
            assert receipt is not None and worker.publish(claim) == receipt
            assert protected_text not in receipt.model_dump_json()
            resume = RuntimeCommandRequest(
                kind="resume_task", operation_id="resume", task_id=task_id, expected_revision=revision + 1,
            )
            runtime.dispatch(resume, operation_origin=runtime.prepare(resume))
            current_task = RuntimeStateRepository(administration.partition()).get_task(task_id)
            assert current_task is not None and current_task.lifecycle == "active"
            from memorii.tools.runtime_operator import main as operator_main

            assert operator_main([
                "--installation-root", str(administration.installation_root),
                "--owner-principal", owner.owner_principal, "--capability-digest", owner.capability_digest,
                "runtime-source-grant", "revoke", "--grant-id", grant_id,
            ]) == 0
            from memorii.core.persistence.managed_delivery import DeliveryTransitionError

            with pytest.raises(DeliveryTransitionError, match="denied"):
                worker.publish(claim)
        with pytest.raises(WritebackDecisionError, match="not_found"):
            decisions.decide(decision, operation_origin=decision_proof)
    hidden = reader.read(query)
    assert all(not isinstance(item.output.payload, EpisodicSummary | ArchivePackage) for item in hidden.outputs)
    with pytest.raises(RuntimeCommandError, match="archived source authority"):
        runtime.dispatch(pause, operation_origin=proof)
