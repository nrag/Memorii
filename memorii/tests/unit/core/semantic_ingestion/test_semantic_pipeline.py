from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.prompts.registry import PromptRegistry
from memorii.core.prompts.runtime_manifest import PromptOwner
from memorii.core.semantic_ingestion.contracts import (
    AuthenticatedSourceIntervalEvidence,
    IndependentSourceAnalysis,
    ParserConsensusAssessment,
    PredicateTemporalRule,
    PredicateTrustRule,
    SemanticArbitrationPolicyBundle,
    SemanticAuthorizationReadSet,
    SemanticCandidate,
    SemanticContractCodecError,
    SemanticEgressAuthorizationBinding,
    SourceAuthority,
    SourceAuthorityEvidence,
    SourceLocalIdentityEvidence,
    SourceSpan,
    SourceTemporalEvidenceSet,
    TemporalEvidenceCandidate,
    TemporalPolicySnapshot,
    TimeInterval,
    TrustPolicySnapshot,
    contract_digest,
    decode_semantic_contract,
    encode_semantic_contract,
)
from memorii.core.semantic_ingestion.egress import ProviderEgressBinding, ProviderEgressDecision
from memorii.core.semantic_ingestion.local_analyzer import ProductionLocalSemanticAnalyzer
from memorii.core.semantic_ingestion.pipeline import AnalyzerRoleInterpretation, SemanticIngestionPipeline
from memorii.core.semantic_ingestion.prompt_authority import SemanticPromptAuthority

SOURCE = "Atlas works for Memorii."
SOURCE_ID = "source"
SOURCE_DIGEST = sha256(SOURCE.encode()).hexdigest()
ARBITRATION = datetime(2026, 3, 1, tzinfo=UTC)


class CaptureTransport:
    def __init__(self, replies: list[bytes]) -> None:
        self.replies = replies
        self.requests: list[bytes] = []

    def propose(self, request_bytes: bytes) -> bytes:
        self.requests.append(request_bytes)
        return self.replies.pop(0)


class Assessor:
    def __init__(self, analyses: dict[str, IndependentSourceAnalysis]) -> None:
        self.analyses = analyses

    def analyze(
        self, *, proposal, source_id: str, source_digest: str, source_text: str,
        source_authority_evidence, source_interval_evidence,
    ):
        return self.analyses.get(proposal.candidate_id)


class Authorization:
    def current_read_set(
        self, *, policy_bundle, egress_policy_revision, egress_decision_digest, use_point,
    ):
        del use_point
        return SemanticAuthorizationReadSet.create(
            policy_bundle=policy_bundle,
            egress_policy_revision=egress_policy_revision,
            egress_decision_digest=egress_decision_digest,
            egress_binding=(
                None if egress_policy_revision is None else SemanticEgressAuthorizationBinding.model_validate(
                    _remote_binding().model_dump(mode="python")
                )
            ),
            deployment_authorization_digest="d" * 64,
            deployment_active_epoch=1,
            deployment_decision_digest="e" * 64,
        )


class RotateBeforeSeal(Authorization):
    def current_read_set(
        self, *, policy_bundle, egress_policy_revision, egress_decision_digest, use_point,
    ):
        read_set = super().current_read_set(
            policy_bundle=policy_bundle,
            egress_policy_revision=egress_policy_revision,
            egress_decision_digest=egress_decision_digest,
            use_point=use_point,
        )
        if use_point == "pre_seal":
            body = read_set.model_dump(mode="python", exclude={"read_set_digest"})
            body["deployment_active_epoch"] = 2
            return SemanticAuthorizationReadSet(
                **body,
                read_set_digest=contract_digest(
                    b"memorii.semantic-ingestion.authorization-read-set.v1", body
                ),
            )
        return read_set


class AllowEgress:
    def current(self, *, binding: ProviderEgressBinding, at: datetime):
        return ProviderEgressDecision.create(
            binding=binding, policy_id="policy", policy_revision=1,
            policy_fingerprint="f" * 64, expires_at=at + timedelta(minutes=1),
        )


def _hex(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _authority() -> SourceAuthorityEvidence:
    return SourceAuthorityEvidence.create(
        source_id=SOURCE_ID,
        source_digest=SOURCE_DIGEST,
        authority=SourceAuthority(
            authority_class="official",
            authenticated_provenance_class="host",
            policy_revision="trust-r1",
        ),
        provenance_digest=_hex("source-authority"),
    )


def _bundle() -> SemanticArbitrationPolicyBundle:
    effective = TimeInterval(
        start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2027, 1, 1, tzinfo=UTC)
    )
    trust = TrustPolicySnapshot.create(
        policy_revision="trust-r1", system_effective_interval=effective,
        rules=(PredicateTrustRule(
            predicate_id="works_for", eligible_authority_classes=frozenset({"official"}),
            authority_rank_by_class={"official": 10},
        ),),
    )
    temporal = TemporalPolicySnapshot.create(
        policy_revision="temporal-r1", system_effective_interval=effective,
        rules=(PredicateTemporalRule(
            predicate_id="works_for", valid_time_requirement="required", allow_open_end=True,
        ),),
    )
    return SemanticArbitrationPolicyBundle.create(
        trust_policy=trust, temporal_policy=temporal, arbitration_as_of=ARBITRATION,
    )


def _temporal(candidate_id: str) -> TemporalEvidenceCandidate:
    interval = TimeInterval(
        start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2026, 2, 1, tzinfo=UTC)
    )
    evidence = AuthenticatedSourceIntervalEvidence.create(
        source_id=SOURCE_ID, source_digest=SOURCE_DIGEST,
        interval=interval, authority_basis="server_source_metadata",
        provenance_digest=_hex("source-interval"),
        policy_revision="trust-r1",
        source_authority_evidence_digest=_authority().evidence_digest,
    )
    return TemporalEvidenceCandidate.create(
        candidate_id=candidate_id, kind="authenticated_source_interval", interval=interval,
        source_authority=SourceAuthority(
            authority_class="official", authenticated_provenance_class="host", policy_revision="trust-r1",
        ),
        authenticated_source_interval_evidence=evidence,
    )


def _proposal(kind: str = "fact") -> SemanticCandidate:
    return SemanticCandidate(
        candidate_id=f"candidate-{kind}", operation_kind=kind,
        predicate_id="works_for", assertion_quote=SOURCE, alignment_refs=(),
    )


def _analysis(proposal: SemanticCandidate) -> IndependentSourceAnalysis:
    first = AnalyzerRoleInterpretation(
        analyzer_id="stanza", analyzer_fingerprint="a" * 64,
        predicate_span=SourceSpan(source_id=SOURCE_ID, start=6, end=11), construction_family="active",
        role_spans=(("subject", SourceSpan(source_id=SOURCE_ID, start=0, end=5)),),
        semantic_scope="asserted", attribution_kind="speaker",
    )
    second = first.model_copy(update={"analyzer_id": "spacy", "analyzer_fingerprint": "b" * 64})
    roles = {
        "fact": ("assertion",), "action": ("assertion",),
        "correction": ("replacement", "transition"),
        "retraction": ("transition",), "identity": ("transition",),
    }[proposal.operation_kind]
    return IndependentSourceAnalysis.create(
        candidate_id=proposal.candidate_id, source_id=SOURCE_ID, source_digest=SOURCE_DIGEST,
        predicate_id=proposal.predicate_id, operation_kind=proposal.operation_kind,
        source_authority_evidence=_authority(),
        assertion_span=SourceSpan(source_id=SOURCE_ID, start=0, end=len(SOURCE)),
        parser_consensus=ParserConsensusAssessment.create(primary=first, corroborating=second),
        identity_evidence=(SourceLocalIdentityEvidence(
            source_id=SOURCE_ID, mention_span=SourceSpan(source_id=SOURCE_ID, start=0, end=5),
            cluster_id="atlas", canonical_entity_id="entity:atlas", evidence_digest=_hex("identity"),
        ),),
        temporal_evidence=tuple(SourceTemporalEvidenceSet(
            temporal_role=role, candidates=(_temporal(f"{role}-time"),), attachment_spans=(),
            attachment_consensus_digest=_hex(f"attachment:{role}"),
        ) for role in roles),
    )


def _accepted(kind: str = "fact", *, operation_id: str = "source-operation"):
    proposal = _proposal(kind)
    return SemanticIngestionPipeline(transport=None).run(
        operation_id=operation_id, source_id=SOURCE_ID, source_digest=SOURCE_DIGEST,
        source_text=SOURCE, policy_bundle=_bundle(), local_proposals=(proposal,),
        independent_assessor=Assessor({proposal.candidate_id: _analysis(proposal)}),
        source_authority_evidence=_authority(),
        source_interval_evidence=_temporal("source-interval").authenticated_source_interval_evidence,
        authorization_read_set_provider=Authorization(),
    )


def _remote_authority():
    prompt = SemanticPromptAuthority.build(
        registry=PromptRegistry(), prompt_ref="semantic_ingestion_proposal:v1",
        owner=PromptOwner.SEMANTIC_INGESTION_PROPOSER, variables={}, source_text=SOURCE,
        metadata={"operation_id": "operation-1"},
    )
    binding = ProviderEgressBinding(
        tenant_id="tenant", source_id=SOURCE_ID, source_digest=SOURCE_DIGEST,
        segment_id="segment", classification="internal", provider="capture", model="capture-v1",
        region="local", retention_mode="none", training_use=False,
    )
    return prompt, binding


def _remote_binding() -> ProviderEgressBinding:
    return _remote_authority()[1]


def test_remote_path_without_registered_prompt_has_zero_wire_calls() -> None:
    transport = CaptureTransport([])
    outcome = SemanticIngestionPipeline(transport=transport).run(
        operation_id="operation-1", source_id=SOURCE_ID, source_digest=SOURCE_DIGEST,
        source_text=SOURCE, policy_bundle=_bundle(), source_authority_evidence=_authority(),
    )
    assert outcome.status == "evidence_only"
    assert outcome.reason_codes == ("remote_proposal_authority_unavailable",)
    assert transport.requests == []


def test_transport_validation_allows_one_registered_repair_only() -> None:
    transport = CaptureTransport([b"not canonical", b"also not canonical"])
    prompt, binding = _remote_authority()
    outcome = SemanticIngestionPipeline(transport=transport).run(
        operation_id="operation-1", source_id=SOURCE_ID, source_digest=SOURCE_DIGEST,
        source_text=SOURCE, policy_bundle=_bundle(), registered_prompt=prompt,
        egress_binding=binding, egress_policy_provider=AllowEgress(),
        current_time_provider=lambda: ARBITRATION,
        source_authority_evidence=_authority(), authorization_read_set_provider=Authorization(),
    )
    assert outcome.status == "rejected" and outcome.attempt_count == 2
    assert len(transport.requests) == 2 and transport.requests[0] != transport.requests[1]


def test_missing_policy_is_evidence_only_before_wire() -> None:
    transport = CaptureTransport([])
    prompt, binding = _remote_authority()
    outcome = SemanticIngestionPipeline(transport=transport).run(
        operation_id="operation-1", source_id=SOURCE_ID, source_digest=SOURCE_DIGEST,
        source_text=SOURCE, policy_bundle=None, registered_prompt=prompt,
        egress_binding=binding, egress_policy_provider=AllowEgress(),
        current_time_provider=lambda: ARBITRATION,
    )
    assert outcome.status == "evidence_only" and transport.requests == []


@pytest.mark.parametrize(
    ("kind", "record_kinds"),
    [
        ("fact", ("claim_assertion",)), ("action", ("action_revision",)),
        ("correction", ("claim_assertion", "temporal_transition")),
        ("retraction", ("temporal_transition",)), ("identity", ("identity_lineage",)),
    ],
)
def test_source_analyses_compile_exact_canonical_carriers(kind: str, record_kinds: tuple[str, ...]) -> None:
    outcome = _accepted(kind)
    assert outcome.status == "accepted"
    assert tuple(value.record_kind for value in outcome.accepted_carriers) == record_kinds
    assert outcome.source_analyses[0].candidate_id == outcome.candidates[0].candidate_id


def test_source_analysis_substitution_is_rejected() -> None:
    proposal = _proposal()
    substituted = _analysis(proposal).model_copy(update={"source_digest": "0" * 64})
    outcome = SemanticIngestionPipeline(transport=None).run(
        operation_id="operation", source_id=SOURCE_ID, source_digest=SOURCE_DIGEST,
        source_text=SOURCE, policy_bundle=_bundle(), local_proposals=(proposal,),
        independent_assessor=Assessor({proposal.candidate_id: substituted}),
        source_authority_evidence=_authority(),
        source_interval_evidence=_temporal("source-interval").authenticated_source_interval_evidence,
        authorization_read_set_provider=Authorization(),
    )
    assert outcome.status == "rejected"


def test_proposer_cannot_supply_source_analysis_fields() -> None:
    proposal = _proposal()
    payload = proposal.model_dump(mode="python") | {"parser_consensus": {}}
    transport = CaptureTransport([encode_typed_value({"candidates": [payload]}), b"invalid"])
    prompt, binding = _remote_authority()
    outcome = SemanticIngestionPipeline(transport=transport).run(
        operation_id="operation", source_id=SOURCE_ID, source_digest=SOURCE_DIGEST,
        source_text=SOURCE, policy_bundle=_bundle(), registered_prompt=prompt,
        egress_binding=binding, egress_policy_provider=AllowEgress(),
        current_time_provider=lambda: ARBITRATION,
        source_authority_evidence=_authority(), authorization_read_set_provider=Authorization(),
    )
    assert outcome.status == "rejected" and outcome.accepted_carriers == ()


def test_closed_codec_round_trip_rejects_legacy_and_wrong_contract_kind() -> None:
    outcome = _accepted("identity")
    assert decode_semantic_contract(encode_semantic_contract(outcome), type(outcome)) == outcome
    with pytest.raises(SemanticContractCodecError, match="legacy|mismatched"):
        decode_semantic_contract(
            encode_typed_value({
                "schema": "memorii.semantic-ingestion.m2.v1", "kind": "semantic_terminal",
                "payload": outcome.model_dump(mode="python"),
            }),
            type(outcome),
        )


def test_production_local_analyzer_emits_exact_authenticated_source_evidence() -> None:
    analyzer = ProductionLocalSemanticAnalyzer()
    proposals = analyzer.propose(
        source_id=SOURCE_ID, source_digest=SOURCE_DIGEST, source_text=SOURCE
    )
    interval = _temporal("source-interval").authenticated_source_interval_evidence
    assert interval is not None
    terminal = SemanticIngestionPipeline(transport=None).run(
        operation_id="production-local",
        source_id=SOURCE_ID,
        source_digest=SOURCE_DIGEST,
        source_text=SOURCE,
        policy_bundle=_bundle(),
        local_proposals=proposals,
        independent_assessor=analyzer,
        source_authority_evidence=_authority(),
        source_interval_evidence=interval,
        authorization_read_set_provider=Authorization(),
    )
    assert terminal.status == "accepted"
    analysis = terminal.source_analyses[0]
    assert analysis.identity_evidence == ()
    assert analysis.assertion_span == SourceSpan(
        source_id=SOURCE_ID, start=0, end=len(SOURCE)
    )
    assert analysis.source_authority_evidence == _authority()


def test_authorization_rotation_before_seal_discards_candidate_without_commit_artifacts() -> None:
    proposal = _proposal()
    terminal = SemanticIngestionPipeline(transport=None).run(
        operation_id="rotated-before-seal",
        source_id=SOURCE_ID,
        source_digest=SOURCE_DIGEST,
        source_text=SOURCE,
        policy_bundle=_bundle(),
        local_proposals=(proposal,),
        independent_assessor=Assessor({proposal.candidate_id: _analysis(proposal)}),
        source_authority_evidence=_authority(),
        source_interval_evidence=_temporal("source-interval").authenticated_source_interval_evidence,
        authorization_read_set_provider=RotateBeforeSeal(),
    )
    assert terminal.status == "evidence_only"
    assert terminal.reason_codes == ("authorization_changed_before_sealing",)
    assert terminal.accepted_carriers == ()
