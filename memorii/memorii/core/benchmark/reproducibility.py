"""Helpers for deterministic benchmark runs."""

from __future__ import annotations

import hashlib
import json
import os
import random
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, Protocol, TypeAlias

from pydantic import BaseModel, ConfigDict, model_validator

from memorii.core.benchmark.models import BenchmarkRunConfig, BenchmarkScenarioFixture

SourceState: TypeAlias = Literal["clean", "dirty", "unversioned"]
_SOURCE_FINGERPRINT_DOMAIN = b"memorii-installable-package"
_IGNORED_SOURCE_DIRECTORY_NAMES = frozenset({"__pycache__"})
_IGNORED_SOURCE_SUFFIXES = frozenset({".pyc", ".pyo"})


class SourceIdentity(BaseModel):
    """Source revision and tree state used to decide report certifiability."""

    revision: str
    state: SourceState
    certifiable: bool

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_certifiability(self) -> SourceIdentity:
        expected = self.state == "clean" and self.revision != "local-source-tree"
        if self.certifiable != expected:
            raise ValueError("source identity certifiability must match revision and tree state")
        return self


class _DigestWriter(Protocol):
    def update(self, data: bytes, /) -> None: ...


def apply_seed(seed: int) -> None:
    random.seed(seed)


def build_run_id(*, config: BenchmarkRunConfig, fixtures: list[BenchmarkScenarioFixture]) -> str:
    fixture_key = "|".join(sorted(f"{fixture.scenario_id}:{fixture.category.value}" for fixture in fixtures))
    raw = f"{config.run_label}:{config.seed}:{fixture_key}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"bench-{digest}"


def build_benchmark_fingerprint(config: Mapping[str, object]) -> str:
    """Return a stable fingerprint for one explicitly owned benchmark layer."""
    payload = json.dumps(dict(config), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonical_json_digest(value: object) -> str:
    """Return the SHA-256 digest of one canonical JSON value."""

    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    """Return the SHA-256 digest of a persisted artifact without loading it."""

    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for block in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_source_revision(*, root: Path, dry_run: bool) -> str:
    """Resolve immutable source identity without invoking a shell.

    CI should set ``MEMORII_SOURCE_REVISION`` to the checked-out commit. Local
    runs use the enclosing Git repository when available. Only dry runs may
    use the explicit local sentinel.
    """

    git_revision = _git_head_revision(root)
    configured = os.environ.get("MEMORII_SOURCE_REVISION")
    if configured is not None:
        revision = configured.strip()
        if not revision or revision != configured:
            raise ValueError("MEMORII_SOURCE_REVISION must be non-empty and normalized")
        if revision == "local-source-tree" and not dry_run:
            raise ValueError("live benchmark reports require a real source revision")
        if git_revision is not None and revision != git_revision:
            raise ValueError("MEMORII_SOURCE_REVISION does not match the checked-out Git HEAD")
        return revision

    if git_revision is not None:
        return git_revision
    if dry_run:
        return "local-source-tree"
    raise ValueError(
        "live benchmark reports require MEMORII_SOURCE_REVISION or an enclosing Git checkout"
    )


def resolve_source_state(*, root: Path) -> SourceState:
    """Return whether the executing source tree is clean and version controlled."""

    status = _git_status_porcelain(root)
    if status is None:
        return "unversioned"
    return "dirty" if status else "clean"


def resolve_source_identity(*, root: Path, dry_run: bool) -> SourceIdentity:
    """Resolve a single validated source identity for report construction."""

    revision = resolve_source_revision(root=root, dry_run=dry_run)
    state = resolve_source_state(root=root)
    return SourceIdentity(
        revision=revision,
        state=state,
        certifiable=state == "clean" and revision != "local-source-tree",
    )


def _git_status_porcelain(root: Path) -> str | None:
    repository_root = _find_git_root(root)
    if repository_root is None:
        return None
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository_root), "status", "--porcelain=v1", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def _find_git_root(root: Path) -> Path | None:
    for candidate in (root.resolve(), *root.resolve().parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _git_head_revision(root: Path) -> str | None:
    for candidate in (root.resolve(), *root.resolve().parents):
        git_dir = candidate / ".git"
        if git_dir.is_file():
            pointer = git_dir.read_text(encoding="utf-8").strip()
            if not pointer.startswith("gitdir: "):
                continue
            git_dir = (candidate / pointer.removeprefix("gitdir: ")).resolve()
        if not git_dir.is_dir():
            continue
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref: "):
            ref = head.removeprefix("ref: ")
            ref_path = git_dir / ref
            if ref_path.is_file():
                return ref_path.read_text(encoding="utf-8").strip()
            packed_refs = git_dir / "packed-refs"
            if packed_refs.is_file():
                for line in packed_refs.read_text(encoding="utf-8").splitlines():
                    if line and not line.startswith(("#", "^")):
                        revision, packed_ref = line.split(" ", 1)
                        if packed_ref == ref:
                            return revision
            return None
        return head or None
    return None


def build_installable_package_fingerprint(*, package_root: Path) -> str:
    """Hash every owned installable package file using a canonical byte protocol.

    Paths are UTF-8 encoded relative to ``package_root`` and ordered by their
    POSIX spelling. File contents remain raw bytes. Every protocol element is
    length-prefixed, so path/content boundaries are unambiguous. Only generated
    Python bytecode and ``__pycache__`` directories are excluded. Missing,
    empty, unreadable, symlinked, or non-regular ownership fails closed.
    """

    if package_root.is_symlink():
        raise ValueError(f"installable package root cannot be a symlink: {package_root}")
    resolved_root = package_root.resolve(strict=True)
    if not resolved_root.is_dir():
        raise ValueError(f"installable package root is not a directory: {package_root}")

    files = _installable_package_files(resolved_root)
    if not files:
        raise ValueError("installable package contains no owned source files")

    digest = hashlib.sha256()
    _update_fingerprint_frame(digest, _SOURCE_FINGERPRINT_DOMAIN)
    _update_fingerprint_frame(digest, len(files).to_bytes(8, byteorder="big"))
    for path in files:
        relative_path = path.relative_to(resolved_root).as_posix().encode("utf-8")
        _update_fingerprint_frame(digest, relative_path)
        _update_fingerprint_frame(digest, path.read_bytes())
    return digest.hexdigest()


def _installable_package_files(package_root: Path) -> list[Path]:
    pending = [package_root]
    files: list[Path] = []
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                relative_path = path.relative_to(package_root).as_posix()
                if entry.is_symlink():
                    raise ValueError(f"installable package cannot contain symlinks: {relative_path}")
                if entry.is_dir(follow_symlinks=False):
                    if entry.name not in _IGNORED_SOURCE_DIRECTORY_NAMES:
                        pending.append(path)
                    continue
                if entry.is_file(follow_symlinks=False):
                    if path.suffix not in _IGNORED_SOURCE_SUFFIXES:
                        files.append(path)
                    continue
                raise ValueError(f"installable package contains a non-regular path: {relative_path}")
    return sorted(files, key=lambda path: path.relative_to(package_root).as_posix())


def _update_fingerprint_frame(digest: _DigestWriter, payload: bytes) -> None:
    digest.update(len(payload).to_bytes(8, byteorder="big"))
    digest.update(payload)
