from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

import pytest
from graph_record_test_support import (
    all_canonical_graph_records,
    next_canonical_graph_record_versions,
)
from memorii.core.memory_evolution.atomic_store import (
    PreplanningStoreError,
    SemanticIngestionAtomicStore,
)
from memorii.core.memory_evolution.conflict_attention import (
    ConflictAccessContext,
    ConflictKind,
    ConflictListRequest,
    SemanticConflictReplayBinding,
)
from memorii.core.memory_evolution.conflict_attention_repository import (
    ConflictCursorKey,
    FileConflictAttentionRepository,
)
from memorii.core.memory_evolution.conflict_integrity import (
    CanonicalReplayIntegrityIncidentReporter,
    ConflictCleanReplayVerification,
    ConflictIntegrityError,
    ConflictRepositoryIntegritySnapshot,
    ConflictRepositoryPartitionSnapshot,
    ConflictScopeIsolationProof,
    FileConflictIntegrityRepository,
    PrivilegedSemanticIntegrityLifecycle,
    ReplayIntegrityLinearization,
    SemanticEventCleanAuthorityBatch,
    SemanticEventCleanRecoveryRequest,
    SemanticEventCleanRecoveryService,
    SemanticEventCleanReplayVerifier,
    SemanticEventFreezeGuard,
)
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.memory_evolution.projection_binding import (
    ProjectionHistoryReplayBinding,
)
from memorii.core.memory_evolution.projection_history import projection_records_from_replay_state
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore, _PersistedBatch
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.semantic_ingestion.contracts import (
    SemanticGraphDelta,
    SemanticTerminalOutcome,
    contract_digest,
)
from memorii.core.semantic_ingestion.event_replay import (
    EventBatchLogPosition,
    FileSemanticEventRepository,
    MemoryIntegrityConflict,
    ReplayCheckpointLifecycleState,
    ReplayCheckpointResumeAuthority,
    ReplayCheckpointSigningKey,
    ReplayCheckpointTrustPolicy,
    SemanticEventReplayError,
    SemanticEventSchemaRegistry,
    SemanticEventSchemaRegistryHistory,
    SemanticEventSchemaSupport,
    SemanticMemoryEventBatch,
    SemanticReplayState,
    build_semantic_memory_event,
    build_semantic_memory_event_batch,
    create_replay_checkpoint,
    decode_semantic_memory_event_batch,
    encode_semantic_memory_event_batch,
    replay_semantic_checkpoint_tail,
    replay_semantic_event_batches,
    semantic_event_id,
    validate_replay_checkpoint,
)
from memorii.domain.enums import (
    CommitStatus,
    MemoryDomain,
    MemoryRecordVisibility,
)
from pydantic import BaseModel, ValidationError
from tests.fixtures.semantic_ingestion.event_replay_fixture import (
    CheckpointKeyMaterial,
    DeterministicCheckpointSignatureAuthority,
    ExactProjectionHistoryVerifier,
    projection_history_bindings,
)
from tests.fixtures.semantic_ingestion.semantic_terminal_fixture import NOW, accepted_terminal


def _real_claim_replay(
    terminals,
):
    registry = SemanticEventSchemaRegistry.create()
    state = SemanticReplayState.genesis("typed-claim-arbitration")
    batches = []
    for index, terminal in enumerate(terminals, start=1):
        delta = SemanticGraphDelta.create(terminal)
        analysis = terminal.source_analyses[0]
        batch = build_semantic_memory_event_batch(
            graph_delta=delta,
            prior_state=state,
            repository_id=state.repository_id,
            source_id=analysis.source_id,
            transaction_group_id=f"claim-arbitration:{index}",
            operation_fence_id=f"claim-operation:{index}",
            writer_epoch=1,
            graph_revision_before=state.graph_revision,
            graph_revision_after=f"claim-graph:{index}",
            timestamp=NOW + timedelta(minutes=index),
            registry=registry,
        )
        batches.append(batch)
        state = replay_semantic_event_batches(
            repository_id=state.repository_id,
            batches=(batch,),
            registry=registry,
            initial_state=state,
        )
    return registry, tuple(batches), state


def _claim_terminal(
    *,
    coordinate: str,
    employer: str,
    authority_class: str,
    ranks: dict[str, int],
    valid_start: datetime = NOW,
    valid_end: datetime | None = NOW + timedelta(days=31),
    atemporal: bool = False,
    state_cardinality: str = "single",
):
    normalized = employer.lower()
    return accepted_terminal(
        operation_id=f"claim-terminal:{coordinate}",
        source_text=f"Alice works for {employer}.",
        source_id=f"claim-source:{coordinate}",
        subject_logical_entity_id="entity:alice",
        subject_entity_revision_id="entity-revision:alice:v1",
        object_logical_entity_id=f"entity:{normalized}",
        object_entity_revision_id=f"entity-revision:{normalized}:v1",
        authority_class=authority_class,
        eligible_authority_classes=frozenset(ranks),
        authority_rank_by_class=ranks,
        valid_start=valid_start,
        valid_end=valid_end,
        atemporal=atemporal,
        state_cardinality=state_cardinality,
    )


def test_real_equal_rank_distinct_claim_values_replay_as_contested() -> None:
    ranks = {"community": 10, "official": 10}
    terminals = (
        _claim_terminal(
            coordinate="official-globex",
            employer="Globex",
            authority_class="official",
            ranks=ranks,
        ),
        _claim_terminal(
            coordinate="community-initech",
            employer="Initech",
            authority_class="community",
            ranks=ranks,
        ),
    )
    registry, batches, state = _real_claim_replay(terminals)

    temporal, trust, _, _, _ = projection_records_from_replay_state(state)

    assert len(temporal) == len(trust) == 1
    assert temporal[0].outcome == trust[0].outcome == "contested"
    expected_ids = tuple(sorted(terminal.accepted_carriers[0].claim_assertion_id for terminal in terminals))
    assert temporal[0].selected_assertion_ids == ()
    assert temporal[0].contested_assertion_ids == expected_ids
    assert trust[0].selected_assertion_ids == ()
    assert trust[0].contested_assertion_ids == expected_ids
    assert {item.source_id for item in trust[0].evidence} == {
        "claim-source:official-globex",
        "claim-source:community-initech",
    }
    replayed = replay_semantic_event_batches(
        repository_id=state.repository_id,
        batches=batches,
        registry=registry,
    )
    assert encode_typed_value(replayed.model_dump(mode="python")) == encode_typed_value(state.model_dump(mode="python"))


def test_real_higher_authority_claim_supersedes_without_source_count_voting() -> None:
    ranks = {"community": 1, "official": 10}
    lower_terminals = (
        _claim_terminal(
            coordinate="community-globex-one",
            employer="Globex",
            authority_class="community",
            ranks=ranks,
        ),
        _claim_terminal(
            coordinate="community-globex-two",
            employer="Globex",
            authority_class="community",
            ranks=ranks,
        ),
    )
    _, _, lower_state = _real_claim_replay(lower_terminals)
    _, lower_trust, _, _, _ = projection_records_from_replay_state(lower_state)
    assert lower_trust[0].outcome == "pass"
    assert len(lower_trust[0].selected_assertion_ids) == 2

    higher = _claim_terminal(
        coordinate="official-initech",
        employer="Initech",
        authority_class="official",
        ranks=ranks,
    )
    _, _, final_state = _real_claim_replay((*lower_terminals, higher))
    temporal, trust, _, _, _ = projection_records_from_replay_state(final_state)

    higher_id = higher.accepted_carriers[0].claim_assertion_id
    lower_ids = tuple(sorted(terminal.accepted_carriers[0].claim_assertion_id for terminal in lower_terminals))
    assert temporal[0].outcome == trust[0].outcome == "pass"
    assert temporal[0].selected_assertion_ids == trust[0].selected_assertion_ids == (higher_id,)
    assert temporal[0].retained_assertion_ids == lower_ids
    assert trust[0].retained_assertion_ids == lower_ids


def test_winning_value_selects_all_eligible_same_value_support() -> None:
    ranks = {"community": 1, "official": 10}
    lower_globex = _claim_terminal(
        coordinate="community-globex-support",
        employer="Globex",
        authority_class="community",
        ranks=ranks,
    )
    higher_globex = _claim_terminal(
        coordinate="official-globex-support",
        employer="Globex",
        authority_class="official",
        ranks=ranks,
    )
    lower_initech = _claim_terminal(
        coordinate="community-initech-displaced",
        employer="Initech",
        authority_class="community",
        ranks=ranks,
    )
    _, _, state = _real_claim_replay((lower_globex, lower_initech, higher_globex))

    temporal, trust, _, _, _ = projection_records_from_replay_state(state)

    expected_selected = tuple(
        sorted(terminal.accepted_carriers[0].claim_assertion_id for terminal in (lower_globex, higher_globex))
    )
    displaced_id = lower_initech.accepted_carriers[0].claim_assertion_id
    assert len(temporal) == len(trust) == 1
    for records in (temporal, trust):
        assert records[0].outcome == "pass"
        assert records[0].selected_assertion_ids == expected_selected
        assert records[0].retained_assertion_ids == (displaced_id,)


def test_multi_valued_claims_partition_by_value_without_competing() -> None:
    ranks = {"official": 10}
    terminals = tuple(
        _claim_terminal(
            coordinate=f"multi:{employer.lower()}",
            employer=employer,
            authority_class="official",
            ranks=ranks,
            state_cardinality="multi",
        )
        for employer in ("Globex", "Initech")
    )
    _, _, state = _real_claim_replay(terminals)

    temporal, trust, _, _, _ = projection_records_from_replay_state(state)

    expected_ids = {terminal.accepted_carriers[0].claim_assertion_id for terminal in terminals}
    assert len(temporal) == len(trust) == 2
    for records in (temporal, trust):
        assert {record.outcome for record in records} == {"pass"}
        assert {record.selected_assertion_ids[0] for record in records} == expected_ids
        assert all(
            len(record.selected_assertion_ids) == 1 and record.contested_assertion_ids == () for record in records
        )


@pytest.mark.parametrize(
    ("case", "claims", "expected"),
    (
        (
            "disjoint",
            (("Globex", 0, 5), ("Initech", 10, 20)),
            (
                (0, 5, "pass", ("Globex",), ()),
                (10, 20, "pass", ("Initech",), ()),
            ),
        ),
        (
            "touching",
            (("Globex", 0, 10), ("Initech", 10, 20)),
            (
                (0, 10, "pass", ("Globex",), ()),
                (10, 20, "pass", ("Initech",), ()),
            ),
        ),
        (
            "partial-overlap",
            (("Globex", 0, 15), ("Initech", 10, 20)),
            (
                (0, 10, "pass", ("Globex",), ()),
                (10, 15, "contested", (), ("Globex", "Initech")),
                (15, 20, "pass", ("Initech",), ()),
            ),
        ),
        (
            "nested",
            (("Globex", 0, 20), ("Initech", 5, 10)),
            (
                (0, 5, "pass", ("Globex",), ()),
                (5, 10, "contested", (), ("Globex", "Initech")),
                (10, 20, "pass", ("Globex",), ()),
            ),
        ),
        (
            "equal",
            (("Globex", 0, 20), ("Initech", 0, 20)),
            ((0, 20, "contested", (), ("Globex", "Initech")),),
        ),
        (
            "open-ended",
            (("Globex", 0, None), ("Initech", 10, 20)),
            (
                (0, 10, "pass", ("Globex",), ()),
                (10, 20, "contested", (), ("Globex", "Initech")),
                (20, None, "pass", ("Globex",), ()),
            ),
        ),
        (
            "late-historical-insertion",
            (("Initech", 10, 20), ("Globex", 0, 15)),
            (
                (0, 10, "pass", ("Globex",), ()),
                (10, 15, "contested", (), ("Globex", "Initech")),
                (15, 20, "pass", ("Initech",), ()),
            ),
        ),
    ),
)
def test_real_claim_valid_time_atom_matrix(
    case: str,
    claims: tuple[tuple[str, int, int | None], ...],
    expected: tuple[
        tuple[
            int,
            int | None,
            str,
            tuple[str, ...],
            tuple[str, ...],
        ],
        ...,
    ],
) -> None:
    ranks = {"official": 10}
    terminals = tuple(
        _claim_terminal(
            coordinate=f"{case}:{index}",
            employer=employer,
            authority_class="official",
            ranks=ranks,
            valid_start=NOW + timedelta(days=start_day),
            valid_end=(None if end_day is None else NOW + timedelta(days=end_day)),
        )
        for index, (employer, start_day, end_day) in enumerate(claims)
    )
    assertion_employers = {
        terminal.accepted_carriers[0].claim_assertion_id: employer
        for terminal, (employer, _, _) in zip(terminals, claims, strict=True)
    }
    _, _, state = _real_claim_replay(terminals)
    temporal, trust, _, _, _ = projection_records_from_replay_state(state)

    def observed(records):
        ordered = sorted(
            records,
            key=lambda record: record.valid_interval.start,
        )
        return tuple(
            (
                (record.valid_interval.start - NOW).days,
                (None if record.valid_interval.end is None else (record.valid_interval.end - NOW).days),
                record.outcome,
                tuple(sorted(assertion_employers[assertion_id] for assertion_id in record.selected_assertion_ids)),
                tuple(sorted(assertion_employers[assertion_id] for assertion_id in record.contested_assertion_ids)),
            )
            for record in ordered
        )

    assert all(record.valid_interval is not None for record in temporal)
    assert all(record.valid_interval is not None for record in trust)
    assert observed(temporal) == expected
    assert observed(trust) == expected


def test_atemporal_claims_arbitrate_in_one_atemporal_atom() -> None:
    ranks = {"official": 10}
    globex = _claim_terminal(
        coordinate="atemporal-globex",
        employer="Globex",
        authority_class="official",
        ranks=ranks,
        atemporal=True,
    )
    initech = _claim_terminal(
        coordinate="atemporal-initech",
        employer="Initech",
        authority_class="official",
        ranks=ranks,
        atemporal=True,
    )
    _, _, state = _real_claim_replay((globex, initech))

    temporal_records, trust_records, _, _, _ = projection_records_from_replay_state(state)

    expected_ids = tuple(sorted(terminal.accepted_carriers[0].claim_assertion_id for terminal in (globex, initech)))
    assert len(temporal_records) == len(trust_records) == 1
    for records in (temporal_records, trust_records):
        assert records[0].outcome == "contested"
        assert records[0].valid_interval is None
        assert records[0].contested_assertion_ids == expected_ids


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _snapshot(*, coordinate: int = 10, retained_byte_one: str | None = None) -> ConflictRepositoryIntegritySnapshot:
    return ConflictRepositoryIntegritySnapshot.create(
        repository_id="repository",
        partitions=tuple(
            ConflictRepositoryPartitionSnapshot(
                partition_id=f"partition-{index}",
                scope_digest=_digest(f"scope-{index}"),
                retained_byte_digests=(
                    retained_byte_one if index == 1 and retained_byte_one is not None else _digest(f"byte-{index}"),
                ),
            )
            for index in range(1, 4)
        ),
        conflict_ledger_start_coordinate=0,
        conflict_ledger_end_coordinate=coordinate,
        last_verified_event_batch_sequence=coordinate - 1,
        store_topology_fingerprint=_digest("topology"),
    )


def _foreign_snapshot() -> ConflictRepositoryIntegritySnapshot:
    current = _snapshot()
    return ConflictRepositoryIntegritySnapshot.create(
        repository_id="foreign-repository",
        partitions=current.partitions,
        conflict_ledger_start_coordinate=current.conflict_ledger_start_coordinate,
        conflict_ledger_end_coordinate=current.conflict_ledger_end_coordinate,
        last_verified_event_batch_sequence=current.last_verified_event_batch_sequence,
        store_topology_fingerprint=current.store_topology_fingerprint,
    )


def _repository(path: Path, holder: list[ConflictRepositoryIntegritySnapshot]) -> FileConflictIntegrityRepository:
    def verify(
        repaired_partition_ids: tuple[str, ...],
        retained_conflicting_byte_digests: tuple[str, ...],
        authority_source_digests: tuple[str, ...],
    ) -> ConflictCleanReplayVerification:
        return ConflictCleanReplayVerification.create(
            repository_id="repository",
            repaired_partition_ids=repaired_partition_ids,
            retained_conflicting_byte_digests=retained_conflicting_byte_digests,
            authority_source_digests=authority_source_digests,
            clean_generation_id=_digest("clean-generation"),
            clean_generation_digest=_digest("clean-generation"),
            retained_corrupt_generation_digest=_digest("corrupt-generation"),
            replay_start_event_batch_sequence=0,
            replay_final_event_batch_sequence=holder[0].last_verified_event_batch_sequence,
            replay_final_batch_digest=_digest("final-batch"),
            replay_repository_state_digest=_digest("repository-state"),
            verified_at=datetime(2026, 8, 2, tzinfo=UTC),
        )

    return FileConflictIntegrityRepository(
        path,
        repository_id="repository",
        snapshot_provider=lambda: holder[0],
        clean_replay_verifier=verify,
        now_provider=lambda: datetime(2026, 8, 2, tzinfo=UTC),
    )


def test_clean_replay_verification_rejects_missing_or_empty_authority_sources() -> None:
    values = {
        "repository_id": "repository",
        "repaired_partition_ids": ("partition-a",),
        "retained_conflicting_byte_digests": (_digest("conflicting"),),
        "clean_generation_id": _digest("clean-generation"),
        "clean_generation_digest": _digest("clean-generation"),
        "retained_corrupt_generation_digest": _digest("corrupt-generation"),
        "replay_start_event_batch_sequence": 0,
        "replay_final_event_batch_sequence": 0,
        "replay_final_batch_digest": _digest("final-batch"),
        "replay_repository_state_digest": _digest("repository-state"),
        "verified_at": datetime(2026, 8, 2, tzinfo=UTC),
        "verification_digest": _digest("verification"),
    }
    with pytest.raises(ValueError):
        ConflictCleanReplayVerification.model_validate(values)
    with pytest.raises(ValueError):
        ConflictCleanReplayVerification.model_validate({**values, "authority_source_digests": ()})


def _graph_delta(*, version: int = 1, statement: str = "first") -> SemanticGraphDelta:
    terminal = accepted_terminal(operation_id="operation")
    if version != 1 or statement != "first":
        # Distinct carrier variants still commit through the terminal's own
        # factory: the delta digest covers the discriminated carrier union's
        # persisted representation, which a hand-built body cannot reproduce.
        carrier = terminal.accepted_carriers[0]
        values = carrier.model_dump(mode="python", exclude={"record_digest"})
        values.update({"record_version": version, "statement_digest": _digest(statement)})
        revised = type(carrier)(
            **values,
            record_digest=contract_digest(b"memorii.semantic-ingestion.temporal-carrier.v1", values),
        )
        carrier_artifact_digest = contract_digest(
            b"memorii.semantic-ingestion.terminal-carrier-artifact.v1",
            {
                "operation_id": terminal.operation_id,
                "sealed_operations": terminal.sealed_operations,
                "accepted_carriers": (revised,),
                "terminal_binding_sets": terminal.terminal_binding_sets,
            },
        )
        terminal = SemanticTerminalOutcome.create(
            operation_id=terminal.operation_id,
            status=terminal.status,
            reason_codes=terminal.reason_codes,
            candidates=terminal.candidates,
            source_analyses=terminal.source_analyses,
            arbitration_policy_bundle=terminal.arbitration_policy_bundle,
            authorization_read_set=terminal.authorization_read_set,
            execution_lineage=terminal.execution_lineage,
            temporal_closures=terminal.temporal_closures,
            carrier_artifact_digest=carrier_artifact_digest,
            sealed_operations=terminal.sealed_operations,
            accepted_carriers=(revised,),
            terminal_binding_sets=terminal.terminal_binding_sets,
            attempt_count=terminal.attempt_count,
        )
    return SemanticGraphDelta.create(terminal)


def _batch(
    *,
    delta: SemanticGraphDelta,
    state: SemanticReplayState,
    before: str,
    after: str,
    group: str = "operation",
    fence: str = "f" * 64,
    registry: SemanticEventSchemaRegistry | None = None,
    repository_id: str = "repository",
):
    registry = registry or SemanticEventSchemaRegistry.create()
    return build_semantic_memory_event_batch(
        graph_delta=delta,
        prior_state=state,
        repository_id=repository_id,
        source_id="source",
        transaction_group_id=group,
        operation_fence_id=fence,
        writer_epoch=1,
        graph_revision_before=before,
        graph_revision_after=after,
        timestamp=NOW,
        registry=registry,
    )


def _single_event_batch(
    *,
    event,
    registry: SemanticEventSchemaRegistry,
    sequence: int,
):
    """Build a canonical one-event batch for integrity-conflict vectors."""

    body = {
        "repository_id": "repository",
        "log_position": EventBatchLogPosition.create(repository_id="repository", sequence=sequence),
        "source_id": event.provenance.source_id,
        "transaction_group_id": event.transaction_group_id,
        "operation_fence_id": event.operation_fence_id,
        "writer_epoch": event.writer_epoch,
        "event_schema_registry_revision": registry.registry_revision,
        "event_schema_registry_digest": registry.registry_digest,
        "graph_delta_digest": event.payload.graph_delta_digest,
        "events": (event,),
    }
    from memorii.core.semantic_ingestion import event_replay as event_module

    return SemanticMemoryEventBatch(
        **body,
        event_batch_digest=event_module._digest(event_module._BATCH_DOMAIN, body),
    )


def _equal_version_conflict_batches(
    *,
    registry: SemanticEventSchemaRegistry,
    initial_state: SemanticReplayState,
    first_statement: str,
    second_statement: str,
    first_group: str,
    second_group: str,
    first_timestamp: datetime,
    second_timestamp: datetime,
) -> tuple:
    """Return consecutive, non-identical envelopes reserving one record/version."""

    version = 1 if not initial_state.materialized_records else initial_state.materialized_records[0].record_version + 1
    prior_record = None if version == 1 else initial_state.materialized_records[0]
    first_sequence = 1 if initial_state.last_batch_position is None else initial_state.last_batch_position.sequence + 1
    first_after = f"conflict-revision-{first_sequence}"
    second_after = f"conflict-revision-{first_sequence + 1}"

    def event_for(
        *,
        statement: str,
        group: str,
        timestamp: datetime,
        graph_revision_before: str,
        graph_revision_after: str,
    ):
        return build_semantic_memory_event(
            record=_graph_delta(version=version, statement=statement).carriers[0],
            prior_record=prior_record,
            repository_id="repository",
            source_id="source",
            transaction_group_id=group,
            operation_fence_id=_digest(f"fence:{group}"),
            writer_epoch=1,
            graph_revision_before=graph_revision_before,
            graph_revision_after=graph_revision_after,
            graph_delta_digest=_digest(f"delta:{statement}"),
            timestamp=timestamp,
        )

    first_event = event_for(
        statement=first_statement,
        group=first_group,
        timestamp=first_timestamp,
        graph_revision_before=initial_state.graph_revision,
        graph_revision_after=first_after,
    )
    second_event = event_for(
        statement=second_statement,
        group=second_group,
        timestamp=second_timestamp,
        graph_revision_before=first_after,
        graph_revision_after=second_after,
    )
    return (
        _single_event_batch(event=first_event, registry=registry, sequence=first_sequence),
        _single_event_batch(event=second_event, registry=registry, sequence=first_sequence + 1),
    )


_EQUAL_VERSION_CONFLICT_ORDERINGS = (
    ("arrival-left", "arrival-right", "arrival-left", "arrival-right", NOW, NOW, None),
    ("arrival-right", "arrival-left", "arrival-right", "arrival-left", NOW, NOW, None),
    ("time-earlier", "time-later", "time-first", "time-second", NOW, NOW + timedelta(seconds=1), None),
    ("time-later", "time-earlier", "time-first", "time-second", NOW + timedelta(seconds=1), NOW, None),
    ("time-tie-left", "time-tie-right", "time-tie-left", "time-tie-right", NOW, NOW, None),
    ("id-ascending-left", "id-ascending-right", "event-id-delta", "event-id-alpha", NOW, NOW, "<"),
    ("id-descending-left", "id-descending-right", "event-id-beta", "event-id-alpha", NOW, NOW, ">"),
)


def _wire_digest(domain: bytes, value: object) -> str:
    return hashlib.sha256(domain + encode_typed_value(value)).hexdigest()


def _persisted_batch_bytes(
    batch,
    *,
    registry: SemanticEventSchemaRegistry,
    source_version: str | None = None,
    invalid_event_digest: bool = False,
    invalid_batch_digest: bool = False,
) -> tuple[bytes, dict[str, object]]:
    payload = batch.model_dump(mode="python")
    payload["event_schema_registry_revision"] = registry.registry_revision
    payload["event_schema_registry_digest"] = registry.registry_digest
    source_events = []
    for current in payload["events"]:
        event = dict(current)
        if source_version is not None:
            event["schema_version"] = source_version
            event.pop("solver_run_id")
            event["event_id"] = semantic_event_id(
                schema_version=source_version,
                transaction_group_id=event["transaction_group_id"],
                operation_fence_id=event["operation_fence_id"],
                graph_revision_after=event["payload"]["graph_revision_after"],
                record_kind=event["payload"]["record_kind"],
                record_id=event["payload"]["record_id"],
                record_version=event["payload"]["metadata"]["version"],
                mutation_kind=event["payload"]["operation"],
            )
        event["event_digest"] = _wire_digest(
            b"memorii.event-envelope.v1\0",
            {key: value for key, value in event.items() if key != "event_digest"},
        )
        if invalid_event_digest:
            event["event_digest"] = "0" * 64
        source_events.append(event)
    payload["events"] = tuple(source_events)
    payload["event_batch_digest"] = _wire_digest(
        b"memorii.semantic-memory-event-batch.v1\0",
        {key: value for key, value in payload.items() if key != "event_batch_digest"},
    )
    if invalid_batch_digest:
        payload["event_batch_digest"] = "0" * 64
    raw = encode_typed_value(
        {
            "schema": "memorii.semantic-memory-event-batch-envelope.v1",
            "payload": payload,
        }
    )
    return raw, payload


def test_persisted_historical_batch_verifies_source_identity_before_upcast() -> None:
    historical = "memorii.semantic-memory-event.v0"
    registry = SemanticEventSchemaRegistry.create(historical_versions=(historical,))
    batch = _batch(
        delta=_graph_delta(),
        state=SemanticReplayState.genesis("repository"),
        before="genesis",
        after="revision-1",
        registry=registry,
    )
    raw, source = _persisted_batch_bytes(batch, registry=registry, source_version=historical)

    decoded = decode_semantic_memory_event_batch(raw, registry=registry)

    assert decoded.events[0].source_schema_version == historical
    assert decoded.events[0].source_event_id == source["events"][0]["event_id"]
    assert decoded.events[0].source_event_digest == source["events"][0]["event_digest"]
    assert decoded.source_event_batch_digest == source["event_batch_digest"]
    assert decoded.events[0].schema_version != historical
    assert (
        replay_semantic_event_batches(
            repository_id="repository", batches=(decoded,), registry=registry
        ).last_event_batch_digest
        == source["event_batch_digest"]
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("future", "unknown, retired, or ambiguous"),
        ("retired", "no deterministic upcaster"),
        ("ambiguous", "unknown, retired, or ambiguous"),
        ("event_digest", "source envelope digest mismatch"),
        ("batch_digest", "source batch digest mismatch"),
    ],
)
def test_persisted_batch_compatibility_fails_closed(mutation: str, message: str) -> None:
    historical = "memorii.semantic-memory-event.v0"
    registry = SemanticEventSchemaRegistry.create(historical_versions=(historical,))
    batch = _batch(
        delta=_graph_delta(),
        state=SemanticReplayState.genesis("repository"),
        before="genesis",
        after="revision-1",
        registry=registry,
    )
    decode_registry = registry
    source_version = historical
    if mutation == "future":
        source_version = "memorii.semantic-memory-event.v999"
    elif mutation == "retired":
        retired = SemanticEventSchemaSupport.create(
            source_schema_version=historical,
            canonical_schema_version=registry.current_write_schema_version,
            envelope_decoder_fingerprint=registry.supported_read_schemas[0].envelope_decoder_fingerprint,
            upcaster_fingerprints=(),
            status="retired",
        )
        decode_registry = registry.model_construct(
            **registry.model_dump(mode="python", exclude={"supported_read_schemas"}),
            supported_read_schemas=(retired, registry.supported_read_schemas[-1]),
        )
    elif mutation == "ambiguous":
        historical_support = registry.supported_read_schemas[0]
        decode_registry = registry.model_construct(
            **registry.model_dump(mode="python", exclude={"supported_read_schemas"}),
            supported_read_schemas=(
                historical_support,
                historical_support,
                registry.supported_read_schemas[-1],
            ),
        )
    raw, _ = _persisted_batch_bytes(
        batch,
        registry=decode_registry,
        source_version=source_version,
        invalid_event_digest=mutation == "event_digest",
        invalid_batch_digest=mutation == "batch_digest",
    )

    with pytest.raises(SemanticEventReplayError, match=message):
        decode_semantic_memory_event_batch(raw, registry=decode_registry)


def test_jsonl_reader_replays_mixed_schema_batches_and_exposes_no_partial_tail(
    tmp_path: Path,
) -> None:
    historical = "memorii.semantic-memory-event.v0"
    registry = SemanticEventSchemaRegistry.create(historical_versions=(historical,))
    first = _batch(
        delta=_graph_delta(),
        state=SemanticReplayState.genesis("repository"),
        before="genesis",
        after="revision-1",
        registry=registry,
    )
    first_raw, _ = _persisted_batch_bytes(first, registry=registry, source_version=historical)
    first_state = replay_semantic_event_batches(
        repository_id="repository",
        batches=(decode_semantic_memory_event_batch(first_raw, registry=registry),),
        registry=registry,
    )
    second = _batch(
        delta=_graph_delta(version=2, statement="second"),
        state=first_state,
        before="revision-1",
        after="revision-2",
        registry=registry,
    )
    second_raw, _ = _persisted_batch_bytes(second, registry=registry)
    path = tmp_path / "mixed-events.jsonl"

    def line(raw: bytes) -> bytes:
        return json.dumps({"canonical_hex": raw.hex()}, sort_keys=True, separators=(",", ":")).encode() + b"\n"

    path.write_bytes(line(first_raw) + line(second_raw))
    repository = FileSemanticEventRepository(path, repository_id="repository", registry=registry)
    batches = repository.read_batches_after(None)
    assert tuple(event.source_schema_version for batch in batches for event in batch.events) == (
        historical,
        registry.current_write_schema_version,
    )
    assert repository.replay_genesis().graph_revision == "revision-2"

    future_raw, _ = _persisted_batch_bytes(
        second,
        registry=registry,
        source_version="memorii.semantic-memory-event.v999",
    )
    path.write_bytes(line(first_raw) + line(second_raw) + line(future_raw))
    with pytest.raises(SemanticEventReplayError):
        repository.read_batches_after(None)


def test_atomic_reader_uses_source_decoder_and_durably_freezes_corrupt_tail(
    tmp_path: Path,
) -> None:
    historical = "memorii.semantic-memory-event.v0"
    registry = SemanticEventSchemaRegistry.create(historical_versions=(historical,))
    first = _batch(
        delta=_graph_delta(),
        state=SemanticReplayState.genesis("semantic_ingestion"),
        before="genesis",
        after="revision-1",
        registry=registry,
        repository_id="semantic_ingestion",
    )
    first_raw, first_source = _persisted_batch_bytes(first, registry=registry, source_version=historical)
    first_state = replay_semantic_event_batches(
        repository_id="semantic_ingestion",
        batches=(decode_semantic_memory_event_batch(first_raw, registry=registry),),
        registry=registry,
    )
    second = _batch(
        delta=_graph_delta(version=2, statement="second"),
        state=first_state,
        before="revision-1",
        after="revision-2",
        registry=registry,
        repository_id="semantic_ingestion",
    )
    second_raw, second_source = _persisted_batch_bytes(
        second,
        registry=registry,
        source_version="memorii.semantic-memory-event.v999",
    )
    backend = JsonlMemoryPlaneStore(tmp_path / "corrupt-tail")
    seeded_records = tuple(
        CanonicalMemoryRecord(
            memory_id=f"semantic_ingestion:event-authority:batch:{sequence:020d}",
            domain=MemoryDomain.EXECUTION,
            text="",
            content={
                "semantic_ingestion_kind": "semantic_event_batch",
                "canonical_hex": raw.hex(),
                "event_batch_digest": source["event_batch_digest"],
            },
            status=CommitStatus.COMMITTED,
            source_kind="semantic_ingestion_event_batch",
            timestamp=NOW,
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )
        for sequence, raw, source in (
            (1, first_raw, first_source),
            (2, second_raw, second_source),
        )
    )
    backend._replace_batches([_PersistedBatch.create(revision=1, data_revision=0, records=seeded_records)])
    plane = MemoryPlaneService(record_store=backend)
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW)
    writers.create_initial_evidence_only(
        admission_id="writer",
        writer_implementation_fingerprint="writer-v1",
        graph_schema_fingerprint="graph-v1",
    )
    store = SemanticIngestionAtomicStore(
        plane,
        writers,
        event_schema_registry=registry,
        now_provider=lambda: NOW,
    )

    with pytest.raises(PreplanningStoreError):
        store.semantic_event_batches()

    freeze = plane.get_record("semantic_ingestion:event-authority:integrity-control")
    assert freeze is not None
    assert tuple(freeze.content["frozen_partition_ids"]) == ("global",)
    assert plane.get_record("semantic_ingestion:event-authority:state") is None


def test_invalid_or_stale_isolation_snapshot_falls_back_to_whole_repository(tmp_path: Path) -> None:
    authoritative = _snapshot()
    holder = [authoritative]
    repository = _repository(tmp_path / "integrity.jsonl", holder)
    stale = _snapshot(coordinate=11)

    control = repository.isolate(
        supplied_snapshot=stale,
        conflicting_byte_digests=(_digest("byte-1"),),
        expected_control_digest=None,
    )

    assert control.frozen_partition_ids == ("partition-1", "partition-2", "partition-3")
    assert repository.current_control() == control


@pytest.mark.parametrize("variant", ["malformed", "cross_repository", "topology_mismatch"])
def test_every_untrusted_isolation_snapshot_family_uses_whole_repository_fallback(
    tmp_path: Path,
    variant: str,
) -> None:
    authoritative = _snapshot()
    if variant == "malformed":
        supplied = authoritative.model_copy(update={"snapshot_digest": _digest("malformed")})
    elif variant == "cross_repository":
        supplied = _foreign_snapshot()
    else:
        supplied = _snapshot(coordinate=12)
    repository = _repository(tmp_path / f"{variant}.jsonl", [authoritative])
    control = repository.isolate(
        supplied_snapshot=supplied,
        conflicting_byte_digests=(_digest("byte-1"),),
        expected_control_digest=None,
    )
    assert control.frozen_partition_ids == ("partition-1", "partition-2", "partition-3")


def test_initial_and_additive_isolation_publish_exact_union_under_control_cas(tmp_path: Path) -> None:
    snapshot = _snapshot()
    repository = _repository(tmp_path / "integrity.jsonl", [snapshot])

    first = repository.isolate(
        supplied_snapshot=snapshot,
        conflicting_byte_digests=(_digest("byte-1"),),
        expected_control_digest=None,
    )
    second = repository.isolate(
        supplied_snapshot=snapshot,
        conflicting_byte_digests=(_digest("byte-2"),),
        expected_control_digest=first.control_digest,
    )

    assert first.frozen_partition_ids == ("partition-1",)
    assert second.frozen_partition_ids == ("partition-1", "partition-2")
    assert second.predecessor_control_digest == first.control_digest
    assert second.control_revision == first.control_revision + 1
    with pytest.raises(ConflictIntegrityError, match="stale_freeze_control"):
        repository.isolate(
            supplied_snapshot=snapshot,
            conflicting_byte_digests=(_digest("byte-3"),),
            expected_control_digest=first.control_digest,
        )

    lines = [json.loads(line) for line in (tmp_path / "integrity.jsonl").read_text(encoding="utf-8").splitlines()]
    additive = lines[1]["isolation_proof"]
    overlap = dict(additive)
    overlap["newly_frozen_partition_ids"] = ["partition-1"]
    with pytest.raises(ValidationError, match="additive disjoint topology"):
        ConflictScopeIsolationProof.model_validate_json(json.dumps(overlap))
    rollback = dict(additive)
    rollback["proof_revision"] = 1
    with pytest.raises(ValidationError, match="initial isolation"):
        ConflictScopeIsolationProof.model_validate_json(json.dumps(rollback))


def test_failed_release_is_byte_identical_and_success_releases_exact_repaired_subset(tmp_path: Path) -> None:
    snapshot = _snapshot()
    path = tmp_path / "integrity.jsonl"
    holder = [snapshot]
    repository = _repository(path, holder)
    first = repository.isolate(
        supplied_snapshot=snapshot,
        conflicting_byte_digests=(_digest("byte-1"),),
        expected_control_digest=None,
    )
    frozen = repository.isolate(
        supplied_snapshot=snapshot,
        conflicting_byte_digests=(_digest("byte-2"),),
        expected_control_digest=first.control_digest,
    )
    corrupt_log = tmp_path / "retained-corrupt.log"
    corrupt_log.write_bytes(b"original-conflicting-bytes")
    original_corrupt_bytes = corrupt_log.read_bytes()
    repair = repository.append_repair(
        repaired_partition_ids=("partition-1",),
        authority_source_digests=(_digest("authority"),),
        retained_conflicting_byte_digests=(_digest("byte-1"),),
    )
    before_failed_release = path.read_bytes()

    with pytest.raises(ConflictIntegrityError, match="stale_freeze_control"):
        repository.release(
            repair_generation_digest=repair.repair_generation_digest,
            supplied_snapshot=snapshot,
            expected_control_digest=first.control_digest,
        )
    assert path.read_bytes() == before_failed_release

    holder[0] = ConflictRepositoryIntegritySnapshot.create(
        repository_id="repository",
        partitions=snapshot.partitions,
        conflict_ledger_start_coordinate=0,
        conflict_ledger_end_coordinate=10,
        last_verified_event_batch_sequence=9,
        store_topology_fingerprint=_digest("changed-topology"),
    )
    with pytest.raises(ConflictIntegrityError, match="invalid_release_proof"):
        repository.release(
            repair_generation_digest=repair.repair_generation_digest,
            supplied_snapshot=snapshot,
            expected_control_digest=frozen.control_digest,
        )
    assert path.read_bytes() == before_failed_release
    holder[0] = snapshot

    released = repository.release(
        repair_generation_digest=repair.repair_generation_digest,
        supplied_snapshot=snapshot,
        expected_control_digest=frozen.control_digest,
    )
    assert released.frozen_partition_ids == ("partition-2",)
    assert corrupt_log.read_bytes() == original_corrupt_bytes


def test_repeated_incident_invalidates_older_repair_until_new_clean_replay(tmp_path: Path) -> None:
    snapshot = _snapshot()
    repository = _repository(tmp_path / "integrity.jsonl", [snapshot])
    frozen = repository.isolate(
        supplied_snapshot=snapshot,
        conflicting_byte_digests=(_digest("byte-1"),),
        expected_control_digest=None,
    )
    old_repair = repository.append_repair(
        repaired_partition_ids=("partition-1",),
        authority_source_digests=(_digest("authority-1"),),
        retained_conflicting_byte_digests=(_digest("byte-1"),),
    )
    assert (
        repository.isolate(
            supplied_snapshot=snapshot,
            conflicting_byte_digests=(_digest("byte-1"),),
            expected_control_digest=frozen.control_digest,
        )
        == frozen
    )
    with pytest.raises(ConflictIntegrityError, match="invalid_release_proof"):
        repository.release(
            repair_generation_digest=old_repair.repair_generation_digest,
            supplied_snapshot=snapshot,
            expected_control_digest=frozen.control_digest,
        )
    new_repair = repository.append_repair(
        repaired_partition_ids=("partition-1",),
        authority_source_digests=(_digest("authority-2"),),
        retained_conflicting_byte_digests=(_digest("byte-1"),),
    )
    assert (
        repository.release(
            repair_generation_digest=new_repair.repair_generation_digest,
            supplied_snapshot=snapshot,
            expected_control_digest=frozen.control_digest,
        ).frozen_partition_ids
        == ()
    )


def test_registry_history_replays_exact_old_coordinate_and_rejects_substitution() -> None:
    registry_v1 = SemanticEventSchemaRegistry.create(registry_revision=1)
    batch = _batch(
        delta=_graph_delta(),
        state=SemanticReplayState.genesis("repository"),
        before="genesis",
        after="revision-1",
        registry=registry_v1,
    )
    registry_v2 = SemanticEventSchemaRegistry.create(
        registry_revision=2,
        historical_versions=("memorii.semantic-memory-event.v0",),
    )
    history = SemanticEventSchemaRegistryHistory.create((registry_v1, registry_v2))
    encoded = encode_semantic_memory_event_batch(batch)

    assert decode_semantic_memory_event_batch(encoded, registry_history=history) == batch
    assert (
        replay_semantic_event_batches(
            repository_id="repository",
            batches=(batch,),
            registry_history=history,
        ).graph_revision
        == "revision-1"
    )

    substituted_v1 = SemanticEventSchemaRegistry.create(
        registry_revision=1,
        historical_versions=("memorii.semantic-memory-event.v0",),
    )
    substituted_history = SemanticEventSchemaRegistryHistory.create((substituted_v1, registry_v2))
    with pytest.raises(SemanticEventReplayError, match="substituted"):
        decode_semantic_memory_event_batch(
            encoded,
            registry_history=substituted_history,
        )


def test_full_state_event_batch_has_distinct_identities_and_replays_exact_update() -> None:
    registry = SemanticEventSchemaRegistry.create()
    genesis = SemanticReplayState.genesis("repository")
    first = _batch(delta=_graph_delta(), state=genesis, before="genesis", after="revision-1")
    first_event = first.events[0]
    assert len({first_event.event_id, first_event.dedupe_key, first_event.payload.record_id}) == 3
    assert first_event.payload.operation == "create"
    state = replay_semantic_event_batches(repository_id="repository", batches=(first,), registry=registry)
    second = _batch(
        delta=_graph_delta(version=2, statement="second"),
        state=state,
        before="revision-1",
        after="revision-2",
    )
    final = replay_semantic_event_batches(
        repository_id="repository", batches=(second,), registry=registry, initial_state=state
    )
    assert second.events[0].payload.operation == "update"
    assert second.events[0].payload.prior_record_digest == first_event.payload.record_digest
    assert final.materialized_records[0].record_version == 2
    assert final.materialized_records[0].record_digest == second.events[0].payload.record_digest


def test_equal_version_conflict_discards_complete_batch_without_changing_prior_state() -> None:
    registry = SemanticEventSchemaRegistry.create()
    genesis = SemanticReplayState.genesis("repository")
    first = _batch(delta=_graph_delta(), state=genesis, before="genesis", after="revision-1")
    state = replay_semantic_event_batches(repository_id="repository", batches=(first,), registry=registry)
    conflicting_event = build_semantic_memory_event(
        record=_graph_delta(statement="conflicting").carriers[0],
        prior_record=None,
        repository_id="repository",
        source_id="source",
        transaction_group_id="different-group",
        operation_fence_id="e" * 64,
        writer_epoch=1,
        graph_revision_before="revision-1",
        graph_revision_after="revision-2",
        graph_delta_digest=_digest("conflicting-delta"),
        timestamp=NOW,
    )
    body = {
        "repository_id": "repository",
        "log_position": type(first.log_position).create(repository_id="repository", sequence=2),
        "source_id": "source",
        "transaction_group_id": "different-group",
        "operation_fence_id": "e" * 64,
        "writer_epoch": 1,
        "event_schema_registry_revision": registry.registry_revision,
        "event_schema_registry_digest": registry.registry_digest,
        "graph_delta_digest": _digest("conflicting-delta"),
        "events": (conflicting_event,),
    }
    from memorii.core.semantic_ingestion import event_replay as event_module

    conflicting_batch = type(first)(
        **body,
        event_batch_digest=event_module._digest(event_module._BATCH_DOMAIN, body),
    )
    with pytest.raises(MemoryIntegrityConflict, match="record/version"):
        replay_semantic_event_batches(
            repository_id="repository",
            batches=(conflicting_batch,),
            registry=registry,
            initial_state=state,
        )
    assert state.materialized_records[0].record_digest == first.events[0].payload.record_digest
    assert state.last_batch_position == first.log_position


@pytest.mark.parametrize(
    (
        "first_statement",
        "second_statement",
        "first_group",
        "second_group",
        "first_timestamp",
        "second_timestamp",
        "event_id_relation",
    ),
    _EQUAL_VERSION_CONFLICT_ORDERINGS,
)
def test_equal_version_conflict_replay_orderings_fail_closed(
    first_statement: str,
    second_statement: str,
    first_group: str,
    second_group: str,
    first_timestamp: datetime,
    second_timestamp: datetime,
    event_id_relation: str | None,
) -> None:
    registry = SemanticEventSchemaRegistry.create()
    initial_state = SemanticReplayState.genesis("repository")
    batches = _equal_version_conflict_batches(
        registry=registry,
        initial_state=initial_state,
        first_statement=first_statement,
        second_statement=second_statement,
        first_group=first_group,
        second_group=second_group,
        first_timestamp=first_timestamp,
        second_timestamp=second_timestamp,
    )
    if event_id_relation is not None:
        assert (batches[0].events[0].source_event_id < batches[1].events[0].source_event_id) == (event_id_relation == "<")

    with pytest.raises(MemoryIntegrityConflict, match="record/version"):
        replay_semantic_event_batches(repository_id="repository", batches=batches, registry=registry, initial_state=initial_state)

    # Candidate state is isolated: neither competing envelope becomes visible.
    assert initial_state == SemanticReplayState.genesis("repository")
    assert initial_state.materialized_records == ()
    assert initial_state.event_bindings == ()


def test_file_repository_rejects_equal_version_conflict_without_changing_reopened_state(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    repository = FileSemanticEventRepository(path, repository_id="repository")
    committed = repository.append_graph_delta(
        graph_delta=_graph_delta(),
        source_id="source",
        transaction_group_id="committed-operation",
        operation_fence_id="f" * 64,
        writer_epoch=1,
        graph_revision_before="genesis",
        graph_revision_after="revision-1",
        timestamp=NOW,
    )
    prior_bytes = path.read_bytes()
    prior_state = repository.replay_genesis()

    with pytest.raises(MemoryIntegrityConflict, match="reservation"):
        repository.append_graph_delta(
            graph_delta=_graph_delta(statement="conflicting"),
            source_id="source",
            transaction_group_id="conflicting-operation",
            operation_fence_id="e" * 64,
            writer_epoch=1,
            graph_revision_before="revision-1",
            graph_revision_after="revision-2",
            timestamp=NOW + timedelta(seconds=1),
        )

    assert path.read_bytes() == prior_bytes
    reopened = FileSemanticEventRepository(path, repository_id="repository")
    assert reopened.read_batches_after(None) == (committed,)
    assert reopened.replay_genesis() == prior_state


def test_file_repository_exact_duplicate_is_idempotent_after_reopen(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    repository = FileSemanticEventRepository(path, repository_id="repository")
    kwargs = {
        "graph_delta": _graph_delta(),
        "source_id": "source",
        "transaction_group_id": "idempotent-operation",
        "operation_fence_id": "f" * 64,
        "writer_epoch": 1,
        "graph_revision_before": "genesis",
        "graph_revision_after": "revision-1",
        "timestamp": NOW,
    }
    committed = repository.append_graph_delta(**kwargs)
    assert repository.append_graph_delta(**kwargs) == committed
    prior_bytes = path.read_bytes()
    prior_state = repository.replay_genesis()

    reopened = FileSemanticEventRepository(path, repository_id="repository")
    retried = reopened.append_graph_delta(**kwargs)
    assert retried == committed
    assert retried.log_position == committed.log_position
    assert path.read_bytes() == prior_bytes
    assert reopened.read_batches_after(None) == (committed,)
    assert reopened.replay_genesis() == prior_state
    assert len(prior_state.event_bindings) == 1
    assert prior_state.event_bindings[0].event_id == committed.events[0].source_event_id

    with pytest.raises(MemoryIntegrityConflict, match="logical retry"):
        reopened.append_graph_delta(**{**kwargs, "graph_delta": _graph_delta(statement="divergent-retry")})
    assert path.read_bytes() == prior_bytes
    assert reopened.read_batches_after(None) == (committed,)
    assert reopened.replay_genesis() == prior_state


def test_process_safe_repository_assigns_one_position_and_reopens_exactly(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    delta = _graph_delta()

    def append() -> str:
        return (
            FileSemanticEventRepository(path, repository_id="repository")
            .append_graph_delta(
                graph_delta=delta,
                source_id="source",
                transaction_group_id="operation",
                operation_fence_id="f" * 64,
                writer_epoch=1,
                graph_revision_before="genesis",
                graph_revision_after="revision-1",
                timestamp=NOW,
            )
            .event_batch_digest
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        digests = tuple(executor.map(lambda _: append(), range(2)))
    assert digests[0] == digests[1]
    reopened = FileSemanticEventRepository(path, repository_id="repository")
    assert len(reopened.read_batches_after(None)) == 1
    assert reopened.replay_genesis().graph_revision == "revision-1"


def test_frozen_partition_rejects_semantic_append_while_proven_unaffected_scope_continues(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()
    integrity = _repository(tmp_path / "integrity.jsonl", [snapshot])
    integrity.isolate(
        supplied_snapshot=snapshot,
        conflicting_byte_digests=(_digest("byte-1"),),
        expected_control_digest=None,
    )
    path = tmp_path / "events.jsonl"
    frozen = FileSemanticEventRepository(
        path,
        repository_id="repository",
        freeze_guard=SemanticEventFreezeGuard(integrity, lambda _: ("partition-1",)),
    )
    with pytest.raises(SemanticEventReplayError, match="scope_frozen"):
        frozen.append_graph_delta(
            graph_delta=_graph_delta(),
            source_id="source",
            transaction_group_id="operation",
            operation_fence_id="f" * 64,
            writer_epoch=1,
            graph_revision_before="genesis",
            graph_revision_after="revision-1",
            timestamp=NOW,
        )
    assert frozen.read_batches_after(None) == ()

    unaffected = FileSemanticEventRepository(
        path,
        repository_id="repository",
        freeze_guard=SemanticEventFreezeGuard(integrity, lambda _: ("partition-2",)),
    )
    assert (
        unaffected.append_graph_delta(
            graph_delta=_graph_delta(),
            source_id="source",
            transaction_group_id="operation",
            operation_fence_id="f" * 64,
            writer_epoch=1,
            graph_revision_before="genesis",
            graph_revision_after="revision-1",
            timestamp=NOW,
        ).log_position.sequence
        == 1
    )


def test_freeze_publication_linearizes_before_concurrent_event_admission(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()
    linearization = ReplayIntegrityLinearization(tmp_path / "integrity.linearization.lock")
    integrity = FileConflictIntegrityRepository(
        tmp_path / "integrity.jsonl",
        repository_id="repository",
        snapshot_provider=lambda: snapshot,
        now_provider=lambda: NOW,
        linearization=linearization,
    )
    events = FileSemanticEventRepository(
        tmp_path / "events.jsonl",
        repository_id="repository",
        freeze_guard=SemanticEventFreezeGuard(integrity, lambda _: ("partition-1",)),
        integrity_linearization=linearization,
    )
    admission_started = Event()

    def append() -> str:
        admission_started.set()
        try:
            events.append_graph_delta(
                graph_delta=_graph_delta(),
                source_id="source",
                transaction_group_id="operation",
                operation_fence_id="f" * 64,
                writer_epoch=1,
                graph_revision_before="genesis",
                graph_revision_after="revision-1",
                timestamp=NOW,
            )
        except SemanticEventReplayError as exc:
            return str(exc)
        return "appended"

    with ThreadPoolExecutor(max_workers=1) as executor:
        with linearization.exclusive():
            pending = executor.submit(append)
            assert admission_started.wait(timeout=5)
            integrity.isolate(
                supplied_snapshot=snapshot,
                conflicting_byte_digests=(_digest("byte-1"),),
                expected_control_digest=None,
            )
        assert pending.result(timeout=5) == "semantic_repository_scope_frozen"
    assert events.read_batches_after(None) == ()


def test_live_integrity_conflict_freezes_and_publishes_pull_attention_after_unlock(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()
    integrity = _repository(tmp_path / "integrity.jsonl", [snapshot])
    attention = FileConflictAttentionRepository(
        tmp_path / "attention.jsonl",
        keys=(
            ConflictCursorKey(
                key_id="key",
                key_epoch=1,
                secret=b"k" * 32,
                valid_from=datetime(2025, 12, 31, tzinfo=UTC),
                expires_at=datetime(2026, 1, 2, tzinfo=UTC),
                signing=True,
            ),
        ),
        now_provider=lambda: NOW,
    )
    events = FileSemanticEventRepository(
        tmp_path / "events.jsonl",
        repository_id="repository",
        integrity_incident_reporter=CanonicalReplayIntegrityIncidentReporter(integrity, attention),
    )
    events.append_graph_delta(
        graph_delta=_graph_delta(),
        source_id="source",
        transaction_group_id="operation",
        operation_fence_id="f" * 64,
        writer_epoch=1,
        graph_revision_before="genesis",
        graph_revision_after="revision-1",
        timestamp=NOW,
    )
    for group in ("conflicting-group-1", "conflicting-group-2"):
        with pytest.raises(MemoryIntegrityConflict, match="reservation"):
            events.append_graph_delta(
                graph_delta=_graph_delta(statement="conflicting"),
                source_id="source",
                transaction_group_id=group,
                operation_fence_id="e" * 64,
                writer_epoch=1,
                graph_revision_before="revision-1",
                graph_revision_after="revision-2",
                timestamp=NOW,
            )
    assert integrity.current_control().frozen_partition_ids == (  # type: ignore[union-attr]
        "partition-1",
        "partition-2",
        "partition-3",
    )
    latest = integrity.latest_incident_evidence()
    assert latest is not None and latest.predecessor_incident_evidence_digest is not None
    page = attention.list_conflicts(
        ConflictAccessContext(
            tenant_id="tenant",
            principal_id="operator",
            principal_binding_digest=_digest("principal"),
            authorized_scope_ids=("partition-1", "partition-2", "partition-3"),
            scope_digest=_digest("access-scope"),
            authorization_snapshot_digest=_digest("authorization"),
        ),
        ConflictListRequest(page_size=10),
    )
    assert page.total_pending == 2
    assert all(item.kind == ConflictKind.STORAGE_INTEGRITY for item in page.items)


def test_repair_coordinates_come_from_actual_clean_event_replay(tmp_path: Path) -> None:
    corrupt_events = FileSemanticEventRepository(tmp_path / "events-corrupt.jsonl", repository_id="repository")
    corrupt_events.append_graph_delta(
        graph_delta=_graph_delta(),
        source_id="source",
        transaction_group_id="operation",
        operation_fence_id="f" * 64,
        writer_epoch=1,
        graph_revision_before="genesis",
        graph_revision_after="revision-1",
        timestamp=NOW,
    )
    retained = corrupt_events.retained_byte_digests()[0]
    clean_events = FileSemanticEventRepository(tmp_path / "events-clean.jsonl", repository_id="repository")
    batch = clean_events.append_graph_delta(
        graph_delta=_graph_delta(),
        source_id="source",
        transaction_group_id="operation",
        operation_fence_id="f" * 64,
        writer_epoch=1,
        graph_revision_before="genesis",
        graph_revision_after="revision-1",
        timestamp=datetime(2026, 8, 2, 0, 0, 1, tzinfo=UTC),
    )
    snapshot = _snapshot(retained_byte_one=retained)
    integrity = FileConflictIntegrityRepository(
        tmp_path / "integrity.jsonl",
        repository_id="repository",
        snapshot_provider=lambda: snapshot,
        clean_replay_verifier=SemanticEventCleanReplayVerifier(
            clean_events,
            retained_corrupt_repository=corrupt_events,
            now_provider=lambda: NOW,
        ),
        now_provider=lambda: NOW,
    )
    integrity.isolate(
        supplied_snapshot=snapshot,
        conflicting_byte_digests=(retained,),
        expected_control_digest=None,
    )
    with pytest.raises(ConflictIntegrityError, match="clean_replay_verification_failed"):
        integrity.append_repair(
            repaired_partition_ids=("partition-1",),
            authority_source_digests=(_digest("detached-authority"),),
            retained_conflicting_byte_digests=(retained,),
        )
    repair = integrity.append_repair(
        repaired_partition_ids=("partition-1",),
        authority_source_digests=(hashlib.sha256(encode_semantic_memory_event_batch(batch)).hexdigest(),),
        retained_conflicting_byte_digests=(retained,),
    )
    assert repair.replay_final_event_batch_sequence == batch.log_position.sequence
    assert repair.replay_final_batch_digest == batch.event_batch_digest
    assert repair.replay_repository_state_digest == clean_events.replay_genesis().state_digest
    assert repair.retained_corrupt_generation_digest == corrupt_events.retained_generation_digest()


def test_store_owned_clean_recovery_builds_and_replays_exact_authority_sources(
    tmp_path: Path,
) -> None:
    corrupt_events = FileSemanticEventRepository(tmp_path / "events-corrupt.jsonl", repository_id="repository")
    corrupt_events.append_graph_delta(
        graph_delta=_graph_delta(),
        source_id="source",
        transaction_group_id="operation",
        operation_fence_id="f" * 64,
        writer_epoch=1,
        graph_revision_before="genesis",
        graph_revision_after="revision-1",
        timestamp=NOW,
    )
    retained = corrupt_events.retained_byte_digests()[0]
    clean_source = FileSemanticEventRepository(tmp_path / "authority-source.jsonl", repository_id="repository")
    batch = clean_source.append_graph_delta(
        graph_delta=_graph_delta(),
        source_id="source",
        transaction_group_id="operation",
        operation_fence_id="f" * 64,
        writer_epoch=1,
        graph_revision_before="genesis",
        graph_revision_after="revision-1",
        timestamp=datetime(2026, 8, 2, 0, 0, 1, tzinfo=UTC),
    )
    canonical_batch = encode_semantic_memory_event_batch(batch)
    authority = SemanticEventCleanAuthorityBatch(
        source_id="authority-batch-1",
        canonical_batch_bytes=canonical_batch,
        source_digest=hashlib.sha256(canonical_batch).hexdigest(),
    )
    request = SemanticEventCleanRecoveryRequest.create(
        repository_id="repository",
        repaired_partition_ids=("partition-1",),
        authority_batches=(authority,),
        retained_conflicting_byte_digests=(retained,),
        retained_corrupt_generation_digest=(corrupt_events.retained_generation_digest()),
    )
    service = SemanticEventCleanRecoveryService(
        clean_generation_root=tmp_path / "clean-generations",
        retained_corrupt_repository=corrupt_events,
        request_provider=lambda repaired, evidence: request,
        now_provider=lambda: NOW,
    )
    snapshot = _snapshot(retained_byte_one=retained)
    integrity = FileConflictIntegrityRepository(
        tmp_path / "integrity-owned.jsonl",
        repository_id="repository",
        snapshot_provider=lambda: snapshot,
        clean_replay_verifier=service,
        now_provider=lambda: NOW,
    )
    frozen = integrity.isolate(
        supplied_snapshot=snapshot,
        conflicting_byte_digests=(retained,),
        expected_control_digest=None,
    )
    lifecycle = PrivilegedSemanticIntegrityLifecycle(integrity)
    repair, released = lifecycle.recover_and_release(
        request,
        supplied_snapshot=snapshot,
        expected_control_digest=frozen.control_digest,
    )

    assert released.frozen_partition_ids == ()
    assert repair.clean_generation_id == request.request_digest
    assert (tmp_path / "clean-generations" / request.request_digest / "request.json").exists()
    assert repair.replay_repository_state_digest == clean_source.replay_genesis().state_digest
    assert lifecycle.current_control() == released


def test_normal_provider_owns_integrity_lifecycle_on_atomic_linearization(
    tmp_path: Path,
) -> None:
    snapshot = ConflictRepositoryIntegritySnapshot.create(
        repository_id="semantic_ingestion",
        partitions=(
            ConflictRepositoryPartitionSnapshot(
                partition_id="global",
                scope_digest=_digest("global-scope"),
                retained_byte_digests=(_digest("retained"),),
            ),
        ),
        conflict_ledger_start_coordinate=0,
        conflict_ledger_end_coordinate=0,
        last_verified_event_batch_sequence=0,
        store_topology_fingerprint=_digest("topology"),
    )
    integrity = FileConflictIntegrityRepository(
        tmp_path / "provider-integrity.jsonl",
        repository_id="semantic_ingestion",
        snapshot_provider=lambda: snapshot,
        now_provider=lambda: NOW,
    )
    lifecycle = PrivilegedSemanticIntegrityLifecycle(integrity)
    provider = ProviderMemoryService(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: NOW,
        semantic_integrity_lifecycle=lifecycle,
    )

    assert provider.semantic_integrity_lifecycle is lifecycle
    assert provider._semantic_atomic_store.semantic_integrity_linearization is lifecycle.linearization


def test_store_owned_clean_recovery_rejects_post_repair_log_mutation(
    tmp_path: Path,
) -> None:
    corrupt_events = FileSemanticEventRepository(tmp_path / "mutated-corrupt.jsonl", repository_id="repository")
    batch = corrupt_events.append_graph_delta(
        graph_delta=_graph_delta(),
        source_id="source",
        transaction_group_id="operation",
        operation_fence_id="f" * 64,
        writer_epoch=1,
        graph_revision_before="genesis",
        graph_revision_after="revision-1",
        timestamp=NOW,
    )
    with (tmp_path / "mutated-corrupt.jsonl").open("ab") as handle:
        handle.write(b"retained-corrupt-tail")
    retained = corrupt_events.retained_byte_digests()[-1]
    canonical_batch = encode_semantic_memory_event_batch(batch)
    authority = SemanticEventCleanAuthorityBatch(
        source_id="authority-batch-1",
        canonical_batch_bytes=canonical_batch,
        source_digest=hashlib.sha256(canonical_batch).hexdigest(),
    )
    request = SemanticEventCleanRecoveryRequest.create(
        repository_id="repository",
        repaired_partition_ids=("partition-1",),
        authority_batches=(authority,),
        retained_conflicting_byte_digests=(retained,),
        retained_corrupt_generation_digest=(corrupt_events.retained_generation_digest()),
    )
    service = SemanticEventCleanRecoveryService(
        clean_generation_root=tmp_path / "mutated-clean",
        retained_corrupt_repository=corrupt_events,
        request_provider=lambda repaired, evidence: request,
        now_provider=lambda: NOW,
    )
    snapshot = _snapshot(retained_byte_one=retained)
    path = tmp_path / "mutated-integrity.jsonl"
    integrity = FileConflictIntegrityRepository(
        path,
        repository_id="repository",
        snapshot_provider=lambda: snapshot,
        clean_replay_verifier=service,
        now_provider=lambda: NOW,
    )
    frozen = integrity.isolate(
        supplied_snapshot=snapshot,
        conflicting_byte_digests=(retained,),
        expected_control_digest=None,
    )
    repair = integrity.append_repair(
        repaired_partition_ids=request.repaired_partition_ids,
        authority_source_digests=request.authority_source_digests,
        retained_conflicting_byte_digests=(retained,),
    )
    clean_log = tmp_path / "mutated-clean" / request.request_digest / "events.jsonl"
    with clean_log.open("ab") as handle:
        handle.write(b"unrelated-same-repository-log\n")
    before = path.read_bytes()

    with pytest.raises(ConflictIntegrityError, match="invalid_release_proof"):
        integrity.release(
            repair_generation_digest=repair.repair_generation_digest,
            supplied_snapshot=snapshot,
            expected_control_digest=frozen.control_digest,
        )
    assert path.read_bytes() == before


def test_signed_checkpoint_tail_equals_genesis_and_rejects_policy_rollback() -> None:
    registry = SemanticEventSchemaRegistry.create()
    genesis = SemanticReplayState.genesis("repository")
    first = _batch(delta=_graph_delta(), state=genesis, before="genesis", after="revision-1")
    first_state = replay_semantic_event_batches(repository_id="repository", batches=(first,), registry=registry)
    second = _batch(
        delta=_graph_delta(version=2, statement="second"),
        state=first_state,
        before="revision-1",
        after="revision-2",
    )
    material = CheckpointKeyMaterial(key_id="checkpoint-key", secret=b"k" * 32)
    signature_authority = DeterministicCheckpointSignatureAuthority(material)
    key = ReplayCheckpointSigningKey.create(
        key_id=material.key_id,
        issuer_id="operator",
        public_key_fingerprint=material.public_key_fingerprint,
        valid_from=datetime(2025, 1, 1, tzinfo=UTC),
    )
    policy = ReplayCheckpointTrustPolicy.create(
        policy_revision=2,
        authorized_repository_id="repository",
        keys=(key,),
    )
    lifecycle = ReplayCheckpointLifecycleState.create(
        repository_id="repository",
        authority_revision=1,
        registry=registry,
        trust_policy=policy,
    )
    authority = ReplayCheckpointResumeAuthority(
        lifecycle=lifecycle,
        registry=registry,
        trust_policy=policy,
        signature_authority_provider=lambda _: signature_authority,
        signing_key_id=material.key_id,
    )
    projection_bindings = projection_history_bindings("repository")
    bundle = create_replay_checkpoint(
        state=first_state,
        watermark_batch=first,
        writer_epoch=1,
        authority=authority,
        created_at=NOW,
        projection_history_bindings=projection_bindings,
    )
    with pytest.raises(
        SemanticEventReplayError,
        match="projection history verifier is required",
    ):
        validate_replay_checkpoint(bundle, authority=authority)
    checkpoint_verifier = ExactProjectionHistoryVerifier(
        bindings=projection_bindings,
        graph_revision=first_state.graph_revision,
    )
    checkpoint_snapshot = validate_replay_checkpoint(
        bundle,
        authority=authority,
        projection_history_verifier=checkpoint_verifier,
    )
    checkpoint_bytes = encode_typed_value(bundle.model_dump(mode="python"))
    checkpoint_tail = replay_semantic_checkpoint_tail(
        bundle,
        tail_batches=(second,),
        authority=authority,
        projection_history_verifier=checkpoint_verifier,
    )
    from_genesis = replay_semantic_event_batches(repository_id="repository", batches=(first, second), registry=registry)
    assert checkpoint_tail == from_genesis
    checkpoint_tail_authority = encode_typed_value(
        {
            "graph_state": checkpoint_tail.model_dump(mode="python"),
            "projection_history_bindings": tuple(
                item.model_dump(mode="python") for item in bundle.checkpoint.projection_history_bindings
            ),
        }
    )
    genesis_authority = encode_typed_value(
        {
            "graph_state": from_genesis.model_dump(mode="python"),
            "projection_history_bindings": tuple(item.model_dump(mode="python") for item in projection_bindings),
        }
    )
    assert checkpoint_tail_authority == genesis_authority
    for (
        first_statement,
        second_statement,
        first_group,
        second_group,
        first_timestamp,
        second_timestamp,
        event_id_relation,
    ) in _EQUAL_VERSION_CONFLICT_ORDERINGS:
        if event_id_relation == ">":
            # Event IDs bind graph revisions. The checkpoint tail therefore
            # uses a different deterministic pair to exercise descending IDs.
            first_group, second_group = "event-id-delta", "event-id-gamma"
        conflicting_tail = _equal_version_conflict_batches(
            registry=registry,
            initial_state=checkpoint_snapshot,
            first_statement=first_statement,
            second_statement=second_statement,
            first_group=first_group,
            second_group=second_group,
            first_timestamp=first_timestamp,
            second_timestamp=second_timestamp,
        )
        if event_id_relation is not None:
            assert (
                conflicting_tail[0].events[0].source_event_id < conflicting_tail[1].events[0].source_event_id
            ) == (event_id_relation == "<")
        with pytest.raises(MemoryIntegrityConflict, match="record/version"):
            replay_semantic_checkpoint_tail(
                bundle,
                tail_batches=conflicting_tail,
                authority=authority,
                projection_history_verifier=checkpoint_verifier,
            )
        with pytest.raises(MemoryIntegrityConflict, match="record/version"):
            replay_semantic_event_batches(
                repository_id="repository",
                batches=(first, *conflicting_tail),
                registry=registry,
            )
        assert validate_replay_checkpoint(
            bundle,
            authority=authority,
            projection_history_verifier=checkpoint_verifier,
        ) == checkpoint_snapshot
        assert encode_typed_value(bundle.model_dump(mode="python")) == checkpoint_bytes
        assert checkpoint_snapshot.last_batch_position == first.log_position
        assert checkpoint_snapshot.materialized_records == first_state.materialized_records
        assert checkpoint_snapshot.event_bindings == first_state.event_bindings
    with pytest.raises(SemanticEventReplayError, match="invalid|rolled back"):
        validate_replay_checkpoint(
            bundle,
            authority=ReplayCheckpointResumeAuthority(
                lifecycle=lifecycle,
                registry=registry,
                trust_policy=policy.model_copy(update={"policy_revision": 1}),
                signature_authority_provider=lambda _: signature_authority,
                signing_key_id=material.key_id,
            ),
            projection_history_verifier=ExactProjectionHistoryVerifier(
                bindings=projection_bindings,
                graph_revision=first_state.graph_revision,
            ),
        )


def _nested_model_types(value: object, path: str = "") -> dict[str, type[BaseModel]]:
    if isinstance(value, BaseModel):
        nested = {path: type(value)} if path else {}
        for field_name in type(value).model_fields:
            nested.update(
                _nested_model_types(
                    getattr(value, field_name),
                    f"{path}.{field_name}" if path else field_name,
                )
            )
        return nested
    if isinstance(value, (tuple, list)):
        nested = {}
        for index, item in enumerate(value):
            nested.update(_nested_model_types(item, f"{path}[{index}]"))
        return nested
    return {}


def test_next_canonical_graph_record_versions_preserves_typed_nested_contracts() -> None:
    records = all_canonical_graph_records(repository_id="repository")
    advanced = next_canonical_graph_record_versions(
        records,
        graph_revision_before="revision-all-kinds",
    )

    assert len(records) == len(advanced) == 12
    for original, current in zip(records, advanced, strict=True):
        assert type(current) is type(original)
        assert _nested_model_types(current) == _nested_model_types(original)

        original_values = original.model_dump(mode="python")
        current_values = current.model_dump(mode="python")
        original_values.pop("record_digest")
        current_values.pop("record_digest")
        original_values.pop("record_version")
        current_values.pop("record_version")
        if original.record_kind == "identity_lineage":
            for values in (original_values, current_values):
                values.pop("identity_lineage_id")
                values.pop("statement_digest")
                transition = values["transition"]
                for field_name in (
                    "transition_digest",
                    "graph_revision_before",
                    "lineage_snapshot_before_digest",
                ):
                    transition.pop(field_name)
            assert current.record_version == 1
            assert current.transition.graph_revision_before == "revision-all-kinds"
            assert (
                current.transition.lineage_snapshot_before_digest
                == original.transition.lineage_snapshot_after_digest
            )
        else:
            assert current.record_version == original.record_version + 1
        assert current_values == original_values

        round_tripped = type(current).model_validate(current.model_dump(mode="python"))
        assert round_tripped == current
        assert round_tripped.record_digest == current.record_digest


def test_all_graph_record_kinds_survive_signed_checkpoint_tail_and_genesis_replay() -> None:
    registry = SemanticEventSchemaRegistry.create()
    records = all_canonical_graph_records(repository_id="repository")
    owning_kinds = {
        "claim_assertion",
        "action_revision",
        "identity_lineage",
        "temporal_transition",
    }
    delta_body = {
        "kind": "semantic_graph_delta",
        "operation_id": "complete-graph-records",
        "carriers": tuple(
            sorted(
                (item for item in records if item.record_kind in owning_kinds),
                key=lambda item: (item.record_kind, item.record_digest),
            )
        ),
        "graph_records": tuple(
            sorted(
                (item for item in records if item.record_kind not in owning_kinds),
                key=lambda item: (item.record_kind, item.record_digest),
            )
        ),
        "terminal_binding_sets": (),
    }
    # Derive the digest from the model's persisted representation, exactly
    # as the accepted-terminal factory does: the discriminated carrier union
    # serializes to a mapping a hand-built body cannot reproduce.
    delta = SemanticGraphDelta(
        **delta_body,
        delta_digest=contract_digest(
            b"memorii.semantic-ingestion.graph-delta.v1",
            SemanticGraphDelta.model_construct(
                **delta_body, delta_digest="0" * 64
            ).model_dump(mode="python", exclude={"delta_digest"}),
        ),
    )
    genesis = SemanticReplayState.genesis("repository")
    first = _batch(
        delta=delta,
        state=genesis,
        before="genesis",
        after="revision-all-kinds",
        group="all-kinds",
        fence="all-kinds-fence",
        registry=registry,
    )
    first_state = replay_semantic_event_batches(
        repository_id="repository", batches=(first,), registry=registry
    )
    assert tuple(item.record_kind for item in first_state.materialized_records) == tuple(
        sorted(item.record_kind for item in records)
    )

    tail_records = next_canonical_graph_record_versions(
        records,
        graph_revision_before="revision-all-kinds",
    )
    tail_body = {
        "kind": "semantic_graph_delta",
        "operation_id": "complete-graph-records:update",
        "carriers": tuple(
            sorted(
                (item for item in tail_records if item.record_kind in owning_kinds),
                key=lambda item: (item.record_kind, item.record_digest),
            )
        ),
        "graph_records": tuple(
            sorted(
                (item for item in tail_records if item.record_kind not in owning_kinds),
                key=lambda item: (item.record_kind, item.record_digest),
            )
        ),
        "terminal_binding_sets": (),
    }
    tail_delta = SemanticGraphDelta(
        **tail_body,
        delta_digest=contract_digest(
            b"memorii.semantic-ingestion.graph-delta.v1",
            SemanticGraphDelta.model_construct(
                **tail_body, delta_digest="0" * 64
            ).model_dump(mode="python", exclude={"delta_digest"}),
        ),
    )
    second = _batch(
        delta=tail_delta,
        state=first_state,
        before="revision-all-kinds",
        after="revision-tail",
        group="tail-update",
        fence="tail-update-fence",
        registry=registry,
    )
    material = CheckpointKeyMaterial(
        key_id="all-kinds-checkpoint-key", secret=b"a" * 32
    )
    signature_authority = DeterministicCheckpointSignatureAuthority(material)
    key = ReplayCheckpointSigningKey.create(
        key_id=material.key_id,
        issuer_id="operator",
        public_key_fingerprint=material.public_key_fingerprint,
        valid_from=datetime(2025, 1, 1, tzinfo=UTC),
    )
    policy = ReplayCheckpointTrustPolicy.create(
        policy_revision=1,
        authorized_repository_id="repository",
        keys=(key,),
    )
    lifecycle = ReplayCheckpointLifecycleState.create(
        repository_id="repository",
        authority_revision=1,
        registry=registry,
        trust_policy=policy,
    )
    authority = ReplayCheckpointResumeAuthority(
        lifecycle=lifecycle,
        registry=registry,
        trust_policy=policy,
        signature_authority_provider=lambda _: signature_authority,
        signing_key_id=material.key_id,
    )
    bindings = projection_history_bindings("repository")
    bundle = create_replay_checkpoint(
        state=first_state,
        watermark_batch=first,
        writer_epoch=1,
        authority=authority,
        created_at=NOW,
        projection_history_bindings=bindings,
    )
    from_checkpoint = replay_semantic_checkpoint_tail(
        bundle,
        tail_batches=(second,),
        authority=authority,
        projection_history_verifier=ExactProjectionHistoryVerifier(
            bindings=bindings,
            graph_revision=first_state.graph_revision,
        ),
    )
    from_genesis = replay_semantic_event_batches(
        repository_id="repository",
        batches=(first, second),
        registry=registry,
    )

    assert from_checkpoint == from_genesis
    assert encode_typed_value(from_checkpoint.model_dump(mode="python")) == (
        encode_typed_value(from_genesis.model_dump(mode="python"))
    )
    assert len(from_checkpoint.materialized_records) == 13
    assert {item.record_kind for item in from_checkpoint.materialized_records} == {
        item.record_kind for item in records
    }

    for phase, batch in (("genesis", first), ("checkpoint_tail", second)):
        for record_kind in sorted(item.record_kind for item in records):
            payload = batch.model_dump(mode="python")
            events = list(payload["events"])
            event_index = next(
                index
                for index, event in enumerate(events)
                if event["payload"]["record_kind"] == record_kind
            )
            event = dict(events[event_index])
            event_payload = dict(event["payload"])
            entity = dict(event_payload["entity"])
            inner_record = dict(entity["record"])
            inner_record["operation_id"] = (
                f"tampered:{phase}:{record_kind}"
            )
            entity["record"] = inner_record
            event_payload["entity"] = entity
            event["payload"] = event_payload
            event["event_digest"] = _wire_digest(
                b"memorii.event-envelope.v1\0",
                {
                    key: value
                    for key, value in event.items()
                    if key != "event_digest"
                },
            )
            events[event_index] = event
            payload["events"] = tuple(events)
            payload["event_batch_digest"] = _wire_digest(
                b"memorii.semantic-memory-event-batch.v1\0",
                {
                    key: value
                    for key, value in payload.items()
                    if key != "event_batch_digest"
                },
            )
            raw = encode_typed_value(
                {
                    "schema": "memorii.semantic-memory-event-batch-envelope.v1",
                    "payload": payload,
                }
            )
            with pytest.raises((SemanticEventReplayError, ValueError)):
                decode_semantic_memory_event_batch(raw, registry=registry)


@pytest.mark.parametrize(
    "mutation",
    (
        "key_expiry",
        "key_retirement",
        "key_revocation",
        "key_compromise",
        "key_id",
        "signature",
        "checkpoint_digest",
        "snapshot",
        "watermark",
        "registry",
        "projection_binding_omission",
        "projection_binding_substitution",
    ),
)
def test_checkpoint_mutation_families_never_expose_state(mutation: str) -> None:
    registry = SemanticEventSchemaRegistry.create()
    genesis = SemanticReplayState.genesis("repository")
    first = _batch(
        delta=_graph_delta(),
        state=genesis,
        before="genesis",
        after="revision-1",
    )
    state = replay_semantic_event_batches(repository_id="repository", batches=(first,), registry=registry)
    material = CheckpointKeyMaterial(key_id="checkpoint-key", secret=b"k" * 32)
    signature_authority = DeterministicCheckpointSignatureAuthority(material)
    clock = [NOW]
    key = ReplayCheckpointSigningKey.create(
        key_id=material.key_id,
        issuer_id="operator",
        public_key_fingerprint=material.public_key_fingerprint,
        valid_from=NOW - timedelta(days=1),
        valid_until=(NOW + timedelta(seconds=1) if mutation == "key_expiry" else None),
    )
    policy = ReplayCheckpointTrustPolicy.create(
        policy_revision=1,
        authorized_repository_id="repository",
        keys=(key,),
    )
    lifecycle = ReplayCheckpointLifecycleState.create(
        repository_id="repository",
        authority_revision=1,
        registry=registry,
        trust_policy=policy,
    )
    authority = ReplayCheckpointResumeAuthority(
        lifecycle=lifecycle,
        registry=registry,
        trust_policy=policy,
        signature_authority_provider=lambda _: signature_authority,
        signing_key_id=material.key_id,
        current_time_provider=lambda: clock[0],
    )
    bundle = create_replay_checkpoint(
        state=state,
        watermark_batch=first,
        writer_epoch=1,
        authority=authority,
        created_at=NOW,
        projection_history_bindings=projection_history_bindings("repository"),
    )
    mutated_bundle = bundle
    mutated_authority = authority
    if mutation == "key_expiry":
        clock[0] = NOW + timedelta(seconds=2)
    elif mutation in {"key_retirement", "key_revocation", "key_compromise"}:
        changed_key = ReplayCheckpointSigningKey.create(
            key_id=material.key_id,
            issuer_id="operator",
            public_key_fingerprint=material.public_key_fingerprint,
            valid_from=NOW - timedelta(days=1),
            status=(
                "retired" if mutation == "key_retirement" else ("revoked" if mutation == "key_revocation" else "active")
            ),
            retired_at=(NOW if mutation == "key_retirement" else None),
            revoked_at=(NOW if mutation == "key_revocation" else None),
            compromise_effective_at=(NOW if mutation == "key_compromise" else None),
        )
        changed_policy = ReplayCheckpointTrustPolicy.create(
            policy_revision=2,
            authorized_repository_id="repository",
            keys=(changed_key,),
        )
        changed_lifecycle = ReplayCheckpointLifecycleState.create(
            repository_id="repository",
            authority_revision=2,
            registry=registry,
            trust_policy=changed_policy,
            predecessor_authority_digest=lifecycle.authority_digest,
        )
        with pytest.raises(SemanticEventReplayError):
            ReplayCheckpointResumeAuthority(
                lifecycle=changed_lifecycle,
                registry=registry,
                trust_policy=changed_policy,
                signature_authority_provider=lambda _: signature_authority,
                signing_key_id=material.key_id,
                current_time_provider=lambda: NOW,
            )
        return
    elif mutation in {"key_id", "signature", "checkpoint_digest"}:
        field = {
            "key_id": "signing_key_id",
            "signature": "signature",
            "checkpoint_digest": "checkpoint_digest",
        }[mutation]
        checkpoint = bundle.checkpoint.model_copy(
            update={field: ("other-key" if mutation == "key_id" else _digest(mutation))}
        )
        mutated_bundle = bundle.model_copy(update={"checkpoint": checkpoint})
    elif mutation == "snapshot":
        mutated_bundle = bundle.model_copy(update={"materialized_snapshot": genesis})
    elif mutation == "watermark":
        second = _batch(
            delta=_graph_delta(version=2, statement="second"),
            state=state,
            before="revision-1",
            after="revision-2",
        )
        mutated_bundle = bundle.model_copy(update={"watermark_batch": second})
    elif mutation.startswith("projection_binding_"):
        bindings = bundle.checkpoint.projection_history_bindings
        if mutation == "projection_binding_omission":
            changed_bindings = ()
        else:
            temporal = ProjectionHistoryReplayBinding.create(
                projection_kind="temporal",
                repository_id="repository",
                history_prefix_digest=bindings[0].history_prefix_digest,
                active_pointer_digest=_digest("substituted-active-pointer"),
                generation_digest=bindings[0].generation_digest,
            )
            changed_bindings = (temporal, bindings[1])
        checkpoint = bundle.checkpoint.model_copy(update={"projection_history_bindings": changed_bindings})
        mutated_bundle = bundle.model_copy(update={"checkpoint": checkpoint})
    else:
        registry_v2 = SemanticEventSchemaRegistry.create(registry_revision=2)
        history = SemanticEventSchemaRegistryHistory.create((registry, registry_v2))
        changed_lifecycle = ReplayCheckpointLifecycleState.create(
            repository_id="repository",
            authority_revision=2,
            registry=registry_v2,
            registry_history=history,
            trust_policy=policy,
            predecessor_authority_digest=lifecycle.authority_digest,
        )
        mutated_authority = ReplayCheckpointResumeAuthority(
            lifecycle=changed_lifecycle,
            registry=registry_v2,
            registry_history=history,
            trust_policy=policy,
            signature_authority_provider=lambda _: signature_authority,
            signing_key_id=material.key_id,
            current_time_provider=lambda: NOW,
        )

    exposed = None
    with pytest.raises((SemanticEventReplayError, ValidationError, ValueError)):
        exposed = validate_replay_checkpoint(
            mutated_bundle,
            authority=mutated_authority,
            projection_history_verifier=ExactProjectionHistoryVerifier(
                bindings=bundle.checkpoint.projection_history_bindings,
                graph_revision=state.graph_revision,
            ),
        )
    assert exposed is None


class _ExactSemanticConflictBindingVerifier:
    def __init__(self, expected: SemanticConflictReplayBinding) -> None:
        self._expected = expected

    def validate_semantic_conflict_replay_binding(
        self,
        binding: SemanticConflictReplayBinding,
    ) -> None:
        if binding != self._expected:
            raise ValueError("semantic conflict replay binding diverged")


def _conflict_authority_record(
    memory_id: str,
    *,
    immutable_coordinate: int | None,
    payload: object | None = None,
) -> CanonicalMemoryRecord:
    record_type = (
        "introduction"
        if ":introduction:" in memory_id
        else "transition"
        if ":transition:" in memory_id
        else "pointer_history"
        if ":pointer-history:" in memory_id
        else "active_pointer"
        if ":pointer:" in memory_id
        else "resolver_pointer"
        if ":resolver-pointer:" in memory_id
        else "resolver_authority"
        if ":resolver:" in memory_id
        else "ledger_head"
    )
    raw = encode_typed_value(payload if payload is not None else {"record_id": memory_id})
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "authority_schema": "memorii.semantic-conflict-authority.v1",
            "authority_record_type": record_type,
            "immutable_record_coordinate": immutable_coordinate,
            "canonical_hex": raw.hex(),
            "authority_digest": hashlib.sha256(raw).hexdigest(),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_conflict_authority",
        timestamp=NOW,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _semantic_conflict_replay_binding(
    records: tuple[str, ...],
    *,
    storage: Path,
) -> SemanticConflictReplayBinding:
    """Derive the authority only by real terminal prepare/CAS/reopen paths."""

    if not records:
        return SemanticConflictReplayBinding.genesis("semantic_ingestion")
    from tests.fixtures.semantic_ingestion.semantic_terminal_fixture import handoff
    from tests.unit.core.semantic_ingestion.test_semantic_terminal_persistence import (
        AUTHORIZATION,
        _activate,
        _setup,
    )

    plane, writers, store, binding, fence, service, repository = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(storage),
        scope_ids=frozenset({"scope:a"}),
        with_test_conflict_authority=True,
    )
    first = accepted_terminal(
        operation_id=fence.operation_id,
        valid_start=NOW,
        valid_end=NOW + timedelta(days=2),
    )
    _activate(repository, fence, first)
    service.persist(fence=fence, terminal=first, authorization_verifier=AUTHORIZATION)
    required_successors = 2 if any(":transition:" in item for item in records) else 1
    for index, value in enumerate(("initech", "umbrella"), start=2):
        if index > required_successors + 1:
            break
        # Admission snapshots the current graph revision.  Handoff is only
        # valid after its predecessor terminal has advanced that revision.
        _, successor = handoff(
            plane,
            coordinate=f"replay-authority-{index}",
            scope_ids=frozenset({"scope:a"}),
            atomic_store=store,
            writer_binding=binding,
        )
        terminal = accepted_terminal(
            operation_id=successor.operation_id,
            object_logical_entity_id=f"entity:{value}",
            object_entity_revision_id=f"entity-revision:{value}:v1",
            valid_start=NOW,
            valid_end=NOW + timedelta(days=2),
        )
        _activate(repository, successor, terminal)
        service.persist(fence=successor, terminal=terminal, authorization_verifier=AUTHORIZATION)

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage))
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: NOW,
    )
    reopened = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: NOW,
    )
    return reopened.projection_history.semantic_conflict_replay_binding()


def test_semantic_conflict_derivation_and_replay_matrix_is_byte_exact(tmp_path: Path) -> None:
    """The typed replay closure is insertion-order independent and checkpoint-bound."""

    cases = (
        (
            "genesis",
            (),
        ),
        (
            "coalesced-temporal-trust",
            (
                "semantic_ingestion:conflict-authority:pointer:conflict-a",
                "semantic_ingestion:conflict-authority:resolver:authority-a",
                "semantic_ingestion:conflict-authority:introduction:conflict-a",
                "semantic_ingestion:conflict-authority:pointer-history:conflict-a:1",
                "semantic_ingestion:conflict-authority:resolver-pointer:tenant-a:renderer-a",
            ),
        ),
        (
            "successor-and-checkpoint-tail",
            (
                "semantic_ingestion:conflict-authority:introduction:conflict-a",
                "semantic_ingestion:conflict-authority:transition:conflict-a:2",
                "semantic_ingestion:conflict-authority:pointer-history:conflict-a:1",
                "semantic_ingestion:conflict-authority:pointer-history:conflict-a:2",
                "semantic_ingestion:conflict-authority:pointer:conflict-a",
            ),
        ),
    )
    registry = SemanticEventSchemaRegistry.create()
    genesis = SemanticReplayState.genesis("semantic_ingestion")
    batch = _batch(
        delta=_graph_delta(), state=genesis, before="genesis", after="revision-1",
        repository_id="semantic_ingestion",
    )
    state = replay_semantic_event_batches(repository_id="semantic_ingestion", batches=(batch,), registry=registry)
    material = CheckpointKeyMaterial(key_id="conflict-binding-key", secret=b"c" * 32)
    signature_authority = DeterministicCheckpointSignatureAuthority(material)
    key = ReplayCheckpointSigningKey.create(
        key_id=material.key_id,
        issuer_id="operator",
        public_key_fingerprint=material.public_key_fingerprint,
        valid_from=NOW - timedelta(days=1),
    )
    policy = ReplayCheckpointTrustPolicy.create(
        policy_revision=1,
        authorized_repository_id="semantic_ingestion",
        keys=(key,),
    )
    lifecycle = ReplayCheckpointLifecycleState.create(
        repository_id="semantic_ingestion",
        authority_revision=1,
        registry=registry,
        trust_policy=policy,
    )
    authority = ReplayCheckpointResumeAuthority(
        lifecycle=lifecycle,
        registry=registry,
        trust_policy=policy,
        signature_authority_provider=lambda _: signature_authority,
        signing_key_id=material.key_id,
    )
    projection_bindings = projection_history_bindings("semantic_ingestion")
    # One real durable terminal publication/reopen proves the store boundary.
    # The remaining entries are deliberately only replay/checkpoint inputs;
    # they must not multiply the multi-minute terminal setup per ordering.
    binding = _semantic_conflict_replay_binding(
        cases[-1][1], storage=tmp_path / "durable-baseline"
    )
    for _, _record_ids in cases:
        bundle = create_replay_checkpoint(
            state=state,
            watermark_batch=batch,
            writer_epoch=1,
            authority=authority,
            created_at=NOW,
            projection_history_bindings=projection_bindings,
            semantic_conflict_replay_binding=binding,
        )
        assert replay_semantic_checkpoint_tail(
            bundle,
            tail_batches=(),
            authority=authority,
            projection_history_verifier=ExactProjectionHistoryVerifier(
                bindings=projection_bindings,
                graph_revision=state.graph_revision,
            ),
            semantic_conflict_verifier=_ExactSemanticConflictBindingVerifier(binding),
        ) == state


def test_semantic_conflict_replay_binding_rejects_every_prefix_and_pointer_mutation(tmp_path: Path) -> None:
    """No mutated nonempty conflict authority binding can expose a checkpoint."""

    binding = _semantic_conflict_replay_binding(
        (
            "semantic_ingestion:conflict-authority:introduction:conflict-a",
            "semantic_ingestion:conflict-authority:pointer-history:conflict-a:1",
            "semantic_ingestion:conflict-authority:pointer:conflict-a",
        ),
        storage=tmp_path / "authority",
    )
    mutations = (
        {"immutable_record_count": binding.immutable_record_count + 1},
        {"immutable_record_prefix_digest": _digest("mutated-prefix")},
        {"last_record_id": "semantic_ingestion:conflict-authority:introduction:other"},
        {"pointer_history_count": binding.pointer_history_count + 1},
        {"current_pointer_set_digest": _digest("mutated-pointer")},
        {"authority_pointer_set_digest": _digest("mutated-authority-pointer")},
        {"repository_id": "other-repository"},
    )
    registry = SemanticEventSchemaRegistry.create()
    state = SemanticReplayState.genesis("semantic_ingestion")
    batch = _batch(
        delta=_graph_delta(), state=state, before="genesis", after="revision-1",
        repository_id="semantic_ingestion",
    )
    state = replay_semantic_event_batches(repository_id="semantic_ingestion", batches=(batch,), registry=registry)
    material = CheckpointKeyMaterial(key_id="conflict-mutation-key", secret=b"m" * 32)
    signature_authority = DeterministicCheckpointSignatureAuthority(material)
    key = ReplayCheckpointSigningKey.create(
        key_id=material.key_id,
        issuer_id="operator",
        public_key_fingerprint=material.public_key_fingerprint,
        valid_from=NOW - timedelta(days=1),
    )
    policy = ReplayCheckpointTrustPolicy.create(
        policy_revision=1,
        authorized_repository_id="semantic_ingestion",
        keys=(key,),
    )
    lifecycle = ReplayCheckpointLifecycleState.create(
        repository_id="semantic_ingestion",
        authority_revision=1,
        registry=registry,
        trust_policy=policy,
    )
    authority = ReplayCheckpointResumeAuthority(
        lifecycle=lifecycle,
        registry=registry,
        trust_policy=policy,
        signature_authority_provider=lambda _: signature_authority,
        signing_key_id=material.key_id,
    )
    bindings = projection_history_bindings("semantic_ingestion")
    bundle = create_replay_checkpoint(
        state=state,
        watermark_batch=batch,
        writer_epoch=1,
        authority=authority,
        created_at=NOW,
        projection_history_bindings=bindings,
        semantic_conflict_replay_binding=binding,
    )
    for update in mutations:
        exposed = None
        mutated = binding.model_copy(update=update)
        checkpoint = bundle.checkpoint.model_copy(
            update={"semantic_conflict_replay_binding": mutated}
        )
        with pytest.raises((SemanticEventReplayError, ValidationError, ValueError)):
            exposed = validate_replay_checkpoint(
                bundle.model_copy(update={"checkpoint": checkpoint}),
                authority=authority,
                projection_history_verifier=ExactProjectionHistoryVerifier(
                    bindings=bindings,
                    graph_revision=state.graph_revision,
                ),
                semantic_conflict_verifier=_ExactSemanticConflictBindingVerifier(binding),
            )
        assert exposed is None


def test_forged_carrier_error_surface_is_pinned() -> None:
    """Bypass-constructed carriers reject with the exact closed error."""

    valid = _graph_delta(version=1, statement="error-surface").carriers[0]
    forged = valid.model_copy(update={"record_digest": "0" * 64})
    with pytest.raises(SemanticEventReplayError, match="semantic event carrier validation failed"):
        build_semantic_memory_event(
            record=forged,
            prior_record=None,
            repository_id="repository",
            source_id="source",
            transaction_group_id="group",
            operation_fence_id=_digest("fence:error-surface"),
            writer_epoch=1,
            graph_revision_before="genesis",
            graph_revision_after="revision-1",
            graph_delta_digest=_digest("delta:error-surface"),
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        )
