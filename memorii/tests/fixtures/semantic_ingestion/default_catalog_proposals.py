"""Deterministic typed structured proposals from the frozen catalog corpus."""

from __future__ import annotations

import json
from dataclasses import dataclass

from memorii.core.semantic_ingestion.contracts import (
    ProviderEntityObject,
    ProviderFact,
    ProviderLiteralObject,
    ProviderMention,
    ProviderSemanticProposal,
)
from memorii.core.semantic_ingestion.default_catalog_corpus import (
    DefaultCatalogCorpusRow,
)
from memorii.core.semantic_ingestion.default_catalog_runtime import (
    DEFAULT_CATALOG_LITERAL_TYPES,
)
from memorii.core.semantic_ingestion.default_catalog_values import CatalogStatusText


@dataclass(frozen=True)
class DefaultCatalogProposalFixture:
    """A corpus row and one grounded direct structured-tool proposal."""

    row: DefaultCatalogCorpusRow
    source: str
    subject_quote: str
    predicate_anchor_quote: str
    object_quote: str
    subject: ProviderMention
    object: ProviderMention | None
    fact: ProviderFact

    def proposal(self) -> ProviderSemanticProposal:
        return ProviderSemanticProposal(
            abstained=False,
            mentions=(self.subject,) if self.object is None else (self.subject, self.object),
            facts=(self.fact,),
        )

    def tool_arguments(self) -> dict[str, object]:
        """Return JSON-shaped arguments for the shipped Hermes tool boundary."""
        return {
            "schema_version": 1,
            "source_quote": self.source,
            "source_quote_start": 0,
            "subject_quote": self.subject_quote,
            "predicate_anchor_quote": self.predicate_anchor_quote,
            "object_quote": self.object_quote,
            "proposal": self.proposal().model_dump(mode="json"),
        }

    def misleading_tool_arguments(self) -> dict[str, object]:
        """Return a same-shape proposal with a deliberately invalid endpoint."""
        proposal = self.proposal()
        invalid_type = next(
            type_id
            for type_id in ("Animal", "Vehicle", "Subscription", "Recipe")
            if type_id not in self.row.subject_type_ids
        )
        bad_subject = self.subject.model_copy(update={"proposed_type": invalid_type})
        return {
            **self.tool_arguments(),
            "proposal": proposal.model_copy(
                update={"mentions": (bad_subject, *proposal.mentions[1:])}
            ).model_dump(mode="json"),
        }


def build_default_catalog_proposal(
    row: DefaultCatalogCorpusRow,
) -> DefaultCatalogProposalFixture:
    """Build one direct source and exact typed endpoints for ``row``."""
    subject_quote = f"{row.subject_type_ids[0]} subject"
    predicate_anchor_quote = row.relation_id.replace("_", " ")
    literal = _literal(row)
    object_quote = (
        _literal_quote(row)
        if literal is not None
        else f"{row.object_entity_type_ids[0]} object"
    )
    source = f"{subject_quote} {predicate_anchor_quote} {object_quote}."
    subject = ProviderMention(
        local_id="subject",
        mention_quote=subject_quote,
        mention_context_quote=source,
        proposed_type=row.subject_type_ids[0],
    )
    object_mention = (
        None
        if literal is not None
        else ProviderMention(
            local_id="object",
            mention_quote=object_quote,
            mention_context_quote=source,
            proposed_type=row.object_entity_type_ids[0],
        )
    )
    fact = ProviderFact(
        local_id="fact",
        predicate_id=row.relation_id,
        subject_entity_ref="subject",
        object=(literal if literal is not None else ProviderEntityObject(entity_ref="object")),
        assertion_quote=source,
        predicate_anchor_quote=predicate_anchor_quote,
        polarity="positive",
        commitment="asserted",
    )
    return DefaultCatalogProposalFixture(
        row=row,
        source=source,
        subject_quote=subject_quote,
        predicate_anchor_quote=predicate_anchor_quote,
        object_quote=object_quote,
        subject=subject,
        object=object_mention,
        fact=fact,
    )


def _literal(row: DefaultCatalogCorpusRow) -> ProviderLiteralObject | None:
    if row.object_value_type is None:
        return None
    if row.object_value_type == "LocalDate":
        payload = {"source_calendar": "gregorian", "value": "2026-10-03"}
    elif row.object_value_type == "Money":
        payload = {"currency": "USD", "decimal_amount": "12.50"}
    elif row.object_value_type == "TimeInterval":
        payload = {
            "end": "2026-10-03T10:00:00Z",
            "end_bound": "exclusive",
            "start": "2026-10-03T09:00:00Z",
            "start_bound": "closed",
        }
    else:
        payload = CatalogStatusText.parse(
            value_policy_id=row.value_policy_id,
            source_text=(
                "todo" if row.value_policy_id == "work_item_status" else "lead"
            ),
        ).model_dump(mode="json")
    return ProviderLiteralObject(
        literal_type=DEFAULT_CATALOG_LITERAL_TYPES[row.object_value_type].value,
        canonical_value=json.dumps(payload, sort_keys=True, separators=(",", ":")),
        unit=None,
    )


def _literal_quote(row: DefaultCatalogCorpusRow) -> str:
    if row.object_value_type == "LocalDate":
        return "2026-10-03"
    if row.object_value_type == "Money":
        return "USD 12.50"
    if row.object_value_type == "TimeInterval":
        return "2026-10-03T09:00:00+00:00/2026-10-03T10:00:00+00:00"
    return "todo" if row.value_policy_id == "work_item_status" else "lead"
