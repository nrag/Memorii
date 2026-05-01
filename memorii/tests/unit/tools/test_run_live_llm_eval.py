from __future__ import annotations

import json
from pathlib import Path

import pytest

from memorii.tools.run_live_llm_eval import main


def _set_env(monkeypatch: pytest.MonkeyPatch, **vals: str) -> None:
    for key in [
        "MEMORII_LLM_PROVIDER",
        "MEMORII_LLM_MODEL",
        "OPENAI_API_KEY",
        "MEMORII_ENABLE_LIVE_LLM_TESTS",
    ]:
        monkeypatch.delenv(key, raising=False)
    for key, value in vals.items():
        monkeypatch.setenv(key, value)


def _latest_run_dir(storage_root: Path) -> Path:
    return sorted((storage_root / "eval_runs" / "llm").glob("*/*"))[-1]


def test_rule_mode_no_live_needed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, MEMORII_LLM_PROVIDER="none")
    assert main(["--mode", "rule", "--storage-root", str(tmp_path)]) == 0


def test_llm_without_allow_live_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(
        monkeypatch,
        MEMORII_LLM_PROVIDER="openai",
        OPENAI_API_KEY="test-key",
        MEMORII_ENABLE_LIVE_LLM_TESTS="true",
    )
    with pytest.raises(SystemExit):
        main(["--mode", "llm"])


def test_mode_all_without_allow_live_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(
        monkeypatch,
        MEMORII_LLM_PROVIDER="openai",
        OPENAI_API_KEY="test-key",
        MEMORII_ENABLE_LIVE_LLM_TESTS="true",
    )
    with pytest.raises(SystemExit):
        main(["--mode", "all"])


def test_hybrid_without_live_gate_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(
        monkeypatch,
        MEMORII_LLM_PROVIDER="openai",
        OPENAI_API_KEY="test-key",
        MEMORII_ENABLE_LIVE_LLM_TESTS="false",
    )
    with pytest.raises(SystemExit):
        main(["--mode", "hybrid", "--allow-live"])


def test_dry_run_llm_succeeds_no_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, MEMORII_LLM_PROVIDER="openai")
    assert main(["--mode", "llm", "--dry-run", "--storage-root", str(tmp_path)]) == 0


def test_dry_run_all_writes_artifacts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, MEMORII_LLM_PROVIDER="none")
    assert main(["--mode", "all", "--dry-run", "--storage-root", str(tmp_path)]) == 0
    assert (tmp_path / "eval_runs" / "llm").exists()


def test_provider_none_llm_without_dry_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, MEMORII_LLM_PROVIDER="none")
    with pytest.raises(SystemExit):
        main(["--mode", "llm", "--allow-live"])


def test_runtime_redacted_output_no_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _set_env(monkeypatch, MEMORII_LLM_PROVIDER="openai", OPENAI_API_KEY="secret-key")
    main(["--mode", "rule", "--storage-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert "secret-key" not in out
    assert "runtime_config=" in out


def test_artifact_layout_and_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, MEMORII_LLM_PROVIDER="none")
    main(["--mode", "rule", "--dry-run", "--storage-root", str(tmp_path)])
    run_dir = _latest_run_dir(tmp_path)
    for rel in [
        "report.json",
        "summary.txt",
        "results.jsonl",
        "failures.jsonl",
        "fallbacks.jsonl",
        "disagreements.jsonl",
        "inputs/snapshots.jsonl",
    ]:
        assert (run_dir / rel).exists()


def test_artifacts_do_not_contain_api_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, MEMORII_LLM_PROVIDER="openai", OPENAI_API_KEY="secret-key")
    main(["--mode", "rule", "--storage-root", str(tmp_path)])
    run_dir = _latest_run_dir(tmp_path)
    for file_path in run_dir.rglob("*"):
        if file_path.is_file():
            assert "secret-key" not in file_path.read_text(encoding="utf-8")


def test_default_prompt_root_works_in_dry_run_llm(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, MEMORII_LLM_PROVIDER="none")
    assert main(["--mode", "llm", "--dry-run", "--storage-root", str(tmp_path)]) == 0


def test_promotion_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, MEMORII_LLM_PROVIDER="none")
    main(
        [
            "--golden-set",
            "promotion",
            "--mode",
            "rule",
            "--dry-run",
            "--storage-root",
            str(tmp_path),
        ]
    )
    run_dir = _latest_run_dir(tmp_path)
    assert all(
        json.loads(line)["decision_point"] == "promotion"
        for line in (run_dir / "inputs" / "snapshots.jsonl").read_text().splitlines()
        if line
    )


def test_belief_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, MEMORII_LLM_PROVIDER="none")
    main(["--golden-set", "belief", "--mode", "rule", "--dry-run", "--storage-root", str(tmp_path)])
    run_dir = _latest_run_dir(tmp_path)
    assert all(
        json.loads(line)["decision_point"] == "belief_update"
        for line in (run_dir / "inputs" / "snapshots.jsonl").read_text().splitlines()
        if line
    )


def test_mode_all_produces_three_reports(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, MEMORII_LLM_PROVIDER="none")
    main(["--mode", "all", "--dry-run", "--storage-root", str(tmp_path)])
    assert len(list((tmp_path / "eval_runs" / "llm").glob("*/*"))) == 3


def test_invalid_cli_exits_nonzero() -> None:
    with pytest.raises(SystemExit):
        main(["--mode", "bad"])
