from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.conflict_attention import (
    INTEGRITY_ATTENTION_QUESTION,
    AgentClarificationProposal,
    CandidateValidityInterval,
    ConflictAccessContext,
    ConflictAttention,
    ConflictAttentionPage,
    ConflictAudience,
    ConflictClarificationAttemptResult,
    ConflictClarificationWork,
    ConflictKind,
    ConflictResolutionAction,
    ConflictResolutionOption,
    ConflictResolutionRequest,
    ConflictStatus,
    SemanticConflictClarificationTransition,
    SemanticConflictClarificationTransitionReason,
    UserConfirmationReceipt,
    VerifiedUserConfirmation,
    decode_persisted_conflict_generation,
)
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from pydantic import BaseModel, ValidationError


def _digest() -> str:
    return "a" * 64


def _option(identifier: str) -> ConflictResolutionOption:
    return ConflictResolutionOption(candidate_id=identifier, label=f"label {identifier}", statement="statement", candidate_digest=_digest())


def _attention(*, kind: ConflictKind = ConflictKind.SEMANTIC_DISAGREEMENT) -> ConflictAttention:
    return ConflictAttention(
        conflict_id="conflict-1" if kind == ConflictKind.SEMANTIC_DISAGREEMENT else "incident-1",
        conflict_revision=_digest(),
        kind=kind,
        audience=ConflictAudience.USER if kind == ConflictKind.SEMANTIC_DISAGREEMENT else ConflictAudience.OPERATOR,
        status=ConflictStatus.OPEN,
        question="Which is correct?" if kind == ConflictKind.SEMANTIC_DISAGREEMENT else INTEGRITY_ATTENTION_QUESTION,
        options=(_option("candidate-1"), _option("candidate-2")) if kind == ConflictKind.SEMANTIC_DISAGREEMENT else (),
        created_at=datetime(2026, 8, 2, tzinfo=UTC),
        creation_coordinate=1,
        scope_digest=_digest(),
    )


def _clarification_transition(
    reason: SemanticConflictClarificationTransitionReason,
) -> SemanticConflictClarificationTransition:
    status = {
        SemanticConflictClarificationTransitionReason.SUBMITTED: ConflictStatus.CLARIFICATION_SUBMITTED,
        SemanticConflictClarificationTransitionReason.ACCEPTED: ConflictStatus.RESOLVED,
        SemanticConflictClarificationTransitionReason.REJECTED: ConflictStatus.OPEN,
        SemanticConflictClarificationTransitionReason.INSUFFICIENT: ConflictStatus.OPEN,
        SemanticConflictClarificationTransitionReason.PROCESSING_EXHAUSTED: ConflictStatus.OPEN,
        SemanticConflictClarificationTransitionReason.SUPERSEDED: ConflictStatus.CLARIFICATION_SUBMITTED,
    }[reason]
    attention = _attention().model_copy(
        update={"status": status, "conflict_revision": "b" * 64}
    )
    body = {
        "conflict_id": attention.conflict_id,
        "predecessor_conflict_revision": _digest(),
        "predecessor_record_digest": "c" * 64,
        "predecessor_status": ConflictStatus.OPEN if reason == SemanticConflictClarificationTransitionReason.SUBMITTED else ConflictStatus.CLARIFICATION_SUBMITTED,
        "resulting_attention": attention,
        "reason": reason,
        "proposal_digest": "d" * 64,
        "processing_operation_id": "e" * 64,
        "successor_conflict_revision": "f" * 64 if reason == SemanticConflictClarificationTransitionReason.SUPERSEDED else None,
        "record_coordinate": 2,
        "transition_coordinate": 2,
        "transitioned_at": datetime(2026, 8, 4, tzinfo=UTC),
    }
    return SemanticConflictClarificationTransition(
        **body,
        transition_digest=sha256(
            b"memorii.semantic-conflict-clarification-transition.v1\0"
            + encode_typed_value(
                SemanticConflictClarificationTransition.model_construct(
                    **body, transition_digest="0" * 64
                ).model_dump(mode="python", exclude={"transition_digest"})
            )
        ).hexdigest(),
    )


def test_persisted_conflict_wire_decoder_keeps_closed_enums_and_scalars_strict() -> None:
    transition = _clarification_transition(
        SemanticConflictClarificationTransitionReason.SUBMITTED
    )
    payload = transition.model_dump(mode="json")
    assert decode_persisted_conflict_generation(
        payload, SemanticConflictClarificationTransition
    ) == transition
    unknown_reason = {**payload, "reason": "unknown"}
    with pytest.raises(ValidationError):
        decode_persisted_conflict_generation(
            unknown_reason, SemanticConflictClarificationTransition
        )
    coercible_coordinate = {**payload, "record_coordinate": "1"}
    with pytest.raises(ValidationError):
        decode_persisted_conflict_generation(
            coercible_coordinate, SemanticConflictClarificationTransition
        )


def test_attempt_result_wire_rejects_the_predecessor_successor_field_name() -> None:
    """The persisted attempt-result wire contract uses the design's name."""
    with pytest.raises(ValidationError):
        ConflictClarificationAttemptResult.model_validate(
            {"successor_conflict_revision": _digest()}
        )


def test_semantic_clarification_transition_has_closed_lifecycle_edges() -> None:
    for reason in SemanticConflictClarificationTransitionReason:
        assert _clarification_transition(reason).reason == reason

    submitted = _clarification_transition(SemanticConflictClarificationTransitionReason.SUBMITTED)
    with pytest.raises(ValidationError):
        SemanticConflictClarificationTransition.model_validate(
            {**submitted.model_dump(), "successor_conflict_revision": "f" * 64}
        )
    with pytest.raises(ValidationError):
        SemanticConflictClarificationTransition.model_validate(
            {**submitted.model_dump(), "predecessor_status": ConflictStatus.CLARIFICATION_SUBMITTED}
        )
    superseded = _clarification_transition(SemanticConflictClarificationTransitionReason.SUPERSEDED)
    with pytest.raises(ValidationError):
        SemanticConflictClarificationTransition.model_validate(
            {**superseded.model_dump(), "successor_conflict_revision": None}
        )


def test_closed_attention_contract_accepts_only_open_semantic_or_integrity_cards() -> None:
    semantic = _attention()
    integrity = _attention(kind=ConflictKind.STORAGE_INTEGRITY)
    page = ConflictAttentionPage(items=(semantic, integrity), total_pending=2)
    assert page.items == (semantic, integrity)

    closed = ConflictAttention.model_validate({**semantic.model_dump(), "status": ConflictStatus.RESOLVED})
    with pytest.raises(ValidationError):
        ConflictAttentionPage(items=(closed,), total_pending=1)
    with pytest.raises(ValidationError):
        ConflictAttention.model_validate({**semantic.model_dump(), "options": [semantic.options[0]]})
    with pytest.raises(ValidationError):
        ConflictAttention.model_validate({**integrity.model_dump(), "options": [semantic.options[0]]})
    with pytest.raises(ValidationError):
        ConflictAttention.model_validate({**semantic.model_dump(), "unexpected": True})


def test_closed_attention_contract_enforces_utf8_digest_utc_and_page_bounds() -> None:
    semantic = _attention()
    with pytest.raises(ValidationError):
        ConflictResolutionOption(candidate_id="x", label="x" * 257, statement="ok", candidate_digest=_digest())
    with pytest.raises(ValidationError):
        ConflictResolutionOption(candidate_id="x", label="ok", statement="ok", candidate_digest="A" * 64)
    with pytest.raises(ValidationError):
        ConflictAttention.model_validate({**semantic.model_dump(), "created_at": datetime(2026, 8, 2)})
    with pytest.raises(ValidationError):
        ConflictAttentionPage(items=(semantic,), total_pending=0)
    with pytest.raises(ValidationError):
        ConflictAttentionPage(total_pending=1)
    with pytest.raises(ValidationError):
        ConflictAttentionPage(total_pending=0, next_cursor="opaque-cursor")


def test_resolution_and_confirmation_contracts_enforce_action_cardinality_and_utc() -> None:
    interval = CandidateValidityInterval(candidate_id="candidate-1", valid_from=datetime(2026, 8, 2, tzinfo=UTC))
    common = dict(
        conflict_id="conflict-1",
        conflict_revision=_digest(),
        operation_id="operation-1",
        source_user_event_id="user-event-1",
        source_user_event_digest=_digest(),
        agent_principal_id="agent-1",
        scope_digest=_digest(),
        request_digest=_digest(),
        proposal_digest=_digest(),
    )
    assert AgentClarificationProposal(
        **common, action=ConflictResolutionAction.SELECT, selected_candidate_ids=("candidate-1",), validity_intervals=()
    )
    with pytest.raises(ValidationError):
        AgentClarificationProposal(
            **common, action=ConflictResolutionAction.SELECT, selected_candidate_ids=("candidate-1",), validity_intervals=(interval,)
        )
    with pytest.raises(ValidationError):
        CandidateValidityInterval(candidate_id="candidate-1", valid_from=datetime(2026, 8, 2), valid_to=None)
    with pytest.raises(ValidationError):
        UserConfirmationReceipt(token=" ")

    verified = VerifiedUserConfirmation(
        issuer_id="issuer-1",
        key_id="key-1",
        trust_snapshot_digest=_digest(),
        revocation_snapshot_digest=_digest(),
        principal_id="principal-1",
        scope_digest=_digest(),
        conflict_id="conflict-1",
        conflict_revision=_digest(),
        action=ConflictResolutionAction.NEITHER,
        request_digest=_digest(),
        source_user_event_id="user-event-1",
        source_user_event_digest=_digest(),
        issued_at=datetime(2026, 8, 2, tzinfo=UTC),
        expires_at=datetime(2026, 8, 2, tzinfo=UTC) + timedelta(minutes=1),
        nonce="nonce-1",
    )
    assert verified.nonce == "nonce-1"


def test_both_with_validity_accepts_disjoint_intervals_and_rejects_overlap_without_store_authority() -> None:
    first = CandidateValidityInterval(
        candidate_id="candidate-1",
        valid_from=datetime(2026, 6, 1, tzinfo=UTC),
        valid_to=datetime(2026, 7, 1, tzinfo=UTC),
    )
    adjacent = CandidateValidityInterval(
        candidate_id="candidate-2",
        valid_from=datetime(2026, 7, 1, tzinfo=UTC),
    )
    common = {
        "conflict_id": "conflict-1",
        "expected_conflict_revision": _digest(),
        "operation_id": "operation-1",
        "action": ConflictResolutionAction.BOTH_WITH_VALIDITY,
        "selected_candidate_ids": ("candidate-1", "candidate-2"),
        "source_user_event_id": "user-event-1",
    }
    assert ConflictResolutionRequest(**common, validity_intervals=(first, adjacent))
    overlapping = adjacent.model_copy(update={"valid_from": datetime(2026, 6, 30, tzinfo=UTC)})
    with pytest.raises(ValidationError, match="store-owned predicate authorization"):
        ConflictResolutionRequest(**common, validity_intervals=(first, overlapping))


def test_access_and_work_contracts_are_closed_and_lease_safe() -> None:
    context = ConflictAccessContext(
        tenant_id="tenant-1",
        principal_id="principal-1",
        principal_binding_digest=_digest(),
        authorized_scope_ids=("scope-1",),
        scope_digest=_digest(),
        authorization_snapshot_digest=_digest(),
    )
    assert context.authorized_scope_ids == ("scope-1",)
    with pytest.raises(ValidationError):
        ConflictAccessContext.model_validate({**context.model_dump(), "authorized_scope_ids": ()})
    with pytest.raises(ValidationError):
        ConflictClarificationWork(
            conflict_id="conflict-1",
            conflict_revision=_digest(),
            proposal_digest=_digest(),
            attempt_id="attempt-1",
            attempt_count=0,
            owner_token="owner-1",
            ownership_epoch=0,
            lease_expires_at=datetime(2026, 8, 2, tzinfo=UTC),
            policy_fingerprint=_digest(),
        )


@pytest.mark.parametrize(
    "factory,field,maximum_bytes",
    [
        (lambda value: ConflictResolutionOption(candidate_id=value, label="label", statement="statement", candidate_digest=_digest()), "identifier", 1024),
        (lambda value: ConflictResolutionOption(candidate_id="candidate", label=value, statement="statement", candidate_digest=_digest()), "label", 256),
        (lambda value: ConflictResolutionOption(candidate_id="candidate", label="label", statement=value, candidate_digest=_digest()), "statement", 4096),
        (lambda value: ConflictAttention.model_validate({**_attention().model_dump(), "question": value}), "question", 1024),
        (lambda value: ConflictAttentionPage(items=(_attention(),), total_pending=1, next_cursor=value), "cursor", 4096),
        (lambda value: UserConfirmationReceipt(token=value), "receipt", 8192),
    ],
)
def test_bounded_utf8_field_families_accept_exact_limits_and_reject_overflow(
    factory: object, field: str, maximum_bytes: int
) -> None:
    assert callable(factory)
    exact = "é" * (maximum_bytes // 2)
    assert factory(exact)
    with pytest.raises(ValidationError, match="byte limit"):
        factory(exact + "x")
    with pytest.raises(ValidationError):
        factory(" ")
    with pytest.raises(ValidationError):
        factory(1)


def _public_records() -> tuple[BaseModel, ...]:
    interval = CandidateValidityInterval(candidate_id="candidate-1", valid_from=datetime(2026, 8, 2, tzinfo=UTC))
    proposal = AgentClarificationProposal(
        conflict_id="conflict-1", conflict_revision=_digest(), operation_id="operation-1", action=ConflictResolutionAction.SELECT,
        selected_candidate_ids=("candidate-1",), validity_intervals=(), source_user_event_id="event-1",
        source_user_event_digest=_digest(), agent_principal_id="agent-1", scope_digest=_digest(), request_digest=_digest(), proposal_digest=_digest(),
    )
    verified = VerifiedUserConfirmation(
        issuer_id="issuer", key_id="key", trust_snapshot_digest=_digest(), revocation_snapshot_digest=_digest(), principal_id="principal",
        scope_digest=_digest(), conflict_id="conflict-1", conflict_revision=_digest(), action=ConflictResolutionAction.NEITHER,
        request_digest=_digest(), source_user_event_id="event-1", source_user_event_digest=_digest(), issued_at=datetime(2026, 8, 2, tzinfo=UTC),
        expires_at=datetime(2026, 8, 2, tzinfo=UTC) + timedelta(seconds=1), nonce="nonce",
    )
    work = ConflictClarificationWork.model_construct(
        conflict_id="conflict-1",
        conflict_revision=_digest(),
        proposal_digest=_digest(),
        attempt_count=0,
        max_attempts=3,
        owner_token=None,
        ownership_epoch=0,
        lease_expires_at=None,
        last_failure_class=None,
        policy_fingerprint=_digest(),
        processing_operation_id=_digest(),
        downstream_receipt_digest=None,
        work_revision=1,
        predecessor_work_digest=None,
        work_digest=_digest(),
    )
    return (_option("candidate-1"), _attention(), ConflictAttentionPage(items=(_attention(),), total_pending=1),
            ConflictAccessContext(tenant_id="tenant", principal_id="principal", principal_binding_digest=_digest(), authorized_scope_ids=("scope",), scope_digest=_digest(), authorization_snapshot_digest=_digest()),
            interval, proposal, UserConfirmationReceipt(token="receipt"), verified, work)


def test_all_public_conflict_records_forbid_unknown_fields_and_tuple_coercion() -> None:
    for record in _public_records():
        with pytest.raises(ValidationError):
            type(record).model_validate({**record.model_dump(), "unexpected": True})
    with pytest.raises(ValidationError):
        ConflictAttentionPage.model_validate({"items": [_attention()], "total_pending": 1})
    with pytest.raises(ValidationError):
        AgentClarificationProposal.model_validate({**_public_records()[5].model_dump(), "selected_candidate_ids": ["candidate-1"]})
