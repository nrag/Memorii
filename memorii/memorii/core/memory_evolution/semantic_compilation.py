"""State-aware deterministic compilation of extraction proposals."""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.memory_evolution.entity_resolution import EntityResolutionService
from memorii.core.memory_evolution.extraction_contracts import MemoryExtractionProposal
from memorii.core.memory_evolution.language_support import (
    DEFAULT_EXTRACTION_LANGUAGE_REGISTRY,
    ExtractionLanguageRegistry,
)
from memorii.core.memory_evolution.models import (
    ClaimAssertionMode,
    ClaimEpistemicStatus,
    ClaimKey,
    ClaimLifecycleTransition,
    ClaimModality,
    ClaimPolarity,
    ClaimSemanticContext,
    ConfidenceComponents,
    EntityLinkState,
    EntityResolutionOutcome,
    EvidenceSpan,
    ExtractedAction,
    ExtractedClaim,
    ExtractedIdentityRelation,
    SourceObservation,
    ValidationResult,
    ValidationVerdict,
)
from memorii.core.memory_evolution.mutations import MemoryEvolutionMutationValidationError
from memorii.core.memory_evolution.source_grounding import ground_extraction_candidates
from memorii.core.memory_evolution.validation import MemoryEvolutionValidator


class SemanticCompilationResult(BaseModel):
    """Canonical proposal ready for atomic persistence and graph projection."""

    proposal: MemoryExtractionProposal
    entity_resolution: EntityResolutionOutcome
    claims: list[ExtractedClaim] = Field(default_factory=list)
    actions: list[ExtractedAction] = Field(default_factory=list)
    identity_relations: list[ExtractedIdentityRelation] = Field(default_factory=list)
    validation_results: dict[str, list[ValidationResult]] = Field(default_factory=dict)
    transitions: list[ClaimLifecycleTransition] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True, extra="forbid")


class SemanticIngestionCompiler:
    """Compile one provider proposal against the latest committed entity state."""

    def __init__(
        self,
        *,
        entity_resolver: EntityResolutionService,
        validator: MemoryEvolutionValidator,
        language_registry: ExtractionLanguageRegistry = DEFAULT_EXTRACTION_LANGUAGE_REGISTRY,
    ) -> None:
        self._entity_resolver = entity_resolver
        self._validator = validator
        self._language_registry = language_registry

    def compile(
        self,
        *,
        proposal: MemoryExtractionProposal,
        observations: list[SourceObservation],
        existing_entity_links: list[EntityLinkState],
    ) -> SemanticCompilationResult:
        grounding = ground_extraction_candidates(
            entities=proposal.entities,
            claims=proposal.claims,
            actions=proposal.actions,
            identity_relations=proposal.identity_relations,
            observations=observations,
            language_registry=self._language_registry,
            allow_argument_reversal=False,
        )
        contract_errors = [
            *_identity_relation_contract_errors(proposal),
            *grounding.errors,
        ]
        if contract_errors:
            raise MemoryEvolutionMutationValidationError(contract_errors)
        proposal = proposal.model_copy(
            update={
                "entities": grounding.entities,
                "claims": grounding.claims,
                "actions": grounding.actions,
                "identity_relations": grounding.identity_relations,
            }
        )
        entity_resolution = self._entity_resolver.resolve_mentions(
            proposal.entities,
            existing_entity_links,
            identity_relations=proposal.identity_relations,
        )
        unresolved_ids = {
            decision.mention_entity_id
            for decision in entity_resolution.decisions
            if decision.resolved_entity_id is None
        }
        errors = _unresolved_reference_errors(
            claims=proposal.claims,
            actions=proposal.actions,
            identity_relations=proposal.identity_relations,
            unresolved_entity_ids=unresolved_ids,
        )
        if errors:
            raise MemoryEvolutionMutationValidationError(errors)

        references = self._entity_resolver.canonical_reference_map(entity_resolution)
        claims: list[ExtractedClaim] = []
        transitions = list(entity_resolution.transitions)
        for claim in proposal.claims:
            canonical, transition = self._entity_resolver.canonicalize_claim_entities(
                claim=claim,
                references=references,
            )
            claims.append(canonical)
            if transition is not None:
                transitions.append(transition)
        actions = [
            self._entity_resolver.canonicalize_action_entities(
                action=action,
                references=references,
            )
            for action in proposal.actions
        ]
        identity_relations = [
            _canonicalize_identity_relation(relation, references) for relation in proposal.identity_relations
        ]

        claims, actions = _compile_action_state_pairs(
            claims=claims,
            actions=actions,
            observations=observations,
        )
        claims, diagnostics = _suppress_redundant_semantic_facts(
            claims=claims,
            identity_relations=identity_relations,
        )
        validation_results = self._validator.validate_claims(
            claims=claims,
            observations=observations,
        )
        for claim in claims:
            if claim.claim_key.predicate_id != "semantic_fact":
                continue
            validation_results.setdefault(claim.claim_id, []).append(
                ValidationResult(
                    validator_name="semantic_fact_promotion_gate",
                    verdict=ValidationVerdict.FAIL,
                    score=0.0,
                    evidence_spans=list(claim.evidence_spans),
                    rationale=(
                        "generic semantic facts remain evidence-only until a typed "
                        "promotion policy represents their semantics"
                    ),
                )
            )

        return SemanticCompilationResult(
            proposal=proposal,
            entity_resolution=entity_resolution,
            claims=claims,
            actions=actions,
            identity_relations=identity_relations,
            validation_results=validation_results,
            transitions=transitions,
            diagnostics=diagnostics,
        )


def _compile_action_state_pairs(
    *,
    claims: list[ExtractedClaim],
    actions: list[ExtractedAction],
    observations: list[SourceObservation],
) -> tuple[list[ExtractedClaim], list[ExtractedAction]]:
    observation_by_id = {observation.source_id: observation for observation in observations}
    compiled_claims = list(claims)
    compiled_actions = list(actions)

    action_claims = [claim for claim in compiled_claims if claim.claim_key.predicate_id == "action_state"]
    for claim in action_claims:
        matches = [
            action
            for action in compiled_actions
            if claim.claim_key.subject_entity_id in action.target_entity_ids
            and _normalized_status(action.status) == _normalized_status(claim.object_value)
            and _source_ids(action.evidence_spans) & _source_ids(claim.evidence_spans)
        ]
        conflicts = [
            action
            for action in compiled_actions
            if claim.claim_key.subject_entity_id in action.target_entity_ids
            and _source_ids(action.evidence_spans) & _source_ids(claim.evidence_spans)
            and _normalized_status(action.status) != _normalized_status(claim.object_value)
        ]
        if conflicts:
            raise MemoryEvolutionMutationValidationError(
                [f"conflicting_action_state:{claim.claim_id}:{conflicts[0].action_id}"]
            )
        if matches:
            continue
        source_id = next(iter(sorted(_source_ids(claim.evidence_spans))), None)
        observation = observation_by_id.get(source_id or "")
        compiled_actions.append(
            ExtractedAction(
                action_id=_stable_id("action", f"{claim.claim_id}:compiled"),
                action_type="work_state",
                target_entity_ids=[claim.claim_key.subject_entity_id],
                status=_normalized_status(claim.object_value),
                timestamp=(observation.timestamp if observation is not None else claim.evidence_spans[0].timestamp),
                scope=claim.claim_key.scope,
                evidence_spans=list(claim.evidence_spans),
                extraction_run_id=claim.extraction_run_id,
            )
        )

    for action in list(compiled_actions):
        matching_claims = [
            claim
            for claim in action_claims
            if claim.claim_key.subject_entity_id in action.target_entity_ids
            and _normalized_status(claim.object_value) == _normalized_status(action.status)
            and _source_ids(claim.evidence_spans) & _source_ids(action.evidence_spans)
        ]
        if matching_claims:
            continue
        if not action.target_entity_ids or not action.evidence_spans:
            raise MemoryEvolutionMutationValidationError([f"ungrounded_action_state:{action.action_id}"])
        target_entity_id = action.target_entity_ids[0]
        compiled_claims.append(
            ExtractedClaim(
                claim_id=_stable_id("claim", f"{action.action_id}:action-state"),
                claim_key=ClaimKey(
                    subject_entity_id=target_entity_id,
                    predicate_id="action_state",
                    scope=action.scope,
                    qualifier_key="default",
                    assertion_mode=ClaimAssertionMode.WORLD_ASSERTION,
                    epistemic_status=ClaimEpistemicStatus.ASSERTED,
                    polarity=ClaimPolarity.POSITIVE,
                    modality=ClaimModality.ASSERTION,
                ),
                object_value=_normalized_status(action.status),
                semantic_context=ClaimSemanticContext(
                    assertion_mode=ClaimAssertionMode.WORLD_ASSERTION,
                    epistemic_status=ClaimEpistemicStatus.ASSERTED,
                    polarity=ClaimPolarity.POSITIVE,
                    modality=ClaimModality.ASSERTION,
                    attribution_source_id=action.evidence_spans[0].source_id,
                ),
                valid_from=action.timestamp,
                evidence_spans=list(action.evidence_spans),
                confidence=ConfidenceComponents(
                    extraction=0.8,
                    evidence=0.8,
                    source_trust=0.8,
                    calibrated=0.8,
                ),
                extraction_run_id=action.extraction_run_id,
            )
        )
    return compiled_claims, compiled_actions


def _suppress_redundant_semantic_facts(
    *,
    claims: list[ExtractedClaim],
    identity_relations: list[ExtractedIdentityRelation],
) -> tuple[list[ExtractedClaim], list[str]]:
    typed_keys = {
        (
            claim.claim_key.subject_entity_id,
            _normalized_status(claim.object_value),
            tuple(sorted(_source_ids(claim.evidence_spans))),
        )
        for claim in claims
        if claim.claim_key.predicate_id != "semantic_fact"
    }
    explicit_identity_sources = {
        (
            relation.source_entity_id,
            tuple(sorted(_source_ids(relation.evidence_spans))),
        )
        for relation in identity_relations
    }
    retained: list[ExtractedClaim] = []
    diagnostics: list[str] = []
    for claim in claims:
        if claim.claim_key.predicate_id != "semantic_fact":
            retained.append(claim)
            continue
        source_ids = tuple(sorted(_source_ids(claim.evidence_spans)))
        key = (
            claim.claim_key.subject_entity_id,
            _normalized_status(claim.object_value),
            source_ids,
        )
        identity_key = (claim.claim_key.subject_entity_id, source_ids)
        if key in typed_keys or identity_key in explicit_identity_sources:
            diagnostics.append(f"suppressed_redundant_semantic_fact:{claim.claim_id}")
            continue
        retained.append(claim)
    return retained, diagnostics


def _canonicalize_identity_relation(
    relation: ExtractedIdentityRelation,
    references: dict[tuple[str, tuple[str | None, str | None, str | None]], str],
) -> ExtractedIdentityRelation:
    scope_identity = relation.scope.identity
    return relation.model_copy(
        update={
            "source_entity_id": references.get(
                (relation.source_entity_id, scope_identity),
                relation.source_entity_id,
            ),
            "target_entity_id": references.get(
                (relation.target_entity_id, scope_identity),
                relation.target_entity_id,
            ),
        }
    )


def _unresolved_reference_errors(
    *,
    claims: list[ExtractedClaim],
    actions: list[ExtractedAction],
    identity_relations: list[ExtractedIdentityRelation],
    unresolved_entity_ids: set[str],
) -> list[str]:
    if not unresolved_entity_ids:
        return []
    errors: list[str] = []
    for claim in claims:
        references = {
            claim.claim_key.subject_entity_id,
            *([claim.object_entity_id] if claim.object_entity_id is not None else []),
        }
        for entity_id in sorted(references & unresolved_entity_ids):
            errors.append(f"unresolved_entity_reference:claim:{claim.claim_id}:{entity_id}")
    for action in actions:
        references = {
            *action.target_entity_ids,
            *action.dependency_entity_ids,
            *action.blocking_entity_ids,
            *([action.actor_entity_id] if action.actor_entity_id is not None else []),
        }
        for entity_id in sorted(references & unresolved_entity_ids):
            errors.append(f"unresolved_entity_reference:action:{action.action_id}:{entity_id}")
    for relation in identity_relations:
        references = {relation.source_entity_id, relation.target_entity_id}
        for entity_id in sorted(references & unresolved_entity_ids):
            errors.append(f"unresolved_entity_reference:identity_relation:{relation.relation_id}:{entity_id}")
    return errors


def _identity_relation_contract_errors(proposal: MemoryExtractionProposal) -> list[str]:
    entity_keys = {(entity.entity_id, entity.scope.identity) for entity in proposal.entities}
    source_counts: dict[tuple[str, tuple[str | None, str | None, str | None]], int] = {}
    errors: list[str] = []
    for relation in proposal.identity_relations:
        source_key = (relation.source_entity_id, relation.scope.identity)
        target_key = (relation.target_entity_id, relation.scope.identity)
        source_counts[source_key] = source_counts.get(source_key, 0) + 1
        if source_key not in entity_keys:
            errors.append(f"identity_relation_source_not_declared:{relation.relation_id}")
        if target_key not in entity_keys:
            errors.append(f"identity_relation_target_not_declared:{relation.relation_id}")
        if relation.source_entity_id == relation.target_entity_id:
            errors.append(f"identity_relation_self_reference:{relation.relation_id}")
        if not relation.evidence_spans:
            errors.append(f"identity_relation_missing_evidence:{relation.relation_id}")
    errors.extend(
        f"multiple_identity_relations_for_source:{entity_id}:{'|'.join(value or '' for value in scope_identity)}"
        for (entity_id, scope_identity), count in sorted(source_counts.items())
        if count > 1
    )
    return errors


def _source_ids(evidence_spans: list[EvidenceSpan]) -> set[str]:
    return {span.source_id for span in evidence_spans}


def _normalized_status(value: str) -> str:
    return "_".join(value.strip().casefold().replace("-", " ").split())


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}:{uuid5(NAMESPACE_URL, value)}"
