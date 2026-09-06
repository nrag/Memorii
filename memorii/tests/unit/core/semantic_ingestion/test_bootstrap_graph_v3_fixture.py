import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from memorii.core.memory_evolution.graph_planning import GraphPlanningState
from memorii.core.memory_evolution.transaction_coordinator import GraphReadSetToken
from memorii.core.memory_plane import JsonlMemoryPlaneStore, MemoryPlaneService
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.semantic_ingestion.contracts import (
    BootstrapTransactionGroupOperationPlanV3,
    BootstrapTransactionGroupPlanMemberV3,
    GraphDependentExecutionPolicyReferenceV3,
    contract_digest,
)
from memorii.domain.enums import CommitStatus, MemoryDomain
from tests.fixtures.semantic_ingestion.bootstrap_graph_v3_fixture import (
    DeterministicBootstrapGraphPlanCompilerV3,
    build_empty_capability_registry,
    build_empty_graph_snapshot_bundle,
    build_graph_policy_reference,
    build_minimal_bootstrap_graph_plan_compilation_v3,
    digest,
)


def _request(*, snapshot: object, policy: object, capability_registry: object) -> SimpleNamespace:
    group = SimpleNamespace(
        group_id=digest("group"),
        operation_ids=(digest("operation"),),
        proposal_digests=(digest("proposal"),),
        member_digests=(digest("member"),),
        segment_ids=(digest("segment"),),
    )
    epoch = SimpleNamespace(
        request_core_digest=digest("request-core"),
        epoch_digest=digest("epoch"),
        operation_lease_binding=SimpleNamespace(binding_digest=digest("lease")),
        operation_fence_binding=SimpleNamespace(binding_digest=digest("fence")),
        writer_commit_binding=SimpleNamespace(binding_digest=digest("writer")),
    )
    return SimpleNamespace(
        request_core_digest=digest("request-core"),
        request_digest=digest("request"),
        normalization_replay=SimpleNamespace(
            replay_digest=digest("replay"),
            source_normalization_result=SimpleNamespace(result_digest=digest("result")),
        ),
        source_alignment=SimpleNamespace(alignment_digest=digest("alignment")),
        source_dependency_groups=(group,),
        initial_control_epoch=epoch,
        graph_authority=SimpleNamespace(
            snapshot=snapshot,
            execution_policy=policy,
            capability_registry_snapshot=capability_registry,
        ),
        authenticated_ingress=SimpleNamespace(
            delivery_principal_binding=SimpleNamespace(binding_digest=digest("principal")),
        ),
        required_outcome_scopes=SimpleNamespace(
            required_scope_set_digest=digest("scopes")
        ),
    )


def test_build_minimal_bootstrap_graph_plan_compilation_v3_requires_retained_reduction_authority() -> None:
    snapshot = build_empty_graph_snapshot_bundle()
    policy = build_graph_policy_reference()
    capability_registry = build_empty_capability_registry()
    with pytest.raises(ValueError, match="retained reduction authority is incomplete"):
        build_minimal_bootstrap_graph_plan_compilation_v3(
            request=_request(
                snapshot=snapshot,
                policy=policy,
                capability_registry=capability_registry,
            ),
            snapshot=snapshot,
            policy=policy,
            capability_registry=capability_registry,
            operation_inputs=(),
        )


def test_build_minimal_bootstrap_graph_plan_compilation_v3_rejects_cross_request_policy() -> None:
    snapshot = build_empty_graph_snapshot_bundle()
    capability_registry = build_empty_capability_registry()
    request_policy = build_graph_policy_reference()
    foreign_policy = GraphDependentExecutionPolicyReferenceV3.create(
        repository_id="tests.bootstrap-graph-v3.foreign",
        repository_contract_fingerprint=digest("foreign-repository-contract"),
        policy_digest=digest("foreign-policy"),
        artifact_digest=digest("foreign-policy-artifact"),
    )
    request = _request(
        snapshot=snapshot,
        policy=request_policy,
        capability_registry=capability_registry,
    )

    with pytest.raises(ValueError, match="authority is substituted"):
        build_minimal_bootstrap_graph_plan_compilation_v3(
            request=request,
            snapshot=snapshot,
            policy=foreign_policy,
            capability_registry=capability_registry,
            operation_inputs=(),
        )


def test_group_member_rejects_digest_recomputed_cross_snapshot_read_token(
    tmp_path,
) -> None:
    snapshot = build_empty_graph_snapshot_bundle()
    state = GraphPlanningState.create(
        base_snapshot_digest=snapshot.snapshot_digest,
        records=(),
        codec_manifest_fingerprint=(
            snapshot.graph_snapshot.codec_manifest_fingerprint
        ),
        applied_planned_delta_digests=(),
    )
    operation = BootstrapTransactionGroupOperationPlanV3.create(
        operation_id=digest("operation"),
        operation_execution_id=digest("operation-execution"),
        proposal_digest=digest("proposal"),
        member_digests=(digest("member"),),
        segment_ids=(digest("segment"),),
        dependency_group_ids=(digest("group"),),
        planning_result=None,
    )
    versions = {
        item.partition_id: item.version
        for item in snapshot.base_read_set.partition_versions
    }
    valid_token = GraphReadSetToken.create(
        graph_revision=snapshot.graph_snapshot.graph_revision,
        replay_state_digest=versions["canonical_graph"],
        reference_ledger_digest=versions["reference_ledger"],
    )
    valid = BootstrapTransactionGroupPlanMemberV3.create(
        transaction_group_id=digest("group"),
        source_dependency_group_digest=digest("group"),
        sealed_graph_snapshot_digest=snapshot.snapshot_digest,
        graph_read_set=valid_token,
        sealed_graph_read_set=snapshot.base_read_set,
        reference_integrity_ledger_digest=versions["reference_ledger"],
        planning_state_before=state,
        operation_plans=(operation,),
        planning_state_after=state,
        required_reservation_digests=(),
    )
    substituted = GraphReadSetToken.create(
        graph_revision=snapshot.graph_snapshot.graph_revision,
        replay_state_digest=digest("foreign-replay-state"),
        reference_ledger_digest=versions["reference_ledger"],
    )
    digest_body = {
        name: getattr(valid, name)
        for name in type(valid).model_fields
        if name != "member_digest"
    }
    digest_body["graph_read_set"] = substituted
    malformed = valid.model_dump(mode="json")
    malformed["graph_read_set"] = substituted.model_dump(mode="json")
    malformed["member_digest"] = contract_digest(
        BootstrapTransactionGroupPlanMemberV3._digest_domain, digest_body,
    )

    for path in (None, tmp_path / "malformed-read-set-jsonl"):
        plane = MemoryPlaneService(
            record_store=(
                None
                if path is None
                else JsonlMemoryPlaneStore(path)
            )
        )
        plane.upsert_record(CanonicalMemoryRecord(
            memory_id="malformed-read-set",
            domain=MemoryDomain.EXECUTION,
            text="",
            content={"member": malformed},
            status=CommitStatus.COMMITTED,
            source_kind="bootstrap_graph_malformed_read_set_fixture",
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        ))
        if path is not None:
            plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
        persisted = plane.get_record("malformed-read-set")
        assert persisted is not None
        with pytest.raises(
            ValueError, match="bootstrap graph plan member read set is inconsistent"
        ):
            BootstrapTransactionGroupPlanMemberV3.model_validate_json(
                json.dumps(persisted.content["member"])
            )
        assert not plane.list_records(
            source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_effect"
        )


def test_fixture_compiler_and_authorizer_construct_one_public_authorization() -> None:
    snapshot = build_empty_graph_snapshot_bundle()
    policy = build_graph_policy_reference()
    capability_registry = build_empty_capability_registry()
    request = _request(
        snapshot=snapshot,
        policy=policy,
        capability_registry=capability_registry,
    )
    compiler = DeterministicBootstrapGraphPlanCompilerV3(
        snapshot=snapshot,
        policy=policy,
        capability_registry=capability_registry,
        operation_inputs=(),
    )
    with pytest.raises(ValueError, match="retained reduction authority is incomplete"):
        compiler.compile(request=request, control_epoch=request.initial_control_epoch)
