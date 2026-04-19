"""Canonical MemoryObject schema."""

from typing import Any

from pydantic import BaseModel, ConfigDict

from memorii.domain.common import Provenance, RoutingInfo
from memorii.domain.enums import CommitStatus, Durability, MemoryDomain, MemoryScope


class MemoryObject(BaseModel):
    memory_id: str
    memory_type: MemoryDomain
    scope: MemoryScope
    durability: Durability
    status: CommitStatus
    content: dict[str, Any]
    provenance: Provenance
    routing: RoutingInfo

    model_config = ConfigDict(extra="forbid")
