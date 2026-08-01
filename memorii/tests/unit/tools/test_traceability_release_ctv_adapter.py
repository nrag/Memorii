"""CTV-v2 release-loader boundary tests."""

from __future__ import annotations

from dataclasses import replace

import pytest
from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueError,
    CanonicalTypedValueProfileBinding,
    decode_typed_value,
    encode_typed_value,
    serialize_artifact,
)
from memorii.tools.semantic_ingestion_traceability_release import _load


def _binding(schema_id: str) -> CanonicalTypedValueProfileBinding:
    return CanonicalTypedValueProfileBinding(
        profile_id="semantic_ingestion_typed_value",
        profile_version=2,
        profile_digest="9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f",
        schema_id=schema_id,
        schema_version=1,
        binding_digest="2e1ba193b6fac94c03598d7c27489f5fa69e48c5a052072124acb398adfd8ce2",
    )


def test_release_loader_decodes_and_reencodes_ctv_v2_body() -> None:
    body = {"release_id": "fixture-release", "epoch": 1}
    raw = serialize_artifact(body, _binding("SemanticIngestionTraceabilityReleaseBody.v1"))

    assert _load(raw, "release") == body


def test_release_loader_rejects_ctv_body_with_wrong_registered_schema() -> None:
    raw = serialize_artifact(
        {"release_id": "fixture-release"},
        _binding("TraceabilityRunnerReportBody.v1"),
    )

    with pytest.raises(ValueError, match="release_ctv_invalid"):
        _load(raw, "release")


def test_release_loader_rejects_ctv_digest_mutation() -> None:
    envelope = decode_typed_value(
        serialize_artifact(
            {"release_id": "fixture-release"},
            _binding("SemanticIngestionTraceabilityReleaseBody.v1"),
        )
    )
    envelope["artifact_digest"] = "0" * 64
    raw = encode_typed_value(envelope)

    with pytest.raises(ValueError, match="release_ctv_invalid"):
        _load(raw, "release")


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("profile_id", "other_profile"),
        ("profile_version", 3),
        ("profile_digest", "0" * 64),
        ("schema_id", "TraceabilityRunnerReportBody.v1"),
        ("schema_version", 2),
        ("binding_digest", "0" * 64),
    ),
)
def test_release_loader_pins_every_binding_component(
    field: str, replacement: str | int
) -> None:
    body = {"release_id": "fixture-release"}
    assert _load(
        serialize_artifact(body, _binding("SemanticIngestionTraceabilityReleaseBody.v1")),
        "release",
    ) == body
    changed = replace(
        _binding("SemanticIngestionTraceabilityReleaseBody.v1"),
        **{field: replacement},
    )
    try:
        raw = serialize_artifact(body, changed)
    except CanonicalTypedValueError:
        # An invalid profile coordinate is rejected even before transport.
        return
    with pytest.raises(ValueError, match="release_ctv_invalid"):
        _load(raw, "release")
