"""Host decision wire records and immutable persisted acceptance."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from memorii.core.consolidation.runtime_outputs import (
    ConsolidationOutput,
    EpisodicSummary,
    SemanticCandidate,
    SkillCandidate,
    UserCandidate,
    runtime_delivery_id,
)
from memorii.core.persistence.managed_delivery import (
    DeliveryAuthorityBinding,
    DeliveryRequest,
    ManagedDelivery,
    MemoryPlaneCandidateScope,
    ProtectedSkillCandidateScope,
)
from memorii.core.persistence.runtime_contracts import OperationOrigin, canonical_runtime_digest

_Coordinate = Annotated[str, Field(min_length=1, max_length=512, pattern=r"^[^\x00]+$")]
_Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
CandidateScope = Annotated[
    MemoryPlaneCandidateScope | ProtectedSkillCandidateScope, Field(discriminator="kind")
]
WritebackDeliveryStatus = Literal["pending", "delivering", "delivered", "rejected", "needs_reconciliation"]


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WritebackHostBinding(_Record):
    installation_id: _Coordinate
    client_namespace: _Coordinate
    task_id: _Coordinate


class WritebackDecisionRequest(_Record):
    protocol_version: Literal[1] = 1
    host_binding: WritebackHostBinding
    task_id: _Coordinate
    result_id: _Digest
    output_id: _Digest
    expected_offer_version: int = Field(ge=1, strict=True)
    expected_payload_digest: _Digest
    operation_id: _Coordinate
    decision: Literal["accept", "decline"]

    @model_validator(mode="after")
    def consistent_task(self) -> Self:
        if self.host_binding.task_id != self.task_id:
            raise ValueError("host binding differs from decision task")
        return self

    def intent_digest(self) -> str:
        return canonical_runtime_digest(("memorii.writeback-decision-intent.v1", self.model_dump(mode="json")))


class WritebackDecisionReceipt(_Record):
    decision_id: _Digest
    outcome: Literal["accepted", "declined"]
    offer_version: Literal[2] = 2
    delivery_id: _Digest | None = None
    delivery_status: WritebackDeliveryStatus | None = None

    @model_validator(mode="after")
    def consistent_delivery(self) -> Self:
        if self.outcome == "accepted" and (self.delivery_id is None or self.delivery_status is None):
            raise ValueError("acceptance requires a delivery")
        if self.outcome == "declined" and (self.delivery_id is not None or self.delivery_status is not None):
            raise ValueError("decline cannot have a delivery")
        return self


class RecordedWritebackDecision(_Record):
    request: WritebackDecisionRequest
    origin: OperationOrigin
    authority: DeliveryAuthorityBinding
    decided_at: AwareDatetime
    scope: CandidateScope

    @model_validator(mode="after")
    def verify_bindings(self) -> Self:
        coordinate = self.origin.coordinate
        if (
            coordinate.operation_id != self.request.operation_id
            or coordinate.request_digest != self.request.intent_digest()
            or coordinate.repository_id != self.scope.partition_id
            or self.scope != self.authority.scope
            or self.request.task_id != self.scope.task_id
            or self.request.host_binding.installation_id != coordinate.installation_id
            or self.request.host_binding.client_namespace != coordinate.client_namespace
            or coordinate.installation_id != self.authority.installation_id
            or coordinate.principal != self.authority.principal
            or coordinate.client_namespace != self.authority.client_namespace
        ):
            raise ValueError("writeback decision does not match its immutable operation binding")
        return self

    @property
    def decision_id(self) -> str:
        return canonical_runtime_digest((
            "memorii.writeback-decision.v1",
            self.origin.coordinate.model_dump(mode="json"),
            self.request.result_id,
            self.request.output_id,
        ))

    def initial_delivery(self) -> ManagedDelivery | None:
        if self.request.decision == "decline":
            return None
        coordinate = self.origin.coordinate
        return ManagedDelivery(
            generation_id=coordinate.generation_id,
            request=DeliveryRequest(
                delivery_id=runtime_delivery_id(
                    self.scope.partition_id, "writeback_candidate", self.request.output_id,
                ),
                operation_generation=coordinate.generation_id,
                origin_operation_id=coordinate.operation_id,
                payload_ref=self.request.output_id,
                payload_digest=self.request.expected_payload_digest,
                authority=self.authority,
            ),
        )

    def receipt(self, delivery: ManagedDelivery | None) -> WritebackDecisionReceipt:
        expected = self.initial_delivery()
        if expected is None:
            if delivery is not None:
                raise ValueError("declined writeback unexpectedly has a delivery")
            return WritebackDecisionReceipt(decision_id=self.decision_id, outcome="declined")
        if delivery is None or delivery.request != expected.request or delivery.generation_id != expected.generation_id:
            raise ValueError("accepted writeback has no matching delivery")
        return WritebackDecisionReceipt(
            decision_id=self.decision_id, outcome="accepted",
            delivery_id=delivery.request.delivery_id, delivery_status=delivery.progress.status,
        )


class CandidateDeliveryEntry(_Record):
    record_type: Literal["managed_writeback_candidate"] = "managed_writeback_candidate"
    decision_output_id: _Digest
    delivery: ManagedDelivery

    @model_validator(mode="after")
    def consistent_target(self) -> Self:
        if (
            self.decision_output_id != self.delivery.request.payload_ref
            or not isinstance(
                self.delivery.request.authority.scope, MemoryPlaneCandidateScope | ProtectedSkillCandidateScope,
            )
        ):
            raise ValueError("writeback delivery does not match its sealed candidate scope")
        return self


def candidate_scope(output: ConsolidationOutput, *, partition_id: str, task_id: str) -> CandidateScope | None:
    match output.payload:
        case EpisodicSummary():
            return MemoryPlaneCandidateScope(partition_id=partition_id, task_id=task_id, domain="episodic")
        case SemanticCandidate():
            return MemoryPlaneCandidateScope(partition_id=partition_id, task_id=task_id, domain="semantic")
        case UserCandidate():
            return MemoryPlaneCandidateScope(partition_id=partition_id, task_id=task_id, domain="user")
        case SkillCandidate():
            return ProtectedSkillCandidateScope(partition_id=partition_id, task_id=task_id)
        case _:
            return None
