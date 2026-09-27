"""Verified package closure for the generated default-catalog runtime.

The acceptance corpus remains the normative inventory.  This module binds that
inventory and the runtime validator source to one generated trust anchor before
it can become a selected catalog version.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.semantic_ingestion.catalog_authority import (
    CatalogAuthorityError,
    CatalogCapabilityDescriptor,
    CatalogChildVersionV2,
    CatalogRuntimeBundle,
    CatalogRuntimeBundleMember,
    CatalogVersion,
    ThreePredicateSeedCatalogAuthorityRepository,
    VerifiedPackagedBaseCatalogRelease,
)
from memorii.core.semantic_ingestion.contracts import contract_digest
from memorii.core.semantic_ingestion.default_catalog_corpus import (
    corpus_resource_sha256,
    load_default_catalog_acceptance_corpus,
)
from memorii.core.semantic_ingestion.default_catalog_values import (
    DEFAULT_CATALOG_VALUE_POLICY_HISTORY,
)

_DESCRIPTORS: tuple[tuple[str, Literal["prompt_schema", "tool_grammar", "proposal_adapter", "state_policy", "trust_policy", "temporal_policy", "protected_reader"], str, str], ...] = (
    ("prompt_schema", "prompt_schema", "memorii.core.semantic_ingestion.default_catalog_corpus", "load_default_catalog_acceptance_corpus"),
    ("tool_grammar", "tool_grammar", "memorii.core.semantic_ingestion.default_catalog_runtime", "default_catalog_runtime_rows"),
    ("proposal_adapter", "proposal_adapter", "memorii.core.semantic_ingestion.default_catalog_runtime", "validate_default_catalog_provider_lifecycle_proposal"),
    ("state_policy", "state_policy", "memorii.core.semantic_ingestion.default_catalog_capability", "selected_default_catalog_state_rules"),
    ("trust_policy", "trust_policy", "memorii.core.semantic_ingestion.default_catalog_capability", "selected_default_catalog_trust_rules"),
    ("temporal_policy", "temporal_policy", "memorii.core.semantic_ingestion.default_catalog_capability", "selected_default_catalog_temporal_rules"),
    ("protected_reader", "protected_reader", "memorii.core.semantic_ingestion.default_catalog_capability", "DefaultCatalogProtectedReader"),
)


class DefaultCatalogPackageAuthority(BaseModel):
    """Generated authority for one complete default-catalog runtime closure."""

    schema_version: Literal[1]
    corpus_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    corpus_resource_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    value_policy_history_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    descriptor_digests: tuple[tuple[str, str], ...]
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> DefaultCatalogPackageAuthority:
        body = self.model_dump(mode="python", exclude={"authority_digest"})
        if self.authority_digest != contract_digest(
            b"memorii.learned-ontology.default-catalog-package.v1", body
        ):
            raise ValueError("default catalog package authority digest is invalid")
        if self.descriptor_digests != tuple(sorted(self.descriptor_digests)):
            raise ValueError("default catalog package descriptors are not canonical")
        return self


def _policy_history_digest() -> str:
    return contract_digest(
        b"memorii.learned-ontology.default-catalog-value-policy-history.v1",
        tuple(policy.model_dump(mode="python") for policy in DEFAULT_CATALOG_VALUE_POLICY_HISTORY.values()),
    )


def _read_descriptor(name: str) -> tuple[CatalogCapabilityDescriptor, bytes]:
    from memorii.core.semantic_ingestion.catalog_authority import _catalog_json, _catalog_resource_bytes

    payload = _catalog_resource_bytes(name)
    try:
        descriptor = CatalogCapabilityDescriptor.model_validate(_catalog_json(name, payload))
    except ValueError as exc:
        raise CatalogAuthorityError("default catalog descriptor is invalid") from exc
    canonical = json.dumps(
        descriptor.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()
    if payload != canonical:
        raise CatalogAuthorityError("default catalog descriptor bytes are not canonical")
    return descriptor, payload


def _implementation_source_sha256(module_name: str, symbol_name: str) -> str:
    module = __import__(module_name, fromlist=[symbol_name])
    symbol = getattr(module, symbol_name)
    try:
        source = inspect.getsourcefile(symbol)
    except TypeError:
        source = None
    source = source or inspect.getsourcefile(module)
    if source is None:
        raise CatalogAuthorityError("default catalog runtime source is unavailable")
    return hashlib.sha256(Path(source).read_bytes()).hexdigest()


def _verify_policy_coverage(corpus_relation_ids: frozenset[str]) -> None:
    from memorii.core.semantic_ingestion.default_catalog_capability import (
        DefaultCatalogProtectedReader,
        selected_default_catalog_state_rules,
        selected_default_catalog_temporal_rules,
        selected_default_catalog_trust_rules,
    )

    rules = (
        selected_default_catalog_state_rules(),
        selected_default_catalog_trust_rules(),
        selected_default_catalog_temporal_rules(),
    )
    selected_relation_ids = corpus_relation_ids | frozenset({
        "project_deadline", "project_owner", "project_status",
    })
    if any(frozenset(rule) != selected_relation_ids for rule in rules):
        raise CatalogAuthorityError("default catalog policy coverage is incomplete")
    if not DefaultCatalogProtectedReader.authorizes_version(
        selected_version_id="default-catalog-v1"
    ):
        raise CatalogAuthorityError("default catalog protected reader is substituted")


def load_packaged_default_catalog_release() -> VerifiedPackagedBaseCatalogRelease:
    """Load the generated authority and construct its exact selectable version."""
    from memorii.core.semantic_ingestion.default_catalog_package_root import (
        DEFAULT_CATALOG_PACKAGE_AUTHORITY,
    )

    try:
        package = DefaultCatalogPackageAuthority.model_validate(
            DEFAULT_CATALOG_PACKAGE_AUTHORITY
        )
        corpus = load_default_catalog_acceptance_corpus()
    except (TypeError, ValueError) as exc:
        raise CatalogAuthorityError("default catalog package authority is invalid") from exc
    if (
        package.corpus_digest != corpus.corpus_digest
        or package.corpus_resource_sha256 != corpus_resource_sha256()
        or package.value_policy_history_digest != _policy_history_digest()
    ):
        raise CatalogAuthorityError("default catalog package authority is substituted")
    _verify_policy_coverage(frozenset(row.relation_id for row in corpus.rows))

    descriptor_digests = dict(package.descriptor_digests)
    members: list[CatalogRuntimeBundleMember] = []
    for role, kind, module, symbol in _DESCRIPTORS:
        path = f"default_catalog.{role}.v1.json"
        descriptor, payload = _read_descriptor(path)
        expected_digest = descriptor_digests.get(path)
        if (
            expected_digest != hashlib.sha256(payload).hexdigest()
            or descriptor.capability_id != f"default_catalog_{role}"
            or descriptor.status != "available"
            or descriptor.implementation is None
            or (descriptor.implementation.module, descriptor.implementation.symbol) != (module, symbol)
            or descriptor.implementation.source_sha256 != _implementation_source_sha256(module, symbol)
        ):
            raise CatalogAuthorityError("default catalog descriptor is substituted")
        assert expected_digest is not None
        members.append(CatalogRuntimeBundleMember(
            capability_id=descriptor.capability_id, artifact_kind=kind,
            resource_path=path, member_digest=expected_digest,
        ))
    if set(descriptor_digests) != {member.resource_path for member in members}:
        raise CatalogAuthorityError("default catalog descriptor inventory is incomplete")
    catalog = ThreePredicateSeedCatalogAuthorityRepository().resolve_base()
    parent = CatalogVersion.genesis(catalog_digest=catalog.catalog_digest)
    bundle_body = {
        "schema_version": 1,
        "catalog_scope": parent.catalog_scope,
        "catalog_digest": catalog.catalog_digest,
        "parent_version_digest": parent.version_digest,
        "declaration_digest": package.authority_digest,
        "members": tuple(sorted(members, key=lambda member: member.capability_id)),
    }
    bundle = CatalogRuntimeBundle(
        **bundle_body,
        bundle_digest=contract_digest(
            b"memorii.learned-ontology.catalog-runtime-bundle.v1", bundle_body
        ),
    )
    version_body = {
        "schema_version": 2,
        "version_id": "default-catalog-v1",
        "catalog_scope": parent.catalog_scope,
        "catalog_digest": catalog.catalog_digest,
        "predicate_ids": tuple(sorted((*parent.predicate_ids, *(row.relation_id for row in corpus.rows)))),
        "parent_version_digest": parent.version_digest,
        "runtime_bundle_digest": bundle.bundle_digest,
    }
    version = CatalogChildVersionV2(
        **version_body,
        version_digest=contract_digest(
            b"memorii.learned-ontology.catalog-child-version.v2", version_body
        ),
    )
    return VerifiedPackagedBaseCatalogRelease(
        catalog_digest=catalog.catalog_digest,
        child_version=version,
        runtime_bundle=bundle,
        child_version_digest=version.version_digest,
        runtime_bundle_digest=bundle.bundle_digest,
        decision_digest=package.authority_digest,
        selectable=True,
    )


__all__ = [
    "DefaultCatalogPackageAuthority",
    "load_packaged_default_catalog_release",
]
