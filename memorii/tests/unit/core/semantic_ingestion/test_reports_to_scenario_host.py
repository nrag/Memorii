"""Scenario-host coverage for the verified reports-to child request path."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedHostIngress
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore, _PersistedBatch
from memorii.core.provider.ingestion import StructuredFactSubmissionStatusRequest
from memorii.core.provider.models import ProviderOperation
from memorii.core.scoped_context.authority import InProcessScopedReadAuthority
from memorii.core.semantic_ingestion.catalog_authority import (
    CatalogSelectionPointer,
    CatalogVersion,
    StructuredClaimCatalogBinding,
    _catalog_selection_pointer_record,
    catalog_version_memory_id,
    contract_digest,
)
from memorii.core.semantic_ingestion.contracts import (
    BootstrapSemanticProposalRequestV3,
    ProviderSemanticProposal,
)
from memorii.core.semantic_ingestion.hermes_completed_turn_runtime import HermesCompletedTurnRuntime
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility
from tests.fixtures.semantic_ingestion.scenario_fixture_authority import (
    _scenario_normalization_host_bundle_builder,
    build_scenario_test_provider_service,
    build_verified_reports_to_scenario_request_catalog,
)
from tests.fixtures.semantic_ingestion.source_normalization_fixture_builder import (
    DynamicSourceNormalizationAuthorityProvider,
    build_bootstrap_freeform_prepared_source,
    build_bootstrap_v3_fixture_authority,
)


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _scenario_request(source_text: str):
    catalog = build_verified_reports_to_scenario_request_catalog()
    source = build_bootstrap_freeform_prepared_source(
        source_id="source:reports-to-scenario",
        source_digest=_digest(source_text),
        source_text=source_text,
    )
    issued = build_bootstrap_v3_fixture_authority(
        source=source,
        scenario_request_catalog=catalog,
    )
    host = _scenario_normalization_host_bundle_builder(
        now_provider=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        scenario_request_catalog=catalog,
    )
    request = issued.runtime_authority.proposal_requests[0]
    return catalog, request, host


def test_verified_scenario_host_issues_reports_to_v3_request_and_proposal() -> None:
    catalog, request, host = _scenario_request("Alice reports to Bob.")

    assert catalog.release.selectable is True
    assert catalog.release.child_version_digest
    assert catalog.release.runtime_bundle_digest
    assert request.predicate_catalog.vocabulary_namespace == catalog.vocabulary_namespace
    assert request.predicate_catalog.catalog_fingerprint == catalog.expected_catalog_fingerprint()
    assert tuple(item.predicate_id for item in request.predicate_catalog.predicates) == (
        "employs", "reports_to", "started_on"
    )
    transport = host.bootstrap_v3_proposal_transport
    assert transport is not None
    result = transport(request)
    assert result is not None
    proposal, _encoded = result

    assert proposal.abstained is False
    assert tuple(fact.predicate_id for fact in proposal.facts) == ("reports_to",)
    assert tuple(mention.proposed_type for mention in proposal.mentions) == (
        "PersonName", "PersonName"
    )
    assert tuple(mention.mention_quote for mention in proposal.mentions) == ("Alice", "Bob")


def test_scenario_transport_denies_a_stale_child_catalog_fingerprint() -> None:
    _catalog, request, host = _scenario_request("Alice reports to Bob.")
    stale_request = request.model_copy(update={
        "predicate_catalog": request.predicate_catalog.model_copy(update={
            "vocabulary_namespace": "scenario-reports-to:stale",
        }),
    })

    transport = host.bootstrap_v3_proposal_transport
    assert transport is not None
    result = transport(stale_request)
    assert result is not None
    assert result[0] == ProviderSemanticProposal(abstained=True)


def test_scenario_service_provider_issues_and_transports_the_exact_reports_to_request() -> None:
    catalog = build_verified_reports_to_scenario_request_catalog()
    now = datetime(2026, 7, 30, tzinfo=UTC)
    service = build_scenario_test_provider_service(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: now,
        scenario_request_catalog=catalog,
    )
    service.sync_event(
        operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
        content="Alice reports to Bob.",
        operation_id="scenario-reports-to-provider-build",
        session_id="scenario-session",
        task_id="scenario-task",
        user_id="scenario-user",
        language="en",
        speaker_id="scenario-speaker",
        timestamp=now,
        authenticated_host_ingress=AuthenticatedHostIngress(
            provider_identity="scenario-test-host",
            principal_handle=("scenario-principal", 17),
            session_handle=("scenario-session", 17),
            received_at=now,
        ),
    )
    runtime = service._provider_ingestion._semantic_runtime
    assert runtime is not None and runtime.source_normalization_host_bundle is not None
    provider = runtime.source_normalization_host_bundle.authority_provider
    assert isinstance(provider, DynamicSourceNormalizationAuthorityProvider)
    (invocation,) = provider.issued_invocations()
    materials = provider.materials_for(invocation=invocation)
    request = materials.request
    assert isinstance(request, BootstrapSemanticProposalRequestV3)
    assert request.predicate_catalog.catalog_fingerprint == catalog.expected_catalog_fingerprint()
    result = provider.transport_issued_request(invocation=invocation)

    assert result is not None
    proposal, _encoded = result
    assert proposal.abstained is False
    assert tuple(fact.predicate_id for fact in proposal.facts) == ("reports_to",)


def test_captured_reports_to_child_reaches_native_claim_and_catalog_binding(
    tmp_path: Path,
) -> None:
    from memorii.integrations.hermes_factory import _LocalLevel2StructuredSubmissionResolver

    catalog = build_verified_reports_to_scenario_request_catalog()
    now = datetime.now(UTC)
    storage_root = tmp_path / "memory-plane"
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage_root))
    scoped_read_authority = InProcessScopedReadAuthority(now_provider=lambda: now)
    resolver = _LocalLevel2StructuredSubmissionResolver(
        installation_id="scenario-installation", operator_id="scenario-principal",
        agent_id="scenario-agent", project_task_id="scenario-task",
        authority_is_current=lambda: True, structured_tool_is_current=lambda: True,
        memory_plane=plane,
    )
    service = build_scenario_test_provider_service(
        memory_plane=plane, now_provider=lambda: now,
        scenario_request_catalog=catalog,
        structured_submission_authority_resolver=resolver,
        scoped_read_authority=scoped_read_authority,
    )
    service.ensure_catalog_seed_genesis()
    selected = service._catalog_selection_repository.resolve_selected_base()
    authority = resolver.issued_authority()
    seed_claim_id = "claim:scenario-seed-project-owner"
    seed_claim_digest = _digest("scenario-seed-project-owner")
    seed_projection = CanonicalMemoryRecord(
        memory_id="mem:bootstrap-v3:runtime-claim:scenario-seed-project-owner",
        domain=MemoryDomain.SEMANTIC,
        text="Atlas project owner is Ada.",
        content={
            "runtime_context_projection_kind": "bootstrap_v3_claim_assertion",
            "claim_assertion_id": seed_claim_id,
            "claim_assertion_record_digest": seed_claim_digest,
        },
        status=CommitStatus.COMMITTED, task_id="scenario-task",
        user_id="scenario-principal", agent_id="scenario-agent",
        source_kind="test_scenario_seed_project_owner",
        visibility=MemoryRecordVisibility.RUNTIME_CONTEXT,
    )
    seed_binding = StructuredClaimCatalogBinding(
        schema_version=1, claim_assertion_id=seed_claim_id,
        claim_record_digest=seed_claim_digest,
        catalog_scope=selected.catalog_scope,
        catalog_digest=selected.catalog_digest,
        fact_scope=authority.fact_grant.fact_scope,
        authenticated=authority.authenticated,
    )
    seed_binding_record = CanonicalMemoryRecord(
        memory_id="semantic_ingestion:structured-claim-catalog:" + seed_claim_id,
        domain=MemoryDomain.SEMANTIC, text="",
        content={"binding": seed_binding.model_dump(mode="json")},
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_structured_claim_catalog_binding",
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    child = catalog.release.child_version
    seed_pointer = CatalogSelectionPointer.genesis(
        version=CatalogVersion.genesis(catalog_digest=selected.catalog_digest)
    )
    pointer_body = {
        "schema_version": 1, "catalog_scope": selected.catalog_scope,
        "selected_version_id": child.version_id,
        "selected_version_digest": child.version_digest,
        "pointer_revision": 2,
        "predecessor_pointer_digest": seed_pointer.pointer_digest,
    }
    pointer = CatalogSelectionPointer(
        **pointer_body,
        pointer_digest=contract_digest(
            b"memorii.learned-ontology.catalog-selection-pointer.v1", pointer_body
        ),
    )
    child_record = CanonicalMemoryRecord(
        memory_id=catalog_version_memory_id(child), domain=MemoryDomain.EXECUTION,
        text="", content={"catalog_version": child.model_dump(mode="json")},
        status=CommitStatus.COMMITTED, source_kind="semantic_ingestion_catalog_version",
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
    pointer_record = _catalog_selection_pointer_record(pointer)
    backend = plane._records
    assert isinstance(backend, JsonlMemoryPlaneStore)
    with backend._locked(exclusive=True):
        batches, _ = backend._current_records_unlocked()
        backend._replace_batches([
            *batches,
            _PersistedBatch.create(
                revision=batches[-1].revision + 1,
                data_revision=batches[-1].data_revision + 1,
                records=(
                    seed_projection, seed_binding_record, child_record, pointer_record,
                ),
            ),
        ])
    service.provision_structured_submission_authority(authority=authority)

    runtime = HermesCompletedTurnRuntime(
        service=service, installation_id="scenario-installation",
        issue_host_ingress=lambda session_id, _author_id, received_at, *_args: AuthenticatedHostIngress(
            provider_identity="scenario-test-host",
            principal_handle=("scenario-principal", session_id),
            session_handle=(session_id, 1), received_at=received_at,
        ),
        scoped_read_authority=scoped_read_authority,
        require_current_authority=lambda: None,
        project_task_id="scenario-task", authenticated_agent_id="scenario-agent",
        authenticated_author_id="scenario-principal",
        structured_authority_request=resolver.issued_authority_request(),
        structured_tool_is_current=lambda: True,
        structured_fact_read_authority=resolver.issued_read_authority,
    )
    sentence = "Alice reports to Bob."
    runtime.capture_user_turn(
        session_id="scenario-session", turn_ordinal=1, message=sentence,
        authenticated_author_id="scenario-principal", received_at=now,
    )
    schema = runtime.get_tool_schemas()[0]["function"]["parameters"]
    assert schema["properties"]["proposal"]["properties"]["facts"]["items"]["properties"]["predicate_id"] == {"const": "reports_to"}
    arguments = {
        "schema_version": 1, "source_quote": sentence, "source_quote_start": 0,
        "subject_quote": "Alice", "predicate_anchor_quote": "reports to",
        "object_quote": "Bob",
        "proposal": {
            "abstained": False,
            "mentions": [
                {"local_id": "alice", "mention_quote": "Alice", "mention_context_quote": sentence, "proposed_type": "PersonName"},
                {"local_id": "bob", "mention_quote": "Bob", "mention_context_quote": sentence, "proposed_type": "PersonName"},
            ],
            "facts": [{
                "kind": "fact", "local_id": "reports", "predicate_id": "reports_to",
                "subject_entity_ref": "alice",
                "object": {"kind": "entity", "entity_ref": "bob"},
                "assertion_quote": sentence, "predicate_anchor_quote": "reports to",
                "polarity": "positive", "commitment": "asserted",
                "attributed_to_entity_ref": None, "temporal_qualifier_quotes": [],
            }],
            "corrections": [], "retractions": [], "action_states": [],
            "identity_operations": [],
        },
    }
    result = runtime.handle_tool_call(tool_name="memorii_submit_fact", arguments=arguments)
    recalled = runtime.prefetch(
        query="Who does Alice report to?", session_id="scenario-session",
        authenticated_author_id="scenario-principal", now=now,
    )
    seed_recalled = runtime.prefetch(
        query="Who owns the Atlas project?", session_id="scenario-session",
        authenticated_author_id="scenario-principal", now=now,
    )
    runtime.close()

    reopened_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage_root)
    )
    reopened_resolver = _LocalLevel2StructuredSubmissionResolver(
        installation_id="scenario-installation", operator_id="scenario-principal",
        agent_id="scenario-agent", project_task_id="scenario-task",
        authority_is_current=lambda: True, structured_tool_is_current=lambda: True,
        memory_plane=reopened_plane,
    )
    reopened_scoped_read_authority = InProcessScopedReadAuthority(
        now_provider=lambda: now
    )
    reopened_service = build_scenario_test_provider_service(
        memory_plane=reopened_plane, now_provider=lambda: now,
        scenario_request_catalog=catalog,
        structured_submission_authority_resolver=reopened_resolver,
        scoped_read_authority=reopened_scoped_read_authority,
    )
    reopened_runtime = HermesCompletedTurnRuntime(
        service=reopened_service, installation_id="scenario-installation",
        issue_host_ingress=lambda session_id, _author_id, received_at, *_args: AuthenticatedHostIngress(
            provider_identity="scenario-test-host",
            principal_handle=("scenario-principal", session_id),
            session_handle=(session_id, 1), received_at=received_at,
        ),
        scoped_read_authority=reopened_scoped_read_authority,
        require_current_authority=lambda: None,
        project_task_id="scenario-task", authenticated_agent_id="scenario-agent",
        authenticated_author_id="scenario-principal",
        structured_authority_request=reopened_resolver.issued_authority_request(),
        structured_tool_is_current=lambda: True,
        structured_fact_read_authority=reopened_resolver.issued_read_authority,
    )
    retry = reopened_service.lookup_structured_fact_status(
        StructuredFactSubmissionStatusRequest(
            operation_id=result["operation_id"],
            authority_request=reopened_resolver.issued_authority_request(),
        ),
        authenticated_host_ingress=AuthenticatedHostIngress(
            provider_identity="scenario-test-host",
            principal_handle=("scenario-principal", "scenario-session"),
            session_handle=("scenario-session", 1), received_at=now,
        ),
    )
    recalled_after_reopen = reopened_runtime.prefetch(
        query="Who does Alice report to?", session_id="scenario-session",
        authenticated_author_id="scenario-principal", now=now,
    )
    seed_recalled_after_reopen = reopened_runtime.prefetch(
        query="Who owns the Atlas project?", session_id="scenario-session",
        authenticated_author_id="scenario-principal", now=now,
    )
    authority = reopened_resolver.issued_authority()
    reopened_service.revoke_structured_submission_authority_grant(
        grant_kind="fact", grant=authority.fact_grant,
    )
    denied_after_revoke = reopened_runtime.prefetch(
        query="Who does Alice report to?", session_id="scenario-session",
        authenticated_author_id="scenario-principal", now=now,
    )
    reopened_runtime.close()

    assert result["status"] == "committed"
    assert retry.status == "committed"
    assert retry.operation_id == result["operation_id"]
    assert "Alice reports to Bob" in recalled
    assert "Alice reports to Bob" in recalled_after_reopen
    assert "Atlas project owner is Ada" in seed_recalled
    assert "Atlas project owner is Ada" in seed_recalled_after_reopen
    assert denied_after_revoke == ""
    records = tuple(reopened_plane.list_records())
    assert sum(
        record.content.get("runtime_context_projection_kind")
        == "bootstrap_v3_claim_assertion"
        and record.source_kind == "memory_evolution"
        for record in records
    ) == 1
    binding = next(
        record.content["binding"] for record in records
        if record.source_kind == "semantic_ingestion_structured_claim_catalog_binding"
        and record.content["binding"]["schema_version"] == 2
    )
    assert binding["schema_version"] == 2
    assert binding["selected_version_digest"] == child.version_digest
    assert binding["runtime_bundle_digest"] == catalog.release.runtime_bundle_digest


@pytest.mark.parametrize(
    "source_text",
    (
        "Alice collaborates with Bob.",
        'Alice said "Bob reports to Carol."',
        "If Alice reports to Bob, we will update the chart.",
        "Alice is reported to by Bob.",
    ),
)
def test_verified_scenario_host_abstains_for_reports_to_near_misses(source_text: str) -> None:
    _catalog, request, host = _scenario_request(source_text)

    transport = host.bootstrap_v3_proposal_transport
    assert transport is not None
    result = transport(request)
    assert result is not None
    proposal, _encoded = result

    assert proposal == ProviderSemanticProposal(abstained=True)
