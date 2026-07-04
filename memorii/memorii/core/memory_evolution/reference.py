"""Read-only reference knowledge for memory evolution."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class ReferenceEntity(BaseModel):
    reference_id: str
    name: str
    entity_type: str
    aliases: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class ReferenceClaim(BaseModel):
    reference_claim_id: str
    subject_reference_id: str
    predicate_id: str
    object_value: str
    object_reference_id: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class ReferenceKnowledgeProvider(Protocol):
    def entities(self) -> list[ReferenceEntity]: ...

    def claims(self) -> list[ReferenceClaim]: ...

    def find_entity(self, text: str) -> ReferenceEntity | None: ...


class BuiltInReferenceKnowledgeProvider:
    """Tiny built-in reference seed kept separate from user/project memory."""

    def __init__(self) -> None:
        self._entities = [
            ReferenceEntity(reference_id="ref:country:france", name="France", entity_type="country"),
            ReferenceEntity(reference_id="ref:city:paris", name="Paris", entity_type="city"),
            ReferenceEntity(
                reference_id="ref:cloud:azure",
                name="Azure",
                entity_type="service",
                aliases=["Microsoft Azure"],
            ),
            ReferenceEntity(reference_id="ref:language:python", name="Python", entity_type="service"),
            ReferenceEntity(
                reference_id="ref:timezone:utc",
                name="UTC",
                entity_type="unknown",
                aliases=["Coordinated Universal Time"],
            ),
        ]
        self._claims = [
            ReferenceClaim(
                reference_claim_id="ref:claim:paris:type",
                subject_reference_id="ref:city:paris",
                predicate_id="entity_type",
                object_value="city",
            ),
            ReferenceClaim(
                reference_claim_id="ref:claim:france:type",
                subject_reference_id="ref:country:france",
                predicate_id="entity_type",
                object_value="country",
            ),
            ReferenceClaim(
                reference_claim_id="ref:claim:paris:located_in:france",
                subject_reference_id="ref:city:paris",
                predicate_id="located_in",
                object_value="France",
                object_reference_id="ref:country:france",
            ),
            ReferenceClaim(
                reference_claim_id="ref:claim:azure:type",
                subject_reference_id="ref:cloud:azure",
                predicate_id="entity_type",
                object_value="cloud_platform",
            ),
            ReferenceClaim(
                reference_claim_id="ref:claim:python:type",
                subject_reference_id="ref:language:python",
                predicate_id="entity_type",
                object_value="programming_language",
            ),
            ReferenceClaim(
                reference_claim_id="ref:claim:utc:type",
                subject_reference_id="ref:timezone:utc",
                predicate_id="entity_type",
                object_value="timezone_standard",
            ),
        ]

    def entities(self) -> list[ReferenceEntity]:
        return list(self._entities)

    def claims(self) -> list[ReferenceClaim]:
        return list(self._claims)

    def find_entity(self, text: str) -> ReferenceEntity | None:
        normalized = _normalize(text)
        for entity in self._entities:
            if normalized == _normalize(entity.name):
                return entity
            if any(normalized == _normalize(alias) for alias in entity.aliases):
                return entity
        return None


def _normalize(value: str) -> str:
    return " ".join(value.strip().lower().split())
