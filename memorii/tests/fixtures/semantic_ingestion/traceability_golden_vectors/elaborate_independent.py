"""Independent fixture-only C1 elaborator; it imports only the standard library."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

_MARKED_REGIONS = (
    b"SIA-CTV-GRAMMAR-V1",
    b"SIA-TRACEABILITY-SCHEMA-INVENTORY-V1",
)

def _hash(tag: str, payload: bytes) -> str:
    return hashlib.sha256(tag.encode("ascii") + b"\0" + payload).hexdigest()


def _pack(value: str | bytes) -> bytes:
    blob = value.encode("ascii") if isinstance(value, str) else value
    return len(blob).to_bytes(8, "big") + blob


def _raw_document(document: bytes) -> None:
    if len(document) == 0 or document[:3] == b"\xef\xbb\xbf":
        raise ValueError("raw design is empty or has a BOM")
    if b"\x00" in document or b"\r" in document:
        raise ValueError("raw design contains a forbidden byte")
    if document[-1:] != b"\n" or document[-2:] == b"\n\n":
        raise ValueError("raw design final LF is not exact")
    try:
        document.decode("utf-8")
    except UnicodeError as error:
        raise ValueError("raw design is not strict UTF-8") from error
    for stem in _MARKED_REGIONS:
        opening = b"`[" + stem + b"-BEGIN]`\n```text\n"
        closing = b"```\n`[" + stem + b"-END]`\n"
        for exact in (opening.split(b"\n", 1)[0] + b"\n", closing.split(b"\n", 1)[1] + b"\n"):
            if document.splitlines().count(exact.rstrip(b"\n")) != 1:
                raise ValueError("raw design marker is not unique and standalone")
        if document.count(opening) != 1 or document.count(closing) != 1:
            raise ValueError("raw design marker fence adjacency is invalid")


def _block(document: bytes, begin: bytes, end: bytes) -> bytes:
    start = b"`[" + begin + b"]`\n```text\n"
    finish = b"```\n`[" + end + b"]`"
    if document.count(start) != 1 or document.count(finish) != 1:
        raise ValueError("marker cardinality")
    body = document.split(start, 1)[1].split(finish, 1)[0]
    if not body.endswith(b"\n") or any(byte > 127 for byte in body):
        raise ValueError("marked bytes")
    return body


def _record(component: str, policy: str, schema: str, design: str, inventory: str) -> bytes:
    return (json.dumps({"component": component, "design_document_digest": design, "policy": policy, "profile_id": "semantic_ingestion_typed_value", "profile_version": 1, "schema_id": schema, "schema_inventory_digest": inventory, "schema_version": 1}, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode("ascii")


def _key_table(document: bytes) -> list[tuple[str, str, str, str, str]]:
    rows: list[tuple[str, str, str, str, str]] = []
    for line in document.splitlines():
        if not line.startswith((b"| `fixture-bootstrap-", b"| `fixture-recovery-")):
            continue
        cells = [cell.strip() for cell in line.split(b"|")[1:-1]]
        if len(cells) != 5:
            raise ValueError("malformed fixed Ed25519 row")
        signer, seed, public, message, signature = cells
        if not all(value.startswith(b"`") and value.endswith(b"`") for value in (signer, seed, public, signature)):
            raise ValueError("malformed fixed Ed25519 cell")
        rows.append(
            (
                signer[1:-1].decode("ascii"),
                seed[1:-1].decode("ascii"),
                public[1:-1].decode("ascii"),
                "" if message == b"empty" else message[1:-1].decode("ascii"),
                signature[1:-1].decode("ascii"),
            )
        )
    names = [row[0] for row in rows]
    if names != ["fixture-bootstrap-1", "fixture-bootstrap-2", "fixture-recovery-1", "fixture-recovery-2"]:
        raise ValueError("fixed Ed25519 signer rows are missing, duplicated, or reordered")
    for name, seed, public, message, signature in rows:
        try:
            widths = (len(bytes.fromhex(seed)), len(bytes.fromhex(public)), len(bytes.fromhex(message)), len(bytes.fromhex(signature)))
        except ValueError as error:
            raise ValueError(f"invalid fixed Ed25519 hex: {name}") from error
        if widths[0] != 32 or widths[1] != 32 or widths[3] != 64:
            raise ValueError(f"invalid fixed Ed25519 width: {name}")
    return rows


def _rfc8032(seed: bytes, message: bytes) -> tuple[bytes, bytes]:
    field = 2**255 - 19
    order = 2**252 + 27742317777372353535851937790883648493
    curve = -121665 * pow(121666, field - 2, field) % field
    sqrt_minus_one = pow(2, (field - 1) // 4, field)
    base_y = 4 * pow(5, field - 2, field) % field

    def recover_x(y: int, sign: int) -> int:
        xx = (y * y - 1) * pow(curve * y * y + 1, field - 2, field) % field
        x = pow(xx, (field + 3) // 8, field)
        if (x * x - xx) % field:
            x = x * sqrt_minus_one % field
        if (x * x - xx) % field or x == 0 and sign:
            raise ValueError("noncanonical Ed25519 point")
        return field - x if x & 1 != sign else x

    base_x = recover_x(base_y, 0)

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

    def decode(raw: bytes) -> tuple[int, int]:
        if len(raw) != 32:
            raise ValueError("Ed25519 point width")
        encoded = int.from_bytes(raw, "little")
        y, sign = encoded & ((1 << 255) - 1), encoded >> 255
        if y >= field:
            raise ValueError("noncanonical Ed25519 point")
        point = (recover_x(y, sign), y)
        if encode(point) != raw:
            raise ValueError("noncanonical Ed25519 point encoding")
        return point

    hashed = hashlib.sha512(seed).digest()
    secret = (int.from_bytes(hashed[:32], "little") & ((1 << 254) - 8)) | (1 << 254)
    public = encode(multiply((base_x, base_y), secret))
    nonce = int.from_bytes(hashlib.sha512(hashed[32:] + message).digest(), "little") % order
    encoded_r = encode(multiply((base_x, base_y), nonce))
    challenge = int.from_bytes(hashlib.sha512(encoded_r + public + message).digest(), "little") % order
    signature = encoded_r + ((nonce + challenge * secret) % order).to_bytes(32, "little")
    scalar = int.from_bytes(signature[32:], "little")
    if scalar >= order:
        raise ValueError("noncanonical Ed25519 scalar")
    left = multiply((base_x, base_y), scalar)
    right = plus(decode(signature[:32]), multiply(decode(public), challenge))
    if encode(left) != encode(right):
        raise ValueError("Ed25519 self-verification failed")
    return public, signature


def elaborate(document: bytes) -> bytes:
    _raw_document(document)
    grammar = _block(document, b"SIA-CTV-GRAMMAR-V1-BEGIN", b"SIA-CTV-GRAMMAR-V1-END")
    inventory = _block(document, b"SIA-TRACEABILITY-SCHEMA-INVENTORY-V1-BEGIN", b"SIA-TRACEABILITY-SCHEMA-INVENTORY-V1-END")
    coordinates = inventory.decode("ascii").splitlines()
    if len(coordinates) != 52 or coordinates != sorted(set(coordinates)):
        raise ValueError("inventory ordering")
    design = _hash("semantic-ingestion-traceability", document)
    grammar_digest = _hash("memorii:sia-ctv-grammar:v1", grammar)
    inventory_digest = _hash("memorii:sia-traceability-schema-inventory:v1", inventory)
    profile_id, version, revision = "semantic_ingestion_typed_value", "1", "sia-ctv-grammar-v1"
    profile = _hash("memorii:sia-ctv-profile:v1", b"".join(_pack(value) for value in (profile_id, version, revision, grammar_digest, grammar)))
    definitions = [
        ("schema_fingerprint", "memorii:sia-ctv-schema-fingerprint:v1", "closed_declared_schema_and_transitive_types"),
        ("enum_registry", "memorii:sia-ctv-enum-registry:v1", "exact_literal_and_enum_members_in_registered_schema"),
        ("optional_field_policy", "memorii:sia-ctv-optional-field-policy:v1", "exact_required_omittable_nullable_state_in_registered_schema"),
        ("numeric_encoding_spec_registry", "memorii:sia-ctv-numeric-spec-registry:v1", "exact_field_constraints_and_no_ambient_numeric_default"),
        ("digest_signature_field_policy", "memorii:sia-ctv-digest-signature-field-policy:v1", "exclude_only_the_named_outer_digest_and_signature_fields"),
        ("decoder", "memorii:sia-ctv-decoder:v1", "strict_schema_decode_then_profile_reencode_byte_equal"),
    ]
    entries: list[dict[str, object]] = []
    for schema in coordinates:
        components = {name: _hash(domain, _record(name, policy, schema, design, inventory_digest)) for name, domain, policy in definitions}
        binding_values = (profile_id, version, profile, schema, version, components["schema_fingerprint"], components["enum_registry"], components["optional_field_policy"], components["numeric_encoding_spec_registry"], components["digest_signature_field_policy"])
        binding = _hash("memorii:sia-ctv-binding:v1", b"".join(_pack(value) for value in binding_values))
        entry_values = (*binding_values[:5], binding, *binding_values[5:], components["decoder"], "", "", "active")
        entry = _hash("memorii:sia-ctv-registry-entry:v1", b"".join(_pack(value) for value in entry_values))
        entries.append({"schema_id": schema, "components": components, "binding_digest": binding, "entry_digest": entry})
    registry = _hash("memorii:sia-ctv-profile-registry:v1", b"".join(_pack(value) for value in (profile_id, version, revision, grammar_digest, profile, str(len(entries)), *(str(entry["entry_digest"]) for entry in entries))))
    vectors = _key_table(document)
    if hashlib.sha256(b"memorii:sia-test-ed25519-seed:fixture-bootstrap-2:v1").hexdigest() != vectors[1][1]:
        raise ValueError("successor seed")
    for name, seed, public, message, signature in vectors:
        derived_public, derived_signature = _rfc8032(bytes.fromhex(seed), bytes.fromhex(message))
        if derived_public.hex() != public or derived_signature.hex() != signature:
            raise ValueError(f"RFC 8032 mismatch: {name}")
    key_vectors = [{"signer": name, "seed_hex": seed, "public_key_hex": public, "message_hex": message, "signature_hex": signature, "key_digest": _hash("memorii:sia-test-ed25519-public-key:v1", bytes.fromhex(public))} for name, seed, public, message, signature in vectors]
    result = {"format": "memorii-sia-c1-fixture-authority-v1", "design_document_digest": design, "grammar_bytes_hex": grammar.hex(), "grammar_digest": grammar_digest, "schema_inventory_bytes_hex": inventory.hex(), "schema_inventory_digest": inventory_digest, "profile_digest": profile, "entries": entries, "registry_digest": registry, "ed25519_vectors": key_vectors}
    return json.dumps(result, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii") + b"\n"


if __name__ == "__main__":
    repository = Path(__file__).parents[5]
    print(elaborate((repository / "docs/design/semantic_ingestion_architecture.md").read_bytes()).decode(), end="")
