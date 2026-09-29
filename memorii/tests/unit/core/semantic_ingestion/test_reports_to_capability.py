from __future__ import annotations

import json
from hashlib import sha256
from types import SimpleNamespace
from typing import cast

import pytest
from memorii.core.semantic_ingestion.catalog_authority import (
    AuthenticatedPrincipalAgent,
    CatalogAuthorityScope,
    CatalogOwnerVisibilityGrant,
    FactScopeGrant,
    StructuredClaimCatalogBinding,
    StructuredFactReadAuthority,
    StructuredGrantState,
)
from memorii.core.semantic_ingestion.contracts import (
    BootstrapSemanticProposalRequestV3,
    ProviderEntityObject,
    ProviderFact,
    ProviderMention,
    ProviderSemanticProposal,
)
from memorii.core.semantic_ingestion.reports_to_capability import (
    REPORTS_TO_OUTPUT_SCHEMA,
    ReportsToProviderProposalAdapter,
    validate_reports_to_tool_proposal,
)
from memorii.core.semantic_ingestion.reports_to_state import (
    ReportsToCatalogMeaning,
    ReportsToCurrentReadGrant,
    ReportsToHistoryEntry,
    ReportsToLine,
    ReportsToPolicyError,
    ReportsToProtectedReader,
    reports_to_state_rule,
    reports_to_temporal_rule,
    reports_to_trust_rule,
)
from pydantic import ValidationError


class _Quotes:
    def __init__(self, text: str) -> None:
        self.text = text

    def __call__(self, quote, context, _owned):
        if context.text.count(quote) != 1:
            raise ValueError("quote is not unique")
        return SimpleNamespace(text=quote, projection_digest=context.projection_digest)

    def verify_quote(self, **_kwargs) -> None:
        return None


def _request(text: str, *, reports_to_available: bool = True) -> BootstrapSemanticProposalRequestV3:
    return cast(
        BootstrapSemanticProposalRequestV3,
        SimpleNamespace(
            segment=SimpleNamespace(
                source_id="source", segment_id="segment",
                context_text=SimpleNamespace(text=text, projection_digest="b" * 64),
            ),
            owned_source_spans=(),
            predicate_catalog=SimpleNamespace(predicates=tuple(
                SimpleNamespace(predicate_id=predicate_id)
                for predicate_id in (("reports_to",) if reports_to_available else ("project_owner",))
            )),
        ),
    )


def _adapter(text: str) -> ReportsToProviderProposalAdapter:
    quotes = _Quotes(text)
    return ReportsToProviderProposalAdapter(
        semantic_contract_digest="a" * 64, resolve_quote=quotes, projection_quote_verifier=quotes,
    )


def _response(text: str, *, subject: str = "Alice", object: str = "Bob") -> str:
    return json.dumps({"abstained": False, "candidates": [{
        "predicate_id": "reports_to", "assertion_quote": text, "subject_quote": subject,
        "predicate_anchor_quote": "reports to", "object_quote": object,
    }]})


def test_direct_reporting_line_compiles_to_two_person_entity_fact() -> None:
    text = "Alice reports to Bob."
    proposal = _adapter(text).from_response(request=_request(text), response_text=_response(text))

    assert proposal is not None and proposal.abstained is False
    assert proposal.facts[0].predicate_id == "reports_to"
    assert proposal.facts[0].object.kind == "entity"
    assert tuple(mention.proposed_type for mention in proposal.mentions) == ("PersonName", "PersonName")
    validate_reports_to_tool_proposal(proposal)


@pytest.mark.parametrize(
    "text",
    (
        "Alice collaborates with Bob.",
        'Alice said "Bob reports to Carol."',
        "If Alice reports to Bob, we will update the chart.",
        "Does Alice report to Bob?",
    ),
)
def test_collaboration_quoted_and_hypothetical_near_misses_abstain(text: str) -> None:
    proposal = _adapter(text).from_response(request=_request(text), response_text=_response(text))

    assert proposal is not None
    assert proposal == ProviderSemanticProposal(abstained=True)


def test_adapter_refuses_an_unselected_predicate_catalog() -> None:
    text = "Alice reports to Bob."
    assert _adapter(text).from_response(
        request=_request(text, reports_to_available=False), response_text=_response(text),
    ) is None


def test_prompt_schema_is_closed_to_the_direct_relation() -> None:
    candidate = REPORTS_TO_OUTPUT_SCHEMA["properties"]["candidates"]
    assert isinstance(candidate, dict)
    items = candidate["items"]
    assert isinstance(items, dict)
    properties = items["properties"]
    assert isinstance(properties, dict)
    assert properties["predicate_id"] == {"type": "string", "const": "reports_to"}
    assert properties["predicate_anchor_quote"] == {"type": "string", "const": "reports to"}


def _external_proposal(
    assertion: str,
    *,
    anchor: str = "reports to",
    commitment: str = "asserted",
    qualifier: tuple[str, ...] = (),
    subject: str = "Alice",
    object: str = "Bob",
) -> ProviderSemanticProposal:
    return ProviderSemanticProposal(
        mentions=(
            ProviderMention(local_id="subject", mention_quote=subject, mention_context_quote=assertion, proposed_type="PersonName"),
            ProviderMention(local_id="object", mention_quote=object, mention_context_quote=assertion, proposed_type="PersonName"),
        ),
        facts=(ProviderFact(
            local_id="fact", predicate_id="reports_to", subject_entity_ref="subject",
            object=ProviderEntityObject(entity_ref="object"), assertion_quote=assertion,
            predicate_anchor_quote=anchor, polarity="positive", commitment=commitment,
            temporal_qualifier_quotes=qualifier,
        ),),
        abstained=False,
    )


@pytest.mark.parametrize(
    ("proposal", "reason"),
    (
        (_external_proposal("Alice collaborates with Bob.", anchor="collaborates with"), "relation shape"),
        (_external_proposal('Alice said "Bob reports to Carol."'), "direct reporting line"),
        (_external_proposal("If Alice reports to Bob, we will update the chart."), "direct reporting line"),
        (_external_proposal("Bob reports to Alice."), "direct reporting line"),
        (_external_proposal("Alice reports to Bob.", qualifier=("today",)), "relation shape"),
        (_external_proposal("Alice reports to Bob.", commitment="quoted"), "relation shape"),
    ),
)
def test_tool_grammar_rejects_external_non_direct_or_qualified_proposals(
    proposal: ProviderSemanticProposal, reason: str,
) -> None:
    with pytest.raises(ValueError, match=reason):
        validate_reports_to_tool_proposal(proposal)


def _meaning() -> ReportsToCatalogMeaning:
    return ReportsToCatalogMeaning(
        catalog_scope=CatalogAuthorityScope(schema_version=1, kind="base"),
        catalog_digest="a" * 64, child_version_digest="b" * 64, runtime_bundle_digest="c" * 64,
    )


def _grant(meaning: ReportsToCatalogMeaning | None = None) -> ReportsToCurrentReadGrant:
    authenticated = AuthenticatedPrincipalAgent(principal_id="principal:alice", agent_id="agent:alice")
    fact_grant = FactScopeGrant(
        grant_id="fact", grant_version=1, fact_scope="user:alice", authenticated=authenticated,
    )
    visibility_grant = CatalogOwnerVisibilityGrant(
        grant_id="visibility", grant_version=1, catalog_scope=CatalogAuthorityScope(schema_version=1, kind="base"),
        authenticated=authenticated, purpose="visibility_status",
    )
    return ReportsToCurrentReadGrant(
        read_authority=StructuredFactReadAuthority(
            authenticated=authenticated, fact_grant=fact_grant, catalog_visibility_grant=visibility_grant,
        ),
        fact_grant_state=StructuredGrantState(
            schema_version=1, grant_kind="fact", grant=fact_grant, active=True,
        ),
        catalog_visibility_grant_state=StructuredGrantState(
            schema_version=1, grant_kind="catalog_visibility", grant=visibility_grant, active=True,
        ),
        meaning=meaning or _meaning(),
    )


def _line(claim_id: str, subject: str, manager: str, *, meaning: ReportsToCatalogMeaning | None = None) -> ReportsToLine:
    from datetime import UTC, datetime

    actual_meaning = meaning or _meaning()
    authenticated = AuthenticatedPrincipalAgent(principal_id="principal:alice", agent_id="agent:alice")
    digest = sha256(claim_id.encode("utf-8")).hexdigest()
    return ReportsToLine(
        claim_id=claim_id, subject_person_id=subject, manager_person_id=manager,
        claim_record_digest=digest, asserted_at=datetime(2026, 9, 26, tzinfo=UTC), meaning=actual_meaning,
        catalog_binding=StructuredClaimCatalogBinding(
            schema_version=1, claim_assertion_id=claim_id, claim_record_digest=digest,
            catalog_scope=actual_meaning.catalog_scope, catalog_digest=actual_meaning.catalog_digest,
            fact_scope="user:alice", authenticated=authenticated,
        ),
    )


def test_reports_to_state_is_multi_set_and_distinct_from_project_owner_single_current() -> None:
    rule = reports_to_state_rule()
    assert (rule.predicate_id, rule.cardinality, rule.conflict_behavior) == (
        "reports_to", "multi", "accumulate_distinct_values",
    )
    history = (
        ReportsToHistoryEntry(event_id="assert-1", event_kind="asserted", line=_line("one", "alice", "bob")),
        ReportsToHistoryEntry(event_id="assert-2", event_kind="asserted", line=_line("two", "alice", "carol")),
    )
    assert [line.manager_person_id for line in ReportsToProtectedReader().read_current(history=history, grant=_grant())] == [
        "bob", "carol",
    ]


def test_reports_to_correction_and_retraction_preserve_history_and_update_active_set() -> None:
    original = _line("one", "alice", "bob")
    replacement = _line("two", "alice", "carol")
    history = (
        ReportsToHistoryEntry(event_id="assert", event_kind="asserted", line=original),
        ReportsToHistoryEntry(event_id="correct", event_kind="corrected", line=replacement, prior_claim_id="one"),
        ReportsToHistoryEntry(event_id="retract", event_kind="retracted", prior_claim_id="two"),
    )
    assert ReportsToProtectedReader().read_current(history=history, grant=_grant()) == ()
    assert tuple(entry.event_id for entry in history) == ("assert", "correct", "retract")


def test_reports_to_reader_denies_duplicate_active_line_and_duplicate_target_correction() -> None:
    reader = ReportsToProtectedReader()
    duplicate = (
        ReportsToHistoryEntry(event_id="first", event_kind="asserted", line=_line("one", "alice", "bob")),
        ReportsToHistoryEntry(event_id="second", event_kind="asserted", line=_line("two", "alice", "bob")),
    )
    with pytest.raises(ReportsToPolicyError, match="active reporting line is duplicated"):
        reader.read_current(history=duplicate, grant=_grant())
    correction = (
        ReportsToHistoryEntry(event_id="first", event_kind="asserted", line=_line("one", "alice", "bob")),
        ReportsToHistoryEntry(event_id="second", event_kind="asserted", line=_line("two", "alice", "carol")),
        ReportsToHistoryEntry(event_id="correct", event_kind="corrected", line=_line("three", "alice", "carol"), prior_claim_id="one"),
    )
    with pytest.raises(ReportsToPolicyError, match="correction duplicates an active reporting line"):
        reader.read_current(history=correction, grant=_grant())


def test_reports_to_reader_denies_mallory_fact_scope_even_with_matching_catalog() -> None:
    line = _line("one", "alice", "bob")
    history = (ReportsToHistoryEntry(event_id="assert", event_kind="asserted", line=line),)
    authenticated = AuthenticatedPrincipalAgent(principal_id="principal:mallory", agent_id="agent:mallory")
    fact = FactScopeGrant(grant_id="mallory", grant_version=1, fact_scope="user:mallory", authenticated=authenticated)
    visibility = CatalogOwnerVisibilityGrant(
        grant_id="mallory-visibility", grant_version=1, catalog_scope=_meaning().catalog_scope,
        authenticated=authenticated, purpose="visibility_status",
    )
    wrong_grant = ReportsToCurrentReadGrant(
        read_authority=StructuredFactReadAuthority(
            authenticated=authenticated, fact_grant=fact, catalog_visibility_grant=visibility,
        ),
        fact_grant_state=StructuredGrantState(schema_version=1, grant_kind="fact", grant=fact, active=True),
        catalog_visibility_grant_state=StructuredGrantState(
            schema_version=1, grant_kind="catalog_visibility", grant=visibility, active=True,
        ),
        meaning=_meaning(),
    )
    with pytest.raises(ReportsToPolicyError, match="historical catalog meaning is unavailable"):
        ReportsToProtectedReader().read_current(history=history, grant=wrong_grant)


def test_reports_to_current_read_grant_rejects_a_revoked_durable_grant_state() -> None:
    payload = _grant().model_dump(mode="json")
    fact_state = payload["fact_grant_state"]
    assert isinstance(fact_state, dict)
    fact_state["active"] = False
    with pytest.raises(ValidationError, match="current grants do not bind"):
        ReportsToCurrentReadGrant.model_validate(payload)


def test_reports_to_reader_denies_missing_historical_child_or_current_grant_meaning() -> None:
    line = _line("one", "alice", "bob")
    history = (ReportsToHistoryEntry(event_id="assert", event_kind="asserted", line=line),)
    mismatched = _meaning().model_copy(update={"child_version_digest": "d" * 64})
    with pytest.raises(ReportsToPolicyError, match="historical catalog meaning is unavailable"):
        ReportsToProtectedReader().read_current(history=history, grant=_grant(mismatched))


def test_reports_to_policy_is_direct_trust_and_optional_temporal() -> None:
    assert reports_to_trust_rule().eligible_authority_classes == frozenset({"official"})
    assert reports_to_temporal_rule().valid_time_requirement == "optional"
