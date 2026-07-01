"""Runtime memory evolution service over the canonical memory plane."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid5, NAMESPACE_URL

from memorii.core.memory_evolution.extraction import RuleMemoryExtractor
from memorii.core.memory_evolution.models import (
    ClaimLifecycleState,
    ClaimLifecycleTransition,
    ClaimState,
    ClaimTransitionType,
    ExtractedClaim,
    MemoryEvolutionResult,
    RetrievalView,
    SourceObservation,
    ValidationResult,
)
from memorii.core.memory_evolution.predicates import PredicateRegistry, source_trust_rank
from memorii.core.memory_evolution.validation import MemoryEvolutionValidator
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.domain.enums import CommitStatus, MemoryDomain, SourceType, TemporalValidityStatus


class MemoryEvolutionService:
    def __init__(
        self,
        *,
        memory_plane: MemoryPlaneService,
        predicate_registry: PredicateRegistry | None = None,
        extractor: RuleMemoryExtractor | None = None,
        validator: MemoryEvolutionValidator | None = None,
    ) -> None:
        self._memory_plane = memory_plane
        self._predicates = predicate_registry or PredicateRegistry()
        self._extractor = extractor or RuleMemoryExtractor()
        self._validator = validator or MemoryEvolutionValidator(predicate_registry=self._predicates)

    def evolve_records(self, records: list[CanonicalMemoryRecord]) -> MemoryEvolutionResult:
        observations = [source_observation_from_record(record) for record in records if record.is_raw_event or record.domain == MemoryDomain.TRANSCRIPT]
        run, entities, claims, actions = self._extractor.extract(observations)
        validation_results = self._validator.validate_claims(claims=claims, observations=observations)
        run = run.model_copy(update={"validation_summary": self._validator.summary(validation_results)})

        claim_states: list[ClaimState] = []
        transitions: list[ClaimLifecycleTransition] = []
        written_record_ids: list[str] = []
        for claim in claims:
            results = validation_results.get(claim.claim_id, [])
            if not self._validator.accepted(results):
                continue
            state, claim_transitions, record_id = self._apply_claim(claim=claim, validation_results=results)
            claim_states.append(state)
            transitions.extend(claim_transitions)
            written_record_ids.append(record_id)

        for action in actions:
            record = CanonicalMemoryRecord(
                memory_id=f"mem:evolution:action:{action.action_id}",
                domain=MemoryDomain.EXECUTION,
                text=f"{action.action_type} {action.status}",
                content={
                    "memory_evolution_kind": "action",
                    "action": action.model_dump(mode="json"),
                },
                status=CommitStatus.COMMITTED,
                validity_status=TemporalValidityStatus.ACTIVE,
                source_kind="memory_evolution",
                timestamp=action.timestamp,
                is_raw_event=False,
                source_candidate_id=action.extraction_run_id,
            )
            self._memory_plane.stage_record(record)
            written_record_ids.append(record.memory_id)

        return MemoryEvolutionResult(
            extraction_run=run,
            entities=entities,
            claims=claims,
            actions=actions,
            validation_results=validation_results,
            claim_states=claim_states,
            transitions=transitions,
            written_record_ids=written_record_ids,
        )

    def evolve_source_ids(self, source_ids: list[str]) -> MemoryEvolutionResult:
        records = [record for source_id in source_ids if (record := self._memory_plane.get_record(source_id)) is not None]
        return self.evolve_records(records)

    def retrieve_claim_states(
        self,
        *,
        view: RetrievalView = RetrievalView.CURRENT,
        valid_at: datetime | None = None,
        predicate_id: str | None = None,
        subject_entity_id: str | None = None,
    ) -> list[ClaimState]:
        states = self._list_claim_states()
        if predicate_id is not None:
            states = [state for state in states if state.claim_key.predicate_id == predicate_id]
        if subject_entity_id is not None:
            states = [state for state in states if state.claim_key.subject_entity_id == subject_entity_id]

        if view == RetrievalView.CURRENT:
            return [state for state in states if state.lifecycle_state == ClaimLifecycleState.ACTIVE]
        if view == RetrievalView.HISTORICAL_AT:
            if valid_at is None:
                raise ValueError("valid_at is required for historical_at retrieval")
            return [state for state in states if _valid_at(state, valid_at)]
        if view == RetrievalView.CONFLICTS:
            return [state for state in states if state.conflict_with_claim_ids or state.lifecycle_state == ClaimLifecycleState.INVALIDATED]
        if view == RetrievalView.EVIDENCE_ONLY:
            return []
        return states

    def _apply_claim(
        self,
        *,
        claim: ExtractedClaim,
        validation_results: list[ValidationResult],
    ) -> tuple[ClaimState, list[ClaimLifecycleTransition], str]:
        now = datetime.now(UTC)
        policy = self._predicates.require(claim.claim_key.predicate_id)
        existing_active = [
            state
            for state in self._list_claim_states()
            if state.claim_key.stable_id() == claim.claim_key.stable_id()
            and state.lifecycle_state == ClaimLifecycleState.ACTIVE
        ]
        same_value = [state for state in existing_active if _norm(state.object_value) == _norm(claim.object_value)]
        different_value = [state for state in existing_active if _norm(state.object_value) != _norm(claim.object_value)]
        transitions: list[ClaimLifecycleTransition] = []

        if same_value:
            lifecycle_state = ClaimLifecycleState.ACTIVE
            transition_type = ClaimTransitionType.REINFORCE
            related = [state.claim_id for state in same_value]
            supersedes: list[str] = []
            conflicts: list[str] = []
            rationale = "new claim reinforces existing active claim"
        elif policy.is_single_value and different_value:
            strongest = max(different_value, key=lambda state: _state_strength(policy.predicate_id, state))
            if _claim_strength(policy.predicate_id, claim) >= _state_strength(policy.predicate_id, strongest):
                lifecycle_state = ClaimLifecycleState.ACTIVE
                transition_type = ClaimTransitionType.SUPERSEDE
                related = [state.claim_id for state in different_value]
                supersedes = list(related)
                conflicts = list(related)
                rationale = "new single-value claim supersedes weaker or older active claims"
                for old_state in different_value:
                    self._mark_superseded(old_state=old_state, superseded_by_claim_id=claim.claim_id, valid_to=claim.valid_from or now)
            else:
                lifecycle_state = ClaimLifecycleState.INVALIDATED
                transition_type = ClaimTransitionType.INVALIDATE
                related = [strongest.claim_id]
                supersedes = []
                conflicts = [strongest.claim_id]
                rationale = "new single-value claim conflicts with a stronger active claim"
        else:
            lifecycle_state = ClaimLifecycleState.ACTIVE
            transition_type = ClaimTransitionType.CREATE if not existing_active else ClaimTransitionType.MERGE
            related = [state.claim_id for state in existing_active]
            supersedes = []
            conflicts = []
            rationale = "new claim creates or accumulates under predicate policy"

        state = ClaimState(
            claim_id=claim.claim_id,
            claim_key=claim.claim_key,
            object_value=claim.object_value,
            lifecycle_state=lifecycle_state,
            source_claim_id=claim.claim_id,
            confidence=claim.confidence,
            validation_results=validation_results,
            evidence_spans=claim.evidence_spans,
            supersedes_claim_ids=supersedes,
            conflict_with_claim_ids=conflicts,
            valid_from=claim.valid_from,
            valid_to=claim.valid_to,
            created_at=now,
            updated_at=now,
        )
        transitions.append(
            ClaimLifecycleTransition(
                transition_id=_stable_id("transition", f"{claim.claim_id}:{transition_type.value}:{','.join(related)}"),
                transition_type=transition_type,
                claim_id=claim.claim_id,
                related_claim_ids=related,
                rationale=rationale,
            )
        )
        record = _record_from_claim_state(state=state, source_candidate_id=claim.extraction_run_id)
        self._memory_plane.stage_record(record)
        return state, transitions, record.memory_id

    def _mark_superseded(
        self,
        *,
        old_state: ClaimState,
        superseded_by_claim_id: str,
        valid_to: datetime,
    ) -> None:
        updated = old_state.model_copy(
            update={
                "lifecycle_state": ClaimLifecycleState.SUPERSEDED,
                "superseded_by_claim_id": superseded_by_claim_id,
                "valid_to": valid_to,
                "updated_at": datetime.now(UTC),
            }
        )
        record = _record_from_claim_state(state=updated, source_candidate_id=updated.source_claim_id)
        self._memory_plane.upsert_record(record)

    def _list_claim_states(self) -> list[ClaimState]:
        states: list[ClaimState] = []
        for record in self._memory_plane.list_records(domains=[MemoryDomain.SEMANTIC, MemoryDomain.USER, MemoryDomain.EXECUTION]):
            if record.content.get("memory_evolution_kind") != "claim_state":
                continue
            states.append(ClaimState.model_validate(record.content["claim_state"]))
        return states


def source_observation_from_record(record: CanonicalMemoryRecord) -> SourceObservation:
    return SourceObservation(
        source_id=record.memory_id,
        text=record.text,
        source_type=_source_type_from_record(record),
        timestamp=record.timestamp,
        domain=record.domain,
        session_id=record.session_id,
        task_id=record.task_id,
        user_id=record.user_id,
    )


def _record_from_claim_state(*, state: ClaimState, source_candidate_id: str) -> CanonicalMemoryRecord:
    validity = {
        ClaimLifecycleState.ACTIVE: TemporalValidityStatus.ACTIVE,
        ClaimLifecycleState.EXPIRED: TemporalValidityStatus.EXPIRED,
        ClaimLifecycleState.SUPERSEDED: TemporalValidityStatus.INVALIDATED,
        ClaimLifecycleState.INVALIDATED: TemporalValidityStatus.INVALIDATED,
        ClaimLifecycleState.ARCHIVED: TemporalValidityStatus.INVALIDATED,
        ClaimLifecycleState.CANDIDATE: TemporalValidityStatus.UNKNOWN,
    }[state.lifecycle_state]
    domain = _domain_for_predicate(state.claim_key.predicate_id)
    return CanonicalMemoryRecord(
        memory_id=f"mem:evolution:claim:{state.claim_id}",
        domain=domain,
        text=f"{state.claim_key.subject_entity_id} {state.claim_key.predicate_id} is {state.object_value}",
        content={
            "memory_evolution_kind": "claim_state",
            "claim_state": state.model_dump(mode="json"),
            "claim_key": state.claim_key.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        validity_status=validity,
        source_kind="memory_evolution",
        timestamp=state.updated_at,
        valid_from=state.valid_from,
        valid_to=state.valid_to,
        source_candidate_id=source_candidate_id,
        supersedes_memory_ids=[f"mem:evolution:claim:{claim_id}" for claim_id in state.supersedes_claim_ids],
        conflict_with_memory_ids=[f"mem:evolution:claim:{claim_id}" for claim_id in state.conflict_with_claim_ids],
    )


def _source_type_from_record(record: CanonicalMemoryRecord) -> SourceType:
    source_kind = record.source_kind.lower()
    if "user" in source_kind:
        return SourceType.USER
    if "tool" in source_kind:
        return SourceType.TOOL
    if "environment" in source_kind:
        return SourceType.ENVIRONMENT
    if "agent" in source_kind:
        return SourceType.AGENT
    if "system" in source_kind:
        return SourceType.SYSTEM
    if record.domain == MemoryDomain.TRANSCRIPT:
        return SourceType.DERIVED
    return SourceType.DERIVED


def _domain_for_predicate(predicate_id: str) -> MemoryDomain:
    if predicate_id == "preference":
        return MemoryDomain.USER
    if predicate_id == "action_state":
        return MemoryDomain.EXECUTION
    return MemoryDomain.SEMANTIC


def _valid_at(state: ClaimState, valid_at: datetime) -> bool:
    if state.valid_from is not None and state.valid_from > valid_at:
        return False
    if state.valid_to is not None and state.valid_to < valid_at:
        return False
    return True


def _claim_strength(predicate_id: str, claim: ExtractedClaim) -> tuple[float, datetime]:
    source_type = claim.evidence_spans[0].source_type if claim.evidence_spans else SourceType.DERIVED
    policy = PredicateRegistry().require(predicate_id)
    trust_bonus = source_trust_rank(policy, source_type) / max(1, len(policy.trust_precedence)) * 0.05
    return (min(1.0, claim.confidence.calibrated + trust_bonus), claim.valid_from or datetime.min.replace(tzinfo=UTC))


def _state_strength(predicate_id: str, state: ClaimState) -> tuple[float, datetime]:
    del predicate_id
    source_type = state.evidence_spans[0].source_type if state.evidence_spans else SourceType.DERIVED
    policy = PredicateRegistry().require(state.claim_key.predicate_id)
    trust_bonus = source_trust_rank(policy, source_type) / max(1, len(policy.trust_precedence)) * 0.05
    return (min(1.0, state.confidence.calibrated + trust_bonus), state.valid_from or datetime.min.replace(tzinfo=UTC))


def _norm(value: str) -> str:
    return " ".join(value.lower().strip(" .").split())


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}:{uuid5(NAMESPACE_URL, value)}"
