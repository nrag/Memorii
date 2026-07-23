"""Deterministic claim comparison helpers used by lifecycle mutation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid5

from memorii.core.memory_evolution.models import (
    ClaimLifecycleState,
    ClaimLifecycleTransition,
    ClaimState,
    ClaimTransitionType,
    ContradictionSet,
    EntityLinkState,
    ExtractedClaim,
    SourceModality,
    SourceObservation,
    ValidationResult,
)
from memorii.core.memory_evolution.predicates import PredicateRegistry, source_trust_rank
from memorii.core.memory_evolution.record_projection import record_from_claim_state
from memorii.domain.enums import SourceType

if TYPE_CHECKING:
    from memorii.core.memory_evolution.confidence import ConfidenceAggregator
    from memorii.core.memory_evolution.contradictions import ContradictionResolver
    from memorii.core.memory_evolution.entity_resolution import EntityResolutionService
    from memorii.core.memory_evolution.state_repository import EvolutionStateRepository
    from memorii.core.memory_plane.service import MemoryPlaneService


def claim_strength(
    claim: ExtractedClaim,
    *,
    predicate_registry: PredicateRegistry,
) -> tuple[float, datetime]:
    source_type = claim.evidence_spans[0].source_type if claim.evidence_spans else SourceType.DERIVED
    policy = predicate_registry.require(claim.claim_key.predicate_id)
    trust_bonus = source_trust_rank(policy, source_type) / max(1, len(policy.trust_precedence)) * 0.05
    return min(1.0, claim.confidence.calibrated + trust_bonus), claim.valid_from or datetime.min.replace(tzinfo=UTC)


def state_strength(
    state: ClaimState,
    *,
    predicate_registry: PredicateRegistry,
) -> tuple[float, datetime]:
    source_type = state.evidence_spans[0].source_type if state.evidence_spans else SourceType.DERIVED
    policy = predicate_registry.require(state.claim_key.predicate_id)
    trust_bonus = source_trust_rank(policy, source_type) / max(1, len(policy.trust_precedence)) * 0.05
    return min(1.0, state.confidence.calibrated + trust_bonus), state.valid_from or datetime.min.replace(tzinfo=UTC)


def modality_for_claim(claim: ExtractedClaim, observations: list[SourceObservation]) -> SourceModality:
    observation_by_id = {observation.source_id: observation for observation in observations}
    for span in claim.evidence_spans:
        if (observation := observation_by_id.get(span.source_id)) is not None:
            return observation.modality
    return SourceModality.ASSERTION


def normalize_claim_value(value: str) -> str:
    return " ".join(value.lower().strip(" .").split())


def stable_evolution_id(prefix: str, value: str) -> str:
    return f"{prefix}:{uuid5(NAMESPACE_URL, value)}"


class ClaimLifecycleMutator:
    """Apply validated claims to lifecycle state inside the caller's unit of work."""

    def __init__(
        self,
        *,
        memory_plane: MemoryPlaneService,
        predicate_registry: PredicateRegistry,
        confidence_aggregator: ConfidenceAggregator,
        contradiction_resolver: ContradictionResolver,
        entity_resolver: EntityResolutionService,
        state_repository: EvolutionStateRepository,
        now_provider: Callable[[], datetime],
    ) -> None:
        self._memory_plane = memory_plane
        self._predicates = predicate_registry
        self._confidence_aggregator = confidence_aggregator
        self._contradiction_resolver = contradiction_resolver
        self._entity_resolver = entity_resolver
        self._state_repository = state_repository
        self._now_provider = now_provider

    def retain_rejected_claim(
        self,
        *,
        claim: ExtractedClaim,
        validation_results: list[ValidationResult],
        source_observations: list[SourceObservation],
        entity_links: list[EntityLinkState],
    ) -> tuple[ClaimState, str, ContradictionSet | None]:
        """Persist rejected evidence as invalidated history, never current truth."""

        now = self._now_provider()
        modality = modality_for_claim(claim, source_observations)
        existing_claim_ids = {state.claim_id for state in self._state_repository.list_claim_states()}
        rejected_claim_id = claim.claim_id
        if rejected_claim_id in existing_claim_ids:
            evidence_identity = "|".join(sorted(span.source_id for span in claim.evidence_spans))
            rejected_claim_id = stable_evolution_id(
                "claim-rejection",
                f"{claim.claim_id}:{evidence_identity}",
            )
        normalized_claim = claim.model_copy(
            update={
                "claim_id": rejected_claim_id,
                "confidence": self._confidence_aggregator.initial_for_claim(claim, modality=modality),
            }
        )
        subject_link = self._entity_resolver.link_for_entity(
            claim.claim_key.subject_entity_id,
            entity_links,
            scope=claim.claim_key.scope,
        )
        object_link = self._entity_resolver.link_for_entity(
            claim.object_entity_id,
            entity_links,
            scope=claim.claim_key.scope,
        )
        existing_active = [
            state
            for state in self._state_repository.list_claim_states()
            if state.claim_key.stable_id() == claim.claim_key.stable_id()
            and state.lifecycle_state == ClaimLifecycleState.ACTIVE
        ]
        different_value = [
            state
            for state in existing_active
            if normalize_claim_value(state.object_value) != normalize_claim_value(claim.object_value)
        ]
        strongest = max(
            different_value,
            key=lambda state: state_strength(state, predicate_registry=self._predicates),
            default=None,
        )
        state = ClaimState(
            claim_id=normalized_claim.claim_id,
            claim_key=normalized_claim.claim_key,
            object_value=normalized_claim.object_value,
            lifecycle_state=ClaimLifecycleState.INVALIDATED,
            source_claim_id=claim.claim_id,
            confidence=normalized_claim.confidence,
            validation_results=validation_results,
            evidence_spans=normalized_claim.evidence_spans,
            conflict_with_claim_ids=[item.claim_id for item in different_value],
            subject_link_id=subject_link.link_id if subject_link is not None else None,
            object_link_id=object_link.link_id if object_link is not None else None,
            valid_from=normalized_claim.valid_from,
            valid_to=normalized_claim.valid_to,
            created_at=now,
            updated_at=now,
        )
        record = record_from_claim_state(state=state, source_candidate_id=normalized_claim.extraction_run_id)
        self._memory_plane.stage_record(record)
        contradiction_set: ContradictionSet | None = None
        policy = self._predicates.get(normalized_claim.claim_key.predicate_id)
        if policy is not None and different_value:
            contradiction_set = self._contradiction_resolver.contradiction_for(
                policy=policy,
                claim=normalized_claim,
                existing_active=different_value,
                active_claim_id=strongest.claim_id if strongest is not None else None,
            )
        return state, record.memory_id, contradiction_set

    def apply_claim(
        self,
        *,
        claim: ExtractedClaim,
        validation_results: list[ValidationResult],
        source_observations: list[SourceObservation],
        entity_links: list[EntityLinkState],
    ) -> tuple[ClaimState, list[ClaimLifecycleTransition], str, ContradictionSet | None]:
        now = self._now_provider()
        policy = self._predicates.require(claim.claim_key.predicate_id)
        modality = modality_for_claim(claim, source_observations)
        claim = claim.model_copy(
            update={"confidence": self._confidence_aggregator.initial_for_claim(claim, modality=modality)}
        )
        subject_link = self._entity_resolver.link_for_entity(
            claim.claim_key.subject_entity_id,
            entity_links,
            scope=claim.claim_key.scope,
        )
        object_link = self._entity_resolver.link_for_entity(
            claim.object_entity_id,
            entity_links,
            scope=claim.claim_key.scope,
        )
        existing_active = [
            state
            for state in self._state_repository.list_claim_states()
            if state.claim_key.stable_id() == claim.claim_key.stable_id()
            and state.lifecycle_state == ClaimLifecycleState.ACTIVE
        ]
        same_value = [
            state
            for state in existing_active
            if normalize_claim_value(state.object_value) == normalize_claim_value(claim.object_value)
        ]
        different_value = [
            state
            for state in existing_active
            if normalize_claim_value(state.object_value) != normalize_claim_value(claim.object_value)
        ]

        if same_value:
            return self._reinforce_claim(
                existing=same_value[0],
                claim=claim,
                validation_results=validation_results,
                modality=modality,
                now=now,
            )

        lifecycle_state = ClaimLifecycleState.ACTIVE
        transition_type = ClaimTransitionType.CREATE if not existing_active else ClaimTransitionType.MERGE
        related = [state.claim_id for state in existing_active]
        supersedes: list[str] = []
        conflicts: list[str] = []
        rationale = "new claim creates or accumulates under predicate policy"
        strongest_conflicting_claim_id: str | None = None
        if policy.is_single_value and different_value:
            strongest = max(
                different_value,
                key=lambda state: state_strength(state, predicate_registry=self._predicates),
            )
            strongest_conflicting_claim_id = strongest.claim_id
            if claim_strength(claim, predicate_registry=self._predicates) >= state_strength(
                strongest,
                predicate_registry=self._predicates,
            ):
                transition_type = ClaimTransitionType.SUPERSEDE
                related = [state.claim_id for state in different_value]
                supersedes = list(related)
                conflicts = list(related)
                rationale = "new single-value claim supersedes weaker or older active claims"
                for old_state in different_value:
                    self._mark_superseded(
                        old_state=old_state,
                        superseded_by_claim_id=claim.claim_id,
                        valid_to=claim.valid_from or now,
                    )
            else:
                lifecycle_state = ClaimLifecycleState.INVALIDATED
                transition_type = ClaimTransitionType.INVALIDATE
                related = [strongest.claim_id]
                conflicts = [strongest.claim_id]
                rationale = "new single-value claim conflicts with a stronger active claim"

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
            subject_link_id=subject_link.link_id if subject_link is not None else None,
            object_link_id=object_link.link_id if object_link is not None else None,
            valid_from=claim.valid_from,
            valid_to=claim.valid_to,
            created_at=now,
            updated_at=now,
        )
        transition = ClaimLifecycleTransition(
            transition_id=stable_evolution_id(
                "transition",
                f"{claim.claim_id}:{transition_type.value}:{','.join(related)}",
            ),
            transition_type=transition_type,
            claim_id=claim.claim_id,
            related_claim_ids=related,
            rationale=rationale,
        )
        record = record_from_claim_state(state=state, source_candidate_id=claim.extraction_run_id)
        self._memory_plane.stage_record(record)
        contradiction_set = self._contradiction_resolver.contradiction_for(
            policy=policy,
            claim=claim,
            existing_active=different_value,
            active_claim_id=(
                state.claim_id
                if state.lifecycle_state == ClaimLifecycleState.ACTIVE
                else strongest_conflicting_claim_id
            ),
        )
        return state, [transition], record.memory_id, contradiction_set

    def _reinforce_claim(
        self,
        *,
        existing: ClaimState,
        claim: ExtractedClaim,
        validation_results: list[ValidationResult],
        modality: SourceModality,
        now: datetime,
    ) -> tuple[ClaimState, list[ClaimLifecycleTransition], str, None]:
        confidence, update = self._confidence_aggregator.reinforce(
            existing=existing,
            claim=claim,
            modality=modality,
        )
        state = existing.model_copy(
            update={
                "confidence": confidence,
                "validation_results": [*existing.validation_results, *validation_results],
                "evidence_spans": [*existing.evidence_spans, *claim.evidence_spans],
                "confidence_history": [*existing.confidence_history, update],
                "updated_at": now,
            }
        )
        transition = ClaimLifecycleTransition(
            transition_id=stable_evolution_id("transition", f"{existing.claim_id}:reinforce:{claim.claim_id}"),
            transition_type=ClaimTransitionType.REINFORCE,
            claim_id=existing.claim_id,
            related_claim_ids=[claim.claim_id],
            rationale="new claim reinforces existing active claim",
        )
        record = record_from_claim_state(state=state, source_candidate_id=claim.extraction_run_id)
        self._memory_plane.upsert_record(record)
        return state, [transition], record.memory_id, None

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
                "conflict_with_claim_ids": sorted({*old_state.conflict_with_claim_ids, superseded_by_claim_id}),
                "valid_to": valid_to,
                "updated_at": self._now_provider(),
            }
        )
        record = record_from_claim_state(state=updated, source_candidate_id=updated.source_claim_id)
        self._memory_plane.upsert_record(record)
