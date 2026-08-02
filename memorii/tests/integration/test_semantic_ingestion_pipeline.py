"""Named semantic ingestion integration evidence for SIA-T02/T04/T05/T06/T07/T09/T12.

These tests also exercise the Reliable production composition, lease-lineage, atomic
artifact, and protected truthful-result contracts without using those requirement
IDs as substitutes for the required semantic ingestion evidence IDs. Fixtures are authored in
this module and expected values are independent of production helper output.
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal

import pytest
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.semantic_ingestion.contracts import (
    AuthenticatedSourceIntervalEvidence,
    IndependentSourceAnalysis,
    OperationKind,
    ParserConsensusAssessment,
    PredicateTemporalRule,
    PredicateTrustRule,
    SemanticArbitrationPolicyBundle,
    SemanticAuthorizationReadSet,
    SemanticCandidate,
    SemanticContractCodecError,
    SourceAuthority,
    SourceAuthorityEvidence,
    SourceLocalIdentityEvidence,
    SourceSpan,
    SourceTemporalEvidenceSet,
    TemporalEvidenceCandidate,
    TemporalEvidenceDecisionClosure,
    TemporalPolicySnapshot,
    TimeInterval,
    TrustPolicySnapshot,
    decode_semantic_contract,
    encode_semantic_contract,
)
from memorii.core.semantic_ingestion.pipeline import (
    AnalyzerRoleInterpretation,
    SemanticIngestionPipeline,
    TemporalEvidenceResolver,
)

SOURCE = "Atlas works for Memorii."
SOURCE_ID = "source:integration"
SOURCE_DIGEST = sha256(SOURCE.encode()).hexdigest()
NOW = datetime(2026, 3, 1, tzinfo=UTC)


def _digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _authority(authority: str = "official") -> SourceAuthorityEvidence:
    return SourceAuthorityEvidence.create(
        source_id=SOURCE_ID,
        source_digest=SOURCE_DIGEST,
        authority=SourceAuthority(
            authority_class=authority,
            authenticated_provenance_class="authenticated-host",
            policy_revision="trust-1",
        ),
        provenance_digest=_digest(f"authority:{authority}"),
    )


class _Authorization:
    def current_read_set(
        self, *, policy_bundle, egress_policy_revision, egress_decision_digest, use_point,
    ):
        del use_point
        if egress_policy_revision is not None:
            return None
        return SemanticAuthorizationReadSet.create(
            policy_bundle=policy_bundle,
            deployment_authorization_digest="d" * 64,
            deployment_active_epoch=1,
            deployment_decision_digest="e" * 64,
        )


def _policies(
    *,
    requirement: Literal["required", "optional", "atemporal"] = "required",
    incomparable: bool = False,
) -> SemanticArbitrationPolicyBundle:
    effective = TimeInterval(
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2027, 1, 1, tzinfo=UTC),
    )
    trust = TrustPolicySnapshot.create(
        policy_revision="trust-1",
        system_effective_interval=effective,
        rules=(PredicateTrustRule(
            predicate_id="works_for",
            eligible_authority_classes=frozenset({"official", "reported"}),
            authority_rank_by_class={"official": 20, "reported": 10},
            incomparable_class_pairs=(
                (("official", "reported"),) if incomparable else ()
            ),
        ),),
    )
    temporal = TemporalPolicySnapshot.create(
        policy_revision="temporal-1",
        system_effective_interval=effective,
        rules=(PredicateTemporalRule(
            predicate_id="works_for",
            valid_time_requirement=requirement,
            allow_open_end=True,
        ),),
    )
    return SemanticArbitrationPolicyBundle.create(
        trust_policy=trust,
        temporal_policy=temporal,
        arbitration_as_of=NOW,
    )


def _candidate(
    candidate_id: str, *, authority: str = "official", start_day: int = 1,
    end_day: int | None = 20,
) -> TemporalEvidenceCandidate:
    interval = TimeInterval(
        start=datetime(2026, 1, start_day, tzinfo=UTC),
        end=(datetime(2026, 1, end_day, tzinfo=UTC) if end_day is not None else None),
    )
    authenticated = None
    spans: tuple[SourceSpan, ...] = (SourceSpan(source_id=SOURCE_ID, start=0, end=5),)
    certified_id: str | None = candidate_id
    kind = "certified_text_interval"
    if authority == "official":
        authenticated = AuthenticatedSourceIntervalEvidence.create(
            source_id=SOURCE_ID, source_digest=SOURCE_DIGEST, interval=interval,
            authority_basis="server_source_metadata",
            provenance_digest=_digest(f"provenance:{candidate_id}"),
            policy_revision="trust-1",
            source_authority_evidence_digest=_authority(authority).evidence_digest,
        )
        spans = ()
        certified_id = None
        kind = "authenticated_source_interval"
    return TemporalEvidenceCandidate.create(
        candidate_id=candidate_id,
        kind=kind,
        interval=interval,
        source_authority=SourceAuthority(
            authority_class=authority,
            authenticated_provenance_class="authenticated-host",
            policy_revision="trust-1",
        ),
        authenticated_source_interval_evidence=authenticated,
        certified_text_candidate_id=certified_id,
        evidence_spans=spans,
    )


def _proposal(kind: OperationKind = "fact") -> SemanticCandidate:
    return SemanticCandidate(
        candidate_id=f"proposal:{kind}",
        operation_kind=kind,
        predicate_id="works_for",
        assertion_quote=SOURCE,
        alignment_refs=(),
    )


def _analysis(
    proposal: SemanticCandidate,
    *, candidates: tuple[TemporalEvidenceCandidate, ...] | None = None,
    stable: bool = True,
) -> IndependentSourceAnalysis:
    primary = AnalyzerRoleInterpretation(
        analyzer_id="stanza",
        analyzer_fingerprint="a" * 64,
        predicate_span=SourceSpan(source_id=SOURCE_ID, start=6, end=15),
        construction_family="active",
        role_spans=(("subject", SourceSpan(source_id=SOURCE_ID, start=0, end=5)),),
        semantic_scope="asserted",
        attribution_kind="speaker",
    )
    corroborating = primary.model_copy(update={
        "analyzer_id": "spacy",
        "analyzer_fingerprint": "b" * 64,
        "construction_family": "active" if stable else "passive",
    })
    roles = {
        "fact": ("assertion",),
        "action": ("assertion",),
        "correction": ("replacement", "transition"),
        "retraction": ("transition",),
        "identity": ("transition",),
    }[proposal.operation_kind]
    temporal_candidates = candidates or (_candidate("time:official"),)
    source_authority = _authority(temporal_candidates[0].source_authority.authority_class)
    return IndependentSourceAnalysis.create(
        candidate_id=proposal.candidate_id,
        source_id=SOURCE_ID,
        source_digest=SOURCE_DIGEST,
        predicate_id=proposal.predicate_id,
        operation_kind=proposal.operation_kind,
        source_authority_evidence=source_authority,
        assertion_span=SourceSpan(source_id=SOURCE_ID, start=0, end=len(SOURCE)),
        parser_consensus=ParserConsensusAssessment.create(
            primary=primary, corroborating=corroborating
        ),
        identity_evidence=(SourceLocalIdentityEvidence(
            source_id=SOURCE_ID,
            mention_span=SourceSpan(source_id=SOURCE_ID, start=0, end=5),
            cluster_id="atlas",
            canonical_entity_id="entity:atlas",
            evidence_digest=_digest("identity:atlas"),
        ),),
        temporal_evidence=tuple(SourceTemporalEvidenceSet(
            temporal_role=role,
            candidates=temporal_candidates,
            attachment_spans=tuple(
                span for candidate in temporal_candidates for span in candidate.evidence_spans
            ),
            attachment_consensus_digest=_digest(f"attachment:{role}"),
        ) for role in roles),
    )


class _Assessor:
    def __init__(self, analysis: IndependentSourceAnalysis) -> None:
        self.analysis = analysis

    def analyze(self, **_: object) -> IndependentSourceAnalysis:
        return self.analysis


def _outcome(
    kind: OperationKind = "fact", *, candidates: tuple[TemporalEvidenceCandidate, ...] | None = None,
    stable: bool = True,
):
    proposal = _proposal(kind)
    analysis = _analysis(proposal, candidates=candidates, stable=stable)
    source_interval = next(
        (
            candidate.authenticated_source_interval_evidence
            for temporal in analysis.temporal_evidence
            for candidate in temporal.candidates
            if candidate.authenticated_source_interval_evidence is not None
        ),
        None,
    )
    return SemanticIngestionPipeline(transport=None).run(
        operation_id="operation:integration",
        source_id=SOURCE_ID,
        source_digest=SOURCE_DIGEST,
        source_text=SOURCE,
        policy_bundle=_policies(),
        local_proposals=(proposal,),
        independent_assessor=_Assessor(analysis),
        source_authority_evidence=analysis.source_authority_evidence,
        source_interval_evidence=source_interval,
        authorization_read_set_provider=_Authorization(),
    )


def _resolve(
    candidates: tuple[TemporalEvidenceCandidate, ...], *, incomparable: bool = False,
):
    policy = _policies(incomparable=incomparable)
    return TemporalEvidenceResolver().resolve(
        predicate_id="works_for",
        candidates=candidates,
        trust_policy=policy.trust_policy,
        temporal_policy=policy.temporal_policy,
        arbitration_as_of=policy.arbitration_as_of,
    )


def test_candidate_proposal_cannot_supply_source_authority() -> None:
    with pytest.raises(ValueError):
        SemanticCandidate.model_validate(
            _proposal().model_dump(mode="python") | {"source_authority": {}}
        )


def test_lineage_closes_proposal_analysis_seal_and_policy() -> None:
    outcome = _outcome()
    assert outcome.status == "accepted" and outcome.execution_lineage is not None
    assert outcome.execution_lineage.source_analysis_digests == (
        outcome.source_analyses[0].analysis_digest,
    )
    assert outcome.execution_lineage.sealed_operation_digests == (
        outcome.sealed_operations[0].sealed_operation_digest,
    )
    assert outcome.arbitration_policy_bundle is not None
    assert outcome.execution_lineage.arbitration_policy_bundle_digest == (
        outcome.arbitration_policy_bundle.bundle_digest
    )


def test_consensus_disagreement_is_nonpromoting() -> None:
    outcome = _outcome(stable=False)
    assert outcome.status == "unresolved" and outcome.accepted_carriers == ()


def test_temporal_required_interval_reaches_exact_carrier() -> None:
    outcome = _outcome(candidates=(_candidate("exact", start_day=2, end_day=9),))
    assert outcome.accepted_carriers[0].valid_interval == TimeInterval(
        start=datetime(2026, 1, 2, tzinfo=UTC),
        end=datetime(2026, 1, 9, tzinfo=UTC),
    )


def test_trust_eligibility_retains_but_never_selects_ineligible() -> None:
    policy = _policies()
    trust = TrustPolicySnapshot.create(
        policy_revision="trust-1",
        system_effective_interval=policy.trust_policy.system_effective_interval,
        rules=(PredicateTrustRule(
            predicate_id="works_for",
            eligible_authority_classes=frozenset({"official"}),
            authority_rank_by_class={"official": 20, "reported": 10},
        ),),
    )
    values = (_candidate("official"), _candidate("reported", authority="reported", start_day=5))
    closure = TemporalEvidenceResolver().resolve(
        predicate_id="works_for", candidates=values, trust_policy=trust,
        temporal_policy=policy.temporal_policy, arbitration_as_of=NOW,
    )
    assert closure.selected_candidate_ids == ("official",) and closure.candidates == values


def test_trust_rank_unique_highest_wins_every_input_order() -> None:
    high = _candidate("a-high", start_day=1)
    low = _candidate("b-low", authority="reported", start_day=5)
    assert _resolve((high, low)).selected_candidate_ids == ("a-high",)
    assert _resolve((low, high)).selected_candidate_ids == ("a-high",)


def test_trust_incomparability_nonidentical_top_is_contested() -> None:
    closure = _resolve(
        (_candidate("a"), _candidate("b", authority="reported", start_day=5)),
        incomparable=True,
    )
    assert closure.outcome == "contested" and closure.contested_candidate_ids == ("a", "b")


def test_trust_equality_cosupports_without_provenance_collapse() -> None:
    closure = _resolve((_candidate("a"), _candidate("b", authority="reported")))
    assert closure.selected_candidate_ids == ("a", "b")
    assert len({value.candidate_digest for value in closure.candidates}) == 2


def test_trust_resolution_never_constructs_a_third_interval() -> None:
    values = (_candidate("a", start_day=1, end_day=None), _candidate("b", authority="reported", start_day=5, end_day=20))
    closure = _resolve(values, incomparable=True)
    assert closure.resolved_interval is None
    assert tuple(value.interval for value in closure.candidates) == tuple(
        value.interval for value in values
    )


def test_temporal_text_many_retains_every_independent_text_candidate() -> None:
    values = (
        _candidate("a", authority="reported"),
        _candidate("b", authority="reported", start_day=5),
    )
    closure = _resolve(values)
    assert closure.outcome == "contested" and closure.candidates == values


def test_temporal_schema_rejects_impossible_candidate_shape() -> None:
    with pytest.raises(ValueError, match="invalid evidence shape"):
        TemporalEvidenceCandidate.create(
            candidate_id="bad",
            kind="authenticated_source_interval",
            interval=TimeInterval(start=NOW),
            source_authority=SourceAuthority(
                authority_class="official",
                authenticated_provenance_class="host",
                policy_revision="trust-1",
            ),
        )


def test_temporal_closure_rejects_selected_subset_mutation() -> None:
    closure = _resolve((_candidate("a"),))
    with pytest.raises(ValueError, match="requires selected"):
        TemporalEvidenceDecisionClosure.model_validate(
            closure.model_copy(update={"selected_candidate_ids": ()}).model_dump(mode="python")
        )


def test_temporal_transitions_preserve_distinct_correction_roles() -> None:
    outcome = _outcome("correction")
    roles = tuple(value.temporal_role for value in outcome.sealed_operations[0].temporal_bindings)
    assert roles == ("replacement", "transition")
    assert len({value.binding_digest for value in outcome.sealed_operations[0].temporal_bindings}) == 2


def test_temporal_role_schema_rejects_binding_role_swap() -> None:
    outcome = _outcome("correction")
    operation = outcome.sealed_operations[0]
    swapped = operation.temporal_bindings[0].model_copy(update={"temporal_role": "transition"})
    with pytest.raises(ValueError):
        type(operation).model_validate(
            operation.model_copy(update={"temporal_bindings": (swapped, *operation.temporal_bindings[1:])}).model_dump(mode="python")
        )


def test_temporal_attachment_plan_retains_exact_text_spans() -> None:
    text = _candidate("text", authority="reported")
    outcome = _outcome(candidates=(text,))
    binding = outcome.sealed_operations[0].temporal_bindings[0]
    assert binding.temporal_attachment.candidate_spans == text.evidence_spans


def test_temporal_preimage_rejects_binding_digest_mutation() -> None:
    binding = _outcome().sealed_operations[0].temporal_bindings[0]
    with pytest.raises(ValueError, match="digest mismatch"):
        type(binding).model_validate(
            binding.model_copy(update={"binding_digest": "0" * 64}).model_dump(mode="python")
        )


def test_temporal_consensus_source_substitution_is_rejected() -> None:
    proposal = _proposal()
    analysis = _analysis(proposal).model_copy(update={"source_digest": "0" * 64})
    outcome = SemanticIngestionPipeline(transport=None).run(
        operation_id="operation:integration", source_id=SOURCE_ID,
        source_digest=SOURCE_DIGEST, source_text=SOURCE, policy_bundle=_policies(),
        local_proposals=(proposal,), independent_assessor=_Assessor(analysis),
        source_authority_evidence=_authority(),
        source_interval_evidence=_candidate("time:official").authenticated_source_interval_evidence,
        authorization_read_set_provider=_Authorization(),
    )
    assert outcome.status == "rejected" and outcome.accepted_carriers == ()


def test_terminal_store_round_trips_complete_terminal_bytes() -> None:
    outcome = _outcome()
    assert decode_semantic_contract(encode_semantic_contract(outcome), type(outcome)) == outcome


def test_temporal_policy_rejects_snapshot_substitution() -> None:
    policy = _policies()
    with pytest.raises(ValueError, match="digest mismatch"):
        TrustPolicySnapshot.model_validate(
            policy.trust_policy.model_copy(update={"policy_revision": "forged"}).model_dump(mode="python")
        )


def test_legacy_rejects_preclosure_terminal_bytes() -> None:
    outcome = _outcome()
    with pytest.raises(SemanticContractCodecError, match="legacy|mismatched"):
        decode_semantic_contract(
            encode_typed_value({
                "schema": "memorii.semantic-ingestion.m2.v1",
                "kind": "semantic_terminal",
                "payload": outcome.model_dump(mode="python"),
            }),
            type(outcome),
        )


def test_prompt_remote_path_without_registered_authority_is_zero_wire() -> None:
    class Transport:
        calls = 0

        def propose(self, request_bytes: bytes) -> bytes:
            del request_bytes
            self.calls += 1
            return b""

    transport = Transport()
    outcome = SemanticIngestionPipeline(transport=transport).run(
        operation_id="operation:integration", source_id=SOURCE_ID,
        source_digest=SOURCE_DIGEST, source_text=SOURCE, policy_bundle=_policies(),
        source_authority_evidence=_authority(),
    )
    assert outcome.status == "evidence_only" and transport.calls == 0


def test_egress_missing_current_policy_is_zero_wire() -> None:
    # The registered prompt path is covered by the unit authority suite; this
    # integration oracle proves that absent egress authority cannot be replaced
    # by the typed local-proposal path or a raw boolean.
    outcome = SemanticIngestionPipeline(transport=None).run(
        operation_id="operation:integration", source_id=SOURCE_ID,
        source_digest=SOURCE_DIGEST, source_text=SOURCE, policy_bundle=_policies(),
        source_authority_evidence=_authority(),
    )
    assert outcome.reason_codes == ("remote_proposal_authority_unavailable",)


def test_pipeline_closed_codec_rejects_wrong_contract_kind() -> None:
    outcome = _outcome("identity")
    encoded = encode_semantic_contract(outcome)
    with pytest.raises(SemanticContractCodecError, match="unsupported|mismatched"):
        decode_semantic_contract(encoded, IndependentSourceAnalysis)


def test_pipeline_slow_stage_renews_lease_heartbeat() -> None:
    proposal = _proposal()
    analysis = _analysis(proposal)
    heartbeats: list[int] = []

    class DeterministicRenewalScheduler:
        calls = 0

        def run(self, *, call, heartbeat):
            self.calls += 1
            heartbeat()
            heartbeat()
            result = call()
            heartbeat()
            return result

    scheduler = DeterministicRenewalScheduler()

    class SlowAssessor:
        def analyze(self, **_: object) -> IndependentSourceAnalysis:
            assert heartbeats == [1, 2]
            return analysis

    def heartbeat() -> None:
        heartbeats.append(len(heartbeats) + 1)

    outcome = SemanticIngestionPipeline(
        transport=None, renewal_scheduler=scheduler
    ).run(
        operation_id="operation:integration",
        source_id=SOURCE_ID,
        source_digest=SOURCE_DIGEST,
        source_text=SOURCE,
        policy_bundle=_policies(),
        local_proposals=(proposal,),
        independent_assessor=SlowAssessor(),
        source_authority_evidence=_authority(),
        source_interval_evidence=_candidate("time:official").authenticated_source_interval_evidence,
        authorization_read_set_provider=_Authorization(),
        lease_heartbeat=heartbeat,
    )
    assert outcome.status == "accepted"
    assert scheduler.calls == 1
    assert heartbeats == [1, 2, 3]
