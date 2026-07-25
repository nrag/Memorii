from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from memorii.core.memory_evolution.extraction import models_from_llm_output
from memorii.core.memory_evolution.models import (
    EntityType,
    ExtractionFailureCode,
    ExtractionRunStatus,
    SourceObservation,
)
from memorii.domain.enums import SourceType

_UTC = ZoneInfo("UTC")


def _observation(source_id: str, text: str):
    return SourceObservation.model_validate(
        {
            "source_id": source_id,
            "text": text,
            "source_type": SourceType.USER,
            "timestamp": datetime(2026, 1, 1, tzinfo=_UTC),
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
        "aliases": [],
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
):
    return models_from_llm_output(
        run_id=f"run:{source_id}",
        provider="test",
        model="test-model",
        prompt_hash="test-prompt",
        observations=[_observation(source_id, text)],
        output={"entities": entities, "claims": claims, "actions": []},
    )


@pytest.mark.parametrize(
    ("subject_ref", "expected_status", "expected_subject", "expected_type"),
    [
        ("atlas", ExtractionRunStatus.SUCCEEDED, "Atlas", EntityType.PROJECT),
        ("alice", ExtractionRunStatus.PARTIAL, None, None),
    ],
)
def test_entity_type_evidence_binds_the_declared_subject(
    subject_ref: str,
    expected_status: ExtractionRunStatus,
    expected_subject: str | None,
    expected_type: EntityType | None,
) -> None:
    source_id = "tx:attributed-type"
    quote = "Alice said Atlas is a project"
    run, entities, claims, _ = _compile(
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
                subject_ref=subject_ref,
                predicate="entity_type",
                object_value="project",
                object_ref=None,
                source_id=source_id,
                quote=quote,
            )
        ],
    )

    assert run.status == expected_status
    assert run.failure_code == (
        None
        if expected_status == ExtractionRunStatus.SUCCEEDED
        else ExtractionFailureCode.OUTPUT_VALIDATION
    )
    accepted = [
        (entity.mention_text, entity.entity_type)
        for entity in entities
        if entity.entity_type != EntityType.UNKNOWN
    ]
    assert accepted == (
        [] if expected_subject is None else [(expected_subject, expected_type)]
    )
    assert [
        (claim.claim_key.predicate_id, claim.object_value)
        for claim in claims
    ] == (
        [] if expected_subject is None else [("entity_type", "project")]
    )
    if expected_status == ExtractionRunStatus.PARTIAL:
        assert run.validation_summary["claim_binding_errors"] == 1
        assert "not grounded in its evidence quote" in run.errors[0]


def test_entity_type_proposal_rejects_misbinding_without_dropping_supported_claim() -> None:
    source_id = "tx:mixed-attributed-type"
    quote = "Alice said Atlas is a project"
    run, entities, claims, _ = _compile(
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
                subject_ref=subject_ref,
                predicate="entity_type",
                object_value="project",
                object_ref=None,
                source_id=source_id,
                quote=quote,
            )
            for subject_ref in ("atlas", "alice")
        ],
    )

    assert run.status == ExtractionRunStatus.PARTIAL
    assert run.failure_code == ExtractionFailureCode.OUTPUT_VALIDATION
    assert run.validation_summary["claim_binding_errors"] == 1
    assert [
        (entity.mention_text, entity.entity_type)
        for entity in entities
    ] == [
        ("Alice", EntityType.UNKNOWN),
        ("Atlas", EntityType.PROJECT),
    ]
    assert len(claims) == 1
    assert claims[0].object_value == "project"


@pytest.mark.parametrize(
    ("subject_ref", "object_ref", "expected_status"),
    [
        ("atlas", "alice", ExtractionRunStatus.SUCCEEDED),
        ("beacon", "alice", ExtractionRunStatus.PARTIAL),
        ("alice", "beacon", ExtractionRunStatus.PARTIAL),
    ],
)
def test_relation_evidence_binds_exact_subject_object_pair(
    subject_ref: str,
    object_ref: str,
    expected_status: ExtractionRunStatus,
) -> None:
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
    run, _, claims, _ = _compile(
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
                subject_ref=subject_ref,
                predicate="owner",
                object_value=names[object_ref],
                object_ref=object_ref,
                source_id=source_id,
                quote=quote,
            )
        ],
    )

    assert run.status == expected_status
    if expected_status == ExtractionRunStatus.SUCCEEDED:
        assert len(claims) == 1
        assert claims[0].object_value == "Alice"
    else:
        assert run.failure_code == ExtractionFailureCode.OUTPUT_VALIDATION
        assert run.validation_summary["claim_binding_errors"] == 1
        assert claims == []
        assert "relation arguments are not grounded" in run.errors[0]


@pytest.mark.parametrize(
    ("quote", "subject_ref", "object_ref"),
    [
        ("Alice owns Atlas", "alice", "atlas"),
        ("Atlas is owned by Alice", "atlas", "alice"),
        ("Atlas owner is Alice", "atlas", "alice"),
    ],
)
def test_owner_surface_forms_compile_to_the_same_semantic_pair(
    quote: str,
    subject_ref: str,
    object_ref: str,
) -> None:
    source_id = "tx:owner-surface"
    run, entities, claims, _ = _compile(
        source_id=source_id,
        text=f"{quote}.",
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
                subject_ref=subject_ref,
                predicate="owner",
                object_value=(
                    "Atlas" if object_ref == "atlas" else "Alice"
                ),
                object_ref=object_ref,
                source_id=source_id,
                quote=quote,
            )
        ],
    )

    entities_by_id = {entity.entity_id: entity for entity in entities}
    assert run.status == ExtractionRunStatus.SUCCEEDED
    assert len(claims) == 1
    assert claims[0].object_entity_id is not None
    assert entities_by_id[claims[0].claim_key.subject_entity_id].mention_text == "Atlas"
    assert entities_by_id[claims[0].object_entity_id].mention_text == "Alice"
