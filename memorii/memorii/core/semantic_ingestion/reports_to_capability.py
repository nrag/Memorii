"""Inert, source-grounded proposal capability for direct reporting lines.

The module deliberately does not select a catalog, advertise a Hermes tool, or
write a fact.  Those actions need the later package-release and capture-pin
owners.  It only compiles a strictly direct ``reports_to(Person, Person)``
proposal from an already authorized source segment.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from memorii.core.semantic_ingestion.contracts import (
    BootstrapSemanticProposalRequestV3,
    ProviderEntityObject,
    ProviderFact,
    ProviderMention,
    ProviderSemanticProposal,
    contract_digest,
)
from memorii.core.semantic_ingestion.proposal_adapter import (
    ProjectionQuoteVerificationAuthority,
    SpanResolver,
)

REPORTS_TO_CAPABILITY_SEMANTIC_REVISION = 1
_PREDICATE_ID = "reports_to"
_DIRECT_REPORTING_LINE = re.compile(
    r"^(?P<subject>[A-Za-z][A-Za-z .'-]{0,126}) reports to "
    r"(?P<object>[A-Za-z][A-Za-z .'-]{0,126})\.$"
)
REPORTS_TO_PROMPT = (
    "Extract one direct reporting-line assertion only when the user source says "
    "'<person> reports to <person>.' exactly. Emit abstention for collaboration, "
    "quoted or reported speech, questions, commands, hypotheticals, uncertainty, "
    "or every other relation."
)
REPORTS_TO_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["abstained", "candidates"],
    "properties": {
        "abstained": {"type": "boolean"},
        "candidates": {
            "type": "array", "maxItems": 1,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": [
                    "predicate_id", "assertion_quote", "subject_quote",
                    "predicate_anchor_quote", "object_quote",
                ],
                "properties": {
                    "predicate_id": {"type": "string", "const": _PREDICATE_ID},
                    "assertion_quote": {"type": "string", "minLength": 1, "maxLength": 1024},
                    "subject_quote": {"type": "string", "minLength": 1, "maxLength": 128},
                    "predicate_anchor_quote": {"type": "string", "const": "reports to"},
                    "object_quote": {"type": "string", "minLength": 1, "maxLength": 128},
                },
            },
        },
    },
}


def reports_to_prompt_contract() -> str:
    """Return the package-owned reporting-line instruction text."""
    return REPORTS_TO_PROMPT


def reports_to_output_schema() -> dict[str, object]:
    """Return a deep JSON round-trip so callers cannot mutate the owner constant."""
    return json.loads(json.dumps(REPORTS_TO_OUTPUT_SCHEMA))


class _Hint(BaseModel):
    predicate_id: str
    assertion_quote: str = Field(min_length=1, max_length=1024)
    subject_quote: str = Field(min_length=1, max_length=128)
    predicate_anchor_quote: str
    object_quote: str = Field(min_length=1, max_length=128)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_reporting_line_hint(self) -> _Hint:
        if self.predicate_id != _PREDICATE_ID or self.predicate_anchor_quote != "reports to":
            raise ValueError("reports-to predicate is unsupported")
        match = _DIRECT_REPORTING_LINE.fullmatch(self.assertion_quote)
        if match is None or (
            match.group("subject") != self.subject_quote
            or match.group("object") != self.object_quote
            or self.subject_quote.casefold() == self.object_quote.casefold()
        ):
            raise ValueError("reports-to assertion is not a direct reporting line")
        return self


class _HintResponse(BaseModel):
    abstained: bool
    candidates: tuple[_Hint, ...] = Field(max_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_closed_outcome(self) -> _HintResponse:
        if self.abstained != (not self.candidates):
            raise ValueError("reports-to abstention and candidates disagree")
        return self


def validate_reports_to_tool_proposal(proposal: ProviderSemanticProposal) -> None:
    """Validate the unadvertised one-fact grammar before any future host wiring."""
    if (
        proposal.abstained or len(proposal.facts) != 1 or proposal.corrections
        or proposal.retractions or proposal.action_states or proposal.identity_operations
    ):
        raise ValueError("reports-to proposal is outside the fact-only grammar")
    fact = proposal.facts[0]
    if (
        fact.predicate_id != _PREDICATE_ID or not isinstance(fact.object, ProviderEntityObject)
        or fact.predicate_anchor_quote != "reports to" or fact.polarity != "positive"
        or fact.commitment != "asserted" or fact.attributed_to_entity_ref is not None
        or fact.temporal_qualifier_quotes
    ):
        raise ValueError("reports-to proposal has an invalid relation shape")
    mentions = {mention.local_id: mention for mention in proposal.mentions}
    subject = mentions.get(fact.subject_entity_ref)
    object_mention = mentions.get(fact.object.entity_ref)
    if (
        len(proposal.mentions) != 2 or len(mentions) != 2 or subject is None or object_mention is None
        or subject.proposed_type != "PersonName" or object_mention.proposed_type != "PersonName"
        or subject.local_id == object_mention.local_id
        or subject.mention_context_quote != fact.assertion_quote
        or object_mention.mention_context_quote != fact.assertion_quote
    ):
        raise ValueError("reports-to proposal must ground two distinct people")
    match = _DIRECT_REPORTING_LINE.fullmatch(fact.assertion_quote)
    if (
        match is None or match.group("subject") != subject.mention_quote
        or match.group("object") != object_mention.mention_quote
        or subject.mention_quote.casefold() == object_mention.mention_quote.casefold()
    ):
        raise ValueError("reports-to proposal is not an exact direct reporting line")


class ReportsToProviderProposalAdapter:
    """Convert one strict direct reporting-line hint into a typed provider proposal."""

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
        self, *, request: BootstrapSemanticProposalRequestV3, response_text: str,
    ) -> ProviderSemanticProposal | None:
        try:
            parsed = _HintResponse.model_validate(json.loads(response_text))
        except (json.JSONDecodeError, ValidationError):
            return ProviderSemanticProposal(abstained=True)
        if not parsed.candidates:
            return ProviderSemanticProposal(abstained=True)
        known = {item.predicate_id for item in request.predicate_catalog.predicates}
        if _PREDICATE_ID not in known:
            return None
        hint = parsed.candidates[0]
        if not self._quotes_are_exact(request=request, hint=hint):
            return ProviderSemanticProposal(abstained=True)
        identity = {
            "source_id": request.segment.source_id,
            "segment_id": request.segment.segment_id,
            "semantic_contract_digest": self._semantic_contract_digest,
            **hint.model_dump(mode="python"),
        }
        fact_id = contract_digest(b"memorii.reports-to.provider-fact.v1", identity)
        subject_id = contract_digest(b"memorii.reports-to.subject-mention.v1", identity)
        object_id = contract_digest(b"memorii.reports-to.object-mention.v1", identity)
        proposal = ProviderSemanticProposal(
            mentions=(
                ProviderMention(
                    local_id=subject_id, mention_quote=hint.subject_quote,
                    mention_context_quote=hint.assertion_quote, proposed_type="PersonName",
                ),
                ProviderMention(
                    local_id=object_id, mention_quote=hint.object_quote,
                    mention_context_quote=hint.assertion_quote, proposed_type="PersonName",
                ),
            ),
            facts=(ProviderFact(
                local_id=fact_id, predicate_id=_PREDICATE_ID, subject_entity_ref=subject_id,
                object=ProviderEntityObject(entity_ref=object_id), assertion_quote=hint.assertion_quote,
                predicate_anchor_quote=hint.predicate_anchor_quote, polarity="positive", commitment="asserted",
            ),),
            abstained=False,
        )
        validate_reports_to_tool_proposal(proposal)
        return proposal

    def _quotes_are_exact(self, *, request: BootstrapSemanticProposalRequestV3, hint: _Hint) -> bool:
        context = request.segment.context_text
        try:
            assertion = self._resolve(hint.assertion_quote, context)
            for quote in (hint.subject_quote, hint.predicate_anchor_quote, hint.object_quote):
                self._resolve(quote, assertion)
        except ValueError:
            return False
        return True

    def _resolve(self, quote: str, context):
        span = self._resolve_quote(quote, context, True)
        self._projection_quote_verifier.verify_quote(
            projection_digest=context.projection_digest, quote=quote, span=span,
        )
        return span


__all__ = [
    "REPORTS_TO_CAPABILITY_SEMANTIC_REVISION", "REPORTS_TO_OUTPUT_SCHEMA", "REPORTS_TO_PROMPT",
    "ReportsToProviderProposalAdapter", "reports_to_output_schema", "reports_to_prompt_contract",
    "validate_reports_to_tool_proposal",
]
