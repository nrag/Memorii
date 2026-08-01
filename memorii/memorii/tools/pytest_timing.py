"""Pytest plugin that records exact per-node wall-clock durations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol


class _Parser(Protocol):
    def getgroup(self, name: str) -> _OptionGroup: ...


class _OptionGroup(Protocol):
    def addoption(self, *names: str, **attributes: object) -> None: ...


class _Config(Protocol):
    def getoption(self, name: str) -> str | None: ...


class _Session(Protocol):
    config: _Config


class _Report(Protocol):
    nodeid: str
    when: str
    duration: float


_durations: dict[str, float] = {}


def pytest_addoption(parser: _Parser) -> None:
    group = parser.getgroup("memorii timing")
    group.addoption(
        "--memorii-timing-output",
        action="store",
        default=None,
        help="Write exact per-node durations as canonical JSON.",
    )
    group.addoption("--memorii-shard-index", action="store", type=int, default=None)
    group.addoption("--memorii-plan-digest", action="store", default=None)


def pytest_runtest_logreport(report: _Report) -> None:
    if report.when in {"setup", "call", "teardown"}:
        _durations[report.nodeid] = _durations.get(report.nodeid, 0.0) + report.duration


def pytest_sessionfinish(session: _Session, exitstatus: int) -> None:
    output = session.config.getoption("memorii_timing_output")
    if output is None:
        return
    payload = {
        "schema_version": 1,
        "exit_status": exitstatus,
        "shard_index": session.config.getoption("memorii_shard_index"),
        "plan_digest": session.config.getoption("memorii_plan_digest"),
        "tests": {nodeid: round(duration, 6) for nodeid, duration in sorted(_durations.items())},
    }
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
