"""Core-owned validation for model-reported ontology coverage gaps."""

from __future__ import annotations

import re
import unicodedata

from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.semantic_ingestion.catalog_authority import (
    CatalogChildVersionV2,
    CatalogVersion,
)
from memorii.core.semantic_ingestion.coverage_observation import CoverageObservation
from memorii.core.semantic_ingestion.coverage_recurrence import (
    EntityTypeGapSignature,
    RelationGapSignature,
)
from memorii.core.semantic_ingestion.default_catalog_corpus import (
    load_default_catalog_acceptance_corpus,
)

_ALIAS_SEPARATOR = re.compile(r"[^a-z0-9]+")
_SEED_RELATIONS = frozenset({"project_deadline", "project_owner", "project_status"})


def _alias_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(part for part in _ALIAS_SEPARATOR.split(normalized) if part)


class CoreCoverageGapValidator:
    """Validate a gap against the observation's persisted historical catalog."""

    def __init__(self, memory_plane: MemoryPlaneService) -> None:
        self._memory_plane = memory_plane

    def validates(
        self,
        *,
        observation: CoverageObservation,
        signature: RelationGapSignature | EntityTypeGapSignature,
    ) -> bool:
        predicate_ids = self._pinned_predicate_ids(observation)
        if predicate_ids is None:
            return False
        corpus = load_default_catalog_acceptance_corpus()
        known_types = {item.type_id for item in corpus.entity_types}
        if isinstance(signature, EntityTypeGapSignature):
            return (
                _alias_key(signature.normalized_type_meaning)
                not in {_alias_key(type_id) for type_id in known_types}
                and signature.proposed_parent_type_id in known_types
                and signature.scope_class in {"G", "P"}
            )
        if (
            signature.subject_type_id not in known_types
            or signature.object_type_id
            not in known_types | {"LocalDate", "Money", "StatusText", "TimeInterval"}
        ):
            return False
        rows = {row.relation_id: row for row in corpus.rows}
        matches = tuple(
            predicate_id
            for predicate_id in predicate_ids
            if _alias_key(predicate_id) == _alias_key(signature.normalized_relation_meaning)
        )
        if len(matches) != 0:
            # A registered relation or its normalized display alias is coverage,
            # including an endpoint mismatch that requires attribution review.
            return False
        return all(
            predicate_id in _SEED_RELATIONS or predicate_id in rows
            for predicate_id in predicate_ids
        )

    def _pinned_predicate_ids(
        self, observation: CoverageObservation
    ) -> tuple[str, ...] | None:
        candidates: list[CatalogVersion | CatalogChildVersionV2] = []
        for record in self._memory_plane.list_records(
            source_kind="semantic_ingestion_catalog_version"
        ):
            try:
                payload = record.content["catalog_version"]
                version = (
                    CatalogVersion.model_validate(payload)
                    if payload.get("schema_version") == 1
                    else CatalogChildVersionV2.model_validate(payload)
                )
            except (AttributeError, KeyError, TypeError, ValueError):
                return None
            if (
                version.catalog_scope == observation.catalog_scope
                and version.version_digest == observation.catalog_digest
            ):
                candidates.append(version)
        if len(candidates) != 1:
            return None
        return candidates[0].predicate_ids


__all__ = ["CoreCoverageGapValidator"]
