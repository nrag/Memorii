from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from memorii.core.prompts.models import PromptContract
from memorii.core.prompts.registry import PromptRegistry
from memorii.core.prompts.render import PromptRenderer, redact_variables

PROMPT_ROOT = Path(__file__).resolve().parents[3] / "prompts"


def _load(ref: str) -> PromptContract:
    return PromptRegistry(prompt_root=PROMPT_ROOT).load(ref)


def test_prompt_contract_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        PromptContract.model_validate({"prompt_id": "a", "version": "v1", "task": "t", "description": "d", "input_schema": {}, "output_schema": {}, "system_template": "s", "user_template": "u", "model_defaults": {}, "redaction": {}, "extra": 1})


def test_prompt_contract_validates_temperature_range() -> None:
    payload = _load("promotion_decision:v1").model_dump()
    payload["model_defaults"]["temperature"] = 2.1
    with pytest.raises(ValidationError):
        PromptContract.model_validate(payload)


def test_prompt_contract_validates_max_tokens() -> None:
    payload = _load("promotion_decision:v1").model_dump()
    payload["model_defaults"]["max_tokens"] = 0
    with pytest.raises(ValidationError):
        PromptContract.model_validate(payload)


def test_registry_loads_and_lists_all() -> None:
    reg = PromptRegistry(prompt_root=PROMPT_ROOT)
    expected = {
        "promotion_decision:v1",
        "belief_update:v1",
        "judges/promotion_precision:v1",
        "judges/temporal_validity:v1",
        "judges/attribution:v1",
        "judges/belief_direction:v1",
        "judges/memory_plane:v1",
    }
    assert expected.issubset(set(reg.list_prompt_refs()))
    for ref in expected:
        assert reg.load(ref).version == "v1"


def test_registry_rejects_malformed_missing_and_traversal() -> None:
    reg = PromptRegistry(prompt_root=PROMPT_ROOT)
    with pytest.raises(ValueError):
        reg.load("badref")
    with pytest.raises(FileNotFoundError):
        reg.load("unknown:v1")
    with pytest.raises(ValueError):
        reg.load("../x:v1")
    with pytest.raises(ValueError):
        reg.load("judges/../../x:v1")


def test_registry_rejects_malformed_yaml(tmp_path: Path) -> None:
    root = tmp_path / "prompts"
    (root / "a").mkdir(parents=True)
    (root / "a" / "v1.yaml").write_text("- not-a-mapping")
    with pytest.raises(ValueError):
        PromptRegistry(prompt_root=root).load("a:v1")


def test_renderer_renders_and_hash_changes() -> None:
    contract = _load("promotion_decision:v1")
    renderer = PromptRenderer()
    vars1 = {"context_json": {"b": 1, "a": [2, 3]}, "candidate_summary": "x"}
    out1 = renderer.render(contract=contract, variables=vars1)
    out2 = renderer.render(contract=contract, variables=vars1)
    out3 = renderer.render(contract=contract, variables={"context_json": {"a": [2, 4], "b": 1}, "candidate_summary": "x"})
    assert out1.prompt_hash == out2.prompt_hash
    assert out1.prompt_hash != out3.prompt_hash
    assert "{\"a\":[2,3],\"b\":1}" in out1.user


def test_renderer_rejects_unsafe_placeholders_and_missing() -> None:
    payload = _load("promotion_decision:v1").model_dump()
    for template in ["bad {x.y}", "bad {x[0]}", "bad {x!r}", "bad {x:>5}"]:
        payload["system_template"] = template
        contract = PromptContract.model_validate(payload)
        with pytest.raises(ValueError):
            PromptRenderer().render(contract=contract, variables={"x": "ok", "context_json": {}, "candidate_summary": "c"})

    with pytest.raises(KeyError):
        PromptRenderer().render(contract=_load("promotion_decision:v1"), variables={"context_json": {}})


def test_redaction_nested_and_non_mutating() -> None:
    policy = _load("promotion_decision:v1").redaction
    variables = {
        "api_key": "abc",
        "input_payload": {"metadata": {"token": "nested"}, "items": [{"password": "p1"}]},
        "actual_output": {"deep": {"secret": "s1"}},
        "metadata": {"trace": [{"cookie": "c"}]},
    }
    before = deepcopy(variables)
    redacted = redact_variables(variables=variables, policy=policy)
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["input_payload"]["metadata"]["token"] == "[REDACTED]"
    assert redacted["input_payload"]["items"][0]["password"] == "[REDACTED]"
    assert redacted["actual_output"]["deep"]["secret"] == "[REDACTED]"
    assert redacted["metadata"]["trace"][0]["cookie"] == "[REDACTED]"
    assert variables == before


def test_grounding_prompts_require_textual_evidence_and_local_ids() -> None:
    for ref in ("evidence_selection:v1", "grounded_answer:v1", "answer_verification:v1"):
        system = _load(ref).system_template
        assert "short local IDs" in system
        assert "Use candidate text as factual evidence" in system
        assert "metadata as locators or disambiguators" in system


def test_answer_verification_prompt_requires_question_constraint_coverage() -> None:
    contract = _load("answer_verification:v1")
    assert "question_constraints" in contract.output_schema["required"]
    assert "question_constraints" in contract.output_schema["properties"]
    assert "alternative_answers" in contract.output_schema["required"]
    assert "alternative_answers" in contract.output_schema["properties"]
    system = contract.system_template
    assert "Break the question into the required constraints" in system
    assert "A locally supported answer is not enough" in system
    assert "plausible alternative answers" in system
    assert "candidate_answers_considered" in system


def test_grounding_prompt_schemas_expose_required_proof_and_answer_span_diagnostics() -> None:
    evidence_contract = _load("evidence_selection:v1")
    proof_step_schema = evidence_contract.output_schema["properties"]["proof_steps"]["items"]
    assert "required_candidate_ids" in proof_step_schema["required"]
    assert "required_candidate_ids" in proof_step_schema["properties"]
    assert "citations" in proof_step_schema["required"]
    citation_schema = proof_step_schema["properties"]["citations"]["items"]
    assert "role" in citation_schema["properties"]
    assert "background_context" in citation_schema["properties"]["role"]["enum"]
    assert "required_for_final_support" in citation_schema["required"]

    answer_contract = _load("grounded_answer:v1")
    for key in ("answer_requirements", "candidate_answers_considered", "answer_type", "answer_span_candidate_id", "answer_span_text"):
        assert key in answer_contract.output_schema["required"]
        assert key in answer_contract.output_schema["properties"]
    candidate_schema = answer_contract.output_schema["properties"]["candidate_answers_considered"]["items"]
    for key in ("answer_type", "requirement_coverage", "satisfied_requirement_ids", "missing_requirement_ids"):
        assert key in candidate_schema["required"]
        assert key in candidate_schema["properties"]


def test_prompt_yaml_security_and_schema_strength() -> None:
    expected_keys = {"api_key", "token", "password", "secret", "authorization", "cookie"}
    for path in PROMPT_ROOT.glob("**/*.yaml"):
        text = path.read_text()
        assert "sk-" not in text
        data = yaml.safe_load(text)
        assert data["output_schema"]["additionalProperties"] is False
        if path.name == "v1.yaml":
            props = data["output_schema"]["properties"]
            for key in ("confidence", "score", "belief"):
                if key in props:
                    assert props[key]["minimum"] == 0.0
                    assert props[key]["maximum"] == 1.0
        assert expected_keys.issubset(set(data["redaction"]["redact_input_fields"]))


def test_all_prompts_render_with_expected_variables() -> None:
    renderer = PromptRenderer()
    samples = {
        "promotion_decision:v1": {"context_json": {}, "candidate_summary": "candidate"},
            "belief_update:v1": {"context_json": {}, "prior_belief": 0.4},
            "lifecycle_decision:v1": {"context_json": {}, "query": "query"},
            "execution_graph_decision:v1": {"context_json": {}, "task": "task"},
            "retrieval_relevance:v1": {"context_json": {}, "query": "query"},
            "evidence_selection:v1": {"context_json": {}, "query": "query"},
            "grounded_answer:v1": {"context_json": {}, "query": "query"},
            "answer_verification:v1": {"context_json": {}, "query": "query"},
            "hotpotqa_answer:v1": {"context_json": {}, "question": "question"},
        }
    for ref in PromptRegistry(prompt_root=PROMPT_ROOT).list_prompt_refs():
        contract = _load(ref)
        if ref.startswith("judges/"):
            variables = {"rubric_json": {}, "input_payload": {}}
        else:
            variables = samples[ref]
        rendered = renderer.render(contract=contract, variables=variables)
        assert rendered.prompt_ref == ref
