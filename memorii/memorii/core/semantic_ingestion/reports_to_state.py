"""Inert state, history, policy, and protected-read contracts for reports-to.

These are package capability owners only.  They never select a catalog, write
the memory plane, or release context.  A later selected-bundle integration
must feed them persisted claim/binding records and current grant certificates.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.semantic_state import PredicateStateRule
from memorii.core.semantic_ingestion.catalog_authority import (
    CatalogAuthorityScope,
    StructuredClaimCatalogBinding,
    StructuredFactReadAuthority,
    StructuredGrantState,
)
from memorii.core.semantic_ingestion.contracts import (
    PredicateTemporalRule,
    PredicateTrustRule,
    contract_digest,
)

_DIGEST = r"^[0-9a-f]{64}$"
_PREDICATE = "reports_to"


class ReportsToPolicyError(ValueError):
    """A reporting-line policy or protected history read is not authorized."""


def reports_to_state_rule() -> PredicateStateRule:
    """Use a multi-value set: one person may report to several distinct people."""
    body = {
        "predicate_id": _PREDICATE, "cardinality": "multi",
        "conflict_behavior": "accumulate_distinct_values", "qualifier_partition_fields": (),
        "value_identity_policy_id": "memorii.reports-to.entity-set.v1",
    }
    return PredicateStateRule(
        **body,
        policy_fingerprint=contract_digest(b"memorii.reports-to.state-rule.v1", body),
    )


def reports_to_temporal_rule() -> PredicateTemporalRule:
    """Reporting lines may be asserted without a bounded valid-time interval."""
    return PredicateTemporalRule(
        predicate_id=_PREDICATE, valid_time_requirement="optional", allow_open_end=True,
    )


def reports_to_trust_rule() -> PredicateTrustRule:
    """Accept authenticated host evidence after the direct-syntax validator succeeds."""
    return PredicateTrustRule(
        predicate_id=_PREDICATE, eligible_authority_classes=frozenset({"official"}),
        authority_rank_by_class={"official": 10},
    )


class ReportsToCatalogMeaning(BaseModel):
    """Stored child meaning; a reader can never substitute the seed catalog."""

    catalog_scope: CatalogAuthorityScope
    catalog_digest: str = Field(pattern=_DIGEST)
    child_version_digest: str = Field(pattern=_DIGEST)
    runtime_bundle_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_base_scope(self) -> ReportsToCatalogMeaning:
        if self.catalog_scope.kind != "base":
            raise ValueError("reports-to catalog meaning must be base scoped")
        return self


class ReportsToLine(BaseModel):
    claim_id: str = Field(min_length=1)
    claim_record_digest: str = Field(pattern=_DIGEST)
    subject_person_id: str = Field(min_length=1)
    manager_person_id: str = Field(min_length=1)
    asserted_at: datetime
    meaning: ReportsToCatalogMeaning
    catalog_binding: StructuredClaimCatalogBinding

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_line(self) -> ReportsToLine:
        if self.subject_person_id == self.manager_person_id:
            raise ValueError("reports-to people must be distinct")
        if (
            self.catalog_binding.claim_assertion_id != self.claim_id
            or self.catalog_binding.claim_record_digest != self.claim_record_digest
            or self.catalog_binding.catalog_scope != self.meaning.catalog_scope
            or self.catalog_binding.catalog_digest != self.meaning.catalog_digest
        ):
            raise ValueError("reports-to line does not bind its persisted catalog claim")
        if self.asserted_at.tzinfo is None or self.asserted_at.utcoffset() != UTC.utcoffset(self.asserted_at):
            raise ValueError("reports-to assertion time must be UTC")
        return self


class ReportsToHistoryEntry(BaseModel):
    event_id: str = Field(min_length=1)
    event_kind: Literal["asserted", "corrected", "retracted"]
    line: ReportsToLine | None = None
    prior_claim_id: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_history_shape(self) -> ReportsToHistoryEntry:
        if self.event_kind == "asserted" and (self.line is None or self.prior_claim_id is not None):
            raise ValueError("reports-to assertion history shape is invalid")
        if self.event_kind == "corrected" and (self.line is None or self.prior_claim_id is None):
            raise ValueError("reports-to correction history shape is invalid")
        if self.event_kind == "retracted" and (self.line is not None or self.prior_claim_id is None):
            raise ValueError("reports-to retraction history shape is invalid")
        return self


class ReportsToCurrentReadGrant(BaseModel):
    """Current-grant certificate supplied by the future canonical read owner."""

    read_authority: StructuredFactReadAuthority
    fact_grant_state: StructuredGrantState
    catalog_visibility_grant_state: StructuredGrantState
    meaning: ReportsToCatalogMeaning

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_grants(self) -> ReportsToCurrentReadGrant:
        authority = self.read_authority
        if (
            self.fact_grant_state.grant_kind != "fact" or not self.fact_grant_state.active
            or self.fact_grant_state.grant != authority.fact_grant
            or self.catalog_visibility_grant_state.grant_kind != "catalog_visibility"
            or not self.catalog_visibility_grant_state.active
            or self.catalog_visibility_grant_state.grant != authority.catalog_visibility_grant
            or authority.catalog_visibility_grant.catalog_scope != self.meaning.catalog_scope
        ):
            raise ValueError("reports-to current grants do not bind catalog meaning")
        return self


class ReportsToProtectedReader:
    """Derive current multi-value state from immutable reporting-line history."""

    def read_current(
        self, *, history: tuple[ReportsToHistoryEntry, ...], grant: ReportsToCurrentReadGrant,
    ) -> tuple[ReportsToLine, ...]:
        active: dict[str, ReportsToLine] = {}
        active_identities: set[tuple[str, str]] = set()
        retired: set[str] = set()
        event_ids: set[str] = set()
        for entry in history:
            if entry.event_id in event_ids:
                raise ReportsToPolicyError("reports-to history event is duplicated")
            event_ids.add(entry.event_id)
            if entry.event_kind == "asserted":
                assert entry.line is not None
                self._authorize_line(entry.line, grant)
                if entry.line.claim_id in active or entry.line.claim_id in retired:
                    raise ReportsToPolicyError("reports-to claim history is duplicated")
                identity = (entry.line.subject_person_id, entry.line.manager_person_id)
                if identity in active_identities:
                    raise ReportsToPolicyError("reports-to active reporting line is duplicated")
                active[entry.line.claim_id] = entry.line
                active_identities.add(identity)
                continue
            assert entry.prior_claim_id is not None
            prior = active.pop(entry.prior_claim_id, None)
            if prior is None or entry.prior_claim_id in retired:
                raise ReportsToPolicyError("reports-to history does not name an active claim")
            retired.add(entry.prior_claim_id)
            active_identities.remove((prior.subject_person_id, prior.manager_person_id))
            if entry.event_kind == "corrected":
                assert entry.line is not None
                if entry.line.subject_person_id != prior.subject_person_id:
                    raise ReportsToPolicyError("reports-to correction changes the reporting person")
                self._authorize_line(entry.line, grant)
                if entry.line.claim_id in active or entry.line.claim_id in retired:
                    raise ReportsToPolicyError("reports-to correction reuses a claim")
                identity = (entry.line.subject_person_id, entry.line.manager_person_id)
                if identity in active_identities:
                    raise ReportsToPolicyError("reports-to correction duplicates an active reporting line")
                active[entry.line.claim_id] = entry.line
                active_identities.add(identity)
        return tuple(sorted(active.values(), key=lambda line: (line.subject_person_id, line.manager_person_id, line.claim_id)))

    @staticmethod
    def _authorize_line(line: ReportsToLine, grant: ReportsToCurrentReadGrant) -> None:
        authority = grant.read_authority
        binding = line.catalog_binding
        if (
            line.meaning != grant.meaning
            or binding.authenticated != authority.authenticated
            or binding.fact_scope != authority.fact_grant.fact_scope
            or binding.catalog_scope != authority.catalog_visibility_grant.catalog_scope
            or binding.catalog_digest != line.meaning.catalog_digest
        ):
            raise ReportsToPolicyError("reports-to historical catalog meaning is unavailable")


__all__ = [
    "ReportsToCatalogMeaning", "ReportsToCurrentReadGrant", "ReportsToHistoryEntry", "ReportsToLine",
    "ReportsToPolicyError", "ReportsToProtectedReader", "reports_to_state_rule", "reports_to_temporal_rule",
    "reports_to_trust_rule",
]
