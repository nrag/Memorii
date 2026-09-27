"""Typed package-indexed bundle location and pre-schema pin construction.

Persistence is intentionally not exposed here: a later atomic-store owner must
admit this record under the capture/writer grammar before Hermes may advertise
a schema.  Keeping construction separate prevents a local handle from being
mistaken for durable pin authority.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.semantic_ingestion.catalog_authority import (
    CatalogAuthorityError,
    CatalogAuthorityScope,
    CatalogChildVersionV2,
    CatalogSelectionPointer,
    CatalogVersion,
    ResolvedCatalogAuthority,
    ThreePredicateSeedCatalogAuthorityRepository,
    VerifiedPackagedBaseCatalogRelease,
    catalog_selection_pointer_memory_id,
    catalog_version_memory_id,
    load_packaged_reports_to_release,
)
from memorii.core.semantic_ingestion.contracts import contract_digest
from memorii.core.semantic_ingestion.hermes_captured_turn import HermesCapturedTurnLedger
from memorii.core.semantic_ingestion.project_assertions_profile import load_project_assertions_bundle

_DIGEST = r"^[0-9a-f]{64}$"


class SeedCatalogBundleLocatorError(ValueError):
    """The fixed three-predicate package cannot be used as a seed bundle."""


class SeedCatalogPackageIndexEntry(BaseModel):
    """Exact old-profile package coordinate for the persisted seed version."""

    schema_version: Literal[1]
    catalog_scope: CatalogAuthorityScope
    catalog_digest: str = Field(pattern=_DIGEST)
    seed_version_digest: str = Field(pattern=_DIGEST)
    profile_manifest_digest: str = Field(pattern=_DIGEST)
    semantic_contract_digest: str = Field(pattern=_DIGEST)
    component_fingerprint_digest: str = Field(pattern=_DIGEST)
    entry_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> SeedCatalogPackageIndexEntry:
        body = self.model_dump(mode="python", exclude={"entry_digest"})
        if self.entry_digest != contract_digest(b"memorii.catalog.seed-package-index.v1", body):
            raise ValueError("seed catalog package index digest is invalid")
        return self


class VerifiedSeedCatalogBundle(BaseModel):
    catalog: ResolvedCatalogAuthority
    version: CatalogVersion
    index_entry: SeedCatalogPackageIndexEntry
    runtime_bundle_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_bundle(self) -> VerifiedSeedCatalogBundle:
        if (
            self.version.catalog_scope != self.catalog.catalog_scope
            or self.version.catalog_digest != self.catalog.catalog_digest
            or self.version.parent_version_digest is not None
            or self.index_entry.catalog_scope != self.catalog.catalog_scope
            or self.index_entry.catalog_digest != self.catalog.catalog_digest
            or self.index_entry.seed_version_digest != self.version.version_digest
        ):
            raise ValueError("seed catalog bundle is substituted")
        return self


class SeedCatalogBundleLocator:
    """Verify the legacy profile before deriving its immutable seed coordinate."""

    def locate(self) -> VerifiedSeedCatalogBundle:
        profile = load_project_assertions_bundle()
        catalog = ThreePredicateSeedCatalogAuthorityRepository().resolve_base()
        version = CatalogVersion.genesis(catalog_digest=catalog.catalog_digest)
        try:
            body = {
                "schema_version": 1, "catalog_scope": catalog.catalog_scope,
                "catalog_digest": catalog.catalog_digest, "seed_version_digest": version.version_digest,
                "profile_manifest_digest": profile.profile_digests["profile_manifest_digest"],
                "semantic_contract_digest": profile.profile_digests["semantic_contract_digest"],
                "component_fingerprint_digest": profile.profile_digests["component_fingerprint_digest"],
            }
        except KeyError as exc:
            raise SeedCatalogBundleLocatorError("seed profile bundle is incomplete") from exc
        return VerifiedSeedCatalogBundle(
            catalog=catalog, version=version,
            index_entry=SeedCatalogPackageIndexEntry(
                **body, entry_digest=contract_digest(b"memorii.catalog.seed-package-index.v1", body),
            ),
            # The legacy profile manifest is the immutable runtime closure for
            # the fixed seed; the package-index entry only locates it.
            runtime_bundle_digest=profile.profile_digests["profile_manifest_digest"],
        )


class VerifiedCatalogBundle(BaseModel):
    """One exact package closure selected by a persisted version coordinate."""

    catalog: ResolvedCatalogAuthority
    version: CatalogVersion | CatalogChildVersionV2
    runtime_bundle_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)


class PackageIndexedCatalogBundleLocator:
    """Resolve package bytes from a selected or historical version, never a fallback.

    A child package is intentionally unusable until its complete capability
    closure verifies.  Historical lookup starts from the stored version tuple,
    not the current pointer, so a later pointer rotation cannot reinterpret a
    pin that was already committed under the seed.
    """

    def __init__(
        self,
        *,
        release_authority_loader: Callable[[], VerifiedPackagedBaseCatalogRelease] = load_packaged_reports_to_release,
        default_release_authority_loader: Callable[[], VerifiedPackagedBaseCatalogRelease] | None = None,
    ) -> None:
        self._release_authority_loader = release_authority_loader
        if default_release_authority_loader is None:
            from memorii.core.semantic_ingestion.default_catalog_package import (
                load_packaged_default_catalog_release,
            )

            default_release_authority_loader = load_packaged_default_catalog_release
        self._default_release_authority_loader = default_release_authority_loader

    def locate_selected(
        self, records: Sequence[CanonicalMemoryRecord], *, scope: CatalogAuthorityScope,
    ) -> tuple[VerifiedCatalogBundle, CatalogSelectionPointer]:
        by_id = {record.memory_id: record for record in records}
        pointer_record = by_id.get(catalog_selection_pointer_memory_id(scope))
        if pointer_record is None:
            raise CatalogAuthorityError("catalog selection is unavailable")
        try:
            pointer = CatalogSelectionPointer.model_validate(
                pointer_record.content["catalog_selection_pointer"]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CatalogAuthorityError("catalog selection state is invalid") from exc
        if (
            pointer_record.domain.value != "execution"
            or pointer_record.status.value != "committed"
            or pointer_record.visibility.value != "internal_control"
            or pointer_record.source_kind != "semantic_ingestion_catalog_selection_pointer"
            or pointer.catalog_scope != scope
        ):
            raise CatalogAuthorityError("catalog selection state is invalid")
        bundle = self.locate_historical(
            records, version_id=pointer.selected_version_id,
            version_digest=pointer.selected_version_digest,
        )
        if bundle.catalog.catalog_scope != scope:
            raise CatalogAuthorityError("catalog selection state is invalid")
        return bundle, pointer

    def locate_historical(
        self, records: Sequence[CanonicalMemoryRecord], *, version_id: str, version_digest: str,
    ) -> VerifiedCatalogBundle:
        seed = SeedCatalogBundleLocator().locate()
        if version_id == seed.version.version_id and version_digest == seed.version.version_digest:
            self._require_persisted_version(records, seed.version)
            return VerifiedCatalogBundle(
                catalog=seed.catalog, version=seed.version,
                runtime_bundle_digest=seed.runtime_bundle_digest,
            )
        releases = (
            self._release_authority_loader(),
            self._default_release_authority_loader(),
        )
        release = next(
            (
                candidate for candidate in releases
                if candidate.child_version.version_id == version_id
                and candidate.child_version.version_digest == version_digest
            ),
            None,
        )
        if release is None:
            raise CatalogAuthorityError("catalog version is unavailable")
        version = release.child_version
        # A release decision is only an installation candidate.  Its descriptor
        # closure must be executable before it can authorize a pin or read.
        if not release.selectable:
            raise CatalogAuthorityError("catalog child capabilities are unavailable")
        seed_catalog = ThreePredicateSeedCatalogAuthorityRepository().resolve_base()
        if (
            version.catalog_scope != seed_catalog.catalog_scope
            or version.catalog_digest != seed_catalog.catalog_digest
            or release.catalog_digest != seed_catalog.catalog_digest
            or release.runtime_bundle_digest != version.runtime_bundle_digest
            or release.runtime_bundle.bundle_digest != version.runtime_bundle_digest
        ):
            raise CatalogAuthorityError("catalog child runtime is unavailable")
        self._require_persisted_child_version(records, version)
        return VerifiedCatalogBundle(
            catalog=seed_catalog,
            version=version,
            runtime_bundle_digest=release.runtime_bundle_digest,
        )

    @staticmethod
    def _require_persisted_version(
        records: Sequence[CanonicalMemoryRecord], version: CatalogVersion,
    ) -> None:
        record = next(
            (item for item in records if item.memory_id == catalog_version_memory_id(version)), None
        )
        if record is None:
            raise CatalogAuthorityError("catalog version is unavailable")
        try:
            persisted = CatalogVersion.model_validate(record.content["catalog_version"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CatalogAuthorityError("catalog version is unavailable") from exc
        if (
            record.domain.value != "execution"
            or record.status.value != "committed"
            or record.visibility.value != "internal_control"
            or record.source_kind != "semantic_ingestion_catalog_version"
            or persisted != version
        ):
            raise CatalogAuthorityError("catalog version is unavailable")

    @staticmethod
    def _require_persisted_child_version(
        records: Sequence[CanonicalMemoryRecord], version: CatalogChildVersionV2,
    ) -> None:
        record = next(
            (item for item in records if item.memory_id == catalog_version_memory_id(version)), None
        )
        if record is None:
            raise CatalogAuthorityError("catalog version is unavailable")
        try:
            persisted = CatalogChildVersionV2.model_validate(record.content["catalog_version"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CatalogAuthorityError("catalog version is unavailable") from exc
        if (
            record.domain.value != "execution"
            or record.status.value != "committed"
            or record.visibility.value != "internal_control"
            or record.source_kind != "semantic_ingestion_catalog_version"
            or persisted != version
        ):
            raise CatalogAuthorityError("catalog version is unavailable")


class CatalogCapturedTurnPin(BaseModel):
    """Closed record payload that a later governed CAS persists before schema egress."""

    schema_version: Literal[1]
    capture_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=_DIGEST)
    catalog_scope: CatalogAuthorityScope
    catalog_digest: str = Field(pattern=_DIGEST)
    selected_version_id: str = Field(min_length=1)
    selected_version_digest: str = Field(pattern=_DIGEST)
    runtime_bundle_digest: str = Field(pattern=_DIGEST)
    selection_pointer_digest: str = Field(pattern=_DIGEST)
    pin_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> CatalogCapturedTurnPin:
        body = self.model_dump(mode="python", exclude={"pin_digest"})
        if self.pin_digest != contract_digest(b"memorii.catalog.capture-pin.v1", body):
            raise ValueError("catalog captured-turn pin digest is invalid")
        return self

    @property
    def memory_id(self) -> str:
        return self.memory_id_for_capture(self.capture_id)

    @staticmethod
    def memory_id_for_capture(capture_id: str) -> str:
        return "semantic_ingestion:catalog_capture_pin:" + sha256(
            b"memorii.catalog.capture-pin.v1\0" + capture_id.encode("utf-8")
        ).hexdigest()

    def runtime_coordinate(self) -> CatalogRuntimeCoordinate:
        """Carry the exact persisted catalog closure into pre-graph authority."""
        return CatalogRuntimeCoordinate(
            catalog_scope=self.catalog_scope,
            catalog_digest=self.catalog_digest,
            selected_version_id=self.selected_version_id,
            selected_version_digest=self.selected_version_digest,
            runtime_bundle_digest=self.runtime_bundle_digest,
            capture_pin_digest=self.pin_digest,
            capture_id=self.capture_id,
            pin_memory_id=self.memory_id,
            source_id=self.source_id,
            source_digest=self.source_digest,
        )

    @classmethod
    def seed(
        cls, *, ledger: HermesCapturedTurnLedger, bundle: VerifiedSeedCatalogBundle,
        selection_pointer_digest: str,
    ) -> CatalogCapturedTurnPin:
        return cls.from_bundle(
            ledger=ledger,
            bundle=VerifiedCatalogBundle(
                catalog=bundle.catalog, version=bundle.version,
                runtime_bundle_digest=bundle.runtime_bundle_digest,
            ),
            selection_pointer_digest=selection_pointer_digest,
        )

    @classmethod
    def from_bundle(
        cls, *, ledger: HermesCapturedTurnLedger, bundle: VerifiedCatalogBundle,
        selection_pointer_digest: str,
    ) -> CatalogCapturedTurnPin:
        body = {
            "schema_version": 1, "capture_id": ledger.capture_id, "source_id": ledger.source_id,
            "source_digest": ledger.source_digest,
            "catalog_scope": bundle.catalog.catalog_scope, "catalog_digest": bundle.catalog.catalog_digest,
            "selected_version_id": bundle.version.version_id,
            "selected_version_digest": bundle.version.version_digest,
            "runtime_bundle_digest": bundle.runtime_bundle_digest,
            "selection_pointer_digest": selection_pointer_digest,
        }
        return cls(**body, pin_digest=contract_digest(b"memorii.catalog.capture-pin.v1", body))


class CatalogRuntimeCoordinate(BaseModel):
    """Typed, capture-derived runtime catalog identity; never a caller choice."""

    catalog_scope: CatalogAuthorityScope
    catalog_digest: str = Field(pattern=_DIGEST)
    selected_version_id: str = Field(min_length=1)
    selected_version_digest: str = Field(pattern=_DIGEST)
    runtime_bundle_digest: str = Field(pattern=_DIGEST)
    capture_pin_digest: str = Field(pattern=_DIGEST)
    capture_id: str = Field(min_length=1)
    pin_memory_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=_DIGEST)

    model_config = ConfigDict(extra="forbid", frozen=True)


__all__ = [
    "CatalogCapturedTurnPin", "CatalogRuntimeCoordinate", "SeedCatalogBundleLocator", "SeedCatalogBundleLocatorError",
    "SeedCatalogPackageIndexEntry", "VerifiedCatalogBundle", "VerifiedSeedCatalogBundle",
    "PackageIndexedCatalogBundleLocator",
]
