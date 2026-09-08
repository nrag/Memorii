"""Prepare and verify unsigned observation activation target manifests."""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path

from memorii.core.memory_evolution.observation_activation_preparation import (
    ObservationActivationPreparationInputs,
    prepare_observation_activation_target,
)
from memorii.core.memory_evolution.observation_activation_target import (
    manifest_preimage,
    parse_observation_activation_target_manifest,
)
from memorii.tools.semantic_ingestion_offline_signing import load_pem_ed25519_public_key_binding, verify_preimage


def _load_factory(specification: str):
    module_name, separator, attribute = specification.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("host_factory_must_be_module_colon_callable")
    factory = getattr(importlib.import_module(module_name), attribute, None)
    if not callable(factory):
        raise ValueError("host_factory_not_callable")
    return factory


def _prepare(args: argparse.Namespace) -> int:
    output = Path(args.output_directory)
    if output.exists():
        raise ValueError(f"refusing_to_overwrite_existing_output_directory:{output}")
    inputs = _load_factory(args.host_factory)()
    if type(inputs) is not ObservationActivationPreparationInputs:
        raise ValueError("host_factory_did_not_return_observation_activation_preparation_inputs")
    prepared = prepare_observation_activation_target(
        inputs, args.target_id, args.signature_profile_id, args.public_key_digest
    )
    output.mkdir(parents=False)
    (output / "target-manifest.json").write_bytes(prepared.manifest_raw_bytes)
    (output / "target-preimage.bin").write_bytes(prepared.preimage)
    return 0


def _verify(args: argparse.Namespace) -> int:
    manifest = parse_observation_activation_target_manifest(Path(args.manifest).read_bytes())
    if (manifest.signature_profile_id, manifest.public_key_digest) != (args.profile_id, args.public_key_digest):
        return 1
    binding = load_pem_ed25519_public_key_binding(
        Path(args.public_key).read_bytes(),
        profile_id=args.profile_id,
        digest_domain=Path(args.digest_domain_file).read_bytes(),
        public_key_digest=args.public_key_digest,
    )
    return (
        0
        if verify_preimage(
            binding=binding, preimage=manifest_preimage(manifest), signature=Path(args.signature).read_bytes()
        )
        else 1
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--host-factory", required=True)
    prepare.add_argument("--target-id", required=True)
    prepare.add_argument("--signature-profile-id", required=True)
    prepare.add_argument("--public-key-digest", required=True)
    prepare.add_argument("--output-directory", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--signature", required=True)
    verify.add_argument("--public-key", required=True)
    verify.add_argument("--profile-id", required=True)
    verify.add_argument("--public-key-digest", required=True)
    verify.add_argument("--digest-domain-file", required=True)
    args = parser.parse_args(argv)
    try:
        return _prepare(args) if args.command == "prepare" else _verify(args)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
