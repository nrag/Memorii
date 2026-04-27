"""Trace storage contracts and JSONL/in-memory implementations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from memorii.core.llm_decision.models import LLMDecisionPoint, LLMDecisionStatus, LLMDecisionTrace


class LLMDecisionTraceStore(Protocol):
    def append_trace(self, trace: LLMDecisionTrace) -> None: ...

    def list_traces(
        self,
        *,
        decision_point: LLMDecisionPoint | None = None,
        status: LLMDecisionStatus | None = None,
    ) -> list[LLMDecisionTrace]: ...


class InMemoryLLMDecisionTraceStore:
    def __init__(self) -> None:
        self._traces: list[LLMDecisionTrace] = []

    def append_trace(self, trace: LLMDecisionTrace) -> None:
        self._traces.append(trace)

    def list_traces(
        self,
        *,
        decision_point: LLMDecisionPoint | None = None,
        status: LLMDecisionStatus | None = None,
    ) -> list[LLMDecisionTrace]:
        return [
            trace
            for trace in self._traces
            if (decision_point is None or trace.decision_point == decision_point)
            and (status is None or trace.status == status)
        ]


class JsonlLLMDecisionTraceStore:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def append_trace(self, trace: LLMDecisionTrace) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(trace.model_dump(mode="json"), sort_keys=True))
            handle.write("\n")

    def list_traces(
        self,
        *,
        decision_point: LLMDecisionPoint | None = None,
        status: LLMDecisionStatus | None = None,
    ) -> list[LLMDecisionTrace]:
        if not self._path.exists():
            return []

        traces: list[LLMDecisionTrace] = []
        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                trace = LLMDecisionTrace.model_validate_json(line)
                if decision_point is not None and trace.decision_point != decision_point:
                    continue
                if status is not None and trace.status != status:
                    continue
                traces.append(trace)
        return traces
