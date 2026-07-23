"""Validated mutation plans for atomic memory evolution."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.models import MemoryGraphSnapshot
from memorii.core.memory_plane.models import CanonicalMemoryRecord


class MemoryEvolutionMutationValidationError(RuntimeError):
    """Raised when a candidate evolution aggregate fails precommit validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = tuple(sorted(set(errors)))
        super().__init__("memory evolution mutation plan is invalid: " + "; ".join(self.errors))


class EvolutionMutationPlan(BaseModel):
    """Immutable, fully materialized write set for one evolution operation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_revision: int = Field(ge=0)
    records: tuple[CanonicalMemoryRecord, ...]
    graph_snapshot: MemoryGraphSnapshot

    @model_validator(mode="after")
    def validate_write_set(self) -> EvolutionMutationPlan:
        record_ids = [record.memory_id for record in self.records]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("mutation plan contains duplicate record ids")

        graph_node_ids = {
            record.content.get("graph_node", {}).get("node_id")
            for record in self.records
            if record.content.get("memory_evolution_kind") == "graph_node"
        }
        graph_edge_ids = {
            record.content.get("graph_edge", {}).get("edge_id")
            for record in self.records
            if record.content.get("memory_evolution_kind") == "graph_edge"
        }
        expected_node_ids = {node.node_id for node in self.graph_snapshot.nodes}
        expected_edge_ids = {edge.edge_id for edge in self.graph_snapshot.edges}
        if graph_node_ids != expected_node_ids:
            raise ValueError("mutation plan graph-node records do not match its snapshot")
        if graph_edge_ids != expected_edge_ids:
            raise ValueError("mutation plan graph-edge records do not match its snapshot")
        return self
