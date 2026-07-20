"""Runtime execution-state projection helpers for benchmark evaluation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from memorii.core.benchmark.artifact_rows import (
    ActionSupportMode,
    AlignmentVerdict,
    RuntimeActionAlignmentRow,
    RuntimeActionSupportRow,
)
from memorii.core.benchmark.memory_evolution_runtime.models import RuntimeGraphItemRow, RuntimeProjection
from memorii.core.benchmark.memory_evolution_runtime.utils import _claim_by_id, _ordered_unique
from memorii.core.benchmark.memory_evolution_sim import LatentClaim, LatentGraphScenario, OracleCheckpoint


def _expected_action_alignment_rows(
    *,
    scenario: LatentGraphScenario,
    expected_action_ids: list[str],
    graph_items: list[RuntimeGraphItemRow],
    runtime_claim_by_oracle: Mapping[str, str | None],
) -> list[RuntimeActionAlignmentRow]:
    rows: list[RuntimeActionAlignmentRow] = []
    runtime_actions = [item for item in graph_items if item.item_type == "action"]
    for action_id in expected_action_ids:
        exact = next(
            (
                item for item in runtime_actions
                if action_id in {item.action_id, item.runtime_item_id}
                or item.runtime_item_id.endswith(action_id)
            ),
            None,
        )
        if exact is not None:
            rows.append(_action_alignment_row(action_id=action_id, runtime_action=exact, verdict="aligned", support_mode="runtime_action_item_exact", matched_on=["action_id"], failure_reason=""))
            continue
        claim_id = action_id.removeprefix("action:") if action_id.startswith("action:") else ""
        claim = _claim_by_id(scenario, claim_id) if claim_id else None
        if claim is None:
            rows.append(_missing_action_alignment_row(action_id=action_id, failure_reason="runtime_missing_expected_action"))
            continue
        candidates = [_semantic_action_alignment_row(action_id=action_id, claim=claim, runtime_action=action) for action in runtime_actions]
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
            _work_state_bridged_action_row(action_id=action_id, claim=claim, runtime_action=action, graph_items=graph_items)
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
        rows.append(_missing_action_alignment_row(action_id=action_id, failure_reason="runtime_missing_expected_action"))
    return rows

def _action_alignment_row(
    *,
    action_id: str,
    runtime_action: RuntimeGraphItemRow,
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
    *, action_id: str, claim: LatentClaim, runtime_action: RuntimeGraphItemRow
) -> RuntimeActionAlignmentRow:
    matched: list[str] = []
    failed: list[str] = []
    derived_status, status_source = _derived_runtime_action_status(runtime_action)
    runtime_targets = list(runtime_action.target_entity_ids)
    if _action_target_matches(runtime_targets=runtime_targets, claim=claim):
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
    verdict = "aligned" if {"target_entity", "status", "evidence_event", "lifecycle"} <= set(matched) else "partial" if matched else "missing_expected"
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
    runtime_action: RuntimeGraphItemRow,
    graph_items: list[RuntimeGraphItemRow],
) -> RuntimeActionAlignmentRow | None:
    row = _semantic_action_alignment_row(action_id=action_id, claim=claim, runtime_action=runtime_action)
    if row.verdict == "aligned" or row.failure_reason != "runtime_action_target_mismatch":
        return None
    if not {"status", "evidence_event", "lifecycle"} <= set(row.matched_on):
        return None
    derived_status, _status_source = _derived_runtime_action_status(runtime_action)
    if derived_status not in {"in_progress", "resumed"}:
        return None
    if not _claim_has_active_branch_history(claim=claim, graph_items=graph_items):
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

def _derived_runtime_action_status(runtime_action: RuntimeGraphItemRow) -> tuple[str, str]:
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

def _action_target_matches(*, runtime_targets: list[str], claim: LatentClaim) -> bool:
    target_names = {_normalize_entity_key(target) for target in runtime_targets}
    oracle_names = {
        _normalize_entity_key(claim.subject.entity_id),
        _normalize_entity_key(claim.subject.canonical_name),
        _normalize_entity_key(claim.subject.observed_text),
    }
    target_names.discard("")
    oracle_names.discard("")
    if target_names & oracle_names:
        return True
    return any(
        (
            target.endswith(oracle)
            or oracle.endswith(target)
            or (len(oracle) >= 8 and target.startswith(oracle))
            or (len(target) >= 8 and oracle.startswith(target))
        )
        for target in target_names
        for oracle in oracle_names
        if len(target) >= 4 and len(oracle) >= 4
    )

def _claim_has_active_branch_history(
    *, claim: LatentClaim, graph_items: list[RuntimeGraphItemRow]
) -> bool:
    has_active_history = False
    for item in graph_items:
        if item.item_type != "action":
            continue
        if not _action_target_matches(runtime_targets=list(item.target_entity_ids), claim=claim):
            continue
        status, _status_source = _derived_runtime_action_status(item)
        if status in {"blocked", "abandoned", "completed", "failed"}:
            return False
        if status in {"started", "in_progress", "resumed"}:
            has_active_history = True
    return has_active_history

def _normalize_entity_key(value: str) -> str:
    value = value.replace("ent:", "").replace("ent_", "").replace("_", " ").replace("-", " ")
    return " ".join(value.strip().lower().split())

def _primary_action_failure(failed: list[str]) -> str:
    for bucket in ["runtime_action_target_mismatch", "runtime_action_status_mismatch", "runtime_action_evidence_missing", "runtime_execution_state_missing"]:
        if bucket in failed:
            return bucket
    return failed[0] if failed else "runtime_missing_expected_action"

def _runtime_action_support_rows(projection: RuntimeProjection) -> list[RuntimeActionSupportRow]:
    return [
        RuntimeActionSupportRow(action_id=action_id, support_mode=support_mode)
        for action_id, support_mode in sorted(projection.action_support.items())
    ]

def _suppressed_branch_ids(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    graph_items: list[RuntimeGraphItemRow],
) -> list[str]:
    suppressed: list[str] = []
    for claim_id in checkpoint.expected_excluded_claim_ids:
        claim = _claim_by_id(scenario, claim_id)
        if claim is None or claim.claim_kind != "action_state":
            continue
        for item in graph_items:
            if item.item_type != "action":
                continue
            if _runtime_action_suppresses_claim(runtime_action=item, claim=claim, graph_items=graph_items):
                suppressed.append(claim.subject.entity_id)
                break
    return _ordered_unique(suppressed)

def _suppressed_action_state_claim_ids(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    graph_items: list[RuntimeGraphItemRow],
) -> list[str]:
    suppressed: list[str] = []
    runtime_actions = [item for item in graph_items if item.item_type == "action"]
    for claim_id in checkpoint.expected_excluded_claim_ids:
        claim = _claim_by_id(scenario, claim_id)
        if claim is None or claim.claim_kind != "action_state":
            continue
        if any(_runtime_action_suppresses_claim(runtime_action=action, claim=claim, graph_items=graph_items) for action in runtime_actions):
            suppressed.append(claim_id)
    return _ordered_unique(suppressed)

def _runtime_action_suppresses_claim(
    *,
    runtime_action: RuntimeGraphItemRow,
    claim: LatentClaim,
    graph_items: list[RuntimeGraphItemRow],
) -> bool:
    status, _status_source = _derived_runtime_action_status(runtime_action)
    expected_status = normalize_action_status(claim.object.value)
    if status != expected_status or status not in {"blocked", "abandoned", "completed", "failed"}:
        return False
    if runtime_action.lifecycle_state != "active":
        return False
    runtime_events = set(runtime_action.evidence_event_ids)
    oracle_events = {str(item) for item in claim.evidence.source_event_ids}
    if oracle_events and not runtime_events & oracle_events:
        return False
    return _action_target_matches(
        runtime_targets=list(runtime_action.target_entity_ids),
        claim=claim,
    ) or _claim_has_active_branch_history(
        claim=claim,
        graph_items=graph_items,
    )


def _object_sequence(value: object) -> Sequence[object]:
    return value if isinstance(value, Sequence) and not isinstance(value, str) else ()

def _action_alignment_failure_reason(rows: Sequence[RuntimeActionAlignmentRow]) -> str:
    for row in rows:
        if row.verdict == "aligned":
            return ""
    for row in rows:
        reason = row.failure_reason
        if reason:
            return reason
    return ""
