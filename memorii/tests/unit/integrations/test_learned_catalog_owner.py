"""Scoped owner decisions through the installed local ontology bindings."""

from __future__ import annotations

import socket
from pathlib import Path
from types import SimpleNamespace

import pytest
from memorii.core.semantic_ingestion.default_catalog_package import load_packaged_default_catalog_release
from memorii.core.semantic_ingestion.learned_relation import (
    AgentLocalCatalogScope,
    CatalogManagementUnavailable,
    LearnedRelationError,
    OntologyChangeProposal,
    OntologyEvidenceReference,
    PairedEvaluation,
    PairedEvaluationCaseOutcome,
    RelationDeclaration,
)
from memorii.integrations.hermes_factory import (
    build_local_level2_authenticated_source_runtime,
    build_local_level2_runtime_binding,
)
from memorii.integrations.hermes_local_authority import (
    authorize_local_level2,
    authorize_local_structured_tool,
    local_catalog_management,
)
from tests.unit.integrations.test_hermes_memory_provider_bridge import (
    _FactoryEntryPoint,
)
from tests.unit.integrations.test_hermes_memory_provider_bridge import (
    bridge_module as bridge_module,
)


def test_installed_owner_review_rejection_and_refresh_reopen(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.core.semantic_ingestion.coverage_observation import CoverageObservationRepository

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def deny_network(*_args: object, **_kwargs: object) -> None:
        pytest.fail("owner review and decisions must not use the network")

    monkeypatch.setattr(socket, "getaddrinfo", deny_network)
    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_network)
    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    monkeypatch.setattr(
        bridge_module.importlib.metadata, "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    host = {
        "hermes_home": tmp_path, "user_id": "raw:user:one", "agent_identity": "profile:primary",
        "platform": "cli", "agent_context": "primary", "agent_workspace": "hermes",
    }
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider.initialize("session:review", **host)
    try:
        local_catalog_management(hermes_home=tmp_path, state="enabled")
        text = "Atlas mentors Ada."
        provider.on_turn_start(1, text)
        runtime = provider._completed_turn_runtime
        learned = provider._learned_ontology_runtime
        ledger = runtime._active_turn.ledger
        plane = provider._provider._service._memory_plane
        observation = next(
            item for item in CoverageObservationRepository(plane).all() if item.source_id == ledger.source_id
        )
        scope = AgentLocalCatalogScope(
            principal_id=provider._absent_author_id, agent_id=runtime._authenticated_agent_id,
        )
        reference = OntologyEvidenceReference(
            source_id=ledger.source_id, source_digest=ledger.source_digest,
            origin_lineage_digest=observation.origin_lineage_digest,
            source_scope_digest=observation.source_scope_digest,
        )
        binding_digest = "4" * 64
        corpus_digest = "5" * 64
        budget_digest = "6" * 64
        case = PairedEvaluationCaseOutcome(
            case_id="negative-no-assertion", expected="deny_or_abstain",
            parent_status="denied", candidate_status="abstained", candidate_read_status="denied",
            binding_digest=binding_digest, corpus_digest=corpus_digest, budget_digest=budget_digest,
        )
        evaluation = PairedEvaluation.create(
            binding_digest=binding_digest, targeted_positive_count=2,
            targeted_positive_committed_and_read=2, parent_regressions=0,
            unsupported_or_misleading_failures=0, scope_or_provenance_failures=0,
            available=True, corpus_digest=corpus_digest, budget_digest=budget_digest,
            case_outcomes=(case,),
        )
        parent = load_packaged_default_catalog_release().child_version.version_digest

        def evaluated(description: str) -> OntologyChangeProposal:
            proposal = learned.prepare_candidate(OntologyChangeProposal.create(
                catalog_scope=scope, parent_catalog_digest=parent,
                relation=RelationDeclaration(description=description),
                evidence=(reference, OntologyEvidenceReference(
                    source_id="source:absent", source_digest="a" * 64,
                    origin_lineage_digest="b" * 64, source_scope_digest="c" * 64,
                )),
            ))
            return learned.record_evaluation(proposal_id=proposal.proposal_id, evaluation=evaluation)

        declined = evaluated("Candidate for owner rejection.")
        review = provider.review_learned_candidate(declined.proposal_id)
        assert review.evidence == (reference,)
        assert review.relation == declined.relation
        assert review.parent_status == "selected"
        assert review.parent_version_digest == parent
        assert review.evaluation == evaluation
        assert review.owner_decision is None
        assert text not in review.model_dump_json()

        original_write = plane.conditionally_write_records

        def pause_before_rejection(records, **kwargs):
            if any(record.memory_id == declined.proposal_id for record in records):
                local_catalog_management(hermes_home=tmp_path, state="paused")
            return original_write(records, **kwargs)

        with monkeypatch.context() as between:
            between.setattr(plane, "conditionally_write_records", pause_before_rejection)
            with pytest.raises(CatalogManagementUnavailable):
                provider.reject_learned_candidate(declined.proposal_id)
        with pytest.raises(CatalogManagementUnavailable):
            provider.review_learned_candidate(declined.proposal_id)
        local_catalog_management(hermes_home=tmp_path, state="enabled")
        assert provider.review_learned_candidate(declined.proposal_id).lifecycle == "awaiting_decision"
        assert provider.reject_learned_candidate(declined.proposal_id) == "rejected"

        approved = evaluated("Candidate for selected catalog refresh.")
        approval = provider.approve_learned_candidate(approved.proposal_id)
        assert approval.model_dump() == {
            "proposal_id": approved.proposal_id, "lifecycle": "approved_for_activation",
        }
        assert provider.approve_learned_candidate(approved.proposal_id) == approval
        assert provider.review_learned_candidate(approved.proposal_id).owner_decision == "approved"
        service = provider._provider._service

        def unavailable_refresh(_service: object, **_kwargs: object) -> None:
            raise OSError("transient grant publication failure")

        with monkeypatch.context() as during:
            during.setattr(type(service), "provision_structured_submission_authority", unavailable_refresh)
            selected = provider.activate_learned_candidate(approved.proposal_id)
            status = provider.lookup_learned_ontology_status()
            assert status["selected_attempt_id"] == selected.attempt_id
            assert status["refresh_pending"] is True
            reopening = build_local_level2_authenticated_source_runtime(SimpleNamespace(
                **host, storage_root=tmp_path / "memorii", session_id="session:review", parent_session_id=None,
            ))
            try:
                assert reopening.lookup_learned_ontology_status() == status
                assert not reopening.retry_learned_catalog_refresh()
            finally:
                reopening.close()
        assert provider.retry_learned_catalog_refresh()
        assert provider.activate_learned_candidate(approved.proposal_id) == selected
        assert provider.lookup_learned_ontology_status()["refresh_pending"] is False
    finally:
        provider.shutdown()
    with pytest.raises(RuntimeError, match="review is unavailable"):
        provider.review_learned_candidate(declined.proposal_id)

    generic = build_local_level2_authenticated_source_runtime(SimpleNamespace(
        **host, storage_root=tmp_path / "memorii", session_id="session:review", parent_session_id=None,
    ))
    try:
        reopened = generic.review_learned_candidate(declined.proposal_id)
        assert reopened.owner_decision == "rejected"
        assert reopened.evidence == (reference,)
        assert reopened.parent_status == "historical"
        assert reopened.selected_version_digest == selected.target_version_digest
        assert generic.reject_learned_candidate(declined.proposal_id) == "rejected"
        with pytest.raises(LearnedRelationError, match="not passed"):
            generic.approve_learned_candidate(declined.proposal_id)
        assert generic.lookup_learned_ontology_status()["selected_attempt_id"] == selected.attempt_id
        local_catalog_management(hermes_home=tmp_path, state="paused")
        with pytest.raises(CatalogManagementUnavailable):
            generic.activate_learned_candidate(approved.proposal_id)
        with pytest.raises(CatalogManagementUnavailable):
            generic.select_prior_learned_version(selected.target_version_digest)
        with pytest.raises(CatalogManagementUnavailable):
            generic.retry_learned_catalog_refresh()
        with pytest.raises(CatalogManagementUnavailable):
            generic.prepare_learned_rebase()
        local_catalog_management(hermes_home=tmp_path, state="enabled")
        assert generic.select_prior_learned_version(selected.target_version_digest) == selected
    finally:
        generic.close()
