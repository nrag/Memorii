"""Production checkpoint selection, replay, and host read behavior."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from memorii.core.harness_state.binding import HermesRuntimeStatePorts, RuntimeTaskBinding
from memorii.core.harness_state.consumer import ManagedRuntimeSpool
from memorii.core.harness_state.credentials import SidecarCredentialStore
from memorii.core.harness_state.paging import cursor_codec_for
from memorii.core.harness_state.service import HarnessStateError, RuntimeReadGrant
from memorii.core.harness_state.sidecar import RuntimeSidecar
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.persistence import runtime_journal
from memorii.core.persistence.runtime_api import RuntimeCommandService
from memorii.core.persistence.runtime_contracts import HypothesisContent, RuntimeCommandRequest, SolverRunRecord
from memorii.core.persistence.runtime_repository import RuntimeStateRepository, publish_runtime_change
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.core.storage_administration.suppression_journal import (
    SuppressionCoordinate,
    SuppressionRecord,
    write_suppression_record,
)
from memorii.domain.enums import CommitStatus, ExecutionNodeStatus, ExecutionNodeType, MemoryDomain
from memorii.domain.execution_graph.nodes import ExecutionNode


def _checkpointed_graph(service: StorageAdministrationService) -> tuple[str, str]:
    commands = RuntimeCommandService(service, client_namespace="host")
    commands.dispatch(RuntimeCommandRequest(
        kind="start_task", operation_id="start", goal="Original goal",
    ))
    task, = commands.repository.list_tasks()
    node = ExecutionNode(
        id=task.root_execution_node_id, type=ExecutionNodeType.MISSION, title="Root", description="Graph root",
        status=ExecutionNodeStatus.READY, owner=task.principal,
        created_at=task.created_at, updated_at=task.created_at,
    )
    run = SolverRunRecord(
        solver_id="solver:checkpoint", task_id=task.task_id, parent_execution_node_id=node.id,
        category="checkpoint", created_by=task.principal,
    )

    def seed(connection: sqlite3.Connection, repository: RuntimeStateRepository) -> None:
        repository.apply_execution_node(connection, task_id=task.task_id, node_id=node.id, node_json=node.model_dump_json())
        repository.apply_solver_run(connection, run)
        repository.apply_solver_node(
            connection, solver_id=run.solver_id, node_id="hypothesis",
            content=HypothesisContent(statement="Checkpoint hypothesis", strength=0.5), metadata_json="{}",
        )

    publish_runtime_change(service, seed)
    checkpoint_request = RuntimeCommandRequest(
        kind="checkpoint_task", operation_id="snapshot", task_id=task.task_id, expected_revision=task.version,
    )
    receipt = commands.dispatch(checkpoint_request)
    assert commands.dispatch(checkpoint_request) == receipt
    with service.verified_operation_context() as (_, finalized):
        assert finalized.checkpoint_digest is not None
        assert finalized.vector.runtime_position.kind == "batch"
        assert finalized.vector.runtime_position.sequence == 3
        checkpoint_digest = finalized.checkpoint_digest
    changed = task.model_copy(update={"version": 2, "goal": "Tail goal"})
    publish_runtime_change(service, lambda connection, repo: repo.apply_task(connection, changed))
    service.publish_memory_plane_batch((CanonicalMemoryRecord(
        memory_id="memory:checkpoint", domain=MemoryDomain.TRANSCRIPT, text="Separate memory publication",
        status=CommitStatus.COMMITTED,
    ),))
    return task.task_id, checkpoint_digest


def test_selected_checkpoint_skips_its_prefix_and_releases_the_same_tail_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "installation"
    with StorageAdministrationService(root) as service:
        service.initialize()
        task_id, digest = _checkpointed_graph(service)
        expected = service.acquire_verified_snapshot()

    replayed: list[int] = []
    original = runtime_journal._bind_events

    def track_batch(signed: runtime_journal._SignedBatch, bindings: runtime_journal._Bindings) -> None:
        replayed.append(signed.batch.sequence)
        original(signed, bindings)

    monkeypatch.setattr(runtime_journal, "_bind_events", track_batch)
    with StorageAdministrationService(root) as reopened:
        assert reopened.acquire_verified_snapshot() == expected
        assert replayed == [4]
        with (
            reopened.verified_operation_context() as (state, publication),
            reopened.partition().transaction(write=False) as connection,
        ):
            assert publication.checkpoint_digest == digest
            runtime_journal.verify_runtime_history(
                connection, finalized=publication, use_checkpoint=False,
                verify=lambda purpose, digest, signature: reopened._signing.verify(
                    reopened._signer_key_id, purpose, digest, signature,
                ),
            )
        assert replayed == [4, 1, 2, 3, 4]

        ports = HermesRuntimeStatePorts(reopened)
        ports.bind_task(RuntimeTaskBinding(installation_task_id=task_id, granted_to_principal="host"))
        envelope = ports.read_bound_state(principal="host")
        assert envelope.checkpoint_ref == digest
        assert envelope.goal == "Tail goal"
        assert envelope.solver_id == "solver:checkpoint"
        resumed = ports.resume_bound_state(principal="host")
        assert resumed.checkpoint_ref == digest
        assert resumed.goal == "Tail goal"
        assert resumed.solver_id == "solver:checkpoint"
        assert replayed == [4, 1, 2, 3, 4, 4]
        assert reopened.acquire_verified_snapshot() == expected

        credentials = SidecarCredentialStore(root / "control" / "credentials")
        _, secret = credentials.issue("host")
        grant = RuntimeReadGrant(
            grant_id="host-checkpoint", principal="host", allowed_task_ids=(task_id,), epoch=1,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        )
        sidecar = RuntimeSidecar.for_managed_installation(
            reopened, credentials=credentials, grant_factory=lambda _: grant,
            spool=ManagedRuntimeSpool(root / "spool"),
        )
        status, raw = sidecar.handle_state_request(
            bearer_token=secret, origin=None, body=json.dumps({"task_id": task_id}).encode(),
        )
        assert status == 200
        assert json.loads(raw)["checkpoint_ref"] == digest
        assert json.loads(raw)["goal"] == "Tail goal"
        codec = cursor_codec_for(reopened.partition())
        current_epoch = state.eligibility_epoch + state.pending_epoch_increments
        for binding, expected_status in (
            (None, 409),
            (("pre-restore-generation", current_epoch), 409),
            ((publication.data_generation_id, current_epoch + 1), 409),
            ((publication.data_generation_id, current_epoch), 200),
        ):
            cursor = codec.encode(
                task_id=task_id, principal="host", grant_id=grant.grant_id, grant_epoch=grant.epoch,
                runtime_revision=envelope.revision, view="summary", offset=0,
                expires_at=grant.expires_at, installation_binding=binding,
            )
            status, raw = sidecar.handle_state_request(
                bearer_token=secret, origin=None, body=json.dumps({"task_id": task_id, "cursor": cursor}).encode(),
            )
            assert status == expected_status
            if expected_status == 409:
                assert json.loads(raw)["code"] == "stale_cursor"
                assert b"Tail goal" not in raw

        old_cursor = codec.encode(
            task_id=task_id, principal="host", grant_id=f"harness:{task_id}", grant_epoch=1,
            runtime_revision=envelope.revision, view="summary", offset=0,
            expires_at=grant.expires_at, installation_binding=("pre-restore-generation", current_epoch),
        )
        with pytest.raises(HarnessStateError, match="stale_cursor"):
            ports.read_bound_state(principal="host", cursor=old_cursor)

        write_suppression_record(root / "control", SuppressionRecord(
            suppression_id="d" * 64, plan_digest="a" * 64, closure_digest="b" * 64,
            scope_note="suppress the restored task", applied_at_unix=1,
            suppressed=(SuppressionCoordinate(coordinate_kind="task", coordinate_id=task_id),),
        ))
        with pytest.raises(HarnessStateError, match="denied"):
            ports.resume_bound_state(principal="host")
        status, raw = sidecar.handle_state_request(
            bearer_token=secret, origin=None, body=json.dumps({"task_id": task_id}).encode(),
        )
        assert status == 403
        assert b"Tail goal" not in raw


@pytest.mark.parametrize("damage", ["member", "index", "anchor", "tail"])
def test_checkpoint_or_tail_corruption_refuses_managed_release(tmp_path: Path, damage: str) -> None:
    root = tmp_path / "installation"
    with StorageAdministrationService(root) as service:
        service.initialize()
        task_id, digest = _checkpointed_graph(service)
        path = service.partition_path()

    with sqlite3.connect(path) as connection:
        if damage in {"member", "index"}:
            row = connection.execute(
                "SELECT record_json FROM runtime_replay_checkpoints WHERE checkpoint_digest = ?", (digest,),
            ).fetchone()
            snapshot = json.loads(row[0])
            if damage == "member":
                snapshot["members"][0]["owner_record_json"] = "{}"
            else:
                snapshot["dedupe_bindings"].pop()
            connection.execute(
                "UPDATE runtime_replay_checkpoints SET record_json = ? WHERE checkpoint_digest = ?",
                (json.dumps(snapshot), digest),
            )
        else:
            connection.execute("DELETE FROM runtime_event_batches WHERE sequence = ?", (3 if damage == "anchor" else 4,))

    with StorageAdministrationService(root) as reopened:
        ports = HermesRuntimeStatePorts(reopened)
        ports.bind_task(RuntimeTaskBinding(installation_task_id=task_id, granted_to_principal="host"))
        with pytest.raises(HarnessStateError, match="integrity_error"):
            ports.read_bound_state(principal="host")


def test_interrupted_finalization_reopens_exact_checkpoint_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "installation"
    with StorageAdministrationService(root) as service:
        service.initialize()
        commands = RuntimeCommandService(service)
        commands.dispatch(RuntimeCommandRequest(kind="start_task", operation_id="start", goal="Recover a checkpoint"))
        task, = commands.repository.list_tasks()
        request = RuntimeCommandRequest(
            kind="checkpoint_task", operation_id="checkpoint", task_id=task.task_id, expected_revision=task.version,
        )

        def interrupt(*_args: object) -> None:
            raise OSError("simulated loss after partition commit")

        with monkeypatch.context() as patch:
            patch.setattr(service, "_finalize_publication", interrupt)
            with pytest.raises(OSError, match="after partition commit"):
                commands.dispatch(request)
        pending = service._control.read_pending_intent(service._repository_id())
        assert pending is not None and pending.candidate_state.checkpoint_digest is not None
        expected_digest = pending.candidate_state.checkpoint_digest

    with StorageAdministrationService(root) as reopened:
        assert reopened.resolve_pending_publication().disposition == "finalized"
        with reopened.verified_operation_context() as (_, publication):
            assert publication.checkpoint_digest == expected_digest
        assert RuntimeCommandService(reopened).dispatch(request).status == "committed"
