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
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Literal, Protocol

try:  # The installed authority runtime is POSIX file-store based.
    import fcntl
except ImportError:  # pragma: no cover - exercised only on unsupported hosts
    fcntl = None  # type: ignore[assignment]

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
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


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


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


class Ed25519DeploymentAuthorizationKeyring:
    """Fixed public-key map for installed authorization verification.

    This boundary deliberately owns verification keys only.  Deployment
    signing remains an offline/release concern and cannot be selected by an
    ingestion candidate or evidence payload.
    """

    def __init__(self, public_keys: dict[str, bytes]) -> None:
        if not public_keys or any(
            not isinstance(reference, str)
            or not reference
            or not isinstance(key, bytes)
            or len(key) != 32
            for reference, key in public_keys.items()
        ):
            raise DeploymentAuthorizationError("deployment_authorization_keyring")
        self._keys = {
            reference: Ed25519PublicKey.from_public_bytes(key)
            for reference, key in public_keys.items()
        }

    def verify(self, *, signing_key_reference: str, preimage: bytes, signature: str) -> bool:
        key = self._keys.get(signing_key_reference)
        if key is None or not isinstance(preimage, bytes):
            return False
        try:
            key.verify(bytes.fromhex(signature), preimage)
        except (InvalidSignature, TypeError, ValueError):
            return False
        return True


class DeploymentAuthorizationCurrentTrustCheck(Protocol):
    """Host-owned signer lifecycle, revocation, and compromise decision.

    The host must linearize this read with its revocation publication. Callers
    fence writes on a false result; they cannot make a later external
    revocation atomic without that host-provided linearization.
    """

    def is_current(
        self, *, artifact: DeploymentAuthorizationArtifact, server_time: datetime
    ) -> bool: ...

    def current_use(
        self, *, artifact: DeploymentAuthorizationArtifact, server_time: datetime
    ) -> AbstractContextManager[bool]: ...


class DeploymentAuthorizationCurrentTrustVerifier(Protocol):
    """Live deployment-authority port for every use, not only construction."""

    def verify_current(
        self,
        *,
        raw: bytes,
        server_time: datetime,
        purpose: _Purpose,
        target_kind: _TargetKind,
        target_artifact_digest: str,
        capability_fingerprint: str,
        authority_snapshot_digest: str,
        active_epoch: int,
    ) -> DeploymentAuthorizationArtifact | None: ...

    def verify_current_use(
        self,
        *,
        raw: bytes,
        server_time: datetime,
        purpose: _Purpose,
        target_kind: _TargetKind,
        target_artifact_digest: str,
        capability_fingerprint: str,
        authority_snapshot_digest: str,
        active_epoch: int,
    ) -> AbstractContextManager[DeploymentAuthorizationArtifact | None]: ...


class ArtifactDeploymentAuthorizationCurrentTrustVerifier:
    """Compose canonical artifact verification with a live host trust decision."""

    def __init__(
        self,
        *,
        artifact_verifier: DeploymentAuthorizationArtifactVerifier,
        current_trust_check: DeploymentAuthorizationCurrentTrustCheck,
    ) -> None:
        self._artifact_verifier = artifact_verifier
        self._current_trust_check = current_trust_check

    def verify_current(
        self,
        *, raw: bytes, server_time: datetime, purpose: _Purpose,
        target_kind: _TargetKind, target_artifact_digest: str,
        capability_fingerprint: str, authority_snapshot_digest: str,
        active_epoch: int,
    ) -> DeploymentAuthorizationArtifact | None:
        try:
            artifact = self._artifact_verifier.verify(raw, server_time=server_time)
        except DeploymentAuthorizationError:
            return None
        if (
            artifact.purpose != purpose
            or artifact.target_kind != target_kind
            or artifact.target_artifact_digest != target_artifact_digest
            or artifact.capability_fingerprint != capability_fingerprint
            or artifact.authority_snapshot_digest != authority_snapshot_digest
            or artifact.active_epoch != active_epoch
            or not self._current_trust_check.is_current(
                artifact=artifact, server_time=server_time
            )
        ):
            return None
        return artifact

    @contextmanager
    def verify_current_use(
        self,
        *, raw: bytes, server_time: datetime, purpose: _Purpose,
        target_kind: _TargetKind, target_artifact_digest: str,
        capability_fingerprint: str, authority_snapshot_digest: str,
        active_epoch: int,
    ) -> Iterator[DeploymentAuthorizationArtifact | None]:
        """Hold the host revocation linearizer through a durable write."""
        try:
            artifact = self._artifact_verifier.verify(raw, server_time=server_time)
        except DeploymentAuthorizationError:
            yield None
            return
        if (
            artifact.purpose != purpose
            or artifact.target_kind != target_kind
            or artifact.target_artifact_digest != target_artifact_digest
            or artifact.capability_fingerprint != capability_fingerprint
            or artifact.authority_snapshot_digest != authority_snapshot_digest
            or artifact.active_epoch != active_epoch
        ):
            yield None
            return
        with self._current_trust_check.current_use(
            artifact=artifact, server_time=server_time
        ) as current:
            yield artifact if current else None


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

    def __init__(self, root: Path, *, now_provider: Callable[[], datetime] | None = None) -> None:
        _secure_path(root, "production_revocation_reader_path")
        self._root = root
        self._now_provider = now_provider
        # This coordinate is shared with the only installed mapping publisher.
        # A shared lock is held through the group CAS; publication takes the
        # exclusive lock before its atomic replacement.
        self._lock_path = root / ".production-revocation.lock"

    @contextmanager
    def _locked(self, mode: int) -> Iterator[None]:
        if fcntl is None:
            raise DeploymentAuthorizationError("production_revocation_lock_unsupported")
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(self._lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        except OSError as exc:
            raise DeploymentAuthorizationError("production_revocation_lock") from exc
        try:
            fcntl.flock(descriptor, mode)
            yield
        except OSError as exc:
            raise DeploymentAuthorizationError("production_revocation_lock") from exc
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

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

    @staticmethod
    def _bounded_canonical_object(raw: bytes, *, kind: str) -> dict[str, object]:
        """Validate only the opaque coordinate shape owned by this runtime.

        Acceptance owns signature and schema semantics.  The production
        publisher deliberately checks just enough stable identity to prevent a
        substituted arbitrary JSON blob from becoming a revocation object.
        """
        if not isinstance(raw, bytes) or not raw or len(raw) > 131072:
            raise DeploymentAuthorizationError("production_revocation_object")
        try:
            value = json.loads(raw, object_pairs_hook=lambda pairs: _unique_json_object(pairs))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise DeploymentAuthorizationError("production_revocation_object") from exc
        if type(value) is not dict or _canonical_bytes(value) != raw:
            raise DeploymentAuthorizationError("production_revocation_object")
        if kind == "receipt":
            required = {"schema_version", "purpose", "prior_approval_release_digest", "receipt_digest", "signing_key_coordinate", "signature"}
            digest_field = "receipt_digest"
            purpose = "production_revocation_receipt"
        else:
            required = {"schema_version", "purpose", "checkpoint_digest", "revocation_receipt_digests", "signing_key_coordinate", "signature"}
            digest_field = "checkpoint_digest"
            purpose = "production_epoch_checkpoint"
        if not required.issubset(value) or value.get("purpose") != purpose:
            raise DeploymentAuthorizationError("production_revocation_object")
        if not isinstance(value.get("schema_version"), int) or value["schema_version"] < 1:
            raise DeploymentAuthorizationError("production_revocation_object")
        if not isinstance(value.get(digest_field), str) or not _DIGEST.fullmatch(value[digest_field]):
            raise DeploymentAuthorizationError("production_revocation_object")
        if not isinstance(value.get("signing_key_coordinate"), str) or not value["signing_key_coordinate"]:
            raise DeploymentAuthorizationError("production_revocation_object")
        if not isinstance(value.get("signature"), str) or not value["signature"]:
            raise DeploymentAuthorizationError("production_revocation_object")
        if kind == "receipt" and not isinstance(value.get("prior_approval_release_digest"), str):
            raise DeploymentAuthorizationError("production_revocation_object")
        if kind == "receipt" and not _DIGEST.fullmatch(value["prior_approval_release_digest"]):
            raise DeploymentAuthorizationError("production_revocation_object")
        if kind == "checkpoint":
            receipts = value.get("revocation_receipt_digests")
            if not isinstance(receipts, list) or not receipts or any(
                not isinstance(item, str) or not _DIGEST.fullmatch(item) for item in receipts
            ):
                raise DeploymentAuthorizationError("production_revocation_object")
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

    def is_current(
        self, *, artifact: DeploymentAuthorizationArtifact, server_time: datetime
    ) -> bool:
        del server_time
        release = artifact.verified_capability_baseline_approval_release_digest
        if release is None:
            return False
        with self._locked(fcntl.LOCK_SH if fcntl is not None else 0):
            return self._is_current_locked(release)

    def _is_current_locked(self, release: str) -> bool:
        mapping_path = self._root / "current" / f"{release}.json"
        _secure_path(mapping_path, "production_revocation_reader_path")
        # Absence is the normal state for an active release. A present mapping
        # is a revocation coordinate; malformed evidence is never active.
        if not mapping_path.exists():
            return True
        try:
            self.read_for_prior_release(release)
        except DeploymentAuthorizationError:
            return False
        return False

    @contextmanager
    def current_use(
        self, *, artifact: DeploymentAuthorizationArtifact, server_time: datetime
    ) -> Iterator[bool]:
        release = artifact.verified_capability_baseline_approval_release_digest
        if release is None:
            yield False
            return
        with self._locked(fcntl.LOCK_SH if fcntl is not None else 0):
            # Production composition supplies a protected host clock.  The
            # sample happens only after acquiring the lease, so an artifact
            # expiring while publication held the exclusive lock cannot CAS.
            now = self._now_provider() if self._now_provider is not None else server_time
            yield artifact.expires_at > now and self._is_current_locked(release)

    def _publish_object_locked(self, *, digest: str, raw: bytes) -> None:
        directory = self._root / "objects"
        path = directory / digest
        _secure_path(path, "production_revocation_reader_path")
        directory.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != raw:
                raise DeploymentAuthorizationError("production_revocation_conflict")
            return
        temporary = directory / f".{digest}.{os.getpid()}.{os.urandom(8).hex()}.tmp"
        try:
            with temporary.open("xb") as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != raw:
                    raise DeploymentAuthorizationError("production_revocation_conflict") from None
            _fsync_directory(directory)
        finally:
            temporary.unlink(missing_ok=True)

    def publish_revocation_evidence(
        self, *, prior_approval_release_digest: str, receipt: bytes, checkpoint: bytes
    ) -> None:
        """Durably publish opaque signed evidence before exposing its mapping."""
        receipt_value = self._bounded_canonical_object(receipt, kind="receipt")
        checkpoint_value = self._bounded_canonical_object(checkpoint, kind="checkpoint")
        receipt_digest = receipt_value["receipt_digest"]
        checkpoint_digest = checkpoint_value["checkpoint_digest"]
        if (
            not isinstance(receipt_digest, str) or not isinstance(checkpoint_digest, str)
            or receipt_value["prior_approval_release_digest"] != prior_approval_release_digest
            or not isinstance(checkpoint_value["revocation_receipt_digests"], list)
            or receipt_digest not in checkpoint_value["revocation_receipt_digests"]
        ):
            raise DeploymentAuthorizationError("production_revocation_coordinate")
        if not _DIGEST.fullmatch(prior_approval_release_digest):
            raise DeploymentAuthorizationError("production_revocation_coordinate")
        with self._locked(fcntl.LOCK_EX if fcntl is not None else 0):
            self._publish_object_locked(digest=receipt_digest, raw=receipt)
            self._publish_object_locked(digest=checkpoint_digest, raw=checkpoint)
            self._publish_revocation_mapping_locked(
                prior_approval_release_digest=prior_approval_release_digest,
                receipt_digest=receipt_digest, checkpoint_digest=checkpoint_digest,
            )

    def publish_revocation_mapping(
        self, *, prior_approval_release_digest: str, receipt_digest: str,
        checkpoint_digest: str,
    ) -> None:
        """Publish one immutable revocation coordinate under the shared lock."""
        if not all(_DIGEST.fullmatch(value) for value in (
            prior_approval_release_digest, receipt_digest, checkpoint_digest,
        )):
            raise DeploymentAuthorizationError("production_revocation_coordinate")
        with self._locked(fcntl.LOCK_EX if fcntl is not None else 0):
            self._publish_revocation_mapping_locked(
                prior_approval_release_digest=prior_approval_release_digest,
                receipt_digest=receipt_digest, checkpoint_digest=checkpoint_digest,
            )

    def _publish_revocation_mapping_locked(
        self, *, prior_approval_release_digest: str, receipt_digest: str, checkpoint_digest: str,
    ) -> None:
        payload = _canonical_bytes({
            "prior_approval_release_digest": prior_approval_release_digest,
            "receipt_digest": receipt_digest,
            "checkpoint_digest": checkpoint_digest,
        })
        directory = self._root / "current"
        path = directory / f"{prior_approval_release_digest}.json"
        _secure_path(path, "production_revocation_reader_path")
        try:
            directory.mkdir(parents=True, exist_ok=True)
            if path.exists():
                if path.read_bytes() != payload:
                    raise DeploymentAuthorizationError(
                        "production_revocation_conflict"
                    ) from None
                return
            temporary = directory / f".{prior_approval_release_digest}.tmp"
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(descriptor, payload)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            try:
                # Hard-link creation is publish-if-absent at the filesystem
                # boundary too; it never replaces a competing coordinate.
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != payload:
                    raise DeploymentAuthorizationError(
                        "production_revocation_conflict"
                    ) from None
            finally:
                temporary.unlink(missing_ok=True)
            _fsync_directory(directory)
        except DeploymentAuthorizationError:
            raise
        except OSError as exc:
            raise DeploymentAuthorizationError("production_revocation_publish") from exc


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
        self, configuration: object, *, now_provider: Callable[[], datetime] | None = None
    ) -> _FileProductionRevocationReader:
        if type(configuration) is not dict or set(configuration) != {"reader_root"}:
            raise DeploymentAuthorizationError("production_revocation_configuration")
        root = Path(str(configuration["reader_root"]))
        if not root.is_absolute() or root.is_symlink():
            raise DeploymentAuthorizationError("production_revocation_configuration")
        return _FileProductionRevocationReader(root, now_provider=now_provider)


class _RawEd25519Signer:
    def __init__(self, key: object) -> None:
        self._key = key

    def sign(self, preimage: bytes) -> str:
        return self._key.sign(preimage).hex()  # type: ignore[union-attr]


__all__ = [
    "ArtifactDeploymentAuthorizationCurrentTrustVerifier",
    "DeploymentAuthorizationArtifact",
    "DeploymentAuthorizationArtifactVerifier",
    "DeploymentAuthorizationCurrentTrustCheck",
    "DeploymentAuthorizationCurrentTrustVerifier",
    "DeploymentAuthorizationError",
    "Ed25519DeploymentAuthorizationKeyring",
    "DeploymentAuthorizationIssuanceRequest",
    "DeploymentAuthorizationIssuer",
    "DeploymentAuthorizationRepository",
    "DeploymentAuthorizationSigner",
    "DeploymentAuthorizationSignatureVerifier",
    "InMemoryDeploymentAuthorizationRepository",
    "IssuerAuthority",
    "InstalledDeploymentAuthorizationPublisher",
    "InstalledProductionRevocationReader",
]
