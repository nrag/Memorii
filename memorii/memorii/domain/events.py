"""Event model schemas for immutable event log records."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from memorii.domain.enums import EventType


class EventRecord(BaseModel):
    event_id: str
    event_type: EventType
    timestamp: datetime
    task_id: str
    execution_node_id: str | None = None
    solver_graph_id: str | None = None
    actor_id: str | None = None
    source: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    dedupe_key: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")
