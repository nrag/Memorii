from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace

from memorii.core.memory_evolution.models import (
    ClaimAssertionMode,
    ClaimEpistemicStatus,
    ClaimKey,
    ClaimLifecycleState,
    ClaimModality,
    ClaimPolarity,
    ClaimSemanticContext,
    ClaimState,
    ConfidenceComponents,
)
from memorii.core.memory_evolution.record_projection import record_from_claim_state
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.semantic_ingestion.catalog_authority import (
    AuthenticatedPrincipalAgent,
    CatalogAuthorityScope,
    CatalogOwnerVisibilityGrant,
    FactScopeGrant,
    StructuredClaimCatalogBinding,
    StructuredFactReadAuthority,
    StructuredGrantState,
)
from memorii.core.semantic_ingestion.structured_fact_read import (
    StructuredFactReadRequest,
    _LifecycleTransition,
    read_structured_facts_from_snapshot,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility

NOW = datetime(2030, 1, 2, tzinfo=UTC)
_DIGEST = "a" * 64


def _state(
    *,
    claim_id: str,
    subject: str,
    value: str,
    predicate: str,
    active: bool = True,
    updated_at: datetime = NOW,
) -> ClaimState:
    return ClaimState(
        claim_id=claim_id,
        source_claim_id="source:" + claim_id,
        claim_key=ClaimKey(
            subject_entity_id=subject,
            predicate_id=predicate,
            assertion_mode=ClaimAssertionMode.WORLD_ASSERTION,
            epistemic_status=ClaimEpistemicStatus.ASSERTED,
            polarity=ClaimPolarity.POSITIVE,
            modality=ClaimModality.ASSERTION,
        ),
        object_value=value,
        lifecycle_state=ClaimLifecycleState.ACTIVE if active else ClaimLifecycleState.SUPERSEDED,
        confidence=ConfidenceComponents(extraction=1, evidence=1, source_trust=1, calibrated=1),
        semantic_context=ClaimSemanticContext(
            assertion_mode=ClaimAssertionMode.WORLD_ASSERTION,
            epistemic_status=ClaimEpistemicStatus.ASSERTED,
            polarity=ClaimPolarity.POSITIVE,
            modality=ClaimModality.ASSERTION,
            attribution_source_id="source:" + claim_id,
        ),
        valid_from=NOW - timedelta(days=1),
        updated_at=updated_at,
    )


def _records(
    *states: ClaimState, active_grants: bool = True
) -> tuple[tuple[CanonicalMemoryRecord, ...], StructuredFactReadAuthority]:
    authenticated = AuthenticatedPrincipalAgent(principal_id="alice", agent_id="agent")
    scope = CatalogAuthorityScope(schema_version=1, kind="base")
    fact = FactScopeGrant(grant_id="fact", grant_version=1, fact_scope="user:alice", authenticated=authenticated)
    visibility = CatalogOwnerVisibilityGrant(
        grant_id="catalog",
        grant_version=1,
        catalog_scope=scope,
        authenticated=authenticated,
        purpose="visibility_status",
    )
    grant_records = tuple(
        CanonicalMemoryRecord(
            memory_id="semantic_ingestion:structured-grant:"
            + sha256((kind + "\0" + grant.grant_id).encode()).hexdigest(),
            domain=MemoryDomain.EXECUTION,
            text="",
            status=CommitStatus.COMMITTED,
            source_kind="semantic_ingestion_structured_grant_state",
            timestamp=NOW,
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
            content={
                "state": StructuredGrantState(
                    schema_version=1, grant_kind=kind, grant=grant, active=active_grants
                ).model_dump(mode="json")
            },
        )
        for kind, grant in (("fact", fact), ("catalog_visibility", visibility))
    )
    bindings = tuple(
        CanonicalMemoryRecord(
            memory_id="semantic_ingestion:structured-claim-catalog:" + state.claim_id,
            domain=MemoryDomain.SEMANTIC,
            text="",
            status=CommitStatus.COMMITTED,
            source_kind="semantic_ingestion_structured_claim_catalog_binding",
            timestamp=state.updated_at,
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
            content={
                "semantic_ingestion_kind": "structured_claim_catalog_binding",
                "binding": StructuredClaimCatalogBinding(
                    schema_version=2,
                    claim_assertion_id=state.claim_id,
                    claim_record_digest=_DIGEST,
                    catalog_scope=scope,
                    catalog_digest=_DIGEST,
                    fact_scope=fact.fact_scope,
                    authenticated=authenticated,
                    capture_id="capture",
                    pin_memory_id="pin",
                    pin_digest=_DIGEST,
                    selected_version_id="default-catalog-v1",
                    selected_version_digest=_DIGEST,
                    runtime_bundle_digest=_DIGEST,
                ).model_dump(mode="json"),
            },
        )
        for state in states
    )
    projections = tuple(
        CanonicalMemoryRecord(
            memory_id="projection:" + state.claim_id,
            domain=MemoryDomain.SEMANTIC,
            text="",
            status=CommitStatus.COMMITTED,
            source_kind="memory_evolution",
            timestamp=state.updated_at,
            content={
                "runtime_context_projection_kind": "bootstrap_v3_claim_assertion",
                "claim_assertion_id": state.claim_id,
                "claim_assertion_record_digest": _DIGEST,
                "claim_identity": {
                    "assertion_key_at_recording": {
                        "slot": {
                            "predicate_id": state.claim_key.predicate_id,
                        },
                        "value": {
                            "object_kind": "entity",
                            "object_logical_entity_id": state.object_value,
                            "literal_type": None,
                            "canonical_literal_value": None,
                        },
                    },
                    "subject_assertion_ref": {
                        "logical_entity_id_at_assertion": state.claim_key.subject_entity_id,
                    },
                    "object_assertion_ref": {
                        "logical_entity_id_at_assertion": state.object_value,
                    },
                },
            },
        )
        for state in states
    )
    return tuple(
        record_from_claim_state(state=state, source_candidate_id="candidate") for state in states
    ) + grant_records + bindings + projections, StructuredFactReadAuthority(
        authenticated=authenticated, fact_grant=fact, catalog_visibility_grant=visibility
    )


def _bundle(_self, _records, *, version_id, version_digest):
    assert version_id == "default-catalog-v1" and version_digest == _DIGEST
    return SimpleNamespace(
        catalog=SimpleNamespace(
            catalog_scope=CatalogAuthorityScope(schema_version=1, kind="base"), catalog_digest=_DIGEST
        ),
        runtime_bundle_digest=_DIGEST,
    )


def test_current_and_history_are_protected_and_symmetric_views_do_not_persist_inverse(monkeypatch) -> None:
    monkeypatch.setattr(
        "memorii.core.semantic_ingestion.structured_fact_read.PackageIndexedCatalogBundleLocator.locate_historical",
        _bundle,
    )
    monkeypatch.setattr(
        "memorii.core.semantic_ingestion.structured_fact_read.verify_structured_catalog_projection_for_read",
        lambda *args, **kwargs: True,
    )
    original = _state(claim_id="one", subject="alice", value="bob", predicate="partner_of", active=False)
    current = _state(claim_id="two", subject="alice", value="carol", predicate="partner_of")
    records, authority = _records(original, current)

    forward = read_structured_facts_from_snapshot(
        records=records,
        authority=authority,
        request=StructuredFactReadRequest(predicate_id="partner_of", subject_entity_id="alice"),
        now=NOW,
    )
    reverse = read_structured_facts_from_snapshot(
        records=records,
        authority=authority,
        request=StructuredFactReadRequest(predicate_id="partner_of", subject_entity_id="carol"),
        now=NOW,
    )
    history = read_structured_facts_from_snapshot(
        records=records,
        authority=authority,
        request=StructuredFactReadRequest(predicate_id="partner_of", subject_entity_id="alice", view="history"),
        now=NOW,
    )

    assert [item.object_value for item in forward.items] == ["carol"]
    assert [(item.object_value, item.derived_direction) for item in reverse.items] == [("alice", "reverse")]
    assert {item.claim_id for item in history.items} == {"one", "two"}
    assert all(record.content.get("memory_evolution_kind") != "inverse_claim" for record in records)


def test_revoked_grant_denies_current_and_history(monkeypatch) -> None:
    monkeypatch.setattr(
        "memorii.core.semantic_ingestion.structured_fact_read.PackageIndexedCatalogBundleLocator.locate_historical",
        _bundle,
    )
    records, authority = _records(
        _state(claim_id="one", subject="project", value="owner", predicate="project_owned_by"), active_grants=False
    )
    for view in ("current", "history"):
        response = read_structured_facts_from_snapshot(
            records=records,
            authority=authority,
            request=StructuredFactReadRequest(predicate_id="project_owned_by", subject_entity_id="project", view=view),
            now=NOW,
        )
        assert response.status == "denied"
        assert response.items == ()


def test_missing_schema_two_binding_fails_closed() -> None:
    records, authority = _records(
        _state(claim_id="one", subject="project", value="owner", predicate="project_owned_by")
    )
    unbound = tuple(
        record for record in records if record.source_kind != "semantic_ingestion_structured_claim_catalog_binding"
    )
    response = read_structured_facts_from_snapshot(
        records=unbound,
        authority=authority,
        request=StructuredFactReadRequest(
            predicate_id="project_owned_by",
            subject_entity_id="project",
        ),
        now=NOW,
    )
    assert response.status == "unavailable"


def test_system_as_of_is_transaction_time_not_valid_time(monkeypatch) -> None:
    monkeypatch.setattr(
        "memorii.core.semantic_ingestion.structured_fact_read.PackageIndexedCatalogBundleLocator.locate_historical",
        _bundle,
    )
    monkeypatch.setattr(
        "memorii.core.semantic_ingestion.structured_fact_read.verify_structured_catalog_projection_for_read",
        lambda *args, **kwargs: True,
    )
    old = _state(
        claim_id="old",
        subject="project",
        value="ada",
        predicate="project_owned_by",
        updated_at=NOW - timedelta(days=2),
    )
    new = _state(
        claim_id="new",
        subject="project",
        value="bea",
        predicate="project_owned_by",
    )
    records, authority = _records(old, new)
    response = read_structured_facts_from_snapshot(
        records=records,
        authority=authority,
        request=StructuredFactReadRequest(
            predicate_id="project_owned_by",
            subject_entity_id="project",
            system_as_of=NOW - timedelta(days=1),
        ),
        now=NOW,
    )
    assert response.status == "ok"
    assert [item.object_value for item in response.items] == ["ada"]


def test_native_projection_fallback_reconstructs_correction_and_as_of(monkeypatch) -> None:
    monkeypatch.setattr(
        "memorii.core.semantic_ingestion.structured_fact_read.PackageIndexedCatalogBundleLocator.locate_historical",
        _bundle,
    )
    monkeypatch.setattr(
        "memorii.core.semantic_ingestion.structured_fact_read.verify_structured_catalog_projection_for_read",
        lambda *args, **kwargs: True,
    )
    old = _state(
        claim_id="old",
        subject="project",
        value="ada",
        predicate="project_owned_by",
        active=False,
        updated_at=NOW - timedelta(days=2),
    )
    new = _state(
        claim_id="new",
        subject="project",
        value="bea",
        predicate="project_owned_by",
        updated_at=NOW,
    )
    records, authority = _records(old, new)
    projection_only = tuple(
        record for record in records if record.content.get("memory_evolution_kind") != "claim_state"
    )
    monkeypatch.setattr(
        "memorii.core.semantic_ingestion.structured_fact_read._lifecycle_transitions",
        lambda _records: (
            _LifecycleTransition(
                transition_id="transition",
                operation_id="correction",
                transition_kind="correction",
                compared_claim_ids=("old",),
                next_claim_ids=("new",),
                recorded_at=NOW,
            ),
        ),
    )

    current = read_structured_facts_from_snapshot(
        records=projection_only,
        authority=authority,
        request=StructuredFactReadRequest(
            predicate_id="project_owned_by",
            subject_entity_id="project",
        ),
        now=NOW,
    )
    historical = read_structured_facts_from_snapshot(
        records=projection_only,
        authority=authority,
        request=StructuredFactReadRequest(
            predicate_id="project_owned_by",
            subject_entity_id="project",
            view="history",
            system_as_of=NOW - timedelta(days=1),
        ),
        now=NOW,
    )

    assert [(item.claim_id, item.object_value, item.lifecycle_state) for item in current.items] == [
        ("new", "bea", "active")
    ]
    assert [(item.claim_id, item.object_value, item.lifecycle_state) for item in historical.items] == [
        ("old", "ada", "active")
    ]
