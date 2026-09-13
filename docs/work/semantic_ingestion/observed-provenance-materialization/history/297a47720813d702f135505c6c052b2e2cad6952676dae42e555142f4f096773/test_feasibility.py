"""Real native planning fields establish recipe feasibility, not certification."""
import pytest
from feasibility import retained_context
from memorii.core.semantic_ingestion.contracts import BootstrapNativeFactEffectV3
from tests.unit.core.semantic_ingestion.test_bootstrap_graph_observation_retention import _capture_builtin_fact_planning


def test_retained_fact_context_has_complete_deterministic_recipe(monkeypatch):
    _, _, request = _capture_builtin_fact_planning(monkeypatch)
    reduction = request.ordered_operation_inputs[0].reduction
    compilation = reduction.native_compilation
    effect = reduction.effect_materialization.accepted_effect
    assert isinstance(effect, BootstrapNativeFactEffectV3)
    authority = compilation.operation_input.planning_construction_authority
    assert authority is not None
    for projection in effect.evidence_projections:
        ancestry, policies = retained_context(compilation, effect, projection)
        construction = next(item for item in authority.evidence_constructions
                            if item.evidence_item_digest == projection.evidence_item_digest)
        assert ancestry == tuple(sorted(set((
            compilation.compilation_digest, authority.authority_digest,
            authority.source_authority_evidence.evidence_digest,
            authority.source_authority_evidence.provenance_digest,
            construction.evidence_digest, projection.projection_digest, effect.effect_digest,
        ))))
        expected = [authority.predicate_registry_fingerprint,
                    authority.predicate_state_rule.policy_fingerprint, authority.action_policy_fingerprint]
        expected.extend(item.temporal_policy_fingerprint for item in authority.temporal_constructions)
        bundle = authority.arbitration_policy_bundle
        if bundle is not None:
            expected.extend((bundle.trust_policy.fingerprint, bundle.temporal_policy.fingerprint))
        assert policies == tuple(sorted(set(expected)))
        bad = projection.model_copy(update={"operation_execution_id": "0" * 64})
        with pytest.raises(ValueError):
            retained_context(compilation, effect, bad)
        bad = projection.model_copy(update={"citation_record": projection.provenance_record})
        with pytest.raises(ValueError):
            retained_context(compilation, effect.model_copy(update={"evidence_projections": (bad,)}), bad)
