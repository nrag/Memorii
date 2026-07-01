"""Conservative extraction provider for runtime memory evolution."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid5, NAMESPACE_URL

from memorii.core.llm_provider.runner import PromptLLMRunner
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
)
from memorii.core.prompts.registry import PromptRegistry


class MemoryExtractor(Protocol):
    provider: str
    model: str | None
    prompt_hash: str | None

    def extract(self, observations: list[SourceObservation]) -> tuple[ExtractionRun, list[EntityMention], list[ExtractedClaim], list[ExtractedAction]]: ...


class RuleMemoryExtractor:
    """Fallback extractor for simple facts/actions.

    The production path can swap in an LLM extractor later; this provider gives
    deterministic coverage for source-linked facts and safe fallback behavior.
    """

    provider = "rule"
    model = None
    prompt_hash = None

    def extract(self, observations: list[SourceObservation]) -> tuple[ExtractionRun, list[EntityMention], list[ExtractedClaim], list[ExtractedAction]]:
        run_id = _stable_id("extraction", "|".join(obs.source_id for obs in observations))
        entities: dict[str, EntityMention] = {}
        claims: list[ExtractedClaim] = []
        actions: list[ExtractedAction] = []
        errors: list[str] = []

        for observation in observations:
            try:
                obs_entities, obs_claims, obs_actions = self._extract_observation(run_id=run_id, observation=observation)
            except ValueError as exc:
                errors.append(f"{observation.source_id}: {exc}")
                continue
            for entity in obs_entities:
                entities.setdefault(entity.entity_id, entity)
            claims.extend(obs_claims)
            actions.extend(obs_actions)

        run = ExtractionRun(
            extraction_run_id=run_id,
            provider=self.provider,
            model=self.model,
            prompt_hash=self.prompt_hash,
            input_source_ids=[obs.source_id for obs in observations],
            entity_ids=sorted(entities),
            claim_ids=[claim.claim_id for claim in claims],
            action_ids=[action.action_id for action in actions],
            validation_summary={},
            errors=errors,
        )
        return run, list(entities.values()), claims, actions

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
                    )
                )
            claims.append(
                ExtractedClaim(
                    claim_id=_stable_id("claim", f"{run_id}:{observation.source_id}:{predicate}:{subject}:{value}"),
                    claim_key=ClaimKey(
                        subject_entity_id=subject_entity_id,
                        predicate_id=predicate,
                        scope_key=observation.task_id or "global",
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

        action_match = re.search(r"\b(?P<target>[A-Z][A-Za-z0-9 _:-]+?)\s+(?P<status>started|blocked|resumed|abandoned|completed|failed|succeeded)\b", text, re.IGNORECASE)
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
                    evidence_spans=[span],
                    extraction_run_id=run_id,
                )
            )

        return entities, claims, actions


class LLMMemoryExtractor:
    provider = "llm"

    def __init__(
        self,
        *,
        runner: PromptLLMRunner,
        prompt_root: Path | None = None,
    ) -> None:
        root = prompt_root or Path(__file__).resolve().parents[2] / "prompts"
        self._runner = runner
        self._registry = PromptRegistry(prompt_root=root)
        self.model: str | None = None
        self.prompt_hash: str | None = None

    def extract(self, observations: list[SourceObservation]) -> tuple[ExtractionRun, list[EntityMention], list[ExtractedClaim], list[ExtractedAction]]:
        run_id = _stable_id("extraction", "|".join(obs.source_id for obs in observations))
        contract = self._registry.load("memory_extraction:v1")
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
        )
        self.model = result.response.model
        self.prompt_hash = result.request.prompt_hash
        if not result.success or result.output is None:
            run = ExtractionRun(
                extraction_run_id=run_id,
                provider=self.provider,
                model=result.response.model,
                prompt_hash=result.request.prompt_hash,
                input_source_ids=[obs.source_id for obs in observations],
                errors=[result.failure_mode or "llm_extraction_failed"],
            )
            return run, [], [], []
        return _models_from_llm_output(
            run_id=run_id,
            provider=self.provider,
            model=result.response.model,
            prompt_hash=result.request.prompt_hash,
            observations=observations,
            output=result.output,
        )


class HybridMemoryExtractor:
    provider = "hybrid"

    def __init__(
        self,
        *,
        llm_extractor: MemoryExtractor,
        rule_extractor: RuleMemoryExtractor | None = None,
    ) -> None:
        self._llm_extractor = llm_extractor
        self._rule_extractor = rule_extractor or RuleMemoryExtractor()
        self.model: str | None = None
        self.prompt_hash: str | None = None

    def extract(self, observations: list[SourceObservation]) -> tuple[ExtractionRun, list[EntityMention], list[ExtractedClaim], list[ExtractedAction]]:
        run, entities, claims, actions = self._llm_extractor.extract(observations)
        self.model = run.model
        self.prompt_hash = run.prompt_hash
        if run.errors:
            fallback_run, fallback_entities, fallback_claims, fallback_actions = self._rule_extractor.extract(observations)
            fallback_run = fallback_run.model_copy(
                update={
                    "provider": self.provider,
                    "errors": [*run.errors, "fallback_used:rule"],
                }
            )
            return fallback_run, fallback_entities, fallback_claims, fallback_actions
        return run.model_copy(update={"provider": self.provider}), entities, claims, actions


def _extract_fact_matches(text: str) -> list[tuple[str, str, str, str]]:
    patterns: list[tuple[str, str]] = [
        ("api_owner", r"(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)\s+(?:API\s+owner|api\s+owner)\s*(?:is|:)\s*(?P<value>[A-Z][A-Za-z0-9 _:-]+)"),
        ("approver", r"(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)\s+approver\s*(?:is|:)\s*(?P<value>[A-Z][A-Za-z0-9 _:-]+)"),
        ("owner", r"(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)\s+owner\s*(?:is|:)\s*(?P<value>[A-Z][A-Za-z0-9 _:-]+)"),
        ("owner", r"(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)\s+ownership\s+(?:in\s+\w+\s+)?(?:belonged to|belongs to)\s+(?P<value>[A-Z][A-Za-z0-9 _:-]+)"),
        ("status", r"(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)\s+(?:state|status)\s*(?:is|:)\s*(?P<value>failed|succeeded|blocked|running|done|active|inactive)"),
        ("status", r"(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)\s+(?:deploy|deployment)\s+(?P<value>failed|succeeded)"),
        ("preference", r"(?:prefers|preference is|style is)\s+(?P<value>[a-z][A-Za-z0-9 _:-]+)"),
    ]
    matches: list[tuple[str, str, str, str]] = []
    for predicate, pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            subject = match.groupdict().get("subject") or "user"
            value = match.group("value").strip(" .")
            quote = match.group(0).strip(" .")
            matches.append((predicate, subject.strip(" ."), value, quote))
    return matches


def _models_from_llm_output(
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
            observation = observation_by_id[source_id]
            span = _span(observation=observation, quote=str(item.get("quote") or item.get("mention_text") or ""))
            entities.append(
                EntityMention(
                    entity_id=str(item["entity_id"]),
                    mention_text=str(item["mention_text"]),
                    normalized_name=str(item.get("normalized_name") or item["mention_text"]).strip().lower(),
                    entity_type=_entity_type(str(item.get("entity_type") or "unknown")),
                    evidence_spans=[span],
                    confidence=float(item.get("confidence", 0.5)),
                )
            )
        except Exception as exc:
            errors.append(f"entity[{idx}]: {type(exc).__name__}")

    for idx, item in enumerate(_list_output(output, "claims")):
        try:
            source_id = str(item.get("source_id") or "")
            observation = observation_by_id[source_id]
            predicate_id = str(item["predicate_id"])
            subject_entity_id = str(item["subject_entity_id"])
            object_value = str(item["object_value"]).strip()
            span = _span(observation=observation, quote=str(item.get("quote") or object_value))
            claim_key = ClaimKey(
                subject_entity_id=subject_entity_id,
                predicate_id=predicate_id,
                scope_key=str(item.get("scope_key") or observation.task_id or "global"),
                qualifier_key=str(item.get("qualifier_key") or "default"),
            )
            confidence = float(item.get("confidence", 0.6))
            claims.append(
                ExtractedClaim(
                    claim_id=str(item.get("claim_id") or _stable_id("claim", f"{run_id}:{source_id}:{predicate_id}:{subject_entity_id}:{object_value}")),
                    claim_key=claim_key,
                    object_value=object_value,
                    object_entity_id=str(item["object_entity_id"]) if item.get("object_entity_id") else None,
                    qualifiers={str(key): str(value) for key, value in dict(item.get("qualifiers") or {}).items()},
                    valid_from=_parse_dt(item.get("valid_from")) or observation.timestamp,
                    valid_to=_parse_dt(item.get("valid_to")),
                    evidence_spans=[span],
                    confidence=ConfidenceComponents(
                        extraction=confidence,
                        evidence=0.8 if span.char_start is not None else 0.4,
                        source_trust=_confidence_for_source(observation).source_trust,
                        calibrated=min(1.0, max(0.0, confidence * 0.5 + _confidence_for_source(observation).source_trust * 0.3 + 0.16)),
                    ),
                    extraction_run_id=run_id,
                )
            )
        except Exception as exc:
            errors.append(f"claim[{idx}]: {type(exc).__name__}")

    for idx, item in enumerate(_list_output(output, "actions")):
        try:
            source_id = str(item.get("source_id") or "")
            observation = observation_by_id[source_id]
            quote = str(item.get("quote") or item.get("status") or item.get("action_type") or "")
            span = _span(observation=observation, quote=quote)
            actions.append(
                ExtractedAction(
                    action_id=str(item.get("action_id") or _stable_id("action", f"{run_id}:{source_id}:{item.get('action_type')}:{item.get('status')}")),
                    actor_entity_id=str(item["actor_entity_id"]) if item.get("actor_entity_id") else None,
                    action_type=str(item["action_type"]),
                    target_entity_ids=[str(value) for value in item.get("target_entity_ids", [])],
                    status=str(item["status"]),
                    dependency_ids=[str(value) for value in item.get("dependency_ids", [])],
                    blocking_ids=[str(value) for value in item.get("blocking_ids", [])],
                    timestamp=_parse_dt(item.get("timestamp")) or observation.timestamp,
                    evidence_spans=[span],
                    extraction_run_id=run_id,
                )
            )
        except Exception as exc:
            errors.append(f"action[{idx}]: {type(exc).__name__}")

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


def _list_output(output: dict[str, object], key: str) -> list[dict[str, object]]:
    value = output.get(key, [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _entity_type(value: str) -> EntityType:
    try:
        return EntityType(value)
    except ValueError:
        return EntityType.UNKNOWN


def _parse_dt(value: object) -> datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return None


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
