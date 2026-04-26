"""Structured solver update pipeline with abstention and verification."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from memorii.core.solver.abstention import ConfidenceBand, SolverDecision
from memorii.core.solver.belief import update_solver_belief
from memorii.core.solver.models import NextTestAction
from memorii.core.solver.verifier import SolverDecisionVerifier
from memorii.domain.common import SolverEdgeMetadata, SolverNodeMetadata
from memorii.domain.enums import CommitStatus, ConfidenceClass, SolverCreatedBy, SolverEdgeType, SolverNodeStatus, SolverNodeType
from memorii.domain.events import EventRecord
from memorii.domain.solver_graph.edges import SolverEdge
from memorii.domain.solver_graph.nodes import SolverNode
from memorii.domain.solver_graph.overlays import SolverNodeOverlay, SolverOverlayVersion


class SolverDecisionOutput(BaseModel):
    decision: SolverDecision
    evidence_ids: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    next_best_test: str | None = None
    next_test_action: NextTestAction | None = None
    rationale_short: str
    confidence_band: ConfidenceBand

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def enforce_decision_invariants(self) -> "SolverDecisionOutput":
        if self.decision in {SolverDecision.SUPPORTED, SolverDecision.REFUTED} and not self.evidence_ids:
            raise ValueError("commitment_decisions_require_evidence_ids")
        if self.decision == SolverDecision.INSUFFICIENT_EVIDENCE and not self.missing_evidence:
            raise ValueError("insufficient_evidence_requires_missing_evidence")
        if self.next_test_action is not None and not self.next_test_action.description.strip():
            raise ValueError("next_test_action_requires_description")
        if self.decision == SolverDecision.NEEDS_TEST:
            if not self.missing_evidence:
                raise ValueError("needs_test_requires_missing_evidence")
            has_next_best_test = self.next_best_test is not None and bool(self.next_best_test.strip())
            if not has_next_best_test and self.next_test_action is None:
                raise ValueError("needs_test_requires_next_test")
        return self


class SolverUpdateInput(BaseModel):
    task_id: str
    solver_run_id: str
    execution_node_id: str
    observation_text: str
    observation_source_ref: str
    available_evidence_ids: list[str] = Field(default_factory=list)
    model_output: dict[str, object] | None = None

    model_config = ConfigDict(extra="forbid")


class SolverUpdateResult(BaseModel):
    parsed_output: SolverDecisionOutput
    final_decision: SolverDecision
    created_nodes: list[SolverNode] = Field(default_factory=list)
    created_edges: list[SolverEdge] = Field(default_factory=list)
    committed_node_ids: list[str] = Field(default_factory=list)
    committed_edge_ids: list[str] = Field(default_factory=list)
    overlay_version: SolverOverlayVersion | None = None
    generated_events: list[EventRecord] = Field(default_factory=list)
    follow_up_required: bool = False
    downgraded: bool = False
    validation_notes: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class SolverUpdateEngine:
    def __init__(self, verifier: SolverDecisionVerifier | None = None) -> None:
        self._verifier = verifier or SolverDecisionVerifier()

    def apply_update(
        self,
        *,
        update_input: SolverUpdateInput,
        next_overlay_version_id: str,
        next_event_id: str,
        next_node_id: str,
        next_edge_id: str,
        prior_overlay_version: SolverOverlayVersion | None = None,
    ) -> SolverUpdateResult:
        now = datetime.now(UTC)
        parsed, parse_errors = self._parse_output(update_input)
        if parse_errors:
            fallback = SolverDecisionOutput(
                decision=SolverDecision.INSUFFICIENT_EVIDENCE,
                evidence_ids=[],
                missing_evidence=["invalid_model_output"],
                next_best_test="emit_valid_structured_output",
                rationale_short="Model output failed schema validation",
                confidence_band=ConfidenceBand.LOW,
            )
            return SolverUpdateResult(
                parsed_output=fallback,
                final_decision=SolverDecision.INSUFFICIENT_EVIDENCE,
                downgraded=False,
                follow_up_required=True,
                validation_notes=parse_errors,
            )

        verification = self._verifier.verify(
            decision=parsed.decision,
            evidence_ids=parsed.evidence_ids,
            missing_evidence=parsed.missing_evidence,
            next_best_test=parsed.next_best_test,
            next_test_action=parsed.next_test_action,
            available_evidence_ids=set(update_input.available_evidence_ids),
        )
        if not verification.is_valid:
            return SolverUpdateResult(
                parsed_output=parsed,
                final_decision=SolverDecision.INSUFFICIENT_EVIDENCE,
                downgraded=verification.downgraded,
                follow_up_required=True,
                validation_notes=list(verification.reasons),
            )
        final_decision = verification.final_decision
        verifier_downgraded = verification.downgraded or parsed.decision != final_decision

        notes = list(verification.reasons)
        if final_decision == SolverDecision.INSUFFICIENT_EVIDENCE and parsed.decision in {
            SolverDecision.SUPPORTED,
            SolverDecision.REFUTED,
        }:
            notes.append("unsupported_commitment_downgraded")

        observation_node = SolverNode(
            id=f"{next_node_id}:obs",
            type=SolverNodeType.OBSERVATION,
            content={"summary": update_input.observation_text, "source_ref": update_input.observation_source_ref},
            metadata=SolverNodeMetadata(
                created_at=now,
                created_by=SolverCreatedBy.SYSTEM,
                candidate_state=CommitStatus.COMMITTED,
                source_refs=[update_input.observation_source_ref],
                tags=["runtime_observation"],
            ),
        )

        created_nodes: list[SolverNode] = [observation_node]
        created_edges: list[SolverEdge] = []
        committed_node_ids = [observation_node.id]
        committed_edge_ids: list[str] = []
        follow_up_required = False

        decision_node_state = CommitStatus.CANDIDATE
        edge_state = CommitStatus.CANDIDATE
        overlay_status = SolverNodeStatus.ACTIVE
        edge_type = SolverEdgeType.REFERENCES

        if final_decision == SolverDecision.SUPPORTED:
            decision_node_type = SolverNodeType.HYPOTHESIS
            decision_node_content = {"decision": final_decision.value, "rationale": parsed.rationale_short}
            decision_node_state = CommitStatus.COMMITTED
            edge_state = CommitStatus.COMMITTED
            overlay_status = SolverNodeStatus.RESOLVED
            edge_type = SolverEdgeType.SUPPORTS
        elif final_decision == SolverDecision.REFUTED:
            decision_node_type = SolverNodeType.HYPOTHESIS
            decision_node_content = {"decision": final_decision.value, "rationale": parsed.rationale_short}
            decision_node_state = CommitStatus.COMMITTED
            edge_state = CommitStatus.COMMITTED
            overlay_status = SolverNodeStatus.RESOLVED
            edge_type = SolverEdgeType.CONTRADICTS
        elif final_decision == SolverDecision.NEEDS_TEST:
            decision_node_type = SolverNodeType.ACTION
            decision_node_content = {
                "decision": final_decision.value,
                "next_best_test": parsed.next_best_test,
                "next_test_action": parsed.next_test_action.model_dump(mode="json") if parsed.next_test_action else None,
                "missing_evidence": parsed.missing_evidence,
            }
            overlay_status = SolverNodeStatus.NEEDS_TEST
            follow_up_required = True
        elif final_decision == SolverDecision.MULTIPLE_PLAUSIBLE_OPTIONS:
            decision_node_type = SolverNodeType.COMPOSITE_HYPOTHESIS
            decision_node_content = {
                "decision": final_decision.value,
                "missing_evidence": parsed.missing_evidence,
                "rationale": parsed.rationale_short,
            }
            overlay_status = SolverNodeStatus.MULTIPLE_PLAUSIBLE_OPTIONS
            follow_up_required = True
        else:
            decision_node_type = SolverNodeType.QUESTION
            decision_node_content = {
                "decision": SolverDecision.INSUFFICIENT_EVIDENCE.value,
                "missing_evidence": parsed.missing_evidence,
            }
            overlay_status = SolverNodeStatus.INSUFFICIENT_EVIDENCE
            follow_up_required = True

        decision_node = SolverNode(
            id=f"{next_node_id}:decision",
            type=decision_node_type,
            content=decision_node_content,
            metadata=SolverNodeMetadata(
                created_at=now,
                created_by=SolverCreatedBy.SYSTEM,
                candidate_state=decision_node_state,
                source_refs=[update_input.observation_source_ref, *parsed.evidence_ids],
                tags=["solver_update"],
            ),
        )
        created_nodes.append(decision_node)
        if decision_node_state == CommitStatus.COMMITTED:
            committed_node_ids.append(decision_node.id)

        link_edge = SolverEdge(
            id=f"{next_edge_id}:decision-link",
            src=decision_node.id,
            dst=observation_node.id,
            type=edge_type,
            metadata=SolverEdgeMetadata(
                created_at=now,
                created_by=SolverCreatedBy.SYSTEM,
                candidate_state=edge_state,
                confidence_class=ConfidenceClass.OBSERVED if edge_state == CommitStatus.COMMITTED else ConfidenceClass.SPECULATIVE,
                source_refs=[update_input.observation_source_ref, *parsed.evidence_ids],
            ),
        )
        created_edges.append(link_edge)
        if edge_state == CommitStatus.COMMITTED:
            committed_edge_ids.append(link_edge.id)

        prior_belief = self._prior_belief_for_node(
            prior_overlay_version=prior_overlay_version,
            node_id=decision_node.id,
        )
        decision_belief = update_solver_belief(
            prior_belief=prior_belief,
            decision=final_decision,
            evidence_count=len(parsed.evidence_ids),
            missing_evidence_count=len(parsed.missing_evidence),
            verifier_downgraded=verifier_downgraded,
            conflict_count=0,
        )

        overlay = SolverOverlayVersion(
            version_id=next_overlay_version_id,
            solver_run_id=update_input.solver_run_id,
            created_at=now,
            committed=True,
            node_overlays=[
                SolverNodeOverlay(
                    node_id=decision_node.id,
                    belief=decision_belief,
                    status=overlay_status,
                    is_frontier=follow_up_required,
                    frontier_priority=1.0 if follow_up_required else None,
                    unexplained=final_decision == SolverDecision.INSUFFICIENT_EVIDENCE,
                    reopenable=final_decision in {SolverDecision.NEEDS_TEST, SolverDecision.MULTIPLE_PLAUSIBLE_OPTIONS},
                    updated_at=now,
                ),
                SolverNodeOverlay(
                    node_id=observation_node.id,
                    belief=1.0,
                    status=SolverNodeStatus.ACTIVE,
                    updated_at=now,
                ),
            ],
        )

        events = self._build_events(
            base_event_id=next_event_id,
            task_id=update_input.task_id,
            solver_run_id=update_input.solver_run_id,
            execution_node_id=update_input.execution_node_id,
            nodes=created_nodes,
            edges=created_edges,
            overlay=overlay,
            committed_node_ids=committed_node_ids,
            committed_edge_ids=committed_edge_ids,
        )

        return SolverUpdateResult(
            parsed_output=parsed,
            final_decision=final_decision,
            created_nodes=created_nodes,
            created_edges=created_edges,
            committed_node_ids=committed_node_ids,
            committed_edge_ids=committed_edge_ids,
            overlay_version=overlay,
            generated_events=events,
            follow_up_required=follow_up_required,
            downgraded=verifier_downgraded,
            validation_notes=notes,
        )

    def _prior_belief_for_node(
        self,
        *,
        prior_overlay_version: SolverOverlayVersion | None,
        node_id: str,
    ) -> float | None:
        if prior_overlay_version is None:
            return None
        for overlay in prior_overlay_version.node_overlays:
            if overlay.node_id == node_id:
                return overlay.belief
        return None

    def _parse_output(self, update_input: SolverUpdateInput) -> tuple[SolverDecisionOutput, list[str]]:
        if update_input.model_output is None:
            return SolverDecisionOutput(
                decision=SolverDecision.INSUFFICIENT_EVIDENCE,
                evidence_ids=[],
                missing_evidence=["model_output_missing"],
                next_best_test="collect_additional_observation",
                rationale_short="No model output provided",
                confidence_band=ConfidenceBand.LOW,
            ), []
        try:
            return SolverDecisionOutput.model_validate(update_input.model_output), []
        except ValidationError as error:
            return (
                SolverDecisionOutput(
                    decision=SolverDecision.INSUFFICIENT_EVIDENCE,
                    evidence_ids=[],
                    missing_evidence=["invalid_model_output"],
                    next_best_test="emit_valid_structured_output",
                    rationale_short="Model output failed schema validation",
                    confidence_band=ConfidenceBand.LOW,
                ),
                [f"invalid_solver_output:{error.errors()[0]['type']}"],
            )

    def _build_events(
        self,
        *,
        base_event_id: str,
        task_id: str,
        solver_run_id: str,
        execution_node_id: str,
        nodes: list[SolverNode],
        edges: list[SolverEdge],
        overlay: SolverOverlayVersion,
        committed_node_ids: list[str],
        committed_edge_ids: list[str],
    ) -> list[EventRecord]:
        now = datetime.now(UTC)
        events: list[EventRecord] = []

        for index, node in enumerate(nodes):
            events.append(
                EventRecord(
                    event_id=f"{base_event_id}:node:{index}",
                    event_type="NODE_ADDED",
                    timestamp=now,
                    task_id=task_id,
                    execution_node_id=execution_node_id,
                    solver_run_id=solver_run_id,
                    source="solver_update_engine",
                    payload={
                        "graph_type": "solver",
                        "entity_type": "node",
                        "operation": "create",
                        "entity_id": node.id,
                        "entity": node.model_dump(mode="json"),
                        "metadata": {
                            "version": 1,
                            "is_candidate": node.metadata.candidate_state == CommitStatus.CANDIDATE,
                            "is_committed": node.metadata.candidate_state == CommitStatus.COMMITTED,
                        },
                    },
                    dedupe_key=f"{solver_run_id}:node:{node.id}:v1",
                )
            )

        for index, edge in enumerate(edges):
            events.append(
                EventRecord(
                    event_id=f"{base_event_id}:edge:{index}",
                    event_type="EDGE_ADDED",
                    timestamp=now,
                    task_id=task_id,
                    execution_node_id=execution_node_id,
                    solver_run_id=solver_run_id,
                    source="solver_update_engine",
                    payload={
                        "graph_type": "solver",
                        "entity_type": "edge",
                        "operation": "create",
                        "entity_id": edge.id,
                        "entity": edge.model_dump(mode="json"),
                        "metadata": {
                            "version": 1,
                            "is_candidate": edge.metadata.candidate_state == CommitStatus.CANDIDATE,
                            "is_committed": edge.metadata.candidate_state == CommitStatus.COMMITTED,
                        },
                    },
                    dedupe_key=f"{solver_run_id}:edge:{edge.id}:v1",
                )
            )

        for node_id in committed_node_ids:
            events.append(
                EventRecord(
                    event_id=f"{base_event_id}:node-commit:{node_id}",
                    event_type="NODE_COMMITTED",
                    timestamp=now,
                    task_id=task_id,
                    execution_node_id=execution_node_id,
                    solver_run_id=solver_run_id,
                    source="solver_update_engine",
                    payload={"node_id": node_id},
                    dedupe_key=f"{solver_run_id}:node-commit:{node_id}",
                )
            )

        for edge_id in committed_edge_ids:
            events.append(
                EventRecord(
                    event_id=f"{base_event_id}:edge-commit:{edge_id}",
                    event_type="EDGE_COMMITTED",
                    timestamp=now,
                    task_id=task_id,
                    execution_node_id=execution_node_id,
                    solver_run_id=solver_run_id,
                    source="solver_update_engine",
                    payload={"edge_id": edge_id},
                    dedupe_key=f"{solver_run_id}:edge-commit:{edge_id}",
                )
            )

        events.append(
            EventRecord(
                event_id=f"{base_event_id}:overlay",
                event_type="BELIEF_UPDATED",
                timestamp=now,
                task_id=task_id,
                execution_node_id=execution_node_id,
                solver_run_id=solver_run_id,
                source="solver_update_engine",
                payload={
                    "graph_type": "solver",
                    "entity_type": "overlay",
                    "operation": "version",
                    "entity_id": overlay.version_id,
                    "entity": overlay.model_dump(mode="json"),
                    "metadata": {"version": 1, "is_candidate": False, "is_committed": True},
                },
                dedupe_key=f"{solver_run_id}:overlay:{overlay.version_id}",
            )
        )

        return events
