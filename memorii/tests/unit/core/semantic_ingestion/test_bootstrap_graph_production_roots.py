"""Production-root composition proof for the mandatory bootstrap graph bundle."""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from memorii.core.filesystem_storage.bundle import (
    build_filesystem_provider as _production_filesystem_provider,
)
from memorii.core.memory_evolution.writer_admission import SemanticWriterAdmissionError
from memorii.core.memory_plane import JsonlMemoryPlaneStore, MemoryPlaneService
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.provider.factory import (
    build_provider_memory_service_from_env as _production_factory_provider,
)
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.semantic_ingestion.bootstrap_graph_host import (
    BootstrapGraphHostBundleBuilder,
    ScenarioBootstrapGraphHostBundle,
)
from memorii.core.semantic_ingestion.bootstrap_graph_repository import (
    AtomicStoreBootstrapGraphControlEpochRepositoryV3,
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
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
    TEST_NOW,
    DeterministicTestHostBootstrapMaterialVerifier,
    _built_in_local_capability,
    _host_ingress,
    _v3_normalization_host_builder,
)

_GRAPH_SCENARIO_BEHAVIOR = {
    "initial_attempt": "normal_success",
    "successor_attempt": "resolved_conflict",
    "reused_committed": "reused_committed",
    "reused_final": "reused_final",
    "reused_unfinished": "reused_unfinished",
    "replacement": "resolved_conflict",
    "epoch_zero": "normal_success",
    "lease_renewed": "lease_renewed",
    "lease_reclaimed": "lease_reclaimed",
    "writer_changed": "writer_changed",
    "writer_unavailable": "writer_unavailable",
    "pre_cas_scope_revoked": "scope_revoked",
    "unrelated_conflict": "unrelated_conflict",
    "related_conflict": "resolved_conflict",
    "partial_commit": "partial_commit",
    "durable_retry": "durable_retry",
    "finalized_failure": "exhausted_conflict",
    "success_finalization": "normal_success",
    "terminal_locator": "terminal_locator",
    "lost_ack": "lost_ack",
    "reopen": "normal_success",
    "mixed_version": "mixed_version",
    "rollback": "rollback",
    "coordinator_removed": "coordinator_removed",
    "authority_omitted": "authority_omitted",
}


class _RemovedBootstrapGraphHostBundleBuilder:
    """Build the private negative-test host with no graph coordinator authority."""

    def build(self, *, atomic_store: object) -> ScenarioBootstrapGraphHostBundle:
        return ScenarioBootstrapGraphHostBundle(
            atomic_store=atomic_store,
            authority_provider=None,
        )


def _provider_service(**kwargs) -> ProviderMemoryService:
    graph_builder = kwargs.pop("bootstrap_graph_host_bundle_builder", None)
    if graph_builder is None:
        return ProviderMemoryService(**kwargs)
    kwargs["host_bootstrap_capability"] = _built_in_local_capability(
        scenario_test=True
    )
    return ProviderMemoryService._from_scenario_test_host(
        bootstrap_graph_host_bundle_builder=graph_builder,
        **kwargs,
    )


def build_provider_memory_service_from_env(**kwargs) -> ProviderMemoryService:
    graph_builder = kwargs.pop("bootstrap_graph_host_bundle_builder", None)
    if graph_builder is None:
        return _production_factory_provider(**kwargs)
    return _provider_service(
        bootstrap_graph_host_bundle_builder=graph_builder,
        **kwargs,
    )


def build_filesystem_provider(storage_root, **kwargs) -> ProviderMemoryService:
    graph_builder = kwargs.pop("bootstrap_graph_host_bundle_builder", None)
    if graph_builder is None:
        return _production_filesystem_provider(storage_root, **kwargs)
    # The graph-host composition must keep the filesystem root's durable
    # memory plane: a reopened service over the same root reloads the
    # retained recovery and graph terminal instead of starting empty.
    if "memory_plane" not in kwargs:
        kwargs["memory_plane"] = MemoryPlaneService(
            record_store=JsonlMemoryPlaneStore(Path(storage_root) / "memory_plane")
        )
    return _provider_service(
        bootstrap_graph_host_bundle_builder=graph_builder,
        **kwargs,
    )


def _hermes_provider(*, service=None, **kwargs):
    graph_builder = kwargs.pop("bootstrap_graph_host_bundle_builder", None)
    if service is not None:
        return _ProductionHermesMemoryProvider(service=service)
    if graph_builder is None:
        return _ProductionHermesMemoryProvider(**kwargs)
    return _ProductionHermesMemoryProvider(
        service=_provider_service(
            bootstrap_graph_host_bundle_builder=graph_builder,
            **kwargs,
        )
    )


def _builders() -> tuple[object, BootstrapGraphHostBundleBuilder]:
    normalization, _calls = _v3_normalization_host_builder(
        proposal=ProviderSemanticProposal(abstained=True)
    )
    graph = BootstrapGraphHostBundleBuilder(
        authority_provider=DeterministicBootstrapGraphAuthorityProviderV3(
            successful_calls=[]
        )
    )
    return normalization, graph


def _graph_fact_proposal(group_count: int = 1) -> ProviderSemanticProposal:
    facts = (
        ProviderFact(
            local_id="owner", predicate_id="owner_is", subject_entity_ref="atlas",
            object=ProviderEntityObject(entity_ref="bob"),
            assertion_quote="Atlas owner is Bob.", predicate_anchor_quote="owner",
            polarity="positive", commitment="asserted",
        ),
        ProviderFact(
            local_id="owned-by", predicate_id="owned_by", subject_entity_ref="bob",
            object=ProviderEntityObject(entity_ref="atlas"),
            assertion_quote="Atlas owner is Bob.", predicate_anchor_quote="Bob",
            polarity="positive", commitment="asserted",
        ),
        ProviderFact(
            local_id="managed-by", predicate_id="managed_by", subject_entity_ref="atlas",
            object=ProviderEntityObject(entity_ref="bob"),
            assertion_quote="Atlas owner is Bob.", predicate_anchor_quote="owner",
            polarity="positive", commitment="asserted",
        ),
    )
    return ProviderSemanticProposal(
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
        facts=facts[:group_count],
        abstained=False,
    )


@pytest.mark.parametrize("root", ("direct", "factory", "filesystem", "hermes"))
def test_all_normal_roots_compose_same_graph_host_bundle(
    root: str, tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    normalization, graph = _builders()
    common = {
        "host_bootstrap_capability": _built_in_local_capability(),
        "host_bootstrap_material_verifier": DeterministicTestHostBootstrapMaterialVerifier(),
        "source_normalization_host_bundle_builder": normalization,
        "bootstrap_graph_host_bundle_builder": graph,
    }
    service: ProviderMemoryService
    if root == "direct":
        service = _provider_service(**common)
    elif root == "factory":
        service = build_provider_memory_service_from_env(**common)
    elif root == "filesystem":
        service = build_filesystem_provider(tmp_path / "memorii", **common)
    else:
        provider = _hermes_provider(**common)
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
        service = _provider_service(**common)
    elif root == "factory":
        service = build_provider_memory_service_from_env(**common)
    elif root == "filesystem":
        service = build_filesystem_provider(tmp_path / "builtin-graph", **common)
    else:
        service = _hermes_provider(
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
    proposal = _graph_fact_proposal()
    normalization, _calls = _v3_normalization_host_builder(proposal=proposal)
    common = {
        "now_provider": lambda: TEST_NOW,
        "host_bootstrap_capability": _built_in_local_capability(),
        "host_bootstrap_material_verifier": DeterministicTestHostBootstrapMaterialVerifier(),
        "source_normalization_host_bundle_builder": normalization,
    }
    if root == "direct":
        service = _provider_service(**common)
    elif root == "factory":
        service = build_provider_memory_service_from_env(**common)
    elif root == "filesystem":
        service = build_filesystem_provider(tmp_path / "builtin-native-graph", **common)
    else:
        service = _hermes_provider(service=_provider_service(**common))._service
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
    proposal = _graph_fact_proposal()
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
        service = _provider_service(**common)
    elif root == "factory":
        service = build_provider_memory_service_from_env(**common)
    elif root == "filesystem":
        service = build_filesystem_provider(tmp_path / "memorii-executable", **common)
    else:
        service = _hermes_provider(service=_provider_service(**common))._service

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
    service = _provider_service(
        # The M4 built-in capability always wires its own graph host, so a
        # graph-authority-less composition is built explicitly: the removed
        # builder installs a scenario host bundle with no authority provider,
        # and the run must fail closed at the graph boundary before effects.
        bootstrap_graph_host_bundle_builder=_RemovedBootstrapGraphHostBundleBuilder(),
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
    proposal = _graph_fact_proposal()
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
            return _hermes_provider(
                service=_provider_service(memory_plane=memory_plane, **common)
            )._service, lane_calls
        return _provider_service(memory_plane=memory_plane, **common), lane_calls

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
    proposal = _graph_fact_proposal()
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
        service = _hermes_provider(
            service=_provider_service(memory_plane=memory_plane, **common)
        )._service
    else:
        service = _provider_service(memory_plane=memory_plane, **common)
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


@pytest.mark.parametrize("root", ("direct", "factory", "filesystem", "hermes"))
@pytest.mark.parametrize("scenario", tuple(_GRAPH_SCENARIO_BEHAVIOR))
def test_graph_race_reopens_in_an_independent_jsonl_process(
    root: str, scenario: str, tmp_path,
) -> None:
    behavior = _GRAPH_SCENARIO_BEHAVIOR[scenario]
    storage_root = tmp_path / scenario / root
    environment = dict(os.environ)
    environment["PYTHONPATH"] = "memorii"
    outputs: list[dict[str, object]] = []
    for phase in ("first", "reopen"):
        output = tmp_path / f"{scenario}-{phase}.json"
        subprocess.run(
            (
                sys.executable,
                "-m",
                "tests.fixtures.semantic_ingestion.bootstrap_graph_v3_process_runner",
                str(storage_root),
                root,
                scenario,
                phase,
                str(output),
            ),
            cwd=Path(__file__).parents[5],
            env=environment,
            check=True,
            timeout=180,
        )
        outputs.append(json.loads(output.read_text(encoding="utf-8")))

    first, reopened = outputs
    if behavior == "scope_revoked":
        assert first["semantic_ingestion"] == "graph_transaction_authority_unavailable"
        assert first["cas_attempts"] == 1
        assert first["graph_effects"] == 0
    elif behavior in {
        "unrelated_conflict", "normal_success", "lease_renewed", "lease_reclaimed",
        "mixed_version", "rollback",
    }:
        assert first["semantic_ingestion"] == "source_only"
        assert first["cas_attempts"] == 1
        assert first["graph_effects"] == 1
    elif behavior in {
        "durable_retry", "coordinator_removed", "authority_omitted",
        "writer_changed", "writer_unavailable",
    }:
        assert first["semantic_ingestion"] == "graph_transaction_authority_unavailable"
        assert first["unavailable_calls"] == (1 if behavior == "durable_retry" else 0)
        assert first["graph_effects"] == 0
    elif behavior == "resolved_conflict":
        assert first["semantic_ingestion"] == "source_only"
        assert first["conflict_calls"] == 2
        assert first["graph_effects"] == 1
    elif behavior == "exhausted_conflict":
        assert first["semantic_ingestion"] == "source_only"
        assert first["exhausted_conflict_calls"] == 2
        assert first["graph_effects"] == 1
    elif behavior == "lost_ack":
        assert first["semantic_ingestion"] == "source_only"
        assert first["partial_conflict_calls"] == 0
        assert first["graph_effects"] == 1
    else:
        assert first["semantic_ingestion"] == "source_only"
        assert first["partial_conflict_calls"] == 4
        assert first["graph_effects"] == 3
    if behavior == "lost_ack":
        assert first["lost_ack_injected"] is True
    if behavior == "terminal_locator":
        assert first["terminal_locator_removed"] == 1
    if behavior == "terminal_locator":
        assert reopened["semantic_ingestion"] != "source_only"
        assert reopened["scan_calls"] == 0
    elif behavior == "mixed_version":
        assert reopened["semantic_ingestion"] in {
            "graph_transaction_authority_unavailable",
            "source_alignment_authority_unavailable",
        }
    elif behavior == "rollback":
        assert reopened["semantic_ingestion"] == "graph_transaction_authority_unavailable"
        assert reopened["prior_terminal_semantic_ingestion"] == "source_only"
    elif behavior in {"writer_changed", "writer_unavailable"}:
        assert reopened["semantic_ingestion"] in {
            "graph_transaction_authority_unavailable", "source_only",
            "source_alignment_authority_unavailable",
        }
    else:
        assert reopened["semantic_ingestion"] == first["semantic_ingestion"]
    assert reopened["cas_attempts"] == 0
    assert reopened["graph_effects"] == 0
    assert reopened["unavailable_calls"] == 0
    assert reopened["conflict_calls"] == 0
    assert reopened["partial_conflict_calls"] == 0
    assert reopened["exhausted_conflict_calls"] == 0
    if behavior != "rollback":
        assert all(value == 0 for value in reopened["lane_calls"].values())
    if behavior == "mixed_version":
        assert first["mixed_version_fixture_mutations"] > 0
    if behavior in {"reused_committed", "reused_final", "reused_unfinished"}:
        evidence = first["successor_evidence"]
        successor = next(item for item in evidence["attempts"] if item["attempt_index"] == 1)
        assert successor["trigger"] == "related_version_conflict"
        assert evidence["lineages"]
        assert evidence["pre_execution"]
        authorities = successor["authority"]["group_member_authorities"]
        expected_kind = behavior
        assert any(item["kind"] == expected_kind for item in authorities)
        # The retained arm is carried through both the successor lineage and
        # the pre-execution identity closure; it is not a selector alias.
        retained = next(item for item in authorities if item["kind"] == expected_kind)
        retained_group_id = retained["transaction_group_id"]
        latest = dict(evidence["lineages"][-1]["latest_entry_by_group"])
        identities = dict(evidence["pre_execution"][-1]["identity_by_group"])
        assert retained_group_id in latest
        assert retained_group_id in identities


@pytest.mark.parametrize("root", ("direct", "factory", "filesystem", "hermes"))
@pytest.mark.parametrize("scenario", tuple(_GRAPH_SCENARIO_BEHAVIOR))
def test_graph_scenario_replays_without_effects_in_memory(
    root: str, scenario: str, tmp_path,
) -> None:
    behavior = _GRAPH_SCENARIO_BEHAVIOR[scenario]
    proposal = _graph_fact_proposal(
        3
        if behavior in {
            "partial_commit", "reused_committed", "reused_final", "reused_unfinished",
        }
        else 1
    )
    normalization, lane_calls = _v3_normalization_host_builder(proposal=proposal)
    successful_calls: list[str] = []
    unavailable_calls: list[str] = []
    conflict_calls: list[str] = []
    partial_conflict_calls: list[str] = []
    exhausted_conflict_calls: list[str] = []
    clock = [TEST_NOW]
    class UnavailableAuthorityProvider:
        def acquire(self, **_kwargs: object) -> None:
            return None

    def before_epoch_created(atomic_store: object) -> None:
        if behavior == "writer_changed":
            original = atomic_store._writers.commit_binding
            atomic_store._writers.commit_binding = lambda record: original(record).model_copy(
                update={"admission_digest": "f" * 64}
            )
        elif behavior == "writer_unavailable":
            def reject(_binding: object) -> None:
                raise SemanticWriterAdmissionError("writer authority is unavailable")
            atomic_store._writers.require_current = reject

    def after_epoch_created(atomic_store: object, request: object, epoch: object) -> object:
        if behavior not in {
            "lease_renewed", "lease_reclaimed", "writer_changed", "writer_unavailable"
        }:
            return epoch
        fence = request.graph_authority.operation_fence_binding
        control = atomic_store.get_operation(fence)
        if behavior in {"writer_changed", "writer_unavailable"}:
            return epoch
        if behavior == "lease_reclaimed":
            clock[0] = control.lease.expires_at + timedelta(seconds=1)
            atomic_store.acquire_lease(
                operation_fence=fence,
                writer_binding=control.writer_binding,
                execution_token="graph-reclaimed-execution",
                owner_id="graph-reclaimed-owner",
                duration=timedelta(minutes=10),
            )
        else:
            atomic_store.renew_lease(
                operation_fence=fence,
                writer_binding=control.writer_binding,
                lease=control.lease,
                duration=timedelta(minutes=10),
            )
        refreshed = AtomicStoreBootstrapGraphControlEpochRepositoryV3(
            atomic_store=atomic_store
        ).refresh_current(request=request, current_epoch=epoch).epoch
        return refreshed

    provider = DeterministicBootstrapGraphAuthorityProviderV3(
        successful_calls=successful_calls,
            unavailable_calls=unavailable_calls if behavior == "durable_retry" else None,
            conflict_calls=conflict_calls if behavior == "resolved_conflict" else None,
        partial_conflict_calls=(
                partial_conflict_calls
                if behavior in {
                    "partial_commit", "reused_committed", "reused_final", "reused_unfinished",
                }
                else None
        ),
        exhausted_conflict_calls=(
                exhausted_conflict_calls if behavior == "exhausted_conflict" else None
        ),
        after_epoch_created=after_epoch_created,
        before_epoch_created=before_epoch_created,
    )
    memory_plane = MemoryPlaneService()
    common = {
        "now_provider": lambda: clock[0],
        "host_bootstrap_capability": _built_in_local_capability(),
        "host_bootstrap_material_verifier": DeterministicTestHostBootstrapMaterialVerifier(),
        "source_normalization_host_bundle_builder": normalization,
    }
    if behavior == "coordinator_removed":
        common["bootstrap_graph_host_bundle_builder"] = (
            _RemovedBootstrapGraphHostBundleBuilder()
        )
    else:
        common["bootstrap_graph_host_bundle_builder"] = BootstrapGraphHostBundleBuilder(
            authority_provider=(
                UnavailableAuthorityProvider()
                    if behavior == "authority_omitted"
                else provider
            )
        )
    if root == "filesystem":
        service = build_filesystem_provider(
            tmp_path / "memory-replay", memory_plane=memory_plane, **common
        )
    elif root == "factory":
        service = build_provider_memory_service_from_env(
            memory_plane=memory_plane, **common
        )
    elif root == "hermes":
        service = _hermes_provider(
            service=_provider_service(memory_plane=memory_plane, **common)
        )._service
    else:
        service = _provider_service(memory_plane=memory_plane, **common)

    operation_id = f"memory-{scenario}-{root}"
    first = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id=operation_id,
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    if behavior in {"writer_changed", "writer_unavailable"}:
        assert first.blocked_reasons["semantic_ingestion"] == "graph_transaction_authority_unavailable"
        assert successful_calls == []
    if behavior in {"lease_renewed", "lease_reclaimed"}:
        assert len(successful_calls) == 1
        assert first.blocked_reasons["semantic_ingestion"] == "source_only"
    counts = (
        len(successful_calls), len(unavailable_calls), len(conflict_calls),
        len(partial_conflict_calls), len(exhausted_conflict_calls),
    )
    lanes = dict(lane_calls)
    if behavior == "lease_reclaimed":
        clock[0] = TEST_NOW
    if behavior == "mixed_version":
        members = service._memory_plane.list_records(
            source_kind="semantic_ingestion_bootstrap_graph_v3_member"
        )
        assert members
        class CorruptionPolicy:
            def validate(self, *_args: object, **_kwargs: object) -> None:
                return None
        service._memory_plane._records.install_governed_write_policy(CorruptionPolicy())
        for member in members:
            content = dict(member.content)
            content["member"] = {"schema_version": 2, "kind": "legacy_graph_member"}
            service._memory_plane.upsert_record(
                member.model_copy(update={"content": content})
            )
        locators = service._memory_plane.list_records(
            source_kind="semantic_ingestion_bootstrap_graph_v3_terminal_locator"
        )
        assert locators
        for locator in locators:
            content = dict(locator.content)
            content["reload"] = {"schema_version": 2, "kind": "legacy_graph_reload"}
            service._memory_plane.upsert_record(
                locator.model_copy(update={"content": content})
            )
    if behavior == "rollback":
        graph_bundle = (
            service._provider_ingestion._semantic_runtime.bootstrap_graph_host_bundle
        )
        assert graph_bundle is not None
        object.__setattr__(graph_bundle, "promotion_enabled", False)
    repeated_operation_id = (
        f"{operation_id}-after-rollback" if behavior == "rollback" else operation_id
    )
    repeated = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id=repeated_operation_id,
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    if behavior == "mixed_version":
        assert repeated.blocked_reasons["semantic_ingestion"] in {
            "graph_transaction_authority_unavailable",
            "source_alignment_authority_unavailable",
        }
    elif behavior in {"writer_changed", "writer_unavailable"}:
        assert repeated.blocked_reasons["semantic_ingestion"] in {
            "graph_transaction_authority_unavailable", "source_only",
            "source_alignment_authority_unavailable",
        }
    elif behavior == "rollback":
        assert repeated.blocked_reasons["semantic_ingestion"] == (
            "graph_transaction_authority_unavailable"
        )
        assert len(successful_calls) == counts[0]
        assert service._memory_plane.list_records(
            source_kind="semantic_ingestion_bootstrap_graph_v3_terminal_locator"
        )
    else:
        assert repeated.blocked_reasons["semantic_ingestion"] == first.blocked_reasons["semantic_ingestion"]
    assert (
        len(successful_calls), len(unavailable_calls), len(conflict_calls),
        len(partial_conflict_calls), len(exhausted_conflict_calls),
    ) == counts
    if behavior != "rollback":
        assert lane_calls == lanes


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
    proposal = _graph_fact_proposal(group_count)
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
    service = _provider_service(
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
    service = _provider_service(
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
