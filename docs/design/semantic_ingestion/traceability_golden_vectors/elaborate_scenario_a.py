"""Reference milestone-1 scenario elaborator using the production CTV codec."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueProfileBinding,
    decode_artifact,
    serialize_artifact,
)
from tests.fixtures.semantic_ingestion.scenario_fixture_authority import (
    build_generation_package,
    build_scenario_test_authority,
)


ROOT = Path(__file__).parents[4]
AUTHORITY = Path(__file__).with_name("ctv-binding-authority-v2.json")
FORMAT = "memorii-sia-scenario-c2-milestone-2"
PROFILE_ID = "semantic_ingestion_typed_value"
PROFILE_VERSION = 2
FIXTURE_SCHEMA = "TraceabilityGoldenTypedInputFixtureBody.v1"
CONTENT_SCHEMA = "memorii.sia.scenario-ingress-evidence.v1"
CONTENT_MEDIA_TYPE = "application/vnd.memorii.ctv+json;version=2"
CONTENT_PROFILE = "semantic_ingestion_typed_value"


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _lp(value: bytes) -> bytes:
    return len(value).to_bytes(8, "big") + value


def _content_digest(content: bytes) -> str:
    return sha(
        b"memorii:sia-canonical-content:v1\0"
        + _lp(CONTENT_SCHEMA.encode("utf-8"))
        + _lp(b"1")
        + _lp(CONTENT_MEDIA_TYPE.encode("utf-8"))
        + _lp(CONTENT_PROFILE.encode("utf-8"))
        + _lp(content)
    )


def _binding(authority: bytes) -> CanonicalTypedValueProfileBinding:
    source = json.loads(authority)
    profile = source["profile"]
    schemas = [
        item for item in source["schemas"] if item["coordinate"] == FIXTURE_SCHEMA
    ]
    if len(schemas) != 1 or profile != {
        "id": PROFILE_ID,
        "version": PROFILE_VERSION,
        "digest": profile.get("digest"),
        "preimage_base64": profile.get("preimage_base64"),
    }:
        raise ValueError("registered CTV fixture binding is unavailable")
    return CanonicalTypedValueProfileBinding(
        profile_id=profile["id"],
        profile_version=profile["version"],
        profile_digest=profile["digest"],
        schema_id=FIXTURE_SCHEMA,
        schema_version=1,
        binding_digest=schemas[0]["binding_digest"],
    )


def _tool_pins() -> dict[str, str]:
    paths = {
        "renderer": Path(__file__).with_name("validate_scenario_first.py"),
        "checker": Path(__file__).with_name("validate_scenario_first.py"),
        "ingress_runner": Path(__file__).with_name("run_scenario_ingress.py"),
        "extractor": ROOT
        / "memorii"
        / "memorii"
        / "core"
        / "memory_evolution"
        / "extraction.py",
        "provider_composition": ROOT
        / "memorii"
        / "memorii"
        / "core"
        / "provider"
        / "service.py",
    }
    return {name: sha(path.read_bytes()) for name, path in sorted(paths.items())}


def _raw_member(name: str, data: bytes, ordinal: int) -> dict[str, Any]:
    return {
        "coordinate": f"scenario-c2/m1/{ordinal:02d}/{name}",
        "kind": "raw_input",
        "name": name,
        "digest": sha(data),
        "bytes_base64": base64.b64encode(data).decode("ascii"),
        "dependencies": [],
    }


def _validate_run(
    run: dict[str, Any],
    *,
    scenario: bytes,
    design: bytes,
    registry: bytes,
    authority: bytes,
) -> None:
    required = {
        "format",
        "projection_policy",
        "projection_version",
        "extractor_identity",
        "composition_identity",
        "tool_pins",
        "oracle_spy_observation_count",
        "runs",
        "stable_evidence",
        "scenario_sha256",
        "design_sha256",
        "registry_sha256",
        "ctv_authority_sha256",
    }
    if set(run) != required or run["format"] != "memorii-sia-scenario-ingress-run-v2":
        raise ValueError("scenario run shape")
    if (
        run["projection_policy"] != "scenario_semantic_persisted_projection"
        or run["projection_version"] != 1
    ):
        raise ValueError("scenario run projection policy")
    if (
        run["scenario_sha256"] != sha(scenario)
        or run["design_sha256"] != sha(design)
        or run["registry_sha256"] != sha(registry)
        or run["ctv_authority_sha256"] != sha(authority)
    ):
        raise ValueError("scenario run raw pin")
    if run["tool_pins"] != _tool_pins() or run["oracle_spy_observation_count"] != len(
        run["runs"]
    ):
        raise ValueError("scenario run tool pin or oracle observation")
    if (
        not isinstance(run["runs"], list)
        or not run["runs"]
        or not isinstance(run["stable_evidence"], list)
    ):
        raise ValueError("scenario run evidence")
    for item in run["runs"]:
        if set(item) != {
            "rendered_source_id",
            "provider_event_id",
            "rendered_bytes_base64",
            "source_span_map",
            "projection_digest",
            "comparator_result",
        }:
            raise ValueError("scenario run item")
        rendered = base64.b64decode(item["rendered_bytes_base64"], validate=True)
        if item["source_span_map"] != [
            {
                "source_id": item["rendered_source_id"],
                "byte_start": 0,
                "byte_end": len(rendered),
            }
        ]:
            raise ValueError("scenario run span")
        if item["comparator_result"] not in {"match", "ambiguous", "abstain"}:
            raise ValueError("scenario comparator result")


def elaborate(
    scenario: bytes, run: bytes, design: bytes, registry: bytes, spool: Path
) -> dict[str, Any]:
    authority = AUTHORITY.read_bytes()
    run_document = json.loads(run)
    _validate_run(
        run_document,
        scenario=scenario,
        design=design,
        registry=registry,
        authority=authority,
    )
    binding = _binding(authority)
    evidence = {
        "scenario_sha256": sha(scenario),
        "run_sha256": sha(run),
        "tool_pins": run_document["tool_pins"],
        "runs": run_document["runs"],
        "stable_evidence": run_document["stable_evidence"],
    }
    content = canonical(evidence)
    body = {
        "fixture_id": "scenario-first-fixture-35",
        "owner": "acceptance_independent_vector_author",
        "target_artifact_kind": "golden_typed_input_fixture",
        "target_schema_id": CONTENT_SCHEMA,
        "target_schema_version": 1,
        "target_body_binding": binding.as_value(),
        "typed_input_value": {
            "content_schema_id": CONTENT_SCHEMA,
            "content_schema_version": 1,
            "media_type": CONTENT_MEDIA_TYPE,
            "canonical_profile_id": CONTENT_PROFILE,
            "content_bytes": content,
            "content_size": len(content),
            "content_digest": _content_digest(content),
        },
    }
    envelope = serialize_artifact(body, binding)
    artifact = decode_artifact(envelope, expected_binding=binding)
    raw = [
        ("scenario", scenario),
        ("public_ingress_run", run),
        ("design", design),
        ("registry", registry),
        ("ctv_binding_authority", authority),
        *[
            (f"tool_{name}", digest.encode("ascii"))
            for name, digest in sorted(_tool_pins().items())
        ],
    ]
    members = [
        _raw_member(name, data, index) for index, (name, data) in enumerate(raw, 1)
    ]
    members.append(
        {
            "coordinate": f"scenario-c2/m1/{len(members) + 1:02d}/fixture_35_golden_typed_input",
            "kind": "golden_typed_input_fixture",
            "name": "fixture_35",
            "schema_id": FIXTURE_SCHEMA,
            "schema_version": 1,
            "binding": binding.as_value(),
            "digest": artifact.artifact_digest,
            "bytes_base64": base64.b64encode(envelope).decode("ascii"),
            "dependencies": [member["coordinate"] for member in members],
        }
    )
    # The scenario closure is exercised with an isolated deterministic root;
    # it is never consulted by default application composition.
    test_authority = build_scenario_test_authority(
        design_bytes=design,
        registry_bytes=registry,
        authority_bytes=authority,
        group_id="semantic-ingestion-r03",
    )
    generation_manifest, generation_members = build_generation_package(
        built=test_authority, design_bytes=design, registry_bytes=registry
    )
    closure_members = [
        {
            "coordinate": coordinate,
            "kind": "registered_generation_member",
            "name": coordinate.rsplit("/", 2)[-2],
            "digest": sha(data),
            "bytes_base64": base64.b64encode(data).decode("ascii"),
            "dependencies": [],
        }
        for coordinate, data in sorted(generation_members.items())
    ]
    closure_members.append(
        {
            "coordinate": "scenario-c2/m2/generation_manifest",
            "kind": "approval_generation_manifest",
            "name": "G1",
            "digest": sha(generation_manifest),
            "bytes_base64": base64.b64encode(generation_manifest).decode("ascii"),
            "dependencies": [member["coordinate"] for member in closure_members],
        }
    )
    spool.write_bytes(canonical({"generation_members": closure_members}) + b"\n")
    return {
        "format": FORMAT,
        "milestone": 2,
        "profile": PROFILE_ID,
        "profile_version": PROFILE_VERSION,
        "spool_digest": sha(spool.read_bytes()),
        "members": members,
        "registered_closure": closure_members,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", type=Path)
    parser.add_argument("run", type=Path)
    parser.add_argument("design", type=Path)
    parser.add_argument("registry", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = elaborate(
        args.scenario.read_bytes(),
        args.run.read_bytes(),
        args.design.read_bytes(),
        args.registry.read_bytes(),
        args.output.with_suffix(".structural.spool"),
    )
    args.output.write_bytes(canonical(result) + b"\n")


if __name__ == "__main__":
    main()
