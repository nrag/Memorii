"""Runtime execution-state projection helpers for benchmark evaluation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from memorii.core.benchmark.artifact_rows import (
    ActionSupportMode,
    AlignmentVerdict,
    RuntimeActionAlignmentRow,
    RuntimeActionSupportRow,
)
from memorii.core.benchmark.calibration.alignment import RuntimeGraphAlignment, RuntimeGraphAlignmentVerdict
from memorii.core.benchmark.memory_evolution_runtime.models import (
    RuntimeActionGraphItemRow,
    RuntimeGraphItem,
    RuntimeProjection,
)
from memorii.core.benchmark.memory_evolution_runtime.utils import claim_by_id
from memorii.core.benchmark.memory_evolution_sim import LatentClaim, LatentGraphScenario


def expected_action_alignment_rows(
    *,
    scenario: LatentGraphScenario,
    expected_action_ids: list[str],
    graph_items: list[RuntimeGraphItem],
    runtime_claim_by_oracle: Mapping[str, str | None],
    entity_alignments: Sequence[RuntimeGraphAlignment],
) -> list[RuntimeActionAlignmentRow]:
    rows: list[RuntimeActionAlignmentRow] = []
    runtime_actions = [item for item in graph_items if item.item_type == "action"]
    for action_id in expected_action_ids:
        claim_id = action_id.removeprefix("action:") if action_id.startswith("action:") else ""
        claim = claim_by_id(scenario, claim_id) if claim_id else None
        if claim is None:
            rows.append(
                _missing_action_alignment_row(action_id=action_id, failure_reason="runtime_missing_expected_action")
            )
            continue
        candidates = [
            _semantic_action_alignment_row(
                action_id=action_id,
                claim=claim,
                runtime_action=action,
                graph_items=graph_items,
                entity_alignments=entity_alignments,
            )
            for action in runtime_actions
        ]
        aligned = [row for row in candidates if row.verdict == "aligned"]
        if len(aligned) == 1:
            rows.append(aligned[0])
            continue
        if len(aligned) > 1:
            best = aligned[0]
            rows.append(
                best.model_copy(
                    update={
                        "verdict": "ambiguous_alignment",
                        "support_mode": "ambiguous_action",
                        "failure_reason": "runtime_execution_state_ambiguous",
                    }
                )
            )
            continue
        bridged = [
            _work_state_bridged_action_row(
                action_id=action_id,
                claim=claim,
                runtime_action=action,
                graph_items=graph_items,
                entity_alignments=entity_alignments,
            )
            for action in runtime_actions
        ]
        bridged = [row for row in bridged if row is not None]
        if len(bridged) == 1:
            rows.append(bridged[0])
            continue
        if len(bridged) > 1:
            best = bridged[0]
            rows.append(
                best.model_copy(
                    update={
                        "verdict": "ambiguous_alignment",
                        "support_mode": "ambiguous_work_state_bridge",
                        "failure_reason": "runtime_execution_state_ambiguous",
                    }
                )
            )
            continue
        partial = [row for row in candidates if row.verdict == "partial"]
        if partial:
            rows.append(max(partial, key=lambda row: len(row.matched_on)))
            continue
        if claim_id in runtime_claim_by_oracle:
            rows.append(
                RuntimeActionAlignmentRow(
                    expected_action_id=action_id,
                    runtime_action_id="",
                    runtime_item_id=runtime_claim_by_oracle[claim_id] or "",
                    verdict="aligned",
                    support_mode="claim_derived_action",
                    matched_on=["claim_alignment"],
                    failure_reason="",
                    evidence_event_ids=list(claim.evidence.source_event_ids),
                )
            )
            continue
        rows.append(
            _missing_action_alignment_row(action_id=action_id, failure_reason="runtime_missing_expected_action")
        )
    return rows


def include_unmatched_selected_actions(
    *,
    rows: Sequence[RuntimeActionAlignmentRow],
    selected_actions: Sequence[RuntimeActionGraphItemRow],
) -> list[RuntimeActionAlignmentRow]:
    """Expose every production-selected action, including oracle-unmatched actions."""

    result = list(rows)
    referenced_runtime_ids = {
        runtime_id
        for row in rows
        for runtime_id in (row.runtime_action_id, row.runtime_item_id)
        if runtime_id
    }
    for action in sorted(selected_actions, key=lambda item: item.runtime_item_id):
        if action.action_id in referenced_runtime_ids or action.runtime_item_id in referenced_runtime_ids:
            continue
        status, status_source = _derived_runtime_action_status(action)
        result.append(
            RuntimeActionAlignmentRow(
                expected_action_id="",
                runtime_action_id=action.action_id,
                runtime_item_id=action.runtime_item_id,
                verdict="unmatched_runtime",
                support_mode="unexpected_action",
                failure_reason="production_retrieval_unexpected_selected_action",
                status=status,
                model_status_raw=action.status,
                action_type_raw=action.action_type,
                status_derived_from=status_source,
                target_entity_ids=list(action.target_entity_ids),
                evidence_event_ids=list(action.evidence_event_ids),
            )
        )
    return result


def _action_alignment_row(
    *,
    action_id: str,
    runtime_action: RuntimeActionGraphItemRow,
    verdict: AlignmentVerdict,
    support_mode: ActionSupportMode,
    matched_on: list[str],
    failure_reason: str,
) -> RuntimeActionAlignmentRow:
    derived_status, status_source = _derived_runtime_action_status(runtime_action)
    return RuntimeActionAlignmentRow(
        expected_action_id=action_id,
        runtime_action_id=runtime_action.action_id,
        runtime_item_id=runtime_action.runtime_item_id,
        verdict=verdict,
        support_mode=support_mode,
        matched_on=matched_on,
        failure_reason=failure_reason,
        status=derived_status,
        model_status_raw=runtime_action.status,
        action_type_raw=runtime_action.action_type,
        status_derived_from=status_source,
        target_entity_ids=list(runtime_action.target_entity_ids),
        evidence_event_ids=list(runtime_action.evidence_event_ids),
    )


def _missing_action_alignment_row(*, action_id: str, failure_reason: str) -> RuntimeActionAlignmentRow:
    return RuntimeActionAlignmentRow(
        expected_action_id=action_id,
        runtime_action_id="",
        runtime_item_id="",
        verdict="missing_expected",
        support_mode="missing_action",
        failed_on=[failure_reason],
        failure_reason=failure_reason,
    )


def _semantic_action_alignment_row(
    *,
    action_id: str,
    claim: LatentClaim,
    runtime_action: RuntimeActionGraphItemRow,
    graph_items: Sequence[RuntimeGraphItem],
    entity_alignments: Sequence[RuntimeGraphAlignment],
) -> RuntimeActionAlignmentRow:
    matched: list[str] = []
    failed: list[str] = []
    derived_status, status_source = _derived_runtime_action_status(runtime_action)
    runtime_targets = list(runtime_action.target_entity_ids)
    if _action_target_matches(
        runtime_targets=runtime_targets,
        oracle_entity_id=claim.subject.entity_id,
        graph_items=graph_items,
        entity_alignments=entity_alignments,
    ):
        matched.append("target_entity")
    else:
        failed.append("runtime_action_target_mismatch")
    if derived_status == normalize_action_status(claim.object.value):
        matched.append("status")
    else:
        failed.append("runtime_action_status_mismatch")
    runtime_events = set(runtime_action.evidence_event_ids)
    oracle_events = {str(item) for item in claim.evidence.source_event_ids}
    if runtime_events & oracle_events:
        matched.append("evidence_event")
    else:
        failed.append("runtime_action_evidence_missing")
    if runtime_action.lifecycle_state == "active":
        matched.append("lifecycle")
    else:
        failed.append("runtime_execution_state_missing")
    verdict = (
        "aligned"
        if {"target_entity", "status", "evidence_event", "lifecycle"} <= set(matched)
        else "partial"
        if matched
        else "missing_expected"
    )
    support_mode = "runtime_action_semantic" if verdict == "aligned" else "partial_action"
    return RuntimeActionAlignmentRow(
        expected_action_id=action_id,
        runtime_action_id=runtime_action.action_id,
        runtime_item_id=runtime_action.runtime_item_id,
        verdict=verdict,
        support_mode=support_mode,
        matched_on=matched,
        failed_on=failed,
        failure_reason="" if verdict == "aligned" else _primary_action_failure(failed),
        status=derived_status,
        model_status_raw=runtime_action.status,
        action_type_raw=runtime_action.action_type,
        status_derived_from=status_source,
        target_entity_ids=runtime_targets,
        evidence_event_ids=sorted(runtime_events),
    )


def _work_state_bridged_action_row(
    *,
    action_id: str,
    claim: LatentClaim,
    runtime_action: RuntimeActionGraphItemRow,
    graph_items: list[RuntimeGraphItem],
    entity_alignments: Sequence[RuntimeGraphAlignment],
) -> RuntimeActionAlignmentRow | None:
    row = _semantic_action_alignment_row(
        action_id=action_id,
        claim=claim,
        runtime_action=runtime_action,
        graph_items=graph_items,
        entity_alignments=entity_alignments,
    )
    if row.verdict == "aligned" or row.failure_reason != "runtime_action_target_mismatch":
        return None
    if not {"status", "evidence_event", "lifecycle"} <= set(row.matched_on):
        return None
    derived_status, _status_source = _derived_runtime_action_status(runtime_action)
    if derived_status not in {"in_progress", "resumed"}:
        return None
    if not _claim_has_active_branch_history(
        claim=claim,
        graph_items=graph_items,
        entity_alignments=entity_alignments,
    ):
        return None
    return row.model_copy(
        update={
            "verdict": "aligned",
            "support_mode": "runtime_action_work_state_bridge",
            "matched_on": [*row.matched_on, "active_branch_history"],
            "failed_on": [],
            "failure_reason": "",
            "bridged_target_entity_id": claim.subject.entity_id,
        }
    )


def normalize_action_status(value: str) -> str:
    normalized = " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())
    mapping = {
        "start": "started",
        "started": "started",
        "in progress": "in_progress",
        "inprogress": "in_progress",
        "progressed": "in_progress",
        "continue": "in_progress",
        "continued": "in_progress",
        "blocked": "blocked",
        "stuck": "blocked",
        "resumed": "resumed",
        "reopened": "resumed",
        "abandoned": "abandoned",
        "dropped": "abandoned",
        "completed": "completed",
        "done": "completed",
        "failed": "failed",
        "succeeded": "succeeded",
    }
    return mapping.get(normalized, normalized.replace(" ", "_"))


def _derived_runtime_action_status(runtime_action: RuntimeActionGraphItemRow) -> tuple[str, str]:
    raw_status = runtime_action.status
    raw_action_type = runtime_action.action_type
    status_signal = _status_signal(raw_status)
    action_type_signal = _status_signal(raw_action_type)
    terminal_states = {"blocked", "abandoned", "completed", "failed", "succeeded"}
    if status_signal in terminal_states:
        return status_signal, "status"
    # Action type describes the event that occurred; it is not the durable
    # work-state status. An explicit in-progress status is authoritative, so
    # a resume event cannot be reinterpreted as a distinct resumed state.
    # started remains a weak extractor default and may be refined by an
    # explicit progress event type.
    if status_signal == "in_progress":
        return status_signal, "status"
    if action_type_signal in terminal_states:
        return action_type_signal, "action_type"
    for preferred in ("in_progress", "resumed", "started"):
        if action_type_signal == preferred:
            return action_type_signal, "action_type"
    if status_signal:
        return status_signal, "status"
    if action_type_signal:
        return action_type_signal, "action_type"
    return "", ""


def _status_signal(value: str) -> str:
    status = normalize_action_status(value)
    if status in {
        "started",
        "in_progress",
        "blocked",
        "resumed",
        "abandoned",
        "completed",
        "failed",
        "succeeded",
    }:
        return status
    lowered = value.strip().lower().replace("-", "_").replace(" ", "_")
    if "in_progress" in lowered or "progress" in lowered or "continue" in lowered:
        return "in_progress"
    if "resume" in lowered or "reopen" in lowered:
        return "resumed"
    if "block" in lowered or "stuck" in lowered:
        return "blocked"
    if "abandon" in lowered or "drop" in lowered:
        return "abandoned"
    if "complete" in lowered or "done" in lowered:
        return "completed"
    if "fail" in lowered:
        return "failed"
    if "succeed" in lowered:
        return "succeeded"
    if "start" in lowered:
        return "started"
    return status


def _action_target_matches(
    *,
    runtime_targets: list[str],
    oracle_entity_id: str,
    graph_items: Sequence[RuntimeGraphItem],
    entity_alignments: Sequence[RuntimeGraphAlignment],
) -> bool:
    aligned_runtime_ids: set[str] = set()
    entity_by_runtime_id = {
        item.runtime_item_id: item for item in graph_items if item.item_type == "entity"
    }
    for alignment in entity_alignments:
        if (
            alignment.item_type != "entity"
            or alignment.verdict != RuntimeGraphAlignmentVerdict.ALIGNED
            or alignment.oracle_item_id != oracle_entity_id
            or alignment.runtime_item_id is None
        ):
            continue
        aligned_runtime_ids.add(alignment.runtime_item_id)
        runtime_entity = entity_by_runtime_id.get(alignment.runtime_item_id)
        if runtime_entity is not None:
            aligned_runtime_ids.add(runtime_entity.canonical_id)
    return bool(set(runtime_targets) & aligned_runtime_ids)


def _claim_has_active_branch_history(
    *,
    claim: LatentClaim,
    graph_items: list[RuntimeGraphItem],
    entity_alignments: Sequence[RuntimeGraphAlignment],
) -> bool:
    has_active_history = False
    for item in graph_items:
        if item.item_type != "action":
            continue
        if not _action_target_matches(
            runtime_targets=list(item.target_entity_ids),
            oracle_entity_id=claim.subject.entity_id,
            graph_items=graph_items,
            entity_alignments=entity_alignments,
        ):
            continue
        status, _status_source = _derived_runtime_action_status(item)
        if status in {"blocked", "abandoned", "completed", "failed"}:
            return False
        if status in {"started", "in_progress", "resumed"}:
            has_active_history = True
    return has_active_history


def _primary_action_failure(failed: list[str]) -> str:
    for bucket in [
        "runtime_action_target_mismatch",
        "runtime_action_status_mismatch",
        "runtime_action_evidence_missing",
        "runtime_execution_state_missing",
    ]:
        if bucket in failed:
            return bucket
    return failed[0] if failed else "runtime_missing_expected_action"


def runtime_action_support_rows(projection: RuntimeProjection) -> list[RuntimeActionSupportRow]:
    return [
        RuntimeActionSupportRow(action_id=action_id, support_mode=support_mode)
        for action_id, support_mode in sorted(projection.action_support.items())
    ]


def _object_sequence(value: object) -> Sequence[object]:
    return value if isinstance(value, Sequence) and not isinstance(value, str) else ()


def action_alignment_failure_reason(rows: Sequence[RuntimeActionAlignmentRow]) -> str:
    for row in rows:
        if row.verdict == "aligned":
            return ""
    for row in rows:
        reason = row.failure_reason
        if reason:
            return reason
    return ""
