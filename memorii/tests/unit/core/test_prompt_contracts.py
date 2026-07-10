from __future__ import annotations

import json
from inspect import signature
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft7Validator
from pydantic import ValidationError

from memorii.core.llm_decision.adapters import (
    LLMAnswerVerificationAdapter,
    LLMBeliefUpdateAdapter,
    LLMEvidenceSelectionAdapter,
    LLMExecutionGraphDecisionAdapter,
    LLMGroundedAnswerAdapter,
    LLMHotpotQAAnswerAdapter,
    LLMLifecycleDecisionAdapter,
    LLMMemoryEvolutionDecisionAdapter,
    LLMMemoryEvolutionSimReconstructionAdapter,
    LLMPromotionDecisionAdapter,
    LLMRetrievalRelevanceDecisionAdapter,
    default_judge_prompt_refs,
)
from memorii.core.llm_provider.models import LLMStructuredResponse
from memorii.core.llm_provider.parser import parse_structured_response
from memorii.core.memory_evolution.extraction import LLMMemoryExtractor
from memorii.core.prompts.manifest import PromptContractManifestEntry, PromptOwner, prompt_contract_manifest_by_ref
from memorii.core.prompts.models import PromptContract
from memorii.core.prompts.registry import PromptRegistry
from memorii.core.prompts.render import PromptRenderer, redact_variables

PROMPT_ROOT = Path(__file__).resolve().parents[3] / "prompts"


def _load(ref: str) -> PromptContract:
    return PromptRegistry(prompt_root=PROMPT_ROOT).load(ref)


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(nested, key) for nested in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False


def _walk_schema_objects(schema: object) -> list[dict[str, object]]:
    objects: list[dict[str, object]] = []
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            objects.append(schema)
        for nested in schema.values():
            objects.extend(_walk_schema_objects(nested))
    elif isinstance(schema, list):
        for item in schema:
            objects.extend(_walk_schema_objects(item))
    return objects


def _parsed_schema_output(ref: str, output: dict[str, object]) -> LLMStructuredResponse:
    contract = _load(ref)
    response = LLMStructuredResponse(
        request_id="test",
        provider="fake",
        raw_text=json.dumps(output, sort_keys=True),
        valid_json=False,
        schema_valid=False,
    )
    return parse_structured_response(response=response, output_schema=contract.output_schema)


_OWNER_DEFAULT_PROMPT_REFS = {
    PromptOwner.LLM_ANSWER_VERIFICATION_ADAPTER: (LLMAnswerVerificationAdapter, "answer_verification:v1"),
    PromptOwner.LLM_BELIEF_UPDATE_ADAPTER: (LLMBeliefUpdateAdapter, "belief_update:v1"),
    PromptOwner.LLM_EVIDENCE_SELECTION_ADAPTER: (LLMEvidenceSelectionAdapter, "evidence_selection:v1"),
    PromptOwner.LLM_EXECUTION_GRAPH_DECISION_ADAPTER: (LLMExecutionGraphDecisionAdapter, "execution_graph_decision:v1"),
    PromptOwner.LLM_GROUNDED_ANSWER_ADAPTER: (LLMGroundedAnswerAdapter, "grounded_answer:v1"),
    PromptOwner.LLM_HOTPOTQA_ANSWER_ADAPTER: (LLMHotpotQAAnswerAdapter, "hotpotqa_answer:v1"),
    PromptOwner.LLM_LIFECYCLE_DECISION_ADAPTER: (LLMLifecycleDecisionAdapter, "lifecycle_decision:v1"),
    PromptOwner.LLM_MEMORY_EVOLUTION_DECISION_ADAPTER: (LLMMemoryEvolutionDecisionAdapter, "memory_evolution_decision:v1"),
    PromptOwner.LLM_MEMORY_EVOLUTION_SIM_RECONSTRUCTION_ADAPTER: (
        LLMMemoryEvolutionSimReconstructionAdapter,
        "memory_evolution_sim_reconstruction:v1",
    ),
    PromptOwner.LLM_PROMOTION_DECISION_ADAPTER: (LLMPromotionDecisionAdapter, "promotion_decision:v1"),
    PromptOwner.LLM_RETRIEVAL_RELEVANCE_DECISION_ADAPTER: (LLMRetrievalRelevanceDecisionAdapter, "retrieval_relevance:v1"),
}


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


def test_memory_extraction_prompt_schema_is_strict_for_openai() -> None:
    contract = _load("memory_extraction:v1")
    claim_schema = contract.output_schema["properties"]["claims"]["items"]
    qualifiers_schema = claim_schema["properties"]["qualifiers"]

    assert qualifiers_schema["type"] == "object"
    assert qualifiers_schema["additionalProperties"] is False
    assert qualifiers_schema["properties"] == {}


def test_memory_evolution_sim_prompt_distinguishes_subject_and_answer_object_entities() -> None:
    contract = _load("memory_evolution_sim_reconstruction:v1")
    system = contract.system_template

    assert "selected_entity_role_policy" in system
    assert "subject_entity_id" in system
    assert "answer-object entities" in system
    assert "what does Y own" in system
    assert "defining identity/type/rekey fact" in system
    assert "set operation=graph_reconstruction" in system
    assert "Previous owners, superseded facts" in system
    assert "context_relation_ids or supporting_relation_ids" in system
    assert "lower-trust or ambiguous claims were rejected" in system
    assert "active current state that the next action continues" in system


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
            "memory_evolution_decision:v1": {"context_json": {}, "query": "query"},
            "memory_evolution_sim_reconstruction:v1": {"context_json": {}, "query": "query"},
            "memory_extraction:v1": {"source_observations": []},
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


def test_prompt_manifest_covers_every_checked_in_prompt() -> None:
    registry_refs = set(PromptRegistry(prompt_root=PROMPT_ROOT).list_prompt_refs())
    manifest_refs = set(prompt_contract_manifest_by_ref())

    assert manifest_refs == registry_refs


@pytest.mark.parametrize("ref,entry", sorted(prompt_contract_manifest_by_ref().items()))
def test_prompt_manifest_matches_yaml_input_contract(ref: str, entry: PromptContractManifestEntry) -> None:
    contract = _load(ref)

    assert entry.prompt_ref == ref
    assert entry.owning_adapter
    assert entry.output_schema_owner == f"{ref}.output_schema"
    assert entry.expected_input_variables == contract.input_schema["required"]
    assert set(entry.representative_variables) == set(entry.expected_input_variables)


def test_prompt_manifest_ownership_matches_adapter_defaults() -> None:
    manifest = prompt_contract_manifest_by_ref()

    for owner, (adapter_cls, prompt_ref) in _OWNER_DEFAULT_PROMPT_REFS.items():
        prompt_ref_parameter = signature(adapter_cls.__init__).parameters["prompt_ref"]
        assert prompt_ref_parameter.default == prompt_ref
        assert manifest[prompt_ref].owning_adapter == owner

    judge_prompt_refs = set(default_judge_prompt_refs().values())
    assert {
        ref
        for ref, entry in manifest.items()
        if entry.owning_adapter == PromptOwner.LLM_JUDGE_DECISION_ADAPTER
    } == judge_prompt_refs
    assert manifest["memory_extraction:v1"].owning_adapter == PromptOwner.LLM_MEMORY_EXTRACTOR
    assert LLMMemoryExtractor.provider == "llm"
    assert LLMMemoryExtractor.prompt_ref == "memory_extraction:v1"


def test_prompt_manifest_rejects_unknown_owner_and_schema_owner_drift() -> None:
    base_payload = prompt_contract_manifest_by_ref()["promotion_decision:v1"].model_dump(mode="json")

    with pytest.raises(ValidationError):
        PromptContractManifestEntry.model_validate({**base_payload, "owning_adapter": "LLMFakePotatoAdapter"})

    with pytest.raises(ValidationError):
        PromptContractManifestEntry.model_validate({**base_payload, "output_schema_owner": "other:v1.output_schema"})


@pytest.mark.parametrize("ref,entry", sorted(prompt_contract_manifest_by_ref().items()))
def test_prompt_manifest_render_variables_are_clean_and_renderable(ref: str, entry: PromptContractManifestEntry) -> None:
    rendered = PromptRenderer().render(contract=_load(ref), variables=entry.render_variables())
    rendered_text = f"{rendered.system}\n{rendered.user}"

    assert rendered.prompt_ref == ref
    for key in entry.forbidden_live_prompt_keys:
        assert not _contains_key(entry.representative_variables, key), f"{ref} representative variables contain forbidden key {key}"
        assert f'"{key}"' not in rendered_text, f"{ref} rendered prompt leaked forbidden JSON key {key}"
    for fragment in entry.forbidden_live_prompt_fragments:
        assert fragment not in rendered_text


@pytest.mark.parametrize("ref,entry", sorted(prompt_contract_manifest_by_ref().items()))
def test_prompt_manifest_fake_outputs_parse_against_yaml_schema(ref: str, entry: PromptContractManifestEntry) -> None:
    valid_response = _parsed_schema_output(ref, entry.fake_valid_output)
    invalid_response = _parsed_schema_output(ref, entry.fake_invalid_output)

    assert valid_response.valid_json is True
    assert valid_response.schema_valid is True
    assert valid_response.parsed_json == entry.fake_valid_output
    assert invalid_response.valid_json is True
    assert invalid_response.schema_valid is False


@pytest.mark.parametrize("ref", PromptRegistry(prompt_root=PROMPT_ROOT).list_prompt_refs())
def test_prompt_output_schemas_are_recursively_strict(ref: str) -> None:
    contract = _load(ref)
    Draft7Validator.check_schema(contract.output_schema)
    assert contract.output_schema["additionalProperties"] is False
    for object_schema in _walk_schema_objects(contract.output_schema):
        assert object_schema["additionalProperties"] is False


def test_prompt_manifest_does_not_import_prompt_optimization_frameworks() -> None:
    import memorii.core.prompts.manifest as manifest

    assert "dspy" not in manifest.__dict__
