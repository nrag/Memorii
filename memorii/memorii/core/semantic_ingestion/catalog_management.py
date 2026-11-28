"""Durable standing management policy for one exact agent catalog."""

from __future__ import annotations

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


class CatalogManagementRepository:
    def __init__(self, plane: MemoryPlaneService, *, partition_id: str,
                 scope: AgentLocalCatalogAuthorityScope) -> None:
        self._plane = plane
        self._partition = partition_id
        self._scope = scope
        self._key = "catalog-management:" + contract_digest(
            b"memorii.catalog-management.v1", (partition_id, scope.model_dump(mode="json")),
        )

    def _read(self) -> tuple[CanonicalMemoryRecord | None, CatalogManagementPolicy | None]:
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
            policy = CatalogManagementPolicy.model_validate(raw)
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
    def _status(policy: CatalogManagementPolicy | None) -> dict[str, object]:
        if policy is None:
            return {"state": "disabled", "generation": 0, "origin": None}
        return {"state": policy.state, "generation": policy.generation, "origin": policy.origin}

    def status(self) -> dict[str, object]:
        _, policy = self._read()
        return self._status(policy)

    def set_state(self, state: Literal["enabled", "paused"]) -> dict[str, object]:
        if state not in ("enabled", "paused"):
            raise ValueError("invalid catalog management state")
        previous, policy = self._read()
        if policy is not None and policy.state == state:
            return self._status(policy)
        replacement = CatalogManagementPolicy(
            schema_version=1, partition_id=self._partition, catalog_scope=self._scope,
            state=state, generation=1 if policy is None else policy.generation + 1, origin="local_operator",
        )
        record = CanonicalMemoryRecord(
            memory_id=self._key, domain=MemoryDomain.EXECUTION,
            text=state, content={"policy": replacement.model_dump(mode="json")},
            status=CommitStatus.COMMITTED, source_kind=_KIND,
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL, timestamp=datetime.now(UTC),
        )
        condition = (
            RecordAbsentPrecondition(memory_id=self._key) if previous is None
            else RecordDigestPrecondition(memory_id=self._key, expected_digest=record_digest(previous))
        )
        try:
            self._plane.conditionally_write_records((record,), preconditions=(condition,))
        except MemoryPlaneRevisionConflictError as exc:
            _, winner = self._read()
            if winner is not None and winner.state == state:
                return self._status(winner)
            raise ValueError("catalog management policy changed concurrently") from exc
        return self._status(replacement)
