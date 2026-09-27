"""Hermes completed-turn bridge to the canonical Bootstrap V3 execution owner."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import unicodedata
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_hex

from memorii.core.memory_evolution.admission import GovernedSourceAdmissionService
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedHostIngress,
    AuthenticatedIngressContext,
    DeliveryIdentity,
    derive_composite_child_delivery_id,
    encode_typed_value,
)
from memorii.core.memory_plane.store import MemoryPlaneRevisionConflictError
from memorii.core.provider.ingestion import (
    CapturedCatalogPinReference,
    StructuredFactSubmissionRequest,
    StructuredFactSubmissionStatusRequest,
)
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.scoped_context.authority import (
    InProcessScopedReadAuthority,
    ScopedNamespaceGrantRow,
)
from memorii.core.scoped_context.contracts import (
    ScopedContextBudget,
    ScopedContextRequest,
    ScopedContextStatus,
)
from memorii.core.semantic_ingestion.catalog_authority import (
    StructuredFactReadAuthority,
    StructuredSubmissionAuthorityRequest,
)
from memorii.core.semantic_ingestion.catalog_capture_pin import (
    CatalogCapturedTurnPin,
)
from memorii.core.semantic_ingestion.contracts import (
    PreparedSource,
    ProviderEntityObject,
    ProviderFact,
    ProviderMention,
    ProviderSemanticProposal,
    TextPreparationRequest,
    VerbatimTextArtifactMappingProof,
)
from memorii.core.semantic_ingestion.default_catalog_corpus import DefaultCatalogCorpusRow
from memorii.core.semantic_ingestion.default_catalog_runtime import (
    DEFAULT_CATALOG_LITERAL_TYPES,
    default_catalog_runtime_rows,
    validate_default_catalog_literal_grounding,
    validate_default_catalog_provider_lifecycle_proposal,
)
from memorii.core.semantic_ingestion.hermes_captured_turn import (
    HermesCapturedTurnCompletion,
    HermesCapturedTurnLedger,
    HermesCapturedTurnSourceOwner,
)
from memorii.core.semantic_ingestion.hermes_completed_turn_admission import (
    HermesCompletedTurnAdmission,
    HermesCompletedTurnAdmissionRequest,
    HermesCompletedTurnAdmissionService,
    HermesCompletedTurnMessage,
    _prepare_governed_child_source,
)
from memorii.core.semantic_ingestion.reports_to_capability import (
    validate_reports_to_tool_proposal,
)
from memorii.core.semantic_ingestion.structured_fact_read import (
    StructuredFactReadRequest,
    StructuredFactReadResponse,
)
from memorii.core.user_context.preferences import (
    PreferenceReadRequest,
    PreferenceService,
    PreferenceWriteRequest,
    preference_candidate_sentence,
    preference_close_sentence,
    preference_confirmation_sentence,
    preference_delegation_sentence,
)
from memorii.domain.enums import MemoryDomain

logger = logging.getLogger(__name__)

# Local no-key semantic reconciliation can run for the complete Level-2
# Bootstrap V3 recovery window. Keep the authenticated capture available for
# its tool calls and one completion callback throughout that window.
_CAPTURED_TURN_TTL = timedelta(minutes=30)


def _structured_fact_read_request(arguments: dict[str, object]) -> StructuredFactReadRequest:
    """Parse the public closed read grammar without accepting caller authority."""
    required = {"predicate_id", "subject_entity_id", "view"}
    if set(arguments) - (required | {"system_as_of"}):
        raise ValueError("structured fact read arguments are not closed")
    if not required.issubset(arguments):
        raise ValueError("structured fact read arguments are incomplete")
    if (
        not isinstance(arguments.get("predicate_id"), str)
        or not isinstance(arguments.get("subject_entity_id"), str)
        or arguments.get("view") not in {"current", "history"}
    ):
        raise ValueError("structured fact read arguments are invalid")
    system_as_of = arguments.get("system_as_of")
    if system_as_of is not None:
        if not isinstance(system_as_of, str):
            raise ValueError("structured fact read system time is invalid")
        system_as_of = datetime.fromisoformat(system_as_of.replace("Z", "+00:00"))
        if system_as_of.tzinfo is None:
            raise ValueError("structured fact read system time is invalid")
    return StructuredFactReadRequest(
        predicate_id=arguments.get("predicate_id"),
        subject_entity_id=arguments.get("subject_entity_id"),
        view=arguments.get("view"),
        system_as_of=system_as_of,
    )


def _parse_project_assertions_literal(*, predicate_id: str, value_quote: object) -> tuple[str, str | None]:
    """Use the selected packaged seed's canonical literal parser."""
    if not isinstance(value_quote, str):
        raise ValueError("structured tool literal quote is invalid")
    from memorii.core.semantic_ingestion.project_assertions import (
        ProjectAssertionProviderProposalAdapter,
        _Hint,
    )

    literal_type, canonical_value = ProjectAssertionProviderProposalAdapter._literal(
        _Hint(
            predicate_id=predicate_id,
            assertion_quote=value_quote,
            subject_quote=value_quote,
            predicate_anchor_quote=value_quote,
            value_quote=value_quote,
        )
    )
    return literal_type.value, canonical_value


_FACT_ONLY_PROPOSAL_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "abstained",
        "mentions",
        "facts",
        "corrections",
        "retractions",
        "action_states",
        "identity_operations",
    ],
    "properties": {
        "abstained": {"const": False},
        "mentions": {
            "type": "array",
            "minItems": 1,
            "maxItems": 2,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["local_id", "mention_quote", "mention_context_quote", "proposed_type"],
                "properties": {
                    "local_id": {"type": "string", "minLength": 1},
                    "mention_quote": {"type": "string", "minLength": 1},
                    "mention_context_quote": {"type": "string", "minLength": 1},
                    "proposed_type": {"type": ["string", "null"]},
                },
            },
        },
        "facts": {
            "type": "array",
            "minItems": 1,
            "maxItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "kind",
                    "local_id",
                    "predicate_id",
                    "subject_entity_ref",
                    "object",
                    "assertion_quote",
                    "predicate_anchor_quote",
                    "polarity",
                    "commitment",
                    "attributed_to_entity_ref",
                    "temporal_qualifier_quotes",
                ],
                "properties": {
                    "kind": {"const": "fact"},
                    "local_id": {"type": "string", "minLength": 1},
                    "predicate_id": {"enum": ["project_owner", "project_status", "project_deadline"]},
                    "subject_entity_ref": {"type": "string", "minLength": 1},
                    "object": {
                        "oneOf": [
                            {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["kind", "entity_ref"],
                                "properties": {
                                    "kind": {"const": "entity"},
                                    "entity_ref": {"type": "string", "minLength": 1},
                                },
                            },
                            {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["kind", "literal_type", "canonical_value", "unit"],
                                "properties": {
                                    "kind": {"const": "literal"},
                                    "literal_type": {"enum": ["text", "date"]},
                                    "canonical_value": {"type": "string", "minLength": 1},
                                    "unit": {"type": ["string", "null"]},
                                },
                            },
                        ]
                    },
                    "assertion_quote": {"type": "string", "minLength": 1},
                    "predicate_anchor_quote": {"type": "string", "minLength": 1},
                    "polarity": {"enum": ["positive", "negative"]},
                    "commitment": {"const": "asserted"},
                    "attributed_to_entity_ref": {"const": None},
                    "temporal_qualifier_quotes": {"type": "array", "items": {"type": "string", "minLength": 1}},
                },
            },
        },
        "corrections": {"type": "array", "maxItems": 0},
        "retractions": {"type": "array", "maxItems": 0},
        "action_states": {"type": "array", "maxItems": 0},
        "identity_operations": {"type": "array", "maxItems": 0},
    },
    # The two entity mentions only make sense for the owner relation.  The
    # literal seeds derive their object from the selected sentence and retain
    # only the project mention.
    "allOf": [
        {
            "oneOf": [
                {
                    "properties": {
                        "mentions": {"minItems": 2, "maxItems": 2},
                        "facts": {
                            "items": {
                                "properties": {
                                    "predicate_id": {"const": "project_owner"},
                                    "object": {"properties": {"kind": {"const": "entity"}}},
                                }
                            }
                        },
                    },
                },
                {
                    "properties": {
                        "mentions": {"minItems": 1, "maxItems": 1},
                        "facts": {
                            "items": {
                                "properties": {
                                    "predicate_id": {"const": "project_status"},
                                    "object": {
                                        "properties": {
                                            "kind": {"const": "literal"},
                                            "literal_type": {"const": "text"},
                                        }
                                    },
                                }
                            }
                        },
                    },
                },
                {
                    "properties": {
                        "mentions": {"minItems": 1, "maxItems": 1},
                        "facts": {
                            "items": {
                                "properties": {
                                    "predicate_id": {"const": "project_deadline"},
                                    "object": {
                                        "properties": {
                                            "kind": {"const": "literal"},
                                            "literal_type": {"const": "date"},
                                        }
                                    },
                                }
                            }
                        },
                    },
                },
            ]
        }
    ],
}

_REPORTS_TO_FACT_ONLY_PROPOSAL_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "abstained",
        "mentions",
        "facts",
        "corrections",
        "retractions",
        "action_states",
        "identity_operations",
    ],
    "properties": {
        "abstained": {"const": False},
        "mentions": {
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["local_id", "mention_quote", "mention_context_quote", "proposed_type"],
                "properties": {
                    "local_id": {"type": "string", "minLength": 1},
                    "mention_quote": {"type": "string", "minLength": 1},
                    "mention_context_quote": {"type": "string", "minLength": 1},
                    "proposed_type": {"const": "PersonName"},
                },
            },
        },
        "facts": {
            "type": "array",
            "minItems": 1,
            "maxItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "kind",
                    "local_id",
                    "predicate_id",
                    "subject_entity_ref",
                    "object",
                    "assertion_quote",
                    "predicate_anchor_quote",
                    "polarity",
                    "commitment",
                    "attributed_to_entity_ref",
                    "temporal_qualifier_quotes",
                ],
                "properties": {
                    "kind": {"const": "fact"},
                    "local_id": {"type": "string", "minLength": 1},
                    "predicate_id": {"const": "reports_to"},
                    "subject_entity_ref": {"type": "string", "minLength": 1},
                    "object": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["kind", "entity_ref"],
                        "properties": {"kind": {"const": "entity"}, "entity_ref": {"type": "string", "minLength": 1}},
                    },
                    "assertion_quote": {"type": "string", "minLength": 1},
                    "predicate_anchor_quote": {"const": "reports to"},
                    "polarity": {"const": "positive"},
                    "commitment": {"const": "asserted"},
                    "attributed_to_entity_ref": {"const": None},
                    "temporal_qualifier_quotes": {"type": "array", "maxItems": 0},
                },
            },
        },
        "corrections": {"type": "array", "maxItems": 0},
        "retractions": {"type": "array", "maxItems": 0},
        "action_states": {"type": "array", "maxItems": 0},
        "identity_operations": {"type": "array", "maxItems": 0},
    },
}


def _default_catalog_fact_only_proposal_schema() -> dict[str, object]:
    """Project default predicates and their closed lifecycle grammar to transport."""
    schema = deepcopy(_FACT_ONLY_PROPOSAL_SCHEMA)
    properties = schema["properties"]
    assert isinstance(properties, dict)
    facts = properties["facts"]
    assert isinstance(facts, dict)
    items = facts["items"]
    assert isinstance(items, dict)
    fact_properties = items["properties"]
    assert isinstance(fact_properties, dict)
    fact_properties["predicate_id"] = {
        "enum": sorted(
            {
                *default_catalog_runtime_rows(),
                "project_deadline",
                "project_owner",
                "project_status",
            }
        ),
    }
    object_schema = fact_properties["object"]
    assert isinstance(object_schema, dict)
    alternatives = object_schema["oneOf"]
    assert isinstance(alternatives, list)
    literal = alternatives[1]
    assert isinstance(literal, dict)
    literal_properties = literal["properties"]
    assert isinstance(literal_properties, dict)
    literal_properties["literal_type"] = {
        "enum": sorted(item.value for item in DEFAULT_CATALOG_LITERAL_TYPES.values()),
    }
    # Corrections and retractions remain normal Bootstrap V3 operations.  They
    # use the same fact contract as an assertion and never introduce a second
    # writer or an untyped lifecycle payload.
    fact_schema = deepcopy(items)
    properties["facts"] = {"type": "array", "minItems": 0, "maxItems": 1, "items": fact_schema}
    mentions = properties["mentions"]
    assert isinstance(mentions, dict)
    mentions["maxItems"] = 4
    properties["corrections"] = {
        "type": "array",
        "minItems": 0,
        "maxItems": 1,
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "kind",
                "local_id",
                "corrected_fact",
                "replacement_fact",
                "assertion_quote",
                "correction_anchor_quote",
            ],
            "properties": {
                "kind": {"const": "correction"},
                "local_id": {"type": "string", "minLength": 1},
                "corrected_fact": deepcopy(fact_schema),
                "replacement_fact": deepcopy(fact_schema),
                "assertion_quote": {"type": "string", "minLength": 1},
                "correction_anchor_quote": {"type": "string", "minLength": 1},
            },
        },
    }
    properties["retractions"] = {
        "type": "array",
        "minItems": 0,
        "maxItems": 1,
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "local_id", "retracted_fact", "assertion_quote", "retraction_anchor_quote"],
            "properties": {
                "kind": {"const": "retraction"},
                "local_id": {"type": "string", "minLength": 1},
                "retracted_fact": deepcopy(fact_schema),
                "assertion_quote": {"type": "string", "minLength": 1},
                "retraction_anchor_quote": {"type": "string", "minLength": 1},
            },
        },
    }
    schema.pop("allOf", None)
    return schema


@dataclass(frozen=True)
class _CompletedTurnWork:
    admitted: HermesCompletedTurnAdmission
    ingress: AuthenticatedIngressContext
    captured_user_admission: object | None = None


@dataclass(frozen=True)
class _CapturedTurnHandle:
    """Provider-local callback join state; never reconstructed after restart."""

    session_id: str
    turn_ordinal: int
    message_digest: str
    admission: object
    ledger: HermesCapturedTurnLedger
    generation: str
    expires_at: datetime
    closing: bool = False


@dataclass(frozen=True)
class _RecoverySweep:
    pass


@dataclass(frozen=True)
class _StopWorker:
    pass


class HermesCompletedTurnRuntime:
    """Run one authenticated, complete Hermes turn through existing V3 owners."""

    def __init__(
        self,
        *,
        service: ProviderMemoryService,
        installation_id: str,
        issue_host_ingress: Callable[[str, str, datetime], AuthenticatedHostIngress],
        scoped_read_authority: InProcessScopedReadAuthority,
        require_current_authority: Callable[[], None],
        project_task_id: str,
        authenticated_agent_id: str,
        authenticated_author_id: str,
        structured_authority_request: StructuredSubmissionAuthorityRequest | None = None,
        structured_tool_is_current: Callable[[], bool] | None = None,
        structured_fact_read_authority: Callable[[], StructuredFactReadAuthority | None] | None = None,
        preference_service: PreferenceService | None = None,
    ) -> None:
        self._service = service
        self._installation_id = installation_id
        self._issue_host_ingress = issue_host_ingress
        self._scoped_read_authority = scoped_read_authority
        self._require_current_authority = require_current_authority
        self._project_task_id = project_task_id
        self._authenticated_agent_id = authenticated_agent_id
        self._authenticated_author_id = authenticated_author_id
        self._structured_authority_request = structured_authority_request
        self._structured_tool_is_current = structured_tool_is_current
        self._structured_fact_read_authority = structured_fact_read_authority
        self._preference_service = preference_service
        self._work: queue.Queue[_CompletedTurnWork | _RecoverySweep | _StopWorker] = queue.Queue()
        self._condition = threading.Condition()
        self._outstanding = 0
        self._failures: list[BaseException] = []
        self._closed = False
        self._stopped = False
        self._active_turn: _CapturedTurnHandle | None = None
        self._active_turn_ambiguous = False
        self._active_tool_calls = 0
        self._active_turn_condition = threading.Condition(self._condition)
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="memorii-hermes-semantic-worker",
            daemon=True,
        )
        self._worker.start()
        self._enqueue(_RecoverySweep())

    def get_tool_schemas(self) -> list[dict[str, object]]:
        """Persist an authorized catalog pin before advertising the fact tool."""
        with self._condition:
            active = self._active_turn
            tool_is_current = self._structured_tool_is_current
            authority_request = self._structured_authority_request
            available = (
                active is not None
                and not active.closing
                and not self._active_turn_ambiguous
                and active.expires_at > datetime.now(UTC)
                and authority_request is not None
                and tool_is_current is not None
            )
            preference_available = (
                getattr(self, "_preference_service", None) is not None
                and active is not None
                and not active.closing
                and not self._active_turn_ambiguous
                and active.expires_at > datetime.now(UTC)
            )
        preference_schemas = _preference_tool_schemas() if preference_available else []
        if preference_schemas:
            try:
                self._require_current_authority()
            except (OSError, ValueError):
                preference_schemas = []
        if not available or tool_is_current is None or not tool_is_current():
            return preference_schemas
        assert active is not None
        assert authority_request is not None
        # The verified factory-controlled file authority is rechecked around
        # the durable operation.  It is deliberately not represented as a
        # memory-plane precondition because it lives in another store.
        try:
            self._require_current_authority()
        except (OSError, ValueError):
            return []
        pin = self._service.pin_captured_turn_catalog(
            ledger=active.ledger,
            authority_request=authority_request,
            authenticated_host_ingress=self._issue_host_ingress(
                active.session_id, self._authenticated_author_id, datetime.now(UTC)
            ),
        )
        if pin is None:
            return []
        if not tool_is_current():
            return []
        with self._condition:
            current = self._active_turn
            if (
                current is not active
                or self._closed
                or active.closing
                or self._active_turn_ambiguous
                or active.expires_at <= datetime.now(UTC)
            ):
                return []
        dispatch = self._service.resolve_captured_turn_catalog_dispatch(pin=pin)
        if dispatch == "reports_to":
            proposal_schema = _REPORTS_TO_FACT_ONLY_PROPOSAL_SCHEMA
        elif dispatch == "default_catalog":
            proposal_schema = _default_catalog_fact_only_proposal_schema()
        else:
            proposal_schema = _FACT_ONLY_PROPOSAL_SCHEMA
        if dispatch not in {"seed", "reports_to", "default_catalog"}:
            return []
        parameters = (
            _default_catalog_tool_parameters(proposal_schema)
            if dispatch == "default_catalog"
            else _ordinary_fact_tool_parameters(proposal_schema)
        )
        submit_schema = {
            "type": "function",
            "function": {
                "name": "memorii_submit_fact",
                "description": "Submit one quote-grounded fact from the current user turn.",
                "parameters": parameters,
            },
        }
        # Submit remains first because existing hosts use the first advertised
        # schema.  Reads are a separate closed grammar and cannot carry a
        # proposal, source text, or authority coordinate from the caller.
        return [
            submit_schema,
            {
                "type": "function",
                "function": {
                    "name": "memorii_read_fact",
                    "description": "Read current or historical protected facts for one relation and subject.",
                    "parameters": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["predicate_id", "subject_entity_id", "view"],
                        "properties": {
                            "predicate_id": {"type": "string", "minLength": 1},
                            "subject_entity_id": {"type": "string", "minLength": 1},
                            "view": {"enum": ["current", "history"]},
                            "system_as_of": {"type": ["string", "null"], "format": "date-time"},
                        },
                    },
                },
            },
            *preference_schemas,
        ]

    def handle_tool_call(self, *, tool_name: str, arguments: dict[str, object]) -> object:
        if tool_name not in {
            "memorii_submit_fact",
            "memorii_read_fact",
            "memorii_create_preference_candidate",
            "memorii_confirm_preference",
            "memorii_close_preference",
            "memorii_read_preference",
            "memorii_set_preference_delegation",
        }:
            raise ValueError(f"Memorii does not provide Hermes tool {tool_name!r}")
        if type(arguments) is not dict:
            return {"status": "rejected"}
        active = self._acquire_active_tool_turn()
        if active is None:
            return {"status": "unavailable"}
        try:
            if tool_name.startswith("memorii_") and "preference" in tool_name:
                return self._handle_preference_tool_call(active=active, tool_name=tool_name, arguments=arguments)
            authority_request = self._structured_authority_request
            if authority_request is None:
                return {"status": "unavailable"}
            if tool_name == "memorii_read_fact":
                try:
                    request = _structured_fact_read_request(arguments)
                except (TypeError, ValueError):
                    return {"status": "rejected"}
                response = self._service.read_structured_facts(
                    request,
                    authority_request=authority_request,
                    authenticated_host_ingress=self._issue_host_ingress(
                        active.session_id, self._authenticated_author_id, datetime.now(UTC)
                    ),
                )
                return response.model_dump(mode="json")
            pin = self._service.load_captured_turn_catalog_pin(
                ledger=active.ledger,
                authority_request=authority_request,
                authenticated_host_ingress=self._issue_host_ingress(
                    active.session_id, self._authenticated_author_id, datetime.now(UTC)
                ),
            )
            if not isinstance(pin, CatalogCapturedTurnPin):
                return {"status": "unavailable"}
            dispatch = self._service.resolve_captured_turn_catalog_dispatch(pin=pin)
            if dispatch not in {"seed", "reports_to", "default_catalog"}:
                return {"status": "denied"}
            try:
                request = self._structured_tool_request(
                    active=active,
                    arguments=arguments,
                    reports_to=dispatch == "reports_to",
                    default_catalog=dispatch == "default_catalog",
                )
            except (TypeError, ValueError):
                return {"status": "rejected"}
            if self._structured_tool_is_current is None or not self._structured_tool_is_current():
                return {"status": "denied"}
            request = request.model_copy(
                update={
                    "captured_pin": CapturedCatalogPinReference(
                        capture_id=pin.capture_id,
                        pin_memory_id=pin.memory_id,
                        pin_digest=pin.pin_digest,
                        catalog_scope=pin.catalog_scope,
                        catalog_digest=pin.catalog_digest,
                        selected_version_id=pin.selected_version_id,
                        selected_version_digest=pin.selected_version_digest,
                        runtime_bundle_digest=pin.runtime_bundle_digest,
                    ),
                }
            )
            response = self._service.submit_structured_fact(
                request,
                authenticated_host_ingress=self._issue_host_ingress(
                    active.session_id, self._authenticated_author_id, datetime.now(UTC)
                ),
            )
            result: dict[str, object] = {"status": response.status}
            if response.operation_id is not None:
                result["operation_id"] = response.operation_id
            return result
        finally:
            with self._condition:
                self._active_tool_calls -= 1
                self._condition.notify_all()

    def _acquire_active_tool_turn(self) -> _CapturedTurnHandle | None:
        with self._condition:
            active = self._active_turn
            if (
                self._closed
                or active is None
                or active.closing
                or self._active_turn_ambiguous
                or active.expires_at <= datetime.now(UTC)
            ):
                return None
            self._active_tool_calls += 1
            return active

    def _handle_preference_tool_call(
        self,
        *,
        active: _CapturedTurnHandle,
        tool_name: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        service = self._preference_service
        if service is None:
            return {"status": "unavailable"}
        try:
            self._require_current_authority()
        except (OSError, ValueError):
            return {"status": "denied"}
        try:
            if tool_name == "memorii_create_preference_candidate":
                preference = service.create_candidate(
                    self._preference_write_request(active=active, arguments=arguments)
                )
                if preference is None:
                    return {"status": "abstained"}
                return {
                    "status": "candidate",
                    "preference_id": preference.preference_id,
                    "preference_key": preference.preference_key,
                    "value": preference.value,
                    "source_digest": preference.source_digest,
                }
            if tool_name == "memorii_confirm_preference":
                evidence = self._require_preference_approval_quote(active=active, arguments=arguments, closing=False)
                preference = service.confirm(
                    preference_id=_required_string(arguments, "preference_id"),
                    holder_user_id=self._authenticated_author_id,
                    agent_id=self._authenticated_agent_id,
                    preference_key=_required_string(arguments, "preference_key"),
                    value=_required_string(arguments, "value"),
                    source_digest=_required_digest(arguments, "source_digest"),
                    approval_evidence=evidence,
                )
                return _preference_result("confirmed", preference)
            if tool_name == "memorii_close_preference":
                evidence = self._require_preference_approval_quote(active=active, arguments=arguments, closing=True)
                state = arguments.get("state")
                if state not in {"expired", "retracted", "rejected"}:
                    raise ValueError("preference close state is invalid")
                preference = service.close(
                    preference_id=_required_string(arguments, "preference_id"),
                    holder_user_id=self._authenticated_author_id,
                    agent_id=self._authenticated_agent_id,
                    preference_key=_required_string(arguments, "preference_key"),
                    value=_required_string(arguments, "value"),
                    source_digest=_required_digest(arguments, "source_digest"),
                    state=state,
                    evidence=evidence,
                )
                return _preference_result("closed", preference)
            if tool_name == "memorii_read_preference":
                if set(arguments) - {"canonical_topic_id", "preference_key", "view"}:
                    raise ValueError("preference read arguments are not closed")
                view = arguments.get("view")
                if view not in {"current", "history"}:
                    raise ValueError("preference read view is invalid")
                topic = arguments.get("canonical_topic_id")
                key = arguments.get("preference_key")
                if topic is not None and (not isinstance(topic, str) or not topic):
                    raise ValueError("preference topic is invalid")
                if key is not None and (not isinstance(key, str) or not key):
                    raise ValueError("preference key is invalid")
                records = service.read(
                    PreferenceReadRequest(
                        holder_user_id=self._authenticated_author_id,
                        agent_id=self._authenticated_agent_id,
                        canonical_topic_id=topic,
                        preference_key=key,
                        history=view == "history",
                    )
                )
                return {"status": "ok", "preferences": [record.model_dump(mode="json") for record in records]}
            if tool_name == "memorii_set_preference_delegation":
                allowed = {"delegated_agent_id", "state", "approval_quote", "approval_quote_start"}
                if set(arguments) != allowed:
                    raise ValueError("preference delegation arguments are not closed")
                delegated_agent_id = _required_string(arguments, "delegated_agent_id")
                state = arguments.get("state")
                if state not in {"active", "revoked"}:
                    raise ValueError("preference delegation state is invalid")
                quote = _required_string(arguments, "approval_quote")
                if quote != preference_delegation_sentence(
                    delegated_agent_id=delegated_agent_id,
                    state=state,
                ):
                    raise ValueError("preference delegation grammar is invalid")
                prepared = self._load_active_prepared_source(active)
                span = self._resolve_sentence_span(
                    prepared=prepared,
                    source_quote=quote,
                    source_quote_start=arguments.get("approval_quote_start"),
                )
                proof = span.text_mapping_proof
                if not isinstance(proof, VerbatimTextArtifactMappingProof):
                    raise ValueError("preference delegation mapping is unavailable")
                start = proof.retained_span.start + (span.projection_span.start - proof.projection_span.start)
                record = service.set_delegation(
                    holder_user_id=self._authenticated_author_id,
                    acting_agent_id=self._authenticated_agent_id,
                    delegated_agent_id=delegated_agent_id,
                    state=state,
                    evidence=(active.ledger.source_id, active.ledger.source_digest, start, start + len(quote)),
                )
                if record is None:
                    return {"status": "denied"}
                return {"status": state, "delegated_agent_id": delegated_agent_id, "revision": record.revision}
        except MemoryPlaneRevisionConflictError:
            return {"status": "unavailable"}
        except (TypeError, ValueError):
            return {"status": "rejected"}
        raise ValueError(f"Memorii does not provide Hermes tool {tool_name!r}")

    def _preference_write_request(
        self,
        *,
        active: _CapturedTurnHandle,
        arguments: dict[str, object],
    ) -> PreferenceWriteRequest:
        allowed = {
            "topic_type",
            "topic_quote",
            "canonical_topic_id",
            "preference_key",
            "value",
            "source_quote",
            "source_quote_start",
            "valid_until",
        }
        required = allowed - {"valid_until"}
        if set(arguments) - allowed or not required <= set(arguments):
            raise ValueError("preference candidate arguments are not closed")
        topic_quote = _required_string(arguments, "topic_quote")
        prepared = self._load_active_prepared_source(active)
        span = self._resolve_sentence_span(
            prepared=prepared,
            source_quote=arguments["source_quote"],
            source_quote_start=arguments["source_quote_start"],
        )
        proof = span.text_mapping_proof
        if not isinstance(proof, VerbatimTextArtifactMappingProof):
            raise ValueError("preference source mapping is unavailable")
        start = proof.retained_span.start + (span.projection_span.start - proof.projection_span.start)
        source_quote = _required_string(arguments, "source_quote")
        request = PreferenceWriteRequest.model_validate(
            {
                "holder_user_id": self._authenticated_author_id,
                "authenticated_author_id": self._authenticated_author_id,
                "authenticated_source_id": active.ledger.source_id,
                "authenticated_agent_id": self._authenticated_agent_id,
                "topic_type": arguments["topic_type"],
                "topic_quote": topic_quote,
                "canonical_topic_id": arguments["canonical_topic_id"],
                "preference_key": arguments["preference_key"],
                "value": arguments["value"],
                "source_id": active.ledger.source_id,
                "source_digest": active.ledger.source_digest,
                "assertion_start": start,
                "assertion_end": start + len(source_quote),
                "origin": "user_assertion",
                "event_time": active.ledger.captured_at,
                "valid_until": arguments.get("valid_until"),
            }
        )
        expected = preference_candidate_sentence(
            topic_quote=topic_quote,
            preference_key=request.preference_key,
            value=request.value,
            valid_until=request.valid_until,
        )
        if source_quote != expected:
            raise ValueError("preference assertion grammar is invalid")
        return request

    def _require_preference_approval_quote(
        self,
        *,
        active: _CapturedTurnHandle,
        arguments: dict[str, object],
        closing: bool,
    ) -> tuple[str, str, int, int]:
        quote_field = "revocation_quote" if closing else "approval_quote"
        offset_field = "revocation_quote_start" if closing else "approval_quote_start"
        common = {"preference_id", "preference_key", "value", "source_digest", quote_field, offset_field}
        allowed = common | ({"state"} if closing else set())
        if set(arguments) - allowed or set(arguments) != allowed:
            raise ValueError("preference approval arguments are not closed")
        preference_id = _required_string(arguments, "preference_id")
        assert self._preference_service is not None
        record = self._preference_service.load_preference(preference_id)
        if record is None or (
            _required_string(arguments, "preference_key"),
            _required_string(arguments, "value"),
            _required_digest(arguments, "source_digest"),
        ) != (record.preference_key, record.value, record.source_digest):
            raise ValueError("preference approval target is invalid")
        state = arguments.get("state") if closing else None
        expected = (
            preference_close_sentence(
                state=str(state),
                topic_id=record.canonical_topic_id,
                preference_key=record.preference_key,
                value=record.value,
                source_digest=record.source_digest,
            )
            if closing
            else preference_confirmation_sentence(
                topic_id=record.canonical_topic_id,
                preference_key=record.preference_key,
                value=record.value,
                source_digest=record.source_digest,
            )
        )
        if arguments[quote_field] != expected:
            raise ValueError("preference approval grammar is invalid")
        prepared = self._load_active_prepared_source(active)
        span = self._resolve_sentence_span(
            prepared=prepared,
            source_quote=arguments[quote_field],
            source_quote_start=arguments[offset_field],
        )
        proof = span.text_mapping_proof
        if not isinstance(proof, VerbatimTextArtifactMappingProof):
            raise ValueError("preference approval mapping is unavailable")
        start = proof.retained_span.start + (span.projection_span.start - proof.projection_span.start)
        quote = _required_string(arguments, quote_field)
        if active.ledger.source_id == record.source_id or active.ledger.source_digest == record.source_digest:
            raise ValueError("preference approval evidence must be distinct")
        return (active.ledger.source_id, active.ledger.source_digest, start, start + len(quote))

    def _structured_tool_request(
        self,
        *,
        active: _CapturedTurnHandle,
        arguments: dict[str, object],
        reports_to: bool = False,
        default_catalog: bool = False,
    ) -> StructuredFactSubmissionRequest:
        ordinary_allowed = {
            "schema_version",
            "source_quote",
            "source_quote_start",
            "subject_quote",
            "predicate_anchor_quote",
            "object_quote",
            "proposal",
        }
        proposal_value = arguments.get("proposal")
        is_default_correction = (
            default_catalog
            and type(proposal_value) is dict
            and type(proposal_value.get("corrections")) is list
            and bool(proposal_value["corrections"])
        )
        allowed = {"schema_version", "proposal", "correction"} if is_default_correction else ordinary_allowed
        if (
            set(arguments) - allowed
            or type(arguments.get("schema_version")) is not int
            or arguments["schema_version"] != 1
        ):
            raise ValueError("structured tool arguments are not closed")
        required = allowed - ({"source_quote_start"} if not is_default_correction else set())
        if set(arguments) < required or (
            not is_default_correction
            and any(
                not isinstance(arguments[name], str) or not arguments[name]
                for name in required - {"schema_version", "proposal"}
            )
        ):
            raise ValueError("structured tool arguments are incomplete")
        source_start = arguments.get("source_quote_start")
        if source_start is not None and (type(source_start) is not int or source_start < 0):
            raise ValueError("structured tool source quote offset is invalid")
        proposal_value = arguments["proposal"]
        if type(proposal_value) is not dict:
            raise ValueError("structured tool proposal is invalid")
        if default_catalog:
            _validate_default_catalog_argument_shape(proposal_value)
        else:
            _validate_fact_only_argument_shape(proposal_value)
        # Hermes function arguments arrive from JSON, while the typed proposal
        # contract deliberately models ordered collections as tuples.
        proposal = ProviderSemanticProposal.model_validate(_json_arrays_to_tuples(proposal_value))
        if reports_to and default_catalog:
            raise ValueError("structured tool dispatch is ambiguous")
        if reports_to:
            validate_reports_to_tool_proposal(proposal)
        elif default_catalog:
            self._validate_default_catalog_tool_proposal(
                proposal=proposal,
                arguments=arguments,
            )
        else:
            HermesCompletedTurnRuntime._validate_fact_only_proposal(proposal=proposal, arguments=arguments)
        prepared = self._load_active_prepared_source(active)
        source_coordinates = (
            _default_catalog_source_coordinates(
                proposal=proposal,
                arguments=arguments,
            )
            if default_catalog and proposal.corrections
            else ((arguments["source_quote"], source_start),)
        )
        resolved_spans = tuple(
            self._resolve_sentence_span(
                prepared=prepared,
                source_quote=source_quote,
                source_quote_start=quote_start,
            )
            for source_quote, quote_start in source_coordinates
        )
        by_digest = {span.reference_digest: span for span in resolved_spans}
        if len(by_digest) != len(resolved_spans) and any(
            by_digest[span.reference_digest] != span for span in resolved_spans
        ):
            raise ValueError("default catalog correction source spans conflict")
        source_spans = tuple(by_digest[digest] for digest in sorted(by_digest))
        raw = encode_typed_value(arguments)
        assert self._structured_authority_request is not None
        return StructuredFactSubmissionRequest(
            source_id=active.ledger.source_id,
            source_digest=active.ledger.source_digest,
            authority_request=self._structured_authority_request,
            exact_source_spans=source_spans,
            raw_proposal_artifact=raw,
            raw_proposal_artifact_digest=sha256(raw).hexdigest(),
            protocol_version="memorii.hermes.structured-fact-tool.v1",
            parser_version="memorii.hermes.retained-sentence-parser.v1",
            proposal=proposal,
            proposal_bytes=encode_typed_value(proposal.model_dump(mode="python")),
        )

    @staticmethod
    def _validate_default_catalog_tool_proposal(
        *,
        proposal: ProviderSemanticProposal,
        arguments: dict[str, object],
    ) -> None:
        if proposal.facts and proposal.facts[0].predicate_id in {
            "project_deadline",
            "project_owner",
            "project_status",
        }:
            # The selected release extends, rather than replaces, the seed
            # grammar.  Retain the seed's exact validation semantics.
            HermesCompletedTurnRuntime._validate_fact_only_proposal(proposal=proposal, arguments=arguments)
            return
        row = validate_default_catalog_provider_lifecycle_proposal(proposal)
        if proposal.corrections:
            _validate_default_catalog_correction_grounding(
                proposal=proposal,
                arguments=arguments,
                row=row,
            )
            return
        source_quote = arguments["source_quote"]
        if not isinstance(source_quote, str):
            raise ValueError("default catalog assertion quotes do not match")
        facts = _default_catalog_lifecycle_facts(proposal)
        if any(
            fact.assertion_quote != source_quote or fact.predicate_anchor_quote != arguments["predicate_anchor_quote"]
            for fact in facts
        ):
            raise ValueError("default catalog assertion quotes do not match")
        if proposal.corrections and proposal.corrections[0].assertion_quote != source_quote:
            raise ValueError("default catalog correction quote does not match")
        if proposal.retractions and proposal.retractions[0].assertion_quote != source_quote:
            raise ValueError("default catalog retraction quote does not match")
        anchors = _default_catalog_lifecycle_anchors(proposal)
        mentions = {mention.local_id: mention for mention in proposal.mentions}
        for fact in facts:
            subject = mentions[fact.subject_entity_ref]
            if subject.mention_quote != arguments["subject_quote"] or subject.mention_context_quote != source_quote:
                raise ValueError("default catalog subject grounding is invalid")
            if isinstance(fact.object, ProviderEntityObject):
                object_mention = mentions[fact.object.entity_ref]
                if (
                    object_mention.mention_quote != arguments["object_quote"]
                    or object_mention.mention_context_quote != source_quote
                ):
                    raise ValueError("default catalog object grounding is invalid")
            else:
                object_quote = arguments["object_quote"]
                if not isinstance(object_quote, str):
                    raise ValueError("default catalog object grounding is invalid")
                validate_default_catalog_literal_grounding(
                    row=row,
                    value=fact.object,
                    object_quote=object_quote,
                )
        for quote in (
            arguments["subject_quote"],
            arguments["predicate_anchor_quote"],
            arguments["object_quote"],
            *anchors,
        ):
            if not isinstance(quote, str) or source_quote.count(quote) != 1:
                raise ValueError("default catalog quote is absent or ambiguous")

    @staticmethod
    def _validate_fact_only_proposal(*, proposal: ProviderSemanticProposal, arguments: dict[str, object]) -> None:
        if (
            proposal.abstained
            or len(proposal.facts) != 1
            or proposal.corrections
            or proposal.retractions
            or proposal.action_states
            or proposal.identity_operations
        ):
            raise ValueError("structured tool proposal is outside the fact-only grammar")
        fact = proposal.facts[0]
        if (
            fact.predicate_id not in {"project_owner", "project_status", "project_deadline"}
            or fact.commitment != "asserted"
            or fact.attributed_to_entity_ref is not None
        ):
            raise ValueError("structured tool fact commitment is invalid")
        if (
            fact.assertion_quote != arguments["source_quote"]
            or fact.predicate_anchor_quote != arguments["predicate_anchor_quote"]
        ):
            raise ValueError("structured tool assertion quotes do not match")
        mentions = {mention.local_id: mention for mention in proposal.mentions}
        subject = mentions.get(fact.subject_entity_ref)
        if (
            subject is None
            or subject.mention_quote != arguments["subject_quote"]
            or subject.mention_context_quote != arguments["source_quote"]
        ):
            raise ValueError("structured tool subject grounding is invalid")
        source_quote = arguments["source_quote"]
        assert isinstance(source_quote, str)
        for quote in (
            arguments["subject_quote"],
            arguments["predicate_anchor_quote"],
            arguments["object_quote"],
            *fact.temporal_qualifier_quotes,
        ):
            if not isinstance(quote, str) or source_quote.count(quote) != 1:
                raise ValueError("structured tool quote is absent or ambiguous")
        if isinstance(fact.object, ProviderEntityObject):
            if fact.predicate_id != "project_owner":
                raise ValueError("structured tool entity object predicate is invalid")
            obj = mentions.get(fact.object.entity_ref)
            if (
                obj is None
                or obj.mention_quote != arguments["object_quote"]
                or obj.mention_context_quote != arguments["source_quote"]
            ):
                raise ValueError("structured tool object grounding is invalid")
            if len(proposal.mentions) != 2 or fact.object.entity_ref == fact.subject_entity_ref:
                raise ValueError("structured tool entity mentions are invalid")
        else:
            if fact.predicate_id == "project_owner" or len(proposal.mentions) != 1:
                raise ValueError("structured tool literal mentions are invalid")
            literal_type, canonical_value = _parse_project_assertions_literal(
                predicate_id=fact.predicate_id, value_quote=arguments["object_quote"]
            )
            if (
                canonical_value is None
                or fact.object.literal_type != literal_type
                or fact.object.canonical_value != canonical_value
                or fact.object.unit is not None
            ):
                raise ValueError("structured tool literal grounding is invalid")

    def _load_active_prepared_source(self, active: _CapturedTurnHandle) -> PreparedSource:
        runtime = self._service._provider_ingestion._semantic_runtime
        if runtime is None or runtime.prepared_source_repository is None:
            raise ValueError("captured prepared source is unavailable")
        prepared = runtime.prepared_source_repository.load(
            source_id=active.ledger.source_id,
            source_digest=active.ledger.source_digest,
        )
        if (
            prepared is None
            or prepared.preparation_fingerprint != active.ledger.preparation_fingerprint
            or prepared.source_id != active.ledger.source_id
            or prepared.source_digest != active.ledger.source_digest
        ):
            raise ValueError("captured prepared source is unavailable")
        return prepared

    @staticmethod
    def _resolve_sentence_span(*, prepared: PreparedSource, source_quote: object, source_quote_start: object):
        if not isinstance(source_quote, str):
            raise ValueError("structured tool source quote is invalid")
        matches = []
        for span in prepared.sentence_spans:
            proof = span.text_mapping_proof
            if not isinstance(proof, VerbatimTextArtifactMappingProof):
                continue
            text = prepared.semantic_text[span.projection_span.start : span.projection_span.end]
            if text != source_quote:
                continue
            retained_start = proof.retained_span.start + (span.projection_span.start - proof.projection_span.start)
            if source_quote_start is not None and retained_start != source_quote_start:
                continue
            matches.append(span)
        if len(matches) != 1:
            raise ValueError("structured tool source sentence is absent or ambiguous")
        return matches[0]

    def capture_user_turn(
        self,
        *,
        session_id: str,
        turn_ordinal: int,
        message: str,
        authenticated_author_id: str,
        received_at: datetime,
    ) -> None:
        """Synchronously retain the user source before Hermes can dispatch tools."""
        author = authenticated_author_id.strip()
        if (
            not session_id.strip()
            or turn_ordinal < 1
            or not message
            or author != self._authenticated_author_id
            or received_at.tzinfo is None
        ):
            raise ValueError("Hermes turn-start authentication is incomplete")
        self._require_current_authority()
        digest = sha256(message.encode("utf-8")).hexdigest()
        with self._condition:
            if self._closed:
                raise RuntimeError("Hermes semantic worker is closed")
            active = self._active_turn
            if active is not None and active.expires_at <= received_at:
                self._active_turn = None
                active = None
            if active is not None:
                if (
                    active.session_id == session_id
                    and active.turn_ordinal == turn_ordinal
                    and active.message_digest == digest
                ):
                    return
                self._active_turn_ambiguous = True
                raise ValueError("Hermes overlapping turn context is ambiguous")

        ingress = self._service._preflight_ingress(self._issue_host_ingress(session_id, author, received_at))
        if ingress is None:
            raise ValueError("Hermes turn-start ingress is unavailable")
        runtime = self._service._composed_semantic_runtime
        if runtime is None or runtime.text_preparation_service is None or runtime.text_preparation_policy is None:
            raise ValueError("Hermes turn-start preparation is unavailable")
        coordinate_digest = sha256(
            (
                "memorii.hermes.captured-turn.coordinate.v1:\0"
                f"{self._installation_id}\0{session_id}\0{author}\0{self._authenticated_agent_id}\0"
                f"{turn_ordinal}\0{digest}"
            ).encode()
        ).hexdigest()
        request = HermesCompletedTurnAdmissionRequest(
            installation_id=self._installation_id,
            session_id=session_id,
            authenticated_author_id=author,
            authenticated_agent_id=self._authenticated_agent_id,
            project_task_namespace=self._project_task_id,
            turn_ordinal=turn_ordinal,
            canonical_transcript_digest=coordinate_digest,
            completed_messages=(
                HermesCompletedTurnMessage(role="user", content=message),
                HermesCompletedTurnMessage(role="assistant", content="capture-placeholder"),
            ),
            completed_at=received_at,
            ingress=ingress,
        )
        child_delivery_id = derive_composite_child_delivery_id(request.delivery_id, "hermes-completed-turn-user")
        identity = DeliveryIdentity.create(ingress.delivery_principal_binding, child_delivery_id)
        child = _prepare_governed_child_source(
            request=request,
            message=request.completed_messages[0],
            child_delivery_id=child_delivery_id,
            child_identity=identity,
            child_kind="hermes-completed-turn-user",
        )
        prepared_admission = GovernedSourceAdmissionService(self._service._memory_plane).prepare_atomic(
            source=child.source,
            delivery_identity=identity,
            ingress=ingress,
            operation_id="hermes-captured-turn-operation:v1:" + coordinate_digest,
            evidence_only=True,
            bootstrap_language_evidence=child.request.bootstrap_language_evidence,
        )
        prepared_source = runtime.text_preparation_service.prepare(
            TextPreparationRequest(
                observation=prepared_admission.accepted.observation,
                policy=runtime.text_preparation_policy,
            )
        )
        ledger = HermesCapturedTurnLedger(
            installation_id=self._installation_id,
            session_id=session_id,
            principal_id=author,
            agent_id=self._authenticated_agent_id,
            turn_ordinal=turn_ordinal,
            message_digest=digest,
            source_id=prepared_admission.accepted.source_id,
            source_digest=prepared_admission.accepted.source_digest,
            preparation_fingerprint=prepared_source.preparation_fingerprint,
            captured_at=received_at,
        )
        owner = HermesCapturedTurnSourceOwner(
            atomic_store=self._service._semantic_atomic_store,
            preparation=runtime.text_preparation_service,
            policy=runtime.text_preparation_policy,
            writer_binding=lambda: self._service._semantic_writer_admission.commit_binding(
                self._service._semantic_writer_admission.current()
            ),
        )
        owner.capture(admission=prepared_admission, ledger=ledger)
        with self._condition:
            if self._active_turn is not None:
                self._active_turn_ambiguous = True
                raise ValueError("Hermes overlapping turn context is ambiguous")
            self._active_turn = _CapturedTurnHandle(
                session_id=session_id,
                turn_ordinal=turn_ordinal,
                message_digest=digest,
                admission=prepared_admission,
                ledger=ledger,
                generation=token_hex(16),
                expires_at=received_at + _CAPTURED_TURN_TTL,
            )

    def complete_captured_turn(
        self,
        *,
        user_content: str,
        assistant_content: str,
        messages: list[dict[str, object]] | None,
        session_id: str,
        authenticated_author_id: str | None,
        received_at: datetime,
    ) -> bool:
        """Join a captured user callback to completion without re-admitting it."""
        author = authenticated_author_id.strip() if isinstance(authenticated_author_id, str) else ""
        digest = sha256(user_content.encode("utf-8")).hexdigest()
        with self._condition:
            active = self._active_turn
            if active is None:
                return False
            if (
                self._active_turn_ambiguous
                or active.closing
                or active.expires_at <= received_at
                or active.session_id != session_id
                or active.message_digest != digest
                or author != self._authenticated_author_id
            ):
                # A captured source already exists for this callback window.
                # Never let a mismatched completion fall back into ordinary
                # completed-turn admission and create a second user lineage.
                raise ValueError("Hermes captured-turn completion is mismatched or ambiguous")
            self._active_turn = _CapturedTurnHandle(**(active.__dict__ | {"closing": True}))
            # A tool has an immutable view of this handle.  Completion must
            # wait for that submission to publish its captured coordination
            # transition before choosing ordinary versus structured work.
            while self._active_tool_calls:
                self._condition.wait()
        try:
            canonical = _canonicalize_completed_messages(
                messages=messages, user_content=user_content, assistant_content=assistant_content
            )
            ordinal = sum(1 for item in canonical if item["role"] == "user")
            if ordinal != active.turn_ordinal:
                raise ValueError("Hermes captured-turn completion ordinal is mismatched")
            completed_at = _completed_turn_timestamp(canonical)
            ingress = self._service._preflight_ingress(self._issue_host_ingress(session_id, author, completed_at))
            if ingress is None:
                raise ValueError("Hermes completed-turn ingress is unavailable")
            request = HermesCompletedTurnAdmissionRequest(
                installation_id=self._installation_id,
                session_id=session_id,
                authenticated_author_id=author,
                authenticated_agent_id=self._authenticated_agent_id,
                project_task_namespace=self._project_task_id,
                turn_ordinal=ordinal,
                canonical_transcript_digest=_canonical_messages_digest(canonical),
                completed_messages=(
                    HermesCompletedTurnMessage(role="user", content=user_content),
                    HermesCompletedTurnMessage(role="assistant", content=assistant_content),
                ),
                completed_at=completed_at,
                ingress=ingress,
            )
            assistant_delivery = derive_composite_child_delivery_id(
                request.delivery_id, "hermes-completed-turn-assistant"
            )
            assistant_identity = DeliveryIdentity.create(ingress.delivery_principal_binding, assistant_delivery)
            assistant = _prepare_governed_child_source(
                request=request,
                message=request.completed_messages[1],
                child_delivery_id=assistant_delivery,
                child_identity=assistant_identity,
                child_kind="hermes-completed-turn-assistant",
            )
            assistant_admission = GovernedSourceAdmissionService(self._service._memory_plane).prepare_atomic(
                source=assistant.source,
                delivery_identity=assistant_identity,
                ingress=ingress,
                operation_id="hermes-captured-turn-assistant:v1:" + active.ledger.capture_id,
                evidence_only=True,
            )
            completion = HermesCapturedTurnCompletion(
                capture_id=active.ledger.capture_id,
                session_id=session_id,
                principal_id=author,
                agent_id=self._authenticated_agent_id,
                turn_ordinal=ordinal,
                user_message_digest=digest,
                assistant_message_digest=sha256(assistant_content.encode("utf-8")).hexdigest(),
                transcript_digest=_canonical_messages_digest(canonical),
            )
            ordinary = self._service._semantic_atomic_store.publish_captured_turn_completion(
                ledger=active.ledger,
                assistant=assistant_admission,
                completion=completion,
                authenticated_ingress=ingress,
                writer_binding=self._service._semantic_writer_admission.commit_binding(
                    self._service._semantic_writer_admission.current()
                ),
            )
            if ordinary is not None:
                # The ordinary operation has a distinct retained-source fence;
                # recovery owns it rather than reusing the capture admission's
                # source-only operation.
                self._enqueue(_RecoverySweep())
        finally:
            with self._condition:
                self._active_turn = None
                self._active_turn_ambiguous = False
                self._condition.notify_all()
        return True

    def sync_completed_turn(
        self,
        *,
        user_content: str,
        assistant_content: str,
        messages: list[dict[str, object]] | None,
        session_id: str,
        authenticated_author_id: str | None,
        received_at: datetime,
    ) -> None:
        with self._condition:
            if self._closed:
                raise RuntimeError("Hermes semantic worker is closed")
        author = authenticated_author_id.strip() if isinstance(authenticated_author_id, str) else ""
        if author != self._authenticated_author_id or received_at.tzinfo is None:
            raise ValueError("Hermes completed-turn authentication is incomplete")
        # Re-open the installation authority immediately before any ingress,
        # egress, or durable operation. A changed/expired sidecar fails closed.
        self._require_current_authority()
        canonical_messages = _canonicalize_completed_messages(
            messages=messages, user_content=user_content, assistant_content=assistant_content
        )
        # Hermes may redeliver the same persisted completion after the callback
        # clock has advanced.  Source retention is bound to the transcript's
        # final persisted timestamp, never to the callback delivery time.
        completed_at = _completed_turn_timestamp(canonical_messages)
        ordinal = sum(1 for item in canonical_messages if item["role"] == "user")
        host_ingress = self._issue_host_ingress(session_id, author, completed_at)
        ingress = self._service._preflight_ingress(host_ingress)
        if ingress is None:
            raise ValueError("Hermes completed-turn ingress is unavailable")
        durable_capture = self._service._semantic_atomic_store.find_captured_turn(
            installation_id=self._installation_id,
            session_id=session_id,
            principal_id=author,
            agent_id=self._authenticated_agent_id,
            turn_ordinal=ordinal,
            message_digest=sha256(user_content.encode("utf-8")).hexdigest(),
        )
        if durable_capture is not None:
            request = HermesCompletedTurnAdmissionRequest(
                installation_id=self._installation_id,
                session_id=session_id,
                authenticated_author_id=author,
                authenticated_agent_id=self._authenticated_agent_id,
                project_task_namespace=self._project_task_id,
                turn_ordinal=ordinal,
                canonical_transcript_digest=_canonical_messages_digest(canonical_messages),
                completed_messages=(
                    HermesCompletedTurnMessage(role="user", content=user_content),
                    HermesCompletedTurnMessage(role="assistant", content=assistant_content),
                ),
                completed_at=completed_at,
                ingress=ingress,
            )
            assistant_delivery = derive_composite_child_delivery_id(
                request.delivery_id, "hermes-completed-turn-assistant"
            )
            assistant_identity = DeliveryIdentity.create(ingress.delivery_principal_binding, assistant_delivery)
            assistant = _prepare_governed_child_source(
                request=request,
                message=request.completed_messages[1],
                child_delivery_id=assistant_delivery,
                child_identity=assistant_identity,
                child_kind="hermes-completed-turn-assistant",
            )
            assistant_admission = GovernedSourceAdmissionService(self._service._memory_plane).prepare_atomic(
                source=assistant.source,
                delivery_identity=assistant_identity,
                ingress=ingress,
                operation_id="hermes-captured-turn-assistant:v1:" + durable_capture.capture_id,
                evidence_only=True,
            )
            completion = HermesCapturedTurnCompletion(
                capture_id=durable_capture.capture_id,
                session_id=session_id,
                principal_id=author,
                agent_id=self._authenticated_agent_id,
                turn_ordinal=ordinal,
                user_message_digest=durable_capture.message_digest,
                assistant_message_digest=sha256(assistant_content.encode("utf-8")).hexdigest(),
                transcript_digest=_canonical_messages_digest(canonical_messages),
            )
            ordinary = self._service._semantic_atomic_store.publish_captured_turn_completion(
                ledger=durable_capture,
                assistant=assistant_admission,
                completion=completion,
                authenticated_ingress=ingress,
                writer_binding=self._service._semantic_writer_admission.commit_binding(
                    self._service._semantic_writer_admission.current()
                ),
            )
            if ordinary is not None:
                self._enqueue(_RecoverySweep())
            return
        request = HermesCompletedTurnAdmissionRequest(
            installation_id=self._installation_id,
            session_id=session_id,
            authenticated_author_id=author,
            authenticated_agent_id=self._authenticated_agent_id,
            project_task_namespace=self._project_task_id,
            turn_ordinal=ordinal,
            canonical_transcript_digest=_canonical_messages_digest(canonical_messages),
            completed_messages=(
                HermesCompletedTurnMessage(role="user", content=user_content),
                HermesCompletedTurnMessage(role="assistant", content=assistant_content),
            ),
            completed_at=completed_at,
            ingress=ingress,
        )
        binding = self._service._semantic_writer_admission.commit_binding(
            self._service._semantic_writer_admission.current()
        )
        admitted = HermesCompletedTurnAdmissionService(
            atomic_store=self._service._semantic_atomic_store, writer_binding=binding
        ).admit(request)
        self._enqueue(_CompletedTurnWork(admitted=admitted, ingress=ingress))

    def _enqueue(self, work: _CompletedTurnWork | _RecoverySweep) -> None:
        with self._condition:
            if self._closed:
                raise RuntimeError("Hermes semantic worker is closed")
            self._outstanding += 1
        self._work.put(work)

    def _worker_loop(self) -> None:
        while True:
            work = self._work.get()
            if isinstance(work, _StopWorker):
                self._work.task_done()
                return
            try:
                if isinstance(work, _RecoverySweep):
                    self._recover_pending()
                    with self._condition:
                        # A successful reconciliation resolves every retained
                        # post-admission failure before a caller can observe idle.
                        self._failures.clear()
                else:
                    self._process(work)
            except Exception as exc:
                logger.exception("hermes_completed_turn_semantic_worker_failed")
                with self._condition:
                    self._failures.append(exc)
                if isinstance(work, _CompletedTurnWork):
                    # A work failure can leave admitted V3 state pending after
                    # its lease. Reconcile once; a failed sweep stays visible
                    # and never schedules an unbounded recovery loop.
                    self._enqueue(_RecoverySweep())
            finally:
                with self._condition:
                    self._outstanding -= 1
                    self._condition.notify_all()
                self._work.task_done()

    def close(self, *, timeout: float = 1200.0) -> None:
        """Drain admitted work, stop the daemon, and reject future ingress."""
        with self._condition:
            if self._stopped:
                return
            self._closed = True
        try:
            self.wait_for_idle(timeout=timeout)
        finally:
            self._work.put(_StopWorker())
            self._worker.join(timeout=timeout)
            if self._worker.is_alive():
                raise TimeoutError("Hermes semantic worker did not stop")
            with self._condition:
                self._stopped = True

    def _recover_pending(self) -> None:
        """Resume retained V3 work after the prior claim's short lease expires."""
        deadline = time.monotonic() + 65.0
        while True:
            self._require_current_authority()
            outcomes = self._service.reconcile_memory_evolution()
            retryable = [outcome for outcome in outcomes if outcome.retryable]
            if not retryable:
                return
            if time.monotonic() >= deadline:
                raise RuntimeError("Hermes semantic recovery remained pending")
            time.sleep(1.0)

    def _process(self, work: _CompletedTurnWork) -> None:
        ingress = work.ingress
        if work.captured_user_admission is not None:
            user_admission = work.captured_user_admission
        else:
            user_admission = work.admitted.normalization_inputs.source_admissions[0]
        coordinator = self._service._provider_ingestion
        with self._service._new_canonical_evidence_arena() as arena:
            handoff_with_lease = coordinator._bootstrap_prepare_and_handoff(
                prepared_admission=user_admission,
                authenticated_ingress=ingress,
                canonical_evidence_arena=arena,
            )
            if handoff_with_lease is None:
                raise ValueError("Hermes completed-turn Bootstrap handoff is unavailable")
            handoff, evidence_lease = handoff_with_lease
            try:
                terminal, guard = coordinator._run_semantic_ingestion(
                    operation_id=user_admission.operation_fence_binding.operation_id,
                    observation=user_admission.observation,
                    authenticated_ingress=ingress,
                    lease_session=None,
                    operation_fence=user_admission.operation_fence_binding,
                    bootstrap_handoff=handoff,
                    canonical_evidence_arena=arena,
                    canonical_evidence_lease=evidence_lease,
                )
            finally:
                if evidence_lease is not None:
                    evidence_lease.release()
        if "bootstrap_graph_terminal_persisted" not in terminal.reason_codes:
            raise RuntimeError(
                "Hermes completed-turn Bootstrap graph did not persist: " + ",".join(terminal.reason_codes)
            )

    def wait_for_idle(self, *, timeout: float = 1200.0) -> None:
        """Wait for admitted work and surface an unresolved worker failure."""
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._outstanding:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Hermes semantic worker did not become idle")
                self._condition.wait(remaining)
            if self._failures:
                failure = self._failures[0]
                raise RuntimeError("Hermes semantic worker failed") from failure

    def prefetch(self, *, query: str, session_id: str, authenticated_author_id: str, now: datetime) -> str:
        """Read committed semantic context through one fresh host-bound grant."""
        author = authenticated_author_id.strip()
        if not query.strip() or author != self._authenticated_author_id or now.tzinfo is None:
            return ""
        self._require_current_authority()
        task_id = self._project_task_id
        state_id = sha256(
            (
                "memorii.hermes.prefetch.v1:"
                f"{task_id}:{session_id}:{author}:{self._authenticated_agent_id}:"
                f"{query}:{now.isoformat()}:{token_hex(16)}"
            ).encode()
        ).hexdigest()
        rows = (
            ScopedNamespaceGrantRow(
                domain=MemoryDomain.SEMANTIC,
                task_id=task_id,
                session_id=None,
                user_id=author,
                agent_id=self._authenticated_agent_id,
                execution_node_id=None,
                solver_run_id=None,
            ),
        )
        read_authority = (
            self._structured_fact_read_authority() if self._structured_fact_read_authority is not None else None
        )
        if read_authority is None:
            return ""
        handle = self._scoped_read_authority.provision(
            host_task_id=task_id,
            host_state_id=state_id,
            rows=rows,
            expires_at=now.replace(microsecond=0) + timedelta(minutes=1),
            structured_fact_read_authorities=(read_authority,),
        )
        try:
            activation = self._service.retrieve_context(
                ScopedContextRequest(
                    host_task_id=task_id,
                    host_state_id=state_id,
                    declared_complete_mandatory_set=True,
                    mandatory_record_references=(),
                    optional_query=query,
                    optional_domains=(MemoryDomain.SEMANTIC,),
                    budget=ScopedContextBudget(
                        max_mandatory_items=1,
                        max_optional_items=8,
                        max_optional_omission_ids=8,
                        max_rendered_utf8_bytes=4096,
                    ),
                    reference_time=now,
                ),
                opaque_host_ingress=handle,
            )
        finally:
            self._scoped_read_authority.revoke(handle)
        if activation.status not in {ScopedContextStatus.COMPLETE, ScopedContextStatus.PARTIAL_OPTIONAL}:
            return ""
        return "\n".join(item.rendered_text for item in activation.optional_items)

    def lookup_structured_fact_status(
        self,
        *,
        operation_id: str,
        session_id: str,
        authenticated_author_id: str,
        now: datetime,
    ) -> dict[str, object]:
        """Return one current-grant-protected terminal status after restart."""
        author = authenticated_author_id.strip()
        if (
            not operation_id.strip()
            or author != self._authenticated_author_id
            or now.tzinfo is None
            or self._structured_authority_request is None
        ):
            return {"status": "unavailable"}
        self._require_current_authority()
        response = self._service.lookup_structured_fact_status(
            StructuredFactSubmissionStatusRequest(
                operation_id=operation_id,
                authority_request=self._structured_authority_request,
            ),
            authenticated_host_ingress=self._issue_host_ingress(session_id, author, now),
        )
        result: dict[str, object] = {"status": response.status}
        if response.operation_id is not None:
            result["operation_id"] = response.operation_id
        return result

    def read_structured_facts(
        self,
        *,
        request: StructuredFactReadRequest,
        session_id: str,
        authenticated_author_id: str,
        now: datetime,
    ) -> StructuredFactReadResponse:
        """Expose the protected structured lifecycle reader at the Hermes root."""
        if (
            authenticated_author_id.strip() != self._authenticated_author_id
            or now.tzinfo is None
            or self._structured_authority_request is None
        ):
            return StructuredFactReadResponse(status="denied")
        self._require_current_authority()
        return self._service.read_structured_facts(
            request,
            authority_request=self._structured_authority_request,
            authenticated_host_ingress=self._issue_host_ingress(
                session_id,
                self._authenticated_author_id,
                now,
            ),
        )


def _canonicalize_completed_messages(
    *, messages: list[dict[str, object]] | None, user_content: str, assistant_content: str
) -> tuple[dict[str, object], ...]:
    """Validate the closed Hermes ABI and return its canonical full transcript."""
    if not messages or len(messages) < 2:
        raise ValueError("Hermes completed-turn transcript is incomplete")
    canonical = tuple(_canonicalize_message(item) for item in messages)
    if canonical[-1]["role"] != "assistant" or canonical[-1]["content"] != assistant_content:
        raise ValueError("Hermes completed-turn transcript does not end in the supplied pair")
    preceding_users = [item for item in canonical[:-1] if item["role"] == "user"]
    if not preceding_users or preceding_users[-1]["content"] != user_content:
        raise ValueError("Hermes completed-turn transcript does not end in the supplied pair")
    pending_calls: set[str] = set()
    for item in canonical:
        if item["role"] == "assistant":
            tool_calls = item.get("tool_calls", ())
            if not isinstance(tool_calls, tuple):
                raise ValueError("Hermes assistant tool calls are invalid")
            for call in tool_calls:
                if not isinstance(call, dict) or not isinstance(call.get("id"), str):
                    raise ValueError("Hermes assistant tool calls are invalid")
                pending_calls.add(call["id"])
        elif item["role"] == "tool":
            call_id = item["tool_call_id"]
            if not isinstance(call_id, str) or call_id not in pending_calls:
                raise ValueError("Hermes tool message is unmatched")
            pending_calls.remove(call_id)
    if pending_calls:
        raise ValueError("Hermes transcript has unmatched tool calls")
    return canonical


def _json_arrays_to_tuples(value: object) -> object:
    """Translate JSON container syntax without relaxing the typed proposal schema."""
    if type(value) is list:
        return tuple(_json_arrays_to_tuples(item) for item in value)
    if type(value) is dict:
        return {key: _json_arrays_to_tuples(item) for key, item in value.items()}
    return value


def _validate_fact_only_argument_shape(proposal: dict[str, object]) -> None:
    """Keep runtime acceptance exactly aligned with the advertised JSON schema."""
    required = {
        "abstained",
        "mentions",
        "facts",
        "corrections",
        "retractions",
        "action_states",
        "identity_operations",
    }
    if set(proposal) != required or proposal.get("abstained") is not False:
        raise ValueError("structured tool proposal is not the closed fact grammar")
    empty = ("corrections", "retractions", "action_states", "identity_operations")
    if any(type(proposal[name]) is not list or proposal[name] for name in empty):
        raise ValueError("structured tool proposal contains a forbidden operation")
    mentions = proposal["mentions"]
    facts = proposal["facts"]
    if type(mentions) is not list or not 1 <= len(mentions) <= 2 or type(facts) is not list or len(facts) != 1:
        raise ValueError("structured tool proposal cardinality is invalid")
    mention_fields = {"local_id", "mention_quote", "mention_context_quote", "proposed_type"}
    if any(type(mention) is not dict or set(mention) != mention_fields for mention in mentions):
        raise ValueError("structured tool mention grammar is invalid")
    fact = facts[0]
    fact_fields = {
        "kind",
        "local_id",
        "predicate_id",
        "subject_entity_ref",
        "object",
        "assertion_quote",
        "predicate_anchor_quote",
        "polarity",
        "commitment",
        "attributed_to_entity_ref",
        "temporal_qualifier_quotes",
    }
    if type(fact) is not dict or set(fact) != fact_fields or fact.get("kind") != "fact":
        raise ValueError("structured tool fact grammar is invalid")
    obj = fact["object"]
    if type(obj) is not dict or obj.get("kind") not in {"entity", "literal"}:
        raise ValueError("structured tool object grammar is invalid")
    expected_object_fields = (
        {"kind", "entity_ref"} if obj["kind"] == "entity" else {"kind", "literal_type", "canonical_value", "unit"}
    )
    if set(obj) != expected_object_fields:
        raise ValueError("structured tool object grammar is invalid")


def _default_catalog_lifecycle_facts(proposal: ProviderSemanticProposal) -> tuple[ProviderFact, ...]:
    if proposal.corrections:
        correction = proposal.corrections[0]
        return (correction.corrected_fact, correction.replacement_fact)
    if proposal.retractions:
        return (proposal.retractions[0].retracted_fact,)
    return proposal.facts


def _ordinary_fact_tool_parameters(proposal_schema: dict[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "source_quote",
            "subject_quote",
            "predicate_anchor_quote",
            "object_quote",
            "proposal",
        ],
        "properties": {
            "schema_version": {"type": "integer", "const": 1},
            "source_quote": {"type": "string", "minLength": 1},
            "source_quote_start": {"type": "integer", "minimum": 0},
            "subject_quote": {"type": "string", "minLength": 1},
            "predicate_anchor_quote": {"type": "string", "minLength": 1},
            "object_quote": {"type": "string", "minLength": 1},
            "proposal": proposal_schema,
        },
    }


def _default_catalog_tool_parameters(proposal_schema: dict[str, object]) -> dict[str, object]:
    ordinary = _ordinary_fact_tool_parameters(proposal_schema)
    properties = ordinary["properties"]
    assert isinstance(properties, dict)
    properties["correction"] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["assertion_quote", "correction_anchor_quote", "corrected", "replacement"],
        "properties": {
            "assertion_quote": {"type": "string", "minLength": 1},
            "correction_anchor_quote": {"type": "string", "minLength": 1},
            "corrected": _default_catalog_fact_grounding_schema(),
            "replacement": _default_catalog_fact_grounding_schema(),
        },
    }
    ordinary["required"] = ["schema_version", "proposal"]
    ordinary["oneOf"] = [
        {"required": ["source_quote", "subject_quote", "predicate_anchor_quote", "object_quote"]},
        {"required": ["correction"]},
    ]
    return ordinary


def _default_catalog_fact_grounding_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["source_quote", "subject_quote", "predicate_anchor_quote", "object_quote"],
        "properties": {
            "source_quote": {"type": "string", "minLength": 1},
            "source_quote_start": {"type": "integer", "minimum": 0},
            "subject_quote": {"type": "string", "minLength": 1},
            "predicate_anchor_quote": {"type": "string", "minLength": 1},
            "object_quote": {"type": "string", "minLength": 1},
        },
    }


def _default_catalog_source_coordinates(
    *,
    proposal: ProviderSemanticProposal,
    arguments: dict[str, object],
) -> tuple[tuple[str, int | None], ...]:
    if not proposal.corrections:
        raise ValueError("default catalog correction source coordinates are absent")
    correction = arguments.get("correction")
    if type(correction) is not dict:
        raise ValueError("default catalog correction grounding is absent")
    result: list[tuple[str, int | None]] = []
    for role in ("corrected", "replacement"):
        grounding = correction.get(role)
        if (
            type(grounding) is not dict
            or set(grounding)
            - {
                "source_quote",
                "source_quote_start",
                "subject_quote",
                "predicate_anchor_quote",
                "object_quote",
            }
            or not {
                "source_quote",
                "subject_quote",
                "predicate_anchor_quote",
                "object_quote",
            }.issubset(grounding)
        ):
            raise ValueError("default catalog correction grounding is invalid")
        source_quote = grounding.get("source_quote")
        source_start = grounding.get("source_quote_start")
        if not isinstance(source_quote, str) or not source_quote:
            raise ValueError("default catalog correction source quote is invalid")
        if source_start is not None and (type(source_start) is not int or source_start < 0):
            raise ValueError("default catalog correction source quote offset is invalid")
        coordinate = (source_quote, source_start)
        if coordinate not in result:
            result.append(coordinate)
    return tuple(result)


def _validate_default_catalog_correction_grounding(
    *,
    proposal: ProviderSemanticProposal,
    arguments: dict[str, object],
    row: object,
) -> None:
    correction_body = arguments.get("correction")
    if type(correction_body) is not dict or set(correction_body) != {
        "assertion_quote",
        "correction_anchor_quote",
        "corrected",
        "replacement",
    }:
        raise ValueError("default catalog correction envelope is invalid")
    correction = proposal.corrections[0]
    if (
        correction.assertion_quote != correction_body["assertion_quote"]
        or correction.correction_anchor_quote != correction_body["correction_anchor_quote"]
    ):
        raise ValueError("default catalog correction evidence does not match")
    facts = (correction.corrected_fact, correction.replacement_fact)
    mentions = {mention.local_id: mention for mention in proposal.mentions}
    for fact, role in zip(facts, ("corrected", "replacement"), strict=True):
        grounding = correction_body[role]
        if type(grounding) is not dict:
            raise ValueError("default catalog correction grounding is invalid")
        _validate_default_catalog_fact_grounding(
            row=row,
            fact=fact,
            mentions=mentions,
            grounding=grounding,
        )
    sources = _default_catalog_source_coordinates(proposal=proposal, arguments=arguments)
    if not any(
        correction.assertion_quote in source and correction.correction_anchor_quote in source for source, _ in sources
    ):
        raise ValueError("default catalog correction anchor is not source grounded")


def _validate_default_catalog_fact_grounding(
    *,
    row: DefaultCatalogCorpusRow,
    fact: ProviderFact,
    mentions: dict[str, ProviderMention],
    grounding: dict[str, object],
) -> None:
    source_quote = grounding.get("source_quote")
    subject_quote = grounding.get("subject_quote")
    predicate_anchor_quote = grounding.get("predicate_anchor_quote")
    object_quote = grounding.get("object_quote")
    if not all(
        isinstance(value, str) and value
        for value in (
            source_quote,
            subject_quote,
            predicate_anchor_quote,
            object_quote,
        )
    ):
        raise ValueError("default catalog correction grounding is invalid")
    if fact.assertion_quote != source_quote or fact.predicate_anchor_quote != predicate_anchor_quote:
        raise ValueError("default catalog correction fact evidence does not match")
    subject = mentions[fact.subject_entity_ref]
    if subject.mention_quote != subject_quote or subject.mention_context_quote != source_quote:
        raise ValueError("default catalog correction subject grounding is invalid")
    if isinstance(fact.object, ProviderEntityObject):
        object_mention = mentions[fact.object.entity_ref]
        if object_mention.mention_quote != object_quote or object_mention.mention_context_quote != source_quote:
            raise ValueError("default catalog correction object grounding is invalid")
    else:
        validate_default_catalog_literal_grounding(
            row=row,
            value=fact.object,
            object_quote=object_quote,
        )
    for quote in (subject_quote, predicate_anchor_quote, object_quote, *fact.temporal_qualifier_quotes):
        if source_quote.count(quote) != 1:
            raise ValueError("default catalog correction quote is absent or ambiguous")


def _default_catalog_lifecycle_anchors(proposal: ProviderSemanticProposal) -> tuple[str, ...]:
    facts = _default_catalog_lifecycle_facts(proposal)
    operation_anchors: tuple[str, ...]
    if proposal.corrections:
        operation_anchors = (proposal.corrections[0].correction_anchor_quote,)
    elif proposal.retractions:
        operation_anchors = (proposal.retractions[0].retraction_anchor_quote,)
    else:
        operation_anchors = ()
    return (*operation_anchors, *(quote for fact in facts for quote in fact.temporal_qualifier_quotes))


def _validate_default_catalog_argument_shape(proposal: dict[str, object]) -> None:
    """Validate JSON shape before typed decoding of default lifecycle operations."""
    required = {
        "abstained",
        "mentions",
        "facts",
        "corrections",
        "retractions",
        "action_states",
        "identity_operations",
    }
    if set(proposal) != required or proposal.get("abstained") is not False:
        raise ValueError("default catalog proposal is not closed")
    if (
        type(proposal["mentions"]) is not list
        or not 1 <= len(proposal["mentions"]) <= 4
        or type(proposal["facts"]) is not list
        or type(proposal["corrections"]) is not list
        or type(proposal["retractions"]) is not list
        or proposal["action_states"] != []
        or proposal["identity_operations"] != []
    ):
        raise ValueError("default catalog lifecycle cardinality is invalid")
    facts = proposal["facts"]
    corrections = proposal["corrections"]
    retractions = proposal["retractions"]
    if len(corrections) + len(retractions) > 1 or (facts and (corrections or retractions)):
        raise ValueError("default catalog lifecycle operation shape is invalid")
    if not facts and not corrections and not retractions:
        raise ValueError("default catalog lifecycle operation is absent")
    if len(facts) > 1 or len(corrections) > 1 or len(retractions) > 1:
        raise ValueError("default catalog lifecycle cardinality is invalid")
    for mention in proposal["mentions"]:
        if type(mention) is not dict or set(mention) != {
            "local_id",
            "mention_quote",
            "mention_context_quote",
            "proposed_type",
        }:
            raise ValueError("default catalog mention grammar is invalid")
    if corrections:
        correction = corrections[0]
        if (
            type(correction) is not dict
            or set(correction)
            != {
                "kind",
                "local_id",
                "corrected_fact",
                "replacement_fact",
                "assertion_quote",
                "correction_anchor_quote",
            }
            or correction.get("kind") != "correction"
        ):
            raise ValueError("default catalog correction grammar is invalid")
        nested_facts: list[object] = [
            correction["corrected_fact"],
            correction["replacement_fact"],
        ]
    elif retractions:
        retraction = retractions[0]
        if (
            type(retraction) is not dict
            or set(retraction)
            != {
                "kind",
                "local_id",
                "retracted_fact",
                "assertion_quote",
                "retraction_anchor_quote",
            }
            or retraction.get("kind") != "retraction"
        ):
            raise ValueError("default catalog retraction grammar is invalid")
        nested_facts = [retraction["retracted_fact"]]
    else:
        nested_facts = []
    for fact in [*facts, *nested_facts]:
        _validate_default_catalog_fact_shape(fact)


def _validate_default_catalog_fact_shape(fact: object) -> None:
    fields = {
        "kind",
        "local_id",
        "predicate_id",
        "subject_entity_ref",
        "object",
        "assertion_quote",
        "predicate_anchor_quote",
        "polarity",
        "commitment",
        "attributed_to_entity_ref",
        "temporal_qualifier_quotes",
    }
    if type(fact) is not dict or set(fact) != fields or fact.get("kind") != "fact":
        raise ValueError("default catalog fact grammar is invalid")
    object_value = fact["object"]
    if type(object_value) is not dict or object_value.get("kind") not in {"entity", "literal"}:
        raise ValueError("default catalog object grammar is invalid")
    expected = (
        {"kind", "entity_ref"}
        if object_value["kind"] == "entity"
        else {
            "kind",
            "literal_type",
            "canonical_value",
            "unit",
        }
    )
    if set(object_value) != expected:
        raise ValueError("default catalog object grammar is invalid")


def _canonicalize_message(value: object) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError("Hermes transcript message is not a closed object")
    role = value.get("role")
    if role not in {"system", "developer", "user", "assistant", "tool"}:
        raise ValueError("Hermes transcript role is unsupported")
    persistence_fields = {"timestamp", "_db_persisted", "_row_id"}
    allowed_fields = {
        "system": {"role", "content", *persistence_fields},
        "developer": {"role", "content", *persistence_fields},
        "user": {
            "role",
            "content",
            *persistence_fields,
            "display_kind",
            "display_metadata",
            "platform_message_id",
            "api_content",
        },
        "assistant": {
            "role",
            "content",
            *persistence_fields,
            "reasoning",
            "finish_reason",
            "reasoning_content",
            "reasoning_details",
            "anthropic_content_blocks",
            "bedrock_content_blocks",
            "codex_reasoning_items",
            "codex_message_items",
            "api_content",
            "tool_calls",
        },
        "tool": {
            "role",
            "content",
            *persistence_fields,
            "tool_call_id",
            "name",
            "tool_name",
            "_tool_output_risk",
            "effect_disposition",
        },
    }
    unexpected_fields = set(value) - allowed_fields[role]
    if unexpected_fields:
        fields = ", ".join(sorted(unexpected_fields))
        raise ValueError(f"Hermes transcript {role} message has unsupported fields: {fields}")
    if role in {"system", "developer", "user"}:
        content = _canonical_text(value.get("content"))
        return _with_canonical_timestamp({"role": role, "content": content}, value)
    if role == "tool":
        content = _canonical_text(value.get("content"))
        if "tool_call_id" not in value:
            raise ValueError("Hermes tool message has invalid fields")
        call_id = _canonical_text(value.get("tool_call_id"))
        return _with_canonical_timestamp({"role": role, "content": content, "tool_call_id": call_id}, value)
    content_value = value.get("content")
    textless_tool_call = content_value == "" and "tool_calls" in value
    content = "" if textless_tool_call else _canonical_text(content_value)
    result: dict[str, object] = {"role": role, "content": content}
    if "tool_calls" in value:
        calls = value["tool_calls"]
        if type(calls) is not list or not calls:
            raise ValueError("Hermes assistant tool calls are invalid")
        result["tool_calls"] = tuple(_canonicalize_tool_call(call) for call in calls)
    return _with_canonical_timestamp(result, value)


def _with_canonical_timestamp(result: dict[str, object], raw: dict[str, object]) -> dict[str, object]:
    """Retain only a validated, canonical persisted Hermes message timestamp."""
    if "timestamp" in raw:
        result["timestamp"] = _canonical_timestamp(raw["timestamp"])
    return result


def _completed_turn_timestamp(canonical_messages: tuple[dict[str, object], ...]) -> datetime:
    """Return the immutable timestamp bound to the final persisted completion."""
    final_timestamp = canonical_messages[-1].get("timestamp")
    if not isinstance(final_timestamp, str):
        raise ValueError("Hermes completed-turn transcript is missing its final timestamp")
    return _parse_canonical_timestamp(final_timestamp)


def _canonical_timestamp(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Hermes transcript timestamp is invalid")
    return _parse_canonical_timestamp(value).isoformat().replace("+00:00", "Z")


def _parse_canonical_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Hermes transcript timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Hermes transcript timestamp is invalid")
    return parsed.astimezone(UTC)


def _canonicalize_tool_call(value: object) -> dict[str, str]:
    if (
        type(value) is not dict
        or set(value) - {"id", "call_id", "response_item_id", "type", "function", "extra_content"}
        or value.get("type") != "function"
        or "id" not in value
        or "function" not in value
    ):
        raise ValueError("Hermes assistant tool call is invalid")
    function = value["function"]
    if type(function) is not dict or set(function) != {"name", "arguments"}:
        raise ValueError("Hermes assistant tool function is invalid")
    arguments = _canonical_text(function["arguments"])
    try:
        parsed = json.loads(
            arguments,
            object_pairs_hook=_reject_duplicate_json_object_keys,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
        canonical_arguments = json.dumps(
            parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Hermes tool arguments are not valid JSON") from exc
    return {
        "id": _canonical_text(value["id"]),
        "type": "function",
        "name": _canonical_text(function["name"]),
        "arguments": canonical_arguments,
    }


def _reject_duplicate_json_object_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Hermes tool arguments contain duplicate object keys")
        result[key] = value
    return result


def _canonical_text(value: object) -> str:
    if not isinstance(value, str) or not value or unicodedata.normalize("NFC", value) != value:
        raise ValueError("Hermes transcript strings must be nonblank NFC text")
    return value


def _canonical_messages_digest(messages: tuple[dict[str, object], ...]) -> str:
    payload = json.dumps(messages, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )
    return sha256(b"memorii.hermes.completed-turn.transcript.v1\0" + payload).hexdigest()


def _required_string(arguments: dict[str, object], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"preference {name} is invalid")
    return value


def _required_digest(arguments: dict[str, object], name: str) -> str:
    value = _required_string(arguments, name)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"preference {name} is invalid")
    return value


def _preference_result(status: str, preference: object) -> dict[str, object]:
    if preference is None:
        return {"status": "denied"}
    preference_id = getattr(preference, "preference_id", None)
    if not isinstance(preference_id, str):
        raise ValueError("preference service returned an invalid result")
    return {"status": status, "preference_id": preference_id}


def _preference_tool_schemas() -> list[dict[str, object]]:
    candidate_required = [
        "topic_type",
        "topic_quote",
        "canonical_topic_id",
        "preference_key",
        "value",
        "source_quote",
        "source_quote_start",
    ]
    approval_required = ["preference_id", "preference_key", "value", "source_digest"]
    string = {"type": "string", "minLength": 1}
    return [
        {
            "type": "function",
            "function": {
                "name": "memorii_create_preference_candidate",
                "description": "Create one quote-grounded user Preference candidate from the active turn.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": candidate_required,
                    "properties": {
                        "topic_type": {"enum": ["ProductService", "Asset", "Place"]},
                        "topic_quote": string,
                        "canonical_topic_id": string,
                        "preference_key": string,
                        "value": string,
                        "source_quote": string,
                        "source_quote_start": {"type": "integer", "minimum": 0},
                        "valid_until": {"type": ["string", "null"], "format": "date-time"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "memorii_confirm_preference",
                "description": "Confirm an exact Preference candidate with an approval quote from the active turn.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [*approval_required, "approval_quote", "approval_quote_start"],
                    "properties": {
                        **{name: string for name in approval_required},
                        "approval_quote": string,
                        "approval_quote_start": {"type": "integer", "minimum": 0},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "memorii_close_preference",
                "description": "Close an exact Preference candidate with an explicit revocation quote from the active turn.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [*approval_required, "state", "revocation_quote", "revocation_quote_start"],
                    "properties": {
                        **{name: string for name in approval_required},
                        "state": {"enum": ["expired", "retracted", "rejected"]},
                        "revocation_quote": string,
                        "revocation_quote_start": {"type": "integer", "minimum": 0},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "memorii_set_preference_delegation",
                "description": "Grant or revoke one agent's access to the signed-in user's Preferences.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["delegated_agent_id", "state", "approval_quote", "approval_quote_start"],
                    "properties": {
                        "delegated_agent_id": string,
                        "state": {"enum": ["active", "revoked"]},
                        "approval_quote": string,
                        "approval_quote_start": {"type": "integer", "minimum": 0},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "memorii_read_preference",
                "description": "Read current or historical protected Preferences for the signed-in user.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["view"],
                    "properties": {
                        "view": {"enum": ["current", "history"]},
                        "canonical_topic_id": string,
                        "preference_key": string,
                    },
                },
            },
        },
    ]


__all__ = ["HermesCompletedTurnRuntime"]
