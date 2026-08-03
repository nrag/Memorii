"""Deterministic trust material used only by semantic-ingestion tests.

This module is intentionally not wired into application composition.  It makes
the acceptance fixture's authority explicit, with a distinct test root, so a
scenario package can prove the release boundary without making test trust a
default trust source.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from hashlib import sha256
from typing import Any, cast

from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueProfileBinding,
    artifact_preimage,
    decode_artifact,
    decode_typed_value,
    encode_typed_value,
    serialize_artifact,
)
from memorii.tools.semantic_ingestion_execution_evidence import (
    artifact_digest,
    observation_digest,
    structural_verification_spool,
)
from memorii.tools.semantic_ingestion_structural_ledger import (
    load_checked_in_frozen_structural_manifest_ledger,
)
from memorii.tools.semantic_ingestion_traceability_checker import (
    rebuild_structural_manifest_bytes,
)
from memorii.tools.semantic_ingestion_traceability_registry import (
    canonical_document,
    load_registry_bytes,
)
from memorii.tools.semantic_ingestion_traceability_release import (
    IndependentGenerationVerificationResult,
    VerifierHeldTrustMaterial,
)


class ExplicitTestIndependentGenerationVerifier:
    """Test-composition fake; candidate request bytes cannot install it."""

    def __init__(self, result: IndependentGenerationVerificationResult) -> None:
        self._result = result

    def verify(self, **_: object) -> IndependentGenerationVerificationResult:
        return self._result

    @property
    def result(self) -> IndependentGenerationVerificationResult:
        return self._result

PROFILE_ID = "semantic_ingestion_typed_value"
PROFILE_VERSION = 2
PROFILE_DIGEST = "9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f"
TEST_BOOTSTRAP_KEY = "scenario-first-closure-test-bootstrap-key"
TEST_RECOVERY_KEY = "scenario-first-closure-test-recovery-key"

# The registered semantic ingestion package is a closed 18-member CTV-v2/raw-ledger closure.
# Keep this local to the fixture producer rather than importing the execution
# verifier's private order, which would make the test fixture an oracle.
CURRENT_GENERATION_MEMBER_ORDER = (
    "design_document",
    "registry_source",
    "structural_manifest_derivation_ledger",
    "bootstrap_anchor",
    "recovery_root",
    "recovery_policy",
    "bootstrap_anchor_history",
    "recovery_root_history",
    "recovery_policy_history",
    "trust_lifecycle_root",
    "trust_snapshot",
    "structural_manifest",
    "coverage_root",
    "execution_root",
    "golden_vector_manifest",
    "release",
    "release_history",
    "pointer_history",
)


def _signature(profile: str, key: str, payload: bytes) -> bytes:
    return sha256(
        b"memorii:acceptance-verifier:v1\0"
        + profile.encode()
        + b"\0"
        + key.encode()
        + b"\0"
        + payload
    ).digest()


def verifier(profile: str, key: str, payload: bytes, signature: bytes) -> bool:
    return signature == _signature(profile, key, payload)


def _signed(
    body: dict[str, object], *, domain: bytes, digest_field: str, key: str
) -> dict[str, object]:
    digest = sha256(domain + b"\0" + canonical_document(body)).hexdigest()
    return {
        **body,
        digest_field: digest,
        "signature": _signature("deterministic-v1", key, digest.encode("ascii")).hex(),
    }


def _binding(authority: dict[str, object], schema_id: str) -> CanonicalTypedValueProfileBinding:
    profile = authority.get("profile")
    schemas = authority.get("schemas")
    if not isinstance(profile, dict) or not isinstance(schemas, list):
        raise ValueError("invalid CTV authority")
    matches = [item for item in schemas if isinstance(item, dict) and item.get("coordinate") == schema_id]
    if len(matches) != 1 or profile.get("id") != PROFILE_ID or profile.get("version") != PROFILE_VERSION or profile.get("digest") != PROFILE_DIGEST:
        raise ValueError(f"unregistered CTV binding: {schema_id}")
    digest = matches[0].get("binding_digest")
    if not isinstance(digest, str):
        raise ValueError(f"invalid CTV binding: {schema_id}")
    return CanonicalTypedValueProfileBinding(PROFILE_ID, PROFILE_VERSION, PROFILE_DIGEST, schema_id, 1, digest)


def _typed(authority: dict[str, object], value: dict[str, object], schema_id: str) -> bytes:
    return serialize_artifact(value, _binding(authority, schema_id))


def _structural_artifact(
    authority: dict[str, object], canonical_body: bytes, structural_digest: str
) -> bytes:
    """Add the terminal structural digest without re-encoding the huge CTV tree."""
    marker = b'["structural_mapping_rule_registry_digest",'
    offset = canonical_body.rfind(marker)
    if offset < 0:
        raise ValueError("scenario structural body lacks its structural mapping root")
    entry = (
        b'["structural_manifest_digest","'
        + structural_digest.encode("ascii")
        + b'"],'
    )
    body = canonical_body[:offset] + entry + canonical_body[offset:]
    binding = _binding(authority, "NormativeTraceabilityStructuralManifestBody.v1")
    value_digest = sha256(body).hexdigest()
    return encode_typed_value(
        {
            "binding": binding.as_value(),
            "canonical_value_bytes": body,
            "canonical_value_digest": value_digest,
            "artifact_digest": sha256(artifact_preimage(binding, body)).hexdigest(),
        }
    )


def _declared_digest(domain: bytes, body: dict[str, object]) -> str:
    return sha256(domain + b"\0" + encode_typed_value(body)).hexdigest()


@lru_cache(maxsize=4)
def _structural_bytes(design_bytes: bytes, registry_bytes: bytes) -> tuple[Any, bytes]:
    registry = load_registry_bytes(registry_bytes)
    return registry, rebuild_structural_manifest_bytes(
        design_bytes=design_bytes, registry=registry, registry_bytes=registry_bytes
    )


def _history(release: dict[str, object]) -> dict[str, object]:
    entry_body: dict[str, object] = {
        "entry_id": "scenario-first-closure-entry-1", "sequence": 1, "predecessor_entry_digest": None,
        "release_id": release["release_id"], "release_digest": release["release_digest"],
        "release_epoch": release["epoch"], "release_sequence": release["sequence"],
        "prior_active_release_digest": None, "prior_release_terminal_state": None,
        "effective_at": release["issued_at"],
    }
    entry = {**entry_body, "entry_digest": sha256(b"memorii:sia-traceability-release-history-entry:v1\0" + canonical_document(entry_body)).hexdigest()}
    return _signed(
        {"history_id": "scenario-first-closure-history", "issuance_purpose": "semantic_ingestion_traceability_release_history", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "issuer_key_or_certificate_digest": TEST_BOOTSTRAP_KEY, "entries": [entry]},
        domain=b"memorii:sia-traceability-release-history:v1", digest_field="release_history_digest", key=TEST_BOOTSTRAP_KEY,
    )


def build_scenario_test_authority(
    *, design_bytes: bytes, registry_bytes: bytes, authority_bytes: bytes, group_id: str
) -> dict[str, object]:
    """Build CTV-v2 release inputs using an intentionally non-production root."""
    authority = json.loads(authority_bytes)
    registry, structural = _structural_bytes(design_bytes, registry_bytes)
    source = registry.source
    groups = [item for item in source["test_evidence_groups"] if item["group_id"] == group_id]
    if len(groups) != 1:
        raise ValueError("registered evidence group unavailable")
    group = groups[0]
    # Verification occurs after the fixed release and lifecycle records.
    now = datetime(2026, 7, 30, 0, 1, tzinfo=UTC)
    bootstrap_value = _signed(
        {"anchor_id": "scenario-first-closure-bootstrap", "issuance_purpose": "semantic_ingestion_traceability_release_root", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "public_key_or_root_certificate_digest": TEST_BOOTSTRAP_KEY, "target_authority_id": "scenario-first-closure-test-authority"},
        domain=b"memorii:sia-traceability-bootstrap-anchor:v1", digest_field="anchor_digest", key=TEST_BOOTSTRAP_KEY,
    )
    recovery_value = _signed(
        {"recovery_root_id": "scenario-first-closure-recovery", "issuance_purpose": "semantic_ingestion_traceability_recovery_root", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "public_key_or_root_certificate_digest": TEST_RECOVERY_KEY, "target_authority_id": "scenario-first-closure-test-authority"},
        domain=b"memorii:sia-traceability-recovery-root:v1", digest_field="recovery_root_digest", key=TEST_RECOVERY_KEY,
    )
    policy_value = _signed(
        {"issuance_purpose": "semantic_ingestion_traceability_recovery_policy", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "policy_signer_key_or_certificate_digest": TEST_BOOTSTRAP_KEY, "active_bootstrap_anchor_digest": bootstrap_value["anchor_digest"], "eligible_recovery_root_digests": [recovery_value["recovery_root_digest"]], "threshold": 1},
        domain=b"memorii:sia-traceability-recovery-policy:v1", digest_field="recovery_policy_digest", key=TEST_BOOTSTRAP_KEY,
    )
    record_body: dict[str, object] = {"issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle", "sequence": 1, "predecessor_record_digest": None, "effective_at": "2026-07-30T00:00:00Z", "recorded_at": "2026-07-30T00:00:01Z", "action": "activate", "target_id": "scenario-first-closure-bootstrap", "target_digest": bootstrap_value["anchor_digest"], "replacement_target_id": None, "replacement_target_digest": None, "signer_bindings": [{"signer_id": "scenario-first-closure-bootstrap", "signature_profile_id": "deterministic-v1", "key_digest": TEST_BOOTSTRAP_KEY}]}
    record_digest = sha256(b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(record_body)).hexdigest()
    lifecycle_value = {"authority_id": "scenario-first-closure-test-authority", "records": [{**record_body, "record_digest": record_digest, "signatures": [_signature("deterministic-v1", TEST_BOOTSTRAP_KEY, record_digest.encode("ascii")).hex()]}]}
    lifecycle_value = {**lifecycle_value, "lifecycle_root_digest": sha256(b"memorii:sia-traceability-trust-lifecycle-root:v1\0" + canonical_document(lifecycle_value)).hexdigest()}
    lifecycle_value["signature"] = _signature("deterministic-v1", TEST_BOOTSTRAP_KEY, lifecycle_value["lifecycle_root_digest"].encode("ascii")).hex()
    ledger = load_checked_in_frozen_structural_manifest_ledger()
    structural_digest = sha256(
        ledger.domain("structural_body")
        + len(structural).to_bytes(8, "big")
        + structural
    ).hexdigest()
    design_digest = sha256(
        b"semantic-ingestion-traceability\0" + design_bytes
    ).hexdigest()
    coverage = {"structural_manifest_digest": structural_digest, "approvals": []}
    coverage["coverage_root_digest"] = sha256(b"memorii:sia-traceability-coverage-root:v1\0" + encode_typed_value(coverage)).hexdigest()
    execution = {"structural_manifest_digest": structural_digest, "evidence_records": []}
    execution["execution_root_digest"] = sha256(b"memorii:sia-traceability-execution-root:v1\0" + encode_typed_value(execution)).hexdigest()
    history_bodies = {
        "bootstrap_anchor_history": {"history_id": "scenario-first-closure-bootstrap-history", "canonical_profile_binding": _binding(authority, "TraceabilityBootstrapAnchorHistoryBody.v1").as_value(), "anchors": [bootstrap_value]},
        "recovery_root_history": {"history_id": "scenario-first-closure-recovery-history", "canonical_profile_binding": _binding(authority, "TraceabilityRecoveryRootHistoryBody.v1").as_value(), "recovery_roots": [recovery_value]},
        "recovery_policy_history": {"history_id": "scenario-first-closure-policy-history", "canonical_profile_binding": _binding(authority, "TraceabilityRecoveryPolicyHistoryBody.v1").as_value(), "policies": [policy_value]},
    }
    history_domains = {"bootstrap_anchor_history": ("TraceabilityBootstrapAnchorHistoryBody.v1", b"memorii:sia-traceability-bootstrap-anchor-history:v1\0", "history_digest"), "recovery_root_history": ("TraceabilityRecoveryRootHistoryBody.v1", b"memorii:sia-traceability-recovery-root-history:v1\0", "history_digest"), "recovery_policy_history": ("TraceabilityRecoveryPolicyHistoryBody.v1", b"memorii:sia-traceability-recovery-policy-history:v1\0", "history_digest")}
    history_values = {name: {**body, field: _declared_digest(domain[:-1], body)} for name, body in history_bodies.items() for _, domain, field in (history_domains[name],)}
    release_id = f"scenario-first-closure-{group_id}-release"
    qualified_issuer = {"signature_purpose": "semantic_ingestion_traceability_release", "issuer_id": "scenario-first-closure-bootstrap", "key_or_certificate_digest": TEST_BOOTSTRAP_KEY, "signature_profile_id": "deterministic-v1", "trust_lifecycle_root_digest": lifecycle_value["lifecycle_root_digest"], "lifecycle_record_digest": record_digest, "eligible_not_before": "0001-01-01T00:00:00+00:00", "eligible_not_after": None, "eligibility_derivation": {"trust_lifecycle_root_digest": lifecycle_value["lifecycle_root_digest"], "terminal_record_digest": record_digest, "terminal_sequence": 1, "target_id": "scenario-first-closure-bootstrap", "target_digest": bootstrap_value["anchor_digest"], "eligible_not_before": "0001-01-01T00:00:00+00:00", "eligible_not_after": None}}
    snapshot_body = {"snapshot_id": "scenario-first-closure-snapshot", "issuance_purpose": "semantic_ingestion_traceability_release_trust_snapshot", "canonical_profile_binding": _binding(authority, "TraceabilityReleaseTrustSnapshotBody.v1").as_value(), "release_id": release_id, "release_epoch": 1, "release_sequence": 1, "bootstrap_anchor_digest": bootstrap_value["anchor_digest"], "recovery_policy_digest": policy_value["recovery_policy_digest"], "trust_lifecycle_root_digest": lifecycle_value["lifecycle_root_digest"], "lifecycle_recorded_time_cutoff": "2026-07-30T00:00:01+00:00", "qualified_issuers": [qualified_issuer], "created_at": "2026-07-30T00:00:02+00:00"}
    snapshot_value = {**snapshot_body, "trust_snapshot_digest": _declared_digest(b"memorii:sia-traceability-release-trust-snapshot:v1", snapshot_body)}
    golden_body = {"manifest_id": "scenario-first-closure-golden", "manifest_version": 1, "source_path": "docs/design/semantic_ingestion/traceability_golden_vectors/v1.json", "owner": "acceptance_independent_vector_author", "authority_use": "verification_fixture_not_runtime_authority", "canonical_profile_binding": _binding(authority, "TraceabilityApprovalGoldenVectorManifestBody.v1").as_value(), "design_document_digest": design_digest, "registry_source_identity": registry.source_identity, "fixtures": [], "vectors": []}
    golden_value = {**golden_body, "golden_vector_manifest_digest": _declared_digest(b"memorii:sia-traceability-approval-golden-vectors:v1", golden_body)}
    roots = {"registry_source_identity": registry.source_identity, **{f"{name}_digest": digest for name, digest in registry.root_digests.items()}, "design_document_digest": design_digest, "structural_manifest_digest": structural_digest, "coverage_root_digest": coverage["coverage_root_digest"], "execution_root_digest": execution["execution_root_digest"], "report_schema_registry_digest": registry.root_digests["report_schemas"], "runner_environment_profile_registry_digest": registry.root_digests["runner_environment_profiles"], "trust_snapshot_digest": snapshot_value["trust_snapshot_digest"], "golden_vector_manifest_digest": golden_value["golden_vector_manifest_digest"], "bootstrap_anchor_history_digest": history_values["bootstrap_anchor_history"]["history_digest"], "recovery_root_history_digest": history_values["recovery_root_history"]["history_digest"], "recovery_policy_history_digest": history_values["recovery_policy_history"]["history_digest"]}
    release_value = _signed(
        {"release_id": release_id, "issuance_purpose": "semantic_ingestion_traceability_release", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "issuer_key_or_certificate_digest": TEST_BOOTSTRAP_KEY, "grammar_revision": source["grammar_revision"], "issued_state": "active", "predecessor_release_id": None, "supersedes_release_id": None, "bootstrap_anchor_id": bootstrap_value["anchor_id"], "bootstrap_anchor_digest": bootstrap_value["anchor_digest"], "bootstrap_rotation_sequence": 1, "recovery_root_digest": recovery_value["recovery_root_digest"], "recovery_trust_policy_digest": policy_value["recovery_policy_digest"], "recovery_trust_root_digests": [recovery_value["recovery_root_digest"]], "trust_lifecycle_root_digest": lifecycle_value["lifecycle_root_digest"], "issued_at": "2026-07-30T00:00:02Z", "expires_at": (now + timedelta(days=1)).isoformat(), "epoch": 1, "sequence": 1, **roots},
        domain=b"memorii:sia-traceability-release:v1", digest_field="release_digest", key=TEST_BOOTSTRAP_KEY,
    )
    pointer_value = _signed(
        {"issuance_purpose": "semantic_ingestion_traceability_active_release_pointer", "release_id": release_value["release_id"], "release_digest": release_value["release_digest"], "epoch": 1, "sequence": 1, "signature_profile_id": "deterministic-v1", "issuer_key_or_certificate_digest": TEST_BOOTSTRAP_KEY},
        domain=b"memorii:sia-traceability-active-release-pointer:v1", digest_field="active_pointer_digest", key=TEST_BOOTSTRAP_KEY,
    )
    typed = {
        "bootstrap_anchor": _typed(authority, bootstrap_value, "TraceabilityBootstrapTrustAnchorBody.v1"),
        "recovery_root": _typed(authority, recovery_value, "TraceabilityRecoveryTrustRootBody.v1"),
        "recovery_policy": _typed(authority, policy_value, "TraceabilityRecoveryTrustPolicyBody.v1"),
        "trust_lifecycle_root": _typed(authority, lifecycle_value, "TraceabilityTrustLifecycleRootBody.v1"),
        "structural_manifest": _structural_artifact(
            authority, structural, structural_digest
        ),
        "coverage_root": _typed(authority, coverage, "TraceabilityCoverageEvidenceRootBody.v1"),
        "execution_root": _typed(authority, execution, "TraceabilityExecutionEvidenceRootBody.v1"),
        "release": _typed(authority, release_value, "SemanticIngestionTraceabilityReleaseBody.v1"),
        "active_pointer": _typed(authority, pointer_value, "TraceabilityActiveReleasePointerBody.v1"),
        "release_history": _typed(authority, _history(release_value), "TraceabilityReleaseHistoryBody.v1"),
        **{name: _typed(authority, value, history_domains[name][0]) for name, value in history_values.items()},
        "trust_snapshot": _typed(authority, snapshot_value, "TraceabilityReleaseTrustSnapshotBody.v1"),
        "golden_vector_manifest": _typed(authority, golden_value, "TraceabilityApprovalGoldenVectorManifestBody.v1"),
    }
    profile = source["runner_environment_profiles"][0]
    environment = canonical_document({"interpreter": profile["interpreter_policy"], "runner": profile["runner_policy"], "plugins": profile["plugin_policy"], "configuration": profile["configuration_policy"], "dependencies": profile["dependency_policy"], "import_paths": profile["import_path_policy"], "startup": profile["startup_customization_policy"], "environment": profile["environment_policy"], "locale_timezone": profile["locale_timezone_policy"], "network": profile["network_policy"]})
    passed = b"passed"
    selected = group["selected_tests"]
    report = {"schema_id": group["report_schema_id"], "schema_version": group["report_schema_version"], "command_id": group["command"]["command_id"], "argv": group["command"]["argv"], "working_directory": group["command"]["working_directory"], "selected_test_ids": [item["test_id"] for item in selected], "collected_test_ids": [item["test_id"] for item in selected], "tests": [{"test_id": item["test_id"], "node_id": item["pytest_node_id"], "outcome": "passed", "result_artifact_digest": artifact_digest(passed)} for item in selected], "exit_code": 0, "runner_id": "cpython-pytest", "runner_version": "8.0", "loaded_report_schema_digest": group["expected_report_schema_digest"], "loaded_runner_environment_profile_digest": group["expected_runner_environment_profile_digest"], "runner_environment_observation_digest": observation_digest(environment), **{key: roots[key] for key in ("design_document_digest", "registry_source_identity", "structural_manifest_digest")}, "implementation_revision": "scenario-first-closure", "implementation_tree_digest": "a" * 64, "started_at": "2026-07-30T00:00:00Z", "finished_at": "2026-07-30T00:00:01Z", "stdout_artifact_digest": None, "stderr_artifact_digest": None, "runner_environment_observation_artifact_digest": artifact_digest(environment)}
    expected_root_fields = (
        "design_document_digest",
        "structural_manifest_digest",
        "coverage_root_digest",
        "execution_root_digest",
        "report_schema_registry_digest",
        "runner_environment_profile_registry_digest",
        "trust_snapshot_digest",
    )
    structural_envelope = typed["structural_manifest"]
    result = IndependentGenerationVerificationResult("memorii-sia-clean-room-b-v1", "45a8403c387c407617a3b580094177d111c8879a752eca2bff6d1786e1e61df6", structural, structural_envelope, structural_verification_spool(structural, structural_envelope))
    return {"authority": authority, "typed": typed, "roots": roots, "expected_release_roots": {key: roots[key] for key in expected_root_fields}, "report_bytes": canonical_document(report), "artifacts": {artifact_digest(passed): passed, artifact_digest(environment): environment}, "environment": environment, "material": VerifierHeldTrustMaterial(typed["bootstrap_anchor"], (typed["recovery_root"],), verifier, typed["recovery_policy"]), "now": now, "release_digest": release_value["release_digest"], "group_id": group_id, "independent_generation_verifier": ExplicitTestIndependentGenerationVerifier(result)}


def build_generation_package(
    *, built: dict[str, object], design_bytes: bytes, registry_bytes: bytes
) -> tuple[bytes, dict[str, bytes]]:
    """Produce the closed, independently addressable scenario generation package."""
    authority = built["authority"]
    typed = built["typed"]
    roots = built["roots"]
    if not isinstance(authority, dict) or not isinstance(typed, dict) or not isinstance(roots, dict):
        raise ValueError("scenario test authority is malformed")
    ledger = load_checked_in_frozen_structural_manifest_ledger()
    bootstrap = typed["bootstrap_anchor"]
    recovery = typed["recovery_root"]
    policy = typed["recovery_policy"]
    lifecycle = typed["trust_lifecycle_root"]
    release = typed["release"]
    release_history = typed["release_history"]
    if any(not isinstance(value, bytes) for value in (bootstrap, recovery, policy, lifecycle, release, release_history)):
        raise ValueError("scenario test release inputs are malformed")
    binding = _binding(authority, "TraceabilityApprovalGenerationManifestBody.v1")
    pointer_binding = _binding(authority, "TraceabilityActiveReleasePointerBody.v1")
    bootstrap_body = decode_typed_value(decode_artifact(bootstrap).canonical_value_bytes)
    recovery_body = decode_typed_value(decode_artifact(recovery).canonical_value_bytes)
    policy_body = decode_typed_value(decode_artifact(policy).canonical_value_bytes)
    lifecycle_body = decode_typed_value(decode_artifact(lifecycle).canonical_value_bytes)
    release_body = decode_typed_value(decode_artifact(release).canonical_value_bytes)
    release_history_body = decode_typed_value(decode_artifact(release_history).canonical_value_bytes)
    if not all(isinstance(value, dict) for value in (bootstrap_body, recovery_body, policy_body, lifecycle_body, release_body, release_history_body)):
        raise ValueError("scenario test release body is malformed")
    release_signer = release_body.get("signer_coordinate")
    configured_sign = built.get("sign")
    if isinstance(release_signer, dict) and callable(configured_sign):
        signer = {
            "signature_purpose": "semantic_ingestion_traceability_approval_generation",
            **{
                name: release_signer[name]
                for name in (
                    "issuer_id",
                    "key_or_certificate_digest",
                    "signature_profile_id",
                    "trust_lifecycle_root_digest",
                    "lifecycle_record_digest",
                    "eligible_not_before",
                    "eligible_not_after",
                )
            },
        }
        signature_profile = signer["signature_profile_id"]
        signature_key = signer["key_or_certificate_digest"]
        sign = cast(Callable[[str, str, bytes], bytes], configured_sign)
    else:
        signer = {
            "signature_purpose": "semantic_ingestion_traceability_approval_generation",
            "issuer_id": "scenario-first-closure-bootstrap",
            "key_or_certificate_digest": TEST_BOOTSTRAP_KEY,
            "signature_profile_id": "deterministic-v1",
            "trust_lifecycle_root_digest": lifecycle_body["lifecycle_root_digest"],
            "lifecycle_record_digest": lifecycle_body["records"][0]["record_digest"],
            "eligible_not_before": "0001-01-01T00:00:00+00:00",
            "eligible_not_after": None,
        }
        signature_profile = "deterministic-v1"
        signature_key = TEST_BOOTSTRAP_KEY
        sign = _signature
    if not isinstance(signature_profile, str) or not isinstance(signature_key, str):
        raise ValueError("scenario generation signer is malformed")
    pointer_signer = {
        **(
            release_signer
            if isinstance(release_signer, dict) and callable(configured_sign)
            else signer
        ),
        "source_kind": "prior_verified_lifecycle_root",
        "signature_purpose": "semantic_ingestion_traceability_active_release_pointer",
    }
    pointer_history_signer = {
        **pointer_signer,
        "signature_purpose": "semantic_ingestion_traceability_pointer_history",
    }
    prior_pointer_raw = built.get("prior_pointer")
    prior_pointers: list[dict[str, object]] = []
    if isinstance(prior_pointer_raw, bytes):
        prior_pointer = decode_typed_value(
            decode_artifact(prior_pointer_raw).canonical_value_bytes
        )
        if not isinstance(prior_pointer, dict):
            raise ValueError("scenario predecessor pointer is malformed")
        prior_pointers.append(prior_pointer)
    pointer_history_body = {"history_id": "scenario-first-closure-pointer-history", "issuance_purpose": "semantic_ingestion_traceability_pointer_history", "canonical_profile_binding": _binding(authority, "TraceabilityActiveReleasePointerHistoryBody.v1").as_value(), "pointers": prior_pointers, "signer_coordinate": pointer_history_signer}
    pointer_history_digest = _declared_digest(
        b"memorii:sia-traceability-pointer-history:v1", pointer_history_body
    )
    pointer_history_value = {
        **pointer_history_body,
        "pointer_history_digest": pointer_history_digest,
        "signature": sign(
            signature_profile,
            signature_key,
            encode_typed_value(
                {
                    "issuance_purpose": "semantic_ingestion_traceability_pointer_history",
                    "body_binding": _binding(
                        authority, "TraceabilityActiveReleasePointerHistoryBody.v1"
                    ).as_value(),
                    "pointer_history_digest": pointer_history_digest,
                    "signer_coordinate": pointer_history_signer,
                }
            ),
        ).hex(),
    }
    raw_by_kind = {
        "bootstrap_anchor": bootstrap, "recovery_root": recovery,
        "recovery_policy": policy, "trust_lifecycle_root": lifecycle,
        "structural_manifest": typed["structural_manifest"], "coverage_root": typed["coverage_root"],
        "execution_root": typed["execution_root"], "release": release,
        "release_history": release_history,
    }
    raw_by_kind.update({kind: typed[kind] for kind in ("bootstrap_anchor_history", "recovery_root_history", "recovery_policy_history", "trust_snapshot", "golden_vector_manifest")})
    raw_by_kind["pointer_history"] = _typed(authority, pointer_history_value, "TraceabilityActiveReleasePointerHistoryBody.v1")
    member_bytes: dict[str, bytes] = {}
    members: list[dict[str, object]] = []
    def add_raw(kind: str, raw: bytes, *, dependencies: list[str]) -> str:
        # The authority builder already produced canonical serialized member
        # bytes. Decoding authenticates their digest; re-encoding the 39 MB
        # structural member here would duplicate the dominant fixture cost.
        artifact = decode_artifact(raw)
        digest = artifact.artifact_digest
        coordinate = f"sia-traceability/v1/{kind}/{digest}"
        member_bytes[coordinate] = raw
        members.append({"artifact_kind": kind, "artifact_coordinate": coordinate, "artifact_digest": digest, "depends_on_coordinates": dependencies, "schema_id": artifact.binding.schema_id, "schema_version": 1, "binding_digest": artifact.binding.binding_digest})
        return coordinate
    design_digest = sha256(b"semantic-ingestion-traceability\0" + design_bytes).hexdigest()
    design_coordinate = f"sia-traceability/v1/design_document/{design_digest}"
    member_bytes[design_coordinate] = design_bytes
    members.append({"artifact_kind": "design_document", "artifact_coordinate": design_coordinate, "artifact_digest": design_digest, "depends_on_coordinates": [], "schema_id": "memorii.raw.design_document.v1", "schema_version": 1, "binding_digest": "raw-sha256-bytes-v1"})
    registry_identity = roots["registry_source_identity"]
    if not isinstance(registry_identity, str):
        raise ValueError("scenario registry identity is malformed")
    registry_coordinate = f"sia-traceability/v1/registry_source/{registry_identity}"
    member_bytes[registry_coordinate] = registry_bytes
    members.append({"artifact_kind": "registry_source", "artifact_coordinate": registry_coordinate, "artifact_digest": registry_identity, "depends_on_coordinates": [design_coordinate], "schema_id": "memorii.raw.registry_source.v1", "schema_version": 1, "binding_digest": "raw-sha256-bytes-v1"})
    ledger_coordinate = f"sia-traceability/v1/structural_manifest_derivation_ledger/{ledger.digest}"
    member_bytes[ledger_coordinate] = ledger.raw_bytes
    members.append({"artifact_kind": "structural_manifest_derivation_ledger", "artifact_coordinate": ledger_coordinate, "artifact_digest": ledger.digest, "depends_on_coordinates": [], "schema_id": "memorii.raw.structural_manifest_derivation_ledger.v1", "schema_version": 1, "binding_digest": "raw-sha256-bytes-v1"})
    order = CURRENT_GENERATION_MEMBER_ORDER[3:]
    dependency_kinds = {
        "bootstrap_anchor": (), "recovery_root": (), "recovery_policy": ("bootstrap_anchor", "recovery_root"),
        "bootstrap_anchor_history": ("bootstrap_anchor",), "recovery_root_history": ("recovery_root",), "recovery_policy_history": ("recovery_policy",),
        "trust_lifecycle_root": ("bootstrap_anchor_history", "recovery_root_history", "recovery_policy_history"),
        "trust_snapshot": ("trust_lifecycle_root", "bootstrap_anchor_history", "recovery_root_history", "recovery_policy_history"),
        "structural_manifest": ("design_document", "registry_source", "structural_manifest_derivation_ledger"), "coverage_root": ("structural_manifest",), "execution_root": ("structural_manifest",), "golden_vector_manifest": (),
        "release": ("bootstrap_anchor", "bootstrap_anchor_history", "recovery_root", "recovery_root_history", "recovery_policy", "recovery_policy_history", "trust_lifecycle_root", "trust_snapshot", "structural_manifest", "coverage_root", "execution_root", "golden_vector_manifest"),
        "release_history": ("release",), "pointer_history": (),
    }
    coordinates = {"design_document": design_coordinate, "registry_source": registry_coordinate, "structural_manifest_derivation_ledger": ledger_coordinate}
    for kind in order:
        raw = raw_by_kind[kind]
        if not isinstance(raw, bytes):
            raise ValueError("scenario typed member is malformed")
        coordinates[kind] = add_raw(kind, raw, dependencies=sorted(coordinates[name] for name in dependency_kinds[kind]))
    predecessor_pointer_digest = (
        prior_pointers[-1]["active_pointer_digest"] if prior_pointers else None
    )
    pointer_intent = {"pointer_id": f"scenario-first-closure-pointer-{release_body['sequence']}", "issuance_purpose": "semantic_ingestion_traceability_active_release_pointer", "target_authority_id": bootstrap_body["target_authority_id"], "canonical_profile_binding": pointer_binding.as_value(), "release_id": release_body["release_id"], "release_digest": release_body["release_digest"], "release_epoch": release_body["epoch"], "release_sequence": release_body["sequence"], "release_history_digest": release_history_body["release_history_digest"], "predecessor_pointer_history_digest": pointer_history_digest if prior_pointers else None, "predecessor_active_pointer_digest": predecessor_pointer_digest, "pointer_sequence": release_body["sequence"], "published_at": release_body["issued_at"], "signer_coordinate": pointer_signer}
    body: dict[str, object] = {"generation_id": f"scenario-first-closure-G{release_body['sequence']}", "issuance_purpose": "semantic_ingestion_traceability_approval_generation", "canonical_profile_binding": binding.as_value(), "design_document_digest": design_digest, "registry_source_identity": registry_identity, "members": members, "active_pointer_intent": pointer_intent}
    generation_digest = sha256(b"memorii:sia-traceability-approval-generation:v1\0" + encode_typed_value(body)).hexdigest()
    manifest = {**body, "signer_coordinate": signer, "generation_manifest_digest": generation_digest}
    manifest["signature"] = sign(signature_profile, signature_key, encode_typed_value({"issuance_purpose": body["issuance_purpose"], "body_binding": binding.as_value(), "generation_manifest_digest": generation_digest, "signer_coordinate": signer})).hex()
    pointer_body = {**pointer_intent, "generation_id": body["generation_id"], "generation_manifest_digest": generation_digest}
    pointer_digest = sha256(b"memorii:sia-traceability-active-release-pointer:v1\0" + encode_typed_value(pointer_body)).hexdigest()
    pointer = {**pointer_body, "active_pointer_digest": pointer_digest}
    pointer["signature"] = sign(signature_profile, signature_key, encode_typed_value({"issuance_purpose": pointer_body["issuance_purpose"], "body_binding": pointer_binding.as_value(), "active_pointer_digest": pointer_digest, "signer_coordinate": pointer_signer})).hex()
    typed["active_pointer"] = serialize_artifact(pointer, pointer_binding)
    if len(member_bytes) != len(CURRENT_GENERATION_MEMBER_ORDER):
        raise ValueError("scenario generation member closure is incomplete")
    return serialize_artifact(manifest, binding), member_bytes
