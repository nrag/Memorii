"""Durable runtime journeys: create, terminate, resume in a fresh process.

The observable acceptance of the runtime-recovery packet: one process
creates a task with competing hypotheses, candidates, overlays,
justifications, unresolved frontier work and a dispatched action; an
independent process restores identical verified state without repeating
anything.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from memorii.core.persistence.runtime_contracts import (
    TaskRecord,
)
from memorii.core.persistence.runtime_repository import (
    RuntimeStateRepository,
    publish_runtime_change,
)
from memorii.core.storage_administration.service import StorageAdministrationService

_NOW = datetime(2026, 1, 1, tzinfo=UTC)

_AUTHOR_PROGRAM = '''
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from memorii.core.persistence.runtime_contracts import (
    ActionAttemptRecord,
    HypothesisContent,
    ObservationContent,
    OverlayJustificationBinding,
    RuntimeOverlayVersion,
    SolverJustificationRecord,
    SolverRunRecord,
    TaskRecord,
)
from memorii.core.persistence.runtime_repository import (
    RuntimeStateRepository,
    publish_runtime_change,
)
from memorii.core.storage_administration.service import StorageAdministrationService

now = datetime(2026, 1, 1, tzinfo=UTC)
root = Path(sys.argv[1])
service = StorageAdministrationService(root)
try:
    publish_runtime_change(
        service,
        lambda connection, repository: [
            repository.apply_task(connection, TaskRecord(
                task_id="task:journey",
                principal="principal:a",
                goal="Diagnose the latency regression",
                created_at=now,
                root_execution_node_id="exec:root",
            )),
            repository.apply_solver_run(connection, SolverRunRecord(
                solver_id="solver:journey",
                task_id="task:journey",
                parent_execution_node_id="exec:root",
                category="diagnostic",
                created_by="author-process",
            )),
            repository.apply_solver_node(connection, solver_id="solver:journey",
                node_id="node:obs",
                content=ObservationContent(summary="p95 doubled after deploy",
                    source_refs=[], result_ref="metric:latency"),
                metadata_json=json.dumps({"created_at": now.isoformat()})),
            repository.apply_solver_node(connection, solver_id="solver:journey",
                node_id="node:h1",
                content=HypothesisContent(statement="Cache stampede", strength=0.7),
                metadata_json=json.dumps({"created_at": now.isoformat()})),
            repository.apply_solver_node(connection, solver_id="solver:journey",
                node_id="node:h2",
                content=HypothesisContent(statement="N+1 query", strength=0.5),
                metadata_json=json.dumps({"created_at": now.isoformat()})),
            repository.apply_solver_node(connection, solver_id="solver:journey",
                node_id="node:h3",
                content=HypothesisContent(statement="Clock skew", strength=0.2),
                metadata_json=json.dumps({"created_at": now.isoformat()})),
            repository.apply_justification(connection, SolverJustificationRecord(
                justification_id="just:obs-supports-h1",
                solver_id="solver:journey",
                conclusion="latency spike aligns with cache miss burst",
                supporting_ids=("node:obs",),
                strength=0.8,
            )),
            repository.apply_overlay(connection, RuntimeOverlayVersion(
                version_id="overlay:v1",
                solver_id="solver:journey",
                node_bindings=(
                    OverlayJustificationBinding(node_id="node:h1",
                        active_justification_ids=("just:obs-supports-h1",),
                        frontier=True, reopenable=True),
                    OverlayJustificationBinding(node_id="node:h2", frontier=True),
                    OverlayJustificationBinding(node_id="node:h3", frontier=True),
                    OverlayJustificationBinding(node_id="node:obs", unexplained=True),
                ),
                created_at=now,
                committed=True,
            )),
            repository.apply_action_attempt(connection, ActionAttemptRecord(
                action_id="action:replay-traffic",
                task_id="task:journey",
                recommendation_id="rec:replay",
                recommendation_revision=1,
                executor_binding="author-host",
                status="dispatched",
            )),
        ],
    )
    repository = RuntimeStateRepository(service.partition())
    print(repository.runtime_revision())
finally:
    service.close()
'''

_READER_PROGRAM = '''
import sys
from pathlib import Path

from memorii.core.persistence.runtime_contracts import HypothesisContent
from memorii.core.persistence.runtime_repository import RuntimeStateRepository
from memorii.core.storage_administration.service import StorageAdministrationService

root = Path(sys.argv[1])
service = StorageAdministrationService(root)
try:
    snapshot = service.acquire_verified_snapshot()
    repository = RuntimeStateRepository(service.partition())
    task = repository.get_task("task:journey")
    runs = repository.list_solver_runs("task:journey")
    overlay = repository.get_overlay("overlay:v1")
    action = repository.get_action_attempt("action:replay-traffic")
    h1 = repository.read_solver_node_content("solver:journey", "node:h1")
    print(
        task.lifecycle,
        len(runs),
        len(overlay.node_bindings),
        action.status,
        isinstance(h1, HypothesisContent) and h1.statement,
        snapshot.vector.runtime_position.sequence,
    )
finally:
    service.close()
'''


def test_task_state_survives_process_death_without_repetition(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    service = StorageAdministrationService(root)
    service.initialize()
    service.close()

    author = subprocess.run(
        [sys.executable, "-c", _AUTHOR_PROGRAM, str(root)],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert author.stdout.strip() == "1"

    reader = subprocess.run(
        [sys.executable, "-c", _READER_PROGRAM, str(root)],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    # active task, one solver run, four overlay bindings (frontier + unexplained),
    # dispatched action intact (never auto-rerun), hypothesis content restored,
    # runtime head at revision 1.
    assert reader.stdout.strip() == "active 1 4 dispatched Cache stampede 1"


def test_second_runtime_publication_advances_both_heads(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    service = StorageAdministrationService(root)
    try:
        service.initialize()
        first = publish_runtime_change(
            service, lambda connection, repository: None
        )
        second = publish_runtime_change(
            service,
            lambda connection, repository: repository.apply_task(
                connection, TaskRecord(
                    task_id="task:second",
                    principal="principal:a",
                    goal="Second task",
                    created_at=_NOW,
                    root_execution_node_id="exec:root",
                ),
            ),
        )
        assert (first, second) == (1, 2)
        snapshot = service.acquire_verified_snapshot()
        assert snapshot.ordinal == 2  # genesis(0) + two runtime publications
        repository = RuntimeStateRepository(service.partition())
        assert repository.get_task("task:second") is not None
    finally:
        service.close()
