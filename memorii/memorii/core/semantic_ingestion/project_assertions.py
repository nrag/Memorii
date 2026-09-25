"""Model-independent project-assertion quote hints and provider proposals.

This module has no persistence or graph dependency.  It turns a strictly
validated, source-quoted response into the existing provider proposal wire;
the normal Bootstrap V3 normalizer remains responsible for sealing it.
"""

from __future__ import annotations

import json
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from memorii.core.memory_evolution.models import ClaimValueType
from memorii.core.semantic_ingestion.contracts import (
    BootstrapSemanticProposalRequestV3,
    ProviderEntityObject,
    ProviderFact,
    ProviderLiteralObject,
    ProviderMention,
    ProviderSemanticProposal,
    SourceSpanReference,
    contract_digest,
)
from memorii.core.semantic_ingestion.proposal_adapter import (
    ProjectionQuoteVerificationAuthority,
    SpanResolver,
)

PROJECT_ASSERTIONS_ADAPTER_SEMANTIC_REVISION = 1
_PREDICATES = frozenset({"project_owner", "project_status", "project_deadline"})
PROJECT_ASSERTIONS_PROMPT = (
    "Extract reusable direct project assertions from the supplied user source segment. "
    "Emit only catalog predicates and exact source quotes. Emit "
    '{"abstained":true,"candidates":[]} for every unsupported, uncertain, non-direct, '
    "quoted, reported, assistant, question, command, or hypothetical statement."
)
PROJECT_ASSERTIONS_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["abstained", "candidates"],
    "properties": {
        "abstained": {"type": "boolean"},
        "candidates": {
            "type": "array", "maxItems": 8,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["predicate_id", "assertion_quote", "subject_quote", "predicate_anchor_quote", "value_quote"],
                "properties": {
                    "predicate_id": {"type": "string", "enum": sorted(_PREDICATES)},
                    "assertion_quote": {"type": "string", "minLength": 1, "maxLength": 1024},
                    "subject_quote": {"type": "string", "minLength": 1, "maxLength": 128},
                    "predicate_anchor_quote": {"type": "string", "minLength": 1, "maxLength": 128},
                    "value_quote": {"type": "string", "minLength": 1, "maxLength": 512},
                },
            },
        },
    },
}


def render_project_assertions_prompt() -> str:
    """Return the fixed profile prompt without accepting caller text."""
    return PROJECT_ASSERTIONS_PROMPT


class _Hint(BaseModel):
    predicate_id: str
    assertion_quote: str = Field(min_length=1, max_length=1024)
    subject_quote: str = Field(min_length=1, max_length=128)
    predicate_anchor_quote: str = Field(min_length=1, max_length=128)
    value_quote: str = Field(min_length=1, max_length=512)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def _catalog_predicate(self) -> _Hint:
        if self.predicate_id not in _PREDICATES:
            raise ValueError("project-facts predicate is unsupported")
        return self


class _HintResponse(BaseModel):
    abstained: bool
    candidates: tuple[_Hint, ...] = Field(max_length=8)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def _closed_outcome(self) -> _HintResponse:
        if self.abstained != (not self.candidates):
            raise ValueError("project-facts abstention and candidates disagree")
        return self


class ProjectAssertionProviderProposalAdapter:
    """Construct a candidate-only provider proposal from fixed-schema quote hints."""

    def __init__(
        self,
        *,
        semantic_contract_digest: str,
        resolve_quote: SpanResolver,
        projection_quote_verifier: ProjectionQuoteVerificationAuthority,
    ) -> None:
        self._semantic_contract_digest = semantic_contract_digest
        self._resolve_quote = resolve_quote
        self._projection_quote_verifier = projection_quote_verifier

    def from_response(
        self, *, request: BootstrapSemanticProposalRequestV3, response_text: str
    ) -> ProviderSemanticProposal | None:
        try:
            raw = json.loads(response_text)
            parsed = _HintResponse.model_validate(raw)
        except (json.JSONDecodeError, ValidationError):
            # The provider returned bytes, but they do not form a usable
            # source-grounded proposal.  Represent that closed validation
            # outcome as an abstention so the admitted source reaches the
            # normal evidence-only terminal.  ``None`` remains reserved for
            # transport/egress unavailability, which is retryable.
            return ProviderSemanticProposal(abstained=True)
        if not parsed.candidates:
            return ProviderSemanticProposal(abstained=True)
        known = {item.predicate_id for item in request.predicate_catalog.predicates}
        if not _PREDICATES.issubset(known):
            return None
        mentions: list[ProviderMention] = []
        facts: list[ProviderFact] = []
        ids: set[str] = set()
        for hint in parsed.candidates:
            if not self._quotes_are_exact(request=request, hint=hint):
                return ProviderSemanticProposal(abstained=True)
            identity = {
                "source_id": request.segment.source_id,
                "segment_id": request.segment.segment_id,
                "semantic_contract_digest": self._semantic_contract_digest,
                **hint.model_dump(mode="python"),
            }
            fact_id = contract_digest(b"memorii.project-assertions.provider-fact.v1", identity)
            project_id = contract_digest(b"memorii.project-assertions.project-mention.v1", identity)
            person_id = contract_digest(b"memorii.project-assertions.person-mention.v1", identity)
            produced_ids = {fact_id, project_id}
            if hint.predicate_id == "project_owner":
                produced_ids.add(person_id)
            if ids.intersection(produced_ids) or len(produced_ids) != (3 if hint.predicate_id == "project_owner" else 2):
                return ProviderSemanticProposal(abstained=True)
            ids.update(produced_ids)
            mentions.append(ProviderMention(
                local_id=project_id, mention_quote=hint.subject_quote,
                mention_context_quote=hint.assertion_quote, proposed_type="ProjectId",
            ))
            if hint.predicate_id == "project_owner":
                mentions.append(ProviderMention(
                    local_id=person_id, mention_quote=hint.value_quote,
                    mention_context_quote=hint.assertion_quote, proposed_type="PersonName",
                ))
                object_value = ProviderEntityObject(entity_ref=person_id)
            else:
                literal_type, canonical = self._literal(hint)
                if canonical is None:
                    return ProviderSemanticProposal(abstained=True)
                object_value = ProviderLiteralObject(literal_type=literal_type, canonical_value=canonical)
            facts.append(ProviderFact(
                local_id=fact_id, predicate_id=hint.predicate_id,
                subject_entity_ref=project_id, object=object_value,
                assertion_quote=hint.assertion_quote, predicate_anchor_quote=hint.predicate_anchor_quote,
                polarity="positive", commitment="asserted",
            ))
        return ProviderSemanticProposal(mentions=tuple(mentions), facts=tuple(facts), abstained=False)

    def _quotes_are_exact(self, *, request: BootstrapSemanticProposalRequestV3, hint: _Hint) -> bool:
        try:
            assertion = self._resolve(hint.assertion_quote, request.segment.context_text)
            for quote in (hint.subject_quote, hint.predicate_anchor_quote, hint.value_quote):
                self._resolve(quote, assertion)
        except ValueError:
            return False
        return True

    def _resolve(self, quote: str, context: SourceSpanReference) -> SourceSpanReference:
        span = self._resolve_quote(quote, context, True)
        self._projection_quote_verifier.verify_quote(
            projection_digest=context.projection_digest, quote=quote, span=span
        )
        return span

    @staticmethod
    def _literal(hint: _Hint) -> tuple[ClaimValueType, str | None]:
        if hint.predicate_id == "project_status":
            value = hint.value_quote.strip()
            return ClaimValueType.TEXT, value if value else None
        try:
            return ClaimValueType.DATE, date.fromisoformat(hint.value_quote).isoformat()
        except ValueError:
            return ClaimValueType.DATE, None


__all__ = [
    "PROJECT_ASSERTIONS_ADAPTER_SEMANTIC_REVISION",
    "PROJECT_ASSERTIONS_OUTPUT_SCHEMA", "PROJECT_ASSERTIONS_PROMPT",
    "ProjectAssertionProviderProposalAdapter", "render_project_assertions_prompt",
]
