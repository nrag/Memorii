"""Independent reference semantics for memory-evolution benchmark expectations."""

from memorii.core.benchmark.memory_evolution_oracle.execution import (
    OracleAction,
    OracleWorkState,
    build_oracle_execution_expectation,
    reduce_oracle_work_states,
)

__all__ = [
    "OracleAction",
    "OracleWorkState",
    "build_oracle_execution_expectation",
    "reduce_oracle_work_states",
]
