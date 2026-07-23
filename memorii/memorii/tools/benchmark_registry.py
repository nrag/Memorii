"""Registry helpers for benchmark suite dispatch.

This module intentionally knows nothing about individual benchmark suites.
Suite-specific code registers callables from ``run_benchmark`` or future
per-suite runner modules, keeping the CLI dispatch path small and explicit.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class BenchmarkSuiteRunner(Protocol):
    """Minimal contract for a benchmark suite CLI runner."""

    @property
    def suite_name(self) -> str:
        """Stable public suite name used by the CLI registry."""
        ...

    def supports_mode(self, mode: str) -> bool:
        """Return whether this suite accepts the requested mode value."""
        ...

    def unsupported_mode_message(self, mode: str) -> str:
        """Return the user-facing error for an unsupported mode."""
        ...

    def run(self, args: argparse.Namespace, *, prompt_root: Path) -> int:
        """Run the suite and return a process-style exit code."""
        ...


@dataclass(frozen=True)
class FunctionBenchmarkSuiteRunner:
    """Small adapter for existing function-based suite implementations."""

    suite_name: str
    run_func: Callable[[argparse.Namespace, Path], int]
    supported_modes: frozenset[str]
    unsupported_mode_message_template: str | None = None

    def supports_mode(self, mode: str) -> bool:
        return mode in self.supported_modes

    def unsupported_mode_message(self, mode: str) -> str:
        if self.unsupported_mode_message_template is not None:
            return self.unsupported_mode_message_template.format(suite=self.suite_name, mode=mode)
        return f"{self.suite_name} does not support mode {mode}"

    def run(self, args: argparse.Namespace, *, prompt_root: Path) -> int:
        return self.run_func(args, prompt_root)


class BenchmarkSuiteRegistry:
    """Name-keyed registry for benchmark suite runners."""

    def __init__(self, runners: Iterable[BenchmarkSuiteRunner] = ()) -> None:
        self._runners: dict[str, BenchmarkSuiteRunner] = {}
        for runner in runners:
            self.register(runner)

    def register(self, runner: BenchmarkSuiteRunner) -> None:
        if runner.suite_name in self._runners:
            raise ValueError(f"Duplicate benchmark suite runner: {runner.suite_name}")
        self._runners[runner.suite_name] = runner

    def get(self, suite_name: str) -> BenchmarkSuiteRunner:
        try:
            return self._runners[suite_name]
        except KeyError as exc:
            raise ValueError(f"Unsupported benchmark suite: {suite_name}") from exc

    def suite_names(self) -> list[str]:
        return list(self._runners)
