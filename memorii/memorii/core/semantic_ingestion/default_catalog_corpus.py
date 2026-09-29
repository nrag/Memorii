"""Typed authority for the frozen Level-2 default-catalog acceptance corpus."""

from __future__ import annotations

import hashlib
import importlib.resources
import json
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.semantic_ingestion.catalog_authority import contract_digest
from memorii.core.semantic_ingestion.default_catalog_values import (
    DEFAULT_CATALOG_VALUE_POLICIES,
)

EXPECTED_DEFAULT_RELATION_IDS = frozenset({
    "account_held_by", "account_with", "agreement_governs", "agreement_party",
    "animal_care_task", "animal_cared_for_by", "asset_located_at", "asset_maintained_by",
    "asset_owned_by", "caregiver_for", "decision_concerns", "decision_made_by",
    "decision_supersedes", "document_about", "document_approved_by", "document_authored_by",
    "document_version_of", "event_concerns", "event_participant", "event_place", "event_time",
    "goal_owned_by", "group_part_of", "group_resides_at", "has_role", "issue_affects",
    "issue_reported_by", "issue_resolved_by", "member_of", "message_about", "message_sent_by",
    "message_sent_to", "obligation_amount", "obligation_due_on", "obligation_owed_by",
    "obligation_owed_to", "obligation_payment_evidence", "opportunity_owned_by",
    "opportunity_stage", "opportunity_with", "parent_of", "partner_of", "product_provided_by",
    "project_advances_goal", "project_has_work_item", "project_owned_by", "reports_to",
    "role_scoped_to", "sibling_of", "work_item_assigned_to", "work_item_depends_on",
    "work_item_due_on", "work_item_status",
})

EXPECTED_SEMANTIC_COVERAGE_CODES = frozenset({
    "CONTENT", "CS", "DATA", "DESIGN", "EM", "EXEC", "FIN", "H1", "H10", "H2",
    "H3", "H4", "H5", "H6", "H7", "H9", "HR", "IT", "LEGAL", "MKT", "OPS",
    "PM", "QA", "SALES", "SALESOPS", "SE", "SRE", "SUP", "UX",
})

EXPECTED_DEFAULT_CATALOG_CONTRACT_SHA256 = (
    "adfa931e754c79475dee90c4a06b150ad001556d9065e0e5072d00a30fd529d0"
)

EXPECTED_DEFAULT_ENTITY_TYPES = {
    "Account": (None, "account", "P"),
    "Agreement": (None, "introduced", "P"),
    "Animal": (None, "animal", "P"),
    "Appointment": ("Event", "event", "P"),
    "Asset": (None, "introduced", "P"),
    "Bill": ("Obligation", "introduced", "P"),
    "Chore": ("WorkItem", "introduced", "P"),
    "Decision": (None, "introduced", "G"),
    "Document": (None, "artifact", "G"),
    "Event": (None, "event", "G"),
    "Goal": (None, "introduced", "G"),
    "Group": (None, "introduced", "G"),
    "Household": ("Group", "introduced", "P"),
    "Issue": (None, "introduced", "G"),
    "Message": (None, "artifact", "P"),
    "Obligation": (None, "introduced", "P"),
    "Opportunity": (None, "introduced", "G"),
    "Organization": (None, "introduced", "G"),
    "Person": (None, "introduced", "P"),
    "Place": (None, "introduced", "G"),
    "ProductService": (None, "introduced", "G"),
    "Project": (None, "introduced", "G"),
    "Recipe": ("Document", "artifact", "P"),
    "Role": (None, "role_assignment", "G"),
    "Subscription": ("Agreement", "introduced", "P"),
    "Vehicle": ("Asset", "introduced", "P"),
    "WorkItem": (None, "introduced", "G"),
}


class DefaultCatalogEntityTypeDeclaration(BaseModel):
    type_id: str = Field(min_length=1)
    parent_type_id: str | None = None
    identity_policy_id: Literal["introduced", "event", "artifact", "role_assignment", "account", "animal"]
    scope: Literal["G", "P"]

    model_config = ConfigDict(extra="forbid", frozen=True)


class DefaultCatalogBehaviorCase(BaseModel):
    kind: Literal["assertion", "abstention", "revision", "current_read", "historical_read"]
    source_text: str = Field(min_length=1)
    expected_predicate_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    expected_effect: Literal["commit", "zero_effect", "revise", "read_current", "read_history"]

    model_config = ConfigDict(extra="forbid", frozen=True)


class DefaultCatalogCorpusRow(BaseModel):
    relation_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    endpoint_contract: str = Field(min_length=1)
    subject_type_ids: tuple[str, ...]
    object_entity_type_ids: tuple[str, ...] = ()
    object_value_type: Literal["LocalDate", "StatusText", "TimeInterval", "Money"] | None = None
    value_policy_id: Literal[
        "local_date", "work_item_status", "time_interval", "money_iso4217",
        "opportunity_stage",
    ] | None = None
    value_policy_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    scope: Literal["G", "P"]
    evidence: Literal["D", "A", "E"]
    lifecycle: Literal["M", "C", "H"]
    read_form: Literal["set", "current", "history"]
    read_derivation_policy: Literal["none", "symmetric_view"]
    meaning: str = Field(min_length=1)
    coverage: tuple[str, ...]
    requires_private_denial: bool
    cases: tuple[DefaultCatalogBehaviorCase, ...]

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_row(self) -> DefaultCatalogCorpusRow:
        if self.read_derivation_policy != (
            "symmetric_view" if self.relation_id in {"partner_of", "sibling_of"} else "none"
        ):
            raise ValueError("default catalog read derivation policy is invalid")
        if self.coverage != tuple(sorted(set(self.coverage))):
            raise ValueError("default catalog coverage codes are not canonical")
        if not self.coverage:
            raise ValueError("default catalog row has no primary coverage journey")
        if self.requires_private_denial != (self.scope == "P"):
            raise ValueError("default catalog private-denial flag is inconsistent")
        if (
            not self.subject_type_ids
            or self.subject_type_ids != tuple(sorted(set(self.subject_type_ids)))
            or self.object_entity_type_ids != tuple(sorted(set(self.object_entity_type_ids)))
            or (bool(self.object_entity_type_ids) == (self.object_value_type is not None))
        ):
            raise ValueError("default catalog endpoint declaration is invalid")
        if (
            (self.object_value_type is None) != (self.value_policy_id is None)
            or (self.value_policy_id is None) != (self.value_policy_digest is None)
        ):
            raise ValueError("default catalog literal value policy is invalid")
        if (
            self.value_policy_id is not None
            and self.value_policy_digest
            != DEFAULT_CATALOG_VALUE_POLICIES[self.value_policy_id].policy_digest
        ):
            raise ValueError("default catalog literal value policy is substituted")
        expected_cases = (
            ("assertion", "commit"), ("abstention", "zero_effect"),
            ("revision", "revise"), ("current_read", "read_current"),
            ("historical_read", "read_history"),
        )
        if tuple((case.kind, case.expected_effect) for case in self.cases) != expected_cases:
            raise ValueError("default catalog behavior case roles are incomplete")
        if any(case.expected_predicate_id != self.relation_id for case in self.cases):
            raise ValueError("default catalog behavior case is bound to another relation")
        if len({case.source_text for case in self.cases}) != len(self.cases):
            raise ValueError("default catalog behavior cases are not distinct")
        return self


class DefaultCatalogAcceptanceCorpus(BaseModel):
    schema_version: Literal[1]
    source_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    entity_types: tuple[DefaultCatalogEntityTypeDeclaration, ...]
    rows: tuple[DefaultCatalogCorpusRow, ...]
    user_context_coverage: tuple[Literal["H8"], ...]
    corpus_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_corpus(self) -> DefaultCatalogAcceptanceCorpus:
        if self.source_contract_sha256 != EXPECTED_DEFAULT_CATALOG_CONTRACT_SHA256:
            raise ValueError("default catalog source contract is substituted")
        entity_types = {
            item.type_id: (item.parent_type_id, item.identity_policy_id, item.scope)
            for item in self.entity_types
        }
        if (
            tuple(item.type_id for item in self.entity_types)
            != tuple(sorted(entity_types))
            or entity_types != EXPECTED_DEFAULT_ENTITY_TYPES
        ):
            raise ValueError("default catalog entity type inventory is incomplete")
        relation_ids = tuple(row.relation_id for row in self.rows)
        if relation_ids != tuple(sorted(relation_ids)) or len(relation_ids) != len(set(relation_ids)):
            raise ValueError("default catalog rows are not canonical")
        if frozenset(relation_ids) != EXPECTED_DEFAULT_RELATION_IDS:
            raise ValueError("default catalog relation inventory is incomplete")
        coverage = frozenset(code for row in self.rows for code in row.coverage)
        if coverage != EXPECTED_SEMANTIC_COVERAGE_CODES or self.user_context_coverage != ("H8",):
            raise ValueError("default catalog coverage inventory is incomplete")
        known_types = frozenset(entity_types)
        if any(
            not set((*row.subject_type_ids, *row.object_entity_type_ids)).issubset(known_types)
            for row in self.rows
        ):
            raise ValueError("default catalog relation uses an unknown entity type")
        body = self.model_dump(mode="python", exclude={"corpus_digest"})
        if self.corpus_digest != contract_digest(
            b"memorii.learned-ontology.default-acceptance-corpus.v1", body
        ):
            raise ValueError("default catalog corpus digest is invalid")
        return self


@lru_cache(maxsize=1)
def load_default_catalog_acceptance_corpus() -> DefaultCatalogAcceptanceCorpus:
    """Load canonical packaged corpus bytes and verify the compiled inventory."""
    payload = importlib.resources.files(
        "memorii.core.semantic_ingestion.resources"
    ).joinpath("default_catalog_acceptance_corpus.v1.json").read_bytes()
    try:
        decoded = json.loads(payload)
        corpus = DefaultCatalogAcceptanceCorpus.model_validate(decoded)
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError("default catalog acceptance corpus is unavailable") from exc
    canonical = json.dumps(
        corpus.model_dump(mode="json"), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8") + b"\n"
    if payload != canonical:
        raise ValueError("default catalog acceptance corpus bytes are not canonical")
    return corpus


def corpus_resource_sha256() -> str:
    payload = importlib.resources.files(
        "memorii.core.semantic_ingestion.resources"
    ).joinpath("default_catalog_acceptance_corpus.v1.json").read_bytes()
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "DefaultCatalogAcceptanceCorpus", "DefaultCatalogBehaviorCase",
    "DefaultCatalogCorpusRow", "DefaultCatalogEntityTypeDeclaration",
    "EXPECTED_DEFAULT_ENTITY_TYPES", "EXPECTED_DEFAULT_RELATION_IDS",
    "EXPECTED_DEFAULT_CATALOG_CONTRACT_SHA256",
    "EXPECTED_SEMANTIC_COVERAGE_CODES", "corpus_resource_sha256",
    "load_default_catalog_acceptance_corpus",
]
