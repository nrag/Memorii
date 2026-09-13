from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest
from memorii.core.memory_evolution.atomic_store import PreplanningStoreError, SemanticIngestionAtomicStore
from memorii.core.memory_evolution.capability_monitoring import (
    CAPABILITY_MONITOR_SEQUENTIAL_IMPLEMENTATION_FINGERPRINT,
    CapabilityEvidenceWindow,
    CapabilityMonitor,
    CapabilityMonitoringPolicy,
    MonitoringMetricGate,
    MonitoringObservation,
    SequentialTestManifest,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    JsonlMemoryPlaneStore,
    MemoryPlaneRevisionConflictError,
    RecordDigestPrecondition,
    record_digest,
)
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.semantic_ingestion.bootstrap_graph_host import BootstrapGraphHostBundleBuilder
from memorii.core.semantic_ingestion.contracts import (
    OperationCapabilityExecutionBinding,
    ProviderEntityObject,
    ProviderFact,
    ProviderMention,
    ProviderSemanticProposal,
)
from tests.fixtures.semantic_ingestion.bootstrap_graph_v3_fixture import (
    DeterministicBootstrapGraphAuthorityProviderV3,
)
from tests.unit.core.semantic_ingestion.bootstrap_graph_production_roots_support import (
    provider_service,
)
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
    TEST_NOW,
    DeterministicTestHostBootstrapMaterialVerifier,
    _built_in_local_capability,
    _host_ingress,
    _v3_normalization_host_builder,
)


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)


def _monitor(memory_plane: MemoryPlaneService | None = None, *, activate_writer: bool = False):
    clock = _Clock()
    memory_plane = memory_plane or MemoryPlaneService()
    migration = None
    if activate_writer:
        from test_semantic_writer_migration import _certified_activation

        migration = _certified_activation(memory_plane)
    writers = SemanticWriterAdmissionStore(
        memory_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: clock.now,
    )
    writers.create_initial_evidence_only(
        admission_id="monitor-test",
        writer_implementation_fingerprint="monitor-test",
        graph_schema_fingerprint="monitor-test",
    )
    if migration is not None:
        plan, checkpoint, certificate, activation, targets = migration
        writers.transition(
            expected=writers.commit_binding(writers.current()),
            admission_id="monitor-active",
            runtime_mode="verified_semantic",
            writer_implementation_fingerprint="monitor-active",
            graph_schema_fingerprint="monitor-active",
            migration_activation=activation,
            migration_plan=plan,
            migration_certificate=certificate,
            migration_checkpoint=checkpoint,
            target_records=targets,
        )
    fingerprint = "a" * 64
    implementation = CAPABILITY_MONITOR_SEQUENTIAL_IMPLEMENTATION_FINGERPRINT
    manifest = SequentialTestManifest.create(
        method="time_uniform_confidence_sequence",
        bounded_value_lower="0",
        bounded_value_upper="1",
        spending_rule_id="inverse_quadratic_union_bound_v1",
        implementation_fingerprint=implementation,
    )
    gate = MonitoringMetricGate.create(
        metric_id="error",
        direction="upper",
        warning_threshold="0.4",
        breach_threshold="0.8",
        minimum_independent_clusters=20,
        maximum_label_delay=timedelta(days=1),
        alpha_budget="0.1",
    )
    policy = CapabilityMonitoringPolicy.create(
        capability_fingerprint=fingerprint,
        monitoring_policy_revision="1",
        maximum_independent_label_age=timedelta(days=1),
        maximum_canary_success_age=timedelta(days=1),
        minimum_labeled_clusters_per_window=1,
        label_window=timedelta(days=1),
        paused_traffic_grace_period=timedelta(hours=1),
        label_pipeline_outage_grace_period=timedelta(hours=1),
        stale_evidence_action="evidence_only",
        metric_gates=(gate,),
        family_wise_alpha_budget="0.1",
        sequential_test_manifest=manifest,
        breach_action="evidence_only",
    )
    monitor = CapabilityMonitor(writers=writers, now=lambda: clock.now, policies=(policy,))
    monitor.initialize_active_status(capability_fingerprint=fingerprint, evidence_freshness_digest="c" * 64)
    return clock, writers, monitor, policy, implementation


def _window(
    clock,
    policy,
    implementation,
    *,
    value="0.1",
    labels_at=None,
    canary_at=None,
    traffic="active",
    outage="healthy",
    state_changed_at=None,
):
    return CapabilityEvidenceWindow.create(
        capability_fingerprint=policy.capability_fingerprint,
        monitoring_policy_digest=policy.policy_digest,
        sequential_implementation_fingerprint=implementation,
        observations=tuple(
            MonitoringObservation(
                event_id=f"event-{index}",
                metric_id="error",
                cluster_id=f"source-template-{index}",
                observed_at=clock.now,
                value=value,
            )
            for index in range(100)
        ),
        latest_independent_label_at=clock.now if labels_at is None else labels_at,
        latest_canary_success_at=clock.now if canary_at is None else canary_at,
        traffic_state=traffic,
        traffic_state_changed_at=clock.now if state_changed_at is None else state_changed_at,
        label_pipeline_state=outage,
        label_pipeline_state_changed_at=clock.now if state_changed_at is None else state_changed_at,
    )


def test_warning_retains_status_but_breach_atomically_fences_writer() -> None:
    clock, writers, monitor, policy, implementation = _monitor()
    warning = monitor.tick(evidence=_window(clock, policy, implementation, value="0.5"))
    assert warning.decision.action == "remain_active"
    before = writers.commit_binding(writers.current())
    breached = monitor.tick(evidence=_window(clock, policy, implementation, value="0.9"))
    assert breached.status.status == "evidence_only"
    assert breached.writer_binding is not None
    assert breached.writer_binding.expected_writer_epoch == before.expected_writer_epoch + 1


def test_breach_changes_verified_writer_to_evidence_only() -> None:
    clock, writers, monitor, policy, implementation = _monitor(activate_writer=True)
    assert writers.current().active_runtime_mode == "verified_semantic"
    result = monitor.tick(evidence=_window(clock, policy, implementation, value="0.9"))
    assert result.writer_binding is not None
    assert result.writer_binding.runtime_mode == "evidence_only"
    assert writers.current().active_runtime_mode == "evidence_only"


def test_stale_labels_demote_even_with_healthy_canary_and_never_reactivate() -> None:
    clock, _, monitor, policy, implementation = _monitor()
    stale = clock.now - timedelta(days=1)
    first = monitor.tick(evidence=_window(clock, policy, implementation, labels_at=stale))
    assert first.decision.action == "evidence_only"
    clock.now += timedelta(minutes=1)
    fresh = monitor.tick(evidence=_window(clock, policy, implementation))
    assert fresh.freshness.freshness == "fresh"
    assert fresh.status.status == "evidence_only"
    assert fresh.writer_binding is None


@pytest.mark.parametrize("traffic,outage", [("paused", "healthy"), ("active", "outage")])
def test_pause_and_outage_expire_at_boundary(traffic: str, outage: str) -> None:
    clock, _, monitor, policy, implementation = _monitor()
    clock.now += timedelta(hours=1)
    result = monitor.tick(
        evidence=_window(
            clock,
            policy,
            implementation,
            traffic=traffic,
            outage=outage,
            state_changed_at=clock.now - timedelta(hours=1),
        )
    )
    assert result.decision.action == "evidence_only"


def test_policy_rejects_alpha_overflow_and_evidence_rejects_cross_metric_cluster() -> None:
    clock, _, _, policy, implementation = _monitor()
    gate = MonitoringMetricGate.create(
        metric_id="other",
        direction="upper",
        warning_threshold="0.4",
        breach_threshold="0.8",
        minimum_independent_clusters=20,
        maximum_label_delay=timedelta(days=1),
        alpha_budget="0.1",
    )
    with pytest.raises(ValueError, match="capability monitoring policy"):
        CapabilityMonitoringPolicy.create(
            capability_fingerprint=policy.capability_fingerprint,
            monitoring_policy_revision=policy.monitoring_policy_revision,
            maximum_independent_label_age=policy.maximum_independent_label_age,
            maximum_canary_success_age=policy.maximum_canary_success_age,
            minimum_labeled_clusters_per_window=policy.minimum_labeled_clusters_per_window,
            label_window=policy.label_window,
            paused_traffic_grace_period=policy.paused_traffic_grace_period,
            label_pipeline_outage_grace_period=policy.label_pipeline_outage_grace_period,
            stale_evidence_action="evidence_only",
            metric_gates=(policy.metric_gates[0], gate),
            family_wise_alpha_budget="0.1",
            sequential_test_manifest=policy.sequential_test_manifest,
            breach_action="evidence_only",
        )
    with pytest.raises(ValueError, match="duplicate or cross-assigned"):
        CapabilityEvidenceWindow.create(
            capability_fingerprint=policy.capability_fingerprint,
            monitoring_policy_digest=policy.policy_digest,
            sequential_implementation_fingerprint=implementation,
            observations=(
                MonitoringObservation(
                    event_id="one", metric_id="error", cluster_id="same", observed_at=clock.now, value="0.1"
                ),
                MonitoringObservation(
                    event_id="two", metric_id="other", cluster_id="same", observed_at=clock.now, value="0.1"
                ),
            ),
            latest_independent_label_at=clock.now,
            latest_canary_success_at=clock.now,
            traffic_state="active",
            traffic_state_changed_at=clock.now,
            label_pipeline_state="healthy",
            label_pipeline_state_changed_at=clock.now,
        )


def test_provider_monitor_tick_reaches_shared_writer_authority() -> None:
    fingerprint = "d" * 64
    implementation = CAPABILITY_MONITOR_SEQUENTIAL_IMPLEMENTATION_FINGERPRINT
    manifest = SequentialTestManifest.create(
        method="time_uniform_confidence_sequence",
        bounded_value_lower="0",
        bounded_value_upper="1",
        spending_rule_id="inverse_quadratic_union_bound_v1",
        implementation_fingerprint=implementation,
    )
    gate = MonitoringMetricGate.create(
        metric_id="error",
        direction="upper",
        warning_threshold="0.4",
        breach_threshold="0.8",
        minimum_independent_clusters=20,
        maximum_label_delay=timedelta(days=1),
        alpha_budget="0.1",
    )
    policy = CapabilityMonitoringPolicy.create(
        capability_fingerprint=fingerprint,
        monitoring_policy_revision="1",
        maximum_independent_label_age=timedelta(days=1),
        maximum_canary_success_age=timedelta(days=1),
        minimum_labeled_clusters_per_window=1,
        label_window=timedelta(days=1),
        paused_traffic_grace_period=timedelta(hours=1),
        label_pipeline_outage_grace_period=timedelta(hours=1),
        stale_evidence_action="evidence_only",
        metric_gates=(gate,),
        family_wise_alpha_budget="0.1",
        sequential_test_manifest=manifest,
        breach_action="evidence_only",
    )
    service = ProviderMemoryService(capability_monitoring_policies=(policy,))
    now = service._clock.now_utc()
    service.initialize_capability_monitor_status(capability_fingerprint=fingerprint, evidence_freshness_digest="f" * 64)
    result = service.run_capability_monitor_tick(
        evidence=_window(
            type("Clock", (), {"now": now})(),
            policy,
            implementation,
            value="0.9",
        ),
    )
    assert result.status.status == "evidence_only"
    assert service._semantic_writer_admission.current().writer_epoch == 2


def test_group_commit_status_read_set_is_exact_and_stale_after_demotion() -> None:
    clock, writers, monitor, policy, implementation = _monitor()
    store = SemanticIngestionAtomicStore(writers._memory_plane, writers, now_provider=lambda: clock.now)
    status_record = writers._memory_plane.get_record(
        "semantic_ingestion:capability-status:" + policy.capability_fingerprint
    )
    assert status_record is not None
    binding = SimpleNamespace(
        operation_id="operation",
        capability_fingerprint=policy.capability_fingerprint,
        capability_status_revision="1",
        capability_status_record_digest=record_digest(status_record),
        monitoring_policy_digest=policy.policy_digest,
        evidence_freshness_digest="c" * 64,
    )
    request = SimpleNamespace(
        operation_ids=("operation",),
        pre_execution_manifest_identity=SimpleNamespace(core=SimpleNamespace(capability_bindings=(binding,))),
    )

    preconditions = store._capability_status_preconditions_for_group_commit(request)
    assert preconditions == (
        RecordDigestPrecondition(memory_id=status_record.memory_id, expected_digest=record_digest(status_record)),
    )
    monitor.tick(evidence=_window(clock, policy, implementation, value="0.9"))
    with pytest.raises(PreplanningStoreError, match="capability status binding is stale"):
        store._capability_status_preconditions_for_group_commit(request)


def test_time_uniform_bounds_match_independent_formula() -> None:
    _, _, monitor, policy, implementation = _monitor()
    result = monitor.tick(evidence=_window(_Clock(), policy, implementation, value="0.1"))
    metric = result.decision.metric_decisions[0]
    with localcontext() as context:
        context.prec = 50
        count = Decimal(100)
        allocated = Decimal("0.1") / (count * (count + 1))
        radius = ((Decimal(2) / allocated).ln() / (Decimal(2) * count)).sqrt()
        expected_lower = max(Decimal(0), Decimal("0.1") - radius)
        expected_upper = min(Decimal(1), Decimal("0.1") + radius)
    assert Decimal(metric.estimate or "NaN") == Decimal("0.1")
    assert Decimal(metric.lower_bound or "NaN") == expected_lower
    assert Decimal(metric.upper_bound or "NaN") == expected_upper


def test_status_and_no_reactivation_survive_restart(tmp_path) -> None:
    path = tmp_path / "monitor-store"
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    clock, _, monitor, policy, implementation = _monitor(plane)
    demoted = monitor.tick(evidence=_window(clock, policy, implementation, value="0.9"))
    assert demoted.status.status == "evidence_only"

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: clock.now,
    )
    reopened_monitor = CapabilityMonitor(writers=reopened_writers, now=lambda: clock.now, policies=(policy,))
    clock.now += timedelta(minutes=1)
    fresh = reopened_monitor.tick(evidence=_window(clock, policy, implementation, value="0.1"))
    assert fresh.freshness.freshness == "fresh"
    assert fresh.status.status == "evidence_only"
    assert reopened_writers.current().writer_epoch == 2


def test_status_cas_loss_fails_without_partial_publication(monkeypatch) -> None:
    clock, writers, monitor, policy, implementation = _monitor()
    plane = writers._memory_plane
    original = plane.conditionally_write_records

    def lose_monitor_cas(records, **kwargs):
        if any(record.source_kind == "semantic_ingestion_capability_monitor_decision" for record in records):
            raise MemoryPlaneRevisionConflictError("injected monitor conflict")
        return original(records, **kwargs)

    monkeypatch.setattr(plane, "conditionally_write_records", lose_monitor_cas)
    with pytest.raises(ValueError, match="requires reevaluation"):
        monitor.tick(evidence=_window(clock, policy, implementation, value="0.9"))
    status = plane.get_record("semantic_ingestion:capability-status:" + policy.capability_fingerprint)
    assert status is not None
    assert status.content["status"]["status"] == "active"
    assert writers.current().writer_epoch == 1
    assert not plane.list_records(source_kind="semantic_ingestion_capability_monitor_decision")


def test_real_group_commit_status_precondition_conflicts_with_monitor_demotion(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    fingerprint = "d" * 64
    implementation = CAPABILITY_MONITOR_SEQUENTIAL_IMPLEMENTATION_FINGERPRINT
    manifest = SequentialTestManifest.create(
        method="time_uniform_confidence_sequence",
        bounded_value_lower="0",
        bounded_value_upper="1",
        spending_rule_id="inverse_quadratic_union_bound_v1",
        implementation_fingerprint=implementation,
    )
    gate = MonitoringMetricGate.create(
        metric_id="error",
        direction="upper",
        warning_threshold="0.4",
        breach_threshold="0.8",
        minimum_independent_clusters=20,
        maximum_label_delay=timedelta(days=1),
        alpha_budget="0.1",
    )
    policy = CapabilityMonitoringPolicy.create(
        capability_fingerprint=fingerprint,
        monitoring_policy_revision="1",
        maximum_independent_label_age=timedelta(days=1),
        maximum_canary_success_age=timedelta(days=1),
        minimum_labeled_clusters_per_window=1,
        label_window=timedelta(days=1),
        paused_traffic_grace_period=timedelta(hours=1),
        label_pipeline_outage_grace_period=timedelta(hours=1),
        stale_evidence_action="evidence_only",
        metric_gates=(gate,),
        family_wise_alpha_budget="0.1",
        sequential_test_manifest=manifest,
        breach_action="evidence_only",
    )
    proposal = ProviderSemanticProposal(
        mentions=(
            ProviderMention(
                local_id="atlas",
                mention_quote="Atlas",
                mention_context_quote="Atlas owner is Bob.",
            ),
            ProviderMention(
                local_id="bob",
                mention_quote="Bob",
                mention_context_quote="Atlas owner is Bob.",
            ),
        ),
        facts=(
            ProviderFact(
                local_id="owner",
                predicate_id="owner_is",
                subject_entity_ref="atlas",
                object=ProviderEntityObject(entity_ref="bob"),
                assertion_quote="Atlas owner is Bob.",
                predicate_anchor_quote="owner",
                polarity="positive",
                commitment="asserted",
            ),
        ),
        abstained=False,
    )
    normalization, _ = _v3_normalization_host_builder(proposal=proposal)
    status_coordinates: dict[str, object] = {}

    def build_bindings(source, operation_inputs):
        status_record = status_coordinates["record"]
        status = status_coordinates["status"]
        routes = {route.segment_id: route.route_digest for route in source.segment_language_routes.routes}
        return tuple(
            OperationCapabilityExecutionBinding.create(
                operation_id=item.operation_id,
                source_dependency_group_id=item.dependency_group.group_id,
                segment_id=item.operation_subject.segment_id,
                segment_language_route_digest=routes[item.operation_subject.segment_id],
                proposal_capability_fingerprint="1" * 64,
                capability_fingerprint=fingerprint,
                capability_selection_digest="2" * 64,
                capability_registry_snapshot_digest="3" * 64,
                capability_status_revision=str(status.status_revision),
                capability_status_record_digest=record_digest(status_record),
                monitoring_policy_digest=policy.policy_digest,
                evidence_freshness_digest=status.evidence_freshness_digest,
                nli_mode="disabled",
                verifier_manifest_digest=None,
                temporal_policy_snapshot_digest="4" * 64,
                trust_policy_fingerprint="5" * 64,
                trust_policy_snapshot_digest="6" * 64,
                arbitration_as_of=TEST_NOW,
            )
            for item in operation_inputs
        )

    authority = DeterministicBootstrapGraphAuthorityProviderV3(
        successful_calls=[],
        capability_bindings_factory=build_bindings,
    )
    store_path = tmp_path / "monitor-group-race"
    service = provider_service(
        memory_plane=MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path)),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=normalization,
        bootstrap_graph_host_bundle_builder=BootstrapGraphHostBundleBuilder(authority_provider=authority),
        capability_monitoring_policies=(policy,),
    )
    status = service.initialize_capability_monitor_status(
        capability_fingerprint=fingerprint,
        evidence_freshness_digest="f" * 64,
    )
    status_record = service._memory_plane.get_record("semantic_ingestion:capability-status:" + fingerprint)
    assert status_record is not None
    status_coordinates.update(record=status_record, status=status)

    observed_status_precondition = False
    demoted = False
    original = service._memory_plane.conditionally_write_records

    def interleave_demotion(records, *, preconditions, authorization, **kwargs):
        nonlocal observed_status_precondition, demoted
        is_group_commit = any(
            record.source_kind == "semantic_ingestion_bootstrap_graph_v3_group_commit_primary" for record in records
        )
        if is_group_commit and not demoted:
            observed_status_precondition = (
                RecordDigestPrecondition(
                    memory_id=status_record.memory_id,
                    expected_digest=record_digest(status_record),
                )
                in preconditions
            )
            demoted = True
            service.run_capability_monitor_tick(
                evidence=_window(
                    type("Clock", (), {"now": TEST_NOW})(),
                    policy,
                    implementation,
                    value="0.9",
                )
            )
        return original(
            records,
            preconditions=preconditions,
            authorization=authorization,
            **kwargs,
        )

    monkeypatch.setattr(
        service._memory_plane,
        "conditionally_write_records",
        interleave_demotion,
    )
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="monitor-group-cas-race",
        task_id="task:monitor",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )

    assert observed_status_precondition
    assert demoted
    assert result.blocked_reasons["semantic_ingestion"] == "graph_transaction_authority_unavailable"
    assert service._semantic_writer_admission.current().active_runtime_mode == "evidence_only"
    assert not service._memory_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    )
    reopened = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path))
    persisted_status = reopened.get_record(status_record.memory_id)
    assert persisted_status is not None
    assert persisted_status.content["status"]["status"] == "evidence_only"
    assert not reopened.list_records(source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary")
