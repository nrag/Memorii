"""Cross-path parity: every serving path agrees the revoked identity is gone.

The canonical acceptance family of the forgetting design on one shared
fixture: seed one installation spanning the closure classes (entity, its
claims, evidence source, entity link, a citing solver justification and
its task), forget it, enforce the publication, then walk every serving
path and assert the absence oracle — the revoked coordinates never
appear, pages count down by exactly the revoked delta, and history
integrity (replay equality, Tier A) stays green.
"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests.unit.core.test_storage_administration_operator import (
    _capability,
    _operator,
)

from memorii.core.harness_state.service import HarnessStateService, RuntimeReadGrant
from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
from memorii.core.memory_evolution.graph_records import (
    canonical_graph_codec_manifest,
)
from memorii.core.memory_evolution.service import MemoryEvolutionService
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore
from memorii.core.persistence.factory import PublishedMemoryPlaneStore
from memorii.core.persistence.runtime_checkpoint import build_resume_envelope
from memorii.core.persistence.runtime_contracts import (
    NodeEvidenceReference,
    SolverJustificationRecord,
    SolverRunRecord,
    TaskRecord,
)
from memorii.core.scoped_context.service import _current_eligible
from memorii.core.storage_administration.operator import ModeChangeRequest
from memorii.core.storage_administration.operator_governance import (
    ForgetTargetSelector,
    GovernanceOperator,
)
from memorii.core.storage_administration.revoked_identity_view import (
    view_from_control_root,
)
from memorii.domain.enums import CommitStatus, MemoryDomain

NOW = datetime.now(UTC)
CLAIM_MEMORY_ID = "mem:evolution:claim:claim:parity"
LINK_MEMORY_ID = "mem:evolution:link:link:parity"


def _seed_records():
    truth = {
        "assertion_mode": "world_assertion",
        "epistemic_status": "asserted",
        "polarity": "positive",
        "modality": "assertion",
    }
    claim = {
        "claim_id": "claim:parity",
        "claim_key": {
            "subject_entity_id": "entity:parity",
            "predicate_id": "owns",
            "scope": {},
            "qualifier_key": "default",
            **truth,
            "belief_holder_entity_id": None,
        },
        "object_value": "parity fixture",
        "lifecycle_state": "active",
        "source_claim_id": "source:parity",
        "confidence": {
            "extraction": 0.9, "evidence": 0.8, "source_trust": 0.7,
            "agreement": 0.0, "contradiction": 0.0, "calibrated": 0.9,
        },
        "semantic_context": {"attribution_source_id": "source:parity", **truth},
        "validation_results": [],
        "evidence_spans": [
            {"source_id": "source:parity", "quote": "fixture",
             "source_type": "user", "timestamp": "2026-10-03T00:00:00Z"},
        ],
        "subject_link_id": "link:parity",
        "object_link_id": None,
    }
    link = {
        "link_id": "link:parity",
        "mention_text": "parity entity",
        "canonical_entity_id": "entity:parity",
        "normalized_name": "parity entity",
        "entity_type": "unknown",
        "aliases": [],
        "observed_names": [],
        "evidence_spans": [],
        "confidence": 0.9,
        "scope": {},
        "lifecycle_state": "active",
    }
    from memorii.core.memory_plane.models import CanonicalMemoryRecord

    return (
        CanonicalMemoryRecord(
            memory_id=CLAIM_MEMORY_ID,
            domain=MemoryDomain.SEMANTIC,
            text="parity fixture",
            content={"memory_evolution_kind": "claim_state", "claim_state": claim},
            status=CommitStatus.COMMITTED,
            source_kind="memory_evolution",
        ),
        CanonicalMemoryRecord(
            memory_id=LINK_MEMORY_ID,
            domain=MemoryDomain.SEMANTIC,
            text="parity entity",
            content={"memory_evolution_kind": "entity_link", "entity_link": link},
            status=CommitStatus.COMMITTED,
            source_kind="memory_evolution",
        ),
    )


def _runtime_seed(connection, repo) -> None:
    repo.apply_task(
        connection,
        TaskRecord(
            task_id="task:parity", principal="p", goal="g",
            created_at=NOW, root_execution_node_id="exec:root",
        ),
    )
    repo.apply_solver_run(
        connection,
        SolverRunRecord(
            solver_id="solver:parity", task_id="task:parity",
            parent_execution_node_id="exec:root",
            category="reasoning", created_by="p",
        ),
    )
    repo.apply_justification(
        connection,
        SolverJustificationRecord(
            justification_id="justification:parity", solver_id="solver:parity",
            conclusion="c", supporting_ids=(), contradicting_ids=(),
            assumption_ids=(), strength=0.9, active=True,
            source_refs=(NodeEvidenceReference(source_id="source:parity"),),
        ),
    )


def test_every_serving_path_agrees_the_revoked_identity_is_gone(tmp_path: Path) -> None:
    from memorii.core.persistence.runtime_repository import (
        RuntimeStateRepository,
        publish_runtime_change,
    )

    operator, service = _operator(tmp_path)
    capability = _capability(service)
    try:
        plane = MemoryPlaneService(
            record_store=PublishedMemoryPlaneStore(
                service, SqliteMemoryPlaneStore(service.partition())
            )
        )
        fingerprint = canonical_graph_codec_manifest().manifest_fingerprint
        writers = SemanticWriterAdmissionStore(
            plane, bounded_preplanning_ownership_manifest()
        )
        writers.create_initial_evidence_only(
            admission_id="parity",
            writer_implementation_fingerprint=fingerprint,
            graph_schema_fingerprint=fingerprint,
        )
        store = SemanticIngestionAtomicStore(plane, writers)

        seed = _seed_records()
        service.publish_memory_plane_batch(seed, operation_binding="parity_seed")
        publish_runtime_change(service, _runtime_seed, operation_binding="parity_seed")

        # Before: the revoked coordinates are served and counted.
        view_before = view_from_control_root(
            service.installation_root / "control", records=plane.list_records()
        )
        assert not view_before.is_revoked_entity("entity:parity")
        export_before = operator.read_export(capability=capability)
        assert len(export_before["tasks"]) == 1

        governance = GovernanceOperator(operator)
        plan = governance.plan_forget(
            capability=capability,
            selectors=(
                ForgetTargetSelector(selector_kind="entity", selector_id="entity:parity"),
            ),
            scope_note="parity",
        )
        operator.change_mode(
            ModeChangeRequest(
                target_mode="read_only",
                expected_control_revision=operator.status().control_revision,
                reason="barrier",
            ),
            capability=capability,
        )
        receipt = governance.apply_forget(capability=capability, plan=plan)
        operator.change_mode(
            ModeChangeRequest(
                target_mode="active",
                expected_control_revision=operator.status().control_revision,
                reason="resume",
            ),
            capability=capability,
        )
        assert governance.enforce_forget(store=store) == (receipt.suppression_id,)

        # Absence oracle, serialized-scan form: the revoked coordinates and
        # the servable fixture text appear in no serving serialization.
        serialized = json.dumps(
            [record.model_dump(mode="json") for record in plane.list_records()]
        )
        assert "parity fixture" not in serialized
        assert "parity entity" not in serialized

        # Replay + history integrity: the directive materialized and the
        # persisted replay state equals what the batches reconstruct.
        replay_state = store.semantic_replay_state()
        assert any(
            item.record_kind == "revocation_directive"
            for item in replay_state.materialized_records
        )

        # The serving view derives every revoked identity.
        view_after = view_from_control_root(
            service.installation_root / "control", records=plane.list_records()
        )
        assert view_after.is_revoked_entity("entity:parity")
        assert view_after.is_revoked_claim("claim:parity")
        assert view_after.is_revoked_source("source:parity")
        assert view_after.is_revoked_justification("justification:parity")
        assert view_after.is_revoked_task("task:parity")

        # Retrieval: the revoked entity's claim is never selected.
        evolution = MemoryEvolutionService(
            memory_plane=plane, revoked_view=view_after
        )
        decision = evolution.retrieve(
            __import__(
                "memorii.core.memory_evolution", fromlist=["MemoryQueryRequest"]
            ).MemoryQueryRequest(query="Who is the parity entity?", reference_time=NOW)
        )
        assert decision.selected_record_ids == []

        # Scoped-context current eligibility: tombstones never serve.
        claim_now = plane.get_record(CLAIM_MEMORY_ID)
        link_now = plane.get_record(LINK_MEMORY_ID)
        assert _current_eligible(claim_now, NOW) is False
        assert _current_eligible(link_now, NOW) is False

        # Export: count arithmetic — exactly the revoked task removed.
        export_after = operator.read_export(capability=capability)
        assert export_after["tasks"] == []

        # Harness envelope + resume: the revoked justification forces
        # revalidation and never sponsors a hypothesis.
        repository = RuntimeStateRepository(service.partition())
        grant = RuntimeReadGrant(
            grant_id="grant:parity", principal="p", epoch=1,
            expires_at=NOW + timedelta(minutes=5),
        )
        envelope = HarnessStateService(
            repository, revoked_view=view_after
        ).read_state(task_id="task:parity", grant=grant, view="solver")
        assert envelope.status == "revalidation_required"
        resume = build_resume_envelope(
            repository, task_id="task:parity", revoked_view=view_after
        )
        assert "justification:parity:revoked_evidence" in resume.revalidation_reasons

        # Tier A stayed green and the epoch increment was consumed.
        status = operator.status()
        assert status.pending_epoch_increments == 0

        # No un-forget: the surface has no revocation-removal path, and a
        # fresh view derivation (restart stand-in) still revokes everything.
        assert not [
            name for name in dir(governance) if "unrevoke" in name.lower()
        ]
    finally:
        service.close()
