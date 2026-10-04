# Memory Accumulation Benchmark Design

- Work ID: memory-accumulation-benchmark-design
- Work type: design
- Delivery fidelity: Level 2 (early real-world testing)
- Status: complete
- Coordinator: main Codex thread
- Created: 2026-10-02
- Last updated: 2026-10-02
- Parent WorkPlan: None
- Related WorkPlans: durable-memory-implementation (provides the durable store
  composition this design depends on), durable-runtime-design,
  hermes-conversation-memory-trial
- Canonical inputs: `AGENTS.md`, `.agents/PLANS.md`,
  `docs/design/latent_graph_simulator.md`,
  `docs/design/memory_evolution_runtime.md`,
  `docs/design/memory_evolution_runtime_benchmark.md`,
  `docs/design/benchmark.md`, `docs/design/semantic_temporal_retrieval.md`,
  `docs/design/memory_lifecycle_benchmark_v1.md`,
  `memorii/memorii/core/benchmark/memory_evolution_runtime/runner.py`,
  `memorii/memorii/core/benchmark/memory_evolution_runtime/ingestion.py`,
  `memorii/memorii/core/benchmark/memory_evolution_sim/` (generation, schemas,
  judges, checkpoints, metrics),
  `memorii/memorii/core/benchmark/calibration/policy.py`,
  `memorii/memorii/core/memory_plane/service.py`,
  `memorii/memorii/core/provider/service.py`,
  `memorii/memorii/core/persistence/factory.py`
- Expected outputs: `docs/design/memory_accumulation_benchmark.md` (canonical
  design), this WorkPlan

## Objective

Produce an approved canonical design for a memory-accumulation benchmark
(`memory_accumulation_v1`) that measures Memorii's production memory plane
under long-running operation: many sessions against one persistent store,
belief revision at depth, multiple users/projects interleaved in one store,
store growth, and durability across restarts, replay, and periodic
reconciliation.

When this operation succeeds, an implementation WorkPlan can be created from
the design alone, without hidden conversational context.

### Position In The Long-Running Evals Roadmap

The owner approved a three-track long-running-task evals plan on 2026-10-02.
This design operation covers Track 1 only:

1. **Track 1 (this design)** — long-horizon accumulation benchmark extending
   the latent-graph simulator and runtime harness.
2. **Track 2 (deferred, separate design)** — community-benchmark
   comparability adapter (LongMemEval-style multi-session QA). Entry
   criteria: Track 1 deterministic + fake-oracle gates green; external
   dataset licensing and format decision recorded.
3. **Track 3 (deferred, separate design)** — agent-level task-utility
   ablation on real host harnesses. Mandated separate by
   `docs/design/memory_evolution_runtime.md` ("An agent-system evaluation
   must be designed and approved separately"). Entry criteria: Track 1 live
   smoke evidence; host-integration readiness per
   `docs/plans/agent_integration_readiness.md`.

## Completion Contract

The design is complete only when the Design Completion Contract in
`.agents/PLANS.md` (Work Type: Design) is satisfied and recorded here, at
Level 2 fidelity, with:

- every requirement in the design's ledger having a stable ID and measurable
  acceptance criteria
- the identity ledger covering every proposed durable surface, with the
  field-aware identity-hygiene enforcement strategy stated
- three independent reviewers (`spec_auditor`, `correctness_reviewer`,
  `test_reviewer`) having reviewed one frozen candidate, all findings
  classified per the AGENTS.md finding-classification contract, and no
  validated P1/P2 design defect or unresolved `blocks_approval` /
  `changes_required` finding remaining
- a final whole-design review recorded

Writing the document is not completion evidence by itself.

## Scope

### Included

- Design of `memory_accumulation_v1`: workload generation (session structure,
  world-set interleaving, revision chains, scale tiers), runtime harness
  composition over a persistent store, metric and judge contracts,
  statistical gate model, artifact contract, failure/fail-closed behavior,
  verification strategy.
- Additive simulator extension design (new composition layer; existing
  families and profiles unchanged).
- Oracle-isolation boundary for every new surface.

### Excluded

- Track 2 and Track 3 (separate linked design operations; entry criteria
  above).
- Any production memory-semantics change (decay/forgetting policy, new
  retrieval ranking, new lifecycle states). The benchmark measures existing
  behavior; it does not add memory behavior.
- Full live certification policy execution for the new suite (Level 3
  follow-up; the gate *design* is in scope, its 40-seed execution is not).
- Real-clock soak testing (simulated time only in scope; real-clock soak
  recorded as follow-up).

### Explicitly Deferred

- Upgrade-mid-accumulation (mixed-version store) family — requires the
  durable-release migration contract to stabilize first.
- Managed `PublishedMemoryPlaneStore` composition family — the base suite
  composes `SqliteMemoryPlaneStore`; the signed-publication view is a
  recorded follow-up family once the base suite exists.

## Constraints And Invariants

- Universal Memorii invariants (`AGENTS.md`) apply, especially: production
  retrieval isolated from benchmark oracle data; candidate state distinct
  from committed state; no model output mutates committed truth without
  validation.
- Simulator three-layer contract (`docs/design/latent_graph_simulator.md`):
  hidden latent graph / surface observations / deterministic judges; LLM
  never truth or judge; oracle fields never reach the runtime path.
- Runtime boundary (`docs/design/memory_evolution_runtime.md`): the
  benchmark consumes only provider-facing entry points (`sync_event`,
  `apply_memory_write`, `prefetch_result`/`retrieve_evolution_decision`,
  `reconcile_memory_evolution`); it must not bypass the provider decision
  boundary.
- Evidence classes stay distinct: deterministic / fake-oracle / live;
  fake-oracle results are never provider success.
- Statistical gates may not be weakened to pass; new gates must state their
  data-generating assumptions.
- Existing certified suites (`memory_evolution_sim_v1`,
  `memory_evolution_runtime_v1`) must be unaffected: additive-only simulator
  changes, digest-stable outputs for existing profiles.
- Identity hygiene: no planning/evidence coordinate in any behavioral or
  protocol identity; `memorii.tools.identity_hygiene` enforcement extended to
  new surfaces.

## Identity And Coordinate Hygiene

Requirement IDs (`MAB-*`) are traceability values only. Proposed durable
identities, all behavioral:

| Surface | Proposed identity | Class | Behavioral meaning | Action |
| --- | --- | --- | --- | --- |
| Suite ID (CLI + registry) | `memory_accumulation_v1` | protocol | benchmark suite measuring memory accumulation; `_v1` genuine suite version | new |
| Design doc | `docs/design/memory_accumulation_benchmark.md` | behavioral | canonical design for the suite | new |
| Sim composition module | `memorii/core/benchmark/memory_evolution_sim/accumulation.py` | behavioral | world-set/session composition over existing family generators | new |
| Runtime suite package | `memorii/core/benchmark/memory_accumulation/` | behavioral | suite runner, metrics, artifact rows | new |
| Suite runner registration | `memorii/tools/benchmark_suites/memory_accumulation.py` | behavioral | suite entry in the benchmark CLI | new |
| Suite profiles | `smoke`, `standard`, `scale` | behavioral | accumulation workload scale/shape variants | new |
| Scale tiers | `compact` (10^2), `growth` (10^3), `saturation` (10^4) observations | behavioral | store-size ladder | new |
| Construct families | `retention_across_idle_gaps`, `supersession_depth`, `cross_world_interference`, `consolidation_survival`, `scale_degradation`, `restart_replay_recovery`, `periodic_reconciliation` | behavioral | workload family names fed to the family gates | new |
| Artifact files | `accumulation_checkpoint_results.jsonl`, `retention_curve.jsonl`, `interference_results.jsonl`, `scale_degradation.jsonl`, `durability_results.jsonl`, `world_set_manifest.json` | behavioral | typed artifact members | new |
| Metric row models | `RetentionCurveRow`, `SupersessionDepthRow`, `InterferenceLeakageRow`, `ConsolidationSurvivalRow`, `ScaleDegradationRow`, `DurabilityOutcomeRow`, `WorldSetManifestRow` | behavioral | typed artifact row contracts | new |
| New judge family | `cross_world_leakage` judge | behavioral | deterministic judge failing cross-world channel contamination | new |
| New failure buckets | `consolidation_dropped_needed_fact`, `cross_world_leakage`, `store_not_durable` | behavioral | stage-attribution buckets | new |
| Typed config error | `AccumulationConfigError` | behavioral | fail-closed profile/tier/scope/ceiling refusals | new |
| Composition module | `memorii/core/benchmark/memory_accumulation/composition.py` | behavioral | benchmark-owned provider factory from production classes only | new |
| Suite typed contract | `AccumulationWorldSet` | behavioral | world-set scenarios + manifest contract emitted by the simulator composition | new |
| CLI flag | `--profile` (values `smoke`/`standard`/`scale`; tier derived from profile) | protocol | suite CLI surface | new |
| Timing artifact | `scale_timing.jsonl` + `ScaleTimingRow` (digest-exempt, report-only) | behavioral | wall-time reporting separated from digest-covered artifacts | new |
| Arm values | `memorii`, `transcript_only`, `flat_retrieval` | behavioral | row discriminator separating Memorii from baseline arms | new |
| Operation-ID prefix | `benchmark:accumulation:<world_set_id>:<world_id>:<event_id>` | behavioral | idempotent replay identity with explicit world scope (round-1 fix) | new |

Durability test: every name above is derivable from the measured behavior
alone; none references this WorkPlan, a milestone, or a review round.
Mutation coverage obligation (extends `memorii.tools.identity_hygiene`):
representative planning-coordinate mutations (`M1`, `R22`, `MAB-01` used as
file/symbol/artifact names) must be rejected on every new surface;
legitimate numerals (`_v1`, tier observation counts) must pass.

## Change Impact And Verification Closure

This operation changes documentation only (this WorkPlan and the design
doc). No production code, tests, fixtures, workflows, or generated artifacts
change; therefore no authority chains or gates are affected at design time.
The implementation WorkPlan will own the changed-surface, authority-chain,
and gate ledgers for code changes.

Pre-existing observation (not silently fixed, out of scope):
`docs/design/benchmark.md` "Planned runtime-backed suite" section describes
`memory_evolution_runtime_v1` as planned although it is implemented — stale
current-state text discovered during baseline exploration on 2026-10-02.

Concurrent-change note (2026-10-02): during this operation the working tree
additionally showed `memorii/tests/unit/core/test_runtime_command_dispatch.py`
modified alongside the release operation's `runtime_api.py`/
`runtime_repository.py` edits (same runtime-command-dispatch boundary).
Verified unrelated to this design operation; left untouched.

## Sources Of Truth

Precedence per `AGENTS.md`. For this design:

1. `docs/design/memorii_spec.md` (core architecture)
2. `docs/design/latent_graph_simulator.md` (simulator contract)
3. `docs/design/memory_evolution_runtime.md` (runtime as-built)
4. `docs/design/memory_evolution_runtime_benchmark.md` (existing runtime suite)
5. `docs/design/benchmark.md` (harness/gates)
6. `docs/design/semantic_temporal_retrieval.md` (retrieval boundary)
7. Code and tests listed in Canonical inputs (as-built authority when docs
   are stale)

Owner direction given in conversation on 2026-10-02 (three-track evals plan,
Track 1 first) is the scope authority; it is recorded here because it is not
otherwise durable in the repository.

## Current State

Verified facts (direct code inspection, 2026-10-02):

- The runtime harness creates a fresh in-memory plane per scenario:
  `runner.py:193` (`memory_plane = MemoryPlaneService()`).
- Session/user/task plumbing exists end-to-end but is never populated by
  generators: `SurfaceObservation` carries `session_id/user_id/task_id`
  (`memory_evolution_sim/schemas.py:344-346`), `IngestionContext` transports
  them (`memory_evolution_runtime/ingestion.py:15-27,124-133`), checkpoints
  carry `request_*` scope with ingestion fallback (`runner.py:258-272`).
- `MemoryPlaneService.__init__(*, record_store=...)` accepts an injected
  store; `SqliteMemoryPlaneStore` and `JsonlMemoryPlaneStore` exist
  (`core/memory_plane/service.py:69-72`, `core/memory_plane/sqlite_store.py`).
- `ProviderMemoryService.reconcile_memory_evolution()` exists
  (`core/provider/service.py:2807`); the runtime design says long-lived
  shared stores should schedule it; nothing benchmarks it today.
- Mutating provider entry points are idempotent under stable operation IDs;
  the benchmark already uses `benchmark:runtime:<event_id>`
  (`ingestion.py:92,104`).
- Live certification machinery (seeds/replicates/scenarios, beta-binomial
  seed-cluster intervals, paired baseline bootstrap, world-fingerprint
  dedup) is implemented in `core/benchmark/calibration/` and enforced in
  `.github/workflows/benchmark-scheduled.yml` scheduled runs.
- Existing horizon ceiling: `long_horizon` profile reaches simulated day
  120, ≤60 events per scenario, one world per store, store size tens of
  records.
- The durable release added managed persistent partitions
  (`core/persistence/factory.py`: `PublishedMemoryPlaneStore` over
  `SqliteMemoryPlaneStore`, signed publication protocol) — available for a
  later composition family; deferred per Scope.
- The shipped CLI has no default provider factory: `BenchmarkRuntimeDependencies`
  defaults `memory_evolution_provider_factory` to `None`
  (`tools/benchmark_suites/runtime_dependencies.py:88`) and the runner
  raises without it (`runner.py:164-170`); the only existing implementation
  is test-support code (`memorii/tests/support/`), so the accumulation suite
  must own its composition (round-1 review finding SA-1/CR-4).
- Pre-existing doc/code divergence (recorded, not fixed here):
  `docs/design/memory_evolution_runtime.md` states the production
  composition root runs one recovery cycle at startup; the framework-neutral
  root `build_provider_memory_service_from_env` has no reconcile call —
  production reconcile callers are the Hermes completed-turn recovery worker
  (`core/semantic_ingestion/hermes_completed_turn_runtime.py`) and the
  Hermes host startup paths (`integrations/hermes_provider.py`
  `start_semantic_ingestion`; `integrations/hermes_factory.py` startup
  recovery, default-on). Round-2 review corrected an earlier "sole caller"
  misclaim of this inventory.

Interpretation (separate from facts): the accumulation benchmark requires no
new production memory semantics; every gap is generation-side (session
structure, world interleaving, scale), harness-side (persistent store,
restart, reconcile), or measurement-side (metrics, judges, gates).

## Assumptions And Open Questions

Verified facts: listed under Current State.

Working assumptions:

- SQLite-plane performance is sufficient for the `saturation` tier (10^4
  observations) within a bounded deterministic CI job; to be confirmed by a
  feasibility measurement in the implementation WorkPlan's first milestone
  (a discriminating experiment with a wall-time ceiling).
- Live-mode cost for accumulation quality constructs can be bounded by
  capping live worlds (small event counts) while scale/latency curves run in
  rule/dry-run modes where extraction mode does not affect retrieval
  behavior.

Unresolved questions (design records a position; none blocks approval):

- Exact retention-curve bin edges (design proposes defaults; implementation
  may tune within the recorded contract).
- Whether `periodic_reconciliation` belongs in the base suite or a separate
  profile (design: base suite, family-gated).

Decisions requiring external input: none currently. Track 2 dataset choice
and Track 3 host scope are future operations' decisions, not this design's.

## Milestones

1. **Baseline and ledgers** — problem, verified baseline, requirements and
   identity ledgers. Method: direct code inspection + explorer report
   reconciliation. Status: complete (evidence: Current State, design doc
   ledgers).
2. **Contract boundaries and feasibility** — workload contract, oracle
   isolation, statistical model, composition roots; feasibility evidence
   from verified code facts. Status: complete (evidence: design doc
   sections; Feasibility Evidence).
3. **Verification and attack model** — requirement-to-evidence matrix,
   attack families, identity-hygiene mutations. Status: complete (evidence:
   design doc Verification Strategy).
4. **Draft design** — `docs/design/memory_accumulation_benchmark.md`.
   Status: complete.
5. **Independent review and convergence** — frozen candidate, three
   reviewers, classification, bounded remediation. Status: complete
   (rounds 1 and 2 recorded in the Review Log; round-2 verdicts: approve,
   approve, changes_required → conformance corrections + folded P3s applied).
6. **Final review and completion** — spec_auditor delta review of the
   corrected candidate; closure records. Status: complete (round 3 verdict:
   approve; closure record below).

## Progress Log

- 2026-10-02 · Created WorkPlan from owner-approved three-track direction;
  explored baseline (read-only explorer + direct verification of runner,
  ingestion, persistence, policy code); classified fidelity Level 2; scoped
  to Track 1 with Tracks 2/3 entry criteria. Next action: draft the design
  doc.
- 2026-10-02 · Drafted `docs/design/memory_accumulation_benchmark.md`
  (requirements MAB-01..MAB-17, workload/metrics/gate contracts, identity
  ledger, verification strategy, alternatives, feasibility evidence).
  Next action: freeze candidate and dispatch reviewers.
- 2026-10-02 · **Final whole-design review (round 2).** correctness and
  test reviewers approved with all round-1 findings closed; spec_auditor
  found the SA-5 remediation had introduced a new "sole caller" misclaim
  (Hermes host startup also calls reconcile) plus two P3 wording items.
  Applied the conformance correction (accurate caller set; narrowed
  divergence; boundary rule: no caller-topology exhaustiveness claims) and
  folded all round-2 P3s (standard-world-set definition, reachable-bin
  definition via `horizon_days`, failing-provider matrix row, slow-tier
  canonical phrasing, completed MAB-18 matrix). Next action: spec_auditor
  delta verdict on the corrected candidate.
- 2026-10-02 · **Remediation round 1.** Reconstructed the statistical-contract
  boundary (units = seed×world-set aggregate + per-(world-set, family)
  collapse; plain binomial confined to descriptive reporting; coverage
  minimums; tier cadence), the composition/bindings boundary (benchmark-owned
  provider factory in shipped package code; test-support import forbidden;
  correct kwargs; reconcile caller corrected), and the identifier-uniqueness
  boundary (world scope embedded in opaque ids and operation IDs; fail-closed
  duplicate detection). Added MAB-18 (profile matrix + CLI surface), explicit
  checkpoint request-scope contract, fault-injection verification rows,
  live-purity rule, digest-exempt timing artifact, `arm` row discriminator,
  and all folded P3 corrections. Next action: final whole-design review.
- 2026-10-02 · Candidate frozen (see freeze record); identity-hygiene scan
  clean over the repo root including both new artifacts. Dispatched
  `spec_auditor`, `correctness_reviewer`, `test_reviewer` in parallel against
  the frozen identity. Next action: reconcile findings per the AGENTS.md
  classification contract.

- 2026-10-02 · **Round 3 delta + closure.** spec_auditor approved the
  corrected candidate (both round-2 findings closed at root cause; all
  round-1 verdicts re-verified); its one new P3 (`WorldSetManifestRow`
  field summary) was folded. Design completion contract satisfied and
  recorded; WorkPlan marked complete at Level 2. Next action: none
  (linked implementation WorkPlan is a separate operation).

## Evidence Log

- 2026-10-02 · Direct reads: `runner.py` (fresh plane per scenario at :193;
  checkpoint request-scope fallback at :258-272), `ingestion.py`
  (IngestionContext :15-27; per-observation scope transport :124-133;
  operation-ID idempotency :92,104), `memory_plane/service.py` (:69-72 store
  injection), `provider/service.py` (:2807 reconcile), `persistence/factory.py`
  (managed partition + PublishedMemoryPlaneStore), `calibration/policy.py`
  (LiveCertificationPolicy structure).
- 2026-10-02 · Explorer report (read-only, reconciled against the direct
  reads above; discrepancies none): horizon ceiling day 120 / ≤60 events /
  one world per store; session fields never populated by generators;
  baseline families list; statistical thresholds; rule-simulated baselines.
- 2026-10-02 · Design doc frozen-candidate review evidence: recorded under
  Review Log when available.

Final closure record (design operation, 2026-10-02):

```yaml
base_revision: f7d8a745920e856c675b77428d9290cd746b221a
reviewed_revision: f7d8a745 (working tree; the two reviewed artifacts are
  new untracked files, not yet committed — see outcome note)
tested_revision: not_applicable (documentation-only design operation; no
  code, tests, fixtures, or generated artifacts changed)
tested_tree_digest: not_applicable (same reason)
tree_state: dirty — four files modified by the concurrent durable-memory
  release operation (hermes trial doc, runtime_api.py, runtime_repository.py,
  test_runtime_command_dispatch.py), all explicitly out of scope and
  recorded; two untracked artifacts owned by this operation
changed_surface_inventory_complete: true
scope_delta_resolved: true (one concurrent-change discovery reconciled and
  recorded, not adopted)
authority_chains_complete: not_applicable (no derived artifacts or gates
  depend on a documentation-only change)
required_local_jobs: [identity-hygiene scan per AGENTS.md invocation]
passed_local_jobs: [identity-hygiene scan exit 0, run three times (freeze,
  post-remediation, post-correction) and independently reproduced once by
  the spec_auditor reviewer]
known_local_failures: []
failure_exclusions: []
workflow_identities: [] (no workflow changes)
ci_event: not_applicable (no CI-affecting change; docs-only)
ci_executed_sha: not_applicable
ci_executed_ref: not_applicable
remaining_validated_p1_p2: []
remaining_blocks_approval: []
remaining_changes_required: []
local_ci_parity: not_applicable
acceptance_gate_inventory: [spec_auditor approve (round 3 delta),
  correctness_reviewer approve (round 2), test_reviewer approve (round 2);
  all round-1 and round-2 finding families closed and verified]
github_run_urls: []
pr_head_sha: not_applicable
pr_base_sha: not_applicable
merge_base_sha: not_applicable
required_checks_green: not_applicable
```

## Decision Log

- 2026-10-02 · **Scope = Track 1 only.** Alternatives: one design covering
  all three tracks (rejected: Track 3 is mandated separate by
  `memory_evolution_runtime.md`; Tracks 2/3 carry external unknowns that
  would force blocked status); design nothing, publish roadmap only
  (rejected: owner asked for a governed design; Track 1 has no external
  dependencies). Consequence: Tracks 2/3 entry criteria recorded here.
- 2026-10-02 · **Fidelity Level 2.** The benchmark must exercise the real
  durable production path end-to-end (persistent SQLite store, restart,
  replay) across happy scenarios and common operational failures. Deferred
  to Level 3: full live certification execution, managed-store family,
  real-clock soak, upgrade-mid-stream family.
- 2026-10-02 · **New suite rather than extending
  `memory_evolution_runtime_v1`.** Alternatives: add an `accumulation`
  profile to the existing suite (rejected: changes a certified, gated suite
  identity and its statistical unit mid-release; existing dry-run/cert
  artifacts would need re-baselining). Consequence: additive-only simulator
  extension with digest-stability requirement (MAB-17).
- 2026-10-02 · **Base composition uses `SqliteMemoryPlaneStore` via
  `MemoryPlaneService(record_store=...)`, not the managed
  `PublishedMemoryPlaneStore`.** The base suite measures memory
  accumulation, not publication signing; the managed composition is a
  recorded follow-up family. Revisit if reviewers demonstrate the
  accumulation claims depend on signed publication behavior.

## Review Log

### Round 1 (2026-10-02) — full review of the coherent draft

Reviewers: `spec_auditor` (SA-1..9), `correctness_reviewer` (CR-1..8),
`test_reviewer` (TR-1..9), all against the frozen candidate
(f7d8a745 + working tree; scope MAB-01..17, Level 2, Track 1). All three
returned `changes_required`; none returned `blocks_approval`.

Coordinator dispositions (duplicates merged; every finding's cited evidence
was validated against direct code reads):

| Finding | Summary | Disposition | Eligibility |
| ------- | ------- | ----------- | ----------- |
| SA-1 + CR-4 (part) | composition root undefined; feasibility text claimed the test-support harness was reusable shipped machinery; kwargs imprecise | confirmed (P2) | eligible_p1_p2 |
| CR-1 | checkpoint request-scope undefined for interleaved world-sets; empty-context fallback yields unscoped queries, corrupting four construct families | confirmed (P2) | eligible_p1_p2 |
| CR-2 + TR-1 | family gate unit undefined; "exact binomial bounds" for retention thresholds contradicts the beta-binomial cluster contract | confirmed (P2) | eligible_p1_p2 |
| CR-3 + TR-7 | wall-time fields in digest-covered artifacts break digest stability; absolute-latency thresholds flaky on CI; heavy tiers lacked a cadence | confirmed (P2) | eligible_p1_p2 |
| TR-2 | vacuous proofs: reconcile/consolidation could pass with behavior absent; no fault-injection rows; partial-provider-failure and import-boundary rows missing | confirmed (P2) | eligible_p1_p2 |
| TR-3 | live-smoke purity: `mixed`-source runs could satisfy the `live_llm` claim | confirmed (P2) | eligible_p1_p2 |
| TR-5 | "world-scoped unique event id" ambiguity + world-less operation-ID prefix → silent data loss via idempotent no-op on collision | confirmed (P2) | eligible_p1_p2 |
| SA-2 | contradiction: calibration "reused unchanged" vs "dedup gate extended to world sets" | confirmed (Not applicable, identity/statistical governance) | contract_conformance_action |
| SA-3 + TR-8 | profiles `smoke|standard|scale` undefined; `AccumulationWorldSet` and CLI flags unledgered; digest-determinism scope unstated | confirmed (Not applicable) | contract_conformance_action |
| TR-4 | identity-hygiene tool cannot detect `MAB-*` spellings today; design narrowed the canonical mutation set | confirmed (Not applicable, identity-governance) | contract_conformance_action |
| SA-4 | "dormant-fact-resurfacing family" misclaim (real construct: dormancy phase, days 92-96) | confirmed (P3) | record_only (folded into revision) |
| SA-5 + CR-4 (part) | reconcile "used by production composition root at startup" misclaim; doc/code divergence unrecorded | confirmed (P3) | record_only (folded; divergence recorded in Current State) |
| SA-6 | WorkPlan cited nonexistent `benchmark.yml`; `schemas.py` lines off by one | confirmed (P3, this WorkPlan's own defect) | record_only (fixed) |
| SA-7 + TR-9 (part) | MAB-13 omitted growth-tier live refusal | confirmed (P3) | record_only (folded) |
| SA-8 | undeclared measurement parameters (session-distance bands, must_survive sampling, provider-recreation cadence conflict) | confirmed (P3) | record_only (folded as declared defaults) |
| SA-9 | missing explicit `baseline_no_solver_graph` exclusion (benchmark.md §15.5) | confirmed (P3) | record_only (folded) |
| CR-5 | reconcile determinism requires injected `now_provider` for expired-lease reclaim | confirmed (P3) | record_only (folded into MAB-10) |
| CR-6 | saturation risk should name quadratic amplifiers; measure complexity class; predeclare minimum informative tier range | confirmed (P3) | record_only (folded into MAB-03/Feasibility) |
| CR-7 | world time-base/overlap undeclared; [90,∞) bin reachability | confirmed (P3) | record_only (folded into MAB-02/05) |
| CR-8 | WorkPlan Next Action section stale vs progress log | confirmed (Not applicable, governance) | contract_conformance_action (fixed) |
| TR-6 | baseline rows indistinguishable from Memorii rows; "row set" undefined | confirmed (P3) | record_only (folded: `arm` field + row-set definition) |
| TR-9 (part) | MAB-01 task_id nullability unstated | confirmed (P3) | record_only (folded) |
| — | unsupported findings | none | — |

Resulting actions: one bounded remediation round (same writer) reconstructing
three semantic boundaries per the build-design skill — (a) statistical
contract (units, interval families, coverage, cadence), (b) composition and
bindings ownership, (c) identifier-uniqueness/operation-ID rule — plus the
folded P3 corrections, a new MAB-18 (profile matrix and CLI surface), and
fault-injection verification rows. No new requirements beyond MAB-18;
no external decision required.

### Round 2 (2026-10-02) — final whole-design review of the remediated candidate

Reviewers: all three, fresh, against the remediated artifacts (identity
re-verified, hygiene scan exit 0). Verdicts: `correctness_reviewer` approve
(8/8 round-1 findings closed, 0 new); `test_reviewer` approve (9/9 closed,
5 new P3 follow-ups NF-1..NF-5); `spec_auditor` changes_required (8/9
closed; SA-5 not fully closed — the remediation's "current sole production
caller" wording was a new misclaim of the same class: the Hermes host
integration also calls reconcile at startup).

Coordinator dispositions:

| Finding | Summary | Disposition | Eligibility |
| ------- | ------- | ----------- | ----------- |
| spec NF-1 + TR NF-5 | "sole production caller" reconcile misclaim (4 design + 1 WorkPlan locations); divergence note too broad | confirmed (Not applicable, verification accuracy) | contract_conformance_action |
| spec NF-2 | "standard world(-set)" undefined, colliding with the `standard` profile name | confirmed (P3) | record_only (folded: defined in World Sets; smoke/scale exemptions and scale family scope stated) |
| TR NF-1 | failing-provider accounting test absent from the verification matrix | confirmed (P3) | record_only (folded into MAB-14 matrix row) |
| TR NF-2 | "reachable age bin" undefined → vacuous audit risk | confirmed (P3) | record_only (folded: reachability defined by manifest `horizon_days`, independent of fact placement) |
| TR NF-3 | slow-tier job described in profile terms once, tier terms once | confirmed (P3) | record_only (folded: canonical phrasing in both places) |
| TR NF-4 | profile matrix axes incomplete for smoke/scale | confirmed (P3) | record_only (folded: MAB-18 matrix completed incl. families, seeds, world-sets, horizons) |
| spec narrative | round-1 freeze record listed 3 of 4 dirty files | confirmed (governance) | contract_conformance_action (round-2 freeze record carries the 4-file inventory) |

Boundary rule applied (second confirmed finding on the as-built-claims
boundary): no more exhaustiveness claims about production caller topology
from partial searches — the design now states the verified caller set and
depends on no caller topology; the divergence note is narrowed to the
specific factory-vs-doc mismatch. Per the review cadence contract this is a
bounded conformance correction plus folded P3s with no material contract
change, so the follow-up is a single-role delta review (spec_auditor), not
a third full cohort.

Candidate freeze record (round 2, 2026-10-02):
- reviewed artifacts: `docs/design/memory_accumulation_benchmark.md` and
  this WorkPlan, working-tree state on `f7d8a745`
- scope: MAB-01..MAB-18, Level 2, Track 1 only
- out of scope (complete dirty-tree inventory): `docs/design/hermes_conversation_memory_trial.md`,
  `memorii/memorii/core/persistence/runtime_api.py`,
  `memorii/memorii/core/persistence/runtime_repository.py`,
  `memorii/tests/unit/core/test_runtime_command_dispatch.py` — all owned by
  the concurrent durable-memory release operation
- focused checks: identity-hygiene scan exit 0 (re-run after remediation);
  no code checks applicable to a documentation-only change

## Blockers And Limits

- Iteration budget: two full review rounds plus bounded delta remediation;
  beyond that, stop and record the exact blocker.
- No code changes in this operation; all runtime claims are design-level
  with production-entrypoint binding plans (see design doc), to be proven by
  the implementation WorkPlan's code-mapper preflight.

## Next Action

None — the WorkPlan is complete. The next repository action belongs to a
separate linked implementation WorkPlan (`$implement-design` against
`docs/design/memory_accumulation_benchmark.md`), to be created on owner
request. Follow-up obligations are recorded under Outcome And Retrospective
and in the design's Limitations section.

Candidate freeze record (round 1, 2026-10-02):
- reviewed artifacts: `docs/design/memory_accumulation_benchmark.md` and this
  WorkPlan, at working-tree state on top of revision `f7d8a745`
- scope: MAB-01..MAB-17, Level 2, Track 1 only
- out of scope (explicitly excluded from review): the three modified files
  `docs/design/hermes_conversation_memory_trial.md`,
  `memorii/memorii/core/persistence/runtime_api.py`,
  `memorii/memorii/core/persistence/runtime_repository.py` — in-flight work
  of the separate durable-memory release operation
- focused checks: identity-hygiene scan
  (`memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json`
  from `memorii/`) exited 0 with no violations; no code checks applicable to
  a documentation-only change
- no writer active on the reviewed artifacts at dispatch

### Round 3 (2026-10-02) — spec_auditor delta review of the corrected candidate

Scope: the round-2 conformance corrections plus folded P3s only (no
material contract change), per the review-cadence contract. Verdict:
**approve** — both round-2 findings closed at root cause; all nine round-1
closure verdicts re-verified; folded items clean; identity-hygiene scan
independently reproduced (exit 0); one new non-blocking finding.

| Finding | Summary | Disposition | Eligibility |
| ------- | ------- | ----------- | ----------- |
| spec NF-delta-1 | `WorldSetManifestRow` field summary omitted `horizon_days` and per-bin retention fact counts mandated by the Workload Contract and MAB-05 | confirmed (P3, verification) | record_only (folded: both fields added to the row summary) |

Final state: zero validated P1/P2 design defects; zero remaining
`blocks_approval` or `changes_required` findings across all three charters
(correctness: approve, round 2; test: approve, round 2; spec: approve,
round 3 delta).

## Outcome And Retrospective

**Final result.** The `memory_accumulation_v1` design (Track 1 of the
owner-approved long-running evals plan) is approved at Level 2 fidelity.
No unresolved validated design gaps remain under the recorded scope,
sources, and review method. Approval covers the design contract only; it
is not production approval, and no implementation, benchmark result, or
live evidence exists yet.

**Evidence.** Canonical design `docs/design/memory_accumulation_benchmark.md`
(requirements MAB-01..MAB-18 with measurable acceptance criteria; workload,
metrics, judge, statistical-gate, oracle-isolation, and fail-closed
contracts; production-entrypoint binding plan with code-mapper obligations;
identity ledger; verification strategy with fault-injection and
identity-hygiene mutation coverage). Review evidence: two full independent
review rounds plus one delta round (26 round-1 + 7 round-2 + 1 round-3
findings, every one dispositioned; all confirmed families closed and
re-verified by the reviewers). Identity-hygiene scan green at every freeze.

**Remaining limitations.** Saturation-tier write-path feasibility is
unmeasured (implementation milestone 1 measures the complexity class);
managed-store composition, real-clock soak, upgrade-mid-stream, and full
live certification are recorded Level 3 follow-ups; Tracks 2 and 3 are
separate future designs with entry criteria recorded here.

**Follow-up work.**
1. Implementation WorkPlan (`$implement-design`) for MAB-01..MAB-18; its
   first milestone is the saturation complexity-class experiment and the
   code-mapper preflight for the composition bindings.
2. Extend `memorii.tools.identity_hygiene` coordinate vocabulary to
   `MAB-<nn>` spellings before the mutation proofs (designated
   implementation prerequisite).
3. Track 2 design when entry criteria are met; Track 3 design thereafter.
4. Pre-existing doc staleness for a docs owner: `benchmark.md` "Planned
   runtime-backed suite" section; `memory_evolution_runtime.md` startup
   recovery wording (both recorded in Current State).

**Lessons for future operations.**
- Reviewer-verified fact-checking caught two generations of caller-topology
  misclaims on the same boundary; the durable rule (now recorded in the
  Review Log) is to state verified caller sets, never exhaustiveness claims
  from partial searches.
- The two-round cadence with folded P3s plus a single-role delta review
  converged within budget without a third full cohort; the boundary-rule
  trigger (two findings on one semantic boundary → reconstruct) worked as
  designed on the statistical, composition, and as-built-claims boundaries.
- The design's biggest feasibility unknown (SQLite write-path scaling) is
  now framed as a predeclared complexity-class experiment with a minimum
  informative tier range, so tuning pressure cannot silently shrink the
  measurement.
