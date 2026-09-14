from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from acceptance.numeric_context_authority import (
    NumericContextAuthorityRejected,
    verify_numeric_context,
)


@pytest.fixture
def fixture_inputs() -> dict[str, object]:
    path = Path(__file__).parents[4] / "docs/work/semantic_ingestion/statistical-unsupported-cell-binding/manifest-fixtures-v1.json"
    value = json.loads(path.read_text())
    artifacts = value["artifacts"]
    return {
        "baseline_bytes": base64.b64decode(artifacts["capability_baseline"]["canonical_bytes_base64"]),
        "release_bytes": base64.b64decode(artifacts["capability_release"]["canonical_bytes_base64"]),
        "coverage_bytes": base64.b64decode(artifacts["capability_coverage_manifest"]["canonical_bytes_base64"]),
        "gate_bytes": base64.b64decode(artifacts["capability_statistical_gate_manifest"]["canonical_bytes_base64"]),
        "sampling_frame_bytes": base64.b64decode(artifacts["capability_sampling_frame_manifest"]["canonical_bytes_base64"]),
        "signing_keys": {"fixture-key": base64.b64decode(value["public_key_base64"])},
        "expected_signing_key_id": "fixture-key",
        "expected_trust_policy_digest": "a" * 64,
    }


def test_signed_v2_chain_projects_complete_numeric_context(fixture_inputs: dict[str, object]) -> None:
    context = verify_numeric_context(**fixture_inputs)  # type: ignore[arg-type]
    assert context.authority.capability_fingerprint == "cap"
    assert context.authority.sampling_frame_manifest_digest
    assert context.authority.unsupported_cells_digest
    assert [row.disposition for row in context.dispositions].count("explicitly_unsupported") == 2
    assert len(context.certification_context.expected_gates) == 5


def test_v2_chain_rejects_tampered_signature(fixture_inputs: dict[str, object]) -> None:
    value = dict(fixture_inputs)
    raw = bytearray(value["coverage_bytes"])
    raw[-2] ^= 1
    value["coverage_bytes"] = bytes(raw)
    with pytest.raises(NumericContextAuthorityRejected):
        verify_numeric_context(**value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field,value",
    (
        ("expected_signing_key_id", "other-key"),
        ("expected_trust_policy_digest", "b" * 64),
    ),
)
def test_v2_chain_rejects_mixed_signer_or_trust_policy(
    fixture_inputs: dict[str, object], field: str, value: str
) -> None:
    changed = dict(fixture_inputs)
    changed[field] = value
    with pytest.raises(NumericContextAuthorityRejected, match="trust_policy|signer"):
        verify_numeric_context(**changed)  # type: ignore[arg-type]
