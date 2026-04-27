# LLM Decision Evals Design

This document defines the shared eval framework for Memorii LLM decision points.

## Scope

This phase introduces only shared models, traces, snapshots, and harvesting rules.
It does not change promotion behavior, belief update behavior, provider tool behavior, or benchmark behavior.

## Offline evals

Offline evals are deterministic and replayable.

- Use curated golden snapshots (high-quality reviewed examples).
- Include regression snapshots generated from known failures.
- Enforce schema-validity checks on inputs and outputs.
- Replay snapshots deterministically for stable comparisons.
- Compare behavior across model/prompt versions using the same snapshot set.

Offline evals are the primary correctness gate before wider deployment.

## Online evals

Online evals are logging-and-harvest focused.

- Log every LLM decision as a structured trace.
- Sample traces for reviewer inspection.
- Harvest failures/disagreements into golden candidates.
- Never rely only on online metrics; online signals are noisy and incomplete.

Online traces are used to discover weak spots and feed offline regression coverage.

## Jury of judges

A jury mechanism supports robust quality checks.

- Multiple judges evaluate the same snapshot independently.
- Each judge emits a structured verdict (pass/fail, optional score, rationale).
- A jury aggregates scores and computes overall pass/fail.
- Disagreement is explicitly detected and tracked.
- Disagreement or uncertainty can route snapshots to a human-review queue.

This avoids depending on a single judge or brittle one-pass grading signal.

## Golden-set improvement loop

Golden data grows through a controlled loop.

1. Online trace is produced.
2. Trace is converted into a candidate when it indicates risk.
3. Human review approves/rejects candidate.
4. Approved candidates are appended to the golden set.

Additional rules:

- Regression failures automatically become golden candidates.
- Judge disagreement becomes golden candidate input.
- Golden set stays append-only, reviewed, and versioned.

This loop continuously improves offline eval quality while keeping provenance explicit.

## Filesystem storage

JSONL is the preferred first storage layer.

- Diffable in code review.
- Replayable in tests and tooling.
- Benchmark-friendly and deterministic.
- No database dependency at this stage.

A database-backed store can be added later behind the same typed interfaces.

## Judge evaluation policy

Judges are intentionally deferred in this PR.

- Offline deterministic eval is the first-pass regression gate.
- Judges are second-pass semantic evaluators.
- Each judge must evaluate exactly one dimension only.
- Multi-dimensional judges are not allowed.
- Jury aggregation combines several single-dimension judges.
- Human review handles judge disagreement or low confidence.
