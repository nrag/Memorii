from __future__ import annotations

import pytest
from memorii.core.memory_evolution import typed_numeric_values
from memorii.core.memory_evolution.typed_numeric_values import (
    CanonicalDecimalQuantity,
    CanonicalFiniteBinary64,
    ProtectedTypedNumericValueLimits,
    TypedNumericValueError,
    decode_typed_numeric_value,
    encode_typed_numeric_value,
)
from memorii.core.memory_evolution.typed_value_declarations import NumericFieldDeclaration

LIMITS = ProtectedTypedNumericValueLimits(2_000, 100, 10)
DECIMAL = NumericFieldDeclaration("quantity", "canonical_decimal_quantity", "example.quantity.v1", "", "2", "-1.25", True, "0.00", False, False)
BINARY = NumericFieldDeclaration("ratio", "canonical_finite_binary64", None, None, None, None, None, None, None, None)


def test_exact_numeric_map_bytes_round_trip_under_selected_field() -> None:
    binary = b'{"$type":"map","entries":[["ieee754_hex","3ff0000000000000"]]}'
    decimal = b'{"$type":"map","entries":[["encoding_spec_id","example.quantity.v1"],["fixed_scale_value","-1.25"]]}'
    assert encode_typed_numeric_value(CanonicalFiniteBinary64("3ff0000000000000"), BINARY, limits=LIMITS) == binary
    assert encode_typed_numeric_value(CanonicalDecimalQuantity("example.quantity.v1", "-1.25"), DECIMAL, limits=LIMITS) == decimal
    assert decode_typed_numeric_value(binary, BINARY, limits=LIMITS) == CanonicalFiniteBinary64("3ff0000000000000")
    assert decode_typed_numeric_value(decimal, DECIMAL, limits=LIMITS) == CanonicalDecimalQuantity("example.quantity.v1", "-1.25")


@pytest.mark.parametrize(
    ("value", "declaration", "raw", "nodes"),
    [
        (CanonicalFiniteBinary64("3ff0000000000000"), BINARY, b'{"$type":"map","entries":[["ieee754_hex","3ff0000000000000"]]}', 6),
        (CanonicalDecimalQuantity("example.quantity.v1", "-1.25"), DECIMAL, b'{"$type":"map","entries":[["encoding_spec_id","example.quantity.v1"],["fixed_scale_value","-1.25"]]}', 9),
    ],
)
def test_encode_decode_accept_exact_resource_caps_and_reencode_identity(
    value: CanonicalFiniteBinary64 | CanonicalDecimalQuantity,
    declaration: NumericFieldDeclaration,
    raw: bytes,
    nodes: int,
) -> None:
    limits = ProtectedTypedNumericValueLimits(len(raw), nodes, 4)
    assert encode_typed_numeric_value(value, declaration, limits=limits) == raw
    decoded = decode_typed_numeric_value(raw, declaration, limits=limits)
    assert encode_typed_numeric_value(decoded, declaration, limits=limits) == raw


@pytest.mark.parametrize(
    ("value", "declaration", "raw", "nodes"),
    [
        (CanonicalFiniteBinary64("3ff0000000000000"), BINARY, b'{"$type":"map","entries":[["ieee754_hex","3ff0000000000000"]]}', 6),
        (CanonicalDecimalQuantity("example.quantity.v1", "-1.25"), DECIMAL, b'{"$type":"map","entries":[["encoding_spec_id","example.quantity.v1"],["fixed_scale_value","-1.25"]]}', 9),
    ],
)
def test_encode_decode_reject_one_less_resource_cap(
    value: CanonicalFiniteBinary64 | CanonicalDecimalQuantity,
    declaration: NumericFieldDeclaration,
    raw: bytes,
    nodes: int,
) -> None:
    for limits in (
        ProtectedTypedNumericValueLimits(len(raw) - 1, nodes, 4),
        ProtectedTypedNumericValueLimits(len(raw), nodes - 1, 4),
        ProtectedTypedNumericValueLimits(len(raw), nodes, 3),
    ):
        with pytest.raises(TypedNumericValueError):
            encode_typed_numeric_value(value, declaration, limits=limits)
        with pytest.raises(TypedNumericValueError):
            decode_typed_numeric_value(raw, declaration, limits=limits)


def test_oversized_decimal_encode_rejects_before_numeric_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def should_not_validate(value: CanonicalDecimalQuantity, declaration: NumericFieldDeclaration) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(typed_numeric_values, "_validate_decimal", should_not_validate)
    value = CanonicalDecimalQuantity("example.quantity.v1", "9" * 2_000)
    with pytest.raises(TypedNumericValueError, match="bytes_limit"):
        encode_typed_numeric_value(value, DECIMAL, limits=LIMITS)
    assert not called


def test_decode_rejects_encoder_disagreement(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = b'{"$type":"map","entries":[["ieee754_hex","3ff0000000000000"]]}'

    def disagree(
        value: CanonicalFiniteBinary64 | CanonicalDecimalQuantity,
        declaration: NumericFieldDeclaration,
        *,
        limits: ProtectedTypedNumericValueLimits,
    ) -> bytes:
        return b"different"

    monkeypatch.setattr(typed_numeric_values, "encode_typed_numeric_value", disagree)
    with pytest.raises(TypedNumericValueError, match="reencode_mismatch"):
        decode_typed_numeric_value(raw, BINARY, limits=LIMITS)


@pytest.mark.parametrize("binary", [True, False])
def test_encode_rejects_public_numeric_body_scalar_wrong_types(binary: bool) -> None:
    if binary:
        value: CanonicalFiniteBinary64 | CanonicalDecimalQuantity = CanonicalFiniteBinary64("3ff0000000000000")
        object.__setattr__(value, "ieee754_hex", 1)
        declaration = BINARY
    else:
        value = CanonicalDecimalQuantity("example.quantity.v1", "-1.25")
        object.__setattr__(value, "fixed_scale_value", 1)
        declaration = DECIMAL
    with pytest.raises(TypedNumericValueError, match="type_invalid"):
        encode_typed_numeric_value(value, declaration, limits=LIMITS)


@pytest.mark.parametrize("bits", ["0000000000000000", "0000000000000001", "bff0000000000000"])
def test_binary64_accepts_finite_zero_subnormal_and_negative(bits: str) -> None:
    assert decode_typed_numeric_value(b'{"$type":"map","entries":[["ieee754_hex","' + bits.encode() + b'"]]}', BINARY, limits=LIMITS) == CanonicalFiniteBinary64(bits)


@pytest.mark.parametrize("bits", ["7ff0000000000000", "fff0000000000000", "7ff8000000000000", "8000000000000000", "3FF0000000000000"])
def test_binary64_rejects_nonfinite_negative_zero_and_noncanonical_bits(bits: str) -> None:
    with pytest.raises(TypedNumericValueError):
        decode_typed_numeric_value(b'{"$type":"map","entries":[["ieee754_hex","' + bits.encode() + b'"]]}', BINARY, limits=LIMITS)


@pytest.mark.parametrize("value", ["-1.26", "0.00", "+1.25", "01.25", "1.2", "1.250", "1e2", "-0.00"])
def test_decimal_rejects_bounds_and_no_rounding_lexical_forms(value: str) -> None:
    raw = b'{"$type":"map","entries":[["encoding_spec_id","example.quantity.v1"],["fixed_scale_value","' + value.encode() + b'"]]}'
    with pytest.raises(TypedNumericValueError):
        decode_typed_numeric_value(raw, DECIMAL, limits=LIMITS)


def test_decimal_rejects_selected_field_id_mismatch_and_map_shape_mutations() -> None:
    for raw in (
        b'{"$type":"map","entries":[["encoding_spec_id","other"],["fixed_scale_value","-1.25"]]}',
        b'{"$type":"map","entries":[["fixed_scale_value","-1.25"],["encoding_spec_id","example.quantity.v1"]]}',
        b'{"$type":"map","entries":[["encoding_spec_id","example.quantity.v1"]]}',
        b'{"$type":"map","entries":[["encoding_spec_id","example.quantity.v1"],["fixed_scale_value","-1.25"],["x","y"]]}',
    ):
        with pytest.raises(TypedNumericValueError):
            decode_typed_numeric_value(raw, DECIMAL, limits=LIMITS)
