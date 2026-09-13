"""Assemble native observation deltas from already-authorized group effects.

This module deliberately does not derive provenance, record identifiers, or
graph-delta identities.  Those values are owned by the bootstrap planner and
the store's graph-delta materialization at the commit boundary.
"""

from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from memorii.core.memory_evolution.graph_effect_contracts import (
    CanonicalOperationIntroductionRecord,
    CanonicalOperationTerminalOutcomeRecord,
    CanonicalSourceIntroductionRecord,
    CanonicalSourceTerminalOutcomeRecord,
    GraphRevisionDelta,
    IngestionObservationDelta,
    IngestionObservationRecordMutation,
    SourceFinalizationObservationDelta,
)
from memorii.core.memory_evolution.graph_records import (
    graph_record_id,
    graph_record_union_member,
)
from memorii.core.semantic_ingestion.contracts import (
    BootstrapGraphGroupCommitRequestV3,
    contract_digest,
)

if TYPE_CHECKING:
    from memorii.core.semantic_ingestion.contracts import (
        GovernanceCarrierArtifact,
        MessageAdmissionIdentity,
        SegmentGovernanceBinding,
    )


class ObservationPersistenceError(ValueError):
    """Raised when a native observation cannot be tied to one group commit."""


def source_finalization_observation_delta_id(
    *, operation_fence_id: str, canonical_source_result_digest: str,
) -> str:
    """Server-owned, CTV-framed identity for one terminal source result."""
    return contract_digest(
        b"memorii.semantic-ingestion.source-finalization-observation-id.v1\0",
        {
            "operation_fence_id": operation_fence_id,
            "canonical_source_result_digest": canonical_source_result_digest,
        },
    )


def source_finalization_observation_revision(
    *, observation_revision_before: str, canonical_source_result_digest: str,
) -> str:
    """Derive the source-only successor from its CAS predecessor and result."""
    return sha256(
        b"memorii.semantic-ingestion.bootstrap-graph-source-finalization-observation-revision.v3\0"
        + observation_revision_before.encode()
        + b"\0"
        + canonical_source_result_digest.encode()
    ).hexdigest()


def source_finalization_observation_schema_fingerprint() -> str:
    """Bind the persisted delta to the actual frozen payload schema."""
    return contract_digest(
        b"memorii.observation-payload-schema.v1\0",
        SourceFinalizationObservationDelta.model_json_schema(),
    )


def build_terminal_group_observation_delta(
    *,
    request: BootstrapGraphGroupCommitRequestV3,
    materialized_graph_records: tuple[BaseModel, ...],
    source_introductions: tuple[CanonicalSourceIntroductionRecord, ...],
    operation_introductions: tuple[CanonicalOperationIntroductionRecord, ...],
    operation_terminal_outcomes: tuple[CanonicalOperationTerminalOutcomeRecord, ...],
    graph_revision_delta: GraphRevisionDelta | None,
    observation_delta_id: str,
    observation_revision_before: str,
    observation_revision_after: str,
    observation_schema_fingerprint: str,
    segment_governance_bindings: tuple[SegmentGovernanceBinding, ...],
    message_admission_identities: tuple[MessageAdmissionIdentity, ...],
    governance_carrier_artifact: GovernanceCarrierArtifact,
    terminal_status: Literal["committed", "evidence_only", "rejected", "unresolved", "failed"],
) -> IngestionObservationDelta:
    """Build one group delta after all record authorities have been materialized.

    The request supplies only group coordinates.  The caller must supply
    canonical records created from the retained planner and admission
    authorities; this prevents a persistence layer from manufacturing missing
    source spans, provenance, or identifier coordinates.
    """
    source_id = request.source_plan_lineage_entry.source_id
    source_digest = request.source_plan_lineage_entry.source_digest
    operation_ids = request.operation_ids
    operation_fence_id = request.operation_fence_binding.operation_fence_id

    if not operation_ids or request.transaction_group_id != request.group_plan_member.transaction_group_id:
        raise ObservationPersistenceError("group request coordinates are incomplete")
    if tuple(item.operation_id for item in operation_introductions) != operation_ids:
        raise ObservationPersistenceError("operation introductions do not close the group")
    if tuple(item.operation_id for item in operation_terminal_outcomes) != operation_ids:
        raise ObservationPersistenceError("operation terminal outcomes do not close the group")
    if any(record.operation_id not in operation_ids for record in source_introductions):
        raise ObservationPersistenceError("source introduction is outside the group")

    records = (
        *source_introductions,
        *operation_introductions,
        *operation_terminal_outcomes,
    )
    if any(
        record.source_id != source_id
        or record.source_digest != source_digest
        or record.operation_fence_id != operation_fence_id
        or record.delivery_principal_binding_digest != request.operation_fence_binding.delivery_principal_binding_digest
        or record.delivery_key_digest != request.operation_fence_binding.delivery_key_digest
        or record.governance_carrier_artifact != governance_carrier_artifact
        for record in records
    ):
        raise ObservationPersistenceError("observation record authority is substituted")
    if any(
        record.transaction_group_id != request.transaction_group_id
        or any(binding not in segment_governance_bindings for binding in record.segment_governance_bindings)
        or any(identity not in message_admission_identities for identity in record.message_admission_identities)
        for record in (*operation_introductions, *operation_terminal_outcomes)
    ):
        raise ObservationPersistenceError("observation operation governance is substituted")

    committed_outcomes = tuple(
        outcome for outcome in operation_terminal_outcomes if outcome.final_status == "committed"
    )
    if (terminal_status == "committed") != bool(committed_outcomes):
        raise ObservationPersistenceError("terminal status does not match operation outcomes")
    if (terminal_status == "committed") != (graph_revision_delta is not None):
        raise ObservationPersistenceError("terminal status does not match graph delta")
    if graph_revision_delta is None:
        if materialized_graph_records:
            raise ObservationPersistenceError("noncommitting group has materialized graph records")
    else:
        if (
            graph_revision_delta.segment_governance_bindings != segment_governance_bindings
            or graph_revision_delta.message_admission_identities != message_admission_identities
            or graph_revision_delta.governance_carrier_artifact != governance_carrier_artifact
        ):
            raise ObservationPersistenceError("graph delta governance is substituted")
        _validate_graph_delta(
            request=request,
            materialized_graph_records=materialized_graph_records,
            graph_revision_delta=graph_revision_delta,
        )
        if any(
            outcome.graph_revision_delta_digest != graph_revision_delta.delta_digest for outcome in committed_outcomes
        ):
            raise ObservationPersistenceError("committed outcome does not name graph delta")

    mutations = tuple(
        IngestionObservationRecordMutation.create(
            mutation_kind="create",
            ingestion_record_kind=record.ingestion_record_kind,
            record_id=(
                record.introduction_id
                if isinstance(
                    record,
                    (CanonicalSourceIntroductionRecord, CanonicalOperationIntroductionRecord),
                )
                else record.outcome_id
            ),
            record_version=1,
            record=record,
            record_digest=record.record_digest,
        )
        for record in records
    )
    return IngestionObservationDelta.create(
        kind="terminal_group",
        observation_delta_id=observation_delta_id,
        observation_revision_before=observation_revision_before,
        observation_revision_after=observation_revision_after,
        source_id=source_id,
        source_digest=source_digest,
        segment_governance_bindings=segment_governance_bindings,
        message_admission_identities=message_admission_identities,
        governance_carrier_artifact=governance_carrier_artifact,
        operation_fence_id=operation_fence_id,
        transaction_group_id=request.transaction_group_id,
        operation_ids=operation_ids,
        terminal_status=terminal_status,
        graph_revision_delta_digest=(None if graph_revision_delta is None else graph_revision_delta.delta_digest),
        observation_schema_fingerprint=observation_schema_fingerprint,
        record_mutations=mutations,
    )


def build_source_finalization_observation_delta(
    *,
    source_outcome: CanonicalSourceTerminalOutcomeRecord,
    observation_delta_id: str,
    observation_revision_before: str,
    observation_revision_after: str,
    observation_schema_fingerprint: str,
) -> SourceFinalizationObservationDelta:
    """Build the source-finalization record for its own finalization transaction.

    This intentionally accepts no terminal-group wrapper or group summary.
    The completed canonical source outcome is the only authority for source
    coordinates and preserves source and group lifecycle separation.
    """
    return SourceFinalizationObservationDelta.create(
        kind="source_finalization",
        observation_delta_id=observation_delta_id,
        observation_revision_before=observation_revision_before,
        observation_revision_after=observation_revision_after,
        source_id=source_outcome.source_id,
        source_digest=source_outcome.source_digest,
        delivery_principal_binding_digest=source_outcome.delivery_principal_binding_digest,
        delivery_key_digest=source_outcome.delivery_key_digest,
        segment_governance_carriers=source_outcome.segment_governance_carriers,
        message_admission_carriers=source_outcome.message_admission_carriers,
        governance_carrier_artifact=source_outcome.governance_carrier_artifact,
        required_outcome_scopes=source_outcome.required_outcome_scopes,
        operation_fence_id=source_outcome.operation_fence_id,
        operation_ids=source_outcome.operation_ids,
        source_outcome=source_outcome,
        observation_schema_fingerprint=observation_schema_fingerprint,
    )


def _validate_graph_delta(
    *,
    request: BootstrapGraphGroupCommitRequestV3,
    materialized_graph_records: tuple[BaseModel, ...],
    graph_revision_delta: GraphRevisionDelta,
) -> None:
    if (
        request.source_plan_lineage_entry.source_id not in graph_revision_delta.source_ids
        or graph_revision_delta.operation_ids != request.operation_ids
        or graph_revision_delta.transaction_group_id != request.transaction_group_id
    ):
        raise ObservationPersistenceError("graph delta does not close the group request")
    materialized = tuple(_record_key(record) for record in materialized_graph_records)
    changed = tuple(_record_key(change.after_record.payload) for change in graph_revision_delta.record_changes)
    if (
        len(set(materialized)) != len(materialized)
        or len(set(changed)) != len(changed)
        or set(materialized) != set(changed)
    ):
        raise ObservationPersistenceError("graph delta does not match materialized graph records")


def _record_key(record: BaseModel) -> tuple[str, str, str]:
    if not graph_record_union_member(record):
        raise ObservationPersistenceError("materialized graph record type is invalid")
    return record.record_kind, graph_record_id(record), record.record_digest


__all__ = [
    "ObservationPersistenceError",
    "build_source_finalization_observation_delta",
    "source_finalization_observation_delta_id",
    "source_finalization_observation_revision",
    "source_finalization_observation_schema_fingerprint",
    "build_terminal_group_observation_delta",
]
