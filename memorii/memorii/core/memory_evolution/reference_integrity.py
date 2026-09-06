"""Generated reference manifest and append-only semantic carrier edge ledger."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.graph_records import (
    AliasRevision,
    CanonicalEntityRevisionRef,
    CitationRecord,
    ClaimProjection,
    EntityRevision,
    GraphRecordKind,
    ProvenanceRecord,
    ReferenceDispositionRecord,
    RelationRevision,
    TypeEvidence,
)
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.semantic_ingestion.contracts import (
    ActionRevision,
    ClaimAssertion,
    IdentityLineageRecord,
    TemporalTransitionRecord,
)
from memorii.core.semantic_ingestion.event_replay import (
    SemanticMaterializedMemoryRecord,
    SemanticReplayState,
)

ReferenceTargetKind = Literal["entity_revision", "logical_entity"]
ReferenceCardinality = Literal["one", "optional", "many"]
ReferenceLifecycle = Literal[
    "immutable_revision", "current_revision_redirectable", "logical_projection_key"
]
CarrierRecordKind = GraphRecordKind


def _digest(domain: bytes, value: object) -> str:
    return sha256(domain + encode_typed_value(_canonical(value))).hexdigest()


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


class ReferenceTarget(BaseModel):
    kind: ReferenceTargetKind
    target_id: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ReferenceFieldAnnotation(BaseModel):
    reference_path: str = Field(min_length=1)
    target_kind: ReferenceTargetKind
    cardinality: ReferenceCardinality
    lifecycle_semantics: ReferenceLifecycle
    annotation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @classmethod
    def create(cls, **values: object) -> ReferenceFieldAnnotation:
        return cls.model_validate(
            values
            | {
                "annotation_fingerprint": _digest(
                    b"memorii.reference-field-annotation.v1\0", values
                )
            }
        )


class ReferenceSchemaEntry(BaseModel):
    record_kind: CarrierRecordKind
    reference_fields: tuple[ReferenceFieldAnnotation, ...]
    owned_partition_family: str = Field(min_length=1)
    persistence_schema_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    extractor_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ReferenceSchemaManifest(BaseModel):
    schema_entries: tuple[ReferenceSchemaEntry, ...]
    manifest_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_manifest(self) -> ReferenceSchemaManifest:
        kinds = tuple(item.record_kind for item in self.schema_entries)
        expected = tuple(sorted(GraphRecordKind.__args__))
        if kinds != expected:
            raise ValueError("reference_manifest_not_total_over_carrier_union")
        if self.manifest_fingerprint != _digest(
            b"memorii.reference-schema-manifest.v1\0",
            tuple(item.model_dump(mode="python") for item in self.schema_entries),
        ):
            raise ValueError("reference_manifest_fingerprint_mismatch")
        return self


class ReferenceEdgeLedgerEntry(BaseModel):
    sequence: int = Field(ge=1)
    graph_revision: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    change: Literal["add", "remove"]
    record_kind: CarrierRecordKind
    record_id: str = Field(min_length=1)
    reference_path: str = Field(min_length=1)
    target: ReferenceTarget
    base_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    prior_entry_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    ledger_entry_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_entry(self) -> ReferenceEdgeLedgerEntry:
        if (self.sequence == 1) != (self.prior_entry_digest is None):
            raise ValueError("reference_ledger_chain_invalid")
        body = self.model_dump(mode="python", exclude={"ledger_entry_digest"})
        if self.ledger_entry_digest != _digest(b"memorii.reference-edge-ledger-entry.v1\0", body):
            raise ValueError("reference_ledger_entry_digest_mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> ReferenceEdgeLedgerEntry:
        return cls.model_validate(
            values
            | {"ledger_entry_digest": _digest(b"memorii.reference-edge-ledger-entry.v1\0", values)}
        )


class ReferenceAuditCertificate(BaseModel):
    certificate_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_revision: str = Field(min_length=1)
    schema_manifest_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    ledger_start_watermark: str = Field(pattern=r"^[0-9a-f]{64}$")
    ledger_end_watermark: str = Field(pattern=r"^[0-9a-f]{64}$")
    covered_partition_versions: tuple[tuple[str, str], ...]
    base_record_count: int = Field(ge=0)
    extracted_reference_count: int = Field(ge=0)
    base_record_counts_by_kind: tuple[tuple[GraphRecordKind, int], ...]
    base_record_digests_by_kind: tuple[tuple[GraphRecordKind, str], ...]
    reference_counts_by_target_kind: tuple[tuple[ReferenceTargetKind, int], ...]
    reference_digests_by_target_kind: tuple[tuple[ReferenceTargetKind, str], ...]
    base_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    ledger_entries_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    complete: Literal[True] = True
    contiguous: Literal[True] = True
    completed_at: datetime
    certificate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_certificate(self) -> ReferenceAuditCertificate:
        if self.completed_at.tzinfo is None or self.completed_at.utcoffset() != timedelta(0):
            raise ValueError("reference_audit_time_must_be_utc")
        if self.ledger_start_watermark != "0" * 64:
            raise ValueError("reference_audit_start_watermark_invalid")
        if self.covered_partition_versions != tuple(
            sorted(set(self.covered_partition_versions))
        ):
            raise ValueError("reference_audit_partition_versions_not_canonical")
        expected_record_kinds = tuple(sorted(GraphRecordKind.__args__))
        if tuple(kind for kind, _ in self.base_record_counts_by_kind) != expected_record_kinds:
            raise ValueError("reference_audit_base_counts_not_total")
        if tuple(kind for kind, _ in self.base_record_digests_by_kind) != expected_record_kinds:
            raise ValueError("reference_audit_base_digests_not_total")
        expected_target_kinds = tuple(sorted(ReferenceTargetKind.__args__))
        if tuple(kind for kind, _ in self.reference_counts_by_target_kind) != expected_target_kinds:
            raise ValueError("reference_audit_reference_counts_not_total")
        if tuple(kind for kind, _ in self.reference_digests_by_target_kind) != expected_target_kinds:
            raise ValueError("reference_audit_reference_digests_not_total")
        identity_body = self.model_dump(
            mode="python", exclude={"certificate_id", "certificate_digest"}
        )
        if self.certificate_id != _digest(
            b"memorii.reference-audit-certificate-id.v1\0", identity_body
        ):
            raise ValueError("reference_audit_certificate_id_mismatch")
        body = self.model_dump(mode="python", exclude={"certificate_digest"})
        if self.certificate_digest != _digest(b"memorii.reference-audit-certificate.v1\0", body):
            raise ValueError("reference_audit_certificate_digest_mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> ReferenceAuditCertificate:
        identity = _digest(b"memorii.reference-audit-certificate-id.v1\0", values)
        body = values | {"certificate_id": identity}
        return cls.model_validate(
            body
            | {"certificate_digest": _digest(b"memorii.reference-audit-certificate.v1\0", body)}
        )


class ReferenceEdgeLedgerSnapshot(BaseModel):
    manifest_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    entries: tuple[ReferenceEdgeLedgerEntry, ...]
    audit_certificate: ReferenceAuditCertificate | None = None
    active: bool = False
    ledger_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_snapshot(self) -> ReferenceEdgeLedgerSnapshot:
        for index, entry in enumerate(self.entries, start=1):
            prior = self.entries[index - 2].ledger_entry_digest if index > 1 else None
            if entry.sequence != index or entry.prior_entry_digest != prior:
                raise ValueError("reference_ledger_not_contiguous")
        if self.active != (self.audit_certificate is not None):
            raise ValueError("reference_integrity_activation_invalid")
        if self.audit_certificate is not None and (
            self.audit_certificate.schema_manifest_fingerprint != self.manifest_fingerprint
            or self.audit_certificate.ledger_end_watermark != self.high_watermark
            or self.audit_certificate.ledger_entries_digest
            != _digest(
                b"memorii.reference-audit-ledger-entries.v1\0",
                tuple(item.ledger_entry_digest for item in self.entries),
            )
        ):
            raise ValueError("reference_audit_certificate_stale")
        body = self.model_dump(mode="python", exclude={"ledger_digest"})
        if self.ledger_digest != _digest(b"memorii.reference-edge-ledger-snapshot.v1\0", body):
            raise ValueError("reference_ledger_digest_mismatch")
        return self

    @property
    def high_watermark(self) -> str:
        return self.entries[-1].ledger_entry_digest if self.entries else "0" * 64

    @classmethod
    def create(cls, **values: object) -> ReferenceEdgeLedgerSnapshot:
        return cls.model_validate(
            values
            | {"ledger_digest": _digest(b"memorii.reference-edge-ledger-snapshot.v1\0", values)}
        )


@lru_cache(maxsize=1)
def generated_reference_schema_manifest() -> ReferenceSchemaManifest:
    """Generate the total manifest from the deployed canonical graph union."""

    specs: dict[CarrierRecordKind, tuple[tuple[str, ReferenceTargetKind, ReferenceCardinality, ReferenceLifecycle], ...]] = {
        "action_revision": (),
        "alias_revision": (
            ("entity_revision_id", "entity_revision", "one", "current_revision_redirectable"),
            ("logical_entity_id", "logical_entity", "one", "logical_projection_key"),
        ),
        "citation": (
            ("entity_revision_id", "entity_revision", "optional", "immutable_revision"),
            ("logical_entity_id", "logical_entity", "optional", "logical_projection_key"),
        ),
        "claim_assertion": (
            ("/claim_identity/subject_assertion_ref/entity_revision_id", "entity_revision", "one", "immutable_revision"),
            ("/claim_identity/assertion_key_at_recording/slot/subject_logical_entity_id", "logical_entity", "one", "immutable_revision"),
            ("/claim_identity/object_assertion_ref/entity_revision_id", "entity_revision", "optional", "immutable_revision"),
            ("/claim_identity/assertion_key_at_recording/value/object_logical_entity_id", "logical_entity", "optional", "immutable_revision"),
        ),
        "claim_projection": (
            ("subject_entity_revision_id", "entity_revision", "one", "current_revision_redirectable"),
            ("subject_logical_entity_id", "logical_entity", "one", "logical_projection_key"),
            ("object_entity_revision_id", "entity_revision", "optional", "current_revision_redirectable"),
            ("object_logical_entity_id", "logical_entity", "optional", "logical_projection_key"),
        ),
        "entity_revision": (
            ("logical_entity_id", "logical_entity", "one", "logical_projection_key"),
        ),
        "identity_lineage": (
            ("transition.predecessors[].entity_revision_id", "entity_revision", "many", "immutable_revision"),
            ("transition.predecessors[].logical_entity_id", "logical_entity", "many", "immutable_revision"),
            ("transition.successors[].entity_revision_id", "entity_revision", "many", "immutable_revision"),
            ("transition.successors[].logical_entity_id", "logical_entity", "many", "immutable_revision"),
        ),
        "provenance": (
            ("entity_revision_id", "entity_revision", "optional", "immutable_revision"),
            ("logical_entity_id", "logical_entity", "optional", "logical_projection_key"),
        ),
        "reference_disposition": (
            ("predecessor_entity_revision_id", "entity_revision", "one", "immutable_revision"),
            ("predecessor_logical_entity_id", "logical_entity", "one", "logical_projection_key"),
            ("successor_entity_revision_ids[]", "entity_revision", "many", "current_revision_redirectable"),
            ("successor_logical_entity_ids[]", "logical_entity", "many", "logical_projection_key"),
        ),
        "relation_revision": (
            ("subject_entity_revision_id", "entity_revision", "one", "current_revision_redirectable"),
            ("subject_logical_entity_id", "logical_entity", "one", "logical_projection_key"),
            ("object_entity_revision_id", "entity_revision", "one", "current_revision_redirectable"),
            ("object_logical_entity_id", "logical_entity", "one", "logical_projection_key"),
        ),
        "temporal_transition": (),
        "type_evidence": (
            ("entity_reference.entity_revision_id", "entity_revision", "optional", "immutable_revision"),
            ("entity_reference.logical_entity_id", "logical_entity", "optional", "logical_projection_key"),
        ),
    }
    entries = []
    models = {
        "action_revision": ActionRevision,
        "alias_revision": AliasRevision,
        "citation": CitationRecord,
        "claim_assertion": ClaimAssertion,
        "claim_projection": ClaimProjection,
        "entity_revision": EntityRevision,
        "identity_lineage": IdentityLineageRecord,
        "provenance": ProvenanceRecord,
        "reference_disposition": ReferenceDispositionRecord,
        "relation_revision": RelationRevision,
        "temporal_transition": TemporalTransitionRecord,
        "type_evidence": TypeEvidence,
    }
    for kind in sorted(specs):
        fields = tuple(
            ReferenceFieldAnnotation.create(
                reference_path=path,
                target_kind=target,
                cardinality=cardinality,
                lifecycle_semantics=lifecycle,
            )
            for path, target, cardinality, lifecycle in specs[kind]
        )
        schema = models[kind].model_json_schema()
        entries.append(
            ReferenceSchemaEntry(
                record_kind=kind,
                reference_fields=fields,
                owned_partition_family=f"canonical_graph:{kind}",
                persistence_schema_fingerprint=_digest(b"memorii.reference-schema.v1\0", schema),
                extractor_fingerprint=_digest(
                    b"memorii.reference-extractor.v1\0",
                    tuple(field.model_dump(mode="python") for field in fields),
                ),
            )
        )
    payload = tuple(entries)
    return ReferenceSchemaManifest(
        schema_entries=payload,
        manifest_fingerprint=_digest(
            b"memorii.reference-schema-manifest.v1\0",
            tuple(item.model_dump(mode="python") for item in payload),
        ),
    )


def extract_reference_edges(record: object) -> tuple[tuple[str, ReferenceTarget], ...]:
    """Extract exactly the references declared by the generated manifest."""

    edges: list[tuple[str, ReferenceTarget]] = []
    if isinstance(record, ClaimAssertion) and record.claim_identity is not None:
        subject = record.claim_identity.subject_assertion_ref
        edges.extend(
            (
                ("/claim_identity/subject_assertion_ref/entity_revision_id", ReferenceTarget(kind="entity_revision", target_id=subject.entity_revision_id)),
                ("/claim_identity/assertion_key_at_recording/slot/subject_logical_entity_id", ReferenceTarget(kind="logical_entity", target_id=subject.logical_entity_id_at_assertion)),
            )
        )
        obj = record.claim_identity.object_assertion_ref
        if obj is not None:
            edges.extend(
                (
                    ("/claim_identity/object_assertion_ref/entity_revision_id", ReferenceTarget(kind="entity_revision", target_id=obj.entity_revision_id)),
                    ("/claim_identity/assertion_key_at_recording/value/object_logical_entity_id", ReferenceTarget(kind="logical_entity", target_id=obj.logical_entity_id_at_assertion)),
                )
            )
    elif isinstance(record, IdentityLineageRecord):
        for label, identities in (("predecessors", record.transition.predecessors), ("successors", record.transition.successors)):
            for identity in identities:
                edges.extend(
                    (
                        (f"transition.{label}[].entity_revision_id", ReferenceTarget(kind="entity_revision", target_id=identity.entity_revision_id)),
                        (f"transition.{label}[].logical_entity_id", ReferenceTarget(kind="logical_entity", target_id=identity.logical_entity_id)),
                    )
                )
    elif isinstance(record, EntityRevision):
        edges.append(("logical_entity_id", ReferenceTarget(kind="logical_entity", target_id=record.logical_entity_id)))
    elif isinstance(record, AliasRevision):
        edges.extend((
            ("entity_revision_id", ReferenceTarget(kind="entity_revision", target_id=record.entity_revision_id)),
            ("logical_entity_id", ReferenceTarget(kind="logical_entity", target_id=record.logical_entity_id)),
        ))
    elif isinstance(record, TypeEvidence) and isinstance(
        record.entity_reference, CanonicalEntityRevisionRef
    ):
        edges.extend((
            ("entity_reference.entity_revision_id", ReferenceTarget(
                kind="entity_revision", target_id=record.entity_reference.entity_revision_id
            )),
            ("entity_reference.logical_entity_id", ReferenceTarget(
                kind="logical_entity", target_id=record.entity_reference.logical_entity_id
            )),
        ))
    elif isinstance(record, ClaimProjection):
        edges.extend((
            ("subject_entity_revision_id", ReferenceTarget(kind="entity_revision", target_id=record.subject_entity_revision_id)),
            ("subject_logical_entity_id", ReferenceTarget(kind="logical_entity", target_id=record.subject_logical_entity_id)),
        ))
        if record.object_entity_revision_id is not None:
            edges.append(("object_entity_revision_id", ReferenceTarget(kind="entity_revision", target_id=record.object_entity_revision_id)))
        if record.object_logical_entity_id is not None:
            edges.append(("object_logical_entity_id", ReferenceTarget(kind="logical_entity", target_id=record.object_logical_entity_id)))
    elif isinstance(record, RelationRevision):
        edges.extend((
            ("subject_entity_revision_id", ReferenceTarget(kind="entity_revision", target_id=record.subject_entity_revision_id)),
            ("subject_logical_entity_id", ReferenceTarget(kind="logical_entity", target_id=record.subject_logical_entity_id)),
            ("object_entity_revision_id", ReferenceTarget(kind="entity_revision", target_id=record.object_entity_revision_id)),
            ("object_logical_entity_id", ReferenceTarget(kind="logical_entity", target_id=record.object_logical_entity_id)),
        ))
    elif isinstance(record, (CitationRecord, ProvenanceRecord)):
        if record.entity_revision_id is not None:
            edges.append(("entity_revision_id", ReferenceTarget(kind="entity_revision", target_id=record.entity_revision_id)))
        if record.logical_entity_id is not None:
            edges.append(("logical_entity_id", ReferenceTarget(kind="logical_entity", target_id=record.logical_entity_id)))
    elif isinstance(record, ReferenceDispositionRecord):
        edges.extend((
            ("predecessor_entity_revision_id", ReferenceTarget(kind="entity_revision", target_id=record.predecessor_entity_revision_id)),
            ("predecessor_logical_entity_id", ReferenceTarget(kind="logical_entity", target_id=record.predecessor_logical_entity_id)),
        ))
        edges.extend(
            ("successor_entity_revision_ids[]", ReferenceTarget(kind="entity_revision", target_id=value))
            for value in record.successor_entity_revision_ids
        )
        edges.extend(
            ("successor_logical_entity_ids[]", ReferenceTarget(kind="logical_entity", target_id=value))
            for value in record.successor_logical_entity_ids
        )
    return tuple(sorted(edges, key=lambda item: (item[0], item[1].kind, item[1].target_id)))


def _reference_audit_certificate(
    *,
    state: SemanticReplayState,
    entries: tuple[ReferenceEdgeLedgerEntry, ...],
    manifest_fingerprint: str,
    completed_at: datetime,
) -> ReferenceAuditCertificate:
    base = tuple(
        (item.record_kind, item.record_id, item.record_digest)
        for item in state.materialized_records
    )
    active = _active_edges(entries)
    end_watermark = entries[-1].ledger_entry_digest if entries else "0" * 64
    base_counts = tuple(
        (kind, sum(item.record_kind == kind for item in state.materialized_records))
        for kind in sorted(GraphRecordKind.__args__)
    )
    base_digests = tuple(
        (
            kind,
            _digest(
                b"memorii.reference-audit-base-record-kind.v1\0",
                tuple(item for item in base if item[0] == kind),
            ),
        )
        for kind in sorted(GraphRecordKind.__args__)
    )
    reference_counts = tuple(
        (kind, sum(item.target.kind == kind for item in active))
        for kind in sorted(ReferenceTargetKind.__args__)
    )
    reference_digests = tuple(
        (
            kind,
            _digest(
                b"memorii.reference-audit-target-kind.v1\0",
                tuple(
                    item.ledger_entry_digest
                    for item in active
                    if item.target.kind == kind
                ),
            ),
        )
        for kind in sorted(ReferenceTargetKind.__args__)
    )
    return ReferenceAuditCertificate.create(
        graph_revision=state.graph_revision,
        schema_manifest_fingerprint=manifest_fingerprint,
        ledger_start_watermark="0" * 64,
        ledger_end_watermark=end_watermark,
        covered_partition_versions=tuple(sorted((
            ("canonical_graph", state.graph_revision),
            ("reference_ledger", end_watermark),
        ))),
        base_record_count=len(state.materialized_records),
        extracted_reference_count=len(active),
        base_record_counts_by_kind=base_counts,
        base_record_digests_by_kind=base_digests,
        reference_counts_by_target_kind=reference_counts,
        reference_digests_by_target_kind=reference_digests,
        base_record_digest=_digest(b"memorii.reference-audit-base-records.v1\0", base),
        ledger_entries_digest=_digest(
            b"memorii.reference-audit-ledger-entries.v1\0",
            tuple(item.ledger_entry_digest for item in entries),
        ),
        complete=True,
        contiguous=True,
        completed_at=completed_at,
    )


def bootstrap_reference_integrity(
    state: SemanticReplayState,
    *,
    completed_at: datetime | None = None,
) -> ReferenceEdgeLedgerSnapshot:
    manifest = generated_reference_schema_manifest()
    entries = _append_changes((), state.materialized_records, state.graph_revision, "reference-integrity-bootstrap")
    certificate = _reference_audit_certificate(
        state=state,
        entries=entries,
        manifest_fingerprint=manifest.manifest_fingerprint,
        completed_at=(completed_at or datetime.now(UTC)).astimezone(UTC),
    )
    snapshot = ReferenceEdgeLedgerSnapshot.create(
        manifest_fingerprint=manifest.manifest_fingerprint,
        entries=entries,
        audit_certificate=certificate,
        active=True,
    )
    validate_reference_integrity_converse(snapshot, state)
    return snapshot


def advance_reference_integrity(
    prior: ReferenceEdgeLedgerSnapshot,
    *,
    prior_state: SemanticReplayState,
    next_state: SemanticReplayState,
    operation_id: str,
    completed_at: datetime,
) -> ReferenceEdgeLedgerSnapshot:
    if not prior.active or prior.manifest_fingerprint != generated_reference_schema_manifest().manifest_fingerprint:
        raise ValueError("unresolved_reference_integrity_not_bootstrapped")
    prior_by_key = {(item.record_kind, item.record_id): item for item in prior_state.materialized_records}
    next_by_key = {(item.record_kind, item.record_id): item for item in next_state.materialized_records}
    changed = tuple(
        next_by_key[key]
        for key in sorted(next_by_key)
        if key not in prior_by_key or prior_by_key[key].record_digest != next_by_key[key].record_digest
    )
    removed = tuple(
        prior_by_key[key]
        for key in sorted(prior_by_key)
        if key in next_by_key and prior_by_key[key].record_digest != next_by_key[key].record_digest
    )
    entries = _append_changes(prior.entries, removed, next_state.graph_revision, operation_id, change="remove")
    entries = _append_changes(entries, changed, next_state.graph_revision, operation_id)
    snapshot = ReferenceEdgeLedgerSnapshot.create(
        manifest_fingerprint=prior.manifest_fingerprint,
        entries=entries,
        audit_certificate=_reference_audit_certificate(
            state=next_state,
            entries=entries,
            manifest_fingerprint=prior.manifest_fingerprint,
            completed_at=completed_at.astimezone(UTC),
        ),
        active=True,
    )
    validate_reference_integrity_converse(snapshot, next_state)
    return snapshot


def active_reverse_references(
    snapshot: ReferenceEdgeLedgerSnapshot,
    targets: Iterable[ReferenceTarget],
) -> tuple[ReferenceEdgeLedgerEntry, ...]:
    target_set = set(targets)
    return tuple(entry for entry in _active_edges(snapshot.entries) if entry.target in target_set)


def validate_reference_integrity_converse(
    snapshot: ReferenceEdgeLedgerSnapshot,
    state: SemanticReplayState,
) -> None:
    """Prove both ledger-to-record and record-to-ledger completeness."""

    manifest = generated_reference_schema_manifest()
    if not snapshot.active or snapshot.manifest_fingerprint != manifest.manifest_fingerprint:
        raise ValueError("unresolved_reference_integrity_not_bootstrapped")
    certificate = snapshot.audit_certificate
    if certificate is None:
        raise ValueError("reference_audit_certificate_missing")
    expected_certificate = _reference_audit_certificate(
        state=state,
        entries=snapshot.entries,
        manifest_fingerprint=snapshot.manifest_fingerprint,
        completed_at=certificate.completed_at,
    )
    if certificate != expected_certificate:
        raise ValueError("reference_audit_certificate_state_mismatch")
    expected = {
        (
            item.record_kind,
            item.record_id,
            path,
            target,
            item.record_digest,
        )
        for item in state.materialized_records
        for path, target in extract_reference_edges(item.record)
    }
    observed = {
        (
            item.record_kind,
            item.record_id,
            item.reference_path,
            item.target,
            item.base_record_digest,
        )
        for item in _active_edges(snapshot.entries)
    }
    if observed != expected:
        raise ValueError("reference_integrity_ledger_converse_mismatch")


def _active_edges(entries: tuple[ReferenceEdgeLedgerEntry, ...]) -> tuple[ReferenceEdgeLedgerEntry, ...]:
    active: dict[tuple[str, str, str, ReferenceTarget], ReferenceEdgeLedgerEntry] = {}
    for entry in entries:
        key = (entry.record_kind, entry.record_id, entry.reference_path, entry.target)
        if entry.change == "add":
            active[key] = entry
        else:
            active.pop(key, None)
    return tuple(sorted(active.values(), key=lambda item: item.ledger_entry_digest))


def _append_changes(
    existing: tuple[ReferenceEdgeLedgerEntry, ...],
    records: Iterable[SemanticMaterializedMemoryRecord],
    graph_revision: str,
    operation_id: str,
    *,
    change: Literal["add", "remove"] = "add",
) -> tuple[ReferenceEdgeLedgerEntry, ...]:
    entries = list(existing)
    for materialized in records:
        record = materialized.record
        for path, target in extract_reference_edges(record):
            values = {
                "sequence": len(entries) + 1,
                "graph_revision": graph_revision,
                "operation_id": operation_id,
                "change": change,
                "record_kind": materialized.record_kind,
                "record_id": materialized.record_id,
                "reference_path": path,
                "target": target,
                "base_record_digest": materialized.record_digest,
                "prior_entry_digest": entries[-1].ledger_entry_digest if entries else None,
            }
            entries.append(ReferenceEdgeLedgerEntry.create(**values))
    return tuple(entries)


__all__ = [
    "ReferenceAuditCertificate", "ReferenceEdgeLedgerEntry", "ReferenceEdgeLedgerSnapshot",
    "ReferenceFieldAnnotation", "ReferenceSchemaManifest", "ReferenceTarget",
    "active_reverse_references", "advance_reference_integrity", "bootstrap_reference_integrity",
    "extract_reference_edges", "generated_reference_schema_manifest",
    "validate_reference_integrity_converse",
]
