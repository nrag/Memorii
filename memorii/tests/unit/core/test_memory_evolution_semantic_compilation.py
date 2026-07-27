from __future__ import annotations

from datetime import UTC, datetime

import pytest
from memorii.core.memory_evolution import (
    EntityResolutionService,
    ExtractionRunStatus,
    MemoryEvolutionMutationValidationError,
    MemoryEvolutionValidator,
    SemanticIngestionCompiler,
    SourceObservation,
)
from memorii.core.memory_evolution.extraction import models_from_llm_output
from memorii.core.memory_evolution.models import (
    ClaimTransitionType,
    EntityIdentityDecisionType,
    EntityLinkLifecycleState,
    ValidationVerdict,
)
from memorii.domain.enums import SourceType


def _observation(source_id: str, text: str, *, language: str = "en") -> SourceObservation:
    return SourceObservation(
        source_id=source_id,
        text=text,
        source_type=SourceType.USER,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        language=language,
    )


def _entity(
    *,
    entity_ref: str,
    mention_text: str,
    entity_type: str,
    source_id: str,
    quote: str,
) -> dict[str, object]:
    return {
        "entity_ref": entity_ref,
        "mention_text": mention_text,
        "entity_type": entity_type,
        "source_id": source_id,
        "quote": quote,
        "confidence": 0.9,
    }


def _proposal(
    *,
    observation: SourceObservation,
    entities: list[dict[str, object]],
    claims: list[dict[str, object]] | None = None,
    actions: list[dict[str, object]] | None = None,
    identity_relations: list[dict[str, object]] | None = None,
):
    return models_from_llm_output(
        run_id=f"run:{observation.source_id}",
        provider="recorded",
        model="recorded-model",
        prompt_hash="recorded-prompt",
        observations=[observation],
        output={
            "entities": entities,
            "claims": claims or [],
            "actions": actions or [],
            "identity_relations": identity_relations or [],
        },
    )


def _compiler() -> SemanticIngestionCompiler:
    return SemanticIngestionCompiler(
        entity_resolver=EntityResolutionService(),
        validator=MemoryEvolutionValidator(),
    )


def test_compiler_derives_action_from_grounded_action_state_claim() -> None:
    observation = _observation("tx:blocked", "Atlas migration is blocked.")
    proposal = _proposal(
        observation=observation,
        entities=[
            _entity(
                entity_ref="task",
                mention_text="Atlas migration",
                entity_type="task",
                source_id=observation.source_id,
                quote=observation.text,
            )
        ],
        claims=[
            {
                "subject_entity_ref": "task",
                "predicate_id": "action_state",
                "object_value": "blocked",
                "object_entity_ref": None,
                "source_id": observation.source_id,
                "quote": observation.text,
                "confidence": 0.9,
            }
        ],
    )

    compiled = _compiler().compile(
        proposal=proposal,
        observations=[observation],
        existing_entity_links=[],
    )

    assert len(compiled.actions) == 1
    assert compiled.actions[0].status == "blocked"
    assert compiled.actions[0].target_entity_ids == [compiled.claims[0].claim_key.subject_entity_id]


def test_compiler_derives_action_state_claim_from_grounded_action() -> None:
    observation = _observation("tx:resumed", "Atlas migration resumed.")
    proposal = _proposal(
        observation=observation,
        entities=[
            _entity(
                entity_ref="task",
                mention_text="Atlas migration",
                entity_type="task",
                source_id=observation.source_id,
                quote=observation.text,
            )
        ],
        actions=[
            {
                "action_ref": "resumed",
                "actor_entity_ref": None,
                "action_type": "work_state",
                "target_entity_refs": ["task"],
                "status": "resumed",
                "dependency_entity_refs": [],
                "blocking_entity_refs": [],
                "source_id": observation.source_id,
                "quote": observation.text,
            }
        ],
    )

    compiled = _compiler().compile(
        proposal=proposal,
        observations=[observation],
        existing_entity_links=[],
    )

    assert len(compiled.claims) == 1
    assert compiled.claims[0].claim_key.predicate_id == "action_state"
    assert compiled.claims[0].object_value == "resumed"


def test_source_grounding_rejects_negated_action_before_state_pair_compilation() -> None:
    observation = _observation("tx:conflict", "Atlas migration is blocked, not resumed.")
    proposal = _proposal(
        observation=observation,
        entities=[
            _entity(
                entity_ref="task",
                mention_text="Atlas migration",
                entity_type="task",
                source_id=observation.source_id,
                quote=observation.text,
            )
        ],
        claims=[
            {
                "subject_entity_ref": "task",
                "predicate_id": "action_state",
                "object_value": "blocked",
                "object_entity_ref": None,
                "source_id": observation.source_id,
                "quote": observation.text,
                "confidence": 0.9,
            }
        ],
        actions=[
            {
                "action_ref": "resumed",
                "actor_entity_ref": None,
                "action_type": "work_state",
                "target_entity_refs": ["task"],
                "status": "resumed",
                "dependency_entity_refs": [],
                "blocking_entity_refs": [],
                "source_id": observation.source_id,
                "quote": observation.text,
            }
        ],
    )

    assert proposal.run.status == ExtractionRunStatus.PARTIAL
    assert proposal.actions == []
    assert any("action semantics are not source-grounded:contradicted" in error for error in proposal.run.errors)


def test_spanish_owner_compiles_through_the_state_aware_boundary() -> None:
    observation = _observation(
        "tx:owner-es",
        "Alicia posee Atlas.",
        language="es-MX",
    )
    proposal = _proposal(
        observation=observation,
        entities=[
            _entity(
                entity_ref="alice",
                mention_text="Alicia",
                entity_type="person",
                source_id=observation.source_id,
                quote="Alicia",
            ),
            _entity(
                entity_ref="atlas",
                mention_text="Atlas",
                entity_type="project",
                source_id=observation.source_id,
                quote="Atlas",
            ),
        ],
        claims=[
            {
                "subject_entity_ref": "atlas",
                "predicate_id": "owner",
                "object_value": "Alicia",
                "object_entity_ref": "alice",
                "source_id": observation.source_id,
                "quote": "Alicia posee Atlas",
                "confidence": 0.9,
            }
        ],
    )

    compiled = _compiler().compile(
        proposal=proposal,
        observations=[observation],
        existing_entity_links=[],
    )

    assert proposal.run.status == ExtractionRunStatus.SUCCEEDED
    assert len(compiled.claims) == 1
    assert compiled.claims[0].claim_key.predicate_id == "owner"
    assert all(result.verdict != ValidationVerdict.FAIL for result in compiled.validation_results[compiled.claims[0].claim_id])


def test_generic_semantic_fact_is_never_promoted_as_active_truth() -> None:
    observation = _observation("tx:generic", "Atlas has a blue marker.")
    proposal = _proposal(
        observation=observation,
        entities=[
            _entity(
                entity_ref="atlas",
                mention_text="Atlas",
                entity_type="project",
                source_id=observation.source_id,
                quote=observation.text,
            )
        ],
        claims=[
            {
                "subject_entity_ref": "atlas",
                "predicate_id": "semantic_fact",
                "object_value": "blue marker",
                "object_entity_ref": None,
                "source_id": observation.source_id,
                "quote": observation.text,
                "confidence": 0.9,
            }
        ],
    )

    compiled = _compiler().compile(
        proposal=proposal,
        observations=[observation],
        existing_entity_links=[],
    )

    assert proposal.run.status == ExtractionRunStatus.SUCCEEDED
    assert any(
        result.validator_name == "semantic_fact_promotion_gate" and result.verdict == ValidationVerdict.FAIL
        for result in compiled.validation_results[compiled.claims[0].claim_id]
    )


def test_explicit_split_relation_overrides_alias_overlap_and_preserves_lineage() -> None:
    compiler = _compiler()
    parent_observation = _observation("tx:parent", "Atlas is a project.")
    parent = _proposal(
        observation=parent_observation,
        entities=[
            _entity(
                entity_ref="parent",
                mention_text="Atlas",
                entity_type="project",
                source_id=parent_observation.source_id,
                quote=parent_observation.text,
            )
        ],
    )
    parent_compilation = compiler.compile(
        proposal=parent,
        observations=[parent_observation],
        existing_entity_links=[],
    )
    parent_link = parent_compilation.entity_resolution.links[0]

    split_observation = _observation(
        "tx:split",
        "Atlas Service split from Atlas.",
    )
    split = _proposal(
        observation=split_observation,
        entities=[
            _entity(
                entity_ref="child",
                mention_text="Atlas Service",
                entity_type="service",
                source_id=split_observation.source_id,
                quote=split_observation.text,
            ),
            _entity(
                entity_ref="parent",
                mention_text="Atlas",
                entity_type="project",
                source_id=split_observation.source_id,
                quote=split_observation.text,
            ),
        ],
        identity_relations=[
            {
                "relation_ref": "split",
                "relation_type": "split_from",
                "source_entity_ref": "child",
                "target_entity_ref": "parent",
                "source_id": split_observation.source_id,
                "quote": split_observation.text,
                "confidence": 0.95,
            }
        ],
    )

    compiled = compiler.compile(
        proposal=split,
        observations=[split_observation],
        existing_entity_links=[parent_link],
    )

    child = next(link for link in compiled.entity_resolution.links if link.lineage_parent_entity_id is not None)
    assert child.canonical_entity_id != parent_link.canonical_entity_id
    assert child.lineage_parent_entity_id == parent_link.canonical_entity_id
    assert child.aliases == []
    assert "Atlas Service" in child.observed_names


def test_explicit_merge_relation_invalidates_duplicate_and_preserves_canonical_identity() -> None:
    compiler = _compiler()
    setup_observation = _observation(
        "tx:setup",
        "Atlas Billing Migration and Atlas Legacy are projects.",
    )
    setup = _proposal(
        observation=setup_observation,
        entities=[
            _entity(
                entity_ref="primary",
                mention_text="Atlas Billing Migration",
                entity_type="project",
                source_id=setup_observation.source_id,
                quote=setup_observation.text,
            ),
            _entity(
                entity_ref="duplicate",
                mention_text="Atlas Legacy",
                entity_type="project",
                source_id=setup_observation.source_id,
                quote=setup_observation.text,
            ),
        ],
    )
    existing = compiler.compile(
        proposal=setup,
        observations=[setup_observation],
        existing_entity_links=[],
    ).entity_resolution.links
    primary_id = next(
        link.canonical_entity_id for link in existing if link.normalized_name == "atlas billing migration"
    )
    duplicate_id = next(link.canonical_entity_id for link in existing if link.normalized_name == "atlas legacy")

    merge_observation = _observation(
        "tx:merge",
        "Atlas Legacy was merged into Atlas Billing Migration.",
    )
    merge = _proposal(
        observation=merge_observation,
        entities=[
            _entity(
                entity_ref="duplicate",
                mention_text="Atlas Legacy",
                entity_type="project",
                source_id=merge_observation.source_id,
                quote=merge_observation.text,
            ),
            _entity(
                entity_ref="primary",
                mention_text="Atlas Billing Migration",
                entity_type="project",
                source_id=merge_observation.source_id,
                quote=merge_observation.text,
            ),
        ],
        identity_relations=[
            {
                "relation_ref": "merge",
                "relation_type": "merged_into",
                "source_entity_ref": "duplicate",
                "target_entity_ref": "primary",
                "source_id": merge_observation.source_id,
                "quote": merge_observation.text,
                "confidence": 0.95,
            }
        ],
    )

    compiled = compiler.compile(
        proposal=merge,
        observations=[merge_observation],
        existing_entity_links=existing,
    )

    merged = next(link for link in compiled.entity_resolution.links if link.canonical_entity_id == primary_id)
    invalidated = next(link for link in compiled.entity_resolution.links if link.canonical_entity_id == duplicate_id)
    merge_decision = next(
        decision
        for decision in compiled.entity_resolution.decisions
        if decision.decision_type == EntityIdentityDecisionType.MERGE_EXISTING
    )
    assert invalidated.lifecycle_state == EntityLinkLifecycleState.MERGED
    assert invalidated.superseded_by_entity_id == primary_id
    assert "Atlas Legacy" in merged.observed_names
    assert merge_decision.resolved_entity_id == primary_id
    assert any(
        transition.transition_type == ClaimTransitionType.ENTITY_MERGE
        and transition.claim_id == primary_id
        and transition.related_claim_ids == [duplicate_id]
        for transition in compiled.transitions
    )


def test_compiler_rejects_multiple_outgoing_identity_relations() -> None:
    observation = _observation(
        "tx:identity-conflict",
        "Atlas Migration is an alias for Atlas and Atlas Project.",
    )
    proposal = _proposal(
        observation=observation,
        entities=[
            _entity(
                entity_ref="alias",
                mention_text="Atlas Migration",
                entity_type="project",
                source_id=observation.source_id,
                quote=observation.text,
            ),
            _entity(
                entity_ref="migration",
                mention_text="Atlas",
                entity_type="project",
                source_id=observation.source_id,
                quote=observation.text,
            ),
            _entity(
                entity_ref="project",
                mention_text="Atlas Project",
                entity_type="project",
                source_id=observation.source_id,
                quote=observation.text,
            ),
        ],
        identity_relations=[
            {
                "relation_ref": "alias-migration",
                "relation_type": "alias_of",
                "source_entity_ref": "alias",
                "target_entity_ref": "migration",
                "source_id": observation.source_id,
                "quote": observation.text,
                "confidence": 0.9,
            }
        ],
    )
    relation = proposal.identity_relations[0]
    conflicting = relation.model_copy(
        update={
            "relation_id": "identity-relation:conflicting",
            "target_entity_id": proposal.entities[2].entity_id,
        }
    )
    conflicting_proposal = proposal.model_copy(update={"identity_relations": [relation, conflicting]})

    with pytest.raises(
        MemoryEvolutionMutationValidationError,
        match="multiple_identity_relations_for_source",
    ):
        _compiler().compile(
            proposal=conflicting_proposal,
            observations=[observation],
            existing_entity_links=[],
        )
