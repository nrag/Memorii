"""Typed, prefix-checked planning state for canonical graph transactions."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.graph_records import (
    AcceptedIdentityOperationArtifact,
    AliasRevision,
    EntityRevision,
    GraphRecordKind,
    ReferenceDispositionRecord,
    SnapshotGraphRecord,
    TrustedAcceptedIdentityOperationDecision,
    VerifiedIdentityDecisionAuthority,
    canonical_graph_codec_manifest,
    canonical_graph_record_adapter,
    certified_graph_record_kind,
    graph_digest,
    graph_record_id,
    graph_record_union_member,
    validated_graph_record,
)

if TYPE_CHECKING:
    from memorii.core.memory_evolution.graph_records import CanonicalGraphRecord
from memorii.core.memory_evolution.reference_integrity import (
    ReferenceTarget,
    extract_reference_edges,
    generated_reference_schema_manifest,
)
from memorii.core.memory_evolution.semantic_state import (
    CompiledIdentityLineageTransition,
    LineageReferenceDisposition,
)
from memorii.core.semantic_ingestion.canonical_evidence_arena import (
    certified_instance,
    deeply_immutable_type,
    record_certified_instance,
)
from memorii.core.semantic_ingestion.carriers import compile_accepted_carriers
from memorii.core.semantic_ingestion.contracts import (
    ActionRevision,
    ClaimAssertion,
    IdentityLineageRecord,
    TemporalTransitionRecord,
    contract_digest,
)


class PlannedCommitCoordinate(BaseModel):
    kind: Literal["transaction_commit_coordinate"] = "transaction_commit_coordinate"
    transaction_group_id: str = Field(min_length=1)
    coordinate: Literal[
        "graph_revision_before", "graph_revision_after", "committed_at"
    ]

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PlanningCommitValues(BaseModel):
    transaction_group_id: str = Field(min_length=1)
    graph_revision_before: str = Field(min_length=1)
    graph_revision_after: str = Field(min_length=1)
    committed_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_time(self) -> PlanningCommitValues:
        if self.committed_at.tzinfo is None or self.committed_at.utcoffset() != timedelta(0):
            raise ValueError("planning_commit_time_invalid")
        return self


class _PlanningPayload(BaseModel):
    record_kind: GraphRecordKind
    planning_record: dict[str, object]

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_coordinates(self) -> _PlanningPayload:
        if self.planning_record.get("record_kind") != self.record_kind:
            raise ValueError("planning_payload_record_kind_mismatch")
        if "record_digest" in self.planning_record:
            raise ValueError("planning_payload_prebound_record_digest")
        manifest = {
            item.record_kind: item
            for item in canonical_graph_codec_manifest().entries
        }
        declared = manifest[self.record_kind].transaction_owned_fields
        found: list[tuple[str, PlannedCommitCoordinate]] = []

        def walk(value: object, path: tuple[str, ...] = ()) -> None:
            if isinstance(value, dict):
                if value.get("kind") == "transaction_commit_coordinate":
                    coordinate = PlannedCommitCoordinate.model_validate(value)
                    found.append((".".join(path), coordinate))
                    return
                for key, item in value.items():
                    walk(item, (*path, key))
            elif isinstance(value, (tuple, list)):
                for index, item in enumerate(value):
                    walk(item, (*path, str(index)))

        walk(self.planning_record)
        if tuple((path, item.coordinate) for path, item in found) != declared:
            raise ValueError("planning_payload_coordinate_manifest_mismatch")
        if len({item.transaction_group_id for _, item in found}) > 1:
            raise ValueError("planning_payload_multiple_producers")
        return self


class PlanningEntityRevision(_PlanningPayload):
    record_kind: Literal["entity_revision"] = "entity_revision"


class PlanningAliasRevision(_PlanningPayload):
    record_kind: Literal["alias_revision"] = "alias_revision"


class PlanningTypeEvidence(_PlanningPayload):
    record_kind: Literal["type_evidence"] = "type_evidence"


class PlanningClaimAssertion(_PlanningPayload):
    record_kind: Literal["claim_assertion"] = "claim_assertion"


class PlanningClaimProjection(_PlanningPayload):
    record_kind: Literal["claim_projection"] = "claim_projection"


class PlanningRelationRevision(_PlanningPayload):
    record_kind: Literal["relation_revision"] = "relation_revision"


class PlanningActionRevision(_PlanningPayload):
    record_kind: Literal["action_revision"] = "action_revision"


class PlanningCitation(_PlanningPayload):
    record_kind: Literal["citation"] = "citation"


class PlanningProvenance(_PlanningPayload):
    record_kind: Literal["provenance"] = "provenance"


class PlanningTemporalTransition(_PlanningPayload):
    record_kind: Literal["temporal_transition"] = "temporal_transition"


class PlanningIdentityLineage(_PlanningPayload):
    record_kind: Literal["identity_lineage"] = "identity_lineage"


class PlanningReferenceDisposition(_PlanningPayload):
    record_kind: Literal["reference_disposition"] = "reference_disposition"


CanonicalPlanningRecordPayload = Annotated[
    PlanningEntityRevision
    | PlanningAliasRevision
    | PlanningTypeEvidence
    | PlanningClaimAssertion
    | PlanningClaimProjection
    | PlanningRelationRevision
    | PlanningActionRevision
    | PlanningCitation
    | PlanningProvenance
    | PlanningTemporalTransition
    | PlanningIdentityLineage
    | PlanningReferenceDisposition,
    Field(discriminator="record_kind"),
]


class PlanningSnapshotGraphRecord(BaseModel):
    record_id: str = Field(min_length=1)
    record_version: int = Field(ge=1)
    payload: CanonicalPlanningRecordPayload
    planning_projection_codec_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_projection_schema_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_record(self) -> PlanningSnapshotGraphRecord:
        manifest = {
            item.record_kind: item for item in canonical_graph_codec_manifest().entries
        }
        codec = manifest[self.payload.record_kind]
        planned_version = self.payload.planning_record.get("record_version")
        if (
            self.record_id != _planning_record_id(self.payload)
            or self.record_version != planned_version
            or self.planning_projection_codec_fingerprint
            != codec.planning_projection_codec_fingerprint
            or self.planning_projection_schema_fingerprint
            != codec.planning_projection_schema_fingerprint
        ):
            raise ValueError("planning_snapshot_record_binding_mismatch")
        body = self.model_dump(mode="python", exclude={"planning_record_digest"})
        if self.planning_record_digest != graph_digest(
            b"memorii.planning-snapshot-record.v1\0", body
        ):
            raise ValueError("planning_snapshot_record_digest_mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> PlanningSnapshotGraphRecord:
        return cls.model_validate(
            values
            | {
                "planning_record_digest": graph_digest(
                    b"memorii.planning-snapshot-record.v1\0", values
                )
            }
        )


class AbsentPlanningPrecondition(BaseModel):
    kind: Literal["absent"] = "absent"
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class DurablePlanningPrecondition(BaseModel):
    kind: Literal["durable"] = "durable"
    record_version: int = Field(ge=1)
    record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PendingPlanningPrecondition(BaseModel):
    kind: Literal["pending"] = "pending"
    producing_transaction_group_id: str = Field(min_length=1)
    record_version: int = Field(ge=1)
    planning_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


PlanningRecordPrecondition = Annotated[
    AbsentPlanningPrecondition | DurablePlanningPrecondition | PendingPlanningPrecondition,
    Field(discriminator="kind"),
]


class PlanningReferenceLedgerEntry(BaseModel):
    commit_coordinate: PlannedCommitCoordinate
    operation_id: str = Field(min_length=1)
    change: Literal["add", "remove"]
    record_kind: GraphRecordKind
    record_id: str = Field(min_length=1)
    reference_path: str = Field(min_length=1)
    target: ReferenceTarget
    base_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_ledger_entry_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_digest(self) -> PlanningReferenceLedgerEntry:
        if self.commit_coordinate.coordinate != "graph_revision_after":
            raise ValueError("planning_reference_commit_coordinate_invalid")
        body = self.model_dump(mode="python", exclude={"planning_ledger_entry_digest"})
        if self.planning_ledger_entry_digest != graph_digest(b"memorii.planning-reference-entry.v1\0", body):
            raise ValueError("planning_reference_entry_digest_mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> PlanningReferenceLedgerEntry:
        return cls.model_validate(
            values
            | {"planning_ledger_entry_digest": graph_digest(b"memorii.planning-reference-entry.v1\0", values)}
        )


class MaterializedPlanningReferenceLedgerMutation(BaseModel):
    graph_revision: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    change: Literal["add", "remove"]
    record_kind: GraphRecordKind
    record_id: str = Field(min_length=1)
    reference_path: str = Field(min_length=1)
    target: ReferenceTarget
    base_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PlanningGraphRecordMutation(BaseModel):
    mutation_kind: Literal["create", "update"]
    record_kind: GraphRecordKind
    record_id: str = Field(min_length=1)
    before: PlanningRecordPrecondition
    after_planning_record: PlanningSnapshotGraphRecord
    reference_edges_removed: tuple[PlanningReferenceLedgerEntry, ...] = ()
    reference_edges_added: tuple[PlanningReferenceLedgerEntry, ...] = ()
    mutation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_mutation(self) -> PlanningGraphRecordMutation:
        if (
            self.record_kind != self.after_planning_record.payload.record_kind
            or self.record_id != self.after_planning_record.record_id
        ):
            raise ValueError("planning_mutation_record_binding_mismatch")
        if self.mutation_kind == "create":
            valid_shape = isinstance(self.before, AbsentPlanningPrecondition)
        else:
            valid_shape = not isinstance(self.before, AbsentPlanningPrecondition)
        if not valid_shape:
            raise ValueError("planning_mutation_precondition_shape_invalid")
        producer_groups = {
            coordinate.transaction_group_id
            for coordinate in _planning_coordinates(
                self.after_planning_record.payload
            )
        } | {
            item.commit_coordinate.transaction_group_id
            for item in (
                *self.reference_edges_removed,
                *self.reference_edges_added,
            )
        }
        for change, values in (
            ("remove", self.reference_edges_removed),
            ("add", self.reference_edges_added),
        ):
            digests = tuple(item.planning_ledger_entry_digest for item in values)
            if digests != tuple(sorted(set(digests))):
                raise ValueError("planning_mutation_reference_entries_not_canonical")
            if any(
                item.change != change
                or item.record_kind != self.record_kind
                or item.record_id != self.record_id
                or item.commit_coordinate.transaction_group_id not in producer_groups
                for item in values
            ):
                raise ValueError("planning_mutation_reference_entry_binding_invalid")
        if self.reference_edges_removed and isinstance(
            self.before, AbsentPlanningPrecondition
        ):
            raise ValueError("planning_create_cannot_remove_reference_edges")
        if isinstance(self.before, DurablePlanningPrecondition) and any(
            item.base_record_digest != self.before.record_digest
            for item in self.reference_edges_removed
        ):
            raise ValueError("planning_removed_reference_base_mismatch")
        if any(
            item.base_record_digest
            != self.after_planning_record.planning_record_digest
            for item in self.reference_edges_added
        ):
            raise ValueError("planning_added_reference_base_mismatch")
        body = self.model_dump(mode="python", exclude={"mutation_digest"})
        if self.mutation_digest != graph_digest(b"memorii.planning-mutation.v1\0", body):
            raise ValueError("planning_mutation_digest_mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> PlanningGraphRecordMutation:
        body = {
            "reference_edges_removed": (),
            "reference_edges_added": (),
            **values,
        }
        return cls.model_validate(
            body | {"mutation_digest": graph_digest(b"memorii.planning-mutation.v1\0", body)}
        )


class DurablePlanningStateRecord(BaseModel):
    state_kind: Literal["durable"] = "durable"
    record: SnapshotGraphRecord
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PendingPlanningStateRecord(BaseModel):
    state_kind: Literal["pending"] = "pending"
    producing_transaction_group_id: str = Field(min_length=1)
    record: PlanningSnapshotGraphRecord
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


PlanningStateRecord = Annotated[
    DurablePlanningStateRecord | PendingPlanningStateRecord,
    Field(discriminator="state_kind"),
]


class GraphPlanningDelta(BaseModel):
    sequence: int = Field(ge=1)
    base_state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    producing_transaction_group_id: str = Field(min_length=1)
    mutations: tuple[PlanningGraphRecordMutation, ...]
    delta_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_delta(self) -> GraphPlanningDelta:
        keys = tuple((item.record_kind, item.record_id) for item in self.mutations)
        if keys != tuple(sorted(set(keys))) or not keys:
            raise ValueError("planning_delta_mutations_not_canonical")
        if any(
            any(
                coordinate.transaction_group_id
                != self.producing_transaction_group_id
                for coordinate in _planning_coordinates(
                    item.after_planning_record.payload
                )
            )
            for item in self.mutations
        ):
            raise ValueError("planning_delta_producer_mismatch")
        body = self.model_dump(mode="python", exclude={"delta_digest"})
        if self.delta_digest != graph_digest(b"memorii.graph-planning-delta.v1\0", body):
            raise ValueError("planning_delta_digest_mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> GraphPlanningDelta:
        return cls.model_validate(
            values | {"delta_digest": graph_digest(b"memorii.graph-planning-delta.v1\0", values)}
        )


class GraphPlanningState(BaseModel):
    base_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    records: tuple[PlanningStateRecord, ...]
    codec_manifest_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    applied_planned_delta_digests: tuple[str, ...]
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_state(self) -> GraphPlanningState:
        keys = tuple(
            (
                item.record.payload_record_kind
                if isinstance(item, DurablePlanningStateRecord)
                else item.record.payload.record_kind,
                item.record.record_id,
            )
            for item in self.records
        )
        if keys != tuple(sorted(set(keys))):
            raise ValueError("planning_state_records_not_canonical")
        if self.codec_manifest_fingerprint != canonical_graph_codec_manifest().manifest_fingerprint:
            raise ValueError("planning_state_manifest_mismatch")
        if len(set(self.applied_planned_delta_digests)) != len(
            self.applied_planned_delta_digests
        ):
            raise ValueError("planning_state_delta_reapplied")
        body = self.model_dump(mode="python", exclude={"state_digest"})
        if self.state_digest != graph_digest(b"memorii.graph-planning-state.v1\0", body):
            raise ValueError("planning_state_digest_mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> GraphPlanningState:
        return cls.model_validate(
            values | {"state_digest": graph_digest(b"memorii.graph-planning-state.v1\0", values)}
        )

    def apply(self, delta: GraphPlanningDelta) -> GraphPlanningState:
        if delta.delta_digest in self.applied_planned_delta_digests:
            raise ValueError("planning_delta_reapplied")
        if delta.sequence != len(self.applied_planned_delta_digests) + 1:
            raise ValueError("planning_delta_prefix_skipped")
        if delta.base_state_digest != self.state_digest:
            raise ValueError("planning_delta_wrong_prefix")
        records = {
            (
                item.record.payload_record_kind
                if isinstance(item, DurablePlanningStateRecord)
                else item.record.payload.record_kind,
                item.record.record_id,
            ): item
            for item in self.records
        }
        for mutation in delta.mutations:
            key = (mutation.record_kind, mutation.record_id)
            current = records.get(key)
            _validate_precondition(current, mutation.before)
            records[key] = PendingPlanningStateRecord(
                producing_transaction_group_id=delta.producing_transaction_group_id,
                record=mutation.after_planning_record,
            )
        values = {
            "base_snapshot_digest": self.base_snapshot_digest,
            "records": tuple(records[key] for key in sorted(records)),
            "codec_manifest_fingerprint": self.codec_manifest_fingerprint,
            "applied_planned_delta_digests": self.applied_planned_delta_digests
            + (delta.delta_digest,),
        }
        return GraphPlanningState.create(**values)

    def materialize(
        self,
        *,
        authorizing_transaction_group_id: str,
        commit_values: PlanningCommitValues,
        durable_records: tuple[SnapshotGraphRecord, ...],
    ) -> GraphPlanningState:
        supplied = {(item.payload_record_kind, item.record_id): item for item in durable_records}
        records: list[PlanningStateRecord] = []
        expected: set[tuple[GraphRecordKind, str]] = set()
        for item in self.records:
            if isinstance(item, DurablePlanningStateRecord):
                records.append(item)
                continue
            key = (item.record.payload.record_kind, item.record.record_id)
            if item.producing_transaction_group_id == authorizing_transaction_group_id:
                expected.add(key)
                durable = supplied.get(key)
                materialized_payload = _materialize_planning_payload(
                    item.record.payload,
                    commit_values=commit_values,
                    authorizing_transaction_group_id=authorizing_transaction_group_id,
                )
                if durable is None or durable.payload.model_dump(mode="python") != (
                    materialized_payload.model_dump(mode="python")
                ):
                    raise ValueError("planning_materialization_projection_mismatch")
                records.append(DurablePlanningStateRecord(record=durable))
            else:
                records.append(item)
        if set(supplied) != expected:
            raise ValueError("planning_materialization_group_scope_invalid")
        values = {
            "base_snapshot_digest": self.base_snapshot_digest,
            "records": tuple(
                sorted(
                    records,
                    key=lambda item: (
                        item.record.payload_record_kind
                        if isinstance(item, DurablePlanningStateRecord)
                        else item.record.payload.record_kind,
                        item.record.record_id,
                    ),
                )
            ),
            "codec_manifest_fingerprint": self.codec_manifest_fingerprint,
            "applied_planned_delta_digests": self.applied_planned_delta_digests,
        }
        return GraphPlanningState.create(**values)


def _validate_precondition(
    current: PlanningStateRecord | None,
    precondition: PlanningRecordPrecondition,
) -> None:
    if isinstance(precondition, AbsentPlanningPrecondition):
        valid = current is None
    elif isinstance(precondition, DurablePlanningPrecondition):
        valid = (
            isinstance(current, DurablePlanningStateRecord)
            and current.record.record_version == precondition.record_version
            and current.record.record_digest == precondition.record_digest
        )
    else:
        valid = (
            isinstance(current, PendingPlanningStateRecord)
            and current.producing_transaction_group_id
            == precondition.producing_transaction_group_id
            and current.record.record_version == precondition.record_version
            and current.record.planning_record_digest == precondition.planning_record_digest
        )
    if not valid:
        raise ValueError("planning_record_precondition_failed")


class FrozenIdentityGraphPlanningArtifact(BaseModel):
    accepted_operation_artifact: AcceptedIdentityOperationArtifact
    trusted_decision: TrustedAcceptedIdentityOperationDecision
    authority_verification: VerifiedIdentityDecisionAuthority
    compiled_transition: CompiledIdentityLineageTransition
    producer_transaction_group_id: str = Field(min_length=1)
    sealed_graph_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_replay_state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_ledger_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_state_before: GraphPlanningState
    planning_delta: GraphPlanningDelta
    planning_state_after: GraphPlanningState
    artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @property
    def operation(self):
        return self.accepted_operation_artifact.operation

    @model_validator(mode="after")
    def validate_artifact(self) -> FrozenIdentityGraphPlanningArtifact:
        group_id = self.producer_transaction_group_id
        accepted_artifact = self.accepted_operation_artifact
        decision = self.trusted_decision
        verification = self.authority_verification
        if (
            decision.operation != accepted_artifact.operation
            or decision.alias_payload != accepted_artifact.alias_payload
            or decision.sealed_operation_digest
            != accepted_artifact.sealed_operation_digest
            or decision.candidate_digest != accepted_artifact.candidate_digest
            or decision.source_analysis_digest
            != accepted_artifact.source_analysis_digest
            or decision.graph_snapshot_digest != self.sealed_graph_snapshot_digest
            or decision.graph_read_set_digest
            != graph_digest(
                b"memorii.graph-read-set-token.v1\0",
                {
                    "graph_revision": self.compiled_transition.graph_revision_before,
                    "replay_state_digest": self.graph_replay_state_digest,
                    "reference_ledger_digest": self.reference_ledger_digest,
                },
            )
            or verification.decision_digest != decision.decision_digest
            or (
                verification.sealed_operation_digest,
                verification.candidate_digest,
                verification.source_analysis_digest,
                verification.operation_fence_binding_digest,
                verification.graph_snapshot_digest,
                verification.graph_read_set_digest,
            )
            != (
                decision.sealed_operation_digest,
                decision.candidate_digest,
                decision.source_analysis_digest,
                decision.operation_fence_binding_digest,
                decision.graph_snapshot_digest,
                decision.graph_read_set_digest,
            )
            or accepted_artifact.verified_decision_digest != decision.decision_digest
            or accepted_artifact.authority_digest != verification.verification_digest
            or verification.verification_digest
            != accepted_artifact.authority_verification_digest
            or verification.authority_record_id
            != accepted_artifact.authority_record_id
            or verification.authority_record_digest
            != accepted_artifact.authority_record_digest
        ):
            raise ValueError("frozen_identity_planning_authority_binding_invalid")
        if self.compiled_transition.operation_id != self.operation.operation_id:
            raise ValueError("frozen_identity_planning_operation_binding_invalid")
        if self.compiled_transition.recorded_at is not None:
            raise ValueError("frozen_identity_planning_time_prebound")
        if self.planning_state_before.base_snapshot_digest != self.graph_snapshot_digest:
            raise ValueError("frozen_identity_planning_snapshot_binding_invalid")
        if self.planning_delta.producing_transaction_group_id != group_id:
            raise ValueError("frozen_identity_planning_group_binding_invalid")
        if (
            self.planning_state_before.apply(self.planning_delta)
            != self.planning_state_after
        ):
            raise ValueError("frozen_identity_planning_delta_binding_invalid")
        mutation_keys = tuple(
            (item.record_kind, item.record_id) for item in self.planning_delta.mutations
        )
        if not mutation_keys:
            raise ValueError("frozen_identity_planning_outputs_incomplete")
        planned_successors = {
            (item.entity_revision_id, item.logical_entity_id)
            for item in self.operation.successors
        }
        planned_output_successors = {
            (
                str(item.after_planning_record.payload.planning_record["entity_revision_id"]),
                str(item.after_planning_record.payload.planning_record["logical_entity_id"]),
            )
            for item in self.planning_delta.mutations
            if item.record_kind == "entity_revision"
            and item.mutation_kind == "create"
        }
        if planned_successors != planned_output_successors:
            raise ValueError("frozen_identity_planning_successors_mismatch")
        current_reference_ids = {
            item.reference_digest
            for item in self.compiled_transition.reverse_reference_closure
            if item.lifecycle == "current"
        }
        reprojectable = {
            entry.record_kind
            for entry in generated_reference_schema_manifest().schema_entries
            if any(
                field.lifecycle_semantics != "immutable_revision"
                for field in entry.reference_fields
            )
        }
        outputs_by_key = {
            (item.record_kind, item.record_id): item.after_planning_record.payload
            for item in self.planning_delta.mutations
        }
        for disposition in self.compiled_transition.reference_dispositions:
            if (
                disposition.reference_digest not in current_reference_ids
                or disposition.record_kind not in reprojectable
                or _reference_disposition_is_noop(disposition)
            ):
                continue
            output = outputs_by_key.get(
                (disposition.record_kind, disposition.record_id)
            )
            if output is None:
                raise ValueError("frozen_identity_planning_reprojection_missing")
        body = self.model_dump(mode="python", exclude={"artifact_digest"})
        if self.artifact_digest != graph_digest(
            b"memorii.frozen-identity-graph-planning-artifact.v1\0", body
        ):
            raise ValueError("frozen_identity_planning_artifact_digest_mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> FrozenIdentityGraphPlanningArtifact:
        return cls.model_validate(
            values
            | {
                "artifact_digest": graph_digest(
                    b"memorii.frozen-identity-graph-planning-artifact.v1\0", values
                )
            }
        )


class NonPublishingIdentityPlanningResultV3(BaseModel):
    """Pure planner output that carries its complete state transition."""

    schema_version: Literal[3]
    transaction_group_id: str = Field(min_length=1)
    sealed_graph_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_state_before_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    frozen_artifact: FrozenIdentityGraphPlanningArtifact
    planning_state_after: GraphPlanningState
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_result(self) -> NonPublishingIdentityPlanningResultV3:
        artifact = self.frozen_artifact
        if (
            artifact.producer_transaction_group_id != self.transaction_group_id
            or artifact.sealed_graph_snapshot_digest != self.sealed_graph_snapshot_digest
            or artifact.planning_state_before.state_digest
            != self.planning_state_before_digest
            or artifact.planning_state_after != self.planning_state_after
        ):
            raise ValueError("identity_nonpublishing_planning_result_binding_invalid")
        body = self.model_dump(mode="python", exclude={"result_digest"})
        if self.result_digest != graph_digest(
            b"memorii.identity-nonpublishing-planning-result.v3\0", body
        ):
            raise ValueError("identity_nonpublishing_planning_result_digest_invalid")
        return self

    @classmethod
    def create(cls, **values: object) -> NonPublishingIdentityPlanningResultV3:
        body = {"schema_version": 3, **values}
        return cls.model_validate(
            body
            | {
                "result_digest": graph_digest(
                    b"memorii.identity-nonpublishing-planning-result.v3\0", body
                )
            }
        )


def materialize_frozen_identity_graph_plan(
    artifact: FrozenIdentityGraphPlanningArtifact,
    *,
    commit_values: PlanningCommitValues,
) -> tuple[tuple[SnapshotGraphRecord, ...], GraphPlanningState]:
    """Bind one frozen plan to the authoritative transaction coordinates."""

    if (
        commit_values.transaction_group_id
        != artifact.producer_transaction_group_id
        or commit_values.graph_revision_before
        != artifact.compiled_transition.graph_revision_before
    ):
        raise ValueError("identity_planning_commit_coordinates_invalid")
    codec_by_kind = {
        item.record_kind: item
        for item in canonical_graph_codec_manifest().entries
    }
    records = tuple(
        sorted(
            (
                _snapshot_record(
                    _materialize_planning_payload(
                        mutation.after_planning_record.payload,
                        commit_values=commit_values,
                        authorizing_transaction_group_id=(
                            artifact.producer_transaction_group_id
                        ),
                    ),
                    codec_by_kind[mutation.record_kind],
                )
                for mutation in artifact.planning_delta.mutations
            ),
            key=lambda item: (item.payload_record_kind, item.record_id),
        )
    )
    state = artifact.planning_state_after.materialize(
        authorizing_transaction_group_id=artifact.producer_transaction_group_id,
        commit_values=commit_values,
        durable_records=records,
    )
    return records, state


def materialize_frozen_identity_reference_mutations(
    artifact: FrozenIdentityGraphPlanningArtifact,
    *,
    commit_values: PlanningCommitValues,
    durable_records: tuple[SnapshotGraphRecord, ...],
) -> tuple[MaterializedPlanningReferenceLedgerMutation, ...]:
    """Bind every frozen reference mutation to committed record coordinates."""

    if (
        commit_values.transaction_group_id
        != artifact.producer_transaction_group_id
        or commit_values.graph_revision_before
        != artifact.compiled_transition.graph_revision_before
    ):
        raise ValueError("identity_planning_commit_coordinates_invalid")
    durable_by_key = {
        (item.payload_record_kind, item.record_id): item
        for item in durable_records
    }
    values: list[MaterializedPlanningReferenceLedgerMutation] = []
    for mutation in artifact.planning_delta.mutations:
        durable = durable_by_key.get((mutation.record_kind, mutation.record_id))
        if durable is None:
            raise ValueError("identity_planning_reference_record_missing")
        for entry in mutation.reference_edges_removed:
            if (
                entry.commit_coordinate.transaction_group_id
                != artifact.producer_transaction_group_id
            ):
                raise ValueError("identity_planning_reference_group_mismatch")
            values.append(
                MaterializedPlanningReferenceLedgerMutation(
                    graph_revision=commit_values.graph_revision_after,
                    operation_id=entry.operation_id,
                    change=entry.change,
                    record_kind=entry.record_kind,
                    record_id=entry.record_id,
                    reference_path=entry.reference_path,
                    target=entry.target,
                    base_record_digest=entry.base_record_digest,
                )
            )
        for entry in mutation.reference_edges_added:
            if (
                entry.commit_coordinate.transaction_group_id
                != artifact.producer_transaction_group_id
            ):
                raise ValueError("identity_planning_reference_group_mismatch")
            values.append(
                MaterializedPlanningReferenceLedgerMutation(
                    graph_revision=commit_values.graph_revision_after,
                    operation_id=entry.operation_id,
                    change=entry.change,
                    record_kind=entry.record_kind,
                    record_id=entry.record_id,
                    reference_path=entry.reference_path,
                    target=entry.target,
                    base_record_digest=durable.record_digest,
                )
            )
    return tuple(values)


def build_frozen_identity_graph_planning_artifact_from_state(
    *,
    sealed_graph_snapshot,
    transaction_group_id: str,
    current_planning_state: GraphPlanningState,
    accepted_operation_artifact: AcceptedIdentityOperationArtifact,
    compiled_transition: CompiledIdentityLineageTransition,
    operation,
    candidate,
    trusted_decision: TrustedAcceptedIdentityOperationDecision,
    authority_verification: VerifiedIdentityDecisionAuthority,
) -> FrozenIdentityGraphPlanningArtifact:
    """Build one identity artifact against the caller-owned planning prefix.

    This is deliberately pure: the caller supplies the one sealed snapshot and
    the exact accumulated planning state.  In particular, this helper must not
    reacquire a snapshot or reset the state for a later operation in a group.
    """

    graph_snapshot = sealed_graph_snapshot
    if (
        not transaction_group_id
        or current_planning_state.base_snapshot_digest
        != graph_snapshot.canonical_graph.snapshot_digest
        or current_planning_state.codec_manifest_fingerprint
        != canonical_graph_codec_manifest().manifest_fingerprint
        or compiled_transition.graph_revision_before
        != graph_snapshot.graph_state.graph_revision
        or trusted_decision.operation != accepted_operation_artifact.operation
        or accepted_operation_artifact.operation.operation_id != operation.operation_id
        or operation.candidate_id != candidate.candidate_id
        or accepted_operation_artifact.candidate_digest != candidate.candidate_digest
        or trusted_decision.candidate_digest != candidate.candidate_digest
        or trusted_decision.sealed_operation_digest != operation.sealed_operation_digest
        or accepted_operation_artifact.sealed_operation_digest
        != operation.sealed_operation_digest
        or trusted_decision.graph_snapshot_digest != graph_snapshot.snapshot_digest
        or authority_verification.graph_snapshot_digest != graph_snapshot.snapshot_digest
        or trusted_decision.graph_read_set_digest != graph_snapshot.read_set.read_set_digest
        or authority_verification.graph_read_set_digest != graph_snapshot.read_set.read_set_digest
    ):
        raise ValueError("identity_nonpublishing_planning_discontinuous")

    accepted = accepted_operation_artifact.operation
    carriers = compile_accepted_carriers(
        operation=operation,
        candidate=candidate,
        identity_transition=compiled_transition,
        committed_at=compiled_transition.recorded_at,
    )
    identity_record = next(
        item for item in carriers if isinstance(item, IdentityLineageRecord)
    )
    codec_by_kind = {
        item.record_kind: item for item in canonical_graph_codec_manifest().entries
    }
    outputs: list[BaseModel] = [identity_record]
    if accepted.operation == "alias":
        alias = accepted_operation_artifact.alias_payload
        if alias is None:
            raise ValueError("identity_planning_alias_payload_missing")
        outputs.append(AliasRevision.create(
            operation_id=accepted.operation_id,
            alias_revision_id=sha256(
                (accepted.operation_id + alias.payload_digest).encode()
            ).hexdigest(),
            entity_revision_id=alias.entity_revision_id,
            logical_entity_id=alias.logical_entity_id,
            alias_namespace=alias.alias_namespace,
            normalized_alias_key=alias.normalized_alias_key,
            source_evidence=alias.source_evidence,
            record_version=1,
            codec_fingerprint=codec_by_kind["alias_revision"].codec_fingerprint,
        ))
    else:
        for reservation in accepted_operation_artifact.successor_reservations:
            planned = reservation.planned_identity
            outputs.append(EntityRevision.create(
                operation_id=accepted.operation_id,
                entity_revision_id=planned.entity_revision_id,
                logical_entity_id=planned.logical_entity_id,
                lifecycle="active",
                source_evidence=accepted.source_evidence,
                record_version=1,
                codec_fingerprint=codec_by_kind["entity_revision"].codec_fingerprint,
            ))
    outputs.extend(
        _reproject_identity_closure(
            graph_snapshot=graph_snapshot,
            compiled_transition=compiled_transition,
            operation_id=accepted.operation_id,
        )
    )
    for disposition in compiled_transition.reference_dispositions:
        outputs.append(ReferenceDispositionRecord.create(
            operation_id=accepted.operation_id,
            reference_disposition_id=disposition.disposition_digest,
            target_record_kind=disposition.record_kind,
            target_record_id=disposition.record_id,
            target_reference_path=disposition.reference_path,
            predecessor_entity_revision_id=disposition.predecessor.entity_revision_id,
            predecessor_logical_entity_id=disposition.predecessor.logical_entity_id,
            successor_entity_revision_ids=tuple(
                item.entity_revision_id for item in disposition.successors
            ),
            successor_logical_entity_ids=tuple(
                item.logical_entity_id for item in disposition.successors
            ),
            disposition=disposition.disposition,
            basis=disposition.basis,
            source_evidence=disposition.source_evidence,
            record_version=1,
            codec_fingerprint=codec_by_kind[
                "reference_disposition"
            ].codec_fingerprint,
        ))
    output_records = tuple(
        sorted(
            (
                _snapshot_record(
                    item,
                    codec_by_kind[_certified_or_validated_record_kind(item)],
                )
                for item in outputs
            ),
            key=lambda item: (item.payload_record_kind, item.record_id),
        )
    )
    before = current_planning_state
    ledger_coordinate = PlannedCommitCoordinate(
        transaction_group_id=transaction_group_id,
        coordinate="graph_revision_after",
    )
    durable_before = {
        (item.payload_record_kind, item.record_id): item
        for item in graph_snapshot.canonical_graph.records
    }
    planned_before = {
        (item.record.payload.record_kind, item.record.record_id): item
        for item in before.records
        if isinstance(item, PendingPlanningStateRecord)
    }
    mutations = []
    for durable in output_records:
        payload = _planning_payload(
            durable.payload,
            transaction_group_id=transaction_group_id,
        )
        planned = PlanningSnapshotGraphRecord.create(
            record_id=durable.record_id,
            record_version=durable.record_version,
            payload=payload,
            planning_projection_codec_fingerprint=codec_by_kind[
                durable.payload_record_kind
            ].planning_projection_codec_fingerprint,
            planning_projection_schema_fingerprint=codec_by_kind[
                durable.payload_record_kind
            ].planning_projection_schema_fingerprint,
        )
        references_added = tuple(
            sorted(
                (
                    PlanningReferenceLedgerEntry.create(
                        commit_coordinate=ledger_coordinate,
                        operation_id=transaction_group_id,
                        change="add",
                        record_kind=durable.payload_record_kind,
                        record_id=durable.record_id,
                        reference_path=path,
                        target=target,
                        base_record_digest=planned.planning_record_digest,
                    )
                    for path, target in extract_reference_edges(durable.payload)
                ),
                key=lambda item: item.planning_ledger_entry_digest,
            )
        )
        key = (durable.payload_record_kind, durable.record_id)
        prior = durable_before.get(key)
        pending_prior = planned_before.get(key)
        references_removed = (
            tuple(
                sorted(
                    (
                        PlanningReferenceLedgerEntry.create(
                            commit_coordinate=ledger_coordinate,
                            operation_id=transaction_group_id,
                            change="remove",
                            record_kind=prior.payload_record_kind,
                            record_id=prior.record_id,
                            reference_path=path,
                            target=target,
                            base_record_digest=prior.record_digest,
                        )
                        for path, target in extract_reference_edges(prior.payload)
                    ),
                    key=lambda item: item.planning_ledger_entry_digest,
                )
            )
            if prior is not None
            else ()
        )
        mutations.append(PlanningGraphRecordMutation.create(
            mutation_kind="create" if prior is None else "update",
            record_kind=durable.payload_record_kind,
            record_id=durable.record_id,
            before=(
                DurablePlanningPrecondition(
                    record_version=prior.record_version,
                    record_digest=prior.record_digest,
                )
                if prior is not None
                else PendingPlanningPrecondition(
                    producing_transaction_group_id=pending_prior.producing_transaction_group_id,
                    record_version=pending_prior.record.record_version,
                    planning_record_digest=pending_prior.record.planning_record_digest,
                )
                if pending_prior is not None
                else AbsentPlanningPrecondition()
            ),
            after_planning_record=planned,
            reference_edges_removed=references_removed,
            reference_edges_added=references_added,
        ))
    delta = GraphPlanningDelta.create(
        sequence=len(before.applied_planned_delta_digests) + 1,
        base_state_digest=before.state_digest,
        producing_transaction_group_id=transaction_group_id,
        mutations=tuple(
            sorted(mutations, key=lambda item: (item.record_kind, item.record_id))
        ),
    )
    after = before.apply(delta)
    return FrozenIdentityGraphPlanningArtifact.create(
        accepted_operation_artifact=accepted_operation_artifact,
        trusted_decision=trusted_decision,
        authority_verification=authority_verification,
        compiled_transition=compiled_transition,
        producer_transaction_group_id=transaction_group_id,
        sealed_graph_snapshot_digest=graph_snapshot.snapshot_digest,
        graph_snapshot_digest=graph_snapshot.canonical_graph.snapshot_digest,
        graph_replay_state_digest=graph_snapshot.graph_state.state_digest,
        reference_ledger_digest=graph_snapshot.reference_integrity.ledger_digest,
        planning_state_before=before,
        planning_delta=delta,
        planning_state_after=after,
    )


def _reproject_identity_closure(
    *,
    graph_snapshot,
    compiled_transition: CompiledIdentityLineageTransition,
    operation_id: str,
) -> tuple[BaseModel, ...]:
    """Produce one versioned after-record for each mutable current projection."""

    current_references = {
        item.reference_digest: item
        for item in compiled_transition.reverse_reference_closure
        if item.lifecycle == "current"
    }
    dispositions_by_record: dict[
        tuple[str, str], list[LineageReferenceDisposition]
    ] = {}
    for disposition in compiled_transition.reference_dispositions:
        if disposition.reference_digest not in current_references:
            continue
        dispositions_by_record.setdefault(
            (disposition.record_kind, disposition.record_id), []
        ).append(disposition)
    materialized = {
        (item.record_kind, item.record_id): item
        for item in graph_snapshot.graph_state.materialized_records
    }
    outputs: list[BaseModel] = []
    annotations = {
        (entry.record_kind, field.reference_path): field
        for entry in generated_reference_schema_manifest().schema_entries
        for field in entry.reference_fields
    }
    for key in sorted(dispositions_by_record):
        source = materialized.get(key)
        if source is None or source.record_digest not in {
            current_references[item.reference_digest].base_record_digest
            for item in dispositions_by_record[key]
        }:
            raise ValueError("identity_planning_closure_record_stale")
        record = source.record
        values = record.model_dump(mode="python")
        changed = False
        for item in dispositions_by_record[key]:
            annotation = annotations.get((item.record_kind, item.reference_path))
            if annotation is None:
                raise ValueError("identity_planning_projection_path_unregistered")
            if annotation.lifecycle_semantics == "immutable_revision":
                continue
            successors = item.successors
            if len(successors) != 1:
                raise ValueError("identity_planning_projection_requires_one_successor")
            successor = successors[0]
            replacement = (
                successor.entity_revision_id
                if annotation.target_kind == "entity_revision"
                else successor.logical_entity_id
            )
            predecessor = (
                item.predecessor.entity_revision_id
                if annotation.target_kind == "entity_revision"
                else item.predecessor.logical_entity_id
            )
            if replacement == predecessor:
                continue
            _replace_reference_path(
                values,
                item.reference_path,
                predecessor=predecessor,
                replacement=replacement,
            )
            changed = True
        if changed:
            outputs.append(
                _rebuild_reprojected_record(
                    record=record, values=values, operation_id=operation_id
                )
            )
    return tuple(outputs)


def _reference_target_kind(
    record_kind: GraphRecordKind, reference_path: str
) -> Literal["entity_revision", "logical_entity"]:
    matches = tuple(
        field.target_kind
        for entry in generated_reference_schema_manifest().schema_entries
        if entry.record_kind == record_kind
        for field in entry.reference_fields
        if field.reference_path == reference_path
    )
    if len(matches) != 1:
        raise ValueError("identity_planning_projection_path_unregistered")
    target_kind = matches[0]
    if target_kind not in ("entity_revision", "logical_entity"):
        raise ValueError("identity_planning_projection_target_invalid")
    return target_kind


def _reference_disposition_is_noop(
    disposition: LineageReferenceDisposition,
) -> bool:
    if len(disposition.successors) != 1:
        return False
    target_kind = _reference_target_kind(
        disposition.record_kind, disposition.reference_path
    )
    successor = disposition.successors[0]
    if target_kind == "entity_revision":
        return (
            successor.entity_revision_id
            == disposition.predecessor.entity_revision_id
        )
    return successor.logical_entity_id == disposition.predecessor.logical_entity_id


def _replace_reference_path(
    values: dict[str, object],
    reference_path: str,
    *,
    predecessor: str,
    replacement: str,
) -> None:
    parts = tuple(
        part
        for part in reference_path.removeprefix("/").replace("/", ".").split(".")
        if part
    )

    def replace(container: object, index: int) -> int:
        part = parts[index]
        repeated = part.endswith("[]")
        name = part.removesuffix("[]")
        if not isinstance(container, dict) or name not in container:
            return 0
        value = container[name]
        if index == len(parts) - 1:
            if repeated:
                if not isinstance(value, (tuple, list)):
                    return 0
                updated = [replacement if item == predecessor else item for item in value]
                count = sum(item == predecessor for item in value)
                container[name] = tuple(updated) if isinstance(value, tuple) else updated
                return count
            if value != predecessor:
                return 0
            container[name] = replacement
            return 1
        if repeated:
            if not isinstance(value, (tuple, list)):
                return 0
            return sum(replace(item, index + 1) for item in value)
        return replace(value, index + 1)

    if replace(values, 0) != 1:
        raise ValueError("identity_planning_projection_path_value_mismatch")


def _rebuild_reprojected_record(
    *, record: BaseModel, values: dict[str, object], operation_id: str
) -> BaseModel:
    values["operation_id"] = operation_id
    record_version = getattr(record, "record_version", None)
    if not isinstance(record_version, int):
        raise ValueError("identity_planning_projection_record_version_invalid")
    values["record_version"] = record_version + 1
    values.pop("record_digest", None)
    if isinstance(record, ClaimAssertion):
        claim_identity = values.get("claim_identity")
        if isinstance(claim_identity, dict):
            key = claim_identity.get("assertion_key_at_recording")
            subject = claim_identity.get("subject_assertion_ref")
            object_ref = claim_identity.get("object_assertion_ref")
            if isinstance(key, dict):
                slot = key.get("slot")
                value = key.get("value")
                if isinstance(slot, dict) and isinstance(subject, dict):
                    subject["logical_entity_id_at_assertion"] = slot.get(
                        "subject_logical_entity_id"
                    )
                if isinstance(value, dict) and isinstance(object_ref, dict):
                    object_ref["logical_entity_id_at_assertion"] = value.get(
                        "object_logical_entity_id"
                    )
    if isinstance(record, IdentityLineageRecord):
        transition_raw = values.get("transition")
        if not isinstance(transition_raw, dict):
            raise ValueError("identity_planning_projection_transition_invalid")
        transition_values = dict(transition_raw)
        transition_values.pop("transition_digest", None)
        transition = CompiledIdentityLineageTransition.create(**transition_values)
        values["transition"] = transition
        values["statement_digest"] = transition.transition_digest
    if isinstance(
        record,
        (ClaimAssertion, ActionRevision, IdentityLineageRecord, TemporalTransitionRecord),
    ):
        temporal = type(record).model_validate(
            values
            | {
                "record_digest": contract_digest(
                    b"memorii.semantic-ingestion.temporal-carrier.v1", values
                )
            }
        )
        record_certified_instance(temporal)
        return temporal
    values["record_digest"] = graph_digest(
        b"memorii.canonical-graph-record.v1\0", values
    )
    return validated_graph_record(values)


def _certified_or_validated_record_kind(record: BaseModel) -> str:
    certified_kind = certified_graph_record_kind(record)
    if certified_kind is not None:
        return certified_kind
    return canonical_graph_record_adapter().validate_python(
        record.model_dump(mode="python")
    ).record_kind


def _snapshot_record(record: BaseModel, codec) -> SnapshotGraphRecord:
    if (
        certified_instance(record)
        and deeply_immutable_type(type(record))
        and graph_record_union_member(record)
    ):
        payload = record
    else:
        payload = validated_graph_record(record.model_dump(mode="python"))
    return SnapshotGraphRecord(
        record_id=graph_record_id(payload),
        record_version=payload.record_version,
        payload=payload,
        codec_fingerprint=codec.codec_fingerprint,
        persistence_schema_fingerprint=codec.payload_schema_fingerprint,
        record_digest=payload.record_digest,
    )


def _planning_record_id(payload: _PlanningPayload) -> str:
    names = {
        "entity_revision": "entity_revision_id",
        "alias_revision": "alias_revision_id",
        "type_evidence": "evidence_id",
        "claim_assertion": "claim_assertion_id",
        "claim_projection": "claim_projection_id",
        "relation_revision": "relation_revision_id",
        "action_revision": "action_revision_id",
        "citation": "citation_id",
        "provenance": "provenance_id",
        "temporal_transition": "transition_id",
        "identity_lineage": "identity_lineage_id",
        "reference_disposition": "reference_disposition_id",
    }
    value = payload.planning_record.get(names[payload.record_kind])
    if not isinstance(value, str) or not value:
        raise ValueError("planning_record_identity_invalid")
    return value


def _planning_coordinates(
    payload: _PlanningPayload,
) -> tuple[PlannedCommitCoordinate, ...]:
    coordinates: list[PlannedCommitCoordinate] = []

    def walk(value: object) -> None:
        if isinstance(value, dict):
            if value.get("kind") == "transaction_commit_coordinate":
                coordinates.append(PlannedCommitCoordinate.model_validate(value))
                return
            for item in value.values():
                walk(item)
        elif isinstance(value, (tuple, list)):
            for item in value:
                walk(item)

    walk(payload.planning_record)
    return tuple(coordinates)


def _replace_planning_path(
    values: dict[str, object], path: str, replacement: object
) -> None:
    parts = path.split(".")
    container = values
    for part in parts[:-1]:
        nested = container.get(part)
        if not isinstance(nested, dict):
            raise ValueError("planning_coordinate_path_invalid")
        container = nested
    if parts[-1] not in container:
        raise ValueError("planning_coordinate_path_invalid")
    container[parts[-1]] = replacement


def _materialize_planning_payload(
    payload: _PlanningPayload,
    *,
    commit_values: PlanningCommitValues,
    authorizing_transaction_group_id: str,
) -> CanonicalGraphRecord:
    if commit_values.transaction_group_id != authorizing_transaction_group_id:
        raise ValueError("planning_commit_group_mismatch")
    values = deepcopy(payload.planning_record)
    manifest = {
        item.record_kind: item for item in canonical_graph_codec_manifest().entries
    }
    for path, coordinate_name in manifest[payload.record_kind].transaction_owned_fields:
        container = values
        parts = path.split(".")
        for part in parts[:-1]:
            nested = container.get(part)
            if not isinstance(nested, dict):
                raise ValueError("planning_coordinate_path_invalid")
            container = nested
        coordinate = PlannedCommitCoordinate.model_validate(container.get(parts[-1]))
        if (
            coordinate.transaction_group_id != authorizing_transaction_group_id
            or coordinate.coordinate != coordinate_name
        ):
            raise ValueError("planning_coordinate_authority_mismatch")
        replacement: object = getattr(commit_values, coordinate_name)
        if path == "system_interval":
            replacement = {"start": commit_values.committed_at, "end": None}
        container[parts[-1]] = replacement
    if payload.record_kind == "identity_lineage":
        transition_raw = values.get("transition")
        if not isinstance(transition_raw, dict):
            raise ValueError("planning_identity_transition_invalid")
        transition_values = dict(transition_raw)
        transition_values.pop("transition_digest", None)
        transition = CompiledIdentityLineageTransition.create(**transition_values)
        values["transition"] = transition
        values["statement_digest"] = transition.transition_digest
    if payload.record_kind in {
        "claim_assertion",
        "action_revision",
        "identity_lineage",
        "temporal_transition",
    }:
        values["record_digest"] = contract_digest(
            b"memorii.semantic-ingestion.temporal-carrier.v1", values
        )
    else:
        values["record_digest"] = graph_digest(
            b"memorii.canonical-graph-record.v1\0", values
        )
    return validated_graph_record(values)


def materialize_canonical_planning_payload(
    payload: CanonicalPlanningRecordPayload,
    *,
    commit_values: PlanningCommitValues,
    authorizing_transaction_group_id: str,
) -> CanonicalGraphRecord:
    """Materialize one validated native planning payload at store commit time."""
    return _materialize_planning_payload(
        payload,
        commit_values=commit_values,
        authorizing_transaction_group_id=authorizing_transaction_group_id,
    )


def _planning_payload(record: BaseModel, *, transaction_group_id: str):
    classes = {
        "entity_revision": PlanningEntityRevision,
        "alias_revision": PlanningAliasRevision,
        "type_evidence": PlanningTypeEvidence,
        "claim_assertion": PlanningClaimAssertion,
        "claim_projection": PlanningClaimProjection,
        "relation_revision": PlanningRelationRevision,
        "action_revision": PlanningActionRevision,
        "citation": PlanningCitation,
        "provenance": PlanningProvenance,
        "temporal_transition": PlanningTemporalTransition,
        "identity_lineage": PlanningIdentityLineage,
        "reference_disposition": PlanningReferenceDisposition,
    }
    kind: object = certified_graph_record_kind(record)
    if kind is None:
        kind = record.model_dump(mode="python").get("record_kind")
    if not isinstance(kind, str):
        raise ValueError("identity_planning_output_kind_invalid")
    cls = classes.get(kind)
    if cls is None:
        raise ValueError("identity_planning_output_kind_invalid")
    values = record.model_dump(mode="python", exclude={"record_digest"})
    manifest = {
        item.record_kind: item for item in canonical_graph_codec_manifest().entries
    }
    for path, coordinate_name in manifest[kind].transaction_owned_fields:
        _replace_planning_path(
            values,
            path,
            PlannedCommitCoordinate(
                transaction_group_id=transaction_group_id,
                coordinate=coordinate_name,
            ).model_dump(mode="python"),
        )
    return cls(planning_record=values)


def canonical_planning_payload_from_record(
    record: BaseModel, *, transaction_group_id: str,
) -> CanonicalPlanningRecordPayload:
    """Project a durable record into its validated pre-CAS planning payload."""
    return _planning_payload(record, transaction_group_id=transaction_group_id)


__all__ = [
    "AbsentPlanningPrecondition",
    "CanonicalPlanningRecordPayload",
    "DurablePlanningPrecondition",
    "DurablePlanningStateRecord",
    "GraphPlanningDelta",
    "GraphPlanningState",
    "FrozenIdentityGraphPlanningArtifact",
    "NonPublishingIdentityPlanningResultV3",
    "build_frozen_identity_graph_planning_artifact_from_state",
    "canonical_planning_payload_from_record",
    "materialize_canonical_planning_payload",
    "PendingPlanningPrecondition",
    "PendingPlanningStateRecord",
    "PlannedCommitCoordinate",
    "PlanningCommitValues",
    "PlanningGraphRecordMutation",
    "PlanningReferenceLedgerEntry",
    "PlanningSnapshotGraphRecord",
    "PlanningStateRecord",
]
