"""Runtime event profile: closed grammar, ordering, idempotency, conflicts.

The reference reducer check runs the same frozen encoded batches through
a deliberately naive independent implementation (a flat replay that
records every non-duplicate application in arrival order) and requires
identical materialized results — a separately authored consumer with no
imports from the production replay module.
"""

from __future__ import annotations

import pytest
from memorii.core.persistence.runtime_events import (
    LEGAL_COMBINATIONS,
    RuntimeEventBatch,
    RuntimeReplayError,
    RuntimeReplayState,
    create_runtime_event,
    reduce_runtime_batch,
    replay_runtime_batches,
)


def _event(
    event_id: str,
    *,
    entity_id: str | None = None,
    version: int = 1,
    statement: str = "hypothesis",
    graph_type: str = "solver",
    entity_type: str = "node",
    operation: str = "create",
    dedupe_key: str | None = None,
    task_id: str = "task:one",
    solver_run_id: str | None = "solver:one",
) -> object:
    return create_runtime_event(
        event_id=event_id,
        dedupe_key=dedupe_key or f"dk:{event_id}",
        graph_type=graph_type,
        entity_type=entity_type,
        operation=operation,
        entity_id=entity_id or event_id,
        entity={
            "id": entity_id or event_id,
            "version": version,
            "statement": statement,
        },
        metadata_version=version,
        task_id=task_id,
        solver_run_id=solver_run_id,
    )


def _batch(sequence: int, events: tuple[object, ...]) -> RuntimeEventBatch:
    from memorii.core.persistence.runtime_events import create_runtime_batch

    return create_runtime_batch(
        repository_id="repo",
        sequence=sequence,
        events=tuple(events),  # type: ignore[arg-type]
    )


def test_closed_combination_matrix_rejects_wildcards() -> None:
    with pytest.raises(ValueError, match="illegal runtime event combination"):
        _event("e:overlay-update", entity_type="overlay", operation="update")
    with pytest.raises(ValueError, match="illegal runtime event combination"):
        _event("e:checkpoint-delete", graph_type="system", entity_type="checkpoint", operation="delete")
    assert ("solver", "overlay", "version") in LEGAL_COMBINATIONS


def test_entity_id_aliasing_rejected() -> None:
    import hashlib
    import json

    from memorii.core.persistence.runtime_events import RuntimeEventEnvelope

    payload = json.dumps(
        {
            "envelope": "memorii.runtime-event-envelope.v1",
            "event_id": "e:alias",
            "dedupe_key": "dk:alias",
            "graph_type": "solver",
            "entity_type": "node",
            "operation": "create",
            "entity_id": "node:one",
            "entity": {"id": "node:one"},
            "metadata_version": 1,
            "is_candidate": False,
            "task_id": "task:one",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(
        b"memorii.runtime-event-envelope.v1\x00" + payload.encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="equal record ids"):
        RuntimeEventEnvelope.model_validate(
            {
                "event_id": "e:alias",
                "dedupe_key": "dk:alias",
                "graph_type": "solver",
                "entity_type": "node",
                "operation": "create",
                "entity_id": "node:one",
                "record_id": "node:DIFFERENT",
                "entity": {"id": "node:one"},
                "metadata_version": 1,
                "is_candidate": False,
                "is_committed": True,
                "task_id": "task:one",
                "solver_run_id": "solver:one",
                "event_digest": digest,
            }
        )


def test_full_state_required_id_only_events_rejected() -> None:
    with pytest.raises(ValueError, match="full state"):
        create_runtime_event(
            event_id="e:id-only",
            dedupe_key="dk:id-only",
            graph_type="solver",
            entity_type="node",
            operation="create",
            entity_id="node:x",
            entity={},
            metadata_version=1,
            task_id="task:one",
        )


def test_replay_orders_by_batch_position_not_timestamps() -> None:
    first = _batch(1, (_event("e:1", version=1, statement="first"),))
    second = _batch(2, (_event("e:2", version=1, statement="second"),))
    state = replay_runtime_batches((first, second))
    assert list(state.solver_nodes) == ["solver:one:e:1", "solver:one:e:2"]
    with pytest.raises(RuntimeReplayError, match="gap"):
        replay_runtime_batches((second, first))


def test_identical_redelivery_is_idempotent_divergent_reuse_fails() -> None:
    event = _event("e:1", version=1)
    first = _batch(1, (event,))
    state = replay_runtime_batches((first,))
    again = reduce_runtime_batch(state, first)
    assert again == state  # byte-identical batch: no state change
    divergent = _event("e:1-divergent", dedupe_key="dk:e:1", version=1, statement="other")
    with pytest.raises(RuntimeReplayError, match="memory_integrity_conflict"):
        reduce_runtime_batch(state, _batch(2, (divergent,)))


def test_equal_version_non_identical_envelopes_fail_closed() -> None:
    one = _event("e:1", version=2, statement="alpha")
    state = reduce_runtime_batch(RuntimeReplayState(), _batch(1, (one,)))
    conflicting = _event("e:2", entity_id="e:1", version=2, statement="beta")
    with pytest.raises(RuntimeReplayError, match="memory_integrity_conflict"):
        reduce_runtime_batch(state, _batch(2, (conflicting,)))


def test_delete_is_logical_retirement_and_older_versions_ignored() -> None:
    created = _event("e:1", version=1)
    retired = _event("e:1-delete", entity_id="e:1", version=2, operation="delete", dedupe_key="dk:delete")
    state = reduce_runtime_batch(
        RuntimeReplayState(), _batch(1, (created, retired))
    )
    assert state.solver_nodes["solver:one:e:1"]["deleted"] is True
    stale = _event("e:3", version=1, statement="stale rewrite")
    state = reduce_runtime_batch(state, _batch(2, (stale,)))
    assert state.solver_nodes["solver:one:e:1"]["deleted"] is True


def test_reference_reducer_agrees_on_materialized_state() -> None:
    """Independently authored replay: naive arrival-order application."""

    def reference_replay(batches: tuple[RuntimeEventBatch, ...]) -> dict[str, dict[str, object]]:
        nodes: dict[str, dict[str, object]] = {}
        seen_events: set[str] = set()
        seen_dedupe: set[str] = set()
        for sequence, batch in enumerate(batches, start=1):
            assert batch.sequence == sequence
            for event in batch.events:
                if event.event_id in seen_events:
                    continue
                assert event.dedupe_key not in seen_dedupe
                seen_events.add(event.event_id)
                seen_dedupe.add(event.dedupe_key)
                key = f"{event.solver_run_id}:{event.entity_id}" if event.solver_run_id else event.entity_id
                if event.operation == "delete":
                    entry = dict(nodes.get(key, event.entity))
                    entry["deleted"] = True
                    nodes[key] = entry
                else:
                    nodes[key] = dict(event.entity)
        return nodes

    batches = (
        _batch(1, (_event("e:1", version=1, statement="first"),)),
        _batch(
            2,
            (
                _event("e:2", version=1, statement="second"),
                _event("e:3", version=1, statement="third"),
            ),
        ),
        _batch(3, (_event("e:2-delete", entity_id="e:2", version=2, operation="delete", dedupe_key="dk:d2"),)),
    )
    production = replay_runtime_batches(batches)
    reference = reference_replay(batches)
    assert production.solver_nodes == reference


def test_business_label_inventory_is_complete() -> None:
    from memorii.core.persistence.runtime_events import EVENT_BUSINESS_LABELS

    assert {
        "task_paused",
        "task_completed",
        "task_aborted",
        "node_merged",
        "node_reopened",
        "belief_updated",
        "justification_invalidated",
        "status_updated",
        "action_completed",
        "observation_received",
        "checkpoint_recorded",
        "consolidation_recorded",
    } <= EVENT_BUSINESS_LABELS


def test_event_id_reuse_with_different_envelope_fails_closed() -> None:
    first = _batch(1, (_event("e:1", version=1, statement="alpha"),))
    state = replay_runtime_batches((first,))
    reused = create_runtime_event(
        event_id="e:1",
        dedupe_key="dk:reused",
        graph_type="solver",
        entity_type="node",
        operation="update",
        entity_id="e:1",
        entity={"id": "e:1", "version": 2, "statement": "beta"},
        metadata_version=2,
        task_id="task:one",
        solver_run_id="solver:one",
    )
    with pytest.raises(RuntimeReplayError, match="reused with a different envelope"):
        reduce_runtime_batch(state, _batch(2, (reused,)))
