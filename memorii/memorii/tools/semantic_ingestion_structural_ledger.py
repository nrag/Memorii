"""Frozen CGS structural-manifest ledger and digest primitives.

This module is deliberately small: the checked-in ledger remains the normative
input, while this production owner pins its identity and exposes only typed
field/domain contracts to derivation and authorization code.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value

FROZEN_LEDGER_SHA256 = "085921e6c4e995f0d6259c9f6f6eabeec3f1455bba344105ef0e16d24eb81671"
FROZEN_LEDGER_SCHEMA_ID = "TraceabilityStructuralManifestDerivationLedger.v1"
FROZEN_LEDGER_SCHEMA_VERSION = 1
FROZEN_LEDGER_GRAMMAR_REVISION = "structural-manifest-derivation-v1"


class StructuralLedgerError(ValueError):
    """Raised when the frozen ledger or a ledger-derived body is invalid."""


@dataclass(frozen=True)
class StructuralLedgerField:
    ordinal: int
    name: str
    source: str
    order: str
    digest_domain: str | None


@dataclass(frozen=True)
class StructuralManifestDerivationLedger:
    raw_bytes: bytes
    schema_id: str
    schema_version: int
    grammar_revision: str
    fields: tuple[StructuralLedgerField, ...]
    digest_domains: Mapping[str, bytes]

    @property
    def digest(self) -> str:
        return digest_ledger_bytes(self.raw_bytes)

    @property
    def coordinate(self) -> str:
        return f"structural_manifest_derivation_ledger/{self.schema_id}/{self.schema_version}/{self.digest}"

    @property
    def body_field_names(self) -> tuple[str, ...]:
        return tuple(field.name for field in self.fields)

    def domain(self, domain_id: str) -> bytes:
        try:
            return self.digest_domains[domain_id]
        except KeyError as exc:
            raise StructuralLedgerError("structural_ledger_domain_unknown") from exc

    def validate_body_shape(self, body: Mapping[str, Any]) -> None:
        if tuple(body) != self.body_field_names:
            raise StructuralLedgerError("structural_body_field_order_or_shape_invalid")
        if body["grammar_revision"] != self.grammar_revision:
            raise StructuralLedgerError("structural_body_grammar_revision_invalid")
        if body["derivation_ledger_schema_id"] != self.schema_id:
            raise StructuralLedgerError("structural_body_ledger_schema_invalid")
        if body["derivation_ledger_schema_version"] != self.schema_version:
            raise StructuralLedgerError("structural_body_ledger_version_invalid")
        if body["derivation_ledger_digest"] != self.digest:
            raise StructuralLedgerError("structural_body_ledger_digest_invalid")
        if body["derivation_ledger_coordinate"] != self.coordinate:
            raise StructuralLedgerError("structural_body_ledger_coordinate_invalid")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise StructuralLedgerError("structural_ledger_duplicate_key")
        result[key] = value
    return result


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"


def _load_canonical(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StructuralLedgerError("structural_ledger_json_invalid") from exc
    # The frozen v1 source itself is pretty-printed rather than compact.  Its
    # SHA-256 pin is therefore the canonicality boundary for this immutable
    # input; parsing still rejects duplicate keys before consumers inspect it.
    if not isinstance(value, dict):
        raise StructuralLedgerError("structural_ledger_not_canonical")
    return value


def _domain_bytes(value: object) -> bytes:
    if not isinstance(value, dict) or set(value) != {"domain_ascii_hex", "operands", "encoding"}:
        raise StructuralLedgerError("structural_ledger_domain_invalid")
    encoded = value["domain_ascii_hex"]
    if not isinstance(encoded, str):
        raise StructuralLedgerError("structural_ledger_domain_invalid")
    try:
        return bytes.fromhex(encoded)
    except ValueError as exc:
        raise StructuralLedgerError("structural_ledger_domain_invalid") from exc


def load_frozen_structural_manifest_ledger(raw: bytes) -> StructuralManifestDerivationLedger:
    """Load the one approved raw ledger; identity failure precedes derivation."""
    if sha256(raw).hexdigest() != FROZEN_LEDGER_SHA256:
        raise StructuralLedgerError("structural_ledger_identity_mismatch")
    value = _load_canonical(raw)
    required = {
        "canonical_bytes",
        "digest_domains",
        "digest_preimage",
        "envelope_contract",
        "fields",
        "grammar_revision",
        "input_contract",
        "ledger_digest_preimage",
        "ledger_id",
        "ledger_version",
        "owner",
        "required_rejections",
        "schema_id",
        "schema_version",
        "structural_body_digest",
    }
    if set(value) != required:
        raise StructuralLedgerError("structural_ledger_shape_invalid")
    if (
        value["schema_id"] != FROZEN_LEDGER_SCHEMA_ID
        or value["schema_version"] != FROZEN_LEDGER_SCHEMA_VERSION
        or value["grammar_revision"] != FROZEN_LEDGER_GRAMMAR_REVISION
    ):
        raise StructuralLedgerError("structural_ledger_coordinate_invalid")
    fields_value = value["fields"]
    if not isinstance(fields_value, list) or len(fields_value) != 29:
        raise StructuralLedgerError("structural_ledger_field_count_invalid")
    fields: list[StructuralLedgerField] = []
    for expected_ordinal, item in enumerate(fields_value, start=1):
        if not isinstance(item, dict) or set(item) != {"ordinal", "name", "source", "order", "digest_domain"}:
            raise StructuralLedgerError("structural_ledger_field_invalid")
        if item["ordinal"] != expected_ordinal or not all(
            isinstance(item[key], str) for key in ("name", "source", "order")
        ):
            raise StructuralLedgerError("structural_ledger_field_invalid")
        domain = item["digest_domain"]
        if domain is not None and not isinstance(domain, str):
            raise StructuralLedgerError("structural_ledger_field_invalid")
        fields.append(StructuralLedgerField(expected_ordinal, item["name"], item["source"], item["order"], domain))
    if len({field.name for field in fields}) != 29:
        raise StructuralLedgerError("structural_ledger_field_duplicate")
    domains_value = value["digest_domains"]
    if not isinstance(domains_value, dict):
        raise StructuralLedgerError("structural_ledger_domains_invalid")
    domains = {name: _domain_bytes(domain) for name, domain in domains_value.items() if isinstance(name, str)}
    if len(domains) != len(domains_value) or any(
        field.digest_domain not in domains for field in fields if field.digest_domain is not None
    ):
        raise StructuralLedgerError("structural_ledger_domain_invalid")
    return StructuralManifestDerivationLedger(
        raw, value["schema_id"], value["schema_version"], value["grammar_revision"], tuple(fields), domains
    )


def frozen_ledger_path() -> Path:
    return (
        Path(__file__).parents[3]
        / "docs/design/semantic_ingestion/traceability_golden_vectors/structural_manifest_derivation_ledger-v1.json"
    )


def load_checked_in_frozen_structural_manifest_ledger() -> StructuralManifestDerivationLedger:
    return load_frozen_structural_manifest_ledger(frozen_ledger_path().read_bytes())


def _length_prefixed_digest(domain: bytes, value: bytes) -> str:
    return sha256(domain + len(value).to_bytes(8, "big") + value).hexdigest()


def digest_raw_bytes(ledger: StructuralManifestDerivationLedger, domain_id: str, value: bytes) -> str:
    """Digest a raw operand exactly as declared by its frozen domain."""
    domain = ledger.domain(domain_id)
    if domain_id in {"raw_design", "raw_registry"}:
        return sha256(domain + value).hexdigest()
    if domain_id == "ledger":
        return _length_prefixed_digest(domain, value)
    raise StructuralLedgerError("structural_ledger_domain_operand_invalid")


def digest_typed_value(ledger: StructuralManifestDerivationLedger, domain_id: str, value: Any) -> str:
    if domain_id in {"raw_design", "raw_registry", "ledger", "outer_envelope"}:
        ledger.domain(domain_id)
        raise StructuralLedgerError("structural_ledger_domain_operand_invalid")
    return _length_prefixed_digest(ledger.domain(domain_id), encode_typed_value(value))


def digest_ledger_bytes(raw: bytes) -> str:
    # `ledger` is intentionally available without a parsed ledger, so identity
    # validation can calculate the expected coordinate before elaboration.
    return sha256(
        b"memorii:sia-traceability-structural-manifest-derivation-ledger:v1\0" + len(raw).to_bytes(8, "big") + raw
    ).hexdigest()
