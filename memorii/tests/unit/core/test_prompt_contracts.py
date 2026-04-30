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
    contract = _load("promotion_decision:v1")
    payload = contract.model_dump()
    payload["model_defaults"]["temperature"] = 2.5
    with pytest.raises(ValidationError):
        PromptContract.model_validate(payload)


def test_prompt_contract_validates_max_tokens() -> None:
    contract = _load("promotion_decision:v1")
    payload = contract.model_dump()
    payload["model_defaults"]["max_tokens"] = 0
    with pytest.raises(ValidationError):
        PromptContract.model_validate(payload)


def test_registry_loads_refs_and_list() -> None:
    reg = PromptRegistry(prompt_root=PROMPT_ROOT)
    assert reg.load("promotion_decision:v1").prompt_id == "promotion_decision"
    assert reg.load("belief_update:v1").prompt_id == "belief_update"
    for ref in [
        "judges/promotion_precision:v1",
        "judges/temporal_validity:v1",
        "judges/attribution:v1",
        "judges/belief_direction:v1",
        "judges/memory_plane:v1",
    ]:
        assert reg.load(ref).prompt_id.startswith("judges/")
    refs = reg.list_prompt_refs()
    assert set(refs) >= {"promotion_decision:v1", "belief_update:v1", "judges/promotion_precision:v1", "judges/temporal_validity:v1", "judges/attribution:v1", "judges/belief_direction:v1", "judges/memory_plane:v1"}


def test_registry_rejects_invalid_ref_and_missing() -> None:
    reg = PromptRegistry(prompt_root=PROMPT_ROOT)
    with pytest.raises(ValueError):
        reg.load("badref")
    with pytest.raises(FileNotFoundError):
        reg.load("not_here:v1")


def test_renderer_and_hash_and_serialization() -> None:
    contract = _load("promotion_decision:v1")
    renderer = PromptRenderer()
    variables = {"context_json": {"b": 1, "a": [2, 3]}, "candidate_summary": "x"}
    rendered = renderer.render(contract=contract, variables=variables)
    assert "{\"a\":[2,3],\"b\":1}" in rendered.user
    again = renderer.render(contract=contract, variables=variables)
    assert rendered.prompt_hash == again.prompt_hash
    changed = renderer.render(contract=contract, variables={"context_json": {"a": [2, 4], "b": 1}, "candidate_summary": "x"})
    assert rendered.prompt_hash != changed.prompt_hash
    assert rendered.prompt_id == contract.prompt_id
    assert rendered.version == contract.version
    assert rendered.model_defaults == contract.model_defaults
    assert rendered.expected_output_schema == contract.output_schema


def test_missing_template_variable_raises() -> None:
    with pytest.raises(KeyError):
        PromptRenderer().render(contract=_load("promotion_decision:v1"), variables={"context_json": {}})


def test_redaction_rules_and_no_mutation() -> None:
    policy = _load("promotion_decision:v1").redaction
    variables = {
        "api_key": "abc",
        "input_payload": {"token": "t", "keep": "ok"},
        "actual_output": {"password": "p"},
        "expected_output": {"secret": "s"},
        "metadata": {"cookie": "c"},
    }
    snapshot = deepcopy(variables)
    redacted = redact_variables(variables=variables, policy=policy)
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["input_payload"]["token"] == "[REDACTED]"
    assert redacted["actual_output"]["password"] == "[REDACTED]"
    assert variables == snapshot


def test_prompt_yaml_security_defaults() -> None:
    keys = {"api_key", "token", "password", "secret", "authorization", "cookie"}
    for path in PROMPT_ROOT.glob("**/*.yaml"):
        body = path.read_text()
        assert "sk-" not in body
        data = yaml.safe_load(body)
        redaction = data["redaction"]
        assert keys.issubset(set(redaction["redact_input_fields"]))
