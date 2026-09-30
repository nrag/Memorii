"""HarnessStateEnvelope: closed structured host view + deterministic text.

The envelope is the single contract hosts consume: candidate and
committed hypotheses stay distinct, recommendations are discriminated and
never executable shell strings, mandatory safety state that cannot fit
the budget degrades to an explicit reconcile_required summary with a
paging handle — never a falsely complete actionable summary. Retrieved
text is untrusted evidence, never instructions or authority.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RecommendationKind = Literal[
    "test",
    "inspect",
    "ask",
    "revalidate",
    "reconcile",
    "wait",
    "none",
]

#: Default prompt budgets (explicit tokenizer identity recorded per render).
DEFAULT_TOKEN_BUDGET = 2000
DEFAULT_WORK_ITEMS = 32
DEFAULT_FRONTIER_ITEMS = 16
DEFAULT_EVIDENCE_REFS = 64

_HEX_64 = r"^[0-9a-f]{64}$"


class HarnessOutputBlock(BaseModel):
    """One bounded work item, frontier entry or evidence reference."""

    kind: Literal["work", "frontier", "evidence", "blocker"] = "work"
    label: str = Field(min_length=1)
    candidate: bool = False
    committed: bool = False
    detail: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def commitment_labels_are_exclusive(self) -> HarnessOutputBlock:
        if self.candidate and self.committed:
            raise ValueError("an item cannot be both candidate and committed")
        return self


class HarnessStateEnvelope(BaseModel):
    """Bounded host view; errors use a separate closed envelope."""

    protocol_version: Literal[1] = 1
    task_id: str = Field(min_length=1)
    revision: int = Field(ge=0)
    checkpoint_ref: str | None = None
    status: Literal[
        "ready", "revalidation_required", "reconcile_required", "pending", "unavailable"
    ]
    goal: str | None = None
    current_execution_node: str | None = None
    execution_status: str | None = None
    ready_work: tuple[HarnessOutputBlock, ...] = ()
    blocked_work: tuple[HarnessOutputBlock, ...] = ()
    constraints: tuple[str, ...] = ()
    remaining_acceptance: tuple[str, ...] = ()
    solver_id: str | None = None
    solver_category: str | None = None
    candidate_hypotheses: tuple[HarnessOutputBlock, ...] = ()
    committed_hypotheses: tuple[HarnessOutputBlock, ...] = ()
    selected_overlay_id: str | None = None
    frontier: tuple[HarnessOutputBlock, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    unexplained_evidence: tuple[HarnessOutputBlock, ...] = ()
    reopenable_branches: tuple[HarnessOutputBlock, ...] = ()
    recommendation_kind: RecommendationKind = "none"
    recommendation_target: str | None = None
    recommendation_evidence: tuple[str, ...] = ()
    recommendation_revision: int | None = Field(default=None, ge=1)
    pending_actions: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    freshness_note: str | None = None
    omissions: tuple[str, ...] = ()
    state_digest: str = Field(pattern=_HEX_64)
    continuation_cursor: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def budget_and_digest(self) -> HarnessStateEnvelope:
        if len(self.ready_work) > DEFAULT_WORK_ITEMS:
            raise ValueError("ready_work exceeds the bounded work-item budget")
        if len(self.frontier) > DEFAULT_FRONTIER_ITEMS:
            raise ValueError("frontier exceeds the bounded frontier budget")
        if len(self.source_refs) > DEFAULT_EVIDENCE_REFS:
            raise ValueError("source_refs exceed the bounded evidence budget")
        if self.state_digest != harness_state_digest(self):
            raise ValueError("harness state digest is invalid")
        return self


def harness_state_digest(envelope: HarnessStateEnvelope) -> str:
    """Domain-separated digest over the envelope's closed fields."""
    payload_fields = envelope.model_dump(
        mode="json", exclude={"state_digest"}, exclude_none=True
    )
    import json

    payload = json.dumps(payload_fields, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(
        b"memorii.harness-state-envelope.v1\x00" + payload.encode("utf-8")
    ).hexdigest()


def build_envelope(**fields: object) -> HarnessStateEnvelope:
    """Construct and validate one envelope, computing its digest.

    Digest computation and validation share one path: the model is
    assembled (defaults applied), digested over its full closed field set,
    and then parsed so every invariant runs.
    """
    assembled = HarnessStateEnvelope.model_construct(**fields, state_digest="0" * 64)
    digest = harness_state_digest(assembled)
    return HarnessStateEnvelope.model_validate(
        assembled.model_dump(mode="json") | {"state_digest": digest}
    )


class HarnessTextRenderer:
    """Deterministic compact text for the model; the same data as JSON."""

    def __init__(self, *, tokenizer_identity: str = "approx-char/4") -> None:
        self.tokenizer_identity = tokenizer_identity

    def render(self, envelope: HarnessStateEnvelope) -> str:
        return self._render_lines(envelope)[0]

    def render_bounded(
        self, envelope: HarnessStateEnvelope
    ) -> tuple[str, HarnessStateEnvelope]:
        """Render under the token budget; degrade on mandatory overflow.

        Returns the text and the (possibly degraded) envelope. When the
        full render exceeds the declared token budget, the mandatory safety
        summary is returned instead: status reconcile_required, an explicit
        omission, and a paging marker — never a falsely complete summary.
        """
        text, char_budget = self._render_lines(envelope)
        if len(text) <= char_budget:
            return text, envelope
        degraded_fields = {
            "protocol_version": 1,
            "task_id": envelope.task_id,
            "revision": envelope.revision,
            "status": "reconcile_required",
            "goal": envelope.goal,
            "pending_actions": tuple(envelope.pending_actions),
            "omissions": [
                "state exceeded the prompt token budget"
                f" ({self.tokenizer_identity}); full state requires paging"
            ],
            "continuation_cursor": envelope.continuation_cursor,
        }
        degraded = build_envelope(**degraded_fields)
        return self._render_lines(degraded)[0], degraded

    def _render_lines(self, envelope: HarnessStateEnvelope) -> tuple[str, int]:
        # approx-char/4: one token ~ four characters, matching the declared
        # tokenizer identity. char_budget derives from DEFAULT_TOKEN_BUDGET.
        char_budget = DEFAULT_TOKEN_BUDGET * 4
        lines: list[str] = [
            f"[memorii v{envelope.protocol_version}]"
            f" task={envelope.task_id} rev={envelope.revision}"
            f" status={envelope.status}"
        ]
        if envelope.goal:
            lines.append(f"goal: {envelope.goal}")
        if envelope.current_execution_node:
            state = envelope.execution_status or "unknown"
            lines.append(f"execution: {envelope.current_execution_node} ({state})")
        for block in envelope.ready_work[:DEFAULT_WORK_ITEMS]:
            marker = _commitment_marker(block)
            lines.append(f"ready: {marker}{block.label}")
        for block in envelope.blocked_work:
            marker = _commitment_marker(block)
            lines.append(f"blocked: {marker}{block.label}")
        for constraint in envelope.constraints:
            lines.append(f"constraint: {constraint}")
        for item in envelope.remaining_acceptance:
            lines.append(f"acceptance: {item}")
        if envelope.solver_id:
            category = envelope.solver_category or "unspecified"
            lines.append(f"solver: {envelope.solver_id} ({category})")
        for block in envelope.candidate_hypotheses:
            lines.append(f"hypothesis (candidate): {block.label}")
        for block in envelope.committed_hypotheses:
            lines.append(f"hypothesis (committed): {block.label}")
        if envelope.selected_overlay_id:
            lines.append(f"overlay: {envelope.selected_overlay_id}")
        for block in envelope.frontier:
            lines.append(f"frontier: {block.label}")
        for question in envelope.unresolved_questions:
            lines.append(f"question: {question}")
        for block in envelope.unexplained_evidence:
            lines.append(f"unexplained: {block.label}")
        for block in envelope.reopenable_branches:
            lines.append(f"reopenable: {block.label}")
        if envelope.recommendation_kind != "none":
            target = envelope.recommendation_target or ""
            revision = envelope.recommendation_revision or 0
            lines.append(
                f"recommend: {envelope.recommendation_kind} {target} (rev {revision})"
            )
        for action in envelope.pending_actions:
            lines.append(f"pending-action: {action} (needs reconciliation)")
        for ref in envelope.source_refs:
            lines.append(f"source: {ref}")
        for omission in envelope.omissions:
            lines.append(f"omitted: {omission}")
        if envelope.continuation_cursor:
            lines.append(f"more: cursor {envelope.continuation_cursor}")
        lines.append(f"state-digest: {envelope.state_digest}")
        return "\n".join(lines), char_budget


def _commitment_marker(block: HarnessOutputBlock) -> str:
    if block.candidate:
        return "[candidate] "
    if block.committed:
        return "[committed] "
    return ""


def render_harness_state(envelope: HarnessStateEnvelope) -> str:
    """Default deterministic rendering with the default tokenizer identity."""
    return HarnessTextRenderer().render(envelope)


__all__ = [
    "DEFAULT_EVIDENCE_REFS",
    "DEFAULT_FRONTIER_ITEMS",
    "DEFAULT_TOKEN_BUDGET",
    "DEFAULT_WORK_ITEMS",
    "HarnessOutputBlock",
    "HarnessStateEnvelope",
    "HarnessTextRenderer",
    "RecommendationKind",
    "build_envelope",
    "harness_state_digest",
    "render_harness_state",
]
