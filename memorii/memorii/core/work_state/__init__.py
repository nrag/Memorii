"""Shared work-state models and passive detection service."""

from memorii.core.work_state.detector import WorkStateDetector
from memorii.core.work_state.models import (
    AgentEventEnvelope,
    WorkStateDetectionAction,
    WorkStateDetectionDecision,
    WorkStateKind,
    WorkStateReasonCode,
    WorkStateRecord,
    WorkStateStatus,
)
from memorii.core.work_state.service import WorkStateService

__all__ = [
    "AgentEventEnvelope",
    "WorkStateDetectionAction",
    "WorkStateDetectionDecision",
    "WorkStateDetector",
    "WorkStateKind",
    "WorkStateReasonCode",
    "WorkStateRecord",
    "WorkStateService",
    "WorkStateStatus",
]
