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

Generated machine identifiers are deterministically permuted into opaque
labels before either suite consumes a scenario. The permutation is
referentially consistent across observations, graph items, checkpoints, and
judges, but the map is never exposed to the system under test. Metamorphic
tests verify that changing every identifier leaves surface evidence and judge
semantics unchanged, preventing answer-bearing fixture names from becoming a
side channel.

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

Checkpoint wording also varies deterministically across seeds while the typed
checkpoint contract, family, severity, and oracle roles remain invariant. This
tests semantic reconstruction rather than memorization of one query template.

## Role-Aware Output Channels

The canonical reconstruction contract uses role-aware channels:

- `selected_*`: winning truth/action for the query
- `supporting_*`: direct evidence needed to support the selected answer/action
- `rejected_*`: stale, superseded, lower-trust, wrong-entity, ambiguous, or pasted evidence considered and ruled out
- `context_*`: useful graph/audit evidence that is neither direct answer support nor explicit rejection

Typed checkpoint artifacts expose these channels directly, and judges use the
same role-aware fields for semantic correctness.

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

Calibration is report-only. It does not change pass/fail unless an explicit
benchmark-fail policy is configured.

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

## Semantic Worlds And Live-Gate Estimand

A generator seed is not itself an independent statistical observation. Every
generated scenario carries a `semantic_world_fingerprint` derived from its
latent world parameters, excluding presentation IDs. A live gate rejects
duplicate semantic worlds across seeds so relabeled copies cannot inflate the
sample size.

The authoritative live-gate unit is one unique `seed:scenario` world. Repeated
inference calls measure stability; they do not add scenario units. A scenario
passes only when every declared inference replicate passes. The aggregate and
family gates use exact one-sided beta-binomial seed-cluster lower bounds over
those collapsed binary outcomes under a declared intraseed correlation. A
simultaneous confidence level covers the aggregate plus every declared family.
The gate additionally reports per-seed and leave-one-seed-out sensitivity.
Paired baseline comparisons collapse replicates with the same rule before
performing the seed/scenario bootstrap.

Metamorphic tests cover every family and profile. They verify that opaque-ID
permutation and unrelated observation ordering preserve oracle judgments, and
that every required checkpoint item remains visible or inferable without
exposing hidden graph items.

## Current Validation Status

The suite now validates that live hybrid reconstruction can pass multi-seed adversarial runs while preserving:

- live/fake separation
- hidden pressure
- role-aware channel hygiene
- evidence integrity
- sparse review artifacts
- deterministic dry-run behavior

## What The Simulator Does Not Prove

The simulator does not prove that the production runtime evolution service
reconstructs the graph from provider events. That is the separate responsibility
of `memory_evolution_runtime_v1`, which consumes the same generated scenarios
through production ingestion and retrieval.

## Statistical Gate Certificate

Live-gate interval coverage is certified over a predeclared reliability grid
under beta-binomial seed effects, logistic-normal seed effects, and heterogeneous
scenario-family mixtures. The production interval is the exact beta-binomial
seed-cluster interval. Wilson is used only to lower-bound the finite-Monte-Carlo
coverage estimate at each predeclared design point. The certificate takes the
minimum simultaneous coverage bound across the grid, not the most favorable
point estimate. It is valid only for reports from one clean source tree and
records the source digest, input report digests, version, data-generating
processes, reliability points, trials, seeds, and every design-point result so
changes to code or statistical assumptions remain reviewable.
