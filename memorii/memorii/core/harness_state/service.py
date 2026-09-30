"""HarnessStateService: authorized host views over the durable partition.

Read permission is not mutation permission: the finite runtime read
grant is distinct from every memory-plane or source authority, is
revalidated before any bytes are released, and denies before lookup so
a missing task is not distinguishable from a denied one. The full graph
is never auto-injected: everything beyond the bounded envelope is
explicit paged retrieval.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.harness_state.envelope import (
    HarnessOutputBlock,
    HarnessStateEnvelope,
    build_envelope,
)
from memorii.core.persistence.runtime_repository import RuntimeStateRepository

_HEX_64 = r"^[0-9a-f]{64}$"


class HarnessStateError(RuntimeError):
    """Harness state read refused; closed error codes carry the reason."""


class RuntimeReadGrant(BaseModel):
    """Finite, revocable read grant over runtime state; opaque authority."""

    grant_id: str = Field(min_length=1)
    principal: str = Field(min_length=1)
    allowed_task_ids: tuple[str, ...] = ()
    epoch: int = Field(ge=1)
    expires_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)

    def authorizes(self, task_id: str, *, now: datetime | None = None) -> bool:
        moment = now or datetime.now(UTC)
        if moment >= self.expires_at:
            return False
        return not (self.allowed_task_ids and task_id not in self.allowed_task_ids)


class HarnessStateService:
    """Serve bounded envelope views from the verified runtime partition."""

    def __init__(self, repository: RuntimeStateRepository) -> None:
        self._repository = repository

    def read_state(
        self,
        *,
        task_id: str,
        grant: RuntimeReadGrant,
        view: str = "summary",
        now: datetime | None = None,
    ) -> HarnessStateEnvelope:
        if view not in ("execution", "solver", "summary", "history", "neighborhood"):
            raise HarnessStateError(
                "invalid_request: unsupported view; use execution|solver|summary"
                "|history|neighborhood"
            )
        if not grant.authorizes(task_id, now=now):
            # Denial before lookup: no task-existence disclosure.
            raise HarnessStateError("denied: read grant does not authorize this task")
        # One consistent snapshot: every read runs in a single partition
        # read transaction so no field mixes revisions.
        partition = self._repository.partition
        with partition.transaction(write=False) as connection:
            task = self._repository.get_task_in(connection, task_id)
            if task is None:
                raise HarnessStateError("not_found: task does not exist")
            attempts = self._repository.list_action_attempts_in(connection, task_id)
            solver_runs = tuple(
                run
                for run in self._repository.list_solver_runs_in(connection, task_id)
            )
            overlays = ()
            justifications = ()
            if solver_runs:
                primary = solver_runs[0]
                overlays = self._repository.list_overlays_in(
                    connection, primary.solver_id
                )
                justifications = self._repository.list_justifications_in(
                    connection, primary.solver_id
                )
            revision = partition.read_runtime_revision(connection)
        pending_actions = tuple(
            attempt.action_id
            for attempt in attempts
            if attempt.status in ("dispatched", "outcome_unknown")
        )
        candidate_hypotheses = tuple(
            HarnessOutputBlock(kind="work", label=item.justification_id, candidate=True)
            for item in justifications
            if item.active
        )[:16]
        committed_hypotheses = tuple(
            HarnessOutputBlock(kind="work", label=item.justification_id, committed=True)
            for item in justifications
            if not item.active
        )[:16]
        frontier = tuple(
            HarnessOutputBlock(kind="frontier", label=binding.node_id, detail=None)
            for overlay in overlays
            for binding in overlay.node_bindings
            if binding.frontier
        )[:16]
        unexplained = tuple(
            HarnessOutputBlock(kind="evidence", label=binding.node_id)
            for overlay in overlays
            for binding in overlay.node_bindings
            if binding.unexplained
        )[:16]
        reopenable = tuple(
            HarnessOutputBlock(kind="work", label=binding.node_id)
            for overlay in overlays
            for binding in overlay.node_bindings
            if binding.reopenable
        )[:16]
        status = "ready"
        omissions: list[str] = []
        if pending_actions:
            status = "reconcile_required"
        elif unexplained:
            status = "revalidation_required"
        for name, items in (
            ("frontier", frontier),
            ("candidate_hypotheses", candidate_hypotheses),
            ("committed_hypotheses", committed_hypotheses),
            ("unexplained_evidence", unexplained),
            ("reopenable_branches", reopenable),
        ):
            if len(items) == 16:
                omissions.append(
                    f"{name} truncated at 16 items; page for more"
                )
        return build_envelope(
            protocol_version=1,
            task_id=task_id,
            revision=revision,
            status=status,
            goal=task.goal,
            current_execution_node=task.root_execution_node_id,
            execution_status=task.lifecycle,
            remaining_acceptance=task.acceptance_criteria,
            solver_id=solver_runs[0].solver_id if solver_runs else None,
            solver_category=solver_runs[0].category if solver_runs else None,
            candidate_hypotheses=candidate_hypotheses,
            committed_hypotheses=committed_hypotheses,
            selected_overlay_id=overlays[0].version_id if overlays else None,
            frontier=frontier,
            unexplained_evidence=unexplained,
            reopenable_branches=reopenable,
            recommendation_kind="reconcile" if pending_actions else "none",
            recommendation_target=pending_actions[0] if pending_actions else None,
            pending_actions=pending_actions,
            omissions=tuple(omissions),
        )
