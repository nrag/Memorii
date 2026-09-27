"""Hermes runtime binding shared by the optional bridge and first-party factory."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256

from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedHostIngress
from memorii.core.provider.service import ProviderMemoryService


@dataclass(frozen=True)
class HermesAuthenticatedOriginReceipt:
    """Bridge-owned receipt for one immutable, observed user-turn source."""

    session_id: str
    turn_ordinal: int
    author_id: str
    source_content_digest: str
    receipt_digest: str

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        turn_ordinal: int,
        author_id: str,
        source_content_digest: str,
    ) -> HermesAuthenticatedOriginReceipt:
        if (
            not session_id.strip()
            or turn_ordinal < 1
            or not author_id.strip()
            or len(source_content_digest) != 64
            or any(character not in "0123456789abcdef" for character in source_content_digest)
        ):
            raise ValueError("Hermes origin receipt coordinates are invalid")
        material = (
            f"{session_id}\0{turn_ordinal}\0{author_id}\0{source_content_digest}"
        ).encode()
        return cls(
            session_id=session_id,
            turn_ordinal=turn_ordinal,
            author_id=author_id,
            source_content_digest=source_content_digest,
            receipt_digest=sha256(
                b"memorii.hermes.authenticated-origin-receipt.v1\0" + material
            ).hexdigest(),
        )

    def verify(self) -> bool:
        try:
            expected = self.create(
                session_id=self.session_id,
                turn_ordinal=self.turn_ordinal,
                author_id=self.author_id,
                source_content_digest=self.source_content_digest,
            )
        except ValueError:
            return False
        return expected == self


@dataclass(frozen=True)
class HermesProviderRuntimeBinding:
    """One configured service and its host-owned authenticated ingress issuer."""

    service: ProviderMemoryService
    issue_ingress: Callable[[object], AuthenticatedHostIngress]
    completed_turn_runtime: object | None = None
    absent_author_id: str = "memorii.hermes.author.absent.v1"
    revoke_structured_submission_grant: Callable[[str], None] | None = None


__all__ = ["HermesAuthenticatedOriginReceipt", "HermesProviderRuntimeBinding"]
