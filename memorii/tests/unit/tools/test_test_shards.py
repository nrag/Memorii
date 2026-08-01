from __future__ import annotations

import json
from pathlib import Path

import pytest
from memorii.tools.test_shards import (
    build_plan,
    load_config,
    load_durations,
    merge_timing_manifests,
    plan_digest,
    validate_plan,
    validate_timing_evidence,
)


def test_duration_balancing_is_deterministic_complete_and_disjoint() -> None:
    nodeids = ("tests/a.py::slow", "tests/a.py::medium", "tests/b.py::fast", "tests/c.py::new")
    durations = {
        "tests/a.py::slow": 9.0,
        "tests/a.py::medium": 4.0,
        "tests/b.py::fast": 1.0,
    }

    first = build_plan(nodeids, durations, shard_count=2)
    second = build_plan(tuple(reversed(nodeids)), durations, shard_count=2)

    validate_plan(first, nodeids)
    assert first == second
    assert first.measured_count == 3
    assert max(first.estimated_seconds) == 13.0
    assert any(
        {"tests/a.py::slow", "tests/a.py::medium"} <= set(shard)
        for shard in first.nodeids
    )


def test_validate_plan_rejects_duplicate_or_missing_ownership() -> None:
    plan = build_plan(("tests/a.py::one", "tests/a.py::two"), {}, shard_count=2)
    duplicate = plan.__class__(
        nodeids=(("tests/a.py::one",), ("tests/a.py::one",)),
        estimated_seconds=plan.estimated_seconds,
        measured_count=0,
        default_duration=1.0,
    )

    with pytest.raises(ValueError, match="more than once"):
        validate_plan(duplicate, ("tests/a.py::one", "tests/a.py::two"))


def test_config_and_manifest_fail_closed_for_invalid_shapes(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"schema_version": 1, "shard_count": 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="shard_count"):
        load_config(config)

    manifest = tmp_path / "durations.json"
    manifest.write_text(json.dumps({"schema_version": 1, "tests": {"node": -1}}), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid duration"):
        load_durations(manifest)


def test_timing_merge_is_complete_conservative_and_rejects_failed_runs(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(
        json.dumps({"schema_version": 1, "exit_status": 0, "tests": {"a": 1.0, "b": 2.0}}),
        encoding="utf-8",
    )
    second.write_text(
        json.dumps({"schema_version": 1, "exit_status": 0, "tests": {"b": 3.0, "c": 1.0}}),
        encoding="utf-8",
    )
    assert merge_timing_manifests((first, second)) == {"a": 1.0, "b": 3.0, "c": 1.0}

    second.write_text(
        json.dumps({"schema_version": 1, "exit_status": 1, "tests": {"c": 1.0}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unsuccessful timing evidence"):
        merge_timing_manifests((first, second))


def test_timing_evidence_requires_every_disjoint_shard_and_current_plan(tmp_path: Path) -> None:
    nodeids = ("tests/a.py::one", "tests/b.py::two")
    plan = build_plan(nodeids, {nodeid: 1.0 for nodeid in nodeids}, shard_count=2)
    digest = plan_digest(plan)
    paths: list[Path] = []
    for index, shard in enumerate(plan.nodeids):
        path = tmp_path / f"shard-{index}.json"
        path.write_text(
            json.dumps({
                "schema_version": 1,
                "exit_status": 0,
                "shard_index": index,
                "plan_digest": digest,
                "tests": {nodeid: 1.0 for nodeid in shard},
            }),
            encoding="utf-8",
        )
        paths.append(path)

    assert validate_timing_evidence(
        tuple(paths),
        expected_shard_count=2,
        expected_plan_digest=digest,
        expected_nodeids=nodeids,
    ) == {nodeid: 1.0 for nodeid in nodeids}

    with pytest.raises(ValueError, match="expected 2 shard"):
        validate_timing_evidence(
            (paths[0],),
            expected_shard_count=2,
            expected_plan_digest=digest,
            expected_nodeids=nodeids,
        )
    with pytest.raises(ValueError, match="duplicate shard index"):
        validate_timing_evidence(
            (paths[0], paths[0]),
            expected_shard_count=2,
            expected_plan_digest=digest,
            expected_nodeids=nodeids,
        )

    overlapping = json.loads(paths[1].read_text(encoding="utf-8"))
    overlapping["tests"] = {**overlapping["tests"], **json.loads(paths[0].read_text(encoding="utf-8"))["tests"]}
    paths[1].write_text(json.dumps(overlapping), encoding="utf-8")
    with pytest.raises(ValueError, match="overlapping timing evidence"):
        validate_timing_evidence(
            tuple(paths),
            expected_shard_count=2,
            expected_plan_digest=digest,
            expected_nodeids=nodeids,
        )

    stale = json.loads(paths[1].read_text(encoding="utf-8"))
    stale["tests"] = {nodeid: 1.0 for nodeid in plan.nodeids[1]}
    stale["plan_digest"] = "0" * 64
    paths[1].write_text(json.dumps(stale), encoding="utf-8")
    with pytest.raises(ValueError, match="stale shard plan digest"):
        validate_timing_evidence(
            tuple(paths),
            expected_shard_count=2,
            expected_plan_digest=digest,
            expected_nodeids=nodeids,
        )
