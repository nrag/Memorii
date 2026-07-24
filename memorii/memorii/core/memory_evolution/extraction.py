"""Conservative extraction provider for runtime memory evolution."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.memory_evolution.extraction_contracts import MemoryExtractionOutput, MemoryExtractor
from memorii.core.memory_evolution.extraction_identity import normalize_extracted_name as _normalize_name
from memorii.core.memory_evolution.extraction_identity import stable_entity_id as _entity_id
from memorii.core.memory_evolution.extraction_identity import stable_extraction_id as _stable_id
from memorii.core.memory_evolution.language import supports_english_rules
from memorii.core.memory_evolution.models import (
    ClaimKey,
    ConfidenceComponents,
    EntityMention,
    EntityType,
    EvidenceSpan,
    ExtractedAction,
    ExtractedClaim,
    ExtractionFailureCode,
    ExtractionRun,
    ExtractionRunStatus,
    FallbackOutcome,
    FinalExtractionSource,
    ProviderAttemptStatus,
    SourceObservation,
    memory_scope_from_observation,
)
from memorii.core.prompts.registry import PromptRegistry, default_prompt_root
from memorii.core.prompts.runtime_manifest import PromptOwner


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
        if not observations:
            return _deterministic_abstention(
                provider=self.provider,
                model=self.model,
                prompt_hash=self.prompt_hash,
            )
        run_id = _stable_id("extraction", "|".join(obs.source_id for obs in observations))
        entities: dict[tuple[str, str, str], EntityMention] = {}
        claims: list[ExtractedClaim] = []
        actions: list[ExtractedAction] = []
        errors: list[str] = []

        for observation in observations:
            if not supports_english_rules(observation.language):
                errors.append(f"{observation.source_id}: unsupported_language:{observation.language}")
                continue
            try:
                obs_entities, obs_claims, obs_actions = self._extract_observation(
                    run_id=run_id, observation=observation
                )
            except ValueError as exc:
                errors.append(f"{observation.source_id}: {exc}")
                continue
            for entity in obs_entities:
                key = (entity.entity_id, entity.normalized_name, entity.scope.stable_id())
                entities.setdefault(key, entity)
            claims.extend(obs_claims)
            actions.extend(obs_actions)

        entity_list = list(entities.values())
        claims = _canonicalize_claim_arguments(claims, entity_list)
        if errors:
            status = ExtractionRunStatus.PARTIAL if entity_list or claims or actions else ExtractionRunStatus.ABSTAINED
            failure_code = (
                ExtractionFailureCode.UNSUPPORTED_LANGUAGE
                if all("unsupported_language:" in error for error in errors)
                else ExtractionFailureCode.OUTPUT_VALIDATION
            )
        else:
            status = ExtractionRunStatus.SUCCEEDED
            failure_code = None
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
            status=status,
            failure_code=failure_code,
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
                        scope=observation_scope,
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
                    scope=observation_scope,
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
        if not observations:
            return _deterministic_abstention(
                provider=self.provider,
                model=self.model,
                prompt_hash=self.prompt_hash,
            )
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
            failure_mode = result.failure_mode or "output_validation"
            failure_code = {
                "provider_error": ExtractionFailureCode.PROVIDER_ERROR,
                "invalid_json": ExtractionFailureCode.INVALID_JSON,
                "schema_validation": ExtractionFailureCode.SCHEMA_VALIDATION,
            }.get(failure_mode, ExtractionFailureCode.OUTPUT_VALIDATION)
            errors = [failure_mode]
            if result.response.error:
                errors.append(result.response.error)
            run = ExtractionRun(
                extraction_run_id=run_id,
                provider=self.provider,
                model=result.response.actual_model or result.response.requested_model,
                prompt_hash=result.request.prompt_hash,
                input_source_ids=[obs.source_id for obs in observations],
                status=ExtractionRunStatus.FAILED,
                provider_attempt_status={
                    ExtractionFailureCode.PROVIDER_ERROR: ProviderAttemptStatus.PROVIDER_ERROR,
                    ExtractionFailureCode.INVALID_JSON: ProviderAttemptStatus.INVALID_JSON,
                    ExtractionFailureCode.SCHEMA_VALIDATION: ProviderAttemptStatus.SCHEMA_ERROR,
                }.get(failure_code, ProviderAttemptStatus.SUCCEEDED),
                final_output_source=FinalExtractionSource.NONE,
                failure_code=failure_code,
                primary_failure_code=failure_code,
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
        if run.status in {ExtractionRunStatus.FAILED, ExtractionRunStatus.PARTIAL}:
            fallback_run, fallback_entities, fallback_claims, fallback_actions = self._rule_extractor.extract(
                observations
            )
            if fallback_run.status != ExtractionRunStatus.SUCCEEDED:
                failed_run = run.model_copy(
                    update={
                        "status": ExtractionRunStatus.FAILED,
                        "fallback_outcome": FallbackOutcome.FAILED,
                        "fallback_provider": self._rule_extractor.provider,
                        "final_output_source": FinalExtractionSource.NONE,
                        "failure_code": fallback_run.failure_code or run.failure_code,
                        "errors": [
                            *run.errors,
                            *fallback_run.errors,
                            f"fallback_failed:{fallback_run.status.value}",
                        ],
                    }
                )
                return failed_run, [], [], []
            fallback_run = fallback_run.model_copy(
                update={
                    "provider": self.provider,
                    "provider_attempt_status": run.provider_attempt_status,
                    "primary_failure_code": run.failure_code,
                    "fallback_outcome": FallbackOutcome.SUCCEEDED,
                    "final_output_source": FinalExtractionSource.FALLBACK,
                    "fallback_provider": self._rule_extractor.provider,
                    "errors": [*run.errors, "fallback_used:english_rule"],
                }
            )
            return fallback_run, fallback_entities, fallback_claims, fallback_actions
        return run.model_copy(update={"provider": self.provider}), entities, claims, actions


def _deterministic_abstention(
    *,
    provider: str,
    model: str | None,
    prompt_hash: str | None,
) -> tuple[ExtractionRun, list[EntityMention], list[ExtractedClaim], list[ExtractedAction]]:
    return (
        ExtractionRun(
            extraction_run_id=_stable_id("extraction", ""),
            provider=provider,
            model=model,
            prompt_hash=prompt_hash,
            input_source_ids=[],
            status=ExtractionRunStatus.ABSTAINED,
            provider_attempt_status=ProviderAttemptStatus.NOT_ATTEMPTED,
            final_output_source=FinalExtractionSource.NONE,
        ),
        [],
        [],
        [],
    )


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
    if len(observation_by_id) != len(observations):
        run = ExtractionRun(
            extraction_run_id=run_id,
            provider=provider,
            model=model,
            prompt_hash=prompt_hash,
            input_source_ids=[obs.source_id for obs in observations],
            status=ExtractionRunStatus.FAILED,
            provider_attempt_status=ProviderAttemptStatus.SUCCEEDED,
            final_output_source=FinalExtractionSource.NONE,
            failure_code=ExtractionFailureCode.OUTPUT_VALIDATION,
            validation_summary={
                "input_validation_errors": 1,
                "entity_binding_errors": 0,
                "claim_binding_errors": 0,
                "action_binding_errors": 0,
            },
            errors=["input: ValueError:source observation IDs must be unique"],
        )
        return run, [], [], []

    entity_items = _list_output(output, "entities")
    entity_id_by_ref: dict[str, str] = {}
    for idx, item in enumerate(entity_items):
        try:
            source_id = str(item.get("source_id") or "")
            observation = _resolve_observation(source_id=source_id, observation_by_id=observation_by_id)
            span = _span(observation=observation, quote=str(item.get("quote") or ""))
            observation_scope = memory_scope_from_observation(observation)
            entity_ref = str(item["entity_ref"]).strip()
            if entity_ref in entity_id_by_ref:
                raise ValueError(f"duplicate entity_ref:{entity_ref!r}")
            entity_id = _stable_id(
                "mention",
                "|".join([run_id, observation.source_id, entity_ref]),
            )
            entity_id_by_ref[entity_ref] = entity_id
            entities.append(
                EntityMention(
                    entity_id=entity_id,
                    mention_text=str(item["mention_text"]),
                    normalized_name=_normalize_name(str(item["mention_text"])),
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
            subject_entity_ref = str(item["subject_entity_ref"]).strip()
            subject_entity_id = entity_id_by_ref[subject_entity_ref]
            object_value = str(item["object_value"]).strip()
            span = _span(observation=observation, quote=str(item.get("quote") or ""))
            observation_scope = memory_scope_from_observation(observation)
            claim_key = ClaimKey(
                subject_entity_id=subject_entity_id,
                predicate_id=predicate_id,
                scope=observation_scope,
                qualifier_key="default",
            )
            confidence = _float_output(item.get("confidence"), default=0.6)
            object_entity_ref = str(item["object_entity_ref"]).strip() if item.get("object_entity_ref") else None
            object_entity_id, object_value, object_qualifiers = _resolve_claim_object_endpoint(
                run_id=run_id,
                predicate_id=predicate_id,
                object_value=object_value,
                object_entity_ref=object_entity_ref,
                observation=observation,
                confidence=confidence,
                entity_id_by_ref=entity_id_by_ref,
                entities=entities,
            )
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
                        claim_key.scope.stable_id(),
                        "default",
                    ]
                ),
            )
            claims.append(
                ExtractedClaim(
                    claim_id=claim_id,
                    claim_key=claim_key,
                    object_value=object_value,
                    object_entity_id=object_entity_id,
                    qualifiers=object_qualifiers,
                    valid_from=observation.timestamp,
                    valid_to=None,
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

    action_items = _list_output(output, "actions")
    action_ref_counts: dict[str, int] = {}
    for item in action_items:
        action_ref = str(item.get("action_ref") or "").strip()
        if action_ref:
            action_ref_counts[action_ref] = action_ref_counts.get(action_ref, 0) + 1
    duplicate_action_refs = {action_ref for action_ref, count in action_ref_counts.items() if count > 1}
    for idx, item in enumerate(action_items):
        try:
            source_id = str(item.get("source_id") or "")
            observation = _resolve_observation(source_id=source_id, observation_by_id=observation_by_id)
            quote = str(item.get("quote") or "")
            span = _span(observation=observation, quote=quote)
            action_ref = str(item["action_ref"]).strip()
            if action_ref in duplicate_action_refs:
                raise ValueError(f"duplicate action_ref:{action_ref!r}")
            action_id = _stable_id(
                "action",
                "|".join([run_id, observation.source_id, action_ref]),
            )
            action_type = str(item["action_type"])
            target_entity_ids = [
                entity_id_by_ref[str(value)] for value in _sequence_output(item.get("target_entity_refs"))
            ]
            if not target_entity_ids:
                raise ValueError("action requires at least one grounded target_entity_ref")
            status = str(item["status"])
            observation_scope = memory_scope_from_observation(observation)
            actor_entity_ref = str(item["actor_entity_ref"]).strip() if item.get("actor_entity_ref") else None
            actions.append(
                ExtractedAction(
                    action_id=action_id,
                    actor_entity_id=(entity_id_by_ref[actor_entity_ref] if actor_entity_ref is not None else None),
                    action_type=action_type,
                    target_entity_ids=target_entity_ids,
                    status=status,
                    dependency_entity_ids=[
                        entity_id_by_ref[str(value)] for value in _sequence_output(item.get("dependency_entity_refs"))
                    ],
                    blocking_entity_ids=[
                        entity_id_by_ref[str(value)] for value in _sequence_output(item.get("blocking_entity_refs"))
                    ],
                    timestamp=observation.timestamp,
                    scope=observation_scope,
                    evidence_spans=[span],
                    extraction_run_id=run_id,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"action[{idx}]: {type(exc).__name__}:{exc}")

    claims = _canonicalize_claim_arguments(claims, entities)
    entities_by_id = {entity.entity_id: entity for entity in entities}
    valid_claims: list[ExtractedClaim] = []
    for idx, claim in enumerate(claims):
        try:
            _validate_claim_endpoint_contract(
                predicate_id=claim.claim_key.predicate_id,
                subject=entities_by_id[claim.claim_key.subject_entity_id],
                object_entity=(entities_by_id[claim.object_entity_id] if claim.object_entity_id is not None else None),
                object_value=claim.object_value,
            )
            valid_claims.append(claim)
        except (KeyError, ValueError) as exc:
            errors.append(f"claim[{idx}]: {type(exc).__name__}:{exc}")
    claims = valid_claims
    extracted_anything = bool(entities or claims or actions)
    if errors:
        status = ExtractionRunStatus.PARTIAL if extracted_anything else ExtractionRunStatus.FAILED
        failure_code = ExtractionFailureCode.OUTPUT_VALIDATION
    elif extracted_anything:
        status = ExtractionRunStatus.SUCCEEDED
        failure_code = None
    else:
        status = ExtractionRunStatus.ABSTAINED
        failure_code = None
    run = ExtractionRun(
        extraction_run_id=run_id,
        provider=provider,
        model=model,
        prompt_hash=prompt_hash,
        input_source_ids=[obs.source_id for obs in observations],
        entity_ids=[entity.entity_id for entity in entities],
        claim_ids=[claim.claim_id for claim in claims],
        action_ids=[action.action_id for action in actions],
        status=status,
        provider_attempt_status=ProviderAttemptStatus.SUCCEEDED,
        final_output_source=(
            FinalExtractionSource.NONE if status == ExtractionRunStatus.FAILED else FinalExtractionSource.PRIMARY
        ),
        failure_code=failure_code,
        validation_summary={
            "input_validation_errors": 0,
            "entity_binding_errors": sum(error.startswith("entity[") for error in errors),
            "claim_binding_errors": sum(error.startswith("claim[") for error in errors),
            "action_binding_errors": sum(error.startswith("action[") for error in errors),
            "accepted_entities": len(entities),
            "accepted_claims": len(claims),
            "accepted_actions": len(actions),
        },
        errors=errors,
    )
    return run, entities, claims, actions


_REQUIRED_OBJECT_ENTITY_TYPES = {
    "owner": EntityType.PERSON,
    "approver": EntityType.PERSON,
    "api_owner": EntityType.PERSON,
    "dependency": EntityType.UNKNOWN,
}


def _resolve_claim_object_endpoint(
    *,
    run_id: str,
    predicate_id: str,
    object_value: str,
    object_entity_ref: str | None,
    observation: SourceObservation,
    confidence: float,
    entity_id_by_ref: dict[str, str],
    entities: list[EntityMention],
) -> tuple[str | None, str, dict[str, str]]:
    normalized_object = _normalize_name(object_value)
    if object_entity_ref is not None and object_entity_ref in entity_id_by_ref:
        entity_id = entity_id_by_ref[object_entity_ref]
        if predicate_id in _REQUIRED_OBJECT_ENTITY_TYPES:
            endpoint = next(
                (entity for entity in entities if entity.entity_id == entity_id),
                None,
            )
            if endpoint is None:
                raise KeyError(object_entity_ref)
            endpoint_names = _normalized_entity_names(endpoint)
            conflicting_entities = [
                entity
                for entity in entities
                if entity.entity_id != endpoint.entity_id
                and entity.scope == memory_scope_from_observation(observation)
                and any(span.source_id == observation.source_id for span in entity.evidence_spans)
                and normalized_object
                and normalized_object in _normalized_entity_names(entity)
            ]
            if normalized_object not in endpoint_names and conflicting_entities:
                raise ValueError(
                    f"object_entity_ref {object_entity_ref!r} conflicts with object_value {object_value!r}"
                )
            canonical_value = _entity_display_name(endpoint, fallback=entity_id)
            if object_value != canonical_value:
                qualifiers = {
                    "object_endpoint_grounding": "declared_entity_ref",
                    "object_value_normalization": "from_grounded_entity",
                }
                if object_value:
                    qualifiers["original_object_value"] = object_value
                return entity_id, canonical_value, qualifiers
        return entity_id, object_value, {}
    if predicate_id not in _REQUIRED_OBJECT_ENTITY_TYPES:
        if object_entity_ref is None:
            return None, object_value, {}
        raise KeyError(object_entity_ref)

    matching_entities = [
        entity
        for entity in entities
        if entity.scope == memory_scope_from_observation(observation)
        and any(span.source_id == observation.source_id for span in entity.evidence_spans)
        and normalized_object in _normalized_entity_names(entity)
    ]
    if len(matching_entities) > 1:
        raise ValueError(f"ambiguous grounded object endpoint:{object_value!r}")
    if matching_entities:
        entity_id = matching_entities[0].entity_id
        if object_entity_ref is not None:
            entity_id_by_ref[object_entity_ref] = entity_id
        return (
            entity_id,
            _entity_display_name(matching_entities[0], fallback=entity_id),
            {"object_endpoint_grounding": "matched_verbatim_entity"},
        )

    endpoint_span = _grounded_endpoint_span(
        observation=observation,
        object_value=object_value,
    )
    if endpoint_span is None:
        if object_entity_ref is not None:
            raise KeyError(object_entity_ref) from None
        return None, object_value, {}

    endpoint_ref = object_entity_ref or f"claim-object:{predicate_id}:{normalized_object}"
    entity_id = _stable_id(
        "mention",
        "|".join([run_id, observation.source_id, endpoint_ref]),
    )
    entities.append(
        EntityMention(
            entity_id=entity_id,
            mention_text=object_value,
            normalized_name=normalized_object,
            aliases=[],
            entity_type=_REQUIRED_OBJECT_ENTITY_TYPES[predicate_id],
            evidence_spans=[endpoint_span],
            confidence=confidence,
            scope=memory_scope_from_observation(observation),
        )
    )
    if object_entity_ref is not None:
        entity_id_by_ref[object_entity_ref] = entity_id
    return (
        entity_id,
        object_value,
        {"object_endpoint_grounding": "materialized_from_verbatim_object"},
    )


def _normalized_entity_names(entity: EntityMention) -> set[str]:
    return {
        _normalize_name(entity.mention_text),
        entity.normalized_name,
        *(_normalize_name(alias) for alias in entity.aliases),
    } - {""}


def _grounded_endpoint_span(
    *,
    observation: SourceObservation,
    object_value: str,
) -> EvidenceSpan | None:
    if not _normalize_name(object_value):
        return None
    try:
        span = _span(observation=observation, quote=object_value)
    except ValueError:
        return None
    assert span.char_start is not None
    assert span.char_end is not None
    before = observation.text[span.char_start - 1] if span.char_start else ""
    after = observation.text[span.char_end] if span.char_end < len(observation.text) else ""
    if object_value[0].isalnum() and before.isalnum():
        return None
    if object_value[-1].isalnum() and after.isalnum():
        return None
    return span


def _validate_claim_endpoint_contract(
    *,
    predicate_id: str,
    subject: EntityMention,
    object_entity: EntityMention | None,
    object_value: str,
) -> None:
    if predicate_id in _REQUIRED_OBJECT_ENTITY_TYPES and object_entity is None:
        raise ValueError(f"{predicate_id} requires a grounded object_entity_ref")
    if (
        predicate_id in {"owner", "approver", "api_owner"}
        and object_entity is not None
        and object_entity.entity_type not in {EntityType.PERSON, EntityType.UNKNOWN}
    ):
        raise ValueError(f"{predicate_id} object must be a person entity")
    if (
        predicate_id == "dependency"
        and object_entity is not None
        and object_entity.entity_type == EntityType.PREFERENCE
    ):
        raise ValueError("dependency object cannot be a preference entity")
    if predicate_id == "entity_type":
        if object_entity is not None:
            raise ValueError("entity_type requires a literal object, not object_entity_ref")
        try:
            declared_type = EntityType(object_value.strip().casefold())
        except ValueError as exc:
            raise ValueError(f"unsupported entity_type value:{object_value!r}") from exc
        if subject.entity_type not in {EntityType.UNKNOWN, declared_type}:
            raise ValueError("entity_type literal conflicts with the grounded subject type")


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
                new_claim_key.scope.stable_id(),
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
        # The source is authoritative at the ingestion boundary. For a
        # single-source request, an echoed opaque ID adds no information; bind
        # provenance deterministically and continue to validate the quote.
        return next(iter(observation_by_id.values()))
    raise KeyError(f"unknown source_id:{source_id!r}")


def _list_output(output: dict[str, object], key: str) -> list[dict[str, object]]:
    value = output.get(key, [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


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


def _span(*, observation: SourceObservation, quote: str) -> EvidenceSpan:
    if not quote:
        raise ValueError("evidence quote must be non-empty")
    start = observation.text.find(quote)
    if start < 0:
        raise ValueError(f"evidence quote is not verbatim in source {observation.source_id!r}")
    end = start + len(quote)
    return EvidenceSpan(
        source_id=observation.source_id,
        quote=quote,
        char_start=start,
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
