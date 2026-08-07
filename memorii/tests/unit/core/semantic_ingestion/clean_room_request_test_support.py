"""Clean-room strict request fixture shared by semantic-ingestion tests."""

from hashlib import sha256

from memorii.core.memory_evolution.models import ClaimValueType, MemoryScope
from memorii.core.memory_evolution.semantic_analysis.policies import ConstructionFamily
from memorii.core.semantic_ingestion.contracts import (
    ActionProposalCatalog,
    ActionProposalRoleContract,
    ActionProposalStateContract,
    AnalyzerRoleInterpretation,
    CanonicalRoleAssignment,
    GovernanceCarrierArtifact,
    IndependentSourceAnalysis,
    LanguageCandidate,
    MessageAdmissionCarrierSet,
    MessageAdmissionIdentity,
    ParserConsensusAssessment,
    PredicatePromptContract,
    PredicateProposalCatalog,
    ProjectionTextSpan,
    RegisteredSemanticPromptBinding,
    RequiredOutcomeScopeSet,
    RetainedSourceTextArtifact,
    RetainedSourceTextSpan,
    SegmentGovernanceBinding,
    SegmentGovernanceCarrierSet,
    SegmentLanguageResourceBinding,
    SegmentLanguageRoute,
    SegmentLocalTextArtifact,
    SegmentLocalTextSpan,
    SemanticCandidate,
    SemanticProjectionTextArtifact,
    SemanticProposalRequest,
    SemanticProposerManifest,
    SourceAuthority,
    SourceAuthorityEvidence,
    SourceSpan,
    SourceSpanReference,
    SourceTemporalEvidenceSet,
    TemporalEvidenceCandidate,
    VerbatimTextArtifactMappingProof,
)
from memorii.domain.enums import SourceModality

_ACTION_SCHEMA = "0fb700ec5d56481e582f70d89a66627708cd95ad2393e9df78559e0f1f0b16fe"
_PREDICATE_SCHEMA = "7c2fef7072d3996b93949eab7db1701d5458379a6b65d96f5851415d748fb0e0"


def _digest(label: str) -> str:
    return sha256(label.encode("ascii")).hexdigest()


def build_clean_room_semantic_proposal_request(
    *,
    source_id: str = "clean-room-source",
    source_digest: str | None = None,
    source_text: str | None = None,
) -> SemanticProposalRequest:
    """Build without importing a test module or production encoding helpers."""
    text = source_text if source_text is not None else "Alice starts project Atlas. " * 4
    source_digest = source_digest or _digest(text)
    if source_digest != _digest(text):
        raise ValueError("clean-room source digest must bind the supplied text")
    parent, child = "parent-0", "child-0"
    retained = RetainedSourceTextArtifact.create(artifact_id="retained-0", content_digest=source_digest, unicode_scalar_length=len(text))
    projection = SemanticProjectionTextArtifact.create(artifact_id="projection-0", content_digest=source_digest, unicode_scalar_length=len(text))
    local = SegmentLocalTextArtifact.create(artifact_id="local-0", projection_segment_id=parent, content_digest=source_digest, unicode_scalar_length=len(text))
    retained_span = RetainedSourceTextSpan.create(artifact=retained, start=0, end=len(text), substring_digest=source_digest)
    projection_span = ProjectionTextSpan.create(artifact=projection, start=0, end=len(text), substring_digest=source_digest)
    local_span = SegmentLocalTextSpan.create(artifact=local, start=0, end=len(text), substring_digest=source_digest)
    proof = VerbatimTextArtifactMappingProof.create(retained_span=retained_span, projection_span=projection_span, segment_span=local_span)
    span = SourceSpanReference.create(source_id=source_id, projection_digest=projection.artifact_digest, projection_segment_id=parent, retained_text_artifact=retained, projection_span=projection_span, segment_local_span=local_span, text_mapping_proof=proof, source_reference="clean-room")
    governance = SegmentGovernanceBinding.create(source_id=source_id, segment_id=parent, message_semantic_context_digest=_digest("context"), effective_scope_digest=_digest("scope"), authority_digest=_digest("authority"), data_classification="internal", modality=SourceModality.ASSERTION, provider_egress_decision_digest=_digest("egress"), egress_disposition="allow_verbatim")
    carriers = SegmentGovernanceCarrierSet.create(source_id=source_id, bindings=(governance,))
    admission = MessageAdmissionIdentity.create(delivery_principal_binding_digest=_digest("principal"), authenticated_source_reference="clean-room-message", authenticated_source_reference_key_digest=_digest("reference-key"), message_bytes_digest=source_digest, segment_governance_binding_digest=governance.binding_digest)
    admissions = MessageAdmissionCarrierSet.create(source_id=source_id, identities=(admission,))
    artifact = GovernanceCarrierArtifact.create(artifact_id="governance-0", atomic_generation=1, segment_governance=carriers, message_admissions=admissions, required_outcome_scopes=RequiredOutcomeScopeSet.create(tenant_partition_id="tenant", scopes=(MemoryScope(user_id="clean-room-user"),)))
    capability = _digest("capability")
    resource = SegmentLanguageResourceBinding.create(selected_language="en", proposal_capability_fingerprint=capability, stanza_analyzer_manifest_digest=_digest("stanza"), spacy_analyzer_manifest_digest=_digest("spacy"), predicate_event_manifest_digest=_digest("predicate-event"), temporal_resolver_manifest_digest=_digest("temporal"))
    route = SegmentLanguageRoute.create(source_id=source_id, source_digest=source_digest, segment_id=child, parent_projection_segment_id=parent, segment_text_artifact_id=local.artifact_id, segment_text_artifact_digest=local.artifact_digest, segment_text_content_digest=local.content_digest, declared_language="en", candidates=(LanguageCandidate(language="en", probability_ppm=1_000_000, model_fingerprint=_digest("router")),), code_switch_spans=(), selected_language="en", decision="selected", minimum_probability_ppm=900_000, minimum_margin_ppm=10_000, routing_policy_fingerprint=_digest("route-policy"), router_manifest_fingerprint=_digest("router"), resource_binding=resource)
    entity = PredicatePromptContract.create(predicate_id="employs", description="entity relation", subject_value_kind="entity", object_value_kind="entity", object_literal_type=None, supported_commitments=("asserted", "reported"))
    literal = PredicatePromptContract.create(predicate_id="started_on", description="date relation", subject_value_kind="entity", object_value_kind="literal", object_literal_type=ClaimValueType.DATE, supported_commitments=("asserted",))
    predicates = PredicateProposalCatalog.create(vocabulary_namespace="vector", proposal_capability_fingerprint=capability, predicates=(entity, literal), catalog_schema_fingerprint=_PREDICATE_SCHEMA)
    actions = ActionProposalCatalog.create(vocabulary_namespace="vector", proposal_capability_fingerprint=capability, roles=(ActionProposalRoleContract(role_id="actor", endpoint_kind="actor", description="Actor", grounding_requirement="verbatim_source_mention"),), states=(ActionProposalStateContract(state_id="started", description="Started", allowed_role_ids=("actor",), required_state_anchor=True),), catalog_schema_fingerprint=_ACTION_SCHEMA)
    prompt = RegisteredSemanticPromptBinding(prompt_ref="semantic-proposal-v1", prompt_registration_digest=_digest("registration"), prompt_content_digest=_digest("content"), output_schema_fingerprint=_digest("schema"), owner_fingerprint=_digest("owner"), visibility_policy_digest=_digest("visibility"), redaction_policy_digest=_digest("redaction"))
    manifest = SemanticProposerManifest.create(proposer_id="local-vector", proposer_kind="local", runtime_fingerprint=_digest("runtime"), model_artifact_fingerprint=_digest("model"), tokenizer_or_template_fingerprint=_digest("tokenizer"), structured_output_capability_fingerprint=capability)
    return SemanticProposalRequest.create(source_id=source_id, source_digest=source_digest, semantic_context_fingerprint=governance.message_semantic_context_digest, preparation_fingerprint=_digest("preparation"), segment_id=child, segment_governance=governance, message_admission_identity=admission, governance_carrier_artifact=artifact, owned_text=span, context_text=span, segment_text=text, language_route=route, provider_egress_decision_digest=None, proposal_capability_fingerprint=capability, predicate_catalog=predicates, action_proposal_catalog=actions, registered_prompt=prompt, proposer_manifest=manifest)


def build_prepared_independent_source_analysis(
    *,
    proposal: SemanticCandidate,
    operation_id: str,
    source_id: str,
    source_digest: str,
    source_text: str,
    source_authority_evidence: SourceAuthorityEvidence,
    source_interval_evidence=None,
    temporal_candidates: tuple[TemporalEvidenceCandidate, ...] | None = None,
    stable: bool = True,
) -> IndependentSourceAnalysis:
    """Build a strict independent analysis closed over one prepared route."""
    request = build_clean_room_semantic_proposal_request(
        source_id=source_id, source_digest=source_digest, source_text=source_text
    )
    if (
        proposal.assertion_quote != source_text
        or source_authority_evidence.source_id != source_id
        or source_authority_evidence.source_digest != source_digest
    ):
        raise ValueError("prepared analysis inputs must bind one exact source")

    span = request.owned_text
    assignment = CanonicalRoleAssignment.create(
        role_id="subject", argument_span=span, endpoint_kind="subject"
    )
    corroborating_assignment = (
        assignment
        if stable
        else CanonicalRoleAssignment.create(
            role_id="subject", argument_span=span, endpoint_kind="object"
        )
    )
    construction = ConstructionFamily.create(family_id="transitive")
    primary = AnalyzerRoleInterpretation.create(
        analyzer_fingerprint="1" * 64,
        predicate_head_span=span,
        construction_family=construction,
        assignments=(assignment,),
    )
    corroborating = AnalyzerRoleInterpretation.create(
        analyzer_fingerprint="2" * 64,
        predicate_head_span=span,
        construction_family=construction,
        assignments=(corroborating_assignment,),
    )
    parser = ParserConsensusAssessment.create(
        source_id=source_id,
        source_digest=source_digest,
        preparation_fingerprint=request.preparation_fingerprint,
        segment_id=request.segment_id,
        proposal_id=proposal.candidate_id,
        operation_id=operation_id,
        segment_language_route_digest=request.language_route.route_digest,
        analysis_bundle_fingerprint=_digest("analysis-bundle"),
        primary_interpretation=primary,
        corroborating_interpretation=corroborating,
        stable_assignment=(assignment,) if stable else None,
        status="stable" if stable else "disagreement",
        consensus_policy_fingerprint=_digest("consensus-policy"),
    )
    if temporal_candidates is None:
        if source_interval_evidence is None:
            raise ValueError("prepared analysis requires temporal candidates or source interval evidence")
        temporal_candidates = (
            TemporalEvidenceCandidate.create(
                candidate_id="prepared-source-interval",
                kind="authenticated_source_interval",
                interval=source_interval_evidence.interval,
                source_authority=SourceAuthority(
                    authority_class=source_authority_evidence.authority.authority_class,
                    authenticated_provenance_class=source_authority_evidence.authority.authenticated_provenance_class,
                    policy_revision=source_authority_evidence.authority.policy_revision,
                ),
                authenticated_source_interval_evidence=source_interval_evidence,
            ),
        )
    candidates = tuple(sorted(temporal_candidates, key=lambda item: item.candidate_id))
    attachment_spans = tuple(
        span
        for candidate in candidates
        for span in candidate.evidence_spans
    )
    roles = {
        "fact": ("assertion",),
        "action": ("assertion",),
        "correction": ("replacement", "transition"),
        "retraction": ("transition",),
        "identity": ("transition",),
    }[proposal.operation_kind]
    return IndependentSourceAnalysis.create(
        candidate_id=proposal.candidate_id,
        source_id=source_id,
        source_digest=source_digest,
        predicate_id=proposal.predicate_id,
        operation_kind=proposal.operation_kind,
        source_authority_evidence=source_authority_evidence,
        # The legacy top-level assertion coordinate remains required by the
        # public contract; all parser evidence uses the prepared SourceSpanReference.
        assertion_span=SourceSpan(source_id=source_id, start=0, end=len(source_text)),
        parser_consensus=parser,
        identity_evidence=(),
        temporal_evidence=tuple(
            SourceTemporalEvidenceSet(
                temporal_role=role,
                candidates=candidates,
                attachment_spans=attachment_spans,
                attachment_consensus_digest=_digest("temporal-attachment"),
            )
            for role in roles
        ),
    )
