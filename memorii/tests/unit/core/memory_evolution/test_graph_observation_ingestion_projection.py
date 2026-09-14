"""Registered projection proof for retained ingestion-observation records."""

import pytest
from memorii.core.memory_evolution.graph_effect_contracts import (
    CanonicalOperationIntroductionRecord,
    CanonicalOperationTerminalOutcomeRecord,
    CanonicalSourceIntroductionRecord,
    CanonicalSourceTerminalOutcomeCore,
    CanonicalSourceTerminalOutcomeRecord,
    IngestionObservationDelta,
    IngestionObservationRecordMutation,
)
from memorii.core.memory_evolution.graph_observation_cohort import ResolvedObservationMembership
from memorii.core.memory_evolution.graph_observation_ingestion_projection import (
    materialize_ingestion_observation_stream,
)
from memorii.core.memory_evolution.graph_observation_paging import ObservationCohortUnavailableError
from memorii.core.memory_evolution.observation_ledger_contracts import (
    ObservationGroupResultLocator,
    ObservationLedgerEntry,
)
from memorii.core.memory_evolution.observation_persistence import (
    build_source_finalization_observation_delta,
)
from tests.fixtures.semantic_ingestion.observation_publication import observation_publication
from tests.unit.core.memory_evolution.test_observation_record_contracts import (
    _records,
    _source_material,
    _source_terminal,
    _terminal_group_delta,
)


def _mutation(record):
    return IngestionObservationRecordMutation.create(
        mutation_kind="create",
        ingestion_record_kind=record.ingestion_record_kind,
        record_id=(
            record.introduction_id
            if isinstance(record, (CanonicalSourceIntroductionRecord, CanonicalOperationIntroductionRecord))
            else record.outcome_id
        ),
        record_version=1,
        record=record,
        record_digest=record.record_digest,
    )


def _committed_group(material, source_introductions):
    _, operation_introduction, evidence_only_outcome = _records(material)
    graph_digest = "a" * 64
    outcome = CanonicalOperationTerminalOutcomeRecord.create(**{
        **evidence_only_outcome.model_dump(mode="python", exclude={"record_digest"}),
        "final_status": "committed",
        "graph_revision_delta_digest": graph_digest,
        "reason_codes": (),
    })
    return IngestionObservationDelta.create(
        kind="terminal_group",
        observation_delta_id="observation:committed-terminal-group",
        observation_revision_before="observation:0",
        observation_revision_after="observation:1",
        source_id=material.source_id,
        source_digest=material.source_digest,
        segment_governance_bindings=(material.segment_governance,),
        message_admission_identities=(material.message_admission_identity,),
        governance_carrier_artifact=material.governance_carrier_artifact,
        operation_fence_id="fence:observation-record",
        transaction_group_id="group:observation-record",
        operation_ids=("operation:observation-record",),
        terminal_status="committed",
        graph_revision_delta_digest=graph_digest,
        observation_schema_fingerprint="b" * 64,
        record_mutations=tuple(
            _mutation(record) for record in (*source_introductions, operation_introduction, outcome)
        ),
    )


def _entry(delta: IngestionObservationDelta) -> ObservationLedgerEntry:
    return ObservationLedgerEntry(
        schema_version=1,
        repository_id="repository:ingestion-projection",
        activation_digest="c" * 64,
        sequence=1,
        previous_entry_digest=None,
        semantic_payload_digest="d" * 64,
        delta=delta,
        result_locator=ObservationGroupResultLocator(
            schema_version=1,
            kind="group_primary",
            immutable_record_id="record:group",
            source_id=delta.source_id,
            source_digest=delta.source_digest,
            source_operation_id="operation:observation-record",
            operation_fence_id=delta.operation_fence_id,
            transaction_group_id=delta.transaction_group_id,
            operation_ids=delta.operation_ids,
            request_ctv_digest="e" * 64,
        ),
        result_digest="f" * 64,
        entry_digest="0" * 64,
    )


def _source_terminal_for_group(material, group: IngestionObservationDelta) -> CanonicalSourceTerminalOutcomeRecord:
    original = _source_terminal(material)
    core = CanonicalSourceTerminalOutcomeCore.create(**{
        **original.core.model_dump(mode="python", exclude={"core_digest"}),
        "group_result_digests": (_entry(group).result_digest,),
    })
    return CanonicalSourceTerminalOutcomeRecord.create(
        core=core, preparation_fingerprint=material.preparation_fingerprint,
    )


def _membership(
    material, group: IngestionObservationDelta, terminal: CanonicalSourceTerminalOutcomeRecord,
) -> ResolvedObservationMembership:
    source_finalization = build_source_finalization_observation_delta(
        source_outcome=terminal,
        observation_delta_id="observation:source-finalization",
        observation_revision_before="observation:1",
        observation_revision_after="observation:2",
        observation_schema_fingerprint="b" * 64,
    )
    return ResolvedObservationMembership(
        seed_source_ids=(material.source_id,),
        seed_operation_ids=(),
        source_ids=(material.source_id,),
        operation_ids=group.operation_ids,
        operation_fence_ids=(group.operation_fence_id,),
        source_finalizations=(source_finalization,),
        group_entries=(_entry(group),),
        graph_deltas=(),
    )


def test_selected_native_ingestion_records_emit_registered_observed_payloads(tmp_path, monkeypatch) -> None:
    history, limits = observation_publication(tmp_path, monkeypatch, (
        "ObservedSourceIntroduction", "ObservedOperationIntroduction",
        "ObservedOperationTerminalOutcome", "ObservedSourceTerminalOutcome",
    ))
    material = _source_material()
    source_introduction, _, _ = _records(material)
    group = _committed_group(material, (source_introduction,))
    terminal = _source_terminal_for_group(material, group)
    membership = _membership(material, group, terminal)

    stream = materialize_ingestion_observation_stream(
        membership=membership,
        records=(*(mutation.record for mutation in group.record_mutations), terminal),
        history=history, publication=history.publications[0], limits=limits,
    )

    assert [item.record_kind for item in stream] == [
        "operation_introduction", "operation_terminal_outcome", "source_introduction",
        "source_terminal_outcome",
    ]
    assert all(item.record_digest == item.payload.record_digest for item in stream)
    assert all(item.payload.record_digest != "0" * 64 for item in stream)
    assert all(getattr(item.payload, "boundary", False) is False for item in stream)


def test_source_terminal_cannot_escape_selected_operation_closure(tmp_path, monkeypatch) -> None:
    history, limits = observation_publication(tmp_path, monkeypatch, ("ObservedSourceTerminalOutcome",))
    material = _source_material()
    terminal = _source_terminal(material)

    with pytest.raises(ObservationCohortUnavailableError, match="operation closure"):
        materialize_ingestion_observation_stream(
            membership=ResolvedObservationMembership(
                seed_source_ids=(material.source_id,), seed_operation_ids=(), source_ids=(material.source_id,),
                operation_ids=(), operation_fence_ids=(), source_finalizations=(), group_entries=(), graph_deltas=(),
            ),
            records=(terminal,), history=history, publication=history.publications[0], limits=limits,
        )


def test_selected_membership_rejects_missing_or_duplicate_native_records(tmp_path, monkeypatch) -> None:
    history, limits = observation_publication(tmp_path, monkeypatch, (
        "ObservedSourceIntroduction", "ObservedOperationIntroduction",
        "ObservedOperationTerminalOutcome", "ObservedSourceTerminalOutcome",
    ))
    material = _source_material()
    source_introduction, _, _ = _records(material)
    group = _committed_group(material, (source_introduction,))
    terminal = _source_terminal_for_group(material, group)
    records = (*(mutation.record for mutation in group.record_mutations), terminal)
    membership = _membership(material, group, terminal)

    with pytest.raises(ObservationCohortUnavailableError, match="incomplete"):
        materialize_ingestion_observation_stream(
            membership=membership, records=records[1:], history=history,
            publication=history.publications[0], limits=limits,
        )
    with pytest.raises(ObservationCohortUnavailableError, match="duplicate"):
        materialize_ingestion_observation_stream(
            membership=membership, records=(*records, source_introduction), history=history,
            publication=history.publications[0], limits=limits,
        )
    substituted = CanonicalSourceIntroductionRecord.create(**{
        **source_introduction.model_dump(mode="python", exclude={"record_digest"}),
        "logical_entity_id": "entity:ada:substituted",
    })
    with pytest.raises(ObservationCohortUnavailableError, match="retained ledger"):
        materialize_ingestion_observation_stream(
            membership=membership,
            records=(substituted, *(mutation.record for mutation in group.record_mutations[1:]), terminal),
            history=history, publication=history.publications[0], limits=limits,
        )


def test_noncommitting_group_requires_no_source_introductions(tmp_path, monkeypatch) -> None:
    history, limits = observation_publication(tmp_path, monkeypatch, (
        "ObservedOperationIntroduction", "ObservedOperationTerminalOutcome", "ObservedSourceTerminalOutcome",
    ))
    material = _source_material()
    group = _terminal_group_delta(material)
    terminal = _source_terminal_for_group(material, group)

    stream = materialize_ingestion_observation_stream(
        membership=_membership(material, group, terminal),
        records=(*(mutation.record for mutation in group.record_mutations), terminal),
        history=history, publication=history.publications[0], limits=limits,
    )

    assert [item.record_kind for item in stream] == [
        "operation_introduction", "operation_terminal_outcome", "source_terminal_outcome",
    ]


def test_committed_group_allows_multiple_source_introductions_for_one_operation(tmp_path, monkeypatch) -> None:
    history, limits = observation_publication(tmp_path, monkeypatch, (
        "ObservedSourceIntroduction", "ObservedOperationIntroduction",
        "ObservedOperationTerminalOutcome", "ObservedSourceTerminalOutcome",
    ))
    material = _source_material()
    first, _, _ = _records(material)
    second = CanonicalSourceIntroductionRecord.create(**{
        **first.model_dump(mode="python", exclude={"record_digest"}),
        "introduction_id": "introduction:source:second",
        "entity_revision_id": "entity-revision:ada:second",
    })
    group = _committed_group(material, (first, second))
    terminal = _source_terminal_for_group(material, group)

    stream = materialize_ingestion_observation_stream(
        membership=_membership(material, group, terminal),
        records=(*(mutation.record for mutation in group.record_mutations), terminal),
        history=history, publication=history.publications[0], limits=limits,
    )

    assert [item.primary_key for item in stream if item.record_kind == "source_introduction"] == [
        first.introduction_id, second.introduction_id,
    ]
