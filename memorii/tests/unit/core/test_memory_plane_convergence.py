from datetime import UTC, datetime

from memorii.core.execution import RuntimeStepService
from memorii.core.execution.service import InMemoryMemoryPlane
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.provider.models import ProviderOperation, ProviderStoredRecord
from memorii.core.provider.service import ProviderMemoryService
from memorii.domain.enums import ExecutionNodeStatus, ExecutionNodeType, MemoryDomain
from memorii.domain.execution_graph.nodes import ExecutionNode
from memorii.stores.event_log import InMemoryEventLogStore
from memorii.stores.execution_graph import InMemoryExecutionGraphStore
from memorii.stores.overlays import InMemoryOverlayStore
from memorii.stores.solver_graph import InMemorySolverGraphStore


def _build_runtime(shared_plane: MemoryPlaneService) -> RuntimeStepService:
    execution_store = InMemoryExecutionGraphStore()
    execution_store.upsert_node(
        "task:compat",
        ExecutionNode(
            id="exec:compat",
            type=ExecutionNodeType.WORK_ITEM,
            title="compat",
            description="compat",
            status=ExecutionNodeStatus.RUNNING,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
    )
    return RuntimeStepService(
        execution_store=execution_store,
        solver_store=InMemorySolverGraphStore(),
        overlay_store=InMemoryOverlayStore(),
        event_log_store=InMemoryEventLogStore(),
        memory_plane=InMemoryMemoryPlane(shared_plane),
    )


def test_provider_and_runtime_compat_write_share_blocking_and_candidate_staging() -> None:
    shared_plane = MemoryPlaneService()
    provider = ProviderMemoryService(memory_plane=shared_plane)
    runtime = _build_runtime(shared_plane)

    provider_result = provider.apply_memory_write(
        operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
        content="timeout is 30s",
        action="upsert",
        target="memory",
        task_id="task:compat",
        session_id="session:compat",
        user_id="user:compat",
    )
    runtime_result = runtime.apply_provider_compat_write(
        operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
        content="timeout is 30s",
        action="upsert",
        target="memory",
        task_id="task:compat",
        session_id="session:compat",
        user_id="user:compat",
    )

    assert provider_result.allowed_candidate_domains == runtime_result.allowed_candidate_domains
    assert provider_result.blocked_commit_domains == runtime_result.blocked_commit_domains
    assert set(provider_result.blocked_domains) == set(runtime_result.blocked_domains)


def test_provider_prefetch_trace_still_uses_bm25_from_canonical_core() -> None:
    shared_plane = MemoryPlaneService()
    service = ProviderMemoryService(memory_plane=shared_plane)
    now = datetime(2026, 1, 15, tzinfo=UTC)
    service.seed_committed_record(
        ProviderStoredRecord(
            memory_id="sem:concise",
            domain=MemoryDomain.SEMANTIC,
            text="Timeout default is 30 seconds.",
            status="committed",
            task_id="task:bm25",
            timestamp=now,
        )
    )

    service.prefetch("timeout default config", task_id="task:bm25")
    trace = service.last_prefetch_trace()
    assert trace is not None
    assert trace.lexical_method == "bm25"
