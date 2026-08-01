"""Regenerate the round-19 enum-qualified C2 authority package."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import rebind_recipe_v17 as v17


def schema_graph(document: str) -> tuple[dict[str, ast.ClassDef], dict[str, ast.expr]]:
    classes: dict[str, ast.ClassDef] = {}
    aliases: dict[str, ast.expr] = {}
    for block in re.findall(r"```python\n(.*?)```", document, re.DOTALL):
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                classes[node.name] = node
            elif (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                aliases[node.targets[0].id] = node.value
    return classes, aliases


def literal_member(node: ast.expr) -> Any:
    value = ast.literal_eval(node)
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return {"$type": "integer", "value": str(value)}
    raise ValueError(f"unsupported CanonicalLiteralScalar {ast.unparse(node)}")


def literal_nodes(
    annotation: ast.expr, aliases: dict[str, ast.expr] | None = None
) -> list[ast.expr]:
    if isinstance(annotation, ast.Name) and aliases and annotation.id in aliases:
        return literal_nodes(aliases[annotation.id], aliases)
    if (
        isinstance(annotation, ast.Subscript)
        and isinstance(annotation.value, ast.Name)
        and annotation.value.id == "Literal"
    ):
        return (
            list(annotation.slice.elts)
            if isinstance(annotation.slice, ast.Tuple)
            else [annotation.slice]
        )
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return literal_nodes(annotation.left, aliases) + literal_nodes(
            annotation.right, aliases
        )
    if (
        isinstance(annotation, ast.Subscript)
        and isinstance(annotation.value, ast.Name)
        and annotation.value.id == "Annotated"
    ):
        inner = (
            annotation.slice.elts[0]
            if isinstance(annotation.slice, ast.Tuple)
            else annotation.slice
        )
        return literal_nodes(inner, aliases)
    return []


def direct_literal_nodes(annotation: ast.expr) -> list[ast.expr]:
    if (
        isinstance(annotation, ast.Subscript)
        and isinstance(annotation.value, ast.Name)
        and annotation.value.id == "Literal"
    ):
        return (
            list(annotation.slice.elts)
            if isinstance(annotation.slice, ast.Tuple)
            else [annotation.slice]
        )
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return direct_literal_nodes(annotation.left) + direct_literal_nodes(
            annotation.right
        )
    if (
        isinstance(annotation, ast.Subscript)
        and isinstance(annotation.value, ast.Name)
        and annotation.value.id == "Annotated"
    ):
        inner = (
            annotation.slice.elts[0]
            if isinstance(annotation.slice, ast.Tuple)
            else annotation.slice
        )
        return direct_literal_nodes(inner)
    return []


def field_nodes(name: str, classes: dict[str, ast.ClassDef]) -> dict[str, tuple[str, ast.AnnAssign]]:
    result: dict[str, tuple[str, ast.AnnAssign]] = {}
    node = classes[name]
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id in classes:
            result.update(field_nodes(base.id, classes))
    for child in node.body:
        if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
            result[child.target.id] = (name, child)
    return result


def collect_registry(
    document: str,
) -> tuple[dict[str, list[Any]], dict[str, ast.ClassDef], dict[str, ast.expr]]:
    classes, aliases = schema_graph(document)
    inventory = v17.marked(
        document.encode("utf-8"), "SIA-TRACEABILITY-SCHEMA-INVENTORY-V1", "text"
    ).decode("ascii").splitlines()
    registry: dict[str, list[Any]] = {}
    visited: set[tuple[str, str | None]] = set()

    def add(schema: str, nodes: list[ast.expr]) -> None:
        members: list[Any] = []
        identities: set[bytes] = set()
        for node in nodes:
            member = literal_member(node)
            identity = v17.canonical(member)
            if identity in identities:
                raise ValueError(f"type-sensitive duplicate in {schema}")
            identities.add(identity)
            members.append(member)
        if not members:
            raise ValueError(f"empty enum schema {schema}")
        existing = registry.setdefault(schema, members)
        if existing != members:
            raise ValueError(f"conflicting enum schema {schema}")

    def visit(annotation: ast.expr, owner: str | None = None, field: str | None = None) -> None:
        key = (ast.dump(annotation), f"{owner}.{field}" if owner and field else None)
        if key in visited:
            return
        visited.add(key)
        if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
            visit(ast.parse(annotation.value, mode="eval").body, owner, field)
            return
        if isinstance(annotation, ast.Name):
            if annotation.id in aliases:
                nodes = literal_nodes(aliases[annotation.id], aliases)
                if nodes:
                    add(annotation.id, nodes)
                    return
                visit(aliases[annotation.id])
            elif annotation.id in classes:
                for field_name, (declaring_owner, node) in field_nodes(
                    annotation.id, classes
                ).items():
                    visit(node.annotation, declaring_owner, field_name)
            return
        nodes = direct_literal_nodes(annotation)
        if nodes:
            if owner is None or field is None:
                raise ValueError(
                    f"anonymous Literal outside a declared field: {ast.unparse(annotation)}"
                )
            add(f"{owner}.{field}", nodes)
            return
        if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
            visit(annotation.left, owner, field)
            visit(annotation.right, owner, field)
        elif isinstance(annotation, ast.Subscript):
            values = (
                list(annotation.slice.elts)
                if isinstance(annotation.slice, ast.Tuple)
                else [annotation.slice]
            )
            for value in values:
                if not (isinstance(value, ast.Constant) and value.value is Ellipsis):
                    visit(value, owner, field)

    for schema in inventory:
        root = schema.removesuffix(".v1")
        if root not in classes and root not in aliases:
            if root.startswith("TraceabilityRegistryRoot."):
                continue
            raise ValueError(f"inventory root {root} is not declared")
        visit(ast.Name(id=root))
    return dict(sorted(registry.items())), classes, aliases


def enum_token(schema: str, value: Any) -> dict[str, Any]:
    member = (
        value
        if value is None or isinstance(value, (str, bool))
        else {"$type": "integer", "value": str(value)}
    )
    return {"$type": "enum", "schema": schema, "member": member}


def qualify(
    value: Any,
    annotation: ast.expr,
    classes: dict[str, ast.ClassDef],
    aliases: dict[str, ast.expr],
    *,
    owner: str | None = None,
    field: str | None = None,
) -> Any:
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        return qualify(
            value,
            ast.parse(annotation.value, mode="eval").body,
            classes,
            aliases,
            owner=owner,
            field=field,
        )
    if isinstance(annotation, ast.Name):
        if annotation.id in aliases:
            if literal_nodes(aliases[annotation.id], aliases):
                raw = (
                    value["member"]
                    if isinstance(value, dict) and value.get("$type") == "enum"
                    else value
                )
                if isinstance(raw, dict) and raw.get("$type") == "integer":
                    raw = int(raw["value"])
                if raw is None:
                    options = literal_nodes(aliases[annotation.id], aliases)
                    if len(options) == 1:
                        raw = ast.literal_eval(options[0])
                return enum_token(annotation.id, raw)
            return qualify(value, aliases[annotation.id], classes, aliases)
        if annotation.id in classes:
            entries = {key: item for key, item in value["entries"]}
            fields = field_nodes(annotation.id, classes)
            return {
                "$type": "map",
                "entries": [
                    [
                        key,
                        qualify(
                            entries[key],
                            node.annotation,
                            classes,
                            aliases,
                            owner=declaring_owner,
                            field=key,
                        ),
                    ]
                    for key, (declaring_owner, node) in sorted(fields.items())
                ],
            }
        return value
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        if value is None:
            return None
        for option in (annotation.left, annotation.right):
            if isinstance(option, ast.Constant) and option.value is None:
                continue
            try:
                return qualify(value, option, classes, aliases, owner=owner, field=field)
            except (KeyError, TypeError, ValueError):
                continue
        raise ValueError(f"value does not match union at {owner}.{field}")
    nodes = direct_literal_nodes(annotation)
    if nodes:
        if owner is None or field is None:
            raise ValueError("inline Literal lacks declaring field")
        raw = (
            value["member"]
            if isinstance(value, dict) and value.get("$type") == "enum"
            else value
        )
        if isinstance(raw, dict) and raw.get("$type") == "integer":
            raw = int(raw["value"])
        if raw is None and len(nodes) == 1:
            raw = ast.literal_eval(nodes[0])
        return enum_token(f"{owner}.{field}", raw)
    if isinstance(annotation, ast.Subscript):
        container = annotation.value.id if isinstance(annotation.value, ast.Name) else ""
        args = (
            list(annotation.slice.elts)
            if isinstance(annotation.slice, ast.Tuple)
            else [annotation.slice]
        )
        if container == "Annotated":
            return qualify(value, args[0], classes, aliases, owner=owner, field=field)
        if container in {"tuple", "list", "set", "frozenset"}:
            inner = args[0]
            return {
                "$type": value["$type"],
                "items": [
                    qualify(item, inner, classes, aliases, owner=owner, field=field)
                    for item in value["items"]
                ],
            }
        if container == "dict":
            inner = args[-1]
            return {
                "$type": "map",
                "entries": [
                    [
                        key,
                        qualify(item, inner, classes, aliases, owner=owner, field=field),
                    ]
                    for key, item in value["entries"]
                ],
            }
    return value


def walk_leaves(value: Any, path: str) -> list[str]:
    if isinstance(value, dict) and value.get("$type") == "map":
        return [
            leaf
            for key, item in value["entries"]
            for leaf in walk_leaves(item, f"{path}.{key}")
        ]
    if isinstance(value, dict):
        return [
            leaf
            for key, item in value.items()
            for leaf in walk_leaves(item, f"{path}.{key}")
        ]
    if isinstance(value, list):
        return [
            leaf
            for index, item in enumerate(value)
            for leaf in walk_leaves(item, f"{path}[{index}]")
        ]
    return [path]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--registry-output", type=Path)
    parser.add_argument("--update-design", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--restore-from-index", action="store_true")
    args = parser.parse_args()
    document = args.design.read_text()
    enum_registry, classes, aliases = collect_registry(document)
    if args.registry_output is not None:
        args.registry_output.write_text(
            json.dumps(enum_registry, ensure_ascii=True, indent=2) + "\n"
        )
    if args.update_design:
        payload = json.dumps(enum_registry, ensure_ascii=True, indent=2)
        pattern = (
            r"(`\[SIA-CTV-ENUM-REGISTRY-V1-BEGIN\]`\n```json\n)"
            r".*?"
            r"(\n```\n`\[SIA-CTV-ENUM-REGISTRY-V1-END\]`)"
        )
        updated, count = re.subn(
            pattern, rf"\g<1>{payload}\g<2>", document, count=1, flags=re.DOTALL
        )
        if count != 1:
            raise ValueError("marked enum registry replacement failed")
        args.design.write_text(updated)
        document = updated
    if args.output is None:
        return
    recipe_bytes = (
        subprocess.check_output(
            ["git", "show", f":{args.recipe.as_posix()}"],
            cwd=Path(__file__).resolve().parents[4],
        )
        if args.restore_from_index
        else args.recipe.read_bytes()
    )
    recipe = json.loads(recipe_bytes)
    negative_by_id = {
        case["case_id"]: case for case in recipe["direct_negative_cases"]
    }
    negative_by_id["negative-two-node-cycle"]["replacement"]["value"] = (
        "fixture-37-approval_generation_manifest"
    )
    negative_by_id["negative-descendant-cycle"]["replacement"]["value"] = (
        "fixture-22-current_pointer_index"
    )
    for fixture_id, record in recipe["expanded_typed_values"].items():
        root = record["inner_schema_id"].removesuffix(".v1")
        qualified = qualify(
            record["typed_ctv"], ast.Name(id=root), classes, aliases
        )
        record["typed_ctv"] = qualified
        authority = recipe["primitive_authority"]["authority_bodies"][fixture_id]
        authority["value"] = json.loads(json.dumps(qualified))
    typed_count = 0
    for row in recipe["field_coverage_ledger"]:
        fixture_id = row["fixture_id"]
        if fixture_id not in recipe["expanded_typed_values"]:
            continue
        paths = walk_leaves(
            recipe["expanded_typed_values"][fixture_id]["typed_ctv"],
            "$.expanded_typed_value",
        )
        row["fields"] = [
            {
                "path": path,
                "rule": "expanded_authority_ctv",
                "source": "deterministic_derivation",
            }
            for path in paths
        ]
        typed_count += len(paths)
    recipe["typed_expansion_leaf_count"] = typed_count
    recipe["expanded_leaf_denominator"] = typed_count + recipe["raw_leaf_count"]
    profile, binding_by_schema = v17.bindings(args.design.read_bytes())
    v17.rebind(recipe, profile, binding_by_schema)
    args.output.write_bytes(v17.canonical(recipe))


if __name__ == "__main__":
    main()
