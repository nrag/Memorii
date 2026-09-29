"""Focused persistence proofs for the source-only Hermes turn capture owner."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.admission import (
    GovernedSourceAdmissionService,
    RetainedSourceOperationRequest,
)
from memorii.core.memory_evolution.atomic_store import (
    PreplanningStoreError,
    SemanticIngestionAtomicStore,
    source_retention_seal_member_id,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    DeliveryIdentity,
    DeliveryPrincipalBinding,
    RequiredOutcomeScopeSet,
)
from memorii.core.memory_evolution.ingestion_time_clock import IngestionTimeClock
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    _has_activated_operation_admission,
    _is_captured_retained_structured_submission_write,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    InMemoryMemoryPlaneStore,
    MemoryPlaneRevisionConflictError,
)
from memorii.core.semantic_ingestion.catalog_authority import (
    AuthenticatedPrincipalAgent,
    CatalogAuthorityScope,
    CatalogOwnerVisibilityGrant,
    CatalogSelectionPointer,
    CatalogVersion,
    FactScopeGrant,
    ResolvedStructuredSubmissionAuthority,
    SelectedCatalogAuthorityRepository,
    SourceScopeGrant,
    _catalog_selection_pointer_record,
    catalog_version_memory_id,
    contract_digest,
    load_packaged_reports_to_release,
)
from memorii.core.semantic_ingestion.catalog_capture_pin import (
    PackageIndexedCatalogBundleLocator,
)
from memorii.core.semantic_ingestion.contracts import TextPreparationPolicy
from memorii.core.semantic_ingestion.hermes_captured_turn import (
    HermesCapturedTurnCompletion,
    HermesCapturedTurnCoordination,
    HermesCapturedTurnLedger,
    HermesCapturedTurnSourceOwner,
)
from memorii.core.semantic_ingestion.source_preparation import (
    InMemoryPreparedSourceRepository,
    TextPreparationService,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility
from tests.fixtures.semantic_ingestion.clean_room_request_fixture import (
    build_prepared_source_authority,
)
from tests.fixtures.semantic_ingestion.scenario_fixture_authority import (
    build_verified_reports_to_scenario_request_catalog,
)
from tests.unit.core.memory_evolution.test_typed_value_artifact_integrity import (
    _publication,
)

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
_SEAL_SCHEMAS = (
    "SourceRetentionTimeAttestation",
    "TransactionGroupCommitTimeAttestation",
)


def _capture_fixture(tmp_path, *, catalog_bundle_locator=None):
    plane = MemoryPlaneService()
    history = _publication(tmp_path, schemas=_SEAL_SCHEMAS)
    writers = SemanticWriterAdmissionStore(
        plane,
        bounded_preplanning_ownership_manifest(),
        now_provider=lambda: NOW,
        typed_value_registry_history=history,
        catalog_bundle_locator=catalog_bundle_locator,
    )
    binding = writers.commit_binding(
        writers.create_initial_evidence_only(
            admission_id="hermes-capture-writer",
            writer_implementation_fingerprint="hermes-capture-writer",
            graph_schema_fingerprint="graph",
        )
    )
    store = SemanticIngestionAtomicStore(
        plane,
        writers,
        now_provider=lambda: NOW,
        ingestion_time_clock=IngestionTimeClock(
            identity="hermes-capture-clock", now_provider=lambda: NOW
        ),
        typed_value_registry_history=history,
        catalog_bundle_locator=catalog_bundle_locator,
    )
    principal = DeliveryPrincipalBinding.create(
        principal_subject_id="principal:hermes-user",
        tenant_partition_id="tenant:hermes-user",
        provider_identity="hermes:local",
    )
    identity = DeliveryIdentity.create(principal, "hermes:session-a:turn-1")
    source = CanonicalMemoryRecord(
        memory_id="hermes:source:session-a:1",
        domain=MemoryDomain.TRANSCRIPT,
        text="Remember that the Atlas owner is Casey.",
        content={"text": "Remember that the Atlas owner is Casey."},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_source",
        timestamp=NOW,
        is_raw_event=True,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    ingress = AuthenticatedIngressContext(
        delivery_principal_binding=principal,
        required_outcome_scopes=RequiredOutcomeScopeSet.create(
            tenant_partition_id="tenant:hermes-user", scopes=set()
        ),
        current_authorized_scopes=RequiredOutcomeScopeSet.create(
            tenant_partition_id="tenant:hermes-user", scopes=set()
        ),
    )
    admission = GovernedSourceAdmissionService(plane).prepare_atomic(
        source=source,
        delivery_identity=identity,
        ingress=ingress,
        operation_id="hermes:session-a:turn-1",
        evidence_only=True,
    )
    policy = TextPreparationPolicy.create(
        max_segment_characters=4096,
        supported_languages=("en",),
        segmentation_algorithm="memorii.semantic-ingestion.safe-sentence-first-paragraph-bounded.v1",
        context_window_algorithm="memorii.semantic-ingestion.owned-partition-whole-boundary-context.v1",
    )
    preparation = TextPreparationService(
        producer=lambda request: build_prepared_source_authority(
            source_id=request.observation.source_id,
            source_digest=request.observation.source_digest or "",
            source_text=request.observation.text,
            preparation_policy=request.policy,
        ),
        repository=InMemoryPreparedSourceRepository(),
    )
    owner = HermesCapturedTurnSourceOwner(
        atomic_store=store,
        preparation=preparation,
        policy=policy,
        writer_binding=lambda: binding,
    )
    return plane, store, owner, admission, binding, policy


def _ledger(admission, policy, *, turn_ordinal: int = 1, message: str = "Remember that the Atlas owner is Casey."):
    prepared_source = build_prepared_source_authority(
        source_id=admission.accepted.source_id,
        source_digest=admission.accepted.source_digest,
        source_text=admission.accepted.observation.text,
        preparation_policy=policy,
    )
    return HermesCapturedTurnLedger(
        installation_id="hermes-installation-a",
        session_id="session-a",
        principal_id="principal:hermes-user",
        agent_id="agent:hermes",
        turn_ordinal=turn_ordinal,
        message_digest=sha256(message.encode("utf-8")).hexdigest(),
        source_id=admission.accepted.source_id,
        source_digest=admission.accepted.source_digest,
        preparation_fingerprint=prepared_source.preparation_fingerprint,
        captured_at=NOW,
    )


def _assistant_admission(plane, *, principal) -> object:
    identity = DeliveryIdentity.create(principal, "hermes:session-a:assistant-1")
    source = CanonicalMemoryRecord(
        memory_id="hermes:source:session-a:assistant:1", domain=MemoryDomain.TRANSCRIPT,
        text="Acknowledged.", content={"text": "Acknowledged."}, status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_source", timestamp=NOW, is_raw_event=True,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    ingress = AuthenticatedIngressContext(
        delivery_principal_binding=principal,
        required_outcome_scopes=RequiredOutcomeScopeSet.create(
            tenant_partition_id="tenant:hermes-user", scopes=set(),
        ),
        current_authorized_scopes=RequiredOutcomeScopeSet.create(
            tenant_partition_id="tenant:hermes-user", scopes=set(),
        ),
    )
    return GovernedSourceAdmissionService(plane).prepare_atomic(
        source=source, delivery_identity=identity, ingress=ingress,
        operation_id="hermes:session-a:assistant-1", evidence_only=True,
    )


def _completion(ledger: HermesCapturedTurnLedger) -> HermesCapturedTurnCompletion:
    return HermesCapturedTurnCompletion(
        capture_id=ledger.capture_id, session_id=ledger.session_id,
        principal_id=ledger.principal_id, agent_id=ledger.agent_id,
        turn_ordinal=ledger.turn_ordinal, user_message_digest=ledger.message_digest,
        assistant_message_digest=sha256(b"Acknowledged.").hexdigest(),
        transcript_digest="c" * 64,
    )


def test_capture_publishes_source_prepared_ledger_and_retention_seal_without_pending_work(tmp_path) -> None:
    plane, _store, owner, admission, _binding, policy = _capture_fixture(tmp_path)
    ledger = _ledger(admission, policy)

    assert owner.capture(admission=admission, ledger=ledger) == admission.accepted

    source = plane.get_record(admission.accepted.source_id)
    prepared = plane.get_record(
        "semantic_ingestion:prepared_source:" + sha256(admission.accepted.source_id.encode()).hexdigest()
    )
    captured = plane.get_record(
        "semantic_ingestion:hermes_captured_turn:" + sha256(ledger.capture_id.encode()).hexdigest()
    )
    coordination = plane.get_record(HermesCapturedTurnCoordination.captured(ledger).memory_id)
    seal = plane.get_record(
        source_retention_seal_member_id(admission.accepted.delivery_identity.delivery_key_digest)
    )
    assert source is not None
    assert prepared is not None and prepared.source_kind == "semantic_ingestion_prepared_source"
    assert captured is not None and captured.content == ledger.model_dump(mode="json")
    assert coordination is not None and coordination.content == {
        "coordination": HermesCapturedTurnCoordination.captured(ledger).model_dump(mode="json")
    }
    assert seal is not None and seal.source_kind == "semantic_ingestion_source_retention_attestation"
    assert not [
        record for record in plane.list_records()
        if record.source_kind in {
            "semantic_ingestion_preplanning_artifact",
            "semantic_ingestion_preplanning_control",
            "semantic_ingestion_retained_source_operation",
        }
    ]


def test_capture_exact_retry_preserves_winning_record_map(tmp_path) -> None:
    plane, _store, owner, admission, _binding, policy = _capture_fixture(tmp_path)
    ledger = _ledger(admission, policy)

    owner.capture(admission=admission, ledger=ledger)
    winner = {record.memory_id: record for record in plane.list_records()}
    assert owner.capture(admission=admission, ledger=ledger) == admission.accepted
    assert {record.memory_id: record for record in plane.list_records()} == winner


def test_captured_completion_atomically_selects_ordinary_or_structured_owner(tmp_path) -> None:
    plane, store, owner, admission, binding, policy = _capture_fixture(tmp_path)
    ledger = _ledger(admission, policy)
    owner.capture(admission=admission, ledger=ledger)
    principal = DeliveryPrincipalBinding.create(
        principal_subject_id="principal:hermes-user", tenant_partition_id="tenant:hermes-user",
        provider_identity="hermes:local",
    )
    ingress = AuthenticatedIngressContext(
        delivery_principal_binding=principal, required_outcome_scopes=admission.accepted.required_outcome_scopes,
        current_authorized_scopes=admission.accepted.required_outcome_scopes,
    )
    assistant = _assistant_admission(plane, principal=principal)
    accepted = store.publish_captured_turn_completion(
        ledger=ledger, assistant=assistant, completion=_completion(ledger),
        authenticated_ingress=ingress, writer_binding=binding,
    )
    assert accepted is not None
    coordination = plane.get_record(HermesCapturedTurnCoordination.captured(ledger).memory_id)
    assert coordination is not None
    assert coordination.content["coordination"]["state"] == "completed_ordinary"
    fence_id = accepted.operation_fence_binding.operation_fence_id
    assert plane.get_record("semantic_ingestion:captured-turn-ordinary-operation:" + fence_id) is not None
    winner = {record.memory_id: record for record in plane.list_records()}
    assert store.publish_captured_turn_completion(
        ledger=ledger, assistant=assistant, completion=_completion(ledger),
        authenticated_ingress=ingress, writer_binding=binding,
    ) is None
    assert {record.memory_id: record for record in plane.list_records()} == winner
    with pytest.raises(PreplanningStoreError, match="completion retry is changed"):
        store.publish_captured_turn_completion(
            ledger=ledger, assistant=assistant,
            completion=_completion(ledger).model_copy(update={"transcript_digest": "d" * 64}),
            authenticated_ingress=ingress, writer_binding=binding,
        )


def test_captured_completion_with_structured_witness_never_creates_ordinary_work(tmp_path) -> None:
    plane, store, owner, admission, binding, policy = _capture_fixture(tmp_path)
    ledger = _ledger(admission, policy)
    owner.capture(admission=admission, ledger=ledger)
    principal = DeliveryPrincipalBinding.create(
        principal_subject_id="principal:hermes-user", tenant_partition_id="tenant:hermes-user",
        provider_identity="hermes:local",
    )
    ingress = AuthenticatedIngressContext(
        delivery_principal_binding=principal, required_outcome_scopes=admission.accepted.required_outcome_scopes,
        current_authorized_scopes=admission.accepted.required_outcome_scopes,
    )
    envelope = b"captured-structured-completion"
    structured = GovernedSourceAdmissionService(plane).allocate_retained_source_operation(
        request=RetainedSourceOperationRequest(
            source_id=admission.accepted.source_id, source_digest=admission.accepted.source_digest,
            canonical_envelope=envelope,
        ), authenticated_ingress=ingress,
    )
    store.publish_captured_retained_structured_submission(
        accepted=structured, canonical_envelope=envelope, proposal_bytes=b"proposal",
        raw_proposal_artifact=b"raw", writer_binding=binding,
    )
    assert store.publish_captured_turn_completion(
        ledger=ledger, assistant=_assistant_admission(plane, principal=principal),
        completion=_completion(ledger), authenticated_ingress=ingress, writer_binding=binding,
    ) is None
    coordination = plane.get_record(HermesCapturedTurnCoordination.captured(ledger).memory_id)
    assert coordination is not None
    assert coordination.content["coordination"]["state"] == "completed_structured"
    assert not [
        record for record in plane.list_records()
        if record.source_kind == "semantic_ingestion_captured_turn_ordinary_operation"
    ]


def test_restart_lookup_denies_matching_coordination_without_its_ledger(tmp_path, monkeypatch) -> None:
    plane, store, owner, admission, _binding, policy = _capture_fixture(tmp_path)
    ledger = _ledger(admission, policy)
    owner.capture(admission=admission, ledger=ledger)
    original = plane.list_records

    def without_ledger(*, source_kind=None, **kwargs):
        records = original(source_kind=source_kind, **kwargs)
        if source_kind == "semantic_ingestion_hermes_captured_turn":
            return []
        return records

    monkeypatch.setattr(plane, "list_records", without_ledger)
    with pytest.raises(PreplanningStoreError, match="coordination is partial"):
        store.find_captured_turn(
            installation_id=ledger.installation_id, session_id=ledger.session_id,
            principal_id=ledger.principal_id, agent_id=ledger.agent_id,
            turn_ordinal=ledger.turn_ordinal, message_digest=ledger.message_digest,
        )


def test_completion_cas_reloads_structured_winner_and_exact_ordinary_retry(tmp_path, monkeypatch) -> None:
    plane, store, owner, admission, binding, policy = _capture_fixture(tmp_path)
    ledger = _ledger(admission, policy)
    owner.capture(admission=admission, ledger=ledger)
    principal = DeliveryPrincipalBinding.create(
        principal_subject_id="principal:hermes-user", tenant_partition_id="tenant:hermes-user",
        provider_identity="hermes:local",
    )
    ingress = AuthenticatedIngressContext(
        delivery_principal_binding=principal, required_outcome_scopes=admission.accepted.required_outcome_scopes,
        current_authorized_scopes=admission.accepted.required_outcome_scopes,
    )
    envelope = b"structured-wins-race"
    structured = GovernedSourceAdmissionService(plane).allocate_retained_source_operation(
        request=RetainedSourceOperationRequest(
            source_id=admission.accepted.source_id, source_digest=admission.accepted.source_digest,
            canonical_envelope=envelope,
        ), authenticated_ingress=ingress,
    )
    original = plane.conditionally_write_records
    injected = False

    def structured_wins(records, *, preconditions, authorization):
        nonlocal injected
        if not injected and any(r.source_kind == "semantic_ingestion_hermes_capture_coordination" for r in records):
            injected = True
            monkeypatch.setattr(plane, "conditionally_write_records", original)
            store.publish_captured_retained_structured_submission(
                accepted=structured, canonical_envelope=envelope, proposal_bytes=b"proposal",
                raw_proposal_artifact=b"raw", writer_binding=binding,
            )
            raise MemoryPlaneRevisionConflictError("structured winner installed")
        return original(records, preconditions=preconditions, authorization=authorization)

    monkeypatch.setattr(plane, "conditionally_write_records", structured_wins)
    assert store.publish_captured_turn_completion(
        ledger=ledger, assistant=_assistant_admission(plane, principal=principal),
        completion=_completion(ledger), authenticated_ingress=ingress, writer_binding=binding,
    ) is None
    coordination = plane.get_record(HermesCapturedTurnCoordination.captured(ledger).memory_id)
    assert coordination is not None
    assert coordination.content["coordination"]["state"] == "completed_structured"
    assert injected


def test_captured_source_classifier_fails_closed_on_partial_evidence(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    plane, store, owner, admission, _binding, policy = _capture_fixture(tmp_path)
    ledger = _ledger(admission, policy)
    assert not store.classify_captured_turn_source(
        source_id="unrelated:source", source_digest="0" * 64,
    )
    owner.capture(admission=admission, ledger=ledger)
    assert store.classify_captured_turn_source(
        source_id=admission.accepted.source_id, source_digest=admission.accepted.source_digest,
    )
    coordination_id = HermesCapturedTurnCoordination.captured(ledger).memory_id
    actual_get = plane.get_record
    monkeypatch.setattr(
        plane, "get_record", lambda memory_id: None if memory_id == coordination_id else actual_get(memory_id),
    )
    with pytest.raises(PreplanningStoreError, match="captured source coordination"):
        store.classify_captured_turn_source(
            source_id=admission.accepted.source_id, source_digest=admission.accepted.source_digest,
        )


def test_capture_pin_load_allows_only_the_pending_structured_successor(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    plane, store, owner, admission, binding, policy = _capture_fixture(tmp_path)
    ledger = _ledger(admission, policy)
    owner.capture(admission=admission, ledger=ledger)
    catalog = SelectedCatalogAuthorityRepository(plane, store._writers).ensure_seed_genesis()
    authenticated = AuthenticatedPrincipalAgent(
        principal_id=ledger.principal_id, agent_id=ledger.agent_id,
    )
    authority = ResolvedStructuredSubmissionAuthority(
        authenticated=authenticated,
        source_grant=SourceScopeGrant(
            grant_id="source:captured-pin", grant_version=1,
            source_scope="task:captured-pin", authenticated=authenticated,
        ),
        fact_grant=FactScopeGrant(
            grant_id="fact:captured-pin", grant_version=1,
            fact_scope="user:captured-pin", authenticated=authenticated,
        ),
        catalog_visibility_grant=CatalogOwnerVisibilityGrant(
            grant_id="catalog:captured-pin", grant_version=1,
            catalog_scope=catalog.catalog_scope, authenticated=authenticated,
            purpose="visibility_status",
        ),
        catalog=catalog,
    )
    store.provision_structured_submission_grant_states(
        authority=authority, writer_binding=binding,
    )
    pin = store.pin_captured_turn_catalog(
        ledger=ledger, authority=authority, writer_binding=binding,
    )
    assert pin is not None
    envelope = b"captured-structured-pin-pending"
    accepted = GovernedSourceAdmissionService(plane).allocate_retained_source_operation(
        request=RetainedSourceOperationRequest(
            source_id=ledger.source_id, source_digest=ledger.source_digest,
            canonical_envelope=envelope,
        ),
        authenticated_ingress=AuthenticatedIngressContext(
            delivery_principal_binding=DeliveryPrincipalBinding.create(
                principal_subject_id="principal:hermes-user",
                tenant_partition_id="tenant:hermes-user", provider_identity="hermes:local",
            ),
            required_outcome_scopes=admission.accepted.required_outcome_scopes,
            current_authorized_scopes=admission.accepted.required_outcome_scopes,
        ),
    )
    store.publish_captured_retained_structured_submission(
        accepted=accepted, canonical_envelope=envelope, proposal_bytes=b"proposal",
        raw_proposal_artifact=b"raw", writer_binding=binding,
    )

    assert store.load_captured_turn_catalog_pin(ledger=ledger, authority=authority) == pin
    release = load_packaged_reports_to_release()
    seed_pointer = CatalogSelectionPointer.genesis(
        version=CatalogVersion.genesis(catalog_digest=catalog.catalog_digest)
    )
    rotated_body = {
        "schema_version": 1,
        "catalog_scope": CatalogAuthorityScope(schema_version=1, kind="base"),
        "selected_version_id": "reports-to-person-person-v1",
        "selected_version_digest": release.child_version_digest,
        "pointer_revision": 2,
        "predecessor_pointer_digest": seed_pointer.pointer_digest,
    }
    rotated = CatalogSelectionPointer(
        **rotated_body,
        pointer_digest=contract_digest(
            b"memorii.learned-ontology.catalog-selection-pointer.v1", rotated_body
        ),
    )
    backend = plane._records
    assert isinstance(backend, InMemoryMemoryPlaneStore)
    backend._records[_catalog_selection_pointer_record(rotated).memory_id] = _catalog_selection_pointer_record(rotated)
    # Retrying an already advertised schema follows the durable pin's seed
    # tuple and never reselects the now incomplete child pointer.
    assert store.pin_captured_turn_catalog(
        ledger=ledger, authority=authority, writer_binding=binding,
    ) == pin
    coordination_id = HermesCapturedTurnCoordination.captured(ledger).memory_id
    coordination_record = plane.get_record(coordination_id)
    assert coordination_record is not None
    foreign = HermesCapturedTurnCoordination.model_validate(
        coordination_record.content["coordination"]
    ).model_copy(update={"session_id": "foreign-session"})
    foreign_record = coordination_record.model_copy(update={
        "content": {"coordination": foreign.model_dump(mode="json")},
    })
    actual_get_record = plane.get_record
    monkeypatch.setattr(
        plane, "get_record",
        lambda memory_id: foreign_record if memory_id == coordination_id else actual_get_record(memory_id),
    )
    with pytest.raises(PreplanningStoreError, match="captured catalog pin is substituted"):
        store.load_captured_turn_catalog_pin(ledger=ledger, authority=authority)
    monkeypatch.setattr(plane, "get_record", actual_get_record)

    principal = DeliveryPrincipalBinding.create(
        principal_subject_id="principal:hermes-user", tenant_partition_id="tenant:hermes-user",
        provider_identity="hermes:local",
    )
    assert store.publish_captured_turn_completion(
        ledger=ledger, assistant=_assistant_admission(plane, principal=principal),
        completion=_completion(ledger),
        authenticated_ingress=AuthenticatedIngressContext(
            delivery_principal_binding=principal,
            required_outcome_scopes=admission.accepted.required_outcome_scopes,
            current_authorized_scopes=admission.accepted.required_outcome_scopes,
        ),
        writer_binding=binding,
    ) is None
    with pytest.raises(PreplanningStoreError, match="captured catalog pin is substituted"):
        store.load_captured_turn_catalog_pin(ledger=ledger, authority=authority)


def test_atomic_capture_pin_uses_the_exact_selectable_child_bundle(tmp_path) -> None:
    scenario = build_verified_reports_to_scenario_request_catalog()
    locator = PackageIndexedCatalogBundleLocator(
        release_authority_loader=lambda: scenario.release
    )
    plane, store, owner, admission, binding, policy = _capture_fixture(
        tmp_path, catalog_bundle_locator=locator
    )
    ledger = _ledger(admission, policy)
    owner.capture(admission=admission, ledger=ledger)
    catalog = SelectedCatalogAuthorityRepository(plane, store._writers).ensure_seed_genesis()
    child = scenario.release.child_version
    seed_pointer = CatalogSelectionPointer.genesis(
        version=CatalogVersion.genesis(catalog_digest=catalog.catalog_digest)
    )
    pointer_body = {
        "schema_version": 1, "catalog_scope": catalog.catalog_scope,
        "selected_version_id": child.version_id,
        "selected_version_digest": child.version_digest,
        "pointer_revision": 2, "predecessor_pointer_digest": seed_pointer.pointer_digest,
    }
    pointer = CatalogSelectionPointer(
        **pointer_body,
        pointer_digest=contract_digest(
            b"memorii.learned-ontology.catalog-selection-pointer.v1", pointer_body
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
    authenticated = AuthenticatedPrincipalAgent(principal_id=ledger.principal_id, agent_id=ledger.agent_id)
    authority = ResolvedStructuredSubmissionAuthority(
        authenticated=authenticated,
        source_grant=SourceScopeGrant(grant_id="source:child", grant_version=1, source_scope="task:child", authenticated=authenticated),
        fact_grant=FactScopeGrant(grant_id="fact:child", grant_version=1, fact_scope="user:child", authenticated=authenticated),
        catalog_visibility_grant=CatalogOwnerVisibilityGrant(grant_id="catalog:child", grant_version=1, catalog_scope=catalog.catalog_scope, authenticated=authenticated, purpose="visibility_status"),
        catalog=catalog,
    )
    store.provision_structured_submission_grant_states(authority=authority, writer_binding=binding)
    pin = store.pin_captured_turn_catalog(ledger=ledger, authority=authority, writer_binding=binding)

    assert pin is not None
    assert pin.selected_version_digest == child.version_digest
    assert pin.runtime_bundle_digest == scenario.release.runtime_bundle.bundle_digest
    assert store.resolve_captured_turn_catalog_dispatch(pin=pin) == "reports_to"


def test_atomic_capture_pin_uses_the_verified_default_catalog_bundle(tmp_path) -> None:
    plane, store, owner, admission, binding, policy = _capture_fixture(tmp_path)
    ledger = _ledger(admission, policy)
    owner.capture(admission=admission, ledger=ledger)
    catalog = SelectedCatalogAuthorityRepository(plane, store._writers).install_default_catalog_release()
    authenticated = AuthenticatedPrincipalAgent(
        principal_id=ledger.principal_id, agent_id=ledger.agent_id
    )
    authority = ResolvedStructuredSubmissionAuthority(
        authenticated=authenticated,
        source_grant=SourceScopeGrant(
            grant_id="source:default", grant_version=1, source_scope="task:default",
            authenticated=authenticated,
        ),
        fact_grant=FactScopeGrant(
            grant_id="fact:default", grant_version=1, fact_scope="user:default",
            authenticated=authenticated,
        ),
        catalog_visibility_grant=CatalogOwnerVisibilityGrant(
            grant_id="catalog:default", grant_version=1, catalog_scope=catalog.catalog_scope,
            authenticated=authenticated, purpose="visibility_status",
        ),
        catalog=catalog,
    )
    store.provision_structured_submission_grant_states(
        authority=authority, writer_binding=binding
    )

    pin = store.pin_captured_turn_catalog(
        ledger=ledger, authority=authority, writer_binding=binding
    )

    assert pin is not None
    assert pin.selected_version_id == "default-catalog-v1"
    assert store.resolve_captured_turn_catalog_dispatch(pin=pin) == "default_catalog"


def test_captured_structured_publication_is_atomic_and_exactly_retryable(tmp_path) -> None:
    plane, store, owner, admission, binding, policy = _capture_fixture(tmp_path)
    ledger = _ledger(admission, policy)
    owner.capture(admission=admission, ledger=ledger)
    envelope = b"captured-structured-envelope"
    accepted = GovernedSourceAdmissionService(plane).allocate_retained_source_operation(
        request=RetainedSourceOperationRequest(
            source_id=admission.accepted.source_id,
            source_digest=admission.accepted.source_digest,
            canonical_envelope=envelope,
        ),
        authenticated_ingress=AuthenticatedIngressContext(
            delivery_principal_binding=DeliveryPrincipalBinding.create(
                principal_subject_id="principal:hermes-user",
                tenant_partition_id="tenant:hermes-user",
                provider_identity="hermes:local",
            ),
            required_outcome_scopes=admission.accepted.required_outcome_scopes,
            current_authorized_scopes=admission.accepted.required_outcome_scopes,
        ),
    )
    store.publish_captured_retained_structured_submission(
        accepted=accepted, canonical_envelope=envelope, proposal_bytes=b"proposal",
        raw_proposal_artifact=b"raw", writer_binding=binding,
    )
    winner = {record.memory_id: record for record in plane.list_records()}
    coordination_record = plane.get_record(HermesCapturedTurnCoordination.captured(ledger).memory_id)
    assert coordination_record is not None
    assert coordination_record.content["coordination"]["state"] == "structured_pending"
    assert coordination_record.content["coordination"]["first_structured_operation_fence_id"] == (
        accepted.operation_fence_binding.operation_fence_id
    )
    assert plane.get_record(
        "semantic_ingestion:retained-structured-submission:" + accepted.operation_fence_binding.operation_fence_id
    ) is not None
    store.publish_captured_retained_structured_submission(
        accepted=accepted, canonical_envelope=envelope, proposal_bytes=b"proposal",
        raw_proposal_artifact=b"raw", writer_binding=binding,
    )
    assert {record.memory_id: record for record in plane.list_records()} == winner

    fence_id = accepted.operation_fence_binding.operation_fence_id
    incoming = [
        record for record in plane.list_records()
        if record.memory_id in {
            "semantic_ingestion:retained-source-operation:" + fence_id,
            "semantic_ingestion:retained-structured-submission:" + fence_id,
            "semantic_ingestion:operation:" + fence_id,
            HermesCapturedTurnCoordination.captured(ledger).memory_id,
        }
        or record.memory_id.startswith("semantic_ingestion:artifact:" + fence_id + ":")
    ]
    current = tuple(plane.list_records())
    assert _is_captured_retained_structured_submission_write(incoming, binding, current)

    prior = next(record for record in current if record.memory_id == coordination_record.memory_id)
    captured_prior = prior.model_copy(update={
        "content": {"coordination": HermesCapturedTurnCoordination.captured(ledger).model_dump(mode="json")}
    })
    bad_coordination = coordination_record.model_copy(update={"content": {"coordination": {
        **coordination_record.content["coordination"],
        "first_structured_operation_fence_id": "wrong-first-fence",
    }}})
    malformed_incoming = [
        bad_coordination if record.memory_id == bad_coordination.memory_id else record
        for record in incoming
    ]
    malformed_current = tuple(
        captured_prior if record.memory_id == captured_prior.memory_id else record
        for record in current
    )
    assert not _is_captured_retained_structured_submission_write(
        malformed_incoming, binding, malformed_current,
    )

    control = plane.get_record("semantic_ingestion:operation:" + fence_id)
    assert control is not None
    assert _has_activated_operation_admission(
        operation_fence=accepted.operation_fence_binding,
        binding=binding,
        current=tuple(plane.list_records()),
        governed=[control],
    )
    link = plane.get_record("semantic_ingestion:retained-source-operation:" + fence_id)
    index = plane.get_record(
        "semantic_ingestion:admission:"
        + accepted.delivery_identity.delivery_key_digest
    )
    assert link is not None and index is not None
    substituted_link = link.model_copy(update={"content": {
        **link.content, "source_admission_index_digest": "0" * 64,
    }})
    substituted_index = index.model_copy(update={"content": {
        **index.content, "writer_admission_digest": "0" * 64,
    }})
    for substituted in (substituted_link, substituted_index):
        altered_current = tuple(
            substituted if record.memory_id == substituted.memory_id else record
            for record in plane.list_records()
        )
        assert not _has_activated_operation_admission(
            operation_fence=accepted.operation_fence_binding,
            binding=binding,
            current=altered_current,
            governed=[control],
        )

    second_envelope = b"captured-structured-envelope-two"
    second = GovernedSourceAdmissionService(plane).allocate_retained_source_operation(
        request=RetainedSourceOperationRequest(
            source_id=admission.accepted.source_id,
            source_digest=admission.accepted.source_digest,
            canonical_envelope=second_envelope,
        ),
        authenticated_ingress=AuthenticatedIngressContext(
            delivery_principal_binding=DeliveryPrincipalBinding.create(
                principal_subject_id="principal:hermes-user",
                tenant_partition_id="tenant:hermes-user", provider_identity="hermes:local",
            ),
            required_outcome_scopes=admission.accepted.required_outcome_scopes,
            current_authorized_scopes=admission.accepted.required_outcome_scopes,
        ),
    )
    store.publish_captured_retained_structured_submission(
        accepted=second, canonical_envelope=second_envelope, proposal_bytes=b"proposal-two",
        raw_proposal_artifact=b"raw-two", writer_binding=binding,
    )
    preserved = plane.get_record(HermesCapturedTurnCoordination.captured(ledger).memory_id)
    assert preserved is not None
    assert preserved.content["coordination"]["first_structured_operation_fence_id"] == fence_id
    assert plane.get_record(
        "semantic_ingestion:retained-structured-submission:"
        + second.operation_fence_binding.operation_fence_id
    ) is not None


@pytest.mark.parametrize(
    ("turn_ordinal", "message"),
    ((2, "Remember that the Atlas owner is Casey."), (1, "Atlas has a different owner.")),
)
def test_capture_rejects_changed_turn_coordinate_or_message_for_existing_source(
    tmp_path, turn_ordinal: int, message: str,
) -> None:
    _plane, _store, owner, admission, _binding, policy = _capture_fixture(tmp_path)
    owner.capture(admission=admission, ledger=_ledger(admission, policy))

    with pytest.raises(PreplanningStoreError, match="captured turn ledger is partial or mismatched"):
        owner.capture(admission=admission, ledger=_ledger(admission, policy, turn_ordinal=turn_ordinal, message=message))


def test_capture_rejects_partial_or_corrupt_recovery(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    plane, _store, owner, admission, _binding, policy = _capture_fixture(tmp_path)
    ledger = _ledger(admission, policy)
    owner.capture(admission=admission, ledger=ledger)
    actual_get = plane.get_record
    monkeypatch.setattr(
        plane,
        "get_record",
        lambda memory_id: None if memory_id == admission.records[0].memory_id else actual_get(memory_id),
    )
    with pytest.raises(PreplanningStoreError, match="captured source admission is partial or mismatched"):
        owner.capture(admission=admission, ledger=ledger)
    monkeypatch.undo()

    # A completed quartet whose durable prepared authority is altered must not
    # be accepted as a retry.
    _plane, _store, owner, admission, _binding, policy = _capture_fixture(tmp_path)
    ledger = _ledger(admission, policy)
    owner.capture(admission=admission, ledger=ledger)
    prepared_id = "semantic_ingestion:prepared_source:" + sha256(admission.accepted.source_id.encode()).hexdigest()
    actual_get = _plane.get_record
    existing = actual_get(prepared_id)
    assert existing is not None
    corrupted = existing.model_copy(update={"content": {**existing.content, "preparation_fingerprint": "0" * 64}})
    monkeypatch.setattr(_plane, "get_record", lambda memory_id: corrupted if memory_id == prepared_id else actual_get(memory_id))
    with pytest.raises(PreplanningStoreError, match="prepared source record fingerprint is substituted"):
        owner.capture(admission=admission, ledger=ledger)

    monkeypatch.undo()
    coordination_id = HermesCapturedTurnCoordination.captured(ledger).memory_id
    coordination = _plane.get_record(coordination_id)
    assert coordination is not None
    corrupted_coordination = coordination.model_copy(update={"content": {"coordination": {}}})
    monkeypatch.setattr(
        _plane,
        "get_record",
        lambda memory_id: corrupted_coordination if memory_id == coordination_id else actual_get(memory_id),
    )
    with pytest.raises(PreplanningStoreError, match="captured turn coordination is partial or mismatched"):
        owner.capture(admission=admission, ledger=ledger)
