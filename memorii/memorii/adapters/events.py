"""Adapter-facing ingestion event contracts."""

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.execution import RuntimeObservationInput
from memorii.domain.routing import InboundEventClass


class HarnessEvent(BaseModel):
    """Canonical event payload accepted from harness adapters."""

    event_id: str
    event_type: InboundEventClass
    task_id: str
    payload: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


def to_runtime_observation(event: HarnessEvent) -> RuntimeObservationInput:
    return RuntimeObservationInput(
        event_id=event.event_id,
        event_class=event.event_type,
        payload=event.payload,
        source="adapter",
    )
