from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from typing import cast

from memorii.core.semantic_ingestion.contracts import (
    BootstrapSemanticProposalRequestV3,
    SourceSpanReference,
    contract_digest,
)
from memorii.core.semantic_ingestion.openai_responses_project_assertions import (
    OPENAI_PROJECT_ASSERTIONS_MODEL,
    BootstrapV3OpenAIProjectAssertionsTransport,
    OpenAIResponsesApiClient,
)
from memorii.core.semantic_ingestion.project_assertions import ProjectAssertionProviderProposalAdapter


class _Quotes:
    def __init__(self, text: str, *, ambiguous: bool = False) -> None:
        self.text = text
        self.ambiguous = ambiguous

    def __call__(self, quote, context, _owned):
        text = getattr(context, "text", self.text)
        if text.count(quote) != 1 or (self.ambiguous and quote == "Atlas"):
            raise ValueError("quote is not unique")
        return cast(
            SourceSpanReference,
            SimpleNamespace(projection_digest=context.projection_digest, text=quote),
        )

    def verify_quote(self, **_kwargs):
        return None


def _request(
    text: str = "Atlas owner is Bob. Atlas status is active. Atlas deadline is 2026-10-01.",
) -> BootstrapSemanticProposalRequestV3:
    context = SimpleNamespace(projection_digest="a" * 64, text=text)
    return cast(
        BootstrapSemanticProposalRequestV3,
        SimpleNamespace(
            provider_egress_decision_digest="b" * 64,
            segment=SimpleNamespace(source_id="source", segment_id="segment", context_text=context, segment_text=text),
            predicate_catalog=SimpleNamespace(predicates=tuple(SimpleNamespace(predicate_id=value) for value in (
                "project_deadline", "project_owner", "project_status",
            ))),
        ),
    )


def _adapter(text: str, *, ambiguous: bool = False, semantic_digest: str = "c" * 64):
    quotes = _Quotes(text, ambiguous=ambiguous)
    return ProjectAssertionProviderProposalAdapter(
        semantic_contract_digest=semantic_digest, resolve_quote=quotes, projection_quote_verifier=quotes,
    )


def _response(*candidates: dict[str, str]) -> str:
    return json.dumps({"abstained": not candidates, "candidates": list(candidates)})


def test_adapter_converts_owner_status_and_deadline_quote_hints() -> None:
    text = "Atlas owner is Bob. Atlas status is active. Atlas deadline is 2026-10-01."
    proposal = _adapter(text).from_response(request=_request(text), response_text=_response(
        {"predicate_id": "project_owner", "assertion_quote": "Atlas owner is Bob.", "subject_quote": "Atlas", "predicate_anchor_quote": "owner", "value_quote": "Bob"},
        {"predicate_id": "project_status", "assertion_quote": "Atlas status is active.", "subject_quote": "Atlas", "predicate_anchor_quote": "status", "value_quote": "active"},
        {"predicate_id": "project_deadline", "assertion_quote": "Atlas deadline is 2026-10-01.", "subject_quote": "Atlas", "predicate_anchor_quote": "deadline", "value_quote": "2026-10-01"},
    ))
    assert proposal is not None
    assert proposal.abstained is False
    assert [fact.predicate_id for fact in proposal.facts] == ["project_owner", "project_status", "project_deadline"]
    assert proposal.facts[0].object.kind == "entity"
    assert proposal.facts[1].object.literal_type == "text"
    assert proposal.facts[1].object.canonical_value == "active"
    assert proposal.facts[2].object.literal_type == "date"
    assert proposal.facts[2].object.canonical_value == "2026-10-01"


def test_proposal_identity_uses_semantic_contract_not_provider_manifest() -> None:
    text = "Atlas owner is Bob."
    hint = {
        "predicate_id": "project_owner", "assertion_quote": text,
        "subject_quote": "Atlas", "predicate_anchor_quote": "owner", "value_quote": "Bob",
    }
    proposal = _adapter(text).from_response(request=_request(text), response_text=_response(hint))
    assert proposal is not None
    identity = {
        "source_id": "source", "segment_id": "segment",
        "semantic_contract_digest": "c" * 64, **hint,
    }
    assert proposal.facts[0].local_id == contract_digest(
        b"memorii.project-assertions.provider-fact.v1", identity
    )
    revised = _adapter(text, semantic_digest="d" * 64).from_response(
        request=_request(text), response_text=_response(hint)
    )
    assert revised is not None
    assert revised.facts[0].local_id != proposal.facts[0].local_id


def test_adapter_rejects_malformed_duplicate_and_ambiguous_hints() -> None:
    text = "Atlas owner is Bob."
    owner = {"predicate_id": "project_owner", "assertion_quote": text, "subject_quote": "Atlas", "predicate_anchor_quote": "owner", "value_quote": "Bob"}
    adapter = _adapter(text)
    assert adapter.from_response(request=_request(text), response_text="not json") is None
    assert adapter.from_response(request=_request(text), response_text=_response(owner, owner)) is None
    assert _adapter(text, ambiguous=True).from_response(request=_request(text), response_text=_response(owner)) is None


def test_adapter_enforces_eight_candidate_limit_locally() -> None:
    text = " ".join(f"Project{i} status is active{i}." for i in range(9))
    candidates = tuple({
        "predicate_id": "project_status",
        "assertion_quote": f"Project{i} status is active{i}.",
        "subject_quote": f"Project{i}",
        "predicate_anchor_quote": "status",
        "value_quote": f"active{i}",
    } for i in range(9))
    assert _adapter(text).from_response(request=_request(text), response_text=_response(*candidates)) is None


class _Client:
    def __init__(self, response: str | None) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def test_transport_denial_and_refusal_have_no_wire_effect() -> None:
    text = "Atlas owner is Bob."
    client = _Client(_response({"predicate_id": "project_owner", "assertion_quote": text, "subject_quote": "Atlas", "predicate_anchor_quote": "owner", "value_quote": "Bob"}))
    transport = BootstrapV3OpenAIProjectAssertionsTransport(
        adapter=_adapter(text), egress_authorized=lambda _request: False,
        credential_resolver=lambda: "secret", client=client,
    )
    assert transport(_request(text)) is None
    assert client.calls == []

    refused = BootstrapV3OpenAIProjectAssertionsTransport(
        adapter=_adapter(text), egress_authorized=lambda _request: True,
        credential_resolver=lambda: "secret", client=_Client(None),
    )
    assert refused(_request(text)) is None


def test_transport_forces_profile_model_no_stateful_response_or_background_work() -> None:
    text = "Atlas owner is Bob."
    payload = _response({"predicate_id": "project_owner", "assertion_quote": text, "subject_quote": "Atlas", "predicate_anchor_quote": "owner", "value_quote": "Bob"})
    client = _Client(payload)
    transport = BootstrapV3OpenAIProjectAssertionsTransport(
        adapter=_adapter(text), egress_authorized=lambda _request: True,
        credential_resolver=lambda: "secret", client=client,
    )
    result = transport(_request(text))
    assert result is not None
    assert result[1] == payload.encode("utf-8")
    assert client.calls == [{
        "api_key": "secret", "model": OPENAI_PROJECT_ASSERTIONS_MODEL,
        "system_prompt": client.calls[0]["system_prompt"], "source_segment": text,
        "output_schema": client.calls[0]["output_schema"], "store": False, "background": False,
    }]


def test_api_client_sets_timeout_and_disables_sdk_retries(monkeypatch) -> None:
    created: list[dict[str, object]] = []

    class _OpenAI:
        def __init__(self, **kwargs):
            created.append(kwargs)
            self.responses = SimpleNamespace(create=lambda **_kwargs: SimpleNamespace(output_text='{"abstained":true,"candidates":[]}'))

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_OpenAI, OpenAIError=Exception))
    result = OpenAIResponsesApiClient().complete(
        api_key="secret", model=OPENAI_PROJECT_ASSERTIONS_MODEL, system_prompt="prompt",
        source_segment="source", output_schema={}, store=False, background=False,
    )
    assert result == '{"abstained":true,"candidates":[]}'
    assert created == [{"api_key": "secret", "timeout": 10.0, "max_retries": 0}]
