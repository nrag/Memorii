"""Canonical policy adapters for the shipped default relation inventory."""

from __future__ import annotations

from memorii.core.memory_evolution.semantic_state import PredicateStateRule
from memorii.core.semantic_ingestion.contracts import (
    PredicateTemporalRule,
    PredicateTrustRule,
    contract_digest,
)
from memorii.core.semantic_ingestion.default_catalog_corpus import (
    DefaultCatalogCorpusRow,
    load_default_catalog_acceptance_corpus,
)

_SEED_PREDICATE_IDS = (
    "project_deadline",
    "project_owner",
    "project_status",
)


def _rows() -> tuple[DefaultCatalogCorpusRow, ...]:
    return load_default_catalog_acceptance_corpus().rows


def default_catalog_state_rules() -> dict[str, PredicateStateRule]:
    """Materialize canonical state rules from each M/C/H corpus declaration."""
    rules: dict[str, PredicateStateRule] = {}
    for row in _rows():
        cardinality = "single" if row.lifecycle == "C" else "multi"
        conflict_behavior = (
            "compete_within_slot" if cardinality == "single" else "accumulate_distinct_values"
        )
        body = {
            "predicate_id": row.relation_id,
            "cardinality": cardinality,
            "conflict_behavior": conflict_behavior,
            "qualifier_partition_fields": (),
            "value_identity_policy_id": (
                f"memorii.default-catalog.{row.lifecycle}.{row.read_form}.{row.evidence}.{row.scope}.v1"
            ),
        }
        rules[row.relation_id] = PredicateStateRule(
            **body,
            policy_fingerprint=contract_digest(
                b"memorii.default-catalog.state-rule.v1", body
            ),
        )
    return rules


def default_catalog_trust_rules() -> dict[str, PredicateTrustRule]:
    """Use the local signed-in official authority for all Level-2 rows."""
    return {
        row.relation_id: PredicateTrustRule(
            predicate_id=row.relation_id,
            eligible_authority_classes=frozenset({"official"}),
            authority_rank_by_class={"official": 10},
        )
        for row in _rows()
    }


def default_catalog_temporal_rules() -> dict[str, PredicateTemporalRule]:
    """Ordinary claims have optional, open valid time; event values stay typed."""
    return {
        row.relation_id: PredicateTemporalRule(
            predicate_id=row.relation_id,
            valid_time_requirement="optional",
            allow_open_end=True,
        )
        for row in _rows()
    }


def selected_default_catalog_state_rules() -> dict[str, PredicateStateRule]:
    """Compose the selected default release's retained seed and corpus rules."""
    rules = {
        predicate_id: PredicateStateRule(
            predicate_id=predicate_id,
            cardinality="single",
            conflict_behavior="compete_within_slot",
            qualifier_partition_fields=(),
            value_identity_policy_id="memorii.project-assertions.value.v1",
            policy_fingerprint=contract_digest(
                b"memorii.default-catalog.seed-state-rule.v1",
                {"predicate_id": predicate_id},
            ),
        )
        for predicate_id in _SEED_PREDICATE_IDS
    }
    rules.update(default_catalog_state_rules())
    return rules


def selected_default_catalog_trust_rules() -> dict[str, PredicateTrustRule]:
    """Compose the selected default release's retained seed and corpus rules."""
    rules = {
        predicate_id: PredicateTrustRule(
            predicate_id=predicate_id,
            eligible_authority_classes=frozenset({"official"}),
            authority_rank_by_class={"official": 10},
        )
        for predicate_id in _SEED_PREDICATE_IDS
    }
    rules.update(default_catalog_trust_rules())
    return rules


def selected_default_catalog_temporal_rules() -> dict[str, PredicateTemporalRule]:
    """Compose the selected default release's retained seed and corpus rules."""
    rules = {
        predicate_id: PredicateTemporalRule(
            predicate_id=predicate_id,
            valid_time_requirement="optional",
            allow_open_end=True,
        )
        for predicate_id in _SEED_PREDICATE_IDS
    }
    rules.update(default_catalog_temporal_rules())
    return rules


class DefaultCatalogProtectedReader:
    """Adapter called by the canonical scoped reader for default pins."""

    @staticmethod
    def authorizes_version(*, selected_version_id: str) -> bool:
        return selected_version_id == "default-catalog-v1"


__all__ = [
    "DefaultCatalogProtectedReader",
    "default_catalog_state_rules",
    "default_catalog_temporal_rules",
    "default_catalog_trust_rules",
    "selected_default_catalog_state_rules",
    "selected_default_catalog_temporal_rules",
    "selected_default_catalog_trust_rules",
]
