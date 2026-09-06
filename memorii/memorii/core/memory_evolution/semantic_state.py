"""Immutable temporal and trust projection-history contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)

from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.memory_evolution.projection_binding import (
    ProjectionHistoryReplayBinding,
    ProjectionKind,
)
from memorii.core.memory_evolution.time_contracts import TimeInterval

ClaimObjectKind = Literal["entity", "literal"]
PredicateCardinality = Literal["single", "multi"]
PredicateConflictBehavior = Literal[
    "compete_within_slot",
    "accumulate_distinct_values",
    "explicit_contradiction_only",
]


class ImmutableAssertionEntityRef(BaseModel):
    entity_revision_id: str = Field(min_length=1)
    logical_entity_id_at_assertion: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SemanticClaimSlotKey(BaseModel):
    subject_logical_entity_id: str = Field(min_length=1)
    predicate_id: str = Field(min_length=1)
    scope_identity: str = Field(min_length=1)
    qualifier_partition: tuple[tuple[str, str], ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_slot(self) -> SemanticClaimSlotKey:
        if self.qualifier_partition != tuple(sorted(set(self.qualifier_partition))):
            raise ValueError("claim qualifier partition must be canonical")
        if any(not key or not value for key, value in self.qualifier_partition):
            raise ValueError("claim qualifier partition cannot contain empty values")
        return self


class SemanticClaimValueKey(BaseModel):
    object_kind: ClaimObjectKind
    object_logical_entity_id: str | None = None
    literal_type: str | None = None
    canonical_literal_value: str | None = None
    value_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_value(self) -> SemanticClaimValueKey:
        entity_shape = (
            self.object_logical_entity_id is not None
            and self.literal_type is None
            and self.canonical_literal_value is None
        )
        literal_shape = (
            self.object_logical_entity_id is None
            and self.literal_type is not None
            and self.canonical_literal_value is not None
        )
        if (self.object_kind == "entity" and not entity_shape) or (self.object_kind == "literal" and not literal_shape):
            raise ValueError("claim value fields do not match object kind")
        return self


class SemanticAssertionKey(BaseModel):
    slot: SemanticClaimSlotKey
    value: SemanticClaimValueKey

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PredicateStateRule(BaseModel):
    predicate_id: str = Field(min_length=1)
    cardinality: PredicateCardinality
    conflict_behavior: PredicateConflictBehavior
    qualifier_partition_fields: tuple[str, ...] = ()
    value_identity_policy_id: str = Field(min_length=1)
    policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_rule(self) -> PredicateStateRule:
        if self.qualifier_partition_fields != tuple(sorted(set(self.qualifier_partition_fields))):
            raise ValueError("predicate qualifier fields must be canonical")
        if self.cardinality == "single" and self.conflict_behavior != "compete_within_slot":
            raise ValueError("single-valued predicates must compete within one slot")
        if self.cardinality == "multi" and self.conflict_behavior == "compete_within_slot":
            raise ValueError("multi-valued predicates cannot use single-slot competition")
        return self


class AcceptedClaimIdentity(BaseModel):
    """Lineage-resolved claim identity supplied by the accepted compiler input."""

    subject_assertion_ref: ImmutableAssertionEntityRef
    object_assertion_ref: ImmutableAssertionEntityRef | None = None
    assertion_key_at_recording: SemanticAssertionKey
    predicate_state_rule: PredicateStateRule
    identity_lineage_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_identity(self) -> AcceptedClaimIdentity:
        slot = self.assertion_key_at_recording.slot
        value = self.assertion_key_at_recording.value
        if (
            self.subject_assertion_ref.logical_entity_id_at_assertion != slot.subject_logical_entity_id
            or self.predicate_state_rule.predicate_id != slot.predicate_id
            or tuple(key for key, _ in slot.qualifier_partition) != self.predicate_state_rule.qualifier_partition_fields
        ):
            raise ValueError("claim identity differs from its predicate state rule")
        if value.object_kind == "entity":
            if (
                self.object_assertion_ref is None
                or self.object_assertion_ref.logical_entity_id_at_assertion != value.object_logical_entity_id
            ):
                raise ValueError("entity claim value lacks its immutable assertion reference")
        elif self.object_assertion_ref is not None:
            raise ValueError("literal claim value cannot carry an entity assertion reference")
        return self


ProjectionRecordKind = Literal[
    "claim_assertion",
    "action_revision",
    "identity_lineage",
    "temporal_transition",
]
ProjectionPublicationKind = Literal["migration_cutover", "projection_commit"]


IdentityLineageOperation = Literal["alias", "rekey", "merge", "split"]
LineageReferenceRecordKind = Literal[
    "entity_revision",
    "alias_revision",
    "identity_lineage",
    "type_evidence",
    "claim_assertion",
    "claim_projection",
    "action_revision",
    "citation",
    "provenance",
    "relation_revision",
    "temporal_transition",
    "reference_disposition",
]
ReferenceDispositionKind = Literal[
    "preserve_historical",
    "redirect_current",
    "migrate_current",
    "share_by_explicit_evidence",
]
ReferenceDispositionBasis = Literal[
    "source_assignment",
    "operation_defined_rekey_redirect",
    "operation_defined_merge_redirect",
    "operation_defined_history_preservation",
]

_LINEAGE_REFERENCE_DOMAIN = b"memorii.identity-lineage.reverse-reference.v1\0"
_LINEAGE_DISPOSITION_DOMAIN = b"memorii.identity-lineage.reference-disposition.v1\0"
_LINEAGE_TRANSITION_DOMAIN = b"memorii.identity-lineage.transition.v1\0"
_LINEAGE_SNAPSHOT_DOMAIN = b"memorii.identity-lineage.snapshot.v1\0"


class LineageEntityIdentity(BaseModel):
    entity_revision_id: str = Field(min_length=1)
    logical_entity_id: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class LineageEvidenceReference(BaseModel):
    source_id: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(ge=1)
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_span(self) -> LineageEvidenceReference:
        if self.end <= self.start:
            raise ValueError("lineage evidence span must be nonempty")
        return self


class GroundedLineageReferenceAssignment(BaseModel):
    """Source-backed decision for one exact member of a reverse-reference closure."""

    reference_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    successors: tuple[LineageEntityIdentity, ...] = ()
    disposition: ReferenceDispositionKind
    source_evidence: tuple[LineageEvidenceReference, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_assignment(self) -> GroundedLineageReferenceAssignment:
        if self.successors != tuple(sorted(set(self.successors), key=_lineage_identity_key)):
            raise ValueError("identity_lineage_assignment_successors_not_canonical")
        if self.source_evidence != tuple(sorted(set(self.source_evidence), key=_lineage_evidence_key)):
            raise ValueError("identity_lineage_assignment_evidence_not_canonical")
        if self.disposition == "preserve_historical":
            valid = not self.successors
        elif self.disposition == "share_by_explicit_evidence":
            valid = len(self.successors) > 1 and bool(self.source_evidence)
        else:
            valid = len(self.successors) == 1 and bool(self.source_evidence)
        if not valid:
            raise ValueError("identity_lineage_assignment_shape_invalid")
        return self


class AcceptedIdentityOperation(BaseModel):
    """Language-neutral, graph-addressed IR accepted before lineage compilation."""

    operation_id: str = Field(min_length=1)
    operation: IdentityLineageOperation
    predecessors: tuple[LineageEntityIdentity, ...]
    successors: tuple[LineageEntityIdentity, ...]
    source_evidence: tuple[LineageEvidenceReference, ...]
    reference_assignments: tuple[GroundedLineageReferenceAssignment, ...] = ()
    accepted_operation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_operation(self) -> AcceptedIdentityOperation:
        if self.predecessors != tuple(sorted(set(self.predecessors), key=_lineage_identity_key)):
            raise ValueError("accepted_identity_predecessors_not_canonical")
        if self.successors != tuple(sorted(set(self.successors), key=_lineage_identity_key)):
            raise ValueError("accepted_identity_successors_not_canonical")
        if not self.source_evidence or self.source_evidence != tuple(
            sorted(set(self.source_evidence), key=_lineage_evidence_key)
        ):
            raise ValueError("accepted_identity_source_evidence_invalid")
        assignment_keys = tuple(item.reference_digest for item in self.reference_assignments)
        if assignment_keys != tuple(sorted(set(assignment_keys))):
            raise ValueError("accepted_identity_assignments_not_canonical")
        probe = CompiledIdentityLineageTransition.create(
            operation_id=self.operation_id,
            operation=self.operation,
            predecessors=self.predecessors,
            successors=self.successors,
            graph_revision_before="accepted-ir-shape-check",
            recorded_at=datetime(1970, 1, 1, tzinfo=UTC),
            lineage_snapshot_before_digest="0" * 64,
            source_evidence=self.source_evidence,
            reverse_reference_closure=(),
            reference_dispositions=(),
        )
        del probe
        body = self.model_dump(mode="python", exclude={"accepted_operation_digest"})
        if self.accepted_operation_digest != _digest(b"memorii.accepted-identity-operation.v1\0", body):
            raise ValueError("accepted_identity_operation_digest_mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> AcceptedIdentityOperation:
        return cls.model_validate(
            values
            | {
                "accepted_operation_digest": _digest(
                    b"memorii.accepted-identity-operation.v1\0", values
                )
            }
        )


class LineageReverseReference(BaseModel):
    record_kind: LineageReferenceRecordKind
    record_id: str = Field(min_length=1)
    reference_path: str = Field(min_length=1)
    predecessor: LineageEntityIdentity
    lifecycle: Literal["current", "historical"]
    base_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    referenced_value_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_digest(self) -> LineageReverseReference:
        body = self.model_dump(mode="python", exclude={"reference_digest"})
        if self.reference_digest != _digest(_LINEAGE_REFERENCE_DOMAIN, body):
            raise ValueError("identity_lineage_reference_digest_mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> LineageReverseReference:
        return cls.model_validate(
            values
            | {"reference_digest": _digest(_LINEAGE_REFERENCE_DOMAIN, values)}
        )


class LineageReferenceDisposition(BaseModel):
    reference_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    record_kind: LineageReferenceRecordKind
    record_id: str = Field(min_length=1)
    reference_path: str = Field(min_length=1)
    predecessor: LineageEntityIdentity
    disposition: ReferenceDispositionKind
    successors: tuple[LineageEntityIdentity, ...] = ()
    source_evidence: tuple[LineageEvidenceReference, ...] = ()
    basis: ReferenceDispositionBasis
    disposition_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_disposition(self) -> LineageReferenceDisposition:
        if self.successors != tuple(sorted(set(self.successors), key=_lineage_identity_key)):
            raise ValueError("identity_lineage_successors_not_canonical")
        if self.source_evidence != tuple(sorted(set(self.source_evidence), key=_lineage_evidence_key)):
            raise ValueError("identity_lineage_evidence_not_canonical")
        if self.disposition == "preserve_historical":
            valid_shape = not self.successors and self.basis == "operation_defined_history_preservation"
        elif self.disposition == "share_by_explicit_evidence":
            valid_shape = bool(self.successors and self.source_evidence) and self.basis == "source_assignment"
        else:
            valid_shape = len(self.successors) == 1
        if not valid_shape:
            raise ValueError("identity_lineage_disposition_shape_invalid")
        body = self.model_dump(mode="python", exclude={"disposition_digest"})
        if self.disposition_digest != _digest(_LINEAGE_DISPOSITION_DOMAIN, body):
            raise ValueError("identity_lineage_disposition_digest_mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> LineageReferenceDisposition:
        return cls.model_validate(
            values
            | {"disposition_digest": _digest(_LINEAGE_DISPOSITION_DOMAIN, values)}
        )


class CompiledIdentityLineageTransition(BaseModel):
    operation_id: str = Field(min_length=1)
    operation: IdentityLineageOperation
    predecessors: tuple[LineageEntityIdentity, ...]
    successors: tuple[LineageEntityIdentity, ...]
    graph_revision_before: str = Field(min_length=1)
    recorded_at: datetime | None
    lineage_snapshot_before_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_evidence: tuple[LineageEvidenceReference, ...]
    reverse_reference_closure: tuple[LineageReverseReference, ...]
    reference_dispositions: tuple[LineageReferenceDisposition, ...]
    transition_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_transition(self) -> CompiledIdentityLineageTransition:
        if self.recorded_at is not None and (
            self.recorded_at.tzinfo is None
            or self.recorded_at.utcoffset() != timedelta(0)
        ):
            raise ValueError("identity_lineage_recorded_at_invalid")
        if self.predecessors != tuple(sorted(set(self.predecessors), key=_lineage_identity_key)):
            raise ValueError("identity_lineage_predecessors_not_canonical")
        if self.successors != tuple(sorted(set(self.successors), key=_lineage_identity_key)):
            raise ValueError("identity_lineage_successors_not_canonical")
        if self.source_evidence != tuple(sorted(set(self.source_evidence), key=_lineage_evidence_key)) or not self.source_evidence:
            raise ValueError("identity_lineage_source_evidence_invalid")
        self._validate_operation_shape()
        closure = {item.reference_digest: item for item in self.reverse_reference_closure}
        if (
            len(closure) != len(self.reverse_reference_closure)
            or self.reverse_reference_closure
            != tuple(sorted(self.reverse_reference_closure, key=lambda item: item.reference_digest))
        ):
            raise ValueError("identity_lineage_reference_closure_not_canonical")
        dispositions = {item.reference_digest: item for item in self.reference_dispositions}
        if (
            len(dispositions) != len(self.reference_dispositions)
            or self.reference_dispositions
            != tuple(sorted(self.reference_dispositions, key=lambda item: item.reference_digest))
            or set(dispositions) != set(closure)
        ):
            raise ValueError("identity_lineage_reference_closure_mismatch")
        for reference_digest, reference in closure.items():
            disposition = dispositions[reference_digest]
            if (
                disposition.record_kind != reference.record_kind
                or disposition.record_id != reference.record_id
                or disposition.reference_path != reference.reference_path
                or disposition.predecessor != reference.predecessor
                or reference.predecessor not in self.predecessors
            ):
                raise ValueError("identity_lineage_reference_binding_mismatch")
            self._validate_disposition(reference, disposition)
        body = self.model_dump(mode="python", exclude={"transition_digest"})
        if self.transition_digest != _digest(_LINEAGE_TRANSITION_DOMAIN, body):
            raise ValueError("identity_lineage_transition_digest_mismatch")
        return self

    def _validate_operation_shape(self) -> None:
        predecessor_logical = {item.logical_entity_id for item in self.predecessors}
        successor_logical = {item.logical_entity_id for item in self.successors}
        predecessor_revisions = {item.entity_revision_id for item in self.predecessors}
        successor_revisions = {item.entity_revision_id for item in self.successors}
        if predecessor_revisions & successor_revisions:
            raise ValueError("identity_lineage_revision_reuse")
        if self.operation == "alias":
            if self.predecessors or self.successors or self.reverse_reference_closure or self.reference_dispositions:
                raise ValueError("identity_lineage_alias_rewrites_identity")
        elif self.operation == "rekey":
            if len(self.predecessors) != 1 or len(self.successors) != 1 or predecessor_logical != successor_logical:
                raise ValueError("identity_lineage_rekey_shape_invalid")
        elif self.operation == "merge":
            if len(self.predecessors) < 2 or len(self.successors) != 1 or successor_logical & predecessor_logical:
                raise ValueError("identity_lineage_merge_shape_invalid")
        elif (
            len(self.predecessors) != 1
            or len(self.successors) < 2
            or successor_logical & predecessor_logical
            or len(successor_logical) != len(self.successors)
        ):
            raise ValueError("identity_lineage_split_shape_invalid")

    def _validate_disposition(
        self,
        reference: LineageReverseReference,
        disposition: LineageReferenceDisposition,
    ) -> None:
        successor_set = set(self.successors)
        if not set(disposition.successors).issubset(successor_set):
            raise ValueError("identity_lineage_disposition_successor_invalid")
        if reference.lifecycle == "historical":
            if disposition.disposition != "preserve_historical":
                raise ValueError("identity_lineage_historical_reference_rewritten")
            return
        if disposition.disposition == "preserve_historical":
            raise ValueError("identity_lineage_current_reference_not_resolved")
        if self.operation == "rekey":
            if disposition.disposition != "redirect_current" or disposition.basis != "operation_defined_rekey_redirect":
                raise ValueError("identity_lineage_rekey_disposition_invalid")
        elif self.operation == "merge":
            if disposition.disposition != "redirect_current" or disposition.basis != "operation_defined_merge_redirect":
                raise ValueError("identity_lineage_merge_disposition_invalid")
        elif self.operation == "split" and (
            disposition.basis != "source_assignment" or not disposition.source_evidence
        ):
            raise ValueError("identity_lineage_split_assignment_missing")

    @classmethod
    def create(cls, **values: object) -> CompiledIdentityLineageTransition:
        return cls.model_validate(
            values
            | {"transition_digest": _digest(_LINEAGE_TRANSITION_DOMAIN, values)}
        )

    @property
    def lineage_snapshot_after_digest(self) -> str:
        return _digest(
            _LINEAGE_SNAPSHOT_DOMAIN,
            {
                "lineage_snapshot_before_digest": self.lineage_snapshot_before_digest,
                "transition_digest": self.transition_digest,
            },
        )


def _lineage_identity_key(value: LineageEntityIdentity) -> tuple[str, str]:
    return value.entity_revision_id, value.logical_entity_id


def _lineage_evidence_key(value: LineageEvidenceReference) -> tuple[str, int, int, str]:
    return value.source_id, value.start, value.end, value.evidence_digest

_TEMPORAL_RECORD_DOMAIN = b"memorii.temporal-projection-record.v1\0"
_TRUST_RECORD_DOMAIN = b"memorii.trust-projection-record.v1\0"
_TEMPORAL_GENERATION_DOMAIN = b"memorii.temporal-projection-generation.v1\0"
_TRUST_GENERATION_DOMAIN = b"memorii.trust-projection-generation.v1\0"
_TEMPORAL_CERTIFICATE_DOMAIN = b"memorii.temporal-projection-certificate.v1\0"
_TRUST_CERTIFICATE_DOMAIN = b"memorii.trust-projection-certificate.v1\0"
_TEMPORAL_POINTER_DOMAIN = b"memorii.temporal-projection-pointer.v1\0"
_TRUST_POINTER_DOMAIN = b"memorii.trust-projection-pointer.v1\0"
_HISTORY_ENTRY_DOMAIN = b"memorii.projection-history-entry.v1\0"


def _canonical_digest_value(value: object) -> object:
    if isinstance(value, BaseModel):
        return _canonical_digest_value(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {key: _canonical_digest_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_canonical_digest_value(item) for item in value)
    if isinstance(value, list):
        return [_canonical_digest_value(item) for item in value]
    return value


def _digest(domain: bytes, value: object) -> str:
    return sha256(domain + encode_typed_value(_canonical_digest_value(value))).hexdigest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("projection time must be timezone-aware")
    normalized = value.astimezone(UTC)
    return normalized


def _strict_digest(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, tuple):
        return tuple(_strict_digest(item) for item in value)
    if not isinstance(value, str):
        raise TypeError("projection digest must be a string")
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("projection digest must be lowercase hexadecimal")
    return value


class ProjectionEvidenceRecord(BaseModel):
    candidate_id: str = Field(min_length=1)
    candidate_digest: str
    authority_relation: Literal["winner", "contested_top", "retained_noncurrent"]
    assertion_key: SemanticAssertionKey | None = None
    source_id: str | None = None
    source_authority_class: str | None = None
    source_authority_evidence_digest: str | None = None
    source_event_id: str | None = None
    source_event_digest: str | None = None
    transaction_group_id: str | None = None
    valid_interval: TimeInterval | None = None
    system_valid_from: datetime | None = None

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digest = field_validator(
        "candidate_digest",
        "source_authority_evidence_digest",
        "source_event_digest",
    )(_strict_digest)

    @model_validator(mode="after")
    def validate_assertion_evidence(self) -> ProjectionEvidenceRecord:
        assertion_coordinates = (
            self.assertion_key,
            self.source_id,
            self.source_authority_class,
            self.source_authority_evidence_digest,
            self.source_event_id,
            self.source_event_digest,
            self.transaction_group_id,
            self.system_valid_from,
        )
        if any(value is None for value in assertion_coordinates) != all(
            value is None for value in assertion_coordinates
        ):
            raise ValueError("projection assertion evidence coordinates must be complete")
        if self.assertion_key is None and self.valid_interval is not None:
            raise ValueError("legacy projection evidence cannot add a valid interval")
        if self.system_valid_from is not None:
            _utc(self.system_valid_from)
        return self

    @model_serializer(mode="wrap")
    def serialize_evidence(self, handler):
        values = handler(self)
        if self.assertion_key is None:
            for field in (
                "assertion_key",
                "source_id",
                "source_authority_class",
                "source_authority_evidence_digest",
                "source_event_id",
                "source_event_digest",
                "transaction_group_id",
                "valid_interval",
                "system_valid_from",
            ):
                values.pop(field, None)
        return values


class TemporalProjectionRecord(BaseModel):
    projection_id: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    source_record_kind: ProjectionRecordKind
    source_record_id: str = Field(min_length=1)
    source_record_version: int = Field(ge=1)
    source_record_digest: str
    temporal_policy_fingerprint: str
    claim_slot_key: SemanticClaimSlotKey | None = None
    predicate_state_policy_fingerprint: str | None = None
    selected_assertion_ids: tuple[str, ...] = ()
    contested_assertion_ids: tuple[str, ...] = ()
    retained_assertion_ids: tuple[str, ...] = ()
    system_valid_from: datetime | None = None
    valid_interval: TimeInterval | None
    outcome: Literal["pass", "unknown", "contested"]
    evidence: tuple[ProjectionEvidenceRecord, ...]
    projection_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digests = field_validator(
        "source_record_digest",
        "temporal_policy_fingerprint",
        "predicate_state_policy_fingerprint",
        "projection_digest",
    )(_strict_digest)

    @model_validator(mode="after")
    def validate_projection(self) -> TemporalProjectionRecord:
        candidate_ids = tuple(item.candidate_id for item in self.evidence)
        if candidate_ids != tuple(sorted(set(candidate_ids))):
            raise ValueError("temporal projection evidence is not canonical")
        selected = tuple(item for item in self.evidence if item.authority_relation == "winner")
        contested = tuple(item for item in self.evidence if item.authority_relation == "contested_top")
        typed_coordinates = (
            self.claim_slot_key,
            self.predicate_state_policy_fingerprint,
            self.system_valid_from,
        )
        if any(value is None for value in typed_coordinates) != all(value is None for value in typed_coordinates):
            raise ValueError("typed temporal projection coordinates must be complete")
        assertion_partitions = (
            self.selected_assertion_ids,
            self.contested_assertion_ids,
            self.retained_assertion_ids,
        )
        if any(values != tuple(sorted(set(values))) for values in assertion_partitions):
            raise ValueError("temporal assertion membership must be canonical")
        if (
            set(self.selected_assertion_ids) & set(self.contested_assertion_ids)
            or set(self.selected_assertion_ids) & set(self.retained_assertion_ids)
            or set(self.contested_assertion_ids) & set(self.retained_assertion_ids)
        ):
            raise ValueError("temporal assertion membership overlaps")
        if self.claim_slot_key is not None:
            expected = {item.candidate_id: item.authority_relation for item in self.evidence}
            observed = {
                **{value: "winner" for value in self.selected_assertion_ids},
                **{value: "contested_top" for value in self.contested_assertion_ids},
                **{value: "retained_noncurrent" for value in self.retained_assertion_ids},
            }
            if expected != observed or any(
                item.assertion_key is None or item.assertion_key.slot != self.claim_slot_key for item in self.evidence
            ):
                raise ValueError("temporal projection membership differs from assertion evidence")
            assert self.system_valid_from is not None
            _utc(self.system_valid_from)
        if self.outcome == "contested":
            if selected or len(contested) < 2:
                raise ValueError("contested temporal projection cannot expose a stable winner")
        elif contested:
            raise ValueError("non-contested temporal projection invents contested evidence")
        elif self.outcome == "pass" and not selected:
            raise ValueError("passing temporal projection requires a winner")
        elif self.outcome == "unknown" and selected:
            raise ValueError("unknown temporal projection cannot expose a winner")
        body = self.model_dump(mode="python", exclude={"projection_digest"})
        if self.projection_digest != _digest(_TEMPORAL_RECORD_DOMAIN, body):
            raise ValueError("temporal projection digest mismatch")
        return self

    @model_serializer(mode="wrap")
    def serialize_projection(self, handler):
        values = handler(self)
        if self.claim_slot_key is None:
            for field in (
                "claim_slot_key",
                "predicate_state_policy_fingerprint",
                "selected_assertion_ids",
                "contested_assertion_ids",
                "retained_assertion_ids",
                "system_valid_from",
            ):
                values.pop(field, None)
        return values

    @classmethod
    def create(cls, **values: object) -> TemporalProjectionRecord:
        return cls.model_validate(
            {
                **values,
                "projection_digest": _digest(_TEMPORAL_RECORD_DOMAIN, values),
            }
        )


class TrustProjectionRecord(BaseModel):
    projection_id: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    source_record_kind: ProjectionRecordKind
    source_record_id: str = Field(min_length=1)
    source_record_version: int = Field(ge=1)
    source_record_digest: str
    trust_policy_fingerprint: str
    claim_slot_key: SemanticClaimSlotKey | None = None
    predicate_state_policy_fingerprint: str | None = None
    selected_assertion_ids: tuple[str, ...] = ()
    contested_assertion_ids: tuple[str, ...] = ()
    retained_assertion_ids: tuple[str, ...] = ()
    system_valid_from: datetime | None = None
    arbitration_as_of: datetime
    valid_interval: TimeInterval | None = None
    outcome: Literal["pass", "unknown", "contested"]
    evidence: tuple[ProjectionEvidenceRecord, ...]
    projection_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digests = field_validator(
        "source_record_digest",
        "trust_policy_fingerprint",
        "predicate_state_policy_fingerprint",
        "projection_digest",
    )(_strict_digest)
    _validate_time = field_validator("arbitration_as_of")(_utc)

    @model_validator(mode="after")
    def validate_projection(self) -> TrustProjectionRecord:
        candidate_ids = tuple(item.candidate_id for item in self.evidence)
        if candidate_ids != tuple(sorted(set(candidate_ids))):
            raise ValueError("trust projection evidence is not canonical")
        selected = tuple(item for item in self.evidence if item.authority_relation == "winner")
        contested = tuple(item for item in self.evidence if item.authority_relation == "contested_top")
        typed_coordinates = (
            self.claim_slot_key,
            self.predicate_state_policy_fingerprint,
            self.system_valid_from,
        )
        if any(value is None for value in typed_coordinates) != all(value is None for value in typed_coordinates):
            raise ValueError("typed trust projection coordinates must be complete")
        assertion_partitions = (
            self.selected_assertion_ids,
            self.contested_assertion_ids,
            self.retained_assertion_ids,
        )
        if any(values != tuple(sorted(set(values))) for values in assertion_partitions):
            raise ValueError("trust assertion membership must be canonical")
        if (
            set(self.selected_assertion_ids) & set(self.contested_assertion_ids)
            or set(self.selected_assertion_ids) & set(self.retained_assertion_ids)
            or set(self.contested_assertion_ids) & set(self.retained_assertion_ids)
        ):
            raise ValueError("trust assertion membership overlaps")
        if self.claim_slot_key is not None:
            expected = {item.candidate_id: item.authority_relation for item in self.evidence}
            observed = {
                **{value: "winner" for value in self.selected_assertion_ids},
                **{value: "contested_top" for value in self.contested_assertion_ids},
                **{value: "retained_noncurrent" for value in self.retained_assertion_ids},
            }
            if expected != observed or any(
                item.assertion_key is None or item.assertion_key.slot != self.claim_slot_key for item in self.evidence
            ):
                raise ValueError("trust projection membership differs from assertion evidence")
            assert self.system_valid_from is not None
            _utc(self.system_valid_from)
        elif self.valid_interval is not None:
            raise ValueError("legacy trust projection cannot add a valid interval")
        if self.outcome == "contested":
            if selected or len(contested) < 2:
                raise ValueError("contested trust projection cannot expose a stable winner")
        elif contested:
            raise ValueError("non-contested trust projection invents contested evidence")
        elif self.outcome == "pass" and not selected:
            raise ValueError("passing trust projection requires a winner")
        elif self.outcome == "unknown" and selected:
            raise ValueError("unknown trust projection cannot expose a winner")
        body = self.model_dump(mode="python", exclude={"projection_digest"})
        if self.projection_digest != _digest(_TRUST_RECORD_DOMAIN, body):
            raise ValueError("trust projection digest mismatch")
        return self

    @model_serializer(mode="wrap")
    def serialize_projection(self, handler):
        values = handler(self)
        if self.claim_slot_key is None:
            for field in (
                "claim_slot_key",
                "predicate_state_policy_fingerprint",
                "selected_assertion_ids",
                "contested_assertion_ids",
                "retained_assertion_ids",
                "system_valid_from",
                "valid_interval",
            ):
                values.pop(field, None)
        return values

    @classmethod
    def create(cls, **values: object) -> TrustProjectionRecord:
        return cls.model_validate(
            {
                **values,
                "projection_digest": _digest(_TRUST_RECORD_DOMAIN, values),
            }
        )


class TemporalProjectionGeneration(BaseModel):
    generation_id: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    temporal_policy_fingerprint: str
    predecessor_generation_digest: str | None
    migration_plan_digest: str
    base_snapshot_token: str = Field(min_length=1)
    base_graph_revision: str = Field(min_length=1)
    final_catch_up_watermark: str = Field(min_length=1)
    canonical_slot_result_digests: tuple[str, ...]
    canonical_projection_digests: tuple[str, ...]
    publication_kind: ProjectionPublicationKind
    publication_certificate_digest: str
    activated_writer_epoch: int = Field(ge=1)
    activated_at: datetime
    generation_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digests = field_validator(
        "temporal_policy_fingerprint",
        "predecessor_generation_digest",
        "migration_plan_digest",
        "canonical_slot_result_digests",
        "canonical_projection_digests",
        "publication_certificate_digest",
        "generation_digest",
    )(_strict_digest)
    _validate_time = field_validator("activated_at")(_utc)

    @model_validator(mode="after")
    def validate_generation(self) -> TemporalProjectionGeneration:
        if self.canonical_slot_result_digests != tuple(
            sorted(set(self.canonical_slot_result_digests))
        ) or self.canonical_projection_digests != tuple(sorted(set(self.canonical_projection_digests))):
            raise ValueError("temporal projection generation membership is not canonical")
        body = self.model_dump(
            mode="python",
            exclude={"generation_digest", "publication_certificate_digest"},
        )
        if self.generation_digest != _digest(_TEMPORAL_GENERATION_DOMAIN, body):
            raise ValueError("temporal projection generation digest mismatch")
        return self


class TrustProjectionGeneration(BaseModel):
    generation_id: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    trust_policy_fingerprint: str
    predecessor_generation_digest: str | None
    migration_plan_digest: str
    base_snapshot_token: str = Field(min_length=1)
    base_graph_revision: str = Field(min_length=1)
    final_catch_up_watermark: str = Field(min_length=1)
    canonical_slot_result_digests: tuple[str, ...]
    canonical_projection_digests: tuple[str, ...]
    canonical_decay_command_digests: tuple[str, ...]
    publication_kind: ProjectionPublicationKind
    publication_certificate_digest: str
    arbitration_as_of: datetime
    activated_writer_epoch: int = Field(ge=1)
    activated_at: datetime
    generation_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digests = field_validator(
        "trust_policy_fingerprint",
        "predecessor_generation_digest",
        "migration_plan_digest",
        "canonical_slot_result_digests",
        "canonical_projection_digests",
        "canonical_decay_command_digests",
        "publication_certificate_digest",
        "generation_digest",
    )(_strict_digest)
    _validate_times = field_validator("arbitration_as_of", "activated_at")(_utc)

    @model_validator(mode="after")
    def validate_generation(self) -> TrustProjectionGeneration:
        for values in (
            self.canonical_slot_result_digests,
            self.canonical_projection_digests,
            self.canonical_decay_command_digests,
        ):
            if values != tuple(sorted(set(values))):
                raise ValueError("trust projection generation membership is not canonical")
        body = self.model_dump(
            mode="python",
            exclude={"generation_digest", "publication_certificate_digest"},
        )
        if self.generation_digest != _digest(_TRUST_GENERATION_DOMAIN, body):
            raise ValueError("trust projection generation digest mismatch")
        return self


class TemporalProjectionCommitCertificate(BaseModel):
    publication_kind: Literal["projection_commit"] = "projection_commit"
    repository_id: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    temporal_policy_fingerprint: str
    predecessor_generation_digest: str
    output_generation_digest: str
    graph_revision: str = Field(min_length=1)
    event_batch_sequence: int = Field(ge=0)
    event_batch_digest: str
    complete_read_set_digest: str
    semantic_conflict_authority_input_digest: str
    added_projection_digests: tuple[str, ...]
    removed_projection_digests: tuple[str, ...]
    writer_epoch: int = Field(ge=1)
    certificate_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digests = field_validator(
        "temporal_policy_fingerprint",
        "predecessor_generation_digest",
        "output_generation_digest",
        "event_batch_digest",
        "complete_read_set_digest",
        "semantic_conflict_authority_input_digest",
        "added_projection_digests",
        "removed_projection_digests",
        "certificate_digest",
    )(_strict_digest)

    @model_validator(mode="after")
    def validate_certificate(self) -> TemporalProjectionCommitCertificate:
        for values in (self.added_projection_digests, self.removed_projection_digests):
            if values != tuple(sorted(set(values))):
                raise ValueError("temporal certificate membership delta is not canonical")
        if set(self.added_projection_digests) & set(self.removed_projection_digests):
            raise ValueError("temporal certificate adds and removes one projection")
        body = self.model_dump(mode="python", exclude={"certificate_digest"})
        if self.certificate_digest != _digest(_TEMPORAL_CERTIFICATE_DOMAIN, body):
            raise ValueError("temporal projection certificate digest mismatch")
        return self


class TrustProjectionCommitCertificate(BaseModel):
    publication_kind: Literal["projection_commit"] = "projection_commit"
    repository_id: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    trust_policy_fingerprint: str
    predecessor_generation_digest: str
    output_generation_digest: str
    graph_revision: str = Field(min_length=1)
    event_batch_sequence: int = Field(ge=0)
    event_batch_digest: str
    complete_read_set_digest: str
    semantic_conflict_authority_input_digest: str
    added_projection_digests: tuple[str, ...]
    removed_projection_digests: tuple[str, ...]
    added_decay_command_digests: tuple[str, ...]
    removed_decay_command_digests: tuple[str, ...]
    arbitration_as_of: datetime
    writer_epoch: int = Field(ge=1)
    certificate_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digests = field_validator(
        "trust_policy_fingerprint",
        "predecessor_generation_digest",
        "output_generation_digest",
        "event_batch_digest",
        "complete_read_set_digest",
        "semantic_conflict_authority_input_digest",
        "added_projection_digests",
        "removed_projection_digests",
        "added_decay_command_digests",
        "removed_decay_command_digests",
        "certificate_digest",
    )(_strict_digest)
    _validate_time = field_validator("arbitration_as_of")(_utc)

    @model_validator(mode="after")
    def validate_certificate(self) -> TrustProjectionCommitCertificate:
        for values in (
            self.added_projection_digests,
            self.removed_projection_digests,
            self.added_decay_command_digests,
            self.removed_decay_command_digests,
        ):
            if values != tuple(sorted(set(values))):
                raise ValueError("trust certificate membership delta is not canonical")
        if set(self.added_projection_digests) & set(self.removed_projection_digests):
            raise ValueError("trust certificate adds and removes one projection")
        if set(self.added_decay_command_digests) & set(self.removed_decay_command_digests):
            raise ValueError("trust certificate adds and removes one decay command")
        body = self.model_dump(mode="python", exclude={"certificate_digest"})
        if self.certificate_digest != _digest(_TRUST_CERTIFICATE_DOMAIN, body):
            raise ValueError("trust projection certificate digest mismatch")
        return self


class TemporalPolicyMigrationCertificate(BaseModel):
    migration_kind: Literal["temporal"] = "temporal"
    publication_kind: Literal["migration_cutover"] = "migration_cutover"
    repository_id: str = Field(min_length=1)
    migration_plan_digest: str
    active_policy_fingerprint_before: str
    pending_policy_fingerprint: str
    active_generation_digest_before: str
    output_generation_digest: str
    server_derived_base_slot_plan_digests: tuple[str, ...]
    server_derived_catch_up_entry_digests: tuple[str, ...]
    final_catch_up_watermark: str = Field(min_length=1)
    complete_read_set_digest: str
    semantic_conflict_authority_input_digest: str
    cutover_digest: str
    writer_epoch_before: int = Field(ge=1)
    activated_writer_epoch: int = Field(ge=1)
    certificate_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digests = field_validator(
        "migration_plan_digest",
        "active_policy_fingerprint_before",
        "pending_policy_fingerprint",
        "active_generation_digest_before",
        "output_generation_digest",
        "server_derived_base_slot_plan_digests",
        "server_derived_catch_up_entry_digests",
        "complete_read_set_digest",
        "semantic_conflict_authority_input_digest",
        "cutover_digest",
        "certificate_digest",
    )(_strict_digest)

    @model_validator(mode="after")
    def validate_certificate(self) -> TemporalPolicyMigrationCertificate:
        for values in (
            self.server_derived_base_slot_plan_digests,
            self.server_derived_catch_up_entry_digests,
        ):
            if values != tuple(sorted(set(values))):
                raise ValueError("temporal migration membership is not canonical")
        if self.activated_writer_epoch <= self.writer_epoch_before:
            raise ValueError("temporal migration writer epoch must advance")
        body = self.model_dump(mode="python", exclude={"certificate_digest"})
        if self.certificate_digest != _digest(_TEMPORAL_CERTIFICATE_DOMAIN, body):
            raise ValueError("temporal migration certificate digest mismatch")
        return self


class TrustPolicyMigrationCertificate(BaseModel):
    migration_kind: Literal["trust"] = "trust"
    publication_kind: Literal["migration_cutover"] = "migration_cutover"
    repository_id: str = Field(min_length=1)
    migration_plan_digest: str
    active_policy_fingerprint_before: str
    pending_policy_fingerprint: str
    active_generation_digest_before: str
    output_generation_digest: str
    server_derived_base_slot_plan_digests: tuple[str, ...]
    server_derived_catch_up_entry_digests: tuple[str, ...]
    final_catch_up_watermark: str = Field(min_length=1)
    complete_read_set_digest: str
    semantic_conflict_authority_input_digest: str
    cutover_digest: str
    writer_epoch_before: int = Field(ge=1)
    activated_writer_epoch: int = Field(ge=1)
    certificate_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digests = field_validator(
        "migration_plan_digest",
        "active_policy_fingerprint_before",
        "pending_policy_fingerprint",
        "active_generation_digest_before",
        "output_generation_digest",
        "server_derived_base_slot_plan_digests",
        "server_derived_catch_up_entry_digests",
        "complete_read_set_digest",
        "semantic_conflict_authority_input_digest",
        "cutover_digest",
        "certificate_digest",
    )(_strict_digest)

    @model_validator(mode="after")
    def validate_certificate(self) -> TrustPolicyMigrationCertificate:
        for values in (
            self.server_derived_base_slot_plan_digests,
            self.server_derived_catch_up_entry_digests,
        ):
            if values != tuple(sorted(set(values))):
                raise ValueError("trust migration membership is not canonical")
        if self.activated_writer_epoch <= self.writer_epoch_before:
            raise ValueError("trust migration writer epoch must advance")
        body = self.model_dump(mode="python", exclude={"certificate_digest"})
        if self.certificate_digest != _digest(_TRUST_CERTIFICATE_DOMAIN, body):
            raise ValueError("trust migration certificate digest mismatch")
        return self


class ActiveTemporalProjectionPointer(BaseModel):
    repository_id: str = Field(min_length=1)
    policy_fingerprint: str
    generation_digest: str
    publication_kind: ProjectionPublicationKind
    publication_certificate_digest: str
    writer_epoch: int = Field(ge=1)
    pointer_revision: int = Field(ge=1)
    published_at: datetime
    publication_sequence: int = Field(ge=1)
    predecessor_pointer_digest: str | None
    pointer_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digests = field_validator(
        "policy_fingerprint",
        "generation_digest",
        "publication_certificate_digest",
        "predecessor_pointer_digest",
        "pointer_digest",
    )(_strict_digest)
    _validate_time = field_validator("published_at")(_utc)

    @model_validator(mode="after")
    def validate_pointer(self) -> ActiveTemporalProjectionPointer:
        body = self.model_dump(mode="python", exclude={"pointer_digest"})
        if self.pointer_digest != _digest(_TEMPORAL_POINTER_DOMAIN, body):
            raise ValueError("temporal projection pointer digest mismatch")
        return self


class ActiveTrustProjectionPointer(BaseModel):
    repository_id: str = Field(min_length=1)
    policy_fingerprint: str
    generation_digest: str
    publication_kind: ProjectionPublicationKind
    publication_certificate_digest: str
    writer_epoch: int = Field(ge=1)
    pointer_revision: int = Field(ge=1)
    published_at: datetime
    publication_sequence: int = Field(ge=1)
    predecessor_pointer_digest: str | None
    pointer_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digests = field_validator(
        "policy_fingerprint",
        "generation_digest",
        "publication_certificate_digest",
        "predecessor_pointer_digest",
        "pointer_digest",
    )(_strict_digest)
    _validate_time = field_validator("published_at")(_utc)

    @model_validator(mode="after")
    def validate_pointer(self) -> ActiveTrustProjectionPointer:
        body = self.model_dump(mode="python", exclude={"pointer_digest"})
        if self.pointer_digest != _digest(_TRUST_POINTER_DOMAIN, body):
            raise ValueError("trust projection pointer digest mismatch")
        return self


class TemporalProjectionHistoryEntry(BaseModel):
    projection_kind: Literal["temporal"] = "temporal"
    repository_id: str = Field(min_length=1)
    pointer: ActiveTemporalProjectionPointer
    entry_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digest = field_validator("entry_digest")(_strict_digest)

    @model_validator(mode="after")
    def validate_entry(self) -> TemporalProjectionHistoryEntry:
        if self.pointer.repository_id != self.repository_id:
            raise ValueError("temporal history entry is cross-repository")
        body = self.model_dump(mode="python", exclude={"entry_digest"})
        if self.entry_digest != _digest(_HISTORY_ENTRY_DOMAIN, body):
            raise ValueError("temporal history entry digest mismatch")
        return self


class TrustProjectionHistoryEntry(BaseModel):
    projection_kind: Literal["trust"] = "trust"
    repository_id: str = Field(min_length=1)
    pointer: ActiveTrustProjectionPointer
    entry_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digest = field_validator("entry_digest")(_strict_digest)

    @model_validator(mode="after")
    def validate_entry(self) -> TrustProjectionHistoryEntry:
        if self.pointer.repository_id != self.repository_id:
            raise ValueError("trust history entry is cross-repository")
        body = self.model_dump(mode="python", exclude={"entry_digest"})
        if self.entry_digest != _digest(_HISTORY_ENTRY_DOMAIN, body):
            raise ValueError("trust history entry digest mismatch")
        return self


class TemporalProjectionView(BaseModel):
    pointer: ActiveTemporalProjectionPointer
    generation: TemporalProjectionGeneration
    projections: tuple[TemporalProjectionRecord, ...]

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @property
    def contested(self) -> tuple[TemporalProjectionRecord, ...]:
        return tuple(item for item in self.projections if item.outcome == "contested")


class TrustProjectionView(BaseModel):
    pointer: ActiveTrustProjectionPointer
    generation: TrustProjectionGeneration
    projections: tuple[TrustProjectionRecord, ...]

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @property
    def contested(self) -> tuple[TrustProjectionRecord, ...]:
        return tuple(item for item in self.projections if item.outcome == "contested")


def projection_contract_digest(
    contract: Literal[
        "temporal_generation",
        "trust_generation",
        "temporal_certificate",
        "trust_certificate",
        "temporal_pointer",
        "trust_pointer",
        "history_entry",
        "history_prefix",
        "projection_commit_plan",
        "projection_generation_id",
        "projection_record_id",
        "projection_genesis",
        "trust_decay_schedule",
        "trust_decay_projection_id",
    ],
    value: object,
) -> str:
    """Derive one domain-separated projection authority digest."""

    domains = {
        "temporal_generation": _TEMPORAL_GENERATION_DOMAIN,
        "trust_generation": _TRUST_GENERATION_DOMAIN,
        "temporal_certificate": _TEMPORAL_CERTIFICATE_DOMAIN,
        "trust_certificate": _TRUST_CERTIFICATE_DOMAIN,
        "temporal_pointer": _TEMPORAL_POINTER_DOMAIN,
        "trust_pointer": _TRUST_POINTER_DOMAIN,
        "history_entry": _HISTORY_ENTRY_DOMAIN,
        "history_prefix": b"memorii.projection-history-prefix.v1\0",
        "projection_commit_plan": b"memorii.projection-commit-plan.v1\0",
        "projection_generation_id": b"memorii.projection-generation-id.v1\0",
        "projection_record_id": b"memorii.projection-record-id.v1\0",
        "projection_genesis": b"memorii.projection-genesis.v1\0",
        "trust_decay_schedule": b"memorii.trust-decay-schedule.v1\0",
        "trust_decay_projection_id": b"memorii.trust-decay-projection-id.v1\0",
    }
    return _digest(domains[contract], value)


__all__ = [
    "AcceptedIdentityOperation",
    "AcceptedClaimIdentity",
    "ActiveTemporalProjectionPointer",
    "ActiveTrustProjectionPointer",
    "ImmutableAssertionEntityRef",
    "CompiledIdentityLineageTransition",
    "IdentityLineageOperation",
    "LineageEntityIdentity",
    "LineageEvidenceReference",
    "GroundedLineageReferenceAssignment",
    "LineageReferenceDisposition",
    "LineageReverseReference",
    "PredicateStateRule",
    "ProjectionEvidenceRecord",
    "ProjectionHistoryReplayBinding",
    "ProjectionKind",
    "ProjectionRecordKind",
    "SemanticAssertionKey",
    "SemanticClaimSlotKey",
    "SemanticClaimValueKey",
    "TemporalProjectionCommitCertificate",
    "TemporalProjectionGeneration",
    "TemporalProjectionHistoryEntry",
    "TemporalPolicyMigrationCertificate",
    "TemporalProjectionRecord",
    "TemporalProjectionView",
    "TrustProjectionCommitCertificate",
    "TrustProjectionGeneration",
    "TrustProjectionHistoryEntry",
    "TrustPolicyMigrationCertificate",
    "TrustProjectionRecord",
    "TrustProjectionView",
    "projection_contract_digest",
]
