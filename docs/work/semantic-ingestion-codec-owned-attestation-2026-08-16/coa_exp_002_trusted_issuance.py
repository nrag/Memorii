from __future__ import annotations

import copy
import json
import pickle
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel

from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.semantic_ingestion import contracts


_PROFILE_REVISION = "semantic-ingestion-canonical-profile-v1"
_CODEC_REVISION = "canonical-typed-value-v1"
_PURPOSE = "content-addressed-contract-digest-validation"


@dataclass(frozen=True)
class _OpaqueAttestation:
    issuer_capability: object
    nonce: str
    concrete_type: type[BaseModel]
    profile_revision: str
    codec_revision: str
    domain: bytes
    purpose: str
    canonical_preimage_bytes: bytes
    digest: str


@dataclass(frozen=True)
class _ConsumedPreimage:
    concrete_type: type[BaseModel]
    canonical_preimage_bytes: bytes
    digest: str


class _TrustedSemanticAttestationIssuer:
    def __init__(self, *, nonce: str) -> None:
        self._nonce = nonce
        self._capability = object()
        self._registered: dict[int, _OpaqueAttestation] = {}
        self._closed = False

    def issue(self, value: BaseModel) -> _OpaqueAttestation:
        if self._closed or not isinstance(value, contracts._ContentAddressedContract):
            raise ValueError("trusted semantic contract required")
        contract_type = type(value)
        # This is the complete legacy validation. No attestation exists yet.
        validated = contract_type.model_validate(
            contracts._restore_closed_wire_enums(contracts.canonical_contract_value(value))
        )
        body = {
            name: getattr(validated, name)
            for name in contract_type.model_fields
            if name != contract_type._digest_field
            and name not in contract_type._digest_excluded_fields
        }
        canonical_preimage_bytes = encode_typed_value(contracts.canonical_contract_value(body))
        digest = sha256(contract_type._digest_domain + b"\0" + canonical_preimage_bytes).hexdigest()
        if getattr(validated, contract_type._digest_field) != digest:
            raise ValueError("complete legacy digest validation did not close")
        attestation = _OpaqueAttestation(
            issuer_capability=self._capability,
            nonce=self._nonce,
            concrete_type=contract_type,
            profile_revision=_PROFILE_REVISION,
            codec_revision=_CODEC_REVISION,
            domain=contract_type._digest_domain,
            purpose=_PURPOSE,
            canonical_preimage_bytes=bytes(canonical_preimage_bytes),
            digest=digest,
        )
        self._registered[id(attestation)] = attestation
        return attestation

    def consume(
        self,
        attestation: object,
        *,
        nonce: str,
        concrete_type: type[BaseModel],
        profile_revision: str,
        codec_revision: str,
        domain: bytes,
        purpose: str,
    ) -> _ConsumedPreimage:
        if self._closed or not isinstance(attestation, _OpaqueAttestation):
            raise ValueError("registered runtime attestation required")
        if self._registered.get(id(attestation)) is not attestation:
            raise ValueError("copied or unregistered attestation")
        if (
            attestation.issuer_capability is not self._capability
            or attestation.nonce != self._nonce
            or nonce != self._nonce
            or attestation.concrete_type is not concrete_type
            or attestation.profile_revision != profile_revision
            or attestation.codec_revision != codec_revision
            or attestation.domain != domain
            or attestation.purpose != purpose
        ):
            raise ValueError("attestation context mismatch")
        return _ConsumedPreimage(
            concrete_type=attestation.concrete_type,
            canonical_preimage_bytes=attestation.canonical_preimage_bytes,
            digest=attestation.digest,
        )

    def close(self) -> None:
        self._registered.clear()
        self._closed = True


def _artifact() -> contracts.RetainedSourceTextArtifact:
    return contracts.RetainedSourceTextArtifact.create(
        artifact_id="trusted-artifact",
        content_digest="0" * 64,
        unicode_scalar_length=0,
    )


def _consume(issuer: _TrustedSemanticAttestationIssuer, handle: object, *, nonce: str = "operation-a", **changes: object) -> _ConsumedPreimage:
    values = {
        "nonce": nonce,
        "concrete_type": contracts.RetainedSourceTextArtifact,
        "profile_revision": _PROFILE_REVISION,
        "codec_revision": _CODEC_REVISION,
        "domain": contracts.RetainedSourceTextArtifact._digest_domain,
        "purpose": _PURPOSE,
    }
    values.update(changes)
    return issuer.consume(handle, **values)  # type: ignore[arg-type]


def _must_reject(name: str, action: object, rejected: list[str]) -> None:
    try:
        action()  # type: ignore[operator]
    except (TypeError, ValueError):
        rejected.append(name)
        return
    raise RuntimeError(f"COA-EXP-002 accepted attack: {name}")


def main() -> None:
    issuer = _TrustedSemanticAttestationIssuer(nonce="operation-a")
    value = _artifact()
    handle = issuer.issue(value)
    consumed = _consume(issuer, handle)
    rejected: list[str] = []

    forged = value.model_copy(update={"artifact_digest": "f" * 64})
    constructed = contracts.RetainedSourceTextArtifact.model_construct(
        artifact_kind="retained_source_text",
        artifact_id="trusted-artifact",
        content_digest="0" * 64,
        unicode_scalar_length=0,
        offset_unit="unicode_scalar",
        artifact_digest="f" * 64,
    )
    _must_reject("caller_claimed_digest", lambda: issuer.issue(forged), rejected)
    _must_reject("model_construct", lambda: issuer.issue(constructed), rejected)
    _must_reject("caller_bytes", lambda: issuer.issue(consumed.canonical_preimage_bytes), rejected)
    _must_reject("copied_handle", lambda: _consume(issuer, copy.copy(handle)), rejected)
    _must_reject("serialized_handle", lambda: _consume(issuer, pickle.loads(pickle.dumps(handle))), rejected)
    _must_reject("arbitrary_object", lambda: _consume(issuer, object()), rejected)
    _must_reject("wrong_nonce", lambda: _consume(issuer, handle, nonce="operation-b"), rejected)
    _must_reject("wrong_type", lambda: _consume(issuer, handle, concrete_type=contracts.SegmentLocalTextArtifact), rejected)
    _must_reject("wrong_profile", lambda: _consume(issuer, handle, profile_revision="profile-v2"), rejected)
    _must_reject("wrong_codec", lambda: _consume(issuer, handle, codec_revision="codec-v2"), rejected)
    _must_reject("wrong_domain", lambda: _consume(issuer, handle, domain=b"wrong-domain"), rejected)
    _must_reject("wrong_purpose", lambda: _consume(issuer, handle, purpose="persistence-admission"), rejected)

    other_issuer = _TrustedSemanticAttestationIssuer(nonce="operation-a")
    _must_reject("cross_issuer", lambda: _consume(other_issuer, handle), rejected)
    other_issuer.close()

    object.__setattr__(value, "artifact_id", "mutated-after-issuance")
    _must_reject("mutated_value_reissue", lambda: issuer.issue(value), rejected)
    if _consume(issuer, handle).canonical_preimage_bytes != consumed.canonical_preimage_bytes:
        raise RuntimeError("issued snapshot changed after source mutation")

    iterations = 100_000
    started = time.perf_counter()
    for _ in range(iterations):
        _consume(issuer, handle)
    consume_elapsed = time.perf_counter() - started

    issuer.close()
    _must_reject("closed_issuer_replay", lambda: _consume(issuer, handle), rejected)
    if len(rejected) != 15:
        raise RuntimeError(f"attack family cardinality mismatch: {rejected}")

    result = {
        "schema": "memorii.semantic-ingestion.codec-attestation.trusted-issuance-prototype.v1",
        "experiment": "COA-EXP-002",
        "evidence_stage": "reference_only_feasibility",
        "certifies_m3_1": False,
        "decision": "SECURITY_PROTOTYPE_PASS_INTEGRATION_UNPROVEN",
        "rejected_attacks": rejected,
        "rejected_attack_count": len(rejected),
        "canonical_preimage_sha256": sha256(consumed.canonical_preimage_bytes).hexdigest(),
        "canonical_preimage_length": len(consumed.canonical_preimage_bytes),
        "digest": consumed.digest,
        "consume_iterations": iterations,
        "consume_elapsed_seconds": consume_elapsed,
        "production_integration_measured": False,
        "integration_blocker": "Pydantic nested validators receive raw reconstructed models, not the private attestation handle; automatic lookup would require a caller digest, object identity, equality, or canonical-byte reconstruction.",
    }
    output = Path(__file__).with_name("evidence") / "coa-exp-002-trusted-issuance-v1.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
