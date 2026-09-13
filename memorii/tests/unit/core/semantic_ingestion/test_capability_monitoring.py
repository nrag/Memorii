import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
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
from memorii.core.memory_evolution.deployment_authorization import (
    DeploymentAuthorizationArtifactVerifier,
    DeploymentAuthorizationIssuer,
    InMemoryDeploymentAuthorizationRepository,
    IssuerAuthority,
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
from memorii.core.provider.factory import build_provider_memory_service_from_env
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.semantic_ingestion.contracts import (
    ProviderEntityObject,
    ProviderFact,
    ProviderMention,
    ProviderSemanticProposal,
    contract_digest,
)
from memorii.core.semantic_ingestion.production_authority import (
    build_verified_capability_monitoring_authority,
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


class _TestDeploymentSigner:
    def sign(self, preimage: bytes) -> str:
        return "signature:" + preimage.hex()

    def verify(
        self, *, signing_key_reference: str, preimage: bytes, signature: str
    ) -> bool:
        return signing_key_reference == "monitor-key" and signature == self.sign(preimage)


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
    traffic_state_changed_at=None,
    pipeline_state_changed_at=None,
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
        traffic_state_changed_at=(
            clock.now
            if traffic_state_changed_at is None and state_changed_at is None
            else traffic_state_changed_at or state_changed_at
        ),
        label_pipeline_state=outage,
        label_pipeline_state_changed_at=(
            clock.now
            if pipeline_state_changed_at is None and state_changed_at is None
            else pipeline_state_changed_at or state_changed_at
        ),
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


def test_repeated_outcome_is_idempotent_but_deadline_crossing_is_re_evaluated() -> None:
    clock, writers, monitor, policy, implementation = _monitor()
    evidence = _window(clock, policy, implementation, value="0.1")
    first = monitor.tick(evidence=evidence)
    first_revision, first_records = writers._memory_plane.read_snapshot()
    first_record_digests = tuple(record_digest(record) for record in first_records)
    first_writer_epoch = writers.current().writer_epoch
    clock.now += timedelta(seconds=1)
    retry = monitor.tick(evidence=evidence)
    assert retry.decision == first.decision
    assert retry.freshness == first.freshness
    retry_revision, retry_records = writers._memory_plane.read_snapshot()
    assert retry_revision == first_revision
    assert tuple(record_digest(record) for record in retry_records) == first_record_digests
    assert writers.current().writer_epoch == first_writer_epoch

    clock.now += timedelta(days=1)
    expired = monitor.tick(evidence=evidence)
    assert expired.freshness.freshness == "stale"
    assert expired.status.status == "evidence_only"


def test_future_authority_time_and_overlapping_expired_pause_fail_closed() -> None:
    clock, _, monitor, policy, implementation = _monitor()
    future = monitor.tick(
        evidence=_window(
            clock,
            policy,
            implementation,
            labels_at=clock.now + timedelta(seconds=1),
        )
    )
    assert future.freshness.freshness_reason == "future_authority_timestamp"
    assert future.status.status == "evidence_only"

    clock, _, monitor, policy, implementation = _monitor()
    overlap = monitor.tick(
        evidence=_window(
            clock,
            policy,
            implementation,
            traffic="paused",
            outage="outage",
            traffic_state_changed_at=clock.now - timedelta(hours=1),
            pipeline_state_changed_at=clock.now - timedelta(minutes=30),
        )
    )
    assert overlap.freshness.freshness_reason == "traffic_pause_expired"
    assert overlap.status.status == "evidence_only"


@pytest.mark.parametrize("traffic,outage", [("paused", "healthy"), ("active", "outage")])
@pytest.mark.parametrize(
    "elapsed,expected",
    [
        (timedelta(hours=1) - timedelta(microseconds=1), "remain_active"),
        (timedelta(hours=1), "evidence_only"),
        (timedelta(hours=1) + timedelta(microseconds=1), "evidence_only"),
    ],
)
def test_pause_and_outage_deadline_boundaries(
    traffic: str, outage: str, elapsed: timedelta, expected: str
) -> None:
    clock, _, monitor, policy, implementation = _monitor()
    result = monitor.tick(
        evidence=_window(
            clock,
            policy,
            implementation,
            traffic=traffic,
            outage=outage,
            state_changed_at=clock.now - elapsed,
        )
    )
    assert result.decision.action == expected


@pytest.mark.parametrize("authority", ["label", "canary"])
@pytest.mark.parametrize(
    "elapsed,expected",
    [
        (timedelta(days=1) - timedelta(microseconds=1), "remain_active"),
        (timedelta(days=1), "evidence_only"),
        (timedelta(days=1) + timedelta(microseconds=1), "evidence_only"),
    ],
)
def test_label_and_canary_deadline_boundaries(
    authority: str, elapsed: timedelta, expected: str
) -> None:
    clock, _, monitor, policy, implementation = _monitor()
    kwargs = {"labels_at" if authority == "label" else "canary_at": clock.now - elapsed}
    evidence = _window(clock, policy, implementation, **kwargs)
    if authority == "label":
        label_time = clock.now - elapsed
        evidence = CapabilityEvidenceWindow.create(
            **evidence.model_dump(
                mode="python",
                exclude={"evidence_window_digest", "observations"},
            ),
            observations=tuple(
                item.model_copy(update={"observed_at": label_time})
                for item in evidence.observations
            ),
        )
    result = monitor.tick(evidence=evidence)
    assert result.decision.action == expected


def test_zero_traffic_unknown_metric_and_implementation_mismatch_fail_closed() -> None:
    clock, _, monitor, policy, implementation = _monitor()
    empty = _window(clock, policy, implementation).model_copy(update={"observations": ()})
    empty = CapabilityEvidenceWindow.create(
        **empty.model_dump(mode="python", exclude={"evidence_window_digest"})
    )
    assert monitor.tick(evidence=empty).decision.reason_codes == (
        "insufficient_metric_evidence",
        "stale_evidence",
    )

    clock, _, monitor, policy, implementation = _monitor()
    mismatched = _window(clock, policy, implementation).model_copy(
        update={"sequential_implementation_fingerprint": "b" * 64}
    )
    mismatched = CapabilityEvidenceWindow.create(
        capability_fingerprint=mismatched.capability_fingerprint,
        monitoring_policy_digest=mismatched.monitoring_policy_digest,
        sequential_implementation_fingerprint=mismatched.sequential_implementation_fingerprint,
        observations=mismatched.observations,
        latest_independent_label_at=mismatched.latest_independent_label_at,
        latest_canary_success_at=mismatched.latest_canary_success_at,
        traffic_state=mismatched.traffic_state,
        traffic_state_changed_at=mismatched.traffic_state_changed_at,
        label_pipeline_state=mismatched.label_pipeline_state,
        label_pipeline_state_changed_at=mismatched.label_pipeline_state_changed_at,
    )
    assert monitor.tick(evidence=mismatched).decision.reason_codes == (
        "insufficient_metric_evidence",
    )

    clock, _, monitor, policy, implementation = _monitor()
    unknown_observation = MonitoringObservation(
        event_id="unknown-event",
        metric_id="unknown",
        cluster_id="unknown-cluster",
        observed_at=clock.now,
        value="0.1",
    )
    unknown = _window(clock, policy, implementation)
    unknown = CapabilityEvidenceWindow.create(
        **unknown.model_dump(mode="python", exclude={"evidence_window_digest", "observations"}),
        observations=(*unknown.observations, unknown_observation),
    )
    assert monitor.tick(evidence=unknown).decision.reason_codes == ("unknown_metric",)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_observation_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        MonitoringObservation(
            event_id="nonfinite",
            metric_id="error",
            cluster_id="nonfinite",
            observed_at=datetime(2026, 1, 1, tzinfo=UTC),
            value=value,
        )


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
    fingerprint = "1" * 64
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
    service._ensure_writer_admission_record()
    service._capability_monitor.initialize_active_status(
        capability_fingerprint=fingerprint, evidence_freshness_digest="f" * 64
    )
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


def test_public_factory_schedules_windows_from_signed_baseline_authority() -> None:
    clock, _, _, policy, implementation = _monitor()
    initial_evidence = _window(clock, policy, implementation, value="0.1")
    evidence = _window(clock, policy, implementation, value="0.9")

    class EvidenceProvider:
        def load_evidence_windows(self, *, max_items: int):
            return (evidence,)[:max_items]

    signer = _TestDeploymentSigner()
    artifact = DeploymentAuthorizationIssuer(
        authority=IssuerAuthority(
            "monitor-release", "monitor-key", "8" * 64, signer
        ),
        repository=InMemoryDeploymentAuthorizationRepository(),
        now_provider=lambda: clock.now,
    ).prepare_verified(
        target_artifact_digest=contract_digest(
            b"memorii.semantic-ingestion.capability-monitoring-baseline.v1",
            {
                "monitoring_policy_digest": policy.policy_digest,
                "initial_evidence_window_digest": initial_evidence.evidence_window_digest,
            },
        ),
        deployment_manifest_digest="7" * 64,
        capability_fingerprint=policy.capability_fingerprint,
        verified_capability_baseline_approval_release_digest="6" * 64,
        requested_active_epoch=1,
        expires_at=clock.now + timedelta(days=1),
    )
    raw = json.dumps(
        artifact.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    authority = build_verified_capability_monitoring_authority(
        deployment_authorization_bytes=raw,
        deployment_authorization_verifier=DeploymentAuthorizationArtifactVerifier(
            signer
        ),
        policy=policy,
        initial_evidence=initial_evidence,
        evidence_provider=EvidenceProvider(),
        server_time=clock.now,
    )
    assert authority is not None
    service = build_provider_memory_service_from_env(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: clock.now,
        verified_capability_monitoring_authorities=(authority,),
    )

    results = service.process_capability_monitoring(max_items=1)

    assert len(results) == 1
    assert results[0].status.status == "evidence_only"
    assert service._semantic_writer_admission.current().writer_epoch == 2
    assert service._memory_plane.list_records(
        source_kind="semantic_ingestion_capability_initial_freshness"
    )
    assert not service._memory_plane.list_records(source_kind="semantic_ingestion_source")
    assert not service._memory_plane.list_records(
        source_kind="semantic_ingestion_accepted_identity_operation"
    )
    assert not service._memory_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    )


def test_signed_monitoring_authority_rejects_substitution_and_unacceptable_baseline() -> None:
    clock, _, _, policy, implementation = _monitor()
    initial_evidence = _window(clock, policy, implementation, value="0.1")

    class EvidenceProvider:
        def load_evidence_windows(self, *, max_items: int):
            return ()

    signer = _TestDeploymentSigner()
    issuer = DeploymentAuthorizationIssuer(
        authority=IssuerAuthority("monitor-release", "monitor-key", "8" * 64, signer),
        repository=InMemoryDeploymentAuthorizationRepository(),
        now_provider=lambda: clock.now,
    )
    baseline_digest = contract_digest(
        b"memorii.semantic-ingestion.capability-monitoring-baseline.v1",
        {
            "monitoring_policy_digest": policy.policy_digest,
            "initial_evidence_window_digest": initial_evidence.evidence_window_digest,
        },
    )

    def encode(artifact) -> bytes:
        return json.dumps(
            artifact.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")

    valid = issuer.prepare_verified(
        target_artifact_digest=baseline_digest,
        deployment_manifest_digest="7" * 64,
        capability_fingerprint=policy.capability_fingerprint,
        verified_capability_baseline_approval_release_digest="6" * 64,
        requested_active_epoch=1,
        expires_at=clock.now + timedelta(days=2),
    )
    verifier = DeploymentAuthorizationArtifactVerifier(signer)
    arguments = {
        "deployment_authorization_verifier": verifier,
        "policy": policy,
        "initial_evidence": initial_evidence,
        "evidence_provider": EvidenceProvider(),
        "server_time": clock.now,
    }
    invalid_signature = json.loads(encode(valid))
    invalid_signature["signature"] = "forged"
    invalid_signature_raw = json.dumps(
        invalid_signature, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    wrong_target = issuer.prepare_verified(
        target_artifact_digest="0" * 64,
        deployment_manifest_digest="7" * 64,
        capability_fingerprint=policy.capability_fingerprint,
        verified_capability_baseline_approval_release_digest="6" * 64,
        requested_active_epoch=1,
        expires_at=clock.now + timedelta(days=2),
    )
    for raw, server_time in (
        (b"not-json", clock.now),
        (invalid_signature_raw, clock.now),
        (encode(wrong_target), clock.now),
        (encode(valid), clock.now + timedelta(days=2)),
    ):
        assert build_verified_capability_monitoring_authority(
            deployment_authorization_bytes=raw,
            **{**arguments, "server_time": server_time},
        ) is None

    forged_evidence = initial_evidence.model_copy(
        update={"monitoring_policy_digest": "0" * 64}
    )
    assert build_verified_capability_monitoring_authority(
        deployment_authorization_bytes=encode(valid),
        **{**arguments, "initial_evidence": forged_evidence},
    ) is None

    stale_evidence = _window(
        clock,
        policy,
        implementation,
        labels_at=clock.now - timedelta(days=1),
    )
    stale_artifact = issuer.prepare_verified(
        target_artifact_digest=contract_digest(
            b"memorii.semantic-ingestion.capability-monitoring-baseline.v1",
            {
                "monitoring_policy_digest": policy.policy_digest,
                "initial_evidence_window_digest": stale_evidence.evidence_window_digest,
            },
        ),
        deployment_manifest_digest="7" * 64,
        capability_fingerprint=policy.capability_fingerprint,
        verified_capability_baseline_approval_release_digest="6" * 64,
        requested_active_epoch=1,
        expires_at=clock.now + timedelta(days=2),
    )
    stale_authority = build_verified_capability_monitoring_authority(
        deployment_authorization_bytes=encode(stale_artifact),
        **{**arguments, "initial_evidence": stale_evidence},
    )
    assert stale_authority is not None
    plane = MemoryPlaneService()
    with pytest.raises(ValueError, match="initial evidence"):
        build_provider_memory_service_from_env(
            memory_plane=plane,
            now_provider=lambda: clock.now,
            verified_capability_monitoring_authorities=(stale_authority,),
        )
    assert not plane.list_records(source_kind="semantic_ingestion_capability_status")
    assert not plane.list_records(
        source_kind="semantic_ingestion_capability_initial_freshness"
    )


def test_normal_reconciliation_scheduler_expires_monitor_without_ingress() -> None:
    clock, _, _, policy, implementation = _monitor()
    initial_evidence = _window(clock, policy, implementation, value="0.1")

    class EvidenceProvider:
        def load_evidence_windows(self, *, max_items: int):
            return (initial_evidence,)[:max_items]

    signer = _TestDeploymentSigner()
    artifact = DeploymentAuthorizationIssuer(
        authority=IssuerAuthority("monitor-release", "monitor-key", "8" * 64, signer),
        repository=InMemoryDeploymentAuthorizationRepository(),
        now_provider=lambda: clock.now,
    ).prepare_verified(
        target_artifact_digest=contract_digest(
            b"memorii.semantic-ingestion.capability-monitoring-baseline.v1",
            {
                "monitoring_policy_digest": policy.policy_digest,
                "initial_evidence_window_digest": initial_evidence.evidence_window_digest,
            },
        ),
        deployment_manifest_digest="7" * 64,
        capability_fingerprint=policy.capability_fingerprint,
        verified_capability_baseline_approval_release_digest="6" * 64,
        requested_active_epoch=1,
        expires_at=clock.now + timedelta(days=3),
    )
    authority = build_verified_capability_monitoring_authority(
        deployment_authorization_bytes=json.dumps(
            artifact.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii"),
        deployment_authorization_verifier=DeploymentAuthorizationArtifactVerifier(signer),
        policy=policy,
        initial_evidence=initial_evidence,
        evidence_provider=EvidenceProvider(),
        server_time=clock.now,
    )
    assert authority is not None
    plane = MemoryPlaneService()
    service = build_provider_memory_service_from_env(
        memory_plane=plane,
        now_provider=lambda: clock.now,
        verified_capability_monitoring_authorities=(authority,),
    )
    clock.now += timedelta(days=1)

    assert service.reconcile_memory_evolution() == []
    status = plane.list_records(source_kind="semantic_ingestion_capability_status")
    assert status[-1].content["status"]["status"] == "evidence_only"
    assert not plane.list_records(source_kind="semantic_ingestion_source")
    assert not plane.list_records(source_kind="semantic_ingestion_accepted_identity_operation")
    assert not plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    )


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
        ordered_operation_inputs=(
            SimpleNamespace(
                operation_id="operation",
                reduction=SimpleNamespace(
                    native_terminal=SimpleNamespace(status="accepted")
                ),
            ),
        ),
        pre_execution_manifest_identity=SimpleNamespace(core=SimpleNamespace(capability_bindings=(binding,))),
    )

    preconditions = store._capability_status_preconditions_for_group_commit(
        request  # pyright: ignore[reportArgumentType] - focused internal fixture
    )
    assert preconditions == (
        RecordDigestPrecondition(memory_id=status_record.memory_id, expected_digest=record_digest(status_record)),
    )
    monitor.tick(evidence=_window(clock, policy, implementation, value="0.9"))
    with pytest.raises(PreplanningStoreError, match="capability status binding is stale"):
        store._capability_status_preconditions_for_group_commit(
            request  # pyright: ignore[reportArgumentType] - focused internal fixture
        )


def test_group_commit_deduplicates_shared_capability_status_coordinates() -> None:
    _, writers, _, policy, _ = _monitor()
    store = SemanticIngestionAtomicStore(writers._memory_plane, writers)
    status_record = writers._memory_plane.get_record(
        "semantic_ingestion:capability-status:" + policy.capability_fingerprint
    )
    assert status_record is not None
    coordinate = {
        "capability_fingerprint": policy.capability_fingerprint,
        "capability_status_revision": "1",
        "capability_status_record_digest": record_digest(status_record),
        "monitoring_policy_digest": policy.policy_digest,
        "evidence_freshness_digest": "c" * 64,
    }
    bindings = tuple(
        SimpleNamespace(operation_id=operation_id, **coordinate)
        for operation_id in ("operation-a", "operation-b")
    )
    request = SimpleNamespace(
        operation_ids=("operation-a", "operation-b"),
        ordered_operation_inputs=tuple(
            SimpleNamespace(
                operation_id=operation_id,
                reduction=SimpleNamespace(
                    native_terminal=SimpleNamespace(status="accepted")
                ),
            )
            for operation_id in ("operation-a", "operation-b")
        ),
        pre_execution_manifest_identity=SimpleNamespace(
            core=SimpleNamespace(capability_bindings=bindings)
        ),
    )
    assert store._capability_status_preconditions_for_group_commit(
        request  # pyright: ignore[reportArgumentType] - focused internal fixture
    ) == (
        RecordDigestPrecondition(
            memory_id=status_record.memory_id,
            expected_digest=record_digest(status_record),
        ),
    )


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


def test_time_uniform_bounds_match_external_frozen_oracle() -> None:
    _, _, monitor, policy, implementation = _monitor()
    metric = monitor.tick(
        evidence=_window(_Clock(), policy, implementation, value="0.1")
    ).decision.metric_decisions[0]
    fixture_root = Path(__file__).parents[3] / "fixtures" / "semantic_ingestion"
    completed = subprocess.run(
        [
            sys.executable,
            str(fixture_root / "capability_monitor_oracle.py"),
            str(fixture_root / "capability_monitor_vector.json"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    independent = json.loads(completed.stdout)
    assert independent == {
        "estimate": metric.estimate,
        "lower_bound": metric.lower_bound,
        "upper_bound": metric.upper_bound,
    }


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
    fingerprint = "38a5be91af79d7e5ba9809bf383c699b6864ee50446239fe56a45e32b84638fe"
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
    store_path = tmp_path / "monitor-group-race"
    service = provider_service(
        memory_plane=MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path)),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=normalization,
        capability_monitoring_policies=(policy,),
    )
    service._ensure_writer_admission_record()
    service._capability_monitor.initialize_active_status(
        capability_fingerprint=fingerprint,
        evidence_freshness_digest="f" * 64,
    )
    status_record = service._memory_plane.get_record("semantic_ingestion:capability-status:" + fingerprint)
    assert status_record is not None
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

    assert observed_status_precondition, result.blocked_reasons
    assert demoted
    assert result.blocked_reasons["semantic_ingestion"] == "graph_transaction_authority_unavailable"
    assert service._semantic_writer_admission.current().active_runtime_mode == "evidence_only"
    assert not service._memory_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    )
    second = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="monitor-after-demotion",
        task_id="task:monitor",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert second.blocked_reasons["semantic_ingestion"] == "graph_transaction_authority_unavailable"
    assert not service._memory_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    )
    reopened = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path))
    persisted_status = reopened.get_record(status_record.memory_id)
    assert persisted_status is not None
    assert persisted_status.content["status"]["status"] == "evidence_only"
    assert not reopened.list_records(source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary")
