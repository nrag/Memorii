# Latent Graph Memory Evolution Simulator

## Status

`memory_evolution_sim_v1` is implemented as a benchmark-only latent graph validation suite. It does not change production runtime memory behavior.

## Purpose

The simulator validates whether a system can reconstruct an evidence-supported memory graph from partial, noisy, long-running observations.

It exists because ordinary retrieval benchmarks do not test the central Memorii problem:

```text
multiple locally plausible memories exist,
but only one is current, scoped, trusted, historical, or actionably relevant.
```

## Three-Layer Contract

The simulator has three layers:

```text
1. hidden latent graph
   complete source of truth for generated scenario

2. surface observations
   the only evidence exposed to the system under test

3. programmatic judge committee
   deterministic scoring over system output vs oracle checkpoints
```

LLMs are never used as truth or judge. In live mode, an LLM is only the system-under-test reconstruction path.

## Modes

Implemented mode behavior:

- `rule`: deterministic shallow baseline
- `llm --dry-run`: fake oracle-shaped output for plumbing validation
- `hybrid --dry-run`: fake oracle-shaped output for plumbing validation
- `llm --allow-live`: live LLM reconstruction from surface observations and visible candidate cards only
- `hybrid --allow-live`: live LLM reconstruction, falling back to rule only on provider/schema failure

A green live run must show `final_output_source=live_llm`, not `fake_oracle`.

## Hidden Graph

Each scenario contains latent entities, claims, relations, source observations, oracle checkpoints, and evaluation metadata.

Adversarial and long-horizon profiles include hidden latent items. Hidden items are plausible but unrecoverable from the exposed observations.

Hidden items may appear in:

- latent graph artifacts
- fixture audit artifacts
- hidden-hallucination judge internals

Hidden items must not appear in:

- surface text
- candidate cards
- live prompt context
- expected selected/supporting/rejected/context IDs
- dry-run oracle output

## Surface Observations

Surface observations are the only records exposed to the system under test.

They include:

- event id
- timestamp
- source type
- modality
- trust level
- text
- exposed entity/claim/relation IDs for artifact construction

Model-facing candidate cards are sanitized. They must not contain keys such as:

- `expected_answer`
- `expected_claim_ids`
- `expected_entity_ids`
- `expected_excluded_*`
- `expected_next_action`
- `expected_relation_ids`
- `hidden_distractor_ids`

## Visible Candidate Cards

Live reconstruction receives visible candidate cards derived only from surface observations and exposed graph items.

Visible cards include:

- events
- entities
- claims
- relations

Visible relation cards include relation type, endpoints, endpoint types, directionality, lifecycle, and evidence quote.

Candidate cards are not oracle answers. They are a model-facing structured view of the exposed observation stream.

## Role-Aware Output Channels

The canonical reconstruction contract uses role-aware channels:

- `selected_*`: winning truth/action for the query
- `supporting_*`: direct evidence needed to support the selected answer/action
- `rejected_*`: stale, superseded, lower-trust, wrong-entity, ambiguous, or pasted evidence considered and ruled out
- `context_*`: useful graph/audit evidence that is neither direct answer support nor explicit rejection

Legacy flattened fields may be kept in artifacts, but judges use role-aware channels for semantic correctness.

## Checkpoint Contracts

Checkpoint contracts define:

- allowed operation: `answer`, `next_action`, `graph_reconstruction`, or `abstain`
- whether answer text is required
- selected entity role policy
- whether stale/superseded facts may be selected
- whether excluded facts must be rejected
- whether subject definition/type claims are required

Important current semantics:

- Truth checkpoints select the claim subject entity, not necessarily the answer object entity.
- Graph reconstruction checkpoints are judged primarily by structured channels, not by natural-language summaries.
- Execution checkpoints require `operation=next_action` and structured continuation state.

## Programmatic Judges

The judge committee is deterministic and transparent.

Implemented judge families cover:

- entity identity
- entity type
- alias resolution
- claim subject-predicate-object
- claim lifecycle
- temporal truth
- source trust
- modality suppression
- relation directionality
- support/contradiction
- scope
- belief ranking
- execution branch
- provenance
- hidden hallucination
- ambiguity abstention
- confidence calibration
- role-aware selected truth precision
- supporting evidence precision
- rejection classification
- graph context
- definition coverage

Required judge failure fails a checkpoint. Optional warning-only issues are reported but do not fail a clean semantic pass.

## Hidden-Fact Pressure

Adversarial fixtures include hidden latent mini-graphs and surface text that tempts unsupported inference without exposing hidden IDs or names.

The hidden hallucination judge fails:

- hidden IDs in any output channel
- answer text that names a hidden entity canonical name or alias

Reports include hidden item counts and hidden hallucination rates.

## Calibration Artifacts

The simulator writes calibration events and reports for decision quality analysis.

Calibration is report-only in v1. It should not change pass/fail unless a canary or explicit benchmark-fail policy is configured.

Current known reporting nuance:

- Green runs can still have low-confidence-correct calibration review recommendations.
- That is calibration feedback, not latent graph reconstruction failure.

## Artifacts

Key artifacts include:

- `latent_graphs.json`
- `surface_observations.jsonl`
- `candidate_cards.jsonl`
- `oracle_checkpoints.jsonl`
- `sim_checkpoint_results.jsonl`
- `judge_votes.jsonl`
- `judge_aggregate.json`
- `review_candidates.jsonl`
- `failures.jsonl`
- `calibration_events.jsonl`
- `calibration_report.json`
- `slice_calibration_report.json`
- `decision_quality_report.json`

## Current Validation Status

The suite now validates that live hybrid reconstruction can pass multi-seed adversarial runs while preserving:

- live/fake separation
- hidden pressure
- role-aware channel hygiene
- evidence integrity
- sparse review artifacts
- deterministic dry-run behavior

## What The Simulator Does Not Prove

The simulator does not prove that the production runtime evolution service reconstructs the graph from provider events.

That requires the future `memory_evolution_runtime_v1` suite.
