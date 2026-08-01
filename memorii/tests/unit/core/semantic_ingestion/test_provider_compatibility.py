from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.fake import FakeLLMStructuredClient
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.memory_evolution import EnglishRuleMemoryExtractor, HybridMemoryExtractor, LLMMemoryExtractor
from memorii.core.memory_evolution.models import SourceObservation
from memorii.core.provider.models import ProviderEvolutionOutcome, ProviderOperation, ProviderSyncResult
from memorii.core.provider.service import ProviderMemoryService
from memorii.domain.enums import SourceModality
from memorii.integrations.hermes_provider import HermesMemoryProvider

_ROOT = Path(__file__).parents[3]
_FIXTURE = _ROOT / "fixtures" / "semantic_ingestion" / "provider_compatibility"
_TOOL = _ROOT.parents[0] / "tools" / "extract_provider_compatibility_fixture.py"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _jcs(value: Any) -> bytes:
    """Independent RFC 8785 verifier program; it imports no capture code."""
    node = shutil.which("node")
    assert node is not None
    program = r'''const fs=require("fs");function cmp(a,b){for(let i=0;i<Math.min(a.length,b.length);i++){let x=a.charCodeAt(i),y=b.charCodeAt(i);if(x!==y)return x-y}return a.length-b.length}function c(x){if(x===null||typeof x!=="object")return JSON.stringify(x);if(Array.isArray(x))return "["+x.map(c).join(",")+"]";return "{"+Object.keys(x).sort(cmp).map(k=>JSON.stringify(k)+":"+c(x[k])).join(",")+"}"}process.stdout.write(c(JSON.parse(fs.readFileSync(0,"utf8"))))'''
    source = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    return subprocess.run([node, "-e", program], input=source, check=True, capture_output=True).stdout


def _authority_digest(root: Path = _FIXTURE) -> str:
    text = (root / "expected_manifest.sha256").read_text(encoding="ascii")
    match = re.fullmatch(r"([0-9a-f]{64})  capture_manifest\.json\n", text)
    assert match is not None
    return match.group(1)


def _corpus() -> dict[str, Any]:
    return _json(_FIXTURE / "provider_envelope_corpus.json")


def _manifest() -> dict[str, Any]:
    return _json(_FIXTURE / "capture_manifest.json")


def _legacy_reader() -> Any:
    spec = importlib.util.spec_from_file_location("provider_compatibility_legacy_reader", _FIXTURE / "legacy_reader.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _failing_extractor() -> LLMMemoryExtractor:
    return LLMMemoryExtractor(
        runner=PromptLLMRunner(
            client=FakeLLMStructuredClient(raise_on_request=True),
            config=LLMRuntimeConfig(provider="none"),
        )
    )


class _FailFirstExtractor(EnglishRuleMemoryExtractor):
    def __init__(self) -> None:
        self.calls = 0

    def extract(self, observations: list[SourceObservation]):
        self.calls += 1
        if self.calls == 1:
            raise OSError("injected retryable failure")
        return super().extract(observations)


def _verify_fixture(root: Path, expected_manifest_digest: str, *, legacy_reader: Path) -> None:
    """Independent fixture verifier: it deliberately does not import capture."""
    manifest_bytes = (root / "capture_manifest.json").read_bytes()
    assert sha256(manifest_bytes).hexdigest() == expected_manifest_digest
    manifest = _json(root / "capture_manifest.json")
    corpus = (root / "provider_envelope_corpus.json").read_bytes()
    try:
        parsed_corpus = json.loads(corpus)
    except json.JSONDecodeError as error:
        raise AssertionError("corpus is not JSON") from error
    assert corpus == _jcs(parsed_corpus)
    assert manifest_bytes == _jcs(manifest)
    assert sha256(corpus).hexdigest() == manifest["corpus_sha256"]
    for name, digest in manifest["generated_files"].items():
        assert sha256((root / name).read_bytes()).hexdigest() == digest
    reader_input = manifest["capture"]["inputs"]["legacy_reader"]
    assert reader_input["path"] == "legacy_reader.py"
    assert sha256(legacy_reader.read_bytes()).hexdigest() == reader_input["sha256"]


def test_independent_rfc8785_known_answer_vectors() -> None:
    assert _jcs([-0.0, 1e-7, 1e-6, 1e20, 1e21]) == b"[0,1e-7,0.000001,100000000000000000000,1e+21]"
    assert _jcs("\x00\b\t\n\f\r\"\\/🙂e\u0301") == b'"\\u0000\\b\\t\\n\\f\\r\\\"\\\\/\xf0\x9f\x99\x82e\xcc\x81"'
    assert _jcs({"\ue000": 1, "\U00010000": 2, "\ufffd": 3}) == '{"𐀀":2,"":1,"�":3}'.encode()


def test_capture_manifest_binds_every_portable_input_tool_and_generated_file() -> None:
    expected_digest = _authority_digest()
    assert sha256((_FIXTURE / "capture_manifest.json").read_bytes()).hexdigest() == expected_digest
    _verify_fixture(_FIXTURE, expected_digest, legacy_reader=_FIXTURE / "legacy_reader.py")
    manifest = _manifest()
    assert manifest["format"] == "memorii.provider-envelope-capture.v4"
    assert manifest["baseline"]["commit"] == "f76850fc45f09d21a40b5a7302d173ce642ec9d6"
    assert manifest["baseline"]["tree"] == "1aef4aa4364dad9cf4e0063fb64a8e26c5783614"
    assert manifest["baseline"]["blob"] == "307921e7648fcaf5e11244200a7fb3c1f402e817"
    assert manifest["baseline"]["source_sha256"] == "38b80a29a991ebfb1076cccc437c2406d43da031982a6c8fe57f755e1e58dbbd"
    assert manifest["capture"]["tool_sha256"] == sha256(_TOOL.read_bytes()).hexdigest()
    assert set(manifest["capture"]) == {
        "inputs",
        "jcs_program_sha256",
        "method",
        "program_sha256",
        "tool_sha256",
    }
    assert "legacy_reader.py" not in manifest["generated_files"]
    for name, digest in manifest["generated_files"].items():
        assert sha256((_FIXTURE / name).read_bytes()).hexdigest() == digest
    assert sha256((_FIXTURE / "provider_envelope_corpus.json").read_bytes()).hexdigest() == manifest["corpus_sha256"]
    for path in (_FIXTURE / "provider_envelope_corpus.json", _FIXTURE / "capture_manifest.json"):
        assert path.read_bytes() == _jcs(_json(path))


def test_schema_field_order_enum_cases_and_validator_matrix_are_exact() -> None:
    corpus, manifest = _corpus(), _manifest()
    reader = _legacy_reader()
    assert ProviderEvolutionOutcome.model_json_schema() == corpus["provider_evolution_outcome_schema"]
    assert ProviderSyncResult.model_json_schema() == corpus["provider_sync_result_schema"]
    assert list(ProviderEvolutionOutcome.model_fields) == corpus["field_order"]["ProviderEvolutionOutcome"]
    assert list(ProviderSyncResult.model_fields) == corpus["field_order"]["ProviderSyncResult"]
    assert len(corpus["validator_branch_matrix"]) == manifest["coverage"]["validator_vector_count"]
    assert set(corpus) >= set(manifest["coverage"]["required_sections"])
    for name, payload in corpus["accepted_outcomes"].items():
        assert _bytes(ProviderEvolutionOutcome.model_validate(payload).model_dump(mode="json", exclude_none=False)) == corpus["accepted_outcome_bytes"][name].encode()
    for payload in corpus["invalid_outcomes"].values():
        with pytest.raises(ValueError):
            ProviderEvolutionOutcome.model_validate(payload)
    for vector in corpus["validator_branch_matrix"].values():
        if vector["accepted"]:
            actual = ProviderEvolutionOutcome.model_validate(vector["input"]).model_dump(mode="json", exclude_none=False)
            assert _bytes(actual) == vector["output_bytes"].encode()
            assert reader.read_outcome(vector["output_bytes"].encode("utf-8"))
        else:
            with pytest.raises(ValueError) as error:
                ProviderEvolutionOutcome.model_validate(vector["input"])
            assert type(error.value).__name__ == vector["error"]


def test_sync_result_serializes_every_public_case_in_field_and_outcome_order() -> None:
    corpus, manifest = _corpus(), _manifest()
    reader = _legacy_reader()
    assert list(corpus["sync_cases"]) == manifest["coverage"]["sync_case_names"]
    for name, payload in corpus["sync_cases"].items():
        actual = ProviderSyncResult.model_validate(payload).model_dump(mode="json", exclude_none=False)
        assert _bytes(actual) == corpus["sync_case_bytes"][name].encode()
    for name, verdict in corpus["sync_validation"].items():
        if verdict["accepted"]:
            actual = ProviderSyncResult.model_validate(verdict["input"]).model_dump(mode="json", exclude_none=False)
            assert _bytes(actual) == verdict["expected_bytes"].encode("utf-8"), name
            assert reader.read_sync(verdict["expected_bytes"].encode("utf-8"))
        else:
            with pytest.raises(ValueError) as error:
                ProviderSyncResult.model_validate(verdict["input"])
            assert type(error.value).__name__ == verdict["error"], name


def test_service_and_hermes_public_paths_preserve_schema_and_reader_contract() -> None:
    def now() -> datetime:
        return datetime(2026, 1, 2, tzinfo=UTC)
    service = ProviderMemoryService(now_provider=now)
    service_result = service.sync_event(
        operation=ProviderOperation.MEMORY_WRITE_DAILYLOG,
        content="Provider compatibility service bytes",
        operation_id="compatibility-service",
        task_id="provider-compatibility",
    )
    assert _legacy_reader().read_sync(_bytes(service_result.model_dump(mode="json", exclude_none=False)))
    hermes = HermesMemoryProvider(ProviderMemoryService(now_provider=now))
    hermes_result = hermes.sync_turn(
        "Provider compatibility user bytes",
        "Provider compatibility assistant bytes",
        operation_id="compatibility-turn",
        task_id="provider-compatibility",
    )
    assert _legacy_reader().read_sync(_bytes(hermes_result.model_dump(mode="json", exclude_none=False)))


def test_current_service_scenarios_remain_reader_compatible() -> None:
    reader = _legacy_reader()

    def now() -> datetime:
        return datetime(2026, 1, 2, tzinfo=UTC)

    def run(extractor: Any, operation_id: str, *, modality: SourceModality | None = None) -> ProviderSyncResult:
        return ProviderMemoryService(memory_evolution_extractor=extractor, now_provider=now).sync_event(
            operation=ProviderOperation.MEMORY_WRITE_DAILYLOG,
            content="Atlas owner is Bob." if modality is None else "ignored",
            operation_id=operation_id,
            task_id="provider-compatibility",
            source_modality=modality,
        )

    terminal = LLMMemoryExtractor(
        runner=PromptLLMRunner(
            client=FakeLLMStructuredClient(default_response="{}"),
            config=LLMRuntimeConfig(provider="none"),
        )
    )
    actual = {
        "deterministic_abstention": run(EnglishRuleMemoryExtractor(), "compatibility-abstained", modality=SourceModality.NOISE),
        "retryable_failure": run(_failing_extractor(), "compatibility-retryable"),
        "terminal_nonretryable": run(terminal, "compatibility-terminal"),
        "committed_primary": run(EnglishRuleMemoryExtractor(), "compatibility-primary"),
        "committed_fallback": run(HybridMemoryExtractor(llm_extractor=_failing_extractor()), "compatibility-fallback"),
    }
    mixed = HermesMemoryProvider(ProviderMemoryService(memory_evolution_extractor=_FailFirstExtractor(), now_provider=now))
    actual["hermes_ordered_mixed"] = mixed.sync_turn(
        "Atlas owner is Bob.",
        "Atlas owner is Carol.",
        operation_id="compatibility-mixed",
        task_id="provider-compatibility",
    )
    for result in actual.values():
        raw = _bytes(result.model_dump(mode="json", exclude_none=False))
        assert reader.read_sync(raw)
        assert result.candidate_ids == []
        assert result.evolution_outcomes == []


def test_frozen_legacy_reader_accepts_public_bytes_and_rejects_order_tamper() -> None:
    module = _legacy_reader()
    corpus = _corpus()
    for payload in corpus["accepted_outcomes"].values():
        assert module.read_outcome(_bytes(ProviderEvolutionOutcome.model_validate(payload).model_dump(mode="json", exclude_none=False)))
    for payload in corpus["sync_cases"].values():
        assert module.read_sync(_bytes(ProviderSyncResult.model_validate(payload).model_dump(mode="json", exclude_none=False)))
    for payload in corpus["service_path_bytes"].values():
        assert module.read_sync(payload.encode("utf-8"))
    bad = b'{"candidate_ids":[],"transcript_ids":[],"blocked_domains":[],"blocked_reasons":{},"allowed_candidate_domains":[],"raw_append_domains":[],"blocked_commit_domains":[],"evolution_outcomes":[]}'
    with pytest.raises(ValueError):
        module.read_sync(bad)
    with pytest.raises(ValueError):
        module.read_outcome(b'{"operation_id":null}')
    with pytest.raises(ValueError):
        module.read_sync(b'[]')


def test_frozen_reader_rejects_closed_schema_and_lifecycle_mutations() -> None:
    reader, corpus = _legacy_reader(), _corpus()
    base = corpus["accepted_outcomes"]["pending"]
    mutations = [
        {**base, "operation_id": 1}, {**base, "attempt_count": True}, {**base, "attempt_count": -1},
        {**base, "retryable": 1}, {**base, "failure_code": []}, {**base, "fallback_provider": []},
        *[{**base, field: "unknown"} for field in ("status", "extraction_status", "provider_attempt_status", "fallback_outcome", "final_extraction_source", "extraction_failure_code", "primary_failure_code")],
        {**base, "status": "evolution_committed"},
        {**base, "status": "evolution_failed"},
        {**base, "fallback_outcome": "succeeded", "final_extraction_source": "fallback"},
        {**base, "fallback_outcome": "failed", "fallback_provider": "x", "final_extraction_source": "primary"},
        {**base, "fallback_provider": "x"},
    ]
    for mutation in mutations:
        with pytest.raises(ValueError):
            reader.read_outcome(_bytes(mutation))
    reordered = {"status": base["status"], **{key: value for key, value in base.items() if key != "status"}}
    with pytest.raises(ValueError):
        reader.read_outcome(_bytes(reordered))
    sync_base = ProviderSyncResult().model_dump(mode="json", exclude_none=False)
    for field, wrong in (
        ("transcript_ids", {}), ("candidate_ids", [1]), ("blocked_domains", ["unknown"]),
        ("blocked_reasons", []), ("allowed_candidate_domains", {}), ("raw_append_domains", [1]),
        ("blocked_commit_domains", None), ("evolution_outcomes", [None]),
    ):
        with pytest.raises(ValueError):
            reader.read_sync(_bytes({**sync_base, field: wrong}))


def test_frozen_reader_uses_exact_baseline_memory_domains() -> None:
    reader = _legacy_reader()
    baseline_domains = ("transcript", "semantic", "episodic", "user", "execution", "solver")
    sync_base = ProviderSyncResult().model_dump(mode="json", exclude_none=False)
    domain_fields = ("blocked_domains", "allowed_candidate_domains", "raw_append_domains", "blocked_commit_domains")
    for field in domain_fields:
        for domain in baseline_domains:
            payload = {**sync_base, field: [domain]}
            assert reader.read_sync(_bytes(payload))
            assert ProviderSyncResult.model_validate(payload)
        for spurious in ("user_context", "execution_plan", "solver_search", "unknown"):
            with pytest.raises(ValueError):
                reader.read_sync(_bytes({**sync_base, field: [spurious]}))


def test_frozen_reader_rejects_duplicate_keys_and_unhashable_enums() -> None:
    reader, corpus = _legacy_reader(), _corpus()
    outcome = corpus["accepted_outcome_bytes"]["pending"].encode("utf-8")
    duplicate_outcome = outcome.replace(b'{"operation_id":', b'{"operation_id":"duplicate","operation_id":', 1)
    with pytest.raises(ValueError, match="duplicate"):
        reader.read_outcome(duplicate_outcome)
    sync = corpus["sync_case_bytes"]["multiple_ordered"].encode("utf-8")
    duplicate_nested = sync.replace(b'{"operation_id":', b'{"operation_id":"duplicate","operation_id":', 1)
    with pytest.raises(ValueError, match="duplicate"):
        reader.read_sync(duplicate_nested)
    duplicate_sync = sync.replace(b'{"transcript_ids":', b'{"transcript_ids":[],"transcript_ids":', 1)
    with pytest.raises(ValueError, match="duplicate"):
        reader.read_sync(duplicate_sync)
    base = corpus["accepted_outcomes"]["pending"]
    for field in ("status", "extraction_status", "provider_attempt_status", "fallback_outcome", "final_extraction_source", "extraction_failure_code", "primary_failure_code"):
        with pytest.raises(ValueError):
            reader.read_outcome(_bytes({**base, field: []}))
    sync_base = ProviderSyncResult().model_dump(mode="json", exclude_none=False)
    with pytest.raises(ValueError):
        reader.read_sync(_bytes({**sync_base, "blocked_domains": [[]]}))


def test_unicode_and_opaque_embedded_payload_contract() -> None:
    corpus = _corpus()
    payload = corpus["accepted_outcomes"]["unicode_boundary"]
    assert payload["operation_id"] == "op-\x00-🙂-e\u0301"
    raw = corpus["accepted_outcome_bytes"]["unicode_boundary"].encode("utf-8")
    assert b"\\u0000" in raw and "🙂".encode() in raw and "e\u0301".encode() in raw
    assert raw.startswith(b'{"operation_id":')
    mutated = dict(corpus)
    mutated_bytes = raw.replace(b'{"operation_id":', b'{"status":"evolution_pending","operation_id":', 1)
    mutated["accepted_outcome_bytes"] = {**corpus["accepted_outcome_bytes"], "unicode_boundary": mutated_bytes.decode()}
    assert sha256(_jcs(mutated)).hexdigest() != _manifest()["corpus_sha256"]
    assert _jcs(json.loads(_jcs(mutated)))[0:1] == b"{"  # string remains opaque across outer round trip


def test_static_authority_rejects_tamper(tmp_path: Path) -> None:
    authority = tmp_path / "expected_manifest.sha256"
    authority.write_text("0" * 64 + "  capture_manifest.json\n", encoding="ascii")
    assert _authority_digest(tmp_path) != sha256((_FIXTURE / "capture_manifest.json").read_bytes()).hexdigest()
