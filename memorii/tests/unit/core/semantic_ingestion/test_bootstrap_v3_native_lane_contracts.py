"""Native-only bootstrap predicate and temporal lane closure vectors."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

import pytest
from memorii.core.semantic_ingestion.contracts import (
    BootstrapAnalysisSourceEvidenceV3,
    BootstrapPredicateEventCandidateV3,
    BootstrapPredicateLanePayloadV3,
    BootstrapResolvedTemporalCandidateV3,
    BootstrapTemporalLanePayloadV3,
    contract_digest,
    decode_semantic_contract,
    encode_semantic_contract,
)
from tests.fixtures.semantic_ingestion.source_normalization_fixture_builder import (
    build_bootstrap_declared_prepared_source,
    build_bootstrap_v3_fixture_authority,
)


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _native_values() -> tuple[object, object, object]:
    source = build_bootstrap_declared_prepared_source(
        source_id="source:native-lane", source_digest=_digest("source"), source_text="Alice works.",
    )
    issued = build_bootstrap_v3_fixture_authority(source=source)
    request = issued.runtime_authority.proposal_requests[0]
    segment, provenance = request.segment, request.bootstrap_analysis_provenance
    span = segment.context_text
    evidence = BootstrapAnalysisSourceEvidenceV3.create(
        source_id=segment.source_id, source_digest=segment.source_digest,
        preparation_fingerprint=segment.preparation_fingerprint, segment_id=segment.segment_id,
        bootstrap_analysis_provenance=provenance, span=span, exact_text=segment.segment_text,
    )
    return request, evidence, issued


def test_native_predicate_lane_roundtrips_and_rejects_generic_shape() -> None:
    request, evidence, issued = _native_values()
    provenance = request.bootstrap_analysis_provenance
    identity = {
        "provenance_digest": provenance.provenance_digest, "predicate_family": "work",
        "lexical_anchor": evidence, "detection_rule_id": "native-rule",
        "detector_fingerprint": issued.predicate_manifest.manifest_digest,
    }
    candidate = BootstrapPredicateEventCandidateV3.create(
        event_id=contract_digest(b"memorii.semantic-ingestion.bootstrap-predicate-event-identity.v3", identity),
        source_id=request.segment.source_id, source_digest=request.segment.source_digest,
        preparation_fingerprint=request.segment.preparation_fingerprint, segment_id=request.segment.segment_id,
        bootstrap_analysis_provenance=provenance, predicate_family="work", lexical_anchor=evidence,
        morphology_evidence=(evidence,), detection_rule_id="native-rule",
        detector_manifest_digest=issued.predicate_manifest.manifest_digest,
    )
    payload = BootstrapPredicateLanePayloadV3.create(
        source_id=request.segment.source_id, source_digest=request.segment.source_digest,
        preparation_fingerprint=request.segment.preparation_fingerprint, segment_id=request.segment.segment_id,
        bootstrap_analysis_provenance=provenance, detector_manifest_digest=issued.predicate_manifest.manifest_digest,
        detector_fingerprint=issued.predicate_manifest.manifest_digest, candidates=(candidate,),
        status="complete", reason_codes=(),
    )
    encoded = encode_semantic_contract(payload)
    assert decode_semantic_contract(encoded, BootstrapPredicateLanePayloadV3) == payload
    with pytest.raises(ValueError):
        BootstrapPredicateLanePayloadV3.model_validate(payload.model_dump(mode="python") | {"inventory": {}})


def test_native_temporal_candidate_identity_and_reference_basis_are_closed() -> None:
    request, evidence, issued = _native_values()
    identity = {
        "source_id": request.segment.source_id, "source_digest": request.segment.source_digest,
        "preparation_fingerprint": request.segment.preparation_fingerprint, "segment_id": request.segment.segment_id,
        "bootstrap_analysis_provenance": request.bootstrap_analysis_provenance, "source_evidence": evidence,
        "value_kind": "instant", "normalized_start": datetime(2026, 1, 1, tzinfo=UTC),
        "normalized_end": datetime(2026, 1, 1, tzinfo=UTC), "normalized_duration_seconds": None,
        "grain": "day", "locale": "en_US", "timezone": "UTC", "reference": None,
        "resolver_rule_id": "absolute-day", "resolver_fingerprint": _digest("resolver"),
    }
    candidate = BootstrapResolvedTemporalCandidateV3.create(
        **identity,
        candidate_id=contract_digest(
            b"memorii.semantic-ingestion.bootstrap-resolved-temporal-candidate-identity.v3", identity
        ),
    )
    payload = BootstrapTemporalLanePayloadV3.create(
        source_id=request.segment.source_id, source_digest=request.segment.source_digest,
        preparation_fingerprint=request.segment.preparation_fingerprint, segment_id=request.segment.segment_id,
        bootstrap_analysis_provenance=request.bootstrap_analysis_provenance,
        resolver_manifest_digest=issued.temporal_manifest.manifest_digest,
        resolver_fingerprint=_digest("resolver"), candidates=(candidate,), ambiguities=(),
        status="complete", reason_codes=(),
    )
    assert decode_semantic_contract(encode_semantic_contract(payload), BootstrapTemporalLanePayloadV3) == payload
    with pytest.raises(ValueError, match="candidate_digest mismatch"):
        BootstrapResolvedTemporalCandidateV3.model_validate(
            candidate.model_dump(mode="python") | {"normalized_end": datetime(2026, 1, 2, tzinfo=UTC)}
        )
