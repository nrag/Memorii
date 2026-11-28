"""Prove exact suppression denial and epoch reconciliation across maintenance crash cuts."""

from __future__ import annotations

from pathlib import Path

import pytest
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.storage_administration.operator import (
    ModeChangeRequest,
    OperatorError,
    StorageAdministrationOperator,
    mint_owner_capability,
)
from memorii.core.storage_administration.operator_governance import (
    ForgetTargetSelector,
    GovernanceOperator,
    RetentionPlan,
)
from memorii.core.storage_administration.read_grant_recovery import ReadGrantRecoveryOwner
from memorii.core.storage_administration.recovery_authority import IndependentRecoveryCustody, RecoveryAuthorityError
from memorii.core.storage_administration.revoked_identity_view import RefreshingRevokedIdentityView
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.core.storage_administration.suppression_journal import read_suppression_records
from memorii.core.storage_administration.suppression_recovery import apply_suppression_with_recovery
from memorii.domain.enums import CommitStatus, MemoryDomain


@pytest.mark.parametrize("cut", ["file_only", "local_committed"])
def test_exact_suppression_finishes_forward_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cut: str) -> None:
    root = tmp_path / "installation"
    custody_dir = tmp_path / "custody"
    custody_dir.mkdir(mode=0o700)
    with StorageAdministrationService(root) as service:
        service.initialize()
        service.publish_memory_plane_batch(
            (
                CanonicalMemoryRecord(
                    memory_id="memory:reviewed-forget",
                    text="private test content",
                    domain=MemoryDomain.TRANSCRIPT,
                    status=CommitStatus.COMMITTED,
                ),
            )
        )
        capability = mint_owner_capability(service, "owner")
        operator = StorageAdministrationOperator(service)
        operator.change_mode(
            ModeChangeRequest(
                target_mode="read_only",
                expected_control_revision=service._control_state().control_revision,
                reason="maintenance",
            ),
            capability=capability,
        )
        governance = GovernanceOperator(operator)
        request = governance.plan_forget(
            capability=capability,
            scope_note="reviewed selector",
            selectors=(ForgetTargetSelector(selector_kind="record", selector_id="memory:reviewed-forget"),),
        )
        signer = service._signer_key_id
        public = service._signing.public_key_bytes(signer)
        custody = IndependentRecoveryCustody(
            custody_dir,
            custody_id="suppression-custody",
            installation_id=service._control_state().installation_id,
            repository_id=service._repository_id(),
            trusted_public_keys={signer: public},
        )
        owner = ReadGrantRecoveryOwner(service, custody=custody, public_key=public, recovery_key=b"c" * 32)
        registered = owner.register(capability=capability)
        original = service._control_state()
        with pytest.raises(OperatorError, match="require independent custody"):
            governance.apply_forget(capability=capability, plan=request)
        with pytest.raises(OperatorError, match="require independent custody"):
            governance.apply_retention(capability=capability, plan=RetentionPlan(older_than_days=1))
        head_path = custody_dir / "head.json"
        missing = head_path.rename(custody_dir / "temporarily-unavailable")
        try:
            with pytest.raises(RecoveryAuthorityError, match="could not be read"):
                apply_suppression_with_recovery(owner, request, operation_id="forget", capability=capability)
            assert read_suppression_records(root / "control") == ()
            assert service._control_state() == original
        finally:
            missing.rename(head_path)

        def interrupted(*_args: object, **_kwargs: object) -> None:
            raise OSError("interrupted suppression")

        with monkeypatch.context() as patch:
            if cut == "file_only":
                patch.setattr(service._control, "write_control_state", interrupted)
            else:
                patch.setattr(owner, "_retain_bundle", interrupted)
            with pytest.raises(OSError, match="interrupted suppression"):
                apply_suppression_with_recovery(owner, request, operation_id="forget", capability=capability)
        pending = custody.current()
        assert pending.payload.state == "pending" and pending.payload.predecessor == registered.digest()
        assert pending.payload.operation == "suppression"
        with pytest.raises(RecoveryAuthorityError, match="pending"):
            custody.current_sealed()
        records = read_suppression_records(root / "control")
        assert len(records) == 1
        assert RefreshingRevokedIdentityView(root / "control").is_revoked_record(
            "memory:reviewed-forget",
        )
        expected_increments = original.pending_epoch_increments + (cut == "local_committed")
        assert service._control_state().pending_epoch_increments == expected_increments
        with pytest.raises(OperatorError, match="require independent custody"):
            governance.apply_forget(capability=capability, plan=request)

    with StorageAdministrationService(root) as service:
        owner = ReadGrantRecoveryOwner(service, custody=custody, public_key=public, recovery_key=b"c" * 32)
        with pytest.raises(RecoveryAuthorityError, match="exact pending suppression plan"):
            apply_suppression_with_recovery(owner, request, operation_id="different", capability=capability)
        successor = apply_suppression_with_recovery(owner, request, operation_id="forget", capability=capability)
        assert successor == custody.current_sealed()
        assert successor == apply_suppression_with_recovery(
            owner, request, operation_id="forget", capability=capability
        )
        assert read_suppression_records(root / "control") == records
        assert service._control_state().pending_epoch_increments == original.pending_epoch_increments + 1
        journal = [entry for entry in service._control.read_journal() if entry.operation == "logical_forget_applied"]
        assert len(journal) == 1 and journal[0].revision == records[0].control_journal_position
        assert any(effect.effect_digest == journal[0].entry_digest for effect in pending.payload.participants)
