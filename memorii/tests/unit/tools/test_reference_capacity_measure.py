"""Small real-owner proofs for the installed capacity measurement driver."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from memorii.core.storage_administration.service import StorageAdministrationService
from tests.support import reference_capacity, reference_capacity_fixture, reference_capacity_profile
from tests.support.reference_capacity import FIXTURE_START, EventFillInput, TaskAllocation
from tests.support.reference_capacity_fixture import ReferenceFixtureError, _prepare
from tests.support.reference_capacity_measure import Measurement, _cold, _summarize, _warm


@pytest.fixture(params=[False, True], ids=["default-format", "staged-raw-format"])
def capacity_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> Path:
    raw_payloads = request.param is True
    monkeypatch.setattr(reference_capacity_fixture, "EVENT_COUNT", 29)
    monkeypatch.setattr(reference_capacity_fixture, "CHECKPOINT_TAIL_COUNT", 2)
    monkeypatch.setattr(reference_capacity, "COLD_SAMPLE_COUNT", 1)
    monkeypatch.setattr(reference_capacity, "WARMUP_COUNT", 1)
    monkeypatch.setattr(reference_capacity, "WARM_SAMPLE_COUNT", 2)

    def fill(mandatory: int) -> list[EventFillInput]:
        assert mandatory == (26 if raw_payloads else 25)
        return [
            EventFillInput(
                ordinal=index, task_id=task.task_id, timestamp=FIXTURE_START + timedelta(seconds=index),
                kind="status_update", checkpoint_tail=index >= 27,
            ) for index in range(mandatory, 29)
        ]

    base = tmp_path / "frozen"
    task = TaskAllocation("concentrated", 0, 3, 9, 0, 0, 2)
    _prepare(base, "concentrated", (task,), fill=fill, raw_payloads=raw_payloads)
    return base


def test_warm_series_and_growth_have_exact_attempts_and_leave_base_unchanged(capacity_base: Path) -> None:
    with StorageAdministrationService(capacity_base) as service:
        database = service.partition_path()
    initial = database.read_bytes()
    for operation in reference_capacity.WARM_OPERATIONS:
        report = _warm(capacity_base, capacity_base.parent, "concentrated", operation, contended=False)
        # This fixture proves call routing and sample accounting. Host time is
        # deliberately outside the assertion for this small test fixture.
        assert (report["attempted"], report["warmup_attempted"], report["errors"]) == (2, 1, 0), report
    growth = _warm(
        capacity_base, capacity_base.parent, "concentrated", "command_commit", contended=False, growth=True,
    )
    assert (growth["attempted"], growth["warmup_attempted"], growth["errors"]) == (2, 0, 0), growth
    growth_bytes = growth["database_and_wal_bytes_growth"]
    assert isinstance(growth_bytes, int) and growth_bytes > 0
    assert database.read_bytes() == initial


def test_cold_samples_use_child_and_report_reopen_genesis_and_backup_pause(capacity_base: Path) -> None:
    for operation in reference_capacity.COLD_OPERATIONS:
        report = _cold(capacity_base, capacity_base.parent, "concentrated", operation)
        assert (report["attempted"], report["errors"]) == (1, 0), report
        samples = report["samples"]
        assert isinstance(samples, list)
        sample, = samples
        assert sample["elapsed_ns"] > 0
        assert sample["reopen_ns"] > 0
        if operation == "checkpoint_resume":
            assert sample["checkpoint_replay_ns"] > 0
            assert sample["genesis_replay_ns"] > 0


@pytest.mark.parametrize(
    ("last_ns", "status"),
    [(10_999_999_999, "passed"), (11_000_000_000, "passed"), (11_000_000_001, "failed")],
)
def test_startup_acquisition_budget_includes_the_tenth_sample(last_ns: int, status: str) -> None:
    samples = [Measurement(str(index), 100_000_000) for index in range(9)]
    samples.append(Measurement("slowest", last_ns))
    report = _summarize("startup_acquisition", samples)
    assert (report["budget_ms"], report["status"]) == (11_000, status)
    quantiles = report["quantiles"]
    assert isinstance(quantiles, dict) and quantiles["p95_ms"] == last_ns / 1_000_000


def test_failed_or_unavailable_samples_cannot_pass_p95_budget() -> None:
    failed = _summarize("state_read", [Measurement("failure", None, "busy"), Measurement("pass", 10)])
    assert (failed["attempted"], failed["errors"], failed["status"]) == (2, 1, "failed")
    assert _summarize("command_commit", [], unavailable="endpoint missing")["status"] == "unavailable"


def test_profile_denies_wrong_os_and_unattested_dedicated_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reference_capacity_profile.platform, "system", lambda: "Linux")
    with pytest.raises(ReferenceFixtureError, match="requires Darwin"):
        reference_capacity_profile.verify_profile("macos", tmp_path, dedicated_idle=True)
    with pytest.raises(ReferenceFixtureError, match="otherwise idle"):
        reference_capacity_profile.verify_profile("linux", tmp_path, dedicated_idle=False)
