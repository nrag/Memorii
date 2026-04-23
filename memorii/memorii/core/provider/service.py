"""Provider-oriented memory service for Hermes-style hooks."""

from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.provider.blocking_policy import evaluate_operation_policy
from memorii.core.provider.classifier import build_event_id, make_event
from memorii.core.provider.models import (
    ProviderEvent,
    ProviderOperation,
    ProviderPrefetchTrace,
    ProviderRerankTraceItem,
    ProviderStoredRecord,
    ProviderSyncResult,
    ProviderWriteDecision,
)
from memorii.core.provider.prefetch import classify_prefetch_query, format_prefetch_context
from memorii.core.provider.reranking import ProviderReranker
from memorii.core.retrieval.planner import RetrievalPlanner
from memorii.domain.enums import MemoryDomain
from memorii.domain.retrieval import RetrievalIntent, RetrievalScope


class ProviderMemoryService:
    """Deterministic provider ingestion + retrieval path without runtime-step dependencies."""

    def __init__(self) -> None:
        self._planner = RetrievalPlanner()
        self._reranker = ProviderReranker()
        self._last_prefetch_trace: ProviderPrefetchTrace | None = None
        self._transcript_records: list[ProviderStoredRecord] = []
        self._candidate_records: list[ProviderStoredRecord] = []
        self._committed_records: list[ProviderStoredRecord] = []
        self._sequence = 0

    def sync_event(self, *, operation: ProviderOperation, content: str, role: str | None = None,
                   target: str | None = None, action: str | None = None, session_id: str | None = None,
                   task_id: str | None = None, user_id: str | None = None) -> ProviderSyncResult:
        self._sequence += 1
        event = make_event(
            event_id=build_event_id(operation.value, session_id=session_id, task_id=task_id, sequence=self._sequence),
            operation=operation,
            content=content,
            role=role,
            target=target,
            action=action,
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            timestamp=datetime.now(UTC),
        )
        return self._ingest_event(event)

    def _ingest_event(self, event: ProviderEvent) -> ProviderSyncResult:
        policy = evaluate_operation_policy(operation=event.operation)
        transcript_ids: list[str] = []
        if MemoryDomain.TRANSCRIPT in policy.allowed_raw_append_domains:
            transcript_ids.append(self._store_transcript(event))

        candidate_ids: list[str] = []
        for domain in policy.allowed_candidate_domains:
            candidate_ids.append(self._store_candidate(event=event, domain=domain))

        return ProviderSyncResult(
            transcript_ids=transcript_ids,
            candidate_ids=candidate_ids,
            blocked_domains=policy.blocked_commit_domains,
            blocked_reasons=policy.blocked_reasons,
            allowed_candidate_domains=policy.allowed_candidate_domains,
            raw_append_domains=policy.allowed_raw_append_domains,
            blocked_commit_domains=policy.blocked_commit_domains,
        )

    def apply_memory_write(
        self,
        *,
        operation: ProviderOperation,
        content: str,
        session_id: str | None,
        task_id: str | None,
        user_id: str | None,
        action: str,
        target: str,
    ) -> ProviderWriteDecision:
        self._sequence += 1
        event = make_event(
            event_id=build_event_id("write", session_id=session_id, task_id=task_id, sequence=self._sequence),
            operation=operation,
            content=content,
            action=action,
            target=target,
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
        )
        sync_result = self._ingest_event(event)
        return ProviderWriteDecision(
            blocked_domains=sync_result.blocked_domains,
            allowed_candidate_domains=sync_result.allowed_candidate_domains,
            committed_domains=[],
            blocked_reasons=sync_result.blocked_reasons,
            candidate_ids=sync_result.candidate_ids,
            raw_append_domains=sync_result.raw_append_domains,
            blocked_commit_domains=sync_result.blocked_commit_domains,
        )

    def prefetch(
        self,
        query: str,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
        top_k: int = 6,
    ) -> str:
        query_class = classify_prefetch_query(query)
        intent = _intent_for_query_class(query_class)
        plan = self._planner.build_plan(intent=intent, scope=RetrievalScope(task_id=task_id), include_raw_transcript=True)
        planned_domains = {query_spec.domain for query_spec in plan.queries}
        committed_pool = [
            item
            for item in self._committed_records
            if item.domain in planned_domains and _in_scope(item=item, session_id=session_id, task_id=task_id, user_id=user_id)
        ]
        transcript_pool = [
            item
            for item in self._transcript_records
            if item.domain in planned_domains and _in_scope(item=item, session_id=session_id, task_id=task_id, user_id=user_id)
        ]
        pool = {item.memory_id: item for item in [*committed_pool, *transcript_pool]}
        reranked = self._reranker.rerank(
            query=query,
            query_class=query_class,
            candidates=list(pool.values()),
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
        )
        self._last_prefetch_trace = ProviderPrefetchTrace(
            query=query,
            query_class=query_class,
            candidate_count=len(reranked),
            ranked_items=[
                ProviderRerankTraceItem(
                    memory_id=item.record.memory_id,
                    domain=item.record.domain,
                    final_score=item.final_score,
                    domain_prior_score=item.signals.domain_prior_score,
                    lexical_score=item.signals.lexical_score,
                    recency_score=item.signals.recency_score,
                    scope_score=item.signals.scope_score,
                    rank=rank,
                )
                for rank, item in enumerate(reranked, start=1)
            ],
        )
        ranked_records = [item.record for item in reranked]
        return format_prefetch_context(ranked_records[:top_k])

    def seed_committed_record(self, record: ProviderStoredRecord) -> None:
        self._committed_records.append(record)

    def candidate_records(self) -> list[ProviderStoredRecord]:
        return list(self._candidate_records)

    def transcript_records(self) -> list[ProviderStoredRecord]:
        return list(self._transcript_records)

    def last_prefetch_trace(self) -> ProviderPrefetchTrace | None:
        return self._last_prefetch_trace

    def _store_transcript(self, event: ProviderEvent) -> str:
        memory_id = f"tx:{event.event_id}"
        self._transcript_records.append(
            ProviderStoredRecord(
                memory_id=memory_id,
                domain=MemoryDomain.TRANSCRIPT,
                text=event.content or "",
                status="committed",
                session_id=event.session_id,
                task_id=event.task_id,
                user_id=event.user_id,
                timestamp=event.timestamp or datetime.now(UTC),
            )
        )
        return memory_id

    def _store_candidate(self, *, event: ProviderEvent, domain: MemoryDomain) -> str:
        memory_id = f"cand:{domain.value}:{event.event_id}"
        self._candidate_records.append(
            ProviderStoredRecord(
                memory_id=memory_id,
                domain=domain,
                text=event.content or "",
                status="candidate",
                session_id=event.session_id,
                task_id=event.task_id,
                user_id=event.user_id,
                timestamp=event.timestamp or datetime.now(UTC),
            )
        )
        return memory_id


def _in_scope(
    *, item: ProviderStoredRecord, session_id: str | None, task_id: str | None, user_id: str | None
) -> bool:
    if session_id is not None and item.session_id not in {None, session_id}:
        return False
    if task_id is not None and item.task_id not in {None, task_id}:
        return False
    if user_id is not None and item.user_id not in {None, user_id}:
        return False
    return True


def _intent_for_query_class(query_class: object) -> RetrievalIntent:
    mapping = {
        "preference_profile": RetrievalIntent.ANSWER_WITH_USER_CONTEXT,
        "fact_config": RetrievalIntent.DEBUG_OR_INVESTIGATE,
        "event_history": RetrievalIntent.DEBUG_OR_INVESTIGATE,
        "general_continuity": RetrievalIntent.DEBUG_OR_INVESTIGATE,
    }
    return mapping.get(getattr(query_class, "value", "general_continuity"), RetrievalIntent.RESUME_TASK)
