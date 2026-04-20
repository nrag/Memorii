"""Intent policy mappings for retrieval planning."""

from memorii.domain.enums import MemoryDomain
from memorii.domain.retrieval import RetrievalIntent


INTENT_DOMAIN_POLICY: dict[RetrievalIntent, list[MemoryDomain]] = {
    RetrievalIntent.CONTINUE_EXECUTION: [MemoryDomain.EXECUTION, MemoryDomain.TRANSCRIPT],
    RetrievalIntent.DEBUG_OR_INVESTIGATE: [MemoryDomain.SOLVER, MemoryDomain.EPISODIC, MemoryDomain.SEMANTIC],
    RetrievalIntent.ANSWER_WITH_USER_CONTEXT: [MemoryDomain.USER, MemoryDomain.SEMANTIC, MemoryDomain.TRANSCRIPT],
    RetrievalIntent.RESUME_TASK: [MemoryDomain.EXECUTION, MemoryDomain.SOLVER, MemoryDomain.TRANSCRIPT],
    RetrievalIntent.CONSOLIDATE_CASE: [MemoryDomain.SOLVER, MemoryDomain.EXECUTION, MemoryDomain.TRANSCRIPT],
}
