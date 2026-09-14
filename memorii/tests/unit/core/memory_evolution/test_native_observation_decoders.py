from __future__ import annotations

import json
from pathlib import Path

import pytest
from memorii.core.memory_evolution.ingestion_contracts import (
    decode_native_observation,
    lookup_native_observation_decoder,
    native_observation_decoder_table,
)
from memorii.core.memory_evolution.models import MemoryScope
from pydantic import ValidationError


def test_static_table_covers_reviewed_inventory_and_is_immutable() -> None:
    inventory_path = (
        Path(__file__).resolve().parents[5]
        / "docs/work/semantic_ingestion/registry-publication/decoder-owner-inventory.json"
    )
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    table = native_observation_decoder_table()

    assert set(table) == {entry["decoder_id"] for entry in inventory["entries"]}
    with pytest.raises(TypeError):
        table["memorii.semantic_ingestion.observation.MemoryScope.v1"] = None  # type: ignore[index]


def test_lookup_rejects_unknown_ids_and_memory_scope_example_constructs_native_model() -> None:
    decoder_id = "memorii.semantic_ingestion.observation.MemoryScope.v1"

    assert lookup_native_observation_decoder(decoder_id) is native_observation_decoder_table()[decoder_id]
    assert decode_native_observation(decoder_id, {}) == MemoryScope()
    for unknown in (
        "memorii.semantic_ingestion.observation.Unknown.v1",
        "memorii.semantic_ingestion.observation.SourceRetentionTimeWitness.v1",
        "memorii.semantic_ingestion.observation.TransactionGroupCommitTimeWitness.v1",
        "",
    ):
        with pytest.raises(ValueError, match="native_observation_decoder_unknown"):
            lookup_native_observation_decoder(unknown)


def test_decoder_rejects_non_mapping_fields() -> None:
    with pytest.raises(ValueError, match="native_observation_fields_invalid"):
        decode_native_observation("memorii.semantic_ingestion.observation.MemoryScope.v1", [])  # type: ignore[arg-type]


def test_memory_scope_example_preserves_native_model_validation() -> None:
    with pytest.raises(ValidationError):
        decode_native_observation(
            "memorii.semantic_ingestion.observation.MemoryScope.v1", {"unexpected": "field"}
        )
