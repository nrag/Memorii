"""Registered projection of retained native ingestion observation records."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

from memorii.core.memory_evolution.graph_effect_contracts import (
    CanonicalOperationIntroductionRecord,
    CanonicalOperationTerminalOutcomeRecord,
    CanonicalSourceIntroductionRecord,
    CanonicalSourceTerminalOutcomeRecord,
    IngestionObservationDelta,
)
from memorii.core.memory_evolution.graph_ingestion_observation_records import (
    ObservedOperationIntroduction,
    ObservedOperationTerminalOutcome,
    ObservedSourceIntroduction,
    ObservedSourceTerminalOutcome,
)
from memorii.core.memory_evolution.graph_observation_cohort import ResolvedObservationMembership
from memorii.core.memory_evolution.graph_observation_paging import ObservationCohortUnavailableError
from memorii.core.memory_evolution.graph_observation_records import ObservedEntityReference
from memorii.core.memory_evolution.graph_observation_streams import (
    OperationIntroductionStreamRecord,
    OperationTerminalOutcomeStreamRecord,
    SourceIntroductionStreamRecord,
    SourceTerminalOutcomeStreamRecord,
)
from memorii.core.memory_evolution.observation_activation_runtime import emit_registered_observation_artifact
from memorii.core.memory_evolution.typed_value_artifact_reader import ProtectedTypedValueArtifactReaderLimits
from memorii.core.memory_evolution.typed_value_publication import VerifiedTypedValuePublication
from memorii.core.memory_evolution.typed_value_registry_history import ProtectedTypedValueRegistryHistory

_Observed = TypeVar(
    "_Observed",
    ObservedSourceIntroduction,
    ObservedOperationIntroduction,
    ObservedOperationTerminalOutcome,
    ObservedSourceTerminalOutcome,
)


def materialize_ingestion_observation_stream(
    *,
    membership: ResolvedObservationMembership,
    records: Iterable[
        CanonicalSourceIntroductionRecord
        | CanonicalOperationIntroductionRecord
        | CanonicalOperationTerminalOutcomeRecord
        | CanonicalSourceTerminalOutcomeRecord
    ],
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> tuple[
    SourceIntroductionStreamRecord
    | OperationIntroductionStreamRecord
    | OperationTerminalOutcomeStreamRecord
    | SourceTerminalOutcomeStreamRecord,
    ...,
]:
    """Emit selected native records under their registered observed roots.

    Membership is already closed by the detached cohort resolver.  This owner
    only converts retained typed records and rejects a source/operation record
    that escapes that closure.
    """
    source_ids = set(membership.source_ids)
    operation_ids = set(membership.operation_ids)
    emitted = []
    selected_records = []
    for record in records:
        if isinstance(record, CanonicalSourceIntroductionRecord):
            if record.source_id not in source_ids or record.operation_id not in operation_ids:
                continue
            value = _emit(ObservedSourceIntroduction(
                introduction_id=record.introduction_id, source_id=record.source_id,
                source_digest=record.source_digest,
                delivery_principal_binding_digest=record.delivery_principal_binding_digest,
                delivery_key_digest=record.delivery_key_digest,
                segment_governance=record.segment_governance,
                message_admission_identity=record.message_admission_identity,
                governance_carrier_artifact=record.governance_carrier_artifact,
                mention_span=record.mention_span,
                entity=ObservedEntityReference(
                    entity_revision_id=record.entity_revision_id,
                    logical_entity_id=record.logical_entity_id,
                    reference_path="entity_revision_id",
                ),
                independently_asserted_type_evidence_ids=record.independently_asserted_type_evidence_ids,
                operation_id=record.operation_id, operation_fence_id=record.operation_fence_id,
                boundary=False, record_digest="0" * 64,
            ), "ObservedSourceIntroduction", history, publication, limits)
            emitted.append(SourceIntroductionStreamRecord(
                record_kind="source_introduction", primary_key=value.introduction_id,
                record_digest=value.record_digest, payload=value,
            ))
        elif isinstance(record, CanonicalOperationIntroductionRecord):
            if record.source_id not in source_ids or record.operation_id not in operation_ids:
                continue
            value = _emit(ObservedOperationIntroduction(
                introduction_id=record.introduction_id, operation_id=record.operation_id,
                source_id=record.source_id, source_digest=record.source_digest,
                delivery_principal_binding_digest=record.delivery_principal_binding_digest,
                delivery_key_digest=record.delivery_key_digest,
                segment_governance_binding_digests=tuple(item.binding_digest for item in record.segment_governance_bindings),
                message_admission_key_digests=tuple(item.message_admission_key_digest for item in record.message_admission_identities),
                governance_carrier_artifact=record.governance_carrier_artifact,
                operation_fence_id=record.operation_fence_id, transaction_group_id=record.transaction_group_id,
                operation_kind=record.operation_kind, predicate_id=record.predicate_id,
                owned_source_spans=record.owned_source_spans, boundary=False, record_digest="0" * 64,
            ), "ObservedOperationIntroduction", history, publication, limits)
            emitted.append(OperationIntroductionStreamRecord(
                record_kind="operation_introduction", primary_key=value.introduction_id,
                record_digest=value.record_digest, payload=value,
            ))
        elif isinstance(record, CanonicalOperationTerminalOutcomeRecord):
            if record.source_id not in source_ids or record.operation_id not in operation_ids:
                continue
            value = _emit(ObservedOperationTerminalOutcome(
                outcome_id=record.outcome_id, operation_id=record.operation_id,
                source_id=record.source_id, source_digest=record.source_digest,
                delivery_principal_binding_digest=record.delivery_principal_binding_digest,
                delivery_key_digest=record.delivery_key_digest,
                segment_governance_binding_digests=tuple(item.binding_digest for item in record.segment_governance_bindings),
                message_admission_key_digests=tuple(item.message_admission_key_digest for item in record.message_admission_identities),
                governance_carrier_artifact=record.governance_carrier_artifact,
                operation_fence_id=record.operation_fence_id, transaction_group_id=record.transaction_group_id,
                final_status=record.final_status, graph_revision_delta_digest=record.graph_revision_delta_digest,
                temporal_decision_bindings=record.temporal_decision_bindings,
                reason_codes=record.reason_codes, record_digest="0" * 64,
            ), "ObservedOperationTerminalOutcome", history, publication, limits)
            emitted.append(OperationTerminalOutcomeStreamRecord(
                record_kind="operation_terminal_outcome", primary_key=value.outcome_id,
                record_digest=value.record_digest, payload=value,
            ))
        elif isinstance(record, CanonicalSourceTerminalOutcomeRecord):
            if record.source_id not in source_ids:
                continue
            if not set(record.operation_ids).issubset(operation_ids):
                raise ObservationCohortUnavailableError("source terminal operation closure is incomplete")
            value = _emit(ObservedSourceTerminalOutcome(
                outcome_id=record.outcome_id, source_id=record.source_id, source_digest=record.source_digest,
                delivery_principal_binding_digest=record.delivery_principal_binding_digest,
                delivery_key_digest=record.delivery_key_digest,
                segment_governance_carrier_set_digest=record.segment_governance_carriers.carrier_set_digest,
                message_admission_carrier_set_digest=record.message_admission_carriers.carrier_set_digest,
                required_outcome_scope_set_digest=record.required_outcome_scopes.required_scope_set_digest,
                governance_carrier_artifact=record.governance_carrier_artifact,
                operation_fence_id=record.operation_fence_id, operation_ids=record.operation_ids,
                final_status=record.final_status, group_result_digests=record.group_result_digests,
                source_result_digest=record.source_result_digest, record_digest="0" * 64,
            ), "ObservedSourceTerminalOutcome", history, publication, limits)
            emitted.append(SourceTerminalOutcomeStreamRecord(
                record_kind="source_terminal_outcome", primary_key=value.outcome_id,
                record_digest=value.record_digest, payload=value,
            ))
        else:
            raise ObservationCohortUnavailableError("unsupported ingestion observation record")
        selected_records.append(record)
    keys = tuple((item.record_kind, item.primary_key) for item in emitted)
    if len(keys) != len(set(keys)):
        raise ObservationCohortUnavailableError("duplicate observed ingestion record")
    _require_complete_selected_records(emitted, membership)
    expected_records = (
        *(mutation.record for entry in membership.group_entries
          if isinstance(entry.delta, IngestionObservationDelta)
          for mutation in entry.delta.record_mutations),
        *(delta.source_outcome for delta in membership.source_finalizations),
    )
    expected = {(record.ingestion_record_kind, record.record_digest): record for record in expected_records}
    selected = {(record.ingestion_record_kind, record.record_digest): record for record in selected_records}
    if len(expected) != len(expected_records) or selected != expected:
        raise ObservationCohortUnavailableError("selected records differ from retained ledger")
    return tuple(sorted(emitted, key=lambda item: (item.record_kind, item.primary_key)))


def _emit(
    value: _Observed,
    schema_id: str,
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> _Observed:
    emitted = emit_registered_observation_artifact(
        value, schema_id=schema_id, history=history, publication=publication, limits=limits,
    ).value
    if not isinstance(emitted, type(value)):
        raise ObservationCohortUnavailableError("registered observed ingestion payload is substituted")
    return emitted


def _require_complete_selected_records(
    emitted: list[object], membership: ResolvedObservationMembership,
) -> None:
    source_introduction_ids = [
        value.payload.introduction_id
        for value in emitted if isinstance(value, SourceIntroductionStreamRecord)
    ]
    operation_introductions = [
        value.payload.operation_id
        for value in emitted if isinstance(value, OperationIntroductionStreamRecord)
    ]
    operation_outcomes = [
        value.payload.operation_id
        for value in emitted if isinstance(value, OperationTerminalOutcomeStreamRecord)
    ]
    source_terminals = [
        value.payload.source_id
        for value in emitted if isinstance(value, SourceTerminalOutcomeStreamRecord)
    ]
    operations = set(membership.operation_ids)
    sources = set(membership.source_ids)
    if any(not isinstance(entry.delta, IngestionObservationDelta) for entry in membership.group_entries):
        raise ObservationCohortUnavailableError("selected group membership has a source finalization entry")
    expected_source_introduction_ids = {
        mutation.record.introduction_id
        for entry in membership.group_entries
        if isinstance(entry.delta, IngestionObservationDelta)
        for mutation in entry.delta.record_mutations
        if isinstance(mutation.record, CanonicalSourceIntroductionRecord)
    }
    if (
        set(source_introduction_ids) != expected_source_introduction_ids
        or len(source_introduction_ids) != len(expected_source_introduction_ids)
        or set(operation_introductions) != operations or len(operation_introductions) != len(operations)
        or set(operation_outcomes) != operations or len(operation_outcomes) != len(operations)
        or set(source_terminals) != sources or len(source_terminals) != len(sources)
    ):
        raise ObservationCohortUnavailableError("selected ingestion record closure is incomplete")


__all__ = ["materialize_ingestion_observation_stream"]
