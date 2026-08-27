"""Typed, deterministic host ingredients for source-normalization tests.

The fixture deliberately receives the volatile publication controls from its
caller.  Those values are issued by the atomic/bootstrap test setup and cannot
be truthfully reconstructed from an immutable ``PreparedSource``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256

from memorii.core.memory_evolution.atomic_store import BootstrapWriterHandoffResult, OperationLeaseBinding
from memorii.core.memory_evolution.ingestion_contracts import (
    OperationFenceBinding,
    SemanticWriterCommitBinding,
    encode_typed_value,
)
from memorii.core.memory_evolution.semantic_analysis.decision_contracts import SourceNormalizationPublicationCoordinate
from memorii.core.memory_evolution.semantic_analysis.policies import (
    ConstructionFamily,
    PredicateSemanticPolicy,
    QuotationBoundaryPolicy,
    SemanticScopePolicy,
    UdPathPattern,
    UdPathStep,
    UdRoleSchema,
)
from memorii.core.semantic_ingestion.contracts import (
    CANONICAL_INGESTION_EXECUTION_GRAPH,
    AnalyzerManifest,
    BootstrapAnalysisProvenanceV1,
    BootstrapAnalysisRouteBinding,
    BootstrapAnalysisRouteBindingSet,
    BootstrapAnalysisRouteProjection,
    BootstrapDeclaredSegmentLanguageRoute,
    BootstrapGraphPreExecutionManifestIdentityClosureV3,
    BootstrapLinguisticAnalysisRequestV3,
    BootstrapPredicateEventDetectionRequestV3,
    BootstrapRecoveryClaimV3,
    BootstrapSegmentAnalysisInputV3,
    BootstrapSemanticProposalRequestV3,
    BootstrapTemporalResolutionRequestV3,
    BootstrapV3PayloadLimitAuthority,
    BootstrapV3PayloadLimitPolicy,
    FactOperationSemanticPolicyKey,
    IngestionExecutionManifest,
    IngestionStageInstanceRef,
    IngestionStageOutcome,
    LanguageConstructionPolicyAuthorityBundle,
    ParserConsensusPolicy,
    ParserOperationPolicyAuthority,
    PredicateEventManifest,
    PredicateSemanticPolicyBinding,
    PreparedSource,
    PrePlanningSourceIngestionProgress,
    ProviderSemanticProposal,
    ScopeConsensusPolicy,
    ScopeOperationPolicyAuthority,
    SegmentLanguageResourceBinding,
    SegmentLanguageRouteSet,
    SemanticProposalRequest,
    SourceSpanReference,
    TemporalAttachmentConsensusPolicy,
    TemporalPolicySnapshot,
    TemporalResolverManifest,
    TrustPolicySnapshot,
    contract_digest,
)
from memorii.core.semantic_ingestion.proposal_adapter import ProjectionQuoteVerificationAuthority
from memorii.core.semantic_ingestion.source_normalization_authority import (
    BootstrapV3RuntimeAuthority,
    CapabilityRegistryEntry,
    CapabilityRegistrySnapshot,
    ConsensusPolicyAuthority,
    GraphDependentExecutionPolicy,
    ProposalRunProductionAuthority,
)
from memorii.core.semantic_ingestion.source_normalization_execution import (
    SourceNormalizationAuthorityBundle,
    SourceNormalizationDerivationAuthority,
    SourceNormalizationPublicationAuthority,
)
from memorii.core.semantic_ingestion.source_normalization_stage import GraphFreeSourceNormalizationInvocation


@dataclass(frozen=True)
class SourceNormalizationPublicationFixture:
    """Already-issued test controls retained by the atomic/bootstrap fixture."""

    operation_id: str
    operation_fence_binding: OperationFenceBinding
    progress: PrePlanningSourceIngestionProgress
    operation_lease_binding: OperationLeaseBinding
    writer_commit_binding: SemanticWriterCommitBinding
    expected_operation_generation: int
    expected_artifact_generation: int

    def coordinate(self, source: PreparedSource) -> SourceNormalizationPublicationCoordinate:
        return SourceNormalizationPublicationCoordinate.create(
            operation_fence_binding=self.operation_fence_binding,
            preparation_fingerprint=source.preparation_fingerprint,
            expected_current_artifact_generation=self.expected_artifact_generation,
        )


def build_source_normalization_publication_fixture(
    *,
    source: PreparedSource,
    operation_id: str,
    bootstrap_handoff: BootstrapWriterHandoffResult,
    expected_operation_generation: int = 1,
    expected_artifact_generation: int = 1,
) -> SourceNormalizationPublicationFixture:
    """Build publication controls from one prepared source and bootstrap handoff.

    The bootstrap marker is the only source of the operation fence and writer
    admission.  This keeps fixture publication inputs aligned with the same
    source-owned handoff that production uses, without inventing a loose test
    namespace for the control-plane values.
    """
    marker = bootstrap_handoff.marker
    if bootstrap_handoff.kind not in {"started", "already_started"} or marker is None:
        raise ValueError("fixture publication requires a started bootstrap handoff")
    fence = marker.operation_fence_binding
    if (
        marker.source_id != source.source_id
        or marker.source_digest != source.source_digest
        or fence.operation_id != operation_id
        or fence.source_id != source.source_id
        or fence.source_digest != source.source_digest
    ):
        raise ValueError("fixture publication source, operation, and bootstrap handoff must join")
    if isinstance(expected_operation_generation, bool) or expected_operation_generation < 1:
        raise ValueError("fixture expected operation generation must be positive")
    if isinstance(expected_artifact_generation, bool) or expected_artifact_generation < 1:
        raise ValueError("fixture expected artifact generation must be positive")

    writer = marker.writer_commit_binding
    lease_values = {
        "operation_id": operation_id,
        "operation_fence_binding": fence,
        "delivery_principal_binding_digest": fence.delivery_principal_binding_digest,
        "delivery_key_digest": fence.delivery_key_digest,
        "allocation_namespace_id": fence.allocation_namespace_id,
        "writer_namespace": "semantic_ingestion",
        "admitted_writer_epoch": writer.expected_writer_epoch,
        "writer_admission_digest": writer.admission_digest,
        "writer_implementation_fingerprint": writer.writer_implementation_fingerprint,
        "state_revision": expected_operation_generation,
        "owner_id": "source-normalization-fixture-owner",
        "execution_token": "source-normalization-fixture-token",
        "ownership_epoch": 1,
        "lease_expires_at": datetime(2026, 1, 2, tzinfo=UTC),
    }
    lease_digest_values = {
        **lease_values,
        "operation_fence_binding": fence.model_dump(mode="python"),
    }
    lease = OperationLeaseBinding(
        **lease_values,
        binding_digest=sha256(encode_typed_value(lease_digest_values)).hexdigest(),
    )
    manifest = _build_preplanning_execution_manifest(source=source, operation_id=operation_id)
    completed = tuple(
        sorted(
            (
                outcome.instance
                for outcome in manifest.source_outcomes
                if outcome.instance.scope == "source" and outcome.status == "complete"
            ),
            key=lambda instance: encode_typed_value(instance.model_dump(mode="python")),
        )
    )
    eligible = tuple(
        sorted(
            (
                outcome.instance
                for outcome in manifest.source_outcomes
                if outcome.instance.scope == "source" and outcome.status == "not_started"
            ),
            key=lambda instance: encode_typed_value(instance.model_dump(mode="python")),
        )
    )
    reusable = tuple(
        sorted(
            outcome.artifact_digest
            for outcome in manifest.source_outcomes
            if outcome.instance.scope == "source"
            and outcome.status == "complete"
            and outcome.artifact_digest is not None
        )
    )
    progress = PrePlanningSourceIngestionProgress.create(
        source_id=source.source_id,
        source_digest=source.source_digest,
        operation_id=operation_id,
        execution_manifest=manifest,
        completed_source_stage_instances=completed,
        next_eligible_source_stage_instances=eligible,
        replay_artifact_bundle_digest=_fixture_digest("replay", source.source_id, operation_id),
        reusable_artifact_digests=reusable,
        retry_attempt_count=1,
        retry_reason_codes=(),
        operation_lease_binding=lease,
    )
    return SourceNormalizationPublicationFixture(
        operation_id=operation_id,
        operation_fence_binding=fence,
        progress=progress,
        operation_lease_binding=lease,
        writer_commit_binding=writer,
        expected_operation_generation=expected_operation_generation,
        expected_artifact_generation=expected_artifact_generation,
    )


def _build_preplanning_execution_manifest(
    *, source: PreparedSource, operation_id: str
) -> IngestionExecutionManifest:
    """Mirror the canonical pre-planning stage closure for a prepared source."""
    outcomes: list[IngestionStageOutcome] = []
    at = datetime(2026, 1, 1, tzinfo=UTC)
    done_at = datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
    for spec in CANONICAL_INGESTION_EXECUTION_GRAPH.stages:
        if "source" in spec.allowed_scopes:
            instance = IngestionStageInstanceRef(stage=spec.stage, scope="source")
            if spec.stage == "source_summary_persistence":
                outcomes.append(IngestionStageOutcome(instance=instance, status="not_started"))
            else:
                outcomes.append(IngestionStageOutcome(
                    instance=instance,
                    status="complete",
                    started_at=at,
                    completed_at=done_at,
                    artifact_digest=_fixture_digest("artifact", operation_id, spec.stage, "source"),
                ))
        if "segment" in spec.allowed_scopes:
            for route in source.segment_language_routes.routes:
                instance = IngestionStageInstanceRef(
                    stage=spec.stage,
                    scope="segment",
                    segment_id=route.segment_id,
                    segment_language_route_digest=route.route_digest,
                )
                outcomes.append(IngestionStageOutcome(
                    instance=instance,
                    status="complete",
                    started_at=at,
                    completed_at=done_at,
                    artifact_digest=_fixture_digest(
                        "artifact", operation_id, spec.stage, route.segment_id
                    ),
                ))
    pre_execution = BootstrapGraphPreExecutionManifestIdentityClosureV3.create(
        request_digest=_fixture_digest("pre-execution-request", operation_id),
        normalization_replay_digest=_fixture_digest("pre-execution-replay", operation_id),
        source_id=source.source_id, source_digest=source.source_digest,
        preparation_fingerprint=source.preparation_fingerprint,
        identities=(), identity_by_group=(),
        operation_fence_binding_digest=_fixture_digest("pre-execution-fence", operation_id),
        writer_commit_binding_digest=_fixture_digest("pre-execution-writer", operation_id),
    )
    return IngestionExecutionManifest.create(
        pre_execution_manifests=pre_execution,
        pre_execution_manifest_identity_closure_digest=pre_execution.closure_digest,
        execution_graph_fingerprint=CANONICAL_INGESTION_EXECUTION_GRAPH.graph_fingerprint,
        segment_language_routes=source.segment_language_routes,
        segment_governance_carriers=source.segment_governance_carriers,
        message_admission_carriers=source.message_admission_carriers,
        governance_carrier_artifact=source.governance_carrier_artifact,
        capability_bindings=(),
        source_outcomes=tuple(
            sorted(outcomes, key=lambda outcome: encode_typed_value(outcome.model_dump(mode="python")))
        ),
        graph_validation_attempts=(),
        transaction_group_outcomes=(),
        causal_blockers=(),
        terminal_before_planning_proof_digests=(),
    )


def _fixture_digest(*parts: str) -> str:
    return sha256("\0".join(parts).encode("utf-8")).hexdigest()


class SourceBackedQuoteAuthority(ProjectionQuoteVerificationAuthority):
    """Validates resolved quotes against the immutable prepared projection text."""

    def __init__(self, source: PreparedSource) -> None:
        self._source = source

    def resolve(self, quote: str, context: object, owned: bool) -> object:
        del owned
        if not hasattr(context, "projection_span"):
            raise ValueError("fixture quote context is invalid")
        start_at = context.projection_span.start
        end_at = context.projection_span.end
        positions = []
        start = self._source.semantic_text.find(quote, start_at, end_at)
        while start >= 0:
            positions.append(start)
            start = self._source.semantic_text.find(quote, start + 1, end_at)
        if len(positions) != 1:
            raise ValueError("fixture quote must resolve exactly once")
        start = positions[0]
        projection = context.projection_span
        local = context.segment_local_span
        return type(context).create(
            source_id=self._source.source_id,
            projection_digest=context.projection_digest,
            projection_segment_id=context.projection_segment_id,
            retained_text_artifact=context.retained_text_artifact,
            projection_span=type(projection).create(
                artifact=projection.artifact, start=start, end=start + len(quote),
                substring_digest=sha256(quote.encode("utf-8")).hexdigest(),
            ),
            segment_local_span=type(local).create(
                artifact=local.artifact, start=start, end=start + len(quote),
                substring_digest=sha256(quote.encode("utf-8")).hexdigest(),
            ),
            text_mapping_proof=context.text_mapping_proof,
            source_reference=quote,
        )

    def verify_quote(self, *, projection_digest: str, quote: str, span: object) -> None:
        if (
            not hasattr(span, "projection_span")
            or projection_digest != span.projection_digest
            or self._source.semantic_text[span.projection_span.start : span.projection_span.end] != quote
        ):
            raise ValueError("fixture quote is not an exact projection slice")


def build_manifest_bound_prepared_source(*, source_id: str, source_digest: str, source_text: str) -> PreparedSource:
    """Rebind the clean-room retained-text fixture to four typed local manifests."""
    from tests.unit.core.semantic_ingestion.clean_room_request_test_support import build_prepared_source_authority

    source = build_prepared_source_authority(source_id=source_id, source_digest=source_digest, source_text=source_text)
    def digest(label: str) -> str:
        return contract_digest(b"memorii.fixture.source-normalization.manifest.v1", {"label": label})
    stanza = AnalyzerManifest.create(analyzer_id="fixture-stanza", analyzer_kind="stanza", library_version="1", resource_manifest_digest=digest("stanza-resource"), model_file_hashes=(digest("stanza-model"),), processor_configuration_digest=digest("stanza-processors"), adapter_version="1", supported_languages=("en",), analyzer_fingerprint=digest("stanza"))
    spacy = AnalyzerManifest.create(analyzer_id="fixture-spacy", analyzer_kind="spacy", library_version="1", resource_manifest_digest=digest("spacy-resource"), model_file_hashes=(digest("spacy-model"),), processor_configuration_digest=digest("spacy-processors"), adapter_version="1", supported_languages=("en",), analyzer_fingerprint=digest("spacy"))
    predicate = PredicateEventManifest.create(language="en", predicate_lemmas=("work",), inflection_table_digest=digest("predicate-inflections"), multi_token_forms=())
    temporal = TemporalResolverManifest.create(binary_digest=digest("duckling-binary"), ruleset_version="1", locale_map_digest=digest("duckling-locales"), timezone_policy_digest=digest("duckling-timezone"), adapter_schema_digest=digest("duckling-schema"), supported_construction_families=("absolute",))
    old = source.segment_language_routes.routes[0]
    binding = SegmentLanguageResourceBinding.create(selected_language="en", proposal_capability_fingerprint=old.resource_binding.proposal_capability_fingerprint, stanza_analyzer_manifest_digest=stanza.manifest_digest, spacy_analyzer_manifest_digest=spacy.manifest_digest, predicate_event_manifest_digest=predicate.manifest_digest, temporal_resolver_manifest_digest=temporal.manifest_digest)
    route = type(old).create(**(old.model_dump(mode="python", exclude={"route_digest"}) | {"resource_binding": binding}))
    routes = SegmentLanguageRouteSet.create(source_id=source.source_id, source_digest=source.source_digest, routes=(route,))
    body = source.model_dump(mode="python", exclude={"preparation_fingerprint"}) | {"segments": (source.segments[0].model_copy(update={"language_route": route}),), "segment_language_routes": routes}
    return PreparedSource(**body, preparation_fingerprint=contract_digest(b"memorii.semantic-ingestion.prepared-source.v1", body))


def build_bootstrap_declared_prepared_source(
    *, source_id: str, source_digest: str, source_text: str
) -> PreparedSource:
    """Build a real bootstrap-route source without turning it into a generic route.

    This is deliberately test-only input construction.  Runtime code receives
    the resulting immutable ``PreparedSource`` exactly as it would after the
    verified bootstrap preparation producer has selected a corpus form.
    """
    from memorii.core.memory_evolution.bootstrap_profile import BootstrapSegmentGrammarProof
    from memorii.core.semantic_ingestion.contracts import PreparedSegment

    prepared = build_manifest_bound_prepared_source(
        source_id=source_id, source_digest=source_digest, source_text=source_text
    )
    old = prepared.segment_language_routes.routes[0]
    proof = BootstrapSegmentGrammarProof.create(
        source_id=prepared.source_id,
        segment_id=old.segment_id,
        language_evidence_tuple=("en", "authenticated_host_declaration", "trusted", "agrees"),
        bootstrap_language_evidence_digest=_fixture_digest("bootstrap-language", source_id),
        normalized_segment_digest=old.segment_text_content_digest,
        corpus_case_id="fixture-supported-form",
    )
    route = BootstrapDeclaredSegmentLanguageRoute.create(
        schema_id="memorii.semantic_ingestion.bootstrap_declared_segment_language_route",
        schema_version=1,
        source_id=prepared.source_id,
        source_digest=prepared.source_digest,
        segment_id=old.segment_id,
        parent_projection_segment_id=old.parent_projection_segment_id,
        segment_text_artifact_id=old.segment_text_artifact_id,
        segment_text_artifact_digest=old.segment_text_artifact_digest,
        segment_text_content_digest=old.segment_text_content_digest,
        declared_language="en",
        language_evidence_kind="authenticated_host_declaration",
        language_evidence_trust="trusted",
        governance_agreement="agrees",
        bootstrap_language_evidence_digest=proof.bootstrap_language_evidence_digest,
        bootstrap_profile_manifest_digest=_fixture_digest("bootstrap-profile"),
        preparation_policy_fingerprint=prepared.preparation_policy.policy_fingerprint,
        component_root_digest=_fixture_digest("bootstrap-components"),
        corpus_case_id=proof.corpus_case_id,
        normalized_segment_digest=proof.normalized_segment_digest,
        grammar_proof_digest=proof.proof_digest,
        decision="selected",
    )
    segment = prepared.segments[0].model_copy(update={"language_route": route})
    body = {
        name: getattr(prepared, name)
        for name in PreparedSource.model_fields
        if name != "preparation_fingerprint"
    }
    body.update(
        segments=(PreparedSegment.model_validate(segment.model_dump(mode="python")),),
        segment_language_routes=SegmentLanguageRouteSet.create(
            source_id=prepared.source_id, source_digest=prepared.source_digest, routes=(route,)
        ),
        grammar_proofs=(proof,),
    )
    return PreparedSource(
        **body,
        preparation_fingerprint=contract_digest(
            b"memorii.semantic-ingestion.prepared-source.v1", body
        ),
    )


@dataclass(frozen=True)
class BootstrapV3FixtureAuthority:
    """Closed V3 request authority and its four manifest-bearing lane inputs."""

    runtime_authority: BootstrapV3RuntimeAuthority
    route_bindings: BootstrapAnalysisRouteBindingSet
    stanza_manifest: AnalyzerManifest
    spacy_manifest: AnalyzerManifest
    predicate_manifest: PredicateEventManifest
    temporal_manifest: TemporalResolverManifest
    linguistic_request: Callable[[BootstrapSemanticProposalRequestV3, str], BootstrapLinguisticAnalysisRequestV3]
    predicate_request: Callable[[BootstrapSemanticProposalRequestV3], BootstrapPredicateEventDetectionRequestV3]
    temporal_request: Callable[[BootstrapSemanticProposalRequestV3], BootstrapTemporalResolutionRequestV3]


def build_bootstrap_v3_fixture_authority(*, source: PreparedSource) -> BootstrapV3FixtureAuthority:
    """Issue one complete V3 runtime authority from a declared prepared source.

    The helper has no V2 recovery/request bridge: callers receive the exact
    V3 proposal request and factories consumed by the configured host bundle.
    """
    from tests.unit.core.semantic_ingestion.clean_room_request_test_support import (
        build_clean_room_semantic_proposal_request,
    )

    if len(source.segments) != 1 or len(source.segment_language_routes.routes) != 1:
        raise ValueError("bootstrap V3 fixture supports exactly one declared segment")
    route = source.segment_language_routes.routes[0]
    if not isinstance(route, BootstrapDeclaredSegmentLanguageRoute):
        raise ValueError("bootstrap V3 fixture requires a declared bootstrap route")
    base = build_clean_room_semantic_proposal_request(
        source_id=source.source_id,
        source_digest=source.source_digest,
        source_text=source.semantic_text,
        require_text_digest=False,
    )

    def manifest(label: str, kind: str) -> AnalyzerManifest:
        return AnalyzerManifest.create(
            analyzer_id=f"fixture-{label}", analyzer_kind=kind, library_version="1",
            resource_manifest_digest=_fixture_digest(label, "resource"),
            model_file_hashes=(_fixture_digest(label, "model"),),
            processor_configuration_digest=_fixture_digest(label, "processors"),
            adapter_version="1", supported_languages=("en",),
            analyzer_fingerprint=_fixture_digest(label, "fingerprint"),
        )

    stanza, spacy = manifest("stanza", "stanza"), manifest("spacy", "spacy")
    predicate = PredicateEventManifest.create(
        language="en", predicate_lemmas=("work",),
        inflection_table_digest=_fixture_digest("predicate", "inflections"), multi_token_forms=(),
    )
    temporal = TemporalResolverManifest.create(
        binary_digest=_fixture_digest("temporal", "binary"), ruleset_version="1",
        locale_map_digest=_fixture_digest("temporal", "locales"),
        timezone_policy_digest=_fixture_digest("temporal", "timezone"),
        adapter_schema_digest=_fixture_digest("temporal", "schema"),
        supported_construction_families=("absolute",),
    )
    resource = SegmentLanguageResourceBinding.create(
        selected_language="en",
        proposal_capability_fingerprint=base.proposal_capability_fingerprint,
        stanza_analyzer_manifest_digest=stanza.manifest_digest,
        spacy_analyzer_manifest_digest=spacy.manifest_digest,
        predicate_event_manifest_digest=predicate.manifest_digest,
        temporal_resolver_manifest_digest=temporal.manifest_digest,
    )
    binding_body = {
        "source_id": source.source_id, "source_digest": source.source_digest,
        "preparation_fingerprint": source.preparation_fingerprint,
        "segment_id": route.segment_id, "parent_projection_segment_id": route.parent_projection_segment_id,
        "bootstrap_route_digest": route.route_digest,
        "segment_text_artifact_id": route.segment_text_artifact_id,
        "segment_text_artifact_digest": route.segment_text_artifact_digest,
        "segment_text_content_digest": route.segment_text_content_digest,
        "selected_language": "en", "resource_binding": resource,
        "proposal_capability_fingerprint": resource.proposal_capability_fingerprint,
        "stanza_analyzer_manifest_digest": stanza.manifest_digest,
        "spacy_analyzer_manifest_digest": spacy.manifest_digest,
        "predicate_event_manifest_digest": predicate.manifest_digest,
        "temporal_resolver_manifest_digest": temporal.manifest_digest,
    }
    binding = BootstrapAnalysisRouteBinding(
        **binding_body,
        binding_digest=contract_digest(
            b"memorii.semantic-ingestion.bootstrap-analysis-route-binding.v1", binding_body
        ),
    )
    provenance = BootstrapAnalysisProvenanceV1.from_binding(binding)
    projection = BootstrapAnalysisRouteProjection.create(
        bootstrap_route=route, binding=binding, bootstrap_analysis_provenance=provenance
    )
    segment = source.segments[0]
    context = SourceSpanReference.create(
        source_id=source.source_id,
        projection_digest=segment.context_projection_span.artifact.artifact_digest,
        projection_segment_id=segment.parent_projection_segment_id,
        retained_text_artifact=source.semantic_text_projection.retained_text_artifact,
        projection_span=segment.context_projection_span,
        segment_local_span=segment.context_segment_span,
        text_mapping_proof=segment.text_mapping_proof,
        source_reference=None,
    )
    input_value = BootstrapSegmentAnalysisInputV3.create(
        schema_version=3, source_id=source.source_id, source_digest=source.source_digest,
        preparation_fingerprint=source.preparation_fingerprint, segment_id=segment.segment_id,
        parent_projection_segment_id=segment.parent_projection_segment_id,
        segment_governance=segment.segment_governance,
        message_admission_identity=segment.message_admission_identity,
        governance_carrier_artifact=source.governance_carrier_artifact,
        context_text=context, segment_text=source.semantic_text,
        bootstrap_projection=projection, bootstrap_analysis_provenance=provenance,
    )
    request = BootstrapSemanticProposalRequestV3.create(
        schema_version=3, segment=input_value,
        semantic_context_fingerprint=segment.segment_governance.message_semantic_context_digest,
        provider_egress_decision_digest=None,
        proposal_capability_fingerprint=base.proposal_capability_fingerprint,
        predicate_catalog=base.predicate_catalog,
        action_proposal_catalog=base.action_proposal_catalog,
        registered_prompt=base.registered_prompt, proposer_manifest=base.proposer_manifest,
        bootstrap_analysis_provenance=provenance,
    )
    policy = BootstrapV3PayloadLimitPolicy.create(**{
        field: (1_000_000 if field.endswith("bytes") else 8)
        for field in BootstrapV3PayloadLimitPolicy.model_fields
        if field not in {"schema_version", "policy_digest"}
    })
    limits = BootstrapV3PayloadLimitAuthority.create(
        policy=policy, source_id=source.source_id, source_digest=source.source_digest,
        preparation_fingerprint=source.preparation_fingerprint,
    )
    runtime_body = {"proposal_requests": (request,), "payload_limit_authority": limits}
    runtime = BootstrapV3RuntimeAuthority(
        **runtime_body,
        authority_digest=contract_digest(
            b"memorii.semantic-ingestion.bootstrap-v3-runtime-authority.v3", runtime_body
        ),
    )
    binding_set_body = {
        "source_id": source.source_id,
        "source_digest": source.source_digest,
        "preparation_fingerprint": source.preparation_fingerprint,
        "bindings": (binding,),
    }
    binding_set = BootstrapAnalysisRouteBindingSet(
        **binding_set_body,
        binding_set_digest=contract_digest(
            b"memorii.semantic-ingestion.bootstrap-analysis-route-binding-set.v1", binding_set_body
        ),
    )

    def linguistic(value: BootstrapSemanticProposalRequestV3, lane: str) -> BootstrapLinguisticAnalysisRequestV3:
        selected = stanza if lane == "stanza" else spacy if lane == "spacy" else None
        if selected is None:
            raise ValueError("fixture linguistic lane is unknown")
        return BootstrapLinguisticAnalysisRequestV3.create(
            schema_version=3, segment=value.segment, analyzer_manifest=selected,
            bootstrap_analysis_provenance=value.bootstrap_analysis_provenance,
        )

    def predicate_request(value: BootstrapSemanticProposalRequestV3) -> BootstrapPredicateEventDetectionRequestV3:
        return BootstrapPredicateEventDetectionRequestV3.create(
            schema_version=3, segment=value.segment, predicate_event_manifest=predicate,
            bootstrap_analysis_provenance=value.bootstrap_analysis_provenance,
        )

    def temporal_request(value: BootstrapSemanticProposalRequestV3) -> BootstrapTemporalResolutionRequestV3:
        return BootstrapTemporalResolutionRequestV3.create(
            schema_version=3, segment=value.segment, resolver_manifest=temporal,
            reference_evidence=None, bootstrap_analysis_provenance=value.bootstrap_analysis_provenance,
        )

    return BootstrapV3FixtureAuthority(
        runtime_authority=runtime, route_bindings=binding_set, stanza_manifest=stanza, spacy_manifest=spacy,
        predicate_manifest=predicate, temporal_manifest=temporal,
        linguistic_request=linguistic, predicate_request=predicate_request,
        temporal_request=temporal_request,
    )


def build_source_normalization_authority_bundle(
    *,
    source: PreparedSource,
    publication: SourceNormalizationPublicationFixture,
    proposal_request: SemanticProposalRequest | None,
    consensus_policy_authority: ConsensusPolicyAuthority,
    language_construction_policies: LanguageConstructionPolicyAuthorityBundle,
    temporal_policy: TemporalPolicySnapshot,
    trust_policy: TrustPolicySnapshot,
    capability_registry: CapabilityRegistrySnapshot,
    graph_dependent_execution_policy: GraphDependentExecutionPolicy,
    retry_policy_fingerprint: str,
    bootstrap_v3_runtime_authority: BootstrapV3RuntimeAuthority | None = None,
    bootstrap_analysis_routes: BootstrapAnalysisRouteBindingSet | None = None,
    arbitration_as_of: datetime = datetime(2026, 1, 1, tzinfo=UTC),
) -> SourceNormalizationAuthorityBundle:
    """Build a complete digest-validated bundle from explicit audited leaves."""
    if publication.operation_id != publication.progress.operation_id:
        raise ValueError("fixture publication operation must join progress")
    if proposal_request is None:
        if bootstrap_v3_runtime_authority is None:
            raise ValueError("fixture authority requires a proposal request or V3 runtime authority")
        v3_request = bootstrap_v3_runtime_authority.proposal_requests[0]
        proposer_fingerprint = v3_request.proposer_manifest.runtime_fingerprint
        proposer_manifest_digest = v3_request.proposer_manifest.manifest_digest
        prompt_registration_digest = v3_request.registered_prompt.prompt_registration_digest
        semantic_request_fingerprint = v3_request.request_digest
        action_catalog_fingerprint = v3_request.action_proposal_catalog.catalog_schema_fingerprint
    else:
        request = SemanticProposalRequest.create(
            **proposal_request.model_dump(mode="python", exclude={"semantic_request_fingerprint"})
        )
        proposer_fingerprint = request.proposer_manifest.runtime_fingerprint
        proposer_manifest_digest = request.proposer_manifest.manifest_digest
        prompt_registration_digest = request.registered_prompt.prompt_registration_digest
        semantic_request_fingerprint = request.semantic_request_fingerprint
        action_catalog_fingerprint = request.action_proposal_catalog.catalog_schema_fingerprint
    authority_body = {
        "source_id": source.source_id, "source_digest": source.source_digest,
        "preparation_fingerprint": source.preparation_fingerprint,
        "route_set_digest": source.segment_language_routes.route_set_digest,
        "proposer_fingerprint": proposer_fingerprint,
        "proposer_manifest_digest": proposer_manifest_digest,
        "prompt_registration_digest": prompt_registration_digest,
        "semantic_request_fingerprint": semantic_request_fingerprint,
        "action_proposal_catalog_fingerprint": action_catalog_fingerprint,
        "retry_policy_fingerprint": retry_policy_fingerprint,
    }
    proposal_authority = ProposalRunProductionAuthority(
        **authority_body,
        authority_digest=contract_digest(b"memorii.semantic-ingestion.proposal-run-production-authority.v1", authority_body),
    )
    resources = tuple(
        route.resource_binding for route in source.segment_language_routes.routes
        if getattr(route, "resource_binding", None) is not None
    )
    bootstrap_routes = bootstrap_analysis_routes or BootstrapAnalysisRouteBindingSet(
        source_id=source.source_id,
        source_digest=source.source_digest,
        preparation_fingerprint=source.preparation_fingerprint,
        bindings=(),
        binding_set_digest=contract_digest(
            b"memorii.semantic-ingestion.bootstrap-analysis-route-binding-set.v1",
            {
                "source_id": source.source_id,
                "source_digest": source.source_digest,
                "preparation_fingerprint": source.preparation_fingerprint,
                "bindings": (),
            },
        ),
    )
    derivation_body = {
        "source_id": source.source_id, "source_digest": source.source_digest,
        "preparation_fingerprint": source.preparation_fingerprint,
        "proposal_run_authority": proposal_authority, "analyzer_resource_bindings": resources,
        "bootstrap_v3_runtime_authority": bootstrap_v3_runtime_authority,
        "bootstrap_analysis_routes": bootstrap_routes,
        "consensus_policy_authority": consensus_policy_authority,
        "language_construction_policies": language_construction_policies,
        "temporal_policy": temporal_policy, "trust_policy": trust_policy,
        "arbitration_as_of": arbitration_as_of, "capability_registry": capability_registry,
        "graph_dependent_execution_policy": graph_dependent_execution_policy,
    }
    # Match the canonical contract preimage exactly: Pydantic normalizes the
    # nested V3 authorities before the derivation authority validates itself.
    derivation_digest_body = SourceNormalizationDerivationAuthority.model_construct(
        **derivation_body,
        authority_digest="0" * 64,
    ).model_dump(mode="python", exclude={"authority_digest"}, exclude_none=True)
    derivation = SourceNormalizationDerivationAuthority(
        **derivation_body,
        authority_digest=contract_digest(
            b"memorii.semantic-ingestion.source-normalization-derivation-authority.v1",
            derivation_digest_body,
        ),
    )
    public = SourceNormalizationPublicationAuthority(
        source_id=source.source_id, source_digest=source.source_digest,
        preparation_fingerprint=source.preparation_fingerprint, operation_id=publication.operation_id,
        publication_coordinate=publication.coordinate(source), progress=publication.progress,
        operation_fence_binding=publication.operation_fence_binding,
        operation_lease_binding=publication.operation_lease_binding,
        writer_commit_binding=publication.writer_commit_binding,
        expected_operation_generation=publication.expected_operation_generation,
        expected_artifact_generation=publication.expected_artifact_generation,
    )
    return SourceNormalizationAuthorityBundle(derivation=derivation, publication=public)


def build_normal_fact_language_policies(*, proposal_run: object) -> LanguageConstructionPolicyAuthorityBundle:
    """Derive the exact two policy leaves for one sealed normal fact operation.

    The operation identifier is intentionally read only after proposal sealing;
    this keeps fixture policy authority coupled to the real proposal expansion.
    """
    from memorii.core.semantic_ingestion.contracts import PreAlignmentSemanticOperationSubjectSet

    proposals = getattr(proposal_run, "validated_segments", ())
    if len(proposals) != 1:
        raise ValueError("normal fixture requires exactly one validated segment")
    subjects = PreAlignmentSemanticOperationSubjectSet.create(proposal=proposals[0]).subjects
    if len(subjects) != 1 or subjects[0].kind != "fact":
        raise ValueError("normal fixture requires exactly one fact operation")
    subject = subjects[0]
    fact = proposals[0].facts[0]
    family = ConstructionFamily.create(family_id="declarative")
    path = UdPathPattern.create(
        anchor="predicate_head",
        steps=(UdPathStep(direction="up", dependency_label="nsubj", ordinal=0),),
    )
    role = UdRoleSchema.create(
        role_id="subject",
        anchor_form="verbal",
        allowed_dependency_paths=(path,),
        required_function_word_lemmas=frozenset(),
        forbidden_clause_crossings=frozenset(),
        coordination_support="allowed",
        voice_normalization="active_only",
        canonical_graph_role="subject",
        required_polarity_evidence="not_required",
        required_commitment_evidence=frozenset(),
    )
    predicate = PredicateSemanticPolicy.create(
        predicate_id=fact.predicate_id,
        language="en",
        predicate_lemmas=frozenset({"work"}),
        nominal_lemmas=frozenset(),
        role_schemas=(role,),
        verbalizer_id=None,
        supported_commitments=frozenset({"asserted"}),
        supported_constructions=frozenset({family}),
    )
    key = FactOperationSemanticPolicyKey(kind="fact", predicate_id=fact.predicate_id)
    parser_policy = ParserConsensusPolicy.create()
    scope_policy = ScopeConsensusPolicy.create()
    temporal_policy = TemporalAttachmentConsensusPolicy.create()
    parser = ParserOperationPolicyAuthority.create(
        operation_id=subject.operation_id,
        proposal_id=subject.proposal_id,
        segment_id=subject.segment_id,
        segment_language_route_digest=subject.segment_language_route_digest,
        parser_consensus_policy_fingerprint=parser_policy.policy_fingerprint,
        semantic_policy_key=key,
        predicate_policy_bindings=(
            PredicateSemanticPolicyBinding.create(
                role="fact", predicate_id=fact.predicate_id, policy=predicate
            ),
        ),
        construction_families=(family,),
        role_schemas=(role,),
    )
    scope = ScopeOperationPolicyAuthority.create(
        operation_id=subject.operation_id,
        proposal_id=subject.proposal_id,
        segment_id=subject.segment_id,
        segment_language_route_digest=subject.segment_language_route_digest,
        scope_consensus_policy_fingerprint=scope_policy.policy_fingerprint,
        temporal_attachment_consensus_policy_fingerprint=temporal_policy.policy_fingerprint,
        semantic_policy_key=key,
        scope_policy=SemanticScopePolicy.create(
            language="en",
            construction_family=family,
            predicate_family="declarative",
            allowed_predicate_ancestor_paths=(path,),
            negation_bearer_patterns=(),
            embedding_head_lemmas={},
            reporting_head_lemmas=frozenset(),
            question_mood_features=frozenset(),
            quotation_boundary_policy=QuotationBoundaryPolicy.create(
                mode="outside_quoted_content"
            ),
            temporal_attachment_patterns=(),
            forbidden_clause_crossings=frozenset(),
        ),
    )
    return LanguageConstructionPolicyAuthorityBundle.create(policies=(parser, scope))


@dataclass(frozen=True)
class DynamicSourceNormalizationProposalMaterials:
    """The exact proposal inputs issued beside one dynamic test authority.

    The real host's transport and request materializer can read this packet
    after ``build`` has admitted the invocation.  Keeping it in fixture code
    prevents a production authority issuer or a public export from becoming a
    test convenience.
    """

    request: object
    provider_proposal: ProviderSemanticProposal


class DynamicSourceNormalizationAuthorityProvider:
    """Test-only authority issuer for a dynamically prepared source.

    Unlike ``StaticSourceNormalizationAuthorityProvider``, this fixture does
    not key off a prebuilt source.  It derives the request, proposal authority,
    operation-keyed language policies, and publication controls from the actual
    invocation and its successful bootstrap handoff.  The preliminary sealing
    pass is intentional: operation identifiers exist only after the canonical
    proposal producer has normalized the supplied provider proposal.
    """

    def __init__(
        self,
        *,
        proposal_factory: Callable[[PreparedSource, SemanticProposalRequest], ProviderSemanticProposal],
        retry_policy_fingerprint: str,
        language_policy_builder: Callable[..., LanguageConstructionPolicyAuthorityBundle] = build_normal_fact_language_policies,
        publication_factory: Callable[[PreparedSource, str, BootstrapWriterHandoffResult], SourceNormalizationPublicationFixture] | None = None,
    ) -> None:
        if len(retry_policy_fingerprint) != 64:
            raise ValueError("fixture retry policy fingerprint must be a digest")
        self._proposal_factory = proposal_factory
        self._retry_policy_fingerprint = retry_policy_fingerprint
        self._language_policy_builder = language_policy_builder
        self._publication_factory = publication_factory or (
            lambda source, operation_id, handoff: build_source_normalization_publication_fixture(
                source=source, operation_id=operation_id, bootstrap_handoff=handoff
            )
        )
        self._issued: dict[
            tuple[str, str, str, str, str],
            tuple[SourceNormalizationAuthorityBundle, DynamicSourceNormalizationProposalMaterials],
        ] = {}
        self._publication_lease_lookup: Callable[..., OperationLeaseBinding] | None = None

    def bind_publication_lease_lookup(
        self, lookup: Callable[..., OperationLeaseBinding]
    ) -> None:
        """Receive the host-owned atomic lease reader during bundle composition."""
        if self._publication_lease_lookup is not None:
            raise ValueError("fixture publication lease authority is already bound")
        self._publication_lease_lookup = lookup
        self._bootstrap_v3_issued: dict[str, BootstrapV3FixtureAuthority] = {}

    def build(
        self,
        *,
        invocation: GraphFreeSourceNormalizationInvocation,
        handoff: BootstrapWriterHandoffResult,
        recovery_claim: BootstrapRecoveryClaimV3,
    ) -> SourceNormalizationAuthorityBundle | None:
        marker = handoff.marker
        if handoff.kind not in {"started", "already_started"} or marker is None:
            return None
        key = (
            invocation.source.source_id,
            invocation.source.source_digest,
            invocation.source.preparation_fingerprint,
            invocation.operation_id,
            invocation.operation_fence_binding.binding_digest,
        )
        if marker.operation_fence_binding != invocation.operation_fence_binding:
            return None
        control = recovery_claim.control_snapshot.control_record
        if control.operation_fence_digest != invocation.operation_fence_binding.binding_digest:
            return None
        cached = self._issued.get(key)
        if cached is not None:
            return cached[0]

        source = invocation.source
        route = source.segment_language_routes.routes[0]
        if len(source.segment_language_routes.routes) != 1:
            raise ValueError("dynamic fixture authority requires one prepared route")
        if isinstance(route, BootstrapDeclaredSegmentLanguageRoute):
            v3 = build_bootstrap_v3_fixture_authority(source=source)
            request = v3.runtime_authority.proposal_requests[0]
            proposal = ProviderSemanticProposal.model_validate(
                self._proposal_factory(source, request).model_dump(mode="python")
            )
            publication = self._publication_factory(source, invocation.operation_id, handoff)
            # The claim is the sole post-probe source of publication controls.
            # Reading a later lease would permit a stale authority bundle.
            lease = control.operation_lease_binding
            progress = type(publication.progress).create(
                **(
                    publication.progress.model_dump(mode="python", exclude={"kind", "progress_digest"})
                    | {"operation_lease_binding": lease}
                )
            )
            publication = replace(
                publication,
                operation_lease_binding=lease,
                writer_commit_binding=control.writer_commit_binding,
                expected_operation_generation=control.operation_generation,
                expected_artifact_generation=control.artifact_generation,
                progress=progress,
            )
            consensus, temporal, trust, registry, execution_policy = _dynamic_fixture_authorities(request)
            bundle = build_source_normalization_authority_bundle(
                source=source,
                publication=publication,
                proposal_request=None,
                bootstrap_v3_runtime_authority=v3.runtime_authority,
                bootstrap_analysis_routes=v3.route_bindings,
                consensus_policy_authority=consensus,
                language_construction_policies=LanguageConstructionPolicyAuthorityBundle.create(policies=()),
                temporal_policy=temporal,
                trust_policy=trust,
                capability_registry=registry,
                graph_dependent_execution_policy=execution_policy,
                retry_policy_fingerprint=self._retry_policy_fingerprint,
            )
            self._issued[key] = (bundle, DynamicSourceNormalizationProposalMaterials(request, proposal))
            self._bootstrap_v3_issued[request.request_digest] = v3
            return bundle

        # Only declared bootstrap routes reach the V3 execution owner; a
        # non-bootstrap route cannot be normalized and fails closed.
        return None

    def materials_for(
        self, *, invocation: GraphFreeSourceNormalizationInvocation
    ) -> DynamicSourceNormalizationProposalMaterials:
        """Return the exact request/proposal issued by a preceding ``build``."""
        key_prefix = (
            invocation.source.source_id,
            invocation.source.source_digest,
            invocation.source.preparation_fingerprint,
            invocation.operation_id,
            invocation.operation_fence_binding.binding_digest,
        )
        issued = self._issued.get(key_prefix)
        if issued is None:
            raise ValueError("dynamic fixture proposal materials were not issued")
        return issued[1]

    def bootstrap_v3_authority_for(
        self, request: BootstrapSemanticProposalRequestV3
    ) -> BootstrapV3FixtureAuthority:
        """Return the exact host-issued V3 request factories for one proposal."""
        issued = self._bootstrap_v3_issued.get(request.request_digest)
        if issued is None:
            raise ValueError("dynamic fixture bootstrap V3 authority was not issued")
        return issued


def _dynamic_fixture_authorities(
    request: SemanticProposalRequest,
) -> tuple[
    ConsensusPolicyAuthority,
    TemporalPolicySnapshot,
    TrustPolicySnapshot,
    CapabilityRegistrySnapshot,
    GraphDependentExecutionPolicy,
]:
    """Build validator-owned default leaves for one dynamic fixture request."""
    parser = ParserConsensusPolicy.create()
    scope = ScopeConsensusPolicy.create()
    attachment = TemporalAttachmentConsensusPolicy.create()
    consensus_body = {
        "parser_policy": parser,
        "scope_policy": scope,
        "temporal_attachment_policy": attachment,
    }
    consensus = ConsensusPolicyAuthority(
        **consensus_body,
        authority_digest=contract_digest(
            b"memorii.semantic-ingestion.consensus-policy-authority.v1", consensus_body
        ),
    )
    from memorii.core.memory_evolution.time_contracts import TimeInterval

    interval = TimeInterval(
        start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2027, 1, 1, tzinfo=UTC)
    )
    temporal = TemporalPolicySnapshot.create(
        policy_revision="dynamic-fixture-temporal", system_effective_interval=interval, rules=()
    )
    trust = TrustPolicySnapshot.create(
        policy_revision="dynamic-fixture-trust", system_effective_interval=interval, rules=()
    )
    registry_body = {
        "registry_revision": "dynamic-fixture",
        "capabilities": (
            CapabilityRegistryEntry(
                capability_id="local", capability_fingerprint=request.proposal_capability_fingerprint
            ),
        ),
    }
    registry = CapabilityRegistrySnapshot(
        **registry_body,
        snapshot_digest=contract_digest(
            b"memorii.semantic-ingestion.capability-registry-snapshot.v2", registry_body
        ),
    )
    limits = {
        "policy_version": 1,
        "maximum_operations_per_source": 1,
        "maximum_groups_per_source": 1,
        "maximum_fixed_point_rounds": 1,
        "maximum_records_per_snapshot": 1,
        "maximum_partitions_per_snapshot": 1,
        "maximum_related_conflicts_per_group": 1,
        "maximum_attempts_per_group": 1,
        "maximum_read_set_extensions": 1,
        "maximum_reservations": 1,
        "maximum_lineage_entries": 1,
        "maximum_replay_artifacts": 1,
        "maximum_replay_bundle_bytes": 1,
        "replay_artifact_schema_registry_fingerprint": _fixture_digest("dynamic", "replay"),
        "maximum_decode_depth": 1,
    }
    execution = GraphDependentExecutionPolicy(
        **limits,
        policy_digest=contract_digest(
            b"memorii.semantic-ingestion.graph-dependent-execution-policy.v1", limits
        ),
    )
    return consensus, temporal, trust, registry, execution


__all__ = [
    "SourceBackedQuoteAuthority", "SourceNormalizationPublicationFixture",
    "DynamicSourceNormalizationAuthorityProvider", "DynamicSourceNormalizationProposalMaterials",
    "build_manifest_bound_prepared_source", "build_source_normalization_authority_bundle",
    "build_bootstrap_declared_prepared_source", "build_bootstrap_v3_fixture_authority",
    "BootstrapV3FixtureAuthority",
    "build_normal_fact_language_policies",
    "build_source_normalization_publication_fixture",
]
