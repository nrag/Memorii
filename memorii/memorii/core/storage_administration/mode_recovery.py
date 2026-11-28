"""Independently sealed mode changes for an enrolled control recovery owner."""

from __future__ import annotations

import hashlib
import tempfile
from contextlib import ExitStack
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from memorii.core.persistence.contracts import (
    InstallationControlJournalEntry,
    InstallationControlState,
    canonical_json_digest,
)
from memorii.core.storage_administration.operator import (
    InstallationMode,
    ModeChangeRequest,
    OwnerCapability,
    require_owner_capability,
)
from memorii.core.storage_administration.operator_backup import backup_lifetime_guard, fsync_directory
from memorii.core.storage_administration.read_grant_recovery import (
    ReadGrantRecoveryOwner,
    RecoveryDigest,
    RecoveryIdentity,
    RecoveryWatermark,
)
from memorii.core.storage_administration.recovery_authority import (
    InstallationRecoveryAnchor,
    InstallationRecoveryHead,
    PendingRecoveryHead,
    RecoveryAuthorityError,
    RecoveryParticipantExpectation,
    SealedRecoveryHead,
    decode_recovery_json,
)
from memorii.core.storage_administration.service import (
    MODE_RECOVERY_DIRECTORY,
    MODE_RECOVERY_PENDING,
    MODE_RECOVERY_QUARANTINE,
)
from memorii.stores.sqlite.private_storage import ensure_private_directory, read_private_file, write_private_file

_STORAGE_OWNER = "storage-owner"
_PLAN_BYTES = 64 * 1024


class _ModeRecoveryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: RecoveryIdentity
    predecessor: RecoveryDigest
    request_digest: RecoveryDigest
    before_authority_digest: RecoveryDigest
    before: InstallationControlState
    target: InstallationMode
    applied: InstallationControlJournalEntry
    activation: InstallationControlJournalEntry

    def digest(self) -> str:
        return canonical_json_digest(self.model_dump(mode="json"))

    def applied_state(self) -> InstallationControlState:
        return self.before.model_copy(update={
            "mode": self.target, "control_revision": self.before.control_revision + 1,
            "quarantined_reason": MODE_RECOVERY_QUARANTINE,
        })

    def ready_state(self) -> InstallationControlState:
        return self.applied_state().model_copy(update={
            "control_revision": self.before.control_revision + 2, "quarantined_reason": None,
        })

    def effect(self) -> RecoveryParticipantExpectation:
        return RecoveryParticipantExpectation(
            participant_id=_STORAGE_OWNER, revision=self.before.control_revision,
            pre_state_digest=self.before_authority_digest, effect_digest=self.activation.entry_digest,
        )


def _mode_watermark(owner: ReadGrantRecoveryOwner, capability: OwnerCapability) -> RecoveryWatermark:
    service = owner._service
    require_owner_capability(service, capability)
    state = service._control_state()
    repository_id = service._repository_id()
    publication = service._control.read_publication_state(repository_id)
    change = service._control.read_generation_change(repository_id)
    if (
        state.quarantined_reason not in (None, MODE_RECOVERY_QUARANTINE) or publication is None
        or service._control.read_pending_intent(repository_id) is not None
        or (change is not None and change.phase == "prepared")
    ):
        raise RecoveryAuthorityError("needs_reconciliation: mode recovery requires settled publication authority")
    return RecoveryWatermark(state, publication, service._control.next_journal_position(), owner._current_suppressions())


def _make_plan(
    owner: ReadGrantRecoveryOwner, watermark: RecoveryWatermark, request: ModeChangeRequest,
    operation_id: str, predecessor: str,
) -> _ModeRecoveryPlan:
    state = watermark.state
    if state.control_revision != request.expected_control_revision or state.quarantined_reason is not None:
        raise RecoveryAuthorityError("conflict: mode change control revision or readiness changed")
    if state.mode == "bypass" and request.target_mode == "read_only":
        raise RecoveryAuthorityError("invalid_request: bypass returns to active only")
    request_digest = canonical_json_digest(request.model_dump(mode="json"))
    applied = owner._service._journal_entry(
        operation="mode_recovery_applied", position=watermark.position,
        before_digest=watermark.digest(), after_digest=canonical_json_digest({
            "operation_id": operation_id, "predecessor": predecessor, "request": request_digest,
        }),
    )
    ready = state.model_copy(update={"mode": request.target_mode, "control_revision": state.control_revision + 2})
    activation = owner._service._journal_entry(
        operation="mode_recovery_activated", position=(applied.revision + 1, applied.entry_digest),
        before_digest=applied.entry_digest, after_digest=canonical_json_digest(ready.model_dump(mode="json")),
    )
    return _ModeRecoveryPlan(
        operation_id=operation_id, predecessor=predecessor, before_authority_digest=watermark.digest(),
        request_digest=request_digest, before=state, target=request.target_mode, applied=applied, activation=activation,
    )


def _ensure_pending_guard(path: Path, plan: _ModeRecoveryPlan) -> None:
    expected = plan.digest().encode("ascii")
    try:
        write_private_file(path, expected, exclusive=True)
    except FileExistsError:
        if read_private_file(path, limit=65) != expected:
            raise RecoveryAuthorityError("conflict: local mode transition guard selects a different operation") from None


def _ready(watermark: RecoveryWatermark, plan: _ModeRecoveryPlan) -> RecoveryWatermark:
    return watermark._replace(
        state=plan.ready_state(), position=(plan.activation.revision + 1, plan.activation.entry_digest),
    )


def _activate(
    owner: ReadGrantRecoveryOwner, watermark: RecoveryWatermark, plan: _ModeRecoveryPlan, path: Path,
    anchor: InstallationRecoveryAnchor,
) -> None:
    ready = _ready(watermark, plan)
    if (
        anchor.publication_digest != ready.publication.payload_digest()
        or anchor.control_revision != ready.state.control_revision
        or anchor.eligibility_epoch != ready.state.eligibility_epoch
        or (anchor.journal_ordinal + 1, anchor.journal_tip) != ready.position
    ):
        raise RecoveryAuthorityError("integrity_error: independent seal does not match exact mode activation")
    pending = path.exists() or path.is_symlink()
    if pending and read_private_file(path, limit=65) != plan.digest().encode("ascii"):
        raise RecoveryAuthorityError("conflict: local mode transition guard changed")
    if watermark != ready:
        if watermark.state != plan.applied_state() or watermark.position != (plan.activation.revision, plan.applied.entry_digest):
            raise RecoveryAuthorityError("needs_reconciliation: local mode effect differs from its sealed activation")
        owner._service._control.write_control_state(ready.state, plan.activation)
    if pending:
        path.unlink()
        fsync_directory(path.parent)


def change_mode_with_recovery(
    owner: ReadGrantRecoveryOwner, request: ModeChangeRequest, *, operation_id: str, capability: OwnerCapability,
) -> InstallationRecoveryHead:
    """Apply one exact mode effect or finish it from an independently retained head."""
    sealed, leaving_barrier = _apply_mode_recovery(owner, request, operation_id=operation_id, capability=capability)
    if leaving_barrier:
        owner._service.drain_pending_forget_enforcement()
    return sealed


def _apply_mode_recovery(
    owner: ReadGrantRecoveryOwner, request: ModeChangeRequest, *, operation_id: str, capability: OwnerCapability,
) -> tuple[InstallationRecoveryHead, bool]:
    if not 0 < len(operation_id) <= 512:
        raise ValueError("mode recovery requires a bounded operation id")
    service, custody, registry = owner._service, owner._custody, owner._registry
    require_owner_capability(service, capability)
    operations = owner._control / MODE_RECOVERY_DIRECTORY
    guard = operations / MODE_RECOVERY_PENDING
    plan_path = operations / f"{hashlib.sha256(operation_id.encode()).hexdigest()}.json"
    with (
        backup_lifetime_guard(service, exclusive=False),
        tempfile.TemporaryDirectory(prefix=".mode-recovery-", dir=owner._control) as scratch,
        custody._writer_lease(), ExitStack() as stack,
    ):
        workspace = Path(scratch)
        current = custody._read()
        retained = owner._retained_grant_proof(workspace, current)
        with service._publication_fence(), registry.recovery_lease():
            watermark = _mode_watermark(owner, capability)
            registry.require_recovery_custody(custody._identity[0])
            denials = registry.recovery_snapshot()
            if denials.digest() != retained.denial_digest:
                raise RecoveryAuthorityError("needs_reconciliation: read denials differ from independent authority")
            try:
                plan = _ModeRecoveryPlan.model_validate(decode_recovery_json(read_private_file(plan_path, limit=_PLAN_BYTES)))
            except FileNotFoundError:
                plan = None
            if plan is not None and (
                plan.operation_id != operation_id or plan.request_digest != canonical_json_digest(request.model_dump(mode="json"))
            ):
                raise RecoveryAuthorityError("conflict: operation id selects another mode change")
            if isinstance(current.payload, SealedRecoveryHead):
                if plan is not None and (
                    current.payload.outcome == "applied" and current.payload.operation_digest == plan.digest()
                    and current.payload.predecessor == plan.predecessor
                ):
                    owner._require_retained_watermark(retained, _ready(watermark, plan))
                    _activate(owner, watermark, plan, guard, retained.anchor)
                    return current, plan.before.mode == "read_only" and plan.target != "read_only"
                owner._require_retained_watermark(retained, watermark)
                # Verify source data before arming the local guard. If a prior
                # attempt stopped after arming it, the exact signed control and
                # independently retained data coordinates still have to match.
                if not service.mode_recovery_pending(watermark.state):
                    service._verified_snapshot_locked()
                expected = _make_plan(owner, watermark, request, operation_id, current.digest())
                if watermark.state.mode == request.target_mode:
                    return current, False
                if plan is not None and plan != expected:
                    raise RecoveryAuthorityError("conflict: mode operation id was already used")
                if plan is None:
                    ensure_private_directory(operations)
                    write_private_file(plan_path, expected.model_dump_json().encode("utf-8"), exclusive=True)
                    plan = expected
                _ensure_pending_guard(guard, plan)
                pending = owner._sign(PendingRecoveryHead(
                    predecessor=plan.predecessor, prior_anchor=retained.anchor, operation="mode",
                    operation_digest=plan.digest(), participants=(plan.effect(),),
                ))
                custody._prepare_locked(pending)
            else:
                pending = current
                if plan is None:
                    raise RecoveryAuthorityError("needs_reconciliation: exact pending mode plan is unavailable")
            payload = pending.payload
            if not isinstance(payload, PendingRecoveryHead) or (
                payload.operation != "mode" or payload.predecessor != plan.predecessor
                or payload.operation_digest != plan.digest() or payload.participants != (plan.effect(),)
            ):
                raise RecoveryAuthorityError("needs_reconciliation: independently pending head is not this mode operation")
            before = watermark._replace(state=plan.before, position=(plan.applied.revision, plan.applied.prior_digest))
            owner._require_retained_watermark(retained, before)
            if plan.before_authority_digest != before.digest():
                raise RecoveryAuthorityError("needs_reconciliation: mode pre-state differs from independently pending proof")
            _ensure_pending_guard(guard, plan)
            if watermark == before:
                service._control.write_control_state(plan.applied_state(), plan.applied)
            elif watermark.state != plan.applied_state() or watermark.position != (plan.activation.revision, plan.applied.entry_digest):
                raise RecoveryAuthorityError("needs_reconciliation: local mode effect differs from its pending proof")
            applied = _mode_watermark(owner, capability)
            pinned = owner._pin_control(stack)
        anchor = owner._retain_bundle(workspace, pinned, _ready(applied, plan), denials, activation=plan.activation)
        successor = owner._sign(SealedRecoveryHead(
            anchor=anchor, outcome="applied", predecessor=plan.predecessor,
            pending_digest=pending.digest(), operation_digest=plan.digest(),
        ))
        with service._publication_fence(), registry.recovery_lease():
            if _mode_watermark(owner, capability) != applied or registry.recovery_snapshot() != denials:
                raise RecoveryAuthorityError("conflict: local authority changed while sealing mode")
            custody._seal_locked(successor, effects={_STORAGE_OWNER: plan.activation.entry_digest})
            _activate(owner, applied, plan, guard, anchor)
    return successor, plan.before.mode == "read_only" and plan.target != "read_only"
