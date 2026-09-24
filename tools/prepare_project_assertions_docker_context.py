#!/usr/bin/env python3
"""Prepare signed project-assertions source bytes for a Docker build context.

Docker copies Windows working-tree bytes verbatim.  The installed
project-assertions profile deliberately fingerprints exact source and resource
bytes, so this tool converts only its declared text material from CRLF to LF
before an editable install.  It rejects every other carriage-return form,
unsafe coordinate, and digest mismatch instead of attempting to repair it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


_RESOURCE_DIRECTORY = Path("memorii/core/semantic_ingestion/resources")
_MANIFEST_NAME = "project_assertions.manifest.v1.json"
_MEMBER_NAMES = frozenset(
    {
        "project_assertions.component_fingerprints.v1.json",
        "project_assertions.egress_policy.v1.json",
        "project_assertions.output_schema.v1.json",
        "project_assertions.predicate_catalog.v1.json",
        "project_assertions.prompt.v1.json",
    }
)
_MODULE_PREFIX = "memorii.core.semantic_ingestion."
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class PreparationError(ValueError):
    """The build context cannot safely produce the signed profile bytes."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    return parser


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _strict_object(payload: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, PreparationError) as error:
        raise PreparationError(f"{label} is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise PreparationError(f"{label} must be a JSON object")
    return value


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PreparationError("duplicate JSON key")
        result[key] = value
    return result


def _normalized_text(path: Path, *, label: str) -> bytes:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise PreparationError(f"{label} is unavailable") from error
    if b"\r" in payload.replace(b"\r\n", b""):
        raise PreparationError(f"{label} contains a lone carriage return")
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PreparationError(f"{label} is not UTF-8") from error
    normalized = payload.replace(b"\r\n", b"\n")
    if normalized != payload:
        path.write_bytes(normalized)
    return normalized


def _resource_path(source_root: Path, name: str) -> Path:
    if name not in _MEMBER_NAMES and name != _MANIFEST_NAME:
        raise PreparationError(f"resource coordinate is not declared by the profile: {name}")
    return source_root / _RESOURCE_DIRECTORY / name


def _component_path(source_root: Path, module: object) -> Path:
    if not isinstance(module, str) or not module.startswith(_MODULE_PREFIX):
        raise PreparationError("component module coordinate is unsafe")
    suffix = module.removeprefix(_MODULE_PREFIX)
    if not suffix or any(not part.isidentifier() for part in suffix.split(".")):
        raise PreparationError("component module coordinate is unsafe")
    package_root = (source_root / "memorii").resolve()
    candidate = (package_root / "core" / "semantic_ingestion" / Path(*suffix.split("."))).with_suffix(".py")
    resolved = candidate.resolve()
    if package_root not in resolved.parents or resolved.suffix != ".py":
        raise PreparationError("component module coordinate is unsafe")
    return resolved


def prepare(source_root: Path) -> None:
    """Normalize and verify every exact byte sequence trusted by the profile."""

    root = source_root.resolve()
    manifest_path = _resource_path(root, _MANIFEST_NAME)
    manifest = _strict_object(_normalized_text(manifest_path, label=_MANIFEST_NAME), _MANIFEST_NAME)
    member_digests = manifest.get("member_digests")
    if not isinstance(member_digests, dict) or set(member_digests) != _MEMBER_NAMES:
        raise PreparationError("manifest member coordinates are invalid")
    for name, expected_digest in member_digests.items():
        if not isinstance(expected_digest, str) or _SHA256.fullmatch(expected_digest) is None:
            raise PreparationError(f"manifest digest is invalid: {name}")
        payload = _normalized_text(_resource_path(root, name), label=name)
        if _sha256(payload) != expected_digest:
            raise PreparationError(f"resource digest is invalid: {name}")

    fingerprints_name = "project_assertions.component_fingerprints.v1.json"
    fingerprints = _strict_object(_resource_path(root, fingerprints_name).read_bytes(), fingerprints_name)
    components = fingerprints.get("components")
    if not isinstance(components, list) or not components:
        raise PreparationError("component fingerprints are invalid")
    for component in components:
        if not isinstance(component, dict):
            raise PreparationError("component fingerprint is invalid")
        module = component.get("module")
        expected_digest = component.get("source_sha256")
        if not isinstance(module, str):
            raise PreparationError("component module coordinates are invalid")
        if not isinstance(expected_digest, str) or _SHA256.fullmatch(expected_digest) is None:
            raise PreparationError("component source digest is invalid")
        payload = _normalized_text(_component_path(root, module), label=f"component {module}")
        if _sha256(payload) != expected_digest:
            raise PreparationError(f"component source digest is invalid: {module}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        prepare(args.source_root)
    except PreparationError as error:
        print(f"project-assertions Docker context preparation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
