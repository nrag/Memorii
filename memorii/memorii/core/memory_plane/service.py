"""Canonical shared memory-plane behavior used by provider and runtime services."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from memorii.core.memory_plane.models import (
    CanonicalMemoryRecord,
    from_memory_object,
    from_provider_stored_record,
    to_memory_object,
    to_provider_stored_record,
)
from memorii.core.memory_plane.store import (
    SEMANTIC_CHECKPOINT_SECRET_PURPOSE,
    CheckpointSignatureAuthority,
    GovernedWritePolicy,
    InMemoryMemoryPlaneStore,
    MemoryPlanePrecondition,
    MemoryPlaneStore,
    MemoryPlaneWriteAuthorization,
)
from memorii.core.memory_plane.unit_of_work import MemoryPlaneUnitOfWork
from memorii.core.provider.blocking_policy import evaluate_operation_policy
from memorii.core.provider.models import (
    ProviderEvent,
    ProviderPrefetchTrace,
    ProviderRerankTraceItem,
    ProviderStoredRecord,
    ProviderSyncResult,
    ProviderWriteDecision,
)
from memorii.core.provider.prefetch import classify_prefetch_query, format_prefetch_context
from memorii.core.provider.reranking import ProviderReranker
from memorii.core.retrieval.planner import RetrievalPlanner
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility
from memorii.domain.memory_object import MemoryObject
from memorii.domain.retrieval import (
    DomainRetrievalQuery,
    FreshnessPolicy,
    RetrievalIntent,
    RetrievalPlan,
    RetrievalScope,
)
from memorii.domain.routing import InboundEvent, RoutingDecision


@dataclass(frozen=True)
class RuntimeRetrievalTrace:
    retrieved_items: list[MemoryObject]
    retrieved_ids_by_domain_raw: dict[str, list[str]]
    retrieved_ids_by_domain_deduped: dict[str, list[str]]
    retrieved_ids_deduped: list[str]


class RuntimeEventRouter(Protocol):
    def route_event(self, event: InboundEvent) -> RoutingDecision: ...


class MemoryPlaneService:
    """Canonical behavior engine for ingestion, staging, and retrieval/reranking."""

    def __init__(self, *, record_store: MemoryPlaneStore | None = None) -> None:
        self._planner = RetrievalPlanner()
        self._reranker = ProviderReranker()
        self._records = record_store if record_store is not None else InMemoryMemoryPlaneStore()
        self._active_unit_of_work: ContextVar[MemoryPlaneUnitOfWork | None] = ContextVar(
            f"memory_plane_unit_of_work_{id(self)}",
            default=None,
        )
        self._last_prefetch_trace: ProviderPrefetchTrace | None = None

    @contextmanager
    def unit_of_work(self) -> Iterator[MemoryPlaneUnitOfWork]:
        """Provide an isolated view whose caller explicitly commits once."""

        if self._active_unit_of_work.get() is not None:
            raise RuntimeError("nested memory-plane units of work are not supported")
        unit_of_work = MemoryPlaneUnitOfWork(self._records)
        token = self._active_unit_of_work.set(unit_of_work)
        try:
            yield unit_of_work
        finally:
            self._active_unit_of_work.reset(token)

    def _record_store(self) -> MemoryPlaneStore:
        return self._active_unit_of_work.get() or self._records

    def install_governed_write_policy(self, policy: GovernedWritePolicy) -> None:
        installer = getattr(self._records, "install_governed_write_policy", None)
        if installer is None:
            raise RuntimeError("memory-plane backend does not support governed-write policy")
        installer(policy)

    @property
    def is_durable_store(self) -> bool:
        durable = getattr(self._records, "durable", None)
        if not isinstance(durable, bool):
            raise RuntimeError("memory-plane backend does not declare durability")
        return durable

    def load_or_create_protected_secret(self, *, purpose: str, length: int = 32) -> bytes:
        if purpose == SEMANTIC_CHECKPOINT_SECRET_PURPOSE:
            raise PermissionError("checkpoint signing material is backend-private")
        loader = getattr(self._records, "load_or_create_protected_secret", None)
        if loader is None:
            raise RuntimeError("memory-plane backend has no protected-secret owner")
        secret = loader(purpose=purpose, length=length)
        if not isinstance(secret, bytes) or len(secret) != length:
            raise RuntimeError("memory-plane protected-secret owner returned invalid material")
        return secret

    def _claim_semantic_checkpoint_signature_authority(
        self,
        *,
        owner: object,
    ) -> CheckpointSignatureAuthority:
        claimer = getattr(
            self._records,
            "_claim_semantic_checkpoint_signature_authority",
            None,
        )
        if claimer is None:
            raise RuntimeError("memory-plane backend has no checkpoint signature owner")
        authority = claimer(owner=owner)
        if not isinstance(authority, CheckpointSignatureAuthority):
            raise RuntimeError("memory-plane backend returned invalid checkpoint authority")
        return authority

    # Runtime-facing canonical methods
    def seed_runtime_memory_object(self, memory_object: MemoryObject) -> None:
        self._record_store().stage_record(from_memory_object(memory_object))

    def query_runtime_memory(self, query: DomainRetrievalQuery) -> list[MemoryObject]:
        records = self._record_store().list_records(domains=[query.domain])
        return [
            to_memory_object(item)
            for item in records
            if item.visibility == MemoryRecordVisibility.RUNTIME_CONTEXT
            and self._matches_scope(item, query.scope)
            and self._matches_semantics(item, include_candidates=query.include_candidates, freshness=query.freshness)
        ]

    def list_records(
        self,
        *,
        status: CommitStatus | None = None,
        domains: list[MemoryDomain] | None = None,
        source_kind: str | None = None,
    ) -> list[CanonicalMemoryRecord]:
        return self._record_store().list_records(
            status=status,
            domains=domains,
            source_kind=source_kind,
        )

    def get_record(self, memory_id: str) -> CanonicalMemoryRecord | None:
        return self._record_store().get_record(memory_id)

    def read_snapshot(self) -> tuple[int, tuple[CanonicalMemoryRecord, ...]]:
        """Return one detached canonical snapshot for a read-only consumer."""

        return self._record_store().read_snapshot()

    def stage_record(
        self,
        record: CanonicalMemoryRecord,
        *,
        authorization: MemoryPlaneWriteAuthorization | None = None,
    ) -> None:
        self._record_store().stage_record(record, authorization=authorization)

    def write_records(
        self, records: tuple[CanonicalMemoryRecord, ...], *, authorization: MemoryPlaneWriteAuthorization | None = None
    ) -> int:
        return self._record_store().write_records(records, authorization=authorization)

    def conditionally_write_records(
        self,
        records: tuple[CanonicalMemoryRecord, ...],
        *,
        preconditions: tuple[MemoryPlanePrecondition, ...],
        authorization: MemoryPlaneWriteAuthorization | None = None,
        transaction_precondition: Callable[[], None] | None = None,
    ) -> int:
        if self._active_unit_of_work.get() is not None:
            raise RuntimeError("conditional control writes cannot be nested in a memory-plane unit of work")
        return self._records.apply_batch(
            records,
            expected_revision=None,
            preconditions=preconditions,
            authorization=authorization,
            transaction_precondition=transaction_precondition,
        )

    def upsert_record(
        self,
        record: CanonicalMemoryRecord,
        *,
        authorization: MemoryPlaneWriteAuthorization | None = None,
    ) -> None:
        self._record_store().upsert_record(record, authorization=authorization)

    def update_candidate_lifecycle(
        self,
        *,
        candidate_id: str,
        promotion_state: str,
        duplicate_of_memory_id: str | None,
        rejected_reason: str | None,
        conflict_with_memory_ids: list[str],
        supersedes_memory_ids: list[str],
    ) -> None:
        candidate = self._record_store().get_record(candidate_id)
        if candidate is None:
            return
        self._record_store().upsert_record(
            candidate.model_copy(
                update={
                    "promotion_state": promotion_state,
                    "duplicate_of_memory_id": duplicate_of_memory_id,
                    "rejected_reason": rejected_reason,
                    "conflict_with_memory_ids": list(conflict_with_memory_ids),
                    "supersedes_memory_ids": list(supersedes_memory_ids),
                }
            )
        )

    def commit_candidate(
        self,
        *,
        candidate_id: str,
        target_domain: MemoryDomain,
        source_candidate_id: str,
        supersedes_memory_ids: list[str],
    ) -> str:
        candidate = self.get_record(candidate_id)
        if candidate is None:
            raise ValueError(f"candidate not found: {candidate_id}")

        existing = [
            item
            for item in self._record_store().list_records(status=CommitStatus.COMMITTED)
            if item.visibility == MemoryRecordVisibility.RUNTIME_CONTEXT
            and item.source_candidate_id == source_candidate_id
            and item.status == CommitStatus.COMMITTED
        ]
        if existing:
            return existing[0].memory_id

        committed_memory_id = f"mem:{target_domain.value}:{candidate.memory_id}"
        committed = candidate.model_copy(
            update={
                "memory_id": committed_memory_id,
                "domain": target_domain,
                "status": CommitStatus.COMMITTED,
                "source_candidate_id": source_candidate_id,
                "promotion_state": "committed",
                "supersedes_memory_ids": list(supersedes_memory_ids),
                "timestamp": datetime.now(UTC),
            }
        )
        self._record_store().stage_record(committed)
        return committed_memory_id

    def ingest_runtime_observation(self, *, router: RuntimeEventRouter, inbound: InboundEvent) -> RoutingDecision:
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
        result, records = self.prepare_provider_event(event)
        self.write_records(records)
        return result

    def prepare_provider_event(
        self,
        event: ProviderEvent,
    ) -> tuple[ProviderSyncResult, tuple[CanonicalMemoryRecord, ...]]:
        policy = evaluate_operation_policy(operation=event.operation)
        transcript_ids: list[str] = []
        records: list[CanonicalMemoryRecord] = []
        if MemoryDomain.TRANSCRIPT in policy.allowed_raw_append_domains:
            transcript = self._transcript_record(event)
            transcript_ids.append(transcript.memory_id)
            records.append(transcript)

        candidate_ids: list[str] = []
        for domain in policy.allowed_candidate_domains:
            candidate = self._candidate_record(event=event, domain=domain)
            candidate_ids.append(candidate.memory_id)
            records.append(candidate)

        return (
            ProviderSyncResult(
                transcript_ids=transcript_ids,
                candidate_ids=candidate_ids,
                blocked_domains=policy.blocked_commit_domains,
                blocked_reasons=policy.blocked_reasons,
                allowed_candidate_domains=policy.allowed_candidate_domains,
                raw_append_domains=policy.allowed_raw_append_domains,
                blocked_commit_domains=policy.blocked_commit_domains,
            ),
            tuple(records),
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
        plan = self._planner.build_plan(
            intent=intent, scope=RetrievalScope(task_id=task_id), include_raw_transcript=True
        )
        planned_domains = {query_spec.domain for query_spec in plan.queries}
        pool = {
            item.memory_id: item
            for item in self._record_store().list_records(status=CommitStatus.COMMITTED)
            if item.visibility == MemoryRecordVisibility.RUNTIME_CONTEXT
            and item.domain in planned_domains
            and not item.source_kind.startswith("memory_evolution")
            and self._matches_scope(item, RetrievalScope(session_id=session_id, task_id=task_id, user_id=user_id))
        }
        provider_candidates = [to_provider_stored_record(item) for item in pool.values()]
        reranked = self._reranker.rerank(
            query=query,
            query_class=query_class,
            candidates=provider_candidates,
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
        self._record_store().stage_record(from_provider_stored_record(record, source_kind="provider_seed"))

    def provider_candidate_records(self) -> list[ProviderStoredRecord]:
        return [
            to_provider_stored_record(item)
            for item in self._record_store().list_records(status=CommitStatus.CANDIDATE)
            if item.visibility == MemoryRecordVisibility.RUNTIME_CONTEXT
            and item.status == CommitStatus.CANDIDATE
            and item.source_kind.startswith("provider")
        ]

    def provider_transcript_records(self) -> list[ProviderStoredRecord]:
        return [
            to_provider_stored_record(item)
            for item in self._record_store().list_records(domains=[MemoryDomain.TRANSCRIPT])
            if item.visibility == MemoryRecordVisibility.RUNTIME_CONTEXT
            and item.domain == MemoryDomain.TRANSCRIPT
            and item.is_raw_event
        ]

    def last_provider_prefetch_trace(self) -> ProviderPrefetchTrace | None:
        return self._last_prefetch_trace

    def _transcript_record(self, event: ProviderEvent) -> CanonicalMemoryRecord:
        memory_id = f"tx:{event.event_id}"
        return CanonicalMemoryRecord(
            memory_id=memory_id,
            domain=MemoryDomain.TRANSCRIPT,
            text=event.content or "",
            content={
                "text": event.content or "",
                "operation": event.operation.value,
                "role": event.role,
                "action": event.action,
                "target": event.target,
                **({"source_modality": event.source_modality.value} if event.source_modality is not None else {}),
                **({"source_speaker_id": event.speaker_id} if event.speaker_id is not None else {}),
            },
            status=CommitStatus.COMMITTED,
            source_kind="provider",
            timestamp=event.timestamp or datetime.now(UTC),
            session_id=event.session_id,
            task_id=event.task_id,
            user_id=event.user_id,
            language=event.language,
            is_raw_event=True,
        )

    def _candidate_record(self, *, event: ProviderEvent, domain: MemoryDomain) -> CanonicalMemoryRecord:
        memory_id = f"cand:{domain.value}:{event.event_id}"
        source_record_id = f"tx:{event.event_id}"
        return CanonicalMemoryRecord(
            memory_id=memory_id,
            domain=domain,
            text=event.content or "",
            content={"text": event.content or ""},
            status=CommitStatus.CANDIDATE,
            source_kind=f"provider:{event.operation.value}",
            timestamp=event.timestamp or datetime.now(UTC),
            session_id=event.session_id,
            task_id=event.task_id,
            user_id=event.user_id,
            language=event.language,
            is_raw_event=False,
            source_record_ids=[source_record_id],
            promotion_state="staged",
        )

    def _matches_scope(self, item: CanonicalMemoryRecord, scope: RetrievalScope) -> bool:
        if scope.session_id is not None and item.session_id not in {None, scope.session_id}:
            return False
        if scope.task_id is not None and item.task_id not in {None, scope.task_id}:
            return False
        if scope.execution_node_id is not None and item.execution_node_id not in {None, scope.execution_node_id}:
            return False
        if scope.solver_run_id is not None and item.solver_run_id not in {None, scope.solver_run_id}:
            return False
        if scope.agent_id is not None and item.agent_id not in {None, scope.agent_id}:
            return False
        return not (scope.user_id is not None and item.user_id not in {None, scope.user_id})

    def _matches_semantics(
        self,
        item: CanonicalMemoryRecord,
        *,
        include_candidates: bool,
        freshness: FreshnessPolicy | None,
    ) -> bool:
        if not include_candidates and item.status == CommitStatus.CANDIDATE:
            return False
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


def _intent_for_query_class(query_class: object) -> RetrievalIntent:
    mapping = {
        "preference_profile": RetrievalIntent.ANSWER_WITH_USER_CONTEXT,
        "fact_config": RetrievalIntent.DEBUG_OR_INVESTIGATE,
        "event_history": RetrievalIntent.DEBUG_OR_INVESTIGATE,
        "general_continuity": RetrievalIntent.DEBUG_OR_INVESTIGATE,
    }
    return mapping.get(getattr(query_class, "value", "general_continuity"), RetrievalIntent.RESUME_TASK)
