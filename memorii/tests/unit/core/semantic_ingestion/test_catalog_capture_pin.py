from __future__ import annotations

import importlib.resources
import json
from datetime import UTC, datetime

import pytest
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import InMemoryMemoryPlaneStore
from memorii.core.semantic_ingestion.catalog_authority import (
    CatalogAuthorityError,
    CatalogAuthorityScope,
    CatalogChildVersionV2,
    CatalogSelectionPointer,
    SelectedCatalogAuthorityRepository,
    _catalog_selection_pointer_record,
    catalog_version_memory_id,
    contract_digest,
    load_packaged_reports_to_release,
)
from memorii.core.semantic_ingestion.catalog_capture_pin import (
    CatalogCapturedTurnPin,
    PackageIndexedCatalogBundleLocator,
    SeedCatalogBundleLocator,
)
from memorii.core.semantic_ingestion.hermes_captured_turn import HermesCapturedTurnLedger
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility
from pydantic import ValidationError
from tests.fixtures.semantic_ingestion.scenario_fixture_authority import (
    build_verified_reports_to_scenario_request_catalog,
)


def _ledger() -> HermesCapturedTurnLedger:
    return HermesCapturedTurnLedger(
        installation_id="installation", session_id="session", principal_id="principal:alice",
        agent_id="agent:alice", turn_ordinal=1, message_digest="a" * 64,
        source_id="source", source_digest="b" * 64, preparation_fingerprint="c" * 64,
        captured_at=datetime(2026, 9, 26, tzinfo=UTC),
    )


def test_seed_bundle_locator_binds_verified_legacy_profile_to_exact_seed_version() -> None:
    bundle = SeedCatalogBundleLocator().locate()
    assert bundle.index_entry.seed_version_digest == bundle.version.version_digest
    assert bundle.index_entry.catalog_digest == bundle.catalog.catalog_digest
    assert bundle.version.parent_version_digest is None


def test_seed_pin_is_capture_bound_content_addressed_and_rejects_substitution() -> None:
    pointer_digest = "d" * 64
    pin = CatalogCapturedTurnPin.seed(
        ledger=_ledger(), bundle=SeedCatalogBundleLocator().locate(),
        selection_pointer_digest=pointer_digest,
    )
    assert pin.memory_id.startswith("semantic_ingestion:catalog_capture_pin:")
    assert CatalogCapturedTurnPin.seed(
        ledger=_ledger(), bundle=SeedCatalogBundleLocator().locate(),
        selection_pointer_digest=pointer_digest,
    ) == pin
    with pytest.raises(ValidationError, match="pin digest is invalid"):
        CatalogCapturedTurnPin.model_validate(
            pin.model_dump(mode="json") | {"selected_version_digest": "e" * 64}
        )


def test_selected_incomplete_child_denies_before_pin_and_historical_seed_ignores_rotation() -> None:
    plane = MemoryPlaneService()
    repository = SelectedCatalogAuthorityRepository(
        plane, SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    )
    repository.ensure_seed_genesis()
    _revision, before_rotation = plane.read_snapshot()
    seed = PackageIndexedCatalogBundleLocator().locate_historical(
        before_rotation,
        version_id=SeedCatalogBundleLocator().locate().version.version_id,
        version_digest=SeedCatalogBundleLocator().locate().version.version_digest,
    )
    release = load_packaged_reports_to_release()
    child = CatalogChildVersionV2.model_validate(json.loads(
        importlib.resources.files("memorii.core.semantic_ingestion.resources")
        .joinpath("reports_to.catalog-version.v2.json").read_text(encoding="utf-8")
    ))
    body = {
        "schema_version": 1,
        "catalog_scope": CatalogAuthorityScope(schema_version=1, kind="base"),
        "selected_version_id": "reports-to-person-person-v1",
        "selected_version_digest": release.child_version_digest,
        "pointer_revision": 2,
        "predecessor_pointer_digest": CatalogSelectionPointer.genesis(
            version=SeedCatalogBundleLocator().locate().version
        ).pointer_digest,
    }
    pointer = CatalogSelectionPointer(
        **body,
        pointer_digest=contract_digest(
            b"memorii.learned-ontology.catalog-selection-pointer.v1", body
        ),
    )
    backend = plane._records
    assert isinstance(backend, InMemoryMemoryPlaneStore)
    backend._records[catalog_version_memory_id(child)] = CanonicalMemoryRecord(
        memory_id=catalog_version_memory_id(child), domain=MemoryDomain.EXECUTION,
        text="", content={"catalog_version": child.model_dump(mode="json")},
        status=CommitStatus.COMMITTED, source_kind="semantic_ingestion_catalog_version",
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    backend._records[_catalog_selection_pointer_record(pointer).memory_id] = _catalog_selection_pointer_record(pointer)
    _revision, rotated = plane.read_snapshot()

    with pytest.raises(CatalogAuthorityError, match="child capabilities are unavailable"):
        PackageIndexedCatalogBundleLocator().locate_selected(
            rotated, scope=CatalogAuthorityScope(schema_version=1, kind="base"),
        )
    assert PackageIndexedCatalogBundleLocator().locate_historical(
        rotated,
        version_id=seed.version.version_id,
        version_digest=seed.version.version_digest,
    ) == seed


def test_selected_seed_requires_committed_internal_execution_pointer_record() -> None:
    plane = MemoryPlaneService()
    repository = SelectedCatalogAuthorityRepository(
        plane, SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    )
    repository.ensure_seed_genesis()
    _revision, records = plane.read_snapshot()
    scope = CatalogAuthorityScope(schema_version=1, kind="base")
    bundle, _pointer = PackageIndexedCatalogBundleLocator().locate_selected(
        records, scope=scope
    )
    assert bundle.version == SeedCatalogBundleLocator().locate().version

    pointer_id = _catalog_selection_pointer_record(_pointer).memory_id
    for update in (
        {"status": CommitStatus.CANDIDATE},
        {"domain": MemoryDomain.SEMANTIC},
        {"visibility": MemoryRecordVisibility.RUNTIME_CONTEXT},
    ):
        malformed = tuple(
            record.model_copy(update=update) if record.memory_id == pointer_id else record
            for record in records
        )
        with pytest.raises(CatalogAuthorityError, match="catalog selection state is invalid"):
            PackageIndexedCatalogBundleLocator().locate_selected(malformed, scope=scope)


def test_historical_seed_requires_committed_internal_execution_version_record() -> None:
    plane = MemoryPlaneService()
    repository = SelectedCatalogAuthorityRepository(
        plane, SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    )
    repository.ensure_seed_genesis()
    _revision, records = plane.read_snapshot()
    seed = SeedCatalogBundleLocator().locate().version
    locator = PackageIndexedCatalogBundleLocator()

    assert locator.locate_historical(
        records, version_id=seed.version_id, version_digest=seed.version_digest
    ).version == seed
    version_id = catalog_version_memory_id(seed)
    for update in (
        {"status": CommitStatus.CANDIDATE},
        {"domain": MemoryDomain.SEMANTIC},
        {"visibility": MemoryRecordVisibility.RUNTIME_CONTEXT},
    ):
        malformed = tuple(
            record.model_copy(update=update) if record.memory_id == version_id else record
            for record in records
        )
        with pytest.raises(CatalogAuthorityError, match="catalog version is unavailable"):
            locator.locate_historical(
                malformed, version_id=seed.version_id, version_digest=seed.version_digest
            )


def _persisted_child_version(version: CatalogChildVersionV2) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=catalog_version_memory_id(version),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={"catalog_version": version.model_dump(mode="json")},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_catalog_version",
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def test_available_scenario_child_requires_exact_verified_persisted_version() -> None:
    scenario = build_verified_reports_to_scenario_request_catalog()
    release = scenario.release
    plane = MemoryPlaneService()
    repository = SelectedCatalogAuthorityRepository(
        plane, SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    )
    repository.ensure_seed_genesis()
    backend = plane._records
    assert isinstance(backend, InMemoryMemoryPlaneStore)
    backend._records[catalog_version_memory_id(release.child_version)] = _persisted_child_version(
        release.child_version
    )
    _revision, records = plane.read_snapshot()
    locator = PackageIndexedCatalogBundleLocator(
        release_authority_loader=lambda: release
    )

    bundle = locator.locate_historical(
        records,
        version_id=release.child_version.version_id,
        version_digest=release.child_version.version_digest,
    )

    assert bundle.version == release.child_version
    assert bundle.runtime_bundle_digest == release.runtime_bundle.bundle_digest
    assert bundle.catalog.catalog_digest == release.catalog_digest


@pytest.mark.parametrize("persisted", ("missing", "substituted"))
def test_available_scenario_child_denies_missing_or_substituted_persisted_version(
    persisted: str,
) -> None:
    scenario = build_verified_reports_to_scenario_request_catalog()
    release = scenario.release
    plane = MemoryPlaneService()
    repository = SelectedCatalogAuthorityRepository(
        plane, SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    )
    repository.ensure_seed_genesis()
    if persisted == "substituted":
        backend = plane._records
        assert isinstance(backend, InMemoryMemoryPlaneStore)
        substituted = release.child_version.model_copy(
            update={"version_id": "reports-to-substituted"}
        )
        backend._records[catalog_version_memory_id(release.child_version)] = _persisted_child_version(
            substituted
        )
    _revision, records = plane.read_snapshot()
    locator = PackageIndexedCatalogBundleLocator(
        release_authority_loader=lambda: release
    )

    with pytest.raises(CatalogAuthorityError, match="catalog version is unavailable"):
        locator.locate_historical(
            records,
            version_id=release.child_version.version_id,
            version_digest=release.child_version.version_digest,
        )
