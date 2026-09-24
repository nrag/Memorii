from datetime import UTC, datetime

from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    AuthenticatedSemanticEgressGovernance,
    AuthenticatedSemanticSourceAuthority,
    AuthenticatedSemanticSourceInterval,
    DeliveryPrincipalBinding,
    RequiredOutcomeScopeSet,
    derive_composite_child_delivery_id,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import InMemoryMemoryPlaneStore
from memorii.core.semantic_ingestion.contracts import (
    AuthenticatedSourceIntervalEvidence,
    SourceAuthorityEvidence,
)
from memorii.core.semantic_ingestion.hermes_completed_turn_admission import (
    HermesCompletedTurnAdmissionRequest,
    HermesCompletedTurnAdmissionService,
    HermesCompletedTurnMessage,
    canonical_transcript_digest,
)

NOW = datetime(2026, 9, 23, tzinfo=UTC)


def _service() -> tuple[HermesCompletedTurnAdmissionService, MemoryPlaneService]:
    plane = MemoryPlaneService(record_store=InMemoryMemoryPlaneStore())
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW)
    binding = writers.commit_binding(
        writers.create_initial_evidence_only(
            admission_id="hermes-completed-turn",
            writer_implementation_fingerprint="test-writer",
            graph_schema_fingerprint="test-graph",
        )
    )
    store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: NOW)
    return HermesCompletedTurnAdmissionService(atomic_store=store, writer_binding=binding), plane


def _request(
    *,
    user: str = "The Mars Venus 001 project owner is Ada.",
    assistant: str = "I will remember that.",
    turn_ordinal: int = 1,
) -> HermesCompletedTurnAdmissionRequest:
    principal = DeliveryPrincipalBinding.create(
        principal_subject_id="operator:nr", tenant_partition_id="local:nr", provider_identity="hermes"
    )
    scopes = RequiredOutcomeScopeSet.create(
        tenant_partition_id="local:nr", scopes={"session:session:one", "user:operator:nr"}
    )
    messages = (
        HermesCompletedTurnMessage(role="user", content=user),
        HermesCompletedTurnMessage(role="assistant", content=assistant),
    )
    return HermesCompletedTurnAdmissionRequest(
        installation_id="install:one",
        session_id="session:one",
        authenticated_author_id="operator:nr",
        authenticated_agent_id="memorii.hermes.agent.absent.v1",
        project_task_namespace="project:Mars-Venus-001",
        turn_ordinal=turn_ordinal,
        canonical_transcript_digest=canonical_transcript_digest(messages),
        completed_messages=messages,
        completed_at=NOW,
        ingress=AuthenticatedIngressContext(
            delivery_principal_binding=principal,
            required_outcome_scopes=scopes,
            current_authorized_scopes=scopes,
            language_declaration="en",
            language_evidence_kind="authenticated_host_declaration",
            language_evidence_trust="trusted",
            language_governance_agreement="agrees",
            semantic_egress_governance=AuthenticatedSemanticEgressGovernance(
                classification="trial",
                provider="openai",
                model="gpt-4.1-nano",
                region="local",
                retention_mode="store_false",
                training_use=False,
            ),
            semantic_source_authority=AuthenticatedSemanticSourceAuthority(
                authority_class="official",
                authenticated_provenance_class="authenticated_user",
                policy_revision="test",
                provenance_digest="b" * 64,
            ),
            semantic_source_interval=AuthenticatedSemanticSourceInterval(
                start=NOW,
                authority_basis="server_source_metadata",
                provenance_digest="b" * 64,
                policy_revision="test",
            ),
        ),
    )


def test_admission_atomically_retains_ordered_children_and_live_fenced_operation() -> None:
    service, plane = _service()
    request = _request()

    admitted = service.admit(request)

    inputs = admitted.normalization_inputs
    assert inputs.source_ids[0] != inputs.source_ids[1]
    assert inputs.child_delivery_identities[0] != inputs.child_delivery_identities[1]
    assert inputs.child_delivery_ids == (
        derive_composite_child_delivery_id(request.delivery_id, "hermes-completed-turn-user"),
        derive_composite_child_delivery_id(request.delivery_id, "hermes-completed-turn-assistant"),
    )
    assert inputs.child_delivery_identities[0].normalized_delivery_id.value == inputs.child_delivery_ids[0]
    assert inputs.operation_fence.delivery_identity == inputs.child_delivery_identities[0]
    assert inputs.source_admissions[0].operation_fence_binding == inputs.operation_fence
    retained = [record for record in plane.list_records() if record.source_kind == "semantic_ingestion_source"]
    assert len(retained) == 2
    assert all("step_one_material_ctv" in record.content["source_admission"] for record in retained)
    for record, source_digest in zip(retained, inputs.source_digests, strict=True):
        authority = SourceAuthorityEvidence.model_validate(
            record.content["source_admission"]["retained_source_authority_evidence"]
        )
        interval = AuthenticatedSourceIntervalEvidence.model_validate(
            record.content["source_admission"]["retained_source_interval_evidence"]
        )
        assert (authority.source_id, authority.source_digest) == (
            record.memory_id,
            source_digest,
        )
        assert interval.source_authority_evidence_digest == authority.evidence_digest
    assert (
        len([record for record in plane.list_records() if record.source_kind == "semantic_ingestion_admission_index"])
        == 2
    )


def test_exact_replay_is_idempotent() -> None:
    service, plane = _service()
    first = service.admit(_request())
    replay = service.admit(_request())

    assert replay.normalization_inputs.operation_fence == first.normalization_inputs.operation_fence


def test_reopen_recovers_the_exact_completed_turn_group() -> None:
    service, plane = _service()
    first = service.admit(_request())
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW)
    store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: NOW)
    reopened = HermesCompletedTurnAdmissionService(
        atomic_store=store,
        writer_binding=first.publication.operation.writer_binding,
    )

    replay = reopened.admit(_request())

    assert replay.normalization_inputs == first.normalization_inputs
    assert replay.normalization_inputs.operation_fence == first.normalization_inputs.operation_fence


def test_changed_full_transcript_digest_at_same_ordinal_has_a_new_coordinate() -> None:
    service, _ = _service()
    first = service.admit(_request())
    changed = _request(assistant="Different completion.").model_copy(update={"canonical_transcript_digest": "b" * 64})

    assert service.admit(changed).normalization_inputs.operation_fence != first.normalization_inputs.operation_fence


def test_equal_text_at_a_later_ordinal_is_distinct() -> None:
    service, _ = _service()
    first = service.admit(_request())
    later = _request(turn_ordinal=2)
    second = service.admit(later)

    assert first.normalization_inputs.operation_fence != second.normalization_inputs.operation_fence


def test_delivery_coordinate_includes_the_full_canonical_transcript_digest() -> None:
    first = _request()
    second = _request().model_copy(update={"canonical_transcript_digest": "a" * 64})

    assert first.delivery_id != second.delivery_id


def test_rejects_substituted_child_coordinate_evidence() -> None:
    import pytest

    service, _ = _service()
    admitted = service.admit(_request())
    values = admitted.normalization_inputs.model_dump(mode="python")
    values["child_delivery_ids"] = ("substituted", values["child_delivery_ids"][1])

    with pytest.raises(ValueError, match="child delivery coordinate"):
        admitted.normalization_inputs.__class__.model_validate(values)


def test_governance_denial_leaves_no_partial_completed_turn_group() -> None:
    import pytest

    service, plane = _service()
    denied = _request().model_copy(
        update={"ingress": _request().ingress.model_copy(update={"semantic_egress_governance": None})}
    )

    with pytest.raises(ValueError, match="governance"):
        service.admit(denied)

    assert not [
        record
        for record in plane.list_records()
        if record.source_kind.startswith("semantic_ingestion_")
        and record.source_kind != "semantic_ingestion_writer_admission"
    ]


def test_transcript_digest_is_part_of_the_delivery_coordinate() -> None:
    request = _request()
    changed = request.model_copy(update={"canonical_transcript_digest": "0" * 64})

    assert changed.delivery_id != request.delivery_id
