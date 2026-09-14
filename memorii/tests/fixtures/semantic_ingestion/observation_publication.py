"""Construction publications with the complete transitive schema role closure."""

import json
from dataclasses import replace

from memorii.core.memory_evolution.typed_value_artifact_reader import ProtectedTypedValueArtifactReaderLimits
from memorii.core.memory_evolution.typed_value_body_validation import ProtectedTypedValueBodyLimits
from tests.unit.core.memory_evolution import test_typed_value_artifact_integrity as registry_fixture


def observation_publication(tmp_path, monkeypatch, roots):
    schemas = set()

    def collect(schema):
        if schema in schemas:
            return
        schemas.add(schema)

        def visit(value):
            if isinstance(value, dict):
                if value.get("kind") == "model_ref":
                    collect(value["schema_id"])
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(json.loads((registry_fixture._ROOT / "schema" / schema / "1.json").read_text()))

    for schema in roots:
        collect(schema)
    publication_limits = registry_fixture._PUBLICATION_LIMITS
    monkeypatch.setattr(registry_fixture, "_PUBLICATION_LIMITS", replace(
        publication_limits,
        decoder_source_limits=replace(publication_limits.decoder_source_limits, maximum_files=len(schemas)),
        maximum_publication_manifest_bytes=2 * 1024 * 1024,
    ))
    registry_path = tmp_path
    registry_path.mkdir(parents=True, exist_ok=True)
    history = registry_fixture._publication(registry_path, tuple(sorted(schemas)))
    limits = ProtectedTypedValueArtifactReaderLimits(
        2 * 1024 * 1024, 64_000, 80, ProtectedTypedValueBodyLimits(2 * 1024 * 1024, 64_000, 80),
    )
    return history, limits
