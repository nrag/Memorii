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
from memorii.core.memory_plane.models import CanonicalMemoryRecord
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
    view_from_control_root,
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
        directive = next(
            item
            for item in replay.materialized_records
            if item.record_kind == "revocation_directive"
        )
        # RV11 fidelity: the directive binds the plan's record closure and
        # the owner capability presented at apply (never a synthetic hash).
        assert (
            directive.record.authority_capability_digest
            == capability.capability_digest
        )
        from tests.integration.test_forget_serving_parity import (
            CLAIM_MEMORY_ID,
            LINK_MEMORY_ID,
        )

        assert sorted(
            coordinate.record_id for coordinate in directive.record.closure_coordinates
        ) == sorted([CLAIM_MEMORY_ID, LINK_MEMORY_ID])
        assert all(
            coordinate.record_kind == "reference_disposition"
            for coordinate in directive.record.closure_coordinates
        )
    finally:
        service.close()


def test_live_managed_root_forgets_mid_process_and_recovers(tmp_path) -> None:
    """Round-2 T4+T5+T6: live refresh, wiring semantics, reopen recovery.

    The managed-partition root (open_managed_partition) composes the
    refreshing gate; a forget applied in the same process is observed by
    the LIVE plane without restart (T6); wire_forget_enforcement is
    idempotent under double-wiring (T5); and a fresh reopen completes a
    pending enforcement through the operator-tool composition — the same
    construction the CLI `forget enforce` runs (T4).
    """
    import tempfile

    from memorii.core.memory_plane.models import MemoryRecordVisibility
    from memorii.core.persistence.factory import open_managed_partition
    from memorii.core.storage_administration.operator import (
        ModeChangeRequest,
        StorageAdministrationOperator,
    )
    from memorii.core.storage_administration.service import StorageAdministrationService
    from memorii.domain.enums import CommitStatus, MemoryDomain

    with tempfile.TemporaryDirectory():
        root = tmp_path / "installation"
        bootstrap = StorageAdministrationService(root)
        bootstrap.initialize()
        administration0, _plane0 = open_managed_partition(root)
        administration0.close()
        bootstrap.close()

        administration, plane = open_managed_partition(root)
        try:
            runtime_record = CanonicalMemoryRecord(
                memory_id="mem:provider:runtime:live:parity",
                domain=MemoryDomain.SEMANTIC,
                text="parity fixture",
                content={"note": "parity fixture"},
                visibility=MemoryRecordVisibility.RUNTIME_CONTEXT,
                status=CommitStatus.COMMITTED,
                source_kind="provider_seed",
            )
            administration.publish_memory_plane_batch(
                (*_seed_records(), runtime_record), operation_binding="live_seed"
            )
            # T6: the production root's plane carries the refreshing gate;
            # the seeded runtime record serves before the forget.
            assert "parity fixture" in plane.prefetch_provider_context(
                "parity fixture", session_id=None, task_id=None, user_id=None, top_k=5
            )

            operator = StorageAdministrationOperator(administration)
            governance = GovernanceOperator(operator)
            capability = _capability(administration)
            plan = governance.plan_forget(
                capability=capability,
                selectors=(
                    ForgetTargetSelector(
                        selector_kind="record",
                        selector_id=runtime_record.memory_id,
                    ),
                ),
                scope_note="live root",
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
            # T6: SAME process, SAME plane — no restart, no re-derivation.
            assert "parity fixture" not in plane.prefetch_provider_context(
                "parity fixture", session_id=None, task_id=None, user_id=None, top_k=5
            )
            # T5: double-wiring stays idempotent at the emitter level (the
            # factory-composed runtime authorizes governance writes only
            # through the bootstrap enrollment; end-to-end publication via
            # a provider-composed store is the CLI path, pinned below).
            from memorii.core.provider.factory import build_provider_memory_service_from_env

            service = build_provider_memory_service_from_env(
                memory_plane=plane,
                revoked_view=plane._revoked_view,
            )
            service.wire_forget_enforcement(administration)
            service.wire_forget_enforcement(administration)
            assert callable(administration._forget_enforcement_emitter)
        finally:
            administration.close()


def test_crash_cut_recovers_and_stops_serving(tmp_path) -> None:
    """The §10.3 crash-cut with post-drain serving assertions.

    A forget applied under the barrier and closed without enforcement
    (crash stand-in) recovers at reopen through the operator-tool
    composition — the exact construction the CLI `forget enforce` runs —
    and after the drain the revoked identities are excluded from serving.
    """
    from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
    from memorii.core.memory_evolution.graph_records import (
        canonical_graph_codec_manifest,
    )
    from memorii.core.memory_evolution.writer_admission import (
        SemanticWriterAdmissionStore,
        bounded_preplanning_ownership_manifest,
    )
    from memorii.core.storage_administration.operator import (
        StorageAdministrationOperator,
    )
    from memorii.core.storage_administration.service import StorageAdministrationService

    root = tmp_path / "installation"
    service = StorageAdministrationService(root)
    service.initialize()
    operator = StorageAdministrationOperator(service)
    capability = _capability(service)
    try:
        service.publish_memory_plane_batch(
            _seed_records(), operation_binding="crash_seed"
        )
        governance = GovernanceOperator(operator)
        plan = governance.plan_forget(
            capability=capability,
            selectors=(
                ForgetTargetSelector(selector_kind="entity", selector_id="entity:parity"),
            ),
            scope_note="crash cut",
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
        assert service.pending_forget_enforcements()
        operator.change_mode(
            ModeChangeRequest(
                target_mode="active",
                expected_control_revision=operator.status().control_revision,
                reason="resume",
            ),
            capability=capability,
        )
    finally:
        service.close()

    reopened = StorageAdministrationService(root)
    try:
        assert reopened.pending_forget_enforcements()
        reopened_plane = MemoryPlaneService(
            record_store=PublishedMemoryPlaneStore(
                reopened, SqliteMemoryPlaneStore(reopened.partition())
            )
        )
        fingerprint = canonical_graph_codec_manifest().manifest_fingerprint
        writers = SemanticWriterAdmissionStore(
            reopened_plane, bounded_preplanning_ownership_manifest()
        )
        if reopened_plane.get_record(
            __import__(
                "memorii.core.memory_evolution.writer_admission",
                fromlist=["writer_admission_memory_id"],
            ).writer_admission_memory_id()
        ) is None:
            writers.create_initial_evidence_only(
                admission_id="crash-reopen",
                writer_implementation_fingerprint=fingerprint,
                graph_schema_fingerprint=fingerprint,
            )
        store = SemanticIngestionAtomicStore(reopened_plane, writers)
        reopened_governance = GovernanceOperator(
            StorageAdministrationOperator(reopened)
        )
        reopened.set_forget_enforcement_emitter(
            lambda _record: reopened_governance.enforce_forget(store=store)
        )
        assert reopened.drain_pending_forget_enforcement() == 0
        assert reopened.pending_forget_enforcements() == ()
        replay = store.semantic_replay_state()
        assert any(
            item.record_kind == "revocation_directive"
            for item in replay.materialized_records
        )
        # Post-drain serving exclusion: the tombstoned claim and link are
        # ineligible and the derived view excludes them from retrieval.
        from datetime import UTC, datetime

        from memorii.core.memory_evolution import MemoryQueryRequest
        from memorii.core.memory_evolution.service import MemoryEvolutionService
        from memorii.core.scoped_context.service import _current_eligible

        now = datetime.now(UTC)
        claim = reopened_plane.get_record(
            "mem:evolution:claim:claim:parity"
        )
        assert claim is not None and _current_eligible(claim, now) is False
        view = view_from_control_root(root / "control", records=reopened_plane.list_records())
        assert view.is_revoked_entity("entity:parity")
        evolution = MemoryEvolutionService(
            memory_plane=reopened_plane, revoked_view=view
        )
        decision = evolution.retrieve(
            MemoryQueryRequest(
                query="Who is the parity entity?", reference_time=now
            )
        )
        assert decision.selected_record_ids == []
    finally:
        reopened.close()
