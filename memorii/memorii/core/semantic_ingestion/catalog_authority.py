"""Closed catalog and grant coordinates for structured fact authority.

The current seed is deliberately a core-selected package resource.  Legacy
claims have no implied seed coordinate; B1-C will bind this coordinate only to
new writes under its commit fence.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.resources
import inspect
import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedIngressContext
from memorii.core.memory_evolution.writer_admission import (
    SemanticCatalogAuthorityAdministrationAuthorization,
    SemanticWriterAdmissionError,
    SemanticWriterAdmissionStore,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    MemoryPlaneRevisionConflictError,
    RecordAbsentPrecondition,
    RecordDigestPrecondition,
    record_digest,
)
from memorii.core.semantic_ingestion.contracts import contract_digest
from memorii.core.semantic_ingestion.project_assertions_profile import (
    ProjectAssertionsProfileError,
    load_project_assertions_bundle,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility

_DIGEST = r"^[0-9a-f]{64}$"
_SEED_PREDICATES = ("project_deadline", "project_owner", "project_status")
_SEED_VERSION_ID = "three-predicate-seed-v1"
_REPORTS_TO_CHILD_RESOURCE = "reports_to.catalog-child.v1.json"
_PACKAGE_SEED_MEMBERS = (
    "project_assertions.manifest.v1.json", "project_assertions.prompt.v1.json",
    "project_assertions.output_schema.v1.json", "project_assertions.predicate_catalog.v1.json",
    "project_assertions.egress_policy.v1.json", "project_assertions.component_fingerprints.v1.json",
)


class CatalogAuthorityError(ValueError):
    """A catalog authority coordinate or core-selected seed is unavailable."""


@dataclass(frozen=True)
class VerifiedPackagedBaseCatalogRelease:
    """Verified inert package material; activation is deliberately separate."""

    catalog_digest: str
    child_version: CatalogChildVersionV2
    runtime_bundle: CatalogRuntimeBundle
    child_version_digest: str
    runtime_bundle_digest: str
    decision_digest: str
    selectable: bool


def _catalog_resource_bytes(name: str) -> bytes:
    try:
        return importlib.resources.files("memorii.core.semantic_ingestion.resources").joinpath(name).read_bytes()
    except (FileNotFoundError, ModuleNotFoundError, OSError) as exc:
        raise CatalogAuthorityError("packaged catalog resource is unavailable") from exc


def _catalog_json(name: str, payload: bytes) -> dict[str, object]:
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise CatalogAuthorityError("packaged catalog resource is invalid") from exc
    if not isinstance(value, dict):
        raise CatalogAuthorityError("packaged catalog resource is invalid")
    return value


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_packaged_reports_to_release() -> VerifiedPackagedBaseCatalogRelease:
    """Verify the bundled child bytes without granting selection authority."""
    from memorii.core.semantic_ingestion.catalog_release_root import REPORTS_TO_RELEASE_MANIFEST_ROOT

    return _load_packaged_reports_to_release(
        resource_bytes=_catalog_resource_bytes,
        package_resource_names=_catalog_package_resource_names,
        release_root=REPORTS_TO_RELEASE_MANIFEST_ROOT,
    )


class CatalogAuthorityScope(BaseModel):
    """The closed base coordinate before namespace and agent overlays exist."""

    schema_version: Literal[1]
    kind: Literal["base"]

    model_config = ConfigDict(extra="forbid", frozen=True)


class AuthenticatedPrincipalAgent(BaseModel):
    """Host-resolved identities; adapters never choose catalog ownership strings."""

    principal_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceScopeGrant(BaseModel):
    """Versioned source retention/disclosure authority for one principal and agent."""

    grant_id: str = Field(min_length=1)
    grant_version: int = Field(ge=1)
    source_scope: str = Field(min_length=1)
    authenticated: AuthenticatedPrincipalAgent

    model_config = ConfigDict(extra="forbid", frozen=True)


class FactScopeGrant(BaseModel):
    """Versioned target fact-write authority, independent of source access."""

    grant_id: str = Field(min_length=1)
    grant_version: int = Field(ge=1)
    fact_scope: str = Field(min_length=1)
    authenticated: AuthenticatedPrincipalAgent

    model_config = ConfigDict(extra="forbid", frozen=True)


class CatalogOwnerVisibilityGrant(BaseModel):
    """Versioned catalog-owner visibility/status authority for future protected reads."""

    grant_id: str = Field(min_length=1)
    grant_version: int = Field(ge=1)
    catalog_scope: CatalogAuthorityScope
    authenticated: AuthenticatedPrincipalAgent
    purpose: Literal["visibility_status"]

    model_config = ConfigDict(extra="forbid", frozen=True)


class ResolvedCatalogAuthority(BaseModel):
    """Core-selected immutable effective catalog coordinate for a new operation."""

    catalog_scope: CatalogAuthorityScope
    catalog_digest: str = Field(pattern=_DIGEST)
    genesis_selection_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)


class CatalogVersion(BaseModel):
    """An immutable catalog declaration whose parent is content-addressed."""

    schema_version: Literal[1]
    version_id: str = Field(min_length=1)
    catalog_scope: CatalogAuthorityScope
    catalog_digest: str = Field(pattern=_DIGEST)
    predicate_ids: tuple[str, ...]
    parent_version_digest: str | None = Field(default=None, pattern=_DIGEST)
    version_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> CatalogVersion:
        body = self.model_dump(mode="python", exclude={"version_digest"})
        if self.version_digest != contract_digest(
            b"memorii.learned-ontology.catalog-version.v1", body
        ):
            raise ValueError("catalog version digest is invalid")
        if self.predicate_ids != tuple(sorted(set(self.predicate_ids))):
            raise ValueError("catalog predicate IDs are not canonical")
        return self

    @classmethod
    def genesis(cls, *, catalog_digest: str) -> CatalogVersion:
        scope = CatalogAuthorityScope(schema_version=1, kind="base")
        body = {
            "schema_version": 1,
            "version_id": _SEED_VERSION_ID,
            "catalog_scope": scope,
            "catalog_digest": catalog_digest,
            "predicate_ids": tuple(sorted(_SEED_PREDICATES)),
            "parent_version_digest": None,
        }
        return cls(
            **body,
            version_digest=contract_digest(
                b"memorii.learned-ontology.catalog-version.v1", body
            ),
        )


class CatalogArtifactDeclaration(BaseModel):
    """One derived artifact that must bind the selected child catalog."""

    artifact_id: str = Field(min_length=1)
    artifact_kind: Literal[
        "prompt_schema", "tool_grammar", "proposal_adapter", "state_policy",
        "trust_policy", "temporal_policy", "protected_reader",
    ]
    artifact_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)


class CatalogArtifactManifest(BaseModel):
    """Content-addressed derived-artifact contract for one catalog child."""

    schema_version: Literal[1]
    artifacts: tuple[CatalogArtifactDeclaration, ...]
    manifest_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="before")
    @classmethod
    def canonicalize_artifacts(cls, value: object) -> object:
        if not isinstance(value, dict) or not isinstance(value.get("artifacts"), list):
            return value
        return {
            **value,
            "artifacts": sorted(value["artifacts"], key=lambda item: item.get("artifact_id", "") if isinstance(item, dict) else ""),
        }

    @model_validator(mode="after")
    def validate_digest(self) -> CatalogArtifactManifest:
        body = self.model_dump(mode="python", exclude={"manifest_digest"})
        if self.manifest_digest != contract_digest(
            b"memorii.learned-ontology.catalog-artifact-manifest.v1", body
        ):
            raise ValueError("catalog artifact manifest digest is invalid")
        ids = tuple(item.artifact_id for item in self.artifacts)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("catalog artifact IDs are not canonical")
        return self


class CatalogCapabilityManifest(BaseModel):
    """Selection requires every declared capability for the exact artifacts."""

    schema_version: Literal[1]
    artifact_manifest_digest: str = Field(pattern=_DIGEST)
    required_capability_ids: tuple[str, ...]
    available_capability_ids: tuple[str, ...]
    manifest_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> CatalogCapabilityManifest:
        body = self.model_dump(mode="python", exclude={"manifest_digest"})
        if self.manifest_digest != contract_digest(
            b"memorii.learned-ontology.catalog-capability-manifest.v1", body
        ):
            raise ValueError("catalog capability manifest digest is invalid")
        required = self.required_capability_ids
        available = self.available_capability_ids
        if required != tuple(sorted(set(required))) or available != tuple(sorted(set(available))):
            raise ValueError("catalog capability IDs are not canonical")
        if not set(available).issubset(required):
            raise ValueError("catalog capability availability is invalid")
        return self

    @property
    def is_complete(self) -> bool:
        return self.required_capability_ids == self.available_capability_ids


class CatalogChildDeclaration(BaseModel):
    """Immutable typed child declaration; it is not an active catalog pointer."""

    schema_version: Literal[1]
    version_id: str = Field(min_length=1)
    parent_version_id: str = Field(min_length=1)
    parent_version_digest: str = Field(pattern=_DIGEST)
    predicate_id: Literal["reports_to"]
    subject_type: Literal["Person"]
    object_type: Literal["Person"]
    scope_class: Literal["P"]
    evidence_class: Literal["D"]
    lifecycle_class: Literal["M"]
    read_form: Literal["set"]
    artifact_manifest: CatalogArtifactManifest
    capability_manifest: CatalogCapabilityManifest
    declaration_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_declaration(self) -> CatalogChildDeclaration:
        body = self.model_dump(mode="python", exclude={"declaration_digest"})
        if self.declaration_digest != contract_digest(
            b"memorii.learned-ontology.catalog-child-declaration.v1", body
        ):
            raise ValueError("catalog child declaration digest is invalid")
        if self.capability_manifest.artifact_manifest_digest != self.artifact_manifest.manifest_digest:
            raise ValueError("catalog child capability manifest does not bind artifacts")
        return self

    @property
    def is_selectable(self) -> bool:
        return self.capability_manifest.is_complete

    def require_selectable(self) -> None:
        if not self.is_selectable:
            raise CatalogAuthorityError("catalog child capabilities are unavailable")


_REPORTS_TO_DESCRIPTOR_PATHS = (
    "reports_to.prompt_schema.v1.json",
    "reports_to.tool_grammar.v1.json",
    "reports_to.proposal_adapter.v1.json",
    "reports_to.state_policy.v1.json",
    "reports_to.temporal_policy.v1.json",
    "reports_to.trust_policy.v1.json",
    "reports_to.protected_reader.v1.json",
)
_REPORTS_TO_PACKAGE_MEMBERS = (
    *_PACKAGE_SEED_MEMBERS,
    _REPORTS_TO_CHILD_RESOURCE,
    "reports_to.catalog-version.v2.json",
    "catalog-package-index.v1.json",
    "reports_to.runtime-bundle.v1.json",
    *_REPORTS_TO_DESCRIPTOR_PATHS,
)
_REPORTS_TO_RELEASE_RESOURCE = "reports_to.release-manifest.v1.json"


def _canonical_json_bytes(value: BaseModel) -> bytes:
    """The exact package-resource encoding; alternate JSON spellings deny."""
    return json.dumps(
        value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


class CatalogCapabilityDescriptor(BaseModel):
    """A declarative capability member, deliberately not an executable capability."""

    schema_version: Literal[1]
    capability_id: str = Field(min_length=1)
    catalog_digest: str = Field(pattern=_DIGEST)
    status: Literal["available", "unavailable"]
    implementation: CatalogCapabilityImplementation | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class CatalogCapabilityImplementation(BaseModel):
    """One package-owned code symbol whose bytes implement an inert capability."""

    module: Literal[
        "memorii.core.semantic_ingestion.default_catalog_capability",
        "memorii.core.semantic_ingestion.default_catalog_corpus",
        "memorii.core.semantic_ingestion.default_catalog_runtime",
        "memorii.core.semantic_ingestion.default_catalog_values",
        "memorii.core.semantic_ingestion.reports_to_capability",
        "memorii.core.semantic_ingestion.reports_to_state",
    ]
    symbol: Literal[
        "DefaultCatalogProtectedReader", "default_catalog_state_rules",
        "default_catalog_temporal_rules", "default_catalog_trust_rules",
        "selected_default_catalog_state_rules",
        "selected_default_catalog_temporal_rules",
        "selected_default_catalog_trust_rules",
        "default_catalog_runtime_rows", "load_default_catalog_acceptance_corpus",
        "validate_default_catalog_literal_grounding",
        "validate_default_catalog_provider_fact",
        "validate_default_catalog_provider_lifecycle_proposal",
        "validate_default_catalog_provider_proposal",
        "reports_to_output_schema", "validate_reports_to_tool_proposal",
        "ReportsToProviderProposalAdapter",
        "reports_to_state_rule", "reports_to_temporal_rule", "reports_to_trust_rule",
        "ReportsToProtectedReader",
    ]
    source_sha256: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)


_REPORTS_TO_IMPLEMENTATIONS = {
    "reports_to_prompt_schema": ("memorii.core.semantic_ingestion.reports_to_capability", "reports_to_output_schema"),
    "reports_to_tool_grammar": ("memorii.core.semantic_ingestion.reports_to_capability", "validate_reports_to_tool_proposal"),
    "reports_to_proposal_adapter": ("memorii.core.semantic_ingestion.reports_to_capability", "ReportsToProviderProposalAdapter"),
    "reports_to_state_policy": ("memorii.core.semantic_ingestion.reports_to_state", "reports_to_state_rule"),
    "reports_to_temporal_policy": ("memorii.core.semantic_ingestion.reports_to_state", "reports_to_temporal_rule"),
    "reports_to_trust_policy": ("memorii.core.semantic_ingestion.reports_to_state", "reports_to_trust_rule"),
    "reports_to_protected_reader": ("memorii.core.semantic_ingestion.reports_to_state", "ReportsToProtectedReader"),
}


class CatalogRuntimeBundleMember(BaseModel):
    """One exact descriptor byte member in a catalog runtime bundle."""

    capability_id: str = Field(min_length=1)
    artifact_kind: Literal[
        "prompt_schema", "tool_grammar", "proposal_adapter", "state_policy",
        "trust_policy", "temporal_policy", "protected_reader",
    ]
    resource_path: str = Field(min_length=1)
    member_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)


class CatalogRuntimeBundle(BaseModel):
    schema_version: Literal[1]
    catalog_scope: CatalogAuthorityScope
    catalog_digest: str = Field(pattern=_DIGEST)
    parent_version_digest: str = Field(pattern=_DIGEST)
    declaration_digest: str = Field(pattern=_DIGEST)
    members: tuple[CatalogRuntimeBundleMember, ...]
    bundle_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> CatalogRuntimeBundle:
        body = self.model_dump(mode="python", exclude={"bundle_digest"})
        if self.bundle_digest != contract_digest(
            b"memorii.learned-ontology.catalog-runtime-bundle.v1", body
        ):
            raise ValueError("catalog runtime bundle digest is invalid")
        identities = tuple(member.capability_id for member in self.members)
        paths = tuple(member.resource_path for member in self.members)
        if identities != tuple(sorted(set(identities))) or paths != tuple(sorted(set(paths))):
            raise ValueError("catalog runtime bundle members are not canonical")
        return self


class CatalogChildVersionV2(BaseModel):
    """Immutable schema-2 child coordinate bound to its completed bundle."""

    schema_version: Literal[2]
    version_id: str = Field(min_length=1)
    catalog_scope: CatalogAuthorityScope
    catalog_digest: str = Field(pattern=_DIGEST)
    predicate_ids: tuple[str, ...]
    parent_version_digest: str = Field(pattern=_DIGEST)
    runtime_bundle_digest: str = Field(pattern=_DIGEST)
    version_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> CatalogChildVersionV2:
        body = self.model_dump(mode="python", exclude={"version_digest"})
        if self.version_digest != contract_digest(
            b"memorii.learned-ontology.catalog-child-version.v2", body
        ):
            raise ValueError("catalog child version digest is invalid")
        if self.predicate_ids != tuple(sorted(set(self.predicate_ids))):
            raise ValueError("catalog child predicates are not canonical")
        return self


class CatalogPackageIndexEntry(BaseModel):
    catalog_scope: CatalogAuthorityScope
    version_digest: str = Field(pattern=_DIGEST)
    bundle_digest: str = Field(pattern=_DIGEST)
    bundle_resource_path: Literal["reports_to.runtime-bundle.v1.json"]

    model_config = ConfigDict(extra="forbid", frozen=True)


class CatalogPackageIndex(BaseModel):
    schema_version: Literal[1]
    entries: tuple[CatalogPackageIndexEntry, ...]
    index_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> CatalogPackageIndex:
        body = self.model_dump(mode="python", exclude={"index_digest"})
        if self.index_digest != contract_digest(
            b"memorii.learned-ontology.catalog-package-index.v1", body
        ):
            raise ValueError("catalog package index digest is invalid")
        keys = tuple(entry.version_digest for entry in self.entries)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("catalog package index entries are not canonical")
        return self


class CatalogPackageInventoryMember(BaseModel):
    resource_path: str = Field(min_length=1)
    member_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)


class PackagedBaseCatalogReleaseDecision(BaseModel):
    schema_version: Literal[1]
    catalog_scope: CatalogAuthorityScope
    product_release_id: Literal["memorii-reports-to-v1"]
    package_content_fingerprint: str = Field(pattern=_DIGEST)
    parent_version_digest: str = Field(pattern=_DIGEST)
    child_declaration_digest: str = Field(pattern=_DIGEST)
    child_version_digest: str = Field(pattern=_DIGEST)
    runtime_bundle_digest: str = Field(pattern=_DIGEST)
    select_on_install: Literal[True]
    decision_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> PackagedBaseCatalogReleaseDecision:
        body = self.model_dump(mode="python", exclude={"decision_digest"})
        if self.decision_digest != contract_digest(
            b"memorii.learned-ontology.packaged-base-release-decision.v1", body
        ):
            raise ValueError("packaged base catalog release decision digest is invalid")
        return self


class PackagedBaseCatalogReleaseManifest(BaseModel):
    schema_version: Literal[1]
    decision: PackagedBaseCatalogReleaseDecision
    release_manifest_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> PackagedBaseCatalogReleaseManifest:
        body = self.model_dump(mode="python", exclude={"release_manifest_digest"})
        expected = _sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())
        if self.release_manifest_digest != expected:
            raise ValueError("packaged base catalog release manifest digest is invalid")
        return self


def _read_typed_catalog_resource(name: str, model: type[BaseModel]) -> tuple[BaseModel, bytes]:
    payload = _catalog_resource_bytes(name)
    decoded = _catalog_json(name, payload)
    try:
        value = model.model_validate(decoded)
    except ValueError as exc:
        raise CatalogAuthorityError("packaged catalog resource is invalid") from exc
    if payload != _canonical_json_bytes(value):
        raise CatalogAuthorityError("packaged catalog resource bytes are not canonical")
    return value, payload


def _catalog_package_resource_names() -> tuple[str, ...]:
    try:
        return tuple(
            item.name
            for item in importlib.resources.files("memorii.core.semantic_ingestion.resources").iterdir()
            if item.is_file()
        )
    except (ModuleNotFoundError, OSError) as exc:
        raise CatalogAuthorityError("packaged catalog resource is unavailable") from exc


def _load_packaged_reports_to_release(
    *, resource_bytes: Callable[[str], bytes], package_resource_names: Callable[[], tuple[str, ...]],
    release_root: str,
) -> VerifiedPackagedBaseCatalogRelease:
    """Verify the complete inert release chain against the compiled root."""
    expected_reports_to_resources = {
        name
        for name in (*_REPORTS_TO_PACKAGE_MEMBERS, _REPORTS_TO_RELEASE_RESOURCE)
        if name.startswith("reports_to.")
    }
    actual_reports_to_resources = {
        name for name in package_resource_names() if name.startswith("reports_to.")
    }
    if actual_reports_to_resources != expected_reports_to_resources:
        raise CatalogAuthorityError("catalog package inventory is invalid")

    def read(name: str, model: type[BaseModel]) -> tuple[BaseModel, bytes]:
        payload = resource_bytes(name)
        decoded = _catalog_json(name, payload)
        try:
            value = model.model_validate(decoded)
        except ValueError as exc:
            raise CatalogAuthorityError("packaged catalog resource is invalid") from exc
        if payload != _canonical_json_bytes(value):
            raise CatalogAuthorityError("packaged catalog resource bytes are not canonical")
        return value, payload

    child, child_bytes = read(_REPORTS_TO_CHILD_RESOURCE, CatalogChildDeclaration)
    assert isinstance(child, CatalogChildDeclaration)
    seed = ThreePredicateSeedCatalogAuthorityRepository().resolve_base()
    parent = CatalogVersion.genesis(catalog_digest=seed.catalog_digest)
    if child.parent_version_id != parent.version_id or child.parent_version_digest != parent.version_digest:
        raise CatalogAuthorityError("packaged catalog child parent is invalid")

    descriptors: dict[str, tuple[CatalogCapabilityDescriptor, bytes]] = {}
    for path in _REPORTS_TO_DESCRIPTOR_PATHS:
        descriptor, descriptor_bytes = read(path, CatalogCapabilityDescriptor)
        assert isinstance(descriptor, CatalogCapabilityDescriptor)
        descriptors[path] = (descriptor, descriptor_bytes)

    bundle, bundle_bytes = read("reports_to.runtime-bundle.v1.json", CatalogRuntimeBundle)
    assert isinstance(bundle, CatalogRuntimeBundle)
    if bundle.catalog_scope != parent.catalog_scope or bundle.catalog_digest != seed.catalog_digest or bundle.parent_version_digest != parent.version_digest or bundle.declaration_digest != child.declaration_digest:
        raise CatalogAuthorityError("catalog runtime bundle is invalid")
    artifact_by_id = {artifact.artifact_id: artifact for artifact in child.artifact_manifest.artifacts}
    expected_ids = child.capability_manifest.required_capability_ids
    if tuple(member.capability_id for member in bundle.members) != expected_ids:
        raise CatalogAuthorityError("catalog runtime bundle members are invalid")
    for member in bundle.members:
        descriptor_pair = descriptors.get(member.resource_path)
        artifact = artifact_by_id.get(member.capability_id)
        if descriptor_pair is None or artifact is None:
            raise CatalogAuthorityError("catalog runtime bundle member is invalid")
        descriptor, descriptor_bytes = descriptor_pair
        if (
            descriptor.capability_id != member.capability_id
            or descriptor.catalog_digest != bundle.catalog_digest
            or (descriptor.status == "available")
            != (member.capability_id in child.capability_manifest.available_capability_ids)
            or member.artifact_kind != artifact.artifact_kind
            or member.member_digest != _sha256(descriptor_bytes)
            or artifact.artifact_digest != member.member_digest
        ):
            raise CatalogAuthorityError("catalog runtime bundle member is invalid")
        expected_implementation = _REPORTS_TO_IMPLEMENTATIONS.get(member.capability_id)
        if (
            expected_implementation is None and descriptor.implementation is not None
        ) or (
            expected_implementation is not None and (
                descriptor.implementation is None
                or (descriptor.implementation.module, descriptor.implementation.symbol)
                != expected_implementation
                or not _verify_capability_implementation(descriptor.implementation)
            )
        ):
            raise CatalogAuthorityError("catalog capability implementation is invalid")

    version, version_bytes = read("reports_to.catalog-version.v2.json", CatalogChildVersionV2)
    assert isinstance(version, CatalogChildVersionV2)
    if (
        version.catalog_scope != parent.catalog_scope
        or version.catalog_digest != bundle.catalog_digest
        or version.parent_version_digest != parent.version_digest
        or version.runtime_bundle_digest != bundle.bundle_digest
        or version.version_id != child.version_id
        or version.predicate_ids != tuple(sorted((*parent.predicate_ids, child.predicate_id)))
    ):
        raise CatalogAuthorityError("catalog child version is invalid")

    index, index_bytes = read("catalog-package-index.v1.json", CatalogPackageIndex)
    assert isinstance(index, CatalogPackageIndex)
    expected_entry = CatalogPackageIndexEntry(
        catalog_scope=parent.catalog_scope, version_digest=version.version_digest,
        bundle_digest=bundle.bundle_digest, bundle_resource_path="reports_to.runtime-bundle.v1.json",
    )
    if index.entries != (expected_entry,):
        raise CatalogAuthorityError("catalog package index is invalid")

    raw: dict[str, bytes] = {
        _REPORTS_TO_CHILD_RESOURCE: child_bytes,
        "reports_to.runtime-bundle.v1.json": bundle_bytes,
        "reports_to.catalog-version.v2.json": version_bytes,
        "catalog-package-index.v1.json": index_bytes,
        **{path: bytes_ for path, (_descriptor, bytes_) in descriptors.items()},
    }
    raw.update({name: resource_bytes(name) for name in _PACKAGE_SEED_MEMBERS})
    if tuple(sorted(raw)) != tuple(sorted(_REPORTS_TO_PACKAGE_MEMBERS)):
        raise CatalogAuthorityError("catalog package inventory is invalid")
    inventory = tuple(
        CatalogPackageInventoryMember(resource_path=name, member_digest=_sha256(raw[name]))
        for name in sorted(raw)
    )
    fingerprint = contract_digest(
        b"memorii.learned-ontology.catalog-package-content.v1", {"members": inventory}
    )

    manifest, manifest_bytes = read(_REPORTS_TO_RELEASE_RESOURCE, PackagedBaseCatalogReleaseManifest)
    assert isinstance(manifest, PackagedBaseCatalogReleaseManifest)
    decision = manifest.decision
    if (
        decision.package_content_fingerprint != fingerprint
        or decision.catalog_scope != parent.catalog_scope
        or decision.parent_version_digest != parent.version_digest
        or decision.child_declaration_digest != child.declaration_digest
        or decision.child_version_digest != version.version_digest
        or decision.runtime_bundle_digest != bundle.bundle_digest
        or _sha256(manifest_bytes) != release_root
    ):
        raise CatalogAuthorityError("packaged catalog release decision is invalid")
    return VerifiedPackagedBaseCatalogRelease(
        catalog_digest=bundle.catalog_digest,
        child_version=version,
        runtime_bundle=bundle,
        child_version_digest=version.version_digest,
        runtime_bundle_digest=bundle.bundle_digest,
        decision_digest=decision.decision_digest,
        selectable=child.is_selectable,
    )


def _verify_capability_implementation(implementation: CatalogCapabilityImplementation) -> bool:
    """Verify the closed source byte coordinate for one implemented descriptor."""
    try:
        module = importlib.import_module(implementation.module)
        symbol = getattr(module, implementation.symbol)
        source_path = inspect.getsourcefile(symbol) or inspect.getsourcefile(module)
        if source_path is None:
            return False
        with open(source_path, "rb") as source:
            return _sha256(source.read()) == implementation.source_sha256
    except (AttributeError, ImportError, OSError, TypeError):
        return False


class CatalogSelectionPointer(BaseModel):
    """Persisted selected-version head. A present invalid head never falls back."""

    schema_version: Literal[1]
    catalog_scope: CatalogAuthorityScope
    selected_version_id: str = Field(min_length=1)
    selected_version_digest: str = Field(pattern=_DIGEST)
    pointer_revision: int = Field(ge=1)
    predecessor_pointer_digest: str | None = Field(default=None, pattern=_DIGEST)
    pointer_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> CatalogSelectionPointer:
        body = self.model_dump(mode="python", exclude={"pointer_digest"})
        if self.pointer_digest != contract_digest(
            b"memorii.learned-ontology.catalog-selection-pointer.v1", body
        ):
            raise ValueError("catalog selection pointer digest is invalid")
        return self

    @classmethod
    def genesis(cls, *, version: CatalogVersion) -> CatalogSelectionPointer:
        body = {
            "schema_version": 1,
            "catalog_scope": version.catalog_scope,
            "selected_version_id": version.version_id,
            "selected_version_digest": version.version_digest,
            "pointer_revision": 1,
            "predecessor_pointer_digest": None,
        }
        return cls(
            **body,
            pointer_digest=contract_digest(
                b"memorii.learned-ontology.catalog-selection-pointer.v1", body
            ),
        )


def catalog_version_memory_id(version: CatalogVersion | CatalogChildVersionV2) -> str:
    return "semantic_ingestion:catalog-version:" + version.version_digest


def catalog_selection_pointer_memory_id(scope: CatalogAuthorityScope) -> str:
    return "semantic_ingestion:catalog-selection:" + scope.kind


class ResolvedStructuredSubmissionAuthority(BaseModel):
    """Resolved authority tuple that B1-C will revalidate under one commit fence."""

    authenticated: AuthenticatedPrincipalAgent
    source_grant: SourceScopeGrant
    fact_grant: FactScopeGrant
    catalog_visibility_grant: CatalogOwnerVisibilityGrant
    catalog: ResolvedCatalogAuthority
    provider_model_prompt_provenance_digest: str | None = Field(default=None, pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_joined_authority(self) -> ResolvedStructuredSubmissionAuthority:
        if (
            self.source_grant.authenticated != self.authenticated
            or self.fact_grant.authenticated != self.authenticated
            or self.catalog_visibility_grant.authenticated != self.authenticated
        ):
            raise ValueError("structured submission grants do not bind the authenticated principal and agent")
        if self.catalog_visibility_grant.catalog_scope != self.catalog.catalog_scope:
            raise ValueError("catalog visibility grant does not bind the selected catalog scope")
        return self


class StructuredGrantState(BaseModel):
    """Same-store current state for one independently revocable grant."""

    schema_version: Literal[1]
    grant_kind: Literal["source", "fact", "catalog_visibility"]
    grant: SourceScopeGrant | FactScopeGrant | CatalogOwnerVisibilityGrant
    active: bool

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_grant_kind(self) -> StructuredGrantState:
        expected_type = {
            "source": SourceScopeGrant,
            "fact": FactScopeGrant,
            "catalog_visibility": CatalogOwnerVisibilityGrant,
        }[self.grant_kind]
        if type(self.grant) is not expected_type:
            raise ValueError("structured grant state kind does not match its grant")
        return self


class StructuredClaimCatalogBinding(BaseModel):
    """Pinned catalog meaning attached to a newly written claim assertion."""

    schema_version: Literal[1, 2]
    claim_assertion_id: str = Field(min_length=1)
    claim_record_digest: str = Field(pattern=_DIGEST)
    catalog_scope: CatalogAuthorityScope
    catalog_digest: str = Field(pattern=_DIGEST)
    fact_scope: str = Field(min_length=1)
    authenticated: AuthenticatedPrincipalAgent
    capture_id: str | None = Field(default=None, min_length=1)
    pin_memory_id: str | None = Field(default=None, min_length=1)
    pin_digest: str | None = Field(default=None, pattern=_DIGEST)
    selected_version_id: str | None = Field(default=None, min_length=1)
    selected_version_digest: str | None = Field(default=None, pattern=_DIGEST)
    runtime_bundle_digest: str | None = Field(default=None, pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_schema_tuple(self) -> StructuredClaimCatalogBinding:
        tuple_fields = (
            self.capture_id, self.pin_memory_id, self.pin_digest,
            self.selected_version_id, self.selected_version_digest,
            self.runtime_bundle_digest,
        )
        if self.schema_version == 1 and any(value is not None for value in tuple_fields):
            raise ValueError("schema-1 catalog binding cannot carry a captured pin tuple")
        if self.schema_version == 2 and any(value is None for value in tuple_fields):
            raise ValueError("schema-2 catalog binding requires the captured pin tuple")
        return self


class StructuredFactReadAuthority(BaseModel):
    """Current fact and catalog visibility grants for a protected claim read."""

    authenticated: AuthenticatedPrincipalAgent
    fact_grant: FactScopeGrant
    catalog_visibility_grant: CatalogOwnerVisibilityGrant

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_joined_authority(self) -> StructuredFactReadAuthority:
        if (
            self.fact_grant.authenticated != self.authenticated
            or self.catalog_visibility_grant.authenticated != self.authenticated
        ):
            raise ValueError("structured read grants do not bind the authenticated principal and agent")
        return self


class StructuredSubmissionAuthorityRequest(BaseModel):
    """Input to the future core resolver; an expected digest only asserts the result."""

    authenticated: AuthenticatedPrincipalAgent
    source_grant: SourceScopeGrant
    fact_grant: FactScopeGrant
    catalog_visibility_grant: CatalogOwnerVisibilityGrant
    expected_catalog_digest: str | None = Field(default=None, pattern=_DIGEST)
    provider_model_prompt_provenance_digest: str | None = Field(default=None, pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)


class StructuredSubmissionAuthorityRepository(Protocol):
    """Canonical owner shape for B1-B resolution and B1-C serialized revalidation."""

    def resolve_submission_authority(
        self, *, request: StructuredSubmissionAuthorityRequest,
    ) -> ResolvedStructuredSubmissionAuthority | None: ...

    def commit_fence(
        self, *, authority: ResolvedStructuredSubmissionAuthority,
    ) -> AbstractContextManager[bool]: ...


class StructuredSubmissionAuthorityResolver(Protocol):
    """Host-bound authority resolver for the staged public submission root."""

    def resolve_submission_authority(
        self,
        *,
        authenticated_ingress: AuthenticatedIngressContext,
        request: StructuredSubmissionAuthorityRequest,
    ) -> ResolvedStructuredSubmissionAuthority | None: ...


class ThreePredicateSeedCatalogAuthorityRepository:
    """Resolve only the verified packaged three-predicate genesis catalog."""

    def resolve_base(
        self, *, expected_catalog_digest: str | None = None,
    ) -> ResolvedCatalogAuthority:
        try:
            bundle = load_project_assertions_bundle()
        except ProjectAssertionsProfileError as exc:
            raise CatalogAuthorityError("three-predicate seed catalog is unavailable") from exc
        digest = bundle.profile_digests.get("predicate_catalog_digest")
        if not isinstance(digest, str):
            raise CatalogAuthorityError("three-predicate seed catalog digest is unavailable")
        scope = CatalogAuthorityScope(schema_version=1, kind="base")
        genesis_selection_digest = contract_digest(
            b"memorii.learned-ontology.three-predicate-seed-genesis.v1",
            {
                "catalog_scope": scope.model_dump(mode="python"),
                "catalog_digest": digest,
                "predicate_ids": _SEED_PREDICATES,
            },
        )
        authority = ResolvedCatalogAuthority(
            catalog_scope=scope,
            catalog_digest=digest,
            genesis_selection_digest=genesis_selection_digest,
        )
        if expected_catalog_digest is not None and expected_catalog_digest != authority.catalog_digest:
            raise CatalogAuthorityError("expected catalog digest does not match the core-selected seed")
        return authority


def load_reports_to_child_declaration() -> CatalogChildDeclaration:
    """Load the fourth relation without granting it selection authority."""

    try:
        payload = importlib.resources.files(
            "memorii.core.semantic_ingestion.resources"
        ).joinpath(_REPORTS_TO_CHILD_RESOURCE).read_bytes()
        decoded = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys
        )
        declaration = CatalogChildDeclaration.model_validate(decoded)
    except (FileNotFoundError, ModuleNotFoundError, OSError, UnicodeDecodeError,
            json.JSONDecodeError, ValueError) as exc:
        raise CatalogAuthorityError("reports-to catalog child is unavailable") from exc
    seed = ThreePredicateSeedCatalogAuthorityRepository().resolve_base()
    version = CatalogVersion.genesis(catalog_digest=seed.catalog_digest)
    if (
        declaration.parent_version_id != version.version_id
        or declaration.parent_version_digest != version.version_digest
    ):
        raise CatalogAuthorityError("reports-to catalog child parent is invalid")
    return declaration


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate catalog child JSON key")
        result[key] = value
    return result


class SelectedCatalogAuthorityRepository:
    """Persist and verify the one selected packaged seed through the memory plane.

    The repository owns only genesis in this slice.  A version is never inferred
    from an absent or corrupt persisted pointer after any catalog state exists.
    """

    def __init__(
        self,
        memory_plane: MemoryPlaneService,
        writer_admission: SemanticWriterAdmissionStore,
    ) -> None:
        self._memory_plane = memory_plane
        self._writer_admission = writer_admission
        self._owner = object()
        self._administration_grant = (
            writer_admission.claim_catalog_authority_administration(owner=self._owner)
        )

    def resolve_selected_base(
        self, *, expected_catalog_digest: str | None = None,
    ) -> ResolvedCatalogAuthority:
        packaged = ThreePredicateSeedCatalogAuthorityRepository().resolve_base(
            expected_catalog_digest=expected_catalog_digest
        )
        self.ensure_seed_genesis(packaged=packaged)
        bundle = self.resolve_selected_bundle()
        if expected_catalog_digest is not None and bundle.catalog.catalog_digest != expected_catalog_digest:
            raise CatalogAuthorityError("core-selected catalog does not match expected digest")
        return bundle.catalog

    def resolve_selected_bundle(self):
        """Return the persisted selected package closure without seed fallback.

        Startup may establish a fresh seed only through ``ensure_seed_genesis``.
        Once a pointer exists this resolver follows that exact version and lets
        the package locator reject an incomplete child before schema egress.
        """
        from memorii.core.semantic_ingestion.catalog_capture_pin import (
            PackageIndexedCatalogBundleLocator,
        )

        _revision, records = self._memory_plane.read_snapshot()
        bundle, _pointer = PackageIndexedCatalogBundleLocator().locate_selected(
            records, scope=CatalogAuthorityScope(schema_version=1, kind="base"),
        )
        return bundle

    def ensure_seed_genesis(
        self, *, packaged: ResolvedCatalogAuthority | None = None,
    ) -> ResolvedCatalogAuthority:
        """Verify or atomically establish the exact packaged seed closure.

        Host composition calls this after writer admission and before it can
        expose semantic behavior.  Keeping it separate from resolution makes
        that startup fence explicit while preserving the generic submitter's
        retry-safe selection path.
        """
        if packaged is None:
            packaged = ThreePredicateSeedCatalogAuthorityRepository().resolve_base()
        expected_version = CatalogVersion.genesis(
            catalog_digest=packaged.catalog_digest
        )
        expected_pointer = CatalogSelectionPointer.genesis(version=expected_version)
        for _ in range(3):
            _revision, records = self._memory_plane.read_snapshot()
            catalog_records = tuple(
                record
                for record in records
                if record.source_kind in {
                    "semantic_ingestion_catalog_version",
                    "semantic_ingestion_catalog_selection_pointer",
                }
            )
            if not catalog_records:
                self._persist_genesis(
                    version=expected_version, pointer=expected_pointer
                )
                continue
            version_records = tuple(
                record
                for record in catalog_records
                if record.source_kind == "semantic_ingestion_catalog_version"
            )
            pointer_records = tuple(
                record
                for record in catalog_records
                if record.source_kind == "semantic_ingestion_catalog_selection_pointer"
            )
            if len(pointer_records) != 1 or not version_records:
                raise CatalogAuthorityError("catalog genesis control inventory is invalid")
            # After a governed release selects a child, startup must verify the
            # selected package rather than trying to recreate the seed pair.
            # The selected-bundle locator is deliberately fail closed for a
            # present incomplete child and for foreign inventory members.
            if len(version_records) != 1:
                try:
                    pointer = CatalogSelectionPointer.model_validate(
                        pointer_records[0].content["catalog_selection_pointer"]
                    )
                    from memorii.core.semantic_ingestion.catalog_capture_pin import (
                        PackageIndexedCatalogBundleLocator,
                    )
                    from memorii.core.semantic_ingestion.default_catalog_package import (
                        load_packaged_default_catalog_release,
                    )
                    releases = (
                        load_packaged_reports_to_release(),
                        load_packaged_default_catalog_release(),
                    )
                    selected = next(
                        (
                            release for release in releases
                            if release.child_version.version_id == pointer.selected_version_id
                            and release.child_version.version_digest == pointer.selected_version_digest
                        ),
                        None,
                    )
                    known_versions = (
                        {expected_version.version_digest, selected.child_version_digest}
                        if selected is not None else set()
                    )
                    persisted_digests = {
                        CatalogVersion.model_validate(record.content["catalog_version"]).version_digest
                        if record.content.get("catalog_version", {}).get("schema_version") == 1
                        else CatalogChildVersionV2.model_validate(record.content["catalog_version"]).version_digest
                        for record in version_records
                    }
                except (AttributeError, KeyError, TypeError, ValueError) as exc:
                    raise CatalogAuthorityError("catalog genesis control inventory is invalid") from exc
                if (
                    selected is None
                    or persisted_digests != known_versions
                ):
                    raise CatalogAuthorityError("catalog genesis control inventory is invalid")
                locator = PackageIndexedCatalogBundleLocator()
                bundle, selected_pointer = locator.locate_selected(
                    records, scope=expected_version.catalog_scope
                )
                if selected_pointer != pointer or bundle.version != selected.child_version:
                    raise CatalogAuthorityError("catalog genesis control inventory is invalid")
                return bundle.catalog
            return self._verify_selected_genesis(
                packaged=packaged,
                expected_version=expected_version,
                expected_pointer=expected_pointer,
                version_record=version_records[0],
                pointer_record=pointer_records[0],
            )
        raise CatalogAuthorityError("catalog genesis selection did not stabilize")

    def install_default_catalog_release(self) -> ResolvedCatalogAuthority:
        """Select the verified generated default catalog from the seed head.

        This is the only Level-2 publication path for the bundled default
        inventory.  It writes the immutable child coordinate and replaces the
        selected pointer under the existing catalog-administration authority.
        """
        from memorii.core.semantic_ingestion.default_catalog_package import (
            load_packaged_default_catalog_release,
        )

        self.ensure_seed_genesis()
        release = load_packaged_default_catalog_release()
        for _ in range(3):
            _revision, records = self._memory_plane.read_snapshot()
            by_id = {record.memory_id: record for record in records}
            pointer_id = catalog_selection_pointer_memory_id(release.child_version.catalog_scope)
            pointer_record = by_id.get(pointer_id)
            if pointer_record is None:
                raise CatalogAuthorityError("catalog selection state is invalid")
            try:
                pointer = CatalogSelectionPointer.model_validate(
                    pointer_record.content["catalog_selection_pointer"]
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise CatalogAuthorityError("catalog selection state is invalid") from exc
            if (
                pointer.selected_version_id == release.child_version.version_id
                and pointer.selected_version_digest == release.child_version.version_digest
            ):
                return ThreePredicateSeedCatalogAuthorityRepository().resolve_base()
            seed = CatalogVersion.genesis(catalog_digest=release.catalog_digest)
            if (
                pointer != CatalogSelectionPointer.genesis(version=seed)
                or catalog_version_memory_id(release.child_version) in by_id
            ):
                raise CatalogAuthorityError("catalog selection state is invalid")
            body = {
                "schema_version": 1,
                "catalog_scope": pointer.catalog_scope,
                "selected_version_id": release.child_version.version_id,
                "selected_version_digest": release.child_version.version_digest,
                "pointer_revision": 2,
                "predecessor_pointer_digest": pointer.pointer_digest,
            }
            selected = CatalogSelectionPointer(
                **body,
                pointer_digest=contract_digest(
                    b"memorii.learned-ontology.catalog-selection-pointer.v1", body
                ),
            )
            try:
                self._memory_plane.conditionally_write_records(
                    (_catalog_version_record(release.child_version), _catalog_selection_pointer_record(selected)),
                    preconditions=(
                        RecordAbsentPrecondition(memory_id=catalog_version_memory_id(release.child_version)),
                        RecordDigestPrecondition(
                            memory_id=pointer_record.memory_id,
                            expected_digest=record_digest(pointer_record),
                        ),
                    ),
                    authorization=SemanticCatalogAuthorityAdministrationAuthorization(
                        owner=self._administration_grant
                    ),
                )
            except MemoryPlaneRevisionConflictError:
                continue
            except SemanticWriterAdmissionError as exc:
                raise CatalogAuthorityError("default catalog release is unavailable") from exc
        raise CatalogAuthorityError("default catalog selection did not stabilize")

    def _persist_genesis(
        self,
        *,
        version: CatalogVersion,
        pointer: CatalogSelectionPointer,
    ) -> None:
        version_record = _catalog_version_record(version)
        pointer_record = _catalog_selection_pointer_record(pointer)
        try:
            self._memory_plane.conditionally_write_records(
                (version_record, pointer_record),
                preconditions=(
                    RecordAbsentPrecondition(memory_id=version_record.memory_id),
                    RecordAbsentPrecondition(memory_id=pointer_record.memory_id),
                ),
                authorization=SemanticCatalogAuthorityAdministrationAuthorization(
                    owner=self._administration_grant
                ),
            )
        except MemoryPlaneRevisionConflictError:
            return
        except SemanticWriterAdmissionError as exc:
            raise CatalogAuthorityError("catalog genesis control inventory is invalid") from exc

    @staticmethod
    def _verify_selected_genesis(
        *,
        packaged: ResolvedCatalogAuthority,
        expected_version: CatalogVersion,
        expected_pointer: CatalogSelectionPointer,
        version_record: CanonicalMemoryRecord,
        pointer_record: CanonicalMemoryRecord,
    ) -> ResolvedCatalogAuthority:
        try:
            version = CatalogVersion.model_validate(version_record.content["catalog_version"])
            pointer = CatalogSelectionPointer.model_validate(
                pointer_record.content["catalog_selection_pointer"]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CatalogAuthorityError("catalog selection state is invalid") from exc
        if (
            version_record.memory_id != catalog_version_memory_id(version)
            or pointer_record.memory_id
            != catalog_selection_pointer_memory_id(pointer.catalog_scope)
            or version != expected_version
            or pointer != expected_pointer
            or pointer.catalog_scope != packaged.catalog_scope
        ):
            raise CatalogAuthorityError("catalog selection state is invalid")
        return packaged


def _catalog_version_record(version: CatalogVersion | CatalogChildVersionV2) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=catalog_version_memory_id(version),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={"catalog_version": version.model_dump(mode="json")},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_catalog_version",
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        timestamp=datetime.now(UTC),
    )


def _catalog_selection_pointer_record(
    pointer: CatalogSelectionPointer,
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=catalog_selection_pointer_memory_id(pointer.catalog_scope),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={"catalog_selection_pointer": pointer.model_dump(mode="json")},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_catalog_selection_pointer",
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        timestamp=datetime.now(UTC),
    )


__all__ = [
    "AuthenticatedPrincipalAgent",
    "CatalogAuthorityError",
    "CatalogAuthorityScope",
    "CatalogArtifactDeclaration",
    "CatalogArtifactManifest",
    "CatalogCapabilityDescriptor",
    "CatalogCapabilityImplementation",
    "CatalogCapabilityManifest",
    "CatalogChildDeclaration",
    "CatalogChildVersionV2",
    "CatalogPackageIndex",
    "CatalogPackageIndexEntry",
    "CatalogPackageInventoryMember",
    "CatalogRuntimeBundle",
    "CatalogRuntimeBundleMember",
    "CatalogSelectionPointer",
    "CatalogVersion",
    "CatalogOwnerVisibilityGrant",
    "FactScopeGrant",
    "PackagedBaseCatalogReleaseDecision",
    "PackagedBaseCatalogReleaseManifest",
    "ResolvedCatalogAuthority",
    "ResolvedStructuredSubmissionAuthority",
    "SourceScopeGrant",
    "StructuredClaimCatalogBinding",
    "StructuredFactReadAuthority",
    "StructuredGrantState",
    "StructuredSubmissionAuthorityRepository",
    "StructuredSubmissionAuthorityResolver",
    "StructuredSubmissionAuthorityRequest",
    "SelectedCatalogAuthorityRepository",
    "ThreePredicateSeedCatalogAuthorityRepository",
    "catalog_selection_pointer_memory_id",
    "catalog_version_memory_id",
    "load_reports_to_child_declaration",
    "load_packaged_reports_to_release",
]
