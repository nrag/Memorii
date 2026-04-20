from memorii.core.consolidation import Consolidator


def test_writeback_candidates_preserve_provenance_and_source_refs() -> None:
    consolidator = Consolidator()
    candidate = consolidator.from_solver_resolution(
        candidate_id="wb-1",
        task_id="task-1",
        solver_run_id="solver-1",
        execution_node_id="exec-1",
        summary="Fixed flaky test",
        source_refs=["evt-1", "evt-2"],
    )

    assert candidate.provenance.source_refs == ["evt-1", "evt-2"]
    assert candidate.source_refs == ["evt-1", "evt-2"]
    assert candidate.source_task_id == "task-1"
    assert candidate.source_solver_run_id == "solver-1"
