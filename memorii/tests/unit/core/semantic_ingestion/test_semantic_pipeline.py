from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.memory_evolution.models import SourceObservation, SourceType
from memorii.core.memory_evolution.semantic_state import (
    CompiledIdentityLineageTransition,
    LineageEvidenceReference,
)
from memorii.core.prompts.registry import PromptRegistry
from memorii.core.prompts.runtime_manifest import PromptOwner
from memorii.core.semantic_ingestion.contracts import (
    AuthenticatedSourceIntervalEvidence,
    IndependentSourceAnalysis,
    PredicateTemporalRule,
    PredicateTrustRule,
    SemanticArbitrationPolicyBundle,
    SemanticAuthorizationReadSet,
    SemanticCandidate,
    SemanticContractCodecError,
    SemanticEgressAuthorizationBinding,
    SourceAuthority,
    SourceAuthorityEvidence,
    TemporalEvidenceCandidate,
    TemporalPolicySnapshot,
    TextPreparationPolicy,
    TextPreparationRequest,
    TimeInterval,
    TrustPolicySnapshot,
    contract_digest,
    decode_semantic_contract,
    encode_semantic_contract,
)
from memorii.core.semantic_ingestion.egress import ProviderEgressBinding, ProviderEgressDecision
from memorii.core.semantic_ingestion.local_analyzer import ProductionLocalSemanticAnalyzer
from memorii.core.semantic_ingestion.pipeline import SemanticIngestionPipeline
from memorii.core.semantic_ingestion.prompt_authority import SemanticPromptAuthority
from memorii.core.semantic_ingestion.source_preparation import (
    InMemoryPreparedSourceRepository,
    TextPreparationService,
)
from tests.unit.core.semantic_ingestion.clean_room_request_test_support import (
    build_prepared_independent_source_analysis,
    build_prepared_source_authority,
)

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
        prepared_source, source_authority_evidence, source_interval_evidence,
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


def _prepared_source_repository() -> InMemoryPreparedSourceRepository:
    """Publish the exact Step-2 authority before exercising downstream stages."""
    repository = InMemoryPreparedSourceRepository()
    policy = TextPreparationPolicy.create(
        max_segment_characters=4096,
        supported_languages=("en",),
        segmentation_algorithm=(
            "memorii.semantic-ingestion.safe-sentence-first-paragraph-bounded.v1"
        ),
        context_window_algorithm=(
            "memorii.semantic-ingestion.owned-partition-whole-boundary-context.v1"
        ),
    )
    observation = SourceObservation(
        source_id=SOURCE_ID,
        text=SOURCE,
        source_type=SourceType.USER,
        source_digest=SOURCE_DIGEST,
        delivery_key_digest=_hex("pipeline-test-delivery"),
    )
    TextPreparationService(
        producer=lambda request: build_prepared_source_authority(
            source_id=request.observation.source_id,
            source_digest=request.observation.source_digest or "",
            source_text=request.observation.text,
            preparation_policy=request.policy,
        ),
        repository=repository,
    ).prepare_and_publish(TextPreparationRequest(observation=observation, policy=policy))
    return repository


def test_policy_snapshot_preimages_match_declared_no_decay_rule_fields() -> None:
    bundle = _bundle()
    assert TrustPolicySnapshot.model_validate(bundle.trust_policy.model_dump(mode="python")) == bundle.trust_policy
    assert TemporalPolicySnapshot.model_validate(bundle.temporal_policy.model_dump(mode="python")) == bundle.temporal_policy


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


def _analysis(proposal: SemanticCandidate) -> None:
    del proposal
    return None

def _accepted(
    kind: str = "fact",
    *,
    operation_id: str = "source-operation",
    identity_lineage_compiler=None,
):
    proposal = _proposal(kind)
    return SemanticIngestionPipeline(
        transport=None,
        identity_lineage_compiler=identity_lineage_compiler,
    ).run(
        operation_id=operation_id, source_id=SOURCE_ID, source_digest=SOURCE_DIGEST,
        source_text=SOURCE, policy_bundle=_bundle(), local_proposals=(proposal,),
        prepared_source_repository=_prepared_source_repository(),
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
        prepared_source_repository=_prepared_source_repository(),
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
        prepared_source_repository=_prepared_source_repository(),
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
        prepared_source_repository=_prepared_source_repository(),
        egress_binding=binding, egress_policy_provider=AllowEgress(),
        current_time_provider=lambda: ARBITRATION,
    )
    assert outcome.status == "evidence_only" and transport.requests == []


@pytest.mark.parametrize(
    ("kind", "record_kinds"),
    [
        ("fact", ("claim_assertion",)), ("action", ("action_revision",)),
        ("correction", ("claim_assertion", "temporal_transition")),
        ("retraction", ("temporal_transition",)),
    ],
)
def test_source_analyses_compile_exact_canonical_carriers(kind: str, record_kinds: tuple[str, ...]) -> None:
    del record_kinds
    outcome = _accepted(kind)
    assert outcome.status == "unresolved"
    assert outcome.reason_codes == ("independent_source_analysis_unavailable",)
    assert outcome.accepted_carriers == ()


def test_identity_operation_without_graph_compiler_is_noncommitting() -> None:
    outcome = _accepted("identity")

    assert outcome.status == "unresolved"
    assert outcome.reason_codes == ("independent_source_analysis_unavailable",)
    assert outcome.accepted_carriers == ()


def test_graph_compiled_alias_is_first_class_and_rewrites_zero_references() -> None:
    class AliasCompiler:
        def compile_transition(self, *, operation, candidate, source_analysis):
            del candidate, source_analysis
            return CompiledIdentityLineageTransition.create(
                operation_id=operation.operation_id,
                operation="alias",
                predecessors=(),
                successors=(),
                graph_revision_before="genesis",
                recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
                lineage_snapshot_before_digest="a" * 64,
                source_evidence=(
                    LineageEvidenceReference(
                        source_id=SOURCE_ID,
                        start=0,
                        end=5,
                        evidence_digest=_hex("alias-evidence"),
                    ),
                ),
                reverse_reference_closure=(),
                reference_dispositions=(),
            )

    outcome = _accepted("identity", identity_lineage_compiler=AliasCompiler())

    assert outcome.status == "unresolved"
    assert outcome.reason_codes == ("independent_source_analysis_unavailable",)
    assert outcome.accepted_carriers == ()


def test_source_analysis_substitution_is_rejected() -> None:
    proposal = _proposal()
    assert _analysis(proposal) is None


def test_proposer_cannot_supply_source_analysis_fields() -> None:
    proposal = _proposal()
    payload = proposal.model_dump(mode="python") | {"parser_consensus": {}}
    transport = CaptureTransport([encode_typed_value({"candidates": [payload]}), b"invalid"])
    prompt, binding = _remote_authority()
    outcome = SemanticIngestionPipeline(transport=transport).run(
        operation_id="operation", source_id=SOURCE_ID, source_digest=SOURCE_DIGEST,
        source_text=SOURCE, policy_bundle=_bundle(), registered_prompt=prompt,
        prepared_source_repository=_prepared_source_repository(),
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


def test_production_local_analyzer_requires_and_consumes_prepared_source_authority() -> None:
    analyzer = ProductionLocalSemanticAnalyzer()
    proposals = analyzer.propose(
        source_id=SOURCE_ID, source_digest=SOURCE_DIGEST, source_text=SOURCE
    )
    interval = _temporal("source-interval").authenticated_source_interval_evidence
    assert interval is not None
    assert len(proposals) == 1
    assert analyzer.analyze(
        proposal=proposals[0],
        source_id=SOURCE_ID,
        source_digest=SOURCE_DIGEST,
        source_text=SOURCE,
        source_authority_evidence=_authority(),
        source_interval_evidence=interval,
    ) is None
    prepared_source = _prepared_source_repository().load(
        source_id=SOURCE_ID, source_digest=SOURCE_DIGEST
    )
    assert prepared_source is not None
    analysis = analyzer.analyze(
        proposal=proposals[0],
        source_id=SOURCE_ID,
        source_digest=SOURCE_DIGEST,
        source_text=SOURCE,
        prepared_source=prepared_source,
        source_authority_evidence=_authority(),
        source_interval_evidence=interval,
    )
    assert analysis is not None
    assert analysis.parser_consensus.preparation_fingerprint == prepared_source.preparation_fingerprint
    assert (
        analysis.parser_consensus.segment_language_route_digest
        == prepared_source.segment_language_routes.routes[0].route_digest
    )
    assert analysis.temporal_evidence[0].candidates[0].authenticated_source_interval_evidence == interval
    assert analyzer.analyze(
        proposal=proposals[0],
        source_id=SOURCE_ID,
        source_digest=SOURCE_DIGEST,
        source_text=SOURCE + " ",
        prepared_source=prepared_source,
        source_authority_evidence=_authority(),
        source_interval_evidence=interval,
    ) is None


def test_local_rejected_terminal_canonicalizes_noncanonical_candidate_order() -> None:
    rejected = SemanticCandidate(
        candidate_id="candidate-z",
        operation_kind="fact",
        predicate_id="works_for",
        assertion_quote=SOURCE,
        alignment_refs=(),
    )
    canonical = SemanticCandidate(
        candidate_id="candidate-a",
        operation_kind="fact",
        predicate_id="works_for",
        assertion_quote=SOURCE,
        alignment_refs=(),
    )
    interval = _temporal("source-interval").authenticated_source_interval_evidence
    assert interval is not None

    class RejectingAssessor:
        def analyze(
            self,
            *,
            proposal,
            source_id: str,
            source_digest: str,
            source_text: str,
            prepared_source,
            source_authority_evidence,
            source_interval_evidence,
        ):
            del proposal
            return build_prepared_independent_source_analysis(
                proposal=canonical,
                operation_id="operation-1",
                source_id=source_id,
                source_digest=source_digest,
                source_text=source_text,
                source_authority_evidence=source_authority_evidence,
                source_interval_evidence=source_interval_evidence,
                preparation_fingerprint=prepared_source.preparation_fingerprint,
            )

    outcome = SemanticIngestionPipeline(transport=None).run(
        operation_id="operation-1",
        source_id=SOURCE_ID,
        source_digest=SOURCE_DIGEST,
        source_text=SOURCE,
        policy_bundle=_bundle(),
        local_proposals=(rejected, canonical),
        prepared_source_repository=_prepared_source_repository(),
        independent_assessor=RejectingAssessor(),
        source_authority_evidence=_authority(),
        source_interval_evidence=interval,
        authorization_read_set_provider=Authorization(),
    )

    assert outcome.status == "rejected"
    assert outcome.reason_codes == ("independent_source_analysis_substitution",)
    assert tuple(candidate.candidate_id for candidate in outcome.candidates) == (
        "candidate-a",
        "candidate-z",
    )


def test_authorization_rotation_before_seal_discards_candidate_without_commit_artifacts() -> None:
    proposal = _proposal()
    terminal = SemanticIngestionPipeline(transport=None).run(
        operation_id="rotated-before-seal",
        source_id=SOURCE_ID,
        source_digest=SOURCE_DIGEST,
        source_text=SOURCE,
        policy_bundle=_bundle(),
        prepared_source_repository=_prepared_source_repository(),
        local_proposals=(proposal,),
        independent_assessor=Assessor({proposal.candidate_id: _analysis(proposal)}),
        source_authority_evidence=_authority(),
        source_interval_evidence=_temporal("source-interval").authenticated_source_interval_evidence,
        authorization_read_set_provider=RotateBeforeSeal(),
    )
    assert terminal.status == "unresolved"
    assert terminal.reason_codes == ("independent_source_analysis_unavailable",)
    assert terminal.accepted_carriers == ()
