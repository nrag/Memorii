from __future__ import annotations

import json
from threading import Thread
from types import SimpleNamespace
from typing import cast

import pytest
from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
from memorii.core.memory_evolution.ingestion_contracts import SemanticWriterCommitBinding
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    _is_structured_grant_state_write,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane import JsonlMemoryPlaneStore, MemoryPlaneService
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import InMemoryMemoryPlaneStore, PersistedBatch
from memorii.core.semantic_ingestion.catalog_authority import (
    AuthenticatedPrincipalAgent,
    CatalogAuthorityError,
    CatalogAuthorityScope,
    CatalogOwnerVisibilityGrant,
    CatalogSelectionPointer,
    CatalogVersion,
    FactScopeGrant,
    ResolvedStructuredSubmissionAuthority,
    SelectedCatalogAuthorityRepository,
    SourceScopeGrant,
    ThreePredicateSeedCatalogAuthorityRepository,
    catalog_selection_pointer_memory_id,
    catalog_version_memory_id,
    contract_digest,
    load_packaged_reports_to_release,
    load_reports_to_child_declaration,
)
from memorii.core.semantic_ingestion.project_assertions_profile import (
    load_project_assertions_bundle,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility
from pydantic import ValidationError


def _authenticated() -> AuthenticatedPrincipalAgent:
    return AuthenticatedPrincipalAgent(principal_id="principal:alice", agent_id="agent:alice")


def _selected_repository(plane: MemoryPlaneService) -> SelectedCatalogAuthorityRepository:
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest()
    )
    return SelectedCatalogAuthorityRepository(plane, writers)


def test_three_predicate_seed_is_core_selected_and_has_a_verified_genesis_coordinate() -> None:
    authority = ThreePredicateSeedCatalogAuthorityRepository().resolve_base()
    bundle = load_project_assertions_bundle()

    assert authority.catalog_scope.model_dump(mode="json") == {
        "schema_version": 1,
        "kind": "base",
    }
    assert authority.catalog_digest == bundle.profile_digests["predicate_catalog_digest"]
    assert len(authority.genesis_selection_digest) == 64
    assert authority == ThreePredicateSeedCatalogAuthorityRepository().resolve_base()


def test_core_selected_seed_denies_a_caller_expected_digest_mismatch() -> None:
    with pytest.raises(CatalogAuthorityError, match="core-selected seed"):
        ThreePredicateSeedCatalogAuthorityRepository().resolve_base(
            expected_catalog_digest="0" * 64
        )


def test_reports_to_child_is_typed_content_addressed_and_not_selectable() -> None:
    child = load_reports_to_child_declaration()

    assert (
        child.predicate_id, child.subject_type, child.object_type,
        child.scope_class, child.evidence_class, child.lifecycle_class,
        child.read_form,
    ) == ("reports_to", "Person", "Person", "P", "D", "M", "set")
    assert child.parent_version_id == "three-predicate-seed-v1"
    assert child.capability_manifest.artifact_manifest_digest == child.artifact_manifest.manifest_digest
    assert child.capability_manifest.available_capability_ids == ()
    assert child.is_selectable is False
    with pytest.raises(CatalogAuthorityError, match="capabilities are unavailable"):
        child.require_selectable()


def test_reports_to_child_rejects_manifest_tampering(monkeypatch: pytest.MonkeyPatch) -> None:
    from memorii.core.semantic_ingestion import catalog_authority

    resource = catalog_authority.importlib.resources.files(
        "memorii.core.semantic_ingestion.resources"
    ).joinpath("reports_to.catalog-child.v1.json")
    payload = json.loads(resource.read_text(encoding="utf-8"))
    payload["capability_manifest"]["available_capability_ids"] = ["reports_to_tool_grammar"]
    monkeypatch.setattr(
        catalog_authority.importlib.resources, "files",
        lambda _package: SimpleNamespace(
            joinpath=lambda _name: SimpleNamespace(
                read_bytes=lambda: json.dumps(payload).encode("utf-8")
            )
        ),
    )
    with pytest.raises(CatalogAuthorityError, match="catalog child is unavailable"):
        load_reports_to_child_declaration()


def test_packaged_reports_to_release_verifies_the_closed_inert_descriptor_chain() -> None:
    release = load_packaged_reports_to_release()

    assert len(release.catalog_digest) == 64
    assert len(release.child_version_digest) == 64
    assert len(release.runtime_bundle_digest) == 64
    assert len(release.decision_digest) == 64
    assert release.selectable is False


def test_factored_release_verifier_matches_installed_reader_and_rejects_wrong_root() -> None:
    from memorii.core.semantic_ingestion import catalog_authority, catalog_release_root

    expected = load_packaged_reports_to_release()
    assert catalog_authority._load_packaged_reports_to_release(
        resource_bytes=catalog_authority.catalog_resource_bytes,
        package_resource_names=catalog_authority._catalog_package_resource_names,
        release_root=catalog_release_root.REPORTS_TO_RELEASE_MANIFEST_ROOT,
    ) == expected
    with pytest.raises(CatalogAuthorityError, match="release decision is invalid"):
        catalog_authority._load_packaged_reports_to_release(
            resource_bytes=catalog_authority.catalog_resource_bytes,
            package_resource_names=catalog_authority._catalog_package_resource_names,
            release_root="0" * 64,
        )


def test_generated_available_scenario_package_verifies_and_denies_mutations(tmp_path) -> None:
    from memorii.core.semantic_ingestion import catalog_authority
    from scripts.generate_reports_to_catalog_package import generate_package

    available = tuple(sorted(catalog_authority._REPORTS_TO_IMPLEMENTATIONS))
    root = generate_package(
        output_dir=tmp_path, root_module=None, available_capability_ids=available,
    )
    def reader(name: str) -> bytes:
        return (tmp_path / name).read_bytes()

    def names() -> tuple[str, ...]:
        return tuple(path.name for path in tmp_path.iterdir() if path.is_file())
    release = catalog_authority._load_packaged_reports_to_release(
        resource_bytes=reader, package_resource_names=names, release_root=root,
    )
    assert release.selectable is True
    for name, bad_root in (
        ("reports_to.release-manifest.v1.json", "0" * 64),
        ("catalog-package-index.v1.json", root),
        ("reports_to.tool_grammar.v1.json", root),
    ):
        original = (tmp_path / name).read_bytes()
        (tmp_path / name).write_bytes(original + b"\n")
        with pytest.raises(CatalogAuthorityError):
            catalog_authority._load_packaged_reports_to_release(
                resource_bytes=reader, package_resource_names=names, release_root=bad_root,
            )
        (tmp_path / name).write_bytes(original)


def test_packaged_reports_to_release_rejects_a_stale_descendant_byte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.core.semantic_ingestion import catalog_authority

    original = catalog_authority.catalog_resource_bytes

    def stale_byte(name: str) -> bytes:
        payload = original(name)
        return payload + b"\n" if name == "reports_to.tool_grammar.v1.json" else payload

    monkeypatch.setattr(catalog_authority, "catalog_resource_bytes", stale_byte)
    with pytest.raises(CatalogAuthorityError, match="bytes are not canonical"):
        load_packaged_reports_to_release()


def test_packaged_reports_to_release_rejects_duplicate_or_unknown_descriptor_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.core.semantic_ingestion import catalog_authority

    original = catalog_authority.catalog_resource_bytes
    payload = original("reports_to.tool_grammar.v1.json")
    duplicate = payload[:-1] + b',"status":"unavailable"}'

    def duplicate_field(name: str) -> bytes:
        return duplicate if name == "reports_to.tool_grammar.v1.json" else original(name)

    monkeypatch.setattr(catalog_authority, "catalog_resource_bytes", duplicate_field)
    with pytest.raises(CatalogAuthorityError, match="resource is invalid"):
        load_packaged_reports_to_release()

    decoded = json.loads(payload)
    decoded["unexpected"] = True
    unknown = json.dumps(decoded, sort_keys=True, separators=(",", ":")).encode()
    monkeypatch.setattr(
        catalog_authority,
        "catalog_resource_bytes",
        lambda name: unknown if name == "reports_to.tool_grammar.v1.json" else original(name),
    )
    with pytest.raises(CatalogAuthorityError, match="resource is invalid"):
        load_packaged_reports_to_release()


def test_catalog_runtime_bundle_rejects_a_substituted_member_path() -> None:
    from memorii.core.semantic_ingestion import catalog_authority
    from memorii.core.semantic_ingestion.catalog_authority import CatalogRuntimeBundle

    original = catalog_authority.catalog_resource_bytes
    bundle = CatalogRuntimeBundle.model_validate(
        catalog_authority.catalog_resource_json(
            "reports_to.runtime-bundle.v1.json",
            original("reports_to.runtime-bundle.v1.json"),
        )
    )
    members = list(bundle.members)
    first_path, second_path = members[0].resource_path, members[1].resource_path
    members[0] = members[0].model_copy(update={"resource_path": second_path})
    members[1] = members[1].model_copy(update={"resource_path": first_path})
    members.sort(key=lambda member: member.capability_id)
    body = {**bundle.model_dump(mode="python", exclude={"bundle_digest"}), "members": tuple(members)}
    with pytest.raises(ValidationError, match="members are not canonical"):
        CatalogRuntimeBundle(
            **body,
            bundle_digest=contract_digest(b"memorii.learned-ontology.catalog-runtime-bundle.v1", body),
        )


def test_packaged_reports_to_release_rejects_a_valid_but_substituted_index_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.core.semantic_ingestion import catalog_authority
    from memorii.core.semantic_ingestion.catalog_authority import CatalogPackageIndex

    original = catalog_authority.catalog_resource_bytes
    index = CatalogPackageIndex.model_validate(
        catalog_authority.catalog_resource_json(
            "catalog-package-index.v1.json",
            original("catalog-package-index.v1.json"),
        )
    )
    body = {"schema_version": 1, "entries": ()}
    substituted = CatalogPackageIndex(
        **body,
        index_digest=contract_digest(b"memorii.learned-ontology.catalog-package-index.v1", body),
    )

    def substituted_index(name: str) -> bytes:
        return catalog_authority._canonical_json_bytes(substituted) if name == "catalog-package-index.v1.json" else original(name)

    assert index.entries
    monkeypatch.setattr(catalog_authority, "catalog_resource_bytes", substituted_index)
    with pytest.raises(CatalogAuthorityError, match="catalog package index is invalid"):
        load_packaged_reports_to_release()


def test_packaged_reports_to_release_rejects_a_changed_compiled_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.core.semantic_ingestion import catalog_release_root

    monkeypatch.setattr(catalog_release_root, "REPORTS_TO_RELEASE_MANIFEST_ROOT", "0" * 64)
    with pytest.raises(CatalogAuthorityError, match="release decision is invalid"):
        load_packaged_reports_to_release()


def test_packaged_reports_to_release_rejects_an_unknown_or_missing_inventory_member(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.core.semantic_ingestion import catalog_authority

    names = catalog_authority._catalog_package_resource_names()
    monkeypatch.setattr(
        catalog_authority,
        "_catalog_package_resource_names",
        lambda: (*names, "reports_to.unrecognized.v1.json"),
    )
    with pytest.raises(CatalogAuthorityError, match="inventory is invalid"):
        load_packaged_reports_to_release()

    monkeypatch.setattr(
        catalog_authority,
        "_catalog_package_resource_names",
        lambda: tuple(name for name in names if name != "reports_to.trust_policy.v1.json"),
    )
    with pytest.raises(CatalogAuthorityError, match="inventory is invalid"):
        load_packaged_reports_to_release()


def test_selected_seed_genesis_is_a_governed_two_record_persistent_closure() -> None:
    plane = MemoryPlaneService()
    selected = _selected_repository(plane).resolve_selected_base()
    version_records = plane.list_records(source_kind="semantic_ingestion_catalog_version")
    pointer_records = plane.list_records(
        source_kind="semantic_ingestion_catalog_selection_pointer"
    )

    assert selected == _selected_repository(plane).resolve_selected_base()
    assert len(version_records) == len(pointer_records) == 1
    version = CatalogVersion.model_validate(version_records[0].content["catalog_version"])
    pointer = CatalogSelectionPointer.model_validate(
        pointer_records[0].content["catalog_selection_pointer"]
    )
    assert pointer.selected_version_digest == version.version_digest
    assert version.parent_version_digest is None


def test_seed_genesis_is_an_explicit_retry_safe_startup_action() -> None:
    plane = MemoryPlaneService()
    repository = _selected_repository(plane)

    first = repository.ensure_seed_genesis()
    second = repository.ensure_seed_genesis()

    assert second == first
    assert len(plane.list_records(source_kind="semantic_ingestion_catalog_version")) == 1
    assert len(plane.list_records(
        source_kind="semantic_ingestion_catalog_selection_pointer"
    )) == 1


def test_generated_default_catalog_release_selects_the_complete_verified_inventory() -> None:
    from memorii.core.semantic_ingestion.default_catalog_package import (
        _read_descriptor,
        load_packaged_default_catalog_release,
    )

    plane = MemoryPlaneService()
    repository = _selected_repository(plane)
    release = load_packaged_default_catalog_release()

    selected = repository.install_default_catalog_release()
    bundle = repository.resolve_selected_bundle()
    pointer_record = plane.list_records(
        source_kind="semantic_ingestion_catalog_selection_pointer"
    )[0]
    pointer = CatalogSelectionPointer.model_validate(
        pointer_record.content["catalog_selection_pointer"]
    )

    assert selected.catalog_digest == release.catalog_digest
    assert bundle.version == release.child_version
    assert pointer.selected_version_digest == release.child_version_digest
    assert len(release.child_version.predicate_ids) == 56
    assert "reports_to" in release.child_version.predicate_ids
    assert len(release.runtime_bundle.members) == 7
    proposal_adapter, _ = _read_descriptor("default_catalog.proposal_adapter.v1.json")
    assert proposal_adapter.implementation is not None
    assert proposal_adapter.implementation.symbol == (
        "validate_default_catalog_provider_lifecycle_proposal"
    )


def test_default_catalog_policy_capabilities_cover_every_corpus_relation() -> None:
    from memorii.core.semantic_ingestion.default_catalog_capability import (
        DefaultCatalogProtectedReader,
        default_catalog_state_rules,
        default_catalog_temporal_rules,
        default_catalog_trust_rules,
        selected_default_catalog_state_rules,
        selected_default_catalog_temporal_rules,
        selected_default_catalog_trust_rules,
    )

    state = default_catalog_state_rules()
    trust = default_catalog_trust_rules()
    temporal = default_catalog_temporal_rules()

    assert len(state) == len(trust) == len(temporal) == 53
    assert state["work_item_status"].cardinality == "single"
    assert state["reports_to"].cardinality == "multi"
    assert trust["reports_to"].eligible_authority_classes == {"official"}
    assert temporal["obligation_due_on"].valid_time_requirement == "optional"
    assert set(selected_default_catalog_state_rules()) == set(selected_default_catalog_trust_rules()) == set(selected_default_catalog_temporal_rules())
    assert len(selected_default_catalog_state_rules()) == 56
    assert {"project_deadline", "project_owner", "project_status"}.issubset(selected_default_catalog_state_rules())
    assert DefaultCatalogProtectedReader.authorizes_version(
        selected_version_id="default-catalog-v1"
    )
    assert not DefaultCatalogProtectedReader.authorizes_version(
        selected_version_id="substituted"
    )


def test_default_catalog_release_denies_a_missing_or_substituted_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.core.semantic_ingestion import default_catalog_package
    from memorii.core.semantic_ingestion.default_catalog_package import (
        load_packaged_default_catalog_release,
    )

    original = default_catalog_package._read_descriptor
    monkeypatch.setattr(
        default_catalog_package,
        "_read_descriptor",
        lambda _name: (_ for _ in ()).throw(CatalogAuthorityError("missing descriptor")),
    )
    with pytest.raises(CatalogAuthorityError, match="missing descriptor"):
        load_packaged_default_catalog_release()
    monkeypatch.setattr(default_catalog_package, "_read_descriptor", original)

    def substituted(name: str):
        descriptor, payload = original(name)
        return descriptor, payload + b" "

    monkeypatch.setattr(default_catalog_package, "_read_descriptor", substituted)
    with pytest.raises(CatalogAuthorityError, match="descriptor is substituted"):
        load_packaged_default_catalog_release()


def test_selected_default_catalog_reopens_from_jsonl_with_the_same_pointer(tmp_path) -> None:
    path = tmp_path / "default-catalog"
    first_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    first = _selected_repository(first_plane)
    first.install_default_catalog_release()

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    reopened = _selected_repository(reopened_plane)
    selected = reopened.ensure_seed_genesis()
    bundle = reopened.resolve_selected_bundle()

    assert selected == ThreePredicateSeedCatalogAuthorityRepository().resolve_base()
    assert bundle.version.version_id == "default-catalog-v1"


def test_concurrent_fresh_seed_startup_accepts_only_the_exact_winning_pair() -> None:
    plane = MemoryPlaneService()
    repository = _selected_repository(plane)
    results = []
    errors = []

    def initialize() -> None:
        try:
            results.append(repository.ensure_seed_genesis())
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    first = Thread(target=initialize)
    second = Thread(target=initialize)
    first.start()
    second.start()
    first.join()
    second.join()

    assert errors == []
    assert len(results) == 2
    assert results[0] == results[1]
    assert len(plane.list_records(source_kind="semantic_ingestion_catalog_version")) == 1
    assert len(plane.list_records(
        source_kind="semantic_ingestion_catalog_selection_pointer"
    )) == 1


def test_selected_seed_reopens_from_jsonl_with_the_same_genesis_pointer(tmp_path) -> None:
    path = tmp_path / "catalog-genesis"
    first_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    first = _selected_repository(first_plane).ensure_seed_genesis()

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    reopened = _selected_repository(reopened_plane).ensure_seed_genesis()

    assert reopened == first
    assert len(reopened_plane.list_records(
        source_kind="semantic_ingestion_catalog_selection_pointer"
    )) == 1


def test_seed_startup_action_denies_a_partial_persisted_genesis_closure() -> None:
    plane = MemoryPlaneService()
    repository = _selected_repository(plane)
    selected = repository.ensure_seed_genesis()
    version = CatalogVersion.genesis(catalog_digest=selected.catalog_digest)
    pointer_id = catalog_selection_pointer_memory_id(version.catalog_scope)
    backend = plane._records
    assert isinstance(backend, InMemoryMemoryPlaneStore)
    del backend._records[pointer_id]

    with pytest.raises(CatalogAuthorityError, match="control inventory is invalid"):
        repository.ensure_seed_genesis()


def _foreign_catalog_version(selected) -> CatalogVersion:
    seed = CatalogVersion.genesis(catalog_digest=selected.catalog_digest)
    body = {
        **seed.model_dump(mode="python", exclude={"version_digest"}),
        "version_id": "foreign-valid-version-v1",
    }
    return CatalogVersion(
        **body,
        version_digest=contract_digest(
            b"memorii.learned-ontology.catalog-version.v1", body
        ),
    )


def test_seed_startup_action_denies_a_foreign_valid_catalog_version() -> None:
    plane = MemoryPlaneService()
    repository = _selected_repository(plane)
    selected = repository.ensure_seed_genesis()
    foreign = _foreign_catalog_version(selected)
    backend = plane._records
    assert isinstance(backend, InMemoryMemoryPlaneStore)
    backend._records[catalog_version_memory_id(foreign)] = _catalog_version_test_record(foreign)

    with pytest.raises(CatalogAuthorityError, match="control inventory is invalid"):
        repository.ensure_seed_genesis()


def test_seed_startup_action_denies_a_substituted_complete_catalog_pair() -> None:
    plane = MemoryPlaneService()
    repository = _selected_repository(plane)
    selected = repository.ensure_seed_genesis()
    foreign = _foreign_catalog_version(selected)
    pointer = CatalogSelectionPointer.genesis(version=foreign)
    backend = plane._records
    assert isinstance(backend, InMemoryMemoryPlaneStore)
    backend._records = {
        catalog_version_memory_id(foreign): _catalog_version_test_record(foreign),
        catalog_selection_pointer_memory_id(pointer.catalog_scope): (
            _catalog_selection_pointer_test_record(pointer)
        ),
    }

    with pytest.raises(CatalogAuthorityError, match="selection state is invalid"):
        repository.ensure_seed_genesis()


def test_seed_startup_action_denies_foreign_version_after_jsonl_reopen(tmp_path) -> None:
    path = tmp_path / "catalog-extra-version"
    first_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    selected = _selected_repository(first_plane).ensure_seed_genesis()
    foreign = _foreign_catalog_version(selected)
    store = JsonlMemoryPlaneStore(path)
    with store._locked(exclusive=True):
        batches, _records = store._current_records_unlocked()
        previous = batches[-1]
        store._replace_batches([
            *batches,
                PersistedBatch.create(
                    revision=previous.revision + 1,
                    data_revision=previous.data_revision,
                records=(_catalog_version_test_record(foreign),),
            ),
        ])

    reopened = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    with pytest.raises(CatalogAuthorityError, match="control inventory is invalid"):
        _selected_repository(reopened).ensure_seed_genesis()


def _catalog_version_test_record(version: CatalogVersion) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=catalog_version_memory_id(version),
        domain=MemoryDomain.EXECUTION,
        text="",
        content={"catalog_version": version.model_dump(mode="json")},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_catalog_version",
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _catalog_selection_pointer_test_record(
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
    )


def test_present_invalid_catalog_pointer_fails_closed_without_seed_fallback() -> None:
    plane = MemoryPlaneService()
    selected = _selected_repository(plane).resolve_selected_base()
    pointer = CatalogSelectionPointer.genesis(
        version=CatalogVersion.genesis(catalog_digest=selected.catalog_digest)
    )
    pointer_record = CanonicalMemoryRecord(
        memory_id=catalog_selection_pointer_memory_id(pointer.catalog_scope),
        domain=MemoryDomain.EXECUTION, text="",
        content={"catalog_selection_pointer": {
            **pointer.model_dump(mode="json"), "pointer_digest": "0" * 64,
        }},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_catalog_selection_pointer",
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    # This models a corruption beneath the store's write boundary; normal
    # runtime writes cannot create this image after policy installation.
    backend = plane._records
    assert isinstance(backend, InMemoryMemoryPlaneStore)
    backend._records[pointer_record.memory_id] = pointer_record

    with pytest.raises(CatalogAuthorityError, match="selection state is invalid"):
        _selected_repository(plane).resolve_selected_base()


def test_structured_authority_rejects_grant_identity_mismatch_and_unknown_fields() -> None:
    scope = CatalogAuthorityScope(schema_version=1, kind="base")
    with pytest.raises(ValidationError, match="grants do not bind"):
        ResolvedStructuredSubmissionAuthority(
            authenticated=_authenticated(),
            source_grant=SourceScopeGrant(
                grant_id="source:one", grant_version=1, source_scope="user:alice",
                authenticated=AuthenticatedPrincipalAgent(
                    principal_id="principal:alice", agent_id="agent:other"
                ),
            ),
            fact_grant=FactScopeGrant(
                grant_id="fact:one", grant_version=2, fact_scope="user:alice",
                authenticated=_authenticated(),
            ),
            catalog_visibility_grant=CatalogOwnerVisibilityGrant(
                grant_id="catalog:one", grant_version=3, catalog_scope=scope,
                authenticated=_authenticated(), purpose="visibility_status",
            ),
            catalog=ThreePredicateSeedCatalogAuthorityRepository().resolve_base(),
        )
    with pytest.raises(ValidationError):
        CatalogAuthorityScope.model_validate(
            {"schema_version": 1, "kind": "base", "agent_id": "agent:alice"}
        )


def test_structured_grant_state_id_matches_the_writer_policy() -> None:
    from memorii.core.semantic_ingestion.catalog_authority import StructuredGrantState

    grant = SourceScopeGrant(
        grant_id="source:one", grant_version=1, source_scope="user:alice",
        authenticated=_authenticated(),
    )
    state = StructuredGrantState(
        schema_version=1, grant_kind="source", grant=grant, active=True,
    )
    record = CanonicalMemoryRecord(
        memory_id=SemanticIngestionAtomicStore._structured_grant_state_record_id(
            state.grant_kind, state.grant.grant_id,
        ),
        domain=MemoryDomain.EXECUTION, text="", content={"state": state.model_dump(mode="json")},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_structured_grant_state",
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )

    assert _is_structured_grant_state_write(
        [record], cast(SemanticWriterCommitBinding, None)
    ) is True
