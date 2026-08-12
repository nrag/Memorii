"""Focused closed-wire vectors for the self-contained bootstrap payload contracts."""

from __future__ import annotations

from hashlib import sha256

import pytest
from memorii.core.semantic_ingestion.contracts import (
    BootstrapV3PayloadLimitAuthority,
    BootstrapV3PayloadLimitPolicy,
    decode_semantic_contract,
    encode_semantic_contract,
)
from tests.fixtures.semantic_ingestion.source_normalization_fixture_builder import (
    build_bootstrap_declared_prepared_source,
    build_bootstrap_v3_fixture_authority,
)


def _hex(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _policy() -> BootstrapV3PayloadLimitPolicy:
    values = {
        name: 1
        for name in BootstrapV3PayloadLimitPolicy.model_fields
        if name not in {"schema_version", "policy_digest"}
    }
    return BootstrapV3PayloadLimitPolicy.create(**values)


def test_bootstrap_v3_limit_policy_and_authority_are_closed_codec_records() -> None:
    policy = _policy()
    authority = BootstrapV3PayloadLimitAuthority.create(
        policy=policy,
        source_id="source:bootstrap",
        source_digest=_hex("source"),
        preparation_fingerprint=_hex("prepared"),
    )
    encoded = encode_semantic_contract(authority)
    assert decode_semantic_contract(encoded, BootstrapV3PayloadLimitAuthority) == authority
    with pytest.raises(ValueError):
        BootstrapV3PayloadLimitAuthority.model_validate(
            authority.model_dump(mode="python") | {"source_id": "source:substituted"}
        )


def test_bootstrap_v3_fixture_issues_declared_route_and_exact_four_lane_requests() -> None:
    source = build_bootstrap_declared_prepared_source(
        source_id="source:bootstrap-fixture",
        source_digest=_hex("bootstrap-fixture-source"),
        source_text="Alice works for Globex.",
    )
    issued = build_bootstrap_v3_fixture_authority(source=source)
    request = issued.runtime_authority.proposal_requests[0]
    assert request.segment.bootstrap_projection.bootstrap_route == source.segment_language_routes.routes[0]
    assert issued.linguistic_request(request, "stanza").analyzer_manifest == issued.stanza_manifest
    assert issued.linguistic_request(request, "spacy").analyzer_manifest == issued.spacy_manifest
    assert issued.predicate_request(request).predicate_event_manifest == issued.predicate_manifest
    assert issued.temporal_request(request).resolver_manifest == issued.temporal_manifest
