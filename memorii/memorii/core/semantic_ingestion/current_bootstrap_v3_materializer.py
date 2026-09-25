"""Current-release Bootstrap V3 request and lane authority materialization.

This is the production owner for turning an already verified freeform prepared
source into the V3 request closure.  It deliberately has no fixture imports,
ambient registry lookup, or storage access: live controls are added by the
dynamic authority issuer after this material is constructed.
"""

from __future__ import annotations

from dataclasses import dataclass

from memorii.core.memory_evolution.models import ClaimValueType
from memorii.core.semantic_ingestion.contracts import (
    ActionProposalCatalog,
    ActionProposalRoleContract,
    ActionProposalStateContract,
    AnalyzerManifest,
    BootstrapAnalysisProvenanceV1,
    BootstrapAnalysisRouteBinding,
    BootstrapAnalysisRouteBindingSet,
    BootstrapAnalysisRouteProjection,
    BootstrapFreeformSegmentLanguageRoute,
    BootstrapLinguisticAnalysisRequestV3,
    BootstrapPredicateEventDetectionRequestV3,
    BootstrapSegmentAnalysisInputV3,
    BootstrapSemanticProposalRequestV3,
    BootstrapTemporalResolutionRequestV3,
    BootstrapV3PayloadLimitAuthority,
    BootstrapV3PayloadLimitPolicy,
    PredicateEventManifest,
    PredicatePromptContract,
    PredicateProposalCatalog,
    PreparedSource,
    RegisteredSemanticPromptBinding,
    SegmentLanguageResourceBinding,
    SemanticProposerManifest,
    SourceSpanReference,
    TemporalResolverManifest,
    contract_digest,
)
from memorii.core.semantic_ingestion.current_bootstrap_v3_authority import (
    VerifiedBootstrapV3ResourcePolicy,
)
from memorii.core.semantic_ingestion.current_bootstrap_v3_lanes import (
    CurrentBootstrapV3InstalledLanes,
)
from memorii.core.semantic_ingestion.source_normalization_authority import BootstrapV3RuntimeAuthority


class CurrentBootstrapV3MaterializationError(ValueError):
    """The installed release cannot issue a closed V3 request authority."""


@dataclass(frozen=True)
class CurrentBootstrapV3Materialization:
    """One complete ephemeral V3 request/lane closure for a prepared source."""

    runtime_authority: BootstrapV3RuntimeAuthority
    route_bindings: BootstrapAnalysisRouteBindingSet
    stanza_manifest: AnalyzerManifest
    spacy_manifest: AnalyzerManifest
    predicate_manifest: PredicateEventManifest
    temporal_manifest: TemporalResolverManifest

    def linguistic_request(
        self, request: BootstrapSemanticProposalRequestV3, lane: str
    ) -> BootstrapLinguisticAnalysisRequestV3:
        manifest = self.stanza_manifest if lane == "stanza" else self.spacy_manifest if lane == "spacy" else None
        if manifest is None:
            raise CurrentBootstrapV3MaterializationError("Bootstrap V3 linguistic lane is invalid")
        return BootstrapLinguisticAnalysisRequestV3.create(
            schema_version=3,
            segment=request.segment,
            analyzer_manifest=manifest,
            bootstrap_analysis_provenance=request.bootstrap_analysis_provenance,
        )

    def predicate_request(
        self, request: BootstrapSemanticProposalRequestV3
    ) -> BootstrapPredicateEventDetectionRequestV3:
        return BootstrapPredicateEventDetectionRequestV3.create(
            schema_version=3,
            segment=request.segment,
            predicate_event_manifest=self.predicate_manifest,
            bootstrap_analysis_provenance=request.bootstrap_analysis_provenance,
        )

    def temporal_request(
        self, request: BootstrapSemanticProposalRequestV3
    ) -> BootstrapTemporalResolutionRequestV3:
        return BootstrapTemporalResolutionRequestV3.create(
            schema_version=3,
            segment=request.segment,
            resolver_manifest=self.temporal_manifest,
            reference_evidence=None,
            bootstrap_analysis_provenance=request.bootstrap_analysis_provenance,
        )


class CurrentBootstrapV3RequestMaterializer:
    """Build V3 request material solely from current installed policy bytes."""

    def __init__(self, *, resource_policy: VerifiedBootstrapV3ResourcePolicy) -> None:
        self._policy = resource_policy
        self._lanes = CurrentBootstrapV3InstalledLanes(resource_policy=resource_policy)
        self._stanza = self._lanes.stanza_manifest
        self._spacy = self._lanes.spacy_manifest
        self._predicate = self._lanes.predicate_manifest
        self._temporal = self._lanes.temporal_manifest
        self._capability = self._lanes.proposal_capability_fingerprint
        self._resource = SegmentLanguageResourceBinding.create(
            selected_language="en",
            proposal_capability_fingerprint=self._capability,
            stanza_analyzer_manifest_digest=self._stanza.manifest_digest,
            spacy_analyzer_manifest_digest=self._spacy.manifest_digest,
            predicate_event_manifest_digest=self._predicate.manifest_digest,
            temporal_resolver_manifest_digest=self._temporal.manifest_digest,
        )
        self._predicate_catalog = PredicateProposalCatalog.create(
            vocabulary_namespace="memorii.project_assertions",
            proposal_capability_fingerprint=self._capability,
            predicates=(
                PredicatePromptContract.create(
                    predicate_id="project_deadline", description="project deadline",
                    subject_value_kind="entity", object_value_kind="literal",
                    object_literal_type=ClaimValueType.DATE, supported_commitments=("asserted",),
                ),
                PredicatePromptContract.create(
                    predicate_id="project_owner", description="project owner",
                    subject_value_kind="entity", object_value_kind="entity",
                    object_literal_type=None, supported_commitments=("asserted",),
                ),
                PredicatePromptContract.create(
                    predicate_id="project_status", description="project status",
                    subject_value_kind="entity", object_value_kind="literal",
                    object_literal_type=ClaimValueType.TEXT, supported_commitments=("asserted",),
                ),
            ),
            catalog_schema_fingerprint="7c2fef7072d3996b93949eab7db1701d5458379a6b65d96f5851415d748fb0e0",
        )
        self._action_catalog = ActionProposalCatalog.create(
            vocabulary_namespace="memorii.project_assertions",
            proposal_capability_fingerprint=self._capability,
            roles=(ActionProposalRoleContract(
                role_id="actor", endpoint_kind="actor", description="action actor",
                grounding_requirement="verbatim_source_mention",
            ),),
            states=(ActionProposalStateContract(
                state_id="declared", description="declared action", allowed_role_ids=("actor",),
                required_state_anchor=True,
            ),),
            catalog_schema_fingerprint="0fb700ec5d56481e582f70d89a66627708cd95ad2393e9df78559e0f1f0b16fe",
        )
        self._prompt = RegisteredSemanticPromptBinding(
            prompt_ref="memorii.project_assertions@1",
            prompt_registration_digest=self._policy.prompt_schema_digest,
            prompt_content_digest=self._policy.prompt_schema_digest,
            output_schema_fingerprint=self._policy.prompt_schema_digest,
            owner_fingerprint=self._policy.component_fingerprint_digest,
            visibility_policy_digest=self._policy.egress_policy_digest,
            redaction_policy_digest=self._policy.egress_policy_digest,
        )
        self._proposer = SemanticProposerManifest.create(
            proposer_id="openai-responses-project-assertions",
            proposer_kind="remote",
            runtime_fingerprint=self._policy.component_fingerprint_digest,
            model_artifact_fingerprint=self._policy.provider_binding_digest,
            tokenizer_or_template_fingerprint=self._policy.prompt_schema_digest,
            structured_output_capability_fingerprint=self._capability,
        )

    def materialize(self, *, source: PreparedSource) -> CurrentBootstrapV3Materialization:
        routes = source.segment_language_routes.routes
        segments = {segment.segment_id: segment for segment in source.segments}
        if (
            source.status != "complete"
            or not routes
            or len(segments) != len(source.segments)
            or set(segments) != {route.segment_id for route in routes}
            or not all(isinstance(route, BootstrapFreeformSegmentLanguageRoute) for route in routes)
        ):
            raise CurrentBootstrapV3MaterializationError("prepared source has no current Bootstrap V3 freeform route closure")
        bindings: list[BootstrapAnalysisRouteBinding] = []
        requests: list[BootstrapSemanticProposalRequestV3] = []
        for route in routes:
            assert isinstance(route, BootstrapFreeformSegmentLanguageRoute)
            segment = segments[route.segment_id]
            binding = self._binding(source=source, route=route)
            provenance = BootstrapAnalysisProvenanceV1.from_binding(binding)
            projection = BootstrapAnalysisRouteProjection.create(
                bootstrap_route=route, binding=binding, bootstrap_analysis_provenance=provenance,
            )
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
            analysis = BootstrapSegmentAnalysisInputV3.create(
                schema_version=3, source_id=source.source_id, source_digest=source.source_digest,
                preparation_fingerprint=source.preparation_fingerprint, segment_id=segment.segment_id,
                parent_projection_segment_id=segment.parent_projection_segment_id,
                segment_governance=segment.segment_governance,
                message_admission_identity=segment.message_admission_identity,
                governance_carrier_artifact=source.governance_carrier_artifact,
                context_text=context, segment_text=source.semantic_text,
                bootstrap_projection=projection, bootstrap_analysis_provenance=provenance,
            )
            requests.append(BootstrapSemanticProposalRequestV3.create(
                schema_version=3, segment=analysis,
                semantic_context_fingerprint=segment.segment_governance.message_semantic_context_digest,
                provider_egress_decision_digest=segment.segment_governance.provider_egress_decision_digest,
                proposal_capability_fingerprint=self._capability,
                predicate_catalog=self._predicate_catalog,
                action_proposal_catalog=self._action_catalog,
                registered_prompt=self._prompt, proposer_manifest=self._proposer,
                bootstrap_analysis_provenance=provenance,
            ))
            bindings.append(binding)
        policy = BootstrapV3PayloadLimitPolicy.create(**{
            field: (1_000_000 if field.endswith("bytes") else 8)
            for field in BootstrapV3PayloadLimitPolicy.model_fields
            if field not in {"schema_version", "policy_digest"}
        })
        limits = BootstrapV3PayloadLimitAuthority.create(
            policy=policy, source_id=source.source_id, source_digest=source.source_digest,
            preparation_fingerprint=source.preparation_fingerprint,
        )
        requests_tuple = tuple(sorted(requests, key=lambda value: value.segment.segment_id))
        runtime_body = {"proposal_requests": requests_tuple, "payload_limit_authority": limits}
        runtime = BootstrapV3RuntimeAuthority(
            **runtime_body,
            authority_digest=contract_digest(b"memorii.semantic-ingestion.bootstrap-v3-runtime-authority.v3", runtime_body),
        )
        binding_body = {
            "source_id": source.source_id, "source_digest": source.source_digest,
            "preparation_fingerprint": source.preparation_fingerprint, "bindings": tuple(bindings),
        }
        return CurrentBootstrapV3Materialization(
            runtime_authority=runtime,
            route_bindings=BootstrapAnalysisRouteBindingSet(
                **binding_body,
                binding_set_digest=contract_digest(
                    b"memorii.semantic-ingestion.bootstrap-analysis-route-binding-set.v1", binding_body
                ),
            ),
            stanza_manifest=self._stanza, spacy_manifest=self._spacy,
            predicate_manifest=self._predicate, temporal_manifest=self._temporal,
        )

    def _binding(
        self, *, source: PreparedSource, route: BootstrapFreeformSegmentLanguageRoute
    ) -> BootstrapAnalysisRouteBinding:
        body = {
            "source_id": source.source_id, "source_digest": source.source_digest,
            "preparation_fingerprint": source.preparation_fingerprint, "segment_id": route.segment_id,
            "parent_projection_segment_id": route.parent_projection_segment_id,
            "bootstrap_route_digest": route.route_digest,
            "segment_text_artifact_id": route.segment_text_artifact_id,
            "segment_text_artifact_digest": route.segment_text_artifact_digest,
            "segment_text_content_digest": route.segment_text_content_digest,
            "selected_language": "en", "resource_binding": self._resource,
            "proposal_capability_fingerprint": self._capability,
            "stanza_analyzer_manifest_digest": self._stanza.manifest_digest,
            "spacy_analyzer_manifest_digest": self._spacy.manifest_digest,
            "predicate_event_manifest_digest": self._predicate.manifest_digest,
            "temporal_resolver_manifest_digest": self._temporal.manifest_digest,
        }
        return BootstrapAnalysisRouteBinding(
            **body,
            binding_digest=contract_digest(b"memorii.semantic-ingestion.bootstrap-analysis-route-binding.v1", body),
        )

    def _digest(self, label: str) -> str:
        return contract_digest(
            b"memorii.semantic-ingestion.current-bootstrap-v3-material.v1",
            {"label": label, "resource_policy_digest": self._policy.policy_digest},
        )


__all__ = [
    "CurrentBootstrapV3Materialization", "CurrentBootstrapV3MaterializationError",
    "CurrentBootstrapV3RequestMaterializer",
]
