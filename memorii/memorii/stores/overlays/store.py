"""In-memory append-only overlay store."""

from collections import defaultdict

from memorii.domain.solver_graph.overlays import SolverOverlayVersion
from memorii.stores.base.interfaces import OverlayStore


class InMemoryOverlayStore(OverlayStore):
    def __init__(self) -> None:
        self._by_solver: dict[str, list[SolverOverlayVersion]] = defaultdict(list)
        self._by_version_id: dict[str, SolverOverlayVersion] = {}

    def append_overlay_version(self, overlay: SolverOverlayVersion) -> None:
        if overlay.version_id in self._by_version_id:
            raise ValueError(f"Overlay version already exists: {overlay.version_id}")
        self._by_solver[overlay.solver_run_id].append(overlay)
        self._by_version_id[overlay.version_id] = overlay

    def list_versions(self, solver_run_id: str) -> list[SolverOverlayVersion]:
        return list(self._by_solver.get(solver_run_id, []))

    def get_latest_version(self, solver_run_id: str) -> SolverOverlayVersion | None:
        versions: list[SolverOverlayVersion] = self._by_solver.get(solver_run_id, [])
        if not versions:
            return None
        return versions[-1]

    def get_latest_for_node(self, solver_run_id: str, node_id: str) -> SolverOverlayVersion | None:
        for version in reversed(self._by_solver.get(solver_run_id, [])):
            if any(node_overlay.node_id == node_id for node_overlay in version.node_overlays):
                return version
        return None
