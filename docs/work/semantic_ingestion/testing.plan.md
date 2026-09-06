# Semantic Ingestion Test And CI Topology

- Work ID: semantic_ingestion_testing
- Work type: testing
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-08-03
- Last updated: 2026-08-04
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: None
- Canonical inputs: `.github/workflows/pr-gates.yml`; `unit-test-durations.json`; `docs/development/static_tooling.md`; `docs/design/semantic_ingestion_architecture.md`
- Expected outputs: non-duplicative required-job ownership, current collection pins, measured timing ownership, workflow contract tests, and revision-bound verification evidence

## Objective

Give every M4 test one intentional required-job owner while retaining exhaustive
coverage, restoring accurate collection and timing evidence, and keeping PR
gates within measured budgets.

## Completion Contract

Complete only when the live M4 test inventory has one documented required-job
owner per proof, accidental duplicate collection is removed, workflow counts
and timing data match the candidate revision, each required local command
passes, the aggregate workflow includes every intended job, and independent
correctness and test review has no unresolved required finding.

## Scope

Included: M4 temporal and conflict-attention test placement, selector and count
pins, duration inventory, required-job topology, workflow structure contracts,
and the current static helper import failure.

Excluded: product-semantic changes, weakened assertions or warning modes, live
provider certification, and unrelated suites. Product defects return to the
parent implementation WorkPlan or a linked debugging WorkPlan.

Deferred: final GitHub-hosted evidence until a reviewed revision is available.

## Constraints And Invariants

- Preserve family-complete deterministic coverage.
- Keep fast gates representative rather than exhaustive.
- Avoid duplicate expensive proof across broad shards and dedicated jobs.
- Use exact workflow cwd, warnings, environment, and arguments.
- Use one writer for overlapping workflow, timing, and test artifacts.
- Preserve behavioral naming and identity hygiene.

## Identity And Coordinate Hygiene

| Surface | Proposed or existing identity | Class | Behavioral owner or protocol meaning | Retain, rename, migrate, or reject | Proof |
| ------- | ----------------------------- | ----- | ------------------------------------ | --------------------------------- | ----- |
| workflow job | `semantic-ingestion-generation` | behavioral identity | generated-authority and semantic integration proof | retain after selector audit | workflow contract |
| proposed job | `semantic-projection-history` | behavioral identity | temporal projection, migration, and restart proof | validate before adoption | identity gate and workflow contract |

## Change Impact And Verification Closure

| Path or pattern | Surface class | Intended scope owner | Authority chain | Required gates | Status |
| --------------- | ------------- | -------------------- | --------------- | -------------- | ------ |
| `.github/workflows/pr-gates.yml` | workflow or gate | this WorkPlan | tests -> selectors -> jobs -> aggregate | workflow structure tests | candidate green |
| `unit-test-durations.json` and `semantic-terminal-persistence-test-durations.json` | timing artifacts | this WorkPlan | node -> duration -> disjoint shard plans | shard planner | candidate complete |
| `memorii/tests/**` selectors | test | this WorkPlan | requirement -> node -> required job | collection and execution | inventory complete |

## Sources Of Truth

Apply `AGENTS.md` precedence. Governing designs define required behavior, the
live workflow and collected node IDs define execution, and measured durations
define budget decisions.

## Current State

Verified on 2026-08-03 before the topology change:

- `semantic-ingestion-generation` collected 637 cases while pinning 295.
- Its selector duplicated 603 unit nodes already owned by broad unit shards.
- The six temporal/history families collect 81 cases: projection history 14,
  scheduler 11, policy migration 28, identity lineage 7, graph planning 6, and
  identity prerequisites 15.
- The final candidate broad selector collects 3,025 cases after excluding the
  six temporal files, the 156-case terminal-persistence owner, and the 13-case
  provider-compatibility unit owner. Its 4-way file-granular plan measures
  2,778 nodes and estimates a 494.479-second maximum shard against a 600-second
  target.
- The dedicated terminal-persistence selector collects and measures all 156
  cases. Its 7-way exact-node plan estimates every shard between 523.112 and
  523.233 seconds against the same 600-second target.
- `tools.extract_provider_compatibility_fixture` exists and imports correctly
  from the workflow's `memorii` working directory. Its tracked ownership and
  historical-fetch boundary are preserved unchanged.

## Assumptions And Open Questions

- Verified: the candidate path selectors have zero cross-job intersection.
- Verified: a 600-second runtime budget plus 300 seconds of timeout headroom
  covers every measured generic and terminal-persistence shard estimate.
- Open: none about selector ownership.
- External decisions: none currently.

## Test Portfolio

| Requirement or contract | Behavior and canonical path | Test owner and level | Failure signal | Status |
| ----------------------- | --------------------------- | -------------------- | -------------- | ------ |
| projection history | current, historical, contested, restart, corruption | `semantic-projection-history` | wrong view or accepted corruption | moved, 14 cases |
| projection scheduling | deterministic trust decay | `semantic-projection-history` | wrong due-set or order | moved, 11 cases |
| policy migration | catch-up, cutover, late arrival, restart, rollback | `semantic-projection-history` | partial cutover or wrong recovery | moved, 28 cases |
| identity and planning | lineage, bootstrap authority, graph planning | `semantic-projection-history` | wrong identity or unauthorized prefix | moved, 28 cases |
| core temporal and conflict | pure decisions, repositories, clarification | `unit-test-shards` | contract or state-machine failure | retained once |
| provider compatibility | frozen/current reader, schema, and historical recapture compatibility | `provider-compatibility` | incompatible public bytes or reader behavior | retained once, 13 unit plus recapture integration cases |
| terminal persistence | semantic terminal writes, replay, reopen, and immutable projection generation | `semantic-terminal-persistence` | lost, duplicated, or corrupt durable terminal state | moved intact, 156 cases |
| conflict persistence and replay | process, restart, concurrency, integration wiring | `semantic-ingestion-generation` | lost or unauthorized durable state | retained once, 34 integration cases total |

## Equivalence And Failure Matrix

Retain applicable positive, malformed, authorization, retry, replay,
concurrency, interruption, migration, rollback, compatibility, and restart
families. Map each family to one canonical test owner before moving a node.

## Suite Topology And Runtime Budget

The candidate owns 84 exact cases in `semantic-projection-history`, 34 exact
integration cases in `semantic-ingestion-generation`, 156 exact cases in
`semantic-terminal-persistence`, and 3,025 cases in broad unit shards. Every
selector uses `-W error` for execution and disables the pytest cache provider.
The before/after semantic-generation count is 637 to 34; the before/after
unit/generation intersection is 603 to zero. The dedicated temporal and
terminal-persistence files are excluded from broad shards, so their
intersections are also zero.

## Test Asset Inventory

Inventory fixtures, helpers, clocks, stores, trust material, and restart
harnesses for the temporal modules, including production-package isolation.

## Retention And Retirement Ledger

| Classification | Families | Replacement or unique signal |
| -------------- | -------- | ---------------------------- |
| moved | projection history, scheduler, migration, lineage, planning, prerequisites | exact 84-case `semantic-projection-history` owner |
| retained | semantic/core conflict and temporal unit tests | broad shards own contract and state-machine behavior |
| moved | terminal persistence | exact 156-case, 7-way `semantic-terminal-persistence` owner |
| retained | pipeline, process safety, conflict persistence, replay integration | exact 34-case generation integration owner |
| retained | benchmark contract and artifact families | benchmark/oracle/artifact evaluation is distinct from durable ingestion behavior |
| removed duplicate execution | 603 unit nodes formerly selected by generation | identical nodes remain in broad shards; no assertion deleted |
| obsolete | none | no tests deleted or weakened |

## Gate Change Log

Candidate gate change: add `Semantic Projection History`; reduce generation to
integration-only selection; exclude the moved six files from unit shards; and
add the fail-closed `Semantic Ingestion` umbrella over generation, scenario,
acceptance, and projection-history jobs. `Unit Tests` remains the umbrella for
static analysis, package smoke, provider recapture, four file-granular shards,
the seven-shard terminal-persistence owner, and both timing inventories.
`Benchmark Contracts` is unchanged because its retained tests have unique
benchmark, oracle, artifact, and evaluation signals.

## Milestones Or Experiments

1. Inventory exact node ownership, overlap, counts, durations, workflow argv,
   and aggregate dependencies. Status: complete except final timing capture.
2. Implement one non-duplicative topology and current pins. Status: complete;
   history is pinned at 84, terminal persistence at 156, and both generic and
   dedicated shard plans verify below the 600-second target.
3. Run exact required gates and coherent review. Status: complete; the final
   focused batch is green and both independent delta reviews approve closure
   with no remaining finding.

## Delegation And Cost Ledger

| Phase | Bounded task | Role and model tier | Writer or read-only | Why this tier | Output or evidence | Status |
| ----- | ------------ | ------------------- | ------------------- | ------------- | ------------------ | ------ |
| inventory | Map selectors, overlap, counts, and aggregate ownership | two explorers, Spark-class | read-only | Mechanical workflow mapping | node-to-job map | complete |
| triage | Measure focused commands and isolate the helper failure | coordinator tooling | read-only | Small discriminating evidence | timing and causal signature | complete |
| implementation | Change selectors, timing, contracts, and workflow | worker, Terra-class | sole writer | Coherent CI mutation | candidate diff and focused proof | complete |
| review | Review topology and proof sufficiency | correctness_reviewer and test_reviewer, Terra-class | read-only | Independent approval judgment | classified findings | complete, no remaining findings |

## Progress Log

- 2026-08-03: Separated substantial M4 CI topology from product implementation
  and recorded the initial Spark inventory and triage evidence.
- 2026-08-03: Recorded the exact zero-overlap retention map and implemented the
  candidate selectors, owner ledger, aggregate, structure contracts, and docs.
- 2026-08-04: Recollected the live candidate selectors after the debugging
  changes: broad unit shards collect 3,184 nodes, generation collects 34, and
  projection history remains 81 with pairwise intersections of zero. Began a
  fresh 598-node M4 broad-unit timing capture, but did not merge it because two
  deterministic product/golden failures made the run non-green.
- 2026-08-04: Resumed after both linked debugging failures closed. Fresh sorted
  collection is broad 3,187, generation 34, and projection history 84, with
  zero pairwise intersections. The history delta is three new identity-lineage
  regression cases, invalidating the prior 81-case execution evidence and pin.
- 2026-08-04: The current broad-owned M4 file inventory collects 601 nodes
  across 17 files. The fresh capture will partition those files without overlap
  and will merge evidence only after every serial partition exits green.
- 2026-08-04: Stopped the first serial timing partition immediately after
  `test_real_terminal_updates_publish_immutable_projection_generations_after_reopen`
  failed. A current temporal projection returned by `current_temporal(...)`
  had `valid_interval=None`, so the test could not order projections by interval
  start. The stopped run recorded 84 passes and one failure in 1,183.00 seconds;
  its timing artifact is rejected and no later partition ran.
- 2026-08-04: The linked temporal-projection interval debug completed with the
  exact current/historical/checkpoint/reopen regression and sibling families
  green. Resumed topology collection; no rejected timing artifact will be
  reused.
- 2026-08-04: Fresh cache-free collection confirmed broad 3,187, generation 34,
  and projection history 84 with zero pairwise intersections. Sorted node-ID
  fingerprints are broad `869715d8e159931b84ffed76b032fe7b6a15dd62ef5c115757d3dc4548cb5fd1`,
  generation `3d26aa03dfda146ed4c3a24bce00d5b2cf0a7f2874beee228eddd2608c10d4de`,
  and projection history
  `7ce7329018433f984f136aff8818c6766056cfb9f5f8554ed6049d337a37f482`.
  Pairwise intersection fingerprints are the canonical empty-list digest
  `01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b`.
- 2026-08-04: The invalidated dedicated projection-history owner passed all 84
  nodes in 503.89 seconds with `-W error`, cache disabled, and fail-fast. Per
  file: projection history 14, scheduler 11, policy migration 28, identity
  lineage 10, graph planning 6, and identity prerequisites 15.
- 2026-08-04: Fresh broad-owned M4 collection contains 601 nodes in 17 files.
  The checked timing inventory has exact entries for 157 and lacks 444. The
  fresh capture covers all 601 rather than only missing nodes. Its two dominant
  terminal-persistence partitions each collect 78 nodes; the remaining three
  partitions use disjoint whole files. All execute serially with fail-fast and
  one shared fresh plan digest.
- 2026-08-04: Broad timing partition 0 passed 78/78 in 1,996.04 seconds. Its
  artifact has exit status zero, 78 positive durations, the fresh plan digest,
  and 1,993.736 seconds of recorded node time. Because the shard planner keeps
  modules intact, this half-file measurement alone exceeds the current
  600-second broad-shard target; complete the capture before deciding topology.
- 2026-08-04: Broad timing partition 1 passed 78/78 in 1,670.95 seconds. Its
  artifact has exit status zero, 78 positive durations, the fresh plan digest,
  and 1,668.356 seconds of recorded node time. The full terminal-persistence
  module therefore records 3,662.092 seconds across 156 nodes; the slowest node
  is the exact immutable-generation reopen regression at 218.635 seconds.
- 2026-08-04: Broad timing partition 2 passed 43/43 in 496.67 seconds. Its
  artifact has exit status zero, 43 positive durations, the fresh plan digest,
  and 494.479 seconds of recorded node time; the slowest node records 54.907
  seconds.
- 2026-08-04: Broad timing partition 3 passed 109/109 in 189.16 seconds. Its
  artifact has exit status zero, 109 positive durations, the fresh plan digest,
  and 187.027 seconds of recorded node time; the slowest node records 30.823
  seconds.
- 2026-08-04: Broad timing partition 4 passed 293/293 in 9.07 seconds. The five
  M4 artifacts cover exactly 601 nodes with zero duplicates, missing nodes,
  extras, failed statuses, stale digests, or nonpositive durations and record
  4,349.974 seconds total.
- 2026-08-04: Fresh whole-module planning failed closed at 3,662.092 seconds
  for terminal persistence against the 600-second target. A first candidate
  changed every broad shard to exact-node assignment and expanded the matrix
  from four to nine; architecture review rejected that blast radius. The
  converged candidate restores the generic 4-way file-granular owner and moves
  only terminal persistence to a dedicated 7-way exact-node owner. Assignment
  scope is explicit in configuration and defaults to `file`.
- 2026-08-04: Final selector and plan verification collected 3,025 broad nodes
  and 156 terminal-persistence nodes with zero intersection. The broad manifest
  has 2,778 positive entries and estimates four shards at 371.876-494.479
  seconds. The dedicated manifest has all 156 positive entries and estimates
  seven shards at 523.112-523.233 seconds. Both plans pass the 600-second
  verifier without timeout inflation.
- 2026-08-04: Testing review found the provider-compatibility unit file still
  duplicated in broad shards and an older CTV workflow contract pinned to the
  pre-terminal aggregate. The remediation assigns all 13 provider unit nodes
  solely to `provider-compatibility`, removes their broad timings, updates both
  aggregate contracts, and adds a live-collection partition proof over the
  complete unit corpus.
- 2026-08-04: Testing review also found timing evidence accepted a missing
  `exit_status` and exact terminal cardinality was only relationally asserted.
  The remediation requires integer zero status, adds CLI rejection for missing
  status/index/digest metadata, pins literal seven-shard and 156-node contracts,
  and proves terminal-manifest equality with current collection.
- 2026-08-04: Shard-planner and workflow-structure contracts passed 22/22 in
  1.11 seconds. The exact semantic-ingestion generation owner passed 34/34 in
  14.22 seconds with `-W error`, cache disabled, and fail-fast.

## Evidence Log

- Spark inventory: pre-change generation 637; unit/generation overlap 603;
  dedicated temporal family 81; candidate generation 34.
- Final generic shard plan: 3,025 collected, 2,778 measured, four file-level
  shards estimated at 371.876-494.479 seconds against 600 seconds.
- Final terminal-persistence plan: 156 collected and measured, seven node-level
  shards estimated at 523.112-523.233 seconds against 600 seconds.
- Final sorted selector fingerprints are generic broad
  `38cda5b19823e5684ad89a83f1e5307bdd3e0bc288736d64564a03922a5ca2af`,
  terminal persistence
  `917ed5ca11dd09a559d3c8daf4486539b237ca2881352ca1cef2f8135d459eb5`,
  generation
  `3d26aa03dfda146ed4c3a24bce00d5b2cf0a7f2874beee228eddd2608c10d4de`,
  and projection history
  `7ce7329018433f984f136aff8818c6766056cfb9f5f8554ed6049d337a37f482`.
  The generic/terminal intersection is empty; generation and projection-history
  remain disjoint from the generic owner through their exact path exclusions.
- Final focused remediation gate: shard planner, workflow structure, and CTV
  workflow authority passed 48/48 in 142.64 seconds with warnings as errors and
  pytest cache disabled. Both planners verify, Ruff is clean, targeted Pyright
  reports zero errors, and the scoped diff check is clean.
- Fresh broad timing attempt: part 1 passed 161/161 in 119.10 seconds and part
  3 passed 144/144 in 5.57 seconds. Part 2 failed 1/140 after 583.21 seconds
  because the frozen public JSONL whole-file digest changed from
  `94f0b866...` to `201cbdb2...` while wire/member digests still matched. Part
  0 failed `test_sequential_rekeys_reuse_logical_identity_without_reservation_collision`
  (`identity_lineage_compilation_failed`) and was stopped after 75 passes and
  792.58 seconds. No timing artifact from this run was merged.
- Resumption selector fingerprints over sorted LF-delimited node IDs: broad
  `869715d8e159931b84ffed76b032fe7b6a15dd62ef5c115757d3dc4548cb5fd1`,
  generation `3d26aa03dfda146ed4c3a24bce00d5b2cf0a7f2874beee228eddd2608c10d4de`,
  and projection history
  `7ce7329018433f984f136aff8818c6766056cfb9f5f8554ed6049d337a37f482`.

## Decision Log

- 2026-08-03: Use Spark for inventory and triage, one Terra writer for mutation,
  and Terra reviewers once per coherent candidate.
- 2026-08-03: Use path-disjoint ownership: broad shards for unit contracts,
  projection-history for the six exhaustive temporal families, and generation
  for integration-only persistence/process/replay proof.
- 2026-08-03: Retain all benchmark families because their oracle, artifact,
  alignment, and evaluation signals are not duplicated by M4 storage tests.
- 2026-08-04: Do not expand the checked duration-manifest schema with a source
  revision in this testing slice. Current-tree collection equality, exact
  plan-digest/index/status shard artifacts, and this WorkPlan's capture
  provenance establish local evidence; committed-head GitHub artifact evidence
  remains deferred until a reviewed revision exists.

## Review Log

- Architecture review: `Not applicable / changes_required / architecture` on
  the rejected global 9-way node-shard candidate. Confirmed and resolved by the
  dedicated 7-way terminal owner and restored 4-way file-level generic owner.
- Correctness review: no findings on the dedicated-boundary candidate.
- Test review: four `Not applicable / changes_required / verification`
  findings covering a stale aggregate contract, 13 duplicated provider nodes,
  fail-open missing timing metadata, and insufficient literal/exact terminal
  assertions. All are confirmed; remediation is implemented and pending delta
  review.
- Test review: `P3 / follow_up / verification` for config-omission coverage of
  the file-level default. Accepted and implemented in the same bounded patch.
- Correctness and test delta reviews: no remaining findings; closure approved.

## Blockers And Limits

Budget: two coherent topology candidates and one bounded remediation round.
All three deterministic failures discovered by earlier timing attempts and all
confirmed review findings are resolved. No current product blocker is known.
GitHub-hosted required-check evidence remains deferred until a reviewed
revision is available and does not block local testing-plan closure.

## Next Action

Return control to the parent M4 implementation WorkPlan with this completed
testing topology and evidence.

## Outcome And Retrospective

Active; no outcome yet.
