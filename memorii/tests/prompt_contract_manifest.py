from __future__ import annotations

from copy import deepcopy
from typing import Any

from memorii.core.prompts.runtime_manifest import PromptOwner
from memorii.core.prompts.sensitivity import ORACLE_INPUT_FIELDS, SECRET_KEYS
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SECRET_KEYS = sorted(SECRET_KEYS)
_ORACLE_KEYS = sorted(ORACLE_INPUT_FIELDS)


class PromptContractManifestEntry(BaseModel):
    prompt_ref: str
    owning_adapter: PromptOwner
    expected_input_variables: list[str]
    representative_variables: dict[str, Any]
    output_schema_owner: str
    fake_valid_output: dict[str, Any]
    fake_invalid_output: dict[str, Any] = Field(default_factory=lambda: {"unexpected_field": True})
    forbidden_live_prompt_keys: list[str] = Field(default_factory=list)
    no_leakage_rules: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @field_validator("prompt_ref", "output_schema_owner")
    @classmethod
    def _non_empty_string(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must be non-empty")
        return value

    @field_validator("expected_input_variables", "forbidden_live_prompt_keys", "no_leakage_rules")
    @classmethod
    def _unique_strings(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("list values must be unique")
        if any(not value.strip() for value in values):
            raise ValueError("list values must be non-empty")
        return values

    def render_variables(self) -> dict[str, Any]:
        return deepcopy(self.representative_variables)

    @model_validator(mode="after")
    def _output_schema_owner_matches_prompt_ref(self) -> PromptContractManifestEntry:
        expected = f"{self.prompt_ref}.output_schema"
        if self.output_schema_owner != expected:
            raise ValueError(f"output_schema_owner must be {expected}")
        return self


class PromptContractManifest(BaseModel):
    entries: list[PromptContractManifestEntry]

    model_config = ConfigDict(extra="forbid")

    @field_validator("entries")
    @classmethod
    def _unique_prompt_refs(cls, entries: list[PromptContractManifestEntry]) -> list[PromptContractManifestEntry]:
        refs = [entry.prompt_ref for entry in entries]
        if len(refs) != len(set(refs)):
            raise ValueError("prompt_ref values must be unique")
        return entries

    def by_prompt_ref(self) -> dict[str, PromptContractManifestEntry]:
        return {entry.prompt_ref: entry for entry in self.entries}


def _base_forbidden_keys(*extra: str) -> list[str]:
    return [*_SECRET_KEYS, *_ORACLE_KEYS, *extra]


def _base_rules(*extra: str) -> list[str]:
    return [
        "Rendered prompts must not contain secrets, API keys, tokens, or credentials.",
        "Rendered prompts must not contain hidden graph identifiers or hidden fact names.",
        "Rendered prompts must not contain oracle expected IDs, answers, excluded IDs, or judge outputs.",
        *extra,
    ]


def _judge_output() -> dict[str, Any]:
    return {
        "passed": True,
        "score": 0.9,
        "rationale": "The candidate satisfies the rubric.",
        "failure_mode": None,
        "needs_human_review": False,
    }


def _judge_entry(prompt_ref: str, dimension: str) -> PromptContractManifestEntry:
    return PromptContractManifestEntry(
        prompt_ref=prompt_ref,
        owning_adapter=PromptOwner.LLM_JUDGE_DECISION_ADAPTER,
        expected_input_variables=["rubric_json", "input_payload"],
        representative_variables={
            "rubric_json": {"dimension": dimension, "criteria": ["Use supplied evidence only."]},
            "input_payload": {"candidate_id": "candidate_1", "summary": "Evidence-backed candidate."},
        },
        output_schema_owner=f"{prompt_ref}.output_schema",
        fake_valid_output=_judge_output(),
        forbidden_live_prompt_keys=_base_forbidden_keys(),
        no_leakage_rules=_base_rules(),
    )


PROMPT_CONTRACT_MANIFEST = PromptContractManifest(
    entries=[
        PromptContractManifestEntry(
            prompt_ref="answer_verification:v1",
            owning_adapter=PromptOwner.LLM_ANSWER_VERIFICATION_ADAPTER,
            expected_input_variables=["context_json", "query"],
            representative_variables={
                "context_json": {
                    "question": "Who owns Atlas?",
                    "proposed_answer": "Bob",
                    "selected_evidence": [{"candidate_id": "cand_1", "text": "Atlas owner is Bob."}],
                },
                "query": "Who owns Atlas?",
            },
            output_schema_owner="answer_verification:v1.output_schema",
            fake_valid_output={
                "entailed": True,
                "corrected_answer": None,
                "required_candidate_ids": ["cand_1"],
                "missing_candidate_ids": [],
                "question_constraints": [
                    {
                        "constraint_id": "constraint_1",
                        "description": "Identify the Atlas owner.",
                        "satisfied": True,
                        "candidate_ids": ["cand_1"],
                        "rationale": "The candidate directly states the owner.",
                    }
                ],
                "alternative_answers": [],
                "confidence": 0.9,
                "rationale": "The cited evidence entails the answer.",
                "failure_mode": None,
                "requires_judge_review": False,
            },
            forbidden_live_prompt_keys=_base_forbidden_keys(),
            no_leakage_rules=_base_rules(),
        ),
        PromptContractManifestEntry(
            prompt_ref="belief_update:v1",
            owning_adapter=PromptOwner.LLM_BELIEF_UPDATE_ADAPTER,
            expected_input_variables=["context_json"],
            representative_variables={
                "context_json": {
                    "prior_belief": None,
                    "decision": "SUPPORTED",
                    "evidence_count": 2,
                    "missing_evidence_count": 0,
                    "verifier_downgraded": False,
                    "conflict_count": 0,
                    "evidence_ids": ["evidence:1", "evidence:2"],
                    "missing_evidence": [],
                    "evidence_quality": {
                        "entity_attribution": "aligned",
                        "independence": "independent",
                        "freshness": "current",
                        "observability": "complete",
                        "source_count": 2,
                        "oscillation_detected": False,
                    },
                }
            },
            output_schema_owner="belief_update:v1.output_schema",
            fake_valid_output={
                "belief": 0.7,
                "confidence": 0.8,
                "rationale": "Independent evidence supports increasing belief.",
                "failure_mode": None,
                "requires_judge_review": False,
            },
            forbidden_live_prompt_keys=_base_forbidden_keys(),
            no_leakage_rules=_base_rules(),
        ),
        PromptContractManifestEntry(
            prompt_ref="evidence_selection:v1",
            owning_adapter=PromptOwner.LLM_EVIDENCE_SELECTION_ADAPTER,
            expected_input_variables=["context_json", "query"],
            representative_variables={
                "context_json": {"candidates": [{"candidate_id": "cand_1", "text": "Atlas owner is Bob."}]},
                "query": "Who owns Atlas?",
            },
            output_schema_owner="evidence_selection:v1.output_schema",
            fake_valid_output={
                "selected_candidate_ids": ["cand_1"],
                "excluded_candidate_ids": [],
                "ranking": ["cand_1"],
                "proof_steps": [
                    {
                        "step_id": "step_1",
                        "description": "Find direct owner evidence.",
                        "candidate_ids": ["cand_1"],
                        "required_candidate_ids": ["cand_1"],
                        "citations": [
                            {
                                "candidate_id": "cand_1",
                                "role": "direct_answer",
                                "required_for_final_support": True,
                                "claim_supported": "Atlas owner is Bob.",
                                "rationale": "Directly states the answer.",
                            }
                        ],
                        "rationale": "The single candidate is sufficient.",
                    }
                ],
                "confidence": 0.9,
                "rationale": "Selected direct evidence only.",
                "failure_mode": None,
                "requires_judge_review": False,
            },
            forbidden_live_prompt_keys=_base_forbidden_keys(),
            no_leakage_rules=_base_rules(),
        ),
        PromptContractManifestEntry(
            prompt_ref="execution_graph_decision:v1",
            owning_adapter=PromptOwner.LLM_EXECUTION_GRAPH_DECISION_ADAPTER,
            expected_input_variables=["context_json", "task"],
            representative_variables={
                "context_json": {"task": "Continue previous fix", "nodes": [{"node_id": "node_b", "status": "ready"}]},
                "task": "Continue previous fix",
            },
            output_schema_owner="execution_graph_decision:v1.output_schema",
            fake_valid_output={
                "selected_node_ids": ["node_b"],
                "active_frontier_node_ids": ["node_b"],
                "blocked_node_ids": [],
                "abandoned_node_ids": [],
                "stale_node_ids": [],
                "resumed_node_id": "node_b",
                "next_action": "Continue node_b.",
                "confidence": 0.85,
                "rationale": "node_b is the active frontier.",
                "failure_mode": None,
                "requires_judge_review": False,
            },
            forbidden_live_prompt_keys=_base_forbidden_keys(),
            no_leakage_rules=_base_rules(),
        ),
        PromptContractManifestEntry(
            prompt_ref="grounded_answer:v1",
            owning_adapter=PromptOwner.LLM_GROUNDED_ANSWER_ADAPTER,
            expected_input_variables=["context_json", "query"],
            representative_variables={
                "context_json": {
                    "query": "Who owns Atlas?",
                    "selected_candidate_ids": ["cand_1"],
                    "candidates": [{"candidate_id": "cand_1", "text": "Atlas owner is Bob."}],
                },
                "query": "Who owns Atlas?",
            },
            output_schema_owner="grounded_answer:v1.output_schema",
            fake_valid_output={
                "answer": "Bob",
                "citation_candidate_ids": ["cand_1"],
                "answer_requirements": [
                    {
                        "requirement_id": "req_1",
                        "description": "Answer names the Atlas owner.",
                        "requirement_type": "direct_answer",
                        "candidate_ids": ["cand_1"],
                        "rationale": "Candidate states the owner.",
                    }
                ],
                "candidate_answers_considered": [
                    {
                        "answer": "Bob",
                        "candidate_ids": ["cand_1"],
                        "answer_type": "entity",
                        "requirement_coverage": [
                            {
                                "requirement_id": "req_1",
                                "satisfied": True,
                                "candidate_ids": ["cand_1"],
                                "rationale": "The candidate states the owner.",
                            }
                        ],
                        "satisfied_requirement_ids": ["req_1"],
                        "missing_requirement_ids": [],
                        "selected": True,
                        "rationale": "Directly supported.",
                    }
                ],
                "answer_type": "entity",
                "answer_span_candidate_id": "cand_1",
                "answer_span_text": "Bob",
                "confidence": 0.9,
                "rationale": "The answer is grounded in the cited candidate.",
                "failure_mode": None,
                "requires_judge_review": False,
            },
            forbidden_live_prompt_keys=_base_forbidden_keys(),
            no_leakage_rules=_base_rules(),
        ),
        PromptContractManifestEntry(
            prompt_ref="hotpotqa_answer:v1",
            owning_adapter=PromptOwner.LLM_HOTPOTQA_ANSWER_ADAPTER,
            expected_input_variables=["context_json", "question"],
            representative_variables={
                "context_json": {"question": "Which city is the capital of France?", "context": []},
                "question": "Which city is the capital of France?",
            },
            output_schema_owner="hotpotqa_answer:v1.output_schema",
            fake_valid_output={
                "answer": "Paris",
                "supporting_facts": [{"title": "France", "sentence_index": 0}],
                "confidence": 0.9,
                "rationale": "The context states the capital.",
            },
            forbidden_live_prompt_keys=_base_forbidden_keys(),
            no_leakage_rules=_base_rules(),
        ),
        _judge_entry("judges/attribution:v1", "attribution"),
        _judge_entry("judges/belief_direction:v1", "belief_direction"),
        _judge_entry("judges/memory_plane:v1", "memory_plane"),
        _judge_entry("judges/promotion_precision:v1", "promotion_precision"),
        _judge_entry("judges/temporal_validity:v1", "temporal_validity"),
        PromptContractManifestEntry(
            prompt_ref="lifecycle_decision:v1",
            owning_adapter=PromptOwner.LLM_LIFECYCLE_DECISION_ADAPTER,
            expected_input_variables=["context_json", "query"],
            representative_variables={
                "context_json": {"query": "current owner", "memories": []},
                "query": "current owner",
            },
            output_schema_owner="lifecycle_decision:v1.output_schema",
            fake_valid_output={
                "selected_retrieval_ids": ["mem_1"],
                "active_memory_ids": ["mem_1"],
                "inactive_memory_ids": [],
                "archived_memory_ids": [],
                "belief_scores": [{"memory_id": "mem_1", "belief": 0.9}],
                "merged_summary": "mem_1 is active.",
                "confidence": 0.85,
                "rationale": "Active memory answers the query.",
                "failure_mode": None,
                "requires_judge_review": False,
            },
            forbidden_live_prompt_keys=_base_forbidden_keys(),
            no_leakage_rules=_base_rules(),
        ),
        PromptContractManifestEntry(
            prompt_ref="memory_evolution_decision:v1",
            owning_adapter=PromptOwner.LLM_MEMORY_EVOLUTION_DECISION_ADAPTER,
            expected_input_variables=["context_json", "query"],
            representative_variables={
                "context_json": {
                    "scenario_id": "evolution_competing_belief_reranking",
                    "family": "competing_belief_reranking",
                    "events": [
                        {
                            "event_id": "belief:a-network-saturation",
                            "timestamp": "2026-05-02T10:00:00Z",
                            "source_type": "assistant",
                            "content": "Hypothesis A: network saturation is possible at 40 percent.",
                            "entity_ids": ["incident-18"],
                            "task_id": None,
                            "scope": None,
                            "trust_level": 2,
                        },
                        {
                            "event_id": "evidence:workers-exhausted",
                            "timestamp": "2026-05-02T10:10:00Z",
                            "source_type": "tool",
                            "content": "Tool evidence supports B worker exhaustion and weakens A network saturation.",
                            "entity_ids": ["incident-18"],
                            "task_id": None,
                            "scope": None,
                            "trust_level": 4,
                        },
                    ],
                    "checkpoint": {
                        "checkpoint_id": "checkpoint:belief-reranking",
                        "timestamp": "2026-05-02T10:15:00Z",
                        "query_or_task": "Rank the current root-cause beliefs.",
                    },
                    "visible_memory_cards": [
                        {
                            "memory_id": "belief:a-network-saturation",
                            "memory_kind": "belief",
                            "statement": "Hypothesis A: network saturation is possible at 40 percent.",
                            "timestamp": "2026-05-02T10:00:00Z",
                            "source_type": "assistant",
                            "trust_level": 2,
                            "entity_ids": ["incident-18"],
                            "task_id": None,
                            "scope": None,
                        },
                        {
                            "memory_id": "evidence:workers-exhausted",
                            "memory_kind": "evidence",
                            "statement": "Tool evidence supports B worker exhaustion and weakens A network saturation.",
                            "timestamp": "2026-05-02T10:10:00Z",
                            "source_type": "tool",
                            "trust_level": 4,
                            "entity_ids": ["incident-18"],
                            "task_id": None,
                            "scope": None,
                        },
                    ],
                    "evidence_effect_cards": [
                        {
                            "evidence_memory_id": "evidence:workers-exhausted",
                            "supports_memory_ids": ["belief:b-worker-exhaustion"],
                            "weakens_memory_ids": ["belief:a-network-saturation"],
                            "falsifies_memory_ids": [],
                            "dependency_memory_ids": [],
                            "extraction_basis": "surface_text_pattern",
                        }
                    ],
                    "metadata": {
                        "output_channel_contract": {
                            "belief_scores": "Rank belief ids with calibrated probabilities.",
                            "answer_selection.citation_memory_ids": "Only direct evidence/source ids, not ranked belief ids.",
                        },
                        "evidence_effect_policy": {"ranking_order": "supported > neutral > weakened > falsified"},
                    },
                },
                "query": "Rank the current root-cause beliefs.",
            },
            output_schema_owner="memory_evolution_decision:v1.output_schema",
            fake_valid_output={
                "operation": "answer",
                "answer": "worker exhaustion",
                "next_action": None,
                "confidence": 0.9,
                "query_temporal_frame": {
                    "temporal_reference": "current",
                    "decision_domain": "belief",
                    "scope_kind": "none",
                    "scope_key": None,
                    "anchor_id": None,
                    "valid_from": None,
                    "valid_to": None,
                    "confidence": 0.9,
                    "rationale": "The query asks for current belief ranking.",
                },
                "answer_selection": {
                    "selected_memory_ids": ["belief:b-worker-exhaustion"],
                    "supporting_memory_ids": ["belief:b-worker-exhaustion"],
                    "citation_memory_ids": ["evidence:workers-exhausted"],
                    "temporal_reference": "current",
                    "rationale": "Worker exhaustion is the top supported belief.",
                },
                "lifecycle_snapshot": {
                    "checkpoint_active_record_ids": [],
                    "checkpoint_superseded_record_ids": [],
                    "checkpoint_retained_record_ids": [],
                    "evaluation_time": "2026-05-02T10:15:00Z",
                    "rationale": "Belief ranking does not mark hypotheses as current active facts.",
                },
                "retrieval_context": {
                    "query_relevant_memory_ids": ["belief:b-worker-exhaustion", "evidence:workers-exhausted"],
                    "query_historical_memory_ids": [],
                    "query_context_memory_ids": [],
                    "rejected_memory_ids": [],
                    "rationale": "The evidence card explains the ranking.",
                },
                "execution_selection": None,
                "evaluated_belief_ids": [
                    "belief:b-worker-exhaustion",
                    "belief:c-database-locks",
                    "belief:a-network-saturation",
                ],
                "belief_scores": [
                    {"memory_id": "belief:b-worker-exhaustion", "belief": 0.7, "belief_state": "unknown"},
                    {"memory_id": "belief:c-database-locks", "belief": 0.2, "belief_state": "unknown"},
                    {"memory_id": "belief:a-network-saturation", "belief": 0.1, "belief_state": "unknown"},
                ],
                "rationale": "Tool evidence supports worker exhaustion and justifies the reranking.",
                "failure_mode": None,
                "requires_judge_review": False,
            },
            forbidden_live_prompt_keys=_base_forbidden_keys(),
            no_leakage_rules=_base_rules("Benchmark prompt inputs must be sanitized before rendering."),
        ),
        PromptContractManifestEntry(
            prompt_ref="memory_evolution_sim_reconstruction:v1",
            owning_adapter=PromptOwner.LLM_MEMORY_EVOLUTION_SIM_RECONSTRUCTION_ADAPTER,
            expected_input_variables=["context_json", "query"],
            representative_variables={
                "context_json": {
                    "scenario_id": "scenario_1",
                    "visible_events": [{"event_id": "event_1", "text": "Atlas owner is Bob."}],
                    "checkpoint": {"checkpoint_id": "cp_1", "query_or_task": "Who owns Atlas?"},
                },
                "query": "Who owns Atlas?",
            },
            output_schema_owner="memory_evolution_sim_reconstruction:v1.output_schema",
            fake_valid_output={
                "operation": "answer",
                "belief_ranking_ids": [],
                "selected_entity_ids": ["ent_atlas"],
                "selected_claim_ids": ["claim_owner"],
                "selected_relation_ids": [],
                "supporting_claim_ids": ["claim_owner"],
                "supporting_relation_ids": [],
                "supporting_citation_event_ids": ["event_1"],
                "rejected_entity_ids": [],
                "rejected_claim_ids": [],
                "rejected_relation_ids": [],
                "rejection_citation_event_ids": [],
                "context_entity_ids": [],
                "context_claim_ids": [],
                "context_relation_ids": [],
                "context_citation_event_ids": [],
                "answer": "Bob",
                "next_action": None,
                "uncertain_ids": [],
                "confidence": 0.9,
                "rationale": "Selected the visible current ownership claim.",
            },
            forbidden_live_prompt_keys=_base_forbidden_keys("excluded_ids"),
            no_leakage_rules=_base_rules("Latent graph oracle fields must never enter live reconstruction prompts."),
        ),
        PromptContractManifestEntry(
            prompt_ref="memory_extraction:v1",
            owning_adapter=PromptOwner.LLM_MEMORY_EXTRACTOR,
            expected_input_variables=["source_observations"],
            representative_variables={
                "source_observations": [{"source_id": "event_1", "text": "Remember that Atlas owner is Bob."}]
            },
            output_schema_owner="memory_extraction:v1.output_schema",
            fake_valid_output={"entities": [], "claims": [], "actions": []},
            forbidden_live_prompt_keys=_base_forbidden_keys(),
            no_leakage_rules=_base_rules("Extraction prompts must not receive benchmark oracle data."),
        ),
        PromptContractManifestEntry(
            prompt_ref="promotion_decision:v1",
            owning_adapter=PromptOwner.LLM_PROMOTION_DECISION_ADAPTER,
            expected_input_variables=["context_json", "candidate_summary"],
            representative_variables={
                "context_json": {
                    "candidate_id": "candidate_1",
                    "candidate_type": "episodic",
                    "content": "Implemented the benchmark runner.",
                    "source_ids": ["event_1"],
                    "related_memory_ids": [],
                    "repeated_across_episodes": 1,
                    "explicit_user_memory_request": False,
                    "created_from": "task_outcome",
                    "evidence_quality": {
                        "entity_attribution": "aligned",
                        "independence": "independent",
                        "freshness": "current",
                        "observability": "complete",
                        "source_count": 1,
                        "oscillation_detected": False,
                    },
                },
                "candidate_summary": "Implemented the benchmark runner.",
            },
            output_schema_owner="promotion_decision:v1.output_schema",
            fake_valid_output={
                "promote": True,
                "target_plane": "episodic",
                "confidence": 0.82,
                "reason_code": "task_outcome",
                "rationale": "The candidate records a completed task outcome.",
                "failure_mode": None,
                "requires_judge_review": False,
            },
            forbidden_live_prompt_keys=_base_forbidden_keys(),
            no_leakage_rules=_base_rules(),
        ),
        PromptContractManifestEntry(
            prompt_ref="retrieval_relevance:v1",
            owning_adapter=PromptOwner.LLM_RETRIEVAL_RELEVANCE_DECISION_ADAPTER,
            expected_input_variables=["context_json", "query"],
            representative_variables={
                "context_json": {"candidates": [{"id": "mem_1", "text": "Atlas owner is Bob."}]},
                "query": "Who owns Atlas?",
            },
            output_schema_owner="retrieval_relevance:v1.output_schema",
            fake_valid_output={
                "selected_ids": ["mem_1"],
                "excluded_ids": [],
                "ranking": ["mem_1"],
                "abstain": False,
                "confidence": 0.9,
                "rationale": "The selected memory directly answers the query.",
                "failure_mode": None,
                "requires_judge_review": False,
            },
            forbidden_live_prompt_keys=_base_forbidden_keys(),
            no_leakage_rules=_base_rules(),
        ),
        PromptContractManifestEntry(
            prompt_ref="structured_query_analysis:v1",
            owning_adapter=PromptOwner.STRUCTURED_QUERY_ANALYSIS_PROVIDER,
            expected_input_variables=["query", "context_json"],
            representative_variables={
                "query": "Who owns Atlas now?",
                "context_json": {
                    "language": "en",
                    "reference_time": "2026-07-19T00:00:00Z",
                    "scope_kind": "task",
                    "entities": [{"entity_id": "entity_1", "names": ["Atlas"], "entity_type": "project"}],
                    "temporal_anchors": [],
                    "predicates": [
                        {
                            "predicate_id": "owner",
                            "description": "The owner of an entity.",
                            "value_type": "text",
                        }
                    ],
                    "graph_operators": ["equals", "in", "not_equals", "not_in"],
                },
            },
            output_schema_owner="structured_query_analysis:v1.output_schema",
            fake_valid_output={
                "language": "en",
                "temporal_intent": "current",
                "temporal_expression": {"expression_kind": "current"},
                "candidate_entity_ids": ["entity_1"],
                "predicate_id": "owner",
                "subject_entity_id": "entity_1",
                "graph_patterns": [],
                "entity_mentions": ["Atlas"],
                "model_confidence": 0.9,
                "abstention_reason": None,
            },
            forbidden_live_prompt_keys=_base_forbidden_keys(),
            no_leakage_rules=_base_rules(
                "The model receives catalog labels but never authoritative intervals, scope keys, or hidden entities."
            ),
        ),
    ]
)


def prompt_contract_manifest() -> PromptContractManifest:
    return PROMPT_CONTRACT_MANIFEST


def prompt_contract_manifest_by_ref() -> dict[str, PromptContractManifestEntry]:
    return PROMPT_CONTRACT_MANIFEST.by_prompt_ref()
