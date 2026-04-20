from memorii.core.directory import MemoryDirectory


def test_directory_correctly_maps_task_execution_nodes_and_solver_runs() -> None:
    directory = MemoryDirectory()
    directory.map_task_to_execution_graph("task-1", "graph-1")
    directory.map_execution_node_to_solver_run("task-1", "exec-1", "solver-1")
    directory.map_execution_node_to_solver_run("task-1", "exec-1", "solver-2")

    assert directory.get_execution_graph_id("task-1") == "graph-1"
    assert directory.list_solver_runs_for_execution_node("exec-1") == ["solver-1", "solver-2"]


def test_directory_maps_transcript_session_to_task() -> None:
    directory = MemoryDirectory()
    directory.map_transcript_to_task("task-1", thread_id="thread-1", session_id="session-1")

    assert directory.get_task_for_thread("thread-1") == "task-1"
    assert directory.get_task_for_session("session-1") == "task-1"
