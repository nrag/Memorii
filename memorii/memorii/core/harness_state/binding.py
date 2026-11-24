"""Hermes runtime-state ports over the durable partition.

The binding composes the same verified installation the semantic path
uses: prefetch appends the bounded runtime envelope beside semantic
recall, and the model tools delegate to the authorized harness read
service. When no durable runtime task binding exists, the tools state
plainly that they are provider work-state summaries — never a durable
runtime view.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.harness_state.envelope import (
    HarnessStateEnvelope,
    render_harness_state,
)
from memorii.core.harness_state.service import (
    HarnessStateError,
    HarnessStateService,
    RuntimeReadGrant,
)
from memorii.core.persistence.runtime_repository import RuntimeStateRepository
from memorii.core.storage_administration.service import (
    InstallationIntegrityError,
    StorageAdministrationError,
    StorageAdministrationService,
)

if TYPE_CHECKING:
    from memorii.core.harness_state.writeback_decision import WritebackDecisionService
    from memorii.core.work_state.runtime_projection_read import ManagedWorkProjectionReader


class RuntimeTaskBinding(BaseModel):
    """Explicit task-to-host binding; a native session id is not authority."""

    installation_task_id: str = Field(min_length=1)
    host_session_id: str | None = None
    granted_to_principal: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class HermesRuntimeStatePorts:
    """Prefetch and tool ports serving bounded durable runtime state."""

    def __init__(
        self,
        administration: StorageAdministrationService,
        *,
        grant_ttl: timedelta = timedelta(minutes=5),
    ) -> None:
        self._administration = administration
        self._grant_ttl = grant_ttl
        self._service = HarnessStateService(
            RuntimeStateRepository(administration.partition())
        )
        self._bindings: dict[str, RuntimeTaskBinding] = {}

    def bind_task(self, binding: RuntimeTaskBinding) -> None:
        self._bindings[binding.granted_to_principal] = binding

    def host_writeback(self, *, credential: str) -> WritebackDecisionService:
        """Return the embedded host-only port using the installed credential owner."""
        from memorii.core.harness_state.credentials import SidecarCredentialStore
        from memorii.core.harness_state.writeback_decision import WritebackDecisionService

        credentials = SidecarCredentialStore(self._administration.installation_root / "control" / "credentials")
        return WritebackDecisionService(self._administration, credentials, credential)

    def host_work_projection(
        self, *, credential: str, grant: RuntimeReadGrant,
    ) -> ManagedWorkProjectionReader:
        """Bind the host-only managed recall port to a provisioned finite grant."""
        from memorii.core.harness_state.credentials import SidecarCredentialStore
        from memorii.core.work_state.runtime_projection_read import ManagedWorkProjectionReader

        credentials = SidecarCredentialStore(self._administration.installation_root / "control" / "credentials")
        return ManagedWorkProjectionReader(
            self._administration, credentials=credentials, secret=credential, grant=grant,
        )

    def runtime_prefetch_text(
        self,
        *,
        principal: str,
        now: Callable[[], datetime] | None = None,
    ) -> str | None:
        """Bounded envelope rendered for the model, or None when unbound."""
        binding = self._bindings.get(principal)
        if binding is None:
            return None
        envelope = self.read_bound_state(principal=principal, now=now)
        return render_harness_state(envelope)

    def read_bound_state(
        self,
        *,
        principal: str,
        now: Callable[[], datetime] | None = None,
    ) -> HarnessStateEnvelope:
        binding = self._bindings.get(principal)
        if binding is None:
            raise HarnessStateError("denied: no runtime task binding for principal")
        moment = (now or (lambda: datetime.now(UTC)))()
        grant = RuntimeReadGrant(
            grant_id=f"harness:{binding.installation_task_id}",
            principal=principal,
            allowed_task_ids=(binding.installation_task_id,),
            epoch=1,
            expires_at=moment + self._grant_ttl,
        )
        try:
            return self._service.read_state(
                task_id=binding.installation_task_id, grant=grant, now=moment
            )
        except InstallationIntegrityError as exc:
            raise HarnessStateError("integrity_error: managed runtime state could not be verified") from exc
        except StorageAdministrationError as exc:
            raise HarnessStateError("unavailable: reopen the managed runtime state port") from exc

    def tool_state_summary(self, *, principal: str) -> dict[str, object]:
        """Model-tool state view: durable when bound, plainly otherwise."""
        if principal not in self._bindings:
            return {
                "source": "provider-work-state-summary",
                "durable_runtime_view": False,
                "note": "no durable runtime task binding; provider work-state only",
            }
        try:
            envelope = self.read_bound_state(principal=principal)
        except HarnessStateError as exc:
            return {
                "source": "provider-work-state-summary",
                "durable_runtime_view": False,
                "note": f"durable runtime view refused: {exc}",
            }
        return {
            "source": "durable-runtime-state",
            "durable_runtime_view": True,
            "task_id": envelope.task_id,
            "revision": envelope.revision,
            "status": envelope.status,
            "recommendation_kind": envelope.recommendation_kind,
            "pending_actions": list(envelope.pending_actions),
        }


__all__ = [
    "HermesRuntimeStatePorts",
    "RuntimeTaskBinding",
]
