"""Prepare and assemble detached signatures for current single-signer release CTV artifacts.

Lifecycle roots and lifecycle records have multi-signer sequencing and are
intentionally owned by a subsequent preparation slice.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueProfileBinding,
    decode_artifact,
    serialize_artifact,
)
from memorii.tools.semantic_ingestion_offline_signing import load_pem_ed25519_public_key_binding
from memorii.tools.semantic_ingestion_signature_verifier import Ed25519SignatureVerifier, Ed25519VerificationKeyBinding
from memorii.tools.semantic_ingestion_traceability_release import (
    load_current_traceability_artifact,
    traceability_artifact_signature_preimage,
)

_KINDS = ("recovery_policy", "release", "release_history", "active_pointer")
_SIGNER_FIELDS = {"recovery_policy": "signer_provenance", "release": "signer_coordinate", "release_history": "signer_coordinate", "active_pointer": "signer_coordinate"}


@dataclass(frozen=True)
class DetachedSigningRequest:
    artifact_kind: str
    profile_id: str
    public_key_digest: str
    purpose: str
    preimage: bytes


@dataclass(frozen=True)
class DetachedSignature:
    artifact_kind: str
    profile_id: str
    public_key_digest: str
    purpose: str
    signature: bytes


@dataclass(frozen=True)
class PreparedReleaseSignatures:
    requests: tuple[DetachedSigningRequest, ...]
    template_bytes: tuple[tuple[str, bytes], ...]


def _prepared_artifact(kind: str, raw: bytes) -> tuple[DetachedSigningRequest, CanonicalTypedValueProfileBinding, dict[str, Any]]:
    if not isinstance(raw, bytes):
        raise ValueError("release_signing_template_invalid")
    artifact = decode_artifact(raw)
    value = load_current_traceability_artifact(raw, kind)
    signer_field = _SIGNER_FIELDS[kind]
    purpose = value.get("issuance_purpose")
    signer = value.get(signer_field)
    if not isinstance(purpose, str) or not isinstance(signer, dict):
        raise ValueError("release_signing_template_invalid")
    digest, preimage = traceability_artifact_signature_preimage(kind, value)
    digest_field = {"recovery_policy": "recovery_policy_digest", "release": "release_digest", "release_history": "release_history_digest", "active_pointer": "active_pointer_digest"}[kind]
    if value.get(digest_field) != digest or not isinstance(value.get("signature"), str):
        raise ValueError("release_signing_template_digest_invalid")
    profile = signer.get("signature_profile_id")
    key = signer.get("key_or_certificate_digest")
    if not isinstance(profile, str) or not isinstance(key, str):
        raise ValueError("release_signing_template_signer_invalid")
    return (
        DetachedSigningRequest(
            kind, profile, key, purpose, preimage,
        ),
        artifact.binding,
        value,
    )


def prepare_release_signatures(templates: Mapping[str, bytes]) -> PreparedReleaseSignatures:
    """Recompute exact detached-signature requests in dependency order."""
    if set(templates) != set(_KINDS):
        raise ValueError("release_signing_template_kinds_invalid")
    prepared = tuple(_prepared_artifact(kind, templates[kind]) for kind in _KINDS)
    return PreparedReleaseSignatures(tuple(item[0] for item in prepared), tuple((kind, templates[kind]) for kind in _KINDS))


def assemble_release_signatures(
    prepared: PreparedReleaseSignatures,
    signatures: tuple[DetachedSignature, ...],
    bindings: tuple[Ed25519VerificationKeyBinding, ...],
) -> dict[str, bytes]:
    """Verify supplied detached signatures and serialize exact current CTV artifacts."""
    if not isinstance(prepared, PreparedReleaseSignatures) or len(signatures) != len(_KINDS):
        raise ValueError("release_signing_signature_count_invalid")
    templates = dict(prepared.template_bytes)
    recomputed = prepare_release_signatures(templates)
    if recomputed.requests != prepared.requests:
        raise ValueError("release_signing_preparation_substituted")
    verifier = Ed25519SignatureVerifier(bindings)
    result: dict[str, bytes] = {}
    for request, supplied, (kind, raw) in zip(recomputed.requests, signatures, recomputed.template_bytes, strict=True):
        artifact = decode_artifact(raw)
        value = load_current_traceability_artifact(raw, kind)
        if kind != request.artifact_kind or (
            supplied.artifact_kind, supplied.profile_id, supplied.public_key_digest, supplied.purpose
        ) != (request.artifact_kind, request.profile_id, request.public_key_digest, request.purpose):
            raise ValueError("release_signing_signature_coordinate_invalid")
        if not verifier.verify(request.profile_id, request.public_key_digest, request.preimage, supplied.signature):
            raise ValueError("release_signing_signature_invalid")
        result[kind] = serialize_artifact({**value, "signature": supplied.signature.hex()}, artifact.binding)
    return result


def _write_new(path: str, value: bytes) -> None:
    with open(path, "xb") as output:
        output.write(value)


def load_release_signing_bindings(path: str) -> tuple[Ed25519VerificationKeyBinding, ...]:
    value = json.loads(Path(path).read_text(), object_pairs_hook=_unique_fields)
    if not isinstance(value, dict) or set(value) != {"bindings"} or not isinstance(value["bindings"], list):
        raise ValueError("release_signing_bindings_invalid")
    output = []
    for item in value["bindings"]:
        if not isinstance(item, dict) or set(item) != {"profile_id", "expected_digest", "digest_domain_file", "public_key_file"}:
            raise ValueError("release_signing_bindings_invalid")
        if not all(isinstance(item[key], str) for key in item):
            raise ValueError("release_signing_bindings_invalid")
        output.append(load_pem_ed25519_public_key_binding(
            Path(item["public_key_file"]).read_bytes(), profile_id=item["profile_id"],
            digest_domain=Path(item["digest_domain_file"]).read_bytes(), public_key_digest=item["expected_digest"],
        ))
    return tuple(output)


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("release_signing_duplicate_field")
        result[key] = value
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--assemble", action="store_true")
    for kind in _KINDS:
        parser.add_argument("--" + kind.replace("_", "-"), required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--bindings")
    for kind in _KINDS:
        parser.add_argument("--" + kind.replace("_", "-") + "-signature")
    args = parser.parse_args(argv)
    if args.prepare == args.assemble:
        parser.error("select exactly one of --prepare or --assemble")
    templates: dict[str, bytes] = {}
    for kind in _KINDS:
        with open(getattr(args, kind), "rb") as template:
            templates[kind] = template.read()
    prepared = prepare_release_signatures(templates)
    if args.prepare:
        value = {"requests": [{"artifact_kind": r.artifact_kind, "profile_id": r.profile_id, "public_key_digest": r.public_key_digest, "purpose": r.purpose, "preimage_hex": r.preimage.hex()} for r in prepared.requests]}
        _write_new(args.output, json.dumps(value, sort_keys=True, separators=(",", ":")).encode())
        return 0
    if args.bindings is None or any(getattr(args, kind + "_signature") is None for kind in _KINDS):
        parser.error("--assemble requires --bindings and every fixed detached signature path")
    signatures = tuple(
        DetachedSignature(request.artifact_kind, request.profile_id, request.public_key_digest, request.purpose,
                          Path(getattr(args, kind + "_signature")).read_bytes())
        for kind, request in zip(_KINDS, prepared.requests, strict=True)
    )
    assembled = assemble_release_signatures(prepared, signatures, load_release_signing_bindings(args.bindings))
    output = Path(args.output)
    output.mkdir()
    for kind, raw in assembled.items():
        _write_new(str(output / (kind + ".ctv")), raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
