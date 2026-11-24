"""Owner-reviewed refusal of an unresolved, prior-generation delivery."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from memorii.core.persistence.contracts import InstallationControlState, RuntimePublicationState
from memorii.core.persistence.managed_delivery import (
    DeliveredDelivery,
    DeliveryRestoreHold,
    DeliveryRestoreRejection,
    RejectedDelivery,
)
from memorii.core.persistence.runtime_api import convert_legacy_outbox_record
from memorii.core.persistence.runtime_contracts import canonical_runtime_digest
from memorii.core.persistence.runtime_repository import RuntimeStateRepository, publish_runtime_change
from memorii.core.persistence.writeback_decisions import CandidateDeliveryEntry
from memorii.core.storage_administration.operator import OperatorError, OwnerCapability, require_owner_capability
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.core.work_state.runtime_projection import ManagedWorkProjectionDelivery
from memorii.stores.sqlite.partition import PartitionDataRepository

_Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
_Identity = Annotated[str, Field(min_length=1, max_length=512)]


class DeliveryRejectionPlan(BaseModel):
    installation_id: _Identity
    partition_id: _Identity
    generation_id: _Identity
    hold_id: _Digest
    delivery_id: _Identity
    expected_control_revision: int = Field(ge=1)
    expected_publication_digest: _Digest
    expected_hold_state: Literal["needs_reconciliation"] = "needs_reconciliation"
    decision: Literal["reject"] = "reject"
    evidence_digest: _Digest

    model_config = ConfigDict(extra="forbid", frozen=True)

    def digest(self) -> str:
        return canonical_runtime_digest(self.model_dump(mode="json"))

    def decision_id(self) -> str:
        return canonical_runtime_digest(("delivery_restore_rejection", self.hold_id, self.delivery_id))


class DeliveryReconciliationOperator:
    def __init__(self, administration: StorageAdministrationService) -> None:
        self._administration = administration

    def plan_rejection(self, *, capability: OwnerCapability, delivery_id: str) -> DeliveryRejectionPlan:
        service = self._administration
        require_owner_capability(service, capability)
        with service.verified_operation_context() as (state, finalized):
            partition = service.partition()
            with partition.transaction(write=False) as connection:
                return self._plan(connection, partition, state, finalized, delivery_id)

    def reject(
        self, *, capability: OwnerCapability, plan: DeliveryRejectionPlan, plan_digest: str,
    ) -> DeliveryRestoreRejection:
        service = self._administration
        require_owner_capability(service, capability)
        if plan.digest() != plan_digest:
            raise OperatorError("conflict: delivery rejection plan digest changed")
        authority: list[tuple[InstallationControlState, RuntimePublicationState]] = []
        result: list[DeliveryRestoreRejection] = []

        def authorize(state: InstallationControlState, publication: RuntimePublicationState) -> None:
            require_owner_capability(service, capability)
            if (
                state.mode == "bypass"
                or publication.installation_id != plan.installation_id
                or publication.repository_id != plan.partition_id
                or publication.data_generation_id != plan.generation_id
            ):
                raise OperatorError("conflict: delivery rejection belongs to another verified generation")
            authority.append((state, publication))

        def apply(connection: sqlite3.Connection, repository: RuntimeStateRepository) -> None:
            partition = repository.partition
            existing = self._read_hold_record(connection, plan.decision_id())
            if existing is not None:
                decision = DeliveryRestoreRejection.model_validate_json(existing)
                if decision.plan_digest != plan_digest:
                    raise OperatorError("conflict: delivery already has a different owner decision")
                result.append(decision)
                return
            state, publication = authority[0]
            if self._plan(connection, partition, state, publication, plan.delivery_id) != plan:
                raise OperatorError("conflict: held delivery or control watermark changed after review")
            decision = DeliveryRestoreRejection(
                record_id=plan.decision_id(), hold_id=plan.hold_id, installation_id=plan.installation_id,
                partition_id=plan.partition_id, restored_generation_id=plan.generation_id,
                delivery_id=plan.delivery_id, control_revision=state.control_revision,
                evidence_digest=plan.evidence_digest, plan_digest=plan_digest,
            )
            partition.insert_delivery_restore_hold(connection, hold_id=decision.record_id, record_json=decision.model_dump_json())
            result.append(decision)

        publish_runtime_change(service, apply, operation_binding="migrate", validate_authority=authorize)
        return result[0]

    def _plan(
        self,
        connection: sqlite3.Connection,
        partition: PartitionDataRepository,
        state: InstallationControlState,
        finalized: RuntimePublicationState,
        delivery_id: str,
    ) -> DeliveryRejectionPlan:
        change = self._administration._control.read_generation_change(finalized.repository_id)
        if (
            state.mode == "bypass" or change is None or change.phase != "finalized"
            or change.candidate_publication.data_generation_id != finalized.data_generation_id
            or not partition.supports_runtime_replay_checkpoints(connection)
        ):
            raise OperatorError("not_found: no active restore delivery hold")
        raw_hold = self._read_hold_record(connection, change.preview_digest)
        if raw_hold is None:
            raise OperatorError("integrity_error: current generation is missing its delivery hold")
        hold = DeliveryRestoreHold.model_validate_json(raw_hold)
        if (
            hold.restored_generation_id != finalized.data_generation_id
            or hold.installation_id != finalized.installation_id or hold.partition_id != finalized.repository_id
            or hold.live_publication_digest != change.old_publication.payload_digest()
        ):
            raise OperatorError("integrity_error: current delivery hold does not match the generation change")
        row = partition.read_runtime_row(
            connection, table="runtime_outbox_deliveries", match=(("delivery_id", delivery_id),),
        )
        if row is None:
            raise OperatorError("not_found: held delivery does not exist")
        raw = str(row["record_json"])
        self._require_held_delivery(raw, delivery_id=delivery_id, finalized=finalized)
        receipt = partition.read_delivery_record(
            connection, catalog="runtime_target_receipts", record_id=delivery_id,
        )
        return DeliveryRejectionPlan(
            installation_id=finalized.installation_id, partition_id=finalized.repository_id,
            generation_id=finalized.data_generation_id, hold_id=hold.hold_id, delivery_id=delivery_id,
            expected_control_revision=state.control_revision, expected_publication_digest=finalized.payload_digest(),
            evidence_digest=canonical_runtime_digest((
                hold.model_dump(mode="json"),
                hashlib.sha256(raw.encode()).hexdigest(),
                None if receipt is None else hashlib.sha256(receipt.encode()).hexdigest(),
            )),
        )

    @staticmethod
    def _read_hold_record(connection: sqlite3.Connection, record_id: str) -> str | None:
        row = connection.execute(
            "SELECT record_json FROM runtime_delivery_restore_holds WHERE hold_id = ?", (record_id,),
        ).fetchone()
        return None if row is None else str(row[0])

    @staticmethod
    def _require_held_delivery(raw: str, *, delivery_id: str, finalized: RuntimePublicationState) -> None:
        try:
            legacy = convert_legacy_outbox_record(delivery_id, raw)
            if legacy is not None:
                return
            discriminator = json.loads(raw)["record_type"]
            entry = (
                ManagedWorkProjectionDelivery.model_validate_json(raw) if discriminator == "managed_work_projection"
                else CandidateDeliveryEntry.model_validate_json(raw)
            )
        except (KeyError, ValueError, ValidationError) as exc:
            raise OperatorError("integrity_error: malformed held delivery") from exc
        delivery = entry.delivery
        if (
            delivery.request.delivery_id != delivery_id
            or delivery.request.authority.installation_id != finalized.installation_id
            or delivery.request.authority.scope.partition_id != finalized.repository_id
        ):
            raise OperatorError("integrity_error: held delivery does not match its scope")
        if delivery.generation_id == finalized.data_generation_id:
            raise OperatorError("conflict: current-generation delivery is outside this restore hold")
        if isinstance(delivery.progress, DeliveredDelivery | RejectedDelivery):
            raise OperatorError("conflict: terminal managed delivery is outside this restore hold")
