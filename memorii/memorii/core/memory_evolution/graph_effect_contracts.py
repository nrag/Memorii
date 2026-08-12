"""Strict graph and observation effects for graph-dependent ingestion.

This leaf intentionally has no store, coordinator, or replay dependency.  It
binds graph/observation effects to already-issued semantic-ingestion authority
without making either side import the other's runtime owner.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

if TYPE_CHECKING:
    from memorii.core.memory_evolution.graph_records import GraphRecordKind, SnapshotGraphRecord
    from memorii.core.memory_evolution.reference_integrity import ReferenceEdgeLedgerEntry
    from memorii.core.semantic_ingestion.contracts import (
        GovernanceCarrierArtifact,
        MessageAdmissionCarrierSet,
        MessageAdmissionIdentity,
        RequiredOutcomeScopeSet,
        SegmentGovernanceBinding,
        SegmentGovernanceCarrierSet,
    )

_DIGEST = r"^[0-9a-f]{64}$"


def _contract_digest(domain: bytes, value: object) -> str:
    """Late import keeps this leaf usable while semantic contracts initialize."""
    from memorii.core.semantic_ingestion.contracts import contract_digest

    return contract_digest(domain, value)


class _Addressed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @classmethod
    def create(cls, **values: object):  # type: ignore[no-untyped-def]
        if not cls.__pydantic_complete__:
            rebuild_graph_effect_contracts()
        digest_field = cls.__private_attributes__["_digest_field"].default
        domain = cls.__private_attributes__["_digest_domain"].default
        return cls(**values, **{digest_field: _contract_digest(domain, values)})


class GraphRecordMutation(_Addressed):
    mutation_kind: Literal["create", "update"]
    record_kind: GraphRecordKind
    record_id: str = Field(min_length=1)
    before_record_version: int | None = Field(default=None, ge=1)
    before_digest: str | None = Field(default=None, pattern=_DIGEST)
    after_record_version: int = Field(ge=1)
    after_digest: str = Field(pattern=_DIGEST)
    after_record: SnapshotGraphRecord
    reference_edges_added: tuple[ReferenceEdgeLedgerEntry, ...]
    reference_edges_removed: tuple[ReferenceEdgeLedgerEntry, ...]
    mutation_digest: str = Field(pattern=_DIGEST)
    _digest_domain = b"memorii.semantic-ingestion.graph-record-mutation.v1"
    _digest_field = "mutation_digest"

    @model_validator(mode="after")
    def validate_mutation(self) -> GraphRecordMutation:
        if (
            self.after_record.record_id != self.record_id
            or self.after_record.record_version != self.after_record_version
            or self.after_record.record_digest != self.after_digest
            or (self.mutation_kind == "create") != (
                self.before_record_version is None and self.before_digest is None
            )
            or (self.mutation_kind == "update") != (
                self.before_record_version is not None and self.before_digest is not None
            )
            or self.reference_edges_added != tuple(sorted(self.reference_edges_added, key=lambda item: item.ledger_entry_digest))
            or self.reference_edges_removed != tuple(sorted(self.reference_edges_removed, key=lambda item: item.ledger_entry_digest))
            or self.mutation_digest != _contract_digest(
                self._digest_domain, self.model_dump(mode="python", exclude={"mutation_digest"})
            )
        ):
            raise ValueError("graph record mutation closure is invalid")
        return self


GraphRecordChange: TypeAlias = GraphRecordMutation


class GraphRevisionDelta(_Addressed):
    graph_revision_delta_id: str = Field(min_length=1)
    graph_revision_before: str = Field(min_length=1)
    graph_revision_after: str = Field(min_length=1)
    source_ids: tuple[str, ...]
    operation_ids: tuple[str, ...]
    transaction_group_id: str = Field(min_length=1)
    segment_governance_bindings: tuple[SegmentGovernanceBinding, ...]
    message_admission_identities: tuple[MessageAdmissionIdentity, ...]
    governance_carrier_artifact: GovernanceCarrierArtifact
    record_changes: tuple[GraphRecordChange, ...]
    read_set_digest: str = Field(pattern=_DIGEST)
    write_set_digest: str = Field(pattern=_DIGEST)
    delta_digest: str = Field(pattern=_DIGEST)
    _digest_domain = b"memorii.semantic-ingestion.graph-revision-delta.v1"
    _digest_field = "delta_digest"

    @model_validator(mode="after")
    def validate_delta(self) -> GraphRevisionDelta:
        if (
            not self.source_ids or not self.operation_ids or not self.record_changes
            or self.source_ids != tuple(sorted(set(self.source_ids)))
            or self.operation_ids != tuple(sorted(set(self.operation_ids)))
            or self.segment_governance_bindings
            != tuple(sorted(self.segment_governance_bindings, key=lambda item: item.binding_digest))
            or self.message_admission_identities
            != tuple(sorted(self.message_admission_identities, key=lambda item: item.message_admission_key_digest))
            or self.record_changes
            != tuple(sorted(self.record_changes, key=lambda item: (item.record_kind, item.record_id, item.mutation_digest)))
            or any(binding.source_id not in self.source_ids for binding in self.segment_governance_bindings)
            or any(
                identity.segment_governance_binding_digest
                not in {item.binding_digest for item in self.segment_governance_bindings}
                for identity in self.message_admission_identities
            )
            or self.delta_digest != _contract_digest(
                self._digest_domain, self.model_dump(mode="python", exclude={"delta_digest"})
            )
        ):
            raise ValueError("graph revision delta closure is invalid")
        return self


class CanonicalSourceTerminalOutcomeCore(_Addressed):
    """Stable terminal-outcome fields that precede its derived identifiers."""

    ingestion_record_kind: Literal["source_terminal_outcome"]
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=_DIGEST)
    delivery_principal_binding_digest: str = Field(pattern=_DIGEST)
    delivery_key_digest: str = Field(pattern=_DIGEST)
    segment_governance_carriers: SegmentGovernanceCarrierSet
    message_admission_carriers: MessageAdmissionCarrierSet
    governance_carrier_artifact: GovernanceCarrierArtifact
    required_outcome_scopes: RequiredOutcomeScopeSet
    operation_fence_id: str = Field(min_length=1)
    operation_ids: tuple[str, ...]
    final_status: Literal["fully_committed", "partially_committed", "evidence_only", "rejected", "unresolved", "failed"]
    group_result_digests: tuple[str, ...]
    core_digest: str = Field(pattern=_DIGEST)
    _digest_domain = b"memorii.semantic-ingestion.canonical-source-terminal-outcome-core.v1"
    _digest_field = "core_digest"

    @model_validator(mode="after")
    def validate_core(self) -> CanonicalSourceTerminalOutcomeCore:
        if (
            self.segment_governance_carriers.source_id != self.source_id
            or self.message_admission_carriers.source_id != self.source_id
            or self.governance_carrier_artifact.segment_governance != self.segment_governance_carriers
            or self.governance_carrier_artifact.message_admissions != self.message_admission_carriers
            or self.governance_carrier_artifact.required_outcome_scopes != self.required_outcome_scopes
            or self.operation_ids != tuple(sorted(set(self.operation_ids)))
            # Graph terminals retain final-plan order; generic evidence-only
            # outcomes may legitimately have no graph group results.
            or (
                bool(self.group_result_digests)
                and len(set(self.group_result_digests)) != len(self.group_result_digests)
            )
            or self.core_digest != _contract_digest(
                self._digest_domain, self.model_dump(mode="python", exclude={"core_digest"})
            )
        ):
            raise ValueError("canonical source terminal outcome core is invalid")
        return self


class CanonicalSourceTerminalOutcomeRecord(_Addressed):
    """Completed terminal outcome derived in core -> ID -> source -> record order."""

    core: CanonicalSourceTerminalOutcomeCore
    ingestion_record_kind: Literal["source_terminal_outcome"]
    outcome_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=_DIGEST)
    delivery_principal_binding_digest: str = Field(pattern=_DIGEST)
    delivery_key_digest: str = Field(pattern=_DIGEST)
    segment_governance_carriers: SegmentGovernanceCarrierSet
    message_admission_carriers: MessageAdmissionCarrierSet
    governance_carrier_artifact: GovernanceCarrierArtifact
    required_outcome_scopes: RequiredOutcomeScopeSet
    operation_fence_id: str = Field(min_length=1)
    operation_ids: tuple[str, ...]
    final_status: Literal["fully_committed", "partially_committed", "evidence_only", "rejected", "unresolved", "failed"]
    group_result_digests: tuple[str, ...]
    source_result_digest: str = Field(pattern=_DIGEST)
    record_digest: str = Field(pattern=_DIGEST)
    _digest_domain = b"memorii.semantic-ingestion.canonical-source-terminal-outcome-record.v1"
    _digest_field = "record_digest"

    @classmethod
    def create(
        cls, *, core: CanonicalSourceTerminalOutcomeCore,
        preparation_fingerprint: str,
    ) -> CanonicalSourceTerminalOutcomeRecord:
        """Complete the required core -> ID -> source-result -> record sequence."""
        outcome_id = _contract_digest(
            b"memorii.semantic-ingestion.bootstrap-graph-source-outcome-id.v3",
            {
                "source_id": core.source_id,
                "source_digest": core.source_digest,
                "preparation_fingerprint": preparation_fingerprint,
                "operation_ids": core.operation_ids,
                "operation_fence_id": core.operation_fence_id,
                "core_digest": core.core_digest,
            },
        )
        body = {
            "core": core,
            "ingestion_record_kind": core.ingestion_record_kind,
            "outcome_id": outcome_id,
            "source_id": core.source_id,
            "source_digest": core.source_digest,
            "delivery_principal_binding_digest": core.delivery_principal_binding_digest,
            "delivery_key_digest": core.delivery_key_digest,
            "segment_governance_carriers": core.segment_governance_carriers,
            "message_admission_carriers": core.message_admission_carriers,
            "governance_carrier_artifact": core.governance_carrier_artifact,
            "required_outcome_scopes": core.required_outcome_scopes,
            "operation_fence_id": core.operation_fence_id,
            "operation_ids": core.operation_ids,
            "final_status": core.final_status,
            "group_result_digests": core.group_result_digests,
        }
        source_result_digest = _contract_digest(
            b"memorii.semantic-ingestion.bootstrap-graph-source-result.v3", body
        )
        completed = {**body, "source_result_digest": source_result_digest}
        return cls(
            **completed,
            record_digest=_contract_digest(
                cls.__private_attributes__["_digest_domain"].default, completed
            ),
        )

    @model_validator(mode="after")
    def validate_record(self) -> CanonicalSourceTerminalOutcomeRecord:
        if (
            self.ingestion_record_kind != self.core.ingestion_record_kind
            or self.source_id != self.core.source_id
            or self.source_digest != self.core.source_digest
            or self.delivery_principal_binding_digest != self.core.delivery_principal_binding_digest
            or self.delivery_key_digest != self.core.delivery_key_digest
            or self.segment_governance_carriers != self.core.segment_governance_carriers
            or self.message_admission_carriers != self.core.message_admission_carriers
            or self.governance_carrier_artifact != self.core.governance_carrier_artifact
            or self.required_outcome_scopes != self.core.required_outcome_scopes
            or self.operation_fence_id != self.core.operation_fence_id
            or self.operation_ids != self.core.operation_ids
            or self.final_status != self.core.final_status
            or self.group_result_digests != self.core.group_result_digests
            or self.record_digest != _contract_digest(
                self._digest_domain, self.model_dump(mode="python", exclude={"record_digest"})
            )
        ):
            raise ValueError("canonical source terminal outcome closure is invalid")
        return self


CanonicalIngestionObservationRecord: TypeAlias = CanonicalSourceTerminalOutcomeRecord


class IngestionObservationRecordMutation(_Addressed):
    mutation_kind: Literal["create"]
    ingestion_record_kind: Literal["source_terminal_outcome"]
    record_id: str = Field(min_length=1)
    record_version: Literal[1]
    record: CanonicalIngestionObservationRecord
    record_digest: str = Field(pattern=_DIGEST)
    mutation_digest: str = Field(pattern=_DIGEST)
    _digest_domain = b"memorii.semantic-ingestion.ingestion-observation-record-mutation.v1"
    _digest_field = "mutation_digest"

    @model_validator(mode="after")
    def validate_mutation(self) -> IngestionObservationRecordMutation:
        if (
            self.record_id != self.record.outcome_id
            or self.record_digest != self.record.record_digest
            or self.mutation_digest != _contract_digest(
                self._digest_domain, self.model_dump(mode="python", exclude={"mutation_digest"})
            )
        ):
            raise ValueError("ingestion observation record mutation closure is invalid")
        return self


class IngestionObservationDelta(_Addressed):
    kind: Literal["terminal_group"]
    observation_delta_id: str = Field(min_length=1)
    observation_revision_before: str = Field(min_length=1)
    observation_revision_after: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=_DIGEST)
    segment_governance_bindings: tuple[SegmentGovernanceBinding, ...]
    message_admission_identities: tuple[MessageAdmissionIdentity, ...]
    governance_carrier_artifact: GovernanceCarrierArtifact
    operation_fence_id: str = Field(min_length=1)
    transaction_group_id: str = Field(min_length=1)
    operation_ids: tuple[str, ...]
    terminal_status: Literal["committed", "evidence_only", "rejected", "unresolved", "failed"]
    graph_revision_delta_digest: str | None = Field(default=None, pattern=_DIGEST)
    observation_schema_fingerprint: str = Field(pattern=_DIGEST)
    record_mutations: tuple[IngestionObservationRecordMutation, ...]
    delta_digest: str = Field(pattern=_DIGEST)
    _digest_domain = b"memorii.semantic-ingestion.ingestion-observation-delta.v1"
    _digest_field = "delta_digest"

    @model_validator(mode="after")
    def validate_delta(self) -> IngestionObservationDelta:
        if (
            not self.operation_ids or not self.record_mutations
            or self.operation_ids != tuple(sorted(set(self.operation_ids)))
            or self.segment_governance_bindings
            != tuple(sorted(self.segment_governance_bindings, key=lambda item: item.binding_digest))
            or self.message_admission_identities
            != tuple(sorted(self.message_admission_identities, key=lambda item: item.message_admission_key_digest))
            or (self.terminal_status == "committed") != (self.graph_revision_delta_digest is not None)
            or self.delta_digest != _contract_digest(
                self._digest_domain, self.model_dump(mode="python", exclude={"delta_digest"})
            )
        ):
            raise ValueError("ingestion observation delta closure is invalid")
        return self


GraphEffectCodec = TypeAdapter(
    Annotated[
        GraphRevisionDelta | CanonicalSourceTerminalOutcomeRecord | IngestionObservationDelta,
        Field(discriminator=None),
    ]
)


def rebuild_graph_effect_contracts() -> None:
    """Resolve concrete shared owners after both dependency leaves are loaded."""
    from memorii.core.memory_evolution.graph_records import GraphRecordKind, SnapshotGraphRecord
    from memorii.core.memory_evolution.reference_integrity import ReferenceEdgeLedgerEntry
    from memorii.core.semantic_ingestion.contracts import (
        GovernanceCarrierArtifact,
        MessageAdmissionCarrierSet,
        MessageAdmissionIdentity,
        RequiredOutcomeScopeSet,
        SegmentGovernanceBinding,
        SegmentGovernanceCarrierSet,
    )

    namespace = {
        "GraphRecordKind": GraphRecordKind,
        "SnapshotGraphRecord": SnapshotGraphRecord,
        "ReferenceEdgeLedgerEntry": ReferenceEdgeLedgerEntry,
        "GovernanceCarrierArtifact": GovernanceCarrierArtifact,
        "MessageAdmissionCarrierSet": MessageAdmissionCarrierSet,
        "MessageAdmissionIdentity": MessageAdmissionIdentity,
        "RequiredOutcomeScopeSet": RequiredOutcomeScopeSet,
        "SegmentGovernanceBinding": SegmentGovernanceBinding,
        "SegmentGovernanceCarrierSet": SegmentGovernanceCarrierSet,
    }
    for model in (
        GraphRecordMutation,
        GraphRevisionDelta,
        CanonicalSourceTerminalOutcomeCore,
        CanonicalSourceTerminalOutcomeRecord,
        IngestionObservationRecordMutation,
        IngestionObservationDelta,
    ):
        model.model_rebuild(_types_namespace=namespace)


__all__ = [
    "CanonicalIngestionObservationRecord",
    "CanonicalSourceTerminalOutcomeCore",
    "CanonicalSourceTerminalOutcomeRecord",
    "GraphEffectCodec",
    "GraphRecordChange",
    "GraphRecordMutation",
    "GraphRevisionDelta",
    "IngestionObservationDelta",
    "IngestionObservationRecordMutation",
    "rebuild_graph_effect_contracts",
]
