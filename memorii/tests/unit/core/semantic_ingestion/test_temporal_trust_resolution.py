from datetime import UTC, datetime
from hashlib import sha256

import pytest
from memorii.core.semantic_ingestion.contracts import AuthenticatedEventTimeReference
from memorii.core.semantic_ingestion.pipeline import (
    AuthenticatedSourceIntervalEvidence,
    OperationTemporalAttachmentBinding,
    OperationTemporalDecisionBinding,
    PredicateTemporalRule,
    PredicateTrustRule,
    SourceAuthority,
    SourceAuthorityEvidence,
    SourceSpan,
    TemporalEvidenceCandidate,
    TemporalEvidenceResolver,
    TemporalPolicySnapshot,
    TimeInterval,
    TrustPolicySnapshot,
)


def _hex(label: str) -> str:
    return sha256(label.encode()).hexdigest()


def _policies(
    *, incomparable: bool = False, allow_open_end: bool = True,
    requirement: str = "required", allow_reference: bool = False,
):
    rule = PredicateTrustRule(
        predicate_id="works_for",
        eligible_authority_classes=frozenset({"official", "reported"}),
        authority_rank_by_class={"official": 20, "reported": 10},
        incomparable_class_pairs=(("official", "reported"),) if incomparable else (),
    )
    active = TimeInterval(
        start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2027, 1, 1, tzinfo=UTC)
    )
    return (
        TrustPolicySnapshot.create(policy_revision="trust-r1", system_effective_interval=active, rules=(rule,)),
        TemporalPolicySnapshot.create(
            policy_revision="temporal-r1", system_effective_interval=active,
            rules=(PredicateTemporalRule(
                predicate_id="works_for", valid_time_requirement=requirement,
                allow_open_end=allow_open_end,
                allow_reference_as_effective_start=allow_reference,
            ),),
        ),
    )


def _candidate(candidate_id: str, authority: str, start: int, end: int | None):
    interval = TimeInterval(start=datetime(2026, 1, start, tzinfo=UTC), end=None if end is None else datetime(2026, 1, end, tzinfo=UTC))
    source_authority = SourceAuthority(
        authority_class=authority,
        authenticated_provenance_class="host",
        policy_revision="1",
    )
    authority_evidence = SourceAuthorityEvidence.create(
        source_id="source", source_digest=_hex("source"), authority=source_authority,
        provenance_digest=_hex(f"authority:{authority}"),
    )
    authenticated = AuthenticatedSourceIntervalEvidence.create(
        source_id="source", source_digest=_hex("source"), interval=interval,
        authority_basis="server_source_metadata",
        provenance_digest=_hex(f"provenance:{candidate_id}"), policy_revision="1",
        source_authority_evidence_digest=authority_evidence.evidence_digest,
    ) if authority == "official" else None
    return TemporalEvidenceCandidate.create(
        candidate_id=candidate_id,
        kind="authenticated_source_interval" if authority == "official" else "certified_text_interval",
        interval=interval,
        source_authority=source_authority,
        authenticated_source_interval_evidence=authenticated,
        certified_text_candidate_id=candidate_id if authority != "official" else None,
        evidence_spans=(SourceSpan(source_id="source", start=0, end=1),) if authority != "official" else (),
    )


def test_highest_eligible_candidate_resolves_without_stitching():
    trust, temporal = _policies()
    closure = TemporalEvidenceResolver().resolve(
        predicate_id="works_for",
        candidates=(_candidate("a", "official", 1, 20), _candidate("b", "reported", 5, None)),
        trust_policy=trust,
        temporal_policy=temporal,
        arbitration_as_of=datetime(2026, 2, 1, tzinfo=UTC),
    )
    assert closure.outcome == "pass"
    assert closure.resolved_interval == TimeInterval(start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2026, 1, 20, tzinfo=UTC))
    assert closure.selected_candidate_ids == ("a",)


def test_equal_rank_nonidentical_evidence_is_contested():
    trust, temporal = _policies(incomparable=True)
    closure = TemporalEvidenceResolver().resolve(
        predicate_id="works_for",
        candidates=(_candidate("a", "official", 1, 20), _candidate("b", "reported", 5, 10)),
        trust_policy=trust,
        temporal_policy=temporal,
        arbitration_as_of=datetime(2026, 2, 1, tzinfo=UTC),
    )
    assert closure.outcome == "contested"
    assert closure.contested_candidate_ids == ("a", "b")
    assert closure.resolved_interval is None


def test_equal_values_co_support_without_provenance_collapse():
    trust, temporal = _policies()
    closure = TemporalEvidenceResolver().resolve(
        predicate_id="works_for",
        candidates=(_candidate("a", "official", 1, 20), _candidate("b", "reported", 1, 20)),
        trust_policy=trust,
        temporal_policy=temporal,
        arbitration_as_of=datetime(2026, 2, 1, tzinfo=UTC),
    )
    assert closure.outcome == "pass"
    assert closure.selected_candidate_ids == ("a", "b")
    assert len({candidate.candidate_digest for candidate in closure.candidates}) == 2


def test_policy_ineligible_evidence_cannot_win():
    trust, temporal = _policies()
    candidate = _candidate("a", "official", 1, 20).model_copy(update={"source_authority": SourceAuthority(authority_class="untrusted", authenticated_provenance_class="host", policy_revision="1")})
    # A substituted authority invalidates the candidate's content-addressed bytes.
    with pytest.raises(ValueError, match="temporal candidate digest mismatch"):
        TemporalEvidenceResolver().resolve(
            predicate_id="works_for", candidates=(candidate,), trust_policy=trust, temporal_policy=temporal,
            arbitration_as_of=datetime(2026, 2, 1, tzinfo=UTC),
        )


def test_role_bound_decision_rejects_cross_operation_attachment():
    trust, temporal = _policies()
    closure = TemporalEvidenceResolver().resolve(
        predicate_id="works_for", candidates=(_candidate("a", "official", 1, 20),),
        trust_policy=trust, temporal_policy=temporal, arbitration_as_of=datetime(2026, 2, 1, tzinfo=UTC),
    )
    attachment = OperationTemporalAttachmentBinding.create(
        operation_id="operation-a", temporal_role="assertion", stable_attachment_consensus_digest=_hex("consensus"),
        candidate_ids=("a",), candidate_spans=(),
    )
    with pytest.raises(ValueError, match="does not bind this operation role"):
        OperationTemporalDecisionBinding.create(
            operation_id="operation-b", temporal_role="assertion", scope_assessment_digest=_hex("scope"),
            semantic_assessment_digest=_hex("semantic"), temporal_attachment=attachment,
            decision_closure=closure,
        )


def test_all_ineligible_evidence_is_retained_but_unresolved():
    trust = TrustPolicySnapshot.create(
        policy_revision="trust-r1",
        system_effective_interval=TimeInterval(
            start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2027, 1, 1, tzinfo=UTC)
        ),
        rules=(PredicateTrustRule(
            predicate_id="works_for", eligible_authority_classes=frozenset(),
            authority_rank_by_class={"reported": 10},
        ),),
    )
    _, temporal = _policies()
    candidate = _candidate("a", "reported", 1, 20)
    closure = TemporalEvidenceResolver().resolve(
        predicate_id="works_for", candidates=(candidate,), trust_policy=trust, temporal_policy=temporal,
        arbitration_as_of=datetime(2026, 2, 1, tzinfo=UTC),
    )
    assert closure.outcome == "unknown"
    assert closure.candidates == (candidate,)
    assert closure.selected_candidate_ids == ()


@pytest.mark.parametrize(
    ("left", "right"),
    [((1, None), (5, 20)), ((1, 10), (5, None)), ((1, 20), (5, 10)), ((1, 8), (10, 20))],
)
def test_no_stitch_matrix_uses_one_exact_candidate_interval(left, right):
    trust, temporal = _policies(incomparable=True)
    closure = TemporalEvidenceResolver().resolve(
        predicate_id="works_for",
        candidates=(_candidate("a", "official", *left), _candidate("b", "reported", *right)),
        trust_policy=trust, temporal_policy=temporal,
        arbitration_as_of=datetime(2026, 2, 1, tzinfo=UTC),
    )
    assert closure.outcome == "contested"
    assert closure.resolved_interval is None


def test_disallowed_open_end_is_nonpromoting_and_retained():
    trust, temporal = _policies(allow_open_end=False)
    candidate = _candidate("a", "official", 1, None)
    closure = TemporalEvidenceResolver().resolve(
        predicate_id="works_for", candidates=(candidate,), trust_policy=trust, temporal_policy=temporal,
        arbitration_as_of=datetime(2026, 2, 1, tzinfo=UTC),
    )
    assert closure.outcome == "unknown" and closure.candidates == (candidate,)


def test_incomparable_policy_pairs_are_closed_and_canonical():
    with pytest.raises(ValueError, match="canonical"):
        PredicateTrustRule(
            predicate_id="works_for", eligible_authority_classes=frozenset({"official", "reported"}),
            authority_rank_by_class={"official": 20, "reported": 10},
            incomparable_class_pairs=(("reported", "official"),),
        )
    with pytest.raises(ValueError, match="ineligible"):
        PredicateTrustRule(
            predicate_id="works_for", eligible_authority_classes=frozenset({"official"}),
            authority_rank_by_class={"official": 20, "reported": 10},
            incomparable_class_pairs=(("official", "reported"),),
        )


@pytest.mark.parametrize(
    ("requirement", "allow_reference", "allow_open_end", "has_reference", "has_attachment", "outcome", "rule"),
    [
        ("required", True, True, True, False, "pass", "authenticated_reference_open_start"),
        ("required", False, True, True, False, "unknown", "unresolved"),
        ("required", True, False, True, False, "unknown", "unresolved"),
        ("required", False, True, False, False, "unknown", "unresolved"),
        ("optional", True, True, True, False, "pass", "authenticated_reference_open_start"),
        ("optional", False, True, True, False, "pass", "atemporal"),
        ("optional", False, True, False, False, "pass", "atemporal"),
        ("optional", False, True, False, True, "unknown", "unresolved"),
        ("atemporal", False, True, True, False, "pass", "atemporal"),
        ("atemporal", False, True, False, False, "pass", "atemporal"),
        ("atemporal", False, True, False, True, "unknown", "unresolved"),
    ],
)
def test_temporal_policy_matrix_without_asserted_interval(
    requirement, allow_reference, allow_open_end, has_reference, has_attachment, outcome, rule,
):
    trust, temporal = _policies(
        requirement=requirement,
        allow_reference=allow_reference,
        allow_open_end=allow_open_end,
    )
    reference = AuthenticatedEventTimeReference.create(
        reference_instant=datetime(2026, 1, 3, tzinfo=UTC),
        authority_basis="server_event_metadata",
        provenance_digest=_hex("event-reference"),
    ) if has_reference else None
    closure = TemporalEvidenceResolver().resolve(
        predicate_id="works_for",
        candidates=(),
        reference_evidence=reference,
        source_present_attachment=has_attachment,
        trust_policy=trust,
        temporal_policy=temporal,
        arbitration_as_of=datetime(2026, 2, 1, tzinfo=UTC),
    )
    assert closure.outcome == outcome
    assert closure.resolution_rule == rule
    if rule == "authenticated_reference_open_start":
        assert closure.resolved_interval == TimeInterval(start=reference.reference_instant)
    else:
        assert closure.resolved_interval is None


def test_atemporal_policy_rejects_attached_asserted_interval():
    trust, temporal = _policies(requirement="atemporal")
    closure = TemporalEvidenceResolver().resolve(
        predicate_id="works_for",
        candidates=(_candidate("a", "official", 1, 20),),
        trust_policy=trust,
        temporal_policy=temporal,
        arbitration_as_of=datetime(2026, 2, 1, tzinfo=UTC),
    )
    assert closure.outcome == "unknown"
    assert closure.candidates[0].candidate_id == "a"
