"""Reproduce construction bytes and compare independently compiled output.

Run from the repository with PYTHONPATH=.:memorii. --refresh-generated updates
only the construction package; this script never supplies deployment pins or
activates a registry. The two compilers receive the same raw source inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from acceptance.observation_registry_compiler import SourceLimits, compile_observation_registry
from memorii.core.memory_evolution.ingestion_contracts import _length_prefixed
from memorii.core.memory_evolution.typed_value_declarations import ProtectedDeclarationParseLimits
from memorii.core.memory_evolution.typed_value_decoder_sources import DecoderSourceSelection, ProtectedDecoderSourceManifestLimits
from memorii.core.memory_evolution.typed_value_publication import ProtectedTypedValuePublicationLimits, parse_typed_value_publication_manifest
from memorii.core.memory_evolution.typed_value_publication_authoring import author_typed_value_publication_package


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-generated", action="store_true")
    args = parser.parse_args()
    work = Path(__file__).resolve().parent
    root = work.parents[3]
    package_root = root / "memorii"
    source = package_root / "memorii/core/memory_evolution/observation_registry_sources"
    selection = json.loads((work / "decoder-source-selection.json").read_bytes())
    inventory = json.loads((work / "source-role-inventory.json").read_bytes())
    raw_roles = []
    for row in inventory["files"]:
        raw = (root / row["path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError(f"reviewed source changed: {row['path']}")
        raw_roles.append(raw)
    rows = tuple(
        DecoderSourceSelection(decoder, item["source_file_id"], item["relative_path"])
        for decoder in selection["decoder_ids"]
        for item in selection["shared_files"]
    )
    limits = ProtectedTypedValuePublicationLimits(
        ProtectedDeclarationParseLimits(2_000_000, 300_000, 64),
        ProtectedDecoderSourceManifestLimits(8_000_000, 300_000, 64, 10_000, 2_000_000),
        2_000_000,
    )
    result = author_typed_value_publication_package(
        raw_roles, rows, source_package_root=package_root, limits=limits,
        forbidden_decoder_source_paths=frozenset(str(path.relative_to(package_root)) for path in source.rglob("*.json")),
    )
    generated = {
        source / "decoder-source-manifest.json": result.raw_decoder_source_manifest,
        source / "publication-manifest.json": result.raw_publication_manifest,
    }
    role_pairs = []
    grammar_raw = None
    for raw in result.raw_role_sources:
        role = json.loads(raw)
        kind = role["role"]
        descriptor = kind if kind in {"grammar", "registry"} else f"{kind}/{role['schema_id']}/{role['schema_version']}"
        role_pairs.append((descriptor, raw))
        if kind == "grammar":
            grammar_raw = raw
        elif kind == "registry":
            generated[source / "registry.json"] = raw
        elif kind == "decoder":
            path = source / kind / role["schema_id"] / f"{role['schema_version']}.json"
            if not path.resolve().is_relative_to(source.resolve()):
                raise ValueError("generated role path escapes source package")
            generated[path] = raw
    for path, raw in generated.items():
        if args.refresh_generated:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        elif path.read_bytes() != raw:
            raise ValueError(f"construction bytes changed: {path.relative_to(root)}")
    independent = compile_observation_registry(
        role_pairs,
        decoder_source_manifest_bytes=result.raw_decoder_source_manifest,
        decoder_source_root=package_root,
        publication_manifest_bytes=result.raw_publication_manifest,
        limits=SourceLimits(8_000_000, 300_000, 64),
    )
    registry = result.compiled_registry
    profile = registry.profile
    if grammar_raw is None:
        raise ValueError("grammar missing")

    def lp(*parts: str | bytes) -> bytes:
        return _length_prefixed(*(part.encode("utf-8") if isinstance(part, str) else part for part in parts))

    primary_entries = []
    for entry in registry.entries:
        policy = asdict(entry.policy_digests)
        preimage = lp(
            "semantic-ingestion-typed-value-registry-entry", profile.profile_id, profile.profile_version,
            profile.profile_digest, entry.schema_id, entry.schema_version, entry.binding_digest,
            entry.schema_fingerprint, policy["enum_registry_digest"], policy["optional_field_policy_digest"],
            policy["numeric_encoding_spec_registry_digest"], policy["digest_signature_field_policy_digest"],
            entry.decoder_digest, "0", "", "", entry.read_status,
        )
        if hashlib.sha256(preimage).hexdigest() != entry.entry_digest:
            raise ValueError("primary entry preimage mismatch")
        primary_entries.append(dict(
            schema_id=entry.schema_id, schema_version=entry.schema_version,
            schema_fingerprint=entry.schema_fingerprint, **policy,
            decoder_digest=entry.decoder_digest, binding_digest=entry.binding_digest,
            entry_digest=entry.entry_digest, entry_preimage=preimage.hex(),
        ))
    primary = dict(
        profile_digest=profile.profile_digest,
        profile_preimage=lp("semantic-ingestion-typed-value-profile", profile.profile_id, profile.profile_version, profile.grammar_revision, grammar_raw).hex(),
        registry_digest=registry.registry_digest,
        registry_preimage=lp("semantic-ingestion-typed-value-registry", profile.profile_id, profile.profile_version, profile.grammar_revision, profile.grammar_digest, profile.profile_digest, str(len(registry.entries)), *(entry.entry_digest for entry in registry.entries)).hex(),
        entries=primary_entries,
        publication_manifest_digest=parse_typed_value_publication_manifest(result.raw_publication_manifest, maximum_bytes=2_000_000).publication_digest,
    )
    independent_output = dict(
        profile_digest=independent.profile_digest, profile_preimage=independent.profile_preimage.hex(),
        registry_digest=independent.registry_digest, registry_preimage=independent.registry_preimage.hex(),
        entries=[dict(asdict(entry), entry_preimage=entry.entry_preimage.hex()) for entry in independent.entries],
        publication_manifest_digest=independent.publication_manifest_digest,
    )
    def encode(value: object) -> bytes:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    primary_bytes, independent_bytes = encode(primary), encode(independent_output)
    if primary_bytes != independent_bytes:
        raise ValueError("complete normalized compiler outputs differ")
    (work / "independent-output.json").write_bytes(independent_bytes)
    evidence = dict(
        status="LOCAL_POSITIVE_PARITY_NOT_VECTOR_OR_RELEASE_APPROVAL",
        role_count=len(role_pairs), entry_count=len(registry.entries),
        output_sha256=hashlib.sha256(independent_bytes).hexdigest(),
        independent_source_sha256=hashlib.sha256((root / "acceptance/observation_registry_compiler.py").read_bytes()).hexdigest(),
        source_inputs={name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(role_pairs)},
        decoder_source_manifest_sha256=hashlib.sha256(result.raw_decoder_source_manifest).hexdigest(),
        publication_manifest_sha256=hashlib.sha256(result.raw_publication_manifest).hexdigest(),
        profile_digest=profile.profile_digest, registry_digest=registry.registry_digest,
        publication_digest=primary["publication_manifest_digest"],
        complete_normalized_output_bytes_equal=True,
        remaining=["run verify_registry_vectors.py for the combined positive/rejection manifest", "protected deployment/runtime composition", "whole-candidate gates and review"],
    )
    (work / "independent-positive-parity.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps({key: value for key, value in evidence.items() if key != "source_inputs"}, indent=2))


if __name__ == "__main__":
    main()
