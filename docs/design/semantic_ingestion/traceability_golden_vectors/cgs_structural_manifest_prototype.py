"""Design-owned, stdlib-only CGS structural-manifest feasibility prototype.

This is intentionally not a production compiler. It proves that the frozen
design, registry, immutable derivation ledger, and current CTV binding
authority can produce one complete 29-field structural body plus a distinct
canonical outer envelope without importing Memorii, either elaborator, or any
generated production artifact.
"""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import re
import signal
import unicodedata
from collections.abc import Callable
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from time import monotonic
from typing import Any

BODY_BINDING = {
    "profile_id": "semantic_ingestion_typed_value",
    "profile_version": 2,
    "profile_digest": "9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f",
    "schema_id": "NormativeTraceabilityStructuralManifestBody.v1",
    "schema_version": 1,
    "binding_digest": "133ba5b492880d5b773eb75f5a81de0bdf0c09e85cce20d17d7aa076cee7b79b",
}


@contextmanager
def parse_watchdog(seconds: float = 30, *, signal_module: Any = signal) -> Any:
    """Interrupt a stalled stdlib parse independently of the parent timeout."""

    def expired(_signum: int, _frame: object) -> None:
        raise TimeoutError("structural parser deadline exceeded")

    previous = signal_module.getsignal(signal_module.SIGALRM)
    signal_module.signal(signal_module.SIGALRM, expired)
    signal_module.setitimer(signal_module.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal_module.setitimer(signal_module.ITIMER_REAL, 0)
        signal_module.signal(signal_module.SIGALRM, previous)


def parser_entry_watchdog(function: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(function)
    def guarded(*args: object, **kwargs: object) -> Any:
        with parse_watchdog(30):
            return function(*args, **kwargs)

    return guarded
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
    "binding_digest": (
    "39222b18e67ffe8f679943676a46a464c804bb2ef9d0e3fd28d27a590fe3fde1"
    ),
}
HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
INTEGER = re.compile(r"(?:0|-?[1-9][0-9]*)\Z")


def canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")
        + b"\n"
    )


def reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def validate_scalar(value: str) -> None:
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise ValueError("non-scalar Unicode")


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
        validate_scalar(value)
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    if isinstance(value, list):
        return b"[" + b",".join(canonical_json_bytes(item) for item in value) + b"]"
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("map keys must be strings")
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
        if isinstance(value, str):
            validate_scalar(value)
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
            if not isinstance(key, str):
                raise ValueError("map keys must be strings")
            entries.append([key, json.loads(encode_typed_value(value[key]))])
        return canonical_json_bytes({"$type": "map", "entries": entries})
    raise TypeError(type(value).__name__)


def freeze(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(freeze(item) for item in value)
    if isinstance(value, dict):
        return {key: freeze(item) for key, item in value.items()}
    return value


def length_prefixed(*parts: bytes) -> bytes:
    return b"".join(len(part).to_bytes(8, "big") + part for part in parts)


def digest_raw(domain: bytes, payload: bytes) -> str:
    return hashlib.sha256(domain + payload).hexdigest()


def digest_ctv(domain: bytes, value: Any) -> str:
    payload = encode_typed_value(value)
    return hashlib.sha256(domain + len(payload).to_bytes(8, "big") + payload).hexdigest()


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


def canonical_artifact(
    binding: dict[str, Any], value: Any, domain: bytes
) -> tuple[dict[str, Any], bytes, str]:
    body_bytes = encode_typed_value(value)
    body_digest = hashlib.sha256(body_bytes).hexdigest()
    envelope_digest = artifact_digest(domain, binding, body_bytes)
    return (
        {
            "binding": dict(binding),
            "canonical_value_bytes": body_bytes,
            "canonical_value_digest": body_digest,
            "artifact_digest": envelope_digest,
        },
        body_bytes,
        envelope_digest,
    )


def serialize_artifact(artifact: dict[str, Any]) -> bytes:
    return encode_typed_value(artifact)


def headings(
    design: bytes, *, check: Callable[[], None] | None = None
) -> tuple[dict[str, object], ...]:
    result: list[dict[str, object]] = []
    ordinal = 0
    cursor = 0
    while cursor <= len(design):
        if check is not None:
            check()
        end = design.find(b"\n", cursor)
        if end < 0:
            end = len(design)
            final = True
        else:
            final = False
        line = design[cursor:end]
        match = re.fullmatch(br"(#{1,6}) ([^\n]+)", line)
        if match is None:
            if final:
                break
            cursor = end + 1
            continue
        ordinal += 1
        result.append(
            {
                "ordinal": ordinal,
                "level": len(match.group(1)),
                "title": match.group(2).decode("utf-8"),
                "byte_offset": cursor,
            }
        )
        if final:
            break
        cursor = end + 1
    return tuple(result)


def require_domain_bytes(ledger: dict[str, Any], domain_id: str) -> bytes:
    domain = ledger["digest_domains"][domain_id]["domain_ascii_hex"]
    if not isinstance(domain, str) or len(domain) % 2 or not re.fullmatch(
        r"[0-9a-f]+", domain
    ):
        raise ValueError(f"invalid domain hex: {domain_id}")
    return bytes.fromhex(domain)


def require_exact_hex(value: str, field: str) -> None:
    if not HEX_64.fullmatch(value):
        raise ValueError(f"{field} must be lowercase 64-hex")


def require_positive_int(value: Any, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")


def require_exact_design_bytes(design: bytes) -> None:
    if design.startswith(b"\xef\xbb\xbf") or b"\x00" in design or b"\r" in design:
        raise ValueError("design contains forbidden bytes")
    if not design.endswith(b"\n") or design.endswith(b"\n\n"):
        raise ValueError("design must end with exactly one LF")
    decoded = design.decode("utf-8")
    if unicodedata.normalize("NFC", decoded) != decoded:
        raise ValueError("design must already be NFC")


def root_domain_value(registry: dict[str, Any], field_name: str) -> Any:
    if field_name == "artifact_dag":
        return freeze(registry["artifact_dag"])
    if field_name == "requirement_binding_registry_digest":
        return freeze(registry["requirement_bindings"])
    if field_name == "section_defaults":
        return freeze(registry["heading_defaults"])
    if field_name == "structural_mapping_rules":
        return freeze(registry["structural_rules"])
    if field_name == "test_evidence_groups":
        return freeze(registry["test_evidence_groups"])
    if field_name == "report_schemas":
        return freeze(registry["report_schemas"])
    if field_name == "runner_environment_profiles":
        return freeze(registry["runner_environment_profiles"])
    if field_name == "overrides":
        return freeze(registry["overrides"])
    raise KeyError(field_name)


@parser_entry_watchdog
def derive(design: bytes, registry: bytes, ledger_bytes: bytes) -> dict[str, object]:
    parse_deadline = monotonic() + 30

    def check_parse() -> None:
        if monotonic() >= parse_deadline:
            raise TimeoutError("structural parser deadline exceeded")

    check_parse()
    require_exact_design_bytes(design)
    check_parse()
    reg = json.loads(registry, object_pairs_hook=reject_duplicate_pairs)
    check_parse()
    led = json.loads(ledger_bytes, object_pairs_hook=reject_duplicate_pairs)
    check_parse()
    fields = led["fields"]
    if [field["ordinal"] for field in fields] != list(range(1, 30)):
        raise ValueError("ledger field ordinals are not complete")
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    if any(
        isinstance(node, ast.Import)
        and any(alias.name.startswith("memorii") for alias in node.names)
        or isinstance(node, ast.ImportFrom)
        and (node.module or "").startswith("memorii")
        for node in ast.walk(tree)
    ):
        raise ValueError("prototype import-boundary self-check failed")

    for binding in (BODY_BINDING, ASSERTION_ROOT_BINDING, OUTER_ENVELOPE_BINDING):
        check_parse()
        require_positive_int(binding["profile_version"], "profile_version")
        require_positive_int(binding["schema_version"], "schema_version")
        require_exact_hex(binding["profile_digest"], "profile_digest")
        require_exact_hex(binding["binding_digest"], "binding_digest")

    outer_envelope_domain = require_domain_bytes(led, "outer_envelope")
    assertion_root_value = {"items": freeze(reg["assertion_templates"])}
    assertion_registry_artifact, _, assertion_registry_digest = canonical_artifact(
        ASSERTION_ROOT_BINDING, assertion_root_value, outer_envelope_domain
    )
    explicit_anchor_bindings = tuple(
        (item["anchor"], (item["heading_path"],)) for item in reg["anchor_bindings"]
    )
    check_parse()

    body = {
        "grammar_revision": led["grammar_revision"],
        "design_document_digest": digest_raw(
            require_domain_bytes(led, "raw_design"), design
        ),
        "registry_source_identity": digest_raw(
            require_domain_bytes(led, "raw_registry"), registry
        ),
        "derivation_ledger_schema_id": led["schema_id"],
        "derivation_ledger_schema_version": led["schema_version"],
        "derivation_ledger_digest": hashlib.sha256(
            require_domain_bytes(led, "ledger")
            + len(ledger_bytes).to_bytes(8, "big")
            + ledger_bytes
        ).hexdigest(),
        "derivation_ledger_coordinate": (
            f"structural_manifest_derivation_ledger/{led['schema_id']}/"
            f"{led['schema_version']}/"
            f"{hashlib.sha256(require_domain_bytes(led, 'ledger') + len(ledger_bytes).to_bytes(8, 'big') + ledger_bytes).hexdigest()}"
        ),
        "artifact_dag": freeze(reg["artifact_dag"]),
        "artifact_dag_digest": digest_ctv(
            require_domain_bytes(led, "artifact_dag_root"),
            root_domain_value(reg, "artifact_dag"),
        ),
        "canonical_profile_binding": dict(BODY_BINDING),
        "requirement_binding_registry_digest": digest_ctv(
            require_domain_bytes(led, "requirement_binding_root"),
            root_domain_value(reg, "requirement_binding_registry_digest"),
        ),
        "section_defaults": freeze(reg["heading_defaults"]),
        "section_default_registry_digest": digest_ctv(
            require_domain_bytes(led, "section_default_root"),
            root_domain_value(reg, "section_defaults"),
        ),
        "structural_mapping_rules": freeze(reg["structural_rules"]),
        "structural_mapping_rule_registry_digest": digest_ctv(
            require_domain_bytes(led, "structural_mapping_rule_root"),
            root_domain_value(reg, "structural_mapping_rules"),
        ),
        "assertion_registry_artifact": assertion_registry_artifact,
        "assertion_registry_digest": assertion_registry_digest,
        "test_evidence_groups": freeze(reg["test_evidence_groups"]),
        "test_evidence_group_registry_digest": digest_ctv(
            require_domain_bytes(led, "test_evidence_group_root"),
            root_domain_value(reg, "test_evidence_groups"),
        ),
        "report_schemas": freeze(reg["report_schemas"]),
        "report_schema_registry_digest": digest_ctv(
            require_domain_bytes(led, "report_schema_root"),
            root_domain_value(reg, "report_schemas"),
        ),
        "runner_environment_profiles": freeze(reg["runner_environment_profiles"]),
        "runner_environment_profile_registry_digest": digest_ctv(
            require_domain_bytes(led, "runner_environment_profile_root"),
            root_domain_value(reg, "runner_environment_profiles"),
        ),
        "units": headings(design, check=check_parse),
        "entries": tuple(),
        "overrides": freeze(reg["overrides"]),
        "override_registry_digest": digest_ctv(
            require_domain_bytes(led, "override_root"),
            root_domain_value(reg, "overrides"),
        ),
        "explicit_anchor_bindings": explicit_anchor_bindings,
        "anchor_binding_registry_digest": digest_ctv(
            require_domain_bytes(led, "anchor_binding_root"), explicit_anchor_bindings
        ),
    }
    body_digest = digest_ctv(require_domain_bytes(led, "structural_body"), body)
    envelope_value, body_bytes, envelope_digest = canonical_artifact(
        BODY_BINDING, body, outer_envelope_domain
    )
    envelope_bytes = serialize_artifact(envelope_value)
    spool_bytes = (
        b"memorii:sia-clean-room-structural-spool:v1\0"
        + len(body_bytes).to_bytes(8, "big")
        + body_bytes
        + len(envelope_bytes).to_bytes(8, "big")
        + envelope_bytes
    )
    return {
        "format": "memorii-cgs-structural-prototype-v1",
        "outer_envelope_binding": dict(OUTER_ENVELOPE_BINDING),
        "ledger_raw_sha256": hashlib.sha256(ledger_bytes).hexdigest(),
        "body": json.loads(body_bytes),
        "body_bytes_hex": body_bytes.hex(),
        "body_digest": body_digest,
        "envelope_bytes_hex": envelope_bytes.hex(),
        "structural_spool_bytes_hex": spool_bytes.hex(),
        "envelope_digest": envelope_digest,
        "known_answer_preimages": {
            "raw_design": {
                "domain_id": "raw_design",
                "domain_ascii_hex": led["digest_domains"]["raw_design"]["domain_ascii_hex"],
            },
            "raw_registry": {
                "domain_id": "raw_registry",
                "domain_ascii_hex": led["digest_domains"]["raw_registry"]["domain_ascii_hex"],
            },
            "ledger": dict(led["ledger_digest_preimage"]),
            "artifact_dag_root": dict(led["digest_domains"]["artifact_dag_root"]),
            "requirement_binding_root": dict(
                led["digest_domains"]["requirement_binding_root"]
            ),
            "section_default_root": dict(led["digest_domains"]["section_default_root"]),
            "structural_mapping_rule_root": dict(
                led["digest_domains"]["structural_mapping_rule_root"]
            ),
            "test_evidence_group_root": dict(
                led["digest_domains"]["test_evidence_group_root"]
            ),
            "report_schema_root": dict(led["digest_domains"]["report_schema_root"]),
            "runner_environment_profile_root": dict(
                led["digest_domains"]["runner_environment_profile_root"]
            ),
            "override_root": dict(led["digest_domains"]["override_root"]),
            "anchor_binding_root": dict(led["digest_domains"]["anchor_binding_root"]),
            "structural_body": dict(led["digest_domains"]["structural_body"]),
            "outer_envelope": dict(led["digest_domains"]["outer_envelope"]),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("design", type=Path)
    parser.add_argument("registry", type=Path)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    value = canonical(
        derive(args.design.read_bytes(), args.registry.read_bytes(), args.ledger.read_bytes())
    )
    if args.verify:
        if args.output.read_bytes() != value:
            raise SystemExit("known-answer mismatch")
    else:
        args.output.write_bytes(value)
    print(hashlib.sha256(value).hexdigest())


if __name__ == "__main__":
    main()
