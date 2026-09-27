"""Typed, inert recurrence groups for verified ontology coverage gaps."""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    MemoryPlaneRevisionConflictError,
    RecordAbsentPrecondition,
    RecordDigestPrecondition,
    record_digest,
)
from memorii.core.semantic_ingestion.catalog_authority import CatalogAuthorityScope
from memorii.core.semantic_ingestion.coverage_observation import (
    CoverageObservation,
    DiscoveryProcessingState,
)
from memorii.domain.enums import (
    CommitStatus,
    MemoryDomain,
    MemoryRecordVisibility,
    TemporalValidityStatus,
)


def _digest(domain: bytes, value: object) -> str:
    payload = json.dumps(
        value,
        default=str,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(domain + b"\0" + payload).hexdigest()


class RelationGapSignature(BaseModel):
    kind: Literal["unsupported_relation"] = "unsupported_relation"
    normalized_relation_meaning: str = Field(min_length=1, max_length=256)
    subject_type_id: str = Field(min_length=1, max_length=256)
    object_type_id: str = Field(min_length=1, max_length=256)
    direction: Literal["subject_to_object"] = "subject_to_object"
    domain_id: str = Field(min_length=1, max_length=256)
    evidence_rule_id: str = Field(min_length=1, max_length=256)
    signature_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def create(
        cls,
        *,
        normalized_relation_meaning: str,
        subject_type_id: str,
        object_type_id: str,
        domain_id: str,
        evidence_rule_id: str,
    ) -> RelationGapSignature:
        body = {
            "kind": "unsupported_relation",
            "normalized_relation_meaning": normalized_relation_meaning,
            "subject_type_id": subject_type_id,
            "object_type_id": object_type_id,
            "direction": "subject_to_object",
            "domain_id": domain_id,
            "evidence_rule_id": evidence_rule_id,
        }
        return cls(
            normalized_relation_meaning=normalized_relation_meaning,
            subject_type_id=subject_type_id,
            object_type_id=object_type_id,
            domain_id=domain_id,
            evidence_rule_id=evidence_rule_id,
            signature_digest=_digest(
                b"memorii.learned-ontology.relation-gap-signature.v1", body
            ),
        )

    @model_validator(mode="after")
    def validate_digest(self) -> RelationGapSignature:
        body = self.model_dump(mode="json", exclude={"signature_digest"})
        if self.signature_digest != _digest(
            b"memorii.learned-ontology.relation-gap-signature.v1", body
        ):
            raise ValueError("relation gap signature digest mismatch")
        return self


class EntityTypeGapSignature(BaseModel):
    kind: Literal["unsupported_entity_type"] = "unsupported_entity_type"
    normalized_type_meaning: str = Field(min_length=1, max_length=256)
    proposed_parent_type_id: str = Field(min_length=1, max_length=256)
    distinguishing_identity_evidence_rule_id: str = Field(
        min_length=1, max_length=256
    )
    scope_class: str = Field(min_length=1, max_length=128)
    signature_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def create(
        cls,
        *,
        normalized_type_meaning: str,
        proposed_parent_type_id: str,
        distinguishing_identity_evidence_rule_id: str,
        scope_class: str,
    ) -> EntityTypeGapSignature:
        body = {
            "kind": "unsupported_entity_type",
            "normalized_type_meaning": normalized_type_meaning,
            "proposed_parent_type_id": proposed_parent_type_id,
            "distinguishing_identity_evidence_rule_id": (
                distinguishing_identity_evidence_rule_id
            ),
            "scope_class": scope_class,
        }
        return cls(
            normalized_type_meaning=normalized_type_meaning,
            proposed_parent_type_id=proposed_parent_type_id,
            distinguishing_identity_evidence_rule_id=(
                distinguishing_identity_evidence_rule_id
            ),
            scope_class=scope_class,
            signature_digest=_digest(
                b"memorii.learned-ontology.entity-type-gap-signature.v1", body
            ),
        )

    @model_validator(mode="after")
    def validate_digest(self) -> EntityTypeGapSignature:
        body = self.model_dump(mode="json", exclude={"signature_digest"})
        if self.signature_digest != _digest(
            b"memorii.learned-ontology.entity-type-gap-signature.v1", body
        ):
            raise ValueError("entity-type gap signature digest mismatch")
        return self


CoverageGapSignature = Annotated[
    RelationGapSignature | EntityTypeGapSignature,
    Field(discriminator="kind"),
]
_SIGNATURE_ADAPTER = TypeAdapter(CoverageGapSignature)


class VerifiedCoverageGap(BaseModel):
    evidence_id: str = Field(min_length=1)
    observation_id: str = Field(min_length=1)
    observation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_scope_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    origin_lineage_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    session_id: str | None
    observed_at: datetime
    catalog_scope: CatalogAuthorityScope
    catalog_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature: CoverageGapSignature
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def from_observation(
        cls,
        observation: CoverageObservation,
        *,
        signature: CoverageGapSignature,
    ) -> VerifiedCoverageGap:
        parsed_signature = _SIGNATURE_ADAPTER.validate_python(signature)
        if (
            observation.processing_state != DiscoveryProcessingState.CLASSIFIED
            or observation.semantic_outcome.value != parsed_signature.kind
            or observation.observer_binding is None
            or observation.source_span is None
        ):
            raise ValueError("coverage observation is not a verified recurrent gap")
        values = {
            "observation_id": observation.observation_id,
            "observation_digest": observation.observation_digest,
            "source_digest": observation.source_digest,
            "source_scope_digest": observation.source_scope_digest,
            "origin_lineage_digest": observation.origin_lineage_digest,
            "session_id": observation.session_id,
            "observed_at": observation.observed_at,
            "catalog_scope": observation.catalog_scope,
            "catalog_digest": observation.catalog_digest,
            "signature": parsed_signature,
        }
        draft = cls.model_construct(
            evidence_id="verified-coverage-gap:v1:pending",
            evidence_digest="0" * 64,
            **values,
        )
        body = draft.model_dump(
            mode="json", exclude={"evidence_id", "evidence_digest"}
        )
        evidence_digest = _digest(
            b"memorii.learned-ontology.verified-coverage-gap.v1", body
        )
        return cls(
            evidence_id=f"verified-coverage-gap:v1:{evidence_digest}",
            evidence_digest=evidence_digest,
            **values,
        )

    @model_validator(mode="after")
    def validate_identity(self) -> VerifiedCoverageGap:
        body = self.model_dump(
            mode="json", exclude={"evidence_id", "evidence_digest"}
        )
        expected = _digest(
            b"memorii.learned-ontology.verified-coverage-gap.v1", body
        )
        if self.evidence_digest != expected or self.evidence_id != (
            f"verified-coverage-gap:v1:{expected}"
        ):
            raise ValueError("verified coverage gap identity mismatch")
        return self


class LineageSessionCoordinate(BaseModel):
    origin_lineage_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    first_session_id: str | None

    model_config = ConfigDict(extra="forbid", frozen=True)


class CoverageRecurrenceGroup(BaseModel):
    group_id: str = Field(min_length=1)
    catalog_scope: CatalogAuthorityScope
    catalog_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_scope_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature: CoverageGapSignature
    evidence_ids: tuple[str, ...]
    lineage_sessions: tuple[LineageSessionCoordinate, ...]
    first_seen: datetime
    last_seen: datetime
    independent_lineage_count: int = Field(ge=1)
    distinct_session_count: int = Field(ge=0)
    example_diversity_count: int = Field(ge=1)
    proposal_eligible: bool
    group_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_group(self) -> CoverageRecurrenceGroup:
        if self.first_seen > self.last_seen:
            raise ValueError("recurrence group timestamps are reversed")
        if self.evidence_ids != tuple(sorted(set(self.evidence_ids))):
            raise ValueError("recurrence evidence IDs must be sorted and unique")
        lineages = tuple(item.origin_lineage_digest for item in self.lineage_sessions)
        if lineages != tuple(sorted(set(lineages))):
            raise ValueError("recurrence lineages must be sorted and unique")
        sessions = {
            item.first_session_id
            for item in self.lineage_sessions
            if item.first_session_id is not None
        }
        eligible = len(lineages) >= 3 and len(sessions) >= 2
        if (
            self.independent_lineage_count != len(lineages)
            or self.distinct_session_count != len(sessions)
            or self.proposal_eligible != eligible
        ):
            raise ValueError("recurrence threshold summary mismatch")
        identity = recurrence_group_id(
            catalog_scope=self.catalog_scope,
            catalog_digest=self.catalog_digest,
            source_scope_digest=self.source_scope_digest,
            signature=self.signature,
        )
        if self.group_id != identity:
            raise ValueError("recurrence group identity mismatch")
        body = self.model_dump(mode="json", exclude={"group_digest"})
        if self.group_digest != _digest(
            b"memorii.learned-ontology.coverage-recurrence-group.v1", body
        ):
            raise ValueError("recurrence group digest mismatch")
        return self


def recurrence_group_id(
    *,
    catalog_scope: CatalogAuthorityScope,
    catalog_digest: str,
    source_scope_digest: str,
    signature: CoverageGapSignature,
) -> str:
    digest = _digest(
        b"memorii.learned-ontology.coverage-recurrence-group-id.v1",
        (
            catalog_scope.model_dump(mode="json"),
            catalog_digest,
            source_scope_digest,
            signature.model_dump(mode="json"),
        ),
    )
    return f"coverage-recurrence-group:v1:{digest}"


def build_coverage_recurrence_group(
    gaps: tuple[VerifiedCoverageGap, ...],
) -> CoverageRecurrenceGroup:
    if not gaps:
        raise ValueError("recurrence group requires verified gaps")
    ordered = tuple(sorted(gaps, key=lambda gap: (gap.observed_at, gap.evidence_id)))
    first = ordered[0]
    expected_id = recurrence_group_id(
        catalog_scope=first.catalog_scope,
        catalog_digest=first.catalog_digest,
        source_scope_digest=first.source_scope_digest,
        signature=first.signature,
    )
    if any(
        recurrence_group_id(
            catalog_scope=gap.catalog_scope,
            catalog_digest=gap.catalog_digest,
            source_scope_digest=gap.source_scope_digest,
            signature=gap.signature,
        )
        != expected_id
        for gap in ordered
    ):
        raise ValueError("verified gaps cross a recurrence boundary")
    representatives: dict[str, VerifiedCoverageGap] = {}
    for gap in ordered:
        representatives.setdefault(gap.origin_lineage_digest, gap)
    lineage_sessions = tuple(
        LineageSessionCoordinate(
            origin_lineage_digest=lineage,
            first_session_id=representatives[lineage].session_id,
        )
        for lineage in sorted(representatives)
    )
    sessions = {
        coordinate.first_session_id
        for coordinate in lineage_sessions
        if coordinate.first_session_id is not None
    }
    body = {
        "group_id": expected_id,
        "catalog_scope": first.catalog_scope,
        "catalog_digest": first.catalog_digest,
        "source_scope_digest": first.source_scope_digest,
        "signature": first.signature,
        "evidence_ids": tuple(sorted({gap.evidence_id for gap in ordered})),
        "lineage_sessions": lineage_sessions,
        "first_seen": ordered[0].observed_at,
        "last_seen": ordered[-1].observed_at,
        "independent_lineage_count": len(lineage_sessions),
        "distinct_session_count": len(sessions),
        "example_diversity_count": len(
            {gap.source_digest for gap in representatives.values()}
        ),
        "proposal_eligible": len(lineage_sessions) >= 3 and len(sessions) >= 2,
    }
    digest_body = CoverageRecurrenceGroup.model_construct(
        **body, group_digest="0" * 64
    ).model_dump(mode="json", exclude={"group_digest"})
    return CoverageRecurrenceGroup.model_validate(
        {
            **body,
            "group_digest": _digest(
                b"memorii.learned-ontology.coverage-recurrence-group.v1",
                digest_body,
            ),
        }
    )


class CoverageRecurrenceRepository:
    _KIND = "learned_ontology_coverage_recurrence_group_v1"

    def __init__(self, memory_plane: MemoryPlaneService) -> None:
        self._plane = memory_plane

    def load(self, group_id: str) -> CoverageRecurrenceGroup | None:
        record = self._plane.get_record(group_id)
        if (
            record is None
            or record.domain != MemoryDomain.EXECUTION
            or record.visibility != MemoryRecordVisibility.INTERNAL_CONTROL
            or record.source_kind != self._KIND
        ):
            return None
        try:
            return CoverageRecurrenceGroup.model_validate(record.content["group"])
        except (KeyError, TypeError, ValueError):
            return None

    def write(
        self,
        group: CoverageRecurrenceGroup,
        *,
        previous: CoverageRecurrenceGroup | None,
    ) -> CoverageRecurrenceGroup:
        record = self._record(group)
        preconditions = (
            (RecordAbsentPrecondition(memory_id=group.group_id),)
            if previous is None
            else (
                RecordDigestPrecondition(
                    memory_id=group.group_id,
                    expected_digest=record_digest(self._record(previous)),
                ),
            )
        )
        try:
            self._plane.conditionally_write_records(
                (record,), preconditions=preconditions
            )
        except MemoryPlaneRevisionConflictError:
            current = self.load(group.group_id)
            if current == group:
                return group
            raise
        return group

    def _record(self, group: CoverageRecurrenceGroup) -> CanonicalMemoryRecord:
        return CanonicalMemoryRecord(
            memory_id=group.group_id,
            domain=MemoryDomain.EXECUTION,
            text=("proposal_eligible" if group.proposal_eligible else "observing"),
            content={"kind": self._KIND, "group": group.model_dump(mode="json")},
            status=CommitStatus.COMMITTED,
            validity_status=TemporalValidityStatus.ACTIVE,
            source_kind=self._KIND,
            timestamp=group.last_seen,
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )


__all__ = [
    "CoverageGapSignature",
    "CoverageRecurrenceGroup",
    "CoverageRecurrenceRepository",
    "EntityTypeGapSignature",
    "LineageSessionCoordinate",
    "RelationGapSignature",
    "VerifiedCoverageGap",
    "build_coverage_recurrence_group",
    "recurrence_group_id",
]
