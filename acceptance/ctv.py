"""Closed CTV-v1 encoder for acceptance certificate algebra.

This boundary owns only the values required by numeric certification.  It is
intentionally narrower than the production codec: no bytes, temporal values,
sets, or production-domain models are accepted here.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any


class NumericCtvError(ValueError):
    """Raised when a numeric certification value has no CTV-v1 encoding."""


def _string(value: str) -> bytes:
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise NumericCtvError("canonical_unicode_scalar_invalid") from exc
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def encode_typed_value(value: Any) -> bytes:
    """Encode the closed numeric result algebra under the frozen CTV-v1 form."""
    if value is None:
        return b"null"
    if type(value) is bool:
        return b"true" if value else b"false"
    if type(value) is int:
        return b'{"$type":"integer","value":"' + str(value).encode("ascii") + b'"}'
    if type(value) is Decimal:
        if not value.is_finite():
            raise NumericCtvError("canonical_decimal_invalid")
        return b'{"$type":"decimal","value":' + _string(format(value, "f")) + b"}"
    if type(value) is str:
        return _string(value)
    if type(value) is bytes:
        return b'{"$type":"bytes","base64":' + _string(base64.b64encode(value).decode("ascii")) + b"}"
    if type(value) is datetime:
        if value.utcoffset() is None:
            raise NumericCtvError("canonical_timestamp_invalid")
        normalized = value.astimezone(UTC).isoformat().replace("+00:00", "Z")
        return b'{"$type":"timestamp","value":' + _string(normalized) + b"}"
    if type(value) is tuple:
        return b'{"$type":"tuple","items":[' + b",".join(encode_typed_value(item) for item in value) + b"]}"
    if type(value) is list:
        return b'{"$type":"list","items":[' + b",".join(encode_typed_value(item) for item in value) + b"]}"
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise NumericCtvError("canonical_map_key_invalid")
        entries = sorted((_string(key), value[key]) for key in value)
        return (
            b'{"$type":"map","entries":['
            + b",".join(b"[" + key + b"," + encode_typed_value(item) + b"]" for key, item in entries)
            + b"]}"
        )
    raise NumericCtvError("canonical_value_type_invalid")
