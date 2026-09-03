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

## Process Note (user direction 2026-09-02)

Before kicking off any expensive gate: verify the working tree is at the
intended final revision and no pending fix is likely to move it — the
CE-9 rerun launched one revision before its own fix landed and was
stopped at ~10% as wasted time.  Every gate launch in this operation
records `git rev-parse HEAD` + `git status --short` immediately before
the command starts.

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

## Phase 2 — The Fix Design (v2, from the measured CE-9 baseline)

Measured post-optimization serial baseline (CE-9 gate, `c9995a1`, load
~8): **4h24m** for 4,076 nodes (pre-optimization 8h15m; quiet-machine
expectation ~2.5-3.5h). Loaded composition estimate:
`test_bootstrap_graph_production_roots` ~120-140m (race ~60-75m
including ~23m of 200 subprocess spawn/import tax; in-memory replay
~35-45m; other families ~15m), `semantic_terminal_persistence`
~25-35m, other `semantic_ingestion` ~25-35m, `tools` ~45-55m, core
misc ~10-15m. CI facts: `production_roots` is ignored by the 4 file-
scope shards and has no dedicated PR job — its cost is local-only; the
durations artifact regenerates via `memorii.tools.test_shards`.

**Target: 15-45 minutes wall for the complete local suite.**

### L1 — Parallel local execution (the primary lever)

`pytest-xdist` (dev dependency via `uv`; not yet installed) with
workers ≈ physical cores. Two distribution modes, decided by an
equivalence experiment, not assumption:

- `--dist loadfile` mirrors the CI shard semantics exactly (whole
  files per worker, in-file order preserved) — but its wall clock is
  capped by the largest single file: `production_roots` (~130m) would
  alone exceed the target.
- `--dist load` (per-node) splits the parametrized matrices across
  workers (the 100-node race and replay families become ~8-12m each),
  which is where the target is reachable — but it requires intra-file
  parallel safety, which the CI shard structure does not prove.

Design: **(a)** split `test_bootstrap_graph_production_roots.py` into
per-family modules — a pure mechanical move (same nodes, same bodies,
retention map is the identity map; behavioral file names: race-reopen,
scenario-replay, root-composition families) which also unblocks CI
file-scope shard balance; **(b)** run the full suite serially and under
both xdist modes at the same quiet revision and require identical
results (and identical failures) before adopting a mode; per-node
`tmp_path` isolation already holds for both subprocess families.
Expected wall from 264m serial: **~35-55m** at 8 workers.

### L2 — Race-family process batching

Extend the test-owned
`tests.fixtures.semantic_ingestion.bootstrap_graph_v3_process_runner`
to accept a batch manifest (list of scenario/root/phase triples) and
emit one JSON array: ~200 interpreter+import launches (~6.8s each,
~23m) collapse to ~8-16. The per-scenario 180s timeout is preserved
per batch element (the runner enforces it internally); outputs remain
per-scenario and the test's assertions are unchanged. Expected: -20m
serial, -5-8m wall under L1, and lower timeout flakiness under
parallel load.

### L3 — Conditional: tools attribution + session fixtures

Only if the measured wall after L1+L2 exceeds 45m: attribute the
~45-55m `tools` block (scenario runner, CTV reference compiler,
traceability manifest), apply session-scoped derivation for stateless
fixtures, and verify placement against the PR-gate owners. No coverage
change without a retention map.

### L4 — Timing-evidence regeneration

Regenerate `tests/ci/unit-test-durations.json` from a `--junitxml` run
via the existing `memorii.tools.test_shards merge` flow — this also
closes the known identity-hygiene finding (124 stale structured keys)
and re-balances the CI shard config against the split files.

### Budget table (post-L1+L2, 8 workers, quiet ~load 4)

| Block | Serial (quiet est.) | Wall under L1+L2 |
| --- | --- | --- |
| Split race family | ~45-55m | ~8-12m |
| Split replay family | ~30-40m | ~6-9m |
| terminal persistence + other SI | ~45-60m | ~8-12m |
| tools | ~40-50m | ~8-11m |
| collection overhead ×8 workers | — | ~2-3m |
| **Total** | ~2.5-3.5h | **~30-45m** |

### Guardrails

- No assertion, family, threshold, or coverage change; the file split
  proves node-identity (count + names) before and after.
- The serial command remains available and equivalent (results must
  match the parallel run at the same revision).
- CI structure stays authoritative; local changes document command
  equivalence against the shard config; the split rebalances it.
- Determinism preserved: no wall-clock or sleep dependencies; xdist
  must not change outcomes (the equivalence experiment is the gate).

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
- 2026-09-02 (lever-1 feasibility): the project venv carries no `pip`
  (uv-managed environment — reviewer tooling bootstrap created an
  `uv.lock` during the milestone review, since removed as noise), so
  adding pytest-xdist is a dev-dependency change through `pyproject` +
  `uv`, not an ad-hoc install; the spike is recorded as blocked on that
  normal dependency decision rather than availability.  The CE-9 broad
  gate now running provides the post-optimization serial baseline this
  design's Step 0 needs; a pre-optimization attribution curiosity is
  also recorded: three test files failed collection at the prior
  campaign's closed revision `21dcaf3` (clean worktree-proven) from a
  stale private import, so the durations artifact's provenance for those
  nodes predates the public rename.

## Next Action

Run the independent `test_reviewer` and `correctness_reviewer` passes
on this design (the coherent topology change), then implement in
order: the production_roots file split (L1a, pure move), the xdist
equivalence experiment and runner (L1b — needs the pytest-xdist
dev-dependency addition via uv, user-approved), race batching (L2),
and durations regeneration (L4); L3 only if the measured wall exceeds
45m.
