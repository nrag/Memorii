"""Hermes external-memory bridge contracts without a Hermes installation."""

from __future__ import annotations

import importlib
import socket
import sys
import tomllib
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from importlib.metadata import EntryPoint
from pathlib import Path
from threading import Event, Thread
from types import ModuleType, SimpleNamespace

import pytest
from memorii.core.memory_evolution.atomic_store import StructuredSubmissionGrantRevokedError
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.provider.models import ProviderOperation
from memorii.core.semantic_ingestion.default_catalog_corpus import (
    EXPECTED_DEFAULT_RELATION_IDS,
    DefaultCatalogCorpusRow,
    load_default_catalog_acceptance_corpus,
)
from tests.fixtures.semantic_ingestion.default_catalog_proposals import (
    DefaultCatalogProposalFixture,
    build_default_catalog_proposal,
)


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

    assert "ARG HERMES_IMAGE=nousresearch/hermes-agent@sha256:6bece0644e29a347e5ae17db43c36938c86f171c6f5e0cef18aa2075d331f3a3" in dockerfile
    assert "FROM ${HERMES_IMAGE}" in dockerfile
    assert (
        "memorii.integrations.hermes_factory:build_local_level2_runtime_binding"
        in (root / "memorii" / "pyproject.toml").read_text()
    )
    assert "prepare_memorii_docker_context.py" in dockerfile
    assert "load_project_assertions_bundle" in dockerfile


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


def test_turn_start_delegates_the_pinned_callback_identity_to_capture_runtime(bridge_module) -> None:
    calls: list[dict[str, object]] = []
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider._provider = object()
    provider._session_id = "session:one"
    provider._default_user_id = "user:ada"
    provider._absent_author_id = "operator:ada"
    provider._completed_turn_runtime = SimpleNamespace(capture_user_turn=lambda **kwargs: calls.append(kwargs))

    provider.on_turn_start(7, "Atlas owner is Ada.", author_id="user:ada")

    assert calls[0]["session_id"] == "session:one"
    assert calls[0]["turn_ordinal"] == 7
    assert calls[0]["message"] == "Atlas owner is Ada."
    assert calls[0]["authenticated_author_id"] == "operator:ada"
    assert isinstance(calls[0]["received_at"], datetime)


def test_sync_turn_joins_a_captured_turn_without_legacy_duplicate_admission(bridge_module) -> None:
    completed: list[dict[str, object]] = []
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider._provider = object()
    provider._session_id = "session:one"
    provider._default_user_id = "user:ada"
    provider._absent_author_id = "operator:ada"
    provider._completed_turn_runtime = SimpleNamespace(
        complete_captured_turn=lambda **kwargs: (completed.append(kwargs) or True),
        sync_completed_turn=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("legacy duplicate admission")),
    )

    provider.sync_turn(
        "Atlas owner is Ada.", "I will remember that.",
        messages=[
            {"role": "user", "content": "Atlas owner is Ada."},
            {"role": "assistant", "content": "I will remember that."},
        ],
    )

    assert completed[0]["session_id"] == "session:one"
    assert completed[0]["authenticated_author_id"] == "operator:ada"


def test_completed_runtime_lifecycle_hooks_drain_before_read_or_return_without_legacy_ingress(bridge_module) -> None:
    calls: list[object] = []
    ordering: list[str] = []
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider._provider = SimpleNamespace(
        on_session_end=lambda *args, **kwargs: calls.append(("session_end", args, kwargs)),
        on_pre_compress=lambda *args, **kwargs: calls.append(("pre_compress", args, kwargs)),
    )
    provider._completed_turn_runtime = SimpleNamespace(
        wait_for_idle=lambda: ordering.append("drain"),
        prefetch=lambda **_kwargs: (ordering.append("prefetch") or "committed context"),
    )
    provider._issue_ingress = lambda _request: (_ for _ in ()).throw(AssertionError("legacy ingress must not issue"))

    provider.on_session_end(["completed turn"])
    assert provider.on_pre_compress(["completed turn"]) == ""
    assert provider.prefetch("what changed") == "committed context"
    provider.on_memory_write("add", "MEMORY.md", "completed turn")
    provider.on_delegation("task", "result", child_session_id="child:one")

    assert calls == []
    assert ordering == ["drain", "drain", "drain", "prefetch", "drain", "drain"]


def test_completed_runtime_delegation_refuses_ambiguous_parent_turns(bridge_module) -> None:
    from memorii.integrations.hermes_runtime_binding import (
        HermesAuthenticatedOriginReceipt,
    )

    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider._provider = object()
    provider._session_id = "session:parent"
    provider._completed_turn_runtime = SimpleNamespace(wait_for_idle=lambda: None)
    provider._origin_receipts = {
        ("session:parent", ordinal): HermesAuthenticatedOriginReceipt.create(
            session_id="session:parent",
            turn_ordinal=ordinal,
            author_id="user:one",
            source_content_digest=str(ordinal) * 64,
        )
        for ordinal in (1, 2)
    }
    provider._issue_forwarding_receipt = lambda *_args: (_ for _ in ()).throw(
        AssertionError("ambiguous parent must not issue a forwarding receipt")
    )

    provider.on_delegation(
        "older task",
        "delayed result",
        child_session_id="session:child",
    )

    assert provider._pending_forwarding_receipts == {}


@pytest.mark.parametrize(
    "invoke",
    [
        lambda provider: provider.on_session_end(["completed turn"]),
        lambda provider: provider.on_pre_compress(["completed turn"]),
        lambda provider: provider.prefetch("what changed"),
        lambda provider: provider.on_memory_write("add", "MEMORY.md", "completed turn"),
        lambda provider: provider.on_delegation("task", "result"),
    ],
)
def test_completed_runtime_lifecycle_drain_failures_surface_without_clearing_state(bridge_module, invoke) -> None:
    provider = bridge_module.MemoriiHermesMemoryProvider()
    legacy = object()
    runtime = SimpleNamespace(wait_for_idle=lambda: (_ for _ in ()).throw(RuntimeError("semantic worker failed")))
    provider._provider = legacy
    provider._completed_turn_runtime = runtime
    provider._issue_ingress = lambda _request: object()

    with pytest.raises(RuntimeError, match="semantic worker failed"):
        invoke(provider)

    assert provider._provider is legacy
    assert provider._completed_turn_runtime is runtime
    assert provider._issue_ingress is not None


def test_legacy_lifecycle_hooks_remain_active_without_completed_runtime(bridge_module) -> None:
    calls: list[tuple[str, object, dict[str, object]]] = []
    ingress_hooks: list[str] = []
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider._session_id = "session:one"
    provider._default_user_id = "user:ada"
    provider._provider = SimpleNamespace(
        on_session_end=lambda messages, **kwargs: calls.append(("session_end", messages, kwargs)),
        on_pre_compress=lambda messages, **kwargs: calls.append(("pre_compress", messages, kwargs)),
    )
    provider._require_ingress = lambda *, hook, **_kwargs: ingress_hooks.append(hook) or object()

    provider.on_session_end(["legacy turn"])
    assert provider.on_pre_compress(["legacy turn"]) == ""

    assert [call[0] for call in calls] == ["session_end", "pre_compress"]
    assert ingress_hooks == ["session_end", "pre_compress"]


def test_shutdown_drains_completed_runtime_before_clearing_provider_state(bridge_module) -> None:
    calls: list[str] = []
    provider = bridge_module.MemoriiHermesMemoryProvider()
    legacy = object()
    provider._provider = legacy
    provider._session_id = "session:one"
    provider._default_user_id = "user:ada"
    provider._agent_identity = "profile:primary"
    provider._issue_ingress = lambda _request: object()

    def close() -> None:
        assert provider._provider is legacy
        calls.append("closed")

    provider._completed_turn_runtime = SimpleNamespace(close=close)
    provider.shutdown()

    assert calls == ["closed"]
    assert provider._provider is None
    assert provider._completed_turn_runtime is None
    assert provider._issue_ingress is None
    assert provider._session_id == ""
    assert provider._current_user_id() is None


def test_shutdown_propagates_worker_failure_and_still_clears_provider_state(bridge_module) -> None:
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider._provider = object()
    provider._issue_ingress = lambda _request: object()

    def failed_close() -> None:
        raise RuntimeError("semantic worker failed")

    provider._completed_turn_runtime = SimpleNamespace(close=failed_close)

    with pytest.raises(RuntimeError, match="semantic worker failed"):
        provider.shutdown()

    assert provider._provider is None
    assert provider._completed_turn_runtime is None
    assert provider._issue_ingress is None


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
        agent_identity="profile:primary",
        platform="cli",
        agent_context="primary",
        agent_workspace="hermes",
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
        agent_identity="profile:primary",
        platform="cli",
        agent_context="primary",
        agent_workspace="hermes",
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
                agent_identity="profile:primary",
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
    assert len(binding.service._memory_plane.list_records(
        source_kind="semantic_ingestion_catalog_version"
    )) == 1
    assert len(binding.service._memory_plane.list_records(
        source_kind="semantic_ingestion_catalog_selection_pointer"
    )) == 1
    runtime = binding.completed_turn_runtime
    assert runtime is not None
    runtime.close()
    reopened = build_local_level2_runtime_binding(
        bridge_module.HermesProviderServiceContext(
            storage_root=tmp_path / "memorii",
            hermes_home=tmp_path,
            session_id="session:two",
            user_id="user:one",
            agent_identity="profile:primary",
            platform="cli",
            agent_context="primary",
            agent_workspace="hermes",
            parent_session_id=None,
        )
    )
    assert len(reopened.service._memory_plane.list_records(
        source_kind="semantic_ingestion_catalog_selection_pointer"
    )) == 1
    reopened_runtime = reopened.completed_turn_runtime
    assert reopened_runtime is not None
    reopened_runtime.close()
    with pytest.raises(LocalLevel2AuthorityError, match="already bound"):
        build_local_level2_runtime_binding(
            bridge_module.HermesProviderServiceContext(
                storage_root=tmp_path / "memorii",
                hermes_home=tmp_path,
                session_id="session:two",
                user_id="user:two",
                agent_identity="profile:primary",
                platform="cli",
                agent_context="primary",
                agent_workspace="hermes",
                parent_session_id=None,
            )
        )


def test_installed_no_observer_persists_one_pending_coverage_observation_after_reopen(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from memorii.core.memory_plane.service import MemoryPlaneService
    from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
    from memorii.core.provider.models import ProviderOperation
    from memorii.core.semantic_ingestion.coverage_observation import (
        CoverageObservationRepository,
        CoverageSemanticOutcome,
        DiscoveryProcessingState,
    )
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import authorize_local_level2

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    authorize_local_level2(hermes_home=tmp_path)
    context = bridge_module.HermesProviderServiceContext(
        storage_root=tmp_path / "memorii",
        hermes_home=tmp_path,
        session_id="session:coverage",
        user_id="raw:user:one",
        agent_identity="profile:primary",
        platform="cli",
        agent_context="primary",
        agent_workspace="hermes",
        parent_session_id=None,
    )
    binding = build_local_level2_runtime_binding(context)
    received_at = datetime(2026, 9, 27, 12, tzinfo=UTC)
    ingress = binding.issue_ingress(
        bridge_module.HermesIngressRequest(
            hook="sync_turn",
            session_id="session:coverage",
            user_id=binding.absent_author_id,
            agent_identity="profile:primary",
            turn_author=None,
            received_at=received_at,
        )
    )
    call = {
        "operation": ProviderOperation.CHAT_USER_TURN,
        "content": "Please remember this source for later ontology coverage.",
        "operation_id": "coverage-observation-one",
        "session_id": "session:coverage",
        "user_id": binding.absent_author_id,
        "authenticated_host_ingress": ingress,
        "timestamp": received_at,
    }
    binding.service.sync_event(**call)
    binding.service.sync_event(**call)
    records = binding.service._memory_plane.list_records(
        source_kind="learned_ontology_coverage_observation_v1"
    )
    assert len(records) == 1
    observation = CoverageObservationRepository(binding.service._memory_plane).load(
        records[0].memory_id
    )
    assert observation is not None
    assert observation.processing_state == DiscoveryProcessingState.PENDING_NO_CAPABILITY
    assert observation.semantic_outcome == CoverageSemanticOutcome.NOT_EVALUATED
    binding.completed_turn_runtime.close()

    reopened_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(context.storage_root / "memory-plane")
    )
    reopened_records = reopened_plane.list_records(
        source_kind="learned_ontology_coverage_observation_v1"
    )
    assert len(reopened_records) == 1
    assert CoverageObservationRepository(reopened_plane).load(
        reopened_records[0].memory_id
    ) == observation
    assert not [
        record
        for record in reopened_plane.list_records()
        if record.source_kind in {
            "learned_ontology_change_proposal_v1",
            "learned_ontology_gap_fact_v1",
        }
    ]


def test_installed_ingress_coalesces_authenticated_forwarded_origin(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    from memorii.core.semantic_ingestion.coverage_observation import (
        CoverageObservationRepository,
    )
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import authorize_local_level2
    from memorii.integrations.hermes_provider import build_started_hermes_memory_provider

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    authorize_local_level2(hermes_home=tmp_path)
    context = bridge_module.HermesProviderServiceContext(
        storage_root=tmp_path / "memorii",
        hermes_home=tmp_path,
        session_id="session:origin-direct",
        user_id="raw:user:one",
        agent_identity="profile:primary",
        platform="cli",
        agent_context="primary",
        agent_workspace="hermes",
        parent_session_id=None,
    )
    binding = build_local_level2_runtime_binding(context)
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider._provider = build_started_hermes_memory_provider(service=binding.service)
    provider._session_id = "session:origin-direct"
    provider._default_user_id = binding.absent_author_id
    provider._turn_user_id.set(binding.absent_author_id)
    provider._agent_identity = "profile:primary"
    provider._issue_ingress = binding.issue_ingress
    provider._completed_turn_runtime = binding.completed_turn_runtime
    provider._absent_author_id = binding.absent_author_id
    provider._issue_origin_receipt = binding.issue_origin_receipt
    provider._issue_forwarding_receipt = binding.issue_forwarding_receipt
    monkeypatch.setattr(binding.service, "reconcile_memory_evolution", lambda: ())

    direct = "Atlas owner is Bob."
    forwarded = "Bob is the owner of Atlas."
    unrelated = "The office closes at six."
    provider.on_turn_start(1, direct, author_id=binding.absent_author_id)
    receipt = provider._origin_receipts[("session:origin-direct", 1)]
    with pytest.raises(ValueError, match="upstream origin receipt is invalid"):
        binding.issue_ingress(
            bridge_module.HermesIngressRequest(
                hook="delegation",
                session_id="session:origin-forwarded",
                user_id=binding.absent_author_id,
                agent_identity="profile:primary",
                turn_author=None,
                received_at=datetime.now(UTC),
                upstream_origin_receipt=replace(
                    receipt, receipt_digest="0" * 64
                ),
            )
        )

    first_messages = [
        {"role": "user", "content": direct, "timestamp": "2026-09-27T13:00:00Z"},
        {
            "role": "assistant",
            "content": "Acknowledged.",
            "timestamp": "2026-09-27T13:00:01Z",
        },
    ]
    provider.sync_turn(direct, "Acknowledged.", messages=first_messages)
    provider.on_delegation(
        "Restate the ownership fact.",
        forwarded,
        child_session_id="session:origin-forwarded",
    )
    provider.on_session_switch("session:origin-forwarded")
    provider.on_turn_start(
        1,
        forwarded,
        author_id=binding.absent_author_id,
        parent_session_id="session:origin-direct",
        parent_turn_number=1,
    )
    second_messages = [
        {
            "role": "user",
            "content": forwarded,
            "timestamp": "2026-09-27T13:01:00Z",
        },
        {
            "role": "assistant",
            "content": "Acknowledged again.",
            "timestamp": "2026-09-27T13:01:01Z",
        },
    ]
    provider.sync_turn(
        forwarded,
        "Acknowledged again.",
        messages=second_messages,
    )
    provider.on_session_switch("session:unrelated")
    provider.on_turn_start(
        1,
        unrelated,
        author_id=binding.absent_author_id,
        parent_session_id="session:origin-direct",
        parent_turn_number=1,
    )
    provider.sync_turn(
        unrelated,
        "Noted.",
        messages=[
            {
                "role": "user",
                "content": unrelated,
                "timestamp": "2026-09-27T13:02:00Z",
            },
            {
                "role": "assistant",
                "content": "Noted.",
                "timestamp": "2026-09-27T13:02:01Z",
            },
        ],
    )
    binding.completed_turn_runtime.wait_for_idle()

    observations = tuple(
        observation
        for record in binding.service._memory_plane.list_records(
            source_kind="learned_ontology_coverage_observation_v1"
        )
        if (
            observation := CoverageObservationRepository(
                binding.service._memory_plane
            ).load(record.memory_id)
        )
        is not None
    )
    assert len(observations) == 3
    by_text = {
        binding.service._memory_plane.get_record(observation.source_id).text: observation
        for observation in observations
    }
    assert by_text[direct].session_id == "session:origin-direct"
    assert by_text[forwarded].session_id == "session:origin-forwarded"
    assert by_text[unrelated].session_id == "session:unrelated"
    assert (
        by_text[direct].origin_lineage_digest
        == by_text[forwarded].origin_lineage_digest
    )
    assert (
        by_text[direct].origin_lineage_digest
        != by_text[unrelated].origin_lineage_digest
    )
    provider.shutdown()


def test_factory_issues_stable_exact_local_structured_grants() -> None:
    from memorii.core.semantic_ingestion.catalog_authority import (
        AuthenticatedPrincipalAgent,
        StructuredSubmissionAuthorityRequest,
    )
    from memorii.integrations.hermes_factory import _LocalLevel2StructuredSubmissionResolver

    resolver = _LocalLevel2StructuredSubmissionResolver(
        installation_id="installation:one",
        operator_id="operator:one",
        agent_id="agent:one",
        project_task_id="task:one",
        authority_is_current=lambda: True,
        structured_tool_is_current=lambda: True,
    )
    authority = resolver.issued_authority()
    assert authority.source_grant.grant_id.startswith("hermes-local-structured-grant:v1:source:")
    assert authority.fact_grant.grant_id.startswith("hermes-local-structured-grant:v1:fact:")
    assert authority.catalog_visibility_grant.grant_id.startswith(
        "hermes-local-structured-grant:v1:catalog_visibility:"
    )
    assert {authority.source_grant.grant_version, authority.fact_grant.grant_version,
            authority.catalog_visibility_grant.grant_version} == {1}

    request = StructuredSubmissionAuthorityRequest(
        authenticated=AuthenticatedPrincipalAgent(principal_id="operator:one", agent_id="agent:one"),
        source_grant=authority.source_grant,
        fact_grant=authority.fact_grant,
        catalog_visibility_grant=authority.catalog_visibility_grant,
    )
    ingress = SimpleNamespace(
        delivery_principal_binding=SimpleNamespace(principal_subject_id="operator:one"),
        authenticated_agent_id="agent:one",
    )
    assert resolver.resolve_submission_authority(authenticated_ingress=ingress, request=request) == authority
    assert resolver.resolve_submission_authority(
        authenticated_ingress=ingress,
        request=request.model_copy(update={"fact_grant": request.fact_grant.model_copy(update={"grant_version": 2})}),
    ) is None


def _append_external_control_record(*, storage_root: Path, record: CanonicalMemoryRecord) -> None:
    """Model a persisted control-plane corruption from a second process."""
    from memorii.core.memory_plane import JsonlMemoryPlaneStore
    from memorii.core.memory_plane.store import _PersistedBatch

    store = JsonlMemoryPlaneStore(storage_root / "memory-plane")
    with store._locked(exclusive=True):
        batches, _records = store._current_records_unlocked()
        write_revision = batches[-1].revision if batches else 0
        data_revision = batches[-1].data_revision if batches else 0
        store._replace_batches([
            *batches,
            _PersistedBatch.create(
                revision=write_revision + 1,
                data_revision=data_revision,
                records=(record,),
            ),
        ])


def test_installed_factory_uses_base_catalog_when_no_agent_local_control_exists(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An untouched owner remains eligible for the persisted base catalog."""
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import (
        authorize_local_level2,
        authorize_local_structured_tool,
    )

    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider.initialize(
        "session:base", hermes_home=tmp_path, user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes",
    )
    try:
        provider.on_turn_start(1, "Atlas owner is Ada.")
        assert [schema["function"]["name"] for schema in provider.get_tool_schemas()][:2] == [
            "memorii_submit_fact", "memorii_read_fact",
        ]
    finally:
        provider.shutdown()


@pytest.mark.parametrize("corruption", ("malformed_pointer", "missing_version", "substituted_scope"))
def test_installed_factory_denies_invalid_agent_local_control_without_base_fallback(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corruption: str,
) -> None:
    """The production root withholds egress and writes no fact for bad learned control."""
    from memorii.core.semantic_ingestion.learned_relation import (
        AgentLocalCatalogScope,
        CatalogPointer,
        learned_catalog_pointer_memory_id,
    )
    from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import (
        authorize_local_level2,
        authorize_local_structured_tool,
    )

    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider.initialize(
        "session:corrupt", hermes_home=tmp_path, user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes",
    )
    try:
        runtime = provider._completed_turn_runtime
        assert runtime is not None
        scope = AgentLocalCatalogScope(
            principal_id=provider._absent_author_id,
            agent_id=runtime._authenticated_agent_id,
        )
        pointer_scope = (
            AgentLocalCatalogScope(principal_id="substituted:owner", agent_id=scope.agent_id)
            if corruption == "substituted_scope" else scope
        )
        pointer = CatalogPointer.create(
            catalog_scope=pointer_scope,
            selected_version_digest="a" * 64,
            selected_attempt_id="oca_" + "b" * 64,
            activation_sequence=1,
        )
        content = {"pointer": {}} if corruption == "malformed_pointer" else {
            "pointer": pointer.model_dump(mode="json"),
        }
        _append_external_control_record(
            storage_root=tmp_path / "memorii",
            record=CanonicalMemoryRecord(
                memory_id=learned_catalog_pointer_memory_id(scope),
                domain=MemoryDomain.EXECUTION,
                text="",
                content=content,
                status=CommitStatus.COMMITTED,
                source_kind="learned_ontology_catalog_pointer_v1",
                visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
                timestamp=datetime.now(UTC),
            ),
        )
        provider.on_turn_start(1, "Atlas owner is Ada.")
        assert provider.get_tool_schemas() == []
        assert provider.handle_tool_call("memorii_submit_fact", {"schema_version": 1}) == {
            "status": "unavailable",
        }
        records = tuple(provider._provider._service._memory_plane.list_records())
        assert not any(
            record.content.get("runtime_context_projection_kind")
            == "bootstrap_v3_claim_assertion"
            for record in records
        )
    finally:
        provider.shutdown()


def test_installed_factory_provisions_the_tool_grant_trio_only_with_tool_artifact(
    bridge_module, tmp_path: Path,
) -> None:
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import (
        authorize_local_level2,
        authorize_local_structured_tool,
    )

    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    binding = build_local_level2_runtime_binding(
        bridge_module.HermesProviderServiceContext(
            storage_root=tmp_path / "memorii", hermes_home=tmp_path,
            session_id="session:one", user_id=None, agent_identity="profile:primary",
            platform="cli", agent_context="primary", agent_workspace="hermes",
            parent_session_id=None,
        )
    )
    states = binding.service._memory_plane.list_records(
        source_kind="semantic_ingestion_structured_grant_state"
    )
    assert len(states) == 3
    assert {record.content["state"]["grant_kind"] for record in states} == {
        "source", "fact", "catalog_visibility",
    }
    assert all(record.content["state"]["active"] for record in states)
    binding.completed_turn_runtime.close()


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
    provider.initialize(
        "session:one",
        hermes_home=tmp_path,
        user_id="raw:user:one",
        agent_identity="profile:primary",
        platform="cli",
        agent_context="primary",
        agent_workspace="hermes",
    )

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


def test_installed_bridge_turn_start_reaches_source_only_capture_owner_without_openai(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.core.semantic_ingestion.openai_responses_project_assertions import OpenAIResponsesApiClient
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import authorize_local_level2

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        OpenAIResponsesApiClient,
        "complete",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("model transport must not run")),
    )
    authorize_local_level2(hermes_home=tmp_path)
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider.initialize(
        "session:one", hermes_home=tmp_path, user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes",
    )

    provider.on_turn_start(1, "Atlas owner is Ada.")

    records = provider._provider._service._memory_plane.list_records()
    assert any(record.source_kind == "semantic_ingestion_hermes_captured_turn" for record in records)
    assert any(record.source_kind == "semantic_ingestion_prepared_source" for record in records)
    assert not any(record.source_kind == "semantic_ingestion_preplanning_control" for record in records)
    provider.shutdown()


def test_installed_no_key_bridge_advertises_only_the_closed_structured_tool_after_capture(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import (
        authorize_local_level2,
        authorize_local_structured_tool,
    )

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider.initialize(
        "session:one", hermes_home=tmp_path, user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes",
    )

    assert provider.get_tool_schemas() == []
    provider.on_turn_start(1, "Atlas owner is Ada.")
    schemas = provider.get_tool_schemas()

    assert [schema["function"]["name"] for schema in schemas] == [
        "memorii_submit_fact", "memorii_read_fact",
    ]
    parameters = schemas[0]["function"]["parameters"]
    assert parameters["additionalProperties"] is False
    assert provider.handle_tool_call("memorii_submit_fact", {"schema_version": 2}) == {
        "status": "rejected"
    }
    provider.shutdown()


def test_installed_no_key_bridge_reaches_learned_mentors_submission_without_model_transport(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.core.semantic_ingestion.openai_responses_project_assertions import OpenAIResponsesApiClient
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import (
        authorize_local_level2,
        authorize_local_structured_tool,
    )

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    def network_forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("installed structured fact attempted network access")

    monkeypatch.setattr(socket, "getaddrinfo", network_forbidden)
    monkeypatch.setattr(socket, "create_connection", network_forbidden)
    monkeypatch.setattr(socket.socket, "connect", network_forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", network_forbidden)
    monkeypatch.setattr(
        OpenAIResponsesApiClient,
        "complete",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("model transport must not run")),
    )
    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider.initialize(
        "session:one", hermes_home=tmp_path, user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes",
    )
    from memorii.core.semantic_ingestion.learned_relation import (
        AgentLocalCatalogScope,
        OntologyChangeProposal,
        OntologyEvidenceReference,
        PairedEvaluation,
        RelationDeclaration,
    )

    learned = provider._learned_ontology_runtime
    assert learned is not None
    active_runtime = provider._completed_turn_runtime
    assert active_runtime is not None
    scope = AgentLocalCatalogScope(
        principal_id=provider._absent_author_id,
        agent_id=active_runtime._authenticated_agent_id,
    )
    candidate = learned.prepare_candidate(OntologyChangeProposal.create(
        catalog_scope=scope, parent_catalog_digest="a" * 64,
        relation=RelationDeclaration(description="A person mentors another person."),
        evidence=(OntologyEvidenceReference(
            source_id="activation:evidence", source_digest="1" * 64,
            origin_lineage_digest="2" * 64, source_scope_digest="3" * 64,
        ),),
    ))
    candidate = learned.record_evaluation(
        proposal_id=candidate.proposal_id,
        evaluation=PairedEvaluation.create(
            binding_digest="4" * 64, targeted_positive_count=2,
            targeted_positive_committed_and_read=2, parent_regressions=0,
            unsupported_or_misleading_failures=0, scope_or_provenance_failures=0,
            available=True,
        ),
    )
    learned.approve_candidate(
        proposal_id=candidate.proposal_id,
        principal_id=scope.principal_id, agent_id=scope.agent_id,
    )
    provider.activate_learned_candidate(candidate.proposal_id)
    sentence = "Atlas mentors Ada."
    provider.on_turn_start(1, sentence)
    arguments = {
        "schema_version": 1,
        "source_quote": sentence,
        "source_quote_start": 0,
        "subject_quote": "Atlas",
        "predicate_anchor_quote": "mentors",
        "object_quote": "Ada",
        "proposal": {
            "abstained": False,
                "mentions": [
                    {"local_id": "atlas", "mention_quote": "Atlas", "mention_context_quote": sentence, "proposed_type": "Person"},
                    {"local_id": "ada", "mention_quote": "Ada", "mention_context_quote": sentence, "proposed_type": "Person"},
            ],
                "facts": [{
                    "kind": "fact", "local_id": "mentors", "predicate_id": "mentors",
                "subject_entity_ref": "atlas", "object": {"kind": "entity", "entity_ref": "ada"},
                "assertion_quote": sentence, "predicate_anchor_quote": "mentors",
                "polarity": "positive", "commitment": "asserted", "attributed_to_entity_ref": None,
                "temporal_qualifier_quotes": [],
            }],
            "corrections": [], "retractions": [], "action_states": [], "identity_operations": [],
        },
    }
    service = provider._provider._service
    runtime = provider._completed_turn_runtime
    active = runtime._active_turn
    assert active is not None
    # Exercise the generic public root directly with a real captured source,
    # valid factory authority and no pin reference.  Submission must deny
    # before retained-operation allocation; only schema egress may create a pin.
    missing_pin = service.submit_structured_fact(
        runtime._structured_tool_request(active=active, arguments=arguments, mentors=True),
        authenticated_host_ingress=runtime._issue_host_ingress(
            active.session_id, runtime._authenticated_author_id, datetime.now(UTC),
        ),
    )
    assert missing_pin.status == "denied"
    assert missing_pin.denial_reason == "retained_source_denied"
    # A captured callback cannot use submission to create its own pre-egress
    # pin.  It leaves no retained structured operation or semantic effect.
    assert provider.handle_tool_call("memorii_submit_fact", arguments) == {
        "status": "unavailable"
    }
    records_before_schema = tuple(service._memory_plane.list_records())
    assert not any(
        record.source_kind == "semantic_ingestion_catalog_capture_pin"
        for record in records_before_schema
    )
    assert not any(
        record.source_kind == "semantic_ingestion_retained_source_operation"
        for record in records_before_schema
    )
    assert not any(
        record.source_kind == "semantic_ingestion_retained_structured_submission"
        for record in records_before_schema
    )
    assert not any(
        record.source_kind == "semantic_ingestion_preplanning_control"
        for record in records_before_schema
    )
    assert not any(
        record.content.get("runtime_context_projection_kind")
        == "bootstrap_v3_claim_assertion"
        for record in records_before_schema
    )
    # The schema call is the pre-tool egress boundary: it persists and
    # verifies the captured-turn catalog witness consumed below.
    schema_names = [item["function"]["name"] for item in provider.get_tool_schemas()]
    assert schema_names[:2] == ["memorii_submit_fact", "memorii_read_fact"]
    assert set(schema_names[2:]) == {
        "memorii_create_preference_candidate", "memorii_confirm_preference",
        "memorii_close_preference", "memorii_read_preference",
        "memorii_set_preference_delegation",
    }
    assert service.load_captured_turn_catalog_pin(
        ledger=active.ledger,
        authority_request=runtime._structured_authority_request,
        authenticated_host_ingress=runtime._issue_host_ingress(
            active.session_id, runtime._authenticated_author_id, datetime.now(UTC),
        ),
    ) is not None
    def stage(note: str) -> None:
        print(f"installed-bridge stage={note} at={datetime.now(UTC).isoformat()}", flush=True)

    stage("captured")
    result = provider.handle_tool_call("memorii_submit_fact", arguments)
    stage("native-commit-returned")

    # The installed bridge reaches a committed native fact without model
    # transport through the captured retained-source path.
    assert result["status"] == "committed"
    assert isinstance(result.get("operation_id"), str)
    assert result["operation_id"].startswith("retained-source:v1:")
    records = tuple(service._memory_plane.list_records())
    assert sum(
        record.content.get("runtime_context_projection_kind")
        == "bootstrap_v3_claim_assertion"
        for record in records
    ) == 1
    assert sum(
        record.source_kind == "semantic_ingestion_structured_claim_catalog_binding"
        for record in records
    ) == 1
    pin_record = next(
        record for record in records
        if record.source_kind == "semantic_ingestion_catalog_capture_pin"
    )
    binding_record = next(
        record for record in records
        if record.source_kind == "semantic_ingestion_structured_claim_catalog_binding"
    )
    pin = pin_record.content["catalog_capture_pin"]
    binding = binding_record.content["binding"]
    assert binding["schema_version"] == 2
    assert {
        key: binding[key]
        for key in (
            "capture_id", "pin_memory_id", "pin_digest", "catalog_scope",
            "catalog_digest", "selected_version_id", "selected_version_digest",
            "runtime_bundle_digest",
        )
    } == {
        "capture_id": pin["capture_id"],
        "pin_memory_id": pin_record.memory_id,
        "pin_digest": pin["pin_digest"],
        "catalog_scope": pin["catalog_scope"],
        "catalog_digest": pin["catalog_digest"],
        "selected_version_id": pin["selected_version_id"],
        "selected_version_digest": pin["selected_version_digest"],
        "runtime_bundle_digest": pin["runtime_bundle_digest"],
    }
    projection = next(
        record for record in records
        if record.content.get("runtime_context_projection_kind") == "bootstrap_v3_claim_assertion"
    )
    subject_entity_id = projection.content["claim_identity"]["subject_assertion_ref"][
        "logical_entity_id_at_assertion"
    ]
    protected_read = provider.handle_tool_call(
        "memorii_read_fact",
        {"predicate_id": "mentors", "subject_entity_id": subject_entity_id, "view": "current"},
    )
    assert protected_read["status"] == "ok"
    assert len(protected_read["items"]) == 1
    from memorii.core.semantic_ingestion.catalog_authority import (
        AuthenticatedPrincipalAgent,
        CatalogAuthorityError,
    )
    from memorii.core.semantic_ingestion.catalog_capture_pin import PackageIndexedCatalogBundleLocator
    from memorii.core.semantic_ingestion.structured_fact_read import StructuredFactReadRequest

    with pytest.raises(CatalogAuthorityError):
        PackageIndexedCatalogBundleLocator().locate_selected(
            records,
            scope=scope,
            authenticated=AuthenticatedPrincipalAgent(
                principal_id=scope.principal_id, agent_id="memorii:other-agent",
            ),
        )
    assert runtime.read_structured_facts(
        request=StructuredFactReadRequest(
            predicate_id="mentors", subject_entity_id=subject_entity_id,
        ),
        session_id=active.session_id,
        authenticated_author_id="memorii:other-principal",
        now=datetime.now(UTC),
    ).status == "denied"
    stage("durable-record-counts-verified")
    first_prefetch = provider.prefetch("Atlas")
    assert "Atlas" in first_prefetch and "Ada" in first_prefetch
    stage("first-protected-prefetch-verified")
    first_status = provider.lookup_structured_fact_status(result["operation_id"])
    assert first_status == result
    stage("first-status-verified")
    provider.shutdown()
    stage("first-runtime-shutdown")

    reopened = bridge_module.MemoriiHermesMemoryProvider()
    reopened.initialize(
        "session:one", hermes_home=tmp_path, user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes",
    )
    stage("jsonl-runtime-reopened")
    retry = reopened.lookup_structured_fact_status(result["operation_id"])
    assert retry == result
    assert reopened.lookup_structured_fact_status(result["operation_id"]) == retry
    stage("reopened-status-retry-verified")
    reopened_prefetch = reopened.prefetch("Atlas")
    assert reopened_prefetch == first_prefetch
    stage("reopened-protected-prefetch-verified")
    reopened.shutdown()


def test_installed_no_key_paired_evaluator_executes_all_cases_without_control_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The installed isolated evaluator reaches writer and protected-reader roots."""
    from memorii.core.semantic_ingestion.learned_relation import (
        AgentLocalCatalogScope,
        FrozenMentorsPairedEvaluator,
        IsolatedMentorsEvaluationExecutor,
        OntologyChangeProposal,
        OntologyEvidenceReference,
        RelationDeclaration,
    )
    from memorii.integrations.hermes_factory import (
        _isolated_mentors_evaluation_cases,
        build_local_level2_runtime_binding,
    )
    from memorii.integrations.hermes_local_authority import (
        authorize_local_level2,
        authorize_local_structured_tool,
    )

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    def network_forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("paired evaluator attempted network access")

    monkeypatch.setattr(socket, "getaddrinfo", network_forbidden)
    monkeypatch.setattr(socket, "create_connection", network_forbidden)
    monkeypatch.setattr(socket.socket, "connect", network_forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", network_forbidden)
    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    context = SimpleNamespace(
        storage_root=tmp_path / "production", hermes_home=tmp_path,
        session_id="session:evaluator", user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes", parent_session_id=None,
    )
    binding = build_local_level2_runtime_binding(context)
    runtime = binding.completed_turn_runtime
    assert runtime is not None
    proposal = OntologyChangeProposal.create(
        catalog_scope=AgentLocalCatalogScope(
            principal_id=binding.absent_author_id,
            agent_id=runtime._authenticated_agent_id,
        ),
        parent_catalog_digest="a" * 64,
        relation=RelationDeclaration(description="A person mentors another person."),
        evidence=(OntologyEvidenceReference(
            source_id="evaluator:evidence", source_digest="1" * 64,
            origin_lineage_digest="2" * 64, source_scope_digest="3" * 64,
        ),),
    )
    executor = IsolatedMentorsEvaluationExecutor(
        run_isolated_cases=lambda proposal, cases, binding_digest, corpus_digest, budget_digest: (
            _isolated_mentors_evaluation_cases(
                proposal, cases, binding_digest, corpus_digest, budget_digest, context,
            )
        ),
    )
    evaluator = FrozenMentorsPairedEvaluator(executor)
    try:
        evaluation = evaluator.evaluate(proposal)
        assert evaluation.available and evaluation.passes, [
            (item.case_id, item.parent_status, item.candidate_status, item.candidate_read_status)
            for item in evaluation.case_outcomes
        ]
        assert [item.case_id for item in evaluation.case_outcomes] == [
            "direct-positive-ada", "direct-positive-cora", "quoted-claim",
            "hypothetical", "ambiguous-role", "correction", "scope-provenance-veto",
            "parent-regression",
        ]
        assert all(
            item.candidate_status == "committed" and item.candidate_read_status == "read"
            for item in evaluation.case_outcomes[:2]
        )
        assert all(
            item.candidate_status in {"abstained", "denied"}
            for item in evaluation.case_outcomes[2:7]
        )
        parent_control = evaluation.case_outcomes[7]
        assert parent_control.parent_status == "read"
        assert parent_control.candidate_status == "committed"
        assert parent_control.candidate_read_status == "read"
        assert all(
            item.parent_status in {"abstained", "denied", "unavailable"}
            for item in evaluation.case_outcomes[:7]
        )
        assert binding.learned_ontology_status() == {
            "active_catalog_digest": None, "active_version_digest": None,
            "activation_sequence": None, "candidate_count": 0,
            "candidate_ids": (),
            "replay_outcomes": {}, "last_error": None,
        }
    finally:
        runtime.close()


def test_learned_replay_of_a_preselection_capture_reopens_jsonl(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The replay control must retain the binding selected for the replay."""
    from memorii.core.semantic_ingestion.learned_relation import (
        AgentLocalCatalogScope,
        OntologyChangeProposal,
        OntologyEvidenceReference,
        PairedEvaluation,
        RelationDeclaration,
    )
    from memorii.core.semantic_ingestion.structured_fact_read import StructuredFactReadRequest
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import (
        authorize_local_level2,
        authorize_local_structured_tool,
    )

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider.initialize(
        "session:replay", hermes_home=tmp_path, user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes",
    )
    provider.on_turn_start(1, "Atlas mentors Ada.")
    runtime = provider._completed_turn_runtime
    learned = provider._learned_ontology_runtime
    assert runtime is not None and learned is not None
    active = runtime._active_turn
    assert active is not None
    scope = AgentLocalCatalogScope(
        principal_id=provider._absent_author_id,
        agent_id=runtime._authenticated_agent_id,
    )
    candidate = learned.prepare_candidate(OntologyChangeProposal.create(
        catalog_scope=scope, parent_catalog_digest="a" * 64,
        relation=RelationDeclaration(description="A person mentors another person."),
        evidence=(OntologyEvidenceReference(
            source_id=active.ledger.source_id, source_digest=active.ledger.source_digest,
            origin_lineage_digest="2" * 64, source_scope_digest="3" * 64,
        ),),
    ))
    candidate = learned.record_evaluation(
        proposal_id=candidate.proposal_id,
        evaluation=PairedEvaluation.create(
            binding_digest="4" * 64, targeted_positive_count=2,
            targeted_positive_committed_and_read=2, parent_regressions=0,
            unsupported_or_misleading_failures=0, scope_or_provenance_failures=0,
            available=True,
        ),
    )
    learned.approve_candidate(
        proposal_id=candidate.proposal_id,
        principal_id=scope.principal_id, agent_id=scope.agent_id,
    )
    first_activation = provider.activate_learned_candidate(candidate.proposal_id)
    status = provider.lookup_learned_ontology_status()
    assert status["replay_outcomes"] == {"committed": 1}
    records = tuple(provider._provider._service._memory_plane.list_records())
    claims = tuple(
        record for record in records
        if record.content.get("runtime_context_projection_kind")
        == "bootstrap_v3_claim_assertion"
    )
    receipts = tuple(
        record for record in records
        if record.source_kind == "learned_ontology_replay_operation_v1"
    )
    assert len(claims) == 1
    assert len(receipts) == 1
    subject_entity_id = claims[0].content["claim_identity"]["subject_assertion_ref"][
        "logical_entity_id_at_assertion"
    ]
    first_read = runtime.read_structured_facts(
        request=StructuredFactReadRequest(
            predicate_id="mentors", subject_entity_id=subject_entity_id,
        ),
        session_id="session:replay",
        authenticated_author_id=scope.principal_id,
        now=datetime.now(UTC),
    )
    assert first_read.status == "ok"
    assert len(first_read.items) == 1
    # Select a later generation through the same public candidate lifecycle,
    # then roll back through the installed owner root. Rollback moves only the
    # pointer; the first fact keeps its original pinned catalog authority.
    successor = learned.prepare_candidate(OntologyChangeProposal.create(
        catalog_scope=scope,
        parent_catalog_digest=first_activation.target_version_digest,
        relation=RelationDeclaration(description="A person mentors another person."),
        evidence=(OntologyEvidenceReference(
            source_id=active.ledger.source_id,
            source_digest=active.ledger.source_digest,
            origin_lineage_digest="5" * 64,
            source_scope_digest="6" * 64,
        ),),
    ))
    successor = learned.record_evaluation(
        proposal_id=successor.proposal_id,
        evaluation=PairedEvaluation.create(
            binding_digest="4" * 64,
            targeted_positive_count=2,
            targeted_positive_committed_and_read=2,
            parent_regressions=0,
            unsupported_or_misleading_failures=0,
            scope_or_provenance_failures=0,
            available=True,
        ),
    )
    provider.approve_learned_candidate(successor.proposal_id)
    successor_activation = provider.activate_learned_candidate(successor.proposal_id)
    assert successor_activation.status == "selected"
    before_rollback = provider.lookup_learned_ontology_status()
    assert before_rollback["active_version_digest"] == successor_activation.target_version_digest
    assert before_rollback["candidate_count"] == 2
    rollback = provider.select_prior_learned_version(first_activation.target_version_digest)
    assert rollback.status == "selected"
    after_rollback = provider.lookup_learned_ontology_status()
    assert after_rollback["active_version_digest"] == first_activation.target_version_digest
    assert after_rollback["candidate_count"] == before_rollback["candidate_count"]
    assert runtime.read_structured_facts(
        request=StructuredFactReadRequest(
            predicate_id="mentors", subject_entity_id=subject_entity_id,
        ),
        session_id="session:replay",
        authenticated_author_id=scope.principal_id,
        now=datetime.now(UTC),
    ) == first_read
    provider.shutdown()

    reopened = bridge_module.MemoriiHermesMemoryProvider()
    reopened.initialize(
        "session:replay", hermes_home=tmp_path, user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes",
    )
    assert (
        reopened.lookup_learned_ontology_status()["replay_outcomes"]
        == after_rollback["replay_outcomes"]
        == {"committed": 1, "revoked": 1}
    )
    reopened_records = tuple(reopened._provider._service._memory_plane.list_records())
    reopened_claims = tuple(
        record for record in reopened_records
        if record.content.get("runtime_context_projection_kind")
        == "bootstrap_v3_claim_assertion"
    )
    reopened_receipts = tuple(
        record for record in reopened_records
        if record.source_kind == "learned_ontology_replay_operation_v1"
    )
    assert len(reopened_claims) == 1
    assert len(reopened_receipts) == 2
    reopened_subject_entity_id = reopened_claims[0].content["claim_identity"]["subject_assertion_ref"][
        "logical_entity_id_at_assertion"
    ]
    reopened_runtime = reopened._completed_turn_runtime
    assert reopened_runtime is not None
    reopened_read = reopened_runtime.read_structured_facts(
        request=StructuredFactReadRequest(
            predicate_id="mentors", subject_entity_id=reopened_subject_entity_id,
        ),
        session_id="session:replay",
        authenticated_author_id=scope.principal_id,
        now=datetime.now(UTC),
    )
    assert reopened_read == first_read
    reopened.shutdown()


@pytest.mark.parametrize("outcome", ["deleted", "revoked"])
def test_installed_learned_replay_skip_receipt_is_durable_and_idempotent(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str,
) -> None:
    """The factory root records unavailable retained replay without a fact."""
    from memorii.core.semantic_ingestion.learned_relation import (
        AgentLocalCatalogScope,
        OntologyChangeProposal,
        OntologyEvidenceReference,
        PairedEvaluation,
        RelationDeclaration,
    )
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import (
        authorize_local_level2,
        authorize_local_structured_tool,
    )

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider.initialize(
        "session:skipped", hermes_home=tmp_path, user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes",
    )
    try:
        runtime = provider._completed_turn_runtime
        learned = provider._learned_ontology_runtime
        assert runtime is not None and learned is not None
        scope = AgentLocalCatalogScope(
            principal_id=provider._absent_author_id,
            agent_id=runtime._authenticated_agent_id,
        )
        if outcome == "deleted":
            source_id, source_digest = "retained:missing", "1" * 64
        else:
            provider.on_turn_start(1, "Atlas mentors Ada.")
            active = runtime._active_turn
            assert active is not None
            source_id, source_digest = active.ledger.source_id, active.ledger.source_digest
            # This is the installed runtime's current-authority revocation
            # boundary.  The ordinary replay root sees it before source/pin
            # or semantic submission and must leave no fact behind.
            runtime._structured_tool_is_current = lambda: False
        candidate = learned.prepare_candidate(OntologyChangeProposal.create(
            catalog_scope=scope, parent_catalog_digest="a" * 64,
            relation=RelationDeclaration(description="A person mentors another person."),
            evidence=(OntologyEvidenceReference(
                source_id=source_id, source_digest=source_digest,
                origin_lineage_digest="2" * 64, source_scope_digest="3" * 64,
            ),),
        ))
        candidate = learned.record_evaluation(
            proposal_id=candidate.proposal_id,
            evaluation=PairedEvaluation.create(
                binding_digest="4" * 64, targeted_positive_count=2,
                targeted_positive_committed_and_read=2, parent_regressions=0,
                unsupported_or_misleading_failures=0, scope_or_provenance_failures=0,
                available=True,
            ),
        )
        learned.approve_candidate(
            proposal_id=candidate.proposal_id,
            principal_id=scope.principal_id, agent_id=scope.agent_id,
        )
        provider.activate_learned_candidate(candidate.proposal_id)

        status = provider.lookup_learned_ontology_status()
        assert status["active_version_digest"] is not None
        assert status["activation_sequence"] == 1
        assert status["candidate_count"] == 1
        assert status["replay_outcomes"] == {outcome: 1}
        assert status["last_error"] == f"replay_{outcome}"
        assert source_id not in repr(status)
        assert source_digest not in repr(status)
        records = tuple(provider._provider._service._memory_plane.list_records())
        assert sum(record.source_kind == "learned_ontology_replay_operation_v1" for record in records) == 1
        assert not any(
            record.content.get("runtime_context_projection_kind") == "bootstrap_v3_claim_assertion"
            for record in records
        )
        learned.recover(scope)
        assert len(learned._plane.list_records(source_kind="learned_ontology_replay_operation_v1")) == 1
    finally:
        provider.shutdown()

    reopened = bridge_module.MemoriiHermesMemoryProvider()
    reopened.initialize(
        "session:skipped", hermes_home=tmp_path, user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes",
    )
    try:
        assert reopened.lookup_learned_ontology_status()["replay_outcomes"] == {outcome: 1}
        reopened_records = tuple(reopened._provider._service._memory_plane.list_records())
        assert sum(record.source_kind == "learned_ontology_replay_operation_v1" for record in reopened_records) == 1
        assert not any(
            record.content.get("runtime_context_projection_kind") == "bootstrap_v3_claim_assertion"
            for record in reopened_records
        )
    finally:
        reopened.shutdown()


def test_installed_default_catalog_entity_relation_commits_and_recalls(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise selected default dispatch through the installed Hermes root."""
    from memorii.core.semantic_ingestion.openai_responses_project_assertions import OpenAIResponsesApiClient
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import (
        authorize_local_level2,
        authorize_local_structured_tool,
    )

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        OpenAIResponsesApiClient,
        "complete",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("model transport must not run")),
    )
    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider.initialize(
        "session:default", hermes_home=tmp_path, user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes",
    )
    row = next(
        row for row in load_default_catalog_acceptance_corpus().rows
        if row.relation_id == "project_owned_by"
    )
    fixture = build_default_catalog_proposal(row)
    sentence = fixture.source
    subject_quote = fixture.subject_quote
    object_quote = fixture.object_quote
    predicate_anchor_quote = fixture.predicate_anchor_quote
    assert fixture.object is not None
    subject_type = fixture.subject.proposed_type
    object_type = fixture.object.proposed_type
    provider.on_turn_start(1, sentence)
    schemas = provider.get_tool_schemas()
    predicate_ids = schemas[0]["function"]["parameters"]["properties"]["proposal"]["properties"]["facts"]["items"]["properties"]["predicate_id"]["enum"]
    assert "reports_to" in predicate_ids
    arguments = fixture.tool_arguments()
    result = provider.handle_tool_call("memorii_submit_fact", arguments)
    assert result["status"] == "committed"
    records = tuple(provider._provider._service._memory_plane.list_records())
    assert any(
        record.content.get("runtime_context_projection_kind") == "bootstrap_v3_claim_assertion"
        for record in records
    )
    binding = next(
        record.content["binding"] for record in records
        if record.source_kind == "semantic_ingestion_structured_claim_catalog_binding"
    )
    assert binding["schema_version"] == 2
    assert binding["selected_version_id"] == "default-catalog-v1"
    projection = next(
        record for record in records
        if record.content.get("runtime_context_projection_kind") == "bootstrap_v3_claim_assertion"
    )
    subject_entity_id = projection.content["claim_identity"]["subject_assertion_ref"][
        "logical_entity_id_at_assertion"
    ]
    direct_read = provider.handle_tool_call(
        "memorii_read_fact",
        {"predicate_id": "project_owned_by", "subject_entity_id": subject_entity_id, "view": "current"},
    )
    assert direct_read["status"] == "ok"
    before_correction = datetime.now(UTC).isoformat()
    provider.sync_turn(
        sentence,
        "Recorded.",
        messages=[
            {"role": "user", "content": sentence, "timestamp": before_correction},
            {"role": "assistant", "content": "Recorded.", "timestamp": before_correction},
        ],
    )
    replacement_object_quote = "Group replacement"
    # The prepared span begins after the sentence boundary and retains its
    # leading space. Keep that exact byte shape in the replacement grounding.
    replacement_source = (
        f" Correction: {subject_quote} {predicate_anchor_quote} {replacement_object_quote}."
    )
    replacement_sentence = sentence + replacement_source
    provider.on_turn_start(2, replacement_sentence)
    assert provider.get_tool_schemas()[0]["function"]["name"] == "memorii_submit_fact"
    correction = {
        "schema_version": 1,
        "correction": {
            "assertion_quote": replacement_source,
            "correction_anchor_quote": "Correction",
            "corrected": {
                "source_quote": sentence, "subject_quote": subject_quote,
                "predicate_anchor_quote": predicate_anchor_quote, "object_quote": object_quote,
            },
            "replacement": {
                "source_quote": replacement_source, "subject_quote": subject_quote,
                "predicate_anchor_quote": predicate_anchor_quote, "object_quote": replacement_object_quote,
            },
        },
        "proposal": {
            "abstained": False,
            "mentions": [
                {"local_id": "old_subject", "mention_quote": subject_quote, "mention_context_quote": sentence, "proposed_type": subject_type},
                {"local_id": "old_object", "mention_quote": object_quote, "mention_context_quote": sentence, "proposed_type": object_type},
                {"local_id": "new_subject", "mention_quote": subject_quote, "mention_context_quote": replacement_source, "proposed_type": subject_type},
                {"local_id": "new_object", "mention_quote": replacement_object_quote, "mention_context_quote": replacement_source, "proposed_type": object_type},
            ],
            "facts": [],
            "corrections": [{
                "kind": "correction", "local_id": "correction",
                "corrected_fact": {
                    "kind": "fact", "local_id": "old", "predicate_id": "project_owned_by",
                    "subject_entity_ref": "old_subject", "object": {"kind": "entity", "entity_ref": "old_object"},
                    "assertion_quote": sentence, "predicate_anchor_quote": predicate_anchor_quote,
                    "polarity": "positive", "commitment": "asserted", "attributed_to_entity_ref": None,
                    "temporal_qualifier_quotes": [],
                },
                "replacement_fact": {
                    "kind": "fact", "local_id": "new", "predicate_id": "project_owned_by",
                    "subject_entity_ref": "new_subject", "object": {"kind": "entity", "entity_ref": "new_object"},
                    "assertion_quote": replacement_source, "predicate_anchor_quote": predicate_anchor_quote,
                    "polarity": "positive", "commitment": "asserted", "attributed_to_entity_ref": None,
                    "temporal_qualifier_quotes": [],
                },
                "assertion_quote": replacement_source, "correction_anchor_quote": "Correction",
            }],
            "retractions": [], "action_states": [], "identity_operations": [],
        },
    }
    corrected = provider.handle_tool_call("memorii_submit_fact", correction)
    assert corrected["status"] == "committed"
    current = provider.handle_tool_call(
        "memorii_read_fact",
        {"predicate_id": "project_owned_by", "subject_entity_id": subject_entity_id, "view": "current"},
    )
    assert current["status"] == "ok"
    assert len(current["items"]) == 1
    assert current["items"][0]["object_value"] != direct_read["items"][0]["object_value"]
    history = provider.handle_tool_call(
        "memorii_read_fact",
        {"predicate_id": "project_owned_by", "subject_entity_id": subject_entity_id, "view": "history"},
    )
    assert history["status"] == "ok"
    assert sorted(item["lifecycle_state"] for item in history["items"]) == ["active", "superseded"]
    historical_as_of = provider.handle_tool_call(
        "memorii_read_fact",
        {"predicate_id": "project_owned_by", "subject_entity_id": subject_entity_id, "view": "history", "system_as_of": before_correction},
    )
    assert historical_as_of["status"] == "ok"
    assert len(historical_as_of["items"]) == 1
    assert historical_as_of["items"][0]["object_value"] == direct_read["items"][0]["object_value"]
    assert historical_as_of["items"][0]["lifecycle_state"] == "active"
    recalled = provider.prefetch(f"Who owns {subject_quote}?")
    provider.shutdown()
    assert replacement_object_quote in recalled

    reopened = bridge_module.MemoriiHermesMemoryProvider()
    reopened.initialize(
        "session:default", hermes_home=tmp_path, user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes",
    )
    reopened.on_turn_start(3, f"Recall who owns {subject_quote}.")
    assert reopened.get_tool_schemas()[1]["function"]["name"] == "memorii_read_fact"
    reopened_current = reopened.handle_tool_call(
        "memorii_read_fact",
        {"predicate_id": "project_owned_by", "subject_entity_id": subject_entity_id, "view": "current"},
    )
    reopened_history = reopened.handle_tool_call(
        "memorii_read_fact",
        {"predicate_id": "project_owned_by", "subject_entity_id": subject_entity_id, "view": "history"},
    )
    reopened_as_of = reopened.handle_tool_call(
        "memorii_read_fact",
        {"predicate_id": "project_owned_by", "subject_entity_id": subject_entity_id,
         "view": "history", "system_as_of": before_correction},
    )
    assert reopened_current == current
    assert reopened_history == history
    assert reopened_as_of == historical_as_of
    assert replacement_object_quote in reopened.prefetch(f"Who owns {subject_quote}?")
    reopened.shutdown()


def test_installed_default_catalog_money_relation_commits_reads_and_revokes(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the private Money row through the installed no-key tool root."""
    from memorii.core.semantic_ingestion.openai_responses_project_assertions import (
        OpenAIResponsesApiClient,
    )
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import (
        authorize_local_level2,
        authorize_local_structured_tool,
    )

    rows = {row.relation_id: row for row in load_default_catalog_acceptance_corpus().rows}
    fixture = build_default_catalog_proposal(rows["obligation_amount"])
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        OpenAIResponsesApiClient,
        "complete",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network")),
    )
    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider.initialize(
        "session:money", hermes_home=tmp_path, user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes",
    )
    try:
        provider.on_turn_start(1, fixture.source)
        schemas = provider.get_tool_schemas()
        predicate_ids = (
            schemas[0]["function"]["parameters"]["properties"]["proposal"]
            ["properties"]["facts"]["items"]["properties"]["predicate_id"]["enum"]
        )
        assert "obligation_amount" in predicate_ids
        result = provider.handle_tool_call("memorii_submit_fact", fixture.tool_arguments())
        assert result["status"] == "committed"

        records = tuple(provider._provider._service._memory_plane.list_records())
        bindings = [
            record.content["binding"]
            for record in records
            if record.source_kind == "semantic_ingestion_structured_claim_catalog_binding"
        ]
        assert len(bindings) == 1
        assert bindings[0]["schema_version"] == 2
        assert bindings[0]["selected_version_id"] == "default-catalog-v1"
        assert fixture.object_quote in provider.prefetch(fixture.subject_quote)

        before_bindings = len(bindings)
        before_projections = sum(
            record.content.get("runtime_context_projection_kind")
            == "bootstrap_v3_claim_assertion"
            for record in records
        )
        rejected = provider.handle_tool_call(
            "memorii_submit_fact", fixture.misleading_tool_arguments()
        )
        assert rejected["status"] in {"rejected", "unavailable"}
        after = tuple(provider._provider._service._memory_plane.list_records())
        assert sum(
            record.source_kind == "semantic_ingestion_structured_claim_catalog_binding"
            for record in after
        ) == before_bindings
        assert sum(
            record.content.get("runtime_context_projection_kind")
            == "bootstrap_v3_claim_assertion"
            for record in after
        ) == before_projections

        provider.revoke_structured_grant("fact")
        assert provider.prefetch(fixture.subject_quote) == ""
        assert not any(
            outcome.retryable
            for outcome in provider._provider._service.reconcile_memory_evolution()
        )
    finally:
        provider.shutdown()


def test_installed_default_catalog_literal_retraction_and_symmetric_reads_survive_reopen(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove the remaining shared M3 lifecycle and symmetric read mechanics."""
    from memorii.core.semantic_ingestion.openai_responses_project_assertions import (
        OpenAIResponsesApiClient,
    )
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import (
        authorize_local_level2,
        authorize_local_structured_tool,
    )

    rows = {row.relation_id: row for row in load_default_catalog_acceptance_corpus().rows}
    due = build_default_catalog_proposal(rows["work_item_due_on"])
    symmetric = tuple(
        build_default_catalog_proposal(rows[relation_id])
        for relation_id in ("partner_of", "sibling_of")
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        OpenAIResponsesApiClient,
        "complete",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("model transport must not run")),
    )
    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider.initialize(
        "session:lifecycle-shared", hermes_home=tmp_path, user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes",
    )
    transcript: list[dict[str, object]] = []

    def complete_turn(source: str) -> None:
        timestamp = datetime.now(UTC).isoformat()
        transcript.extend((
            {"role": "user", "content": source, "timestamp": timestamp},
            {"role": "assistant", "content": "Recorded.", "timestamp": timestamp},
        ))
        provider.sync_turn(
            user_content=source,
            assistant_content="Recorded.",
            messages=transcript,
        )
        provider.prefetch(source)

    provider.on_turn_start(1, due.source)
    assert provider.get_tool_schemas()[0]["function"]["name"] == "memorii_submit_fact"
    assert provider.handle_tool_call("memorii_submit_fact", due.tool_arguments())["status"] == "committed"
    initial_records = tuple(provider._provider._service._memory_plane.list_records())
    initial_projection = next(
        record for record in initial_records
        if record.content.get("runtime_context_projection_kind") == "bootstrap_v3_claim_assertion"
        and record.content["claim_identity"]["assertion_key_at_recording"]["slot"]["predicate_id"]
        == "work_item_due_on"
    )
    due_subject_id = initial_projection.content["claim_identity"]["subject_assertion_ref"][
        "logical_entity_id_at_assertion"
    ]
    initial_due = provider.handle_tool_call(
        "memorii_read_fact",
        {"predicate_id": "work_item_due_on", "subject_entity_id": due_subject_id, "view": "current"},
    )
    assert initial_due["status"] == "ok"
    before_correction = datetime.now(UTC).isoformat()
    complete_turn(due.source)

    replacement_quote = "2027-10-03"
    replacement_value = '{"source_calendar":"gregorian","value":"2027-10-03"}'
    replacement_source = (
        f" Correction: {due.subject_quote} {due.predicate_anchor_quote} {replacement_quote}."
    )
    correction_source = due.source + replacement_source
    old_subject = due.subject.model_copy(update={"local_id": "old_subject"})
    new_subject = due.subject.model_copy(update={
        "local_id": "new_subject", "mention_context_quote": replacement_source,
    })
    corrected_fact = due.fact.model_copy(update={
        "local_id": "old", "subject_entity_ref": old_subject.local_id,
    })
    replacement_fact = due.fact.model_copy(update={
        "local_id": "new", "subject_entity_ref": new_subject.local_id,
        "assertion_quote": replacement_source,
        "object": due.fact.object.model_copy(update={"canonical_value": replacement_value}),
    })
    correction_arguments = {
        "schema_version": 1,
        "correction": {
            "assertion_quote": replacement_source,
            "correction_anchor_quote": "Correction",
            "corrected": {
                "source_quote": due.source, "subject_quote": due.subject_quote,
                "predicate_anchor_quote": due.predicate_anchor_quote, "object_quote": due.object_quote,
            },
            "replacement": {
                "source_quote": replacement_source, "subject_quote": due.subject_quote,
                "predicate_anchor_quote": due.predicate_anchor_quote, "object_quote": replacement_quote,
            },
        },
        "proposal": {
            "abstained": False,
            "mentions": [
                old_subject.model_dump(mode="json"),
                new_subject.model_dump(mode="json"),
            ],
            "facts": [],
            "corrections": [{
                "kind": "correction", "local_id": "correction",
                "corrected_fact": corrected_fact.model_dump(mode="json"),
                "replacement_fact": replacement_fact.model_dump(mode="json"),
                "assertion_quote": replacement_source,
                "correction_anchor_quote": "Correction",
            }],
            "retractions": [], "action_states": [], "identity_operations": [],
        },
    }
    provider.on_turn_start(2, correction_source)
    assert provider.get_tool_schemas()[0]["function"]["name"] == "memorii_submit_fact"
    assert provider.handle_tool_call("memorii_submit_fact", correction_arguments)["status"] == "committed"
    corrected_due = provider.handle_tool_call(
        "memorii_read_fact",
        {"predicate_id": "work_item_due_on", "subject_entity_id": due_subject_id, "view": "current"},
    )
    assert [item["object_value"] for item in corrected_due["items"]] == [replacement_value]
    before_retraction = datetime.now(UTC).isoformat()
    complete_turn(correction_source)

    retracted_subject = new_subject.model_copy(update={"local_id": "subject"})
    retracted_fact = replacement_fact.model_copy(update={
        "local_id": "retracted", "subject_entity_ref": retracted_subject.local_id,
    })
    retraction_arguments = {
        "schema_version": 1,
        "source_quote": replacement_source,
        "subject_quote": due.subject_quote,
        "predicate_anchor_quote": due.predicate_anchor_quote,
        "object_quote": replacement_quote,
        "proposal": {
            "abstained": False,
            "mentions": [retracted_subject.model_dump(mode="json")],
            "facts": [], "corrections": [],
            "retractions": [{
                "kind": "retraction", "local_id": "retraction",
                "retracted_fact": retracted_fact.model_dump(mode="json"),
                "assertion_quote": replacement_source,
                "retraction_anchor_quote": due.predicate_anchor_quote,
            }],
            "action_states": [], "identity_operations": [],
        },
    }
    provider.on_turn_start(3, replacement_source)
    assert provider.get_tool_schemas()[0]["function"]["name"] == "memorii_submit_fact"
    assert provider.handle_tool_call("memorii_submit_fact", retraction_arguments)["status"] == "committed"
    retracted_current = provider.handle_tool_call(
        "memorii_read_fact",
        {"predicate_id": "work_item_due_on", "subject_entity_id": due_subject_id, "view": "current"},
    )
    assert retracted_current == {"status": "ok", "items": []}
    due_history = provider.handle_tool_call(
        "memorii_read_fact",
        {"predicate_id": "work_item_due_on", "subject_entity_id": due_subject_id, "view": "history"},
    )
    assert sorted(item["lifecycle_state"] for item in due_history["items"]) == ["retracted", "superseded"]
    due_before_correction = provider.handle_tool_call(
        "memorii_read_fact",
        {"predicate_id": "work_item_due_on", "subject_entity_id": due_subject_id,
         "view": "history", "system_as_of": before_correction},
    )
    assert [item["object_value"] for item in due_before_correction["items"]] == [
        initial_due["items"][0]["object_value"]
    ]
    due_before_retraction = provider.handle_tool_call(
        "memorii_read_fact",
        {"predicate_id": "work_item_due_on", "subject_entity_id": due_subject_id,
         "view": "history", "system_as_of": before_retraction},
    )
    assert [item["object_value"] for item in due_before_retraction["items"]] == [replacement_value]
    complete_turn(replacement_source)

    symmetric_results: dict[str, tuple[str, dict[str, object]]] = {}
    for ordinal, fixture in enumerate(symmetric, start=4):
        provider.on_turn_start(ordinal, fixture.source)
        assert provider.get_tool_schemas()[0]["function"]["name"] == "memorii_submit_fact"
        assert provider.handle_tool_call("memorii_submit_fact", fixture.tool_arguments())["status"] == "committed"
        records = tuple(provider._provider._service._memory_plane.list_records())
        projection = next(
            record for record in records
            if record.content.get("runtime_context_projection_kind") == "bootstrap_v3_claim_assertion"
            and record.content["claim_identity"]["assertion_key_at_recording"]["slot"]["predicate_id"]
            == fixture.row.relation_id
        )
        identity = projection.content["claim_identity"]
        subject_id = identity["subject_assertion_ref"]["logical_entity_id_at_assertion"]
        object_id = identity["object_assertion_ref"]["logical_entity_id_at_assertion"]
        before_read_count = len(records)
        reverse = provider.handle_tool_call(
            "memorii_read_fact",
            {"predicate_id": fixture.row.relation_id, "subject_entity_id": object_id, "view": "current"},
        )
        assert reverse["status"] == "ok"
        assert [(item["object_value"], item["derived_direction"]) for item in reverse["items"]] == [
            (subject_id, "reverse")
        ]
        assert len(tuple(provider._provider._service._memory_plane.list_records())) == before_read_count
        symmetric_results[fixture.row.relation_id] = (object_id, reverse)
        complete_turn(fixture.source)

    provider.shutdown()
    reopened = bridge_module.MemoriiHermesMemoryProvider()
    reopened.initialize(
        "session:lifecycle-shared", hermes_home=tmp_path, user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes",
    )
    reopened.on_turn_start(6, "Recall lifecycle and family relations.")
    assert reopened.get_tool_schemas()[1]["function"]["name"] == "memorii_read_fact"
    assert reopened.handle_tool_call(
        "memorii_read_fact",
        {"predicate_id": "work_item_due_on", "subject_entity_id": due_subject_id, "view": "current"},
    ) == retracted_current
    assert reopened.handle_tool_call(
        "memorii_read_fact",
        {"predicate_id": "work_item_due_on", "subject_entity_id": due_subject_id, "view": "history"},
    ) == due_history
    for relation_id, (object_id, reverse) in symmetric_results.items():
        assert reopened.handle_tool_call(
            "memorii_read_fact",
            {"predicate_id": relation_id, "subject_entity_id": object_id, "view": "current"},
        ) == reverse
    reopened.shutdown()


_INSTALLED_DEFAULT_CATALOG_ROWS = tuple(
    sorted(load_default_catalog_acceptance_corpus().rows, key=lambda row: row.relation_id)
)


def test_installed_default_catalog_matrix_inventory_matches_normative_corpus() -> None:
    """Keep the opt-in installed matrix locked to the frozen corpus."""
    corpus = load_default_catalog_acceptance_corpus()

    assert tuple(row.relation_id for row in _INSTALLED_DEFAULT_CATALOG_ROWS) == tuple(
        sorted(EXPECTED_DEFAULT_RELATION_IDS)
    )
    assert {
        row.relation_id for row in _INSTALLED_DEFAULT_CATALOG_ROWS
        if row.requires_private_denial
    } == {row.relation_id for row in corpus.rows if row.scope == "P"}


@pytest.mark.default_catalog_installed
@pytest.mark.parametrize(
    "row", _INSTALLED_DEFAULT_CATALOG_ROWS, ids=lambda row: row.relation_id,
)
def test_installed_default_catalog_every_row_commits_recalls_and_denies(
    bridge_module,
    row: DefaultCatalogCorpusRow,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise one canonical default row through an isolated installed root."""
    from time import monotonic

    from memorii.core.semantic_ingestion.openai_responses_project_assertions import (
        OpenAIResponsesApiClient,
    )
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import (
        authorize_local_level2,
        authorize_local_structured_tool,
    )

    fixture = build_default_catalog_proposal(row)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        OpenAIResponsesApiClient,
        "complete",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network")),
    )
    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider.initialize(
        f"session:default-catalog:{row.relation_id}",
        hermes_home=tmp_path,
        user_id="raw:user:one",
        agent_identity="profile:primary",
        platform="cli",
        agent_context="primary",
        agent_workspace="hermes",
    )
    try:
        provider.on_turn_start(1, fixture.source)
        schemas = provider.get_tool_schemas()
        predicate_ids = (
            schemas[0]["function"]["parameters"]["properties"]["proposal"]
            ["properties"]["facts"]["items"]["properties"]["predicate_id"]["enum"]
        )
        assert row.relation_id in predicate_ids

        started = monotonic()
        result = provider.handle_tool_call("memorii_submit_fact", fixture.tool_arguments())
        print(
            f"installed-default-catalog-row={row.relation_id} "
            f"elapsed_seconds={monotonic() - started:.3f}",
            flush=True,
        )
        assert result["status"] == "committed"

        records = tuple(provider._provider._service._memory_plane.list_records())
        bindings = [
            record.content["binding"]
            for record in records
            if record.source_kind == "semantic_ingestion_structured_claim_catalog_binding"
        ]
        assert len(bindings) == 1
        assert bindings[0]["schema_version"] == 2
        assert bindings[0]["selected_version_id"] == "default-catalog-v1"
        assert fixture.object_quote in provider.prefetch(fixture.subject_quote)

        before_bindings = len(bindings)
        before_projections = sum(
            record.content.get("runtime_context_projection_kind")
            == "bootstrap_v3_claim_assertion"
            for record in records
        )
        rejected = provider.handle_tool_call(
            "memorii_submit_fact", fixture.misleading_tool_arguments(),
        )
        assert rejected["status"] in {"rejected", "unavailable"}
        after = tuple(provider._provider._service._memory_plane.list_records())
        assert sum(
            record.source_kind == "semantic_ingestion_structured_claim_catalog_binding"
            for record in after
        ) == before_bindings
        assert sum(
            record.content.get("runtime_context_projection_kind")
            == "bootstrap_v3_claim_assertion"
            for record in after
        ) == before_projections

        if row.requires_private_denial:
            provider.revoke_structured_grant("fact")
            assert provider.prefetch(fixture.subject_quote) == ""

        outcomes = provider._provider._service.reconcile_memory_evolution()
        assert not any(outcome.retryable for outcome in outcomes)
    finally:
        provider.shutdown()


def test_installed_default_catalog_reuses_one_runtime_for_compact_corpus_matrix(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One installed root proves representative corpus mechanics end to end."""
    from time import monotonic

    from memorii.core.semantic_ingestion.openai_responses_project_assertions import (
        OpenAIResponsesApiClient,
    )
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import (
        authorize_local_level2,
        authorize_local_structured_tool,
    )

    rows = {row.relation_id: row for row in load_default_catalog_acceptance_corpus().rows}
    fixtures = tuple(
        build_default_catalog_proposal(rows[relation_id])
        for relation_id in (
            "project_owned_by",      # M, public entity
            "reports_to",            # M, private entity and grant denial
            "decision_supersedes",   # H, public entity
            "event_time",            # C, public TimeInterval
            "work_item_due_on",      # C, public LocalDate
            "work_item_status",      # C, public StatusText
            "obligation_amount",     # C, private Money
        )
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        OpenAIResponsesApiClient,
        "complete",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("network")),
    )
    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider.initialize(
        "session:matrix", hermes_home=tmp_path, user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes",
    )
    transcript: list[dict[str, object]] = []

    def submit(
        *, ordinal: int, fixture: DefaultCatalogProposalFixture, complete: bool = True,
        arguments: dict[str, object] | None = None,
    ) -> dict[str, object]:
        provider.on_turn_start(ordinal, fixture.source)
        predicate_ids = provider.get_tool_schemas()[0]["function"]["parameters"]["properties"]["proposal"]["properties"]["facts"]["items"]["properties"]["predicate_id"]["enum"]
        assert fixture.row.relation_id in predicate_ids
        started = monotonic()
        result = provider.handle_tool_call(
            "memorii_submit_fact",
            fixture.tool_arguments() if arguments is None else arguments,
        )
        print(
            f"default-catalog-row={fixture.row.relation_id} "
            f"elapsed_seconds={monotonic() - started:.3f}",
            flush=True,
        )
        if not complete:
            return result
        transcript.extend((
            {"role": "user", "content": fixture.source},
            {
                "role": "assistant",
                "content": "Recorded.",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        ))
        provider.sync_turn(
            user_content=fixture.source,
            assistant_content="Recorded.",
            messages=transcript,
        )
        # Retrieval is the public drain before opening the next captured turn.
        provider.prefetch(fixture.subject_quote)
        return result

    try:
        results = tuple(
            submit(ordinal=ordinal, fixture=fixture)
            for ordinal, fixture in enumerate(fixtures, start=1)
        )
        assert all(result["status"] == "committed" for result in results)
        records = tuple(provider._provider._service._memory_plane.list_records())
        bindings = [
            record.content["binding"]
            for record in records
            if record.source_kind == "semantic_ingestion_structured_claim_catalog_binding"
        ]
        assert len(bindings) == len(fixtures)
        assert all(
            binding["schema_version"] == 2
            and binding["selected_version_id"] == "default-catalog-v1"
            for binding in bindings
        )
        for fixture in fixtures:
            recalled = provider.prefetch(fixture.subject_quote)
            assert fixture.object_quote in recalled

        before_bindings = len(bindings)
        before_projections = sum(
            record.content.get("runtime_context_projection_kind")
            == "bootstrap_v3_claim_assertion"
            for record in records
        )
        denied = submit(
            ordinal=len(fixtures) + 1,
            fixture=fixtures[0],
            complete=False,
            arguments=fixtures[0].misleading_tool_arguments(),
        )
        assert denied["status"] in {"rejected", "unavailable"}
        after = tuple(provider._provider._service._memory_plane.list_records())
        assert sum(
            record.source_kind == "semantic_ingestion_structured_claim_catalog_binding"
            for record in after
        ) == before_bindings
        assert sum(
            record.content.get("runtime_context_projection_kind")
            == "bootstrap_v3_claim_assertion"
            for record in after
        ) == before_projections

        provider.revoke_structured_grant("fact")
        assert provider.prefetch(fixtures[1].subject_quote) == ""
        outcomes = provider._provider._service.reconcile_memory_evolution()
        print(f"default-catalog-pending-outcomes={outcomes!r}", flush=True)
        assert not any(outcome.retryable for outcome in outcomes)
    finally:
        provider.shutdown()


def _persist_installed_protected_claim(
    *,
    provider: object,
    storage_root: Path,
):
    """Write a narrow persisted read fixture bound to the installed grants.

    The native V3 commit is separately covered above.  These records isolate
    the release race while retaining the factory-issued principal, grants, and
    catalog binding that the bridge uses in production.
    """
    from hashlib import sha256

    from memorii.core.memory_plane import JsonlMemoryPlaneStore
    from memorii.core.memory_plane.models import CanonicalMemoryRecord
    from memorii.core.memory_plane.store import _PersistedBatch
    from memorii.core.semantic_ingestion.catalog_authority import (
        StructuredClaimCatalogBinding,
        ThreePredicateSeedCatalogAuthorityRepository,
    )
    from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility

    runtime = provider._completed_turn_runtime
    read_authority = runtime._structured_fact_read_authority()
    assert read_authority is not None
    claim_id = "claim:installed-release-race"
    claim_digest = sha256(b"installed-release-race-claim").hexdigest()
    projection = CanonicalMemoryRecord(
        memory_id="semantic:installed-release-race",
        domain=MemoryDomain.SEMANTIC,
        text="Atlas project owner is Ada.",
        content={
            "runtime_context_projection_kind": "bootstrap_v3_claim_assertion",
            "claim_assertion_id": claim_id,
            "claim_assertion_record_digest": claim_digest,
        },
        status=CommitStatus.COMMITTED,
        task_id=runtime._project_task_id,
        user_id=runtime._authenticated_author_id,
        agent_id=runtime._authenticated_agent_id,
        source_kind="test_installed_protected_claim",
        visibility=MemoryRecordVisibility.RUNTIME_CONTEXT,
    )
    catalog = ThreePredicateSeedCatalogAuthorityRepository().resolve_base()
    binding = StructuredClaimCatalogBinding(
        schema_version=1,
        claim_assertion_id=claim_id,
        claim_record_digest=claim_digest,
        catalog_scope=catalog.catalog_scope,
        catalog_digest=catalog.catalog_digest,
        fact_scope=read_authority.fact_grant.fact_scope,
        authenticated=read_authority.authenticated,
    )
    binding_record = CanonicalMemoryRecord(
        memory_id="semantic_ingestion:structured-claim-catalog:" + claim_id,
        domain=MemoryDomain.SEMANTIC,
        text="",
        content={"binding": binding.model_dump(mode="json")},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_structured_claim_catalog_binding",
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    # The fixture is deliberately persisted through a second JSONL handle.
    # It models an already committed protected projection and binding without
    # repeating the native commit path, which this regression does not test.
    external_store = JsonlMemoryPlaneStore(storage_root / "memory-plane")
    with external_store._locked(exclusive=True):
        batches, _ = external_store._current_records_unlocked()
        write_revision = batches[-1].revision if batches else 0
        data_revision = batches[-1].data_revision if batches else 0
        external_store._replace_batches([
            *batches,
            _PersistedBatch.create(
                revision=write_revision + 1,
                data_revision=data_revision + 1,
                records=(projection, binding_record),
            ),
        ])
    return external_store, read_authority


def test_installed_bridge_operator_revocation_only_accepts_factory_grant_kinds(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import (
        authorize_local_level2,
        authorize_local_structured_tool,
    )

    unavailable_home = tmp_path / "unavailable"
    authorize_local_level2(hermes_home=unavailable_home)
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    unavailable = bridge_module.MemoriiHermesMemoryProvider()
    unavailable.initialize(
        "session:one", hermes_home=unavailable_home, user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes",
    )
    try:
        with pytest.raises(RuntimeError, match="revocation is unavailable"):
            unavailable.revoke_structured_grant("fact")
    finally:
        unavailable.shutdown()

    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider.initialize(
        "session:one", hermes_home=tmp_path, user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes",
    )
    try:
        with pytest.raises(ValueError, match="grant kind is invalid"):
            provider.revoke_structured_grant("foreign")
        provider.revoke_structured_grant("fact")
        records = provider._provider._service._memory_plane.list_records(
            source_kind="semantic_ingestion_structured_grant_state"
        )
        states = {record.content["state"]["grant_kind"]: record.content["state"] for record in records}
        assert states["fact"]["active"] is False
        assert states["source"]["active"] is True
        assert states["catalog_visibility"]["active"] is True
        provider.revoke_structured_grant("fact")
    finally:
        provider.shutdown()


@pytest.mark.parametrize("grant_kind", ("source", "fact", "catalog_visibility"))
def test_installed_schema_retry_after_pin_denies_each_revoked_grant(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grant_kind: str,
) -> None:
    """An existing pin is historical selection, never a grant authorization."""
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import (
        authorize_local_level2,
        authorize_local_structured_tool,
    )

    home = tmp_path / grant_kind
    authorize_local_level2(hermes_home=home)
    authorize_local_structured_tool(hermes_home=home)
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider.initialize(
        "session:one", hermes_home=home, user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes",
    )
    try:
        provider.on_turn_start(1, "Atlas owner is Ada.")
        assert [item["function"]["name"] for item in provider.get_tool_schemas()] == [
            "memorii_submit_fact", "memorii_read_fact"
        ]
        service = provider._provider._service
        before = len(service._memory_plane.list_records())
        provider.revoke_structured_grant(grant_kind)
        assert provider.get_tool_schemas() == []
        assert len(service._memory_plane.list_records()) == before
    finally:
        provider.shutdown()


def test_verified_operator_action_revokes_before_provisioning_and_blocks_later_startup(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.core.memory_plane import JsonlMemoryPlaneStore, MemoryPlaneService
    from memorii.integrations.hermes_factory import (
        build_local_level2_runtime_binding,
        revoke_local_level2_structured_grant,
    )
    from memorii.integrations.hermes_local_authority import (
        authorize_local_level2,
        authorize_local_structured_tool,
    )

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    context = bridge_module.HermesProviderServiceContext(
        storage_root=tmp_path / "memorii",
        hermes_home=tmp_path,
        session_id="session:operator-revoke",
        user_id="raw:user:one",
        agent_identity="profile:primary",
        platform="cli",
        agent_context="primary",
        agent_workspace="hermes",
        parent_session_id=None,
    )

    revoke_local_level2_structured_grant(context=context, grant_kind="fact")

    records = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(tmp_path / "memorii" / "memory-plane")
    ).list_records(source_kind="semantic_ingestion_structured_grant_state")
    assert len(records) == 1
    assert records[0].content["state"]["grant_kind"] == "fact"
    assert records[0].content["state"]["active"] is False
    with pytest.raises(StructuredSubmissionGrantRevokedError, match="revoked"):
        build_local_level2_runtime_binding(context)


def test_installed_bridge_durable_revocation_before_release_discloses_no_protected_context(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An installed bridge sees a durable fact revoke before it releases context."""
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import (
        authorize_local_level2,
        authorize_local_structured_tool,
    )

    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider.initialize(
        "session:one", hermes_home=tmp_path, user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes",
    )
    try:
        _external_store, _read_authority = _persist_installed_protected_claim(
            provider=provider, storage_root=tmp_path / "memorii",
        )
        service = provider._provider._service
        provider.revoke_structured_grant("fact")
        observed = []
        original = service.retrieve_context

        def capture_activation(*args, **kwargs):
            result = original(*args, **kwargs)
            observed.append(result)
            return result

        monkeypatch.setattr(service, "retrieve_context", capture_activation)
        assert provider.prefetch("Atlas") == ""
        assert len(observed) == 1
        assert observed[0].mandatory_items == ()
        assert observed[0].optional_items == ()
        assert observed[0].omissions == ()
        assert observed[0].structured_outcome is None
    finally:
        provider.shutdown()


def test_installed_bridge_release_receipt_linearizes_before_durable_fact_revocation(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A competing JSONL revoke waits for the bridge's final release receipt."""
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import (
        authorize_local_level2,
        authorize_local_structured_tool,
    )

    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider.initialize(
        "session:one", hermes_home=tmp_path, user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes",
    )
    revoker = bridge_module.MemoriiHermesMemoryProvider()
    revoker.initialize(
        "session:two", hermes_home=tmp_path, user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes",
    )
    try:
        _external_store, _read_authority = _persist_installed_protected_claim(
            provider=provider, storage_root=tmp_path / "memorii",
        )
        service = provider._provider._service
        authority = service._scoped_read_authority
        original_authorize_release = authority.authorize_release
        revoke_started = Event()
        revoke_finished = Event()
        receipt_issued = Event()
        writer: Thread | None = None
        race_started = False

        def revoke() -> None:
            revoke_started.set()
            revoker.revoke_structured_grant("fact")
            revoke_finished.set()

        def authorize_release(grant):
            nonlocal race_started, writer
            if race_started:
                return original_authorize_release(grant)
            race_started = True
            writer = Thread(target=revoke, name="installed-fact-grant-revoker")
            writer.start()
            assert revoke_started.wait(timeout=1.0)
            receipt = original_authorize_release(grant)
            assert receipt is not None
            # The competing JSONL writer began after the final durable
            # recheck and cannot alter the decision before its receipt.
            assert not revoke_finished.is_set()
            receipt_issued.set()
            return receipt

        monkeypatch.setattr(authority, "authorize_release", authorize_release)
        released = provider.prefetch("Atlas")
        assert receipt_issued.is_set()
        assert "Atlas project owner is Ada." in released
        assert writer is not None
        writer.join(timeout=2.0)
        assert not writer.is_alive()
        assert revoke_finished.is_set()

        # The next bridge read sees the durable tombstone and releases no
        # protected text after the earlier receipt's linearization point.
        assert provider.prefetch("Atlas") == ""
    finally:
        revoker.shutdown()
        provider.shutdown()


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
    provider.initialize(
        "session:one",
        hermes_home=tmp_path,
        agent_identity="profile:primary",
        platform="cli",
        agent_context="primary",
        agent_workspace="hermes",
    )
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
            platform="cli",
            agent_context="primary",
            agent_workspace="/workspace",
            parent_session_id="parent:one",
        )

    assert len(contexts) == 1
    assert contexts[0].storage_root == tmp_path / "profile" / "memorii"
    assert contexts[0].session_id == "session:one"
    assert contexts[0].user_id == "user:alice"
    assert contexts[0].platform == "cli"
    assert contexts[0].agent_context == "primary"
    assert contexts[0].parent_session_id == "parent:one"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("platform", None),
        ("platform", "api"),
        ("agent_context", None),
        ("agent_context", "delegated"),
        ("agent_workspace", None),
        ("agent_workspace", "shared"),
        ("parent_session_id", "session:parent"),
    ],
)
def test_first_party_factory_rejects_every_non_primary_cli_context(
    bridge_module, tmp_path: Path, field: str, value: object
) -> None:
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import LocalLevel2AuthorityError

    context = SimpleNamespace(
        storage_root=tmp_path / "memorii",
        hermes_home=tmp_path,
        session_id="session:one",
        user_id="raw:user:one",
        agent_identity="profile:primary",
        platform="cli",
        agent_context="primary",
        agent_workspace="hermes",
        parent_session_id=None,
    )
    setattr(context, field, value)

    with pytest.raises(LocalLevel2AuthorityError, match="requires Hermes primary CLI execution"):
        build_local_level2_runtime_binding(context)


@pytest.mark.parametrize("parent_session_id", [0, object()])
def test_bridge_preserves_opaque_parent_markers_for_factory_denial(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, parent_session_id: object
) -> None:
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import LocalLevel2AuthorityError

    constructed = False

    def should_not_construct(*_args: object, **_kwargs: object) -> object:
        nonlocal constructed
        constructed = True
        raise AssertionError("service construction must not follow a rejected parent marker")

    monkeypatch.setattr(
        "memorii.integrations.hermes_factory.build_provider_memory_service_from_env", should_not_construct
    )
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    provider = bridge_module.MemoriiHermesMemoryProvider()

    with pytest.raises(LocalLevel2AuthorityError, match="requires Hermes primary CLI execution"):
        provider.initialize(
            "session:one",
            hermes_home=tmp_path,
            user_id="raw:user:one",
            agent_identity="profile:primary",
            platform="cli",
            agent_context="primary",
            agent_workspace="hermes",
            parent_session_id=parent_session_id,
        )

    assert constructed is False


def test_bridge_primary_cli_initialization_admits_a_completed_turn(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from memorii.core.semantic_ingestion.openai_responses_project_assertions import OpenAIResponsesApiClient
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import authorize_local_level2

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        OpenAIResponsesApiClient,
        "complete",
        lambda _client, **_kwargs: (
            '{"abstained":false,"candidates":[{'
            '"predicate_id":"project_owner",'
            '"assertion_quote":"Mars Venus 001 project owner is Ada.",'
            '"subject_quote":"Mars Venus 001",'
            '"predicate_anchor_quote":"owner",'
            '"value_quote":"Ada"}]}'
        ),
    )
    authorize_local_level2(hermes_home=tmp_path)
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    provider = bridge_module.MemoriiHermesMemoryProvider()

    provider.initialize(
        "session:one",
        hermes_home=tmp_path,
        user_id="raw:user:one",
        agent_identity="profile:primary",
        platform="cli",
        agent_context="primary",
        agent_workspace="hermes",
    )
    provider.sync_turn(
        "Mars Venus 001 project owner is Ada.",
        "I will remember that.",
        session_id="session:one",
        messages=[
            {
                "role": "user",
                "content": "Mars Venus 001 project owner is Ada.",
                "timestamp": "2026-09-24T21:00:00Z",
            },
            {
                "role": "assistant",
                "content": "I will remember that.",
                "timestamp": "2026-09-24T21:00:01Z",
            },
        ],
    )

    runtime = provider._completed_turn_runtime
    assert runtime is not None
    runtime.wait_for_idle()
    records = provider._provider._service._memory_plane.list_records()
    assert any(record.source_kind == "semantic_ingestion_source" for record in records)
    assert any(record.visibility.value == "runtime_context" for record in records)


def test_bridge_separates_equal_text_positions_and_redelivery_reuses_the_second_operation(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from memorii.core.semantic_ingestion.openai_responses_project_assertions import OpenAIResponsesApiClient
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    from memorii.integrations.hermes_local_authority import authorize_local_level2

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = 0

    def response(_client: object, **_kwargs: object) -> str:
        nonlocal calls
        calls += 1
        return (
            '{"abstained":false,"candidates":[{'
            '"predicate_id":"project_owner",'
            '"assertion_quote":"Mars Venus 001 project owner is Ada.",'
            '"subject_quote":"Mars Venus 001",'
            '"predicate_anchor_quote":"owner",'
            '"value_quote":"Ada"}]}'
        )

    monkeypatch.setattr(OpenAIResponsesApiClient, "complete", response)
    authorize_local_level2(hermes_home=tmp_path)
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    provider = bridge_module.MemoriiHermesMemoryProvider()
    provider.initialize(
        "session:one",
        hermes_home=tmp_path,
        user_id="raw:user:one",
        agent_identity="profile:primary",
        platform="cli",
        agent_context="primary",
        agent_workspace="hermes",
    )
    first_messages = [
        {
            "role": "user",
            "content": "Mars Venus 001 project owner is Ada.",
            "timestamp": "2026-09-24T21:00:00Z",
        },
        {
            "role": "assistant",
            "content": "I will remember that.",
            "timestamp": "2026-09-24T21:00:01Z",
        },
    ]
    later_messages = [
        *first_messages,
        {
            "role": "user",
            "content": "Mars Venus 001 project owner is Ada.",
            "timestamp": "2026-09-24T21:10:00Z",
        },
        {
            "role": "assistant",
            "content": "I will remember that.",
            "timestamp": "2026-09-24T21:10:01Z",
        },
    ]

    callback_times = iter((
        datetime(2026, 9, 24, 21, 5, tzinfo=UTC),
        datetime(2026, 9, 24, 21, 15, tzinfo=UTC),
        datetime(2026, 9, 24, 21, 25, tzinfo=UTC),
    ))

    class _CallbackClock:
        @classmethod
        def now(cls, timezone: object) -> datetime:
            assert timezone is UTC
            return next(callback_times)

    monkeypatch.setattr(bridge_module, "datetime", _CallbackClock)

    provider.sync_turn(
        "Mars Venus 001 project owner is Ada.",
        "I will remember that.",
        messages=first_messages,
    )
    runtime = provider._completed_turn_runtime
    assert runtime is not None
    runtime.wait_for_idle()

    authority_checks = 0
    require_current_authority = runtime._require_current_authority

    def count_current_authority() -> None:
        nonlocal authority_checks
        authority_checks += 1
        require_current_authority()

    runtime._require_current_authority = count_current_authority

    provider.sync_turn(
        "Mars Venus 001 project owner is Ada.",
        "I will remember that.",
        messages=later_messages,
    )
    runtime.wait_for_idle()
    provider.sync_turn(
        "Mars Venus 001 project owner is Ada.",
        "I will remember that.",
        messages=later_messages,
    )
    runtime.wait_for_idle()

    records = provider._provider._service._memory_plane.list_records()
    assert calls == 2
    assert authority_checks >= 2
    assert len([record for record in records if record.source_kind == "semantic_ingestion_source"]) == 4
    assert len([record for record in records if record.visibility.value == "runtime_context"]) == 2


def test_generic_authenticated_source_reaches_the_local_candidate_and_owner_path(
    bridge_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-Hermes envelope reaches the same core recurrence/candidate owner."""
    from memorii.core.semantic_ingestion.learned_relation import LearnedRelationError
    from memorii.core.semantic_ingestion.structured_fact_read import StructuredFactReadRequest
    from memorii.integrations.authenticated_source import AuthenticatedSourceSubmission
    from memorii.integrations.hermes_factory import (
        build_local_level2_authenticated_source_runtime,
    )
    from memorii.integrations.hermes_local_authority import (
        authorize_local_level2,
        authorize_local_structured_tool,
    )

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    def forbid_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("generic no-key ontology journey attempted network I/O")
    monkeypatch.setattr(socket, "getaddrinfo", forbid_network)
    monkeypatch.setattr(socket, "create_connection", forbid_network)
    monkeypatch.setattr(socket.socket, "connect", forbid_network)
    monkeypatch.setattr(socket.socket, "connect_ex", forbid_network)
    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    context = SimpleNamespace(
        storage_root=tmp_path / "generic", hermes_home=tmp_path,
        session_id="generic:one", user_id="raw:user:one",
        agent_identity="profile:primary", platform="cli", agent_context="primary",
        agent_workspace="hermes", parent_session_id=None,
    )
    runtime = build_local_level2_authenticated_source_runtime(context)
    results = []
    for ordinal, (session_id, sentence) in enumerate((
        ("generic:one", "Ada mentors Bea."),
        ("generic:two", "Cora mentors Dax."),
        ("generic:one", "Eve mentors Finn."),
        ("generic:two", "Gia mentors Hugo."),
    ), start=1):
        submission = AuthenticatedSourceSubmission(
            operation=ProviderOperation.CHAT_USER_TURN,
            content=sentence, operation_id=f"generic-mentors:{ordinal}",
            session_id=session_id, user_id="raw:user:one",
            timestamp=datetime(2026, 9, 27, ordinal, tzinfo=UTC),
        )
        results.append(runtime.submit(submission))
        if ordinal == 4:
            results.append(runtime.submit(submission))
    status = runtime.lookup_learned_ontology_status()
    assert status["candidate_count"] == 1, [item.model_dump(mode="json") for item in results]
    assert len(status["candidate_ids"]) == 1
    proposal_records = runtime._adapter._service._memory_plane.list_records(
        source_kind="learned_ontology_change_proposal_v1",
    )
    assert len(proposal_records) == 1
    assert proposal_records[0].content["proposal"]["lifecycle"] == "awaiting_decision"
    proposal_id = status["candidate_ids"][0]
    runtime.approve_learned_candidate(proposal_id)
    activation = runtime.activate_learned_candidate(proposal_id)
    assert activation.status == "selected"
    selected = runtime.lookup_learned_ontology_status()
    assert selected["active_version_digest"] == activation.target_version_digest
    assert selected["replay_outcomes"] == {"committed": 3}
    claims = [
        record
        for record in runtime._adapter._service._memory_plane.list_records()
        if record.content.get("runtime_context_projection_kind")
        == "bootstrap_v3_claim_assertion"
        and record.content.get("claim_identity", {})
        .get("assertion_key_at_recording", {})
        .get("slot", {})
        .get("predicate_id")
        == "mentors"
    ]
    assert len(claims) == 3
    subject_id = claims[0].content["claim_identity"]["subject_assertion_ref"][
        "logical_entity_id_at_assertion"
    ]
    read_request = StructuredFactReadRequest(
        predicate_id="mentors",
        subject_entity_id=subject_id,
    )
    read = runtime.read_structured_facts(read_request)
    assert read.status == "ok" and len(read.items) == 1
    runtime.close()
    runtime = build_local_level2_authenticated_source_runtime(context)
    reopened = runtime.read_structured_facts(read_request)
    assert reopened == read
    assert runtime.lookup_learned_ontology_status() == selected

    before = selected
    with pytest.raises(LearnedRelationError):
        runtime.approve_learned_candidate("ocp_" + "0" * 64)
    assert runtime.lookup_learned_ontology_status() == before

    # The independently composed Hermes adapter receives the same source
    # evidence. Both adapters leave proposal/version identity to core.
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
    monkeypatch.setattr(
        bridge_module.importlib.metadata,
        "entry_points",
        lambda *, group: (_FactoryEntryPoint(build_local_level2_runtime_binding),),
    )
    hermes = None
    for ordinal, (session_id, sentence) in enumerate((
        ("generic:one", "Ada mentors Bea."),
        ("generic:two", "Cora mentors Dax."),
        ("generic:one", "Eve mentors Finn."),
    ), start=1):
        hermes = bridge_module.MemoriiHermesMemoryProvider()
        hermes.initialize(
            session_id, hermes_home=tmp_path, user_id="raw:user:one",
            agent_identity="profile:primary", platform="cli", agent_context="primary",
            agent_workspace="hermes",
        )
        # Coverage observation happens at the public authenticated capture
        # boundary. A fresh host instance per retained turn also proves restart
        # recovery without creating overlapping live tool handles.
        hermes.on_turn_start(ordinal, sentence)
        if ordinal < 3:
            hermes.shutdown()
    assert hermes is not None
    hermes_status = hermes.lookup_learned_ontology_status()
    assert hermes_status["candidate_ids"] == (proposal_id,)
    hermes.approve_learned_candidate(proposal_id)
    hermes_activation = hermes.activate_learned_candidate(proposal_id)
    assert hermes_activation.target_version_digest == activation.target_version_digest
    hermes.shutdown()
    runtime.close()
