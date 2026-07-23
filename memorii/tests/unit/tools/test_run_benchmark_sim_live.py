from __future__ import annotations

import json
from pathlib import Path

import pytest
from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.models import LLMStructuredRequest, LLMStructuredResponse
from tests.unit.tools.run_benchmark_test_helpers import (
    _application_with_fake_client,
    _application_with_live_client,
    _latest_run_dir,
)


def test_memory_evolution_sim_live_llm_uses_live_adapter_not_oracle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class StubLiveClient:
        provider_name = "stub-live"

        def complete_structured(self, request: LLMStructuredRequest, *, config: LLMRuntimeConfig) -> LLMStructuredResponse:
            del config
            output = {
                "operation": "abstain",
                "belief_ranking_ids": [],
                "selected_claim_ids": [],
                "considered_claim_ids": [],
                "relevant_relation_ids": [],
                "answer": None,
                "next_action": None,
                "uncertain_ids": [],
                "confidence": 0.5,
                "rationale": "valid semantic abstention, intentionally not oracle",
            }
            return LLMStructuredResponse(
                request_id=request.request_id,
                provider=self.provider_name,
                requested_model="stub-model",
                actual_model="stub-model",
                raw_text=json.dumps(output),
                parsed_json=output,
                valid_json=True,
                schema_valid=True,
            )

    monkeypatch.setenv("MEMORII_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("MEMORII_ENABLE_LIVE_LLM_TESTS", "true")
    app = _application_with_live_client(StubLiveClient)

    assert app.run(
        [
            "--suite",
            "memory_evolution_sim_v1",
            "--mode",
            "llm",
            "--allow-live",
            "--storage-root",
            str(tmp_path),
            "--sim-scenario-count",
            "1",
        ]
    ) == 0

    run_dir = _latest_run_dir(tmp_path, "memory_evolution_sim_v1", "llm")
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (run_dir / "sim_checkpoint_results.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    traces = [
        json.loads(line)
        for line in (run_dir / "llm_traces.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert payload["final_output_source_counts"] == {"live_llm": payload["checkpoint_count"]}
    assert payload["failed"] > 0
    assert rows[0]["output"]["operation"] == "abstain"
    assert traces[0]["trace"]["input_payload"]["provider"] == "stub-live"
    assert traces[0]["trace"]["prompt_version"] == "memory_evolution_sim_reconstruction:v1"


def test_memory_evolution_sim_hybrid_falls_back_to_rule_on_invalid_llm_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class InvalidFakeClient:
        provider_name = "fake-invalid"

        def complete_structured(
            self,
            request: LLMStructuredRequest,
            *,
            config: LLMRuntimeConfig,
        ) -> LLMStructuredResponse:
            del config
            return LLMStructuredResponse(
                request_id=request.request_id,
                provider=self.provider_name,
                raw_text="not-json",
                valid_json=False,
                schema_valid=False,
            )

    app = _application_with_fake_client(InvalidFakeClient)
    monkeypatch.setenv("MEMORII_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    assert app.run(
        [
            "--suite",
            "memory_evolution_sim_v1",
            "--mode",
            "hybrid",
            "--dry-run",
            "--storage-root",
            str(tmp_path),
        ]
    ) == 0

    run_dir = _latest_run_dir(tmp_path, "memory_evolution_sim_v1", "hybrid")
    rows = [
        json.loads(line)
        for line in (run_dir / "sim_checkpoint_results.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len([row for row in rows if row["fallback_used"] is True]) == len(rows)
    assert len([row for row in rows if row["success"] is False]) > 0
