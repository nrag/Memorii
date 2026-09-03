"""Production-root composition, revocation, conflict, and reopen proofs."""



from __future__ import annotations

import inspect

import pytest
from memorii.core.filesystem_storage.bundle import (
    build_filesystem_provider as _production_filesystem_provider,
)
from memorii.core.memory_plane import JsonlMemoryPlaneStore, MemoryPlaneService
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.provider.factory import (
    build_provider_memory_service_from_env as _production_factory_provider,
)
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.semantic_ingestion.bootstrap_graph_host import (
    BootstrapGraphHostBundleBuilder,
)
from memorii.core.semantic_ingestion.contracts import (
    ProviderEntityObject,
    ProviderFact,
    ProviderMention,
    ProviderSemanticProposal,
)
from memorii.domain.enums import CommitStatus, MemoryDomain
from memorii.integrations.hermes_provider import (
    HermesMemoryProvider as _ProductionHermesMemoryProvider,
)
from tests.fixtures.semantic_ingestion.bootstrap_graph_v3_fixture import (
    DeterministicBootstrapGraphAuthorityProviderV3,
)
from tests.unit.core.semantic_ingestion.bootstrap_graph_production_roots_support import (
    RemovedBootstrapGraphHostBundleBuilder,
    build_filesystem_provider,
    build_provider_memory_service_from_env,
    graph_fact_proposal,
    graph_host_bundle_builders,
    hermes_provider,
    provider_service,
)
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
    TEST_NOW,
    DeterministicTestHostBootstrapMaterialVerifier,
    _built_in_local_capability,
    _host_ingress,
    _v3_normalization_host_builder,
)


@pytest.mark.parametrize("root", ("direct", "factory", "filesystem", "hermes"))
def test_all_normal_roots_compose_same_graph_host_bundle(
    root: str, tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    normalization, graph = graph_host_bundle_builders()
    common = {
        "host_bootstrap_capability": _built_in_local_capability(),
        "host_bootstrap_material_verifier": DeterministicTestHostBootstrapMaterialVerifier(),
        "source_normalization_host_bundle_builder": normalization,
        "bootstrap_graph_host_bundle_builder": graph,
    }
    service: ProviderMemoryService
    if root == "direct":
        service = provider_service(**common)
    elif root == "factory":
        service = build_provider_memory_service_from_env(**common)
    elif root == "filesystem":
        service = build_filesystem_provider(tmp_path / "memorii", **common)
    else:
        provider = hermes_provider(**common)
        service = provider._service

    runtime = service._provider_ingestion._semantic_runtime
    assert runtime is not None
    assert runtime.bootstrap_graph_host_bundle is not None
    assert runtime.bootstrap_graph_host_bundle.authority_provider is graph.authority_provider


@pytest.mark.parametrize("root", ("direct", "factory", "filesystem", "hermes"))
def test_all_normal_roots_install_builtin_graph_host_without_injection(
    root: str, tmp_path,
) -> None:
    """The normal host has a native graph authority without test-fixture wiring."""
    normalization, _calls = _v3_normalization_host_builder(
        proposal=ProviderSemanticProposal(abstained=True)
    )
    common = {
        "now_provider": lambda: TEST_NOW,
        "host_bootstrap_capability": _built_in_local_capability(),
        "host_bootstrap_material_verifier": DeterministicTestHostBootstrapMaterialVerifier(),
        "source_normalization_host_bundle_builder": normalization,
    }
    if root == "direct":
        service = provider_service(**common)
    elif root == "factory":
        service = build_provider_memory_service_from_env(**common)
    elif root == "filesystem":
        service = build_filesystem_provider(tmp_path / "builtin-graph", **common)
    else:
        service = hermes_provider(
            host_bootstrap_capability=common["host_bootstrap_capability"],
            host_bootstrap_material_verifier=common["host_bootstrap_material_verifier"],
            source_normalization_host_bundle_builder=common[
                "source_normalization_host_bundle_builder"
            ],
        )._service

    runtime = service._provider_ingestion._semantic_runtime
    assert runtime is not None
    assert runtime.bootstrap_graph_host_bundle is not None
    assert type(runtime.bootstrap_graph_host_bundle).__name__ == "BootstrapGraphHostBundle"
    assert not hasattr(runtime.bootstrap_graph_host_bundle, "authority_provider")


def test_normal_root_signatures_do_not_expose_graph_authority_injection() -> None:
    """Fixture graph providers are available only through the private test harness."""
    for target in (
        ProviderMemoryService,
        _production_factory_provider,
        _production_filesystem_provider,
        _ProductionHermesMemoryProvider,
    ):
        assert "bootstrap_graph_host_bundle_builder" not in inspect.signature(
            target
        ).parameters
    assert "bootstrap_graph_host_bundle_builder" in inspect.signature(
        ProviderMemoryService._from_scenario_test_host
    ).parameters


@pytest.mark.parametrize("root", ("direct", "factory", "filesystem", "hermes"))
def test_all_normal_roots_execute_builtin_native_graph_path_without_injection(
    root: str, tmp_path,
) -> None:
    """A real fact reaches native graph commit through every normal root."""
    proposal = graph_fact_proposal()
    normalization, _calls = _v3_normalization_host_builder(proposal=proposal)
    common = {
        "now_provider": lambda: TEST_NOW,
        "host_bootstrap_capability": _built_in_local_capability(),
        "host_bootstrap_material_verifier": DeterministicTestHostBootstrapMaterialVerifier(),
        "source_normalization_host_bundle_builder": normalization,
    }
    if root == "direct":
        service = provider_service(**common)
    elif root == "factory":
        service = build_provider_memory_service_from_env(**common)
    elif root == "filesystem":
        service = build_filesystem_provider(tmp_path / "builtin-native-graph", **common)
    else:
        service = hermes_provider(service=provider_service(**common))._service
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id=f"builtin-native-graph-{root}",
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert result.blocked_reasons["semantic_ingestion"] == "source_only"
    assert len(service._memory_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    )) == 1


@pytest.mark.parametrize("root", ("direct", "factory", "filesystem", "hermes"))
def test_all_normal_roots_execute_graph_terminal_once(
    root: str, tmp_path,
) -> None:
    proposal = graph_fact_proposal()
    normalization, lane_calls = _v3_normalization_host_builder(proposal=proposal)
    graph_calls: list[str] = []
    graph = BootstrapGraphHostBundleBuilder(
        authority_provider=DeterministicBootstrapGraphAuthorityProviderV3(
            successful_calls=graph_calls
        )
    )
    common = {
        "now_provider": lambda: TEST_NOW,
        "host_bootstrap_capability": _built_in_local_capability(),
        "host_bootstrap_material_verifier": DeterministicTestHostBootstrapMaterialVerifier(),
        "source_normalization_host_bundle_builder": normalization,
        "bootstrap_graph_host_bundle_builder": graph,
    }
    if root == "direct":
        service = provider_service(**common)
    elif root == "factory":
        service = build_provider_memory_service_from_env(**common)
    elif root == "filesystem":
        service = build_filesystem_provider(tmp_path / "memorii-executable", **common)
    else:
        service = hermes_provider(service=provider_service(**common))._service

    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id=f"graph-root-{root}",
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert result.blocked_reasons["semantic_ingestion"] == "source_only"
    assert len(graph_calls) == 1
    assert all(count == 1 for count in lane_calls.values())


def test_partial_normal_composition_fails_closed_before_graph_effects() -> None:
    normalization, _calls = _v3_normalization_host_builder(
        proposal=ProviderSemanticProposal(
            mentions=(
                ProviderMention(
                    local_id="atlas", mention_quote="Atlas",
                    mention_context_quote="Atlas owner is Bob.",
                ),
                ProviderMention(
                    local_id="bob", mention_quote="Bob",
                    mention_context_quote="Atlas owner is Bob.",
                ),
            ),
            facts=(ProviderFact(
                local_id="owner", predicate_id="owner_is", subject_entity_ref="atlas",
                object=ProviderEntityObject(entity_ref="bob"), assertion_quote="Atlas owner is Bob.",
                predicate_anchor_quote="owner", polarity="positive", commitment="asserted",
            ),),
            abstained=False,
        )
    )
    service = provider_service(
        # The M4 built-in capability always wires its own graph host, so a
        # graph-authority-less composition is built explicitly: the removed
        # builder installs a scenario host bundle with no authority provider,
        # and the run must fail closed at the graph boundary before effects.
        bootstrap_graph_host_bundle_builder=RemovedBootstrapGraphHostBundleBuilder(),
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(scenario_test=True),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=normalization,
    )

    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id="graph-bundle-absent",
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )

    assert result.blocked_reasons["semantic_ingestion"] == "graph_transaction_authority_unavailable"
    assert not service._memory_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_member"
    )


@pytest.mark.parametrize(
    ("root", "backend"),
    tuple(
        (root, backend)
        for root in ("direct", "factory", "filesystem", "hermes")
        for backend in ("memory", "jsonl")
    ),
)
def test_public_root_scope_revocation_immediately_before_group_cas_is_durable(
    root: str, backend: str, tmp_path,
) -> None:
    proposal = graph_fact_proposal()
    ingress = _host_ingress()
    current_scope = [""]
    cas_attempts: list[str] = []
    graph_effects: list[str] = []

    def revoke_scope(_group_id: str) -> None:
        # The store-backed group commit derives its outcome from the sealed
        # reductions and never consults the executor's scope check, so the
        # revocation must fail the CAS itself: one attempt, zero effects.
        current_scope[0] = "f" * 64
        from memorii.core.memory_evolution.atomic_store import PreplanningStoreError

        raise PreplanningStoreError("injected scope revocation before group CAS")

    def build_service(*, replay: bool) -> tuple[ProviderMemoryService, dict[str, int]]:
        normalization, lane_calls = _v3_normalization_host_builder(proposal=proposal)
        provider = DeterministicBootstrapGraphAuthorityProviderV3(
            successful_calls=graph_effects,
            cas_attempts=cas_attempts,
            before_compare_and_swap=None if replay else revoke_scope,
            current_scope_digest=lambda: current_scope[0],
        )
        common = {
            "now_provider": lambda: TEST_NOW,
            "host_bootstrap_capability": _built_in_local_capability(),
            "host_bootstrap_material_verifier": DeterministicTestHostBootstrapMaterialVerifier(),
            "source_normalization_host_bundle_builder": normalization,
            "bootstrap_graph_host_bundle_builder": BootstrapGraphHostBundleBuilder(
                authority_provider=provider
            ),
        }
        memory_plane = (
            MemoryPlaneService(
                record_store=JsonlMemoryPlaneStore(tmp_path / "scope-revoked" / "memory-plane")
            )
            if backend == "jsonl"
            else MemoryPlaneService()
        )
        if root == "filesystem":
            return build_filesystem_provider(
                tmp_path / "scope-revoked-filesystem",
                memory_plane=memory_plane,
                **common,
            ), lane_calls
        if root == "factory":
            return build_provider_memory_service_from_env(
                memory_plane=memory_plane, **common
            ), lane_calls
        if root == "hermes":
            return hermes_provider(
                service=provider_service(memory_plane=memory_plane, **common)
            )._service, lane_calls
        return provider_service(memory_plane=memory_plane, **common), lane_calls

    first, _first_lanes = build_service(replay=False)
    resolved_ingress = first._resolve_ingress(ingress)
    assert resolved_ingress is not None
    current_scope[0] = (
        resolved_ingress.current_authorized_scopes.required_scope_set_digest
    )
    first_result = first.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id=f"scope-revoked-{root}-{backend}",
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=ingress,
    )
    assert first_result.blocked_reasons["semantic_ingestion"] == "graph_transaction_authority_unavailable"
    assert len(cas_attempts) == 1
    assert graph_effects == []
    assert first._memory_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_retry_index"
    )

    replay_service, replay_lanes = (
        build_service(replay=True) if backend == "jsonl" else (first, {})
    )
    replay_result = replay_service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id=f"scope-revoked-{root}-{backend}",
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=ingress,
    )
    assert replay_result.blocked_reasons["semantic_ingestion"] == "graph_transaction_authority_unavailable"
    assert len(cas_attempts) == 1
    assert graph_effects == []
    assert all(count == 0 for count in replay_lanes.values())


@pytest.mark.parametrize(
    ("root", "backend"),
    tuple(
        (root, backend)
        for root in ("direct", "factory", "filesystem", "hermes")
        for backend in ("memory", "jsonl")
    ),
)
def test_unrelated_foreign_write_does_not_conflict_with_group_cas(
    root: str, backend: str, tmp_path,
) -> None:
    proposal = graph_fact_proposal()
    normalization, lane_calls = _v3_normalization_host_builder(proposal=proposal)
    cas_attempts: list[str] = []
    graph_effects: list[str] = []
    service_holder: list[ProviderMemoryService] = []

    def write_unrelated(_group_id: str) -> None:
        service_holder[0]._memory_plane.upsert_record(
            CanonicalMemoryRecord(
                memory_id=f"unrelated:{root}:{backend}",
                domain=MemoryDomain.EXECUTION,
                text="unrelated graph partition write",
                content={"partition": "outside-sealed-read-set"},
                status=CommitStatus.COMMITTED,
                source_kind="bootstrap_graph_unrelated_foreign_write",
                timestamp=TEST_NOW,
            )
        )

    graph = BootstrapGraphHostBundleBuilder(
        authority_provider=DeterministicBootstrapGraphAuthorityProviderV3(
            successful_calls=graph_effects,
            cas_attempts=cas_attempts,
            before_compare_and_swap=write_unrelated,
        )
    )
    common = {
        "now_provider": lambda: TEST_NOW,
        "host_bootstrap_capability": _built_in_local_capability(),
        "host_bootstrap_material_verifier": DeterministicTestHostBootstrapMaterialVerifier(),
        "source_normalization_host_bundle_builder": normalization,
        "bootstrap_graph_host_bundle_builder": graph,
    }
    memory_plane = (
        MemoryPlaneService(
            record_store=JsonlMemoryPlaneStore(tmp_path / "unrelated-write" / "memory-plane")
        )
        if backend == "jsonl"
        else MemoryPlaneService()
    )
    if root == "filesystem":
        service = build_filesystem_provider(
            tmp_path / "unrelated-write-filesystem",
            memory_plane=memory_plane,
            **common,
        )
    elif root == "factory":
        service = build_provider_memory_service_from_env(memory_plane=memory_plane, **common)
    elif root == "hermes":
        service = hermes_provider(
            service=provider_service(memory_plane=memory_plane, **common)
        )._service
    else:
        service = provider_service(memory_plane=memory_plane, **common)
    service_holder.append(service)
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id=f"unrelated-write-{root}-{backend}",
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )

    assert result.blocked_reasons["semantic_ingestion"] == "source_only"
    assert len(cas_attempts) == 1
    assert len(graph_effects) == 1
    assert all(count == 1 for count in lane_calls.values())
    assert service._memory_plane.get_record(f"unrelated:{root}:{backend}") is not None




def test_filesystem_root_reopens_graph_terminal_without_reexecuting(tmp_path) -> None:
    storage_root = tmp_path / "memorii-reopen"
    proposal = ProviderSemanticProposal(
        mentions=(
            ProviderMention(
                local_id="atlas", mention_quote="Atlas",
                mention_context_quote="Atlas owner is Bob.",
            ),
            ProviderMention(
                local_id="bob", mention_quote="Bob",
                mention_context_quote="Atlas owner is Bob.",
            ),
        ),
        facts=(ProviderFact(
            local_id="owner", predicate_id="owner_is", subject_entity_ref="atlas",
            object=ProviderEntityObject(entity_ref="bob"), assertion_quote="Atlas owner is Bob.",
            predicate_anchor_quote="owner", polarity="positive", commitment="asserted",
        ),),
        abstained=False,
    )
    first_normalization, _first_lanes = _v3_normalization_host_builder(proposal=proposal)
    first_graph_calls: list[str] = []
    first = build_filesystem_provider(
        storage_root,
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=first_normalization,
        bootstrap_graph_host_bundle_builder=BootstrapGraphHostBundleBuilder(
            authority_provider=DeterministicBootstrapGraphAuthorityProviderV3(
                successful_calls=first_graph_calls
            )
        ),
    )
    first_result = first.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id="graph-jsonl-reopen",
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert first_result.blocked_reasons["semantic_ingestion"] == "source_only"
    assert len(first_graph_calls) == 1

    second_normalization, second_lanes = _v3_normalization_host_builder(proposal=proposal)
    second_graph_calls: list[str] = []
    second = build_filesystem_provider(
        storage_root,
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=second_normalization,
        bootstrap_graph_host_bundle_builder=BootstrapGraphHostBundleBuilder(
            authority_provider=DeterministicBootstrapGraphAuthorityProviderV3(
                successful_calls=second_graph_calls
            )
        ),
    )
    second_result = second.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id="graph-jsonl-reopen",
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert second_result == first_result
    assert second_graph_calls == []
    assert sum(second_lanes.values()) == 0


def test_filesystem_root_reloads_durable_graph_retry_without_reexecuting(tmp_path) -> None:
    storage_root = tmp_path / "memorii-retry-reopen"
    proposal = ProviderSemanticProposal(
        mentions=(
            ProviderMention(
                local_id="atlas", mention_quote="Atlas",
                mention_context_quote="Atlas owner is Bob.",
            ),
            ProviderMention(
                local_id="bob", mention_quote="Bob",
                mention_context_quote="Atlas owner is Bob.",
            ),
        ),
        facts=(ProviderFact(
            local_id="owner", predicate_id="owner_is",
            subject_entity_ref="atlas", object=ProviderEntityObject(entity_ref="bob"),
            assertion_quote="Atlas owner is Bob.", predicate_anchor_quote="owner",
            polarity="positive", commitment="asserted",
        ),),
        abstained=False,
    )
    first_normalization, _first_lanes = _v3_normalization_host_builder(proposal=proposal)
    first_unavailable_calls: list[str] = []
    first = build_filesystem_provider(
        storage_root,
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=first_normalization,
        bootstrap_graph_host_bundle_builder=BootstrapGraphHostBundleBuilder(
            authority_provider=DeterministicBootstrapGraphAuthorityProviderV3(
                successful_calls=[], unavailable_calls=first_unavailable_calls,
            )
        ),
    )
    first_result = first.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id="graph-jsonl-retry",
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert first_result.blocked_reasons["semantic_ingestion"] == "graph_transaction_authority_unavailable"
    assert len(first_unavailable_calls) == 1

    second_normalization, second_lanes = _v3_normalization_host_builder(proposal=proposal)
    second_unavailable_calls: list[str] = []
    second = build_filesystem_provider(
        storage_root,
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=second_normalization,
        bootstrap_graph_host_bundle_builder=BootstrapGraphHostBundleBuilder(
            authority_provider=DeterministicBootstrapGraphAuthorityProviderV3(
                successful_calls=[], unavailable_calls=second_unavailable_calls,
            )
        ),
    )
    second_result = second.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id="graph-jsonl-retry",
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert second_result == first_result
    assert second_unavailable_calls == []
    assert sum(second_lanes.values()) == 0


@pytest.mark.parametrize(
    ("scenario", "group_count", "conflict_count", "effect_count"),
    (
        ("resolved", 1, 2, 1),
        ("exhausted", 1, 2, 1),
        ("partial", 3, 4, 3),
    ),
)
def test_filesystem_root_reloads_graph_successor_without_reexecuting(
    tmp_path, scenario: str, group_count: int, conflict_count: int, effect_count: int,
) -> None:
    storage_root = tmp_path / f"memorii-{scenario}-successor-reopen"
    proposal = graph_fact_proposal(group_count)
    first_normalization, _first_lanes = _v3_normalization_host_builder(proposal=proposal)
    first_conflicts: list[str] = []
    first_effects: list[str] = []
    conflict_field = {
        "resolved": "conflict_calls",
        "exhausted": "exhausted_conflict_calls",
        "partial": "partial_conflict_calls",
    }[scenario]
    provider_kwargs = {
        "successful_calls": first_effects,
        conflict_field: first_conflicts,
    }
    first = build_filesystem_provider(
        storage_root,
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=first_normalization,
        bootstrap_graph_host_bundle_builder=BootstrapGraphHostBundleBuilder(
            authority_provider=DeterministicBootstrapGraphAuthorityProviderV3(
                **provider_kwargs
            )
        ),
    )
    first_result = first.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id=f"graph-jsonl-{scenario}-successor",
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert first_result.blocked_reasons["semantic_ingestion"] == "source_only"
    assert len(first_conflicts) == conflict_count
    assert len(first_effects) == effect_count

    second_normalization, second_lanes = _v3_normalization_host_builder(proposal=proposal)
    second_conflicts: list[str] = []
    second_effects: list[str] = []
    second_provider_kwargs = {
        "successful_calls": second_effects,
        conflict_field: second_conflicts,
    }
    second = build_filesystem_provider(
        storage_root,
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=second_normalization,
        bootstrap_graph_host_bundle_builder=BootstrapGraphHostBundleBuilder(
            authority_provider=DeterministicBootstrapGraphAuthorityProviderV3(
                **second_provider_kwargs
            )
        ),
    )
    second_result = second.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id=f"graph-jsonl-{scenario}-successor",
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert second_result == first_result
    assert second_conflicts == []
    assert second_effects == []
    assert sum(second_lanes.values()) == 0


def test_direct_root_replans_once_after_related_conflict() -> None:
    proposal = ProviderSemanticProposal(
        mentions=(
            ProviderMention(
                local_id="atlas", mention_quote="Atlas",
                mention_context_quote="Atlas owner is Bob.",
            ),
            ProviderMention(
                local_id="bob", mention_quote="Bob",
                mention_context_quote="Atlas owner is Bob.",
            ),
        ),
        facts=(ProviderFact(
            local_id="owner", predicate_id="owner_is",
            subject_entity_ref="atlas", object=ProviderEntityObject(entity_ref="bob"),
            assertion_quote="Atlas owner is Bob.", predicate_anchor_quote="owner",
            polarity="positive", commitment="asserted",
        ),),
        abstained=False,
    )
    normalization, _lane_calls = _v3_normalization_host_builder(proposal=proposal)
    conflict_calls: list[str] = []
    successful_calls: list[str] = []
    service = provider_service(
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=normalization,
        bootstrap_graph_host_bundle_builder=BootstrapGraphHostBundleBuilder(
            authority_provider=DeterministicBootstrapGraphAuthorityProviderV3(
                successful_calls=successful_calls,
                conflict_calls=conflict_calls,
            )
        ),
    )

    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id="graph-related-conflict",
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )

    assert result.blocked_reasons["semantic_ingestion"] == "source_only", (
        conflict_calls, successful_calls
    )
    assert len(conflict_calls) == 2
    assert len(successful_calls) == 1
    repeat = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id="graph-related-conflict",
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert repeat == result
    assert len(conflict_calls) == 2
    assert len(successful_calls) == 1


def test_direct_root_preserves_completed_group_during_related_conflict() -> None:
    proposal = ProviderSemanticProposal(
        mentions=(
            ProviderMention(
                local_id="atlas", mention_quote="Atlas",
                mention_context_quote="Atlas owner is Bob.",
            ),
            ProviderMention(
                local_id="bob", mention_quote="Bob",
                mention_context_quote="Atlas owner is Bob.",
            ),
        ),
        facts=(
            ProviderFact(
                local_id="owner", predicate_id="owner_is",
                subject_entity_ref="atlas", object=ProviderEntityObject(entity_ref="bob"),
                assertion_quote="Atlas owner is Bob.", predicate_anchor_quote="owner",
                polarity="positive", commitment="asserted",
            ),
            ProviderFact(
                local_id="owned-by", predicate_id="owned_by",
                subject_entity_ref="bob", object=ProviderEntityObject(entity_ref="atlas"),
                assertion_quote="Atlas owner is Bob.", predicate_anchor_quote="Bob",
                polarity="positive", commitment="asserted",
            ),
            ProviderFact(
                local_id="managed-by", predicate_id="managed_by",
                subject_entity_ref="atlas", object=ProviderEntityObject(entity_ref="bob"),
                assertion_quote="Atlas owner is Bob.", predicate_anchor_quote="owner",
                polarity="positive", commitment="asserted",
            ),
        ),
        abstained=False,
    )
    normalization, _lane_calls = _v3_normalization_host_builder(proposal=proposal)
    conflict_calls: list[str] = []
    successful_calls: list[str] = []
    service = provider_service(
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=normalization,
        bootstrap_graph_host_bundle_builder=BootstrapGraphHostBundleBuilder(
            authority_provider=DeterministicBootstrapGraphAuthorityProviderV3(
                successful_calls=successful_calls,
                partial_conflict_calls=conflict_calls,
            )
        ),
    )

    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id="graph-partial-conflict",
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )

    assert result.blocked_reasons["semantic_ingestion"] == "source_only", (
        conflict_calls, successful_calls
    )
    assert len(conflict_calls) == 4
    assert len(successful_calls) == 3
    repeat = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id="graph-partial-conflict",
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert repeat == result
    assert len(conflict_calls) == 4
    assert len(successful_calls) == 3
