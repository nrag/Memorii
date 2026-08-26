"""Single fail-closed resolver for frozen canonical-evidence authorities."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class LockResolutionError(RuntimeError):
    pass


ARTIFACT_NAMES = frozenset({
    "design", "verification_contract", "binding_map", "performance_schema",
    "standard_fixture_schema", "fixture_manifest", "production_sources",
    "event_schema", "receipt_schema", "runner", "recipe", "artifact_validator",
    "lock_resolver", "thin_fixture_grammar", "preimport_launcher", "evidence_manifest_schema", "result_lock_schema", "comparison_authority_schema", "comparison_schedule_authority", "comparison_result_binding_schema",
})


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class ResolvedLock:
    root: Path
    lock_path: Path
    lock_hash: str
    artifacts: dict[str, dict[str, str]]

    def path(self, name: str) -> Path:
        try:
            return self.root / self.artifacts[name]["path"]
        except KeyError as error:
            raise LockResolutionError(f"lock omits required authority: {name}") from error

    def load_json(self, name: str) -> dict[str, Any]:
        try:
            value = json.loads(self.path(name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise LockResolutionError(f"locked JSON authority is unreadable: {name}") from error
        if not isinstance(value, dict):
            raise LockResolutionError(f"locked JSON authority must be an object: {name}")
        return value


def resolve_lock(
    root: Path,
    *,
    expected_lock_hash: str | None = None,
    lock_path: Path | None = None,
) -> ResolvedLock:
    root = root.resolve()
    lock_path = (lock_path or root / "docs/design/semantic_ingestion_canonical_evidence/candidate-lock-v1.json").resolve()
    try:
        lock_hash = sha256(lock_path)
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LockResolutionError("candidate lock is unreadable") from error
    if expected_lock_hash is not None and lock_hash != expected_lock_hash:
        raise LockResolutionError("candidate lock hash mismatch")
    if not isinstance(lock, dict) or lock.get("immutable_path") != "docs/design/semantic_ingestion_canonical_evidence/candidate-lock-v1.json":
        raise LockResolutionError("candidate lock identity is invalid")
    artifacts = lock.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != ARTIFACT_NAMES:
        raise LockResolutionError("candidate lock authority set is incomplete")
    normalized: dict[str, dict[str, str]] = {}
    for name, item in artifacts.items():
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise LockResolutionError(f"locked authority shape is invalid: {name}")
        relative, digest = item["path"], item["sha256"]
        if not isinstance(relative, str) or not isinstance(digest, str) or len(digest) != 64:
            raise LockResolutionError(f"locked authority identity is invalid: {name}")
        target = (root / relative).resolve()
        if root not in target.parents or not target.is_file() or sha256(target) != digest:
            raise LockResolutionError(f"locked authority is missing, stale, or substituted: {name}")
        normalized[name] = {"path": relative, "sha256": digest}
    return ResolvedLock(root=root, lock_path=lock_path, lock_hash=lock_hash, artifacts=normalized)


def capture_ready_source_frames(lock: ResolvedLock) -> dict[str, dict[str, str]]:
    """Return the canonical source-frame inventory only when every frame is real."""
    manifest = lock.load_json("production_sources")
    if manifest.get("capture_status") != "capture_ready":
        raise LockResolutionError("capture-ready production source manifest required")
    if set(manifest) != {"schema", "capture_status", "sources", "source_frames", "capture_ready_transition"}:
        raise LockResolutionError("production source manifest shape is invalid")
    transition = manifest["capture_ready_transition"]
    sources = manifest["sources"]
    frames = manifest["source_frames"]
    if not isinstance(transition, dict) or set(transition) != {"required_symbols", "required_paths", "rule"}:
        raise LockResolutionError("capture-ready transition shape is invalid")
    symbols, paths = transition["required_symbols"], transition["required_paths"]
    if not isinstance(symbols, list) or not isinstance(paths, list) or not symbols or not paths or len(symbols) != len(set(symbols)) or len(paths) != len(set(paths)):
        raise LockResolutionError("capture-ready source inventory cardinality is invalid")
    if not isinstance(sources, list) or not isinstance(frames, list) or len(sources) != len(paths) or len(frames) != len(symbols):
        raise LockResolutionError("capture-ready source inventory cardinality is invalid")
    digest = re.compile(r"^[0-9a-f]{64}$")
    source_by_path: dict[str, str] = {}
    for source in sources:
        if not isinstance(source, dict) or set(source) != {"path", "sha256"}:
            raise LockResolutionError("production source manifest shape is invalid")
        path, source_sha = source.get("path"), source.get("sha256")
        target = (lock.root / path).resolve() if isinstance(path, str) else lock.root
        if not isinstance(path, str) or not isinstance(source_sha, str) or not digest.fullmatch(source_sha) or path in source_by_path or lock.root not in target.parents or not target.is_file() or sha256(target) != source_sha:
            raise LockResolutionError("capture-ready production source is missing, duplicated, or substituted")
        source_by_path[path] = source_sha
    if set(source_by_path) != set(paths):
        raise LockResolutionError("capture-ready production source paths are incomplete")
    frame_by_symbol: dict[str, dict[str, str]] = {}
    for frame in frames:
        if not isinstance(frame, dict) or set(frame) != {"symbol", "path", "sha256"}:
            raise LockResolutionError("source-frame inventory shape is invalid")
        symbol, path, frame_sha = frame.get("symbol"), frame.get("path"), frame.get("sha256")
        if not isinstance(symbol, str) or not isinstance(path, str) or not isinstance(frame_sha, str) or not digest.fullmatch(frame_sha) or symbol in frame_by_symbol or source_by_path.get(path) != frame_sha:
            raise LockResolutionError("source-frame inventory has a duplicate, sentinel, or wrong owner")
        frame_by_symbol[symbol] = {"path": path, "sha256": frame_sha}
    if set(frame_by_symbol) != set(symbols) or {frame["path"] for frame in frame_by_symbol.values()} != set(source_by_path):
        raise LockResolutionError("source-frame inventory is incomplete or maps every symbol to one source")
    bindings = lock.load_json("binding_map").get("production_entrypoint_bindings")
    if not isinstance(bindings, list) or not bindings or not isinstance(bindings[0], dict) or bindings[0].get("requirement") != "public_matrix":
        raise LockResolutionError("production binding map is invalid")
    bound_frames = bindings[0].get("source_frame_map")
    if not isinstance(bound_frames, dict) or bound_frames != frame_by_symbol:
        raise LockResolutionError("source-frame inventory does not equal the canonical production binding map")
    return frame_by_symbol
