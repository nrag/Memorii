"""Assembly and publication of one graph-free source-normalization closure."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from pydantic import BaseModel

from memorii.core.memory_evolution.atomic_store import (
    AtomicGenerationMember,
    OperationLeaseBinding,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    OperationFenceBinding,
    SemanticWriterCommitBinding,
    encode_typed_value,
)
from memorii.core.semantic_ingestion.contracts import (
    BootstrapAnalysisLaneResultV3,
    BootstrapDeclaredSegmentLanguageRoute,
    BootstrapGraphFreeIdentityPlanningInputV3,
    BootstrapGraphFreeInterpretationBundleV3,
    BootstrapGraphNormalizationAuthorityMemberV3,
    BootstrapNativeOperationReductionInputV3,
    BootstrapNormalizationRequestCoreV3,
    BootstrapOperationCoverageBindingV3,
    BootstrapProposalRunPayloadV3,
    BootstrapRecoveryClaimV3,
    BootstrapRecoveryKeyV3,
    BootstrapSemanticProposalRunV3,
    BootstrapSemanticReductionAuthorityMemberV3,
    BootstrapSourceNormalizationAtomicWriteRequestV3,
    BootstrapSourceNormalizationEvidenceManifestV3,
    BootstrapSourceNormalizationRequestV3,
    BootstrapSourceNormalizationResultV3,
    BootstrapSourceProposalAlignmentV3,
    BootstrapV3PayloadLimitAuthority,
    PreparedSource,
    canonical_contract_value,
    contract_digest,
    encode_semantic_contract,
)
from memorii.core.semantic_ingestion.source_normalization_authority import (
    CapabilityRegistrySnapshot,
    GraphDependentExecutionPolicy,
)
from memorii.core.semantic_ingestion.source_normalization_repository import SourceNormalizationStage


def _native_reduction_inputs(
    *, core: BootstrapNormalizationRequestCoreV3, operation_fence_binding: OperationFenceBinding,
) -> tuple[BootstrapNativeOperationReductionInputV3, ...]:
    """Project V3-native operation inputs from the sealed normalization core."""
    payload = core.proposal_payload
    alignment = core.source_alignment
    subjects = {
        item.operation_id: item
        for subject_set in core.interpretation_bundle.subject_sets
        for item in subject_set.subjects
    }
    parser = {item.operation_id: item for item in alignment.parser_consensus}
    scope = {item.operation_id: item for item in alignment.scope_consensus}
    temporal = {item.operation_id: item for item in alignment.temporal_attachment_consensus_sets}
    alignments = {item.operation_id: item for item in alignment.operation_alignments}
    groups = {
        operation_id: group
        for group in alignment.source_dependency_groups
        if group.status == "complete"
        for operation_id in group.operation_ids
    }
    proposals = {item.proposal_digest: item for item in payload.normalized_proposals}
    lane_by_segment = {
        item.segment_id: tuple(row for row in core.lane_results if row.segment_id == item.segment_id)
        for item in payload.bootstrap_analysis_provenances
    }
    inputs: list[BootstrapNativeOperationReductionInputV3] = []
    for group in alignment.source_dependency_groups:
        if group.status != "complete":
            continue
        for operation_id in group.operation_ids:
            subject = subjects[operation_id]
            proposal = proposals[subject.proposal_digest]
            member = next(
                item for item in proposal.operation_members
                if _operation_member_digest(item) == subject.member_digest
            )
            operation_alignment = alignments[operation_id]
            execution_id = contract_digest(
                b"memorii.bootstrap-graph.operation-execution-id.v3",
                {
                    "source_id": core.recovery_key.source_id,
                    "source_digest": core.recovery_key.source_digest,
                    "preparation_fingerprint": core.recovery_key.preparation_fingerprint,
                    "operation_id": operation_id,
                    "proposal_digest": subject.proposal_digest,
                    "member_digest": subject.member_digest,
                    "segment_id": subject.segment_id,
                    "provenance_digest": subject.bootstrap_analysis_provenance.provenance_digest,
                    "dependency_group_id": group.group_id,
                },
            )
            bindings = tuple(
                BootstrapOperationCoverageBindingV3.create(
                    operation_execution_id=execution_id,
                    operation_id=operation_id,
                    predicate_event_id=disposition.event_id,
                    proposal_digest=subject.proposal_digest,
                    member_digest=subject.member_digest,
                    bootstrap_analysis_provenance=subject.bootstrap_analysis_provenance,
                    operation_alignment_digest=operation_alignment.alignment_digest,
                    disposition=disposition,
                )
                for disposition in alignment.proposal_coverage.dispositions
                if (
                    operation_id in disposition.operation_ids
                    if disposition.kind == "covered"
                    else subject.proposal_digest in disposition.related_proposal_digests
                )
            )
            identity_input = None
            if member.kind == "identity":
                identity_input = BootstrapGraphFreeIdentityPlanningInputV3.create(
                    source_id=core.recovery_key.source_id,
                    source_digest=core.recovery_key.source_digest,
                    preparation_fingerprint=core.recovery_key.preparation_fingerprint,
                    operation_id=operation_id,
                    proposal_digest=subject.proposal_digest,
                    identity_member=member,
                    operation_subject=subject,
                    bootstrap_analysis_provenance=subject.bootstrap_analysis_provenance,
                    identity_partition_evidence=core.interpretation_bundle.identity_partition_evidence,
                    source_local_identity=alignment.source_local_identity,
                    operation_alignment=operation_alignment,
                    dependency_group_id=group.group_id,
                    operation_fence_binding_digest=operation_fence_binding.binding_digest,
                )
            inputs.append(BootstrapNativeOperationReductionInputV3.create(
                source_id=core.recovery_key.source_id,
                source_digest=core.recovery_key.source_digest,
                preparation_fingerprint=core.recovery_key.preparation_fingerprint,
                operation_id=operation_id,
                normalized_proposal=proposal,
                operation_member=member,
                operation_subject=subject,
                lane_results=lane_by_segment[subject.segment_id],
                parser_consensus=parser[operation_id],
                scope_consensus=scope[operation_id],
                temporal_consensus_set=temporal[operation_id],
                operation_alignment=operation_alignment,
                identity_partition_evidence=core.interpretation_bundle.identity_partition_evidence,
                source_local_identity=alignment.source_local_identity,
                dependency_group=groups[operation_id],
                operation_execution_id=execution_id,
                coverage_bindings=bindings,
                graph_free_identity_input=identity_input,
            ))
    return tuple(sorted(inputs, key=lambda item: (item.dependency_group.group_id, item.operation_id)))


def _operation_member_digest(member: object) -> str:
    for name in type(member).model_fields:
        if name.endswith("_digest") and name not in {"logical_action_digest", "execution_branch_digest"}:
            value = getattr(member, name)
            if isinstance(value, str):
                return value
    raise ValueError("bootstrap operation member has no native digest")


@dataclass(frozen=True)
class BootstrapV3SourceNormalizationInputs:
    """The standalone V3 publication closure, with no generic V2 members."""

    proposal_payload: BootstrapProposalRunPayloadV3
    lane_results: tuple[BootstrapAnalysisLaneResultV3, ...]
    interpretation_bundle: BootstrapGraphFreeInterpretationBundleV3
    source_alignment: BootstrapSourceProposalAlignmentV3
    payload_limit_authority: BootstrapV3PayloadLimitAuthority
    capability_registry: CapabilityRegistrySnapshot
    graph_dependent_execution_policy: GraphDependentExecutionPolicy
    bootstrap_recovery_key: BootstrapRecoveryKeyV3
    bootstrap_recovery_claim: BootstrapRecoveryClaimV3
    operation_fence_binding: OperationFenceBinding
    operation_lease_binding: OperationLeaseBinding
    writer_commit_binding: SemanticWriterCommitBinding
    expected_operation_generation: int
    expected_artifact_generation: int


@dataclass(frozen=True)
class GraphFreeSourceNormalizationInvocation:
    """Provider-owned inputs available before graph or terminal work.

    The invocation is intentionally narrower than the sealed write inputs.  A
    producer must supply the remaining graph-free analysis authorities through
    ``GraphFreeSourceNormalizationInputsProvider``; the provider coordinator
    cannot reconstruct them from a terminal-shaped result.
    """

    operation_id: str
    source: PreparedSource
    source_authority_evidence: BaseModel
    source_interval_evidence: BaseModel | None
    policy_bundle: BaseModel
    authorization_read_set_provider: object
    operation_fence_binding: OperationFenceBinding


def validate_reloaded_bootstrap_v3_source_normalization_result(
    *, result: object, source: PreparedSource
) -> BootstrapSourceNormalizationResultV3 | None:
    """Accept only the exact native V3 closure for this prepared source."""
    if type(result) is not BootstrapSourceNormalizationResultV3:
        return None
    try:
        validated = BootstrapSourceNormalizationResultV3.model_validate(
            result.model_dump(mode="python")
        )
    except (AttributeError, TypeError, ValueError):
        return None
    expected_segments = {
        (route.segment_id, route.route_digest)
        for route in source.segment_language_routes.routes
        if isinstance(route, BootstrapDeclaredSegmentLanguageRoute)
    }
    actual_segments = {
        (item.segment_id, item.bootstrap_route_digest)
        for item in validated.bootstrap_analysis_provenance
        if (
            item.source_id,
            item.source_digest,
            item.preparation_fingerprint,
        )
        == (source.source_id, source.source_digest, source.preparation_fingerprint)
    }
    if (
        validated != result
        or not expected_segments
        or actual_segments != expected_segments
        or len(actual_segments) != len(validated.bootstrap_analysis_provenance)
    ):
        return None
    return validated


class BootstrapV3SourceNormalizationStage:
    """Publish the V3 closure without translating it through V2 contracts."""

    def __init__(self, *, publisher: SourceNormalizationStage) -> None:
        self._publisher = publisher

    def normalize(self, inputs: BootstrapV3SourceNormalizationInputs) -> BootstrapSourceNormalizationResultV3:
        request = self.build_request(inputs)
        result = self._publisher.normalize(request)
        if type(result) is not BootstrapSourceNormalizationResultV3:
            raise ValueError("bootstrap V3 publisher returned a foreign result")
        return result

    @staticmethod
    def build_request(inputs: BootstrapV3SourceNormalizationInputs) -> BootstrapSourceNormalizationAtomicWriteRequestV3:
        authority = inputs.payload_limit_authority
        payload = inputs.proposal_payload
        provenance = payload.bootstrap_analysis_provenances
        lane_order = ("stanza", "spacy", "predicate_event_detection", "temporal_resolution")
        if (
            not provenance
            or payload.payload_limit_authority_digest != authority.authority_digest
            or inputs.interpretation_bundle.proposal_payload_digest != payload.payload_digest
            or inputs.source_alignment.interpretation_bundle_digest != inputs.interpretation_bundle.bundle_digest
            or tuple((row.segment_id, row.lane) for row in inputs.lane_results)
            != tuple((item.segment_id, lane) for item in provenance for lane in lane_order)
        ):
            raise ValueError("bootstrap V3 stage input closure is incomplete")
        # This is the only graph-free preimage shared by both downstream
        # authorities.  It is formed before either authority exists so replay
        # can authenticate retained source bytes without reconstructing them.
        core = BootstrapNormalizationRequestCoreV3.create(
            proposal_payload=payload,
            lane_results=inputs.lane_results,
            interpretation_bundle=inputs.interpretation_bundle,
            source_alignment=inputs.source_alignment,
            payload_limit_authority=authority,
            recovery_key=inputs.bootstrap_recovery_key,
        )
        proposal_run = BootstrapSemanticProposalRunV3.create(
            schema_version=3, source_id=payload.source_id, source_digest=payload.source_digest,
            preparation_fingerprint=payload.preparation_fingerprint, proposal_payload=payload,
            bootstrap_analysis_provenance=provenance,
        )
        normalization_request = BootstrapSourceNormalizationRequestV3.create(
            schema_version=3, source_id=payload.source_id, source_digest=payload.source_digest,
            preparation_fingerprint=payload.preparation_fingerprint, proposal_run=proposal_run,
            lane_results=inputs.lane_results, interpretation_bundle=inputs.interpretation_bundle,
            source_alignment=inputs.source_alignment, bootstrap_analysis_provenance=provenance,
            payload_limit_authority=authority,
        )
        manifest = BootstrapSourceNormalizationEvidenceManifestV3.create(
            schema_version=3, source_normalization_request_digest=normalization_request.request_digest,
            interpretation_bundle_digest=inputs.interpretation_bundle.bundle_digest,
            source_alignment_digest=inputs.source_alignment.alignment_digest,
            bootstrap_analysis_provenance=provenance,
            lane_result_digests=tuple(sorted(row.result_digest for row in inputs.lane_results)),
            payload_limit_policy_digest=authority.policy.policy_digest,
            payload_limit_authority_digest=authority.authority_digest,
        )
        result = BootstrapSourceNormalizationResultV3.create(
            schema_version=3, source_normalization_request_digest=normalization_request.request_digest,
            evidence_manifest=manifest, interpretation_bundle_digest=inputs.interpretation_bundle.bundle_digest,
            source_alignment_digest=inputs.source_alignment.alignment_digest,
            bootstrap_analysis_provenance=provenance,
            payload_limit_policy_digest=authority.policy.policy_digest,
            payload_limit_authority_digest=authority.authority_digest,
        )
        normalization_authority = BootstrapGraphNormalizationAuthorityMemberV3.create(
            recovery_key_digest=inputs.bootstrap_recovery_key.recovery_key_digest,
            normalization_request_digest=normalization_request.request_digest,
            normalization_result_digest=result.result_digest,
            execution_policy=inputs.graph_dependent_execution_policy,
            execution_policy_canonical_bytes=encode_typed_value(
                canonical_contract_value(inputs.graph_dependent_execution_policy)
            ),
            capability_registry=inputs.capability_registry,
            capability_registry_canonical_bytes=encode_typed_value(
                canonical_contract_value(inputs.capability_registry)
            ),
        )
        semantic_reduction_authority = BootstrapSemanticReductionAuthorityMemberV3.create(
            normalization_request_core=core,
            normalization_request_core_canonical_bytes=encode_typed_value(
                canonical_contract_value(core)
            ),
            operation_inputs=_native_reduction_inputs(
                core=core, operation_fence_binding=inputs.operation_fence_binding,
            ),
            execution_policy=inputs.graph_dependent_execution_policy,
            execution_policy_canonical_bytes=encode_typed_value(
                canonical_contract_value(inputs.graph_dependent_execution_policy)
            ),
            capability_registry=inputs.capability_registry,
            capability_registry_canonical_bytes=encode_typed_value(
                canonical_contract_value(inputs.capability_registry)
            ),
        )
        artifacts: tuple[tuple[str, object], ...] = (
            ("bootstrap_proposal_run_payload", payload),
            *(("bootstrap_analysis_lane_result", row) for row in inputs.lane_results),
            *(("bootstrap_pre_alignment_operation_subject_set", row) for row in inputs.interpretation_bundle.subject_sets),
            *(("bootstrap_analyzer_scope_observation", row) for row in inputs.interpretation_bundle.scope_observations),
            *(("bootstrap_analyzer_temporal_attachment_observation", row) for row in inputs.interpretation_bundle.temporal_attachment_observations),
            *(("bootstrap_parser_consensus_assessment", row) for row in inputs.source_alignment.parser_consensus),
            *(("bootstrap_semantic_scope_consensus", row) for row in inputs.source_alignment.scope_consensus),
            *(("bootstrap_temporal_attachment_consensus", row) for row in inputs.source_alignment.temporal_attachment_consensus),
            *(("bootstrap_operation_temporal_attachment_consensus_set", row) for row in inputs.source_alignment.temporal_attachment_consensus_sets),
            ("bootstrap_source_local_identity_partition_evidence", inputs.interpretation_bundle.identity_partition_evidence),
            ("bootstrap_source_local_identity_resolution", inputs.source_alignment.source_local_identity),
            ("bootstrap_proposal_coverage_audit", inputs.source_alignment.proposal_coverage),
            *(("bootstrap_operation_alignment", row) for row in inputs.source_alignment.operation_alignments),
            *(("bootstrap_source_dependency_group", row) for row in inputs.source_alignment.source_dependency_groups),
            ("bootstrap_graph_free_interpretation_bundle", inputs.interpretation_bundle),
            ("bootstrap_source_proposal_alignment", inputs.source_alignment),
            # Recovery reuses this sealed native result; it must never derive
            # a replacement from the retained lane payloads after a lost ack.
            ("bootstrap_source_normalization_request", normalization_request),
            ("bootstrap_source_normalization_evidence_manifest", manifest),
            ("bootstrap_source_normalization_result", result),
            ("bootstrap_normalization_request_core", core),
            ("bootstrap_semantic_reduction_authority", semantic_reduction_authority),
            ("bootstrap_graph_normalization_authority", normalization_authority),
        )
        members = tuple(
            AtomicGenerationMember(
                member_id=f"{index:02d}-{kind}",
                kind=kind,
                canonical_payload=encode_semantic_contract(value),
                payload_digest=sha256(encode_semantic_contract(value)).hexdigest(),
            )
            for index, (kind, value) in enumerate(artifacts)
        )
        base = {
            "schema_version": 3, "kind": "bootstrap_source_normalization_checkpoint", "progress_state": "preplanning",
            "publication_generation": inputs.expected_artifact_generation + 1,
            "operation_fence_binding": inputs.operation_fence_binding, "operation_lease_binding": inputs.operation_lease_binding,
            "writer_commit_binding": inputs.writer_commit_binding, "expected_operation_generation": inputs.expected_operation_generation,
            "expected_artifact_generation": inputs.expected_artifact_generation, "members": members,
            "required_artifact_digests": tuple(row.payload_digest for row in members),
            "source_normalization_request": normalization_request, "source_normalization_result": result,
            "evidence_manifest": manifest, "bootstrap_v3_payload_limit_authority": authority,
            "normalization_request_core": core,
            "semantic_reduction_authority": semantic_reduction_authority,
            "bootstrap_graph_normalization_authority": normalization_authority,
            "bootstrap_proposal_run_payload": payload, "bootstrap_analysis_lane_results": inputs.lane_results,
            "bootstrap_recovery_key": inputs.bootstrap_recovery_key, "bootstrap_recovery_claim": inputs.bootstrap_recovery_claim,
        }
        return BootstrapSourceNormalizationAtomicWriteRequestV3.model_validate(
            base | {
                "request_digest": sha256(
                    encode_typed_value(canonical_contract_value(base))
                ).hexdigest()
            }
        )


__all__ = [
    "BootstrapV3SourceNormalizationInputs",
    "BootstrapV3SourceNormalizationStage",
    "GraphFreeSourceNormalizationInvocation",
    "validate_reloaded_bootstrap_v3_source_normalization_result",
]
