"""Regenerate the checked-in profile-3 observation publication authority.

The decoder selections are intentionally read from the prior checked-in
manifest: they are the reviewed finite implementation closure.  The canonical
authoring library then re-reads every selected source, derives decoder and
registry declarations, and writes the two manifests atomically at the
artifact level.
"""

from __future__ import annotations

import json
from pathlib import Path

from memorii.core.memory_evolution.typed_value_declarations import (
    ProtectedDeclarationParseLimits,
    parse_typed_value_declaration,
)
from memorii.core.memory_evolution.typed_value_decoder_sources import (
    DecoderSourceSelection,
    ProtectedDecoderSourceManifestLimits,
)
from memorii.core.memory_evolution.typed_value_publication import (
    ProtectedTypedValuePublicationLimits,
)
from memorii.core.memory_evolution.typed_value_publication_authoring import (
    author_typed_value_publication_package,
)
from memorii.core.memory_evolution.typed_value_registry_compilation import (
    typed_value_declaration_role_descriptor,
)


def _source_root() -> Path:
    return Path(__file__).resolve().parents[1] / "memorii" / "core" / "memory_evolution" / "observation_registry_sources"


def _role_sources(root: Path) -> tuple[bytes, ...]:
    return tuple(
        path.read_bytes()
        for path in sorted(
            (
                path
                for path in root.rglob("*.json")
                if path.name not in {
                    "decoder-source-manifest.json",
                    "publication-manifest.json",
                    "registry.json",
                }
                and "decoder" not in path.relative_to(root).parts
            ),
            key=lambda path: path.relative_to(root).as_posix().encode("utf-8"),
        )
    )


def _selections(root: Path) -> tuple[DecoderSourceSelection, ...]:
    manifest = json.loads((root / "decoder-source-manifest.json").read_text(encoding="utf-8"))
    return tuple(
        DecoderSourceSelection(
            decoder_id=row["decoder_id"],
            source_file_id=row["source_file_id"],
            relative_path=row["relative_path"],
        )
        for row in manifest["files"]
    )


def generate(*, root: Path | None = None) -> None:
    source_root = _source_root() if root is None else root
    limits = ProtectedTypedValuePublicationLimits(
        ProtectedDeclarationParseLimits(2_000_000, 300_000, 64),
        ProtectedDecoderSourceManifestLimits(8_000_000, 300_000, 64, 10_000, 2_000_000),
        2_000_000,
    )
    package_root = source_root.parents[3]
    package = author_typed_value_publication_package(
        _role_sources(source_root),
        _selections(source_root),
        source_package_root=package_root,
        limits=limits,
    )
    for raw in package.raw_role_sources:
        descriptor = typed_value_declaration_role_descriptor(
            parse_typed_value_declaration(raw, limits=limits.declaration_limits)
        )
        destination = source_root / ("grammar.json" if descriptor == "grammar" else "registry.json" if descriptor == "registry" else f"{descriptor}.json")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
    (source_root / "decoder-source-manifest.json").write_bytes(package.raw_decoder_source_manifest)
    (source_root / "publication-manifest.json").write_bytes(package.raw_publication_manifest)


if __name__ == "__main__":
    generate()
