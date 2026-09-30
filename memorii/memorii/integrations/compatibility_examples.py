"""LangGraph/AutoGen/OpenAI Agents compatibility examples (contract-only).

The design (spec 22.2) requires documented adapter contracts for these
frameworks; actual framework-version certification is required only
before advertising an installed adapter. Each example below maps the
framework's native coordinates into the same versioned command/state
schema, duplicate/conflict rules, dispatch reconciliation and
candidate/committed distinctions. Native session identity alone is
never user authority. These are protocol fixtures, not installed
support, and are labeled as such everywhere they surface.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTRACT_LABEL = "memorii-compatibility-example/v1"


class _ExampleBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LangGraphHostWrapper(_ExampleBase):
    """Maps graph/thread/checkpoint coordinates to a task binding.

    LangGraph retains its own checkpoint authority; the wrapper only
    translates coordinates and durable observations.
    """

    framework: Literal["langgraph"] = "langgraph"
    graph_id: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)
    checkpoint_ns: str | None = None

    def host_binding_fields(self) -> dict[str, str]:
        return {
            "host_kind": "langgraph",
            "session": self.thread_id,
            "thread": self.graph_id,
            "client_installation": self.checkpoint_ns or "",
        }


class AutoGenHostWrapper(_ExampleBase):
    """Maps conversation/participant and tool-delivery identities.

    Each participant receives a finite task scope from the host grant,
    never from message fields.
    """

    framework: Literal["autogen"] = "autogen"
    conversation_id: str = Field(min_length=1)
    participant_id: str = Field(min_length=1)

    def host_binding_fields(self) -> dict[str, str]:
        return {
            "host_kind": "autogen",
            "session": self.conversation_id,
            "thread": self.participant_id,
            "client_installation": "",
        }


class OpenAIAgentsHostWrapper(_ExampleBase):
    """Maps application session/run/item identities."""

    framework: Literal["openai_agents"] = "openai_agents"
    application_session: str = Field(min_length=1)
    run_id: str = Field(min_length=1)

    def host_binding_fields(self) -> dict[str, str]:
        return {
            "host_kind": "openai_agents",
            "session": self.application_session,
            "thread": self.run_id,
            "client_installation": "",
        }


CompatibilityHostWrapper = LangGraphHostWrapper | AutoGenHostWrapper | OpenAIAgentsHostWrapper


class CompatibilityExampleEnvelope(_ExampleBase):
    """The shared versioned protocol every example produces."""

    contract: Literal["memorii-compatibility-example/v1"] = CONTRACT_LABEL
    wrapper: CompatibilityHostWrapper
    task_id: str = Field(min_length=1)
    note: str = "contract example; not an installed adapter"

    @model_validator(mode="after")
    def label_is_never_installled(self) -> CompatibilityExampleEnvelope:
        if "installed" in self.note and "not" not in self.note:
            raise ValueError("compatibility examples must not claim installed support")
        return self


__all__ = [
    "CONTRACT_LABEL",
    "AutoGenHostWrapper",
    "CompatibilityExampleEnvelope",
    "CompatibilityHostWrapper",
    "LangGraphHostWrapper",
    "OpenAIAgentsHostWrapper",
]
