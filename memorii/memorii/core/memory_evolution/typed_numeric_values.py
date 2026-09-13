"""Closed profile-3 numeric map bodies selected by verified numeric declarations."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from memorii.core.memory_evolution.typed_value_declarations import (
    NumericFieldDeclaration,
    is_canonical_fixed_scale_decimal,
)
from memorii.core.memory_evolution.typed_value_decoder_sources import (
    DecoderSourceManifestError,
    ProtectedDecoderSourceManifestLimits,
    parse_canonical_raw_json_object,
)

_BINARY64 = re.compile(r"[0-9a-f]{16}\Z")
_NEGATIVE_ZERO_BITS = 1 << 63
_BINARY_PREFIX = b'{"$type":"map","entries":[["ieee754_hex","'
_DECIMAL_PREFIX = b'{"$type":"map","entries":[["encoding_spec_id","'
_DECIMAL_MIDDLE = b'"],["fixed_scale_value","'
_MAP_SUFFIX = b'"]]}'


class TypedNumericValueError(ValueError):
    """A numeric body does not match its selected registered field."""


@dataclass(frozen=True)
class ProtectedTypedNumericValueLimits:
    maximum_bytes: int
    maximum_nodes: int
    maximum_depth: int

    def __post_init__(self) -> None:
        if any(type(value) is not int or value <= 0 for value in (self.maximum_bytes, self.maximum_nodes, self.maximum_depth)):
            raise ValueError("typed_numeric_value_limits_must_be_positive")


@dataclass(frozen=True)
class CanonicalFiniteBinary64:
    ieee754_hex: str


@dataclass(frozen=True)
class CanonicalDecimalQuantity:
    encoding_spec_id: str
    fixed_scale_value: str


TypedNumericValue = CanonicalFiniteBinary64 | CanonicalDecimalQuantity


def encode_typed_numeric_value(
    value: TypedNumericValue,
    declaration: NumericFieldDeclaration,
    *,
    limits: ProtectedTypedNumericValueLimits,
) -> bytes:
    """Encode one value only under its verified numeric field declaration."""
    if isinstance(value, CanonicalFiniteBinary64):
        if not isinstance(value.ieee754_hex, str):
            raise TypedNumericValueError("typed_numeric_value_binary64_type_invalid")
        _require_encode_limits(
            limits,
            byte_count=len(_BINARY_PREFIX) + len(value.ieee754_hex) + len(_MAP_SUFFIX),
            nodes=6,
            depth=4,
        )
        _validate_binary64(value.ieee754_hex, declaration)
        encoded = _BINARY_PREFIX + value.ieee754_hex.encode("ascii") + _MAP_SUFFIX
    elif isinstance(value, CanonicalDecimalQuantity):
        if not isinstance(value.encoding_spec_id, str) or not isinstance(value.fixed_scale_value, str):
            raise TypedNumericValueError("typed_numeric_value_decimal_type_invalid")
        _require_encode_limits(
            limits,
            byte_count=(
                len(_DECIMAL_PREFIX)
                + len(value.encoding_spec_id)
                + len(_DECIMAL_MIDDLE)
                + len(value.fixed_scale_value)
                + len(_MAP_SUFFIX)
            ),
            nodes=9,
            depth=4,
        )
        _validate_decimal(value, declaration)
        encoded = (
            _DECIMAL_PREFIX
            + value.encoding_spec_id.encode("ascii")
            + _DECIMAL_MIDDLE
            + value.fixed_scale_value.encode("ascii")
            + _MAP_SUFFIX
        )
    else:
        raise TypedNumericValueError("typed_numeric_value_unknown")  # pragma: no cover
    return encoded


def decode_typed_numeric_value(
    raw_bytes: bytes,
    declaration: NumericFieldDeclaration,
    *,
    limits: ProtectedTypedNumericValueLimits,
) -> TypedNumericValue:
    """Parse a canonical map and validate it against the selected field only."""
    try:
        parsed = parse_canonical_raw_json_object(
            raw_bytes,
            limits=ProtectedDecoderSourceManifestLimits(
                maximum_manifest_bytes=limits.maximum_bytes,
                maximum_manifest_nodes=limits.maximum_nodes,
                maximum_manifest_depth=limits.maximum_depth,
                maximum_files=1,
                maximum_file_bytes=limits.maximum_bytes,
            ),
        )
    except DecoderSourceManifestError as exc:
        raise TypedNumericValueError("typed_numeric_value_raw_invalid") from exc
    entries = _map_entries(parsed.value)
    if declaration.representation == "canonical_finite_binary64":
        if len(entries) != 1 or entries[0][0] != "ieee754_hex" or not isinstance(entries[0][1], str):
            raise TypedNumericValueError("typed_numeric_value_binary64_shape_invalid")
        value = CanonicalFiniteBinary64(entries[0][1])
        _validate_binary64(value.ieee754_hex, declaration)
    elif declaration.representation == "canonical_decimal_quantity":
        if (
            len(entries) != 2
            or tuple(key for key, _ in entries) != ("encoding_spec_id", "fixed_scale_value")
            or not all(isinstance(item, str) for _, item in entries)
        ):
            raise TypedNumericValueError("typed_numeric_value_decimal_shape_invalid")
        encoding_spec_id = entries[0][1]
        fixed_scale_value = entries[1][1]
        assert isinstance(encoding_spec_id, str) and isinstance(fixed_scale_value, str)
        value = CanonicalDecimalQuantity(encoding_spec_id, fixed_scale_value)
        _validate_decimal(value, declaration)
    else:
        raise TypedNumericValueError("typed_numeric_value_representation_invalid")
    if encode_typed_numeric_value(value, declaration, limits=limits) != raw_bytes:
        raise TypedNumericValueError("typed_numeric_value_reencode_mismatch")
    return value


def _map_entries(root: Mapping[str, object]) -> tuple[tuple[str, object], ...]:
    raw_entries = root.get("entries")
    if set(root) != {"$type", "entries"} or root.get("$type") != "map" or not isinstance(raw_entries, tuple):
        raise TypedNumericValueError("typed_numeric_value_map_invalid")
    entries: list[tuple[str, object]] = []
    for item in raw_entries:
        if not isinstance(item, tuple) or len(item) != 2 or not isinstance(item[0], str):
            raise TypedNumericValueError("typed_numeric_value_map_invalid")
        entries.append((item[0], item[1]))
    if len({key for key, _ in entries}) != len(entries):
        raise TypedNumericValueError("typed_numeric_value_map_invalid")
    return tuple(entries)


def _validate_binary64(value: str, declaration: NumericFieldDeclaration) -> None:
    if declaration.representation != "canonical_finite_binary64" or declaration.encoding_spec_id is not None:
        raise TypedNumericValueError("typed_numeric_value_selected_field_invalid")
    if not _BINARY64.fullmatch(value):
        raise TypedNumericValueError("typed_numeric_value_binary64_lexical_invalid")
    bits = int(value, 16)
    if ((bits >> 52) & 0x7FF) == 0x7FF or bits == _NEGATIVE_ZERO_BITS:
        raise TypedNumericValueError("typed_numeric_value_binary64_nonfinite_invalid")


def _validate_decimal(value: CanonicalDecimalQuantity, declaration: NumericFieldDeclaration) -> None:
    if declaration.representation != "canonical_decimal_quantity" or declaration.encoding_spec_id is None:
        raise TypedNumericValueError("typed_numeric_value_selected_field_invalid")
    if value.encoding_spec_id != declaration.encoding_spec_id:
        raise TypedNumericValueError("typed_numeric_value_encoding_spec_mismatch")
    if not is_canonical_fixed_scale_decimal(value.fixed_scale_value, declaration.scale):
        raise TypedNumericValueError("typed_numeric_value_decimal_lexical_invalid")
    if (
        declaration.lower is None
        or declaration.upper is None
        or declaration.lower_inclusive is None
        or declaration.upper_inclusive is None
    ):
        raise TypedNumericValueError("typed_numeric_value_selected_field_invalid")
    lower = _decimal_compare(value.fixed_scale_value, declaration.lower)
    upper = _decimal_compare(value.fixed_scale_value, declaration.upper)
    if lower < 0 or (lower == 0 and not declaration.lower_inclusive) or upper > 0 or (upper == 0 and not declaration.upper_inclusive):
        raise TypedNumericValueError("typed_numeric_value_decimal_range_invalid")


def _decimal_compare(left: str, right: str) -> int:
    left_negative = left.startswith("-")
    right_negative = right.startswith("-")
    if left_negative != right_negative:
        return -1 if left_negative else 1
    left_digits = left.removeprefix("-").replace(".", "")
    right_digits = right.removeprefix("-").replace(".", "")
    magnitude = (len(left_digits) > len(right_digits)) - (len(left_digits) < len(right_digits))
    if magnitude == 0:
        magnitude = (left_digits > right_digits) - (left_digits < right_digits)
    return -magnitude if left_negative else magnitude


def _require_encode_limits(
    limits: ProtectedTypedNumericValueLimits, *, byte_count: int, nodes: int, depth: int
) -> None:
    if byte_count > limits.maximum_bytes:
        raise TypedNumericValueError("typed_numeric_value_bytes_limit_exceeded")
    if nodes > limits.maximum_nodes:
        raise TypedNumericValueError("typed_numeric_value_nodes_limit_exceeded")
    if depth > limits.maximum_depth:
        raise TypedNumericValueError("typed_numeric_value_depth_limit_exceeded")
