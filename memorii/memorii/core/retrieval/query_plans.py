"""Helpers for building retrieval query objects."""

from memorii.domain.enums import MemoryDomain
from memorii.domain.retrieval import (
    DomainRetrievalQuery,
    FreshnessPolicy,
    RetrievalNamespace,
    RetrievalScope,
    TimeRange,
    ValidityStatus,
)


def make_query(
    domain: MemoryDomain,
    scope: RetrievalScope,
    *,
    require_raw_transcript: bool = False,
    include_candidates: bool = False,
    include_time_range: TimeRange | None = None,
    freshness: FreshnessPolicy | None = None,
) -> DomainRetrievalQuery:
    namespace = RetrievalNamespace(
        memory_domain=domain,
        task_id=scope.task_id,
        execution_node_id=scope.execution_node_id,
        solver_run_id=scope.solver_run_id,
        agent_id=scope.agent_id,
        artifact_id=scope.artifact_id,
    )
    return DomainRetrievalQuery(
        domain=domain,
        scope=scope,
        namespace=namespace,
        time_range=include_time_range,
        freshness=freshness,
        require_raw_transcript=require_raw_transcript,
        include_candidates=include_candidates,
    )


def validity_constrained(active_only: bool) -> FreshnessPolicy | None:
    if not active_only:
        return None
    return FreshnessPolicy(required_validity=ValidityStatus.ACTIVE)
