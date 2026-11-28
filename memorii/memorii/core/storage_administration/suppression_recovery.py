"""Independently seal one exact logical forget in settled maintenance mode."""

from __future__ import annotations

import hashlib
import tempfile
from contextlib import ExitStack
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.persistence.contracts import InstallationControlState, canonical_json_digest
from memorii.core.storage_administration.control_recovery_export import (
    MAX_RECOVERY_METADATA_BYTES,
    recovery_suppression_digests,
)
from memorii.core.storage_administration.operator import (
    OwnerCapability,
    StorageAdministrationOperator,
    require_owner_capability,
)
from memorii.core.storage_administration.operator_backup import backup_lifetime_guard, fsync_directory
from memorii.core.storage_administration.operator_governance import ForgetPlan, GovernanceOperator
from memorii.core.storage_administration.read_grant_recovery import ReadGrantRecoveryOwner, RecoveryWatermark
from memorii.core.storage_administration.recovery_authority import (
    InstallationRecoveryHead,
    PendingRecoveryHead,
    RecoveryAuthorityError,
    RecoveryParticipantExpectation,
    SealedRecoveryHead,
    decode_recovery_json,
)
from memorii.core.storage_administration.suppression_journal import SuppressionRecord, journal_directory
from memorii.stores.sqlite.private_storage import ensure_private_directory, read_private_file, write_private_file

_Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
_STORAGE = "storage-owner"
_SUPPRESSIONS = "suppression-owner"


class _SuppressionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    protocol_version: Literal[1] = 1
    operation_id: str = Field(min_length=1, max_length=512)
    request_digest: _Digest
    predecessor: _Digest
    before_digest: _Digest
    record: SuppressionRecord

    def digest(self) -> str:
        return canonical_json_digest(self.model_dump(mode="json"))

    @property
    def exported_record(self) -> SuppressionRecord:
        return self.record.model_copy(update={"authority_capability_digest": None})


def _new_plan(
    owner: ReadGrantRecoveryOwner,
    capability: OwnerCapability,
    request: ForgetPlan,
    operation_id: str,
    predecessor: str,
    before: RecoveryWatermark,
) -> _SuppressionPlan:
    governance = GovernanceOperator(StorageAdministrationOperator(owner._service))
    reviewed = governance.plan_forget(capability=capability, selectors=request.selectors, scope_note=request.scope_note)
    if reviewed != request:
        raise RecoveryAuthorityError("conflict: exact reviewed forget closure changed")
    revoked = {
        f"{item.coordinate_kind}|{item.coordinate_id}" + (f"|{item.record_kind}" if item.record_kind else "")
        for group in before.suppressions
        for record in group
        for item in record.suppressed
    }
    record = governance._make_suppression_record(
        request,
        capability=capability,
        installation_id=before.state.installation_id,
        already_revoked=revoked,
        journal_position=before.position[0],
    )
    if any(record.suppression_id == other.suppression_id for group in before.suppressions for other in group):
        raise RecoveryAuthorityError("conflict: suppression identity already exists")
    return _SuppressionPlan(
        operation_id=operation_id,
        request_digest=canonical_json_digest(request.model_dump(mode="json")),
        predecessor=predecessor,
        before_digest=before.digest(),
        record=record,
    )


def _next_state(state: InstallationControlState) -> InstallationControlState:
    return state.model_copy(
        update={
            "control_revision": state.control_revision + 1,
            "pending_epoch_increments": state.pending_epoch_increments + 1,
        }
    )


def _record_path(owner: ReadGrantRecoveryOwner, record: SuppressionRecord) -> Path:
    return journal_directory(owner._control) / f"forget-{record.applied_at_unix * 1000}-{record.suppression_id}.json"


def _read_record(path: Path) -> SuppressionRecord | None:
    try:
        content = read_private_file(path, limit=MAX_RECOVERY_METADATA_BYTES + 1)
    except FileNotFoundError:
        return None
    if len(content) > MAX_RECOVERY_METADATA_BYTES:
        raise RecoveryAuthorityError("integrity_error: recovery operation exceeds its byte limit")
    return SuppressionRecord.model_validate(decode_recovery_json(content))


def apply_suppression_with_recovery(
    owner: ReadGrantRecoveryOwner,
    request: ForgetPlan,
    *,
    operation_id: str,
    capability: OwnerCapability,
) -> InstallationRecoveryHead:
    """Apply or resume exactly one reviewed forget and seal its current deny state."""
    if not 0 < len(operation_id) <= 512:
        raise ValueError("suppression recovery requires a bounded operation id")
    service, custody, registry = owner._service, owner._custody, owner._registry
    require_owner_capability(service, capability)
    operations = owner._control / "suppression-recovery"
    plan_path = operations / f"{hashlib.sha256(operation_id.encode()).hexdigest()}.json"
    with (
        backup_lifetime_guard(service, exclusive=False),
        tempfile.TemporaryDirectory(prefix=".suppression-recovery-", dir=owner._control) as scratch,
        custody._writer_lease(),
        ExitStack() as stack,
    ):
        workspace = Path(scratch)
        current = custody._read()
        retained = owner._retained_grant_proof(workspace, current)
        with service._publication_fence(), registry.recovery_lease():
            watermark = owner._maintenance_watermark(capability)
            registry.require_recovery_custody(custody._identity[0])
            denials = registry.recovery_snapshot()
            if denials.digest() != retained.denial_digest:
                raise RecoveryAuthorityError("needs_reconciliation: read denials differ from independent authority")
            try:
                raw_plan = read_private_file(plan_path, limit=MAX_RECOVERY_METADATA_BYTES + 1)
            except FileNotFoundError:
                plan = None
            else:
                if len(raw_plan) > MAX_RECOVERY_METADATA_BYTES:
                    raise RecoveryAuthorityError("integrity_error: recovery operation exceeds its byte limit")
                plan = _SuppressionPlan.model_validate(decode_recovery_json(raw_plan))
                if (
                    plan.operation_id != operation_id
                    or plan.request_digest != canonical_json_digest(request.model_dump(mode="json"))
                    or plan.record.authority_capability_digest != capability.capability_digest
                ):
                    raise RecoveryAuthorityError("conflict: operation id identifies a different reviewed suppression")
            if isinstance(current.payload, SealedRecoveryHead):
                owner._require_retained_watermark(retained, watermark)
                if plan is not None and (
                    current.payload.operation_digest == plan.digest() and current.payload.outcome == "applied"
                ):
                    if _read_record(_record_path(owner, plan.record)) != plan.record:
                        raise RecoveryAuthorityError(
                            "needs_reconciliation: sealed local suppression receipt is missing"
                        )
                    return current
                service._verified_snapshot_locked()
                expected = _new_plan(owner, capability, request, operation_id, current.digest(), watermark)
                if plan is None:
                    plan = expected
                    ensure_private_directory(operations)
                    fsync_directory(owner._control)
                    payload = plan.model_dump_json().encode()
                    if len(payload) > MAX_RECOVERY_METADATA_BYTES:
                        raise RecoveryAuthorityError("resource_exhausted: recovery operation exceeds its byte limit")
                    write_private_file(plan_path, payload)
                elif plan != expected.model_copy(
                    update={
                        "record": expected.record.model_copy(update={"applied_at_unix": plan.record.applied_at_unix}),
                    }
                ):
                    raise RecoveryAuthorityError("conflict: suppression operation id was already used")
            elif plan is None:
                raise RecoveryAuthorityError("needs_reconciliation: exact pending suppression plan is unavailable")

            # Derive the exact prior view by removing only this operation's known
            # file effect. Retained bundle proof covers every other row and tier.
            live_record = _read_record(_record_path(owner, plan.record))
            if live_record is not None and live_record != plan.record:
                raise RecoveryAuthorityError("needs_reconciliation: local suppression bytes differ from the plan")
            active, archived = watermark.suppressions
            if (plan.exported_record in active) != (live_record is not None):
                raise RecoveryAuthorityError("needs_reconciliation: suppression is outside its expected path")
            before_suppressions = (tuple(record for record in active if record != plan.exported_record), archived)
            before = watermark._replace(
                state=retained.control,
                position=(retained.anchor.journal_ordinal + 1, retained.anchor.journal_tip),
                suppressions=before_suppressions,
            )
            owner._require_retained_watermark(retained, before)
            if before.digest() != plan.before_digest:
                raise RecoveryAuthorityError(
                    "needs_reconciliation: suppression pre-state differs from its pending proof"
                )
            next_state = _next_state(before.state)
            after_suppressions = (
                tuple(sorted((*before_suppressions[0], plan.exported_record), key=lambda item: item.suppression_id)),
                before_suppressions[1],
            )
            journal = service._journal_entry(
                operation="logical_forget_applied",
                position=before.position,
                before_digest=before.digest(),
                after_digest=canonical_json_digest(
                    {
                        "operation": plan.digest(),
                        "control": next_state.model_dump(mode="json"),
                        "suppression": plan.exported_record.model_dump(mode="json"),
                    }
                ),
            )
            participants = (
                RecoveryParticipantExpectation(
                    participant_id=_STORAGE,
                    revision=before.state.control_revision,
                    pre_state_digest=before.digest(),
                    effect_digest=journal.entry_digest,
                ),
                RecoveryParticipantExpectation(
                    participant_id=_SUPPRESSIONS,
                    revision=len(before_suppressions[0]),
                    pre_state_digest=recovery_suppression_digests(before_suppressions)[0],
                    effect_digest=recovery_suppression_digests(after_suppressions)[0],
                ),
            )
            current_payload = current.payload
            if isinstance(current_payload, SealedRecoveryHead):
                if watermark != before:
                    raise RecoveryAuthorityError("needs_reconciliation: unsealed local suppression effect")
                pending = owner._sign(
                    PendingRecoveryHead(
                        predecessor=plan.predecessor,
                        prior_anchor=retained.anchor,
                        operation="suppression",
                        operation_digest=plan.digest(),
                        participants=participants,
                    )
                )
                custody._prepare_locked(pending)
            else:
                pending = current
                if (
                    current_payload.operation != "suppression"
                    or current_payload.predecessor != plan.predecessor
                    or current_payload.operation_digest != plan.digest()
                    or current_payload.participants != participants
                ):
                    raise RecoveryAuthorityError(
                        "needs_reconciliation: independently pending head is not this suppression"
                    )

            applied = before._replace(
                state=next_state,
                position=(journal.revision + 1, journal.entry_digest),
                suppressions=after_suppressions,
            )
            if (watermark.state, watermark.position) == (before.state, before.position):
                if live_record is None:
                    path = _record_path(owner, plan.record)
                    ensure_private_directory(path.parent)
                    fsync_directory(owner._control)
                    write_private_file(path, (plan.record.model_dump_json() + "\n").encode())
                else:
                    # A prior writer could have stopped after rename but before
                    # syncing the entry, so repeat the barrier before SQLite.
                    fsync_directory(_record_path(owner, plan.record).parent)
                service._control.write_control_state(next_state, journal)
            elif watermark != applied:
                raise RecoveryAuthorityError(
                    "needs_reconciliation: local suppression state differs from its pending proof"
                )
            if owner._maintenance_watermark(capability) != applied:
                raise RecoveryAuthorityError("needs_reconciliation: local suppression receipt did not materialize")
            pinned = owner._pin_control(stack)
        anchor = owner._retain_bundle(workspace, pinned, applied, denials)
        successor = owner._sign(
            SealedRecoveryHead(
                anchor=anchor,
                outcome="applied",
                predecessor=plan.predecessor,
                pending_digest=pending.digest(),
                operation_digest=plan.digest(),
            )
        )
        with service._publication_fence(), registry.recovery_lease():
            if owner._maintenance_watermark(capability) != applied or registry.recovery_snapshot() != denials:
                raise RecoveryAuthorityError("conflict: local authority advanced while sealing suppression")
            custody._seal_locked(
                successor, effects={effect.participant_id: effect.effect_digest for effect in participants}
            )
    return successor
