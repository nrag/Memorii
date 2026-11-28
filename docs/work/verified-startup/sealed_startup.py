"""Test-only sealed startup for private named v8 fixture copies on macOS."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import sqlite3
import stat
from collections.abc import Callable, Iterator
from contextlib import ExitStack, closing, contextmanager
from pathlib import Path
from typing import Annotated, Literal

from memorii.core.memory_plane.file_lock import locked_file
from memorii.core.persistence.contracts import (
    RuntimePublicationState,
    canonical_json_digest,
)
from memorii.core.persistence.key_owner import (
    RUNTIME_PUBLICATION_SIGNATURE_PURPOSE,
    LocalSigningKeyOwner,
)
from memorii.core.persistence.runtime_journal import verify_runtime_history
from memorii.core.storage_administration.operator_backup import (
    _backup_suppression_watermark,
)
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.stores.sqlite.materialization_sql import rebuild_manifest
from memorii.stores.sqlite.partition import (
    _MATERIALIZATION_CATALOGS_BY_VERSION,
    RAW_MEMORY_PAYLOAD_SCHEMA_VERSION,
    PartitionDataRepository,
)
from pydantic import BaseModel, ConfigDict, Field

_PURPOSE = "memorii.verified-image.v1"
_SEAL = "verified_image.json"
_LIMIT = 8_192
_Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class SealedStartupError(RuntimeError):
    """A seal, authority, or selected byte view could not be verified."""


class _FixtureSealKeyOwner(LocalSigningKeyOwner):
    @staticmethod
    def _validate_purpose(purpose: str) -> None:
        if purpose != _PURPOSE:
            raise SealedStartupError("fixture seal key owner requires the seal signature purpose")


def _seal_key(owner: StorageAdministrationService) -> _FixtureSealKeyOwner:
    return _FixtureSealKeyOwner(owner.installation_root / "control" / "keys")


class ImageSeal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    version: Literal[1]
    authority: _Digest
    publication: _Digest
    verifier: _Digest
    image: _Digest
    length: int = Field(gt=0, le=2**63 - 1)
    signature: str = Field(pattern=r"^[0-9a-f]{128}$")

    def signing_digest(self) -> str:
        return canonical_json_digest(self.model_dump(mode="json", exclude={"signature"}))


def _stat_identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev, info.st_ino, info.st_size, info.st_ctime_ns, info.st_mtime_ns,
        info.st_mode, info.st_uid, info.st_nlink, info.st_flags,
    )


def _require_single_image(path: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        if os.path.lexists(str(path) + suffix):
            raise SealedStartupError("SQLite side files are outside the sealed image")


def _image_descriptors(identity: tuple[int, ...]) -> set[int]:
    descriptors = set()
    for name in os.listdir("/dev/fd"):
        descriptor = int(name)
        try:
            info = os.fstat(descriptor)
        except OSError as exc:
            if exc.errno != errno.EBADF:
                raise
            continue
        if _stat_identity(info) == identity:
            descriptors.add(descriptor)
    return descriptors


@contextmanager
def frozen_fixture(root: Path, path: Path) -> Iterator[None]:
    """Freeze the file and selected directory namespace on a disposable copy."""
    if not path.is_relative_to(root / "partition") or not path.is_file():
        raise SealedStartupError("image must be inside the private fixture")
    _require_single_image(path)
    locations = [path, *[parent for parent in path.parents if parent.is_relative_to(root / "partition")]]
    with ExitStack() as stack:
        for entry in locations:
            info = entry.lstat()
            if stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid():
                raise SealedStartupError("fixture custody requires owner-held real paths")
            os.chflags(entry, info.st_flags | stat.UF_IMMUTABLE, follow_symlinks=False)
            stack.callback(os.chflags, entry, info.st_flags, follow_symlinks=False)
        yield


class ImageView:
    def __init__(self, root: Path, path: Path, descriptor: int) -> None:
        self.path = path
        self.descriptor = descriptor
        self.parents = tuple(parent for parent in path.parents if parent.is_relative_to(root / "partition"))
        self.image = _stat_identity(os.fstat(descriptor))
        self.namespace = tuple(_stat_identity(parent.lstat()) for parent in self.parents)
        self.require_current()

    def require_current(self) -> None:
        _require_single_image(self.path)
        info = self.path.lstat()
        if (
            not stat.S_ISREG(info.st_mode) or not info.st_flags & stat.UF_IMMUTABLE
            or info.st_uid != os.getuid() or info.st_nlink != 1
            or _stat_identity(info) != self.image
            or _stat_identity(os.fstat(self.descriptor)) != self.image
        ):
            raise SealedStartupError("selected image identity or custody changed")
        for parent, recorded in zip(self.parents, self.namespace, strict=True):
            current = parent.lstat()
            if (
                not stat.S_ISDIR(current.st_mode) or not current.st_flags & stat.UF_IMMUTABLE
                or current.st_uid != os.getuid() or _stat_identity(current) != recorded
            ):
                raise SealedStartupError("sealed path namespace changed")

    def hash(self) -> tuple[int, str]:
        with os.fdopen(os.dup(self.descriptor), "rb", buffering=0) as image:
            image.seek(0)
            digest = hashlib.file_digest(image, "sha256").hexdigest()
            length = image.tell()
        self.require_current()
        return length, digest

    @contextmanager
    def sqlite_view(self) -> Iterator[sqlite3.Connection]:
        self.require_current()
        existing = _image_descriptors(self.image)
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro&immutable=1", uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            databases = [tuple(row) for row in connection.execute("PRAGMA database_list")]
            if len(databases) != 1 or databases[0][1:] != ("main", str(self.path)):
                raise SealedStartupError("SQLite opened an unexpected image")
            if len(_image_descriptors(self.image) - existing) != 1:
                raise SealedStartupError("SQLite did not open the hashed inode")
            self.require_current()
            yield connection
            self.require_current()


@contextmanager
def image_view(root: Path, path: Path) -> Iterator[ImageView]:
    # The data connection uses immutable mode, so there are no SQLite locks on
    # this inode to release by closing the hash reader's descriptor.
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        yield ImageView(root, path, descriptor)
    finally:
        os.close(descriptor)


def _authority(owner: StorageAdministrationService) -> tuple[Path, RuntimePublicationState, str]:
    state = owner._require_operational()
    path, publication = owner._active_partition_selection()
    if (
        state.mode != "read_only" or publication is None
        or owner._control.read_pending_intent(publication.repository_id) is not None
    ):
        raise SealedStartupError("sealed startup requires a clean read-only named generation")
    key_id = owner._signer_key_id
    signer = LocalSigningKeyOwner(owner.installation_root / "control" / "keys").public_key_fingerprint(key_id)
    if signer != owner._signing.public_key_fingerprint(key_id):
        raise SealedStartupError("current and opened signing authority differ")
    if owner._trust_registry_digest() != publication.trust_registry_digest:
        raise SealedStartupError("current trust registry differs from the signed publication")
    entry = next((item for item in owner._control.list_trust_entries() if item.key_id == key_id), None)
    if (
        entry is None or entry.lifecycle != "active" or entry.public_key_fingerprint != signer
        or entry.purpose != RUNTIME_PUBLICATION_SIGNATURE_PURPOSE
    ):
        raise SealedStartupError("current trust registry does not authorize the fixture publication signer")
    digest = canonical_json_digest({
        "state": state.model_dump(mode="json"),
        "publication": publication.payload_digest(),
        "journal": owner._control.next_journal_position(),
        "suppression": _backup_suppression_watermark(owner),
        "signer": [key_id, signer],
    })
    return path, publication, digest


def _control_identity(owner: StorageAdministrationService) -> tuple[tuple[int, int], tuple[int, int, int]]:
    return (
        owner._partition_file_identity(owner.control_path()),
        PartitionDataRepository.verification_cookie(owner._control._connection),
    )


def _publication_check(
    owner: StorageAdministrationService, connection: sqlite3.Connection, publication: RuntimePublicationState,
) -> None:
    row = connection.execute("SELECT * FROM main.partition_publication WHERE id = 1").fetchone()
    revisions = connection.execute(
        "SELECT write_revision, data_revision FROM main.memory_revision_state WHERE id = 1",
    ).fetchone()
    if (
        not PartitionDataRepository.uses_raw_memory_payloads(connection)
        or row is None or row["tuple_digest"] != publication.payload_digest()
        or not owner._matches_signed_publication(row, publication)
        or revisions is None or tuple(revisions) != (
            publication.vector.memory_write_revision, publication.vector.memory_data_revision,
        )
    ):
        raise SealedStartupError("selected image does not match the signed publication")


def _exact_verification(
    owner: StorageAdministrationService, connection: sqlite3.Connection, publication: RuntimePublicationState,
) -> None:
    _publication_check(owner, connection, publication)
    catalogs = _MATERIALIZATION_CATALOGS_BY_VERSION[RAW_MEMORY_PAYLOAD_SCHEMA_VERSION]
    if rebuild_manifest(connection, frozenset(name for name, _, _ in catalogs)).manifest.digest() != publication.manifest_digest:
        raise SealedStartupError("image manifest differs from the signed publication")
    verify_runtime_history(
        connection, finalized=publication,
        verify=lambda purpose, digest, signature: owner._verify_journal_signature(
            owner._signer_key_id, purpose, digest, signature,
        ),
        checkpoint_signer_key_id=owner._signer_key_id,
        checkpoint_signer_fingerprint=owner._signing.public_key_fingerprint(owner._signer_key_id),
    )


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SealedStartupError("duplicate image seal field")
        result[key] = value
    return result


def _read_seal(root: Path) -> ImageSeal:
    descriptor = os.open(root / "control" / _SEAL, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
            raise SealedStartupError("image seal requires an owner-only regular file")
        content = handle.read(_LIMIT + 1)
    if len(content) > _LIMIT:
        raise SealedStartupError("image seal is oversized")
    return ImageSeal.model_validate(json.loads(content, object_pairs_hook=_unique_fields))


def issue_seal(root: Path, verifier: str) -> ImageSeal:
    with locked_file(root / ".publication.lock", exclusive=True), StorageAdministrationService(root) as owner:
        path, publication, authority = _authority(owner)
        control = _control_identity(owner)
        with image_view(root, path) as view:
            with view.sqlite_view() as connection:
                _exact_verification(owner, connection, publication)
            length, digest = view.hash()
            if _authority(owner) != (path, publication, authority) or _control_identity(owner) != control:
                raise SealedStartupError("control changed during sealing")
            unsigned = ImageSeal(
                version=1, authority=authority, publication=publication.payload_digest(), verifier=verifier,
                image=digest, length=length, signature="0" * 128,
            )
            sealed = unsigned.model_copy(update={
                "signature": _seal_key(owner).sign(owner._signer_key_id, _PURPOSE, unsigned.signing_digest()),
            })
    # The caller owns the private fixture and persists the seal for the trials.
    return sealed


def acquire(
    owner: StorageAdministrationService, verifier: str, *, before_sqlite: Callable[[], None] | None = None,
) -> tuple[str, int]:
    root = owner.installation_root
    with ExitStack() as stack:
        with owner._publication_fence():
            control = _control_identity(owner)
            owner._control.validate_journal()
            path, publication, authority = _authority(owner)
            seal = _read_seal(root)
            if not _seal_key(owner).verify(owner._signer_key_id, _PURPOSE, seal.signing_digest(), seal.signature):
                raise SealedStartupError("invalid image seal signature")
            if (seal.authority, seal.publication, seal.verifier) != (authority, publication.payload_digest(), verifier):
                raise SealedStartupError("image seal does not match the current authority")
            view = stack.enter_context(image_view(root, path))
        length, digest = view.hash()
        if (length, digest) != (seal.length, seal.image):
            raise SealedStartupError("sealed byte image differs")
        if before_sqlite is not None:
            before_sqlite()
        with owner._publication_fence():
            if _authority(owner) != (path, publication, authority) or _control_identity(owner) != control:
                raise SealedStartupError("control changed before sealed readiness")
            with view.sqlite_view() as connection:
                _publication_check(owner, connection, publication)
        return publication.payload_digest(), length
