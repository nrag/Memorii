from __future__ import annotations

import json
import queue
import threading
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace

import memorii.core.semantic_ingestion.hermes_completed_turn_runtime as hermes_runtime_module
import pytest
from jsonschema import Draft202012Validator
from memorii.core.semantic_ingestion.catalog_authority import (
    StructuredSubmissionAuthorityRequest,
    ThreePredicateSeedCatalogAuthorityRepository,
)
from memorii.core.semantic_ingestion.catalog_capture_pin import (
    CatalogCapturedTurnPin,
    SeedCatalogBundleLocator,
    VerifiedCatalogBundle,
)
from memorii.core.semantic_ingestion.contracts import (
    ProjectionTextSpan,
    ProviderCorrection,
    ProviderEntityObject,
    ProviderRetraction,
    ProviderSemanticProposal,
    RetainedSourceTextArtifact,
    RetainedSourceTextSpan,
    SegmentLocalTextArtifact,
    SegmentLocalTextSpan,
    SemanticProjectionTextArtifact,
    SourceSpanReference,
    VerbatimTextArtifactMappingProof,
)
from memorii.core.semantic_ingestion.default_catalog_corpus import (
    DefaultCatalogCorpusRow,
    load_default_catalog_acceptance_corpus,
)
from memorii.core.semantic_ingestion.default_catalog_values import CatalogStatusText
from memorii.core.semantic_ingestion.hermes_captured_turn import HermesCapturedTurnLedger
from memorii.core.semantic_ingestion.hermes_completed_turn_runtime import (
    HermesCompletedTurnRuntime,
    _canonical_messages_digest,
    _canonicalize_completed_messages,
    _CapturedTurnHandle,
    _CompletedTurnWork,
    _default_catalog_fact_only_proposal_schema,
    _json_arrays_to_tuples,
    _validate_default_catalog_argument_shape,
)
from memorii.core.semantic_ingestion.reports_to_capability import validate_reports_to_tool_proposal
from tests.fixtures.semantic_ingestion.default_catalog_proposals import (
    build_default_catalog_proposal,
)
from tests.fixtures.semantic_ingestion.scenario_fixture_authority import (
    build_verified_reports_to_scenario_request_catalog,
)


def _worker_runtime() -> HermesCompletedTurnRuntime:
    """Construct only the isolated worker boundary used by recovery tests."""
    runtime = object.__new__(HermesCompletedTurnRuntime)
    runtime._work = queue.Queue()
    runtime._condition = threading.Condition()
    runtime._outstanding = 0
    runtime._failures = []
    runtime._closed = False
    runtime._stopped = False
    runtime._worker = threading.Thread(target=runtime._worker_loop, daemon=True)
    runtime._worker.start()
    return runtime


def _active_capture_runtime() -> HermesCompletedTurnRuntime:
    runtime = object.__new__(HermesCompletedTurnRuntime)
    runtime._condition = threading.Condition()
    runtime._closed = False
    runtime._active_turn_ambiguous = False
    runtime._authenticated_author_id = "operator:ada"
    runtime._require_current_authority = lambda: None
    runtime._issue_host_ingress = lambda *_args: object()
    runtime._active_tool_calls = 0
    now = datetime(2026, 9, 26, tzinfo=UTC)
    message = "Atlas owner is Ada."
    digest = sha256(message.encode()).hexdigest()
    ledger = HermesCapturedTurnLedger(
        installation_id="install:a", session_id="session:a", principal_id="operator:ada", agent_id="agent:a",
        turn_ordinal=1, message_digest=digest, source_id="source:a", source_digest="a" * 64,
        preparation_fingerprint="b" * 64, captured_at=now,
    )
    runtime._active_turn = _CapturedTurnHandle(
        session_id="session:a", turn_ordinal=1, message_digest=digest,
        admission=object(), ledger=ledger, generation="generation", expires_at=now + timedelta(minutes=1),
    )
    seed_pin = CatalogCapturedTurnPin.seed(
        ledger=ledger, bundle=SeedCatalogBundleLocator().locate(), selection_pointer_digest="d" * 64,
    )
    runtime._service = SimpleNamespace(
        pin_captured_turn_catalog=lambda **_kwargs: seed_pin,
        load_captured_turn_catalog_pin=lambda **_kwargs: seed_pin,
        resolve_captured_turn_catalog_dispatch=lambda **_kwargs: "seed",
    )
    return runtime


def test_captured_turn_tool_access_last_thirty_minutes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert timedelta(minutes=30) == hermes_runtime_module._CAPTURED_TURN_TTL
    runtime = _active_capture_runtime()
    captured_at = datetime(2026, 9, 26, tzinfo=UTC)
    active = runtime._active_turn
    assert active is not None
    runtime._active_turn = active.__class__(
        **(active.__dict__ | {"expires_at": captured_at + timedelta(minutes=30)})
    )
    runtime._structured_authority_request = object()

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is UTC
            return captured_at + timedelta(minutes=16)

    monkeypatch.setattr(hermes_runtime_module, "datetime", Clock)
    assert runtime._acquire_active_tool_turn() is runtime._active_turn
    assert runtime._active_tool_calls == 1
    with runtime._condition:
        runtime._active_tool_calls -= 1
        runtime._condition.notify_all()

    class ExpiredClock(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is UTC
            return captured_at + timedelta(minutes=30)

    monkeypatch.setattr(hermes_runtime_module, "datetime", ExpiredClock)
    assert runtime._acquire_active_tool_turn() is None
    assert runtime._active_tool_calls == 0


def _real_source_span(*, source_id: str, text: str = "Alice reports to Bob.") -> SourceSpanReference:
    digest = sha256(text.encode()).hexdigest()
    retained = RetainedSourceTextArtifact.create(
        artifact_id="retained-reports", content_digest=digest, unicode_scalar_length=len(text),
    )
    projection = SemanticProjectionTextArtifact.create(
        artifact_id="projection-reports", content_digest=digest, unicode_scalar_length=len(text),
    )
    segment = SegmentLocalTextArtifact.create(
        artifact_id="segment-reports", content_digest=digest, unicode_scalar_length=len(text),
        projection_segment_id="segment:reports",
    )
    retained_span = RetainedSourceTextSpan.create(artifact=retained, start=0, end=len(text), substring_digest=digest)
    projection_span = ProjectionTextSpan.create(artifact=projection, start=0, end=len(text), substring_digest=digest)
    segment_span = SegmentLocalTextSpan.create(artifact=segment, start=0, end=len(text), substring_digest=digest)
    proof = VerbatimTextArtifactMappingProof.create(
        retained_span=retained_span, projection_span=projection_span, segment_span=segment_span,
    )
    return SourceSpanReference.create(
        source_id=source_id, projection_digest=projection.artifact_digest,
        projection_segment_id="segment:reports", retained_text_artifact=retained,
        projection_span=projection_span, segment_local_span=segment_span,
        text_mapping_proof=proof, source_reference=None,
    )


def test_capture_callback_reuses_exact_handle_and_denies_changed_or_overlapping_context() -> None:
    runtime = _active_capture_runtime()
    now = datetime(2026, 9, 26, tzinfo=UTC)

    runtime.capture_user_turn(
        session_id="session:a", turn_ordinal=1, message="Atlas owner is Ada.",
        authenticated_author_id="operator:ada", received_at=now,
    )
    with pytest.raises(ValueError, match="overlapping turn context"):
        runtime.capture_user_turn(
            session_id="session:a", turn_ordinal=1, message="Atlas owner is Bob.",
            authenticated_author_id="operator:ada", received_at=now,
        )
    assert runtime._active_turn_ambiguous
    with pytest.raises(ValueError, match="mismatched or ambiguous"):
        runtime.complete_captured_turn(
            user_content="Atlas owner is Ada.", assistant_content="Acknowledged.", messages=None,
            session_id="session:a", authenticated_author_id="operator:ada", received_at=now,
        )


def test_structured_tool_is_closed_and_requires_an_active_captured_turn() -> None:
    runtime = _active_capture_runtime()
    runtime._active_turn = runtime._active_turn.__class__(
        **(runtime._active_turn.__dict__ | {"expires_at": datetime.now(UTC) + timedelta(minutes=1)})
    )
    runtime._structured_authority_request = object()
    runtime._structured_tool_is_current = lambda: True
    runtime._active_tool_calls = 0

    schemas = runtime.get_tool_schemas()

    assert schemas[0]["function"]["name"] == "memorii_submit_fact"
    parameters = schemas[0]["function"]["parameters"]
    assert parameters["additionalProperties"] is False
    assert parameters["properties"]["schema_version"]["const"] == 1
    assert runtime.handle_tool_call(tool_name="memorii_submit_fact", arguments={"schema_version": 2}) == {
        "status": "rejected"
    }
    assert runtime.handle_tool_call(tool_name="memorii_submit_fact", arguments={"schema_version": True}) == {
        "status": "rejected"
    }
    assert runtime._active_tool_calls == 0

    runtime._active_turn = None
    assert runtime.get_tool_schemas() == []
    assert runtime.handle_tool_call(tool_name="memorii_submit_fact", arguments={}) == {"status": "unavailable"}


def test_schema_egress_is_withheld_when_the_core_catalog_pin_is_unavailable() -> None:
    runtime = _active_capture_runtime()
    runtime._active_turn = runtime._active_turn.__class__(
        **(runtime._active_turn.__dict__ | {"expires_at": datetime.now(UTC) + timedelta(minutes=1)})
    )
    runtime._structured_authority_request = object()
    runtime._structured_tool_is_current = lambda: True
    runtime._service = SimpleNamespace(pin_captured_turn_catalog=lambda **_kwargs: None)

    assert runtime.get_tool_schemas() == []


def test_tool_call_loads_an_existing_pin_without_creating_one() -> None:
    runtime = _active_capture_runtime()
    active = runtime._active_turn
    assert active is not None
    runtime._active_turn = active.__class__(
        **(active.__dict__ | {"expires_at": datetime.now(UTC) + timedelta(minutes=1)})
    )
    runtime._structured_authority_request = object()
    runtime._structured_tool_is_current = lambda: True
    pin = CatalogCapturedTurnPin.seed(
        ledger=active.ledger, bundle=SeedCatalogBundleLocator().locate(),
        selection_pointer_digest="d" * 64,
    )
    calls: list[str] = []

    class _Request:
        def model_copy(self, *, update: dict[str, object]) -> _Request:
            assert update["captured_pin"] is not None
            return self

    runtime._structured_tool_request = lambda **_kwargs: _Request()
    submissions = 0

    def submit(*_args: object, **_kwargs: object) -> SimpleNamespace:
        nonlocal submissions
        submissions += 1
        return SimpleNamespace(status="committed", operation_id=f"operation:{submissions}")

    runtime._service = SimpleNamespace(
        load_captured_turn_catalog_pin=lambda **_kwargs: calls.append("load") or pin,
        resolve_captured_turn_catalog_dispatch=lambda **_kwargs: "seed",
        submit_structured_fact=submit,
        pin_captured_turn_catalog=lambda **_kwargs: pytest.fail("tool call must not create a pin"),
    )

    assert runtime.handle_tool_call(tool_name="memorii_submit_fact", arguments={}) == {
        "status": "committed", "operation_id": "operation:1",
    }
    assert runtime.handle_tool_call(tool_name="memorii_submit_fact", arguments={}) == {
        "status": "committed", "operation_id": "operation:2",
    }
    assert calls == ["load", "load"]


def test_advertised_structured_tool_schema_matches_entity_and_literal_branches() -> None:
    runtime = _active_capture_runtime()
    runtime._active_turn = runtime._active_turn.__class__(
        **(runtime._active_turn.__dict__ | {"expires_at": datetime.now(UTC) + timedelta(minutes=1)})
    )
    runtime._structured_authority_request = object()
    runtime._structured_tool_is_current = lambda: True
    proposal_schema = runtime.get_tool_schemas()[0]["function"]["parameters"]["properties"]["proposal"]
    validator = Draft202012Validator(proposal_schema)
    common = {
        "abstained": False,
        "corrections": [], "retractions": [], "action_states": [], "identity_operations": [],
    }
    owner = common | {
        "mentions": [
            {"local_id": "atlas", "mention_quote": "Atlas", "mention_context_quote": "Atlas owner Ada.", "proposed_type": None},
            {"local_id": "ada", "mention_quote": "Ada", "mention_context_quote": "Atlas owner Ada.", "proposed_type": None},
        ],
        "facts": [{
            "kind": "fact", "local_id": "owner", "predicate_id": "project_owner",
            "subject_entity_ref": "atlas", "object": {"kind": "entity", "entity_ref": "ada"},
            "assertion_quote": "Atlas owner Ada.", "predicate_anchor_quote": "owner",
            "polarity": "positive", "commitment": "asserted", "attributed_to_entity_ref": None,
            "temporal_qualifier_quotes": [],
        }],
    }
    status = common | {
        "mentions": [
            {"local_id": "atlas", "mention_quote": "Atlas", "mention_context_quote": "Atlas status active.", "proposed_type": None},
        ],
        "facts": [{
            "kind": "fact", "local_id": "status", "predicate_id": "project_status",
            "subject_entity_ref": "atlas", "object": {"kind": "literal", "literal_type": "text", "canonical_value": "active", "unit": None},
            "assertion_quote": "Atlas status active.", "predicate_anchor_quote": "status",
            "polarity": "positive", "commitment": "asserted", "attributed_to_entity_ref": None,
            "temporal_qualifier_quotes": [],
        }],
    }
    deadline = common | {
        "mentions": [
            {"local_id": "atlas", "mention_quote": "Atlas", "mention_context_quote": "Atlas deadline 2026-10-01.", "proposed_type": None},
        ],
        "facts": [{
            "kind": "fact", "local_id": "deadline", "predicate_id": "project_deadline",
            "subject_entity_ref": "atlas", "object": {"kind": "literal", "literal_type": "date", "canonical_value": "2026-10-01", "unit": None},
            "assertion_quote": "Atlas deadline 2026-10-01.", "predicate_anchor_quote": "deadline",
            "polarity": "positive", "commitment": "asserted", "attributed_to_entity_ref": None,
            "temporal_qualifier_quotes": [],
        }],
    }
    assert not list(validator.iter_errors(owner))
    assert not list(validator.iter_errors(status))
    assert not list(validator.iter_errors(deadline))
    assert list(validator.iter_errors(owner | {"mentions": owner["mentions"][:1]}))
    assert list(validator.iter_errors(status | {"facts": [{**status["facts"][0], "object": {"kind": "entity", "entity_ref": "ada"}}]}))
    assert list(validator.iter_errors(status | {"facts": [{**status["facts"][0], "object": {**status["facts"][0]["object"], "literal_type": "date"}}]}))
    assert list(validator.iter_errors(deadline | {"facts": [{**deadline["facts"][0], "object": {**deadline["facts"][0]["object"], "literal_type": "text"}}]}))


def test_verified_reports_to_pin_advertises_and_dispatches_only_the_closed_child_grammar() -> None:
    runtime = _active_capture_runtime()
    active = runtime._active_turn
    assert active is not None
    runtime._active_turn = active.__class__(
        **(active.__dict__ | {"expires_at": datetime.now(UTC) + timedelta(minutes=1)})
    )
    runtime._structured_authority_request = object()
    runtime._structured_tool_is_current = lambda: True
    scenario = build_verified_reports_to_scenario_request_catalog()
    release = scenario.release
    pin = CatalogCapturedTurnPin.from_bundle(
        ledger=active.ledger,
        bundle=VerifiedCatalogBundle(
            catalog=ThreePredicateSeedCatalogAuthorityRepository().resolve_base(),
            version=release.child_version,
            runtime_bundle_digest=release.runtime_bundle_digest,
        ),
        selection_pointer_digest="e" * 64,
    )
    calls: list[str] = []

    class _Request:
        def model_copy(self, *, update: dict[str, object]) -> _Request:
            assert update["captured_pin"] is not None
            return self

    def parse(**kwargs: object) -> _Request:
        calls.append("parse")
        assert kwargs["reports_to"] is True
        return _Request()

    runtime._structured_tool_request = parse
    runtime._service = SimpleNamespace(
        pin_captured_turn_catalog=lambda **_kwargs: pin,
        load_captured_turn_catalog_pin=lambda **_kwargs: calls.append("pin") or pin,
        resolve_captured_turn_catalog_dispatch=lambda **_kwargs: "reports_to",
        submit_structured_fact=lambda *_args, **_kwargs: SimpleNamespace(
            status="committed", operation_id="operation:reports-to"
        ),
    )

    schema = runtime.get_tool_schemas()[0]["function"]["parameters"]["properties"]["proposal"]
    assert schema["properties"]["facts"]["items"]["properties"]["predicate_id"] == {"const": "reports_to"}
    runtime._structured_authority_request = StructuredSubmissionAuthorityRequest.model_construct()
    runtime._load_active_prepared_source = lambda _active: object()
    runtime._resolve_sentence_span = lambda **_kwargs: _real_source_span(source_id=active.ledger.source_id)
    direct_arguments = {
        "schema_version": 1, "source_quote": "Alice reports to Bob.", "source_quote_start": 0,
        "subject_quote": "Alice", "predicate_anchor_quote": "reports to", "object_quote": "Bob",
        "proposal": {"abstained": False, "mentions": [
            {"local_id": "alice", "mention_quote": "Alice", "mention_context_quote": "Alice reports to Bob.", "proposed_type": "PersonName"},
            {"local_id": "bob", "mention_quote": "Bob", "mention_context_quote": "Alice reports to Bob.", "proposed_type": "PersonName"},
        ], "facts": [{"kind": "fact", "local_id": "reports", "predicate_id": "reports_to", "subject_entity_ref": "alice", "object": {"kind": "entity", "entity_ref": "bob"}, "assertion_quote": "Alice reports to Bob.", "predicate_anchor_quote": "reports to", "polarity": "positive", "commitment": "asserted", "attributed_to_entity_ref": None, "temporal_qualifier_quotes": []}], "corrections": [], "retractions": [], "action_states": [], "identity_operations": []},
    }
    request = HermesCompletedTurnRuntime._structured_tool_request(
        runtime, active=active, arguments=direct_arguments, reports_to=True,
    )
    assert request.proposal.facts[0].predicate_id == "reports_to"
    assert tuple(mention.proposed_type for mention in request.proposal.mentions) == ("PersonName", "PersonName")
    runtime._structured_authority_request = object()
    assert runtime.handle_tool_call(tool_name="memorii_submit_fact", arguments={}) == {
        "status": "committed", "operation_id": "operation:reports-to"
    }
    assert calls == ["pin", "parse"]


def test_default_catalog_dispatch_advertises_corpus_and_validates_before_normalization() -> None:
    runtime = _active_capture_runtime()
    active = runtime._active_turn
    assert active is not None
    runtime._active_turn = active.__class__(
        **(active.__dict__ | {"expires_at": datetime.now(UTC) + timedelta(minutes=1)})
    )
    runtime._structured_authority_request = object()
    runtime._structured_tool_is_current = lambda: True
    pin = runtime._service.pin_captured_turn_catalog()
    runtime._service = SimpleNamespace(
        pin_captured_turn_catalog=lambda **_kwargs: pin,
        resolve_captured_turn_catalog_dispatch=lambda **_kwargs: "default_catalog",
    )

    schema = runtime.get_tool_schemas()[0]["function"]["parameters"]["properties"]["proposal"]
    predicate_schema = schema["properties"]["facts"]["items"]["properties"]["predicate_id"]
    literal_schema = schema["properties"]["facts"]["items"]["properties"]["object"]["oneOf"][1]["properties"]["literal_type"]
    assert len(predicate_schema["enum"]) == 56
    assert predicate_schema["enum"][0] == "account_held_by"
    assert {"project_deadline", "project_owner", "project_status"}.issubset(
        predicate_schema["enum"]
    )
    assert literal_schema["enum"] == ["local_date", "money", "status_text", "time_interval"]

    source = "Atlas project has work item Fix bug."
    arguments = {
        "source_quote": source,
        "subject_quote": "Atlas project",
        "predicate_anchor_quote": "has work item",
        "object_quote": "Fix bug",
    }
    proposal = ProviderSemanticProposal.model_validate(_json_arrays_to_tuples({
        "abstained": False,
        "mentions": [
            {"local_id": "project", "mention_quote": "Atlas project", "mention_context_quote": source, "proposed_type": "Project"},
            {"local_id": "work", "mention_quote": "Fix bug", "mention_context_quote": source, "proposed_type": "WorkItem"},
        ],
        "facts": [{
            "local_id": "fact", "predicate_id": "project_has_work_item",
            "subject_entity_ref": "project", "object": {"kind": "entity", "entity_ref": "work"},
            "assertion_quote": source, "predicate_anchor_quote": "has work item",
            "polarity": "positive", "commitment": "asserted",
        }],
        "corrections": [], "retractions": [], "action_states": [], "identity_operations": [],
    }))

    HermesCompletedTurnRuntime._validate_default_catalog_tool_proposal(
        proposal=proposal, arguments=arguments,
    )
    wrong = proposal.model_copy(update={
        "mentions": (
            proposal.mentions[0],
            proposal.mentions[1].model_copy(update={"proposed_type": "Person"}),
        ),
    })
    with pytest.raises(ValueError, match="object type"):
        HermesCompletedTurnRuntime._validate_default_catalog_tool_proposal(
            proposal=wrong, arguments=arguments,
        )


@pytest.mark.parametrize("operation", ("correction", "retraction"))
def test_default_catalog_tool_accepts_closed_lifecycle_operations(operation: str) -> None:
    fixture = build_default_catalog_proposal(
        next(row for row in load_default_catalog_acceptance_corpus().rows if row.relation_id == "project_owned_by")
    )
    if operation == "correction":
        replacement_object_quote = "Organization replacement"
        replacement_source = (
            f"Correction: {fixture.subject_quote} {fixture.predicate_anchor_quote} "
            f"{replacement_object_quote}."
        )
        corrected_subject = fixture.subject.model_copy(update={"local_id": "corrected_subject"})
        corrected_object = fixture.object.model_copy(update={"local_id": "corrected_object"})
        replacement_subject = fixture.subject.model_copy(update={
            "local_id": "replacement_subject", "mention_context_quote": replacement_source,
        })
        replacement_object = fixture.object.model_copy(update={
            "local_id": "replacement_object", "mention_quote": replacement_object_quote,
            "mention_context_quote": replacement_source,
        })
        corrected = fixture.fact.model_copy(update={
            "local_id": "corrected", "subject_entity_ref": corrected_subject.local_id,
            "object": ProviderEntityObject(entity_ref=corrected_object.local_id),
        })
        replacement = fixture.fact.model_copy(update={
            "local_id": "replacement", "assertion_quote": replacement_source,
            "subject_entity_ref": replacement_subject.local_id,
            "object": ProviderEntityObject(entity_ref=replacement_object.local_id),
        })
        proposal = ProviderSemanticProposal(
            abstained=False,
            mentions=(corrected_subject, corrected_object, replacement_subject, replacement_object),
            corrections=(ProviderCorrection(
                local_id="correction", corrected_fact=corrected,
                replacement_fact=replacement,
                assertion_quote=replacement_source, correction_anchor_quote="Correction",
            ),),
        )
        arguments = {
            "schema_version": 1,
            "correction": {
                "assertion_quote": replacement_source, "correction_anchor_quote": "Correction",
                "corrected": {
                    "source_quote": fixture.source, "subject_quote": fixture.subject_quote,
                    "predicate_anchor_quote": fixture.predicate_anchor_quote,
                    "object_quote": fixture.object_quote,
                },
                "replacement": {
                    "source_quote": replacement_source, "subject_quote": fixture.subject_quote,
                    "predicate_anchor_quote": fixture.predicate_anchor_quote,
                    "object_quote": replacement_object_quote,
                },
            },
        }
    else:
        corrected = fixture.fact.model_copy(update={"local_id": "corrected"})
        proposal = ProviderSemanticProposal(
            abstained=False, mentions=fixture.proposal().mentions,
            retractions=(ProviderRetraction(
                local_id="retraction", retracted_fact=corrected,
                assertion_quote=fixture.source, retraction_anchor_quote=fixture.predicate_anchor_quote,
            ),),
        )
        arguments = {
            "schema_version": 1, "source_quote": fixture.source,
            "subject_quote": fixture.subject_quote,
            "predicate_anchor_quote": fixture.predicate_anchor_quote,
            "object_quote": fixture.object_quote,
        }
    tool_proposal = proposal.model_dump(mode="json")

    _validate_default_catalog_argument_shape(tool_proposal)
    HermesCompletedTurnRuntime._validate_default_catalog_tool_proposal(
        proposal=proposal, arguments=arguments,
    )
    assert not list(Draft202012Validator(_default_catalog_fact_only_proposal_schema()).iter_errors(tool_proposal))


def test_default_catalog_tool_accepts_a_literal_replacement_with_independent_grounding() -> None:
    fixture = build_default_catalog_proposal(
        next(row for row in load_default_catalog_acceptance_corpus().rows if row.relation_id == "work_item_due_on")
    )
    replacement_quote = "2027-10-03"
    replacement_source = (
        f"Correction: {fixture.subject_quote} {fixture.predicate_anchor_quote} {replacement_quote}."
    )
    corrected_subject = fixture.subject.model_copy(update={"local_id": "corrected_subject"})
    replacement_subject = fixture.subject.model_copy(update={
        "local_id": "replacement_subject", "mention_context_quote": replacement_source,
    })
    corrected = fixture.fact.model_copy(update={
        "local_id": "corrected", "subject_entity_ref": corrected_subject.local_id,
    })
    replacement = fixture.fact.model_copy(update={
        "local_id": "replacement", "assertion_quote": replacement_source,
        "subject_entity_ref": replacement_subject.local_id,
        "object": fixture.fact.object.model_copy(update={
            "canonical_value": '{"source_calendar":"gregorian","value":"2027-10-03"}',
        }),
    })
    proposal = ProviderSemanticProposal(
        abstained=False, mentions=(corrected_subject, replacement_subject),
        corrections=(ProviderCorrection(
            local_id="correction", corrected_fact=corrected, replacement_fact=replacement,
            assertion_quote=replacement_source, correction_anchor_quote="Correction",
        ),),
    )
    arguments = {
        "schema_version": 1,
        "correction": {
            "assertion_quote": replacement_source, "correction_anchor_quote": "Correction",
            "corrected": {
                "source_quote": fixture.source, "subject_quote": fixture.subject_quote,
                "predicate_anchor_quote": fixture.predicate_anchor_quote,
                "object_quote": fixture.object_quote,
            },
            "replacement": {
                "source_quote": replacement_source, "subject_quote": fixture.subject_quote,
                "predicate_anchor_quote": fixture.predicate_anchor_quote,
                "object_quote": replacement_quote,
            },
        },
    }
    tool_proposal = proposal.model_dump(mode="json")

    _validate_default_catalog_argument_shape(tool_proposal)
    HermesCompletedTurnRuntime._validate_default_catalog_tool_proposal(
        proposal=proposal, arguments=arguments,
    )
    assert not list(Draft202012Validator(_default_catalog_fact_only_proposal_schema()).iter_errors(tool_proposal))


def test_default_catalog_handle_tool_call_validates_before_preparation_and_submission() -> None:
    runtime = _active_capture_runtime()
    active = runtime._active_turn
    assert active is not None
    runtime._active_turn = active.__class__(
        **(active.__dict__ | {"expires_at": datetime.now(UTC) + timedelta(minutes=1)})
    )
    pin = runtime._service.pin_captured_turn_catalog()
    submissions: list[object] = []
    preparations: list[str] = []
    runtime._structured_authority_request = StructuredSubmissionAuthorityRequest.model_construct()
    runtime._structured_tool_is_current = lambda: True
    runtime._load_active_prepared_source = lambda _active: preparations.append("prepare") or object()
    first_span = _real_source_span(source_id=active.ledger.source_id, text="first span")
    second_span = _real_source_span(source_id=active.ledger.source_id, text="second span")
    high_span, low_span = sorted(
        (first_span, second_span), key=lambda span: span.reference_digest, reverse=True,
    )
    runtime._resolve_sentence_span = lambda **kwargs: (
        low_span
        if str(kwargs["source_quote"]).lstrip().startswith("Correction:")
        else high_span
    )
    runtime._service = SimpleNamespace(
        load_captured_turn_catalog_pin=lambda **_kwargs: pin,
        resolve_captured_turn_catalog_dispatch=lambda **_kwargs: "default_catalog",
        submit_structured_fact=lambda request, **_kwargs: submissions.append(request) or SimpleNamespace(
            status="committed", operation_id=f"operation:{len(submissions)}",
        ),
    )

    def arguments(
        *, source: str, subject: str, anchor: str, object_quote: str,
        subject_type: str, predicate: str, object_value: dict[str, object],
        object_mention: dict[str, object] | None,
    ) -> dict[str, object]:
        mentions = [{
            "local_id": "subject", "mention_quote": subject,
            "mention_context_quote": source, "proposed_type": subject_type,
        }]
        if object_mention is not None:
            mentions.append(object_mention)
        return {
            "schema_version": 1, "source_quote": source, "source_quote_start": 0,
            "subject_quote": subject, "predicate_anchor_quote": anchor,
            "object_quote": object_quote,
            "proposal": {
                "abstained": False, "mentions": mentions,
                "facts": [{
                    "kind": "fact", "local_id": "fact", "predicate_id": predicate,
                    "subject_entity_ref": "subject", "object": object_value,
                    "assertion_quote": source, "predicate_anchor_quote": anchor,
                    "polarity": "positive", "commitment": "asserted",
                    "attributed_to_entity_ref": None, "temporal_qualifier_quotes": [],
                }],
                "corrections": [], "retractions": [], "action_states": [],
                "identity_operations": [],
            },
        }

    entity = arguments(
        source="Atlas project has work item Fix bug.", subject="Atlas project",
        anchor="has work item", object_quote="Fix bug", subject_type="Project",
        predicate="project_has_work_item",
        object_value={"kind": "entity", "entity_ref": "object"},
        object_mention={
            "local_id": "object", "mention_quote": "Fix bug",
            "mention_context_quote": "Atlas project has work item Fix bug.",
            "proposed_type": "WorkItem",
        },
    )
    literal = arguments(
        source="Fix bug due on 2026-10-03.", subject="Fix bug", anchor="due on",
        object_quote="2026-10-03", subject_type="WorkItem", predicate="work_item_due_on",
        object_value={
            "kind": "literal", "literal_type": "local_date",
            "canonical_value": '{"source_calendar":"gregorian","value":"2026-10-03"}',
            "unit": None,
        },
        object_mention=None,
    )

    assert runtime.handle_tool_call(tool_name="memorii_submit_fact", arguments=entity)["status"] == "committed"
    assert runtime.handle_tool_call(tool_name="memorii_submit_fact", arguments=literal)["status"] == "committed"
    lifecycle_fact = {**entity["proposal"]["facts"][0], "local_id": "corrected"}
    replacement_source = "Correction: Atlas project has work item Ship docs."
    replacement_fact = {
        **lifecycle_fact,
        "local_id": "replacement", "assertion_quote": replacement_source,
        "subject_entity_ref": "replacement_project",
        "object": {"kind": "entity", "entity_ref": "replacement_work"},
    }
    correction = {
        "schema_version": 1,
        "correction": {
            "assertion_quote": replacement_source, "correction_anchor_quote": "Correction",
            "corrected": {
                "source_quote": entity["source_quote"], "subject_quote": "Atlas project",
                "predicate_anchor_quote": "has work item", "object_quote": "Fix bug",
            },
            "replacement": {
                "source_quote": replacement_source, "subject_quote": "Atlas project",
                "predicate_anchor_quote": "has work item", "object_quote": "Ship docs",
            },
        },
        "proposal": {
            **entity["proposal"],
            "mentions": [
                {**entity["proposal"]["mentions"][0], "local_id": "corrected_project"},
                {**entity["proposal"]["mentions"][1], "local_id": "corrected_work"},
                {**entity["proposal"]["mentions"][0], "local_id": "replacement_project", "mention_context_quote": replacement_source},
                {"local_id": "replacement_work", "mention_quote": "Ship docs", "mention_context_quote": replacement_source, "proposed_type": "WorkItem"},
            ],
            "facts": [],
            "corrections": [{
                "kind": "correction", "local_id": "correction",
                "corrected_fact": {**lifecycle_fact, "subject_entity_ref": "corrected_project", "object": {"kind": "entity", "entity_ref": "corrected_work"}},
                "replacement_fact": replacement_fact,
                "assertion_quote": replacement_source, "correction_anchor_quote": "Correction",
            }],
        },
    }
    assert runtime.handle_tool_call(
        tool_name="memorii_submit_fact", arguments=correction,
    )["status"] == "committed"
    assert submissions[-1].proposal.corrections[0].corrected_fact.predicate_id == "project_has_work_item"
    assert tuple(span.reference_digest for span in submissions[-1].exact_source_spans) == (
        low_span.reference_digest, high_span.reference_digest,
    )
    # Segment-local preparation retains the separator byte before the second
    # sentence. The correction envelope, replacement fact, and replacement
    # mention contexts must all ground against that exact persisted span.
    leading_space_correction = deepcopy(correction)
    leading_space_source = f" {replacement_source}"
    leading_space_correction["correction"]["assertion_quote"] = leading_space_source
    leading_space_correction["correction"]["replacement"]["source_quote"] = leading_space_source
    leading_space_correction["proposal"]["mentions"][2]["mention_context_quote"] = leading_space_source
    leading_space_correction["proposal"]["mentions"][3]["mention_context_quote"] = leading_space_source
    leading_space_correction["proposal"]["corrections"][0]["assertion_quote"] = leading_space_source
    leading_space_correction["proposal"]["corrections"][0]["replacement_fact"]["assertion_quote"] = leading_space_source
    leading_result = runtime.handle_tool_call(
        tool_name="memorii_submit_fact", arguments=leading_space_correction,
    )
    assert leading_result["status"] == "committed"
    assert tuple(span.reference_digest for span in submissions[-1].exact_source_spans) == (
        low_span.reference_digest, high_span.reference_digest,
    )
    before_invalid_correction = (len(preparations), len(submissions))
    invalid_correction = {
        **correction,
        "correction": {
            **correction["correction"],
            "corrected": {**correction["correction"]["corrected"], "extra": "reject"},
        },
    }
    assert runtime.handle_tool_call(
        tool_name="memorii_submit_fact", arguments=invalid_correction,
    ) == {"status": "rejected"}
    assert (len(preparations), len(submissions)) == before_invalid_correction
    retraction = {
        **entity,
        "proposal": {
            **entity["proposal"],
            "facts": [],
            "retractions": [{
                "kind": "retraction", "local_id": "retraction",
                "retracted_fact": lifecycle_fact,
                "assertion_quote": entity["source_quote"],
                "retraction_anchor_quote": entity["predicate_anchor_quote"],
            }],
        },
    }
    assert runtime.handle_tool_call(
        tool_name="memorii_submit_fact", arguments=retraction,
    )["status"] == "committed"
    assert submissions[-1].proposal.retractions[0].retracted_fact.predicate_id == "project_has_work_item"
    before = (len(preparations), len(submissions))
    ungrounded_literal = dict(literal)
    ungrounded_literal["proposal"] = {
        **literal["proposal"],
        "facts": [{
            **literal["proposal"]["facts"][0],
            "object": {
                **literal["proposal"]["facts"][0]["object"],
                "canonical_value": '{"source_calendar":"gregorian","value":"2027-10-03"}',
            },
        }],
    }
    assert runtime.handle_tool_call(
        tool_name="memorii_submit_fact", arguments=ungrounded_literal,
    ) == {"status": "rejected"}
    assert (len(preparations), len(submissions)) == before

    literal_cases = (
        (
            arguments(
                source="Bill amount USD 12.50.", subject="Bill", anchor="amount",
                object_quote="USD 12.50", subject_type="Obligation",
                predicate="obligation_amount", object_mention=None,
                object_value={
                    "kind": "literal", "literal_type": "money",
                    "canonical_value": '{"currency":"USD","decimal_amount":"12.50"}',
                    "unit": None,
                },
            ),
            '{"currency":"USD","decimal_amount":"13.50"}',
        ),
        (
            arguments(
                source=(
                    "Meeting time 2026-10-03T09:00:00+00:00/"
                    "2026-10-03T10:00:00+00:00."
                ),
                subject="Meeting", anchor="time",
                object_quote=(
                    "2026-10-03T09:00:00+00:00/2026-10-03T10:00:00+00:00"
                ),
                subject_type="Event", predicate="event_time", object_mention=None,
                object_value={
                    "kind": "literal", "literal_type": "time_interval",
                    "canonical_value": (
                        '{"end":"2026-10-03T10:00:00Z","end_bound":"exclusive",'
                        '"start":"2026-10-03T09:00:00Z","start_bound":"closed"}'
                    ),
                    "unit": None,
                },
            ),
            (
                '{"end":"2026-10-03T11:00:00Z","end_bound":"exclusive",'
                '"start":"2026-10-03T09:00:00Z","start_bound":"closed"}'
            ),
        ),
        (
            arguments(
                source="Fix bug status completed.", subject="Fix bug", anchor="status",
                object_quote="completed", subject_type="WorkItem",
                predicate="work_item_status", object_mention=None,
                object_value={
                    "kind": "literal", "literal_type": "status_text",
                    "canonical_value": json.dumps(
                        CatalogStatusText.parse(
                            value_policy_id="work_item_status", source_text="done",
                        ).model_dump(mode="json"),
                        sort_keys=True, separators=(",", ":"),
                    ),
                    "unit": None,
                },
            ),
            json.dumps(
                CatalogStatusText.parse(
                    value_policy_id="work_item_status", source_text="blocked",
                ).model_dump(mode="json"),
                sort_keys=True, separators=(",", ":"),
            ),
        ),
    )
    for valid, substituted_canonical in literal_cases:
        assert runtime.handle_tool_call(
            tool_name="memorii_submit_fact", arguments=valid,
        )["status"] == "committed"
        accepted_counts = (len(preparations), len(submissions))
        substituted = dict(valid)
        substituted["proposal"] = {
            **valid["proposal"],
            "facts": [{
                **valid["proposal"]["facts"][0],
                "object": {
                    **valid["proposal"]["facts"][0]["object"],
                    "canonical_value": substituted_canonical,
                },
            }],
        }
        assert runtime.handle_tool_call(
            tool_name="memorii_submit_fact", arguments=substituted,
        ) == {"status": "rejected"}
        assert (len(preparations), len(submissions)) == accepted_counts

    wrong = dict(entity)
    wrong["proposal"] = {
        **entity["proposal"],
        "mentions": [
            {**entity["proposal"]["mentions"][0], "proposed_type": "Person"},
            entity["proposal"]["mentions"][1],
        ],
    }
    assert runtime.handle_tool_call(tool_name="memorii_submit_fact", arguments=wrong) == {
        "status": "rejected"
    }
    assert (len(preparations), len(submissions)) == (8, 8)
    assert all(request.captured_pin is not None for request in submissions)


@pytest.mark.parametrize(
    "row",
    load_default_catalog_acceptance_corpus().rows,
    ids=lambda row: row.relation_id,
)
def test_every_misleading_corpus_proposal_rejects_before_normalization(
    row: DefaultCatalogCorpusRow,
) -> None:
    """Endpoint denial must happen before prepared-source normalization work."""
    runtime = _active_capture_runtime()
    active = runtime._active_turn
    assert active is not None
    fixture = build_default_catalog_proposal(row)
    preparations: list[str] = []
    runtime._load_active_prepared_source = (
        lambda _active: preparations.append("prepared") or object()
    )

    with pytest.raises(ValueError):
        runtime._structured_tool_request(
            active=active,
            arguments=fixture.misleading_tool_arguments(),
            default_catalog=True,
        )

    assert preparations == []


@pytest.mark.parametrize("assertion_quote", [
    "Alice reports to Bob.",
    "Alice collaborates with Bob.",
    'Alice said "Alice reports to Bob."',
    "If Alice reports to Bob.",
    "Bob reports to Alice.",
])
def test_reports_to_child_grammar_rejects_direct_and_near_miss_payloads(assertion_quote: str) -> None:
    proposal = ProviderSemanticProposal.model_validate(_json_arrays_to_tuples({
        "abstained": False,
        "mentions": [
            {"local_id": "alice", "mention_quote": "Alice", "mention_context_quote": assertion_quote, "proposed_type": "PersonName"},
            {"local_id": "bob", "mention_quote": "Bob", "mention_context_quote": assertion_quote, "proposed_type": "PersonName"},
        ],
        "facts": [{
            "local_id": "reports", "predicate_id": "reports_to", "subject_entity_ref": "alice",
            "object": {"kind": "entity", "entity_ref": "bob"}, "assertion_quote": assertion_quote,
            "predicate_anchor_quote": "reports to", "polarity": "positive", "commitment": "asserted",
        }],
        "corrections": [], "retractions": [], "action_states": [], "identity_operations": [],
    }))
    if assertion_quote == "Alice reports to Bob.":
        validate_reports_to_tool_proposal(proposal)
    else:
        with pytest.raises(ValueError):
            validate_reports_to_tool_proposal(proposal)


def test_rejected_structured_tool_call_does_not_block_captured_completion() -> None:
    runtime = _active_capture_runtime()
    runtime._active_turn = runtime._active_turn.__class__(
        **(runtime._active_turn.__dict__ | {"expires_at": datetime.now(UTC) + timedelta(minutes=1)})
    )
    runtime._structured_authority_request = object()
    runtime._structured_tool_is_current = lambda: True
    runtime._service = SimpleNamespace(
        _preflight_ingress=lambda _ingress: None,
        load_captured_turn_catalog_pin=lambda **_kwargs: None,
    )
    runtime._issue_host_ingress = lambda *_args: object()
    now = datetime(2026, 9, 26, tzinfo=UTC)

    assert runtime.handle_tool_call(
        tool_name="memorii_submit_fact", arguments={"schema_version": 2}
    ) == {"status": "unavailable"}
    assert runtime._active_tool_calls == 0
    with pytest.raises(ValueError, match="ingress is unavailable"):
        runtime.complete_captured_turn(
            user_content="Atlas owner is Ada.", assistant_content="Acknowledged.",
            messages=[
                {"role": "user", "content": "Atlas owner is Ada.", "timestamp": "2026-09-26T00:00:00Z"},
                {"role": "assistant", "content": "Acknowledged.", "timestamp": "2026-09-26T00:00:01Z"},
            ],
            session_id="session:a", authenticated_author_id="operator:ada", received_at=now,
        )
    assert runtime._active_turn is None


def test_structured_tool_literal_grounding_uses_the_packaged_parser() -> None:
    arguments = {
        "source_quote": "Atlas project status is   active.",
        "subject_quote": "Atlas",
        "predicate_anchor_quote": "status",
        "object_quote": "active",
    }
    proposal = ProviderSemanticProposal.model_validate(_json_arrays_to_tuples({
        "abstained": False,
        "mentions": [{"local_id": "atlas", "mention_quote": "Atlas", "mention_context_quote": arguments["source_quote"]}],
        "facts": [{"local_id": "status", "predicate_id": "project_status", "subject_entity_ref": "atlas", "object": {"kind": "literal", "literal_type": "text", "canonical_value": "active", "unit": None}, "assertion_quote": arguments["source_quote"], "predicate_anchor_quote": "status", "polarity": "positive", "commitment": "asserted"}],
        "corrections": [], "retractions": [], "action_states": [], "identity_operations": [],
    }))
    HermesCompletedTurnRuntime._validate_fact_only_proposal(proposal=proposal, arguments=arguments)

    invalid = proposal.model_copy(update={
        "facts": (proposal.facts[0].model_copy(update={"object": proposal.facts[0].object.model_copy(update={"canonical_value": "inactive"})}),)
    })
    with pytest.raises(ValueError, match="literal grounding"):
        HermesCompletedTurnRuntime._validate_fact_only_proposal(proposal=invalid, arguments=arguments)


def test_structured_tool_rejects_ambiguous_inner_quote() -> None:
    arguments = {
        "source_quote": "Atlas owner Ada told Atlas owner Ada.",
        "subject_quote": "Atlas", "predicate_anchor_quote": "owner", "object_quote": "Ada",
    }
    proposal = ProviderSemanticProposal.model_validate(_json_arrays_to_tuples({
        "abstained": False,
        "mentions": [
            {"local_id": "atlas", "mention_quote": "Atlas", "mention_context_quote": arguments["source_quote"]},
            {"local_id": "ada", "mention_quote": "Ada", "mention_context_quote": arguments["source_quote"]},
        ],
        "facts": [{"local_id": "owner", "predicate_id": "project_owner", "subject_entity_ref": "atlas", "object": {"kind": "entity", "entity_ref": "ada"}, "assertion_quote": arguments["source_quote"], "predicate_anchor_quote": "owner", "polarity": "positive", "commitment": "asserted"}],
        "corrections": [], "retractions": [], "action_states": [], "identity_operations": [],
    }))
    with pytest.raises(ValueError, match="absent or ambiguous"):
        HermesCompletedTurnRuntime._validate_fact_only_proposal(proposal=proposal, arguments=arguments)


def test_close_stops_worker_and_rejects_post_close_enqueue() -> None:
    runtime = _worker_runtime()
    runtime._recover_pending = lambda: None

    runtime.close(timeout=1.0)

    assert not runtime._worker.is_alive()
    assert runtime._outstanding == 0
    with pytest.raises(RuntimeError, match="closed"):
        runtime._enqueue(_CompletedTurnWork(admitted=object(), ingress=object()))


def test_post_admission_failure_recovers_before_idle_and_clears_failure() -> None:
    runtime = _worker_runtime()
    process_calls: list[object] = []
    recovery_calls: list[str] = []

    def fail_once(work: object) -> None:
        process_calls.append(work)
        raise RuntimeError("post-admission failure")

    runtime._process = fail_once
    runtime._recover_pending = lambda: recovery_calls.append("recovered")
    runtime._enqueue(_CompletedTurnWork(admitted=object(), ingress=object()))

    runtime.wait_for_idle(timeout=1.0)

    assert len(process_calls) == 1
    assert recovery_calls == ["recovered"]
    assert runtime._failures == []


def test_persistent_recovery_failure_remains_visible_without_rescheduling() -> None:
    runtime = _worker_runtime()
    recovery_calls: list[str] = []
    runtime._process = lambda _work: (_ for _ in ()).throw(RuntimeError("post-admission failure"))

    def failed_recovery() -> None:
        recovery_calls.append("attempted")
        raise RuntimeError("recovery remained pending")

    runtime._recover_pending = failed_recovery
    runtime._enqueue(_CompletedTurnWork(admitted=object(), ingress=object()))

    with pytest.raises(RuntimeError, match="semantic worker failed") as first:
        runtime.wait_for_idle(timeout=1.0)
    with pytest.raises(RuntimeError, match="semantic worker failed") as second:
        runtime.wait_for_idle(timeout=1.0)

    assert first.value.__cause__ is second.value.__cause__
    assert recovery_calls == ["attempted"]
    assert len(runtime._failures) == 2
    assert runtime._work.empty()


def test_full_transcript_canonicalization_accepts_matched_tool_sequence() -> None:
    messages = _canonicalize_completed_messages(
        messages=[
            {"role": "user", "content": "Find Atlas"},
            {"role": "assistant", "content": "Calling lookup.", "tool_calls": [{
                "id": "call-1", "type": "function",
                "function": {"name": "lookup", "arguments": "{\"name\":\"Atlas\"}"},
            }]},
            {"role": "tool", "content": "Atlas found", "tool_call_id": "call-1"},
            {"role": "assistant", "content": "Atlas is found."},
        ],
        user_content="Find Atlas",
        assistant_content="Atlas is found.",
    )

    assert messages[-1] == {"role": "assistant", "content": "Atlas is found."}


def test_full_transcript_canonicalization_discards_known_hermes_message_carriers() -> None:
    messages = _canonicalize_completed_messages(
        messages=[
            {
                "role": "user",
                "content": "Find Atlas",
                "timestamp": "2026-09-24T00:00:00Z",
                "display_kind": "user",
                "display_metadata": {"channel": "cli"},
                "platform_message_id": "platform:user:1",
                "api_content": [{"type": "input_text", "text": "Find Atlas"}],
                "_db_persisted": True,
                "_row_id": 41,
            },
            {
                "role": "assistant",
                "content": "Atlas is found.",
                "reasoning": "private",
                "finish_reason": "stop",
                "timestamp": "2026-09-24T00:00:01Z",
                "reasoning_content": "private",
                "reasoning_details": [{"type": "summary"}],
                "anthropic_content_blocks": [],
                "bedrock_content_blocks": [],
                "codex_reasoning_items": [],
                "codex_message_items": [],
                "api_content": [{"type": "output_text", "text": "Atlas is found."}],
                "_db_persisted": True,
                "_row_id": 42,
            },
        ],
        user_content="Find Atlas",
        assistant_content="Atlas is found.",
    )

    assert messages == (
        {"role": "user", "content": "Find Atlas", "timestamp": "2026-09-24T00:00:00Z"},
        {"role": "assistant", "content": "Atlas is found.", "timestamp": "2026-09-24T00:00:01Z"},
    )


def test_full_transcript_canonicalization_accepts_decorated_tool_sequence() -> None:
    messages = _canonicalize_completed_messages(
        messages=[
            {"role": "user", "content": "Find Atlas", "timestamp": "2026-09-24T00:00:00Z"},
            {
                "role": "assistant",
                "content": "Calling lookup.",
                "reasoning": "private",
                "tool_calls": [{
                    "id": "call-1", "type": "function",
                    "function": {"name": "lookup", "arguments": "{\"name\":\"Atlas\"}"},
                }],
            },
            {
                "role": "tool",
                "content": "Atlas found",
                "tool_call_id": "call-1",
                "name": "lookup",
                "tool_name": "lookup",
                "timestamp": "2026-09-24T00:00:01Z",
                "_tool_output_risk": "low",
                "effect_disposition": "read_only",
            },
            {"role": "assistant", "content": "Atlas is found.", "finish_reason": "stop"},
        ],
        user_content="Find Atlas",
        assistant_content="Atlas is found.",
    )

    assert messages[1]["tool_calls"] == (
        {"id": "call-1", "type": "function", "name": "lookup", "arguments": "{\"name\":\"Atlas\"}"},
    )
    assert messages[2] == {
        "role": "tool",
        "content": "Atlas found",
        "tool_call_id": "call-1",
        "timestamp": "2026-09-24T00:00:01Z",
    }


@pytest.mark.parametrize("timestamp", [None, "not-a-timestamp", "2026-09-24T00:00:00"])
def test_completed_turn_timestamp_requires_a_timezone_aware_final_persisted_timestamp(timestamp: object) -> None:
    final: dict[str, object] = {"role": "assistant", "content": "Acknowledged."}
    if timestamp is not None:
        final["timestamp"] = timestamp

    from memorii.core.semantic_ingestion.hermes_completed_turn_runtime import _completed_turn_timestamp

    with pytest.raises(ValueError, match="timestamp"):
        canonical = _canonicalize_completed_messages(
            messages=[
                {"role": "user", "content": "Remember Atlas", "timestamp": "2026-09-24T00:00:00Z"},
                final,
            ],
            user_content="Remember Atlas",
            assistant_content="Acknowledged.",
        )
        _completed_turn_timestamp(canonical)


def test_full_transcript_canonicalization_accepts_real_hermes_textless_tool_call() -> None:
    messages = _canonicalize_completed_messages(
        messages=[
            {"role": "user", "content": "Find Atlas", "timestamp": "2026-09-24T00:00:00Z"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "tool-call:1",
                    "call_id": "provider-call:1",
                    "response_item_id": "response-item:1",
                    "type": "function",
                    "function": {"name": "lookup", "arguments": "{\"name\":\"Atlas\"}"},
                    "extra_content": {"provider": "hermes"},
                }],
            },
            {"role": "tool", "content": "Atlas found", "tool_call_id": "tool-call:1"},
            {"role": "assistant", "content": "Atlas is found."},
        ],
        user_content="Find Atlas",
        assistant_content="Atlas is found.",
    )

    assert messages[1] == {
        "role": "assistant",
        "content": "",
        "tool_calls": (
            {"id": "tool-call:1", "type": "function", "name": "lookup", "arguments": "{\"name\":\"Atlas\"}"},
        ),
    }


def test_tool_arguments_are_json_canonicalized_for_equivalent_transport_encodings() -> None:
    def transcript(arguments: str) -> tuple[dict[str, object], ...]:
        return _canonicalize_completed_messages(
            messages=[
                {"role": "user", "content": "Find Atlas"},
                {
                    "role": "assistant",
                    "content": "Calling lookup.",
                    "tool_calls": [{
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "lookup", "arguments": arguments},
                    }],
                },
                {"role": "tool", "content": "Atlas found", "tool_call_id": "call-1"},
                {"role": "assistant", "content": "Atlas is found."},
            ],
            user_content="Find Atlas",
            assistant_content="Atlas is found.",
        )

    formatted = transcript('{ "subject": "Atlas", "limit": 1 }')
    compact = transcript('{"limit":1,"subject":"Atlas"}')

    assert formatted == compact
    assert formatted[1]["tool_calls"] == (
        {"id": "call-1", "type": "function", "name": "lookup", "arguments": '{"limit":1,"subject":"Atlas"}'},
    )
    assert _canonical_messages_digest(formatted) == _canonical_messages_digest(compact)


@pytest.mark.parametrize("arguments", ["{", '{"key":1,"key":2}'])
def test_tool_arguments_reject_malformed_or_duplicate_key_json(arguments: str) -> None:
    with pytest.raises(ValueError, match="tool arguments"):
        _canonicalize_completed_messages(
            messages=[
                {"role": "user", "content": "Find Atlas"},
                {
                    "role": "assistant",
                    "content": "Calling lookup.",
                    "tool_calls": [{
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "lookup", "arguments": arguments},
                    }],
                },
                {"role": "tool", "content": "Atlas found", "tool_call_id": "call-1"},
                {"role": "assistant", "content": "Atlas is found."},
            ],
            user_content="Find Atlas",
            assistant_content="Atlas is found.",
        )


@pytest.mark.parametrize("messages", [
    [{"role": "user", "content": "x", "unknown": "x"}, {"role": "assistant", "content": "ok"}],
    [{"role": "user", "content": "x", "timestamp": "now", "unexpected": "x"}, {"role": "assistant", "content": "ok"}],
    [{"role": "user", "content": "x"}, {"role": "assistant", "content": "ok", "unexpected": "x"}],
    [{"role": "user", "content": "x"}, {"role": "tool", "content": "bad", "tool_call_id": "none", "unexpected": "x"}, {"role": "assistant", "content": "ok"}],
    [{"role": "user", "content": "x"}, {"role": "tool", "content": "bad", "tool_call_id": "none"}, {"role": "assistant", "content": "ok"}],
    [{"role": "user", "content": "x"}, {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "type": "function", "function": {"name": "x", "arguments": "{"}}]}],
])
def test_full_transcript_canonicalization_rejects_invalid_messages(messages: list[dict[str, object]]) -> None:
    with pytest.raises(ValueError):
        _canonicalize_completed_messages(messages=messages, user_content="x", assistant_content="ok")
