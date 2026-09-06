from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from memorii.core.memory_evolution.atomic_store import (
    SemanticIngestionAtomicStore,
    _semantic_checkpoint_lifecycle_record,
    _semantic_registry_history_record,
    _semantic_replay_authority_record,
)
from memorii.core.memory_evolution.conflict_attention import (
    SemanticConflictAuthorityCommitInput,
)
from memorii.core.memory_evolution.projection_history import (
    ProjectionCommitRequest,
    ProjectionHistoryError,
)
from memorii.core.memory_evolution.projection_scheduler import ProjectionSchedulerError
from memorii.core.memory_evolution.semantic_state import (
    ProjectionEvidenceRecord,
    SemanticAssertionKey,
    SemanticClaimSlotKey,
    SemanticClaimValueKey,
    TemporalProjectionRecord,
    TrustProjectionRecord,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore, _PersistedBatch
from memorii.core.semantic_ingestion.contracts import (
    PredicateTrustRule,
    TimeInterval,
    TrustDecayStep,
    TrustPolicySnapshot,
)
from memorii.core.semantic_ingestion.event_replay import (
    SemanticReplayAuthorityAggregate,
    advance_semantic_replay_authority,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)
REPOSITORY_ID = "semantic_ingestion"
DEFAULT_VALID_INTERVAL = TimeInterval(start=T0, end=None)


def _digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


@dataclass
class _Harness:
    path: Path
    now: list[datetime]
    plane: MemoryPlaneService
    store: SemanticIngestionAtomicStore
    binding: object
    policy: TrustPolicySnapshot

    def reopen(self) -> _Harness:
        plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(self.path))
        writers = SemanticWriterAdmissionStore(
            plane,
            bounded_preplanning_ownership_manifest(),
            now_provider=lambda: self.now[0],
        )
        store = SemanticIngestionAtomicStore(
            plane,
            writers,
            now_provider=lambda: self.now[0],
        )
        return _Harness(
            path=self.path,
            now=self.now,
            plane=plane,
            store=store,
            binding=writers.commit_binding(writers.current()),
            policy=self.policy,
        )


def _policy(*steps: TrustDecayStep) -> TrustPolicySnapshot:
    return TrustPolicySnapshot.create(
        policy_revision="trust-decay-policy",
        system_effective_interval=TimeInterval(
            start=T0,
            end=T0 + timedelta(days=365),
        ),
        rules=(
            PredicateTrustRule(
                predicate_id="works_for",
                eligible_authority_classes=frozenset({"official"}),
                authority_rank_by_class={"official": 10},
                decay_age_basis="assertion_system_start",
                decay_schedule_by_class={"official": steps},
            ),
        ),
    )


def _typed_projection_pair(
    policy: TrustPolicySnapshot,
    *,
    system_valid_from: datetime = T0,
    valid_interval: TimeInterval | None = DEFAULT_VALID_INTERVAL,
    temporal_policy_fingerprint: str | None = None,
    identity: str = "alice-globex",
    subject_logical_entity_id: str = "entity:alice",
    object_logical_entity_id: str = "entity:globex",
) -> tuple[TemporalProjectionRecord, TrustProjectionRecord]:
    temporal_policy_fingerprint = temporal_policy_fingerprint or _digest(
        "temporal-policy"
    )
    slot = SemanticClaimSlotKey(
        subject_logical_entity_id=subject_logical_entity_id,
        predicate_id="works_for",
        scope_identity="asserted:speaker",
    )
    assertion_key = SemanticAssertionKey(
        slot=slot,
        value=SemanticClaimValueKey(
            object_kind="entity",
            object_logical_entity_id=object_logical_entity_id,
            value_policy_fingerprint=_digest("value-policy"),
        ),
    )
    evidence = (
        ProjectionEvidenceRecord(
            candidate_id=f"assertion:{identity}",
            candidate_digest=_digest(f"assertion:{identity}"),
            authority_relation="winner",
            assertion_key=assertion_key,
            source_id=f"source:{identity}",
            source_authority_class="official",
            source_authority_evidence_digest=_digest("authority-evidence"),
            source_event_id=f"event:{identity}",
            source_event_digest=_digest(f"event:{identity}"),
            transaction_group_id=f"operation:{identity}",
            valid_interval=valid_interval,
            system_valid_from=system_valid_from,
        ),
    )
    common = {
        "projection_id": _digest(f"initial-projection:{identity}"),
        "repository_id": REPOSITORY_ID,
        "source_record_kind": "claim_assertion",
        "source_record_id": f"assertion:{identity}",
        "source_record_version": 1,
        "source_record_digest": _digest(f"source-record:{identity}"),
        "claim_slot_key": slot,
        "predicate_state_policy_fingerprint": _digest("state-policy"),
        "selected_assertion_ids": (f"assertion:{identity}",),
        "contested_assertion_ids": (),
        "retained_assertion_ids": (),
        "system_valid_from": system_valid_from,
        "valid_interval": valid_interval,
        "outcome": "pass",
        "evidence": evidence,
    }
    return (
        TemporalProjectionRecord.create(
            **common,
            temporal_policy_fingerprint=temporal_policy_fingerprint,
        ),
        TrustProjectionRecord.create(
            **common,
            trust_policy_fingerprint=policy.fingerprint,
            arbitration_as_of=T0,
        ),
    )


def _harness(
    tmp_path: Path,
    policy: TrustPolicySnapshot,
    *,
    system_valid_from: datetime = T0,
    valid_interval: TimeInterval | None = DEFAULT_VALID_INTERVAL,
    temporal_policy_fingerprint: str | None = None,
    projection_pairs: tuple[
        tuple[TemporalProjectionRecord, TrustProjectionRecord], ...
    ]
    | None = None,
) -> _Harness:
    path = tmp_path / "projection-scheduler"
    now = [T0]
    backend = JsonlMemoryPlaneStore(path)
    plane = MemoryPlaneService(record_store=backend)
    writers = SemanticWriterAdmissionStore(
        plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: now[0],
    )
    admission = writers.create_initial_evidence_only(
        admission_id="projection-scheduler-writer",
        writer_implementation_fingerprint="projection-scheduler-writer",
        graph_schema_fingerprint="projection-scheduler-schema",
    )
    binding = writers.commit_binding(admission)
    store = SemanticIngestionAtomicStore(
        plane,
        writers,
        now_provider=lambda: now[0],
    )
    authorization = writers._authorize_atomic(
        binding,
        capability=store._write_capability,
    )
    if projection_pairs is None:
        projection_pairs = (
            _typed_projection_pair(
                policy,
                system_valid_from=system_valid_from,
                valid_interval=valid_interval,
                temporal_policy_fingerprint=temporal_policy_fingerprint,
            ),
        )
    temporal_projections = tuple(
        sorted(
            (item[0] for item in projection_pairs),
            key=lambda item: item.projection_digest,
        )
    )
    trust_projections = tuple(
        sorted(
            (item[1] for item in projection_pairs),
            key=lambda item: item.projection_digest,
        )
    )
    prepared = store.projection_history.prepare(
        ProjectionCommitRequest(
            repository_id=REPOSITORY_ID,
            operation_id="initial-projection",
            graph_revision="genesis",
            event_batch_sequence=0,
            event_batch_digest=_digest("initial-event"),
            complete_read_set_digest=_digest("initial-read-set"),
            writer_epoch=1,
            base_snapshot_token="genesis",
            temporal_policy_fingerprint=(
                temporal_projections[0].temporal_policy_fingerprint
            ),
            trust_policy_fingerprint=policy.fingerprint,
            arbitration_as_of=T0,
            temporal_projections=temporal_projections,
            trust_projections=trust_projections,
            semantic_conflict_authority=SemanticConflictAuthorityCommitInput.empty(),
        ),
        capability=store._write_capability,
        authorization=authorization,
    )
    genesis = SemanticReplayAuthorityAggregate.genesis(REPOSITORY_ID)
    aggregate = advance_semantic_replay_authority(
        genesis,
        graph_state=genesis.graph_state,
        member_bindings=(),
        reconstructed_authority_digest=genesis.reconstructed_authority_digest,
        latest_checkpoint=None,
        projection_history_bindings=prepared.publication.replay_bindings,
    )
    replay_records = (
        _semantic_replay_authority_record(aggregate, T0),
        _semantic_checkpoint_lifecycle_record(store._checkpoint_resume_authority, T0),
        _semantic_registry_history_record(store.event_schema_registry_history, T0),
    )
    current = tuple(plane.list_records())
    backend._replace_batches(
        [
            _PersistedBatch.create(
                revision=1,
                data_revision=0,
                records=(*current, *prepared.records, *replay_records),
            )
        ]
    )
    return _Harness(
        path=path,
        now=now,
        plane=plane,
        store=store,
        binding=binding,
        policy=policy,
    )


def test_decay_threshold_is_not_applied_before_and_is_exact_at_boundary(
    tmp_path: Path,
) -> None:
    policy = _policy(
        TrustDecayStep(
            minimum_age=timedelta(days=10),
            authority_loss=2,
            eligibility="eligible",
        ),
    )
    harness = _harness(tmp_path, policy)
    read_set = _digest("decay-read-set")

    harness.now[0] = T0 + timedelta(days=9)
    assert harness.store.reconcile_trust_decay(
        policy,
        writer_binding=harness.binding,
        complete_read_set_digest=read_set,
    )
    assert harness.store.run_due_trust_decay(
        policy,
        writer_binding=harness.binding,
        complete_read_set_digest=read_set,
    ) == ()
    before = harness.store.projection_history.current_trust(
        policy_fingerprint=policy.fingerprint
    )
    assert before.generation.arbitration_as_of == T0
    with pytest.raises(
        ProjectionHistoryError,
        match="stale_materialized_projection",
    ):
        harness.store.projection_history.current_trust(
            policy_fingerprint=policy.fingerprint,
            system_as_of=T0 + timedelta(days=10),
        )

    harness.now[0] = T0 + timedelta(days=10)
    applied = harness.store.run_due_trust_decay(
        policy,
        writer_binding=harness.binding,
        complete_read_set_digest=read_set,
    )
    assert len(applied) == 1
    at = harness.store.projection_history.current_trust(
        policy_fingerprint=policy.fingerprint
    )
    assert at.generation.arbitration_as_of == harness.now[0]
    assert harness.store.run_due_trust_decay(
        policy,
        writer_binding=harness.binding,
        complete_read_set_digest=read_set,
    ) == ()
    assert harness.store.projection_history.current_trust(
        policy_fingerprint=policy.fingerprint
    ) == at


def test_missed_thresholds_catch_up_in_order_and_survive_jsonl_reopen(
    tmp_path: Path,
) -> None:
    policy = _policy(
        TrustDecayStep(minimum_age=timedelta(days=5), authority_loss=1),
        TrustDecayStep(
            minimum_age=timedelta(days=10),
            authority_loss=20,
            eligibility="ineligible",
        ),
    )
    harness = _harness(tmp_path, policy)
    read_set = _digest("catch-up-read-set")
    assert harness.store.reconcile_trust_decay(
        policy,
        writer_binding=harness.binding,
        complete_read_set_digest=read_set,
    )

    harness.now[0] = T0 + timedelta(days=20)
    reopened = harness.reopen()
    applied = reopened.store.run_due_trust_decay(
        policy,
        writer_binding=reopened.binding,
        complete_read_set_digest=read_set,
    )
    assert len(applied) == 2
    current = reopened.store.projection_history.current_trust(
        policy_fingerprint=policy.fingerprint
    )
    assert current.generation.arbitration_as_of == T0 + timedelta(days=10)
    assert current.projections[0].outcome == "unknown"
    assert current.projections[0].retained_assertion_ids == (
        "assertion:alice-globex",
    )
    assert reopened.store.projection_history.historical_trust(
        system_as_of=T0
    ).projections[0].outcome == "pass"
    again = reopened.reopen()
    assert again.store.run_due_trust_decay(
        policy,
        writer_binding=again.binding,
        complete_read_set_digest=read_set,
    ) == ()
    assert again.store.projection_history.current_trust(
        policy_fingerprint=policy.fingerprint
    ) == current


def test_equal_time_commands_form_one_audited_batch_across_slots_and_restart(
    tmp_path: Path,
) -> None:
    policy = _policy(
        TrustDecayStep(
            minimum_age=timedelta(days=5),
            authority_loss=20,
            eligibility="ineligible",
        ),
    )
    projection_pairs = (
        _typed_projection_pair(policy),
        _typed_projection_pair(
            policy,
            identity="bob-initech",
            subject_logical_entity_id="entity:bob",
            object_logical_entity_id="entity:initech",
        ),
    )
    harness = _harness(
        tmp_path,
        policy,
        projection_pairs=projection_pairs,
    )
    read_set = _digest("equal-time-read-set")
    assert harness.store.reconcile_trust_decay(
        policy,
        writer_binding=harness.binding,
        complete_read_set_digest=read_set,
    )
    scheduled = harness.store.projection_scheduler.pending_commands(policy)
    assert len(scheduled) == 2
    assert tuple(item.threshold_time for item in scheduled) == (
        T0 + timedelta(days=5),
        T0 + timedelta(days=5),
    )

    harness.now[0] = T0 + timedelta(days=5)
    reopened = harness.reopen()
    applied = reopened.store.run_due_trust_decay(
        policy,
        writer_binding=reopened.binding,
        complete_read_set_digest=read_set,
    )
    assert applied == tuple(item.command_digest for item in scheduled)
    current = reopened.store.projection_history.current_trust(
        policy_fingerprint=policy.fingerprint
    )
    assert current.generation.arbitration_as_of == T0 + timedelta(days=5)
    assert {item.outcome for item in current.projections} == {"unknown"}
    again = reopened.reopen()
    assert again.store.run_due_trust_decay(
        policy,
        writer_binding=again.binding,
        complete_read_set_digest=read_set,
    ) == ()


def test_same_policy_decay_preserves_temporal_atoms_multivalue_and_source_independence(
    tmp_path: Path,
) -> None:
    policy = TrustPolicySnapshot.create(
        policy_revision="typed-decay-policy",
        system_effective_interval=TimeInterval(
            start=T0,
            end=T0 + timedelta(days=365),
        ),
        rules=(
            PredicateTrustRule(
                predicate_id="works_for",
                eligible_authority_classes=frozenset(
                    {"official", "community"}
                ),
                authority_rank_by_class={"official": 10, "community": 8},
                decay_age_basis="assertion_system_start",
                decay_schedule_by_class={
                    "official": (
                        TrustDecayStep(
                            minimum_age=timedelta(days=5),
                            authority_loss=5,
                        ),
                        TrustDecayStep(
                            minimum_age=timedelta(days=10),
                            authority_loss=10,
                        ),
                    )
                },
            ),
        ),
    )

    def evidence(
        *,
        candidate_id: str,
        slot: SemanticClaimSlotKey,
        object_id: str,
        authority_class: str,
        interval: TimeInterval,
        relation: str,
    ) -> ProjectionEvidenceRecord:
        return ProjectionEvidenceRecord(
            candidate_id=candidate_id,
            candidate_digest=_digest(candidate_id),
            authority_relation=relation,
            assertion_key=SemanticAssertionKey(
                slot=slot,
                value=SemanticClaimValueKey(
                    object_kind="entity",
                    object_logical_entity_id=object_id,
                    value_policy_fingerprint=_digest("typed-value-policy"),
                ),
            ),
            source_id=f"source:{candidate_id}",
            source_authority_class=authority_class,
            source_authority_evidence_digest=_digest(
                f"authority:{candidate_id}"
            ),
            source_event_id=f"event:{candidate_id}",
            source_event_digest=_digest(f"event:{candidate_id}"),
            transaction_group_id=f"operation:{candidate_id}",
            valid_interval=interval,
            system_valid_from=T0,
        )

    def pair(
        *,
        identity: str,
        slot: SemanticClaimSlotKey,
        interval: TimeInterval,
        evidence_records: tuple[ProjectionEvidenceRecord, ...],
        selected: tuple[str, ...],
        retained: tuple[str, ...],
        state_policy: str,
    ) -> tuple[TemporalProjectionRecord, TrustProjectionRecord]:
        common = {
            "projection_id": _digest(f"typed-projection:{identity}"),
            "repository_id": REPOSITORY_ID,
            "source_record_kind": "claim_assertion",
            "source_record_id": f"claim-slot:{identity}",
            "source_record_version": 1,
            "source_record_digest": _digest(f"typed-source:{identity}"),
            "claim_slot_key": slot,
            "predicate_state_policy_fingerprint": _digest(state_policy),
            "selected_assertion_ids": selected,
            "contested_assertion_ids": (),
            "retained_assertion_ids": retained,
            "system_valid_from": T0,
            "valid_interval": interval,
            "outcome": "pass",
            "evidence": tuple(
                sorted(evidence_records, key=lambda item: item.candidate_id)
            ),
        }
        return (
            TemporalProjectionRecord.create(
                **common,
                temporal_policy_fingerprint=_digest("typed-temporal-policy"),
            ),
            TrustProjectionRecord.create(
                **common,
                trust_policy_fingerprint=policy.fingerprint,
                arbitration_as_of=T0,
            ),
        )

    single_slot = SemanticClaimSlotKey(
        subject_logical_entity_id="entity:alice",
        predicate_id="works_for",
        scope_identity="asserted:speaker",
    )
    overlap = TimeInterval(start=T0, end=T0 + timedelta(days=10))
    overlap_evidence = (
        evidence(
            candidate_id="assertion:official",
            slot=single_slot,
            object_id="entity:globex",
            authority_class="official",
            interval=overlap,
            relation="winner",
        ),
        evidence(
            candidate_id="assertion:community-one",
            slot=single_slot,
            object_id="entity:initech",
            authority_class="community",
            interval=overlap,
            relation="retained_noncurrent",
        ),
        evidence(
            candidate_id="assertion:community-two",
            slot=single_slot,
            object_id="entity:initech",
            authority_class="community",
            interval=overlap,
            relation="retained_noncurrent",
        ),
    )
    disjoint = TimeInterval(
        start=T0 + timedelta(days=10),
        end=T0 + timedelta(days=20),
    )
    disjoint_evidence = (
        evidence(
            candidate_id="assertion:disjoint",
            slot=single_slot,
            object_id="entity:umbrella",
            authority_class="official",
            interval=disjoint,
            relation="winner",
        ),
    )
    multi_slot = SemanticClaimSlotKey(
        subject_logical_entity_id="entity:bob",
        predicate_id="works_for",
        scope_identity="asserted:speaker",
    )
    multi_interval = TimeInterval(start=T0, end=None)
    multi_one = evidence(
        candidate_id="assertion:multi-one",
        slot=multi_slot,
        object_id="entity:acme",
        authority_class="official",
        interval=multi_interval,
        relation="winner",
    )
    multi_two = evidence(
        candidate_id="assertion:multi-two",
        slot=multi_slot,
        object_id="entity:stark",
        authority_class="official",
        interval=multi_interval,
        relation="winner",
    )
    projection_pairs = (
        pair(
            identity="overlap",
            slot=single_slot,
            interval=overlap,
            evidence_records=overlap_evidence,
            selected=("assertion:official",),
            retained=(
                "assertion:community-one",
                "assertion:community-two",
            ),
            state_policy="single-state-policy",
        ),
        pair(
            identity="disjoint",
            slot=single_slot,
            interval=disjoint,
            evidence_records=disjoint_evidence,
            selected=("assertion:disjoint",),
            retained=(),
            state_policy="single-state-policy",
        ),
        pair(
            identity="multi-one",
            slot=multi_slot,
            interval=multi_interval,
            evidence_records=(multi_one,),
            selected=("assertion:multi-one",),
            retained=(),
            state_policy="multi-state-policy",
        ),
        pair(
            identity="multi-two",
            slot=multi_slot,
            interval=multi_interval,
            evidence_records=(multi_two,),
            selected=("assertion:multi-two",),
            retained=(),
            state_policy="multi-state-policy",
        ),
    )
    harness = _harness(
        tmp_path,
        policy,
        projection_pairs=projection_pairs,
    )
    before = harness.store.projection_history.current_trust(
        policy_fingerprint=policy.fingerprint
    )
    overlap_before = next(
        item for item in before.projections if item.source_record_id == "claim-slot:overlap"
    )
    assert overlap_before.selected_assertion_ids == ("assertion:official",)
    assert overlap_before.retained_assertion_ids == (
        "assertion:community-one",
        "assertion:community-two",
    )

    read_set = _digest("typed-decay-read-set")
    assert harness.store.reconcile_trust_decay(
        policy,
        writer_binding=harness.binding,
        complete_read_set_digest=read_set,
    )
    harness.now[0] = T0 + timedelta(days=20)
    reopened = harness.reopen()
    applied = reopened.store.run_due_trust_decay(
        policy,
        writer_binding=reopened.binding,
        complete_read_set_digest=read_set,
    )
    commands = {
        item.command_digest: item
        for item in reopened.store.projection_scheduler._load_commands()
    }
    assert len(applied) == 8
    assert len(set(applied)) == 8
    assert tuple(commands[item].threshold_time for item in applied) == (
        *(T0 + timedelta(days=5) for _ in range(4)),
        *(T0 + timedelta(days=10) for _ in range(4)),
    )

    current = reopened.store.projection_history.current_trust(
        policy_fingerprint=policy.fingerprint
    )
    by_source = {item.source_record_id: item for item in current.projections}
    assert by_source["claim-slot:overlap"].selected_assertion_ids == (
        "assertion:community-one",
        "assertion:community-two",
    )
    assert by_source["claim-slot:overlap"].retained_assertion_ids == (
        "assertion:official",
    )
    assert by_source["claim-slot:disjoint"].selected_assertion_ids == (
        "assertion:disjoint",
    )
    assert by_source["claim-slot:multi-one"].selected_assertion_ids == (
        "assertion:multi-one",
    )
    assert by_source["claim-slot:multi-two"].selected_assertion_ids == (
        "assertion:multi-two",
    )
    assert reopened.store.projection_history.historical_trust(
        system_as_of=T0
    ).projections == before.projections
    again = reopened.reopen()
    assert again.store.run_due_trust_decay(
        policy,
        writer_binding=again.binding,
        complete_read_set_digest=read_set,
    ) == ()
    assert again.store.projection_history.current_trust(
        policy_fingerprint=policy.fingerprint
    ) == current


def test_decay_apply_then_raise_recovers_schedule_and_threshold_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _policy(
        TrustDecayStep(
            minimum_age=timedelta(days=5),
            authority_loss=20,
            eligibility="ineligible",
        ),
    )
    harness = _harness(tmp_path, policy)
    read_set = _digest("decay-lost-ack-read-set")
    backend = harness.plane._records
    original_apply = backend.apply_batch
    fired = False

    def lose_schedule_ack(*args, **kwargs):
        nonlocal fired
        result = original_apply(*args, **kwargs)
        records = args[0] if args else kwargs["records"]
        if not fired and any(
            record.source_kind == "semantic_projection_trust_decay_command"
            for record in records
        ):
            fired = True
            raise OSError("decay schedule lost acknowledgement")
        return result

    monkeypatch.setattr(backend, "apply_batch", lose_schedule_ack)
    with pytest.raises(OSError, match="schedule lost acknowledgement"):
        harness.store.reconcile_trust_decay(
            policy,
            writer_binding=harness.binding,
            complete_read_set_digest=read_set,
        )
    assert fired

    scheduled = harness.reopen()
    assert not scheduled.store.reconcile_trust_decay(
        policy,
        writer_binding=scheduled.binding,
        complete_read_set_digest=read_set,
    )
    pending = scheduled.store.projection_scheduler.pending_commands(policy)
    assert len(pending) == 1
    scheduled.now[0] = T0 + timedelta(days=5)
    backend = scheduled.plane._records
    original_apply = backend.apply_batch
    fired = False

    def lose_threshold_ack(*args, **kwargs):
        nonlocal fired
        result = original_apply(*args, **kwargs)
        records = args[0] if args else kwargs["records"]
        if not fired and any(
            record.source_kind == "semantic_projection_trust_generation"
            for record in records
        ):
            fired = True
            raise OSError("decay threshold lost acknowledgement")
        return result

    monkeypatch.setattr(backend, "apply_batch", lose_threshold_ack)
    with pytest.raises(OSError, match="threshold lost acknowledgement"):
        scheduled.store.run_due_trust_decay(
            policy,
            writer_binding=scheduled.binding,
            complete_read_set_digest=read_set,
        )
    assert fired

    completed = scheduled.reopen()
    committed_records = tuple(completed.plane.list_records())
    assert completed.store.run_due_trust_decay(
        policy,
        writer_binding=completed.binding,
        complete_read_set_digest=read_set,
    ) == ()
    current = completed.store.projection_history.current_trust(
        policy_fingerprint=policy.fingerprint
    )
    assert current.generation.arbitration_as_of == T0 + timedelta(days=5)
    assert current.projections[0].outcome == "unknown"
    assert tuple(completed.plane.list_records()) == committed_records


@pytest.mark.parametrize(
    "rule",
    (
        lambda: PredicateTrustRule(
            predicate_id="works_for",
            eligible_authority_classes=frozenset({"official"}),
            authority_rank_by_class={"official": 10},
            decay_schedule_by_class={
                "official": (
                    TrustDecayStep(minimum_age=timedelta(days=2), authority_loss=2),
                    TrustDecayStep(minimum_age=timedelta(days=1), authority_loss=3),
                )
            },
        ),
        lambda: PredicateTrustRule(
            predicate_id="works_for",
            eligible_authority_classes=frozenset({"official"}),
            authority_rank_by_class={"official": 10},
            decay_schedule_by_class={
                "foreign": (
                    TrustDecayStep(minimum_age=timedelta(days=1), authority_loss=1),
                )
            },
        ),
        lambda: PredicateTrustRule(
            predicate_id="works_for",
            eligible_authority_classes=frozenset({"official"}),
            authority_rank_by_class={"official": 10},
            decay_schedule_by_class={
                "official": (
                    TrustDecayStep(
                        minimum_age=timedelta(days=1),
                        authority_loss=1,
                        eligibility="ineligible",
                    ),
                    TrustDecayStep(
                        minimum_age=timedelta(days=2),
                        authority_loss=2,
                        eligibility="eligible",
                    ),
                )
            },
        ),
    ),
)
def test_malformed_decay_algebra_is_rejected(rule) -> None:
    with pytest.raises(ValueError):
        rule()


def test_stale_policy_fails_without_publication(tmp_path: Path) -> None:
    policy = _policy(
        TrustDecayStep(minimum_age=timedelta(days=1), authority_loss=1),
    )
    harness = _harness(tmp_path, policy)
    before = tuple(harness.plane.list_records())
    foreign = _policy()
    with pytest.raises(ProjectionSchedulerError, match="trust_decay_policy_mismatch"):
        harness.store.reconcile_trust_decay(
            foreign,
            writer_binding=harness.binding,
            complete_read_set_digest=_digest("read-set"),
        )
    assert tuple(harness.plane.list_records()) == before


def test_future_assertion_anchor_fails_without_publication(tmp_path: Path) -> None:
    policy = _policy(
        TrustDecayStep(minimum_age=timedelta(days=1), authority_loss=1),
    )
    harness = _harness(
        tmp_path,
        policy,
        system_valid_from=T0 + timedelta(days=1),
    )
    before = tuple(harness.plane.list_records())

    with pytest.raises(ProjectionSchedulerError, match="trust_decay_anchor_in_future"):
        harness.store.reconcile_trust_decay(
            policy,
            writer_binding=harness.binding,
            complete_read_set_digest=_digest("future-anchor-read-set"),
        )

    assert tuple(harness.plane.list_records()) == before


def test_missing_authenticated_event_anchor_fails_without_publication(
    tmp_path: Path,
) -> None:
    policy = TrustPolicySnapshot.create(
        policy_revision="event-time-decay",
        system_effective_interval=TimeInterval(
            start=T0,
            end=T0 + timedelta(days=365),
        ),
        rules=(
            PredicateTrustRule(
                predicate_id="works_for",
                eligible_authority_classes=frozenset({"official"}),
                authority_rank_by_class={"official": 10},
                decay_age_basis="authenticated_event_time",
                decay_schedule_by_class={
                    "official": (
                        TrustDecayStep(
                            minimum_age=timedelta(days=1),
                            authority_loss=1,
                        ),
                    )
                },
            ),
        ),
    )
    harness = _harness(tmp_path, policy, valid_interval=None)
    before = tuple(harness.plane.list_records())

    with pytest.raises(
        ProjectionSchedulerError,
        match="trust_decay_anchor_unavailable",
    ):
        harness.store.reconcile_trust_decay(
            policy,
            writer_binding=harness.binding,
            complete_read_set_digest=_digest("missing-anchor-read-set"),
        )

    assert tuple(harness.plane.list_records()) == before
