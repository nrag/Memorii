"""Build calibration artifacts from benchmark checkpoint rows."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import datetime

from memorii.core.benchmark.artifact_rows import CheckpointResultRow
from memorii.core.benchmark.calibration.metrics import (
    brier_score,
    build_calibration_slices,
    expected_calibration_error,
    labeled_events,
    low_confidence_correct_count,
    overconfident_wrong_count,
    risk_coverage_curve,
    rolling_window_metrics,
    scenario_cluster_accuracy_interval,
)
from memorii.core.benchmark.calibration.models import (
    CalibrationDecisionChannel,
    CalibrationEvent,
    CalibrationHierarchyLayer,
    CalibrationItemType,
    CalibrationLabel,
    CalibrationLabelSource,
    CalibrationReport,
    CalibrationResponseLevel,
    CalibrationSlice,
    CalibrationStabilityStatus,
    DecisionAction,
    DecisionCostReport,
)
from memorii.core.benchmark.calibration.policy import DEFAULT_DECISION_COSTS, response_for_failure_buckets
from memorii.core.benchmark.memory_evolution_sim.schemas import (
    OracleCheckpoint,
    VisibleClaimCandidate,
    VisibleRelationCandidate,
)


def build_calibration_artifacts(
    *,
    suite: str,
    profile: str,
    checkpoint_rows: Sequence[CheckpointResultRow],
) -> tuple[list[CalibrationEvent], CalibrationReport, list[CalibrationSlice], DecisionCostReport]:
    events = calibration_events_from_checkpoint_rows(suite=suite, profile=profile, checkpoint_rows=checkpoint_rows)
    report = build_calibration_report(events, input_telemetry=_input_telemetry_from_checkpoint_rows(checkpoint_rows))
    slices = build_calibration_slices(events)
    decision_report = build_decision_cost_report(checkpoint_rows)
    return events, report, slices, decision_report


def calibration_events_from_checkpoint_rows(
    *,
    suite: str,
    profile: str,
    checkpoint_rows: Sequence[CheckpointResultRow],
) -> list[CalibrationEvent]:
    events: list[CalibrationEvent] = []
    for index, row in enumerate(checkpoint_rows):
        output = row.output
        expected = row.expected
        judge_ids = [vote.judge_id for vote in row.judge_aggregate.votes]
        base_failure_buckets = list(row.failure_buckets)
        row_confidence = output.confidence
        row_event_count = 0
        channel_specs = [
            (
                CalibrationDecisionChannel.SELECTED,
                "selected_entity_ids",
                CalibrationItemType.ENTITY,
                "expected_entity_ids",
            ),
            (
                CalibrationDecisionChannel.SELECTED,
                "selected_claim_ids",
                CalibrationItemType.CLAIM,
                "expected_claim_ids",
            ),
            (
                CalibrationDecisionChannel.SELECTED,
                "selected_relation_ids",
                CalibrationItemType.RELATION,
                "expected_relation_ids",
            ),
            (
                CalibrationDecisionChannel.SUPPORTING,
                "supporting_claim_ids",
                CalibrationItemType.CLAIM,
                "expected_claim_ids",
            ),
            (
                CalibrationDecisionChannel.SUPPORTING,
                "supporting_relation_ids",
                CalibrationItemType.RELATION,
                "expected_relation_ids",
            ),
            (
                CalibrationDecisionChannel.SUPPORTING,
                "supporting_citation_event_ids",
                CalibrationItemType.SOURCE_OBSERVATION,
                "expected_citation_event_ids",
            ),
            (
                CalibrationDecisionChannel.REJECTED,
                "rejected_entity_ids",
                CalibrationItemType.ENTITY,
                "expected_entity_ids",
            ),
            (
                CalibrationDecisionChannel.REJECTED,
                "rejected_claim_ids",
                CalibrationItemType.CLAIM,
                "expected_claim_ids",
            ),
            (
                CalibrationDecisionChannel.REJECTED,
                "rejected_relation_ids",
                CalibrationItemType.RELATION,
                "expected_relation_ids",
            ),
            (
                CalibrationDecisionChannel.CONTEXT,
                "context_entity_ids",
                CalibrationItemType.ENTITY,
                "expected_entity_ids",
            ),
            (CalibrationDecisionChannel.CONTEXT, "context_claim_ids", CalibrationItemType.CLAIM, "expected_claim_ids"),
            (
                CalibrationDecisionChannel.CONTEXT,
                "context_relation_ids",
                CalibrationItemType.RELATION,
                "expected_relation_ids",
            ),
        ]
        for channel, output_key, item_type, expected_key in channel_specs:
            ids = getattr(output, output_key)
            expected_ids = set(getattr(expected, expected_key))
            excluded_ids = set(_excluded_ids_for_item_type(expected, item_type))
            for item_id in ids:
                item = str(item_id)
                evidence_event_ids = _evidence_event_ids(row, item)
                evidence_phases = _evidence_phases(row, item, evidence_event_ids=evidence_event_ids)
                label, label_source, rationale, buckets = _label_for_item(
                    item_id=item,
                    channel=channel,
                    expected_ids=expected_ids,
                    excluded_ids=excluded_ids,
                    row_success=row.success,
                    base_failure_buckets=base_failure_buckets,
                )
                row_event_count += 1
                event_confidence = 0.5 if label == CalibrationLabel.PARTIAL else row_confidence
                events.append(
                    _calibration_event(
                        suite=suite,
                        profile=profile,
                        row=row,
                        row_index=index,
                        item_id=item,
                        item_type=item_type,
                        hierarchy_layer=CalibrationHierarchyLayer.RETRIEVAL_DECISION,
                        decision_channel=channel,
                        confidence=event_confidence,
                        label=label,
                        label_source=label_source,
                        label_rationale=rationale,
                        failure_buckets=buckets,
                        judge_ids=judge_ids,
                        evidence_event_ids=evidence_event_ids,
                        phase=_phase_from_evidence(evidence_phases),
                        evidence_phases=evidence_phases,
                        output_key=output_key,
                    )
                )
            if channel in {CalibrationDecisionChannel.SELECTED, CalibrationDecisionChannel.SUPPORTING}:
                emitted_ids = {str(item_id) for item_id in ids}
                for missing_id in sorted(expected_ids - emitted_ids):
                    row_event_count += 1
                    missing_buckets = [*base_failure_buckets, f"missing_required_{channel.value}"]
                    rejected_ids = set(output.rejected_claim_ids)
                    if missing_id in rejected_ids:
                        missing_buckets.append("expected_item_rejected")
                    events.append(
                        _calibration_event(
                            suite=suite,
                            profile=profile,
                            row=row,
                            row_index=index,
                            item_id=missing_id,
                            item_type=item_type,
                            hierarchy_layer=CalibrationHierarchyLayer.RETRIEVAL_DECISION,
                            decision_channel=channel,
                            confidence=row_confidence,
                            label=CalibrationLabel.INCORRECT,
                            label_source=CalibrationLabelSource.LATENT_ORACLE,
                            label_rationale="required item was absent from the answer-bearing channel",
                            failure_buckets=missing_buckets,
                            judge_ids=judge_ids,
                            output_key=f"{output_key}:missing",
                        )
                    )
        if base_failure_buckets and any(
            bucket in {"hidden_fact_hallucinated", "hidden_fact_answer_leak", "overconfident_wrong_answer"}
            for bucket in base_failure_buckets
        ):
            events.append(
                _calibration_event(
                    suite=suite,
                    profile=profile,
                    row=row,
                    row_index=index,
                    item_id=row.checkpoint_id,
                    item_type=CalibrationItemType.ANSWER,
                    hierarchy_layer=CalibrationHierarchyLayer.RETRIEVAL_DECISION,
                    decision_channel=CalibrationDecisionChannel.SELECTED,
                    confidence=row_confidence,
                    label=CalibrationLabel.INCORRECT,
                    label_source=CalibrationLabelSource.PROGRAMMATIC_JUDGE,
                    label_rationale="critical checkpoint-level failure bucket",
                    failure_buckets=base_failure_buckets,
                    judge_ids=judge_ids,
                    output_key="answer",
                )
            )
        if row_event_count == 0:
            events.append(
                _abstained_event(
                    suite=suite, profile=profile, row=row, index=index, confidence=row_confidence, judge_ids=judge_ids
                )
            )
    return events


def build_calibration_report(
    events: list[CalibrationEvent],
    *,
    input_telemetry: dict[str, int] | None = None,
) -> CalibrationReport:
    labeled = labeled_events(events)
    probability_labeled = [
        event for event in labeled if event.label in {CalibrationLabel.CORRECT, CalibrationLabel.INCORRECT}
    ]
    positives = sum(1 for event in probability_labeled if event.label == CalibrationLabel.CORRECT)
    hidden_events = [
        event
        for event in events
        if "hidden_fact_hallucinated" in event.failure_buckets or "hidden_fact_answer_leak" in event.failure_buckets
    ]
    ambiguous_events = [event for event in events if "ambiguous_fact_overcommitted" in event.failure_buckets]
    response_counts = Counter(response_for_failure_buckets(event.failure_buckets).value for event in events)
    label_source_counts = Counter(source.value for event in events for source in event.label_sources)
    hierarchy_layer_counts = Counter(event.hierarchy_layer.value for event in events)
    slices = build_calibration_slices(events)
    worst_slices = [
        item
        for item in slices
        if item.eligible_for_failure and item.response_level != CalibrationResponseLevel.REPORT_ONLY
    ][:10]
    response_counts.update(item.response_level.value for item in worst_slices)
    cluster_accuracy = scenario_cluster_accuracy_interval(events)
    risk_coverage = risk_coverage_curve(events)
    scenario_count = len({event.scenario_id for event in events})
    return CalibrationReport(
        event_count=len(events),
        labeled_event_count=len(labeled),
        probability_event_count=len(probability_labeled),
        partial_event_count=sum(1 for event in labeled if event.label == CalibrationLabel.PARTIAL),
        overall_accuracy=(positives / len(probability_labeled)) if probability_labeled else None,
        ece=expected_calibration_error(events),
        brier_score=brier_score(events),
        overconfident_wrong_count=overconfident_wrong_count(events),
        low_confidence_correct_count=low_confidence_correct_count(events),
        hidden_hallucination_rate=len(hidden_events) / max(1, len(events)),
        ambiguous_overcommit_rate=len(ambiguous_events) / max(1, len(events)),
        worst_slices=worst_slices,
        rolling_windows=rolling_window_metrics(events),
        response_recommendations=dict(sorted(response_counts.items())),
        label_source_counts=dict(sorted(label_source_counts.items())),
        hierarchy_layer_counts=dict(sorted(hierarchy_layer_counts.items())),
        scenario_cluster_intervals={"accuracy": cluster_accuracy} if cluster_accuracy is not None else {},
        risk_coverage=risk_coverage,
        abstention_rate=(
            sum(1 for event in labeled if event.decision_channel.value == "abstained") / len(labeled)
            if labeled
            else None
        ),
        selective_risk_at_full_coverage=risk_coverage[-1].selective_risk if risk_coverage else None,
        input_telemetry_count=sum(input_telemetry.values()) if input_telemetry else 0,
        input_telemetry_by_type=dict(sorted((input_telemetry or {}).items())),
        scenario_count=scenario_count,
        stability_status=(
            CalibrationStabilityStatus.ELIGIBLE
            if scenario_count >= 30
            else CalibrationStabilityStatus.INSUFFICIENT_COVERAGE
        ),
    )


def _input_telemetry_from_checkpoint_rows(
    checkpoint_rows: Sequence[CheckpointResultRow],
) -> dict[str, int]:
    """Count observable inputs without treating them as model predictions.

    Candidate cards are context supplied to an extractor or decision stage.
    They are useful for coverage audits, but labeling them correct would
    contaminate calibration metrics with oracle-visible inputs.
    """

    counts: Counter[str] = Counter()
    for row in checkpoint_rows:
        cards = row.candidate_cards
        for key in ("visible_events", "visible_entities", "visible_claims", "visible_relations"):
            values = getattr(cards, key)
            if values:
                counts[key] += len(values)
    return dict(counts)


def build_decision_cost_report(
    checkpoint_rows: Sequence[CheckpointResultRow],
) -> DecisionCostReport:
    by_bucket: Counter[str] = Counter()
    by_checkpoint: Counter[str] = Counter()
    by_modality: Counter[str] = Counter()
    by_action: Counter[str] = Counter()
    for row in checkpoint_rows:
        checkpoint_type = row.checkpoint_type
        action = _decision_action_for_checkpoint(checkpoint_type).value
        buckets = list(row.failure_buckets)
        if not buckets and not row.success:
            buckets = ["unclassified_failure"]
        for bucket in buckets:
            cost = DEFAULT_DECISION_COSTS.get(bucket, 5)
            by_bucket[bucket] += cost
            by_checkpoint[checkpoint_type] += cost
            by_modality[_first_modality(row)] += cost
            by_action[action] += cost
    total = float(sum(by_bucket.values()))
    return DecisionCostReport(
        decision_cost_total=total,
        decision_cost_mean=total / max(1, len(checkpoint_rows)),
        cost_by_failure_bucket={key: float(value) for key, value in sorted(by_bucket.items())},
        cost_by_checkpoint_type={key: float(value) for key, value in sorted(by_checkpoint.items())},
        cost_by_source_modality={key: float(value) for key, value in sorted(by_modality.items())},
        cost_by_decision_action={key: float(value) for key, value in sorted(by_action.items())},
        regret_total=total,
        regret_mean=total / max(1, len(checkpoint_rows)),
    )


def _calibration_event(
    *,
    suite: str,
    profile: str,
    row: CheckpointResultRow,
    row_index: int,
    item_id: str,
    item_type: CalibrationItemType,
    hierarchy_layer: CalibrationHierarchyLayer,
    decision_channel: CalibrationDecisionChannel,
    confidence: float,
    label: CalibrationLabel,
    label_source: CalibrationLabelSource,
    label_rationale: str,
    failure_buckets: list[str] | None = None,
    judge_ids: list[str] | None = None,
    source_modality: str | None = None,
    source_trust: int | None = None,
    predicate_id: str | None = None,
    scope_key: str | None = None,
    lifecycle_state: str | None = None,
    evidence_event_ids: list[str] | None = None,
    phase: str | None = None,
    evidence_phases: list[str] | None = None,
    output_key: str = "unknown",
) -> CalibrationEvent:
    item_failure_buckets = list(failure_buckets or [])
    label_sources = [label_source]
    if item_failure_buckets and CalibrationLabelSource.PROGRAMMATIC_JUDGE not in label_sources:
        label_sources.append(CalibrationLabelSource.PROGRAMMATIC_JUDGE)
    resolved_evidence_event_ids = (
        evidence_event_ids if evidence_event_ids is not None else _evidence_event_ids(row, item_id)
    )
    resolved_evidence_phases = (
        evidence_phases
        if evidence_phases is not None
        else _evidence_phases(
            row,
            item_id,
            evidence_event_ids=resolved_evidence_event_ids,
        )
    )
    return CalibrationEvent(
        event_id=f"cal:{row.scenario_id}:{row.checkpoint_id}:{row_index}:{hierarchy_layer.value}:{decision_channel.value}:{output_key}:{item_id}",
        timestamp=_calibration_event_timestamp(row, row_index),
        suite=suite,
        scenario_id=row.scenario_id,
        checkpoint_id=row.checkpoint_id,
        item_id=item_id,
        item_type=item_type,
        hierarchy_layer=hierarchy_layer,
        decision_channel=decision_channel,
        confidence=max(0.0, min(1.0, confidence)),
        label=label,
        label_source=label_source,
        label_sources=label_sources,
        label_confidence=1.0,
        label_rationale=label_rationale,
        failure_buckets=item_failure_buckets,
        source_modality=source_modality or _row_source_modality(row, item_id),
        source_trust=source_trust if source_trust is not None else _row_source_trust(row, item_id),
        predicate_id=predicate_id or _row_predicate_id(row, item_id),
        scope_key=scope_key or _row_scope_key(row, item_id),
        lifecycle_state=lifecycle_state or _row_lifecycle_state(row, item_id),
        retrieval_view=_retrieval_view_for_checkpoint(row.checkpoint_type),
        entity_ambiguity="ambiguous" if "ambiguous" in item_id else "none",
        evidence_event_ids=resolved_evidence_event_ids,
        judge_ids=judge_ids or [],
        decision_action=_decision_action_for_checkpoint(row.checkpoint_type),
        metadata={
            "checkpoint_type": row.checkpoint_type,
            "profile": profile,
            "phase": phase or _phase_from_evidence(resolved_evidence_phases) or row.phase,
            "evidence_phases": "|".join(resolved_evidence_phases),
            "horizon_distance_bucket": row.horizon_distance_bucket,
            "interference_count_bucket": row.interference_count_bucket,
            "source_event_age_days_bucket": row.source_event_age_days_bucket,
            "required_retrieval_view": row.required_retrieval_view,
            "output_key": output_key,
        },
    )


def _calibration_event_timestamp(row: CheckpointResultRow, row_index: int) -> datetime:
    """Use the required typed oracle checkpoint timestamp for ordering."""

    del row_index
    return row.expected.timestamp


def _label_for_item(
    *,
    item_id: str,
    channel: CalibrationDecisionChannel,
    expected_ids: set[str],
    excluded_ids: set[str],
    row_success: bool,
    base_failure_buckets: list[str],
) -> tuple[CalibrationLabel, CalibrationLabelSource, str, list[str]]:
    if channel in {CalibrationDecisionChannel.SELECTED, CalibrationDecisionChannel.SUPPORTING}:
        if item_id in excluded_ids:
            return (
                CalibrationLabel.INCORRECT,
                CalibrationLabelSource.LATENT_ORACLE,
                "excluded item appeared in selected/supporting channel",
                [*base_failure_buckets, "stale_memory_selected"],
            )
        if expected_ids and item_id in expected_ids:
            return (
                CalibrationLabel.CORRECT,
                CalibrationLabelSource.LATENT_ORACLE,
                "item matched expected oracle id in answer-bearing channel",
                [],
            )
        if row_success and not base_failure_buckets:
            return (
                CalibrationLabel.CORRECT,
                CalibrationLabelSource.PROGRAMMATIC_JUDGE,
                "item was accepted as selected/supporting by programmatic judges",
                [],
            )
        return (
            CalibrationLabel.INCORRECT,
            CalibrationLabelSource.PROGRAMMATIC_JUDGE,
            "item did not match selected/supporting channel semantics",
            list(base_failure_buckets),
        )
    if channel == CalibrationDecisionChannel.REJECTED:
        if item_id in excluded_ids:
            return (
                CalibrationLabel.CORRECT,
                CalibrationLabelSource.LATENT_ORACLE,
                "excluded item was correctly rejected",
                [],
            )
        if expected_ids and item_id in expected_ids:
            return (
                CalibrationLabel.INCORRECT,
                CalibrationLabelSource.LATENT_ORACLE,
                "expected item was incorrectly rejected",
                [*base_failure_buckets, "expected_item_rejected"],
            )
        if row_success and not base_failure_buckets:
            return (
                CalibrationLabel.CORRECT,
                CalibrationLabelSource.PROGRAMMATIC_JUDGE,
                "item was accepted as rejected audit evidence by programmatic judges",
                [],
            )
        return (
            CalibrationLabel.INCORRECT,
            CalibrationLabelSource.PROGRAMMATIC_JUDGE,
            "item did not match rejected channel semantics",
            list(base_failure_buckets),
        )
    if channel == CalibrationDecisionChannel.CONTEXT:
        if row_success and not base_failure_buckets:
            return (
                CalibrationLabel.CORRECT,
                CalibrationLabelSource.PROGRAMMATIC_JUDGE,
                "context item was accepted as audit evidence without being answer support",
                [],
            )
        if item_id in excluded_ids:
            return (
                CalibrationLabel.PARTIAL,
                CalibrationLabelSource.LATENT_ORACLE,
                "excluded item appeared only as context during a failed checkpoint",
                list(base_failure_buckets),
            )
        return (
            CalibrationLabel.INCORRECT,
            CalibrationLabelSource.PROGRAMMATIC_JUDGE,
            "context item appeared in a failed checkpoint",
            list(base_failure_buckets),
        )
    if row_success and not base_failure_buckets:
        return (
            CalibrationLabel.CORRECT,
            CalibrationLabelSource.PROGRAMMATIC_JUDGE,
            "item was accepted by programmatic judges",
            [],
        )
    return (
        CalibrationLabel.INCORRECT,
        CalibrationLabelSource.PROGRAMMATIC_JUDGE,
        "item did not match channel semantics",
        list(base_failure_buckets),
    )


def _abstained_event(
    *, suite: str, profile: str, row: CheckpointResultRow, index: int, confidence: float, judge_ids: list[str]
) -> CalibrationEvent:
    label = CalibrationLabel.CORRECT if row.success else CalibrationLabel.INCORRECT
    return _calibration_event(
        suite=suite,
        profile=profile,
        row=row,
        row_index=index,
        item_id=row.checkpoint_id,
        item_type=CalibrationItemType.ANSWER,
        hierarchy_layer=CalibrationHierarchyLayer.RETRIEVAL_DECISION,
        decision_channel=CalibrationDecisionChannel.ABSTAINED,
        confidence=confidence,
        label=label,
        label_source=CalibrationLabelSource.PROGRAMMATIC_JUDGE,
        label_rationale="checkpoint emitted no structured ids; calibrated as abstention",
        failure_buckets=list(row.failure_buckets),
        judge_ids=judge_ids,
        output_key="abstained",
    )


def _excluded_ids_for_item_type(expected: OracleCheckpoint, item_type: CalibrationItemType) -> list[str]:
    if item_type == CalibrationItemType.ENTITY:
        return list(expected.expected_excluded_entity_ids)
    if item_type == CalibrationItemType.CLAIM:
        return list(expected.expected_excluded_claim_ids)
    return []


def _row_predicate_id(row: CheckpointResultRow, item_id: str) -> str | None:
    for claim in _visible_claims(row):
        if claim.claim_id == item_id:
            return claim.predicate_id
    return None


def _row_source_modality(row: CheckpointResultRow, item_id: str) -> str | None:
    for claim in _visible_claims(row):
        if claim.claim_id == item_id:
            return claim.source_modality
    return _first_modality(row)


def _row_source_trust(row: CheckpointResultRow, item_id: str) -> int | None:
    for claim in _visible_claims(row):
        if claim.claim_id == item_id:
            return claim.source_trust
    return None


def _row_scope_key(row: CheckpointResultRow, item_id: str) -> str | None:
    for claim in _visible_claims(row):
        if claim.claim_id == item_id:
            return claim.scope_key
    return None


def _row_lifecycle_state(row: CheckpointResultRow, item_id: str) -> str | None:
    for claim in _visible_claims(row):
        if claim.claim_id == item_id:
            return claim.lifecycle_state
    return None


def _evidence_event_ids(row: CheckpointResultRow, item_id: str) -> list[str]:
    if item_id in _visible_event_phase_map(row):
        return [item_id]
    for claim in _visible_claims(row):
        if claim.claim_id == item_id:
            return list(claim.evidence_event_ids)
    for relation in _visible_relations(row):
        if relation.relation_id == item_id:
            return list(relation.evidence_event_ids)
    return []


def _evidence_phases(
    row: CheckpointResultRow, item_id: str, *, evidence_event_ids: list[str] | None = None
) -> list[str]:
    phase_by_event = _visible_event_phase_map(row)
    event_ids = evidence_event_ids if evidence_event_ids is not None else _evidence_event_ids(row, item_id)
    phases = sorted({phase_by_event[event_id] for event_id in event_ids if event_id in phase_by_event})
    return [phase for phase in phases if phase]


def _phase_from_evidence(phases: list[str]) -> str | None:
    if not phases:
        return None
    if len(phases) == 1:
        return phases[0]
    return "mixed"


def _visible_event_phase_map(row: CheckpointResultRow) -> dict[str, str]:
    return {event.event_id: event.phase for event in row.candidate_cards.visible_events}


def _visible_claims(row: CheckpointResultRow) -> list[VisibleClaimCandidate]:
    return row.candidate_cards.visible_claims


def _visible_relations(row: CheckpointResultRow) -> list[VisibleRelationCandidate]:
    return row.candidate_cards.visible_relations


def _first_modality(row: CheckpointResultRow) -> str:
    claims = _visible_claims(row)
    if claims:
        return claims[0].source_modality
    return "unknown"


def _retrieval_view_for_checkpoint(checkpoint_type: str) -> str:
    if checkpoint_type == "historical_truth":
        return "historical_at"
    if checkpoint_type in {"conflict_audit", "source_trust_conflict"}:
        return "conflicts"
    return "current"


def _decision_action_for_checkpoint(checkpoint_type: str) -> DecisionAction:
    if checkpoint_type == "historical_truth":
        return DecisionAction.ANSWER_HISTORICAL_TRUTH
    if checkpoint_type == "execution_continuation":
        return DecisionAction.CONTINUE_EXECUTION_BRANCH
    if checkpoint_type in {"entity_reconstruction", "claim_rekey", "entity_split_repair", "conflict_audit"}:
        return DecisionAction.RECONSTRUCT_GRAPH
    if checkpoint_type == "abstention":
        return DecisionAction.ABSTAIN
    if checkpoint_type == "source_trust_conflict":
        return DecisionAction.EXPOSE_CONFLICT
    return DecisionAction.ANSWER_CURRENT_TRUTH
