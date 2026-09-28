"""Focused contracts for the installed local Level 2 operator CLI."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import memorii.integrations.hermes_local_authority as local_authority
import pytest
from memorii.core.memory_evolution.atomic_store import StructuredSubmissionGrantRevokedError
from memorii.core.memory_evolution.models import EntityType
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import MemoryPlaneRevisionConflictError
from memorii.core.semantic_ingestion.default_catalog_corpus import load_default_catalog_acceptance_corpus
from memorii.core.user_context.preferences import (
    PreferenceReadRequest,
    preference_candidate_sentence,
    preference_close_sentence,
    preference_confirmation_sentence,
    preference_delegation_sentence,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility
from memorii.integrations.hermes_local_authority import (
    LocalLevel2AuthorityError,
    authorize_local_level2,
    authorize_local_structured_tool,
    load_local_level2_authority,
    load_local_structured_tool_authority,
    local_level2_status,
    main,
)
from tests.fixtures.semantic_ingestion.default_catalog_proposals import build_default_catalog_proposal


def _commit_preference_topic(binding, *, relation_id: str, topic_type: EntityType) -> tuple[str, str]:
    """Commit and return one canonical topic through the installed semantic writer."""
    row = next(
        row for row in load_default_catalog_acceptance_corpus().rows
        if row.relation_id == relation_id
    )
    fixture = build_default_catalog_proposal(row)
    runtime = binding.completed_turn_runtime
    runtime.capture_user_turn(
        session_id="session:topic",
        turn_ordinal=1,
        message=fixture.source,
        authenticated_author_id=binding.absent_author_id,
        received_at=datetime.now(UTC),
    )
    assert "memorii_submit_fact" in {
        schema["function"]["name"] for schema in runtime.get_tool_schemas()
    }
    assert runtime.handle_tool_call(
        tool_name="memorii_submit_fact",
        arguments=fixture.tool_arguments(),
    )["status"] == "committed"
    expected_type = topic_type.value.replace("_", "")
    if fixture.subject.proposed_type is not None and fixture.subject.proposed_type.casefold() == expected_type:
        topic_quote = fixture.subject_quote
        topic_position = "subject"
    else:
        assert (
            fixture.object is not None
            and fixture.object.proposed_type is not None
            and fixture.object.proposed_type.casefold() == expected_type
        )
        topic_quote = fixture.object_quote
        topic_position = "object"
    projections = [
        record
        for record in binding.service._memory_plane.list_records()
        if record.content.get("runtime_context_projection_kind") == "bootstrap_v3_claim_assertion"
        and record.content["claim_identity"]["assertion_key_at_recording"]["slot"]["predicate_id"]
        == relation_id
    ]
    assert len(projections) == 1
    identity = projections[0].content["claim_identity"]
    if topic_position == "subject":
        topic_id = identity["subject_assertion_ref"]["logical_entity_id_at_assertion"]
    else:
        topic_id = identity["object_assertion_ref"]["logical_entity_id_at_assertion"]
    assert isinstance(topic_id, str)
    runtime.close()
    return topic_quote, topic_id


def test_installed_preference_uses_existing_canonical_typed_topic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.core.semantic_ingestion.openai_responses_project_assertions import OpenAIResponsesApiClient
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        OpenAIResponsesApiClient,
        "complete",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Preference tools must not call model transport")
        ),
    )
    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    context = SimpleNamespace(
        storage_root=tmp_path / "memorii",
        hermes_home=tmp_path,
        session_id="session:typed-preference",
        user_id="raw:user:one",
        agent_identity="profile:primary",
        platform="cli",
        agent_context="primary",
        agent_workspace="hermes",
        parent_session_id=None,
    )
    topic_binding = build_local_level2_runtime_binding(context)
    topic_quote, topic_id = _commit_preference_topic(
        topic_binding,
        relation_id="product_provided_by",
        topic_type=EntityType.PRODUCT_SERVICE,
    )

    assertion = preference_candidate_sentence(
        topic_quote=topic_quote,
        preference_key="drink",
        value="tea",
    )
    candidate_binding = build_local_level2_runtime_binding(context)
    runtime = candidate_binding.completed_turn_runtime
    runtime.capture_user_turn(
        session_id="session:typed-preference",
        turn_ordinal=2,
        message=assertion,
        authenticated_author_id=candidate_binding.absent_author_id,
        received_at=datetime.now(UTC),
    )
    base_arguments = {
        "topic_quote": topic_quote,
        "preference_key": "drink",
        "value": "tea",
        "source_quote": assertion,
        "source_quote_start": 0,
    }
    before = tuple(candidate_binding.service._memory_plane.list_records(domains=[MemoryDomain.USER]))
    assert runtime.handle_tool_call(
        tool_name="memorii_create_preference_candidate",
        arguments={
            **base_arguments,
            "topic_type": "ProductService",
            "canonical_topic_id": "unknown-topic",
        },
    ) == {"status": "abstained"}
    assert runtime.handle_tool_call(
        tool_name="memorii_create_preference_candidate",
        arguments={
            **base_arguments,
            "topic_type": "Asset",
            "canonical_topic_id": topic_id,
        },
    ) == {"status": "abstained"}
    assert tuple(candidate_binding.service._memory_plane.list_records(domains=[MemoryDomain.USER])) == before
    candidate = runtime.handle_tool_call(
        tool_name="memorii_create_preference_candidate",
        arguments={
            **base_arguments,
            "topic_type": "ProductService",
            "canonical_topic_id": topic_id,
        },
    )
    assert candidate["status"] == "candidate"
    runtime.close()

    confirmation = preference_confirmation_sentence(
        topic_id=topic_id,
        preference_key="drink",
        value="tea",
        source_digest=candidate["source_digest"],
    )
    confirmed_binding = build_local_level2_runtime_binding(context)
    runtime = confirmed_binding.completed_turn_runtime
    runtime.capture_user_turn(
        session_id="session:typed-preference",
        turn_ordinal=3,
        message=confirmation,
        authenticated_author_id=confirmed_binding.absent_author_id,
        received_at=datetime.now(UTC),
    )
    assert runtime.handle_tool_call(
        tool_name="memorii_confirm_preference",
        arguments={
            "preference_id": candidate["preference_id"],
            "preference_key": "drink",
            "value": "tea",
            "source_digest": candidate["source_digest"],
            "approval_quote": confirmation,
            "approval_quote_start": 0,
        },
    )["status"] == "confirmed"
    current = runtime.handle_tool_call(
        tool_name="memorii_read_preference",
        arguments={"view": "current", "canonical_topic_id": topic_id},
    )
    assert [(item["canonical_topic_id"], item["state"]) for item in current["preferences"]] == [
        (topic_id, "confirmed")
    ]
    runtime.close()


def test_authorize_issues_an_installed_bundle_bound_sidecar(tmp_path: Path) -> None:
    result = authorize_local_level2(hermes_home=tmp_path)

    assert result.available is True
    assert result.profile == "memorii.project_assertions@1"
    assert (tmp_path / "memorii" / "installation-id").is_file()
    assert (tmp_path / "memorii" / "local-level2.json").is_file()


def test_cli_acknowledgement_issues_a_sidecar_from_verified_installed_material(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["authorize-local-level2", "--hermes-home", str(tmp_path), "--acknowledge-openai-egress"]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["available"] is True
    assert result["profile"] == "memorii.project_assertions@1"
    assert (tmp_path / "memorii" / "local-level2.json").is_file()


def test_cli_requires_explicit_egress_acknowledgement(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as error:
        main(["authorize-local-level2", "--hermes-home", str(tmp_path)])

    assert error.value.code == 2
    assert not (tmp_path / "memorii").exists()


def test_structured_tool_artifact_is_closed_and_requires_the_verified_bootstrap_sidecar(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(LocalLevel2AuthorityError):
        authorize_local_structured_tool(hermes_home=tmp_path)

    authorize_local_level2(hermes_home=tmp_path)
    assert (
        main(
            [
                "authorize-local-structured-tool",
                "--hermes-home",
                str(tmp_path),
                "--acknowledge-local-memory",
            ]
        )
        == 0
    )
    artifact = json.loads(capsys.readouterr().out)
    assert set(artifact) == local_authority._STRUCTURED_TOOL_FIELDS
    assert artifact["operator_acknowledgement"] == "local_structured_fact_no_egress"
    assert (tmp_path / "memorii" / "local-structured-tool.json").read_bytes().endswith(b"\n")
    assert load_local_structured_tool_authority(hermes_home=tmp_path) == artifact


def test_cli_revokes_factory_derived_grant_before_provisioning(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from memorii.core.memory_plane import JsonlMemoryPlaneStore, MemoryPlaneService
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    binding = build_local_level2_runtime_binding(
        SimpleNamespace(
            storage_root=tmp_path / "memorii",
            hermes_home=tmp_path,
            session_id="session:one",
            user_id="raw:user:one",
            agent_identity="profile:primary",
            platform="cli",
            agent_context="primary",
            agent_workspace="hermes",
            parent_session_id=None,
        )
    )
    binding.completed_turn_runtime.close()
    authorize_local_structured_tool(hermes_home=tmp_path)

    assert (
        main(
            [
                "revoke-local-structured-grant",
                "--hermes-home",
                str(tmp_path),
                "--grant-kind",
                "fact",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == {"grant_kind": "fact", "status": "revoked"}
    states = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(tmp_path / "memorii" / "memory-plane")).list_records(
        source_kind="semantic_ingestion_structured_grant_state"
    )
    assert len(states) == 3
    fact_state = next(
        state for state in states
        if state.content["state"]["grant_kind"] == "fact"
    )
    assert fact_state.content["state"]["active"] is False
    with pytest.raises(StructuredSubmissionGrantRevokedError, match="revoked"):
        build_local_level2_runtime_binding(
            SimpleNamespace(
                storage_root=tmp_path / "memorii",
                hermes_home=tmp_path,
                session_id="session:two",
                user_id="raw:user:one",
                agent_identity="profile:primary",
                platform="cli",
                agent_context="primary",
                agent_workspace="hermes",
                parent_session_id=None,
            )
        )


def test_installed_no_key_preference_tools_persist_through_reopen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.core.provider.service import ProviderMemoryService
    from memorii.core.semantic_ingestion.openai_responses_project_assertions import OpenAIResponsesApiClient
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        OpenAIResponsesApiClient,
        "complete",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Preference tools must not call model transport")
        ),
    )
    monkeypatch.setattr(
        ProviderMemoryService,
        "current_semantic_entity_matches",
        lambda _self, **kwargs: (
            kwargs["canonical_entity_id"] == "entity:tea"
            and kwargs["asserted_type"] == "product_service"
            and kwargs["normalized_alias_key"] == "tea"
        ),
    )
    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    context = SimpleNamespace(
        storage_root=tmp_path / "memorii",
        hermes_home=tmp_path,
        session_id="session:preference",
        user_id="raw:user:one",
        agent_identity="profile:primary",
        platform="cli",
        agent_context="primary",
        agent_workspace="hermes",
        parent_session_id=None,
    )
    topic_quote = "tea"
    topic_id = "entity:tea"
    sentence = preference_candidate_sentence(
        topic_quote=topic_quote,
        preference_key="drink",
        value="tea",
    )
    summary = f'Assistant said, "{sentence}"'
    summary_binding = build_local_level2_runtime_binding(context)
    runtime = summary_binding.completed_turn_runtime
    runtime.capture_user_turn(
        session_id="session:preference",
        turn_ordinal=1,
        message=summary,
        authenticated_author_id=summary_binding.absent_author_id,
        received_at=datetime.now(UTC),
    )
    summary_before = tuple(summary_binding.service._memory_plane.list_records(domains=[MemoryDomain.USER]))
    assert runtime.handle_tool_call(
        tool_name="memorii_create_preference_candidate",
        arguments={
            "topic_type": "ProductService",
            "topic_quote": topic_quote,
            "canonical_topic_id": topic_id,
            "preference_key": "drink",
            "value": "tea",
            "source_quote": summary,
            "source_quote_start": 0,
        },
    ) == {"status": "rejected"}
    assert tuple(summary_binding.service._memory_plane.list_records(domains=[MemoryDomain.USER])) == summary_before
    runtime.close()

    first = build_local_level2_runtime_binding(context)
    runtime = first.completed_turn_runtime
    assert runtime is not None
    runtime.capture_user_turn(
        session_id="session:preference",
        turn_ordinal=2,
        message=sentence,
        authenticated_author_id=first.absent_author_id,
        received_at=datetime.now(UTC),
    )
    assert {schema["function"]["name"] for schema in runtime.get_tool_schemas()} >= {
        "memorii_create_preference_candidate",
        "memorii_confirm_preference",
        "memorii_close_preference",
        "memorii_read_preference",
    }
    assert "memorii_register_preference_topic" not in {
        schema["function"]["name"] for schema in runtime.get_tool_schemas()
    }
    before_user_records = tuple(
        first.service._memory_plane.list_records(domains=[MemoryDomain.USER])
    )
    assert runtime.handle_tool_call(
        tool_name="memorii_submit_fact",
        arguments={"schema_version": 1, "preference": {"value": "tea"}},
    ) == {"status": "rejected"}
    assert tuple(first.service._memory_plane.list_records(domains=[MemoryDomain.USER])) == before_user_records
    assert runtime.handle_tool_call(
        tool_name="memorii_create_preference_candidate",
        arguments={
            "topic_type": "ProductService",
            "topic_quote": topic_quote,
            "canonical_topic_id": "unknown-topic",
            "preference_key": "drink",
            "value": "tea",
            "source_quote": sentence,
            "source_quote_start": 0,
        },
    ) == {"status": "abstained"}
    assert tuple(first.service._memory_plane.list_records(domains=[MemoryDomain.USER])) == before_user_records
    runtime.close()
    candidate_binding = build_local_level2_runtime_binding(context)
    runtime = candidate_binding.completed_turn_runtime
    runtime.capture_user_turn(
        session_id="session:preference",
        turn_ordinal=3,
        message=sentence,
        authenticated_author_id=candidate_binding.absent_author_id,
        received_at=datetime.now(UTC),
    )
    first_source = runtime._active_turn.ledger
    before_candidate_records = tuple(
        candidate_binding.service._memory_plane.list_records(domains=[MemoryDomain.USER])
    )
    invalid_topic = runtime.handle_tool_call(
        tool_name="memorii_create_preference_candidate",
        arguments={
            "topic_type": "Asset",
            "topic_quote": topic_quote,
            "canonical_topic_id": topic_id,
            "preference_key": "drink",
            "value": "tea",
            "source_quote": sentence,
            "source_quote_start": 0,
        },
    )
    assert invalid_topic == {"status": "abstained"}
    assert tuple(candidate_binding.service._memory_plane.list_records(domains=[MemoryDomain.USER])) == before_candidate_records
    candidate_arguments = {
        "topic_type": "ProductService",
        "topic_quote": topic_quote,
        "canonical_topic_id": topic_id,
        "preference_key": "drink",
        "value": "tea",
        "source_quote": sentence,
        "source_quote_start": 0,
    }
    original_write = runtime._preference_service._write
    injected = [False]

    def conflict_once(*args, **kwargs):
        if not injected[0]:
            injected[0] = True
            raise MemoryPlaneRevisionConflictError("injected preference CAS conflict")
        return original_write(*args, **kwargs)

    runtime._preference_service._write = conflict_once
    assert runtime.handle_tool_call(
        tool_name="memorii_create_preference_candidate",
        arguments=candidate_arguments,
    ) == {"status": "unavailable"}
    assert tuple(candidate_binding.service._memory_plane.list_records(domains=[MemoryDomain.USER])) == before_candidate_records
    candidate = runtime.handle_tool_call(
        tool_name="memorii_create_preference_candidate",
        arguments=candidate_arguments,
    )
    assert candidate["status"] == "candidate"
    assert runtime.handle_tool_call(
        tool_name="memorii_confirm_preference",
        arguments={
            "preference_id": candidate["preference_id"],
            "preference_key": candidate["preference_key"],
            "value": candidate["value"],
            "source_digest": candidate["source_digest"],
            "approval_quote": sentence,
            "approval_quote_start": 0,
        },
    ) == {"status": "rejected"}
    assert (
        runtime.handle_tool_call(
            tool_name="memorii_create_preference_candidate",
            arguments={
                "topic_type": "ProductService",
                "topic_quote": topic_quote,
                "canonical_topic_id": topic_id,
                "preference_key": "drink",
                "value": "tea",
                "source_quote": sentence,
                "source_quote_start": 0,
            },
        )["preference_id"]
        == candidate["preference_id"]
    )
    runtime.close()
    second = build_local_level2_runtime_binding(context)
    runtime = second.completed_turn_runtime
    assert runtime is not None
    approval_sentence = preference_confirmation_sentence(
        topic_id=topic_id,
        preference_key="drink",
        value="tea",
        source_digest=candidate["source_digest"],
    )
    runtime.capture_user_turn(
        session_id="session:preference",
        turn_ordinal=5,
        message=approval_sentence,
        authenticated_author_id=second.absent_author_id,
        received_at=datetime.now(UTC),
    )
    approval_source = runtime._active_turn.ledger
    confirmation = {
        "preference_id": candidate["preference_id"],
        "preference_key": candidate["preference_key"],
        "value": candidate["value"],
        "source_digest": candidate["source_digest"],
        "approval_quote": approval_sentence,
        "approval_quote_start": 0,
    }
    assert (
        runtime.handle_tool_call(tool_name="memorii_confirm_preference", arguments=confirmation)["status"]
        == "confirmed"
    )
    runtime.close()
    third = build_local_level2_runtime_binding(context)
    runtime = third.completed_turn_runtime
    assert runtime is not None
    correction_sentence = preference_candidate_sentence(
        topic_quote=topic_quote,
        preference_key="drink",
        value="coffee",
    )
    runtime.capture_user_turn(
        session_id="session:preference",
        turn_ordinal=6,
        message=correction_sentence,
        authenticated_author_id=third.absent_author_id,
        received_at=datetime.now(UTC),
    )
    correction_source = runtime._active_turn.ledger
    correction = runtime.handle_tool_call(
        tool_name="memorii_create_preference_candidate",
        arguments={
            "topic_type": "ProductService",
            "topic_quote": topic_quote,
            "canonical_topic_id": topic_id,
            "preference_key": "drink",
            "value": "coffee",
            "source_quote": correction_sentence,
            "source_quote_start": 0,
        },
    )
    assert correction["status"] == "candidate"
    runtime.close()
    fourth = build_local_level2_runtime_binding(context)
    runtime = fourth.completed_turn_runtime
    assert runtime is not None
    correction_approval = preference_confirmation_sentence(
        topic_id=topic_id,
        preference_key="drink",
        value="coffee",
        source_digest=correction["source_digest"],
    )
    runtime.capture_user_turn(
        session_id="session:preference",
        turn_ordinal=7,
        message=correction_approval,
        authenticated_author_id=fourth.absent_author_id,
        received_at=datetime.now(UTC),
    )
    correction_approval_source = runtime._active_turn.ledger
    assert (
        runtime.handle_tool_call(
            tool_name="memorii_confirm_preference",
            arguments={
                "preference_id": correction["preference_id"],
                "preference_key": "drink",
                "value": "coffee",
                "source_digest": correction["source_digest"],
                "approval_quote": correction_approval,
                "approval_quote_start": 0,
            },
        )["status"]
        == "confirmed"
    )
    assert (
        runtime.handle_tool_call(tool_name="memorii_read_preference", arguments={"view": "current"})["preferences"][0][
            "value"
        ]
        == "coffee"
    )
    runtime.close()
    fifth = build_local_level2_runtime_binding(context)
    runtime = fifth.completed_turn_runtime
    assert runtime is not None
    revocation_sentence = preference_close_sentence(
        state="retracted",
        topic_id=topic_id,
        preference_key="drink",
        value="coffee",
        source_digest=correction["source_digest"],
    )
    runtime.capture_user_turn(
        session_id="session:preference",
        turn_ordinal=8,
        message=revocation_sentence,
        authenticated_author_id=fifth.absent_author_id,
        received_at=datetime.now(UTC),
    )
    revocation_source = runtime._active_turn.ledger
    assert (
        runtime.handle_tool_call(
            tool_name="memorii_close_preference",
            arguments={
                "preference_id": correction["preference_id"],
                "preference_key": "drink",
                "value": "coffee",
                "source_digest": correction["source_digest"],
                "state": "retracted",
                "revocation_quote": revocation_sentence,
                "revocation_quote_start": 0,
            },
        )["status"]
        == "closed"
    )
    assert (
        runtime.handle_tool_call(tool_name="memorii_read_preference", arguments={"view": "current"})["preferences"]
        == []
    )
    runtime.close()
    reopened = build_local_level2_runtime_binding(context)
    reopened_runtime = reopened.completed_turn_runtime
    assert reopened_runtime is not None
    reopened_runtime.capture_user_turn(
        session_id="session:preference",
        turn_ordinal=9,
        message=sentence,
        authenticated_author_id=reopened.absent_author_id,
        received_at=datetime.now(UTC),
    )
    history = reopened_runtime.handle_tool_call(
        tool_name="memorii_read_preference", arguments={"view": "history"}
    )
    assert history["status"] == "ok"
    assert {item["state"] for item in history["preferences"]} == {"superseded", "retracted"}
    events = reopened_runtime._preference_service.read_events(
        PreferenceReadRequest(holder_user_id=reopened.absent_author_id, agent_id=reopened_runtime._authenticated_agent_id)
    )
    assert {
        (
            event.preference_id,
            event.event_type,
            event.evidence_source_id,
            event.evidence_source_digest,
            event.evidence_start,
            event.evidence_end,
        )
        for event in events
    } == {
        (candidate["preference_id"], "candidate_observed", first_source.source_id, first_source.source_digest, 0, len(sentence)),
        (candidate["preference_id"], "confirmed", approval_source.source_id, approval_source.source_digest, 0, len(approval_sentence)),
        (candidate["preference_id"], "superseded", correction_approval_source.source_id, correction_approval_source.source_digest, 0, len(correction_approval)),
        (correction["preference_id"], "candidate_observed", correction_source.source_id, correction_source.source_digest, 0, len(correction_sentence)),
        (correction["preference_id"], "confirmed", correction_approval_source.source_id, correction_approval_source.source_digest, 0, len(correction_approval)),
        (correction["preference_id"], "retracted", revocation_source.source_id, revocation_source.source_digest, 0, len(revocation_sentence)),
    }
    sidecar = tmp_path / "memorii" / "local-level2.json"
    invalid_authority = json.loads(sidecar.read_text(encoding="utf-8"))
    invalid_authority["unexpected"] = True
    sidecar.write_text(json.dumps(invalid_authority), encoding="utf-8")
    assert not any(
        "preference" in schema["function"]["name"]
        for schema in reopened_runtime.get_tool_schemas()
    )
    assert reopened_runtime.handle_tool_call(
        tool_name="memorii_read_preference", arguments={"view": "history"}
    ) == {"status": "denied"}
    reopened_runtime.close()


def test_primary_can_grant_and_revoke_one_persisted_preference_delegate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.integrations.hermes_factory import _canonical_agent_id, build_local_level2_runtime_binding

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    authorize_local_level2(hermes_home=tmp_path)
    authorize_local_structured_tool(hermes_home=tmp_path)
    primary_context = SimpleNamespace(
        storage_root=tmp_path / "memorii",
        hermes_home=tmp_path,
        session_id="session:primary",
        user_id="raw:user:one",
        agent_identity="profile:primary",
        platform="cli",
        agent_context="primary",
        agent_workspace="hermes",
        parent_session_id=None,
    )
    delegated_agent_id = _canonical_agent_id("profile:delegate")
    topic_binding = build_local_level2_runtime_binding(primary_context)
    topic_quote, topic_id = _commit_preference_topic(
        topic_binding,
        relation_id="product_provided_by",
        topic_type=EntityType.PRODUCT_SERVICE,
    )
    preference_sentence = preference_candidate_sentence(
        topic_quote=topic_quote,
        preference_key="drink",
        value="tea",
    )
    primary = build_local_level2_runtime_binding(primary_context)
    primary_runtime = primary.completed_turn_runtime
    primary_runtime.capture_user_turn(
        session_id="session:primary",
        turn_ordinal=2,
        message=preference_sentence,
        authenticated_author_id=primary.absent_author_id,
        received_at=datetime.now(UTC),
    )
    candidate = primary_runtime.handle_tool_call(
        tool_name="memorii_create_preference_candidate",
        arguments={
            "topic_type": "ProductService",
            "topic_quote": topic_quote,
            "canonical_topic_id": topic_id,
            "preference_key": "drink",
            "value": "tea",
            "source_quote": preference_sentence,
            "source_quote_start": 0,
        },
    )
    assert candidate["status"] == "candidate"
    primary_runtime.close()

    confirmation = preference_confirmation_sentence(
        topic_id=topic_id,
        preference_key="drink",
        value="tea",
        source_digest=candidate["source_digest"],
    )
    primary = build_local_level2_runtime_binding(primary_context)
    primary_runtime = primary.completed_turn_runtime
    primary_runtime.capture_user_turn(
        session_id="session:primary",
        turn_ordinal=3,
        message=confirmation,
        authenticated_author_id=primary.absent_author_id,
        received_at=datetime.now(UTC),
    )
    assert primary_runtime.handle_tool_call(
        tool_name="memorii_confirm_preference",
        arguments={
            "preference_id": candidate["preference_id"],
            "preference_key": "drink",
            "value": "tea",
            "source_digest": candidate["source_digest"],
            "approval_quote": confirmation,
            "approval_quote_start": 0,
        },
    )["status"] == "confirmed"
    primary_runtime.close()

    grant_quote = preference_delegation_sentence(
        delegated_agent_id=delegated_agent_id,
        state="active",
    )
    primary = build_local_level2_runtime_binding(primary_context)
    primary_runtime = primary.completed_turn_runtime
    never_granted_context = SimpleNamespace(
        **{
            **vars(primary_context),
            "agent_identity": "profile:never-granted",
            "agent_context": "delegated",
            "agent_workspace": "never-granted",
            "parent_session_id": "session:primary",
        }
    )
    with pytest.raises(LocalLevel2AuthorityError, match="delegation is unavailable"):
        build_local_level2_runtime_binding(never_granted_context)
    primary_runtime.capture_user_turn(
        session_id="session:primary",
        turn_ordinal=4,
        message=grant_quote,
        authenticated_author_id=primary.absent_author_id,
        received_at=datetime.now(UTC),
    )
    assert primary_runtime.handle_tool_call(
        tool_name="memorii_set_preference_delegation",
        arguments={
            "delegated_agent_id": delegated_agent_id,
            "state": "active",
            "approval_quote": grant_quote,
            "approval_quote_start": 0,
        },
    )["status"] == "active"
    primary_runtime.close()

    delegated_context = SimpleNamespace(
        **{
            **vars(primary_context),
            "session_id": "session:delegate",
            "agent_identity": "profile:delegate",
            "agent_context": "delegated",
            "agent_workspace": "delegate-workspace",
            "parent_session_id": "session:primary",
        }
    )
    delegated = build_local_level2_runtime_binding(delegated_context)
    delegated_runtime = delegated.completed_turn_runtime
    delegated_runtime.capture_user_turn(
        session_id="session:delegate",
        turn_ordinal=1,
        message="Read my preferences.",
        authenticated_author_id=delegated.absent_author_id,
        received_at=datetime.now(UTC),
    )
    names = {schema["function"]["name"] for schema in delegated_runtime.get_tool_schemas()}
    assert "memorii_read_preference" in names
    assert "memorii_submit_fact" not in names
    delegated_read = delegated_runtime.handle_tool_call(
        tool_name="memorii_read_preference",
        arguments={"view": "current"},
    )
    assert delegated_read["status"] == "ok"
    assert len(delegated_read["preferences"]) == 1
    delegated_preference = delegated_read["preferences"][0]
    assert delegated_preference["preference_id"] == candidate["preference_id"]
    assert delegated_preference["canonical_topic_id"] == topic_id
    assert delegated_preference["preference_key"] == "drink"
    assert delegated_preference["value"] == "tea"
    assert delegated_preference["state"] == "confirmed"
    delegated_runtime.close()
    delegated = build_local_level2_runtime_binding(delegated_context)
    delegated_runtime = delegated.completed_turn_runtime
    other_agent_id = _canonical_agent_id("profile:other")
    redelegation_quote = preference_delegation_sentence(
        delegated_agent_id=other_agent_id,
        state="active",
    )
    delegated_runtime.capture_user_turn(
        session_id="session:delegate",
        turn_ordinal=2,
        message=redelegation_quote,
        authenticated_author_id=delegated.absent_author_id,
        received_at=datetime.now(UTC),
    )
    assert delegated_runtime.handle_tool_call(
        tool_name="memorii_set_preference_delegation",
        arguments={
            "delegated_agent_id": other_agent_id,
            "state": "active",
            "approval_quote": redelegation_quote,
            "approval_quote_start": 0,
        },
    ) == {"status": "denied"}

    primary = build_local_level2_runtime_binding(primary_context)
    primary_runtime = primary.completed_turn_runtime
    revoke_quote = preference_delegation_sentence(
        delegated_agent_id=delegated_agent_id,
        state="revoked",
    )
    primary_runtime.capture_user_turn(
        session_id="session:primary",
        turn_ordinal=5,
        message=revoke_quote,
        authenticated_author_id=primary.absent_author_id,
        received_at=datetime.now(UTC),
    )
    assert primary_runtime.handle_tool_call(
        tool_name="memorii_set_preference_delegation",
        arguments={
            "delegated_agent_id": delegated_agent_id,
            "state": "revoked",
            "approval_quote": revoke_quote,
            "approval_quote_start": 0,
        },
    )["status"] == "revoked"
    primary_runtime.close()
    assert delegated_runtime.handle_tool_call(
        tool_name="memorii_read_preference",
        arguments={"view": "current"},
    ) == {"status": "denied"}
    delegated_runtime.close()
    with pytest.raises(LocalLevel2AuthorityError, match="delegation is unavailable"):
        build_local_level2_runtime_binding(delegated_context)
    with pytest.raises(LocalLevel2AuthorityError, match="another Hermes user context"):
        build_local_level2_runtime_binding(
            SimpleNamespace(**{**vars(primary_context), "user_id": "raw:user:two"})
        )


def test_installed_preference_valid_until_expires_durably_on_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.core.provider.service import ProviderMemoryService
    from memorii.integrations.hermes_factory import build_local_level2_runtime_binding

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        ProviderMemoryService,
        "current_semantic_entity_matches",
        lambda _self, **kwargs: (
            kwargs["canonical_entity_id"] == "entity:home"
            and kwargs["asserted_type"] == "place"
            and kwargs["normalized_alias_key"] == "home"
        ),
    )
    authorize_local_level2(hermes_home=tmp_path)
    context = SimpleNamespace(
        storage_root=tmp_path / "memorii",
        hermes_home=tmp_path,
        session_id="session:expiry",
        user_id="raw:user:one",
        agent_identity="profile:primary",
        platform="cli",
        agent_context="primary",
        agent_workspace="hermes",
        parent_session_id=None,
    )
    topic_quote = "home"
    topic_id = "entity:home"

    valid_until = datetime.now(UTC) - timedelta(minutes=1)
    assertion = preference_candidate_sentence(
        topic_quote=topic_quote,
        preference_key="temperature",
        value="warm",
        valid_until=valid_until,
    )
    candidate_binding = build_local_level2_runtime_binding(context)
    runtime = candidate_binding.completed_turn_runtime
    runtime.capture_user_turn(
        session_id="session:expiry",
        turn_ordinal=2,
        message=assertion,
        authenticated_author_id=candidate_binding.absent_author_id,
        received_at=datetime.now(UTC),
    )
    before = tuple(candidate_binding.service._memory_plane.list_records(domains=[MemoryDomain.USER]))
    malformed = runtime.handle_tool_call(
        tool_name="memorii_create_preference_candidate",
        arguments={
            "topic_type": "Place",
            "topic_quote": topic_quote,
            "canonical_topic_id": topic_id,
            "preference_key": "temperature",
            "value": "warm",
            "source_quote": assertion,
            "source_quote_start": 0,
            "valid_until": "2026-09-27T12:00:00",
        },
    )
    assert malformed == {"status": "rejected"}
    assert tuple(candidate_binding.service._memory_plane.list_records(domains=[MemoryDomain.USER])) == before
    candidate = runtime.handle_tool_call(
        tool_name="memorii_create_preference_candidate",
        arguments={
            "topic_type": "Place",
            "topic_quote": topic_quote,
            "canonical_topic_id": topic_id,
            "preference_key": "temperature",
            "value": "warm",
            "source_quote": assertion,
            "source_quote_start": 0,
            "valid_until": valid_until.isoformat(),
        },
    )
    runtime.close()

    confirmation = preference_confirmation_sentence(
        topic_id=topic_id,
        preference_key="temperature",
        value="warm",
        source_digest=candidate["source_digest"],
    )
    confirm_binding = build_local_level2_runtime_binding(context)
    runtime = confirm_binding.completed_turn_runtime
    runtime.capture_user_turn(
        session_id="session:expiry",
        turn_ordinal=3,
        message=confirmation,
        authenticated_author_id=confirm_binding.absent_author_id,
        received_at=datetime.now(UTC),
    )
    assert runtime.handle_tool_call(
        tool_name="memorii_confirm_preference",
        arguments={
            "preference_id": candidate["preference_id"],
            "preference_key": "temperature",
            "value": "warm",
            "source_digest": candidate["source_digest"],
            "approval_quote": confirmation,
            "approval_quote_start": 0,
        },
    )["status"] == "confirmed"
    assert runtime.handle_tool_call(
        tool_name="memorii_read_preference", arguments={"view": "current"}
    ) == {"status": "ok", "preferences": []}
    history = runtime.handle_tool_call(
        tool_name="memorii_read_preference", arguments={"view": "history"}
    )
    assert [item["state"] for item in history["preferences"]] == ["expired"]
    runtime.close()

    reopened = build_local_level2_runtime_binding(context)
    runtime = reopened.completed_turn_runtime
    runtime.capture_user_turn(
        session_id="session:expiry",
        turn_ordinal=4,
        message="Read preference history.",
        authenticated_author_id=reopened.absent_author_id,
        received_at=datetime.now(UTC),
    )
    history = runtime.handle_tool_call(
        tool_name="memorii_read_preference", arguments={"view": "history"}
    )
    assert [item["state"] for item in history["preferences"]] == ["expired"]
    events = runtime._preference_service.read_events(
        PreferenceReadRequest(holder_user_id=reopened.absent_author_id, agent_id=runtime._authenticated_agent_id)
    )
    assert [event.event_type for event in events].count("expired") == 1
    runtime.close()


def test_structured_tool_artifact_rejects_unknown_field_and_sidecar_refresh(tmp_path: Path) -> None:
    issued = datetime(2026, 9, 26, tzinfo=UTC)
    authorize_local_level2(hermes_home=tmp_path, now=issued)
    authorize_local_structured_tool(hermes_home=tmp_path, now=issued)
    path = tmp_path / "memorii" / "local-structured-tool.json"
    artifact = json.loads(path.read_text(encoding="utf-8"))
    artifact["unexpected"] = True
    path.write_text(json.dumps(artifact, sort_keys=True, separators=(",", ":")) + "\n", encoding="ascii")
    with pytest.raises(LocalLevel2AuthorityError, match="fields are invalid"):
        load_local_structured_tool_authority(hermes_home=tmp_path)

    authorize_local_structured_tool(hermes_home=tmp_path, now=issued)
    authorize_local_level2(hermes_home=tmp_path, now=issued + timedelta(seconds=1))
    with pytest.raises(LocalLevel2AuthorityError, match="bootstrap binding"):
        load_local_structured_tool_authority(hermes_home=tmp_path)


def test_inspection_summary_distinguishes_sources_graph_ledger_and_recall(tmp_path: Path) -> None:
    records = (
        CanonicalMemoryRecord(
            memory_id="source:1",
            domain=MemoryDomain.TRANSCRIPT,
            text="source",
            status=CommitStatus.COMMITTED,
            source_kind="semantic_ingestion_source",
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        ),
        CanonicalMemoryRecord(
            memory_id="graph:1",
            domain=MemoryDomain.SEMANTIC,
            text="graph",
            content={"member": {"kind": "claim_assertion"}},
            status=CommitStatus.COMMITTED,
            source_kind="semantic_ingestion_bootstrap_graph_v3_member",
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        ),
        CanonicalMemoryRecord(
            memory_id="ledger:1",
            domain=MemoryDomain.SEMANTIC,
            text="ledger",
            status=CommitStatus.COMMITTED,
            source_kind="semantic_ingestion_observation_ledger_entry",
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        ),
        CanonicalMemoryRecord(
            memory_id="recall:1",
            domain=MemoryDomain.SEMANTIC,
            text="Mars Venus 001",
            content={"runtime_context_projection_kind": "bootstrap_v3_claim_assertion"},
            status=CommitStatus.COMMITTED,
            source_kind="semantic_projection",
            visibility=MemoryRecordVisibility.RUNTIME_CONTEXT,
        ),
    )

    summary = local_authority._inspection_summary(
        storage_root=tmp_path / "memorii" / "memory-plane", write_revision=8, records=records
    )

    assert summary["captured_source_count"] == 1
    assert summary["graph_record_count"] == 1
    assert summary["graph_record_counts_by_kind"] == {"claim_assertion": 1}
    assert summary["observation_ledger_entry_count"] == 1
    assert summary["retrieval_visible_record_count"] == 1
    assert summary["runtime_context_projection_count"] == 1


def test_status_maps_sidecar_filesystem_error_to_unavailable(tmp_path: Path) -> None:
    authority_root = tmp_path / "memorii"
    authority_root.mkdir()
    (authority_root / "installation-id").write_text("0" * 64 + "\n", encoding="ascii")
    (authority_root / "local-level2.json").mkdir()

    status = local_level2_status(hermes_home=tmp_path)

    assert status.available is False
    assert status.reason == "local Level 2 authority storage is unavailable"


def test_load_preserves_filesystem_cause_for_callers(tmp_path: Path) -> None:
    authority_root = tmp_path / "memorii"
    authority_root.mkdir()
    (authority_root / "installation-id").write_text("0" * 64 + "\n", encoding="ascii")
    (authority_root / "local-level2.json").mkdir()

    with pytest.raises(LocalLevel2AuthorityError, match="storage is unavailable") as error:
        load_local_level2_authority(hermes_home=tmp_path)

    assert isinstance(error.value.__cause__, OSError)


def test_first_install_stages_before_atomic_no_replace_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installation_path = tmp_path / "memorii" / "installation-id"

    def fail_link(_: Path, __: Path) -> None:
        raise OSError("injected link failure")

    monkeypatch.setattr(local_authority.os, "link", fail_link)
    with pytest.raises(OSError, match="injected link failure"):
        local_authority._atomic_write(installation_path, b"0" * 64 + b"\n", exclusive=True)

    assert not installation_path.exists()
    assert list(installation_path.parent.iterdir()) == []


def test_authorize_maps_write_side_storage_error_to_unavailable_with_cause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_digests = {field: "a" * 64 for field in local_authority._PROFILE_DIGEST_FIELDS}

    def write_denied(_: Path, __: bytes, *, exclusive: bool = False) -> None:
        raise PermissionError("injected write denial")

    monkeypatch.setattr(local_authority, "_registered_profile_digests", lambda: profile_digests)
    monkeypatch.setattr(local_authority, "_atomic_write", write_denied)

    with pytest.raises(LocalLevel2AuthorityError, match="storage is unavailable") as error:
        authorize_local_level2(hermes_home=tmp_path)

    assert isinstance(error.value.__cause__, PermissionError)
    assert not (tmp_path / "memorii" / "local-level2.json").exists()


def test_load_rejects_profile_drift_before_a_factory_can_use_the_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorize_local_level2(hermes_home=tmp_path)
    monkeypatch.setattr(
        local_authority,
        "_registered_profile_digests",
        lambda: {field: "b" * 64 for field in local_authority._PROFILE_DIGEST_FIELDS},
    )

    with pytest.raises(LocalLevel2AuthorityError, match=r"authorization .* is invalid"):
        load_local_level2_authority(hermes_home=tmp_path)
