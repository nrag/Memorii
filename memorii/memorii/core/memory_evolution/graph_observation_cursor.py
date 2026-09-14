"""Opaque Ed25519 cursor codec for graph-observation page owners."""
from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field

from memorii.core.memory_evolution.graph_observation_contracts import (
    GraphObservationCursorPayload,
    GraphObservationUnsignedCursorCoordinates,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueError,
    decode_typed_value,
    encode_typed_value,
)

_CURSOR_DOMAIN = b"memorii.graph-observation.cursor.v1\0"


class GraphObservationCursorError(ValueError):
    """A malformed, over-budget, or cryptographically invalid cursor."""


class GraphObservationCursorDecodeLimits(BaseModel):
    """Protected resource ceilings passed by the production composition root."""
    maximum_wire_characters: int = Field(ge=32, le=32_768)
    maximum_raw_bytes: int = Field(ge=16, le=24_576)
    maximum_ctv_nodes: int = Field(ge=1, le=4_096)
    maximum_ctv_depth: int = Field(ge=1, le=64)
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class GraphObservationCursorVerificationKey(BaseModel):
    public_key: bytes = Field(min_length=32, max_length=32)
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    if not value or "=" in value:
        raise ValueError("invalid base64url")
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class GraphObservationCursorSigner:
    """Private signing authority supplied only by trusted server configuration."""
    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._private_key = private_key

    def sign(self, coordinates: GraphObservationUnsignedCursorCoordinates) -> GraphObservationCursorPayload:
        raw = encode_typed_value(coordinates.model_dump(mode="python"))
        return coordinates.signed(self._private_key.sign(_CURSOR_DOMAIN + raw).hex())


class GraphObservationCursorVerifier:
    """Public verifier that can run independently from the server signing key."""
    def __init__(self, verification_key: GraphObservationCursorVerificationKey, limits: GraphObservationCursorDecodeLimits) -> None:
        self._public_key = Ed25519PublicKey.from_public_bytes(verification_key.public_key)
        self._limits = limits

    def decode(self, cursor: str) -> GraphObservationCursorPayload:
        try:
            if len(cursor) > self._limits.maximum_wire_characters:
                raise ValueError("cursor wire ceiling")
            version, encoded = cursor.split(".")
            if version != "v1" or len(encoded) > ((self._limits.maximum_raw_bytes + 2) // 3) * 4:
                raise ValueError("invalid cursor wire format")
            raw = _unb64(encoded)
            if len(raw) > self._limits.maximum_raw_bytes or _b64(raw) != encoded:
                raise ValueError("cursor raw ceiling")
            value = decode_typed_value(raw, max_nodes=self._limits.maximum_ctv_nodes, max_depth=self._limits.maximum_ctv_depth)
            if encode_typed_value(value) != raw or not isinstance(value, dict):
                raise ValueError("cursor must be canonical")
            payload = GraphObservationCursorPayload.model_validate(value)
            coordinates = GraphObservationUnsignedCursorCoordinates.model_validate(payload.model_dump(mode="python", exclude={"signature"}))
            self._public_key.verify(bytes.fromhex(payload.signature), _CURSOR_DOMAIN + encode_typed_value(coordinates.model_dump(mode="python")))
            return payload
        except (binascii.Error, CanonicalTypedValueError, InvalidSignature, TypeError, ValueError, RecursionError):
            raise GraphObservationCursorError("invalid graph observation cursor") from None


class GraphObservationCursorCodec:
    """Composition convenience for a configured signer and separate verifier."""
    def __init__(self, signer: GraphObservationCursorSigner, verifier: GraphObservationCursorVerifier) -> None:
        self._signer = signer
        self._verifier = verifier

    def issue(self, coordinates: GraphObservationUnsignedCursorCoordinates) -> str:
        payload = self._signer.sign(coordinates)
        return f"v1.{_b64(encode_typed_value(payload.model_dump(mode='python')))}"

    def decode(self, cursor: str) -> GraphObservationCursorPayload:
        return self._verifier.decode(cursor)

    @staticmethod
    def continuation_failure(*, payload: GraphObservationCursorPayload, now: datetime, caller_context_digest: str, authorization_decision_digest: str, page_policy_revision: str, page_policy_digest: str, graph_revision: str, observation_revision: str, requested_total_page_size: int, view: str | None, valid_at: datetime | None, system_as_of: datetime | None) -> Literal["invalid_cursor", "stale_cursor", "revoked_access"] | None:
        if now.tzinfo is None or now.utcoffset() is None or now.astimezone(UTC) >= payload.authorization_expires_at:
            return "revoked_access"
        if (payload.page_policy_revision != page_policy_revision or payload.page_policy_digest != page_policy_digest or payload.graph_revision != graph_revision or payload.observation_revision != observation_revision):
            return "stale_cursor"
        if (payload.caller_context_digest != caller_context_digest or payload.authorization_decision_digest != authorization_decision_digest or payload.requested_total_page_size != requested_total_page_size or payload.view != view or payload.valid_at != valid_at or payload.system_as_of != system_as_of):
            return "invalid_cursor"
        return None
