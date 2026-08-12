"""Recovery proof for failures that occur after a graph effect can commit."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from memorii.core.filesystem_storage.bundle import build_filesystem_provider
from memorii.core.memory_evolution.atomic_store import (
    BootstrapWriterHandoffMarkerV3,
    PreplanningStoreError,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.core.provider.factory import build_provider_memory_service_from_env
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.semantic_ingestion.bootstrap_graph_host import BootstrapGraphHostBundleBuilder
from memorii.core.semantic_ingestion.contracts import (
    ProviderEntityObject,
    ProviderFact,
    ProviderMention,
    ProviderSemanticProposal,
)
from memorii.integrations.hermes_provider import HermesMemoryProvider
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


def _graph_service(
    *, storage: Path | None, executor_calls: list[str], built_in: bool = False,
    root: str = "direct", filesystem_root: Path | None = None,
) -> tuple[ProviderMemoryService, MemoryPlaneService]:
    builder, _ = _v3_normalization_host_builder(
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
            facts=(
                ProviderFact(
                    local_id="owner", predicate_id="owner_is",
                    subject_entity_ref="atlas",
                    object=ProviderEntityObject(entity_ref="bob"),
                    assertion_quote="Atlas owner is Bob.",
                    predicate_anchor_quote="owner", polarity="positive",
                    commitment="asserted",
                ),
            ),
            abstained=False,
        )
    )
    plane = MemoryPlaneService(
        record_store=None if storage is None else JsonlMemoryPlaneStore(storage)
    )
    kwargs = {}
    if not built_in:
        kwargs["bootstrap_graph_host_bundle_builder"] = BootstrapGraphHostBundleBuilder(
            authority_provider=DeterministicBootstrapGraphAuthorityProviderV3(
                successful_calls=executor_calls
            )
        )
    common = dict(
        memory_plane=plane,
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(
            scenario_test=not built_in
        ),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=builder,
        **kwargs,
    )
    if not built_in:
        return ProviderMemoryService._from_scenario_test_host(**common), plane
    if root == "factory":
        return build_provider_memory_service_from_env(**common), plane
    if root == "filesystem":
        assert filesystem_root is not None
        return build_filesystem_provider(
            filesystem_root, **common
        ), plane
    if root == "hermes":
        return HermesMemoryProvider(service=ProviderMemoryService(**common))._service, plane
    return ProviderMemoryService(**common), plane


def _sync(service: ProviderMemoryService, *, operation_id: str):
    return service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id=operation_id,
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )


def _durable_graph_records(plane: MemoryPlaneService) -> tuple[tuple[str, bytes], ...]:
    """Compare stable durable JSON bytes, normalizing tuple/list reload shapes."""
    return tuple(sorted(
        (
            record.memory_id,
            json.dumps(
                record.content, sort_keys=True, separators=(",", ":")
            ).encode("utf-8"),
        )
        for record in plane.list_records()
        if record.source_kind.startswith("semantic_ingestion_bootstrap_graph_v3_")
    ))


def _terminal_reload_identities(plane: MemoryPlaneService) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(
        (record.memory_id, record.content["reload"]["reload_digest"])
        for record in plane.list_records(
            source_kind="semantic_ingestion_bootstrap_graph_v3_terminal_locator"
        )
    ))


@pytest.mark.parametrize("persistent", (False, True))
def test_group_effect_checkpoint_ack_failure_publishes_reloaded_retry_without_reexecution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, persistent: bool,
) -> None:
    storage = tmp_path / "jsonl" if persistent else None
    calls: list[str] = []
    service, plane = _graph_service(storage=storage, executor_calls=calls)
    atomic = service._semantic_atomic_store
    original = atomic.checkpoint_bootstrap_graph_transaction_v3
    injected = False

    def fail_before_group_checkpoint(*, request, **kwargs):
        nonlocal injected
        if request.kind == "bootstrap_graph_group_result_checkpoint" and not injected:
            injected = True
            raise PreplanningStoreError("injected group checkpoint acknowledgement failure")
        return original(request=request, **kwargs)

    monkeypatch.setattr(atomic, "checkpoint_bootstrap_graph_transaction_v3", fail_before_group_checkpoint)
    first = _sync(service, operation_id="post-effect-group-checkpoint")

    assert injected
    assert first.blocked_reasons["semantic_ingestion"] == "graph_transaction_authority_unavailable"
    assert len(calls) == 1
    retry_records = plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_retry_index"
    )
    assert len(retry_records) == 1
    checkpoint_members = [
        record.content["member"]
        for record in plane.list_records(
            source_kind="semantic_ingestion_bootstrap_graph_v3_member"
        )
    ]
    assert sum(
        member["kind"] == "transaction_group_result"
        for member in checkpoint_members
    ) == 1
    assert sum(
        member["kind"] == "bootstrap_graph_retry_progress"
        for member in checkpoint_members
    ) == 1
    before_reopen = _durable_graph_records(plane)
    recovery_index = plane.list_records(
        source_kind="semantic_ingestion_bootstrap_v3_recovery_index"
    )
    assert len(recovery_index) == 1
    assert service._semantic_atomic_store.recover_bootstrap_v3_source_normalization(
        recovery_key_digest=recovery_index[0].content["recovery_key_digest"]
    ) is not None

    reopened_calls: list[str] = []
    reopened, reopened_plane = (
        _graph_service(storage=storage, executor_calls=reopened_calls)
        if persistent
        else (service, plane)
    )
    repeated = _sync(reopened, operation_id="post-effect-group-checkpoint")

    assert repeated == first
    assert reopened_calls == []
    assert _durable_graph_records(reopened_plane) == before_reopen


@pytest.mark.parametrize("persistent", (False, True))
def test_terminal_cas_ack_failure_reloads_finalized_state_without_duplicate_effect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, persistent: bool,
) -> None:
    storage = tmp_path / "jsonl" if persistent else None
    calls: list[str] = []
    service, plane = _graph_service(storage=storage, executor_calls=calls)
    atomic = service._semantic_atomic_store
    original = atomic.persist_bootstrap_graph_terminal_v3
    injected = False

    def fail_after_terminal_cas(*, request):
        nonlocal injected
        reload = original(request=request)
        if not injected:
            injected = True
            raise PreplanningStoreError("injected terminal acknowledgement failure")
        return reload

    monkeypatch.setattr(atomic, "persist_bootstrap_graph_terminal_v3", fail_after_terminal_cas)
    first = _sync(service, operation_id="post-effect-terminal-cas")

    assert injected
    assert first.blocked_reasons["semantic_ingestion"] == "source_only"
    assert len(calls) == 1
    assert len(plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_terminal_locator"
    )) == 3
    before_reopen = _terminal_reload_identities(plane)

    reopened_calls: list[str] = []
    reopened, reopened_plane = (
        _graph_service(storage=storage, executor_calls=reopened_calls)
        if persistent
        else (service, plane)
    )
    repeated = _sync(reopened, operation_id="post-effect-terminal-cas")

    assert repeated == first
    assert reopened_calls == []
    assert _terminal_reload_identities(reopened_plane) == before_reopen


@pytest.mark.parametrize("persistent", (False, True))
@pytest.mark.parametrize("root", ("direct", "factory", "filesystem", "hermes"))
def test_builtin_terminal_ack_loss_reloads_exact_terminal_without_duplicate_group(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, root: str, persistent: bool,
) -> None:
    storage = tmp_path / root / "builtin-terminal-ack" if persistent else None
    filesystem_root = tmp_path / root / "filesystem-terminal-ack"
    service, plane = _graph_service(
        storage=storage, executor_calls=[], built_in=True, root=root,
        filesystem_root=filesystem_root,
    )
    atomic = service._semantic_atomic_store
    original = atomic.persist_bootstrap_graph_terminal_v3
    injected = False

    def fail_after_terminal_cas(*, request):
        nonlocal injected
        reload = original(request=request)
        if not injected:
            injected = True
            raise PreplanningStoreError("injected built-in terminal acknowledgement loss")
        return reload

    monkeypatch.setattr(
        atomic, "persist_bootstrap_graph_terminal_v3", fail_after_terminal_cas
    )
    first = _sync(service, operation_id="builtin-terminal-ack")
    assert injected
    assert first.blocked_reasons["semantic_ingestion"] == "source_only"
    before_terminal = _terminal_reload_identities(plane)
    before_group = tuple(
        record.memory_id
        for record in plane.list_records(
            source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
        )
    )
    assert len(before_terminal) == 3
    assert len(before_group) == 1

    reopened, reopened_plane = (
        _graph_service(
            storage=storage, executor_calls=[], built_in=True, root=root,
            filesystem_root=filesystem_root,
        )
        if persistent
        else (service, plane)
    )
    repeated = _sync(reopened, operation_id="builtin-terminal-ack")

    assert repeated == first
    assert _terminal_reload_identities(reopened_plane) == before_terminal
    assert tuple(
        record.memory_id
        for record in reopened_plane.list_records(
            source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
        )
    ) == before_group


@pytest.mark.parametrize("persistent", (False, True))
@pytest.mark.parametrize("root", ("direct", "factory", "filesystem", "hermes"))
def test_builtin_recovery_preserves_group_identity_after_lease_reclaim(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, persistent: bool, root: str,
) -> None:
    """The default provider must recover the predecessor request after takeover."""
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
                subject_entity_ref="atlas",
                object=ProviderEntityObject(entity_ref="bob"),
                assertion_quote="Atlas owner is Bob.",
                predicate_anchor_quote="owner", polarity="positive",
                commitment="asserted",
            ),),
            abstained=False,
        )
    builder, _ = _v3_normalization_host_builder(proposal=proposal)
    clock = [TEST_NOW]
    storage = tmp_path / "builtin-lease-reclaim" if persistent else None
    plane = MemoryPlaneService(
        record_store=None if storage is None else JsonlMemoryPlaneStore(storage)
    )
    common = dict(
        memory_plane=plane,
        now_provider=lambda: clock[0],
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=(
            DeterministicTestHostBootstrapMaterialVerifier()
        ),
        source_normalization_host_bundle_builder=builder,
    )
    if root == "factory":
        service = build_provider_memory_service_from_env(**common)
    elif root == "filesystem":
        service = build_filesystem_provider(
            tmp_path / root / "filesystem-reclaim", **common
        )
    elif root == "hermes":
        service = HermesMemoryProvider(
            service=ProviderMemoryService(**common)
        )._service
    else:
        service = ProviderMemoryService(**common)
    monkeypatch.setattr(
        service._provider_ingestion,
        "_persist_semantic_terminal",
        lambda *_args, **_kwargs: None,
    )
    atomic = service._semantic_atomic_store
    original_checkpoint = atomic.checkpoint_bootstrap_graph_transaction_v3
    injected = False

    def fail_group_checkpoint_once(*, request, **kwargs):
        nonlocal injected
        if request.kind == "bootstrap_graph_group_result_checkpoint" and not injected:
            injected = True
            raise PreplanningStoreError("injected group checkpoint acknowledgement failure")
        return original_checkpoint(request=request, **kwargs)

    monkeypatch.setattr(
        atomic,
        "checkpoint_bootstrap_graph_transaction_v3",
        fail_group_checkpoint_once,
    )
    first = _sync(service, operation_id="builtin-lease-reclaim")
    assert injected
    assert first.blocked_reasons["semantic_ingestion"] == (
        "graph_transaction_authority_unavailable"
    )
    primary_before = plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    )
    authority_before = plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_pre_epoch_authority"
    )
    assert len(primary_before) == len(authority_before) == 1

    marker = BootstrapWriterHandoffMarkerV3.model_validate(
        plane.list_records(
            source_kind="semantic_ingestion_bootstrap_handoff_marker"
        )[0].content["marker"]
    )
    control = atomic.get_operation(marker.operation_fence_binding)
    assert control.lease is not None
    clock[0] = control.lease.expires_at + timedelta(seconds=1)
    atomic.acquire_lease(
        operation_fence=marker.operation_fence_binding,
        writer_binding=control.writer_binding,
        execution_token="builtin-reclaimed-execution",
        owner_id="builtin-reclaimed-owner",
        duration=timedelta(minutes=10),
    )
    # Admission evidence is content-addressed with its original host clock.
    # The store already retained the reclaimed lease issued at the later time.
    clock[0] = TEST_NOW

    repeated_service = service
    repeated_plane = plane
    if persistent:
        reopened_builder, _ = _v3_normalization_host_builder(proposal=proposal)
        repeated_plane = MemoryPlaneService(
            record_store=JsonlMemoryPlaneStore(storage)
        )
        reopened_common = dict(
            memory_plane=repeated_plane,
            now_provider=lambda: clock[0],
            host_bootstrap_capability=_built_in_local_capability(),
            host_bootstrap_material_verifier=(
                DeterministicTestHostBootstrapMaterialVerifier()
            ),
            source_normalization_host_bundle_builder=reopened_builder,
        )
        if root == "factory":
            repeated_service = build_provider_memory_service_from_env(
                **reopened_common
            )
        elif root == "filesystem":
            repeated_service = build_filesystem_provider(
                tmp_path / root / "filesystem-reclaim", **reopened_common
            )
        elif root == "hermes":
            repeated_service = HermesMemoryProvider(
                service=ProviderMemoryService(**reopened_common)
            )._service
        else:
            repeated_service = ProviderMemoryService(**reopened_common)
        monkeypatch.setattr(
            repeated_service._provider_ingestion,
            "_persist_semantic_terminal",
            lambda *_args, **_kwargs: None,
        )
    repeated = _sync(repeated_service, operation_id="builtin-lease-reclaim")
    assert repeated == first
    primary_after = repeated_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    )
    authority_after = repeated_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_pre_epoch_authority"
    )
    assert tuple(item.memory_id for item in primary_after) == tuple(
        item.memory_id for item in primary_before
    )
    assert tuple(item.memory_id for item in authority_after) == tuple(
        item.memory_id for item in authority_before
    )
