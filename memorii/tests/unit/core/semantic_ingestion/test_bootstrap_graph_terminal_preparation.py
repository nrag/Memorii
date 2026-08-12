from types import SimpleNamespace

import pytest
from memorii.core.semantic_ingestion.bootstrap_graph_terminal_preparation import (
    DeterministicBootstrapGraphTerminalPreparationV3,
)


class _Preparation(DeterministicBootstrapGraphTerminalPreparationV3):
    """Keep these boundary tests focused on validation before carrier assembly."""

    def execution_manifest(self, *, construction: object) -> object:
        return construction.manifest


def _inputs() -> tuple[SimpleNamespace, ...]:
    fence = SimpleNamespace(binding_digest="a" * 64)
    request = SimpleNamespace(
        request_digest="b" * 64,
        authenticated_ingress=SimpleNamespace(
            delivery_principal_binding=SimpleNamespace(binding_digest="c" * 64)
        ),
        required_outcome_scopes=SimpleNamespace(scope_set_digest="d" * 64),
        initial_control_epoch=SimpleNamespace(operation_fence_binding=fence),
    )
    epoch = SimpleNamespace(epoch_digest="e" * 64)
    generation = SimpleNamespace(request_digest="b" * 64, control_epoch_digest="e" * 64)
    attempt = SimpleNamespace(attempt_digest="f" * 64, request_digest="b" * 64, transaction_group_plan_digest="0" * 64)
    plan = SimpleNamespace(plan_digest="0" * 64)
    lineage = SimpleNamespace(
        lineage_digest="1" * 64, request_digest="b" * 64,
        entries=(SimpleNamespace(source_id="source", source_digest="2" * 64, preparation_fingerprint="3" * 64),),
    )
    manifest = SimpleNamespace()
    construction = SimpleNamespace(
        request_digest="b" * 64, attempt_digest="f" * 64,
        transaction_group_plan_digest="0" * 64, source_plan_lineage_digest="1" * 64,
        control_epoch_digest="e" * 64, manifest=manifest,
    )
    authority = SimpleNamespace(
        source_id="source", source_digest="2" * 64, preparation_fingerprint="3" * 64,
        segment_governance_carriers="segment", message_admission_carriers="message",
        governance_carrier_artifact="governance", required_outcome_scopes=request.required_outcome_scopes,
        delivery_principal_binding_digest="c" * 64, operation_fence_binding=fence,
    )
    manifest.segment_governance_carriers = authority.segment_governance_carriers
    manifest.message_admission_carriers = authority.message_admission_carriers
    manifest.governance_carrier_artifact = authority.governance_carrier_artifact
    return request, epoch, generation, attempt, plan, construction, lineage, authority


@pytest.mark.parametrize("field, value", [("source_digest", "wrong"), ("delivery_principal_binding_digest", "wrong")])
def test_preparation_rejects_host_authority_substitution_before_assembly(field: str, value: str) -> None:
    request, epoch, generation, attempt, plan, construction, lineage, authority = _inputs()
    setattr(authority, field, value)

    with pytest.raises(ValueError, match="host authority is substituted"):
        _Preparation().validate_host_authority(
            request=request,
            complete_lineage=lineage,
            manifest=construction.manifest,
            host_authority=authority,
        )
