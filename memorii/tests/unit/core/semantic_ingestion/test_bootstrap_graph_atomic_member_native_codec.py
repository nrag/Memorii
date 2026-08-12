from hashlib import sha256

import pytest
from memorii.core.semantic_ingestion.contracts import (
    BOOTSTRAP_GRAPH_V3_ATOMIC_MEMBER_CODECS,
    BootstrapGraphOperationReductionV3,
    BootstrapGraphPlanAtomicMemberV3,
    SemanticContractCodecError,
    decode_bootstrap_graph_atomic_member_payload_v3,
    encode_bootstrap_graph_atomic_member_payload_v3,
    rebuild_bootstrap_graph_effect_contracts,
    validate_bootstrap_graph_plan_atomic_members_v3,
)
from pydantic import BaseModel, ConfigDict


class _NativeProjection(BaseModel):
    projection: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class _RetiredGenericProjection(BaseModel):
    semantic_compilation: str

    model_config = ConfigDict(extra="forbid", frozen=True)


def test_each_v3_atomic_member_kind_has_one_qualified_native_codec() -> None:
    assert len(BOOTSTRAP_GRAPH_V3_ATOMIC_MEMBER_CODECS) == 21
    assert len(set(BOOTSTRAP_GRAPH_V3_ATOMIC_MEMBER_CODECS.values())) == 21

    for kind, codec_key in BOOTSTRAP_GRAPH_V3_ATOMIC_MEMBER_CODECS.items():
        assert codec_key == f"bootstrap_graph_v3/{kind}/native"
        # The result member is deliberately construction-typed; its positive
        # proof belongs to the native group-commit closure fixture below.
        if kind == "transaction_group_result":
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
