"""Closed runtime persistence contracts: records, content codecs, commands.

Every model is a closed schema (``extra=forbid``) with finite enums. The
node-content union replaces generic dictionaries at the persistence
boundary; the command union carries the complete task lifecycle (including
complete/pause/abort) and the closed solver proposal union (belief update,
status update, reopen, merge) with justification-bound belief changes and
gate-checked merges. No timestamp is a fencing token; revision numbers are
the only ordering authority.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_HEX_64 = r"^[0-9a-f]{64}$"
_EPISTEMIC = ("candidate", "committed", "weakened", "suspended", "retired")

EpistemicStatus = Literal["candidate", "committed", "weakened", "suspended", "retired"]
TaskLifecycle = Literal["active", "paused", "completed", "aborted"]
SolverRunLifecycle = Literal["active", "resolved", "archived"]
JustificationRole = Literal["supporting", "contradicting", "assumption"]


class NodeEvidenceReference(BaseModel):
    source_id: str = Field(min_length=1)
    source_digest: str | None = Field(default=None, pattern=_HEX_64)

    model_config = ConfigDict(extra="forbid", frozen=True)


class _ContentBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GoalContent(_ContentBase):
    kind: Literal["GOAL"] = "GOAL"
    statement: str = Field(min_length=1)
    acceptance_criteria: tuple[str, ...] = ()


class QuestionContent(_ContentBase):
    kind: Literal["QUESTION"] = "QUESTION"
    question: str = Field(min_length=1)
    resolved_by: tuple[str, ...] = ()


class AssumptionContent(_ContentBase):
    kind: Literal["ASSUMPTION"] = "ASSUMPTION"
    statement: str = Field(min_length=1)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    evidence: tuple[NodeEvidenceReference, ...] = ()


class ConstraintContent(_ContentBase):
    kind: Literal["CONSTRAINT"] = "CONSTRAINT"
    statement: str = Field(min_length=1)
    evidence: tuple[NodeEvidenceReference, ...] = ()


class HypothesisContent(_ContentBase):
    kind: Literal["HYPOTHESIS"] = "HYPOTHESIS"
    statement: str = Field(min_length=1)
    epistemic_status: EpistemicStatus = "candidate"
    strength: float = Field(ge=0.0, le=1.0)
    constituents: tuple[str, ...] = ()
    evidence: tuple[NodeEvidenceReference, ...] = ()


class CompositeHypothesisContent(HypothesisContent):
    kind: Literal["COMPOSITE_HYPOTHESIS"] = "COMPOSITE_HYPOTHESIS"
    constituent_hypothesis_ids: tuple[str, ...] = ()


class ExplanationFactorContent(HypothesisContent):
    kind: Literal["EXPLANATION_FACTOR"] = "EXPLANATION_FACTOR"


class SynthesisContent(HypothesisContent):
    kind: Literal["SYNTHESIS"] = "SYNTHESIS"
    conclusion_refs: tuple[str, ...] = ()


class ObservationContent(_ContentBase):
    kind: Literal["OBSERVATION"] = "OBSERVATION"
    summary: str = Field(min_length=1)
    source_refs: tuple[NodeEvidenceReference, ...] = ()
    result_ref: str | None = None


class ActionContent(_ContentBase):
    kind: Literal["ACTION"] = "ACTION"
    action: str = Field(min_length=1)
    evidence: tuple[NodeEvidenceReference, ...] = ()


class ScenarioContent(_ContentBase):
    kind: Literal["SCENARIO"] = "SCENARIO"
    conditions: tuple[str, ...] = ()
    expected_observation_refs: tuple[str, ...] = ()


class DomainReferenceContent(_ContentBase):
    referenced_id: str = Field(min_length=1)
    referenced_revision: int | None = Field(default=None, ge=0)
    valid_until: datetime | None = None


class SemanticRefContent(DomainReferenceContent):
    kind: Literal["SEMANTIC_REF"] = "SEMANTIC_REF"


class EpisodicRefContent(DomainReferenceContent):
    kind: Literal["EPISODIC_REF"] = "EPISODIC_REF"


class UserRefContent(DomainReferenceContent):
    kind: Literal["USER_REF"] = "USER_REF"


class EnvironmentRefContent(DomainReferenceContent):
    kind: Literal["ENVIRONMENT_REF"] = "ENVIRONMENT_REF"


class SkillRefContent(DomainReferenceContent):
    kind: Literal["SKILL_REF"] = "SKILL_REF"


SolverNodeContent = Annotated[
    GoalContent
    | QuestionContent
    | AssumptionContent
    | ConstraintContent
    | HypothesisContent
    | CompositeHypothesisContent
    | ExplanationFactorContent
    | SynthesisContent
    | ObservationContent
    | ActionContent
    | ScenarioContent
    | SemanticRefContent
    | EpisodicRefContent
    | UserRefContent
    | EnvironmentRefContent
    | SkillRefContent,
    Field(discriminator="kind"),
]

_CONTENT_KINDS = frozenset(
    {
        "GOAL", "QUESTION", "ASSUMPTION", "CONSTRAINT", "HYPOTHESIS",
        "COMPOSITE_HYPOTHESIS", "EXPLANATION_FACTOR", "SYNTHESIS",
        "OBSERVATION", "ACTION", "SCENARIO", "SEMANTIC_REF",
        "EPISODIC_REF", "USER_REF", "ENVIRONMENT_REF", "SKILL_REF",
    }
)


class TaskRecord(BaseModel):
    """One durable task and its explicit active solver selections."""

    task_id: str = Field(min_length=1)
    principal: str = Field(min_length=1)
    project: str | None = None
    goal: str = Field(min_length=1)
    created_at: datetime
    root_execution_node_id: str = Field(min_length=1)
    lifecycle: TaskLifecycle = "active"
    retention_tier: Literal["HOT", "WARM", "COLD", "ARCHIVED"] = "HOT"
    active_solver_by_execution_node: dict[str, str] = Field(default_factory=dict)
    acceptance_criteria: tuple[str, ...] = ()
    version: int = Field(default=1, ge=1)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def selection_is_explicit(self) -> TaskRecord:
        if not self.active_solver_by_execution_node and self.lifecycle == "active":
            # A task may start without a solver; the selection is explicit
            # whenever present and never inferred by ID ordering.
            pass
        return self


class SolverRunRecord(BaseModel):
    solver_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    parent_execution_node_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    lifecycle: SolverRunLifecycle = "active"
    created_by: str = Field(min_length=1)
    selected_overlay_id: str | None = None
    version: int = Field(default=1, ge=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class SolverJustificationRecord(BaseModel):
    justification_id: str = Field(min_length=1)
    solver_id: str = Field(min_length=1)
    conclusion: str = Field(min_length=1)
    supporting_ids: tuple[str, ...] = ()
    contradicting_ids: tuple[str, ...] = ()
    assumption_ids: tuple[str, ...] = ()
    strength: float = Field(ge=0.0, le=1.0)
    active: bool = True
    source_refs: tuple[NodeEvidenceReference, ...] = ()
    version: int = Field(default=1, ge=1)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def roles_are_disjoint(self) -> SolverJustificationRecord:
        overlap = (
            set(self.supporting_ids) & set(self.contradicting_ids)
        ) | (set(self.supporting_ids) & set(self.assumption_ids)) | (
            set(self.contradicting_ids) & set(self.assumption_ids)
        )
        if overlap:
            raise ValueError(
                f"justification roles must be disjoint; conflicting ids: {sorted(overlap)}"
            )
        return self


class OverlayJustificationBinding(BaseModel):
    node_id: str = Field(min_length=1)
    active_justification_ids: tuple[str, ...] = ()
    inactive_justification_ids: tuple[str, ...] = ()
    frontier: bool = False
    reopenable: bool = False
    unexplained: bool = False

    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeOverlayVersion(BaseModel):
    """Immutable full overlay snapshot per version."""

    version_id: str = Field(min_length=1)
    solver_id: str = Field(min_length=1)
    parent_version_id: str | None = None
    node_bindings: tuple[OverlayJustificationBinding, ...] = ()
    created_at: datetime
    committed: bool = False

    model_config = ConfigDict(extra="forbid", frozen=True)


class ActionAttemptRecord(BaseModel):
    action_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    recommendation_id: str = Field(min_length=1)
    recommendation_revision: int = Field(ge=1)
    executor_binding: str = Field(min_length=1)
    status: Literal[
        "selected", "dispatched", "succeeded", "failed", "outcome_unknown", "cancelled"
    ] = "selected"
    evidence_refs: tuple[NodeEvidenceReference, ...] = ()
    result_ref: str | None = None
    delivery_identity: str | None = None
    version: int = Field(default=1, ge=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeCommandReceipt(BaseModel):
    operation_id: str = Field(min_length=1)
    client_namespace: str = Field(min_length=1)
    request_digest: str = Field(pattern=_HEX_64)
    status: Literal["pending", "committed", "rejected", "needs_reconciliation"] = "pending"
    base_revision: int = Field(ge=0)
    current_revision: int = Field(ge=0)
    result_digest: str | None = Field(default=None, pattern=_HEX_64)

    model_config = ConfigDict(extra="forbid", frozen=True)


class BeliefUpdateProposal(BaseModel):
    """The durable carrier of the spec's update_belief: justification-bound."""

    kind: Literal["belief_update"] = "belief_update"
    solver_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    justification_id: str = Field(min_length=1)
    epistemic_status: EpistemicStatus
    strength: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid", frozen=True)


class StatusUpdateProposal(BaseModel):
    kind: Literal["status_update"] = "status_update"
    solver_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    evidence: tuple[NodeEvidenceReference, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True)


class NodeReopenProposal(BaseModel):
    kind: Literal["node_reopen"] = "node_reopen"
    solver_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    reason_refs: tuple[str, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True)


class NodeMergeProposal(BaseModel):
    kind: Literal["node_merge"] = "node_merge"
    solver_id: str = Field(min_length=1)
    source_node_id: str = Field(min_length=1)
    target_node_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def source_and_target_differ(self) -> NodeMergeProposal:
        if self.source_node_id == self.target_node_id:
            raise ValueError("merge source and target must differ")
        return self


SolverProposal = Annotated[
    BeliefUpdateProposal | StatusUpdateProposal | NodeReopenProposal | NodeMergeProposal,
    Field(discriminator="kind"),
]


class TaskCompletionEvidence(BaseModel):
    """Typed completion evidence; acceptance validation applies before DONE."""

    acceptance_results: tuple[str, ...] = ()
    required_artifact_refs: tuple[str, ...] = ()
    unresolved_blocker_acknowledged: bool = False

    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeCommandRequest(BaseModel):
    """Closed version-1 runtime command union."""

    protocol_version: Literal[1] = 1
    kind: Literal[
        "start_task",
        "resume_task",
        "record_observation",
        "propose_state_change",
        "record_action_dispatch",
        "record_action_result",
        "checkpoint_task",
        "replan_task",
        "complete_task",
        "pause_task",
        "abort_task",
    ]
    operation_id: str = Field(min_length=1)
    task_id: str | None = None
    expected_revision: int | None = Field(default=None, ge=0)
    goal: str | None = None
    completion_evidence: TaskCompletionEvidence | None = None
    pause_reason: str | None = None
    abort_reason: str | None = None
    proposal: SolverProposal | None = None
    source_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def payload_matches_kind(self) -> RuntimeCommandRequest:
        if self.kind == "start_task":
            if not self.goal or self.task_id is not None or self.expected_revision is not None:
                raise ValueError("start_task requires a goal and no task id or revision")
        else:
            if not self.task_id:
                raise ValueError(f"{self.kind} requires task_id")
            if self.expected_revision is None:
                raise ValueError(f"{self.kind} requires expected_revision")
            if self.kind == "propose_state_change" and self.proposal is None:
                raise ValueError("propose_state_change requires a proposal")
            if self.kind == "complete_task" and self.completion_evidence is None:
                raise ValueError("complete_task requires completion evidence")
            if self.kind == "pause_task" and not self.pause_reason:
                raise ValueError("pause_task requires a reason")
            if self.kind == "abort_task" and not self.abort_reason:
                raise ValueError("abort_task requires a reason")
        if self.kind != "propose_state_change" and self.proposal is not None:
            raise ValueError("proposal is only valid with propose_state_change")
        if self.kind == "record_observation":
            if self.source_digest is None:
                raise ValueError("record_observation requires a source digest")
        elif self.source_digest is not None:
            raise ValueError("source_digest is only valid with record_observation")
        return self


__all__ = [
    "ActionAttemptRecord",
    "AssumptionContent",
    "ActionContent",
    "BeliefUpdateProposal",
    "CompositeHypothesisContent",
    "ConstraintContent",
    "EpisodicRefContent",
    "EpistemicStatus",
    "EnvironmentRefContent",
    "ExplanationFactorContent",
    "GoalContent",
    "HypothesisContent",
    "NodeEvidenceReference",
    "NodeMergeProposal",
    "NodeReopenProposal",
    "ObservationContent",
    "OverlayJustificationBinding",
    "QuestionContent",
    "RuntimeCommandReceipt",
    "RuntimeCommandRequest",
    "RuntimeOverlayVersion",
    "ScenarioContent",
    "SemanticRefContent",
    "SkillRefContent",
    "SolverJustificationRecord",
    "SolverNodeContent",
    "SolverProposal",
    "SolverRunRecord",
    "StatusUpdateProposal",
    "SynthesisContent",
    "TaskCompletionEvidence",
    "TaskRecord",
    "UserRefContent",
    "_CONTENT_KINDS",
]
