"""Deterministic conversion of transient provider proposal wires to sealed contracts."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from memorii.core.semantic_ingestion.contracts import (
    GovernanceCarrierArtifact,
    MessageAdmissionIdentity,
    ProposedActionRecordSelector,
    ProposedActionRoleBinding,
    ProposedActionRoleParticipant,
    ProposedActionState,
    ProposedAliasRecordSelector,
    ProposedClaimRecordSelector,
    ProposedCorrection,
    ProposedEntityObject,
    ProposedFact,
    ProposedIdentityOperation,
    ProposedLiteralObject,
    ProposedMention,
    ProposedReferenceAssignment,
    ProposedRetraction,
    ProviderActionRecordSelector,
    ProviderAliasRecordSelector,
    ProviderClaimRecordSelector,
    ProviderEntityObject,
    ProviderFact,
    ProviderLiteralObject,
    ProviderSemanticProposal,
    SegmentGovernanceBinding,
    SegmentLanguageRoute,
    SemanticProposal,
    SourceSpanReference,
    TypedLiteral,
    contract_digest,
)


class ProposalNormalizationError(ValueError):
    """Provider proposal cannot be resolved without guessing."""


SpanResolver = Callable[[str, SourceSpanReference, bool], SourceSpanReference]


class ProjectionQuoteVerificationAuthority(Protocol):
    """Verifies a quote against registered immutable projection bytes."""

    def verify_quote(
        self,
        *,
        projection_digest: str,
        quote: str,
        span: SourceSpanReference,
    ) -> None:
        """Reject unless ``span`` is the exact scalar slice of the registered projection."""


def normalize_provider_proposal(
    *,
    provider: ProviderSemanticProposal,
    proposal_id: str,
    source_id: str,
    source_digest: str,
    preparation_fingerprint: str,
    segment_id: str,
    segment_governance: SegmentGovernanceBinding,
    message_admission_identity: MessageAdmissionIdentity | None,
    governance_carrier_artifact: GovernanceCarrierArtifact,
    owned_text: SourceSpanReference,
    context_text: SourceSpanReference,
    language_route: SegmentLanguageRoute,
    proposer_fingerprint: str,
    proposer_manifest_digest: str,
    prompt_registration_digest: str,
    semantic_request_fingerprint: str,
    action_proposal_catalog_fingerprint: str,
    attempt_payload_fingerprint: str,
    originating_attempt_digest: str,
    diagnostics: tuple[str, ...],
    resolve_quote: SpanResolver,
    projection_quote_verifier: ProjectionQuoteVerificationAuthority,
) -> SemanticProposal:
    """Resolve provider-local references only through the supplied source authority.

    The adapter is intentionally unable to manufacture governance, routing, or
    text coordinates.  Every returned resolver value is checked before it can
    become a normalized member.
    """
    _validate_authorities(
        source_id=source_id,
        source_digest=source_digest,
        segment_id=segment_id,
        segment_governance=segment_governance,
        message_admission_identity=message_admission_identity,
        governance_carrier_artifact=governance_carrier_artifact,
        owned_text=owned_text,
        context_text=context_text,
        language_route=language_route,
    )

    def resolve(text: str, context: SourceSpanReference, *, owned: bool = False) -> SourceSpanReference:
        try:
            resolved = resolve_quote(text, context, owned)
        except ValueError as exc:
            raise ProposalNormalizationError("quote must resolve uniquely in the declared context") from exc
        _validate_resolved_span(
            resolved=resolved,
            context=context,
            source_id=source_id,
            segment_id=segment_id,
            projection_digest=context_text.projection_digest,
            owned=owned,
            owned_text=owned_text,
        )
        try:
            projection_quote_verifier.verify_quote(
                projection_digest=context_text.projection_digest,
                quote=text,
                span=resolved,
            )
        except ValueError as exc:
            raise ProposalNormalizationError(
                "resolved quote does not match the registered immutable projection bytes"
            ) from exc
        return resolved

    mentions: dict[str, ProposedMention] = {}
    for item in provider.mentions:
        mention_context = resolve(item.mention_context_quote, context_text)
        mention_span = resolve(item.mention_quote, mention_context)
        mentions[item.local_id] = ProposedMention.create(
            mention_span=mention_span, proposed_type=item.proposed_type
        )

    def entity(local_id: str) -> str:
        if local_id not in mentions:
            raise ProposalNormalizationError("entity reference is missing or cross-kind")
        return mentions[local_id].mention_digest

    def obj(value: ProviderEntityObject | ProviderLiteralObject):
        if isinstance(value, ProviderEntityObject):
            return ProposedEntityObject.create(kind="entity", mention_digest=entity(value.entity_ref))
        return ProposedLiteralObject.create(
            kind="literal",
            value=TypedLiteral.create(
                literal_type=value.literal_type,
                canonical_value=value.canonical_value,
                unit=value.unit,
            )
        )

    def fact(value: ProviderFact) -> ProposedFact:
        assertion = resolve(value.assertion_quote, context_text)
        return ProposedFact.create(
            kind="fact",
            predicate_id=value.predicate_id,
            subject_mention_digest=entity(value.subject_entity_ref),
            object=obj(value.object),
            assertion_span=assertion,
            predicate_anchor_span=resolve(value.predicate_anchor_quote, assertion, owned=True),
            polarity=value.polarity,
            commitment=value.commitment,
            attributed_to_mention_digest=(
                None if value.attributed_to_entity_ref is None else entity(value.attributed_to_entity_ref)
            ),
            temporal_qualifier_spans=tuple(
                sorted(
                    (resolve(item, assertion) for item in value.temporal_qualifier_quotes),
                    key=lambda span: span.reference_digest,
                )
            ),
        )

    facts_by_local = {item.local_id: fact(item) for item in provider.facts}
    corrections = []
    for item in provider.corrections:
        assertion = resolve(item.assertion_quote, context_text)
        corrections.append(
            ProposedCorrection.create(
                kind="correction",
                corrected_fact=fact(item.corrected_fact),
                replacement_fact=fact(item.replacement_fact),
                assertion_span=assertion,
                correction_anchor_span=resolve(item.correction_anchor_quote, assertion, owned=True),
            )
        )
    retractions = []
    for item in provider.retractions:
        assertion = resolve(item.assertion_quote, context_text)
        retractions.append(
            ProposedRetraction.create(
                kind="retraction",
                retracted_fact=fact(item.retracted_fact),
                assertion_span=assertion,
                retraction_anchor_span=resolve(item.retraction_anchor_quote, assertion, owned=True),
            )
        )

    actions_by_coordinate: dict[tuple[str, str], ProposedActionState] = {}
    actions: list[ProposedActionState] = []
    for item in provider.action_states:
        assertion = resolve(item.assertion_quote, context_text)
        action_anchor = resolve(item.action_anchor_quote, assertion, owned=True)
        coordinate = (item.logical_action_local_id, action_anchor.reference_digest)
        if coordinate in actions_by_coordinate:
            raise ProposalNormalizationError("duplicate logical action and anchor coordinate")
        bindings = []
        for binding in item.role_bindings:
            if len(binding.entity_refs) != len(binding.grounding_quotes):
                raise ProposalNormalizationError("action role references and grounding quotes must pair")
            participants = tuple(
                sorted(
                    (
                        ProposedActionRoleParticipant.create(
                            mention_digest=entity(ref),
                            grounding_spans=(resolve(grounding, assertion),),
                        )
                        for ref, grounding in zip(binding.entity_refs, binding.grounding_quotes, strict=True)
                    ),
                    key=lambda value: (value.mention_digest, value.participant_digest),
                )
            )
            bindings.append(
                ProposedActionRoleBinding.create(
                    role_id=binding.role_id, endpoint_kind=binding.endpoint_kind, participants=participants
                )
            )
        canonical_bindings = tuple(
            sorted(bindings, key=lambda value: (value.role_id, value.endpoint_kind, value.binding_digest))
        )
        branch = (
            None
            if item.execution_branch_anchor_quote is None
            else resolve(item.execution_branch_anchor_quote, assertion)
        )
        branch_digest = (
            None
            if branch is None
            else contract_digest(
                b"memorii.semantic-ingestion.proposed-execution-branch.v1",
                {"execution_branch_span": branch},
            )
        )
        logical_digest = contract_digest(
            b"memorii.semantic-ingestion.proposed-logical-action.v1",
            {"action_anchor_span": action_anchor, "role_bindings": canonical_bindings},
        )
        normalized = ProposedActionState.create(
            kind="action_state",
            action_anchor_span=action_anchor,
            logical_action_digest=logical_digest,
            role_bindings=canonical_bindings,
            state_id=item.state_id,
            state_anchor_span=resolve(item.state_anchor_quote, assertion, owned=True),
            execution_branch_span=branch,
            execution_branch_digest=branch_digest,
            assertion_span=assertion,
            temporal_qualifier_spans=tuple(
                sorted(
                    (resolve(value, assertion) for value in item.temporal_qualifier_quotes),
                    key=lambda span: span.reference_digest,
                )
            ),
        )
        actions_by_coordinate[coordinate] = normalized
        actions.append(normalized)

    identities = []
    for item in provider.identity_operations:
        assertion = resolve(item.assertion_quote, context_text)
        assignments = []
        for assignment in item.reference_assignments:
            assignment_assertion = resolve(assignment.assertion_quote, assertion)
            selector = assignment.record_selector
            if isinstance(selector, ProviderClaimRecordSelector):
                if selector.fact_local_id not in facts_by_local:
                    raise ProposalNormalizationError("claim selector must name one top-level fact")
                resolved_selector = ProposedClaimRecordSelector.create(
                    kind="claim",
                    fact_digest=facts_by_local[selector.fact_local_id].fact_digest
                )
            elif isinstance(selector, ProviderActionRecordSelector):
                selector_anchor = resolve(selector.action_anchor_quote, assignment_assertion, owned=True)
                action = actions_by_coordinate.get(
                    (selector.logical_action_local_id, selector_anchor.reference_digest)
                )
                if action is None:
                    raise ProposalNormalizationError("action selector must name one exact action coordinate")
                resolved_selector = ProposedActionRecordSelector.create(
                    kind="action",
                    logical_action_digest=action.logical_action_digest,
                    action_anchor_span=action.action_anchor_span,
                )
            else:
                assert isinstance(selector, ProviderAliasRecordSelector)
                resolved_selector = ProposedAliasRecordSelector.create(
                    kind="alias",
                    alias_namespace=selector.alias_namespace,
                    alias_anchor_span=resolve(selector.alias_anchor_quote, assignment_assertion),
                )
            assignments.append(
                ProposedReferenceAssignment.create(
                    record_selector=resolved_selector,
                    successor_mention_digests=tuple(sorted(entity(value) for value in assignment.successor_entity_refs)),
                    disposition=assignment.disposition,
                    assertion_span=assignment_assertion,
                )
            )
        identities.append(
            ProposedIdentityOperation.create(
                kind="identity",
                operation=item.operation,
                predecessor_mention_digests=tuple(sorted(entity(value) for value in item.predecessor_entity_refs)),
                successor_mention_digests=tuple(sorted(entity(value) for value in item.successor_entity_refs)),
                reference_assignments=tuple(
                    sorted(assignments, key=lambda value: (value.record_selector.selector_digest, value.assignment_digest))
                ),
                assertion_span=assertion,
                identity_anchor_span=resolve(item.identity_anchor_quote, assertion, owned=True),
            )
        )

    return SemanticProposal.create(
        proposal_id=proposal_id,
        source_id=source_id,
        source_digest=source_digest,
        preparation_fingerprint=preparation_fingerprint,
        segment_id=segment_id,
        segment_governance=segment_governance,
        message_admission_identity=message_admission_identity,
        governance_carrier_artifact=governance_carrier_artifact,
        owned_text=owned_text,
        context_text=context_text,
        language_route=language_route,
        proposer_fingerprint=proposer_fingerprint,
        proposer_manifest_digest=proposer_manifest_digest,
        prompt_registration_digest=prompt_registration_digest,
        semantic_request_fingerprint=semantic_request_fingerprint,
        action_proposal_catalog_fingerprint=action_proposal_catalog_fingerprint,
        attempt_payload_fingerprint=attempt_payload_fingerprint,
        originating_attempt_digest=originating_attempt_digest,
        mentions=tuple(sorted(mentions.values(), key=lambda value: (value.mention_span.reference_digest, value.mention_digest))),
        facts=tuple(sorted(facts_by_local.values(), key=lambda value: (value.predicate_anchor_span.reference_digest, value.assertion_span.reference_digest, value.fact_digest))),
        corrections=tuple(sorted(corrections, key=lambda value: (value.correction_anchor_span.reference_digest, value.assertion_span.reference_digest, value.correction_digest))),
        retractions=tuple(sorted(retractions, key=lambda value: (value.retraction_anchor_span.reference_digest, value.assertion_span.reference_digest, value.retraction_digest))),
        action_states=tuple(sorted(actions, key=lambda value: (value.action_anchor_span.reference_digest, value.assertion_span.reference_digest, value.action_state_digest))),
        identity_operations=tuple(sorted(identities, key=lambda value: (value.identity_anchor_span.reference_digest, value.assertion_span.reference_digest, value.identity_operation_digest))),
        status="abstained" if provider.abstained else "complete",
        diagnostics=diagnostics,
    )


def _validate_authorities(
    *,
    source_id: str,
    source_digest: str,
    segment_id: str,
    segment_governance: SegmentGovernanceBinding,
    message_admission_identity: MessageAdmissionIdentity | None,
    governance_carrier_artifact: GovernanceCarrierArtifact,
    owned_text: SourceSpanReference,
    context_text: SourceSpanReference,
    language_route: SegmentLanguageRoute,
) -> None:
    if (
        segment_governance.source_id != source_id
        or segment_governance.segment_id != language_route.parent_projection_segment_id
        or language_route.source_id != source_id
        or language_route.source_digest != source_digest
        or language_route.segment_id != segment_id
    ):
        raise ProposalNormalizationError("proposal authority source, segment, or route mismatch")
    if message_admission_identity is not None and (
        message_admission_identity.segment_governance_binding_digest != segment_governance.binding_digest
    ):
        raise ProposalNormalizationError("message admission does not bind proposal segment governance")
    if (
        governance_carrier_artifact.segment_governance.source_id != source_id
        or segment_governance not in governance_carrier_artifact.segment_governance.bindings
        or (
            message_admission_identity is not None
            and message_admission_identity not in governance_carrier_artifact.message_admissions.identities
        )
    ):
        raise ProposalNormalizationError("governance carrier does not contain proposal authorities")
    for span in (owned_text, context_text):
        if span.source_id != source_id or span.projection_segment_id != language_route.parent_projection_segment_id:
            raise ProposalNormalizationError("proposal text authority source or segment mismatch")
    if (
        owned_text.projection_digest != context_text.projection_digest
        or owned_text.retained_text_artifact != context_text.retained_text_artifact
        or owned_text.segment_local_span.artifact != context_text.segment_local_span.artifact
        or not _contains(context_text, owned_text)
    ):
        raise ProposalNormalizationError("proposal owned and context text authority mismatch")
    segment_artifact = context_text.segment_local_span.artifact
    if (
        language_route.segment_text_artifact_id != segment_artifact.artifact_id
        or language_route.segment_text_artifact_digest != segment_artifact.artifact_digest
        or language_route.segment_text_content_digest != segment_artifact.content_digest
    ):
        raise ProposalNormalizationError("language route does not bind the exact segment text artifact")


def _validate_resolved_span(
    *,
    resolved: SourceSpanReference,
    context: SourceSpanReference,
    source_id: str,
    segment_id: str,
    projection_digest: str,
    owned: bool,
    owned_text: SourceSpanReference,
) -> None:
    """Reject a resolver result unless it is inside the exact supplied authority."""
    if (
        resolved.source_id != source_id
        or resolved.projection_digest != projection_digest
        or resolved.projection_segment_id != context.projection_segment_id
        or resolved.retained_text_artifact != context.retained_text_artifact
        or resolved.projection_span.artifact != context.projection_span.artifact
        or resolved.segment_local_span.artifact != context.segment_local_span.artifact
    ):
        raise ProposalNormalizationError("resolved quote has wrong source, projection, segment, or retained artifact")
    if not _contains(context, resolved):
        raise ProposalNormalizationError("resolved quote lies outside its declared context")
    if owned and not _contains(owned_text, resolved):
        raise ProposalNormalizationError("resolved anchor lies outside owned text")


def _contains(outer: SourceSpanReference, inner: SourceSpanReference) -> bool:
    return (
        outer.projection_span.start <= inner.projection_span.start
        and inner.projection_span.end <= outer.projection_span.end
        and outer.segment_local_span.start <= inner.segment_local_span.start
        and inner.segment_local_span.end <= outer.segment_local_span.end
    )
