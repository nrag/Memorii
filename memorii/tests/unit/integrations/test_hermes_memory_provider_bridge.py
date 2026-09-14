"""Hermes external-memory bridge contracts without a Hermes installation."""

from __future__ import annotations

import importlib
import sys
import tomllib
from abc import ABC, abstractmethod
from importlib.metadata import EntryPoint
from pathlib import Path
from types import ModuleType

import pytest
from memorii.core.memory_evolution.writer_admission import writer_admission_memory_id
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.core.provider.models import ProviderStoredRecord
from memorii.domain.enums import MemoryDomain


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


def test_bridge_is_a_usable_hermes_abc_subclass_without_touching_storage(bridge_module) -> None:
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
    assert bridge_module._resolve_storage_root(hermes_home=tmp_path / "profile") == (
        tmp_path / "profile" / "memorii"
    )

    file_root = tmp_path / "profile" / "memorii"
    file_root.parent.mkdir()
    file_root.write_text("not a directory")
    with pytest.raises(ValueError, match="not a directory"):
        bridge_module._resolve_storage_root(hermes_home=tmp_path / "profile")
    with pytest.raises(ValueError, match="hermes_home"):
        bridge_module._resolve_storage_root(hermes_home=None)


def test_unconfigured_profile_fails_closed_before_canonical_startup(bridge_module, tmp_path: Path) -> None:
    provider = bridge_module.MemoriiHermesMemoryProvider()

    with pytest.raises(RuntimeError, match="no memorii.hermes.provider_service factory is installed"):
        provider.initialize("session:one", hermes_home=tmp_path)

    with pytest.raises(RuntimeError, match="has not been initialized"):
        provider.prefetch("what changed")


class _FactoryEntryPoint:
    def __init__(self, value: object) -> None:
        self._value = value

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


def test_configured_factory_starts_the_canonical_adapter_and_reopens_recall(
    bridge_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from tests.integration.test_observation_ledger_activation import _provider_factory, _seed_provider
    from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import _host_ingress

    authority_root = tmp_path / "authority"
    authority_root.mkdir()
    build_service, _, _ = _provider_factory(
        authority_root, monkeypatch, normalization=True, complete_registry=True
    )

    issued_requests = []
    services = []
    reject_ingress = [False]

    def factory(context):
        service = build_service(
            MemoryPlaneService(record_store=JsonlMemoryPlaneStore(context.storage_root / "memory-plane"))
        )
        if service._memory_plane.get_record(writer_admission_memory_id()) is None:
            _seed_provider(service)
            service.seed_committed_record(
                ProviderStoredRecord(
                    memory_id="semantic:atlas-owner",
                    domain=MemoryDomain.SEMANTIC,
                    text="Atlas migration owner is Alice.",
                    status="committed",
                    session_id=context.session_id,
                    user_id=context.user_id,
                )
            )
        services.append(service)
        def issue_ingress(request):
            issued_requests.append(request)
            return object() if reject_ingress[0] else _host_ingress()

        return bridge_module.HermesProviderRuntimeBinding(service=service, issue_ingress=issue_ingress)

    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(factory),),
    )
    first = bridge_module.MemoriiHermesMemoryProvider()
    first.initialize("session:one", hermes_home=tmp_path / "profile", user_id="user:alice")

    assert "Atlas migration owner is Alice." in first.prefetch("Who owns Atlas?")
    completed_messages = [
        {"role": "user", "content": "The Zephyr deployment owner is Bob."},
        {"role": "assistant", "content": "I will remember that Bob owns Zephyr deployment."},
    ]
    first.sync_turn(
        "The Zephyr deployment owner is Bob.",
        "I will remember that Bob owns Zephyr deployment.",
        messages=completed_messages,
        turn_author={"id": "user:alice"},
    )
    first.sync_turn(
        "The Zephyr deployment owner is Bob.",
        "I will remember that Bob owns Zephyr deployment.",
        messages=completed_messages,
        turn_author={"id": "user:alice"},
    )

    assert len(services[0]._memory_plane.list_records(source_kind="semantic_ingestion_source")) == 2
    assert [request.hook for request in issued_requests] == ["sync_turn", "sync_turn"]
    assert issued_requests[0].session_id == "session:one"
    assert issued_requests[0].user_id == "user:alice"
    assert issued_requests[0].turn_author == {"id": "user:alice"}

    first.on_turn_start(2, "Who owns Atlas?", author_id="user:bob")
    assert "Atlas migration owner is Alice." not in first.prefetch("Who owns Atlas?")

    assert first.on_pre_compress(completed_messages) == ""
    first.on_memory_write("upsert", "memory", "Atlas is active.")
    first.on_delegation("verify Atlas", "Atlas verified", child_session_id="session:child")
    first.on_session_end(completed_messages)
    first.on_session_switch(
        "session:two",
        parent_session_id="session:one",
        reset=False,
        rewound=False,
        user_id="user:bob",
    )

    assert [request.hook for request in issued_requests] == [
        "sync_turn",
        "sync_turn",
        "pre_compress",
        "memory_write",
        "delegation",
        "session_end",
    ]
    assert issued_requests[4].session_id == "session:child"
    assert all(request.user_id == "user:bob" for request in issued_requests[2:])

    source_count = len(services[0]._memory_plane.list_records(source_kind="semantic_ingestion_source"))
    reject_ingress[0] = True
    with pytest.raises(TypeError, match="must return AuthenticatedHostIngress"):
        first.on_memory_write("upsert", "memory", "must not persist")
    assert len(services[0]._memory_plane.list_records(source_kind="semantic_ingestion_source")) == source_count

    first.shutdown()
    reopened = bridge_module.MemoriiHermesMemoryProvider()
    reopened.initialize("session:one", hermes_home=tmp_path / "profile", user_id="user:alice")

    assert "Atlas migration owner is Alice." in reopened.prefetch("Who owns Atlas?")
