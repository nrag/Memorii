"""Helpers for deterministic benchmark runs."""

from __future__ import annotations

import hashlib
import json
import os
import random
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, model_validator

from memorii.core.benchmark.models import BenchmarkRunConfig, BenchmarkScenarioFixture

SourceState: TypeAlias = Literal["clean", "dirty", "unversioned"]
_SOURCE_FINGERPRINT_DOMAIN = b"memorii-owned-source\0"
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


def build_source_tree_fingerprint(*, root: Path, relative_paths: list[str]) -> str:
    """Hash a complete, explicitly owned source tree with canonical ordering."""

    if root.is_symlink():
        raise ValueError(f"source fingerprint root cannot be a symlink: {root}")
    resolved_root = root.resolve(strict=True)
    if not resolved_root.is_dir():
        raise ValueError(f"source fingerprint root is not a directory: {root}")
    if not relative_paths:
        raise ValueError("source fingerprint requires at least one owned path")

    files: set[Path] = set()
    for relative_path in relative_paths:
        requested_path = Path(relative_path)
        if requested_path.is_absolute() or not requested_path.parts or ".." in requested_path.parts:
            raise ValueError(f"source fingerprint path escapes root: {relative_path}")
        candidate = resolved_root / requested_path
        if candidate.is_symlink():
            raise ValueError(f"source fingerprint path cannot be a symlink: {relative_path}")
        if candidate.is_dir():
            for path in candidate.rglob("*"):
                if path.is_symlink():
                    raise ValueError(
                        f"source fingerprint tree cannot contain symlinks: "
                        f"{path.relative_to(resolved_root).as_posix()}"
                    )
                if not path.is_file() or _is_ignored_source_path(path=path, root=resolved_root):
                    continue
                resolved_path = path.resolve(strict=True)
                if not resolved_path.is_relative_to(resolved_root):
                    raise ValueError(
                        f"source fingerprint file escapes root: "
                        f"{path.relative_to(resolved_root).as_posix()}"
                    )
                files.add(resolved_path)
        elif candidate.is_file():
            resolved_path = candidate.resolve(strict=True)
            if not resolved_path.is_relative_to(resolved_root):
                raise ValueError(f"source fingerprint path escapes root: {relative_path}")
            if not _is_ignored_source_path(path=resolved_path, root=resolved_root):
                files.add(resolved_path)
        else:
            raise ValueError(f"source fingerprint path does not exist: {relative_path}")
    if not files:
        raise ValueError("source fingerprint ownership contains no source files")

    digest = hashlib.sha256()
    digest.update(_SOURCE_FINGERPRINT_DOMAIN)
    for path in sorted(files, key=lambda item: item.relative_to(resolved_root).as_posix()):
        relative = path.relative_to(resolved_root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _is_ignored_source_path(*, path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return bool(_IGNORED_SOURCE_DIRECTORY_NAMES.intersection(relative.parts)) or (
        path.suffix in _IGNORED_SOURCE_SUFFIXES
    )
