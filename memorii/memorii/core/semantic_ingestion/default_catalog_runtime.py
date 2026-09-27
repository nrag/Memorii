"""Corpus-backed runtime endpoint validation for the default catalog."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from memorii.core.memory_evolution.models import ClaimValueType, EntityType
from memorii.core.semantic_ingestion.contracts import (
    ProviderFact,
    ProviderLiteralObject,
    ProviderMention,
    ProviderSemanticProposal,
)
from memorii.core.semantic_ingestion.default_catalog_corpus import (
    DefaultCatalogAcceptanceCorpus,
    DefaultCatalogCorpusRow,
    load_default_catalog_acceptance_corpus,
)
from memorii.core.semantic_ingestion.default_catalog_values import (
    DEFAULT_CATALOG_VALUE_POLICIES,
    CatalogLocalDate,
    CatalogMoney,
    CatalogStatusText,
    CatalogTimeInterval,
)

DEFAULT_CATALOG_ENTITY_TYPES: dict[str, EntityType] = {
    "Account": EntityType.ACCOUNT,
    "Agreement": EntityType.AGREEMENT,
    "Animal": EntityType.ANIMAL,
    "Appointment": EntityType.APPOINTMENT,
    "Asset": EntityType.ASSET,
    "Bill": EntityType.BILL,
    "Chore": EntityType.CHORE,
    "Decision": EntityType.DECISION,
    "Document": EntityType.DOCUMENT,
    "Event": EntityType.EVENT,
    "Goal": EntityType.GOAL,
    "Group": EntityType.GROUP,
    "Household": EntityType.HOUSEHOLD,
    "Issue": EntityType.ISSUE,
    "Message": EntityType.MESSAGE,
    "Obligation": EntityType.OBLIGATION,
    "Opportunity": EntityType.OPPORTUNITY,
    "Organization": EntityType.ORGANIZATION,
    "Person": EntityType.PERSON,
    "Place": EntityType.PLACE,
    "ProductService": EntityType.PRODUCT_SERVICE,
    "Project": EntityType.PROJECT,
    "Recipe": EntityType.RECIPE,
    "Role": EntityType.ROLE,
    "Subscription": EntityType.SUBSCRIPTION,
    "Vehicle": EntityType.VEHICLE,
    "WorkItem": EntityType.WORK_ITEM,
}

DEFAULT_CATALOG_LITERAL_TYPES: dict[str, ClaimValueType] = {
    "LocalDate": ClaimValueType.LOCAL_DATE,
    "Money": ClaimValueType.MONEY,
    "StatusText": ClaimValueType.STATUS_TEXT,
    "TimeInterval": ClaimValueType.TIME_INTERVAL,
}


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    )


def _decode_literal(row: DefaultCatalogCorpusRow, value: ProviderLiteralObject) -> object:
    if row.object_value_type is None or row.value_policy_id is None:
        raise ValueError("default catalog relation does not accept a literal object")
    expected_type = DEFAULT_CATALOG_LITERAL_TYPES[row.object_value_type]
    if value.literal_type != expected_type.value or value.unit is not None:
        raise ValueError("default catalog literal type is incompatible")
    try:
        payload = json.loads(value.canonical_value)
        if _canonical_json(payload) != value.canonical_value:
            raise ValueError("default catalog literal bytes are not canonical")
        if row.object_value_type == "LocalDate":
            decoded = CatalogLocalDate.model_validate(payload)
        elif row.object_value_type == "Money":
            decoded = CatalogMoney.model_validate(payload)
        elif row.object_value_type == "TimeInterval":
            decoded = CatalogTimeInterval.model_validate(payload)
        else:
            decoded = CatalogStatusText.decode(
                payload,
                historical_policies=(DEFAULT_CATALOG_VALUE_POLICIES[row.value_policy_id],),
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("default catalog literal value is invalid") from exc
    if row.value_policy_digest != DEFAULT_CATALOG_VALUE_POLICIES[row.value_policy_id].policy_digest:
        raise ValueError("default catalog literal policy is substituted")
    return decoded


@lru_cache(maxsize=1)
def default_catalog_runtime_rows() -> dict[str, DefaultCatalogCorpusRow]:
    corpus: DefaultCatalogAcceptanceCorpus = load_default_catalog_acceptance_corpus()
    if set(DEFAULT_CATALOG_ENTITY_TYPES) != {item.type_id for item in corpus.entity_types}:
        raise ValueError("default catalog entity runtime registration is incomplete")
    if set(DEFAULT_CATALOG_LITERAL_TYPES) != {
        row.object_value_type for row in corpus.rows if row.object_value_type is not None
    }:
        raise ValueError("default catalog literal runtime registration is incomplete")
    return {row.relation_id: row for row in corpus.rows}


def validate_default_catalog_provider_fact(
    *,
    fact: ProviderFact,
    mentions: dict[str, ProviderMention],
) -> DefaultCatalogCorpusRow:
    """Validate one provider fact against the compiled relation endpoint authority."""
    try:
        row = default_catalog_runtime_rows()[fact.predicate_id]
        subject = mentions[fact.subject_entity_ref]
    except KeyError as exc:
        raise ValueError("default catalog fact authority is absent") from exc
    if subject.proposed_type not in row.subject_type_ids:
        raise ValueError("default catalog subject type is incompatible")
    if isinstance(fact.object, ProviderLiteralObject):
        _decode_literal(row, fact.object)
    else:
        try:
            object_mention = mentions[fact.object.entity_ref]
        except KeyError as exc:
            raise ValueError("default catalog object authority is absent") from exc
        if (
            row.object_value_type is not None
            or object_mention.proposed_type not in row.object_entity_type_ids
        ):
            raise ValueError("default catalog object type is incompatible")
    return row


def validate_default_catalog_provider_proposal(
    proposal: ProviderSemanticProposal,
) -> DefaultCatalogCorpusRow:
    """Validate the fact-only proposal shape before Bootstrap V3 normalization."""
    if (
        proposal.abstained
        or len(proposal.facts) != 1
        or proposal.corrections
        or proposal.retractions
        or proposal.action_states
        or proposal.identity_operations
    ):
        raise ValueError("default catalog proposal is outside the fact-only grammar")
    fact = proposal.facts[0]
    if (
        fact.commitment != "asserted"
        or fact.attributed_to_entity_ref is not None
        or fact.polarity != "positive"
    ):
        raise ValueError("default catalog fact commitment is invalid")
    mentions = {mention.local_id: mention for mention in proposal.mentions}
    referenced = {fact.subject_entity_ref}
    if not isinstance(fact.object, ProviderLiteralObject):
        referenced.add(fact.object.entity_ref)
    if set(mentions) != referenced:
        raise ValueError("default catalog proposal mention set is not exact")
    return validate_default_catalog_provider_fact(fact=fact, mentions=mentions)


def validate_default_catalog_literal_grounding(
    *, row: DefaultCatalogCorpusRow, value: ProviderLiteralObject, object_quote: str,
) -> None:
    """Require the source object span to deterministically encode the typed value."""
    decoded = _decode_literal(row, value)
    if isinstance(decoded, CatalogLocalDate):
        expected = decoded.value.isoformat()
    elif isinstance(decoded, CatalogMoney):
        expected = f"{decoded.currency} {decoded.decimal_amount}"
    elif isinstance(decoded, CatalogTimeInterval):
        start = ".." if decoded.start is None else decoded.start.isoformat()
        end = ".." if decoded.end is None else decoded.end.isoformat()
        expected = f"{start}/{end}"
    else:
        assert isinstance(decoded, CatalogStatusText)
        parsed = CatalogStatusText.parse(
            value_policy_id=decoded.value_policy_id, source_text=object_quote,
        )
        if parsed != decoded:
            raise ValueError("default catalog literal is not grounded by its source quote")
        return
    if object_quote != expected:
        raise ValueError("default catalog literal is not grounded by its source quote")


__all__ = [
    "DEFAULT_CATALOG_ENTITY_TYPES",
    "DEFAULT_CATALOG_LITERAL_TYPES",
    "default_catalog_runtime_rows",
    "validate_default_catalog_provider_fact",
    "validate_default_catalog_literal_grounding",
    "validate_default_catalog_provider_proposal",
]
