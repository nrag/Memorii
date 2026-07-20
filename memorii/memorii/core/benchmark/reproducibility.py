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

from memorii.core.benchmark.models import BenchmarkRunConfig, BenchmarkScenarioFixture

SourceState: TypeAlias = Literal["clean", "dirty", "unversioned"]


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

    configured = os.environ.get("MEMORII_SOURCE_REVISION")
    if configured is not None:
        revision = configured.strip()
        if not revision or revision != configured:
            raise ValueError("MEMORII_SOURCE_REVISION must be non-empty and normalized")
        if revision == "local-source-tree" and not dry_run:
            raise ValueError("live benchmark reports require a real source revision")
        return revision

    revision = _git_head_revision(root)
    if revision is not None:
        return revision
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
    """Hash an explicitly owned set of source files and directories."""

    resolved_root = root.resolve()
    files: set[Path] = set()
    for relative_path in relative_paths:
        candidate = (resolved_root / relative_path).resolve()
        if not candidate.is_relative_to(resolved_root):
            raise ValueError(f"source fingerprint path escapes root: {relative_path}")
        if candidate.is_dir():
            files.update(
                path
                for path in candidate.rglob("*")
                if path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix in {".json", ".py", ".toml", ".yaml", ".yml"}
            )
        elif candidate.is_file():
            files.add(candidate)
        else:
            raise ValueError(f"source fingerprint path does not exist: {relative_path}")
    digest = hashlib.sha256()
    for path in sorted(files):
        relative = path.relative_to(resolved_root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
