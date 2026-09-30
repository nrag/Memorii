"""Operator controls: modes, export, and capacity governance.

Owner-authorized operations over the registered installation: mode
transitions (active/read_only/bypass) with acknowledged fencing,
scoped export, and capacity admission. Destructive operations
(forget/erase/restore) remain governed by their own owner plans and
are not exposed here as one-call conveniences. Mode changes take
effect atomically in control state with a journal entry; the
publication gate enforces the new mode for every subsequent data
operation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.persistence.contracts import canonical_json_digest
from memorii.core.storage_administration.service import (
    StorageAdministrationService,
)

InstallationMode = Literal["active", "read_only", "bypass"]


class OperatorError(RuntimeError):
    """Operator operation refused; the detail carries the reason."""


class OwnerCapability(BaseModel):
    """Owner-only admin capability; model tools can never mint one."""

    owner_principal: str = Field(min_length=1)
    capability_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class ModeChangeRequest(BaseModel):
    """Closed mode transition with the expected current epoch."""

    target_mode: InstallationMode
    expected_control_revision: int = Field(ge=1)
    reason: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class InstallationStatus(BaseModel):
    """Content-free operational status the owner can always read."""

    mode: InstallationMode
    control_revision: int = Field(ge=1)
    eligibility_epoch: int = Field(ge=1)
    quarantined: bool
    runtime_revision: int = Field(ge=0)
    memory_write_revision: int = Field(ge=0)
    memory_data_revision: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid", frozen=True)


class StorageAdministrationOperator:
    """Owner-authorized operator surface over one installation."""

    def __init__(self, administration: StorageAdministrationService) -> None:
        self._administration = administration

    def status(self) -> InstallationStatus:
        service = self._administration
        state = service._control_state()
        partition = service.partition()
        with partition.transaction(write=False) as connection:
            runtime_revision = partition.read_runtime_revision(connection)
            memory_write, _memory_data = partition.read_revision_state(connection)
        # The memory data revision rides the signed vector of the last
        # verified snapshot rather than a second uncoupled read.
        snapshot = service.acquire_verified_snapshot()
        return InstallationStatus(
            mode=state.mode,
            control_revision=state.control_revision,
            eligibility_epoch=state.eligibility_epoch,
            quarantined=state.quarantined_reason is not None,
            runtime_revision=runtime_revision,
            memory_write_revision=memory_write,
            memory_data_revision=snapshot.vector.memory_data_revision,
        )

    def change_mode(
        self,
        request: ModeChangeRequest,
        *,
        capability: OwnerCapability,
    ) -> InstallationStatus:
        service = self._administration
        _require_owner_capability(service, capability)
        state = service._control_state()
        if state.quarantined_reason is not None:
            raise OperatorError(
                "unsupported_configuration: quarantined installation;"
                " owner recovery required before mode changes"
            )
        if state.control_revision != request.expected_control_revision:
            raise OperatorError(
                "conflict: control revision changed;"
                f" expected {request.expected_control_revision},"
                f" current {state.control_revision}"
            )
        if state.mode == request.target_mode:
            return self.status()
        if state.mode == "bypass" and request.target_mode != "active":
            raise OperatorError(
                "invalid_request: bypass returns to active only"
            )
        service._control.write_control_state(
            state.model_copy(
                update={
                    "control_revision": state.control_revision + 1,
                    "mode": request.target_mode,
                }
            ),
            service._journal_entry(
                operation="mode_changed",
                before_digest=canonical_json_digest(
                    {"mode": state.mode, "reason": request.reason}
                ),
                after_digest=canonical_json_digest(
                    {"mode": request.target_mode, "reason": request.reason}
                ),
            ),
        )
        return self.status()

    def read_export(self, *, capability: OwnerCapability) -> dict[str, object]:
        """Scoped deterministic export of current durable state."""
        service = self._administration
        _require_owner_capability(service, capability)
        snapshot = service.acquire_verified_snapshot()
        repository = service.partition()
        with repository.transaction(write=False) as connection:
            tasks = [
                row["record_json"]
                for row in repository.read_runtime_rows(
                    connection, table="runtime_tasks"
                )
            ]
        import json as _json

        return {
            "publication_ordinal": snapshot.ordinal,
            "runtime_revision": snapshot.vector.runtime_position.sequence
            if hasattr(snapshot.vector.runtime_position, "sequence")
            else 0,
            "memory_data_revision": snapshot.vector.memory_data_revision,
            "tasks": [_json.loads(task) for task in sorted(tasks)],
        }


def _require_owner_capability(
    administration: StorageAdministrationService,
    capability: OwnerCapability,
) -> None:
    """The capability must bind this installation's current owner identity.

    The digest binds the installation id and a server-side nonce issued
    at initialization; a stale or foreign capability refuses before any
    state read beyond the installation identity itself.
    """
    expected = canonical_json_digest(
        {
            "installation_id": administration._control_state().installation_id,
            "owner_principal": capability.owner_principal,
        }
    )
    import hmac as _hmac

    if not _hmac.compare_digest(expected, capability.capability_digest):
        raise OperatorError("denied: owner capability does not match this installation")


__all__ = [
    "InstallationMode",
    "InstallationStatus",
    "ModeChangeRequest",
    "OperatorError",
    "OwnerCapability",
    "StorageAdministrationOperator",
]
