"""Host-injected transport that seals provider proposals into one proposal run."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.memory_evolution.atomic_store import BootstrapWriterHandoffResult
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.semantic_ingestion.contracts import (
    ProviderSemanticProposal,
    SegmentLanguageRoute,
    SegmentProposalOutcome,
    SemanticProposalAttempt,
    SemanticProposalAttemptIdentity,
    SemanticProposalRequest,
    SemanticProposalRequestArtifact,
    SemanticProposalResponseArtifact,
    SemanticProposalRun,
    contract_digest,
    encode_semantic_contract,
)
from memorii.core.semantic_ingestion.proposal_adapter import (
    ProjectionQuoteVerificationAuthority,
    SpanResolver,
    normalize_provider_proposal,
)
from memorii.core.semantic_ingestion.source_normalization_authority import ProposalRunProductionAuthority
from memorii.core.semantic_ingestion.source_normalization_execution import SourceNormalizationNonCommit
from memorii.core.semantic_ingestion.source_normalization_stage import GraphFreeSourceNormalizationInvocation


class ProposalTransportResponse(BaseModel):
    """One exact provider response; bytes must encode the returned typed proposal."""

    proposal: ProviderSemanticProposal
    raw_output_bytes: bytes

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    def exact_bytes(self) -> bool:
        return self.raw_output_bytes == encode_typed_value(self.proposal.model_dump(mode="python"))


class SemanticProposalTransport(Protocol):
    """Host-selected provider transport. It has no configuration lookup fallback."""

    def propose(self, *, request: SemanticProposalRequest, attempt_number: int) -> ProposalTransportResponse | None: ...


class SemanticProposalRequestMaterializer(Protocol):
    """Host-owned resolver for registered prompt/catalog/manifest values."""

    def build_request(
        self,
        *,
        invocation: GraphFreeSourceNormalizationInvocation,
        handoff: BootstrapWriterHandoffResult,
        authority: ProposalRunProductionAuthority,
        route: SegmentLanguageRoute,
    ) -> SemanticProposalRequest: ...


class ProposalRetryPolicy(BaseModel):
    maximum_attempts: int = Field(ge=1)
    retry_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SealedSemanticProposalRunProducer:
    """Materializes, transports, normalizes, and seals every selected route."""

    def __init__(
        self,
        *,
        transport: SemanticProposalTransport,
        request_materializer: SemanticProposalRequestMaterializer,
        retry_policy: ProposalRetryPolicy,
        resolve_quote: SpanResolver,
        projection_quote_verifier: ProjectionQuoteVerificationAuthority,
    ) -> None:
        self._transport = transport
        self._requests = request_materializer
        self._retry_policy = retry_policy
        self._resolve_quote = resolve_quote
        self._quote_verifier = projection_quote_verifier

    def produce(
        self,
        *,
        invocation: GraphFreeSourceNormalizationInvocation,
        handoff: BootstrapWriterHandoffResult,
        authority: ProposalRunProductionAuthority,
    ) -> SemanticProposalRun | SourceNormalizationNonCommit:
        if self._retry_policy.retry_policy_fingerprint != authority.retry_policy_fingerprint:
            return self._unavailable(invocation)
        source = invocation.source
        if (
            source.status != "complete"
            or (authority.source_id, authority.source_digest, authority.preparation_fingerprint)
            != (source.source_id, source.source_digest, source.preparation_fingerprint)
            or authority.route_set_digest != source.segment_language_routes.route_set_digest
        ):
            return self._unavailable(invocation)

        attempts: list[SemanticProposalAttempt] = []
        proposals = []
        outcomes: list[SegmentProposalOutcome] = []
        for route in source.segment_language_routes.routes:
            if route.decision != "selected":
                outcomes.append(SegmentProposalOutcome.create(
                    segment_id=route.segment_id, segment_language_route_digest=route.route_digest,
                    status="evidence_only", proposal_digest=None, attempt_digest=None,
                    reason_codes=("route_not_selected",),
                ))
                continue
            request = self._requests.build_request(
                invocation=invocation, handoff=handoff, authority=authority, route=route
            )
            if not self._request_joins(request=request, source=source, route=route, authority=authority):
                return self._unavailable(invocation)
            request_artifact = SemanticProposalRequestArtifact.create(
                request_bytes=encode_semantic_contract(request)
            )
            history, proposal = self._seal_route(
                request=request, request_artifact=request_artifact, authority=authority, route=route
            )
            attempts.extend(history)
            if proposal is None:
                return self._unavailable(invocation)
            proposals.append(proposal)
            outcomes.append(SegmentProposalOutcome.create(
                segment_id=route.segment_id, segment_language_route_digest=route.route_digest,
                status=proposal.status, proposal_digest=proposal.proposal_digest,
                attempt_digest=proposal.originating_attempt_digest, reason_codes=(),
            ))
        try:
            return SemanticProposalRun.create(
                source_id=source.source_id, source_digest=source.source_digest,
                preparation_fingerprint=source.preparation_fingerprint,
                segment_governance_carriers=source.segment_governance_carriers,
                message_admission_carriers=source.message_admission_carriers,
                governance_carrier_artifact=source.governance_carrier_artifact,
                segment_language_routes=source.segment_language_routes,
                expected_segment_ids=tuple(route.segment_id for route in source.segment_language_routes.routes),
                segment_attempts=tuple(attempts), validated_segments=tuple(proposals),
                segment_outcomes=tuple(outcomes), status=self._run_status(outcomes), diagnostics=(),
            )
        except ValueError:
            return self._unavailable(invocation)

    def _seal_route(
        self, *, request: SemanticProposalRequest, request_artifact: SemanticProposalRequestArtifact,
        authority: ProposalRunProductionAuthority, route: SegmentLanguageRoute,
    ) -> tuple[list[SemanticProposalAttempt], object | None]:
        history: list[SemanticProposalAttempt] = []
        for attempt_number in range(self._retry_policy.maximum_attempts):
            response = self._transport.propose(request=request, attempt_number=attempt_number)
            payload_fingerprint = contract_digest(
                b"memorii.semantic-ingestion.semantic-proposal-attempt-payload.v1",
                {"request_digest": request_artifact.request_digest, "attempt_number": attempt_number},
            )
            if response is None or not response.exact_bytes():
                history.append(self._attempt(
                    request=request, request_artifact=request_artifact, route=route,
                    attempt_number=attempt_number, payload_fingerprint=payload_fingerprint,
                    response_artifact=None, status="failed", diagnostics=("transport_unavailable",),
                ))
                continue
            response_artifact = SemanticProposalResponseArtifact.create(raw_output_bytes=response.raw_output_bytes)
            attempt = self._attempt(
                request=request, request_artifact=request_artifact, route=route,
                attempt_number=attempt_number, payload_fingerprint=payload_fingerprint,
                response_artifact=response_artifact, status="partial", diagnostics=("normalization_rejected",),
            )
            try:
                proposal = normalize_provider_proposal(
                    provider=response.proposal, proposal_id=contract_digest(
                        b"memorii.semantic-ingestion.semantic-proposal-id.v1",
                        {"request_digest": request_artifact.request_digest, "attempt_number": attempt_number},
                    ), source_id=request.source_id, source_digest=request.source_digest,
                    preparation_fingerprint=request.preparation_fingerprint, segment_id=request.segment_id,
                    segment_governance=request.segment_governance,
                    message_admission_identity=request.message_admission_identity,
                    governance_carrier_artifact=request.governance_carrier_artifact,
                    owned_text=request.owned_text, context_text=request.context_text,
                    language_route=request.language_route, proposer_fingerprint=authority.proposer_fingerprint,
                    proposer_manifest_digest=authority.proposer_manifest_digest,
                    prompt_registration_digest=authority.prompt_registration_digest,
                    semantic_request_fingerprint=authority.semantic_request_fingerprint,
                    action_proposal_catalog_fingerprint=authority.action_proposal_catalog_fingerprint,
                    attempt_payload_fingerprint=payload_fingerprint, originating_attempt_digest=attempt.attempt_digest,
                    diagnostics=(), resolve_quote=self._resolve_quote,
                    projection_quote_verifier=self._quote_verifier,
                )
            except ValueError:
                history.append(attempt)
                continue
            complete = SemanticProposalAttempt.create(
                **(attempt.model_dump(mode="python", exclude={"attempt_digest"}) | {
                    "status": "abstained" if response.proposal.abstained else "complete", "diagnostics": (),
                })
            )
            proposal = proposal.model_copy(update={"originating_attempt_digest": complete.attempt_digest})
            # Revalidate the content-addressed proposal after binding its final attempt.
            proposal = type(proposal).create(**proposal.model_dump(mode="python", exclude={"proposal_digest"}))
            history.append(complete)
            return history, proposal
        return history, None

    @staticmethod
    def _attempt(*, request: SemanticProposalRequest, request_artifact: SemanticProposalRequestArtifact,
                 route: SegmentLanguageRoute, attempt_number: int, payload_fingerprint: str,
                 response_artifact: SemanticProposalResponseArtifact | None, status: str,
                 diagnostics: tuple[str, ...]) -> SemanticProposalAttempt:
        identity = SemanticProposalAttemptIdentity.create(
            source_id=request.source_id, preparation_fingerprint=request.preparation_fingerprint,
            segment_id=route.segment_id, segment_governance=request.segment_governance,
            message_admission_identity=request.message_admission_identity,
            governance_carrier_artifact=request.governance_carrier_artifact,
            owned_text=request.owned_text, context_text=request.context_text, language_route=route,
            proposer_fingerprint=request.proposer_manifest.runtime_fingerprint,
            proposer_manifest_digest=request.proposer_manifest.manifest_digest,
            prompt_registration_digest=request.registered_prompt.prompt_registration_digest,
            semantic_request_fingerprint=request.semantic_request_fingerprint,
            attempt_payload_fingerprint=payload_fingerprint, attempt_number=attempt_number,
            request_digest=request_artifact.request_digest, request_artifact_digest=request_artifact.artifact_digest,
        )
        return SemanticProposalAttempt.create(
            identity=identity,
            raw_output_digest=None if response_artifact is None else response_artifact.raw_output_digest,
            response_artifact_digest=None if response_artifact is None else response_artifact.artifact_digest,
            status=status, diagnostics=diagnostics,
        )

    @staticmethod
    def _request_joins(*, request: SemanticProposalRequest, source: object,
                       route: SegmentLanguageRoute, authority: ProposalRunProductionAuthority) -> bool:
        return (
            request.source_id == authority.source_id and request.source_digest == authority.source_digest
            and request.preparation_fingerprint == authority.preparation_fingerprint
            and request.language_route == route and request.proposer_manifest.runtime_fingerprint == authority.proposer_fingerprint
            and request.proposer_manifest.manifest_digest == authority.proposer_manifest_digest
            and request.registered_prompt.prompt_registration_digest == authority.prompt_registration_digest
            and request.semantic_request_fingerprint == authority.semantic_request_fingerprint
            and request.action_proposal_catalog.catalog_schema_fingerprint == authority.action_proposal_catalog_fingerprint
        )

    @staticmethod
    def _run_status(outcomes: list[SegmentProposalOutcome]) -> str:
        if all(outcome.status == "evidence_only" for outcome in outcomes):
            return "evidence_only"
        if all(outcome.status in {"abstained", "evidence_only"} for outcome in outcomes):
            return "abstained"
        return "complete"

    @staticmethod
    def _unavailable(invocation: GraphFreeSourceNormalizationInvocation) -> SourceNormalizationNonCommit:
        return SourceNormalizationNonCommit.create(
            phase="proposal_sealed", reason="proposal_run_unavailable", invocation=invocation
        )


__all__ = [
    "ProposalRetryPolicy", "ProposalTransportResponse", "SealedSemanticProposalRunProducer",
    "SemanticProposalRequestMaterializer", "SemanticProposalTransport",
]
