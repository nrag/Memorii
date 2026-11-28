"""Durable standing management policy for one exact agent catalog."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    MemoryPlaneRevisionConflictError,
    RecordAbsentPrecondition,
    RecordDigestPrecondition,
    record_digest,
)
from memorii.core.semantic_ingestion.catalog_authority import AgentLocalCatalogAuthorityScope
from memorii.core.semantic_ingestion.contracts import contract_digest
from memorii.core.semantic_ingestion.learned_relation import (
    ActivationPolicy,
    CatalogManagementUnavailable,
    LearnedRelationRuntime,
    OrdinarySemanticReplayWriter,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility

_KIND = "catalog_management_policy_v1"


class CatalogManagementPolicy(BaseModel):
    schema_version: Literal[1]
    partition_id: str = Field(min_length=1)
    catalog_scope: AgentLocalCatalogAuthorityScope
    state: Literal["enabled", "paused"]
    generation: int = Field(ge=1, strict=True)
    origin: Literal["local_operator"]

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ManagedCatalogEnrollmentDecision(BaseModel):
    """A decision verified by the trusted workspace enrollment control plane."""

    partition_id: str = Field(min_length=1)
    catalog_scope: AgentLocalCatalogAuthorityScope
    state: Literal["enabled", "paused"]
    enrollment_revision: int = Field(ge=1)

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _ManagedCatalogPolicy(ManagedCatalogEnrollmentDecision):
    schema_version: Literal[2]
    origin: Literal["managed_host"]
    generation: int = Field(ge=1)


class ManagedCatalogEnrollmentReceipt(ManagedCatalogEnrollmentDecision):
    """Acknowledgment for the exact enrollment revision persisted by Memorii."""

    generation: int = Field(ge=1)


class CatalogManagementRepository:
    def __init__(self, plane: MemoryPlaneService, *, partition_id: str,
                 scope: AgentLocalCatalogAuthorityScope) -> None:
        self._plane = plane
        self._partition = partition_id
        self._scope = scope
        self._key = "catalog-management:" + contract_digest(
            b"memorii.catalog-management.v1", (partition_id, scope.model_dump(mode="json")),
        )

    def _read(self) -> tuple[CanonicalMemoryRecord | None, CatalogManagementPolicy | _ManagedCatalogPolicy | None]:
        record = self._plane.get_record(self._key)
        if record is None:
            return None, None
        try:
            if (record.source_kind != _KIND or record.domain != MemoryDomain.EXECUTION
                    or record.status != CommitStatus.COMMITTED
                    or record.visibility != MemoryRecordVisibility.INTERNAL_CONTROL
                    or set(record.content) != {"policy"}):
                raise ValueError("invalid catalog management record")
            raw = record.content["policy"]
            if not isinstance(raw, dict) or type(raw.get("schema_version")) is not int:
                raise ValueError("invalid catalog management schema")
            policy = (
                _ManagedCatalogPolicy.model_validate(raw)
                if raw["schema_version"] == 2
                else CatalogManagementPolicy.model_validate(raw)
            )
            if (
                policy.model_dump(mode="json") != raw
                or policy.partition_id != self._partition
                or policy.catalog_scope != self._scope
                or record.text != policy.state
            ):
                raise ValueError("invalid catalog management coordinate")
            return record, policy
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid catalog management policy") from exc

    @staticmethod
    def _status(policy: CatalogManagementPolicy | _ManagedCatalogPolicy | None) -> dict[str, object]:
        if policy is None:
            return {"state": "disabled", "generation": 0, "origin": None}
        return {"state": policy.state, "generation": policy.generation, "origin": policy.origin}

    def status(self) -> dict[str, object]:
        _, policy = self._read()
        return self._status(policy)

    def enabled_write_fence(self, scope: AgentLocalCatalogAuthorityScope) -> RecordDigestPrecondition | None:
        """Pin local consent for a write in the same memory plane."""
        if scope != self._scope:
            return None
        record, policy = self._read()
        if record is None or not isinstance(policy, CatalogManagementPolicy) or policy.state != "enabled":
            return None
        return RecordDigestPrecondition(memory_id=self._key, expected_digest=record_digest(record))

    def set_state(self, state: Literal["enabled", "paused"]) -> dict[str, object]:
        if state not in ("enabled", "paused"):
            raise ValueError("invalid catalog management state")
        previous, policy = self._read()
        if isinstance(policy, _ManagedCatalogPolicy):
            raise ValueError("managed catalog policy requires the enrollment authority")
        if policy is not None and policy.state == state:
            return self._status(policy)
        replacement = CatalogManagementPolicy(
            schema_version=1, partition_id=self._partition, catalog_scope=self._scope,
            state=state, generation=1 if policy is None else policy.generation + 1, origin="local_operator",
        )
        try:
            self._write(previous, replacement)
        except MemoryPlaneRevisionConflictError as exc:
            _, winner = self._read()
            if isinstance(winner, CatalogManagementPolicy) and winner.state == state:
                return self._status(winner)
            raise ValueError("catalog management policy changed concurrently") from exc
        return self._status(replacement)

    def _write(
        self, previous: CanonicalMemoryRecord | None, replacement: CatalogManagementPolicy | _ManagedCatalogPolicy,
        *, verify_current: Callable[[], None] | None = None,
    ) -> None:
        record = CanonicalMemoryRecord(
            memory_id=self._key, domain=MemoryDomain.EXECUTION,
            text=replacement.state, content={"policy": replacement.model_dump(mode="json")},
            status=CommitStatus.COMMITTED, source_kind=_KIND,
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL, timestamp=datetime.now(UTC),
        )
        condition = (
            RecordAbsentPrecondition(memory_id=self._key) if previous is None
            else RecordDigestPrecondition(memory_id=self._key, expected_digest=record_digest(previous))
        )
        self._plane.conditionally_write_records(
            (record,), preconditions=(condition,), transaction_precondition=verify_current,
        )


class ManagedCatalogAuthorityError(ValueError):
    """A scoped enrollment decision could not authorize catalog management."""


class ManagedCatalogProvisioning:
    """Control-plane port composed with one verified workspace memory plane.

    The host verifier supplies current decisions from the enrollment owner.
    It must support revalidation during a write without calling this plane.
    """

    def __init__(
        self, plane: MemoryPlaneService, *, partition_id: str, scope: AgentLocalCatalogAuthorityScope,
        verify_enrollment: Callable[[], ManagedCatalogEnrollmentDecision | None],
    ) -> None:
        if not plane.is_durable_store:
            raise ManagedCatalogAuthorityError("managed catalog provisioning requires durable workspace storage")
        self._plane = plane
        self._repository = CatalogManagementRepository(plane, partition_id=partition_id, scope=scope)
        self._partition = partition_id
        self._scope = scope
        self._verify_enrollment = verify_enrollment

    def _current_decision(self) -> ManagedCatalogEnrollmentDecision:
        decision = self._verify_enrollment()
        if (
            type(decision) is not ManagedCatalogEnrollmentDecision
            or decision.partition_id != self._partition
            or decision.catalog_scope != self._scope
        ):
            raise ManagedCatalogAuthorityError("verified catalog enrollment is unavailable")
        try:
            return ManagedCatalogEnrollmentDecision.model_validate(decision.model_dump())
        except ValueError as exc:
            raise ManagedCatalogAuthorityError("verified catalog enrollment is invalid") from exc

    def reconcile(self) -> ManagedCatalogEnrollmentReceipt:
        """Persist current host intent and acknowledge its durable grant generation."""
        decision = self._current_decision()
        previous, policy = self._repository._read()
        if isinstance(policy, CatalogManagementPolicy):
            raise ManagedCatalogAuthorityError("local catalog policy requires the operator")
        if policy is not None and decision.enrollment_revision <= policy.enrollment_revision:
            if self._matches(policy, decision):
                return self._receipt(policy)
            raise ManagedCatalogAuthorityError("catalog enrollment revision is stale or conflicting")
        replacement = _ManagedCatalogPolicy(
            partition_id=decision.partition_id, catalog_scope=decision.catalog_scope,
            state=decision.state, enrollment_revision=decision.enrollment_revision,
            schema_version=2, origin="managed_host",
            generation=1 if policy is None else policy.generation + 1,
        )

        def verify_current() -> None:
            if self._current_decision() != decision:
                raise ManagedCatalogAuthorityError("catalog enrollment changed before the write")

        try:
            self._repository._write(previous, replacement, verify_current=verify_current)
        except MemoryPlaneRevisionConflictError as exc:
            _, winner = self._repository._read()
            if isinstance(winner, _ManagedCatalogPolicy) and self._matches(winner, decision):
                return self._receipt(winner)
            raise ManagedCatalogAuthorityError("catalog enrollment changed concurrently") from exc
        return self._receipt(replacement)

    @staticmethod
    def _receipt(policy: _ManagedCatalogPolicy) -> ManagedCatalogEnrollmentReceipt:
        return ManagedCatalogEnrollmentReceipt(
            partition_id=policy.partition_id, catalog_scope=policy.catalog_scope,
            state=policy.state, enrollment_revision=policy.enrollment_revision,
            generation=policy.generation,
        )

    @staticmethod
    def _matches(policy: _ManagedCatalogPolicy, decision: ManagedCatalogEnrollmentDecision) -> bool:
        return policy.enrollment_revision == decision.enrollment_revision and policy.state == decision.state

    def enabled_write_fence(self, scope: AgentLocalCatalogAuthorityScope) -> RecordDigestPrecondition | None:
        if scope != self._scope:
            return None
        try:
            decision = self._current_decision()
        except ManagedCatalogAuthorityError:
            return None
        record, policy = self._repository._read()
        if (
            record is None or not isinstance(policy, _ManagedCatalogPolicy)
            or decision.state != "enabled" or not self._matches(policy, decision)
        ):
            return None
        return RecordDigestPrecondition(memory_id=record.memory_id, expected_digest=record_digest(record))

    def _require_current_binding(self) -> None:
        """Check the live host prerequisite at transaction admission."""
        try:
            decision = self._current_decision()
        except ManagedCatalogAuthorityError as exc:
            raise CatalogManagementUnavailable("managed catalog enrollment is unavailable") from exc
        if decision.state != "enabled":
            raise CatalogManagementUnavailable("managed catalog enrollment is paused")

    def build_learned_runtime(self, *, replay_writer: OrdinarySemanticReplayWriter) -> LearnedRelationRuntime:
        """Compose the agent-local learner with this partition and grant owner."""
        owner = ActivationPolicy(owner_principal_id=self._scope.principal_id, owner_agent_id=self._scope.agent_id)
        return LearnedRelationRuntime(
            memory_plane=self._plane,
            replay_writer=replay_writer,
            policy_for_scope=lambda _scope: owner,
            management_fence_for_scope=self.enabled_write_fence,
            validate_management_host=self._require_current_binding,
            bound_scope=self._scope,
        )
