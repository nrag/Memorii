"""Independent acceptance validation of production revocation evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from acceptance.production_revocation_bridge import SerializedProductionRevocationReader
from acceptance.schema_registry import decode_artifact, signing_preimage


class ProductionRevocationEvidenceError(ValueError):
    """Production evidence is unavailable, malformed, or not current."""


class ProductionRevocationEvidenceVerifier(Protocol):
    def verify(
        self,
        *,
        prior_approval_release_digest: str,
        receipt: bytes,
        checkpoint: bytes,
        require_current_reader_bytes: bool,
    ) -> tuple[dict[str, Any], dict[str, Any]]: ...


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ProductionRevocationEvidenceError("production_revocation_time")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProductionRevocationEvidenceError("production_revocation_time") from exc
    if result.utcoffset() is None:
        raise ProductionRevocationEvidenceError("production_revocation_time")
    return result.astimezone(UTC)


class IndependentProductionRevocationEvidenceVerifier:
    """Verifies registered production objects with separately held trust keys."""

    def __init__(
        self,
        *,
        reader: SerializedProductionRevocationReader,
        trust_keys: Mapping[str, bytes],
    ) -> None:
        if not trust_keys or any(
            not isinstance(coordinate, str)
            or not coordinate
            or not isinstance(key, bytes)
            or len(key) != 32
            for coordinate, key in trust_keys.items()
        ):
            raise ProductionRevocationEvidenceError("production_revocation_trust")
        self._reader = reader
        self._trust_keys = dict(trust_keys)

    def _artifact(self, raw: bytes, schema: str) -> dict[str, Any]:
        try:
            value = decode_artifact(raw, schema)
            coordinate = value["signing_key_coordinate"]
            signature = bytes.fromhex(value["signature"])
            key = self._trust_keys.get(coordinate)
            if key is None:
                raise ProductionRevocationEvidenceError("production_revocation_signer")
            Ed25519PublicKey.from_public_bytes(key).verify(
                signature, signing_preimage(schema, value, coordinate)
            )
            return value
        except (InvalidSignature, ValueError, TypeError) as exc:
            raise ProductionRevocationEvidenceError("production_revocation_signature") from exc

    def _walk_checkpoint(self, value: dict[str, Any], seen: set[str]) -> None:
        digest = value["checkpoint_digest"]
        if digest in seen:
            raise ProductionRevocationEvidenceError("production_revocation_checkpoint_fork")
        seen.add(digest)
        generation = value["checkpoint_generation"]
        predecessor = value["predecessor_checkpoint_digest"]
        if generation == 1:
            if predecessor is not None:
                raise ProductionRevocationEvidenceError("production_revocation_checkpoint_predecessor")
            return
        if predecessor is None:
            raise ProductionRevocationEvidenceError("production_revocation_checkpoint_predecessor")
        try:
            prior = self._artifact(
                self._reader.load_checkpoint(predecessor), "ProductionEpochCheckpoint"
            )
        except ProductionRevocationEvidenceError:
            raise
        except (KeyError, OSError, TypeError, ValueError) as exc:
            raise ProductionRevocationEvidenceError("production_revocation_reader") from exc
        if (
            prior["checkpoint_digest"] != predecessor
            or prior["checkpoint_generation"] != generation - 1
            or prior["active_production_epoch"] > value["active_production_epoch"]
            or _time(prior["observed_at"]) > _time(value["observed_at"])
        ):
            raise ProductionRevocationEvidenceError("production_revocation_checkpoint_history")
        self._walk_checkpoint(prior, seen)

    def verify(
        self,
        *,
        prior_approval_release_digest: str,
        receipt: bytes,
        checkpoint: bytes,
        require_current_reader_bytes: bool,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        receipt_value = self._artifact(receipt, "ProductionRevocationReceipt")
        checkpoint_value = self._artifact(checkpoint, "ProductionEpochCheckpoint")
        if require_current_reader_bytes:
            try:
                current = self._reader.read_for_prior_release(prior_approval_release_digest)
            except (KeyError, OSError, TypeError, ValueError) as exc:
                raise ProductionRevocationEvidenceError("production_revocation_reader") from exc
            if current.receipt != receipt or current.checkpoint != checkpoint:
                raise ProductionRevocationEvidenceError("production_revocation_currentness")
        if (
            receipt_value["prior_approval_release_digest"] != prior_approval_release_digest
            or receipt_value["receipt_digest"]
            not in checkpoint_value["revocation_receipt_digests"]
            or receipt_value["advanced_production_epoch"]
            <= receipt_value["prior_production_epoch"]
            or checkpoint_value["active_production_epoch"]
            < receipt_value["advanced_production_epoch"]
            or _time(receipt_value["withdrawal_requested_at"])
            > _time(receipt_value["completed_at"])
            or _time(receipt_value["completed_at"])
            > _time(checkpoint_value["observed_at"])
        ):
            raise ProductionRevocationEvidenceError("production_revocation_join")
        self._walk_checkpoint(checkpoint_value, set())
        return receipt_value, checkpoint_value
