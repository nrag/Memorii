from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.memory_evolution.admission import source_admission_source_digest
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.core.persistence.factory import open_managed_partition
from memorii.core.semantic_ingestion.catalog_authority import (
    AuthenticatedPrincipalAgent,
    CatalogAuthorityError,
    CatalogAuthorityScope,
)
from memorii.core.semantic_ingestion.catalog_capture_pin import (
    CatalogCapturedTurnPin,
    PackageIndexedCatalogBundleLocator,
)
from memorii.core.semantic_ingestion.catalog_management import (
    CatalogManagementRepository,
    ManagedCatalogAuthorityError,
    ManagedCatalogEnrollmentDecision,
    ManagedCatalogProvisioning,
)
from memorii.core.semantic_ingestion.contracts import (
    ProviderEntityObject,
    ProviderFact,
    ProviderMention,
    ProviderSemanticProposal,
)
from memorii.core.semantic_ingestion.coverage_observation import (
    CoverageObservationRepository,
    CoverageSemanticOutcome,
    CoverageSourceSpan,
    ObserverBindingIdentity,
    classify_coverage_observation,
    new_coverage_observation,
    start_coverage_observation,
)
from memorii.core.semantic_ingestion.coverage_recurrence import (
    CoverageRecurrenceRepository,
    RelationGapSignature,
    VerifiedCoverageGap,
    VerifiedCoverageGapRepository,
    build_coverage_recurrence_group,
    recurrence_owner_scope_digest,
)
from memorii.core.semantic_ingestion.hermes_captured_turn import HermesCapturedTurnLedger
from memorii.core.semantic_ingestion.learned_relation import (
    ActivationPolicy,
    AgentLocalCatalogScope,  # noqa: I001
    CatalogManagementUnavailable,
    FrozenMentorsPairedEvaluator,
    IsolatedMentorsEvaluationExecutor,
    LearnedRelationCandidateService,
    LearnedRelationError,
    LearnedRelationRuntime,
    OntologyActivation,
    OntologyCatalogVersion,
    OntologyChangeProposal,
    OntologyEvidenceReference,
    PairedEvaluation,
    PairedEvaluationCaseOutcome,
    RelationDeclaration,
    validate_mentors_tool_proposal,
)
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility


class _ReplayWriter:
    def __init__(self, outcome: str = "committed") -> None:
        self.calls: list[str] = []
        self.outcome = outcome

    def replay_retained_source(self, *, source_id: str, source_digest: str,
                               catalog_scope: AgentLocalCatalogScope, catalog_digest: str,
                               replay_operation_id: str) -> str:
        self.calls.append(replay_operation_id)
        return self.outcome


_SCOPE = AgentLocalCatalogScope(principal_id="user:one", agent_id="agent:one")


def _proposal() -> OntologyChangeProposal:
    return OntologyChangeProposal.create(
        catalog_scope=_SCOPE,
        parent_catalog_digest="a" * 64,
        relation=RelationDeclaration(description="A person mentors another person."),
        evidence=(
            OntologyEvidenceReference(source_id="source:one", source_digest="1" * 64,
                                      origin_lineage_digest="a" * 64, source_scope_digest="b" * 64),
            OntologyEvidenceReference(source_id="source:two", source_digest="2" * 64,
                                      origin_lineage_digest="c" * 64, source_scope_digest="b" * 64),
        ),
    )


def _proposal_from_parent(*, parent_catalog_digest: str, source_id: str, source_digit: str) -> OntologyChangeProposal:
    return OntologyChangeProposal.create(
        catalog_scope=_SCOPE,
        parent_catalog_digest=parent_catalog_digest,
        relation=RelationDeclaration(description="A person mentors another person."),
        evidence=(
            OntologyEvidenceReference(
                source_id=source_id,
                source_digest=source_digit * 64,
                origin_lineage_digest="a" * 64,
                source_scope_digest="b" * 64,
            ),
        ),
    )


def _runtime(writer: _ReplayWriter, plane: MemoryPlaneService | None = None) -> LearnedRelationRuntime:
    return LearnedRelationRuntime(
        memory_plane=plane or MemoryPlaneService(), replay_writer=writer,
        policy_for_scope=lambda _scope: ActivationPolicy(
            owner_principal_id="user:one", owner_agent_id="agent:one"
        ),
    )


def _authenticated() -> AuthenticatedPrincipalAgent:
    return AuthenticatedPrincipalAgent(principal_id="user:one", agent_id="agent:one")


def _ledger(*, principal_id: str = "user:one", agent_id: str = "agent:one") -> HermesCapturedTurnLedger:
    return HermesCapturedTurnLedger(
        installation_id="installation", session_id="session", principal_id=principal_id,
        agent_id=agent_id, turn_ordinal=1, message_digest="a" * 64,
        source_id="source", source_digest="b" * 64, preparation_fingerprint="c" * 64,
        captured_at=datetime(2026, 9, 27, tzinfo=UTC),
    )


def _passing_evaluation() -> PairedEvaluation:
    return PairedEvaluation.create(
        binding_digest="d" * 64, targeted_positive_count=2,
        targeted_positive_committed_and_read=2, parent_regressions=0,
        unsupported_or_misleading_failures=0, scope_or_provenance_failures=0,
        available=True,
    )


def _isolated_case_executor(*, veto_case: str | None = None) -> IsolatedMentorsEvaluationExecutor:
    """A deterministic isolated-root stand-in for evaluator contract proof."""
    def run(
        _proposal: OntologyChangeProposal,
        cases: tuple[tuple[str, str, str], ...],
        binding_digest: str,
        corpus_digest: str,
        budget_digest: str,
    ) -> tuple[PairedEvaluationCaseOutcome, ...]:
        outcomes: list[PairedEvaluationCaseOutcome] = []
        for case_id, _text, expected in cases:
            if expected == "candidate_commit_and_read":
                parent, candidate, read = "unavailable", "committed", "read"
            elif case_id == "parent-regression":
                parent, candidate, read = "read", "committed", "read"
            else:
                parent, candidate, read = "unavailable", "abstained", "unavailable"
            if case_id == veto_case:
                candidate = "committed"
            outcomes.append(PairedEvaluationCaseOutcome(
                case_id=case_id, expected=expected, parent_status=parent,
                candidate_status=candidate, candidate_read_status=read,
                binding_digest=binding_digest, corpus_digest=corpus_digest,
                budget_digest=budget_digest,
            ))
        return tuple(outcomes)

    return IsolatedMentorsEvaluationExecutor(run_isolated_cases=run)


def _approve_and_activate(runtime: LearnedRelationRuntime, proposal: OntologyChangeProposal):
    prepared = runtime.prepare_candidate(proposal)
    evaluated = runtime.record_evaluation(
        proposal_id=prepared.proposal_id, evaluation=_passing_evaluation(),
    )
    approved = runtime.approve_candidate(
        proposal_id=evaluated.proposal_id, principal_id="user:one", agent_id="agent:one",
    )
    return runtime.activate_candidate(
        proposal_id=approved.proposal_id, principal_id="user:one", agent_id="agent:one",
    )


def test_owner_activates_a_validated_relation_and_replays_through_writer() -> None:
    writer = _ReplayWriter()
    runtime = _runtime(writer)
    proposal = runtime.prepare_candidate(_proposal())
    evaluated = runtime.record_evaluation(proposal_id=proposal.proposal_id,
                                          evaluation=_passing_evaluation())
    approved = runtime.approve_candidate(proposal_id=evaluated.proposal_id,
                                         principal_id="user:one", agent_id="agent:one")

    selected = runtime.activate_candidate(proposal_id=approved.proposal_id,
                                          principal_id="user:one", agent_id="agent:one")

    assert selected.status == "selected"
    assert len(writer.calls) == 2
    assert runtime.status(_SCOPE)["candidate_count"] == 1
    assert runtime.status(_SCOPE)["activation_sequence"] == 1


def test_failed_evaluation_and_non_owner_never_activate_or_replay() -> None:
    writer = _ReplayWriter()
    runtime = _runtime(writer)
    proposal = runtime.prepare_candidate(_proposal())
    failed = PairedEvaluation.create(
        binding_digest="d" * 64, targeted_positive_count=2,
        targeted_positive_committed_and_read=1, parent_regressions=0,
        unsupported_or_misleading_failures=0, scope_or_provenance_failures=0,
        available=True,
    )
    evaluated = runtime.record_evaluation(proposal_id=proposal.proposal_id, evaluation=failed)
    assert evaluated.lifecycle == "rejected"
    with pytest.raises(LearnedRelationError, match="authorization"):
        runtime.approve_candidate(proposal_id=evaluated.proposal_id,
                                  principal_id="user:two", agent_id="agent:two")
    with pytest.raises(LearnedRelationError, match="has not passed"):
        runtime.approve_candidate(proposal_id=evaluated.proposal_id,
                                  principal_id="user:one", agent_id="agent:one")
    assert writer.calls == []


def test_candidate_owner_rejects_missing_recurrence_without_control_or_fact_state() -> None:
    """A caller cannot fabricate a proposal when no durable group exists."""
    writer = _ReplayWriter()
    plane = MemoryPlaneService()
    service = LearnedRelationCandidateService(
        memory_plane=plane, runtime=_runtime(writer, plane),
        evaluator=FrozenMentorsPairedEvaluator(),
    )

    with pytest.raises(LearnedRelationError, match="not eligible"):
        service.admit_recurrence(group_id="coverage-recurrence-group:v1:missing", authenticated=_authenticated())

    assert writer.calls == []
    assert plane.list_records() == []


@pytest.mark.parametrize("interruption", ["before_result", "after_result"])
def test_repeat_recurrence_admission_recovers_interrupted_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interruption: str,
) -> None:
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(tmp_path / "plane"))
    writer = _ReplayWriter()
    policy = CatalogManagementRepository(plane, partition_id="local:test", scope=_SCOPE)
    policy.set_state("enabled")
    runtime = LearnedRelationRuntime(
        memory_plane=plane,
        replay_writer=writer,
        policy_for_scope=lambda scope: ActivationPolicy(
            owner_principal_id=scope.principal_id, owner_agent_id=scope.agent_id,
        ),
        management_fence_for_scope=policy.enabled_write_fence,
    )
    authenticated = _authenticated()
    evaluator = FrozenMentorsPairedEvaluator(_isolated_case_executor())
    result = evaluator.evaluate(_proposal())
    evaluate_calls = []

    def evaluate(proposal: OntologyChangeProposal) -> PairedEvaluation:
        evaluate_calls.append(proposal.proposal_id)
        if interruption == "before_result" and len(evaluate_calls) == 1:
            policy.set_state("paused")
        return result

    monkeypatch.setattr(evaluator, "evaluate", evaluate)
    service = LearnedRelationCandidateService(memory_plane=plane, runtime=runtime, evaluator=evaluator)
    binding = ObserverBindingIdentity(
        binding_version="observer:v1", provider="local", model="test-model",
        prompt_version="prompt:v1", transport="in_process", egress_policy_digest="5" * 64,
        output_schema_digest="6" * 64,
    )
    signature = RelationGapSignature.create(
        normalized_relation_meaning="mentors", subject_type_id="Person", object_type_id="Person",
        domain_id="organization", evidence_rule_id="direct_assertion:v1",
    )
    observed_scope_digest = recurrence_owner_scope_digest(
        principal_id=authenticated.principal_id, agent_id=authenticated.agent_id,
    )
    observations = CoverageObservationRepository(plane)
    verified_gaps = VerifiedCoverageGapRepository(plane)
    evidence = []
    for index, source_text in enumerate(("Ada mentors Bea.", "Cora mentors Dax.", "Eve mentors Fay."), start=1):
        source = CanonicalMemoryRecord(
            memory_id=f"source:{index}", domain=MemoryDomain.TRANSCRIPT, text=source_text,
            status=CommitStatus.COMMITTED, source_kind="semantic_ingestion_source", is_raw_event=True,
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )
        plane.write_records((source,))
        queued = new_coverage_observation(
            source_id=source.memory_id, source_digest=source_admission_source_digest(source), source_span=None,
            source_scope_digest=observed_scope_digest, origin_lineage_digest=str(index) * 64,
            session_id="session:one" if index < 3 else "session:two", principal_id=authenticated.principal_id,
            agent_id=authenticated.agent_id, observed_at=datetime(2026, 9, 27, tzinfo=UTC),
            catalog_scope=CatalogAuthorityScope(schema_version=1, kind="base"),
            catalog_digest="a" * 64, observer_binding=binding,
        )
        observed = classify_coverage_observation(
            start_coverage_observation(queued), semantic_outcome=CoverageSemanticOutcome.UNSUPPORTED_RELATION,
            source_span=CoverageSourceSpan(start=0, end=len(source_text)),
        )
        observations.create(observed)
        gap = VerifiedCoverageGap.from_observation(observed, signature=signature)
        verified_gaps.create(gap)
        evidence.append(gap)
    group = build_coverage_recurrence_group(tuple(evidence), recurrence_scope_digest=observed_scope_digest)
    CoverageRecurrenceRepository(plane).write(group, previous=None)

    replace = runtime._replace_proposal

    def interrupt_after_commit(old: OntologyChangeProposal, new: OntologyChangeProposal, *fence) -> None:
        replace(old, new, *fence)
        if new.lifecycle == "evaluating":
            raise InterruptedError("evaluation result committed")

    if interruption == "before_result":
        with pytest.raises(CatalogManagementUnavailable):
            service.admit_recurrence(group_id=group.group_id, authenticated=authenticated)
        assert runtime._require_proposal(evaluate_calls[0]).lifecycle == "validated"
        assert runtime._require_proposal(evaluate_calls[0]).evaluation is None
        policy.set_state("enabled")
    else:
        with monkeypatch.context() as patch:
            patch.setattr(runtime, "_replace_proposal", interrupt_after_commit)
            with pytest.raises(InterruptedError, match="evaluation result committed"):
                service.admit_recurrence(group_id=group.group_id, authenticated=authenticated)

    before = plane.read_snapshot()
    with pytest.raises(LearnedRelationError, match="outside the authenticated owner"):
        service.admit_recurrence(
            group_id=group.group_id,
            authenticated=AuthenticatedPrincipalAgent(principal_id="user:two", agent_id=_SCOPE.agent_id),
        )
    assert plane.read_snapshot() == before

    finished = service.admit_recurrence(group_id=group.group_id, authenticated=authenticated)
    assert finished.lifecycle == "awaiting_decision"
    assert finished.evaluation == result
    assert evaluate_calls == [finished.proposal_id] * (2 if interruption == "before_result" else 1)
    assert writer.calls == []


def test_registered_evaluator_derives_frozen_paired_counts() -> None:
    evaluation = FrozenMentorsPairedEvaluator(
        _isolated_case_executor()
    ).evaluate(_proposal())

    assert evaluation.available
    assert evaluation.targeted_positive_count == 2
    assert evaluation.targeted_positive_committed_and_read == 2
    assert evaluation.parent_regressions == 0
    assert evaluation.unsupported_or_misleading_failures == 0
    assert evaluation.scope_or_provenance_failures == 0
    assert len(evaluation.case_outcomes) == 8
    assert evaluation.case_outcomes[0].binding_digest == evaluation.binding_digest


def test_registered_evaluator_is_unavailable_before_root_is_bound_or_when_vetoed() -> None:
    unavailable = FrozenMentorsPairedEvaluator().evaluate(_proposal())
    vetoed = FrozenMentorsPairedEvaluator(
        _isolated_case_executor(veto_case="scope-provenance-veto")
    ).evaluate(_proposal())

    assert unavailable.available is False
    assert unavailable.case_outcomes == ()
    assert vetoed.available
    assert vetoed.scope_or_provenance_failures == 1
    assert vetoed.passes is False


@pytest.mark.parametrize(
    ("interrupted_transition", "after_commit", "persisted_lifecycle", "resume_by_retry"),
    (
        ("evaluating", False, "validated", False),
        ("evaluating", True, "evaluating", False),
        ("evaluated", False, "evaluating", True),
        ("evaluated", True, "evaluated", False),
        ("awaiting_decision", False, "evaluated", True),
        ("awaiting_decision", True, "awaiting_decision", True),
    ),
)
def test_restart_finishes_only_durable_evaluation_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interrupted_transition: str,
    after_commit: bool, persisted_lifecycle: str, resume_by_retry: bool,
) -> None:
    path = tmp_path / "plane"
    writer = _ReplayWriter()
    runtime = _runtime(writer, MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path)))
    proposal = runtime.prepare_candidate(_proposal())
    replace = runtime._replace_proposal
    result = _passing_evaluation()

    def interrupt_publication(old: OntologyChangeProposal, new: OntologyChangeProposal) -> None:
        interrupted = new.lifecycle == interrupted_transition
        if interrupted and not after_commit:
            raise InterruptedError("evaluation publication interrupted")
        replace(old, new)
        if interrupted:
            raise InterruptedError("evaluation publication interrupted")

    monkeypatch.setattr(runtime, "_replace_proposal", interrupt_publication)
    with pytest.raises(InterruptedError, match="evaluation publication interrupted"):
        runtime.record_evaluation(proposal_id=proposal.proposal_id, evaluation=result)

    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    reopened = _runtime(writer, plane)
    persisted = reopened._require_proposal(proposal.proposal_id)
    assert persisted.lifecycle == persisted_lifecycle
    assert persisted.evaluation == (None if persisted_lifecycle == "validated" else result)
    assert reopened.status(_SCOPE)["candidate_count"] == 1

    before = plane.read_snapshot()
    reopened.recover(AgentLocalCatalogScope(principal_id="user:two", agent_id=_SCOPE.agent_id))
    assert plane.read_snapshot() == before
    if persisted_lifecycle == "validated":
        reopened.recover(_SCOPE)
        assert plane.read_snapshot() == before
    else:
        changed = FrozenMentorsPairedEvaluator().evaluate(proposal)
        with pytest.raises(LearnedRelationError, match="differs from the published result"):
            reopened.record_evaluation(proposal_id=proposal.proposal_id, evaluation=changed)
        assert plane.read_snapshot() == before

    if persisted_lifecycle == "validated" or resume_by_retry:
        reopened.record_evaluation(proposal_id=proposal.proposal_id, evaluation=result)
    else:
        reopened.recover(_SCOPE)
    finished = reopened._require_proposal(proposal.proposal_id)
    assert finished.lifecycle == "awaiting_decision"
    assert finished.evaluation == result
    after = plane.read_snapshot()
    reopened.recover(_SCOPE)
    assert reopened.record_evaluation(proposal_id=proposal.proposal_id, evaluation=result) == finished
    assert plane.read_snapshot() == after
    assert writer.calls == []


@pytest.mark.parametrize("outcome", ("evaluation_unavailable", "rejected"))
def test_recovery_leaves_unavailable_or_vetoed_audits_inert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str,
) -> None:
    path = tmp_path / "plane"
    writer = _ReplayWriter()
    runtime = _runtime(writer, MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path)))
    proposal = runtime.prepare_candidate(_proposal())
    evaluator = FrozenMentorsPairedEvaluator(
        None if outcome == "evaluation_unavailable" else _isolated_case_executor(veto_case="scope-provenance-veto"),
    )
    result = evaluator.evaluate(proposal)
    replace = runtime._replace_proposal

    def interrupt_after_commit(old: OntologyChangeProposal, new: OntologyChangeProposal) -> None:
        replace(old, new)
        raise InterruptedError("evaluation result committed")

    monkeypatch.setattr(runtime, "_replace_proposal", interrupt_after_commit)
    with pytest.raises(InterruptedError, match="evaluation result committed"):
        runtime.record_evaluation(proposal_id=proposal.proposal_id, evaluation=result)

    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    reopened = _runtime(writer, plane)
    reopened.recover(_SCOPE)
    finished = reopened._require_proposal(proposal.proposal_id)
    assert finished.lifecycle == outcome
    assert finished.evaluation == result
    before = plane.read_snapshot()
    assert reopened.record_evaluation(proposal_id=proposal.proposal_id, evaluation=result) == finished
    with pytest.raises(LearnedRelationError, match="candidate evaluation has not passed"):
        reopened.approve_candidate(proposal_id=proposal.proposal_id, principal_id="user:one", agent_id="agent:one")
    assert plane.read_snapshot() == before
    assert writer.calls == []


def test_recovery_does_not_replace_an_unproven_legacy_evaluation(tmp_path: Path) -> None:
    path = tmp_path / "plane"
    writer = _ReplayWriter()
    runtime = _runtime(writer, MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path)))
    proposal = runtime.prepare_candidate(_proposal())
    legacy = proposal.model_copy(update={"lifecycle": "evaluating"})
    runtime._replace_proposal(proposal, legacy)

    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    reopened = _runtime(writer, plane)
    before = plane.read_snapshot()
    reopened.recover(_SCOPE)
    assert reopened._require_proposal(proposal.proposal_id) == legacy
    with pytest.raises(LearnedRelationError, match="proposal is not awaiting evaluation"):
        reopened.record_evaluation(proposal_id=proposal.proposal_id, evaluation=_passing_evaluation())
    assert plane.read_snapshot() == before
    assert writer.calls == []


def test_result_with_invalid_digest_is_not_published() -> None:
    plane = MemoryPlaneService()
    runtime = _runtime(_ReplayWriter(), plane)
    proposal = runtime.prepare_candidate(_proposal())
    before = plane.read_snapshot()
    altered = _passing_evaluation().model_copy(update={"binding_digest": "e" * 64})

    with pytest.raises(ValueError, match="paired evaluation digest is invalid"):
        runtime.record_evaluation(proposal_id=proposal.proposal_id, evaluation=altered)
    assert plane.read_snapshot() == before


@pytest.mark.parametrize("invalid_lifecycle", ("draft", "validating", "validated"))
def test_result_on_prepublication_stage_is_not_a_successful_retry(invalid_lifecycle: str) -> None:
    plane = MemoryPlaneService()
    runtime = _runtime(_ReplayWriter(), plane)
    proposal = runtime.prepare_candidate(_proposal())
    result = _passing_evaluation()
    inconsistent = proposal.model_copy(update={"lifecycle": invalid_lifecycle, "evaluation": result})
    runtime._replace_proposal(proposal, inconsistent)
    before = plane.read_snapshot()

    with pytest.raises(LearnedRelationError, match="proposal is not awaiting evaluation"):
        runtime.record_evaluation(proposal_id=proposal.proposal_id, evaluation=result)
    assert plane.read_snapshot() == before


@pytest.mark.parametrize(
    ("persisted_lifecycle", "before_predecessor_read", "winner_finishes"),
    (
        ("evaluating", True, False),
        ("evaluating", False, True),
        ("evaluated", True, True),
        ("evaluated", False, True),
    ),
)
def test_startup_recovery_accepts_the_winning_same_result_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, persisted_lifecycle: str,
    before_predecessor_read: bool, winner_finishes: bool,
) -> None:
    path = tmp_path / "plane"
    writer = _ReplayWriter()
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    recovery = _runtime(writer, plane)
    proposal = recovery.prepare_candidate(_proposal())
    result = _passing_evaluation()
    interrupted = proposal.model_copy(update={"lifecycle": persisted_lifecycle, "evaluation": result})
    recovery._replace_proposal(proposal, interrupted)
    publisher = _runtime(writer, MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path)))
    published = False

    def publish_winner() -> None:
        nonlocal published
        if published:
            return
        published = True
        if winner_finishes:
            publisher.record_evaluation(proposal_id=proposal.proposal_id, evaluation=result)
        else:
            publisher._replace_proposal(interrupted, interrupted.model_copy(update={"lifecycle": "evaluated"}))

    if before_predecessor_read:
        replace = recovery._replace_proposal

        def publish_before_read(old: OntologyChangeProposal, new: OntologyChangeProposal) -> None:
            publish_winner()
            replace(old, new)

        monkeypatch.setattr(recovery, "_replace_proposal", publish_before_read)
    else:
        write = plane.conditionally_write_records

        def publish_before_cas(*args, **kwargs):
            publish_winner()
            return write(*args, **kwargs)

        monkeypatch.setattr(plane, "conditionally_write_records", publish_before_cas)

    recovery.recover(_SCOPE)

    assert published
    finished = publisher._require_proposal(proposal.proposal_id)
    assert finished == interrupted.model_copy(update={"lifecycle": "awaiting_decision"})
    before = plane.read_snapshot()
    recovery.recover(_SCOPE)
    assert plane.read_snapshot() == before
    assert writer.calls == []


@pytest.mark.parametrize("winner_change", ("same", "result", "evidence"))
def test_concurrent_result_publishers_require_the_same_durable_proposal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, winner_change: str,
) -> None:
    path = tmp_path / "plane"
    writer = _ReplayWriter()
    runtime = _runtime(writer, MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path)))
    proposal = runtime.prepare_candidate(_proposal())
    result = _passing_evaluation()
    winner_result = FrozenMentorsPairedEvaluator().evaluate(proposal) if winner_change == "result" else result
    publisher = _runtime(writer, MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path)))
    replace = runtime._replace_proposal

    def publish_winner_first(old: OntologyChangeProposal, new: OntologyChangeProposal) -> None:
        if winner_change == "evidence":
            changed = proposal.model_copy(update={"evidence": proposal.evidence[:1]})
            publisher._replace_proposal(proposal, changed)
        publisher.record_evaluation(proposal_id=proposal.proposal_id, evaluation=winner_result)
        replace(old, new)

    monkeypatch.setattr(runtime, "_replace_proposal", publish_winner_first)
    if winner_change == "same":
        finished = runtime.record_evaluation(proposal_id=proposal.proposal_id, evaluation=result)
        assert finished == publisher._require_proposal(proposal.proposal_id)
    else:
        with pytest.raises(LearnedRelationError, match="proposal lifecycle conflicted"):
            runtime.record_evaluation(proposal_id=proposal.proposal_id, evaluation=result)

    winner = publisher._require_proposal(proposal.proposal_id)
    assert winner.lifecycle == ("evaluation_unavailable" if winner_change == "result" else "awaiting_decision")
    assert winner.evaluation == winner_result
    assert winner.evidence == (proposal.evidence[:1] if winner_change == "evidence" else proposal.evidence)
    assert writer.calls == []


@pytest.mark.parametrize("winner_timing", ("before_predecessor_read", "before_compare_and_swap"))
def test_stale_proposal_transition_preserves_the_winning_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, winner_timing: str,
) -> None:
    path = tmp_path / "plane"
    writer = _ReplayWriter()
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    runtime = _runtime(writer, plane)
    proposal = runtime.prepare_candidate(_proposal())
    competitor = _runtime(writer, MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path)))

    def finish_evaluation() -> None:
        competitor.record_evaluation(proposal_id=proposal.proposal_id, evaluation=_passing_evaluation())

    if winner_timing == "before_predecessor_read":
        finish_evaluation()
    else:
        write = plane.conditionally_write_records

        def commit_winner_first(*args, **kwargs):
            finish_evaluation()
            return write(*args, **kwargs)

        monkeypatch.setattr(plane, "conditionally_write_records", commit_winner_first)

    with pytest.raises(LearnedRelationError, match="proposal lifecycle conflicted"):
        runtime._replace_proposal(proposal, proposal.model_copy(update={"lifecycle": "evaluating"}))

    reopened = _runtime(writer, MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path)))
    winning_proposal = reopened._require_proposal(proposal.proposal_id)
    assert winning_proposal == proposal.model_copy(update={
        "lifecycle": "awaiting_decision", "evaluation": _passing_evaluation(),
    })
    assert writer.calls == []


def test_recovery_finalizes_both_selection_crash_windows_and_replay_receipts() -> None:
    writer = _ReplayWriter("revoked")
    plane = MemoryPlaneService()
    runtime = _runtime(writer, plane)
    proposal = runtime.prepare_candidate(_proposal())
    proposal = runtime.record_evaluation(proposal_id=proposal.proposal_id, evaluation=_passing_evaluation())
    proposal = runtime.approve_candidate(
        proposal_id=proposal.proposal_id, principal_id="user:one", agent_id="agent:one",
    )
    version = runtime.activate_candidate(
        proposal_id=proposal.proposal_id, principal_id="user:one", agent_id="agent:one",
    )
    # Rewriting the selected attempt as prepared simulates a crash after the
    # pointer CAS and before attempt-state finalization.
    selected = runtime._require_attempt(version.attempt_id)
    runtime._replace_attempt(selected, selected.model_copy(update={"status": "prepared"}))
    runtime.recover(_SCOPE)
    assert runtime._require_attempt(version.attempt_id).status == "selected"
    status = runtime.status(_SCOPE)
    assert status["replay_outcomes"] == {"revoked": 2}
    assert "source:one" not in repr(status)
    # A second recovery has the same two durable operation receipts and does
    # not call the ordinary writer again.
    calls = tuple(writer.calls)
    runtime.recover(_SCOPE)
    assert tuple(writer.calls) == calls


def test_pause_at_pointer_commit_blocks_selection_and_old_attempt_on_reopen(tmp_path, monkeypatch) -> None:
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(tmp_path))
    policy = CatalogManagementRepository(plane, partition_id="local:test", scope=_SCOPE)
    policy.set_state("enabled")
    writer = _ReplayWriter()

    def open_runtime(memory_plane, management):
        return LearnedRelationRuntime(
            memory_plane=memory_plane,
            replay_writer=writer,
            policy_for_scope=lambda scope: ActivationPolicy(
                owner_principal_id=scope.principal_id, owner_agent_id=scope.agent_id,
            ),
            management_fence_for_scope=management.enabled_write_fence,
        )

    runtime = open_runtime(plane, policy)
    proposal = runtime.prepare_candidate(_proposal())
    runtime.record_evaluation(proposal_id=proposal.proposal_id, evaluation=_passing_evaluation())
    owner = {"principal_id": _SCOPE.principal_id, "agent_id": _SCOPE.agent_id}
    decision = runtime.approve_candidate(proposal_id=proposal.proposal_id, **owner)
    write = plane.conditionally_write_records

    def pause_before_pointer(records, **kwargs):
        if records[0].memory_id.startswith("learned-catalog-pointer:"):
            policy.set_state("paused")
        return write(records, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(plane, "conditionally_write_records", pause_before_pointer)
        with pytest.raises(CatalogManagementUnavailable):
            runtime.activate_candidate(proposal_id=proposal.proposal_id, **owner)
    assert runtime.status(_SCOPE)["active_version_digest"] is None
    assert writer.calls == []

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(tmp_path))
    reopened_policy = CatalogManagementRepository(reopened_plane, partition_id="local:test", scope=_SCOPE)
    reopened = open_runtime(reopened_plane, reopened_policy)
    reopened.recover(_SCOPE)
    reopened_policy.set_state("enabled")
    reopened.recover(_SCOPE)
    assert reopened.status(_SCOPE)["active_version_digest"] is None
    assert reopened._require_proposal(proposal.proposal_id) == decision
    assert writer.calls == []
    activation = reopened.activate_candidate(proposal_id=proposal.proposal_id, **owner)
    assert activation.status == "selected"


def test_reference_host_reconciles_and_fences_managed_catalogs(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    workspace_one = tmp_path / "workspace-one"
    workspace_two = tmp_path / "workspace-two"
    for path in (workspace_one, workspace_two):
        with StorageAdministrationService(path) as admin:
            admin.initialize()

    class ReferenceEnrollment:
        def __init__(self, partition: str, scope: AgentLocalCatalogScope = _SCOPE) -> None:
            self.partition = partition
            self.scope = scope
            self.current: ManagedCatalogEnrollmentDecision | None = None

        def publish(self, revision: int, *, learning_allowed: bool = True) -> None:
            self.current = ManagedCatalogEnrollmentDecision(
                partition_id=self.partition,
                catalog_scope=self.scope,
                state="enabled" if learning_allowed else "paused",
                enrollment_revision=revision,
            )

        def verify(self) -> ManagedCatalogEnrollmentDecision | None:
            return self.current

        def bind(self, plane: MemoryPlaneService) -> ManagedCatalogProvisioning:
            return ManagedCatalogProvisioning(
                plane, partition_id=self.partition, scope=self.scope, verify_enrollment=self.verify,
            )

    host_one = ReferenceEnrollment("workspace-one")
    host_two = ReferenceEnrollment("workspace-two")
    admin_one, plane_one = open_managed_partition(workspace_one)
    admin_two, plane_two = open_managed_partition(workspace_two)
    writer = _ReplayWriter()
    owner = {"principal_id": _SCOPE.principal_id, "agent_id": _SCOPE.agent_id}
    try:
        one = host_one.bind(plane_one)
        two = host_two.bind(plane_two)
        runtime = one.build_learned_runtime(replay_writer=writer)
        peer_runtime = two.build_learned_runtime(replay_writer=writer)
        with pytest.raises(ManagedCatalogAuthorityError, match="unavailable"):
            one.reconcile()
        host_one.publish(revision=1)
        enrollment = one.reconcile()
        assert (enrollment.state, enrollment.generation, enrollment.enrollment_revision) == ("enabled", 1, 1)
        assert one.reconcile() == enrollment
        assert one.enabled_write_fence(_SCOPE) is not None

        # Even with identical principal and agent IDs, a cross-wired
        # workspace decision cannot provision the peer.
        host_two.current = host_one.current
        with pytest.raises(ManagedCatalogAuthorityError, match="unavailable"):
            two.reconcile()
        host_two.publish(revision=1, learning_allowed=False)
        denied = two.reconcile()
        assert (denied.state, denied.generation) == ("paused", 1)
        with pytest.raises(CatalogManagementUnavailable):
            peer_runtime.prepare_candidate(_proposal())
        assert peer_runtime.status(_SCOPE)["candidate_count"] == 0

        proposal = runtime.prepare_candidate(_proposal())
        assert runtime.record_evaluation(
            proposal_id=proposal.proposal_id, evaluation=_passing_evaluation(),
        ).lifecycle == "awaiting_decision"
        approved = runtime.approve_candidate(proposal_id=proposal.proposal_id, **owner)
        write = plane_one.conditionally_write_records

        def withdraw_before_pointer(records, **kwargs):
            if records[0].memory_id.startswith("learned-catalog-pointer:"):
                host_one.publish(revision=2, learning_allowed=False)
                assert one.reconcile().generation == 2
            return write(records, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(plane_one, "conditionally_write_records", withdraw_before_pointer)
            with pytest.raises(CatalogManagementUnavailable):
                runtime.activate_candidate(proposal_id=proposal.proposal_id, **owner)
        assert runtime.status(_SCOPE)["active_version_digest"] is None
        assert writer.calls == []
    finally:
        admin_one.close()
        admin_two.close()

    reopened_admin, reopened_plane = open_managed_partition(workspace_one)
    try:
        one = host_one.bind(reopened_plane)
        runtime = one.build_learned_runtime(replay_writer=writer)
        assert one.reconcile().generation == 2
        host_one.publish(revision=1)
        with pytest.raises(ManagedCatalogAuthorityError, match="stale or conflicting"):
            one.reconcile()
        host_one.publish(revision=2)
        with pytest.raises(ManagedCatalogAuthorityError, match="stale or conflicting"):
            one.reconcile()
        assert one.enabled_write_fence(_SCOPE) is None
        host_one.publish(revision=3)
        assert one.reconcile().generation == 3
        runtime.recover(_SCOPE)
        assert runtime.status(_SCOPE)["active_version_digest"] is None
        assert runtime._require_proposal(proposal.proposal_id) == approved
        assert writer.calls == []
        activation = runtime.activate_candidate(proposal_id=proposal.proposal_id, **owner)
        assert activation.status == "selected"
        host_one.publish(revision=4)
        fence = one.enabled_write_fence(_SCOPE)
        assert fence is None
        refreshed = one.reconcile()
        assert refreshed.generation == 4
        assert one.enabled_write_fence(_SCOPE) is not None

        same_workspace_peer = ReferenceEnrollment(
            "workspace-one", AgentLocalCatalogScope(principal_id=_SCOPE.principal_id, agent_id="agent:two"),
        )
        same_workspace_peer.publish(revision=1)
        peer = same_workspace_peer.bind(reopened_plane)
        peer.reconcile()
        peer_runtime = peer.build_learned_runtime(replay_writer=writer)
        peer_owner = {"principal_id": _SCOPE.principal_id, "agent_id": "agent:two"}
        with pytest.raises(LearnedRelationError, match="outside the installed binding"):
            peer_runtime.activate_candidate(proposal_id=proposal.proposal_id, **peer_owner)
        with pytest.raises(LearnedRelationError, match="outside the installed binding"):
            peer_runtime.select_prior_version(
                catalog_scope=_SCOPE, target_version_digest=activation.target_version_digest, **peer_owner,
            )
        with pytest.raises(LearnedRelationError, match="outside the installed binding"):
            peer_runtime.status(_SCOPE)
        with pytest.raises(LearnedRelationError, match="outside the installed binding"):
            peer_runtime.recover(_SCOPE)
    finally:
        reopened_admin.close()


def test_host_authority_is_checked_inside_the_approval_write(monkeypatch) -> None:
    plane = MemoryPlaneService()
    policy = CatalogManagementRepository(plane, partition_id="local:test", scope=_SCOPE)
    policy.set_state("enabled")
    host_current = True

    def validate_host():
        if not host_current:
            raise CatalogManagementUnavailable("host authority withdrawn")

    runtime = LearnedRelationRuntime(
        memory_plane=plane,
        replay_writer=_ReplayWriter(),
        policy_for_scope=lambda scope: ActivationPolicy(
            owner_principal_id=scope.principal_id, owner_agent_id=scope.agent_id,
        ),
        management_fence_for_scope=policy.enabled_write_fence,
        validate_management_host=validate_host,
    )
    proposal = runtime.prepare_candidate(_proposal())
    evaluated = runtime.record_evaluation(
        proposal_id=proposal.proposal_id, evaluation=_passing_evaluation(),
    )
    write = plane.conditionally_write_records

    def withdraw_host_before_write(*args, **kwargs):
        nonlocal host_current
        host_current = False
        return write(*args, **kwargs)

    monkeypatch.setattr(plane, "conditionally_write_records", withdraw_host_before_write)
    with pytest.raises(CatalogManagementUnavailable, match="host authority withdrawn"):
        runtime.approve_candidate(
            proposal_id=proposal.proposal_id, principal_id=_SCOPE.principal_id, agent_id=_SCOPE.agent_id,
        )
    assert runtime._require_proposal(proposal.proposal_id) == evaluated


def test_rollback_only_selects_prior_selected_same_scope_ancestor_without_new_catalog_state() -> None:
    """Rollback is a pointer move, never a new learned catalog publication."""
    writer = _ReplayWriter()
    runtime = _runtime(writer)
    first = _approve_and_activate(runtime, _proposal_from_parent(
        parent_catalog_digest="a" * 64, source_id="source:first", source_digit="1",
    ))
    second = _approve_and_activate(runtime, _proposal_from_parent(
        parent_catalog_digest=first.target_version_digest, source_id="source:second", source_digit="2",
    ))
    pointer = runtime._load_pointer(_SCOPE)
    assert pointer is not None and pointer.selected_version_digest == second.target_version_digest

    # An orphan, a sibling, a foreign-scope version, and an ancestor without a
    # selected activation must never become rollback targets.
    orphan = OntologyCatalogVersion.create(
        catalog_scope=_SCOPE, catalog_digest="3" * 64, parent_version_digest=None,
        relation_ids=("mentors",), introduced_proposal_id=None,
    )
    sibling = OntologyCatalogVersion.create(
        catalog_scope=_SCOPE, catalog_digest="4" * 64,
        parent_version_digest=first.target_version_digest, relation_ids=("mentors",),
        introduced_proposal_id=None,
    )
    foreign_scope = AgentLocalCatalogScope(principal_id="user:two", agent_id="agent:two")
    foreign = OntologyCatalogVersion.create(
        catalog_scope=foreign_scope, catalog_digest="5" * 64, parent_version_digest=None,
        relation_ids=("mentors",), introduced_proposal_id=None,
    )
    for version in (orphan, sibling, foreign):
        runtime._write_version(version)
        with pytest.raises(LearnedRelationError, match="selected ancestor"):
            runtime.select_prior_version(
                catalog_scope=_SCOPE, target_version_digest=version.version_digest,
                principal_id="user:one", agent_id="agent:one",
            )

    first_attempt = runtime._require_attempt(first.attempt_id)
    for terminal_status in ("prepared", "abandoned"):
        runtime._replace_attempt(first_attempt, first_attempt.model_copy(update={"status": terminal_status}))
        with pytest.raises(LearnedRelationError, match="selected history"):
            runtime.select_prior_version(
                catalog_scope=_SCOPE, target_version_digest=first.target_version_digest,
                principal_id="user:one", agent_id="agent:one",
            )
        first_attempt = runtime._require_attempt(first.attempt_id)
    runtime._replace_attempt(first_attempt, first_attempt.model_copy(update={"status": "selected"}))

    before_versions = len(runtime._plane.list_records(source_kind="learned_ontology_catalog_version_v1"))
    before_proposals = len(runtime._plane.list_records(source_kind="learned_ontology_change_proposal_v1"))
    stale = OntologyActivation.create(
        schema_version=1, catalog_scope=_SCOPE, operation="select_prior_version",
        proposal_id=None, target_version_digest=first.target_version_digest,
        expected_pointer_digest=pointer.pointer_digest,
        expected_pointer_sequence=pointer.activation_sequence,
        authorizing_decision_digest="6" * 64, status="prepared",
    )
    runtime._write_attempt(stale)
    rollback = runtime.select_prior_version(
        catalog_scope=_SCOPE, target_version_digest=first.target_version_digest,
        principal_id="user:one", agent_id="agent:one",
    )
    assert rollback.status == "selected"
    with pytest.raises(LearnedRelationError, match="stale"):
        runtime._select(attempt=stale, expected_pointer=pointer)
    assert len(runtime._plane.list_records(source_kind="learned_ontology_catalog_version_v1")) == before_versions
    assert len(runtime._plane.list_records(source_kind="learned_ontology_change_proposal_v1")) == before_proposals


@pytest.mark.parametrize("outcome", ["revoked", "deleted"])
def test_failed_retained_replay_writes_one_durable_receipt_without_retry_effect(outcome: str) -> None:
    writer = _ReplayWriter(outcome)
    plane = MemoryPlaneService()
    runtime = _runtime(writer, plane)
    _approve_and_activate(runtime, _proposal_from_parent(
        parent_catalog_digest="a" * 64, source_id=f"source:{outcome}", source_digit="7",
    ))
    status = runtime.status(_SCOPE)
    assert status["replay_outcomes"] == {outcome: 1}
    assert status["last_error"] == f"replay_{outcome}"
    assert f"source:{outcome}" not in repr(status)
    calls = tuple(writer.calls)
    runtime.recover(_SCOPE)
    assert tuple(writer.calls) == calls
    assert len(plane.list_records(source_kind="learned_ontology_replay_operation_v1")) == 1


def test_status_is_scope_bounded_and_exposes_only_closed_operational_values() -> None:
    writer = _ReplayWriter("deleted")
    runtime = _runtime(writer)
    selected = _approve_and_activate(runtime, _proposal_from_parent(
        parent_catalog_digest="a" * 64, source_id="source:private", source_digit="8",
    ))
    status = runtime.status(_SCOPE)
    assert status == {
        "active_catalog_digest": runtime._require_version(selected.target_version_digest).catalog_digest,
        "active_version_digest": selected.target_version_digest,
        "activation_sequence": 1,
        "selected_attempt_id": selected.attempt_id,
        "candidate_count": 1,
        "candidate_ids": (_proposal_from_parent(
            parent_catalog_digest="a" * 64,
            source_id="source:private",
            source_digit="8",
        ).proposal_id,),
        "replay_outcomes": {"deleted": 1},
        "last_error": "replay_deleted",
    }
    other = runtime.status(AgentLocalCatalogScope(principal_id="user:two", agent_id="agent:two"))
    assert other == {
        "active_catalog_digest": None, "active_version_digest": None,
        "activation_sequence": None, "candidate_count": 0,
        "candidate_ids": (),
        "replay_outcomes": {}, "last_error": None,
    }


def test_agent_local_scope_and_automatic_policy_fail_closed_without_calibration() -> None:
    policy = ActivationPolicy(owner_principal_id="user:one", owner_agent_id="agent:one",
                              automatic_activation_enabled=True, calibration_labels=59,
                              calibration_correct=59, calibration_binding_digest="f" * 64)
    assert policy.allows_automatic_activation(binding_digest="f" * 64, mandatory_gates_pass=True)
    assert not ActivationPolicy(owner_principal_id="user:one", owner_agent_id="agent:one",
                                automatic_activation_enabled=True, calibration_labels=58,
                                calibration_correct=58, calibration_binding_digest="f" * 64).allows_automatic_activation(
                                    binding_digest="f" * 64, mandatory_gates_pass=True)
    assert not ActivationPolicy(owner_principal_id="user:one", owner_agent_id="agent:one",
                                automatic_activation_enabled=True, calibration_labels=59,
                                calibration_correct=58, calibration_binding_digest="f" * 64).allows_automatic_activation(
                                    binding_digest="f" * 64, mandatory_gates_pass=True)
    assert not policy.allows_automatic_activation(binding_digest="e" * 64, mandatory_gates_pass=True)
    with pytest.raises(ValueError):
        AgentLocalCatalogScope()
    with pytest.raises(ValueError):
        AgentLocalCatalogScope(principal_id="", agent_id="agent:one")


def test_agent_local_selected_bundle_pins_and_resolves_its_exact_historical_version() -> None:
    writer = _ReplayWriter()
    plane = MemoryPlaneService()
    runtime = _runtime(writer, plane)
    proposal = runtime.prepare_candidate(_proposal())
    evaluated = runtime.record_evaluation(proposal_id=proposal.proposal_id, evaluation=_passing_evaluation())
    approved = runtime.approve_candidate(
        proposal_id=evaluated.proposal_id, principal_id="user:one", agent_id="agent:one",
    )
    runtime.activate_candidate(proposal_id=approved.proposal_id, principal_id="user:one", agent_id="agent:one")
    _revision, records = plane.read_snapshot()

    locator = PackageIndexedCatalogBundleLocator()
    bundle, pointer = locator.locate_selected(records, scope=_SCOPE, authenticated=_authenticated())
    historical = locator.locate_historical(
        records, scope=_SCOPE, authenticated=_authenticated(),
        version_id=bundle.version.version_id, version_digest=bundle.version.version_digest,
    )
    pin = CatalogCapturedTurnPin.from_bundle(
        ledger=_ledger(), bundle=bundle, selection_pointer_digest=pointer.pointer_digest,
    )

    assert bundle.catalog.catalog_scope == _SCOPE
    assert historical.version == bundle.version
    assert historical.runtime_bundle_digest == bundle.runtime_bundle_digest
    assert pin.catalog_scope == _SCOPE
    assert pin.selected_version_digest == bundle.version.version_digest


def test_agent_local_catalog_denies_other_owner_and_invalid_selected_child() -> None:
    writer = _ReplayWriter()
    plane = MemoryPlaneService()
    runtime = _runtime(writer, plane)
    proposal = runtime.prepare_candidate(_proposal())
    evaluated = runtime.record_evaluation(proposal_id=proposal.proposal_id, evaluation=_passing_evaluation())
    approved = runtime.approve_candidate(
        proposal_id=evaluated.proposal_id, principal_id="user:one", agent_id="agent:one",
    )
    runtime.activate_candidate(proposal_id=approved.proposal_id, principal_id="user:one", agent_id="agent:one")
    _revision, records = plane.read_snapshot()
    locator = PackageIndexedCatalogBundleLocator()

    with pytest.raises(CatalogAuthorityError, match="agent-local catalog selection"):
        locator.locate_selected(
            records, scope=_SCOPE,
            authenticated=AuthenticatedPrincipalAgent(principal_id="user:two", agent_id="agent:two"),
        )
    bundle, pointer = locator.locate_selected(records, scope=_SCOPE, authenticated=_authenticated())
    with pytest.raises(CatalogAuthorityError, match="agent-local catalog owner"):
        CatalogCapturedTurnPin.from_bundle(
            ledger=_ledger(principal_id="user:two", agent_id="agent:two"),
            bundle=bundle, selection_pointer_digest=pointer.pointer_digest,
        )

    pointer_record = next(record for record in records if record.memory_id.startswith("learned-catalog-pointer:"))
    corrupt = pointer_record.model_copy(update={"content": {"pointer": {}}})
    malformed = tuple(corrupt if record.memory_id == pointer_record.memory_id else record for record in records)
    with pytest.raises(CatalogAuthorityError, match="agent-local catalog selection"):
        locator.locate_selected(malformed, scope=_SCOPE, authenticated=_authenticated())


def test_mentors_grammar_accepts_only_direct_person_relation() -> None:
    proposal = ProviderSemanticProposal(
        abstained=False,
        mentions=(
            ProviderMention(local_id="alice", mention_quote="Alice", mention_context_quote="Alice mentors Bob.", proposed_type="Person"),
            ProviderMention(local_id="bob", mention_quote="Bob", mention_context_quote="Alice mentors Bob.", proposed_type="Person"),
        ),
        facts=(ProviderFact(
            local_id="fact", predicate_id="mentors", subject_entity_ref="alice",
            object=ProviderEntityObject(entity_ref="bob"), assertion_quote="Alice mentors Bob.",
            predicate_anchor_quote="mentors", polarity="positive", commitment="asserted",
        ),),
    )
    arguments = {
        "source_quote": "Alice mentors Bob.", "subject_quote": "Alice",
        "predicate_anchor_quote": "mentors", "object_quote": "Bob",
    }
    validate_mentors_tool_proposal(proposal, arguments=arguments)
    with pytest.raises(ValueError, match="relation shape"):
        validate_mentors_tool_proposal(
            proposal.model_copy(update={"facts": (proposal.facts[0].model_copy(update={"assertion_quote": "Alice might mentor Bob."}),)}),
            arguments=arguments,
        )
