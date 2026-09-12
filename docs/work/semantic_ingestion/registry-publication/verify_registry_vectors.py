"""Compare independently authored registry vectors against both implementations.

Run from the repository with PYTHONPATH=.:memorii. This is local construction
evidence, not deployment authorization. Declaration rejection is checked before
derived registry commitments, so stale hashes cannot hide missing validation.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from acceptance.observation_registry_compiler import (
    RegistrySourceError,
    SourceLimits,
    compile_observation_registry,
    derive_observation_registry,
)
from acceptance.observation_registry_vectors import RegistryRejectionVector, build_rejection_vectors
from memorii.core.memory_evolution.ingestion_contracts import length_prefixed
from memorii.core.memory_evolution.typed_value_declarations import (
    DeclarationParseError,
    ProtectedDeclarationParseLimits,
)
from memorii.core.memory_evolution.typed_value_decoder_sources import (
    DecoderSourceManifestError,
    ProtectedDecoderSourceManifestLimits,
    verify_decoder_source_manifest,
)
from memorii.core.memory_evolution.typed_value_publication import (
    DecoderSourceSnapshotPin,
    ProtectedTypedValuePublicationLimits,
    ProtectedTypedValuePublicationPins,
    TypedValuePublicationError,
    parse_typed_value_publication_manifest,
    verify_typed_value_publication,
)
from memorii.core.memory_evolution.typed_value_registry_compilation import (
    TypedValueRegistryCompilationError,
    author_typed_value_registry_role,
    compile_typed_value_registry,
)

_DECLARATION_LIMITS = ProtectedDeclarationParseLimits(1_000_000, 100_000, 64)
_SOURCE_LIMITS = ProtectedDecoderSourceManifestLimits(1_000_000, 100_000, 64, 100, 1_000_000)
_LIMITS = ProtectedTypedValuePublicationLimits(_DECLARATION_LIMITS, _SOURCE_LIMITS, 1_000_000)
_INDEPENDENT_LIMITS = SourceLimits(1_000_000, 100_000, 64)
_FULL_LIMITS = ProtectedTypedValuePublicationLimits(
    ProtectedDeclarationParseLimits(2_000_000, 300_000, 64),
    ProtectedDecoderSourceManifestLimits(8_000_000, 300_000, 64, 10_000, 2_000_000),
    2_000_000,
)
_FULL_INDEPENDENT_LIMITS = SourceLimits(8_000_000, 300_000, 64)


def _json_bytes(value):
    def convert(item):
        if isinstance(item, bytes):
            return {"hex": item.hex()}
        raise TypeError(f"unsupported evidence value: {type(item)}")
    return json.dumps(value, default=convert, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _lp(*parts):
    return length_prefixed(*(part.encode("utf-8") if isinstance(part, str) else part for part in parts))


def _primary_output(verified):
    registry = verified.compiled_registry
    profile = registry.profile
    grammar = next(role.raw_bytes for role in registry.parsed_roles if role.role == "grammar")
    entries = []
    for entry in registry.entries:
        policy = asdict(entry.policy_digests)
        entries.append(dict(
            schema_id=entry.schema_id, schema_version=entry.schema_version,
            schema_fingerprint=entry.schema_fingerprint, **policy,
            decoder_digest=entry.decoder_digest, binding_digest=entry.binding_digest,
            entry_digest=entry.entry_digest,
            entry_preimage=_lp(
                "semantic-ingestion-typed-value-registry-entry", profile.profile_id,
                profile.profile_version, profile.profile_digest, entry.schema_id,
                entry.schema_version, entry.binding_digest, entry.schema_fingerprint,
                policy["enum_registry_digest"], policy["optional_field_policy_digest"],
                policy["numeric_encoding_spec_registry_digest"], policy["digest_signature_field_policy_digest"],
                entry.decoder_digest, "0", "", "", entry.read_status,
            ),
        ))
    return dict(
        profile_digest=profile.profile_digest,
        profile_preimage=_lp("semantic-ingestion-typed-value-profile", profile.profile_id, profile.profile_version, profile.grammar_revision, grammar),
        registry_digest=registry.registry_digest,
        registry_preimage=_lp("semantic-ingestion-typed-value-registry", profile.profile_id, profile.profile_version, profile.grammar_revision, profile.grammar_digest, profile.profile_digest, str(len(entries)), *(entry.entry_digest for entry in registry.entries)),
        entries=entries,
        publication_manifest_digest=verified.publication_manifest.publication_digest,
    )


def _primary(vector, root, limits=_LIMITS):
    raw_roles = tuple(raw for _, raw in vector.raw_role_pairs)
    if vector.boundary == "declaration":
        author_typed_value_registry_role(
            (raw for role, raw in vector.raw_role_pairs if role != "registry"),
            limits=_DECLARATION_LIMITS,
        )
        return None
    if vector.boundary == "registry" and not vector.expected_valid:
        compile_typed_value_registry(raw_roles, limits=_DECLARATION_LIMITS)
        return None
    if vector.boundary == "source":
        verify_decoder_source_manifest(vector.decoder_source_manifest_bytes, source_package_root=root, limits=_SOURCE_LIMITS)
    manifest = parse_typed_value_publication_manifest(vector.publication_manifest_bytes, maximum_bytes=1_000_000)
    # Runtime verifies the vector's pinned raw bytes; this harness separately
    # compares the independent complete expected result and source identity.
    raw_vector = _json_bytes(asdict(vector))
    pins = ProtectedTypedValuePublicationPins(
        manifest.publication_digest, manifest.registry_digest,
        tuple(DecoderSourceSnapshotPin(row.decoder_id, row.source_snapshot_digest) for row in manifest.decoder_source_snapshots),
        hashlib.sha256(raw_vector).hexdigest(),
    )
    return _primary_output(verify_typed_value_publication(
        raw_roles, vector.decoder_source_manifest_bytes, vector.publication_manifest_bytes,
        raw_vector, source_package_root=root, limits=limits, pins=pins,
    ))


def _independent(vector, root, limits=_INDEPENDENT_LIMITS):
    if vector.boundary == "declaration":
        derive_observation_registry(
            ((role, raw) for role, raw in vector.raw_role_pairs if role != "registry"),
            limits=limits,
        )
        return None
    report = compile_observation_registry(
        vector.raw_role_pairs,
        decoder_source_manifest_bytes=vector.decoder_source_manifest_bytes,
        decoder_source_root=root,
        publication_manifest_bytes=vector.publication_manifest_bytes,
        limits=limits,
    )
    output = asdict(report)
    for key in ("source_identities", "decoder_source_manifest_bytes", "publication_manifest_bytes"):
        del output[key]
    return output


def _materialize_sources(vector, directory):
    container = Path(directory).resolve()
    root = container / vector.source_root_relative_path
    actual = container / vector.source_root_symlink_target if vector.source_root_symlink_target else root
    actual.mkdir(parents=True, exist_ok=True)
    if not actual.resolve().is_relative_to(container):
        raise ValueError("vector setup root escapes temporary directory")
    for source in vector.decoder_source_files:
        path = actual / source.relative_path
        if not path.resolve().is_relative_to(container):
            raise ValueError("vector setup file escapes temporary directory")
        path.parent.mkdir(parents=True, exist_ok=True)
        if source.symlink_target is None:
            path.write_bytes(source.raw_bytes)
        else:
            target = actual / source.symlink_target
            if not target.resolve().is_relative_to(container):
                raise ValueError("vector setup link escapes temporary directory")
            path.symlink_to(target)
    if vector.source_root_symlink_target:
        root.symlink_to(actual, target_is_directory=True)
    return root


def _full_package(work, repository):
    """Recheck the full raw package against retained independent expected bytes."""
    source = repository / "memorii/memorii/core/memory_evolution/observation_registry_sources"
    proof = json.loads((work / "independent-positive-parity.json").read_bytes())
    compiler_sha = hashlib.sha256((repository / "acceptance/observation_registry_compiler.py").read_bytes()).hexdigest()
    if proof["independent_source_sha256"] != compiler_sha:
        raise ValueError("full package independent implementation identity is stale")
    expected_raw = (work / "independent-output.json").read_bytes()
    if hashlib.sha256(expected_raw).hexdigest() != proof["output_sha256"]:
        raise ValueError("full package expected output identity mismatch")
    expected = json.loads(expected_raw)
    for key in ("profile_preimage", "registry_preimage"):
        expected[key] = bytes.fromhex(expected[key])
    for entry in expected["entries"]:
        entry["entry_preimage"] = bytes.fromhex(entry["entry_preimage"])
    raw_roles = []
    for role, digest in proof["source_inputs"].items():
        relative = role + ".json"
        path = source / relative
        if not path.resolve().is_relative_to(source.resolve()):
            raise ValueError("full package role path escapes source package")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError(f"full package source identity changed: {role}")
        raw_roles.append((role, raw))
    decoder_manifest = (source / "decoder-source-manifest.json").read_bytes()
    publication_manifest = (source / "publication-manifest.json").read_bytes()
    if hashlib.sha256(decoder_manifest).hexdigest() != proof["decoder_source_manifest_sha256"]:
        raise ValueError("full package decoder manifest changed")
    if hashlib.sha256(publication_manifest).hexdigest() != proof["publication_manifest_sha256"]:
        raise ValueError("full package publication manifest changed")
    vector = RegistryRejectionVector(
        name="complete_observation_publication", expected_valid=True,
        rationale="Complete checked-in role package and original named decoder source files.",
        raw_role_pairs=tuple(raw_roles), decoder_source_files=(),
        decoder_source_manifest_bytes=decoder_manifest,
        publication_manifest_bytes=publication_manifest, boundary="registry",
    )
    expected_bytes = _json_bytes(expected)
    primary = _primary(vector, repository / "memorii", _FULL_LIMITS)
    independent = _independent(vector, repository / "memorii", _FULL_INDEPENDENT_LIMITS)
    if _json_bytes(primary) != expected_bytes or _json_bytes(independent) != expected_bytes:
        raise ValueError("full publication complete outputs do not agree")
    decoder_sources = {
        row["relative_path"]: row["sha256"]
        for row in json.loads(decoder_manifest)["files"]
    }
    return dict(
        name=vector.name, source_inputs=proof["source_inputs"],
        decoder_sources=decoder_sources,
        decoder_source_manifest_sha256=proof["decoder_source_manifest_sha256"],
        publication_manifest_sha256=proof["publication_manifest_sha256"],
        expected_complete_output=expected,
        expected_output_sha256=hashlib.sha256(expected_bytes).hexdigest(),
        both_complete_outputs_equal=True,
    )


def main():
    work = Path(__file__).resolve().parent
    repository = work.parents[3]
    vectors = build_rejection_vectors()
    results = []
    for vector in vectors:
        with tempfile.TemporaryDirectory(prefix="observation-registry-vector-") as directory:
            root = _materialize_sources(vector, directory)
            expected_bytes = None if vector.expected_report is None else _json_bytes(asdict(vector.expected_report))
            row = dict(name=vector.name, boundary=vector.boundary, expected_valid=vector.expected_valid)
            for name, compiler, errors in (
                ("primary", _primary, (DeclarationParseError, TypedValueRegistryCompilationError, DecoderSourceManifestError, TypedValuePublicationError)),
                ("independent", _independent, (RegistrySourceError,)),
            ):
                try:
                    output = compiler(vector, root)
                except errors as error:
                    row[name] = dict(accepted=False, error=str(error), matches=not vector.expected_valid)
                else:
                    matches = vector.expected_valid and expected_bytes == _json_bytes(output)
                    row[name] = dict(accepted=True, matches=matches)
                    if output is not None:
                        row[name]["output_sha256"] = hashlib.sha256(_json_bytes(output)).hexdigest()
            results.append(row)
    full_package = _full_package(work, repository)
    manifest = dict(
        kind="independent_registry_vector_manifest", format_version=1,
        independent_implementation={path: hashlib.sha256((repository / path).read_bytes()).hexdigest() for path in ("acceptance/observation_registry_compiler.py", "acceptance/observation_registry_vectors.py")},
        allowed_shared_inputs=["normative literal grammar", "normative declaration and LP/SHA-256 specification", "explicit raw source package", "Python standard library"],
        prohibited_shared_inputs=["production compiler or codec", "runtime models or callbacks", "reflection", "primary expected outputs", "historical profile-2 fixture authority"],
        vectors=[asdict(vector) for vector in vectors],
        full_publication_vector=full_package,
    )
    raw_manifest = _json_bytes(manifest)
    (work / "registry-vector-manifest.json").write_bytes(raw_manifest)
    failures = [row for row in results if not row["primary"]["matches"] or not row["independent"]["matches"]]
    report = dict(status="LOCAL_VECTOR_PARITY" if not failures else "VECTOR_PARITY_INCOMPLETE", vector_count=len(vectors), full_publication_entries=len(full_package["expected_complete_output"]["entries"]), full_publication_role_count=len(full_package["source_inputs"]), manifest_sha256=hashlib.sha256(raw_manifest).hexdigest(), results=results, failures=failures, limitations=["construction parity only", "not CI or deployment authority", "protected runtime composition and final review remain open"])
    (work / "registry-vector-results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
