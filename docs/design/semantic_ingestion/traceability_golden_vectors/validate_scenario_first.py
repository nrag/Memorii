"""Independent design-side feasibility checker for scenario-first scenario-first closure authority.

It deliberately gives the runtime extractor rendered observations only.  The
scenario world is retained by this process until its normalized output is
compared after extraction; it is never serialized into a SourceObservation.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from memorii.core.memory_evolution.extraction import EnglishRuleMemoryExtractor
from memorii.core.memory_evolution.models import (
    ClaimAssertionMode,
    ClaimEpistemicStatus,
    ClaimModality,
    ClaimPolarity,
    ExtractionTriggerMode,
    SourceObservation,
)
from memorii.domain.enums import MemoryDomain, SourceModality, SourceType


ROOT_KEYS = {"format", "scenario_set_id", "scenarios"}
SCENARIO_KEYS = {"scenario_id", "classification", "entities", "claims", "interaction", "expectation"}
ENTITY_KEYS = {"id", "name", "type"}
CLAIM_KEYS = {"id", "subject", "predicate", "object", "polarity", "modality", "attribution", "temporal", "scope", "provenance"}
TURN_KEYS = {"turn_id", "speaker", "source_kind", "timestamp", "claim_ids"}


def _exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} has incomplete or unknown fields")
    return value


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or not value.endswith("Z") or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("timestamps must be UTC RFC3339 Z values")
    return parsed


def validate(world: Any) -> list[dict[str, Any]]:
    root = _exact(world, ROOT_KEYS, "scenario root")
    if root["format"] != "memorii-sia-scenario-first-v1" or not isinstance(root["scenario_set_id"], str):
        raise ValueError("unsupported scenario format")
    if not isinstance(root["scenarios"], list) or not root["scenarios"]:
        raise ValueError("scenarios must be a non-empty list")
    seen: set[str] = set()
    for scenario in root["scenarios"]:
        _exact(scenario, SCENARIO_KEYS, "scenario")
        scenario_id = scenario["scenario_id"]
        if not isinstance(scenario_id, str) or scenario_id in seen:
            raise ValueError("scenario IDs must be unique strings")
        seen.add(scenario_id)
        if scenario["classification"] not in {"supported_roundtrip", "ambiguous", "insufficient_evidence", "negative"}:
            raise ValueError(f"{scenario_id}: unknown classification")
        entities = scenario["entities"]
        if not isinstance(entities, list):
            raise ValueError(f"{scenario_id}: entities must be a list")
        entity_ids: set[str] = set()
        for entity in entities:
            _exact(entity, ENTITY_KEYS, f"{scenario_id}: entity")
            if not all(isinstance(entity[key], str) and entity[key] for key in ENTITY_KEYS) or entity["id"] in entity_ids:
                raise ValueError(f"{scenario_id}: invalid entity")
            entity_ids.add(entity["id"])
        claims = scenario["claims"]
        if not isinstance(claims, list):
            raise ValueError(f"{scenario_id}: claims must be a list")
        claim_ids: set[str] = set()
        for claim in claims:
            _exact(claim, CLAIM_KEYS, f"{scenario_id}: claim")
            if claim["id"] in claim_ids or claim["subject"] not in entity_ids:
                raise ValueError(f"{scenario_id}: invalid claim identity or subject")
            if claim["predicate"] not in {"owner", "status"} or claim["polarity"] != "positive" or claim["modality"] != "assertion":
                raise ValueError(f"{scenario_id}: unsupported deterministic claim")
            if claim["predicate"] == "owner" and claim["object"] not in entity_ids:
                raise ValueError(f"{scenario_id}: owner object must be an entity")
            if not isinstance(claim["object"], str) or not isinstance(claim["attribution"], dict):
                raise ValueError(f"{scenario_id}: invalid claim semantics")
            if (
                set(claim["attribution"]) != {"kind", "speaker"}
                or claim["attribution"]["kind"] != "direct"
                or not isinstance(claim["attribution"]["speaker"], str)
                or not claim["attribution"]["speaker"]
            ):
                raise ValueError(f"{scenario_id}: unsupported attribution")
            if set(claim["temporal"]) != {"valid_from", "valid_to"}:
                raise ValueError(f"{scenario_id}: invalid temporal shape")
            if claim["temporal"]["valid_to"] is not None and _utc(claim["temporal"]["valid_from"]) >= _utc(claim["temporal"]["valid_to"]):
                raise ValueError(f"{scenario_id}: invalid temporal interval")
            if set(claim["scope"]) != {"user_id", "session_id", "task_id"} or not all(isinstance(v, str) and v for v in claim["scope"].values()):
                raise ValueError(f"{scenario_id}: invalid scope")
            if set(claim["provenance"]) != {"source_kind", "source_id"} or claim["provenance"]["source_kind"] != "user":
                raise ValueError(f"{scenario_id}: invalid provenance")
            claim_ids.add(claim["id"])
        interaction = scenario["interaction"]
        if set(interaction) != {"turns"} or not isinstance(interaction["turns"], list) or not interaction["turns"]:
            raise ValueError(f"{scenario_id}: invalid interaction")
        referenced: list[str] = []
        turn_by_id: dict[str, dict[str, Any]] = {}
        for turn in interaction["turns"]:
            _exact(turn, TURN_KEYS, f"{scenario_id}: turn")
            _utc(turn["timestamp"])
            if (
                turn["source_kind"] != "user"
                or not isinstance(turn["speaker"], str)
                or not turn["speaker"]
                or not isinstance(turn["claim_ids"], list)
                or turn["turn_id"] in turn_by_id
            ):
                raise ValueError(f"{scenario_id}: invalid turn")
            turn_by_id[turn["turn_id"]] = turn
            referenced.extend(turn["claim_ids"])
        if sorted(referenced) != sorted(claim_ids):
            raise ValueError(f"{scenario_id}: interactions must render every claim exactly once")
        for claim in claims:
            turn = turn_by_id.get(claim["provenance"]["source_id"])
            if turn is None or claim["attribution"]["speaker"] != turn["speaker"]:
                raise ValueError(f"{scenario_id}: claim attribution must match its source turn")
        expected = {"supported_roundtrip": "match", "ambiguous": "ambiguous", "insufficient_evidence": "abstain", "negative": "abstain"}[scenario["classification"]]
        if scenario["expectation"] != expected:
            raise ValueError(f"{scenario_id}: classification and expectation disagree")
    return root["scenarios"]


def render(scenario: dict[str, Any]) -> list[SourceObservation]:
    """Renderer A: templates are constrained to the checked runtime rule grammar."""
    entities = {item["id"]: item["name"] for item in scenario["entities"]}
    claims = {item["id"]: item for item in scenario["claims"]}
    rendered: list[SourceObservation] = []
    for turn in scenario["interaction"]["turns"]:
        fragments: list[str] = []
        turn_claims = [claims[claim_id] for claim_id in turn["claim_ids"]]
        for claim in turn_claims:
            subject = entities[claim["subject"]]
            value = entities[claim["object"]] if claim["predicate"] == "owner" else claim["object"]
            fragments.append(f"{subject} {claim['predicate']} is {value}.")
        text = " ".join(fragments) if fragments else "No source-grounded assertion is available."
        scope = turn_claims[0]["scope"] if turn_claims else {"user_id": "fixture-user", "session_id": "fixture-session", "task_id": "fixture-task"}
        rendered.append(SourceObservation(source_id=turn["turn_id"], text=text, source_type=SourceType.USER, timestamp=_utc(turn["timestamp"]), domain=MemoryDomain.TRANSCRIPT, language="en", speaker_id=turn["speaker"], modality=SourceModality.ASSERTION, trigger_mode=ExtractionTriggerMode.IMMEDIATE, **scope))
    return rendered


def _expected(scenario: dict[str, Any], observations: dict[str, SourceObservation]) -> list[tuple[Any, ...]]:
    names = {item["id"]: item["name"].casefold() for item in scenario["entities"]}
    output: list[tuple[Any, ...]] = []
    for claim in scenario["claims"]:
        source_id = claim["provenance"]["source_id"]
        observation = observations[source_id]
        subject = names[claim["subject"]]
        object_value = names[claim["object"]] if claim["predicate"] == "owner" else claim["object"].casefold()
        quote = f"{next(item['name'] for item in scenario['entities'] if item['id'] == claim['subject'])} {claim['predicate']} is {next(item['name'] for item in scenario['entities'] if item['id'] == claim['object']) if claim['predicate'] == 'owner' else claim['object']}"
        start = observation.text.encode("utf-8").find(quote.encode("utf-8"))
        if start < 0:
            raise ValueError("rendered claim quote missing")
        output.append((
            subject, claim["predicate"], object_value, claim["predicate"] == "owner",
            tuple(claim["scope"][key] for key in ("user_id", "session_id", "task_id")),
            source_id, SourceType.USER.value, quote, start, start + len(quote.encode("utf-8")),
            claim["temporal"]["valid_from"], claim["temporal"]["valid_to"],
            ClaimAssertionMode.WORLD_ASSERTION.value, ClaimEpistemicStatus.ASSERTED.value,
            ClaimPolarity(claim["polarity"]).value, ClaimModality.ASSERTION.value,
            claim["attribution"]["speaker"], None,
        ))
    return output


def compare_proposal(
    scenario: dict[str, Any], proposal: Any, *, source_id_map: dict[str, str] | None = None,
    observations: dict[str, SourceObservation] | None = None,
) -> str:
    """Project an actual proposal without giving it hidden scenario authority."""
    source_id_map = source_id_map or {}
    observations = observations or {item.source_id: item for item in render(scenario)}
    actual = [
        (
            entity_names[claim.claim_key.subject_entity_id],
            claim.claim_key.predicate_id,
            claim.object_value.casefold(),
            claim.object_entity_id is not None,
            claim.claim_key.scope.identity,
            source_id_map.get(claim.evidence_spans[0].source_id, claim.evidence_spans[0].source_id),
            claim.evidence_spans[0].source_type.value,
            claim.evidence_spans[0].quote,
            len(observations[source_id_map.get(claim.evidence_spans[0].source_id, claim.evidence_spans[0].source_id)].text[:claim.evidence_spans[0].char_start or 0].encode("utf-8")),
            len(observations[source_id_map.get(claim.evidence_spans[0].source_id, claim.evidence_spans[0].source_id)].text[:claim.evidence_spans[0].char_end or 0].encode("utf-8")),
            claim.valid_from.isoformat().replace("+00:00", "Z") if claim.valid_from is not None else None,
            claim.valid_to.isoformat().replace("+00:00", "Z") if claim.valid_to is not None else None,
            claim.semantic_context.assertion_mode.value,
            claim.semantic_context.epistemic_status.value,
            claim.semantic_context.polarity.value,
            claim.semantic_context.modality.value,
            claim.semantic_context.attribution_speaker_id,
            claim.semantic_context.belief_holder_entity_id,
        )
        for claim in proposal.claims
        for entity_names in [{entity.entity_id: entity.normalized_name for entity in proposal.entities}]
        if claim.claim_key.subject_entity_id in entity_names
    ]
    if not actual and scenario["expectation"] == "abstain" and proposal.run.status.value == "abstained":
        return "abstain"
    keys = [(item[0], item[1], item[4], item[12], item[17]) for item in actual]
    if scenario["expectation"] == "ambiguous" and len(keys) != len(set(keys)) and len({item[2] for item in actual}) > 1:
        return "ambiguous"
    return "match" if sorted(actual) == sorted(_expected(scenario, observations)) else "mismatch"


def compare(scenario: dict[str, Any], observations: list[SourceObservation]) -> str:
    """Compatibility helper for the direct extractor feasibility spike."""
    return compare_proposal(scenario, EnglishRuleMemoryExtractor().extract(observations))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario_file", type=Path)
    args = parser.parse_args()
    scenarios = validate(json.loads(args.scenario_file.read_text(encoding="ascii")))
    outcomes = {scenario["scenario_id"]: compare(scenario, render(scenario)) for scenario in scenarios}
    mismatches = {scenario["scenario_id"]: {"expected": scenario["expectation"], "actual": outcomes[scenario["scenario_id"]]} for scenario in scenarios if outcomes[scenario["scenario_id"]] != scenario["expectation"]}
    if mismatches:
        raise SystemExit(json.dumps({"mismatches": mismatches}, sort_keys=True))
    print(json.dumps({"scenarios": len(scenarios), "outcomes": outcomes}, sort_keys=True))


if __name__ == "__main__":
    main()
