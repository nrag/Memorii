"""Generated OpenAPI schema: model-derived, deterministic, closed."""

from __future__ import annotations

import json

from memorii.tools.runtime_schema_export import build_openapi_document


def test_document_is_deterministic_and_model_derived() -> None:
    first = json.dumps(build_openapi_document(), sort_keys=True)
    second = json.dumps(build_openapi_document(), sort_keys=True)
    assert first == second
    document = json.loads(first)
    schemas = document["components"]["schemas"]
    # Every schema is closed (extra properties forbidden) because the
    # owning models are; the generator adds nothing by hand.
    for name in ("SidecarRequest", "HarnessStateEnvelope", "SidecarError"):
        assert schemas[name]["additionalProperties"] is False
    assert document["servers"] == [{"url": "http://127.0.0.1", "description": "loopback only"}]
    assert document["paths"]["/v1/runtime/state"]["post"]["security"] == [{"bearerAuth": []}]


def test_envelope_schema_carries_the_budget_fields() -> None:
    envelope = build_openapi_document()["components"]["schemas"]["HarnessStateEnvelope"]
    properties = envelope["properties"]
    assert "state_digest" in properties
    assert "continuation_cursor" in properties
    assert "omissions" in properties
    kinds = properties["recommendation_kind"]["enum"]
    assert set(kinds) == {
        "test", "inspect", "ask", "revalidate", "reconcile", "wait", "none",
    }
