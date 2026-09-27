"""Runtime endpoint validation for every compiled default-catalog row."""

from __future__ import annotations

import json

import pytest
from memorii.core.memory_evolution.models import ClaimValueType, EntityType
from memorii.core.semantic_ingestion.contracts import (
    ProviderEntityObject,
    ProviderFact,
    ProviderLiteralObject,
    ProviderMention,
    ProviderSemanticProposal,
)
from memorii.core.semantic_ingestion.default_catalog_corpus import (
    DefaultCatalogCorpusRow,
    load_default_catalog_acceptance_corpus,
)
from memorii.core.semantic_ingestion.default_catalog_runtime import (
    DEFAULT_CATALOG_ENTITY_TYPES,
    DEFAULT_CATALOG_LITERAL_TYPES,
    default_catalog_runtime_rows,
    validate_default_catalog_literal_grounding,
    validate_default_catalog_provider_fact,
    validate_default_catalog_provider_proposal,
)
from memorii.core.semantic_ingestion.default_catalog_values import (
    DEFAULT_CATALOG_VALUE_POLICIES,
    CatalogStatusText,
)
from tests.fixtures.semantic_ingestion.default_catalog_proposals import (
    build_default_catalog_proposal,
)


def _canonical(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _literal(row: DefaultCatalogCorpusRow) -> ProviderLiteralObject:
    assert row.object_value_type is not None
    if row.object_value_type == "LocalDate":
        payload = {"source_calendar": "gregorian", "value": "2026-10-03"}
    elif row.object_value_type == "Money":
        payload = {"currency": "USD", "decimal_amount": "12.50"}
    elif row.object_value_type == "TimeInterval":
        payload = {
            "end": "2026-10-03T10:00:00Z", "end_bound": "exclusive",
            "start": "2026-10-03T09:00:00Z", "start_bound": "closed",
        }
    else:
        assert row.value_policy_id in ("work_item_status", "opportunity_stage")
        source = "todo" if row.value_policy_id == "work_item_status" else "lead"
        payload = CatalogStatusText.parse(
            value_policy_id=row.value_policy_id, source_text=source,
        ).model_dump(mode="json")
    return ProviderLiteralObject(
        literal_type=DEFAULT_CATALOG_LITERAL_TYPES[row.object_value_type].value,
        canonical_value=_canonical(payload), unit=None,
    )


def _fact(row: DefaultCatalogCorpusRow) -> tuple[ProviderFact, dict[str, ProviderMention]]:
    mentions = {
        "subject": ProviderMention(
            local_id="subject", mention_quote="subject", mention_context_quote="subject",
            proposed_type=row.subject_type_ids[0],
        ),
    }
    if row.object_value_type is None:
        mentions["object"] = ProviderMention(
            local_id="object", mention_quote="object", mention_context_quote="object",
            proposed_type=row.object_entity_type_ids[0],
        )
        object_value = ProviderEntityObject(entity_ref="object")
    else:
        object_value = _literal(row)
    return ProviderFact(
        local_id="fact", predicate_id=row.relation_id, subject_entity_ref="subject",
        object=object_value, assertion_quote="subject relation object",
        predicate_anchor_quote="relation", polarity="positive", commitment="asserted",
    ), mentions


def test_runtime_registration_exactly_covers_compiled_entity_and_literal_types() -> None:
    corpus = load_default_catalog_acceptance_corpus()

    assert DEFAULT_CATALOG_ENTITY_TYPES == {
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
    assert DEFAULT_CATALOG_LITERAL_TYPES == {
        "LocalDate": ClaimValueType.LOCAL_DATE,
        "Money": ClaimValueType.MONEY,
        "StatusText": ClaimValueType.STATUS_TEXT,
        "TimeInterval": ClaimValueType.TIME_INTERVAL,
    }
    assert set(DEFAULT_CATALOG_ENTITY_TYPES) == {item.type_id for item in corpus.entity_types}
    assert set(DEFAULT_CATALOG_LITERAL_TYPES) == {
        row.object_value_type for row in corpus.rows if row.object_value_type is not None
    }
    assert set(default_catalog_runtime_rows()) == {row.relation_id for row in corpus.rows}


@pytest.mark.parametrize("row", load_default_catalog_acceptance_corpus().rows, ids=lambda row: row.relation_id)
def test_corpus_generated_proposal_passes_real_validator_and_misleading_endpoint_rejects(row: DefaultCatalogCorpusRow) -> None:
    fixture = build_default_catalog_proposal(row)
    assert validate_default_catalog_provider_proposal(fixture.proposal()) == row
    if isinstance(fixture.fact.object, ProviderLiteralObject):
        validate_default_catalog_literal_grounding(
            row=row,
            value=fixture.fact.object,
            object_quote=fixture.object_quote,
        )
    invalid_type = next(
        type_id
        for type_id in ("Animal", "Vehicle", "Subscription", "Recipe")
        if type_id not in row.subject_type_ids
    )
    bad_subject = fixture.subject.model_copy(update={"proposed_type": invalid_type})
    with pytest.raises(ValueError):
        validate_default_catalog_provider_fact(
            fact=fixture.fact,
            mentions={"subject": bad_subject, **({"object": fixture.object} if fixture.object else {})},
        )


@pytest.mark.parametrize(
    "row", load_default_catalog_acceptance_corpus().rows, ids=lambda row: row.relation_id,
)
def test_every_compiled_relation_accepts_its_registered_runtime_endpoints(
    row: DefaultCatalogCorpusRow,
) -> None:
    fact, mentions = _fact(row)

    assert validate_default_catalog_provider_fact(fact=fact, mentions=mentions) == row


def test_runtime_rejects_unknown_relation_wrong_endpoint_and_noncanonical_literal() -> None:
    row = default_catalog_runtime_rows()["work_item_due_on"]
    fact, mentions = _fact(row)

    with pytest.raises(ValueError, match="authority"):
        validate_default_catalog_provider_fact(
            fact=fact.model_copy(update={"predicate_id": "unknown_relation"}), mentions=mentions,
        )
    with pytest.raises(ValueError, match="subject"):
        validate_default_catalog_provider_fact(
            fact=fact,
            mentions={**mentions, "subject": mentions["subject"].model_copy(update={"proposed_type": "Person"})},
        )
    literal = fact.object
    assert isinstance(literal, ProviderLiteralObject)
    with pytest.raises(ValueError, match="literal value"):
        validate_default_catalog_provider_fact(
            fact=fact.model_copy(update={
                "object": literal.model_copy(update={
                    "canonical_value": json.dumps({"value": "2026-10-03", "source_calendar": "gregorian"})
                })
            }),
            mentions=mentions,
        )


def test_status_runtime_requires_the_corpus_policy_digest() -> None:
    row = default_catalog_runtime_rows()["work_item_status"]
    fact, mentions = _fact(row)
    literal = fact.object
    assert isinstance(literal, ProviderLiteralObject)
    payload = json.loads(literal.canonical_value)
    payload["value_policy_digest"] = "0" * 64

    with pytest.raises(ValueError, match="literal value"):
        validate_default_catalog_provider_fact(
            fact=fact.model_copy(update={
                "object": literal.model_copy(update={"canonical_value": _canonical(payload)})
            }),
            mentions=mentions,
        )

    assert row.value_policy_digest == DEFAULT_CATALOG_VALUE_POLICIES["work_item_status"].policy_digest


def test_provider_proposal_validation_runs_before_normalization_and_requires_exact_mentions() -> None:
    row = default_catalog_runtime_rows()["project_has_work_item"]
    fact, mentions = _fact(row)
    proposal = ProviderSemanticProposal(
        mentions=tuple(mentions.values()), facts=(fact,), abstained=False,
    )

    assert validate_default_catalog_provider_proposal(proposal) == row
    with pytest.raises(ValueError, match="mention set"):
        validate_default_catalog_provider_proposal(
            proposal.model_copy(update={
                "mentions": (*proposal.mentions, ProviderMention(
                    local_id="extra", mention_quote="extra", mention_context_quote="extra",
                    proposed_type="Person",
                )),
            })
        )
    with pytest.raises(ValueError, match="commitment"):
        validate_default_catalog_provider_proposal(
            proposal.model_copy(update={
                "facts": (fact.model_copy(update={"commitment": "believed"}),),
            })
        )
