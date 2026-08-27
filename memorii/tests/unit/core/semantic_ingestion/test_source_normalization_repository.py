"""Publication/reload invariants for graph-free source normalization."""

from __future__ import annotations

from hashlib import sha256

import pytest
from memorii.core.memory_evolution.atomic_store import AtomicGenerationMember
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.semantic_ingestion.contracts import (
    BootstrapRecoveryKeyV3,
    BootstrapRecoveryProbeV3,
    contract_digest,
)
from memorii.core.semantic_ingestion.source_normalization_repository import (
    AtomicStoreSourceNormalizationRepository,
)


def _member(kind: str, payload: bytes) -> AtomicGenerationMember:
    return AtomicGenerationMember(
        member_id=f"00-{kind}", kind=kind, canonical_payload=payload,
        payload_digest=sha256(payload).hexdigest(),
    )


def test_v3_probe_rejects_retired_generation_only_shape() -> None:
    digest = "a" * 64
    key_body = {
        "source_id": "source", "source_digest": digest,
        "preparation_fingerprint": digest, "operation_id": "operation",
        "operation_fence_digest": digest, "bootstrap_profile_manifest_digest": digest,
        "handoff_request_digest": digest,
    }
    key = BootstrapRecoveryKeyV3(
        **key_body,
        recovery_key_digest=contract_digest(
            b"memorii.semantic-ingestion.bootstrap-recovery-key.v3", key_body
        ),
    )
    legacy_probe = {
        "recovery_key": key, "expected_operation_generation": 1,
        "expected_artifact_generation": 1, "probe_digest": "b" * 64,
    }
    with pytest.raises(ValueError):
        BootstrapRecoveryProbeV3.model_validate(legacy_probe)


@pytest.mark.parametrize(
    ("members", "message"),
    (
            (
                (_member("bootstrap_analysis_provenance", encode_typed_value(())),),
                "retained member bytes are invalid",
        ),
        (
            (
                AtomicGenerationMember(
                    member_id="01-provenance",
                    kind="bootstrap_analysis_provenance",
                    canonical_payload=encode_typed_value(()),
                    payload_digest=sha256(encode_typed_value(())).hexdigest(),
                ),
                AtomicGenerationMember(
                    member_id="00-authority",
                    kind="bootstrap_v3_payload_limit_authority",
                    canonical_payload=b"wrong-type",
                    payload_digest=sha256(b"wrong-type").hexdigest(),
                ),
            ),
            "identity order",
        ),
        (
            (
                _member("bootstrap_analysis_provenance", encode_typed_value(())),
                _member("bootstrap_v3_payload_limit_authority", b"wrong-type"),
            ),
            "retained member bytes are invalid",
        ),
    ),
)
def test_v3_reopen_decoder_rejects_missing_reordered_and_type_swapped_members(
    members: tuple[AtomicGenerationMember, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        AtomicStoreSourceNormalizationRepository.validate_bootstrap_v3_reloaded_members(members)
