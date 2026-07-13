from __future__ import annotations

from typing import Literal, cast

from memorii.core.benchmark.artifact_rows import RuntimeCheckpointResultRow
from memorii.core.calibration.alignment import RuntimeGraphAlignment
from pydantic import BaseModel, ConfigDict, Field
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    checkpoint_by_type,
    generate_scenario_by_family,
)

RuntimeGraphItemKind = Literal["entity", "claim", "action"]
RuntimeGraphValue = str | float | list[str]
RuntimeGraphItem = dict[str, RuntimeGraphValue]


class RuntimeGraphItemFixture(BaseModel):
    scenario_id: str
    runtime_item_id: str
    item_type: RuntimeGraphItemKind
    lifecycle_state: str = "active"
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    evidence_event_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    def to_graph_item(self) -> RuntimeGraphItem:
        return cast(RuntimeGraphItem, self.model_dump(mode="json"))


class RuntimeEntityFixture(RuntimeGraphItemFixture):
    item_type: Literal["entity"] = "entity"
    canonical_name: str
    canonical_id: str
    entity_type: str
    aliases: list[str]


class RuntimeClaimFixture(RuntimeGraphItemFixture):
    item_type: Literal["claim"] = "claim"
    claim_id: str
    subject: str
    subject_entity_id: str
    predicate: str
    object: str
    object_value: str
    scope: str = "global"
    valid_from: str = ""
    valid_to: str = ""


class RuntimeActionFixture(RuntimeGraphItemFixture):
    item_type: Literal["action"] = "action"
    action_id: str
    action_type: str = "update_status"
    status: str
    target_entity_ids: list[str]
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


def runtime_checkpoint_row(**legacy_fields: object) -> RuntimeCheckpointResultRow:
    return RuntimeCheckpointResultRow(
        scenario_id=str(legacy_fields.pop("scenario_id", "scenario_1")),
        checkpoint_id=str(legacy_fields.pop("checkpoint_id", "checkpoint_1")),
        checkpoint_type=str(legacy_fields.pop("checkpoint_type", "current_truth")),
        success=bool(legacy_fields.pop("success", True)),
        passed=bool(legacy_fields.pop("passed", True)),
        verdict=str(legacy_fields.pop("verdict", "pass")),
        score=float(legacy_fields.pop("score", 1.0)),
        review_required=bool(legacy_fields.pop("review_required", False)),
        failure_buckets=list(legacy_fields.pop("failure_buckets", [])),
        warning_buckets=list(legacy_fields.pop("warning_buckets", [])),
        diagnostics=dict(legacy_fields.pop("diagnostics", {})),
        output=dict(legacy_fields.pop("output", {})),
        profile=str(legacy_fields.pop("profile", "long_horizon")),
        family=str(legacy_fields.pop("family", "current_truth")),
        decision_mode=str(legacy_fields.pop("decision_mode", "llm")),
        effective_decision_mode=str(legacy_fields.pop("effective_decision_mode", "llm")),
        final_output_source=str(legacy_fields.pop("final_output_source", "fake_oracle")),
        runtime_failure_buckets=list(legacy_fields.pop("runtime_failure_buckets", [])),
        runtime_failure_classification=list(legacy_fields.pop("runtime_failure_classification", [])),
        scenario_provider_successes=int(legacy_fields.pop("scenario_provider_successes", 0)),
        scenario_provider_failures=int(legacy_fields.pop("scenario_provider_failures", 0)),
        scenario_fallbacks=int(legacy_fields.pop("scenario_fallbacks", 0)),
        provider_count_scope=str(legacy_fields.pop("provider_count_scope", "scenario_extractor_calls")),
        legacy_fields=legacy_fields,
    )


def runtime_entity(
    *,
    scenario_id: str,
    runtime_id: str,
    canonical_id: str,
    name: str,
    entity_type: str,
    aliases: list[str],
    events: list[str],
) -> RuntimeGraphItem:
    return RuntimeEntityFixture(
        scenario_id=scenario_id,
        runtime_item_id=runtime_id,
        canonical_name=name,
        canonical_id=canonical_id,
        entity_type=entity_type,
        aliases=aliases,
        evidence_event_ids=events,
    ).to_graph_item()


def runtime_claim(
    *,
    scenario_id: str,
    runtime_id: str,
    subject_id: str,
    subject: str,
    predicate: str,
    obj: str,
    event: str,
) -> RuntimeGraphItem:
    return RuntimeClaimFixture(
        scenario_id=scenario_id,
        runtime_item_id=runtime_id,
        claim_id=runtime_id,
        subject=subject,
        subject_entity_id=subject_id,
        predicate=predicate,
        object=obj,
        object_value=obj,
        evidence_event_ids=[event],
    ).to_graph_item()


def alignment_for(alignments: list[RuntimeGraphAlignment], oracle_id: str) -> RuntimeGraphAlignment:
    return next(item for item in alignments if item.oracle_item_id == oracle_id and item.item_type == "claim")


def long_horizon_execution_scenario():
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="abandoned_then_resumed_work",
        scenario_count=10,
        seed=7,
        min_events=25,
        max_events=60,
        noise_rate=0.35,
    )
    return scenario, checkpoint_by_type(scenario, "execution_continuation")


def runtime_execution_base_items(
    *,
    scenario_id: str,
    branch_b_events: list[str] | None = None,
) -> list[RuntimeGraphItem]:
    return [
        runtime_entity(
            scenario_id=scenario_id,
            runtime_id="rt:entity:atlas-migration",
            canonical_id="ent:atlas-billing-migration",
            name="Atlas Billing Migration",
            entity_type="project",
            aliases=["Atlas Billing Migration"],
            events=["event_09_001"],
        ),
        runtime_entity(
            scenario_id=scenario_id,
            runtime_id="rt:entity:branch-b",
            canonical_id="ent:atlas-cleanup-branch-b",
            name="Atlas Cleanup Branch B",
            entity_type="task",
            aliases=["Atlas cleanup Branch B"],
            events=branch_b_events or ["event_09_branch_b_progress"],
        ),
        runtime_claim(
            scenario_id=scenario_id,
            runtime_id="rt:claim:project-type",
            subject_id="ent:atlas-billing-migration",
            subject="Atlas Billing Migration",
            predicate="entity_type",
            obj="project",
            event="event_09_001",
        ),
        runtime_claim(
            scenario_id=scenario_id,
            runtime_id="rt:claim:current-owner",
            subject_id="ent:atlas-billing-migration",
            subject="Atlas Billing Migration",
            predicate="owner",
            obj="Bob",
            event="event_09_005",
        ),
    ]


def runtime_action(
    *,
    target: str,
    status: str,
    events: list[str],
    scenario_id: str = "sim_09_abandoned_then_resumed_work",
) -> RuntimeGraphItem:
    return RuntimeActionFixture(
        scenario_id=scenario_id,
        runtime_item_id=f"graph:node:action:uuid-{target}-{status}",
        action_id=f"action:uuid-{target}-{status}",
        status=status,
        target_entity_ids=[target],
        evidence_event_ids=events,
    ).to_graph_item()
