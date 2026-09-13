"""Protected cursor emission interoperates with the independent artifact verifier."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from memorii.core.memory_evolution.graph_observation_snapshot_contracts import GraphObservationCursorPayload
from memorii.core.memory_evolution.observation_activation_runtime import (
    ObservationActivationRuntimeError,
    decode_registered_observation_cursor,
    issue_registered_observation_cursor,
)
from memorii.core.memory_evolution.typed_value_artifact_integrity import (
    TrustedTypedValueArtifactVerificationKey,
    TypedValueArtifactIntegrityError,
    verify_protected_typed_value_artifact_integrity,
)
from memorii.core.memory_evolution.typed_value_registry_history import TypedValueRegistryReadRoute
from tests.unit.core.memory_evolution.test_typed_value_artifact_integrity import _LIMITS, _publication


def test_cursor_signed_registered_envelope_rejects_wrong_key_and_wire_substitution(tmp_path):
    history = _publication(tmp_path, schemas=("GraphObservationCursorPayload",))
    private_key = Ed25519PrivateKey.generate()
    public_key = TrustedTypedValueArtifactVerificationKey(private_key.public_key().public_bytes_raw())
    options = dict(history=history, publication=history.publications[0], verification_key=public_key, limits=_LIMITS)
    payload = GraphObservationCursorPayload(
        schema_version=1, stream_position=0, preceding_record_kind=None,
        preceding_primary_key=None, preceding_record_digest=None, requested_total_page_size=1,
        page_policy_revision="policy", page_policy_digest="a" * 64,
        caller_context_digest="b" * 64, authorization_decision_digest="c" * 64,
        authorization_expires_at=datetime(2026, 9, 9, tzinfo=UTC), cohort_digest="d" * 64,
        snapshot_token="snapshot", snapshot_write_revision=42, graph_revision="graph",
        observation_revision="observation", view="current", valid_at=None,
        system_as_of=datetime(2026, 9, 8, tzinfo=UTC), signature="0" * 128,
    )
    cursor = issue_registered_observation_cursor(payload, signing_key=private_key, **options)
    decoded = decode_registered_observation_cursor(cursor, **options)
    assert decoded.model_dump(exclude={"signature"}) == payload.model_dump(exclude={"signature"})
    assert decoded.signature != payload.signature
    independent = verify_protected_typed_value_artifact_integrity(
        cursor.encode("utf-8"), history=history, route=TypedValueRegistryReadRoute.PUBLIC,
        limits=_LIMITS, verification_key=public_key,
    )
    assert independent.cryptographic_signature_checked
    assert independent.materialization.materialized.value == decoded
    wrong_key = TrustedTypedValueArtifactVerificationKey(Ed25519PrivateKey.generate().public_key().public_bytes_raw())
    with pytest.raises(TypedValueArtifactIntegrityError, match="signature_mismatch"):
        decode_registered_observation_cursor(cursor, **{**options, "verification_key": wrong_key})
    with pytest.raises(TypedValueArtifactIntegrityError, match="signature_mismatch"):
        issue_registered_observation_cursor(payload, signing_key=private_key, **{**options, "verification_key": wrong_key})
    with pytest.raises(ObservationActivationRuntimeError, match="wire limit"):
        decode_registered_observation_cursor(cursor, **{**options, "limits": replace(_LIMITS, maximum_envelope_bytes=len(cursor) - 1)})
    with pytest.raises(ObservationActivationRuntimeError, match="Unicode scalar"):
        decode_registered_observation_cursor("\ud800", **options)
    for invalid in ("v1." + cursor, cursor + "\n", cursor[:-1]):
        with pytest.raises(TypedValueArtifactIntegrityError):
            decode_registered_observation_cursor(invalid, **options)
