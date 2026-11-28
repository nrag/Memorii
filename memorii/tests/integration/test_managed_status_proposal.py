"""An installed scoped command can propose only candidate solver status."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from memorii.core.harness_state.credentials import SidecarCredentialStore
from memorii.core.harness_state.managed_ingress import authenticated_host_commands
from memorii.core.harness_state.write_authority import HostCommandGrantRequest, ManagedHostCommandAuthority
from memorii.core.persistence.runtime_api import RuntimeCommandError
from memorii.core.persistence.runtime_contracts import (
    BeliefUpdateProposal,
    HypothesisContent,
    NodeEvidenceReference,
    RuntimeCommandRequest,
    SolverRunRecord,
    StatusUpdateProposal,
    TaskRecord,
)
from memorii.core.persistence.runtime_repository import RuntimeStateRepository, publish_runtime_change
from memorii.core.storage_administration.operator import mint_owner_capability
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.core.storage_administration.suppression_journal import (
    SuppressionCoordinate,
    SuppressionRecord,
    write_suppression_record,
)
from memorii.domain.enums import SolverNodeStatus


def test_managed_status_proposal_requires_scoped_active_graph_and_preserves_candidate_state(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    with StorageAdministrationService(root) as admin:
        admin.initialize()
        credentials = SidecarCredentialStore(root / "control" / "credentials")
        credential, secret = credentials.issue("host")
        grant_owner = ManagedHostCommandAuthority(admin)
        owner = mint_owner_capability(admin, "owner")
        now = datetime.now(UTC)
        task = TaskRecord(
            task_id="task:status", root_execution_node_id="exec:status", principal="host",
            goal="Assess the solver node", created_at=now,
            active_solver_by_execution_node={"exec:status": "solver:status"},
        )
        run = SolverRunRecord(
            solver_id="solver:status", task_id=task.task_id, parent_execution_node_id=task.root_execution_node_id,
            category="check", created_by="host",
        )
        other = run.model_copy(update={"solver_id": "solver:other", "task_id": "task:other"})
        node = HypothesisContent(statement="The observation may support the conclusion", strength=0.4)

        def seed(connection: sqlite3.Connection, repo: RuntimeStateRepository) -> None:
            repo.apply_task(connection, task)
            repo.apply_task(connection, task.model_copy(update={
                "task_id": "task:other",
                "active_solver_by_execution_node": {"exec:status": other.solver_id},
            }))
            for solver in (run, other):
                repo.apply_solver_run(connection, solver)
                repo.apply_solver_node(
                    connection, solver_id=solver.solver_id, node_id="hypothesis",
                    content=node, metadata_json="{}",
                )

        publish_runtime_change(admin, seed)
        grant_owner.issue(HostCommandGrantRequest(
            grant_id="status", credential_id=credential.credential_id, principal="host",
            client_namespace="host:status", allowed_kinds=("propose_state_change",),
            allowed_task_ids=(task.task_id,), expires_at=now + timedelta(minutes=5),
        ), capability=owner)
        commands = authenticated_host_commands(admin, credentials, secret)
        request = RuntimeCommandRequest(
            kind="propose_state_change", operation_id="status", task_id=task.task_id, expected_revision=task.version,
            proposal=StatusUpdateProposal(
                solver_id=run.solver_id, node_id="hypothesis", status="NEEDS_TEST", reason="Evidence is incomplete",
            ),
        )
        proposal = request.proposal
        assert isinstance(proposal, StatusUpdateProposal)
        for invalid, error in (
            (proposal.model_copy(update={"solver_id": other.solver_id}), "solver status authority"),
            (proposal.model_copy(update={"node_id": "other-node"}), "solver status authority"),
            (proposal.model_copy(update={"status": "unknown"}), "invalid_request"),
            (proposal.model_copy(update={"reason": "  "}), "invalid_request"),
            (proposal.model_copy(update={"evidence": (NodeEvidenceReference(source_id="external"),)}),
             "unsupported_configuration"),
            (BeliefUpdateProposal(
                solver_id=run.solver_id, node_id="hypothesis", justification_id="belief",
                epistemic_status="candidate", strength=0.3,
            ), "unsupported_configuration"),
        ):
            with pytest.raises(RuntimeCommandError, match=error):
                commands.prepare(request.model_copy(update={"proposal": invalid}))

        proof = commands.prepare(request)
        receipt = commands.dispatch(request, operation_origin=proof)
        assert commands.dispatch(request, operation_origin=proof) == receipt
        repo = RuntimeStateRepository(admin.partition())
        assert repo.get_task(task.task_id) == task
        assert repo.get_solver_run(run.solver_id) == run
        assert repo.read_solver_node_content(run.solver_id, "hypothesis") == node
        overlay, = repo.list_overlays(run.solver_id)
        justification, = repo.list_justifications(run.solver_id)
        assert overlay.committed is False
        assert overlay.node_bindings[0].candidate_status == SolverNodeStatus.NEEDS_TEST
        assert overlay.node_bindings[0].active_justification_ids == (justification.justification_id,)
        assert justification.conclusion == "status_update:NEEDS_TEST:Evidence is incomplete"

        stale = request.model_copy(update={"operation_id": "stale"})
        stale_proof = commands.prepare(stale)
        publish_runtime_change(admin, lambda connection, repo: repo.apply_task(
            connection, task.model_copy(update={"version": task.version + 1}),
        ))
        with pytest.raises(RuntimeCommandError, match="expected revision"):
            commands.dispatch(stale, operation_origin=stale_proof)
        assert len(repo.list_overlays(run.solver_id)) == 1

        write_suppression_record(root / "control", SuppressionRecord(
            suppression_id="1" * 64, plan_digest="2" * 64, closure_digest="3" * 64, applied_at_unix=1,
            scope_note="withhold this task",
            suppressed=(SuppressionCoordinate(coordinate_kind="task", coordinate_id=task.task_id),),
        ))
        with pytest.raises(RuntimeCommandError, match="authority"):
            commands.dispatch(request, operation_origin=proof)
