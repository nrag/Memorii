"""Fail-closed verifier for the registered CTV scenario package."""

from __future__ import annotations

import argparse
import base64
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueError,
    decode_artifact,
    decode_typed_value,
    serialize_artifact,
)

from elaborate_scenario_a import (
    AUTHORITY,
    CONTENT_MEDIA_TYPE,
    CONTENT_PROFILE,
    CONTENT_SCHEMA,
    FIXTURE_SCHEMA,
    FORMAT,
    PROFILE_ID,
    PROFILE_VERSION,
    _binding,
    _content_digest,
    _tool_pins,
    canonical,
    sha,
)
from tests.fixtures.semantic_ingestion.scenario_fixture_authority import (
    build_generation_package,
    build_scenario_test_authority,
)


ROOT = Path(__file__).parents[4]
RAW_NAMES = (
    "scenario",
    "public_ingress_run",
    "design",
    "registry",
    "ctv_binding_authority",
    "tool_checker",
    "tool_extractor",
    "tool_ingress_runner",
    "tool_provider_composition",
    "tool_renderer",
)


def _decode_base64(value: object, label: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError(label)
    try:
        return base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise ValueError(label) from exc


def _raw_members(document: dict[str, Any]) -> tuple[dict[str, bytes], dict[str, Any]]:
    members = document["members"]
    if not isinstance(members, list) or len(members) != len(RAW_NAMES) + 1:
        raise ValueError("member count")
    raw: dict[str, bytes] = {}
    coordinates: set[str] = set()
    for index, name in enumerate(RAW_NAMES, 1):
        row = members[index - 1]
        if set(row) != {
            "coordinate",
            "kind",
            "name",
            "digest",
            "bytes_base64",
            "dependencies",
        }:
            raise ValueError("raw member shape")
        if (
            row["coordinate"]
            != f"scenario-first-closure/governed-source-admission/{index:02d}/{name}"
            or row["kind"] != "raw_input"
            or row["name"] != name
            or row["dependencies"] != []
        ):
            raise ValueError("raw member identity")
        data = _decode_base64(row["bytes_base64"], "raw member bytes")
        if row["digest"] != sha(data) or row["coordinate"] in coordinates:
            raise ValueError("raw member digest")
        coordinates.add(row["coordinate"])
        raw[name] = data
    fixture = members[-1]
    if set(fixture) != {
        "coordinate",
        "kind",
        "name",
        "schema_id",
        "schema_version",
        "binding",
        "digest",
        "bytes_base64",
        "dependencies",
    }:
        raise ValueError("fixture member shape")
    if (
        fixture["coordinate"]
        != f"scenario-first-closure/governed-source-admission/{len(RAW_NAMES) + 1:02d}/fixture_35_golden_typed_input"
        or fixture["kind"] != "golden_typed_input_fixture"
        or fixture["name"] != "fixture_35"
    ):
        raise ValueError("fixture member identity")
    if fixture["dependencies"] != [member["coordinate"] for member in members[:-1]]:
        raise ValueError("fixture dependency closure")
    return raw, fixture


def _validate_run(run: dict[str, Any], raw: dict[str, bytes]) -> None:
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
        raise ValueError("run shape")
    if (
        run["projection_policy"] != "scenario_semantic_persisted_projection"
        or run["projection_version"] != 1
    ):
        raise ValueError("run projection policy")
    if (
        run["scenario_sha256"],
        run["design_sha256"],
        run["registry_sha256"],
        run["ctv_authority_sha256"],
    ) != (
        sha(raw["scenario"]),
        sha(raw["design"]),
        sha(raw["registry"]),
        sha(raw["ctv_binding_authority"]),
    ):
        raise ValueError("run raw pin")
    if run["tool_pins"] != _tool_pins() or run["oracle_spy_observation_count"] != len(
        run["runs"]
    ):
        raise ValueError("run tool pin or oracle count")
    if (
        not isinstance(run["runs"], list)
        or not isinstance(run["stable_evidence"], list)
        or len(run["runs"]) != len(run["stable_evidence"])
        or not run["runs"]
    ):
        raise ValueError("run evidence cardinality")
    for row, projection in zip(run["runs"], run["stable_evidence"], strict=True):
        if set(row) != {
            "rendered_source_id",
            "provider_event_id",
            "rendered_bytes_base64",
            "source_span_map",
            "projection_digest",
            "comparator_result",
        }:
            raise ValueError("run item shape")
        rendered = _decode_base64(row["rendered_bytes_base64"], "rendered bytes")
        if row["source_span_map"] != [
            {
                "source_id": row["rendered_source_id"],
                "byte_start": 0,
                "byte_end": len(rendered),
            }
        ]:
            raise ValueError("run span map")
        if row["projection_digest"] != sha(canonical(projection)) or row[
            "comparator_result"
        ] not in {"match", "ambiguous", "abstain"}:
            raise ValueError("run semantic evidence")


def validate(document: dict[str, Any], spool: bytes) -> None:
    if set(document) != {
        "format",
        "closure_version",
        "profile",
        "profile_version",
        "spool_digest",
        "members",
        "registered_closure",
    }:
        raise ValueError("manifest root")
    if (
        document["format"] != FORMAT
        or document["closure_version"] != 1
        or document["profile"] != PROFILE_ID
        or document["profile_version"] != PROFILE_VERSION
    ):
        raise ValueError("manifest identity")
    if document["spool_digest"] != sha(spool):
        raise ValueError("scenario closure spool")
    raw, fixture = _raw_members(document)
    if (
        raw["ctv_binding_authority"] != AUTHORITY.read_bytes()
        or raw["scenario"] == b""
        or raw["public_ingress_run"] == b""
    ):
        raise ValueError("raw authority or input")
    if (
        raw["design"]
        != (
            ROOT / "docs" / "design" / "semantic_ingestion_architecture.md"
        ).read_bytes()
        or raw["registry"]
        != (
            ROOT
            / "docs"
            / "design"
            / "semantic_ingestion"
            / "traceability_registry"
            / "registry-v1.json"
        ).read_bytes()
    ):
        raise ValueError("current design or registry pin")
    for name, digest in _tool_pins().items():
        if raw[f"tool_{name}"] != digest.encode("ascii"):
            raise ValueError("tool dependency pin")
    try:
        run = json.loads(raw["public_ingress_run"])
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("run bytes") from exc
    _validate_run(run, raw)
    binding = _binding(raw["ctv_binding_authority"])
    if (
        fixture["schema_id"] != FIXTURE_SCHEMA
        or fixture["schema_version"] != 1
        or fixture["binding"] != binding.as_value()
    ):
        raise ValueError("fixture binding")
    envelope_bytes = _decode_base64(fixture["bytes_base64"], "fixture bytes")
    try:
        artifact = decode_artifact(envelope_bytes, expected_binding=binding)
    except CanonicalTypedValueError as exc:
        raise ValueError("fixture CTV envelope") from exc
    if fixture["digest"] != artifact.artifact_digest:
        raise ValueError("fixture artifact digest")
    body = json.loads(artifact.canonical_value_bytes)
    try:
        from memorii.core.memory_evolution.ingestion_contracts import decode_typed_value

        body = decode_typed_value(artifact.canonical_value_bytes)
    except CanonicalTypedValueError as exc:
        raise ValueError("fixture body CTV") from exc
    if not isinstance(body, dict) or set(body) != {
        "fixture_id",
        "owner",
        "target_artifact_kind",
        "target_schema_id",
        "target_schema_version",
        "target_body_binding",
        "typed_input_value",
    }:
        raise ValueError("fixture body shape")
    if (
        body["fixture_id"] != "scenario-first-fixture-35"
        or body["owner"] != "acceptance_independent_vector_author"
        or body["target_artifact_kind"] != "golden_typed_input_fixture"
        or body["target_schema_id"] != CONTENT_SCHEMA
        or body["target_schema_version"] != 1
        or body["target_body_binding"] != binding.as_value()
    ):
        raise ValueError("fixture target binding")
    boundary = body["typed_input_value"]
    expected_boundary = {
        "content_schema_id",
        "content_schema_version",
        "media_type",
        "canonical_profile_id",
        "content_bytes",
        "content_size",
        "content_digest",
    }
    if (
        not isinstance(boundary, dict)
        or set(boundary) != expected_boundary
        or boundary["content_schema_id"] != CONTENT_SCHEMA
        or boundary["content_schema_version"] != 1
        or boundary["media_type"] != CONTENT_MEDIA_TYPE
        or boundary["canonical_profile_id"] != CONTENT_PROFILE
        or not isinstance(boundary["content_bytes"], bytes)
        or boundary["content_size"] != len(boundary["content_bytes"])
        or boundary["content_size"] < 1
        or boundary["content_digest"] != _content_digest(boundary["content_bytes"])
    ):
        raise ValueError("fixture canonical content boundary")
    try:
        evidence = json.loads(boundary["content_bytes"])
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("fixture evidence bytes") from exc
    expected_evidence = {
        "scenario_sha256": sha(raw["scenario"]),
        "run_sha256": sha(raw["public_ingress_run"]),
        "tool_pins": run["tool_pins"],
        "runs": run["runs"],
        "stable_evidence": run["stable_evidence"],
    }
    if (
        evidence != expected_evidence
        or canonical(evidence) != boundary["content_bytes"]
    ):
        raise ValueError("fixture evidence binding")
    if serialize_artifact(body, binding) != envelope_bytes:
        raise ValueError("fixture re-encode")
    closure = document["registered_closure"]
    if not isinstance(closure, list) or not closure:
        raise ValueError("registered closure missing")
    built = build_scenario_test_authority(
        design_bytes=raw["design"], registry_bytes=raw["registry"],
        authority_bytes=raw["ctv_binding_authority"], group_id="semantic-ingestion-normative-traceability-approval",
    )
    expected_manifest, expected_members = build_generation_package(
        built=built, design_bytes=raw["design"], registry_bytes=raw["registry"]
    )
    expected_rows = [
        (coordinate, data) for coordinate, data in sorted(expected_members.items())
    ] + [
        (
            "scenario-first-closure/writer-safe-preplanning/generation_manifest",
            expected_manifest,
        )
    ]
    if len(closure) != len(expected_rows):
        raise ValueError("registered closure member count")
    closure_bytes: dict[str, bytes] = {}
    prior: list[str] = []
    for row, (coordinate, expected) in zip(closure, expected_rows, strict=True):
        if not isinstance(row, dict) or set(row) != {
            "coordinate", "kind", "name", "digest", "bytes_base64", "dependencies"
        } or row["coordinate"] != coordinate:
            raise ValueError("registered closure member shape")
        value = _decode_base64(row["bytes_base64"], "registered closure bytes")
        if value != expected or row["digest"] != sha(value):
            raise ValueError("registered closure member bytes")
        expected_dependencies = prior if coordinate.endswith("/generation_manifest") else []
        if row["dependencies"] != expected_dependencies:
            raise ValueError("registered closure dependency order")
        prior.append(coordinate)
        closure_bytes[coordinate] = value
    if spool != canonical({"generation_members": closure}) + b"\n":
        raise ValueError("registered closure spool")
    # This artifact validator proves the checked-in scenario's independently
    # reconstructed bytes and mutation behavior. Public registered acceptance
    # is exercised separately with composition-owned current trust material;
    # the scenario's isolated deterministic root is not public authority.


def self_test(document: dict[str, Any], spool: bytes) -> None:
    validate(document, spool)
    mutations: list[tuple[str, dict[str, Any]]] = []
    for label in (
        "digest",
        "binding",
        "body",
        "target_binding",
        "evidence",
        "tool",
        "scenario",
        "run",
        "extra",
    ):
        candidate = deepcopy(document)
        fixture = candidate["members"][-1]
        if label == "digest":
            fixture["digest"] = "0" * 64
        elif label == "binding":
            fixture["binding"]["binding_digest"] = "0" * 64
        elif label == "body":
            fixture["bytes_base64"] = base64.b64encode(b"{}").decode("ascii")
        elif label == "tool":
            candidate["members"][5]["bytes_base64"] = base64.b64encode(
                b"0" * 64
            ).decode("ascii")
        elif label == "scenario":
            candidate["members"][0]["bytes_base64"] = base64.b64encode(b"{}").decode(
                "ascii"
            )
        elif label == "run":
            candidate["members"][1]["bytes_base64"] = base64.b64encode(b"{}").decode(
                "ascii"
            )
        elif label == "extra":
            candidate["extra"] = True
        else:
            envelope = _decode_base64(fixture["bytes_base64"], "fixture bytes")
            artifact = decode_artifact(envelope)
            body = decode_typed_value(artifact.canonical_value_bytes)
            if label == "target_binding":
                body["target_body_binding"]["binding_digest"] = "0" * 64
            else:
                body["typed_input_value"]["content_digest"] = "0" * 64
            replacement = serialize_artifact(body, artifact.binding)
            fixture["bytes_base64"] = base64.b64encode(replacement).decode("ascii")
            fixture["digest"] = decode_artifact(replacement).artifact_digest
        mutations.append((label, candidate))
    for label, candidate in mutations:
        try:
            validate(candidate, spool)
        except (ValueError, CanonicalTypedValueError):
            continue
        raise AssertionError(f"mutation accepted: {label}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("spool", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    document = json.loads(args.manifest.read_bytes())
    spool = args.spool.read_bytes()
    validate(document, spool)
    if args.self_test:
        self_test(document, spool)
    print(
        json.dumps(
            {"accepted": True, "members": len(document["members"])}, sort_keys=True
        )
    )


if __name__ == "__main__":
    main()
