"""Semantic parity checks for YAML prompt schemas and Pydantic outputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import BaseModel

_ANNOTATION_KEYS = frozenset(
    {"$comment", "$id", "$schema", "default", "deprecated", "description", "discriminator", "examples", "readOnly", "title", "writeOnly"}
)
_SUPPORTED_VALIDATION_KEYS = frozenset(
    {
        "$defs",
        "$ref",
        "additionalProperties",
        "anyOf",
        "const",
        "enum",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "format",
        "items",
        "maxItems",
        "maxLength",
        "maxProperties",
        "maximum",
        "minItems",
        "minLength",
        "minProperties",
        "minimum",
        "multipleOf",
        "oneOf",
        "pattern",
        "properties",
        "required",
        "type",
        "uniqueItems",
    }
)


def assert_supported_json_schema(*, schema_name: str, schema: Mapping[str, object]) -> None:
    """Validate syntax and reject semantics the parity checker cannot prove."""

    schema_dict = dict(schema)
    Draft202012Validator.check_schema(schema_dict)
    _assert_supported_schema_node(schema_dict, path=schema_name)


def assert_output_schema_matches_model(
    *,
    prompt_ref: str,
    output_schema: Mapping[str, object],
    output_model: type[BaseModel],
) -> None:
    """Reject prompt/model pairs that accept different structural values."""

    prompt_schema = dict(output_schema)
    assert_supported_json_schema(schema_name=f"{prompt_ref}.output_schema", schema=prompt_schema)
    prompt_signature = _acceptance_signature(prompt_schema, root=prompt_schema)
    model_schema = output_model.model_json_schema()
    assert_supported_json_schema(
        schema_name=f"{output_model.__module__}.{output_model.__name__}",
        schema=model_schema,
    )
    model_signature = _acceptance_signature(model_schema, root=model_schema)
    if prompt_signature != model_signature:
        difference = _first_difference(prompt_signature, model_signature)
        raise ValueError(
            "Prompt output schema does not match "
            f"{output_model.__module__}.{output_model.__name__}: {prompt_ref}; {difference}"
        )


def _first_difference(left: object, right: object, *, path: str = "schema") -> str:
    if type(left) is not type(right):
        return f"{path} has prompt={left!r}, model={right!r}"
    if isinstance(left, tuple) and isinstance(right, tuple):
        if len(left) != len(right):
            return f"{path} has prompt length={len(left)}, model length={len(right)}"
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=True)):
            if left_item != right_item:
                return _first_difference(left_item, right_item, path=f"{path}[{index}]")
    if left != right:
        return f"{path} has prompt={left!r}, model={right!r}"
    return f"{path} differs"


def _acceptance_signature(schema: dict[str, Any], *, root: dict[str, Any]) -> object:
    if "$ref" in schema:
        siblings = set(schema) - {"$ref", *_ANNOTATION_KEYS}
        if siblings:
            raise ValueError(f"$ref siblings are not supported: {sorted(siblings)}")
        return _acceptance_signature(_resolve_ref(root, str(schema["$ref"])), root=root)
    union_key = "anyOf" if "anyOf" in schema else "oneOf" if "oneOf" in schema else None
    if union_key is not None:
        siblings = set(schema) - {union_key, *_ANNOTATION_KEYS}
        if siblings:
            raise ValueError(f"{union_key} siblings are not supported: {sorted(siblings)}")
        variants = [_acceptance_signature(dict(item), root=root) for item in schema[union_key]]
        flattened: list[object] = []
        for variant in variants:
            if isinstance(variant, tuple) and len(variant) == 2 and variant[0] == "union":
                flattened.extend(variant[1])
            else:
                flattened.append(variant)
        return ("union", tuple(sorted(flattened, key=repr)))

    schema = {key: value for key, value in schema.items() if key not in _ANNOTATION_KEYS and key != "$defs"}
    schema_type = schema.get("type") or _type_for_literal(schema)
    if isinstance(schema_type, list):
        variants = [
            _acceptance_signature(
                {**schema, "type": item, "enum": _enum_for_type(schema.get("enum"), str(item))},
                root=root,
            )
            for item in schema_type
        ]
        return ("union", tuple(sorted(variants, key=repr)))
    if schema_type == "object" or (schema_type is None and "properties" in schema):
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            raise ValueError("object schema properties must be a mapping")
        return (
            "object",
            _additional_properties_signature(schema.get("additionalProperties", True), root=root),
            tuple(sorted(str(item) for item in schema.get("required", []))),
            schema.get("minProperties"),
            schema.get("maxProperties"),
            tuple(
                (name, _acceptance_signature(dict(value), root=root))
                for name, value in sorted(properties.items())
                if isinstance(value, dict)
            ),
        )
    if schema_type == "array":
        items = schema.get("items", {})
        if not isinstance(items, dict):
            raise ValueError("array schema items must be a mapping")
        return (
            "array",
            _acceptance_signature(items, root=root),
            schema.get("minItems"),
            schema.get("maxItems"),
            bool(schema.get("uniqueItems", False)),
        )
    enum_values = schema.get("enum")
    if "const" in schema:
        enum_values = [schema["const"]]
    if schema_type == "null" and enum_values is None:
        enum_values = [None]
    numeric = schema_type in {"integer", "number"}
    textual = schema_type == "string"
    return (
        "scalar",
        schema_type,
        tuple(sorted(enum_values, key=repr)) if isinstance(enum_values, list) else None,
        _inclusive_minimum(schema, schema_type) if numeric else None,
        _inclusive_maximum(schema, schema_type) if numeric else None,
        schema.get("minLength") if textual else None,
        schema.get("maxLength") if textual else None,
        schema.get("pattern") if textual else None,
        schema.get("format") if textual else None,
        schema.get("multipleOf") if numeric else None,
    )


def _assert_supported_schema_node(schema: dict[str, Any], *, path: str) -> None:
    unsupported = set(schema) - _SUPPORTED_VALIDATION_KEYS - _ANNOTATION_KEYS
    if unsupported:
        raise ValueError(f"unsupported JSON Schema keywords at {path}: {sorted(unsupported)}")
    definitions = schema.get("$defs", {})
    if not isinstance(definitions, dict):
        raise ValueError(f"{path}.$defs must be a mapping")
    for name, definition in definitions.items():
        if not isinstance(definition, dict):
            raise ValueError(f"{path}.$defs.{name} must be a schema")
        _assert_supported_schema_node(definition, path=f"{path}.$defs.{name}")
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise ValueError(f"{path}.properties must be a mapping")
    for name, property_schema in properties.items():
        if not isinstance(property_schema, dict):
            raise ValueError(f"{path}.properties.{name} must be a schema")
        _assert_supported_schema_node(property_schema, path=f"{path}.properties.{name}")
    items = schema.get("items")
    if items is not None:
        if not isinstance(items, dict):
            raise ValueError(f"{path}.items must be a schema")
        _assert_supported_schema_node(items, path=f"{path}.items")
    for union_key in ("anyOf", "oneOf"):
        variants = schema.get(union_key, [])
        if not isinstance(variants, list):
            raise ValueError(f"{path}.{union_key} must be a list")
        for index, variant in enumerate(variants):
            if not isinstance(variant, dict):
                raise ValueError(f"{path}.{union_key}[{index}] must be a schema")
            _assert_supported_schema_node(variant, path=f"{path}.{union_key}[{index}]")
    additional = schema.get("additionalProperties")
    if isinstance(additional, dict):
        _assert_supported_schema_node(additional, path=f"{path}.additionalProperties")


def _additional_properties_signature(value: object, *, root: dict[str, Any]) -> object:
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        return _acceptance_signature(value, root=root)
    raise ValueError("additionalProperties must be a boolean or schema")


def _resolve_ref(root: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError(f"only local JSON schema references are supported: {ref}")
    value: object = root
    for component in ref[2:].split("/"):
        if not isinstance(value, dict) or component not in value:
            raise ValueError(f"unresolvable JSON schema reference: {ref}")
        value = value[component]
    if not isinstance(value, dict):
        raise ValueError(f"JSON schema reference does not resolve to an object: {ref}")
    return value


def _enum_for_type(values: object, schema_type: str) -> list[object] | None:
    if not isinstance(values, list):
        return None
    if schema_type == "null":
        return [None] if None in values else []
    return [value for value in values if value is not None]


def _type_for_literal(schema: dict[str, Any]) -> str | None:
    values = [schema["const"]] if "const" in schema else schema.get("enum")
    if not isinstance(values, list) or not values:
        return None
    non_null_values = [value for value in values if value is not None]
    if not non_null_values:
        return "null"
    value_types = {type(value) for value in non_null_values}
    if value_types == {str}:
        return "string"
    if value_types == {bool}:
        return "boolean"
    if value_types == {int}:
        return "integer"
    if value_types <= {int, float}:
        return "number"
    return None


def _inclusive_minimum(schema: dict[str, Any], schema_type: object) -> object:
    if "minimum" in schema:
        return schema["minimum"]
    exclusive = schema.get("exclusiveMinimum")
    if schema_type == "integer" and isinstance(exclusive, int):
        return exclusive + 1
    return ("exclusive", exclusive) if exclusive is not None else None


def _inclusive_maximum(schema: dict[str, Any], schema_type: object) -> object:
    if "maximum" in schema:
        return schema["maximum"]
    exclusive = schema.get("exclusiveMaximum")
    if schema_type == "integer" and isinstance(exclusive, int):
        return exclusive - 1
    return ("exclusive", exclusive) if exclusive is not None else None
