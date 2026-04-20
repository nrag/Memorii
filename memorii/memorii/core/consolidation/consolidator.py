"""Consolidation pipeline that emits typed writeback candidates only."""

from datetime import UTC, datetime
from typing import Any

from memorii.core.consolidation.policies import ConsolidationPolicy
from memorii.domain.common import Provenance
from memorii.domain.enums import MemoryDomain, SourceType
from memorii.domain.routing import ValidationState
from memorii.domain.writebacks import ValidityWindow, WritebackCandidate, WritebackType


class Consolidator:
    def __init__(self, policy: ConsolidationPolicy | None = None) -> None:
        self._policy = policy or ConsolidationPolicy()

    def from_solver_resolution(
        self,
        *,
        candidate_id: str,
        task_id: str,
        solver_run_id: str,
        execution_node_id: str,
        summary: str,
        source_refs: list[str],
    ) -> WritebackCandidate:
        return self._build_candidate(
            candidate_id=candidate_id,
            writeback_type=WritebackType.EPISODIC,
            target_domain=MemoryDomain.EPISODIC,
            content={"summary": summary},
            source_refs=source_refs,
            task_id=task_id,
            solver_run_id=solver_run_id,
            execution_node_id=execution_node_id,
            eligibility_reason="solver_resolved",
            validation_state=ValidationState.VALIDATED,
        )

    def from_validated_abstraction(
        self,
        *,
        candidate_id: str,
        task_id: str,
        abstraction: str,
        source_refs: list[str],
        is_validated: bool,
        is_speculative: bool,
    ) -> WritebackCandidate | None:
        if not self._policy.allow_writeback(
            domain=MemoryDomain.SEMANTIC,
            is_validated=is_validated,
            is_speculative=is_speculative,
            is_durable_user_signal=False,
        ):
            return None
        return self._build_candidate(
            candidate_id=candidate_id,
            writeback_type=WritebackType.SEMANTIC,
            target_domain=MemoryDomain.SEMANTIC,
            content={"abstraction": abstraction},
            source_refs=source_refs,
            task_id=task_id,
            solver_run_id=None,
            execution_node_id=None,
            eligibility_reason="validated_abstraction",
            validation_state=ValidationState.VALIDATED,
        )

    def from_user_finding(
        self,
        *,
        candidate_id: str,
        task_id: str,
        statement: str,
        source_refs: list[str],
        is_durable: bool,
        is_validated: bool,
        is_speculative: bool,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
    ) -> WritebackCandidate | None:
        if not self._policy.allow_writeback(
            domain=MemoryDomain.USER,
            is_validated=is_validated,
            is_speculative=is_speculative,
            is_durable_user_signal=is_durable,
        ):
            return None
        validity_window = None
        if valid_from is not None or valid_to is not None:
            validity_window = ValidityWindow(valid_from=valid_from, valid_to=valid_to)

        return self._build_candidate(
            candidate_id=candidate_id,
            writeback_type=WritebackType.USER,
            target_domain=MemoryDomain.USER,
            content={"preference": statement},
            source_refs=source_refs,
            task_id=task_id,
            solver_run_id=None,
            execution_node_id=None,
            eligibility_reason="durable_user_signal",
            validation_state=ValidationState.VALIDATED,
            validity_window=validity_window,
        )

    def _build_candidate(
        self,
        *,
        candidate_id: str,
        writeback_type: WritebackType,
        target_domain: MemoryDomain,
        content: dict[str, Any],
        source_refs: list[str],
        task_id: str,
        solver_run_id: str | None,
        execution_node_id: str | None,
        eligibility_reason: str,
        validation_state: ValidationState,
        validity_window: ValidityWindow | None = None,
    ) -> WritebackCandidate:
        return WritebackCandidate(
            candidate_id=candidate_id,
            writeback_type=writeback_type,
            target_domain=target_domain,
            content=content,
            provenance=Provenance(
                source_type=SourceType.DERIVED,
                source_refs=source_refs,
                created_at=datetime.now(UTC),
                created_by="consolidator",
            ),
            source_refs=source_refs,
            source_task_id=task_id,
            source_solver_run_id=solver_run_id,
            source_execution_node_id=execution_node_id,
            validation_state=validation_state,
            eligibility_reason=eligibility_reason,
            validity_window=validity_window,
        )
