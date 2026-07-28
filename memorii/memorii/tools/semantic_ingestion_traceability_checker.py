"""Independent structural and coverage checker (no generator imports)."""

from __future__ import annotations

import ast
import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any

_H = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
_L = re.compile(r"^(\s*)(?:[-*+] |\d+[.)] )")
_T = re.compile(r"^\s*\|.*\|\s*$")
_REV = "sia-traceability-v1"


class TraceabilityCoverageError(ValueError):
    pass


_REGISTRY_ROOTS = frozenset(
    {
        "anchor_bindings", "artifact_dag", "assertion_templates", "design_path", "format", "grammar_revision",
        "heading_defaults", "overrides", "registry_id", "report_schemas", "requirement_bindings",
        "runner_environment_profiles", "structural_rules", "test_evidence_groups",
    }
)


def _registry_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TraceabilityCoverageError("registry contains a duplicate JSON object key")
        result[key] = value
    return result


def _canonical(value: Any) -> bytes:
    """Independent canonical JSON encoder for the approval path.

    This intentionally does not call the registry loader or its serializer.
    """
    if value is None:
        return b"null"
    if value is True:
        return b"true"
    if value is False:
        return b"false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value).encode("ascii")
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value:
            raise TraceabilityCoverageError("registry string is not NFC")
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if isinstance(value, list):
        return b"[" + b",".join(_canonical(item) for item in value) + b"]"
    if isinstance(value, dict):
        return b"{" + b",".join(
            _canonical(key) + b":" + _canonical(value[key]) for key in sorted(value, key=lambda k: tuple(map(ord, k)))
        ) + b"}"
    raise TraceabilityCoverageError("registry has an unsupported JSON value")


def load_independent_registry_bytes(raw: bytes) -> dict[str, Any]:
    """Load the approval input directly from raw canonical registry bytes."""
    try:
        source = json.loads(raw.decode("utf-8"), object_pairs_hook=_registry_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TraceabilityCoverageError("registry bytes are not strict JSON") from exc
    if not isinstance(source, dict) or set(source) != _REGISTRY_ROOTS or raw != _canonical(source) + b"\n":
        raise TraceabilityCoverageError("registry bytes are not the complete canonical source")
    requirements = {f"SIA-R{number:02d}" for number in range(1, 24)}
    bindings = source["requirement_bindings"]
    defaults = source["heading_defaults"]
    groups = source["test_evidence_groups"]
    templates = source["assertion_templates"]
    if not all(isinstance(item, dict) for item in bindings + defaults + groups + templates):
        raise TraceabilityCoverageError("registry collections contain an invalid item")
    binding_ids = {item.get("requirement_id") for item in bindings}
    if binding_ids != requirements or len(bindings) != 23:
        raise TraceabilityCoverageError("registry does not bind exactly R01 through R23")
    paths = [item.get("heading_path") for item in defaults]
    if len(defaults) != 144 or len(set(paths)) != 144 or any(not item.get("requirements") for item in defaults):
        raise TraceabilityCoverageError("registry does not contain exactly 144 nonempty unique defaults")
    template_ids = {item.get("template_id") for item in templates}
    group_ids = {item.get("group_id") for item in groups}
    if len(group_ids) != 23 or any(
        item.get("assertion_template_id") not in template_ids or item.get("test_evidence_group") not in group_ids
        for item in bindings
    ):
        raise TraceabilityCoverageError("registry has an unresolved assertion or evidence group")
    if [item.get("test_evidence_group") for item in bindings] != [item.get("group_id") for item in groups]:
        raise TraceabilityCoverageError("registry evidence group order differs from ordered bindings")
    schemas = source["report_schemas"]
    profiles = source["runner_environment_profiles"]
    if not all(isinstance(item, dict) for item in schemas + profiles):
        raise TraceabilityCoverageError("registry schema/profile collections contain an invalid item")
    schema_coordinates = [(item.get("schema_id"), item.get("schema_version")) for item in schemas]
    profile_coordinates = [(item.get("profile_id"), item.get("profile_version")) for item in profiles]
    if len(set(schema_coordinates)) != len(schemas) or len(set(profile_coordinates)) != len(profiles):
        raise TraceabilityCoverageError("registry schema/profile coordinates are duplicate")
    if any(not isinstance(item.get("schema_document"), dict) or item["schema_document"].get("additionalProperties") is not False for item in schemas):
        raise TraceabilityCoverageError("registry report schema is not closed")
    expected_profile_keys = {
        "canonical_profile_id", "configuration_policy", "dependency_policy", "environment_policy", "import_path_policy",
        "interpreter_policy", "locale_timezone_policy", "network_policy", "plugin_policy", "profile_id", "profile_version",
        "runner_policy", "startup_customization_policy",
    }
    if any(set(item) != expected_profile_keys for item in profiles):
        raise TraceabilityCoverageError("registry runner profile is not closed")
    schema_digests = [sha256(b"memorii:sia-report-schema:v1\0" + _canonical(item) + b"\n").hexdigest() for item in schemas]
    profile_digests = [sha256(b"memorii:sia-runner-environment-profile:v1\0" + _canonical(item) + b"\n").hexdigest() for item in profiles]
    for group in groups:
        schema_coordinate = (group.get("report_schema_id"), group.get("report_schema_version"))
        profile_coordinate = (group.get("runner_environment_profile_id"), group.get("runner_environment_profile_version"))
        if (
            not group.get("selected_tests")
            or schema_coordinate not in schema_coordinates
            or profile_coordinate not in profile_coordinates
            or group.get("expected_report_schema_digest") != schema_digests[schema_coordinates.index(schema_coordinate)]
            or group.get("expected_runner_environment_profile_digest") != profile_digests[profile_coordinates.index(profile_coordinate)]
        ):
            raise TraceabilityCoverageError("registry evidence group is incomplete")
    nodes = source["artifact_dag"]
    node_ids = [item.get("node_id") for item in nodes if isinstance(item, dict)]
    if len(nodes) != 13 or len(node_ids) != 13 or len(set(node_ids)) != 13:
        raise TraceabilityCoverageError("registry artifact DAG is incomplete")
    seen: set[str] = set()
    for node in nodes:
        deps = node.get("depends_on")
        if not isinstance(deps, list) or any(dep not in seen for dep in deps):
            raise TraceabilityCoverageError("registry artifact DAG is unordered or cyclic")
        seen.add(node["node_id"])
    return source


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


def _d(v: object) -> str:
    return sha256(
        b"semantic-ingestion-traceability\0"
        + json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _p(v: list[str]) -> str:
    return "\n".join(unicodedata.normalize("NFC", x.rstrip(" \t")) for x in v)


def _schema(body: list[str]) -> list[tuple[str, str, int]]:
    try:
        tree = ast.parse("\n".join(body))
    except SyntaxError as exc:
        raise TraceabilityCoverageError("unclassifiable Python schema fence") from exc

    def leaves(v: ast.expr) -> tuple[ast.expr, ...]:
        return leaves(v.left) + leaves(v.right) if isinstance(v, ast.BinOp) and isinstance(v.op, ast.BitOr) else (v,)

    output = []
    seen = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            output.append(
                ("schema_declaration", ast.get_source_segment("\n".join(body), node) or node.name, node.lineno - 1)
            )
            seen.add(node.lineno - 1)
            for m in node.body:
                if isinstance(m, ast.AnnAssign) and isinstance(m.target, ast.Name):
                    output.append(
                        ("schema_field", ast.get_source_segment("\n".join(body), m) or m.target.id, m.lineno - 1)
                    )
                    seen.add(m.lineno - 1)
                    if "|" in ast.unparse(m.annotation) or "Union[" in ast.unparse(m.annotation):
                        output.extend(
                            ("schema_union_member", ast.unparse(x), m.lineno - 1) for x in leaves(m.annotation)
                        )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            output.append(("schema_declaration", ast.get_source_segment("\n".join(body), node) or "", node.lineno - 1))
            seen.add(node.lineno - 1)
            value = getattr(node, "value", None)
            if value is not None and ("|" in ast.unparse(value) or "Union[" in ast.unparse(value)):
                output.extend(("schema_union_member", ast.unparse(x), node.lineno - 1) for x in leaves(value))
    return output + [("code_line", x, i) for i, x in enumerate(body) if x.strip() and i not in seen]


def _independent_extract(data: bytes) -> tuple[_Unit, ...]:
    try:
        all_lines = data.decode("utf-8", "strict").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    except UnicodeDecodeError as exc:
        raise TraceabilityCoverageError("design bytes must be valid UTF-8") from exc
    starts = [i for i, x in enumerate(all_lines) if x.startswith("## 1.")]
    if len(starts) != 1:
        raise TraceabilityCoverageError("design must contain exactly one Section 1 heading")
    five = next((i for i in range(starts[0], len(all_lines)) if all_lines[i].startswith("## 5.")), None)
    if five is None:
        raise TraceabilityCoverageError("design must contain a Section 5 heading")
    stop = next((i for i in range(five + 1, len(all_lines)) if all_lines[i].startswith("## ")), len(all_lines))
    lines = all_lines[starts[0] : stop]
    offset = starts[0] + 1
    raw = []
    # Do not use the hash of a heading path as an occurrence key: repeated
    # headings are legal and children must bind to the emitted parent instance.
    stack: list[tuple[int, str, int]] = []
    i = 0
    while i < len(lines):
        x = lines[i]
        if not x.strip():
            i += 1
            continue
        m = _H.match(x)
        if m:
            level, title = len(m.group(1)), m.group(2)
            while stack and stack[-1][0] >= level:
                stack.pop()
            path = _d({"heading_path": tuple(q[1] for q in stack) + (title,)})
            heading_index = len(raw)
            raw.append(("heading", title, f"@{stack[-1][2]}" if stack else None, path, offset + i, offset + i, ()))
            stack.append((level, title, heading_index))
            i += 1
            continue
        parent = f"@{stack[-1][2]}" if stack else None
        path = _d({"heading_path": tuple(q[1] for q in stack)}) if stack else _d({"heading_path": ()})
        if x.startswith("```"):
            begin = i
            lang = x[3:].strip().lower()
            i += 1
            body = []
            while i < len(lines) and not lines[i].startswith("```"):
                body.append(lines[i])
                i += 1
            if i == len(lines):
                raise TraceabilityCoverageError("unclosed fence")
            fence_index = len(raw)
            raw.append(("fence", f"{lang}\n{_p(body)}", parent, path, offset + begin, offset + i, ()))
            children = (
                _schema(body)
                if lang in {"python", "py"}
                else [
                    ("diagram_edge" if "-->" in z.strip() or "---" in z.strip() else "diagram_node", z.strip(), j)
                    for j, z in enumerate(body)
                    if z.strip()
                ]
                if lang in {"mermaid", "diagram"}
                else [("code_line", z, j) for j, z in enumerate(body) if z.strip()]
            )
            raw.extend((k, v, f"@{fence_index}", path, offset + begin + j + 1, offset + begin + j + 1, ()) for k, v, j in children)
            i += 1
            continue
        if _T.match(x):
            begin = i
            rows = []
            while i < len(lines) and _T.match(lines[i]):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if len(cells) < 2:
                    raise TraceabilityCoverageError("malformed table")
                rows.append(lines[i])
                i += 1
            child_rows = [
                r for r in rows if not all(c and set(c) <= {"-", ":"} for c in r.strip().strip("|").split("|"))
            ]
            visible_rows = [
                r
                for r in rows
                if not all(c.strip() and set(c.strip()) <= {"-", ":"} for c in r.strip().strip("|").split("|"))
            ]
            table_index = len(raw)
            raw.append(
                (
                    "table",
                    _p(rows),
                    parent,
                    path,
                    offset + begin,
                    offset + i - 1,
                    tuple(_d({"row": _p([r])}) for r in child_rows),
                )
            )
            raw.extend(
                ("table_row", r, f"@{table_index}", path, offset + begin + j, offset + begin + j, ())
                for j, r in enumerate(rows)
                if r in visible_rows
            )
            continue
        if _L.match(x):
            begin = i
            items = []
            while i < len(lines) and (not lines[i].strip() or _L.match(lines[i]) or lines[i].startswith((" ", "\t"))):
                if _L.match(lines[i]):
                    s = i
                    item = [lines[i]]
                    i += 1
                    while i < len(lines) and lines[i].startswith((" ", "\t")) and not _L.match(lines[i]):
                        item.append(lines[i])
                        i += 1
                    items.append((s, item))
                else:
                    i += 1
            list_index = len(raw)
            raw.append(
                (
                    "list",
                    _p([v[0] for _, v in items]),
                    parent,
                    path,
                    offset + begin,
                    offset + i - 1,
                    tuple(_d({"item": _p(v)}) for _, v in items),
                )
            )
            raw.extend(("list_item", _p(v), f"@{list_index}", path, offset + s, offset + s + len(v) - 1, ()) for s, v in items)
            continue
        if x.startswith((">", "---", "***")):
            raise TraceabilityCoverageError("unknown Markdown block")
        begin = i
        p = []
        while (
            i < len(lines)
            and lines[i].strip()
            and not _H.match(lines[i])
            and not lines[i].startswith("```")
            and not _T.match(lines[i])
            and not _L.match(lines[i])
        ):
            p.append(lines[i])
            i += 1
        raw.append(("paragraph", _p(p), parent, path, offset + begin, offset + i - 1, ()))
    seen = {}
    provisional = []
    for k, v, parent, path, b, e, ch in raw:
        key = _d({"grammar_revision": _REV, "kind": k, "payload": v, "children": ch})
        n = seen.get(key, 0)
        seen[key] = n + 1
        provisional.append((f"SIA-N-{key}-{n}", key, n, k, parent, path, b, e, _d(v)))
    out = []
    for invariant_id, key, occurrence, kind, parent, path, begin, end, payload_digest in provisional:
        if parent is None:
            resolved_parent = None
        elif parent.startswith("@"):
            resolved_parent = provisional[int(parent[1:])][0]
        else:
            raise TraceabilityCoverageError("unit parent must reference an emitted raw occurrence")
        out.append(_Unit(invariant_id, key, occurrence, kind, resolved_parent, path, begin, end, payload_digest))
    return tuple(out)


def _shape(value: Any) -> tuple[Any, ...]:
    return tuple(getattr(value, n) for n in _Unit.__dataclass_fields__)


def verify_traceability_coverage(
    *,
    design_bytes: bytes,
    published_units: tuple[Any, ...],
    mappings: tuple[Any, ...],
    requirements_to_owners: dict[str, str],
) -> None:
    if tuple(_shape(x) for x in _independent_extract(design_bytes)) != tuple(_shape(x) for x in published_units):
        raise TraceabilityCoverageError("published structural units do not equal independent extraction")
    if not requirements_to_owners:
        raise TraceabilityCoverageError("requirement ledger cannot be empty")
    keys = {(x.invariant_id, x.content_key) for x in published_units}
    invariant_ids = {x.invariant_id for x in published_units}
    if any(x.parent_invariant_id is not None and x.parent_invariant_id not in invariant_ids for x in published_units):
        raise TraceabilityCoverageError("published unit has an unresolved structural parent")
    covered = {x.invariant_id: set() for x in published_units}
    seen = set()
    for m in mappings:
        if (m.invariant_id, m.content_key) not in keys:
            raise TraceabilityCoverageError("mapping refers to an orphaned unit or stale content key")
        if (m.invariant_id, m.requirement_id) in seen:
            raise TraceabilityCoverageError("duplicate unit-to-requirement mapping")
        seen.add((m.invariant_id, m.requirement_id))
        if requirements_to_owners.get(m.requirement_id) != m.owner:
            raise TraceabilityCoverageError("mapping owner differs from the requirement ledger")
        if m.assertion_version < 1 or not m.assertion_id or not m.test_evidence_group:
            raise TraceabilityCoverageError("mapping has an invalid assertion binding")
        covered[m.invariant_id].add(m.requirement_id)
    if any(not v for v in covered.values()):
        raise TraceabilityCoverageError("every structural unit requires explicit requirement coverage")


def rebuild_structural_manifest_bytes(*, design_bytes: bytes, registry: Any, registry_bytes: bytes | None = None) -> bytes:
    """Independently expand the registry and return the canonical manifest body.

    This deliberately accepts only canonical source artifacts and does not
    import the generator's parser, models, or mapping implementation.
    """
    # Approval callers must supply the canonical raw artifact.  The optional
    # object parameter only preserves the legacy non-approval helper surface.
    source = load_independent_registry_bytes(registry_bytes) if registry_bytes is not None else registry.source
    units = _independent_extract(design_bytes)
    try:
        lines = design_bytes.decode("utf-8", "strict").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    except UnicodeDecodeError as exc:
        raise TraceabilityCoverageError("design bytes must be valid UTF-8") from exc
    numbered = []
    for line_number, line in enumerate(lines, start=1):
        match = re.match(r"^(#{2,6})\s+(\d+(?:\.\d+)*)[.\s]", line)
        if match:
            numbered.append((line_number, match.group(2)))
    defaults = {item["heading_path"]: tuple(item["requirements"]) for item in source["heading_defaults"]}
    bindings = {item["requirement_id"]: item for item in source["requirement_bindings"]}
    overrides = {item["invariant_id"]: item for item in source["overrides"]}
    rendered = design_bytes.decode("utf-8", "strict")
    for anchor in source["anchor_bindings"]:
        if rendered.count(f"[{anchor['anchor']}]") != 1:
            raise TraceabilityCoverageError("registry anchor is dangling or duplicated")
    mappings: list[dict[str, Any]] = []
    for unit in units:
        candidates = [path for line, path in numbered if line <= unit.source_start_line]
        if not candidates:
            raise TraceabilityCoverageError("unit has no numeric heading")
        heading_path = candidates[-1]
        requirements = set(defaults.get(heading_path, ()))
        if not requirements:
            raise TraceabilityCoverageError("unit has no registered heading default")
        sources = [f"heading-default:{heading_path}"]
        for rule in source["structural_rules"]:
            if rule["heading_path"] != heading_path or rule["selector_kind"] != "named_table_rows" or unit.unit_kind != "table_row":
                continue
            row = next((line for line in lines[unit.source_start_line - 1 : unit.source_end_line] if line.lstrip().startswith("|")), "")
            cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
            for requirement in rule["selector_values"]:
                if requirement in cells:
                    requirements.add(requirement)
                    sources.append(f"rule:{rule['rule_id']}:{requirement}")
        override = overrides.get(unit.invariant_id)
        if override:
            requirements.update(override["added_requirements"])
            sources.append(f"override:{unit.invariant_id}")
        for requirement in sorted(requirements, key=lambda item: int(item.rsplit("R", 1)[1])):
            binding = bindings.get(requirement)
            if binding is None:
                raise TraceabilityCoverageError("mapping refers to an unregistered requirement")
            mappings.append({
                "invariant_id": unit.invariant_id,
                "content_key": unit.content_key,
                "requirement_id": requirement,
                "assertion_template_id": binding["assertion_template_id"],
                "assertion_version": binding["assertion_version"],
                "test_evidence_group": binding["test_evidence_group"],
                "mapping_sources": sources,
            })
    if registry_bytes is None:
        root_digests = registry.root_digests
    else:
        root_digests = {
            key: sha256(
                b"memorii:sia-traceability-registry-root:" + key.encode() + b":v1\0" + _canonical(source[key])
            ).hexdigest()
            for key in _REGISTRY_ROOTS - {"design_path", "format", "grammar_revision", "registry_id", "report_schemas", "runner_environment_profiles"}
        }
        root_digests["report_schemas"] = sha256(
            b"memorii:sia-report-schema-registry:v1\0" + _canonical([
                sha256(b"memorii:sia-report-schema:v1\0" + _canonical(item) + b"\n").hexdigest()
                for item in source["report_schemas"]
            ]) + b"\n"
        ).hexdigest()
        root_digests["runner_environment_profiles"] = sha256(
            b"memorii:sia-runner-environment-profile-registry:v1\0" + _canonical([
                sha256(b"memorii:sia-runner-environment-profile:v1\0" + _canonical(item) + b"\n").hexdigest()
                for item in source["runner_environment_profiles"]
            ]) + b"\n"
        ).hexdigest()
    body = {
        "design_document_digest": sha256(design_bytes).hexdigest(),
        "registry_source_identity": sha256(b"memorii:sia-traceability-source:v1\0" + (registry_bytes if registry_bytes is not None else registry.canonical_bytes)).hexdigest(),
        "grammar_revision": source["grammar_revision"],
        "registry_root_digests": [list(item) for item in sorted(root_digests.items())],
        "units": [asdict(unit) for unit in units],
        "mappings": mappings,
    }
    return _canonical(body)


def verify_structural_manifest(*, design_bytes: bytes, registry: Any, published_manifest: Any) -> None:
    """Require the published manifest body to equal the independent rebuild."""
    expected = rebuild_structural_manifest_bytes(design_bytes=design_bytes, registry=registry)
    actual = getattr(published_manifest, "canonical_bytes", None)
    if not isinstance(actual, bytes) or actual != expected:
        raise TraceabilityCoverageError("published structural manifest differs from independent registry expansion")
    digest = sha256(b"memorii:sia-traceability-structural-manifest:v1\0" + actual).hexdigest()
    if getattr(published_manifest, "structural_manifest_digest", None) != digest:
        raise TraceabilityCoverageError("published structural manifest digest is invalid")


def design_digest(design_bytes: bytes) -> str:
    return sha256(design_bytes).hexdigest()
