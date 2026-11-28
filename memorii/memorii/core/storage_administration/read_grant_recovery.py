"""Live read-grant denial custody for the bounded maintenance recovery profile."""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Annotated, Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.harness_state.grant_registry import GrantDenial, GrantDenialSnapshot, GrantEpochRegistry
from memorii.core.persistence.contracts import InstallationControlState, RuntimePublicationState, canonical_json_digest
from memorii.core.storage_administration.control_recovery_export import (
    export_control_recovery,
    read_recovery_suppressions,
    recovery_suppression_digests,
)
from memorii.core.storage_administration.operator import OwnerCapability, require_owner_capability
from memorii.core.storage_administration.operator_backup import (
    _open_backup_snapshot,
    _snapshot_digest,
    _sqlite_backup,
    backup_lifetime_guard,
)
from memorii.core.storage_administration.recovery_authority import (
    IndependentRecoveryCustody,
    InstallationRecoveryAnchor,
    InstallationRecoveryHead,
    PendingRecoveryHead,
    RecoveryAuthorityError,
    RecoveryParticipantExpectation,
    SealedRecoveryHead,
    decode_recovery_json,
    sign_recovery_head,
)
from memorii.core.storage_administration.recovery_bundle import open_recovery_bundle, seal_recovery_bundle
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.core.storage_administration.suppression_journal import SuppressionRecord
from memorii.stores.sqlite.private_storage import ensure_private_directory, read_private_file, write_private_file

_READ_GRANTS = "read-grants"
_Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
_Identity = Annotated[str, Field(min_length=1, max_length=512)]
_Suppressions = tuple[tuple[SuppressionRecord, ...], tuple[SuppressionRecord, ...]]


class _Watermark(NamedTuple):
    state: InstallationControlState
    publication: RuntimePublicationState
    position: tuple[int, str]
    suppressions: _Suppressions

    def digest(self) -> str:
        return canonical_json_digest({
            "control": self.state.model_dump(mode="json"),
            "publication": self.publication.payload_digest(),
            "journal": self.position,
            "suppressions": [[record.model_dump(mode="json") for record in owner] for owner in self.suppressions],
        })


class ReadGrantRecoveryRevocation(BaseModel):
    """Exact intent for one independently serialized read-grant revocation."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    protocol_version: Literal[1] = 1
    operation_id: _Identity
    predecessor: _Digest
    local_authority_digest: _Digest
    before_digest: _Digest
    before_count: Annotated[int, Field(ge=0, strict=True)]
    denial: GrantDenial
    effect_digest: _Digest

    def digest(self) -> str:
        return canonical_json_digest(self.model_dump(mode="json"))


class ReadGrantRecoveryOwner:
    """Owner entrypoint for a registered, currently read-only installation.

    This participant profile cannot attest to other live authority owners.
    Installed production registration needs the complete mutation composition.
    """

    def __init__(
        self, service: StorageAdministrationService, *, custody: IndependentRecoveryCustody,
        public_key: bytes, recovery_key: bytes,
    ) -> None:
        root = service.installation_root.resolve()
        custody_root = custody._head_path.parent.resolve()
        if root.is_relative_to(custody_root) or custody_root.is_relative_to(root):
            raise RecoveryAuthorityError("denied: recovery custody must be outside the installation tree")
        if len(recovery_key) != 32 or service._signing.public_key_bytes(service._signer_key_id) != public_key:
            raise RecoveryAuthorityError("denied: recovery key or pinned signer does not match")
        self._service = service
        self._custody = custody
        self._public_key = public_key
        self._key = recovery_key
        self._control = root / "control"
        self._registry = GrantEpochRegistry(self._control / "grants")

    def _sign(self, payload: PendingRecoveryHead | SealedRecoveryHead) -> InstallationRecoveryHead:
        return sign_recovery_head(payload, signer=self._service._signing, signer_key_id=self._service._signer_key_id)

    def _current_suppressions(self) -> _Suppressions:
        return (
            read_recovery_suppressions(self._control / "suppressions"),
            read_recovery_suppressions(self._control / "suppressions-archive"),
        )

    def _maintenance_watermark(self, capability: OwnerCapability) -> _Watermark:
        service = self._service
        require_owner_capability(service, capability)
        state, publication = service.current_publication_in_fence()
        change = service._control.read_generation_change(publication.repository_id)
        if (
            state.mode != "read_only" or service._control.read_pending_intent(publication.repository_id) is not None
            or (change is not None and change.phase == "prepared")
        ):
            raise RecoveryAuthorityError("conflict: read-grant recovery requires settled read-only maintenance")
        position = service._control.next_journal_position()
        return _Watermark(state, publication, position, self._current_suppressions())

    def _pin_control(self, stack: ExitStack) -> sqlite3.Connection:
        connection = stack.enter_context(_open_backup_snapshot(self._service.control_path()))
        connection.execute("SELECT id FROM installation_control").fetchone()
        return connection

    def _retain_bundle(
        self, workspace: Path, pinned: sqlite3.Connection, watermark: _Watermark, denials: GrantDenialSnapshot,
    ) -> InstallationRecoveryAnchor:
        snapshot = workspace / "control.sqlite3"
        _sqlite_backup(pinned, snapshot)
        _snapshot_digest(snapshot)
        state, publication, _, suppressions = watermark
        manifest, paths = export_control_recovery(
            self._service, snapshot=snapshot, state=state, publication=publication, output=workspace,
            custody_id=self._custody._identity[0], suppressions=suppressions, grant_denials=denials,
        )
        anchor = manifest.anchor()
        destination = self._custody.bundle_path(anchor)
        if destination.exists() or destination.is_symlink():
            open_recovery_bundle(
                destination, anchor=anchor, public_key=self._public_key,
                recovery_key=self._key, destination=workspace / "verified-successor",
            )
        else:
            seal_recovery_bundle(manifest, sources=paths, destination=destination, public_key=self._public_key, recovery_key=self._key)
        return anchor

    def register(self, *, capability: OwnerCapability) -> InstallationRecoveryHead:
        """Retain the initial read-grant/suppression snapshot in external custody."""
        custody, registry, service = self._custody, self._registry, self._service
        require_owner_capability(service, capability)
        with (
            backup_lifetime_guard(service, exclusive=False),
            tempfile.TemporaryDirectory(prefix=".read-grant-recovery-", dir=self._control) as scratch,
            custody._writer_lease(), ExitStack() as stack,
        ):
            workspace = Path(scratch)
            if custody._head_path.exists() or custody._head_path.is_symlink():
                existing = custody._read()
                if not isinstance(existing.payload, SealedRecoveryHead):
                    raise RecoveryAuthorityError("needs_reconciliation: independent authority is pending")
                retained, proof, suppressions = self._retained_grant_proof(workspace, existing)
                with service._publication_fence(), registry.recovery_lease():
                    registry.require_recovery_custody(custody._identity[0])
                    self._require_retained_watermark(retained, suppressions, self._maintenance_watermark(capability))
                    if registry.recovery_snapshot().digest() != proof:
                        raise RecoveryAuthorityError("needs_reconciliation: live read grants differ from retained state")
                return existing
            with service.verified_operation_context(), registry.recovery_lease():
                watermark = self._maintenance_watermark(capability)
                denials = registry.recovery_snapshot()
                registry.register_recovery_custody(custody._identity[0])
                pinned = self._pin_control(stack)
            anchor = self._retain_bundle(workspace, pinned, watermark, denials)
            head = self._sign(SealedRecoveryHead(anchor=anchor, outcome="registered"))
            with service._publication_fence(), registry.recovery_lease():
                if self._maintenance_watermark(capability) != watermark or registry.recovery_snapshot() != denials:
                    raise RecoveryAuthorityError("conflict: authority changed during read-grant recovery registration")
                custody._register_locked(head)
            return head

    def _make_plan(
        self, predecessor: InstallationRecoveryHead, before: GrantDenialSnapshot, watermark: _Watermark,
        grant_id: str, operation_id: str,
    ) -> ReadGrantRecoveryRevocation:
        denial = GrantDenial(grant_id=grant_id, epoch=before.epochs().get(grant_id, 1) + 1, revoked_at_unix=int(time.time()))
        expected = GrantDenialSnapshot(denials=(*before.denials, denial))
        return ReadGrantRecoveryRevocation(
            operation_id=operation_id, predecessor=predecessor.digest(), local_authority_digest=watermark.digest(),
            before_digest=before.digest(), before_count=len(before.denials),
            denial=denial, effect_digest=expected.digest(),
        )

    def _retained_grant_proof(
        self, workspace: Path, head: InstallationRecoveryHead,
    ) -> tuple[InstallationRecoveryAnchor, str, tuple[str, str]]:
        anchor = head.payload.anchor if isinstance(head.payload, SealedRecoveryHead) else head.payload.prior_anchor
        if hashlib.sha256(self._public_key).hexdigest() != anchor.signer_fingerprint:
            raise RecoveryAuthorityError("denied: historical signer continuity is not established")
        manifest = open_recovery_bundle(
            self._custody.bundle_path(anchor), anchor=anchor, public_key=self._public_key,
            recovery_key=self._key, destination=workspace / "previous",
        )
        members = {(member.owner_id, member.kind): member for member in manifest.members}
        grant_member = members.get((_READ_GRANTS, "deny_state"))
        active = members.get(("active", "suppression"))
        archived = members.get(("archived", "suppression"))
        if grant_member is None or active is None or archived is None or any(
            member.schema_version != 1 for member in (grant_member, active, archived)
        ):
            raise RecoveryAuthorityError("unsupported_configuration: retained authority lacks read-grant denial state")
        return anchor, grant_member.source_coordinate, (active.digest, archived.digest)

    @staticmethod
    def _require_retained_watermark(
        retained: InstallationRecoveryAnchor, suppressions: tuple[str, str], watermark: _Watermark,
    ) -> None:
        if (
            (retained.control_revision, retained.journal_ordinal + 1, retained.journal_tip)
            != (watermark.state.control_revision, *watermark.position)
            or retained.publication_digest != watermark.publication.payload_digest()
            or suppressions != recovery_suppression_digests(watermark.suppressions)
        ):
            raise RecoveryAuthorityError("needs_reconciliation: live authority differs from retained control and suppressions")

    def revoke(self, grant_id: str, *, operation_id: str, capability: OwnerCapability) -> InstallationRecoveryHead:
        """Apply or finish the matching pending denial and independently seal it."""
        if not grant_id or not 0 < len(operation_id) <= 512:
            raise ValueError("grant id and bounded operation id are required")
        require_owner_capability(self._service, capability)
        custody, registry, service = self._custody, self._registry, self._service
        with (
            backup_lifetime_guard(service, exclusive=False),
            tempfile.TemporaryDirectory(prefix=".read-grant-recovery-", dir=self._control) as scratch,
            custody._writer_lease(), ExitStack() as stack,
        ):
            workspace = Path(scratch)
            current = custody._read()
            retained, proof, suppressions = self._retained_grant_proof(workspace, current)
            with service._publication_fence(), registry.recovery_lease():
                watermark = self._maintenance_watermark(capability)
                registry.require_recovery_custody(custody._identity[0])
                self._require_retained_watermark(retained, suppressions, watermark)
                operations = self._control / "read-grant-recovery"
                ensure_private_directory(operations)
                operation_path = operations / f"{hashlib.sha256(operation_id.encode()).hexdigest()}.json"
                try:
                    plan = ReadGrantRecoveryRevocation.model_validate(decode_recovery_json(
                        read_private_file(operation_path, limit=256 * 1024),
                    ))
                except FileNotFoundError:
                    plan = None
                if plan is not None and (plan.operation_id != operation_id or plan.denial.grant_id != grant_id):
                    raise RecoveryAuthorityError("conflict: operation id identifies a different read-grant denial")
                if isinstance(current.payload, SealedRecoveryHead):
                    before = registry.recovery_snapshot()
                    if before.digest() != proof:
                        raise RecoveryAuthorityError("needs_reconciliation: live read grants differ from retained state")
                    if plan is not None:
                        if current.payload.operation_digest == plan.digest() and current.payload.outcome == "applied":
                            return current
                        if (
                            plan.predecessor != current.digest() or plan.before_digest != before.digest()
                            or plan.before_count != len(before.denials)
                            or plan.local_authority_digest != watermark.digest()
                        ):
                            raise RecoveryAuthorityError("conflict: read-grant recovery operation id was already used")
                    else:
                        plan = self._make_plan(current, before, watermark, grant_id, operation_id)
                        write_private_file(operation_path, plan.model_dump_json().encode("utf-8"), exclusive=True)
                    pending = self._sign(PendingRecoveryHead(
                        predecessor=plan.predecessor, prior_anchor=current.payload.anchor, operation="grant",
                        operation_digest=plan.digest(), participants=(RecoveryParticipantExpectation(
                            participant_id=_READ_GRANTS, revision=plan.before_count, pre_state_digest=plan.before_digest,
                            effect_digest=plan.effect_digest,
                        ),),
                    ))
                    custody._prepare_locked(pending)
                else:
                    pending = current
                    if plan is None:
                        raise RecoveryAuthorityError("needs_reconciliation: pending read-grant operation is unavailable")
                payload = pending.payload
                if not isinstance(payload, PendingRecoveryHead) or (
                    payload.operation != "grant" or payload.operation_digest != plan.digest()
                    or payload.predecessor != plan.predecessor or proof != plan.before_digest
                    or plan.local_authority_digest != watermark.digest()
                    or plan.denial.grant_id != grant_id or payload.participants != (RecoveryParticipantExpectation(
                        participant_id=_READ_GRANTS, revision=plan.before_count, pre_state_digest=plan.before_digest,
                        effect_digest=plan.effect_digest,
                    ),)
                ):
                    raise RecoveryAuthorityError("needs_reconciliation: pending operation is not this read-grant denial")
                denials = registry.apply_recovery_denial(
                    plan.denial, before_digest=plan.before_digest, before_count=plan.before_count,
                    effect_digest=plan.effect_digest, operation_digest=plan.digest(),
                )
                if denials.digest() != plan.effect_digest:
                    raise RecoveryAuthorityError("needs_reconciliation: read-grant denial does not match its planned effect")
                pinned = self._pin_control(stack)
            anchor = self._retain_bundle(workspace, pinned, watermark, denials)
            successor = self._sign(SealedRecoveryHead(
                anchor=anchor, outcome="applied", predecessor=plan.predecessor,
                pending_digest=pending.digest(), operation_digest=plan.digest(),
            ))
            with service._publication_fence(), registry.recovery_lease():
                if self._maintenance_watermark(capability) != watermark or registry.recovery_snapshot() != denials:
                    raise RecoveryAuthorityError("conflict: authority advanced while sealing read-grant denial")
                custody._seal_locked(successor, effects={_READ_GRANTS: denials.digest()})
            return successor
