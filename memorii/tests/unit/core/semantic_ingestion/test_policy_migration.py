from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from threading import Barrier, Event
from typing import Literal

import pytest
from memorii.core.memory_evolution.atomic_store import PreplanningStoreError
from memorii.core.memory_evolution.ingestion_contracts import (
    decode_typed_value,
    encode_typed_value,
)
from memorii.core.memory_evolution.policy_migration import PolicyMigrationError
from memorii.core.memory_evolution.projection_history import ProjectionHistoryError
from memorii.core.memory_evolution.projection_scheduler import ProjectionSchedulerError
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionError,
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    JsonlMemoryPlaneStore,
    MemoryPlaneRevisionConflictError,
    _PersistedBatch,
)
from memorii.core.semantic_ingestion.authorization import (
    SemanticAuthorizationAuthorityRepository,
)
from memorii.core.semantic_ingestion.contracts import (
    PredicateTemporalRule,
    PredicateTrustRule,
    TemporalPolicySnapshot,
    TimeInterval,
    TrustDecayStep,
    TrustPolicySnapshot,
)
from memorii.core.semantic_ingestion.event_replay import (
    SemanticEventReplayError,
    SemanticReplayCheckpointBundle,
    replay_semantic_event_batches,
)
from memorii.core.semantic_ingestion.persistence import SemanticTerminalPersistenceService
from semantic_terminal_test_support import (
    TestSemanticConflictAuthorityResolver as _TestSemanticConflictAuthorityResolver,
)
from semantic_terminal_test_support import accepted_terminal
from tests.unit.core.semantic_ingestion.test_projection_scheduler import (
    T0,
    _digest,
    _harness,
    _policy,
)
from tests.unit.core.semantic_ingestion.test_semantic_terminal_persistence import (
    AUTHORIZATION,
    _activate,
    _claim_canonical_clarification,
    _commit_claimed_accepted_clarification,
    _json_round_tripped,
    _setup,
)


def _semantic_effect_record_ids(plane):
    """Ids of records carrying committed semantic effects (not raw admissions).

    A rejected stale-policy clarification still admits its contest sources;
    the fail-closed contract is that no terminal, conflict, or migration
    effect is committed.
    """
    return tuple(
        record.memory_id
        for record in plane.list_records()
        if record.source_kind
        not in {
            "semantic_ingestion_source",
            "semantic_ingestion_prepared_source",
            "semantic_ingestion_admission_index",
            "semantic_ingestion_profile_selection",
            "semantic_ingestion_profile_verification",
            "semantic_ingestion_profile_outcome",
            "semantic_ingestion_preplanning_control",
            "semantic_ingestion_preplanning_artifact",
            "semantic_ingestion_bootstrap_handoff_marker",
            "semantic_ingestion_bootstrap_v3_recovery_index",
            "semantic_ingestion_authorization_authority",
        }
    )


def _persist_one_normal_event(
    store,
    *,
    plane,
    service,
    authorization_repository,
    coordinate: str,
    **terminal_kwargs,
):
    """Persist exactly one ordinary graph-advancing semantic write.

    The migration catch-up tests exercise one normal late event; an ordinary
    accepted terminal is that event, with no clarification lifecycle noise.
    """
    from semantic_terminal_test_support import handoff

    _, fence = handoff(
        plane,
        coordinate=coordinate,
        scope_ids=frozenset({"scope:a"}),
        atomic_store=store,
        writer_binding=store._writers.commit_binding(store._writers.current()),
    )
    terminal = accepted_terminal(operation_id=fence.operation_id, **terminal_kwargs)
    _activate(authorization_repository, fence, terminal)
    service.persist(
        fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION
    )


def _commit_clarification_terminal(
    store,
    *,
    plane,
    service,
    authorization_repository,
    coordinate: str,
    **terminal_kwargs,
):
    """Commit one accepted clarification terminal through the real lifecycle.

    Builds the claimed work on an isolated contest, then commits a terminal
    carrying the caller's policy characteristics bound to that claim.
    """
    # The contest claims must carry the same policy characteristics as the
    # committed answer: after a policy cutover the active policy governs
    # every persist in the lifecycle, not only the final terminal.
    claim, cas = _claim_canonical_clarification(
        store,
        coordinate,
        plane=plane,
        service=service,
        authorization_repository=authorization_repository,
        terminal_kwargs=terminal_kwargs,
    )
    receipt, terminal, _processing_operation_id = _commit_claimed_accepted_clarification(
        store,
        claim,
        cas,
        terminal_kwargs=terminal_kwargs,
    )
    return receipt, terminal


def _directory_bytes(path: Path) -> dict[str, bytes]:
    return {
        str(item.relative_to(path)): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def _substitute_persisted_authority(
    path: Path,
    *,
    source_kind: str,
    field_path: tuple[str, ...],
    replacement,
) -> None:
    backend = JsonlMemoryPlaneStore(path)
    batches = backend._read_batches_unlocked()
    target_ids = [
        record.memory_id
        for batch in batches
        for record in batch.records
        if record.source_kind == source_kind
    ]
    assert target_ids
    target_id = target_ids[-1]
    rewritten = []
    changed = False
    for batch in batches:
        records = []
        for record in batch.records:
            if record.memory_id == target_id:
                raw = decode_typed_value(
                    bytes.fromhex(str(record.content["canonical_hex"]))
                )
                assert isinstance(raw, dict)
                cursor = raw
                for name in field_path[:-1]:
                    nested = cursor[name]
                    assert isinstance(nested, dict)
                    cursor = nested
                name = field_path[-1]
                cursor[name] = (
                    replacement(cursor[name])
                    if callable(replacement)
                    else replacement
                )
                canonical = encode_typed_value(raw)
                record = record.model_copy(
                    update={
                        "content": {
                            **record.content,
                            "canonical_hex": canonical.hex(),
                            "authority_digest": sha256(canonical).hexdigest(),
                        }
                    }
                )
                changed = True
            records.append(record)
        rewritten.append(
            _PersistedBatch.create(
                revision=batch.revision,
                data_revision=batch.data_revision,
                records=tuple(records),
            )
        )
    assert changed
    backend._replace_batches(rewritten)


def _rank_policy(rank: int, revision: str) -> TrustPolicySnapshot:
    return TrustPolicySnapshot.create(
        policy_revision=revision,
        system_effective_interval=TimeInterval(
            start=T0,
            end=T0 + timedelta(days=365),
        ),
        rules=(
            PredicateTrustRule(
                predicate_id="works_for",
                eligible_authority_classes=frozenset({"official"}),
                authority_rank_by_class={"official": rank},
            ),
        ),
    )


def _temporal_policy(
    requirement: Literal["required", "optional", "atemporal"],
    revision: str,
) -> TemporalPolicySnapshot:
    return TemporalPolicySnapshot.create(
        policy_revision=revision,
        system_effective_interval=TimeInterval(
            start=T0,
            end=T0 + timedelta(days=365),
        ),
        rules=(
            PredicateTemporalRule(
                predicate_id="works_for",
                valid_time_requirement=requirement,
                allow_open_end=True,
            ),
        ),
    )


def _prepare_policy_with_pending_decay(tmp_path):
    decay = TrustDecayStep(
        minimum_age=timedelta(days=1), authority_loss=20, eligibility="ineligible"
    )
    policy_a = _policy(decay)
    policy_b = TrustPolicySnapshot.create(
        policy_revision="migration-decay-mutation-policy",
        system_effective_interval=TimeInterval(start=T0, end=T0 + timedelta(days=365)),
        rules=(
            PredicateTrustRule(
                predicate_id="works_for",
                eligible_authority_classes=frozenset({"official"}),
                authority_rank_by_class={"official": 20},
                decay_age_basis="assertion_system_start",
                decay_schedule_by_class={"official": (decay,)},
            ),
        ),
    )
    harness = _harness(tmp_path, policy_a)
    plan = harness.store.plan_trust_policy_migration(
        policy_a, policy_b, arbitration_as_of=T0, writer_binding=harness.binding
    )
    result = harness.store.policy_migration.trust_result(
        plan, plan.slot_plans[0], policy_b,
        complete_read_set_digest=_digest("migration-decay-mutation-read-set"),
    )
    return harness, policy_b, plan, result


def _cut_over_policy_with_pending_decay(tmp_path):
    harness, policy_b, plan, result = _prepare_policy_with_pending_decay(tmp_path)
    binding = harness.store.cutover_trust_policy(
        plan, policy_b, (result,), writer_binding=harness.binding,
        final_catch_up_watermark=plan.base_catch_up_watermark,
        expected_partition_revision=0,
        complete_read_set_digest=_digest("migration-decay-mutation-read-set"),
    )
    return harness, policy_b, result, binding


def test_tampered_migrated_decay_command_is_rejected_after_reopen(tmp_path) -> None:
    harness, policy, _, _ = _cut_over_policy_with_pending_decay(tmp_path)
    tampered = tmp_path / "tampered-migrated-decay"
    shutil.copytree(harness.path, tampered)
    _substitute_persisted_authority(
        tampered,
        source_kind="semantic_projection_trust_decay_command",
        field_path=("command_id",),
        replacement="tampered-command",
    )
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(tampered))
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: T0
    )
    from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore

    store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: T0)
    with pytest.raises(ProjectionSchedulerError, match="trust_decay_integrity_error"):
        store.projection_scheduler.pending_commands(policy)


@pytest.mark.parametrize(
    "replacement",
    (lambda _: (), lambda values: (*values, "0" * 64)),
)
def test_migrated_decay_membership_mutation_is_rejected(tmp_path, replacement) -> None:
    harness, policy, _, _ = _cut_over_policy_with_pending_decay(tmp_path)
    mutated = tmp_path / "mutated-migrated-decay"
    shutil.copytree(harness.path, mutated)
    _substitute_persisted_authority(
        mutated,
        source_kind="semantic_projection_trust_generation",
        field_path=("canonical_decay_command_digests",),
        replacement=replacement,
    )
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(mutated))
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: T0
    )
    from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore

    store = SemanticIngestionAtomicStore(plane, writers, now_provider=lambda: T0)
    with pytest.raises(ProjectionHistoryError, match="projection_history_integrity_error"):
        store.projection_history.current_trust(policy_fingerprint=policy.fingerprint)


def test_nested_decay_command_substitution_is_rejected_before_persistence(
    tmp_path,
) -> None:
    harness, policy, result, _ = _cut_over_policy_with_pending_decay(tmp_path)
    plan_record = next(
        record
        for record in harness.plane.list_records()
        if record.source_kind == "semantic_projection_trust_migration_plan"
    )
    plan = harness.store.policy_migration._load_plan(
        "trust", str(plan_record.content["authority_digest"])
    )
    substituted_command = result.decay_commands[0].model_copy(
        update={"command_digest": "0" * 64}
    )
    substituted_result = result.model_copy(
        update={"decay_commands": (substituted_command,)}
    )
    records_before = tuple(harness.plane.list_records())
    pointer_before = harness.store.projection_history.active_trust_authority().pointer
    epoch_before = harness.store._writers.current().writer_epoch

    with pytest.raises(PolicyMigrationError, match="policy_migration_integrity_error"):
        harness.store.policy_migration.prepare_progress(
            plan, results=(substituted_result,)
        )

    assert tuple(harness.plane.list_records()) == records_before
    assert harness.store.projection_history.active_trust_authority().pointer == pointer_before
    assert harness.store._writers.current().writer_epoch == epoch_before


def test_nonempty_migration_decay_command_recovers_lost_progress_and_cutover_ack(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness, policy, plan, result = _prepare_policy_with_pending_decay(tmp_path)
    assert result.decay_commands
    assert result.decay_command_digests
    backend = harness.plane._records
    original_apply = backend.apply_batch
    lost = False

    def lose_once(source_kind: str, message: str):
        def apply(*args, **kwargs):
            nonlocal lost
            outcome = original_apply(*args, **kwargs)
            records = args[0] if args else kwargs["records"]
            if not lost and any(record.source_kind == source_kind for record in records):
                if source_kind == "semantic_projection_trust_migration_result":
                    assert any(
                        record.source_kind == "semantic_projection_trust_decay_command"
                        for record in records
                    )
                lost = True
                raise OSError(message)
            return outcome

        return apply

    monkeypatch.setattr(
        backend,
        "apply_batch",
        lose_once("semantic_projection_trust_migration_result", "decay progress lost ack"),
    )
    with pytest.raises(OSError, match="decay progress lost ack"):
        harness.store._commit_policy_migration_progress(
            harness.store.policy_migration.prepare_progress(plan, results=(result,)),
            writer_binding=harness.binding,
        )
    progressed = harness.reopen()
    records_after_progress = tuple(progressed.plane.list_records())
    progressed.store._commit_policy_migration_progress(
        progressed.store.policy_migration.prepare_progress(plan, results=(result,)),
        writer_binding=progressed.binding,
    )
    assert tuple(progressed.plane.list_records()) == records_after_progress

    backend = progressed.plane._records
    original_apply = backend.apply_batch
    lost = False
    monkeypatch.setattr(
        backend,
        "apply_batch",
        lose_once("semantic_projection_trust_migration_cutover", "decay cutover lost ack"),
    )
    with pytest.raises(OSError, match="decay cutover lost ack"):
        progressed.store.cutover_trust_policy(
            plan, policy, (result,), writer_binding=progressed.binding,
            final_catch_up_watermark=plan.base_catch_up_watermark,
            expected_partition_revision=0,
            complete_read_set_digest=_digest("migration-decay-mutation-read-set"),
        )
    completed = progressed.reopen()
    records_after_cutover = tuple(completed.plane.list_records())
    binding = completed.store.cutover_trust_policy(
        plan, policy, (result,), writer_binding=progressed.binding,
        final_catch_up_watermark=plan.base_catch_up_watermark,
        expected_partition_revision=0,
        complete_read_set_digest=_digest("migration-decay-mutation-read-set"),
    )
    assert tuple(completed.plane.list_records()) == records_after_cutover
    assert completed.store.cutover_trust_policy(
        plan, policy, (result,), writer_binding=progressed.binding,
        final_catch_up_watermark=plan.base_catch_up_watermark,
        expected_partition_revision=0,
        complete_read_set_digest=_digest("migration-decay-mutation-read-set"),
    ) == binding
    records = completed.plane.list_records()
    assert len({record.memory_id for record in records}) == len(records)


def test_temporal_cutover_changes_only_temporal_authority(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trust = _policy()
    temporal_a = _temporal_policy("optional", "temporal-a")
    temporal_b = _temporal_policy("required", "temporal-b")
    harness = _harness(
        tmp_path,
        trust,
        temporal_policy_fingerprint=temporal_a.fingerprint,
    )
    trust_before = harness.store.projection_history.active_trust_authority()
    plan = harness.store.plan_temporal_policy_migration(
        temporal_a,
        temporal_b,
        trust,
        writer_binding=harness.binding,
    )
    command = harness.store.policy_migration.temporal_commands(plan)[0]
    assert command.migration_work_item_digest == plan.slot_plans[0].slot_plan_digest
    assert command.complete_read_set_digest == plan.base_snapshot_token

    recovered = harness.reopen()
    assert recovered.store.policy_migration.temporal_commands(plan) == (command,)
    with pytest.raises(PolicyMigrationError, match="policy_migration_unauthorized"):
        recovered.store.policy_migration.temporal_result(
            plan,
            plan.slot_plans[0],
            temporal_b,
            trust,
        )
    backend = recovered.plane._records
    original_apply = backend.apply_batch
    lost_ack = False

    def lose_result_ack(*args, **kwargs):
        nonlocal lost_ack
        result_value = original_apply(*args, **kwargs)
        records = args[0] if args else kwargs["records"]
        if not lost_ack and any(
            record.source_kind
            == "semantic_projection_temporal_migration_result"
            for record in records
        ):
            lost_ack = True
            raise OSError("temporal executor lost acknowledgement")
        return result_value

    monkeypatch.setattr(backend, "apply_batch", lose_result_ack)
    with pytest.raises(OSError, match="executor lost acknowledgement"):
        recovered.store.run_temporal_policy_migration(
            plan,
            temporal_b,
            trust,
            writer_binding=recovered.binding,
        )
    assert lost_ack

    progressed = recovered.reopen()
    results = progressed.store.run_temporal_policy_migration(
        plan,
        temporal_b,
        trust,
        writer_binding=progressed.binding,
    )
    assert len(results) == 1
    result = results[0]
    assert result.status == "committed"
    assert result.command == command

    binding = progressed.store.cutover_temporal_policy(
        plan,
        temporal_b,
        (result,),
        writer_binding=progressed.binding,
        final_catch_up_watermark=plan.base_catch_up_watermark,
        expected_partition_revision=0,
        complete_read_set_digest=_digest("temporal-read-set"),
    )

    assert binding.expected_writer_epoch == 2
    assert (
        progressed.store.projection_history.current_temporal(
            policy_fingerprint=temporal_b.fingerprint
        ).pointer.publication_kind
        == "migration_cutover"
    )
    assert (
        progressed.store.projection_history.active_trust_authority().generation
        == trust_before.generation
    )


def test_trust_policy_cutover_and_forward_rollback_create_distinct_generations(
    tmp_path,
) -> None:
    policy_a = _policy()
    policy_b = _rank_policy(20, "policy-b")
    harness = _harness(tmp_path, policy_a)

    harness.now[0] = T0 + timedelta(hours=1)
    plan_b = harness.store.plan_trust_policy_migration(
        policy_a,
        policy_b,
        arbitration_as_of=harness.now[0],
        writer_binding=harness.binding,
    )
    assert len(plan_b.slot_plans) == 1
    result_b = harness.store.policy_migration.trust_result(
        plan_b,
        plan_b.slot_plans[0],
        policy_b,
        complete_read_set_digest=_digest("migration-b-read-set"),
    )
    binding_b = harness.store.cutover_trust_policy(
        plan_b,
        policy_b,
        (result_b,),
        writer_binding=harness.binding,
        final_catch_up_watermark=plan_b.base_catch_up_watermark,
        expected_partition_revision=0,
        complete_read_set_digest=_digest("migration-b-read-set"),
    )
    view_b = harness.store.projection_history.current_trust(
        policy_fingerprint=policy_b.fingerprint
    )
    assert binding_b.expected_writer_epoch == 2
    assert view_b.pointer.publication_kind == "migration_cutover"
    committed_records = tuple(harness.plane.list_records())
    retried_binding_b = harness.store.cutover_trust_policy(
        plan_b,
        policy_b,
        (result_b,),
        writer_binding=harness.binding,
        final_catch_up_watermark=plan_b.base_catch_up_watermark,
        expected_partition_revision=0,
        complete_read_set_digest=_digest("migration-b-read-set"),
    )
    assert retried_binding_b == binding_b
    assert tuple(harness.plane.list_records()) == committed_records

    harness.now[0] = T0 + timedelta(hours=2)
    plan_a = harness.store.plan_trust_policy_migration(
        policy_b,
        policy_a,
        arbitration_as_of=harness.now[0],
        writer_binding=binding_b,
    )
    result_a = harness.store.policy_migration.trust_result(
        plan_a,
        plan_a.slot_plans[0],
        policy_a,
        complete_read_set_digest=_digest("migration-a-read-set"),
    )
    binding_a = harness.store.cutover_trust_policy(
        plan_a,
        policy_a,
        (result_a,),
        writer_binding=binding_b,
        final_catch_up_watermark=plan_a.base_catch_up_watermark,
        expected_partition_revision=0,
        complete_read_set_digest=_digest("migration-a-read-set"),
    )

    historical_a = harness.store.projection_history.historical_trust(
        system_as_of=T0
    )
    historical_b = harness.store.projection_history.historical_trust(
        system_as_of=T0 + timedelta(hours=1)
    )
    current_a = harness.store.projection_history.current_trust(
        policy_fingerprint=policy_a.fingerprint
    )
    assert binding_a.expected_writer_epoch == 3
    assert historical_a.pointer.policy_fingerprint == policy_a.fingerprint
    assert historical_b.pointer.policy_fingerprint == policy_b.fingerprint
    assert current_a.pointer.policy_fingerprint == policy_a.fingerprint
    assert len(
        {
            historical_a.generation.generation_digest,
            historical_b.generation.generation_digest,
            current_a.generation.generation_digest,
        }
    ) == 3


def test_policy_round_trip_checkpoint_tail_equals_genesis_and_reopen_authority(
    tmp_path,
) -> None:
    storage = tmp_path / "policy-round-trip-checkpoint"
    clock = [T0]
    (
        plane,
        _,
        store,
        binding_a0,
        fence,
        service,
        authorization_repository,
    ) = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(storage),
        now_provider=lambda: clock[0],
    )
    terminal_a = accepted_terminal(operation_id=fence.operation_id)
    _activate(authorization_repository, fence, terminal_a)
    service.persist(
        fence=fence,
        terminal=terminal_a,
        authorization_verifier=AUTHORIZATION,
    )
    assert terminal_a.arbitration_policy_bundle is not None
    policy_a = terminal_a.arbitration_policy_bundle.trust_policy
    terminal_b = accepted_terminal(
        operation_id=_digest("checkpoint-policy-b"),
        authority_rank_by_class={"official": 20},
    )
    assert terminal_b.arbitration_policy_bundle is not None
    policy_b = terminal_b.arbitration_policy_bundle.trust_policy

    clock[0] = T0 + timedelta(hours=1)
    plan_b = store.plan_trust_policy_migration(
        policy_a,
        policy_b,
        arbitration_as_of=clock[0],
        writer_binding=binding_a0,
    )
    result_b = store.policy_migration.trust_result(
        plan_b,
        plan_b.slot_plans[0],
        policy_b,
        complete_read_set_digest=_digest("checkpoint-b-read-set"),
    )
    binding_b = store.cutover_trust_policy(
        plan_b,
        policy_b,
        (result_b,),
        writer_binding=binding_a0,
        final_catch_up_watermark=plan_b.base_catch_up_watermark,
        expected_partition_revision=0,
        complete_read_set_digest=_digest("checkpoint-b-read-set"),
    )

    clock[0] = T0 + timedelta(hours=2)
    plan_a = store.plan_trust_policy_migration(
        policy_b,
        policy_a,
        arbitration_as_of=clock[0],
        writer_binding=binding_b,
    )
    result_a = store.policy_migration.trust_result(
        plan_a,
        plan_a.slot_plans[0],
        policy_a,
        complete_read_set_digest=_digest("checkpoint-a-read-set"),
    )
    binding_a1 = store.cutover_trust_policy(
        plan_a,
        policy_a,
        (result_a,),
        writer_binding=binding_b,
        final_catch_up_watermark=plan_a.base_catch_up_watermark,
        expected_partition_revision=0,
        complete_read_set_digest=_digest("checkpoint-a-read-set"),
    )

    authority = store.semantic_replay_authority()
    assert authority.latest_checkpoint is not None
    genesis = replay_semantic_event_batches(
        repository_id="semantic_ingestion",
        batches=store.semantic_event_batches(),
        registry_history=store.event_schema_registry_history,
    )
    checkpoint_state = store.validate_semantic_replay_checkpoint(
        authority.latest_checkpoint
    )
    assert checkpoint_state == genesis
    assert (
        store.resume_semantic_replay_checkpoint_tail(
            authority.latest_checkpoint,
            (),
        )
        == genesis
    )
    views_before = (
        store.projection_history.historical_trust(system_as_of=T0),
        store.projection_history.historical_trust(
            system_as_of=T0 + timedelta(hours=1)
        ),
        store.projection_history.current_trust(
            policy_fingerprint=policy_a.fingerprint
        ),
    )
    authority_kinds = {
        "semantic_projection_trust_migration_plan",
        "semantic_projection_trust_migration_result",
        "semantic_projection_trust_migration_cutover",
        "semantic_projection_trust_certificate",
        "semantic_projection_trust_generation",
        "semantic_projection_trust_active_pointer",
        "semantic_projection_trust_history_entry",
    }
    persisted_before = tuple(
        record
        for record in plane.list_records()
        if record.source_kind in authority_kinds
    )

    reopened_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage)
    )
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: clock[0],
    )
    from memorii.core.memory_evolution.atomic_store import (
        SemanticIngestionAtomicStore,
    )

    reopened = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: clock[0],
    )
    assert reopened_writers.commit_binding(reopened_writers.current()) == binding_a1
    assert (
        reopened.policy_migration._load_plan("trust", plan_b.plan_digest)
        == plan_b
    )
    assert (
        reopened.policy_migration._load_plan("trust", plan_a.plan_digest)
        == plan_a
    )
    assert tuple(
        record
        for record in reopened_plane.list_records()
        if record.source_kind in authority_kinds
    ) == persisted_before
    assert (
        reopened.projection_history.historical_trust(system_as_of=T0),
        reopened.projection_history.historical_trust(
            system_as_of=T0 + timedelta(hours=1)
        ),
        reopened.projection_history.current_trust(
            policy_fingerprint=policy_a.fingerprint
        ),
    ) == views_before
    assert reopened.validate_semantic_replay_checkpoint(
        authority.latest_checkpoint
    ) == genesis

    forged_checkpoint = authority.latest_checkpoint.checkpoint.model_copy(
        update={"signature": "f" * 64}
    )
    forged_body = {
        "checkpoint": forged_checkpoint,
        "materialized_snapshot": authority.latest_checkpoint.materialized_snapshot,
        "watermark_batch": authority.latest_checkpoint.watermark_batch,
    }
    forged = SemanticReplayCheckpointBundle(
        checkpoint=forged_checkpoint,
        materialized_snapshot=authority.latest_checkpoint.materialized_snapshot,
        watermark_batch=authority.latest_checkpoint.watermark_batch,
        bundle_digest=sha256(
            b"memorii.semantic-replay-checkpoint-bundle.v1\0"
            + encode_typed_value(
                {
                    key: value.model_dump(mode="python")
                    for key, value in forged_body.items()
                }
            )
        ).hexdigest(),
    )
    bytes_before = _directory_bytes(storage)
    with pytest.raises(
        SemanticEventReplayError,
        match="checkpoint signature is invalid",
    ):
        reopened.validate_semantic_replay_checkpoint(forged)
    assert _directory_bytes(storage) == bytes_before


def test_unavailable_slot_blocks_cutover_without_changing_active_policy(
    tmp_path,
) -> None:
    policy_a = _policy()
    policy_b = _rank_policy(20, "policy-b")
    harness = _harness(tmp_path, policy_a)
    plan = harness.store.plan_trust_policy_migration(
        policy_a,
        policy_b,
        arbitration_as_of=T0 + timedelta(hours=1),
        writer_binding=harness.binding,
    )
    after_plan = tuple(harness.plane.list_records())
    unavailable = harness.store.policy_migration.unavailable_trust_result(
        plan,
        plan.slot_plans[0],
        reason="operator_action_required",
        retryable=False,
    )

    with pytest.raises(PolicyMigrationError, match="policy_migration_incomplete"):
        harness.store.cutover_trust_policy(
            plan,
            policy_b,
            (unavailable,),
            writer_binding=harness.binding,
            final_catch_up_watermark=plan.base_catch_up_watermark,
            expected_partition_revision=0,
            complete_read_set_digest=_digest("blocked-read-set"),
        )

    after_unavailable = tuple(harness.plane.list_records())
    assert len(after_unavailable) > len(after_plan)
    assert any(
        record.source_kind == "semantic_projection_trust_migration_result"
        for record in after_unavailable
    )
    assert (
        harness.store.projection_history.current_trust(
            policy_fingerprint=policy_a.fingerprint
        ).pointer.policy_fingerprint
        == policy_a.fingerprint
    )


def test_temporal_unavailable_slot_blocks_cutover_without_changing_active_policy(
    tmp_path,
) -> None:
    trust = _policy()
    temporal_a = _temporal_policy("optional", "temporal-unavailable-a")
    temporal_b = _temporal_policy("required", "temporal-unavailable-b")
    harness = _harness(
        tmp_path,
        trust,
        temporal_policy_fingerprint=temporal_a.fingerprint,
    )
    plan = harness.store.plan_temporal_policy_migration(
        temporal_a,
        temporal_b,
        trust,
        writer_binding=harness.binding,
    )
    unavailable = harness.store.policy_migration.unavailable_temporal_result(
        plan,
        plan.slot_plans[0],
        reason="operator_action_required",
        retryable=False,
    )

    with pytest.raises(PolicyMigrationError, match="policy_migration_incomplete"):
        harness.store.cutover_temporal_policy(
            plan,
            temporal_b,
            (unavailable,),
            writer_binding=harness.binding,
            final_catch_up_watermark=plan.base_catch_up_watermark,
            expected_partition_revision=0,
            complete_read_set_digest=_digest("temporal-blocked-read-set"),
        )

    assert any(
        record.source_kind == "semantic_projection_temporal_migration_result"
        for record in harness.plane.list_records()
    )
    assert (
        harness.store.projection_history.current_temporal(
            policy_fingerprint=temporal_a.fingerprint
        ).pointer.policy_fingerprint
        == temporal_a.fingerprint
    )


def test_temporal_cutover_and_forward_rollback_preserve_immutable_history(
    tmp_path,
) -> None:
    trust = _policy()
    temporal_a = _temporal_policy("optional", "temporal-rollback-a")
    temporal_b = _temporal_policy("required", "temporal-rollback-b")
    harness = _harness(
        tmp_path,
        trust,
        temporal_policy_fingerprint=temporal_a.fingerprint,
    )

    harness.now[0] = T0 + timedelta(hours=1)
    plan_b = harness.store.plan_temporal_policy_migration(
        temporal_a, temporal_b, trust, writer_binding=harness.binding
    )
    results_b = harness.store.run_temporal_policy_migration(
        plan_b, temporal_b, trust, writer_binding=harness.binding
    )
    binding_b = harness.store.cutover_temporal_policy(
        plan_b,
        temporal_b,
        results_b,
        writer_binding=harness.binding,
        final_catch_up_watermark=plan_b.base_catch_up_watermark,
        expected_partition_revision=0,
        complete_read_set_digest=_digest("temporal-rollback-b-read-set"),
    )

    harness.now[0] = T0 + timedelta(hours=2)
    plan_a = harness.store.plan_temporal_policy_migration(
        temporal_b, temporal_a, trust, writer_binding=binding_b
    )
    results_a = harness.store.run_temporal_policy_migration(
        plan_a, temporal_a, trust, writer_binding=binding_b
    )
    binding_a = harness.store.cutover_temporal_policy(
        plan_a,
        temporal_a,
        results_a,
        writer_binding=binding_b,
        final_catch_up_watermark=plan_a.base_catch_up_watermark,
        expected_partition_revision=0,
        complete_read_set_digest=_digest("temporal-rollback-a-read-set"),
    )

    historical_a = harness.store.projection_history.historical_temporal(
        system_as_of=T0
    )
    historical_b = harness.store.projection_history.historical_temporal(
        system_as_of=T0 + timedelta(hours=1)
    )
    current_a = harness.store.projection_history.current_temporal(
        policy_fingerprint=temporal_a.fingerprint
    )
    assert binding_a.expected_writer_epoch == 3
    assert historical_a.pointer.policy_fingerprint == temporal_a.fingerprint
    assert historical_b.pointer.policy_fingerprint == temporal_b.fingerprint
    assert current_a.pointer.policy_fingerprint == temporal_a.fingerprint
    assert len(
        {
            historical_a.generation.generation_digest,
            historical_b.generation.generation_digest,
            current_a.generation.generation_digest,
        }
    ) == 3


def test_temporal_plan_progress_and_cutover_recover_lost_acknowledgements(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trust = _policy()
    temporal_a = _temporal_policy("optional", "temporal-lost-ack-a")
    temporal_b = _temporal_policy("required", "temporal-lost-ack-b")
    harness = _harness(
        tmp_path,
        trust,
        temporal_policy_fingerprint=temporal_a.fingerprint,
    )
    backend = harness.plane._records
    original_apply = backend.apply_batch
    lost = False

    def lose_once(source_kind: str, message: str):
        def apply(*args, **kwargs):
            nonlocal lost
            result = original_apply(*args, **kwargs)
            records = args[0] if args else kwargs["records"]
            if not lost and any(record.source_kind == source_kind for record in records):
                lost = True
                raise OSError(message)
            return result

        return apply

    monkeypatch.setattr(
        backend,
        "apply_batch",
        lose_once("semantic_projection_temporal_migration_plan", "temporal plan lost acknowledgement"),
    )
    with pytest.raises(OSError, match="temporal plan lost acknowledgement"):
        harness.store.plan_temporal_policy_migration(
            temporal_a, temporal_b, trust, writer_binding=harness.binding
        )

    recovered = harness.reopen()
    plan = recovered.store.plan_temporal_policy_migration(
        temporal_a, temporal_b, trust, writer_binding=recovered.binding
    )
    backend = recovered.plane._records
    original_apply = backend.apply_batch
    lost = False
    monkeypatch.setattr(
        backend,
        "apply_batch",
        lose_once("semantic_projection_temporal_migration_result", "temporal progress lost acknowledgement"),
    )
    with pytest.raises(OSError, match="temporal progress lost acknowledgement"):
        recovered.store.run_temporal_policy_migration(
            plan, temporal_b, trust, writer_binding=recovered.binding
        )

    progressed = recovered.reopen()
    results = progressed.store.run_temporal_policy_migration(
        plan, temporal_b, trust, writer_binding=progressed.binding
    )
    backend = progressed.plane._records
    original_apply = backend.apply_batch
    lost = False
    monkeypatch.setattr(
        backend,
        "apply_batch",
        lose_once("semantic_projection_temporal_migration_cutover", "temporal cutover lost acknowledgement"),
    )
    with pytest.raises(OSError, match="temporal cutover lost acknowledgement"):
        progressed.store.cutover_temporal_policy(
            plan,
            temporal_b,
            results,
            writer_binding=progressed.binding,
            final_catch_up_watermark=plan.base_catch_up_watermark,
            expected_partition_revision=0,
            complete_read_set_digest=_digest("temporal-lost-ack-read-set"),
        )

    completed = progressed.reopen()
    records_before_retry = tuple(completed.plane.list_records())
    binding = completed.store.cutover_temporal_policy(
        plan,
        temporal_b,
        results,
        writer_binding=progressed.binding,
        final_catch_up_watermark=plan.base_catch_up_watermark,
        expected_partition_revision=0,
        complete_read_set_digest=_digest("temporal-lost-ack-read-set"),
    )
    assert binding.expected_writer_epoch == progressed.binding.expected_writer_epoch + 1
    assert tuple(completed.plane.list_records()) == records_before_retry


def test_trust_cutover_binds_scheduled_decay_membership_before_due_execution(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decay = TrustDecayStep(
        minimum_age=timedelta(days=1),
        authority_loss=20,
        eligibility="ineligible",
    )
    policy_a = _policy(decay)
    policy_b = TrustPolicySnapshot.create(
        policy_revision="migration-decay-policy-b",
        system_effective_interval=TimeInterval(
            start=T0, end=T0 + timedelta(days=365)
        ),
        rules=(
            PredicateTrustRule(
                predicate_id="works_for",
                eligible_authority_classes=frozenset({"official"}),
                authority_rank_by_class={"official": 20},
                decay_age_basis="assertion_system_start",
                decay_schedule_by_class={"official": (decay,)},
            ),
        ),
    )
    harness = _harness(tmp_path, policy_a)
    plan = harness.store.plan_trust_policy_migration(
        policy_a,
        policy_b,
        arbitration_as_of=T0,
        writer_binding=harness.binding,
    )
    result = harness.store.policy_migration.trust_result(
        plan,
        plan.slot_plans[0],
        policy_b,
        complete_read_set_digest=_digest("migration-decay-read-set"),
    )
    assert result.decay_command_digests
    harness.store.cutover_trust_policy(
        plan,
        policy_b,
        (result,),
        writer_binding=harness.binding,
        final_catch_up_watermark=plan.base_catch_up_watermark,
        expected_partition_revision=0,
        complete_read_set_digest=_digest("migration-decay-read-set"),
    )
    current = harness.store.projection_history.current_trust(
        policy_fingerprint=policy_b.fingerprint
    )
    assert current.generation.canonical_decay_command_digests == result.decay_command_digests
    assert {
        command.command_digest
        for command in harness.store.projection_scheduler.pending_commands(policy_b)
    } == set(result.decay_command_digests)

    reopened = harness.reopen()
    assert {
        command.command_digest
        for command in reopened.store.projection_scheduler.pending_commands(policy_b)
    } == set(result.decay_command_digests)
    reopened.now[0] = T0 + timedelta(days=1)
    backend = reopened.plane._records
    original_apply = backend.apply_batch
    lost_ack = False

    def lose_due_ack(*args, **kwargs):
        nonlocal lost_ack
        result_value = original_apply(*args, **kwargs)
        records = args[0] if args else kwargs["records"]
        if not lost_ack and any(
            record.source_kind == "semantic_projection_trust_generation"
            for record in records
        ):
            lost_ack = True
            raise OSError("migrated decay lost acknowledgement")
        return result_value

    monkeypatch.setattr(backend, "apply_batch", lose_due_ack)
    with pytest.raises(OSError, match="migrated decay lost acknowledgement"):
        reopened.store.run_due_trust_decay(
            policy_b,
            writer_binding=reopened.binding,
            complete_read_set_digest=_digest("migration-decay-read-set"),
        )
    assert lost_ack
    completed = reopened.reopen()
    assert completed.store.run_due_trust_decay(
        policy_b,
        writer_binding=completed.binding,
        complete_read_set_digest=_digest("migration-decay-read-set"),
    ) == ()


@pytest.mark.parametrize("winner", ("decay", "cutover"))
def test_cutover_and_decay_conflict_authority_share_projection_cas(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    winner: Literal["decay", "cutover"],
) -> None:
    decay = TrustDecayStep(
        minimum_age=timedelta(days=1), authority_loss=20, eligibility="ineligible"
    )
    policy_a = _policy(decay)
    policy_b = TrustPolicySnapshot.create(
        policy_revision=f"race-decay-policy-b-{winner}",
        system_effective_interval=TimeInterval(start=T0, end=T0 + timedelta(days=365)),
        rules=(
            PredicateTrustRule(
                predicate_id="works_for",
                eligible_authority_classes=frozenset({"official"}),
                authority_rank_by_class={"official": 20},
                decay_age_basis="assertion_system_start",
                decay_schedule_by_class={"official": (decay,)},
            ),
        ),
    )
    harness = _harness(tmp_path, policy_a)
    read_set = _digest(f"decay-cutover-race-{winner}")
    assert harness.store.reconcile_trust_decay(
        policy_a, writer_binding=harness.binding, complete_read_set_digest=read_set
    )
    harness.now[0] = T0 + timedelta(days=1)
    plan = harness.store.plan_trust_policy_migration(
        policy_a, policy_b, arbitration_as_of=harness.now[0], writer_binding=harness.binding
    )
    result = harness.store.policy_migration.trust_result(
        plan, plan.slot_plans[0], policy_b, complete_read_set_digest=read_set
    )
    rendezvous = Barrier(2)
    winner_done = Event()
    original = harness.plane.conditionally_write_records

    def ordered_write(records, *, preconditions=(), authorization=None, transaction_precondition=None):
        is_cutover = any(
            record.source_kind == "semantic_projection_trust_migration_cutover"
            for record in records
        )
        is_decay = any(
            record.content.get("publication_kind") == "trust_decay_threshold"
            for record in records
        )
        contender = "cutover" if is_cutover else "decay" if is_decay else None
        if contender is not None:
            rendezvous.wait(timeout=30)
            if contender != winner:
                assert winner_done.wait(timeout=10)
            try:
                return original(records, preconditions=preconditions, authorization=authorization,
                                transaction_precondition=transaction_precondition)
            finally:
                if contender == winner:
                    winner_done.set()
        return original(records, preconditions=preconditions, authorization=authorization,
                        transaction_precondition=transaction_precondition)

    monkeypatch.setattr(harness.plane, "conditionally_write_records", ordered_write)

    def due_attempt():
        try:
            return harness.store.run_due_trust_decay(
                policy_a, writer_binding=harness.binding, complete_read_set_digest=read_set
            )
        except Exception as exc:
            return exc

    def cutover_attempt():
        try:
            return harness.store.cutover_trust_policy(
                plan, policy_b, (result,), writer_binding=harness.binding,
                final_catch_up_watermark=plan.base_catch_up_watermark,
                expected_partition_revision=0, complete_read_set_digest=read_set,
            )
        except Exception as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        due_future = executor.submit(due_attempt)
        cutover_future = executor.submit(cutover_attempt)
        due = due_future.result(timeout=90)
        cutover = cutover_future.result(timeout=90)
    monkeypatch.setattr(harness.plane, "conditionally_write_records", original)
    assert sum(not isinstance(item, Exception) for item in (due, cutover)) == 1
    if winner == "decay":
        assert isinstance(
            cutover,
            (MemoryPlaneRevisionConflictError, PolicyMigrationError, PreplanningStoreError),
        )
        records_before_retry = tuple(harness.plane.list_records())
        with pytest.raises(
            (MemoryPlaneRevisionConflictError, PolicyMigrationError, PreplanningStoreError)
        ):
            harness.store.cutover_trust_policy(
                plan, policy_b, (result,), writer_binding=harness.binding,
                final_catch_up_watermark=plan.base_catch_up_watermark,
                expected_partition_revision=0, complete_read_set_digest=read_set,
            )
        assert tuple(harness.plane.list_records()) == records_before_retry
        assert harness.store.projection_history.current_trust(
            policy_fingerprint=policy_a.fingerprint
        ).pointer.policy_fingerprint == policy_a.fingerprint
    else:
        assert isinstance(due, (MemoryPlaneRevisionConflictError, PreplanningStoreError, SemanticWriterAdmissionError))
        assert not isinstance(cutover, Exception)
        applied = harness.store.run_due_trust_decay(
            policy_b, writer_binding=cutover, complete_read_set_digest=read_set
        )
        assert applied == ()
        assert harness.store.run_due_trust_decay(
            policy_b, writer_binding=cutover, complete_read_set_digest=read_set
        ) == ()
        assert harness.store.projection_history.current_trust(
            policy_fingerprint=policy_b.fingerprint
        ).pointer.policy_fingerprint == policy_b.fingerprint
    record_ids = [record.memory_id for record in harness.plane.list_records()]
    assert len(record_ids) == len(set(record_ids))
    reopened = harness.reopen()
    assert [record.memory_id for record in reopened.plane.list_records()] == record_ids


def test_normal_event_atomically_appends_catch_up_then_restart_cutover(
    tmp_path,
) -> None:
    storage = tmp_path / "policy-migration-catch-up"
    (
        plane,
        _,
        store,
        binding,
        fence,
        service,
        authorization_repository,
    ) = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(storage),
        now_provider=lambda: T0,
        with_test_conflict_authority=True,
    )
    initial = accepted_terminal(operation_id=fence.operation_id)
    _activate(authorization_repository, fence, initial)
    service.persist(
        fence=fence,
        terminal=initial,
        authorization_verifier=AUTHORIZATION,
    )
    assert initial.arbitration_policy_bundle is not None
    active = initial.arbitration_policy_bundle.trust_policy
    pending_terminal = accepted_terminal(
        operation_id=_digest("pending-policy-template"),
        authority_rank_by_class={"official": 20},
    )
    assert pending_terminal.arbitration_policy_bundle is not None
    pending = pending_terminal.arbitration_policy_bundle.trust_policy
    plan = store.plan_trust_policy_migration(
        active,
        pending,
        arbitration_as_of=T0 + timedelta(hours=1),
        writer_binding=binding,
    )
    base_result = store.policy_migration.trust_result(
        plan,
        plan.slot_plans[0],
        pending,
        complete_read_set_digest=_digest("catch-up-read-set"),
    )

    _persist_one_normal_event(
        store,
        plane=plane,
        service=service,
        authorization_repository=authorization_repository,
        coordinate="migration-late-arrival",
    )
    catch_up_records = plane.list_records(
        source_kind="semantic_projection_trust_migration_catch_up"
    )
    assert len(catch_up_records) == 1
    assert store.semantic_replay_state().graph_revision != plan.base_graph_revision

    reopened_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage)
    )
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: T0,
    )
    from memorii.core.memory_evolution.atomic_store import (
        SemanticIngestionAtomicStore,
    )

    reopened = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: T0,
        semantic_conflict_authority_resolver=_TestSemanticConflictAuthorityResolver(
            reopened_plane
        ),
    )
    reopened_binding = reopened_writers.commit_binding(reopened_writers.current())
    catch_up, _ = reopened.policy_migration._load_trust_progress(plan)
    assert len(catch_up) == 1
    entry = catch_up[0]
    assert entry.partition_revision == 1
    assert entry.graph_revision == reopened.semantic_replay_state().graph_revision
    assert entry.watermark == reopened.semantic_event_batches()[-1].source_event_batch_digest
    catch_up_result = reopened.policy_migration.trust_result(
        plan,
        entry.slot_plan,
        pending,
        complete_read_set_digest=_digest("catch-up-read-set"),
        catch_up_entry=entry,
    )

    successor = reopened.cutover_trust_policy(
        plan,
        pending,
        (base_result, catch_up_result),
        writer_binding=reopened_binding,
        catch_up=catch_up,
        final_catch_up_watermark=entry.watermark,
        expected_partition_revision=entry.partition_revision,
        complete_read_set_digest=_digest("catch-up-read-set"),
    )

    # The cutover activated a new writer epoch; the post-cutover clarification
    # authorities must bind the successor.
    reopened_binding = reopened_writers.commit_binding(reopened_writers.current())
    reopened_repository = SemanticAuthorizationAuthorityRepository(
        atomic_store=reopened,
        writer_binding_provider=lambda: reopened_binding,
        now_provider=lambda: T0,
    )
    reopened_service = SemanticTerminalPersistenceService(
        atomic_store=reopened,
        writer_binding_provider=lambda: reopened_binding,
        authorization_repository=reopened_repository,
    )
    assert successor.expected_writer_epoch == reopened_binding.expected_writer_epoch
    assert (
        reopened.projection_history.current_trust(
            policy_fingerprint=pending.fingerprint
        ).generation.base_graph_revision
        == entry.graph_revision
    )
    assert len(
        reopened_plane.list_records(
            source_kind="semantic_projection_trust_migration_catch_up"
        )
    ) == 1

    _commit_clarification_terminal(
        reopened,
        plane=reopened_plane,
        service=reopened_service,
        authorization_repository=reopened_repository,
        coordinate=_digest("first-post-cutover-new-policy"),
        authority_rank_by_class={"official": 20},
    )
    # The cutover completed the plan; post-cutover writes run directly under
    # the new policy and append no migration catch-up work.
    assert len(
        reopened_plane.list_records(
            source_kind="semantic_projection_trust_migration_catch_up"
        )
    ) == 1

    before_stale = _semantic_effect_record_ids(reopened_plane)
    with pytest.raises(
        (PreplanningStoreError, SemanticWriterAdmissionError),
    ):
        _commit_clarification_terminal(
            reopened,
            plane=reopened_plane,
            service=reopened_service,
            authorization_repository=reopened_repository,
            coordinate=_digest("post-cutover-stale-old-policy"),
        )
    assert _semantic_effect_record_ids(reopened_plane) == before_stale


def test_temporal_migration_replays_retained_evidence_and_rebases_late_writes(
    tmp_path,
) -> None:
    storage = tmp_path / "temporal-policy-migration-catch-up"
    (
        plane,
        _,
        store,
        binding,
        fence,
        service,
        authorization_repository,
    ) = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(storage),
        now_provider=lambda: T0,
        with_test_conflict_authority=True,
    )
    initial = accepted_terminal(operation_id=fence.operation_id)
    _activate(authorization_repository, fence, initial)
    service.persist(
        fence=fence,
        terminal=initial,
        authorization_verifier=AUTHORIZATION,
    )
    assert initial.arbitration_policy_bundle is not None
    active_temporal = initial.arbitration_policy_bundle.temporal_policy
    active_trust = initial.arbitration_policy_bundle.trust_policy
    pending_terminal = accepted_terminal(
        operation_id=_digest("pending-atemporal-policy-template"),
        atemporal=True,
    )
    assert pending_terminal.arbitration_policy_bundle is not None
    pending_temporal = pending_terminal.arbitration_policy_bundle.temporal_policy
    plan = store.plan_temporal_policy_migration(
        active_temporal,
        pending_temporal,
        active_trust,
        writer_binding=binding,
    )
    _persist_one_normal_event(
        store,
        plane=plane,
        service=service,
        authorization_repository=authorization_repository,
        coordinate="temporal-migration-late-arrival",
    )
    reopened_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage)
    )
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: T0,
    )
    from memorii.core.memory_evolution.atomic_store import (
        SemanticIngestionAtomicStore,
    )

    reopened = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: T0,
        semantic_conflict_authority_resolver=_TestSemanticConflictAuthorityResolver(
            reopened_plane
        ),
    )
    reopened_binding = reopened_writers.commit_binding(reopened_writers.current())
    catch_up, _ = reopened.policy_migration._load_temporal_progress(plan)
    assert len(catch_up) == 1
    commands = reopened.policy_migration.temporal_commands(plan)
    assert {item.migration_work_item_digest for item in commands} == {
        plan.slot_plans[0].slot_plan_digest,
        catch_up[0].entry_digest,
    }
    assert commands == tuple(
        sorted(commands, key=lambda item: (item.policy_effective_at, item.command_id))
    )
    results = reopened.run_temporal_policy_migration(
        plan,
        pending_temporal,
        active_trust,
        writer_binding=reopened_binding,
    )
    assert len(results) == 2
    committed_results = tuple(
        item for item in results if item.status == "committed"
    )
    assert all(
        item.projections[0].valid_interval is None
        for item in committed_results
    )

    successor = reopened.cutover_temporal_policy(
        plan,
        pending_temporal,
        results,
        writer_binding=reopened_binding,
        catch_up=catch_up,
        final_catch_up_watermark=catch_up[0].watermark,
        expected_partition_revision=catch_up[0].partition_revision,
        complete_read_set_digest=_digest("temporal-cutover-read-set"),
    )
    # The cutover activated a new writer epoch; the post-cutover clarification
    # authorities must bind the successor.
    reopened_binding = reopened_writers.commit_binding(reopened_writers.current())
    reopened_repository = SemanticAuthorizationAuthorityRepository(
        atomic_store=reopened,
        writer_binding_provider=lambda: reopened_binding,
        now_provider=lambda: T0,
    )
    reopened_service = SemanticTerminalPersistenceService(
        atomic_store=reopened,
        writer_binding_provider=lambda: reopened_binding,
        authorization_repository=reopened_repository,
    )
    assert successor.expected_writer_epoch == reopened_binding.expected_writer_epoch

    _commit_clarification_terminal(
        reopened,
        plane=reopened_plane,
        service=reopened_service,
        authorization_repository=reopened_repository,
        coordinate=_digest("first-post-temporal-cutover"),
        atemporal=True,
    )
    # The cutover completed the plan; post-cutover writes run directly under
    # the new policy and append no migration catch-up work.
    assert len(
        reopened_plane.list_records(
            source_kind="semantic_projection_temporal_migration_catch_up"
        )
    ) == 1

    before_stale = _semantic_effect_record_ids(reopened_plane)
    with pytest.raises((PreplanningStoreError, SemanticWriterAdmissionError)):
        _commit_clarification_terminal(
            reopened,
            plane=reopened_plane,
            service=reopened_service,
            authorization_repository=reopened_repository,
            coordinate=_digest("stale-required-temporal-policy"),
        )
    assert _semantic_effect_record_ids(reopened_plane) == before_stale


def test_post_cutover_write_resolves_retained_reference_only_evidence(
    tmp_path,
) -> None:
    storage = tmp_path / "temporal-reference-rebase"
    reference_instant = T0 + timedelta(days=3)
    (
        plane,
        _,
        store,
        binding,
        fence,
        service,
        authorization_repository,
    ) = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(storage),
        now_provider=lambda: T0,
        with_test_conflict_authority=True,
    )
    initial = accepted_terminal(
        operation_id=fence.operation_id,
        temporal_requirement="optional",
        reference_instant=reference_instant,
    )
    _activate(authorization_repository, fence, initial)
    service.persist(
        fence=fence,
        terminal=initial,
        authorization_verifier=AUTHORIZATION,
    )
    assert initial.arbitration_policy_bundle is not None
    active_temporal = initial.arbitration_policy_bundle.temporal_policy
    active_trust = initial.arbitration_policy_bundle.trust_policy
    before_cutover = store.projection_history.current_temporal(
        policy_fingerprint=active_temporal.fingerprint
    )
    # The original policy deliberately does not promote reference-only evidence
    # into a valid-time interval. Cutover must rebase that retained assertion
    # under the new authority rather than rely on a new temporal candidate.
    assert before_cutover.projections[0].valid_interval is None
    assert before_cutover.projections[0].outcome == "pass"
    pending_terminal = accepted_terminal(
        operation_id=_digest("reference-enabled-policy-template"),
        temporal_requirement="required",
        allow_reference_as_effective_start=True,
        reference_instant=reference_instant,
    )
    assert pending_terminal.arbitration_policy_bundle is not None
    pending_temporal = pending_terminal.arbitration_policy_bundle.temporal_policy
    plan = store.plan_temporal_policy_migration(
        active_temporal,
        pending_temporal,
        active_trust,
        writer_binding=binding,
    )
    results = store.run_temporal_policy_migration(
        plan,
        pending_temporal,
        active_trust,
        writer_binding=binding,
    )
    assert len(results) == 1 and results[0].status == "committed"
    assert results[0].projections[0].valid_interval == TimeInterval(
        start=reference_instant
    )
    successor = store.cutover_temporal_policy(
        plan,
        pending_temporal,
        results,
        writer_binding=binding,
        final_catch_up_watermark=plan.base_catch_up_watermark,
        expected_partition_revision=0,
        complete_read_set_digest=_digest("reference-cutover-read-set"),
    )
    # The cutover activated a new writer epoch; the persistence authorities
    # used by the post-cutover clarification must bind the successor.
    binding = store._writers.commit_binding(store._writers.current())
    authorization_repository = SemanticAuthorizationAuthorityRepository(
        atomic_store=store,
        writer_binding_provider=lambda: binding,
        now_provider=lambda: T0,
    )
    service = SemanticTerminalPersistenceService(
        atomic_store=store,
        writer_binding_provider=lambda: binding,
        authorization_repository=authorization_repository,
    )
    rebased = store.projection_history.current_temporal(
        policy_fingerprint=pending_temporal.fingerprint
    )
    assert rebased.projections[0].valid_interval == TimeInterval(
        start=reference_instant
    )
    assert rebased.projections[0].outcome == "pass"

    # The claim lifecycle derives its own processing operation id, so the
    # post-cutover write's assertion identity is read from the committed
    # terminal itself rather than predicted from a probe operation id.
    _receipt, committed_terminal = _commit_clarification_terminal(
        store,
        plane=plane,
        service=service,
        authorization_repository=authorization_repository,
        coordinate=_digest("reference-enabled-post-cutover-write"),
        temporal_requirement="required",
        allow_reference_as_effective_start=True,
        reference_instant=reference_instant,
    )
    current = store.projection_history.current_temporal(
        policy_fingerprint=pending_temporal.fingerprint
    )
    assert current.pointer.policy_fingerprint == pending_temporal.fingerprint
    assert all(
        projection.temporal_policy_fingerprint == pending_temporal.fingerprint
        for projection in current.projections
    )
    assert current.projections[0].valid_interval == TimeInterval(
        start=reference_instant
    )
    assert committed_terminal.accepted_carriers[0].claim_assertion_id in {
        evidence.candidate_id
        for projection in current.projections
        for evidence in projection.evidence
    }
    records_before_stale = _semantic_effect_record_ids(plane)
    with pytest.raises((PreplanningStoreError, SemanticWriterAdmissionError)):
        _commit_clarification_terminal(
            store,
            plane=plane,
            service=service,
            authorization_repository=authorization_repository,
            coordinate=_digest("reference-only-stale-old-policy"),
            temporal_requirement="optional",
            reference_instant=reference_instant,
        )
    assert _semantic_effect_record_ids(plane) == records_before_stale
    reopened_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage)
    )
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: T0,
    )
    from memorii.core.memory_evolution.atomic_store import (
        SemanticIngestionAtomicStore,
    )

    reopened = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: T0,
    )
    assert reopened_writers.current().writer_epoch == successor.expected_writer_epoch
    assert reopened.projection_history.current_temporal(
        policy_fingerprint=pending_temporal.fingerprint
    ) == current


@pytest.mark.parametrize("winner", ("event", "cutover"))
def test_normal_writer_and_cutover_race_has_one_linearized_winner(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    winner: Literal["event", "cutover"],
) -> None:
    storage = tmp_path / f"policy-race-{winner}"
    (
        plane,
        _,
        store,
        binding,
        fence,
        service,
        authorization_repository,
    ) = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(storage),
        now_provider=lambda: T0,
        with_test_conflict_authority=True,
    )
    initial = accepted_terminal(operation_id=fence.operation_id)
    _activate(authorization_repository, fence, initial)
    service.persist(
        fence=fence,
        terminal=initial,
        authorization_verifier=AUTHORIZATION,
    )
    assert initial.arbitration_policy_bundle is not None
    active = initial.arbitration_policy_bundle.trust_policy
    # Pre-stage the racing event's admission BEFORE the migration plan reads
    # the plane: the admission handoff advances the event-authority aggregate,
    # and a freely-running unclassified admission write would move it under
    # the cutover's captured read set mid-race.  With the admission staged,
    # the race exercises exactly the two linearized graph writes.
    from semantic_terminal_test_support import handoff as _handoff

    _, race_fence = _handoff(
        plane,
        coordinate=f"race-event-{winner}",
        scope_ids=frozenset({"scope:a"}),
        atomic_store=store,
        writer_binding=store._writers.commit_binding(store._writers.current()),
    )
    race_terminal = accepted_terminal(operation_id=race_fence.operation_id)
    _activate(authorization_repository, race_fence, race_terminal)
    pending_terminal = accepted_terminal(
        operation_id=_digest(f"race-pending-{winner}"),
        authority_rank_by_class={"official": 20},
    )
    assert pending_terminal.arbitration_policy_bundle is not None
    pending = pending_terminal.arbitration_policy_bundle.trust_policy
    plan = store.plan_trust_policy_migration(
        active,
        pending,
        arbitration_as_of=T0 + timedelta(hours=1),
        writer_binding=binding,
    )
    base_result = store.policy_migration.trust_result(
        plan,
        plan.slot_plans[0],
        pending,
        complete_read_set_digest=_digest(f"race-read-set-{winner}"),
    )
    winner_done = Event()
    event_thread_idents: set[int] = set()
    original = plane.conditionally_write_records

    def ordered_write(
        records,
        *,
        preconditions=(),
        authorization=None,
        transaction_precondition=None,
    ):
        # A persist and a cutover each stage several conditional writes
        # (fence control, generation manifests, plan/result publication)
        # before their graph-advancing batch, so the contender cannot be
        # classified by record kind: every write is attributed to its
        # attempt's thread, and the loser's first write linearizes behind
        # the winner's complete attempt.
        import threading as _threading

        contender = (
            "event"
            if _threading.get_ident() in event_thread_idents
            else "cutover"
        )
        if contender != winner and not winner_done.wait(timeout=60):
            raise AssertionError("race winner did not complete its attempt")
        return original(
            records,
            preconditions=preconditions,
            authorization=authorization,
            transaction_precondition=transaction_precondition,
        )

    monkeypatch.setattr(plane, "conditionally_write_records", ordered_write)

    def event_attempt():
        import threading as _threading

        event_thread_idents.add(_threading.get_ident())
        try:
            service.persist(
                fence=race_fence,
                terminal=race_terminal,
                authorization_verifier=AUTHORIZATION,
            )
            return None
        except Exception as exc:  # the losing CAS is the asserted result
            return exc
        finally:
            if winner == "event":
                winner_done.set()

    def cutover_attempt():
        try:
            return store.cutover_trust_policy(
                plan,
                pending,
                (base_result,),
                writer_binding=binding,
                final_catch_up_watermark=plan.base_catch_up_watermark,
                expected_partition_revision=0,
                complete_read_set_digest=_digest(f"race-read-set-{winner}"),
            )
        except Exception as exc:  # the losing CAS is the asserted result
            return exc
        finally:
            if winner == "cutover":
                winner_done.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        event_future = executor.submit(event_attempt)
        cutover_future = executor.submit(cutover_attempt)
        event_outcome = event_future.result(timeout=90)
        cutover_outcome = cutover_future.result(timeout=90)

    monkeypatch.setattr(plane, "conditionally_write_records", original)
    if winner == "event":
        assert not isinstance(event_outcome, Exception), (
            event_outcome,
            cutover_outcome,
        )
        assert isinstance(
            cutover_outcome,
            (
                MemoryPlaneRevisionConflictError,
                PreplanningStoreError,
                # The losing cutover can fail closed at its plan freshness
                # gate before any conditional write: a stale plan after the
                # event's linearized writes is the same CAS-class rejection.
                PolicyMigrationError,
            ),
        )
        catch_up, _ = store.policy_migration._load_trust_progress(plan)
        assert len(catch_up) == 1
        catch_up_result = store.policy_migration.trust_result(
            plan,
            catch_up[0].slot_plan,
            pending,
            complete_read_set_digest=_digest(f"race-read-set-{winner}"),
            catch_up_entry=catch_up[0],
        )
        successor = store.cutover_trust_policy(
            plan,
            pending,
            (base_result, catch_up_result),
            writer_binding=binding,
            catch_up=catch_up,
            final_catch_up_watermark=catch_up[0].watermark,
            expected_partition_revision=1,
            complete_read_set_digest=_digest(f"race-read-set-{winner}"),
        )
    else:
        assert not isinstance(cutover_outcome, Exception)
        assert isinstance(
            event_outcome,
            (
                MemoryPlaneRevisionConflictError,
                PreplanningStoreError,
                SemanticWriterAdmissionError,
            ),
        )
        successor = cutover_outcome
        assert not plane.list_records(
            source_kind="semantic_projection_trust_migration_catch_up"
        )

    assert (
        successor.expected_writer_epoch
        == binding.expected_writer_epoch + 1
    )
    committed_records = tuple(plane.list_records())
    reopened_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage)
    )
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: T0,
    )
    from memorii.core.memory_evolution.atomic_store import (
        SemanticIngestionAtomicStore,
    )

    reopened = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: T0,
    )
    assert _json_round_tripped(
        tuple(reopened_plane.list_records())
    ) == _json_round_tripped(committed_records)
    assert reopened_writers.current().writer_epoch == successor.expected_writer_epoch
    assert {
        item.trust_policy_fingerprint
        for item in reopened.projection_history.active_trust_authority().projections
    } == {pending.fingerprint}
    record_ids = [record.memory_id for record in committed_records]
    assert len(record_ids) == len(set(record_ids))


def test_reopened_catch_up_authority_substitution_matrix_fails_without_effect(
    tmp_path,
) -> None:
    storage = tmp_path / "policy-substitution-source"
    (
        plane,
        _,
        store,
        binding,
        fence,
        service,
        authorization_repository,
    ) = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(storage),
        now_provider=lambda: T0,
        with_test_conflict_authority=True,
    )
    initial = accepted_terminal(operation_id=fence.operation_id)
    _activate(authorization_repository, fence, initial)
    service.persist(
        fence=fence,
        terminal=initial,
        authorization_verifier=AUTHORIZATION,
    )
    assert initial.arbitration_policy_bundle is not None
    active = initial.arbitration_policy_bundle.trust_policy
    pending_terminal = accepted_terminal(
        operation_id=_digest("substitution-pending"),
        authority_rank_by_class={"official": 20},
    )
    assert pending_terminal.arbitration_policy_bundle is not None
    pending = pending_terminal.arbitration_policy_bundle.trust_policy
    plan = store.plan_trust_policy_migration(
        active,
        pending,
        arbitration_as_of=T0 + timedelta(hours=1),
        writer_binding=binding,
    )
    base_result = store.policy_migration.trust_result(
        plan,
        plan.slot_plans[0],
        pending,
        complete_read_set_digest=_digest("substitution-read-set"),
    )
    _persist_one_normal_event(
        store,
        plane=plane,
        service=service,
        authorization_repository=authorization_repository,
        coordinate="substitution-late-event",
    )
    catch_up, _ = store.policy_migration._load_trust_progress(plan)
    assert len(catch_up) == 1
    catch_result = store.policy_migration.trust_result(
        plan,
        catch_up[0].slot_plan,
        pending,
        complete_read_set_digest=_digest("substitution-read-set"),
        catch_up_entry=catch_up[0],
    )
    store._commit_policy_migration_progress(
        store.policy_migration.prepare_progress(
            plan,
            catch_up=catch_up,
            results=(base_result, catch_result),
        ),
        writer_binding=binding,
    )

    catch_kind = "semantic_projection_trust_migration_catch_up"
    result_kind = "semantic_projection_trust_migration_result"
    mutations = (
        ("kind", catch_kind, ("migration_kind",), "temporal"),
        ("plan", catch_kind, ("migration_plan_digest",), "0" * 64),
        ("old_policy", catch_kind, ("active_policy_fingerprint",), "0" * 64),
        ("pending_policy", catch_kind, ("pending_policy_fingerprint",), "0" * 64),
        ("writer_epoch", catch_kind, ("writer_epoch",), lambda value: value + 1),
        ("graph_revision", catch_kind, ("graph_revision",), "substituted"),
        ("graph_delta", catch_kind, ("graph_delta_digest",), "0" * 64),
        ("ledger_position", catch_kind, ("ledger_position",), lambda value: value + 1),
        ("watermark", catch_kind, ("watermark",), "0" * 64),
        ("read_set", catch_kind, ("complete_read_set_digest",), "0" * 64),
        (
            "partition_before",
            catch_kind,
            ("partition_revision_before",),
            lambda value: value + 1,
        ),
        (
            "partition_after",
            catch_kind,
            ("partition_revision",),
            lambda value: value + 1,
        ),
        ("membership", catch_kind, ("membership_digest",), "0" * 64),
        ("slot", catch_kind, ("slot_plan", "assertion_ids"), ()),
        ("result", result_kind, ("result_digest",), "0" * 64),
        ("availability", result_kind, ("status",), "unavailable"),
    )
    for name, source_kind, field_path, replacement in mutations:
        case_path = tmp_path / f"policy-substitution-{name}"
        shutil.copytree(storage, case_path)
        _substitute_persisted_authority(
            case_path,
            source_kind=source_kind,
            field_path=field_path,
            replacement=replacement,
        )
        case_plane = MemoryPlaneService(
            record_store=JsonlMemoryPlaneStore(case_path)
        )
        case_writers = SemanticWriterAdmissionStore(
            case_plane,
            bounded_preplanning_ownership_manifest(),
            now_provider=lambda: T0,
        )
        from memorii.core.memory_evolution.atomic_store import (
            SemanticIngestionAtomicStore,
        )

        case_store = SemanticIngestionAtomicStore(
            case_plane,
            case_writers,
            now_provider=lambda: T0,
        )
        pointer_before = case_store.projection_history.active_trust_authority().pointer
        epoch_before = case_writers.current().writer_epoch
        bytes_before = _directory_bytes(case_path)
        try:
            case_store.cutover_trust_policy(
                plan,
                pending,
                (base_result, catch_result),
                writer_binding=case_writers.commit_binding(case_writers.current()),
                catch_up=catch_up,
                final_catch_up_watermark=catch_up[0].watermark,
                expected_partition_revision=catch_up[0].partition_revision,
                complete_read_set_digest=_digest("substitution-read-set"),
            )
        except (
            PolicyMigrationError,
            PreplanningStoreError,
            ProjectionHistoryError,
            SemanticWriterAdmissionError,
        ):
            pass
        else:
            pytest.fail(f"{name} substitution was accepted")
        assert (
            case_store.projection_history.active_trust_authority().pointer
            == pointer_before
        )
        assert case_writers.current().writer_epoch == epoch_before
        assert _directory_bytes(case_path) == bytes_before


def test_policy_migration_apply_then_raise_recovers_plan_progress_and_cutover(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_a = _policy()
    policy_b = _rank_policy(20, "lost-ack-policy-b")
    harness = _harness(tmp_path, policy_a)
    backend = harness.plane._records
    original_apply = backend.apply_batch
    fired = False

    def lose_plan_ack(*args, **kwargs):
        nonlocal fired
        result = original_apply(*args, **kwargs)
        records = args[0] if args else kwargs["records"]
        if not fired and any(
            record.source_kind == "semantic_projection_trust_migration_plan"
            for record in records
        ):
            fired = True
            raise OSError("migration plan lost acknowledgement")
        return result

    monkeypatch.setattr(backend, "apply_batch", lose_plan_ack)
    with pytest.raises(OSError, match="plan lost acknowledgement"):
        harness.store.plan_trust_policy_migration(
            policy_a,
            policy_b,
            arbitration_as_of=T0 + timedelta(hours=1),
            writer_binding=harness.binding,
        )
    assert fired

    recovered = harness.reopen()
    plan = recovered.store.plan_trust_policy_migration(
        policy_a,
        policy_b,
        arbitration_as_of=T0 + timedelta(hours=1),
        writer_binding=recovered.binding,
    )
    result = recovered.store.policy_migration.trust_result(
        plan,
        plan.slot_plans[0],
        policy_b,
        complete_read_set_digest=_digest("lost-ack-read-set"),
    )
    backend = recovered.plane._records
    original_apply = backend.apply_batch
    fired = False

    def lose_progress_ack(*args, **kwargs):
        nonlocal fired
        result_value = original_apply(*args, **kwargs)
        records = args[0] if args else kwargs["records"]
        if not fired and any(
            record.source_kind == "semantic_projection_trust_migration_result"
            for record in records
        ):
            fired = True
            raise OSError("migration progress lost acknowledgement")
        return result_value

    monkeypatch.setattr(backend, "apply_batch", lose_progress_ack)
    prepared = recovered.store.policy_migration.prepare_progress(
        plan,
        results=(result,),
    )
    with pytest.raises(OSError, match="progress lost acknowledgement"):
        recovered.store._commit_policy_migration_progress(
            prepared,
            writer_binding=recovered.binding,
        )
    assert fired

    progressed = recovered.reopen()
    progressed.store._commit_policy_migration_progress(
        progressed.store.policy_migration.prepare_progress(
            plan,
            results=(result,),
        ),
        writer_binding=progressed.binding,
    )
    backend = progressed.plane._records
    original_apply = backend.apply_batch
    fired = False

    def lose_cutover_ack(*args, **kwargs):
        nonlocal fired
        result_value = original_apply(*args, **kwargs)
        records = args[0] if args else kwargs["records"]
        if not fired and any(
            record.source_kind == "semantic_projection_trust_migration_cutover"
            for record in records
        ):
            fired = True
            raise OSError("migration cutover lost acknowledgement")
        return result_value

    monkeypatch.setattr(backend, "apply_batch", lose_cutover_ack)
    with pytest.raises(OSError, match="cutover lost acknowledgement"):
        progressed.store.cutover_trust_policy(
            plan,
            policy_b,
            (result,),
            writer_binding=progressed.binding,
            final_catch_up_watermark=plan.base_catch_up_watermark,
            expected_partition_revision=0,
            complete_read_set_digest=_digest("lost-ack-read-set"),
        )
    assert fired

    completed = progressed.reopen()
    committed_records = tuple(completed.plane.list_records())
    successor = completed.store.cutover_trust_policy(
        plan,
        policy_b,
        (result,),
        writer_binding=progressed.binding,
        final_catch_up_watermark=plan.base_catch_up_watermark,
        expected_partition_revision=0,
        complete_read_set_digest=_digest("lost-ack-read-set"),
    )
    assert successor.expected_writer_epoch == progressed.binding.expected_writer_epoch + 1
    assert tuple(completed.plane.list_records()) == committed_records


def test_normal_catch_up_apply_then_raise_reopens_to_one_exact_partition(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = tmp_path / "catch-up-lost-ack"
    (
        plane,
        _,
        store,
        binding,
        fence,
        service,
        authorization_repository,
    ) = _setup(
        verified=True,
        backend=JsonlMemoryPlaneStore(storage),
        now_provider=lambda: T0,
        with_test_conflict_authority=True,
    )
    initial = accepted_terminal(operation_id=fence.operation_id)
    _activate(authorization_repository, fence, initial)
    service.persist(
        fence=fence,
        terminal=initial,
        authorization_verifier=AUTHORIZATION,
    )
    assert initial.arbitration_policy_bundle is not None
    active = initial.arbitration_policy_bundle.trust_policy
    pending = _rank_policy(20, "catch-up-lost-ack-pending")
    # Claim the canonical work once BEFORE planning: the lost acknowledgement
    # must fire inside the committed answer's catch-up append, and the retry
    # must replay the same claimed image rather than a second lifecycle.
    claim, cas = _claim_canonical_clarification(
        store,
        _digest("catch-up-lost-ack-operation"),
        plane=plane,
        service=service,
        authorization_repository=authorization_repository,
    )
    plan = store.plan_trust_policy_migration(
        active,
        pending,
        arbitration_as_of=T0 + timedelta(hours=1),
        writer_binding=binding,
    )
    backend = plane._records
    original_apply = backend.apply_batch
    fired = False

    def lose_catch_up_ack(*args, **kwargs):
        nonlocal fired
        result = original_apply(*args, **kwargs)
        records = args[0] if args else kwargs["records"]
        if not fired and any(
            record.source_kind == "semantic_projection_trust_migration_catch_up"
            for record in records
        ):
            fired = True
            raise OSError("migration catch-up lost acknowledgement")
        return result

    monkeypatch.setattr(backend, "apply_batch", lose_catch_up_ack)
    with pytest.raises(OSError, match="catch-up lost acknowledgement"):
        _commit_claimed_accepted_clarification(store, claim, cas)
    assert fired

    reopened_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage)
    )
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: T0,
    )
    from memorii.core.memory_evolution.atomic_store import (
        SemanticIngestionAtomicStore,
    )

    reopened = SemanticIngestionAtomicStore(
        reopened_plane,
        reopened_writers,
        now_provider=lambda: T0,
    )
    committed_records = tuple(reopened_plane.list_records())
    receipt, _, _ = _commit_claimed_accepted_clarification(reopened, claim, cas)
    assert receipt.processing_operation_id == claim.work.processing_operation_id
    assert tuple(reopened_plane.list_records()) == committed_records
    catch_up, _ = reopened.policy_migration._load_trust_progress(plan)
    assert len(catch_up) == 1
    assert catch_up[0].partition_revision == 1


def test_deleted_slot_produces_explicit_empty_catch_up_work(tmp_path) -> None:
    active = _policy()
    pending = _rank_policy(20, "deletion-pending")
    harness = _harness(tmp_path, active)
    plan = harness.store.plan_trust_policy_migration(
        active,
        pending,
        arbitration_as_of=T0 + timedelta(hours=1),
        writer_binding=harness.binding,
    )
    prepared = harness.store.policy_migration.prepare_write_catch_up(
        temporal_projections=(
            harness.store.projection_history.active_temporal_authority().projections
        ),
        trust_projections=(),
        trust_decay_command_digests=(),
        graph_revision="graph-after-delete",
        graph_delta_digest=_digest("delete-delta"),
        ledger_position=1,
        watermark=_digest("delete-event"),
        complete_read_set_digest=_digest("delete-read-set"),
    )

    assert len(prepared.trust_entries) == 1
    entry = prepared.trust_entries[0]
    assert entry.slot_plan.assertion_ids == ()
    assert entry.slot_plan.projection_digests == ()
    result = harness.store.policy_migration.trust_result(
        plan,
        entry.slot_plan,
        pending,
        complete_read_set_digest=_digest("delete-read-set"),
        catch_up_entry=entry,
    )
    assert result.projections == ()
    assert result.migration_work_item_digest == entry.entry_digest


def test_stale_base_plan_fails_closed_before_cutover(tmp_path) -> None:
    policy_a = _policy()
    policy_b = _rank_policy(20, "policy-b")
    harness = _harness(tmp_path, policy_a)
    plan = harness.store.plan_trust_policy_migration(
        policy_a,
        policy_b,
        arbitration_as_of=T0 + timedelta(hours=1),
        writer_binding=harness.binding,
    )
    result = harness.store.policy_migration.trust_result(
        plan,
        plan.slot_plans[0],
        policy_b,
        complete_read_set_digest=_digest("stale-read-set"),
    )
    stale = plan.model_copy(update={"writer_epoch": plan.writer_epoch + 1})

    with pytest.raises(PolicyMigrationError, match="policy_migration_stale_plan"):
        harness.store.policy_migration.prepare_trust_cutover(
            stale,
            policy_b,
            (result,),
            final_catch_up_watermark=stale.base_catch_up_watermark,
            expected_partition_revision=0,
            complete_read_set_digest=_digest("stale-read-set"),
            authorization=harness.store._writers._authorize_atomic(
                harness.binding,
                capability=harness.store._write_capability,
            ),
        )


def test_direct_migration_authority_write_without_atomic_envelope_is_rejected(
    tmp_path,
) -> None:
    policy_a = _policy()
    policy_b = _rank_policy(20, "policy-b")
    harness = _harness(tmp_path, policy_a)
    plan = harness.store.plan_trust_policy_migration(
        policy_a,
        policy_b,
        arbitration_as_of=T0 + timedelta(hours=1),
        writer_binding=harness.binding,
    )
    result = harness.store.policy_migration.trust_result(
        plan,
        plan.slot_plans[0],
        policy_b,
        complete_read_set_digest=_digest("direct-read-set"),
    )
    authorization = harness.store._writers._authorize_atomic(
        harness.binding,
        capability=harness.store._write_capability,
    )
    harness.store._commit_policy_migration_progress(
        harness.store.policy_migration.prepare_progress(
            plan,
            results=(result,),
        ),
        writer_binding=harness.binding,
    )
    prepared = harness.store.policy_migration.prepare_trust_cutover(
        plan,
        policy_b,
        (result,),
        final_catch_up_watermark=plan.base_catch_up_watermark,
        expected_partition_revision=0,
        complete_read_set_digest=_digest("direct-read-set"),
        authorization=authorization,
    )
    before = tuple(harness.plane.list_records())

    with pytest.raises(
        SemanticWriterAdmissionError,
        match="governed semantic write lacks one atomic control record",
    ):
        harness.plane.conditionally_write_records(
            (*prepared.publication.records, *prepared.authority_records),
            preconditions=(
                *prepared.publication.preconditions,
                *prepared.authority_preconditions,
            ),
            authorization=authorization,
        )

    assert tuple(harness.plane.list_records()) == before


def test_caller_fabricated_catch_up_cannot_enter_progress_authority(
    tmp_path,
) -> None:
    active = _policy()
    pending = _rank_policy(20, "forged-catch-up-pending")
    harness = _harness(tmp_path, active)
    plan = harness.store.plan_trust_policy_migration(
        active,
        pending,
        arbitration_as_of=T0 + timedelta(hours=1),
        writer_binding=harness.binding,
    )
    view = harness.store.projection_history.active_trust_authority()
    forged = harness.store.policy_migration.trust_catch_up(
        plan,
        view.projections,
        view=view,
        graph_revision=view.generation.base_graph_revision,
        graph_delta_digest=_digest("forged-delta"),
        ledger_position=1,
        watermark=_digest("forged-watermark"),
        complete_read_set_digest=_digest("forged-read-set"),
        partition_revision=1,
    )

    with pytest.raises(PolicyMigrationError, match="policy_migration_stale_plan"):
        harness.store.policy_migration.prepare_progress(
            plan,
            catch_up=(forged,),
        )


def test_torn_policy_cutover_is_rejected_without_advancing_writer_epoch(
    tmp_path,
    monkeypatch,
) -> None:
    policy_a = _policy()
    policy_b = _rank_policy(20, "policy-b")
    harness = _harness(tmp_path, policy_a)
    plan = harness.store.plan_trust_policy_migration(
        policy_a,
        policy_b,
        arbitration_as_of=T0 + timedelta(hours=1),
        writer_binding=harness.binding,
    )
    result = harness.store.policy_migration.trust_result(
        plan,
        plan.slot_plans[0],
        policy_b,
        complete_read_set_digest=_digest("torn-read-set"),
    )
    original = harness.plane.conditionally_write_records

    def torn(records, *, preconditions=(), authorization=None):
        if any(
            record.source_kind == "semantic_ingestion_projection_publication"
            for record in records
        ):
            records = tuple(
                record
                for record in records
                if record.content.get("projection_authority_kind") != "generation"
            )
        return original(
            records,
            preconditions=preconditions,
            authorization=authorization,
        )

    monkeypatch.setattr(harness.plane, "conditionally_write_records", torn)
    before = tuple(harness.plane.list_records())

    with pytest.raises(
        SemanticWriterAdmissionError,
        match="policy writer transition is invalid",
    ):
        harness.store.cutover_trust_policy(
            plan,
            policy_b,
            (result,),
            writer_binding=harness.binding,
            final_catch_up_watermark=plan.base_catch_up_watermark,
            expected_partition_revision=0,
            complete_read_set_digest=_digest("torn-read-set"),
        )

    after = tuple(harness.plane.list_records())
    assert len(after) > len(before)
    assert not any(
        record.source_kind == "semantic_projection_trust_migration_cutover"
        for record in after
    )
    assert harness.store._writers.current().writer_epoch == 1
