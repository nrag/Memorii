"""Trusted, revision-bound execution-evidence verification for SIA-R03.

The verifier is deliberately separate from structural extraction.  Parser
agreement is accepted only as a precondition and cannot make execution pass.
"""

from __future__ import annotations

import hmac
import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Any

from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueError,
    CanonicalTypedValueProfileBinding,
    artifact_preimage,
    decode_artifact,
    decode_typed_value,
    encode_typed_value,
)
from memorii.tools.semantic_ingestion_structural_ledger import (
    StructuralLedgerError,
    load_checked_in_frozen_structural_manifest_ledger,
    load_frozen_structural_manifest_ledger,
)
from memorii.tools.semantic_ingestion_traceability import UnitRequirementMapping
from memorii.tools.semantic_ingestion_traceability_checker import (
    TraceabilityCoverageError,
    load_independent_registry_bytes,
)
from memorii.tools.semantic_ingestion_traceability_registry import canonical_document, load_registry_bytes
from memorii.tools.semantic_ingestion_traceability_release import (
    AcceptanceTrustStore,
    IndependentGenerationVerificationResult,
    TraceabilityGateAuthorized,
    VerifiedReleaseCandidate,
    candidate_authorization,
    commit_verified_release,
    validate_release_candidate,
)
from memorii.tools.semantic_ingestion_trust_resolver import AcceptanceTrustResolver

UTC = timezone.utc  # noqa: UP017


class ExecutionEvidenceError(ValueError):
    """Raised when execution evidence cannot safely approve a mapping."""


_CLEAN_ROOM_B_EXECUTOR_ID = "memorii-sia-clean-room-b-v1"
_CLEAN_ROOM_B_IMPLEMENTATION_SHA256 = "b655f474e4918d64447251e40b9a3af53daca0efd2e2cb6baa76890243bae5ed"


@dataclass(frozen=True)
class PinnedIsolatedIndependentGenerationVerifier:
    """Execute the stdlib-only B compiler behind a pinned file/byte boundary."""

    implementation_path: Path
    implementation_sha256: str = "b655f474e4918d64447251e40b9a3af53daca0efd2e2cb6baa76890243bae5ed"

    def verify(
        self,
        *,
        design_bytes: bytes,
        registry_bytes: bytes,
        ledger_bytes: bytes,
        expected_body_bytes: bytes,
        expected_envelope_bytes: bytes,
    ) -> IndependentGenerationVerificationResult:
        implementation = self.implementation_path.read_bytes()
        if sha256(implementation).hexdigest() != self.implementation_sha256:
            raise ExecutionEvidenceError("independent verifier implementation identity mismatch")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            design, registry, ledger, output = (
                root / "design.bin", root / "registry.bin", root / "ledger.bin", root / "result.json"
            )
            design.write_bytes(design_bytes)
            registry.write_bytes(registry_bytes)
            ledger.write_bytes(ledger_bytes)
            try:
                completed = subprocess.run(
                    [sys.executable, "-I", str(self.implementation_path), str(design), str(registry), str(ledger), str(output)],
                    check=False,
                    capture_output=True,
                    timeout=60,
                )
            except subprocess.TimeoutExpired as exc:
                raise ExecutionEvidenceError("independent verifier total deadline exceeded") from exc
            if completed.returncode != 0:
                raise ExecutionEvidenceError("independent verifier execution failed")
            try:
                result = json.loads(output.read_bytes())
                body = bytes.fromhex(result["body_bytes_hex"])
                envelope = bytes.fromhex(result["envelope_bytes_hex"])
                spool = bytes.fromhex(result["structural_spool_bytes_hex"])
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ExecutionEvidenceError("independent verifier byte protocol is invalid") from exc
        if (
            body != expected_body_bytes
            or envelope != expected_envelope_bytes
            or spool != structural_verification_spool(body, envelope)
        ):
            raise ExecutionEvidenceError("independent clean-room structural verification disagrees")
        return IndependentGenerationVerificationResult(
            _CLEAN_ROOM_B_EXECUTOR_ID,
            _CLEAN_ROOM_B_IMPLEMENTATION_SHA256,
            body,
            envelope,
            spool,
        )


def structural_verification_spool(body: bytes, envelope: bytes) -> bytes:
    """Closed binary spool shared with the separately executed verifier."""
    return (
        b"memorii:sia-clean-room-structural-spool:v1\0"
        + len(body).to_bytes(8, "big")
        + body
        + len(envelope).to_bytes(8, "big")
        + envelope
    )


def _verify_independent_structural_result(
    result: IndependentGenerationVerificationResult | None,
    *,
    body: bytes,
    envelope: bytes,
) -> None:
    if (
        result is None
        or result.executor_id != _CLEAN_ROOM_B_EXECUTOR_ID
        or result.implementation_sha256 != _CLEAN_ROOM_B_IMPLEMENTATION_SHA256
        or result.structural_body_bytes != body
        or result.structural_envelope_bytes != envelope
        or result.structural_spool_bytes
        != structural_verification_spool(body, envelope)
    ):
        raise ExecutionEvidenceError(
            "independent clean-room structural verification disagrees"
        )


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


class RegisteredApprovalExecutor:
    """Composition-bootstrapped registered approval boundary.

    Trust authority is captured once during application composition. Request
    callers can supply only candidate and operational evidence bytes.
    """

    def __init__(self, authority: AcceptanceTrustStore) -> None:
        self._authority = authority

    @classmethod
    def from_resolver(cls, resolver: AcceptanceTrustResolver) -> RegisteredApprovalExecutor:
        authority = resolver.resolve_registered_execution()
        if authority is None:
            raise ExecutionEvidenceError("registered trust authority is unavailable")
        return cls(authority)

    def execute(
        self,
        *,
        registry_bytes: bytes,
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
        pointer_history_artifact: bytes | None = None,
        historical_release_artifacts: tuple[bytes, ...] = (),
        recovery_artifacts: tuple[bytes, ...] = (),
        generation_manifest_bytes: bytes | None = None,
        generation_member_bytes: dict[str, bytes] | None = None,
        design_document_bytes: bytes | None = None,
        verification_deadline: datetime | None = None,
        cancelled: Callable[[], bool] | None = None,
        retry_count: int = 0,
        now: datetime,
    ) -> dict[str, object]:
        return _verify_registered_approval_execution(
            registry_bytes=registry_bytes,
            group_id=group_id,
            report_bytes=report_bytes,
            artifacts=artifacts,
            implementation_revision=implementation_revision,
            implementation_tree_digest=implementation_tree_digest,
            environment_observation_bytes=environment_observation_bytes,
            bootstrap_artifact=bootstrap_artifact,
            recovery_artifact=recovery_artifact,
            lifecycle_artifact=lifecycle_artifact,
            release_artifact=release_artifact,
            active_pointer_artifact=active_pointer_artifact,
            release_history_artifact=release_history_artifact,
            pointer_history_artifact=pointer_history_artifact,
            historical_release_artifacts=historical_release_artifacts,
            recovery_artifacts=recovery_artifacts,
            generation_manifest_bytes=generation_manifest_bytes,
            generation_member_bytes=generation_member_bytes,
            design_document_bytes=design_document_bytes,
            authority=self._authority,
            verification_deadline=verification_deadline,
            cancelled=cancelled,
            retry_count=retry_count,
            now=now,
        )


def _verify_registered_approval_execution(
    *,
    registry_bytes: bytes,
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
    pointer_history_artifact: bytes | None = None,
    historical_release_artifacts: tuple[bytes, ...] = (),
    recovery_artifacts: tuple[bytes, ...] = (),
    generation_manifest_bytes: bytes | None = None,
    generation_member_bytes: dict[str, bytes] | None = None,
    design_document_bytes: bytes | None = None,
    authority: AcceptanceTrustStore,
    verification_deadline: datetime | None = None,
    cancelled: Callable[[], bool] | None = None,
    retry_count: int = 0,
    now: datetime,
) -> dict[str, object]:
    """Implementation behind the composition-bootstrapped executor."""
    if authority.publication_store is None and not authority.allow_test_watermark_fallback:
        raise ExecutionEvidenceError("registered publication store is unavailable")
    # Registered approval is a typed CTV-v2 boundary.  The legacy raw release
    # gate remains available for migration callers, but cannot authorize this
    # production-facing execution path.
    typed_release_artifacts = (
        bootstrap_artifact,
        recovery_artifact,
        lifecycle_artifact,
        release_artifact,
        active_pointer_artifact,
        release_history_artifact,
        *( () if pointer_history_artifact is None else (pointer_history_artifact,) ),
        *historical_release_artifacts,
        *recovery_artifacts,
    )
    try:
        for raw in typed_release_artifacts:
            decode_artifact(raw)
    except CanonicalTypedValueError as exc:
        raise ExecutionEvidenceError("registered release artifacts must be CTV-v2 envelopes") from exc
    source = load_independent_registry_bytes(registry_bytes)
    try:
        registry = load_registry_bytes(registry_bytes)
    except ValueError as exc:
        raise ExecutionEvidenceError("registry raw bytes are not canonical authority") from exc
    groups = [item for item in source["test_evidence_groups"] if item.get("group_id") == group_id]
    if len(groups) != 1:
        raise ExecutionEvidenceError("registered evidence group is unavailable or ambiguous")
    group = groups[0]
    schemas = [
        item
        for item in source["report_schemas"]
        if (item.get("schema_id"), item.get("schema_version"))
        == (group.get("report_schema_id"), group.get("report_schema_version"))
    ]
    profiles = [
        item
        for item in source["runner_environment_profiles"]
        if (item.get("profile_id"), item.get("profile_version"))
        == (group.get("runner_environment_profile_id"), group.get("runner_environment_profile_version"))
    ]
    if len(schemas) != 1 or len(profiles) != 1:
        raise ExecutionEvidenceError("registered schema or environment profile is unavailable or ambiguous")
    candidate = validate_release_candidate(
        registry=registry,
        bootstrap_artifact=bootstrap_artifact,
        recovery_artifact=recovery_artifact,
        lifecycle_artifact=lifecycle_artifact,
        release_artifact=release_artifact,
        active_pointer_artifact=active_pointer_artifact,
        release_history_artifact=release_history_artifact,
        historical_release_artifacts=historical_release_artifacts,
        recovery_artifacts=recovery_artifacts,
        verifier_material=authority.material,
        expected_release_roots=authority.expected_release_roots,
        now=now,
    )
    if not isinstance(candidate, VerifiedReleaseCandidate):
        raise ExecutionEvidenceError(f"release gate did not authorize: {candidate.reason}")
    release = candidate_authorization(candidate)
    if release.root_bindings is None:
        raise ExecutionEvidenceError("validated release lacks root bindings")
    roots = release.root_bindings
    try:
        _verify_optional_generation_closure(
            generation_manifest_bytes=generation_manifest_bytes,
        generation_member_bytes=generation_member_bytes,
        design_document_bytes=design_document_bytes,
        registry_bytes=registry_bytes,
        registry=registry,
        release_roots=roots,
        active_pointer_artifact=active_pointer_artifact,
        expected_member_bytes={
            "bootstrap_anchor": bootstrap_artifact,
            "bootstrap_anchors": (
                bootstrap_artifact,
                *authority.material.provisioned_successor_root_bytes,
            ),
            "recovery_root": recovery_artifact,
            "recovery_roots": (recovery_artifact, *recovery_artifacts),
            "recovery_policy": authority.material.recovery_policy_bytes,
            "trust_lifecycle_root": lifecycle_artifact,
            "release": release_artifact,
            "release_history": release_history_artifact,
            "pointer_history": pointer_history_artifact,
        },
        active_signers=candidate.active_signers,
        verify_signature=authority.material.verify_signature,
        now=now,
        verification_deadline=verification_deadline,
        cancelled=cancelled,
        retry_count=retry_count,
            independent_verifier=authority.independent_generation_verifier,
        )
    except ExecutionEvidenceError as exc:
        message = str(exc)
        if any(token in message for token in ("deadline", "cancelled", "count exceeded", "byte budget exceeded", "8 MiB", "parser is unavailable", "structural_derivation_unavailable")):
            raise ExecutionEvidenceError("structural_derivation_unavailable") from exc
        raise
    verified_report = _verify_release_bound_execution(
        report_bytes=report_bytes,
        artifacts=artifacts,
        group=group,
        registry_source_identity=roots["registry_source_identity"],
        structural_manifest_digest=roots["structural_manifest_digest"],
        design_document_digest=roots["design_document_digest"],
        implementation_revision=implementation_revision,
        implementation_tree_digest=implementation_tree_digest,
        release=release,
        environment_observation_bytes=environment_observation_bytes,
        report_schema=schemas[0],
        runner_environment_profile=profiles[0],
    )
    committed = commit_verified_release(
        candidate,
        authority.watermark_store,
        publication_store=authority.publication_store,
        release_artifact=release_artifact,
        release_history_artifact=release_history_artifact,
        active_pointer_artifact=active_pointer_artifact,
        pointer_history_artifact=pointer_history_artifact,
        allow_test_file_fence=authority.allow_test_file_fence,
        verified_anti_rollback_registration=authority.verified_anti_rollback_registration,
        anti_rollback_resolver=authority.anti_rollback_resolver,
    )
    if not isinstance(committed, TraceabilityGateAuthorized):
        raise ExecutionEvidenceError(f"release gate did not authorize: {committed.reason}")
    return verified_report


_GENERATION_SINGLETON_KINDS = frozenset(
    {
        "design_document",
        "registry_source",
        "structural_manifest_derivation_ledger",
        "bootstrap_anchor_history",
        "recovery_root_history",
        "recovery_policy_history",
        "trust_lifecycle_root",
        "trust_snapshot",
        "structural_manifest",
        "coverage_root",
        "execution_root",
        "release",
        "release_history",
        "pointer_history",
        "golden_vector_manifest",
    }
)
_GENERATION_KINDS = _GENERATION_SINGLETON_KINDS | {
    "bootstrap_anchor",
    "recovery_root",
    "recovery_policy",
    "coverage_approval",
    "report_schema",
    "runner_environment_profile",
    "runner_environment_observation",
    "runner_report",
    "test_artifact",
    "result_artifact",
    "stdout_artifact",
    "stderr_artifact",
    "execution_evidence",
    "golden_typed_input_fixture",
}

_GENERATION_PROFILE = (
    "semantic_ingestion_typed_value",
    2,
    "9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f",
)
_GENERATION_MANIFEST_BINDING = CanonicalTypedValueProfileBinding(
    *_GENERATION_PROFILE,
    "TraceabilityApprovalGenerationManifestBody.v1",
    1,
    "9a8157b88ff3ddc299030c877a8f2cf6e95114da331174bfc1bb47836841fe69",
)
_CURRENT_RELEASE_MEMBER_PROFILE = (
    "semantic_ingestion_typed_value",
    2,
    "9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f",
)
_CURRENT_RELEASE_MEMBER_BINDINGS = {
    "bootstrap_anchor": (
        "TraceabilityBootstrapTrustAnchorBody.v1", 1,
        "b3afc00594f4ba871e64a1a1d649a1d32e1b7bb77e7eb2ff14d550e897f19c77",
    ),
    "recovery_root": (
        "TraceabilityRecoveryTrustRootBody.v1", 1,
        "b8e2679794f444955932cd204dee8312e6c0077346c9f5570e1c28770c09abf3",
    ),
    "recovery_policy": (
        "TraceabilityRecoveryTrustPolicyBody.v1", 1,
        "4cf90609b1ab78610816b1316082f40f749052f33fe3ad5a2b85b65820cffd75",
    ),
    "trust_lifecycle_root": (
        "TraceabilityTrustLifecycleRootBody.v1", 1,
        "82cee87c03a941f2dc58489f9f358d18eb505bf956a72bc23b9f4f2abd0d214e",
    ),
    "release": (
        "SemanticIngestionTraceabilityReleaseBody.v1", 1,
        "2e1ba193b6fac94c03598d7c27489f5fa69e48c5a052072124acb398adfd8ce2",
    ),
    "release_history": (
        "TraceabilityReleaseHistoryBody.v1", 1,
        "398f87e800eba421e3e657af5c6b34e1887c5c93e7038c981d6e6ce3d38d87e3",
    ),
}
_GENERATION_RAW_BINDINGS = {
    "design_document": ("memorii.raw.design_document.v1", 1, "raw-sha256-bytes-v1"),
    "registry_source": (
        "memorii.raw.registry_source.v1",
        1,
        "raw-sha256-bytes-v1",
    ),
    "structural_manifest_derivation_ledger": (
        "memorii.raw.structural_manifest_derivation_ledger.v1", 1, "raw-sha256-bytes-v1",
    ),
}
_GENERATION_CTV_BINDINGS = {
    "bootstrap_anchor": (
        "TraceabilityBootstrapTrustAnchorBody.v1",
        1,
        "0f7c971321982968f22a86856f16bb65b1d325de896b4a668ddcdb95fa14d348",
    ),
    "bootstrap_anchor_history": (
        "TraceabilityBootstrapAnchorHistoryBody.v1",
        1,
        "1dc722062d722fcd0684f99643815083a658f6f5a2af46bf1c1b7e1d10993486",
    ),
    "recovery_root": (
        "TraceabilityRecoveryTrustRootBody.v1",
        1,
        "d3c3f1e4ad54823395d1a5588811288957ac644a4fa5046b4af7795f24792b80",
    ),
    "recovery_root_history": (
        "TraceabilityRecoveryRootHistoryBody.v1",
        1,
        "9ec22f55091d02e08b16bd0ff8df9415a07215adb08d738ce85ee4102bcfe7d6",
    ),
    "recovery_policy": (
        "TraceabilityRecoveryTrustPolicyBody.v1",
        1,
        "b3bdaccb4b40c1cff561f434b862cf0c19c4d6e0e2b57225b1300630a2e433d5",
    ),
    "recovery_policy_history": (
        "TraceabilityRecoveryPolicyHistoryBody.v1",
        1,
        "774f8b854a2341af729f3c03192b65d74b6ea7d80ac57d8487368496bf8ad531",
    ),
    "trust_lifecycle_root": (
        "TraceabilityTrustLifecycleRootBody.v1",
        1,
        "1bec92aad57fa277c4b3022e5e0e8ba8d25c62cf26d8d7e6453a475b2cd4cdae",
    ),
    "trust_snapshot": (
        "TraceabilityReleaseTrustSnapshotBody.v1",
        1,
        "cf54bc76121a70f09f3df0b38a9cf3524a41f59f4a155ad902a5c1ae0d3dd746",
    ),
    "structural_manifest": (
        "NormativeTraceabilityStructuralManifestBody.v1",
        1,
        "133ba5b492880d5b773eb75f5a81de0bdf0c09e85cce20d17d7aa076cee7b79b",
    ),
    "coverage_approval": (
        "TraceabilityCoverageApprovalRecordBody.v1",
        1,
        "dc9b582ce0bc10c2ad30343f5795c4ccd68bce816d8d768f80938fa70d0f2420",
    ),
    "coverage_root": (
        "TraceabilityCoverageEvidenceRootBody.v1",
        1,
        "9bd880643b48ebd59f8a559f66ea4b8c16f09c58343e2518662e712f971c1967",
    ),
    "execution_evidence": (
        "NormativeExecutionEvidenceRecordBody.v1",
        1,
        "3cf25676fe23bc4baf7cf346d5b3ed17ab21e9c703222da79e92e2c810a11b09",
    ),
    "execution_root": (
        "TraceabilityExecutionEvidenceRootBody.v1",
        1,
        "3bfad21a4da22616bdbfb1fb9d9ee0bd2ad9a627e15b871a8614b76857be9f9f",
    ),
    "release": (
        "SemanticIngestionTraceabilityReleaseBody.v1",
        1,
        "a9354b6e9920382bf2ded9165e9c748f70fcc1b81c93847ab6d931c500ab41d2",
    ),
    "release_history": (
        "TraceabilityReleaseHistoryBody.v1",
        1,
        "68353a3e6a9b96bcabc8e949e1919b19ac172915a2e921921e3b8c0549af5bf8",
    ),
    "pointer_history": (
        "TraceabilityActiveReleasePointerHistoryBody.v1",
        1,
        "6beb555ad4f7f68823b4283e3728e23bf21233bf1b53423f92f31e1418acd6b7",
    ),
    "golden_vector_manifest": (
        "TraceabilityApprovalGoldenVectorManifestBody.v1",
        1,
        "450c30559b0dbdea167182e3893c88108701e85593f9be5682e8b6de83b5e9c3",
    ),
    "golden_typed_input_fixture": (
        "TraceabilityGoldenTypedInputFixtureBody.v1",
        1,
        "51670d26f287456abce92872559a294c68175315f62e2f2898c8966957ffa885",
    ),
}
_M0_GENERATION_ORDER = (
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
_M0_GENERATION_DEPENDENCIES = {
    "design_document": (),
    "registry_source": ("design_document",),
    "structural_manifest_derivation_ledger": (),
    "bootstrap_anchor": (),
    "recovery_root": (),
    "recovery_policy": ("bootstrap_anchor", "recovery_root"),
    "bootstrap_anchor_history": ("bootstrap_anchor",),
    "recovery_root_history": ("recovery_root",),
    "recovery_policy_history": ("recovery_policy",),
    "trust_lifecycle_root": (
        "bootstrap_anchor_history",
        "recovery_root_history",
        "recovery_policy_history",
    ),
    "trust_snapshot": (
        "trust_lifecycle_root",
        "bootstrap_anchor_history",
        "recovery_root_history",
        "recovery_policy_history",
    ),
    "structural_manifest": ("design_document", "registry_source", "structural_manifest_derivation_ledger"),
    "coverage_root": ("structural_manifest",),
    "execution_root": ("structural_manifest",),
    "golden_vector_manifest": (),
    "release": (
        "bootstrap_anchor",
        "bootstrap_anchor_history",
        "recovery_root",
        "recovery_root_history",
        "recovery_policy",
        "recovery_policy_history",
        "trust_lifecycle_root",
        "trust_snapshot",
        "structural_manifest",
        "coverage_root",
        "execution_root",
        "golden_vector_manifest",
    ),
    "release_history": ("release",),
    "pointer_history": (),
}

# Admission limits apply before a CTV body is decoded or any dependency graph
# is expanded.  They deliberately bound the immutable package transport rather
# than silently truncating a generation.
# CTV bodies are governed by the architecture's frozen 64 MiB ceiling.
_MAX_GENERATION_MEMBER_BYTES = 64 * 1024 * 1024
_MAX_GENERATION_TOTAL_BYTES = 128 * 1024 * 1024
_MAX_CTV_NESTING_DEPTH = 256
_MAX_CTV_CONTAINERS = 250_000
_MAX_CTV_FIELDS = 250_000
_MAX_GENERATION_RETRIES = 0
_MAX_GENERATION_VERIFICATION_SECONDS = 60


@dataclass(frozen=True)
class _GenerationVerificationBudget:
    """Bound CTV admission work before typed decoding can expand a package."""

    deadline: datetime
    monotonic_deadline: float
    cancelled: Callable[[], bool] | None

    def check(self) -> None:
        if self.cancelled is not None and self.cancelled():
            raise ExecutionEvidenceError("generation verification was cancelled")
        if datetime.now(UTC) >= self.deadline or monotonic() >= self.monotonic_deadline:
            raise ExecutionEvidenceError("generation verification deadline exceeded")


def _generation_verification_budget(
    *,
    verification_deadline: datetime | None,
    cancelled: Callable[[], bool] | None,
    retry_count: int,
) -> _GenerationVerificationBudget:
    if retry_count != _MAX_GENERATION_RETRIES:
        raise ExecutionEvidenceError("generation retry count exceeds the closed contract")
    now = datetime.now(UTC)
    deadline = verification_deadline or now + timedelta(
        seconds=_MAX_GENERATION_VERIFICATION_SECONDS
    )
    if deadline.tzinfo is None:
        raise ExecutionEvidenceError("generation verification deadline is not timezone-aware")
    remaining = (deadline.astimezone(UTC) - now).total_seconds()
    if remaining <= 0:
        raise ExecutionEvidenceError("generation verification deadline exceeded")
    return _GenerationVerificationBudget(
        deadline=deadline.astimezone(UTC),
        monotonic_deadline=monotonic() + min(
            remaining, _MAX_GENERATION_VERIFICATION_SECONDS
        ),
        cancelled=cancelled,
    )


def _verify_ctv_transport_shape(raw: bytes, budget: _GenerationVerificationBudget) -> None:
    """Reject pathological JSON before the canonical CTV decoder walks it."""
    budget.check()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExecutionEvidenceError("generation CTV transport is invalid") from exc
    pending: list[tuple[object, int]] = [(value, 1)]
    containers = 0
    fields = 0
    while pending:
        value, depth = pending.pop()
        budget.check()
        if depth > _MAX_CTV_NESTING_DEPTH:
            raise ExecutionEvidenceError("generation CTV nesting depth exceeded")
        if isinstance(value, dict):
            containers += 1
            fields += len(value)
            if containers > _MAX_CTV_CONTAINERS:
                raise ExecutionEvidenceError("generation CTV container count exceeded")
            if fields > _MAX_CTV_FIELDS:
                raise ExecutionEvidenceError("generation CTV field count exceeded")
            pending.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            containers += 1
            if containers > _MAX_CTV_CONTAINERS:
                raise ExecutionEvidenceError("generation CTV container count exceeded")
            pending.extend((item, depth + 1) for item in value)


def _verify_generation_admission(
    *,
    generation_manifest_bytes: bytes,
    generation_member_bytes: dict[str, bytes],
    design_document_bytes: bytes,
    registry_bytes: bytes,
    verification_deadline: datetime | None,
    cancelled: Callable[[], bool] | None,
    retry_count: int,
) -> _GenerationVerificationBudget:
    """Apply all fixed resource limits before CTV decoding or graph expansion."""
    budget = _generation_verification_budget(
        verification_deadline=verification_deadline,
        cancelled=cancelled,
        retry_count=retry_count,
    )
    budget.check()
    if len(design_document_bytes) > _MAX_GENERATION_MEMBER_BYTES:
        raise ExecutionEvidenceError("generation design byte limit exceeded")
    if len(registry_bytes) > _MAX_GENERATION_MEMBER_BYTES:
        raise ExecutionEvidenceError("generation registry byte limit exceeded")
    if len(generation_manifest_bytes) > _MAX_GENERATION_MEMBER_BYTES or any(
        len(raw) > _MAX_GENERATION_MEMBER_BYTES for raw in generation_member_bytes.values()
    ):
        raise ExecutionEvidenceError("generation member byte limit exceeded")
    # Design and registry are members of the closed package; do not count the
    # separately supplied comparison bytes a second time.
    total = len(generation_manifest_bytes) + sum(
        len(raw) for raw in generation_member_bytes.values()
    )
    if total > _MAX_GENERATION_TOTAL_BYTES:
        raise ExecutionEvidenceError("generation total byte limit exceeded")
    _verify_ctv_transport_shape(generation_manifest_bytes, budget)
    for coordinate, raw in generation_member_bytes.items():
        if raw in {design_document_bytes, registry_bytes}:
            continue
        if coordinate.startswith("sia-traceability/v1/structural_manifest/"):
            # The structural member is exact-byte reconstructed below. Avoid a
            # redundant generic JSON tree walk over the dominant 50+ MiB body.
            continue
        if coordinate.startswith(
            "sia-traceability/v1/structural_manifest_derivation_ledger/"
        ):
            # Exact checked-in bytes are compared before any release use.
            continue
        _verify_ctv_transport_shape(raw, budget)
    return budget

_M0_NONCYCLIC_BODY_FIELDS = {
    "bootstrap_anchor": frozenset(
        {
            "anchor_id", "issuance_purpose", "target_purpose", "target_authority_id",
            "authorized_signature_purposes", "canonical_profile_binding", "signature_profile_id",
            "public_key_or_root_certificate_digest", "provisioned_channel_id", "rotation_sequence",
            "predecessor_anchor_id", "predecessor_anchor_digest", "effective_at", "recorded_at",
            "expires_at", "provenance",
        }
    ),
    "recovery_root": frozenset(
        {
            "recovery_root_id", "issuance_purpose", "target_authority_id",
            "authorized_signature_purposes", "canonical_profile_binding", "signature_profile_id",
            "public_key_or_root_certificate_digest", "provisioned_channel_id", "rotation_sequence",
            "predecessor_recovery_root_id", "predecessor_recovery_root_digest", "effective_at",
            "recorded_at", "expires_at", "provenance",
        }
    ),
    "recovery_policy": frozenset(
        {
            "policy_id", "issuance_purpose", "target_authority_id", "bootstrap_anchor_id",
            "bootstrap_anchor_digest", "eligible_recovery_root_digests", "minimum_distinct_signatures",
            "signer_separation_rule_digest", "canonical_profile_binding", "effective_at", "recorded_at",
            "sequence", "predecessor_policy_digest", "expires_at", "signer_provenance", "signature",
            "recovery_policy_digest",
        }
    ),
    "bootstrap_anchor_history": frozenset(
        {"history_id", "canonical_profile_binding", "anchors", "history_digest"}
    ),
    "recovery_root_history": frozenset(
        {"history_id", "canonical_profile_binding", "recovery_roots", "history_digest"}
    ),
    "recovery_policy_history": frozenset(
        {"history_id", "canonical_profile_binding", "policies", "history_digest"}
    ),
    "structural_manifest": frozenset(
        {
            "grammar_revision",
            "design_document_digest",
            "registry_source_identity",
            "registry_root_digests",
            "units",
            "mappings",
            "structural_manifest_digest",
        }
    ),
    "trust_snapshot": frozenset(
        {
            "snapshot_id",
            "issuance_purpose",
            "canonical_profile_binding",
            "release_id",
            "release_epoch",
            "release_sequence",
            "bootstrap_anchor_digest",
            "recovery_policy_digest",
            "trust_lifecycle_root_digest",
            "lifecycle_recorded_time_cutoff",
            "qualified_issuers",
            "created_at",
            "trust_snapshot_digest",
        }
    ),
    "golden_vector_manifest": frozenset(
        {
            "manifest_id",
            "manifest_version",
            "source_path",
            "owner",
            "authority_use",
            "canonical_profile_binding",
            "design_document_digest",
            "registry_source_identity",
            "fixtures",
            "vectors",
            "golden_vector_manifest_digest",
        }
    ),
    "release_history": frozenset(
        {
            "history_id",
            "issuance_purpose",
            "canonical_profile_binding",
            "entries",
            "signer_coordinate",
            "signature",
            "release_history_digest",
        }
    ),
    "pointer_history": frozenset(
        {
            "history_id",
            "issuance_purpose",
            "canonical_profile_binding",
            "pointers",
            "signer_coordinate",
            "signature",
            "pointer_history_digest",
        }
    ),
    "trust_lifecycle_root": frozenset(
        {
            "authority_id", "issuance_purpose", "canonical_profile_binding",
            "bootstrap_anchor_history_digest", "recovery_root_history_digest",
            "recovery_policy_history_digest", "records", "signer_coordinates",
            "signatures", "lifecycle_root_digest",
        }
    ),
    "release": frozenset(
        {
            "release_id", "issuance_purpose", "registry_source_identity", "design_document_digest",
            "structural_manifest_digest", "grammar_revision", "canonical_profile_binding",
            "artifact_dag_digest", "requirement_binding_registry_digest", "assertion_registry_digest",
            "test_evidence_group_registry_digest", "report_schema_registry_digest",
            "runner_environment_profile_registry_digest", "golden_vector_manifest_digest",
            "section_default_registry_digest", "structural_mapping_rule_registry_digest",
            "override_registry_digest", "anchor_binding_registry_digest", "coverage_root_digest",
            "execution_root_digest", "bootstrap_anchor_id", "bootstrap_anchor_digest",
            "bootstrap_anchor_history_digest", "bootstrap_rotation_sequence",
            "recovery_trust_policy_digest", "recovery_policy_history_digest",
            "recovery_trust_root_digests", "recovery_root_history_digest",
            "trust_lifecycle_root_digest", "trust_snapshot_digest", "epoch", "sequence",
            "issued_state", "predecessor_release_id", "supersedes_release_id", "issued_at",
            "expires_at", "signer_coordinate", "signature", "release_digest",
        }
    ),
}
_M0_NONEMPTY_COLLECTION_FIELDS = {
    "bootstrap_anchor_history": ("anchors",),
    "recovery_root_history": ("recovery_roots",),
    "recovery_policy_history": ("policies",),
    "trust_snapshot": ("qualified_issuers",),
    "release_history": ("entries",),
    "trust_lifecycle_root": ("records", "signer_coordinates", "signatures"),
    "release": ("recovery_trust_root_digests",),
}


def _verify_m0_registered_body_shape(kind: str, body: dict[str, object]) -> None:
    """Fail closed on aliases, omitted fields, and placeholder registered bodies."""
    expected_fields = _M0_NONCYCLIC_BODY_FIELDS.get(kind)
    if expected_fields is None:
        return
    if set(body) != expected_fields:
        raise ExecutionEvidenceError(f"generation {kind} body fields are invalid")
    for field in _M0_NONEMPTY_COLLECTION_FIELDS.get(kind, ()):
        value = body[field]
        if not isinstance(value, list) or not value:
            raise ExecutionEvidenceError(
                f"generation {kind} {field} must be a non-empty canonical collection"
            )
    if kind == "structural_manifest":
        units = body["units"]
        mappings = body["mappings"]
        if not isinstance(units, list) or len(units) > 100_000:
            raise ExecutionEvidenceError("generation unit count exceeded")
        if not isinstance(mappings, list) or len(mappings) > 250_000:
            raise ExecutionEvidenceError("generation entry mapping count exceeded")
        anchors = sum(
            len(unit.get("explicit_anchor_bindings", ()))
            for unit in units
            if isinstance(unit, dict)
        )
        if anchors > 100_000:
            raise ExecutionEvidenceError("generation anchor binding count exceeded")


def _verify_optional_generation_closure(
    *,
    generation_manifest_bytes: bytes | None,
    generation_member_bytes: dict[str, bytes] | None,
    design_document_bytes: bytes | None,
    registry_bytes: bytes,
    registry: Any,
    release_roots: dict[str, str],
    active_pointer_artifact: bytes,
    expected_member_bytes: dict[str, object],
    active_signers: tuple[tuple[str, str, str, str, datetime, datetime | None], ...],
    verify_signature: Any,
    now: datetime,
    verification_deadline: datetime | None = None,
    cancelled: Callable[[], bool] | None = None,
    retry_count: int = 0,
    independent_verifier: Any = None,
) -> None:
    """Verify byte-addressed C2 closure before durable release acceptance.

    The legacy request shape predates C2 and remains explicitly unavailable as
    a generation input.  Once any C2 byte is supplied the complete package is
    mandatory; this prevents a caller from adding a synthetic root beside an
    otherwise legacy artifact bag.
    """
    if generation_manifest_bytes is None or generation_member_bytes is None or design_document_bytes is None:
        raise ExecutionEvidenceError("generation closure is incomplete")
    if not isinstance(generation_member_bytes, dict) or any(
        not isinstance(key, str) or not isinstance(value, bytes) for key, value in generation_member_bytes.items()
    ):
        raise ExecutionEvidenceError("generation member bytes are invalid")
    if len(generation_member_bytes) != len(_M0_GENERATION_ORDER):
        raise ExecutionEvidenceError("generation member count exceeds or misses the closed contract")
    budget = _verify_generation_admission(
        generation_manifest_bytes=generation_manifest_bytes,
        generation_member_bytes=generation_member_bytes,
        design_document_bytes=design_document_bytes,
        registry_bytes=registry_bytes,
        verification_deadline=verification_deadline,
        cancelled=cancelled,
        retry_count=retry_count,
    )
    try:
        envelope = decode_artifact(
            generation_manifest_bytes,
            expected_binding=_GENERATION_MANIFEST_BINDING,
        )
        manifest = decode_typed_value(envelope.canonical_value_bytes)
    except CanonicalTypedValueError as exc:
        raise ExecutionEvidenceError("generation manifest is not canonical typed bytes") from exc
    if not isinstance(manifest, dict):
        raise ExecutionEvidenceError("generation manifest body is invalid")
    required = {
        "generation_id",
        "issuance_purpose",
        "canonical_profile_binding",
        "design_document_digest",
        "registry_source_identity",
        "members",
        "active_pointer_intent",
        "signer_coordinate",
        "signature",
        "generation_manifest_digest",
    }
    if (
        set(manifest) != required
        or manifest.get("issuance_purpose") != "semantic_ingestion_traceability_approval_generation"
    ):
        raise ExecutionEvidenceError("generation manifest has an unknown field or purpose")
    if (
        not isinstance(manifest.get("canonical_profile_binding"), dict)
        or manifest["canonical_profile_binding"] != envelope.binding.as_value()
        or envelope.binding.schema_id != "TraceabilityApprovalGenerationManifestBody.v1"
    ):
        raise ExecutionEvidenceError("generation manifest binding is invalid")
    body = {
        key: value
        for key, value in manifest.items()
        if key not in {"signer_coordinate", "signature", "generation_manifest_digest"}
    }
    digest = sha256(b"memorii:sia-traceability-approval-generation:v1\0" + encode_typed_value(body)).hexdigest()
    if manifest["generation_manifest_digest"] != digest:
        raise ExecutionEvidenceError("generation manifest digest is invalid")
    signer = manifest["signer_coordinate"]
    if not isinstance(signer, dict) or set(signer) != {
        "signature_purpose",
        "issuer_id",
        "key_or_certificate_digest",
        "signature_profile_id",
        "trust_lifecycle_root_digest",
        "lifecycle_record_digest",
        "eligible_not_before",
        "eligible_not_after",
    }:
        raise ExecutionEvidenceError("generation manifest signer coordinate is invalid")
    if signer.get("signature_purpose") != "semantic_ingestion_traceability_approval_generation":
        raise ExecutionEvidenceError("generation manifest signer purpose is invalid")
    try:
        signer_start = datetime.fromisoformat(str(signer["eligible_not_before"]).replace("Z", "+00:00"))
        signer_end = (
            None
            if signer["eligible_not_after"] is None
            else datetime.fromisoformat(str(signer["eligible_not_after"]).replace("Z", "+00:00"))
        )
    except ValueError as exc:
        raise ExecutionEvidenceError("generation manifest signer interval is invalid") from exc
    eligible_signers = {
        (signer_id, profile, key, start, end)
        for signer_id, _, profile, key, start, end in active_signers
        if start <= now and (end is None or now < end)
    }
    lifecycle_raw = expected_member_bytes.get("trust_lifecycle_root")
    if not isinstance(lifecycle_raw, bytes):
        raise ExecutionEvidenceError("generation lifecycle signer authority is invalid")
    try:
        lifecycle = decode_typed_value(
            decode_artifact(lifecycle_raw).canonical_value_bytes
        )
    except CanonicalTypedValueError as exc:
        raise ExecutionEvidenceError("generation lifecycle signer authority is invalid") from exc
    lifecycle_records = lifecycle.get("records") if isinstance(lifecycle, dict) else None
    lifecycle_record_digests = (
        {record.get("record_digest") for record in lifecycle_records if isinstance(record, dict)}
        if isinstance(lifecycle_records, list)
        else set()
    )
    if (
        signer_start.tzinfo is None
        or (signer_end is not None and signer_end.tzinfo is None)
        or (
            signer["issuer_id"],
            signer["signature_profile_id"],
            signer["key_or_certificate_digest"],
            signer_start,
            signer_end,
        )
        not in eligible_signers
        or not isinstance(lifecycle, dict)
        or signer["trust_lifecycle_root_digest"] != lifecycle.get("lifecycle_root_digest")
        or signer["lifecycle_record_digest"] not in lifecycle_record_digests
    ):
        raise ExecutionEvidenceError("generation manifest signer is not lifecycle qualified")
    signature = manifest["signature"]
    if not isinstance(signature, str):
        raise ExecutionEvidenceError("generation manifest signature is invalid")
    try:
        signature_bytes = bytes.fromhex(signature)
    except ValueError as exc:
        raise ExecutionEvidenceError("generation manifest signature is invalid") from exc
    signature_preimage = encode_typed_value(
        {
            "issuance_purpose": "semantic_ingestion_traceability_approval_generation",
            "body_binding": envelope.binding.as_value(),
            "generation_manifest_digest": digest,
            "signer_coordinate": signer,
        }
    )
    if not verify_signature(
        signer["signature_profile_id"],
        signer["key_or_certificate_digest"],
        signature_preimage,
        signature_bytes,
    ):
        raise ExecutionEvidenceError("generation manifest signature is invalid")
    intent = manifest["active_pointer_intent"]
    try:
        pointer = decode_typed_value(decode_artifact(active_pointer_artifact).canonical_value_bytes)
    except CanonicalTypedValueError as exc:
        raise ExecutionEvidenceError("generation active pointer bytes are invalid") from exc
    if not isinstance(pointer, dict) or not isinstance(intent, dict):
        raise ExecutionEvidenceError("generation pointer intent is invalid")
    if (
        pointer.get("generation_id") != manifest["generation_id"]
        or pointer.get("generation_manifest_digest") != manifest["generation_manifest_digest"]
    ):
        raise ExecutionEvidenceError("generation manifest is not bound by active pointer")
    # The manifest deliberately omits the two fixed-point fields from its
    # intent.  Every remaining pointer body field is immutable generation
    # input and therefore must be byte-for-byte equal to the selected pointer.
    pointer_body = {
        key: value
        for key, value in pointer.items()
        if key not in {"active_pointer_digest", "signature", "generation_id", "generation_manifest_digest"}
    }
    if intent != pointer_body:
        raise ExecutionEvidenceError("generation pointer intent digest is invalid")
    if (
        manifest["design_document_digest"]
        != sha256(b"semantic-ingestion-traceability\0" + design_document_bytes).hexdigest()
    ):
        raise ExecutionEvidenceError("generation design bytes do not match its digest")
    if manifest["registry_source_identity"] != release_roots.get("registry_source_identity"):
        raise ExecutionEvidenceError("generation registry identity differs from release")
    if registry_bytes != generation_member_bytes.get(
        _coordinate("registry_source", manifest["registry_source_identity"])
    ):
        raise ExecutionEvidenceError("generation registry member bytes are unavailable")
    ledger = load_checked_in_frozen_structural_manifest_ledger()
    ledger_coordinate = _coordinate("structural_manifest_derivation_ledger", ledger.digest)
    if generation_member_bytes.get(ledger_coordinate) != ledger.raw_bytes:
        raise ExecutionEvidenceError("generation raw derivation ledger is unavailable")
    members = manifest["members"]
    if not isinstance(members, list) or not members:
        raise ExecutionEvidenceError("generation members are invalid")
    _verify_m0_manifest_graph(members, generation_member_bytes, budget)
    coordinates: set[str] = set()
    member_bodies: dict[str, list[dict[str, object]]] = {}
    member_coordinates_by_kind: dict[str, list[str]] = {}
    kinds: list[str] = []
    for member in members:
        budget.check()
        if not isinstance(member, dict) or set(member) != {
            "artifact_kind",
            "artifact_coordinate",
            "artifact_digest",
            "depends_on_coordinates",
            "schema_id",
            "schema_version",
            "binding_digest",
        }:
            raise ExecutionEvidenceError("generation member shape is invalid")
        kind, coordinate, member_digest, dependencies = (
            member["artifact_kind"],
            member["artifact_coordinate"],
            member["artifact_digest"],
            member["depends_on_coordinates"],
        )
        if (
            not isinstance(kind, str)
            or kind not in _GENERATION_KINDS
            or not isinstance(coordinate, str)
            or not isinstance(member_digest, str)
            or not isinstance(dependencies, list)
        ):
            raise ExecutionEvidenceError("generation member metadata is invalid")
        if (
            coordinate != _coordinate(kind, member_digest)
            or coordinate in coordinates
            or any(not isinstance(dep, str) or dep not in coordinates for dep in dependencies)
        ):
            raise ExecutionEvidenceError("generation member coordinate or order is invalid")
        if len(dependencies) != len(set(dependencies)) or dependencies != sorted(dependencies):
            raise ExecutionEvidenceError("generation member dependency set is invalid")
        expected_raw_binding = _GENERATION_RAW_BINDINGS.get(kind)
        if (
            expected_raw_binding is not None
            and (
                member["schema_id"],
                member["schema_version"],
                member["binding_digest"],
            )
            != expected_raw_binding
        ):
            raise ExecutionEvidenceError("generation raw member binding is invalid")
        raw = generation_member_bytes.get(coordinate)
        if raw is None:
            raise ExecutionEvidenceError("generation member bytes are unavailable")
        expected_raw = expected_member_bytes.get(kind)
        if expected_raw is not None and raw != expected_raw:
            raise ExecutionEvidenceError("generation member differs from validated release input")
        actual = (
            member_digest
            if kind == "structural_manifest"
            else _member_digest(kind, raw)
        )
        if actual != member_digest:
            raise ExecutionEvidenceError("generation member digest is invalid")
        coordinates.add(coordinate)
        kinds.append(kind)
        member_coordinates_by_kind.setdefault(kind, []).append(coordinate)
        if kind == "structural_manifest" and (
            member["schema_id"],
            member["schema_version"],
            member["binding_digest"],
        ) != _GENERATION_CTV_BINDINGS["structural_manifest"]:
            raise ExecutionEvidenceError(
                "generation member binding differs from envelope"
            )
        if kind not in {
            "design_document",
            "registry_source",
            "structural_manifest_derivation_ledger",
            "structural_manifest",
        }:
            try:
                typed_envelope = decode_artifact(raw)
                decoded = decode_typed_value(typed_envelope.canonical_value_bytes)
            except CanonicalTypedValueError as exc:
                raise ExecutionEvidenceError("generation typed member bytes are invalid") from exc
            if not isinstance(decoded, dict):
                raise ExecutionEvidenceError("generation typed member body is invalid")
            registered = _GENERATION_CTV_BINDINGS.get(kind)
            if registered is None:
                raise ExecutionEvidenceError("generation artifact kind has no frozen CTV binding")
            release_registered = _CURRENT_RELEASE_MEMBER_BINDINGS.get(kind)
            expected_binding = CanonicalTypedValueProfileBinding(
                *(
                    _CURRENT_RELEASE_MEMBER_PROFILE
                    if release_registered is not None
                    else _GENERATION_PROFILE
                ),
                *(release_registered or registered),
            )
            if (
                typed_envelope.binding != expected_binding
                or (
                    member["schema_id"],
                    member["schema_version"],
                    member["binding_digest"],
                )
                != (release_registered or registered)
            ):
                raise ExecutionEvidenceError("generation member binding differs from envelope")
            _verify_m0_registered_body_shape(kind, decoded)
            member_bodies.setdefault(kind, []).append(decoded)
    if any(kinds.count(kind) != 1 for kind in _GENERATION_SINGLETON_KINDS):
        raise ExecutionEvidenceError("generation member set is incomplete")
    # Rebuild from the two raw authority bytes.  A declared structural root is
    # never authorization: it must equal independent reconstruction.
    from memorii.tools.semantic_ingestion_traceability_checker import rebuild_structural_manifest_bytes

    parse_deadline = monotonic() + 30

    def check_parse_budget() -> None:
        budget.check()
        if monotonic() >= parse_deadline:
            raise ExecutionEvidenceError("structural parser deadline exceeded")

    try:
        rebuilt = rebuild_structural_manifest_bytes(
            design_bytes=design_document_bytes,
            registry=registry,
            registry_bytes=registry_bytes,
            parse_check=check_parse_budget,
            reconstruction_check=budget.check,
        )
    except TraceabilityCoverageError as exc:
        raise ExecutionEvidenceError("structural_derivation_unavailable") from exc
    budget.check()
    ledger = load_checked_in_frozen_structural_manifest_ledger()
    structural_digest = sha256(
        ledger.domain("structural_body")
        + len(rebuilt).to_bytes(8, "big")
        + rebuilt
    ).hexdigest()
    if structural_digest != release_roots.get("structural_manifest_digest"):
        raise ExecutionEvidenceError("independent structural root differs from release")
    marker = b'["structural_mapping_rule_registry_digest",'
    offset = rebuilt.rfind(marker)
    if offset < 0:
        raise ExecutionEvidenceError("independent structural body is invalid")
    structural_body_bytes = (
        rebuilt[:offset]
        + b'["structural_manifest_digest","'
        + structural_digest.encode("ascii")
        + b'"],'
        + rebuilt[offset:]
    )
    structural_binding_spec = _GENERATION_CTV_BINDINGS["structural_manifest"]
    structural_binding = CanonicalTypedValueProfileBinding(
        *_GENERATION_PROFILE, *structural_binding_spec
    )
    structural_value_digest = sha256(structural_body_bytes).hexdigest()
    expected_structural_bytes = encode_typed_value(
        {
            "binding": structural_binding.as_value(),
            "canonical_value_bytes": structural_body_bytes,
            "canonical_value_digest": structural_value_digest,
            "artifact_digest": sha256(
                artifact_preimage(structural_binding, structural_body_bytes)
            ).hexdigest(),
        }
    )
    budget.check()
    if independent_verifier is None:
        raise ExecutionEvidenceError("structural_derivation_unavailable")
    try:
        independent_result = independent_verifier.verify(
            design_bytes=design_document_bytes,
            registry_bytes=registry_bytes,
            ledger_bytes=ledger.raw_bytes,
            expected_body_bytes=rebuilt,
            expected_envelope_bytes=expected_structural_bytes,
        )
        _verify_independent_structural_result(
            independent_result,
            body=rebuilt,
            envelope=expected_structural_bytes,
        )
    except Exception as exc:
        raise ExecutionEvidenceError("structural_derivation_unavailable") from exc
    structural_coordinate = member_coordinates_by_kind.get("structural_manifest", [])
    if (
        len(structural_coordinate) != 1
        or generation_member_bytes.get(structural_coordinate[0])
        != expected_structural_bytes
    ):
        raise ExecutionEvidenceError("generation structural manifest member is missing")
    _verify_loaded_evidence_root(
        kind="coverage_root",
        digest_field="coverage_root_digest",
        domain=b"memorii:sia-traceability-coverage-root:v1\0",
        required_field="approvals",
        structural_digest=structural_digest,
        bodies=member_bodies.get("coverage_root", []),
        release_roots=release_roots,
    )
    _verify_loaded_evidence_root(
        kind="execution_root",
        digest_field="execution_root_digest",
        domain=b"memorii:sia-traceability-execution-root:v1\0",
        required_field="evidence_records",
        structural_digest=structural_digest,
        bodies=member_bodies.get("execution_root", []),
        release_roots=release_roots,
    )
    _verify_m0_pointer_history(
        bodies=member_bodies.get("pointer_history", []),
        active_pointer=pointer,
        lifecycle_artifact=expected_member_bytes.get("trust_lifecycle_root"),
        active_signers=active_signers,
        verify_signature=verify_signature,
        now=now,
    )
    _verify_m0_generation_cross_references(
        member_bodies=member_bodies,
        release_roots=release_roots,
        expected_member_bytes=expected_member_bytes,
        design_document_bytes=design_document_bytes,
        registry_source_identity=manifest["registry_source_identity"],
        active_signers=active_signers,
    )


def _verify_m0_pointer_history(
    *,
    bodies: list[dict[str, object]],
    active_pointer: dict[str, object],
    lifecycle_artifact: object,
    active_signers: tuple[tuple[str, str, str, str, datetime, datetime | None], ...],
    verify_signature: Any,
    now: datetime,
) -> None:
    """Validate the signed predecessor history before publication can select it."""
    if len(bodies) != 1:
        raise ExecutionEvidenceError("generation pointer history is missing")
    history = bodies[0]
    try:
        if not isinstance(lifecycle_artifact, bytes):
            raise CanonicalTypedValueError("missing lifecycle")
        lifecycle = decode_typed_value(decode_artifact(lifecycle_artifact).canonical_value_bytes)
    except CanonicalTypedValueError as exc:
        raise ExecutionEvidenceError("generation pointer lifecycle authority is invalid") from exc
    records = lifecycle.get("records") if isinstance(lifecycle, dict) else None
    if not isinstance(records, list):
        raise ExecutionEvidenceError("generation pointer lifecycle authority is invalid")
    records_by_digest = {
        record.get("record_digest"): record for record in records if isinstance(record, dict)
    }
    coordinate_fields = {
        "source_kind", "signature_purpose", "issuer_id", "key_or_certificate_digest",
        "signature_profile_id", "trust_lifecycle_root_digest",
        "lifecycle_record_digest", "eligible_not_before", "eligible_not_after",
    }

    def authorize_coordinate(value: object, *, purpose: str, published_at: object) -> tuple[str, str]:
        if (
            not isinstance(value, dict)
            or set(value) != coordinate_fields
            or value.get("source_kind") != "prior_verified_lifecycle_root"
            or value.get("signature_purpose") != purpose
        ):
            raise ExecutionEvidenceError("generation pointer signer coordinate is invalid")
        try:
            published = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
            start = datetime.fromisoformat(str(value["eligible_not_before"]).replace("Z", "+00:00"))
            end = None if value["eligible_not_after"] is None else datetime.fromisoformat(str(value["eligible_not_after"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError) as exc:
            raise ExecutionEvidenceError("generation pointer signer interval is invalid") from exc
        record = records_by_digest.get(value.get("lifecycle_record_digest"))
        authorized = any(
            issuer == value.get("issuer_id")
            and profile == value.get("signature_profile_id")
            and key == value.get("key_or_certificate_digest")
            and eligible_start == start
            and eligible_end == end
            for issuer, _, profile, key, eligible_start, eligible_end in active_signers
        )
        if (
            published.tzinfo is None or start.tzinfo is None
            or (end is not None and end.tzinfo is None)
            or not (start <= published and (end is None or published < end))
            or not authorized
            or not isinstance(record, dict)
            or not isinstance(lifecycle, dict)
            or value.get("trust_lifecycle_root_digest") != lifecycle.get("lifecycle_root_digest")
        ):
            raise ExecutionEvidenceError("generation pointer signer is not lifecycle qualified")
        return str(value["signature_profile_id"]), str(value["key_or_certificate_digest"])
    body = {key: value for key, value in history.items() if key not in {"pointer_history_digest", "signature"}}
    digest = sha256(
        b"memorii:sia-traceability-pointer-history:v1\0" + encode_typed_value(body)
    ).hexdigest()
    if history.get("pointer_history_digest") != digest:
        raise ExecutionEvidenceError("generation pointer history digest is invalid")
    signer = history.get("signer_coordinate")
    signature = history.get("signature")
    pointers = history.get("pointers")
    if not isinstance(signer, dict) or not isinstance(signature, str) or not isinstance(pointers, list):
        raise ExecutionEvidenceError("generation pointer history is invalid")
    try:
        signature_bytes = bytes.fromhex(signature)
    except ValueError as exc:
        raise ExecutionEvidenceError("generation pointer history signer is invalid") from exc
    profile, key = authorize_coordinate(
        signer,
        purpose="semantic_ingestion_traceability_pointer_history",
        published_at=active_pointer.get("published_at"),
    )
    preimage = encode_typed_value(
        {
            "issuance_purpose": "semantic_ingestion_traceability_pointer_history",
            "body_binding": history.get("canonical_profile_binding"),
            "pointer_history_digest": digest,
            "signer_coordinate": signer,
        }
    )
    if not verify_signature(profile, key, preimage, signature_bytes):
        raise ExecutionEvidenceError("generation pointer history signature is invalid")
    pointer_fields = {
        "pointer_id", "issuance_purpose", "target_authority_id",
        "canonical_profile_binding", "generation_id", "generation_manifest_digest",
        "release_id", "release_digest", "release_epoch", "release_sequence",
        "release_history_digest", "predecessor_pointer_history_digest",
        "predecessor_active_pointer_digest", "pointer_sequence", "published_at",
        "signer_coordinate", "signature", "active_pointer_digest",
    }
    previous_digest: str | None = None
    for index, pointer in enumerate(pointers):
        if not isinstance(pointer, dict) or set(pointer) != pointer_fields:
            raise ExecutionEvidenceError("generation pointer history entry shape is invalid")
        sequence = pointer.get("pointer_sequence")
        if type(sequence) is not int or sequence != index + 1:
            raise ExecutionEvidenceError("generation pointer history sequence is invalid")
        if pointer.get("predecessor_active_pointer_digest") != previous_digest:
            raise ExecutionEvidenceError("generation pointer history predecessor link is invalid")
        prefix_body = {**body, "pointers": pointers[:index]}
        expected_history_predecessor = (
            None
            if index == 0
            else sha256(
                b"memorii:sia-traceability-pointer-history:v1\0"
                + encode_typed_value(prefix_body)
            ).hexdigest()
        )
        if pointer.get("predecessor_pointer_history_digest") != expected_history_predecessor:
            raise ExecutionEvidenceError("generation pointer history chain digest is invalid")
        pointer_body = {
            key: value
            for key, value in pointer.items()
            if key not in {"active_pointer_digest", "signature"}
        }
        pointer_digest = sha256(
            b"memorii:sia-traceability-active-release-pointer:v1\0"
            + encode_typed_value(pointer_body)
        ).hexdigest()
        if pointer.get("active_pointer_digest") != pointer_digest:
            raise ExecutionEvidenceError("generation pointer history entry digest is invalid")
        pointer_signer = pointer.get("signer_coordinate")
        pointer_signature = pointer.get("signature")
        if not isinstance(pointer_signer, dict) or not isinstance(pointer_signature, str):
            raise ExecutionEvidenceError("generation pointer history entry signature is invalid")
        try:
            pointer_signature_bytes = bytes.fromhex(pointer_signature)
        except ValueError as exc:
            raise ExecutionEvidenceError("generation pointer history entry signature is invalid") from exc
        pointer_profile, pointer_key = authorize_coordinate(
            pointer_signer,
            purpose="semantic_ingestion_traceability_active_release_pointer",
            published_at=pointer.get("published_at"),
        )
        pointer_preimage = encode_typed_value(
            {
                "issuance_purpose": "semantic_ingestion_traceability_active_release_pointer",
                "body_binding": pointer.get("canonical_profile_binding"),
                "active_pointer_digest": pointer_digest,
                "signer_coordinate": pointer_signer,
            }
        )
        if not verify_signature(
            pointer_profile,
            pointer_key,
            pointer_preimage,
            pointer_signature_bytes,
        ):
            raise ExecutionEvidenceError("generation pointer history entry signature is invalid")
        previous_digest = pointer_digest
    active_sequence = active_pointer.get("pointer_sequence")
    if type(active_sequence) is not int or active_sequence != len(pointers) + 1:
        raise ExecutionEvidenceError("generation active pointer sequence is not history contiguous")
    expected_active_history = digest if pointers else None
    if active_pointer.get("predecessor_pointer_history_digest") != expected_active_history:
        raise ExecutionEvidenceError("generation active pointer history link is invalid")
    if pointers:
        tail = pointers[-1]
        if not isinstance(tail, dict) or tail.get("active_pointer_digest") != active_pointer.get("predecessor_active_pointer_digest"):
            raise ExecutionEvidenceError("generation pointer history tail is invalid")
    elif active_pointer.get("predecessor_active_pointer_digest") is not None:
        raise ExecutionEvidenceError("generation pointer history predecessor is invalid")


def _verify_m0_manifest_graph(
    members: list[object],
    generation_member_bytes: dict[str, bytes],
    budget: _GenerationVerificationBudget | None = None,
) -> None:
    """Reject membership/DAG mutations before decoding large member bodies."""
    coordinates: set[str] = set()
    coordinate_by_kind: dict[str, str] = {}
    kinds: list[str] = []
    for member in members:
        if budget is not None:
            budget.check()
        if not isinstance(member, dict) or set(member) != {
            "artifact_kind",
            "artifact_coordinate",
            "artifact_digest",
            "depends_on_coordinates",
            "schema_id",
            "schema_version",
            "binding_digest",
        }:
            raise ExecutionEvidenceError("generation member shape is invalid")
        kind = member["artifact_kind"]
        coordinate = member["artifact_coordinate"]
        digest = member["artifact_digest"]
        dependencies = member["depends_on_coordinates"]
        if (
            not isinstance(kind, str)
            or kind not in _GENERATION_KINDS
            or not isinstance(coordinate, str)
            or not isinstance(digest, str)
            or not isinstance(dependencies, list)
            or coordinate != _coordinate(kind, digest)
            or coordinate in coordinates
            or any(not isinstance(dependency, str) or dependency not in coordinates for dependency in dependencies)
        ):
            raise ExecutionEvidenceError("generation member coordinate or order is invalid")
        coordinates.add(coordinate)
        coordinate_by_kind[kind] = coordinate
        kinds.append(kind)
    if set(generation_member_bytes) != coordinates or tuple(kinds) != _M0_GENERATION_ORDER:
        raise ExecutionEvidenceError("generation member set is incomplete")
    for member in members:
        if not isinstance(member, dict):
            raise ExecutionEvidenceError("generation member shape is invalid")
        kind = member["artifact_kind"]
        if not isinstance(kind, str):
            raise ExecutionEvidenceError("generation member metadata is invalid")
        expected = sorted(coordinate_by_kind[dependency_kind] for dependency_kind in _M0_GENERATION_DEPENDENCIES[kind])
        if member["depends_on_coordinates"] != expected:
            raise ExecutionEvidenceError("generation dependency closure is invalid")
    declared_index = {
        member["artifact_coordinate"]: index for index, member in enumerate(members) if isinstance(member, dict)
    }
    remaining = {
        member["artifact_coordinate"]: set(member["depends_on_coordinates"])
        for member in members
        if isinstance(member, dict)
    }
    emitted: list[str] = []
    while remaining:
        ready = sorted(
            (coordinate for coordinate, deps in remaining.items() if not deps),
            key=declared_index.__getitem__,
        )
        if not ready:
            raise ExecutionEvidenceError("generation dependency graph is cyclic")
        coordinate = ready[0]
        emitted.append(coordinate)
        del remaining[coordinate]
        for dependencies in remaining.values():
            dependencies.discard(coordinate)
    if emitted != list(declared_index):
        raise ExecutionEvidenceError("generation member order is not canonical")


def _verify_m0_generation_cross_references(
    *,
    member_bodies: dict[str, list[dict[str, object]]],
    release_roots: dict[str, str],
    expected_member_bytes: dict[str, object],
    design_document_bytes: bytes,
    registry_source_identity: object,
    active_signers: tuple[tuple[str, str, str, str, datetime, datetime | None], ...],
) -> None:
    def one(kind: str) -> dict[str, object]:
        bodies = member_bodies.get(kind, [])
        if len(bodies) != 1:
            raise ExecutionEvidenceError(f"generation {kind} cross-reference body is missing")
        return bodies[0]

    expected_decoded: dict[str, dict[str, object]] = {}
    for kind in ("bootstrap_anchor", "recovery_root", "recovery_policy"):
        raw = expected_member_bytes.get(kind)
        if not isinstance(raw, bytes):
            raise ExecutionEvidenceError(
                f"generation {kind} validated input is invalid"
            )
        try:
            decoded = decode_typed_value(decode_artifact(raw).canonical_value_bytes)
        except CanonicalTypedValueError as exc:
            raise ExecutionEvidenceError(f"generation {kind} validated input is invalid") from exc
        if not isinstance(decoded, dict):
            raise ExecutionEvidenceError(f"generation {kind} validated input is invalid")
        expected_decoded[kind] = decoded

    history_specs = (
        (
            "bootstrap_anchor_history",
            "anchors",
            "bootstrap_anchor",
            b"memorii:sia-traceability-bootstrap-anchor-history:v1\0",
        ),
        (
            "recovery_root_history",
            "recovery_roots",
            "recovery_root",
            b"memorii:sia-traceability-recovery-root-history:v1\0",
        ),
        (
            "recovery_policy_history",
            "policies",
            "recovery_policy",
            b"memorii:sia-traceability-recovery-policy-history:v1\0",
        ),
    )
    for kind, collection, input_kind, domain in history_specs:
        history = one(kind)
        expected_history_values = [expected_decoded[input_kind]]
        if input_kind == "bootstrap_anchor":
            bootstrap_inputs = expected_member_bytes.get("bootstrap_anchors")
            if not isinstance(bootstrap_inputs, tuple) or not all(
                isinstance(raw, bytes) for raw in bootstrap_inputs
            ):
                raise ExecutionEvidenceError(
                    "generation bootstrap anchors validated inputs are invalid"
                )
            try:
                expected_history_values = [
                    decode_typed_value(decode_artifact(raw).canonical_value_bytes)
                    for raw in bootstrap_inputs
                ]
            except CanonicalTypedValueError as exc:
                raise ExecutionEvidenceError(
                    "generation bootstrap anchors validated inputs are invalid"
                ) from exc
        if input_kind == "recovery_root":
            recovery_inputs = expected_member_bytes.get("recovery_roots")
            if not isinstance(recovery_inputs, tuple) or not all(
                isinstance(raw, bytes) for raw in recovery_inputs
            ):
                raise ExecutionEvidenceError(
                    "generation recovery roots validated inputs are invalid"
                )
            try:
                expected_history_values = [
                    decode_typed_value(decode_artifact(raw).canonical_value_bytes)
                    for raw in recovery_inputs
                ]
            except CanonicalTypedValueError as exc:
                raise ExecutionEvidenceError(
                    "generation recovery roots validated inputs are invalid"
                ) from exc
        if history.get(collection) != expected_history_values:
            raise ExecutionEvidenceError(f"generation {kind} does not contain the exact validated history")
        supplied_digest = history.get("history_digest")
        history_body = {key: value for key, value in history.items() if key != "history_digest"}
        recomputed = sha256(domain + encode_typed_value(history_body)).hexdigest()
        if supplied_digest != recomputed:
            raise ExecutionEvidenceError(f"generation {kind} digest is invalid")

    snapshot = one("trust_snapshot")
    snapshot_body = {key: value for key, value in snapshot.items() if key != "trust_snapshot_digest"}
    snapshot_digest = sha256(
        b"memorii:sia-traceability-release-trust-snapshot:v1\0" + encode_typed_value(snapshot_body)
    ).hexdigest()
    release = one("release")
    lifecycle = one("trust_lifecycle_root")
    lifecycle_records = lifecycle.get("records")
    terminal_record_digest = (
        lifecycle_records[-1].get("record_digest")
        if isinstance(lifecycle_records, list) and lifecycle_records and isinstance(lifecycle_records[-1], dict)
        else None
    )
    qualified = snapshot.get("qualified_issuers")
    qualified_coordinates = (
        {
            (
                item.get("issuer_id"),
                item.get("signature_profile_id"),
                item.get("key_or_certificate_digest"),
                item.get("trust_lifecycle_root_digest"),
                item.get("lifecycle_record_digest"),
            )
            for item in qualified
            if isinstance(item, dict)
        }
        if isinstance(qualified, list)
        else set()
    )
    expected_qualified = {
        (
            signer_id,
            profile,
            key,
            lifecycle.get("lifecycle_root_digest"),
            terminal_record_digest,
        )
        for signer_id, _, profile, key, _, _ in active_signers
    }
    if (
        snapshot.get("trust_snapshot_digest") != snapshot_digest
        or release_roots.get("trust_snapshot_digest") != snapshot_digest
        or snapshot.get("release_id") != release.get("release_id")
        or snapshot.get("release_epoch") != release.get("epoch")
        or snapshot.get("release_sequence") != release.get("sequence")
        or snapshot.get("bootstrap_anchor_digest") != release.get("bootstrap_anchor_digest")
        or snapshot.get("recovery_policy_digest") != expected_decoded["recovery_policy"].get("recovery_policy_digest")
        or snapshot.get("trust_lifecycle_root_digest") != lifecycle.get("lifecycle_root_digest")
        or qualified_coordinates != expected_qualified
    ):
        raise ExecutionEvidenceError("generation trust snapshot is not release/lifecycle bound")

    golden = one("golden_vector_manifest")
    golden_body = {key: value for key, value in golden.items() if key != "golden_vector_manifest_digest"}
    golden_digest = sha256(
        b"memorii:sia-traceability-approval-golden-vectors:v1\0" + encode_typed_value(golden_body)
    ).hexdigest()
    if (
        golden.get("golden_vector_manifest_digest") != golden_digest
        or golden.get("design_document_digest")
        != sha256(b"semantic-ingestion-traceability\0" + design_document_bytes).hexdigest()
        or golden.get("registry_source_identity") != registry_source_identity
        or golden.get("fixtures") != []
    ):
        raise ExecutionEvidenceError("generation golden vector manifest cross-reference is invalid")


def _verify_loaded_evidence_root(
    *,
    kind: str,
    digest_field: str,
    domain: bytes,
    required_field: str,
    structural_digest: str,
    bodies: list[dict[str, object]],
    release_roots: dict[str, str],
) -> None:
    """Recompute a root from the exact decoded member body, never its spelling."""
    if len(bodies) != 1:
        raise ExecutionEvidenceError(f"generation {kind} member is missing")
    body = bodies[0]
    if set(body) != {"structural_manifest_digest", required_field, digest_field}:
        raise ExecutionEvidenceError(f"generation {kind} body is invalid")
    if body["structural_manifest_digest"] != structural_digest or not isinstance(body[required_field], list):
        raise ExecutionEvidenceError(f"generation {kind} structural binding is invalid")
    preimage = {
        "structural_manifest_digest": structural_digest,
        required_field: body[required_field],
    }
    recomputed = sha256(domain + encode_typed_value(preimage)).hexdigest()
    if body[digest_field] != recomputed or recomputed != release_roots.get(digest_field):
        raise ExecutionEvidenceError(f"generation {kind} differs from release")


def _coordinate(kind: object, digest: object) -> str:
    if not isinstance(kind, str) or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ExecutionEvidenceError("generation coordinate is invalid")
    return f"sia-traceability/v1/{kind}/{digest}"


def _member_digest(kind: str, raw: bytes) -> str:
    if kind == "design_document":
        return sha256(b"semantic-ingestion-traceability\0" + raw).hexdigest()
    if kind == "registry_source":
        return sha256(b"memorii:sia-traceability-source:v1\0" + raw).hexdigest()
    if kind == "structural_manifest_derivation_ledger":
        try:
            return load_frozen_structural_manifest_ledger(raw).digest
        except StructuralLedgerError as exc:
            raise ExecutionEvidenceError("generation raw derivation ledger is invalid") from exc
    try:
        return decode_artifact(raw).artifact_digest
    except CanonicalTypedValueError as exc:
        raise ExecutionEvidenceError("generation typed member bytes are invalid") from exc


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
    if sha256(b"memorii:sia-report-schema:v1\0" + canonical_document(report_schema)).hexdigest() != group.get(
        "expected_report_schema_digest"
    ):
        raise ExecutionEvidenceError("registered report schema bytes are not authorized")
    if sha256(
        b"memorii:sia-runner-environment-profile:v1\0" + canonical_document(runner_environment_profile)
    ).hexdigest() != group.get("expected_runner_environment_profile_digest"):
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
    if (
        not isinstance(observation_artifact, str)
        or artifacts.get(observation_artifact) != environment_observation_bytes
    ):
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
    required = {
        "interpreter",
        "runner",
        "plugins",
        "configuration",
        "dependencies",
        "import_paths",
        "startup",
        "environment",
        "locale_timezone",
        "network",
    }
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
        if (
            not isinstance(properties, dict)
            or not isinstance(required, list)
            or any(name not in value for name in required)
        ):
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
    if (report["schema_id"], report["schema_version"]) != (
        group.get("report_schema_id"),
        group.get("report_schema_version"),
    ):
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
