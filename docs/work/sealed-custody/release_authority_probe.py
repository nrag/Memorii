"""Current authority checks for the private retained socket experiment."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from collections.abc import Callable
from pathlib import Path

from memorii.core.harness_state.credentials import (
    IssuedCredential,
    SidecarCredentialStore,
)
from memorii.core.harness_state.service import RuntimeReadGrant
from memorii.core.memory_plane.file_lock import locked_file
from memorii.core.storage_administration.service import (
    StorageAdministrationError,
    StorageAdministrationService,
)
from retained_vfs_probe import ReleaseDenied
from sealed_startup import SealedStartupError, _authority, _publication_check


class ReleaseAuthority:
    """Bind one authenticated publication to the retained view and each request."""

    def __init__(self, root: Path, principal: str) -> None:
        self.root = root
        self.principal = principal
        self.store = SidecarCredentialStore(root / "control" / "credentials")
        with locked_file(root / ".publication.lock", exclusive=True), StorageAdministrationService(root) as owner:
            self.coordinate = _authority(owner)
        self.image = self.coordinate[0]

    def verify_view(self, connection: sqlite3.Connection) -> None:
        original = connection.row_factory
        try:
            connection.row_factory = sqlite3.Row
            with (
                locked_file(self.root / ".publication.lock", exclusive=True),
                StorageAdministrationService(self.root) as owner,
            ):
                if _authority(owner) != self.coordinate:
                    raise ReleaseDenied("publication changed while opening retained view")
                _publication_check(owner, connection, self.coordinate[1])
        finally:
            connection.row_factory = original

    def guard(self, secret: str, grant: RuntimeReadGrant, task: str) -> Callable[[], None]:
        """Caller invokes the check under the same fence as mutation and send."""
        issued: IssuedCredential | None = None

        def require_current() -> None:
            nonlocal issued
            self.store.verify_permissions()
            credential = self.store.credential_for(secret)
            if credential is None or credential.principal != self.principal or grant.principal != credential.principal:
                raise ReleaseDenied("credential no longer authorized")
            if not grant.authorizes(task):
                raise ReleaseDenied("grant no longer authorizes the requested task")
            if issued is not None and credential != issued:
                raise ReleaseDenied("credential changed after intake")
            issued = credential
            try:
                with StorageAdministrationService(self.root) as owner:
                    current = _authority(owner)
            except (StorageAdministrationError, SealedStartupError) as exc:
                raise ReleaseDenied("current signed publication failed validation") from exc
            if current != self.coordinate:
                raise ReleaseDenied("signed publication changed after acquisition")

        return require_current


def rotate_fixture_credential(root: Path, secret: str) -> str:
    """Issue and retire under the existing fence for this private fixture."""
    store = SidecarCredentialStore(root / "control" / "credentials")
    with StorageAdministrationService(root) as owner, owner._publication_fence():
        old = store.credential_for(secret)
        if old is None:
            raise RuntimeError("fixture credential is already retired")
        index = root / "control" / "credentials" / "credentials.json"
        # Reuse the production minting format in a private staging directory,
        # then atomically replace the live index once under the fence.
        with tempfile.TemporaryDirectory(dir=index.parent) as directory:
            staging = SidecarCredentialStore(directory)
            _, token = staging.issue(old.principal)
            (replacement,) = staging._read_entries()
        remaining = [entry for entry in store._read_entries() if entry["credential_id"] != old.credential_id]
        remaining.append(replacement)
        descriptor, temporary = tempfile.mkstemp(dir=index.parent, prefix=".rotated-")
        try:
            with os.fdopen(descriptor, "w") as writer:
                json.dump({"entries": remaining}, writer)
                writer.flush()
                os.fsync(writer.fileno())
            os.replace(temporary, index)
            directory = os.open(index.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return token
