"""Generate the inert reports-to package from typed catalog contracts.

Run from ``memorii/`` with ``PYTHONPATH=.``.  The release-root module is the
only generated Python carrier; no loose resource file is a trust anchor.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
from pathlib import Path
from typing import Literal

from memorii.core.semantic_ingestion.catalog_authority import (
    _PACKAGE_SEED_MEMBERS,
    _REPORTS_TO_CHILD_RESOURCE,
    _REPORTS_TO_DESCRIPTOR_PATHS,
    CatalogArtifactDeclaration,
    CatalogArtifactManifest,
    CatalogCapabilityDescriptor,
    CatalogCapabilityImplementation,
    CatalogCapabilityManifest,
    CatalogChildDeclaration,
    CatalogChildVersionV2,
    CatalogPackageIndex,
    CatalogPackageIndexEntry,
    CatalogPackageInventoryMember,
    CatalogRuntimeBundle,
    CatalogRuntimeBundleMember,
    CatalogVersion,
    PackagedBaseCatalogReleaseDecision,
    PackagedBaseCatalogReleaseManifest,
    ThreePredicateSeedCatalogAuthorityRepository,
    _canonical_json_bytes,
    _sha256,
)
from memorii.core.semantic_ingestion.contracts import contract_digest

_RESOURCE_DIR = Path(__file__).resolve().parents[1] / "memorii" / "core" / "semantic_ingestion" / "resources"
_ROOT_MODULE = Path(__file__).resolve().parents[1] / "memorii" / "core" / "semantic_ingestion" / "catalog_release_root.py"
ArtifactKind = Literal[
    "prompt_schema", "tool_grammar", "proposal_adapter", "state_policy",
    "trust_policy", "temporal_policy", "protected_reader",
]
ImplementationSymbol = Literal[
    "reports_to_output_schema", "validate_reports_to_tool_proposal",
    "ReportsToProviderProposalAdapter",
    "reports_to_state_rule", "reports_to_temporal_rule", "reports_to_trust_rule",
    "ReportsToProtectedReader",
]
ImplementationModule = Literal[
    "memorii.core.semantic_ingestion.reports_to_capability",
    "memorii.core.semantic_ingestion.reports_to_state",
]
_DESCRIPTORS: tuple[tuple[str, ArtifactKind], ...] = (
    ("reports_to.prompt_schema", "prompt_schema"),
    ("reports_to.tool_grammar", "tool_grammar"),
    ("reports_to.proposal_adapter", "proposal_adapter"),
    ("reports_to.state_policy", "state_policy"),
    ("reports_to.temporal_policy", "temporal_policy"),
    ("reports_to.trust_policy", "trust_policy"),
    ("reports_to.protected_reader", "protected_reader"),
)
_IMPLEMENTED_CAPABILITIES: dict[str, tuple[ImplementationModule, ImplementationSymbol]] = {
    "reports_to_prompt_schema": ("memorii.core.semantic_ingestion.reports_to_capability", "reports_to_output_schema"),
    "reports_to_tool_grammar": ("memorii.core.semantic_ingestion.reports_to_capability", "validate_reports_to_tool_proposal"),
    "reports_to_proposal_adapter": ("memorii.core.semantic_ingestion.reports_to_capability", "ReportsToProviderProposalAdapter"),
    "reports_to_state_policy": ("memorii.core.semantic_ingestion.reports_to_state", "reports_to_state_rule"),
    "reports_to_temporal_policy": ("memorii.core.semantic_ingestion.reports_to_state", "reports_to_temporal_rule"),
    "reports_to_trust_policy": ("memorii.core.semantic_ingestion.reports_to_state", "reports_to_trust_rule"),
    "reports_to_protected_reader": ("memorii.core.semantic_ingestion.reports_to_state", "ReportsToProtectedReader"),
}


def _digest(domain: bytes, body: dict[str, object]) -> str:
    return contract_digest(domain, body)


def _implementation(capability_id: str) -> CatalogCapabilityImplementation | None:
    coordinate = _IMPLEMENTED_CAPABILITIES.get(capability_id)
    if coordinate is None:
        return None
    module_name, symbol_name = coordinate
    module = importlib.import_module(module_name)
    symbol = getattr(module, symbol_name)
    source_path = inspect.getsourcefile(symbol) or inspect.getsourcefile(module)
    if source_path is None:
        raise RuntimeError("reports-to implementation source is unavailable")
    return CatalogCapabilityImplementation(
        module=module_name, symbol=symbol_name,
        source_sha256=hashlib.sha256(Path(source_path).read_bytes()).hexdigest(),
    )


def generate_package(
    *, output_dir: Path, root_module: Path | None,
    available_capability_ids: tuple[str, ...],
) -> str:
    """Generate one closed package and return its computed manifest root."""
    capability_ids_allowed = tuple(sorted(_IMPLEMENTED_CAPABILITIES))
    if available_capability_ids not in ((), capability_ids_allowed):
        raise ValueError("reports-to availability must be empty or the complete closed capability set")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in _PACKAGE_SEED_MEMBERS:
        (output_dir / name).write_bytes((_RESOURCE_DIR / name).read_bytes())

    def _write(name: str, value) -> bytes:
        payload = _canonical_json_bytes(value)
        (output_dir / name).write_bytes(payload)
        return payload

    seed = ThreePredicateSeedCatalogAuthorityRepository().resolve_base()
    parent = CatalogVersion.genesis(catalog_digest=seed.catalog_digest)

    descriptor_payloads: dict[str, bytes] = {}
    artifacts: list[CatalogArtifactDeclaration] = []
    for (artifact_prefix, artifact_kind), path in zip(_DESCRIPTORS, _REPORTS_TO_DESCRIPTOR_PATHS, strict=True):
        capability_id = artifact_prefix.replace("reports_to.", "reports_to_")
        descriptor = CatalogCapabilityDescriptor(
            schema_version=1, capability_id=capability_id,
            catalog_digest=seed.catalog_digest,
            status="available" if capability_id in available_capability_ids else "unavailable",
            implementation=_implementation(capability_id),
        )
        descriptor_payloads[path] = _write(path, descriptor)
        artifacts.append(CatalogArtifactDeclaration(
            artifact_id=capability_id, artifact_kind=artifact_kind,
            artifact_digest=_sha256(descriptor_payloads[path]),
        ))
    artifacts.sort(key=lambda artifact: artifact.artifact_id)
    artifact_body = {"schema_version": 1, "artifacts": tuple(artifacts)}
    artifact_manifest = CatalogArtifactManifest(
        **artifact_body,
        manifest_digest=_digest(b"memorii.learned-ontology.catalog-artifact-manifest.v1", artifact_body),
    )
    capability_ids = tuple(artifact.artifact_id for artifact in artifacts)
    capability_body = {
        "schema_version": 1, "artifact_manifest_digest": artifact_manifest.manifest_digest,
        "required_capability_ids": capability_ids,
        "available_capability_ids": available_capability_ids,
    }
    capability_manifest = CatalogCapabilityManifest(
        **capability_body,
        manifest_digest=_digest(b"memorii.learned-ontology.catalog-capability-manifest.v1", capability_body),
    )
    child_body = {
        "schema_version": 1, "version_id": "reports-to-person-person-v1",
        "parent_version_id": parent.version_id, "parent_version_digest": parent.version_digest,
        "predicate_id": "reports_to", "subject_type": "Person", "object_type": "Person",
        "scope_class": "P", "evidence_class": "D", "lifecycle_class": "M", "read_form": "set",
        "artifact_manifest": artifact_manifest, "capability_manifest": capability_manifest,
    }
    child = CatalogChildDeclaration(
        **child_body,
        declaration_digest=_digest(b"memorii.learned-ontology.catalog-child-declaration.v1", child_body),
    )
    child_bytes = _write(_REPORTS_TO_CHILD_RESOURCE, child)

    members = tuple(sorted((
        CatalogRuntimeBundleMember(
            capability_id=artifact.artifact_id, artifact_kind=artifact.artifact_kind,
            resource_path=path, member_digest=artifact.artifact_digest,
        )
        for artifact, path in zip(artifacts, sorted(_REPORTS_TO_DESCRIPTOR_PATHS), strict=True)
    ), key=lambda member: member.capability_id))
    bundle_body = {
        "schema_version": 1, "catalog_scope": parent.catalog_scope, "catalog_digest": seed.catalog_digest,
        "parent_version_digest": parent.version_digest, "declaration_digest": child.declaration_digest,
        "members": members,
    }
    bundle = CatalogRuntimeBundle(
        **bundle_body,
        bundle_digest=_digest(b"memorii.learned-ontology.catalog-runtime-bundle.v1", bundle_body),
    )
    bundle_bytes = _write("reports_to.runtime-bundle.v1.json", bundle)
    version_body = {
        "schema_version": 2, "version_id": child.version_id, "catalog_scope": parent.catalog_scope,
        "catalog_digest": seed.catalog_digest,
        "predicate_ids": tuple(sorted((*parent.predicate_ids, child.predicate_id))),
        "parent_version_digest": parent.version_digest, "runtime_bundle_digest": bundle.bundle_digest,
    }
    version = CatalogChildVersionV2(
        **version_body,
        version_digest=_digest(b"memorii.learned-ontology.catalog-child-version.v2", version_body),
    )
    version_bytes = _write("reports_to.catalog-version.v2.json", version)
    entry = CatalogPackageIndexEntry(
        catalog_scope=parent.catalog_scope, version_digest=version.version_digest,
        bundle_digest=bundle.bundle_digest, bundle_resource_path="reports_to.runtime-bundle.v1.json",
    )
    index_body = {"schema_version": 1, "entries": (entry,)}
    index = CatalogPackageIndex(
        **index_body,
        index_digest=_digest(b"memorii.learned-ontology.catalog-package-index.v1", index_body),
    )
    index_bytes = _write("catalog-package-index.v1.json", index)

    package_bytes = {
        _REPORTS_TO_CHILD_RESOURCE: child_bytes,
        "reports_to.runtime-bundle.v1.json": bundle_bytes,
        "reports_to.catalog-version.v2.json": version_bytes,
        "catalog-package-index.v1.json": index_bytes,
        **descriptor_payloads,
        **{name: (output_dir / name).read_bytes() for name in _PACKAGE_SEED_MEMBERS},
    }
    inventory = tuple(
        CatalogPackageInventoryMember(resource_path=name, member_digest=_sha256(package_bytes[name]))
        for name in sorted(package_bytes)
    )
    fingerprint = contract_digest(
        b"memorii.learned-ontology.catalog-package-content.v1", {"members": inventory}
    )
    decision_body = {
        "schema_version": 1, "catalog_scope": parent.catalog_scope,
        "product_release_id": "memorii-reports-to-v1", "package_content_fingerprint": fingerprint,
        "parent_version_digest": parent.version_digest, "child_declaration_digest": child.declaration_digest,
        "child_version_digest": version.version_digest, "runtime_bundle_digest": bundle.bundle_digest,
        "select_on_install": True,
    }
    decision = PackagedBaseCatalogReleaseDecision(
        **decision_body,
        decision_digest=_digest(b"memorii.learned-ontology.packaged-base-release-decision.v1", decision_body),
    )
    manifest_body = {"schema_version": 1, "decision": decision}
    # The manifest digest is the SHA-256 of its canonical body, never its own bytes.
    import json
    manifest_digest = _sha256(json.dumps(
        {"schema_version": 1, "decision": decision.model_dump(mode="json")},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8"))
    manifest = PackagedBaseCatalogReleaseManifest(
        **manifest_body, release_manifest_digest=manifest_digest,
    )
    manifest_bytes = _write("reports_to.release-manifest.v1.json", manifest)
    compiled_root = _sha256(manifest_bytes)
    if root_module is not None:
        root_module.write_text(
            '"""Compiled trust anchor for the bundled reports-to product release."""\n\n'
            f'REPORTS_TO_RELEASE_MANIFEST_ROOT = "{compiled_root}"\n', encoding="utf-8"
        )
    return compiled_root


def main() -> None:
    generate_package(
        output_dir=_RESOURCE_DIR, root_module=_ROOT_MODULE,
        available_capability_ids=(),
    )


if __name__ == "__main__":
    main()
