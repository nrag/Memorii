"""Shared work-state models and passive detection service."""

from memorii.core.work_state.detector import WorkStateDetector
from memorii.core.work_state.models import (
    AgentEventEnvelope,
    WorkStateBinding,
    WorkStateBindingStatus,
    WorkStateDetectionAction,
    WorkStateDetectionDecision,
    WorkStateKind,
    WorkStateReasonCode,
    WorkStateRecord,
    WorkStateStatus,
)
from memorii.core.work_state.service import WorkStateService
from memorii.core.work_state.store import InMemoryWorkStateStore, JsonlWorkStateStore, WorkStateStore

__all__ = [
    "AgentEventEnvelope",
    "WorkStateBinding",
    "WorkStateBindingStatus",
    "WorkStateDetectionAction",
    "WorkStateDetectionDecision",
    "WorkStateDetector",
    "WorkStateKind",
    "WorkStateReasonCode",
    "WorkStateRecord",
    "WorkStateService",
    "WorkStateStore",
    "InMemoryWorkStateStore",
    "JsonlWorkStateStore",
    "WorkStateStatus",
]
