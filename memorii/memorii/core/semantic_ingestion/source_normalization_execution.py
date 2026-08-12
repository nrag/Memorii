"""Closed, call-scoped execution owner for source-normalization publication.

This module deliberately contains no model, policy, or analyzer discovery.  A
composition root supplies sealed producers and a complete authority bundle.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from secrets import token_urlsafe
from threading import Lock
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.atomic_store import BootstrapWriterHandoffResult, OperationLeaseBinding
from memorii.core.memory_evolution.ingestion_contracts import OperationFenceBinding, SemanticWriterCommitBinding
from memorii.core.memory_evolution.semantic_analysis.decision_contracts import SourceNormalizationPublicationCoordinate
from memorii.core.semantic_ingestion.bootstrap_v3_interpreter import BootstrapV3GraphFreeInterpreter
from memorii.core.semantic_ingestion.contracts import (
    BootstrapAnalysisLaneResultV3,
    BootstrapAnalysisRouteBindingSet,
    BootstrapDeclaredSegmentLanguageRoute,
    BootstrapProposalRunPayloadV3,
    BootstrapRecoveryAbortedV3,
    BootstrapRecoveryClaimV3,
    BootstrapRecoveryKeyV3,
    BootstrapRecoveryRenewedV3,
    BootstrapSourceNormalizationResultV3,
    LanguageConstructionPolicyAuthorityBundle,
    PrePlanningSourceIngestionProgress,
    SegmentLanguageResourceBinding,
    SemanticProposalRun,
    SourceNormalizationResult,
    TemporalPolicySnapshot,
    TrustPolicySnapshot,
    contract_digest,
)
from memorii.core.semantic_ingestion.source_normalization_authority import (
    BootstrapV3RuntimeAuthority,
    CapabilityRegistrySnapshot,
    ConsensusPolicyAuthority,
    GraphDependentExecutionPolicy,
    ProposalRunProductionAuthority,
)
from memorii.core.semantic_ingestion.source_normalization_repository import SourceNormalizationStage
from memorii.core.semantic_ingestion.source_normalization_stage import (
    BootstrapV3SourceNormalizationInputs,
    BootstrapV3SourceNormalizationStage,
    GraphFreeSourceNormalizationInputs,
    GraphFreeSourceNormalizationInvocation,
    GraphFreeSourceNormalizationStage,
    validate_reloaded_source_normalization_result,
)

_DIGEST = r"^[0-9a-f]{64}$"


class SourceNormalizationNonCommit(BaseModel):
    """A safe terminal state of exactly one execution phase."""

    phase: Literal[
        "recovery_probe",
        "reservation_reserved",
        "proposal_sealed",
        "reservation_consumed",
        "evidence_sealed",
        "publication_linearized",
    ]
    reason: Literal[
        "proposal_run_unavailable",
        "resource_unavailable",
        "analysis_unavailable",
        "publication_conflict",
        "publication_unavailable",
    ]
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=_DIGEST)
    preparation_fingerprint: str = Field(pattern=_DIGEST)
    operation_id: str = Field(min_length=1)
    operation_fence_digest: str = Field(pattern=_DIGEST)
    reason_code_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def _phase_reason_is_closed(self) -> SourceNormalizationNonCommit:
        allowed = {
            "recovery_probe": {"publication_unavailable"},
            "reservation_reserved": {"resource_unavailable"},
            "proposal_sealed": {"proposal_run_unavailable"},
            "reservation_consumed": {"resource_unavailable"},
            "evidence_sealed": {"analysis_unavailable"},
            "publication_linearized": {"publication_conflict", "publication_unavailable"},
        }
        if self.reason not in allowed[self.phase]:
            raise ValueError("source-normalization noncommit phase/reason is invalid")
        body = self.model_dump(mode="python", exclude={"reason_code_digest"})
        if self.reason_code_digest != contract_digest(
            b"memorii.semantic-ingestion.source-normalization-noncommit.v1", body
        ):
            raise ValueError("source-normalization noncommit digest mismatch")
        return self

    @classmethod
    def create(
        cls, *, phase: str, reason: str, invocation: GraphFreeSourceNormalizationInvocation
    ) -> SourceNormalizationNonCommit:
        body = {
            "phase": phase,
            "reason": reason,
            "source_id": invocation.source.source_id,
            "source_digest": invocation.source.source_digest,
            "preparation_fingerprint": invocation.source.preparation_fingerprint,
            "operation_id": invocation.operation_id,
            "operation_fence_digest": invocation.operation_fence_binding.binding_digest,
        }
        return cls(
            **body,
            reason_code_digest=contract_digest(b"memorii.semantic-ingestion.source-normalization-noncommit.v1", body),
        )


class SourceNormalizationDerivationAuthority(BaseModel):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=_DIGEST)
    preparation_fingerprint: str = Field(pattern=_DIGEST)
    proposal_run_authority: ProposalRunProductionAuthority
    bootstrap_v3_runtime_authority: BootstrapV3RuntimeAuthority | None = None
    analyzer_resource_bindings: tuple[SegmentLanguageResourceBinding, ...]
    bootstrap_analysis_routes: BootstrapAnalysisRouteBindingSet
    consensus_policy_authority: ConsensusPolicyAuthority
    language_construction_policies: LanguageConstructionPolicyAuthorityBundle
    temporal_policy: TemporalPolicySnapshot
    trust_policy: TrustPolicySnapshot
    arbitration_as_of: datetime
    capability_registry: CapabilityRegistrySnapshot
    graph_dependent_execution_policy: GraphDependentExecutionPolicy
    authority_digest: str = Field(pattern=_DIGEST)
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def _validates_complete_authority(self) -> SourceNormalizationDerivationAuthority:
        bindings = tuple(binding.resource_binding_digest for binding in self.analyzer_resource_bindings)
        if bindings != tuple(sorted(set(bindings))):
            raise ValueError("analyzer resource bindings must be canonical and unique")
        if (self.proposal_run_authority.source_id, self.proposal_run_authority.source_digest,
            self.proposal_run_authority.preparation_fingerprint) != (
            self.source_id, self.source_digest, self.preparation_fingerprint,
        ):
            raise ValueError("proposal-run authority does not join source normalization authority")
        if (
            self.bootstrap_analysis_routes.source_id,
            self.bootstrap_analysis_routes.source_digest,
            self.bootstrap_analysis_routes.preparation_fingerprint,
        ) != (self.source_id, self.source_digest, self.preparation_fingerprint):
            raise ValueError("bootstrap analysis route bindings do not join authority")
        bootstrap_runtime = self.bootstrap_v3_runtime_authority
        if bootstrap_runtime is not None and (
            bootstrap_runtime.payload_limit_authority.source_id,
            bootstrap_runtime.payload_limit_authority.source_digest,
            bootstrap_runtime.payload_limit_authority.preparation_fingerprint,
        ) != (self.source_id, self.source_digest, self.preparation_fingerprint):
            raise ValueError("bootstrap V3 runtime authority does not join source normalization authority")
        body = self.model_dump(
            mode="python",
            exclude={"authority_digest"},
            exclude_none=True,
        )
        if self.authority_digest != contract_digest(
            b"memorii.semantic-ingestion.source-normalization-derivation-authority.v1",
            body,
        ):
            raise ValueError("source-normalization derivation authority digest mismatch")
        return self


class SourceNormalizationPublicationAuthority(BaseModel):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=_DIGEST)
    preparation_fingerprint: str = Field(pattern=_DIGEST)
    operation_id: str = Field(min_length=1)
    publication_coordinate: SourceNormalizationPublicationCoordinate
    progress: PrePlanningSourceIngestionProgress
    operation_fence_binding: OperationFenceBinding
    operation_lease_binding: OperationLeaseBinding
    writer_commit_binding: SemanticWriterCommitBinding
    expected_operation_generation: int = Field(ge=1)
    expected_artifact_generation: int = Field(ge=1)
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def _validates_current_publication(self) -> SourceNormalizationPublicationAuthority:
        coordinate = self.publication_coordinate
        if (
            coordinate.preparation_fingerprint != self.preparation_fingerprint
            or coordinate.operation_fence_binding != self.operation_fence_binding
            or coordinate.expected_current_artifact_generation != self.expected_artifact_generation
            or self.operation_lease_binding.operation_fence_binding != self.operation_fence_binding
            or self.progress.operation_lease_binding != self.operation_lease_binding
            or (self.progress.source_id, self.progress.source_digest, self.progress.operation_id)
            != (self.source_id, self.source_digest, self.operation_id)
        ):
            raise ValueError("source-normalization publication authority does not close")
        return self


class SourceNormalizationAuthorityBundle(BaseModel):
    derivation: SourceNormalizationDerivationAuthority
    publication: SourceNormalizationPublicationAuthority
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def _joins(self) -> SourceNormalizationAuthorityBundle:
        if (self.derivation.source_id, self.derivation.source_digest, self.derivation.preparation_fingerprint) != (
            self.publication.source_id,
            self.publication.source_digest,
            self.publication.preparation_fingerprint,
        ):
            raise ValueError("source-normalization authority source coordinates differ")
        if self.publication.operation_fence_binding != self.publication.publication_coordinate.operation_fence_binding:
            raise ValueError("source-normalization publication fence differs from coordinate")
        return self


class SourceNormalizationAuthorityProvider(Protocol):
    """Host-owned issuer for one fully validated, current authority bundle."""

    def build(
        self,
        *,
        invocation: GraphFreeSourceNormalizationInvocation,
        handoff: BootstrapWriterHandoffResult,
        recovery_claim: BootstrapRecoveryClaimV3,
    ) -> SourceNormalizationAuthorityBundle | None: ...


class StaticSourceNormalizationAuthorityProvider:
    """Explicit host fixture/composition provider over prevalidated bundles.

    It performs no discovery or derivation.  Production hosts may use a more
    dynamic authority owner, but must retain this exact request boundary.
    """

    def __init__(self, *, bundles: tuple[SourceNormalizationAuthorityBundle, ...]) -> None:
        keys = tuple(
            (
                bundle.publication.source_id,
                bundle.publication.source_digest,
                bundle.publication.preparation_fingerprint,
                bundle.publication.operation_id,
                bundle.publication.operation_fence_binding.binding_digest,
            )
            for bundle in bundles
        )
        if len(set(keys)) != len(keys):
            raise ValueError("source-normalization authority bundles must be unique")
        self._bundles = dict(zip(keys, bundles, strict=True))

    def build(
        self,
        *,
        invocation: GraphFreeSourceNormalizationInvocation,
        handoff: BootstrapWriterHandoffResult,
        recovery_claim: BootstrapRecoveryClaimV3,
    ) -> SourceNormalizationAuthorityBundle | None:
        marker = handoff.marker
        if handoff.kind not in {"started", "already_started"} or marker is None:
            return None
        key = (
            invocation.source.source_id,
            invocation.source.source_digest,
            invocation.source.preparation_fingerprint,
            invocation.operation_id,
            invocation.operation_fence_binding.binding_digest,
        )
        bundle = self._bundles.get(key)
        if bundle is None or marker.operation_fence_binding != invocation.operation_fence_binding:
            return None
        control = recovery_claim.control_snapshot.control_record
        if (
            control.operation_fence_digest != invocation.operation_fence_binding.binding_digest
            or control.operation_generation != bundle.publication.expected_operation_generation
            or control.artifact_generation != bundle.publication.expected_artifact_generation
            or control.operation_lease_binding != bundle.publication.operation_lease_binding
            or control.writer_commit_binding != bundle.publication.writer_commit_binding
        ):
            return None
        return bundle


class SourceNormalizationTrustedTime(Protocol):
    def server_time(self) -> datetime: ...
    def monotonic_tick(self) -> int: ...


class SourceNormalizationResourceReservation(BaseModel):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=_DIGEST)
    preparation_fingerprint: str = Field(pattern=_DIGEST)
    operation_id: str = Field(min_length=1)
    operation_fence_digest: str = Field(pattern=_DIGEST)
    required_lane_manifest_digests: tuple[str, ...]
    resource_envelope_digest: str = Field(pattern=_DIGEST)
    reservation_nonce: str = Field(min_length=1)
    issued_server_time: datetime
    expires_server_time: datetime
    issued_monotonic_tick: int
    expires_monotonic_tick: int
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ConsumedSourceNormalizationResourceReservation(SourceNormalizationResourceReservation):
    consumed_server_time: datetime
    consumed_monotonic_tick: int
    consumption_digest: str = Field(pattern=_DIGEST)


class SourceNormalizationResourceReservationProvider(Protocol):
    def reserve(
        self,
        *,
        invocation: GraphFreeSourceNormalizationInvocation,
        handoff: BootstrapWriterHandoffResult,
        authority: SourceNormalizationDerivationAuthority,
        server_time: datetime,
        monotonic_tick: int,
    ) -> SourceNormalizationResourceReservation | None: ...
    def validate_or_consume(
        self,
        *,
        reservation: SourceNormalizationResourceReservation,
        invocation: GraphFreeSourceNormalizationInvocation,
        handoff: BootstrapWriterHandoffResult,
        authority: SourceNormalizationDerivationAuthority,
        server_time: datetime,
        monotonic_tick: int,
    ) -> ConsumedSourceNormalizationResourceReservation | None: ...
    def release(
        self,
        *,
        reservation: SourceNormalizationResourceReservation,
        consumed: ConsumedSourceNormalizationResourceReservation | None,
    ) -> None: ...


class InjectedSourceNormalizationTrustedTime:
    """Composition-owned dual clock; callers must inject both trusted sources."""

    def __init__(self, *, server_time: Callable[[], datetime], monotonic_tick: Callable[[], int]) -> None:
        self._server_time = server_time
        self._monotonic_tick = monotonic_tick

    def server_time(self) -> datetime:
        value = self._server_time()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("trusted server clock returned an invalid value")
        return value

    def monotonic_tick(self) -> int:
        value = self._monotonic_tick()
        if not isinstance(value, int) or value < 0:
            raise ValueError("trusted monotonic clock returned an invalid value")
        return value


class InMemorySourceNormalizationResourceReservationProvider:
    """Atomic, call-scoped reservation for the complete selected analyzer envelope."""

    def __init__(self, *, capacity: int, ttl_ticks: int) -> None:
        if capacity < 1 or ttl_ticks < 1:
            raise ValueError("reservation capacity and lifetime must be positive")
        self._capacity = capacity
        self._ttl_ticks = ttl_ticks
        self._lock = Lock()
        self._states: dict[str, tuple[SourceNormalizationResourceReservation, bool, bool]] = {}

    def reserve(self, *, invocation: GraphFreeSourceNormalizationInvocation, handoff: BootstrapWriterHandoffResult,
                authority: SourceNormalizationDerivationAuthority, server_time: datetime,
                monotonic_tick: int) -> SourceNormalizationResourceReservation | None:
        del handoff
        required = tuple(binding.resource_binding_digest for binding in authority.analyzer_resource_bindings)
        route_bindings = tuple(route.resource_binding.resource_binding_digest for route in invocation.source.segment_language_routes.routes if route.resource_binding is not None)
        if required != route_bindings or not required:
            return None
        with self._lock:
            self._expire(monotonic_tick)
            if sum(not released for _, _, released in self._states.values()) >= self._capacity:
                return None
            nonce = token_urlsafe(24)
            reservation = SourceNormalizationResourceReservation(
                source_id=invocation.source.source_id, source_digest=invocation.source.source_digest,
                preparation_fingerprint=invocation.source.preparation_fingerprint,
                operation_id=invocation.operation_id,
                operation_fence_digest=invocation.operation_fence_binding.binding_digest,
                required_lane_manifest_digests=required,
                resource_envelope_digest=contract_digest(b"memorii.semantic-ingestion.source-normalization-resource-envelope.v1", {"lanes": required}),
                reservation_nonce=nonce, issued_server_time=server_time, expires_server_time=server_time + timedelta(seconds=self._ttl_ticks),
                issued_monotonic_tick=monotonic_tick, expires_monotonic_tick=monotonic_tick + self._ttl_ticks,
            )
            self._states[nonce] = (reservation, False, False)
            return reservation

    def validate_or_consume(self, *, reservation: SourceNormalizationResourceReservation,
                            invocation: GraphFreeSourceNormalizationInvocation, handoff: BootstrapWriterHandoffResult,
                            authority: SourceNormalizationDerivationAuthority, server_time: datetime,
                            monotonic_tick: int) -> ConsumedSourceNormalizationResourceReservation | None:
        del handoff
        with self._lock:
            state = self._states.get(reservation.reservation_nonce)
            if state is None:
                return None
            saved, consumed, released = state
            if consumed or released or saved != reservation or monotonic_tick > saved.expires_monotonic_tick or server_time > saved.expires_server_time:
                return None
            expected = (invocation.source.source_id, invocation.source.source_digest, invocation.source.preparation_fingerprint, invocation.operation_id, invocation.operation_fence_binding.binding_digest)
            actual = (saved.source_id, saved.source_digest, saved.preparation_fingerprint, saved.operation_id, saved.operation_fence_digest)
            lanes = tuple(binding.resource_binding_digest for binding in authority.analyzer_resource_bindings)
            if actual != expected or saved.required_lane_manifest_digests != lanes:
                return None
            body = saved.model_dump(mode="python") | {"consumed_server_time": server_time, "consumed_monotonic_tick": monotonic_tick}
            result = ConsumedSourceNormalizationResourceReservation(**body, consumption_digest=contract_digest(b"memorii.semantic-ingestion.source-normalization-resource-consumption.v1", body))
            self._states[saved.reservation_nonce] = (saved, True, False)
            return result

    def release(self, *, reservation: SourceNormalizationResourceReservation,
                consumed: ConsumedSourceNormalizationResourceReservation | None) -> None:
        del consumed
        with self._lock:
            state = self._states.get(reservation.reservation_nonce)
            if state is not None:
                saved, was_consumed, _ = state
                if saved == reservation:
                    self._states[saved.reservation_nonce] = (saved, was_consumed, True)

    def _expire(self, monotonic_tick: int) -> None:
        for nonce, (reservation, consumed, _released) in tuple(self._states.items()):
            if monotonic_tick > reservation.expires_monotonic_tick:
                self._states[nonce] = (reservation, consumed, True)


class SealedSemanticProposalRunProducer(Protocol):
    def produce(
        self,
        *,
        invocation: GraphFreeSourceNormalizationInvocation,
        handoff: BootstrapWriterHandoffResult,
        authority: ProposalRunProductionAuthority,
    ) -> SemanticProposalRun | SourceNormalizationNonCommit: ...


class SealedSourceNormalizationEvidenceProducerProtocol(Protocol):
    def produce(
        self,
        *,
        invocation: GraphFreeSourceNormalizationInvocation,
        proposal_run: SemanticProposalRun,
        authority: SourceNormalizationAuthorityBundle,
        resources: ConsumedSourceNormalizationResourceReservation,
        renew_claim: Callable[[], BootstrapRecoveryClaimV3 | None],
    ) -> GraphFreeSourceNormalizationInputs | SourceNormalizationNonCommit: ...


class BootstrapV3ProposalProducer(Protocol):
    def produce(self, *, authority: BootstrapV3RuntimeAuthority,
                renew: Callable[[], bool]) -> BootstrapProposalRunPayloadV3 | None: ...


class BootstrapV3EvidenceProducerProtocol(Protocol):
    def produce(self, *, authority: BootstrapV3RuntimeAuthority,
                renew: Callable[[], bool]) -> tuple[BootstrapAnalysisLaneResultV3, ...] | None: ...


class BootstrapRecoveryClaimRepository(Protocol):
    """Owns only the live, fence-bound V3 claim used by this attempt."""

    def renew_or_abort(
        self, *, claim: BootstrapRecoveryClaimV3, server_time: datetime, monotonic_tick: int
    ) -> BootstrapRecoveryRenewedV3 | BootstrapRecoveryAbortedV3 | BootstrapRecoveryClaimV3 | None: ...


class SourceNormalizationExecutionOwnerProtocol(Protocol):
    """The mandatory typed continuation from bootstrap into normalization."""

    def normalize_after_recovery_claim(
        self,
        *,
        invocation: GraphFreeSourceNormalizationInvocation,
        handoff: BootstrapWriterHandoffResult,
        recovery_claim: BootstrapRecoveryClaimV3,
        authority: SourceNormalizationAuthorityBundle,
    ) -> SourceNormalizationResult | SourceNormalizationNonCommit: ...


class SourceNormalizationExecutionOwner:
    """The only owner that advances an already-probed V3 recovery claim."""

    def __init__(
        self,
        *,
        proposal_producer: SealedSemanticProposalRunProducer,
        evidence_producer: SealedSourceNormalizationEvidenceProducerProtocol,
        trusted_time: SourceNormalizationTrustedTime,
        reservation_provider: SourceNormalizationResourceReservationProvider,
        recovery_repository: BootstrapRecoveryClaimRepository,
        publisher: SourceNormalizationStage,
        bootstrap_v3_proposal_producer: BootstrapV3ProposalProducer | None = None,
        bootstrap_v3_evidence_producer: BootstrapV3EvidenceProducerProtocol | None = None,
        bootstrap_v3_interpreter: BootstrapV3GraphFreeInterpreter | None = None,
    ) -> None:
        self._proposal_producer = proposal_producer
        self._evidence_producer = evidence_producer
        self._trusted_time = trusted_time
        self._reservation_provider = reservation_provider
        self._recovery_repository = recovery_repository
        self._stage = GraphFreeSourceNormalizationStage(publisher=publisher)
        self._bootstrap_v3_stage = BootstrapV3SourceNormalizationStage(publisher=publisher)
        self._bootstrap_v3_proposal_producer = bootstrap_v3_proposal_producer
        self._bootstrap_v3_evidence_producer = bootstrap_v3_evidence_producer
        self._bootstrap_v3_interpreter = bootstrap_v3_interpreter

    def normalize_after_recovery_claim(
        self,
        *,
        invocation: GraphFreeSourceNormalizationInvocation,
        handoff: BootstrapWriterHandoffResult,
        recovery_claim: BootstrapRecoveryClaimV3,
        authority: SourceNormalizationAuthorityBundle,
    ) -> SourceNormalizationResult | SourceNormalizationNonCommit:
        # Probe/found/unavailable handling belongs to the coordinator.  This
        # boundary receives only its one live claim and cannot retry a probe.
        try:
            self._validate_authority(invocation=invocation, handoff=handoff, authority=authority)
        except (AttributeError, TypeError, ValueError):
            return SourceNormalizationNonCommit.create(
                phase="recovery_probe", reason="publication_unavailable", invocation=invocation
            )
        claim = recovery_claim
        if not self._claim_joins(
            claim=claim, invocation=invocation, handoff=handoff, authority=authority
        ):
            return SourceNormalizationNonCommit.create(
                phase="recovery_probe", reason="publication_unavailable", invocation=invocation
            )
        if authority.derivation.bootstrap_v3_runtime_authority is not None:
            return self._normalize_bootstrap_v3(
                invocation=invocation, handoff=handoff, claim=claim, authority=authority
            )
        reservation = None
        consumed = None
        try:
            reservation = self._reservation_provider.reserve(
                invocation=invocation,
                handoff=handoff,
                authority=authority.derivation,
                server_time=self._trusted_time.server_time(),
                monotonic_tick=self._trusted_time.monotonic_tick(),
            )
            if reservation is None:
                return SourceNormalizationNonCommit.create(
                    phase="reservation_reserved", reason="resource_unavailable", invocation=invocation
                )
            claim = self._renew(claim=claim)
            if claim is None:
                return SourceNormalizationNonCommit.create(
                    phase="proposal_sealed", reason="proposal_run_unavailable", invocation=invocation
                )
            run = self._proposal_producer.produce(
                invocation=invocation, handoff=handoff, authority=authority.derivation.proposal_run_authority
            )
            if isinstance(run, SourceNormalizationNonCommit):
                return self._expect(run, "proposal_sealed", "proposal_run_unavailable")
            claim = self._renew(claim=claim)
            if claim is None:
                return SourceNormalizationNonCommit.create(
                    phase="reservation_consumed", reason="resource_unavailable", invocation=invocation
                )
            consumed = self._reservation_provider.validate_or_consume(
                reservation=reservation,
                invocation=invocation,
                handoff=handoff,
                authority=authority.derivation,
                server_time=self._trusted_time.server_time(),
                monotonic_tick=self._trusted_time.monotonic_tick(),
            )
            if consumed is None:
                return SourceNormalizationNonCommit.create(
                    phase="reservation_consumed", reason="resource_unavailable", invocation=invocation
                )
            def renew_for_lane() -> BootstrapRecoveryClaimV3 | None:
                nonlocal claim
                claim = self._renew(claim=claim)
                return claim

            inputs = self._evidence_producer.produce(
                invocation=invocation, proposal_run=run, authority=authority, resources=consumed,
                renew_claim=renew_for_lane,
            )
            if isinstance(inputs, SourceNormalizationNonCommit):
                return self._expect(inputs, "evidence_sealed", "analysis_unavailable")
            claim = self._renew(claim=claim)
            if claim is None:
                return SourceNormalizationNonCommit.create(
                    phase="publication_linearized", reason="publication_conflict", invocation=invocation
                )
            inputs = replace(
                inputs,
                bootstrap_recovery_key=self._recovery_key(invocation=invocation, handoff=handoff),
                bootstrap_recovery_claim=claim,
            )
            return self._validated_result(
                self._stage.normalize(inputs), invocation=invocation, authority=authority
            )
        except ValueError:
            return SourceNormalizationNonCommit.create(
                phase="publication_linearized", reason="publication_conflict", invocation=invocation
            )
        finally:
            if reservation is not None:
                self._reservation_provider.release(reservation=reservation, consumed=consumed)

    @staticmethod
    def _validate_authority(
        *,
        invocation: GraphFreeSourceNormalizationInvocation,
        handoff: BootstrapWriterHandoffResult,
        authority: SourceNormalizationAuthorityBundle,
    ) -> None:
        publication = authority.publication
        if (
            (authority.derivation.source_id, authority.derivation.source_digest, authority.derivation.preparation_fingerprint)
            != (invocation.source.source_id, invocation.source.source_digest, invocation.source.preparation_fingerprint)
            or (publication.source_id, publication.source_digest, publication.preparation_fingerprint, publication.operation_id)
            != (invocation.source.source_id, invocation.source.source_digest, invocation.source.preparation_fingerprint, invocation.operation_id)
            or publication.operation_fence_binding != invocation.operation_fence_binding
        ):
            raise ValueError("authority does not join invocation")
        route_bindings = tuple(
            route.resource_binding.resource_binding_digest
            for route in invocation.source.segment_language_routes.routes
            if getattr(route, "resource_binding", None) is not None
        )
        supplied_bindings = tuple(binding.resource_binding_digest for binding in authority.derivation.analyzer_resource_bindings)
        if supplied_bindings != route_bindings:
            raise ValueError("authority analyzer resources do not biject with source routes")
        bootstrap_routes = tuple(
            route for route in invocation.source.segment_language_routes.routes
            if isinstance(route, BootstrapDeclaredSegmentLanguageRoute)
        )
        bootstrap_bindings = authority.derivation.bootstrap_analysis_routes.bindings
        if (
            tuple(binding.segment_id for binding in bootstrap_bindings)
            != tuple(route.segment_id for route in bootstrap_routes)
            or any(
                (
                    binding.source_id, binding.source_digest,
                    binding.preparation_fingerprint, binding.segment_id,
                    binding.parent_projection_segment_id,
                    binding.bootstrap_route_digest,
                    binding.segment_text_artifact_id,
                    binding.segment_text_artifact_digest,
                    binding.segment_text_content_digest,
                    binding.selected_language,
                )
                != (
                    route.source_id, route.source_digest,
                    invocation.source.preparation_fingerprint, route.segment_id,
                    route.parent_projection_segment_id, route.route_digest,
                    route.segment_text_artifact_id, route.segment_text_artifact_digest,
                    route.segment_text_content_digest, route.declared_language,
                )
                for binding, route in zip(bootstrap_bindings, bootstrap_routes, strict=True)
            )
        ):
            raise ValueError("bootstrap analysis bindings do not biject with declared routes")
        if authority.derivation.proposal_run_authority.route_set_digest != invocation.source.segment_language_routes.route_set_digest:
            raise ValueError("proposal-run authority does not bind source route set")
        marker = handoff.marker
        if marker is None or (
            publication.operation_fence_binding != marker.operation_fence_binding
            or publication.writer_commit_binding != marker.writer_commit_binding
        ):
            raise ValueError("publication authority does not join bootstrap handoff")

    def _renew(self, *, claim: BootstrapRecoveryClaimV3) -> BootstrapRecoveryClaimV3 | None:
        result = self._recovery_repository.renew_or_abort(
            claim=claim,
            server_time=self._trusted_time.server_time(),
            monotonic_tick=self._trusted_time.monotonic_tick(),
        )
        if isinstance(result, BootstrapRecoveryRenewedV3):
            return result.claim
        if isinstance(result, BootstrapRecoveryClaimV3):
            return result
        return None

    @staticmethod
    def _recovery_key(*, invocation: GraphFreeSourceNormalizationInvocation, handoff: BootstrapWriterHandoffResult) -> BootstrapRecoveryKeyV3:
        marker = handoff.marker
        if marker is None or not hasattr(marker, "recovery_key_digest"):
            raise ValueError("V3 bootstrap handoff marker is required")
        body = {
            "source_id": invocation.source.source_id,
            "source_digest": invocation.source.source_digest,
            "preparation_fingerprint": invocation.source.preparation_fingerprint,
            "operation_id": invocation.operation_id,
            "operation_fence_digest": invocation.operation_fence_binding.binding_digest,
            "bootstrap_profile_manifest_digest": marker.release_evidence_digest,
            "handoff_request_digest": marker.handoff_request_digest,
        }
        key = BootstrapRecoveryKeyV3(**body, recovery_key_digest=contract_digest(
            b"memorii.semantic-ingestion.bootstrap-recovery-key.v3", body
        ))
        if key.recovery_key_digest != marker.recovery_key_digest:
            raise ValueError("bootstrap recovery key does not join handoff marker")
        return key

    @classmethod
    def _claim_joins(cls, *, claim: BootstrapRecoveryClaimV3,
                     invocation: GraphFreeSourceNormalizationInvocation,
                     handoff: BootstrapWriterHandoffResult,
                     authority: SourceNormalizationAuthorityBundle) -> bool:
        try:
            return (
                claim.recovery_key_digest == cls._recovery_key(invocation=invocation, handoff=handoff).recovery_key_digest
                and claim.operation_fence_digest == invocation.operation_fence_binding.binding_digest
                and claim.expected_operation_generation == authority.publication.expected_operation_generation
                and claim.expected_artifact_generation == authority.publication.expected_artifact_generation
            )
        except (AttributeError, TypeError, ValueError):
            return False

    @staticmethod
    def _expect(value: SourceNormalizationNonCommit, phase: str, reason: str) -> SourceNormalizationNonCommit:
        if (value.phase, value.reason) != (phase, reason):
            raise ValueError("producer returned noncommit for wrong phase")
        return value

    @staticmethod
    def _validated_result(
        result: object,
        *,
        invocation: GraphFreeSourceNormalizationInvocation,
        authority: SourceNormalizationAuthorityBundle,
    ) -> SourceNormalizationResult | SourceNormalizationNonCommit:
        validated = validate_reloaded_source_normalization_result(
            result=result,
            source=invocation.source,
            operation_fence_binding=invocation.operation_fence_binding,
            publication_coordinate=authority.publication.publication_coordinate,
        )
        if validated is not None:
            return validated
        return SourceNormalizationNonCommit.create(
            phase="publication_linearized",
            reason="publication_unavailable",
            invocation=invocation,
        )

    def _normalize_bootstrap_v3(
        self,
        *,
        invocation: GraphFreeSourceNormalizationInvocation,
        handoff: BootstrapWriterHandoffResult,
        claim: BootstrapRecoveryClaimV3,
        authority: SourceNormalizationAuthorityBundle,
    ) -> BootstrapSourceNormalizationResultV3 | SourceNormalizationNonCommit:
        """Run the strictly V3-native branch; generic V2 producers never enter it."""
        runtime = authority.derivation.bootstrap_v3_runtime_authority
        if (
            runtime is None
            or self._bootstrap_v3_proposal_producer is None
            or self._bootstrap_v3_evidence_producer is None
            or self._bootstrap_v3_interpreter is None
        ):
            return SourceNormalizationNonCommit.create(
                phase="proposal_sealed", reason="proposal_run_unavailable", invocation=invocation
            )
        current = claim
        def renew() -> bool:
            nonlocal current
            renewed = self._renew(claim=current)
            if renewed is None:
                return False
            current = renewed
            return True

        if not renew():
            return SourceNormalizationNonCommit.create(
                phase="proposal_sealed", reason="proposal_run_unavailable", invocation=invocation
            )
        try:
            payload = self._bootstrap_v3_proposal_producer.produce(authority=runtime, renew=renew)
            if payload is None or not renew():
                return SourceNormalizationNonCommit.create(
                    phase="proposal_sealed", reason="proposal_run_unavailable", invocation=invocation
                )
            lanes = self._bootstrap_v3_evidence_producer.produce(authority=runtime, renew=renew)
            if lanes is None or not renew():
                return SourceNormalizationNonCommit.create(
                    phase="evidence_sealed", reason="analysis_unavailable", invocation=invocation
                )
            interpreted = self._bootstrap_v3_interpreter.interpret(
                proposal_payload=payload, lane_results=lanes,
                payload_limit_authority=runtime.payload_limit_authority,
            )
            if not renew():
                raise ValueError("bootstrap claim expired before publication")
            return self._bootstrap_v3_stage.normalize(BootstrapV3SourceNormalizationInputs(
                proposal_payload=payload, lane_results=lanes, interpretation_bundle=interpreted.bundle,
                source_alignment=interpreted.alignment, payload_limit_authority=runtime.payload_limit_authority,
                capability_registry=authority.derivation.capability_registry,
                graph_dependent_execution_policy=(
                    authority.derivation.graph_dependent_execution_policy
                ),
                bootstrap_recovery_key=self._recovery_key(invocation=invocation, handoff=handoff),
                bootstrap_recovery_claim=current, operation_fence_binding=authority.publication.operation_fence_binding,
                operation_lease_binding=authority.publication.operation_lease_binding,
                writer_commit_binding=authority.publication.writer_commit_binding,
                expected_operation_generation=authority.publication.expected_operation_generation,
                expected_artifact_generation=authority.publication.expected_artifact_generation,
            ))
        except ValueError:
            return SourceNormalizationNonCommit.create(
                phase="publication_linearized", reason="publication_conflict", invocation=invocation
            )



__all__ = [name for name in globals() if name.startswith(("SourceNormalization", "Sealed", "Consumed", "Static"))]
