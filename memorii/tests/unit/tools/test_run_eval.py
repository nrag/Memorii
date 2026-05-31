from __future__ import annotations

import json
from pathlib import Path

import pytest

from memorii.tools.run_eval import main


def _clear_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [
        "MEMORII_LLM_PROVIDER",
        "MEMORII_LLM_MODEL",
        "OPENAI_API_KEY",
        "MEMORII_ENABLE_LIVE_LLM_TESTS",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MEMORII_LLM_PROVIDER", "none")


def test_run_eval_routes_memory_lifecycle_suite(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _clear_llm_env(monkeypatch)
    assert main(["--suite", "memory_lifecycle_v1", "--storage-root", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "suite=memory_lifecycle_v1" in output
    assert "memorii_cases=11" in output
    assert "lifecycle_failed=0" in output
    assert "llm_calls=0" in output


def test_run_eval_routes_promotion_belief_decision_suite(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_llm_env(monkeypatch)

    assert main(
        [
            "--suite",
            "promotion_belief_v1",
            "--mode",
            "rule",
            "--storage-root",
            str(tmp_path),
        ]
    ) == 0

    run_dir = sorted((tmp_path / "eval_runs" / "llm").glob("*/*"))[-1]
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert payload["total_cases"] == 61


def test_run_eval_routes_belief_only_decision_suite(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_llm_env(monkeypatch)

    main(["--suite", "belief_v1", "--mode", "rule", "--storage-root", str(tmp_path)])

    run_dir = sorted((tmp_path / "eval_runs" / "llm").glob("*/*"))[-1]
    snapshots = (run_dir / "inputs" / "snapshots.jsonl").read_text(encoding="utf-8").splitlines()
    assert snapshots
    assert all(json.loads(line)["decision_point"] == "belief_update" for line in snapshots)


def test_run_eval_lifecycle_llm_mode_requires_live_gate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _clear_llm_env(monkeypatch)
    with pytest.raises(SystemExit, match="Refusing"):
        main(
            [
                "--suite",
                "memory_lifecycle_v1",
                "--mode",
                "llm",
                "--storage-root",
                str(tmp_path),
            ]
        )


def test_run_eval_lifecycle_dry_run_llm_mode_traces_calls(tmp_path: Path) -> None:
    assert main(
        [
            "--suite",
            "memory_lifecycle_v1",
            "--mode",
            "llm",
            "--dry-run",
            "--storage-root",
            str(tmp_path),
        ]
    ) == 0

    run_dir = sorted((tmp_path / "benchmark_runs" / "memory_lifecycle_v1" / "llm").glob("bench-*"))[-1]
    assert len((run_dir / "llm_traces.jsonl").read_text(encoding="utf-8").splitlines()) == 11


def test_run_eval_auto_lifecycle_uses_hybrid_when_llm_configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MEMORII_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    assert main(["--suite", "memory_lifecycle_v1", "--dry-run", "--storage-root", str(tmp_path)]) == 0

    run_dir = sorted((tmp_path / "benchmark_runs" / "memory_lifecycle_v1" / "auto").glob("bench-*"))[-1]
    assert len((run_dir / "llm_traces.jsonl").read_text(encoding="utf-8").splitlines()) == 11


def test_run_eval_rejects_systems_for_decision_suite() -> None:
    with pytest.raises(SystemExit, match="does not support --systems"):
        main(["--suite", "promotion_belief_v1", "--systems", "all"])


def test_run_eval_default_suite_runs_promotion_belief_and_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _clear_llm_env(monkeypatch)

    assert main(["--mode", "rule", "--storage-root", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "suite=promotion_belief_v1 status=starting" in output
    assert "suite=promotion_belief_v1 status=finished exit_code=0" in output
    assert "suite=memory_lifecycle_v1 status=starting" in output
    assert "suite=memory_lifecycle_v1 status=finished exit_code=0" in output
    assert "mode=rule total_cases=61" in output
    assert "suite=memory_lifecycle_v1" in output
    assert (tmp_path / "eval_runs" / "llm").exists()
    assert (tmp_path / "benchmark_runs" / "memory_lifecycle_v1" / "rule").exists()


def test_run_eval_suite_all_runs_promotion_belief_and_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _clear_llm_env(monkeypatch)

    assert main(["--suite", "all", "--mode", "rule", "--storage-root", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "suite=promotion_belief_v1 status=starting" in output
    assert "suite=memory_lifecycle_v1 status=starting" in output
    assert "mode=rule total_cases=61" in output
    assert "suite=memory_lifecycle_v1" in output
