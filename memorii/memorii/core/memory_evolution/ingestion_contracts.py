"""Closed canonical typed-value boundary for semantic-ingestion artifacts.

This intentionally owns only the deterministic wire algebra.  Release and
acceptance code supplies the registered schema field set and signature policy;
it must not select a profile or silently coerce a decoded value.
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta  # type: ignore[attr-defined]
from hashlib import sha256
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

_INTEGER = re.compile(r"(?:0|-?[1-9][0-9]*)\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_PROFILE_ID = "semantic_ingestion_typed_value"
_ARTIFACT_DOMAIN = b"semantic-ingestion-canonical-artifact"
_PROFILE_VERSION = 2
_PROFILE_DIGEST = "9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f"
_OUTER_ENVELOPE_SCHEMA_ID = "CanonicalEncodedArtifact.v1"
_OUTER_ENVELOPE_BINDING_DIGEST = "39222b18e67ffe8f679943676a46a464c804bb2ef9d0e3fd28d27a590fe3fde1"
_DELIVERY_ID_MAX_UTF8_BYTES = 1024


def _digest(domain: bytes, *parts: bytes) -> str:
    """Hash explicit length-delimited fields so identity inputs cannot alias."""

    return sha256(_length_prefixed(domain, *parts)).hexdigest()


def normalize_delivery_id(value: str) -> str:
    """Validate one public delivery ID without changing a single accepted byte.

    This is deliberately not a cosmetic normalizer: trimming, case folding,
    NFC/NFD conversion, and delimiter rewriting all change delivery identity.
    """

    if not isinstance(value, str):
        raise ValueError("delivery_id must be a string")
    try:
        encoded = value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise ValueError("delivery_id must contain only Unicode scalar values") from exc
    if not encoded or len(encoded) > _DELIVERY_ID_MAX_UTF8_BYTES or not value.strip():
        raise ValueError("delivery_id must be nonblank UTF-8 within the byte limit")
    return value


def derive_composite_child_delivery_id(parent_delivery_id: str, child_kind: str) -> str:
    """Derive a domain-separated child coordinate without delimiter concatenation."""

    parent = normalize_delivery_id(parent_delivery_id).encode("utf-8")
    if not child_kind or child_kind.strip() != child_kind:
        raise ValueError("composite child kind must be non-empty and exact")
    return f"composite:v1:{_digest(b'memorii.semantic-ingestion.composite-child.v1', parent, child_kind.encode())}"


def is_reserved_composite_delivery_id(value: str) -> bool:
    return value.startswith("composite:v1:")


class DeliveryPrincipalBinding(BaseModel):
    """Stable authenticated principal coordinate, excluding session authority."""

    principal_subject_id: str = Field(min_length=1)
    tenant_partition_id: str = Field(min_length=1)
    provider_identity: str = Field(min_length=1)
    binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> DeliveryPrincipalBinding:
        expected = _digest(
            b"memorii.semantic-ingestion.delivery-principal.v1",
            self.principal_subject_id.encode(),
            self.tenant_partition_id.encode(),
            self.provider_identity.encode(),
        )
        if self.binding_digest != expected:
            raise ValueError("delivery principal binding digest mismatch")
        return self

    @classmethod
    def create(
        cls, *, principal_subject_id: str, tenant_partition_id: str, provider_identity: str
    ) -> DeliveryPrincipalBinding:
        for value in (principal_subject_id, tenant_partition_id, provider_identity):
            if not value:
                raise ValueError("delivery principal binding fields must be non-empty")
        return cls(
            principal_subject_id=principal_subject_id,
            tenant_partition_id=tenant_partition_id,
            provider_identity=provider_identity,
            binding_digest=_digest(
                b"memorii.semantic-ingestion.delivery-principal.v1",
                principal_subject_id.encode(),
                tenant_partition_id.encode(),
                provider_identity.encode(),
            ),
        )


class NormalizedDeliveryId(BaseModel):
    normalization_contract_version: int = Field(default=1, ge=1, le=1)
    value: str
    strict_utf8_bytes: bytes
    utf8_byte_length: int = Field(ge=1, le=_DELIVERY_ID_MAX_UTF8_BYTES)
    normalized_delivery_id_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_normalized(self) -> NormalizedDeliveryId:
        if normalize_delivery_id(self.value) != self.value or self.strict_utf8_bytes != self.value.encode("utf-8"):
            raise ValueError("delivery ID bytes must be exact")
        if self.utf8_byte_length != len(self.strict_utf8_bytes):
            raise ValueError("delivery ID byte length mismatch")
        if self.normalized_delivery_id_digest != _digest(
            b"memorii.semantic-ingestion.delivery-id.v1", self.strict_utf8_bytes
        ):
            raise ValueError("delivery ID digest mismatch")
        return self

    @classmethod
    def from_public(cls, value: str) -> NormalizedDeliveryId:
        exact = normalize_delivery_id(value)
        encoded = exact.encode("utf-8")
        return cls(
            value=exact,
            strict_utf8_bytes=encoded,
            utf8_byte_length=len(encoded),
            normalized_delivery_id_digest=_digest(b"memorii.semantic-ingestion.delivery-id.v1", encoded),
        )


class DeliveryIdentity(BaseModel):
    delivery_principal_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_delivery_id: NormalizedDeliveryId
    delivery_key_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_delivery_key(self) -> DeliveryIdentity:
        expected = _digest(
            b"memorii.semantic-ingestion.delivery-key.v1",
            self.delivery_principal_binding_digest.encode(),
            self.normalized_delivery_id.normalized_delivery_id_digest.encode(),
        )
        if self.delivery_key_digest != expected:
            raise ValueError("delivery key digest mismatch")
        return self

    @classmethod
    def create(cls, binding: DeliveryPrincipalBinding, delivery_id: str) -> DeliveryIdentity:
        normalized = NormalizedDeliveryId.from_public(delivery_id)
        return cls(
            delivery_principal_binding_digest=binding.binding_digest,
            normalized_delivery_id=normalized,
            delivery_key_digest=_digest(
                b"memorii.semantic-ingestion.delivery-key.v1",
                binding.binding_digest.encode(),
                normalized.normalized_delivery_id_digest.encode(),
            ),
        )


class RequiredOutcomeScopeSet(BaseModel):
    """Server-derived complete scope names; caller scope data is never accepted."""

    tenant_partition_id: str = Field(min_length=1)
    scopes: tuple[str, ...] = ()
    required_scope_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_scope_set(self) -> RequiredOutcomeScopeSet:
        if tuple(sorted(set(self.scopes))) != self.scopes or any(not scope for scope in self.scopes):
            raise ValueError("required scopes must be ordered, unique, and non-empty")
        expected = _digest(
            b"memorii.semantic-ingestion.required-scopes.v1",
            self.tenant_partition_id.encode(),
            *(scope.encode() for scope in self.scopes),
        )
        if self.required_scope_set_digest != expected:
            raise ValueError("required scope digest mismatch")
        return self

    @classmethod
    def create(
        cls, *, tenant_partition_id: str, scopes: set[str] | tuple[str, ...] | list[str]
    ) -> RequiredOutcomeScopeSet:
        ordered = tuple(sorted(set(scopes)))
        return cls(
            tenant_partition_id=tenant_partition_id,
            scopes=ordered,
            required_scope_set_digest=_digest(
                b"memorii.semantic-ingestion.required-scopes.v1",
                tenant_partition_id.encode(),
                *(scope.encode() for scope in ordered),
            ),
        )


class AuthenticatedIngressContext(BaseModel):
    delivery_principal_binding: DeliveryPrincipalBinding
    # The host derives this from authenticated message governance.  It is
    # deliberately distinct from the current authorization snapshot: callers
    # may have additional scopes, but cannot shrink retained-source coverage.
    required_outcome_scopes: RequiredOutcomeScopeSet
    current_authorized_scopes: RequiredOutcomeScopeSet
    language_declaration: str | None = None
    language_evidence_kind: Literal["authenticated_host_declaration", "missing", "untrusted", "mismatched"] = "missing"
    language_evidence_trust: Literal["trusted", "missing", "untrusted", "mismatched"] = "missing"
    language_governance_agreement: Literal["agrees", "missing", "disagrees"] = "missing"
    semantic_egress_governance: AuthenticatedSemanticEgressGovernance | None = None
    semantic_source_authority: AuthenticatedSemanticSourceAuthority | None = None
    semantic_source_interval: AuthenticatedSemanticSourceInterval | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_tenant(self) -> AuthenticatedIngressContext:
        tenant = self.delivery_principal_binding.tenant_partition_id
        if (
            self.current_authorized_scopes.tenant_partition_id != tenant
            or self.required_outcome_scopes.tenant_partition_id != tenant
        ):
            raise ValueError("authorized and required scopes tenant must match authenticated principal")
        evidence = (
            self.language_evidence_kind,
            self.language_evidence_trust,
            self.language_governance_agreement,
        )
        if self.language_declaration is None and evidence not in {
            ("missing", "missing", "missing"),
            ("untrusted", "untrusted", "missing"),
        }:
            raise ValueError("language evidence tuple is invalid")
        if self.language_declaration is not None and evidence not in {
            ("authenticated_host_declaration", "trusted", "agrees"),
            ("mismatched", "mismatched", "disagrees"),
        }:
            raise ValueError("language evidence tuple is invalid")
        return self


class AuthenticatedSemanticSourceAuthority(BaseModel):
    """Host-authenticated semantic authority metadata before source admission binds it."""

    authority_class: str = Field(min_length=1)
    authenticated_provenance_class: str = Field(min_length=1)
    governing_principal_id: str | None = None
    policy_revision: str = Field(min_length=1)
    provenance_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class AuthenticatedSemanticSourceInterval(BaseModel):
    """Host-authenticated source interval metadata before source binding."""

    start: datetime
    end: datetime | None = None
    authority_basis: Literal["server_source_metadata", "authenticated_external_interval"]
    provenance_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_revision: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_interval(self) -> AuthenticatedSemanticSourceInterval:
        if self.end is not None and self.end <= self.start:
            raise ValueError("authenticated source interval end must be later than start")
        return self


class AuthenticatedSemanticEgressGovernance(BaseModel):
    """Host-authenticated, source-classification input for remote M3 use.

    It intentionally contains no source identity: admission supplies the exact
    retained source bytes/digest, preventing callers from swapping an event
    metadata value into a provider authorization.
    """

    classification: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    region: str = Field(min_length=1)
    retention_mode: str = Field(min_length=1)
    training_use: bool

    model_config = ConfigDict(extra="forbid", frozen=True)


class AuthenticatedHostIngress(BaseModel):
    """Opaque host-authenticated handoff, never reconstructed from event fields."""

    provider_identity: str = Field(min_length=1)
    principal_handle: object
    session_handle: object
    received_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class AuthenticatedIngressContextResolver(Protocol):
    def resolve(self, host_ingress: AuthenticatedHostIngress, server_time: datetime) -> AuthenticatedIngressContext: ...


class AuthenticatedIngressResolutionError(ValueError):
    """Expected denial from the external host authentication boundary."""


class OperationFenceBinding(BaseModel):
    operation_id: str = Field(min_length=1)
    operation_fence_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    delivery_identity: DeliveryIdentity
    delivery_principal_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    delivery_key_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    allocation_namespace_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_binding(self) -> OperationFenceBinding:
        if self.delivery_principal_binding_digest != self.delivery_identity.delivery_principal_binding_digest:
            raise ValueError("operation fence principal binding mismatch")
        if self.delivery_key_digest != self.delivery_identity.delivery_key_digest:
            raise ValueError("operation fence delivery key mismatch")
        common = (
            self.delivery_key_digest.encode(),
            self.source_id.encode(),
            self.source_digest.encode(),
            self.operation_id.encode(),
        )
        if self.operation_fence_id != _digest(b"memorii.semantic-ingestion.operation-fence.v1", *common):
            raise ValueError("operation fence ID mismatch")
        if self.allocation_namespace_id != _digest(b"memorii.semantic-ingestion.allocation-namespace.v1", *common):
            raise ValueError("allocation namespace mismatch")
        values = (
            self.operation_id,
            self.operation_fence_id,
            self.source_id,
            self.source_digest,
            self.delivery_principal_binding_digest,
            self.delivery_key_digest,
            self.allocation_namespace_id,
        )
        if self.binding_digest != _digest(
            b"memorii.semantic-ingestion.operation-fence-binding.v1", *(value.encode() for value in values)
        ):
            raise ValueError("operation fence binding digest mismatch")
        return self

    @classmethod
    def create(
        cls, *, operation_id: str, source_id: str, source_digest: str, delivery_identity: DeliveryIdentity
    ) -> OperationFenceBinding:
        common = (
            delivery_identity.delivery_key_digest.encode(),
            source_id.encode(),
            source_digest.encode(),
            operation_id.encode(),
        )
        fence = _digest(b"memorii.semantic-ingestion.operation-fence.v1", *common)
        allocation = _digest(b"memorii.semantic-ingestion.allocation-namespace.v1", *common)
        values = (
            operation_id,
            fence,
            source_id,
            source_digest,
            delivery_identity.delivery_principal_binding_digest,
            delivery_identity.delivery_key_digest,
            allocation,
        )
        return cls(
            operation_id=operation_id,
            operation_fence_id=fence,
            source_id=source_id,
            source_digest=source_digest,
            delivery_identity=delivery_identity,
            delivery_principal_binding_digest=delivery_identity.delivery_principal_binding_digest,
            delivery_key_digest=delivery_identity.delivery_key_digest,
            allocation_namespace_id=allocation,
            binding_digest=_digest(
                b"memorii.semantic-ingestion.operation-fence-binding.v1", *(value.encode() for value in values)
            ),
        )


class SemanticWriterAdmission(BaseModel):
    admission_id: str = Field(min_length=1)
    writer_namespace: Literal["semantic_ingestion"]
    active_runtime_mode: Literal["legacy_pre_cutover", "verified_semantic", "evidence_only"]
    active_writer_implementation_fingerprint: str = Field(min_length=1)
    accepted_graph_schema_fingerprint: str = Field(min_length=1)
    writer_epoch: int = Field(ge=1)
    activated_at: datetime
    previous_admission_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    admission_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticWriterCommitBinding(BaseModel):
    admission_id: str = Field(min_length=1)
    admission_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    writer_namespace: Literal["semantic_ingestion"]
    expected_writer_epoch: int = Field(ge=1)
    runtime_mode: Literal["legacy_pre_cutover", "verified_semantic", "evidence_only"]
    writer_implementation_fingerprint: str = Field(min_length=1)
    graph_schema_fingerprint: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticRecordOwnershipManifest(BaseModel):
    manifest_revision: str = Field(min_length=1)
    governed_record_kinds: frozenset[str]
    semantic_store_methods: frozenset[str]
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class CanonicalTypedValueError(ValueError):
    """Raised when a typed artifact has no unique canonical representation."""


@dataclass(frozen=True)
class CanonicalTypedValueProfileBinding:
    profile_id: str
    profile_version: int
    profile_digest: str
    schema_id: str
    schema_version: int
    binding_digest: str

    def validate(self) -> None:
        if (
            self.profile_id != _PROFILE_ID
            or isinstance(self.profile_version, bool)
            or self.profile_version < 1
            or isinstance(self.schema_version, bool)
            or self.schema_version < 1
            or not self.schema_id
            or not _HEX.fullmatch(self.profile_digest)
            or not _HEX.fullmatch(self.binding_digest)
        ):
            raise CanonicalTypedValueError("canonical_binding_invalid")

    def as_value(self) -> dict[str, object]:
        self.validate()
        return {
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "profile_digest": self.profile_digest,
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "binding_digest": self.binding_digest,
        }


@dataclass(frozen=True)
class CanonicalEncodedArtifact:
    binding: CanonicalTypedValueProfileBinding
    canonical_value_bytes: bytes
    canonical_value_digest: str
    artifact_digest: str


def canonical_encoded_artifact_binding() -> CanonicalTypedValueProfileBinding:
    """Return the frozen binding for the CTV outer-envelope model.

    The outer value is a `CanonicalEncodedArtifact.v1` CTV model, not a JSON
    transport wrapper.  Its binding is a frozen authority coordinate; callers
    use it for registry/vector validation while the model's inner `binding`
    selects the body decoder.
    """
    return CanonicalTypedValueProfileBinding(
        _PROFILE_ID,
        _PROFILE_VERSION,
        _PROFILE_DIGEST,
        _OUTER_ENVELOPE_SCHEMA_ID,
        1,
        _OUTER_ENVELOPE_BINDING_DIGEST,
    )


def _scalar(value: str) -> None:
    # The C implementation performs the same strict scalar validation without
    # walking every character in Python.  Structural manifests contain the
    # complete design text, so this check must remain bounded by transport
    # bytes rather than quadratic-ish repeated Python iteration.
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise CanonicalTypedValueError("canonical_unicode_scalar_invalid") from exc


def _json(value: Any, *, check: Callable[[], None] | None = None) -> bytes:
    """Encode JSON with a fixed UTF-8 scalar and key-order policy."""
    if check is not None:
        check()
    if value is None:
        return b"null"
    if value is True:
        return b"true"
    if value is False:
        return b"false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value).encode("ascii")
    if isinstance(value, str):
        _scalar(value)
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if isinstance(value, list):
        return b"[" + b",".join(_json(item, check=check) for item in value) + b"]"
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise CanonicalTypedValueError("canonical_map_key_invalid")
        for key in value:
            _scalar(key)
        keys = sorted(value, key=lambda key: _json(key, check=check))
        return b"{" + b",".join(_json(key, check=check) + b":" + _json(value[key], check=check) for key in keys) + b"}"
    raise CanonicalTypedValueError("canonical_json_value_invalid")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CanonicalTypedValueError("canonical_duplicate_key")
        result[key] = value
    return result


def _strict_json(raw: bytes) -> Any:
    try:
        decoded = raw.decode("utf-8")
        _scalar(decoded)
        value = json.loads(
            decoded,
            object_pairs_hook=_pairs,
            parse_float=lambda _: (_ for _ in ()).throw(CanonicalTypedValueError("canonical_float_forbidden")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CanonicalTypedValueError("canonical_bytes_invalid") from exc
    if _json(value) != raw:
        raise CanonicalTypedValueError("canonical_reencode_mismatch")
    return value


def _integer(value: object) -> int:
    if not isinstance(value, str) or not _INTEGER.fullmatch(value):
        raise CanonicalTypedValueError("canonical_integer_invalid")
    return int(value)


def _normalized_typed_json(value: Any, *, check: Callable[[], None] | None = None) -> Any:
    """Return the JSON tree for a CTV value before its single final encoding.

    Nested CTV members are already JSON-compatible trees.  Keeping them in
    that form avoids repeatedly serializing a child only to parse it back with
    ``json.loads`` before serializing the parent.
    """
    if check is not None:
        check()
    if value is None or isinstance(value, (bool, str)):
        if isinstance(value, str):
            _scalar(value)
        return value
    if isinstance(value, int):
        return {"$type": "integer", "value": str(value)}
    if isinstance(value, bytes):
        return {"$type": "bytes", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise CanonicalTypedValueError("canonical_datetime_naive")
        utc = value.astimezone(UTC)
        return {
            "$type": "datetime",
            "value": utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond:06d}Z",
        }
    if isinstance(value, timedelta):
        microseconds = value.days * 86_400_000_000 + value.seconds * 1_000_000 + value.microseconds
        if not -(2**63) <= microseconds < 2**63:
            raise CanonicalTypedValueError("canonical_duration_overflow")
        return {"$type": "duration_microseconds", "value": str(microseconds)}
    if isinstance(value, tuple):
        return {"$type": "tuple", "items": [_normalized_typed_json(item, check=check) for item in value]}
    if isinstance(value, list):
        return {"$type": "list", "items": [_normalized_typed_json(item, check=check) for item in value]}
    if isinstance(value, (set, frozenset)):
        normalized_items = [_normalized_typed_json(item, check=check) for item in value]
        items = sorted((_json(item), item) for item in normalized_items)
        if len({encoded for encoded, _ in items}) != len(items):
            raise CanonicalTypedValueError("canonical_set_duplicate")
        return {
            "$type": "frozenset" if isinstance(value, frozenset) else "set",
            "items": [item for _, item in items],
        }
    if isinstance(value, dict):
        entries = []
        for key in sorted(value, key=lambda item: _json(item)):
            if not isinstance(key, str):
                raise CanonicalTypedValueError("canonical_map_key_invalid")
            entries.append([key, _normalized_typed_json(value[key], check=check)])
        return {"$type": "map", "entries": entries}
    raise CanonicalTypedValueError("canonical_value_type_invalid")


def encode_typed_value(value: Any, *, check: Callable[[], None] | None = None) -> bytes:
    """Encode the closed CTV algebra; no runtime numeric coercions are allowed."""
    return _json(
        _normalized_typed_json(value, check=check),
        check=check,
    )


def decode_typed_value(raw: bytes) -> Any:
    value = _strict_json(raw)
    if value is None or isinstance(value, (bool, str)):
        return value
    if not isinstance(value, dict) or not isinstance(value.get("$type"), str):
        raise CanonicalTypedValueError("canonical_tag_invalid")
    tag = value["$type"]
    if tag == "integer" and set(value) == {"$type", "value"}:
        result = _integer(value["value"])
    elif tag == "datetime" and set(value) == {"$type", "value"} and isinstance(value["value"], str):
        spelling = value["value"]
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z", spelling):
            raise CanonicalTypedValueError("canonical_datetime_invalid")
        try:
            result = datetime.strptime(spelling, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
        except ValueError as exc:
            raise CanonicalTypedValueError("canonical_datetime_invalid") from exc
    elif tag == "duration_microseconds" and set(value) == {"$type", "value"}:
        microseconds = _integer(value["value"])
        if not -(2**63) <= microseconds < 2**63:
            raise CanonicalTypedValueError("canonical_duration_overflow")
        result = timedelta(microseconds=microseconds)
    elif tag == "bytes" and set(value) == {"$type", "value"} and isinstance(value["value"], str):
        try:
            result = base64.b64decode(value["value"], validate=True)
        except ValueError as exc:
            raise CanonicalTypedValueError("canonical_bytes_base64_invalid") from exc
        if base64.b64encode(result).decode("ascii") != value["value"]:
            raise CanonicalTypedValueError("canonical_bytes_base64_invalid")
    elif (
        tag in {"list", "tuple", "set", "frozenset"}
        and set(value) == {"$type", "items"}
        and isinstance(value["items"], list)
    ):
        items = [decode_typed_value(_json(item)) for item in value["items"]]
        if tag in {"set", "frozenset"}:
            encoded = [encode_typed_value(item) for item in items]
            if encoded != sorted(encoded) or len(set(encoded)) != len(encoded):
                raise CanonicalTypedValueError("canonical_set_order_invalid")
            result = frozenset(items) if tag == "frozenset" else set(items)
        else:
            result = tuple(items) if tag == "tuple" else items
    elif tag == "map" and set(value) == {"$type", "entries"} and isinstance(value["entries"], list):
        result = {}
        prior: bytes | None = None
        for pair in value["entries"]:
            if not isinstance(pair, list) or len(pair) != 2 or not isinstance(pair[0], str):
                raise CanonicalTypedValueError("canonical_map_entry_invalid")
            key_bytes = _json(pair[0])
            if prior is not None and key_bytes <= prior:
                raise CanonicalTypedValueError("canonical_map_order_invalid")
            prior = key_bytes
            result[pair[0]] = decode_typed_value(_json(pair[1]))
    else:
        raise CanonicalTypedValueError("canonical_tag_invalid")
    if encode_typed_value(result) != raw:
        raise CanonicalTypedValueError("canonical_reencode_mismatch")
    return result


def _length_prefixed(*parts: bytes) -> bytes:
    return b"".join(len(part).to_bytes(8, "big") + part for part in parts)


def artifact_preimage(binding: CanonicalTypedValueProfileBinding, canonical_value_bytes: bytes) -> bytes:
    binding.validate()
    return _length_prefixed(
        _ARTIFACT_DOMAIN,
        binding.profile_id.encode("utf-8"),
        str(binding.profile_version).encode("ascii"),
        binding.profile_digest.encode("ascii"),
        binding.schema_id.encode("utf-8"),
        str(binding.schema_version).encode("ascii"),
        binding.binding_digest.encode("ascii"),
        canonical_value_bytes,
    )


def encode_artifact(value: Any, binding: CanonicalTypedValueProfileBinding) -> CanonicalEncodedArtifact:
    canonical_value_bytes = encode_typed_value(value)
    return CanonicalEncodedArtifact(
        binding,
        canonical_value_bytes,
        sha256(canonical_value_bytes).hexdigest(),
        sha256(artifact_preimage(binding, canonical_value_bytes)).hexdigest(),
    )


def serialize_artifact(value: Any, binding: CanonicalTypedValueProfileBinding) -> bytes:
    """Return the CTV-v2 `CanonicalEncodedArtifact.v1` outer model bytes."""
    artifact = encode_artifact(value, binding)
    outer_binding = canonical_encoded_artifact_binding()
    outer_binding.validate()
    return encode_typed_value(
        {
            "binding": artifact.binding.as_value(),
            "canonical_value_bytes": artifact.canonical_value_bytes,
            "canonical_value_digest": artifact.canonical_value_digest,
            "artifact_digest": artifact.artifact_digest,
        }
    )


def decode_artifact(
    raw: bytes, *, expected_binding: CanonicalTypedValueProfileBinding | None = None
) -> CanonicalEncodedArtifact:
    """Decode only the registered CTV-v2 outer envelope.

    The historical JSON wrapper has a diagnostic reader below.  It is kept
    deliberately separate so authorization callers cannot accidentally accept
    pre-correction transport bytes.
    """
    value = decode_typed_value(raw)
    if not isinstance(value, dict) or set(value) != {
        "binding",
        "canonical_value_bytes",
        "canonical_value_digest",
        "artifact_digest",
    }:
        raise CanonicalTypedValueError("canonical_envelope_shape_invalid")
    binding_value = value["binding"]
    if not isinstance(binding_value, dict) or set(binding_value) != {
        "profile_id",
        "profile_version",
        "profile_digest",
        "schema_id",
        "schema_version",
        "binding_digest",
    }:
        raise CanonicalTypedValueError("canonical_binding_invalid")
    binding = CanonicalTypedValueProfileBinding(**binding_value)
    binding.validate()
    if expected_binding is not None and binding != expected_binding:
        raise CanonicalTypedValueError("canonical_binding_mismatch")
    if not isinstance(value["canonical_value_bytes"], bytes):
        raise CanonicalTypedValueError("canonical_envelope_bytes_invalid")
    body = value["canonical_value_bytes"]
    decode_typed_value(body)
    expected_value_digest = sha256(body).hexdigest()
    expected_artifact_digest = sha256(artifact_preimage(binding, body)).hexdigest()
    if value["canonical_value_digest"] != expected_value_digest or value["artifact_digest"] != expected_artifact_digest:
        raise CanonicalTypedValueError("canonical_envelope_digest_mismatch")
    return CanonicalEncodedArtifact(binding, body, expected_value_digest, expected_artifact_digest)


def serialize_legacy_artifact_diagnostic(value: Any, binding: CanonicalTypedValueProfileBinding) -> bytes:
    """Encode the retired JSON wrapper for non-authorizing diagnostics only."""
    artifact = encode_artifact(value, binding)
    return _json(
        {
            "binding": artifact.binding.as_value(),
            "canonical_value_bytes": base64.b64encode(artifact.canonical_value_bytes).decode("ascii"),
            "canonical_value_digest": artifact.canonical_value_digest,
            "artifact_digest": artifact.artifact_digest,
        }
    )


def decode_legacy_artifact_diagnostic(
    raw: bytes, *, expected_binding: CanonicalTypedValueProfileBinding | None = None
) -> CanonicalEncodedArtifact:
    """Read a retired JSON envelope without making it authorization-capable."""
    value = _strict_json(raw)
    if not isinstance(value, dict) or set(value) != {
        "binding",
        "canonical_value_bytes",
        "canonical_value_digest",
        "artifact_digest",
    }:
        raise CanonicalTypedValueError("canonical_envelope_shape_invalid")
    binding_value = value["binding"]
    if not isinstance(binding_value, dict) or set(binding_value) != {
        "profile_id",
        "profile_version",
        "profile_digest",
        "schema_id",
        "schema_version",
        "binding_digest",
    }:
        raise CanonicalTypedValueError("canonical_binding_invalid")
    binding = CanonicalTypedValueProfileBinding(**binding_value)
    binding.validate()
    if expected_binding is not None and binding != expected_binding:
        raise CanonicalTypedValueError("canonical_binding_mismatch")
    encoded = value["canonical_value_bytes"]
    if not isinstance(encoded, str):
        raise CanonicalTypedValueError("canonical_envelope_bytes_invalid")
    try:
        body = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise CanonicalTypedValueError("canonical_envelope_bytes_invalid") from exc
    decode_typed_value(body)
    expected_value_digest = sha256(body).hexdigest()
    expected_artifact_digest = sha256(artifact_preimage(binding, body)).hexdigest()
    if value["canonical_value_digest"] != expected_value_digest or value["artifact_digest"] != expected_artifact_digest:
        raise CanonicalTypedValueError("canonical_envelope_digest_mismatch")
    return CanonicalEncodedArtifact(binding, body, expected_value_digest, expected_artifact_digest)
