"""Runtime certification against pinned real framework packages.

These journeys import the actual LangGraph, AutoGen and OpenAI Agents
libraries at the exact versions pinned in requirements.txt, map their
native coordinate objects through the compatibility wrappers, and drive
a real durable command round trip. With ``MEMORII_HOSTCERT=1`` (the CI
job and the certification venv) a missing framework is a hard failure,
never a skip; without it the suite skips so ordinary local runs do not
require the pins.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.harness_state.tools import (
    TOOL_MEMORII_GET_EXECUTION_STATE,
    RuntimeModelTools,
    ToolCall,
)
from memorii.core.persistence.runtime_api import RuntimeCommandService
from memorii.core.persistence.runtime_contracts import RuntimeCommandRequest
from memorii.core.storage_administration.service import StorageAdministrationService

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_CERTIFIED_PINS = {
    "langgraph": "1.0.10",
    "ag2": "1.1.1",
    "openai-agents": "0.22.3",
}


def _require(framework: str):
    from importlib.metadata import version

    try:
        installed = version(framework)
    except Exception:  # noqa: BLE001 - importlib raises several types
        if os.environ.get("MEMORII_HOSTCERT") == "1":
            pytest.fail(
                f"certification environment is missing {framework}"
                f"=={_CERTIFIED_PINS[framework]}"
            )
        pytest.skip(f"{framework} pins not installed in this environment")
    assert installed == _CERTIFIED_PINS[framework], (
        f"{framework} pin drifted: certified {_CERTIFIED_PINS[framework]},"
        f" found {installed}"
    )
    return installed


def _durable_round_trip(wrapper) -> tuple[str, object]:
    """Start one durable task and read it back through the model tools."""
    from memorii.integrations.compatibility_examples import (
        CompatibilityExampleEnvelope,
    )

    administration = StorageAdministrationService(
        Path(_make_tmp_root(wrapper))
    )
    administration.initialize()
    try:
        service = RuntimeCommandService(
            administration, client_namespace="hostcert"
        )
        envelope = CompatibilityExampleEnvelope(
            wrapper=wrapper, task_id="task:hostcert"
        )
        assert "not an installed adapter" in envelope.note
        receipt = service.dispatch(
            RuntimeCommandRequest(
                kind="start_task",
                operation_id="op:hostcert-start",
                goal=f"Certified round trip for {wrapper.framework}",
            )
        )
        assert receipt.status == "committed"
        task_id = service.repository.list_tasks()[0].task_id
        tools = RuntimeModelTools(
            _ports_for(administration, wrapper.host_binding_fields())
        )
        state = tools.dispatch(
            ToolCall(
                name=TOOL_MEMORII_GET_EXECUTION_STATE,
                principal=wrapper.host_binding_fields()["session"],
            )
        )
        assert state.status == "ok"
        assert state.payload["task_id"] == task_id
        return task_id, state
    finally:
        administration.close()


def _make_tmp_root(wrapper) -> str:
    import tempfile

    return tempfile.mkdtemp(prefix=f"hostcert-{wrapper.framework}-")


def _ports_for(administration, binding_fields: dict[str, str]):
    from memorii.core.harness_state.binding import (
        HermesRuntimeStatePorts,
        RuntimeTaskBinding,
    )

    ports = HermesRuntimeStatePorts(administration)
    ports.bind_task(
        RuntimeTaskBinding(
            installation_task_id=_seeded_task_id(administration),
            host_session_id=binding_fields.get("session"),
            granted_to_principal=binding_fields["session"],
        )
    )
    return ports


def _seeded_task_id(administration) -> str:
    from memorii.core.persistence.runtime_api import RuntimeCommandService
    from memorii.core.persistence.runtime_contracts import RuntimeCommandRequest

    service = RuntimeCommandService(
        administration, client_namespace="hostcert"
    )
    service.dispatch(
        RuntimeCommandRequest(
            kind="start_task",
            operation_id="op:hostcert-seed",
            goal="Host certification binding",
        )
    )
    return service.repository.list_tasks()[0].task_id


def test_langgraph_runtime_certification() -> None:
    _require("langgraph")
    from langchain_core.runnables import RunnableConfig
    from memorii.integrations.compatibility_examples import LangGraphHostWrapper

    # Real LangGraph thread config: the native checkpoint coordinate the
    # wrapper must translate, with LangGraph retaining its own checkpoint
    # authority.
    config = RunnableConfig(
        configurable={"thread_id": "cert-thread-1", "checkpoint_ns": "cert-ns"}
    )
    wrapper = LangGraphHostWrapper(
        graph_id="cert-graph",
        thread_id=config["configurable"]["thread_id"],
        checkpoint_ns=config["configurable"]["checkpoint_ns"],
    )
    fields = wrapper.host_binding_fields()
    assert fields["session"] == "cert-thread-1"
    assert fields["thread"] == "cert-graph"
    assert fields["client_installation"] == "cert-ns"
    task_id, _state = _durable_round_trip(wrapper)
    assert task_id.startswith("task:")


def test_autogen_runtime_certification() -> None:
    _require("ag2")
    from ag2 import AgentSpec
    from memorii.integrations.compatibility_examples import AutoGenHostWrapper

    # Real AG2 (active AutoGen) agent specification: the native
    # participant identity the wrapper maps; the agent never receives
    # authority from message fields. (The legacy `pyautogen` 0.10 name is
    # a transition stub with an empty surface; the active line ships as
    # `ag2` with the `autogen` import expected at 0.14+.)
    spec = AgentSpec(name="cert-participant-1", prompt=["cert turn"])
    wrapper = AutoGenHostWrapper(
        conversation_id="cert-conversation-1",
        participant_id=spec.name,
    )
    fields = wrapper.host_binding_fields()
    assert fields["thread"] == "cert-participant-1"
    assert fields["session"] == "cert-conversation-1"
    task_id, _state = _durable_round_trip(wrapper)
    assert task_id.startswith("task:")


def test_openai_agents_runtime_certification() -> None:
    _require("openai-agents")
    from agents import RunConfig
    from memorii.integrations.compatibility_examples import OpenAIAgentsHostWrapper

    # Real OpenAI Agents run configuration: the native session/run
    # coordinates the wrapper maps into the same binding fields.
    run_config = RunConfig(
        workflow_name="cert-run-1", trace_id="cert-trace-1"
    )
    wrapper = OpenAIAgentsHostWrapper(
        application_session="cert-session-1",
        run_id=run_config.workflow_name,
    )
    fields = wrapper.host_binding_fields()
    assert fields["thread"] == "cert-run-1"
    assert fields["session"] == "cert-session-1"
    task_id, _state = _durable_round_trip(wrapper)
    assert task_id.startswith("task:")


def test_certified_pin_registry_matches_requirements() -> None:
    """The pin table in code equals the pinned requirements file."""
    requirements = (
        Path(__file__).parent / "requirements.txt"
    ).read_text(encoding="utf-8")
    for framework, pinned in _CERTIFIED_PINS.items():
        assert f"{framework}=={pinned}" in requirements, framework
