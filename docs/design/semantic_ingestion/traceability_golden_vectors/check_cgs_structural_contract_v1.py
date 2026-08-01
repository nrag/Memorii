"""Hermetic checker for the CGS structural-contract design artifacts."""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

EXPECTED = {
    "design": "70ace2b99c4db79911f45555f72cde43278ccaac69c1fc11530e2d474f1fa26c",
    "registry": "8e6395e2657eb1a51e5eef7d9b88b5d43b974a58f7f786ed135f6758262bfec1",
    "ledger": "085921e6c4e995f0d6259c9f6f6eabeec3f1455bba344105ef0e16d24eb81671",
    "matrix": "a3375bd0d8d01cf7a7c9d7d16d90945d792d932eca7161097f6ee5ba44d3f604",
    "prototype": "b655f474e4918d64447251e40b9a3af53daca0efd2e2cb6baa76890243bae5ed",
    "vector": "7af8aa57cf1b81f243883077fdde27064a638e95bf366cfd1cfd16979340c3ab",
}
WORKPLAN_PATH = Path(
    "docs/work/semantic_ingestion/"
    "m0-canonical-genesis-structural-contract-correction-2026-07-30/"
    "design.plan.md"
)
BODY_BINDING = {
    "profile_id": "semantic_ingestion_typed_value",
    "profile_version": 2,
    "profile_digest": "9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f",
    "schema_id": "NormativeTraceabilityStructuralManifestBody.v1",
    "schema_version": 1,
    "binding_digest": "133ba5b492880d5b773eb75f5a81de0bdf0c09e85cce20d17d7aa076cee7b79b",
}
ASSERTION_ROOT_BINDING = {
    "profile_id": "semantic_ingestion_typed_value",
    "profile_version": 2,
    "profile_digest": "9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f",
    "schema_id": "TraceabilityRegistryRoot.assertion_templates.v1",
    "schema_version": 1,
    "binding_digest": "bcec42cc6a2f198fd8a35461f612ee5ca373af14b6e74d023e98cc7cbe70acb6",
}
OUTER_ENVELOPE_BINDING = {
    "profile_id": "semantic_ingestion_typed_value",
    "profile_version": 2,
    "profile_digest": "9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f",
    "schema_id": "CanonicalEncodedArtifact.v1",
    "schema_version": 1,
    "binding_digest": "39222b18e67ffe8f679943676a46a464c804bb2ef9d0e3fd28d27a590fe3fde1",
}
HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
REQUIRED_CASE_KEYS = {
    "requirement_id",
    "case_id",
    "mutation_or_variant",
    "boundary",
    "evidence",
    "expected_verdict_reason",
    "postcondition",
}
REQUIRED_LIFECYCLE_ROOT_CASES = {
    "lifecycle-root-genesis-authority-substitution",
    "lifecycle-root-genesis-channel-substitution",
    "lifecycle-root-genesis-anchor-id-substitution",
    "lifecycle-root-genesis-anchor-digest-substitution",
    "lifecycle-root-genesis-issuer-substitution",
    "lifecycle-root-genesis-key-substitution",
    "lifecycle-root-genesis-profile-substitution",
    "lifecycle-root-genesis-purpose-substitution",
    "lifecycle-root-genesis-not-before-substitution",
    "lifecycle-root-genesis-not-after-substitution",
    "lifecycle-root-genesis-mixed-union-fields",
    "lifecycle-root-sequence-one-successor",
    "lifecycle-root-successor-genesis-downgrade",
    "lifecycle-root-successor-authority-substitution",
    "lifecycle-root-successor-issuer-substitution",
    "lifecycle-root-successor-key-substitution",
    "lifecycle-root-successor-profile-substitution",
    "lifecycle-root-successor-purpose-substitution",
    "lifecycle-root-successor-not-before-substitution",
    "lifecycle-root-successor-not-after-substitution",
    "lifecycle-root-genesis-issued-at-not-before",
    "lifecycle-root-genesis-issued-at-not-after",
    "lifecycle-root-genesis-issued-before-not-before",
    "lifecycle-root-genesis-issued-after-not-after",
    "lifecycle-root-successor-issued-at-not-before",
    "lifecycle-root-successor-issued-at-not-after",
    "lifecycle-root-successor-issued-before-not-before",
    "lifecycle-root-successor-issued-after-not-after",
    "lifecycle-root-successor-issuer-malformed",
    "lifecycle-root-successor-key-malformed",
    "lifecycle-root-successor-profile-malformed",
    "lifecycle-root-successor-interval-order-malformed",
    "lifecycle-root-history-issuer-malformed",
    "lifecycle-root-history-key-malformed",
    "lifecycle-root-history-profile-malformed",
    "lifecycle-root-history-interval-order-malformed",
    "lifecycle-root-rp-owner-cross-substitution",
    "lifecycle-root-ba-owner-cross-substitution",
    "lifecycle-root-rr-owner-cross-substitution",
    "lifecycle-root-record-owner-cross-substitution",
    "lifecycle-root-envelope-preimage-mismatch",
    "lifecycle-root-successor-self-root-reference",
    "lifecycle-root-successor-self-record-reference",
    "lifecycle-root-successor-forward-root-reference",
    "lifecycle-root-successor-forward-record-reference",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reject(command: list[str], label: str) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode == 0:
        raise AssertionError(f"mutation accepted: {label}")
    print(f"rejected mutation: {label}: {result.stderr.strip() or result.stdout.strip()}")


def canonical_json_bytes(value: Any) -> bytes:
    if value is None:
        return b"null"
    if value is True:
        return b"true"
    if value is False:
        return b"false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value).encode("ascii")
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    if isinstance(value, list):
        return b"[" + b",".join(canonical_json_bytes(item) for item in value) + b"]"
    if isinstance(value, dict):
        keys = sorted(value, key=lambda item: canonical_json_bytes(item))
        return (
            b"{"
            + b",".join(
                canonical_json_bytes(key) + b":" + canonical_json_bytes(value[key])
                for key in keys
            )
            + b"}"
        )
    raise TypeError(type(value).__name__)


def encode_typed_value(value: Any) -> bytes:
    if value is None or isinstance(value, (bool, str)):
        return canonical_json_bytes(value)
    if isinstance(value, int):
        return canonical_json_bytes({"$type": "integer", "value": str(value)})
    if isinstance(value, bytes):
        return canonical_json_bytes(
            {"$type": "bytes", "value": base64.b64encode(value).decode("ascii")}
        )
    if isinstance(value, tuple):
        return canonical_json_bytes(
            {
                "$type": "tuple",
                "items": [json.loads(encode_typed_value(item)) for item in value],
            }
        )
    if isinstance(value, list):
        return canonical_json_bytes(
            {
                "$type": "list",
                "items": [json.loads(encode_typed_value(item)) for item in value],
            }
        )
    if isinstance(value, dict):
        entries = []
        for key in sorted(value, key=lambda item: canonical_json_bytes(item)):
            entries.append([key, json.loads(encode_typed_value(value[key]))])
        return canonical_json_bytes({"$type": "map", "entries": entries})
    raise TypeError(type(value).__name__)


def decode_typed_value_json(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if not isinstance(value, dict) or not isinstance(value.get("$type"), str):
        raise ValueError("invalid typed value")
    tag = value["$type"]
    if tag == "integer":
        return int(value["value"])
    if tag == "bytes":
        return base64.b64decode(value["value"], validate=True)
    if tag == "tuple":
        return tuple(decode_typed_value_json(item) for item in value["items"])
    if tag == "list":
        return [decode_typed_value_json(item) for item in value["items"]]
    if tag == "map":
        result: dict[str, Any] = {}
        for key, item in value["entries"]:
            result[key] = decode_typed_value_json(item)
        return result
    raise ValueError(f"unsupported tag: {tag}")


def decode_typed_value_bytes(raw: bytes) -> Any:
    value = decode_typed_value_json(json.loads(raw))
    if encode_typed_value(value) != raw:
        raise ValueError("typed value bytes are not canonical")
    return value


def require_binding_value(
    value: Any, expected: dict[str, Any] | None, label: str
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "profile_id",
        "profile_version",
        "profile_digest",
        "schema_id",
        "schema_version",
        "binding_digest",
    }:
        raise ValueError(f"{label} shape invalid")
    if (
        not isinstance(value["profile_id"], str)
        or not isinstance(value["schema_id"], str)
        or isinstance(value["profile_version"], bool)
        or not isinstance(value["profile_version"], int)
        or value["profile_version"] < 1
        or isinstance(value["schema_version"], bool)
        or not isinstance(value["schema_version"], int)
        or value["schema_version"] < 1
        or not isinstance(value["profile_digest"], str)
        or not HEX_64.fullmatch(value["profile_digest"])
        or not isinstance(value["binding_digest"], str)
        or not HEX_64.fullmatch(value["binding_digest"])
    ):
        raise ValueError(f"{label} fields invalid")
    if expected is not None and value != expected:
        raise ValueError(f"{label} mismatch")
    return value


def validate_artifact_value(
    value: Any, artifact_domain: bytes, expected_inner_binding: dict[str, Any]
) -> tuple[dict[str, Any], bytes, Any]:
    if not isinstance(value, dict) or set(value) != {
        "binding",
        "canonical_value_bytes",
        "canonical_value_digest",
        "artifact_digest",
    }:
        raise ValueError("artifact value shape invalid")
    binding = require_binding_value(
        value["binding"], expected_inner_binding, "inner artifact binding"
    )
    if not isinstance(value["canonical_value_bytes"], bytes):
        raise ValueError("artifact canonical_value_bytes invalid")
    if not isinstance(value["canonical_value_digest"], str) or not HEX_64.fullmatch(
        value["canonical_value_digest"]
    ):
        raise ValueError("artifact canonical_value_digest invalid")
    if not isinstance(value["artifact_digest"], str) or not HEX_64.fullmatch(
        value["artifact_digest"]
    ):
        raise ValueError("artifact artifact_digest invalid")
    expected_value_digest = hashlib.sha256(value["canonical_value_bytes"]).hexdigest()
    expected_artifact_digest = artifact_digest(
        artifact_domain, binding, value["canonical_value_bytes"]
    )
    if value["canonical_value_digest"] != expected_value_digest:
        raise ValueError("artifact canonical_value_digest mismatch")
    if value["artifact_digest"] != expected_artifact_digest:
        raise ValueError("artifact artifact_digest mismatch")
    inner_value = decode_typed_value_bytes(value["canonical_value_bytes"])
    return binding, value["canonical_value_bytes"], inner_value


def decode_artifact_bytes(
    raw: bytes, artifact_domain: bytes, expected_inner_binding: dict[str, Any]
) -> tuple[dict[str, Any], bytes, Any]:
    value = decode_typed_value_bytes(raw)
    return validate_artifact_value(value, artifact_domain, expected_inner_binding)


def require_domain_bytes(ledger: dict[str, Any], domain_id: str) -> bytes:
    value = ledger["digest_domains"][domain_id]["domain_ascii_hex"]
    if not isinstance(value, str) or len(value) % 2 or not re.fullmatch(
        r"[0-9a-f]+", value
    ):
        raise ValueError(f"invalid domain hex for {domain_id}")
    return bytes.fromhex(value)


def digest_raw(domain: bytes, payload: bytes) -> str:
    return hashlib.sha256(domain + payload).hexdigest()


def digest_ctv(domain: bytes, value: Any) -> str:
    payload = encode_typed_value(value)
    return hashlib.sha256(domain + len(payload).to_bytes(8, "big") + payload).hexdigest()


def length_prefixed(*parts: bytes) -> bytes:
    return b"".join(len(part).to_bytes(8, "big") + part for part in parts)


def artifact_digest(
    domain: bytes, binding: dict[str, Any], canonical_value_bytes: bytes
) -> str:
    return hashlib.sha256(
        length_prefixed(
            domain,
            binding["profile_id"].encode("utf-8"),
            str(binding["profile_version"]).encode("ascii"),
            binding["profile_digest"].encode("ascii"),
            binding["schema_id"].encode("utf-8"),
            str(binding["schema_version"]).encode("ascii"),
            binding["binding_digest"].encode("ascii"),
            canonical_value_bytes,
        )
    ).hexdigest()


def artifact_payload(
    binding: dict[str, Any], value: Any, domain: bytes
) -> tuple[dict[str, Any], bytes]:
    body_bytes = encode_typed_value(value)
    canonical_value_digest = hashlib.sha256(body_bytes).hexdigest()
    envelope_digest = artifact_digest(domain, binding, body_bytes)
    return (
        {
            "binding": dict(binding),
            "canonical_value_bytes": body_bytes,
            "canonical_value_digest": canonical_value_digest,
            "artifact_digest": envelope_digest,
        },
        encode_typed_value(
            {
                "binding": dict(binding),
                "canonical_value_bytes": body_bytes,
                "canonical_value_digest": canonical_value_digest,
                "artifact_digest": envelope_digest,
            }
        ),
    )


def freeze(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(freeze(item) for item in value)
    if isinstance(value, dict):
        return {key: freeze(item) for key, item in value.items()}
    return value


def headings(design: bytes) -> tuple[dict[str, object], ...]:
    result: list[dict[str, object]] = []
    for ordinal, match in enumerate(re.finditer(br"^(#{1,6}) ([^\n]+)$", design, re.M), 1):
        result.append(
            {
                "ordinal": ordinal,
                "level": len(match.group(1)),
                "title": match.group(2).decode("utf-8"),
                "byte_offset": match.start(),
            }
        )
    return tuple(result)


def parse_table(design: Path) -> list[tuple[int, str, str]]:
    text = design.read_text(encoding="utf-8")
    start = text.index("| # | Body field |")
    lines = text[start:].splitlines()[2:]
    rows: list[tuple[int, str, str]] = []
    for line in lines:
        if not line.startswith("| "):
            break
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        rows.append((int(cells[0]), cells[1].strip("`"), cells[2]))
    return rows


def replace_ledger_pins(
    text: str, raw_sha: str, derived_digest: str, coordinate: str
) -> str:
    text = re.sub(
        r"The frozen raw ledger SHA-256 is\s+`[0-9a-f]{64}`",
        f"The frozen raw ledger SHA-256 is\n`{raw_sha}`",
        text,
        count=1,
    )
    text = re.sub(
        r"The current domain-derived `derivation_ledger_digest` is\s+`[0-9a-f]{64}`",
        "The current domain-derived `derivation_ledger_digest` is\n"
        f"`{derived_digest}`",
        text,
        count=1,
    )
    text = re.sub(
        r"The current `derivation_ledger_coordinate` is\s+`[^`]+`",
        f"The current `derivation_ledger_coordinate` is\n`{coordinate}`",
        text,
        count=1,
    )
    text = re.sub(
        r"raw ledger SHA-256\s+`[0-9a-f]{64}`",
        f"raw ledger SHA-256\n  `{raw_sha}`",
        text,
        count=1,
    )
    text = re.sub(
        r"domain-derived `derivation_ledger_digest`\s+`[0-9a-f]{64}`",
        "domain-derived `derivation_ledger_digest`\n"
        f"  `{derived_digest}`",
        text,
        count=1,
    )
    text = re.sub(
        r"`derivation_ledger_coordinate`\s+`[^`]+`",
        f"`derivation_ledger_coordinate`\n  `{coordinate}`",
        text,
        count=1,
    )
    return text


def assert_no_literal_backslash_zero(path: Path) -> None:
    if "\\\\0" in path.read_text(encoding="utf-8"):
        raise ValueError(f"literal backslash-zero remains in {path}")


def expected_body(registry: dict[str, Any], ledger: dict[str, Any], design: bytes) -> dict[str, Any]:
    outer_envelope_domain = require_domain_bytes(ledger, "outer_envelope")
    assertion_root_value = {"items": freeze(registry["assertion_templates"])}
    assertion_registry_artifact, _ = artifact_payload(
        ASSERTION_ROOT_BINDING, assertion_root_value, outer_envelope_domain
    )
    return {
        "grammar_revision": ledger["grammar_revision"],
        "design_document_digest": digest_raw(
            require_domain_bytes(ledger, "raw_design"), design
        ),
        "registry_source_identity": digest_raw(
            require_domain_bytes(ledger, "raw_registry"),
            canonical_json_bytes(json.loads(json.dumps(registry))),
        ),
        "derivation_ledger_schema_id": ledger["schema_id"],
        "derivation_ledger_schema_version": ledger["schema_version"],
        "derivation_ledger_digest": hashlib.sha256(
            require_domain_bytes(ledger, "ledger")
            + len(canonical_json_bytes(json.loads(json.dumps(ledger))) + b"\n").to_bytes(8, "big")
            + (canonical_json_bytes(json.loads(json.dumps(ledger))) + b"\n")
        ).hexdigest(),
        "derivation_ledger_coordinate": None,
        "artifact_dag": freeze(registry["artifact_dag"]),
        "artifact_dag_digest": digest_ctv(
            require_domain_bytes(ledger, "artifact_dag_root"),
            freeze(registry["artifact_dag"]),
        ),
        "canonical_profile_binding": dict(BODY_BINDING),
        "requirement_binding_registry_digest": digest_ctv(
            require_domain_bytes(ledger, "requirement_binding_root"),
            freeze(registry["requirement_bindings"]),
        ),
        "section_defaults": freeze(registry["heading_defaults"]),
        "section_default_registry_digest": digest_ctv(
            require_domain_bytes(ledger, "section_default_root"),
            freeze(registry["heading_defaults"]),
        ),
        "structural_mapping_rules": freeze(registry["structural_rules"]),
        "structural_mapping_rule_registry_digest": digest_ctv(
            require_domain_bytes(ledger, "structural_mapping_rule_root"),
            freeze(registry["structural_rules"]),
        ),
        "assertion_registry_artifact": assertion_registry_artifact,
        "assertion_registry_digest": assertion_registry_artifact["artifact_digest"],
        "test_evidence_groups": freeze(registry["test_evidence_groups"]),
        "test_evidence_group_registry_digest": digest_ctv(
            require_domain_bytes(ledger, "test_evidence_group_root"),
            freeze(registry["test_evidence_groups"]),
        ),
        "report_schemas": freeze(registry["report_schemas"]),
        "report_schema_registry_digest": digest_ctv(
            require_domain_bytes(ledger, "report_schema_root"),
            freeze(registry["report_schemas"]),
        ),
        "runner_environment_profiles": freeze(registry["runner_environment_profiles"]),
        "runner_environment_profile_registry_digest": digest_ctv(
            require_domain_bytes(ledger, "runner_environment_profile_root"),
            freeze(registry["runner_environment_profiles"]),
        ),
        "units": headings(design),
        "entries": tuple(),
        "overrides": freeze(registry["overrides"]),
        "override_registry_digest": digest_ctv(
            require_domain_bytes(ledger, "override_root"),
            freeze(registry["overrides"]),
        ),
        "explicit_anchor_bindings": tuple(
            (item["anchor"], (item["heading_path"],))
            for item in registry["anchor_bindings"]
        ),
        "anchor_binding_registry_digest": digest_ctv(
            require_domain_bytes(ledger, "anchor_binding_root"),
            tuple((item["anchor"], (item["heading_path"],)) for item in registry["anchor_bindings"]),
        ),
    }


def validate(
    design: Path,
    registry: Path,
    ledger_path: Path,
    matrix_path: Path,
    prototype: Path,
    vector: Path,
    workplan_path: Path,
    enforce_hashes: bool,
) -> None:
    paths = {
        "design": design,
        "registry": registry,
        "ledger": ledger_path,
        "matrix": matrix_path,
        "prototype": prototype,
        "vector": vector,
    }
    if enforce_hashes:
        for label, path in paths.items():
            if sha(path) != EXPECTED[label]:
                raise ValueError(f"{label} hash mismatch")

    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    registry_value = json.loads(registry.read_text(encoding="utf-8"))
    vector_value = json.loads(vector.read_text(encoding="utf-8"))
    design_bytes = design.read_bytes()
    ledger_bytes = ledger_path.read_bytes()

    fields = ledger["fields"]
    if [field["ordinal"] for field in fields] != list(range(1, 30)):
        raise ValueError("ledger ordinals")
    if len({field["name"] for field in fields}) != 29:
        raise ValueError("ledger names")
    for field in fields:
        domain_id = field["digest_domain"]
        if domain_id is None:
            continue
        if domain_id not in ledger["digest_domains"]:
            raise ValueError(f"unknown digest domain: {field['name']}")
        if "\\\\0" in str(domain_id):
            raise ValueError("field references literal backslash-zero")
    for domain_id, domain in ledger["digest_domains"].items():
        hex_value = domain["domain_ascii_hex"]
        if not re.fullmatch(r"[0-9a-f]+", hex_value):
            raise ValueError(f"domain hex invalid: {domain_id}")
        if domain_id != "outer_envelope" and not hex_value.endswith("00"):
            raise ValueError(f"domain missing NUL terminator: {domain_id}")

    table = parse_table(design)
    expected_table = [(field["ordinal"], field["name"]) for field in fields]
    if [(ordinal, name) for ordinal, name, _ in table] != expected_table:
        raise ValueError("architecture table ordinal/name mismatch")
    refs = {ordinal: source for ordinal, _, source in table}
    if "outer artifact digest" not in refs[17]:
        raise ValueError("architecture table envelope distinction")
    if "exact domain ID" not in refs[29]:
        raise ValueError("architecture table exact-domain pin missing")
    design_text = design.read_text(encoding="utf-8")
    raw_ledger_match = re.search(
        r"The frozen raw ledger SHA-256 is\s+`([0-9a-f]{64})`", design_text
    )
    derived_ledger_match = re.search(
        r"The current domain-derived `derivation_ledger_digest` is\s+`([0-9a-f]{64})`",
        design_text,
    )
    coordinate_match = re.search(
        r"The current `derivation_ledger_coordinate` is\s+`([^`]+)`", design_text
    )
    matrix_match = re.search(r"`cgs_verification_attack_matrix-v1\.json`, raw SHA-256\s+`([0-9a-f]{64})`", design_text)
    expected_raw_ledger_sha = sha(ledger_path)
    expected_derived_ledger_digest = hashlib.sha256(
        require_domain_bytes(ledger, "ledger")
        + len(ledger_bytes).to_bytes(8, "big")
        + ledger_bytes
    ).hexdigest()
    expected_derived_coordinate = (
        f"structural_manifest_derivation_ledger/{ledger['schema_id']}/"
        f"{ledger['schema_version']}/{expected_derived_ledger_digest}"
    )
    if raw_ledger_match is None or raw_ledger_match.group(1) != expected_raw_ledger_sha:
        raise ValueError("architecture raw ledger pin mismatch")
    if (
        derived_ledger_match is None
        or derived_ledger_match.group(1) != expected_derived_ledger_digest
    ):
        raise ValueError("architecture derived ledger digest pin mismatch")
    if coordinate_match is None or coordinate_match.group(1) != expected_derived_coordinate:
        raise ValueError("architecture derived ledger coordinate pin mismatch")
    if matrix_match is None or matrix_match.group(1) != sha(matrix_path):
        raise ValueError("architecture matrix pin mismatch")

    workplan = workplan_path.read_text(encoding="utf-8")
    if "25-field" in workplan or "the 25-field structural ledger" in workplan:
        raise ValueError("workplan still references 25-field ledger")
    if "29-field" not in workplan:
        raise ValueError("workplan missing 29-field evidence")
    workplan_raw_match = re.search(r"raw ledger SHA-256\s+`([0-9a-f]{64})`", workplan)
    workplan_derived_match = re.search(
        r"domain-derived `derivation_ledger_digest`\s+`([0-9a-f]{64})`", workplan
    )
    workplan_coordinate_match = re.search(
        r"`derivation_ledger_coordinate`\s+`([^`]+)`", workplan
    )
    if workplan_raw_match is None or workplan_raw_match.group(1) != expected_raw_ledger_sha:
        raise ValueError("workplan raw ledger pin mismatch")
    if (
        workplan_derived_match is None
        or workplan_derived_match.group(1) != expected_derived_ledger_digest
    ):
        raise ValueError("workplan derived ledger pin mismatch")
    if (
        workplan_coordinate_match is None
        or workplan_coordinate_match.group(1) != expected_derived_coordinate
    ):
        raise ValueError("workplan derived ledger coordinate pin mismatch")

    seen: set[str] = set()
    for case in matrix["cases"]:
        if set(case) != REQUIRED_CASE_KEYS:
            raise ValueError("matrix unknown or missing key")
        if case["case_id"] in seen:
            raise ValueError("matrix duplicate case ID")
        seen.add(case["case_id"])
    if not REQUIRED_LIFECYCLE_ROOT_CASES.issubset(seen):
        raise ValueError("matrix missing lifecycle-root signer provenance cases")

    assert_no_literal_backslash_zero(prototype)
    tree = ast.parse(prototype.read_text(encoding="utf-8"))
    if any(
        isinstance(node, ast.Import)
        and any(alias.name.startswith("memorii") for alias in node.names)
        or isinstance(node, ast.ImportFrom)
        and (node.module or "").startswith("memorii")
        for node in ast.walk(tree)
    ):
        raise ValueError("prototype import boundary violated")

    subprocess.run(
        [
            sys.executable,
            str(prototype),
            str(design),
            str(registry),
            str(ledger_path),
            str(vector),
            "--verify",
        ],
        check=True,
    )

    require_binding_value(
        vector_value.get("outer_envelope_binding"),
        OUTER_ENVELOPE_BINDING,
        "outer envelope binding",
    )
    if vector_value.get("ledger_raw_sha256") != expected_raw_ledger_sha:
        raise ValueError("vector raw ledger SHA mismatch")
    outer_envelope_domain = require_domain_bytes(ledger, "outer_envelope")
    _, decoded_body_bytes, decoded_body = decode_artifact_bytes(
        bytes.fromhex(vector_value["envelope_bytes_hex"]),
        outer_envelope_domain,
        BODY_BINDING,
    )
    body = decode_typed_value_json(vector_value["body"])
    if decoded_body != body:
        raise ValueError("envelope-decoded body mismatch")
    expected = expected_body(registry_value, ledger, design_bytes)
    expected["registry_source_identity"] = digest_raw(
        require_domain_bytes(ledger, "raw_registry"), registry.read_bytes()
    )
    expected["derivation_ledger_digest"] = expected_derived_ledger_digest
    expected["derivation_ledger_coordinate"] = expected_derived_coordinate
    if body != expected:
        raise ValueError("body content mismatch")

    body_bytes = encode_typed_value(body)
    if vector_value["body_bytes_hex"] != body_bytes.hex():
        raise ValueError("body bytes mismatch")
    if decoded_body_bytes != body_bytes:
        raise ValueError("envelope body bytes mismatch")
    expected_body_digest = digest_ctv(
        require_domain_bytes(ledger, "structural_body"), body
    )
    if vector_value["body_digest"] != expected_body_digest:
        raise ValueError("body digest mismatch")
    _, expected_envelope = artifact_payload(
        BODY_BINDING, body, outer_envelope_domain
    )
    expected_envelope_digest = artifact_digest(
        outer_envelope_domain, BODY_BINDING, body_bytes
    )
    if vector_value["envelope_bytes_hex"] != expected_envelope.hex():
        raise ValueError("envelope bytes mismatch")
    if vector_value["envelope_digest"] != expected_envelope_digest:
        raise ValueError("envelope digest mismatch")
    if body["assertion_registry_digest"] != body["assertion_registry_artifact"]["artifact_digest"]:
        raise ValueError("assertion registry digest mismatch")
    _, assertion_body_bytes, assertion_body = validate_artifact_value(
        body["assertion_registry_artifact"],
        outer_envelope_domain,
        ASSERTION_ROOT_BINDING,
    )
    if (
        body["assertion_registry_artifact"]["binding"]["schema_id"]
        != ASSERTION_ROOT_BINDING["schema_id"]
    ):
        raise ValueError("assertion registry schema mismatch")
    if assertion_body != {"items": freeze(registry_value["assertion_templates"])}:
        raise ValueError("assertion registry body mismatch")
    if (
        body["assertion_registry_artifact"]["canonical_value_bytes"]
        != assertion_body_bytes
    ):
        raise ValueError("assertion registry bytes mismatch")
    if (
        body["explicit_anchor_bindings"]
        and not isinstance(body["explicit_anchor_bindings"][0], tuple)
    ):
        raise ValueError("anchor binding tuple form mismatch")


def self_test(args: argparse.Namespace) -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        copies: dict[str, Path] = {}
        for label, path in (
            ("design", args.design),
            ("registry", args.registry),
            ("ledger", args.ledger),
            ("matrix", args.matrix),
            ("prototype", args.prototype),
            ("vector", args.vector),
            ("workplan", args.workplan),
        ):
            target = root / path.name
            shutil.copyfile(path, target)
            copies[label] = target
        validate(
            copies["design"],
            copies["registry"],
            copies["ledger"],
            copies["matrix"],
            copies["prototype"],
            copies["vector"],
            copies["workplan"],
            False,
        )

        ledger = json.loads(copies["ledger"].read_text(encoding="utf-8"))
        ledger["digest_domains"]["anchor_binding_root"]["domain_ascii_hex"] = (
            ledger["digest_domains"]["anchor_binding_root"]["domain_ascii_hex"][:-2] + "01"
        )
        copies["ledger"].write_text(
            json.dumps(ledger, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n",
            encoding="utf-8",
        )
        reject(
            [
                sys.executable,
                str(Path(__file__)),
                "--design",
                str(copies["design"]),
                "--registry",
                str(copies["registry"]),
                "--ledger",
                str(copies["ledger"]),
                "--matrix",
                str(copies["matrix"]),
                "--prototype",
                str(copies["prototype"]),
                "--vector",
                str(copies["vector"]),
                "--workplan",
                str(copies["workplan"]),
                "--unpin",
            ],
            "domain-mapping-mutation",
        )
        shutil.copyfile(args.ledger, copies["ledger"])

        workplan_text = copies["workplan"].read_text(encoding="utf-8").replace(
            "29-field", "25-field", 1
        )
        copies["workplan"].write_text(workplan_text, encoding="utf-8")
        reject(
            [
                sys.executable,
                str(Path(__file__)),
                "--design",
                str(copies["design"]),
                "--registry",
                str(copies["registry"]),
                "--ledger",
                str(copies["ledger"]),
                "--matrix",
                str(copies["matrix"]),
                "--prototype",
                str(copies["prototype"]),
                "--vector",
                str(copies["vector"]),
                "--workplan",
                str(copies["workplan"]),
                "--unpin",
            ],
            "workplan-29-field-pin",
        )
        shutil.copyfile(args.workplan, copies["workplan"])

        mutated_ledger = json.loads(copies["ledger"].read_text(encoding="utf-8"))
        mutated_ledger["digest_domains"]["outer_envelope"]["domain_ascii_hex"] = (
            "71656d616e7469632d696e67657374696f6e2d63616e6f6e6963616c2d6172746966616374"
        )
        copies["ledger"].write_text(
            json.dumps(
                mutated_ledger, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            + "\n",
            encoding="utf-8",
        )
        mutated_ledger_bytes = copies["ledger"].read_bytes()
        mutated_raw_sha = sha(copies["ledger"])
        mutated_derived_digest = hashlib.sha256(
            require_domain_bytes(mutated_ledger, "ledger")
            + len(mutated_ledger_bytes).to_bytes(8, "big")
            + mutated_ledger_bytes
        ).hexdigest()
        mutated_coordinate = (
            "structural_manifest_derivation_ledger/"
            f"{mutated_ledger['schema_id']}/{mutated_ledger['schema_version']}/"
            f"{mutated_derived_digest}"
        )
        copies["design"].write_text(
            replace_ledger_pins(
                copies["design"].read_text(encoding="utf-8"),
                mutated_raw_sha,
                mutated_derived_digest,
                mutated_coordinate,
            ),
            encoding="utf-8",
        )
        copies["workplan"].write_text(
            replace_ledger_pins(
                copies["workplan"].read_text(encoding="utf-8"),
                mutated_raw_sha,
                mutated_derived_digest,
                mutated_coordinate,
            ),
            encoding="utf-8",
        )
        original_vector = json.loads(copies["vector"].read_text(encoding="utf-8"))
        original_body = decode_typed_value_json(original_vector["body"])
        mutated_outer_domain = require_domain_bytes(mutated_ledger, "outer_envelope")
        mutated_assertion_root_value = {
            "items": freeze(json.loads(copies["registry"].read_text(encoding="utf-8"))["assertion_templates"])
        }
        mutated_assertion_artifact, _ = artifact_payload(
            ASSERTION_ROOT_BINDING,
            mutated_assertion_root_value,
            mutated_outer_domain,
        )
        if (
            mutated_assertion_artifact["artifact_digest"]
            == original_body["assertion_registry_digest"]
        ):
            raise AssertionError("outer-envelope mutation did not change assertion artifact digest")
        if (
            artifact_digest(mutated_outer_domain, BODY_BINDING, bytes.fromhex(original_vector["body_bytes_hex"]))
            == original_vector["envelope_digest"]
        ):
            raise AssertionError("outer-envelope mutation did not change structural envelope digest")
        reject(
            [
                sys.executable,
                str(Path(__file__)),
                "--design",
                str(copies["design"]),
                "--registry",
                str(copies["registry"]),
                "--ledger",
                str(copies["ledger"]),
                "--matrix",
                str(copies["matrix"]),
                "--prototype",
                str(copies["prototype"]),
                "--vector",
                str(copies["vector"]),
                "--workplan",
                str(copies["workplan"]),
                "--unpin",
            ],
            "outer-envelope-domain-mutation",
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("design", "registry", "ledger", "matrix", "prototype", "vector"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--workplan", type=Path, default=WORKPLAN_PATH)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--unpin", action="store_true")
    args = parser.parse_args()
    validate(
        args.design,
        args.registry,
        args.ledger,
        args.matrix,
        args.prototype,
        args.vector,
        args.workplan,
        not args.unpin,
    )
    if args.self_test:
        self_test(args)
    print("CGS structural contract checked")


if __name__ == "__main__":
    main()
