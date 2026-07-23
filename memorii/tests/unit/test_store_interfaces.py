import pytest
from memorii.stores.base.interfaces import (
    DirectoryStore,
    EventLogStore,
    ExecutionGraphStore,
    MemoryObjectStore,
    OverlayStore,
    SolverGraphStore,
)


@pytest.mark.parametrize(
    ("store_type", "required_methods"),
    [
        (MemoryObjectStore, {"put", "get"}),
        (
            ExecutionGraphStore,
            {
                "upsert_node",
                "upsert_edge",
                "get_node",
                "get_edge",
                "list_nodes",
                "list_edges",
                "get_children",
                "get_parents",
                "get_dependencies",
                "get_status_snapshot",
            },
        ),
        (
            SolverGraphStore,
            {
                "create_solver_run",
                "upsert_node",
                "upsert_edge",
                "get_node",
                "get_edge",
                "list_nodes",
                "list_edges",
                "list_by_execution_node",
                "get_execution_node_id",
                "list_candidate_nodes",
                "list_committed_nodes",
                "list_candidate_edges",
                "list_committed_edges",
                "get_local_neighborhood",
            },
        ),
        (EventLogStore, {"append", "append_many", "get_by_event_id", "list_by_task", "list_by_solver_run"}),
        (
            OverlayStore,
            {
                "append_overlay_version",
                "list_versions",
                "get_latest_version",
                "get_latest_for_node",
                "get_latest_node_overlay",
            },
        ),
        (
            DirectoryStore,
            {
                "map_task_to_execution_graph",
                "get_execution_graph_id",
                "map_execution_node_to_solver_run",
                "list_solver_runs_for_execution_node",
                "map_transcript_to_task",
                "get_task_for_thread",
                "get_task_for_session",
                "map_agent_partition",
                "list_partitions_for_agent",
                "map_writeback_source",
                "get_writeback_source",
            },
        ),
    ],
)
def test_store_interfaces_require_the_complete_contract(
    store_type: type[object],
    required_methods: set[str],
) -> None:
    assert store_type.__abstractmethods__ == required_methods

    with pytest.raises(TypeError, match="abstract class"):
        store_type()
