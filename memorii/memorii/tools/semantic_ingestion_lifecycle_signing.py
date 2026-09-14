"""Prepare and assemble detached signatures for one current lifecycle CTV."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from memorii.tools.semantic_ingestion_release_signing import load_release_signing_bindings
from memorii.tools.semantic_ingestion_signature_verifier import (
    Ed25519SignatureVerifier,
    Ed25519VerificationKeyBinding,
)
from memorii.tools.semantic_ingestion_traceability_release import (
    LifecycleDetachedSignatureRequest,
    assemble_current_lifecycle_detached_signatures,
    prepare_current_lifecycle_detached_signatures,
)

LifecycleSigningKind = Literal["lifecycle_record", "lifecycle_root"]
_KINDS: tuple[LifecycleSigningKind, LifecycleSigningKind] = ("lifecycle_record", "lifecycle_root")


@dataclass(frozen=True)
class DetachedLifecycleSignature:
    """One raw signature returned for an explicit lifecycle signer slot."""

    lifecycle_kind: LifecycleSigningKind
    record_index: int | None
    signature_index: int
    profile_id: str
    public_key_digest: str
    purpose: str
    signature: bytes


@dataclass(frozen=True)
class PreparedLifecycleSignatures:
    """Immutable raw template and its independently reproducible requests."""

    lifecycle_kind: LifecycleSigningKind
    requests: tuple[LifecycleDetachedSignatureRequest, ...]
    template_bytes: bytes


def prepare_lifecycle_signatures(
    lifecycle_kind: LifecycleSigningKind, template: bytes,
) -> PreparedLifecycleSignatures:
    """Prepare exact signer-order requests from one canonical lifecycle CTV."""
    if lifecycle_kind not in _KINDS or not isinstance(template, bytes):
        raise ValueError("lifecycle_signing_template_invalid")
    _, requests, _ = prepare_current_lifecycle_detached_signatures(template, lifecycle_kind)
    return PreparedLifecycleSignatures(lifecycle_kind, requests, template)


def assemble_lifecycle_signatures(
    prepared: PreparedLifecycleSignatures,
    signatures: tuple[DetachedLifecycleSignature, ...],
    bindings: tuple[Ed25519VerificationKeyBinding, ...],
) -> bytes:
    """Reprepare, authenticate and serialize signatures for one lifecycle CTV."""
    if not isinstance(prepared, PreparedLifecycleSignatures):
        raise ValueError("lifecycle_signing_preparation_invalid")
    recomputed = prepare_lifecycle_signatures(prepared.lifecycle_kind, prepared.template_bytes)
    if recomputed.requests != prepared.requests:
        raise ValueError("lifecycle_signing_preparation_substituted")
    if len(signatures) != len(recomputed.requests):
        raise ValueError("lifecycle_signing_signature_count_invalid")
    raw_signatures: list[bytes] = []
    for request, supplied in zip(recomputed.requests, signatures, strict=True):
        if not isinstance(supplied, DetachedLifecycleSignature) or (
            supplied.lifecycle_kind,
            supplied.record_index,
            supplied.signature_index,
            supplied.profile_id,
            supplied.public_key_digest,
            supplied.purpose,
        ) != (
            prepared.lifecycle_kind,
            request.record_index,
            request.signature_index,
            request.profile_id,
            request.public_key_digest,
            request.purpose,
        ):
            raise ValueError("lifecycle_signing_signature_coordinate_invalid")
        if not isinstance(supplied.signature, bytes):
            raise ValueError("lifecycle_signing_signature_invalid")
        raw_signatures.append(supplied.signature)
    verifier = Ed25519SignatureVerifier(bindings)
    return assemble_current_lifecycle_detached_signatures(
        prepared.template_bytes, prepared.lifecycle_kind, tuple(raw_signatures), verifier=verifier.verify
    )


def _write_new(path: str, value: bytes) -> None:
    with open(path, "xb") as output:
        output.write(value)


def _signature_argument(value: str) -> tuple[int, str]:
    try:
        index_text, path = value.split("=", 1)
        index = int(index_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("signature must be INDEX=PATH") from exc
    if index < 0 or not path:
        raise argparse.ArgumentTypeError("signature must be INDEX=PATH")
    return index, path


def _lifecycle_kind(value: str) -> LifecycleSigningKind:
    if value not in _KINDS:
        raise ValueError("lifecycle_signing_kind_invalid")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--assemble", action="store_true")
    parser.add_argument("--kind", choices=_KINDS, required=True)
    parser.add_argument("--template", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--bindings")
    parser.add_argument("--signature", action="append", type=_signature_argument, default=[])
    args = parser.parse_args(argv)

    prepared = prepare_lifecycle_signatures(_lifecycle_kind(args.kind), Path(args.template).read_bytes())
    if args.prepare:
        if args.bindings is not None or args.signature:
            parser.error("--prepare does not accept --bindings or --signature")
        _write_new(args.output, json.dumps({
            "requests": [
                {
                    "lifecycle_kind": prepared.lifecycle_kind,
                    "record_index": request.record_index,
                    "signature_index": request.signature_index,
                    "profile_id": request.profile_id,
                    "public_key_digest": request.public_key_digest,
                    "purpose": request.purpose,
                    "preimage_hex": request.preimage.hex(),
                }
                for request in prepared.requests
            ]
        }, sort_keys=True, separators=(",", ":")).encode())
        return 0
    if args.bindings is None:
        parser.error("--assemble requires --bindings")
    by_index = dict(args.signature)
    if len(by_index) != len(args.signature) or set(by_index) != set(range(len(prepared.requests))):
        parser.error("--assemble requires each --signature INDEX=PATH exactly once")
    supplied = tuple(
        DetachedLifecycleSignature(
            prepared.lifecycle_kind,
            request.record_index,
            request.signature_index,
            request.profile_id,
            request.public_key_digest,
            request.purpose,
            Path(by_index[index]).read_bytes(),
        )
        for index, request in enumerate(prepared.requests)
    )
    _write_new(args.output, assemble_lifecycle_signatures(
        prepared, supplied, load_release_signing_bindings(args.bindings)
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
