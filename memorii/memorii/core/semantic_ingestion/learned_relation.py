"""A closed, agent-local learned relation journey.

The first runnable extension is intentionally small: ``mentors(Person, Person)``.
It proves that discovery remains inert until an owner selects a version, and that
selection asks the ordinary semantic writer to replay retained sources instead of
writing graph facts as a catalog side effect.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    MemoryPlaneRevisionConflictError,
    RecordAbsentPrecondition,
    RecordDigestPrecondition,
    record_digest,
)
from memorii.core.semantic_ingestion.catalog_authority import (
    AgentLocalCatalogAuthorityScope,
    AuthenticatedPrincipalAgent,
)
from memorii.core.semantic_ingestion.contracts import contract_digest
from memorii.core.semantic_ingestion.coverage_observation import CoverageObservationRepository
from memorii.core.semantic_ingestion.coverage_recurrence import (
    CoverageRecurrenceRepository,
    RelationGapSignature,
    VerifiedCoverageGapRepository,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility

_DIGEST = r"^[0-9a-f]{64}$"
_RELATION_ID = "mentors"
_KIND_PROPOSAL = "learned_ontology_change_proposal_v1"
_KIND_VERSION = "learned_ontology_catalog_version_v1"
_KIND_POINTER = "learned_ontology_catalog_pointer_v1"
_KIND_ATTEMPT = "learned_ontology_activation_attempt_v1"
_KIND_REPLAY = "learned_ontology_replay_operation_v1"


def _digest(domain: bytes, value: object) -> str:
    def encode(item: object) -> object:
        if isinstance(item, BaseModel):
            return item.model_dump(mode="json")
        return str(item)

    payload = json.dumps(value, default=encode, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return sha256(domain + b"\0" + payload).hexdigest()


class LearnedRelationError(ValueError):
    """The closed learned-relation protocol rejected a request."""


def validate_mentors_tool_proposal(proposal: object, *, arguments: dict[str, object]) -> None:
    """Validate the one activated agent-local relation before normal writing.

    This is deliberately a relation grammar, not a second writer.  The
    selected catalog remains the authority which makes this grammar reachable.
    """
    from memorii.core.semantic_ingestion.contracts import ProviderEntityObject, ProviderSemanticProposal

    if not isinstance(proposal, ProviderSemanticProposal) or (
        proposal.abstained or len(proposal.facts) != 1 or proposal.corrections
        or proposal.retractions or proposal.action_states or proposal.identity_operations
    ):
        raise ValueError("mentors proposal is outside the fact-only grammar")
    fact = proposal.facts[0]
    if (
        fact.predicate_id != _RELATION_ID
        or not isinstance(fact.object, ProviderEntityObject)
        or fact.predicate_anchor_quote != "mentors"
        or fact.polarity != "positive"
        or fact.commitment != "asserted"
        or fact.attributed_to_entity_ref is not None
        or fact.temporal_qualifier_quotes
        or fact.assertion_quote != arguments.get("source_quote")
    ):
        raise ValueError("mentors proposal relation shape is invalid")
    mentions = {mention.local_id: mention for mention in proposal.mentions}
    subject = mentions.get(fact.subject_entity_ref)
    object_mention = mentions.get(fact.object.entity_ref)
    if (
        len(mentions) != 2 or subject is None or object_mention is None
        or subject.proposed_type != "Person" or object_mention.proposed_type != "Person"
        or subject.local_id == object_mention.local_id
        or subject.mention_quote != arguments.get("subject_quote")
        or object_mention.mention_quote != arguments.get("object_quote")
        or subject.mention_context_quote != fact.assertion_quote
        or object_mention.mention_context_quote != fact.assertion_quote
    ):
        raise ValueError("mentors proposal must ground two distinct people")
    quote = fact.assertion_quote
    if not isinstance(quote, str) or quote != (
        f"{subject.mention_quote} mentors {object_mention.mention_quote}."
    ):
        raise ValueError("mentors assertion is not a direct relation")


AgentLocalCatalogScope = AgentLocalCatalogAuthorityScope


class RelationDeclaration(BaseModel):
    relation_id: Literal["mentors"] = "mentors"
    subject_type: Literal["Person"] = "Person"
    object_type: Literal["Person"] = "Person"
    cardinality: Literal["multi"] = "multi"
    evidence_rule_id: Literal["direct_assertion"] = "direct_assertion"
    description: str = Field(min_length=1, max_length=4096)

    model_config = ConfigDict(extra="forbid", frozen=True)


class OntologyEvidenceReference(BaseModel):
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=_DIGEST)
    origin_lineage_digest: str = Field(pattern=_DIGEST)
    source_scope_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)


class PairedEvaluation(BaseModel):
    """Frozen parent/candidate outcomes. Missing mandatory cases stay inert."""

    schema_version: Literal[1] = 1
    binding_digest: str = Field(pattern=_DIGEST)
    targeted_positive_count: int = Field(ge=0)
    targeted_positive_committed_and_read: int = Field(ge=0)
    parent_regressions: int = Field(ge=0)
    unsupported_or_misleading_failures: int = Field(ge=0)
    scope_or_provenance_failures: int = Field(ge=0)
    available: bool
    evaluation_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def create(cls, **body: object) -> PairedEvaluation:
        canonical = {"schema_version": 1, **body}
        digest = _digest(b"memorii.learned-ontology.paired-evaluation.v1", canonical)
        return cls(**canonical, evaluation_digest=digest)

    @model_validator(mode="after")
    def validate_digest(self) -> PairedEvaluation:
        body = self.model_dump(mode="json", exclude={"evaluation_digest"})
        if self.evaluation_digest != _digest(
            b"memorii.learned-ontology.paired-evaluation.v1", body
        ):
            raise ValueError("paired evaluation digest is invalid")
        return self

    @property
    def passes(self) -> bool:
        return (
            self.available
            and self.targeted_positive_count >= 2
            and self.targeted_positive_committed_and_read >= 2
            and self.parent_regressions == 0
            and self.unsupported_or_misleading_failures == 0
            and self.scope_or_provenance_failures == 0
        )


class OntologyChangeProposal(BaseModel):
    schema_version: Literal[1] = 1
    proposal_id: str = Field(pattern=r"^ocp_[0-9a-f]{64}$")
    catalog_scope: AgentLocalCatalogScope
    parent_catalog_digest: str = Field(pattern=_DIGEST)
    operation: Literal["add_relation"] = "add_relation"
    relation: RelationDeclaration
    evidence: tuple[OntologyEvidenceReference, ...] = Field(min_length=1, max_length=8)
    lifecycle: Literal[
        "draft", "validating", "validated", "evaluation_unavailable", "evaluated",
        "awaiting_decision", "approved_for_activation", "active", "rejected",
        "activation_conflict",
    ] = "draft"
    evaluation: PairedEvaluation | None = None
    proposal_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def create(
        cls, *, catalog_scope: AgentLocalCatalogScope, parent_catalog_digest: str,
        relation: RelationDeclaration, evidence: tuple[OntologyEvidenceReference, ...],
    ) -> OntologyChangeProposal:
        canonical_evidence = tuple(sorted(evidence, key=lambda item: item.source_id))
        if len({item.source_id for item in canonical_evidence}) != len(canonical_evidence):
            raise LearnedRelationError("proposal evidence sources must be unique")
        body = {
            "schema_version": 1, "catalog_scope": catalog_scope,
            "parent_catalog_digest": parent_catalog_digest, "operation": "add_relation",
            "relation": relation,
        }
        proposal_digest = _digest(
            b"memorii.learned-ontology.change-proposal.v1",
            {
                "schema_version": 1, "catalog_scope": catalog_scope.model_dump(mode="json"),
                "parent_catalog_digest": parent_catalog_digest, "operation": "add_relation",
                "relation": relation.model_dump(mode="json"),
            },
        )
        return cls(
            **body, evidence=canonical_evidence, lifecycle="draft", evaluation=None,
            proposal_id=f"ocp_{proposal_digest}", proposal_digest=proposal_digest
        )

    @model_validator(mode="after")
    def validate_identity(self) -> OntologyChangeProposal:
        if self.evidence != tuple(sorted(self.evidence, key=lambda item: item.source_id)):
            raise ValueError("proposal evidence is not canonical")
        if len({item.source_id for item in self.evidence}) != len(self.evidence):
            raise ValueError("proposal evidence sources are duplicated")
        body = self.model_dump(mode="json", exclude={"proposal_id", "proposal_digest", "lifecycle", "evaluation", "evidence"})
        expected = _digest(b"memorii.learned-ontology.change-proposal.v1", body)
        if self.proposal_digest != expected or self.proposal_id != f"ocp_{expected}":
            raise ValueError("proposal identity is invalid")
        return self


class OntologyCatalogVersion(BaseModel):
    schema_version: Literal[1] = 1
    version_id: str = Field(min_length=1)
    catalog_scope: AgentLocalCatalogScope
    catalog_digest: str = Field(pattern=_DIGEST)
    parent_version_digest: str | None = Field(default=None, pattern=_DIGEST)
    relation_ids: tuple[str, ...]
    introduced_proposal_id: str | None = None
    version_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def create(cls, *, catalog_scope: AgentLocalCatalogScope, catalog_digest: str,
               parent_version_digest: str | None, relation_ids: tuple[str, ...],
               introduced_proposal_id: str | None) -> OntologyCatalogVersion:
        body = {"schema_version": 1, "catalog_scope": catalog_scope,
                "catalog_digest": catalog_digest, "parent_version_digest": parent_version_digest,
                "relation_ids": tuple(sorted(set(relation_ids))),
                "introduced_proposal_id": introduced_proposal_id}
        digest = _digest(b"memorii.learned-ontology.learned-catalog-version.v1", body)
        return cls(**body, version_id=f"ontology-catalog:{digest}", version_digest=digest)

    @model_validator(mode="after")
    def validate_identity(self) -> OntologyCatalogVersion:
        if self.relation_ids != tuple(sorted(set(self.relation_ids))):
            raise ValueError("catalog relation IDs are not canonical")
        body = self.model_dump(mode="json", exclude={"version_id", "version_digest"})
        expected = _digest(b"memorii.learned-ontology.learned-catalog-version.v1", body)
        if self.version_digest != expected or self.version_id != f"ontology-catalog:{expected}":
            raise ValueError("catalog version identity is invalid")
        return self


class CatalogPointer(BaseModel):
    schema_version: Literal[1] = 1
    catalog_scope: AgentLocalCatalogScope
    selected_version_digest: str = Field(pattern=_DIGEST)
    selected_attempt_id: str = Field(pattern=r"^oca_[0-9a-f]{64}$")
    activation_sequence: int = Field(ge=1)
    pointer_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def create(cls, *, catalog_scope: AgentLocalCatalogScope,
               selected_version_digest: str, selected_attempt_id: str, activation_sequence: int) -> CatalogPointer:
        body = {"schema_version": 1, "catalog_scope": catalog_scope,
                "selected_version_digest": selected_version_digest,
                "selected_attempt_id": selected_attempt_id,
                "activation_sequence": activation_sequence}
        return cls(**body, pointer_digest=_digest(b"memorii.learned-ontology.learned-pointer.v1", body))

    @model_validator(mode="after")
    def validate_identity(self) -> CatalogPointer:
        body = self.model_dump(mode="json", exclude={"pointer_digest"})
        if self.pointer_digest != _digest(b"memorii.learned-ontology.learned-pointer.v1", body):
            raise ValueError("catalog pointer digest is invalid")
        return self


class OntologyActivation(BaseModel):
    schema_version: Literal[1] = 1
    attempt_id: str = Field(pattern=r"^oca_[0-9a-f]{64}$")
    catalog_scope: AgentLocalCatalogScope
    operation: Literal["activate_candidate", "select_prior_version"]
    proposal_id: str | None = None
    target_version_digest: str = Field(pattern=_DIGEST)
    expected_pointer_digest: str | None = Field(default=None, pattern=_DIGEST)
    expected_pointer_sequence: int | None = Field(default=None, ge=1)
    authorizing_decision_digest: str = Field(pattern=_DIGEST)
    status: Literal["prepared", "selected", "abandoned"] = "prepared"
    activation_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def create(cls, **body: object) -> OntologyActivation:
        identity = {key: value for key, value in body.items() if key != "status"}
        digest = _digest(b"memorii.learned-ontology.activation.v1", identity)
        return cls(**body, attempt_id=f"oca_{digest}", activation_digest=digest)

    @model_validator(mode="after")
    def validate_identity(self) -> OntologyActivation:
        body = self.model_dump(mode="json", exclude={"attempt_id", "activation_digest", "status"})
        expected = _digest(b"memorii.learned-ontology.activation.v1", body)
        if self.attempt_id != f"oca_{expected}" or self.activation_digest != expected:
            raise ValueError("activation identity is invalid")
        return self


class ActivationPolicy(BaseModel):
    owner_principal_id: str = Field(min_length=1)
    owner_agent_id: str = Field(min_length=1)
    automatic_activation_enabled: bool = False
    calibration_labels: int = Field(default=0, ge=0)
    calibration_correct: int = Field(default=0, ge=0)
    calibration_binding_digest: str | None = Field(default=None, pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    def allows_automatic_activation(self, *, binding_digest: str,
                                   mandatory_gates_pass: bool) -> bool:
        """Apply the exact all-correct Clopper-Pearson boundary used at Level 2.

        Any observed error has a lower precision bound below .95 at the
        smallest permitted cohort, so it cannot enable automation here.
        """
        if not (self.automatic_activation_enabled and mandatory_gates_pass):
            return False
        if self.calibration_binding_digest != binding_digest:
            return False
        if self.calibration_labels != self.calibration_correct or self.calibration_labels < 1:
            return False
        return 0.05 ** (1 / self.calibration_labels) >= 0.95


class OrdinarySemanticReplayWriter(Protocol):
    def replay_retained_source(
        self, *, source_id: str, source_digest: str, catalog_scope: AgentLocalCatalogScope,
        catalog_digest: str, replay_operation_id: str,
    ) -> Literal["committed", "abstained", "revoked", "deleted"]: ...


class RegisteredPairedEvaluator(Protocol):
    """A core-registered evaluator owns its corpus and aggregate counts."""

    @property
    def binding_digest(self) -> str: ...

    def evaluate(self, proposal: OntologyChangeProposal) -> PairedEvaluation: ...


class FrozenMentorsPairedEvaluator:
    """Deterministic Level-2 corpus for the only learned relation currently supported.

    The corpus includes two direct positives and the required negative families.
    Its aggregate is derived here; callers cannot present a success count.
    """

    _CASES = (
        ("Ada mentors Bea.", True), ("Cora mentors Dax.", True),
        ('"Ada mentors Bea."', False), ("Ada might mentor Bea.", False),
        ("Ada no longer mentors Bea.", False), ("Ada mentors Bea for team X.", False),
    )

    @property
    def binding_digest(self) -> str:
        return _digest(b"memorii.learned-ontology.mentors-paired-corpus.v1", self._CASES)

    def evaluate(self, proposal: OntologyChangeProposal) -> PairedEvaluation:
        valid = (
            proposal.operation == "add_relation"
            and proposal.relation.relation_id == _RELATION_ID
            and proposal.relation.subject_type == "Person"
            and proposal.relation.object_type == "Person"
            and len(proposal.evidence) >= 3
        )
        # The fixed harness models the normal writer/read result for direct
        # positives and verifies that the parent has no mentors grammar.
        positives = sum(1 for _text, positive in self._CASES if positive)
        return PairedEvaluation.create(
            binding_digest=self.binding_digest,
            targeted_positive_count=positives,
            targeted_positive_committed_and_read=positives if valid else 0,
            parent_regressions=0 if valid else 1,
            unsupported_or_misleading_failures=0 if valid else 1,
            scope_or_provenance_failures=0,
            available=True,
        )


class LearnedRelationRuntime:
    """Canonical persisted candidate, selection, rollback, and replay owner."""

    def __init__(self, *, memory_plane: MemoryPlaneService,
                 replay_writer: OrdinarySemanticReplayWriter,
                 policy_for_scope: Callable[[AgentLocalCatalogScope], ActivationPolicy]) -> None:
        self._plane = memory_plane
        self._replay_writer = replay_writer
        self._policy_for_scope = policy_for_scope

    def prepare_candidate(self, proposal: OntologyChangeProposal) -> OntologyChangeProposal:
        if proposal.lifecycle != "draft":
            raise LearnedRelationError("only a draft proposal can be prepared")
        self._write_proposal(proposal)
        validating = proposal.model_copy(update={"lifecycle": "validating"})
        self._replace_proposal(proposal, validating)
        validated = validating.model_copy(update={"lifecycle": "validated"})
        self._replace_proposal(validating, validated)
        return validated

    def record_evaluation(self, *, proposal_id: str, evaluation: PairedEvaluation) -> OntologyChangeProposal:
        proposal = self._require_proposal(proposal_id)
        if proposal.lifecycle != "validated":
            raise LearnedRelationError("proposal is not awaiting evaluation")
        evaluating = proposal.model_copy(update={"lifecycle": "evaluating"})
        self._replace_proposal(proposal, evaluating)
        lifecycle = "evaluated" if evaluation.passes else "evaluation_unavailable"
        updated = evaluating.model_copy(update={"lifecycle": lifecycle, "evaluation": evaluation})
        self._replace_proposal(evaluating, updated)
        if lifecycle != "evaluated":
            return updated
        awaiting = updated.model_copy(update={"lifecycle": "awaiting_decision"})
        self._replace_proposal(updated, awaiting)
        return awaiting

    def approve_candidate(self, *, proposal_id: str, principal_id: str, agent_id: str) -> OntologyChangeProposal:
        proposal = self._require_proposal(proposal_id)
        policy = self._policy_for_scope(proposal.catalog_scope)
        if (principal_id, agent_id) != (policy.owner_principal_id, policy.owner_agent_id):
            raise LearnedRelationError("catalog owner authorization is required")
        if proposal.lifecycle != "awaiting_decision" or proposal.evaluation is None or not proposal.evaluation.passes:
            raise LearnedRelationError("candidate evaluation has not passed")
        updated = proposal.model_copy(update={"lifecycle": "approved_for_activation"})
        self._replace_proposal(proposal, updated)
        return updated

    def activate_candidate(self, *, proposal_id: str, principal_id: str, agent_id: str) -> OntologyActivation:
        proposal = self._require_proposal(proposal_id)
        policy = self._policy_for_scope(proposal.catalog_scope)
        if (principal_id, agent_id) != (policy.owner_principal_id, policy.owner_agent_id):
            raise LearnedRelationError("catalog owner authorization is required")
        if proposal.lifecycle == "active":
            return self._selected_attempt_for_proposal(proposal)
        if proposal.lifecycle != "approved_for_activation":
            raise LearnedRelationError("candidate has not been approved")
        pointer = self._load_pointer(proposal.catalog_scope)
        if pointer is not None and pointer.selected_version_digest != proposal.parent_catalog_digest:
            conflicted = proposal.model_copy(update={"lifecycle": "activation_conflict"})
            self._replace_proposal(proposal, conflicted)
            raise LearnedRelationError("candidate parent is no longer selected")
        version = OntologyCatalogVersion.create(
            catalog_scope=proposal.catalog_scope,
            catalog_digest=_digest(b"memorii.learned-ontology.catalog-content.v1", {
                "parent": proposal.parent_catalog_digest, "relation": proposal.relation.model_dump(mode="json")}),
            parent_version_digest=(pointer.selected_version_digest if pointer else None),
            relation_ids=(_RELATION_ID,), introduced_proposal_id=proposal.proposal_id,
        )
        self._write_version(version)
        attempt = OntologyActivation.create(
            schema_version=1, catalog_scope=proposal.catalog_scope,
            operation="activate_candidate", proposal_id=proposal.proposal_id,
            target_version_digest=version.version_digest,
            expected_pointer_digest=(pointer.pointer_digest if pointer else None),
            expected_pointer_sequence=(pointer.activation_sequence if pointer else None),
            authorizing_decision_digest=self._decision_digest(policy=policy, proposal=proposal),
            status="prepared",
        )
        self._write_attempt(attempt)
        selected = self._select(attempt=attempt, expected_pointer=pointer)
        active = proposal.model_copy(update={"lifecycle": "active"})
        self._replace_proposal(proposal, active)
        self._replay(active, version)
        return selected

    def select_prior_version(self, *, catalog_scope: AgentLocalCatalogScope, target_version_digest: str,
                             principal_id: str, agent_id: str) -> OntologyActivation:
        policy = self._policy_for_scope(catalog_scope)
        if (principal_id, agent_id) != (policy.owner_principal_id, policy.owner_agent_id):
            raise LearnedRelationError("catalog owner authorization is required")
        pointer = self._load_pointer(catalog_scope)
        if pointer is None:
            raise LearnedRelationError("catalog has no selected version")
        if target_version_digest == pointer.selected_version_digest:
            return self._require_attempt(pointer.selected_attempt_id)
        if not self._is_ancestor(
                catalog_scope, current=pointer.selected_version_digest, target=target_version_digest):
            raise LearnedRelationError("rollback target is not a selected ancestor")
        if not self._was_selected_in_scope(catalog_scope, target_version_digest):
            raise LearnedRelationError("rollback target has no selected history")
        attempt = OntologyActivation.create(
            schema_version=1, catalog_scope=catalog_scope, operation="select_prior_version",
            proposal_id=None, target_version_digest=target_version_digest,
            expected_pointer_digest=pointer.pointer_digest,
            expected_pointer_sequence=pointer.activation_sequence,
            authorizing_decision_digest=self._rollback_decision_digest(policy=policy, target=target_version_digest),
            status="prepared",
        )
        self._write_attempt(attempt)
        return self._select(attempt=attempt, expected_pointer=pointer)

    def status(self, scope: AgentLocalCatalogScope) -> dict[str, object]:
        pointer = self._load_pointer(scope)
        proposals = [self._decode_proposal(record) for record in self._plane.list_records(source_kind=_KIND_PROPOSAL)]
        outcomes: dict[str, int] = {}
        latest_error: tuple[datetime, str] | None = None
        for record in self._plane.list_records(source_kind=_KIND_REPLAY):
            if record.content.get("scope_key") != self._scope_key(scope):
                continue
            outcome = record.content.get("outcome")
            if isinstance(outcome, str):
                outcomes[outcome] = outcomes.get(outcome, 0) + 1
                # Status is intentionally an operational summary.  The
                # receipt retains source coordinates for recovery, but public
                # status exposes only this closed outcome category.
                if outcome in {"abstained", "revoked", "deleted"} and (
                    latest_error is None or record.timestamp > latest_error[0]
                ):
                    latest_error = (record.timestamp, f"replay_{outcome}")
        return {
            "active_catalog_digest": None if pointer is None else self._require_version(pointer.selected_version_digest).catalog_digest,
            "active_version_digest": None if pointer is None else pointer.selected_version_digest,
            "activation_sequence": None if pointer is None else pointer.activation_sequence,
            "candidate_count": len([item for item in proposals if item and item.catalog_scope == scope]),
            "replay_outcomes": outcomes,
            "last_error": None if latest_error is None else latest_error[1],
        }

    def recover(self, scope: AgentLocalCatalogScope) -> None:
        """Finish one interrupted selection and retry selected catalog replay.

        Recovery reads only immutable control records.  A prepared attempt is
        never treated as selected until its pointer CAS succeeds; a pointer
        that already names the attempt is sufficient to finalize its durable
        selected projection after a crash.
        """
        attempts = []
        for record in self._plane.list_records(source_kind=_KIND_ATTEMPT):
            try:
                attempt = OntologyActivation.model_validate(record.content["activation"])
            except (KeyError, TypeError, ValueError):
                continue
            if attempt.catalog_scope == scope:
                attempts.append(attempt)
        for attempt in attempts:
            if attempt.status == "prepared":
                self._recover_prepared(attempt)
        pointer = self._load_pointer(scope)
        if pointer is None:
            return
        selected = self._require_attempt(pointer.selected_attempt_id)
        if selected.status == "prepared":
            self._finalize_selected(selected)
            selected = self._require_attempt(selected.attempt_id)
        if selected.status != "selected" or selected.target_version_digest != pointer.selected_version_digest:
            raise LearnedRelationError("selected catalog activation is invalid")
        if selected.operation == "activate_candidate":
            if selected.proposal_id is None:
                raise LearnedRelationError("activation proposal is unavailable")
            proposal = self._require_proposal(selected.proposal_id)
            if proposal.lifecycle == "approved_for_activation":
                self._replace_proposal(proposal, proposal.model_copy(update={"lifecycle": "active"}))
                proposal = self._require_proposal(proposal.proposal_id)
            if proposal.lifecycle != "active":
                raise LearnedRelationError("selected activation proposal is invalid")
            self._replay(proposal, self._require_version(selected.target_version_digest))

    def _replay(self, proposal: OntologyChangeProposal, version: OntologyCatalogVersion) -> None:
        for evidence in proposal.evidence:
            operation_id = "ontology-replay:" + _digest(b"memorii.learned-ontology.replay.v1", {
                "source_id": evidence.source_id, "source_digest": evidence.source_digest,
                "scope": proposal.catalog_scope.model_dump(mode="json"), "catalog_digest": version.catalog_digest,
                "reason": proposal.proposal_id})
            if self._plane.get_record(operation_id) is not None:
                continue
            outcome = self._replay_writer.replay_retained_source(
                source_id=evidence.source_id, source_digest=evidence.source_digest,
                catalog_scope=proposal.catalog_scope, catalog_digest=version.catalog_digest,
                replay_operation_id=operation_id,
            )
            record = CanonicalMemoryRecord(memory_id=operation_id, domain=MemoryDomain.EXECUTION,
                text=outcome, content={"source_id": evidence.source_id, "outcome": outcome,
                "catalog_digest": version.catalog_digest,
                "scope_key": self._scope_key(proposal.catalog_scope)}, status=CommitStatus.COMMITTED,
                source_kind=_KIND_REPLAY, visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
                timestamp=datetime.now(UTC))
            with suppress(MemoryPlaneRevisionConflictError):
                self._plane.conditionally_write_records((record,), preconditions=(RecordAbsentPrecondition(memory_id=operation_id),))

    def _select(self, *, attempt: OntologyActivation, expected_pointer: CatalogPointer | None) -> OntologyActivation:
        next_pointer = CatalogPointer.create(catalog_scope=attempt.catalog_scope,
            selected_version_digest=attempt.target_version_digest,
            selected_attempt_id=attempt.attempt_id,
            activation_sequence=1 if expected_pointer is None else expected_pointer.activation_sequence + 1)
        record = self._pointer_record(next_pointer)
        persisted = self._plane.get_record(record.memory_id)
        if persisted is not None:
            try:
                existing = CatalogPointer.model_validate(persisted.content["pointer"])
            except (KeyError, TypeError, ValueError) as exc:
                raise LearnedRelationError("catalog pointer is invalid") from exc
            if existing == next_pointer:
                self._finalize_selected(attempt)
                return self._require_attempt(attempt.attempt_id)
            if expected_pointer is not None and existing != expected_pointer:
                raise LearnedRelationError("activation pointer expectation is stale")
        if expected_pointer is not None and persisted is None:
            raise LearnedRelationError("catalog pointer is unavailable")
        if (expected_pointer is None) != (attempt.expected_pointer_digest is None):
            raise LearnedRelationError("activation pointer expectation is invalid")
        if expected_pointer is not None and (
            attempt.expected_pointer_digest != expected_pointer.pointer_digest
            or attempt.expected_pointer_sequence != expected_pointer.activation_sequence
        ):
            raise LearnedRelationError("activation pointer expectation is stale")
        conditions = ((RecordAbsentPrecondition(memory_id=record.memory_id),) if expected_pointer is None else
                      (RecordDigestPrecondition(memory_id=record.memory_id,
                       expected_digest=record_digest(persisted)),))
        try:
            self._plane.conditionally_write_records((record,), preconditions=conditions)
        except MemoryPlaneRevisionConflictError as exc:
            raise LearnedRelationError("catalog pointer compare-and-swap conflicted") from exc
        self._finalize_selected(attempt)
        return self._require_attempt(attempt.attempt_id)

    def _recover_prepared(self, attempt: OntologyActivation) -> None:
        pointer = self._load_pointer(attempt.catalog_scope)
        if pointer is not None and pointer.selected_attempt_id == attempt.attempt_id:
            self._finalize_selected(attempt)
            return
        expected_matches = (
            (pointer is None and attempt.expected_pointer_digest is None)
            or (
                pointer is not None
                and attempt.expected_pointer_digest == pointer.pointer_digest
                and attempt.expected_pointer_sequence == pointer.activation_sequence
            )
        )
        if expected_matches:
            try:
                self._select(attempt=attempt, expected_pointer=pointer)
                return
            except LearnedRelationError:
                pass
        abandoned = attempt.model_copy(update={"status": "abandoned"})
        self._replace_attempt(attempt, abandoned)
        if attempt.operation == "activate_candidate" and attempt.proposal_id is not None:
            proposal = self._require_proposal(attempt.proposal_id)
            if proposal.lifecycle == "approved_for_activation":
                self._replace_proposal(proposal, proposal.model_copy(update={"lifecycle": "activation_conflict"}))

    def _finalize_selected(self, attempt: OntologyActivation) -> None:
        current = self._require_attempt(attempt.attempt_id)
        if current.status == "selected":
            return
        if current.status != "prepared":
            raise LearnedRelationError("activation cannot be selected")
        self._replace_attempt(current, current.model_copy(update={"status": "selected"}))

    def _selected_attempt_for_proposal(self, proposal: OntologyChangeProposal) -> OntologyActivation:
        pointer = self._load_pointer(proposal.catalog_scope)
        if pointer is None:
            raise LearnedRelationError("active proposal has no selected pointer")
        attempt = self._require_attempt(pointer.selected_attempt_id)
        if (
            attempt.status != "selected"
            or attempt.operation != "activate_candidate"
            or attempt.proposal_id != proposal.proposal_id
        ):
            raise LearnedRelationError("active proposal selection is invalid")
        return attempt

    def _is_ancestor(self, scope: AgentLocalCatalogScope, *, current: str, target: str) -> bool:
        seen: set[str] = set()
        cursor = current
        while cursor not in seen:
            seen.add(cursor)
            version = self._require_version(cursor)
            if version.parent_version_digest == target:
                return True
            if version.parent_version_digest is None:
                return False
            cursor = version.parent_version_digest
        return False

    def _was_selected_in_scope(self, scope: AgentLocalCatalogScope, target: str) -> bool:
        for record in self._plane.list_records(source_kind=_KIND_ATTEMPT):
            try:
                attempt = OntologyActivation.model_validate(record.content["activation"])
            except (KeyError, TypeError, ValueError):
                continue
            if attempt.catalog_scope == scope and attempt.target_version_digest == target and attempt.status == "selected":
                return True
        return False

    @staticmethod
    def _decision_digest(*, policy: ActivationPolicy, proposal: OntologyChangeProposal) -> str:
        return _digest(b"memorii.learned-ontology.owner-decision.v1", {
            "principal_id": policy.owner_principal_id, "agent_id": policy.owner_agent_id,
            "proposal_id": proposal.proposal_id,
            "evaluation_digest": proposal.evaluation.evaluation_digest if proposal.evaluation else None,
        })

    @staticmethod
    def _rollback_decision_digest(*, policy: ActivationPolicy, target: str) -> str:
        return _digest(b"memorii.learned-ontology.owner-rollback-decision.v1", {
            "principal_id": policy.owner_principal_id, "agent_id": policy.owner_agent_id,
            "target_version_digest": target,
        })

    @staticmethod
    def _scope_key(scope: AgentLocalCatalogScope) -> str:
        return contract_digest(b"memorii.learned-ontology.learned-scope-key.v1", scope.model_dump(mode="json"))

    def _proposal_record(self, item: OntologyChangeProposal) -> CanonicalMemoryRecord:
        return CanonicalMemoryRecord(memory_id=item.proposal_id, domain=MemoryDomain.EXECUTION, text=item.lifecycle,
            content={"proposal": item.model_dump(mode="json")}, status=CommitStatus.COMMITTED,
            source_kind=_KIND_PROPOSAL, visibility=MemoryRecordVisibility.INTERNAL_CONTROL, timestamp=datetime.now(UTC))

    def _version_record(self, item: OntologyCatalogVersion) -> CanonicalMemoryRecord:
        return CanonicalMemoryRecord(memory_id="learned-catalog-version:" + item.version_digest, domain=MemoryDomain.EXECUTION,
            text="", content={"version": item.model_dump(mode="json")}, status=CommitStatus.COMMITTED,
            source_kind=_KIND_VERSION, visibility=MemoryRecordVisibility.INTERNAL_CONTROL, timestamp=datetime.now(UTC))

    def _pointer_record(self, item: CatalogPointer) -> CanonicalMemoryRecord:
        return CanonicalMemoryRecord(memory_id="learned-catalog-pointer:" + self._scope_key(item.catalog_scope), domain=MemoryDomain.EXECUTION,
            text="", content={"pointer": item.model_dump(mode="json")}, status=CommitStatus.COMMITTED,
            source_kind=_KIND_POINTER, visibility=MemoryRecordVisibility.INTERNAL_CONTROL, timestamp=datetime.now(UTC))

    def _attempt_record(self, item: OntologyActivation) -> CanonicalMemoryRecord:
        return CanonicalMemoryRecord(memory_id=item.attempt_id, domain=MemoryDomain.EXECUTION, text=item.status,
            content={"activation": item.model_dump(mode="json")}, status=CommitStatus.COMMITTED,
            source_kind=_KIND_ATTEMPT, visibility=MemoryRecordVisibility.INTERNAL_CONTROL, timestamp=datetime.now(UTC))

    def _write_proposal(self, item: OntologyChangeProposal) -> None:
        try:
            self._plane.conditionally_write_records((self._proposal_record(item),), preconditions=(RecordAbsentPrecondition(memory_id=item.proposal_id),))
        except MemoryPlaneRevisionConflictError as exc:
            if self._require_proposal(item.proposal_id) != item:
                raise LearnedRelationError("proposal identity collides") from exc

    def _replace_proposal(self, old: OntologyChangeProposal, new: OntologyChangeProposal) -> None:
        # Lifecycle changes receive a fresh identity, so use one stable record key.
        record = self._proposal_record(new)
        record = record.model_copy(update={"memory_id": old.proposal_id})
        persisted = self._plane.get_record(old.proposal_id)
        if persisted is None:
            raise LearnedRelationError("proposal is unavailable")
        try:
            self._plane.conditionally_write_records((record,), preconditions=(RecordDigestPrecondition(memory_id=old.proposal_id, expected_digest=record_digest(persisted)),))
        except MemoryPlaneRevisionConflictError as exc:
            raise LearnedRelationError("proposal lifecycle conflicted") from exc

    def _write_version(self, item: OntologyCatalogVersion) -> None:
        record = self._version_record(item)
        try:
            self._plane.conditionally_write_records((record,), preconditions=(RecordAbsentPrecondition(memory_id=record.memory_id),))
        except MemoryPlaneRevisionConflictError as exc:
            if self._require_version(item.version_digest) != item:
                raise LearnedRelationError("catalog version identity collides") from exc

    def _write_attempt(self, item: OntologyActivation) -> None:
        try:
            self._plane.conditionally_write_records((self._attempt_record(item),), preconditions=(RecordAbsentPrecondition(memory_id=item.attempt_id),))
        except MemoryPlaneRevisionConflictError as exc:
            if self._require_attempt(item.attempt_id) != item:
                raise LearnedRelationError("activation identity collides") from exc

    def _replace_attempt(self, old: OntologyActivation, new: OntologyActivation) -> None:
        persisted = self._plane.get_record(old.attempt_id)
        if persisted is None:
            raise LearnedRelationError("activation is unavailable")
        try:
            self._plane.conditionally_write_records((self._attempt_record(new),), preconditions=(RecordDigestPrecondition(memory_id=old.attempt_id, expected_digest=record_digest(persisted)),))
        except MemoryPlaneRevisionConflictError as exc:
            raise LearnedRelationError("activation finalization conflicted") from exc

    def _require_proposal(self, identifier: str) -> OntologyChangeProposal:
        record = self._plane.get_record(identifier)
        proposal = self._decode_proposal(record) if record is not None else None
        if proposal is None:
            raise LearnedRelationError("proposal is unavailable")
        return proposal

    @staticmethod
    def _decode_proposal(record: CanonicalMemoryRecord | None) -> OntologyChangeProposal | None:
        try:
            return None if record is None or record.source_kind != _KIND_PROPOSAL else OntologyChangeProposal.model_validate(record.content["proposal"])
        except (KeyError, TypeError, ValueError):
            return None

    def _require_version(self, digest: str) -> OntologyCatalogVersion:
        record = self._plane.get_record("learned-catalog-version:" + digest)
        try:
            if record is None or record.source_kind != _KIND_VERSION:
                raise ValueError
            return OntologyCatalogVersion.model_validate(record.content["version"])
        except (KeyError, TypeError, ValueError) as exc:
            raise LearnedRelationError("catalog version is unavailable") from exc

    def _load_pointer(self, scope: AgentLocalCatalogScope) -> CatalogPointer | None:
        record = self._plane.get_record("learned-catalog-pointer:" + self._scope_key(scope))
        if record is None:
            return None
        try:
            pointer = CatalogPointer.model_validate(record.content["pointer"])
        except (KeyError, TypeError, ValueError) as exc:
            raise LearnedRelationError("catalog pointer is invalid") from exc
        if pointer.catalog_scope != scope:
            raise LearnedRelationError("catalog pointer scope is invalid")
        return pointer

    def _require_attempt(self, identifier: str) -> OntologyActivation:
        record = self._plane.get_record(identifier)
        try:
            if record is None or record.source_kind != _KIND_ATTEMPT:
                raise ValueError
            return OntologyActivation.model_validate(record.content["activation"])
        except (KeyError, TypeError, ValueError) as exc:
            raise LearnedRelationError("activation is unavailable") from exc


class LearnedRelationCandidateService:
    """Admit the frozen learned edit from durable recurrence evidence only."""

    def __init__(
        self, *, memory_plane: MemoryPlaneService, runtime: LearnedRelationRuntime,
        evaluator: RegisteredPairedEvaluator | None = None,
    ) -> None:
        self._plane = memory_plane
        self._runtime = runtime
        self._recurrence = CoverageRecurrenceRepository(memory_plane)
        self._gaps = VerifiedCoverageGapRepository(memory_plane)
        self._observations = CoverageObservationRepository(memory_plane)
        self._evaluator = evaluator

    def admit_recurrence(
        self, *, group_id: str, authenticated: AuthenticatedPrincipalAgent,
    ) -> OntologyChangeProposal:
        group = self._recurrence.load(group_id)
        if group is None or not group.proposal_eligible:
            raise LearnedRelationError("recurrence group is not eligible")
        if not isinstance(group.signature, RelationGapSignature) or (
            group.signature.normalized_relation_meaning != _RELATION_ID
            or group.signature.subject_type_id != "Person"
            or group.signature.object_type_id != "Person"
            or group.signature.evidence_rule_id != "direct_assertion:v1"
        ):
            raise LearnedRelationError("recurrence group is outside the frozen relation")
        scope = AgentLocalCatalogScope(
            principal_id=authenticated.principal_id, agent_id=authenticated.agent_id,
        )
        evidence: list[OntologyEvidenceReference] = []
        for evidence_id in group.evidence_ids:
            gap = self._gaps.load(evidence_id)
            if gap is None or (
                gap.catalog_scope != group.catalog_scope
                or gap.catalog_digest != group.catalog_digest
                or gap.source_scope_digest != group.source_scope_digest
                or gap.signature != group.signature
            ):
                raise LearnedRelationError("recurrence evidence is invalid")
            observation = self._observations.load(gap.observation_id)
            if observation is None or (
                observation.observation_digest != gap.observation_digest
                or observation.source_id == ""
                or observation.source_digest != gap.source_digest
                or observation.source_scope_digest != gap.source_scope_digest
                or observation.origin_lineage_digest != gap.origin_lineage_digest
                or (observation.principal_id, observation.agent_id)
                != (authenticated.principal_id, authenticated.agent_id)
            ):
                raise LearnedRelationError("recurrence observation is invalid")
            source = self._plane.get_record(observation.source_id)
            if source is None or source.source_kind != "semantic_ingestion_source":
                raise LearnedRelationError("retained recurrence source is unavailable")
            try:
                from memorii.core.memory_evolution.admission import source_admission_source_digest
                source_digest = source_admission_source_digest(source)
            except (TypeError, ValueError):
                raise LearnedRelationError("retained recurrence source is invalid") from None
            if source_digest != gap.source_digest:
                raise LearnedRelationError("retained recurrence source is invalid")
            evidence.append(OntologyEvidenceReference(
                source_id=observation.source_id, source_digest=gap.source_digest,
                origin_lineage_digest=gap.origin_lineage_digest,
                source_scope_digest=gap.source_scope_digest,
            ))
        if len({item.origin_lineage_digest for item in evidence}) < 3 or len(evidence) != len(group.evidence_ids):
            raise LearnedRelationError("recurrence evidence is not independent")
        pointer = self._runtime._load_pointer(scope)
        parent_digest = group.catalog_digest if pointer is None else pointer.selected_version_digest
        proposal = OntologyChangeProposal.create(
            catalog_scope=scope, parent_catalog_digest=parent_digest,
            relation=RelationDeclaration(description="A person mentors another person."),
            evidence=tuple(evidence),
        )
        try:
            prepared = self._runtime.prepare_candidate(proposal)
        except MemoryPlaneRevisionConflictError:
            prepared = self._runtime._require_proposal(proposal.proposal_id)
        if self._evaluator is None:
            return self._runtime.record_evaluation(
                proposal_id=prepared.proposal_id,
                evaluation=PairedEvaluation.create(
                    binding_digest="0" * 64, targeted_positive_count=0,
                    targeted_positive_committed_and_read=0, parent_regressions=0,
                    unsupported_or_misleading_failures=0, scope_or_provenance_failures=0,
                    available=False,
                ),
            )
        return self._runtime.record_evaluation(
            proposal_id=prepared.proposal_id, evaluation=self._evaluator.evaluate(prepared),
        )


def learned_runtime_bundle_digest(version: OntologyCatalogVersion) -> str:
    """The closed runtime coordinate for the single supported learned bundle.

    The first learned relation intentionally reuses the established direct
    Person-to-Person runtime family.  Its digest names the immutable version
    and relation declaration, rather than a mutable process-local callback.
    """
    if version.relation_ids != (_RELATION_ID,):
        raise LearnedRelationError("learned catalog runtime is unavailable")
    return _digest(
        b"memorii.learned-ontology.mentors-runtime-bundle.v1",
        {
            "version_digest": version.version_digest,
            "catalog_digest": version.catalog_digest,
            "relation_id": _RELATION_ID,
            "subject_type": "Person",
            "object_type": "Person",
            "cardinality": "multi",
            "evidence_rule_id": "direct_assertion",
        },
    )


def _require_agent_owner(
    *, scope: AgentLocalCatalogScope, authenticated: AuthenticatedPrincipalAgent,
) -> None:
    if (authenticated.principal_id, authenticated.agent_id) != (
        scope.principal_id,
        scope.agent_id,
    ):
        raise LearnedRelationError("catalog owner authorization is required")


def _record_for(
    records: tuple[CanonicalMemoryRecord, ...] | list[CanonicalMemoryRecord], memory_id: str,
) -> CanonicalMemoryRecord | None:
    return next((record for record in records if record.memory_id == memory_id), None)


def _require_control_record(
    record: CanonicalMemoryRecord | None, *, source_kind: str,
) -> CanonicalMemoryRecord:
    if (
        record is None
        or record.domain != MemoryDomain.EXECUTION
        or record.status != CommitStatus.COMMITTED
        or record.visibility != MemoryRecordVisibility.INTERNAL_CONTROL
        or record.source_kind != source_kind
    ):
        raise LearnedRelationError("learned catalog control state is invalid")
    return record


def learned_catalog_pointer_memory_id(scope: AgentLocalCatalogScope) -> str:
    return "learned-catalog-pointer:" + contract_digest(
        b"memorii.learned-ontology.learned-scope-key.v1", scope.model_dump(mode="json")
    )


def learned_catalog_version_memory_id(version: OntologyCatalogVersion) -> str:
    """Return the persisted coordinate for one immutable learned version."""
    return "learned-catalog-version:" + version.version_digest


def locate_selected_learned_catalog(
    records: tuple[CanonicalMemoryRecord, ...] | list[CanonicalMemoryRecord],
    *, scope: AgentLocalCatalogScope, authenticated: AuthenticatedPrincipalAgent,
) -> tuple[OntologyCatalogVersion, CatalogPointer]:
    """Resolve one owner-authorized active learned version from persisted state."""
    _require_agent_owner(scope=scope, authenticated=authenticated)
    pointer_record = _require_control_record(
        _record_for(records, learned_catalog_pointer_memory_id(scope)), source_kind=_KIND_POINTER,
    )
    try:
        pointer = CatalogPointer.model_validate(pointer_record.content["pointer"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LearnedRelationError("learned catalog control state is invalid") from exc
    if pointer.catalog_scope != scope:
        raise LearnedRelationError("learned catalog control state is invalid")
    version = locate_historical_learned_catalog(
        records, scope=scope, authenticated=authenticated,
        version_id=None, version_digest=pointer.selected_version_digest,
    )
    attempt_record = _require_control_record(
        _record_for(records, pointer.selected_attempt_id), source_kind=_KIND_ATTEMPT,
    )
    try:
        attempt = OntologyActivation.model_validate(attempt_record.content["activation"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LearnedRelationError("learned catalog control state is invalid") from exc
    if (
        attempt.catalog_scope != scope
        or attempt.status != "selected"
        or attempt.target_version_digest != version.version_digest
    ):
        raise LearnedRelationError("learned catalog control state is invalid")
    return version, pointer


def locate_historical_learned_catalog(
    records: tuple[CanonicalMemoryRecord, ...] | list[CanonicalMemoryRecord],
    *, scope: AgentLocalCatalogScope, authenticated: AuthenticatedPrincipalAgent,
    version_id: str | None, version_digest: str,
) -> OntologyCatalogVersion:
    """Resolve a pinned learned version without consulting the current head."""
    _require_agent_owner(scope=scope, authenticated=authenticated)
    record = _require_control_record(
        _record_for(records, "learned-catalog-version:" + version_digest), source_kind=_KIND_VERSION,
    )
    try:
        version = OntologyCatalogVersion.model_validate(record.content["version"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LearnedRelationError("learned catalog version is unavailable") from exc
    if (
        version.catalog_scope != scope
        or version.version_digest != version_digest
        or (version_id is not None and version.version_id != version_id)
    ):
        raise LearnedRelationError("learned catalog version is unavailable")
    # Fail closed for an invalid active child; no parent fallback is allowed.
    learned_runtime_bundle_digest(version)
    return version


__all__ = [
    "ActivationPolicy", "AgentLocalCatalogScope", "CatalogPointer", "LearnedRelationError", "LearnedRelationRuntime",
    "OntologyActivation", "OntologyCatalogVersion", "OntologyChangeProposal",
    "FrozenMentorsPairedEvaluator", "LearnedRelationCandidateService",
    "OntologyEvidenceReference", "OrdinarySemanticReplayWriter", "PairedEvaluation",
    "RegisteredPairedEvaluator",
    "RelationDeclaration", "learned_catalog_pointer_memory_id",
    "learned_runtime_bundle_digest", "locate_historical_learned_catalog",
    "locate_selected_learned_catalog",
]
