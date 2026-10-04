"""Composition gates for the revoked-identity serving spine.

Pins the review-round findings RV1/RV2/RV9: the provider factory refuses
to compose without an explicit revoked-identity gate (absence never
silently means "nothing revoked"), the refreshing gate observes journal
writes without a process restart, and the wired enforcement emitter makes
the drain publish pending revocation directives.
"""

from pathlib import Path

from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
from memorii.core.memory_evolution.graph_records import canonical_graph_codec_manifest
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore
from memorii.core.persistence.factory import PublishedMemoryPlaneStore
from memorii.core.storage_administration.operator import ModeChangeRequest
from memorii.core.storage_administration.operator_governance import (
    ForgetTargetSelector,
    GovernanceOperator,
)
from memorii.core.storage_administration.revoked_identity_view import (
    RefreshingRevokedIdentityView,
    empty_revoked_view,
)
from tests.integration.test_forget_serving_parity import _seed_records
from tests.unit.core.test_storage_administration_operator import (
    _capability,
    _operator,
)


def test_provider_factory_refuses_composition_without_a_gate() -> None:
    from memorii.core.provider.factory import build_provider_memory_service_from_env

    try:
        build_provider_memory_service_from_env(memory_plane=MemoryPlaneService())
    except TypeError as exc:
        assert "revoked_view" in str(exc)
    else:
        raise AssertionError(
            "the factory must fail closed when no revoked-identity gate is supplied"
        )
    # The explicit empty view is the valid statement for ephemeral planes.
    service = build_provider_memory_service_from_env(
        memory_plane=MemoryPlaneService(), revoked_view=empty_revoked_view()
    )
    assert service is not None


def test_refreshing_gate_observes_journal_writes_without_restart(
    tmp_path: Path,
) -> None:
    operator, service = _operator(tmp_path)
    capability = _capability(service)
    try:
        view = RefreshingRevokedIdentityView(service.installation_root / "control")
        assert view.is_revoked_entity("entity:parity") is False

        service.publish_memory_plane_batch(
            _seed_records(), operation_binding="refresh_seed"
        )
        governance = GovernanceOperator(operator)
        plan = governance.plan_forget(
            capability=capability,
            selectors=(
                ForgetTargetSelector(selector_kind="entity", selector_id="entity:parity"),
            ),
            scope_note="refresh",
        )
        operator.change_mode(
            ModeChangeRequest(
                target_mode="read_only",
                expected_control_revision=operator.status().control_revision,
                reason="barrier",
            ),
            capability=capability,
        )
        governance.apply_forget(capability=capability, plan=plan)
        operator.change_mode(
            ModeChangeRequest(
                target_mode="active",
                expected_control_revision=operator.status().control_revision,
                reason="resume",
            ),
            capability=capability,
        )

        # Same process, same gate instance: the journal write is observed.
        assert view.is_revoked_entity("entity:parity") is True
        assert view.is_revoked_claim("claim:parity") is True
    finally:
        service.close()


def test_wired_emitter_drains_pending_enforcement(tmp_path: Path) -> None:
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
            admission_id="drain",
            writer_implementation_fingerprint=fingerprint,
            graph_schema_fingerprint=fingerprint,
        )
        store = SemanticIngestionAtomicStore(plane, writers)
        service.publish_memory_plane_batch(
            _seed_records(), operation_binding="drain_seed"
        )

        governance = GovernanceOperator(operator)
        plan = governance.plan_forget(
            capability=capability,
            selectors=(
                ForgetTargetSelector(selector_kind="entity", selector_id="entity:parity"),
            ),
            scope_note="drain",
        )
        operator.change_mode(
            ModeChangeRequest(
                target_mode="read_only",
                expected_control_revision=operator.status().control_revision,
                reason="barrier",
            ),
            capability=capability,
        )
        governance.apply_forget(capability=capability, plan=plan)

        # Before wiring: leaving the barrier drains nothing (inert emitter).
        assert service.drain_pending_forget_enforcement() == 1

        # The production wiring: the emitter runs the governance entry
        # against the composed store; the mode-resume drain retries per
        # entry, so the directive publishes as the barrier lifts.
        service.set_forget_enforcement_emitter(
            lambda _record: governance.enforce_forget(store=store)
        )
        operator.change_mode(
            ModeChangeRequest(
                target_mode="active",
                expected_control_revision=operator.status().control_revision,
                reason="resume",
            ),
            capability=capability,
        )
        assert service.drain_pending_forget_enforcement() == 0
        assert service.pending_forget_enforcements() == ()
        replay = store.semantic_replay_state()
        assert any(
            item.record_kind == "revocation_directive"
            for item in replay.materialized_records
        )
    finally:
        service.close()
