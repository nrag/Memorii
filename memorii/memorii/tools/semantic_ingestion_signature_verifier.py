"""Ed25519 verification for independently provisioned traceability trust."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

_LOWERCASE_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ED25519_PUBLIC_KEY_LENGTH = 32
_ED25519_SIGNATURE_LENGTH = 64


@dataclass(frozen=True)
class Ed25519VerificationKeyBinding:
    """One externally provisioned profile-to-public-key authorization."""

    profile_id: str
    public_key: bytes
    public_key_digest: str
    digest_domain: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.profile_id, str) or not self.profile_id:
            raise ValueError("signature_profile_id_invalid")
        if not isinstance(self.public_key, bytes) or len(self.public_key) != _ED25519_PUBLIC_KEY_LENGTH:
            raise ValueError("ed25519_public_key_invalid")
        if not isinstance(self.digest_domain, bytes) or not self.digest_domain:
            raise ValueError("public_key_digest_domain_invalid")
        if not isinstance(self.public_key_digest, str) or not _LOWERCASE_SHA256.fullmatch(self.public_key_digest):
            raise ValueError("public_key_digest_invalid")
        expected_digest = sha256(self.digest_domain + self.public_key).hexdigest()
        if self.public_key_digest != expected_digest:
            raise ValueError("public_key_digest_mismatch")


class Ed25519SignatureVerifier:
    """Verify exact signature preimage bytes against immutable configured keys."""

    def __init__(self, bindings: tuple[Ed25519VerificationKeyBinding, ...]) -> None:
        if not bindings:
            raise ValueError("signature_bindings_empty")
        verified: dict[tuple[str, str], Ed25519PublicKey] = {}
        for binding in bindings:
            if not isinstance(binding, Ed25519VerificationKeyBinding):
                raise ValueError("signature_binding_invalid")
            coordinate = (binding.profile_id, binding.public_key_digest)
            if coordinate in verified:
                raise ValueError("signature_binding_duplicate")
            try:
                verified[coordinate] = Ed25519PublicKey.from_public_bytes(binding.public_key)
            except ValueError as exc:
                raise ValueError("ed25519_public_key_invalid") from exc
        self._keys: Mapping[tuple[str, str], Ed25519PublicKey] = MappingProxyType(verified)

    def verify(self, profile_id: str, public_key_digest: str, payload: bytes, signature: bytes) -> bool:
        """Return whether *signature* authenticates the exact supplied payload."""
        if (
            not isinstance(profile_id, str)
            or not isinstance(public_key_digest, str)
            or not isinstance(payload, bytes)
            or not isinstance(signature, bytes)
            or len(signature) != _ED25519_SIGNATURE_LENGTH
        ):
            return False
        key = self._keys.get((profile_id, public_key_digest))
        if key is None:
            return False
        try:
            key.verify(signature, payload)
        except (InvalidSignature, ValueError, TypeError):
            return False
        return True
