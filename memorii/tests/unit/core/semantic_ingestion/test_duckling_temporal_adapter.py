"""Contract tests for the sealed local Duckling client."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.memory_evolution.semantic_analysis.temporal.duckling_adapter import (
    DucklingRuntimeCoordinates,
    DucklingTemporalResolver,
    DucklingTemporalResolverUnavailable,
)
from memorii.core.semantic_ingestion.contracts import (
    SegmentAnalysisInput,
    SegmentLanguageResourceBinding,
    SegmentLanguageRoute,
    TemporalResolutionRequest,
    TemporalResolverManifest,
)
from tests.unit.core.semantic_ingestion.test_source_analysis_contracts import _proposal


class _Response:
    def __init__(self, payload: object) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body


def _manifest() -> TemporalResolverManifest:
    return TemporalResolverManifest.create(
        binary_digest="a" * 64,
        ruleset_version="duckling-59a13ff87b1aa8be6b93d387244f8636b26185c5",
        locale_map_digest="b" * 64,
        timezone_policy_digest="c" * 64,
        adapter_schema_digest="d" * 64,
        supported_construction_families=("absolute",),
    )


def _coordinates() -> DucklingRuntimeCoordinates:
    manifest = _manifest()
    return DucklingRuntimeCoordinates(
        image_digest=manifest.binary_digest,
        ruleset_version=manifest.ruleset_version,
        locale_map_digest=manifest.locale_map_digest,
        timezone_policy_digest=manifest.timezone_policy_digest,
        adapter_schema_digest=manifest.adapter_schema_digest,
        supported_construction_families=manifest.supported_construction_families,
    )


def _request(
    text: str = "mañana 2026-01-02" + " " * 63,
    manifest: TemporalResolverManifest | None = None,
) -> TemporalResolutionRequest:
    proposal = _proposal()
    route = proposal.language_route
    assert route.resource_binding is not None
    manifest = _manifest() if manifest is None else manifest
    binding = SegmentLanguageResourceBinding.create(
        selected_language="en",
        proposal_capability_fingerprint=route.resource_binding.proposal_capability_fingerprint,
        stanza_analyzer_manifest_digest=route.resource_binding.stanza_analyzer_manifest_digest,
        spacy_analyzer_manifest_digest=route.resource_binding.spacy_analyzer_manifest_digest,
        predicate_event_manifest_digest=route.resource_binding.predicate_event_manifest_digest,
        temporal_resolver_manifest_digest=manifest.manifest_digest,
    )
    selected = SegmentLanguageRoute.create(
        **(route.model_dump(mode="python", exclude={"route_digest"}) | {"resource_binding": binding})
    )
    segment = SegmentAnalysisInput.create(
        source_id=proposal.source_id,
        source_digest=proposal.source_digest,
        segment_id=proposal.segment_id,
        preparation_fingerprint=proposal.preparation_fingerprint,
        parent_projection_segment_id=selected.parent_projection_segment_id,
        segment_governance=proposal.segment_governance,
        message_admission_identity=proposal.message_admission_identity,
        governance_carrier_artifact=proposal.governance_carrier_artifact,
        context_text=proposal.owned_text,
        segment_text=text,
        language_route=selected,
    )
    return TemporalResolutionRequest.create(segment=segment, resolver_manifest=manifest, reference_evidence=None)


def _resolver(payload: object) -> DucklingTemporalResolver:
    return DucklingTemporalResolver(
        endpoint="http://127.0.0.1:8000/parse",
        runtime_coordinates=_coordinates(),
        resolver_manifest=_manifest(),
        transport=lambda _request, _timeout: _Response(payload),
    )


def test_resolver_uses_character_offsets_and_returns_an_exact_typed_candidate() -> None:
    request = _request()
    # Duckling reports character offsets for the exact source span.
    resolver = _resolver(
        [
            {
                "start": 7,
                "end": 17,
                "body": "2026-01-02",
                "dim": "time",
                "value": {
                    "type": "value",
                    "value": "2026-01-02T00:00:00+00:00",
                    "grain": "day",
                    "values": [{"type": "value", "value": "2026-01-02T00:00:00+00:00", "grain": "day"}],
                },
            },
            {"start": 0, "end": 6, "body": "mañana", "dim": "phone-number", "value": {"value": "123"}},
        ]
    )
    result = resolver.resolve(request, locale="en_US", timezone="UTC")
    assert result is not None
    assert result.candidates[0].exact_text == "2026-01-02"
    assert result.candidates[0].source_span.segment_local_span.start == 17
    assert result.candidates[0].normalized_interval.start == datetime(2026, 1, 2, tzinfo=UTC)


@pytest.mark.parametrize(
    "payload",
    [
        [{"start": 8, "end": 18, "body": "2026-01-02", "dim": "time", "value": {"type": "value", "value": "2026-01-02T00:00:00+00:00", "grain": "day"}}],
        [{"start": 7, "end": 17, "body": "2026-01-02", "dim": "time", "value": {"type": "duration", "value": "P1D", "grain": "day"}}],
        [
            {
                "start": 7,
                "end": 17,
                "body": "2026-01-02",
                "dim": "time",
                "value": {
                    "type": "value",
                    "value": "2026-01-02T00:00:00+00:00",
                    "grain": "day",
                    "values": [
                        {"type": "value", "value": "2026-01-02T00:00:00+00:00", "grain": "day"},
                        {"type": "value", "value": "2027-01-02T00:00:00+00:00", "grain": "day"},
                    ],
                },
            },
        ],
    ],
)
def test_resolver_fails_closed_for_wrong_offsets_unsupported_values_and_ambiguity(payload: object) -> None:
    resolver = _resolver(payload)
    assert resolver.resolve(_request(), locale="en_US", timezone="UTC") is None


def test_resolver_limits_sidecar_request_to_the_time_dimension() -> None:
    captured: dict[str, str] = {}

    def transport(request: object, _timeout: float) -> _Response:
        assert hasattr(request, "data")
        assert isinstance(request.data, bytes)
        captured["body"] = request.data.decode("ascii")
        return _Response(
            [
                {
                    "start": 7,
                    "end": 17,
                    "body": "2026-01-02",
                    "dim": "time",
                    "value": {"type": "value", "value": "2026-01-02T00:00:00+00:00", "grain": "day"},
                }
            ]
        )

    resolver = DucklingTemporalResolver(
        endpoint="http://127.0.0.1:8000/parse",
        runtime_coordinates=_coordinates(),
        resolver_manifest=_manifest(),
        transport=transport,
    )
    result = resolver.resolve(_request(), locale="en_US", timezone="UTC")
    assert result is not None
    assert "dims=%5B%22time%22%5D" in captured["body"]


def test_resolver_rejects_non_loopback_or_substituted_runtime_coordinates() -> None:
    with pytest.raises(DucklingTemporalResolverUnavailable):
        DucklingTemporalResolver(
            endpoint="http://duckling.internal:8000/parse",
            runtime_coordinates=_coordinates(),
            resolver_manifest=_manifest(),
        )
    bad = DucklingRuntimeCoordinates(**(_coordinates().__dict__ | {"image_digest": "f" * 64}))
    with pytest.raises(DucklingTemporalResolverUnavailable):
        DucklingTemporalResolver(
            endpoint="http://127.0.0.1:8000/parse",
            runtime_coordinates=bad,
            resolver_manifest=_manifest(),
        )


def test_sidecar_build_manifest_is_pinned_but_never_claims_an_unbuilt_image() -> None:
    path = Path(__file__).parents[4] / "containers" / "duckling" / "build-manifest.v1.json"
    manifest = json.loads(path.read_text(encoding="ascii"))
    assert manifest["source_commit"] == "59a13ff87b1aa8be6b93d387244f8636b26185c5"
    assert manifest["runtime_network"] == "disabled-required"
    assert manifest["produced_image_digest"] is None


@pytest.mark.integration
def test_live_loopback_sidecar_smoke_when_explicitly_attested() -> None:
    """Optional local-only selector; never contacts a non-loopback host."""

    endpoint = os.environ.get("MEMORII_DUCKLING_SMOKE_ENDPOINT")
    image_digest = os.environ.get("MEMORII_DUCKLING_IMAGE_DIGEST")
    if endpoint is None or image_digest is None:
        pytest.skip("set local Duckling endpoint and produced image digest to enable smoke")
    base = _manifest()
    manifest = TemporalResolverManifest.create(
        binary_digest=image_digest,
        ruleset_version=base.ruleset_version,
        locale_map_digest=base.locale_map_digest,
        timezone_policy_digest=base.timezone_policy_digest,
        adapter_schema_digest=base.adapter_schema_digest,
        supported_construction_families=base.supported_construction_families,
    )
    resolver = DucklingTemporalResolver(
        endpoint=endpoint,
        runtime_coordinates=DucklingRuntimeCoordinates(
            **(_coordinates().__dict__ | {"image_digest": image_digest})
        ),
        resolver_manifest=manifest,
    )
    assert resolver.resolve(_request(manifest=manifest), locale="en_US", timezone="UTC") is not None
