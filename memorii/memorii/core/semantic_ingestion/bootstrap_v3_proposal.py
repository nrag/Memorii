"""Bootstrap-only proposal normalization without generic-route reconstruction.

The generic proposal adapter deliberately produces ``SemanticProposal``.  A
bootstrap retry must never create that type because recovery would then have a
generic route-shaped object available.  This module is the narrow V3 equivalent
that resolves provider-local references directly into the retained operation
algebra.
"""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256

from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.semantic_ingestion.contracts import (
    BootstrapNormalizedProposalV3,
    BootstrapProposalActionRecordSelectorV3,
    BootstrapProposalActionRoleBindingV3,
    BootstrapProposalActionRoleParticipantV3,
    BootstrapProposalActionStateV3,
    BootstrapProposalAliasRecordSelectorV3,
    BootstrapProposalAttemptV3,
    BootstrapProposalClaimRecordSelectorV3,
    BootstrapProposalCorrectionV3,
    BootstrapProposalEntityObjectV3,
    BootstrapProposalEvidenceItemV3,
    BootstrapProposalFactV3,
    BootstrapProposalIdentityOperationV3,
    BootstrapProposalLiteralObjectV3,
    BootstrapProposalMentionV3,
    BootstrapProposalReferenceAssignmentV3,
    BootstrapProposalRetractionV3,
    BootstrapProposalRunPayloadV3,
    BootstrapProposalTransportRequestV3,
    BootstrapProposalTypedLiteralV3,
    BootstrapSemanticProposalRequestV3,
    BootstrapV3PayloadLimitAuthority,
    ProviderActionRecordSelector,
    ProviderAliasRecordSelector,
    ProviderClaimRecordSelector,
    ProviderEntityObject,
    ProviderFact,
    ProviderLiteralObject,
    ProviderSemanticProposal,
    SourceSpanReference,
    contract_digest,
)
from memorii.core.semantic_ingestion.proposal_adapter import (
    ProjectionQuoteVerificationAuthority,
    ProposalNormalizationError,
    SpanResolver,
)

BootstrapV3ProposalTransport = Callable[
    [BootstrapSemanticProposalRequestV3], tuple[ProviderSemanticProposal, bytes] | None
]


def normalize_bootstrap_provider_proposal(
    *,
    provider: ProviderSemanticProposal,
    request: BootstrapSemanticProposalRequestV3,
    originating_attempt_digest: str,
    resolve_quote: SpanResolver,
    projection_quote_verifier: ProjectionQuoteVerificationAuthority,
    payload_limit_authority: BootstrapV3PayloadLimitAuthority,
) -> BootstrapNormalizedProposalV3:
    """Resolve one transport response into the closed bootstrap V3 algebra."""
    segment = request.segment
    provenance = request.bootstrap_analysis_provenance
    policy = payload_limit_authority.policy
    if (
        request.bootstrap_analysis_provenance != segment.bootstrap_analysis_provenance
        or request.proposal_capability_fingerprint != provenance.proposal_capability_fingerprint
        or (payload_limit_authority.source_id, payload_limit_authority.source_digest,
            payload_limit_authority.preparation_fingerprint)
        != (segment.source_id, segment.source_digest, segment.preparation_fingerprint)
    ):
        raise ProposalNormalizationError("bootstrap proposal authority is substituted")

    def span(quote: str, context: SourceSpanReference) -> SourceSpanReference:
        try:
            value = resolve_quote(quote, context, False)
            projection_quote_verifier.verify_quote(
                projection_digest=context.projection_digest, quote=quote, span=value
            )
        except ValueError as exc:
            raise ProposalNormalizationError("bootstrap quote cannot be resolved exactly") from exc
        if (
            value.source_id != segment.source_id
            or value.projection_digest != context.projection_digest
            or value.projection_segment_id != context.projection_segment_id
            or value.retained_text_artifact != context.retained_text_artifact
            or not _contains(context, value)
        ):
            raise ProposalNormalizationError("bootstrap quote span is outside its declared source context")
        return value

    def evidence(quote: str, context: SourceSpanReference) -> BootstrapProposalEvidenceItemV3:
        return BootstrapProposalEvidenceItemV3.create(span=span(quote, context), quote=quote)

    mentions: dict[str, BootstrapProposalMentionV3] = {}
    for item in provider.mentions:
        context_span = span(item.mention_context_quote, segment.context_text)
        mention_span = span(item.mention_quote, context_span)
        mentions[item.local_id] = BootstrapProposalMentionV3.create(
            mention_span=mention_span,
            mention_quote=item.mention_quote,
            mention_context_span=context_span,
            mention_context_quote=item.mention_context_quote,
            proposed_type=item.proposed_type,
        )
    if len(mentions) > policy.max_mentions_per_proposal:
        raise ProposalNormalizationError("bootstrap mention quota exceeded")

    def entity(local_id: str) -> str:
        try:
            return mentions[local_id].mention_digest
        except KeyError as exc:
            raise ProposalNormalizationError("bootstrap entity reference is absent") from exc

    def object_value(value: ProviderEntityObject | ProviderLiteralObject):
        if isinstance(value, ProviderEntityObject):
            return BootstrapProposalEntityObjectV3.create(mention_digest=entity(value.entity_ref))
        literal = BootstrapProposalTypedLiteralV3.create(
            literal_type=value.literal_type, canonical_value=value.canonical_value, unit=value.unit
        )
        return BootstrapProposalLiteralObjectV3.create(value=literal)

    def fact(value: ProviderFact) -> BootstrapProposalFactV3:
        assertion = evidence(value.assertion_quote, segment.context_text)
        qualifiers = tuple(sorted(
            (evidence(item, assertion.span) for item in value.temporal_qualifier_quotes),
            key=lambda item: item.item_digest,
        ))
        if len(qualifiers) > policy.max_temporal_qualifiers_per_member:
            raise ProposalNormalizationError("bootstrap temporal qualifier quota exceeded")
        return BootstrapProposalFactV3.create(
            predicate_id=value.predicate_id,
            subject_mention_digest=entity(value.subject_entity_ref),
            object=object_value(value.object),
            assertion=assertion,
            predicate_anchor=evidence(value.predicate_anchor_quote, assertion.span),
            polarity=value.polarity,
            commitment=value.commitment,
            attributed_to_mention_digest=(
                None if value.attributed_to_entity_ref is None else entity(value.attributed_to_entity_ref)
            ),
            temporal_qualifiers=qualifiers,
        )

    facts_by_local = {item.local_id: fact(item) for item in provider.facts}
    actions_by_coordinate: dict[tuple[str, str], BootstrapProposalActionStateV3] = {}
    actions = []
    for item in provider.action_states:
        assertion = evidence(item.assertion_quote, segment.context_text)
        action_anchor = evidence(item.action_anchor_quote, assertion.span)
        bindings = []
        for binding in item.role_bindings:
            if len(binding.entity_refs) != len(binding.grounding_quotes):
                raise ProposalNormalizationError("bootstrap action role grounding does not pair")
            participants = tuple(sorted((
                BootstrapProposalActionRoleParticipantV3.create(
                    mention_digest=entity(reference),
                    grounding=(evidence(grounding, assertion.span),),
                )
                for reference, grounding in zip(binding.entity_refs, binding.grounding_quotes, strict=True)
            ), key=lambda value: (value.mention_digest, value.participant_digest)))
            if len(participants) > policy.max_action_participants_per_binding:
                raise ProposalNormalizationError("bootstrap action participant quota exceeded")
            bindings.append(BootstrapProposalActionRoleBindingV3.create(
                role_id=binding.role_id, endpoint_kind=binding.endpoint_kind, participants=participants
            ))
        bindings = tuple(sorted(bindings, key=lambda value: (value.role_id, value.endpoint_kind, value.binding_digest)))
        if len(bindings) > policy.max_action_role_bindings_per_member:
            raise ProposalNormalizationError("bootstrap action binding quota exceeded")
        branch = None if item.execution_branch_anchor_quote is None else evidence(item.execution_branch_anchor_quote, assertion.span)
        action = BootstrapProposalActionStateV3.create(
            action_anchor=action_anchor,
            logical_action_digest=contract_digest(
                b"memorii.semantic-ingestion.bootstrap-proposal-logical-action.v3",
                {"action_anchor": action_anchor, "role_bindings": bindings},
            ),
            role_bindings=bindings,
            state_id=item.state_id,
            state_anchor=evidence(item.state_anchor_quote, assertion.span),
            execution_branch=branch,
            execution_branch_digest=(None if branch is None else contract_digest(
                b"memorii.semantic-ingestion.bootstrap-proposal-execution-branch.v3",
                {"execution_branch": branch},
            )),
            assertion=assertion,
            temporal_qualifiers=tuple(sorted(
                (evidence(value, assertion.span) for value in item.temporal_qualifier_quotes),
                key=lambda value: value.item_digest,
            )),
        )
        actions_by_coordinate[(item.logical_action_local_id, action_anchor.span.reference_digest)] = action
        actions.append(action)

    corrections = tuple(BootstrapProposalCorrectionV3.create(
        corrected_fact=fact(item.corrected_fact), replacement_fact=fact(item.replacement_fact),
        assertion=evidence(item.assertion_quote, segment.context_text),
        correction_anchor=evidence(item.correction_anchor_quote, segment.context_text),
    ) for item in provider.corrections)
    retractions = tuple(BootstrapProposalRetractionV3.create(
        retracted_fact=fact(item.retracted_fact),
        assertion=evidence(item.assertion_quote, segment.context_text),
        retraction_anchor=evidence(item.retraction_anchor_quote, segment.context_text),
    ) for item in provider.retractions)
    identities = []
    for item in provider.identity_operations:
        assertion = evidence(item.assertion_quote, segment.context_text)
        assignments = []
        for assignment in item.reference_assignments:
            selector = assignment.record_selector
            if isinstance(selector, ProviderClaimRecordSelector):
                if selector.fact_local_id not in facts_by_local:
                    raise ProposalNormalizationError("bootstrap claim selector is absent")
                resolved = BootstrapProposalClaimRecordSelectorV3.create(fact_digest=facts_by_local[selector.fact_local_id].fact_digest)
            elif isinstance(selector, ProviderActionRecordSelector):
                anchor = evidence(selector.action_anchor_quote, assertion.span)
                action = actions_by_coordinate.get((selector.logical_action_local_id, anchor.span.reference_digest))
                if action is None:
                    raise ProposalNormalizationError("bootstrap action selector is absent")
                resolved = BootstrapProposalActionRecordSelectorV3.create(
                    logical_action_digest=action.logical_action_digest, action_anchor=action.action_anchor
                )
            elif isinstance(selector, ProviderAliasRecordSelector):
                resolved = BootstrapProposalAliasRecordSelectorV3.create(
                    alias_namespace=selector.alias_namespace, alias_anchor=evidence(selector.alias_anchor_quote, assertion.span)
                )
            else:  # The provider union is closed, but retain a fail-closed branch.
                raise ProposalNormalizationError("bootstrap record selector kind is unknown")
            assignments.append(BootstrapProposalReferenceAssignmentV3.create(
                record_selector=resolved,
                successor_mention_digests=tuple(sorted(entity(value) for value in assignment.successor_entity_refs)),
                disposition=assignment.disposition,
                assertion=evidence(assignment.assertion_quote, assertion.span),
            ))
        if len(assignments) > policy.max_reference_assignments_per_identity:
            raise ProposalNormalizationError("bootstrap identity assignment quota exceeded")
        identities.append(BootstrapProposalIdentityOperationV3.create(
            operation=item.operation,
            predecessor_mention_digests=tuple(sorted(entity(value) for value in item.predecessor_entity_refs)),
            successor_mention_digests=tuple(sorted(entity(value) for value in item.successor_entity_refs)),
            reference_assignments=tuple(sorted(assignments, key=lambda value: (value.record_selector.selector_digest, value.assignment_digest))),
            assertion=assertion,
            identity_anchor=evidence(item.identity_anchor_quote, assertion.span),
        ))

    members = [*facts_by_local.values(), *corrections, *retractions, *actions, *identities]
    counts = {
        "fact": len(facts_by_local), "correction": len(corrections), "retraction": len(retractions),
        "action_state": len(actions), "identity": len(identities),
    }
    for kind, limit in (
        ("fact", policy.max_fact_members_per_proposal),
        ("correction", policy.max_correction_members_per_proposal),
        ("retraction", policy.max_retraction_members_per_proposal),
        ("action_state", policy.max_action_state_members_per_proposal),
        ("identity", policy.max_identity_members_per_proposal),
    ):
        if counts[kind] > limit:
            raise ProposalNormalizationError("bootstrap operation quota exceeded")
    ranks = {"fact": 0, "correction": 1, "retraction": 2, "action_state": 3, "identity": 4}
    def member_key(value: object) -> tuple[int, str, str]:
        anchor = next(getattr(value, field) for field in (
            "predicate_anchor", "correction_anchor", "retraction_anchor", "action_anchor", "identity_anchor"
        ) if getattr(value, field, None) is not None)
        digest = next(getattr(value, field) for field in type(value).model_fields if field.endswith("_digest") and field not in {"logical_action_digest", "execution_branch_digest"})
        return ranks[value.kind], anchor.item_digest, digest
    members = tuple(sorted(members, key=member_key))
    return BootstrapNormalizedProposalV3.create(
        source_id=segment.source_id, source_digest=segment.source_digest,
        preparation_fingerprint=segment.preparation_fingerprint, segment_id=segment.segment_id,
        bootstrap_analysis_provenance=provenance,
        mentions=tuple(sorted(mentions.values(), key=lambda value: (value.mention_span.reference_digest, value.mention_digest))),
        operation_members=members,
        status="abstained" if provider.abstained else "complete",
        originating_attempt_digest=originating_attempt_digest,
        payload_limit_policy_digest=policy.policy_digest,
        payload_limit_authority_digest=payload_limit_authority.authority_digest,
    )


def seal_bootstrap_proposal_run(
    *,
    requests: tuple[BootstrapSemanticProposalRequestV3, ...],
    responses: tuple[ProviderSemanticProposal, ...],
    raw_response_bytes: tuple[bytes, ...],
    payload_limit_authority: BootstrapV3PayloadLimitAuthority,
    resolve_quote: SpanResolver,
    projection_quote_verifier: ProjectionQuoteVerificationAuthority,
) -> BootstrapProposalRunPayloadV3:
    """Seal one source-wide V3 response set.  Retries are intentionally explicit."""
    if len(requests) != len(responses) or len(requests) != len(raw_response_bytes):
        raise ProposalNormalizationError("bootstrap proposal response cardinality is invalid")
    ordered = tuple(sorted(requests, key=lambda value: value.segment.segment_id))
    if requests != ordered or len({value.segment.segment_id for value in requests}) != len(requests):
        raise ProposalNormalizationError("bootstrap proposal requests are not source ordered")
    policy = payload_limit_authority.policy
    if len(requests) > policy.max_proposal_attempts or len(requests) > policy.max_normalized_proposals:
        raise ProposalNormalizationError("bootstrap proposal payload quota exceeded")
    transport = tuple(BootstrapProposalTransportRequestV3.create(
        source_id=request.segment.source_id, source_digest=request.segment.source_digest,
        preparation_fingerprint=request.segment.preparation_fingerprint,
        provenance_keys=(request.bootstrap_analysis_provenance.provenance_digest,),
        prompt_registration_digest=request.registered_prompt.prompt_registration_digest,
        request_bytes_digest=sha256(encode_typed_value(request.model_dump(mode="python"))).hexdigest(),
    ) for request in requests)
    attempts = tuple(BootstrapProposalAttemptV3.create(
        attempt_ordinal=index, transport_request_digest=item.request_digest,
        provider_response_digest=sha256(raw_response_bytes[index]).hexdigest(), transport_status="succeeded",
    ) for index, item in enumerate(transport))
    proposals = tuple(normalize_bootstrap_provider_proposal(
        provider=response, request=requests[index], originating_attempt_digest=attempts[index].attempt_digest,
        resolve_quote=resolve_quote, projection_quote_verifier=projection_quote_verifier,
        payload_limit_authority=payload_limit_authority,
    ) for index, response in enumerate(responses))
    provenance = tuple(request.bootstrap_analysis_provenance for request in requests)
    return BootstrapProposalRunPayloadV3.create(
        source_id=payload_limit_authority.source_id, source_digest=payload_limit_authority.source_digest,
        preparation_fingerprint=payload_limit_authority.preparation_fingerprint,
        bootstrap_analysis_provenances=provenance, transport_requests=transport,
        proposal_attempts=attempts, normalized_proposals=proposals,
        payload_limit_policy_digest=policy.policy_digest,
        payload_limit_authority_digest=payload_limit_authority.authority_digest,
        attempt_closure_digest=contract_digest(
            b"memorii.semantic-ingestion.bootstrap-proposal-attempt-closure.v3",
            {"transport_request_digests": tuple(item.request_digest for item in transport),
             "attempt_digests": tuple(item.attempt_digest for item in attempts),
             "normalized_proposal_digests": tuple(item.proposal_digest for item in proposals)},
        ),
    )


class SealedBootstrapV3ProposalProducer:
    """Host-configured V3 transport bridge with no generic proposal fallback."""

    def __init__(
        self,
        *,
        transport: BootstrapV3ProposalTransport,
        resolve_quote: SpanResolver,
        projection_quote_verifier: ProjectionQuoteVerificationAuthority,
    ) -> None:
        self._transport = transport
        self._resolve_quote = resolve_quote
        self._projection_quote_verifier = projection_quote_verifier

    def produce(self, *, authority: object, renew: Callable[[], bool]) -> BootstrapProposalRunPayloadV3 | None:
        requests = getattr(authority, "proposal_requests", None)
        payload_limit_authority = getattr(authority, "payload_limit_authority", None)
        if not isinstance(requests, tuple) or payload_limit_authority is None:
            return None
        responses: list[ProviderSemanticProposal] = []
        raw: list[bytes] = []
        for request in requests:
            if not renew():
                return None
            returned = self._transport(request)
            if returned is None:
                return None
            response, response_bytes = returned
            if not isinstance(response, ProviderSemanticProposal) or not isinstance(response_bytes, bytes):
                return None
            responses.append(response)
            raw.append(response_bytes)
        try:
            return seal_bootstrap_proposal_run(
                requests=requests, responses=tuple(responses), raw_response_bytes=tuple(raw),
                payload_limit_authority=payload_limit_authority, resolve_quote=self._resolve_quote,
                projection_quote_verifier=self._projection_quote_verifier,
            )
        except ValueError:
            return None


def _contains(outer: SourceSpanReference, inner: SourceSpanReference) -> bool:
    return (
        outer.projection_span.start <= inner.projection_span.start <= inner.projection_span.end <= outer.projection_span.end
        and outer.segment_local_span.start <= inner.segment_local_span.start <= inner.segment_local_span.end <= outer.segment_local_span.end
    )


__all__ = [
    "BootstrapV3ProposalTransport",
    "SealedBootstrapV3ProposalProducer",
    "normalize_bootstrap_provider_proposal",
    "seal_bootstrap_proposal_run",
]
