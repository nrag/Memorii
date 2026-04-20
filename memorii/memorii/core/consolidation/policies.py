"""Policy gates for writeback candidate generation."""

from memorii.domain.enums import MemoryDomain


class ConsolidationPolicy:
    def allow_writeback(
        self,
        *,
        domain: MemoryDomain,
        is_validated: bool,
        is_speculative: bool,
        is_durable_user_signal: bool,
    ) -> bool:
        if domain == MemoryDomain.SEMANTIC:
            return is_validated and not is_speculative
        if domain == MemoryDomain.USER:
            return is_durable_user_signal and is_validated and not is_speculative
        if domain in {MemoryDomain.EPISODIC, MemoryDomain.SOLVER, MemoryDomain.EXECUTION, MemoryDomain.TRANSCRIPT}:
            return True
        return False
