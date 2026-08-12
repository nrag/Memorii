"""Assembly and publication of one graph-free source-normalization closure."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Protocol

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
from memorii.core.memory_evolution.semantic_analysis.decision_contracts import SourceNormalizationPublicationCoordinate
from memorii.core.semantic_ingestion.contracts import (
    BootstrapAnalysisLaneResultV3,
    BootstrapAnalysisProvenanceV1,
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
    ConsensusPolicySelectionBundle,
    GraphFreeInterpretationBundle,
    LanguageConstructionPolicyAuthorityBundle,
    LinguisticAnalysisBundle,
    ParserConsensusAssessment,
    PredicateEventInventory,
    PreparedSource,
    PrePlanningSourceIngestionProgress,
    SemanticProposalRun,
    SourceNormalizationAtomicWriteRequest,
    SourceNormalizationEvidenceEntry,
    SourceNormalizationEvidenceManifest,
    SourceNormalizationRequest,
    SourceNormalizationResult,
    TemporalPolicySnapshot,
    TemporalResolution,
    TrustPolicySnapshot,
    canonical_contract_value,
    contract_digest,
    encode_semantic_contract,
)
from memorii.core.semantic_ingestion.source_alignment import build_source_proposal_alignment
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
class GraphFreeSourceNormalizationInputs:
    """All authority required to form a sealed source-normalization write.

    This deliberately accepts no provider, graph, terminal, or configuration
    owner.  Those objects cannot be recovered or looked up while assembling
    the graph-free closure.
    """

    source: PreparedSource
    proposal_run: SemanticProposalRun
    analyses: LinguisticAnalysisBundle
    interpretation_bundle: GraphFreeInterpretationBundle
    predicate_events: PredicateEventInventory
    temporal_resolution: TemporalResolution
    consensus_policy_selections: ConsensusPolicySelectionBundle
    language_construction_policies: LanguageConstructionPolicyAuthorityBundle
    publication_coordinate: SourceNormalizationPublicationCoordinate
    temporal_policy: TemporalPolicySnapshot
    trust_policy: TrustPolicySnapshot
    arbitration_as_of: datetime
    capability_registry: CapabilityRegistrySnapshot
    parser_consensus: tuple[ParserConsensusAssessment, ...]
    evidence_entries: tuple[SourceNormalizationEvidenceEntry, ...]
    capability_selections: tuple[CapabilityRegistrySnapshot, ...]
    graph_dependent_execution_policy: GraphDependentExecutionPolicy
    graph_dependent_execution_policy_digest: str
    progress: PrePlanningSourceIngestionProgress
    operation_fence_binding: OperationFenceBinding
    operation_lease_binding: OperationLeaseBinding
    writer_commit_binding: SemanticWriterCommitBinding
    expected_operation_generation: int
    expected_artifact_generation: int
    bootstrap_analysis_provenance: tuple[BootstrapAnalysisProvenanceV1, ...] = ()
    bootstrap_recovery_key: BootstrapRecoveryKeyV3 | None = None
    bootstrap_recovery_claim: BootstrapRecoveryClaimV3 | None = None


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


def validate_reloaded_source_normalization_result(
    *,
    result: object,
    source: PreparedSource,
    operation_fence_binding: OperationFenceBinding,
    publication_coordinate: object,
) -> SourceNormalizationResult | None:
    """Accept only the exact typed closure reloaded for this source publication."""
    if (
        type(result) is not SourceNormalizationResult
        or type(publication_coordinate) is not SourceNormalizationPublicationCoordinate
    ):
        return None
    try:
        validated = SourceNormalizationResult.model_validate(
            result.model_dump(mode="python")
        )
    except (AttributeError, TypeError, ValueError):
        return None
    coordinate = validated.evidence_manifest.publication_coordinate
    alignment = validated.source_alignment
    if (
        type(coordinate) is not SourceNormalizationPublicationCoordinate
        or validated != result
        or coordinate != publication_coordinate
        or coordinate.operation_fence_binding != operation_fence_binding
        or coordinate.preparation_fingerprint != source.preparation_fingerprint
        or alignment.source_id != source.source_id
        or alignment.segment_language_routes != source.segment_language_routes
        or validated.evidence_manifest.source_id != source.source_id
        or validated.evidence_manifest.source_digest != source.source_digest
    ):
        return None
    return validated


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


class GraphFreeSourceNormalizationInputsProvider(Protocol):
    """Host-owned producer for one complete graph-free authority closure."""

    def build_inputs(
        self,
        invocation: GraphFreeSourceNormalizationInvocation,
    ) -> GraphFreeSourceNormalizationInputs | None: ...


class GraphFreeSourceNormalizationStage:
    """Build the only source-normalization atomic request and publish it once."""

    def __init__(self, *, publisher: SourceNormalizationStage) -> None:
        self._publisher = publisher

    def normalize(self, inputs: GraphFreeSourceNormalizationInputs) -> SourceNormalizationResult:
        request = self.build_request(inputs)
        return self._publisher.normalize(request)


    @staticmethod
    def build_request(inputs: GraphFreeSourceNormalizationInputs) -> SourceNormalizationAtomicWriteRequest:
        GraphFreeSourceNormalizationStage._validate_inputs(inputs)
        alignment = build_source_proposal_alignment(
            bundle=inputs.interpretation_bundle,
            parser_consensus=inputs.parser_consensus,
            segment_language_routes=inputs.source.segment_language_routes,
            predicate_event_ids=tuple(item.event_id for item in inputs.predicate_events.candidates),
            predicate_event_inventory_fingerprint=inputs.predicate_events.inventory_fingerprint,
            coverage_policy_fingerprint=inputs.consensus_policy_selections.bundle_digest,
            temporal_candidates=inputs.temporal_resolution.candidates,
        )
        if alignment is None:
            raise ValueError("source normalization alignment authority is unavailable")
        request = GraphFreeSourceNormalizationStage._normalization_request(inputs)
        manifest = GraphFreeSourceNormalizationStage._manifest(inputs, request)
        result = SourceNormalizationResult.create(
            schema_version=2,
            source_alignment=alignment,
            evidence_manifest=manifest,
            interpretation_bundle_digest=inputs.interpretation_bundle.bundle_digest,
            identity_partition_evidence_digest=inputs.interpretation_bundle.identity_partition_evidence.evidence_digest,
            capability_selections=inputs.capability_selections,
            trust_policy_snapshot_digest=GraphFreeSourceNormalizationStage._digest_field(inputs.trust_policy, "snapshot_digest"),
            arbitration_as_of=inputs.arbitration_as_of,
        )
        artifacts = (
            ("progress", inputs.progress),
            ("source_normalization_request", request),
            *(
                (("bootstrap_analysis_provenance", inputs.bootstrap_analysis_provenance),)
                if inputs.bootstrap_recovery_key is not None
                else ()
            ),
            ("graph_free_interpretation_bundle", inputs.interpretation_bundle),
            ("source_local_identity_partition_evidence", inputs.interpretation_bundle.identity_partition_evidence),
            *(("parser_consensus", row) for row in alignment.parser_consensus),
            *(("semantic_scope_consensus", row) for row in alignment.scope_consensus),
            *(("temporal_attachment_consensus", row) for row in alignment.temporal_attachment_consensus),
            ("source_local_identity_resolution", alignment.source_local_identity),
            ("source_proposal_alignment", alignment),
            ("source_dependency_groups", alignment.source_dependency_groups),
            ("source_normalization_result", result),
            ("source_normalization_evidence_manifest", manifest),
            ("graph_dependent_execution_policy", inputs.graph_dependent_execution_policy),
            ("consensus_policy_selection_bundle", inputs.consensus_policy_selections),
            ("language_construction_policy_bundle", inputs.language_construction_policies),
        )
        members = tuple(
            GraphFreeSourceNormalizationStage._member(index, kind, value)
            for index, (kind, value) in enumerate(artifacts)
        )
        # The request digest covers the complete request itself, so form the
        # canonical preimage before attaching its derived digest.
        request_type = (
            BootstrapSourceNormalizationAtomicWriteRequestV3
            if inputs.bootstrap_recovery_key is not None
            else SourceNormalizationAtomicWriteRequest
        )
        base = {
            "schema_version": 3 if request_type is BootstrapSourceNormalizationAtomicWriteRequestV3 else 2,
            "kind": "source_normalization_checkpoint",
            "progress_state": "preplanning",
            "publication_generation": inputs.expected_artifact_generation + 1,
            "operation_fence_binding": inputs.operation_fence_binding,
            "operation_lease_binding": inputs.operation_lease_binding,
            "writer_commit_binding": inputs.writer_commit_binding,
            "expected_operation_generation": inputs.expected_operation_generation,
            "expected_artifact_generation": inputs.expected_artifact_generation,
            "members": members,
            "required_artifact_digests": tuple(member.payload_digest for member in members),
            "source_normalization_request": request,
            "source_normalization_request_digest": request.request_digest,
            "source_normalization_result": result,
            "source_normalization_result_digest": result.result_digest,
            "evidence_manifest": manifest,
            "evidence_manifest_digest": manifest.manifest_digest,
            "graph_dependent_execution_policy": inputs.graph_dependent_execution_policy,
            "graph_dependent_execution_policy_digest": inputs.graph_dependent_execution_policy_digest,
            "consensus_policy_selection_bundle": inputs.consensus_policy_selections,
            "consensus_policy_selection_bundle_digest": inputs.consensus_policy_selections.bundle_digest,
            "language_construction_policy_bundle": inputs.language_construction_policies,
            "language_construction_policy_bundle_digest": inputs.language_construction_policies.bundle_digest,
            **(
                {
                    "bootstrap_analysis_provenance": inputs.bootstrap_analysis_provenance,
                    "bootstrap_recovery_key": inputs.bootstrap_recovery_key,
                    "bootstrap_recovery_claim": inputs.bootstrap_recovery_claim,
                }
                if request_type is BootstrapSourceNormalizationAtomicWriteRequestV3
                else {}
            ),
        }
        # ``request_digest`` is derived from the wire preimage, so do not use
        # Pydantic's unchecked construction escape hatch to manufacture it.
        return request_type.model_validate(
            base | {
                "request_digest": sha256(
                    encode_typed_value(base)
                ).hexdigest()
            }
        )

    @staticmethod
    def _validate_inputs(inputs: GraphFreeSourceNormalizationInputs) -> None:
        source = inputs.source
        bundle = inputs.interpretation_bundle
        if (
            inputs.proposal_run.status != "complete"
            or inputs.analyses.status != "complete"
            or inputs.predicate_events.status != "complete"
            or inputs.temporal_resolution.status != "complete"
            or (bundle.source_id, bundle.source_digest, bundle.preparation_fingerprint)
            != (source.source_id, source.source_digest, source.preparation_fingerprint)
            or (inputs.proposal_run.source_id, inputs.proposal_run.source_digest, inputs.proposal_run.preparation_fingerprint)
            != (source.source_id, source.source_digest, source.preparation_fingerprint)
            or inputs.proposal_run.run_fingerprint != bundle.proposal_run_fingerprint
            or inputs.analyses.bundle_fingerprint != bundle.analysis_bundle_fingerprint
            or inputs.temporal_resolution.resolver_fingerprint != bundle.temporal_resolution_fingerprint
            or inputs.operation_fence_binding != getattr(inputs.publication_coordinate, "operation_fence_binding", None)
            or inputs.expected_artifact_generation != getattr(inputs.publication_coordinate, "expected_current_artifact_generation", None)
            or inputs.operation_lease_binding.operation_fence_binding != inputs.operation_fence_binding
            or inputs.progress.operation_lease_binding != inputs.operation_lease_binding
            or inputs.graph_dependent_execution_policy_digest != GraphFreeSourceNormalizationStage._digest_field(inputs.graph_dependent_execution_policy, "policy_digest")
        ):
            raise ValueError("source normalization inputs do not form one sealed authority chain")
        if not inputs.parser_consensus or len({row.assessment_digest for row in inputs.parser_consensus}) != len(inputs.parser_consensus):
            raise ValueError("source normalization parser consensus is incomplete")
        v3_values = (
            inputs.bootstrap_analysis_provenance,
            inputs.bootstrap_recovery_key,
            inputs.bootstrap_recovery_claim,
        )
        if any(value is not None and value != () for value in v3_values) and not (
            inputs.bootstrap_analysis_provenance
            and inputs.bootstrap_recovery_key is not None
            and inputs.bootstrap_recovery_claim is not None
        ):
            raise ValueError("bootstrap V3 source-normalization authority is incomplete")
        GraphFreeSourceNormalizationStage._validate_selection_closure(inputs)

    @staticmethod
    def _validate_selection_closure(inputs: GraphFreeSourceNormalizationInputs) -> None:
        """Require one selection for every parser, scope, and temporal role."""
        required_roles = {
            "fact": ("assertion",),
            "action_state": ("assertion",),
            "correction": ("replacement", "transition"),
            "retraction": ("transition",),
            "identity": ("transition",),
        }
        expected = set()
        for subject_set in inputs.interpretation_bundle.subject_sets:
            for subject in subject_set.subjects:
                coordinate = (
                    subject.operation_id,
                    subject.proposal_id,
                    subject.segment_id,
                    subject.segment_language_route_digest,
                )
                expected.update((("parser", *coordinate, None), ("scope", *coordinate, None)))
                expected.update(
                    ("temporal_attachment", *coordinate, role)
                    for role in required_roles[subject.kind]
                )
        selection_keys = tuple(
            (
                selection.kind,
                selection.operation_id,
                selection.proposal_id,
                selection.segment_id,
                selection.segment_language_route_digest,
                selection.temporal_role,
            )
            for selection in inputs.consensus_policy_selections.selections
        )
        if selection_keys != tuple(
            sorted(
                selection_keys,
                key=lambda key: (*key[:-1], key[-1] or ""),
            )
        ) or set(selection_keys) != expected:
            raise ValueError("source normalization consensus policy selections are not role-complete")

    @staticmethod
    def _normalization_request(inputs: GraphFreeSourceNormalizationInputs) -> SourceNormalizationRequest:
        values = dict(
            schema_version=2, source=inputs.source, proposal_run=inputs.proposal_run,
            analyses=inputs.analyses, interpretation_bundle=inputs.interpretation_bundle,
            predicate_events=inputs.predicate_events, temporal_resolution=inputs.temporal_resolution,
            consensus_policy_selections=inputs.consensus_policy_selections,
            language_construction_policies=inputs.language_construction_policies,
            publication_coordinate=inputs.publication_coordinate, temporal_policy=inputs.temporal_policy,
            trust_policy=inputs.trust_policy, arbitration_as_of=inputs.arbitration_as_of,
            capability_registry=inputs.capability_registry,
        )
        return SourceNormalizationRequest.create(**values)

    @staticmethod
    def _manifest(inputs: GraphFreeSourceNormalizationInputs, request: SourceNormalizationRequest) -> SourceNormalizationEvidenceManifest:
        entries = tuple(sorted(inputs.evidence_entries, key=lambda entry: entry.entry_digest))
        expected = {
            *( ("parser", row.operation_id, None, row.assessment_digest) for row in inputs.parser_consensus),
        }
        actual = {(entry.kind, entry.operation_id, entry.temporal_role, entry.artifact_digest) for entry in entries}
        if not expected <= actual:
            raise ValueError("source normalization evidence entries omit parser consensus")
        values = dict(
            schema_version=2, source_id=inputs.source.source_id, source_digest=inputs.source.source_digest,
            source_normalization_request_digest=request.request_digest,
            consensus_policy_selection_bundle_digest=inputs.consensus_policy_selections.bundle_digest,
            language_construction_policy_bundle_digest=inputs.language_construction_policies.bundle_digest,
            interpretation_bundle_digest=inputs.interpretation_bundle.bundle_digest,
            identity_partition_evidence_digest=inputs.interpretation_bundle.identity_partition_evidence.evidence_digest,
            publication_coordinate=inputs.publication_coordinate, retained_entries=entries,
            completeness="complete", bijection_verified=True,
        )
        return SourceNormalizationEvidenceManifest.create(**values)

    @staticmethod
    def _member(index: int, kind: str, value: object) -> AtomicGenerationMember:
        if isinstance(value, tuple):
            payload = encode_typed_value(tuple(item.model_dump(mode="python") for item in value))
        elif isinstance(value, BaseModel):
            try:
                payload = encode_semantic_contract(value)
            except ValueError:
                payload = encode_typed_value(value.model_dump(mode="python"))
        else:
            raise ValueError("source normalization member is not typed")
        return AtomicGenerationMember(member_id=f"{index:02d}-{kind}", kind=kind, canonical_payload=payload, payload_digest=sha256(payload).hexdigest())

    @staticmethod
    def _digest_field(value: BaseModel, field: str) -> str:
        digest = getattr(value, field, None)
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"source normalization authority lacks {field}")
        return digest


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
                inputs.graph_dependent_execution_policy.model_dump(mode="python")
            ),
            capability_registry=inputs.capability_registry,
            capability_registry_canonical_bytes=encode_typed_value(
                inputs.capability_registry.model_dump(mode="python")
            ),
        )
        semantic_reduction_authority = BootstrapSemanticReductionAuthorityMemberV3.create(
            normalization_request_core=core,
            normalization_request_core_canonical_bytes=encode_typed_value(
                core.model_dump(mode="python")
            ),
            operation_inputs=_native_reduction_inputs(
                core=core, operation_fence_binding=inputs.operation_fence_binding,
            ),
            execution_policy=inputs.graph_dependent_execution_policy,
            execution_policy_canonical_bytes=encode_typed_value(
                inputs.graph_dependent_execution_policy.model_dump(mode="python")
            ),
            capability_registry=inputs.capability_registry,
            capability_registry_canonical_bytes=encode_typed_value(
                inputs.capability_registry.model_dump(mode="python")
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


class GraphFreeSourceNormalizationRuntime:
    """Bind the pure stage to a host-owned, typed input producer.

    Returning ``None`` is a typed non-commit: the coordinator must stop before
    terminal persistence rather than fabricate a partial authority chain.
    """

    def __init__(
        self,
        *,
        stage: GraphFreeSourceNormalizationStage,
        inputs_provider: GraphFreeSourceNormalizationInputsProvider,
    ) -> None:
        self._stage = stage
        self._inputs_provider = inputs_provider

    def normalize(
        self,
        invocation: GraphFreeSourceNormalizationInvocation,
    ) -> SourceNormalizationResult | None:
        inputs = self._inputs_provider.build_inputs(invocation)
        if inputs is None:
            return None
        if (
            inputs.source != invocation.source
            or inputs.operation_fence_binding != invocation.operation_fence_binding
        ):
            return None
        try:
            return self._stage.normalize(inputs)
        except ValueError:
            return None


__all__ = [
    "GraphFreeSourceNormalizationInputs",
    "GraphFreeSourceNormalizationInputsProvider",
    "GraphFreeSourceNormalizationInvocation",
    "GraphFreeSourceNormalizationRuntime",
    "GraphFreeSourceNormalizationStage",
    "validate_reloaded_source_normalization_result",
    "validate_reloaded_bootstrap_v3_source_normalization_result",
]
