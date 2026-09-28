from __future__ import annotations

from datetime import UTC, datetime

import pytest
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.semantic_ingestion.catalog_authority import (
    AuthenticatedPrincipalAgent,
    CatalogAuthorityError,
)
from memorii.core.semantic_ingestion.catalog_capture_pin import (
    CatalogCapturedTurnPin,
    PackageIndexedCatalogBundleLocator,
)
from memorii.core.semantic_ingestion.contracts import (
    ProviderEntityObject,
    ProviderFact,
    ProviderMention,
    ProviderSemanticProposal,
)
from memorii.core.semantic_ingestion.hermes_captured_turn import HermesCapturedTurnLedger
from memorii.core.semantic_ingestion.learned_relation import (
    ActivationPolicy,
    AgentLocalCatalogScope,  # noqa: I001
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
