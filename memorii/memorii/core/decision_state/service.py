"""Deterministic CRUD service for explicit decision states."""

from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.decision_state.models import (
    DecisionCriterion,
    DecisionEvidence,
    DecisionEvidencePolarity,
    DecisionOption,
    DecisionState,
    DecisionStatus,
)
from memorii.core.decision_state.store import DecisionStateStore, InMemoryDecisionStateStore


class DecisionStateService:
    def __init__(self, store: DecisionStateStore | None = None) -> None:
        self._store = store or InMemoryDecisionStateStore()

    def open_decision(
        self,
        *,
        question: str,
        decision_id: str | None = None,
        work_state_id: str | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
        constraints: list[str] | None = None,
        unresolved_questions: list[str] | None = None,
    ) -> DecisionState:
        timestamp = datetime.now(UTC)
        resolved_decision_id = decision_id or self._build_decision_id(timestamp=timestamp)
        decision = DecisionState(
            decision_id=resolved_decision_id,
            work_state_id=work_state_id,
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            question=question,
            options=[],
            criteria=[],
            constraints=list(constraints or []),
            evidence=[],
            current_recommendation=None,
            unresolved_questions=list(unresolved_questions or []),
            final_decision=None,
            status=DecisionStatus.OPEN,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._store.upsert_decision(decision)
        return decision

    def add_option(
        self,
        *,
        decision_id: str,
        option_id: str,
        label: str,
        description: str | None = None,
    ) -> DecisionState | None:
        decision = self._store.get_decision(decision_id)
        if decision is None:
            return None
        option = DecisionOption(option_id=option_id, label=label, description=description)
        return self._persist_updated(decision, options=[*decision.options, option])

    def add_criterion(
        self,
        *,
        decision_id: str,
        criterion_id: str,
        label: str,
        weight: float = 1.0,
    ) -> DecisionState | None:
        decision = self._store.get_decision(decision_id)
        if decision is None:
            return None
        criterion = DecisionCriterion(criterion_id=criterion_id, label=label, weight=weight)
        return self._persist_updated(decision, criteria=[*decision.criteria, criterion])

    def add_evidence(
        self,
        *,
        decision_id: str,
        evidence_id: str,
        content: str,
        polarity: DecisionEvidencePolarity,
        option_id: str | None = None,
        source_ids: list[str] | None = None,
    ) -> DecisionState | None:
        decision = self._store.get_decision(decision_id)
        if decision is None:
            return None
        evidence = DecisionEvidence(
            evidence_id=evidence_id,
            content=content,
            option_id=option_id,
            polarity=polarity,
            source_ids=list(source_ids or []),
        )
        return self._persist_updated(decision, evidence=[*decision.evidence, evidence])

    def update_recommendation(
        self,
        *,
        decision_id: str,
        recommendation: str | None,
    ) -> DecisionState | None:
        decision = self._store.get_decision(decision_id)
        if decision is None:
            return None
        return self._persist_updated(decision, current_recommendation=recommendation)

    def record_final_decision(self, *, decision_id: str, final_decision: str) -> DecisionState | None:
        decision = self._store.get_decision(decision_id)
        if decision is None:
            return None
        return self._persist_updated(
            decision,
            final_decision=final_decision,
            status=DecisionStatus.DECIDED,
        )

    def abandon_decision(self, *, decision_id: str) -> DecisionState | None:
        decision = self._store.get_decision(decision_id)
        if decision is None:
            return None
        return self._persist_updated(decision, status=DecisionStatus.ABANDONED)

    def get_decision(self, decision_id: str) -> DecisionState | None:
        return self._store.get_decision(decision_id)

    def list_decisions(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        work_state_id: str | None = None,
        statuses: list[DecisionStatus] | None = None,
    ) -> list[DecisionState]:
        return self._store.list_decisions(
            session_id=session_id,
            task_id=task_id,
            work_state_id=work_state_id,
            statuses=statuses,
        )

    def _persist_updated(self, decision: DecisionState, **updates: object) -> DecisionState:
        updated = decision.model_copy(update={**updates, "updated_at": datetime.now(UTC)})
        self._store.upsert_decision(updated)
        return updated

    def _build_decision_id(self, *, timestamp: datetime) -> str:
        existing_count = len(self._store.list_decisions())
        return f"decision:{timestamp.timestamp()}:{existing_count}"
