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
    }
    for ref in PromptRegistry(prompt_root=PROMPT_ROOT).list_prompt_refs():
        contract = _load(ref)
        if ref.startswith("judges/"):
            variables = {"rubric_json": {}, "input_payload": {}}
        else:
            variables = samples[ref]
        rendered = renderer.render(contract=contract, variables=variables)
        assert rendered.prompt_ref == ref
