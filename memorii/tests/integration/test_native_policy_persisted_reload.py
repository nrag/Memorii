"""Durable public-path proof for retained native policy bundles."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.memory_plane import JsonlMemoryPlaneStore, MemoryPlaneService
from memorii.core.semantic_ingestion.contracts import (
    AcceptedTemporalEvidence,
    BootstrapGraphGroupCommitRequestV3,
    BootstrapNativePlanningConstructionAuthorityV3,
    BootstrapNativeTemporalConstructionV3,
    OperationTemporalDecisionBinding,
    PredicateTrustRule,
    SemanticArbitrationPolicyBundle,
    TemporalEvidenceDecisionClosure,
    TrustPolicySnapshot,
    contract_digest,
    decode_semantic_contract,
    encode_semantic_contract,
)
from tests.unit.core.semantic_ingestion.test_bootstrap_graph_observation_retention import (
    _capture_builtin_fact_planning,
)


def _create_authority(
    authority: BootstrapNativePlanningConstructionAuthorityV3,
    **updates: object,
) -> BootstrapNativePlanningConstructionAuthorityV3:
    values = {
        name: getattr(authority, name)
        for name in type(authority).model_fields
        if name not in {"schema_version", "authority_digest"}
    }
    values.update(updates)
    return BootstrapNativePlanningConstructionAuthorityV3.create(**values)


def _rebuild_closure(
    closure: TemporalEvidenceDecisionClosure,
    **updates: object,
) -> TemporalEvidenceDecisionClosure:
    values = {
        name: getattr(closure, name)
        for name in type(closure).model_fields
        if name != "closure_digest"
    }
    values.update(updates)
    return TemporalEvidenceDecisionClosure(
        **values,
        closure_digest=contract_digest(
            b"memorii.semantic-ingestion.temporal-decision-closure.v1", values
        ),
    )


def _rebuild_construction(
    construction: BootstrapNativeTemporalConstructionV3,
    *,
    closure: TemporalEvidenceDecisionClosure | None = None,
    **updates: object,
) -> BootstrapNativeTemporalConstructionV3:
    selected_closure = (
        construction.accepted_temporal_evidence.decision_closure
        if closure is None
        else closure
    )
    decision = construction.temporal_decision_binding
    binding = OperationTemporalDecisionBinding.create(
        operation_id=decision.operation_id,
        temporal_role=decision.temporal_role,
        scope_assessment_digest=decision.scope_assessment_digest,
        semantic_assessment_digest=decision.semantic_assessment_digest,
        temporal_attachment=decision.temporal_attachment,
        reference_evidence=decision.reference_evidence,
        decision_closure=selected_closure,
    )
    values = {
        "temporal_role": construction.temporal_role,
        "temporal_consensus_digest": construction.temporal_consensus_digest,
        "effective_time": construction.effective_time,
        "accepted_temporal_evidence": AcceptedTemporalEvidence(
            reference_evidence=construction.accepted_temporal_evidence.reference_evidence,
            decision_closure=selected_closure,
        ),
        "temporal_decision_binding": binding,
        "temporal_policy_fingerprint": construction.temporal_policy_fingerprint,
    }
    values.update(updates)
    return BootstrapNativeTemporalConstructionV3.create(**values)


def test_public_fact_persists_exact_bundle_and_rejects_coordinate_substitution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plane_path = tmp_path / "native-policy-retention"
    memory_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(plane_path))
    request, _plan, group_request = _capture_builtin_fact_planning(
        monkeypatch,
        memory_plane=memory_plane,
    )
    authority = request.operation_input.planning_construction_authority
    assert authority is not None
    retained_input = group_request.ordered_operation_inputs[0].reduction.native_compilation.operation_input
    assert retained_input == request.operation_input
    assert retained_input.planning_construction_authority == authority
    bundle = authority.arbitration_policy_bundle
    assert bundle is not None
    source_bundle_bytes = encode_typed_value(bundle.model_dump(mode="python"))
    source_request_bytes = encode_semantic_contract(group_request)

    reopened = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(plane_path))
    primaries = reopened.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    )
    assert len(primaries) == 1
    persisted_request = decode_semantic_contract(
        bytes.fromhex(primaries[0].content["request_hex"]),
        BootstrapGraphGroupCommitRequestV3,
    )
    assert encode_semantic_contract(persisted_request) == source_request_bytes
    persisted_authority = (
        persisted_request.ordered_operation_inputs[0]
        .reduction.native_compilation.operation_input.planning_construction_authority
    )
    assert persisted_authority is not None
    assert persisted_authority.arbitration_policy_bundle is not None
    assert encode_typed_value(
        persisted_authority.arbitration_policy_bundle.model_dump(mode="python")
    ) == source_bundle_bytes

    dropped = persisted_request.model_dump(mode="python")
    dropped_authority = (
        dropped["ordered_operation_inputs"][0]["reduction"]["native_compilation"]
        ["operation_input"]["planning_construction_authority"]
    )
    assert isinstance(dropped_authority, dict)
    dropped_authority.pop("arbitration_policy_bundle")
    with pytest.raises(ValueError, match="authority_digest mismatch"):
        BootstrapGraphGroupCommitRequestV3.model_validate(dropped)

    assert _create_authority(authority) == authority
    empty_temporal = _create_authority(authority, temporal_constructions=())
    assert empty_temporal.arbitration_policy_bundle == bundle
    assert authority.predicate_trust_rule == bundle.trust_policy.rule_for(
        authority.predicate_trust_rule.predicate_id
    )
    construction = authority.temporal_constructions[0]
    closure = construction.accepted_temporal_evidence.decision_closure
    for field, value in (
        ("temporal_policy_fingerprint", "0" * 64),
        ("temporal_policy_snapshot_digest", "0" * 64),
        ("trust_policy_fingerprint", "0" * 64),
        ("trust_policy_snapshot_digest", "0" * 64),
        ("arbitration_as_of", bundle.arbitration_as_of + timedelta(seconds=1)),
    ):
        with pytest.raises(ValueError, match="policy authority"):
            _create_authority(
                authority,
                temporal_constructions=(
                    _rebuild_construction(
                        construction,
                        closure=_rebuild_closure(closure, **{field: value}),
                    ),
                ),
            )
    for field in ("temporal_policy_fingerprint", "temporal_policy_snapshot_digest"):
        effective_values = {
            name: getattr(construction.effective_time, name)
            for name in type(construction.effective_time).model_fields
        }
        effective_values[field] = "0" * 64
        with pytest.raises(ValueError, match="policy authority"):
            _create_authority(
                authority,
                temporal_constructions=(
                    _rebuild_construction(
                        construction,
                        effective_time=type(construction.effective_time)(**effective_values),
                    ),
                ),
            )
    with pytest.raises(ValueError, match="policy authority"):
        _create_authority(
            authority,
            temporal_constructions=(
                _rebuild_construction(
                    construction,
                    temporal_policy_fingerprint="0" * 64,
                ),
            ),
        )
    different_rule = authority.predicate_trust_rule.model_copy(
        update={"authority_rank_by_class": {"official": 11}}
    )
    with pytest.raises(ValueError, match="policy rule"):
        _create_authority(authority, predicate_trust_rule=different_rule)
    different_trust = TrustPolicySnapshot.create(
        policy_revision="native-policy-retention-substitute",
        system_effective_interval=bundle.trust_policy.system_effective_interval,
        rules=(PredicateTrustRule(**authority.predicate_trust_rule.model_dump(mode="python")),),
    )
    substituted_bundle = SemanticArbitrationPolicyBundle.create(
        trust_policy=different_trust,
        temporal_policy=bundle.temporal_policy,
        arbitration_as_of=bundle.arbitration_as_of + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="policy (rule|authority)"):
        _create_authority(authority, arbitration_policy_bundle=substituted_bundle)
