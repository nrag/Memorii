"""Deterministic, server-clocked capability monitoring authority.

The immutable capability registry remains an identifier/fingerprint snapshot.
This module owns the separately persisted mutable status record and never
derives a policy, clock, or activation from traffic.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, localcontext
from hashlib import sha256
from typing import Any, Literal, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.ingestion_contracts import SemanticWriterCommitBinding
from memorii.core.memory_evolution.writer_admission import SemanticWriterAdmissionStore
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import (
    MemoryPlaneRevisionConflictError,
    RecordAbsentPrecondition,
    RecordDigestPrecondition,
    record_digest,
)
from memorii.core.semantic_ingestion.contracts import contract_digest
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility

CAPABILITY_MONITOR_SEQUENTIAL_IMPLEMENTATION_FINGERPRINT = sha256(
    b"memorii.capability-monitor.inverse-quadratic-hoeffding-cs.v1"
).hexdigest()
_ModelT = TypeVar("_ModelT", bound=BaseModel)


def _digest(domain: bytes, value: BaseModel, field: str) -> str:
    return contract_digest(domain, value.model_dump(mode="python", exclude={field}))


def _create_digest_bound(
    model: type[_ModelT],
    *,
    domain: bytes,
    digest_field: str,
    values: Mapping[str, Any],
) -> _ModelT:
    partial = model.model_construct(**values)
    digest = contract_digest(
        domain, partial.model_dump(mode="python", exclude={digest_field})
    )
    return model.model_validate({**values, digest_field: digest})


def _status_id(capability_fingerprint: str) -> str:
    return "semantic_ingestion:capability-status:" + capability_fingerprint


def _authorization_checkpoint_id(capability_fingerprint: str) -> str:
    return "semantic_ingestion:capability-authorization-checkpoint:" + capability_fingerprint


def _decision_outcome_id(
    decision: CapabilityMonitoringDecision,
    freshness: CapabilityEvidenceFreshness,
) -> str:
    body: dict[str, object] = {
        "capability_fingerprint": decision.capability_fingerprint,
        "monitoring_policy_digest": decision.monitoring_policy_digest,
        "evidence_window_digest": decision.evidence_window_digest,
        "metric_decision_digests": tuple(
            item.decision_digest for item in decision.metric_decisions
        ),
        "evidence_freshness": decision.evidence_freshness,
        "freshness_reason": freshness.freshness_reason,
        "action": decision.action,
        "reason_codes": decision.reason_codes,
    }
    if decision.schema_version == 1:
        return contract_digest(
            b"memorii.semantic-ingestion.capability-monitor-outcome.v1", body
        )
    body["schema_version"] = decision.schema_version
    body["evaluation_kind"] = decision.evaluation_kind
    return contract_digest(
        b"memorii.semantic-ingestion.capability-monitor-outcome.v2", body
    )


def _decimal(value: str) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("monitoring numeric value is invalid") from exc
    if not result.is_finite():
        raise ValueError("monitoring numeric value must be finite")
    return result


def _wire_datetime(value: object) -> object:
    if not isinstance(value, str):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value


def _classify_historical_wire(
    value: object,
    *,
    pre_field_keys: frozenset[str],
    extended_v1_keys: frozenset[str],
    v2_keys: frozenset[str],
) -> tuple[dict[str, object], Literal["pre_field_v1", "extended_v1", "v2"]]:
    """Derive the authenticated wire generation from its exact persisted shape.

    ``wire_generation`` is an in-memory decoding aid, never a persisted
    authority coordinate.  In particular, an attacker cannot turn a historical
    pre-field payload into an extended shape by supplying a helper field.
    """
    if not isinstance(value, dict):
        raise ValueError("capability monitoring wire payload is invalid")
    if "wire_generation" in value:
        raise ValueError("capability monitoring wire generation is derived")
    keys = frozenset(value)
    if "schema_version" in value:
        if value["schema_version"] != 2 or keys != v2_keys:
            raise ValueError("capability monitoring v2 wire shape is invalid")
        return dict(value), "v2"
    if keys == pre_field_keys:
        return {**value, "schema_version": 1}, "pre_field_v1"
    if keys == extended_v1_keys:
        return {**value, "schema_version": 1}, "extended_v1"
    raise ValueError("capability monitoring historical wire shape is invalid")


def _canonical_decimal(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _confidence_bounds(
    values: tuple[Decimal, ...], *, lower: Decimal, upper: Decimal, alpha: Decimal
) -> tuple[Decimal, Decimal, Decimal]:
    """A time-uniform Hoeffding sequence via an inverse-quadratic alpha union bound."""
    count = Decimal(len(values))
    with localcontext() as context:
        context.prec = 50
        estimate = sum(values, Decimal(0)) / count
        allocated_alpha = alpha / (count * (count + 1))
        radius = (upper - lower) * (((Decimal(2) / allocated_alpha).ln() / (Decimal(2) * count)).sqrt())
        return estimate, max(lower, estimate - radius), min(upper, estimate + radius)


class SequentialTestManifest(BaseModel):
    method: Literal["time_uniform_confidence_sequence"]
    bounded_value_lower: str
    bounded_value_upper: str
    spending_rule_id: str = Field(min_length=1)
    implementation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def _valid(self) -> SequentialTestManifest:
        if (
            _decimal(self.bounded_value_lower) >= _decimal(self.bounded_value_upper)
            or self.spending_rule_id != "inverse_quadratic_union_bound_v1"
            or self.implementation_fingerprint != CAPABILITY_MONITOR_SEQUENTIAL_IMPLEMENTATION_FINGERPRINT
        ):
            raise ValueError("sequential test bounds are invalid")
        if self.manifest_digest != _digest(
            b"memorii.semantic-ingestion.monitor-sequential-test.v1", self, "manifest_digest"
        ):
            raise ValueError("sequential test manifest digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> SequentialTestManifest:
        return _create_digest_bound(
            cls,
            domain=b"memorii.semantic-ingestion.monitor-sequential-test.v1",
            digest_field="manifest_digest",
            values=values,
        )


class MonitoringMetricGate(BaseModel):
    metric_id: str = Field(min_length=1)
    direction: Literal["upper", "lower"]
    warning_threshold: str
    breach_threshold: str
    minimum_independent_clusters: int = Field(ge=1)
    maximum_label_delay: timedelta
    alpha_budget: str
    gate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def _valid(self) -> MonitoringMetricGate:
        alpha = _decimal(self.alpha_budget)
        if (
            not 0 < alpha <= 1
            or self.maximum_label_delay <= timedelta(0)
            or (self.direction == "upper" and _decimal(self.warning_threshold) > _decimal(self.breach_threshold))
            or (self.direction == "lower" and _decimal(self.warning_threshold) < _decimal(self.breach_threshold))
        ):
            raise ValueError("monitoring metric gate is invalid")
        if self.gate_digest != _digest(b"memorii.semantic-ingestion.monitoring-metric-gate.v1", self, "gate_digest"):
            raise ValueError("monitoring metric gate digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> MonitoringMetricGate:
        return _create_digest_bound(
            cls,
            domain=b"memorii.semantic-ingestion.monitoring-metric-gate.v1",
            digest_field="gate_digest",
            values=values,
        )


class CapabilityMonitoringPolicy(BaseModel):
    capability_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    monitoring_policy_revision: str = Field(min_length=1)
    maximum_independent_label_age: timedelta
    maximum_canary_success_age: timedelta
    minimum_labeled_clusters_per_window: int = Field(ge=1)
    label_window: timedelta
    paused_traffic_grace_period: timedelta
    label_pipeline_outage_grace_period: timedelta
    stale_evidence_action: Literal["evidence_only"]
    metric_gates: tuple[MonitoringMetricGate, ...]
    family_wise_alpha_budget: str
    sequential_test_manifest: SequentialTestManifest
    breach_action: Literal["evidence_only"]
    policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def _valid(self) -> CapabilityMonitoringPolicy:
        gates = self.metric_gates
        if (
            not gates
            or gates != tuple(sorted(gates, key=lambda gate: gate.metric_id))
            or len({gate.metric_id for gate in gates}) != len(gates)
            or not 0 < _decimal(self.family_wise_alpha_budget) <= 1
            or sum((_decimal(gate.alpha_budget) for gate in gates), Decimal(0))
            > _decimal(self.family_wise_alpha_budget)
            or any(
                value <= timedelta(0)
                for value in (
                    self.maximum_independent_label_age,
                    self.maximum_canary_success_age,
                    self.label_window,
                    self.paused_traffic_grace_period,
                    self.label_pipeline_outage_grace_period,
                )
            )
        ):
            raise ValueError("capability monitoring policy is invalid")
        if self.policy_digest != _digest(
            b"memorii.semantic-ingestion.capability-monitoring-policy.v1", self, "policy_digest"
        ):
            raise ValueError("capability monitoring policy digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> CapabilityMonitoringPolicy:
        return _create_digest_bound(
            cls,
            domain=b"memorii.semantic-ingestion.capability-monitoring-policy.v1",
            digest_field="policy_digest",
            values=values,
        )


class MonitoringObservation(BaseModel):
    event_id: str = Field(min_length=1)
    metric_id: str = Field(min_length=1)
    cluster_id: str = Field(min_length=1)
    observed_at: datetime
    value: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def _valid(self) -> MonitoringObservation:
        if self.observed_at.utcoffset() is None:
            raise ValueError("monitoring observation is invalid")
        _decimal(self.value)
        return self


class CapabilityEvidenceWindow(BaseModel):
    capability_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    monitoring_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    sequential_implementation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    observations: tuple[MonitoringObservation, ...]
    latest_independent_label_at: datetime | None
    latest_canary_success_at: datetime | None
    traffic_state: Literal["active", "paused"]
    traffic_state_changed_at: datetime
    label_pipeline_state: Literal["healthy", "outage"]
    label_pipeline_state_changed_at: datetime
    evidence_window_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def _valid(self) -> CapabilityEvidenceWindow:
        times = (
            self.traffic_state_changed_at,
            self.label_pipeline_state_changed_at,
            self.latest_independent_label_at,
            self.latest_canary_success_at,
        )
        if any(value is not None and value.utcoffset() is None for value in times):
            raise ValueError("capability evidence time is naive")
        keys = tuple((item.metric_id, item.cluster_id) for item in self.observations)
        clusters = tuple(item.cluster_id for item in self.observations)
        events = tuple(item.event_id for item in self.observations)
        if len(set(keys)) != len(keys) or len(set(clusters)) != len(clusters) or len(set(events)) != len(events):
            raise ValueError("monitoring clusters are duplicate or cross-assigned")
        if self.evidence_window_digest != _digest(
            b"memorii.semantic-ingestion.capability-evidence-window.v1", self, "evidence_window_digest"
        ):
            raise ValueError("capability evidence window digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> CapabilityEvidenceWindow:
        return _create_digest_bound(
            cls,
            domain=b"memorii.semantic-ingestion.capability-evidence-window.v1",
            digest_field="evidence_window_digest",
            values=values,
        )


class CapabilityEvidenceFreshness(BaseModel):
    schema_version: Literal[1, 2] = 2
    wire_generation: Literal["pre_field_v1", "extended_v1", "v2"] = Field(
        default="v2", exclude=True
    )
    capability_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    monitoring_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluated_at: datetime
    latest_independent_label_at: datetime | None
    latest_canary_success_at: datetime | None
    labeled_cluster_count_in_window: int = Field(ge=0)
    traffic_state: Literal["active", "paused"]
    traffic_state_changed_at: datetime
    label_pipeline_state: Literal["healthy", "outage"]
    label_pipeline_state_changed_at: datetime
    freshness: Literal["fresh", "grace", "stale"]
    freshness_reason: str = Field(min_length=1)
    status_revision: str = Field(min_length=1)
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="before")
    @classmethod
    def _upcast_legacy(cls, value: object) -> object:
        pre_keys = frozenset({
            "capability_fingerprint", "monitoring_policy_digest", "evaluated_at",
            "latest_independent_label_at", "latest_canary_success_at",
            "labeled_cluster_count_in_window", "traffic_state",
            "label_pipeline_state", "freshness", "freshness_reason",
            "status_revision", "evidence_digest",
        })
        extended_keys = pre_keys | frozenset({
            "traffic_state_changed_at", "label_pipeline_state_changed_at",
        })
        v2_keys = extended_keys | frozenset({"schema_version"})
        decoded, generation = _classify_historical_wire(
            value, pre_field_keys=pre_keys, extended_v1_keys=extended_keys,
            v2_keys=v2_keys,
        )
        if generation == "pre_field_v1":
            # V1 did not persist the state-transition instants. Retain the
            # original digest and fence deadline-derived uses below.
            decoded["traffic_state_changed_at"] = decoded["evaluated_at"]
            decoded["label_pipeline_state_changed_at"] = decoded["evaluated_at"]
        decoded["wire_generation"] = generation
        return {
            **decoded,
            **{
                field: _wire_datetime(decoded.get(field))
                for field in (
                    "evaluated_at", "latest_independent_label_at",
                    "latest_canary_success_at", "traffic_state_changed_at",
                    "label_pipeline_state_changed_at",
                )
            },
        }

    @model_validator(mode="after")
    def _valid(self) -> CapabilityEvidenceFreshness:
        body = self.model_dump(mode="python", exclude={"evidence_digest"})
        domain = b"memorii.semantic-ingestion.capability-evidence-freshness.v2"
        if self.schema_version == 1:
            body.pop("schema_version")
            if self.wire_generation == "pre_field_v1":
                body.pop("traffic_state_changed_at")
                body.pop("label_pipeline_state_changed_at")
            domain = b"memorii.semantic-ingestion.capability-evidence-freshness.v1"
        if any(value.utcoffset() is None for value in (self.evaluated_at, self.traffic_state_changed_at, self.label_pipeline_state_changed_at)) or self.evidence_digest != contract_digest(
            domain, body
        ):
            raise ValueError("capability evidence freshness is invalid")
        return self


class MonitoringMetricDecision(BaseModel):
    metric_id: str
    independent_cluster_count: int = Field(ge=0)
    estimate: str | None
    lower_bound: str | None
    upper_bound: str | None
    alpha_spent: str
    status: Literal["insufficient_data", "healthy", "warning", "breach"]
    decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def _valid(self) -> MonitoringMetricDecision:
        if self.decision_digest != _digest(
            b"memorii.semantic-ingestion.monitoring-metric-decision.v1",
            self,
            "decision_digest",
        ):
            raise ValueError("monitoring metric decision digest mismatch")
        return self


class CapabilityMonitoringDecision(BaseModel):
    schema_version: Literal[1, 2] = 2
    wire_generation: Literal["pre_field_v1", "extended_v1", "v2"] = Field(
        default="v2", exclude=True
    )
    capability_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    monitoring_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_window_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluated_at: datetime
    metric_decisions: tuple[MonitoringMetricDecision, ...]
    evidence_freshness: Literal["fresh", "grace", "stale"]
    evaluation_kind: Literal["evidence_window", "missing_window", "provider_failure", "authorization_failure"] = "evidence_window"
    action: Literal["remain_active", "evidence_only"]
    reason_codes: tuple[str, ...]
    decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="before")
    @classmethod
    def _upcast_legacy(cls, value: object) -> object:
        pre_keys = frozenset({
            "capability_fingerprint", "monitoring_policy_digest",
            "evidence_window_digest", "evaluated_at", "metric_decisions",
            "evidence_freshness", "action", "reason_codes", "decision_digest",
        })
        extended_keys = pre_keys | frozenset({"evaluation_kind"})
        v2_keys = extended_keys | frozenset({"schema_version"})
        decoded, generation = _classify_historical_wire(
            value, pre_field_keys=pre_keys, extended_v1_keys=extended_keys,
            v2_keys=v2_keys,
        )
        if generation == "pre_field_v1":
            decoded["evaluation_kind"] = "evidence_window"
        decoded["wire_generation"] = generation
        metric_decisions = decoded.get("metric_decisions")
        reason_codes = decoded.get("reason_codes")
        if isinstance(metric_decisions, (list, tuple)):
            decoded["metric_decisions"] = tuple(metric_decisions)
        if isinstance(reason_codes, (list, tuple)):
            decoded["reason_codes"] = tuple(reason_codes)
        return {
            **decoded,
            "evaluated_at": _wire_datetime(decoded.get("evaluated_at")),
        }

    @model_validator(mode="after")
    def _valid(self) -> CapabilityMonitoringDecision:
        if (
            self.evaluated_at.utcoffset() is None
            or self.reason_codes != tuple(sorted(set(self.reason_codes)))
            or self.metric_decisions != tuple(sorted(self.metric_decisions, key=lambda item: item.metric_id))
            or self.decision_digest != contract_digest(
                (b"memorii.semantic-ingestion.capability-monitoring-decision.v1"
                 if self.schema_version == 1 else b"memorii.semantic-ingestion.capability-monitoring-decision.v2"),
                self.model_dump(
                    mode="python", exclude=(
                        ({"decision_digest", "schema_version", "evaluation_kind"}
                         if self.wire_generation == "pre_field_v1"
                         else {"decision_digest", "schema_version"})
                        if self.schema_version == 1 else {"decision_digest"}
                    ),
                ),
            )
        ):
            raise ValueError("capability monitoring decision is invalid")
        return self


class CapabilityStatus(BaseModel):
    schema_version: Literal[1, 2] = 2
    wire_generation: Literal["pre_field_v1", "extended_v1", "v2"] = Field(
        default="v2", exclude=True
    )
    capability_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["active", "evidence_only"]
    status_revision: int = Field(ge=1)
    monitoring_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_freshness_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_checkpoint_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    status_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="before")
    @classmethod
    def _upcast_legacy(cls, value: object) -> object:
        pre_keys = frozenset({
            "capability_fingerprint", "status", "status_revision",
            "monitoring_policy_digest", "evidence_freshness_digest",
            "status_digest",
        })
        extended_keys = pre_keys | frozenset({"authorization_checkpoint_digest"})
        v2_keys = extended_keys | frozenset({"schema_version"})
        decoded, generation = _classify_historical_wire(
            value, pre_field_keys=pre_keys, extended_v1_keys=extended_keys,
            v2_keys=v2_keys,
        )
        if generation == "pre_field_v1":
            decoded["authorization_checkpoint_digest"] = None
        decoded["wire_generation"] = generation
        return decoded

    @model_validator(mode="after")
    def _valid(self) -> CapabilityStatus:
        body = self.model_dump(mode="python", exclude={"status_digest"})
        domain = b"memorii.semantic-ingestion.capability-status.v2"
        if self.schema_version == 1:
            body.pop("schema_version")
            if self.wire_generation == "pre_field_v1":
                body.pop("authorization_checkpoint_digest")
            domain = b"memorii.semantic-ingestion.capability-status.v1"
        if self.status_digest != contract_digest(domain, body):
            raise ValueError("capability status digest mismatch")
        return self


class CapabilityAuthorizationCheckpoint(BaseModel):
    capability_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    monitoring_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    deployment_authorization_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    deployment_artifact_raw_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_release_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at: datetime
    signer_subject_id: str = Field(min_length=1)
    signing_key_reference: str = Field(min_length=1)
    authority_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    active_epoch: int = Field(ge=1)
    checkpoint_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def _valid(self) -> CapabilityAuthorizationCheckpoint:
        if self.expires_at.utcoffset() is None or self.checkpoint_digest != _digest(
            b"memorii.semantic-ingestion.capability-authorization-checkpoint.v1", self, "checkpoint_digest"
        ):
            raise ValueError("capability authorization checkpoint is invalid")
        return self


@dataclass(frozen=True)
class CapabilityMonitorTickResult:
    decision: CapabilityMonitoringDecision
    freshness: CapabilityEvidenceFreshness
    status: CapabilityStatus
    writer_binding: SemanticWriterCommitBinding | None


class CapabilityEvidenceWindowProvider(Protocol):
    """Host scheduler port returning immutable windows ready for evaluation."""

    def load_evidence_windows(
        self, *, max_items: int
    ) -> tuple[CapabilityEvidenceWindow, ...]: ...


class CapabilityMonitor:
    """Evaluates only caller-supplied, content-bound policy and evidence."""

    def __init__(
        self,
        *,
        writers: SemanticWriterAdmissionStore,
        now: Callable[[], datetime],
        policies: tuple[CapabilityMonitoringPolicy, ...],
        authorization_checkpoints: tuple[CapabilityAuthorizationCheckpoint, ...] = (),
    ) -> None:
        if len({policy.capability_fingerprint for policy in policies}) != len(policies):
            raise ValueError("capability monitoring policies are duplicate")
        self._writers = writers
        self._now = now
        self._policies = {policy.capability_fingerprint: policy for policy in policies}
        if len({item.capability_fingerprint for item in authorization_checkpoints}) != len(authorization_checkpoints):
            raise ValueError("capability authorization checkpoints are duplicate")
        self._authorization_checkpoints = {item.capability_fingerprint: item for item in authorization_checkpoints}
        self._write_capability = writers._register_atomic_owner()

    @property
    def configured_capability_fingerprints(self) -> tuple[str, ...]:
        """Return the complete deterministic scheduler inventory."""
        return tuple(sorted(self._policies))

    def tick_missing_window(
        self,
        *,
        capability_fingerprint: str,
        provider_failure: bool = False,
        provider_failure_reason: str | None = None,
    ) -> CapabilityMonitorTickResult | None:
        """Fail closed once the last durable freshness coordinate reaches its deadline.

        A scheduler outage must not leave an active capability indefinitely
        admitted merely because no host window was returned.  The stored
        freshness record is the only authority used to derive the deadline.
        """
        policy = self._policies.get(capability_fingerprint)
        if policy is None:
            raise ValueError("capability monitoring policy is unavailable")
        current_record = self._writers._memory_plane.get_record(_status_id(capability_fingerprint))
        if current_record is None:
            raise ValueError("capability status authority is unavailable")
        current = CapabilityStatus.model_validate(current_record.content["status"])
        if current.status == "evidence_only":
            return None
        freshness = self._load_current_freshness(current.evidence_freshness_digest)
        if freshness.wire_generation == "pre_field_v1":
            # The old wire shape has no durable transition instants, so its
            # pause/outage grace cannot be reconstructed safely after restart.
            return self.demote_untrusted_authority(
                capability_fingerprint=capability_fingerprint
            )
        now = self._now()
        if now.utcoffset() is None:
            raise ValueError("capability monitor clock must be timezone-aware")
        if freshness.latest_independent_label_at is None or freshness.latest_canary_success_at is None:
            raise ValueError("capability monitor active freshness authority is incomplete")
        deadlines = [
            freshness.latest_independent_label_at + policy.maximum_independent_label_age,
            freshness.latest_canary_success_at + policy.maximum_canary_success_age,
        ]
        if freshness.traffic_state == "paused":
            deadlines.append(
                freshness.traffic_state_changed_at + policy.paused_traffic_grace_period
            )
        if freshness.label_pipeline_state == "outage":
            deadlines.append(
                freshness.label_pipeline_state_changed_at
                + policy.label_pipeline_outage_grace_period
            )
        if now < min(deadlines):
            return None
        missing = CapabilityEvidenceWindow.create(
            capability_fingerprint=capability_fingerprint,
            monitoring_policy_digest=policy.policy_digest,
            sequential_implementation_fingerprint=policy.sequential_test_manifest.implementation_fingerprint,
            observations=(),
            latest_independent_label_at=freshness.latest_independent_label_at,
            latest_canary_success_at=freshness.latest_canary_success_at,
            traffic_state=freshness.traffic_state,
            traffic_state_changed_at=freshness.traffic_state_changed_at,
            label_pipeline_state=freshness.label_pipeline_state,
            label_pipeline_state_changed_at=freshness.label_pipeline_state_changed_at,
        )
        return self.tick(
            evidence=missing,
            evaluation_kind=("provider_failure" if provider_failure else "missing_window"),
            provider_failure_reason=provider_failure_reason,
        )

    def demote_untrusted_authority(self, *, capability_fingerprint: str) -> CapabilityMonitorTickResult | None:
        """Fence an active writer immediately when live deployment trust fails."""
        policy = self._policies.get(capability_fingerprint)
        if policy is None:
            raise ValueError("capability monitoring policy is unavailable")
        current_record = self._writers._memory_plane.get_record(_status_id(capability_fingerprint))
        if current_record is None:
            raise ValueError("capability status authority is unavailable")
        current = CapabilityStatus.model_validate(current_record.content["status"])
        if current.status == "evidence_only":
            return None
        now = self._now()
        if now.utcoffset() is None:
            raise ValueError("capability monitor clock must be timezone-aware")
        # A future authority timestamp is a closed, typed invalid-evidence
        # coordinate and forces the normal atomic demotion path.
        invalid_at = now + timedelta(microseconds=1)
        return self.tick(evidence=CapabilityEvidenceWindow.create(
            capability_fingerprint=capability_fingerprint,
            monitoring_policy_digest=policy.policy_digest,
            sequential_implementation_fingerprint=policy.sequential_test_manifest.implementation_fingerprint,
            observations=(), latest_independent_label_at=invalid_at,
            latest_canary_success_at=invalid_at, traffic_state="active",
            traffic_state_changed_at=now, label_pipeline_state="healthy",
            label_pipeline_state_changed_at=now,
        ), evaluation_kind="authorization_failure")

    def _load_current_freshness(self, digest: str) -> CapabilityEvidenceFreshness:
        records = (*self._writers._memory_plane.list_records(source_kind="semantic_ingestion_capability_initial_freshness"), *self._writers._memory_plane.list_records(source_kind="semantic_ingestion_capability_monitor_decision"))
        for record in records:
            value = record.content.get("freshness")
            if value is None:
                continue
            try:
                freshness = CapabilityEvidenceFreshness.model_validate_json(
                    json.dumps(value)
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("capability monitor freshness authority is corrupt") from exc
            if record_digest(record) == digest or freshness.evidence_digest == digest:
                return freshness
        raise ValueError("capability monitor freshness authority is unavailable")

    def _initialize_active_status(
        self,
        *,
        capability_fingerprint: str,
        evidence_freshness_digest: str,
        freshness_record: CanonicalMemoryRecord,
    ) -> CapabilityStatus:
        """Persist one validated baseline freshness/status pair atomically."""
        policy = self._policies.get(capability_fingerprint)
        if policy is None:
            raise ValueError("capability monitoring policy is unavailable")
        checkpoint = self._authorization_checkpoints.get(capability_fingerprint)
        checkpoint_record = None
        if checkpoint is not None:
            checkpoint_record = CanonicalMemoryRecord(
                memory_id=_authorization_checkpoint_id(capability_fingerprint), domain=MemoryDomain.EXECUTION,
                text="", content={"semantic_ingestion_kind": "capability_authorization_checkpoint", "checkpoint": checkpoint.model_dump(mode="json")},
                status=CommitStatus.COMMITTED, source_kind="semantic_ingestion_capability_authorization_checkpoint",
                timestamp=self._now(), visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
            )
        base = {
            "capability_fingerprint": capability_fingerprint,
            "status": "active",
            "status_revision": 1,
            "monitoring_policy_digest": policy.policy_digest,
            "evidence_freshness_digest": evidence_freshness_digest,
            "authorization_checkpoint_digest": record_digest(checkpoint_record) if checkpoint_record is not None else None,
        }
        status = CapabilityStatus(
            **base,
            schema_version=2,
            status_digest=contract_digest(
                b"memorii.semantic-ingestion.capability-status.v2",
                {"schema_version": 2, **base},
            ),
        )
        record = CanonicalMemoryRecord(
            memory_id=_status_id(capability_fingerprint),
            domain=MemoryDomain.EXECUTION,
            text="",
            content={"semantic_ingestion_kind": "capability_status", "status": status.model_dump(mode="json")},
            status=CommitStatus.COMMITTED,
            source_kind="semantic_ingestion_capability_status",
            timestamp=self._now(),
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )
        existing = self._writers._memory_plane.get_record(record.memory_id)
        if existing is not None:
            loaded = CapabilityStatus.model_validate(existing.content["status"])
            if (
                loaded.status != "active"
                or loaded.capability_fingerprint != status.capability_fingerprint
                or loaded.monitoring_policy_digest != status.monitoring_policy_digest
            ):
                raise ValueError("capability status is already bound differently")
            if loaded.schema_version == 2:
                if (
                    loaded.authorization_checkpoint_digest
                    != status.authorization_checkpoint_digest
                ):
                    raise ValueError("capability status is already bound differently")
                persisted_freshness = self._writers._memory_plane.get_record(
                    freshness_record.memory_id
                )
                if (
                    persisted_freshness is None
                    or record_digest(persisted_freshness)
                    != record_digest(freshness_record)
                ):
                    raise ValueError("capability initial freshness authority is unavailable")
            else:
                # Historical V1 active records predate either the durable
                # checkpoint or the V2 freshness preimage.  They remain
                # readable so public ingress can fence them and the scheduler
                # can make the monotonic successor without inventing a new
                # baseline under the old record.
                persisted_freshness = next(
                    (
                        candidate
                        for candidate in self._writers._memory_plane.list_records(
                            source_kind="semantic_ingestion_capability_initial_freshness"
                        )
                        if record_digest(candidate)
                        == loaded.evidence_freshness_digest
                    ),
                    None,
                )
                if persisted_freshness is None:
                    raise ValueError("capability initial freshness authority is unavailable")
            if loaded.authorization_checkpoint_digest is not None:
                persisted_checkpoint = self._writers._memory_plane.get_record(
                    _authorization_checkpoint_id(capability_fingerprint)
                )
                if (
                    persisted_checkpoint is None
                    or record_digest(persisted_checkpoint)
                    != loaded.authorization_checkpoint_digest
                ):
                    raise ValueError("capability authorization checkpoint is unavailable")
            return loaded
        authorization = self._writers._authorize_atomic(
            self._writers.commit_binding(self._writers.current()),
            capability=self._write_capability,
        )
        try:
            self._writers._memory_plane.conditionally_write_records(
                (freshness_record, *( (checkpoint_record,) if checkpoint_record is not None else ()), record),
                preconditions=(
                    RecordAbsentPrecondition(memory_id=freshness_record.memory_id),
                    *( (RecordAbsentPrecondition(memory_id=checkpoint_record.memory_id),) if checkpoint_record is not None else ()),
                    RecordAbsentPrecondition(memory_id=record.memory_id),
                ),
                authorization=authorization,
            )
        except MemoryPlaneRevisionConflictError as exc:
            existing = self._writers._memory_plane.get_record(record.memory_id)
            if existing is None:
                raise ValueError("capability status initialization conflicted") from exc
            loaded = CapabilityStatus.model_validate(existing.content["status"])
            if loaded != status:
                raise ValueError("capability status is already bound differently") from exc
            persisted_freshness = self._writers._memory_plane.get_record(
                freshness_record.memory_id
            )
            if (
                persisted_freshness is None
                or record_digest(persisted_freshness) != record_digest(freshness_record)
            ):
                raise ValueError(
                    "capability initial freshness authority is unavailable"
                ) from exc
            return loaded
        return status

    def initialize_active_from_verified_evidence(
        self, *, evidence: CapabilityEvidenceWindow
    ) -> CapabilityStatus:
        """Create active status only from a fresh, sufficient baseline window."""

        evidence = CapabilityEvidenceWindow.model_validate_json(
            evidence.model_dump_json()
        )
        now = self._now()
        if now.utcoffset() is None:
            raise ValueError("capability monitor clock must be timezone-aware")
        policy = self._policies.get(evidence.capability_fingerprint)
        if policy is None or evidence.monitoring_policy_digest != policy.policy_digest:
            raise ValueError("capability monitor policy/evidence mismatch")
        freshness = self._freshness(policy, evidence, now, status_revision="1")
        metrics = tuple(self._metric(policy, gate, evidence) for gate in policy.metric_gates)
        declared_metrics = {gate.metric_id for gate in policy.metric_gates}
        invalid = (
            freshness.freshness != "fresh"
            or any(item.status in {"insufficient_data", "breach"} for item in metrics)
            or any(item.metric_id not in declared_metrics for item in evidence.observations)
            or any(item.observed_at > now for item in evidence.observations)
        )
        if invalid:
            raise ValueError("capability initial evidence is not fresh and acceptable")
        freshness_record = CanonicalMemoryRecord(
            memory_id=(
                "semantic_ingestion:capability-initial-freshness:"
                + freshness.evidence_digest
            ),
            domain=MemoryDomain.EXECUTION,
            text="",
            content={
                "semantic_ingestion_kind": "capability_initial_freshness",
                "evidence_window_digest": evidence.evidence_window_digest,
                "freshness": freshness.model_dump(mode="json"),
                "metric_decisions": tuple(
                    item.model_dump(mode="json") for item in metrics
                ),
            },
            status=CommitStatus.COMMITTED,
            source_kind="semantic_ingestion_capability_initial_freshness",
            timestamp=now,
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )
        return self._initialize_active_status(
            capability_fingerprint=policy.capability_fingerprint,
            evidence_freshness_digest=record_digest(freshness_record),
            freshness_record=freshness_record,
        )

    def tick(
        self,
        *,
        evidence: CapabilityEvidenceWindow,
        evaluation_kind: Literal[
            "evidence_window", "missing_window", "provider_failure", "authorization_failure"
        ] = "evidence_window",
        provider_failure_reason: str | None = None,
    ) -> CapabilityMonitorTickResult:
        evidence = CapabilityEvidenceWindow.model_validate_json(
            evidence.model_dump_json()
        )
        now = self._now()
        if now.utcoffset() is None:
            raise ValueError("capability monitor clock must be timezone-aware")
        policy = self._policies.get(evidence.capability_fingerprint)
        if policy is None or evidence.monitoring_policy_digest != policy.policy_digest:
            raise ValueError("capability monitor policy/evidence mismatch")
        current_record = self._writers._memory_plane.get_record(_status_id(policy.capability_fingerprint))
        if current_record is None:
            raise ValueError("capability status authority is unavailable")
        current = CapabilityStatus.model_validate(current_record.content["status"])
        if (
            current.capability_fingerprint != policy.capability_fingerprint
            or current.monitoring_policy_digest != policy.policy_digest
        ):
            raise ValueError("capability monitor current policy is mismatched")
        freshness = self._freshness(policy, evidence, now, status_revision=str(current.status_revision))
        metrics = tuple(self._metric(policy, gate, evidence) for gate in policy.metric_gates)
        reasons_list: list[str] = []
        if provider_failure_reason is not None:
            if evaluation_kind != "provider_failure" or provider_failure_reason not in {
                "provider_failure_known_exception",
                "provider_failure_unexpected_exception",
                "provider_failure_non_tuple",
                "provider_failure_non_window",
                "provider_failure_unknown_capability",
                "provider_failure_duplicate_capability",
                "provider_failure_oversized_result",
            }:
                raise ValueError("capability monitor provider failure diagnostic is invalid")
            reasons_list.append(provider_failure_reason)
        if freshness.freshness == "stale":
            reasons_list.append("stale_evidence")
        if any(item.status == "insufficient_data" for item in metrics):
            reasons_list.append("insufficient_metric_evidence")
        if any(item.status == "breach" for item in metrics):
            reasons_list.append("metric_breach")
        declared_metrics = {gate.metric_id for gate in policy.metric_gates}
        if any(item.metric_id not in declared_metrics for item in evidence.observations):
            reasons_list.append("unknown_metric")
        if any(item.observed_at > now for item in evidence.observations):
            reasons_list.append("future_observation")
        reasons = tuple(sorted(reasons_list))
        action: Literal["remain_active", "evidence_only"] = "evidence_only" if reasons else "remain_active"
        decision_base = {
            "capability_fingerprint": policy.capability_fingerprint,
            "monitoring_policy_digest": policy.policy_digest,
            "evidence_window_digest": evidence.evidence_window_digest,
            "evaluated_at": now,
            "metric_decisions": metrics,
            "evidence_freshness": freshness.freshness,
            "evaluation_kind": evaluation_kind,
            "action": action,
            "reason_codes": reasons,
        }
        decision = CapabilityMonitoringDecision(
            **decision_base,
            schema_version=2,
            decision_digest=contract_digest(
                b"memorii.semantic-ingestion.capability-monitoring-decision.v2",
                {"schema_version": 2, **decision_base},
            ),
        )
        decision_record_id = (
            "semantic_ingestion:capability-monitor-decision:"
            + _decision_outcome_id(decision, freshness)
        )
        prior_decision_record = self._writers._memory_plane.get_record(decision_record_id)
        if prior_decision_record is not None:
            try:
                prior_decision = CapabilityMonitoringDecision.model_validate_json(
                    json.dumps(prior_decision_record.content["decision"])
                )
                prior_freshness = CapabilityEvidenceFreshness.model_validate_json(
                    json.dumps(prior_decision_record.content["freshness"])
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("capability monitor prior decision is corrupt") from exc
            if (
                _decision_outcome_id(prior_decision, prior_freshness)
                != decision_record_id.rsplit(":", 1)[1]
            ):
                raise ValueError("capability monitor decision identity is substituted")
            return CapabilityMonitorTickResult(
                prior_decision, prior_freshness, current, None
            )
        successor_status: Literal["active", "evidence_only"] = (
            "evidence_only" if action == "evidence_only" or current.status == "evidence_only" else "active"
        )
        successor_base = {
            "capability_fingerprint": current.capability_fingerprint,
            "status": successor_status,
            "status_revision": current.status_revision + 1,
            "monitoring_policy_digest": policy.policy_digest,
            "evidence_freshness_digest": freshness.evidence_digest,
            "authorization_checkpoint_digest": current.authorization_checkpoint_digest,
        }
        successor = CapabilityStatus(
            **successor_base,
            schema_version=2,
            status_digest=contract_digest(
                b"memorii.semantic-ingestion.capability-status.v2",
                {"schema_version": 2, **successor_base},
            ),
        )
        status_record = CanonicalMemoryRecord(
            memory_id=_status_id(policy.capability_fingerprint),
            domain=MemoryDomain.EXECUTION,
            text="",
            content={
                "semantic_ingestion_kind": "capability_status",
                "status": successor.model_dump(mode="json"),
                "previous_status_record_digest": record_digest(current_record),
            },
            status=CommitStatus.COMMITTED,
            source_kind="semantic_ingestion_capability_status",
            timestamp=now,
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )
        decision_record = CanonicalMemoryRecord(
            memory_id=decision_record_id,
            domain=MemoryDomain.EXECUTION,
            text="",
            content={
                "semantic_ingestion_kind": "capability_monitor_decision",
                "decision": decision.model_dump(mode="json"),
                "freshness": freshness.model_dump(mode="json"),
                "status_record_digest": record_digest(current_record),
            },
            status=CommitStatus.COMMITTED,
            source_kind="semantic_ingestion_capability_monitor_decision",
            timestamp=now,
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )
        expected = self._writers.commit_binding(self._writers.current())
        if current.status == "evidence_only" or action == "remain_active":
            writer_record = self._writers.require_current(expected)
            authorization = self._writers._authorize_atomic(expected, capability=self._write_capability)
            try:
                self._writers._memory_plane.conditionally_write_records(
                    (status_record, decision_record),
                    preconditions=(
                        RecordDigestPrecondition(
                            memory_id=current_record.memory_id,
                            expected_digest=record_digest(current_record),
                        ),
                        RecordDigestPrecondition(
                            memory_id=writer_record.memory_id,
                            expected_digest=record_digest(writer_record),
                        ),
                        RecordAbsentPrecondition(memory_id=decision_record.memory_id),
                    ),
                    authorization=authorization,
                )
            except MemoryPlaneRevisionConflictError as exc:
                raise ValueError("capability monitor CAS conflict requires reevaluation") from exc
            return CapabilityMonitorTickResult(decision, freshness, successor, None)
        try:
            writer = self._writers.demote_capability_monitor(
                expected=expected,
                status_record=status_record,
                decision_record=decision_record,
                expected_status_digest=record_digest(current_record),
                monitor_transition_digest=decision.decision_digest,
            )
        except MemoryPlaneRevisionConflictError as exc:
            raise ValueError("capability monitor CAS conflict requires reevaluation") from exc
        return CapabilityMonitorTickResult(decision, freshness, successor, self._writers.commit_binding(writer))

    @staticmethod
    def _freshness(
        policy: CapabilityMonitoringPolicy,
        evidence: CapabilityEvidenceWindow,
        now: datetime,
        *,
        status_revision: str,
    ) -> CapabilityEvidenceFreshness:
        eligible = tuple(
            item for item in evidence.observations if timedelta(0) <= now - item.observed_at <= policy.label_window
        )
        labels_fresh = (
            evidence.latest_independent_label_at is not None
            and now - evidence.latest_independent_label_at < policy.maximum_independent_label_age
        )
        canary_fresh = (
            evidence.latest_canary_success_at is not None
            and now - evidence.latest_canary_success_at < policy.maximum_canary_success_age
        )
        authority_times = (
            evidence.latest_independent_label_at,
            evidence.latest_canary_success_at,
            evidence.traffic_state_changed_at,
            evidence.label_pipeline_state_changed_at,
        )
        pause_expired = (
            evidence.traffic_state == "paused"
            and now - evidence.traffic_state_changed_at
            >= policy.paused_traffic_grace_period
        )
        outage_expired = (
            evidence.label_pipeline_state == "outage"
            and now - evidence.label_pipeline_state_changed_at
            >= policy.label_pipeline_outage_grace_period
        )
        if any(value is not None and value > now for value in authority_times):
            freshness, reason = "stale", "future_authority_timestamp"
        elif pause_expired:
            freshness, reason = "stale", "traffic_pause_expired"
        elif outage_expired:
            freshness, reason = "stale", "label_pipeline_outage_expired"
        elif not labels_fresh or len(eligible) < policy.minimum_labeled_clusters_per_window:
            freshness, reason = "stale", "independent_labels_stale_or_insufficient"
        elif not canary_fresh:
            freshness, reason = "stale", "canary_stale"
        elif evidence.label_pipeline_state == "outage":
            freshness, reason = "grace", "label_pipeline_outage_grace"
        elif evidence.traffic_state == "paused":
            freshness, reason = "grace", "traffic_pause_grace"
        else:
            freshness, reason = "fresh", "fresh"
        base = {
            "capability_fingerprint": policy.capability_fingerprint,
            "monitoring_policy_digest": policy.policy_digest,
            "evaluated_at": now,
            "latest_independent_label_at": evidence.latest_independent_label_at,
            "latest_canary_success_at": evidence.latest_canary_success_at,
            "labeled_cluster_count_in_window": len(eligible),
            "traffic_state": evidence.traffic_state,
            "traffic_state_changed_at": evidence.traffic_state_changed_at,
            "label_pipeline_state": evidence.label_pipeline_state,
            "label_pipeline_state_changed_at": evidence.label_pipeline_state_changed_at,
            "freshness": freshness,
            "freshness_reason": reason,
            "status_revision": status_revision,
        }
        return CapabilityEvidenceFreshness(
            **base,
            schema_version=2,
            evidence_digest=contract_digest(
                b"memorii.semantic-ingestion.capability-evidence-freshness.v2",
                {"schema_version": 2, **base},
            ),
        )

    @staticmethod
    def _metric(
        policy: CapabilityMonitoringPolicy, gate: MonitoringMetricGate, evidence: CapabilityEvidenceWindow
    ) -> MonitoringMetricDecision:
        latest_label = evidence.latest_independent_label_at
        rows = tuple(
            item
            for item in evidence.observations
            if item.metric_id == gate.metric_id
            and latest_label is not None
            and timedelta(0) <= latest_label - item.observed_at <= gate.maximum_label_delay
        )
        if (
            len(rows) < gate.minimum_independent_clusters
            or evidence.sequential_implementation_fingerprint
            != policy.sequential_test_manifest.implementation_fingerprint
        ):
            base = {
                "metric_id": gate.metric_id,
                "independent_cluster_count": len(rows),
                "estimate": None,
                "lower_bound": None,
                "upper_bound": None,
                "alpha_spent": gate.alpha_budget,
                "status": "insufficient_data",
            }
        else:
            values = tuple(_decimal(row.value) for row in rows)
            manifest = policy.sequential_test_manifest
            domain_lower = _decimal(manifest.bounded_value_lower)
            domain_upper = _decimal(manifest.bounded_value_upper)
            if any(value < domain_lower or value > domain_upper for value in values):
                base = {
                    "metric_id": gate.metric_id,
                    "independent_cluster_count": len(rows),
                    "estimate": None,
                    "lower_bound": None,
                    "upper_bound": None,
                    "alpha_spent": gate.alpha_budget,
                    "status": "insufficient_data",
                }
                return MonitoringMetricDecision(
                    **base,
                    decision_digest=contract_digest(b"memorii.semantic-ingestion.monitoring-metric-decision.v1", base),
                )
            estimate, lower, upper = _confidence_bounds(
                values,
                lower=domain_lower,
                upper=domain_upper,
                alpha=_decimal(gate.alpha_budget),
            )
            breach = (
                upper >= _decimal(gate.breach_threshold)
                if gate.direction == "upper"
                else lower <= _decimal(gate.breach_threshold)
            )
            warning = (
                upper >= _decimal(gate.warning_threshold)
                if gate.direction == "upper"
                else lower <= _decimal(gate.warning_threshold)
            )
            base = {
                "metric_id": gate.metric_id,
                "independent_cluster_count": len(rows),
                "estimate": _canonical_decimal(estimate),
                "lower_bound": _canonical_decimal(lower),
                "upper_bound": _canonical_decimal(upper),
                "alpha_spent": gate.alpha_budget,
                "status": "breach" if breach else "warning" if warning else "healthy",
            }
        return MonitoringMetricDecision(
            **base, decision_digest=contract_digest(b"memorii.semantic-ingestion.monitoring-metric-decision.v1", base)
        )


__all__ = [
    "CAPABILITY_MONITOR_SEQUENTIAL_IMPLEMENTATION_FINGERPRINT",
    "CapabilityEvidenceFreshness",
    "CapabilityEvidenceWindow",
    "CapabilityEvidenceWindowProvider",
    "CapabilityMonitor",
    "CapabilityMonitorTickResult",
    "CapabilityMonitoringDecision",
    "CapabilityMonitoringPolicy",
    "CapabilityStatus",
    "MonitoringMetricDecision",
    "MonitoringMetricGate",
    "MonitoringObservation",
    "SequentialTestManifest",
]
