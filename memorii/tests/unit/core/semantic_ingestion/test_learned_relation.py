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
from memorii.core.semantic_ingestion.hermes_captured_turn import HermesCapturedTurnLedger
from memorii.core.semantic_ingestion.learned_relation import (
    ActivationPolicy,
    AgentLocalCatalogScope,  # noqa: I001
    LearnedRelationError,
    LearnedRelationRuntime,
    OntologyChangeProposal,
    OntologyEvidenceReference,
    PairedEvaluation,
    RelationDeclaration,
)


class _ReplayWriter:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def replay_retained_source(self, *, source_id: str, source_digest: str,
                               catalog_scope: AgentLocalCatalogScope, catalog_digest: str,
                               replay_operation_id: str) -> str:
        self.calls.append(replay_operation_id)
        return "committed"


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
    with pytest.raises(LearnedRelationError, match="authorization"):
        runtime.approve_candidate(proposal_id=evaluated.proposal_id,
                                  principal_id="user:two", agent_id="agent:two")
    with pytest.raises(LearnedRelationError, match="has not passed"):
        runtime.approve_candidate(proposal_id=evaluated.proposal_id,
                                  principal_id="user:one", agent_id="agent:one")
    assert writer.calls == []


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
