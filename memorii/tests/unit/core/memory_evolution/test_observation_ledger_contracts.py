from datetime import UTC, datetime
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.graph_effect_contracts import (
    IngestionObservationDelta,
    SourceFinalizationObservationDelta,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    SemanticWriterAdmission,
    SemanticWriterCommitBinding,
    encode_typed_value,
)
from memorii.core.memory_evolution.observation_ledger_contracts import (
    ObservationGroupResultLocator,
    ObservationGroupSemanticPayload,
    ObservationLedgerActivation,
    ObservationLedgerHead,
    ObservationLedgerSemanticPayload,
    ObservationSourceSemanticPayload,
)
from memorii.core.semantic_ingestion.contracts import canonical_contract_value
from pydantic import TypeAdapter, ValidationError
from tests.unit.core.memory_evolution.test_observation_record_contracts import (
    _source_material,
    _source_terminal,
    _terminal_group_delta,
)


def _digest(label: str) -> str:
    return sha256(label.encode("ascii")).hexdigest()


def _group_locator(**overrides: object) -> ObservationGroupResultLocator:
    body = {
        "schema_version": 1,
        "kind": "group_primary",
        "immutable_record_id": "record:group",
        "source_id": "source:ledger",
        "source_digest": _digest("source"),
        "source_operation_id": "operation:source",
        "operation_fence_id": "fence:ledger",
        "transaction_group_id": "group:ledger",
        "operation_ids": ("operation:one", "operation:two"),
        "request_ctv_digest": _digest("request"),
    }
    return ObservationGroupResultLocator(**{**body, **overrides})


def _writer_admission(*, activation_digest: str | None) -> SemanticWriterAdmission:
    return SemanticWriterAdmission(
        admission_id="admission:ledger",
        writer_namespace="semantic_ingestion",
        active_runtime_mode="verified_semantic",
        active_writer_implementation_fingerprint="writer:fingerprint",
        accepted_graph_schema_fingerprint="graph:fingerprint",
        writer_epoch=2,
        activated_at=datetime(2026, 9, 7, tzinfo=UTC),
        previous_admission_digest=_digest("previous-admission"),
        activation_digest=activation_digest,
        admission_digest=_digest("admission"),
    )


def _writer_binding(*, activation_digest: str | None) -> SemanticWriterCommitBinding:
    return SemanticWriterCommitBinding(
        admission_id="admission:ledger",
        admission_digest=_digest("admission"),
        writer_namespace="semantic_ingestion",
        expected_writer_epoch=2,
        runtime_mode="verified_semantic",
        writer_implementation_fingerprint="writer:fingerprint",
        graph_schema_fingerprint="graph:fingerprint",
        activation_digest=activation_digest,
    )


@pytest.mark.parametrize(
    ("value", "serialized"),
    (
        pytest.param(
            _writer_admission(activation_digest=None),
            _writer_admission(activation_digest=None).model_dump(mode="python"),
            id="legacy-admission",
        ),
        pytest.param(
            _writer_binding(activation_digest=None),
            _writer_binding(activation_digest=None).model_dump(mode="python"),
            id="legacy-binding",
        ),
        pytest.param(
            _writer_admission(activation_digest=_digest("activation")),
            _writer_admission(activation_digest=_digest("activation")).model_dump(mode="python"),
            id="activated-admission",
        ),
        pytest.param(
            _writer_binding(activation_digest=_digest("activation")),
            _writer_binding(activation_digest=_digest("activation")).model_dump(mode="python"),
            id="activated-binding",
        ),
    ),
)
def test_writer_models_canonicalize_exactly_as_serialized_maps(
    value: SemanticWriterAdmission | SemanticWriterCommitBinding, serialized: dict[str, object]
) -> None:
    direct = encode_typed_value(canonical_contract_value(value))
    serialized_bytes = encode_typed_value(canonical_contract_value(serialized))
    nested = encode_typed_value(canonical_contract_value({"writer": value}))
    nested_serialized = encode_typed_value(canonical_contract_value({"writer": serialized}))

    assert direct == serialized_bytes
    assert nested == nested_serialized


def test_writer_activation_digest_preserves_legacy_omission_and_changes_binding() -> None:
    legacy = _writer_binding(activation_digest=None)
    activated = _writer_binding(activation_digest=_digest("activation"))

    assert "activation_digest" not in legacy.model_dump(mode="python")
    assert "activation_digest" not in canonical_contract_value(legacy)
    assert tuple(canonical_contract_value(legacy)) == tuple(
        name for name in SemanticWriterCommitBinding.model_fields if name != "activation_digest"
    )
    assert "activation_digest" in activated.model_dump(mode="python")
    assert "activation_digest" in canonical_contract_value(activated)
    assert legacy.binding_digest != activated.binding_digest


def test_ledger_head_requires_exact_genesis_predecessor_shape() -> None:
    base = {
        "schema_version": 1,
        "repository_id": "repository:ledger",
        "activation_digest": _digest("activation"),
        "observation_revision": "genesis",
        "last_delta_id": None,
        "last_delta_digest": None,
        "last_entry_digest": None,
        "head_digest": _digest("head"),
    }

    assert ObservationLedgerHead(sequence=0, **base).last_entry_digest is None
    assert ObservationLedgerHead(
        sequence=1,
        **{
            **base,
            "observation_revision": "revision:one",
            "last_delta_id": "delta:one",
            "last_delta_digest": _digest("delta"),
            "last_entry_digest": _digest("entry"),
        },
    ).sequence == 1
    with pytest.raises(ValidationError, match="predecessor shape"):
        ObservationLedgerHead(sequence=0, **{**base, "last_delta_id": "delta:one"})
    with pytest.raises(ValidationError, match="predecessor shape"):
        ObservationLedgerHead(sequence=1, **base)
    with pytest.raises(ValidationError, match="genesis revision"):
        ObservationLedgerHead(sequence=0, **{**base, "observation_revision": "revision:genesis"})
    with pytest.raises(ValidationError, match="genesis revision"):
        ObservationLedgerHead(sequence=1, **{**base, "last_delta_id": "delta:one", "last_delta_digest": _digest("delta"), "last_entry_digest": _digest("entry")})
    with pytest.raises(ValidationError, match="schema version"):
        ObservationLedgerHead(sequence=0, **{**base, "schema_version": True})


def test_group_locator_rejects_unsorted_or_empty_operation_coordinates() -> None:
    assert _group_locator().operation_ids == ("operation:one", "operation:two")
    with pytest.raises(ValidationError, match="sorted, unique, and nonempty"):
        _group_locator(operation_ids=("operation:two", "operation:one"))
    with pytest.raises(ValidationError, match="sorted, unique, and nonempty"):
        _group_locator(operation_ids=())
    with pytest.raises(ValidationError):
        _group_locator(operation_ids=("",))


def test_semantic_payload_fields_are_exact_native_delta_subsets() -> None:
    removed = {"observation_revision_before", "observation_revision_after", "delta_digest"}
    assert set(ObservationGroupSemanticPayload.model_fields) == set(IngestionObservationDelta.model_fields) - removed
    assert set(ObservationSourceSemanticPayload.model_fields) == set(SourceFinalizationObservationDelta.model_fields) - removed


def test_semantic_payload_conversion_preserves_every_native_field() -> None:
    group_delta = _terminal_group_delta(_source_material())
    group_payload = ObservationGroupSemanticPayload.from_delta(group_delta)
    assert group_payload.model_dump(mode="python") == group_delta.model_dump(
        mode="python",
        exclude={"observation_revision_before", "observation_revision_after", "delta_digest"},
    )

    outcome = _source_terminal(_source_material())
    source_delta = SourceFinalizationObservationDelta.create(
        kind="source_finalization",
        observation_delta_id="observation:source-finalization",
        observation_revision_before="observation:0",
        observation_revision_after="observation:1",
        source_id=outcome.source_id,
        source_digest=outcome.source_digest,
        delivery_principal_binding_digest=outcome.delivery_principal_binding_digest,
        delivery_key_digest=outcome.delivery_key_digest,
        segment_governance_carriers=outcome.segment_governance_carriers,
        message_admission_carriers=outcome.message_admission_carriers,
        governance_carrier_artifact=outcome.governance_carrier_artifact,
        required_outcome_scopes=outcome.required_outcome_scopes,
        operation_fence_id=outcome.operation_fence_id,
        operation_ids=outcome.operation_ids,
        source_outcome=outcome,
        observation_schema_fingerprint=_digest("observation-schema"),
    )
    source_payload = ObservationSourceSemanticPayload.from_delta(source_delta)
    assert source_payload.model_dump(mode="python") == source_delta.model_dump(
        mode="python",
        exclude={"observation_revision_before", "observation_revision_after", "delta_digest"},
    )


def test_semantic_payload_alias_is_closed_and_kind_discriminated() -> None:
    adapter = TypeAdapter(ObservationLedgerSemanticPayload)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "unknown"})
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "terminal_group", "extra": "forbidden"})


def test_activation_is_strict_and_requires_profile_three_fields() -> None:
    body = {
        "schema_version": 1,
        "repository_id": "repository:ledger",
        "previous_writer_admission_digest": _digest("admission"),
        "target_writer_epoch": 1,
        "writer_implementation_fingerprint": _digest("writer"),
        "observation_schema_fingerprint": _digest("schema"),
        "ledger_codec_fingerprint": _digest("codec"),
        "legacy_terminal_inventory_digest": _digest("inventory"),
        "activation_digest": _digest("activation"),
    }
    assert ObservationLedgerActivation(**body).target_writer_epoch == 1
    with pytest.raises(ValidationError):
        ObservationLedgerActivation(**{**body, "target_writer_epoch": True})
    with pytest.raises(ValidationError):
        ObservationLedgerActivation(**{**body, "unknown": "forbidden"})


@pytest.mark.parametrize("activation_digest", [None, _digest("activation")])
def test_writer_admission_preserves_unset_predecessor_in_canonical_values(activation_digest: str | None) -> None:
    admission = _writer_admission(activation_digest=activation_digest).model_copy(
        update={"previous_admission_digest": None}
    )
    serialized = admission.model_dump(mode="python")
    canonical = canonical_contract_value(admission)
    assert canonical["previous_admission_digest"] is None
    assert ("activation_digest" in canonical) is (activation_digest is not None)
    assert encode_typed_value(canonical) == encode_typed_value(canonical_contract_value(serialized))
    assert encode_typed_value(canonical_contract_value({"writer": admission})) == encode_typed_value(
        canonical_contract_value({"writer": serialized})
    )
