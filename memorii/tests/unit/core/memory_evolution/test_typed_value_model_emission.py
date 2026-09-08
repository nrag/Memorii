from __future__ import annotations

import pytest
from memorii.core.memory_evolution import typed_value_model_codec as codec
from memorii.core.memory_evolution.typed_value_declarations import (
    CollectionTypeExpr,
    IntegerTypeExpr,
    MapTypeExpr,
    ScalarTypeExpr,
)


def _emit(value: object, expression: object, *, maximum_bytes: int = 10_000, maximum_nodes: int = 200) -> bytes:
    writer = codec._BoundedWriter(maximum_bytes, maximum_nodes, 20)
    codec._emit_value(writer, value, expression, None, None, None, None, 1)  # type: ignore[arg-type]
    return writer.finish()


def test_map_keys_sort_by_encoded_json_string_bytes() -> None:
    encoded = _emit(
        {"\x01": "control", "\n": "newline"},
        MapTypeExpr("map", ScalarTypeExpr("string")),
    )

    assert encoded == (
        b'{"$type":"map","entries":[["\\n","newline"],["\\u0001","control"]]}'
    )


def test_integer_rejects_wrong_native_type_before_emitting_placeholder() -> None:
    with pytest.raises(codec.TypedValueModelCodecError, match="native_integer_invalid"):
        _emit(True, IntegerTypeExpr("integer", None, None))


def test_bytes_limit_rejects_before_base64_materialization(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_base64(_: bytes) -> bytes:
        raise AssertionError("base64 encoding ran after the output cap rejected")

    monkeypatch.setattr(codec.base64, "b64encode", unexpected_base64)

    with pytest.raises(codec.TypedValueModelCodecError, match="bytes_limit_exceeded"):
        _emit(b"x" * 4_096, ScalarTypeExpr("bytes"), maximum_bytes=20)


def test_set_cardinality_rejects_before_staging_all_encoded_members() -> None:
    values = {f"member-{index}" for index in range(20)}

    with pytest.raises(codec.TypedValueModelCodecError, match="nodes_limit_exceeded"):
        _emit(
            values,
            CollectionTypeExpr("set", ScalarTypeExpr("string")),
            maximum_nodes=3,
        )


def test_large_integer_rejects_before_decimal_string_materialization(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_integer_text(_: int) -> str:
        raise AssertionError("integer text was materialized before the output cap rejected")

    monkeypatch.setattr(codec, "_integer_text", unexpected_integer_text)

    with pytest.raises(codec.TypedValueModelCodecError, match="bytes_limit_exceeded"):
        _emit(1 << 100_000, IntegerTypeExpr("integer", None, None), maximum_bytes=100)
