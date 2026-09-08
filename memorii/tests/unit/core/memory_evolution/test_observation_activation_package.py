from __future__ import annotations

import base64
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.observation_activation_package import (
    ObservationActivationPackageError,
    _parse_record,
)


def _record_row(path: str, payload: bytes) -> bytes:
    digest = base64.urlsafe_b64encode(sha256(payload).digest()).rstrip(b"=")
    return path.encode() + b",sha256=" + digest + b"," + str(len(payload)).encode() + b"\n"


def test_record_parser_requires_exact_sha256_membership_rows() -> None:
    raw = _record_row("memorii/__init__.py", b"")
    assert _parse_record(raw) == {
        "memorii/__init__.py": ("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", 0)
    }
    with pytest.raises(ObservationActivationPackageError):
        _parse_record(raw + raw)
    with pytest.raises(ObservationActivationPackageError):
        _parse_record(b"memorii/__init__.py,sha256=wrong,0\n")
