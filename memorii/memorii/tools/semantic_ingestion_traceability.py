"""Closed structural parser for the revision-3 traceability grammar."""

from __future__ import annotations

import ast
import json
import re
import unicodedata
from dataclasses import dataclass
from hashlib import sha256

GRAMMAR_REVISION = "sia-traceability-v1"
_HEADING = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
_LIST = re.compile(r"^(\s*)(?:[-*+] |\d+[.)] )(.+)$")
_TABLE = re.compile(r"^\s*\|.*\|\s*$")


class TraceabilityStructureError(ValueError):
    """The frozen document contains syntax outside the closed grammar."""


@dataclass(frozen=True)
class NormativeUnit:
    invariant_id: str
    content_key: str
    duplicate_occurrence: int
    unit_kind: str
    parent_invariant_id: str | None
    heading_path_hash: str
    source_start_line: int
    source_end_line: int
    canonical_payload_digest: str


@dataclass(frozen=True)
class UnitRequirementMapping:
    invariant_id: str
    content_key: str
    requirement_id: str
    owner: str
    assertion_id: str
    assertion_version: int
    test_evidence_group: str


def _digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(b"semantic-ingestion-traceability\0" + raw).hexdigest()


def _prepare(lines: list[str]) -> str:
    return "\n".join(unicodedata.normalize("NFC", item.rstrip(" \t")) for item in lines)


def _window(document_bytes: bytes) -> tuple[list[str], int]:
    try:
        lines = document_bytes.decode("utf-8", "strict").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    except UnicodeDecodeError as exc:
        raise TraceabilityStructureError("design bytes must be valid UTF-8") from exc
    starts = [index for index, line in enumerate(lines) if line.startswith("## 1.")]
    if len(starts) != 1:
        raise TraceabilityStructureError("design must contain exactly one Section 1 heading")
    end_five = next((index for index in range(starts[0], len(lines)) if lines[index].startswith("## 5.")), None)
    if end_five is None:
        raise TraceabilityStructureError("design must contain a Section 5 heading")
    stop = next((index for index in range(end_five + 1, len(lines)) if lines[index].startswith("## ")), len(lines))
    return lines[starts[0] : stop], starts[0] + 1


def _schema_units(body: list[str]) -> list[tuple[str, str, int]]:
    """Use Python's grammar for declarations, while retaining every other line."""
    source = "\n".join(body)
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise TraceabilityStructureError("unclassifiable Python schema fence") from exc

    def union_leaves(value: ast.expr) -> tuple[ast.expr, ...]:
        if isinstance(value, ast.BinOp) and isinstance(value.op, ast.BitOr):
            return union_leaves(value.left) + union_leaves(value.right)
        return (value,)

    seen: set[int] = set()
    out: list[tuple[str, str, int]] = []
    for node in tree.body:
        if not isinstance(node, (ast.ClassDef, ast.Assign, ast.AnnAssign)):
            continue
        if isinstance(node, ast.ClassDef):
            out.append(("schema_declaration", ast.get_source_segment(source, node) or node.name, node.lineno - 1))
            seen.add(node.lineno - 1)
            for member in node.body:
                if isinstance(member, ast.AnnAssign) and isinstance(member.target, ast.Name):
                    rendered = ast.get_source_segment(source, member) or member.target.id
                    out.append(("schema_field", rendered, member.lineno - 1))
                    seen.add(member.lineno - 1)
                    annotation = ast.unparse(member.annotation)
                    if "|" in annotation or "Union[" in annotation:
                        out.extend(
                            ("schema_union_member", ast.unparse(value), member.lineno - 1)
                            for value in union_leaves(member.annotation)
                        )
        else:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                name = node.target.id
            else:
                name = ""
            out.append(("schema_declaration", ast.get_source_segment(source, node) or name, node.lineno - 1))
            seen.add(node.lineno - 1)
            value = getattr(node, "value", None)
            if value is not None and ("|" in (ast.unparse(value)) or "Union[" in ast.unparse(value)):
                out.extend(("schema_union_member", ast.unparse(part), node.lineno - 1) for part in union_leaves(value))
    out.extend(("code_line", line, index) for index, line in enumerate(body) if line.strip() and index not in seen)
    return out


def extract_normative_units(document_bytes: bytes) -> tuple[NormativeUnit, ...]:
    lines, offset = _window(document_bytes)
    raw: list[tuple[str, str, str | None, str, int, int, tuple[str, ...]]] = []
    # A heading path is a content identity, not an occurrence identity.  Keep
    # the raw emission index on the stack so repeated sibling/nested headings
    # retain their direct parent occurrence until final IDs are assigned.
    stack: list[tuple[int, str, int]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        match = _HEADING.match(line)
        if match:
            level, title = len(match.group(1)), match.group(2)
            while stack and stack[-1][0] >= level:
                stack.pop()
            path = tuple(item[1] for item in stack) + (title,)
            path_hash = _digest({"heading_path": path})
            heading_index = len(raw)
            raw.append(
                ("heading", title, f"@{stack[-1][2]}" if stack else None, path_hash, offset + index, offset + index, ())
            )
            stack.append((level, title, heading_index))
            index += 1
            continue
        parent = f"@{stack[-1][2]}" if stack else None
        path = _digest({"heading_path": tuple(item[1] for item in stack)}) if stack else _digest({"heading_path": ()})
        if line.startswith("```"):
            begin, language = index, line[3:].strip().lower()
            index += 1
            body: list[str] = []
            while index < len(lines) and not lines[index].startswith("```"):
                body.append(lines[index])
                index += 1
            if index == len(lines):
                raise TraceabilityStructureError(f"unclosed fence at line {offset + begin}")
            # Children belong to the fence, not merely its enclosing heading.
            # The temporary raw index is resolved to the emitted invariant ID
            # only after duplicate occurrences have been assigned.
            fence_index = len(raw)
            raw.append(("fence", f"{language}\n{_prepare(body)}", parent, path, offset + begin, offset + index, ()))
            if language in {"python", "py"}:
                children = _schema_units(body)
            elif language in {"mermaid", "diagram"}:
                children = []
                for position, value in enumerate(body):
                    folded = value.strip()
                    if not folded:
                        continue
                    children.append(
                        ("diagram_edge" if "-->" in folded or "---" in folded else "diagram_node", folded, position)
                    )
            else:
                children = [("code_line", value, position) for position, value in enumerate(body) if value.strip()]
            raw.extend(
                (kind, value, f"@{fence_index}", path, offset + begin + pos + 1, offset + begin + pos + 1, ())
                for kind, value, pos in children
            )
            index += 1
            continue
        if _TABLE.match(line):
            begin, rows = index, []
            while index < len(lines) and _TABLE.match(lines[index]):
                cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                if len(cells) < 2:
                    raise TraceabilityStructureError(f"malformed table at line {offset + index}")
                rows.append(lines[index])
                index += 1
            child_keys = tuple(
                _digest({"row": _prepare([row])})
                for row in rows
                if not all(cell and set(cell) <= {"-", ":"} for cell in row.strip().strip("|").split("|"))
            )
            table_index = len(raw)
            raw.append(("table", _prepare(rows), parent, path, offset + begin, offset + index - 1, child_keys))
            raw.extend(
                ("table_row", row, f"@{table_index}", path, offset + begin + pos, offset + begin + pos, ())
                for pos, row in enumerate(rows)
                if not all(
                    cell.strip() and set(cell.strip()) <= {"-", ":"} for cell in row.strip().strip("|").split("|")
                )
            )
            continue
        if _LIST.match(line):
            begin, items = index, []
            while index < len(lines) and (
                not lines[index].strip() or _LIST.match(lines[index]) or lines[index].startswith((" ", "\t"))
            ):
                if _LIST.match(lines[index]):
                    item_start = index
                    item = [lines[index]]
                    index += 1
                    while index < len(lines) and lines[index].startswith((" ", "\t")) and not _LIST.match(lines[index]):
                        item.append(lines[index])
                        index += 1
                    items.append((item_start, item))
                else:
                    index += 1
            keys = tuple(_digest({"item": _prepare(value)}) for _, value in items)
            list_index = len(raw)
            raw.append(
                (
                    "list",
                    _prepare([value[0] for _, value in items]),
                    parent,
                    path,
                    offset + begin,
                    offset + index - 1,
                    keys,
                )
            )
            raw.extend(
                ("list_item", _prepare(value), f"@{list_index}", path, offset + start, offset + start + len(value) - 1, ())
                for start, value in items
            )
            continue
        if line.startswith((">", "---", "***")):
            raise TraceabilityStructureError(f"unknown Markdown block at line {offset + index}")
        begin, paragraph = index, []
        while (
            index < len(lines)
            and lines[index].strip()
            and not _HEADING.match(lines[index])
            and not lines[index].startswith("```")
            and not _TABLE.match(lines[index])
            and not _LIST.match(lines[index])
        ):
            paragraph.append(lines[index])
            index += 1
        raw.append(("paragraph", _prepare(paragraph), parent, path, offset + begin, offset + index - 1, ()))
    occurrences: dict[str, int] = {}
    provisional: list[tuple[str, str, int, str, str | None, str, int, int]] = []
    for kind, payload, parent, path, begin, end, children in raw:
        key = _digest({"grammar_revision": GRAMMAR_REVISION, "kind": kind, "payload": payload, "children": children})
        occurrence = occurrences.get(key, 0)
        occurrences[key] = occurrence + 1
        provisional.append((f"SIA-N-{key}-{occurrence}", key, occurrence, kind, parent, path, begin, end))
    units: list[NormativeUnit] = []
    for raw_index, (invariant_id, key, occurrence, kind, parent, path, begin, end) in enumerate(provisional):
        if parent is None:
            resolved_parent = None
        elif parent.startswith("@"):
            resolved_parent = provisional[int(parent[1:])][0]
        else:
            raise TraceabilityStructureError("unit parent must reference an emitted raw occurrence")
        units.append(NormativeUnit(invariant_id, key, occurrence, kind, resolved_parent, path, begin, end, _digest(raw[raw_index][1])))
    return tuple(units)
