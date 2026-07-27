from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from memorii.core.memory_evolution.extraction import models_from_llm_output
from memorii.core.memory_evolution.models import (
    EntityIdentityRelationType,
    EntityType,
    ExtractionFailureCode,
    ExtractionRunStatus,
    SourceObservation,
)
from memorii.domain.enums import SourceType

_UTC = ZoneInfo("UTC")


def _observation(source_id: str, text: str, *, language: str = "en"):
    return SourceObservation.model_validate(
        {
            "source_id": source_id,
            "text": text,
            "source_type": SourceType.USER,
            "timestamp": datetime(2026, 1, 1, tzinfo=_UTC),
            "language": language,
        }
    )


def _entity(
    *,
    entity_ref: str,
    mention_text: str,
    entity_type: str,
    source_id: str,
) -> dict[str, object]:
    return {
        "entity_ref": entity_ref,
        "mention_text": mention_text,
        "entity_type": entity_type,
        "source_id": source_id,
        "quote": mention_text,
        "confidence": 0.9,
    }


def _claim(
    *,
    subject_ref: str,
    predicate: str,
    object_value: str,
    object_ref: str | None,
    source_id: str,
    quote: str,
) -> dict[str, object]:
    return {
        "subject_entity_ref": subject_ref,
        "predicate_id": predicate,
        "object_value": object_value,
        "object_entity_ref": object_ref,
        "source_id": source_id,
        "quote": quote,
        "confidence": 0.9,
    }


def _compile(
    *,
    source_id: str,
    text: str,
    entities: list[dict[str, object]],
    claims: list[dict[str, object]],
    language: str = "en",
):
    return models_from_llm_output(
        run_id=f"run:{source_id}",
        provider="test",
        model="test-model",
        prompt_hash="test-prompt",
        observations=[_observation(source_id, text, language=language)],
        output={"entities": entities, "claims": claims, "actions": []},
    )


def test_entity_type_source_local_grounding_requires_direct_semantic_binding() -> None:
    source_id = "tx:attributed-type"
    quote = "Alice said Atlas is a project"
    proposal = _compile(
        source_id=source_id,
        text=f"{quote}.",
        entities=[
            _entity(
                entity_ref="alice",
                mention_text="Alice",
                entity_type="unknown",
                source_id=source_id,
            ),
            _entity(
                entity_ref="atlas",
                mention_text="Atlas",
                entity_type="unknown",
                source_id=source_id,
            ),
        ],
        claims=[
            _claim(
                subject_ref="atlas",
                predicate="entity_type",
                object_value="project",
                object_ref=None,
                source_id=source_id,
                quote=quote,
            )
        ],
    )
    run = proposal.run
    entities = proposal.entities
    claims = proposal.claims

    assert run.status == ExtractionRunStatus.SUCCEEDED
    assert run.failure_code is None
    accepted = [
        (entity.mention_text, entity.entity_type) for entity in entities if entity.entity_type != EntityType.UNKNOWN
    ]
    assert accepted == [("Atlas", EntityType.PROJECT)]
    assert [(claim.claim_key.predicate_id, claim.object_value) for claim in claims] == [("entity_type", "project")]


def test_entity_type_rejects_attribution_distractor_with_same_type_term() -> None:
    source_id = "tx:attributed-type-distractor"
    quote = "Alice said Atlas is a project"
    proposal = _compile(
        source_id=source_id,
        text=f"{quote}.",
        entities=[
            _entity(entity_ref="alice", mention_text="Alice", entity_type="person", source_id=source_id),
            _entity(entity_ref="atlas", mention_text="Atlas", entity_type="project", source_id=source_id),
        ],
        claims=[
            _claim(
                subject_ref="alice",
                predicate="entity_type",
                object_value="project",
                object_ref=None,
                source_id=source_id,
                quote=quote,
            )
        ],
    )

    assert proposal.run.status == ExtractionRunStatus.PARTIAL
    assert proposal.claims == []
    assert any("entity_type declaration is not semantically grounded" in error for error in proposal.run.errors)


def test_entity_type_source_local_grounding_rejects_missing_type_term() -> None:
    source_id = "tx:missing-type-term"
    quote = "Alice discussed Atlas"
    proposal = _compile(
        source_id=source_id,
        text=f"{quote}.",
        entities=[
            _entity(
                entity_ref="alice",
                mention_text="Alice",
                entity_type="unknown",
                source_id=source_id,
            ),
            _entity(
                entity_ref="atlas",
                mention_text="Atlas",
                entity_type="unknown",
                source_id=source_id,
            ),
        ],
        claims=[
            _claim(
                subject_ref="atlas",
                predicate="entity_type",
                object_value="project",
                object_ref=None,
                source_id=source_id,
                quote=quote,
            )
        ],
    )
    run = proposal.run
    entities = proposal.entities
    claims = proposal.claims

    assert run.status == ExtractionRunStatus.PARTIAL
    assert run.failure_code == ExtractionFailureCode.OUTPUT_VALIDATION
    assert run.validation_summary["claim_binding_errors"] == 1
    assert [(entity.mention_text, entity.entity_type) for entity in entities] == [
        ("Alice", EntityType.UNKNOWN),
        ("Atlas", EntityType.UNKNOWN),
    ]
    assert claims == []


def test_relation_source_local_grounding_accepts_only_the_bound_semantic_pair() -> None:
    source_id = "tx:owner-distractor"
    quote = "Alice owns Atlas, not Beacon"
    entity_types = {
        "alice": "person",
        "atlas": "project",
        "beacon": "project",
    }
    names = {
        "alice": "Alice",
        "atlas": "Atlas",
        "beacon": "Beacon",
    }
    proposal = _compile(
        source_id=source_id,
        text=f"{quote}.",
        entities=[
            _entity(
                entity_ref=entity_ref,
                mention_text=names[entity_ref],
                entity_type=entity_types[entity_ref],
                source_id=source_id,
            )
            for entity_ref in ("alice", "atlas", "beacon")
        ],
        claims=[
            _claim(
                subject_ref="atlas",
                predicate="owner",
                object_value=names["alice"],
                object_ref="alice",
                source_id=source_id,
                quote=quote,
            )
        ],
    )
    run = proposal.run
    entities = proposal.entities
    claims = proposal.claims

    entities_by_id = {entity.entity_id: entity for entity in entities}
    assert run.status == ExtractionRunStatus.SUCCEEDED
    assert len(claims) == 1
    assert entities_by_id[claims[0].claim_key.subject_entity_id].mention_text == "Atlas"
    assert claims[0].object_entity_id is not None
    assert entities_by_id[claims[0].object_entity_id].mention_text == "Alice"


@pytest.mark.parametrize(("subject_ref", "object_ref"), [("beacon", "alice"), ("alice", "beacon")])
def test_relation_source_local_grounding_rejects_co_mentioned_false_edges(
    subject_ref: str,
    object_ref: str,
) -> None:
    source_id = "tx:owner-distractor-rejected"
    quote = "Alice owns Atlas, not Beacon"
    names = {"alice": "Alice", "atlas": "Atlas", "beacon": "Beacon"}
    proposal = _compile(
        source_id=source_id,
        text=f"{quote}.",
        entities=[
            _entity(
                entity_ref=entity_ref,
                mention_text=name,
                entity_type=("person" if entity_ref == "alice" else "project"),
                source_id=source_id,
            )
            for entity_ref, name in names.items()
        ],
        claims=[
            _claim(
                subject_ref=subject_ref,
                predicate="owner",
                object_value=names[object_ref],
                object_ref=object_ref,
                source_id=source_id,
                quote=quote,
            )
        ],
    )

    assert proposal.run.status == ExtractionRunStatus.PARTIAL
    assert proposal.claims == []
    assert any("relation semantics are not grounded" in error for error in proposal.run.errors)


def test_relation_source_local_grounding_rejects_anaphoric_missing_endpoint() -> None:
    source_id = "tx:anaphoric-owner"
    text = "Alice joined the project. She owns Atlas."
    proposal = _compile(
        source_id=source_id,
        text=text,
        entities=[
            _entity(
                entity_ref="alice",
                mention_text="Alice",
                entity_type="person",
                source_id=source_id,
            ),
            _entity(
                entity_ref="atlas",
                mention_text="Atlas",
                entity_type="project",
                source_id=source_id,
            ),
        ],
        claims=[
            _claim(
                subject_ref="atlas",
                predicate="owner",
                object_value="Alice",
                object_ref="alice",
                source_id=source_id,
                quote="She owns Atlas",
            )
        ],
    )

    assert proposal.run.status == ExtractionRunStatus.PARTIAL
    assert proposal.claims == []
    assert proposal.run.validation_summary["claim_binding_errors"] == 1
    assert "relation semantics are not grounded" in proposal.run.errors[0]


def test_owner_keyword_without_a_supported_frame_does_not_ground_a_relation() -> None:
    source_id = "tx:owner-keyword-distractor"
    quote = "Alice criticized Atlas owner"
    proposal = _compile(
        source_id=source_id,
        text=f"{quote}.",
        entities=[
            _entity(entity_ref="alice", mention_text="Alice", entity_type="person", source_id=source_id),
            _entity(entity_ref="atlas", mention_text="Atlas", entity_type="project", source_id=source_id),
        ],
        claims=[
            _claim(
                subject_ref="atlas",
                predicate="owner",
                object_value="Alice",
                object_ref="alice",
                source_id=source_id,
                quote=quote,
            )
        ],
    )

    assert proposal.run.status == ExtractionRunStatus.PARTIAL
    assert proposal.claims == []
    assert any("relation semantics are not grounded" in error for error in proposal.run.errors)


def test_owner_role_suffix_requires_and_accepts_language_owned_bridge_tokens() -> None:
    source_id = "tx:owner-role-suffix"
    quote = "Alice is the temporary Atlas owner"
    proposal = _compile(
        source_id=source_id,
        text=f"{quote}.",
        entities=[
            _entity(entity_ref="alice", mention_text="Alice", entity_type="unknown", source_id=source_id),
            _entity(entity_ref="atlas", mention_text="Atlas", entity_type="project", source_id=source_id),
        ],
        claims=[
            _claim(
                subject_ref="atlas",
                predicate="owner",
                object_value="Alice",
                object_ref="alice",
                source_id=source_id,
                quote=quote,
            )
        ],
    )

    assert proposal.run.status == ExtractionRunStatus.SUCCEEDED
    assert len(proposal.claims) == 1
    alice = next(entity for entity in proposal.entities if entity.mention_text == "Alice")
    assert alice.entity_type == EntityType.PERSON


@pytest.mark.parametrize(
    ("quote", "person_name", "subject_ref", "object_ref"),
    [
        ("Alice owns Atlas", "Alice", "alice", "atlas"),
        ("Atlas is owned by Alice", "Alice", "atlas", "alice"),
        ("Atlas owner is Alice", "Alice", "atlas", "alice"),
        ("La propietaria de Atlas es Alicia", "Alicia", "atlas", "alice"),
    ],
)
def test_owner_surface_forms_compile_to_the_same_semantic_pair(
    quote: str,
    person_name: str,
    subject_ref: str,
    object_ref: str,
) -> None:
    source_id = "tx:owner-surface"
    proposal = _compile(
        source_id=source_id,
        text=f"{quote}.",
        entities=[
            _entity(
                entity_ref="alice",
                mention_text=person_name,
                entity_type="person",
                source_id=source_id,
            ),
            _entity(
                entity_ref="atlas",
                mention_text="Atlas",
                entity_type="project",
                source_id=source_id,
            ),
        ],
        claims=[
            _claim(
                subject_ref=subject_ref,
                predicate="owner",
                object_value=("Atlas" if object_ref == "atlas" else person_name),
                object_ref=object_ref,
                source_id=source_id,
                quote=quote,
            )
        ],
        language=("es-MX" if quote.startswith("La propietaria") else "en-US"),
    )
    run = proposal.run
    entities = proposal.entities
    claims = proposal.claims

    entities_by_id = {entity.entity_id: entity for entity in entities}
    assert run.status == ExtractionRunStatus.SUCCEEDED
    assert len(claims) == 1
    assert claims[0].object_entity_id is not None
    assert entities_by_id[claims[0].claim_key.subject_entity_id].mention_text == "Atlas"
    assert entities_by_id[claims[0].object_entity_id].mention_text == person_name


def test_explicit_split_relation_compiles_as_typed_identity_data() -> None:
    source_id = "tx:split"
    text = "Atlas Service split from Atlas."

    proposal = models_from_llm_output(
        run_id="run:split",
        provider="test",
        model="test-model",
        prompt_hash="test-prompt",
        observations=[_observation(source_id, text)],
        output={
            "entities": [
                _entity(
                    entity_ref="child",
                    mention_text="Atlas Service",
                    entity_type="service",
                    source_id=source_id,
                ),
                _entity(
                    entity_ref="parent",
                    mention_text="Atlas",
                    entity_type="project",
                    source_id=source_id,
                ),
            ],
            "claims": [],
            "actions": [],
            "identity_relations": [
                {
                    "relation_ref": "split",
                    "relation_type": "split_from",
                    "source_entity_ref": "child",
                    "target_entity_ref": "parent",
                    "source_id": source_id,
                    "quote": text,
                    "confidence": 0.95,
                }
            ],
        },
    )

    assert proposal.run.status == ExtractionRunStatus.SUCCEEDED
    assert len(proposal.identity_relations) == 1
    relation = proposal.identity_relations[0]
    assert relation.relation_type == EntityIdentityRelationType.SPLIT_FROM
    assert relation.source_entity_id != relation.target_entity_id
    assert proposal.run.identity_relation_ids == [relation.relation_id]


def test_identity_relation_with_same_endpoint_fails_source_local_validation() -> None:
    source_id = "tx:self-alias"

    proposal = models_from_llm_output(
        run_id="run:self-alias",
        provider="test",
        model="test-model",
        prompt_hash="test-prompt",
        observations=[_observation(source_id, "Atlas is also called Atlas.")],
        output={
            "entities": [
                _entity(
                    entity_ref="atlas",
                    mention_text="Atlas",
                    entity_type="project",
                    source_id=source_id,
                )
            ],
            "claims": [],
            "actions": [],
            "identity_relations": [
                {
                    "relation_ref": "self",
                    "relation_type": "alias_of",
                    "source_entity_ref": "atlas",
                    "target_entity_ref": "atlas",
                    "source_id": source_id,
                    "quote": "Atlas is also called Atlas",
                    "confidence": 0.9,
                }
            ],
        },
    )

    assert proposal.run.status == ExtractionRunStatus.PARTIAL
    assert proposal.identity_relations == []
    assert proposal.run.validation_summary["identity_relation_binding_errors"] == 1


def test_identity_relation_requires_both_endpoints_in_its_evidence_quote() -> None:
    source_id = "tx:ungrounded-split"
    relation_quote = "Atlas Service was split yesterday"
    text = f"Atlas Billing Migration exists. {relation_quote}."

    proposal = models_from_llm_output(
        run_id="run:ungrounded-split",
        provider="test",
        model="test-model",
        prompt_hash="test-prompt",
        observations=[_observation(source_id, text)],
        output={
            "entities": [
                _entity(
                    entity_ref="child",
                    mention_text="Atlas Service",
                    entity_type="service",
                    source_id=source_id,
                ),
                _entity(
                    entity_ref="parent",
                    mention_text="Atlas Billing Migration",
                    entity_type="project",
                    source_id=source_id,
                ),
            ],
            "claims": [],
            "actions": [],
            "identity_relations": [
                {
                    "relation_ref": "split",
                    "relation_type": "split_from",
                    "source_entity_ref": "child",
                    "target_entity_ref": "parent",
                    "source_id": source_id,
                    "quote": relation_quote,
                    "confidence": 0.9,
                }
            ],
        },
    )

    assert proposal.run.status == ExtractionRunStatus.PARTIAL
    assert proposal.identity_relations == []
    assert any("identity relation is not semantically grounded" in error for error in proposal.run.errors)


def test_explicit_alias_relation_is_directional_and_source_grounded() -> None:
    source_id = "tx:explicit-alias"
    quote = "Atlas is an alias for Atlas Billing Migration"
    proposal = models_from_llm_output(
        run_id="run:explicit-alias",
        provider="test",
        model="test-model",
        prompt_hash="test-prompt",
        observations=[_observation(source_id, f"{quote}.")],
        output={
            "entities": [
                _entity(entity_ref="alias", mention_text="Atlas", entity_type="unknown", source_id=source_id),
                _entity(
                    entity_ref="canonical",
                    mention_text="Atlas Billing Migration",
                    entity_type="project",
                    source_id=source_id,
                ),
            ],
            "claims": [],
            "actions": [],
            "identity_relations": [
                {
                    "relation_ref": "alias-link",
                    "relation_type": "alias_of",
                    "source_entity_ref": "alias",
                    "target_entity_ref": "canonical",
                    "source_id": source_id,
                    "quote": quote,
                    "confidence": 0.95,
                }
            ],
        },
    )

    assert proposal.run.status == ExtractionRunStatus.SUCCEEDED
    assert len(proposal.identity_relations) == 1


def test_negated_alias_relation_is_not_created_from_co_mention() -> None:
    source_id = "tx:negated-alias"
    quote = "Atlas is not an alias for Beacon"
    proposal = models_from_llm_output(
        run_id="run:negated-alias",
        provider="test",
        model="test-model",
        prompt_hash="test-prompt",
        observations=[_observation(source_id, f"{quote}.")],
        output={
            "entities": [
                _entity(entity_ref="atlas", mention_text="Atlas", entity_type="project", source_id=source_id),
                _entity(entity_ref="beacon", mention_text="Beacon", entity_type="project", source_id=source_id),
            ],
            "claims": [],
            "actions": [],
            "identity_relations": [
                {
                    "relation_ref": "false-alias",
                    "relation_type": "alias_of",
                    "source_entity_ref": "atlas",
                    "target_entity_ref": "beacon",
                    "source_id": source_id,
                    "quote": quote,
                    "confidence": 0.9,
                }
            ],
        },
    )

    assert proposal.run.status == ExtractionRunStatus.PARTIAL
    assert proposal.identity_relations == []
    assert any("identity relation is not semantically grounded" in error for error in proposal.run.errors)


def test_denial_wrapper_outside_provider_quote_cannot_create_owner_claim() -> None:
    source_id = "tx:false-owner"
    proposal = _compile(
        source_id=source_id,
        text="It is false that Alice owns Atlas.",
        entities=[
            _entity(entity_ref="alice", mention_text="Alice", entity_type="person", source_id=source_id),
            _entity(entity_ref="atlas", mention_text="Atlas", entity_type="project", source_id=source_id),
        ],
        claims=[
            _claim(
                subject_ref="atlas",
                predicate="owner",
                object_value="Alice",
                object_ref="alice",
                source_id=source_id,
                quote="Alice owns Atlas",
            )
        ],
    )

    assert proposal.run.status == ExtractionRunStatus.PARTIAL
    assert proposal.claims == []
    assert any(":contradicted:" in error for error in proposal.run.errors)


def test_negated_literal_state_cannot_create_active_status_candidate() -> None:
    source_id = "tx:not-blocked"
    proposal = _compile(
        source_id=source_id,
        text="Atlas is not blocked.",
        entities=[
            _entity(entity_ref="atlas", mention_text="Atlas", entity_type="project", source_id=source_id),
        ],
        claims=[
            _claim(
                subject_ref="atlas",
                predicate="status",
                object_value="blocked",
                object_ref=None,
                source_id=source_id,
                quote="Atlas is not blocked",
            )
        ],
    )

    assert proposal.run.status == ExtractionRunStatus.PARTIAL
    assert proposal.claims == []
    assert any("literal claim semantics are not source-grounded:contradicted" in error for error in proposal.run.errors)


def test_entity_name_must_occur_in_its_own_verbatim_evidence() -> None:
    source_id = "tx:hallucinated-entity"
    proposal = models_from_llm_output(
        run_id="run:hallucinated-entity",
        provider="test",
        model="test-model",
        prompt_hash="test-prompt",
        observations=[_observation(source_id, "Atlas is a project.")],
        output={
            "entities": [
                {
                    "entity_ref": "zeus",
                    "mention_text": "Zeus",
                    "entity_type": "project",
                    "source_id": source_id,
                    "quote": "Atlas",
                    "confidence": 0.9,
                }
            ],
            "claims": [],
            "actions": [],
            "identity_relations": [],
        },
    )

    assert proposal.run.status == ExtractionRunStatus.FAILED
    assert proposal.entities == []
    assert any("entity name is absent" in error for error in proposal.run.errors)


def test_repeated_quote_cannot_be_bound_to_an_arbitrary_assertion() -> None:
    source_id = "tx:ambiguous-assertion"
    proposal = _compile(
        source_id=source_id,
        text="Alice owns Atlas. It is false that Alice owns Atlas.",
        entities=[
            _entity(
                entity_ref="alice",
                mention_text="Alice",
                entity_type="person",
                source_id=source_id,
            ),
            _entity(
                entity_ref="atlas",
                mention_text="Atlas",
                entity_type="project",
                source_id=source_id,
            ),
        ],
        claims=[
            _claim(
                subject_ref="atlas",
                predicate="owner",
                object_value="Alice",
                object_ref="alice",
                source_id=source_id,
                quote="Alice owns Atlas",
            )
        ],
    )

    assert proposal.run.status == ExtractionRunStatus.PARTIAL
    assert proposal.claims == []
    assert any("evidence quote is ambiguous" in error for error in proposal.run.errors)
