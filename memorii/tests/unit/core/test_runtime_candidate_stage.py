from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from memorii.core.consolidation.runtime_outputs import (
    ConsolidationOrigin,
    ConsolidationPayload,
    ConsolidationSourceReference,
    EpisodicSummary,
    SemanticCandidate,
    SkillCandidate,
    UserCandidate,
    build_consolidation_result,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import record_digest
from memorii.core.persistence.managed_delivery import (
    DeliveryAuthorityBinding,
    MemoryPlaneCandidateScope,
    ProtectedSkillCandidateScope,
)
from memorii.core.provider.runtime_candidate import (
    AcceptedCandidateOffer,
    CandidateStageError,
    ProtectedSkillCandidate,
    prepare_candidate_stage,
)
from memorii.core.storage_administration.revoked_identity_view import (
    RevokedIdentities,
    RevokedIdentityView,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility
from pydantic import ValidationError

_NOW = datetime(2026, 4, 25, tzinfo=UTC)
_ORIGIN = ConsolidationOrigin(
    installation_id="installation", partition_id="partition",
    operation_generation="generation", task_id="task", client_namespace="client",
    operation_id="operation", request_digest="a" * 64,
)
_SOURCE = CanonicalMemoryRecord(
    memory_id="source", domain=MemoryDomain.TRANSCRIPT, status=CommitStatus.COMMITTED,
    text="retained source", user_id="principal", task_id="task", timestamp=_NOW,
)
_REF = ConsolidationSourceReference(source_id="source", source_digest=record_digest(_SOURCE))


def _offer(
    payload: ConsolidationPayload,
    scope: MemoryPlaneCandidateScope | ProtectedSkillCandidateScope,
):
    result = build_consolidation_result(_ORIGIN, origin_revision=3, outputs=(payload,))
    (output,) = result.outputs
    accepted = AcceptedCandidateOffer(
        decision_id="b" * 64, result_id=result.result_id,
        output_id=output.output_id, payload_digest=output.payload_digest,
        accepted_at=_NOW, target_scope=scope,
    )
    authority = DeliveryAuthorityBinding(
        installation_id="installation", principal="principal",
        client_namespace="client", host_binding_id="client", credential_id="credential",
        grant_id="grant", grant_epoch=1, scope=scope, source_refs=(_REF,),
    )
    return result, accepted, authority


@pytest.mark.parametrize(
    ("domain", "payload"),
    [
        ("episodic", EpisodicSummary(summary="A task summary", source_refs=(_REF,))),
        ("semantic", SemanticCandidate(abstraction="A sealed abstraction", source_refs=(_REF,))),
        ("user", UserCandidate(preference="A validated preference", source_refs=(_REF,), valid_from=_NOW)),
    ],
)
def test_memory_candidate_shape_preserves_inert_status_and_scope(domain, payload) -> None:
    scope = MemoryPlaneCandidateScope(partition_id="partition", task_id="task", domain=domain)
    result, acceptance, authority = _offer(payload, scope)
    staged = prepare_candidate_stage(
        result=result, acceptance=acceptance, authority=authority,
        current_sources=(_SOURCE,), revoked=RevokedIdentityView.empty(), now=_NOW,
    )
    assert isinstance(staged, CanonicalMemoryRecord)
    assert staged.domain == domain
    assert staged.status == CommitStatus.CANDIDATE
    assert staged.visibility == MemoryRecordVisibility.INTERNAL_CONTROL
    assert staged.memory_id == f"cand:runtime:{acceptance.output_id}"
    assert staged.source_record_ids == [_REF.source_id]
    assert staged.is_raw_event is False
    if isinstance(payload, UserCandidate):
        assert staged.valid_from == _NOW


def test_skill_candidate_has_its_own_closed_protected_scope() -> None:
    scope = ProtectedSkillCandidateScope(partition_id="partition", task_id="task")
    result, acceptance, authority = _offer(
        SkillCandidate(title="Task", summary="Summary", steps=("step",), source_refs=(_REF,)),
        scope,
    )
    staged = prepare_candidate_stage(
        result=result, acceptance=acceptance, authority=authority,
        current_sources=(_SOURCE,), revoked=RevokedIdentityView.empty(), now=_NOW,
    )
    assert isinstance(staged, ProtectedSkillCandidate)
    assert staged.ordered_steps == ("step",)
    assert staged.originating_result_id == result.result_id
    with pytest.raises(ValidationError):
        ProtectedSkillCandidate.model_validate({**staged.model_dump(), "domain": "semantic"})


def test_source_scope_freshness_and_output_revision_are_exact() -> None:
    scope = MemoryPlaneCandidateScope(partition_id="partition", task_id="task", domain="semantic")
    result, acceptance, authority = _offer(
        SemanticCandidate(abstraction="A sealed abstraction", source_refs=(_REF,)), scope,
    )
    for current_sources, revoked in (
        ((), RevokedIdentityView.empty()),
        ((_SOURCE.model_copy(update={"text": "changed"}),), RevokedIdentityView.empty()),
        ((_SOURCE.model_copy(update={"task_id": "other"}),), RevokedIdentityView.empty()),
        ((_SOURCE.model_copy(update={"valid_to": _NOW - timedelta(seconds=1)}),), RevokedIdentityView.empty()),
        ((_SOURCE,), RevokedIdentityView(RevokedIdentities(sources=frozenset({"source"})))),
    ):
        with pytest.raises(CandidateStageError, match="source"):
            prepare_candidate_stage(
                result=result, acceptance=acceptance, authority=authority,
                current_sources=current_sources, revoked=revoked, now=_NOW,
            )
    with pytest.raises(CandidateStageError, match="sealed result"):
        prepare_candidate_stage(
            result=result, acceptance=acceptance.model_copy(update={"payload_digest": "c" * 64}),
            authority=authority, current_sources=(_SOURCE,),
            revoked=RevokedIdentityView.empty(), now=_NOW,
        )
    episodic_scope = scope.model_copy(update={"domain": "episodic"})
    with pytest.raises(CandidateStageError, match="domain"):
        prepare_candidate_stage(
            result=result, acceptance=acceptance.model_copy(update={"target_scope": episodic_scope}),
            authority=authority.model_copy(update={"scope": episodic_scope}),
            current_sources=(_SOURCE,), revoked=RevokedIdentityView.empty(), now=_NOW,
        )
