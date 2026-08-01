from memorii.core.benchmark.memory_evolution_runtime.graph_items import graph_items_from_snapshot
from memorii.core.memory_evolution import MemoryGraphNode, MemoryGraphNodeType, MemoryGraphSnapshot


def _entity_node(
    *,
    node_id: str,
    canonical_id: str | None,
    normalized_name: str | None = None,
    aliases: str = "",
) -> MemoryGraphNode:
    properties = {"entity_type": "project", "aliases": aliases}
    if normalized_name is not None:
        properties["normalized_name"] = normalized_name
    return MemoryGraphNode(
        node_id=node_id,
        node_type=MemoryGraphNodeType.ENTITY,
        label=canonical_id or "missing",
        canonical_id=canonical_id,
        lifecycle_state="active",
        confidence=0.9,
        payload_ref=f"payload:{node_id}",
        properties=properties,
    )


def test_graph_item_normalization_reports_and_skips_missing_identity() -> None:
    result = graph_items_from_snapshot(
        scenario_id="scenario:1",
        snapshot=MemoryGraphSnapshot(
            snapshot_id="snapshot:1",
            nodes=[
                _entity_node(node_id="node:valid", canonical_id="entity:atlas"),
                _entity_node(node_id="node:invalid", canonical_id=None),
            ],
        ),
        source_id_to_event_id={},
    )

    assert [item.runtime_item_id for item in result.items] == ["node:valid"]
    assert result.validation_errors == ["malformed_graph_row:node:invalid:invalid_canonical_id"]


def test_graph_item_normalization_preserves_persisted_canonical_name() -> None:
    result = graph_items_from_snapshot(
        scenario_id="scenario:1",
        snapshot=MemoryGraphSnapshot(
            snapshot_id="snapshot:1",
            nodes=[
                _entity_node(
                    node_id="node:atlas",
                    canonical_id="entity:opaque-atlas-id",
                    normalized_name="atlas billing migration",
                    aliases="Atlas|Migration project",
                )
            ],
        ),
        source_id_to_event_id={},
    )

    [entity] = result.items
    assert entity.canonical_name == "atlas billing migration"
    assert entity.canonical_id == "entity:opaque-atlas-id"
    assert entity.aliases == ["Atlas", "Migration project"]
    assert result.validation_errors == []
