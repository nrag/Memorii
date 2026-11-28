"""Typed, signed currentness records for independent installation custody."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_plane.file_lock import locked_file
from memorii.core.persistence.contracts import canonical_json_digest
from memorii.core.persistence.key_owner import (
    INSTALLATION_CONTROL_RECOVERY_SIGNATURE_PURPOSE,
    INSTALLATION_RECOVERY_HEAD_SIGNATURE_PURPOSE,
    LocalSigningKeyOwner,
    verify_public_signature,
)
from memorii.stores.sqlite.private_storage import (
    read_private_file,
    require_private_directory,
    write_private_file,
)

_Identity = Annotated[str, Field(min_length=1, max_length=512)]
_Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
_Signature = Annotated[str, Field(pattern=r"^[0-9a-f]{128}$")]
_Revision = Annotated[int, Field(ge=1, strict=True)]
_MAX_HEAD_BYTES = 256 * 1024


class RecoveryAuthorityError(RuntimeError):
    """Independent current authority could not be proven or changed safely."""


class _RecoveryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class InstallationRecoveryAnchor(_RecoveryRecord):
    protocol_version: Literal[1] = 1
    installation_id: _Identity
    repository_id: _Identity
    custody_id: _Identity
    control_revision: _Revision
    journal_ordinal: _Revision
    journal_tip: _Digest
    eligibility_epoch: _Revision
    signer_fingerprint: _Digest
    publication_digest: _Digest
    bundle_digest: _Digest


class RecoveryBundleMember(_RecoveryRecord):
    owner_id: _Identity
    kind: Literal[
        "control_snapshot", "control_journal", "public_trust", "finalized_publications",
        "participant_inventory", "deny_state", "suppression",
    ]
    schema_version: _Revision
    size_bytes: Annotated[int, Field(ge=0, strict=True)]
    digest: _Digest
    source_coordinate: _Digest


_REQUIRED_BUNDLE_KINDS = frozenset({
    "control_snapshot", "control_journal", "public_trust", "finalized_publications", "participant_inventory",
})


class InstallationControlRecoveryBundle(_RecoveryRecord):
    protocol_version: Literal[1] = 1
    installation_id: _Identity
    repository_id: _Identity
    custody_id: _Identity
    generation_id: _Identity
    control_revision: _Revision
    journal_ordinal: _Revision
    journal_tip: _Digest
    eligibility_epoch: _Revision
    publication_digest: _Digest
    trust_registry_digest: _Digest
    signer_fingerprint: _Digest
    signer_key_id: _Identity
    members: tuple[RecoveryBundleMember, ...] = Field(min_length=5, max_length=256)
    signature: _Signature

    @model_validator(mode="after")
    def closed_inventory(self) -> Self:
        identities = tuple((member.owner_id, member.kind) for member in self.members)
        if identities != tuple(sorted(set(identities))):
            raise ValueError("recovery bundle members must be unique and ordered")
        singleton_kinds = tuple(member.kind for member in self.members if member.kind in _REQUIRED_BUNDLE_KINDS)
        if tuple(sorted(singleton_kinds)) != tuple(sorted(_REQUIRED_BUNDLE_KINDS)):
            raise ValueError("recovery bundle core inventory is incomplete")
        return self

    def unsigned_digest(self) -> str:
        return canonical_json_digest(self.model_dump(mode="json", exclude={"signature"}))

    def digest(self) -> str:
        return canonical_json_digest(self.model_dump(mode="json"))

    def anchor(self) -> InstallationRecoveryAnchor:
        return InstallationRecoveryAnchor(
            installation_id=self.installation_id, repository_id=self.repository_id, custody_id=self.custody_id,
            control_revision=self.control_revision, journal_ordinal=self.journal_ordinal, journal_tip=self.journal_tip,
            eligibility_epoch=self.eligibility_epoch, signer_fingerprint=self.signer_fingerprint,
            publication_digest=self.publication_digest, bundle_digest=self.digest(),
        )

    def verify(self, anchor: InstallationRecoveryAnchor, public_key: bytes) -> None:
        if (
            self.anchor() != anchor
            or hashlib.sha256(public_key).hexdigest() != anchor.signer_fingerprint
            or not verify_public_signature(
                public_key, INSTALLATION_CONTROL_RECOVERY_SIGNATURE_PURPOSE, self.unsigned_digest(), self.signature,
            )
        ):
            raise RecoveryAuthorityError("integrity_error: recovery bundle does not match the trusted anchor")


class RecoveryParticipantExpectation(_RecoveryRecord):
    participant_id: _Identity
    revision: Annotated[int, Field(ge=0, strict=True)]
    pre_state_digest: _Digest
    effect_digest: _Digest


class PendingRecoveryHead(_RecoveryRecord):
    state: Literal["pending"] = "pending"
    predecessor: _Digest
    prior_anchor: InstallationRecoveryAnchor
    operation: Literal[
        "backup",
        "credential",
        "grant",
        "suppression",
        "mode",
        "trust",
        "participant",
        "generation",
        "erasure",
    ]
    operation_digest: _Digest
    participants: tuple[RecoveryParticipantExpectation, ...] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def unique_ordered_participants(self) -> Self:
        identities = tuple(item.participant_id for item in self.participants)
        if identities != tuple(sorted(set(identities))):
            raise ValueError("recovery participants must be unique and ordered")
        return self


class SealedRecoveryHead(_RecoveryRecord):
    state: Literal["sealed"] = "sealed"
    anchor: InstallationRecoveryAnchor
    predecessor: _Digest | None = None
    operation_digest: _Digest | None = None
    pending_digest: _Digest | None = None
    outcome: Literal["registered", "applied", "aborted"]

    @model_validator(mode="after")
    def exact_transition(self) -> Self:
        parts = (self.predecessor, self.operation_digest, self.pending_digest)
        if self.outcome == "registered":
            if any(part is not None for part in parts):
                raise ValueError("initial recovery registration has no predecessor")
        elif any(part is None for part in parts):
            raise ValueError("recovery transition must name its exact pending predecessor")
        return self


RecoveryHeadPayload = Annotated[PendingRecoveryHead | SealedRecoveryHead, Field(discriminator="state")]


def _unique_object(items: list[tuple[str, object]]) -> dict[str, object]:
    result = dict(items)
    if len(items) != len(result):
        raise ValueError("duplicate recovery record field")
    return result


def decode_recovery_json(content: bytes) -> object:
    """Decode a closed recovery record without accepting duplicate fields."""
    return json.loads(content, object_pairs_hook=_unique_object)


def _anchor(payload: RecoveryHeadPayload) -> InstallationRecoveryAnchor:
    return payload.anchor if isinstance(payload, SealedRecoveryHead) else payload.prior_anchor


class InstallationRecoveryHead(_RecoveryRecord):
    protocol_version: Literal[1] = 1
    payload: RecoveryHeadPayload
    signer_key_id: _Identity
    signature: _Signature

    def unsigned_digest(self) -> str:
        return canonical_json_digest(self.model_dump(mode="json", exclude={"signature"}))

    def digest(self) -> str:
        return canonical_json_digest(self.model_dump(mode="json"))


def sign_recovery_head(
    payload: RecoveryHeadPayload, *, signer: LocalSigningKeyOwner, signer_key_id: str,
) -> InstallationRecoveryHead:
    if _anchor(payload).signer_fingerprint != signer.public_key_fingerprint(signer_key_id):
        raise RecoveryAuthorityError("denied: recovery signer does not match the anchor")
    unsigned = InstallationRecoveryHead(payload=payload, signer_key_id=signer_key_id, signature="0" * 128)
    return unsigned.model_copy(update={
        "signature": signer.sign(
            signer_key_id, INSTALLATION_RECOVERY_HEAD_SIGNATURE_PURPOSE, unsigned.unsigned_digest(),
        ),
    })


class IndependentRecoveryCustody:
    """Compare and exchange a private recovery head against pinned public trust.

    Callers own participant locking, effect receipts and the authenticated
    independent custody location. The data archive supplies neither trust nor
    the expected installation and repository.
    """

    def __init__(
        self,
        directory: Path,
        *,
        custody_id: str,
        installation_id: str,
        repository_id: str,
        trusted_public_keys: Mapping[str, bytes],
    ) -> None:
        require_private_directory(directory)
        self._head_path = directory / "head.json"
        self._lock = directory / ".head.lock"
        self._identity = (custody_id, installation_id, repository_id)
        self._public_keys = dict(trusted_public_keys)

    def _verify(self, head: InstallationRecoveryHead) -> None:
        anchor = _anchor(head.payload)
        key = self._public_keys.get(head.signer_key_id)
        if (
            (anchor.custody_id, anchor.installation_id, anchor.repository_id) != self._identity
            or key is None
            or hashlib.sha256(key).hexdigest() != anchor.signer_fingerprint
            or not verify_public_signature(
                key, INSTALLATION_RECOVERY_HEAD_SIGNATURE_PURPOSE, head.unsigned_digest(), head.signature,
            )
        ):
            raise RecoveryAuthorityError("integrity_error: recovery head identity or signature is invalid")

    def _read(self) -> InstallationRecoveryHead:
        try:
            content = read_private_file(self._head_path, limit=_MAX_HEAD_BYTES + 1)
            if len(content) > _MAX_HEAD_BYTES:
                raise RecoveryAuthorityError("integrity_error: recovery head exceeds limit")
            head = InstallationRecoveryHead.model_validate(decode_recovery_json(content))
        except (OSError, ValueError) as exc:
            raise RecoveryAuthorityError("unavailable: recovery head could not be read") from exc
        self._verify(head)
        return head

    def _write(self, head: InstallationRecoveryHead, *, exclusive: bool = False) -> None:
        content = head.model_dump_json().encode("utf-8")
        if len(content) > _MAX_HEAD_BYTES:
            raise RecoveryAuthorityError("resource_exhausted: recovery head exceeds limit")
        write_private_file(self._head_path, content, exclusive=exclusive)

    def current_sealed(self) -> InstallationRecoveryHead:
        head = self.current()
        if not isinstance(head.payload, SealedRecoveryHead):
            raise RecoveryAuthorityError("needs_reconciliation: independent authority is pending")
        return head

    def current(self) -> InstallationRecoveryHead:
        """Read the verified currentness record for offline reconciliation."""
        with locked_file(self._lock, exclusive=False, private=True):
            return self._read()

    @contextmanager
    def guard_current_seal(self, expected: InstallationRecoveryHead) -> Iterator[None]:
        """Keep a verified seal current through a local activation commit."""
        with locked_file(self._lock, exclusive=False, private=True):
            head = self._read()
            if not isinstance(head.payload, SealedRecoveryHead) or head != expected:
                raise RecoveryAuthorityError("conflict: independent seal advanced during replacement activation")
            yield

    def bundle_path(self, anchor: InstallationRecoveryAnchor) -> Path:
        """Derive the independent retention path from a trusted anchor."""
        if (anchor.custody_id, anchor.installation_id, anchor.repository_id) != self._identity:
            raise RecoveryAuthorityError("denied: recovery bundle belongs to different custody")
        return self._head_path.parent / f"bundle-{anchor.bundle_digest}"

    @contextmanager
    def _writer_lease(self) -> Iterator[None]:
        with locked_file(self._lock, exclusive=True, private=True):
            yield

    def register(self, head: InstallationRecoveryHead) -> None:
        with self._writer_lease():
            self._register_locked(head)

    def _register_locked(self, head: InstallationRecoveryHead) -> None:
        self._verify(head)
        if not isinstance(head.payload, SealedRecoveryHead) or head.payload.outcome != "registered":
            raise RecoveryAuthorityError("invalid_request: registration requires an initial sealed head")
        try:
            self._write(head, exclusive=True)
        except FileExistsError as exc:
            raise RecoveryAuthorityError("conflict: recovery custody already registered") from exc

    def prepare(self, head: InstallationRecoveryHead) -> None:
        with self._writer_lease():
            self._prepare_locked(head)

    def _prepare_locked(self, head: InstallationRecoveryHead) -> None:
        self._verify(head)
        prior = self._read()
        if (
            not isinstance(prior.payload, SealedRecoveryHead)
            or not isinstance(head.payload, PendingRecoveryHead)
            or head.payload.predecessor != prior.digest()
            or head.payload.prior_anchor != prior.payload.anchor
        ):
            raise RecoveryAuthorityError("conflict: recovery prepare requires the exact current sealed head")
        self._write(head)

    def seal(self, head: InstallationRecoveryHead, *, effects: Mapping[str, str]) -> None:
        with self._writer_lease():
            self._seal_locked(head, effects=effects)

    def _seal_locked(self, head: InstallationRecoveryHead, *, effects: Mapping[str, str]) -> None:
        self._verify(head)
        prior = self._read()
        old, new = prior.payload, head.payload
        if (
            not isinstance(old, PendingRecoveryHead)
            or not isinstance(new, SealedRecoveryHead)
            or new.outcome == "registered"
            or new.pending_digest != prior.digest()
            or new.predecessor != old.predecessor
            or new.operation_digest != old.operation_digest
        ):
            raise RecoveryAuthorityError("conflict: recovery seal requires the exact current pending head")
        expected = {item.participant_id: item.effect_digest for item in old.participants}
        if new.outcome == "aborted":
            if effects or new.anchor != old.prior_anchor:
                raise RecoveryAuthorityError("conflict: recovery abort requires an unchanged verified authority")
        elif (
            effects != expected
            or not self._is_monotonic(old.prior_anchor, new.anchor)
            or (
                new.anchor.signer_fingerprint != old.prior_anchor.signer_fingerprint
                and old.operation not in ("trust", "generation")
            )
        ):
            raise RecoveryAuthorityError("conflict: recovery seal lacks the exact successor evidence")
        self._write(head)

    @staticmethod
    def _is_monotonic(old: InstallationRecoveryAnchor, new: InstallationRecoveryAnchor) -> bool:
        return (
            new.control_revision >= old.control_revision
            and new.journal_ordinal >= old.journal_ordinal
            and new.eligibility_epoch >= old.eligibility_epoch
            and (new.journal_ordinal != old.journal_ordinal or new.journal_tip == old.journal_tip)
        )
