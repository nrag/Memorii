"""Owner-forensic retained lineage (R16) and prefetch canonical-channel exclusion.

Two deferred serving-path gates from the forgetting design's enforcement
matrix on the shared parity fixture: the governance-operator forensic
surface serves the complete retained lineage for named coordinates and
refuses without the owner capability, and the canonical prefetch channel
assembles with revoked records excluded when the revoked-identity view is
injected.
"""

from pathlib import Path

from tests.integration.test_forget_serving_parity import (
    CLAIM_MEMORY_ID,
    _seed_records,
)
from tests.unit.core.test_storage_administration_operator import (
    _capability,
    _operator,
)

from memorii.core.memory_plane.models import (
    CanonicalMemoryRecord,
    MemoryRecordVisibility,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore
from memorii.core.persistence.factory import PublishedMemoryPlaneStore
from memorii.core.storage_administration.operator import (
    OperatorError,
    OwnerCapability,
)
from memorii.core.storage_administration.operator_governance import (
    ForgetTargetSelector,
    GovernanceOperator,
)
from memorii.core.storage_administration.revoked_identity_view import (
    view_from_control_root,
)
from memorii.domain.enums import MemoryDomain


def _forget_entity(operator, governance, capability) -> None:
    from memorii.core.storage_administration.operator import ModeChangeRequest

    plan = governance.plan_forget(
        capability=capability,
        selectors=(
            ForgetTargetSelector(selector_kind="entity", selector_id="entity:parity"),
        ),
        scope_note="forensic",
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
    assert receipt.historical_bytes_retained is True


def test_owner_forensic_surface_serves_retained_lineage_for_named_coordinates(
    tmp_path: Path,
) -> None:
    operator, service = _operator(tmp_path)
    capability = _capability(service)
    try:
        plane = MemoryPlaneService(
            record_store=PublishedMemoryPlaneStore(
                service, SqliteMemoryPlaneStore(service.partition())
            )
        )
        service.publish_memory_plane_batch(
            _seed_records(), operation_binding="forensic_seed"
        )

        governance = GovernanceOperator(operator)
        _forget_entity(operator, governance, capability)

        lineage = governance.read_retained_lineage(
            capability=capability,
            coordinates=("entity|entity:parity",),
        )
        assert lineage["coordinates"] == ("entity|entity:parity",)
        claim_entries = [
            entry
            for entry in lineage["entries"]
            if entry.memory_id == CLAIM_MEMORY_ID
        ]
        # The retained history still carries the original committed bytes.
        assert claim_entries, "forensic lineage must retain the claim history"
        assert all(entry.revoked is True for entry in claim_entries)
        assert all(
            entry.record["content"]["claim_state"]["claim_key"][
                "subject_entity_id"
            ]
            == "entity:parity"
            for entry in claim_entries
        )

        # Refuses without a valid capability.
        try:
            governance.read_retained_lineage(
                capability=OwnerCapability(
                    owner_principal="forged",
                    capability_digest="0" * 64,
                ),
                coordinates=("entity|entity:parity",),
            )
        except OperatorError:
            pass
        else:
            raise AssertionError("forensic lineage must refuse without capability")

        # Refuses empty coordinate lists rather than serving everything.
        try:
            governance.read_retained_lineage(
                capability=capability, coordinates=()
            )
        except OperatorError:
            pass
        else:
            raise AssertionError("forensic lineage requires named coordinates")
    finally:
        service.close()


def test_prefetch_canonical_channel_excludes_revoked_records(
    tmp_path: Path,
) -> None:
    operator, service = _operator(tmp_path)
    capability = _capability(service)
    try:
        store = PublishedMemoryPlaneStore(
            service, SqliteMemoryPlaneStore(service.partition())
        )
        plane = MemoryPlaneService(record_store=store)
        from memorii.domain.enums import CommitStatus

        runtime_claim = CanonicalMemoryRecord(
            memory_id="mem:provider:runtime:parity",
            domain=MemoryDomain.SEMANTIC,
            text="parity fixture",
            content={"note": "parity fixture"},
            visibility=MemoryRecordVisibility.RUNTIME_CONTEXT,
            status=CommitStatus.COMMITTED,
            source_kind="provider_seed",
        )
        service.publish_memory_plane_batch(
            (runtime_claim,), operation_binding="prefetch_seed"
        )
        kwargs = dict(session_id=None, task_id=None, user_id=None, top_k=5)

        before = plane.prefetch_provider_context("parity fixture", **kwargs)
        assert "parity fixture" in before

        governance = GovernanceOperator(operator)
        from memorii.core.storage_administration.operator import ModeChangeRequest

        plan = governance.plan_forget(
            capability=capability,
            selectors=(
                ForgetTargetSelector(
                    selector_kind="record",
                    selector_id="mem:provider:runtime:parity",
                ),
            ),
            scope_note="prefetch channel",
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
        view = view_from_control_root(
            service.installation_root / "control", records=plane.list_records()
        )
        assert view.is_revoked_record("mem:provider:runtime:parity")

        # Restart stand-in: a reopened plane with the derived view injected
        # never assembles the revoked record into the canonical channel.
        reopened = MemoryPlaneService(record_store=store, revoked_view=view)
        after = reopened.prefetch_provider_context("parity fixture", **kwargs)
        assert "parity fixture" not in after
    finally:
        service.close()
