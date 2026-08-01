"""Deterministic duration-balanced pytest shard planner and runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ShardConfig:
    shard_count: int
    target_seconds: float
    pytest_args: tuple[str, ...]
    timing_manifest: Path


@dataclass(frozen=True)
class ShardPlan:
    nodeids: tuple[tuple[str, ...], ...]
    estimated_seconds: tuple[float, ...]
    measured_count: int
    default_duration: float


def load_config(path: Path) -> ShardConfig:
    payload = _load_json_object(path)
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported shard config schema_version")
    shard_count = payload.get("shard_count")
    target_seconds = payload.get("target_seconds")
    pytest_args = payload.get("pytest_args")
    timing_manifest = payload.get("timing_manifest")
    if not isinstance(shard_count, int) or isinstance(shard_count, bool) or shard_count < 2:
        raise ValueError("shard_count must be an integer of at least 2")
    if not isinstance(target_seconds, (int, float)) or isinstance(target_seconds, bool) or target_seconds <= 0:
        raise ValueError("target_seconds must be positive")
    if not isinstance(pytest_args, list) or not pytest_args or not all(isinstance(item, str) for item in pytest_args):
        raise ValueError("pytest_args must be a non-empty string array")
    if not isinstance(timing_manifest, str) or not timing_manifest:
        raise ValueError("timing_manifest must be a non-empty path")
    return ShardConfig(
        shard_count=shard_count,
        target_seconds=float(target_seconds),
        pytest_args=tuple(pytest_args),
        timing_manifest=(path.parent / timing_manifest).resolve(),
    )


def load_durations(path: Path) -> dict[str, float]:
    payload = _load_json_object(path)
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported timing manifest schema_version")
    tests = payload.get("tests")
    if not isinstance(tests, dict):
        raise ValueError("timing manifest tests must be an object")
    durations: dict[str, float] = {}
    for nodeid, duration in tests.items():
        if not isinstance(nodeid, str) or not nodeid:
            raise ValueError("timing manifest node IDs must be non-empty strings")
        if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration < 0:
            raise ValueError(f"invalid duration for {nodeid}")
        durations[nodeid] = float(duration)
    return durations


def merge_timing_manifests(paths: tuple[Path, ...]) -> dict[str, float]:
    if not paths:
        raise ValueError("at least one timing manifest is required")
    merged: dict[str, float] = {}
    for path in paths:
        payload = _load_json_object(path)
        if payload.get("exit_status", 0) != 0:
            raise ValueError(f"cannot merge unsuccessful timing evidence: {path}")
        for nodeid, duration in load_durations(path).items():
            merged[nodeid] = max(duration, merged.get(nodeid, 0.0))
    return merged


def validate_timing_evidence(
    paths: tuple[Path, ...],
    *,
    expected_shard_count: int,
    expected_plan_digest: str,
    expected_nodeids: tuple[str, ...],
) -> dict[str, float]:
    if len(paths) != expected_shard_count:
        raise ValueError(f"expected {expected_shard_count} shard timing artifacts, received {len(paths)}")
    seen_indices: set[int] = set()
    seen_nodeids: set[str] = set()
    for path in paths:
        payload = _load_json_object(path)
        index = payload.get("shard_index")
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < expected_shard_count:
            raise ValueError(f"invalid shard index in timing evidence: {path}")
        if index in seen_indices:
            raise ValueError(f"duplicate shard index in timing evidence: {index}")
        seen_indices.add(index)
        if payload.get("plan_digest") != expected_plan_digest:
            raise ValueError(f"stale shard plan digest in timing evidence: {path}")
        current = set(load_durations(path))
        overlap = seen_nodeids.intersection(current)
        if overlap:
            raise ValueError(f"overlapping timing evidence for {sorted(overlap)[0]}")
        seen_nodeids.update(current)
    if seen_nodeids != set(expected_nodeids):
        missing = sorted(set(expected_nodeids) - seen_nodeids)
        extra = sorted(seen_nodeids - set(expected_nodeids))
        raise ValueError(f"timing evidence coverage mismatch: missing={missing[:3]} extra={extra[:3]}")
    return merge_timing_manifests(paths)


def collect_nodeids(pytest_args: tuple[str, ...], *, cwd: Path) -> tuple[str, ...]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *pytest_args, "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pytest collection failed:\n{result.stdout}{result.stderr}")
    nodeids = tuple(line for line in result.stdout.splitlines() if line.startswith("tests/") and "::" in line)
    if not nodeids:
        raise RuntimeError("pytest collection returned no test node IDs")
    if len(nodeids) != len(set(nodeids)):
        raise RuntimeError("pytest collection returned duplicate test node IDs")
    return nodeids


def build_plan(nodeids: tuple[str, ...], durations: dict[str, float], shard_count: int) -> ShardPlan:
    nodeid_set = set(nodeids)
    known = sorted(duration for nodeid, duration in durations.items() if nodeid in nodeid_set and duration > 0)
    default_duration = known[len(known) // 2] if known else 1.0
    files: dict[str, list[str]] = {}
    for nodeid in nodeids:
        files.setdefault(nodeid.split("::", maxsplit=1)[0], []).append(nodeid)
    weighted_files = [
        (path, sum(durations.get(nodeid, default_duration) for nodeid in members), tuple(sorted(members)))
        for path, members in files.items()
    ]
    weighted_files.sort(key=lambda item: (-item[1], item[0]))
    assignments: list[list[str]] = [[] for _ in range(shard_count)]
    totals = [0.0] * shard_count
    for _path, duration, members in weighted_files:
        index = min(range(shard_count), key=lambda candidate: (totals[candidate], candidate))
        assignments[index].extend(members)
        totals[index] += duration
    return ShardPlan(
        nodeids=tuple(tuple(sorted(items)) for items in assignments),
        estimated_seconds=tuple(totals),
        measured_count=sum(nodeid in durations for nodeid in nodeids),
        default_duration=default_duration,
    )


def validate_plan(plan: ShardPlan, expected: tuple[str, ...]) -> None:
    flattened = [nodeid for shard in plan.nodeids for nodeid in shard]
    if len(flattened) != len(set(flattened)):
        raise ValueError("shard plan assigns at least one test more than once")
    if set(flattened) != set(expected):
        missing = sorted(set(expected) - set(flattened))
        extra = sorted(set(flattened) - set(expected))
        raise ValueError(f"shard plan coverage mismatch: missing={missing[:3]} extra={extra[:3]}")


def plan_digest(plan: ShardPlan) -> str:
    payload = json.dumps(plan.nodeids, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _plan(config_path: Path, *, cwd: Path) -> tuple[ShardConfig, ShardPlan, tuple[str, ...]]:
    config = load_config(config_path)
    nodeids = collect_nodeids(config.pytest_args, cwd=cwd)
    durations = load_durations(config.timing_manifest)
    plan = build_plan(nodeids, durations, config.shard_count)
    validate_plan(plan, nodeids)
    return config, plan, nodeids


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify", "run", "merge"))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--index", type=int)
    parser.add_argument("--timing-output", type=Path)
    parser.add_argument("--input", type=Path, action="append", default=[])
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "merge":
        if args.output is None:
            raise SystemExit("merge requires --output")
        inputs = list(args.input)
        if args.input_dir is not None:
            inputs.extend(sorted(args.input_dir.glob("*.json")))
        if args.config is None:
            raise SystemExit("merge requires --config")
        config, plan, nodeids = _plan(args.config.resolve(), cwd=Path.cwd())
        merged = validate_timing_evidence(
            tuple(inputs),
            expected_shard_count=config.shard_count,
            expected_plan_digest=plan_digest(plan),
            expected_nodeids=nodeids,
        )
        args.output.write_text(
            json.dumps({"schema_version": 1, "tests": merged}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"merged": len(merged)}, sort_keys=True))
        return 0
    if args.config is None:
        raise SystemExit(f"{args.command} requires --config")
    cwd = Path.cwd()
    config, plan, nodeids = _plan(args.config.resolve(), cwd=cwd)
    summary = {
        "collected": len(nodeids),
        "measured": plan.measured_count,
        "default_duration": round(plan.default_duration, 6),
        "estimated_seconds": [round(value, 3) for value in plan.estimated_seconds],
        "counts": [len(items) for items in plan.nodeids],
        "target_seconds": config.target_seconds,
    }
    print(json.dumps(summary, sort_keys=True))
    if args.command == "verify":
        if max(plan.estimated_seconds) > config.target_seconds:
            raise SystemExit("estimated shard runtime exceeds target_seconds")
        return 0
    if args.index is None or not 0 <= args.index < config.shard_count:
        raise SystemExit(f"--index must be between 0 and {config.shard_count - 1}")
    shard_files = sorted({nodeid.split("::", maxsplit=1)[0] for nodeid in plan.nodeids[args.index]})
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-W",
        "error",
        *shard_files,
        "-p",
        "no:cacheprovider",
    ]
    if args.timing_output is not None:
        command.extend([
            "-p",
            "memorii.tools.pytest_timing",
            f"--memorii-timing-output={args.timing_output}",
            f"--memorii-shard-index={args.index}",
            f"--memorii-plan-digest={plan_digest(plan)}",
        ])
    return subprocess.run(command, cwd=cwd, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
