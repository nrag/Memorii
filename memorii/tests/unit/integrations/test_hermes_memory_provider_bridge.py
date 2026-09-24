"""Hermes external-memory bridge contracts without a Hermes installation."""

from __future__ import annotations

import importlib
import sys
import tomllib
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from importlib.metadata import EntryPoint
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture
def bridge_module(monkeypatch: pytest.MonkeyPatch):
    agent_module = ModuleType("agent")
    memory_provider_module = ModuleType("agent.memory_provider")

    class FakeMemoryProvider(ABC):
        @property
        @abstractmethod
        def name(self) -> str: ...

        @abstractmethod
        def is_available(self) -> bool: ...

        @abstractmethod
        def initialize(self, session_id: str, **kwargs: object) -> None: ...

        @abstractmethod
        def get_tool_schemas(self) -> list[dict[str, object]]: ...

    memory_provider_module.MemoryProvider = FakeMemoryProvider
    monkeypatch.setitem(sys.modules, "agent", agent_module)
    monkeypatch.setitem(sys.modules, "agent.memory_provider", memory_provider_module)
    monkeypatch.delitem(sys.modules, "memorii.integrations.hermes_memory_provider", raising=False)
    return importlib.import_module("memorii.integrations.hermes_memory_provider")


def test_distribution_declares_the_hermes_memory_provider_entry_point() -> None:
    project = tomllib.loads((Path(__file__).parents[3] / "pyproject.toml").read_text())
    value = project["project"]["entry-points"]["hermes_agent.memory_providers"]["memorii"]

    entry_point = EntryPoint(name="memorii", value=value, group="hermes_agent.memory_providers")

    assert entry_point.value == "memorii.integrations.hermes_memory_provider:MemoriiHermesMemoryProvider"


def test_pinned_hermes_image_and_first_party_factory_match_the_level2_abi() -> None:
    root = Path(__file__).parents[4]
    dockerfile = (root / "Dockerfile.memorii").read_text()

    assert ("FROM nousresearch/hermes-agent@sha256:eaa1c0b93eea54dadb8b072ffaffd569f93af444eacc2f3a") in dockerfile
    assert (
        "memorii.integrations.hermes_factory:build_local_level2_runtime_binding"
        in (root / "memorii" / "pyproject.toml").read_text()
    )


def test_distribution_declares_exactly_one_first_party_hermes_service_factory() -> None:
    project = tomllib.loads((Path(__file__).parents[3] / "pyproject.toml").read_text())

    assert project["project"]["entry-points"]["memorii.hermes.provider_service"] == {
        "installed": "memorii.integrations.hermes_factory:build_local_level2_runtime_binding"
    }


def test_bridge_is_a_usable_hermes_abc_subclass_without_touching_storage(bridge_module) -> None:
    bridge_module.importlib.metadata.entry_points = lambda *, group: ()
    provider = bridge_module.MemoriiHermesMemoryProvider()

    assert isinstance(provider, bridge_module.MemoryProvider)
    assert provider.name == "memorii"
    assert not provider.is_available()
    assert provider.unavailable_reason() == "no memorii.hermes.provider_service factory is installed"
    assert provider.get_tool_schemas() == []


def test_bridge_rejects_calls_before_successful_initialization(bridge_module) -> None:
    provider = bridge_module.MemoriiHermesMemoryProvider()

    with pytest.raises(RuntimeError, match="has not been initialized"):
        provider.prefetch("what changed")
    with pytest.raises(ValueError, match="does not provide Hermes tool"):
        provider.handle_tool_call("memorii.search", {})


def test_operation_identity_reuses_completed_transcript_and_separates_positions(bridge_module) -> None:
    first_messages = [
        {"role": "user", "content": "remember Atlas"},
        {"role": "assistant", "content": "acknowledged"},
    ]
    later_messages = [
        *first_messages,
        {"role": "user", "content": "remember Atlas"},
        {"role": "assistant", "content": "acknowledged"},
    ]

    first = bridge_module._operation_id("sync_turn", "session:one", first_messages)

    assert first == bridge_module._operation_id("sync_turn", "session:one", first_messages)
    assert first != bridge_module._operation_id("sync_turn", "session:one", later_messages)
    assert first.startswith("hermes:")


def test_default_storage_root_is_profile_local_and_invalid_roots_fail(bridge_module, tmp_path: Path) -> None:
    assert bridge_module._resolve_storage_root(hermes_home=tmp_path / "profile") == (tmp_path / "profile" / "memorii")

    file_root = tmp_path / "profile" / "memorii"
    file_root.parent.mkdir()
    file_root.write_text("not a directory")
    with pytest.raises(ValueError, match="not a directory"):
        bridge_module._resolve_storage_root(hermes_home=tmp_path / "profile")
    with pytest.raises(ValueError, match="hermes_home"):
        bridge_module._resolve_storage_root(hermes_home=None)


def test_unconfigured_profile_fails_closed_before_canonical_startup(
    bridge_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(bridge_module.importlib.metadata, "entry_points", lambda *, group: ())
    provider = bridge_module.MemoriiHermesMemoryProvider()

    with pytest.raises(RuntimeError, match="no memorii.hermes.provider_service factory is installed"):
        provider.initialize("session:one", hermes_home=tmp_path)

    with pytest.raises(RuntimeError, match="has not been initialized"):
        provider.prefetch("what changed")


def test_first_party_factory_rejects_missing_authority_before_service_construction(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding

    called = False

    def should_not_build(*args, **kwargs):
        nonlocal called
        del args, kwargs
        called = True
        raise AssertionError("service construction must follow authority validation")

    monkeypatch.setattr("memorii.integrations.hermes_factory.build_provider_memory_service_from_env", should_not_build)
    context = bridge_module.HermesProviderServiceContext(
        storage_root=tmp_path / "memorii",
        hermes_home=tmp_path,
        session_id="session:one",
        user_id="user:one",
        agent_identity=None,
        agent_workspace=None,
        parent_session_id=None,
    )

    with pytest.raises(Exception, match="identity is absent"):
        build_local_level2_runtime_binding(context)
    assert called is False


def test_first_party_factory_initializes_after_authority_validation_without_openai_call(
    bridge_module, tmp_path: Path
) -> None:
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import (
        LocalLevel2AuthorityError,
        authorize_local_level2,
    )

    authorize_local_level2(hermes_home=tmp_path)
    context = bridge_module.HermesProviderServiceContext(
        storage_root=tmp_path / "memorii",
        hermes_home=tmp_path,
        session_id="session:one",
        user_id="user:one",
        agent_identity=None,
        agent_workspace=None,
        parent_session_id=None,
    )

    binding = build_local_level2_runtime_binding(context)

    assert isinstance(binding, bridge_module.HermesProviderRuntimeBinding)
    with pytest.raises(ValueError, match="operator identity is substituted"):
        binding.issue_ingress(
            bridge_module.HermesIngressRequest(
                hook="sync_turn",
                session_id="session:one",
                user_id="user:one",
                agent_identity=None,
                turn_author=None,
                received_at=datetime.now(UTC),
            )
        )
    ingress = binding.issue_ingress(
        bridge_module.HermesIngressRequest(
            hook="sync_turn",
            session_id="session:one",
            user_id=binding.absent_author_id,
            agent_identity=None,
            turn_author=None,
            received_at=datetime.now(UTC),
        )
    )
    assert ingress.provider_identity == "hermes"
    assert ingress.principal_handle.author_id == binding.absent_author_id
    assert binding.absent_author_id.startswith("memorii:hermes:operator:")
    with pytest.raises(LocalLevel2AuthorityError, match="already bound"):
        build_local_level2_runtime_binding(
            bridge_module.HermesProviderServiceContext(
                storage_root=tmp_path / "memorii",
                hermes_home=tmp_path,
                session_id="session:two",
                user_id="user:two",
                agent_identity=None,
                agent_workspace=None,
                parent_session_id=None,
            )
        )


def test_bridge_rejects_changed_raw_author_before_turn_admission(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import authorize_local_level2

    authorize_local_level2(hermes_home=tmp_path)
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider.initialize("session:one", hermes_home=tmp_path, user_id="raw:user:one")

    with pytest.raises(ValueError, match="author identity changed"):
        provider.on_turn_start(1, "hello", author_id="raw:user:two")
    with pytest.raises(ValueError, match="author identity changed"):
        provider.sync_turn(
            "hello",
            "acknowledged",
            session_id="session:one",
            messages=[
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "acknowledged"},
            ],
            turn_author={"id": "raw:user:two"},
        )


def test_bridge_without_initial_raw_user_rejects_author_bearing_callbacks(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import authorize_local_level2

    authorize_local_level2(hermes_home=tmp_path)
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider.initialize("session:one", hermes_home=tmp_path)
    before = tuple(provider._provider._service._memory_plane.list_records())

    with pytest.raises(ValueError, match="author identity changed"):
        provider.on_turn_start(1, "hello", author_id="raw:user:one")
    with pytest.raises(ValueError, match="author identity changed"):
        provider.sync_turn(
            "hello",
            "acknowledged",
            session_id="session:one",
            messages=[
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "acknowledged"},
            ],
            turn_author={"id": "raw:user:one"},
        )
    assert tuple(provider._provider._service._memory_plane.list_records()) == before


class _FactoryEntryPoint:
    def __init__(
        self,
        value: object,
        definition: str = "memorii.integrations.hermes_factory:build_local_level2_runtime_binding",
    ) -> None:
        self._value = value
        self.value = definition

    def load(self) -> object:
        return self._value


def test_multiple_or_noncallable_service_factories_are_unavailable(
    bridge_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(lambda context: context), _FactoryEntryPoint(lambda context: context)),
    )
    provider = bridge_module.MemoriiHermesMemoryProvider()
    assert not provider.is_available()
    assert provider.unavailable_reason() == "multiple memorii.hermes.provider_service factories are installed"

    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(object()),),
    )
    assert not provider.is_available()
    assert provider.unavailable_reason() == "configured memorii.hermes.provider_service value is not callable"


def test_factory_context_is_profile_scoped_and_rejects_the_wrong_service_type(
    bridge_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    contexts = []

    def factory(context):
        contexts.append(context)
        return object()

    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(factory),),
    )
    provider = bridge_module.MemoriiHermesMemoryProvider()

    with pytest.raises(TypeError, match="must return HermesProviderRuntimeBinding"):
        provider.initialize(
            "session:one",
            hermes_home=tmp_path / "profile",
            user_id="user:alice",
            agent_identity={"id": "agent:one"},
            agent_workspace="/workspace",
            parent_session_id="parent:one",
        )

    assert len(contexts) == 1
    assert contexts[0].storage_root == tmp_path / "profile" / "memorii"
    assert contexts[0].session_id == "session:one"
    assert contexts[0].user_id == "user:alice"
    assert contexts[0].parent_session_id == "parent:one"
