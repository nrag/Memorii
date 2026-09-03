"""Closed canonical graph-record, snapshot, read/write-set, and reservation contracts."""

from __future__ import annotations

from datetime import datetime, timedelta
from functools import lru_cache
from hashlib import sha256
from typing import TYPE_CHECKING, Annotated, Literal, TypeAlias, TypeGuard, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_serializer,
    field_validator,
    model_validator,
)

from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.memory_evolution.semantic_state import (
    AcceptedIdentityOperation,
    LineageEvidenceReference,
)
from memorii.core.memory_evolution.time_contracts import TimeInterval


def _arena_registry():
    # Lazy: importing the arena package at module level re-enters this
    # module through the semantic-ingestion package initializer.
    from memorii.core.semantic_ingestion.canonical_evidence_arena import (
        certified_instance,
        deeply_immutable_type,
        record_certified_instance,
    )

    return certified_instance, deeply_immutable_type, record_certified_instance

GraphRecordKind = Literal[
    "entity_revision", "alias_revision", "type_evidence", "claim_assertion",
    "claim_projection", "relation_revision", "action_revision", "citation",
    "provenance", "temporal_transition", "identity_lineage", "reference_disposition",
]


class SourceAuthority(BaseModel):
    authority_class: str = Field(min_length=1)
    authenticated_provenance_class: str = Field(min_length=1)
    governing_principal_id: str | None = None
    policy_revision: str = Field(min_length=1)
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class GroundedMentionRef(BaseModel):
    kind: Literal["grounded_mention"] = "grounded_mention"
    source_id: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    cluster_id: str = Field(min_length=1)
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_span(self) -> GroundedMentionRef:
        if self.end <= self.start:
            raise ValueError("grounded_mention_span_invalid")
        return self


class CanonicalEntityRevisionRef(BaseModel):
    kind: Literal["canonical_entity_revision"] = "canonical_entity_revision"
    entity_revision_id: str = Field(min_length=1)
    logical_entity_id: str = Field(min_length=1)
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


TypeEvidenceEntityReference = Annotated[
    GroundedMentionRef | CanonicalEntityRevisionRef,
    Field(discriminator="kind"),
]


def _canonical(value: object) -> object:
    if isinstance(value, BaseModel):
        return _canonical(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_canonical(item) for item in value)
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def graph_digest(domain: bytes, value: object) -> str:
    return sha256(domain + encode_typed_value(_canonical(value))).hexdigest()


class _GraphRecord(BaseModel):
    operation_id: str = Field(min_length=1)
    record_version: int = Field(default=1, ge=1)
    codec_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_digest(self) -> _GraphRecord:
        body = self.model_dump(mode="python", exclude={"record_digest"})
        if self.record_digest != graph_digest(b"memorii.canonical-graph-record.v1\0", body):
            raise ValueError("canonical_graph_record_digest_mismatch")
        return self

    @classmethod
    def create(cls, **values: object):
        body = {"record_kind": cls.model_fields["record_kind"].default, **values}
        validated = cls.model_validate(
            body
            | {"record_digest": graph_digest(b"memorii.canonical-graph-record.v1\0", body)}
        )
        _arena_registry()[2](validated)
        return validated


class EntityRevision(_GraphRecord):
    record_kind: Literal["entity_revision"] = "entity_revision"
    entity_revision_id: str = Field(min_length=1)
    logical_entity_id: str = Field(min_length=1)
    lifecycle: Literal["active", "retired"] = "active"
    source_evidence: tuple[LineageEvidenceReference, ...]


class AliasRevision(_GraphRecord):
    record_kind: Literal["alias_revision"] = "alias_revision"
    alias_revision_id: str = Field(min_length=1)
    entity_revision_id: str = Field(min_length=1)
    logical_entity_id: str = Field(min_length=1)
    alias_namespace: str = Field(min_length=1)
    normalized_alias_key: str = Field(min_length=1)
    source_evidence: tuple[LineageEvidenceReference, ...]

    @model_validator(mode="after")
    def validate_grounding(self) -> AliasRevision:
        if not self.source_evidence:
            raise ValueError("alias_revision_source_grounding_missing")
        return self


class TypeEvidence(_GraphRecord):
    record_kind: Literal["type_evidence"] = "type_evidence"
    evidence_id: str = Field(min_length=1)
    entity_reference: TypeEvidenceEntityReference
    asserted_type: str = Field(min_length=1)
    origin: Literal[
        "certified_source_assertion", "authenticated_external_registry",
        "verified_graph_type_assertion",
    ]
    source_evidence: tuple[LineageEvidenceReference, ...] = ()
    registry_record_id: str | None = None
    authority: SourceAuthority
    valid_interval: TimeInterval | None = None
    recorded_at: datetime
    proof_ancestry_ids: tuple[str, ...] = ()
    proof_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_type_evidence(self) -> TypeEvidence:
        if self.recorded_at.tzinfo is None or self.recorded_at.utcoffset() is None:
            raise ValueError("type_evidence_recorded_at_invalid")
        if self.origin == "authenticated_external_registry":
            if self.registry_record_id is None:
                raise ValueError("type_evidence_registry_record_missing")
        elif self.registry_record_id is not None:
            raise ValueError("type_evidence_registry_record_forbidden")
        if self.origin == "certified_source_assertion" and not self.source_evidence:
            raise ValueError("type_evidence_source_proof_missing")
        return self


class ClaimProjection(_GraphRecord):
    record_kind: Literal["claim_projection"] = "claim_projection"
    claim_projection_id: str = Field(min_length=1)
    claim_assertion_id: str = Field(min_length=1)
    subject_entity_revision_id: str = Field(min_length=1)
    subject_logical_entity_id: str = Field(min_length=1)
    object_entity_revision_id: str | None = None
    object_logical_entity_id: str | None = None


class RelationRevision(_GraphRecord):
    record_kind: Literal["relation_revision"] = "relation_revision"
    relation_revision_id: str = Field(min_length=1)
    subject_entity_revision_id: str = Field(min_length=1)
    subject_logical_entity_id: str = Field(min_length=1)
    object_entity_revision_id: str = Field(min_length=1)
    object_logical_entity_id: str = Field(min_length=1)
    predicate_id: str = Field(min_length=1)


class CitationRecord(_GraphRecord):
    record_kind: Literal["citation"] = "citation"
    citation_id: str = Field(min_length=1)
    cited_record_id: str = Field(min_length=1)
    entity_revision_id: str | None = None
    logical_entity_id: str | None = None


class ProvenanceRecord(_GraphRecord):
    record_kind: Literal["provenance"] = "provenance"
    provenance_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    entity_revision_id: str | None = None
    logical_entity_id: str | None = None


class ReferenceDispositionRecord(_GraphRecord):
    record_kind: Literal["reference_disposition"] = "reference_disposition"
    reference_disposition_id: str = Field(min_length=1)
    target_record_kind: GraphRecordKind
    target_record_id: str = Field(min_length=1)
    target_reference_path: str = Field(min_length=1)
    predecessor_entity_revision_id: str = Field(min_length=1)
    predecessor_logical_entity_id: str = Field(min_length=1)
    successor_entity_revision_ids: tuple[str, ...] = ()
    successor_logical_entity_ids: tuple[str, ...] = ()
    disposition: Literal[
        "preserve_historical", "redirect_current", "migrate_current",
        "share_by_explicit_evidence", "unresolved",
    ]
    basis: Literal[
        "source_assignment", "operation_defined_rekey_redirect",
        "operation_defined_merge_redirect",
        "operation_defined_history_preservation", "insufficient_evidence",
    ]
    source_evidence: tuple[LineageEvidenceReference, ...] = ()

    @model_validator(mode="after")
    def validate_disposition(self) -> ReferenceDispositionRecord:
        if self.disposition == "unresolved" and (
            self.successor_entity_revision_ids
            or self.successor_logical_entity_ids
            or self.basis != "insufficient_evidence"
        ):
            raise ValueError("reference_disposition_unresolved_shape_invalid")
        if self.disposition != "unresolved" and self.basis == "insufficient_evidence":
            raise ValueError("reference_disposition_basis_invalid")
        return self


NonOwningGraphRecord = Annotated[
    EntityRevision | AliasRevision | TypeEvidence | ClaimProjection | RelationRevision
    | CitationRecord | ProvenanceRecord | ReferenceDispositionRecord,
    Field(discriminator="record_kind"),
]


def graph_record_id(record: object) -> str:
    names = {
        "entity_revision": "entity_revision_id", "alias_revision": "alias_revision_id",
        "type_evidence": "evidence_id", "claim_assertion": "claim_assertion_id",
        "claim_projection": "claim_projection_id", "relation_revision": "relation_revision_id",
        "action_revision": "action_revision_id", "citation": "citation_id",
        "provenance": "provenance_id", "temporal_transition": "transition_id",
        "identity_lineage": "identity_lineage_id", "reference_disposition": "reference_disposition_id",
    }
    kind = getattr(record, "record_kind", None)
    if not isinstance(kind, str):
        raise ValueError("canonical_graph_record_identity_invalid")
    field = names.get(kind)
    value = getattr(record, field, None) if field is not None else None
    if not isinstance(value, str) or not value:
        raise ValueError("canonical_graph_record_identity_invalid")
    return value


class CanonicalGraphRecordCodecEntry(BaseModel):
    record_kind: GraphRecordKind
    payload_schema_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    codec_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_projection_schema_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_projection_codec_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_owned_fields: tuple[
        tuple[
            str,
            Literal["graph_revision_before", "graph_revision_after", "committed_at"],
        ],
        ...,
    ] = ()

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CanonicalGraphRecordCodecManifest(BaseModel):
    entries: tuple[CanonicalGraphRecordCodecEntry, ...]
    manifest_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_manifest(self) -> CanonicalGraphRecordCodecManifest:
        expected = tuple(sorted(GraphRecordKind.__args__))
        if tuple(item.record_kind for item in self.entries) != expected:
            raise ValueError("canonical_graph_codec_manifest_not_total")
        body = tuple(item.model_dump(mode="python") for item in self.entries)
        if self.manifest_fingerprint != graph_digest(b"memorii.graph-codec-manifest.v1\0", body):
            raise ValueError("canonical_graph_codec_manifest_digest_mismatch")
        return self


@lru_cache(maxsize=1)
def canonical_graph_codec_manifest() -> CanonicalGraphRecordCodecManifest:
    from memorii.core.semantic_ingestion.contracts import (
        ActionRevision,
        ClaimAssertion,
        IdentityLineageRecord,
        TemporalTransitionRecord,
    )

    models: dict[GraphRecordKind, type[BaseModel]] = {
        "entity_revision": EntityRevision, "alias_revision": AliasRevision,
        "type_evidence": TypeEvidence, "claim_assertion": ClaimAssertion,
        "claim_projection": ClaimProjection, "relation_revision": RelationRevision,
        "action_revision": ActionRevision, "citation": CitationRecord,
        "provenance": ProvenanceRecord, "temporal_transition": TemporalTransitionRecord,
        "identity_lineage": IdentityLineageRecord,
        "reference_disposition": ReferenceDispositionRecord,
    }
    entries = tuple(
        CanonicalGraphRecordCodecEntry(
            record_kind=kind,
            payload_schema_fingerprint=graph_digest(b"memorii.graph-payload-schema.v1\0", models[kind].model_json_schema()),
            codec_fingerprint=graph_digest(b"memorii.graph-payload-codec.v1\0", kind),
            planning_projection_schema_fingerprint=graph_digest(
                b"memorii.graph-planning-projection-schema.v1\0",
                (kind, models[kind].model_json_schema()),
            ),
            planning_projection_codec_fingerprint=graph_digest(
                b"memorii.graph-planning-projection-codec.v1\0", kind
            ),
            transaction_owned_fields=cast(
                tuple[
                    tuple[
                        str,
                        Literal[
                            "graph_revision_before",
                            "graph_revision_after",
                            "committed_at",
                        ],
                    ],
                    ...,
                ],
                {
                    "identity_lineage": (
                        ("transition.recorded_at", "committed_at"),
                    ),
                    "temporal_transition": (
                        ("system_interval", "committed_at"),
                    ),
                }.get(kind, ()),
            ),
        )
        for kind in sorted(models)
    )
    return CanonicalGraphRecordCodecManifest(
        entries=entries,
        manifest_fingerprint=graph_digest(
            b"memorii.graph-codec-manifest.v1\0",
            tuple(item.model_dump(mode="python") for item in entries),
        ),
    )


class SnapshotGraphRecord(BaseModel):
    record_id: str = Field(min_length=1)
    record_version: int = Field(ge=1)
    payload: BaseModel
    codec_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    persistence_schema_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @field_validator("payload", mode="before")
    @classmethod
    def validate_payload(cls, value: object) -> BaseModel:
        _certified, _immutable, _record_certified = _arena_registry()
        if (
            _certified(value)
            and _immutable(type(value))
            and graph_record_union_member(value)
        ):
            return value  # type: ignore[return-value]
        raw = value.model_dump(mode="python") if isinstance(value, BaseModel) else value
        payload = canonical_graph_record_adapter().validate_python(raw)
        _arena_registry()[2](payload)
        return payload

    @field_serializer("payload")
    def serialize_payload(self, value: BaseModel) -> object:
        return value.model_dump(mode="python")

    @model_validator(mode="after")
    def validate_record(self) -> SnapshotGraphRecord:
        _certified, _immutable, _record_certified = _arena_registry()
        if (
            _certified(self.payload)
            and _immutable(type(self.payload))
            and graph_record_union_member(self.payload)
        ):
            payload = self.payload
        else:
            payload = canonical_graph_record_adapter().validate_python(
                self.payload.model_dump(mode="python")
            )
            _record_certified(payload)
        manifest = {item.record_kind: item for item in canonical_graph_codec_manifest().entries}
        codec = manifest[payload.record_kind]
        if (
            self.record_id != graph_record_id(payload)
            or self.record_version != payload.record_version
            or self.record_digest != payload.record_digest
            or self.codec_fingerprint != codec.codec_fingerprint
            or self.persistence_schema_fingerprint != codec.payload_schema_fingerprint
        ):
            raise ValueError("snapshot_graph_record_binding_mismatch")
        object.__setattr__(self, "payload", payload)
        return self

    @property
    def payload_record_kind(self) -> GraphRecordKind:
        certified_kind = certified_graph_record_kind(self.payload)
        kind: object
        if certified_kind is not None:
            kind = certified_kind
        else:
            kind = self.payload.model_dump(mode="python").get("record_kind")
        if kind not in GraphRecordKind.__args__:
            raise ValueError("snapshot_graph_record_kind_invalid")
        return cast(GraphRecordKind, kind)


@lru_cache(maxsize=1)
def canonical_graph_record_adapter() -> TypeAdapter:
    from memorii.core.semantic_ingestion.contracts import (
        ActionRevision,
        ClaimAssertion,
        IdentityLineageRecord,
        TemporalTransitionRecord,
    )
    union = Annotated[
        EntityRevision | AliasRevision | TypeEvidence | ClaimAssertion | ClaimProjection
        | RelationRevision | ActionRevision | CitationRecord | ProvenanceRecord
        | TemporalTransitionRecord | IdentityLineageRecord | ReferenceDispositionRecord,
        Field(discriminator="record_kind"),
    ]
    return TypeAdapter(union)


def validated_graph_record(values: object) -> CanonicalGraphRecord:
    """Construct one graph-record union member and certify it when scoped.

    Complete validation always runs through the discriminated-union
    adapter; inside an enabled operation the constructed instance is also
    recorded in the validated-instance registry so downstream
    revalidation sites can reuse it under the sharing rule.
    """

    payload = canonical_graph_record_adapter().validate_python(values)
    _arena_registry()[2](payload)
    return payload


def graph_record_union_member(value: object) -> TypeGuard[CanonicalGraphRecord]:
    from memorii.core.semantic_ingestion.contracts import (
        ActionRevision,
        ClaimAssertion,
        IdentityLineageRecord,
        TemporalTransitionRecord,
    )

    return isinstance(
        value,
        (
            EntityRevision,
            AliasRevision,
            TypeEvidence,
            ClaimAssertion,
            ClaimProjection,
            RelationRevision,
            ActionRevision,
            CitationRecord,
            ProvenanceRecord,
            TemporalTransitionRecord,
            IdentityLineageRecord,
            ReferenceDispositionRecord,
        ),
    )


def certified_graph_record_kind(record: object) -> str | None:
    """Direct ``record_kind`` read for certified union members only."""

    if _arena_registry()[0](record) and graph_record_union_member(record):
        return record.record_kind  # type: ignore[return-value]
    return None


class GraphPartitionVersion(BaseModel):
    partition_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class GraphReadSet(BaseModel):
    record_keys: tuple[str, ...]
    partition_versions: tuple[GraphPartitionVersion, ...]
    manifest_fingerprints: tuple[str, ...]
    read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_read_set(self) -> GraphReadSet:
        if (
            self.record_keys != tuple(sorted(set(self.record_keys)))
            or self.partition_versions
            != tuple(sorted(self.partition_versions, key=lambda item: item.partition_id))
            or len({item.partition_id for item in self.partition_versions})
            != len(self.partition_versions)
            or self.manifest_fingerprints != tuple(sorted(set(self.manifest_fingerprints)))
        ):
            raise ValueError("graph_read_set_not_canonical")
        body = self.model_dump(mode="python", exclude={"read_set_digest"})
        if self.read_set_digest != graph_digest(b"memorii.graph-read-set.v1\0", body):
            raise ValueError("graph_read_set_digest_mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> GraphReadSet:
        return cls.model_validate(
            values | {"read_set_digest": graph_digest(b"memorii.graph-read-set.v1\0", values)}
        )


class GraphReadSetExtension(BaseModel):
    snapshot_token: str = Field(min_length=1)
    graph_revision: str = Field(min_length=1)
    segment_governance_binding_digests: tuple[str, ...] = ()
    operation_fence_id: str = Field(min_length=1)
    issuer_repository_id: str = Field(min_length=1)
    issuer_contract_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    dependency_kind: Literal[
        "identity_allocation", "claim_state", "correction_target", "type_evidence",
        "action_state", "reference_closure", "policy", "capability_status",
    ]
    record_keys: tuple[str, ...]
    partition_versions: tuple[GraphPartitionVersion, ...] = ()
    manifest_fingerprints: tuple[str, ...]
    extension_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_extension(self) -> GraphReadSetExtension:
        for values in (self.segment_governance_binding_digests, self.record_keys, self.manifest_fingerprints):
            if values != tuple(sorted(set(values))):
                raise ValueError("graph_read_set_extension_not_canonical")
        body = self.model_dump(mode="python", exclude={"extension_digest"})
        if self.extension_digest != graph_digest(b"memorii.graph-read-set-extension.v1\0", body):
            raise ValueError("graph_read_set_extension_digest_mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> GraphReadSetExtension:
        return cls.model_validate(values | {"extension_digest": graph_digest(b"memorii.graph-read-set-extension.v1\0", values)})


class GraphWriteIntent(BaseModel):
    record_key: str = Field(min_length=1)
    expected_before_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PlannedEntityIdentity(BaseModel):
    allocation_key: str = Field(min_length=1)
    entity_revision_id: str = Field(min_length=1)
    logical_entity_id: str = Field(min_length=1)
    allocation_namespace_id: str = Field(min_length=1)
    allocation_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PlannedIdentityReservation(BaseModel):
    planned_identity: PlannedEntityIdentity
    collision_read_set_extension: GraphReadSetExtension
    expected_absent_write_intents: tuple[GraphWriteIntent, ...]
    logical_entity_reservation_required: bool = True
    reservation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_reservation(self) -> PlannedIdentityReservation:
        keys = (f"entity_revision:{self.planned_identity.entity_revision_id}",)
        if self.logical_entity_reservation_required:
            keys = tuple(
                sorted(
                    (*keys, f"logical_entity:{self.planned_identity.logical_entity_id}")
                )
            )
        intents = tuple(item.record_key for item in self.expected_absent_write_intents)
        if (
            self.collision_read_set_extension.dependency_kind != "identity_allocation"
            or self.collision_read_set_extension.record_keys != keys
            or intents != keys
            or any(item.expected_before_digest is not None for item in self.expected_absent_write_intents)
        ):
            raise ValueError("planned_identity_reservation_collision_contract_invalid")
        body = self.model_dump(mode="python", exclude={"reservation_digest"})
        if self.reservation_digest != graph_digest(b"memorii.planned-identity-reservation.v1\0", body):
            raise ValueError("planned_identity_reservation_digest_mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> PlannedIdentityReservation:
        body = {"logical_entity_reservation_required": True, **values}
        return cls.model_validate(
            body
            | {
                "reservation_digest": graph_digest(
                    b"memorii.planned-identity-reservation.v1\0", body
                )
            }
        )


class SourceGroundedAliasPayload(BaseModel):
    alias_namespace: str = Field(min_length=1)
    normalized_alias_key: str = Field(min_length=1)
    entity_revision_id: str = Field(min_length=1)
    logical_entity_id: str = Field(min_length=1)
    source_evidence: tuple[LineageEvidenceReference, ...]
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_alias(self) -> SourceGroundedAliasPayload:
        if not self.source_evidence:
            raise ValueError("source_grounded_alias_evidence_missing")
        body = self.model_dump(mode="python", exclude={"payload_digest"})
        if self.payload_digest != graph_digest(b"memorii.source-grounded-alias.v1\0", body):
            raise ValueError("source_grounded_alias_digest_mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> SourceGroundedAliasPayload:
        return cls.model_validate(values | {"payload_digest": graph_digest(b"memorii.source-grounded-alias.v1\0", values)})


class TrustedAcceptedIdentityOperationDecision(BaseModel):
    """Host-authenticated identity decision consumed by the graph planning owner."""

    operation: AcceptedIdentityOperation
    alias_payload: SourceGroundedAliasPayload | None = None
    sealed_operation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_analysis_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_fence_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_decision(self) -> TrustedAcceptedIdentityOperationDecision:
        if (self.operation.operation == "alias") != (self.alias_payload is not None):
            raise ValueError("trusted_identity_decision_alias_shape_invalid")
        if self.alias_payload is not None and (
            self.alias_payload.source_evidence != self.operation.source_evidence
        ):
            raise ValueError("trusted_identity_decision_alias_evidence_mismatch")
        body = self.model_dump(mode="python", exclude={"decision_digest"})
        if self.decision_digest != graph_digest(
            b"memorii.trusted-identity-operation-decision.v1\0", body
        ):
            raise ValueError("trusted_identity_decision_digest_mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> TrustedAcceptedIdentityOperationDecision:
        return cls.model_validate(
            values
            | {
                "decision_digest": graph_digest(
                    b"memorii.trusted-identity-operation-decision.v1\0", values
                )
            }
        )


class VerifiedIdentityDecisionAuthority(BaseModel):
    decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_operation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_analysis_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_fence_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_record_id: str = Field(min_length=1)
    authority_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    verifier_id: str = Field(min_length=1)
    verification_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_verification(self) -> VerifiedIdentityDecisionAuthority:
        body = self.model_dump(mode="python", exclude={"verification_digest"})
        if self.verification_digest != graph_digest(
            b"memorii.verified-identity-decision-authority.v1\0", body
        ):
            raise ValueError("verified_identity_decision_authority_digest_mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> VerifiedIdentityDecisionAuthority:
        return cls.model_validate(
            values
            | {
                "verification_digest": graph_digest(
                    b"memorii.verified-identity-decision-authority.v1\0", values
                )
            }
        )


class AcceptedIdentityOperationArtifact(BaseModel):
    operation: AcceptedIdentityOperation
    operation_fence_id: str = Field(min_length=1)
    sealed_operation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_analysis_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_evidence_digests: tuple[str, ...]
    semantic_authorization_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    verified_decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_record_id: str = Field(min_length=1)
    authority_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_verification_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    successor_reservations: tuple[PlannedIdentityReservation, ...] = ()
    alias_payload: SourceGroundedAliasPayload | None = None
    artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_artifact(self) -> AcceptedIdentityOperationArtifact:
        expected_evidence = tuple(sorted(item.evidence_digest for item in self.operation.source_evidence))
        if self.source_evidence_digests != expected_evidence:
            raise ValueError("accepted_identity_artifact_evidence_mismatch")
        reserved = tuple(
            sorted(
                (
                    item.planned_identity.entity_revision_id,
                    item.planned_identity.logical_entity_id,
                )
                for item in self.successor_reservations
            )
        )
        successors = tuple(
            sorted((item.entity_revision_id, item.logical_entity_id) for item in self.operation.successors)
        )
        if self.operation.operation == "alias":
            if self.successor_reservations or self.alias_payload is None:
                raise ValueError("accepted_alias_artifact_shape_invalid")
        elif reserved != successors or self.alias_payload is not None:
            raise ValueError("accepted_identity_artifact_reservations_incomplete")
        if self.authority_digest != self.authority_verification_digest:
            raise ValueError("accepted_identity_artifact_authority_binding_invalid")
        body = self.model_dump(mode="python", exclude={"artifact_digest"})
        if self.artifact_digest != graph_digest(b"memorii.accepted-identity-artifact.v1\0", body):
            raise ValueError("accepted_identity_artifact_digest_mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> AcceptedIdentityOperationArtifact:
        return cls.model_validate(values | {"artifact_digest": graph_digest(b"memorii.accepted-identity-artifact.v1\0", values)})


class GraphStateSnapshot(BaseModel):
    snapshot_token: str = Field(min_length=1)
    graph_revision: str = Field(min_length=1)
    system_as_of: datetime
    records: tuple[SnapshotGraphRecord, ...]
    exact_record_counts_by_kind: tuple[tuple[GraphRecordKind, int], ...]
    codec_manifest_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    governance_policy_fingerprints: tuple[str, ...] = ()
    read_set: GraphReadSet
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_snapshot(self) -> GraphStateSnapshot:
        if self.system_as_of.tzinfo is None or self.system_as_of.utcoffset() != timedelta(0):
            raise ValueError("graph_state_snapshot_time_invalid")
        keys = tuple(
            (item.payload_record_kind, item.record_id)
            for item in self.records
        )
        if keys != tuple(sorted(set(keys))):
            raise ValueError("graph_state_snapshot_records_not_canonical")
        expected_counts = tuple(
            (
                kind,
                sum(item.payload_record_kind == kind for item in self.records),
            )
            for kind in sorted(GraphRecordKind.__args__)
        )
        if self.exact_record_counts_by_kind != expected_counts:
            raise ValueError("graph_state_snapshot_counts_invalid")
        if self.codec_manifest_fingerprint != canonical_graph_codec_manifest().manifest_fingerprint:
            raise ValueError("graph_state_snapshot_codec_manifest_invalid")
        body = self.model_dump(mode="python", exclude={"snapshot_digest"})
        if self.snapshot_digest != graph_digest(b"memorii.graph-state-snapshot.v1\0", body):
            raise ValueError("graph_state_snapshot_digest_mismatch")
        return self


if TYPE_CHECKING:
    from memorii.core.semantic_ingestion.contracts import (
        ActionRevision,
        ClaimAssertion,
        IdentityLineageRecord,
        TemporalTransitionRecord,
    )

    CanonicalGraphRecord: TypeAlias = Annotated[
        EntityRevision | AliasRevision | TypeEvidence | ClaimAssertion | ClaimProjection
        | RelationRevision | ActionRevision | CitationRecord | ProvenanceRecord
        | TemporalTransitionRecord | IdentityLineageRecord | ReferenceDispositionRecord,
        Field(discriminator="record_kind"),
    ]


__all__ = [
    "AliasRevision", "CanonicalEntityRevisionRef", "CanonicalGraphRecordCodecManifest",
    "CitationRecord", "ClaimProjection",
    "EntityRevision", "GraphPartitionVersion", "GraphReadSet", "GraphReadSetExtension", "GraphRecordKind",
    "GroundedMentionRef",
    "GraphStateSnapshot", "GraphWriteIntent", "NonOwningGraphRecord", "PlannedEntityIdentity",
    "PlannedIdentityReservation", "ProvenanceRecord", "ReferenceDispositionRecord",
    "AcceptedIdentityOperationArtifact", "SourceGroundedAliasPayload",
    "TrustedAcceptedIdentityOperationDecision",
    "VerifiedIdentityDecisionAuthority",
    "RelationRevision", "SnapshotGraphRecord", "SourceAuthority", "TypeEvidence",
    "TypeEvidenceEntityReference", "canonical_graph_codec_manifest",
    "canonical_graph_record_adapter", "graph_digest", "graph_record_id",
]
