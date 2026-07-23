"""Runtime graph to latent oracle alignment helpers."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RuntimeGraphAlignmentVerdict(StrEnum):
    ALIGNED = "aligned"
    PARTIAL = "partial"
    UNMATCHED_RUNTIME = "unmatched_runtime"
    MISSING_EXPECTED = "missing_expected"
    AMBIGUOUS_ALIGNMENT = "ambiguous_alignment"


class RuntimeGraphAlignment(BaseModel):
    runtime_item_id: str | None = None
    oracle_item_id: str | None = None
    item_type: str
    verdict: RuntimeGraphAlignmentVerdict
    score: float = Field(ge=0.0, le=1.0)
    matched_on: list[str] = Field(default_factory=list)
    rationale: str

    model_config = ConfigDict(extra="forbid")


def normalize_alignment_value(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def align_by_normalized_fields(
    *,
    runtime_item_id: str,
    oracle_item_id: str,
    item_type: str,
    runtime_fields: dict[str, str | None],
    oracle_fields: dict[str, str | None],
    required_fields: list[str],
) -> RuntimeGraphAlignment:
    matched = [field for field in required_fields if normalize_alignment_value(runtime_fields.get(field)) == normalize_alignment_value(oracle_fields.get(field))]
    if len(matched) == len(required_fields):
        verdict = RuntimeGraphAlignmentVerdict.ALIGNED
    elif matched:
        verdict = RuntimeGraphAlignmentVerdict.PARTIAL
    else:
        verdict = RuntimeGraphAlignmentVerdict.UNMATCHED_RUNTIME
    return RuntimeGraphAlignment(
        runtime_item_id=runtime_item_id,
        oracle_item_id=oracle_item_id,
        item_type=item_type,
        verdict=verdict,
        score=len(matched) / max(1, len(required_fields)),
        matched_on=matched,
        rationale=f"matched {len(matched)} of {len(required_fields)} required fields",
    )


def align_entity_by_fields(
    *,
    runtime_item_id: str,
    oracle_item_id: str,
    runtime_fields: dict[str, object],
    oracle_fields: dict[str, object],
) -> RuntimeGraphAlignment:
    runtime_names = _name_set(runtime_fields.get("canonical_name"), runtime_fields.get("aliases"))
    oracle_names = _name_set(oracle_fields.get("canonical_name"), oracle_fields.get("aliases"))
    name_match = bool(runtime_names & oracle_names)
    type_match = normalize_alignment_value(_as_str(runtime_fields.get("entity_type"))) == normalize_alignment_value(_as_str(oracle_fields.get("entity_type")))
    evidence_match = _list_overlap(runtime_fields.get("evidence_event_ids"), oracle_fields.get("evidence_event_ids"))
    matched = []
    if name_match:
        matched.append("canonical_name_or_alias")
    if type_match:
        matched.append("entity_type")
    if evidence_match:
        matched.append("alias_evidence")
    return _alignment_from_matches(
        runtime_item_id=runtime_item_id,
        oracle_item_id=oracle_item_id,
        item_type="entity",
        matched=matched,
        required_count=2,
        rationale="entity alignment uses canonical/alias identity plus entity type; evidence overlap is supporting signal",
    )


def align_claim_by_fields(
    *,
    runtime_item_id: str,
    oracle_item_id: str,
    runtime_fields: dict[str, object],
    oracle_fields: dict[str, object],
) -> RuntimeGraphAlignment:
    required = ["subject", "predicate", "object", "scope"]
    matched = [
        field
        for field in required
        if normalize_alignment_value(_as_str(runtime_fields.get(field))) == normalize_alignment_value(_as_str(oracle_fields.get(field)))
    ]
    runtime_time = normalize_alignment_value(_as_str(runtime_fields.get("valid_time") or runtime_fields.get("valid_from")))
    oracle_time = normalize_alignment_value(_as_str(oracle_fields.get("valid_time") or oracle_fields.get("valid_from")))
    if runtime_time and oracle_time and runtime_time == oracle_time:
        matched.append("valid_time")
    return _alignment_from_matches(
        runtime_item_id=runtime_item_id,
        oracle_item_id=oracle_item_id,
        item_type="claim",
        matched=matched,
        required_count=len(required),
        rationale="claim alignment uses subject, predicate, object, scope, and optional valid-time agreement",
    )


def align_relation_by_fields(
    *,
    runtime_item_id: str,
    oracle_item_id: str,
    runtime_fields: dict[str, object],
    oracle_fields: dict[str, object],
) -> RuntimeGraphAlignment:
    required = ["source", "target", "relation_type", "directionality"]
    matched = [
        field
        for field in required
        if normalize_alignment_value(_as_str(runtime_fields.get(field))) == normalize_alignment_value(_as_str(oracle_fields.get(field)))
    ]
    return _alignment_from_matches(
        runtime_item_id=runtime_item_id,
        oracle_item_id=oracle_item_id,
        item_type="relation",
        matched=matched,
        required_count=len(required),
        rationale="relation alignment is directional and requires endpoint/type agreement",
    )


def align_evidence_by_fields(
    *,
    runtime_item_id: str,
    oracle_item_id: str,
    runtime_fields: dict[str, object],
    oracle_fields: dict[str, object],
) -> RuntimeGraphAlignment:
    source_match = normalize_alignment_value(_as_str(runtime_fields.get("source_event_id"))) == normalize_alignment_value(_as_str(oracle_fields.get("source_event_id")))
    quote_score = _quote_overlap(_as_str(runtime_fields.get("quote")) or "", _as_str(oracle_fields.get("quote")) or "")
    matched = []
    if source_match:
        matched.append("source_event_id")
    if quote_score >= 0.5:
        matched.append("quote_overlap")
    alignment = _alignment_from_matches(
        runtime_item_id=runtime_item_id,
        oracle_item_id=oracle_item_id,
        item_type="evidence",
        matched=matched,
        required_count=2,
        rationale=f"evidence alignment uses source event id and quote token overlap={quote_score:.2f}",
    )
    if source_match and 0.0 < quote_score < 0.5:
        return alignment.model_copy(update={"verdict": RuntimeGraphAlignmentVerdict.PARTIAL, "score": max(alignment.score, 0.5)})
    return alignment


def _alignment_from_matches(
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


def _name_set(canonical: object, aliases: object) -> set[str]:
    names = {normalize_alignment_value(_as_str(canonical))}
    if isinstance(aliases, list):
        names.update(normalize_alignment_value(_as_str(item)) for item in aliases)
    names.discard("")
    return names


def _list_overlap(left: object, right: object) -> bool:
    if not isinstance(left, list) or not isinstance(right, list):
        return False
    return bool({normalize_alignment_value(_as_str(item)) for item in left} & {normalize_alignment_value(_as_str(item)) for item in right})


def _quote_overlap(left: str, right: str) -> float:
    left_tokens = set(normalize_alignment_value(left).split())
    right_tokens = set(normalize_alignment_value(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _as_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
