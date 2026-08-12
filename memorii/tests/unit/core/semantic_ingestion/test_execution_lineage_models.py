from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.atomic_store import OperationLeaseBinding
from memorii.core.memory_evolution.ingestion_contracts import (
    DeliveryIdentity,
    DeliveryPrincipalBinding,
    OperationFenceBinding,
    decode_typed_value,
    encode_typed_value,
)
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.semantic_ingestion.contracts import (
    CANONICAL_INGESTION_EXECUTION_GRAPH,
    GovernanceCarrierArtifact,
    IngestionExecutionGraph,
    IngestionExecutionManifest,
    IngestionStageInstanceRef,
    IngestionStageOutcome,
    LanguageCandidate,
    MessageAdmissionCarrierSet,
    MessageAdmissionIdentity,
    OperationCapabilityExecutionBinding,
    PlannedSourceIngestionProgress,
    PrePlanningSourceIngestionProgress,
    RequiredOutcomeScopeSet,
    SegmentGovernanceBinding,
    SegmentGovernanceCarrierSet,
    SegmentLanguageResourceBinding,
    SegmentLanguageRoute,
    SegmentLanguageRouteSet,
    SemanticContractCodecError,
    SourceIngestionProgress,
    SourceTransactionPlanLineageReference,
    canonical_contract_value,
    decode_semantic_contract,
    encode_semantic_contract,
)
from memorii.domain.enums import SourceModality
from pydantic import TypeAdapter


def _digest(character: str) -> str:
    return character * 64


def _hash(label: str) -> str:
    return sha256(label.encode()).hexdigest()


def _carrier_artifact() -> GovernanceCarrierArtifact:
    binding = SegmentGovernanceBinding.create(
        source_id="source-1", segment_id="segment-1", message_semantic_context_digest=_hash("context"),
        effective_scope_digest=_hash("scope"), authority_digest=_hash("authority"), data_classification="internal",
        modality=SourceModality.ASSERTION, provider_egress_decision_digest=_hash("egress"),
        egress_disposition="allow_verbatim",
    )
    governance = SegmentGovernanceCarrierSet.create(source_id="source-1", bindings=(binding,))
    admissions = MessageAdmissionCarrierSet.create(source_id="source-1", identities=(
        MessageAdmissionIdentity.create(
            delivery_principal_binding_digest=_hash("principal"), authenticated_source_reference="source-ref-1",
            authenticated_source_reference_key_digest=_hash("source-ref"), message_bytes_digest=_hash("message"),
            segment_governance_binding_digest=binding.binding_digest,
        ),
    ))
    scopes = RequiredOutcomeScopeSet.create(tenant_partition_id="tenant-1", scopes=(MemoryScope(user_id="user-1"),))
    return GovernanceCarrierArtifact.create(
        artifact_id="governance-1", atomic_generation=1, segment_governance=governance,
        message_admissions=admissions, required_outcome_scopes=scopes,
    )


def _route() -> SegmentLanguageRoute:
    resources = SegmentLanguageResourceBinding.create(
        selected_language="en", proposal_capability_fingerprint=_hash("proposal-capability"),
        stanza_analyzer_manifest_digest=_hash("stanza"), spacy_analyzer_manifest_digest=_hash("spacy"),
        predicate_event_manifest_digest=_hash("predicate"), temporal_resolver_manifest_digest=_hash("temporal"),
    )
    return SegmentLanguageRoute.create(
        source_id="source-1", source_digest=_hash("source"), segment_id="segment-1",
        parent_projection_segment_id="segment-1",
        segment_text_artifact_id="segment-artifact-1", segment_text_artifact_digest=_hash("segment-artifact"),
        segment_text_content_digest=_hash("segment-content"), declared_language=None,
        candidates=(LanguageCandidate(language="en", probability_ppm=1_000_000, model_fingerprint=_hash("router")),),
        code_switch_spans=(),
        selected_language="en", decision="selected", minimum_probability_ppm=1, minimum_margin_ppm=1,
        routing_policy_fingerprint=_hash("routing-policy"), router_manifest_fingerprint=_hash("router"), resource_binding=resources,
    )


def _lease(operation_id: str = "operation-1") -> OperationLeaseBinding:
    principal = DeliveryPrincipalBinding.create(principal_subject_id="principal-1", tenant_partition_id="tenant-1", provider_identity="provider-1")
    delivery = DeliveryIdentity.create(principal, "delivery-1")
    fence = OperationFenceBinding.create(operation_id=operation_id, source_id="source-1", source_digest=_hash("source"), delivery_identity=delivery)
    values = {
        "operation_id": operation_id, "operation_fence_binding": fence,
        "delivery_principal_binding_digest": fence.delivery_principal_binding_digest,
        "delivery_key_digest": fence.delivery_key_digest, "allocation_namespace_id": fence.allocation_namespace_id,
        "writer_namespace": "semantic_ingestion", "admitted_writer_epoch": 1, "writer_admission_digest": _hash("writer-admission"),
        "writer_implementation_fingerprint": "implementation-1", "state_revision": 1, "owner_id": "owner-1",
        "execution_token": "token-1", "ownership_epoch": 1, "lease_expires_at": datetime(2026, 1, 2, tzinfo=UTC),
    }
    digest_values = {**values, "operation_fence_binding": fence.model_dump(mode="python")}
    return OperationLeaseBinding(**values, binding_digest=sha256(encode_typed_value(digest_values)).hexdigest())


def _outcome(instance: IngestionStageInstanceRef, *, status: str = "complete", blockers: tuple[IngestionStageInstanceRef, ...] = ()) -> IngestionStageOutcome:
    if status == "not_started":
        return IngestionStageOutcome(instance=instance, status=status, blocking_stages=blockers)
    return IngestionStageOutcome(
        instance=instance, status=status, started_at=datetime(2026, 1, 1, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, 0, 1, tzinfo=UTC), artifact_digest=_hash(f"artifact:{instance.stage}:{instance.scope}"),
        reason_codes=("fixture_failure",) if status in {"rejected", "unresolved", "failed"} else (),
    )


def _manifest() -> IngestionExecutionManifest:
    artifact = _carrier_artifact()
    route = _route()
    routes = SegmentLanguageRouteSet.create(source_id="source-1", source_digest=_hash("source"), routes=(route,))
    outcomes = []
    for spec in CANONICAL_INGESTION_EXECUTION_GRAPH.stages:
        if "source" in spec.allowed_scopes:
            instance = IngestionStageInstanceRef(stage=spec.stage, scope="source")
            outcomes.append(_outcome(instance, status="not_started" if spec.stage == "source_summary_persistence" else "complete"))
        if "segment" in spec.allowed_scopes:
            outcomes.append(_outcome(IngestionStageInstanceRef(
                stage=spec.stage, scope="segment", segment_id=route.segment_id, segment_language_route_digest=route.route_digest,
            )))
    canonical_outcomes = tuple(sorted(outcomes, key=lambda outcome: encode_typed_value(outcome.model_dump(mode="python"))))
    return IngestionExecutionManifest.create(
        execution_graph_fingerprint=CANONICAL_INGESTION_EXECUTION_GRAPH.graph_fingerprint, segment_language_routes=routes,
        segment_governance_carriers=artifact.segment_governance, message_admission_carriers=artifact.message_admissions,
        governance_carrier_artifact=artifact, capability_bindings=(_binding(route_digest=route.route_digest),),
        source_outcomes=canonical_outcomes, graph_validation_attempts=(), transaction_group_outcomes=(), causal_blockers=(),
    )


def _preplanning_progress() -> PrePlanningSourceIngestionProgress:
    manifest = _manifest()

    def canonical_instances(instances: Iterable[IngestionStageInstanceRef]) -> tuple[IngestionStageInstanceRef, ...]:
        return tuple(sorted(
            instances, key=lambda instance: encode_typed_value(canonical_contract_value(instance))
        ))

    completed = canonical_instances(
        outcome.instance for outcome in manifest.source_outcomes if outcome.instance.scope == "source" and outcome.status == "complete"
    )
    eligible = canonical_instances(
        outcome.instance for outcome in manifest.source_outcomes if outcome.instance.scope == "source" and outcome.status == "not_started"
    )
    reusable = tuple(sorted(outcome.artifact_digest for outcome in manifest.source_outcomes if outcome.instance.scope == "source" and outcome.artifact_digest is not None))
    return PrePlanningSourceIngestionProgress.create(
        source_id="source-1", source_digest=_hash("source"), operation_id="operation-1", execution_manifest=manifest,
        completed_source_stage_instances=completed, next_eligible_source_stage_instances=eligible,
        replay_artifact_bundle_digest=_hash("bundle"), reusable_artifact_digests=reusable, retry_attempt_count=1,
        retry_reason_codes=(), operation_lease_binding=_lease(),
    )


def _planned_progress() -> PlannedSourceIngestionProgress:
    return PlannedSourceIngestionProgress.create(
        source_id="source-1", source_digest=_hash("source"), operation_id="operation-1",
        plan_lineage=SourceTransactionPlanLineageReference(lineage_id="lineage-1", lineage_digest=_hash("lineage"), repository_id="repo-1"),
        replay_artifact_bundle_digest=_hash("bundle"), terminal_group_result_digests=(_hash("terminal"),),
        unfinished_transaction_group_ids=("group-1",), latest_retryable_attempt_digests=(_hash("retry"),), operation_lease_binding=_lease(),
    )


def _binding(*, route_digest: str | None = None) -> OperationCapabilityExecutionBinding:
    return OperationCapabilityExecutionBinding.create(
        operation_id="operation-1",
        source_dependency_group_id="dependency-group-1",
        segment_id="segment-1",
        segment_language_route_digest=route_digest or _digest("a"),
        proposal_capability_fingerprint=_digest("b"),
        capability_fingerprint=_digest("c"),
        capability_selection_digest=_digest("d"),
        capability_registry_snapshot_digest=_digest("e"),
        capability_status_revision="status-revision-1",
        capability_status_record_digest=_digest("f"),
        monitoring_policy_digest=_digest("1"),
        evidence_freshness_digest=_digest("2"),
        nli_mode="disabled",
        verifier_manifest_digest=None,
        temporal_policy_snapshot_digest=_digest("3"),
        trust_policy_fingerprint=_digest("4"),
        trust_policy_snapshot_digest=_digest("5"),
        arbitration_as_of=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_execution_graph_is_closed_and_round_trips_exactly() -> None:
    graph = CANONICAL_INGESTION_EXECUTION_GRAPH
    assert graph == IngestionExecutionGraph.create()
    assert len(graph.stages) == 37
    assert graph.graph_fingerprint == "ce8987e5c7a703732148b69138703ae9715df73466c2fdfb32df9bb072fc253a"
    # This declarative vector is intentionally independent of the construction helper.
    assert tuple((spec.stage, spec.allowed_scopes) for spec in graph.stages[:4]) == (
        ("source_ingestion", frozenset(("source",))),
        ("source_governance", frozenset(("source",))),
        ("text_preparation", frozenset(("source",))),
        ("language_routing", frozenset(("segment",))),
    )
    assert decode_semantic_contract(encode_semantic_contract(graph), IngestionExecutionGraph) == graph


@pytest.mark.parametrize(
    "instance",
    [
        IngestionStageInstanceRef(stage="source_ingestion", scope="source"),
        IngestionStageInstanceRef(
            stage="language_routing", scope="segment", segment_id="segment-1", segment_language_route_digest=_digest("a")
        ),
        IngestionStageInstanceRef(stage="capability_selection", scope="source_plan_attempt", attempt_id="attempt-1"),
        IngestionStageInstanceRef(
            stage="graph_proposal_alignment", scope="transaction_group_attempt", transaction_group_id="group-1", attempt_id="attempt-2"
        ),
        IngestionStageInstanceRef(stage="graph_compilation", scope="transaction_group", transaction_group_id="group-1"),
    ],
)
def test_stage_instance_scope_algebra_accepts_exact_coordinates(instance: IngestionStageInstanceRef) -> None:
    assert instance == IngestionStageInstanceRef.model_validate(instance.model_dump(mode="python"))


@pytest.mark.parametrize(
    "values",
    [
        {"stage": "source_ingestion", "scope": "segment", "segment_id": "segment-1", "segment_language_route_digest": _digest("a")},
        {"stage": "language_routing", "scope": "segment", "segment_id": "segment-1"},
        {"stage": "graph_compilation", "scope": "transaction_group", "transaction_group_id": "group-1", "attempt_id": "attempt-1"},
    ],
)
def test_stage_instance_scope_algebra_rejects_mixed_coordinates(values: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        IngestionStageInstanceRef.model_validate(values)


def test_stage_outcome_and_capability_binding_are_strictly_coded() -> None:
    instance = IngestionStageInstanceRef(stage="source_ingestion", scope="source")
    outcome = IngestionStageOutcome(
        instance=instance,
        status="complete",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
        artifact_digest=_digest("a"),
    )
    assert decode_semantic_contract(encode_semantic_contract(outcome), IngestionStageOutcome) == outcome
    binding = _binding()
    encoded = encode_semantic_contract(binding)
    assert decode_semantic_contract(encoded, OperationCapabilityExecutionBinding) == binding

    envelope = decode_typed_value(encoded)
    assert isinstance(envelope, dict)
    payload = dict(envelope["payload"])
    payload["operation_id"] = ["operation-1"]
    with pytest.raises(SemanticContractCodecError):
        decode_semantic_contract(encode_typed_value({**envelope, "payload": payload}), OperationCapabilityExecutionBinding)


@pytest.mark.parametrize("field", ["stage", "scope", "status", "artifact_digest"])
def test_stage_outcome_codec_rejects_discriminator_and_coordinate_mutations(field: str) -> None:
    outcome = IngestionStageOutcome(
        instance=IngestionStageInstanceRef(stage="source_ingestion", scope="source"),
        status="complete",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
        artifact_digest=_digest("a"),
    )
    envelope = decode_typed_value(encode_semantic_contract(outcome))
    assert isinstance(envelope, dict)
    payload = dict(envelope["payload"])
    if field == "stage":
        instance = dict(payload["instance"])
        instance[field] = "unknown_stage"
        payload["instance"] = instance
    elif field == "scope":
        instance = dict(payload["instance"])
        instance[field] = "segment"
        payload["instance"] = instance
    elif field == "status":
        payload[field] = "future"
    else:
        payload[field] = "not-a-digest"
    with pytest.raises(SemanticContractCodecError):
        decode_semantic_contract(encode_typed_value({**envelope, "payload": payload}), IngestionStageOutcome)


def test_execution_manifest_and_progress_aggregates_round_trip_through_the_closed_codec() -> None:
    manifest = _manifest()
    preplanning = _preplanning_progress()
    planned = _planned_progress()

    for value, expected_type in (
        (manifest, IngestionExecutionManifest),
        (preplanning, PrePlanningSourceIngestionProgress),
        (planned, PlannedSourceIngestionProgress),
    ):
        assert decode_semantic_contract(encode_semantic_contract(value), expected_type) == value

    envelope = decode_typed_value(encode_semantic_contract(manifest))
    assert isinstance(envelope, dict)
    payload = dict(envelope["payload"])
    payload["execution_graph_fingerprint"] = [manifest.execution_graph_fingerprint]
    with pytest.raises(SemanticContractCodecError):
        decode_semantic_contract(encode_typed_value({**envelope, "payload": payload}), IngestionExecutionManifest)


def test_progress_factories_materialize_default_kind_in_digest_preimage() -> None:
    preplanning = _preplanning_progress()
    planned = _planned_progress()

    assert preplanning.kind == "pre_planning"
    assert planned.kind == "planned"
    assert PrePlanningSourceIngestionProgress.model_validate(preplanning.model_dump(mode="python")) == preplanning
    assert PlannedSourceIngestionProgress.model_validate(planned.model_dump(mode="python")) == planned
    assert decode_semantic_contract(
        encode_semantic_contract(preplanning), PrePlanningSourceIngestionProgress
    ) == preplanning
    assert decode_semantic_contract(
        encode_semantic_contract(planned), PlannedSourceIngestionProgress
    ) == planned


def test_execution_manifest_rejects_dependency_failure_and_wrong_blockers() -> None:
    manifest = _manifest()
    values = manifest.model_dump(mode="python", exclude={"manifest_digest"})
    failed_governance = _outcome(IngestionStageInstanceRef(stage="source_governance", scope="source"), status="failed")
    values["source_outcomes"] = tuple(sorted((
        failed_governance if outcome.instance == failed_governance.instance else outcome
        for outcome in manifest.source_outcomes
    ), key=lambda outcome: encode_typed_value(outcome.model_dump(mode="python"))))
    with pytest.raises(ValueError, match="unsatisfied required dependency"):
        IngestionExecutionManifest.create(**values)

    blocked_summary = _outcome(
        IngestionStageInstanceRef(stage="source_summary_persistence", scope="source"), status="not_started",
        blockers=(IngestionStageInstanceRef(stage="source_ingestion", scope="source"),),
    )
    values = manifest.model_dump(mode="python", exclude={"manifest_digest"})
    values["source_outcomes"] = tuple(sorted((
        blocked_summary if outcome.instance == blocked_summary.instance else outcome
        for outcome in manifest.source_outcomes
    ), key=lambda outcome: encode_typed_value(outcome.model_dump(mode="python"))))
    with pytest.raises(ValueError, match="blockers must exactly"):
        IngestionExecutionManifest.create(**values)


def test_preplanning_progress_rejects_coercion_lease_mismatch_and_derived_state_gaps() -> None:
    progress = _preplanning_progress()
    wire = progress.model_dump(mode="python")
    wire["retry_attempt_count"] = "1"
    with pytest.raises(ValueError):
        PrePlanningSourceIngestionProgress.model_validate(wire)

    values = progress.model_dump(mode="python", exclude={"progress_digest"})
    values["operation_lease_binding"] = _lease("operation-2")
    with pytest.raises(ValueError, match="lease mismatch"):
        PrePlanningSourceIngestionProgress.create(**values)

    values = progress.model_dump(mode="python", exclude={"progress_digest"})
    values["next_eligible_source_stage_instances"] = values["completed_source_stage_instances"][:1]
    with pytest.raises(ValueError, match="overlap"):
        PrePlanningSourceIngestionProgress.create(**values)

    values = progress.model_dump(mode="python", exclude={"progress_digest"})
    values["completed_source_stage_instances"] = values["completed_source_stage_instances"][:-1]
    with pytest.raises(ValueError, match="completed stages"):
        PrePlanningSourceIngestionProgress.create(**values)

    values = progress.model_dump(mode="python", exclude={"progress_digest"})
    values["reusable_artifact_digests"] = values["reusable_artifact_digests"][:-1]
    with pytest.raises(ValueError, match="reusable artifacts"):
        PrePlanningSourceIngestionProgress.create(**values)


def test_progress_discriminator_and_phase_fields_are_closed() -> None:
    preplanning = _preplanning_progress()
    planned = _planned_progress()
    preplanning_wire = preplanning.model_dump(mode="python")
    preplanning_wire["kind"] = "planned"
    with pytest.raises(ValueError):
        TypeAdapter(SourceIngestionProgress).validate_python(preplanning_wire)

    planned_wire = planned.model_dump(mode="python")
    planned_wire["kind"] = 1
    with pytest.raises(ValueError):
        TypeAdapter(SourceIngestionProgress).validate_python(planned_wire)

    preplanning_wire = preplanning.model_dump(mode="python")
    preplanning_wire["plan_lineage"] = planned.plan_lineage.model_dump(mode="python")
    with pytest.raises(ValueError):
        PrePlanningSourceIngestionProgress.model_validate(preplanning_wire)

    planned_wire = planned.model_dump(mode="python")
    planned_wire["execution_manifest"] = preplanning.execution_manifest.model_dump(mode="python")
    with pytest.raises(ValueError):
        PlannedSourceIngestionProgress.model_validate(planned_wire)


@pytest.mark.parametrize(
    ("progress", "expected_type", "cross_kind"),
    [
        (_preplanning_progress(), PrePlanningSourceIngestionProgress, "planned"),
        (_planned_progress(), PlannedSourceIngestionProgress, "pre_planning"),
    ],
)
def test_progress_rejects_cross_kind_and_digest_mutations(
    progress: PrePlanningSourceIngestionProgress | PlannedSourceIngestionProgress,
    expected_type: type[PrePlanningSourceIngestionProgress] | type[PlannedSourceIngestionProgress],
    cross_kind: str,
) -> None:
    cross_kind_values = progress.model_dump(mode="python")
    cross_kind_values["kind"] = cross_kind
    with pytest.raises(ValueError):
        expected_type.model_validate(cross_kind_values)

    digest_values = progress.model_dump(mode="python")
    digest_values["progress_digest"] = "0" * 64
    with pytest.raises(ValueError, match="digest mismatch"):
        expected_type.model_validate(digest_values)
