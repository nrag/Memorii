"""Trusted, revision-bound execution-evidence verification for SIA-R03.

The verifier is deliberately separate from structural extraction.  Parser
agreement is accepted only as a precondition and cannot make execution pass.
"""

from __future__ import annotations

import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from memorii.tools.semantic_ingestion_traceability import UnitRequirementMapping
from memorii.tools.semantic_ingestion_traceability_registry import canonical_document
from memorii.tools.semantic_ingestion_traceability_release import TraceabilityGateAuthorized


class ExecutionEvidenceError(ValueError):
    """Raised when execution evidence cannot safely approve a mapping."""


@dataclass(frozen=True)
class ExecutionEvidenceRecord:
    unit_content_keys: tuple[str, ...]
    requirement_ids: tuple[str, ...]
    assertion_id: str
    assertion_version: int
    test_evidence_group: str
    test_artifact_digest: str
    design_document_digest: str
    implementation_revision: str
    implementation_tree_digest: str
    execution_id: str
    execution_status: str
    execution_result: str
    result_artifact_digest: str | None
    issued_at: datetime
    issuer_id: str
    issuance_purpose: str
    trust_context_digest: str
    expires_at: datetime | None
    signature: str

    def signing_payload(self) -> bytes:
        data = {name: getattr(self, name) for name in self.__dataclass_fields__ if name != "signature"}
        data["issued_at"] = self.issued_at.isoformat()
        data["expires_at"] = self.expires_at.isoformat() if self.expires_at else None
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_record(record: ExecutionEvidenceRecord, signing_secret: bytes) -> str:
    """Legacy test-record helper; it is not accepted by the approval path."""
    return hmac.new(signing_secret, record.signing_payload(), "sha256").hexdigest()


def artifact_digest(content: bytes) -> str:
    return sha256(content).hexdigest()


def observation_digest(observation_bytes: bytes) -> str:
    """Domain-separate runner-environment observations from generic artifacts."""
    return sha256(b"memorii:sia-traceability-runner-observation:v1\0" + observation_bytes).hexdigest()


def verify_release_bound_execution(
    *,
    report_bytes: bytes,
    artifacts: dict[str, bytes],
    group: dict[str, object],
    registry_source_identity: str,
    structural_manifest_digest: str,
    design_document_digest: str,
    implementation_revision: str,
    implementation_tree_digest: str,
    release: TraceabilityGateAuthorized | None,
    environment_observation_bytes: bytes,
) -> dict[str, object]:
    """Approval-capable evidence entry point.

    No caller key, HMAC, or ad-hoc success record can authorize this path: a
    lifecycle-verified release and the registered immutable runner report are
    both required before its report is returned to coverage verification.
    """
    if release is None:
        raise ExecutionEvidenceError("release authority is unavailable")
    report = verify_registered_runner_report(
        report_bytes=report_bytes,
        artifacts=artifacts,
        group=group,
        registry_source_identity=registry_source_identity,
        structural_manifest_digest=structural_manifest_digest,
        design_document_digest=design_document_digest,
        implementation_revision=implementation_revision,
        implementation_tree_digest=implementation_tree_digest,
    )
    observation_artifact = report.get("runner_environment_observation_artifact_digest")
    if not isinstance(observation_artifact, str) or artifacts.get(observation_artifact) != environment_observation_bytes:
        raise ExecutionEvidenceError("runner environment observation bytes are unavailable")
    if report.get("runner_environment_observation_digest") != observation_digest(environment_observation_bytes):
        raise ExecutionEvidenceError("runner environment observation digest is invalid")
    return report


def verify_registered_runner_report(
    *,
    report_bytes: bytes,
    artifacts: dict[str, bytes],
    group: dict[str, object],
    registry_source_identity: str,
    structural_manifest_digest: str,
    design_document_digest: str,
    implementation_revision: str,
    implementation_tree_digest: str,
) -> dict[str, object]:
    """Verify immutable report bytes against the registry, before evidence can use it.

    This deliberately implements the report's closed schema locally rather than
    accepting a caller's success-shaped JSON object or a JSON-schema library's
    permissive defaults.
    """
    try:
        report = json.loads(report_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExecutionEvidenceError("runner report is not UTF-8 JSON") from exc
    if not isinstance(report, dict) or canonical_document(report) != report_bytes:
        raise ExecutionEvidenceError("runner report is not canonical immutable bytes")
    command = group.get("command")
    selected = group.get("selected_tests")
    if not isinstance(command, dict) or not isinstance(selected, list):
        raise ExecutionEvidenceError("registered group is malformed")
    required = {
        "schema_id",
        "schema_version",
        "command_id",
        "argv",
        "working_directory",
        "selected_test_ids",
        "collected_test_ids",
        "tests",
        "exit_code",
        "runner_id",
        "runner_version",
        "loaded_report_schema_digest",
        "loaded_runner_environment_profile_digest",
        "runner_environment_observation_digest",
        "design_document_digest",
        "registry_source_identity",
        "structural_manifest_digest",
        "implementation_revision",
        "implementation_tree_digest",
        "started_at",
        "finished_at",
        "stdout_artifact_digest",
        "stderr_artifact_digest",
        "runner_environment_observation_artifact_digest",
    }
    if set(report) != required:
        raise ExecutionEvidenceError("runner report has unknown or missing fields")
    expected_ids = [item.get("test_id") for item in selected if isinstance(item, dict)]
    expected_nodes = [item.get("pytest_node_id") for item in selected if isinstance(item, dict)]
    if (report["command_id"], report["argv"], report["working_directory"]) != (
        command.get("command_id"),
        command.get("argv"),
        command.get("working_directory"),
    ):
        raise ExecutionEvidenceError("runner report command is not registered")
    if (
        report["selected_test_ids"] != expected_ids
        or report["collected_test_ids"] != expected_ids
        or report["exit_code"] != 0
    ):
        raise ExecutionEvidenceError("selected tests were skipped, xfailed, deselected, or not all collected")
    tests = report["tests"]
    if not isinstance(tests, list) or len(tests) != len(expected_ids):
        raise ExecutionEvidenceError("runner report test results are incomplete")
    if [
        (item.get("test_id"), item.get("node_id"), item.get("outcome")) for item in tests if isinstance(item, dict)
    ] != list(zip(expected_ids, expected_nodes, ["passed"] * len(expected_ids), strict=True)):
        raise ExecutionEvidenceError("runner report result order or outcomes differ from registry")
    bindings = {
        "design_document_digest": design_document_digest,
        "registry_source_identity": registry_source_identity,
        "structural_manifest_digest": structural_manifest_digest,
        "implementation_revision": implementation_revision,
        "implementation_tree_digest": implementation_tree_digest,
        "loaded_report_schema_digest": group.get("expected_report_schema_digest"),
        "loaded_runner_environment_profile_digest": group.get("expected_runner_environment_profile_digest"),
    }
    if any(report.get(key) != value for key, value in bindings.items()):
        raise ExecutionEvidenceError("runner report root binding differs from registered value")
    for digest in [
        report["stdout_artifact_digest"],
        report["stderr_artifact_digest"],
        report["runner_environment_observation_artifact_digest"],
    ] + [item.get("result_artifact_digest") for item in tests]:
        if digest is not None and (
            not isinstance(digest, str) or artifacts.get(digest) is None or artifact_digest(artifacts[digest]) != digest
        ):
            raise ExecutionEvidenceError("runner report artifact is unavailable or digest-mismatched")
    return report


def verify_execution_evidence(
    *,
    mappings: tuple[UnitRequirementMapping, ...],
    records: tuple[ExecutionEvidenceRecord, ...],
    artifacts: dict[str, bytes],
    expected_design_digest: str,
    expected_implementation_revision: str,
    expected_implementation_tree_digest: str,
    expected_trust_context_digest: str,
    trusted_issuers: dict[str, bytes],
    now: datetime,
) -> None:
    """Require one fresh, trusted, passing record for every mapping."""

    if now.tzinfo is None:
        raise ExecutionEvidenceError("verification time must be timezone-aware")
    for mapping in mappings:
        applicable = [
            record
            for record in records
            if mapping.content_key in record.unit_content_keys
            and mapping.requirement_id in record.requirement_ids
            and mapping.assertion_id == record.assertion_id
            and mapping.assertion_version == record.assertion_version
            and mapping.test_evidence_group == record.test_evidence_group
        ]
        if len(applicable) != 1:
            raise ExecutionEvidenceError("each mapping requires exactly one applicable evidence record")
        record = applicable[0]
        secret = trusted_issuers.get(record.issuer_id)
        if secret is None:
            raise ExecutionEvidenceError("evidence issuer is not trusted")
        if record.issuance_purpose != "semantic_ingestion_normative_evidence":
            raise ExecutionEvidenceError("evidence has the wrong issuance purpose")
        if record.execution_status != "executed" or record.execution_result != "pass":
            raise ExecutionEvidenceError("evidence was not a passing execution")
        if record.design_document_digest != expected_design_digest:
            raise ExecutionEvidenceError("evidence has a stale or wrong design digest")
        if record.implementation_revision != expected_implementation_revision:
            raise ExecutionEvidenceError("evidence has the wrong implementation revision")
        if record.implementation_tree_digest != expected_implementation_tree_digest:
            raise ExecutionEvidenceError("evidence has the wrong implementation tree digest")
        if record.trust_context_digest != expected_trust_context_digest:
            raise ExecutionEvidenceError("evidence has the wrong trust context")
        if record.issued_at > now:
            raise ExecutionEvidenceError("evidence was issued in the future")
        if record.expires_at is not None and record.expires_at < now:
            raise ExecutionEvidenceError("evidence has expired")
        if record.test_artifact_digest not in artifacts or record.result_artifact_digest not in artifacts:
            raise ExecutionEvidenceError("evidence artifacts are not loadable")
        if artifact_digest(artifacts[record.test_artifact_digest]) != record.test_artifact_digest:
            raise ExecutionEvidenceError("test artifact digest does not match persisted bytes")
        if artifact_digest(artifacts[record.result_artifact_digest]) != record.result_artifact_digest:
            raise ExecutionEvidenceError("result artifact digest does not match persisted bytes")
        if not hmac.compare_digest(record.signature, sign_record(record, secret)):
            raise ExecutionEvidenceError("evidence signature is forged or corrupt")
