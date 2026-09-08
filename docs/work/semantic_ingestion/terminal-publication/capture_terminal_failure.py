"""Diagnostic-only wrappers; preserve original returns and exceptions."""

from functools import wraps
import traceback

import pytest

from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
from memorii.core.semantic_ingestion.bootstrap_graph_terminal_preparation import (
    DeterministicBootstrapGraphTerminalPreparationV3,
)


def observe(owner: type, name: str) -> None:
    original = getattr(owner, name)

    @wraps(original)
    def traced(*args, **kwargs):
        print(f"ENTER {owner.__name__}.{name}", flush=True)
        try:
            result = original(*args, **kwargs)
        except Exception:
            print(f"FAIL {owner.__name__}.{name}", flush=True)
            traceback.print_exc()
            raise
        print(f"RETURN {owner.__name__}.{name}: {type(result).__name__}", flush=True)
        return result

    setattr(owner, name, traced)


if __name__ == "__main__":
    observe(DeterministicBootstrapGraphTerminalPreparationV3, "prepare")
    observe(SemanticIngestionAtomicStore, "persist_bootstrap_graph_terminal_v3")
    raise SystemExit(pytest.main([
        "-q", "-s", "-x", "-p", "no:cacheprovider",
        "memorii/tests/unit/core/semantic_ingestion/"
        "test_bootstrap_graph_root_composition.py::"
        "test_all_normal_roots_execute_graph_terminal_once[direct]",
    ]))
