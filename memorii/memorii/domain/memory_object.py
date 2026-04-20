"""Canonical MemoryObject schema."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from memorii.domain.common import Provenance, RoutingInfo
from memorii.domain.enums import CommitStatus, Durability, MemoryDomain, MemoryScope, TemporalValidityStatus


class MemoryObject(BaseModel):
    memory_id: str
    memory_type: MemoryDomain
    scope: MemoryScope
    durability: Durability
    status: CommitStatus
    content: dict[str, Any]
    provenance: Provenance
    routing: RoutingInfo
    namespace: dict[str, str] | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    validity_status: TemporalValidityStatus | None = None

    model_config = ConfigDict(extra="forbid")
