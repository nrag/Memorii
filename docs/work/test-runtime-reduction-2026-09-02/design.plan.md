# Test Runtime Reduction Design WorkPlan

- Work ID: `test-runtime-reduction-2026-09-02`
- Work type: `testing`
- Status: `active`
- Coordinator: sole writer (main thread)
- Created: 2026-09-02
- Last updated: 2026-09-02
- Parent WorkPlan: none (user direction 2026-09-02: "reduce the test
  running time to about 30 mins (give or take 15)")
- Related WorkPlans:
  - `../semantic-ingestion-canonical-member-reuse-2026-09-01/implementation.plan.md`
    (the delivery-path optimization whose CE-9 broad gate provides this
    design's post-optimization serial baseline)
- Canonical inputs: `memorii/tests/ci/unit-test-durations.json` (4,052
  nodes, 8.26h serial pre-optimization); `.github/workflows/pr-gates.yml`
  (unit-test-shards matrix: 4 shards, file-scope assignment, 600s target,
  15-min timeouts; heavy files routed to dedicated jobs);
  `memorii/tools/test_shards` (the merge/split tooling).
- Expected outputs: a reviewed test-architecture change bringing the
  serial-equivalent local full-suite runtime to ~15-45 minutes with no
  coverage weakening, plus regenerated timing evidence.

## Objective

Reduce the locally experienced full-suite runtime from the 8h15m
pre-optimization serial baseline (post-optimization serial expected
~2.5-4h, to be confirmed by the linked operation's CE-9 broad gate) to
approximately 30 minutes ±15, without weakening any assertion, family,
threshold, or gate.

## Phase 1 — Measured Baseline And Cost Attribution

Pre-optimization serial attribution (durations artifact):

| Cost center | Duration | Share |
| --- | --- | --- |
| `tests/unit/core/semantic_ingestion` total | 442.6m | 89% of 8.26h |
| `test_bootstrap_graph_production_roots.py` | 279.9m | 56% |
| — `test_graph_race_reopens_in_an_independent_jsonl_process` (100 nodes) | 151.9m | subprocess: 2 interpreter launches per node (first + reopen), each paying full package import |
| — `test_graph_scenario_replays_without_effects_in_memory` (100 nodes) | 91.3m | delivery-shaped; measured 1.93x under host load from the optimization branch (5.4x pure-delivery quiet) |
| `test_semantic_terminal_persistence.py` | 84.6m | dedicated CI job; attribution pending |
| `tests/unit/tools` family | ~45m | partial optimization benefit (mostly arena-less) |
| Everything else | ~12m | |

CI structure facts: the unit suite already runs as 4 file-scope
duration-balanced shards plus dedicated jobs for the excluded heavy files;
`assignment_scope: file` is the sanctioned isolation boundary; the
durations artifact is regenerated per CI run by `memorii.tools.test_shards`.

## Phase 2 — Levers, Sized And Ordered

1. **Local parallel execution at the sanctioned isolation boundary**
   (pytest-xdist, `--dist loadfile`, `-n` ≈ physical cores): mirrors the
   CI shard semantics exactly (whole files per worker, in-file order
   preserved); per-test `tmp_path` storage isolation already holds for
   the subprocess and replay families. Expected wall ≈ serial/6-8 for
   the CPU-bound portion; subprocess families partially serialize on
   child processes. This lever alone plausibly reaches the 30±15 target
   from a ~2.5-4h serial base. Cost: one dev dependency, one runner
   entry point, an isolation-verification pass, and a documented
   CI-parity statement.
2. **Race-family process batching**: extend the test-owned
   `tests.fixtures.semantic_ingestion.bootstrap_graph_v3_process_runner`
   to accept multiple (scenario, phase) pairs per invocation, amortizing
   ~200 interpreter+import launches down to ~8-16. Saves ~50-70m serial
   and relieves parallel CPU contention; also reduces the CI dedicated
   job's time. Per-node 180s subprocess timeouts preserved per batch.
3. **Conditional census-driven suite work** (only if the target is still
   missed): `test_semantic_terminal_persistence` (84.6m) and the tools
   family (~45m) attribution, session-scoped fixture derivation, and —
   only behind a case-by-case retention map proving class equivalence —
   any matrix reduction. No assertion, family, or threshold weakening.

## Phase 3 — Contract And Guardrails

- No coverage weakening anywhere; any proposed matrix change requires a
  retention map and discriminating-failure proof per the design-tests
  contract.
- The 4-shard CI structure and its dedicated jobs remain authoritative;
  local changes must document command-equivalence against them.
- The durations artifact is regenerated after material test moves via
  the existing `memorii.tools.test_shards` merge flow.
- Deterministic behavior preserved: no wall-clock, sleep, or ambient
  randomness dependencies introduced; xdist distribution must not change
  any test's outcome (verified by a full pass/fail comparison).
- Identity hygiene: no planning-coordinate names in new runner scripts,
  jobs, or fixtures.

## Completion Contract

- Post-optimization serial baseline recorded (from the linked CE-9 gate).
- The local full-suite command runs the complete corpus in ~15-45 min
  wall with identical pass/fail results and no deselected nodes.
- Isolation verification: a parallel run's results equal the serial
  run's at the same revision.
- Timing evidence regenerated; WorkPlan records before/after counts and
  durations; reviewers (`test_reviewer`, `correctness_reviewer`) pass
  with `remaining_validated_p1_p2: []`.

## Progress Log

- 2026-09-02: opened. Phase 1 attribution recorded from the durations
  artifact and `pr-gates.yml`; the race family's two-subprocesses-per-node
  structure confirmed in the test source.

## Next Action

Wait for the linked operation's CE-9 broad gate to record the
post-optimization serial baseline, then implement lever 1 (xdist
loadfile runner + isolation verification) as the first slice.
