"""Exact four-lane bootstrap V3 evidence sealing.

This boundary only retains results returned by host-injected lane adapters.  It
does not reconstruct a generic route or retrieve any external artifact during
reopen.
"""

from __future__ import annotations

from collections.abc import Callable

from memorii.core.semantic_ingestion.contracts import (
    BootstrapAnalysisLaneResultV3,
    BootstrapAnalysisSourceEvidenceV3,
    BootstrapLinguisticAnalysisRequestV3,
    BootstrapPredicateEventCandidateV3,
    BootstrapPredicateEventDetectionRequestV3,
    BootstrapPredicateLanePayloadV3,
    BootstrapResolvedTemporalCandidateV3,
    BootstrapSemanticProposalRequestV3,
    BootstrapSpacyLanePayloadV3,
    BootstrapStanzaLanePayloadV3,
    BootstrapTemporalAmbiguityMemberV3,
    BootstrapTemporalAmbiguitySetV3,
    BootstrapTemporalLanePayloadV3,
    BootstrapTemporalReferenceV3,
    BootstrapTemporalResolutionRequestV3,
    BootstrapV3PayloadLimitAuthority,
    LinguisticAnalysis,
    PredicateEventInventory,
    TemporalResolution,
    contract_digest,
    encode_semantic_contract,
)

BootstrapV3Renew = Callable[[], bool]
BootstrapV3LinguisticLane = Callable[[BootstrapLinguisticAnalysisRequestV3], LinguisticAnalysis | None]
BootstrapV3PredicateLane = Callable[
    [BootstrapPredicateEventDetectionRequestV3], BootstrapPredicateLanePayloadV3 | None
]
BootstrapV3TemporalLane = Callable[
    [BootstrapTemporalResolutionRequestV3], BootstrapTemporalLanePayloadV3 | None
]


class BootstrapV3EvidenceProducer:
    """Run and seal all four required bootstrap analysis lanes in order."""

    def __init__(
        self,
        *,
        stanza: BootstrapV3LinguisticLane,
        spacy: BootstrapV3LinguisticLane,
        predicate_event_detection: BootstrapV3PredicateLane,
        temporal_resolution: BootstrapV3TemporalLane,
    ) -> None:
        self._stanza = stanza
        self._spacy = spacy
        self._predicate = predicate_event_detection
        self._temporal = temporal_resolution

    def produce(
        self,
        *,
        requests: tuple[BootstrapSemanticProposalRequestV3, ...],
        linguistic_request: Callable[[BootstrapSemanticProposalRequestV3, str], BootstrapLinguisticAnalysisRequestV3],
        predicate_request: Callable[[BootstrapSemanticProposalRequestV3], BootstrapPredicateEventDetectionRequestV3],
        temporal_request: Callable[[BootstrapSemanticProposalRequestV3], BootstrapTemporalResolutionRequestV3],
        payload_limit_authority: BootstrapV3PayloadLimitAuthority,
        renew: BootstrapV3Renew,
    ) -> tuple[BootstrapAnalysisLaneResultV3, ...] | None:
        """Return the canonical lane tuple or abort before the next effect."""
        expected = tuple(sorted(requests, key=lambda value: value.segment.segment_id))
        if requests != expected or not requests:
            return None
        policy = payload_limit_authority.policy
        results: list[BootstrapAnalysisLaneResultV3] = []
        for proposal_request in requests:
            provenance = proposal_request.bootstrap_analysis_provenance
            if not renew():
                return None
            stanza_request = linguistic_request(proposal_request, "stanza")
            stanza = self._stanza(stanza_request)
            if stanza is None or stanza.analyzer_manifest_digest != provenance.stanza_analyzer_manifest_digest:
                return None
            if not renew():
                return None
            spacy_request = linguistic_request(proposal_request, "spacy")
            spacy = self._spacy(spacy_request)
            if spacy is None or spacy.analyzer_manifest_digest != provenance.spacy_analyzer_manifest_digest:
                return None
            if not renew():
                return None
            predicate_request_value = predicate_request(proposal_request)
            predicate = self._predicate(predicate_request_value)
            if (
                predicate is None
                or predicate.bootstrap_analysis_provenance != provenance
                or predicate.detector_manifest_digest
                != provenance.predicate_event_manifest_digest
            ):
                return None
            if not renew():
                return None
            temporal_request_value = temporal_request(proposal_request)
            temporal = self._temporal(temporal_request_value)
            if (
                temporal is None
                or temporal.bootstrap_analysis_provenance != provenance
                or temporal.resolver_manifest_digest
                != provenance.temporal_resolver_manifest_digest
            ):
                return None
            lane_values = (
                ("stanza", BootstrapStanzaLanePayloadV3.create(
                    analyzer_fingerprint=stanza.analyzer_fingerprint, analysis=stanza)),
                ("spacy", BootstrapSpacyLanePayloadV3.create(
                    analyzer_fingerprint=spacy.analyzer_fingerprint, analysis=spacy)),
                ("predicate_event_detection", predicate),
                ("temporal_resolution", temporal),
            )
            for lane, payload in lane_values:
                if not _within_item_limit(payload, policy.max_lane_items):
                    return None
                encoded = encode_semantic_contract(payload)
                maximum = {
                    "stanza": policy.max_stanza_bytes,
                    "spacy": policy.max_spacy_bytes,
                    "predicate_event_detection": policy.max_predicate_event_detection_bytes,
                    "temporal_resolution": policy.max_temporal_resolution_bytes,
                }[lane]
                if len(encoded) > maximum:
                    return None
                results.append(BootstrapAnalysisLaneResultV3.create(
                    lane=lane,
                    source_id=proposal_request.segment.source_id,
                    source_digest=proposal_request.segment.source_digest,
                    preparation_fingerprint=proposal_request.segment.preparation_fingerprint,
                    segment_id=proposal_request.segment.segment_id,
                    lane_payload=payload,
                    payload_limit_policy_digest=policy.policy_digest,
                    payload_limit_authority_digest=payload_limit_authority.authority_digest,
                    payload_digest=payload.payload_digest,
                    bootstrap_analysis_provenance=provenance,
                ))
        if len(results) != 4 * len(requests):
            return None
        aggregate = sum(len(encode_semantic_contract(value)) for value in results)
        if aggregate > policy.max_aggregate_bytes:
            return None
        return tuple(results)


def _source_evidence(request: object, span: object, exact_text: str) -> BootstrapAnalysisSourceEvidenceV3:
    segment = request.segment
    return BootstrapAnalysisSourceEvidenceV3.create(
        source_id=segment.source_id, source_digest=segment.source_digest,
        preparation_fingerprint=segment.preparation_fingerprint, segment_id=segment.segment_id,
        bootstrap_analysis_provenance=request.bootstrap_analysis_provenance, span=span, exact_text=exact_text,
    )


def _text_for_span(request: object, span: object) -> str:
    local = span.segment_local_span
    text = request.segment.segment_text[local.start:local.end]
    if len(text) != local.end - local.start:
        raise ValueError("generic lane span is outside the bootstrap segment")
    return text


def _seal_predicate(request: BootstrapPredicateEventDetectionRequestV3,
                    inventory: PredicateEventInventory) -> BootstrapPredicateLanePayloadV3:
    segment, provenance = request.segment, request.bootstrap_analysis_provenance
    if (inventory.source_id, inventory.source_digest, inventory.preparation_fingerprint) != (
            segment.source_id, segment.source_digest, segment.preparation_fingerprint):
        raise ValueError("generic predicate inventory does not join bootstrap request")
    candidates = []
    for candidate in inventory.candidates:
        if candidate.segment_id != segment.segment_id:
            continue
        anchor = _source_evidence(request, candidate.lexical_anchor_span, _text_for_span(request, candidate.lexical_anchor_span))
        morphology = tuple(_source_evidence(request, item, _text_for_span(request, item)) for item in candidate.morphology_evidence_spans)
        # Generic adapters historically omit morphology for bare lexical rules.  The lexical
        # anchor is the only certified morphology evidence in that legacy representation.
        if not morphology:
            morphology = (anchor,)
        identity = {"provenance_digest": provenance.provenance_digest, "predicate_family": candidate.predicate_family,
                    "lexical_anchor": anchor, "detection_rule_id": candidate.detection_rule_id,
                    "detector_fingerprint": request.predicate_event_manifest.manifest_digest}
        candidates.append(BootstrapPredicateEventCandidateV3.create(
            event_id=contract_digest(b"memorii.semantic-ingestion.bootstrap-predicate-event-identity.v3", identity),
            source_id=segment.source_id, source_digest=segment.source_digest,
            preparation_fingerprint=segment.preparation_fingerprint, segment_id=segment.segment_id,
            bootstrap_analysis_provenance=provenance, predicate_family=candidate.predicate_family,
            lexical_anchor=anchor, morphology_evidence=tuple(sorted(morphology, key=lambda item: item.evidence_digest)),
            detection_rule_id=candidate.detection_rule_id,
            detector_manifest_digest=request.predicate_event_manifest.manifest_digest,
        ))
    return BootstrapPredicateLanePayloadV3.create(
        source_id=segment.source_id, source_digest=segment.source_digest,
        preparation_fingerprint=segment.preparation_fingerprint, segment_id=segment.segment_id,
        bootstrap_analysis_provenance=provenance,
        detector_manifest_digest=request.predicate_event_manifest.manifest_digest,
        detector_fingerprint=request.predicate_event_manifest.manifest_digest,
        candidates=tuple(sorted(candidates, key=lambda item: (item.lexical_anchor.evidence_digest, item.event_id, item.candidate_digest))),
        status=inventory.status, reason_codes=tuple(sorted(set(inventory.segment_outcomes[0].reason_codes))),
    )


def _native_reference(request: BootstrapTemporalResolutionRequestV3, reference: object | None) -> BootstrapTemporalReferenceV3 | None:
    if reference is None:
        return None
    segment = request.segment
    values = {
        "kind": reference.kind, "source_id": segment.source_id, "source_digest": segment.source_digest,
        "preparation_fingerprint": segment.preparation_fingerprint, "source_field": reference.source_field,
        "reference_instant": reference.reference_instant, "authority_basis": reference.authority_basis,
        "authority_provenance_digest": reference.provenance_digest,
        "source_semantic_context_digest": segment.segment_governance.message_semantic_context_digest,
        "bootstrap_analysis_provenance": request.bootstrap_analysis_provenance,
    }
    return BootstrapTemporalReferenceV3.create(**values)


def _value_basis_key(candidate: BootstrapResolvedTemporalCandidateV3) -> str:
    return contract_digest(b"memorii.semantic-ingestion.bootstrap-temporal-value-basis-key.v3", {
        name: getattr(candidate, name) for name in ("value_kind", "normalized_start", "normalized_end",
        "normalized_duration_seconds", "grain", "locale", "timezone", "reference", "resolver_rule_id", "resolver_fingerprint")})


def _seal_temporal(request: BootstrapTemporalResolutionRequestV3,
                   resolution: TemporalResolution) -> BootstrapTemporalLanePayloadV3:
    segment, provenance = request.segment, request.bootstrap_analysis_provenance
    if (resolution.source_id, resolution.source_digest, resolution.preparation_fingerprint) != (
            segment.source_id, segment.source_digest, segment.preparation_fingerprint):
        raise ValueError("generic temporal resolution does not join bootstrap request")
    candidates = []
    for item in resolution.candidates:
        if item.segment_id != segment.segment_id:
            continue
        evidence = _source_evidence(request, item.source_span, item.exact_text)
        interval = item.normalized_interval
        start = interval.start if interval is not None else None
        end = (interval.start if item.value_kind == "instant" and interval is not None else
               interval.end if interval is not None else None)
        duration = int(item.normalized_duration.total_seconds()) if item.normalized_duration is not None else None
        reference = _native_reference(request, item.reference_evidence)
        identity = {"source_id": segment.source_id, "source_digest": segment.source_digest,
                    "preparation_fingerprint": segment.preparation_fingerprint, "segment_id": segment.segment_id,
                    "bootstrap_analysis_provenance": provenance, "source_evidence": evidence,
                    "value_kind": item.value_kind, "normalized_start": start, "normalized_end": end,
                    "normalized_duration_seconds": duration, "grain": item.grain, "locale": item.locale,
                    "timezone": item.timezone, "reference": reference, "resolver_rule_id": item.resolver_rule_id,
                    "resolver_fingerprint": resolution.resolver_fingerprint}
        candidates.append(BootstrapResolvedTemporalCandidateV3.create(
            **identity, candidate_id=contract_digest(
                b"memorii.semantic-ingestion.bootstrap-resolved-temporal-candidate-identity.v3", identity)))
    candidates = tuple(sorted(candidates, key=lambda item: (item.source_evidence.evidence_digest, item.candidate_id, item.candidate_digest)))
    groups: list[BootstrapTemporalAmbiguitySetV3] = []
    for evidence_digest in {item.source_evidence.evidence_digest for item in candidates}:
        members = tuple(item for item in candidates if item.source_evidence.evidence_digest == evidence_digest)
        if len(members) > 1:
            alternatives = tuple(BootstrapTemporalAmbiguityMemberV3.create(candidate=item, value_basis_key=_value_basis_key(item)) for item in members)
            first = members[0]
            groups.append(BootstrapTemporalAmbiguitySetV3.create(
                source_id=first.source_id, source_digest=first.source_digest, preparation_fingerprint=first.preparation_fingerprint,
                segment_id=first.segment_id, bootstrap_analysis_provenance=first.bootstrap_analysis_provenance,
                source_evidence=first.source_evidence,
                alternatives=tuple(sorted(alternatives, key=lambda item: (item.value_basis_key, item.candidate.candidate_id, item.member_digest))),
            ))
    return BootstrapTemporalLanePayloadV3.create(
        source_id=segment.source_id, source_digest=segment.source_digest, preparation_fingerprint=segment.preparation_fingerprint,
        segment_id=segment.segment_id, bootstrap_analysis_provenance=provenance,
        resolver_manifest_digest=request.resolver_manifest.manifest_digest, resolver_fingerprint=resolution.resolver_fingerprint,
        candidates=candidates, ambiguities=tuple(sorted(groups, key=lambda item: (item.source_evidence.evidence_digest, item.ambiguity_digest))),
        status=resolution.status, reason_codes=tuple(sorted(set(resolution.diagnostics))),
    )


def _within_item_limit(payload: object, maximum: int) -> bool:
    """Apply the V3 lane-item quota after generic output has been discarded."""
    if isinstance(payload, BootstrapPredicateLanePayloadV3):
        return (
            len(payload.candidates) <= maximum
            and len(payload.reason_codes) <= maximum
            and all(len(item.morphology_evidence) <= maximum for item in payload.candidates)
        )
    if isinstance(payload, BootstrapTemporalLanePayloadV3):
        return (
            len(payload.candidates) <= maximum
            and len(payload.ambiguities) <= maximum
            and len(payload.reason_codes) <= maximum
            and all(len(item.alternatives) <= maximum for item in payload.ambiguities)
        )
    return True


class ConfiguredBootstrapV3EvidenceProducer:
    """Binds four injected V3 lane factories to one runtime authority."""

    def __init__(
        self,
        *,
        producer: BootstrapV3EvidenceProducer,
        linguistic_request: Callable[[BootstrapSemanticProposalRequestV3, str], BootstrapLinguisticAnalysisRequestV3],
        predicate_request: Callable[[BootstrapSemanticProposalRequestV3], BootstrapPredicateEventDetectionRequestV3],
        temporal_request: Callable[[BootstrapSemanticProposalRequestV3], BootstrapTemporalResolutionRequestV3],
    ) -> None:
        self._producer = producer
        self._linguistic_request = linguistic_request
        self._predicate_request = predicate_request
        self._temporal_request = temporal_request

    def produce(self, *, authority: object, renew: BootstrapV3Renew) -> tuple[BootstrapAnalysisLaneResultV3, ...] | None:
        requests = getattr(authority, "proposal_requests", None)
        payload_limit_authority = getattr(authority, "payload_limit_authority", None)
        if not isinstance(requests, tuple) or payload_limit_authority is None:
            return None
        return self._producer.produce(
            requests=requests, linguistic_request=self._linguistic_request,
            predicate_request=self._predicate_request, temporal_request=self._temporal_request,
            payload_limit_authority=payload_limit_authority, renew=renew,
        )


__all__ = ["BootstrapV3EvidenceProducer", "ConfiguredBootstrapV3EvidenceProducer"]
