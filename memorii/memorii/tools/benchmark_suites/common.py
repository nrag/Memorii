"""Shared helpers for benchmark suite runner modules."""

from __future__ import annotations

import argparse

ALL_DECISION_MODES = frozenset({"auto", "rule", "llm", "hybrid", "all"})
DETERMINISTIC_BENCHMARK_MODES = frozenset({"auto", "rule", "all"})


def require_memorii_only(args: argparse.Namespace, suite_name: str) -> None:
    if args.systems == "all":
        raise SystemExit(f"{suite_name} currently supports --systems memorii only")
