import json
import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from hashlib import sha256
from multiprocessing import get_context
from pathlib import Path
from queue import Empty
from threading import Event, RLock, Thread
from types import SimpleNamespace
from typing import cast

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from memorii.core.filesystem_storage.bundle import build_filesystem_provider
from memorii.core.memory_evolution.atomic_store import (
    AtomicGenerationMember,
    PreplanningStoreError,
    SemanticIngestionAtomicStore,
)
from memorii.core.memory_evolution.capability_monitoring import (
    CAPABILITY_MONITOR_SEQUENTIAL_IMPLEMENTATION_FINGERPRINT,
    CapabilityEvidenceFreshness,
    CapabilityEvidenceWindow,
    CapabilityEvidenceWindowProvider,
    CapabilityMonitor,
    CapabilityMonitoringDecision,
    CapabilityMonitoringPolicy,
    CapabilityStatus,
    MonitoringMetricGate,
    MonitoringObservation,
    SequentialTestManifest,
)
from memorii.core.memory_evolution.deployment_authorization import (
    ArtifactDeploymentAuthorizationCurrentTrustVerifier,
    DeploymentAuthorizationArtifact,
    DeploymentAuthorizationArtifactVerifier,
    DeploymentAuthorizationIssuer,
    InMemoryDeploymentAuthorizationRepository,
    InstalledProductionRevocationReader,
    IssuerAuthority,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionError,
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    JsonlMemoryPlaneStore,
    MemoryPlaneRevisionConflictError,
    RecordAbsentPrecondition,
    record_digest,
)
from memorii.core.provider.factory import build_provider_memory_service_from_env
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.semantic_ingestion.contracts import (
    BootstrapGraphNormalizationAuthorityMemberV3,
    ProviderEntityObject,
    ProviderFact,
    ProviderMention,
    ProviderSemanticProposal,
    contract_digest,
    decode_semantic_contract,
    decode_typed_value,
)
from memorii.core.semantic_ingestion.production_authority import (
    VerifiedCapabilityMonitoringAuthority,
    build_verified_capability_monitoring_authority,
    capability_monitoring_authority_checkpoint,
)
from memorii.core.semantic_ingestion.source_normalization_authority import (
    CapabilityRegistryEntry,
    CapabilityRegistrySnapshot,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility
from memorii.integrations.hermes_provider import HermesMemoryProvider
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


class _UnexpectedEvidenceProviderError(Exception):
    pass


class _NoEvidenceProvider:
    def load_evidence_windows(self, *, max_items: int) -> tuple[CapabilityEvidenceWindow, ...]:
        return ()


class _TestDeploymentSigner:
    def sign(self, preimage: bytes) -> str:
        return "signature:" + preimage.hex()

    def verify(
        self, *, signing_key_reference: str, preimage: bytes, signature: str
    ) -> bool:
        return signing_key_reference == "monitor-key" and signature == self.sign(preimage)


class _Ed25519DeploymentSigner:
    def __init__(self, key: Ed25519PrivateKey) -> None:
        self._key = key

    def sign(self, preimage: bytes) -> str:
        return self._key.sign(preimage).hex()


def _publish_revocation_in_child(
    root: str, release: str, receipt: str, checkpoint: str, queue: object,
) -> None:
    reader = InstalledProductionRevocationReader().from_fixed_configuration(
        {"reader_root": root}
    )
    reader.publish_revocation_mapping(
        prior_approval_release_digest=release,
        receipt_digest=receipt,
        checkpoint_digest=checkpoint,
    )
    queue.put("published")  # type: ignore[union-attr]


class _CurrentDeploymentTrust:
    def __init__(self, *, current: bool = True, sequence: list[bool] | None = None) -> None:
        self.current = current
        self.sequence = sequence or []
        self._lock = RLock()

    def is_current(self, *, artifact, server_time: datetime) -> bool:
        with self._lock:
            if self.sequence:
                return self.sequence.pop(0) and artifact.expires_at > server_time
            return self.current and artifact.expires_at > server_time

    @contextmanager
    def current_use(self, *, artifact, server_time: datetime) -> Iterator[bool]:
        with self._lock:
            yield self.is_current(artifact=artifact, server_time=server_time)

    def revoke(self) -> None:
        with self._lock:
            self.current = False


def _current_trust_verifier(signer: _TestDeploymentSigner, trust: _CurrentDeploymentTrust | None = None):
    return ArtifactDeploymentAuthorizationCurrentTrustVerifier(
        artifact_verifier=DeploymentAuthorizationArtifactVerifier(signer),
        current_trust_check=trust or _CurrentDeploymentTrust(),
    )


def _installed_monitoring_configuration(
    tmp_path: Path, *, clock: _Clock, expires_at: datetime | None = None,
) -> tuple[dict[str, object], CapabilityMonitoringPolicy]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    _, _, _, policy, implementation = _monitor()
    initial = _window(clock, policy, implementation, value="0.1")
    key = Ed25519PrivateKey.generate()
    signer = _Ed25519DeploymentSigner(key)
    artifact = DeploymentAuthorizationIssuer(
        authority=IssuerAuthority("monitor-release", "installed-key", "8" * 64, signer),
        repository=InMemoryDeploymentAuthorizationRepository(), now_provider=lambda: clock.now,
    ).prepare_verified(
        target_artifact_digest=contract_digest(
            b"memorii.semantic-ingestion.capability-monitoring-baseline.v1",
            {"monitoring_policy_digest": policy.policy_digest,
             "initial_evidence_window_digest": initial.evidence_window_digest},
        ), deployment_manifest_digest="7" * 64,
        capability_fingerprint=policy.capability_fingerprint,
        verified_capability_baseline_approval_release_digest="6" * 64,
        requested_active_epoch=1, expires_at=expires_at or clock.now + timedelta(days=1),
    )
    paths = {
        "deployment_authorization_path": tmp_path / "authorization.json",
        "monitoring_policy_path": tmp_path / "policy.json",
        "initial_evidence_path": tmp_path / "initial.json",
        "ongoing_evidence_path": tmp_path / "ongoing.json",
    }
    paths["deployment_authorization_path"].write_bytes(json.dumps(
        artifact.model_dump(mode="json"), sort_keys=True, separators=(",", ":"),
    ).encode("ascii"))
    paths["monitoring_policy_path"].write_text(policy.model_dump_json())
    paths["initial_evidence_path"].write_text(initial.model_dump_json())
    paths["ongoing_evidence_path"].write_text(json.dumps([initial.model_dump(mode="json")]))
    revocations = tmp_path / "revocations"
    revocations.mkdir()
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return ({
        "public_keys": {"installed-key": public.hex()},
        **{name: str(path) for name, path in paths.items()},
        "revocation_reader_root": str(revocations),
    }, policy)


def _monitor(
    memory_plane: MemoryPlaneService | None = None,
    *,
    activate_writer: bool = False,
    fingerprint: str = "a" * 64,
):
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
    monitor.initialize_active_from_verified_evidence(
        evidence=_window(clock, policy, implementation)
    )
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



def _signed_monitoring_authority(
    *,
    clock: _Clock,
    policy: CapabilityMonitoringPolicy,
    implementation: str,
    evidence_provider: CapabilityEvidenceWindowProvider,
    signer: _TestDeploymentSigner,
    trust: _CurrentDeploymentTrust | None = None,
    expires_at: datetime | None = None,
):
    initial_evidence = _window(clock, policy, implementation, value="0.1")
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
        expires_at=expires_at or clock.now + timedelta(days=1),
    )
    raw = json.dumps(
        artifact.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    authority = build_verified_capability_monitoring_authority(
        deployment_authorization_bytes=raw,
        deployment_authorization_verifier=DeploymentAuthorizationArtifactVerifier(signer),
        deployment_authorization_current_trust_verifier=_current_trust_verifier(
            signer, trust
        ),
        policy=policy,
        initial_evidence=initial_evidence,
        evidence_provider=evidence_provider,
        server_time=clock.now,
    )
    assert authority is not None
    return authority


def _monitoring_graph_proposal() -> ProviderSemanticProposal:
    assertion = "Atlas owner is Bob."
    return ProviderSemanticProposal(
        mentions=(
            ProviderMention(
                local_id="atlas", mention_quote="Atlas", mention_context_quote=assertion,
            ),
            ProviderMention(
                local_id="bob", mention_quote="Bob", mention_context_quote=assertion,
            ),
        ),
        facts=(
            ProviderFact(
                local_id="owner", predicate_id="owner_is", subject_entity_ref="atlas",
                object=ProviderEntityObject(entity_ref="bob"), assertion_quote=assertion,
                predicate_anchor_quote="owner", polarity="positive", commitment="asserted",
            ),
        ),
        abstained=False,
    )


def _service_for_joined_monitoring_ingress(
    *,
    plane: MemoryPlaneService,
    clock: _Clock,
    authority: VerifiedCapabilityMonitoringAuthority,
) -> ProviderMemoryService:
    normalization, _ = _v3_normalization_host_builder(
        proposal=_monitoring_graph_proposal()
    )
    return provider_service(
        memory_plane=plane,
        now_provider=lambda: clock.now,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=normalization,
        verified_capability_monitoring_authorities=(authority,),
    )


def _joined_monitoring_sync(service: ProviderMemoryService, *, operation_id: str):
    return service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id=operation_id,
        task_id="task:joined-monitoring",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
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


@pytest.mark.parametrize("traffic,outage", [("paused", "healthy"), ("active", "outage")])
def test_missing_window_preserves_pause_and_outage_grace_deadline(
    traffic: str, outage: str
) -> None:
    """A missing provider window cannot restart the recorded grace clock."""
    clock, _, monitor, policy, implementation = _monitor()
    initial = monitor.tick(
        evidence=_window(
            clock,
            policy,
            implementation,
            traffic=traffic,
            outage=outage,
            state_changed_at=clock.now,
        )
    )
    assert initial.status.status == "active"
    clock.now += timedelta(hours=1) - timedelta(microseconds=1)
    before_deadline = monitor.tick_missing_window(
        capability_fingerprint=policy.capability_fingerprint
    )
    assert before_deadline is None
    clock.now += timedelta(microseconds=1)
    at_deadline = monitor.tick_missing_window(
        capability_fingerprint=policy.capability_fingerprint
    )
    assert at_deadline is not None
    assert at_deadline.decision.evaluation_kind == "missing_window"
    assert at_deadline.status.status == "evidence_only"


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
    if authority == "label":
        evidence = _window(
            clock, policy, implementation, labels_at=clock.now - elapsed
        )
    else:
        evidence = _window(
            clock, policy, implementation, canary_at=clock.now - elapsed
        )
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
    service._capability_monitor.initialize_active_from_verified_evidence(
        evidence=_window(
            type("Clock", (), {"now": now})(), policy, implementation
        )
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


def test_public_factory_schedules_windows_from_signed_baseline_authority(tmp_path: Path) -> None:
    clock, _, _, policy, implementation = _monitor()
    initial_evidence = _window(clock, policy, implementation, value="0.1")
    registry_values = {
        "registry_revision": "monitor-v1",
        "capabilities": (
            CapabilityRegistryEntry(
                capability_id="built-in-local",
                capability_fingerprint=policy.capability_fingerprint,
            ),
        ),
    }
    registry = CapabilityRegistrySnapshot(
        **registry_values,
        snapshot_digest=contract_digest(
            b"memorii.semantic-ingestion.capability-registry-snapshot.v2",
            registry_values,
        ),
    )
    registry_bytes = registry.model_dump_json().encode("utf-8")

    class EvidenceProvider:
        def __init__(self) -> None:
            self.calls = 0

        def load_evidence_windows(self, *, max_items: int):
            self.calls += 1
            return (_window(clock, policy, implementation, value="0.1"),)[:max_items]

    evidence_provider = EvidenceProvider()
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
        deployment_authorization_current_trust_verifier=_current_trust_verifier(signer),
        policy=policy,
        initial_evidence=initial_evidence,
        evidence_provider=evidence_provider,
        server_time=clock.now,
    )
    assert authority is not None
    store_path = tmp_path / "signed-monitor"
    service = build_provider_memory_service_from_env(
        memory_plane=MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path)),
        now_provider=lambda: clock.now,
        verified_capability_monitoring_authorities=(authority,),
    )

    results = service.process_capability_monitoring(max_items=1)

    assert len(results) == 1
    assert results[0].status.status == "active"
    assert evidence_provider.calls == 1
    assert service._semantic_writer_admission.current().writer_epoch == 1
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
    assert registry.model_dump_json().encode("utf-8") == registry_bytes
    assert CapabilityRegistrySnapshot.model_validate_json(registry_bytes) == registry
    restarted_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path))
    restarted = build_provider_memory_service_from_env(
        memory_plane=restarted_plane, now_provider=lambda: clock.now,
        verified_capability_monitoring_authorities=(authority,),
    )
    checkpoint = restarted_plane.list_records(
        source_kind="semantic_ingestion_capability_authorization_checkpoint"
    )
    assert len(checkpoint) == 1
    clock.now += timedelta(days=1)
    expired_results = restarted.process_capability_monitoring(max_items=1)
    assert expired_results[-1].status.status == "evidence_only"
    # The second call produces current healthy evidence, but live expiry
    # validation demotes it before monitoring can accept the window.
    assert evidence_provider.calls == 2
    assert any(
        record.content["decision"]["evaluation_kind"] == "authorization_failure"
        for record in restarted_plane.list_records(
            source_kind="semantic_ingestion_capability_monitor_decision"
        )
    )
    reopened = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path))
    reopened_status = reopened.list_records(
        source_kind="semantic_ingestion_capability_status"
    )
    assert reopened_status[-1].content["status"]["status"] == "evidence_only"
    assert CapabilityRegistrySnapshot.model_validate_json(registry_bytes) == registry


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
        "deployment_authorization_current_trust_verifier": _current_trust_verifier(signer),
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


def test_status_only_active_initialization_is_rejected_by_governed_store() -> None:
    clock, writers, monitor, policy, _ = _monitor()
    fingerprint = "b" * 64
    status_base = {
        "capability_fingerprint": fingerprint,
        "status": "active",
        "status_revision": 1,
        "monitoring_policy_digest": policy.policy_digest,
        "evidence_freshness_digest": "c" * 64,
        "authorization_checkpoint_digest": None,
    }
    status = CapabilityStatus(
        **status_base,
        schema_version=2,
        status_digest=contract_digest(
            b"memorii.semantic-ingestion.capability-status.v2",
            {"schema_version": 2, **status_base},
        ),
    )
    record = CanonicalMemoryRecord(
        memory_id="semantic_ingestion:capability-status:" + fingerprint,
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "capability_status",
            "status": status.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_capability_status",
        timestamp=clock.now,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    authorization = writers._authorize_atomic(
        writers.commit_binding(writers.current()), capability=monitor._write_capability
    )
    with pytest.raises(SemanticWriterAdmissionError):
        writers._memory_plane.conditionally_write_records(
            (record,),
            preconditions=(RecordAbsentPrecondition(memory_id=record.memory_id),),
            authorization=authorization,
        )
    assert not hasattr(monitor, "initialize_active_status")
    assert writers._memory_plane.get_record(record.memory_id) is None


def test_historical_monitor_wires_reject_injected_generation_fields() -> None:
    """Historical digest domains authenticate their exact persisted key sets."""
    clock, _, monitor, policy, implementation = _monitor()
    result = monitor.tick(evidence=_window(clock, policy, implementation))
    v2_status = result.status.model_dump(mode="json")
    v2_decision = result.decision.model_dump(mode="json")
    v2_freshness = result.freshness.model_dump(mode="json")

    for payload, mutation in (
        (v2_status, {"wire_generation": "pre_field_v1"}),
        (v2_decision, {"schema_version": 1}),
        (v2_freshness, {"schema_version": 1}),
    ):
        with pytest.raises(ValueError, match="wire"):
            (
                CapabilityStatus if payload is v2_status else
                CapabilityMonitoringDecision if payload is v2_decision else
                CapabilityEvidenceFreshness
            ).model_validate({**payload, **mutation})

    pre_status = {
        "capability_fingerprint": policy.capability_fingerprint,
        "status": "active",
        "status_revision": 1,
        "monitoring_policy_digest": policy.policy_digest,
        "evidence_freshness_digest": "c" * 64,
    }
    pre_status["status_digest"] = contract_digest(
        b"memorii.semantic-ingestion.capability-status.v1", pre_status
    )
    # This happens to match the extended-V1 key set, but it cannot preserve
    # the authenticated pre-field digest after adding the checkpoint.
    with pytest.raises(ValueError, match="digest mismatch"):
        CapabilityStatus.model_validate(
            {**pre_status, "authorization_checkpoint_digest": "d" * 64}
        )


@pytest.mark.parametrize(
    ("source_kind", "content_key", "forged_field"),
    (
        ("semantic_ingestion_capability_status", "status", "authorization_checkpoint_digest"),
        ("semantic_ingestion_capability_monitor_decision", "decision", "evaluation_kind"),
        ("semantic_ingestion_capability_initial_freshness", "freshness", "traffic_state_changed_at"),
    ),
)
def test_forged_v2_monitor_wire_fields_fail_before_signed_ingress_publication(
    tmp_path: Path, source_kind: str, content_key: str, forged_field: str,
) -> None:
    """A persisted authenticated V2 record cannot acquire a later wire field.

    The JSONL checksum is recomputed to demonstrate that store integrity alone
    is insufficient: contract verification must reject the forged value before
    a real signed service can publish operation, effect, or group records.
    """
    clock, _, monitor, policy, implementation = _monitor(
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(tmp_path / "records")),
        fingerprint="38a5be91af79d7e5ba9809bf383c699b6864ee50446239fe56a45e32b84638fe",
    )
    clock.now = TEST_NOW
    monitor.tick(evidence=_window(clock, policy, implementation, value="0.1"))
    journal = tmp_path / "records" / "memory_records.jsonl"
    batches = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    changed = False
    for batch in batches:
        for record in batch["records"]:
            if record["source_kind"] == source_kind:
                record["content"][content_key][forged_field] = "f" * 64
                changed = True
        body = {key: value for key, value in batch.items() if key != "checksum"}
        batch["checksum"] = sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    assert changed
    journal.write_text(
        "".join(json.dumps(batch, sort_keys=True, separators=(",", ":")) + "\n" for batch in batches),
        encoding="utf-8",
    )
    reopened = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(tmp_path / "records"))
    authority = _signed_monitoring_authority(
        clock=clock, policy=policy, implementation=implementation,
        evidence_provider=_NoEvidenceProvider(),
        signer=_TestDeploymentSigner(),
    )
    with pytest.raises(ValueError):
        _service_for_joined_monitoring_ingress(
            plane=reopened, clock=clock, authority=authority
        )
    assert not reopened.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    )
    assert not reopened.list_records(source_kind="semantic_ingestion_accepted_identity_operation")
    assert not reopened.list_records(source_kind="semantic_ingestion_effect")


@pytest.mark.parametrize(
    ("wire", "source_kind", "content_key", "forged_field"),
    (
        ("pre_field", "semantic_ingestion_capability_status", "status", "authorization_checkpoint_digest"),
        ("pre_field", "semantic_ingestion_capability_monitor_decision", "decision", "evaluation_kind"),
        ("pre_field", "semantic_ingestion_capability_initial_freshness", "freshness", "traffic_state_changed_at"),
        ("extended", "semantic_ingestion_capability_status", "status", "authorization_checkpoint_digest"),
        ("extended", "semantic_ingestion_capability_monitor_decision", "decision", "evaluation_kind"),
        ("extended", "semantic_ingestion_capability_initial_freshness", "freshness", "traffic_state_changed_at"),
    ),
)
def test_forged_legacy_monitor_wire_fields_fail_before_signed_ingress_publication(
    tmp_path: Path, wire: str, source_kind: str, content_key: str, forged_field: str,
) -> None:
    """Legacy V1 preimages reject later fields even with a valid JSONL checksum."""
    clock, _, monitor, policy, implementation = _monitor(
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(tmp_path / "records")),
        fingerprint="38a5be91af79d7e5ba9809bf383c699b6864ee50446239fe56a45e32b84638fe",
    )
    clock.now = TEST_NOW
    monitor.tick(evidence=_window(clock, policy, implementation, value="0.1"))
    journal = tmp_path / "records" / "memory_records.jsonl"
    batches = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    changed = False
    for batch in batches:
        for record in batch["records"]:
            if record["source_kind"] != source_kind:
                continue
            current = record["content"][content_key]
            body = {key: value for key, value in current.items() if key not in {
                "schema_version", "wire_generation", "status_digest", "decision_digest", "evidence_digest",
            }}
            if wire == "pre_field":
                body.pop("authorization_checkpoint_digest", None)
                body.pop("evaluation_kind", None)
                body.pop("traffic_state_changed_at", None)
                body.pop("label_pipeline_state_changed_at", None)
            domain = {
                "status": b"memorii.semantic-ingestion.capability-status.v1",
                "decision": b"memorii.semantic-ingestion.capability-monitoring-decision.v1",
                "freshness": b"memorii.semantic-ingestion.capability-evidence-freshness.v1",
            }[content_key]
            digest_key = {
                "status": "status_digest", "decision": "decision_digest", "freshness": "evidence_digest",
            }[content_key]
            legacy = {**body, digest_key: contract_digest(domain, body)}
            legacy[forged_field] = "f" * 64
            record["content"][content_key] = legacy
            changed = True
        body = {key: value for key, value in batch.items() if key != "checksum"}
        batch["checksum"] = sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    assert changed
    journal.write_text(
        "".join(json.dumps(batch, sort_keys=True, separators=(",", ":")) + "\n" for batch in batches),
        encoding="utf-8",
    )
    reopened = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(tmp_path / "records"))
    authority = _signed_monitoring_authority(
        clock=clock, policy=policy, implementation=implementation,
        evidence_provider=_NoEvidenceProvider(),
        signer=_TestDeploymentSigner(),
    )
    with pytest.raises(ValueError):
        _service_for_joined_monitoring_ingress(
            plane=reopened, clock=clock, authority=authority
        )
    assert not reopened.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    )
    assert not reopened.list_records(source_kind="semantic_ingestion_accepted_identity_operation")
    assert not reopened.list_records(source_kind="semantic_ingestion_effect")


def test_normal_reconciliation_scheduler_expires_monitor_without_ingress() -> None:
    clock, _, _, policy, implementation = _monitor()
    initial_evidence = _window(clock, policy, implementation, value="0.1")

    class EvidenceProvider:
        def load_evidence_windows(self, *, max_items: int):
            return ()

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
        deployment_authorization_current_trust_verifier=_current_trust_verifier(signer),
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
    decisions = plane.list_records(source_kind="semantic_ingestion_capability_monitor_decision")
    assert decisions[-1].content["decision"]["evaluation_kind"] == "missing_window"
    status = plane.list_records(source_kind="semantic_ingestion_capability_status")
    assert status[-1].content["status"]["status"] == "evidence_only"
    assert not plane.list_records(source_kind="semantic_ingestion_source")
    assert not plane.list_records(source_kind="semantic_ingestion_accepted_identity_operation")
    assert not plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    )


@pytest.mark.parametrize("expired", (False, True))
def test_signed_monitor_initialization_requires_current_use_lease(expired: bool) -> None:
    clock, _, _, policy, implementation = _monitor()

    class EvidenceProvider:
        def load_evidence_windows(self, *, max_items: int):
            return ()

    signer = _TestDeploymentSigner()
    trust = _CurrentDeploymentTrust()
    authority = _signed_monitoring_authority(
        clock=clock, policy=policy, implementation=implementation,
        evidence_provider=EvidenceProvider(), signer=signer, trust=trust,
        expires_at=clock.now + timedelta(seconds=1) if expired else clock.now + timedelta(days=1),
    )
    if expired:
        # The authority was retained while valid, then time advanced before
        # process construction. Build it at the prior server instant.
        clock.now += timedelta(seconds=1)
    assert authority is not None
    if not expired:
        trust.revoke()
    plane = MemoryPlaneService()
    build_provider_memory_service_from_env(
        memory_plane=plane, now_provider=lambda: clock.now,
        verified_capability_monitoring_authorities=(authority,),
    )
    assert not plane.list_records(
        source_kind="semantic_ingestion_capability_status"
    )
    assert not plane.list_records(
        source_kind="semantic_ingestion_capability_authorization_checkpoint"
    )


@pytest.mark.parametrize(
    ("payload_factory", "diagnostic"),
    [
        (lambda clock, policy, implementation: [], "provider_failure_non_tuple"),
        (lambda clock, policy, implementation: (object(),), "provider_failure_non_window"),
        (
            lambda clock, policy, implementation: (
                _window(clock, policy, implementation).model_copy(
                    update={"capability_fingerprint": "b" * 64}
                ),
            ),
            "provider_failure_unknown_capability",
        ),
        (
            lambda clock, policy, implementation: (
                _window(clock, policy, implementation),
                _window(clock, policy, implementation),
            ),
            "provider_failure_duplicate_capability",
        ),
        (
            lambda clock, policy, implementation: (
                _window(clock, policy, implementation),
                _window(clock, policy, implementation),
                _window(clock, policy, implementation),
            ),
            "provider_failure_oversized_result",
        ),
    ],
)
def test_signed_factory_malformed_provider_poll_fails_closed_at_deadline(
    payload_factory, diagnostic: str
) -> None:
    clock, _, _, policy, implementation = _monitor()

    class Provider:
        payload: object

        def load_evidence_windows(self, *, max_items: int):
            return self.payload

    provider = Provider()
    provider.payload = payload_factory(clock, policy, implementation)
    authority = _signed_monitoring_authority(
        clock=clock,
        policy=policy,
        implementation=implementation,
        evidence_provider=cast(CapabilityEvidenceWindowProvider, provider),
        signer=_TestDeploymentSigner(),
        expires_at=clock.now + timedelta(days=2),
    )
    plane = MemoryPlaneService()
    service = build_provider_memory_service_from_env(
        memory_plane=plane,
        now_provider=lambda: clock.now,
        verified_capability_monitoring_authorities=(authority,),
    )
    max_items = 2 if diagnostic == "provider_failure_duplicate_capability" else 1
    assert service.process_capability_monitoring(max_items=max_items) == ()
    clock.now += timedelta(days=1)
    results = service.process_capability_monitoring(max_items=max_items)
    assert len(results) == 1
    assert results[0].status.status == "evidence_only"
    assert results[0].decision.evaluation_kind == "provider_failure"
    assert diagnostic in results[0].decision.reason_codes
    assert not plane.list_records(source_kind="semantic_ingestion_source")
    assert not plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    )


def test_signed_factory_direct_tick_revalidates_revoked_authority() -> None:
    clock, _, _, policy, implementation = _monitor()

    class Provider:
        def load_evidence_windows(self, *, max_items: int):
            return (_window(clock, policy, implementation, value="0.1"),)

    trust = _CurrentDeploymentTrust()
    authority = _signed_monitoring_authority(
        clock=clock,
        policy=policy,
        implementation=implementation,
        evidence_provider=Provider(),
        signer=_TestDeploymentSigner(),
        trust=trust,
    )
    plane = MemoryPlaneService()
    service = build_provider_memory_service_from_env(
        memory_plane=plane,
        now_provider=lambda: clock.now,
        verified_capability_monitoring_authorities=(authority,),
    )
    trust.current = False
    result = service.run_capability_monitor_tick(
        evidence=_window(clock, policy, implementation, value="0.1")
    )
    assert result.status.status == "evidence_only"
    assert result.decision.evaluation_kind == "authorization_failure"
    assert service._semantic_writer_admission.current().writer_epoch == 2
    assert not plane.list_records(source_kind="semantic_ingestion_source")
    assert not plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    )


@pytest.mark.parametrize(
    ("exception_type", "diagnostic"),
    [
        (RuntimeError, "provider_failure_known_exception"),
        (KeyError, "provider_failure_unexpected_exception"),
        (_UnexpectedEvidenceProviderError, "provider_failure_unexpected_exception"),
    ],
)
def test_scheduler_accounts_for_more_than_sixteen_active_policies_after_provider_failure(
    exception_type: type[Exception], diagnostic: str
) -> None:
    """Every ordinary provider exception fails closed across signed inventory."""
    clock = _Clock()
    implementation = CAPABILITY_MONITOR_SEQUENTIAL_IMPLEMENTATION_FINGERPRINT
    manifest = SequentialTestManifest.create(
        method="time_uniform_confidence_sequence",
        bounded_value_lower="0",
        bounded_value_upper="1",
        spending_rule_id="inverse_quadratic_union_bound_v1",
        implementation_fingerprint=implementation,
    )
    gate = MonitoringMetricGate.create(
        metric_id="error", direction="upper", warning_threshold="0.4",
        breach_threshold="0.8", minimum_independent_clusters=1,
        maximum_label_delay=timedelta(days=1), alpha_budget="0.1",
    )
    policies = tuple(
        CapabilityMonitoringPolicy.create(
            capability_fingerprint=f"{index:064x}", monitoring_policy_revision="1",
            maximum_independent_label_age=timedelta(hours=1),
            maximum_canary_success_age=timedelta(hours=1),
            minimum_labeled_clusters_per_window=1, label_window=timedelta(days=1),
            paused_traffic_grace_period=timedelta(hours=1),
            label_pipeline_outage_grace_period=timedelta(hours=1),
            stale_evidence_action="evidence_only", metric_gates=(gate,),
            family_wise_alpha_budget="0.1", sequential_test_manifest=manifest,
            breach_action="evidence_only",
        )
        for index in range(1, 18)
    )

    class FailingProvider:
        def load_evidence_windows(self, *, max_items: int):
            raise exception_type("host evidence transport unavailable")

    provider = FailingProvider()
    signer = _TestDeploymentSigner()
    authorities = tuple(
        _signed_monitoring_authority(
            clock=clock,
            policy=policy,
            implementation=implementation,
            evidence_provider=provider,
            signer=signer,
            expires_at=clock.now + timedelta(days=2),
        )
        for policy in policies
    )
    plane = MemoryPlaneService()
    service = build_provider_memory_service_from_env(
        memory_plane=plane,
        now_provider=lambda: clock.now,
        verified_capability_monitoring_authorities=authorities,
    )
    clock.now += timedelta(hours=1)
    results = service.process_capability_monitoring(max_items=1)
    assert len(results) == 17
    assert {result.status.capability_fingerprint for result in results} == {
        policy.capability_fingerprint for policy in policies
    }
    assert all(result.status.status == "evidence_only" for result in results)
    assert all(result.decision.evaluation_kind == "provider_failure" for result in results)
    assert all(diagnostic in result.decision.reason_codes for result in results)
    assert not plane.list_records(source_kind="semantic_ingestion_source")
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
    status = CapabilityStatus.model_validate(status_record.content["status"])
    binding = SimpleNamespace(
        operation_id="operation",
        capability_fingerprint=policy.capability_fingerprint,
        capability_status_revision="1",
        capability_status_record_digest=record_digest(status_record),
        monitoring_policy_digest=policy.policy_digest,
        evidence_freshness_digest=status.evidence_freshness_digest,
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

    with pytest.raises(PreplanningStoreError, match="checkpoint is unavailable"):
        store._capability_status_preconditions_for_group_commit(
            request  # pyright: ignore[reportArgumentType] - focused internal fixture
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
    status = CapabilityStatus.model_validate(status_record.content["status"])
    coordinate = {
        "capability_fingerprint": policy.capability_fingerprint,
        "capability_status_revision": "1",
        "capability_status_record_digest": record_digest(status_record),
        "monitoring_policy_digest": policy.policy_digest,
        "evidence_freshness_digest": status.evidence_freshness_digest,
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
    with pytest.raises(PreplanningStoreError, match="checkpoint is unavailable"):
        store._capability_status_preconditions_for_group_commit(
            request  # pyright: ignore[reportArgumentType] - focused internal fixture
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
    clock, _, monitor, policy, implementation = _monitor()
    evidence = _window(clock, policy, implementation, value="0.1")
    result = monitor.tick(evidence=evidence)
    metric = result.decision.metric_decisions[0]
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
        "eligible_event_ids": [item.event_id for item in evidence.observations],
        "freshness": result.freshness.freshness,
        "freshness_reason": result.freshness.freshness_reason,
        "labeled_cluster_count": result.freshness.labeled_cluster_count_in_window,
        "metric_id": metric.metric_id,
        "independent_cluster_count": metric.independent_cluster_count,
        "estimate": metric.estimate,
        "lower_bound": metric.lower_bound,
        "upper_bound": metric.upper_bound,
        "alpha_spent": metric.alpha_spent,
        "metric_status": metric.status,
        "action": result.decision.action,
        "reason_codes": list(result.decision.reason_codes),
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


def test_pre_checkpoint_v1_jsonl_restart_upcasts_and_fences_legacy_active_state(
    tmp_path: Path,
) -> None:
    """A persisted pre-c9 monitor state remains readable but cannot admit work.

    This writes the historical wire payload directly to JSONL before the
    writer policy is installed.  It therefore exercises real reload parsing
    and the original v1 digest preimages, rather than a model-only fixture.
    """
    clock, _, _, policy, _ = _monitor(
        fingerprint="38a5be91af79d7e5ba9809bf383c699b6864ee50446239fe56a45e32b84638fe"
    )
    # The built-in graph authority fixture is valid at its pinned production
    # server instant; keep the historical monitor wire state at that instant.
    clock.now = TEST_NOW
    store_path = tmp_path / "pre-c9-monitor-state"
    freshness_body = {
        "capability_fingerprint": policy.capability_fingerprint,
        "monitoring_policy_digest": policy.policy_digest,
        "evaluated_at": clock.now,
        "latest_independent_label_at": clock.now,
        "latest_canary_success_at": clock.now,
        "labeled_cluster_count_in_window": 20,
        "traffic_state": "paused",
        "label_pipeline_state": "healthy",
        "freshness": "grace",
        "freshness_reason": "traffic_pause_grace",
        "status_revision": "1",
    }
    freshness = {
        **freshness_body,
        "evidence_digest": contract_digest(
            b"memorii.semantic-ingestion.capability-evidence-freshness.v1",
            freshness_body,
        ),
    }
    freshness_record = CanonicalMemoryRecord(
        memory_id="semantic_ingestion:capability-initial-freshness:" + freshness["evidence_digest"],
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "capability_initial_freshness",
            "evidence_window_digest": "1" * 64,
            "freshness": freshness,
            "metric_decisions": (),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_capability_initial_freshness",
        timestamp=clock.now,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    decision_body = {
        "capability_fingerprint": policy.capability_fingerprint,
        "monitoring_policy_digest": policy.policy_digest,
        "evidence_window_digest": "1" * 64,
        "evaluated_at": clock.now,
        "metric_decisions": (),
        "evidence_freshness": "grace",
        "action": "remain_active",
        "reason_codes": (),
    }
    decision = {
        **decision_body,
        "decision_digest": contract_digest(
            b"memorii.semantic-ingestion.capability-monitoring-decision.v1",
            decision_body,
        ),
    }
    decision_record = CanonicalMemoryRecord(
        memory_id="semantic_ingestion:capability-monitor-decision:legacy-v1",
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "capability_monitor_decision",
            "decision": decision,
            "freshness": freshness,
            "status_record_digest": "2" * 64,
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_capability_monitor_decision",
        timestamp=clock.now,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    status_body = {
        "capability_fingerprint": policy.capability_fingerprint,
        "status": "active",
        "status_revision": 1,
        "monitoring_policy_digest": policy.policy_digest,
        "evidence_freshness_digest": record_digest(freshness_record),
    }
    status_record = CanonicalMemoryRecord(
        memory_id="semantic_ingestion:capability-status:" + policy.capability_fingerprint,
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "capability_status",
            "status": {
                **status_body,
                "status_digest": contract_digest(
                    b"memorii.semantic-ingestion.capability-status.v1", status_body
                ),
            },
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_capability_status",
        timestamp=clock.now,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    # This is the exact JSONL batch envelope emitted by the historical store.
    # Construct it as a fixture because current stores correctly reject an
    # unauthorised semantic-control write before installing their policy.
    batch_body = {
        "revision": 1,
        "data_revision": 0,
        "records": [
            record.model_dump(mode="json")
            for record in (freshness_record, decision_record, status_record)
        ],
    }
    batch = {
        **batch_body,
        "checksum": sha256(
            json.dumps(batch_body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }
    store_path.mkdir()
    (store_path / "memory_records.jsonl").write_text(
        json.dumps(batch, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    persisted = (store_path / "memory_records.jsonl").read_text(encoding="utf-8")
    assert "authorization_checkpoint_digest" not in persisted
    assert "traffic_state_changed_at" not in persisted
    assert "evaluation_kind" not in persisted

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path))
    reopened_status = CapabilityStatus.model_validate(
        reopened_plane.get_record(status_record.memory_id).content["status"]  # type: ignore[union-attr]
    )
    reopened_freshness = CapabilityEvidenceFreshness.model_validate(
        reopened_plane.get_record(freshness_record.memory_id).content["freshness"]  # type: ignore[union-attr]
    )
    reopened_decision = CapabilityMonitoringDecision.model_validate(
        reopened_plane.get_record(decision_record.memory_id).content["decision"]  # type: ignore[union-attr]
    )
    assert reopened_status.schema_version == 1
    assert reopened_status.authorization_checkpoint_digest is None
    assert reopened_freshness.schema_version == 1
    assert reopened_decision.schema_version == 1
    assert reopened_decision.evaluation_kind == "evidence_window"

    class MissingEvidence:
        def load_evidence_windows(self, *, max_items: int):
            return ()

    authority = _signed_monitoring_authority(
        clock=clock,
        policy=policy,
        implementation=CAPABILITY_MONITOR_SEQUENTIAL_IMPLEMENTATION_FINGERPRINT,
        evidence_provider=MissingEvidence(),
        signer=_TestDeploymentSigner(),
    )
    service = _service_for_joined_monitoring_ingress(
        plane=reopened_plane, clock=clock, authority=authority
    )
    denied = _joined_monitoring_sync(service, operation_id="pre-checkpoint-v1-ingress")
    assert denied.blocked_reasons["semantic_ingestion"] == "graph_transaction_authority_unavailable"
    assert not reopened_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    )
    assert not reopened_plane.list_records(
        source_kind="semantic_ingestion_accepted_identity_operation"
    )
    assert not reopened_plane.list_records(
        source_kind="semantic_ingestion_effect"
    )

    demoted = service.process_capability_monitoring(max_items=1)
    assert len(demoted) == 1
    assert demoted[0].status.status == "evidence_only"
    assert demoted[0].status.schema_version == 2
    assert service._semantic_writer_admission.current().active_runtime_mode == "evidence_only"
    assert service._semantic_writer_admission.current().writer_epoch == 2
    reopened_after = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path))
    persisted_status = reopened_after.get_record(status_record.memory_id)
    assert persisted_status is not None
    assert CapabilityStatus.model_validate(persisted_status.content["status"]).status == "evidence_only"


def test_extended_v1_jsonl_restart_preserves_v1_preimages_and_group_authority(
    tmp_path: Path,
) -> None:
    """The e0/c9 unversioned field additions were still V1-digested values."""
    clock, _, _, policy, implementation = _monitor(
        fingerprint="38a5be91af79d7e5ba9809bf383c699b6864ee50446239fe56a45e32b84638fe"
    )
    clock.now = TEST_NOW
    store_path = tmp_path / "extended-v1-monitor-state"

    class HealthyEvidence:
        def load_evidence_windows(self, *, max_items: int):
            return (_window(clock, policy, implementation, value="0.1"),)

    authority = _signed_monitoring_authority(
        clock=clock,
        policy=policy,
        implementation=implementation,
        evidence_provider=HealthyEvidence(),
        signer=_TestDeploymentSigner(),
    )
    checkpoint = capability_monitoring_authority_checkpoint(authority)
    freshness_body = {
        "capability_fingerprint": policy.capability_fingerprint,
        "monitoring_policy_digest": policy.policy_digest,
        "evaluated_at": clock.now,
        "latest_independent_label_at": clock.now,
        "latest_canary_success_at": clock.now,
        "labeled_cluster_count_in_window": 20,
        "traffic_state": "active",
        "traffic_state_changed_at": clock.now,
        "label_pipeline_state": "healthy",
        "label_pipeline_state_changed_at": clock.now,
        "freshness": "fresh",
        "freshness_reason": "fresh",
        "status_revision": "1",
    }
    freshness = {
        **freshness_body,
        "evidence_digest": contract_digest(
            b"memorii.semantic-ingestion.capability-evidence-freshness.v1",
            freshness_body,
        ),
    }
    freshness_record = CanonicalMemoryRecord(
        memory_id="semantic_ingestion:capability-initial-freshness:" + freshness["evidence_digest"],
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "capability_initial_freshness",
            "evidence_window_digest": "3" * 64,
            "freshness": freshness,
            "metric_decisions": (),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_capability_initial_freshness",
        timestamp=clock.now,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    decision_body = {
        "capability_fingerprint": policy.capability_fingerprint,
        "monitoring_policy_digest": policy.policy_digest,
        "evidence_window_digest": "3" * 64,
        "evaluated_at": clock.now,
        "metric_decisions": (),
        "evidence_freshness": "fresh",
        "evaluation_kind": "evidence_window",
        "action": "remain_active",
        "reason_codes": (),
    }
    decision = {
        **decision_body,
        "decision_digest": contract_digest(
            b"memorii.semantic-ingestion.capability-monitoring-decision.v1",
            decision_body,
        ),
    }
    checkpoint_record = CanonicalMemoryRecord(
        memory_id=(
            "semantic_ingestion:capability-authorization-checkpoint:"
            + policy.capability_fingerprint
        ),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "capability_authorization_checkpoint",
            "checkpoint": checkpoint.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_capability_authorization_checkpoint",
        timestamp=clock.now,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    status_body = {
        "capability_fingerprint": policy.capability_fingerprint,
        "status": "active",
        "status_revision": 1,
        "monitoring_policy_digest": policy.policy_digest,
        "evidence_freshness_digest": record_digest(freshness_record),
        "authorization_checkpoint_digest": record_digest(checkpoint_record),
    }
    status_record = CanonicalMemoryRecord(
        memory_id="semantic_ingestion:capability-status:" + policy.capability_fingerprint,
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "capability_status",
            "status": {
                **status_body,
                "status_digest": contract_digest(
                    b"memorii.semantic-ingestion.capability-status.v1", status_body
                ),
            },
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_capability_status",
        timestamp=clock.now,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    decision_record = CanonicalMemoryRecord(
        memory_id="semantic_ingestion:capability-monitor-decision:extended-v1",
        domain=MemoryDomain.EXECUTION,
        text="",
        content={
            "semantic_ingestion_kind": "capability_monitor_decision",
            "decision": decision,
            "freshness": freshness,
            "status_record_digest": record_digest(status_record),
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_capability_monitor_decision",
        timestamp=clock.now,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    batch_body = {
        "revision": 1,
        "data_revision": 0,
        "records": [
            record.model_dump(mode="json")
            for record in (checkpoint_record, freshness_record, decision_record, status_record)
        ],
    }
    batch = {
        **batch_body,
        "checksum": sha256(
            json.dumps(batch_body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }
    store_path.mkdir()
    (store_path / "memory_records.jsonl").write_text(
        json.dumps(batch, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path))
    reopened_status = CapabilityStatus.model_validate(
        reopened_plane.get_record(status_record.memory_id).content["status"]  # type: ignore[union-attr]
    )
    reopened_freshness = CapabilityEvidenceFreshness.model_validate(
        reopened_plane.get_record(freshness_record.memory_id).content["freshness"]  # type: ignore[union-attr]
    )
    reopened_decision = CapabilityMonitoringDecision.model_validate(
        reopened_plane.get_record(decision_record.memory_id).content["decision"]  # type: ignore[union-attr]
    )
    assert reopened_status.schema_version == 1
    assert reopened_status.wire_generation == "extended_v1"
    assert reopened_freshness.wire_generation == "extended_v1"
    assert reopened_decision.wire_generation == "extended_v1"

    service = _service_for_joined_monitoring_ingress(
        plane=reopened_plane, clock=clock, authority=authority
    )
    transitioned = service.process_capability_monitoring(max_items=1)
    assert len(transitioned) == 1
    assert transitioned[0].status.status == "active"
    assert transitioned[0].status.schema_version == 2
    assert transitioned[0].status.authorization_checkpoint_digest == record_digest(checkpoint_record)
    current_record = reopened_plane.get_record(status_record.memory_id)
    assert current_record is not None

    observed_preconditions = []
    original_write = reopened_plane.conditionally_write_records

    def capture_group_preconditions(records, **kwargs):
        if any(
            record.source_kind == "semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
            for record in records
        ):
            observed_preconditions.extend(kwargs["preconditions"])
        return original_write(records, **kwargs)

    reopened_plane.conditionally_write_records = capture_group_preconditions  # type: ignore[method-assign]
    admitted = _joined_monitoring_sync(service, operation_id="extended-v1-ingress")
    assert admitted.blocked_reasons["semantic_ingestion"] == "source_only"
    assert len(reopened_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    )) == 1
    expected_digests = {
        record_digest(current_record),
        record_digest(checkpoint_record),
    }
    assert expected_digests.issubset({
        precondition.expected_digest
        for precondition in observed_preconditions
        if hasattr(precondition, "expected_digest")
    })
    reopened_after = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path))
    persisted_status = reopened_after.get_record(status_record.memory_id)
    assert persisted_status is not None
    assert CapabilityStatus.model_validate(persisted_status.content["status"]).schema_version == 2


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
    tmp_path, monkeypatch
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
    source_text = "Atlas owner is Bob."
    normalization, _ = _v3_normalization_host_builder(proposal=proposal)
    store_path = tmp_path / "monitor-group-race"
    initial_evidence = _window(type("Clock", (), {"now": TEST_NOW})(), policy, implementation)

    class EvidenceProvider:
        def load_evidence_windows(self, *, max_items: int):
            return ()

    signer = _TestDeploymentSigner()
    artifact = DeploymentAuthorizationIssuer(
        authority=IssuerAuthority("monitor-release", "monitor-key", "8" * 64, signer),
        repository=InMemoryDeploymentAuthorizationRepository(), now_provider=lambda: TEST_NOW,
    ).prepare_verified(
        target_artifact_digest=contract_digest(
            b"memorii.semantic-ingestion.capability-monitoring-baseline.v1",
            {"monitoring_policy_digest": policy.policy_digest,
             "initial_evidence_window_digest": initial_evidence.evidence_window_digest},
        ), deployment_manifest_digest="7" * 64,
        capability_fingerprint=policy.capability_fingerprint,
        verified_capability_baseline_approval_release_digest="6" * 64,
        requested_active_epoch=1, expires_at=TEST_NOW + timedelta(days=1),
    )
    raw = json.dumps(artifact.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    class LinearizedTrust(_CurrentDeploymentTrust):
        def __init__(self) -> None:
            super().__init__()
            self.revocation_attempted = Event()
            self.revocation_completed = Event()

        def revoke(self) -> None:
            self.revocation_attempted.set()
            super().revoke()
            self.revocation_completed.set()

    trust = LinearizedTrust()
    authority = build_verified_capability_monitoring_authority(
        deployment_authorization_bytes=raw,
        deployment_authorization_verifier=DeploymentAuthorizationArtifactVerifier(signer),
        deployment_authorization_current_trust_verifier=_current_trust_verifier(signer, trust),
        policy=policy, initial_evidence=initial_evidence,
        evidence_provider=EvidenceProvider(), server_time=TEST_NOW,
    )
    assert authority is not None
    service = provider_service(
        memory_plane=MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path)),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=normalization,
        verified_capability_monitoring_authorities=(authority,),
    )
    successful = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN, content=source_text,
        operation_id="monitor-registry-byte-success", task_id="task:one",
        user_id="user:alice", authenticated_host_ingress=_host_ingress(),
    )
    assert successful.blocked_reasons["semantic_ingestion"] == "source_only"
    initial_group_count = len(service._memory_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    ))
    assert initial_group_count == 1

    def registry_bytes(value):
        if isinstance(value, bytes):
            try:
                return registry_bytes(decode_typed_value(value))
            except (TypeError, ValueError):
                return None
        if isinstance(value, dict):
            if "capability_registry_canonical_bytes" in value:
                return value["capability_registry_canonical_bytes"]
            return next((found for item in value.values() if (found := registry_bytes(item)) is not None), None)
        if isinstance(value, (tuple, list)):
            return next((found for item in value if (found := registry_bytes(item)) is not None), None)
        return None

    member_record = next(record for record in service._memory_plane.list_records(
        source_kind="semantic_ingestion_generation_member"
    ) if record.content["member"]["kind"] == "bootstrap_graph_normalization_authority")
    member = AtomicGenerationMember.model_validate(member_record.content["member"])
    normalization_authority = decode_semantic_contract(
        member.canonical_payload, BootstrapGraphNormalizationAuthorityMemberV3
    )
    registry_before = normalization_authority.capability_registry_canonical_bytes
    assert registry_before is not None
    assert isinstance(registry_before, bytes)
    assert CapabilityRegistrySnapshot.model_validate(decode_typed_value(registry_before)).snapshot_digest
    status_record = service._memory_plane.get_record("semantic_ingestion:capability-status:" + fingerprint)
    assert status_record is not None
    cas_entered = Event()
    allow_cas = Event()
    original_cas = service._memory_plane.conditionally_write_records

    def pause_after_trust_lease(records, **kwargs):
        if any(
            record.source_kind
            == "semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
            for record in records
        ):
            cas_entered.set()
            assert allow_cas.wait(timeout=5)
        return original_cas(records, **kwargs)

    monkeypatch.setattr(
        service._memory_plane, "conditionally_write_records", pause_after_trust_lease
    )
    outcomes = []
    failures = []

    def write_group() -> None:
        try:
            outcomes.append(service.sync_event(
                operation=ProviderOperation.CHAT_USER_TURN,
                content=source_text,
                operation_id="monitor-group-cas-race",
                task_id="task:monitor",
                user_id="user:alice",
                authenticated_host_ingress=_host_ingress(),
            ))
        except BaseException as exc:  # pragma: no cover - assertion surface below
            failures.append(exc)

    group_thread = Thread(target=write_group)
    group_thread.start()
    assert cas_entered.wait(timeout=60)
    revocation_thread = Thread(target=trust.revoke)
    revocation_thread.start()
    assert trust.revocation_attempted.wait(timeout=5)
    # `current_use()` still owns the host linearizer while the group CAS is
    # paused, so revocation cannot become visible before publication finishes.
    assert not trust.revocation_completed.is_set()
    assert len(service._memory_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    )) == initial_group_count
    allow_cas.set()
    group_thread.join(timeout=60)
    revocation_thread.join(timeout=5)
    assert not group_thread.is_alive()
    assert not revocation_thread.is_alive()
    assert not failures
    assert len(outcomes) == 1
    assert outcomes[0].blocked_reasons["semantic_ingestion"] == "source_only"
    assert trust.revocation_completed.is_set()
    assert len(service._memory_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    )) == initial_group_count + 1

    second = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content=source_text,
        operation_id="monitor-after-demotion",
        task_id="task:monitor",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert second.blocked_reasons["semantic_ingestion"] == "graph_transaction_authority_unavailable"
    assert service._semantic_writer_admission.current().active_runtime_mode == "evidence_only"
    assert len(service._memory_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    )) == initial_group_count + 1
    reopened = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path))
    persisted_status = reopened.get_record(status_record.memory_id)
    assert persisted_status is not None
    assert persisted_status.content["status"]["status"] == "evidence_only"
    reopened_member_record = next(record for record in reopened.list_records(
        source_kind="semantic_ingestion_generation_member"
    ) if record.memory_id == member_record.memory_id)
    reopened_member = AtomicGenerationMember.model_validate(
        reopened_member_record.content["member"]
    )
    registry_after = decode_semantic_contract(
        reopened_member.canonical_payload, BootstrapGraphNormalizationAuthorityMemberV3
    ).capability_registry_canonical_bytes
    assert registry_after == registry_before
    assert CapabilityRegistrySnapshot.model_validate(decode_typed_value(registry_after)).snapshot_digest
    assert len(reopened.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    )) == initial_group_count + 1


def test_installed_monitoring_configuration_activates_only_verified_operator_artifacts(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    configuration, policy = _installed_monitoring_configuration(tmp_path, clock=clock)
    service = build_provider_memory_service_from_env(
        now_provider=lambda: clock.now,
        installed_capability_monitoring_configuration=configuration,
    )
    assert service._capability_monitor is not None
    assert service._capability_monitor.configured_capability_fingerprints == (
        policy.capability_fingerprint,
    )
    # The signed baseline initialized active state during construction; the
    # identical first scheduler sample is intentionally deduplicated.
    assert service.process_capability_monitoring(max_items=1) == ()
    statuses = service._memory_plane.list_records(
        source_kind="semantic_ingestion_capability_status"
    )
    assert len(statuses) == 1
    assert statuses[0].content["status"]["status"] == "active"


@pytest.mark.parametrize(
    "failure", ("unknown_key", "tamper", "expired", "revoked", "path_substitution")
)
def test_installed_monitoring_configuration_fails_closed(
    tmp_path: Path, failure: str,
) -> None:
    clock = _Clock()
    configuration, _ = _installed_monitoring_configuration(tmp_path, clock=clock)
    authorization = Path(str(configuration["deployment_authorization_path"]))
    if failure == "unknown_key":
        payload = json.loads(authorization.read_text())
        payload["signing_key_reference"] = "unknown"
        authorization.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    elif failure == "tamper":
        authorization.write_bytes(authorization.read_bytes() + b" ")
    elif failure == "expired":
        payload = json.loads(authorization.read_text())
        payload["expires_at"] = (clock.now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        authorization.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    elif failure == "revoked":
        root = Path(str(configuration["revocation_reader_root"]))
        current = root / "current"
        current.mkdir()
        (current / ("6" * 64 + ".json")).write_text("{}")
    elif failure == "path_substitution":
        original = Path(str(configuration["monitoring_policy_path"]))
        substituted = tmp_path / "policy-link.json"
        substituted.symlink_to(original)
        configuration["monitoring_policy_path"] = str(substituted)
    with pytest.raises(ValueError, match="installed capability monitoring authority"):
        build_provider_memory_service_from_env(
            now_provider=lambda: clock.now,
            installed_capability_monitoring_configuration=configuration,
        )


def test_installed_monitoring_rejects_valid_signed_artifact_after_protected_clock_expiry(
    tmp_path: Path,
) -> None:
    """The lease samples the same host clock used at installed construction.

    This is intentionally not a tamper case: the Ed25519 signature remains
    valid at T2, while its signed expiry was at T1.
    """
    clock = _Clock()
    expiry = clock.now + timedelta(minutes=1)
    configuration, _ = _installed_monitoring_configuration(
        tmp_path, clock=clock, expires_at=expiry
    )
    clock.now = expiry + timedelta(seconds=1)
    plane = MemoryPlaneService()
    with pytest.raises(ValueError, match="installed capability monitoring authority"):
        build_provider_memory_service_from_env(
            memory_plane=plane,
            now_provider=lambda: clock.now,
            installed_capability_monitoring_configuration=configuration,
        )
    assert not plane.list_records(source_kind="semantic_ingestion_capability_status")
    assert not plane.list_records(
        source_kind="semantic_ingestion_capability_authorization_checkpoint"
    )


def test_absent_installed_monitoring_configuration_leaves_service_evidence_only() -> None:
    service = build_provider_memory_service_from_env()
    assert service._capability_monitor is not None
    assert service._capability_monitor.configured_capability_fingerprints == ()


def test_installed_monitoring_configuration_reaches_all_capture_roots(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    clock.now = datetime.now(UTC)
    configuration, policy = _installed_monitoring_configuration(tmp_path / "authority", clock=clock)
    installed = build_provider_memory_service_from_env(
        now_provider=lambda: clock.now,
        installed_capability_monitoring_configuration=configuration,
    )
    direct = ProviderMemoryService(
        now_provider=lambda: clock.now,
        verified_capability_monitoring_authorities=installed._verified_capability_monitoring_authorities,
    )
    factory = build_provider_memory_service_from_env(
        now_provider=lambda: clock.now,
        installed_capability_monitoring_configuration=configuration,
    )
    filesystem = build_filesystem_provider(
        tmp_path / "storage", now_provider=lambda: clock.now,
        installed_capability_monitoring_configuration=configuration,
    )
    hermes = HermesMemoryProvider(
        installed_capability_monitoring_configuration=configuration,
        now_provider=lambda: clock.now,
    )
    for service in (direct, factory, filesystem, hermes._service):
        assert service._capability_monitor.configured_capability_fingerprints == (
            policy.capability_fingerprint,
        )
        # Initial construction has durably activated the signed capability;
        # exercise the public scheduler rather than inspecting only wiring.
        assert service.process_capability_monitoring(max_items=1) == ()
        statuses = service._memory_plane.list_records(
            source_kind="semantic_ingestion_capability_status"
        )
        checkpoints = service._memory_plane.list_records(
            source_kind="semantic_ingestion_capability_authorization_checkpoint"
        )
        assert len(statuses) == len(checkpoints) == 1
        assert statuses[0].content["status"]["status"] == "active"


def test_installed_initial_activation_holds_revocation_lease_through_status_cas(
    tmp_path: Path, monkeypatch,
) -> None:
    """External revocation cannot become current between activation check and CAS."""
    clock = _Clock()
    configuration, _ = _installed_monitoring_configuration(tmp_path, clock=clock)
    plane = MemoryPlaneService()
    cas_entered = Event()
    release_cas = Event()
    original_write = plane.conditionally_write_records

    def pause_initial_status(records, **kwargs):
        if any(record.source_kind == "semantic_ingestion_capability_status" for record in records):
            cas_entered.set()
            assert release_cas.wait(timeout=5)
        return original_write(records, **kwargs)

    monkeypatch.setattr(plane, "conditionally_write_records", pause_initial_status)
    errors: list[BaseException] = []
    services = []

    def construct() -> None:
        try:
            services.append(build_provider_memory_service_from_env(
                memory_plane=plane, now_provider=lambda: clock.now,
                installed_capability_monitoring_configuration=configuration,
            ))
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    activation = Thread(target=construct)
    activation.start()
    assert cas_entered.wait(timeout=10)
    reader = InstalledProductionRevocationReader().from_fixed_configuration(
        {"reader_root": configuration["revocation_reader_root"]}, now_provider=lambda: clock.now
    )
    published = Event()

    def revoke() -> None:
        reader.publish_revocation_mapping(
            prior_approval_release_digest="6" * 64,
            receipt_digest="a" * 64,
            checkpoint_digest="b" * 64,
        )
        published.set()

    revoker = Thread(target=revoke)
    revoker.start()
    assert not published.wait(timeout=0.2)
    release_cas.set()
    activation.join(timeout=10)
    revoker.join(timeout=10)
    assert not activation.is_alive() and not revoker.is_alive()
    assert not errors
    assert published.is_set()
    assert len(services) == 1
    demoted = services[0].process_capability_monitoring(max_items=1)
    assert len(demoted) == 1
    assert demoted[0].status.status == "evidence_only"
    # Subsequent installed construction sees the current mapping and fails
    # before a replacement status/checkpoint can be initialized.
    with pytest.raises(ValueError, match="installed capability monitoring authority"):
        build_provider_memory_service_from_env(
            memory_plane=MemoryPlaneService(), now_provider=lambda: clock.now,
            installed_capability_monitoring_configuration=configuration,
        )


def test_installed_revocation_publication_is_interprocess_linearized_and_monotonic(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    configuration, _ = _installed_monitoring_configuration(tmp_path, clock=clock)
    root = str(configuration["revocation_reader_root"])
    artifact = DeploymentAuthorizationArtifact.model_validate_json(
        Path(str(configuration["deployment_authorization_path"])).read_bytes()
    )
    reader = InstalledProductionRevocationReader().from_fixed_configuration(
        {"reader_root": root}
    )
    context = get_context("fork")
    queue = context.Queue()
    release = "6" * 64
    receipt = "a" * 64
    checkpoint = "b" * 64
    with reader.current_use(artifact=artifact, server_time=clock.now) as current:
        assert current
        child = context.Process(
            target=_publish_revocation_in_child,
            args=(root, release, receipt, checkpoint, queue),
        )
        child.start()
        child.join(timeout=0.2)
        assert child.is_alive()
        with pytest.raises(Empty):
            queue.get_nowait()
    child.join(timeout=5)
    assert child.exitcode == 0
    assert queue.get(timeout=1) == "published"
    # Exact retry is idempotent; a different coordinate is a conflict and
    # cannot roll back or overwrite the published mapping.
    reader.publish_revocation_mapping(
        prior_approval_release_digest=release,
        receipt_digest=receipt,
        checkpoint_digest=checkpoint,
    )
    with pytest.raises(ValueError, match="production_revocation_conflict"):
        reader.publish_revocation_mapping(
            prior_approval_release_digest=release,
            receipt_digest="c" * 64,
            checkpoint_digest=checkpoint,
        )
    assert json.loads((Path(root) / "current" / f"{release}.json").read_text()) == {
        "prior_approval_release_digest": release,
        "receipt_digest": receipt,
        "checkpoint_digest": checkpoint,
    }


def test_installed_revocation_publish_cli_persists_opaque_evidence_before_mapping(
    tmp_path: Path,
) -> None:
    root = tmp_path / "revocations"
    release = "6" * 64
    receipt_digest = "a" * 64
    checkpoint_digest = "b" * 64
    receipt = {
        "schema_version": 1, "purpose": "production_revocation_receipt",
        "prior_approval_release_digest": release, "receipt_digest": receipt_digest,
        "signing_key_coordinate": "acceptance-key", "signature": "00",
    }
    checkpoint = {
        "schema_version": 1, "purpose": "production_epoch_checkpoint",
        "checkpoint_digest": checkpoint_digest,
        "revocation_receipt_digests": [receipt_digest],
        "signing_key_coordinate": "acceptance-key", "signature": "00",
    }
    receipt_path = tmp_path / "receipt.json"
    checkpoint_path = tmp_path / "checkpoint.json"
    for path, value in ((receipt_path, receipt), (checkpoint_path, checkpoint)):
        path.write_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii"))
    result = subprocess.run(
        [sys.executable, "-m", "memorii.tools.semantic_ingestion_revocation_publish",
         "--root", str(root), "--prior-approval-release-digest", release,
         "--receipt", str(receipt_path), "--checkpoint", str(checkpoint_path)],
        cwd=Path(__file__).parents[4],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[4] / "memorii")},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (root / "objects" / receipt_digest).read_bytes() == receipt_path.read_bytes()
    assert (root / "objects" / checkpoint_digest).read_bytes() == checkpoint_path.read_bytes()
    assert json.loads((root / "current" / f"{release}.json").read_text()) == {
        "prior_approval_release_digest": release,
        "receipt_digest": receipt_digest,
        "checkpoint_digest": checkpoint_digest,
    }


@pytest.mark.parametrize("mutation", ("missing", "tampered", "conflicting"))
def test_installed_revocation_publish_cli_never_exposes_mapping_on_invalid_objects(
    tmp_path: Path, mutation: str,
) -> None:
    root = tmp_path / "revocations"
    release = "6" * 64
    receipt_digest = "a" * 64
    checkpoint_digest = "b" * 64
    receipt = {
        "schema_version": 1, "purpose": "production_revocation_receipt",
        "prior_approval_release_digest": release, "receipt_digest": receipt_digest,
        "signing_key_coordinate": "acceptance-key", "signature": "00",
    }
    checkpoint = {
        "schema_version": 1, "purpose": "production_epoch_checkpoint",
        "checkpoint_digest": checkpoint_digest,
        "revocation_receipt_digests": [receipt_digest],
        "signing_key_coordinate": "acceptance-key", "signature": "00",
    }
    receipt_path = tmp_path / "receipt.json"
    checkpoint_path = tmp_path / "checkpoint.json"
    receipt_path.write_bytes(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("ascii"))
    checkpoint_path.write_bytes(json.dumps(checkpoint, sort_keys=True, separators=(",", ":")).encode("ascii"))
    if mutation == "missing":
        receipt_path.unlink()
    elif mutation == "tampered":
        receipt_path.write_bytes(receipt_path.read_bytes() + b" ")
    else:
        checkpoint["revocation_receipt_digests"] = ["c" * 64]
        checkpoint_path.write_bytes(json.dumps(checkpoint, sort_keys=True, separators=(",", ":")).encode("ascii"))
    command = [
        sys.executable, "-m", "memorii.tools.semantic_ingestion_revocation_publish",
        "--root", str(root), "--prior-approval-release-digest", release,
        "--receipt", str(receipt_path), "--checkpoint", str(checkpoint_path),
    ]
    result = subprocess.run(
        command, cwd=Path(__file__).parents[4],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[4] / "memorii")},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert not (root / "current" / f"{release}.json").exists()
    # An exact retry after correcting the original bytes remains possible.
    receipt_path.write_bytes(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("ascii"))
    checkpoint["revocation_receipt_digests"] = [receipt_digest]
    checkpoint_path.write_bytes(json.dumps(checkpoint, sort_keys=True, separators=(",", ":")).encode("ascii"))
    repaired = subprocess.run(
        command, cwd=Path(__file__).parents[4],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[4] / "memorii")},
        capture_output=True, text=True, check=False,
    )
    assert repaired.returncode == 0, repaired.stderr
    assert (root / "current" / f"{release}.json").exists()
