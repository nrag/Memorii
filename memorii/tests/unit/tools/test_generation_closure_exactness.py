"""Focused tests for exact C2 generation membership and dependency closure."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest
from memorii.core.memory_evolution.ingestion_contracts import (
    decode_artifact,
    decode_typed_value,
    encode_artifact,
    encode_typed_value,
    serialize_artifact,
)
from memorii.tools.semantic_ingestion_execution_evidence import (
    _M0_GENERATION_DEPENDENCIES,
    _M0_GENERATION_ORDER,
    ExecutionEvidenceError,
    _verify_m0_manifest_graph,
    _verify_m0_registered_body_shape,
    _verify_optional_generation_closure,
)
from memorii.tools.semantic_ingestion_scenario_test_trust import (
    ExplicitTestIndependentGenerationVerifier,
)
from memorii.tools.semantic_ingestion_traceability_registry import load_registry_bytes
from memorii.tools.semantic_ingestion_traceability_release import VerifierHeldTrustMaterial
from tests.unit.tools.test_scenario_test_trust import (
    _generation_package as current_generation_package,
)
from tests.unit.tools.test_scenario_test_trust import (
    _inputs as current_inputs,
)

ROOT = Path(__file__).parents[4]
DESIGN = ROOT / "docs/design/semantic_ingestion_architecture.md"
REGISTRY = ROOT / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json"
CTV_AUTHORITY = ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors/ctv-binding-authority-v2.json"


def _synthetic_graph() -> tuple[list[dict[str, object]], dict[str, bytes]]:
    coordinates = {
        kind: f"sia-traceability/v1/{kind}/{sha256(kind.encode()).hexdigest()}" for kind in _M0_GENERATION_ORDER
    }
    members = [
        {
            "artifact_kind": kind,
            "artifact_coordinate": coordinates[kind],
            "artifact_digest": sha256(kind.encode()).hexdigest(),
            "depends_on_coordinates": sorted(
                coordinates[dependency] for dependency in _M0_GENERATION_DEPENDENCIES[kind]
            ),
            "schema_id": f"synthetic.{kind}",
            "schema_version": 1,
            "binding_digest": "0" * 64,
        }
        for kind in _M0_GENERATION_ORDER
    ]
    return members, {str(member["artifact_coordinate"]): b"x" for member in members}


@lru_cache(maxsize=1)
def _package() -> tuple[dict[str, object], bytes, dict[str, bytes], bytes, bytes]:
    design = DESIGN.read_bytes()
    registry_bytes = REGISTRY.read_bytes()
    built = current_inputs()
    manifest, members = current_generation_package()
    return built, manifest, members, design, registry_bytes


def _rewrite_manifest(raw: bytes, mutate: object) -> bytes:
    envelope = decode_artifact(raw)
    body = decode_typed_value(envelope.canonical_value_bytes)
    assert isinstance(body, dict)
    changed = deepcopy(body)
    assert callable(mutate)
    mutate(changed)
    digest_body = {
        key: value
        for key, value in changed.items()
        if key not in {"signer_coordinate", "signature", "generation_manifest_digest"}
    }
    changed["generation_manifest_digest"] = sha256(
        b"memorii:sia-traceability-approval-generation:v1\0" + encode_typed_value(digest_body)
    ).hexdigest()
    signer = changed["signer_coordinate"]
    assert isinstance(signer, dict)
    preimage = encode_typed_value(
        {
            "issuance_purpose": "semantic_ingestion_traceability_approval_generation",
            "body_binding": envelope.binding.as_value(),
            "generation_manifest_digest": changed["generation_manifest_digest"],
            "signer_coordinate": signer,
        }
    )
    sign = cast(Callable[[str, str, bytes], bytes], current_inputs()["sign"])
    changed["signature"] = sign(
        str(signer["signature_profile_id"]),
        str(signer["key_or_certificate_digest"]),
        preimage,
    ).hex()
    return serialize_artifact(changed, envelope.binding)


def _verify(
    built: dict[str, object],
    manifest: bytes,
    members: dict[str, bytes],
    design: bytes,
    registry_bytes: bytes,
) -> None:
    typed = built["typed"]
    assert isinstance(typed, dict)
    pointer_envelope = decode_artifact(typed["active_pointer"])
    pointer = decode_typed_value(pointer_envelope.canonical_value_bytes)
    manifest_body = decode_typed_value(decode_artifact(manifest).canonical_value_bytes)
    assert isinstance(pointer, dict)
    assert isinstance(manifest_body, dict)
    pointer["generation_id"] = manifest_body["generation_id"]
    pointer["generation_manifest_digest"] = manifest_body["generation_manifest_digest"]
    pointer_body = {key: value for key, value in pointer.items() if key not in {"signature", "active_pointer_digest"}}
    pointer_digest = sha256(
        b"memorii:sia-traceability-active-release-pointer:v1\0" + encode_typed_value(pointer_body)
    ).hexdigest()
    pointer["active_pointer_digest"] = pointer_digest
    pointer_signer = pointer["signer_coordinate"]
    assert isinstance(pointer_signer, dict)
    pointer_preimage = encode_typed_value(
        {
            "issuance_purpose": "semantic_ingestion_traceability_active_release_pointer",
            "body_binding": pointer_envelope.binding.as_value(),
            "active_pointer_digest": pointer_digest,
            "signer_coordinate": pointer_signer,
        }
    )
    pointer["signature"] = sha256(
        b"memorii:acceptance-verifier:v1\0"
        + str(pointer_signer["signature_profile_id"]).encode()
        + b"\0"
        + str(pointer_signer["key_or_certificate_digest"]).encode()
        + b"\0"
        + pointer_preimage
    ).hexdigest()
    pointer_bytes = serialize_artifact(pointer, pointer_envelope.binding)
    release = decode_typed_value(decode_artifact(typed["release"]).canonical_value_bytes)
    bootstrap = decode_typed_value(decode_artifact(typed["bootstrap_anchor"]).canonical_value_bytes)
    assert isinstance(release, dict) and isinstance(bootstrap, dict)
    release_signer = release["signer_coordinate"]
    assert isinstance(release_signer, dict)
    verifier = built["independent_generation_verifier"]
    assert isinstance(verifier, ExplicitTestIndependentGenerationVerifier)
    material = built["material"]
    assert isinstance(material, VerifierHeldTrustMaterial)
    bootstrap_anchors = (
        material.bootstrap_anchor_bytes,
        *material.provisioned_successor_root_bytes,
    )
    recovery_roots = material.recovery_root_bytes
    _verify_optional_generation_closure(
        generation_manifest_bytes=manifest,
        generation_member_bytes=members,
        design_document_bytes=design,
        registry_bytes=registry_bytes,
        registry=load_registry_bytes(registry_bytes),
        release_roots={
            **built["roots"],  # type: ignore[dict-item]
            **built["expected_release_roots"],  # type: ignore[dict-item]
        },
        active_pointer_artifact=pointer_bytes,
        expected_member_bytes={
            "bootstrap_anchor": typed["bootstrap_anchor"],
            "bootstrap_anchors": bootstrap_anchors,
            "recovery_root": typed["recovery_root"],
            "recovery_roots": recovery_roots,
            "recovery_policy": typed["recovery_policy"],
            "trust_lifecycle_root": typed["trust_lifecycle_root"],
            "release": typed["release"],
            "release_history": typed["release_history"],
            "pointer_history": next(
                raw for coordinate, raw in members.items() if "/pointer_history/" in coordinate
            ),
        },
        active_signers=(
            (
                str(release_signer["issuer_id"]),
                str(release["bootstrap_anchor_digest"]),
                str(release_signer["signature_profile_id"]),
                str(release_signer["key_or_certificate_digest"]),
                datetime.fromisoformat(str(release_signer["eligible_not_before"]).replace("Z", "+00:00")),
                None if release_signer["eligible_not_after"] is None else datetime.fromisoformat(str(release_signer["eligible_not_after"]).replace("Z", "+00:00")),
            ),
        ),
        verify_signature=built["material"].verify_signature,  # type: ignore[union-attr]
        now=built["now"],  # type: ignore[arg-type]
        independent_verifier=verifier,
    )


def test_exact_scenario_generation_closure_is_accepted() -> None:
    built, manifest, members, design, registry_bytes = _package()
    _verify(built, manifest, members, design, registry_bytes)


@pytest.mark.parametrize(
    "mutation",
    ["alternate_edge", "extra_member", "omitted_member", "valid_dag_reorder"],
)
def test_manifest_graph_preflight_rejects_before_member_decoding(
    mutation: str,
) -> None:
    members, member_bytes = _synthetic_graph()
    if mutation == "alternate_edge":
        coverage = next(member for member in members if member["artifact_kind"] == "coverage_root")
        registry = next(member for member in members if member["artifact_kind"] == "registry_source")
        coverage["depends_on_coordinates"] = [registry["artifact_coordinate"]]
    elif mutation == "extra_member":
        extra = deepcopy(members[-1])
        extra["artifact_kind"] = "golden_typed_input_fixture"
        extra_digest = sha256(b"extra").hexdigest()
        extra["artifact_digest"] = extra_digest
        extra["artifact_coordinate"] = f"sia-traceability/v1/golden_typed_input_fixture/{extra_digest}"
        extra["depends_on_coordinates"] = []
        members.append(extra)
        member_bytes[str(extra["artifact_coordinate"])] = b"x"
    elif mutation == "omitted_member":
        omitted = next(member for member in members if member["artifact_kind"] == "trust_snapshot")
        members.remove(omitted)
        del member_bytes[str(omitted["artifact_coordinate"])]
    else:
        left = _M0_GENERATION_ORDER.index("bootstrap_anchor")
        right = _M0_GENERATION_ORDER.index("recovery_root")
        members[left], members[right] = members[right], members[left]
    with pytest.raises(ExecutionEvidenceError):
        _verify_m0_manifest_graph(cast(list[object], members), member_bytes)


_BODY_SHAPE_CASES = {
    "structural_manifest": {
        "grammar_revision": "v1",
        "design_document_digest": "design",
        "registry_source_identity": "registry",
        "registry_root_digests": [],
        "units": [],
        "mappings": [],
        "structural_manifest_digest": "digest",
    },
    "bootstrap_anchor_history": {
        "history_id": "bootstrap-history",
        "canonical_profile_binding": {},
        "anchors": [{}],
        "history_digest": "digest",
    },
    "recovery_root_history": {
        "history_id": "recovery-root-history",
        "canonical_profile_binding": {},
        "recovery_roots": [{}],
        "history_digest": "digest",
    },
    "recovery_policy_history": {
        "history_id": "recovery-policy-history",
        "canonical_profile_binding": {},
        "policies": [{}],
        "history_digest": "digest",
    },
    "trust_snapshot": {
        "snapshot_id": "snapshot",
        "issuance_purpose": "semantic_ingestion_traceability_release_trust_snapshot",
        "canonical_profile_binding": {},
        "release_id": "release",
        "release_epoch": 1,
        "release_sequence": 1,
        "bootstrap_anchor_digest": "bootstrap",
        "recovery_policy_digest": "policy",
        "trust_lifecycle_root_digest": "lifecycle",
        "lifecycle_recorded_time_cutoff": datetime.min.replace(tzinfo=UTC),
        "qualified_issuers": [{}],
        "created_at": datetime.min.replace(tzinfo=UTC),
        "trust_snapshot_digest": "digest",
    },
    "golden_vector_manifest": {
        "manifest_id": "golden",
        "manifest_version": 1,
        "source_path": "docs/design/semantic_ingestion/traceability_golden_vectors/v1.json",
        "owner": "acceptance_independent_vector_author",
        "authority_use": "verification_fixture_not_runtime_authority",
        "canonical_profile_binding": {},
        "design_document_digest": "design",
        "registry_source_identity": "registry",
        "fixtures": [],
        "vectors": [],
        "golden_vector_manifest_digest": "digest",
    },
}


@pytest.mark.parametrize("kind", sorted(_BODY_SHAPE_CASES))
@pytest.mark.parametrize("mutation", ["missing", "extra", "empty"])
def test_registered_m0_body_shape_rejects_required_extra_and_placeholder_fields(
    kind: str, mutation: str
) -> None:
    body = deepcopy(_BODY_SHAPE_CASES[kind])
    if mutation == "missing":
        body.pop(next(iter(body)))
    elif mutation == "extra":
        body["canonical_profile_id"] = "legacy-alias"
    else:
        body = {}
    with pytest.raises(ExecutionEvidenceError, match="body fields"):
        _verify_m0_registered_body_shape(kind, body)


@pytest.mark.parametrize(
    ("kind", "field"),
    [
        ("bootstrap_anchor_history", "anchors"),
        ("recovery_root_history", "recovery_roots"),
        ("recovery_policy_history", "policies"),
        ("trust_snapshot", "qualified_issuers"),
    ],
)
def test_registered_m0_body_shape_rejects_empty_semantic_collections(
    kind: str, field: str
) -> None:
    body = deepcopy(_BODY_SHAPE_CASES[kind])
    body[field] = []
    with pytest.raises(ExecutionEvidenceError, match="non-empty canonical collection"):
        _verify_m0_registered_body_shape(kind, body)


def test_registered_golden_body_allows_empty_closed_collections() -> None:
    _verify_m0_registered_body_shape(
        "golden_vector_manifest",
        deepcopy(_BODY_SHAPE_CASES["golden_vector_manifest"]),
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_id", "WrongBody.v1"),
        ("schema_version", 2),
        ("binding_digest", "0" * 64),
    ],
)
def test_generation_rejects_member_binding_metadata_mutations(field: str, value: object) -> None:
    built, manifest, members, design, registry_bytes = _package()

    def mutate(body: dict[str, object]) -> None:
        rows = body["members"]
        assert isinstance(rows, list)
        row = rows[2]
        assert isinstance(row, dict)
        row[field] = value

    with pytest.raises(ExecutionEvidenceError, match="binding"):
        _verify(
            built,
            _rewrite_manifest(manifest, mutate),
            members,
            design,
            registry_bytes,
        )


def test_generation_rejects_dependency_omission() -> None:
    built, manifest, members, design, registry_bytes = _package()

    def mutate(body: dict[str, object]) -> None:
        rows = body["members"]
        assert isinstance(rows, list)
        row = next(row for row in rows if isinstance(row, dict) and row["artifact_kind"] == "recovery_policy")
        assert isinstance(row, dict)
        row["depends_on_coordinates"] = []

    with pytest.raises(ExecutionEvidenceError, match="dependency closure"):
        _verify(
            built,
            _rewrite_manifest(manifest, mutate),
            members,
            design,
            registry_bytes,
        )


def test_generation_rejects_alternate_earlier_reachable_edge() -> None:
    built, manifest, members, design, registry_bytes = _package()

    def mutate(body: dict[str, object]) -> None:
        rows = body["members"]
        assert isinstance(rows, list)
        by_kind = {row["artifact_kind"]: row for row in rows if isinstance(row, dict)}
        by_kind["coverage_root"]["depends_on_coordinates"] = [by_kind["registry_source"]["artifact_coordinate"]]

    with pytest.raises(ExecutionEvidenceError, match="dependency closure"):
        _verify(
            built,
            _rewrite_manifest(manifest, mutate),
            members,
            design,
            registry_bytes,
        )


def test_generation_rejects_valid_dag_noncanonical_reorder() -> None:
    built, manifest, members, design, registry_bytes = _package()

    def mutate(body: dict[str, object]) -> None:
        rows = body["members"]
        assert isinstance(rows, list)
        bootstrap = next(
            index
            for index, row in enumerate(rows)
            if isinstance(row, dict) and row["artifact_kind"] == "bootstrap_anchor"
        )
        recovery = next(
            index for index, row in enumerate(rows) if isinstance(row, dict) and row["artifact_kind"] == "recovery_root"
        )
        rows[bootstrap], rows[recovery] = rows[recovery], rows[bootstrap]

    with pytest.raises(ExecutionEvidenceError, match="member set|canonical"):
        _verify(
            built,
            _rewrite_manifest(manifest, mutate),
            members,
            design,
            registry_bytes,
        )


def test_generation_rejects_extra_valid_typed_member() -> None:
    built, manifest, members, design, registry_bytes = _package()
    envelope = decode_artifact(manifest)
    fixture_binding = envelope.binding.__class__(
        envelope.binding.profile_id,
        envelope.binding.profile_version,
        envelope.binding.profile_digest,
        "TraceabilityGoldenTypedInputFixtureBody.v1",
        1,
        "9ad8061f09262f3e2db406a3a5a6c2a3ad340c7e696a6b41332b4d4e1912f4d3",
    )
    fixture_body = {"fixture_id": "unexpected-extra"}
    fixture = serialize_artifact(fixture_body, fixture_binding)
    fixture_digest = encode_artifact(fixture_body, fixture_binding).artifact_digest
    fixture_coordinate = f"sia-traceability/v1/golden_typed_input_fixture/{fixture_digest}"

    def mutate(body: dict[str, object]) -> None:
        rows = body["members"]
        assert isinstance(rows, list)
        rows.append(
            {
                "artifact_kind": "golden_typed_input_fixture",
                "artifact_coordinate": fixture_coordinate,
                "artifact_digest": fixture_digest,
                "depends_on_coordinates": [],
                "schema_id": fixture_binding.schema_id,
                "schema_version": fixture_binding.schema_version,
                "binding_digest": fixture_binding.binding_digest,
            }
        )

    with pytest.raises(ExecutionEvidenceError, match="member count"):
        _verify(
            built,
            _rewrite_manifest(manifest, mutate),
            {**members, fixture_coordinate: fixture},
            design,
            registry_bytes,
        )


def test_generation_rejects_omitted_transitive_member() -> None:
    built, manifest, members, design, registry_bytes = _package()
    omitted_coordinate = next(key for key in members if "/trust_snapshot/" in key)

    def mutate(body: dict[str, object]) -> None:
        rows = body["members"]
        assert isinstance(rows, list)
        rows[:] = [
            row for row in rows if not (isinstance(row, dict) and row["artifact_coordinate"] == omitted_coordinate)
        ]

    with pytest.raises(ExecutionEvidenceError, match="member count"):
        _verify(
            built,
            _rewrite_manifest(manifest, mutate),
            {key: value for key, value in members.items() if key != omitted_coordinate},
            design,
            registry_bytes,
        )


@pytest.mark.parametrize("field", ["signer_coordinate", "signature"])
def test_generation_rejects_signer_or_signature_tamper(field: str) -> None:
    built, manifest, members, design, registry_bytes = _package()
    envelope = decode_artifact(manifest)
    body = decode_typed_value(envelope.canonical_value_bytes)
    assert isinstance(body, dict)
    if field == "signature":
        body[field] = "00"
    else:
        signer = body[field]
        assert isinstance(signer, dict)
        signer["issuer_id"] = "foreign-signer"
    tampered = serialize_artifact(body, envelope.binding)
    with pytest.raises(ExecutionEvidenceError, match="signature|lifecycle qualified"):
        _verify(built, tampered, members, design, registry_bytes)


def test_generation_rejects_cross_generation_release_member() -> None:
    built, manifest, members, design, registry_bytes = _package()
    typed = built["typed"]
    assert isinstance(typed, dict)
    release = typed["release"]
    assert isinstance(release, bytes)
    coordinate = next(key for key in members if "/release/" in key)
    changed_members = {**members, coordinate: typed["recovery_root"]}
    with pytest.raises(ExecutionEvidenceError, match="validated release input|digest"):
        _verify(built, manifest, changed_members, design, registry_bytes)
