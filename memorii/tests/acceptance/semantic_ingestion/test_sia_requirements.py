"""End-to-end registered R03/R13 approval coordinates."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from memorii.tools.semantic_ingestion_execution_evidence import (
    ExecutionEvidenceError,
    artifact_digest,
    observation_digest,
    verify_registered_approval_execution,
)
from memorii.tools.semantic_ingestion_traceability_registry import (
    TraceabilityRegistry,
    canonical_document,
    load_registry,
)
from memorii.tools.semantic_ingestion_traceability_release import VerifierHeldTrustMaterial


def _registry_path() -> Path:
    return Path(__file__).parents[4] / "docs" / "design" / "semantic_ingestion" / "traceability_registry" / "registry-v1.json"


def _signature(profile: str, key: str, payload: bytes) -> bytes:
    return sha256(b"memorii:acceptance-verifier:v1\0" + profile.encode() + b"\0" + key.encode() + b"\0" + payload).digest()


def _verifier(profile: str, key: str, payload: bytes, signature: bytes) -> bool:
    return signature == _signature(profile, key, payload)


def _signed(body: dict[str, object], *, domain: bytes, digest_field: str, key: str = "bootstrap-key") -> bytes:
    digest = sha256(domain + b"\0" + canonical_document(body)).hexdigest()
    return canonical_document({**body, digest_field: digest, "signature": _signature("deterministic-v1", key, digest.encode("ascii")).hex()})


def _approval_inputs(group_id: str) -> dict[str, object]:
    registry_path = _registry_path()
    raw = registry_path.read_bytes()
    registry = load_registry(registry_path)
    group = next(item for item in registry.source["test_evidence_groups"] if item["group_id"] == group_id)
    now = datetime(2026, 1, 2, tzinfo=UTC)
    bootstrap = _signed({"anchor_id": "bootstrap", "issuance_purpose": "semantic_ingestion_traceability_release_root", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "public_key_or_root_certificate_digest": "bootstrap-key", "target_authority_id": "authority"}, domain=b"memorii:sia-traceability-bootstrap-anchor:v1", digest_field="anchor_digest")
    bootstrap_value = json.loads(bootstrap)
    recovery = _signed({"recovery_root_id": "recovery", "issuance_purpose": "semantic_ingestion_traceability_recovery_root", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "public_key_or_root_certificate_digest": "recovery-key", "target_authority_id": "authority"}, domain=b"memorii:sia-traceability-recovery-root:v1", digest_field="recovery_root_digest", key="recovery-key")
    recovery_value = json.loads(recovery)
    policy = _signed({"issuance_purpose": "semantic_ingestion_traceability_recovery_policy", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "policy_signer_key_or_certificate_digest": "bootstrap-key", "active_bootstrap_anchor_digest": bootstrap_value["anchor_digest"], "eligible_recovery_root_digests": [recovery_value["recovery_root_digest"]], "threshold": 1}, domain=b"memorii:sia-traceability-recovery-policy:v1", digest_field="recovery_policy_digest")
    record_body: dict[str, object] = {"issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle", "sequence": 1, "predecessor_record_digest": None, "effective_at": "2026-01-01T00:00:00Z", "recorded_at": "2026-01-01T00:00:01Z", "action": "activate", "target_id": "bootstrap", "target_digest": bootstrap_value["anchor_digest"], "replacement_target_id": None, "replacement_target_digest": None, "signer_bindings": [{"signer_id": "bootstrap", "signature_profile_id": "deterministic-v1", "key_digest": "bootstrap-key"}]}
    record_digest = sha256(b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(record_body)).hexdigest()
    record = {**record_body, "record_digest": record_digest, "signatures": [_signature("deterministic-v1", "bootstrap-key", record_digest.encode("ascii")).hex()]}
    lifecycle_body = {"authority_id": "authority", "records": [record]}
    lifecycle_digest = sha256(b"memorii:sia-traceability-trust-lifecycle-root:v1\0" + canonical_document(lifecycle_body)).hexdigest()
    lifecycle = canonical_document({**lifecycle_body, "lifecycle_root_digest": lifecycle_digest, "signature": _signature("deterministic-v1", "bootstrap-key", lifecycle_digest.encode("ascii")).hex()})
    roots = {"registry_source_identity": registry.source_identity, **{f"{name}_digest": digest for name, digest in registry.root_digests.items()}, "design_document_digest": "d" * 64, "structural_manifest_digest": "1" * 64, "coverage_root_digest": "c" * 64, "execution_root_digest": "e" * 64, "report_schema_registry_digest": "a" * 64, "runner_environment_profile_registry_digest": "b" * 64, "trust_snapshot_digest": "f" * 64}
    release = _signed({"release_id": f"{group_id}-release", "issuance_purpose": "semantic_ingestion_traceability_release", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "issuer_key_or_certificate_digest": "bootstrap-key", "grammar_revision": registry.source["grammar_revision"], "state": "active", "predecessor_release_id": None, "supersedes_release_id": None, "bootstrap_anchor_digest": bootstrap_value["anchor_digest"], "recovery_root_digest": recovery_value["recovery_root_digest"], "issued_at": "2026-01-01T00:00:02Z", "expires_at": (now + timedelta(days=1)).isoformat(), "epoch": 1, "sequence": 1, **roots}, domain=b"memorii:sia-traceability-release:v1", digest_field="release_digest")
    release_value = json.loads(release)
    pointer = _signed({"release_id": release_value["release_id"], "release_digest": release_value["release_digest"], "epoch": 1, "sequence": 1, "signature_profile_id": "deterministic-v1", "issuer_key_or_certificate_digest": "bootstrap-key"}, domain=b"memorii:sia-traceability-active-release-pointer:v1", digest_field="active_pointer_digest")
    profile = registry.source["runner_environment_profiles"][0]
    environment = canonical_document({"interpreter": profile["interpreter_policy"], "runner": profile["runner_policy"], "plugins": profile["plugin_policy"], "configuration": profile["configuration_policy"], "dependencies": profile["dependency_policy"], "import_paths": profile["import_path_policy"], "startup": profile["startup_customization_policy"], "environment": profile["environment_policy"], "locale_timezone": profile["locale_timezone_policy"], "network": profile["network_policy"]})
    passed = b"passed"
    passed_digest = artifact_digest(passed)
    environment_digest = artifact_digest(environment)
    selected = group["selected_tests"]
    report = {"schema_id": group["report_schema_id"], "schema_version": group["report_schema_version"], "command_id": group["command"]["command_id"], "argv": group["command"]["argv"], "working_directory": group["command"]["working_directory"], "selected_test_ids": [item["test_id"] for item in selected], "collected_test_ids": [item["test_id"] for item in selected], "tests": [{"test_id": item["test_id"], "node_id": item["pytest_node_id"], "outcome": "passed", "result_artifact_digest": passed_digest} for item in selected], "exit_code": 0, "runner_id": "cpython-pytest", "runner_version": "8.0", "loaded_report_schema_digest": group["expected_report_schema_digest"], "loaded_runner_environment_profile_digest": group["expected_runner_environment_profile_digest"], "runner_environment_observation_digest": observation_digest(environment), **{key: roots[key] for key in ("design_document_digest", "registry_source_identity", "structural_manifest_digest")}, "implementation_revision": "acceptance-revision", "implementation_tree_digest": "a" * 64, "started_at": "2026-01-01T00:00:00Z", "finished_at": "2026-01-01T00:00:01Z", "stdout_artifact_digest": None, "stderr_artifact_digest": None, "runner_environment_observation_artifact_digest": environment_digest}
    return {"registry_bytes": raw, "registry": registry, "group_id": group_id, "report_bytes": canonical_document(report), "artifacts": {passed_digest: passed, environment_digest: environment}, "implementation_revision": "acceptance-revision", "implementation_tree_digest": "a" * 64, "environment_observation_bytes": environment, "bootstrap_artifact": bootstrap, "recovery_artifact": recovery, "lifecycle_artifact": lifecycle, "release_artifact": release, "active_pointer_artifact": pointer, "release_history_artifact": canonical_document({"releases": [release_value]}), "verifier_material": VerifierHeldTrustMaterial(bootstrap, (recovery,), _verifier, policy), "now": now}


def _approve(inputs: dict[str, object]) -> dict[str, object]:
    required_bytes = (
        "registry_bytes", "report_bytes", "environment_observation_bytes", "bootstrap_artifact",
        "recovery_artifact", "lifecycle_artifact", "release_artifact", "active_pointer_artifact",
        "release_history_artifact",
    )
    if any(not isinstance(inputs[name], bytes) for name in required_bytes):
        raise AssertionError("acceptance fixture has a non-byte artifact")
    registry = inputs["registry"]
    material = inputs["verifier_material"]
    if not isinstance(registry, TraceabilityRegistry) or not isinstance(material, VerifierHeldTrustMaterial):
        raise AssertionError("acceptance fixture has invalid trust material")
    group_id, revision, tree_digest, now = inputs["group_id"], inputs["implementation_revision"], inputs["implementation_tree_digest"], inputs["now"]
    if not isinstance(group_id, str) or not isinstance(revision, str) or not isinstance(tree_digest, str) or not isinstance(now, datetime):
        raise AssertionError("acceptance fixture has invalid scalar input")
    artifacts = inputs["artifacts"]
    if not isinstance(artifacts, dict) or not all(isinstance(key, str) and isinstance(value, bytes) for key, value in artifacts.items()):
        raise AssertionError("acceptance fixture has invalid artifact map")
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
    return verify_registered_approval_execution(registry_bytes=registry_bytes, registry=registry, group_id=group_id, report_bytes=report_bytes, artifacts=artifacts, implementation_revision=revision, implementation_tree_digest=tree_digest, environment_observation_bytes=environment_bytes, bootstrap_artifact=bootstrap, recovery_artifact=recovery, lifecycle_artifact=lifecycle, release_artifact=release, active_pointer_artifact=pointer, release_history_artifact=history, verifier_material=material, now=now)


@pytest.mark.parametrize("group_id", ["semantic-ingestion-r03", "semantic-ingestion-r13"])
def test_registered_normative_approval_accepts_signed_provisioned_generation(group_id: str) -> None:
    assert _approve(_approval_inputs(group_id))["command_id"]


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
