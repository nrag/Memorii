"""Focused strict-wire proof for source context and proposal-run inputs."""

from __future__ import annotations

import base64
import copy
import json
import zlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from clean_room_request_test_support import build_clean_room_semantic_proposal_request
from memorii.core.memory_evolution.ingestion_contracts import decode_typed_value, encode_typed_value
from memorii.core.memory_evolution.models import ExtractionTriggerMode
from memorii.core.semantic_ingestion.contracts import (
    AnalyzerManifest,
    LanguageCandidate,
    LinguisticFeature,
    SegmentLanguageRoute,
    SegmentLanguageRouteSet,
    SegmentProposalOutcome,
    SemanticContractCodecError,
    SemanticProposal,
    SemanticProposalAttempt,
    SemanticProposalAttemptIdentity,
    SemanticProposalRequestArtifact,
    SemanticProposalResponseArtifact,
    SemanticProposalRun,
    SourceSemanticContext,
    TemporalResolverManifest,
    _restore_closed_wire_enums,
    decode_semantic_contract,
    encode_semantic_contract,
)


def _request_artifact(proposal: SemanticProposal) -> SemanticProposalRequestArtifact:
    """Use persisted clean-room request bytes; legacy proposals lack source text."""
    del proposal
    return SemanticProposalRequestArtifact.create(request_bytes=encode_semantic_contract(build_clean_room_semantic_proposal_request()))

_FIXTURE = (
    Path(__file__).parents[3]
    / "fixtures"
    / "semantic_ingestion"
    / "normalization_contracts"
    / "semantic_proposal_literal_v1.json"
)


def _proposal() -> SemanticProposal:
    vector = json.loads(_FIXTURE.read_text(encoding="ascii"))
    body = decode_typed_value(zlib.decompress(base64.b64decode(vector["expected_ctv_preimage_zlib_base64"])))
    payload = json.loads(zlib.decompress(base64.b64decode(vector["semantic_proposal_zlib_base64"])))
    body["proposal_digest"] = payload["proposal_digest"]
    # The frozen vector predates attempt provenance; it is input material for
    # a final proposal, not a legacy wire accepted by the codec.
    body = _restore_closed_wire_enums(body)
    body["preparation_fingerprint"] = "1" * 64
    route = body["language_route"]
    assert isinstance(route, dict)
    body["language_route"] = SegmentLanguageRoute.create(
        **({key: value for key, value in route.items() if key != "route_digest"} | {"parent_projection_segment_id": body["segment_id"], "candidates": (LanguageCandidate(language="en", probability_ppm=1_000_000, model_fingerprint="1" * 64),)})
    )
    return SemanticProposal.create(
        **({key: value for key, value in body.items() if key != "proposal_digest"} | {"originating_attempt_digest": "0" * 64})
    )


def _attempt(proposal: SemanticProposal) -> SemanticProposalAttempt:
    request = _request_artifact(proposal)
    identity = SemanticProposalAttemptIdentity.create(
        source_id=proposal.source_id,
        preparation_fingerprint=proposal.preparation_fingerprint,
        segment_id=proposal.segment_id,
        segment_governance=proposal.segment_governance,
        message_admission_identity=proposal.message_admission_identity,
        governance_carrier_artifact=proposal.governance_carrier_artifact,
        owned_text=proposal.owned_text,
        context_text=proposal.context_text,
        language_route=proposal.language_route,
        proposer_fingerprint=proposal.proposer_fingerprint,
        proposer_manifest_digest=proposal.proposer_manifest_digest,
        prompt_registration_digest=proposal.prompt_registration_digest,
        semantic_request_fingerprint=proposal.semantic_request_fingerprint,
        attempt_payload_fingerprint=proposal.attempt_payload_fingerprint,
        attempt_number=0,
        request_digest=request.request_digest,
        request_artifact_digest=request.artifact_digest,
    )
    response = SemanticProposalResponseArtifact.create(raw_output_bytes=b"response")
    return SemanticProposalAttempt.create(
        identity=identity,
        raw_output_digest=response.raw_output_digest,
        response_artifact_digest=response.artifact_digest,
        status="complete",
        diagnostics=(),
    )


def _run(proposal: SemanticProposal) -> SemanticProposalRun:
    attempt = _attempt(proposal)
    proposal = SemanticProposal.create(**(proposal.model_dump(mode="python", exclude={"proposal_digest"}) | {"originating_attempt_digest": attempt.attempt_digest}))
    outcome = SegmentProposalOutcome.create(
        segment_id=proposal.segment_id,
        segment_language_route_digest=proposal.language_route.route_digest,
        status=proposal.status,
        proposal_digest=proposal.proposal_digest,
        attempt_digest=attempt.attempt_digest,
        reason_codes=(),
    )
    artifact = proposal.governance_carrier_artifact
    return SemanticProposalRun.create(
        source_id=proposal.source_id,
        source_digest=proposal.source_digest,
        preparation_fingerprint="1" * 64,
        segment_governance_carriers=artifact.segment_governance,
        message_admission_carriers=artifact.message_admissions,
        governance_carrier_artifact=artifact,
        segment_language_routes=SegmentLanguageRouteSet.create(
            source_id=proposal.source_id,
            source_digest=proposal.source_digest,
            routes=(proposal.language_route,),
        ),
        expected_segment_ids=(proposal.segment_id,),
        segment_attempts=(attempt,),
        validated_segments=(proposal,),
        segment_outcomes=(outcome,),
        status="complete",
        diagnostics=(),
    )


def test_attempt_and_run_round_trip_and_reject_cross_coordinate_mutations() -> None:
    proposal = _proposal()
    attempt = _attempt(proposal)
    assert decode_semantic_contract(encode_semantic_contract(attempt), SemanticProposalAttempt) == attempt

    run = _run(proposal)
    assert decode_semantic_contract(encode_semantic_contract(run), SemanticProposalRun) == run
    for wrong_status in {"evidence_only", "failed", "incomplete", "complete", "abstained"} - {run.status}:
        with pytest.raises(ValueError):
            SemanticProposalRun.create(
                **(run.model_dump(mode="python", exclude={"run_fingerprint"}) | {"status": wrong_status})
            )

    outcome = run.segment_outcomes[0]
    body = run.model_dump(mode="python", exclude={"run_fingerprint"})
    body["segment_outcomes"] = (
        SegmentProposalOutcome.create(
            **(outcome.model_dump(mode="python", exclude={"outcome_digest"}) | {"attempt_digest": "f" * 64})
        ),
    )
    with pytest.raises(ValueError, match="outcome must copy its exact attempt"):
        SemanticProposalRun.create(**body)


def test_proposal_digest_rejects_direct_and_closed_codec_substitution() -> None:
    proposal = _proposal()
    payload = proposal.model_dump(mode="python") | {"proposal_digest": "f" * 64}
    with pytest.raises(ValueError, match="proposal_digest mismatch"):
        SemanticProposal.model_validate(payload)

    envelope = decode_typed_value(encode_semantic_contract(proposal))
    assert isinstance(envelope, dict)
    with pytest.raises(SemanticContractCodecError, match="validation failed"):
        decode_semantic_contract(
            encode_typed_value({**envelope, "payload": payload}), SemanticProposal
        )


def test_abstained_run_and_partial_to_failed_repair_are_derived_and_closed() -> None:
    proposal = _proposal()
    abstained = SemanticProposal.create(
        **(
            proposal.model_dump(mode="python", exclude={"proposal_digest"})
            | {
                "status": "abstained",
                "facts": (),
                "corrections": (),
                "retractions": (),
                "action_states": (),
                "identity_operations": (),
            }
        )
    )
    attempt = _attempt(abstained)
    attempt = SemanticProposalAttempt.create(
        **(attempt.model_dump(mode="python", exclude={"attempt_digest"}) | {"status": "abstained"})
    )
    abstained = SemanticProposal.create(
        **(
            abstained.model_dump(mode="python", exclude={"proposal_digest"})
            | {"originating_attempt_digest": attempt.attempt_digest}
        )
    )
    outcome = SegmentProposalOutcome.create(
        segment_id=abstained.segment_id,
        segment_language_route_digest=abstained.language_route.route_digest,
        status="abstained",
        proposal_digest=abstained.proposal_digest,
        attempt_digest=attempt.attempt_digest,
        reason_codes=(),
    )
    artifact = abstained.governance_carrier_artifact
    run = SemanticProposalRun.create(
        source_id=abstained.source_id,
        source_digest=abstained.source_digest,
        preparation_fingerprint="1" * 64,
        segment_governance_carriers=artifact.segment_governance,
        message_admission_carriers=artifact.message_admissions,
        governance_carrier_artifact=artifact,
        segment_language_routes=SegmentLanguageRouteSet.create(
            source_id=abstained.source_id, source_digest=abstained.source_digest, routes=(abstained.language_route,)
        ),
        expected_segment_ids=(abstained.segment_id,),
        segment_attempts=(attempt,),
        validated_segments=(abstained,),
        segment_outcomes=(outcome,),
        status="abstained",
        diagnostics=(),
    )
    assert run.status == "abstained"
    for wrong_status in {"evidence_only", "failed", "incomplete", "complete", "abstained"} - {run.status}:
        with pytest.raises(ValueError):
            SemanticProposalRun.create(
                **(run.model_dump(mode="python", exclude={"run_fingerprint"}) | {"status": wrong_status})
            )

    partial = SemanticProposalAttempt.create(
        **(_attempt(proposal).model_dump(mode="python", exclude={"attempt_digest"}) | {"status": "partial"})
    )
    failed_identity = SemanticProposalAttemptIdentity.create(
        **(
            partial.identity.model_dump(mode="python", exclude={"attempt_identity_digest"})
            | {"attempt_number": 1}
        )
    )
    failed = SemanticProposalAttempt.create(
        identity=failed_identity,
        raw_output_digest=None,
        response_artifact_digest=None,
        status="failed",
        diagnostics=(),
    )
    failed_outcome = SegmentProposalOutcome.create(
        segment_id=proposal.segment_id,
        segment_language_route_digest=proposal.language_route.route_digest,
        status="failed",
        proposal_digest=None,
        attempt_digest=failed.attempt_digest,
        reason_codes=(),
    )
    artifact = proposal.governance_carrier_artifact
    with pytest.raises(ValueError, match="repair after artifact-bearing partial or failure"):
        SemanticProposalRun.create(
            source_id=proposal.source_id, source_digest=proposal.source_digest, preparation_fingerprint="1" * 64,
            segment_governance_carriers=artifact.segment_governance, message_admission_carriers=artifact.message_admissions,
            governance_carrier_artifact=artifact,
            segment_language_routes=SegmentLanguageRouteSet.create(source_id=proposal.source_id, source_digest=proposal.source_digest, routes=(proposal.language_route,)),
            expected_segment_ids=(proposal.segment_id,), segment_attempts=(partial, failed), validated_segments=(),
            segment_outcomes=(failed_outcome,), status="failed", diagnostics=(),
        )


def test_run_rejects_proposal_owned_or_context_span_substitution() -> None:
    proposal = _proposal()
    attempt = _attempt(proposal)
    substituted_identity = SemanticProposalAttemptIdentity.create(
        **(
            attempt.identity.model_dump(mode="python", exclude={"attempt_identity_digest"})
            | {"owned_text": proposal.context_text, "context_text": proposal.context_text}
        )
    )
    substituted_attempt = SemanticProposalAttempt.create(
        identity=substituted_identity,
        raw_output_digest=attempt.raw_output_digest,
        response_artifact_digest=attempt.response_artifact_digest,
        status="complete",
        diagnostics=(),
    )
    proposal = SemanticProposal.create(
        **(proposal.model_dump(mode="python", exclude={"proposal_digest"}) | {"originating_attempt_digest": substituted_attempt.attempt_digest})
    )
    outcome = SegmentProposalOutcome.create(
        segment_id=proposal.segment_id, segment_language_route_digest=proposal.language_route.route_digest,
        status="complete", proposal_digest=proposal.proposal_digest, attempt_digest=substituted_attempt.attempt_digest,
        reason_codes=(),
    )
    artifact = proposal.governance_carrier_artifact
    with pytest.raises(ValueError, match="validated proposal must exactly match its attempt coordinate"):
        SemanticProposalRun.create(
            source_id=proposal.source_id, source_digest=proposal.source_digest, preparation_fingerprint="1" * 64,
            segment_governance_carriers=artifact.segment_governance, message_admission_carriers=artifact.message_admissions,
            governance_carrier_artifact=artifact,
            segment_language_routes=SegmentLanguageRouteSet.create(source_id=proposal.source_id, source_digest=proposal.source_digest, routes=(proposal.language_route,)),
            expected_segment_ids=(proposal.segment_id,), segment_attempts=(substituted_attempt,), validated_segments=(proposal,),
            segment_outcomes=(outcome,), status="complete", diagnostics=(),
        )


@pytest.mark.parametrize(
    ("attempt_status", "outcome_status", "run_status"),
    [
        ("partial", "evidence_only", "evidence_only"),
        ("failed", "failed", "failed"),
    ],
)
def test_run_terminal_attempt_outcomes_derive_evidence_only_or_failed_status(
    attempt_status: str, outcome_status: str, run_status: str
) -> None:
    proposal = _proposal()
    attempt = _attempt(proposal)
    if attempt_status == "failed":
        attempt = SemanticProposalAttempt.create(
            **(
                attempt.model_dump(mode="python", exclude={"attempt_digest"})
                | {"raw_output_digest": None, "response_artifact_digest": None, "status": "failed"}
            )
        )
    else:
        attempt = SemanticProposalAttempt.create(
            **(attempt.model_dump(mode="python", exclude={"attempt_digest"}) | {"status": "partial"})
        )
    outcome = SegmentProposalOutcome.create(
        segment_id=proposal.segment_id,
        segment_language_route_digest=proposal.language_route.route_digest,
        status=outcome_status,
        proposal_digest=None,
        attempt_digest=attempt.attempt_digest,
        reason_codes=(),
    )
    artifact = proposal.governance_carrier_artifact
    values = {
        "source_id": proposal.source_id,
        "source_digest": proposal.source_digest,
        "preparation_fingerprint": "1" * 64,
        "segment_governance_carriers": artifact.segment_governance,
        "message_admission_carriers": artifact.message_admissions,
        "governance_carrier_artifact": artifact,
        "segment_language_routes": SegmentLanguageRouteSet.create(
            source_id=proposal.source_id, source_digest=proposal.source_digest, routes=(proposal.language_route,)
        ),
        "expected_segment_ids": (proposal.segment_id,),
        "segment_attempts": (attempt,),
        "validated_segments": (),
        "segment_outcomes": (outcome,),
        "status": run_status,
        "diagnostics": (),
    }
    run = SemanticProposalRun.create(**values)
    assert run.status == run_status
    for wrong_status in {"evidence_only", "failed", "incomplete", "complete", "abstained"} - {run_status}:
        with pytest.raises(ValueError):
            SemanticProposalRun.create(**(values | {"status": wrong_status}))


def test_source_context_closed_envelope_rejects_missing_extra_and_digest_mutation() -> None:
    context = SourceSemanticContext.create(
        source_id="source-a",
        source_digest="a" * 64,
        trigger_mode=ExtractionTriggerMode.IMMEDIATE,
        provenance_digest="b" * 64,
        temporal_references=(),
        received_at=datetime(2026, 8, 5, tzinfo=UTC),
        retained_at=datetime(2026, 8, 5, tzinfo=UTC),
        source_effective_interval_evidence=None,
        provider_egress_policy_fingerprint="c" * 64,
        governance_policy_fingerprint="d" * 64,
        trust_policy_fingerprint="e" * 64,
    )
    assert decode_semantic_contract(encode_semantic_contract(context), SourceSemanticContext) == context
    envelope = {
        "schema": "memorii.semantic-ingestion.contract-envelope.v1",
        "kind": "source_semantic_context",
        "payload": context.model_dump(mode="python"),
    }
    envelope["payload"] = copy.deepcopy(envelope["payload"])
    envelope["payload"].pop("context_digest")
    with pytest.raises(SemanticContractCodecError, match="validation failed"):
        decode_semantic_contract(
            encode_typed_value(envelope),
            SourceSemanticContext,
        )
    envelope["payload"] = context.model_dump(mode="python") | {"unexpected": True}
    with pytest.raises(SemanticContractCodecError, match="validation failed"):
        decode_semantic_contract(
            encode_typed_value(envelope),
            SourceSemanticContext,
        )


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(_proposal(), id="proposal"),
        pytest.param(_request_artifact(_proposal()), id="request_artifact"),
        pytest.param(SemanticProposalResponseArtifact.create(raw_output_bytes=b"response"), id="response_artifact"),
    ],
)
def test_concrete_proposal_contract_codecs_reject_unknown_envelope_and_scalar_payload(
    value: object,
) -> None:
    assert isinstance(value, (SemanticProposal, SemanticProposalRequestArtifact, SemanticProposalResponseArtifact))
    encoded = encode_semantic_contract(value)
    envelope = decode_typed_value(encoded)
    assert isinstance(envelope, dict)
    assert decode_semantic_contract(encoded, type(value)) == value
    with pytest.raises(SemanticContractCodecError):
        decode_semantic_contract(encode_typed_value({**envelope, "kind": "future_contract"}), type(value))
    with pytest.raises(SemanticContractCodecError):
        decode_semantic_contract(encode_typed_value({**envelope, "payload": "not-a-contract"}), type(value))


def test_attempt_run_concrete_codecs_reject_unknown_envelope_and_scalar_payload() -> None:
    proposal = _proposal()
    attempt = _attempt(proposal)
    run = _run(proposal)
    values = (attempt.identity, attempt, run.segment_outcomes[0], run)
    for value in values:
        encoded = encode_semantic_contract(value)
        envelope = decode_typed_value(encoded)
        assert isinstance(envelope, dict)
        assert decode_semantic_contract(encoded, type(value)) == value
        with pytest.raises(SemanticContractCodecError):
            decode_semantic_contract(encode_typed_value({**envelope, "kind": "future_contract"}), type(value))
        with pytest.raises(SemanticContractCodecError):
            decode_semantic_contract(encode_typed_value({**envelope, "payload": ()}), type(value))
def test_step_four_leaf_contracts_are_content_addressed_and_closed() -> None:
    feature = LinguisticFeature.create(name="Number", value="Sing")
    assert decode_semantic_contract(encode_semantic_contract(feature), LinguisticFeature) == feature

    manifest = AnalyzerManifest.create(
        analyzer_id="stanza-en",
        analyzer_kind="stanza",
        library_version="1.0",
        resource_manifest_digest="1" * 64,
        model_file_hashes=("2" * 64,),
        processor_configuration_digest="3" * 64,
        adapter_version="1",
        supported_languages=("en",),
        analyzer_fingerprint="4" * 64,
    )
    assert decode_semantic_contract(encode_semantic_contract(manifest), AnalyzerManifest) == manifest
    with pytest.raises(ValueError, match="manifest_digest mismatch"):
        AnalyzerManifest.model_validate(manifest.model_dump() | {"manifest_digest": "f" * 64})

    resolver = TemporalResolverManifest.create(
        binary_digest="5" * 64,
        ruleset_version="1",
        locale_map_digest="6" * 64,
        timezone_policy_digest="7" * 64,
        adapter_schema_digest="8" * 64,
        supported_construction_families=("absolute",),
    )
    assert decode_semantic_contract(encode_semantic_contract(resolver), TemporalResolverManifest) == resolver
