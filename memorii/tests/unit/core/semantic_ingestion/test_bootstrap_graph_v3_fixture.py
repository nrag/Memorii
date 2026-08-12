from types import SimpleNamespace

import pytest
from memorii.core.semantic_ingestion.bootstrap_graph_artifact_assembler import (
    BootstrapGraphArtifactAssemblerV3,
)
from memorii.core.semantic_ingestion.contracts import (
    GraphDependentExecutionPolicyReferenceV3,
)
from tests.fixtures.semantic_ingestion.bootstrap_graph_v3_fixture import (
    DeterministicBootstrapGraphPlanCompilerV3,
    DeterministicBootstrapGraphPlanningAuthorizerV3,
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
