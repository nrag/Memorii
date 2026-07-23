from memorii.core.benchmark.memory_evolution_runtime.graph_items import graph_items_from_snapshot
from memorii.core.memory_evolution import MemoryGraphNode, MemoryGraphNodeType, MemoryGraphSnapshot


def _entity_node(*, node_id: str, canonical_id: str | None) -> MemoryGraphNode:
    return MemoryGraphNode(
        node_id=node_id,
        node_type=MemoryGraphNodeType.ENTITY,
        label="Atlas",
        canonical_id=canonical_id,
        lifecycle_state="active",
        confidence=0.9,
        payload_ref=f"payload:{node_id}",
        properties={"entity_type": "project"},
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
    assert result.validation_errors == [
        "malformed_graph_row:node:invalid:invalid_canonical_id"
    ]
