"""Intent-driven retrieval planner with explicit scope and namespace filters."""

from memorii.core.retrieval.intents import INTENT_DOMAIN_POLICY
from memorii.core.retrieval.query_plans import make_query, validity_constrained
from memorii.domain.enums import MemoryDomain
from memorii.domain.retrieval import RetrievalIntent, RetrievalPlan, RetrievalScope, TimeRange


class RetrievalPlanner:
    def build_plan(
        self,
        *,
        intent: RetrievalIntent,
        scope: RetrievalScope,
        time_range: TimeRange | None = None,
        active_validity_only: bool = False,
        include_raw_transcript: bool = False,
    ) -> RetrievalPlan:
        queries = []
        freshness = validity_constrained(active_validity_only)
        for domain in INTENT_DOMAIN_POLICY[intent]:
            queries.append(
                make_query(
                    domain,
                    scope,
                    require_raw_transcript=include_raw_transcript and domain == MemoryDomain.TRANSCRIPT,
                    include_time_range=time_range,
                    freshness=freshness,
                )
            )
        return RetrievalPlan(intent=intent, queries=queries)
