from memorii.core.provider.models import ProviderStoredRecord
from memorii.core.provider.service import ProviderMemoryService
from memorii.integrations.hermes_provider import HermesMemoryProvider
from memorii.domain.enums import MemoryDomain


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
