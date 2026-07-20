"""Runtime graph-to-oracle alignment helpers."""

from __future__ import annotations

from memorii.core.benchmark.memory_evolution_runtime.models import RuntimeGraphItemRow
from memorii.core.benchmark.memory_evolution_sim import (
    LatentClaim,
    LatentEntity,
    LatentGraphScenario,
    LatentRelation,
    ObservabilityLabel,
)
from memorii.core.calibration.alignment import (
    RuntimeGraphAlignment,
    RuntimeGraphAlignmentVerdict,
    align_entity_by_fields,
    align_relation_by_fields,
    normalize_alignment_value,
)


def align_runtime_graph_to_oracle(
    *, scenario: LatentGraphScenario, graph_items: list[RuntimeGraphItemRow]
) -> list[RuntimeGraphAlignment]:
    alignments: list[RuntimeGraphAlignment] = []
    runtime_entities = [item for item in graph_items if item.item_type == "entity"]
    runtime_claims = [item for item in graph_items if item.item_type == "claim"]
    runtime_relations = [item for item in graph_items if item.item_type == "relation"]
    runtime_entity_by_canonical_id = {
        item.canonical_id: item for item in runtime_entities if item.canonical_id
    }
    oracle_entity_by_id = {entity.entity_id: entity for entity in scenario.entities if entity.observability != ObservabilityLabel.HIDDEN}
    for runtime in runtime_entities:
        best = _best_alignment([
            align_entity_by_fields(
                runtime_item_id=runtime.runtime_item_id,
                oracle_item_id=entity.entity_id,
                runtime_fields=_runtime_entity_fields(runtime),
                oracle_fields=_oracle_entity_fields(entity),
            )
            for entity in oracle_entity_by_id.values()
        ])
        alignments.append(best or RuntimeGraphAlignment(runtime_item_id=runtime.runtime_item_id, item_type="entity", verdict=RuntimeGraphAlignmentVerdict.UNMATCHED_RUNTIME, score=0.0, rationale="no oracle entity candidates"))
    for runtime in runtime_claims:
        direct = next((claim for claim in scenario.claims if claim.claim_id == runtime.claim_id and claim.observability != ObservabilityLabel.HIDDEN), None)
        if direct is not None:
            evidence_ids = set(runtime.evidence_event_ids)
            oracle_evidence_ids = {span.event_id for span in direct.evidence.spans}
            has_provenance = bool(evidence_ids & oracle_evidence_ids)
            alignments.append(RuntimeGraphAlignment(
                runtime_item_id=runtime.runtime_item_id,
                oracle_item_id=direct.claim_id,
                item_type="claim",
                verdict=RuntimeGraphAlignmentVerdict.ALIGNED if has_provenance else RuntimeGraphAlignmentVerdict.PARTIAL,
                score=1.0 if has_provenance else 0.8,
                matched_on=["claim_id", "evidence_event_ids"] if has_provenance else ["claim_id"],
                rationale="runtime claim id and provenance match latent claim" if has_provenance else "claim id matches but provenance is missing",
            ))
            continue
        best = _best_alignment([
            _align_claim_with_entity_context(
                runtime=runtime,
                oracle_claim=claim,
                runtime_entity_by_canonical_id=runtime_entity_by_canonical_id,
                oracle_entity_by_id=oracle_entity_by_id,
            )
            for claim in scenario.claims
            if claim.observability != ObservabilityLabel.HIDDEN
        ])
        alignments.append(best or RuntimeGraphAlignment(runtime_item_id=runtime.runtime_item_id, item_type="claim", verdict=RuntimeGraphAlignmentVerdict.UNMATCHED_RUNTIME, score=0.0, rationale="no oracle claim candidates"))
    for runtime in runtime_relations:
        best = _best_alignment([
            align_relation_by_fields(
                runtime_item_id=runtime.runtime_item_id,
                oracle_item_id=relation.relation_id,
                runtime_fields=_runtime_relation_fields(runtime),
                oracle_fields=_oracle_relation_fields(relation),
            )
            for relation in scenario.relations
            if relation.observability != ObservabilityLabel.HIDDEN
        ])
        if best is not None:
            alignments.append(best)
    alignments = _enforce_one_to_one_alignment(alignments)
    for entity in scenario.entities:
        if entity.observability != ObservabilityLabel.HIDDEN and not any(a.oracle_item_id == entity.entity_id and a.item_type == "entity" for a in alignments):
            alignments.append(RuntimeGraphAlignment(oracle_item_id=entity.entity_id, item_type="entity", verdict=RuntimeGraphAlignmentVerdict.MISSING_EXPECTED, score=0.0, rationale="oracle entity missing from runtime graph"))
    for claim in scenario.claims:
        if claim.observability != ObservabilityLabel.HIDDEN and not any(a.oracle_item_id == claim.claim_id and a.item_type == "claim" for a in alignments):
            alignments.append(RuntimeGraphAlignment(oracle_item_id=claim.claim_id, item_type="claim", verdict=RuntimeGraphAlignmentVerdict.MISSING_EXPECTED, score=0.0, rationale="oracle claim missing from runtime graph"))
    return alignments

def _align_claim_with_entity_context(
    *,
    runtime: RuntimeGraphItemRow,
    oracle_claim: LatentClaim,
    runtime_entity_by_canonical_id: dict[str, RuntimeGraphItemRow],
    oracle_entity_by_id: dict[str, LatentEntity],
) -> RuntimeGraphAlignment:
    matched: list[str] = []
    runtime_item_id = runtime.runtime_item_id
    subject_entity = oracle_entity_by_id.get(oracle_claim.subject.entity_id)
    object_entity = oracle_entity_by_id.get(oracle_claim.object.entity_id) if oracle_claim.object.entity_id else None
    if subject_entity is not None and _runtime_claim_entity_matches(
        runtime_entity_id=runtime.subject_entity_id,
        runtime_name=runtime.subject,
        runtime_entities_by_canonical_id=runtime_entity_by_canonical_id,
        oracle_entity=subject_entity,
    ):
        matched.append("subject_entity")
    if normalize_alignment_value(runtime.predicate) == normalize_alignment_value(oracle_claim.predicate.predicate_id):
        matched.append("predicate")
    if _runtime_claim_object_matches(
        runtime=runtime,
        oracle_claim=oracle_claim,
        object_entity=object_entity,
        runtime_entity_by_canonical_id=runtime_entity_by_canonical_id,
    ):
        matched.append("object")
    if normalize_alignment_value(runtime.scope) == normalize_alignment_value(oracle_claim.scope.scope_key):
        matched.append("scope")
    if set(runtime.evidence_event_ids) & {span.event_id for span in oracle_claim.evidence.spans}:
        matched.append("evidence_event_ids")
    alignment = _runtime_alignment_from_matches(
        runtime_item_id=runtime_item_id,
        oracle_item_id=oracle_claim.claim_id,
        item_type="claim",
        matched=matched,
        required_count=5,
        rationale="claim alignment requires subject, predicate, object, scope, and provenance",
    )
    return alignment

def _runtime_alignment_from_matches(
    *,
    runtime_item_id: str,
    oracle_item_id: str,
    item_type: str,
    matched: list[str],
    required_count: int,
    rationale: str,
) -> RuntimeGraphAlignment:
    required_matches = min(len(matched), required_count)
    if required_matches >= required_count:
        verdict = RuntimeGraphAlignmentVerdict.ALIGNED
    elif required_matches > 0:
        verdict = RuntimeGraphAlignmentVerdict.PARTIAL
    else:
        verdict = RuntimeGraphAlignmentVerdict.UNMATCHED_RUNTIME
    return RuntimeGraphAlignment(
        runtime_item_id=runtime_item_id,
        oracle_item_id=oracle_item_id,
        item_type=item_type,
        verdict=verdict,
        score=required_matches / max(1, required_count),
        matched_on=matched,
        rationale=rationale,
    )

def _runtime_claim_object_matches(
    *,
    runtime: RuntimeGraphItemRow,
    oracle_claim: LatentClaim,
    object_entity: LatentEntity | None,
    runtime_entity_by_canonical_id: dict[str, RuntimeGraphItemRow],
) -> bool:
    runtime_value = runtime.object_value or runtime.object
    if normalize_alignment_value(runtime_value) == normalize_alignment_value(oracle_claim.object.value):
        return True
    if object_entity is None:
        return False
    return _runtime_claim_entity_matches(
        runtime_entity_id=runtime.object_entity_id,
        runtime_name=runtime.object or runtime_value,
        runtime_entities_by_canonical_id=runtime_entity_by_canonical_id,
        oracle_entity=object_entity,
    )

def _runtime_claim_entity_matches(
    *,
    runtime_entity_id: str,
    runtime_name: str,
    runtime_entities_by_canonical_id: dict[str, RuntimeGraphItemRow],
    oracle_entity: LatentEntity,
) -> bool:
    runtime_entity = runtime_entities_by_canonical_id.get(runtime_entity_id)
    runtime_names = _runtime_entity_names(runtime_entity=runtime_entity, fallback_name=runtime_name, fallback_entity_id=runtime_entity_id)
    oracle_names = _oracle_entity_names(oracle_entity)
    if runtime_names & oracle_names:
        return True
    runtime_type = normalize_alignment_value(runtime_entity.entity_type if runtime_entity else "unknown")
    oracle_type = normalize_alignment_value(oracle_entity.entity_type)
    if runtime_type not in {"", "unknown", oracle_type}:
        return False
    if oracle_type and runtime_type not in {"", "unknown", oracle_type}:
        return False
    return _runtime_names_are_safe_alias(runtime_names=runtime_names, oracle_names=oracle_names, oracle_type=oracle_type)

def _runtime_entity_names(
    *, runtime_entity: RuntimeGraphItemRow | None, fallback_name: str, fallback_entity_id: str
) -> set[str]:
    names = {
        normalize_alignment_value(fallback_name),
        normalize_alignment_value(runtime_entity.canonical_name if runtime_entity else ""),
        normalize_alignment_value(
            (runtime_entity.canonical_id if runtime_entity else fallback_entity_id)
            .replace("ent:", "")
            .replace("-", " ")
        ),
    }
    if runtime_entity is not None:
        names.update(normalize_alignment_value(alias) for alias in runtime_entity.aliases)
    names.discard("")
    return names

def _oracle_entity_names(entity: LatentEntity) -> set[str]:
    names = {normalize_alignment_value(entity.canonical_name)}
    names.update(normalize_alignment_value(alias.alias_text) for alias in entity.aliases)
    names.add(normalize_alignment_value(entity.entity_id.replace("ent_", "").replace("_", " ")))
    names.discard("")
    return names

def _runtime_names_are_safe_alias(*, runtime_names: set[str], oracle_names: set[str], oracle_type: str) -> bool:
    if oracle_type == "service":
        return False
    for runtime_name in runtime_names:
        if "service" in runtime_name.split():
            continue
        for oracle_name in oracle_names:
            if not oracle_name or len(oracle_name) < 4:
                continue
            if runtime_name.startswith(f"{oracle_name} ") or runtime_name.endswith(f" {oracle_name}"):
                return True
    return False

def best_alignment_map(alignments: list[RuntimeGraphAlignment], *, item_type: str) -> dict[str, RuntimeGraphAlignment]:
    result: dict[str, RuntimeGraphAlignment] = {}
    for alignment in alignments:
        if alignment.item_type != item_type or alignment.oracle_item_id is None:
            continue
        if alignment.verdict != RuntimeGraphAlignmentVerdict.ALIGNED:
            continue
        existing = result.get(alignment.oracle_item_id)
        if existing is None or alignment.score > existing.score:
            result[alignment.oracle_item_id] = alignment
    return result

def _best_alignment(alignments: list[RuntimeGraphAlignment]) -> RuntimeGraphAlignment | None:
    if not alignments:
        return None
    alignments = sorted(alignments, key=lambda item: (item.score, item.verdict == RuntimeGraphAlignmentVerdict.ALIGNED), reverse=True)
    best = alignments[0]
    if len(alignments) > 1 and best.score == alignments[1].score and best.score > 0.0 and best.oracle_item_id != alignments[1].oracle_item_id:
        return best.model_copy(update={"verdict": RuntimeGraphAlignmentVerdict.AMBIGUOUS_ALIGNMENT, "rationale": f"ambiguous alignment between {best.oracle_item_id} and {alignments[1].oracle_item_id}"})
    return best


def _enforce_one_to_one_alignment(alignments: list[RuntimeGraphAlignment]) -> list[RuntimeGraphAlignment]:
    """Prevent duplicate runtime items from inflating oracle recall."""

    winners: dict[tuple[str, str], RuntimeGraphAlignment] = {}
    for alignment in alignments:
        if alignment.verdict != RuntimeGraphAlignmentVerdict.ALIGNED or alignment.oracle_item_id is None:
            continue
        key = (alignment.item_type, alignment.oracle_item_id)
        current = winners.get(key)
        if current is None or (alignment.score, str(alignment.runtime_item_id)) > (current.score, str(current.runtime_item_id)):
            winners[key] = alignment
    winner_ids = {id(alignment) for alignment in winners.values()}
    result: list[RuntimeGraphAlignment] = []
    for alignment in alignments:
        if alignment.verdict != RuntimeGraphAlignmentVerdict.ALIGNED or alignment.oracle_item_id is None:
            result.append(alignment)
            continue
        if id(alignment) in winner_ids:
            result.append(alignment)
            continue
        result.append(alignment.model_copy(update={
            "oracle_item_id": None,
            "verdict": RuntimeGraphAlignmentVerdict.UNMATCHED_RUNTIME,
            "score": 0.0,
            "rationale": "duplicate runtime item competes for an already aligned oracle item",
        }))
    return result

def _oracle_entity_fields(entity: LatentEntity) -> dict[str, object]:
    return {
        "canonical_name": entity.canonical_name,
        "aliases": [alias.alias_text for alias in entity.aliases],
        "entity_type": entity.entity_type,
        "evidence_event_ids": [span.event_id for span in entity.evidence_spans],
    }


def _runtime_entity_fields(item: RuntimeGraphItemRow) -> dict[str, object]:
    return {
        "canonical_name": item.canonical_name,
        "aliases": item.aliases,
        "entity_type": item.entity_type,
        "evidence_event_ids": item.evidence_event_ids,
    }

def _oracle_claim_fields(claim: LatentClaim) -> dict[str, object]:
    return {
        "subject": claim.subject.canonical_name,
        "predicate": claim.predicate.predicate_id,
        "object": claim.object.value,
        "scope": claim.scope.scope_key,
        "valid_from": claim.lifecycle.valid_from.isoformat() if claim.lifecycle.valid_from else "",
    }

def _oracle_relation_fields(relation: LatentRelation) -> dict[str, object]:
    return {
        "source": relation.source.endpoint_id,
        "target": relation.target.endpoint_id,
        "relation_type": relation.relation_type,
        "directionality": relation.directionality,
    }


def _runtime_relation_fields(item: RuntimeGraphItemRow) -> dict[str, object]:
    return {
        "source": item.source,
        "target": item.target,
        "relation_type": item.relation_type,
        "directionality": item.directionality,
    }
