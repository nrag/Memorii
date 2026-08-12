"""Publication/reload invariants for graph-free source normalization."""

from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace

import pytest
from memorii.core.memory_evolution.atomic_store import AtomicGenerationMember
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.semantic_ingestion.contracts import (
    BootstrapRecoveryKeyV3,
    BootstrapRecoveryProbeV3,
    SourceNormalizationRecoveryAuthorityBinding,
    SourceNormalizationRecoveryHandoffBinding,
    SourceNormalizationRecoveryInvocationBinding,
    SourceNormalizationRecoveryRequest,
    SourceNormalizationRecoveryValidationContext,
    contract_digest,
)
from memorii.core.semantic_ingestion.source_normalization_repository import (
    AtomicStoreSourceNormalizationRepository,
)


class _Request:
    def __init__(self, *, members: tuple[AtomicGenerationMember, ...], result: object) -> None:
        self.members = members
        self.source_normalization_result = result
        self.source_normalization_result_digest = result.result_digest
        self.operation_fence_binding = object()

    def model_dump(self, *, mode: str) -> dict[str, object]:
        assert mode == "python"
        return {}


class _Store:
    def __init__(self, members: tuple[AtomicGenerationMember, ...]) -> None:
        self._members = members
        self.request = None

    def checkpoint_source_progress(self, request):
        self.request = request
        return self._members

    def get_operation(self, operation_fence):
        return SimpleNamespace(generation=2)

    def generation_members(self, operation_fence, generation: int):
        assert generation == 2
        return self._members


def _member(kind: str, payload: bytes) -> AtomicGenerationMember:
    return AtomicGenerationMember(
        member_id=f"00-{kind}", kind=kind, canonical_payload=payload,
        payload_digest=sha256(payload).hexdigest(),
    )


def _wire_repository(monkeypatch, request: _Request, decoded: object) -> None:
    import memorii.core.semantic_ingestion.source_normalization_repository as module

    monkeypatch.setattr(
        module.SourceNormalizationAtomicWriteRequest,
        "model_validate",
        classmethod(lambda cls, value: request),
    )
    monkeypatch.setattr(module, "decode_semantic_contract", lambda payload, cls: decoded)
    monkeypatch.setattr(module, "encode_semantic_contract", lambda value: b"result")
    monkeypatch.setattr(
        module.SourceNormalizationResult,
        "model_validate",
        classmethod(lambda cls, value: decoded),
    )


def test_publish_returns_only_the_same_generation_reloaded_result(monkeypatch) -> None:
    result = SimpleNamespace(result_digest="a" * 64, model_dump=lambda *, mode: {})
    members = (_member("source_normalization_result", b"result"),)
    request = _Request(members=members, result=result)
    _wire_repository(monkeypatch, request, result)
    store = _Store(members)

    returned = AtomicStoreSourceNormalizationRepository(atomic_store=store).publish_and_reload(request)

    assert returned is result
    assert store.request is request


@pytest.mark.parametrize("mutation", ("missing", "foreign", "substituted"))
def test_publish_rejects_any_nonexact_generation_reload(monkeypatch, mutation: str) -> None:
    result = SimpleNamespace(result_digest="a" * 64, model_dump=lambda *, mode: {})
    expected = (_member("source_normalization_result", b"result"),)
    request = _Request(members=expected, result=result)
    _wire_repository(monkeypatch, request, result)
    if mutation == "missing":
        actual = ()
    elif mutation == "foreign":
        actual = (*expected, _member("progress", b"progress"))
    else:
        actual = (_member("source_normalization_result", b"other"),)

    with pytest.raises(ValueError, match="partial or substituted"):
        AtomicStoreSourceNormalizationRepository(atomic_store=_Store(actual)).publish_and_reload(request)


def test_recovery_rejects_context_substitution_before_store_read() -> None:
    digest = "a" * 64
    invocation_body = {
        "source_id": "source", "source_digest": digest, "preparation_fingerprint": digest,
        "operation_id": "operation", "operation_fence_digest": digest,
    }
    invocation = SourceNormalizationRecoveryInvocationBinding(
        **invocation_body,
        binding_digest=contract_digest(
            b"memorii.semantic-ingestion.source-normalization-recovery-invocation-binding.v1", invocation_body
        ),
    )
    handoff_body = {
        "kind": "started", "source_id": "source", "source_digest": digest,
        "handoff_request_digest": digest, "prepared_generation": 1,
        "prepared_source_digest": digest, "authority_pin_digest": digest,
        "release_evidence_digest": digest, "bootstrap_language_evidence_digest": digest,
        "delivery_identity_digest": digest, "operation_fence_digest": digest,
        "writer_commit_binding_digest": digest, "pending_operation_id": "operation",
        "pending_operation_digest": digest, "marker_digest": digest, "handoff_result_digest": digest,
    }
    authority_body = {
        "derivation_authority_digest": digest, "publication_authority_digest": digest,
        "publication_coordinate_digest": digest, "authority_bundle_digest": digest,
        "expected_operation_generation": 1, "expected_artifact_generation": 1,
    }
    authority = SourceNormalizationRecoveryAuthorityBinding(
        **authority_body,
        binding_digest=contract_digest(
            b"memorii.semantic-ingestion.source-normalization-recovery-authority-binding.v1", authority_body
        ),
    )
    request_body = {
        **invocation_body, "expected_operation_generation": 1,
        "expected_artifact_generation": 1, "derivation_authority_digest": digest,
        "publication_coordinate_digest": digest,
    }
    identity = contract_digest(
        b"memorii.semantic-ingestion.source-normalization-recovery-identity.v1", request_body
    )
    request = SourceNormalizationRecoveryRequest(
        **request_body, request_identity=identity,
        request_digest=contract_digest(
            b"memorii.semantic-ingestion.source-normalization-recovery-request.v1",
            {**request_body, "request_identity": identity},
        ),
    )

    class _NeverRead:
        def recover_source_normalization(self, **kwargs):
            raise AssertionError("invalid context must not read persistence")

    foreign_handoff_body = {**handoff_body, "source_id": "foreign"}
    foreign_handoff = SourceNormalizationRecoveryHandoffBinding(
        **foreign_handoff_body,
        binding_digest=contract_digest(
            b"memorii.semantic-ingestion.source-normalization-recovery-handoff-binding.v1", foreign_handoff_body
        ),
    )
    substituted_body = {"invocation": invocation, "handoff": foreign_handoff, "authority": authority}
    substituted = SourceNormalizationRecoveryValidationContext(
        **substituted_body,
        context_digest=contract_digest(
            b"memorii.semantic-ingestion.source-normalization-recovery-context.v1", substituted_body
        ),
    )
    result = AtomicStoreSourceNormalizationRepository(atomic_store=_NeverRead()).recover(
        request=request, context=substituted
    )
    assert result.kind == "publication_unavailable"
    assert result.reason == "context_mismatch"


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
