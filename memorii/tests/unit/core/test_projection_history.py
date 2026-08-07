from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Literal

import pytest
from memorii.core.memory_evolution.conflict_attention import (
    SemanticConflictAuthorityCommitInput,
)
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.memory_evolution.projection_history import (
    ProjectionCommitRequest,
    ProjectionHistoryError,
    ProjectionHistoryRepository,
)
from memorii.core.memory_evolution.semantic_state import (
    ActiveTemporalProjectionPointer,
    ProjectionEvidenceRecord,
    SemanticAssertionKey,
    SemanticClaimSlotKey,
    SemanticClaimValueKey,
    TemporalProjectionHistoryEntry,
    TemporalProjectionRecord,
    TrustProjectionRecord,
    projection_contract_digest,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionError,
    SemanticWriterAdmissionStore,
    SemanticWriterWriteAuthorization,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    JsonlMemoryPlaneStore,
    _PersistedBatch,
)
from memorii.core.semantic_ingestion.contracts import TimeInterval

REPOSITORY_ID = "semantic_ingestion"
T0 = datetime(2026, 8, 3, 12, tzinfo=UTC)


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


class _Clock:
    def __init__(self, *values: datetime) -> None:
        self._values = values
        self._index = 0

    def __call__(self) -> datetime:
        value = self._values[min(self._index, len(self._values) - 1)]
        self._index += 1
        return value


def _projection_pair(
    *,
    version: int,
    outcome: Literal["pass", "contested"],
) -> tuple[TemporalProjectionRecord, TrustProjectionRecord]:
    if outcome == "contested":
        evidence = tuple(
            ProjectionEvidenceRecord(
                candidate_id=candidate_id,
                candidate_digest=_digest(candidate_id),
                authority_relation="contested_top",
            )
            for candidate_id in ("candidate-a", "candidate-z")
        )
    else:
        evidence = (
            ProjectionEvidenceRecord(
                candidate_id="candidate-high-authority",
                candidate_digest=_digest("candidate-high-authority"),
                authority_relation="winner",
            ),
            ProjectionEvidenceRecord(
                candidate_id="candidate-low-authority",
                candidate_digest=_digest("candidate-low-authority"),
                authority_relation="retained_noncurrent",
            ),
        )
    common = {
        "projection_id": _digest(f"projection-{version}"),
        "repository_id": REPOSITORY_ID,
        "source_record_kind": "claim_assertion",
        "source_record_id": "alice-employer",
        "source_record_version": version,
        "source_record_digest": _digest(f"source-{version}"),
        "outcome": outcome,
        "evidence": evidence,
    }
    temporal = TemporalProjectionRecord.create(
        **common,
        temporal_policy_fingerprint=_digest("temporal-policy"),
        valid_interval=TimeInterval(
            start=T0 + timedelta(days=version),
            end=None,
        ),
    )
    trust = TrustProjectionRecord.create(
        **common,
        trust_policy_fingerprint=_digest("trust-policy"),
        arbitration_as_of=T0,
    )
    return temporal, trust


def _request(
    operation: int,
    *,
    outcome: Literal["pass", "contested"],
) -> ProjectionCommitRequest:
    temporal, trust = _projection_pair(version=operation, outcome=outcome)
    return ProjectionCommitRequest(
        repository_id=REPOSITORY_ID,
        operation_id=f"operation-{operation}",
        graph_revision=f"graph-revision-{operation}",
        event_batch_sequence=operation,
        event_batch_digest=_digest(f"event-batch-{operation}"),
        complete_read_set_digest=_digest(f"read-set-{operation}"),
        writer_epoch=1,
        base_snapshot_token=f"snapshot-{operation - 1}",
        temporal_policy_fingerprint=_digest("temporal-policy"),
        trust_policy_fingerprint=_digest("trust-policy"),
        arbitration_as_of=T0,
        temporal_projections=(temporal,),
        trust_projections=(trust,),
        semantic_conflict_authority=SemanticConflictAuthorityCommitInput.empty(),
    )


@dataclass
class _ProjectionHarness:
    plane: MemoryPlaneService
    backend: JsonlMemoryPlaneStore
    repository: ProjectionHistoryRepository
    capability: object
    authorization: SemanticWriterWriteAuthorization
    authority: list[tuple[str, tuple]]

    def replace_records(
        self,
        replacements: tuple[CanonicalMemoryRecord, ...],
    ) -> None:
        records = {record.memory_id: record for record in self.plane.list_records()}
        records.update({record.memory_id: record for record in replacements})
        self.backend._replace_batches(
            [
                _PersistedBatch.create(
                    revision=1,
                    data_revision=0,
                    records=tuple(records.values()),
                )
            ]
        )

    def install(self, request: ProjectionCommitRequest):
        prepared = self.repository.prepare(
            request,
            capability=self.capability,
            authorization=self.authorization,
        )
        if prepared.records:
            records = {record.memory_id: record for record in self.plane.list_records()}
            records.update({record.memory_id: record for record in prepared.records})
            self.backend._replace_batches(
                [
                    _PersistedBatch.create(
                        revision=1,
                        data_revision=0,
                        records=tuple(records.values()),
                    )
                ]
            )
        self.authority[:] = [
            (
                request.graph_revision,
                prepared.publication.replay_bindings,
            )
        ]
        return prepared.publication


def _repository(
    path: Path,
    clock: Callable[[], datetime],
) -> _ProjectionHarness:
    backend = JsonlMemoryPlaneStore(path)
    plane = MemoryPlaneService(record_store=backend)
    writers = SemanticWriterAdmissionStore(
        plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: T0,
    )
    admission = writers.create_initial_evidence_only(
        admission_id="projection-test-writer",
        writer_implementation_fingerprint="projection-test-writer",
        graph_schema_fingerprint="projection-test-schema",
    )
    binding = writers.commit_binding(admission)
    capability = writers._register_atomic_owner()
    authorization = writers._authorize_atomic(binding, capability=capability)
    authority: list[tuple[str, tuple]] = []
    repository = ProjectionHistoryRepository(
        plane,
        repository_id=REPOSITORY_ID,
        now_provider=clock,
        publication_capability=capability,
        current_replay_authority_resolver=lambda: authority[0],
    )
    return _ProjectionHarness(
        plane=plane,
        backend=backend,
        repository=repository,
        capability=capability,
        authorization=authorization,
        authority=authority,
    )


def test_jsonl_generations_are_immutable_and_queries_keep_contested_history(
    tmp_path: Path,
) -> None:
    path = tmp_path / "projection-history"
    first_time = T0 + timedelta(hours=1)
    second_time = T0 + timedelta(hours=2)
    harness = _repository(path, _Clock(first_time, second_time))
    repository = harness.repository

    first = harness.install(_request(1, outcome="contested"))
    assert repository.contested_temporal(
        policy_fingerprint=_digest("temporal-policy")
    ) == (_request(1, outcome="contested").temporal_projections[0],)
    assert repository.contested_trust(
        policy_fingerprint=_digest("trust-policy")
    ) == (_request(1, outcome="contested").trust_projections[0],)
    second = harness.install(_request(2, outcome="pass"))

    assert first.temporal.active_pointer.publication_sequence == 1
    assert second.temporal.active_pointer.publication_sequence == 2
    assert second.temporal.active_pointer.predecessor_pointer_digest == (
        first.temporal.active_pointer.pointer_digest
    )
    assert first.temporal.generation.canonical_projection_digests != (
        second.temporal.generation.canonical_projection_digests
    )
    historical = repository.historical_trust(system_as_of=first_time)
    current = repository.current_trust(
        policy_fingerprint=_digest("trust-policy"),
    )
    assert historical.projections[0].outcome == "contested"
    assert not any(
        item.authority_relation == "winner"
        for item in historical.projections[0].evidence
    )
    assert current.projections[0].outcome == "pass"
    assert tuple(
        item.candidate_id
        for item in current.projections[0].evidence
        if item.authority_relation == "winner"
    ) == ("candidate-high-authority",)

    reopened = ProjectionHistoryRepository(
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path)),
        repository_id=REPOSITORY_ID,
        now_provider=lambda: second_time,
        current_replay_authority_resolver=lambda: harness.authority[0],
    )
    assert reopened.historical_trust(system_as_of=first_time) == historical
    assert reopened.current_trust(
        policy_fingerprint=_digest("trust-policy")
    ) == current
    assert reopened.replay_bindings() == repository.replay_bindings()


def test_equal_publication_times_use_sequence_only_for_history_not_truth(
    tmp_path: Path,
) -> None:
    harness = _repository(tmp_path / "equal-time", lambda: T0)
    repository = harness.repository
    first_request = _request(1, outcome="contested")
    first = harness.install(first_request)
    second = harness.install(_request(2, outcome="pass"))

    assert first.trust.active_pointer.published_at == second.trust.active_pointer.published_at
    assert repository.historical_trust(system_as_of=T0).pointer == (
        second.trust.active_pointer
    )
    assert not any(
        item.authority_relation == "winner"
        for item in first_request.trust_projections[0].evidence
    )
    assert repository.historical_trust(system_as_of=T0).projections[0].outcome == "pass"


def test_exact_retry_survives_reopen_and_divergent_retry_fails_closed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "retry"
    harness = _repository(path, lambda: T0)
    request = _request(1, outcome="contested")
    original = harness.install(request)
    reopened = ProjectionHistoryRepository(
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path)),
        repository_id=REPOSITORY_ID,
        now_provider=lambda: T0 + timedelta(days=1),
        publication_capability=harness.capability,
        current_replay_authority_resolver=lambda: harness.authority[0],
    )

    assert reopened.prepare(
        request,
        capability=harness.capability,
        authorization=harness.authorization,
    ).publication == original
    divergent = request.model_copy(
        update={"complete_read_set_digest": _digest("different-read-set")}
    )
    with pytest.raises(
        ProjectionHistoryError,
        match="projection_publication_diverged",
    ):
        reopened.prepare(
            divergent,
            capability=harness.capability,
            authorization=harness.authorization,
        )
    assert reopened.replay_bindings() == original.replay_bindings


def test_current_queries_reject_stale_policy_or_graph_revision(tmp_path: Path) -> None:
    harness = _repository(tmp_path / "stale", lambda: T0)
    repository = harness.repository
    harness.install(_request(1, outcome="pass"))

    with pytest.raises(ProjectionHistoryError, match="stale_materialized_projection"):
        repository.current_temporal(policy_fingerprint=_digest("retired-policy"))
    with pytest.raises(ProjectionHistoryError, match="stale_materialized_projection"):
        harness.authority[0] = ("stale-graph", harness.authority[0][1])
        repository.current_trust(policy_fingerprint=_digest("trust-policy"))


def test_queries_before_first_publication_return_typed_unavailable(
    tmp_path: Path,
) -> None:
    harness = _repository(tmp_path / "unavailable", lambda: T0)
    repository = harness.repository

    with pytest.raises(
        ProjectionHistoryError,
        match="projection_history_unavailable",
    ):
        repository.current_temporal(
            policy_fingerprint=_digest("temporal-policy")
        )
    harness.install(_request(1, outcome="pass"))
    with pytest.raises(
        ProjectionHistoryError,
        match="projection_history_unavailable",
    ):
        repository.historical_trust(system_as_of=T0 - timedelta(seconds=1))


def test_server_time_regression_is_rejected_without_publishing(tmp_path: Path) -> None:
    first_time = T0 + timedelta(hours=2)
    harness = _repository(
        tmp_path / "clock-regression",
        _Clock(first_time, T0 + timedelta(hours=1)),
    )
    repository = harness.repository
    first = harness.install(_request(1, outcome="contested"))

    with pytest.raises(
        ProjectionHistoryError,
        match="projection_publication_time_regression",
    ):
        harness.install(_request(2, outcome="pass"))
    assert repository.replay_bindings() == first.replay_bindings


def test_trust_decay_certificate_names_exact_added_and_removed_commands(
    tmp_path: Path,
) -> None:
    harness = _repository(
        tmp_path / "trust-decay",
        _Clock(T0, T0 + timedelta(hours=1)),
    )
    first_request = _request(1, outcome="pass")
    first_request = ProjectionCommitRequest.model_validate(
        {
            **first_request.model_dump(mode="python"),
            "trust_decay_command_digests": (_digest("decay-a"),),
        }
    )
    second_request = _request(2, outcome="pass")
    second_request = ProjectionCommitRequest.model_validate(
        {
            **second_request.model_dump(mode="python"),
            "trust_decay_command_digests": (_digest("decay-b"),),
        }
    )

    first = harness.install(first_request)
    second = harness.install(second_request)

    assert first.trust.certificate.added_decay_command_digests == (
        _digest("decay-a"),
    )
    assert first.trust.certificate.removed_decay_command_digests == ()
    assert second.trust.certificate.added_decay_command_digests == (
        _digest("decay-b"),
    )
    assert second.trust.certificate.removed_decay_command_digests == (
        _digest("decay-a"),
    )


def _replace_authority_record(
    record: CanonicalMemoryRecord,
    value: ActiveTemporalProjectionPointer | TemporalProjectionHistoryEntry,
) -> CanonicalMemoryRecord:
    raw = encode_typed_value(value.model_dump(mode="python"))
    return record.model_copy(
        update={
            "content": {
                "projection_authority_kind": record.content[
                    "projection_authority_kind"
                ],
                "canonical_hex": raw.hex(),
                "authority_digest": sha256(raw).hexdigest(),
            }
        }
    )


@pytest.mark.parametrize("mutation", ("sequence_gap", "predecessor", "time_regression"))
def test_pointer_chain_mutation_families_fail_closed(
    tmp_path: Path,
    mutation: str,
) -> None:
    harness = _repository(
        tmp_path / mutation,
        _Clock(T0 + timedelta(hours=1), T0 + timedelta(hours=2)),
    )
    plane = harness.plane
    repository = harness.repository
    first = harness.install(_request(1, outcome="contested"))
    second = harness.install(_request(2, outcome="pass"))
    pointer_values = second.temporal.active_pointer.model_dump(
        mode="python", exclude={"pointer_digest"}
    )
    if mutation == "sequence_gap":
        pointer_values.update({"pointer_revision": 3, "publication_sequence": 3})
    elif mutation == "predecessor":
        pointer_values["predecessor_pointer_digest"] = _digest("foreign-pointer")
    else:
        pointer_values["published_at"] = first.temporal.active_pointer.published_at - (
            timedelta(seconds=1)
        )
    pointer = ActiveTemporalProjectionPointer.model_validate(
        {
            **pointer_values,
            "pointer_digest": projection_contract_digest(
                "temporal_pointer", pointer_values
            ),
        }
    )
    entry_values = second.temporal.history_entry.model_dump(
        mode="python", exclude={"entry_digest", "pointer"}
    )
    entry_values["pointer"] = pointer
    entry = TemporalProjectionHistoryEntry.model_validate(
        {
            **entry_values,
            "entry_digest": projection_contract_digest(
                "history_entry", entry_values
            ),
        }
    )
    history_record = next(
        record
        for record in plane.list_records(
            source_kind="semantic_projection_temporal_history_entry"
        )
        if record.memory_id.endswith("00000000000000000002")
    )
    active_record = plane.list_records(
        source_kind="semantic_projection_temporal_active_pointer"
    )[0]
    harness.replace_records(
        (
            _replace_authority_record(history_record, entry),
            _replace_authority_record(active_record, pointer),
        )
    )

    with pytest.raises(
        ProjectionHistoryError,
        match="projection_history_integrity_error",
    ):
        repository.replay_bindings()


def test_detached_publication_is_unauthorized_and_writes_nothing(
    tmp_path: Path,
) -> None:
    harness = _repository(tmp_path / "detached-publication", lambda: T0)
    before = tuple(harness.plane.list_records())

    with pytest.raises(
        ProjectionHistoryError,
        match="projection_publication_unauthorized",
    ):
        harness.repository.publish(_request(1, outcome="contested"))

    assert tuple(harness.plane.list_records()) == before
    assert harness.repository.replay_bindings() == ()


@pytest.mark.parametrize("coordinate", ("source_kind", "namespace"))
def test_projection_source_and_namespace_writes_require_writer_authority(
    tmp_path: Path,
    coordinate: str,
) -> None:
    harness = _repository(tmp_path / f"governed-{coordinate}", lambda: T0)
    prepared = harness.repository.prepare(
        _request(1, outcome="pass"),
        capability=harness.capability,
        authorization=harness.authorization,
    )
    record = prepared.records[0]
    if coordinate == "source_kind":
        record = record.model_copy(update={"memory_id": "detached:projection"})
    else:
        record = record.model_copy(update={"source_kind": "detached_projection"})
    before = tuple(harness.plane.list_records())

    with pytest.raises(SemanticWriterAdmissionError):
        harness.plane.write_records((record,))

    assert tuple(harness.plane.list_records()) == before


def test_current_read_without_replay_authority_is_unavailable(
    tmp_path: Path,
) -> None:
    harness = _repository(tmp_path / "detached-current-read", lambda: T0)
    harness.install(_request(1, outcome="pass"))
    detached = ProjectionHistoryRepository(
        harness.plane,
        repository_id=REPOSITORY_ID,
        now_provider=lambda: T0,
    )

    with pytest.raises(
        ProjectionHistoryError,
        match="projection_history_unavailable",
    ):
        detached.current_temporal(
            policy_fingerprint=_digest("temporal-policy")
        )


def test_generic_projection_publication_requires_exact_conflict_authority(
    tmp_path: Path,
) -> None:
    """The generic request choke point rejects a contested slot before CAS."""

    harness = _repository(tmp_path / "generic-conflict-authority", _Clock(T0))
    slot = SemanticClaimSlotKey(
        subject_logical_entity_id="entity:alice",
        predicate_id="works_for",
        scope_identity="asserted:speaker",
    )
    evidence = tuple(
        ProjectionEvidenceRecord(
            candidate_id=f"assertion:{candidate}",
            candidate_digest=_digest(f"assertion:{candidate}"),
            authority_relation="contested_top",
            assertion_key=SemanticAssertionKey(
                slot=slot,
                value=SemanticClaimValueKey(
                    object_kind="entity",
                    object_logical_entity_id=f"entity:{candidate}",
                    value_policy_fingerprint=_digest("value-policy"),
                ),
            ),
            source_id=f"source:{candidate}",
            source_authority_class="official",
            source_authority_evidence_digest=_digest("authority-evidence"),
            source_event_id=f"event:{candidate}",
            source_event_digest=_digest(f"event:{candidate}"),
            transaction_group_id=f"operation:{candidate}",
            valid_interval=TimeInterval(start=T0, end=None),
            system_valid_from=T0,
        )
        for candidate in ("globex", "initech")
    )
    common = {
        "projection_id": _digest("contested-projection"),
        "repository_id": REPOSITORY_ID,
        "source_record_kind": "claim_assertion",
        "source_record_id": "assertion:alice-employer",
        "source_record_version": 1,
        "source_record_digest": _digest("source-record"),
        "claim_slot_key": slot,
        "predicate_state_policy_fingerprint": _digest("state-policy"),
        "selected_assertion_ids": (),
        "contested_assertion_ids": tuple(item.candidate_id for item in evidence),
        "retained_assertion_ids": (),
        "system_valid_from": T0,
        "valid_interval": TimeInterval(start=T0, end=None),
        "outcome": "contested",
        "evidence": evidence,
    }
    temporal = TemporalProjectionRecord.create(
        **common,
        temporal_policy_fingerprint=_digest("temporal-policy"),
    )
    trust = TrustProjectionRecord.create(
        **common,
        trust_policy_fingerprint=_digest("trust-policy"),
        arbitration_as_of=T0,
    )
    before = tuple(harness.plane.list_records())

    with pytest.raises(ValueError, match="do not biject contested projections"):
        ProjectionCommitRequest(
            repository_id=REPOSITORY_ID,
            operation_id="contested-without-authority",
            graph_revision="graph-revision-1",
            event_batch_sequence=1,
            event_batch_digest=_digest("event-batch-1"),
            complete_read_set_digest=_digest("read-set-1"),
            writer_epoch=1,
            base_snapshot_token="snapshot-0",
            temporal_policy_fingerprint=_digest("temporal-policy"),
            trust_policy_fingerprint=_digest("trust-policy"),
            arbitration_as_of=T0,
            temporal_projections=(temporal,),
            trust_projections=(trust,),
            semantic_conflict_authority=SemanticConflictAuthorityCommitInput.empty(),
        )

    assert tuple(harness.plane.list_records()) == before
