"""Fixture-only C1 elaborator.  It deliberately has no Memorii dependencies."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

_DESIGN_ID_DOMAIN = b"semantic-ingestion-traceability\0"
_GRAMMAR_DOMAIN = b"memorii:sia-ctv-grammar:v1\0"
_INVENTORY_DOMAIN = b"memorii:sia-traceability-schema-inventory:v1\0"
_MARKERS = ("SIA-CTV-GRAMMAR-V1", "SIA-TRACEABILITY-SCHEMA-INVENTORY-V1")


def _digest(domain: bytes, value: bytes) -> str:
    return hashlib.sha256(domain + value).hexdigest()


def _lp(value: str | bytes) -> bytes:
    raw = value.encode("ascii") if isinstance(value, str) else value
    return len(raw).to_bytes(8, "big") + raw


def _validate_design(design: bytes) -> None:
    if not design or design.startswith(b"\xef\xbb\xbf") or b"\0" in design or b"\r" in design:
        raise ValueError("raw design bytes violate the frozen preflight")
    if not design.endswith(b"\n") or design.endswith(b"\n\n"):
        raise ValueError("raw design must end in exactly one final LF")
    try:
        design.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("raw design must be strict UTF-8") from error
    for marker in _MARKERS:
        for edge in ("BEGIN", "END"):
            token = f"[{marker}-{edge}]".encode("ascii")
            line = b"`" + token + b"`\n"
            if design.splitlines().count(line.rstrip(b"\n")) != 1:
                raise ValueError(f"{marker} must have one standalone {edge} marker")
        begin = f"`[{marker}-BEGIN]`\n```text\n".encode("ascii")
        end = f"```\n`[{marker}-END]`\n".encode("ascii")
        if design.count(begin) != 1 or design.count(end) != 1:
            raise ValueError(f"{marker} must use exact adjacent text fences")


def _marked_bytes(design: bytes, marker: str) -> bytes:
    text = design.decode("utf-8")
    pattern = rf"^`\[{re.escape(marker)}-BEGIN\]`\n```text\n(.*?)^```\n`\[{re.escape(marker)}-END\]`$"
    matches = re.findall(pattern, text, flags=re.MULTILINE | re.DOTALL)
    if len(matches) != 1:
        raise ValueError(f"{marker} must have one fenced block")
    try:
        return matches[0].encode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError(f"{marker} content must be exact ASCII") from error


def _source(component: str, schema_id: str, design_digest: str, inventory_digest: str, policy: str) -> bytes:
    item = {
        "component": component,
        "design_document_digest": design_digest,
        "policy": policy,
        "profile_id": "semantic_ingestion_typed_value",
        "profile_version": 1,
        "schema_id": schema_id,
        "schema_inventory_digest": inventory_digest,
        "schema_version": 1,
    }
    return json.dumps(item, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii") + b"\n"


def _signature_vectors(design: bytes) -> tuple[tuple[str, str, str, str, str], ...]:
    row = re.compile(
        rb"^\| `(?P<signer>fixture-(?:bootstrap|recovery)-[12])` "
        rb"\| `(?P<seed>[0-9a-f]+)` \| `(?P<public>[0-9a-f]+)` "
        rb"\| (?P<message>empty|`[0-9a-f]+`) \| `(?P<signature>[0-9a-f]+)` \|$",
        re.MULTILINE,
    )
    vectors = tuple(
        (
            match["signer"].decode("ascii"),
            match["seed"].decode("ascii"),
            match["public"].decode("ascii"),
            "" if match["message"] == b"empty" else match["message"][1:-1].decode("ascii"),
            match["signature"].decode("ascii"),
        )
        for match in row.finditer(design)
    )
    expected_signers = (
        "fixture-bootstrap-1",
        "fixture-bootstrap-2",
        "fixture-recovery-1",
        "fixture-recovery-2",
    )
    if tuple(vector[0] for vector in vectors) != expected_signers:
        raise ValueError("fixed Ed25519 signer table is missing, duplicated, or reordered")
    return vectors


def _ed25519(seed: bytes, message: bytes) -> tuple[bytes, bytes]:
    # RFC 8032, section 5.1.  This compact implementation is intentionally
    # local to the fixture elaborator so test keys cannot become runtime code.
    q, order = 2**255 - 19, 2**252 + 27742317777372353535851937790883648493
    d = -121665 * pow(121666, q - 2, q) % q
    i = pow(2, (q - 1) // 4, q)
    by = 4 * pow(5, q - 2, q) % q
    bx = pow((by * by - 1) * pow(d * by * by + 1, q - 2, q), (q + 3) // 8, q)
    if (bx * bx - (by * by - 1) * pow(d * by * by + 1, q - 2, q)) % q:
        bx = bx * i % q
    if bx & 1:
        bx = q - bx

    def add(left: tuple[int, int], right: tuple[int, int]) -> tuple[int, int]:
        x1, y1 = left
        x2, y2 = right
        x3 = (x1 * y2 + x2 * y1) * pow(1 + d * x1 * x2 * y1 * y2, q - 2, q) % q
        y3 = (y1 * y2 + x1 * x2) * pow(1 - d * x1 * x2 * y1 * y2, q - 2, q) % q
        return x3, y3

    def scalar(value: int) -> tuple[int, int]:
        point, base = (0, 1), (bx, by)
        while value:
            if value & 1:
                point = add(point, base)
            base = add(base, base)
            value >>= 1
        return point

    def enc(point: tuple[int, int]) -> bytes:
        x, y = point
        return (y | ((x & 1) << 255)).to_bytes(32, "little")

    h = hashlib.sha512(seed).digest()
    secret = int.from_bytes(h[:32], "little") & ((1 << 254) - 8) | (1 << 254)
    prefix = h[32:]
    public = enc(scalar(secret))
    r = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % order
    encoded_r = enc(scalar(r))
    s = (r + int.from_bytes(hashlib.sha512(encoded_r + public + message).digest(), "little") * secret) % order
    return public, encoded_r + s.to_bytes(32, "little")


def elaborate(design_bytes: bytes) -> bytes:
    _validate_design(design_bytes)
    grammar = _marked_bytes(design_bytes, "SIA-CTV-GRAMMAR-V1")
    inventory = _marked_bytes(design_bytes, "SIA-TRACEABILITY-SCHEMA-INVENTORY-V1")
    schemas = inventory.decode("ascii").splitlines()
    if len(schemas) != 52 or schemas != sorted(schemas) or len(set(schemas)) != len(schemas):
        raise ValueError("C1 inventory must be 52 unique Unicode-scalar-sorted coordinates")
    design_digest = _digest(_DESIGN_ID_DOMAIN, design_bytes)
    grammar_digest = _digest(_GRAMMAR_DOMAIN, grammar)
    inventory_digest = _digest(_INVENTORY_DOMAIN, inventory)
    profile_id, version, revision = "semantic_ingestion_typed_value", "1", "sia-ctv-grammar-v1"
    profile_digest = _digest(b"memorii:sia-ctv-profile:v1\0", b"".join(map(_lp, (profile_id, version, revision, grammar_digest, grammar))))
    domains = (
        ("schema_fingerprint", b"memorii:sia-ctv-schema-fingerprint:v1\0", "closed_declared_schema_and_transitive_types"),
        ("enum_registry", b"memorii:sia-ctv-enum-registry:v1\0", "exact_literal_and_enum_members_in_registered_schema"),
        ("optional_field_policy", b"memorii:sia-ctv-optional-field-policy:v1\0", "exact_required_omittable_nullable_state_in_registered_schema"),
        ("numeric_encoding_spec_registry", b"memorii:sia-ctv-numeric-spec-registry:v1\0", "exact_field_constraints_and_no_ambient_numeric_default"),
        ("digest_signature_field_policy", b"memorii:sia-ctv-digest-signature-field-policy:v1\0", "exclude_only_the_named_outer_digest_and_signature_fields"),
        ("decoder", b"memorii:sia-ctv-decoder:v1\0", "strict_schema_decode_then_profile_reencode_byte_equal"),
    )
    entries = []
    for schema in schemas:
        components = {name: _digest(domain, _source(name, schema, design_digest, inventory_digest, policy)) for name, domain, policy in domains}
        binding = _digest(b"memorii:sia-ctv-binding:v1\0", b"".join(map(_lp, (profile_id, version, profile_digest, schema, version, components["schema_fingerprint"], components["enum_registry"], components["optional_field_policy"], components["numeric_encoding_spec_registry"], components["digest_signature_field_policy"]))))
        entry = _digest(b"memorii:sia-ctv-registry-entry:v1\0", b"".join(map(_lp, (profile_id, version, profile_digest, schema, version, binding, components["schema_fingerprint"], components["enum_registry"], components["optional_field_policy"], components["numeric_encoding_spec_registry"], components["digest_signature_field_policy"], components["decoder"], "", "", "active"))))
        entries.append({"schema_id": schema, "components": components, "binding_digest": binding, "entry_digest": entry})
    registry_digest = _digest(b"memorii:sia-ctv-profile-registry:v1\0", b"".join(map(_lp, (profile_id, version, revision, grammar_digest, profile_digest, str(len(entries)), *(item["entry_digest"] for item in entries)))))
    vectors = []
    for signer, seed_hex, public_hex, message_hex, signature_hex in _signature_vectors(design_bytes):
        try:
            widths = tuple(len(bytes.fromhex(value)) for value in (seed_hex, public_hex, signature_hex))
        except ValueError as error:
            raise ValueError(f"invalid fixed Ed25519 hex: {signer}") from error
        if widths != (32, 32, 64):
            raise ValueError(f"invalid fixed Ed25519 width: {signer}")
        public, signature = _ed25519(bytes.fromhex(seed_hex), bytes.fromhex(message_hex))
        if public.hex() != public_hex or signature.hex() != signature_hex:
            raise ValueError(f"RFC 8032 mismatch: {signer}")
        vectors.append({"signer": signer, "seed_hex": seed_hex, "public_key_hex": public_hex, "message_hex": message_hex, "signature_hex": signature_hex, "key_digest": _digest(b"memorii:sia-test-ed25519-public-key:v1\0", public)})
    successor_seed = hashlib.sha256(b"memorii:sia-test-ed25519-seed:fixture-bootstrap-2:v1").digest()
    if successor_seed.hex() != vectors[1]["seed_hex"]:
        raise ValueError("successor bootstrap seed mismatch")
    result = {"format": "memorii-sia-c1-fixture-authority-v1", "design_document_digest": design_digest, "grammar_bytes_hex": grammar.hex(), "grammar_digest": grammar_digest, "schema_inventory_bytes_hex": inventory.hex(), "schema_inventory_digest": inventory_digest, "profile_digest": profile_digest, "entries": entries, "registry_digest": registry_digest, "ed25519_vectors": vectors}
    return json.dumps(result, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii") + b"\n"


if __name__ == "__main__":
    root = Path(__file__).parents[5]
    print(elaborate((root / "docs/design/semantic_ingestion_architecture.md").read_bytes()).decode(), end="")
