"""Installed, fixed-location composition for acceptance evaluation.

This module is intentionally the only production composition root for the
acceptance package.  Candidate input never contributes a key, path, limit, or
clock.  The configuration is an administrator-installed file at a platform
data location; there are no environment or command-line fallbacks.
"""

from __future__ import annotations

import json
import base64
import os
import stat
import sysconfig
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from acceptance.authority_repository import (
    AcceptanceAuthorityRepository,
    AcceptanceEvaluationSnapshot,
    AcceptanceFenceRegistration,
    AtomicEvaluationReceiptStore,
    AuthorityRepositoryUnavailable,
    SqliteAcceptanceAuthorityFence,
)
from acceptance.capability_baseline_approval import (
    AcceptanceApprovalIssuanceSnapshotV1,
    AcceptanceSigningKey,
    AcceptanceVerifierLimits,
    CapabilityBaselineApprovalVerifier,
    AcceptanceStatus,
    CurrentAcceptanceCheckpoint,
    KeyLifecycleEvent,
)
from acceptance.evaluator import AcceptanceEvaluator, SerializedDeploymentAuthorizationBridge
from acceptance.deployment_bridge import configured_publisher
from acceptance.production_revocation import IndependentProductionRevocationEvidenceVerifier
from acceptance.production_revocation_bridge import configured_revocation_reader
from acceptance.numeric_context_authority import FixedNumericManifestAuthority
from acceptance.statistical_certification import (
    CanonicalDecimalQuantity,
    EncodingSpec,
    Gate,
    GateLocator,
    HeldBinding,
    Membership,
    NumericAuthority,
    PreverifiedNumericCertificationContext,
    PreverifiedNumericGate,
    TransportLimits,
)

_FORMAT = "memorii.acceptance.runtime.v2"
_CONFIG = Path(sysconfig.get_path("data")) / "etc" / "memorii" / "acceptance" / "runtime-v2.json"
_HEX = frozenset("0123456789abcdef")


class AcceptanceRuntimeConfigurationError(ValueError):
    """The installed authority configuration cannot safely compose a runtime."""


def runtime_config_path() -> Path:
    """The one fixed runtime coordinate, derived from Python platform data."""
    return _CONFIG


def _absolute_path(value: object, name: str) -> Path:
    if not isinstance(value, str):
        raise AcceptanceRuntimeConfigurationError(f"acceptance_runtime_{name}")
    path = Path(value)
    if not path.is_absolute():
        raise AcceptanceRuntimeConfigurationError(f"acceptance_runtime_{name}")
    return path


def _secure_file(path: Path, name: str) -> bytes:
    try:
        _secure_path(path, name)
        if not path.is_file():
            raise AcceptanceRuntimeConfigurationError(f"acceptance_runtime_{name}")
        return path.read_bytes()
    except OSError as exc:
        raise AcceptanceRuntimeConfigurationError(f"acceptance_runtime_{name}") from exc


def _secure_path(path: Path, name: str) -> None:
    """Admit an absolute fixed resource only through secure existing ancestry."""
    if not path.is_absolute():
        raise AcceptanceRuntimeConfigurationError(f"acceptance_runtime_{name}")
    current = path
    while True:
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            if current.parent == current:
                raise AcceptanceRuntimeConfigurationError(f"acceptance_runtime_{name}")
            current = current.parent
            continue
        except OSError as exc:
            raise AcceptanceRuntimeConfigurationError(f"acceptance_runtime_{name}") from exc
        if (
            stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid not in {os.geteuid(), 0}
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise AcceptanceRuntimeConfigurationError(f"acceptance_runtime_{name}")
        if current.parent == current:
            return
        current = current.parent


def _distinct_domains(paths: tuple[Path, ...]) -> None:
    for index, left in enumerate(paths):
        for right in paths[index + 1:]:
            if left == right or left in right.parents or right in left.parents:
                raise AcceptanceRuntimeConfigurationError("acceptance_runtime_path_alias")


def _closed_config() -> dict[str, Any]:
    raw = _secure_file(runtime_config_path(), "config")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceRuntimeConfigurationError("acceptance_runtime_config") from exc
    required = {
        "format", "authority_repository_root", "fence_database_path", "receipt_root",
        "fence_registration", "trust_keys", "acceptance_keys", "numeric_authority",
        "numeric_limits", "acceptance_limits", "deployment_issuer", "evaluator_subject_id",
        "evaluator_signing_key_coordinate", "evaluator_private_key",
        "production_revocation_reader", "production_trust_keys",
    }
    if type(value) is not dict or set(value) != required or value["format"] != _FORMAT:
        raise AcceptanceRuntimeConfigurationError("acceptance_runtime_config")
    authority = _absolute_path(value["authority_repository_root"], "authority_repository_root")
    fence = _absolute_path(value["fence_database_path"], "fence_database_path")
    receipt = _absolute_path(value["receipt_root"], "receipt_root")
    deployment = value["deployment_issuer"]
    if type(deployment) is not dict:
        raise AcceptanceRuntimeConfigurationError("acceptance_runtime_deployment_issuer")
    publisher = _absolute_path(deployment.get("publisher_root"), "publisher_root")
    revocation = value["production_revocation_reader"]
    if type(revocation) is not dict:
        raise AcceptanceRuntimeConfigurationError("acceptance_runtime_production_revocation_reader")
    reader_root = _absolute_path(revocation.get("reader_root"), "production_revocation_reader_root")
    for path, name in ((authority, "authority_repository_root"), (fence, "fence_database_path"), (receipt, "receipt_root"), (publisher, "publisher_root"), (reader_root, "production_revocation_reader_root")):
        _secure_path(path, name)
    _distinct_domains((authority, receipt, publisher, reader_root, fence.parent))
    return value


def _hex(value: object, name: str, length: int | None = None) -> bytes:
    if not isinstance(value, str) or len(value) % 2 or any(c not in _HEX for c in value):
        raise AcceptanceRuntimeConfigurationError(f"acceptance_runtime_{name}")
    answer = bytes.fromhex(value)
    if length is not None and len(answer) != length:
        raise AcceptanceRuntimeConfigurationError(f"acceptance_runtime_{name}")
    return answer


def _time(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise AcceptanceRuntimeConfigurationError(f"acceptance_runtime_{name}")
    try:
        answer = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AcceptanceRuntimeConfigurationError(f"acceptance_runtime_{name}") from exc
    if answer.utcoffset() is None:
        raise AcceptanceRuntimeConfigurationError(f"acceptance_runtime_{name}")
    return answer.astimezone(UTC)


class _DurableApprovalView:
    """Compatibility view over the fenced commit selected while the lease is held."""

    def __init__(self, repository: AcceptanceAuthorityRepository) -> None:
        self._repository = repository
        self._selected: dict[str, Any] | None = None

    def select_snapshot(self, snapshot: AcceptanceEvaluationSnapshot) -> None:
        self._selected = dict(self._repository.selected_evaluation_artifacts(snapshot))

    def _selected_or_raise(self) -> dict[str, Any]:
        if self._selected is None:
            raise AuthorityRepositoryUnavailable("acceptance_snapshot_required")
        return self._selected

    def _commit(self) -> dict[str, Any]:
        return dict(self._selected_or_raise()["commit"])

    def load_current(self) -> AcceptanceStatus:
        commit = self._commit()
        active = commit["active_release_digest"]
        if active is None:
            raise AuthorityRepositoryUnavailable("acceptance_active_release_absent")
        releases = tuple(value["release_digest"] for value in self._selected_or_raise()["releases"])
        return AcceptanceStatus(
            commit["authority_snapshot_digest"], active, commit["active_release_epoch"],
            commit["active_release_sequence"], releases,
        )

    def load_issuance_snapshot(self, snapshot_digest: str, release_digest: str) -> AcceptanceApprovalIssuanceSnapshotV1 | None:
        selected = self._selected_or_raise()
        issuance = selected["issuance"]
        commit = self._commit()
        if snapshot_digest != issuance["trust_snapshot_digest"] or release_digest != commit["active_release_digest"]:
            return None
        events = self.load_current_key_history()
        return AcceptanceApprovalIssuanceSnapshotV1(
            issuance["snapshot_digest"], issuance["trust_snapshot_digest"], events,
            issuance["key_history_head_digest"], issuance["key_history_head_sequence"],
            issuance["signing_key_coordinate"],
        )

    def load_current_key_history(self) -> tuple[KeyLifecycleEvent, ...]:
        return tuple(
            KeyLifecycleEvent(value["key_reference"], value["state"], _time(value["effective_at"], "key_event"), value["global_sequence"], value["predecessor_event_digest"], value["event_digest"])
            for value in self._selected_or_raise()["keys"]
        )

    def load_current_trust_snapshot(self) -> dict[str, Any]:
        return dict(self._selected_or_raise()["trust"])

    def load_current_checkpoint(self) -> CurrentAcceptanceCheckpoint:
        value = self._selected_or_raise()["checkpoint"]
        return CurrentAcceptanceCheckpoint(
            value["authority_snapshot_digest"], value["release_history_head_digest"], value["release_history_head_sequence"],
            value["key_history_head_digest"], value["key_history_head_sequence"], value["active_release_digest"],
            value["active_epoch"], value["active_sequence"], _time(value["observed_at"], "checkpoint"),
        )


def _numeric_binding(value: object) -> HeldBinding:
    """Decode the fixed numeric authority tree from closed administrator config."""
    if type(value) is not dict or set(value) != {"policy_sha256", "evidence_sha256", "authority", "specs", "family_alpha", "family_alpha_spec_id", "gates", "clusters"}:
        raise AcceptanceRuntimeConfigurationError("acceptance_runtime_numeric_binding")
    def quantity(raw: object) -> CanonicalDecimalQuantity:
        if type(raw) is not dict or set(raw) != {"encoding_spec_id", "fixed_scale_value"}:
            raise AcceptanceRuntimeConfigurationError("acceptance_runtime_numeric_binding")
        return CanonicalDecimalQuantity(**raw)
    def locator(raw: object) -> GateLocator:
        if type(raw) is not dict or set(raw) != {"capability_fingerprint", "cell_id", "metric_id"}:
            raise AcceptanceRuntimeConfigurationError("acceptance_runtime_numeric_binding")
        return GateLocator(**raw)
    try:
        authority = NumericAuthority(**value["authority"])
        specs = tuple(EncodingSpec(**item) for item in value["specs"])
        gates = tuple(PreverifiedNumericGate(
            Gate(locator=locator(item["locator"]), method=item["method"], direction=item["direction"],
                 estimand=item["estimand"], threshold=quantity(item["threshold"]),
                 nominal_alpha=quantity(item["nominal_alpha"]), minimum_clusters=item["minimum_clusters"],
                 threshold_spec_id=item["threshold_spec_id"], nominal_alpha_spec_id=item["nominal_alpha_spec_id"],
                 lower_spec_id=item["lower_spec_id"], upper_spec_id=item["upper_spec_id"],
                 weight_spec_id=item["weight_spec_id"], event_value_spec_id=item["event_value_spec_id"],
                 iid_declared=item["iid_declared"]), item["iid_bernoulli_clusters_proven"]
        ) for item in value["gates"])
        clusters = tuple(Membership(locator=locator(item["locator"]), provenance_ids=tuple(item["provenance_ids"]),
                                    expected_event_ids=tuple(item["expected_event_ids"]), weight=quantity(item["weight"]),
                                    lower=quantity(item["lower"]), upper=quantity(item["upper"]), cluster_id=item["cluster_id"])
                         for item in value["clusters"])
        context = PreverifiedNumericCertificationContext(authority, specs, quantity(value["family_alpha"]),
                                                         value["family_alpha_spec_id"], gates, clusters)
        return HeldBinding(value["policy_sha256"], value["evidence_sha256"], authority, context)
    except (KeyError, TypeError, ValueError) as exc:
        raise AcceptanceRuntimeConfigurationError("acceptance_runtime_numeric_binding") from exc


def _v2_numeric_authority(value: object) -> FixedNumericManifestAuthority:
    """Decode immutable manifests and trust; the candidate supplies its release."""
    required = {
        "coverage", "gates", "sampling_frame", "trust_keys",
        "signing_key_id", "trust_policy_digest",
    }
    if type(value) is not dict or set(value) != required or type(value["trust_keys"]) is not dict:
        raise AcceptanceRuntimeConfigurationError("acceptance_runtime_numeric_authority")
    try:
        raw = {
            name: base64.b64decode(value[name], validate=True)
            for name in ("coverage", "gates", "sampling_frame")
        }
        keys = {name: _hex(key, "numeric_authority_key", 32) for name, key in value["trust_keys"].items()}
        signing_key_id = value["signing_key_id"]
        trust_policy_digest = value["trust_policy_digest"]
        if not isinstance(signing_key_id, str) or signing_key_id not in keys:
            raise ValueError("numeric_authority_signer")
        _hex(trust_policy_digest, "numeric_authority_trust_policy", 32)
        return FixedNumericManifestAuthority(
            coverage_bytes=raw["coverage"], gate_bytes=raw["gates"],
            sampling_frame_bytes=raw["sampling_frame"], signing_keys=keys,
            expected_signing_key_id=signing_key_id,
            expected_trust_policy_digest=trust_policy_digest,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AcceptanceRuntimeConfigurationError("acceptance_runtime_numeric_authority") from exc


class InstalledAcceptanceRuntime:
    """The one registered runtime provider; it accepts no caller authority."""

    def __init__(self) -> None:
        config = _closed_config()
        trust = config["trust_keys"]
        if type(trust) is not dict or not trust or any(not isinstance(k, str) for k in trust):
            raise AcceptanceRuntimeConfigurationError("acceptance_runtime_trust")
        public = {name: Ed25519PublicKey.from_public_bytes(_hex(key, "trust_key", 32)) for name, key in trust.items()}

        def verify_artifact(schema: str, preimage: bytes, coordinate: str, signature: str) -> bool:
            key = public.get(coordinate)
            if key is None:
                return False
            try:
                key.verify(_hex(signature, "artifact_signature", 64), preimage)
            except (InvalidSignature, AcceptanceRuntimeConfigurationError):
                return False
            return True

        production_trust = config["production_trust_keys"]
        if (
            type(production_trust) is not dict
            or not production_trust
            or any(not isinstance(coordinate, str) for coordinate in production_trust)
        ):
            raise AcceptanceRuntimeConfigurationError("acceptance_runtime_production_trust")
        try:
            production_verifier = IndependentProductionRevocationEvidenceVerifier(
                reader=configured_revocation_reader(config["production_revocation_reader"]),
                trust_keys={
                    coordinate: _hex(key, "production_trust_key", 32)
                    for coordinate, key in production_trust.items()
                },
            )
        except (ValueError, TypeError) as exc:
            raise AcceptanceRuntimeConfigurationError(
                "acceptance_runtime_production_revocation_reader"
            ) from exc

        registration_value = config["fence_registration"]
        if type(registration_value) is not dict or set(registration_value) != {
            "namespace", "backend_id", "backend_kind", "failure_domain", "repository_id", "credential_reference", "signer_coordinate", "signature"
        }:
            raise AcceptanceRuntimeConfigurationError("acceptance_runtime_fence_registration")
        registration = AcceptanceFenceRegistration(**registration_value)
        fence = SqliteAcceptanceAuthorityFence(
            _absolute_path(config["fence_database_path"], "fence_database_path"), registration,
            lambda body, coordinate, signature: verify_artifact("fence", body, coordinate, signature),
        )
        repository = AcceptanceAuthorityRepository(
            _absolute_path(config["authority_repository_root"], "authority_repository_root"), fence,
            artifact_signature_verifier=verify_artifact,
            production_revocation_verifier=production_verifier,
        )
        keys_value = config["acceptance_keys"]
        if type(keys_value) is not list or not keys_value:
            raise AcceptanceRuntimeConfigurationError("acceptance_runtime_acceptance_keys")
        keys = tuple(AcceptanceSigningKey(
            item["key_reference"], _hex(item["public_key"], "acceptance_key", 32), _time(item["valid_from"], "acceptance_key"),
            None if item["valid_until"] is None else _time(item["valid_until"], "acceptance_key"), item["status"]
        ) for item in keys_value if type(item) is dict and set(item) == {"key_reference", "public_key", "valid_from", "valid_until", "status"})
        if len(keys) != len(keys_value):
            raise AcceptanceRuntimeConfigurationError("acceptance_runtime_acceptance_keys")
        acceptance_limits = AcceptanceVerifierLimits(**config["acceptance_limits"])
        numeric_limits = TransportLimits(**config["numeric_limits"])
        deployment = config["deployment_issuer"]
        if type(deployment) is not dict:
            raise AcceptanceRuntimeConfigurationError("acceptance_runtime_deployment_issuer")
        try:
            issuer = configured_publisher(deployment)
        except ValueError as exc:
            raise AcceptanceRuntimeConfigurationError("acceptance_runtime_deployment_issuer") from exc
        coordinate = config["evaluator_signing_key_coordinate"]
        if not isinstance(coordinate, str) or not coordinate:
            raise AcceptanceRuntimeConfigurationError("acceptance_runtime_evaluator_signer")
        evaluator_key = Ed25519PrivateKey.from_private_bytes(
            _hex(config["evaluator_private_key"], "evaluator_private_key", 32)
        )
        self._evaluator = AcceptanceEvaluator(
            approval_verifier=CapabilityBaselineApprovalVerifier(keys=keys, authority_repository=_DurableApprovalView(repository), limits=acceptance_limits),
            numeric_binding=None,
            numeric_context_resolver=_v2_numeric_authority(config["numeric_authority"]),
            numeric_limits=numeric_limits,
            receipt_store=AtomicEvaluationReceiptStore(_absolute_path(config["receipt_root"], "receipt_root")),
            deployment_issuer=SerializedDeploymentAuthorizationBridge(issuer),
            now_provider=lambda: datetime.now(tz=UTC), authority_repository=repository,
            evaluator_subject_id=config["evaluator_subject_id"],
            artifact_signer=lambda preimage: evaluator_key.sign(preimage).hex(),
            evaluator_signing_key_coordinate=coordinate,
        )

    def evaluator(self) -> AcceptanceEvaluator:
        return self._evaluator


__all__ = ["AcceptanceRuntimeConfigurationError", "InstalledAcceptanceRuntime", "runtime_config_path"]
