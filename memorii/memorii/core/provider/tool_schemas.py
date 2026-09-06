"""Provider tool schemas exposed to agent integrations."""

from __future__ import annotations

from memorii.core.work_state.models import WorkStateKind


def provider_tool_schemas() -> list[dict[str, object]]:
    return [
        _schema(
            "memorii_decision_add_option",
            "Add an option to an existing decision state.",
            {
                "decision_state_id": {"type": "string"},
                "option_id": {"type": "string"},
                "label": {"type": "string"},
                "description": {"type": "string"},
            },
            ["decision_state_id", "option_id", "label"],
        ),
        _schema(
            "memorii_decision_add_criterion",
            "Add a weighted criterion to an existing decision state.",
            {
                "decision_state_id": {"type": "string"},
                "criterion_id": {"type": "string"},
                "label": {"type": "string"},
                "weight": {"type": "number"},
            },
            ["decision_state_id", "criterion_id", "label"],
        ),
        _schema(
            "memorii_decision_add_evidence",
            "Add evidence for/against an option (or neutral) in a decision state.",
            {
                "decision_state_id": {"type": "string"},
                "evidence_id": {"type": "string"},
                "content": {"type": "string"},
                "polarity": {
                    "type": "string",
                    "enum": ["for_option", "against_option", "neutral"],
                },
                "option_id": {"type": "string"},
                "source_ids": {"type": "array", "items": {"type": "string"}},
            },
            ["decision_state_id", "evidence_id", "content", "polarity"],
        ),
        _schema(
            "memorii_decision_set_recommendation",
            "Set or clear the recommendation on a decision state.",
            {
                "decision_state_id": {"type": "string"},
                "recommendation": {"type": ["string", "null"]},
            },
            ["decision_state_id", "recommendation"],
        ),
        _schema(
            "memorii_decision_finalize",
            "Record the final decision and mark the decision state as decided.",
            {
                "decision_state_id": {"type": "string"},
                "final_decision": {"type": "string"},
            },
            ["decision_state_id", "final_decision"],
        ),
        _schema(
            "memorii_get_state_summary",
            "Return Memorii's current work-state summary for the given session/task/user scope.",
            {
                "session_id": {"type": "string"},
                "task_id": {"type": "string"},
                "user_id": {"type": "string"},
            },
        ),
        _schema(
            "memorii_get_next_step",
            (
                "Return a simple next-step recommendation based on current work state. "
                "This is a placeholder until frontier planning is implemented."
            ),
            {
                "query": {"type": "string"},
                "session_id": {"type": "string"},
                "task_id": {"type": "string"},
                "user_id": {"type": "string"},
                "solver_run_id": {"type": "string"},
            },
        ),
        _schema(
            "memorii_open_or_resume_work",
            "Explicitly open or resume structured work state and optionally create solver/execution bindings.",
            {
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "kind": {"type": "string", "enum": [kind.value for kind in WorkStateKind]},
                "session_id": {"type": "string"},
                "task_id": {"type": "string"},
                "user_id": {"type": "string"},
                "work_state_id": {"type": "string"},
                "execution_node_id": {"type": "string"},
                "solver_run_id": {"type": "string"},
            },
            ["title"],
        ),
        _schema(
            "memorii_record_progress",
            "Record meaningful progress against an active work state.",
            {
                "work_state_id": {"type": "string"},
                "task_id": {"type": "string"},
                "session_id": {"type": "string"},
                "title": {"type": "string"},
                "content": {"type": "string"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
                "solver_run_id": {"type": "string"},
                "execution_node_id": {"type": "string"},
            },
            ["content"],
        ),
        _schema(
            "memorii_record_outcome",
            "Record a terminal or semi-terminal outcome for a work state.",
            {
                "work_state_id": {"type": "string"},
                "task_id": {"type": "string"},
                "session_id": {"type": "string"},
                "outcome": {
                    "type": "string",
                    "enum": ["completed", "blocked", "abandoned", "needs_followup"],
                },
                "content": {"type": "string"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
                "solver_run_id": {"type": "string"},
                "execution_node_id": {"type": "string"},
            },
            ["outcome", "content"],
        ),
    ]


def provider_tool_schemas_with_attention() -> list[dict[str, object]]:
    """Return the opt-in tool set paired with attention-aware dispatch."""

    return [*provider_tool_schemas(), conflict_attention_resolve_tool_schema(), conflict_attention_list_tool_schema()]


def conflict_attention_resolve_tool_schema() -> dict[str, object]:
    return _schema(
        "memorii_resolve_conflict",
        "Submit an explicit clarification for a displayed semantic conflict.",
        {
            "conflict_id": {"type": "string"},
            "expected_conflict_revision": {"type": "string"},
            "operation_id": {"type": "string"},
            "action": {"type": "string", "enum": ["select", "both_with_validity", "neither"]},
            "selected_candidate_ids": {"type": "array", "items": {"type": "string"}},
            "validity_intervals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "candidate_id": {"type": "string"},
                        "valid_from": {"type": "string", "format": "date-time"},
                        "valid_to": {"type": ["string", "null"], "format": "date-time"},
                    },
                    "required": ["candidate_id", "valid_from"],
                    "additionalProperties": False,
                },
            },
            "source_user_event_id": {"type": "string"},
            "user_confirmation_receipt": {"type": ["string", "null"]},
        },
        [
            "conflict_id",
            "expected_conflict_revision",
            "operation_id",
            "action",
            "selected_candidate_ids",
            "validity_intervals",
            "source_user_event_id",
        ],
    )


def conflict_attention_list_tool_schema() -> dict[str, object]:
    return _schema(
        "memorii_list_conflicts",
        "List unresolved Memorii conflicts visible to the authenticated caller.",
        {
            "scope_ids": {"type": "array", "items": {"type": "string"}},
            "page_size": {"type": "integer", "minimum": 1, "maximum": 100},
            "cursor": {"type": ["string", "null"]},
        },
    )


def _schema(
    name: str,
    description: str,
    properties: dict[str, object],
    required: list[str] | None = None,
) -> dict[str, object]:
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        input_schema["required"] = required
    input_schema["additionalProperties"] = False
    return {
        "name": name,
        "description": description,
        "input_schema": input_schema,
    }
