"""Focused proof for host-injected sealed proposal transport."""

from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace

from clean_room_request_test_support import build_clean_room_semantic_proposal_request, build_prepared_source_authority
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.semantic_ingestion.contracts import ProviderSemanticProposal, SemanticProposalRequest, contract_digest
from memorii.core.semantic_ingestion.sealed_proposal_producer import (
    ProposalRetryPolicy,
    ProposalTransportResponse,
    SealedSemanticProposalRunProducer,
)
from memorii.core.semantic_ingestion.source_normalization_authority import ProposalRunProductionAuthority
from memorii.core.semantic_ingestion.source_normalization_execution import SourceNormalizationNonCommit


class _Materializer:
    def __init__(self, request: SemanticProposalRequest) -> None:
        self.request = request

    def build_request(self, **_: object) -> SemanticProposalRequest:
        return self.request


class _Transport:
    def __init__(self, responses: list[ProposalTransportResponse | None]) -> None:
        self.responses = responses
        self.calls = 0

    def propose(self, **_: object) -> ProposalTransportResponse | None:
        response = self.responses[self.calls]
        self.calls += 1
        return response


class _Verifier:
    def verify_quote(self, **_: object) -> None:
        raise AssertionError("abstention must not resolve quotes")


def _request_and_source() -> tuple[SemanticProposalRequest, object]:
    text = "Alice starts project Atlas. " * 4
    digest = sha256(text.encode()).hexdigest()
    source = build_prepared_source_authority(source_id="sealed-source", source_digest=digest, source_text=text)
    request = build_clean_room_semantic_proposal_request(source_id=source.source_id, source_digest=digest, source_text=text)
    request = SemanticProposalRequest.create(**(
        request.model_dump(mode="python", exclude={"semantic_request_fingerprint"})
        | {"preparation_fingerprint": source.preparation_fingerprint}
    ))
    return request, source


def _authority(request: SemanticProposalRequest, source: object, retry: str) -> ProposalRunProductionAuthority:
    values = {
        "source_id": request.source_id, "source_digest": request.source_digest,
        "preparation_fingerprint": source.preparation_fingerprint,
        "route_set_digest": source.segment_language_routes.route_set_digest,
        "proposer_fingerprint": request.proposer_manifest.runtime_fingerprint,
        "proposer_manifest_digest": request.proposer_manifest.manifest_digest,
        "prompt_registration_digest": request.registered_prompt.prompt_registration_digest,
        "semantic_request_fingerprint": request.semantic_request_fingerprint,
        "action_proposal_catalog_fingerprint": request.action_proposal_catalog.catalog_schema_fingerprint,
        "retry_policy_fingerprint": retry,
    }
    return ProposalRunProductionAuthority(
        **values,
        authority_digest=contract_digest(b"memorii.semantic-ingestion.proposal-run-production-authority.v1", values),
    )


def _invocation(source: object) -> object:
    return SimpleNamespace(source=source, operation_id="operation", operation_fence_binding=SimpleNamespace(binding_digest="f" * 64))


def _producer(request: SemanticProposalRequest, responses: list[ProposalTransportResponse | None], retry: str, attempts: int = 2) -> SealedSemanticProposalRunProducer:
    return SealedSemanticProposalRunProducer(
        transport=_Transport(responses), request_materializer=_Materializer(request),
        retry_policy=ProposalRetryPolicy(maximum_attempts=attempts, retry_policy_fingerprint=retry),
        resolve_quote=lambda *_: (_ for _ in ()).throw(AssertionError("not reached")),
        projection_quote_verifier=_Verifier(),
    )


def _abstention() -> ProposalTransportResponse:
    proposal = ProviderSemanticProposal(abstained=True)
    return ProposalTransportResponse(proposal=proposal, raw_output_bytes=encode_typed_value(proposal.model_dump(mode="python")))


def test_host_injected_transport_seals_exact_abstention_run() -> None:
    request, source = _request_and_source()
    retry = "a" * 64
    result = _producer(request, [_abstention()], retry, attempts=1).produce(
        invocation=_invocation(source), handoff=SimpleNamespace(), authority=_authority(request, source, retry)
    )
    assert result.status == "abstained"
    assert result.segment_attempts[0].status == "abstained"
    assert result.segment_attempts[0].response_artifact_digest is not None


def test_transport_retry_preserves_partial_attempt_before_success() -> None:
    request, source = _request_and_source()
    retry = "a" * 64
    malformed = ProviderSemanticProposal(abstained=False)
    bad = ProposalTransportResponse(proposal=malformed, raw_output_bytes=encode_typed_value(malformed.model_dump(mode="python")))
    result = _producer(request, [bad, _abstention()], retry).produce(
        invocation=_invocation(source), handoff=SimpleNamespace(), authority=_authority(request, source, retry)
    )
    assert result.status == "abstained"
    assert [item.status for item in result.segment_attempts] == ["partial", "abstained"]
    assert result.segment_attempts[0].identity.attempt_payload_fingerprint != result.segment_attempts[1].identity.attempt_payload_fingerprint


def test_rejects_authority_substitution_and_nonexact_provider_bytes() -> None:
    request, source = _request_and_source()
    retry = "a" * 64
    authority = _authority(request, source, retry)
    substituted = authority.model_copy(update={"proposer_manifest_digest": "x" * 64})
    response = _abstention().model_copy(update={"raw_output_bytes": b"not-the-provider-wire"})
    result = _producer(request, [response], retry, attempts=1).produce(
        invocation=_invocation(source), handoff=SimpleNamespace(), authority=substituted
    )
    assert isinstance(result, SourceNormalizationNonCommit)
    assert result.reason == "proposal_run_unavailable"
    bytes_result = _producer(request, [response], retry, attempts=1).produce(
        invocation=_invocation(source), handoff=SimpleNamespace(), authority=authority
    )
    assert isinstance(bytes_result, SourceNormalizationNonCommit)
