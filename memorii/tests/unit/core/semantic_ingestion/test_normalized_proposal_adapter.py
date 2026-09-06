"""Fast tests for the strict provider-to-normalized proposal boundary."""

from __future__ import annotations

import json
from hashlib import sha256

import memorii.core.semantic_ingestion as semantic_ingestion
import memorii.core.semantic_ingestion.contracts as semantic_contracts
import pytest
from memorii.core.memory_evolution.ingestion_contracts import decode_typed_value, encode_typed_value
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.semantic_ingestion.contracts import (
    EnvelopeFieldTextArtifactMappingProof,
    GovernanceCarrierArtifact,
    LanguageCandidate,
    MessageAdmissionCarrierSet,
    MessageAdmissionIdentity,
    PreAlignmentSemanticOperationSubject,
    PreAlignmentSemanticOperationSubjectSet,
    ProjectionTextSpan,
    ProposedActionRecordSelector,
    ProposedActionRoleBinding,
    ProposedActionRoleParticipant,
    ProposedActionState,
    ProposedAliasRecordSelector,
    ProposedCorrection,
    ProposedEntityObject,
    ProposedFact,
    ProposedLiteralObject,
    ProposedReferenceAssignment,
    ProposedRetraction,
    ProviderActionRecordSelector,
    ProviderActionRoleBinding,
    ProviderActionState,
    ProviderAliasRecordSelector,
    ProviderClaimRecordSelector,
    ProviderCorrection,
    ProviderEntityObject,
    ProviderFact,
    ProviderIdentityOperation,
    ProviderLiteralObject,
    ProviderMention,
    ProviderReferenceAssignment,
    ProviderRetraction,
    ProviderSemanticProposal,
    RequiredOutcomeScopeSet,
    RetainedSourceTextArtifact,
    RetainedSourceTextSpan,
    SegmentGovernanceBinding,
    SegmentGovernanceCarrierSet,
    SegmentLanguageResourceBinding,
    SegmentLanguageRoute,
    SegmentLocalTextArtifact,
    SegmentLocalTextSpan,
    SemanticContractCodecError,
    SemanticProjectionTextArtifact,
    SemanticProposal,
    SourceSpanReference,
    TypedLiteral,
    VerbatimTextArtifactMappingProof,
    contract_digest,
    decode_semantic_contract,
    encode_semantic_contract,
    expand_pre_alignment_subjects,
)
from memorii.core.semantic_ingestion.proposal_adapter import (
    ProposalNormalizationError,
    normalize_provider_proposal,
)
from memorii.domain.enums import SourceModality
from pydantic import ValidationError

SOURCE_ID = "source-a"
SOURCE_DIGEST = sha256(SOURCE_ID.encode()).hexdigest()
SEGMENT_ID = "segment-a"


def _hex(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _manual_subject_ctv(body: dict[str, object]) -> bytes:
    """A deliberately local CTV writer for the fixed subject-vector grammar only."""
    entries: list[list[object]] = []
    for key in sorted(body):
        value = body[key]
        entries.append([key, {"$type": "integer", "value": str(value)} if isinstance(value, int) else value])
    return json.dumps({"$type": "map", "entries": entries}, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def test_hand_authored_subject_ctv_vectors_cover_all_kinds_and_preimage_fields() -> None:
    common: dict[str, object] = {
        "source_id": "source-vector", "source_digest": "1" * 64,
        "proposal_id": "proposal-vector", "proposal_digest": "2" * 64,
        "segment_id": "segment-vector", "segment_language_route_digest": "3" * 64,
    }
    expected = {
        "fact": "26da965d2e23a9761cd82bcc8a593e24c68f0eca10ab98c65f09114c4f962d81",
        "correction": "2084879c99e99e4f443d21b9be06c93358eb4c738610ad0b50597c2c0fee9fbb",
        "retraction": "35a2c9dc99c6653ec781f6f227abcef4725c8cf80a26156421bbe42fc46b0f3f",
        "action_state": "3e75b5551049b136ec71162b8fdef64c6877ec250b4d06603ead738e531c7bc3",
        "identity": "6084fa26265e7bc1add961e57bc3244b6ba93a95a2f714e6cfecc277e23d1ac0",
    }
    for index, kind in enumerate(expected):
        body = {"kind": kind, **common, "proposal_member_index": index}
        encoded = _manual_subject_ctv(body)
        independently_computed = sha256(
            b"memorii.semantic-ingestion.pre-alignment-semantic-operation-subject.v1\0" + encoded
        ).hexdigest()
        assert independently_computed == expected[kind]
        subject = PreAlignmentSemanticOperationSubject.create(**body)
        assert subject.operation_id == expected[kind]
        assert sha256(
            b"wrong-domain\0" + encoded
        ).hexdigest() != expected[kind]
        for field, value in body.items():
            if field == "kind":
                continue
            mutated = {**body, field: value + 1 if isinstance(value, int) else f"x{value}"}
            assert _manual_subject_ctv(mutated) != encoded
        with pytest.raises(ValidationError, match="operation_id"):
            PreAlignmentSemanticOperationSubject(**body, operation_id="A" * 64)


def _span(
    label: str,
    start: int,
    end: int,
    *,
    source_id: str = SOURCE_ID,
    segment_id: str = SEGMENT_ID,
    projection_digest: str | None = None,
) -> SourceSpanReference:
    """Build a real, shared-artifact source span for one deterministic range."""
    content = _hex("whole source")
    retained = RetainedSourceTextArtifact.create(
        artifact_id="retained-source", content_digest=content, unicode_scalar_length=100,
    )
    projection = SemanticProjectionTextArtifact.create(
        artifact_id="projection-source", content_digest=content, unicode_scalar_length=100,
    )
    segment = SegmentLocalTextArtifact.create(
        artifact_id="segment-source", content_digest=content, unicode_scalar_length=100,
        projection_segment_id=segment_id,
    )
    digest = _hex(label)
    complete_retained_span = RetainedSourceTextSpan.create(
        artifact=retained, start=0, end=100, substring_digest=content,
    )
    complete_projection_span = ProjectionTextSpan.create(
        artifact=projection, start=0, end=100, substring_digest=content,
    )
    complete_segment_span = SegmentLocalTextSpan.create(
        artifact=segment, start=0, end=100, substring_digest=content,
    )
    projection_span = ProjectionTextSpan.create(
        artifact=projection, start=start, end=end, substring_digest=digest,
    )
    segment_span = SegmentLocalTextSpan.create(
        artifact=segment, start=start, end=end, substring_digest=digest,
    )
    proof = VerbatimTextArtifactMappingProof.create(
        retained_span=complete_retained_span, projection_span=complete_projection_span,
        segment_span=complete_segment_span,
    )
    return SourceSpanReference.create(
        source_id=source_id, projection_digest=projection_digest or projection.artifact_digest,
        projection_segment_id=segment_id, retained_text_artifact=retained,
        projection_span=projection_span, segment_local_span=segment_span,
        text_mapping_proof=proof, source_reference=label,
    )


def _envelope_mapping_proof() -> EnvelopeFieldTextArtifactMappingProof:
    """Exercise the non-verbatim member of the closed mapping-proof union."""
    decoded = b"abc"
    content_digest = sha256(decoded).hexdigest()
    retained = RetainedSourceTextArtifact.create(
        artifact_id="retained-envelope", content_digest=content_digest, unicode_scalar_length=3,
    )
    projection = SemanticProjectionTextArtifact.create(
        artifact_id="projection-envelope", content_digest=content_digest, unicode_scalar_length=3,
    )
    segment = SegmentLocalTextArtifact.create(
        artifact_id="segment-envelope", content_digest=content_digest, unicode_scalar_length=3,
        projection_segment_id=SEGMENT_ID,
    )
    projection_span = ProjectionTextSpan.create(
        artifact=projection, start=0, end=3, substring_digest=content_digest,
    )
    segment_span = SegmentLocalTextSpan.create(
        artifact=segment, start=0, end=3, substring_digest=content_digest,
    )
    encoded_field = b'"abc"'
    return EnvelopeFieldTextArtifactMappingProof.create(
        retained_artifact=retained, canonical_json_pointer="/body/text",
        canonical_encoded_field_value_bytes=encoded_field,
        canonical_encoded_field_value_digest=sha256(encoded_field).hexdigest(),
        decoded_content_bytes=decoded, decoded_content_text_digest=content_digest,
        projection_segment_id=SEGMENT_ID, projection_span=projection_span,
        segment_artifact=segment, segment_span=segment_span,
    )


def _authorities() -> tuple[SegmentGovernanceBinding, MessageAdmissionIdentity, GovernanceCarrierArtifact, SegmentLanguageRoute]:
    binding = SegmentGovernanceBinding.create(
        source_id=SOURCE_ID, segment_id=SEGMENT_ID,
        message_semantic_context_digest=_hex("context"), effective_scope_digest=_hex("scope"),
        authority_digest=_hex("authority"), data_classification="internal",
        modality=SourceModality.ASSERTION, provider_egress_decision_digest=_hex("egress"),
        egress_disposition="allow_verbatim",
    )
    governance = SegmentGovernanceCarrierSet.create(source_id=SOURCE_ID, bindings=(binding,))
    admission = MessageAdmissionIdentity.create(
        delivery_principal_binding_digest=_hex("principal"), authenticated_source_reference="source-ref",
        authenticated_source_reference_key_digest=_hex("source-ref"), message_bytes_digest=_hex("message"),
        segment_governance_binding_digest=binding.binding_digest,
    )
    admissions = MessageAdmissionCarrierSet.create(source_id=SOURCE_ID, identities=(admission,))
    scopes = RequiredOutcomeScopeSet.create(
        tenant_partition_id="tenant-a", scopes=(MemoryScope(user_id="user-a"),),
    )
    artifact = GovernanceCarrierArtifact.create(
        artifact_id="governance-a", atomic_generation=1, segment_governance=governance,
        message_admissions=admissions, required_outcome_scopes=scopes,
    )
    resource = SegmentLanguageResourceBinding.create(
        selected_language="en", proposal_capability_fingerprint=_hex("capability"),
        stanza_analyzer_manifest_digest=_hex("stanza"), spacy_analyzer_manifest_digest=_hex("spacy"),
        predicate_event_manifest_digest=_hex("predicate"), temporal_resolver_manifest_digest=_hex("temporal"),
    )
    segment_artifact = SegmentLocalTextArtifact.create(
        artifact_id="segment-source", content_digest=_hex("whole source"), unicode_scalar_length=100,
        projection_segment_id=SEGMENT_ID,
    )
    route = SegmentLanguageRoute.create(
        source_id=SOURCE_ID, source_digest=SOURCE_DIGEST, segment_id=SEGMENT_ID, parent_projection_segment_id=SEGMENT_ID,
        segment_text_artifact_id=segment_artifact.artifact_id,
        segment_text_artifact_digest=segment_artifact.artifact_digest,
        segment_text_content_digest=segment_artifact.content_digest, declared_language=None, candidates=(LanguageCandidate(language="en", probability_ppm=1_000_000, model_fingerprint=_hex("router-model")),),
        code_switch_spans=(), selected_language="en", decision="selected",
        minimum_probability_ppm=1, minimum_margin_ppm=1,
        routing_policy_fingerprint=_hex("routing"), router_manifest_fingerprint=_hex("router"),
        resource_binding=resource,
    )
    return binding, admission, artifact, route


def _route_for_segment_artifact(route: SegmentLanguageRoute, artifact: SegmentLocalTextArtifact) -> SegmentLanguageRoute:
    body = route.model_dump(mode="python", exclude={"route_digest"})
    body.update(
        segment_text_artifact_id=artifact.artifact_id,
        segment_text_artifact_digest=artifact.artifact_digest,
        segment_text_content_digest=artifact.content_digest,
    )
    return SegmentLanguageRoute.create(**body)


class _TypedQuoteResolver:
    """Typed resolver whose ranges make context and ownership enforcement observable."""

    def __init__(self, *, ambiguous: frozenset[str] = frozenset(), outside: frozenset[str] = frozenset()) -> None:
        self.ambiguous = ambiguous
        self.outside = outside
        self.calls: list[tuple[str, str, bool]] = []

    def __call__(self, quote: str, context: SourceSpanReference, owned: bool) -> SourceSpanReference:
        self.calls.append((quote, context.reference_digest, owned))
        if quote in self.ambiguous:
            raise ValueError("ambiguous")
        if quote == "entire source":
            return _span(quote, 0, 100)
        if quote.startswith("assert"):
            return _span(quote, 20, 40)
        if quote in self.outside:
            return _span(quote, 60, 61)
        return _span(quote, 21, 22)


class _TypedProjectionVerifier:
    """Fixture authority for synthetic spans without retained projection bytes."""

    def verify_quote(
        self, *, projection_digest: str, quote: str, span: SourceSpanReference
    ) -> None:
        if (
            span.projection_digest != projection_digest
            or span.projection_span.artifact.artifact_digest != projection_digest
            or span.source_reference != quote
        ):
            raise ValueError("unregistered projection or wrong synthetic quote")


def _normalize(
    provider: ProviderSemanticProposal,
    *,
    resolver: _TypedQuoteResolver | None = None,
    verifier: _TypedProjectionVerifier | None = None,
    route: SegmentLanguageRoute | None = None,
) -> SemanticProposal:
    binding, admission, artifact, route_from_authorities = _authorities()
    return normalize_provider_proposal(
        provider=provider, proposal_id="proposal-a", source_id=SOURCE_ID, source_digest=SOURCE_DIGEST,
        preparation_fingerprint=_hex("preparation"),
        segment_id=SEGMENT_ID, segment_governance=binding, message_admission_identity=admission,
        governance_carrier_artifact=artifact, owned_text=_span("owned", 10, 90),
        context_text=_span("entire source", 0, 100), language_route=route or route_from_authorities,
        proposer_fingerprint=_hex("proposer"), proposer_manifest_digest=_hex("manifest"),
        prompt_registration_digest=_hex("prompt"), semantic_request_fingerprint=_hex("request"),
        action_proposal_catalog_fingerprint=_hex("catalog"), attempt_payload_fingerprint=_hex("attempt"),
        originating_attempt_digest=_hex("originating-attempt"),
        diagnostics=(), resolve_quote=resolver or _TypedQuoteResolver(),
        projection_quote_verifier=verifier or _TypedProjectionVerifier(),
    )


def _mentions(*ids: str) -> tuple[ProviderMention, ...]:
    return tuple(ProviderMention(local_id=value, mention_quote=f"mention-{index}", mention_context_quote="entire source") for index, value in enumerate(ids))


def _fact(local_id: str = "fact", *, subject: str = "alice", object_ref: str = "globex") -> ProviderFact:
    return ProviderFact(
        local_id=local_id, predicate_id="works_for", subject_entity_ref=subject,
        object=ProviderEntityObject(entity_ref=object_ref), assertion_quote=f"assert-{local_id}",
        predicate_anchor_quote=f"predicate-{local_id}", polarity="positive", commitment="asserted",
        temporal_qualifier_quotes=("time-z", "time-a"),
    )


def _base_provider(**changes: object) -> ProviderSemanticProposal:
    body: dict[str, object] = {"mentions": _mentions("alice", "globex", "alice-new"), "facts": (_fact(),), "abstained": False}
    body.update(changes)
    return ProviderSemanticProposal(**body)


class _SourceBackedResolver:
    """Resolve exact source substrings once, constrained by the typed parent span."""

    def __init__(self, text: str) -> None:
        self.text = text

    def span(self, quote: str, start: int, end: int) -> SourceSpanReference:
        content = _hex(self.text)
        retained = RetainedSourceTextArtifact.create(artifact_id="retained-backed", content_digest=content, unicode_scalar_length=len(self.text))
        projection = SemanticProjectionTextArtifact.create(artifact_id="projection-backed", content_digest=content, unicode_scalar_length=len(self.text))
        segment = SegmentLocalTextArtifact.create(artifact_id="segment-backed", content_digest=content, unicode_scalar_length=len(self.text), projection_segment_id=SEGMENT_ID)
        complete_retained = RetainedSourceTextSpan.create(artifact=retained, start=0, end=len(self.text), substring_digest=content)
        complete_projection = ProjectionTextSpan.create(artifact=projection, start=0, end=len(self.text), substring_digest=content)
        complete_segment = SegmentLocalTextSpan.create(artifact=segment, start=0, end=len(self.text), substring_digest=content)
        substring = _hex(self.text[start:end])
        proof = VerbatimTextArtifactMappingProof.create(retained_span=complete_retained, projection_span=complete_projection, segment_span=complete_segment)
        return SourceSpanReference.create(
            source_id=SOURCE_ID, projection_digest=projection.artifact_digest,
            projection_segment_id=SEGMENT_ID, retained_text_artifact=retained,
            projection_span=ProjectionTextSpan.create(artifact=projection, start=start, end=end, substring_digest=substring),
            segment_local_span=SegmentLocalTextSpan.create(artifact=segment, start=start, end=end, substring_digest=substring),
            text_mapping_proof=proof, source_reference=quote,
        )

    def __call__(self, quote: str, context: SourceSpanReference, _owned: bool) -> SourceSpanReference:
        matches = []
        start = self.text.find(quote, context.projection_span.start, context.projection_span.end)
        while start >= 0 and start + len(quote) <= context.projection_span.end:
            matches.append(start)
            start = self.text.find(quote, start + 1, context.projection_span.end)
        if len(matches) != 1:
            raise ValueError("quote must occur exactly once in its context")
        return self.span(quote, matches[0], matches[0] + len(quote))

    def verify_quote(
        self, *, projection_digest: str, quote: str, span: SourceSpanReference
    ) -> None:
        if (
            span.projection_digest != projection_digest
            or span.projection_span.artifact.artifact_digest != projection_digest
            or self.text[span.projection_span.start : span.projection_span.end] != quote
            or span.projection_span.substring_digest
            != sha256(quote.encode("utf-8")).hexdigest()
        ):
            raise ValueError("quote is not the exact registered projection scalar slice")


def test_source_backed_resolver_enforces_unique_nested_and_owned_occurrences() -> None:
    text = "MENTION_ALICE MENTION_GLOBEX [assert-fact predicate-fact time-a time-z]"
    resolver = _SourceBackedResolver(text)
    binding, admission, artifact, route = _authorities()
    context = resolver.span(text, 0, len(text))
    owned_start = text.index("assert-fact")
    owned = resolver.span("assert-fact predicate-fact time-a time-z", owned_start, len(text) - 1)
    provider = ProviderSemanticProposal(
        mentions=(
            ProviderMention(local_id="alice", mention_quote="MENTION_ALICE", mention_context_quote=text),
            ProviderMention(local_id="globex", mention_quote="MENTION_GLOBEX", mention_context_quote=text),
        ),
        facts=(ProviderFact(local_id="fact", predicate_id="works_for", subject_entity_ref="alice", object=ProviderEntityObject(entity_ref="globex"), assertion_quote="assert-fact predicate-fact time-a time-z", predicate_anchor_quote="predicate-fact", polarity="positive", commitment="asserted", temporal_qualifier_quotes=("time-a", "time-z")),),
        abstained=False,
    )
    proposal = normalize_provider_proposal(
        provider=provider, proposal_id="proposal-backed", source_id=SOURCE_ID, source_digest=SOURCE_DIGEST,
        preparation_fingerprint=_hex("preparation"),
        segment_id=SEGMENT_ID, segment_governance=binding, message_admission_identity=admission,
        governance_carrier_artifact=artifact, owned_text=owned, context_text=context,
        language_route=_route_for_segment_artifact(route, context.segment_local_span.artifact),
        proposer_fingerprint=_hex("proposer"), proposer_manifest_digest=_hex("manifest"),
        prompt_registration_digest=_hex("prompt"), semantic_request_fingerprint=_hex("request"),
        action_proposal_catalog_fingerprint=_hex("catalog"), attempt_payload_fingerprint=_hex("attempt"),
        originating_attempt_digest=_hex("originating-attempt"),
        diagnostics=(), resolve_quote=resolver, projection_quote_verifier=resolver,
    )
    assert proposal.facts[0].predicate_anchor_span.source_reference == "predicate-fact"
    repeated = _SourceBackedResolver("repeat repeat")
    with pytest.raises(ValueError, match="exactly once"):
        repeated("repeat", repeated.span("repeat repeat", 0, 13), False)


def test_provider_permutations_normalize_to_identical_strict_bytes_without_local_ids() -> None:
    mentions = (
        ProviderMention(local_id="m-1", mention_quote="Alice", mention_context_quote="entire source"),
        ProviderMention(local_id="m-2", mention_quote="Globex", mention_context_quote="entire source"),
        ProviderMention(local_id="m-3", mention_quote="Alice II", mention_context_quote="entire source"),
    )
    first = _base_provider(mentions=mentions, facts=(_fact(subject="m-1", object_ref="m-2"),))
    second = _base_provider(mentions=tuple(reversed(mentions)), facts=(_fact(subject="m-1", object_ref="m-2"),))
    normalized_first, normalized_second = _normalize(first), _normalize(second)
    encoded = encode_semantic_contract(normalized_first)

    assert normalized_first == normalized_second
    assert normalized_first.context_text.projection_digest == normalized_first.context_text.projection_span.artifact.artifact_digest
    assert normalized_first.context_text.projection_digest != normalized_first.context_text.projection_span.artifact.content_digest
    assert sha256(b"memorii.semantic-ingestion.semantic-proposal.v1\0" + encode_typed_value(normalized_first.model_dump(mode="python", exclude={"proposal_digest"}))).hexdigest() == normalized_first.proposal_digest
    assert b"m-1" not in encoded and b"m-2" not in encoded
    assert decode_semantic_contract(encoded, SemanticProposal) == normalized_first
    envelope = decode_typed_value(encoded)
    assert isinstance(envelope, dict) and isinstance(envelope["payload"], dict)
    envelope["payload"]["legacy"] = True
    with pytest.raises(SemanticContractCodecError, match="validation failed"):
        decode_semantic_contract(encode_typed_value(envelope), SemanticProposal)
    with pytest.raises(SemanticContractCodecError, match="unsupported"):
        encode_semantic_contract(expand_pre_alignment_subjects(normalized_first)[0])


def test_resolver_rejects_ambiguous_cross_source_and_out_of_assertion_spans() -> None:
    with pytest.raises(ProposalNormalizationError, match="uniquely"):
        _normalize(_base_provider(), resolver=_TypedQuoteResolver(ambiguous=frozenset({"mention-0"})))

    class CrossSourceResolver(_TypedQuoteResolver):
        def __call__(self, quote: str, context: SourceSpanReference, owned: bool) -> SourceSpanReference:
            return _span(quote, 21, 22, source_id="other-source")

    with pytest.raises(ProposalNormalizationError, match="wrong source"):
        _normalize(_base_provider(), resolver=CrossSourceResolver())
    action = _action("action", "logical", "action anchor", "state outside", "branch anchor")
    with pytest.raises(ProposalNormalizationError, match="outside"):
        _normalize(_base_provider(action_states=(action,)), resolver=_TypedQuoteResolver(outside=frozenset({"state outside"})))
    branch_outside = _action("action", "logical", "action anchor", "state anchor", "branch outside")
    with pytest.raises(ProposalNormalizationError, match="outside"):
        _normalize(_base_provider(action_states=(branch_outside,)), resolver=_TypedQuoteResolver(outside=frozenset({"branch outside"})))


def test_package_root_exports_every_provider_and_normalized_slice_helper() -> None:
    names = (
        "ProviderEntityObject", "ProviderLiteralObject", "ProviderMention", "ProviderFact",
        "ProviderCorrection", "ProviderRetraction", "ProviderActionRoleBinding",
        "ProviderActionState", "ProviderClaimRecordSelector", "ProviderActionRecordSelector",
        "ProviderAliasRecordSelector", "ProviderReferenceAssignment", "ProviderIdentityOperation",
        "ProviderSemanticProposal", "ProposedMention", "ProposedEntityObject",
        "ProposedLiteralObject", "ProposedFact", "ProposedCorrection", "ProposedRetraction",
        "ProposedActionRoleParticipant", "ProposedActionRoleBinding", "ProposedActionState",
        "ProposedClaimRecordSelector", "ProposedActionRecordSelector", "ProposedAliasRecordSelector",
        "ProposedReferenceAssignment", "ProposedIdentityOperation", "SemanticProposal",
        "PreAlignmentSemanticOperationSubjectSet", "normalize_provider_proposal",
    )
    assert all(hasattr(semantic_ingestion, name) for name in names)


@pytest.mark.parametrize("missing_ref", ("missing", "fact"))
def test_entity_references_reject_missing_or_nonmention_local_ids(missing_ref: str) -> None:
    with pytest.raises(ProposalNormalizationError, match="missing or cross-kind"):
        _normalize(_base_provider(facts=(_fact(subject=missing_ref),)))


def test_literal_and_entity_objects_and_temporal_qualifiers_are_canonical() -> None:
    literal = _fact("literal").model_copy(update={"object": ProviderLiteralObject(literal_type="year", canonical_value="2026")})
    proposal = _normalize(_base_provider(facts=(_fact(), literal)))
    assert any(item.object.kind == "literal" for item in proposal.facts)
    assert proposal.facts[0].temporal_qualifier_spans == tuple(sorted(proposal.facts[0].temporal_qualifier_spans, key=lambda item: item.reference_digest))
    body = proposal.facts[0].model_dump(mode="python", exclude={"fact_digest"})
    body["temporal_qualifier_spans"] = (proposal.facts[0].temporal_qualifier_spans[0],) * 2
    with pytest.raises(ValidationError, match="canonical"):
        ProposedFact.create(**body)
    with pytest.raises(ValidationError, match="canonical"):
        _reseal(proposal, facts=tuple(reversed(proposal.facts)))


def _action(local_id: str, logical_id: str, anchor: str, state_anchor: str, branch_anchor: str) -> ProviderActionState:
    return ProviderActionState(
        local_id=local_id, logical_action_local_id=logical_id, action_anchor_quote=anchor,
        role_bindings=(ProviderActionRoleBinding(role_id="actor", endpoint_kind="actor", entity_refs=("alice",), grounding_quotes=("grounding",)),),
        state_id="started", state_anchor_quote=state_anchor, execution_branch_local_id=f"branch-{local_id}",
        execution_branch_anchor_quote=branch_anchor, assertion_quote=f"assert-{local_id}", temporal_qualifier_quotes=("action time",),
    )


def test_correction_retraction_actions_and_split_identity_use_exact_coordinates() -> None:
    first = _action("action-one", "logical", "action anchor one", "state one", "branch one")
    second = _action("action-two", "logical", "action anchor two", "state two", "branch two")
    identity = ProviderIdentityOperation(
        local_id="identity", operation="split", predecessor_entity_refs=("alice",), successor_entity_refs=("alice-new",),
        assertion_quote="assert-identity", identity_anchor_quote="identity anchor", reference_assignments=(
            ProviderReferenceAssignment(record_selector=ProviderClaimRecordSelector(fact_local_id="fact"), successor_entity_refs=("alice-new",), disposition="migrate_current", assertion_quote="assignment claim"),
            ProviderReferenceAssignment(record_selector=ProviderActionRecordSelector(logical_action_local_id="logical", action_anchor_quote="action anchor two"), successor_entity_refs=("alice-new",), disposition="preserve_historical", assertion_quote="assignment action"),
            ProviderReferenceAssignment(record_selector=ProviderAliasRecordSelector(alias_namespace="host", alias_anchor_quote="alias anchor"), successor_entity_refs=("alice-new",), disposition="share_by_explicit_evidence", assertion_quote="assignment alias"),
        ),
    )
    correction = ProviderCorrection(local_id="correction", corrected_fact=_fact("old"), replacement_fact=_fact("new"), assertion_quote="assert-correction", correction_anchor_quote="correction anchor")
    retraction = ProviderRetraction(local_id="retraction", retracted_fact=_fact("old-ret"), assertion_quote="assert-retraction", retraction_anchor_quote="retraction anchor")
    proposal = _normalize(_base_provider(corrections=(correction,), retractions=(retraction,), action_states=(first, second), identity_operations=(identity,)))

    assert len(proposal.action_states) == 2
    assert {item.logical_action_digest for item in proposal.action_states}.__len__() == 2
    assert all(item.execution_branch_digest for item in proposal.action_states)
    assert len(proposal.identity_operations[0].reference_assignments) == 3
    assert isinstance(proposal.action_states[0], ProposedActionState)
    subject_set = PreAlignmentSemanticOperationSubjectSet.create(proposal=proposal)
    assert [(item.kind, item.proposal_member_index) for item in subject_set.subjects] == [("fact", 0), ("correction", 0), ("retraction", 0), ("action_state", 0), ("action_state", 1), ("identity", 0)]
    assert decode_semantic_contract(encode_semantic_contract(subject_set), PreAlignmentSemanticOperationSubjectSet) == subject_set


def test_identity_assignments_are_split_only_and_abstention_has_no_subjects() -> None:
    with pytest.raises(ValidationError, match="paired"):
        ProviderActionState(local_id="action", logical_action_local_id="logical", action_anchor_quote="anchor", role_bindings=(), state_id="started", state_anchor_quote="state", execution_branch_local_id="branch", assertion_quote="assert")
    assignment = ProviderReferenceAssignment(record_selector=ProviderAliasRecordSelector(alias_namespace="host", alias_anchor_quote="alias"), successor_entity_refs=("alice-new",), disposition="migrate_current", assertion_quote="assignment")
    with pytest.raises(ValidationError, match="only splits"):
        _normalize(_base_provider(identity_operations=(ProviderIdentityOperation(local_id="identity", operation="merge", predecessor_entity_refs=("alice",), successor_entity_refs=("alice-new",), reference_assignments=(assignment,), assertion_quote="assert-identity", identity_anchor_quote="identity anchor"),)))
    abstained = _normalize(ProviderSemanticProposal(mentions=_mentions("alice"), abstained=True))
    assert abstained.status == "abstained"
    assert PreAlignmentSemanticOperationSubjectSet.create(proposal=abstained).subjects == ()


def test_semantic_proposal_requires_every_new_strict_authority_field() -> None:
    proposal = _normalize(_base_provider())
    payload = proposal.model_dump(mode="python")
    payload.pop("attempt_payload_fingerprint")
    with pytest.raises(ValidationError):
        SemanticProposal.model_validate(payload)
    payload = proposal.model_dump(mode="python")
    payload["segment_language_route_digest"] = proposal.language_route.route_digest
    with pytest.raises(ValidationError, match="extra"):
        SemanticProposal.model_validate(payload)


@pytest.mark.parametrize(
    "field",
    ("segment_text_artifact_id", "segment_text_artifact_digest", "segment_text_content_digest"),
)
def test_language_route_must_bind_the_exact_segment_artifact_at_normalization_and_reseal(field: str) -> None:
    proposal = _normalize(_base_provider())
    route_body = proposal.language_route.model_dump(mode="python", exclude={"route_digest"})
    route_body[field] = _hex(f"wrong-{field}")
    route = SegmentLanguageRoute.create(**route_body)
    with pytest.raises(ProposalNormalizationError, match="exact segment text artifact"):
        _normalize(_base_provider(), route=route)
    with pytest.raises(ValidationError, match="exact segment text artifact"):
        _reseal(proposal, language_route=route)


def test_slice_a_codec_matrix_rejects_extra_alias_digest_kind_and_legacy_envelopes() -> None:
    action = _action("codec-action", "codec-logical", "codec action", "codec state", "codec branch")
    correction = ProviderCorrection(local_id="codec-correction", corrected_fact=_fact("codec-old"), replacement_fact=_fact("codec-new"), assertion_quote="assert-correction", correction_anchor_quote="codec correction")
    retraction = ProviderRetraction(local_id="codec-retraction", retracted_fact=_fact("codec-retracted"), assertion_quote="assert-retraction", retraction_anchor_quote="codec retraction")
    identity = ProviderIdentityOperation(
        local_id="codec-identity", operation="split", predecessor_entity_refs=("alice",), successor_entity_refs=("alice-new",), assertion_quote="assert-identity", identity_anchor_quote="codec identity", reference_assignments=(
            ProviderReferenceAssignment(record_selector=ProviderClaimRecordSelector(fact_local_id="fact"), successor_entity_refs=("alice-new",), disposition="migrate_current", assertion_quote="codec assignment claim"),
            ProviderReferenceAssignment(record_selector=ProviderActionRecordSelector(logical_action_local_id="codec-logical", action_anchor_quote="codec action"), successor_entity_refs=("alice-new",), disposition="preserve_historical", assertion_quote="codec assignment action"),
            ProviderReferenceAssignment(record_selector=ProviderAliasRecordSelector(alias_namespace="codec", alias_anchor_quote="codec alias"), successor_entity_refs=("alice-new",), disposition="share_by_explicit_evidence", assertion_quote="codec assignment alias"),
        ),
    )
    proposal = _normalize(_base_provider(corrections=(correction,), retractions=(retraction,), action_states=(action,), identity_operations=(identity,)))
    subject_set = PreAlignmentSemanticOperationSubjectSet.create(proposal=proposal)
    fact = proposal.facts[0]
    values = (
        proposal.context_text.retained_text_artifact,
        proposal.context_text.projection_span.artifact,
        proposal.context_text.segment_local_span.artifact,
        RetainedSourceTextSpan.create(
            artifact=proposal.context_text.retained_text_artifact, start=0, end=100,
            substring_digest=proposal.context_text.retained_text_artifact.content_digest,
        ),
        proposal.context_text.projection_span,
        proposal.context_text.segment_local_span,
        proposal.context_text.text_mapping_proof,
        _envelope_mapping_proof(),
        proposal.context_text,
        TypedLiteral.create(literal_type="year", canonical_value="2026", unit=None),
        ProposedLiteralObject.create(
            value=TypedLiteral.create(literal_type="year", canonical_value="2026", unit=None),
        ),
        proposal.mentions[0],
        fact.object,
        fact,
        proposal.corrections[0],
        proposal.retractions[0],
        proposal.action_states[0].role_bindings[0].participants[0],
        proposal.action_states[0].role_bindings[0],
        proposal.action_states[0],
        *(assignment.record_selector for assignment in proposal.identity_operations[0].reference_assignments),
        *proposal.identity_operations[0].reference_assignments,
        proposal.identity_operations[0],
        proposal,
        subject_set,
    )
    for value in values:
        expected_type = type(value)
        raw = encode_semantic_contract(value)
        assert decode_semantic_contract(raw, expected_type) == value
        envelope = decode_typed_value(raw)
        assert isinstance(envelope, dict) and isinstance(envelope["payload"], dict)
        payload = envelope["payload"]
        payload["unexpected"] = True
        with pytest.raises(SemanticContractCodecError):
            decode_semantic_contract(encode_typed_value(envelope), expected_type)

        envelope = decode_typed_value(raw)
        assert isinstance(envelope, dict) and isinstance(envelope["payload"], dict)
        payload = envelope["payload"]
        required = next(name for name, field in expected_type.model_fields.items() if field.is_required())
        payload.pop(required)
        with pytest.raises(SemanticContractCodecError):
            decode_semantic_contract(encode_typed_value(envelope), expected_type)

        envelope = decode_typed_value(raw)
        assert isinstance(envelope, dict) and isinstance(envelope["payload"], dict)
        payload = envelope["payload"]
        payload[f"alias_{required}"] = payload.pop(required)
        with pytest.raises(SemanticContractCodecError):
            decode_semantic_contract(encode_typed_value(envelope), expected_type)

        envelope = decode_typed_value(raw)
        assert isinstance(envelope, dict) and isinstance(envelope["payload"], dict)
        payload = envelope["payload"]
        digest_field = value._digest_field
        payload[digest_field] = "A" * 64
        with pytest.raises(SemanticContractCodecError):
            decode_semantic_contract(encode_typed_value(envelope), expected_type)

        envelope = decode_typed_value(raw)
        assert isinstance(envelope, dict)
        envelope["kind"] = "unknown"
        with pytest.raises(SemanticContractCodecError):
            decode_semantic_contract(encode_typed_value(envelope), expected_type)

        envelope = decode_typed_value(raw)
        assert isinstance(envelope, dict)
        envelope["schema"] = "memorii.semantic-ingestion.contract-envelope.v0"
        with pytest.raises(SemanticContractCodecError):
            decode_semantic_contract(encode_typed_value(envelope), expected_type)

    envelope = decode_typed_value(encode_semantic_contract(proposal))
    assert isinstance(envelope, dict) and isinstance(envelope["payload"], dict)
    envelope["payload"].pop("diagnostics")
    with pytest.raises(SemanticContractCodecError, match="validation failed"):
        decode_semantic_contract(encode_typed_value(envelope), SemanticProposal)


def _reseal(proposal: SemanticProposal, **changes: object) -> SemanticProposal:
    body = proposal.model_dump(mode="python", exclude={"proposal_digest"})
    body.update(changes)
    return SemanticProposal.create(**body)


def test_whole_segment_mapping_allows_a_shorter_contained_source_reference() -> None:
    whole = _span("whole", 0, 100)
    contained = _span("contained", 20, 40)
    proposal = _normalize(_base_provider())
    fact_body = proposal.facts[0].model_dump(mode="python", exclude={"fact_digest"})
    fact_body["assertion_span"] = contained
    fact_body["predicate_anchor_span"] = _span("anchor", 21, 22)
    contained_fact = ProposedFact.create(**fact_body)

    assert contained.projection_span.start > whole.projection_span.start
    assert contained.projection_span.end < whole.projection_span.end
    assert _reseal(proposal, owned_text=whole, context_text=whole, facts=(contained_fact,)).facts == (contained_fact,)


def test_mapping_proof_rejects_unequal_relative_offsets_and_wrong_slice_artifacts() -> None:
    mismatched = _span("short", 20, 40)
    payload = mismatched.model_dump(mode="python", exclude={"reference_digest"})
    projection = mismatched.projection_span.model_copy(update={"start": 21, "end": 41})
    payload["projection_span"] = projection
    with pytest.raises(ValidationError, match="mapping|offset|span_digest"):
        SourceSpanReference.create(**payload)

    with pytest.raises(ValidationError, match="projection digest"):
        _span("foreign-projection", 20, 40, projection_digest=_hex("foreign-projection"))


def test_source_span_reference_binds_projection_artifact_digest() -> None:
    payload = _span("forged-projection", 20, 40).model_dump(
        mode="python", exclude={"reference_digest"}
    )
    payload["projection_digest"] = _hex("forged-projection-digest")
    with pytest.raises(ValidationError, match="projection digest"):
        SourceSpanReference.create(**payload)


def test_normalization_rejects_a_resolver_quote_that_is_not_the_projection_slice() -> None:
    text = "MENTION_ALICE MENTION_GLOBEX [assert-fact predicate-fact time-a time-z]"
    resolver = _SourceBackedResolver(text)

    class WrongSliceResolver(_SourceBackedResolver):
        def __call__(self, _quote: str, _context: SourceSpanReference, _owned: bool) -> SourceSpanReference:
            return self.span("M", 0, 1)

    wrong = WrongSliceResolver(text)
    binding, admission, artifact, route = _authorities()
    context = resolver.span(text, 0, len(text))
    owned_start = text.index("assert-fact")
    owned = resolver.span("assert-fact predicate-fact time-a time-z", owned_start, len(text) - 1)
    provider = ProviderSemanticProposal(
        mentions=(
            ProviderMention(local_id="alice", mention_quote="MENTION_ALICE", mention_context_quote=text),
            ProviderMention(local_id="globex", mention_quote="MENTION_GLOBEX", mention_context_quote=text),
        ),
        facts=(_fact(subject="alice", object_ref="globex").model_copy(update={
            "assertion_quote": "assert-fact predicate-fact time-a time-z",
            "predicate_anchor_quote": "predicate-fact",
        }),),
        abstained=False,
    )
    with pytest.raises(ProposalNormalizationError, match="immutable projection bytes"):
        normalize_provider_proposal(
            provider=provider, proposal_id="proposal-wrong-slice", source_id=SOURCE_ID,
            source_digest=SOURCE_DIGEST, preparation_fingerprint=_hex("preparation"), segment_id=SEGMENT_ID, segment_governance=binding,
            message_admission_identity=admission, governance_carrier_artifact=artifact,
            owned_text=owned, context_text=context,
            language_route=_route_for_segment_artifact(route, context.segment_local_span.artifact),
            proposer_fingerprint=_hex("proposer"), proposer_manifest_digest=_hex("manifest"),
            prompt_registration_digest=_hex("prompt"), semantic_request_fingerprint=_hex("request"),
            action_proposal_catalog_fingerprint=_hex("catalog"), attempt_payload_fingerprint=_hex("attempt"),
            originating_attempt_digest=_hex("originating-attempt"),
            diagnostics=(), resolve_quote=wrong, projection_quote_verifier=resolver,
        )


def test_subject_expansion_rejects_operation_id_collisions(monkeypatch: pytest.MonkeyPatch) -> None:
    proposal = _normalize(_base_provider(facts=(_fact("first"), _fact("second"))))
    original = semantic_contracts.contract_digest

    def colliding_digest(domain: bytes, value: object) -> str:
        if domain == b"memorii.semantic-ingestion.pre-alignment-semantic-operation-subject.v1":
            return "0" * 64
        return original(domain, value)

    monkeypatch.setattr(semantic_contracts, "contract_digest", colliding_digest)
    with pytest.raises(ValueError, match="unique operation ids"):
        expand_pre_alignment_subjects(proposal)


def test_direct_semantic_proposal_sealing_rejects_dangling_member_references() -> None:
    proposal = _normalize(_base_provider())
    fact = proposal.facts[0]
    fact_body = fact.model_dump(mode="python", exclude={"fact_digest"})
    fact_body["subject_mention_digest"] = "0" * 64
    with pytest.raises(ValidationError, match="mention|subject"):
        _reseal(proposal, facts=(ProposedFact.create(**fact_body),))

    fact_body = fact.model_dump(mode="python", exclude={"fact_digest"})
    fact_body["object"] = ProposedEntityObject.create(mention_digest="1" * 64)
    with pytest.raises(ValidationError, match="mention|object"):
        _reseal(proposal, facts=(ProposedFact.create(**fact_body),))

    fact_body = fact.model_dump(mode="python", exclude={"fact_digest"})
    fact_body["attributed_to_mention_digest"] = "2" * 64
    with pytest.raises(ValidationError, match="mention|attribution"):
        _reseal(proposal, facts=(ProposedFact.create(**fact_body),))


def test_direct_semantic_proposal_sealing_rejects_dangling_action_and_identity_members() -> None:
    action = _action("action", "logical", "action anchor", "state", "branch")
    identity = ProviderIdentityOperation(
        local_id="identity", operation="split", predecessor_entity_refs=("alice",),
        successor_entity_refs=("alice-new",), assertion_quote="assert-identity",
        identity_anchor_quote="identity anchor", reference_assignments=(
            ProviderReferenceAssignment(
                record_selector=ProviderClaimRecordSelector(fact_local_id="fact"),
                successor_entity_refs=("alice-new",), disposition="migrate_current",
                assertion_quote="assignment",
            ),
        ),
    )
    proposal = _normalize(_base_provider(action_states=(action,), identity_operations=(identity,)))
    action_state = proposal.action_states[0]
    binding = action_state.role_bindings[0]
    participant_body = binding.participants[0].model_dump(
        mode="python", exclude={"participant_digest"}
    )
    participant_body["mention_digest"] = "3" * 64
    participant = ProposedActionRoleParticipant.create(**participant_body)
    invalid_binding = ProposedActionRoleBinding.create(
        role_id=binding.role_id, endpoint_kind=binding.endpoint_kind, participants=(participant,)
    )
    action_body = action_state.model_dump(mode="python", exclude={"action_state_digest"})
    action_body["role_bindings"] = (invalid_binding,)
    action_body["logical_action_digest"] = contract_digest(
        b"memorii.semantic-ingestion.proposed-logical-action.v1",
        {"action_anchor_span": action_state.action_anchor_span, "role_bindings": (invalid_binding,)},
    )
    with pytest.raises(ValidationError, match="participant|mention"):
        _reseal(proposal, action_states=(ProposedActionState.create(**action_body),))

    identity_operation = proposal.identity_operations[0]
    identity_body = identity_operation.model_dump(mode="python", exclude={"identity_operation_digest"})
    identity_body["predecessor_mention_digests"] = ("4" * 64,)
    with pytest.raises(ValidationError, match="predecessor|mention"):
        _reseal(proposal, identity_operations=(identity_operation.__class__.create(**identity_body),))

    assignment = identity_operation.reference_assignments[0]
    assignment_body = assignment.model_dump(mode="python", exclude={"assignment_digest"})
    assignment_body["successor_mention_digests"] = ("5" * 64,)
    invalid_assignment = ProposedReferenceAssignment.create(**assignment_body)
    identity_body = identity_operation.model_dump(mode="python", exclude={"identity_operation_digest"})
    identity_body["reference_assignments"] = (invalid_assignment,)
    with pytest.raises(ValidationError, match="assignment|successor|mention"):
        _reseal(proposal, identity_operations=(identity_operation.__class__.create(**identity_body),))


def test_direct_semantic_proposal_sealing_rejects_foreign_or_out_of_context_spans() -> None:
    proposal = _normalize(_base_provider())
    fact_body = proposal.facts[0].model_dump(mode="python", exclude={"fact_digest"})
    fact_body["assertion_span"] = _span("foreign-source", 20, 40, source_id="other-source")
    fact_body["predicate_anchor_span"] = _span("anchor", 21, 22, source_id="other-source")
    with pytest.raises(ValidationError, match="source"):
        _reseal(proposal, facts=(ProposedFact.create(**fact_body),))

    fact_body = proposal.facts[0].model_dump(mode="python", exclude={"fact_digest"})
    fact_body["assertion_span"] = _span("foreign-segment", 20, 40, segment_id="other-segment")
    fact_body["predicate_anchor_span"] = _span("anchor", 21, 22, segment_id="other-segment")
    with pytest.raises(ValidationError, match="segment"):
        _reseal(proposal, facts=(ProposedFact.create(**fact_body),))

    fact_body = proposal.facts[0].model_dump(mode="python", exclude={"fact_digest"})
    fact_body["assertion_span"] = _span("outside", 91, 99)
    fact_body["predicate_anchor_span"] = _span("outside-anchor", 92, 93)
    with pytest.raises(ValidationError, match="context|owned"):
        _reseal(proposal, facts=(ProposedFact.create(**fact_body),))


def _rehash(value):
    body = value.model_dump(mode="python", exclude={value._digest_field})
    return value.model_copy(update={value._digest_field: contract_digest(value._digest_domain, body)})


def test_direct_semantic_proposal_sealing_preserves_assertion_local_containment() -> None:
    action = _action("action", "logical", "action anchor", "state", "branch")
    identity = ProviderIdentityOperation(
        local_id="identity", operation="split", predecessor_entity_refs=("alice",),
        successor_entity_refs=("alice-new",), assertion_quote="assert-identity",
        identity_anchor_quote="identity anchor", reference_assignments=(
            ProviderReferenceAssignment(
                record_selector=ProviderAliasRecordSelector(alias_namespace="host", alias_anchor_quote="alias"),
                successor_entity_refs=("alice-new",), disposition="migrate_current", assertion_quote="assignment",
            ),
            ProviderReferenceAssignment(
                record_selector=ProviderActionRecordSelector(
                    logical_action_local_id="logical", action_anchor_quote="action anchor"
                ),
                successor_entity_refs=("alice-new",), disposition="preserve_historical", assertion_quote="assignment",
            ),
        ),
    )
    correction = ProviderCorrection(
        local_id="correction", corrected_fact=_fact("old"), replacement_fact=_fact("new"),
        assertion_quote="assert-correction", correction_anchor_quote="correction anchor",
    )
    retraction = ProviderRetraction(
        local_id="retraction", retracted_fact=_fact("old-ret"), assertion_quote="assert-retraction",
        retraction_anchor_quote="retraction anchor",
    )
    proposal = _normalize(_base_provider(
        corrections=(correction,), retractions=(retraction,), action_states=(action,), identity_operations=(identity,)
    ))
    outside_anchor = _span("outside-anchor", 42, 43)

    invalid_fact = _rehash(proposal.facts[0].model_copy(update={"predicate_anchor_span": outside_anchor}))
    with pytest.raises(ValidationError, match="predicate.*assertion"):
        _reseal(proposal, facts=(invalid_fact,))

    invalid_fact = _rehash(proposal.facts[0].model_copy(update={"temporal_qualifier_spans": (outside_anchor,)}))
    with pytest.raises(ValidationError, match="temporal qualifier.*assertion"):
        _reseal(proposal, facts=(invalid_fact,))

    invalid_correction = _rehash(
        proposal.corrections[0].model_copy(update={"correction_anchor_span": outside_anchor})
    )
    with pytest.raises(ValidationError, match="correction.*anchor.*assertion"):
        _reseal(proposal, corrections=(invalid_correction,))

    invalid_retraction = _rehash(
        proposal.retractions[0].model_copy(update={"retraction_anchor_span": outside_anchor})
    )
    with pytest.raises(ValidationError, match="retraction.*anchor.*assertion"):
        _reseal(proposal, retractions=(invalid_retraction,))

    action_member = proposal.action_states[0]
    invalid_action = action_member.model_copy(update={
        "action_anchor_span": outside_anchor,
        "logical_action_digest": contract_digest(
            b"memorii.semantic-ingestion.proposed-logical-action.v1",
            {"action_anchor_span": outside_anchor, "role_bindings": action_member.role_bindings},
        ),
    })
    invalid_action = _rehash(invalid_action)
    with pytest.raises(ValidationError, match="action.*anchor.*assertion"):
        _reseal(proposal, action_states=(invalid_action,))

    invalid_action = _rehash(action_member.model_copy(update={"state_anchor_span": outside_anchor}))
    with pytest.raises(ValidationError, match="action.*state.*assertion"):
        _reseal(proposal, action_states=(invalid_action,))

    invalid_action = action_member.model_copy(update={
        "execution_branch_span": outside_anchor,
        "execution_branch_digest": contract_digest(
            b"memorii.semantic-ingestion.proposed-execution-branch.v1",
            {"execution_branch_span": outside_anchor},
        ),
    })
    with pytest.raises(ValidationError, match="execution branch.*assertion"):
        _reseal(proposal, action_states=(_rehash(invalid_action),))

    invalid_action = _rehash(action_member.model_copy(update={"temporal_qualifier_spans": (outside_anchor,)}))
    with pytest.raises(ValidationError, match="temporal qualifier.*assertion"):
        _reseal(proposal, action_states=(invalid_action,))

    binding = action_member.role_bindings[0]
    participant = _rehash(binding.participants[0].model_copy(update={"grounding_spans": (outside_anchor,)}))
    invalid_binding = _rehash(binding.model_copy(update={"participants": (participant,)}))
    invalid_action = action_member.model_copy(update={"role_bindings": (invalid_binding,)})
    invalid_action = invalid_action.model_copy(update={"logical_action_digest": contract_digest(
        b"memorii.semantic-ingestion.proposed-logical-action.v1",
        {"action_anchor_span": invalid_action.action_anchor_span, "role_bindings": invalid_action.role_bindings},
    )})
    with pytest.raises(ValidationError, match="participant grounding.*assertion"):
        _reseal(proposal, action_states=(_rehash(invalid_action),))

    identity_member = proposal.identity_operations[0]
    invalid_identity = _rehash(identity_member.model_copy(update={"identity_anchor_span": outside_anchor}))
    with pytest.raises(ValidationError, match="identity.*anchor.*assertion"):
        _reseal(proposal, identity_operations=(invalid_identity,))

    assignment = next(
        value for value in identity_member.reference_assignments
        if isinstance(value.record_selector, ProposedAliasRecordSelector)
    )
    selector = _rehash(assignment.record_selector.model_copy(update={"alias_anchor_span": outside_anchor}))
    invalid_assignment = _rehash(assignment.model_copy(update={"record_selector": selector}))
    invalid_identity = _rehash(identity_member.model_copy(update={"reference_assignments": (invalid_assignment,)}))
    with pytest.raises(ValidationError, match="alias selector.*assignment assertion"):
        _reseal(proposal, identity_operations=(invalid_identity,))

    invalid_assignment = _rehash(assignment.model_copy(update={"assertion_span": outside_anchor}))
    invalid_identity = _rehash(identity_member.model_copy(update={"reference_assignments": (invalid_assignment,)}))
    with pytest.raises(ValidationError, match="assignment.*must lie within its assertion"):
        _reseal(proposal, identity_operations=(invalid_identity,))

    action_assignment = next(
        value for value in identity_member.reference_assignments
        if isinstance(value.record_selector, ProposedActionRecordSelector)
    )
    action_selector = _rehash(action_assignment.record_selector.model_copy(update={"action_anchor_span": outside_anchor}))
    invalid_assignment = _rehash(action_assignment.model_copy(update={"record_selector": action_selector}))
    remaining = next(value for value in identity_member.reference_assignments if value != action_assignment)
    assignments = tuple(sorted(
        (remaining, invalid_assignment), key=lambda value: (value.record_selector.selector_digest, value.assignment_digest)
    ))
    invalid_identity = _rehash(identity_member.model_copy(update={"reference_assignments": assignments}))
    with pytest.raises(ValidationError, match="action selector.*assignment assertion"):
        _reseal(proposal, identity_operations=(invalid_identity,))


def test_correction_and_retraction_facts_keep_independent_valid_assertions() -> None:
    correction = ProviderCorrection(
        local_id="correction", corrected_fact=_fact("old"), replacement_fact=_fact("new"),
        assertion_quote="assert-correction", correction_anchor_quote="correction anchor",
    )
    retraction = ProviderRetraction(
        local_id="retraction", retracted_fact=_fact("old-ret"), assertion_quote="assert-retraction",
        retraction_anchor_quote="retraction anchor",
    )
    proposal = _normalize(_base_provider(corrections=(correction,), retractions=(retraction,)))

    fact_body = proposal.corrections[0].corrected_fact.model_dump(
        mode="python", exclude={"fact_digest"}
    )
    independent_assertion = _span("independent-fact-assertion", 50, 60)
    fact_body.update(
        assertion_span=independent_assertion,
        predicate_anchor_span=_span("independent-fact-predicate", 51, 52),
        temporal_qualifier_spans=tuple(
            sorted(
                (_span("independent-time-a", 53, 54), _span("independent-time-b", 55, 56)),
                key=lambda span: span.reference_digest,
            )
        ),
    )
    independent_fact = ProposedFact.create(**fact_body)

    correction_body = proposal.corrections[0].model_dump(
        mode="python", exclude={"correction_digest"}
    )
    correction_body["corrected_fact"] = independent_fact
    independent_correction = ProposedCorrection.create(**correction_body)

    retraction_body = proposal.retractions[0].model_dump(
        mode="python", exclude={"retraction_digest"}
    )
    retraction_body["retracted_fact"] = independent_fact
    independent_retraction = ProposedRetraction.create(**retraction_body)

    resealed = _reseal(
        proposal,
        corrections=(independent_correction,),
        retractions=(independent_retraction,),
    )
    assert resealed.corrections[0].corrected_fact.assertion_span == independent_assertion
    assert resealed.retractions[0].retracted_fact.assertion_span == independent_assertion


def _recomputed_invalid_proposal(proposal: SemanticProposal, **changes: object) -> SemanticProposal:
    candidate = proposal.model_copy(update=changes)
    body = candidate.model_dump(mode="python", exclude={"proposal_digest"})
    return candidate.model_copy(update={
        "proposal_digest": contract_digest(b"memorii.semantic-ingestion.semantic-proposal.v1", body)
    })


@pytest.mark.parametrize("field", ("corrections", "retractions", "action_states", "identity_operations"))
def test_recomputed_proposal_digest_does_not_mask_noncanonical_operation_order(field: str) -> None:
    def correction(local_id: str) -> ProviderCorrection:
        return ProviderCorrection(
            local_id=local_id, corrected_fact=_fact(f"{local_id}-old"), replacement_fact=_fact(f"{local_id}-new"),
            assertion_quote=f"assert-{local_id}", correction_anchor_quote=f"anchor-{local_id}",
        )

    def retraction(local_id: str) -> ProviderRetraction:
        return ProviderRetraction(
            local_id=local_id, retracted_fact=_fact(f"{local_id}-fact"), assertion_quote=f"assert-{local_id}",
            retraction_anchor_quote=f"anchor-{local_id}",
        )

    def identity(local_id: str) -> ProviderIdentityOperation:
        return ProviderIdentityOperation(
            local_id=local_id, operation="alias", predecessor_entity_refs=("alice",), successor_entity_refs=("alice-new",),
            assertion_quote=f"assert-{local_id}", identity_anchor_quote=f"anchor-{local_id}",
        )
    proposal = _normalize(_base_provider(
        corrections=(correction("correction-a"), correction("correction-b")),
        retractions=(retraction("retraction-a"), retraction("retraction-b")),
        action_states=(
            _action("action-a", "logical-a", "anchor-a", "state-a", "branch-a"),
            _action("action-b", "logical-b", "anchor-b", "state-b", "branch-b"),
        ),
        identity_operations=(identity("identity-a"), identity("identity-b")),
    ))
    invalid = _recomputed_invalid_proposal(proposal, **{field: tuple(reversed(getattr(proposal, field)))})
    with pytest.raises(ValidationError, match="canonical"):
        SemanticProposal.model_validate(invalid.model_dump(mode="python"))


def test_recomputed_nested_digest_does_not_mask_noncanonical_temporal_order() -> None:
    proposal = _normalize(_base_provider())
    fact = proposal.facts[0]
    invalid_fact = _rehash(fact.model_copy(update={
        "temporal_qualifier_spans": tuple(reversed(fact.temporal_qualifier_spans))
    }))
    invalid = _recomputed_invalid_proposal(proposal, facts=(invalid_fact,))
    with pytest.raises(ValidationError, match="temporal qualifiers.*canonical"):
        SemanticProposal.model_validate(invalid.model_dump(mode="python"))


def test_recomputed_nested_digests_do_not_mask_role_or_identity_tuple_order() -> None:
    action = ProviderActionState(
        local_id="action", logical_action_local_id="logical", action_anchor_quote="action anchor",
        role_bindings=(
            ProviderActionRoleBinding(role_id="actor", endpoint_kind="actor", entity_refs=("alice", "globex"), grounding_quotes=("grounding-a", "grounding-b")),
            ProviderActionRoleBinding(role_id="object", endpoint_kind="object", entity_refs=("alice-new",), grounding_quotes=("grounding-c",)),
        ),
        state_id="started", state_anchor_quote="state", assertion_quote="assert-action",
    )
    identity = ProviderIdentityOperation(
        local_id="identity", operation="split", predecessor_entity_refs=("alice", "globex"),
        successor_entity_refs=("alice-new", "globex"), assertion_quote="assert-identity",
        identity_anchor_quote="identity anchor", reference_assignments=(
            ProviderReferenceAssignment(record_selector=ProviderClaimRecordSelector(fact_local_id="fact"), successor_entity_refs=("alice-new",), disposition="migrate_current", assertion_quote="assignment-a"),
            ProviderReferenceAssignment(record_selector=ProviderClaimRecordSelector(fact_local_id="second"), successor_entity_refs=("alice-new",), disposition="preserve_historical", assertion_quote="assignment-b"),
        ),
    )
    proposal = _normalize(_base_provider(
        facts=(_fact(), _fact("second")), action_states=(action,), identity_operations=(identity,)
    ))
    action_member = proposal.action_states[0]
    role_binding = action_member.role_bindings[0]
    invalid_participants = _rehash(role_binding.model_copy(update={
        "participants": tuple(reversed(role_binding.participants))
    }))
    invalid_action = action_member.model_copy(update={
        "role_bindings": (invalid_participants, *action_member.role_bindings[1:]),
    })
    invalid_action = invalid_action.model_copy(update={"logical_action_digest": contract_digest(
        b"memorii.semantic-ingestion.proposed-logical-action.v1",
        {"action_anchor_span": invalid_action.action_anchor_span, "role_bindings": invalid_action.role_bindings},
    )})
    invalid = _recomputed_invalid_proposal(proposal, action_states=(_rehash(invalid_action),))
    with pytest.raises(ValidationError, match="role participants.*canonical"):
        SemanticProposal.model_validate(invalid.model_dump(mode="python"))

    identity_member = proposal.identity_operations[0]
    invalid_identity = _rehash(identity_member.model_copy(update={
        "predecessor_mention_digests": tuple(reversed(identity_member.predecessor_mention_digests)),
        "successor_mention_digests": tuple(reversed(identity_member.successor_mention_digests)),
        "reference_assignments": tuple(reversed(identity_member.reference_assignments)),
    }))
    invalid = _recomputed_invalid_proposal(proposal, identity_operations=(invalid_identity,))
    with pytest.raises(ValidationError, match="identity members|reference assignments"):
        SemanticProposal.model_validate(invalid.model_dump(mode="python"))
