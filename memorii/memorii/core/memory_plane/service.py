"""Canonical shared memory-plane behavior used by provider and runtime compatibility layers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from memorii.core.provider.blocking_policy import evaluate_operation_policy
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
from memorii.domain.enums import CommitStatus, MemoryDomain
from memorii.domain.memory_object import MemoryObject
from memorii.domain.retrieval import DomainRetrievalQuery, RetrievalIntent, RetrievalPlan, RetrievalScope
from memorii.domain.routing import InboundEvent, RoutingDecision


@dataclass(frozen=True)
class RuntimeRetrievalTrace:
    retrieved_items: list[MemoryObject]
    retrieved_ids_by_domain_raw: dict[str, list[str]]
    retrieved_ids_by_domain_deduped: dict[str, list[str]]
    retrieved_ids_deduped: list[str]


class MemoryPlaneService:
    """Canonical behavior engine for ingestion, staging, and retrieval/reranking."""

    def __init__(self) -> None:
        self._planner = RetrievalPlanner()
        self._reranker = ProviderReranker()
        self._runtime_by_domain: dict[MemoryDomain, list[MemoryObject]] = {domain: [] for domain in MemoryDomain}

        self._last_prefetch_trace: ProviderPrefetchTrace | None = None
        self._transcript_records: list[ProviderStoredRecord] = []
        self._candidate_records: list[ProviderStoredRecord] = []
        self._committed_records: list[ProviderStoredRecord] = []

    # Runtime-facing canonical methods
    def seed_runtime_memory_object(self, memory_object: MemoryObject) -> None:
        self._runtime_by_domain[memory_object.memory_type].append(memory_object)

    def query_runtime_memory(self, query: DomainRetrievalQuery) -> list[MemoryObject]:
        items = self._runtime_by_domain[query.domain]
        return [item for item in items if self._matches_scope(item, query) and self._matches_semantics(item, query)]

    def ingest_runtime_observation(self, *, router: object, inbound: InboundEvent) -> RoutingDecision:
        decision = router.route_event(inbound)
        for routed in decision.routed_objects:
            self.seed_runtime_memory_object(routed.memory_object)
        return decision

    def retrieve_runtime_context(self, *, plan: RetrievalPlan) -> RuntimeRetrievalTrace:
        results: list[MemoryObject] = []
        raw_by_domain: dict[str, list[str]] = {}
        deduped_by_domain: dict[str, list[str]] = {}
        seen_ids: set[str] = set()
        for query in plan.queries:
            raw_ids: list[str] = []
            deduped_ids: list[str] = []
            for item in self.query_runtime_memory(query):
                raw_ids.append(item.memory_id)
                if item.memory_id in seen_ids:
                    continue
                seen_ids.add(item.memory_id)
                results.append(item)
                deduped_ids.append(item.memory_id)
            raw_by_domain.setdefault(query.domain.value, []).extend(raw_ids)
            deduped_by_domain.setdefault(query.domain.value, []).extend(deduped_ids)
        return RuntimeRetrievalTrace(
            retrieved_items=results,
            retrieved_ids_by_domain_raw=raw_by_domain,
            retrieved_ids_by_domain_deduped=deduped_by_domain,
            retrieved_ids_deduped=[item.memory_id for item in results],
        )

    # Provider-facing canonical methods
    def ingest_provider_event(self, event: ProviderEvent) -> ProviderSyncResult:
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

    def apply_provider_memory_write(
        self,
        *,
        event: ProviderEvent,
    ) -> ProviderWriteDecision:
        sync_result = self.ingest_provider_event(event)
        return ProviderWriteDecision(
            blocked_domains=sync_result.blocked_domains,
            allowed_candidate_domains=sync_result.allowed_candidate_domains,
            committed_domains=[],
            blocked_reasons=sync_result.blocked_reasons,
            candidate_ids=sync_result.candidate_ids,
            raw_append_domains=sync_result.raw_append_domains,
            blocked_commit_domains=sync_result.blocked_commit_domains,
        )

    def prefetch_provider_context(
        self,
        query: str,
        *,
        session_id: str | None,
        task_id: str | None,
        user_id: str | None,
        top_k: int,
    ) -> str:
        query_class = classify_prefetch_query(query)
        intent = _intent_for_query_class(query_class)
        plan = self._planner.build_plan(intent=intent, scope=RetrievalScope(task_id=task_id), include_raw_transcript=True)
        planned_domains = {query_spec.domain for query_spec in plan.queries}
        committed_pool = [
            item
            for item in self._committed_records
            if item.domain in planned_domains and _provider_in_scope(item=item, session_id=session_id, task_id=task_id, user_id=user_id)
        ]
        transcript_pool = [
            item
            for item in self._transcript_records
            if item.domain in planned_domains and _provider_in_scope(item=item, session_id=session_id, task_id=task_id, user_id=user_id)
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
            lexical_method="bm25",
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

    def seed_provider_committed_record(self, record: ProviderStoredRecord) -> None:
        self._committed_records.append(record)

    def provider_candidate_records(self) -> list[ProviderStoredRecord]:
        return list(self._candidate_records)

    def provider_transcript_records(self) -> list[ProviderStoredRecord]:
        return list(self._transcript_records)

    def last_provider_prefetch_trace(self) -> ProviderPrefetchTrace | None:
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

    def _matches_scope(self, item: MemoryObject, query: DomainRetrievalQuery) -> bool:
        ns = item.namespace or {}
        if query.scope.task_id is not None and ns.get("task_id") != query.scope.task_id:
            return False
        if query.scope.execution_node_id is not None and ns.get("execution_node_id") != query.scope.execution_node_id:
            return False
        if query.scope.solver_run_id is not None and ns.get("solver_run_id") != query.scope.solver_run_id:
            return False
        if query.scope.agent_id is not None and ns.get("agent_id") != query.scope.agent_id:
            return False
        return True

    def _matches_semantics(self, item: MemoryObject, query: DomainRetrievalQuery) -> bool:
        if not query.include_candidates and item.status == CommitStatus.CANDIDATE:
            return False
        freshness = query.freshness
        if freshness is None or freshness.required_validity is None:
            return True

        required = freshness.required_validity.value
        item_validity = item.validity_status.value if item.validity_status is not None else "active"
        if item_validity != required:
            return False

        valid_at = freshness.valid_at
        if valid_at is not None:
            if item.valid_from is not None and item.valid_from > valid_at:
                return False
            if item.valid_to is not None and item.valid_to < valid_at:
                return False
        return True


def _provider_in_scope(
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
