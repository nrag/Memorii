"""Production-owned deployment authorization issuance.

This module deliberately accepts only already verified digest coordinates.  It
does not import the acceptance package or decode an approval release: the
acceptance evaluator is responsible for that boundary before it calls the
issuer.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_Purpose = Literal[
    "semantic_ingestion_capability_baseline",
    "semantic_ingestion_local_resource_profile",
    "semantic_ingestion_topology",
]
_TargetKind = Literal["capability_baseline", "local_resource_profile", "topology"]


class DeploymentAuthorizationError(ValueError):
    """An issuance request cannot create a deployment authorization."""


def _secure_path(path: Path, failure: str) -> None:
    """Reject aliases at every existing coordinate before opening authority data."""
    current = path
    while True:
        if current.is_symlink():
            raise DeploymentAuthorizationError(failure)
        if current.parent == current:
            return
        current = current.parent


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _digest(domain: bytes, value: object) -> str:
    return sha256(domain + b"\0" + _canonical_bytes(value)).hexdigest()


def _time_json(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


class DeploymentAuthorizationIssuanceRequest(BaseModel):
    """Digest-only request supplied by an independently verified evaluator."""

    purpose: _Purpose
    target_kind: _TargetKind
    target_artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    deployment_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    verified_capability_baseline_approval_release_digest: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    requested_active_epoch: int = Field(ge=1)
    expires_at: datetime
    issuance_request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def _validate_request(self) -> DeploymentAuthorizationIssuanceRequest:
        expected_pair = {
            "semantic_ingestion_capability_baseline": "capability_baseline",
            "semantic_ingestion_local_resource_profile": "local_resource_profile",
            "semantic_ingestion_topology": "topology",
        }
        if expected_pair[self.purpose] != self.target_kind:
            raise ValueError("deployment_authorization_target_kind")
        if self.expires_at.utcoffset() is None:
            raise ValueError("deployment_authorization_expiry_timezone")
        approval = self.verified_capability_baseline_approval_release_digest
        if (self.target_kind == "capability_baseline") != (approval is not None):
            raise ValueError("deployment_authorization_approval_binding")
        body = self.model_dump(mode="json", exclude={"issuance_request_digest"})
        if self.issuance_request_digest != _digest(b"memorii.deployment-authorization.request.v1", body):
            raise ValueError("deployment_authorization_request_digest")
        return self

    @classmethod
    def create(
        cls,
        *,
        purpose: _Purpose,
        target_kind: _TargetKind,
        target_artifact_digest: str,
        deployment_manifest_digest: str,
        capability_fingerprint: str | None,
        verified_capability_baseline_approval_release_digest: str | None,
        requested_active_epoch: int,
        expires_at: datetime,
    ) -> DeploymentAuthorizationIssuanceRequest:
        body = {
            "purpose": purpose,
            "target_kind": target_kind,
            "target_artifact_digest": target_artifact_digest,
            "deployment_manifest_digest": deployment_manifest_digest,
            "capability_fingerprint": capability_fingerprint,
            "verified_capability_baseline_approval_release_digest": verified_capability_baseline_approval_release_digest,
            "requested_active_epoch": requested_active_epoch,
            "expires_at": _time_json(expires_at),
        }
        return cls(**body, issuance_request_digest=_digest(b"memorii.deployment-authorization.request.v1", body))


class DeploymentAuthorizationArtifact(BaseModel):
    """Signed production artifact; acceptance state is represented only by a digest."""

    schema_version: Literal[1] = 1
    purpose: _Purpose
    target_kind: _TargetKind
    target_artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    deployment_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    verified_capability_baseline_approval_release_digest: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    signer_subject_id: str = Field(min_length=1)
    signing_key_reference: str = Field(min_length=1)
    authority_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    active_epoch: int = Field(ge=1)
    issued_at: datetime
    expires_at: datetime
    authorization_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def _validate_artifact(self) -> DeploymentAuthorizationArtifact:
        if self.issued_at.utcoffset() is None or self.expires_at.utcoffset() is None or self.expires_at <= self.issued_at:
            raise ValueError("deployment_authorization_interval")
        body = self.model_dump(mode="json", exclude={"authorization_digest", "signature"})
        if self.authorization_digest != _digest(b"memorii.deployment-authorization.artifact.v1", body):
            raise ValueError("deployment_authorization_digest")
        return self


class DeploymentAuthorizationSigner(Protocol):
    def sign(self, preimage: bytes) -> str: ...


class DeploymentAuthorizationSignatureVerifier(Protocol):
    def verify(self, *, signing_key_reference: str, preimage: bytes, signature: str) -> bool: ...


class DeploymentAuthorizationRepository(Protocol):
    def publish_if_absent(self, artifact: DeploymentAuthorizationArtifact) -> DeploymentAuthorizationArtifact: ...


@dataclass(frozen=True)
class IssuerAuthority:
    signer_subject_id: str
    signing_key_reference: str
    authority_snapshot_digest: str
    signer: DeploymentAuthorizationSigner


class InMemoryDeploymentAuthorizationRepository:
    """Process-safe idempotent repository used by host composition and tests."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._artifacts: dict[str, DeploymentAuthorizationArtifact] = {}

    def publish_if_absent(self, artifact: DeploymentAuthorizationArtifact) -> DeploymentAuthorizationArtifact:
        with self._lock:
            existing = self._artifacts.get(artifact.authorization_digest)
            if existing is not None:
                if existing != artifact:
                    raise DeploymentAuthorizationError("deployment_authorization_digest_conflict")
                return existing
            self._artifacts[artifact.authorization_digest] = artifact
            return artifact


class DeploymentAuthorizationIssuer:
    """Issues production artifacts from primitive, preverified digest coordinates."""

    def __init__(
        self,
        *,
        authority: IssuerAuthority,
        repository: DeploymentAuthorizationRepository,
        now_provider: Callable[[], datetime],
    ) -> None:
        if not _DIGEST.fullmatch(authority.authority_snapshot_digest):
            raise DeploymentAuthorizationError("deployment_authorization_authority_snapshot")
        self._authority = authority
        self._repository = repository
        self._now_provider = now_provider

    def issue(self, request: DeploymentAuthorizationIssuanceRequest) -> DeploymentAuthorizationArtifact:
        return self.publish_prepared(self.prepare(request))

    def prepare(self, request: DeploymentAuthorizationIssuanceRequest) -> DeploymentAuthorizationArtifact:
        """Create a signed artifact without making it visible to runtime readers."""
        if type(request) is not DeploymentAuthorizationIssuanceRequest:
            raise DeploymentAuthorizationError("deployment_authorization_request_type")
        issued_at = self._now_provider()
        if issued_at.utcoffset() is None or request.expires_at <= issued_at:
            raise DeploymentAuthorizationError("deployment_authorization_expired_request")
        unsigned = {
            "schema_version": 1,
            "purpose": request.purpose,
            "target_kind": request.target_kind,
            "target_artifact_digest": request.target_artifact_digest,
            "deployment_manifest_digest": request.deployment_manifest_digest,
            "capability_fingerprint": request.capability_fingerprint,
            "verified_capability_baseline_approval_release_digest": request.verified_capability_baseline_approval_release_digest,
            "signer_subject_id": self._authority.signer_subject_id,
            "signing_key_reference": self._authority.signing_key_reference,
            "authority_snapshot_digest": self._authority.authority_snapshot_digest,
            "active_epoch": request.requested_active_epoch,
            "issued_at": _time_json(issued_at),
            "expires_at": _time_json(request.expires_at),
        }
        authorization_digest = _digest(b"memorii.deployment-authorization.artifact.v1", unsigned)
        signature = self._authority.signer.sign(
            b"memorii.deployment-authorization.signature.v1\0" + authorization_digest.encode("ascii")
        )
        if not isinstance(signature, str) or not signature:
            raise DeploymentAuthorizationError("deployment_authorization_signature")
        return DeploymentAuthorizationArtifact(
            **unsigned, authorization_digest=authorization_digest, signature=signature
        )

    def publish_prepared(self, artifact: DeploymentAuthorizationArtifact) -> DeploymentAuthorizationArtifact:
        if type(artifact) is not DeploymentAuthorizationArtifact:
            raise DeploymentAuthorizationError("deployment_authorization_artifact_type")
        return self._repository.publish_if_absent(artifact)

    def issue_verified(
        self,
        *,
        target_artifact_digest: str,
        deployment_manifest_digest: str,
        capability_fingerprint: str,
        verified_capability_baseline_approval_release_digest: str,
        requested_active_epoch: int,
        expires_at: datetime,
    ) -> DeploymentAuthorizationArtifact:
        """Bridge entry for acceptance callers carrying only verified digests."""
        return self.issue(
            DeploymentAuthorizationIssuanceRequest.create(
                purpose="semantic_ingestion_capability_baseline",
                target_kind="capability_baseline",
                target_artifact_digest=target_artifact_digest,
                deployment_manifest_digest=deployment_manifest_digest,
                capability_fingerprint=capability_fingerprint,
                verified_capability_baseline_approval_release_digest=verified_capability_baseline_approval_release_digest,
                requested_active_epoch=requested_active_epoch,
                expires_at=expires_at,
            )
        )

    def prepare_verified(
        self,
        *,
        target_artifact_digest: str,
        deployment_manifest_digest: str,
        capability_fingerprint: str,
        verified_capability_baseline_approval_release_digest: str,
        requested_active_epoch: int,
        expires_at: datetime,
    ) -> DeploymentAuthorizationArtifact:
        return self.prepare(
            DeploymentAuthorizationIssuanceRequest.create(
                purpose="semantic_ingestion_capability_baseline",
                target_kind="capability_baseline",
                target_artifact_digest=target_artifact_digest,
                deployment_manifest_digest=deployment_manifest_digest,
                capability_fingerprint=capability_fingerprint,
                verified_capability_baseline_approval_release_digest=verified_capability_baseline_approval_release_digest,
                requested_active_epoch=requested_active_epoch,
                expires_at=expires_at,
            )
        )


class DeploymentAuthorizationArtifactVerifier:
    """Production-side decoder/verifier for serialized issuer output only."""

    def __init__(self, verifier: DeploymentAuthorizationSignatureVerifier) -> None:
        self._verifier = verifier

    def verify(self, raw: bytes, *, server_time: datetime) -> DeploymentAuthorizationArtifact:
        if not isinstance(raw, bytes) or server_time.utcoffset() is None:
            raise DeploymentAuthorizationError("deployment_authorization_transport")
        try:
            artifact = DeploymentAuthorizationArtifact.model_validate_json(raw)
        except ValueError as exc:
            raise DeploymentAuthorizationError("deployment_authorization_decode") from exc
        if _canonical_bytes(artifact.model_dump(mode="json")) != raw:
            raise DeploymentAuthorizationError("deployment_authorization_canonical_bytes")
        if artifact.expires_at <= server_time:
            raise DeploymentAuthorizationError("deployment_authorization_expired")
        preimage = b"memorii.deployment-authorization.signature.v1\0" + artifact.authorization_digest.encode("ascii")
        if not self._verifier.verify(
            signing_key_reference=artifact.signing_key_reference,
            preimage=preimage,
            signature=artifact.signature,
        ):
            raise DeploymentAuthorizationError("deployment_authorization_signature")
        return artifact


class _FileDeploymentAuthorizationRepository:
    """Durable production-side publication owner for the serialized bridge."""

    def __init__(self, root: Path) -> None:
        _secure_path(root, "deployment_authorization_repository_path")
        self._root = root

    def visible_exact(self, digest: str, raw: bytes) -> bool:
        if not _DIGEST.fullmatch(digest) or not isinstance(raw, bytes):
            raise DeploymentAuthorizationError("deployment_authorization_visibility")
        path = self._root / digest
        _secure_path(path, "deployment_authorization_repository_path")
        try:
            return path.read_bytes() == raw
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise DeploymentAuthorizationError("deployment_authorization_visibility") from exc

    def publish_if_absent(self, artifact: DeploymentAuthorizationArtifact) -> DeploymentAuthorizationArtifact:
        raw = _canonical_bytes(artifact.model_dump(mode="json"))
        _secure_path(self._root, "deployment_authorization_repository_path")
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / artifact.authorization_digest
        _secure_path(path, "deployment_authorization_repository_path")
        temporary = self._root / f".{artifact.authorization_digest}.{os.getpid()}.{os.urandom(8).hex()}.tmp"
        try:
            with temporary.open("xb") as out:
                out.write(raw)
                out.flush()
                os.fsync(out.fileno())
            try:
                os.link(temporary, path)
                _fsync_directory(self._root)
            except FileExistsError as exc:
                if not self.visible_exact(artifact.authorization_digest, raw):
                    raise DeploymentAuthorizationError("deployment_authorization_digest_conflict") from exc
                # The prior link might have reached storage before an interrupted
                # directory fsync.  Re-fsync on the idempotent recovery path.
                _fsync_directory(self._root)
        except FileExistsError as exc:
            raise DeploymentAuthorizationError("deployment_authorization_digest_conflict") from exc
        finally:
            temporary.unlink(missing_ok=True)
        return artifact


@dataclass(frozen=True)
class _SerializedProductionRevocationEvidence:
    """Opaque bytes crossing to acceptance's independently owned decoder."""

    receipt: bytes
    checkpoint: bytes


class _FileProductionRevocationReader:
    """Least-privilege read-only owner of production revocation evidence."""

    def __init__(self, root: Path) -> None:
        _secure_path(root, "production_revocation_reader_path")
        self._root = root

    def _object(self, digest: str) -> bytes:
        if not _DIGEST.fullmatch(digest):
            raise DeploymentAuthorizationError("production_revocation_coordinate")
        path = self._root / "objects" / digest
        _secure_path(path, "production_revocation_reader_path")
        try:
            value = path.read_bytes()
        except OSError as exc:
            raise DeploymentAuthorizationError("production_revocation_missing") from exc
        if not value:
            raise DeploymentAuthorizationError("production_revocation_missing")
        return value

    def load_checkpoint(self, checkpoint_digest: str) -> bytes:
        return self._object(checkpoint_digest)

    def read_for_prior_release(
        self, prior_approval_release_digest: str
    ) -> _SerializedProductionRevocationEvidence:
        if not _DIGEST.fullmatch(prior_approval_release_digest):
            raise DeploymentAuthorizationError("production_revocation_coordinate")
        mapping_path = self._root / "current" / f"{prior_approval_release_digest}.json"
        _secure_path(mapping_path, "production_revocation_reader_path")
        try:
            raw = mapping_path.read_bytes()
            value = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DeploymentAuthorizationError("production_revocation_current") from exc
        if (
            type(value) is not dict
            or set(value)
            != {
                "prior_approval_release_digest",
                "receipt_digest",
                "checkpoint_digest",
            }
            or _canonical_bytes(value) != raw
            or value["prior_approval_release_digest"] != prior_approval_release_digest
            or not isinstance(value["receipt_digest"], str)
            or not isinstance(value["checkpoint_digest"], str)
        ):
            raise DeploymentAuthorizationError("production_revocation_current")
        return _SerializedProductionRevocationEvidence(
            receipt=self._object(value["receipt_digest"]),
            checkpoint=self._object(value["checkpoint_digest"]),
        )


class _SerializedDeploymentPublisher:
    _acceptance_serialized_bridge = True

    def __init__(self, issuer: DeploymentAuthorizationIssuer) -> None:
        self._issuer = issuer

    def prepare_verified(self, request: bytes) -> bytes:
        try:
            parsed = DeploymentAuthorizationIssuanceRequest.model_validate_json(request)
        except ValueError as exc:
            raise DeploymentAuthorizationError("deployment_authorization_decode") from exc
        if _canonical_bytes(parsed.model_dump(mode="json")) != request:
            raise DeploymentAuthorizationError("deployment_authorization_canonical_bytes")
        return _canonical_bytes(self._issuer.prepare(parsed).model_dump(mode="json"))

    def publish_prepared(self, artifact: bytes) -> bytes:
        try:
            parsed = DeploymentAuthorizationArtifact.model_validate_json(artifact)
        except ValueError as exc:
            raise DeploymentAuthorizationError("deployment_authorization_decode") from exc
        if _canonical_bytes(parsed.model_dump(mode="json")) != artifact:
            raise DeploymentAuthorizationError("deployment_authorization_canonical_bytes")
        return _canonical_bytes(self._issuer.publish_prepared(parsed).model_dump(mode="json"))

    def visible_exact(self, artifact: bytes) -> bool:
        try:
            parsed = DeploymentAuthorizationArtifact.model_validate_json(artifact)
        except ValueError as exc:
            raise DeploymentAuthorizationError("deployment_authorization_decode") from exc
        if _canonical_bytes(parsed.model_dump(mode="json")) != artifact:
            raise DeploymentAuthorizationError("deployment_authorization_canonical_bytes")
        repository = self._issuer._repository
        if not isinstance(repository, _FileDeploymentAuthorizationRepository):
            raise DeploymentAuthorizationError("deployment_authorization_visibility")
        return repository.visible_exact(parsed.authorization_digest, artifact)


class InstalledDeploymentAuthorizationPublisher:
    """Fixed production provider selected by package metadata, never candidates."""

    def from_fixed_configuration(self, configuration: object) -> _SerializedDeploymentPublisher:
        if type(configuration) is not dict or set(configuration) != {
            "subject_id", "key_reference", "authority_snapshot_digest", "private_key", "publisher_root"
        }:
            raise DeploymentAuthorizationError("deployment_authorization_configuration")
        try:
            private_key = bytes.fromhex(str(configuration["private_key"]))
            root = Path(str(configuration["publisher_root"]))
            if not root.is_absolute() or root.is_symlink() or len(private_key) != 32:
                raise ValueError
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            signer = _RawEd25519Signer(Ed25519PrivateKey.from_private_bytes(private_key))
            authority = IssuerAuthority(str(configuration["subject_id"]), str(configuration["key_reference"]), str(configuration["authority_snapshot_digest"]), signer)
        except (TypeError, ValueError) as exc:
            raise DeploymentAuthorizationError("deployment_authorization_configuration") from exc
        return _SerializedDeploymentPublisher(DeploymentAuthorizationIssuer(authority=authority, repository=_FileDeploymentAuthorizationRepository(root), now_provider=lambda: datetime.now().astimezone()))


class InstalledProductionRevocationReader:
    """Fixed entry-point factory for the independent acceptance reader port."""

    def from_fixed_configuration(
        self, configuration: object
    ) -> _FileProductionRevocationReader:
        if type(configuration) is not dict or set(configuration) != {"reader_root"}:
            raise DeploymentAuthorizationError("production_revocation_configuration")
        root = Path(str(configuration["reader_root"]))
        if not root.is_absolute() or root.is_symlink():
            raise DeploymentAuthorizationError("production_revocation_configuration")
        return _FileProductionRevocationReader(root)


class _RawEd25519Signer:
    def __init__(self, key: object) -> None:
        self._key = key

    def sign(self, preimage: bytes) -> str:
        return self._key.sign(preimage).hex()  # type: ignore[union-attr]


__all__ = [
    "DeploymentAuthorizationArtifact",
    "DeploymentAuthorizationError",
    "DeploymentAuthorizationIssuanceRequest",
    "DeploymentAuthorizationIssuer",
    "DeploymentAuthorizationRepository",
    "DeploymentAuthorizationSigner",
    "DeploymentAuthorizationSignatureVerifier",
    "DeploymentAuthorizationArtifactVerifier",
    "InMemoryDeploymentAuthorizationRepository",
    "IssuerAuthority",
    "InstalledDeploymentAuthorizationPublisher",
    "InstalledProductionRevocationReader",
]
