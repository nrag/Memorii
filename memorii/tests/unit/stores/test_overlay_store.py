from datetime import UTC, datetime

from memorii.domain.enums import SolverNodeStatus
from memorii.domain.solver_graph.overlays import SolverNodeOverlay, SolverOverlayVersion
from memorii.stores.overlays import InMemoryOverlayStore


def _overlay(version_id: str, solver_run_id: str, node_id: str, status: SolverNodeStatus) -> SolverOverlayVersion:
    return SolverOverlayVersion(
        version_id=version_id,
        solver_run_id=solver_run_id,
        created_at=datetime.now(UTC),
        node_overlays=[
            SolverNodeOverlay(
                node_id=node_id,
                belief=0.5,
                status=status,
                frontier_priority=0.9,
                is_frontier=True,
                updated_at=datetime.now(UTC),
            )
        ],
    )


def test_overlay_version_retrieval() -> None:
    store = InMemoryOverlayStore()
    v1 = _overlay("v1", "solver-1", "n1", SolverNodeStatus.ACTIVE)
    v2 = _overlay("v2", "solver-1", "n2", SolverNodeStatus.REOPENABLE)

    store.append_overlay_version(v1)
    store.append_overlay_version(v2)

    assert [v.version_id for v in store.list_versions("solver-1")] == ["v1", "v2"]
    assert store.get_latest_version("solver-1").version_id == "v2"
    assert store.get_latest_for_node("solver-1", "n1").version_id == "v1"
