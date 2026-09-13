"""Byte-exact read compatibility for terminal fixtures captured from baseline HEAD."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest
from memorii.core.semantic_ingestion.contracts import (
    BootstrapGraphTerminalPublicationIntentV3,
    BootstrapGraphTerminalPublicationRequestV3,
    BootstrapGraphTerminalReloadV3,
    decode_semantic_contract,
    encode_semantic_contract,
)

_FIXTURES = (
    ("publication-request.ctv.gz", BootstrapGraphTerminalPublicationRequestV3),
    ("publication-intent.ctv.gz", BootstrapGraphTerminalPublicationIntentV3),
    ("terminal-reload.ctv.gz", BootstrapGraphTerminalReloadV3),
)
_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[3]
    / "fixtures/semantic_ingestion/historical_terminal"
)


@pytest.mark.parametrize(("filename", "contract_type"), _FIXTURES)
def test_historical_terminal_contract_reencodes_byte_identically(
    filename: str, contract_type: type,
) -> None:
    raw = gzip.decompress((_FIXTURE_ROOT / filename).read_bytes())
    decoded = decode_semantic_contract(raw, contract_type)
    assert encode_semantic_contract(decoded) == raw

