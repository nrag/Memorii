"""Eval snapshot/candidate storage and helper logic for harvesting golden data."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol

from memorii.core.llm_decision.models import (
    EvalSnapshot,
    GoldenCandidate,
    JuryVerdict,
    LLMDecisionPoint,
    LLMDecisionStatus,
    LLMDecisionTrace,
)


class EvalSnapshotStore(Protocol):
    def append_snapshot(self, snapshot: EvalSnapshot) -> None: ...

    def list_snapshots(
        self,
        *,
        decision_point: LLMDecisionPoint | None = None,
        source: str | None = None,
    ) -> list[EvalSnapshot]: ...


class InMemoryEvalSnapshotStore:
    def __init__(self) -> None:
        self._snapshots: list[EvalSnapshot] = []

    def append_snapshot(self, snapshot: EvalSnapshot) -> None:
        self._snapshots.append(snapshot)

    def list_snapshots(
        self,
        *,
        decision_point: LLMDecisionPoint | None = None,
        source: str | None = None,
    ) -> list[EvalSnapshot]:
        return [
            snapshot
            for snapshot in self._snapshots
            if (decision_point is None or snapshot.decision_point == decision_point)
            and (source is None or snapshot.source == source)
        ]


class JsonlEvalSnapshotStore:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def append_snapshot(self, snapshot: EvalSnapshot) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(snapshot.model_dump(mode="json"), sort_keys=True))
            handle.write("\n")

    def list_snapshots(
        self,
        *,
        decision_point: LLMDecisionPoint | None = None,
        source: str | None = None,
    ) -> list[EvalSnapshot]:
        if not self._path.exists():
            return []

        snapshots: list[EvalSnapshot] = []
        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                snapshot = EvalSnapshot.model_validate_json(line)
                if decision_point is not None and snapshot.decision_point != decision_point:
                    continue
                if source is not None and snapshot.source != source:
                    continue
                snapshots.append(snapshot)
        return snapshots


class GoldenCandidateStore(Protocol):
    def append_candidate(self, candidate: GoldenCandidate) -> None: ...

    def list_candidates(
        self,
        *,
        decision_point: LLMDecisionPoint | None = None,
    ) -> list[GoldenCandidate]: ...


class InMemoryGoldenCandidateStore:
    def __init__(self) -> None:
        self._candidates: list[GoldenCandidate] = []

    def append_candidate(self, candidate: GoldenCandidate) -> None:
        self._candidates.append(candidate)

    def list_candidates(
        self,
        *,
        decision_point: LLMDecisionPoint | None = None,
    ) -> list[GoldenCandidate]:
        return [
            candidate
            for candidate in self._candidates
            if decision_point is None or candidate.decision_point == decision_point
        ]


class JsonlGoldenCandidateStore:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def append_candidate(self, candidate: GoldenCandidate) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(candidate.model_dump(mode="json"), sort_keys=True))
            handle.write("\n")

    def list_candidates(
        self,
        *,
        decision_point: LLMDecisionPoint | None = None,
    ) -> list[GoldenCandidate]:
        if not self._path.exists():
            return []

        candidates: list[GoldenCandidate] = []
        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                candidate = GoldenCandidate.model_validate_json(line)
                if decision_point is not None and candidate.decision_point != decision_point:
                    continue
                candidates.append(candidate)
        return candidates


def should_harvest_golden_candidate(
    *,
    trace: LLMDecisionTrace,
    jury_verdict: JuryVerdict | None = None,
) -> bool:
    if trace.status in {LLMDecisionStatus.VALIDATION_FAILED, LLMDecisionStatus.PROVIDER_ERROR}:
        return True
    if trace.fallback_used:
        return True
    if jury_verdict is None:
        return False
    return jury_verdict.needs_human_review or jury_verdict.disagreement


def build_golden_candidate_from_trace(
    *,
    trace: LLMDecisionTrace,
    snapshot_id: str,
    reason: str,
    priority: float = 0.5,
) -> GoldenCandidate:
    stable_key = {
        "snapshot_id": snapshot_id,
        "decision_point": trace.decision_point.value,
        "trace_id": trace.trace_id,
        "reason": reason,
    }
    digest = hashlib.sha256(json.dumps(stable_key, sort_keys=True).encode("utf-8")).hexdigest()[:16]

    return GoldenCandidate(
        candidate_id=f"golden:{digest}",
        snapshot_id=snapshot_id,
        decision_point=trace.decision_point,
        reason=reason,
        priority=priority,
        created_at=trace.created_at,
    )
