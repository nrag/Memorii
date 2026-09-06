from hashlib import sha256

import pytest
from memorii.core.semantic_ingestion.contracts import (
    BootstrapGraphAtomicMemberReferenceV3,
    BootstrapGraphObservedCountersV3,
    BootstrapGraphPlannedProgressV3,
    BootstrapGraphPlanPublishedProgressV3,
    BootstrapGraphReplanClosureReferenceV3,
    decode_bootstrap_graph_atomic_member_payload_v3,
    encode_bootstrap_graph_atomic_member_payload_v3,
)


def _digest(label: str) -> str:
    return sha256(label.encode()).hexdigest()


def _reference(repository_id: str, member_id: str, member_kind: str, payload_type: str) -> BootstrapGraphAtomicMemberReferenceV3:
    return BootstrapGraphAtomicMemberReferenceV3.create(
        repository_id=repository_id, artifact_digest=_digest(repository_id), generation=1,
        member_id=member_id, member_kind=member_kind,
        member_payload_digest=_digest(member_id), payload_type=payload_type,
    )


def test_native_progress_codec_round_trips_only_the_native_member_type() -> None:
    plan = _reference("semantic_ingestion.bootstrap_graph_plan.v3", "plan", "bootstrap_transaction_group_plan", "BootstrapTransactionGroupPlanV3")
    replay = _reference("semantic_ingestion.bootstrap_graph_replay_bundle.v3", "replay-bundle", "bootstrap_graph_replay_bundle", "BootstrapGraphReplayBundleV3")
    counters = _reference("semantic_ingestion.bootstrap_graph_observed_counters.v3", "observed-counters", "bootstrap_graph_observed_counters", "BootstrapGraphObservedCountersV3")
    progress = BootstrapGraphPlanPublishedProgressV3.create(
        source_id="source", source_digest=_digest("source"), preparation_fingerprint=_digest("preparation"),
        operation_id="operation", request_digest=_digest("request"), normalization_replay_digest=_digest("replay"),
        normalization_result_digest=_digest("result"), control_epoch_digest=_digest("epoch"),
        operation_fence_binding_digest=_digest("fence"), operation_lease_binding_digest=_digest("lease"),
        writer_commit_binding_digest=_digest("writer"), plan_reference=plan,
        replay_bundle_reference=replay, observed_counters_reference=counters,
    )
    raw = encode_bootstrap_graph_atomic_member_payload_v3(
        kind="bootstrap_graph_source_progress", artifact=progress,
    )
    assert decode_bootstrap_graph_atomic_member_payload_v3(
        kind="bootstrap_graph_source_progress", raw=raw,
    )["kind"] == "plan_published"


def test_native_reference_rejects_relabelled_member() -> None:
    with pytest.raises(ValueError, match="legal native member"):
        _reference("semantic_ingestion.bootstrap_graph_plan.v3", "plan", "bootstrap_graph_source_progress", "BootstrapTransactionGroupPlanV3")


def test_observed_counters_are_not_a_snapshot_alias() -> None:
    counters = BootstrapGraphObservedCountersV3.create(
        request_digest=_digest("request"), control_epoch_digest=_digest("epoch"),
        operation_fence_binding_digest=_digest("fence"), execution_policy_reference_digest=_digest("policy"),
        publication_generation=1, observed_operations=1, observed_groups=1,
        observed_fixed_point_rounds=0, observed_snapshot_records=0,
        observed_snapshot_partitions=0, observed_related_conflicts=0,
        observed_attempts=0, observed_read_set_extensions=0, observed_reservations=0,
        observed_lineage_entries=0, observed_replay_artifacts=1,
        observed_replay_bundle_bytes=1, observed_decode_depth=0,
    )
    assert counters.counters_digest != _digest("snapshot")


def test_planned_progress_digest_includes_its_null_manifest_default() -> None:
    plan = _reference("semantic_ingestion.bootstrap_graph_plan.v3", "plan", "bootstrap_transaction_group_plan", "BootstrapTransactionGroupPlanV3")
    replay = _reference("semantic_ingestion.bootstrap_graph_replay_bundle.v3", "replay-bundle", "bootstrap_graph_replay_bundle", "BootstrapGraphReplayBundleV3")
    counters = _reference("semantic_ingestion.bootstrap_graph_observed_counters.v3", "observed-counters", "bootstrap_graph_observed_counters", "BootstrapGraphObservedCountersV3")
    authority = _reference("semantic_ingestion.bootstrap_graph_authority.v3", "successor-authority", "bootstrap_graph_successor_attempt_authority", "BootstrapGraphAttemptAuthorityV3")
    attempt = _reference("semantic_ingestion.bootstrap_graph_attempt.v3", "attempt", "bootstrap_graph_dependent_attempt", "BootstrapGraphDependentAttemptV3")
    lineage = _reference("semantic_ingestion.bootstrap_source_plan_lineage.v3", "lineage", "bootstrap_source_plan_lineage", "BootstrapSourcePlanLineageV3")
    closure = _reference("semantic_ingestion.bootstrap_graph_pre_execution_identity_closure.v3", "pre-execution-identity-closure", "bootstrap_graph_pre_execution_identity_closure", "BootstrapGraphPreExecutionManifestIdentityClosureV3")
    progress = BootstrapGraphPlannedProgressV3.create(source_id="source", source_digest=_digest("source"), preparation_fingerprint=_digest("preparation"), operation_id="operation", request_digest=_digest("request"), normalization_replay_digest=_digest("replay"), normalization_result_digest=_digest("result"), control_epoch_digest=_digest("epoch"), operation_fence_binding_digest=_digest("fence"), operation_lease_binding_digest=_digest("lease"), writer_commit_binding_digest=_digest("writer"), plan_reference=plan, replay_bundle_reference=replay, observed_counters_reference=counters, authority_reference=authority, attempt_reference=attempt, lineage_reference=lineage, pre_execution_identity_closure_reference=closure)
    assert progress.execution_manifest_reference is None
    assert progress.pre_execution_identity_closure_reference == closure


def test_replan_closure_requires_canonical_predecessor_references() -> None:
    predecessor = _reference("semantic_ingestion.bootstrap_graph_progress.v3", "source-progress", "bootstrap_graph_source_progress", "BootstrapGraphSourceProgressV3")
    lineage = _reference("semantic_ingestion.bootstrap_source_plan_lineage.v3", "lineage", "bootstrap_source_plan_lineage", "BootstrapSourcePlanLineageV3")
    result = _reference("semantic_ingestion.bootstrap_group_result.v3", f"group-result:{'a' * 64}", "transaction_group_result", "BootstrapNativeGroupCommitTerminalConstructionV3")
    closure = BootstrapGraphReplanClosureReferenceV3.create(
        predecessor_planned_progress_reference=predecessor,
        predecessor_lineage_reference=lineage,
        canonical_final_result_references=(result,),
        unfinished_transaction_group_ids=("b" * 64,),
        replanned_transaction_group_ids=("b" * 64,),
    )
    assert closure.predecessor_planned_progress_reference == predecessor
    successor = BootstrapGraphPlanPublishedProgressV3.create(
        source_id="source", source_digest=_digest("source"),
        preparation_fingerprint=_digest("preparation"), operation_id="operation",
        request_digest=_digest("request"), normalization_replay_digest=_digest("replay"),
        normalization_result_digest=_digest("result"), control_epoch_digest=_digest("epoch"),
        operation_fence_binding_digest=_digest("fence"),
        operation_lease_binding_digest=_digest("lease"),
        writer_commit_binding_digest=_digest("writer"),
        plan_reference=_reference("semantic_ingestion.bootstrap_graph_plan.v3", "plan", "bootstrap_transaction_group_plan", "BootstrapTransactionGroupPlanV3"),
        replay_bundle_reference=_reference("semantic_ingestion.bootstrap_graph_replay_bundle.v3", "replay-bundle", "bootstrap_graph_replay_bundle", "BootstrapGraphReplayBundleV3"),
        observed_counters_reference=_reference("semantic_ingestion.bootstrap_graph_observed_counters.v3", "observed-counters", "bootstrap_graph_observed_counters", "BootstrapGraphObservedCountersV3"),
        predecessor_progress_reference=predecessor,
        replan_closure_reference=closure,
    )
    assert successor.predecessor_progress_reference == predecessor
    assert successor.replan_closure_reference == closure
    with pytest.raises(ValueError, match="replan closure"):
        BootstrapGraphReplanClosureReferenceV3.create(
            predecessor_planned_progress_reference=predecessor,
            predecessor_lineage_reference=lineage,
            canonical_final_result_references=(result,),
            unfinished_transaction_group_ids=("b" * 64,),
            replanned_transaction_group_ids=("c" * 64,),
        )
