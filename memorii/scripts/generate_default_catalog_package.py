"""Generate the immutable Python trust anchor for the default catalog package."""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

from memorii.core.semantic_ingestion.catalog_authority import (
    CatalogCapabilityDescriptor,
    CatalogCapabilityImplementation,
    ThreePredicateSeedCatalogAuthorityRepository,
    _canonical_json_bytes,
)
from memorii.core.semantic_ingestion.contracts import contract_digest
from memorii.core.semantic_ingestion.default_catalog_corpus import (
    corpus_resource_sha256,
    load_default_catalog_acceptance_corpus,
)
from memorii.core.semantic_ingestion.default_catalog_package import _DESCRIPTORS
from memorii.core.semantic_ingestion.default_catalog_values import (
    DEFAULT_CATALOG_VALUE_POLICY_HISTORY,
)


def generate(*, output: Path) -> None:
    resource_dir = output.parent / "resources"
    resource_dir.mkdir(parents=True, exist_ok=True)
    descriptor_digests: list[tuple[str, str]] = []
    for role, _kind, module_name, symbol_name in _DESCRIPTORS:
        module = __import__(module_name, fromlist=[symbol_name])
        symbol = getattr(module, symbol_name)
        try:
            source = inspect.getsourcefile(symbol)
        except TypeError:
            source = None
        source = source or inspect.getsourcefile(module)
        if source is None:
            raise RuntimeError("default catalog runtime source is unavailable")
        descriptor = CatalogCapabilityDescriptor(
            schema_version=1, capability_id=f"default_catalog_{role}",
            catalog_digest=ThreePredicateSeedCatalogAuthorityRepository().resolve_base().catalog_digest,
            status="available",
            implementation=CatalogCapabilityImplementation(
                module=module_name, symbol=symbol_name,
                source_sha256=hashlib.sha256(Path(source).read_bytes()).hexdigest(),
            ),
        )
        path = resource_dir / f"default_catalog.{role}.v1.json"
        path.write_bytes(_canonical_json_bytes(descriptor))
        descriptor_digests.append((path.name, hashlib.sha256(path.read_bytes()).hexdigest()))
    body = {
        "schema_version": 1,
        "corpus_digest": load_default_catalog_acceptance_corpus().corpus_digest,
        "corpus_resource_sha256": corpus_resource_sha256(),
        "value_policy_history_digest": contract_digest(
            b"memorii.learned-ontology.default-catalog-value-policy-history.v1",
            tuple(policy.model_dump(mode="python") for policy in DEFAULT_CATALOG_VALUE_POLICY_HISTORY.values()),
        ),
        "descriptor_digests": tuple(sorted(descriptor_digests)),
    }
    authority = body | {
        "authority_digest": contract_digest(
            b"memorii.learned-ontology.default-catalog-package.v1", body
        )
    }
    output.write_text(
        '"""Generated trust anchor for the default-catalog package."""\n\n'
        f"DEFAULT_CATALOG_PACKAGE_AUTHORITY = {authority!r}\n",
        encoding="utf-8",
    )


def main() -> None:
    generate(output=Path(__file__).resolve().parents[1] / "memorii" / "core" / "semantic_ingestion" / "default_catalog_package_root.py")


if __name__ == "__main__":
    main()
