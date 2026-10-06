"""The revoked-identity view gates every serving surface it composes into."""

from datetime import UTC, datetime

from memorii.core.harness_state.service import HarnessStateService
from memorii.core.memory_evolution.models import (
    ClaimKey,
    ClaimLifecycleState,
    ClaimSemanticContext,
    ClaimState,
    ConfidenceComponents,
    EntityLinkState,
)
from memorii.core.memory_evolution.service import MemoryEvolutionService
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.persistence.runtime_checkpoint import build_resume_envelope
from memorii.core.persistence.runtime_contracts import (
    NodeEvidenceReference,
    SolverJustificationRecord,
    SolverRunRecord,
    TaskRecord,
)
from memorii.core.storage_administration.revoked_identity_view import (
    RevokedIdentities,
    RevokedIdentityView,
)
from memorii.core.storage_administration.suppression_journal import (
    SuppressionCoordinate,
    SuppressionRecord,
    write_suppression_record,
)
from memorii.domain.enums import CommitStatus, MemoryDomain

NOW = datetime.now(UTC)


def _view(**overrides) -> RevokedIdentityView:
    return RevokedIdentityView(RevokedIdentities(**overrides))


def _link(link_id: str, entity: str, name: str) -> EntityLinkState:
    return EntityLinkState(
        link_id=link_id, mention_text=name, canonical_entity_id=entity,
        normalized_name=name.lower(), aliases=[name], observed_names=[name.lower()],
        confidence=0.9,
    )


def _claim(claim_id: str, subject: str, value: str) -> ClaimState:
    truth = {
        "assertion_mode": "world_assertion", "epistemic_status": "asserted",
        "polarity": "positive", "modality": "assertion",
    }
    return ClaimState(
        claim_id=claim_id,
        claim_key=ClaimKey(subject_entity_id=subject, predicate_id="owns", **truth),
        object_value=value,
        lifecycle_state=ClaimLifecycleState.ACTIVE,
        source_claim_id=f"source:{claim_id}",
        confidence=ConfidenceComponents(
            extraction=0.9, evidence=0.8, source_trust=0.7, calibrated=0.9
        ),
        semantic_context=ClaimSemanticContext(
            attribution_source_id=f"source:{claim_id}", **truth
        ),
    )


def _claim_record(state: ClaimState) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=f"mem:evolution:claim:{state.claim_id}",
        domain=MemoryDomain.SEMANTIC, text=state.object_value,
        content={"memory_evolution_kind": "claim_state",
                 "claim_state": state.model_dump(mode="python")},
        status=CommitStatus.COMMITTED, source_kind="memory_evolution",
    )


def _link_record(link: EntityLinkState) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=f"mem:evolution:link:{link.link_id}",
        domain=MemoryDomain.SEMANTIC, text=link.mention_text,
        content={"memory_evolution_kind": "entity_link",
                 "entity_link": link.model_dump(mode="python")},
        status=CommitStatus.COMMITTED, source_kind="memory_evolution",
    )


def test_view_derives_from_journal_and_filters_records(tmp_path) -> None:
    control_root = tmp_path / "control"
    write_suppression_record(
        control_root,
        SuppressionRecord(
            suppression_id="a" * 64,
            plan_digest="b" * 64,
            closure_digest="c" * 64,
            scope_note="note",
            suppressed=(
                SuppressionCoordinate(coordinate_kind="claim",
                                      coordinate_id="claim:gone"),
                SuppressionCoordinate(coordinate_kind="entity",
                                      coordinate_id="entity:ada"),
            ),
            applied_at_unix=1,
        ),
    )
    from memorii.core.storage_administration.revoked_identity_view import (
        view_from_control_root,
    )

    view = view_from_control_root(control_root)
    assert view.is_revoked_entity("entity:ada")
    assert view.is_revoked_claim("claim:gone")
    assert not view.is_revoked_entity("entity:other")

    kept = view.filter_records(
        (_claim_record(_claim("claim:kept", "entity:kept", "kept")),
         _claim_record(_claim("claim:gone", "entity:ada", "gone")),
         _link_record(_link("link:kept", "entity:kept", "Kept")),
         _link_record(_link("link:gone", "entity:ada", "Gone")))
    )
    assert tuple(record.memory_id for record in kept) == (
        "mem:evolution:claim:claim:kept",
        "mem:evolution:link:link:kept",
    )


def test_retrieval_view_excludes_revoked_identities_before_lifecycle() -> None:
    plane = MemoryPlaneService()
    plane.upsert_record(_claim_record(_claim("claim:gone", "entity:gone", "Gone Owner")))
    plane.upsert_record(_link_record(_link("link:gone", "entity:gone", "Goneowner")))
    service = MemoryEvolutionService(
        memory_plane=plane,
        revoked_view=_view(entities=frozenset({"entity:gone"})),
    )

    decision = service.retrieve(
        __import__(
            "memorii.core.memory_evolution", fromlist=["MemoryQueryRequest"]
        ).MemoryQueryRequest(query="Who is the Goneowner?", reference_time=NOW),
    )

    assert decision.selected_record_ids == []


def test_harness_envelope_marks_revoked_justifications(tmp_path) -> None:
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parent))
    from test_storage_administration_operator import _operator

    operator, service = _operator(tmp_path)
    try:
        from memorii.core.persistence.runtime_repository import (
            RuntimeStateRepository,
            publish_runtime_change,
        )

        repository = RuntimeStateRepository(service.partition())

        def seed(connection, repo) -> None:
            repo.apply_task(
                connection,
                TaskRecord(
                    task_id="task:view", principal="p", goal="g",
                    created_at=NOW, root_execution_node_id="exec:root",
                ),
            )
            repo.apply_solver_run(
                connection,
                SolverRunRecord(
                    solver_id="solver:view", task_id="task:view",
                    parent_execution_node_id="exec:root",
                    category="reasoning", created_by="p",
                ),
            )
            repo.apply_justification(
                connection,
                SolverJustificationRecord(
                    justification_id="justification:view", solver_id="solver:view",
                    conclusion="c", supporting_ids=(), contradicting_ids=(),
                    assumption_ids=(), strength=0.9, active=True,
                    source_refs=(NodeEvidenceReference(source_id="source:x"),),
                ),
            )

        publish_runtime_change(service, seed, operation_binding="view_seed")
        view = _view(justifications=frozenset({"justification:view"}))
        envelope = HarnessStateService(
            repository, revoked_view=view
        ).read_state(
            task_id="task:view",
            grant=_read_grant(repository, "task:view"),
            view="solver",
        )
        assert envelope.status == "revalidation_required"
        rendered = envelope.model_dump(mode="json")
        assert "justification:view" not in str(
            rendered.get("candidate_hypotheses", "")
        )
        resume = build_resume_envelope(
            repository, task_id="task:view", revoked_view=view
        )
        assert "justification:view:revoked_evidence" in resume.revalidation_reasons
        assert resume.status == "revalidation_required"
    finally:
        service.close()


def _read_grant(repository, task_id: str):
    from datetime import timedelta

    from memorii.core.harness_state.service import RuntimeReadGrant

    return RuntimeReadGrant(
        grant_id="grant:view", principal="p", epoch=1,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
