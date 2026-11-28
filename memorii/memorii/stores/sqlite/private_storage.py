"""POSIX custody checks for owner-managed SQLite data and input files."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from memorii.stores.sqlite.darwin_acl import require_no_extended_acl


class PrivateStorageError(PermissionError):
    """A managed storage object has unsafe ownership, type, or permissions."""


def _check_owner(
    location: Path | int, *, directory: bool, allow_public_mode: bool = False
) -> os.stat_result:
    state = os.fstat(location) if isinstance(location, int) else location.lstat()
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if (
        not expected_type(state.st_mode)
        or state.st_uid != os.geteuid()
        or (not directory and state.st_nlink != 1)
        or (not allow_public_mode and state.st_mode & 0o077)
    ):
        raise PrivateStorageError("expected an owner-only directory or regular file")
    try:
        require_no_extended_acl(location)
    except PermissionError as exc:
        raise PrivateStorageError("managed storage must have no extended access rules") from exc
    return state


def require_private_directory(path: Path) -> None:
    _check_owner(path, directory=True)


def require_private_file(path: Path, *, allow_missing: bool = False) -> None:
    try:
        _check_owner(path, directory=False)
    except FileNotFoundError:
        if not allow_missing:
            raise


def ensure_private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    require_private_directory(path)


@contextmanager
def open_private_file(path: Path) -> Iterator[BinaryIO]:
    """Read the same private regular file whose descriptor we check."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as source:
        _check_owner(source.fileno(), directory=False)
        yield source


def read_private_file(path: Path, *, limit: int) -> bytes:
    with open_private_file(path) as source:
        return source.read(limit)


@contextmanager
def open_private_lock(path: Path) -> Iterator[BinaryIO]:
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    with os.fdopen(descriptor, "r+b") as handle:
        _check_owner(handle.fileno(), directory=False)
        yield handle


def require_private_sqlite(path: Path, *, allow_missing: bool = False) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        require_private_file(path.with_name(path.name + suffix), allow_missing=bool(suffix) or allow_missing)


def prepare_private_sqlite(path: Path, *, require_existing: bool = False) -> None:
    """Create the main file privately so SQLite inherits a safe sidecar mode."""
    require_private_directory(path.parent)
    require_private_sqlite(path, allow_missing=not require_existing)
    if not require_existing:
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            require_private_sqlite(path)
        else:
            try:
                _check_owner(descriptor, directory=False)
            finally:
                os.close(descriptor)


def prepare_installation_root(path: Path, *, adopting_legacy: bool = False) -> None:
    """Create a private root or adopt an empty, owner-controlled directory."""
    try:
        ensure_private_directory(path)
    except PrivateStorageError:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            state = _check_owner(descriptor, directory=True, allow_public_mode=True)
            if state.st_mode & 0o022 or (not adopting_legacy and os.listdir(descriptor)):
                raise
            os.fchmod(descriptor, 0o700)
        finally:
            os.close(descriptor)


def repair_installation_permissions(root: Path) -> None:
    """Constrain only the named installation and its managed subtrees."""
    def open_owned(path: Path | str, *, directory: bool, parent: int | None = None) -> int:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        if directory:
            flags |= os.O_DIRECTORY
        descriptor = os.open(path, flags, dir_fd=parent)
        try:
            _check_owner(descriptor, directory=directory, allow_public_mode=True)
        except OSError:
            os.close(descriptor)
            raise
        return descriptor

    def restrict(parent: int, name: str, *, directory: bool) -> None:
        descriptor = open_owned(name, directory=directory, parent=parent)
        try:
            os.fchmod(descriptor, 0o700 if directory else 0o600)
            if directory:
                for child in os.listdir(descriptor):
                    state = os.stat(child, dir_fd=descriptor, follow_symlinks=False)
                    restrict(descriptor, child, directory=stat.S_ISDIR(state.st_mode))
        finally:
            os.close(descriptor)

    root_descriptor = open_owned(root, directory=True)
    try:
        # Refuse to change an arbitrary directory named by mistake.
        control = open_owned("control", directory=True, parent=root_descriptor)
        try:
            database = open_owned("control.sqlite3", directory=False, parent=control)
            with os.fdopen(database, "rb") as control_file:
                if control_file.read(16) != b"SQLite format 3\0":
                    raise PrivateStorageError("installation control SQLite header is missing")
            os.close(open_owned("keys", directory=True, parent=control))
        finally:
            os.close(control)
        # Restrict the outer boundary before inspecting other descendants.
        os.fchmod(root_descriptor, 0o700)
        members = set(os.listdir(root_descriptor))
        for name in ("control", "partition", "spool"):
            if name in members:
                restrict(root_descriptor, name, directory=True)
        for name in (".init.lock", ".publication.lock"):
            if name in members:
                restrict(root_descriptor, name, directory=False)
    finally:
        os.close(root_descriptor)
