"""Level 2 product proof for the installed Hermes Bootstrap V3 path."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from memorii.core.memory_evolution.admission import source_admission_source_digest
from memorii.core.memory_evolution.record_projection import (
    runtime_context_records_from_committed_claims,
)
from memorii.core.semantic_ingestion.hermes_completed_turn_admission import (
    HermesCompletedTurnAdmissionRequest,
    HermesCompletedTurnAdmissionService,
    HermesCompletedTurnMessage,
)
from memorii.core.semantic_ingestion.hermes_completed_turn_runtime import (
    _canonical_messages_digest,
)
from memorii.integrations.hermes_factory import build_local_level2_runtime_binding
from memorii.integrations.hermes_local_authority import (
    authorize_local_level2,
    inspect_local_memory,
)
from memorii.integrations.hermes_local_authority import (
    main as memorii_hermes_main,
)


def _context(home: Path, *, session_id: str, agent_identity: object | None = "profile:primary") -> SimpleNamespace:
    return SimpleNamespace(
        storage_root=home / "memorii",
        hermes_home=home,
        session_id=session_id,
        user_id="user:ada",
        agent_identity=agent_identity,
        platform="cli",
        agent_context="primary",
        agent_workspace="hermes",
        parent_session_id=None,
    )


def _response(_: object, **kwargs: object) -> str:
    source = str(kwargs.get("source_segment"))
    if "Mars Venus 001 project status is active." in source:
        return (
            '{"abstained":false,"candidates":[{'
            '"predicate_id":"project_status",'
            '"assertion_quote":"Mars Venus 001 project status is active.",'
            '"subject_quote":"Mars Venus 001",'
            '"predicate_anchor_quote":"status",'
            '"value_quote":"active"}]}'
        )
    return (
        '{"abstained":false,"candidates":[{'
        '"predicate_id":"project_owner",'
        '"assertion_quote":"Mars Venus 001 project owner is Ada.",'
        '"subject_quote":"Mars Venus 001",'
        '"predicate_anchor_quote":"owner",'
        '"value_quote":"Ada"}]}'
    )


def test_installed_hermes_abstained_turn_is_terminal_and_does_not_block_reopen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from memorii.core.semantic_ingestion.openai_responses_project_assertions import (
        OpenAIResponsesApiClient,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls: list[str] = []

    def response(_: object, **kwargs: object) -> str:
        source = str(kwargs.get("source_segment"))
        calls.append(source)
        if "project name is Mars Venus 001" in source:
            return '{"abstained":true,"candidates":[]}'
        return _response(_, **kwargs)

    monkeypatch.setattr(OpenAIResponsesApiClient, "complete", response)
    authorize_local_level2(hermes_home=tmp_path)
    first = build_local_level2_runtime_binding(_context(tmp_path, session_id="session:abstained"))
    runtime = first.completed_turn_runtime
    assert runtime is not None
    runtime.wait_for_idle()
    runtime.sync_completed_turn(
        user_content="For this session the project name is Mars Venus 001.",
        assistant_content="Understood.",
        messages=[
            {"role": "user", "content": "For this session the project name is Mars Venus 001."},
            {"role": "assistant", "content": "Understood."},
        ],
        session_id="session:abstained",
        authenticated_author_id=first.absent_author_id,
        received_at=datetime.now(UTC),
    )
    runtime.wait_for_idle()
    assert len(calls) == 1
    inspection = inspect_local_memory(hermes_home=tmp_path)
    assert inspection["captured_source_count"] >= 2
    assert inspection["observation_ledger_entry_count"] == 1
    assert inspection["operation_terminal_counts_by_outcome"] == {"evidence_only": 1}
    assert inspection["graph_revision_delta_count"] == 0
    assert inspection["retrieval_visible_record_count"] == 0
    assert inspection["runtime_context_projection_count"] == 0
    assert not any(
        record.content.get("runtime_context_projection_kind") == "bootstrap_v3_claim_assertion"
        for record in first.service._memory_plane.list_records()
    )

    reopened = build_local_level2_runtime_binding(_context(tmp_path, session_id="session:reopened"))
    assert reopened.completed_turn_runtime is not None
    reopened.completed_turn_runtime.wait_for_idle()
    reopened.completed_turn_runtime.sync_completed_turn(
        user_content="Mars Venus 001 project owner is Ada.",
        assistant_content="I will remember that.",
        messages=[
            {"role": "user", "content": "Mars Venus 001 project owner is Ada."},
            {"role": "assistant", "content": "I will remember that."},
        ],
        session_id="session:reopened",
        authenticated_author_id=reopened.absent_author_id,
        received_at=datetime.now(UTC),
    )
    reopened.completed_turn_runtime.wait_for_idle()
    assert "Mars Venus 001 project owner is Ada." in reopened.completed_turn_runtime.prefetch(
        query="Who owns Mars Venus 001?",
        session_id="session:reopened",
        authenticated_author_id=reopened.absent_author_id,
        now=datetime.now(UTC),
    )
    assert len(calls) == 2


def test_installed_hermes_completed_turn_commits_and_recalls_after_reopen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from memorii.core.semantic_ingestion.openai_responses_project_assertions import (
        OpenAIResponsesApiClient,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls: list[str] = []
    entered = threading.Event()
    release_first = threading.Event()
    retry_entered = threading.Event()
    release_retry = threading.Event()

    def response(client: object, **kwargs: object) -> str | None:
        calls.append(str(kwargs.get("source_segment")))
        if len(calls) == 1:
            entered.set()
            assert release_first.wait(5)
            return None
        if len(calls) == 2:
            retry_entered.set()
            assert release_retry.wait(5)
        return _response(client, **kwargs)

    monkeypatch.setattr(OpenAIResponsesApiClient, "complete", response)
    authorize_local_level2(hermes_home=tmp_path)
    first = build_local_level2_runtime_binding(_context(tmp_path, session_id="session:one"))
    operator_id = first.absent_author_id
    runtime = first.completed_turn_runtime
    assert runtime is not None
    completed_at = datetime.now(UTC)
    runtime.sync_completed_turn(
        user_content="Mars Venus 001 project owner is Ada.",
        assistant_content="I will remember that.",
        messages=[
            {"role": "user", "content": "Mars Venus 001 project owner is Ada."},
            {"role": "assistant", "content": "I will remember that."},
        ],
        session_id="session:one",
        authenticated_author_id=operator_id,
        received_at=completed_at,
    )
    assert entered.wait(5)
    records_while_blocked = first.service._memory_plane.list_records()
    assert any(record.source_kind == "semantic_ingestion_source" for record in records_while_blocked)
    assert all(
        record.content["source_admission"].get("retained_source_authority_evidence")
        for record in records_while_blocked
        if record.source_kind == "semantic_ingestion_source"
    )
    for record in records_while_blocked:
        if record.source_kind != "semantic_ingestion_source":
            continue
        digest = source_admission_source_digest(record)
        assert (
            first.service._provider_ingestion._retained_source_evidence(
                source_id=record.memory_id,
                source_digest=digest,
            )
            is not None
        )
        assert (
            first.service._provider_ingestion._retained_source_evidence(
                source_id=record.memory_id,
                source_digest="0" * 64,
            )
            is None
        )
    assert not any(
        record.content.get("runtime_context_projection_kind") == "bootstrap_v3_claim_assertion"
        for record in records_while_blocked
    )
    release_first.set()
    assert retry_entered.wait(5)
    assert len(calls) == 2
    assert not any(
        record.content.get("runtime_context_projection_kind") == "bootstrap_v3_claim_assertion"
        for record in first.service._memory_plane.list_records()
    )
    release_retry.set()
    runtime.wait_for_idle()
    records = first.service._memory_plane.list_records()
    assert any(record.source_kind == "semantic_ingestion_source" for record in records)
    assert any(record.source_kind == "semantic_ingestion_observation_ledger_entry" for record in records)
    assert any(record.visibility.value == "runtime_context" for record in records)
    source = next(record for record in records if record.source_kind == "semantic_ingestion_source")
    source_digest = source_admission_source_digest(source)
    replay_state = first.service._semantic_atomic_store.semantic_replay_state()
    claims = tuple(item.record for item in replay_state.materialized_records if item.record_kind == "claim_assertion")
    transaction_group_id = next(item.transaction_group_id for item in replay_state.materialized_records)
    projected = runtime_context_records_from_committed_claims(
        source_record=source,
        expected_source_id=source.memory_id,
        expected_source_digest=source_digest,
        transaction_group_id=transaction_group_id,
        claims=claims,
    )
    assert projected == runtime_context_records_from_committed_claims(
        source_record=source,
        expected_source_id=source.memory_id,
        expected_source_digest=source_digest,
        transaction_group_id=transaction_group_id,
        claims=claims,
    )
    assert {record.memory_id for record in projected}.issubset({record.memory_id for record in records})
    with pytest.raises(ValueError, match="source fence is substituted"):
        runtime_context_records_from_committed_claims(
            source_record=source.model_copy(update={"text": "substituted"}),
            expected_source_id=source.memory_id,
            expected_source_digest=source_digest,
            transaction_group_id=transaction_group_id,
            claims=claims,
        )
    runtime.sync_completed_turn(
        user_content="Mars Venus 001 project owner is Ada.",
        assistant_content="I will remember that.",
        messages=[
            {"role": "user", "content": "Mars Venus 001 project owner is Ada."},
            {"role": "assistant", "content": "I will remember that."},
        ],
        session_id="session:one",
        authenticated_author_id=operator_id,
        received_at=completed_at,
    )
    runtime.wait_for_idle()
    assert len(calls) == 2
    assert {
        record.memory_id
        for record in first.service._memory_plane.list_records()
        if record.content.get("runtime_context_projection_kind") == "bootstrap_v3_claim_assertion"
    } == {record.memory_id for record in projected}
    first_turn_messages = [
        {"role": "user", "content": "Mars Venus 001 project owner is Ada."},
        {"role": "assistant", "content": "I will remember that."},
    ]
    second_turn_messages = [
        *first_turn_messages,
        {"role": "user", "content": "Mars Venus 001 project status is active."},
        {"role": "assistant", "content": "I will remember the status."},
    ]
    runtime.sync_completed_turn(
        user_content="Mars Venus 001 project status is active.",
        assistant_content="I will remember the status.",
        messages=second_turn_messages,
        session_id="session:one",
        authenticated_author_id=operator_id,
        received_at=datetime.now(UTC),
    )
    runtime.wait_for_idle()
    records_after_two = first.service._memory_plane.list_records()
    projections = tuple(
        record
        for record in records_after_two
        if record.content.get("runtime_context_projection_kind") == "bootstrap_v3_claim_assertion"
    )
    assert len(projections) == 2
    assert all(record.session_id is None for record in projections)
    assert len({record.task_id for record in projections}) == 1
    assert {record.agent_id for record in projections} == {runtime._authenticated_agent_id}
    assert {record.content["source_id"] for record in projections} <= {
        record.memory_id for record in records_after_two if record.source_kind == "semantic_ingestion_source"
    }
    assert all(record.content.get("source_authority_evidence") for record in projections)
    owner_recall = runtime.prefetch(
        query="Who owns Mars Venus 001?",
        session_id="session:two",
        authenticated_author_id=operator_id,
        now=datetime.now(UTC),
    )
    status_recall = runtime.prefetch(
        query="What is the status of Mars Venus 001?",
        session_id="session:two",
        authenticated_author_id=operator_id,
        now=datetime.now(UTC),
    )
    assert "Mars Venus 001 project owner is Ada." in owner_recall
    assert "Mars Venus 001 project status is active." in status_recall
    assert (
        runtime.prefetch(
            query="Who owns Mars Venus 001?",
            session_id="session:two",
            authenticated_author_id="user:other",
            now=datetime.now(UTC),
        )
        == ""
    )
    before_denials = tuple(record.memory_id for record in first.service._memory_plane.list_records())
    with pytest.raises(ValueError, match="does not end"):
        runtime.sync_completed_turn(
            user_content="Mars Venus 001 project status is active.",
            assistant_content="changed acknowledgement",
            messages=second_turn_messages,
            session_id="session:one",
            authenticated_author_id=operator_id,
            received_at=datetime.now(UTC),
        )
    with pytest.raises(ValueError, match="does not end"):
        runtime.sync_completed_turn(
            user_content="Mars Venus 001 project status is active.",
            assistant_content="I will remember the status.",
            messages=[second_turn_messages[-1], second_turn_messages[-2]],
            session_id="session:one",
            authenticated_author_id=operator_id,
            received_at=datetime.now(UTC),
        )
    assert tuple(record.memory_id for record in first.service._memory_plane.list_records()) == before_denials
    reopened = build_local_level2_runtime_binding(_context(tmp_path, session_id="session:three"))
    reopened_runtime = reopened.completed_turn_runtime
    assert reopened_runtime is not None
    reopened_recall = reopened_runtime.prefetch(
        query="Who owns Mars Venus 001?",
        session_id="session:three",
        authenticated_author_id=operator_id,
        now=datetime.now(UTC),
    )
    assert "Mars Venus 001 project owner is Ada." in reopened_recall
    assert "Mars Venus 001 project status is active." in reopened_runtime.prefetch(
        query="What is the status of Mars Venus 001?",
        session_id="session:three",
        authenticated_author_id=operator_id,
        now=datetime.now(UTC),
    )
    other_agent = build_local_level2_runtime_binding(
        _context(
            tmp_path,
            session_id="session:other-agent",
            agent_identity="agent:other",
        )
    )
    assert other_agent.completed_turn_runtime is not None
    assert (
        other_agent.completed_turn_runtime.prefetch(
            query="Who owns Mars Venus 001?",
            session_id="session:other-agent",
            authenticated_author_id=operator_id,
            now=datetime.now(UTC),
        )
        == ""
    )
    assert memorii_hermes_main(["status", "--hermes-home", str(tmp_path)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["available"] is True
    assert status["authority"] == "local_level2"
    assert status["profile"] == "memorii.project_assertions@1"
    assert memorii_hermes_main(["inspect", "--hermes-home", str(tmp_path)]) == 0
    inspection = json.loads(capsys.readouterr().out)
    assert inspection["captured_source_count"] >= 4
    assert inspection["graph_record_count"] >= 2
    assert inspection["observation_ledger_entry_count"] >= 2
    assert inspection["runtime_context_projection_count"] == 2
    assert inspection["retrieval_visible_record_count"] >= 2
    isolated_home = tmp_path / "isolated"
    authorize_local_level2(hermes_home=isolated_home)
    isolated = build_local_level2_runtime_binding(_context(isolated_home, session_id="session:isolated"))
    assert isolated.completed_turn_runtime is not None
    assert (
        isolated.completed_turn_runtime.prefetch(
            query="Who owns Mars Venus 001?",
            session_id="session:isolated",
            authenticated_author_id=isolated.absent_author_id,
            now=datetime.now(UTC),
        )
        == ""
    )
    bad_home = tmp_path / "bad"
    authorize_local_level2(hermes_home=bad_home)
    sidecar = bad_home / "memorii" / "local-level2.json"
    sidecar.write_text(
        sidecar.read_text().replace(
            '"local_level2_enabled":true',
            '"local_level2_enabled":false',
        )
    )
    with pytest.raises(ValueError, match="invalid"):
        build_local_level2_runtime_binding(_context(bad_home, session_id="session:bad"))
    assert not (bad_home / "memorii" / "memory-plane" / "memory_records.jsonl").exists()
    assert len(calls) == 3
    assert "Mars Venus 001 project owner is Ada." in calls[0]
    assert calls[1] == calls[0]
    assert "Mars Venus 001 project status is active." in calls[2]
    with pytest.raises(ValueError, match="incomplete"):
        runtime.sync_completed_turn(
            user_content="Mars Venus 001 project owner is Ada.",
            assistant_content="I will remember that.",
            messages=[{"role": "user", "content": "Mars Venus 001 project owner is Ada."}],
            session_id="session:one",
            authenticated_author_id=operator_id,
            received_at=datetime.now(UTC),
        )


def test_active_runtime_revocation_during_egress_prevents_semantic_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from memorii.core.semantic_ingestion.openai_responses_project_assertions import (
        OpenAIResponsesApiClient,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    entered = threading.Event()
    release = threading.Event()
    calls = 0

    def response(client: object, **kwargs: object) -> str:
        nonlocal calls
        calls += 1
        entered.set()
        assert release.wait(5)
        return _response(client, **kwargs)

    monkeypatch.setattr(OpenAIResponsesApiClient, "complete", response)
    authorize_local_level2(hermes_home=tmp_path)
    binding = build_local_level2_runtime_binding(_context(tmp_path, session_id="session:revoked"))
    operator_id = binding.absent_author_id
    runtime = binding.completed_turn_runtime
    assert runtime is not None
    runtime.sync_completed_turn(
        user_content="Mars Venus 001 project owner is Ada.",
        assistant_content="I will remember that.",
        messages=[
            {"role": "user", "content": "Mars Venus 001 project owner is Ada."},
            {"role": "assistant", "content": "I will remember that."},
        ],
        session_id="session:revoked",
        authenticated_author_id=operator_id,
        received_at=datetime.now(UTC),
    )
    assert entered.wait(5)
    sidecar = tmp_path / "memorii" / "local-level2.json"
    sidecar.write_text(sidecar.read_text().replace('"local_level2_enabled":true', '"local_level2_enabled":false'))
    release.set()
    with pytest.raises(RuntimeError, match="semantic worker failed"):
        runtime.wait_for_idle()
    records = binding.service._memory_plane.list_records()
    assert calls == 1
    assert not any(
        record.content.get("runtime_context_projection_kind") == "bootstrap_v3_claim_assertion" for record in records
    )
    assert not any(record.source_kind == "semantic_ingestion_observation_ledger_entry" for record in records)
    with pytest.raises(ValueError, match="authority is unavailable"):
        runtime.prefetch(
            query="Who owns Mars Venus 001?",
            session_id="session:after-revocation",
            authenticated_author_id=operator_id,
            now=datetime.now(UTC),
        )


def test_startup_recovers_atomic_admission_before_handoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from memorii.core.semantic_ingestion.openai_responses_project_assertions import (
        OpenAIResponsesApiClient,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = 0

    def response(client: object, **kwargs: object) -> str:
        nonlocal calls
        calls += 1
        return _response(client, **kwargs)

    monkeypatch.setattr(OpenAIResponsesApiClient, "complete", response)
    authorize_local_level2(hermes_home=tmp_path)
    first = build_local_level2_runtime_binding(_context(tmp_path, session_id="session:interrupted"))
    assert first.completed_turn_runtime is not None
    first.completed_turn_runtime.wait_for_idle()
    operator_id = first.absent_author_id
    agent_id = first.completed_turn_runtime._authenticated_agent_id
    completed_at = datetime.now(UTC)
    messages = (
        HermesCompletedTurnMessage(role="user", content="Mars Venus 001 project owner is Ada."),
        HermesCompletedTurnMessage(role="assistant", content="I will remember that."),
    )
    host_ingress = first.issue_ingress(
        SimpleNamespace(
            session_id="session:interrupted",
            user_id=operator_id,
            agent_id=agent_id,
            received_at=completed_at,
        )
    )
    ingress = first.service._preflight_ingress(host_ingress)
    assert ingress is not None
    writer_binding = first.service._semantic_writer_admission.commit_binding(
        first.service._semantic_writer_admission.current()
    )
    admitted = HermesCompletedTurnAdmissionService(
        atomic_store=first.service._semantic_atomic_store,
        writer_binding=writer_binding,
    ).admit(
        HermesCompletedTurnAdmissionRequest(
            installation_id=first.completed_turn_runtime._installation_id,
            session_id="session:interrupted",
            authenticated_author_id=operator_id,
            authenticated_agent_id=agent_id,
            project_task_namespace=first.completed_turn_runtime._project_task_id,
            turn_ordinal=1,
            canonical_transcript_digest=_canonical_messages_digest(
                tuple(message.model_dump(mode="json") for message in messages)
            ),
            completed_messages=messages,
            completed_at=completed_at,
            ingress=ingress,
        )
    )
    assert (
        first.service._semantic_atomic_store.load_bootstrap_writer_handoff_marker_v3(
            operation_fence_binding=admitted.normalization_inputs.operation_fence
        )
        is None
    )
    before = first.service._memory_plane.list_records()
    assert not any(
        record.content.get("runtime_context_projection_kind") == "bootstrap_v3_claim_assertion" for record in before
    )
    assert not any(record.source_kind == "semantic_ingestion_observation_ledger_entry" for record in before)

    reopened = build_local_level2_runtime_binding(_context(tmp_path, session_id="session:recovered"))
    assert reopened.completed_turn_runtime is not None
    reopened.completed_turn_runtime.wait_for_idle()
    after = reopened.service._memory_plane.list_records()
    assert calls == 1
    assert (
        sum(record.content.get("runtime_context_projection_kind") == "bootstrap_v3_claim_assertion" for record in after)
        == 1
    )
    ledger_entries = tuple(
        record for record in after if record.source_kind == "semantic_ingestion_observation_ledger_entry"
    )
    assert len(ledger_entries) == 2
    assert "Mars Venus 001 project owner is Ada." in reopened.completed_turn_runtime.prefetch(
        query="Who owns Mars Venus 001?",
        session_id="session:recovered",
        authenticated_author_id=reopened.absent_author_id,
        now=datetime.now(UTC),
    )
    before_replay = tuple(record.memory_id for record in after)
    reopened.completed_turn_runtime.sync_completed_turn(
        user_content=messages[0].content,
        assistant_content=messages[1].content,
        messages=[message.model_dump(mode="json") for message in messages],
        session_id="session:interrupted",
        authenticated_author_id=reopened.absent_author_id,
        received_at=completed_at,
    )
    reopened.completed_turn_runtime.wait_for_idle()
    assert calls == 1
    assert tuple(record.memory_id for record in reopened.service._memory_plane.list_records()) == before_replay
