# Calibration And Decision Quality

## Status

Calibration is implemented as a benchmark/report-only layer. It does not yet change runtime retrieval, writeback, confidence caps, or abstention behavior.

## Purpose

Memorii needs calibrated memory behavior, not just high benchmark pass rates.

A memory system for agents must know when it is likely wrong, where it is brittle, and which errors are costly. Aggregate accuracy is not enough because agent failures are often slice-specific:

- source modality
- stale vs current truth
- selected vs supporting evidence
- hidden-fact hallucination
- ambiguous entity resolution
- task-scoped vs global memory

The calibration layer records decision-level events so we can reason about correctness, confidence, cost, and drift across the memory hierarchy.

## Memory Hierarchy Covered

Calibration events are intended to cover this hierarchy:

```text
raw observations
  -> extraction
  -> validation
  -> evolution
  -> graph
  -> retrieval / decision output
```

Current benchmark integration is strongest for `memory_evolution_sim_v1`, where labels come from latent oracle expectations and programmatic judges.

Runtime production events should use `label_source=runtime_unknown` until a benchmark, reviewer, or oracle alignment layer supplies labels.

## Core Event Model

`CalibrationEvent` records:

- item id and item type
- hierarchy layer
- decision channel
- confidence
- label and label source
- failure buckets
- source modality and trust
- predicate, scope, lifecycle, retrieval view
- entity ambiguity
- evidence event IDs
- judge IDs

Decision channels are:

- selected
- supporting
- rejected
- context
- abstained

## Metrics

Implemented metrics include:

- ECE with fixed 10-bin calibration
- Brier score
- Wilson interval for slice accuracy
- overconfident wrong count/rate
- low-confidence correct count/rate
- rolling windows over 10, 25, and 50 events
- drift alerts

`runtime_unknown` labels are excluded from metric denominators by default.

## Slice Reporting

Calibration computes slices by:

- predicate id
- source modality
- source trust band
- lifecycle state
- retrieval view
- scope type
- decision channel
- checkpoint type
- entity ambiguity
- profile

Pairwise slices include:

- predicate id + source modality
- predicate id + lifecycle state
- checkpoint type + decision channel
- source modality + decision channel

Minimum support policy:

- `n >= 10`: eligible for hard failure or review recommendation
- `5 <= n < 10`: warning only
- `n < 5`: informational only

## Decision Cost

Decision quality reports distinguish critical memory failures from harmless trace noise.

Default cost examples:

- hidden fact hallucinated: high cost
- wrong current truth: high cost
- source trust inversion: high cost
- scope leak: high cost
- stale memory selected: medium/high cost
- missing provenance: lower cost
- extra provenance noise: low cost

This is important because a system can have the same accuracy but very different agent risk.

## Response Policy

Response levels are:

- report_only
- review
- confidence_cap
- abstain_threshold
- benchmark_fail

V1 only recommends responses. It does not apply runtime confidence caps or abstention thresholds.

## How To Interpret Green Benchmark Runs

A green simulator run can still contain calibration recommendations.

Examples:

- low-confidence correct slices
- extra context provenance warnings
- optional graph answer missing when structured graph channels are correct

These should not be confused with semantic reconstruction failure.

For a benchmark pass to be suspect, look for:

- hidden hallucination
- selected/supporting excluded IDs
- high-confidence wrong output
- required judge failures
- provider/schema failures
- review candidates from required failures
- non-live output in a live run

## Current Known Drift

The calibration layer can currently mark low-confidence-correct slices as `review`. This is useful as calibration feedback, but it is noisy if interpreted as benchmark risk.

Recommended refinement:

- separate `low_confidence_correct_review` from true risk review
- keep true risk review for overconfident wrong, hidden leakage, and supported bad slices
- report low-confidence-correct as calibration opportunity, not pass/fail concern

## Runtime Alignment Plan

The next validation step is runtime-backed calibration.

The intended suite is `memory_evolution_runtime_v1`:

1. Generate latent simulator scenarios.
2. Ingest only surface observations through real provider/runtime APIs.
3. Let runtime memory evolution construct graph state.
4. Align runtime graph items to latent graph oracle items.
5. Emit calibration events for aligned, partial, missing, ambiguous, and extra runtime graph items.
6. Report calibration and decision quality by layer and slice.

Alignment rules should use:

- entity: normalized canonical name + entity type + alias evidence
- claim: aligned subject + predicate + normalized object + scope + valid time
- relation: aligned endpoints + relation type + directionality
- evidence: source event ID + quote overlap

## Design Principle

LLMs may help extract or classify structured information, but calibration and decision quality scoring should be deterministic, auditable, and slice-aware.
