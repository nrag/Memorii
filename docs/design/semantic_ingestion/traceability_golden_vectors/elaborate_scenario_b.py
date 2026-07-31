# ruff: noqa: E701, E702
"""Independent stdlib encoder for the scenario CTV package."""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).parents[4]
AUTHORITY = Path(__file__).with_name("ctv-binding-authority-v2.json")
LEDGER = Path(__file__).with_name("structural_manifest_derivation_ledger-v1.json")
FORMAT = "memorii-sia-scenario-c2-milestone-2"
PROFILE_ID = "semantic_ingestion_typed_value"
PROFILE_VERSION = 2
FIXTURE_SCHEMA = "TraceabilityGoldenTypedInputFixtureBody.v1"
CONTENT_SCHEMA = "memorii.sia.scenario-ingress-evidence.v1"
CONTENT_MEDIA_TYPE = "application/vnd.memorii.ctv+json;version=2"
CONTENT_PROFILE = "semantic_ingestion_typed_value"
ARTIFACT_DOMAIN = b"semantic-ingestion-canonical-artifact"
_HEAD = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
_LIST = re.compile(r"^(\s*)(?:[-*+] |\d+[.)] )")
_TABLE = re.compile(r"^\s*\|.*\|\s*$")


@dataclass(frozen=True)
class _Unit:
    invariant_id: str
    content_key: str
    duplicate_occurrence: int
    unit_kind: str
    parent_invariant_id: str | None
    heading_path_hash: str
    source_start_line: int
    source_end_line: int
    canonical_payload_digest: str


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(value: Any) -> str:
    return sha(b"semantic-ingestion-traceability\0" + canonical(value))


def _paragraph(lines: list[str]) -> str:
    return "\n".join(unicodedata.normalize("NFC", line.rstrip(" \t")) for line in lines)


def _schema_lines(body: list[str]) -> list[tuple[str, str, int]]:
    source = "\n".join(body)
    tree = ast.parse(source)
    result: list[tuple[str, str, int]] = []
    occupied: set[int] = set()

    def leaves(node: ast.expr) -> tuple[ast.expr, ...]:
        return (
            leaves(node.left) + leaves(node.right)
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr)
            else (node,)
        )

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            result.append(
                (
                    "schema_declaration",
                    ast.get_source_segment(source, node) or node.name,
                    node.lineno - 1,
                )
            )
            occupied.add(node.lineno - 1)
            for field in node.body:
                if isinstance(field, ast.AnnAssign) and isinstance(
                    field.target, ast.Name
                ):
                    result.append(
                        (
                            "schema_field",
                            ast.get_source_segment(source, field) or field.target.id,
                            field.lineno - 1,
                        )
                    )
                    occupied.add(field.lineno - 1)
                    if "|" in ast.unparse(field.annotation) or "Union[" in ast.unparse(
                        field.annotation
                    ):
                        result.extend(
                            ("schema_union_member", ast.unparse(item), field.lineno - 1)
                            for item in leaves(field.annotation)
                        )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            result.append(
                (
                    "schema_declaration",
                    ast.get_source_segment(source, node) or "",
                    node.lineno - 1,
                )
            )
            occupied.add(node.lineno - 1)
            value = getattr(node, "value", None)
            if value is not None and (
                "|" in ast.unparse(value) or "Union[" in ast.unparse(value)
            ):
                result.extend(
                    ("schema_union_member", ast.unparse(item), node.lineno - 1)
                    for item in leaves(value)
                )
    return result + [
        ("code_line", line, index)
        for index, line in enumerate(body)
        if line.strip() and index not in occupied
    ]


def _extract_units(design: bytes) -> tuple[_Unit, ...]:
    if (
        not design
        or design.startswith(b"\xef\xbb\xbf")
        or b"\0" in design
        or b"\r" in design
        or not design.endswith(b"\n")
        or design.endswith(b"\n\n")
    ):
        raise ValueError("invalid design transport")
    all_lines = design.decode("utf-8").split("\n")
    starts = [index for index, line in enumerate(all_lines) if line.startswith("## 1.")]
    if len(starts) != 1:
        raise ValueError("section 1")
    five = next(
        (
            index
            for index in range(starts[0], len(all_lines))
            if all_lines[index].startswith("## 5.")
        ),
        None,
    )
    if five is None:
        raise ValueError("section 5")
    stop = next(
        (
            index
            for index in range(five + 1, len(all_lines))
            if all_lines[index].startswith("## ")
        ),
        len(all_lines),
    )
    lines, offset, raw, stack, index = (
        all_lines[starts[0] : stop],
        starts[0] + 1,
        [],
        [],
        0,
    )
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        match = _HEAD.match(line)
        if match:
            level, title = len(match.group(1)), match.group(2)
            while stack and stack[-1][0] >= level:
                stack.pop()
            path = _digest(
                {"heading_path": tuple(item[1] for item in stack) + (title,)}
            )
            raw.append(
                (
                    "heading",
                    title,
                    f"@{stack[-1][2]}" if stack else None,
                    path,
                    offset + index,
                    offset + index,
                    (),
                )
            )
            stack.append((level, title, len(raw) - 1))
            index += 1
            continue
        parent = f"@{stack[-1][2]}" if stack else None
        path = (
            _digest({"heading_path": tuple(item[1] for item in stack)})
            if stack
            else _digest({"heading_path": ()})
        )
        if line.startswith("```"):
            begin, lang = index, line[3:].strip().lower()
            index += 1
            body = []
            while index < len(lines) and not lines[index].startswith("```"):
                body.append(lines[index])
                index += 1
            if index == len(lines):
                raise ValueError("unclosed fence")
            fence_index = len(raw)
            raw.append(
                (
                    "fence",
                    f"{lang}\n{_paragraph(body)}",
                    parent,
                    path,
                    offset + begin,
                    offset + index,
                    (),
                )
            )
            children = (
                _schema_lines(body)
                if lang in {"python", "py"}
                else [
                    (
                        "diagram_edge"
                        if "-->" in item.strip() or "---" in item.strip()
                        else "diagram_node",
                        item.strip(),
                        item_index,
                    )
                    for item_index, item in enumerate(body)
                    if item.strip()
                ]
                if lang in {"mermaid", "diagram"}
                else [
                    ("code_line", item, item_index)
                    for item_index, item in enumerate(body)
                    if item.strip()
                ]
            )
            raw.extend(
                (
                    kind,
                    value,
                    f"@{fence_index}",
                    path,
                    offset + begin + child_index + 1,
                    offset + begin + child_index + 1,
                    (),
                )
                for kind, value, child_index in children
            )
            index += 1
            continue
        if _TABLE.match(line):
            begin, rows = index, []
            while index < len(lines) and _TABLE.match(lines[index]):
                rows.append(lines[index])
                index += 1

            def visible(row: str) -> bool:
                return not all(
                    cell.strip() and set(cell.strip()) <= {"-", ":"}
                    for cell in row.strip().strip("|").split("|")
                )

            child_rows = [
                row
                for row in rows
                if not all(
                    cell and set(cell) <= {"-", ":"}
                    for cell in row.strip().strip("|").split("|")
                )
            ]
            visible_rows = [row for row in rows if visible(row)]
            table_index = len(raw)
            raw.append(
                (
                    "table",
                    _paragraph(rows),
                    parent,
                    path,
                    offset + begin,
                    offset + index - 1,
                    tuple(_digest({"row": _paragraph([row])}) for row in child_rows),
                )
            )
            raw.extend(
                (
                    "table_row",
                    row,
                    f"@{table_index}",
                    path,
                    offset + begin + row_index,
                    offset + begin + row_index,
                    (),
                )
                for row_index, row in enumerate(rows)
                if row in visible_rows
            )
            continue
        if _LIST.match(line):
            begin, items = index, []
            while index < len(lines) and (
                not lines[index].strip()
                or _LIST.match(lines[index])
                or lines[index].startswith((" ", "\t"))
            ):
                if _LIST.match(lines[index]):
                    start, item = index, [lines[index]]
                    index += 1
                    while (
                        index < len(lines)
                        and lines[index].startswith((" ", "\t"))
                        and not _LIST.match(lines[index])
                    ):
                        item.append(lines[index])
                        index += 1
                    items.append((start, item))
                else:
                    index += 1
            list_index = len(raw)
            raw.append(
                (
                    "list",
                    _paragraph([item[0] for _, item in items]),
                    parent,
                    path,
                    offset + begin,
                    offset + index - 1,
                    tuple(_digest({"item": _paragraph(item)}) for _, item in items),
                )
            )
            raw.extend(
                (
                    "list_item",
                    _paragraph(item),
                    f"@{list_index}",
                    path,
                    offset + start,
                    offset + start + len(item) - 1,
                    (),
                )
                for start, item in items
            )
            continue
        begin, paragraph = index, []
        while (
            index < len(lines)
            and lines[index].strip()
            and not _HEAD.match(lines[index])
            and not lines[index].startswith("```")
            and not _TABLE.match(lines[index])
            and not _LIST.match(lines[index])
        ):
            paragraph.append(lines[index])
            index += 1
        raw.append(
            (
                "paragraph",
                _paragraph(paragraph),
                parent,
                path,
                offset + begin,
                offset + index - 1,
                (),
            )
        )
    seen: dict[str, int] = {}
    provisional = []
    for kind, value, parent, path, begin, end, children in raw:
        key = _digest(
            {
                "grammar_revision": "sia-traceability-v1",
                "kind": kind,
                "payload": value,
                "children": children,
            }
        )
        occurrence = seen.get(key, 0)
        seen[key] = occurrence + 1
        provisional.append(
            (
                f"SIA-N-{key}-{occurrence}",
                key,
                occurrence,
                kind,
                parent,
                path,
                begin,
                end,
                _digest(value),
            )
        )
    return tuple(
        _Unit(
            identity,
            key,
            occurrence,
            kind,
            None if parent is None else provisional[int(parent[1:])][0],
            path,
            begin,
            end,
            payload,
        )
        for identity, key, occurrence, kind, parent, path, begin, end, payload in provisional
    )


def rebuild_structural_manifest_bytes(design: bytes, registry_bytes: bytes) -> bytes:
    """B's stdlib-only reconstruction of the registered structural body."""
    registry = json.loads(registry_bytes)
    units = _extract_units(design)
    lines = design.decode("utf-8").split("\n")
    numbered: list[tuple[int, str]] = []
    paths: set[str] = set()
    active = False
    for line_number, line in enumerate(lines, 1):
        if re.match(r"^##\s+[1-5]\.\s", line):
            active = True
        elif line.startswith("## "):
            active = False
        match = re.match(r"^(#{2,6})\s+(\d+(?:\.\d+)*)[.\s]", line)
        if match:
            numbered.append((line_number, match.group(2)))
            if active:
                paths.add(match.group(2))
    defaults = {
        row["heading_path"]: tuple(row["requirements"])
        for row in registry["heading_defaults"]
    }
    if set(defaults) != paths:
        raise ValueError("heading defaults")
    bindings = {row["requirement_id"]: row for row in registry["requirement_bindings"]}
    overrides = {row["invariant_id"]: row for row in registry["overrides"]}
    mappings = []
    for unit in units:
        heading = [path for line, path in numbered if line <= unit.source_start_line][
            -1
        ]
        required = set(defaults[heading])
        sources = [f"heading-default:{heading}"]
        if unit.unit_kind == "table_row":
            row = next(
                line
                for line in lines[unit.source_start_line - 1 : unit.source_end_line]
                if line.lstrip().startswith("|")
            )
            cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
            for rule in registry["structural_rules"]:
                if (
                    rule["heading_path"] == heading
                    and rule["selector_kind"] == "named_table_rows"
                ):
                    for requirement in rule["selector_values"]:
                        if requirement in cells:
                            required.add(requirement)
                            sources.append(f"rule:{rule['rule_id']}:{requirement}")
        if unit.invariant_id in overrides:
            required.update(overrides[unit.invariant_id]["added_requirements"])
            sources.append(f"override:{unit.invariant_id}")
        for requirement in sorted(
            required, key=lambda item: int(item.rsplit("R", 1)[1])
        ):
            binding = bindings[requirement]
            mappings.append(
                {
                    "invariant_id": unit.invariant_id,
                    "content_key": unit.content_key,
                    "requirement_id": requirement,
                    "assertion_template_id": binding["assertion_template_id"],
                    "assertion_version": binding["assertion_version"],
                    "test_evidence_group": binding["test_evidence_group"],
                    "mapping_sources": sources,
                }
            )

    def reg(value: Any) -> bytes:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    roots = {
        name: sha(
            b"memorii:sia-traceability-registry-root:"
            + name.encode()
            + b":v1\0"
            + reg(registry[name])
        )
        for name in registry
        if name
        not in {
            "format",
            "registry_id",
            "grammar_revision",
            "design_path",
            "report_schemas",
            "runner_environment_profiles",
        }
    }
    for name, item_domain, root_domain in (
        (
            "report_schemas",
            b"memorii:sia-report-schema:v1\0",
            b"memorii:sia-report-schema-registry:v1\0",
        ),
        (
            "runner_environment_profiles",
            b"memorii:sia-runner-environment-profile:v1\0",
            b"memorii:sia-runner-environment-profile-registry:v1\0",
        ),
    ):
        items = [sha(item_domain + reg(item) + b"\n") for item in registry[name]]
        roots[name] = sha(root_domain + reg(items) + b"\n")
    body = {
        "design_document_digest": sha(b"semantic-ingestion-traceability\0" + design),
        "registry_source_identity": sha(
            b"memorii:sia-traceability-source:v1\0" + registry_bytes
        ),
        "grammar_revision": registry["grammar_revision"],
        "registry_root_digests": [list(item) for item in sorted(roots.items())],
        "units": [asdict(unit) for unit in units],
        "mappings": mappings,
    }
    return reg(body)


def _document(value: Any) -> bytes:
    return canonical(value) + b"\n"


def _signature(key: str, payload: bytes) -> bytes:
    return hashlib.sha256(
        b"memorii:acceptance-verifier:v1\0deterministic-v1\0"
        + key.encode()
        + b"\0"
        + payload
    ).digest()


def _signed(
    body: dict[str, Any], domain: bytes, digest_field: str, key: str
) -> dict[str, Any]:
    digest = sha(domain + b"\0" + _document(body))
    return {
        **body,
        digest_field: digest,
        "signature": _signature(key, digest.encode()).hex(),
    }


def _authority_binding(authority: dict[str, Any], schema: str) -> dict[str, Any]:
    profile = authority["profile"]
    item = next(item for item in authority["schemas"] if item["coordinate"] == schema)
    return {
        "profile_id": profile["id"],
        "profile_version": profile["version"],
        "profile_digest": profile["digest"],
        "schema_id": schema,
        "schema_version": 1,
        "binding_digest": item["binding_digest"],
    }


def _typed(authority: dict[str, Any], body: dict[str, Any], schema: str) -> bytes:
    return artifact(body, _authority_binding(authority, schema))[0]


def _artifact_digest(raw: bytes) -> str:
    return sha(b"memorii:sia-evidence-artifact:v1\0" + raw)


def _observation_digest(raw: bytes) -> str:
    return sha(b"memorii:sia-runner-environment-observation:v1\0" + raw)


def _build_registered_closure(
    design: bytes, registry_bytes: bytes, authority_bytes: bytes, ledger_bytes: bytes
) -> tuple[bytes, list[dict[str, Any]]]:
    """Independently rebuild the deterministic, explicitly test-only authority."""
    authority, registry = json.loads(authority_bytes), json.loads(registry_bytes)
    structural = rebuild_structural_manifest_bytes(design, registry_bytes)
    bootstrap_key, recovery_key = (
        "scenario-c2-test-bootstrap-key",
        "scenario-c2-test-recovery-key",
    )
    bootstrap = _signed(
        {
            "anchor_id": "scenario-c2-bootstrap",
            "issuance_purpose": "semantic_ingestion_traceability_release_root",
            "canonical_profile_id": "memorii-sia-canonical-json-v1",
            "signature_profile_id": "deterministic-v1",
            "public_key_or_root_certificate_digest": bootstrap_key,
            "target_authority_id": "scenario-c2-test-authority",
        },
        b"memorii:sia-traceability-bootstrap-anchor:v1",
        "anchor_digest",
        bootstrap_key,
    )
    recovery = _signed(
        {
            "recovery_root_id": "scenario-c2-recovery",
            "issuance_purpose": "semantic_ingestion_traceability_recovery_root",
            "canonical_profile_id": "memorii-sia-canonical-json-v1",
            "signature_profile_id": "deterministic-v1",
            "public_key_or_root_certificate_digest": recovery_key,
            "target_authority_id": "scenario-c2-test-authority",
        },
        b"memorii:sia-traceability-recovery-root:v1",
        "recovery_root_digest",
        recovery_key,
    )
    policy = _signed(
        {
            "issuance_purpose": "semantic_ingestion_traceability_recovery_policy",
            "canonical_profile_id": "memorii-sia-canonical-json-v1",
            "signature_profile_id": "deterministic-v1",
            "policy_signer_key_or_certificate_digest": bootstrap_key,
            "active_bootstrap_anchor_digest": bootstrap["anchor_digest"],
            "eligible_recovery_root_digests": [recovery["recovery_root_digest"]],
            "threshold": 1,
        },
        b"memorii:sia-traceability-recovery-policy:v1",
        "recovery_policy_digest",
        bootstrap_key,
    )
    record = {
        "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
        "sequence": 1,
        "predecessor_record_digest": None,
        "effective_at": "2026-07-30T00:00:00Z",
        "recorded_at": "2026-07-30T00:00:01Z",
        "action": "activate",
        "target_id": "scenario-c2-bootstrap",
        "target_digest": bootstrap["anchor_digest"],
        "replacement_target_id": None,
        "replacement_target_digest": None,
        "signer_bindings": [
            {
                "signer_id": "scenario-c2-bootstrap",
                "signature_profile_id": "deterministic-v1",
                "key_digest": bootstrap_key,
            }
        ],
    }
    record_digest = sha(
        b"memorii:sia-traceability-lifecycle-record:v1\0" + _document(record)
    )
    lifecycle = {
        "authority_id": "scenario-c2-test-authority",
        "records": [
            {
                **record,
                "record_digest": record_digest,
                "signatures": [_signature(bootstrap_key, record_digest.encode()).hex()],
            }
        ],
    }
    lifecycle["lifecycle_root_digest"] = sha(
        b"memorii:sia-traceability-trust-lifecycle-root:v1\0" + _document(lifecycle)
    )
    lifecycle["signature"] = _signature(
        bootstrap_key, lifecycle["lifecycle_root_digest"].encode()
    ).hex()
    rebuilt_structural = json.loads(structural)
    ledger_bytes = Path(__file__).with_name(
        "structural_manifest_derivation_ledger-v1.json"
    ).read_bytes()
    ledger = json.loads(ledger_bytes)
    domains = {
        name: bytes.fromhex(value["domain_ascii_hex"])
        for name, value in ledger["digest_domains"].items()
    }

    def ledger_value_digest(domain: str, value: Any) -> str:
        encoded = canonical(typed(value))
        return sha(domains[domain] + len(encoded).to_bytes(8, "big") + encoded)

    ledger_identity = sha(
        bytes.fromhex(ledger["ledger_digest_preimage"]["domain_ascii_hex"])
        + len(ledger_bytes).to_bytes(8, "big")
        + ledger_bytes
    )
    assertion_registry = _typed(
        authority,
        registry["assertion_templates"],
        "TraceabilityRegistryRoot.assertion_templates.v1",
    )
    assertion_envelope = dict(json.loads(assertion_registry)["entries"])
    requirement_bindings = sorted(
        registry["requirement_bindings"],
        key=lambda item: int(item["requirement_id"].rsplit("R", 1)[1]),
    )
    numbered_paths = [
        match.group(1)
        for line in design.decode().splitlines()
        if (match := re.match(r"^#{2,6}\s+(\d+(?:\.\d+)*)[.\s]", line))
    ]
    section_defaults = sorted(
        registry["heading_defaults"],
        key=lambda item: numbered_paths.index(item["heading_path"]),
    )
    anchors = [
        (item["anchor"], (item["heading_path"],))
        for item in registry["anchor_bindings"]
    ]
    structural_value = {
        "grammar_revision": ledger["grammar_revision"],
        "design_document_digest": sha(domains["raw_design"] + design),
        "registry_source_identity": sha(domains["raw_registry"] + registry_bytes),
        "derivation_ledger_schema_id": ledger["schema_id"],
        "derivation_ledger_schema_version": ledger["schema_version"],
        "derivation_ledger_digest": ledger_identity,
        "derivation_ledger_coordinate": f"structural_manifest_derivation_ledger/{ledger['schema_id']}/{ledger['schema_version']}/{ledger_identity}",
        "artifact_dag": registry["artifact_dag"],
        "artifact_dag_digest": ledger_value_digest("artifact_dag_root", registry["artifact_dag"]),
        "canonical_profile_binding": _authority_binding(authority, "NormativeTraceabilityStructuralManifestBody.v1"),
        "requirement_binding_registry_digest": ledger_value_digest("requirement_binding_root", requirement_bindings),
        "section_defaults": section_defaults,
        "section_default_registry_digest": ledger_value_digest("section_default_root", section_defaults),
        "structural_mapping_rules": registry["structural_rules"],
        "structural_mapping_rule_registry_digest": ledger_value_digest("structural_mapping_rule_root", registry["structural_rules"]),
        "assertion_registry_artifact": assertion_registry,
        "assertion_registry_digest": assertion_envelope["artifact_digest"],
        "test_evidence_groups": registry["test_evidence_groups"],
        "test_evidence_group_registry_digest": ledger_value_digest("test_evidence_group_root", registry["test_evidence_groups"]),
        "report_schemas": registry["report_schemas"],
        "report_schema_registry_digest": ledger_value_digest("report_schema_root", registry["report_schemas"]),
        "runner_environment_profiles": registry["runner_environment_profiles"],
        "runner_environment_profile_registry_digest": ledger_value_digest("runner_environment_profile_root", registry["runner_environment_profiles"]),
        "units": rebuilt_structural["units"],
        "entries": rebuilt_structural["mappings"],
        "overrides": registry["overrides"],
        "override_registry_digest": ledger_value_digest("override_root", registry["overrides"]),
        "explicit_anchor_bindings": anchors,
        "anchor_binding_registry_digest": ledger_value_digest("anchor_binding_root", anchors),
    }
    structural_digest = ledger_value_digest("structural_body", structural_value)
    structural_value["structural_manifest_digest"] = structural_digest
    coverage = {"structural_manifest_digest": structural_digest, "approvals": []}
    coverage["coverage_root_digest"] = sha(
        b"memorii:sia-traceability-coverage-root:v1\0" + canonical(typed(coverage))
    )
    execution = {
        "structural_manifest_digest": structural_digest,
        "evidence_records": [],
    }
    execution["execution_root_digest"] = sha(
        b"memorii:sia-traceability-execution-root:v1\0" + canonical(typed(execution))
    )
    def declared(domain: bytes, body: dict[str, Any]) -> str:
        return sha(domain + b"\0" + canonical(typed(body)))

    history_bodies = {
        "bootstrap_anchor_history": {"history_id": "scenario-c2-bootstrap-history", "canonical_profile_binding": _authority_binding(authority, "TraceabilityBootstrapAnchorHistoryBody.v1"), "anchors": [bootstrap]},
        "recovery_root_history": {"history_id": "scenario-c2-recovery-history", "canonical_profile_binding": _authority_binding(authority, "TraceabilityRecoveryRootHistoryBody.v1"), "recovery_roots": [recovery]},
        "recovery_policy_history": {"history_id": "scenario-c2-policy-history", "canonical_profile_binding": _authority_binding(authority, "TraceabilityRecoveryPolicyHistoryBody.v1"), "policies": [policy]},
    }
    history_domains = {"bootstrap_anchor_history": ("TraceabilityBootstrapAnchorHistoryBody.v1", b"memorii:sia-traceability-bootstrap-anchor-history:v1"), "recovery_root_history": ("TraceabilityRecoveryRootHistoryBody.v1", b"memorii:sia-traceability-recovery-root-history:v1"), "recovery_policy_history": ("TraceabilityRecoveryPolicyHistoryBody.v1", b"memorii:sia-traceability-recovery-policy-history:v1")}
    history_values = {name: {**body, "history_digest": declared(history_domains[name][1], body)} for name, body in history_bodies.items()}
    release_id = "scenario-c2-semantic-ingestion-r03-release"
    qualified_issuer = {"signature_purpose": "semantic_ingestion_traceability_release", "issuer_id": "scenario-c2-bootstrap", "key_or_certificate_digest": bootstrap_key, "signature_profile_id": "deterministic-v1", "trust_lifecycle_root_digest": lifecycle["lifecycle_root_digest"], "lifecycle_record_digest": record_digest, "eligible_not_before": "0001-01-01T00:00:00+00:00", "eligible_not_after": None, "eligibility_derivation": {"trust_lifecycle_root_digest": lifecycle["lifecycle_root_digest"], "terminal_record_digest": record_digest, "terminal_sequence": 1, "target_id": "scenario-c2-bootstrap", "target_digest": bootstrap["anchor_digest"], "eligible_not_before": "0001-01-01T00:00:00+00:00", "eligible_not_after": None}}
    snapshot_body = {"snapshot_id": "scenario-c2-snapshot", "issuance_purpose": "semantic_ingestion_traceability_release_trust_snapshot", "canonical_profile_binding": _authority_binding(authority, "TraceabilityReleaseTrustSnapshotBody.v1"), "release_id": release_id, "release_epoch": 1, "release_sequence": 1, "bootstrap_anchor_digest": bootstrap["anchor_digest"], "recovery_policy_digest": policy["recovery_policy_digest"], "trust_lifecycle_root_digest": lifecycle["lifecycle_root_digest"], "lifecycle_recorded_time_cutoff": "2026-07-30T00:00:01+00:00", "qualified_issuers": [qualified_issuer], "created_at": "2026-07-30T00:00:02+00:00"}
    snapshot_value = {**snapshot_body, "trust_snapshot_digest": declared(b"memorii:sia-traceability-release-trust-snapshot:v1", snapshot_body)}
    golden_body = {"manifest_id": "scenario-c2-golden", "manifest_version": 1, "source_path": "docs/design/semantic_ingestion/traceability_golden_vectors/v1.json", "owner": "acceptance_independent_vector_author", "authority_use": "verification_fixture_not_runtime_authority", "canonical_profile_binding": _authority_binding(authority, "TraceabilityApprovalGoldenVectorManifestBody.v1"), "design_document_digest": sha(b"semantic-ingestion-traceability\0" + design), "registry_source_identity": sha(b"memorii:sia-traceability-source:v1\0" + registry_bytes), "fixtures": [], "vectors": []}
    golden_value = {**golden_body, "golden_vector_manifest_digest": declared(b"memorii:sia-traceability-approval-golden-vectors:v1", golden_body)}
    root_digests = json.loads(structural)["registry_root_digests"]
    roots = {
        "registry_source_identity": sha(
            b"memorii:sia-traceability-source:v1\0" + registry_bytes
        ),
        **{f"{name}_digest": digest for name, digest in root_digests},
        "design_document_digest": sha(b"semantic-ingestion-traceability\0" + design),
        "structural_manifest_digest": structural_digest,
        "coverage_root_digest": coverage["coverage_root_digest"],
        "execution_root_digest": execution["execution_root_digest"],
        "report_schema_registry_digest": dict(root_digests)["report_schemas"],
        "runner_environment_profile_registry_digest": dict(root_digests)[
            "runner_environment_profiles"
        ],
        "trust_snapshot_digest": snapshot_value["trust_snapshot_digest"],
        "golden_vector_manifest_digest": golden_value["golden_vector_manifest_digest"],
        "bootstrap_anchor_history_digest": history_values["bootstrap_anchor_history"]["history_digest"],
        "recovery_root_history_digest": history_values["recovery_root_history"]["history_digest"],
        "recovery_policy_history_digest": history_values["recovery_policy_history"]["history_digest"],
    }
    release = _signed(
        {
            "release_id": release_id,
            "issuance_purpose": "semantic_ingestion_traceability_release",
            "canonical_profile_id": "memorii-sia-canonical-json-v1",
            "signature_profile_id": "deterministic-v1",
            "issuer_key_or_certificate_digest": bootstrap_key,
            "grammar_revision": registry["grammar_revision"],
            "issued_state": "active",
            "predecessor_release_id": None,
            "supersedes_release_id": None,
            "bootstrap_anchor_id": bootstrap["anchor_id"],
            "bootstrap_anchor_digest": bootstrap["anchor_digest"],
            "bootstrap_rotation_sequence": 1,
            "recovery_root_digest": recovery["recovery_root_digest"],
            "recovery_trust_policy_digest": policy["recovery_policy_digest"],
            "recovery_trust_root_digests": [recovery["recovery_root_digest"]],
            "trust_lifecycle_root_digest": lifecycle["lifecycle_root_digest"],
            "issued_at": "2026-07-30T00:00:02Z",
            "expires_at": datetime(2026, 7, 31, 0, 1, tzinfo=timezone.utc).isoformat(),
            "epoch": 1,
            "sequence": 1,
            **roots,
        },
        b"memorii:sia-traceability-release:v1",
        "release_digest",
        bootstrap_key,
    )
    history_entry = {
        "entry_id": "scenario-c2-entry-1",
        "sequence": 1,
        "predecessor_entry_digest": None,
        "release_id": release["release_id"],
        "release_digest": release["release_digest"],
        "release_epoch": release["epoch"],
        "release_sequence": release["sequence"],
        "prior_active_release_digest": None,
        "prior_release_terminal_state": None,
        "effective_at": release["issued_at"],
    }
    history_entry["entry_digest"] = sha(
        b"memorii:sia-traceability-release-history-entry:v1\0"
        + _document(history_entry)
    )
    history = _signed(
        {
            "history_id": "scenario-c2-history",
            "issuance_purpose": "semantic_ingestion_traceability_release_history",
            "canonical_profile_id": "memorii-sia-canonical-json-v1",
            "signature_profile_id": "deterministic-v1",
            "issuer_key_or_certificate_digest": bootstrap_key,
            "entries": [history_entry],
        },
        b"memorii:sia-traceability-release-history:v1",
        "release_history_digest",
        bootstrap_key,
    )
    values = {
        "bootstrap_anchor": (bootstrap, "TraceabilityBootstrapTrustAnchorBody.v1"),
        "recovery_root": (recovery, "TraceabilityRecoveryTrustRootBody.v1"),
        "recovery_policy": (policy, "TraceabilityRecoveryTrustPolicyBody.v1"),
        "trust_lifecycle_root": (lifecycle, "TraceabilityTrustLifecycleRootBody.v1"),
        "structural_manifest": (structural_value, "NormativeTraceabilityStructuralManifestBody.v1"),
        "coverage_root": (coverage, "TraceabilityCoverageEvidenceRootBody.v1"),
        "execution_root": (execution, "TraceabilityExecutionEvidenceRootBody.v1"),
        "release": (release, "SemanticIngestionTraceabilityReleaseBody.v1"),
        "release_history": (history, "TraceabilityReleaseHistoryBody.v1"),
    }
    raw = {
        name: _typed(authority, body, schema) for name, (body, schema) in values.items()
    }
    generation_binding = _authority_binding(authority, "TraceabilityApprovalGenerationManifestBody.v1")
    pointer_binding = _authority_binding(authority, "TraceabilityActiveReleasePointerBody.v1")
    signer = {
        "signature_purpose": "semantic_ingestion_traceability_approval_generation",
        "issuer_id": "scenario-c2-bootstrap",
        "key_or_certificate_digest": bootstrap_key,
        "signature_profile_id": "deterministic-v1",
        "trust_lifecycle_root_digest": lifecycle["lifecycle_root_digest"],
        "lifecycle_record_digest": lifecycle["records"][0]["record_digest"],
        "eligible_not_before": "0001-01-01T00:00:00+00:00",
        "eligible_not_after": None,
    }
    pointer_signer = {
        **signer,
        "source_kind": "prior_verified_lifecycle_root",
        "signature_purpose": "semantic_ingestion_traceability_active_release_pointer",
    }
    pointer_history_signer = {
        **pointer_signer,
        "signature_purpose": "semantic_ingestion_traceability_pointer_history",
    }
    pointer_history_body = {"history_id": "scenario-c2-pointer-history", "issuance_purpose": "semantic_ingestion_traceability_pointer_history", "canonical_profile_binding": _authority_binding(authority, "TraceabilityActiveReleasePointerHistoryBody.v1"), "pointers": [], "signer_coordinate": pointer_history_signer}
    pointer_history_digest = declared(
        b"memorii:sia-traceability-pointer-history:v1", pointer_history_body
    )
    pointer_history_value = {
        **pointer_history_body,
        "pointer_history_digest": pointer_history_digest,
        "signature": _signature(
            bootstrap_key,
            canonical(
                typed(
                    {
                        "issuance_purpose": "semantic_ingestion_traceability_pointer_history",
                        "body_binding": _authority_binding(
                            authority,
                            "TraceabilityActiveReleasePointerHistoryBody.v1",
                        ),
                        "pointer_history_digest": pointer_history_digest,
                        "signer_coordinate": pointer_history_signer,
                    }
                )
            ),
        ).hex(),
    }
    raw.update({name: _typed(authority, value, history_domains[name][0]) for name, value in history_values.items()})
    raw["trust_snapshot"] = _typed(authority, snapshot_value, "TraceabilityReleaseTrustSnapshotBody.v1")
    raw["golden_vector_manifest"] = _typed(authority, golden_value, "TraceabilityApprovalGoldenVectorManifestBody.v1")
    raw["pointer_history"] = _typed(authority, pointer_history_value, "TraceabilityActiveReleasePointerHistoryBody.v1")
    design_digest = roots["design_document_digest"]
    members = []
    blobs = {}

    def add(kind: str, raw_bytes: bytes, dependencies: list[str]) -> None:
        envelope = json.loads(raw_bytes)
        if envelope.get("$type") != "map" or not isinstance(envelope.get("entries"), list):
            raise ValueError("registered generation member envelope")
        envelope_values = dict(envelope["entries"])
        digest = envelope_values["artifact_digest"]
        binding_value = envelope_values["binding"]
        if not isinstance(binding_value, dict) or binding_value.get("$type") != "map":
            raise ValueError("registered generation member binding")
        binding = dict(binding_value["entries"])
        coordinate = f"sia-traceability/v1/{kind}/{digest}"
        blobs[coordinate] = raw_bytes
        members.append(
            {
                "artifact_kind": kind,
                "artifact_coordinate": coordinate,
                "artifact_digest": digest,
                "depends_on_coordinates": dependencies,
                "schema_id": binding["schema_id"],
                "schema_version": 1,
                "binding_digest": binding["binding_digest"],
            }
        )

    design_coordinate = f"sia-traceability/v1/design_document/{design_digest}"
    blobs[design_coordinate] = design
    members.append(
        {
            "artifact_kind": "design_document",
            "artifact_coordinate": design_coordinate,
            "artifact_digest": design_digest,
            "depends_on_coordinates": [],
            "schema_id": "memorii.raw.design_document.v1",
            "schema_version": 1,
            "binding_digest": "raw-sha256-bytes-v1",
        }
    )
    registry_coordinate = (
        f"sia-traceability/v1/registry_source/{roots['registry_source_identity']}"
    )
    blobs[registry_coordinate] = registry_bytes
    members.append(
        {
            "artifact_kind": "registry_source",
            "artifact_coordinate": registry_coordinate,
            "artifact_digest": roots["registry_source_identity"],
            "depends_on_coordinates": [design_coordinate],
            "schema_id": "memorii.raw.registry_source.v1",
            "schema_version": 1,
            "binding_digest": "raw-sha256-bytes-v1",
        }
    )
    ledger_digest = sha(
        b"memorii:sia-traceability-structural-manifest-derivation-ledger:v1\0"
        + len(ledger_bytes).to_bytes(8, "big")
        + ledger_bytes
    )
    ledger_coordinate = (
        "sia-traceability/v1/structural_manifest_derivation_ledger/"
        + ledger_digest
    )
    blobs[ledger_coordinate] = ledger_bytes
    members.append(
        {
            "artifact_kind": "structural_manifest_derivation_ledger",
            "artifact_coordinate": ledger_coordinate,
            "artifact_digest": ledger_digest,
            "depends_on_coordinates": [],
            "schema_id": "memorii.raw.structural_manifest_derivation_ledger.v1",
            "schema_version": 1,
            "binding_digest": "raw-sha256-bytes-v1",
        }
    )
    coordinate_by_kind = {
        "design_document": design_coordinate,
        "registry_source": registry_coordinate,
        "structural_manifest_derivation_ledger": ledger_coordinate,
    }
    dependencies = {
        "bootstrap_anchor": (), "recovery_root": (), "recovery_policy": ("bootstrap_anchor", "recovery_root"),
        "bootstrap_anchor_history": ("bootstrap_anchor",), "recovery_root_history": ("recovery_root",), "recovery_policy_history": ("recovery_policy",),
        "trust_lifecycle_root": ("bootstrap_anchor_history", "recovery_root_history", "recovery_policy_history"),
        "trust_snapshot": ("trust_lifecycle_root", "bootstrap_anchor_history", "recovery_root_history", "recovery_policy_history"),
        "structural_manifest": ("design_document", "registry_source", "structural_manifest_derivation_ledger"), "coverage_root": ("structural_manifest",), "execution_root": ("structural_manifest",), "golden_vector_manifest": (),
        "release": ("bootstrap_anchor", "bootstrap_anchor_history", "recovery_root", "recovery_root_history", "recovery_policy", "recovery_policy_history", "trust_lifecycle_root", "trust_snapshot", "structural_manifest", "coverage_root", "execution_root", "golden_vector_manifest"),
        "release_history": ("release",), "pointer_history": (),
    }
    for name in ("bootstrap_anchor", "recovery_root", "recovery_policy", "bootstrap_anchor_history", "recovery_root_history", "recovery_policy_history", "trust_lifecycle_root", "trust_snapshot", "structural_manifest", "coverage_root", "execution_root", "golden_vector_manifest", "release", "release_history", "pointer_history"):
        raw_bytes = raw[name]
        assert isinstance(raw_bytes, bytes)
        envelope = json.loads(raw_bytes)
        if envelope.get("$type") != "map" or not isinstance(envelope.get("entries"), list):
            raise ValueError("registered generation member envelope")
        digest = dict(envelope["entries"])["artifact_digest"]
        coordinate_by_kind[name] = f"sia-traceability/v1/{name}/{digest}"
        add(name, raw_bytes, sorted(coordinate_by_kind[item] for item in dependencies[name]))
    intent = {"pointer_id": "scenario-c2-pointer-1", "issuance_purpose": "semantic_ingestion_traceability_active_release_pointer", "target_authority_id": "scenario-c2-test-authority", "canonical_profile_binding": pointer_binding, "release_id": release["release_id"], "release_digest": release["release_digest"], "release_epoch": 1, "release_sequence": 1, "release_history_digest": history["release_history_digest"], "predecessor_pointer_history_digest": None, "predecessor_active_pointer_digest": None, "pointer_sequence": 1, "published_at": "2026-07-30T00:00:02Z", "signer_coordinate": pointer_signer}
    manifest_body = {
        "generation_id": "scenario-c2-G1",
        "issuance_purpose": "semantic_ingestion_traceability_approval_generation",
        "canonical_profile_binding": generation_binding,
        "design_document_digest": design_digest,
        "registry_source_identity": roots["registry_source_identity"],
        "members": members,
        "active_pointer_intent": intent,
    }
    generation_digest = sha(
        b"memorii:sia-traceability-approval-generation:v1\0"
        + canonical(typed(manifest_body))
    )
    manifest = {**manifest_body, "signer_coordinate": signer, "generation_manifest_digest": generation_digest}
    manifest["signature"] = _signature(bootstrap_key, canonical(typed({"issuance_purpose": manifest_body["issuance_purpose"], "body_binding": generation_binding, "generation_manifest_digest": generation_digest, "signer_coordinate": signer}))).hex()
    generation = artifact(manifest, generation_binding)[0]
    closure = []
    for coordinate, data in sorted(blobs.items()):
        closure.append(
            {
                "coordinate": coordinate,
                "kind": "registered_generation_member",
                "name": coordinate.rsplit("/", 2)[-2],
                "digest": sha(data),
                "bytes_base64": base64.b64encode(data).decode(),
                "dependencies": [],
            }
        )
    closure.append(
        {
            "coordinate": "scenario-c2/m2/generation_manifest",
            "kind": "approval_generation_manifest",
            "name": "G1",
            "digest": sha(generation),
            "bytes_base64": base64.b64encode(generation).decode(),
            "dependencies": [item["coordinate"] for item in closure],
        }
    )
    return generation, closure


def lp(value: bytes) -> bytes:
    return len(value).to_bytes(8, "big") + value


def typed(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return {"$type": "integer", "value": str(value)}
    if isinstance(value, bytes):
        return {"$type": "bytes", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, list):
        return {"$type": "list", "items": [typed(item) for item in value]}
    if isinstance(value, tuple):
        return {"$type": "tuple", "items": [typed(item) for item in value]}
    if isinstance(value, dict):
        return {
            "$type": "map",
            "entries": [[key, typed(value[key])] for key in sorted(value)],
        }
    raise ValueError("unsupported CTV value")


def content_digest(content: bytes) -> str:
    return sha(
        b"memorii:sia-canonical-content:v1\0"
        + lp(CONTENT_SCHEMA.encode())
        + lp(b"1")
        + lp(CONTENT_MEDIA_TYPE.encode())
        + lp(CONTENT_PROFILE.encode())
        + lp(content)
    )


def tool_pins() -> dict[str, str]:
    paths = {
        "checker": Path(__file__).with_name("validate_scenario_first.py"),
        "extractor": ROOT
        / "memorii"
        / "memorii"
        / "core"
        / "memory_evolution"
        / "extraction.py",
        "ingress_runner": Path(__file__).with_name("run_scenario_ingress.py"),
        "provider_composition": ROOT
        / "memorii"
        / "memorii"
        / "core"
        / "provider"
        / "service.py",
        "renderer": Path(__file__).with_name("validate_scenario_first.py"),
    }
    return {name: sha(path.read_bytes()) for name, path in sorted(paths.items())}


def binding(authority: bytes) -> dict[str, Any]:
    source = json.loads(authority)
    profile = source["profile"]
    schema = [
        item for item in source["schemas"] if item["coordinate"] == FIXTURE_SCHEMA
    ]
    if (
        len(schema) != 1
        or profile["id"] != PROFILE_ID
        or profile["version"] != PROFILE_VERSION
    ):
        raise ValueError("registered CTV fixture binding is unavailable")
    return {
        "profile_id": profile["id"],
        "profile_version": profile["version"],
        "profile_digest": profile["digest"],
        "schema_id": FIXTURE_SCHEMA,
        "schema_version": 1,
        "binding_digest": schema[0]["binding_digest"],
    }


def validate_run(
    run: dict[str, Any],
    scenario: bytes,
    design: bytes,
    registry: bytes,
    authority: bytes,
) -> None:
    expected = {
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
    if set(run) != expected or run["format"] != "memorii-sia-scenario-ingress-run-v2":
        raise ValueError("scenario run shape")
    if (
        run["projection_policy"] != "scenario_semantic_persisted_projection"
        or run["projection_version"] != 1
    ):
        raise ValueError("scenario run projection policy")
    if (
        run["scenario_sha256"],
        run["design_sha256"],
        run["registry_sha256"],
        run["ctv_authority_sha256"],
    ) != (sha(scenario), sha(design), sha(registry), sha(authority)):
        raise ValueError("scenario run raw pin")
    if run["tool_pins"] != tool_pins() or run["oracle_spy_observation_count"] != len(
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
        ] or item["comparator_result"] not in {"match", "ambiguous", "abstain"}:
            raise ValueError("scenario run semantic evidence")


def artifact(body: dict[str, Any], schema_binding: dict[str, Any]) -> tuple[bytes, str]:
    body_bytes = canonical(typed(body))
    preimage = b"".join(
        [
            lp(ARTIFACT_DOMAIN),
            lp(schema_binding["profile_id"].encode()),
            lp(str(schema_binding["profile_version"]).encode()),
            lp(schema_binding["profile_digest"].encode()),
            lp(schema_binding["schema_id"].encode()),
            lp(str(schema_binding["schema_version"]).encode()),
            lp(schema_binding["binding_digest"].encode()),
            lp(body_bytes),
        ]
    )
    artifact_digest = sha(preimage)
    return canonical(
        typed({
            "binding": schema_binding,
            "canonical_value_bytes": body_bytes,
            "canonical_value_digest": sha(body_bytes),
            "artifact_digest": artifact_digest,
        })
    ), artifact_digest


def raw_member(name: str, data: bytes, ordinal: int) -> dict[str, Any]:
    return {
        "coordinate": f"scenario-c2/m1/{ordinal:02d}/{name}",
        "kind": "raw_input",
        "name": name,
        "digest": sha(data),
        "bytes_base64": base64.b64encode(data).decode("ascii"),
        "dependencies": [],
    }


def elaborate(
    scenario: bytes, run_bytes: bytes, design: bytes, registry: bytes, spool: Path
) -> dict[str, Any]:
    authority = AUTHORITY.read_bytes()
    run = json.loads(run_bytes)
    validate_run(run, scenario, design, registry, authority)
    schema_binding = binding(authority)
    evidence = {
        "scenario_sha256": sha(scenario),
        "run_sha256": sha(run_bytes),
        "tool_pins": run["tool_pins"],
        "runs": run["runs"],
        "stable_evidence": run["stable_evidence"],
    }
    content = canonical(evidence)
    body = {
        "fixture_id": "scenario-first-fixture-35",
        "owner": "acceptance_independent_vector_author",
        "target_artifact_kind": "golden_typed_input_fixture",
        "target_schema_id": CONTENT_SCHEMA,
        "target_schema_version": 1,
        "target_body_binding": schema_binding,
        "typed_input_value": {
            "content_schema_id": CONTENT_SCHEMA,
            "content_schema_version": 1,
            "media_type": CONTENT_MEDIA_TYPE,
            "canonical_profile_id": CONTENT_PROFILE,
            "content_bytes": content,
            "content_size": len(content),
            "content_digest": content_digest(content),
        },
    }
    envelope, artifact_digest = artifact(body, schema_binding)
    raw = [
        ("scenario", scenario),
        ("public_ingress_run", run_bytes),
        ("design", design),
        ("registry", registry),
        ("ctv_binding_authority", authority),
        *[
            (f"tool_{name}", digest.encode("ascii"))
            for name, digest in sorted(tool_pins().items())
        ],
    ]
    members = [
        raw_member(name, data, index) for index, (name, data) in enumerate(raw, 1)
    ]
    members.append(
        {
            "coordinate": f"scenario-c2/m1/{len(members) + 1:02d}/fixture_35_golden_typed_input",
            "kind": "golden_typed_input_fixture",
            "name": "fixture_35",
            "schema_id": FIXTURE_SCHEMA,
            "schema_version": 1,
            "binding": schema_binding,
            "digest": artifact_digest,
            "bytes_base64": base64.b64encode(envelope).decode("ascii"),
            "dependencies": [member["coordinate"] for member in members],
        }
    )
    _generation, closure = _build_registered_closure(
        design, registry, authority, LEDGER.read_bytes()
    )
    spool.write_bytes(canonical({"generation_members": closure}) + b"\n")
    return {
        "format": FORMAT,
        "milestone": 2,
        "profile": PROFILE_ID,
        "profile_version": PROFILE_VERSION,
        "spool_digest": sha(spool.read_bytes()),
        "members": members,
        "registered_closure": closure,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", type=Path)
    parser.add_argument("run", type=Path)
    parser.add_argument("design", type=Path)
    parser.add_argument("registry", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_bytes(
        canonical(
            elaborate(
                args.scenario.read_bytes(),
                args.run.read_bytes(),
                args.design.read_bytes(),
                args.registry.read_bytes(),
                args.output.with_suffix(".structural.spool"),
            )
        )
        + b"\n"
    )


if __name__ == "__main__":
    main()
