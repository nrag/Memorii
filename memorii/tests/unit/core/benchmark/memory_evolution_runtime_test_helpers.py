from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from memorii.core.benchmark.artifact_rows import (
    CheckpointDiagnosticsPayload,
    RuntimeCheckpointResultRow,
)
from memorii.core.benchmark.calibration.alignment import RuntimeGraphAlignment
from memorii.core.benchmark.memory_evolution_runtime.models import (
    RUNTIME_GRAPH_ITEM_ADAPTER,
    RuntimeGraphItem,
)
from memorii.core.benchmark.memory_evolution_sim.schemas import (
    JudgeAggregate,
    JudgeVerdict,
    LatentClaim,
    LatentGraphScenario,
    MemoryEvolutionSimReconstructionContext,
    OracleCheckpoint,
    ReconstructionTaskContract,
    SimSystemOutput,
)
from pydantic import BaseModel, ConfigDict, Field
from tests.unit.core.benchmark.checkpoint_artifact_test_helpers import checkpoint_diagnostics_payload
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    checkpoint_by_type,
    claim_by_role,
    generate_scenario_by_family,
)

RuntimeGraphItemKind = Literal["entity", "claim", "action"]


class RuntimeGraphItemFixture(BaseModel):
    scenario_id: str
    runtime_item_id: str
    item_type: RuntimeGraphItemKind
    lifecycle_state: str = "active"
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    evidence_event_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    def to_graph_item(self) -> RuntimeGraphItem:
        return RUNTIME_GRAPH_ITEM_ADAPTER.validate_python(self.model_dump(mode="json"))


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


def runtime_checkpoint_row(**row_fields: object) -> RuntimeCheckpointResultRow:
    expected_payload = dict(row_fields.pop("expected", {}))
    output_payload = dict(row_fields.pop("output", {}))
    candidate_payload = dict(row_fields.pop("candidate_cards", {}))
    raw_output_payload = dict(row_fields.pop("raw_output", output_payload))
    judge_payload = dict(row_fields.pop("judge_aggregate", {}))
    diagnostic_overrides = dict(row_fields.pop("diagnostics", {}))
    for field_name in CheckpointDiagnosticsPayload.model_fields:
        if field_name in row_fields:
            diagnostic_overrides[field_name] = row_fields.pop(field_name)
    diagnostics = checkpoint_diagnostics_payload(**diagnostic_overrides)
    return RuntimeCheckpointResultRow(
        scenario_id=str(row_fields.pop("scenario_id", "scenario_1")),
        checkpoint_id=str(row_fields.pop("checkpoint_id", "checkpoint_1")),
        checkpoint_type=str(row_fields.pop("checkpoint_type", "current_truth")),
        success=bool(row_fields.pop("success", True)),
        passed=bool(row_fields.pop("passed", True)),
        verdict=str(row_fields.pop("verdict", "pass")),
        score=float(row_fields.pop("score", 1.0)),
        review_required=bool(row_fields.pop("review_required", False)),
        failure_buckets=list(row_fields.pop("failure_buckets", [])),
        warning_buckets=list(row_fields.pop("warning_buckets", [])),
        output=SimSystemOutput.model_validate(output_payload or {"operation": "abstain", "rationale": "test"}),
        profile=str(row_fields.pop("profile", "long_horizon")),
        family=str(row_fields.pop("family", "current_truth")),
        decision_mode=str(row_fields.pop("decision_mode", "llm")),
        effective_decision_mode=str(row_fields.pop("effective_decision_mode", "llm")),
        final_output_source=str(row_fields.pop("final_output_source", "fake_oracle")),
        runtime_failure_buckets=list(row_fields.pop("runtime_failure_buckets", [])),
        runtime_failure_classification=list(row_fields.pop("runtime_failure_classification", [])),
        scenario_provider_successes=int(row_fields.pop("scenario_provider_successes", 0)),
        scenario_provider_failures=int(row_fields.pop("scenario_provider_failures", 0)),
        scenario_fallbacks=int(row_fields.pop("scenario_fallbacks", 0)),
        provider_count_scope=str(row_fields.pop("provider_count_scope", "scenario_extractor_calls")),
        confidence=float(row_fields.pop("confidence", 1.0)),
        provider_successes=int(row_fields.pop("provider_successes", 0)),
        provider_failures=int(row_fields.pop("provider_failures", 0)),
        fallbacks=int(row_fields.pop("fallbacks", 0)),
        phase=str(row_fields.pop("phase", "checkpoint")),
        horizon_distance=int(row_fields.pop("horizon_distance", 0)),
        horizon_distance_bucket=str(row_fields.pop("horizon_distance_bucket", "short")),
        interference_count=int(row_fields.pop("interference_count", 0)),
        interference_count_bucket=str(row_fields.pop("interference_count_bucket", "none")),
        source_event_age_days=float(row_fields.pop("source_event_age_days", 0.0)),
        source_event_age_days_bucket=str(row_fields.pop("source_event_age_days_bucket", "fresh")),
        required_retrieval_view=str(row_fields.pop("required_retrieval_view", "current")),
        query_or_task=str(row_fields.pop("query_or_task", "")),
        expected=OracleCheckpoint.model_validate(
            {
                "checkpoint_id": "checkpoint_1",
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
                "checkpoint_type": "current_truth",
                "query_or_task": "",
                "task_contract": ReconstructionTaskContract().model_dump(mode="json"),
                **expected_payload,
            }
        ),
        candidate_cards=MemoryEvolutionSimReconstructionContext.model_validate(
            {
                "scenario_id": "scenario_1",
                "surface_observations": [],
                "checkpoint": {
                    "checkpoint_id": "checkpoint_1",
                    "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
                    "query_or_task": "",
                    "task_contract": ReconstructionTaskContract().model_dump(mode="json"),
                },
                **candidate_payload,
            }
        ),
        raw_output=SimSystemOutput.model_validate(raw_output_payload or {"operation": "abstain", "rationale": "test"}),
        judge_aggregate=JudgeAggregate.model_validate(
            {
                "checkpoint_id": "checkpoint_1",
                "verdict": JudgeVerdict.PASS,
                "score": 1.0,
                "confidence": 1.0,
                "votes": [],
                "required_judge_ids": [],
                "critical_failure_buckets": [],
                "review_required": False,
                "rationale": "test",
                **judge_payload,
            }
        ),
        diagnostics=diagnostics,
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


def action_claim_by_state(
    scenario: LatentGraphScenario,
    state: str,
    *,
    subject_name: str | None = None,
) -> LatentClaim:
    matches = [
        claim
        for claim in scenario.claims
        if "action_state" in claim.evaluation_roles
        and claim.object.normalized_value == state
        and (subject_name is None or claim.subject.canonical_name == subject_name)
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"Expected one action-state claim for state={state!r}, subject={subject_name!r}; "
            f"found {[(claim.subject.canonical_name, claim.object.value) for claim in matches]}"
        )
    return matches[0]


def claim_event_id(claim: LatentClaim) -> str:
    if len(claim.evidence.source_event_ids) != 1:
        raise AssertionError(f"Expected one evidence event for claim {claim.claim_id}")
    return claim.evidence.source_event_ids[0]


def runtime_execution_base_items(
    *,
    scenario: LatentGraphScenario,
    branch_b_events: list[str] | None = None,
) -> list[RuntimeGraphItem]:
    project_type = claim_by_role(scenario, "entity_type_missing")
    current_owner = claim_by_role(scenario, "current_truth")
    branch_b_progress = action_claim_by_state(
        scenario,
        "in_progress",
        subject_name="Atlas Cleanup Branch B",
    )
    return [
        runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:atlas-migration",
            canonical_id="ent:atlas-billing-migration",
            name="Atlas Billing Migration",
            entity_type="project",
            aliases=["Atlas Billing Migration"],
            events=[claim_event_id(project_type)],
        ),
        runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:branch-b",
            canonical_id="ent:atlas-cleanup-branch-b",
            name="Atlas Cleanup Branch B",
            entity_type="task",
            aliases=["Atlas cleanup Branch B"],
            events=branch_b_events or [claim_event_id(branch_b_progress)],
        ),
        runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:project-type",
            subject_id="ent:atlas-billing-migration",
            subject="Atlas Billing Migration",
            predicate="entity_type",
            obj="project",
            event=claim_event_id(project_type),
        ),
        runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:current-owner",
            subject_id="ent:atlas-billing-migration",
            subject="Atlas Billing Migration",
            predicate="owner",
            obj=current_owner.object.value,
            event=claim_event_id(current_owner),
        ),
    ]


def runtime_action(
    *,
    target: str,
    status: str,
    events: list[str],
    action_type: str = "status_update",
    scenario_id: str = "sim_09_abandoned_then_resumed_work",
) -> RuntimeGraphItem:
    return RuntimeActionFixture(
        scenario_id=scenario_id,
        runtime_item_id=f"graph:node:action:uuid-{target}-{status}",
        action_id=f"action:uuid-{target}-{status}",
        action_type=action_type,
        status=status,
        target_entity_ids=[target],
        evidence_event_ids=events,
    ).to_graph_item()
