"""End-to-end registered R03/R13 approval coordinates."""

from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueProfileBinding,
    artifact_preimage,
    decode_artifact,
    decode_typed_value,
    encode_artifact,
    encode_typed_value,
    serialize_artifact,
)
from memorii.tools.semantic_ingestion_acceptance_watermark_store import (
    FileTraceabilityReleaseWatermarkStore,
    WatermarkAdvanced,
    WatermarkUnavailable,
)
from memorii.tools.semantic_ingestion_execution_evidence import (
    ExecutionEvidenceError,
    RegisteredApprovalExecutor,
    artifact_digest,
    observation_digest,
    structural_verification_spool,
)
from memorii.tools.semantic_ingestion_structural_ledger import (
    load_checked_in_frozen_structural_manifest_ledger,
)
from memorii.tools.semantic_ingestion_traceability_checker import (
    TraceabilityCoverageError,
    rebuild_structural_manifest_bytes,
)
from memorii.tools.semantic_ingestion_traceability_registry import canonical_document, load_registry
from memorii.tools.semantic_ingestion_traceability_release import (
    AcceptanceTrustStore,
    IndependentGenerationVerificationResult,
    VerifierHeldTrustMaterial,
)
from tests.fixtures.semantic_ingestion.scenario_fixture_authority import (
    ExplicitTestIndependentGenerationVerifier,
)
from tests.fixtures.semantic_ingestion.scenario_fixture_authority import (
    build_generation_package as build_current_generation_package,
)


def _registry_path() -> Path:
    return Path(__file__).parents[4] / "docs" / "design" / "semantic_ingestion" / "traceability_registry" / "registry-v1.json"


def _signature(profile: str, key: str, payload: bytes) -> bytes:
    return sha256(b"memorii:acceptance-verifier:v1\0" + profile.encode() + b"\0" + key.encode() + b"\0" + payload).digest()


def _verifier(profile: str, key: str, payload: bytes, signature: bytes) -> bool:
    return signature == _signature(profile, key, payload)


def _signed(body: dict[str, object], *, domain: bytes, digest_field: str, key: str = "bootstrap-key") -> bytes:
    digest = sha256(domain + b"\0" + canonical_document(body)).hexdigest()
    return canonical_document({**body, digest_field: digest, "signature": _signature("deterministic-v1", key, digest.encode("ascii")).hex()})


def _typed_body(raw: bytes) -> tuple[dict[str, object], CanonicalTypedValueProfileBinding]:
    envelope = decode_artifact(raw)
    value = decode_typed_value(envelope.canonical_value_bytes)
    assert isinstance(value, dict)
    return value, envelope.binding


def _typed_signed(
    body: dict[str, object], *, domain: bytes, digest_field: str,
    binding: CanonicalTypedValueProfileBinding,
) -> bytes:
    return serialize_artifact(
        json.loads(_signed(body, domain=domain, digest_field=digest_field)), binding
    )


def _release_history(release: dict[str, object]) -> bytes:
    entry_body: dict[str, object] = {
        "entry_id": "entry-1", "sequence": 1, "predecessor_entry_digest": None,
        "release_id": release["release_id"], "release_digest": release["release_digest"],
        "release_epoch": release["epoch"], "release_sequence": release["sequence"],
        "prior_active_release_digest": None, "prior_release_terminal_state": None,
        "effective_at": release["issued_at"],
    }
    entry = {**entry_body, "entry_digest": sha256(b"memorii:sia-traceability-release-history-entry:v1\0" + canonical_document(entry_body)).hexdigest()}
    return _signed({"history_id": "history", "issuance_purpose": "semantic_ingestion_traceability_release_history", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "issuer_key_or_certificate_digest": "bootstrap-key", "entries": [entry]}, domain=b"memorii:sia-traceability-release-history:v1", digest_field="release_history_digest")


def _history_entry(release: dict[str, object], sequence: int, predecessor: dict[str, object] | None = None) -> dict[str, object]:
    body: dict[str, object] = {"entry_id": f"entry-{sequence}", "sequence": sequence, "predecessor_entry_digest": predecessor["entry_digest"] if predecessor else None, "release_id": release["release_id"], "release_digest": release["release_digest"], "release_epoch": release["epoch"], "release_sequence": release["sequence"], "prior_active_release_digest": predecessor["release_digest"] if predecessor else None, "prior_release_terminal_state": "superseded" if predecessor else None, "effective_at": release["issued_at"]}
    return {**body, "entry_digest": sha256(b"memorii:sia-traceability-release-history-entry:v1\0" + canonical_document(body)).hexdigest()}


def _history(entries: list[dict[str, object]], *, key: str = "bootstrap-key") -> bytes:
    return _signed({"history_id": "history", "issuance_purpose": "semantic_ingestion_traceability_release_history", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "issuer_key_or_certificate_digest": key, "entries": entries}, domain=b"memorii:sia-traceability-release-history:v1", digest_field="release_history_digest", key=key)


_STRUCTURAL_BYTES: bytes | None = None


def _structural_bytes(*, design: bytes, registry: object, registry_bytes: bytes) -> bytes:
    global _STRUCTURAL_BYTES
    if _STRUCTURAL_BYTES is None:
        _STRUCTURAL_BYTES = rebuild_structural_manifest_bytes(
            design_bytes=design, registry=registry, registry_bytes=registry_bytes
        )
    return _STRUCTURAL_BYTES


def _minimal_registered_design(registry_source: dict[str, object]) -> bytes:
    """Build the smallest design artifact closed over the registered grammar."""
    heading_defaults = registry_source["heading_defaults"]
    anchor_bindings = registry_source["anchor_bindings"]
    if not isinstance(heading_defaults, list) or not isinstance(anchor_bindings, list):
        raise AssertionError("acceptance registry structural authority is invalid")
    anchors = " ".join(
        f"[{item['anchor']}]" for item in anchor_bindings if isinstance(item, dict)
    )
    lines: list[str] = []
    for index, item in enumerate(heading_defaults):
        if not isinstance(item, dict) or not isinstance(item.get("heading_path"), str):
            raise AssertionError("acceptance registry heading authority is invalid")
        path = item["heading_path"]
        level = min(6, path.count(".") + 2)
        lines.append(f"{'#' * level} {path}. Acceptance fixture")
        if index == 0:
            lines.extend(("", anchors, ""))
    return ("\n".join(lines) + "\n").encode()


def _generation_package(*, generation_id: str, design: bytes, registry_bytes: bytes, registry: object, roots: dict[str, str], pointer: bytes, typed_members: dict[str, bytes] | None = None, sign: object = None, prior_pointer: bytes | None = None) -> tuple[bytes, dict[str, bytes]]:
    """Acceptance-owned finite package; it never imports the release verifier."""
    if typed_members is not None:
        authority = json.loads(
            (
                Path(__file__).parents[4]
                / "docs/design/semantic_ingestion/traceability_golden_vectors/ctv-binding-authority-v2.json"
            ).read_bytes()
        )
        built: dict[str, object] = {
                "authority": authority,
                "typed": typed_members,
                "roots": roots,
                "sign": sign if callable(sign) else _signature,
            }
        if prior_pointer is not None:
            built["prior_pointer"] = prior_pointer
        return build_current_generation_package(
            built=built,
            design_bytes=design,
            registry_bytes=registry_bytes,
        )
    binding = CanonicalTypedValueProfileBinding(
        "semantic_ingestion_typed_value", 2,
        "c425fa6823f42fdd0d83ff444699bfd4c2b5fc9468812ff2b60c158a04ad254f",
        "TraceabilityApprovalGenerationManifestBody.v1", 1,
        "288ad3d24ed76b79434985b8a2e1a8fc91d6bd631f2d174057ca54c7870da9c0",
    )
    structural = _structural_bytes(
        design=design, registry=registry, registry_bytes=registry_bytes
    )
    bodies = {
        "bootstrap_anchor": {}, "recovery_root": {}, "recovery_policy": {},
        "bootstrap_anchor_history": {}, "recovery_root_history": {},
        "recovery_policy_history": {}, "trust_lifecycle_root": {}, "trust_snapshot": {},
        "structural_manifest": {
            "structural_manifest_digest": roots["structural_manifest_digest"],
            "structural_manifest_bytes": structural,
        },
        "coverage_root": {
            "structural_manifest_digest": roots["structural_manifest_digest"],
            "approvals": [],
            "coverage_root_digest": roots["coverage_root_digest"],
        },
        "execution_root": {
            "structural_manifest_digest": roots["structural_manifest_digest"],
            "evidence_records": [],
            "execution_root_digest": roots["execution_root_digest"],
        },
        "golden_vector_manifest": {}, "release": {}, "release_history": {},
        "pointer_history": {},
    }
    member_bytes: dict[str, bytes] = {}
    members: list[dict[str, object]] = []
    for kind, raw in (("design_document", design), ("registry_source", registry_bytes)):
        digest = sha256((b"semantic-ingestion-traceability\0" if kind == "design_document" else b"memorii:sia-traceability-source:v1\0") + raw).hexdigest()
        coordinate = f"sia-traceability/v1/{kind}/{digest}"
        member_bytes[coordinate] = raw
        members.append({"artifact_kind": kind, "artifact_coordinate": coordinate, "artifact_digest": digest, "depends_on_coordinates": [] if kind == "design_document" else [members[-1]["artifact_coordinate"]], "schema_id": f"memorii.raw.{kind}.v1", "schema_version": 1, "binding_digest": "raw-sha256-bytes-v1"})
    schemas = {
        "bootstrap_anchor": "TraceabilityBootstrapTrustAnchorBody.v1",
        "recovery_root": "TraceabilityRecoveryTrustRootBody.v1",
        "recovery_policy": "TraceabilityRecoveryTrustPolicyBody.v1",
        "bootstrap_anchor_history": "TraceabilityBootstrapAnchorHistoryBody.v1",
        "recovery_root_history": "TraceabilityRecoveryRootHistoryBody.v1",
        "recovery_policy_history": "TraceabilityRecoveryPolicyHistoryBody.v1",
        "trust_lifecycle_root": "TraceabilityTrustLifecycleRootBody.v1",
        "trust_snapshot": "TraceabilityReleaseTrustSnapshotBody.v1",
        "structural_manifest": "NormativeTraceabilityStructuralManifestBody.v1",
        "coverage_root": "TraceabilityCoverageEvidenceRootBody.v1",
        "execution_root": "TraceabilityExecutionEvidenceRootBody.v1",
        "release": "SemanticIngestionTraceabilityReleaseBody.v1",
        "release_history": "TraceabilityReleaseHistoryBody.v1",
        "pointer_history": "TraceabilityActiveReleasePointerHistoryBody.v1",
        "golden_vector_manifest": "TraceabilityApprovalGoldenVectorManifestBody.v1",
    }
    authority = json.loads((Path(__file__).parents[4] / "docs/design/semantic_ingestion/traceability_golden_vectors/ctv-binding-authority-v2.json").read_bytes())
    bindings = {item["coordinate"]: item["binding_digest"] for item in authority["schemas"]}
    dependencies = {
        "bootstrap_anchor": (),
        "recovery_root": (),
        "recovery_policy": ("bootstrap_anchor", "recovery_root"),
        "bootstrap_anchor_history": ("bootstrap_anchor",),
        "recovery_root_history": ("recovery_root",),
        "recovery_policy_history": ("recovery_policy",),
        "trust_lifecycle_root": (
            "bootstrap_anchor_history", "recovery_root_history",
            "recovery_policy_history",
        ),
        "trust_snapshot": (
            "trust_lifecycle_root", "bootstrap_anchor_history",
            "recovery_root_history", "recovery_policy_history",
        ),
        "structural_manifest": ("design_document", "registry_source"),
        "coverage_root": ("structural_manifest",),
        "execution_root": ("structural_manifest",),
        "golden_vector_manifest": (),
        "release": (
            "bootstrap_anchor", "bootstrap_anchor_history", "recovery_root",
            "recovery_root_history", "recovery_policy", "recovery_policy_history",
            "trust_lifecycle_root", "trust_snapshot", "structural_manifest",
            "coverage_root", "execution_root", "golden_vector_manifest",
        ),
        "release_history": ("release",),
        "pointer_history": (),
    }
    coordinates_by_kind = {
        str(member["artifact_kind"]): str(member["artifact_coordinate"])
        for member in members
    }
    for kind, body in bodies.items():
        supplied = (typed_members or {}).get(kind)
        if supplied is not None:
            envelope = decode_artifact(supplied)
            raw = supplied
            digest = envelope.artifact_digest
            schema_id = envelope.binding.schema_id
            member_binding = envelope.binding
            coordinate = f"sia-traceability/v1/{kind}/{digest}"
            member_bytes[coordinate] = raw
            members.append({"artifact_kind": kind, "artifact_coordinate": coordinate, "artifact_digest": digest, "depends_on_coordinates": sorted(coordinates_by_kind[item] for item in dependencies[kind]), "schema_id": schema_id, "schema_version": 1, "binding_digest": member_binding.binding_digest})
            coordinates_by_kind[kind] = coordinate
            continue
        schema_id = schemas[kind]
        member_binding = CanonicalTypedValueProfileBinding(
            binding.profile_id, binding.profile_version, binding.profile_digest,
            schema_id, 1, bindings[schema_id],
        )
        raw = serialize_artifact(body, member_binding)
        digest = encode_artifact(body, member_binding).artifact_digest
        coordinate = f"sia-traceability/v1/{kind}/{digest}"
        member_bytes[coordinate] = raw
        members.append({"artifact_kind": kind, "artifact_coordinate": coordinate, "artifact_digest": digest, "depends_on_coordinates": sorted(coordinates_by_kind[item] for item in dependencies[kind]), "schema_id": schema_id, "schema_version": 1, "binding_digest": member_binding.binding_digest})
        coordinates_by_kind[kind] = coordinate
    # Generation assembly runs before `_approval_inputs` wraps the pointer in
    # its registered CTV envelope; reject non-canonical raw bodies here.
    pointer_value = json.loads(pointer)
    if not isinstance(pointer_value, dict) or canonical_document(pointer_value) != pointer:
        raise AssertionError("generation pointer must be canonical raw JSON")
    pointer_intent = {
        key: value for key, value in pointer_value.items()
        if key not in {"active_pointer_digest", "signature", "generation_id", "generation_manifest_digest"}
    }
    body = {"generation_id": generation_id, "issuance_purpose": "semantic_ingestion_traceability_approval_generation", "canonical_profile_binding": binding.as_value(), "design_document_digest": roots["design_document_digest"], "registry_source_identity": roots["registry_source_identity"], "members": members, "active_pointer_intent": pointer_intent, "signer_coordinate": {}, "signature": "fixture"}
    body["generation_manifest_digest"] = sha256(b"memorii:sia-traceability-approval-generation:v1\0" + encode_typed_value({key: value for key, value in body.items() if key not in {"signer_coordinate", "signature", "generation_manifest_digest"}})).hexdigest()
    return serialize_artifact(body, binding), member_bytes


def _generation_package_g1(**kwargs: object) -> tuple[bytes, dict[str, bytes]]:
    return _generation_package(generation_id="G1", **kwargs)


def _generation_package_g2(**kwargs: object) -> tuple[bytes, dict[str, bytes]]:
    return _generation_package(generation_id="G2", **kwargs)


def _generation_package_g3(**kwargs: object) -> tuple[bytes, dict[str, bytes]]:
    return _generation_package(generation_id="G3", **kwargs)


def _approval_inputs(
    group_id: str,
    *,
    threshold_recovery: bool = False,
    activate_recovery_roots: bool = True,
    bootstrap_expires_at: str | None = None,
    release_issued_at: str | None = None,
) -> dict[str, object]:
    # Reuse the closed current-CTV chain fixture so registered execution tests
    # exercise authorization semantics instead of the retired flat transport.
    from memorii.tools.semantic_ingestion_traceability_registry import TraceabilityRegistry
    from tests.fixtures.semantic_ingestion.current_release_chain import (
        bind_chain_to_generation,
    )
    from tests.unit.tools.test_traceability_release_provenance import _current_chain

    registry_path = _registry_path()
    registry_bytes = registry_path.read_bytes()
    registry_source = load_registry(registry_path)
    design_bytes = _minimal_registered_design(registry_source.source)
    structural_bytes = _structural_bytes(
        design=design_bytes, registry=registry_source, registry_bytes=registry_bytes
    )
    ledger = load_checked_in_frozen_structural_manifest_ledger()
    structural_digest = sha256(
        ledger.domain("structural_body")
        + len(structural_bytes).to_bytes(8, "big")
        + structural_bytes
    ).hexdigest()
    structural_value = decode_typed_value(structural_bytes)
    if not isinstance(structural_value, dict):
        raise AssertionError("current structural body is invalid")
    external_roots = {
        "design_document_digest": sha256(
            b"semantic-ingestion-traceability\0" + design_bytes
        ).hexdigest(),
        "structural_manifest_digest": structural_digest,
        "coverage_root_digest": sha256(
            b"memorii:sia-traceability-coverage-root:v1\0"
            + encode_typed_value({
                "structural_manifest_digest": structural_digest,
                "approvals": [],
            })
        ).hexdigest(),
        "execution_root_digest": sha256(
            b"memorii:sia-traceability-execution-root:v1\0"
            + encode_typed_value({
                "structural_manifest_digest": structural_digest,
                "evidence_records": [],
            })
        ).hexdigest(),
        "report_schema_registry_digest": structural_value[
            "report_schema_registry_digest"
        ],
        "runner_environment_profile_registry_digest": structural_value[
            "runner_environment_profile_registry_digest"
        ],
        "trust_snapshot_digest": "8" * 64,
    }
    authority_source = json.loads(
        (
            Path(__file__).parents[4]
            / "docs/design/semantic_ingestion/traceability_golden_vectors/ctv-binding-authority-v2.json"
        ).read_bytes()
    )
    authority_bindings = {
        item["coordinate"]: item["binding_digest"]
        for item in authority_source["schemas"]
    }

    def generation_binding(schema_id: str) -> CanonicalTypedValueProfileBinding:
        return CanonicalTypedValueProfileBinding(
            "semantic_ingestion_typed_value", 2,
            "9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f",
            schema_id, 1, authority_bindings[schema_id],
        )

    golden_body = {
        "manifest_id": "acceptance-golden",
        "manifest_version": 1,
        "source_path": "tests/acceptance/semantic_ingestion/test_sia_requirements.py",
        "owner": "acceptance_fixture",
        "authority_use": "verification_fixture_not_runtime_authority",
        "canonical_profile_binding": generation_binding(
            "TraceabilityApprovalGoldenVectorManifestBody.v1"
        ).as_value(),
        "design_document_digest": external_roots["design_document_digest"],
        "registry_source_identity": registry_source.source_identity,
        "fixtures": [],
        "vectors": [],
    }
    golden_digest = sha256(
        b"memorii:sia-traceability-approval-golden-vectors:v1\0"
        + encode_typed_value(golden_body)
    ).hexdigest()
    golden = {
        **golden_body,
        "golden_vector_manifest_digest": golden_digest,
    }
    provisional = _current_chain(
        external_roots,
        golden_digest,
        threshold_recovery=threshold_recovery,
        activate_recovery_roots=activate_recovery_roots,
        bootstrap_expires_at=bootstrap_expires_at,
        release_issued_at=release_issued_at,
    )
    provisional_lifecycle, _ = _typed_body(provisional["lifecycle"])  # type: ignore[arg-type]
    provisional_release, _ = _typed_body(provisional["release"])  # type: ignore[arg-type]
    terminal = provisional_lifecycle["records"][-1]
    provisional_signer = provisional_release["signer_coordinate"]
    assert isinstance(provisional_signer, dict)
    snapshot_issuer = {
        "issuer_id": provisional_signer["issuer_id"],
        "signature_profile_id": provisional_signer["signature_profile_id"],
        "key_or_certificate_digest": provisional_signer[
            "key_or_certificate_digest"
        ],
        "trust_lifecycle_root_digest": provisional_lifecycle["lifecycle_root_digest"],
        "lifecycle_record_digest": terminal["record_digest"],
    }
    snapshot_body = {
        "snapshot_id": "acceptance-snapshot",
        "issuance_purpose": "semantic_ingestion_traceability_release_trust_snapshot",
        "canonical_profile_binding": generation_binding(
            "TraceabilityReleaseTrustSnapshotBody.v1"
        ).as_value(),
        "release_id": provisional_release["release_id"],
        "release_epoch": provisional_release["epoch"],
        "release_sequence": provisional_release["sequence"],
        "bootstrap_anchor_digest": provisional_release["bootstrap_anchor_digest"],
        "recovery_policy_digest": provisional_release["recovery_trust_policy_digest"],
        "trust_lifecycle_root_digest": provisional_lifecycle["lifecycle_root_digest"],
        "lifecycle_recorded_time_cutoff": terminal["recorded_at"],
        "qualified_issuers": [snapshot_issuer],
        "created_at": provisional_release["issued_at"],
    }
    snapshot_digest = sha256(
        b"memorii:sia-traceability-release-trust-snapshot:v1\0"
        + encode_typed_value(snapshot_body)
    ).hexdigest()
    snapshot = {**snapshot_body, "trust_snapshot_digest": snapshot_digest}
    external_roots["trust_snapshot_digest"] = snapshot_digest
    chain = _current_chain(
        external_roots,
        golden_digest,
        threshold_recovery=threshold_recovery,
        activate_recovery_roots=activate_recovery_roots,
        bootstrap_expires_at=bootstrap_expires_at,
        release_issued_at=release_issued_at,
    )
    chain = bind_chain_to_generation(
        chain,
        roots={
            **external_roots,
            "golden_vector_manifest_digest": golden_digest,
        },
        binding_for_schema=generation_binding,
    )
    registry = chain["registry"]
    if not isinstance(registry, TraceabilityRegistry):
        raise AssertionError("current approval fixture registry is invalid")
    group = next(
        item
        for item in registry.source["test_evidence_groups"]
        if item["group_id"] == group_id
    )
    roots = chain["release_roots"]
    now = chain["now"]
    material = chain["material"]
    release_bytes = chain["release"]
    if (
        not isinstance(roots, dict)
        or not isinstance(now, datetime)
        or not isinstance(material, VerifierHeldTrustMaterial)
        or not isinstance(release_bytes, bytes)
    ):
        raise AssertionError("current approval fixture is incomplete")
    profile = registry.source["runner_environment_profiles"][0]
    environment = canonical_document({
        "interpreter": profile["interpreter_policy"],
        "runner": profile["runner_policy"],
        "plugins": profile["plugin_policy"],
        "configuration": profile["configuration_policy"],
        "dependencies": profile["dependency_policy"],
        "import_paths": profile["import_path_policy"],
        "startup": profile["startup_customization_policy"],
        "environment": profile["environment_policy"],
        "locale_timezone": profile["locale_timezone_policy"],
        "network": profile["network_policy"],
    })
    passed = b"passed"
    passed_digest = artifact_digest(passed)
    environment_digest = artifact_digest(environment)
    selected = group["selected_tests"]
    report = {
        "schema_id": group["report_schema_id"],
        "schema_version": group["report_schema_version"],
        "command_id": group["command"]["command_id"],
        "argv": group["command"]["argv"],
        "working_directory": group["command"]["working_directory"],
        "selected_test_ids": [item["test_id"] for item in selected],
        "collected_test_ids": [item["test_id"] for item in selected],
        "tests": [{
            "test_id": item["test_id"],
            "node_id": item["pytest_node_id"],
            "outcome": "passed",
            "result_artifact_digest": passed_digest,
        } for item in selected],
        "exit_code": 0,
        "runner_id": "cpython-pytest",
        "runner_version": "8.0",
        "loaded_report_schema_digest": group["expected_report_schema_digest"],
        "loaded_runner_environment_profile_digest": group["expected_runner_environment_profile_digest"],
        "runner_environment_observation_digest": observation_digest(environment),
        "design_document_digest": roots["design_document_digest"],
        "registry_source_identity": registry.source_identity,
        "structural_manifest_digest": roots["structural_manifest_digest"],
        "implementation_revision": "acceptance-revision",
        "implementation_tree_digest": "a" * 64,
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:00:01Z",
        "stdout_artifact_digest": None,
        "stderr_artifact_digest": None,
        "runner_environment_observation_artifact_digest": environment_digest,
    }
    release, _ = _typed_body(release_bytes)
    pointer_bytes = chain["pointer"]
    if not isinstance(pointer_bytes, bytes):
        raise AssertionError("current pointer fixture is invalid")
    pointer, pointer_binding = _typed_body(pointer_bytes)
    release_roots = chain["release_roots"]
    if not isinstance(release_roots, dict):
        raise AssertionError("current release roots are invalid")
    bootstrap_body, _ = _typed_body(chain["bootstrap"])  # type: ignore[arg-type]
    recovery_body, _ = _typed_body(chain["recovery"])  # type: ignore[arg-type]
    policy_body, _ = _typed_body(chain["policy"])  # type: ignore[arg-type]
    lifecycle_body, _ = _typed_body(chain["lifecycle"])  # type: ignore[arg-type]
    history_body, _ = _typed_body(chain["history"])  # type: ignore[arg-type]

    def history_member(
        *, kind: str, collection: str, values: list[dict[str, object]],
        schema_id: str, domain: bytes,
    ) -> bytes:
        body = {
            "history_id": f"acceptance-{kind}",
            "canonical_profile_binding": generation_binding(schema_id).as_value(),
            collection: values,
        }
        body["history_digest"] = sha256(
            domain + encode_typed_value(body)
        ).hexdigest()
        return serialize_artifact(body, generation_binding(schema_id))

    structural_binding = generation_binding(
        "NormativeTraceabilityStructuralManifestBody.v1"
    )
    marker = b'["structural_mapping_rule_registry_digest",'
    marker_offset = structural_bytes.rfind(marker)
    if marker_offset < 0:
        raise AssertionError("current structural body lacks its terminal insertion point")
    structural_member_body = (
        structural_bytes[:marker_offset]
        + b'["structural_manifest_digest","'
        + structural_digest.encode("ascii")
        + b'"],'
        + structural_bytes[marker_offset:]
    )
    structural_member = encode_typed_value(
        {
            "binding": structural_binding.as_value(),
            "canonical_value_bytes": structural_member_body,
            "canonical_value_digest": sha256(structural_member_body).hexdigest(),
            "artifact_digest": sha256(
                artifact_preimage(structural_binding, structural_member_body)
            ).hexdigest(),
        }
    )
    coverage_member = {
        "structural_manifest_digest": structural_digest,
        "approvals": [],
        "coverage_root_digest": external_roots["coverage_root_digest"],
    }
    execution_member = {
        "structural_manifest_digest": structural_digest,
        "evidence_records": [],
        "execution_root_digest": external_roots["execution_root_digest"],
    }
    pointer_history_body = {
        "history_id": "acceptance-pointer-history",
        "issuance_purpose": "semantic_ingestion_traceability_pointer_history",
        "canonical_profile_binding": generation_binding(
            "TraceabilityActiveReleasePointerHistoryBody.v1"
        ).as_value(),
        "pointers": [],
        "signer_coordinate": pointer["signer_coordinate"],
        "signature": "00",
    }
    pointer_history_body["pointer_history_digest"] = sha256(
        b"memorii:sia-traceability-pointer-history:v1\0"
        + encode_typed_value({
            key: value
            for key, value in pointer_history_body.items()
            if key not in {"signature", "pointer_history_digest"}
        })
    ).hexdigest()
    typed_members = {
        "bootstrap_anchor": chain["bootstrap"],
        "recovery_root": chain["recovery"],
        "recovery_policy": chain["policy"],
        "bootstrap_anchor_history": history_member(
            kind="bootstrap-history",
            collection="anchors",
            values=[
                bootstrap_body,
                *[
                    _typed_body(raw)[0]
                    for raw in material.provisioned_successor_root_bytes
                ],
            ],
            schema_id="TraceabilityBootstrapAnchorHistoryBody.v1",
            domain=b"memorii:sia-traceability-bootstrap-anchor-history:v1\0",
        ),
        "recovery_root_history": history_member(
            kind="recovery-history", collection="recovery_roots",
            values=[
                _typed_body(raw)[0]
                for raw in chain.get("recoveries", (chain["recovery"],))
                if isinstance(raw, bytes)
            ],
            schema_id="TraceabilityRecoveryRootHistoryBody.v1",
            domain=b"memorii:sia-traceability-recovery-root-history:v1\0",
        ),
        "recovery_policy_history": history_member(
            kind="policy-history", collection="policies", values=[policy_body],
            schema_id="TraceabilityRecoveryPolicyHistoryBody.v1",
            domain=b"memorii:sia-traceability-recovery-policy-history:v1\0",
        ),
        "trust_lifecycle_root": chain["lifecycle"],
        "trust_snapshot": serialize_artifact(
            snapshot, generation_binding("TraceabilityReleaseTrustSnapshotBody.v1")
        ),
        "structural_manifest": structural_member,
        "coverage_root": serialize_artifact(
            coverage_member,
            generation_binding("TraceabilityCoverageEvidenceRootBody.v1"),
        ),
        "execution_root": serialize_artifact(
            execution_member,
            generation_binding("TraceabilityExecutionEvidenceRootBody.v1"),
        ),
        "golden_vector_manifest": serialize_artifact(
            golden,
            generation_binding("TraceabilityApprovalGoldenVectorManifestBody.v1"),
        ),
        "release": release_bytes,
        "release_history": serialize_artifact(
            history_body,
            decode_artifact(chain["history"]).binding,  # type: ignore[arg-type]
        ),
        "pointer_history": serialize_artifact(
            pointer_history_body,
            generation_binding("TraceabilityActiveReleasePointerHistoryBody.v1"),
        ),
    }
    generation_artifacts = chain["generation_artifacts"]
    if not isinstance(generation_artifacts, dict):
        raise AssertionError("current generation artifacts are invalid")
    typed_members.update(generation_artifacts)
    if not all(isinstance(value, bytes) for value in typed_members.values()):
        raise AssertionError("current generation members are invalid")
    manifest, member_bytes = _generation_package(
        generation_id="generation-1",
        design=design_bytes,
        registry_bytes=registry_bytes,
        registry=registry,
        roots=release_roots,
        pointer=canonical_document(pointer),
        typed_members=typed_members,  # type: ignore[arg-type]
        sign=chain["sign"],
    )
    manifest_body, manifest_binding = _typed_body(manifest)
    lifecycle_body, _ = _typed_body(chain["lifecycle"])  # type: ignore[arg-type]
    release_signer = release["signer_coordinate"]
    assert isinstance(release_signer, dict)
    generation_signer = {
        "signature_purpose": "semantic_ingestion_traceability_approval_generation",
        "issuer_id": release_signer["issuer_id"],
        "key_or_certificate_digest": release_signer[
            "key_or_certificate_digest"
        ],
        "signature_profile_id": release_signer["signature_profile_id"],
        "trust_lifecycle_root_digest": lifecycle_body["lifecycle_root_digest"],
        "lifecycle_record_digest": lifecycle_body["records"][-1]["record_digest"],
        "eligible_not_before": release_signer["eligible_not_before"],
        "eligible_not_after": release_signer["eligible_not_after"],
    }
    generation_preimage = encode_typed_value({
        "issuance_purpose": "semantic_ingestion_traceability_approval_generation",
        "body_binding": manifest_binding.as_value(),
        "generation_manifest_digest": manifest_body["generation_manifest_digest"],
        "signer_coordinate": generation_signer,
    })
    generation_signature = sha256(
        str(generation_signer["signature_profile_id"]).encode()
        + b"\0"
        + str(generation_signer["key_or_certificate_digest"]).encode()
        + b"\0"
        + generation_preimage
    ).hexdigest()
    manifest_body.update({
        "signer_coordinate": generation_signer,
        "signature": generation_signature,
    })
    manifest = serialize_artifact(manifest_body, manifest_binding)
    pointer_intent = manifest_body["active_pointer_intent"]
    if not isinstance(pointer_intent, dict):
        raise AssertionError("current generation pointer intent is invalid")
    pointer_body = dict(pointer_intent)
    pointer_body["generation_id"] = manifest_body["generation_id"]
    pointer_body["generation_manifest_digest"] = manifest_body[
        "generation_manifest_digest"
    ]
    pointer_digest = sha256(
        b"memorii:sia-traceability-active-release-pointer:v1\0"
        + encode_typed_value(pointer_body)
    ).hexdigest()
    pointer_signer = pointer_body["signer_coordinate"]
    assert isinstance(pointer_signer, dict)
    pointer_preimage = encode_typed_value({
        "issuance_purpose": pointer_body["issuance_purpose"],
        "body_binding": pointer_body["canonical_profile_binding"],
        "active_pointer_digest": pointer_digest,
        "signer_coordinate": pointer_signer,
    })
    pointer_signature = sha256(
        str(pointer_signer["signature_profile_id"]).encode()
        + b"\0"
        + str(pointer_signer["key_or_certificate_digest"]).encode()
        + b"\0"
        + pointer_preimage
    ).digest()
    pointer_bytes = serialize_artifact(
        {
            **pointer_body,
            "active_pointer_digest": pointer_digest,
            "signature": pointer_signature.hex(),
        },
        pointer_binding,
    )
    expected_fields = (
        "design_document_digest", "structural_manifest_digest",
        "coverage_root_digest", "execution_root_digest",
        "report_schema_registry_digest",
        "runner_environment_profile_registry_digest", "trust_snapshot_digest",
    )
    return {
        "registry_bytes": registry_bytes,
        "registry": registry,
        "group_id": group_id,
        "report_bytes": canonical_document(report),
        "artifacts": {passed_digest: passed, environment_digest: environment},
        "implementation_revision": "acceptance-revision",
        "implementation_tree_digest": "a" * 64,
        "environment_observation_bytes": environment,
        "bootstrap_artifact": chain["bootstrap"],
        "recovery_artifact": chain["recovery"],
        "recovery_artifacts": tuple(chain.get("recoveries", ()))[1:],
        "lifecycle_artifact": chain["lifecycle"],
        "release_artifact": release_bytes,
        "active_pointer_artifact": pointer_bytes,
        "release_history_artifact": chain["history"],
        "historical_release_artifacts": (),
        "generation_manifest_bytes": manifest,
        "generation_member_bytes": member_bytes,
        "design_document_bytes": design_bytes,
        "watermark_provisioning": (
            release["epoch"], release["sequence"], release["release_digest"]
        ),
        "expected_release_roots": {key: roots[key] for key in expected_fields},
        "verifier_material": material,
        "independent_generation_verifier": ExplicitTestIndependentGenerationVerifier(
            IndependentGenerationVerificationResult(
                "memorii-sia-clean-room-b-v1",
                "b655f474e4918d64447251e40b9a3af53daca0efd2e2cb6baa76890243bae5ed",
                structural_bytes,
                structural_member,
                structural_verification_spool(
                    structural_bytes, structural_member
                ),
            )
        ),
        "now": now,
        "_chain": chain,
        "_typed_members": typed_members,
        "_generation_roots": roots,
        "_authority_source": authority_source,
    }


def _legacy_threshold_recovery_inputs(group_id: str) -> dict[str, object]:
    inputs = _approval_inputs(group_id)
    bootstrap_bytes = inputs["bootstrap_artifact"]
    first_recovery_bytes = inputs["recovery_artifact"]
    lifecycle_bytes = inputs["lifecycle_artifact"]
    release_bytes = inputs["release_artifact"]
    pointer_bytes = inputs["active_pointer_artifact"]
    assert all(
        isinstance(value, bytes)
        for value in (
            bootstrap_bytes,
            first_recovery_bytes,
            lifecycle_bytes,
            release_bytes,
            pointer_bytes,
        )
    )
    assert isinstance(bootstrap_bytes, bytes)
    assert isinstance(first_recovery_bytes, bytes)
    assert isinstance(lifecycle_bytes, bytes)
    assert isinstance(release_bytes, bytes)
    assert isinstance(pointer_bytes, bytes)
    bootstrap = json.loads(bootstrap_bytes)
    first_recovery = json.loads(first_recovery_bytes)
    second_recovery_bytes = _signed(
        {
            "recovery_root_id": "recovery-two",
            "issuance_purpose": "semantic_ingestion_traceability_recovery_root",
            "canonical_profile_id": "memorii-sia-canonical-json-v1",
            "signature_profile_id": "deterministic-v1",
            "public_key_or_root_certificate_digest": "recovery-two-key",
            "target_authority_id": "authority",
        },
        domain=b"memorii:sia-traceability-recovery-root:v1",
        digest_field="recovery_root_digest",
        key="recovery-two-key",
    )
    second_recovery = json.loads(second_recovery_bytes)
    recovered_root = _signed(
        {
            "anchor_id": "bootstrap-recovered",
            "issuance_purpose": "semantic_ingestion_traceability_release_root",
            "canonical_profile_id": "memorii-sia-canonical-json-v1",
            "signature_profile_id": "deterministic-v1",
            "public_key_or_root_certificate_digest": "recovered-key",
            "target_authority_id": "authority",
            "effective_at": "2026-01-01T00:00:03Z",
        },
        domain=b"memorii:sia-traceability-bootstrap-anchor:v1",
        digest_field="anchor_digest",
        key="recovered-key",
    )
    recovered = json.loads(recovered_root)
    final_root = _signed(
        {
            "anchor_id": "bootstrap-final",
            "issuance_purpose": "semantic_ingestion_traceability_release_root",
            "canonical_profile_id": "memorii-sia-canonical-json-v1",
            "signature_profile_id": "deterministic-v1",
            "public_key_or_root_certificate_digest": "final-key",
            "target_authority_id": "authority",
            "effective_at": "2026-01-01T00:00:04Z",
        },
        domain=b"memorii:sia-traceability-bootstrap-anchor:v1",
        digest_field="anchor_digest",
        key="final-key",
    )
    final = json.loads(final_root)
    policy = _signed(
        {
            "issuance_purpose": "semantic_ingestion_traceability_recovery_policy",
            "canonical_profile_id": "memorii-sia-canonical-json-v1",
            "signature_profile_id": "deterministic-v1",
            "policy_signer_key_or_certificate_digest": "bootstrap-key",
            "active_bootstrap_anchor_digest": bootstrap["anchor_digest"],
            "eligible_recovery_root_digests": [
                first_recovery["recovery_root_digest"],
                second_recovery["recovery_root_digest"],
            ],
            "threshold": 2,
        },
        domain=b"memorii:sia-traceability-recovery-policy:v1",
        digest_field="recovery_policy_digest",
    )

    def lifecycle_record(
        body: dict[str, object], signing_keys: tuple[str, ...]
    ) -> dict[str, object]:
        digest = sha256(
            b"memorii:sia-traceability-lifecycle-record:v1\0"
            + canonical_document(body)
        ).hexdigest()
        return {
            **body,
            "record_digest": digest,
            "signatures": [
                _signature("deterministic-v1", key, digest.encode("ascii")).hex()
                for key in signing_keys
            ],
        }

    genesis = json.loads(lifecycle_bytes)["records"][0]
    first_activation = lifecycle_record(
        {
            "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
            "sequence": 2,
            "predecessor_record_digest": genesis["record_digest"],
            "effective_at": "2026-01-01T00:00:01Z",
            "recorded_at": "2026-01-01T00:00:01.500000Z",
            "action": "activate",
            "target_id": "recovery",
            "target_digest": first_recovery["recovery_root_digest"],
            "replacement_target_id": None,
            "replacement_target_digest": None,
            "signer_bindings": [
                {
                    "signer_id": "bootstrap",
                    "signature_profile_id": "deterministic-v1",
                    "key_digest": "bootstrap-key",
                }
            ],
        },
        ("bootstrap-key",),
    )
    second_activation = lifecycle_record(
        {
            **{
                key: value
                for key, value in first_activation.items()
                if key not in {"record_digest", "signatures"}
            },
            "sequence": 3,
            "predecessor_record_digest": first_activation["record_digest"],
            "effective_at": "2026-01-01T00:00:02Z",
            "recorded_at": "2026-01-01T00:00:02.500000Z",
            "target_id": "recovery-two",
            "target_digest": second_recovery["recovery_root_digest"],
        },
        ("bootstrap-key",),
    )
    recovery_record = lifecycle_record(
        {
            "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
            "sequence": 4,
            "predecessor_record_digest": second_activation["record_digest"],
            "effective_at": "2026-01-01T00:00:03Z",
            "recorded_at": "2026-01-01T00:00:03.500000Z",
            "action": "recover",
            "target_id": "bootstrap",
            "target_digest": bootstrap["anchor_digest"],
            "replacement_target_id": "bootstrap-recovered",
            "replacement_target_digest": recovered["anchor_digest"],
            "replacement_signature_profile_id": "deterministic-v1",
            "replacement_key_digest": "recovered-key",
            "signer_bindings": [
                {
                    "signer_id": "recovery-one",
                    "signature_profile_id": "deterministic-v1",
                    "key_digest": "recovery-key",
                    "recovery_root_digest": first_recovery["recovery_root_digest"],
                },
                {
                    "signer_id": "recovery-two",
                    "signature_profile_id": "deterministic-v1",
                    "key_digest": "recovery-two-key",
                    "recovery_root_digest": second_recovery["recovery_root_digest"],
                },
            ],
        },
        ("recovery-key", "recovery-two-key"),
    )
    rotation_record = lifecycle_record(
        {
            "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
            "sequence": 5,
            "predecessor_record_digest": recovery_record["record_digest"],
            "effective_at": "2026-01-01T00:00:04Z",
            "recorded_at": "2026-01-01T00:00:04.500000Z",
            "action": "rotate",
            "target_id": "bootstrap-recovered",
            "target_digest": recovered["anchor_digest"],
            "replacement_target_id": "bootstrap-final",
            "replacement_target_digest": final["anchor_digest"],
            "replacement_signature_profile_id": "deterministic-v1",
            "replacement_key_digest": "final-key",
            "signer_bindings": [
                {
                    "signer_id": "recovered",
                    "signature_profile_id": "deterministic-v1",
                    "key_digest": "recovered-key",
                }
            ],
        },
        ("recovered-key",),
    )
    lifecycle_body = {
        "authority_id": "authority",
        "records": [
            genesis,
            first_activation,
            second_activation,
            recovery_record,
            rotation_record,
        ],
    }
    lifecycle_digest = sha256(
        b"memorii:sia-traceability-trust-lifecycle-root:v1\0"
        + canonical_document(lifecycle_body)
    ).hexdigest()
    lifecycle = canonical_document(
        {
            **lifecycle_body,
            "lifecycle_root_digest": lifecycle_digest,
            "signature": _signature(
                "deterministic-v1", "final-key", lifecycle_digest.encode("ascii")
            ).hex(),
        }
    )
    release, release_binding = _typed_body(release_bytes)
    release_body = {
        key: value
        for key, value in release.items()
        if key not in {"release_digest", "signature"}
    }
    final_release_bytes = _signed(
        {
            **release_body,
            "issuer_key_or_certificate_digest": "final-key",
            "issued_at": "2026-01-01T00:00:05Z",
        },
        domain=b"memorii:sia-traceability-release:v1",
        digest_field="release_digest",
        key="final-key",
    )
    final_release = json.loads(final_release_bytes)
    pointer = json.loads(pointer_bytes)
    pointer_body = {
        key: value
        for key, value in pointer.items()
        if key not in {"active_pointer_digest", "signature"}
    }
    final_pointer = _signed(
        {
            **pointer_body,
            "release_digest": final_release["release_digest"],
            "issuer_key_or_certificate_digest": "final-key",
        },
        domain=b"memorii:sia-traceability-active-release-pointer:v1",
        digest_field="active_pointer_digest",
        key="final-key",
    )
    inputs.update(
        {
            "recovery_artifacts": (second_recovery_bytes,),
            "lifecycle_artifact": lifecycle,
            "release_artifact": final_release_bytes,
            "active_pointer_artifact": final_pointer,
            "release_history_artifact": _history(
                [_history_entry(final_release, 1)], key="final-key"
            ),
            "watermark_provisioning": (1, 1, final_release["release_digest"]),
            "verifier_material": VerifierHeldTrustMaterial(
                bootstrap_bytes,
                (first_recovery_bytes, second_recovery_bytes),
                _verifier,
                policy,
                (recovered_root, final_root),
            ),
        }
    )
    return inputs


def _threshold_recovery_inputs(group_id: str) -> dict[str, object]:
    return _approval_inputs(group_id, threshold_recovery=True)


def _successor_inputs(group_id: str) -> dict[str, object]:
    inputs = _approval_inputs(group_id)
    from tests.fixtures.semantic_ingestion.current_release_chain import (
        bind_chain_to_generation,
        current_chain_successor,
    )

    chain = inputs["_chain"]
    typed_members = inputs["_typed_members"]
    if not isinstance(chain, dict) or not isinstance(typed_members, dict):
        raise AssertionError("current successor fixture inputs are invalid")
    prior_pointer = inputs["active_pointer_artifact"]
    prior_release = inputs["release_artifact"]
    if not isinstance(prior_pointer, bytes) or not isinstance(prior_release, bytes):
        raise AssertionError("current predecessor fixture is invalid")
    authority_source = inputs["_authority_source"]
    roots = inputs["_generation_roots"]
    if not isinstance(authority_source, dict) or not isinstance(roots, dict):
        raise AssertionError("current successor authority is invalid")
    profile = authority_source["profile"]
    schemas = authority_source["schemas"]
    if not isinstance(profile, dict) or not isinstance(schemas, list):
        raise AssertionError("current successor binding authority is invalid")

    def successor_binding(schema_id: str) -> CanonicalTypedValueProfileBinding:
        schema = next(
            item
            for item in schemas
            if isinstance(item, dict) and item.get("coordinate") == schema_id
        )
        return CanonicalTypedValueProfileBinding(
            str(profile["id"]), int(profile["version"]), str(profile["digest"]),
            schema_id, 1, str(schema["binding_digest"]),
        )

    successor_chain = bind_chain_to_generation(
        current_chain_successor(chain),
        roots=roots,
        binding_for_schema=successor_binding,
    )
    successor_release, _ = _typed_body(successor_chain["release"])  # type: ignore[arg-type]
    expected_roots = inputs["expected_release_roots"]
    if not isinstance(expected_roots, dict):
        raise AssertionError("current successor expected roots are invalid")
    inputs["expected_release_roots"] = {
        name: successor_release[name] for name in expected_roots
    }
    successor_typed = dict(typed_members)
    successor_generation_artifacts = successor_chain["generation_artifacts"]
    if not isinstance(successor_generation_artifacts, dict):
        raise AssertionError("current successor generation artifacts are invalid")
    successor_typed.update(successor_generation_artifacts)
    successor_typed["release"] = successor_chain["release"]
    successor_typed["release_history"] = successor_chain["history"]
    registry_bytes = inputs["registry_bytes"]
    design_bytes = inputs["design_document_bytes"]
    assert isinstance(registry_bytes, bytes) and isinstance(design_bytes, bytes)
    manifest, member_bytes = _generation_package_g2(
        design=design_bytes, registry_bytes=registry_bytes,
        registry=load_registry(_registry_path()), roots=roots,
        pointer=successor_chain["pointer"], typed_members=successor_typed,
        sign=successor_chain["sign"], prior_pointer=prior_pointer,
    )
    successor_pointer = successor_typed["active_pointer"]
    if not isinstance(successor_pointer, bytes):
        raise AssertionError("current successor pointer is invalid")
    inputs.update(
        {
            "release_artifact": successor_chain["release"],
            "active_pointer_artifact": successor_pointer,
            "release_history_artifact": successor_chain["history"],
            "historical_release_artifacts": (prior_release,),
            "generation_manifest_bytes": manifest,
            "generation_member_bytes": member_bytes,
            "pointer_history_artifact": next(
                raw
                for coordinate, raw in member_bytes.items()
                if "/pointer_history/" in coordinate
            ),
            "_chain": successor_chain,
            "_typed_members": successor_typed,
        }
    )
    return inputs


def _approve(inputs: dict[str, object]) -> dict[str, object]:
    required_bytes = (
        "registry_bytes", "report_bytes", "environment_observation_bytes", "bootstrap_artifact",
        "recovery_artifact", "lifecycle_artifact", "release_artifact", "active_pointer_artifact",
        "release_history_artifact",
    )
    if any(not isinstance(inputs[name], bytes) for name in required_bytes):
        raise AssertionError("acceptance fixture has a non-byte artifact")
    material = inputs["verifier_material"]
    if not isinstance(material, VerifierHeldTrustMaterial):
        raise AssertionError("acceptance fixture has invalid trust material")
    group_id, revision, tree_digest, now = inputs["group_id"], inputs["implementation_revision"], inputs["implementation_tree_digest"], inputs["now"]
    if not isinstance(group_id, str) or not isinstance(revision, str) or not isinstance(tree_digest, str) or not isinstance(now, datetime):
        raise AssertionError("acceptance fixture has invalid scalar input")
    artifacts = inputs["artifacts"]
    historical = inputs["historical_release_artifacts"]
    if not isinstance(artifacts, dict) or not all(isinstance(key, str) and isinstance(value, bytes) for key, value in artifacts.items()):
        raise AssertionError("acceptance fixture has invalid artifact map")
    if not isinstance(historical, tuple) or not all(isinstance(item, bytes) for item in historical):
        raise AssertionError("acceptance fixture has invalid historical releases")
    registry_bytes, report_bytes, environment_bytes, bootstrap, recovery, lifecycle, release, pointer, history = (inputs[name] for name in required_bytes)
    assert isinstance(registry_bytes, bytes)
    assert isinstance(report_bytes, bytes)
    assert isinstance(environment_bytes, bytes)
    assert isinstance(bootstrap, bytes)
    assert isinstance(recovery, bytes)
    assert isinstance(lifecycle, bytes)
    assert isinstance(release, bytes)
    assert isinstance(pointer, bytes)
    assert isinstance(history, bytes)
    expected_roots = inputs["expected_release_roots"]
    if not isinstance(expected_roots, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in expected_roots.items()):
        raise AssertionError("acceptance fixture has invalid expected roots")
    with tempfile.TemporaryDirectory() as directory:
        store = FileTraceabilityReleaseWatermarkStore(Path(directory) / "acceptance-watermark.json")
        provisioning = inputs["watermark_provisioning"]
        if not isinstance(provisioning, tuple) or len(provisioning) != 3:
            raise AssertionError("acceptance fixture has invalid watermark provisioning")
        assert isinstance(store.provision(*provisioning), WatermarkAdvanced)
        authority = AcceptanceTrustStore(
            material=material,
            watermark_store=store,
            expected_release_roots=expected_roots,
            independent_generation_verifier=inputs[
                "independent_generation_verifier"
            ],
            allow_test_watermark_fallback=True,
        )
        return _registered_call(inputs, authority)


def _registered_call(inputs: dict[str, object], authority: AcceptanceTrustStore) -> dict[str, object]:
    required = ("registry_bytes", "group_id", "report_bytes", "artifacts", "implementation_revision", "implementation_tree_digest", "environment_observation_bytes", "bootstrap_artifact", "recovery_artifact", "lifecycle_artifact", "release_artifact", "active_pointer_artifact", "release_history_artifact", "historical_release_artifacts", "now")
    if any(name not in inputs for name in required):
        raise AssertionError("acceptance fixture is incomplete")
    if authority.independent_generation_verifier is None:
        authority = replace(
            authority,
            independent_generation_verifier=inputs[
                "independent_generation_verifier"
            ],
        )
    return RegisteredApprovalExecutor(authority).execute(
        registry_bytes=inputs["registry_bytes"], group_id=inputs["group_id"], report_bytes=inputs["report_bytes"],
        artifacts=inputs["artifacts"], implementation_revision=inputs["implementation_revision"],
        implementation_tree_digest=inputs["implementation_tree_digest"],
        environment_observation_bytes=inputs["environment_observation_bytes"], bootstrap_artifact=inputs["bootstrap_artifact"],
        recovery_artifact=inputs["recovery_artifact"], lifecycle_artifact=inputs["lifecycle_artifact"],
        release_artifact=inputs["release_artifact"], active_pointer_artifact=inputs["active_pointer_artifact"],
        release_history_artifact=inputs["release_history_artifact"], pointer_history_artifact=inputs.get("pointer_history_artifact"), historical_release_artifacts=inputs["historical_release_artifacts"],
        recovery_artifacts=inputs.get("recovery_artifacts", ()),
        generation_manifest_bytes=inputs.get("generation_manifest_bytes"),
        generation_member_bytes=inputs.get("generation_member_bytes"),
        design_document_bytes=inputs.get("design_document_bytes"),
        now=inputs["now"],
    )


class _CountingWatermarkStore:
    """Protocol-shaped test double that makes commit inputs observable."""

    def __init__(self, result: object) -> None:
        self._result = result
        self.calls: list[tuple[int, int, str]] = []
        self.sentinel_state = {"unchanged": True}

    def provision(self, epoch: int, sequence: int, release_digest: str) -> WatermarkAdvanced:
        return WatermarkAdvanced()

    def compare_and_advance(self, epoch: int, sequence: int, release_digest: str) -> object:
        self.calls.append((epoch, sequence, release_digest))
        return self._result


@pytest.mark.parametrize("group_id", ["semantic-ingestion-r03", "semantic-ingestion-r13"])
def test_registered_normative_approval_accepts_signed_provisioned_generation(group_id: str) -> None:
    assert _approve(_approval_inputs(group_id))["command_id"]


@pytest.mark.parametrize(
    ("watermark_result", "expected"),
    [
        (
            WatermarkUnavailable(reason="injected_watermark_unavailable"),
            "release gate did not authorize: injected_watermark_unavailable",
        ),
        (object(), "release gate did not authorize: watermark_store_indeterminate"),
    ],
)
def test_registered_approval_rejects_unavailable_or_indeterminate_watermark_commit_outcomes(
    watermark_result: object, expected: str
) -> None:
    inputs = _approval_inputs("semantic-ingestion-r03")
    material = inputs["verifier_material"]
    expected_roots = inputs["expected_release_roots"]
    release_bytes = inputs["release_artifact"]
    assert isinstance(material, VerifierHeldTrustMaterial)
    assert isinstance(expected_roots, dict)
    assert isinstance(release_bytes, bytes)
    release, _ = _typed_body(release_bytes)
    store = _CountingWatermarkStore(watermark_result)
    sentinel_before = dict(store.sentinel_state)

    with pytest.raises(ExecutionEvidenceError, match=expected):
        _registered_call(inputs, AcceptanceTrustStore(material, store, expected_roots, allow_test_watermark_fallback=True))

    assert store.calls == [(release["epoch"], release["sequence"], release["release_digest"])]
    assert store.sentinel_state == sentinel_before


def test_registered_approval_accepts_threshold_recovery_then_ordinary_rotation() -> None:
    assert _approve(_threshold_recovery_inputs("semantic-ingestion-r03"))["command_id"]


def test_registered_approval_rejects_unactivated_threshold_recovery_without_mutation(
    tmp_path: Path,
) -> None:
    inputs = _approval_inputs(
        "semantic-ingestion-r03",
        threshold_recovery=True,
        activate_recovery_roots=False,
    )
    path = tmp_path / "unactivated-recovery-watermark.json"
    authority, record_before, seal_before = _provisioned_authority(inputs, path)
    with pytest.raises(
        ExecutionEvidenceError,
        match="release gate did not authorize: recovery_root_not_lifecycle_eligible",
    ):
        _registered_call(inputs, authority)
    assert path.read_bytes() == record_before
    assert path.with_name(f"{path.name}.bootstrap-seal").read_bytes() == seal_before


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("missing", "trust_not_independently_provisioned"),
        ("duplicate", "recovery_roots_duplicate"),
    ],
)
def test_registered_approval_rejects_invalid_additional_recovery_roots_without_mutation(
    tmp_path: Path, mutation: str, expected: str
) -> None:
    inputs = _threshold_recovery_inputs("semantic-ingestion-r03")
    additional = inputs["recovery_artifacts"]
    assert isinstance(additional, tuple) and len(additional) == 1
    inputs["recovery_artifacts"] = () if mutation == "missing" else (additional[0], additional[0])
    path = tmp_path / f"{mutation}-recovery-watermark.json"
    authority, record_before, seal_before = _provisioned_authority(inputs, path)
    with pytest.raises(ExecutionEvidenceError, match=expected):
        _registered_call(inputs, authority)
    assert path.read_bytes() == record_before
    assert path.with_name(f"{path.name}.bootstrap-seal").read_bytes() == seal_before


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("missing_prior", "provisioned_successor_lifecycle_root_invalid"),
        ("duplicate_prior", "prior_lifecycle_root_missing_or_ambiguous"),
        ("cross_authority_prior", "prior_lifecycle_root_authority_invalid"),
        ("wrong_terminal_coordinate", "lifecycle_root_successor_binding_invalid"),
    ],
)
def test_public_current_ctv_rejects_prior_root_attacks_without_durable_mutation(
    tmp_path: Path, mutation: str, expected: str
) -> None:
    inputs = _approval_inputs("semantic-ingestion-r03")
    material = inputs["verifier_material"]
    assert isinstance(material, VerifierHeldTrustMaterial)
    prior_roots = material.prior_verified_lifecycle_root_bytes
    assert len(prior_roots) == 1
    if mutation == "missing_prior":
        replacement_priors: tuple[bytes, ...] = ()
    elif mutation == "duplicate_prior":
        replacement_priors = (prior_roots[0], prior_roots[0])
    elif mutation == "cross_authority_prior":
        prior_body, prior_binding = _typed_body(prior_roots[0])
        prior_body["authority_id"] = "cross-authority"
        replacement_priors = (serialize_artifact(prior_body, prior_binding),)
    else:
        replacement_priors = prior_roots
        lifecycle_raw = inputs["lifecycle_artifact"]
        assert isinstance(lifecycle_raw, bytes)
        lifecycle_body, lifecycle_binding = _typed_body(lifecycle_raw)
        coordinates = lifecycle_body["signer_coordinates"]
        assert isinstance(coordinates, list) and isinstance(coordinates[0], dict)
        coordinates[0]["lifecycle_record_digest"] = "0" * 64
        inputs["lifecycle_artifact"] = serialize_artifact(
            lifecycle_body, lifecycle_binding
        )
    inputs["verifier_material"] = VerifierHeldTrustMaterial(
        material.bootstrap_anchor_bytes,
        material.recovery_root_bytes,
        material.verify_signature,
        material.recovery_policy_bytes,
        material.provisioned_successor_root_bytes,
        replacement_priors,
    )
    path = tmp_path / f"{mutation}-prior-root-watermark.json"
    authority, record_before, seal_before = _provisioned_authority(inputs, path)
    with pytest.raises(
        ExecutionEvidenceError,
        match=f"release gate did not authorize: {expected}",
    ):
        _registered_call(inputs, authority)
    assert path.read_bytes() == record_before
    assert path.with_name(f"{path.name}.bootstrap-seal").read_bytes() == seal_before


@pytest.mark.parametrize(
    ("case_id", "bootstrap_end", "release_issued_at"),
    [
        (
            "verification_time_ineligible",
            "2026-01-01T00:00:04Z",
            "2026-01-01T00:00:03Z",
        ),
        (
            "issuance_at_exclusive_end",
            "2026-01-01T00:00:03Z",
            "2026-01-01T00:00:03Z",
        ),
        (
            "issuance_beyond_end",
            "2026-01-01T00:00:03Z",
            "2026-01-01T00:00:03.500000Z",
        ),
    ],
)
def test_public_current_ctv_rejects_ineligible_release_signer_without_durable_mutation(
    tmp_path: Path,
    case_id: str,
    bootstrap_end: str,
    release_issued_at: str,
) -> None:
    inputs = _approval_inputs(
        "semantic-ingestion-r03",
        bootstrap_expires_at=bootstrap_end,
        release_issued_at=release_issued_at,
    )
    path = tmp_path / f"{case_id}-watermark.json"
    authority, record_before, seal_before = _provisioned_authority(inputs, path)
    with pytest.raises(
        ExecutionEvidenceError,
        match="release gate did not authorize: signer_coordinate_not_lifecycle_eligible",
    ):
        _registered_call(inputs, authority)
    assert path.read_bytes() == record_before
    assert path.with_name(f"{path.name}.bootstrap-seal").read_bytes() == seal_before


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("report", "runner report command is not registered"),
        ("runner", "runner environment observation bytes are unavailable"),
        ("artifact", "runner report artifact is unavailable"),
    ],
)
def test_registered_successor_report_failures_do_not_advance_watermark(
    tmp_path: Path, mutation: str, expected: str
) -> None:
    inputs = _successor_inputs("semantic-ingestion-r03")
    report_bytes = inputs["report_bytes"]
    assert isinstance(report_bytes, bytes)
    report = json.loads(report_bytes)
    if mutation == "report":
        report["command_id"] = "unregistered-command"
        inputs["report_bytes"] = canonical_document(report)
    elif mutation == "runner":
        environment = inputs["environment_observation_bytes"]
        assert isinstance(environment, bytes)
        observed = json.loads(environment)
        observed["plugins"] = {"forged": True}
        inputs["environment_observation_bytes"] = canonical_document(observed)
    else:
        artifacts = inputs["artifacts"]
        result_digest = report["tests"][0]["result_artifact_digest"]
        assert isinstance(artifacts, dict)
        assert isinstance(result_digest, str)
        inputs["artifacts"] = {
            key: value for key, value in artifacts.items() if key != result_digest
        }
    path = tmp_path / f"{mutation}-successor-watermark.json"
    authority, record_before, seal_before = _provisioned_authority(inputs, path)
    files_before = {
        item.name: item.read_bytes() for item in tmp_path.iterdir() if item.is_file()
    }
    with pytest.raises(ExecutionEvidenceError, match=expected):
        _registered_call(inputs, authority)
    assert path.read_bytes() == record_before
    assert path.with_name(f"{path.name}.bootstrap-seal").read_bytes() == seal_before
    assert {
        item.name: item.read_bytes() for item in tmp_path.iterdir() if item.is_file()
    } == files_before


def test_registered_valid_successor_advances_once_and_retry_is_idempotent(
    tmp_path: Path,
) -> None:
    inputs = _successor_inputs("semantic-ingestion-r03")
    path = tmp_path / "valid-successor-watermark.json"
    authority, record_before, seal_before = _provisioned_authority(inputs, path)
    assert _registered_call(inputs, authority)["command_id"] == "pytest-sia-r03-v1"
    record_after = path.read_bytes()
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    assert record_after != record_before
    release_bytes = inputs["release_artifact"]
    assert isinstance(release_bytes, bytes)
    release, _ = _typed_body(release_bytes)
    assert json.loads(record_after) == {
        "format": "memorii.semantic-ingestion.acceptance-watermark.v1",
        "epoch": 1,
        "sequence": 2,
        "release_digest": release["release_digest"],
    }
    assert seal.read_bytes() == seal_before
    files_after = {
        item.name: item.read_bytes() for item in tmp_path.iterdir() if item.is_file()
    }
    assert _registered_call(inputs, authority)["command_id"] == "pytest-sia-r03-v1"
    assert path.read_bytes() == record_after
    assert seal.read_bytes() == seal_before
    assert {
        item.name: item.read_bytes() for item in tmp_path.iterdir() if item.is_file()
    } == files_after


def test_public_acceptance_fails_closed_for_corrupt_persisted_watermark(tmp_path: Path) -> None:
    inputs = _approval_inputs("semantic-ingestion-r03")
    required = (
        "registry_bytes", "registry", "report_bytes", "artifacts", "implementation_revision",
        "implementation_tree_digest", "environment_observation_bytes", "bootstrap_artifact",
        "recovery_artifact", "lifecycle_artifact", "release_artifact", "active_pointer_artifact",
        "release_history_artifact", "verifier_material", "expected_release_roots", "now",
    )
    assert all(name in inputs for name in required)
    path = tmp_path / "acceptance-watermark.json"
    path.write_bytes(b"not canonical json")
    with pytest.raises(ExecutionEvidenceError, match="watermark_storage_corrupt"):
        RegisteredApprovalExecutor(
            AcceptanceTrustStore(
                inputs["verifier_material"], FileTraceabilityReleaseWatermarkStore(path), inputs["expected_release_roots"],
                independent_generation_verifier=inputs[
                    "independent_generation_verifier"
                ],
                allow_test_watermark_fallback=True,
            )
        ).execute(
            registry_bytes=inputs["registry_bytes"], group_id="semantic-ingestion-r03",
            report_bytes=inputs["report_bytes"], artifacts=inputs["artifacts"],
            implementation_revision=inputs["implementation_revision"],
            implementation_tree_digest=inputs["implementation_tree_digest"],
            environment_observation_bytes=inputs["environment_observation_bytes"],
            bootstrap_artifact=inputs["bootstrap_artifact"], recovery_artifact=inputs["recovery_artifact"],
            lifecycle_artifact=inputs["lifecycle_artifact"], release_artifact=inputs["release_artifact"],
                active_pointer_artifact=inputs["active_pointer_artifact"],
                release_history_artifact=inputs["release_history_artifact"],
                generation_manifest_bytes=inputs["generation_manifest_bytes"],
                generation_member_bytes=inputs["generation_member_bytes"],
                design_document_bytes=inputs["design_document_bytes"],
                now=inputs["now"],
        )


@pytest.mark.parametrize("deleted", ["unprovisioned", "after_provision"])
def test_public_acceptance_never_creates_or_recreates_missing_watermark(tmp_path: Path, deleted: str) -> None:
    inputs = _approval_inputs("semantic-ingestion-r03")
    path = tmp_path / "acceptance-watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    if deleted == "after_provision":
        provisioning = inputs["watermark_provisioning"]
        assert isinstance(provisioning, tuple)
        assert isinstance(store.provision(*provisioning), WatermarkAdvanced)
        path.unlink()
    authority = AcceptanceTrustStore(inputs["verifier_material"], store, inputs["expected_release_roots"], allow_test_watermark_fallback=True)
    with pytest.raises(ExecutionEvidenceError, match="watermark_storage_missing"):
        _registered_call(inputs, authority)
    assert not path.exists()


@pytest.mark.parametrize("failure", ["missing", "corrupt"])
def test_public_acceptance_fails_closed_for_missing_or_corrupt_bootstrap_seal(
    tmp_path: Path, failure: str
) -> None:
    inputs = _approval_inputs("semantic-ingestion-r03")
    path = tmp_path / "acceptance-watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    provisioning = inputs["watermark_provisioning"]
    assert isinstance(provisioning, tuple)
    assert isinstance(store.provision(*provisioning), WatermarkAdvanced)
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    record_before = path.read_bytes()
    if failure == "missing":
        seal.unlink()
        expected_reason = "watermark_storage_missing"
    else:
        seal.write_bytes(b"not canonical json")
        expected_reason = "watermark_storage_corrupt"
    with pytest.raises(ExecutionEvidenceError, match=expected_reason):
        _registered_call(
            inputs,
            AcceptanceTrustStore(inputs["verifier_material"], store, inputs["expected_release_roots"], allow_test_watermark_fallback=True),
        )
    assert path.read_bytes() == record_before
    if failure == "missing":
        assert not seal.exists()
    else:
        assert seal.read_bytes() == b"not canonical json"


def test_public_boundary_rejects_forged_registry_object_argument(tmp_path: Path) -> None:
    inputs = _approval_inputs("semantic-ingestion-r03")
    fake = SimpleNamespace(canonical_bytes=inputs["registry_bytes"], source_identity="0" * 64, root_digests={})
    with pytest.raises(TypeError, match="registry"):
        RegisteredApprovalExecutor(
            AcceptanceTrustStore(
                inputs["verifier_material"],
                FileTraceabilityReleaseWatermarkStore(tmp_path / "watermark.json"),
                inputs["expected_release_roots"],
                allow_test_watermark_fallback=True,
            )
        ).execute(
            registry_bytes=inputs["registry_bytes"], registry=fake, group_id="semantic-ingestion-r03",
            report_bytes=inputs["report_bytes"], artifacts=inputs["artifacts"],
            implementation_revision=inputs["implementation_revision"], implementation_tree_digest=inputs["implementation_tree_digest"],
            environment_observation_bytes=inputs["environment_observation_bytes"], bootstrap_artifact=inputs["bootstrap_artifact"],
            recovery_artifact=inputs["recovery_artifact"], lifecycle_artifact=inputs["lifecycle_artifact"],
            release_artifact=inputs["release_artifact"], active_pointer_artifact=inputs["active_pointer_artifact"],
            release_history_artifact=inputs["release_history_artifact"], now=inputs["now"],
        )


def _provisioned_authority(
    inputs: dict[str, object], path: Path
) -> tuple[AcceptanceTrustStore, bytes, bytes]:
    """Create a real sealed watermark already at the candidate coordinate."""
    provisioning = inputs["watermark_provisioning"]
    material = inputs["verifier_material"]
    expected_roots = inputs["expected_release_roots"]
    assert isinstance(provisioning, tuple) and len(provisioning) == 3
    assert isinstance(material, VerifierHeldTrustMaterial)
    assert isinstance(expected_roots, dict)
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(*provisioning), WatermarkAdvanced)
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    return AcceptanceTrustStore(material, store, expected_roots, allow_test_watermark_fallback=True), path.read_bytes(), seal.read_bytes()


def test_public_acceptance_reconstructs_supplied_loader_valid_registry_bytes_before_root_check(
    tmp_path: Path,
) -> None:
    inputs = _approval_inputs("semantic-ingestion-r03")
    raw = inputs["registry_bytes"]
    assert isinstance(raw, bytes)
    source = json.loads(raw)
    # This remains a canonical source package; only its declared heading
    # default differs, so the supplied bytes acquire a distinct root identity.
    source["heading_defaults"][0]["requirements"] = ["SIA-R03"]
    inputs["registry_bytes"] = canonical_document(source)
    authority, record_before, seal_before = _provisioned_authority(
        inputs, tmp_path / "watermark.json"
    )
    with pytest.raises(ExecutionEvidenceError, match="active_pointer_current_release_root_binding_invalid"):
        _registered_call(inputs, authority)
    path = tmp_path / "watermark.json"
    assert path.read_bytes() == record_before
    assert path.with_name(f"{path.name}.bootstrap-seal").read_bytes() == seal_before


_PUBLIC_ARRAY_ROOT_NAMES = (
    "anchor_bindings",
    "artifact_dag",
    "assertion_templates",
    "heading_defaults",
    "overrides",
    "report_schemas",
    "requirement_bindings",
    "runner_environment_profiles",
    "structural_rules",
    "test_evidence_groups",
)


def _parser_hostile_registry_bytes() -> tuple[tuple[str, bytes], ...]:
    return (
        ("deep_array", b"[" * 1100 + b"0" + b"]" * 1100 + b"\n"),
        ("deep_object", b'{"child":' * 1100 + b"0" + b"}" * 1100 + b"\n"),
        (
            "deep_schema",
            b'{"type":"array","items":' * 1100
            + b'{"type":"null"}'
            + b"}" * 1100
            + b"\n",
        ),
        ("oversized_integer", b'{"value":' + b"9" * 5000 + b"}\n"),
    )


@pytest.mark.parametrize(
    ("case_id", "mutate"),
    (
        ("trailing_space_without_final_lf", lambda raw: raw + b" "),
        ("extra_line_feed", lambda raw: raw + b"\n"),
        ("utf8_bom", lambda raw: b"\xef\xbb\xbf" + raw),
    ),
)
def test_public_acceptance_rejects_noncanonical_registry_bytes_before_durable_state(
    tmp_path: Path, case_id: str, mutate: object
) -> None:
    inputs = _approval_inputs("semantic-ingestion-r03")
    raw = inputs["registry_bytes"]
    assert isinstance(raw, bytes) and callable(mutate)
    inputs["registry_bytes"] = mutate(raw)
    path = tmp_path / f"{case_id}-watermark.json"
    authority, record_before, seal_before = _provisioned_authority(inputs, path)
    with pytest.raises(TraceabilityCoverageError):
        _registered_call(inputs, authority)
    assert path.read_bytes() == record_before
    assert path.with_name(f"{path.name}.bootstrap-seal").read_bytes() == seal_before


@pytest.mark.parametrize(("case_id", "registry_bytes"), _parser_hostile_registry_bytes())
def test_public_acceptance_rejects_parser_hostile_registry_before_durable_state(
    tmp_path: Path, case_id: str, registry_bytes: bytes
) -> None:
    inputs = _approval_inputs("semantic-ingestion-r03")
    inputs["registry_bytes"] = registry_bytes
    path = tmp_path / f"{case_id}-watermark.json"
    authority, record_before, seal_before = _provisioned_authority(inputs, path)
    with pytest.raises(TraceabilityCoverageError):
        _registered_call(inputs, authority)
    assert path.read_bytes() == record_before
    assert path.with_name(f"{path.name}.bootstrap-seal").read_bytes() == seal_before


@pytest.mark.parametrize("root", _PUBLIC_ARRAY_ROOT_NAMES)
@pytest.mark.parametrize(
    ("replacement_id", "replacement"),
    (("object", {}), ("null", None), ("string", "not-an-array"), ("number", 1)),
)
def test_public_acceptance_rejects_non_array_registry_root_before_durable_state(
    tmp_path: Path, root: str, replacement_id: str, replacement: object
) -> None:
    inputs = _approval_inputs("semantic-ingestion-r03")
    raw = inputs["registry_bytes"]
    assert isinstance(raw, bytes)
    source = json.loads(raw)
    source[root] = replacement
    inputs["registry_bytes"] = canonical_document(source)
    path = tmp_path / f"{root}-{replacement_id}-watermark.json"
    authority, record_before, seal_before = _provisioned_authority(inputs, path)
    with pytest.raises(TraceabilityCoverageError):
        _registered_call(inputs, authority)
    assert path.read_bytes() == record_before
    assert path.with_name(f"{path.name}.bootstrap-seal").read_bytes() == seal_before


def test_public_acceptance_rejects_lone_surrogate_before_durable_state(
    tmp_path: Path,
) -> None:
    inputs = _approval_inputs("semantic-ingestion-r03")
    raw = inputs["registry_bytes"]
    assert isinstance(raw, bytes)
    source = json.loads(raw)
    source["assertion_templates"][0]["acceptance"] = "lone-surrogate-marker"
    mutated = canonical_document(source)
    assert mutated.count(b'"lone-surrogate-marker"') == 1
    inputs["registry_bytes"] = mutated.replace(
        b'"lone-surrogate-marker"', b'"\\ud800"', 1
    )
    path = tmp_path / "lone-surrogate-watermark.json"
    authority, record_before, seal_before = _provisioned_authority(inputs, path)
    with pytest.raises(TraceabilityCoverageError):
        _registered_call(inputs, authority)
    assert path.read_bytes() == record_before
    assert path.with_name(f"{path.name}.bootstrap-seal").read_bytes() == seal_before


def test_public_acceptance_rejects_rebound_pattern_compile_overflow_before_durable_state(
    tmp_path: Path,
) -> None:
    inputs = _approval_inputs("semantic-ingestion-r03")
    raw = inputs["registry_bytes"]
    assert isinstance(raw, bytes)
    source = json.loads(raw)
    schema = source["report_schemas"][0]["schema_document"]
    assert isinstance(schema, dict)
    properties = schema["properties"]
    assert isinstance(properties, dict)
    argv = properties["argv"]
    assert isinstance(argv, dict)
    items = argv["items"]
    assert isinstance(items, dict)
    items["pattern"] = "a{999999999999999999999999999999}"
    _rebind_public_specialized_group_digests(source)
    inputs["registry_bytes"] = canonical_document(source)
    path = tmp_path / "pattern-compile-overflow-watermark.json"
    authority, record_before, seal_before = _provisioned_authority(inputs, path)
    with pytest.raises(TraceabilityCoverageError, match="pattern is not compilable"):
        _registered_call(inputs, authority)
    assert path.read_bytes() == record_before
    assert path.with_name(f"{path.name}.bootstrap-seal").read_bytes() == seal_before


@pytest.mark.parametrize(
    "mutation",
    ("duplicate_dag_dependency", "duplicate_rule_id", "duplicate_anchor", "nonempty_overrides"),
)
def test_public_acceptance_rejects_closed_registry_duplicate_policy_before_watermark_mutation(
    tmp_path: Path, mutation: str
) -> None:
    inputs = _approval_inputs("semantic-ingestion-r03")
    raw = inputs["registry_bytes"]
    assert isinstance(raw, bytes)
    source = json.loads(raw)
    if mutation == "duplicate_dag_dependency":
        node = next(item for item in source["artifact_dag"] if item["depends_on"])
        node["depends_on"].append(node["depends_on"][0])
    elif mutation == "duplicate_rule_id":
        source["structural_rules"].append({**source["structural_rules"][0]})
    elif mutation == "duplicate_anchor":
        source["anchor_bindings"].append({**source["anchor_bindings"][0]})
    else:
        source["overrides"].append(
            {"invariant_id": "SIA-N-test-0", "added_requirements": ["SIA-R01"]}
        )
    inputs["registry_bytes"] = canonical_document(source)
    path = tmp_path / f"{mutation}-watermark.json"
    authority, record_before, seal_before = _provisioned_authority(inputs, path)
    with pytest.raises(TraceabilityCoverageError):
        _registered_call(inputs, authority)
    assert path.read_bytes() == record_before
    assert path.with_name(f"{path.name}.bootstrap-seal").read_bytes() == seal_before


@pytest.mark.parametrize(
    "mutation",
    (
        "unknown_requirement_binding",
        "unknown_assertion_template",
        "unknown_heading_default",
        "unknown_structural_rule",
        "unknown_anchor",
        "unknown_artifact_node",
        "unknown_test_group",
        "assertion_version_mismatch",
        "requirement_binding_order",
        "assertion_template_order",
        "test_group_order",
        "dependency_string",
        "dependency_null",
        "dependency_object",
        "dependency_number",
        "dependency_mixed",
        "kahn_valid_reorder",
    ),
)
def test_public_acceptance_rejects_closed_v1_registry_mutations_before_durable_state(
    tmp_path: Path, mutation: str
) -> None:
    inputs = _approval_inputs("semantic-ingestion-r03")
    raw = inputs["registry_bytes"]
    assert isinstance(raw, bytes)
    source = json.loads(raw)
    bindings = source["requirement_bindings"]
    templates = source["assertion_templates"]
    groups = source["test_evidence_groups"]
    nodes = source["artifact_dag"]
    unknown_member_roots = {
        "unknown_requirement_binding": "requirement_bindings",
        "unknown_assertion_template": "assertion_templates",
        "unknown_heading_default": "heading_defaults",
        "unknown_structural_rule": "structural_rules",
        "unknown_anchor": "anchor_bindings",
        "unknown_artifact_node": "artifact_dag",
        "unknown_test_group": "test_evidence_groups",
    }
    if mutation in unknown_member_roots:
        source[unknown_member_roots[mutation]][0]["unknown_v1_member"] = "forbidden"
    elif mutation == "assertion_version_mismatch":
        bindings[0]["assertion_version"] = 2
    elif mutation == "requirement_binding_order":
        bindings[0], bindings[1] = bindings[1], bindings[0]
    elif mutation == "assertion_template_order":
        templates.append({**templates[0], "template_id": "aaa-structural-conformance"})
    elif mutation == "test_group_order":
        groups[0], groups[1] = groups[1], groups[0]
    elif mutation.startswith("dependency_"):
        node = next(item for item in nodes if item["depends_on"])
        if mutation == "dependency_string":
            node["depends_on"] = ""
        elif mutation == "dependency_null":
            node["depends_on"] = None
        elif mutation == "dependency_object":
            node["depends_on"] = {}
        elif mutation == "dependency_number":
            node["depends_on"] = 1
        else:
            node["depends_on"] = [node["depends_on"][0], 1]
    elif mutation == "kahn_valid_reorder":
        nodes[0], nodes[1] = nodes[1], nodes[0]
    else:
        nodes[0]["depends_on"] = ["recovery_trust_roots"]
    inputs["registry_bytes"] = canonical_document(source)
    path = tmp_path / f"{mutation}-watermark.json"
    authority, record_before, seal_before = _provisioned_authority(inputs, path)
    with pytest.raises(TraceabilityCoverageError):
        _registered_call(inputs, authority)
    assert path.read_bytes() == record_before
    assert path.with_name(f"{path.name}.bootstrap-seal").read_bytes() == seal_before


@pytest.mark.parametrize(
    "mutation",
    (
        "missing",
        "duplicate_heading",
        "empty_requirements",
        "unknown_requirement",
        "duplicate_requirement",
        "requirement_order",
    ),
)
def test_public_acceptance_rejects_closed_heading_defaults_before_durable_state(
    tmp_path: Path, mutation: str
) -> None:
    inputs = _approval_inputs("semantic-ingestion-r03")
    raw = inputs["registry_bytes"]
    assert isinstance(raw, bytes)
    source = json.loads(raw)
    defaults = source["heading_defaults"]
    if mutation == "missing":
        defaults.pop()
    elif mutation == "duplicate_heading":
        defaults.append(defaults[0].copy())
    elif mutation == "empty_requirements":
        defaults[0]["requirements"] = []
    elif mutation == "unknown_requirement":
        defaults[0]["requirements"] = ["SIA-R99"]
    elif mutation == "duplicate_requirement":
        defaults[0]["requirements"] = ["SIA-R01", "SIA-R01"]
    else:
        target = next(item for item in defaults if len(item["requirements"]) > 1)
        target["requirements"] = list(reversed(target["requirements"]))
    inputs["registry_bytes"] = canonical_document(source)
    path = tmp_path / f"heading-default-{mutation}-watermark.json"
    authority, record_before, seal_before = _provisioned_authority(inputs, path)
    with pytest.raises(TraceabilityCoverageError):
        _registered_call(inputs, authority)
    assert path.read_bytes() == record_before
    assert path.with_name(f"{path.name}.bootstrap-seal").read_bytes() == seal_before


def test_public_acceptance_rejects_kahn_back_edge_before_durable_state(
    tmp_path: Path,
) -> None:
    inputs = _approval_inputs("semantic-ingestion-r03")
    raw = inputs["registry_bytes"]
    assert isinstance(raw, bytes)
    source = json.loads(raw)
    nodes = source["artifact_dag"]
    nodes[0]["depends_on"] = ["recovery_trust_roots"]
    inputs["registry_bytes"] = canonical_document(source)
    path = tmp_path / "kahn-back-edge-watermark.json"
    authority, record_before, seal_before = _provisioned_authority(inputs, path)
    with pytest.raises(TraceabilityCoverageError, match="deterministic Kahn"):
        _registered_call(inputs, authority)
    assert path.read_bytes() == record_before
    assert path.with_name(f"{path.name}.bootstrap-seal").read_bytes() == seal_before


_SPECIALIZED_V1_PUBLIC_MUTATIONS = (
    "metadata_format_literal",
    "metadata_registry_id_type",
    "metadata_registry_id_literal",
    "metadata_grammar_revision_literal",
    "metadata_design_path_type",
    "metadata_design_path_literal",
    "report_unknown_outer",
    "report_unknown_root",
    "report_canonical_literal",
    "report_media_literal",
    "report_schema_id_list",
    "report_schema_id_number",
    "report_version_bool",
    "report_version_zero",
    "report_version_string",
    "report_version_two",
    "report_document_schema_literal",
    "report_document_additional_literal",
    "report_document_properties_type",
    "report_document_required_type",
    "report_document_required_item_type",
    "report_document_type_literal",
    "report_property_schema_list",
    "report_duplicate_required",
    "report_inconsistent_required",
    "report_incomplete_closed_required",
    "report_unsupported_keyword",
    "report_unsupported_type",
    "report_anyof_empty",
    "report_anyof_invalid_alternative",
    "report_const_extra_keyword",
    "report_incompatible_keyword",
    "report_items_type",
    "report_min_items_bool",
    "report_unique_items_type",
    "report_min_length_bool",
    "report_pattern_type",
    "report_pattern_uncompilable",
    "report_format_literal",
    "report_additional_properties_type",
    "profile_unknown_outer",
    "profile_canonical_literal",
    "profile_id_list",
    "profile_id_number",
    "profile_version_bool",
    "profile_version_zero",
    "profile_version_string",
    "profile_version_two",
    "interpreter_unknown_member",
    "interpreter_literal",
    "interpreter_invocation_type",
    "runner_literal",
    "runner_version_type",
    "plugin_allowed_type",
    "configuration_literal",
    "configuration_option_literal",
    "configuration_file_unknown",
    "configuration_file_digest_type",
    "pytest_ini_unknown",
    "pytest_ini_testpaths_literal",
    "pytest_ini_markers_type",
    "dependency_unknown",
    "project_metadata_literal",
    "project_metadata_digest_type",
    "lockfile_literal",
    "lockfile_required_type",
    "fingerprint_fields_type",
    "fingerprint_literal",
    "import_path_paths_type",
    "import_path_literal",
    "startup_literal",
    "environment_unknown",
    "fixed_variables_unknown",
    "fixed_variable_literal",
    "dynamic_variables_type",
    "locale_literal",
    "network_unknown",
    "network_literal",
)


def _rebind_public_specialized_group_digests(source: dict[str, object]) -> None:
    schemas = source["report_schemas"]
    profiles = source["runner_environment_profiles"]
    groups = source["test_evidence_groups"]
    assert (
        isinstance(schemas, list)
        and len(schemas) == 1
        and isinstance(schemas[0], dict)
    )
    assert (
        isinstance(profiles, list)
        and len(profiles) == 1
        and isinstance(profiles[0], dict)
    )
    assert isinstance(groups, list) and all(isinstance(group, dict) for group in groups)
    schema_digest = sha256(
        b"memorii:sia-report-schema:v1\0" + canonical_document(schemas[0])
    ).hexdigest()
    profile_digest = sha256(
        b"memorii:sia-runner-environment-profile:v1\0"
        + canonical_document(profiles[0])
    ).hexdigest()
    for group in groups:
        group["expected_report_schema_digest"] = schema_digest
        group["expected_runner_environment_profile_digest"] = profile_digest


def _mutate_public_specialized_v1_source(
    source: dict[str, object], mutation: str
) -> None:
    schemas = source["report_schemas"]
    profiles = source["runner_environment_profiles"]
    assert (
        isinstance(schemas, list)
        and len(schemas) == 1
        and isinstance(schemas[0], dict)
    )
    assert (
        isinstance(profiles, list)
        and len(profiles) == 1
        and isinstance(profiles[0], dict)
    )
    schema = schemas[0]
    profile = profiles[0]
    document = schema["schema_document"]
    assert isinstance(document, dict)
    if mutation == "metadata_format_literal":
        source["format"] = "memorii.semantic-ingestion.traceability-source.v2"
    elif mutation == "metadata_registry_id_type":
        source["registry_id"] = ["semantic-ingestion-traceability-registry-v1"]
    elif mutation == "metadata_registry_id_literal":
        source["registry_id"] = "semantic-ingestion-traceability-registry-alternate"
    elif mutation == "metadata_grammar_revision_literal":
        source["grammar_revision"] = "sia-traceability-v2"
    elif mutation == "metadata_design_path_type":
        source["design_path"] = {"path": "docs/design/semantic_ingestion_architecture.md"}
    elif mutation == "metadata_design_path_literal":
        source["design_path"] = "docs/design/alternate.md"
    elif mutation == "report_unknown_outer":
        schema["unknown_v1_member"] = "forbidden"
    elif mutation == "report_unknown_root":
        document["unknown_v1_member"] = "forbidden"
    elif mutation == "report_canonical_literal":
        schema["canonical_profile_id"] = "other-profile"
    elif mutation == "report_media_literal":
        schema["media_type"] = "application/json"
    elif mutation == "report_schema_id_list":
        schema["schema_id"] = ["memorii.semantic_ingestion.pytest_report"]
    elif mutation == "report_schema_id_number":
        schema["schema_id"] = 1
    elif mutation == "report_version_bool":
        schema["schema_version"] = True
    elif mutation == "report_version_zero":
        schema["schema_version"] = 0
    elif mutation == "report_version_string":
        schema["schema_version"] = "1"
    elif mutation == "report_version_two":
        schema["schema_version"] = 2
    elif mutation == "report_document_schema_literal":
        document["$schema"] = "https://json-schema.org/draft/2019-09/schema"
    elif mutation == "report_document_additional_literal":
        document["additionalProperties"] = True
    elif mutation == "report_document_properties_type":
        document["properties"] = []
    elif mutation == "report_document_required_type":
        document["required"] = {}
    elif mutation == "report_document_required_item_type":
        document["required"][0] = 1
    elif mutation == "report_document_type_literal":
        document["type"] = "array"
    elif mutation == "report_property_schema_list":
        document["properties"]["argv"] = []
    elif mutation == "report_duplicate_required":
        document["required"].append(document["required"][0])
    elif mutation == "report_inconsistent_required":
        document["required"].append("not_a_property")
    elif mutation == "report_incomplete_closed_required":
        document["required"].pop()
    elif mutation == "report_unsupported_keyword":
        document["properties"]["argv"]["maxItems"] = 10
    elif mutation == "report_unsupported_type":
        document["properties"]["argv"]["type"] = "number"
    elif mutation == "report_anyof_empty":
        document["properties"]["stdout_artifact_digest"]["anyOf"] = []
    elif mutation == "report_anyof_invalid_alternative":
        document["properties"]["stdout_artifact_digest"]["anyOf"][0] = []
    elif mutation == "report_const_extra_keyword":
        document["properties"]["schema_id"]["minLength"] = 1
    elif mutation == "report_incompatible_keyword":
        document["properties"]["runner_id"]["minItems"] = 1
    elif mutation == "report_items_type":
        document["properties"]["argv"]["items"] = []
    elif mutation == "report_min_items_bool":
        document["properties"]["argv"]["minItems"] = True
    elif mutation == "report_unique_items_type":
        document["properties"]["selected_test_ids"]["uniqueItems"] = "true"
    elif mutation == "report_min_length_bool":
        document["properties"]["runner_id"]["minLength"] = True
    elif mutation == "report_pattern_type":
        document["properties"]["design_document_digest"]["pattern"] = 1
    elif mutation == "report_pattern_uncompilable":
        document["properties"]["design_document_digest"]["pattern"] = "["
    elif mutation == "report_format_literal":
        document["properties"]["started_at"]["format"] = "email"
    elif mutation == "report_additional_properties_type":
        document["properties"]["tests"]["items"]["additionalProperties"] = "false"
    elif mutation == "profile_unknown_outer":
        profile["unknown_v1_member"] = "forbidden"
    elif mutation == "profile_canonical_literal":
        profile["canonical_profile_id"] = "other-profile"
    elif mutation == "profile_id_list":
        profile["profile_id"] = ["memorii.semantic_ingestion.runner_environment"]
    elif mutation == "profile_id_number":
        profile["profile_id"] = 1
    elif mutation == "profile_version_bool":
        profile["profile_version"] = True
    elif mutation == "profile_version_zero":
        profile["profile_version"] = 0
    elif mutation == "profile_version_string":
        profile["profile_version"] = "1"
    elif mutation == "profile_version_two":
        profile["profile_version"] = 2
    elif mutation == "interpreter_unknown_member":
        profile["interpreter_policy"]["unknown_v1_member"] = "forbidden"
    elif mutation == "interpreter_literal":
        profile["interpreter_policy"]["implementation"] = "PyPy"
    elif mutation == "interpreter_invocation_type":
        profile["interpreter_policy"]["invocation"] = "python -m pytest"
    elif mutation == "runner_literal":
        profile["runner_policy"]["distribution"] = "other"
    elif mutation == "runner_version_type":
        profile["runner_policy"]["minimum_version"] = 8
    elif mutation == "plugin_allowed_type":
        profile["plugin_policy"]["allowed_third_party_plugins"] = {}
    elif mutation == "configuration_literal":
        profile["configuration_policy"]["config_discovery"] = "ambient"
    elif mutation == "configuration_option_literal":
        profile["configuration_policy"]["command_options"] = ["-x"]
    elif mutation == "configuration_file_unknown":
        profile["configuration_policy"]["files"][0]["unknown_v1_member"] = "forbidden"
    elif mutation == "configuration_file_digest_type":
        profile["configuration_policy"]["files"][0]["sha256"] = 1
    elif mutation == "pytest_ini_unknown":
        profile["configuration_policy"]["pytest_ini_options"][
            "unknown_v1_member"
        ] = "forbidden"
    elif mutation == "pytest_ini_testpaths_literal":
        profile["configuration_policy"]["pytest_ini_options"]["testpaths"] = ["other"]
    elif mutation == "pytest_ini_markers_type":
        profile["configuration_policy"]["pytest_ini_options"]["markers"] = [1]
    elif mutation == "dependency_unknown":
        profile["dependency_policy"]["unknown_v1_member"] = "forbidden"
    elif mutation == "project_metadata_literal":
        profile["dependency_policy"]["project_metadata"]["path"] = "other.toml"
    elif mutation == "project_metadata_digest_type":
        profile["dependency_policy"]["project_metadata"]["sha256"] = 1
    elif mutation == "lockfile_literal":
        profile["dependency_policy"]["lockfile"]["state"] = "present"
    elif mutation == "lockfile_required_type":
        profile["dependency_policy"]["lockfile"]["state_must_be_observed"] = 1
    elif mutation == "fingerprint_fields_type":
        profile["dependency_policy"]["installed_distribution_fingerprint"][
            "fields"
        ] = "normalized_name"
    elif mutation == "fingerprint_literal":
        profile["dependency_policy"]["installed_distribution_fingerprint"][
            "ordering"
        ] = "source"
    elif mutation == "import_path_paths_type":
        profile["import_path_policy"]["normalized_paths"] = "<implementation-root>"
    elif mutation == "import_path_literal":
        profile["import_path_policy"]["outside_root"] = "allow"
    elif mutation == "startup_literal":
        profile["startup_customization_policy"]["sitecustomize"] = "present"
    elif mutation == "environment_unknown":
        profile["environment_policy"]["unknown_v1_member"] = "forbidden"
    elif mutation == "fixed_variables_unknown":
        profile["environment_policy"]["fixed_variables"][
            "UNKNOWN"
        ] = "forbidden"
    elif mutation == "fixed_variable_literal":
        profile["environment_policy"]["fixed_variables"]["TZ"] = "local"
    elif mutation == "dynamic_variables_type":
        profile["environment_policy"]["dynamic_artifact_coordinate_variables"] = [
            1
        ]
    elif mutation == "locale_literal":
        profile["locale_timezone_policy"]["timezone"] = "local"
    elif mutation == "network_unknown":
        profile["network_policy"]["unknown_v1_member"] = "forbidden"
    elif mutation == "network_literal":
        profile["network_policy"]["enforcement"] = "allowed"
    else:
        raise AssertionError(f"unknown specialized mutation: {mutation}")
    _rebind_public_specialized_group_digests(source)


@pytest.mark.parametrize("mutation", _SPECIALIZED_V1_PUBLIC_MUTATIONS)
def test_public_acceptance_rejects_rebound_specialized_v1_mutations_before_durable_state(
    tmp_path: Path, mutation: str
) -> None:
    inputs = _approval_inputs("semantic-ingestion-r03")
    raw = inputs["registry_bytes"]
    assert isinstance(raw, bytes)
    source = json.loads(raw)
    _mutate_public_specialized_v1_source(source, mutation)
    inputs["registry_bytes"] = canonical_document(source)
    path = tmp_path / f"{mutation}-watermark.json"
    authority, record_before, seal_before = _provisioned_authority(inputs, path)
    with pytest.raises(TraceabilityCoverageError):
        _registered_call(inputs, authority)
    assert path.read_bytes() == record_before
    assert path.with_name(f"{path.name}.bootstrap-seal").read_bytes() == seal_before


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("implementation_revision", "runner report root binding differs"),
        ("implementation_tree_digest", "runner report root binding differs"),
        ("command", "runner report command is not registered"),
        ("selected_test_ids", "selected tests were skipped"),
        ("collected_test_ids", "selected tests were skipped"),
        ("outcome", "differs from the registered schema constant"),
        ("result_artifact_digest", "runner report artifact is unavailable"),
        ("runner_environment_observation_digest", "runner environment observation digest is invalid"),
    ],
)
def test_public_acceptance_rejects_report_mutations_before_watermark_mutation(
    tmp_path: Path, mutation: str, expected: str
) -> None:
    inputs = _approval_inputs("semantic-ingestion-r03")
    report_bytes = inputs["report_bytes"]
    assert isinstance(report_bytes, bytes)
    report = json.loads(report_bytes)
    if mutation == "implementation_revision":
        report[mutation] = "other-revision"
    elif mutation == "implementation_tree_digest":
        report[mutation] = "b" * 64
    elif mutation == "command":
        report["command_id"] = "other-command"
    elif mutation in {"selected_test_ids", "collected_test_ids"}:
        report[mutation] = ["other-test-id"]
    elif mutation == "outcome":
        report["tests"][0]["outcome"] = "failed"
    elif mutation == "result_artifact_digest":
        report["tests"][0]["result_artifact_digest"] = "0" * 64
    else:
        report[mutation] = "0" * 64
    inputs["report_bytes"] = canonical_document(report)
    authority, record_before, seal_before = _provisioned_authority(
        inputs, tmp_path / "watermark.json"
    )
    with pytest.raises(ExecutionEvidenceError, match=expected):
        _registered_call(inputs, authority)
    path = tmp_path / "watermark.json"
    assert path.read_bytes() == record_before
    assert path.with_name(f"{path.name}.bootstrap-seal").read_bytes() == seal_before


def test_public_acceptance_rejects_resigned_forged_structural_root(tmp_path: Path) -> None:
    inputs = _approval_inputs("semantic-ingestion-r03")
    release_bytes, pointer_bytes = inputs["release_artifact"], inputs["active_pointer_artifact"]
    assert isinstance(release_bytes, bytes) and isinstance(pointer_bytes, bytes)
    release, release_binding = _typed_body(release_bytes)
    body = {key: value for key, value in release.items() if key not in {"release_digest", "signature"}}
    inputs["release_artifact"] = _typed_signed({**body, "structural_manifest_digest": "0" * 64}, domain=b"memorii:sia-traceability-release:v1", digest_field="release_digest", binding=release_binding)
    forged, _ = _typed_body(inputs["release_artifact"])
    pointer, pointer_binding = _typed_body(pointer_bytes)
    pointer_body = {key: value for key, value in pointer.items() if key not in {"active_pointer_digest", "signature"}}
    inputs["active_pointer_artifact"] = _typed_signed({**pointer_body, "release_digest": forged["release_digest"]}, domain=b"memorii:sia-traceability-active-release-pointer:v1", digest_field="active_pointer_digest", binding=pointer_binding)
    _, history_binding = _typed_body(inputs["release_history_artifact"])
    inputs["release_history_artifact"] = serialize_artifact(json.loads(_release_history(forged)), history_binding)
    path = tmp_path / "acceptance-watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, forged["release_digest"]), WatermarkAdvanced)
    record_before = path.read_bytes()
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    seal_before = seal.read_bytes()
    with pytest.raises(
        ExecutionEvidenceError,
        match="release_history_invalid",
    ):
        _registered_call(
            inputs,
            AcceptanceTrustStore(
                inputs["verifier_material"], store, inputs["expected_release_roots"],
                allow_test_watermark_fallback=True,
            ),
        )
    assert path.read_bytes() == record_before
    assert seal.read_bytes() == seal_before


def test_public_acceptance_successor_reopen_rejects_valid_historical_147_release(tmp_path: Path) -> None:
    genesis = _approval_inputs("semantic-ingestion-r03")
    inputs = _successor_inputs("semantic-ingestion-r03")
    path = tmp_path / "watermark.json"
    authority = _provisioned_authority(inputs, path)[0]
    assert _registered_call(inputs, authority)["command_id"]
    reopened = replace(authority, watermark_store=FileTraceabilityReleaseWatermarkStore(path))
    assert _registered_call(inputs, reopened)["command_id"]
    with pytest.raises(ExecutionEvidenceError, match="active_pointer_watermark_rewind"):
        _registered_call(genesis, replace(reopened, expected_release_roots=genesis["expected_release_roots"]))


@pytest.mark.parametrize("mutation", ["root", "lifecycle", "report", "profile"])
def test_registered_normative_approval_rejects_root_report_profile_and_lifecycle_mutations(mutation: str) -> None:
    inputs = _approval_inputs("semantic-ingestion-r03")
    if mutation == "root":
        assert isinstance(inputs["release_artifact"], bytes)
        inputs["release_artifact"] += b" "
    elif mutation == "lifecycle":
        assert isinstance(inputs["lifecycle_artifact"], bytes)
        inputs["lifecycle_artifact"] += b" "
    elif mutation == "report":
        assert isinstance(inputs["report_bytes"], bytes)
        inputs["report_bytes"] += b" "
    else:
        assert isinstance(inputs["environment_observation_bytes"], bytes)
        environment = json.loads(inputs["environment_observation_bytes"])
        environment["plugins"] = {"forged": True}
        inputs["environment_observation_bytes"] = canonical_document(environment)
    with pytest.raises(ExecutionEvidenceError):
        _approve(inputs)


def test_sia_r03_acceptance() -> None:
    """Registered R03 coordinate: approve a complete signed generation."""
    assert _approve(_approval_inputs("semantic-ingestion-r03"))["command_id"] == "pytest-sia-r03-v1"


def test_sia_r13_acceptance() -> None:
    """Registered R13 coordinate: trust is composition-owned, never request-owned."""
    inputs = _approval_inputs("semantic-ingestion-r13")
    assert _approve(inputs)["command_id"] == "pytest-sia-r13-v1"
