"""Deterministic identity-lineage replay and graph-audit views."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from typing import TYPE_CHECKING, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.memory_evolution.graph_records import (
    AcceptedIdentityOperationArtifact,
    GraphReadSetExtension,
    GraphWriteIntent,
    PlannedEntityIdentity,
    PlannedIdentityReservation,
    TrustedAcceptedIdentityOperationDecision,
    VerifiedIdentityDecisionAuthority,
    canonical_graph_codec_manifest,
    graph_digest,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    OperationFenceBinding,
    encode_typed_value,
)
from memorii.core.memory_evolution.semantic_state import (
    CompiledIdentityLineageTransition,
    ImmutableAssertionEntityRef,
    LineageEntityIdentity,
    LineageReferenceDisposition,
    LineageReverseReference,
    SemanticAssertionKey,
)
from memorii.core.memory_evolution.transaction_coordinator import (
    SealedGraphStateSnapshot,
    SemanticIngestionTransactionCoordinator,
)
from memorii.core.memory_evolution.writer_admission import SemanticWriterAdmissionStore
from memorii.core.semantic_ingestion.contracts import (
    ClaimAssertion,
    IdentityLineageRecord,
    IndependentSourceAnalysis,
    SealedSemanticOperation,
    SemanticAuthorizationReadSet,
    SemanticCandidate,
)

if TYPE_CHECKING:
    from memorii.core.memory_evolution.graph_planning import (
        FrozenIdentityGraphPlanningArtifact,
    )

_GENESIS_DOMAIN = b"memorii.identity-lineage.genesis.v1\0"
_AUDIT_VIEW_DOMAIN = b"memorii.identity-lineage.audit-view.v1\0"


class IdentityLineageError(ValueError):
    """A closed identity-lineage compiler, replay, or read failure."""


class IdentityLineageAuditScopeSnapshot(BaseModel):
    tenant_partition_id: str = Field(min_length=1)
    principal_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorized_scope_ids: tuple[str, ...]
    scope_mode: Literal["scoped", "full"]
    issued_at: datetime
    expires_at: datetime
    authorization_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    def model_post_init(self, __context: object) -> None:
        if self.authorized_scope_ids != tuple(sorted(set(self.authorized_scope_ids))):
            raise ValueError("identity_lineage_audit_scopes_not_canonical")
        if self.issued_at.tzinfo is None or self.expires_at.tzinfo is None or self.expires_at <= self.issued_at:
            raise ValueError("identity_lineage_audit_scope_interval_invalid")

    @classmethod
    def create(cls, **values: object) -> IdentityLineageAuditScopeSnapshot:
        body = dict(values)
        return cls.model_validate(
            body
            | {
                "authorization_snapshot_digest": sha256(
                    b"memorii.identity-lineage.audit-scope.v1\0"
                    + encode_typed_value(_canonical(body))
                ).hexdigest()
            }
        )

    def require_current(self, at: datetime) -> None:
        if (
            at.tzinfo is None
            or at.utcoffset() is None
            or at.astimezone(UTC) < self.issued_at
            or at.astimezone(UTC) >= self.expires_at
            or not self.authorized_scope_ids
        ):
            raise IdentityLineageError("identity_lineage_audit_denied")


class IdentityLineageAuditGrant(BaseModel):
    tenant_partition_id: str = Field(min_length=1)
    principal_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorized_scope_ids: tuple[str, ...]
    allow_full_scope: bool = False
    issued_at: datetime
    expires_at: datetime
    revoked: bool = False

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    def model_post_init(self, __context: object) -> None:
        if self.authorized_scope_ids != tuple(sorted(set(self.authorized_scope_ids))):
            raise ValueError("identity_lineage_audit_grant_scopes_not_canonical")
        if self.issued_at.tzinfo is None or self.expires_at.tzinfo is None or self.expires_at <= self.issued_at:
            raise ValueError("identity_lineage_audit_grant_interval_invalid")


class GrantBackedIdentityLineageAuditAuthorizer:
    """Derive a purpose-bound scope snapshot from authenticated host authority."""

    def __init__(self, grant_provider: Callable[[str], IdentityLineageAuditGrant | None]) -> None:
        self._grant_provider = grant_provider

    def authorize_identity_lineage_audit(self, *, ingress: object, request: object, server_time: datetime) -> IdentityLineageAuditScopeSnapshot | None:
        principal = getattr(ingress, "delivery_principal_binding", None)
        current = getattr(getattr(ingress, "current_authorized_scopes", None), "scopes", ())
        if principal is None:
            return None
        grant = self._grant_provider(principal.binding_digest)
        if (
            grant is None
            or grant.revoked
            or grant.principal_binding_digest != principal.binding_digest
            or grant.tenant_partition_id != principal.tenant_partition_id
            or server_time < grant.issued_at
            or server_time >= grant.expires_at
        ):
            return None
        allowed = tuple(sorted(set(grant.authorized_scope_ids) & set(current)))
        mode = getattr(request, "scope_mode", None)
        if mode == "full":
            if not grant.allow_full_scope or not allowed:
                return None
            authorized = allowed
        elif mode == "scoped":
            scope_key = getattr(request, "scope_key", None)
            if scope_key not in allowed:
                return None
            authorized = (scope_key,)
        else:
            return None
        return IdentityLineageAuditScopeSnapshot.create(
            tenant_partition_id=grant.tenant_partition_id,
            principal_binding_digest=grant.principal_binding_digest,
            authorized_scope_ids=authorized,
            scope_mode=mode,
            issued_at=server_time,
            expires_at=grant.expires_at,
        )

    def revalidate_identity_lineage_audit_scope(
        self,
        scope: IdentityLineageAuditScopeSnapshot,
        *,
        server_time: datetime,
    ) -> IdentityLineageAuditScopeSnapshot | None:
        grant = self._grant_provider(scope.principal_binding_digest)
        if (
            grant is None
            or grant.revoked
            or grant.principal_binding_digest != scope.principal_binding_digest
            or grant.tenant_partition_id != scope.tenant_partition_id
            or server_time < grant.issued_at
            or server_time >= grant.expires_at
            or not set(scope.authorized_scope_ids).issubset(
                grant.authorized_scope_ids
            )
            or (scope.scope_mode == "full" and not grant.allow_full_scope)
        ):
            return None
        return IdentityLineageAuditScopeSnapshot.create(
            tenant_partition_id=scope.tenant_partition_id,
            principal_binding_digest=scope.principal_binding_digest,
            authorized_scope_ids=scope.authorized_scope_ids,
            scope_mode=scope.scope_mode,
            issued_at=server_time,
            expires_at=grant.expires_at,
        )


class ResolvedLineageReference(BaseModel):
    record_kind: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    reference_path: str = Field(min_length=1)
    assertion_reference: ImmutableAssertionEntityRef
    resolved_identity: LineageEntityIdentity
    lineage_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ResolvedClaimLineage(BaseModel):
    claim_assertion_id: str = Field(min_length=1)
    immutable_assertion_key: SemanticAssertionKey
    resolved_assertion_key: SemanticAssertionKey
    subject: ResolvedLineageReference
    object: ResolvedLineageReference | None = None
    system_time: datetime

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class IdentityLineageAuditView(BaseModel):
    repository_id: str = Field(min_length=1)
    graph_revision: str = Field(min_length=1)
    system_time: datetime | None = None
    lineage_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    transition_digests: tuple[str, ...]
    resolved_claims: tuple[ResolvedClaimLineage, ...]
    view_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class IdentityLineageAuditReader(Protocol):
    def read_identity_lineage(
        self,
        *,
        system_time: datetime | None = None,
    ) -> IdentityLineageAuditView: ...


class ScopedIdentityLineageAuditStore(Protocol):
    def lineage_audit_scope_event_ids(
        self,
        *,
        tenant_partition_id: str,
        authorized_scope_ids: tuple[str, ...],
    ) -> frozenset[str]: ...

    def semantic_replay_state(self) -> object: ...


class AtomicStoreScopedIdentityLineageAuditReader:
    """Read a tenant-partitioned atomic store only within an authorized scope."""

    def __init__(
        self,
        store: ScopedIdentityLineageAuditStore,
        *,
        tenant_partition_id: str,
        scope_revalidator: Callable[
            [IdentityLineageAuditScopeSnapshot, datetime],
            IdentityLineageAuditScopeSnapshot | None,
        ],
        now_provider: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not callable(getattr(store, "semantic_replay_state", None)) or not callable(
            getattr(store, "lineage_audit_scope_event_ids", None)
        ):
            raise TypeError("identity lineage audit reader requires canonical atomic store")
        if not tenant_partition_id:
            raise ValueError("identity lineage audit tenant is required")
        self._store = store
        self._tenant_partition_id = tenant_partition_id
        self._scope_revalidator = scope_revalidator
        self._now = now_provider

    def read_identity_lineage(
        self,
        *,
        request: object,
        scope: IdentityLineageAuditScopeSnapshot,
        system_time: datetime | None = None,
    ) -> IdentityLineageAuditView:
        scope_key = getattr(request, "scope_key", None)
        scope_mode = getattr(request, "scope_mode", None)
        if (
            scope.tenant_partition_id != self._tenant_partition_id
            or scope_mode != scope.scope_mode
            or (
                scope_mode == "scoped"
                and (not isinstance(scope_key, str) or scope_key not in scope.authorized_scope_ids)
            )
        ):
            raise IdentityLineageError("identity_lineage_audit_denied")
        revalidated_scope = self._scope_revalidator(scope, self._now())
        if revalidated_scope is None:
            raise IdentityLineageError("identity_lineage_audit_denied")
        scope = revalidated_scope
        event_ids = self._store.lineage_audit_scope_event_ids(
            tenant_partition_id=scope.tenant_partition_id,
            authorized_scope_ids=scope.authorized_scope_ids,
        )
        state = self._store.semantic_replay_state()
        return scoped_identity_lineage_audit_view(
            state,
            disclosed_event_ids=event_ids,
            system_time=system_time,
        )


class AcceptedIdentityOperationRepository(Protocol):
    def get_accepted_identity_operation(
        self,
        *,
        operation_id: str,
        sealed_operation_digest: str | None,
        candidate_digest: str | None,
        source_analysis_digest: str | None,
    ) -> BaseModel | None: ...

    def get_identity_graph_planning_artifact(
        self,
        *,
        operation_id: str,
        sealed_operation_digest: str | None,
        candidate_digest: str | None,
        source_analysis_digest: str | None,
    ) -> FrozenIdentityGraphPlanningArtifact | None: ...

    def publish_accepted_identity_operation(
        self,
        artifact: FrozenIdentityGraphPlanningArtifact,
        *,
        writer_binding: object,
    ) -> FrozenIdentityGraphPlanningArtifact: ...


class TrustedAcceptedIdentityOperationResolver(Protocol):
    """Resolve graph-addressed identity IR only from authenticated host authority."""

    def resolve_accepted_identity_operation(
        self,
        *,
        operation: SealedSemanticOperation,
        candidate: SemanticCandidate,
        source_analysis: IndependentSourceAnalysis,
        operation_fence: OperationFenceBinding,
        graph_snapshot: SealedGraphStateSnapshot,
    ) -> TrustedAcceptedIdentityOperationDecision | None: ...


class TrustedIdentityDecisionAuthorityVerifier(Protocol):
    def verify_identity_decision_authority(
        self, decision: TrustedAcceptedIdentityOperationDecision
    ) -> VerifiedIdentityDecisionAuthority | None: ...


class AtomicStoreAcceptedIdentityOperationPlanner:
    """Sole terminal owner that validates, reserves, and publishes accepted IR."""

    def __init__(
        self,
        coordinator: SemanticIngestionTransactionCoordinator,
        repository: AcceptedIdentityOperationRepository,
        writers: SemanticWriterAdmissionStore,
        resolver: TrustedAcceptedIdentityOperationResolver,
        authority_verifier: TrustedIdentityDecisionAuthorityVerifier,
    ) -> None:
        self._coordinator = coordinator
        self._repository = repository
        self._writers = writers
        self._resolver = resolver
        self._authority_verifier = authority_verifier

    def prepare_accepted_identity_operation(
        self,
        *,
        operation: SealedSemanticOperation,
        candidate: SemanticCandidate,
        source_analysis: IndependentSourceAnalysis,
        operation_fence: OperationFenceBinding,
        authorization_read_set: SemanticAuthorizationReadSet,
    ) -> None:
        existing = self._repository.get_identity_graph_planning_artifact(
            operation_id=operation.operation_id,
            sealed_operation_digest=operation.sealed_operation_digest,
            candidate_digest=candidate.candidate_digest,
            source_analysis_digest=source_analysis.analysis_digest,
        )
        if existing is not None:
            decision = TrustedAcceptedIdentityOperationDecision.model_validate(
                existing.trusted_decision.model_dump(mode="python")
            )
            verification = self._authority_verifier.verify_identity_decision_authority(
                decision
            )
            if verification is None or VerifiedIdentityDecisionAuthority.model_validate(
                verification.model_dump(mode="python")
            ) != existing.authority_verification:
                raise ValueError("existing_identity_planning_authority_unverified")
            return
        if (
            operation.kind != "identity"
            or candidate.candidate_id != operation.candidate_id
            or source_analysis.candidate_id != operation.candidate_id
            or source_analysis.source_id != operation_fence.source_id
            or source_analysis.source_digest != operation_fence.source_digest
        ):
            raise ValueError("accepted_identity_planning_binding_invalid")

        def plan(snapshot: SealedGraphStateSnapshot):
            decision = self._resolver.resolve_accepted_identity_operation(
                operation=operation,
                candidate=candidate,
                source_analysis=source_analysis,
                operation_fence=operation_fence,
                graph_snapshot=snapshot,
            )
            if decision is None:
                raise ValueError("accepted_identity_operation_authority_missing")
            decision = TrustedAcceptedIdentityOperationDecision.model_validate(
                decision.model_dump(mode="python")
            )
            expected_bindings = (
                operation.sealed_operation_digest,
                candidate.candidate_digest,
                source_analysis.analysis_digest,
                operation_fence.binding_digest,
                snapshot.snapshot_digest,
                snapshot.read_set.read_set_digest,
            )
            if (
                decision.sealed_operation_digest,
                decision.candidate_digest,
                decision.source_analysis_digest,
                decision.operation_fence_binding_digest,
                decision.graph_snapshot_digest,
                decision.graph_read_set_digest,
            ) != expected_bindings:
                raise ValueError("trusted_identity_decision_binding_mismatch")
            verification = self._authority_verifier.verify_identity_decision_authority(
                decision
            )
            if verification is None:
                raise ValueError("trusted_identity_decision_authority_unverified")
            verification = VerifiedIdentityDecisionAuthority.model_validate(
                verification.model_dump(mode="python")
            )
            if (
                verification.decision_digest != decision.decision_digest
                or (
                    verification.sealed_operation_digest,
                    verification.candidate_digest,
                    verification.source_analysis_digest,
                    verification.operation_fence_binding_digest,
                    verification.graph_snapshot_digest,
                    verification.graph_read_set_digest,
                )
                != expected_bindings
            ):
                raise ValueError("trusted_identity_decision_verification_substitution")
            accepted = decision.operation
            if accepted.operation_id != operation.operation_id:
                raise ValueError("accepted_identity_operation_id_mismatch")
            grounded = tuple(
                sorted(
                    (
                        item.source_id,
                        item.mention_span.start,
                        item.mention_span.end,
                        item.evidence_digest,
                    )
                    for item in source_analysis.identity_evidence
                )
            )
            accepted_grounding = tuple(
                sorted(
                    (item.source_id, item.start, item.end, item.evidence_digest)
                    for item in accepted.source_evidence
                )
            )
            assertion_grounding = {
                (
                    source_analysis.source_id,
                    source_analysis.assertion_span.start,
                    source_analysis.assertion_span.end,
                )
            }
            accepted_spans = {item[:3] for item in accepted_grounding}
            if not accepted_grounding or not (
                set(accepted_grounding).issubset(set(grounded))
                if grounded
                else accepted_spans.issubset(assertion_grounding)
            ):
                raise ValueError("accepted_identity_operation_source_grounding_invalid")
            occupied = {
                f"{item.payload_record_kind}:{item.record_id}"
                for item in snapshot.canonical_graph.records
            }
            reservations = tuple(
                self._reservation(
                    identity=identity,
                    operation_fence=operation_fence,
                    snapshot=snapshot,
                    allocation_policy_fingerprint=verification.verification_digest,
                    occupied=occupied,
                    reserve_logical_entity=(
                        identity.logical_entity_id
                        not in {
                            predecessor.logical_entity_id
                            for predecessor in accepted.predecessors
                        }
                    ),
                )
                for identity in accepted.successors
            )
            accepted_artifact = AcceptedIdentityOperationArtifact.create(
                operation=accepted,
                operation_fence_id=operation_fence.operation_fence_id,
                sealed_operation_digest=operation.sealed_operation_digest,
                candidate_digest=candidate.candidate_digest,
                source_analysis_digest=source_analysis.analysis_digest,
                source_evidence_digests=tuple(
                    sorted(item.evidence_digest for item in accepted.source_evidence)
                ),
                semantic_authorization_read_set_digest=authorization_read_set.read_set_digest,
                authority_digest=verification.verification_digest,
                verified_decision_digest=decision.decision_digest,
                authority_record_id=verification.authority_record_id,
                authority_record_digest=verification.authority_record_digest,
                authority_verification_digest=verification.verification_digest,
                successor_reservations=reservations,
                alias_payload=decision.alias_payload,
            )
            transition = compile_accepted_identity_transition(snapshot, accepted)
            from memorii.core.memory_evolution.graph_planning import (
                build_frozen_identity_graph_planning_artifact,
            )

            return build_frozen_identity_graph_planning_artifact(
                graph_snapshot=snapshot,
                accepted_operation_artifact=accepted_artifact,
                compiled_transition=transition,
                operation=operation,
                candidate=candidate,
                trusted_decision=decision,
                authority_verification=verification,
                producer_transaction_group_id=operation_fence.operation_id,
            )

        binding = self._writers.commit_binding(self._writers.current())
        from memorii.core.memory_evolution.atomic_store import (
            IdentityPlanningStaleSnapshotError,
        )

        for attempt in range(2):
            artifact = self._coordinator.execute(plan)
            try:
                self._repository.publish_accepted_identity_operation(
                    artifact,
                    writer_binding=binding,
                )
                return
            except IdentityPlanningStaleSnapshotError:
                if attempt == 1:
                    raise
        raise AssertionError("unreachable bounded identity publication retry")

    @staticmethod
    def _reservation(
        *,
        identity: LineageEntityIdentity,
        operation_fence: OperationFenceBinding,
        snapshot: SealedGraphStateSnapshot,
        allocation_policy_fingerprint: str,
        occupied: set[str],
        reserve_logical_entity: bool,
    ) -> PlannedIdentityReservation:
        keys = (f"entity_revision:{identity.entity_revision_id}",)
        if reserve_logical_entity:
            keys = tuple(
                sorted((*keys, f"logical_entity:{identity.logical_entity_id}"))
            )
        if any(key in occupied for key in keys):
            raise ValueError("accepted_identity_allocation_collision")
        extension = GraphReadSetExtension.create(
            snapshot_token=snapshot.canonical_graph.snapshot_token,
            graph_revision=snapshot.graph_state.graph_revision,
            segment_governance_binding_digests=(),
            operation_fence_id=operation_fence.operation_fence_id,
            issuer_repository_id=snapshot.graph_state.repository_id,
            issuer_contract_fingerprint=graph_digest(
                b"memorii.identity-planner-contract.v1\0",
                canonical_graph_codec_manifest().manifest_fingerprint,
            ),
            dependency_kind="identity_allocation",
            record_keys=keys,
            partition_versions=snapshot.canonical_graph.read_set.partition_versions,
            manifest_fingerprints=tuple(sorted((
                canonical_graph_codec_manifest().manifest_fingerprint,
                snapshot.reference_integrity.manifest_fingerprint,
            ))),
        )
        return PlannedIdentityReservation.create(
            planned_identity=PlannedEntityIdentity(
                allocation_key=identity.entity_revision_id,
                entity_revision_id=identity.entity_revision_id,
                logical_entity_id=identity.logical_entity_id,
                allocation_namespace_id=operation_fence.allocation_namespace_id,
                allocation_policy_fingerprint=allocation_policy_fingerprint,
            ),
            collision_read_set_extension=extension,
            expected_absent_write_intents=tuple(
                GraphWriteIntent(record_key=key, expected_before_digest=None)
                for key in keys
            ),
            logical_entity_reservation_required=reserve_logical_entity,
        )


def identity_lineage_genesis_digest(repository_id: str) -> str:
    if not repository_id:
        raise IdentityLineageError("identity_lineage_repository_invalid")
    return sha256(_GENESIS_DOMAIN + encode_typed_value(repository_id)).hexdigest()


def derive_claim_reverse_reference_closure(
    *,
    claims: tuple[object, ...],
    predecessors: tuple[LineageEntityIdentity, ...],
    recorded_before: datetime,
) -> tuple[LineageReverseReference, ...]:
    """Extract the complete supported claim-reference schema without heuristics."""

    predecessor_set = set(predecessors)
    values: list[LineageReverseReference] = []
    for materialized in claims:
        record = getattr(materialized, "record", None)
        system_valid_from = getattr(materialized, "system_valid_from", None)
        if not isinstance(record, ClaimAssertion) or record.claim_identity is None:
            continue
        if not isinstance(system_valid_from, datetime) or system_valid_from > recorded_before:
            continue
        identity = record.claim_identity
        references = [
            (
                "/claim_identity/subject_assertion_ref/entity_revision_id",
                "/claim_identity/assertion_key_at_recording/slot/subject_logical_entity_id",
                identity.subject_assertion_ref,
            )
        ]
        if identity.object_assertion_ref is not None:
            references.append(
                (
                    "/claim_identity/object_assertion_ref/entity_revision_id",
                    "/claim_identity/assertion_key_at_recording/value/object_logical_entity_id",
                    identity.object_assertion_ref,
                )
            )
        for historical_path, current_path, assertion_ref in references:
            assert assertion_ref is not None
            predecessor = LineageEntityIdentity(
                entity_revision_id=assertion_ref.entity_revision_id,
                logical_entity_id=assertion_ref.logical_entity_id_at_assertion,
            )
            if predecessor not in predecessor_set:
                continue
            reference_value_digest = sha256(
                encode_typed_value(assertion_ref.model_dump(mode="python"))
            ).hexdigest()
            for path, lifecycle in (
                (historical_path, "historical"),
                (current_path, "current"),
            ):
                values.append(
                    LineageReverseReference.create(
                        record_kind="claim_assertion",
                        record_id=record.claim_assertion_id,
                        reference_path=path,
                        predecessor=predecessor,
                        lifecycle=lifecycle,
                        base_record_digest=record.record_digest,
                        referenced_value_digest=reference_value_digest,
                    )
                )
    return tuple(sorted(values, key=lambda item: item.reference_digest))


def derive_total_reverse_reference_closure(
    *,
    materialized_records: tuple[object, ...],
    predecessors: tuple[LineageEntityIdentity, ...],
    recorded_before: datetime,
) -> tuple[LineageReverseReference, ...]:
    """Extract the full manifest-governed reverse-reference closure."""

    from memorii.core.memory_evolution.reference_integrity import (
        extract_reference_edges,
        generated_reference_schema_manifest,
    )

    claims = tuple(
        item
        for item in materialized_records
        if isinstance(getattr(item, "record", None), ClaimAssertion)
    )
    values = list(
        derive_claim_reverse_reference_closure(
            claims=claims,
            predecessors=predecessors,
            recorded_before=recorded_before,
        )
    )
    annotations = {
        (entry.record_kind, field.reference_path): field.lifecycle_semantics
        for entry in generated_reference_schema_manifest().schema_entries
        for field in entry.reference_fields
    }
    for materialized in materialized_records:
        record = getattr(materialized, "record", None)
        system_valid_from = getattr(materialized, "system_valid_from", None)
        if (
            isinstance(record, ClaimAssertion)
            or not isinstance(system_valid_from, datetime)
            or system_valid_from > recorded_before
        ):
            continue
        record_kind = getattr(materialized, "record_kind", None)
        record_id = getattr(materialized, "record_id", None)
        base_record_digest = getattr(materialized, "record_digest", None)
        if not isinstance(record_kind, str):
            raise IdentityLineageError("identity_lineage_reference_record_invalid")
        for path, target in extract_reference_edges(record):
            matched = tuple(
                item
                for item in predecessors
                if (
                    target.kind == "entity_revision"
                    and item.entity_revision_id == target.target_id
                )
                or (
                    target.kind == "logical_entity"
                    and item.logical_entity_id == target.target_id
                )
            )
            if not matched:
                continue
            if len(matched) != 1:
                raise IdentityLineageError("identity_lineage_reference_target_ambiguous")
            lifecycle = annotations.get((record_kind, path))
            if lifecycle is None:
                raise IdentityLineageError("identity_lineage_reference_manifest_incomplete")
            values.append(
                LineageReverseReference.create(
                    record_kind=record_kind,
                    record_id=record_id,
                    reference_path=path,
                    predecessor=matched[0],
                    lifecycle=(
                        "historical" if lifecycle == "immutable_revision" else "current"
                    ),
                    base_record_digest=base_record_digest,
                    referenced_value_digest=sha256(
                        encode_typed_value(target.model_dump(mode="python"))
                    ).hexdigest(),
                )
            )
    return tuple(sorted(values, key=lambda item: item.reference_digest))


class ReplayedIdentityLineage:
    """Validated lineage prefix used by projection and graph-audit reads."""

    def __init__(
        self,
        *,
        repository_id: str,
        graph_revision: str,
        transitions: tuple[tuple[CompiledIdentityLineageTransition, datetime], ...],
    ) -> None:
        self.repository_id = repository_id
        self.graph_revision = graph_revision
        self.transitions = transitions
        self.snapshot_digest = (
            transitions[-1][0].lineage_snapshot_after_digest
            if transitions
            else identity_lineage_genesis_digest(repository_id)
        )

    def resolve_claim(
        self,
        materialized: object,
        *,
        system_time: datetime | None = None,
    ) -> ResolvedClaimLineage:
        record = getattr(materialized, "record", None)
        recorded_at = getattr(materialized, "system_valid_from", None)
        if not isinstance(record, ClaimAssertion) or record.claim_identity is None or not isinstance(recorded_at, datetime):
            raise IdentityLineageError("identity_lineage_claim_binding_invalid")
        identity = record.claim_identity
        subject = self._resolve(
            record_id=record.claim_assertion_id,
            path="/claim_identity/assertion_key_at_recording/slot/subject_logical_entity_id",
            assertion_ref=identity.subject_assertion_ref,
            system_time=system_time,
        )
        object_ref = None
        if identity.object_assertion_ref is not None:
            object_ref = self._resolve(
                record_id=record.claim_assertion_id,
                path="/claim_identity/assertion_key_at_recording/value/object_logical_entity_id",
                assertion_ref=identity.object_assertion_ref,
                system_time=system_time,
            )
        slot = identity.assertion_key_at_recording.slot.model_copy(
            update={"subject_logical_entity_id": subject.resolved_identity.logical_entity_id}
        )
        value = identity.assertion_key_at_recording.value
        if object_ref is not None:
            value = value.model_copy(
                update={"object_logical_entity_id": object_ref.resolved_identity.logical_entity_id}
            )
        return ResolvedClaimLineage(
            claim_assertion_id=record.claim_assertion_id,
            immutable_assertion_key=identity.assertion_key_at_recording,
            resolved_assertion_key=SemanticAssertionKey(slot=slot, value=value),
            subject=subject,
            object=object_ref,
            system_time=recorded_at,
        )

    def _resolve(
        self,
        *,
        record_id: str,
        path: str,
        assertion_ref: ImmutableAssertionEntityRef,
        system_time: datetime | None,
    ) -> ResolvedLineageReference:
        current = LineageEntityIdentity(
            entity_revision_id=assertion_ref.entity_revision_id,
            logical_entity_id=assertion_ref.logical_entity_id_at_assertion,
        )
        snapshot = identity_lineage_genesis_digest(self.repository_id)
        for transition, recorded_at in self.transitions:
            if system_time is not None and recorded_at > system_time:
                break
            snapshot = transition.lineage_snapshot_after_digest
            disposition = next(
                (
                    item
                    for item in transition.reference_dispositions
                    if item.record_kind == "claim_assertion"
                    and item.record_id == record_id
                    and item.reference_path == path
                    and item.predecessor == current
                ),
                None,
            )
            if disposition is None:
                continue
            if disposition.disposition == "share_by_explicit_evidence" and len(disposition.successors) != 1:
                raise IdentityLineageError("identity_lineage_claim_fanout_forbidden")
            if len(disposition.successors) != 1:
                raise IdentityLineageError("identity_lineage_current_resolution_missing")
            current = disposition.successors[0]
        return ResolvedLineageReference(
            record_kind="claim_assertion",
            record_id=record_id,
            reference_path=path,
            assertion_reference=assertion_ref,
            resolved_identity=current,
            lineage_snapshot_digest=snapshot,
        )


def replay_identity_lineage(
    state: object,
    *,
    system_time: datetime | None = None,
) -> ReplayedIdentityLineage:
    repository_id = getattr(state, "repository_id", None)
    graph_revision = getattr(state, "graph_revision", None)
    materialized_records = getattr(state, "materialized_records", None)
    event_bindings = getattr(state, "event_bindings", None)
    if not isinstance(repository_id, str) or not isinstance(graph_revision, str) or not isinstance(materialized_records, tuple):
        raise IdentityLineageError("identity_lineage_replay_state_invalid")
    bindings = {item.event_id: item for item in event_bindings or ()}
    graph_before_by_batch: dict[int, str] = {}
    previous_graph_revision = "genesis"
    for binding in sorted(event_bindings or (), key=lambda item: (item.batch_sequence, item.event_offset)):
        graph_before_by_batch.setdefault(binding.batch_sequence, previous_graph_revision)
        previous_graph_revision = binding.graph_revision_after
    lineage_materialized = tuple(
        item
        for item in materialized_records
        if isinstance(getattr(item, "record", None), IdentityLineageRecord)
        and (system_time is None or item.system_valid_from <= system_time)
    )
    if any(item.source_event_id not in bindings for item in lineage_materialized):
        raise IdentityLineageError("identity_lineage_event_binding_missing")
    lineage_materialized = tuple(
        sorted(
            lineage_materialized,
            key=lambda item: (
                bindings[item.source_event_id].batch_sequence,
                bindings[item.source_event_id].event_offset,
            ),
        )
    )
    snapshot = identity_lineage_genesis_digest(repository_id)
    transitions: list[tuple[CompiledIdentityLineageTransition, datetime]] = []
    successor_revisions: set[str] = set()
    redirects: dict[str, tuple[str, ...]] = {}
    for item in lineage_materialized:
        try:
            record = IdentityLineageRecord.model_validate(
                item.record.model_dump(mode="python")
            )
        except (TypeError, ValueError) as exc:
            raise IdentityLineageError("identity_lineage_record_invalid") from exc
        transition = record.transition
        binding = bindings.get(item.source_event_id)
        if binding is None:
            raise IdentityLineageError("identity_lineage_event_binding_missing")
        expected_graph_before = graph_before_by_batch.get(binding.batch_sequence)
        if transition.graph_revision_before != expected_graph_before:
            raise IdentityLineageError("identity_lineage_graph_revision_mismatch")
        if transition.lineage_snapshot_before_digest != snapshot:
            raise IdentityLineageError("identity_lineage_snapshot_prefix_conflict")
        expected_closure = derive_total_reverse_reference_closure(
            materialized_records=tuple(
                candidate
                for candidate in materialized_records
                if candidate.source_event_id in bindings
                and bindings[candidate.source_event_id].batch_sequence
                < binding.batch_sequence
            ),
            predecessors=transition.predecessors,
            recorded_before=item.system_valid_from,
        )
        if any(
            reference not in transition.reverse_reference_closure
            for reference in expected_closure
        ):
            raise IdentityLineageError("identity_lineage_reference_closure_mismatch")
        predecessor_revisions = {
            item.entity_revision_id for item in transition.predecessors
        }
        for successor in transition.successors:
            if _reaches_any(
                successor.entity_revision_id,
                predecessor_revisions,
                redirects,
            ):
                raise IdentityLineageError("identity_lineage_cycle")
        new_revisions = {value.entity_revision_id for value in transition.successors}
        if new_revisions & successor_revisions:
            raise IdentityLineageError("identity_lineage_successor_revision_reused")
        successor_revisions.update(new_revisions)
        for predecessor in transition.predecessors:
            redirects[predecessor.entity_revision_id] = tuple(
                value.entity_revision_id for value in transition.successors
            )
        transitions.append((transition, item.system_valid_from))
        snapshot = transition.lineage_snapshot_after_digest
    return ReplayedIdentityLineage(
        repository_id=repository_id,
        graph_revision=graph_revision,
        transitions=tuple(transitions),
    )


class ProductionIdentityLineageCompiler:
    """Compile only pre-accepted identity IR against one sealed atomic-store snapshot."""

    def __init__(
        self,
        coordinator: object,
        accepted_operation_repository: AcceptedIdentityOperationRepository,
    ) -> None:
        from memorii.core.memory_evolution.transaction_coordinator import (
            SemanticIngestionTransactionCoordinator,
        )

        if not isinstance(coordinator, SemanticIngestionTransactionCoordinator):
            raise TypeError("identity lineage compiler requires the canonical transaction coordinator")
        self._coordinator = coordinator
        if not callable(getattr(accepted_operation_repository, "get_accepted_identity_operation", None)):
            raise TypeError("identity lineage compiler requires the canonical accepted-operation repository")
        self._accepted_operation_repository = accepted_operation_repository

    def compile_transition(self, *, operation: object, candidate: object, source_analysis: object) -> CompiledIdentityLineageTransition:
        operation_id = getattr(operation, "operation_id", None)
        candidate_id = getattr(operation, "candidate_id", None)
        if (
            not isinstance(operation_id, str)
            or getattr(operation, "kind", None) != "identity"
            or getattr(candidate, "candidate_id", None) != candidate_id
            or getattr(source_analysis, "candidate_id", None) != candidate_id
        ):
            raise ValueError("accepted_identity_compiler_input_mismatch")
        artifact = self._accepted_operation_repository.get_accepted_identity_operation(
            operation_id=operation_id,
            sealed_operation_digest=getattr(operation, "sealed_operation_digest", None),
            candidate_digest=getattr(candidate, "candidate_digest", None),
            source_analysis_digest=getattr(source_analysis, "analysis_digest", None),
        )
        if artifact is None:
            raise ValueError("accepted_identity_operation_missing")
        from memorii.core.memory_evolution.graph_records import (
            AcceptedIdentityOperationArtifact,
        )

        artifact = AcceptedIdentityOperationArtifact.model_validate(
            artifact.model_dump(mode="python")
        )
        accepted = artifact.operation
        planning_reader = getattr(
            self._accepted_operation_repository,
            "get_identity_graph_planning_artifact",
            None,
        )
        if callable(planning_reader):
            from memorii.core.memory_evolution.graph_planning import (
                FrozenIdentityGraphPlanningArtifact,
            )

            planned = planning_reader(
                operation_id=operation_id,
                sealed_operation_digest=getattr(
                    operation, "sealed_operation_digest", None
                ),
                candidate_digest=getattr(candidate, "candidate_digest", None),
                source_analysis_digest=getattr(
                    source_analysis, "analysis_digest", None
                ),
            )
            if planned is None:
                raise ValueError("frozen_identity_graph_planning_artifact_missing")
            planned = FrozenIdentityGraphPlanningArtifact.model_validate(planned)
            if planned.accepted_operation_artifact != artifact:
                raise ValueError("frozen_identity_graph_planning_artifact_substituted")
            return planned.compiled_transition

        return self._coordinator.execute(
            lambda snapshot: compile_accepted_identity_transition(snapshot, accepted)
        )


def compile_accepted_identity_transition(
    snapshot: SealedGraphStateSnapshot,
    accepted,
) -> CompiledIdentityLineageTransition:
    """Pure identity compilation against one already-sealed graph authority."""

    from memorii.core.memory_evolution.reference_integrity import (
        ReferenceTarget,
        active_reverse_references,
    )

    graph_state = snapshot.graph_state
    lineage = replay_identity_lineage(graph_state)
    targets = tuple(
        target
        for predecessor in accepted.predecessors
        for target in (
            ReferenceTarget(
                kind="entity_revision", target_id=predecessor.entity_revision_id
            ),
            ReferenceTarget(
                kind="logical_entity", target_id=predecessor.logical_entity_id
            ),
        )
    )
    ledger_edges = active_reverse_references(snapshot.reference_integrity, targets)
    closure = derive_total_reverse_reference_closure(
        materialized_records=graph_state.materialized_records,
        predecessors=accepted.predecessors,
        recorded_before=snapshot.system_as_of,
    )
    covered = {
        (edge.record_kind, edge.record_id, edge.target.target_id)
        for edge in ledger_edges
    }
    for reference in closure:
        if (
            reference.record_kind,
            reference.record_id,
            reference.predecessor.entity_revision_id,
        ) not in covered and (
            reference.record_kind,
            reference.record_id,
            reference.predecessor.logical_entity_id,
        ) not in covered:
            raise ValueError("identity_lineage_reference_ledger_incomplete")
    assignments = {
        item.reference_digest: item for item in accepted.reference_assignments
    }
    dispositions: list[LineageReferenceDisposition] = []
    for reference in closure:
        assignment = assignments.pop(reference.reference_digest, None)
        if reference.lifecycle == "historical":
            if assignment is not None and assignment.disposition != "preserve_historical":
                raise ValueError("identity_lineage_historical_assignment_invalid")
            values = {
                "disposition": "preserve_historical",
                "successors": (),
                "source_evidence": (),
                "basis": "operation_defined_history_preservation",
            }
        elif accepted.operation == "rekey":
            values = {
                "disposition": "redirect_current",
                "successors": accepted.successors,
                "source_evidence": (),
                "basis": "operation_defined_rekey_redirect",
            }
        elif accepted.operation == "merge":
            values = {
                "disposition": "redirect_current",
                "successors": accepted.successors,
                "source_evidence": (),
                "basis": "operation_defined_merge_redirect",
            }
        elif accepted.operation == "split" and assignment is not None:
            values = {
                "disposition": assignment.disposition,
                "successors": assignment.successors,
                "source_evidence": assignment.source_evidence,
                "basis": "source_assignment",
            }
        else:
            raise ValueError("identity_lineage_reference_assignment_missing")
        dispositions.append(
            LineageReferenceDisposition.create(
                reference_digest=reference.reference_digest,
                record_kind=reference.record_kind,
                record_id=reference.record_id,
                reference_path=reference.reference_path,
                predecessor=reference.predecessor,
                **values,
            )
        )
    if assignments:
        raise ValueError("identity_lineage_assignment_outside_closure")
    transition = CompiledIdentityLineageTransition.create(
        operation_id=accepted.operation_id,
        operation=accepted.operation,
        predecessors=accepted.predecessors,
        successors=accepted.successors,
        graph_revision_before=graph_state.graph_revision,
        recorded_at=None,
        lineage_snapshot_before_digest=lineage.snapshot_digest,
        source_evidence=accepted.source_evidence,
        reverse_reference_closure=closure,
        reference_dispositions=tuple(
            sorted(dispositions, key=lambda item: item.reference_digest)
        ),
    )
    redirects = {
        predecessor.entity_revision_id: tuple(
            successor.entity_revision_id for successor in prior.successors
        )
        for prior, _ in lineage.transitions
        for predecessor in prior.predecessors
    }
    predecessor_ids = {
        item.entity_revision_id for item in transition.predecessors
    }
    if any(
        _reaches_any(item.entity_revision_id, predecessor_ids, redirects)
        for item in transition.successors
    ):
        raise ValueError("identity_lineage_cycle")
    return transition


def identity_lineage_audit_view(
    state: object,
    *,
    system_time: datetime | None = None,
) -> IdentityLineageAuditView:
    lineage = replay_identity_lineage(state, system_time=system_time)
    claims = tuple(
        lineage.resolve_claim(item, system_time=system_time)
        for item in getattr(state, "materialized_records", ())
        if isinstance(getattr(item, "record", None), ClaimAssertion)
        and getattr(item.record, "claim_identity", None) is not None
        and (system_time is None or item.system_valid_from <= system_time)
    )
    body = {
        "repository_id": lineage.repository_id,
        "graph_revision": lineage.graph_revision,
        "system_time": system_time,
        "lineage_snapshot_digest": lineage.snapshot_digest,
        "transition_digests": tuple(value.transition_digest for value, _ in lineage.transitions),
        "resolved_claims": tuple(sorted(claims, key=lambda item: item.claim_assertion_id)),
    }
    return IdentityLineageAuditView(
        **body,
        view_digest=sha256(_AUDIT_VIEW_DOMAIN + encode_typed_value(_canonical(body))).hexdigest(),
    )


def scoped_identity_lineage_audit_view(
    state: object,
    *,
    disclosed_event_ids: frozenset[str],
    system_time: datetime | None = None,
) -> IdentityLineageAuditView:
    """Build and digest only the records authorized for this audit request."""

    lineage = replay_identity_lineage(state, system_time=system_time)
    materialized = tuple(
        item
        for item in getattr(state, "materialized_records", ())
        if getattr(item, "source_event_id", None) in disclosed_event_ids
    )
    disclosed_transition_digests = {
        item.record.transition.transition_digest
        for item in materialized
        if isinstance(getattr(item, "record", None), IdentityLineageRecord)
    }
    disclosed_transitions = tuple(
        value
        for value in lineage.transitions
        if value[0].transition_digest in disclosed_transition_digests
    )
    scoped_transition_digests = tuple(
        item.transition_digest for item, _ in disclosed_transitions
    )
    scoped_snapshot_digest = sha256(
        b"memorii.identity-lineage.scoped-snapshot.v1\0"
        + encode_typed_value(
            (lineage.repository_id, system_time, scoped_transition_digests)
        )
    ).hexdigest()
    scoped_graph_revision = "scoped:" + sha256(
        b"memorii.identity-lineage.scoped-graph-revision.v1\0"
        + encode_typed_value(scoped_transition_digests)
    ).hexdigest()
    scoped_lineage = ReplayedIdentityLineage(
        repository_id=lineage.repository_id,
        graph_revision=scoped_graph_revision,
        transitions=disclosed_transitions,
    )
    claims = []
    for item in materialized:
        if (
            not isinstance(getattr(item, "record", None), ClaimAssertion)
            or item.record.claim_identity is None
            or (system_time is not None and item.system_valid_from > system_time)
        ):
            continue
        claim = scoped_lineage.resolve_claim(item, system_time=system_time)
        subject = claim.subject.model_copy(
            update={"lineage_snapshot_digest": scoped_snapshot_digest}
        )
        object_ref = (
            claim.object.model_copy(
                update={"lineage_snapshot_digest": scoped_snapshot_digest}
            )
            if claim.object is not None
            else None
        )
        claims.append(claim.model_copy(update={"subject": subject, "object": object_ref}))
    body = {
        "repository_id": lineage.repository_id,
        "graph_revision": scoped_graph_revision,
        "system_time": system_time,
        "lineage_snapshot_digest": scoped_snapshot_digest,
        "transition_digests": scoped_transition_digests,
        "resolved_claims": tuple(sorted(claims, key=lambda item: item.claim_assertion_id)),
    }
    return IdentityLineageAuditView(
        **body,
        view_digest=sha256(
            _AUDIT_VIEW_DOMAIN + encode_typed_value(_canonical(body))
        ).hexdigest(),
    )


def _reaches_any(start: str, targets: set[str], redirects: dict[str, tuple[str, ...]]) -> bool:
    pending = [start]
    seen: set[str] = set()
    while pending:
        current = pending.pop()
        if current in targets:
            return True
        if current in seen:
            continue
        seen.add(current)
        pending.extend(redirects.get(current, ()))
    return False


def _canonical(value: object) -> object:
    if isinstance(value, BaseModel):
        return _canonical(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_canonical(item) for item in value)
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


__all__ = [
    "GrantBackedIdentityLineageAuditAuthorizer",
    "AtomicStoreScopedIdentityLineageAuditReader",
    "IdentityLineageAuditGrant",
    "IdentityLineageAuditReader",
    "IdentityLineageAuditScopeSnapshot",
    "IdentityLineageAuditView",
    "IdentityLineageError",
    "ProductionIdentityLineageCompiler",
    "ReplayedIdentityLineage",
    "ResolvedClaimLineage",
    "ResolvedLineageReference",
    "derive_claim_reverse_reference_closure",
    "derive_total_reverse_reference_closure",
    "identity_lineage_audit_view",
    "identity_lineage_genesis_digest",
    "replay_identity_lineage",
    "scoped_identity_lineage_audit_view",
]
