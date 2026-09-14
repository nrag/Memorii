"""Design-only shape and retained-state proof; no signature or wire codec."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.graph_ingestion_time_contracts import (
    ProductionIngestionTimeAttestation,
    SourceRetentionTimeAttestation,
)
from memorii.core.memory_evolution.graph_observation_public_contracts import (
    IngestionTimeAttestationRequestCoordinates,
)
from memorii.core.memory_evolution.graph_observation_records import Digest, Identifier


class IngestionTimeAttestationCursorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal[1]
    stream_position: int = Field(ge=0)
    preceding_attestation_kind: Literal["source_retention", "transaction_group_commit"] | None
    preceding_attestation_id: Identifier | None
    preceding_attestation_digest: Digest | None
    request: IngestionTimeAttestationRequestCoordinates
    page_policy_revision: Identifier
    page_policy_digest: Digest
    caller_context_digest: Digest
    authorization_decision_digest: Digest
    authorization_expires_at: datetime
    cohort_digest: Digest
    snapshot_token: Identifier
    snapshot_write_revision: int = Field(ge=0)
    signature: str = Field(pattern=r"^[0-9a-f]{128}$")

    @model_validator(mode="before")
    @classmethod
    def reject_boolean_version(cls, value: object) -> object:
        if isinstance(value, Mapping) and isinstance(value.get("schema_version"), bool):
            raise ValueError("schema version is not an integer literal")
        return value

    @model_validator(mode="after")
    def validate_predecessor(self):
        triple = (self.preceding_attestation_kind, self.preceding_attestation_id,
                  self.preceding_attestation_digest)
        if (self.stream_position == 0 and triple != (None, None, None)) or (
            self.stream_position > 0 and any(item is None for item in triple)
        ):
            raise ValueError("predecessor is invalid")
        offset = self.authorization_expires_at.utcoffset()
        if offset is None or offset.total_seconds() != 0:
            raise ValueError("expiry must be aware UTC")
        return self


def attestation_key(value: ProductionIngestionTimeAttestation) -> tuple[str, str, str, str, str]:
    group = "" if isinstance(value, SourceRetentionTimeAttestation) else value.transaction_group_id
    return (value.kind, value.source_id, value.operation_fence_id, group, value.attestation_id)


@dataclass(frozen=True)
class RetainedContinuation:
    issued: IngestionTimeAttestationCursorPayload
    stream: tuple[ProductionIngestionTimeAttestation, ...]
    retention_deadline: datetime


def continue_verified_cursor(
    payload: object, *, retained: RetainedContinuation,
    request: IngestionTimeAttestationRequestCoordinates,
    current_write_revision: int, now: datetime,
    context_digest: str, decision_digest: str, decision_expires_at: datetime,
    policy_revision: str, policy_digest: str,
) -> tuple[ProductionIngestionTimeAttestation, ...]:
    """Only tests post-cryptographic typed coordinates, never grants authority."""
    cursor = IngestionTimeAttestationCursorPayload.model_validate(payload)
    if (
        cursor.request != request or cursor.request != retained.issued.request
        or cursor.caller_context_digest != context_digest
        or cursor.authorization_decision_digest != decision_digest
        or cursor.authorization_expires_at != decision_expires_at
        or cursor.page_policy_revision != policy_revision or cursor.page_policy_digest != policy_digest
        or now >= decision_expires_at or now >= retained.retention_deadline
        or cursor.snapshot_write_revision != current_write_revision
        or cursor.snapshot_token != retained.issued.snapshot_token
        or cursor.cohort_digest != retained.issued.cohort_digest
        or cursor.model_dump(exclude={"signature"}) != retained.issued.model_dump(exclude={"signature"})
    ):
        raise ValueError("stale cursor")
    keys = tuple(attestation_key(item) for item in retained.stream)
    if keys != tuple(sorted(set(keys))):
        raise ValueError("invalid ordered stream")
    position = cursor.stream_position
    if not 0 < position < len(retained.stream):
        raise ValueError("invalid continuation position")
    previous = retained.stream[position - 1]
    if (previous.kind, previous.attestation_id, previous.attestation_digest) != (
        cursor.preceding_attestation_kind, cursor.preceding_attestation_id,
        cursor.preceding_attestation_digest,
    ):
        raise ValueError("invalid retained predecessor")
    return retained.stream[position:position + request.total_page_size]


def cursor_schema(endpoint: str) -> str:
    return {"graph_observation": "GraphObservationCursorPayload",
            "ingestion_time_attestation": "IngestionTimeAttestationCursorPayload"}[endpoint]


def failure_dispatch(*, continuation: bool, authorized: bool = True,
                     size_allowed: bool = True, cursor_valid: bool = True,
                     revisions_current: bool = True, request_matches: bool = True,
                     retained: bool = True) -> str | None:
    if not authorized:
        return "revoked_access" if continuation else "denied"
    if not size_allowed:
        return "denied"
    if continuation and not cursor_valid:
        return "invalid_cursor"
    if not revisions_current:
        return "stale_cursor" if continuation else "denied"
    if continuation and not request_matches:
        return "invalid_cursor"
    if continuation and not retained:
        return "stale_cursor"
    return None


class RetentionReservations:
    """Design proof of count/byte reservation; full runtime lifecycle is a gate."""

    def __init__(self, *, total_tokens: int, tenant_tokens: int, total_bytes: int, tenant_bytes: int):
        values = (total_tokens, tenant_tokens, total_bytes, tenant_bytes)
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("invalid capacity")
        self.limits = values
        self.entries: dict[str, tuple[str, int]] = {}
        self.lock = RLock()

    def reserve(self, token: str, tenant: str, size: int) -> bool:
        with self.lock:
            if type(size) is not int or size <= 0 or token in self.entries:
                raise ValueError("invalid reservation")
            mine = tuple(value for value in self.entries.values() if value[0] == tenant)
            total_tokens, tenant_tokens, total_bytes, tenant_bytes = self.limits
            if (len(self.entries) >= total_tokens or len(mine) >= tenant_tokens
                    or sum(value[1] for value in self.entries.values()) + size > total_bytes
                    or sum(value[1] for value in mine) + size > tenant_bytes):
                return False
            self.entries[token] = (tenant, size)
            return True

    def release(self, token: str) -> None:
        with self.lock:
            del self.entries[token]
