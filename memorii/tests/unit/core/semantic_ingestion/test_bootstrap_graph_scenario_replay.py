"""In-memory scenario replay proof across graph scenarios."""



from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import pytest
from memorii.core.memory_evolution.writer_admission import SemanticWriterAdmissionError
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.provider.models import ProviderOperation
from memorii.core.semantic_ingestion.bootstrap_graph_host import (
    BootstrapGraphHostBundle,
    BootstrapGraphHostBundleBuilder,
)
from memorii.core.semantic_ingestion.bootstrap_graph_repository import (
    AtomicStoreBootstrapGraphControlEpochRepositoryV3,
)
from memorii.core.semantic_ingestion.contracts import (
    BootstrapGraphPlanAtomicWriteRequestV3,
    decode_bootstrap_graph_atomic_member_payload_v3,
)
from tests.fixtures.semantic_ingestion.bootstrap_graph_v3_fixture import (
    DeterministicBootstrapGraphAuthorityProviderV3,
)
from tests.unit.core.semantic_ingestion.bootstrap_graph_production_roots_support import (
    GRAPH_SCENARIO_BEHAVIOR,
    RemovedBootstrapGraphHostBundleBuilder,
    build_filesystem_provider,
    build_provider_memory_service_from_env,
    graph_fact_proposal,
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


def _progress_evidence(service: object) -> tuple[dict[str, object], ...]:
    """Read only sealed native progress bytes from V3 manifests."""
    evidence = []
    for record in service._memory_plane.list_records(  # type: ignore[attr-defined]
        source_kind="semantic_ingestion_bootstrap_graph_v3_manifest"
    ):
        if "request" not in record.content:
            continue
        request = BootstrapGraphPlanAtomicWriteRequestV3.model_validate_json(
            json.dumps(record.content["request"])
        )
        member = next(
            (item for item in request.members if item.member_id == "source-progress"),
            None,
        )
        if member is None:
            continue
        progress = decode_bootstrap_graph_atomic_member_payload_v3(
            kind=member.kind, raw=member.canonical_payload,
        )
        evidence.append({
            "kind": progress["kind"],
            "progress_digest": progress["progress_digest"],
            "plan_member_payload_digest": progress["plan_reference"]["member_payload_digest"],
            "replay_member_payload_digest": progress["replay_bundle_reference"]["member_payload_digest"],
        })
    return tuple(evidence)


def _assert_source_progress_evidence(scenario: str, service: object) -> None:
    evidence = _progress_evidence(service)
    expected = ("plan_published", "attempt_published", "planned") * (
        3 if scenario == "source_progress_related_conflict" else 1
    )
    assert tuple(item["kind"] for item in evidence) == expected
    for offset in range(0, len(evidence), 3):
        generation = evidence[offset:offset + 3]
        assert len({item["plan_member_payload_digest"] for item in generation}) == 1
        assert len({item["replay_member_payload_digest"] for item in generation}) == 1
        assert all(isinstance(item["progress_digest"], str) for item in generation)


@pytest.mark.parametrize("root", ("direct", "factory", "filesystem", "hermes"))
@pytest.mark.parametrize("scenario", tuple(GRAPH_SCENARIO_BEHAVIOR))
def test_graph_scenario_replays_without_effects_in_memory(
    root: str, scenario: str, tmp_path,
) -> None:
    behavior = GRAPH_SCENARIO_BEHAVIOR[scenario]
    proposal = graph_fact_proposal(
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
    cas_attempts: list[str] = []
    paused = Event()
    release_first = Event()
    second_ready = Event()
    release_second = Event()
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

    def pause_first_group(_group_id: str) -> str | None:
        if not paused.is_set():
            paused.set()
            assert release_first.wait(timeout=300), "test did not release A"
            return "first"
        if not second_ready.is_set():
            second_ready.set()
            assert release_second.wait(timeout=300), "test did not release B"
            return "second"
        return None

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
        cas_attempts=cas_attempts,
        unavailable_calls=unavailable_calls if behavior == "durable_retry" else None,
        conflict_calls=(
            conflict_calls
            if behavior in {"resolved_conflict", "reused_unfinished"}
            else None
        ),
        partial_conflict_calls=(
                partial_conflict_calls
                if behavior in {
                    "partial_commit", "reused_committed", "reused_final",
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
    if behavior == "real_related_conflict":
        pass
    elif behavior == "coordinator_removed":
        common["bootstrap_graph_host_bundle_builder"] = (
            RemovedBootstrapGraphHostBundleBuilder()
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
        service = hermes_provider(
            service=provider_service(memory_plane=memory_plane, **common)
        )._service
    else:
        service = provider_service(memory_plane=memory_plane, **common)

    if behavior == "real_related_conflict":
        graph_bundle = (
            service._provider_ingestion._semantic_runtime.bootstrap_graph_host_bundle
        )
        assert type(graph_bundle) is BootstrapGraphHostBundle
        assert not hasattr(graph_bundle, "authority_provider")
        atomic = service._semantic_atomic_store
        real_group_commit = atomic.commit_or_reload_bootstrap_graph_group_v3

        def scheduled_group_commit(*, request):
            cas_attempts.append(request.transaction_group_id)
            pause_first_group(request.transaction_group_id)
            return real_group_commit(request=request)

        atomic.commit_or_reload_bootstrap_graph_group_v3 = scheduled_group_commit

    operation_id = f"memory-{scenario}-{root}"
    if behavior == "real_related_conflict":
        with ThreadPoolExecutor(max_workers=2) as executor:
            pending = executor.submit(
                service.sync_event,
                operation=ProviderOperation.CHAT_USER_TURN,
                content="Atlas owner is Bob.", operation_id=operation_id,
                task_id="task:one", user_id="user:alice",
                authenticated_host_ingress=_host_ingress(),
            )
            try:
                if not paused.wait(timeout=300):
                    release_first.set()
                    early = pending.result(timeout=300)
                    raise AssertionError(
                        "A did not reach group CAS: "
                        f"blocked={early.blocked_reasons!r}, cas_attempts={cas_attempts!r}"
                    )
                competing = executor.submit(
                    service.sync_event,
                    operation=ProviderOperation.CHAT_USER_TURN,
                    content="Atlas owner is Bob.",
                    operation_id=f"{operation_id}-winner",
                    task_id="task:one",
                    user_id="user:bob",
                    authenticated_host_ingress=_host_ingress(),
                )
                if not second_ready.wait(timeout=300):
                    release_first.set()
                    early_second = competing.result(timeout=300)
                    early_first = pending.result(timeout=300)
                    raise AssertionError(
                        "B did not reach group CAS: "
                        f"first={early_first.blocked_reasons!r}, "
                        f"second={early_second.blocked_reasons!r}, "
                        f"cas_attempts={cas_attempts!r}"
                    )
                release_second.set()
                winner = competing.result(timeout=300)
                release_first.set()
                first = pending.result(timeout=300)
            finally:
                release_second.set()
                release_first.set()
        assert winner.blocked_reasons["semantic_ingestion"] == "source_only"
        assert len(cas_attempts) == 3
        assert len(memory_plane.list_records(
            source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
        )) == 2
        assert len(memory_plane.list_records(
            source_kind="semantic_ingestion_admission_index"
        )) == 2
    else:
        first = service.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN,
            content="Atlas owner is Bob.", operation_id=operation_id,
            task_id="task:one", user_id="user:alice",
            authenticated_host_ingress=_host_ingress(),
        )
    if scenario.startswith("source_progress_"):
        _assert_source_progress_evidence(scenario, service)
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
