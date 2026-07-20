"""Conservative extraction provider for runtime memory evolution."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.memory_evolution.language import supports_english_rules
from memorii.core.memory_evolution.models import (
    ClaimKey,
    ConfidenceComponents,
    EntityMention,
    EntityType,
    EvidenceSpan,
    ExtractedAction,
    ExtractedClaim,
    ExtractionRun,
    SourceObservation,
    memory_scope_from_observation,
)
from memorii.core.prompts.registry import PromptRegistry, default_prompt_root
from memorii.core.prompts.runtime_manifest import PromptOwner


class MemoryExtractor(Protocol):
    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str | None: ...

    @property
    def prompt_hash(self) -> str | None: ...

    def extract(
        self, observations: list[SourceObservation]
    ) -> tuple[ExtractionRun, list[EntityMention], list[ExtractedClaim], list[ExtractedAction]]: ...


class ExtractedEntityOutput(BaseModel):
    entity_id: str
    mention_text: str
    normalized_name: str
    aliases: list[str]
    entity_type: EntityType
    source_id: str
    quote: str
    confidence: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class EmptyQualifiersOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtractedClaimOutput(BaseModel):
    claim_id: str
    subject_entity_id: str
    predicate_id: Literal[
        "owner",
        "approver",
        "api_owner",
        "status",
        "preference",
        "dependency",
        "action_state",
        "belief",
        "correction",
        "entity_type",
        "semantic_fact",
    ]
    object_value: str
    object_entity_id: str | None
    scope_key: str
    qualifier_key: str
    qualifiers: EmptyQualifiersOutput
    valid_from: str | None
    valid_to: str | None
    source_id: str
    quote: str
    confidence: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class ExtractedActionOutput(BaseModel):
    action_id: str
    actor_entity_id: str | None
    action_type: str
    target_entity_ids: list[str]
    status: str
    dependency_ids: list[str]
    blocking_ids: list[str]
    timestamp: str | None
    source_id: str
    quote: str

    model_config = ConfigDict(extra="forbid")


class MemoryExtractionOutput(BaseModel):
    entities: list[ExtractedEntityOutput]
    claims: list[ExtractedClaimOutput]
    actions: list[ExtractedActionOutput]

    model_config = ConfigDict(extra="forbid")


class EnglishRuleMemoryExtractor:
    """English-only fallback extractor for simple facts/actions.

    The production path can swap in an LLM extractor later; this provider gives
    deterministic coverage for source-linked facts and safe fallback behavior.
    """

    provider: str = "english_rule"
    model: str | None = None
    prompt_hash: str | None = None

    def extract(
        self, observations: list[SourceObservation]
    ) -> tuple[ExtractionRun, list[EntityMention], list[ExtractedClaim], list[ExtractedAction]]:
        run_id = _stable_id("extraction", "|".join(obs.source_id for obs in observations))
        entities: dict[tuple[str, str, str], EntityMention] = {}
        claims: list[ExtractedClaim] = []
        actions: list[ExtractedAction] = []
        errors: list[str] = []

        for observation in observations:
            if not supports_english_rules(observation.language):
                errors.append(
                    f"{observation.source_id}: unsupported_language:{observation.language}"
                )
                continue
            try:
                obs_entities, obs_claims, obs_actions = self._extract_observation(
                    run_id=run_id, observation=observation
                )
            except ValueError as exc:
                errors.append(f"{observation.source_id}: {exc}")
                continue
            for entity in obs_entities:
                key = (entity.entity_id, entity.normalized_name, entity.scope.scope_key)
                entities.setdefault(key, entity)
            claims.extend(obs_claims)
            actions.extend(obs_actions)

        entity_list = list(entities.values())
        claims = _canonicalize_claim_arguments(claims, entity_list)
        run = ExtractionRun(
            extraction_run_id=run_id,
            provider=self.provider,
            model=self.model,
            prompt_hash=self.prompt_hash,
            input_source_ids=[obs.source_id for obs in observations],
            entity_ids=sorted({entity.entity_id for entity in entity_list}),
            claim_ids=[claim.claim_id for claim in claims],
            action_ids=[action.action_id for action in actions],
            validation_summary={},
            errors=errors,
        )
        return run, entity_list, claims, actions

    def _extract_observation(
        self,
        *,
        run_id: str,
        observation: SourceObservation,
    ) -> tuple[list[EntityMention], list[ExtractedClaim], list[ExtractedAction]]:
        text = observation.text.strip()
        entities: list[EntityMention] = []
        claims: list[ExtractedClaim] = []
        actions: list[ExtractedAction] = []
        observation_scope = memory_scope_from_observation(observation)

        for predicate, subject, value, quote in _extract_fact_matches(text):
            subject_entity_id = _entity_id(subject)
            value_entity_id = _entity_id(value) if predicate in {"owner", "approver", "api_owner"} else None
            span = _span(observation=observation, quote=quote)
            entities.append(
                EntityMention(
                    entity_id=subject_entity_id,
                    mention_text=subject,
                    normalized_name=_normalize_name(subject),
                    entity_type=EntityType.UNKNOWN,
                    evidence_spans=[span],
                    confidence=0.7,
                    scope=observation_scope,
                )
            )
            if value_entity_id is not None:
                entities.append(
                    EntityMention(
                        entity_id=value_entity_id,
                        mention_text=value,
                        normalized_name=_normalize_name(value),
                        entity_type=EntityType.PERSON,
                        evidence_spans=[span],
                        confidence=0.7,
                        scope=observation_scope,
                    )
                )
            claims.append(
                ExtractedClaim(
                    claim_id=_stable_id("claim", f"{run_id}:{observation.source_id}:{predicate}:{subject}:{value}"),
                    claim_key=ClaimKey(
                        subject_entity_id=subject_entity_id,
                        predicate_id=predicate,
                        scope_key=observation_scope.scope_key,
                        qualifier_key="default",
                    ),
                    object_value=value,
                    object_entity_id=value_entity_id,
                    valid_from=observation.timestamp,
                    evidence_spans=[span],
                    confidence=_confidence_for_source(observation),
                    extraction_run_id=run_id,
                )
            )

        action_match = re.search(
            r"\b(?P<target>[A-Z][A-Za-z0-9 _:-]+?)\s+(?P<status>started|blocked|resumed|abandoned|completed|failed|succeeded)\b",
            text,
            re.IGNORECASE,
        )
        if action_match:
            target = action_match.group("target").strip()
            status = action_match.group("status").lower()
            span = _span(observation=observation, quote=action_match.group(0))
            actions.append(
                ExtractedAction(
                    action_id=_stable_id("action", f"{run_id}:{observation.source_id}:{target}:{status}"),
                    action_type="work_state",
                    target_entity_ids=[_entity_id(target)],
                    status=status,
                    timestamp=observation.timestamp,
                    task_id=observation.task_id,
                    session_id=observation.session_id,
                    user_id=observation.user_id,
                    scope_key=observation_scope.scope_key,
                    evidence_spans=[span],
                    extraction_run_id=run_id,
                )
            )

        return entities, claims, actions


class LLMMemoryExtractor:
    provider: str = "llm"
    prompt_ref = "memory_extraction:v1"
    output_model = MemoryExtractionOutput

    def __init__(
        self,
        *,
        runner: PromptLLMRunner,
        prompt_root: Path | None = None,
    ) -> None:
        root = prompt_root or default_prompt_root()
        self._runner = runner
        self._registry = PromptRegistry(prompt_root=root)
        self.model: str | None = None
        self.prompt_hash: str | None = None

    def extract(
        self, observations: list[SourceObservation]
    ) -> tuple[ExtractionRun, list[EntityMention], list[ExtractedClaim], list[ExtractedAction]]:
        run_id = _stable_id("extraction", "|".join(obs.source_id for obs in observations))
        contract = self._registry.load(
            self.prompt_ref,
            owner=PromptOwner.LLM_MEMORY_EXTRACTOR,
            output_model=self.output_model,
        )
        result = self._runner.run(
            contract=contract,
            variables={
                "source_observations": [obs.model_dump(mode="json") for obs in observations],
            },
            request_id=f"runtime:memory_extraction:{run_id}",
            metadata={
                "decision_point": "memory_extraction",
                "source_ids": [obs.source_id for obs in observations],
            },
            output_model=self.output_model,
        )
        self.model = result.response.actual_model or result.response.requested_model
        self.prompt_hash = result.request.prompt_hash
        if not result.success or result.output is None:
            errors = [result.failure_mode or "llm_extraction_failed"]
            if result.response.error:
                errors.append(result.response.error)
            run = ExtractionRun(
                extraction_run_id=run_id,
                provider=self.provider,
                model=result.response.actual_model or result.response.requested_model,
                prompt_hash=result.request.prompt_hash,
                input_source_ids=[obs.source_id for obs in observations],
                errors=errors,
            )
            return run, [], [], []
        return models_from_llm_output(
            run_id=run_id,
            provider=self.provider,
            model=result.response.actual_model or result.response.requested_model,
            prompt_hash=result.request.prompt_hash,
            observations=observations,
            output=result.output,
        )


class HybridMemoryExtractor:
    provider: str = "hybrid"

    def __init__(
        self,
        *,
        llm_extractor: MemoryExtractor,
        rule_extractor: EnglishRuleMemoryExtractor | None = None,
    ) -> None:
        self._llm_extractor = llm_extractor
        self._rule_extractor = rule_extractor or EnglishRuleMemoryExtractor()
        self.model: str | None = None
        self.prompt_hash: str | None = None

    def extract(
        self, observations: list[SourceObservation]
    ) -> tuple[ExtractionRun, list[EntityMention], list[ExtractedClaim], list[ExtractedAction]]:
        run, entities, claims, actions = self._llm_extractor.extract(observations)
        self.model = run.model
        self.prompt_hash = run.prompt_hash
        if run.errors:
            fallback_run, fallback_entities, fallback_claims, fallback_actions = self._rule_extractor.extract(
                observations
            )
            fallback_run = fallback_run.model_copy(
                update={
                    "provider": self.provider,
                    "errors": [*run.errors, "fallback_used:english_rule"],
                }
            )
            return fallback_run, fallback_entities, fallback_claims, fallback_actions
        return run.model_copy(update={"provider": self.provider}), entities, claims, actions


def _extract_fact_matches(text: str) -> list[tuple[str, str, str, str]]:
    patterns: list[tuple[str, str]] = [
        (
            "api_owner",
            r"(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)\s+(?:API\s+owner|api\s+owner)\s*(?:is|:|=)\s*(?P<value>[A-Z][A-Za-z0-9 _:-]+)",
        ),
        ("approver", r"(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)\s+approver\s*(?:is|:|=)\s*(?P<value>[A-Z][A-Za-z0-9 _:-]+)"),
        ("owner", r"(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)\s+owner\s*(?:is|:|=)\s*(?P<value>[A-Z][A-Za-z0-9 _:-]+)"),
        (
            "owner",
            r"(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)\s+ownership\s+(?:in\s+\w+\s+)?(?:belonged to|belongs to)\s+(?P<value>[A-Z][A-Za-z0-9 _:-]+)",
        ),
        (
            "owner",
            r"(?P<value>[A-Z][A-Za-z0-9 _:-]+?)\s+owns\s+(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)(?=\s+for now|\s+currently|[.,;]|$)",
        ),
        (
            "owner",
            r"(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)\s+is\s+(?:the\s+)?[A-Za-z0-9 _:-]*?\b(?:project|service|task|workstream)\b\s+owned\s+by\s+(?P<value>[A-Z][A-Za-z0-9 _:-]+)",
        ),
        (
            "entity_type",
            r"(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)\s+is\s+(?:the\s+)?[A-Za-z0-9 _:-]*?\b(?P<value>project|service|task|incident|document|preference)\b",
        ),
        (
            "status",
            r"(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)\s+(?:state|status)\s*(?:is|:|=)\s*(?P<value>failed|succeeded|blocked|running|done|active|inactive)",
        ),
        ("status", r"(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)\s+(?:deploy|deployment)\s+(?P<value>failed|succeeded)"),
        ("preference", r"(?:prefers|preference is|style is)\s+(?P<value>[a-z][A-Za-z0-9 _:-]+)"),
    ]
    matches: list[tuple[str, str, str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for predicate, pattern in patterns:
        for match in re.finditer(pattern, text):
            subject = _clean_extracted_value(match.groupdict().get("subject") or "user")
            value = _clean_extracted_value(match.group("value"))
            quote = match.group(0).strip(" .")
            key = (predicate, subject.lower(), value.lower(), quote.lower())
            if key in seen:
                continue
            seen.add(key)
            matches.append((predicate, subject, value, quote))
    return matches


def _clean_extracted_value(value: str) -> str:
    cleaned = re.sub(r"^(?:the|a|an)\s+", "", value.strip(" .:"), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+for now$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+currently$", "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip(" .:")


def models_from_llm_output(
    *,
    run_id: str,
    provider: str,
    model: str | None,
    prompt_hash: str | None,
    observations: list[SourceObservation],
    output: dict[str, object],
) -> tuple[ExtractionRun, list[EntityMention], list[ExtractedClaim], list[ExtractedAction]]:
    observation_by_id = {obs.source_id: obs for obs in observations}
    errors: list[str] = []
    entities: list[EntityMention] = []
    claims: list[ExtractedClaim] = []
    actions: list[ExtractedAction] = []

    for idx, item in enumerate(_list_output(output, "entities")):
        try:
            source_id = str(item.get("source_id") or "")
            observation = _resolve_observation(source_id=source_id, observation_by_id=observation_by_id)
            span = _span(observation=observation, quote=str(item.get("quote") or item.get("mention_text") or ""))
            observation_scope = memory_scope_from_observation(observation)
            _validate_model_scope(item, observation=observation, scope_key=observation_scope.scope_key)
            entities.append(
                EntityMention(
                    entity_id=str(item["entity_id"]),
                    mention_text=str(item["mention_text"]),
                    normalized_name=str(item.get("normalized_name") or item["mention_text"]).strip().lower(),
                    aliases=[str(alias) for alias in _sequence_output(item.get("aliases"))],
                    entity_type=_entity_type(str(item.get("entity_type") or "unknown")),
                    evidence_spans=[span],
                    confidence=_float_output(item.get("confidence"), default=0.5),
                    scope=observation_scope,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"entity[{idx}]: {type(exc).__name__}:{exc}")

    for idx, item in enumerate(_list_output(output, "claims")):
        try:
            source_id = str(item.get("source_id") or "")
            observation = _resolve_observation(source_id=source_id, observation_by_id=observation_by_id)
            predicate_id = str(item["predicate_id"])
            subject_entity_id = str(item["subject_entity_id"])
            object_value = str(item["object_value"]).strip()
            span = _span(observation=observation, quote=str(item.get("quote") or object_value))
            observation_scope = memory_scope_from_observation(observation)
            _validate_model_scope(item, observation=observation, scope_key=observation_scope.scope_key)
            claim_key = ClaimKey(
                subject_entity_id=subject_entity_id,
                predicate_id=predicate_id,
                scope_key=observation_scope.scope_key,
                qualifier_key=str(item.get("qualifier_key") or "default"),
            )
            confidence = _float_output(item.get("confidence"), default=0.6)
            object_entity_id = str(item["object_entity_id"]) if item.get("object_entity_id") else None
            raw_claim_id = str(item.get("claim_id") or "").strip()
            qualifiers = {str(key): str(value) for key, value in _dict_output(item.get("qualifiers")).items()}
            valid_from, valid_from_normalization = _parse_dt_with_normalization(item.get("valid_from"))
            valid_to, valid_to_normalization = _parse_dt_with_normalization(item.get("valid_to"))
            if valid_from_normalization:
                qualifiers.setdefault("valid_from_date_normalization", valid_from_normalization)
                qualifiers.setdefault("date_normalization", valid_from_normalization)
            if valid_to_normalization:
                qualifiers.setdefault("valid_to_date_normalization", valid_to_normalization)
                qualifiers.setdefault("date_normalization", valid_to_normalization)
            if raw_claim_id:
                qualifiers.setdefault("model_claim_id", raw_claim_id)
            claim_id = _stable_id(
                "claim",
                "|".join(
                    [
                        run_id,
                        observation.source_id,
                        predicate_id,
                        subject_entity_id,
                        object_value,
                        object_entity_id or "",
                        claim_key.scope_key,
                        claim_key.qualifier_key,
                    ]
                ),
            )
            claims.append(
                ExtractedClaim(
                    claim_id=claim_id,
                    claim_key=claim_key,
                    object_value=object_value,
                    object_entity_id=object_entity_id,
                    qualifiers=qualifiers,
                    valid_from=valid_from or observation.timestamp,
                    valid_to=valid_to,
                    evidence_spans=[span],
                    confidence=ConfidenceComponents(
                        extraction=confidence,
                        evidence=0.8 if span.char_start is not None else 0.4,
                        source_trust=_confidence_for_source(observation).source_trust,
                        calibrated=min(
                            1.0,
                            max(0.0, confidence * 0.5 + _confidence_for_source(observation).source_trust * 0.3 + 0.16),
                        ),
                    ),
                    extraction_run_id=run_id,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"claim[{idx}]: {type(exc).__name__}:{exc}")

    for idx, item in enumerate(_list_output(output, "actions")):
        try:
            source_id = str(item.get("source_id") or "")
            observation = _resolve_observation(source_id=source_id, observation_by_id=observation_by_id)
            quote = str(item.get("quote") or item.get("status") or item.get("action_type") or "")
            span = _span(observation=observation, quote=quote)
            action_type = str(item["action_type"])
            target_entity_ids = [str(value) for value in _sequence_output(item.get("target_entity_ids"))]
            status = str(item["status"])
            observation_scope = memory_scope_from_observation(observation)
            _validate_model_scope(item, observation=observation, scope_key=observation_scope.scope_key)
            action_id = _stable_id(
                "action",
                "|".join([run_id, observation.source_id, action_type, "|".join(target_entity_ids), status]),
            )
            actions.append(
                ExtractedAction(
                    action_id=action_id,
                    actor_entity_id=str(item["actor_entity_id"]) if item.get("actor_entity_id") else None,
                    action_type=action_type,
                    target_entity_ids=target_entity_ids,
                    status=status,
                    dependency_ids=[str(value) for value in _sequence_output(item.get("dependency_ids"))],
                    blocking_ids=[str(value) for value in _sequence_output(item.get("blocking_ids"))],
                    timestamp=_parse_dt(item.get("timestamp")) or observation.timestamp,
                    task_id=observation.task_id,
                    session_id=observation.session_id,
                    user_id=observation.user_id,
                    scope_key=observation_scope.scope_key,
                    evidence_spans=[span],
                    extraction_run_id=run_id,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"action[{idx}]: {type(exc).__name__}:{exc}")

    claims = _canonicalize_claim_arguments(claims, entities)
    run = ExtractionRun(
        extraction_run_id=run_id,
        provider=provider,
        model=model,
        prompt_hash=prompt_hash,
        input_source_ids=[obs.source_id for obs in observations],
        entity_ids=[entity.entity_id for entity in entities],
        claim_ids=[claim.claim_id for claim in claims],
        action_ids=[action.action_id for action in actions],
        errors=errors,
    )
    return run, entities, claims, actions


def _canonicalize_claim_arguments(claims: list[ExtractedClaim], entities: list[EntityMention]) -> list[ExtractedClaim]:
    entities_by_id = {entity.entity_id: entity for entity in entities}
    return [_canonicalize_claim_argument(claim, entities_by_id) for claim in claims]


def _canonicalize_claim_argument(claim: ExtractedClaim, entities_by_id: dict[str, EntityMention]) -> ExtractedClaim:
    if claim.claim_key.predicate_id != "owner" or not claim.object_entity_id:
        return claim

    subject = entities_by_id.get(claim.claim_key.subject_entity_id)
    obj = entities_by_id.get(claim.object_entity_id)
    if not _looks_like_inverse_owner_claim(subject=subject, obj=obj):
        return claim

    original_subject_id = claim.claim_key.subject_entity_id
    original_object_entity_id = claim.object_entity_id
    original_object_value = claim.object_value
    object_value = _entity_display_name(subject, fallback=original_subject_id)
    source_id = claim.evidence_spans[0].source_id if claim.evidence_spans else ""
    new_claim_key = claim.claim_key.model_copy(update={"subject_entity_id": original_object_entity_id})
    qualifiers = {
        **claim.qualifiers,
        "argument_normalization": "owner_inverse_subject_object_swap",
        "original_subject_entity_id": original_subject_id,
        "original_object_entity_id": original_object_entity_id,
        "original_object_value": original_object_value,
    }
    claim_id = _stable_id(
        "claim",
        "|".join(
            [
                claim.extraction_run_id,
                source_id,
                new_claim_key.predicate_id,
                new_claim_key.subject_entity_id,
                object_value,
                original_subject_id,
                new_claim_key.scope_key,
                new_claim_key.qualifier_key,
            ]
        ),
    )
    return claim.model_copy(
        update={
            "claim_id": claim_id,
            "claim_key": new_claim_key,
            "object_value": object_value,
            "object_entity_id": original_subject_id,
            "qualifiers": qualifiers,
        }
    )


def _looks_like_inverse_owner_claim(*, subject: EntityMention | None, obj: EntityMention | None) -> bool:
    if subject is None or obj is None:
        return False
    owner_types = {EntityType.PERSON}
    owned_types = {EntityType.PROJECT, EntityType.SERVICE, EntityType.TASK, EntityType.PREFERENCE}
    return subject.entity_type in owner_types and obj.entity_type in owned_types


def _entity_display_name(entity: EntityMention | None, *, fallback: str) -> str:
    if entity is not None and entity.mention_text.strip():
        return entity.mention_text.strip()
    return fallback.removeprefix("ent:").replace("-", " ").title()


def _resolve_observation(*, source_id: str, observation_by_id: dict[str, SourceObservation]) -> SourceObservation:
    observation = observation_by_id.get(source_id)
    if observation is not None:
        return observation
    if len(observation_by_id) == 1:
        return next(iter(observation_by_id.values()))
    raise KeyError(source_id)


def _validate_model_scope(
    item: Mapping[str, object],
    *,
    observation: SourceObservation,
    scope_key: str,
) -> None:
    expected = {
        "scope_key": scope_key,
        "task_id": observation.task_id,
        "session_id": observation.session_id,
        "user_id": observation.user_id,
    }
    for field_name, expected_value in expected.items():
        supplied = item.get(field_name)
        if supplied not in {None, ""} and (expected_value is None or str(supplied) != expected_value):
            raise ValueError(f"model supplied {field_name} outside the source observation scope")


def _list_output(output: dict[str, object], key: str) -> list[dict[str, object]]:
    value = output.get(key, [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dict_output(value: object) -> Mapping[object, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence_output(value: object) -> Sequence[object]:
    return value if isinstance(value, Sequence) and not isinstance(value, str) else ()


def _float_output(value: object, *, default: float) -> float:
    if isinstance(value, (int, float, str)):
        return float(value)
    return default


def _entity_type(value: str) -> EntityType:
    try:
        return EntityType(value)
    except ValueError:
        return EntityType.UNKNOWN


def _parse_dt(value: object) -> datetime | None:
    parsed, _ = _parse_dt_with_normalization(value)
    return parsed


def _parse_dt_with_normalization(value: object) -> tuple[datetime | None, str | None]:
    if value in {None, ""}:
        return None, None
    if isinstance(value, datetime):
        return (value if value.tzinfo is not None else value.replace(tzinfo=UTC)), None
    if isinstance(value, str):
        stripped = value.strip()
        quarter_match = re.fullmatch(r"(\d{4})-Q([1-4])", stripped, flags=re.IGNORECASE)
        if quarter_match:
            year = int(quarter_match.group(1))
            month = {"1": 1, "2": 4, "3": 7, "4": 10}[quarter_match.group(2)]
            return datetime(year, month, 1, tzinfo=UTC), "quarter_start"
        parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        return (parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)), None
    return None, None


def _span(*, observation: SourceObservation, quote: str) -> EvidenceSpan:
    start = observation.text.lower().find(quote.lower())
    end = start + len(quote) if start >= 0 else None
    return EvidenceSpan(
        source_id=observation.source_id,
        quote=quote,
        char_start=start if start >= 0 else None,
        char_end=end,
        source_type=observation.source_type,
        timestamp=observation.timestamp,
    )


def _confidence_for_source(observation: SourceObservation) -> ConfidenceComponents:
    trust = {
        "user": 0.95,
        "tool": 0.9,
        "environment": 0.9,
        "derived": 0.75,
        "agent": 0.7,
        "system": 0.65,
    }.get(observation.source_type.value, 0.6)
    evidence = 0.85
    extraction = 0.65
    calibrated = round((trust * 0.4) + (evidence * 0.35) + (extraction * 0.25), 4)
    return ConfidenceComponents(
        extraction=extraction,
        evidence=evidence,
        source_trust=trust,
        agreement=0.0,
        contradiction=0.0,
        calibrated=calibrated,
    )


def _entity_id(value: str) -> str:
    return f"ent:{_normalize_name(value).replace(' ', '-')}"


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip(" .:")).lower()


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}:{uuid5(NAMESPACE_URL, value)}"
