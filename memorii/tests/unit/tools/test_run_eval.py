from __future__ import annotations

import json
from pathlib import Path

import pytest

from memorii.tools.run_eval import main


def _summary_fields(output: str, *, suite: str) -> dict[str, str]:
    for line in output.splitlines():
        if f"suite={suite} " not in line:
            continue
        fields: dict[str, str] = {}
        for part in line.strip().split():
            if "=" not in part:
                continue
            key, value = part.split("=", maxsplit=1)
            fields[key] = value
        return fields
    raise AssertionError(f"summary line for {suite} not found in output: {output}")


def _jsonl_count(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    return len(text.splitlines()) if text else 0


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
    run_dir = sorted((tmp_path / "benchmark_runs" / "memory_lifecycle_v1" / "auto").glob("bench-*"))[-1]
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    fields = _summary_fields(output, suite="memory_lifecycle_v1")

    assert int(fields["scenarios"]) == payload["summary"]["scenario_fixtures_total"]
    assert int(fields["memorii_runs"]) == payload["summary"]["memorii_runs_total"]
    assert int(fields["memorii_runs_failed"]) == payload["summary"]["memorii_runs_failed"]
    assert int(fields["llm_calls"]) == 0


def test_run_eval_routes_retrieval_corruption_suite(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _clear_llm_env(monkeypatch)
    assert main(["--suite", "retrieval_corruption_v1", "--storage-root", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    run_dir = sorted((tmp_path / "benchmark_runs" / "retrieval_corruption_v1" / "auto").glob("bench-*"))[-1]
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    fields = _summary_fields(output, suite="retrieval_corruption_v1")

    assert int(fields["scenarios"]) == payload["summary"]["scenario_fixtures_total"]
    assert int(fields["memorii_runs"]) == payload["summary"]["memorii_runs_total"]
    assert int(fields["memorii_runs_passed"]) == payload["summary"]["memorii_runs_passed"]
    assert int(fields["llm_calls"]) == _jsonl_count(run_dir / "llm_traces.jsonl")


def test_run_eval_routes_execution_graph_suite(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _clear_llm_env(monkeypatch)
    assert main(["--suite", "execution_graph_v1", "--storage-root", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    run_dir = sorted((tmp_path / "benchmark_runs" / "execution_graph_v1" / "auto").glob("bench-*"))[-1]
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    fields = _summary_fields(output, suite="execution_graph_v1")

    assert int(fields["execution_cases"]) == len(payload["scenario_results"])
    assert int(fields["passed"]) == payload["passed"]
    assert int(fields["failed"]) == payload["failed"]
    assert int(fields["llm_calls"]) == _jsonl_count(run_dir / "llm_traces.jsonl")

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
    assert payload["total_cases"] > 0


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
    assert _jsonl_count(run_dir / "llm_traces.jsonl") == _jsonl_count(run_dir / "lifecycle_traces.jsonl")


def test_run_eval_auto_lifecycle_uses_hybrid_when_llm_configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MEMORII_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    assert main(["--suite", "memory_lifecycle_v1", "--dry-run", "--storage-root", str(tmp_path)]) == 0

    run_dir = sorted((tmp_path / "benchmark_runs" / "memory_lifecycle_v1" / "auto").glob("bench-*"))[-1]
    assert _jsonl_count(run_dir / "llm_traces.jsonl") == _jsonl_count(run_dir / "lifecycle_traces.jsonl")


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
    assert "suite=retrieval_corruption_v1 status=starting" in output
    assert "suite=retrieval_corruption_v1 status=finished exit_code=0" in output
    assert "suite=execution_graph_v1 status=starting" in output
    assert "suite=execution_graph_v1 status=finished exit_code=0" in output
    assert "mode=rule total_cases=" in output
    assert "suite=memory_lifecycle_v1" in output
    assert "suite=retrieval_corruption_v1" in output
    assert "suite=execution_graph_v1" in output
    assert (tmp_path / "eval_runs" / "llm").exists()
    assert (tmp_path / "benchmark_runs" / "memory_lifecycle_v1" / "rule").exists()
    assert (tmp_path / "benchmark_runs" / "retrieval_corruption_v1" / "rule").exists()
    assert (tmp_path / "benchmark_runs" / "execution_graph_v1" / "rule").exists()


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

    assert "suite=retrieval_corruption_v1 status=starting" in output
    assert "suite=execution_graph_v1 status=starting" in output
    assert "mode=rule total_cases=" in output
    assert "suite=memory_lifecycle_v1" in output
    assert "suite=retrieval_corruption_v1" in output
    assert "suite=execution_graph_v1" in output
