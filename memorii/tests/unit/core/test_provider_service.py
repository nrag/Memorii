from memorii.core.provider.models import ProviderStoredRecord
from memorii.core.provider.service import ProviderMemoryService
from memorii.integrations.hermes_provider import HermesMemoryProvider
from memorii.domain.enums import MemoryDomain
from datetime import UTC, datetime, timedelta


def test_prefetch_excludes_candidate_only_records_and_formats_context() -> None:
    service = ProviderMemoryService()
    provider = HermesMemoryProvider(service)
    service.seed_committed_record(
        ProviderStoredRecord(
            memory_id="sem:1",
            domain=MemoryDomain.SEMANTIC,
            text="API timeout default is 30 seconds",
            status="committed",
            task_id="task:1",
        )
    )
    provider.on_memory_write(
        action="upsert",
        target="memory",
        content="The service maybe uses legacy timeout",
        task_id="task:1",
    )

    context = provider.prefetch("what is the timeout default", task_id="task:1")

    assert "Memorii context:" in context
    assert "API timeout default is 30 seconds" in context
    assert "cand:semantic" not in context


def test_provider_hook_methods_cover_core_operations() -> None:
    provider = HermesMemoryProvider(ProviderMemoryService())
    turn_result = provider.sync_turn("User asked to summarize", "Assistant summarized", task_id="task:2")
    write_result = provider.on_memory_write("upsert", "user", "Maybe user likes terse responses", task_id="task:2")
    session_result = provider.on_session_end(["incident fixed after deploy rollback"], task_id="task:2")
    precompress_result = provider.on_pre_compress([{"role": "assistant", "content": "resolved bug"}], task_id="task:2")
    delegation_result = provider.on_delegation("verify migration", "migration completed", task_id="task:2")
    prefetch_text = provider.prefetch("what happened last session", task_id="task:2")

    assert len(turn_result.transcript_ids) == 2
    assert write_result.blocked_domains
    assert session_result.transcript_ids
    assert precompress_result.transcript_ids
    assert delegation_result.transcript_ids
    assert isinstance(prefetch_text, str)


def test_prefetch_includes_transcript_continuity_records() -> None:
    service = ProviderMemoryService()
    provider = HermesMemoryProvider(service)
    provider.sync_turn(
        "I moved the deploy window to Friday.",
        "Understood, deploy window moved to Friday.",
        task_id="task:history",
    )

    context = provider.prefetch("what deploy window was set", task_id="task:history")
    assert "deploy window" in context.lower()


def test_memory_write_stages_semantic_candidate_and_blocks_commit() -> None:
    provider = HermesMemoryProvider(ProviderMemoryService())
    result = provider.on_memory_write("upsert", "memory", "timeout is 30s", task_id="task:w")
    assert any(candidate_id.startswith("cand:semantic:") for candidate_id in result.candidate_ids)
    assert result.allowed_candidate_domains == [MemoryDomain.SEMANTIC]
    assert MemoryDomain.SEMANTIC in result.blocked_commit_domains
    assert MemoryDomain.USER in result.blocked_commit_domains
    assert result.committed_domains == []


def test_memory_write_stages_user_candidate_and_blocks_commit() -> None:
    provider = HermesMemoryProvider(ProviderMemoryService())
    result = provider.on_memory_write("upsert", "user", "prefers concise responses", task_id="task:w")
    assert any(candidate_id.startswith("cand:user:") for candidate_id in result.candidate_ids)
    assert result.allowed_candidate_domains == [MemoryDomain.USER]
    assert MemoryDomain.USER in result.blocked_commit_domains
    assert MemoryDomain.SEMANTIC in result.blocked_commit_domains
    assert result.committed_domains == []


def test_session_end_stages_episodic_candidate() -> None:
    provider = HermesMemoryProvider(ProviderMemoryService())
    result = provider.on_session_end(["resolved incident"], task_id="task:end")
    assert result.allowed_candidate_domains == [MemoryDomain.EPISODIC]
    assert any(candidate_id.startswith("cand:episodic:") for candidate_id in result.candidate_ids)


def test_sync_turn_raw_transcript_only_no_direct_commits() -> None:
    provider = HermesMemoryProvider(ProviderMemoryService())
    result = provider.sync_turn("user says x", "assistant replies y", task_id="task:sync")
    assert len(result.transcript_ids) == 2
    assert result.candidate_ids == []
    assert result.blocked_commit_domains


def test_prefetch_general_continuity_prefers_recent_transcript_over_old_semantic() -> None:
    service = ProviderMemoryService()
    now = datetime(2026, 1, 15, tzinfo=UTC)
    service.seed_committed_record(
        ProviderStoredRecord(
            memory_id="sem:old",
            domain=MemoryDomain.SEMANTIC,
            text="Deployment checklist includes QA signoff.",
            status="committed",
            task_id="task:rank",
            timestamp=now - timedelta(days=30),
        )
    )
    service.seed_committed_record(
        ProviderStoredRecord(
            memory_id="tx:new",
            domain=MemoryDomain.TRANSCRIPT,
            text="Let's continue with the deployment checklist and QA signoff now.",
            status="committed",
            task_id="task:rank",
            timestamp=now,
        )
    )

    service.prefetch("continue with deployment checklist", task_id="task:rank")
    trace = service.last_prefetch_trace()
    assert trace is not None
    assert trace.query_class.value == "general_continuity"
    assert trace.ranked_items[0].memory_id == "tx:new"
    assert trace.candidate_count == 2
    assert trace.ranked_items[0].recency_score >= trace.ranked_items[1].recency_score


def test_prefetch_fact_config_prefers_semantic_when_query_is_fact_like() -> None:
    service = ProviderMemoryService()
    now = datetime(2026, 1, 15, tzinfo=UTC)
    service.seed_committed_record(
        ProviderStoredRecord(
            memory_id="sem:config",
            domain=MemoryDomain.SEMANTIC,
            text="Timeout default is 30 seconds.",
            status="committed",
            task_id="task:fact",
            timestamp=now - timedelta(days=10),
        )
    )
    service.seed_committed_record(
        ProviderStoredRecord(
            memory_id="tx:noise",
            domain=MemoryDomain.TRANSCRIPT,
            text="We talked about many defaults yesterday.",
            status="committed",
            task_id="task:fact",
            timestamp=now,
        )
    )

    service.prefetch("what is the timeout default config", task_id="task:fact")
    trace = service.last_prefetch_trace()
    assert trace is not None
    assert trace.query_class.value == "fact_config"
    assert trace.ranked_items[0].memory_id == "sem:config"


def test_prefetch_fact_config_bm25_prefers_concise_fact_over_noisy_match() -> None:
    service = ProviderMemoryService()
    now = datetime(2026, 1, 15, tzinfo=UTC)
    service.seed_committed_record(
        ProviderStoredRecord(
            memory_id="sem:concise",
            domain=MemoryDomain.SEMANTIC,
            text="Timeout default is 30 seconds.",
            status="committed",
            task_id="task:fact:bm25",
            timestamp=now - timedelta(days=5),
        )
    )
    service.seed_committed_record(
        ProviderStoredRecord(
            memory_id="sem:noisy",
            domain=MemoryDomain.SEMANTIC,
            text=(
                "Meeting transcript recap with many unrelated details and only one mention "
                "that timeout might have a default value."
            ),
            status="committed",
            task_id="task:fact:bm25",
            timestamp=now,
        )
    )

    service.prefetch("what is the timeout default config", task_id="task:fact:bm25")
    trace = service.last_prefetch_trace()
    assert trace is not None
    assert trace.ranked_items[0].memory_id == "sem:concise"


def test_prefetch_event_history_prefers_episodic_over_transcript() -> None:
    service = ProviderMemoryService()
    now = datetime(2026, 1, 15, tzinfo=UTC)
    service.seed_committed_record(
        ProviderStoredRecord(
            memory_id="epi:incident",
            domain=MemoryDomain.EPISODIC,
            text="Outage history timeline: rollback fixed API outage.",
            status="committed",
            task_id="task:event",
            timestamp=now - timedelta(hours=3),
        )
    )
    service.seed_committed_record(
        ProviderStoredRecord(
            memory_id="tx:incident",
            domain=MemoryDomain.TRANSCRIPT,
            text="I think we had an outage last week.",
            status="committed",
            task_id="task:event",
            timestamp=now - timedelta(hours=1),
        )
    )

    service.prefetch("what happened in the last outage history", task_id="task:event")
    trace = service.last_prefetch_trace()
    assert trace is not None
    assert trace.query_class.value == "event_history"
    assert trace.ranked_items[0].memory_id == "epi:incident"


def test_prefetch_preference_profile_prefers_user_memory() -> None:
    service = ProviderMemoryService()
    now = datetime(2026, 1, 15, tzinfo=UTC)
    service.seed_committed_record(
        ProviderStoredRecord(
            memory_id="user:style",
            domain=MemoryDomain.USER,
            text="User prefers concise bullet responses.",
            status="committed",
            task_id="task:user",
            user_id="user:1",
            timestamp=now - timedelta(days=5),
        )
    )
    service.seed_committed_record(
        ProviderStoredRecord(
            memory_id="tx:style",
            domain=MemoryDomain.TRANSCRIPT,
            text="Can you keep responses short?",
            status="committed",
            task_id="task:user",
            user_id="user:1",
            timestamp=now,
        )
    )

    service.prefetch("what is my preference profile", task_id="task:user", user_id="user:1")
    trace = service.last_prefetch_trace()
    assert trace is not None
    assert trace.query_class.value == "preference_profile"
    assert trace.ranked_items[0].memory_id == "user:style"


def test_prefetch_trace_exposes_score_breakdown_and_deterministic_ranks() -> None:
    service = ProviderMemoryService()
    baseline_time = datetime(2026, 1, 10, tzinfo=UTC)
    for index in range(3):
        service.seed_committed_record(
            ProviderStoredRecord(
                memory_id=f"sem:{index}",
                domain=MemoryDomain.SEMANTIC,
                text=f"Timeout default detail {index}",
                status="committed",
                task_id="task:trace",
                timestamp=baseline_time + timedelta(minutes=index),
            )
        )

    service.prefetch("timeout default config", task_id="task:trace")
    trace = service.last_prefetch_trace()
    assert trace is not None
    assert trace.lexical_method == "bm25"
    assert trace.candidate_count == 3
    assert [item.rank for item in trace.ranked_items] == [1, 2, 3]
    top = trace.ranked_items[0]
    assert isinstance(top.final_score, float)
    assert isinstance(top.domain_prior_score, float)
    assert isinstance(top.lexical_score, float)
    assert isinstance(top.recency_score, float)
    assert isinstance(top.scope_score, float)
