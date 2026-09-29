"""Framework-neutral replay of retained evidence after ontology activation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256

from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedHostIngress,
    encode_typed_value,
)
from memorii.core.provider.ingestion import (
    CapturedCatalogPinReference,
    StructuredFactSubmissionRequest,
)
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.semantic_ingestion.catalog_authority import (
    StructuredSubmissionAuthorityRequest,
)
from memorii.core.semantic_ingestion.contracts import (
    PreparedSource,
    ProviderSemanticProposal,
    VerbatimTextArtifactMappingProof,
)
from memorii.core.semantic_ingestion.learned_relation import AgentLocalCatalogScope


def mentors_replay_arguments(prepared: PreparedSource) -> dict[str, object]:
    """Materialize the frozen direct ``Person mentors Person`` proposal."""
    matches = []
    for span in prepared.sentence_spans:
        quote = prepared.semantic_text[
            span.projection_span.start : span.projection_span.end
        ]
        if not quote.endswith(".") or quote.count(" mentors ") != 1:
            continue
        subject, object_quote = quote[:-1].split(" mentors ", 1)
        if subject and object_quote:
            matches.append((quote, subject, object_quote, span))
    if len(matches) != 1:
        raise ValueError("retained replay is not a unique mentors sentence")
    quote, subject, object_quote, span = matches[0]
    proof = span.text_mapping_proof
    if not isinstance(proof, VerbatimTextArtifactMappingProof):
        raise ValueError("retained replay mapping is unavailable")
    source_start = proof.retained_span.start + (
        span.projection_span.start - proof.projection_span.start
    )
    return {
        "schema_version": 1,
        "source_quote": quote,
        "source_quote_start": source_start,
        "subject_quote": subject,
        "predicate_anchor_quote": "mentors",
        "object_quote": object_quote,
        "proposal": {
            "abstained": False,
            "mentions": [
                {
                    "local_id": "subject",
                    "mention_quote": subject,
                    "mention_context_quote": quote,
                    "proposed_type": "Person",
                },
                {
                    "local_id": "object",
                    "mention_quote": object_quote,
                    "mention_context_quote": quote,
                    "proposed_type": "Person",
                },
            ],
            "facts": [
                {
                    "kind": "fact",
                    "local_id": "mentors",
                    "predicate_id": "mentors",
                    "subject_entity_ref": "subject",
                    "object": {"kind": "entity", "entity_ref": "object"},
                    "assertion_quote": quote,
                    "predicate_anchor_quote": "mentors",
                    "polarity": "positive",
                    "commitment": "asserted",
                    "attributed_to_entity_ref": None,
                    "temporal_qualifier_quotes": [],
                }
            ],
            "corrections": [],
            "retractions": [],
            "action_states": [],
            "identity_operations": [],
        },
    }


def _json_arrays_to_tuples(value: object) -> object:
    if type(value) is list:
        return tuple(_json_arrays_to_tuples(item) for item in value)
    if type(value) is dict:
        return {key: _json_arrays_to_tuples(item) for key, item in value.items()}
    return value


class LearnedRetainedSourceReplayService:
    """Submit learned replay through public provider contracts.

    Host integrations supply only current authority and ingress issuance. The
    provider owns retained source loading, catalog pinning, typed request
    construction, and the ordinary semantic terminal.
    """

    def __init__(
        self,
        *,
        service: ProviderMemoryService,
        authority_request: Callable[[], StructuredSubmissionAuthorityRequest],
        issue_ingress: Callable[[str, str, datetime], AuthenticatedHostIngress],
    ) -> None:
        self._service = service
        self._authority_request = authority_request
        self._issue_ingress = issue_ingress

    def replay_retained_source(
        self,
        *,
        source_id: str,
        source_digest: str,
        catalog_scope: AgentLocalCatalogScope,
        catalog_digest: str,
        replay_operation_id: str,
    ) -> str:
        if not replay_operation_id.startswith("ontology-replay:"):
            return "revoked"
        prepared = self._service.load_retained_prepared_source(
            source_id=source_id,
            source_digest=source_digest,
        )
        session_id = self._service.retained_source_session_id(
            source_id=source_id,
            source_digest=source_digest,
        )
        if prepared is None or session_id is None:
            return "deleted"
        try:
            arguments = mentors_replay_arguments(prepared)
            proposal = ProviderSemanticProposal.model_validate(
                _json_arrays_to_tuples(arguments["proposal"])
            )
            source_quote = arguments["source_quote"]
            source_start = arguments["source_quote_start"]
            if not isinstance(source_quote, str) or not isinstance(source_start, int):
                return "deleted"
            spans = tuple(
                span
                for span in prepared.sentence_spans
                if isinstance(span.text_mapping_proof, VerbatimTextArtifactMappingProof)
                if prepared.semantic_text[
                    span.projection_span.start : span.projection_span.end
                ]
                == source_quote
                and span.text_mapping_proof.retained_span.start
                + (
                    span.projection_span.start
                    - span.text_mapping_proof.projection_span.start
                )
                == source_start
            )
            if len(spans) != 1:
                return "deleted"
            authority_request = self._authority_request()
            ingress = self._issue_ingress(
                session_id,
                catalog_scope.principal_id,
                datetime.now(UTC),
            )
            pin = self._service.pin_retained_source_catalog(
                source_id=source_id,
                source_digest=source_digest,
                authority_request=authority_request,
                authenticated_host_ingress=ingress,
            )
            if (
                pin is None
                or pin.catalog_scope != catalog_scope
                or pin.catalog_digest != catalog_digest
                or self._service.resolve_captured_turn_catalog_dispatch(pin=pin)
                != "learned_overlay"
            ):
                return "revoked"
            raw = encode_typed_value(arguments)
            request = StructuredFactSubmissionRequest(
                source_id=source_id,
                source_digest=source_digest,
                authority_request=authority_request,
                captured_pin=CapturedCatalogPinReference(
                    capture_id=pin.capture_id,
                    pin_memory_id=pin.memory_id,
                    pin_digest=pin.pin_digest,
                    catalog_scope=pin.catalog_scope,
                    catalog_digest=pin.catalog_digest,
                    selected_version_id=pin.selected_version_id,
                    selected_version_digest=pin.selected_version_digest,
                    runtime_bundle_digest=pin.runtime_bundle_digest,
                ),
                exact_source_spans=spans,
                raw_proposal_artifact=raw,
                raw_proposal_artifact_digest=sha256(raw).hexdigest(),
                protocol_version="memorii.authenticated-source.learned-replay.v1",
                parser_version="memorii.retained-sentence-parser.v1",
                proposal=proposal,
                proposal_bytes=encode_typed_value(
                    proposal.model_dump(mode="python")
                ),
            )
            response = self._service.submit_structured_fact(
                request,
                authenticated_host_ingress=ingress,
            )
        except (AttributeError, OSError, TypeError, ValueError):
            return "deleted"
        if response.status == "committed":
            return "committed"
        if response.status in {"abstained", "rejected"}:
            return "abstained"
        if response.status in {"denied", "authorization_revoked_before_commit"}:
            return "revoked"
        return "deleted"


__all__ = ["LearnedRetainedSourceReplayService", "mentors_replay_arguments"]
