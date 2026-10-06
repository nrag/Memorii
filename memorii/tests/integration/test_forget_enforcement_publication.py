"""The governance enforcement publication appends the directive end to end."""

import json
from datetime import UTC, datetime
from pathlib import Path

from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore  # noqa: E402
from memorii.core.memory_evolution.graph_records import (  # noqa: E402
    canonical_graph_codec_manifest,
)
from memorii.core.memory_evolution.writer_admission import (  # noqa: E402
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord  # noqa: E402
from memorii.core.memory_plane.service import MemoryPlaneService  # noqa: E402
from memorii.core.persistence.factory import (  # noqa: E402
    PublishedMemoryPlaneStore,
)
from memorii.core.scoped_context.service import _current_eligible  # noqa: E402
from memorii.core.storage_administration.operator import (  # noqa: E402
    ModeChangeRequest,
)
from memorii.core.storage_administration.operator_governance import (  # noqa: E402
    ForgetTargetSelector,
    GovernanceOperator,
)
from memorii.core.storage_administration.revoked_identity_view import (  # noqa: E402
    view_from_control_root,
)
from memorii.domain.enums import CommitStatus, MemoryDomain  # noqa: E402
from tests.unit.core.test_storage_administration_operator import (  # noqa: E402
    _capability,
    _operator,
)


def _claim_record() -> CanonicalMemoryRecord:
    truth = {
        "assertion_mode": "world_assertion", "epistemic_status": "asserted",
        "polarity": "positive", "modality": "assertion",
    }
    claim = {
        "claim_id": "claim:enforce", "claim_key": {
            "subject_entity_id": "entity:enforce", "predicate_id": "owns",
            "scope": {}, "qualifier_key": "default", **truth,
            "belief_holder_entity_id": None,
        },
        "object_value": "enforcement fixture",
        "lifecycle_state": "active", "source_claim_id": "source:enforce",
        "confidence": {"extraction": 0.9, "evidence": 0.8, "source_trust": 0.7,
                       "agreement": 0.0, "contradiction": 0.0, "calibrated": 0.9},
        "semantic_context": {"attribution_source_id": "source:enforce", **truth},
        "validation_results": [], "evidence_spans": [
            {"source_id": "source:enforce", "quote": "fixture",
             "source_type": "user", "timestamp": "2026-10-03T00:00:00Z"},
        ],
        "subject_link_id": "link:enforce", "object_link_id": None,
    }
    link = {
        "link_id": "link:enforce", "mention_text": "enforced entity",
        "canonical_entity_id": "entity:enforce", "normalized_name": "enforced entity",
        "entity_type": "unknown", "aliases": [], "observed_names": [],
        "evidence_spans": [], "confidence": 0.9, "scope": {},
        "lifecycle_state": "active",
    }
    return (
        CanonicalMemoryRecord(
            memory_id="mem:evolution:claim:claim:enforce",
            domain=MemoryDomain.SEMANTIC, text="enforcement fixture",
            content={"memory_evolution_kind": "claim_state", "claim_state": claim},
            status=CommitStatus.COMMITTED, source_kind="memory_evolution",
        ),
        CanonicalMemoryRecord(
            memory_id="mem:evolution:link:link:enforce",
            domain=MemoryDomain.SEMANTIC, text="enforced entity",
            content={"memory_evolution_kind": "entity_link", "entity_link": link},
            status=CommitStatus.COMMITTED, source_kind="memory_evolution",
        ),
    )


def test_forget_enforcement_publication_appends_the_directive(tmp_path: Path) -> None:
    operator, service = _operator(tmp_path)
    capability = _capability(service)
    try:
        inner_view = MemoryPlaneService(
            record_store=PublishedMemoryPlaneStore(
                service, __import__(
                    "memorii.core.memory_plane.sqlite_store", fromlist=["SqliteMemoryPlaneStore"]
                ).SqliteMemoryPlaneStore(service.partition()),
            )
        )
        manifest_fingerprint = canonical_graph_codec_manifest().manifest_fingerprint
        writers = SemanticWriterAdmissionStore(
            inner_view, bounded_preplanning_ownership_manifest()
        )
        writers.create_initial_evidence_only(
            admission_id="governance-enforcement",
            writer_implementation_fingerprint=manifest_fingerprint,
            graph_schema_fingerprint=manifest_fingerprint,
        )
        store = SemanticIngestionAtomicStore(inner_view, writers)

        seed = _claim_record()
        service.publish_memory_plane_batch(seed, operation_binding="enforce_seed")

        governance = GovernanceOperator(operator)
        plan = governance.plan_forget(
            capability=capability,
            selectors=(
                ForgetTargetSelector(selector_kind="entity", selector_id="entity:enforce"),
            ),
            scope_note="enforcement",
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
        assert service.pending_forget_enforcements()

        operator.change_mode(
            ModeChangeRequest(
                target_mode="active",
                expected_control_revision=operator.status().control_revision,
                reason="resume",
            ),
            capability=capability,
        )

        enforced = governance.enforce_forget(store=store)
        assert enforced == (receipt.suppression_id,)

        # The directive materialized in the replay authority: persisted
        # state equals genesis reconstruction including the new record.
        replay_state = store.semantic_replay_state()
        kinds = {item.record_kind for item in replay_state.materialized_records}
        assert "revocation_directive" in kinds

        # The enforcement is present: the drain is quiescent.
        assert service.pending_forget_enforcements() == ()
        assert governance.enforce_forget(store=store) == ()

        # Tombstones landed: the closure records are content-free revoked
        # versions and fail scoped-context current eligibility.
        claim_now = inner_view.get_record("mem:evolution:claim:claim:enforce")
        link_now = inner_view.get_record("mem:evolution:link:link:enforce")
        assert claim_now.content["claim_state"]["lifecycle_state"] == "revoked"
        assert link_now.content["entity_link"]["lifecycle_state"] == "revoked"
        assert "enforcement fixture" not in json.dumps(claim_now.content)
        assert _current_eligible(claim_now, datetime.now(UTC)) is False
        assert _current_eligible(link_now, datetime.now(UTC)) is False

        # The serving view derives the revoked identities from the journal
        # plus the directive index record written by the publication.
        view = view_from_control_root(
            service.installation_root / "control",
            records=inner_view.list_records(),
        )
        assert view.is_revoked_entity("entity:enforce")
        assert view.is_revoked_claim("claim:enforce")
        assert view.is_revoked_source("source:enforce")

        # Tier A stayed green and the pending epoch increment this
        # publication rode was consumed atomically.
        status = operator.status()
        assert status.pending_epoch_increments == 0
        assert status.eligibility_epoch >= 1
    finally:
        service.close()
