from __future__ import annotations
import json
from pathlib import Path
import pytest
from memorii.tools.run_live_llm_eval import main

def _set_env(monkeypatch: pytest.MonkeyPatch, **vals: str) -> None:
    for k in ["MEMORII_LLM_PROVIDER", "MEMORII_LLM_MODEL", "OPENAI_API_KEY", "MEMORII_ENABLE_LIVE_LLM_TESTS"]:
        monkeypatch.delenv(k, raising=False)
    for k, v in vals.items():
        monkeypatch.setenv(k, v)

def test_rule_mode_no_live_needed(monkeypatch, tmp_path):
    _set_env(monkeypatch, MEMORII_LLM_PROVIDER="none")
    assert main(["--mode", "rule", "--storage-root", str(tmp_path)]) == 0

def test_llm_without_allow_live_fails(monkeypatch):
    _set_env(monkeypatch, MEMORII_LLM_PROVIDER="openai", OPENAI_API_KEY="sk-test", MEMORII_ENABLE_LIVE_LLM_TESTS="true")
    with pytest.raises(SystemExit): main(["--mode", "llm"])

def test_hybrid_without_live_gate_fails(monkeypatch):
    _set_env(monkeypatch, MEMORII_LLM_PROVIDER="openai", OPENAI_API_KEY="sk-test", MEMORII_ENABLE_LIVE_LLM_TESTS="false")
    with pytest.raises(SystemExit): main(["--mode", "hybrid", "--allow-live"])

def test_dry_run_llm_succeeds_no_key(monkeypatch, tmp_path):
    _set_env(monkeypatch, MEMORII_LLM_PROVIDER="openai")
    assert main(["--mode", "llm", "--dry-run", "--storage-root", str(tmp_path)]) == 0

def test_dry_run_all_writes_artifacts(monkeypatch, tmp_path):
    _set_env(monkeypatch, MEMORII_LLM_PROVIDER="none")
    assert main(["--mode", "all", "--dry-run", "--storage-root", str(tmp_path)]) == 0
    assert (tmp_path / "eval_runs" / "llm").exists()

def test_provider_none_llm_without_dry_fails(monkeypatch):
    _set_env(monkeypatch, MEMORII_LLM_PROVIDER="none")
    with pytest.raises(SystemExit): main(["--mode", "llm", "--allow-live"])

def test_runtime_redacted_output_no_key(monkeypatch, capsys, tmp_path):
    _set_env(monkeypatch, MEMORII_LLM_PROVIDER="openai", OPENAI_API_KEY="sk-secret")
    main(["--mode", "rule", "--storage-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert "sk-secret" not in out and "runtime_config=" in out

def test_artifact_layout_and_files(monkeypatch, tmp_path):
    _set_env(monkeypatch, MEMORII_LLM_PROVIDER="none")
    main(["--mode", "rule", "--dry-run", "--storage-root", str(tmp_path)])
    run_dir = next((tmp_path / "eval_runs" / "llm").glob("*/*"))
    for rel in ["report.json", "summary.txt", "results.jsonl", "failures.jsonl", "fallbacks.jsonl", "disagreements.jsonl", "inputs/snapshots.jsonl"]:
        assert (run_dir / rel).exists()

def test_promotion_only(monkeypatch, tmp_path):
    _set_env(monkeypatch, MEMORII_LLM_PROVIDER="none")
    main(["--golden-set", "promotion", "--mode", "rule", "--dry-run", "--storage-root", str(tmp_path)])
    run_dir = next((tmp_path / "eval_runs" / "llm").glob("*/*"))
    assert all(json.loads(l)["decision_point"] == "promotion" for l in (run_dir / "inputs" / "snapshots.jsonl").read_text().splitlines() if l)

def test_belief_only(monkeypatch, tmp_path):
    _set_env(monkeypatch, MEMORII_LLM_PROVIDER="none")
    main(["--golden-set", "belief", "--mode", "rule", "--dry-run", "--storage-root", str(tmp_path)])
    run_dir = next((tmp_path / "eval_runs" / "llm").glob("*/*"))
    assert all(json.loads(l)["decision_point"] == "belief_update" for l in (run_dir / "inputs" / "snapshots.jsonl").read_text().splitlines() if l)

def test_mode_all_produces_three_reports(monkeypatch, tmp_path):
    _set_env(monkeypatch, MEMORII_LLM_PROVIDER="none")
    main(["--mode", "all", "--dry-run", "--storage-root", str(tmp_path)])
    assert len(list((tmp_path / "eval_runs" / "llm").glob("*/*"))) == 3

def test_invalid_cli_exits_nonzero():
    with pytest.raises(SystemExit): main(["--mode", "bad"])
