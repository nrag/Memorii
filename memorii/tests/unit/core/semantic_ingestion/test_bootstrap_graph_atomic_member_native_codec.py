import json
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.graph_effect_contracts import (
    CanonicalSourceTerminalOutcomeCore,
    CanonicalSourceTerminalOutcomeRecord,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    decode_typed_value,
    encode_typed_value,
)
from memorii.core.memory_evolution.observation_persistence import (
    build_source_finalization_observation_delta,
)
from memorii.core.provider.models import ProviderOperation
from memorii.core.semantic_ingestion.contracts import (
    BOOTSTRAP_GRAPH_V3_ATOMIC_MEMBER_CODECS,
    BootstrapGraphOperationReductionV3,
    BootstrapGraphPlanAtomicMemberV3,
    BootstrapNativeGroupCommitTerminalConstructionV3,
    SemanticContractCodecError,
    decode_bootstrap_graph_atomic_member_payload_v3,
    encode_bootstrap_graph_atomic_member_payload_v3,
    rebuild_bootstrap_graph_effect_contracts,
    validate_bootstrap_graph_plan_atomic_members_v3,
)
from memorii.domain.enums import SourceModality
from pydantic import BaseModel, ConfigDict
from tests.fixtures.semantic_ingestion.clean_room_request_fixture import (
    build_clean_room_proposal_catalogs,
)
from tests.unit.core.semantic_ingestion.bootstrap_graph_production_roots_support import (
    graph_fact_proposal,
    provider_service,
)
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
    TEST_NOW,
    DeterministicTestHostBootstrapMaterialVerifier,
    _built_in_local_capability,
    _host_ingress,
    _v3_normalization_host_builder,
)


class _NativeProjection(BaseModel):
    projection: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class _RetiredGenericProjection(BaseModel):
    semantic_compilation: str

    model_config = ConfigDict(extra="forbid", frozen=True)


def _source_finalization_delta():
    material = build_clean_room_proposal_catalogs(
        source_id="source:native-source-finalization",
        source_digest=sha256(b"source:native-source-finalization").hexdigest(),
        source_text="Ada works.", require_text_digest=False,
    )
    outcome = CanonicalSourceTerminalOutcomeRecord.create(
        core=CanonicalSourceTerminalOutcomeCore.create(
            ingestion_record_kind="source_terminal_outcome",
            source_id=material.source_id, source_digest=material.source_digest,
            delivery_principal_binding_digest=sha256(b"principal").hexdigest(),
            delivery_key_digest=sha256(b"delivery").hexdigest(),
            segment_governance_carriers=material.governance_carrier_artifact.segment_governance,
            message_admission_carriers=material.governance_carrier_artifact.message_admissions,
            governance_carrier_artifact=material.governance_carrier_artifact,
            required_outcome_scopes=material.governance_carrier_artifact.required_outcome_scopes,
            operation_fence_id="fence:native-source-finalization",
            operation_ids=("operation:native-source-finalization",),
            final_status="evidence_only", group_result_digests=(),
        ), preparation_fingerprint=material.preparation_fingerprint,
    )
    return build_source_finalization_observation_delta(
        source_outcome=outcome,
        observation_delta_id="source-finalization:native",
        observation_revision_before="genesis",
        observation_revision_after="source-finalization:successor",
        observation_schema_fingerprint=sha256(b"schema").hexdigest(),
    )


def test_source_finalization_atomic_member_uses_its_native_codec() -> None:
    delta = _source_finalization_delta()
    kind = "bootstrap_graph_source_finalization_observation_delta"
    raw = encode_bootstrap_graph_atomic_member_payload_v3(kind=kind, artifact=delta)
    assert decode_bootstrap_graph_atomic_member_payload_v3(kind=kind, raw=raw) == (
        delta.model_dump(mode="python")
    )
    with pytest.raises(SemanticContractCodecError):
        decode_bootstrap_graph_atomic_member_payload_v3(
            kind="bootstrap_graph_canonical_source_result", raw=raw,
        )
    with pytest.raises(SemanticContractCodecError):
        encode_bootstrap_graph_atomic_member_payload_v3(
            kind=kind, artifact=_NativeProjection(projection="wrong-artifact"),
        )


def test_each_v3_atomic_member_kind_has_one_qualified_native_codec() -> None:
    assert len(BOOTSTRAP_GRAPH_V3_ATOMIC_MEMBER_CODECS) == 28
    assert len(set(BOOTSTRAP_GRAPH_V3_ATOMIC_MEMBER_CODECS.values())) == 28

    for kind, codec_key in BOOTSTRAP_GRAPH_V3_ATOMIC_MEMBER_CODECS.items():
        assert codec_key == f"bootstrap_graph_v3/{kind}/native"
        # These members deliberately require their native sealed artifact;
        # their positive proof belongs to the focused closure fixtures.
        if kind in {
                "transaction_group_result",
                "group_compilation_artifact",
            "bootstrap_graph_replay_bundle",
            "bootstrap_graph_observed_counters",
            "bootstrap_graph_source_progress",
            "bootstrap_graph_pre_execution_identity_closure",
            "bootstrap_graph_source_finalization_observation_delta",
        }:
            continue
        payload = encode_bootstrap_graph_atomic_member_payload_v3(
            kind=kind, artifact=_NativeProjection(projection=kind),
        )
        member = BootstrapGraphPlanAtomicMemberV3.create(
            member_id=kind,
            kind=kind,
            canonical_payload=payload,
            payload_digest=sha256(payload).hexdigest(),
        )
        assert decode_bootstrap_graph_atomic_member_payload_v3(
            kind=kind, raw=payload,
        ) == {"projection": kind}
        validate_bootstrap_graph_plan_atomic_members_v3((member,))


def test_atomic_member_decoder_rejects_cross_kind_and_retired_generic_payloads() -> None:
    first_kind, second_kind = tuple(BOOTSTRAP_GRAPH_V3_ATOMIC_MEMBER_CODECS)[:2]
    payload = encode_bootstrap_graph_atomic_member_payload_v3(
        kind=first_kind, artifact=_NativeProjection(projection="native"),
    )
    with pytest.raises(SemanticContractCodecError):
        decode_bootstrap_graph_atomic_member_payload_v3(kind=second_kind, raw=payload)

    with pytest.raises(SemanticContractCodecError):
        encode_bootstrap_graph_atomic_member_payload_v3(
            kind=first_kind,
            artifact=_RetiredGenericProjection(semantic_compilation="retired"),
        )


def test_v3_reduction_contract_cannot_represent_retired_generic_output() -> None:
    rebuild_bootstrap_graph_effect_contracts()
    with pytest.raises(ValueError):
        BootstrapGraphOperationReductionV3.model_validate({
            "schema_version": 3,
            "transaction_group_id": "0" * 64,
            "operation_id": "1" * 64,
            "proposal_digest": "2" * 64,
            "semantic_compilation": {},
            "terminal_outcome": {},
            "artifact_closure": {},
            "reduction_digest": "3" * 64,
        })


def test_native_member_recovery_codec_rebuilds_identity_authorities() -> None:
    """A fresh recovery process resolves deferred identity authority types."""
    rebuild_bootstrap_graph_effect_contracts()
    kind = "bootstrap_graph_dependent_attempt"
    payload = encode_bootstrap_graph_atomic_member_payload_v3(
        kind=kind, artifact=_NativeProjection(projection="recovery"),
    )
    assert decode_bootstrap_graph_atomic_member_payload_v3(
        kind=kind, raw=payload,
    ) == {"projection": "recovery"}


def _replace_first_key(value: object, key: str, replacement: object) -> bool:
    if isinstance(value, dict):
        if key in value:
            value[key] = replacement
            return True
        return any(
            _replace_first_key(item, key, replacement)
            for item in value.values()
        )
    if isinstance(value, list):
        return any(_replace_first_key(item, key, replacement) for item in value)
    return False


def _source_modalities(value: object) -> tuple[SourceModality, ...]:
    if isinstance(value, SourceModality):
        return (value,)
    if isinstance(value, BaseModel):
        return tuple(
            modality
            for name in type(value).model_fields
            for modality in _source_modalities(getattr(value, name))
        )
    if isinstance(value, dict):
        return tuple(
            modality
            for item in value.values()
            for modality in _source_modalities(item)
        )
    if isinstance(value, (tuple, list, frozenset)):
        return tuple(
            modality for item in value for modality in _source_modalities(item)
        )
    return ()


def _replace_first_modality_string(value: object) -> bool:
    allowed = {item.value for item in SourceModality}
    if isinstance(value, dict):
        for key, item in value.items():
            if type(item) is str and item in allowed:
                value[key] = "not-a-modality"
                return True
            if _replace_first_modality_string(item):
                return True
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if type(item) is str and item in allowed:
                value[index] = "not-a-modality"
                return True
            if _replace_first_modality_string(item):
                return True
    elif isinstance(value, tuple):
        return any(_replace_first_modality_string(item) for item in value)
    return False


def test_transaction_group_result_json_round_trip_is_typed_and_fail_closed() -> None:
    normalization, _ = _v3_normalization_host_builder(proposal=graph_fact_proposal())
    service = provider_service(
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=(
            DeterministicTestHostBootstrapMaterialVerifier()
        ),
        source_normalization_host_bundle_builder=normalization,
    )
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="native-group-result-codec",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    record = next(
        item
        for item in service._memory_plane.list_records(
            source_kind="semantic_ingestion_bootstrap_graph_v3_member"
        )
        if item.content["member"]["kind"] == "transaction_group_result"
    )
    persisted_member = json.loads(json.dumps(record.content["member"]))
    member = BootstrapGraphPlanAtomicMemberV3.model_validate(
        persisted_member, strict=False
    )
    decoded = decode_bootstrap_graph_atomic_member_payload_v3(
        kind=member.kind, raw=member.canonical_payload
    )
    typed = BootstrapNativeGroupCommitTerminalConstructionV3.model_validate(
        decoded, strict=False
    )
    assert _source_modalities(typed)
    assert typed.result_digest == decoded["result_digest"]

    envelope = decode_typed_value(member.canonical_payload)
    wrong_codec = {**envelope, "codec_key": "bootstrap_graph_v3/wrong/native"}
    with pytest.raises(SemanticContractCodecError):
        decode_bootstrap_graph_atomic_member_payload_v3(
            kind=member.kind, raw=encode_typed_value(wrong_codec)
        )

    modality_mutation = decode_typed_value(member.canonical_payload)
    assert _replace_first_modality_string(modality_mutation["payload"])
    with pytest.raises(SemanticContractCodecError):
        decode_bootstrap_graph_atomic_member_payload_v3(
            kind=member.kind, raw=encode_typed_value(modality_mutation)
        )

    extra_request = decode_typed_value(member.canonical_payload)
    extra_request["payload"]["group_commit_request"] = {}
    with pytest.raises(SemanticContractCodecError):
        decode_bootstrap_graph_atomic_member_payload_v3(
            kind=member.kind, raw=encode_typed_value(extra_request)
        )

    for key, replacement in (("result_digest", "0" * 64),):
        mutated = decode_typed_value(member.canonical_payload)
        assert _replace_first_key(mutated["payload"], key, replacement)
        with pytest.raises(SemanticContractCodecError):
            decode_bootstrap_graph_atomic_member_payload_v3(
                kind=member.kind, raw=encode_typed_value(mutated)
            )
