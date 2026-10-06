"""Compatibility examples: coordinate mapping, contract-only labeling."""

from __future__ import annotations

import pytest
from memorii.integrations.compatibility_examples import (
    CONTRACT_LABEL,
    AutoGenHostWrapper,
    CompatibilityExampleEnvelope,
    LangGraphHostWrapper,
    OpenAIAgentsHostWrapper,
)


@pytest.mark.parametrize(
    ("wrapper", "expected"),
    [
        (
            LangGraphHostWrapper(graph_id="g:1", thread_id="t:1", checkpoint_ns="ns"),
            {"host_kind": "langgraph", "session": "t:1", "thread": "g:1", "client_installation": "ns"},
        ),
        (
            AutoGenHostWrapper(conversation_id="c:1", participant_id="p:1"),
            {"host_kind": "autogen", "session": "c:1", "thread": "p:1", "client_installation": ""},
        ),
        (
            OpenAIAgentsHostWrapper(application_session="s:1", run_id="r:1"),
            {"host_kind": "openai_agents", "session": "s:1", "thread": "r:1", "client_installation": ""},
        ),
    ],
)
def test_every_framework_maps_to_the_same_binding_fields(wrapper, expected) -> None:
    assert wrapper.host_binding_fields() == expected
    envelope = CompatibilityExampleEnvelope(wrapper=wrapper, task_id="task:1")
    assert envelope.contract == CONTRACT_LABEL
    assert "not an installed adapter" in envelope.note


def test_examples_cannot_claim_installed_support() -> None:
    with pytest.raises(ValueError, match="installed support"):
        CompatibilityExampleEnvelope(
            wrapper=LangGraphHostWrapper(graph_id="g", thread_id="t"),
            task_id="task:1",
            note="this is installed support",
        )


def test_coordinate_schemas_are_closed() -> None:
    with pytest.raises(ValueError):
        LangGraphHostWrapper.model_validate(
            {"graph_id": "g", "thread_id": "t", "unexpected": True}
        )
