# Memory Accumulation Benchmark

## Status

Design. `memory_accumulation_v1` is specified by this document and is not
implemented. No claim of existing benchmark behavior may cite this document
until the implementation WorkPlan records revision-bound evidence.

## Purpose

The existing memory-evolution suites validate that the production runtime can
reconstruct a correct memory graph from one short, single-stream,
single-world scenario against a fresh in-memory store:

- `memory_evolution_sim_v1` validates reconstruction decisions from visible
  simulator cards.
- `memory_evolution_runtime_v1` validates the production
  `ProviderMemoryService` path over simulator surface observations.

Neither measures what a memory plane faces under long-running operation:
many sessions arriving against one persistent store over weeks, beliefs
revised repeatedly, several users and projects interleaved in the same store,
store growth into the thousands of items, and restarts or recovery
mid-stream.

`memory_accumulation_v1` measures the production memory plane under exactly
those accumulation conditions. It extends the latent-graph simulator with
session-structured, multi-world, scale-tiered workloads and runs them through
the production provider path over a persistent store, judged by the existing
deterministic judge committee plus one new judge family.

The suite changes no production defaults and adds no production memory
semantics.

## Position In The Long-Running Evals Roadmap

This design is Track 1 of the owner-approved three-track long-running-task
evals plan (2026-10-02):

1. **Track 1 — this design.** Long-horizon accumulation benchmark.
2. **Track 2 — community comparability adapter** (LongMemEval-style
   multi-session QA). Separate future design. Entry criteria: Track 1
   deterministic and fake-oracle gates green; external dataset licensing and
   format decision recorded.
3. **Track 3 — agent-level task-utility ablation** on real host harnesses.
   Separate future design, mandated by
   `docs/design/memory_evolution_runtime.md`. Entry criteria: Track 1 live
   smoke evidence (MAB-16); host readiness per
   `docs/plans/agent_integration_readiness.md`.

## Problem Definition

- **Actors.** Benchmark operators (maintainers, CI), the memory-plane
  maintainers consuming the measurements, and — downstream — agent-host
  integrators deciding whether the plane retains, scopes, and recovers memory
  reliably over long horizons.
- **Current behavior.** Each scenario is one temporally ordered observation
  stream (`memory_evolution_runtime/runner.py:208`) against a fresh
  in-memory `MemoryPlaneService()` (`runner.py:193`), with at most 60 events,
  one project world per store, and simulated horizons up to ~120 days. The
  `session_id`/`user_id`/`task_id` fields exist end-to-end
  (`memory_evolution_sim/schemas.py:344-346`,
  `memory_evolution_runtime/ingestion.py:15-27,124-133`,
  `runner.py:258-272`) but no generator populates them. Nothing benchmarks
  persistent-store accumulation, cross-world interference, retrieval
  degradation with store size, or `reconcile_memory_evolution()`.
- **Desired outcome.** A benchmark suite that, through the production
  provider entry points only, measures retention across sessions and idle
  gaps, supersession at revision depth, cross-world interference isolation,
  consolidation survival of needed facts, retrieval behavior as the store
  grows, and durability across restart, replay, and periodic
  reconciliation — with oracle isolation, deterministic judges, and
  statistical gates equal in rigor to the existing suites.
- **Why it matters.** The product thesis is a durable memory plane for
  long-running agents. Every claim the thesis makes is currently unmeasured.
  The first-release announcement will be asked "what about long-running
  evals?"; this track is the governed answer, and it must not overclaim.

## Non-Goals

- Agent policy interaction or end-to-end task outcomes (Track 3).
- External benchmark comparability or leaderboard numbers (Track 2).
- New production memory semantics: no decay/forgetting function, no recency
  ranking, no new lifecycle states. Retention is *measured*, not implemented.
- Real-clock (wall-week) soak testing; horizons are simulated time.
- Full live certification execution for this suite (Level 3 follow-up; the
  gate design is in scope).
- Weakening or re-baselining any existing suite, gate, or threshold.

## Existing-System Analysis

Verified against code on 2026-10-02 (details in the WorkPlan evidence log):

- **Harness composition.** `run_runtime_scenarios` builds one extractor, one
  fresh `MemoryPlaneService`, and one provider per scenario
  (`runner.py:184-206`); the provider is constructed by an injected
  `provider_factory(memory_plane=..., memory_evolution_extractor=...,
  memory_evolution_query_analyzer=...)` (`runner.py:202-206`). The factory is
  a required dependency — `BenchmarkRuntimeDependencies` defaults it to
  `None` (`tools/benchmark_suites/runtime_dependencies.py:88`) and the runner
  raises without it (`runner.py:164-170`) — and the only existing
  implementation is test-support code
  (`memorii/tests/support/memory_evolution_provider_harness.py`), not
  shipped-package machinery. The suite observes only provider-facing entry
  points: ingestion via `sync_event`/`apply_memory_write` with stable
  operation IDs (`ingestion.py:83-107`), retrieval via
  `provider.prefetch_result(..., reference_time=..., purpose=...,
  task_id=..., session_id=..., user_id=...)` (`runner.py:261-272`).
- **Scope plumbing exists, with a single-stream fallback.** Observations
  carry session/user/task fields into `IngestionContext`
  (`ingestion.py:124-133`); checkpoints carry `request_*` scope with an
  ingestion-context fallback (`runner.py:258-260`). The runner-level context
  is created empty and never written back, so today every checkpoint that
  leaves `request_*` unset issues an unscoped query — harmless in the
  single-world suites, invalid for interleaved world-sets (see Workload
  Contract).
- **Persistence exists.** `MemoryPlaneService.__init__(*, record_store=...)`
  accepts a store; `SqliteMemoryPlaneStore` provides a durable SQLite-backed
  plane with `is_durable_store` reporting (`core/memory_plane/service.py:69-72,104-109`,
  `core/memory_plane/sqlite_store.py`). The durable release added managed
  partitions with signed publication (`core/persistence/factory.py`),
  deferred to a follow-up family here.
- **Recovery exists.** `ProviderMemoryService.reconcile_memory_evolution()`
  (`core/provider/service.py:2807`) reclaims expired leases and retryable
  failures. Production callers today: the Hermes completed-turn recovery
  worker (`core/semantic_ingestion/hermes_completed_turn_runtime.py`) and
  the Hermes host integration startup path
  (`integrations/hermes_provider.py` `start_semantic_ingestion`;
  `integrations/hermes_factory.py` startup recovery, default-on). The
  framework-neutral composition root `build_provider_memory_service_from_env`
  does not itself call reconcile at startup, while
  `docs/design/memory_evolution_runtime.md` describes a startup recovery
  cycle there — recorded as a pre-existing doc/code divergence in the
  WorkPlan (the Hermes host composition does run startup recovery, outside
  the core factory). Nothing measures reconcile behavior.
- **Judges and stats exist.** The deterministic judge committee
  (`memory_evolution_sim/judges.py`, ~21 families), stage-attribution
  failure buckets, beta-binomial seed-cluster live gates with
  `semantic_world_fingerprint` dedup (`calibration/gates.py`,
  `calibration/statistics.py` — the seed-cluster interval AND-collapses
  within-unit values before clustering), paired-baseline bootstrap, and
  `LiveCertificationPolicy` (`calibration/policy.py`) are reusable
  machinery. Note: the shipped CLI wires provider factories only through the
  injected dependency above; there is no shipped default factory.
- **Simulator limits.** One templated project world per scenario; opaque-ID
  permutation and world fingerprints are per-scenario; horizon ceiling day
  120, ≤60 events; store sizes in the tens of records.

## Requirements Ledger

Priorities: `P1` = the benchmark's core purpose is broken without it;
`P2` = important measurement or safety property; `P3` = fit and finish.
All requirements are currently `specified` (see Evidence Maturity).

| ID | Requirement | Source | Priority | Acceptance criteria | Status |
| -- | ----------- | ------ | -------- | ------------------- | ------ |
| MAB-01 | Session-structured workload generation: world-set observations grouped into sessions with populated `session_id`/`user_id` (`task_id` optional per schema; null `task_id` means task-global scope) | Track 1 direction; Current State gap | P1 | Every observation has non-null `session_id` and `user_id`; every session has ≥1 observation; gap distribution declared in the manifest with at least one ≥14-day dormancy gap per standard world; session-distance reporting bands [0], (0,4], (4,16], (16,∞) sessions are the declared default; same seed yields byte-identical generation-side artifact digests | specified |
| MAB-02 | Multi-world interleaving: 2–3 semantic worlds (distinct users/projects) interleaved in one store over a shared epoch, with declared cross-world alias pressure | Track 1 direction | P1 | World-set manifest lists worlds with distinct `user_id` and project entities; ≥1 shared entity name declared as alias pressure; worlds share one epoch with a minimum cross-world temporal overlap fraction of 0.5 (half of each world's span overlaps another world's); the merged stream is a total order over globally-unique event ids; existing single-world families generate unchanged bytes | specified |
| MAB-03 | Scale tiers: `compact` (~10^2), `growth` (~10^3), `saturation` (~10^4) observations per world-set, with explicit tier selection and recorded resource ceilings | Track 1 direction | P2 | Tier observation ranges and wall-clock ceilings are declared constants; the `saturation` range floor is predeclared (≥5×10^3 observations) so tuning cannot silently shrink the ladder below the Problem Definition's thousands-of-items target; unknown tier or exceeded ceiling fails with a typed error; `saturation` completes deterministically within its ceiling (implementation feasibility gate measuring the write-path complexity class, not one wall-time number) | specified |
| MAB-04 | Persistent-store composition: accumulation runs compose the production plane over a benchmark-owned SQLite store that survives provider recreation, using a benchmark-owned provider composition | Track 1 direction; durable-release thesis | P1 | The accumulation package owns a provider factory with the same DI shape and kwargs as the test-support harness (`memory_plane`, `memory_evolution_extractor`, `memory_evolution_query_analyzer`), constructed from production classes only and never importing `memorii.tests.support` from shipped code; runs use `MemoryPlaneService(record_store=SqliteMemoryPlaneStore(...))`; an in-memory store fails the `store_not_durable` bucket; an import-boundary architecture test proves no benchmark-private persistence path exists | specified |
| MAB-05 | Retention measurement: recall of oracle-labeled facts as a function of age and sessions-since-write | Track 1 constructs | P1 | Retention checkpoints exist at predeclared age bins [0,1), [1,7), [7,30), [30,90), [90,∞) days and the declared session-distance bands; the world-set manifest declares per-bin fact counts, and an empty reachable bin (notably [90,∞)) is a generator contract violation, not a measured zero; `retention_curve.jsonl` rows carry fact age, session distance, tier, arm, mode, verdict; per-bin descriptive reporting may use exact binomial bounds, but every retention threshold *decision* uses the MAB-12 seed-cluster machinery (deterministic tiers: exact all-must-pass assertions) | specified |
| MAB-06 | Supersession-depth measurement: current-truth correctness after repeated revision of the same predicate | Track 1 constructs | P1 | Revision chains of depth 3 (smoke) / 5 (standard) over single-value predicates; after each revision a `current`-view checkpoint must reflect the latest eligible revision and a `historical_at` checkpoint must return the revision valid at query time; depth rows record chain depth and per-revision correctness | specified |
| MAB-07 | Interference measurement: cross-world leakage in one store, under explicit query scope | Track 1 constructs | P1 | Every accumulation checkpoint carries an explicit world-correct `request_user_id` (plus `request_session_id`/`request_task_id` where the construct requires); the ingestion-context fallback is disallowed in the accumulation runner, and a contract test asserts no accumulation checkpoint resolves to a null or cross-world scope; scoped queries are judged by the `cross_world_leakage` judge — any world-B item in selected/supporting/rejected/context channels for a world-A query fails; any cross-world `merged_into`/`same_as` edge fails the graph audit; leakage rate reported per world-set | specified |
| MAB-08 | Consolidation-survival measurement: facts needed later that evolution dropped or merged away | Track 1 constructs | P1 | The generator plants `must_survive` facts (oracle-only metadata) with declared sampling floors: ≥20 per standard world-set, spread to cover every reachable age bin with ≥3 facts per bin; later checkpoints query them; a checkpoint failing because no aligned claim exists in the store emits the `consolidation_dropped_needed_fact` bucket; survival rate reported; a fault-injection test seeds a suppressed/dropped fact and proves the bucket fires (the measurement is not vacuous) | specified |
| MAB-09 | Scale-degradation measurement: retrieval quality and deterministic-gate latency behavior vs. store size | Track 1 constructs | P2 | At each tier boundary a fixed probe query set is evaluated; `scale_degradation.jsonl` rows carry store item count, arm, precision@8, and mode; retrieval wall-time p50/p95 live in the digest-exempt `scale_timing.jsonl` report-only artifact; hard deterministic-tier gates are precision@8 plus a coarse wall-time *ceiling* (typed failure with generous bound); percentile values are informational, never threshold assertions | specified |
| MAB-10 | Durability-under-operations family: session-boundary provider recreation, mid-session crash restart, duplicate replay, periodic reconciliation | Track 1 constructs; durable-release thesis | P1 | Providers are recreated at declared session boundaries (host-like churn) and, in the durability family, additionally at a mid-session crash point followed by duplicate redelivery of the last operation ID, which adds no new records; graph-snapshot alignment across each boundary shows no semantic loss; the reconcile family seeds a genuinely stuck operation (expired lease via injected deterministic `now_provider` advanced past the lease duration, or a retryable failure) and proves `reconcile_memory_evolution()` reclaims it, with lease outcomes judged against the injected clock — a run with nothing stuck does not satisfy the reconcile evidence; outcomes recorded in `durability_results.jsonl` | specified |
| MAB-11 | Oracle isolation on all new surfaces | Simulator contract | P1 | Session/user/task metadata, world-set manifest, and new artifacts contain no oracle fields; sanitized-surface contract tests cover the new members; hidden items never enter surface text, candidate cards, or prompts; opaque-ID permutation is referentially consistent across worlds within a set; the world-set row fingerprint is a deterministic digest over ordered member-world fingerprints (reusing the existing dedup gate unchanged), and member-level cross-seed duplicate worlds are excluded by generator policy plus a deterministic manifest-audit test | specified |
| MAB-12 | Statistical gate model with store-level clustering honored | Gate rigor | P1 | The aggregate live-gate unit is one `seed × world-set` collapsed binary (every checkpoint in the world-set must pass); each construct-family gate uses the per-(`world-set` × family) all-must-pass collapse over that family's checkpoints as its unit binary, entering the existing `seed_cluster_scenario_pass_interval` machinery with declared intraseed correlation; family coverage requires an accumulation-specific per-seed minimum of world-sets containing that family; deterministic tiers use exact assertions with no sampling; every threshold decision on any construct uses this machinery | specified |
| MAB-13 | Fail-closed inputs and ceilings | Universal invariant | P2 | Unknown profile/tier/world-count, malformed session boundaries, exceeded observation or cost ceilings, and live mode requested on `growth` or `saturation` all produce typed errors with explicit codes; no silent truncation, fallback, or tier reassignment | specified |
| MAB-14 | Typed artifact contract with evidence-class separation | Implementation rules | P2 | Every artifact member is a pydantic row model with `extra="forbid"`; the common row identity block is (run identity, arm, seed, tier, world-set id, world id where applicable, mode); a "row set" is one (run identity, arm, world-set, seed) group; `arm` distinguishes `memorii` from baseline arms (`transcript_only`, `flat_retrieval`) since mode cannot; modes (`rule`/`fake_oracle`/`live_llm`) never mix within a row set; digest determinism covers generation-side artifacts byte-for-byte and store-derived rows after declared sort-key canonicalization; the digest-exempt member list (`scale_timing.jsonl`) is itself contract-tested; stage-attribution buckets extended with the new buckets | specified |
| MAB-15 | Paired rule-simulated baselines extended to accumulation, with explicit applicability | Existing baseline contract | P2 | Transcript-only (recency) and flat-retrieval baselines run per world-set using the existing paired seed/scenario-collapsed bootstrap; baseline rows carry their `arm` and never count as Memorii arms; `baseline_no_solver_graph` is explicitly excluded with reason (no solver memory in the measured path), satisfying the benchmark.md §15.5 skip rule | specified |
| MAB-16 | Evidence ladder and claims discipline with live purity | Evidence-class rules | P1 | Deterministic dry-run gate (smoke profile) green in the PR gate; fake-oracle plumbing validated; a live smoke of ≤2 bounded `compact` world-sets counts as live evidence only when every world-set reports `final_output_source == live_llm` on every checkpoint — runs with rule fallback (`mixed`) or any non-live source are recorded, labeled, and never counted as live provider success; the extractor mode(s) used by the smoke are recorded in the artifact; the full live certification policy for this suite is recorded as Level 3 follow-up and never claimed from smoke evidence | specified |
| MAB-17 | Non-regression of existing suites | Release safety | P1 | With accumulation code present but unselected, `memory_evolution_sim_v1` and `memory_evolution_runtime_v1` outputs for existing profiles are digest-stable; existing certification policy and thresholds unchanged; a test proves the stability | specified |
| MAB-18 | Profile matrix and CLI surface: named profiles selecting tier, worlds, seeds, revision depth, families, modes, and gate placement | Spec-audit round 1 | P2 | Profiles are declared constants covering every axis: `smoke` = `compact` tier, 1 world-set of 2 worlds, 1 seed, revision depth 3, all construct families at minimum counts (≥1 checkpoint each, `must_survive`/dormancy floors exempt), rule + fake-oracle modes, horizon 30d, PR-gate dry-run placement; `standard` = 3 seeds × 2 world-sets of 2–3 worlds, `growth`-tier deterministic + bounded `compact` live, revision depth 5, all construct families, horizon 180d, scheduled placement; `scale` = `saturation` tier, 1 seed × 1 world-set, no revision chains, `scale_degradation` + `restart_replay_recovery` families only, rule only, horizon 180d, named slow-tier scheduled placement with recorded budget; the suite CLI exposes `--profile` (tier derived from profile, not free-combinable); the `AccumulationWorldSet` typed contract and CLI flags are ledgered in the identity table; unknown profile fails closed per MAB-13 | specified |

## Architecture And Ownership

```text
memory_evolution_sim/accumulation.py      (new, additive)
  composes world-sets: N existing-family worlds, shared epoch, session
  boundaries, idle gaps, revision chains, must_survive metadata, alias
  pressure, tier scaling; emits AccumulationWorldSet (scenarios + manifest)

core/benchmark/memory_accumulation/       (new package)
  composition.py  benchmark-owned provider factory: ProviderMemoryService
                 composed from production classes with memory_plane /
                 memory_evolution_extractor / memory_evolution_query_analyzer
                 injection (same DI shape and kwargs as the test-support
                 harness; never imports tests.support)
  runner.py       one persistent SQLite plane per world-set; provider
                 recreation at session boundaries; checkpoint evaluation
                 reusing memory_evolution_runtime pieces
  metrics.py      typed metric row models and aggregations
  artifacts.py    artifact writers (digest-covered + digest-exempt members)
  models.py       suite row models

tools/benchmark_suites/memory_accumulation.py   (new)
  registers suite id memory_accumulation_v1, profiles smoke|standard|scale,
  --profile flag; wires the benchmark-owned composition
```

Ownership boundaries:

- The simulator package owns workload truth (latent graphs, sessions,
  worlds, checkpoints). It gains no knowledge of the runtime composition.
- The benchmark package owns the provider composition, production-path
  orchestration, measurement, and artifacts. It consumes only provider-facing
  entry points, exactly as `memory_evolution_runtime` does today, and owns
  its composition explicitly rather than relying on the test-support
  harness (which remains test-only and must never be imported from shipped
  code).
- The calibration package is reused unchanged for interval machinery;
  accumulation-specific policy *values* (coverage minimums, tier ceilings)
  live in the accumulation package as declared constants; a full
  `LiveCertificationPolicy` value for this suite is added at Level 3.
- No production package under `memorii.core.memory_evolution`,
  `memorii.core.provider`, or `memorii.core.memory_plane` changes.

## Workload Contract

### Sessions

A session is a maximal group of observations sharing `session_id`,
`user_id`, and `task_id` (null `task_id` = task-global), ordered by
timestamp, bounded by declared intra-session spacing (seconds to hours).
Consecutive sessions of the same task are separated by idle gaps drawn from
a declared discrete distribution covering same-day, next-day, multi-day, and
at least one ≥14-day dormancy gap per standard world (aligning with the
existing long-horizon `dormancy`-phase stale-resurfacing pressure in
`family_observations.py`, days 92-96). Session boundaries are oracle-neutral
metadata: the runtime receives them only as the scope fields it already
accepts.

### World Sets

A world-set is 2–3 independent semantic worlds (existing family generators,
relabeled) sharing one store and one time epoch, with a minimum cross-world
temporal overlap fraction of 0.5 so interleaving pressure is real rather
than sequential. Worlds have distinct `user_id` values and distinct project
entities; a declared subset of entity names is shared across worlds as alias
pressure.

Terminology: a **standard world-set** is a world-set generated under the
`standard` profile. The `smoke` and `scale` profiles are exempt from the
dormancy-gap and `must_survive` floors; `scale` exercises the
`scale_degradation` and `restart_replay_recovery` families only. Each
world-set's horizon span (`horizon_days`) is a manifest-declared constant
per profile (defaults: smoke 30, standard 180, scale 180); a retention age
bin is *reachable* for a world-set iff it intersects `[0, horizon_days]`,
independent of where facts were placed.

**Identifier uniqueness (closed rule).** After world-scoped opaque-ID
permutation, every event id, checkpoint id, and artifact row id is globally
unique within the world-set: the world scope is embedded in the opaque id
namespace. Operation IDs therefore carry the world component explicitly:
`benchmark:accumulation:<world_set_id>:<world_id>:<event_id>`. The merged
stream is the time-ordered merge of per-world streams with total-order key
`(timestamp, event_id)`. Duplicate operation IDs or event ids within a run
are a fail-closed typed error (belt-and-braces validation on top of the
uniqueness rule), because the production idempotency contract would
otherwise silently drop the second delivery.

### Revision Chains

Single-value predicates receive chained revisions (depth 3 smoke, 5
standard) spaced across sessions and idle gaps. After each revision the
oracle expects: `current` view answers the newest eligible revision;
`historical_at` answers the revision valid at the queried time. This
exercises the production precedence tuple (effective time, source
authority, claim-ID tie-break) at depth rather than once.

### Must-Survive Facts

The world-set oracle marks a sampled set of facts `must_survive`, spread
across the declared age bins and session-distance bands with declared
floors (≥20 per standard world-set, ≥3 per reachable age bin — reachability
is defined by the world-set's `horizon_days`, not by fact placement; the
manifest declares per-bin counts and an empty reachable bin is a generator
contract violation). Later checkpoints query them. Absence of any aligned
claim at query time is a `consolidation_dropped_needed_fact` failure — the
measurement of compression/merge loss. `must_survive` membership is
oracle-side only.

### Tiers

| Tier | Observations per world-set | Modes permitted |
| ---- | -------------------------- | --------------- |
| `compact` | 10^2 (declared range) | rule, fake-oracle, live |
| `growth` | 10^3 (declared range) | rule, fake-oracle |
| `saturation` | ≥5×10^3, target 10^4 (declared range) | rule only |

Live mode is refused on `growth`/`saturation` by fail-closed cost guard
(MAB-13): scale-degradation curves measure retrieval against store growth
and do not require live extraction; memory-quality constructs are measured
live on `compact` world-sets with a bounded provider-call budget.

### Checkpoint Query Scope

Every accumulation checkpoint carries an explicit world-correct
`request_user_id`, plus `request_session_id`/`request_task_id` where the
construct requires session- or task-scoped evaluation. The single-stream
ingestion-context fallback that `memory_evolution_runtime` permits
(`runner.py:258-260`) is disallowed in the accumulation runner: in an
interleaved store an unscoped query matches every world, which would turn
the interference measurement into global-retrieval hygiene and corrupt
retention/supersession candidate pools. A contract test asserts no
accumulation checkpoint resolves to a null or cross-world scope.

## Runtime Composition And Production Entrypoint Bindings

Design-level bindings; the implementation WorkPlan must produce the
code-mapper preflight artifact proving each before its first writer edit.
The composition precedent for CI/PR-gate execution is the tests-support
runner pattern (`tests/support/run_memory_evolution_runtime_benchmark.py`);
the accumulation suite instead owns its factory in shipped package code
(`core/benchmark/memory_accumulation/composition.py`) so the registered CLI
suite is self-contained — importing `memorii.tests.support` from shipped
code is forbidden.

| Requirement | Canonical trigger and composition root | Callsite and authority | Owner chain | Proof obligation |
| ----------- | --------------------------------------- | ---------------------- | ----------- | ---------------- |
| MAB-04 | Accumulation composition module constructs `MemoryPlaneService(record_store=SqliteMemoryPlaneStore(path))` and the provider via the benchmark-owned factory (kwargs `memory_plane`, `memory_evolution_extractor`, `memory_evolution_query_analyzer`) | Factory mirrors the test-support harness DI shape using production classes only | composition → provider factory → `ProviderMemoryService` | store file survives provider recreation; `store_not_durable` fires on in-memory miscomposition; import-boundary test passes |
| MAB-01/02 ingestion | Per-observation `sync_event`/`apply_memory_write` with `benchmark:accumulation:<world_set_id>:<world_id>:<event_id>` operation IDs | Session scope passed via the existing `IngestionContext` transport | runner → ingestion helper → provider entry points | replay of an operation ID adds no records; duplicate ids fail closed |
| MAB-05..09 retrieval | Checkpoint evaluation via `provider.prefetch_result(..., reference_time=..., purpose=..., task_id=..., session_id=..., user_id=...)` with mandatory world-correct request scope | Identical public contract to `runner.py:261-272`; the ingestion-context fallback is not used | runner → provider prefetch → `retrieve_evolution_decision` | scope contract test (MAB-07); benchmark never calls internal retrieval directly |
| MAB-10 reconcile | Scheduled `provider.reconcile_memory_evolution()` at declared intervals with an injected deterministic `now_provider` | Public provider method; production precedent: the Hermes completed-turn recovery worker and the Hermes host startup recovery paths | runner → provider | seeded stuck operation (expired lease / retryable failure) is reclaimed; outcomes judged against the injected clock |
| MAB-10 restart | Provider recreation at session boundaries; durability family adds a mid-session crash point over the same SQLite store | Composition identical to initial | runner → composition | alignment across boundaries shows no semantic loss |

## Metrics And Judge Contracts

All rows are pydantic models with `extra="forbid"`, carrying the common
identity block (run identity, arm, seed, tier, world-set id, world id where
applicable, mode). A "row set" is one (run identity, arm, world-set, seed)
group.

- `RetentionCurveRow` — fact (opaque id), family, planted-at, queried-at,
  `age_days`, `sessions_since_planted`, verdict, judge id.
- `SupersessionDepthRow` — chain id, depth, revision index, view
  (`current`/`historical_at`), verdict.
- `InterferenceLeakageRow` — querying world, leaked world or null, channel
  (`selected`/`supporting`/`rejected`/`context`/`graph_edge`), item count.
- `ConsolidationSurvivalRow` — fact id, needed-at, survived, failure bucket.
- `ScaleDegradationRow` — store item count, probe set id, precision@8, mode
  (digest-covered; no timing fields).
- `ScaleTimingRow` (`scale_timing.jsonl`, digest-exempt, report-only) —
  store item count, probe set id, retrieval wall-time p50/p95, runner
  environment label.
- `DurabilityOutcomeRow` — boundary (`session_boundary`/`crash_restart`/
  `replay`/`reconcile`), outcome, record counts before/after,
  semantic-delta-empty flag, clock basis (injected).
- `WorldSetManifestRow` — worlds with fingerprints, session counts, event
  counts, gap distribution, alias-pressure list, revision-chain inventory,
  `must_survive` per-bin counts, per-bin retention fact counts, and the
  world-set `horizon_days`. The manifest is an oracle-side artifact
  and is never an input to the runtime path.

Judge reuse and extension:

- Retention, supersession, and consolidation checkpoints reuse the existing
  truth/lifecycle/temporal judges and role-aware channels unchanged.
- One new deterministic judge family, `cross_world_leakage`, fails any
  world-B content in any output channel of a world-A-scoped query and any
  cross-world identity-merge edge in the aligned graph. It receives oracle
  world membership only after runtime output, like every other judge.

## Oracle Isolation Boundary

The three-layer contract extends unchanged:

- Hidden: latent graphs, expected ids/answers, `must_survive` membership,
  world membership of hidden items, the world-set manifest.
- Exposed: surface observations (with session/user/task scope as plain
  caller metadata), visible candidate cards, checkpoint query text and
  request scope.
- Forbidden everywhere on the runtime path: `expected_*` keys, hidden
  distractor ids, world fingerprints, oracle labels.

New attack surfaces and their controls (equivalence classes for the attack
matrix):

1. Session/user/task fields smuggling oracle values — sanitized-surface
   contract tests extended to the new fields and manifest.
2. World-set manifest leaking into prompts or candidate cards — manifest is
   write-only for judges; leakage tests assert absence.
3. Opaque-ID collisions or cross-world referential breaks — world-scoped
   namespaces embedded in the opaque ids; fail-closed duplicate detection;
   metamorphic tests extend permutation invariance to interleaved sets.
4. Duplicate semantic worlds inflating live-gate sample size — the
   world-set row fingerprint is a deterministic digest over ordered member
   world fingerprints (the existing gate applies unchanged at set level);
   member-level cross-seed duplicates are excluded by generator policy
   (disjoint member-world pools per policy window) and proven by a
   deterministic manifest-audit test.
5. New artifacts embedding oracle labels readable by later runtime stages —
   artifacts are terminal outputs; pipeline-order tests assert no runtime
   stage reads benchmark artifacts.

## Statistical Gate Model

- **Units.** Aggregate live-gate unit: one `seed × world-set` collapsed
  binary — every checkpoint in the world-set must pass. Construct-family
  gate unit: the per-(`world-set` × family) all-must-pass collapse over
  that family's checkpoints, entering `seed_cluster_scenario_pass_interval`
  as the family's unit binary. Correlated checkpoints within one store
  never enter as independent units.
- **Intervals.** Every threshold decision — aggregate, per-family, and any
  live retention/consolidation threshold — uses the exact beta-binomial
  seed-cluster lower bounds with declared intraseed correlation, exactly as
  the certified suites do. Plain exact binomial bounds appear only in
  descriptive per-bin reporting (counts with intervals), never in a
  threshold decision.
- **Deterministic tiers.** Exact assertions: required pass sets per family,
  zero-tolerance buckets (`cross_world_leakage`,
  `consolidation_dropped_needed_fact` thresholds predeclared),
  digest-stable outputs. No sampling.
- **Coverage.** Family coverage uses an accumulation-specific per-seed
  minimum of world-sets containing each construct family (declared
  constant), replacing the single-suite `minimum_family_scenarios_per_seed`
  reading; the machinery is unchanged, the policy value is suite-owned.
- **Paired baselines** collapse identically (per arm) before the
  seed/scenario bootstrap.
- **Predeclared analysis discipline.** Retention bin edges, session-distance
  bands, tier thresholds, and family pass criteria are fixed before runs;
  post-run tuning invalidates the run identity, per existing certification
  rules.
- **Cadence.** PR gate: `smoke` dry-run only (compact, bounded). Scheduled
  tier: `standard` fake-oracle and (separately governed) live smoke; a
  named slow-tier job runs the `standard` profile deterministic dry-run and
  the `scale` profile dry-run — covering the `growth` and `saturation`
  tiers — with recorded budgets so the MAB-03 ceilings execute on a
  cadence, not only at implementation milestone 1.
- The full `LiveCertificationPolicy` value for this suite (seeds,
  replicates, world-sets per replicate, thresholds) is specified at
  implementation time under a Level 3 follow-up; Level 2 requires the gate
  design plus a bounded live smoke.

## Failure And Operational Analysis

- **Invalid inputs.** Unknown profile/tier/world-count, malformed session
  boundaries (overlapping, empty, non-monotonic), observation counts
  outside the declared range, live mode on `growth`/`saturation`: typed
  `AccumulationConfigError` with explicit codes; the run refuses to start.
  No truncation, no fallback tier.
- **Resource exhaustion.** Wall-clock ceilings per tier (the saturation
  ceiling is a hard typed failure with a generous bound; percentile timing
  is informational); provider-call budget for live `compact` runs; artifact
  row caps with explicit truncation markers (counts preserved). Ceiling
  breach is a typed terminal failure, never a silent partial report.
- **Partial provider failure mid-accumulation.** Provider failures follow
  the existing accounting (successes/failures/fallbacks,
  `final_output_source` `live_llm`/`fake_oracle`/`rule`, `mixed` labeling);
  a failed extraction does not abort the world-set — it is recorded and the
  affected checkpoints fail with stage attribution. A verification test
  drives a failing fake provider mid-world-set and asserts the accounting
  and stage attribution.
- **Restart semantics.** A crashed run leaves a valid SQLite store; the
  durability family recreates the provider and continues; duplicate
  operation-ID redelivery is a no-op by the existing idempotency contract.
- **Observability.** All failures carry stage buckets; the world-set
  manifest makes every world auditable; modes and provider health are
  reported per existing conventions.

## Verification Strategy

| Requirement | Deterministic evidence | Additional evidence |
| ----------- | ---------------------- | ------------------- |
| MAB-01/02 | unit tests on composition (sessions, gaps, shared-epoch overlap, alias pressure, determinism digests); metamorphic permutation tests on interleaved sets; fail-closed duplicate-id tests | manifest audits |
| MAB-03 | tier constant tests; fail-closed unknown-tier and live-on-growth/saturation tests | saturation write-path complexity-class measurement with predeclared ceiling and minimum informative range (implementation milestone 1) |
| MAB-04 | composition test: store survives provider recreation; `store_not_durable` miscomposition test; import-boundary architecture test (no `tests.support` import, no private persistence) | — |
| MAB-05/06/08 | dry-run suite runs produce rows with expected structure and labeled modes; judge-contract tests; fault-injection: seeded `must_survive` drop fires `consolidation_dropped_needed_fact` | live smoke rows labeled `live_llm` per MAB-16 purity rule |
| MAB-07 | `cross_world_leakage` judge unit tests incl. each channel and graph-edge class; leakage-contract test that world membership never precedes output; checkpoint scope contract test (no null/cross-world scope) | live smoke leakage reporting |
| MAB-09 | probe-set precision rows at tier boundaries; precision@8 threshold tests on deterministic tiers; coarse wall-time ceiling test; digest-exemption contract test for `scale_timing.jsonl` | — |
| MAB-10 | durability family tests: session-boundary recreation alignment; crash-restart + replay record-count assertions; fault-injected reconcile (expired lease via injected `now_provider`, and retryable-failure reclaim) with injected-clock judging | — |
| MAB-11 | sanitized-surface contract tests extended; hidden-item absence tests; set-level fingerprint dedup tests; member-level cross-seed manifest-audit test | — |
| MAB-12 | gate unit tests: per-family collapse units, cluster intervals, coverage minimums (reuse existing calibration test patterns) | — |
| MAB-13 | fail-closed input matrix tests (all tier×mode refusals incl. growth×live, saturation×live) | — |
| MAB-14 | row-model schema tests (`extra="forbid"`, arm discrimination, mode separation, row-set grouping, digest canonicalization); failing-provider mid-world-set accounting + stage-attribution test | — |
| MAB-15 | paired-baseline rows present, `arm`-labeled; explicit `baseline_no_solver_graph` exclusion recorded | — |
| MAB-16 | PR-gate dry-run green; fake-oracle plumbing test; live smoke executed with per-world-set `final_output_source == live_llm` purity assertions and recorded extractor mode | certification policy follow-up recorded |
| MAB-17 | digest-stability test for existing suites with accumulation code present | — |
| MAB-18 | profile-matrix constant tests; `--profile` CLI contract tests; unknown-profile fail-closed tests | — |

Identity hygiene: the `memorii.tools.identity_hygiene` coordinate
*detection vocabulary* is extended to recognize this design's
requirement-ledger family (`MAB-<nn>` spellings) in identifier, value, and
structured-key positions — today the tool does not detect them, so the
obligation is unsatisfiable without that extension. Mutation tests then
prove the full canonical set (`M1`, `M2`, `M3`, `C2`, `R22`, `SIA-R22`) plus
`MAB-01` is rejected on every new behavioral surface, while the positive
corpus (`BM25`, genuine `_v1` versions, tier observation numerals) passes.
If typed MAB traceability fields are ever added, the allowlist's
typed-traceability exception contract must be generalized beyond its
current SIA-only spelling.

## Alternatives Considered

- **Extend `memory_evolution_runtime_v1` with an accumulation profile.**
  Rejected: mutates a certified, gated suite identity mid-release and
  re-baselines its statistical unit. Kept as additive-only extension with
  digest stability instead (MAB-17).
- **Reuse the test-support provider harness as the accumulation composition
  root.** Rejected: test-support code cannot own a shipped composition
  (wheel-based PR gates exclude `tests/`); the accumulation package owns a
  mirror-image factory built from production classes (MAB-04).
- **Managed `PublishedMemoryPlaneStore` composition for the base suite.**
  Rejected for Level 2: measures signed publication as well as accumulation,
  widening the suite's blame surface; recorded as a follow-up family.
- **New judges for retention/supersession/consolidation.** Rejected:
  existing judges already score truth/lifecycle/temporal correctness; these
  constructs need aggregation and checkpoint placement, not new semantics.
  Only `cross_world_leakage` is genuinely new failure semantics.
- **Counting checkpoints (or facts) as statistical units.** Rejected:
  within-store outcomes are correlated; the all-must-pass world-set and
  per-family collapses preserve the certified machinery's unit semantics,
  and plain binomial intervals are confined to descriptive reporting.
- **Live runs at `growth`/`saturation`.** Rejected on cost; scale curves do
  not need live extraction. Fail-closed guard instead.
- **Community benchmark adoption now (Track 2 pulled in).** Rejected:
  external licensing/format decisions and adapter isolation design are
  separable and would block this track.

## Feasibility Evidence

- Session/user/task transport is implemented end-to-end today
  (`schemas.py:344-346`, `ingestion.py:124-133`, `runner.py:258-272`);
  generation is the only missing writer. The runner-level context fallback
  is empty today, which is why MAB-07 mandates explicit checkpoint request
  scope rather than relying on it.
- Persistent composition needs no change to `memorii.core.memory_evolution`,
  `memorii.core.provider`, or `memorii.core.memory_plane`:
  `MemoryPlaneService(record_store=SqliteMemoryPlaneStore(...))` plus a new
  benchmark-owned provider factory mirroring the test-support harness DI
  shape. Building that factory is the code-mapper preflight's first proof
  obligation; no shipped default factory exists today
  (`runtime_dependencies.py:88`, `runner.py:164-170`).
- `reconcile_memory_evolution()` is a public provider method with existing
  production callers in the Hermes integration (the completed-turn recovery
  worker and host startup recovery); the benchmark calls the public method
  directly and depends on no caller topology.
- The calibration machinery (seed-cluster intervals with AND-collapse,
  paired bootstrap, fingerprint dedup) is row-shape-generic and reusable
  without modification; suite-specific policy values live with the suite.
- Residual feasibility risks (recorded, not hidden): (a) SQLite-plane
  write-path cost at 10^4 observations is unmeasured — the store decodes
  current state per write batch and the reusable ingestion helper lists all
  records per observation, so the naive path is quadratic; the
  implementation's first milestone measures the complexity class with a
  predeclared ceiling, and the `saturation` floor (≥5×10^3) plus the
  Problem-Definition target prevent silent shrinking; batching ingestion is
  the anticipated remedy if needed. (b) Artifact volume at `saturation` is
  bounded by row caps with preserved counts.

## Compatibility And Migration

- Additive-only simulator changes; existing profiles' generated bytes are
  digest-stable (MAB-17 test).
- No persisted format, protocol, or workflow for existing suites changes.
  The benchmark CLI gains one suite id, one `--profile` flag, and a new
  slow-tier scheduled job running the `standard` deterministic and `scale`
  dry-runs (covering the `growth` and `saturation` tiers).
- No migration or rollback surface exists at design time; the
  implementation WorkPlan owns rollout of the new CI gate entries.

## Evidence Maturity

| Claim | State |
| ----- | ----- |
| Workload contract (sessions, worlds, tiers, chains, must-survive, scope) | specified |
| Metric and artifact row contracts (incl. arm, row sets, digest exemptions) | specified |
| `cross_world_leakage` judge contract | specified |
| Statistical gate model (units, intervals, coverage, cadence) | specified |
| Composition bindings (MAB-04, MAB-10) | derivable (all production inputs exist; the benchmark-owned factory is new benchmark code, not a production change) |
| Identity-hygiene vocabulary extension | specified (implementation required before mutation proofs can run) |
| Saturation-tier wall-time/complexity feasibility | unspecified until implementation measurement |
| Suite implementation, dry-run gate, live smoke, certification | not started |

## Limitations And Follow-Ups

- Simulated time only; real-clock soak is a recorded follow-up.
- The base composition does not exercise signed publication; managed-store
  family is a follow-up.
- Upgrade-mid-accumulation (mixed-version store) requires the durable
  migration contract to stabilize; follow-up family.
- Full live certification policy execution: Level 3 follow-up.
- Tracks 2 and 3: separate governed designs with entry criteria in the
  WorkPlan.
- Pre-existing doc divergence recorded in the WorkPlan:
  `docs/design/memory_evolution_runtime.md` describes a startup recovery
  cycle in the production composition root; `build_provider_memory_service_from_env`
  itself does not call reconcile there, while the Hermes host composition
  does run startup recovery outside the core factory.

**Announcement claims discipline.** Until implementation evidence lands,
public statements may say this design exists and is governed; they may not
cite accumulation numbers of any kind.
