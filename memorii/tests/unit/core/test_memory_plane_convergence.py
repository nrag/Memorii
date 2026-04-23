from datetime import UTC, datetime

from memorii.core.execution import RuntimeStepService
from memorii.core.execution.service import InMemoryMemoryPlane
from memorii.core.memory_plane import MemoryPlaneService, from_memory_object, from_provider_stored_record
from memorii.core.provider.models import ProviderOperation, ProviderStoredRecord
from memorii.core.provider.service import ProviderMemoryService
from memorii.domain.common import Provenance, RoutingInfo
from memorii.domain.enums import (
    CommitStatus,
    Durability,
    ExecutionNodeStatus,
    ExecutionNodeType,
    MemoryDomain,
    MemoryScope,
    SourceType,
    TemporalValidityStatus,
)
from memorii.domain.execution_graph.nodes import ExecutionNode
from memorii.domain.memory_object import MemoryObject
from memorii.domain.retrieval import DomainRetrievalQuery, FreshnessPolicy, RetrievalNamespace, RetrievalScope, ValidityStatus
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


def test_memory_object_to_canonical_conversion() -> None:
    memory = MemoryObject(
        memory_id="m:1",
        memory_type=MemoryDomain.SOLVER,
        scope=MemoryScope.EXECUTION_NODE,
        durability=Durability.TASK_PERSISTENT,
        status=CommitStatus.COMMITTED,
        content={"text": "solver observation"},
        provenance=Provenance(
            source_type=SourceType.SYSTEM,
            source_refs=["evt:1"],
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by="test",
        ),
        routing=RoutingInfo(primary_store="in_memory", secondary_stores=[]),
        namespace={"task_id": "task:1", "execution_node_id": "exec:1", "solver_run_id": "solver:1"},
        validity_status=TemporalValidityStatus.ACTIVE,
    )

    canonical = from_memory_object(memory)
    assert canonical.memory_id == "m:1"
    assert canonical.domain == MemoryDomain.SOLVER
    assert canonical.task_id == "task:1"
    assert canonical.execution_node_id == "exec:1"
    assert canonical.solver_run_id == "solver:1"


def test_provider_stored_record_to_canonical_conversion() -> None:
    provider_record = ProviderStoredRecord(
        memory_id="sem:1",
        domain=MemoryDomain.SEMANTIC,
        text="timeout default is 30s",
        status="committed",
        task_id="task:1",
        timestamp=datetime(2026, 1, 2, tzinfo=UTC),
    )

    canonical = from_provider_stored_record(provider_record)
    assert canonical.memory_id == "sem:1"
    assert canonical.domain == MemoryDomain.SEMANTIC
    assert canonical.text == "timeout default is 30s"
    assert canonical.status == CommitStatus.COMMITTED


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


def test_canonical_storage_coexists_for_provider_and_runtime_records() -> None:
    shared_plane = MemoryPlaneService()
    provider = ProviderMemoryService(memory_plane=shared_plane)
    provider.seed_committed_record(
        ProviderStoredRecord(
            memory_id="sem:seed",
            domain=MemoryDomain.SEMANTIC,
            text="seeded provider fact",
            status="committed",
            task_id="task:compat",
        )
    )

    runtime_memory = MemoryObject(
        memory_id="solv:seed",
        memory_type=MemoryDomain.SOLVER,
        scope=MemoryScope.EXECUTION_NODE,
        durability=Durability.TASK_PERSISTENT,
        status=CommitStatus.COMMITTED,
        content={"text": "runtime observation"},
        provenance=Provenance(
            source_type=SourceType.SYSTEM,
            source_refs=["evt:runtime"],
            created_at=datetime.now(UTC),
            created_by="test",
        ),
        routing=RoutingInfo(primary_store="in_memory", secondary_stores=[]),
        namespace={"task_id": "task:compat", "execution_node_id": "exec:compat", "solver_run_id": "solver:compat"},
        validity_status=TemporalValidityStatus.ACTIVE,
    )
    shared_plane.seed_runtime_memory_object(runtime_memory)

    query = DomainRetrievalQuery(
        domain=MemoryDomain.SOLVER,
        scope=RetrievalScope(task_id="task:compat", execution_node_id="exec:compat", solver_run_id="solver:compat"),
        namespace=RetrievalNamespace(memory_domain=MemoryDomain.SOLVER),
        freshness=FreshnessPolicy(required_validity=ValidityStatus.ACTIVE),
        include_candidates=False,
    )
    results = shared_plane.query_runtime_memory(query)
    assert [item.memory_id for item in results] == ["solv:seed"]


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


def test_memory_plane_primary_storage_is_canonical_records_only() -> None:
    plane = MemoryPlaneService()
    assert hasattr(plane, "_records")
    assert not hasattr(plane, "_runtime_by_domain")
    assert not hasattr(plane, "_transcript_records")
    assert not hasattr(plane, "_candidate_records")
    assert not hasattr(plane, "_committed_records")
