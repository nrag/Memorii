from types import SimpleNamespace

import pytest
from memorii.core.semantic_ingestion.bootstrap_graph_artifact_assembler import (
    BootstrapGraphArtifactAssemblerV3,
)
from tests.fixtures.semantic_ingestion.bootstrap_graph_v3_fixture import (
    PersistedBootstrapGraphReplayFixture,
    build_graph_epoch_transition_request,
)


def _attempt(**overrides: object) -> SimpleNamespace:
    values = {
        "request_digest": "a" * 64,
        "normalization_replay_digest": "b" * 64,
        "attempt_digest": "c" * 64,
        "transaction_group_plan_digest": "d" * 64,
        "control_epoch_digest": "e" * 64,
        "sealed_read_set_digest": "f" * 64,
        "normalization_result_digest": "0" * 64,
        "operation_fence_binding_digest": "1" * 64,
        "writer_commit_binding_digest": "2" * 64,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_group_cas_request_rejects_substituted_authorization() -> None:
    member = SimpleNamespace(transaction_group_id="3" * 64, member_digest="4" * 64)
    authorization = SimpleNamespace(
        transaction_group_id="3" * 64, group_plan_member_digest="wrong",
    )
    lineage = SimpleNamespace(
        transaction_group_id="3" * 64, attempt_digest="c" * 64,
        group_plan_member_digest="4" * 64, planning_authorization_digest="5" * 64,
        control_epoch_digest="e" * 64,
    )
    with pytest.raises(ValueError, match="substituted"):
        BootstrapGraphArtifactAssemblerV3.group_cas_request(
            request_digest="a" * 64, normalization_replay_digest="b" * 64,
            attempt=_attempt(), member=member, authorization=authorization, lineage=lineage,
            pre_execution_manifest_identity_digest="6" * 64,
        )


def test_terminal_request_rejects_generation_mismatch_before_schema_construction() -> None:
    core = SimpleNamespace(request_digest="a" * 64, transaction_group_plan_digest="d" * 64, control_epoch_digest="e" * 64)
    intent = SimpleNamespace(
        request_digest="a" * 64, control_epoch_digest="e" * 64,
        expected_operation_generation=2, expected_artifact_generation=2,
    )
    handoff = SimpleNamespace(core=core, publication_intent=intent)
    with pytest.raises(ValueError, match="substituted"):
        BootstrapGraphArtifactAssemblerV3.build_terminal_publication_request(
            coordinator_request=object(), control_epoch=object(), final_attempt=_attempt(),
            final_plan=object(), complete_lineage=object(), execution_manifest=object(),
            ordered_group_result_constructions=(SimpleNamespace(attempt_digest="c" * 64),),
            canonical_source_result_input=object(), handoff_core=core, publication_intent=intent,
            handoff=handoff,
            predecessor_generation=SimpleNamespace(
                operation_generation=3, artifact_generation=3,
            ), delivery_principal_binding_digest="b" * 64,
            required_outcome_scopes=object(), operation_lease_binding=object(),
            operation_fence_binding=object(), writer_commit_binding=object(),
        )


def test_pre_execution_identity_closure_rejects_evidence_projection_substitution() -> None:
    group_id = "3" * 64
    plan = SimpleNamespace(plan_digest="4" * 64, group_members=(SimpleNamespace(transaction_group_id=group_id),))
    attempt = _attempt(
        attempt_context=SimpleNamespace(ordered_pre_execution_evidence_digests=("5" * 64,)),
        transaction_group_plan_digest="4" * 64,
    )
    compilation = SimpleNamespace(
        plan=plan, request_digest="a" * 64, normalization_replay_digest="b" * 64,
        control_epoch_digest="e" * 64, manifest_group_inputs=(), pre_execution_evidence=(),
        attempt_construction_inputs=SimpleNamespace(ordered_pre_execution_evidence_digests=("5" * 64,)),
    )
    lineage = SimpleNamespace(
        request_digest="a" * 64, normalization_replay_digest="b" * 64,
        control_epoch_digest="e" * 64, latest_entry_by_group=(), entries=(),
    )
    with pytest.raises(ValueError, match="inputs are substituted"):
        BootstrapGraphArtifactAssemblerV3.build_pre_execution_identity_closure(
            compilation=compilation, attempt=attempt, plan=plan, lineage=lineage,
            host_authority=object(),
        )


def test_pre_execution_identity_closure_rejects_foreign_lineage_entry() -> None:
    group_id = "3" * 64
    member = SimpleNamespace(transaction_group_id=group_id, member_digest="4" * 64)
    plan = SimpleNamespace(plan_digest="5" * 64, group_members=(member,))
    attempt = _attempt(
        transaction_group_plan_digest="5" * 64, graph_snapshot_digest="x" * 64,
        reconciliation_digest="y" * 64, reference_closure_digest="z" * 64,
        capability_binding_digests=(),
    )
    evidence = SimpleNamespace(
        transaction_group_id=group_id, evidence_digest="6" * 64,
        request_digest="a" * 64, normalization_replay_digest="b" * 64,
        group_plan_member_digest="4" * 64, graph_snapshot_digest="x" * 64,
        sealed_read_set_digest="f" * 64, reconciliation_digest="y" * 64,
        reference_closure_digest="z" * 64, control_epoch_digest="e" * 64,
    )
    compilation = SimpleNamespace(
        plan=plan, request_digest="a" * 64, normalization_replay_digest="b" * 64,
        control_epoch_digest="e" * 64,
        manifest_group_inputs=(SimpleNamespace(transaction_group_id=group_id, group_plan_member=member),),
        pre_execution_evidence=(evidence,),
        attempt_construction_inputs=SimpleNamespace(ordered_pre_execution_evidence_digests=("6" * 64,)),
    )
    lineage = SimpleNamespace(
        request_digest="a" * 64, normalization_replay_digest="b" * 64,
        control_epoch_digest="e" * 64, latest_entry_by_group=((group_id, "7" * 64),), entries=(),
    )
    with pytest.raises(ValueError, match="group closure is substituted"):
        BootstrapGraphArtifactAssemblerV3.build_pre_execution_identity_closure(
            compilation=compilation, attempt=attempt, plan=plan, lineage=lineage,
            host_authority=SimpleNamespace(
                operation_fence_binding=SimpleNamespace(binding_digest="1" * 64),
                capability_bindings=(), source_id="source", source_digest="8" * 64,
                preparation_fingerprint="9" * 64,
            ),
        )


def test_durable_retry_rejects_unavailable_epoch_substitution() -> None:
    unavailable = SimpleNamespace(request_digest="a" * 64, control_epoch_digest="wrong")
    with pytest.raises(ValueError, match="substituted"):
        BootstrapGraphArtifactAssemblerV3.durable_retry(
            unavailable=unavailable, attempt=_attempt(), source_plan_lineage_digest="6" * 64,
            completed_group_result_digests=(), retry_group_ids=("7" * 64,), reason="storage_retry",
        )


def test_graph_epoch_fixture_rejects_foreign_replay_authority() -> None:
    fixture = PersistedBootstrapGraphReplayFixture(
        replay=SimpleNamespace(replay_digest="a" * 64),
        delivery_principal_binding_digest="b" * 64,
        required_outcome_scopes=SimpleNamespace(scope_set_digest="c" * 64),
        operation_fence_binding=object(), operation_lease_binding=object(),
        writer_commit_binding=object(), control_epoch=SimpleNamespace(required_scope_set_digest="c" * 64),
    )
    authority = SimpleNamespace(
        normalization_replay_digest="0" * 64,
        operation_fence_binding=fixture.operation_fence_binding,
        operation_lease_binding=fixture.operation_lease_binding,
        writer_commit_binding=fixture.writer_commit_binding,
        required_scope_set_digest="c" * 64,
        delivery_principal_binding_digest="b" * 64,
    )
    with pytest.raises(ValueError, match="authority is substituted"):
        build_graph_epoch_transition_request(
            fixture=fixture, graph_authority=authority,
            source_alignment=SimpleNamespace(source_dependency_groups=()),
        )
