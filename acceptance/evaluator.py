"""Orchestrate acceptance verification, numeric recomputation, and publication."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import asdict, replace
from datetime import datetime
from hashlib import sha256
from io import BytesIO
import json
from typing import TYPE_CHECKING, Protocol, TypedDict, runtime_checkable

from acceptance.capability_baseline_approval import (
    ApprovalRejected,
    CapabilityBaselineApprovalVerifier,
    DeploymentAuthorizationBridge,
    EvaluationReceipt,
    _digest_for,
)
from acceptance.deployment_bridge import SerializedDeploymentPublisher
from acceptance.statistical_certification import HeldBinding, TransportLimits, WireRejected, verify_certificate
from acceptance.schema_registry import canonical_digest, signing_preimage

if TYPE_CHECKING:
    from acceptance.authority_repository import (
        AcceptanceAuthorityRepository,
        AcceptanceEvaluationSnapshot,
    )


class AcceptanceEvaluationError(ValueError):
    """The evaluator did not publish a receipt or deployment authorization."""


@runtime_checkable
class RegisteredEvaluationReceiptStore(Protocol):
    """Durable store for registered, signed evaluation receipts."""

    def publish(self, digest: str, raw: bytes) -> None: ...


@runtime_checkable
class DurableEvaluationAttemptStore(RegisteredEvaluationReceiptStore, Protocol):
    """Immutable pre-publication record for restart-safe authority runs."""

    def load_attempt(self, attempt_digest: str) -> tuple[bytes, bytes] | None: ...

    def prepare_attempt(
        self, attempt_digest: str, authorization: bytes, receipt: bytes
    ) -> tuple[bytes, bytes]: ...


@runtime_checkable
class NumericContextResolver(Protocol):
    def resolve(
        self, *, baseline_bytes: bytes, release_bytes: bytes,
        policy_bytes: bytes, evidence_bytes: bytes,
    ) -> HeldBinding: ...


@runtime_checkable
class LegacyEvaluationReceiptStore(Protocol):
    """Compatibility store for non-authoritative in-process evaluation."""

    def publish_if_absent(self, receipt: EvaluationReceipt) -> EvaluationReceipt: ...


class _DeploymentAuthorizationRequestBody(TypedDict):
    purpose: str
    target_kind: str
    target_artifact_digest: str
    deployment_manifest_digest: str
    capability_fingerprint: str
    verified_capability_baseline_approval_release_digest: str
    requested_active_epoch: int
    expires_at: str


class _DeploymentAuthorizationRequest(_DeploymentAuthorizationRequestBody):
    issuance_request_digest: str


class SerializedDeploymentAuthorizationBridge:
    """Typed adapter for the installed bytes-only production boundary."""

    def __init__(self, publisher: SerializedDeploymentPublisher) -> None:
        self._publisher = publisher

    def prepare(self, request: _DeploymentAuthorizationRequest) -> bytes:
        return self._publisher.prepare_verified(
            json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        )

    def publish(self, artifact: bytes) -> None:
        try:
            self._publisher.publish_prepared(artifact)
        except (OSError, ValueError):
            # A transport acknowledgement can be lost after the file became
            # durable.  Exact visibility is the reconciliation authority.
            if not self._publisher.visible_exact(artifact):
                raise


class AcceptanceEvaluator:
    """Constructor-held authority prevents CLI callers from injecting trust context."""

    def __init__(
        self,
        *,
        approval_verifier: CapabilityBaselineApprovalVerifier,
        numeric_binding: HeldBinding | None,
        numeric_limits: TransportLimits,
        receipt_store: LegacyEvaluationReceiptStore | RegisteredEvaluationReceiptStore,
        deployment_issuer: DeploymentAuthorizationBridge | SerializedDeploymentAuthorizationBridge,
        now_provider: Callable[[], datetime],
        authority_repository: "AcceptanceAuthorityRepository | None" = None,
        evaluator_subject_id: str | None = None,
        artifact_signer: Callable[[bytes], str] | None = None,
        evaluator_signing_key_coordinate: str | None = None,
        numeric_context_resolver: NumericContextResolver | None = None,
    ) -> None:
        if (
            type(numeric_limits) is not TransportLimits
            or (type(numeric_binding) is HeldBinding) == isinstance(numeric_context_resolver, NumericContextResolver)
        ):
            raise AcceptanceEvaluationError("acceptance_numeric_authority")
        self._approval_verifier = approval_verifier
        self._numeric_binding = numeric_binding
        self._numeric_context_resolver = numeric_context_resolver
        self._numeric_limits = numeric_limits
        self._receipt_store = receipt_store
        self._deployment_issuer = deployment_issuer
        self._now_provider = now_provider
        self._authority_repository = authority_repository
        self._evaluator_subject_id = evaluator_subject_id
        # Receipt signing is configured by the installed runtime. Keeping it on
        # the evaluator prevents candidate input from selecting a signer.
        self._artifact_signer = artifact_signer
        self._evaluator_signing_key_coordinate = evaluator_signing_key_coordinate

    def evaluate_and_publish(
        self,
        *,
        release_bytes: bytes,
        baseline_bytes: bytes,
        policy_bytes: bytes,
        evidence_bytes: bytes,
        certificate_bytes: bytes,
        deployment_manifest_digest: str,
    ) -> EvaluationReceipt:
        now = self._now_provider()
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise AcceptanceEvaluationError("acceptance_clock")
        lease = nullcontext(None)
        if self._authority_repository is not None:
            lease = self._authority_repository.begin_evaluation(now)
        with lease as snapshot:
            if snapshot is not None and hasattr(self._approval_verifier, "select_snapshot"):
                self._approval_verifier.select_snapshot(snapshot)
            return self._evaluate_under_snapshot(
                snapshot, now, release_bytes, baseline_bytes, policy_bytes, evidence_bytes,
                certificate_bytes, deployment_manifest_digest,
            )

    def _evaluate_under_snapshot(
        self,
        snapshot: "AcceptanceEvaluationSnapshot | None",
        now: datetime,
        release_bytes: bytes,
        baseline_bytes: bytes,
        policy_bytes: bytes,
        evidence_bytes: bytes,
        certificate_bytes: bytes,
        deployment_manifest_digest: str,
    ) -> EvaluationReceipt:
        # A fenced snapshot is the authority's evaluation clock.  It is the
        # only timestamp that may enter a signed receipt for durable runs.
        if snapshot is not None:
            snapshot_time = getattr(snapshot, "evaluated_at", None)
            if not isinstance(snapshot_time, datetime) or snapshot_time.utcoffset() is None:
                raise AcceptanceEvaluationError("acceptance_snapshot_clock")
            now = snapshot_time
        try:
            verified = self._approval_verifier.verify(release_bytes, baseline_bytes, now)
            binding = self._numeric_binding
            if self._numeric_context_resolver is not None:
                binding = self._numeric_context_resolver.resolve(
                    baseline_bytes=baseline_bytes, release_bytes=release_bytes,
                    policy_bytes=policy_bytes, evidence_bytes=evidence_bytes,
                )
            if type(binding) is not HeldBinding:
                raise AcceptanceEvaluationError("acceptance_numeric_authority")
            certificate = verify_certificate(BytesIO(certificate_bytes), BytesIO(policy_bytes), BytesIO(evidence_bytes), binding, self._numeric_limits)
        except (ApprovalRejected, WireRejected, ValueError) as exc:
            raise AcceptanceEvaluationError("acceptance_evaluation_rejected") from exc
        if not certificate.accepted:
            raise AcceptanceEvaluationError("acceptance_certificate_not_approved")
        expected_numeric_authority = {
            "approved_baseline_artifact_digest": verified.target_approved_capability_baseline_artifact_digest,
            "verified_baseline_approval_release_digest": verified.release_digest,
            **{name: getattr(verified, name) for name in (
                "capability_fingerprint", "capability_contract_digest", "coverage_manifest_digest",
                "coverage_release_id", "statistical_gate_manifest_digest", "sampling_frame_manifest_digest",
                "sampling_frame_digest", "independent_cluster_definition_digest", "strata_definition_digest",
                "cluster_weighting_digest", "numeric_encoding_registry_digest", "unsupported_cells_digest",
            )},
        }
        if asdict(certificate.authority) != expected_numeric_authority:
            raise AcceptanceEvaluationError("acceptance_numeric_authority_binding")
        request_body: _DeploymentAuthorizationRequestBody = {
            "purpose": "semantic_ingestion_capability_baseline",
            "target_kind": "capability_baseline",
            "target_artifact_digest": verified.target_approved_capability_baseline_artifact_digest,
            "deployment_manifest_digest": deployment_manifest_digest,
            "capability_fingerprint": certificate.authority.capability_fingerprint,
            "verified_capability_baseline_approval_release_digest": verified.release_digest,
            "requested_active_epoch": verified.acceptance_release_epoch,
            # The production serialized request has a canonical UTC timestamp;
            # its digest owner rejects an equivalent but differently encoded
            # ``+00:00`` representation.
            "expires_at": self._approval_expiry(release_bytes).isoformat().replace("+00:00", "Z"),
        }
        # This crosses the serialized production boundary.  Its digest is
        # defined by the production JSON contract rather than acceptance CTV.
        issuance_request_digest = sha256(
            b"memorii.deployment-authorization.request.v1\0"
            + json.dumps(request_body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        ).hexdigest()
        request: _DeploymentAuthorizationRequest = {
            "purpose": request_body["purpose"],
            "target_kind": request_body["target_kind"],
            "target_artifact_digest": request_body["target_artifact_digest"],
            "deployment_manifest_digest": request_body["deployment_manifest_digest"],
            "capability_fingerprint": request_body["capability_fingerprint"],
            "verified_capability_baseline_approval_release_digest": request_body[
                "verified_capability_baseline_approval_release_digest"
            ],
            "requested_active_epoch": request_body["requested_active_epoch"],
            "expires_at": request_body["expires_at"],
            "issuance_request_digest": issuance_request_digest,
        }
        if snapshot is not None and isinstance(self._receipt_store, DurableEvaluationAttemptStore):
            return self._publish_durable_attempt(
                snapshot, request, now, verified.verification_digest, certificate_bytes,
                policy_bytes, evidence_bytes,
            )
        artifact = self._prepare_authorization(request)
        authorization_digest = self._authorization_digest(artifact)
        if not isinstance(authorization_digest, str) or len(authorization_digest) != 64:
            raise AcceptanceEvaluationError("deployment_issuer_outcome")
        receipt_digest_body = {
            "verified_approval_digest": verified.verification_digest,
            "certificate_digest": sha256(certificate_bytes).hexdigest(),
            "policy_digest": sha256(policy_bytes).hexdigest(),
            "evidence_digest": sha256(evidence_bytes).hexdigest(),
            "deployment_authorization_digest": authorization_digest,
            "published_at": now.isoformat(),
        }
        receipt = EvaluationReceipt(
            receipt_digest=_digest_for(b"memorii.acceptance.evaluation-receipt.v1", receipt_digest_body),
            verified_approval_digest=verified.verification_digest,
            certificate_digest=sha256(certificate_bytes).hexdigest(),
            policy_digest=sha256(policy_bytes).hexdigest(),
            evidence_digest=sha256(evidence_bytes).hexdigest(),
            deployment_authorization_digest=authorization_digest,
            published_at=now,
        )
        published = self._publish_receipt(receipt, snapshot, now)
        # The production bridge receives only its canonical request/artifact bytes.
        self._publish_authorization(artifact)
        return published

    def _publish_durable_attempt(
        self,
        snapshot: "AcceptanceEvaluationSnapshot",
        request: _DeploymentAuthorizationRequest,
        now: datetime,
        verified_approval_digest: str,
        certificate_bytes: bytes,
        policy_bytes: bytes,
        evidence_bytes: bytes,
    ) -> EvaluationReceipt:
        store = self._receipt_store
        assert isinstance(store, DurableEvaluationAttemptStore)
        attempt_digest = sha256(
            json.dumps(
                {
                    "authority_commit_digest": snapshot.commit_digest,
                    "release_request": request,
                    "certificate_sha256": sha256(certificate_bytes).hexdigest(),
                    "policy_sha256": sha256(policy_bytes).hexdigest(),
                    "evidence_sha256": sha256(evidence_bytes).hexdigest(),
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("ascii")
        ).hexdigest()
        prepared = store.load_attempt(attempt_digest)
        if prepared is None:
            authorization = self._prepare_authorization(request)
            if not isinstance(authorization, bytes):
                raise AcceptanceEvaluationError("deployment_issuer_outcome")
            authorization_digest = self._authorization_digest(authorization)
            if not isinstance(authorization_digest, str):
                raise AcceptanceEvaluationError("deployment_issuer_outcome")
            receipt = EvaluationReceipt(
                receipt_digest="0" * 64,
                verified_approval_digest=verified_approval_digest,
                certificate_digest=sha256(certificate_bytes).hexdigest(),
                policy_digest=sha256(policy_bytes).hexdigest(),
                evidence_digest=sha256(evidence_bytes).hexdigest(),
                deployment_authorization_digest=authorization_digest,
                published_at=now,
            )
            _, receipt_raw = self._registered_receipt_bytes(receipt, snapshot, now)
            prepared = store.prepare_attempt(attempt_digest, authorization, receipt_raw)
        authorization, receipt_raw = prepared
        # Reconcile an uncertain production acknowledgement before publishing
        # the dependent receipt; both bytes came from the immutable attempt.
        self._publish_authorization(authorization)
        try:
            receipt_value = json.loads(receipt_raw)
            digest = receipt_value["receipt_digest"]
        except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AcceptanceEvaluationError("acceptance_attempt_receipt") from exc
        store.publish(digest, receipt_raw)
        return self._receipt_from_registered(receipt_raw)

    def _publish_receipt(
        self,
        receipt: EvaluationReceipt,
        snapshot: "AcceptanceEvaluationSnapshot | None",
        now: datetime,
    ) -> EvaluationReceipt:
        if snapshot is None:
            if not isinstance(self._receipt_store, LegacyEvaluationReceiptStore):
                raise AcceptanceEvaluationError("acceptance_receipt_authority")
            return self._receipt_store.publish_if_absent(receipt)
        commit_digest = snapshot.commit_digest
        if (
            not isinstance(commit_digest, str)
            or self._artifact_signer is None
            or not self._evaluator_subject_id
            or not self._evaluator_signing_key_coordinate
            or not isinstance(self._receipt_store, RegisteredEvaluationReceiptStore)
        ):
            raise AcceptanceEvaluationError("acceptance_receipt_authority")
        digest, raw = self._registered_receipt_bytes(receipt, snapshot, now)
        try:
            self._receipt_store.publish(digest, raw)
        except (TypeError, ValueError) as exc:
            raise AcceptanceEvaluationError("acceptance_receipt_authority") from exc
        return replace(receipt, receipt_digest=digest, published_at=now)

    def _registered_receipt_bytes(
        self, receipt: EvaluationReceipt, snapshot: "AcceptanceEvaluationSnapshot", now: datetime
    ) -> tuple[str, bytes]:
        if (
            self._artifact_signer is None
            or not self._evaluator_subject_id
            or not self._evaluator_signing_key_coordinate
        ):
            raise AcceptanceEvaluationError("acceptance_receipt_authority")
        unsigned = {
            "schema_version": 1,
            "purpose": "acceptance_evaluation_receipt",
            "authority_commit_digest": snapshot.commit_digest,
            "verified_approval_digest": receipt.verified_approval_digest,
            "certificate_digest": receipt.certificate_digest,
            "policy_digest": receipt.policy_digest,
            "evidence_digest": receipt.evidence_digest,
            "deployment_authorization_digest": receipt.deployment_authorization_digest,
            "evaluated_at": now.isoformat().replace("+00:00", "Z"),
            "evaluator_subject_id": self._evaluator_subject_id,
            "signing_key_coordinate": self._evaluator_signing_key_coordinate,
        }
        digest = canonical_digest("memorii.acceptance.evaluation-receipt.v1", "registered", unsigned)
        value = {**unsigned, "receipt_digest": digest, "signature": "0" * 128}
        try:
            value["signature"] = self._artifact_signer(
                signing_preimage("AcceptanceEvaluationReceipt", value, self._evaluator_signing_key_coordinate)
            )
            return digest, json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        except (TypeError, ValueError) as exc:
            raise AcceptanceEvaluationError("acceptance_receipt_authority") from exc

    @staticmethod
    def _receipt_from_registered(raw: bytes) -> EvaluationReceipt:
        try:
            value = json.loads(raw)
            evaluated = datetime.fromisoformat(value["evaluated_at"].replace("Z", "+00:00"))
            return EvaluationReceipt(
                value["receipt_digest"], value["verified_approval_digest"], value["certificate_digest"],
                value["policy_digest"], value["evidence_digest"], value["deployment_authorization_digest"], evaluated,
            )
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AcceptanceEvaluationError("acceptance_attempt_receipt") from exc

    def _prepare_authorization(self, request: _DeploymentAuthorizationRequest) -> object:
        bridge = self._deployment_issuer
        if not isinstance(bridge, SerializedDeploymentAuthorizationBridge):
            prepared = bridge.prepare_verified(
                target_artifact_digest=request["target_artifact_digest"],
                deployment_manifest_digest=request["deployment_manifest_digest"],
                capability_fingerprint=request["capability_fingerprint"],
                verified_capability_baseline_approval_release_digest=request["verified_capability_baseline_approval_release_digest"],
                requested_active_epoch=request["requested_active_epoch"],
                expires_at=self._approval_expiry_from_request(request),
            )
            return prepared
        try:
            return bridge.prepare(request)
        except (AttributeError, TypeError, ValueError) as exc:
            raise AcceptanceEvaluationError("deployment_issuer_outcome") from exc

    @staticmethod
    def _approval_expiry_from_request(request: _DeploymentAuthorizationRequest) -> datetime:
        return datetime.fromisoformat(request["expires_at"].replace("Z", "+00:00"))

    @staticmethod
    def _authorization_digest(artifact: object) -> str | None:
        if isinstance(artifact, bytes):
            try:
                value = json.loads(artifact)
            except (UnicodeDecodeError, json.JSONDecodeError):
                return None
            if json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii") != artifact:
                return None
            return value.get("authorization_digest") if type(value) is dict else None
        return getattr(artifact, "authorization_digest", None)

    def _publish_authorization(self, artifact: object) -> None:
        try:
            if isinstance(self._deployment_issuer, SerializedDeploymentAuthorizationBridge):
                if not isinstance(artifact, bytes):
                    raise TypeError("serialized deployment artifact required")
                self._deployment_issuer.publish(artifact)
            else:
                self._deployment_issuer.publish_prepared(artifact)
        except (AttributeError, TypeError, ValueError) as exc:
            raise AcceptanceEvaluationError("deployment_issuer_outcome") from exc

    @staticmethod
    def _approval_expiry(release_bytes: bytes) -> datetime:
        # The approval verifier has already validated this closed value.  Reparse only
        # to pass the exact release expiry into the production issuer.
        import json
        try:
            value = json.loads(release_bytes)
            expiry = datetime.fromisoformat(value["expires_at"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AcceptanceEvaluationError("approval_release_expiry") from exc
        if expiry.utcoffset() is None:
            raise AcceptanceEvaluationError("approval_release_expiry")
        return expiry


__all__ = [
    "AcceptanceEvaluationError",
    "AcceptanceEvaluator",
    "DurableEvaluationAttemptStore",
    "NumericContextResolver",
    "LegacyEvaluationReceiptStore",
    "RegisteredEvaluationReceiptStore",
    "SerializedDeploymentAuthorizationBridge",
]
