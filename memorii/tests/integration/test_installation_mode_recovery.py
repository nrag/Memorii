"""Exercise signed local mode effects against verified independent seals."""

from __future__ import annotations

from pathlib import Path

import pytest
from memorii.core.storage_administration import mode_recovery, read_grant_recovery
from memorii.core.storage_administration.mode_recovery import change_mode_with_recovery
from memorii.core.storage_administration.operator import (
    ModeChangeRequest,
    OperatorError,
    StorageAdministrationOperator,
    mint_owner_capability,
)
from memorii.core.storage_administration.read_grant_recovery import ReadGrantRecoveryOwner
from memorii.core.storage_administration.recovery_authority import IndependentRecoveryCustody, RecoveryAuthorityError
from memorii.core.storage_administration.service import (
    MODE_RECOVERY_DIRECTORY,
    MODE_RECOVERY_PENDING,
    MODE_RECOVERY_QUARANTINE,
    InstallationQuarantinedError,
    StorageAdministrationService,
)


def test_mode_custody_fences_pending_activation_and_retries_exact_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "installation"
    location = tmp_path / "independent"
    location.mkdir(mode=0o700)
    key = b"k" * 32
    with StorageAdministrationService(root) as service:
        service.initialize()
        cap = mint_owner_capability(service, "owner:mode-recovery")
        operator = StorageAdministrationOperator(service)
        operator.change_mode(ModeChangeRequest(
            expected_control_revision=service._control_state().control_revision, target_mode="read_only",
            reason="maintenance setup",
        ), capability=cap)
        public_key = service._signing.public_key_bytes(service._signer_key_id)
        custody = IndependentRecoveryCustody(
            location, custody_id="test-mode-custody", installation_id=service._control_state().installation_id,
            repository_id=service._repository_id(), trusted_public_keys={service._signer_key_id: public_key},
        )
        owner = ReadGrantRecoveryOwner(service, custody=custody, public_key=public_key, recovery_key=key)
        original = owner.register(capability=cap)
        request = ModeChangeRequest(
            expected_control_revision=service._control_state().control_revision, target_mode="active",
            reason="enter active under read grant and mode custody",
        )
        with pytest.raises(OperatorError, match="require independent custody"):
            operator.change_mode(request, capability=cap)
        partition = service.partition()
        unavailable = (location / "head.json").rename(location / "unavailable")
        try:
            with pytest.raises(RecoveryAuthorityError, match="could not be read"):
                change_mode_with_recovery(owner, request, operation_id="activate", capability=cap)
            assert service._control_state().mode == "read_only"
        finally:
            unavailable.rename(location / "head.json")

        def cut_export(*_args: object, **_kwargs: object) -> None:
            raise OSError("cut after local mode effect")

        with monkeypatch.context() as patch:
            patch.setattr(read_grant_recovery, "seal_recovery_bundle", cut_export)
            with pytest.raises(OSError, match="after local mode effect"):
                change_mode_with_recovery(owner, request, operation_id="activate", capability=cap)
        pending = custody.current()
        assert pending.payload.state == "pending"
        assert pending.payload.predecessor == original.digest()
        assert service._control_state().mode == "active"
        assert service._control_state().quarantined_reason == MODE_RECOVERY_QUARANTINE
        assert operator.status().readiness == "pending_recovery"
        assert operator.status().effective_mode == "offline"
        with pytest.raises(InstallationQuarantinedError, match="pending independent seal"), partition.transaction(write=False):
            pytest.fail("a previously opened partition retained access")
        guard = root / "control" / MODE_RECOVERY_DIRECTORY / MODE_RECOVERY_PENDING
        guard.unlink()
        with pytest.raises(InstallationQuarantinedError, match="pending independent seal"):
            service.partition()
        moved = guard.parent.rename(tmp_path / "interrupted-local-mode-records")
        try:
            with pytest.raises(InstallationQuarantinedError, match="pending independent seal"), partition.transaction(write=False):
                pytest.fail("persisted quarantine lost effect with missing local records")
        finally:
            moved.rename(guard.parent)

    with StorageAdministrationService(root) as service:
        owner = ReadGrantRecoveryOwner(service, custody=custody, public_key=public_key, recovery_key=key)
        operator = StorageAdministrationOperator(service)
        with pytest.raises(RecoveryAuthorityError, match="pending mode plan"):
            change_mode_with_recovery(owner, request, operation_id="other", capability=cap)
        with pytest.raises(OperatorError, match="require independent custody"):
            operator.change_mode(request, capability=cap)

        def cut_activation(*_args: object, **_kwargs: object) -> None:
            raise OSError("cut after independent mode seal")

        with monkeypatch.context() as patch:
            patch.setattr(mode_recovery, "_activate", cut_activation)
            with pytest.raises(OSError, match="after independent mode seal"):
                change_mode_with_recovery(owner, request, operation_id="activate", capability=cap)
        sealed = custody.current_sealed()
        assert operator.status().readiness == "pending_recovery"
        assert sealed.payload.state == "sealed"
        assert sealed.payload.pending_digest == pending.digest()

    with StorageAdministrationService(root) as service:
        owner = ReadGrantRecoveryOwner(service, custody=custody, public_key=public_key, recovery_key=key)
        operator = StorageAdministrationOperator(service)
        for _ in range(2):
            assert change_mode_with_recovery(owner, request, operation_id="activate", capability=cap) == sealed
        assert not guard.exists()
        assert service._require_operational().mode == "active"
        assert operator.status().readiness == "ready"
        journal = service._control.read_journal()
        assert [entry.operation for entry in journal[-2:]] == ["mode_recovery_applied", "mode_recovery_activated"]
        assert journal[-1].entry_digest == sealed.payload.anchor.journal_tip
        assert service._control_state().control_revision == request.expected_control_revision + 2
        to_read_only = ModeChangeRequest(
            expected_control_revision=service._control_state().control_revision, target_mode="read_only",
            reason="return to maintenance",
        )
        change_mode_with_recovery(owner, to_read_only, operation_id="read-only", capability=cap)
        assert service._require_operational().mode == "read_only"
        (root / "control" / MODE_RECOVERY_DIRECTORY).rename(tmp_path / "removed-local-mode-records")
        with pytest.raises(OperatorError, match="require independent custody"):
            operator.change_mode(to_read_only, capability=cap)
