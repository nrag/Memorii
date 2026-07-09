"""Runtime execution-state projection helpers for benchmark evaluation."""

from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim import LatentClaim, LatentGraphScenario, OracleCheckpoint
from memorii.core.benchmark.memory_evolution_runtime.models import RuntimeProjection
from memorii.core.benchmark.memory_evolution_runtime.utils import _claim_by_id, _ordered_unique
from memorii.core.calibration.alignment import RuntimeGraphAlignmentVerdict


def _expected_action_alignment_rows(
    *,
    scenario: LatentGraphScenario,
    expected_action_ids: list[str],
    graph_items: list[dict[str, object]],
    runtime_claim_by_oracle: dict[str, str],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    runtime_actions = [item for item in graph_items if item.get("item_type") == "action"]
    for action_id in expected_action_ids:
        exact = next(
            (
                item for item in runtime_actions
                if action_id in {str(item.get("action_id", "")), str(item.get("runtime_item_id", ""))}
                or str(item.get("runtime_item_id", "")).endswith(action_id)
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
        aligned = [row for row in candidates if row["verdict"] == "aligned"]
        if len(aligned) == 1:
            rows.append(aligned[0])
            continue
        if len(aligned) > 1:
            best = aligned[0]
            rows.append({**best, "verdict": "ambiguous_alignment", "support_mode": "ambiguous_action", "failure_reason": "runtime_execution_state_ambiguous"})
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
            rows.append({**best, "verdict": "ambiguous_alignment", "support_mode": "ambiguous_work_state_bridge", "failure_reason": "runtime_execution_state_ambiguous"})
            continue
        partial = [row for row in candidates if row["verdict"] == "partial"]
        if partial:
            rows.append(sorted(partial, key=lambda row: len(row.get("matched_on", [])), reverse=True)[0])
            continue
        if claim_id in runtime_claim_by_oracle:
            rows.append({
                "expected_action_id": action_id,
                "runtime_action_id": "",
                "runtime_item_id": runtime_claim_by_oracle[claim_id],
                "verdict": "aligned",
                "support_mode": "claim_derived_action",
                "matched_on": ["claim_alignment"],
                "failed_on": [],
                "failure_reason": "",
                "evidence_event_ids": list(claim.evidence.source_event_ids),
            })
            continue
        rows.append(_missing_action_alignment_row(action_id=action_id, failure_reason="runtime_missing_expected_action"))
    return rows

def _action_alignment_row(*, action_id: str, runtime_action: dict[str, object], verdict: str, support_mode: str, matched_on: list[str], failure_reason: str) -> dict[str, object]:
    return {
        "expected_action_id": action_id,
        "runtime_action_id": str(runtime_action.get("action_id", "")),
        "runtime_item_id": str(runtime_action.get("runtime_item_id", "")),
        "verdict": verdict,
        "support_mode": support_mode,
        "matched_on": matched_on,
        "failed_on": [],
        "failure_reason": failure_reason,
        "status": normalize_action_status(str(runtime_action.get("status", ""))),
        "target_entity_ids": [str(item) for item in runtime_action.get("target_entity_ids", []) or []],
        "evidence_event_ids": [str(item) for item in runtime_action.get("evidence_event_ids", []) or []],
    }

def _missing_action_alignment_row(*, action_id: str, failure_reason: str) -> dict[str, object]:
    return {
        "expected_action_id": action_id,
        "runtime_action_id": "",
        "runtime_item_id": "",
        "verdict": "missing_expected",
        "support_mode": "missing_action",
        "matched_on": [],
        "failed_on": [failure_reason],
        "failure_reason": failure_reason,
        "evidence_event_ids": [],
    }

def _semantic_action_alignment_row(*, action_id: str, claim: LatentClaim, runtime_action: dict[str, object]) -> dict[str, object]:
    matched: list[str] = []
    failed: list[str] = []
    runtime_targets = [str(item) for item in runtime_action.get("target_entity_ids", []) or []]
    if _action_target_matches(runtime_targets=runtime_targets, claim=claim):
        matched.append("target_entity")
    else:
        failed.append("runtime_action_target_mismatch")
    if normalize_action_status(str(runtime_action.get("status", ""))) == normalize_action_status(claim.object.value):
        matched.append("status")
    else:
        failed.append("runtime_action_status_mismatch")
    runtime_events = {str(item) for item in runtime_action.get("evidence_event_ids", []) or []}
    oracle_events = {str(item) for item in claim.evidence.source_event_ids}
    if runtime_events & oracle_events:
        matched.append("evidence_event")
    else:
        failed.append("runtime_action_evidence_missing")
    if str(runtime_action.get("lifecycle_state", "active")) == "active":
        matched.append("lifecycle")
    else:
        failed.append("runtime_execution_state_missing")
    verdict = "aligned" if {"target_entity", "status", "evidence_event", "lifecycle"} <= set(matched) else "partial" if matched else "missing_expected"
    support_mode = "runtime_action_semantic" if verdict == "aligned" else "partial_action"
    return {
        "expected_action_id": action_id,
        "runtime_action_id": str(runtime_action.get("action_id", "")),
        "runtime_item_id": str(runtime_action.get("runtime_item_id", "")),
        "verdict": verdict,
        "support_mode": support_mode,
        "matched_on": matched,
        "failed_on": failed,
        "failure_reason": "" if verdict == "aligned" else _primary_action_failure(failed),
        "status": normalize_action_status(str(runtime_action.get("status", ""))),
        "target_entity_ids": runtime_targets,
        "evidence_event_ids": sorted(runtime_events),
    }

def _work_state_bridged_action_row(
    *,
    action_id: str,
    claim: LatentClaim,
    runtime_action: dict[str, object],
    graph_items: list[dict[str, object]],
) -> dict[str, object] | None:
    row = _semantic_action_alignment_row(action_id=action_id, claim=claim, runtime_action=runtime_action)
    if row["verdict"] == "aligned" or row["failure_reason"] != "runtime_action_target_mismatch":
        return None
    if not {"status", "evidence_event", "lifecycle"} <= set(row["matched_on"]):
        return None
    if normalize_action_status(str(runtime_action.get("status", ""))) not in {"in_progress", "resumed"}:
        return None
    if not _claim_has_active_branch_history(claim=claim, graph_items=graph_items):
        return None
    return {
        **row,
        "verdict": "aligned",
        "support_mode": "runtime_action_work_state_bridge",
        "matched_on": [*row["matched_on"], "active_branch_history"],
        "failed_on": [],
        "failure_reason": "",
        "bridged_target_entity_id": claim.subject.entity_id,
    }

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
    return any(target.endswith(oracle) or oracle.endswith(target) for target in target_names for oracle in oracle_names if len(target) >= 4 and len(oracle) >= 4)

def _claim_has_active_branch_history(*, claim: LatentClaim, graph_items: list[dict[str, object]]) -> bool:
    has_active_history = False
    for item in graph_items:
        if item.get("item_type") != "action":
            continue
        if not _action_target_matches(runtime_targets=[str(value) for value in item.get("target_entity_ids", []) or []], claim=claim):
            continue
        status = normalize_action_status(str(item.get("status", "")))
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

def _runtime_action_support_rows(projection: RuntimeProjection) -> list[dict[str, str]]:
    return [
        {"action_id": action_id, "support_mode": support_mode}
        for action_id, support_mode in sorted(projection.action_support.items())
    ]

def _action_backed_claim_ids(*, expected_action_ids: list[str], action_support: dict[str, str]) -> list[str]:
    claim_ids: list[str] = []
    for action_id in expected_action_ids:
        if action_id not in action_support or not action_id.startswith("action:"):
            continue
        claim_ids.append(action_id.removeprefix("action:"))
    return claim_ids

def _oracle_evidence_events_for_claims(*, scenario: LatentGraphScenario, claim_ids: list[str], expected_event_ids: list[str]) -> list[str]:
    events: list[str] = []
    expected = set(expected_event_ids)
    for claim_id in claim_ids:
        claim = _claim_by_id(scenario, claim_id)
        if claim is None:
            continue
        evidence = [str(event_id) for event_id in claim.evidence.source_event_ids if event_id]
        events.extend([event_id for event_id in evidence if event_id in expected] or evidence)
    return _ordered_unique(events)

def _runtime_execution_state(
    *,
    scenario: LatentGraphScenario,
    graph_items: list[dict[str, object]],
    checkpoint: OracleCheckpoint,
    action_alignment_rows: list[dict[str, object]],
) -> dict[str, object]:
    action_rows = [item for item in graph_items if item.get("item_type") == "action"]
    branch_rows: list[dict[str, object]] = []
    for action in action_rows:
        status = normalize_action_status(str(action.get("status", "")))
        targets = [str(item) for item in action.get("target_entity_ids", []) or []]
        branch_rows.append(
            {
                "runtime_action_id": str(action.get("action_id", "")),
                "runtime_item_id": str(action.get("runtime_item_id", "")),
                "target_entity_ids": targets,
                "status": status,
                "evidence_event_ids": [str(item) for item in action.get("evidence_event_ids", []) or []],
                "continuation_rank": _continuation_rank(status),
            }
        )
    aligned_rows = [row for row in action_alignment_rows if row.get("verdict") == "aligned"]
    active_row = next((row for row in aligned_rows if str(row.get("expected_action_id", "")) in checkpoint.expected_action_ids), None)
    active_branch = ""
    active_events: list[str] = []
    if active_row is not None:
        active_branch = _branch_from_action_alignment(scenario=scenario, action_id=str(active_row.get("expected_action_id", "")))
        active_events = [str(item) for item in active_row.get("evidence_event_ids", []) or []]
    suppressed_branch_ids = _suppressed_branch_ids(scenario=scenario, checkpoint=checkpoint, graph_items=graph_items)
    return {
        "active_continuation_branch": active_branch,
        "active_evidence_event_ids": active_events,
        "suppressed_branch_ids": suppressed_branch_ids,
        "actions": branch_rows,
        "aligned_action_count": len(aligned_rows),
        "ambiguous_action_count": sum(1 for row in action_alignment_rows if row.get("verdict") == "ambiguous_alignment"),
    }

def _continuation_rank(status: str) -> int:
    if status in {"in_progress", "resumed"}:
        return 3
    if status == "started":
        return 2
    if status in {"blocked", "abandoned", "completed", "failed"}:
        return 0
    return 1

def _branch_from_action_alignment(*, scenario: LatentGraphScenario, action_id: str) -> str:
    claim_id = action_id.removeprefix("action:") if action_id.startswith("action:") else ""
    claim = _claim_by_id(scenario, claim_id) if claim_id else None
    return claim.subject.entity_id if claim else ""

def _suppressed_branch_ids(*, scenario: LatentGraphScenario, checkpoint: OracleCheckpoint, graph_items: list[dict[str, object]]) -> list[str]:
    suppressed: list[str] = []
    for claim_id in checkpoint.expected_excluded_claim_ids:
        claim = _claim_by_id(scenario, claim_id)
        if claim is None or claim.claim_kind != "action_state":
            continue
        for item in graph_items:
            if item.get("item_type") != "action":
                continue
            if _runtime_action_suppresses_claim(runtime_action=item, claim=claim, graph_items=graph_items):
                suppressed.append(claim.subject.entity_id)
                break
    return _ordered_unique(suppressed)

def _suppressed_action_state_claim_ids(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    graph_items: list[dict[str, object]],
) -> list[str]:
    suppressed: list[str] = []
    runtime_actions = [item for item in graph_items if item.get("item_type") == "action"]
    for claim_id in checkpoint.expected_excluded_claim_ids:
        claim = _claim_by_id(scenario, claim_id)
        if claim is None or claim.claim_kind != "action_state":
            continue
        if any(_runtime_action_suppresses_claim(runtime_action=action, claim=claim, graph_items=graph_items) for action in runtime_actions):
            suppressed.append(claim_id)
    return _ordered_unique(suppressed)

def _runtime_action_suppresses_claim(*, runtime_action: dict[str, object], claim: LatentClaim, graph_items: list[dict[str, object]]) -> bool:
    status = normalize_action_status(str(runtime_action.get("status", "")))
    expected_status = normalize_action_status(claim.object.value)
    if status != expected_status or status not in {"blocked", "abandoned", "completed", "failed"}:
        return False
    if str(runtime_action.get("lifecycle_state", "active")) != "active":
        return False
    runtime_events = {str(item) for item in runtime_action.get("evidence_event_ids", []) or []}
    oracle_events = {str(item) for item in claim.evidence.source_event_ids}
    if oracle_events and not runtime_events & oracle_events:
        return False
    return _action_target_matches(
        runtime_targets=[str(value) for value in runtime_action.get("target_entity_ids", []) or []],
        claim=claim,
    ) or _claim_has_active_branch_history(claim=claim, graph_items=graph_items)

def _action_alignment_failure_reason(rows: list[dict[str, object]]) -> str:
    for row in rows:
        if row.get("verdict") == "aligned":
            return ""
    for row in rows:
        reason = str(row.get("failure_reason", ""))
        if reason:
            return reason
    return ""
