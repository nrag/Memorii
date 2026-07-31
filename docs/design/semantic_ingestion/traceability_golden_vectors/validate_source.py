"""Independent standard-library validation for the C2 golden-source package.

This validates source-package authority before an implementation may consume
the bytes.  It intentionally imports neither Memorii nor any runtime codec.
"""

from __future__ import annotations

import base64
import ast
import functools
import hashlib
import json
import re
from pathlib import Path


_ROOT = Path(__file__).parents[4]
_SOURCE = _ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors/v1.json"
_DESIGN = _ROOT / "docs/design/semantic_ingestion_architecture.md"
_KNOWN_INCOMPLETE_SOURCE_SHA256 = "b91599eee3eef49584db27a6b94b91eccbf560077466a94023b4eab5b3a504ec"
_APPROVED_SOURCE_SHA256 = "5f4a2e0f160acb36fcea22a82a31a07c8f4d3a7509177c2b1100f8f60d1579d1"
_REQUIRED_FIXTURE_KEYS = {
    "depends_on_coordinates",
    "exact_reference_coordinates",
    "expected_artifact_coordinate",
    "expected_artifact_digest",
    "expected_body_bytes_base64",
    "expected_body_digest",
    "expected_envelope_bytes_base64",
    "expected_historical_manifest_loads",
    "expected_ordinary_historical_member_traversals",
    "expected_signature_preimage_bytes_base64",
    "expected_signatures_base64",
    "expected_total_manifest_loads",
    "fixture_id",
    "inner_body_binding_digest",
    "inner_body_binding_id",
    "inner_body_schema_id",
    "inner_body_schema_version",
    "outer_envelope_binding_digest",
    "outer_envelope_binding_id",
    "outer_envelope_schema_id",
    "outer_envelope_schema_version",
    "signer_coordinate_references",
    "target_artifact_kind",
    "typed_input_bytes_base64",
}


class IncompletePackageError(ValueError):
    """The preserved C2 candidate is structurally checkable but not authoritative."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii") + b"\n"


def _digest(domain: str, payload: bytes) -> str:
    return hashlib.sha256(domain.encode("ascii") + b"\0" + payload).hexdigest()


def _lp(value: str) -> bytes:
    raw = value.encode("ascii")
    return len(raw).to_bytes(8, "big") + raw


class _Bytes:
    def __init__(self, value: bytes) -> None:
        self.value = value


class _DateTime:
    def __init__(self, value: str) -> None:
        self.value = value


def canonical_typed_value(value: object) -> bytes:
    """Encode the CTV v1 algebra without importing an application codec."""
    def encode(item: object) -> object:
        if item is None or isinstance(item, (bool, str)):
            return item
        if isinstance(item, int):
            return {"$type": "integer", "value": str(item)}
        if isinstance(item, _Bytes):
            return {"$type": "bytes", "value": base64.b64encode(item.value).decode("ascii")}
        if isinstance(item, _DateTime):
            return {"$type": "datetime", "value": item.value}
        if isinstance(item, tuple):
            return {"$type": "tuple", "items": [encode(entry) for entry in item]}
        if isinstance(item, list):
            return {"$type": "list", "items": [encode(entry) for entry in item]}
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise TypeError("CTV model maps require string keys")
            return {"$type": "map", "entries": [[key, encode(item[key])] for key in sorted(item)]}
        raise TypeError(f"unsupported CTV value: {type(item)!r}")
    return json.dumps(encode(value), ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii")


def _artifact_digest(binding: dict[str, object], value: bytes) -> str:
    values = (
        "semantic-ingestion-canonical-artifact",
        str(binding["profile_id"]), str(binding["profile_version"]),
        str(binding["profile_digest"]), str(binding["schema_id"]),
        str(binding["schema_version"]), str(binding["binding_digest"]),
    )
    payload = b"".join(_lp(value) for value in values) + len(value).to_bytes(8, "big") + value
    return hashlib.sha256(payload).hexdigest()


def _raw_digest(kind: str, value: bytes) -> str:
    domain = {
        "design_document": "semantic-ingestion-traceability",
        "registry_source": "memorii:sia-traceability-source:v1",
        "report_schema": "memorii:sia-report-schema:v1",
        "runner_environment_profile": "memorii:sia-runner-environment-profile:v1",
        "test_artifact": "memorii:sia-traceability-test-artifact:v1",
        "result_artifact": "memorii:sia-traceability-result-artifact:v1",
        "stdout_artifact": "memorii:sia-traceability-stdout:v1",
        "stderr_artifact": "memorii:sia-traceability-stderr:v1",
    }[kind]
    return hashlib.sha256(domain.encode("ascii") + b"\0" + value).hexdigest()


@functools.cache
def _rfc8032_verify(seed: bytes, message: bytes, signature: bytes) -> bool:
    field = 2**255 - 19
    order = 2**252 + 27742317777372353535851937790883648493
    curve = -121665 * pow(121666, field - 2, field) % field
    sqrt_minus_one = pow(2, (field - 1) // 4, field)

    def recover(encoded: bytes) -> tuple[int, int]:
        if len(encoded) != 32:
            raise ValueError("invalid Ed25519 point width")
        packed = int.from_bytes(encoded, "little")
        y, sign = packed & ((1 << 255) - 1), packed >> 255
        if y >= field:
            raise ValueError("non-canonical Ed25519 point")
        xx = (y * y - 1) * pow(curve * y * y + 1, field - 2, field) % field
        x = pow(xx, (field + 3) // 8, field)
        if (x * x - xx) % field:
            x = x * sqrt_minus_one % field
        if (x * x - xx) % field:
            raise ValueError("invalid Ed25519 point")
        if x & 1 != sign:
            x = field - x
        return x, y

    def plus(left: tuple[int, int], right: tuple[int, int]) -> tuple[int, int]:
        x1, y1 = left
        x2, y2 = right
        product = curve * x1 * x2 * y1 * y2
        return (
            (x1 * y2 + x2 * y1) * pow(1 + product, field - 2, field) % field,
            (y1 * y2 + x1 * x2) * pow(1 - product, field - 2, field) % field,
        )

    def multiply(point: tuple[int, int], scalar: int) -> tuple[int, int]:
        result = (0, 1)
        while scalar:
            if scalar & 1:
                result = plus(result, point)
            point = plus(point, point)
            scalar >>= 1
        return result

    def encode(point: tuple[int, int]) -> bytes:
        x, y = point
        return (y | ((x & 1) << 255)).to_bytes(32, "little")

    hashed = hashlib.sha512(seed).digest()
    secret = (int.from_bytes(hashed[:32], "little") & ((1 << 254) - 8)) | (1 << 254)
    base_y = 4 * pow(5, field - 2, field) % field
    base = recover(base_y.to_bytes(32, "little"))
    public = encode(multiply(base, secret))
    encoded_r, scalar_bytes = signature[:32], signature[32:]
    scalar = int.from_bytes(scalar_bytes, "little")
    if scalar >= order:
        return False
    challenge = int.from_bytes(hashlib.sha512(encoded_r + public + message).digest(), "little") % order
    return encode(multiply(base, scalar)) == encode(plus(recover(encoded_r), multiply(recover(public), challenge)))


def _marked(document: bytes, name: str) -> bytes:
    begin = f"`[{name}-BEGIN]`\n```text\n".encode("ascii")
    end = f"```\n`[{name}-END]`".encode("ascii")
    if document.count(begin) != 1 or document.count(end) != 1:
        raise ValueError(f"invalid {name} marker")
    value = document.split(begin, 1)[1].split(end, 1)[0]
    if not value.endswith(b"\n") or any(byte > 127 for byte in value):
        raise ValueError(f"invalid {name} bytes")
    return value


def _bindings(document: bytes) -> dict[str, str]:
    """Derive current bindings only from the frozen design's marked inputs."""
    grammar = _marked(document, "SIA-CTV-GRAMMAR-V1")
    inventory = _marked(document, "SIA-TRACEABILITY-SCHEMA-INVENTORY-V1")
    schemas = inventory.decode("ascii").splitlines()
    if schemas != sorted(set(schemas)) or len(schemas) != 56:
        raise ValueError("expected 56 sorted current C2 inventory coordinates")
    design_digest = _digest("semantic-ingestion-traceability", document)
    grammar_digest = _digest("memorii:sia-ctv-grammar:v1", grammar)
    inventory_digest = _digest("memorii:sia-traceability-schema-inventory:v1", inventory)
    profile = _digest(
        "memorii:sia-ctv-profile:v1",
        b"".join(_lp(value) for value in (
            "semantic_ingestion_typed_value", "1", "sia-ctv-grammar-v1",
            grammar_digest, grammar.decode("ascii"),
        )),
    )
    domains = (
        ("schema_fingerprint", "memorii:sia-ctv-schema-fingerprint:v1", "closed_declared_schema_and_transitive_types"),
        ("enum_registry", "memorii:sia-ctv-enum-registry:v1", "exact_literal_and_enum_members_in_registered_schema"),
        ("optional_field_policy", "memorii:sia-ctv-optional-field-policy:v1", "exact_required_omittable_nullable_state_in_registered_schema"),
        ("numeric_encoding_spec_registry", "memorii:sia-ctv-numeric-spec-registry:v1", "exact_field_constraints_and_no_ambient_numeric_default"),
        ("digest_signature_field_policy", "memorii:sia-ctv-digest-signature-field-policy:v1", "exclude_only_the_named_outer_digest_and_signature_fields"),
    )
    result: dict[str, str] = {}
    for schema in schemas:
        values: dict[str, str] = {}
        for component, domain, policy in domains:
            record = _canonical({
                "component": component,
                "design_document_digest": design_digest,
                "policy": policy,
                "profile_id": "semantic_ingestion_typed_value",
                "profile_version": 1,
                "schema_id": schema,
                "schema_inventory_digest": inventory_digest,
                "schema_version": 1,
            })
            values[component] = _digest(domain, record)
        result[schema] = _digest(
            "memorii:sia-ctv-binding:v1",
            b"".join(_lp(value) for value in (
                "semantic_ingestion_typed_value", "1", profile, schema, "1",
                values["schema_fingerprint"], values["enum_registry"],
                values["optional_field_policy"],
                values["numeric_encoding_spec_registry"],
                values["digest_signature_field_policy"],
            )),
        )
    return result


def profile_binding(document: bytes, schema_id: str) -> dict[str, object]:
    grammar = _marked(document, "SIA-CTV-GRAMMAR-V1")
    grammar_digest = _digest("memorii:sia-ctv-grammar:v1", grammar)
    profile = _digest(
        "memorii:sia-ctv-profile:v1",
        b"".join(_lp(value) for value in (
            "semantic_ingestion_typed_value", "1", "sia-ctv-grammar-v1",
            grammar_digest, grammar.decode("ascii"),
        )),
    )
    return {
        "profile_id": "semantic_ingestion_typed_value",
        "profile_version": 1,
        "profile_digest": profile,
        "schema_id": schema_id,
        "schema_version": 1,
        "binding_digest": _bindings(document)[schema_id],
    }


def _b64(value: str) -> bytes:
    raw = base64.b64decode(value, validate=True)
    if base64.b64encode(raw).decode("ascii") != value:
        raise ValueError("non-canonical base64")
    return raw


def _coordinates(name: str, values: list[str]) -> None:
    if values != sorted(set(values)):
        raise ValueError(f"{name} must be distinct Unicode-scalar sorted")


def _schema_contracts(design: bytes) -> tuple[dict[str, ast.ClassDef], dict[str, ast.expr]]:
    classes: dict[str, ast.ClassDef] = {}
    aliases: dict[str, ast.expr] = {}
    for block in re.findall(r"```python\n(.*?)\n```", design.decode("utf-8"), re.DOTALL):
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue
        classes.update({node.name: node for node in tree.body if isinstance(node, ast.ClassDef)})
        aliases.update({node.targets[0].id: node.value for node in tree.body if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)})
    return classes, aliases


def _declared_fields(name: str, classes: dict[str, ast.ClassDef]) -> dict[str, ast.expr]:
    node = classes[name]
    result: dict[str, ast.expr] = {}
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id in classes and base.id != "BaseModel":
            result.update(_declared_fields(base.id, classes))
    result.update({item.target.id: item.annotation for item in node.body if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)})
    return result

def _literal_values(annotation: ast.expr) -> list[object] | None:
    if isinstance(annotation, ast.Subscript) and isinstance(annotation.value, ast.Name) and annotation.value.id == "Literal":
        values = annotation.slice.elts if isinstance(annotation.slice, ast.Tuple) else [annotation.slice]
        return [ast.literal_eval(value) for value in values]
    return None


def _validate_declared_value(
    value: object,
    annotation: ast.expr,
    classes: dict[str, ast.ClassDef],
    aliases: dict[str, ast.expr],
    path: str,
) -> None:
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        _validate_declared_value(value, ast.Name(id=annotation.value), classes, aliases, path)
        return
    literal_values = _literal_values(annotation)
    if literal_values is not None:
        comparable = value
        if isinstance(value, dict) and set(value) == {"$type", "value"} and value.get("$type") == "integer":
            comparable = int(value["value"])
        if comparable not in literal_values:
            raise ValueError(f"literal mismatch: {path}")
        return
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        for option in (annotation.left, annotation.right):
            try:
                _validate_declared_value(value, option, classes, aliases, path)
                return
            except ValueError:
                pass
        raise ValueError(f"union mismatch: {path}")
    if isinstance(annotation, ast.Constant) and annotation.value is None:
        if value is not None:
            raise ValueError(f"null mismatch: {path}")
        return
    if isinstance(annotation, ast.Subscript):
        container = annotation.value.id if isinstance(annotation.value, ast.Name) else ""
        if container in {"tuple", "list"}:
            if not isinstance(value, dict) or value.get("$type") != "tuple" or not isinstance(value.get("items"), list):
                raise ValueError(f"tuple mismatch: {path}")
            items = value["items"]
            element = annotation.slice.elts[0] if isinstance(annotation.slice, ast.Tuple) else annotation.slice
            for index, item in enumerate(items):
                _validate_declared_value(item, element, classes, aliases, f"{path}[{index}]")
            return
        if container == "dict":
            if not isinstance(value, dict) or "$type" in value:
                raise ValueError(f"mapping mismatch: {path}")
            return
        if container == "Annotated" and isinstance(annotation.slice, ast.Tuple):
            _validate_declared_value(value, annotation.slice.elts[0], classes, aliases, path)
            return
        _validate_declared_value(value, annotation.slice, classes, aliases, path)
        return
    if not isinstance(annotation, ast.Name):
        raise ValueError(f"unsupported declared annotation: {path}")
    name = annotation.id
    if name in aliases:
        _validate_declared_value(value, aliases[name], classes, aliases, path)
    elif name in classes:
        if not isinstance(value, dict) or "$type" in value:
            raise ValueError(f"model mismatch: {path}")
        fields = _declared_fields(name, classes)
        if set(value) != set(fields):
            raise ValueError(f"nested declared fields mismatch: {path}")
        for field, child_annotation in fields.items():
            _validate_declared_value(value[field], child_annotation, classes, aliases, f"{path}.{field}")
    elif name == "str":
        if not isinstance(value, str):
            raise ValueError(f"string mismatch: {path}")
    elif name == "datetime":
        if (
            not isinstance(value, dict)
            or set(value) != {"$type", "value"}
            or value.get("$type") != "datetime"
            or not isinstance(value.get("value"), str)
            or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", value["value"]) is None
        ):
            raise ValueError(f"datetime mismatch: {path}")
    elif name == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"boolean mismatch: {path}")
    elif name == "int":
        if not isinstance(value, dict) or value.get("$type") != "integer" or not isinstance(value.get("value"), str):
            raise ValueError(f"integer mismatch: {path}")
    elif name == "bytes":
        if not isinstance(value, dict) or set(value) != {"$type", "value"} or value.get("$type") != "bytes" or not isinstance(value.get("value"), str):
            raise ValueError(f"bytes mismatch: {path}")
        _b64(value["value"])
    elif name == "None":
        if value is not None:
            raise ValueError(f"null mismatch: {path}")
    elif name != "object":
        raise ValueError(f"unknown declared type {name}: {path}")


def _decode_ctv(value: object) -> object:
    if isinstance(value, dict) and value.get("$type") == "map" and set(value) == {"$type", "entries"}:
        entries = value["entries"]
        if not isinstance(entries, list):
            raise ValueError("CTV map entries")
        result: dict[str, object] = {}
        for row in entries:
            if not isinstance(row, list) or len(row) != 2 or not isinstance(row[0], str) or row[0] in result:
                raise ValueError("CTV map row")
            result[row[0]] = _decode_ctv(row[1])
        return result
    if isinstance(value, dict) and value.get("$type") == "tuple" and set(value) == {"$type", "items"}:
        items = value["items"]
        if not isinstance(items, list):
            raise ValueError("CTV tuple items")
        return {"$type": "tuple", "items": [_decode_ctv(item) for item in items]}
    if isinstance(value, dict) and value.get("$type") in {"bytes", "integer", "datetime"}:
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_decode_ctv(item) for item in value]
    raise ValueError("unknown CTV value")


def _validate_raw_fixture(fixture: dict[str, object], body: bytes, design: bytes) -> None:
    kind = str(fixture["target_artifact_kind"])
    if kind == "design_document":
        expected = design
    elif kind == "registry_source":
        expected = (_ROOT / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json").read_bytes()
    elif kind in {"stdout_artifact", "stderr_artifact", "test_artifact", "result_artifact"}:
        expected = f"nonoperational {kind} fixture\n".encode("ascii")
    else:
        expected = _canonical({
            "artifact_kind": kind,
            "media_type": "application/schema+json" if kind == "report_schema" else "application/json",
            "nonoperational": True,
            "schema_id": fixture["inner_body_schema_id"],
            "schema_version": fixture["inner_body_schema_version"],
        })
    if body != expected or _b64(str(fixture["typed_input_bytes_base64"])) != expected:
        raise ValueError(f"exact raw contract mismatch: {fixture['fixture_id']}")


def validate(source: bytes, design: bytes | None = None) -> dict[str, object]:
    if source != _canonical(json.loads(source)):
        raise ValueError("source is not canonical compact JSON plus final LF")
    package = json.loads(source)
    if set(package) != {"fixtures", "format", "manifest_id", "manifest_version", "owner", "source_path", "vectors"}:
        raise ValueError("closed top-level source schema")
    fixtures = package["fixtures"]
    vectors = package["vectors"]
    ids = [fixture["fixture_id"] for fixture in fixtures]
    if ids != sorted(set(ids)):
        raise ValueError("fixture IDs must be distinct Unicode-scalar sorted")
    if len(vectors) != 25:
        raise ValueError("C2 requires exactly 25 vector cases")
    if len(fixtures) != 57:
        raise ValueError("C2 requires exactly 57 fixture instances")
    vector_ids = [vector["vector_id"] for vector in vectors]
    if vector_ids != sorted(set(vector_ids)):
        raise ValueError("vector IDs must be distinct Unicode-scalar sorted")
    fixture_ids = set(ids)
    bindings = _bindings(_DESIGN.read_bytes() if design is None else design)
    design_bytes = _DESIGN.read_bytes() if design is None else design
    classes, aliases = _schema_contracts(design_bytes)
    for fixture in fixtures:
        if set(fixture) != _REQUIRED_FIXTURE_KEYS:
            raise ValueError(f"closed fixture schema: {fixture['fixture_id']}")
        for field in ("typed_input_bytes_base64", "expected_body_bytes_base64", "expected_envelope_bytes_base64"):
            _b64(fixture[field])
        for field in ("expected_signature_preimage_bytes_base64", "expected_signatures_base64"):
            for item in fixture[field]:
                _b64(item)
        signed_kinds = {
            "recovery_policy", "trust_lifecycle_record", "trust_lifecycle_root", "coverage_approval",
            "execution_evidence", "release", "release_history", "active_release_pointer", "reader_lease",
            "retention_watermark", "pointer_history", "monotonic_time_witness", "approval_generation_manifest",
        }
        if fixture["target_artifact_kind"] in signed_kinds:
            fixture_number = int(fixture["fixture_id"].split("-", 2)[1])
            expected_signature_count = (
                2
                if fixture_number == 44
                else 1
            )
            if len(fixture["expected_signature_preimage_bytes_base64"]) != 1 or len(fixture["expected_signatures_base64"]) != expected_signature_count:
                raise ValueError("signed fixture has wrong RFC 8032 preimage/signature count")
            signature = _b64(fixture["expected_signatures_base64"][0])
            preimage = _b64(fixture["expected_signature_preimage_bytes_base64"][0])
            if len(signature) != 64:
                raise ValueError("RFC 8032 signature width")
            seeds = (
                (
                    bytes.fromhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb"),
                    bytes.fromhex("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7"),
                )
                if expected_signature_count == 2
                else (bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"),)
            )
            encoded_signatures = fixture["expected_signatures_base64"]
            if len(seeds) != len(encoded_signatures):
                raise ValueError("signature seed/material cardinality mismatch")
            for seed, encoded_signature in zip(seeds, encoded_signatures):
                if not _rfc8032_verify(seed, preimage, _b64(encoded_signature)):
                    raise ValueError(f"RFC 8032 signature verification failed: {fixture['fixture_id']}")
        elif fixture["expected_signature_preimage_bytes_base64"] or fixture["expected_signatures_base64"]:
            raise ValueError("unsigned fixture has signature material")
        for field in ("depends_on_coordinates", "exact_reference_coordinates", "signer_coordinate_references"):
            _coordinates(f"{fixture['fixture_id']}:{field}", fixture[field])
        direct = set(fixture["depends_on_coordinates"])
        references = set(fixture["exact_reference_coordinates"])
        if not direct <= references:
            raise ValueError("every direct dependency must be an exact reference")
        outer = [fixture[name] for name in (
            "outer_envelope_schema_id", "outer_envelope_schema_version",
            "outer_envelope_binding_id", "outer_envelope_binding_digest",
        )]
        if any(value is None for value in outer) and any(value is not None for value in outer):
            raise ValueError("outer binding must be all-null or fully present")
        if all(value is None for value in outer):
            if fixture["expected_envelope_bytes_base64"]:
                raise ValueError("raw fixture has envelope bytes")
        elif fixture["outer_envelope_schema_id"] != "CanonicalEncodedArtifact.v1" or fixture["outer_envelope_binding_id"] != "CanonicalEncodedArtifact.v1":
            raise ValueError("typed fixture must use the generic outer envelope")
        elif fixture["outer_envelope_binding_digest"] != bindings["CanonicalEncodedArtifact.v1"]:
            raise ValueError("outer binding digest is not independently derived")
        inner = fixture["inner_body_schema_id"]
        if inner in bindings and fixture["inner_body_binding_digest"] != bindings[inner]:
            raise ValueError("inner binding digest is not independently derived")
        if len(fixture["expected_artifact_digest"]) != 64 or set(fixture["expected_artifact_digest"]) == {"0"}:
            raise ValueError("placeholder artifact digest")
        if len(fixture["expected_body_digest"]) != 64 or set(fixture["expected_body_digest"]) == {"0"}:
            raise ValueError("placeholder body digest")
        body_bytes = _b64(fixture["expected_body_bytes_base64"])
        if _b64(fixture["typed_input_bytes_base64"]) != body_bytes:
            raise ValueError("typed input/body byte mismatch")
        try:
            decoded_body = json.loads(body_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError):
            decoded_body = None
        schema_name = fixture["inner_body_schema_id"].removesuffix(".v1")
        raw_kinds = {
            "design_document", "registry_source", "report_schema", "runner_environment_profile",
            "test_artifact", "result_artifact", "stdout_artifact", "stderr_artifact",
        }
        if fixture["target_artifact_kind"] in raw_kinds:
            _validate_raw_fixture(fixture, body_bytes, design_bytes)
            expected_body_digest = _raw_digest(fixture["target_artifact_kind"], body_bytes)
            expected_artifact_digest = expected_body_digest
        else:
            body_value = _decode_ctv(decoded_body)
            if not isinstance(body_value, dict) or schema_name not in classes:
                raise ValueError(f"unknown typed fixture schema: {schema_name}")
            _validate_declared_value(body_value, ast.Name(id=schema_name), classes, aliases, fixture["fixture_id"])
            expected_body_digest = hashlib.sha256(
                b"memorii:sia-ctv-body:" + str(inner).encode("ascii") + b":v1\0" + body_bytes
            ).hexdigest()
            outer_binding = profile_binding(design_bytes, "CanonicalEncodedArtifact.v1")
            expected_artifact_digest = _artifact_digest(outer_binding, body_bytes)
            expected_envelope = canonical_typed_value({
                "artifact_digest": expected_artifact_digest,
                "binding": outer_binding,
                "canonical_value_bytes": _Bytes(body_bytes),
                "canonical_value_digest": expected_body_digest,
            })
            if _b64(fixture["expected_envelope_bytes_base64"]) != expected_envelope:
                raise ValueError(f"generic envelope mismatch: {fixture['fixture_id']}")
        if fixture["expected_body_digest"] != expected_body_digest:
            raise ValueError(f"body digest mismatch: {fixture['fixture_id']}")
        if fixture["expected_artifact_digest"] != expected_artifact_digest:
            raise ValueError(f"artifact digest mismatch: {fixture['fixture_id']}")
        if fixture["outer_envelope_schema_id"] is not None and isinstance(decoded_body, dict) and decoded_body.get("fixture_id") == fixture["fixture_id"]:
            raise ValueError("schematic fixture body is not a target-schema value")
        coordinate = fixture["expected_artifact_coordinate"]
        if coordinate is not None:
            expected = f"sia-traceability/v1/{fixture['target_artifact_kind']}/{fixture['expected_artifact_digest']}"
            if coordinate != expected:
                raise ValueError("artifact coordinate does not bind its kind and digest")
    for vector in vectors:
        if vector["fixture_id"] not in fixture_ids:
            raise ValueError("dangling vector fixture")
        if (vector["expected_verdict"] == "accept") != (vector["expected_reason"] is None):
            raise ValueError("verdict/reason algebra")
        if vector["mutation_kind"] == "none":
            if vector["mutation_target"] is not None or vector["replacement_bytes_base64"] is not None or vector["replacement_reference"] is not None:
                raise ValueError("unmutated vector has replacement material")
        elif vector["mutation_target"] is None:
            raise ValueError("mutation requires an exact target")
    load_counts = {
        "fixture-21-active_release_pointer": (1, 0, 0),
        "fixture-22-current_pointer_index": (2, 1, 0),
        "fixture-23-current_pointer_fence": (3, 2, 0),
    }
    by_id = {fixture["fixture_id"]: fixture for fixture in fixtures}
    accepted_numbers = {*range(1, 14), *range(16, 21), 24, 25}
    expected_cases: dict[str, tuple[object, ...]] = {
        f"vector-{number:02d}-{numbered_name}": ("none", None, None, None, "accept", None)
        for number in accepted_numbers
        for numbered_name in [by_id[next(key for key in by_id if key.startswith(f"fixture-{number:02d}-"))]["fixture_id"].split("-", 2)[2]]
    }
    expected_cases.update({
        "vector-14-runner_report": ("cross_stream_substitution", "stream", None, by_id["fixture-15-stdout_artifact"]["expected_artifact_coordinate"], "reject", "stream_kind_mismatch"),
        "vector-15-stdout_artifact": ("alias_forbidden_stream", "owning_runner_report_digests", None, by_id["fixture-16-stderr_artifact"]["expected_artifact_coordinate"], "reject", "stream_alias_forbidden"),
        "vector-21-active_release_pointer": ("restore_prior_index", "current_pointer_index", None, "fixture-generation-G1", "reject", "active_pointer_monotonicity"),
        "vector-22-current_pointer_index": ("idempotent_lost_ack_replay", "G2", None, "fixture-generation-G2", "accept", None),
        "vector-23-inline_active_pointer_intent": ("substitute_reference", "active_pointer_intent", None, "fixture-generation-G2", "reject", "historical_predecessor_mismatch"),
    })
    for vector in vectors:
        actual_case = (
            vector["mutation_kind"], vector["mutation_target"], vector["replacement_bytes_base64"],
            vector["replacement_reference"], vector["expected_verdict"], vector["expected_reason"],
        )
        if vector["vector_id"] not in expected_cases or actual_case != expected_cases[vector["vector_id"]]:
            raise ValueError(f"exact vector case mismatch: {vector['vector_id']}")
    for fixture_id, counts in load_counts.items():
        fixture = by_id[fixture_id]
        actual = (
            fixture["expected_total_manifest_loads"],
            fixture["expected_historical_manifest_loads"],
            fixture["expected_ordinary_historical_member_traversals"],
        )
        if actual != counts:
            raise ValueError(f"G1/G2/G3 load closure mismatch: {fixture_id}")
    dependency_ids = {
        2: (1,), 4: (3,), 5: (1, 3), 6: (5,), 7: (1, 3, 5), 8: (2, 4, 6, 7), 9: (8,),
        10: (29, 30, 31, 32), 11: (9, 10), 12: (10, 11), 13: (32,), 14: (13, 15, 16, 34),
        17: (9, 10, 13, 14, 33, 34), 18: (10, 17), 19: (8, 9, 10, 12, 18, 36),
        20: (19,), 21: (19, 20, 37), 22: (21, 37), 23: (21, 22), 24: (21,),
        25: (20, 21, 24, 26), 26: (57, 51), 27: (21, 24, 25, 26), 28: (8,), 36: (35,),
        37: (8, 9, 10, 12, 18, 19, 20, 29, 30, 31, 32, 33, 34, 35, 36),
        38: (1, 47), 39: (2, 38), 40: (), 41: (5, 6),
        42: (7, 8, 3), 43: (42, 45, 40), 44: (43, 46, 5, 38),
        45: (8, 42), 46: (45, 43), 47: (46, 41), 48: (47, 44, 39),
        49: (8, 9, 10, 12, 18, 19, 20, 29, 30, 31, 32, 33, 34, 35, 36, 57),
        50: (8, 9, 10, 12, 18, 19, 20, 26, 29, 30, 31, 32, 33, 34, 35, 36),
        51: (49, 57), 52: (50, 26),
        53: (22, 51), 54: (53, 52), 55: (23, 53), 56: (55, 54),
        57: (21,),
    }
    numbered = {int(fixture["fixture_id"].split("-", 2)[1]): fixture for fixture in fixtures}
    for number, fixture in numbered.items():
        expected_dependencies = sorted(
            str(numbered[dependency]["expected_artifact_coordinate"])
            for dependency in dependency_ids.get(number, ())
        )
        if fixture["depends_on_coordinates"] != expected_dependencies:
            raise ValueError(f"exact C2 DAG mismatch: {fixture['fixture_id']}")
        if fixture["exact_reference_coordinates"] != expected_dependencies:
            raise ValueError(f"exact C2 reference closure mismatch: {fixture['fixture_id']}")
    if hashlib.sha256(source).hexdigest() != _APPROVED_SOURCE_SHA256:
        raise IncompletePackageError(
            "C2_INCOMPLETE_PACKAGE: preserved non-convergent candidate is not "
            "authoritative and must not be consumed as successful validation"
        )
    return {
        "fixture_count": len(fixtures),
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "vector_count": len(vectors),
    }


if __name__ == "__main__":
    print(json.dumps(validate(_SOURCE.read_bytes()), sort_keys=True))
