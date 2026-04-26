from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.work_state.service import WorkStateService


def test_get_tool_schemas_includes_state_summary_and_next_step() -> None:
    provider = ProviderMemoryService()

    schemas = provider.get_tool_schemas()
    tool_names = {schema["name"] for schema in schemas}

    assert "memorii_get_state_summary" in tool_names
    assert "memorii_get_next_step" in tool_names


def test_handle_tool_call_unknown_tool_returns_error() -> None:
    provider = ProviderMemoryService()

    result = provider.handle_tool_call("not_a_tool", {})

    assert result.ok is False
    assert "not_a_tool" in (result.error or "")


def test_handle_tool_call_validation_error_returns_error() -> None:
    provider = ProviderMemoryService()

    result = provider.handle_tool_call("memorii_get_state_summary", {"task_id": 123})

    assert result.ok is False
    assert "Validation error" in (result.error or "")


def test_get_state_summary_without_work_state_service_returns_empty() -> None:
    provider = ProviderMemoryService()

    result = provider.handle_tool_call("memorii_get_state_summary", {"task_id": "task:none"})

    assert result.ok is True
    assert result.result["state_count"] == 0
    assert result.result["work_states"] == []


def test_get_state_summary_with_matching_state_returns_state() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)

    provider.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="please implement parser updates and write tests",
        session_id="session:tool:1",
        task_id="task:tool:1",
        user_id="user:tool:1",
    )

    result = provider.handle_tool_call("memorii_get_state_summary", {"task_id": "task:tool:1"})

    assert result.ok is True
    assert result.result["state_count"] == 1
    work_states = result.result["work_states"]
    assert isinstance(work_states, list)
    assert work_states[0]["task_id"] == "task:tool:1"


def test_get_next_step_without_state_returns_ask_user_stub() -> None:
    provider = ProviderMemoryService()

    result = provider.handle_tool_call("memorii_get_next_step", {"task_id": "task:none"})

    assert result.ok is True
    next_step = result.result["next_step"]
    assert next_step["action_type"] == "ask_user"
    assert next_step["reason"] == "no_active_work_state"


def test_get_next_step_with_task_state_returns_continue_task_stub() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)

    provider.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="please implement parser updates and write tests",
        session_id="session:tool:2",
        task_id="task:tool:2",
        user_id="user:tool:2",
    )

    summary_result = provider.handle_tool_call("memorii_get_state_summary", {"task_id": "task:tool:2"})
    work_state_id = summary_result.result["work_states"][0]["work_state_id"]

    result = provider.handle_tool_call("memorii_get_next_step", {"task_id": "task:tool:2"})

    assert result.ok is True
    assert result.result["next_step"]["action_type"] == "continue_task"
    assert result.result["based_on_work_state_id"] == work_state_id


def test_get_next_step_with_investigation_state_returns_inspect_failure_stub() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)

    provider.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="build failed on CI while running tests",
        session_id="session:tool:3",
        task_id="task:tool:3",
        user_id="user:tool:3",
    )

    result = provider.handle_tool_call("memorii_get_next_step", {"task_id": "task:tool:3"})

    assert result.ok is True
    assert result.result["next_step"]["action_type"] == "inspect_failure"
