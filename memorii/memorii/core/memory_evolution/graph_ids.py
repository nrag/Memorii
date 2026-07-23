"""Stable identifiers for memory graph nodes and edges."""

from uuid import NAMESPACE_URL, uuid5

from memorii.core.memory_evolution.models import MemoryGraphEdgeType, MemoryScope


def stable_graph_id(prefix: str, value: str) -> str:
    return f"{prefix}:{uuid5(NAMESPACE_URL, value)}"


def source_node_id(source_id: str) -> str:
    return f"graph:node:source:{source_id}"


def entity_node_id(link_id: str) -> str:
    return f"graph:node:entity:{link_id}"


def candidate_entity_node_id(entity_id: str) -> str:
    return f"graph:node:entity:candidate:{entity_id}"


def claim_node_id(claim_id: str) -> str:
    return f"graph:node:claim:{claim_id}"


def action_node_id(action_id: str) -> str:
    return f"graph:node:action:{action_id}"


def literal_node_id(value: str) -> str:
    return stable_graph_id("graph:node:literal", normalize_value(value))


def scope_node_id(scope: MemoryScope) -> str:
    return stable_graph_id("graph:node:scope", scope.stable_id())


def task_node_id(task_id: str) -> str:
    return f"graph:node:task:{task_id}"


def contradiction_node_id(contradiction_set_id: str) -> str:
    return f"graph:node:contradiction:{contradiction_set_id}"


def edge_id(
    edge_type: MemoryGraphEdgeType,
    source_node_id: str,
    target_node_id: str,
    qualifier: str = "default",
) -> str:
    return stable_graph_id(
        "graph:edge",
        f"{edge_type.value}|{source_node_id}|{target_node_id}|{qualifier}",
    )


def normalize_value(value: str) -> str:
    return " ".join(value.strip().lower().split())
