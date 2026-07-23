from __future__ import annotations

import json
import re
from copy import deepcopy
from inspect import signature
from pathlib import Path
from typing import get_args

import pytest
import yaml
from jsonschema import Draft7Validator
from memorii.core.benchmark.fixture_sets.memory_evolution_v1 import load_memory_evolution_v1_fixture_set
from memorii.core.benchmark.fixture_sets.retrieval_corruption_v1 import (
    load_retrieval_corruption_v1_fixture_set,
)
from memorii.core.benchmark.llm_adapters import (
    LLMExecutionGraphDecisionAdapter,
    LLMHotpotQAAnswerAdapter,
    LLMLifecycleDecisionAdapter,
    LLMMemoryEvolutionDecisionAdapter,
    LLMMemoryEvolutionSimReconstructionAdapter,
    LLMRetrievalRelevanceDecisionAdapter,
)
from memorii.core.benchmark.memory_evolution_decision import memory_evolution_context_for_checkpoint
from memorii.core.benchmark.memory_evolution_decision.contracts import MemoryEvolutionDecision
from memorii.core.benchmark.memory_evolution_sim import (
    generate_memory_evolution_sim_scenarios,
    sim_reconstruction_context_for_checkpoint,
)
from memorii.core.benchmark.retrieval_relevance_decision import (
    RetrievalRelevanceContext,
    retrieval_relevance_context_for_fixture,
)
from memorii.core.grounding.models import EvidenceSelectionDecision, GroundedAnswerDecision
from memorii.core.llm_decision.adapters import (
    LLMAnswerVerificationAdapter,
    LLMBeliefUpdateAdapter,
    LLMEvidenceSelectionAdapter,
    LLMGroundedAnswerAdapter,
    LLMJudgeDecisionAdapter,
    LLMPromotionAssessmentAdapter,
    default_judge_prompt_refs,
)
from memorii.core.llm_provider.models import LLMStructuredResponse
from memorii.core.llm_provider.parser import parse_structured_response
from memorii.core.memory_evolution.extraction import LLMMemoryExtractor
from memorii.core.memory_evolution.query_analysis.provider import PromptBackedStructuredQueryAnalysisProvider
from memorii.core.memory_evolution.temporal_contracts import TemporalInterpretationProposal
from memorii.core.prompts.models import PromptContract
from memorii.core.prompts.registry import (
    PromptRegistry,
    RegisteredPromptContract,
    default_prompt_root,
    prompt_registration_digest,
)
from memorii.core.prompts.render import PromptRenderer, redact_variables
from memorii.core.prompts.runtime_manifest import (
    PromptOwner,
    PromptSemanticContract,
    prompt_runtime_registrations,
)
from memorii.core.prompts.schema_parity import (
    assert_output_schema_matches_model,
    assert_supported_json_schema,
)
from pydantic import BaseModel, ValidationError
from tests.prompt_contract_manifest import PromptContractManifestEntry, prompt_contract_manifest_by_ref

PROMPT_ROOT = default_prompt_root()
_ADVERSARIAL_SENTINELS = {
    "SECRET_SHOULD_NOT_RENDER",
    "HIDDEN_ID_SHOULD_NOT_RENDER",
    "ORACLE_EXPECTED_SHOULD_NOT_RENDER",
    "JUDGE_OUTPUT_SHOULD_NOT_RENDER",
}


def _load(ref: str) -> RegisteredPromptContract:
    entry = prompt_contract_manifest_by_ref()[ref]
    return PromptRegistry(prompt_root=PROMPT_ROOT).load(
        ref,
        owner=entry.owning_adapter,
        output_model=_OUTPUT_MODELS_BY_REF[ref],
    )


def _replace_registered(
    contract: RegisteredPromptContract,
    **updates: object,
) -> RegisteredPromptContract:
    modified = contract.model_copy(update=updates)
    return modified.model_copy(
        update={
            "registration_digest": prompt_registration_digest(
                modified,
                modified.runtime_registration,
            ),
        }
    )


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
    PromptOwner.LLM_MEMORY_EVOLUTION_DECISION_ADAPTER: (
        LLMMemoryEvolutionDecisionAdapter,
        "memory_evolution_decision:v1",
    ),
    PromptOwner.LLM_MEMORY_EVOLUTION_SIM_RECONSTRUCTION_ADAPTER: (
        LLMMemoryEvolutionSimReconstructionAdapter,
        "memory_evolution_sim_reconstruction:v1",
    ),
    PromptOwner.LLM_PROMOTION_DECISION_ADAPTER: (LLMPromotionAssessmentAdapter, "promotion_decision:v1"),
    PromptOwner.LLM_RETRIEVAL_RELEVANCE_DECISION_ADAPTER: (
        LLMRetrievalRelevanceDecisionAdapter,
        "retrieval_relevance:v1",
    ),
}

_OUTPUT_MODELS_BY_REF = {
    prompt_ref: adapter_cls.output_model for adapter_cls, prompt_ref in _OWNER_DEFAULT_PROMPT_REFS.values()
}
_OUTPUT_MODELS_BY_REF.update(
    {ref: LLMJudgeDecisionAdapter.output_model for ref in default_judge_prompt_refs().values()}
)
_OUTPUT_MODELS_BY_REF[LLMMemoryExtractor.prompt_ref] = LLMMemoryExtractor.output_model
_OUTPUT_MODELS_BY_REF[PromptBackedStructuredQueryAnalysisProvider.prompt_ref] = (
    PromptBackedStructuredQueryAnalysisProvider.output_model
)

_SEMANTIC_MODELS_BY_REF = {
    "evidence_selection:v1": EvidenceSelectionDecision,
    "grounded_answer:v1": GroundedAnswerDecision,
    "memory_evolution_decision:v1": MemoryEvolutionDecision,
    "structured_query_analysis:v1": TemporalInterpretationProposal,
}


def _semantic_adversarial_payload(ref: str) -> dict[str, object]:
    payload = deepcopy(prompt_contract_manifest_by_ref()[ref].fake_valid_output)
    if ref == "evidence_selection:v1":
        payload["proof_steps"][0]["citations"] = []
    elif ref == "grounded_answer:v1":
        payload["candidate_answers_considered"][0]["selected"] = False
    elif ref == "memory_evolution_decision:v1":
        payload["execution_selection"] = {
            "selected_action_memory_ids": [],
            "active_work_state_memory_ids": [],
            "command_context_memory_ids": [],
            "suppressed_branch_memory_ids": [],
            "rationale": "Invalid for an answer operation.",
        }
    elif ref == "structured_query_analysis:v1":
        payload["temporal_intent"] = "ambiguous"
        payload["abstention_reason"] = "Multiple temporal frames remain plausible."
    else:
        raise AssertionError(f"No semantic adversary registered for {ref}")
    return payload


def test_prompt_contract_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        PromptContract.model_validate(
            {
                "prompt_id": "a",
                "version": "v1",
                "task": "t",
                "description": "d",
                "input_schema": {},
                "output_schema": {},
                "system_template": "s",
                "user_template": "u",
                "model_defaults": {},
                "redaction": {},
                "extra": 1,
            }
        )


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
        assert (
            reg.load(
                ref,
                owner=prompt_contract_manifest_by_ref()[ref].owning_adapter,
                output_model=_OUTPUT_MODELS_BY_REF[ref],
            ).version
            == "v1"
        )


def test_registry_rejects_malformed_missing_and_traversal() -> None:
    reg = PromptRegistry(prompt_root=PROMPT_ROOT)
    with pytest.raises(ValueError):
        reg.load(
            "badref",
            owner=PromptOwner.LLM_PROMOTION_DECISION_ADAPTER,
            output_model=LLMPromotionAssessmentAdapter.output_model,
        )
    with pytest.raises(ValueError, match="not registered"):
        reg.load(
            "unknown:v1",
            owner=PromptOwner.LLM_PROMOTION_DECISION_ADAPTER,
            output_model=LLMPromotionAssessmentAdapter.output_model,
        )
    with pytest.raises(ValueError):
        reg.load(
            "../x:v1",
            owner=PromptOwner.LLM_PROMOTION_DECISION_ADAPTER,
            output_model=LLMPromotionAssessmentAdapter.output_model,
        )
    with pytest.raises(ValueError):
        reg.load(
            "judges/../../x:v1",
            owner=PromptOwner.LLM_PROMOTION_DECISION_ADAPTER,
            output_model=LLMPromotionAssessmentAdapter.output_model,
        )


def test_registry_rejects_malformed_yaml(tmp_path: Path) -> None:
    root = tmp_path / "prompts"
    (root / "a").mkdir(parents=True)
    (root / "a" / "v1.yaml").write_text("- not-a-mapping")
    with pytest.raises(ValueError):
        PromptRegistry(prompt_root=root).load(
            "a:v1",
            owner=PromptOwner.LLM_PROMOTION_DECISION_ADAPTER,
            output_model=LLMPromotionAssessmentAdapter.output_model,
        )


def test_renderer_renders_and_hash_changes() -> None:
    contract = _load("promotion_decision:v1")
    renderer = PromptRenderer()
    vars1 = prompt_contract_manifest_by_ref()["promotion_decision:v1"].render_variables()
    out1 = renderer.render(contract=contract, variables=vars1)
    out2 = renderer.render(contract=contract, variables=vars1)
    changed = deepcopy(vars1)
    changed["candidate_summary"] = "A different candidate summary."
    out3 = renderer.render(contract=contract, variables=changed)
    assert out1.prompt_hash == out2.prompt_hash
    assert out1.prompt_hash != out3.prompt_hash
    assert "Implemented the benchmark runner" in out1.user


def test_renderer_rejects_unsafe_placeholders_and_missing() -> None:
    registered = _load("promotion_decision:v1")
    for template in ["bad {x.y}", "bad {x[0]}", "bad {x!r}", "bad {x:>5}"]:
        contract = _replace_registered(registered, system_template=template)
        with pytest.raises(ValueError):
            PromptRenderer().render(
                contract=contract, variables={"x": "ok", "context_json": {}, "candidate_summary": "c"}
            )

    with pytest.raises(ValueError, match="Prompt input validation failed"):
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
    for key in (
        "answer_requirements",
        "candidate_answers_considered",
        "answer_type",
        "answer_span_candidate_id",
        "answer_span_text",
    ):
        assert key in answer_contract.output_schema["required"]
        assert key in answer_contract.output_schema["properties"]
    candidate_schema = answer_contract.output_schema["properties"]["candidate_answers_considered"]["items"]
    for key in ("answer_type", "requirement_coverage", "satisfied_requirement_ids", "missing_requirement_ids"):
        assert key in candidate_schema["required"]
        assert key in candidate_schema["properties"]


def test_memory_extraction_prompt_schema_is_strict_for_openai() -> None:
    contract = _load("memory_extraction:v1")
    entity_schema = contract.output_schema["properties"]["entities"]["items"]
    claim_schema = contract.output_schema["properties"]["claims"]["items"]
    action_schema = contract.output_schema["properties"]["actions"]["items"]

    assert entity_schema["properties"]["entity_ref"]["minLength"] == 1
    assert claim_schema["properties"]["subject_entity_ref"]["minLength"] == 1
    assert action_schema["properties"]["action_ref"]["minLength"] == 1
    runtime_owned = {
        "entity_id",
        "claim_id",
        "action_id",
        "scope_key",
        "task_id",
        "session_id",
        "user_id",
        "timestamp",
        "valid_from",
        "valid_to",
    }
    assert runtime_owned.isdisjoint(entity_schema["properties"])
    assert runtime_owned.isdisjoint(claim_schema["properties"])
    assert runtime_owned.isdisjoint(action_schema["properties"])


def test_memory_evolution_sim_prompt_distinguishes_subject_and_answer_object_entities() -> None:
    contract = _load("memory_evolution_sim_reconstruction:v1")
    system = contract.system_template

    assert "subject entity" in system
    assert "object entity" in system
    assert "selected_entity_role_policy" in system
    assert "Query wording does not reverse graph endpoints" in system
    assert "definition_claim_placement" in system
    assert "belief_ranking_policy" in system
    assert "active visible definition/type claims" in system
    assert "operation=next_action" in system
    assert "conflict/correction relations" in system
    assert "latest eligible active action-state branch" in system


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
    manifest = prompt_contract_manifest_by_ref()
    for ref in PromptRegistry(prompt_root=PROMPT_ROOT).list_prompt_refs():
        contract = _load(ref)
        variables = manifest[ref].render_variables()
        rendered = renderer.render(contract=contract, variables=variables)
        assert rendered.prompt_ref == ref


def test_prompt_manifest_covers_every_checked_in_prompt() -> None:
    registry_refs = set(PromptRegistry(prompt_root=PROMPT_ROOT).list_prompt_refs())
    manifest_refs = set(prompt_contract_manifest_by_ref())

    assert manifest_refs == registry_refs


def test_runtime_prompt_registrations_match_conformance_manifest_and_yaml() -> None:
    registrations = prompt_runtime_registrations()
    manifest = prompt_contract_manifest_by_ref()
    yaml_refs = set(PromptRegistry(prompt_root=PROMPT_ROOT).list_prompt_refs())

    assert set(registrations) == set(manifest) == yaml_refs
    for ref, registration in registrations.items():
        entry = manifest[ref]
        assert registration.owning_adapter == entry.owning_adapter

    assert "expected_input_variables" not in type(next(iter(registrations.values()))).model_fields


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
        declared_prompt_ref = getattr(adapter_cls, "prompt_ref", None)
        if declared_prompt_ref is None:
            declared_prompt_ref = signature(adapter_cls.__init__).parameters["prompt_ref"].default
        assert declared_prompt_ref == prompt_ref
        assert manifest[prompt_ref].owning_adapter == owner

    judge_prompt_refs = set(default_judge_prompt_refs().values())
    assert {
        ref for ref, entry in manifest.items() if entry.owning_adapter == PromptOwner.LLM_JUDGE_DECISION_ADAPTER
    } == judge_prompt_refs
    assert manifest["memory_extraction:v1"].owning_adapter == PromptOwner.LLM_MEMORY_EXTRACTOR
    assert LLMMemoryExtractor.provider == "llm"
    assert LLMMemoryExtractor.prompt_ref == "memory_extraction:v1"


def test_production_prompt_registry_enforces_manifest_ownership() -> None:
    registry = PromptRegistry(prompt_root=PROMPT_ROOT)

    registry.load(
        "promotion_decision:v1",
        owner=PromptOwner.LLM_PROMOTION_DECISION_ADAPTER,
        output_model=LLMPromotionAssessmentAdapter.output_model,
    )
    with pytest.raises(ValueError, match="owned by"):
        registry.load(
            "promotion_decision:v1",
            owner=PromptOwner.LLM_BELIEF_UPDATE_ADAPTER,
            output_model=LLMPromotionAssessmentAdapter.output_model,
        )


def test_prompt_manifest_rejects_unknown_owner_and_schema_owner_drift() -> None:
    base_payload = prompt_contract_manifest_by_ref()["promotion_decision:v1"].model_dump(mode="json")

    with pytest.raises(ValidationError):
        PromptContractManifestEntry.model_validate({**base_payload, "owning_adapter": "LLMFakePotatoAdapter"})

    with pytest.raises(ValidationError):
        PromptContractManifestEntry.model_validate({**base_payload, "output_schema_owner": "other:v1.output_schema"})


@pytest.mark.parametrize("ref,entry", sorted(prompt_contract_manifest_by_ref().items()))
def test_prompt_manifest_render_variables_are_clean_and_renderable(
    ref: str, entry: PromptContractManifestEntry
) -> None:
    rendered = PromptRenderer().render(contract=_load(ref), variables=entry.render_variables())
    rendered_text = f"{rendered.system}\n{rendered.user}"

    assert rendered.prompt_ref == ref
    for key in entry.forbidden_live_prompt_keys:
        assert not _contains_key(entry.representative_variables, key), (
            f"{ref} representative variables contain forbidden key {key}"
        )
        assert f'"{key}"' not in rendered_text, f"{ref} rendered prompt leaked forbidden JSON key {key}"
    for fragment in _ADVERSARIAL_SENTINELS:
        assert fragment not in rendered_text


@pytest.mark.parametrize("ref,entry", sorted(prompt_contract_manifest_by_ref().items()))
def test_prompt_renderer_redacts_adversarial_nested_oracle_fields(
    ref: str,
    entry: PromptContractManifestEntry,
) -> None:
    contract = _load(ref)
    variables = entry.render_variables()
    structured_key = next(
        (key for key, value in variables.items() if isinstance(value, (dict, list))),
        None,
    )
    if structured_key is None:
        pytest.skip(f"{ref} has no structured prompt input")
    adversarial_fields = {
        "expected_answer": "ORACLE_EXPECTED_SHOULD_NOT_RENDER",
        "ExpectedExecutionClaimIds": ["HIDDEN_ID_SHOULD_NOT_RENDER"],
        "hidden_graph_items": [{"id": "HIDDEN_ID_SHOULD_NOT_RENDER"}],
        "Required-Judge-Ids": ["JUDGE_OUTPUT_SHOULD_NOT_RENDER"],
        "judge_votes": [{"score": "JUDGE_OUTPUT_SHOULD_NOT_RENDER"}],
        "ApiKey": "SECRET_SHOULD_NOT_RENDER",
    }
    structured_value = variables[structured_key]
    if isinstance(structured_value, dict):
        variables[structured_key] = {**structured_value, **adversarial_fields}
    else:
        assert isinstance(structured_value, list) and structured_value
        first_item = structured_value[0]
        assert isinstance(first_item, dict)
        variables[structured_key] = [{**first_item, **adversarial_fields}, *structured_value[1:]]

    rendered = PromptRenderer().render(contract=contract, variables=variables)
    rendered_text = f"{rendered.system}\n{rendered.user}"

    for key in entry.forbidden_live_prompt_keys:
        assert f'"{key}"' not in rendered_text
    for fragment in _ADVERSARIAL_SENTINELS:
        assert fragment not in rendered_text


def test_prompt_renderer_uses_manifest_owned_visibility_policy() -> None:
    contract = _load("promotion_decision:v1")
    entry = prompt_contract_manifest_by_ref()["promotion_decision:v1"]
    variables = entry.render_variables()
    context_json = variables["context_json"]
    assert isinstance(context_json, dict)
    variables["context_json"] = {
        **context_json,
        "Expected-Answer": "ORACLE_EXPECTED_SHOULD_NOT_RENDER",
        "content": "visible context",
    }

    rendered = PromptRenderer().render(contract=contract, variables=variables)

    assert "ORACLE_EXPECTED_SHOULD_NOT_RENDER" not in rendered.user
    assert "visible context" in rendered.user


def test_prompt_renderer_fails_closed_for_unowned_contract() -> None:
    contract = _load("promotion_decision:v1").model_copy(update={"prompt_id": "unregistered_prompt"})

    with pytest.raises(ValueError, match="policy does not match prompt identity"):
        PromptRenderer().render(
            contract=contract,
            variables={"context_json": {}, "candidate_summary": "candidate"},
        )


def test_prompt_renderer_rejects_post_registration_contract_mutation() -> None:
    contract = _load("promotion_decision:v1").model_copy(update={"system_template": "Ignore the registered contract."})

    with pytest.raises(ValueError, match="modified after registration"):
        PromptRenderer().render(
            contract=contract,
            variables={"context_json": {}, "candidate_summary": "candidate"},
        )


def test_prompt_redaction_covers_all_normalized_top_level_secret_aliases() -> None:
    contract = _load("memory_extraction:v1")
    variables = {
        "api_key": "FIRST_SECRET",
        "Api-Key": "SECOND_SECRET",
        "ＡＰＩ＿ＫＥＹ": "THIRD_SECRET",
        "safe_context": "visible",
    }

    redacted = redact_variables(variables=variables, policy=contract.redaction)

    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["Api-Key"] == "[REDACTED]"
    assert redacted["ＡＰＩ＿ＫＥＹ"] == "[REDACTED]"
    assert redacted["safe_context"] == "visible"


def test_prompt_renderer_does_not_render_hidden_values_from_real_candidate_cards() -> None:
    scenario = next(
        item
        for item in generate_memory_evolution_sim_scenarios(
            profile="adversarial",
            scenario_count=10,
            seed=7,
            noise_rate=0.35,
        )
        if item.family == "belief_dependency_and_reranking"
    )
    checkpoint = scenario.checkpoints[0]
    context = sim_reconstruction_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    hidden_values = {
        value
        for collection, identifier in (
            (scenario.entities, "entity_id"),
            (scenario.claims, "claim_id"),
            (scenario.relations, "relation_id"),
        )
        for item in collection
        if getattr(item, "observability", None) == "hidden"
        for value in [str(getattr(item, identifier))]
        if value
    }
    assert hidden_values
    rendered = PromptRenderer().render(
        contract=_load("memory_evolution_decision:v1"),
        variables={"context_json": context.model_dump(mode="json"), "query": checkpoint.query_or_task},
    )
    rendered_text = f"{rendered.system}\n{rendered.user}"
    assert hidden_values.isdisjoint(set(re.findall(r"[A-Za-z0-9_:-]+", rendered_text)))


def test_memory_evolution_decision_real_context_render_excludes_oracle_fields() -> None:
    scenario = next(
        item
        for item in load_memory_evolution_v1_fixture_set()
        if item.scenario_id == "evolution_competing_belief_reranking"
    )
    checkpoint = scenario.checkpoints[0]
    context = memory_evolution_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    rendered = PromptRenderer().render(
        contract=_load("memory_evolution_decision:v1"),
        variables={
            "context_json": context.model_dump(mode="json"),
            "query": checkpoint.query_or_task,
        },
    )
    rendered_text = f"{rendered.system}\n{rendered.user}"
    forbidden_expected_keys = [
        "expected_answer",
        "expected_next_action",
        "expected_retrieval_ids",
        "expected_citation_ids",
        "expected_excluded_memory_ids",
        "expected_checkpoint_active_record_ids",
        "expected_checkpoint_superseded_record_ids",
        "expected_checkpoint_retained_record_ids",
        "expected_belief_ranking",
        "expected_belief_scores",
    ]

    for forbidden_key in forbidden_expected_keys:
        assert f'"{forbidden_key}"' not in rendered_text


def test_retrieval_prompt_context_excludes_oracle_expectations_by_construction() -> None:
    fixture = load_retrieval_corruption_v1_fixture_set()[0]
    context = retrieval_relevance_context_for_fixture(fixture)
    payload = context.model_dump(mode="json")

    assert payload["metadata"] == {"category": fixture.category.value}
    assert not any(key.startswith("expected_") for key in payload["metadata"])
    with pytest.raises(ValidationError):
        RetrievalRelevanceContext.model_validate({**payload, "expected_relevant_ids": ["oracle:must-not-enter"]})


@pytest.mark.parametrize("ref,entry", sorted(prompt_contract_manifest_by_ref().items()))
def test_prompt_manifest_fake_outputs_parse_against_yaml_schema(ref: str, entry: PromptContractManifestEntry) -> None:
    valid_response = _parsed_schema_output(ref, entry.fake_valid_output)
    invalid_response = _parsed_schema_output(ref, entry.fake_invalid_output)

    assert valid_response.valid_json is True
    assert valid_response.schema_valid is True
    assert valid_response.parsed_json == entry.fake_valid_output
    assert _OUTPUT_MODELS_BY_REF[ref].model_validate(entry.fake_valid_output)
    assert invalid_response.valid_json is True
    assert invalid_response.schema_valid is False


@pytest.mark.parametrize("ref", sorted(_SEMANTIC_MODELS_BY_REF))
def test_schema_valid_transport_can_fail_only_at_explicit_semantic_boundary(ref: str) -> None:
    contract = _load(ref)
    payload = _semantic_adversarial_payload(ref)

    assert list(Draft7Validator(contract.output_schema).iter_errors(payload)) == []
    transport = _OUTPUT_MODELS_BY_REF[ref].model_validate(payload)
    with pytest.raises(ValidationError):
        _SEMANTIC_MODELS_BY_REF[ref].model_validate(transport.model_dump(mode="python"))


def test_runtime_manifest_declares_every_semantic_boundary() -> None:
    registrations = prompt_runtime_registrations()
    expected = {
        ref: PromptSemanticContract(model.__module__ + "." + model.__qualname__)
        for ref, model in _SEMANTIC_MODELS_BY_REF.items()
    }
    for ref, registration in registrations.items():
        assert registration.semantic_contract == expected.get(ref, PromptSemanticContract.NONE)


def test_semantic_prompt_adapters_supply_the_registered_domain_model() -> None:
    adapter_by_ref = {ref: adapter_cls for adapter_cls, ref in _OWNER_DEFAULT_PROMPT_REFS.values()}
    adapter_by_ref[PromptBackedStructuredQueryAnalysisProvider.prompt_ref] = PromptBackedStructuredQueryAnalysisProvider
    for ref, semantic_model in _SEMANTIC_MODELS_BY_REF.items():
        assert adapter_by_ref[ref].semantic_model is semantic_model


def test_registered_transport_models_have_no_hidden_custom_validators() -> None:
    visited: set[type[BaseModel]] = set()

    def visit(annotation: object) -> None:
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            if annotation in visited:
                return
            visited.add(annotation)
            decorators = annotation.__pydantic_decorators__
            assert decorators.field_validators == {}
            assert decorators.model_validators == {}
            for field in annotation.model_fields.values():
                visit(field.annotation)
            return
        for argument in get_args(annotation):
            visit(argument)

    for output_model in _OUTPUT_MODELS_BY_REF.values():
        visit(output_model)


def test_schema_parity_rejects_stricter_string_pattern() -> None:
    class UnconstrainedStringOutput(BaseModel):
        value: str

    prompt_schema = UnconstrainedStringOutput.model_json_schema()
    value_schema = prompt_schema["properties"]["value"]
    assert isinstance(value_schema, dict)
    value_schema["pattern"] = "^ONLY_THIS$"

    with pytest.raises(ValueError, match="does not match"):
        assert_output_schema_matches_model(
            prompt_ref="test_pattern:v1",
            output_schema=prompt_schema,
            output_model=UnconstrainedStringOutput,
        )


def test_schema_dialect_rejects_unproved_validation_keywords() -> None:
    with pytest.raises(ValueError, match="unsupported JSON Schema keywords"):
        assert_supported_json_schema(
            schema_name="unsupported",
            schema={"allOf": [{"type": "string"}]},
        )


def test_prompt_renderer_rejects_unexpected_and_wrongly_typed_inputs() -> None:
    contract = _load("promotion_decision:v1")
    variables = prompt_contract_manifest_by_ref()["promotion_decision:v1"].render_variables()
    unexpected = {**variables, "unregistered_context": "not allowed"}
    wrong_type = {**variables, "candidate_summary": 42}

    with pytest.raises(ValueError, match="Additional properties are not allowed"):
        PromptRenderer().render(contract=contract, variables=unexpected)
    with pytest.raises(ValueError, match="is not of type 'string'"):
        PromptRenderer().render(contract=contract, variables=wrong_type)


@pytest.mark.parametrize("ref", PromptRegistry(prompt_root=PROMPT_ROOT).list_prompt_refs())
def test_prompt_output_schemas_are_recursively_strict(ref: str) -> None:
    contract = _load(ref)
    Draft7Validator.check_schema(contract.output_schema)
    assert contract.output_schema["additionalProperties"] is False
    for object_schema in _walk_schema_objects(contract.output_schema):
        assert object_schema["additionalProperties"] is False


def test_prompt_manifest_does_not_import_prompt_optimization_frameworks() -> None:
    import tests.prompt_contract_manifest as manifest

    assert "dspy" not in manifest.__dict__
