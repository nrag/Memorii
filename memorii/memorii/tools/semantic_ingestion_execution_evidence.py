"""Trusted, revision-bound execution-evidence verification for SIA-R03.

The verifier is deliberately separate from structural extraction.  Parser
agreement is accepted only as a precondition and cannot make execution pass.
"""

from __future__ import annotations

import hmac
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from memorii.tools.semantic_ingestion_traceability import UnitRequirementMapping
from memorii.tools.semantic_ingestion_traceability_checker import load_independent_registry_bytes
from memorii.tools.semantic_ingestion_traceability_registry import TraceabilityRegistry, canonical_document
from memorii.tools.semantic_ingestion_traceability_release import (
    AcceptanceTrustStore,
    TraceabilityGateAuthorized,
    verify_release_gate,
)


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


def verify_registered_approval_execution(
    *,
    registry_bytes: bytes,
    registry: TraceabilityRegistry,
    group_id: str,
    report_bytes: bytes,
    artifacts: dict[str, bytes],
    implementation_revision: str,
    implementation_tree_digest: str,
    environment_observation_bytes: bytes,
    bootstrap_artifact: bytes,
    recovery_artifact: bytes,
    lifecycle_artifact: bytes,
    release_artifact: bytes,
    active_pointer_artifact: bytes,
    release_history_artifact: bytes,
    authority: AcceptanceTrustStore,
    now: datetime,
) -> dict[str, object]:
    """The sole approval entry point.

    ``authority`` is constructed at composition time.  Candidate generations
    contain only bytes; callers cannot supply a verifier callback, root channel,
    or watermark and therefore cannot install self-signed authority.
    """
    source = load_independent_registry_bytes(registry_bytes)
    if getattr(registry, "canonical_bytes", None) != registry_bytes:
        raise ExecutionEvidenceError("registry object does not equal the approval raw bytes")
    groups = [item for item in source["test_evidence_groups"] if item.get("group_id") == group_id]
    if len(groups) != 1:
        raise ExecutionEvidenceError("registered evidence group is unavailable or ambiguous")
    group = groups[0]
    schemas = [item for item in source["report_schemas"] if (item.get("schema_id"), item.get("schema_version")) == (group.get("report_schema_id"), group.get("report_schema_version"))]
    profiles = [item for item in source["runner_environment_profiles"] if (item.get("profile_id"), item.get("profile_version")) == (group.get("runner_environment_profile_id"), group.get("runner_environment_profile_version"))]
    if len(schemas) != 1 or len(profiles) != 1:
        raise ExecutionEvidenceError("registered schema or environment profile is unavailable or ambiguous")
    release = verify_release_gate(
        registry=registry, bootstrap_artifact=bootstrap_artifact, recovery_artifact=recovery_artifact,
        lifecycle_artifact=lifecycle_artifact, release_artifact=release_artifact,
        active_pointer_artifact=active_pointer_artifact, release_history_artifact=release_history_artifact,
        verifier_material=authority.material, watermark=authority.watermark, now=now,
    )
    if not isinstance(release, TraceabilityGateAuthorized) or release.root_bindings is None:
        raise ExecutionEvidenceError("release gate did not authorize the complete durable generation")
    roots = release.root_bindings
    return _verify_release_bound_execution(
        report_bytes=report_bytes, artifacts=artifacts, group=group,
        registry_source_identity=roots["registry_source_identity"],
        structural_manifest_digest=roots["structural_manifest_digest"],
        design_document_digest=roots["design_document_digest"],
        implementation_revision=implementation_revision,
        implementation_tree_digest=implementation_tree_digest, release=release,
        environment_observation_bytes=environment_observation_bytes, report_schema=schemas[0],
        runner_environment_profile=profiles[0],
    )


def _verify_release_bound_execution(
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
    report_schema: dict[str, object] | None = None,
    runner_environment_profile: dict[str, object] | None = None,
) -> dict[str, object]:
    """Internal release-bound report verifier; never an approval boundary."""
    if release is None:
        raise ExecutionEvidenceError("release authority is unavailable")
    roots = release.root_bindings
    if roots is None:
        raise ExecutionEvidenceError("release lacks verified root bindings")
    for name, supplied in {
        "registry_source_identity": registry_source_identity,
        "structural_manifest_digest": structural_manifest_digest,
        "design_document_digest": design_document_digest,
    }.items():
        if roots.get(name) != supplied:
            raise ExecutionEvidenceError("caller root does not equal the authorized release")
    if report_schema is None or runner_environment_profile is None:
        raise ExecutionEvidenceError("registered report schema and runner profile are required")
    # Artifact digests are domain separated in the registry, unlike normal
    # report artifacts; recompute the exact registered coordinate here.
    if sha256(b"memorii:sia-report-schema:v1\0" + canonical_document(report_schema)).hexdigest() != group.get("expected_report_schema_digest"):
        raise ExecutionEvidenceError("registered report schema bytes are not authorized")
    if sha256(b"memorii:sia-runner-environment-profile:v1\0" + canonical_document(runner_environment_profile)).hexdigest() != group.get("expected_runner_environment_profile_digest"):
        raise ExecutionEvidenceError("registered runner profile bytes are not authorized")
    report = verify_registered_runner_report(
        report_bytes=report_bytes,
        artifacts=artifacts,
        group=group,
        registry_source_identity=registry_source_identity,
        structural_manifest_digest=structural_manifest_digest,
        design_document_digest=design_document_digest,
        implementation_revision=implementation_revision,
        implementation_tree_digest=implementation_tree_digest,
        report_schema=report_schema,
    )
    observation_artifact = report.get("runner_environment_observation_artifact_digest")
    if not isinstance(observation_artifact, str) or artifacts.get(observation_artifact) != environment_observation_bytes:
        raise ExecutionEvidenceError("runner environment observation bytes are unavailable")
    if report.get("runner_environment_observation_digest") != observation_digest(environment_observation_bytes):
        raise ExecutionEvidenceError("runner environment observation digest is invalid")
    _verify_environment_observation(environment_observation_bytes, runner_environment_profile)
    return report


def _verify_environment_observation(raw: bytes, profile: dict[str, object]) -> None:
    """Reject partial observations before a passing report can become evidence."""
    try:
        observed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExecutionEvidenceError("runner environment observation is not JSON") from exc
    if not isinstance(observed, dict) or canonical_document(observed) != raw:
        raise ExecutionEvidenceError("runner environment observation is not canonical")
    # The observation is deliberately explicit rather than trusting the runner's
    # digest: all policy-bearing categories must be present for comparison.
    required = {"interpreter", "runner", "plugins", "configuration", "dependencies", "import_paths", "startup", "environment", "locale_timezone", "network"}
    if set(observed) != required or any(not isinstance(observed[key], (dict, list, str)) for key in required):
        raise ExecutionEvidenceError("runner environment observation is incomplete")
    comparisons = {
        "interpreter": "interpreter_policy",
        "runner": "runner_policy",
        "plugins": "plugin_policy",
        "configuration": "configuration_policy",
        "dependencies": "dependency_policy",
        "import_paths": "import_path_policy",
        "startup": "startup_customization_policy",
        "environment": "environment_policy",
        "locale_timezone": "locale_timezone_policy",
        "network": "network_policy",
    }
    for observation_key, profile_key in comparisons.items():
        if observed[observation_key] != profile.get(profile_key):
            raise ExecutionEvidenceError(f"runner environment {observation_key} differs from the registered profile")


def _validate_schema(value: object, schema: object, *, path: str = "report") -> None:
    """Small closed validator for the frozen report-schema dialect."""
    if not isinstance(schema, dict):
        raise ExecutionEvidenceError("registered report schema is malformed")
    any_of = schema.get("anyOf")
    if isinstance(any_of, list):
        if not any(_schema_accepts(value, candidate, path=path) for candidate in any_of):
            raise ExecutionEvidenceError(f"{path} does not match the registered schema")
        return
    if "const" in schema and value != schema["const"]:
        raise ExecutionEvidenceError(f"{path} differs from the registered schema constant")
    kind = schema.get("type")
    valid_type = {
        "object": lambda: isinstance(value, dict),
        "array": lambda: isinstance(value, list),
        "string": lambda: isinstance(value, str),
        "integer": lambda: isinstance(value, int) and not isinstance(value, bool),
        "null": lambda: value is None,
    }
    if kind in valid_type and not valid_type[kind]():
        raise ExecutionEvidenceError(f"{path} has the wrong registered schema type")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, dict) or not isinstance(required, list) or any(name not in value for name in required):
            raise ExecutionEvidenceError(f"{path} misses a registered schema field")
        if schema.get("additionalProperties") is False and set(value) != set(properties):
            raise ExecutionEvidenceError(f"{path} has an unknown registered schema field")
        for name, child_schema in properties.items():
            if name in value:
                _validate_schema(value[name], child_schema, path=f"{path}.{name}")
    elif isinstance(value, list):
        minimum = schema.get("minItems")
        if isinstance(minimum, int) and len(value) < minimum:
            raise ExecutionEvidenceError(f"{path} is shorter than the registered schema")
        if schema.get("uniqueItems") is True and len({canonical_document(item) for item in value}) != len(value):
            raise ExecutionEvidenceError(f"{path} has duplicate registered-schema items")
        if "items" in schema:
            for index, item in enumerate(value):
                _validate_schema(item, schema["items"], path=f"{path}[{index}]")
    elif isinstance(value, str):
        minimum = schema.get("minLength")
        if isinstance(minimum, int) and len(value) < minimum:
            raise ExecutionEvidenceError(f"{path} is shorter than the registered schema")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
            raise ExecutionEvidenceError(f"{path} does not match the registered schema pattern")
        if schema.get("format") == "date-time":
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ExecutionEvidenceError(f"{path} is not an RFC3339 date-time") from exc
            if parsed.tzinfo is None:
                raise ExecutionEvidenceError(f"{path} is a naive date-time")


def _schema_accepts(value: object, schema: object, *, path: str) -> bool:
    try:
        _validate_schema(value, schema, path=path)
    except ExecutionEvidenceError:
        return False
    return True


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
    report_schema: dict[str, object],
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
    schema_document = report_schema.get("schema_document")
    _validate_schema(report, schema_document)
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
    # Schema ID and version are normative coordinates before the report's
    # individual bindings are consumed.
    if (report["schema_id"], report["schema_version"]) != (group.get("report_schema_id"), group.get("report_schema_version")):
        raise ExecutionEvidenceError("runner report schema coordinate is not registered")
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
    if report["runner_id"] != "cpython-pytest" or not isinstance(report["runner_version"], str):
        raise ExecutionEvidenceError("runner identity is not registered")
    try:
        started = datetime.fromisoformat(str(report["started_at"]).replace("Z", "+00:00")).astimezone(UTC)
        finished = datetime.fromisoformat(str(report["finished_at"]).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as exc:
        raise ExecutionEvidenceError("runner report time is invalid") from exc
    if started > finished:
        raise ExecutionEvidenceError("runner report time order is invalid")
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
    """Legacy record verifier retained for diagnostics only, never approval.

    The old API accepted caller-selected HMAC keys and therefore cannot create
    acceptance authority.  Approval must enter through
    :func:`verify_release_bound_execution` after release and report validation.
    """
    raise ExecutionEvidenceError("legacy caller-HMAC evidence is not approval-capable")


def _verify_legacy_execution_evidence(
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
    """Non-exported diagnostic implementation for migrating old fixtures."""

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
