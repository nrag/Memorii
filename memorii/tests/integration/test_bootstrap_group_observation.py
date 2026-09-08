"""Audit construction consumes an actual public-provider native commit."""

from __future__ import annotations

import pytest

from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
from memorii.core.memory_evolution.bootstrap_group_observation import (
    BootstrapGroupObservationAuditError,
    build_bootstrap_group_observation_audit,
    build_native_group_observation_delta,
)
from memorii.core.memory_evolution.graph_planning import PlanningCommitValues
from tests.unit.core.semantic_ingestion.test_bootstrap_graph_observation_retention import _capture_builtin_fact_planning
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import TEST_NOW


def test_audit_binds_actual_native_graph_and_retained_mentions(monkeypatch):
    captured = []
    commit = SemanticIngestionAtomicStore.commit_or_reload_bootstrap_graph_group_v3
    def capture(self, *, request):
        graph = self.graph_state_snapshot()
        reference = self.reference_integrity_snapshot()
        result = commit(self, request=request)
        after = self.graph_state_snapshot()
        before_by_key = {(record.payload_record_kind, record.record_id): record.record_digest for record in graph.records}
        changed = tuple(record.payload for record in after.records if before_by_key.get((record.payload_record_kind, record.record_id)) != record.record_digest)
        captured.append(dict(request=request, current_graph_snapshot=graph,
            materialized_graph_records=changed, prior_reference_integrity=reference,
            next_reference_integrity=self.reference_integrity_snapshot(),
            commit_values=PlanningCommitValues(transaction_group_id=request.transaction_group_id,
                graph_revision_before=result.persisted_result.core.graph_revision_before,
                graph_revision_after=result.persisted_result.core.graph_revision_after, committed_at=TEST_NOW)))
        return result
    monkeypatch.setattr(SemanticIngestionAtomicStore, "commit_or_reload_bootstrap_graph_group_v3", capture)
    _, _, request = _capture_builtin_fact_planning(monkeypatch)
    assert len(captured) == 1
    inputs = captured[0]
    audit = build_bootstrap_group_observation_audit(**inputs)
    delta = audit.graph_revision_delta
    assert delta is not None
    observation = build_native_group_observation_delta(
        request=request, audit=audit, materialized_graph_records=inputs["materialized_graph_records"],
        observation_revision_before="genesis", observation_revision_after="next",
        observation_schema_fingerprint="a" * 64,
    )
    assert observation.graph_revision_delta_digest == delta.delta_digest
    assert observation.operation_ids == request.operation_ids
    assert len(delta.record_changes) == len(inputs["materialized_graph_records"])
    assert tuple(record.operation_id for record in audit.operation_introductions) == request.operation_ids
    assert tuple(record.operation_id for record in audit.operation_terminal_outcomes) == request.operation_ids
    assert all(record.execution_manifest_digest == request.pre_execution_manifest_identity.identity_digest for record in audit.operation_terminal_outcomes)
    retained = request.ordered_operation_inputs[0].reduction.effect_materialization.accepted_effect.observation_mention_bindings
    assert {(record.mention_span, record.entity_revision_id, record.logical_entity_id) for record in audit.source_introductions} == {
        (binding.mention_span, binding.target_candidate.entity_revision_id, binding.target_candidate.logical_entity_id) for binding in retained
    }
    for records in ((), inputs["materialized_graph_records"][:-1], (*inputs["materialized_graph_records"], inputs["materialized_graph_records"][0])):
        with pytest.raises(BootstrapGroupObservationAuditError):
            build_bootstrap_group_observation_audit(**{**inputs, "materialized_graph_records": records})
