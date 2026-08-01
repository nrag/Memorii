"""Authoritative source-grounding policy for extraction proposals."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from memorii.core.memory_evolution.language_support import (
    DEFAULT_EXTRACTION_LANGUAGE_REGISTRY,
    ArgumentOrder,
    ExtractionLanguageRegistry,
    SourceEvidence,
)
from memorii.core.memory_evolution.models import (
    EntityMention,
    EntityType,
    EvidenceSpan,
    ExtractedAction,
    ExtractedClaim,
    ExtractedIdentityRelation,
    SourceObservation,
)

ENTITY_RELATION_PREDICATES = frozenset({"owner", "approver", "api_owner", "dependency"})


@dataclass(frozen=True)
class SourceGroundingResult:
    """Grounded candidates plus deterministic diagnostics for rejected proposals."""

    entities: list[EntityMention]
    claims: list[ExtractedClaim]
    actions: list[ExtractedAction]
    identity_relations: list[ExtractedIdentityRelation]
    errors: list[str]
    capability_ids: frozenset[str]


def ground_extraction_candidates(
    *,
    entities: list[EntityMention],
    claims: list[ExtractedClaim],
    actions: list[ExtractedAction],
    identity_relations: list[ExtractedIdentityRelation],
    observations: list[SourceObservation],
    language_registry: ExtractionLanguageRegistry = DEFAULT_EXTRACTION_LANGUAGE_REGISTRY,
    allow_argument_reversal: bool,
) -> SourceGroundingResult:
    """Compile every candidate against one language-owned evidence policy.

    The provider may propose structure, but it cannot establish source meaning.
    This function is the sole semantic authority for entity mentions, claims,
    actions, and identity relations before state-aware compilation.
    """

    observation_by_id = {observation.source_id: observation for observation in observations}
    errors: list[str] = []
    capability_ids: set[str] = set()

    grounded_entities: list[EntityMention] = []
    for index, entity in enumerate(entities):
        try:
            evidence, capability = _candidate_evidence(
                evidence_spans=entity.evidence_spans,
                observation_by_id=observation_by_id,
                language_registry=language_registry,
            )
            capability_ids.add(capability.capability_id)
            decision = capability.verify_entity_mention(evidence=evidence, entity_name=entity.mention_text)
            if not decision.supported:
                raise ValueError(f"entity mention is not source-grounded:{decision.verdict.value}:{decision.rationale}")
            grounded_entities.append(entity)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"entity[{index}]: {type(exc).__name__}:{exc}")

    entities_by_id = {entity.entity_id: entity for entity in grounded_entities}
    known_names = tuple(entity.mention_text for entity in grounded_entities)
    inferred_types: dict[str, set[EntityType]] = {}

    grounded_claims: list[ExtractedClaim] = []
    for index, claim in enumerate(claims):
        try:
            evidence, capability = _candidate_evidence(
                evidence_spans=claim.evidence_spans,
                observation_by_id=observation_by_id,
                language_registry=language_registry,
            )
            capability_ids.add(capability.capability_id)
            predicate_id = claim.claim_key.predicate_id
            subject = entities_by_id[claim.claim_key.subject_entity_id]
            grounded_claim = claim
            if predicate_id == "entity_type":
                if claim.object_entity_id is not None:
                    raise ValueError("entity_type requires a literal object")
                try:
                    declared_type = EntityType(claim.object_value.strip().casefold())
                except ValueError as exc:
                    raise ValueError(f"unsupported entity_type value:{claim.object_value!r}") from exc
                decision = capability.verify_entity_type(
                    evidence=evidence,
                    entity_name=subject.mention_text,
                    entity_type=declared_type.value,
                    known_entity_names=known_names,
                )
                if not decision.supported:
                    raise ValueError(
                        "entity_type declaration is not semantically grounded"
                        f":{decision.verdict.value}:{decision.rationale}"
                    )
                inferred_types.setdefault(subject.entity_id, set()).add(declared_type)
            elif predicate_id in ENTITY_RELATION_PREDICATES:
                if claim.object_entity_id is None:
                    raise ValueError(f"{predicate_id} requires a grounded object_entity_ref")
                object_entity = entities_by_id[claim.object_entity_id]
                decision = capability.verify_relation(
                    evidence=evidence,
                    predicate_id=predicate_id,
                    subject_name=subject.mention_text,
                    object_name=object_entity.mention_text,
                    known_entity_names=known_names,
                )
                if not decision.supported:
                    raise ValueError(
                        "relation semantics are not grounded in source evidence"
                        f":{decision.verdict.value}:{decision.rationale}"
                    )
                if decision.argument_order == ArgumentOrder.REVERSED:
                    if not allow_argument_reversal:
                        raise ValueError("relation arguments are not in canonical semantic order")
                    grounded_claim = _reverse_relation_arguments(claim, subject=subject)
                subject_type, object_type = capability.inferred_entity_types(predicate_id)
                if subject_type is not None:
                    inferred_types.setdefault(grounded_claim.claim_key.subject_entity_id, set()).add(
                        EntityType(subject_type)
                    )
                if object_type is not None and grounded_claim.object_entity_id is not None:
                    inferred_types.setdefault(grounded_claim.object_entity_id, set()).add(EntityType(object_type))
            else:
                if claim.object_entity_id is not None and predicate_id != "semantic_fact":
                    raise ValueError(f"literal predicate {predicate_id!r} cannot reference an object entity")
                object_value = (
                    entities_by_id[claim.object_entity_id].mention_text
                    if claim.object_entity_id is not None
                    else claim.object_value
                )
                decision = capability.verify_literal_claim(
                    evidence=evidence,
                    predicate_id=predicate_id,
                    subject_name=subject.mention_text,
                    object_value=object_value,
                    known_entity_names=known_names,
                )
                if not decision.supported:
                    raise ValueError(
                        "literal claim semantics are not source-grounded"
                        f":{decision.verdict.value}:{decision.rationale}"
                    )
            grounded_claims.append(grounded_claim)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"claim[{index}]: {type(exc).__name__}:{exc}")

    grounded_entities = _apply_inferred_types(grounded_entities, inferred_types, errors)
    entities_by_id = {entity.entity_id: entity for entity in grounded_entities}

    grounded_relations: list[ExtractedIdentityRelation] = []
    for index, relation in enumerate(identity_relations):
        try:
            evidence, capability = _candidate_evidence(
                evidence_spans=relation.evidence_spans,
                observation_by_id=observation_by_id,
                language_registry=language_registry,
            )
            capability_ids.add(capability.capability_id)
            decision = capability.verify_identity_relation(
                evidence=evidence,
                relation_type=relation.relation_type.value,
                source_name=entities_by_id[relation.source_entity_id].mention_text,
                target_name=entities_by_id[relation.target_entity_id].mention_text,
                known_entity_names=known_names,
            )
            if not decision.supported:
                raise ValueError(
                    "identity relation is not semantically grounded"
                    f":{decision.verdict.value}:{decision.rationale}"
                )
            grounded_relations.append(relation)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"identity_relation[{index}]: {type(exc).__name__}:{exc}")

    grounded_actions: list[ExtractedAction] = []
    for index, action in enumerate(actions):
        try:
            evidence, capability = _candidate_evidence(
                evidence_spans=action.evidence_spans,
                observation_by_id=observation_by_id,
                language_registry=language_registry,
            )
            capability_ids.add(capability.capability_id)
            decision = capability.verify_action(
                evidence=evidence,
                action_type=action.action_type,
                status=action.status,
                target_names=tuple(entities_by_id[entity_id].mention_text for entity_id in action.target_entity_ids),
                actor_name=(
                    entities_by_id[action.actor_entity_id].mention_text
                    if action.actor_entity_id is not None
                    else None
                ),
                dependency_names=tuple(
                    entities_by_id[entity_id].mention_text for entity_id in action.dependency_entity_ids
                ),
                blocking_names=tuple(
                    entities_by_id[entity_id].mention_text for entity_id in action.blocking_entity_ids
                ),
                known_entity_names=known_names,
            )
            if not decision.supported:
                raise ValueError(
                    "action semantics are not source-grounded"
                    f":{decision.verdict.value}:{decision.rationale}"
                )
            grounded_actions.append(action)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"action[{index}]: {type(exc).__name__}:{exc}")

    return SourceGroundingResult(
        entities=grounded_entities,
        claims=grounded_claims,
        actions=grounded_actions,
        identity_relations=grounded_relations,
        errors=errors,
        capability_ids=frozenset(capability_ids),
    )


def _candidate_evidence(
    *,
    evidence_spans: list[EvidenceSpan],
    observation_by_id: dict[str, SourceObservation],
    language_registry: ExtractionLanguageRegistry,
):
    if len(evidence_spans) != 1:
        raise ValueError("candidate requires exactly one source-local evidence span")
    span = evidence_spans[0]
    observation = observation_by_id.get(span.source_id)
    if observation is None:
        raise KeyError(f"unknown evidence source:{span.source_id!r}")
    if span.char_start is None or span.char_end is None:
        first = observation.text.find(span.quote)
        if first < 0:
            raise ValueError("candidate evidence quote is not verbatim in its source")
        if observation.text.find(span.quote, first + 1) >= 0:
            raise ValueError("candidate evidence quote is ambiguous without character offsets")
        char_start, char_end = first, first + len(span.quote)
    else:
        char_start, char_end = span.char_start, span.char_end
    capability = language_registry.resolve(observation.language)
    if capability is None:
        raise ValueError(f"unsupported_language:{observation.language}")
    return (
        SourceEvidence(
            source_text=observation.text,
            quote=span.quote,
            char_start=char_start,
            char_end=char_end,
        ),
        capability,
    )


def _apply_inferred_types(
    entities: list[EntityMention],
    inferred_types: dict[str, set[EntityType]],
    errors: list[str],
) -> list[EntityMention]:
    grounded: list[EntityMention] = []
    for entity in entities:
        types = inferred_types.get(entity.entity_id, set()) - {EntityType.UNKNOWN}
        if len(types) > 1:
            errors.append(
                f"entity[{entity.entity_id}]: ValueError:conflicting source-grounded entity types:"
                f"{sorted(item.value for item in types)!r}"
            )
            grounded.append(entity)
        elif types:
            grounded.append(entity.model_copy(update={"entity_type": next(iter(types))}))
        else:
            grounded.append(entity)
    return grounded


def _reverse_relation_arguments(claim: ExtractedClaim, *, subject: EntityMention) -> ExtractedClaim:
    if claim.object_entity_id is None:
        raise ValueError("cannot reverse a literal relation")
    original_subject_id = claim.claim_key.subject_entity_id
    original_object_id = claim.object_entity_id
    object_value = subject.mention_text.strip() or original_subject_id
    source_id = claim.evidence_spans[0].source_id
    claim_key = claim.claim_key.model_copy(update={"subject_entity_id": original_object_id})
    claim_id = _stable_id(
        "claim",
        "|".join(
            [
                claim.extraction_run_id,
                source_id,
                claim_key.predicate_id,
                claim_key.subject_entity_id,
                object_value,
                original_subject_id,
                claim_key.scope.stable_id(),
                claim_key.qualifier_key,
            ]
        ),
    )
    return claim.model_copy(
        update={
            "claim_id": claim_id,
            "claim_key": claim_key,
            "object_value": object_value,
            "object_entity_id": original_subject_id,
            "qualifiers": {
                **claim.qualifiers,
                "argument_normalization": "semantic_inverse_subject_object_swap",
                "original_subject_entity_id": original_subject_id,
                "original_object_entity_id": original_object_id,
                "original_object_value": claim.object_value,
            },
        }
    )


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}:{uuid5(NAMESPACE_URL, value)}"
