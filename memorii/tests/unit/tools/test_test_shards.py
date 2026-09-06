from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from memorii.tools.test_shards import (
    build_plan,
    collect_nodeids,
    load_config,
    load_durations,
    merge_timing_manifests,
    plan_digest,
    shard_pytest_command,
    validate_plan,
    validate_timing_evidence,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_duration_balancing_is_deterministic_complete_and_disjoint() -> None:
    nodeids = ("tests/a.py::slow", "tests/a.py::medium", "tests/b.py::fast", "tests/c.py::new")
    durations = {
        "tests/a.py::slow": 9.0,
        "tests/a.py::medium": 4.0,
        "tests/b.py::fast": 1.0,
    }

    first = build_plan(nodeids, durations, shard_count=2, assignment_scope="node")
    second = build_plan(
        tuple(reversed(nodeids)),
        durations,
        shard_count=2,
        assignment_scope="node",
    )

    validate_plan(first, nodeids)
    assert first == second
    assert first.measured_count == 3
    assert max(first.estimated_seconds) == 9.0
    assert not any(
        {"tests/a.py::slow", "tests/a.py::medium"} <= set(shard)
        for shard in first.nodeids
    )


def test_shard_command_executes_exact_nodes_without_file_expansion(tmp_path: Path) -> None:
    nodeids = (
        "tests/a.py::test_case[value with spaces]",
        "tests/a.py::test_other",
        "tests/b.py::test_third",
    )
    plan = build_plan(
        nodeids,
        {nodeid: float(index) for index, nodeid in enumerate(nodeids, start=1)},
        shard_count=2,
        assignment_scope="node",
    )
    output = tmp_path / "timing.json"

    command = shard_pytest_command(
        plan,
        index=0,
        timing_output=output,
        assignment_scope="node",
    )

    assert command[:5] == [
        command[0],
        "-m",
        "pytest",
        "-W",
        "error",
    ]
    assert set(plan.nodeids[0]) <= set(command)
    assert not set(plan.nodeids[1]).intersection(command)
    assert "tests/a.py" not in command
    assert f"--memorii-timing-output={output}" in command
    assert f"--memorii-plan-digest={plan_digest(plan)}" in command


def test_file_scope_is_default_and_executes_each_owned_file_once(tmp_path: Path) -> None:
    nodeids = (
        "tests/a.py::slow",
        "tests/a.py::medium",
        "tests/b.py::fast",
    )
    plan = build_plan(
        nodeids,
        {"tests/a.py::slow": 9.0, "tests/a.py::medium": 4.0, "tests/b.py::fast": 1.0},
        shard_count=2,
    )
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({
            "pytest_args": ["tests"],
            "schema_version": 1,
            "shard_count": 2,
            "target_seconds": 30,
            "timing_manifest": "durations.json",
        }),
        encoding="utf-8",
    )
    config = load_config(config_path)

    commands = [
        shard_pytest_command(
            plan,
            index=index,
            timing_output=None,
            assignment_scope=config.assignment_scope,
        )
        for index in range(2)
    ]

    assert config.assignment_scope == "file"
    assert any(
        {"tests/a.py::slow", "tests/a.py::medium"} <= set(shard)
        for shard in plan.nodeids
    )
    targets = [target for command in commands for target in command[5:-2]]
    assert sorted(targets) == ["tests/a.py", "tests/b.py"]


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

    config.write_text(
        json.dumps({
            "schema_version": 1,
            "shard_count": 2,
            "target_seconds": 1,
            "pytest_args": ["tests/unit"],
            "timing_manifest": "durations.json",
            "assignment_scope": "module",
        }),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="assignment_scope"):
        load_config(config)

    config.write_text(
        json.dumps({
            "schema_version": 1,
            "shard_count": 2,
            "target_seconds": 1,
            "pytest_args": ["tests/unit"],
            "timing_manifest": "durations.json",
        }),
        encoding="utf-8",
    )
    assert load_config(config).assignment_scope == "file"

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

    for invalid_status in (None, "0", False):
        payload = {"schema_version": 1, "tests": {"c": 1.0}}
        if invalid_status is not None:
            payload["exit_status"] = invalid_status
        second.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match="unsuccessful timing evidence"):
            merge_timing_manifests((first, second))


@pytest.mark.parametrize(
    ("missing_field", "message"),
    [
        ("exit_status", "cannot merge unsuccessful timing evidence"),
        ("shard_index", "invalid shard index in timing evidence"),
        ("plan_digest", "stale shard plan digest in timing evidence"),
    ],
)
def test_merge_cli_rejects_timing_artifact_without_required_metadata(
    tmp_path: Path,
    missing_field: str,
    message: str,
) -> None:
    selector = ("tests/unit/tools/test_test_shards.py",)
    nodeids = collect_nodeids(selector, cwd=PROJECT_ROOT)
    durations = {nodeid: 1.0 for nodeid in nodeids}
    plan = build_plan(nodeids, durations, shard_count=2)
    timing_manifest = tmp_path / "durations.json"
    timing_manifest.write_text(
        json.dumps({
            "schema_version": 1,
            "tests": durations,
        }),
        encoding="utf-8",
    )
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({
            "assignment_scope": "file",
            "pytest_args": list(selector),
            "schema_version": 1,
            "shard_count": 2,
            "target_seconds": 1000,
            "timing_manifest": timing_manifest.name,
        }),
        encoding="utf-8",
    )
    digest = plan_digest(plan)
    artifacts: list[Path] = []
    for index, shard in enumerate(plan.nodeids):
        artifact = tmp_path / f"shard-{index}.json"
        payload = {
            "exit_status": 0,
            "plan_digest": digest,
            "schema_version": 1,
            "shard_index": index,
            "tests": {nodeid: 1.0 for nodeid in shard},
        }
        if index == 0:
            del payload[missing_field]
        artifact.write_text(json.dumps(payload), encoding="utf-8")
        artifacts.append(artifact)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "memorii.tools.test_shards",
            "merge",
            "--config",
            str(config),
            "--input",
            str(artifacts[0]),
            "--input",
            str(artifacts[1]),
            "--output",
            str(tmp_path / "merged.json"),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert message in completed.stderr


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
