"""Reject planning and evidence coordinates used as durable repository identities."""

from __future__ import annotations

import argparse
import ast
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_DELIMITED_IDENTIFIER_PATTERN = re.compile(
    r"(?:^|[._])(?:m\d+|r\d{2}|sia_[rt]\d+)(?:_|$)"
    r"|(?:^|_)(?:milestone|phase|review_round)_?\d+(?:_|$)"
    r"|^(?:m\d+|c2|r\d{2}|sia[rt]\d+)(?=[a-z_]|$)",
    re.IGNORECASE,
)
_CAMEL_IDENTIFIER_PATTERN = re.compile(
    r"(?<=[a-z])(?:M\d+|C2|R\d{2})(?=[A-Z]|$)"
    r"|(?:Scenario|SIA)C2(?=[A-Z]|$)"
)
_VALUE_PATTERN = re.compile(
    r"memorii\.m\d+\."
    r"|scenario[-_/]c2"
    r"|sia[-_]c2"
    r"|(?:^|[.:/_-])m\d+(?:$|[.:/_-])"
    r"|semantic-ingestion-r\d{2}(?:$|[.:/_-])"
    r"|pytest-sia-r\d{2}(?:$|[.:/_-])"
    r"|test_sia_r\d{2}(?:$|[.:/_-])"
    r"|(?:milestone|phase|review[-_ ]round)[-_/ ]?\d+"
    r"|\bSIA-(?:I\d+|T(?:\d+|-[A-Z0-9]+(?:-[A-Z0-9]+)*))\b"
    r"|\b(?:M\d+|C2|R\d{2}|SIA-R\d{2})\b",
    re.IGNORECASE,
)
_MARKDOWN_IDENTITY_VALUE_PATTERN = re.compile(
    r"(?:semantic-ingestion-r\d{2}|pytest-sia-r\d{2})(?:[-./_][a-z0-9]+)*",
    re.IGNORECASE,
)
_TRACEABILITY_FIELDS = {
    "approved_requirement_ids",
    "requirement_id",
    "requirement_ids",
    "requirements",
}
_PLANNING_FIELDS = {
    "milestone",
    "milestone_id",
    "milestone_name",
    "phase",
    "phase_id",
    "phase_name",
    "review_round",
    "review_round_id",
    "review_round_name",
}
_IDENTITY_FIELDS = {
    "admission_id",
    "command_id",
    "coordinate",
    "discriminator",
    "fingerprint",
    "format",
    "group_id",
    "id",
    "kind",
    "label",
    "member_id",
    "migration_plan_id",
    "name",
    "node_id",
    "operation_id",
    "owner",
    "pytest_node_id",
    "run",
    "schema",
    "schema_id",
    "type",
}
_EXCEPTION_CLASSES = {
    "legacy_rejection_vector",
    "shipped_migration_identity",
    "typed_traceability_metadata",
}
_CANONICAL_TRACEABILITY_CONSTRUCTORS = {
    "memorii.tools.semantic_ingestion_execution_evidence.ExecutionEvidenceRecord",
    "memorii.tools.semantic_ingestion_traceability.UnitRequirementMapping",
}
_CANONICAL_COMPATIBILITY_READERS = {
    "tests.fixtures.semantic_ingestion.provider_compatibility.legacy_reader.read_outcome",
    "tests.fixtures.semantic_ingestion.provider_compatibility.legacy_reader.read_sync",
}
_DYNAMIC_BINDING_NAMES = {
    "__builtins__",
    # Keep the detector's own static vocabulary from being mistaken for a
    # production dynamic-import capability by the architecture guard.
    "__" + "import__",
    "delattr",
    "eval",
    "exec",
    "getattr",
    "globals",
    "locals",
    "setattr",
    "vars",
}


@dataclass(frozen=True, order=True)
class IdentityViolation:
    path: str
    location: str
    value: str
    reason: str


@dataclass(frozen=True)
class _Exception:
    path: str
    location: str
    value: str
    classification: str
    proof: str
    rationale: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.path, self.location, self.value)


def _is_identity_field(field: str) -> bool:
    lowered = field.lower()
    return lowered not in _TRACEABILITY_FIELDS and (
        lowered in _IDENTITY_FIELDS
        or lowered.endswith(
            ("_discriminator", "_fingerprint", "_format", "_id", "_ids", "_kind", "_label", "_name")
        )
    )


def _planning_identifier(value: str) -> bool:
    return any(
        pattern.search(value) is not None
        for pattern in (_DELIMITED_IDENTIFIER_PATTERN, _CAMEL_IDENTIFIER_PATTERN, _VALUE_PATTERN)
    )


def _planning_value(value: str) -> bool:
    return (
        _VALUE_PATTERN.search(value) is not None
        or _CAMEL_IDENTIFIER_PATTERN.search(value) is not None
    )


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _proof_import_bindings(tree: ast.AST) -> dict[str, str]:
    if not isinstance(tree, ast.Module):
        return {}
    if any(
        (isinstance(node, ast.Name) and node.id in _DYNAMIC_BINDING_NAMES)
        or (isinstance(node, ast.Attribute) and node.attr in _DYNAMIC_BINDING_NAMES)
        or (
            isinstance(node, ast.ImportFrom)
            and any(alias.name in _DYNAMIC_BINDING_NAMES for alias in node.names)
        )
        for node in ast.walk(tree)
    ):
        return {}
    if any(
        isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names)
        for node in ast.walk(tree)
    ):
        return {}
    bindings: dict[str, str] = {}
    import_binding_counts: dict[str, int] = {}
    module_import_ids = {
        id(node) for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
    }
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            for alias in node.names:
                if alias.name != "*":
                    local_name = alias.asname or alias.name
                    bindings[local_name] = f"{node.module}.{alias.name}"
                    import_binding_counts[local_name] = import_binding_counts.get(local_name, 0) + 1
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname is not None:
                    local_name, owner = alias.asname, alias.name
                else:
                    local_name = owner = alias.name.split(".")[0]
                bindings[local_name] = owner
                import_binding_counts[local_name] = import_binding_counts.get(local_name, 0) + 1

    binding_counts = dict(import_binding_counts)
    for node in ast.walk(tree):
        names: tuple[str, ...] = ()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = (node.name,)
        elif isinstance(node, ast.arg):
            names = (node.arg,)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names = (node.id,)
        elif isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)) and isinstance(
            node.name, str
        ):
            names = (node.name,)
        elif isinstance(node, ast.MatchMapping) and node.rest is not None:
            names = (node.rest,)
        elif isinstance(node, ast.ImportFrom) and id(node) not in module_import_ids:
            names = tuple(alias.asname or alias.name for alias in node.names if alias.name != "*")
        elif isinstance(node, ast.Import) and id(node) not in module_import_ids:
            names = tuple(alias.asname or alias.name.split(".")[0] for alias in node.names)
        for name in names:
            binding_counts[name] = binding_counts.get(name, 0) + 1

    return {
        name: owner
        for name, owner in bindings.items()
        if import_binding_counts[name] == 1 and binding_counts[name] == 1
    }


def _qualified_call_owner(call: ast.Call, bindings: dict[str, str]) -> str | None:
    if isinstance(call.func, ast.Name):
        return bindings.get(call.func.id)
    return None


def _static_text(
    node: ast.AST, resolve_name: Callable[[str], str | None] | None = None
) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _static_text(node.left, resolve_name)
        right = _static_text(node.right, resolve_name)
        return None if left is None or right is None else left + right
    if isinstance(node, ast.Name) and resolve_name is not None:
        return resolve_name(node.id)
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                parts.append(_static_text(value.value, resolve_name) or "<dynamic>")
            else:
                parts.append("<dynamic>")
        return "".join(parts)
    return None


def _string_nodes(
    node: ast.AST, resolve_name: Callable[[str], str | None] | None = None
) -> list[tuple[ast.AST, str]]:
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [
            pair
            for item in node.elts
            if (pair := _static_text_pair(item, resolve_name)) is not None
        ]
    pair = _static_text_pair(node, resolve_name)
    return [] if pair is None else [pair]


def _static_text_pair(
    node: ast.AST, resolve_name: Callable[[str], str | None] | None = None
) -> tuple[ast.AST, str] | None:
    value = _static_text(node, resolve_name)
    return None if value is None else (node, value)


class _PythonIdentityVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.violations: list[IdentityViolation] = []
        self._constant_scopes: list[dict[str, str | int]] = [{}]
        self._enum_depth = 0

    def _resolve_constant(self, name: str) -> str | int | None:
        for scope in reversed(self._constant_scopes):
            if name in scope:
                return scope[name]
        return None

    def _resolve_name(self, name: str) -> str | None:
        value = self._resolve_constant(name)
        return value if isinstance(value, str) else None

    def _remember_constant(self, target: ast.AST, value: ast.AST) -> None:
        if not isinstance(target, ast.Name):
            return
        resolved: str | int | None
        if isinstance(value, ast.Constant) and type(value.value) is int:
            resolved = value.value
        else:
            resolved = _static_text(value, self._resolve_name)
        if resolved is None:
            self._constant_scopes[-1].pop(target.id, None)
        else:
            self._constant_scopes[-1][target.id] = resolved

    def _planning_field_coordinate(self, field: str, value: ast.AST) -> bool:
        if field.lower() not in _PLANNING_FIELDS:
            return False
        if isinstance(value, ast.Constant) and type(value.value) is int:
            return True
        if isinstance(value, ast.Name) and type(self._resolve_constant(value.id)) is int:
            return True
        text = _static_text(value, self._resolve_name)
        return text is not None and (text.isdigit() or _planning_value(text))

    def _identifier(self, value: str, node: ast.AST) -> None:
        if _planning_identifier(value):
            self.violations.append(
                IdentityViolation(
                    self.path,
                    f"python:identifier:{getattr(node, 'lineno', 0)}:{getattr(node, 'col_offset', 0)}",
                    value,
                    "planning/evidence coordinate used in Python identifier",
                )
            )

    def _field_value(self, field: str, value: ast.AST, *, force_identity: bool = False) -> None:
        lowered = field.lower()
        if self._planning_field_coordinate(field, value):
            self.violations.append(
                IdentityViolation(
                    self.path,
                    f"python:field:{field}:{getattr(value, 'lineno', 0)}:{getattr(value, 'col_offset', 0)}",
                    _static_text(value, self._resolve_name) or ast.unparse(value),
                    "planning/evidence coordinate used as durable field",
                )
            )
            return
        if (
            not force_identity
            and lowered not in _TRACEABILITY_FIELDS
            and not _is_identity_field(field)
        ):
            return
        for item, text in _string_nodes(value, self._resolve_name):
            if _planning_value(text):
                self.violations.append(
                    IdentityViolation(
                        self.path,
                        f"python:field:{field}:{getattr(item, 'lineno', 0)}:{getattr(item, 'col_offset', 0)}",
                        text,
                        "planning/evidence coordinate used in identity-bearing field",
                    )
                )

    def _diagnostic_values(self, node: ast.Call) -> None:
        name = _call_name(node)
        if not (
            name.endswith(("Error", "Exception"))
            or name
            in {
                "critical",
                "debug",
                "echo",
                "error",
                "exception",
                "exit",
                "fail",
                "info",
                "log",
                "print",
                "warn",
                "warning",
                "write",
            }
        ):
            return
        for argument in node.args:
            for item, text in _string_nodes(argument, self._resolve_name):
                if _planning_value(text):
                    self.violations.append(
                        IdentityViolation(
                            self.path,
                            f"python:diagnostic:{getattr(item, 'lineno', 0)}:{getattr(item, 'col_offset', 0)}",
                            text,
                            "planning/evidence coordinate used in runtime diagnostic",
                        )
                    )
        for keyword in node.keywords:
            for item, text in _string_nodes(keyword.value, self._resolve_name):
                if _planning_value(text):
                    self.violations.append(
                        IdentityViolation(
                            self.path,
                            f"python:diagnostic:{getattr(item, 'lineno', 0)}:{getattr(item, 'col_offset', 0)}",
                            text,
                            "planning/evidence coordinate used in runtime diagnostic",
                        )
                    )

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._identifier(node.name, node)
        for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
            self._identifier(argument.arg, argument)
        if node.args.vararg is not None:
            self._identifier(node.args.vararg.arg, node.args.vararg)
        if node.args.kwarg is not None:
            self._identifier(node.args.kwarg.arg, node.args.kwarg)
        self._constant_scopes.append({})
        self.generic_visit(node)
        self._constant_scopes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._identifier(node.name, node)
        is_enum = any(
            (isinstance(base, ast.Name) and base.id.endswith("Enum"))
            or (isinstance(base, ast.Attribute) and base.attr.endswith("Enum"))
            for base in node.bases
        )
        self._constant_scopes.append({})
        self._enum_depth += int(is_enum)
        self.generic_visit(node)
        self._enum_depth -= int(is_enum)
        self._constant_scopes.pop()

    def visit_Name(self, node: ast.Name) -> None:
        self._identifier(node.id, node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self._identifier(node.attr, node)
        self.generic_visit(node)

    def visit_keyword(self, node: ast.keyword) -> None:
        if node.arg is not None:
            self._identifier(node.arg, node)
            self._field_value(node.arg, node.value)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                self._field_value(
                    target.id,
                    node.value,
                    force_identity=self._enum_depth > 0 and target.id.isupper(),
                )
            elif isinstance(target, ast.Attribute):
                self._field_value(target.attr, node.value)
            self._remember_constant(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            if isinstance(node.target, ast.Name):
                self._field_value(
                    node.target.id,
                    node.value,
                    force_identity=self._enum_depth > 0 and node.target.id.isupper(),
                )
            elif isinstance(node.target, ast.Attribute):
                self._field_value(node.target.attr, node.value)
            self._remember_constant(node.target, node.value)
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        for key, value in zip(node.keys, node.values, strict=True):
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                self._field_value(key.value, value)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if _planning_identifier(alias.name):
                self.violations.append(
                    IdentityViolation(
                        self.path,
                        f"python:import:{node.lineno}:{node.col_offset}",
                        alias.name,
                        "planning/evidence coordinate used in import path",
                    )
                )
            if alias.asname is not None:
                self._identifier(alias.asname, alias)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module is not None and _planning_identifier(node.module):
            self.violations.append(
                IdentityViolation(
                    self.path,
                    f"python:import:{node.lineno}:{node.col_offset}",
                    node.module,
                    "planning/evidence coordinate used in import path",
                )
            )
        for alias in node.names:
            if alias.name != "*":
                self._identifier(alias.name, alias)
            if alias.asname is not None:
                self._identifier(alias.asname, alias)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        for argument in node.args:
            for item, text in _string_nodes(argument, self._resolve_name):
                if re.fullmatch(r"SIA-(?:R\d{2}|T-[A-Z0-9-]+)", text):
                    self.violations.append(
                        IdentityViolation(
                            self.path,
                            f"python:traceability-positional:{getattr(item, 'lineno', 0)}:{getattr(item, 'col_offset', 0)}",
                            text,
                            "traceability coordinate must use an explicit typed field",
                        )
                    )
        self._diagnostic_values(node)
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        if node.msg is not None:
            for item, text in _string_nodes(node.msg, self._resolve_name):
                if _planning_value(text):
                    self.violations.append(
                        IdentityViolation(
                            self.path,
                            f"python:diagnostic:{getattr(item, 'lineno', 0)}:{getattr(item, 'col_offset', 0)}",
                            text,
                            "planning/evidence coordinate used in runtime diagnostic",
                        )
                    )
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        if isinstance(node.exc, ast.Call):
            for argument in (*node.exc.args, *(item.value for item in node.exc.keywords)):
                for item, text in _string_nodes(argument, self._resolve_name):
                    if _planning_value(text):
                        self.violations.append(
                            IdentityViolation(
                                self.path,
                                f"python:diagnostic:{getattr(item, 'lineno', 0)}:{getattr(item, 'col_offset', 0)}",
                                text,
                                "planning/evidence coordinate used in runtime diagnostic",
                            )
                        )
        self.generic_visit(node)


def _scan_python(path: Path, relative: str) -> list[IdentityViolation]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
    visitor = _PythonIdentityVisitor(relative)
    visitor.visit(tree)
    return visitor.violations


def _allowed_structured_traceability(path: str, location: str, field: str) -> bool:
    patterns_by_path = {
        "docs/design/semantic_ingestion/traceability_registry/registry-v1.json": {
            "requirement_id": r"^\$\.requirement_bindings\[\d+\]\.requirement_id$",
            "requirements": r"^\$\.heading_defaults\[\d+\]\.requirements\[\d+\]$",
            "selector_values": r"^\$\.structural_rules\[\d+\]\.selector_values\[\d+\]$",
            "test_id": r"^\$\.test_evidence_groups\[\d+\]\.selected_tests\[\d+\]\.test_id$",
        },
        "memorii/tests/ci/bootstrap-graph-transaction-boundary.json": {
            "requirement_ids": r"^\$\.rows\[\d+\]\.requirement_ids\[\d+\]$",
        },
    }
    patterns = patterns_by_path.get(path, {})
    pattern = patterns.get(field)
    return pattern is not None and re.fullmatch(pattern, location) is not None


def _scan_structured_value(
    value: Any,
    *,
    path: str,
    location: str,
    inherited_field: str | None = None,
) -> list[IdentityViolation]:
    violations: list[IdentityViolation] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{location}.{key}"
            key_text = str(key)
            planning_field_coordinate = key_text.lower() in _PLANNING_FIELDS and (
                type(item) is int
                or (
                    isinstance(item, str)
                    and (item.isdigit() or _planning_value(item))
                )
            )
            if planning_field_coordinate or _planning_identifier(key_text):
                violations.append(
                    IdentityViolation(
                        path,
                        f"structured-key:{child}",
                        key_text,
                        "planning/evidence coordinate used as structured key",
                    )
                )
            violations.extend(
                _scan_structured_value(item, path=path, location=child, inherited_field=key_text)
            )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            violations.extend(
                _scan_structured_value(
                    item,
                    path=path,
                    location=f"{location}[{index}]",
                    inherited_field=inherited_field,
                )
            )
    elif (
        isinstance(value, str)
        and inherited_field is not None
        and (
            _is_identity_field(inherited_field)
            or inherited_field.lower() in _TRACEABILITY_FIELDS
        )
        and _planning_value(value)
        and not _allowed_structured_traceability(path, location, inherited_field.lower())
    ):
        violations.append(
            IdentityViolation(
                path,
                f"structured:{location}",
                value,
                "planning/evidence coordinate used in identity-bearing field",
            )
        )
    return violations


def _scan_markdown_identity_values(path: Path, relative: str) -> list[IdentityViolation]:
    """Reject retired planning coordinates presented as durable Markdown identifiers."""
    violations: list[IdentityViolation] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        for code_span in re.finditer(r"`([^`]+)`", line):
            for match in _MARKDOWN_IDENTITY_VALUE_PATTERN.finditer(code_span.group(1)):
                violations.append(
                    IdentityViolation(
                        relative,
                        f"markdown:code-span:{line_number}:{code_span.start(1) + match.start()}",
                        match.group(),
                        "planning/evidence coordinate used as durable Markdown identity",
                    )
                )
    return violations


def _location_line(location: str) -> int | None:
    parts = location.rsplit(":", maxsplit=2)
    if len(parts) < 2:
        return None
    try:
        return int(parts[-2])
    except ValueError:
        return None


def _is_rejection_test_proof(root: Path, exception: _Exception) -> bool:
    if not exception.path.startswith("memorii/tests/") or not exception.path.endswith(".py"):
        return False
    prefix = f"{exception.path}::"
    if not exception.proof.startswith(prefix):
        return False
    function_name = exception.proof.removeprefix(prefix)
    if not any(token in function_name.lower() for token in ("legacy", "malformed", "reject")):
        return False
    source = root / exception.path
    if not source.is_file():
        return False
    line = _location_line(exception.location)
    if line is None:
        return False
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=exception.path)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != function_name:
            continue
        if not (node.lineno <= line <= (node.end_lineno or node.lineno)):
            return False
        for candidate in ast.walk(node):
            if not isinstance(candidate, ast.With):
                continue
            is_rejection_context = any(
                isinstance(item.context_expr, ast.Call)
                and isinstance(item.context_expr.func, ast.Attribute)
                and item.context_expr.func.attr == "raises"
                and isinstance(item.context_expr.func.value, ast.Name)
                and item.context_expr.func.value.id == "pytest"
                for item in candidate.items
            )
            if not is_rejection_context or not (
                candidate.lineno <= line <= (candidate.end_lineno or candidate.lineno)
            ):
                continue
            if len(candidate.body) != 1 or not isinstance(candidate.body[0], ast.Expr):
                return False
            boundary = candidate.body[0].value
            return isinstance(boundary, ast.Call) and any(
                isinstance(descendant, ast.Constant)
                and descendant.value == exception.value
                for descendant in ast.walk(boundary)
            )
        return False
    return False


def _proof_contains_traceability_value(
    value: Any,
    *,
    path: str,
    location: str,
    target: str,
    allowed_fields: frozenset[str],
) -> bool:
    if isinstance(value, dict):
        return any(
            _proof_contains_traceability_value(
                item,
                path=path,
                location=f"{location}.{key}",
                target=target,
                allowed_fields=allowed_fields,
            )
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(
            _proof_contains_traceability_value(
                item,
                path=path,
                location=f"{location}[{index}]",
                target=target,
                allowed_fields=allowed_fields,
            )
            for index, item in enumerate(value)
        )
    if value != target:
        return False
    field_match = re.search(r"\.([^.\[]+)(?:\[\d+\])?$", location)
    return (
        field_match is not None
        and field_match.group(1) in allowed_fields
        and _allowed_structured_traceability(path, location, field_match.group(1))
    )


def _proof_contains_compatibility_identity(value: Any, target: str) -> bool:
    if not isinstance(value, dict):
        return False
    compatibility_fields = {
        "format",
        "migration_id",
        "schema",
        "source_format",
        "source_schema",
        "target_format",
        "target_schema",
    }
    return any(
        str(key).lower() in compatibility_fields and item == target
        for key, item in value.items()
    )


def _load_structured_proof(path: Path) -> Any:
    raw = path.read_text(encoding="utf-8")
    return yaml.safe_load(raw) if path.suffix in {".yml", ".yaml"} else json.loads(raw)


def _compatibility_test_binds_value(path: Path, test_name: str, target: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
    bindings = _proof_import_bindings(tree)
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if function.name != test_name or not function.name.startswith("test_") or not any(
            token in function.name.lower()
            for token in ("compatibility", "fixture", "legacy", "reader")
        ):
            continue
        constants: dict[str, str] = {}
        for statement in function.body:
            if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                value = statement.value
                if value is not None:
                    resolved = _static_text(value, constants.get)
                    for assignment_target in targets:
                        if isinstance(assignment_target, ast.Name) and resolved is not None:
                            constants[assignment_target.id] = resolved
            if not isinstance(statement, ast.Assert):
                continue
            for call in (item for item in ast.walk(statement.test) if isinstance(item, ast.Call)):
                if _qualified_call_owner(call, bindings) not in _CANONICAL_COMPATIBILITY_READERS:
                    continue
                arguments = (*call.args, *(keyword.value for keyword in call.keywords))
                if any(_static_text(argument, constants.get) == target for argument in arguments):
                    return True
    return False


def _typed_traceability_source_binds(root: Path, exception: _Exception) -> bool:
    source = root / exception.path
    line = _location_line(exception.location)
    field_match = re.fullmatch(r"python:field:([^:]+):(\d+):(\d+)", exception.location)
    if not source.is_file() or line is None or field_match is None:
        return False
    field = field_match.group(1)
    column = int(field_match.group(3))
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=exception.path)
    bindings = _proof_import_bindings(tree)
    return any(
        _qualified_call_owner(call, bindings) in _CANONICAL_TRACEABILITY_CONSTRUCTORS
        and any(
            keyword.arg == field
            and any(
                text == exception.value
                and getattr(item, "lineno", 0) == line
                and getattr(item, "col_offset", -1) == column
                for item, text in _string_nodes(keyword.value)
            )
            for keyword in call.keywords
        )
        for call in (item for item in ast.walk(tree) if isinstance(item, ast.Call))
    )


def _traceability_exception_contract(exception: _Exception) -> frozenset[str]:
    field_match = re.fullmatch(r"python:field:([^:]+):\d+:\d+", exception.location)
    if field_match is None:
        raise ValueError("typed traceability exception must identify an exact Python field")
    field = field_match.group(1).lower()
    if field in _TRACEABILITY_FIELDS:
        if re.fullmatch(r"SIA-R\d{2}", exception.value) is None:
            raise ValueError("requirement traceability field must contain an SIA-R value")
        return frozenset({"requirement_id"})
    if field == "test_id":
        if re.fullmatch(r"SIA-T-[A-Z0-9-]+", exception.value) is None:
            raise ValueError("test traceability field must contain an SIA-T value")
        return frozenset({"test_id"})
    if field == "selector_values":
        if re.fullmatch(r"SIA-R\d{2}", exception.value) is None:
            raise ValueError("selector traceability field must contain an SIA-R value")
        return frozenset({"selector_values"})
    raise ValueError("typed traceability exception uses an unsupported source field")


def _validate_exception(root: Path, exception: _Exception) -> None:
    if exception.classification == "legacy_rejection_vector":
        if not _is_rejection_test_proof(root, exception):
            raise ValueError("legacy rejection exception requires an exact rejecting test proof")
        return
    proof_path = root / exception.proof
    if not proof_path.is_file():
        raise ValueError("identity allowlist proof must name an existing repository artifact")
    if exception.classification == "shipped_migration_identity":
        if not re.search(
            r"(?:field|structured):.*(?:format|migration|schema|source)",
            exception.location,
            re.IGNORECASE,
        ):
            raise ValueError("shipped migration exception must target an exact compatibility identity field")
        proof = _load_structured_proof(proof_path)
        if not _proof_contains_compatibility_identity(proof, exception.value):
            raise ValueError("compatibility proof does not contain the exact retained identity")
        proof_test = proof.get("proof_test") if isinstance(proof, dict) else None
        if not isinstance(proof_test, str) or "::" not in proof_test:
            raise ValueError("compatibility proof must name its exact reader or fixture test")
        proof_test_relative, proof_test_name = proof_test.rsplit("::", maxsplit=1)
        proof_test_path = root / proof_test_relative
        if not proof_test_path.is_file() or not _compatibility_test_binds_value(
            proof_test_path, proof_test_name, exception.value
        ):
            raise ValueError("compatibility proof test does not bind the exact retained identity")
        return
    if exception.classification == "typed_traceability_metadata" and not (
        exception.path.startswith(("docs/design/", "memorii/tests/"))
        and exception.proof
        == "docs/design/semantic_ingestion/traceability_registry/registry-v1.json"
    ):
        raise ValueError("typed traceability exception must target exact design traceability metadata")
    if exception.classification == "typed_traceability_metadata":
        allowed_fields = _traceability_exception_contract(exception)
        if not _typed_traceability_source_binds(root, exception):
            raise ValueError("traceability exception source is not an exact typed call field")
        proof = _load_structured_proof(proof_path)
        if not _proof_contains_traceability_value(
            proof,
            path=exception.proof,
            location="$",
            target=exception.value,
            allowed_fields=allowed_fields,
        ):
            raise ValueError("traceability proof does not bind the exact permitted field and value")


def _load_exceptions(path: Path, *, root: Path) -> tuple[_Exception, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if set(raw) != {"exceptions", "version"} or raw["version"] != 1 or not isinstance(raw["exceptions"], list):
        raise ValueError("identity allowlist must use the exact v1 shape")
    exceptions: list[_Exception] = []
    required = {"classification", "location", "path", "proof", "rationale", "value"}
    for item in raw["exceptions"]:
        if not isinstance(item, dict) or set(item) != required:
            raise ValueError("identity allowlist entry must use the exact v1 shape")
        exception = _Exception(**item)
        if exception.classification not in _EXCEPTION_CLASSES or not exception.rationale.strip():
            raise ValueError("identity allowlist entry has invalid classification or rationale")
        _validate_exception(root, exception)
        exceptions.append(exception)
    if len({item.key for item in exceptions}) != len(exceptions):
        raise ValueError("identity allowlist entries must be unique")
    return tuple(exceptions)


def scan_repository(root: Path, *, allowlist_path: Path) -> tuple[IdentityViolation, ...]:
    root = root.resolve()
    exceptions = _load_exceptions(allowlist_path.resolve(), root=root)
    violations: list[IdentityViolation] = []

    python_roots = (
        root / "memorii" / "memorii",
        root / "memorii" / "tests",
        root / "docs" / "design",
    )
    for python_root in python_roots:
        for path in sorted(python_root.rglob("*.py")):
            relative = path.relative_to(root).as_posix()
            if _planning_identifier(relative):
                violations.append(
                    IdentityViolation(
                        relative,
                        "path",
                        relative,
                        "planning/evidence coordinate used in repository path",
                    )
                )
            violations.extend(_scan_python(path, relative))

    design_root = root / "docs" / "design"
    for path in sorted(design_root.rglob("*.md")):
        relative = path.relative_to(root).as_posix()
        violations.extend(_scan_markdown_identity_values(path, relative))

    structured_paths = sorted(
        {
            *root.joinpath(".github", "workflows").glob("*.yml"),
            *root.joinpath(".github", "workflows").glob("*.yaml"),
            *root.joinpath("memorii", "memorii").rglob("*.json"),
            *root.joinpath("memorii", "memorii").rglob("*.yaml"),
            *root.joinpath("memorii", "memorii").rglob("*.yml"),
            *root.joinpath("memorii", "tests").rglob("*.json"),
            *root.joinpath("memorii", "tests").rglob("*.yaml"),
            *root.joinpath("memorii", "tests").rglob("*.yml"),
            *root.joinpath("docs", "design").rglob("*.json"),
            *root.joinpath("docs", "design").rglob("*.yaml"),
            *root.joinpath("docs", "design").rglob("*.yml"),
        }
    )
    for path in structured_paths:
        relative = path.relative_to(root).as_posix()
        if _planning_identifier(relative):
            violations.append(
                IdentityViolation(
                    relative,
                    "path",
                    relative,
                    "planning/evidence coordinate used in repository path",
                )
            )
        raw = path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(raw) if path.suffix in {".yml", ".yaml"} else json.loads(raw)
        violations.extend(_scan_structured_value(parsed, path=relative, location="$"))

    exception_by_key = {item.key: item for item in exceptions}
    observed_keys = {(item.path, item.location, item.value) for item in violations}
    filtered = [item for item in violations if (item.path, item.location, item.value) not in exception_by_key]
    for exception in exceptions:
        if exception.key not in observed_keys:
            filtered.append(
                IdentityViolation(
                    exception.path,
                    exception.location,
                    exception.value,
                    "stale identity allowlist entry",
                )
            )
    return tuple(sorted(set(filtered)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--allowlist", type=Path, required=True)
    args = parser.parse_args(argv)
    violations = scan_repository(args.root, allowlist_path=args.allowlist)
    for violation in violations:
        print(f"{violation.path}:{violation.location}: {violation.reason}: {violation.value}")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
