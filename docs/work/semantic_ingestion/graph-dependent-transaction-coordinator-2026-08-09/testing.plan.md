# Bootstrap Graph Transaction Boundary Verification

- Work ID: `bootstrap-graph-transaction-boundary-verification`
- Work type: testing
- Status: active
- Coordinator: Codex `/root`
- Created: 2026-08-11
- Last updated: 2026-08-12
- Parent WorkPlan: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/design.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md` section 4.8.1; `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/production-entrypoint-bindings.json`; current graph V3 production and test paths
- Expected outputs: exact selector manifest and validator; dedicated CI owner/job/aggregate; measured runtime evidence; independent test and correctness review

## Objective

Make every required bootstrap graph transaction behavior mechanically traceable
from its public trigger through an exact test selector, root, backend, durable
state, CAS/effect oracle, CI owner, and aggregate result.

## Completion Contract

The operation is complete only when the committed selector/validator proves the
closed 352-tuple universe, every selector collects and passes without duplicate
generic-shard ownership, timing and timeout evidence are current, workflow and
aggregate checks enforce the manifest, identity hygiene passes, and independent
test/correctness reviewers have no unresolved approval findings.

## Scope

Included: graph V3 public-root tests and fixtures; independent-process JSONL
runner; selector schema/manifest/generator/validator; workflow ownership,
timing, and aggregate wiring. Excluded: changing graph product semantics or
weakening the approved 352-tuple contract. No cases are deferred.

## Constraints And Invariants

- Preserve the 44 requirement/scenario pairs times four roots times two
  backends exactly.
- Every executed row invokes `ProviderMemoryService.sync_event`; helper-only
  coverage is not accepted.
- Exclusions require architecture-proven semantic non-applicability.
- Independent JSONL means separate Python processes.
- Names remain behavioral; requirement IDs occur only as traceability values.

## Identity And Coordinate Hygiene

| Surface | Identity | Class | Owner/meaning | Action | Proof |
| --- | --- | --- | --- | --- | --- |
| selector file/job | `bootstrap-graph-transaction-boundary` | behavioral | exhaustive V3 transaction boundary | retain | governing design |
| row requirement values | `GTC-R09`, `GTC-R14`--`GTC-R21` | planning/evidence | traceability only | retain only in typed fields | selector validator |
| process runner/tests | graph race/reopen behavioral names | behavioral | public CAS/restart behavior | retain | identity gate |

## Change Impact And Verification Closure

| Path | Surface | Owner | Authority chain | Gates | Status |
| --- | --- | --- | --- | --- | --- |
| `memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_*.py` | tests | this plan | architecture -> selectors -> CI | focused/exhaustive | active |
| `memorii/tests/fixtures/semantic_ingestion/bootstrap_graph_v3_*` | fixture | this plan | test oracle -> public root | focused/exhaustive | active |
| `memorii/tests/ci/bootstrap-graph-transaction-boundary.json` | generated manifest | this plan | coverage table -> collection | validator/CI | implemented |
| `.github/workflows/pr-gates.yml` | workflow | this plan | manifest -> dedicated job -> aggregate | workflow contract | implemented |

## Sources Of Truth

Precedence follows root `AGENTS.md`; the governing behavior is architecture
4.8.1, with current production call paths and persisted tests used to validate
feasibility. The implementation binding ledger must match observed callers.

## Current State

Runtime behavior, root execution, restart, renewal/reclaim, writer partition,
conflict/retry/finalization, scope-revocation, and unrelated-write tests exist.
The four public roots now execute the main success, durable-retry,
resolved/exhausted-conflict, partial-commit, scope-revocation, and unrelated-
write families in memory and through independent-process JSONL reopen. The
canonical 25-scenario public matrix, generated 200-row/352-tuple manifest,
fail-closed validator, eight dedicated root/backend CI shards, and semantic-
ingestion aggregate dependency now exist. Exhaustive shard execution and
independent closure review remain.

## Assumptions And Open Questions

Verified: the required universe is 352 tuples. Working assumption: existing
behavioral tests can be consolidated behind one public matrix harness without
weakening their distinct failure signals. Unresolved: exact runtime allocation
between PR-fast samples and the required exhaustive job; measurement decides.
No external decision is currently required.

## Milestones

1. Inventory existing selectors and map each of the 44 scenario requirements.
2. Implement missing public root/backend scenario rows and independent-process
   restart cases.
3. Generate and validate the exact manifest, then wire one dedicated job and
   aggregate edge.
4. Measure, run gates, freeze, and obtain independent reviews.

## Progress Log

- 2026-08-11: Created the testing operation after runtime implementation
  reached the selector/CI boundary. Existing focused race and root evidence is
  recorded in the parent implementation WorkPlan.
- 2026-08-11: Exact graph V3 collection contains 64 tests. The mechanical
  inventory finds only `pre_cas_scope_revoked` and `unrelated_conflict` have
  complete four-root/two-backend public rows; the canonical manifest is not yet
  eligible for generation.
- 2026-08-11: Added root/backend public matrices for normal success, durable
  retry, resolved and exhausted related conflict, and partial commit. Exact
  focused collection is now 103 tests. Two representative new memory replay
  rows passed in 151.16 seconds; independently started JSONL process rows have
  passed for every implemented scenario family without second-run lane or
  executor effects.
- 2026-08-11: Extended both public matrices to coordinator removal and graph
  authority omission. The first run exposed a Found-replay defect where an
  absent graph coordinator fell through to generic source-only terminal
  recovery. The provider now preserves the mandatory V3 graph failure on
  replay; direct memory and independent-process JSONL representatives pass.
- 2026-08-11: Added public renew, same-writer reclaim, writer-changed, and
  writer-unavailable matrices. Reclaim exposed an epoch-zero-only coordinator
  guard and a fixture authorizer that trusted its precomputed compilation
  instead of the atomically reloaded plan. The coordinator now accepts only a
  fully linked current epoch, and the host authorizer derives its plan and
  attempt inputs from reloaded member bytes. Direct memory reclaim and direct
  independent-process reclaim/writer-change representatives pass.
- 2026-08-11: Completed canonical public aliases for all 25 scenarios,
  including reused-final, epoch-zero, mixed-version rejection, and rollback.
  Production-root collection is 232 tests; representative new memory and
  independent-process rows pass.
- 2026-08-11: Generated the canonical 200-row manifest whose requirement
  projection is exactly the required 352 tuples. Added mutation tests and an
  eight-shard dedicated CI owner; the semantic-ingestion aggregate now
  requires every graph transaction shard.

## Evidence Log

- Production-root suite: `16 passed in 628.45s` before the new race matrix.
- Scope revocation: four ordinary-root rows passed; independent JSONL process
  proof passed.
- Unrelated foreign write: four ordinary-root rows passed; independent JSONL
  process proof passed after fixing terminal reload forward-reference rebuild.
- Inventory: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/selector-inventory.json`.
- Current focused collection: `151 tests collected in 4.25s`.
- New memory replay sample: `2 passed, 78 deselected in 151.16s`.
- Coordinator removal/authority omission regression sample: `2 passed, 94
  deselected in 96.63s`.
- Lease reclaim memory sample: `1 passed, 127 deselected in 71.87s`.
- Independent-process reclaim/writer-change sample: `2 passed, 126 deselected
  in 162.95s`.
- Mixed-version and rollback samples: memory `2 passed, 142 deselected in
  129.13s`; independent-process JSONL `2 passed, 142 deselected in 186.23s`.
- Canonical alias samples: `2 passed, 230 deselected in 198.92s`.
- Selector validator and CI-topology tests: `6 passed in 6.57s`.
- Canonical in-memory boundary: all four 25-row shards passed (100 rows);
  direct `1401.00s`, factory `1384.00s`, filesystem `1397.20s`, Hermes
  `1393.16s`.
- Canonical independent-process JSONL boundary: all four 25-row shards passed
  (100 rows); direct `1730.49s`, factory `1730.35s`, filesystem `1730.37s`,
  Hermes `1730.80s`.
- Exact manifest projection: 200 public selectors, zero exclusions, 352 unique
  requirement/scenario/root/backend tuples.
- Focused graph contract/store/coordinator/terminal/fixture closure: `21 passed
  in 5.70s` after migrating the final stale V38/V40 unit fixtures.
- Current v80 direct-memory shard: all 25 manifest selectors passed in
  `3468.59s`.  This current accepted-effect path invalidates the historical
  2100-second budget while remaining below a measured 4200-second dedicated
  slow-exhaustive budget.  The workflow timeout is now 90 minutes, preserving
  1200 seconds of headroom.  Selector count, warning mode, public roots,
  backends, 352-tuple universe, and aggregate receipt validation are unchanged.
- Field-aware identity hygiene now permits `GTC-R*` values only at
  `rows[*].requirement_ids[*]` in the canonical selector manifest.  The same
  value in `node_id` or any other identity-bearing field still rejects.  The
  complete identity suite passed (`150 passed in 26.62s`) and the repository
  identity scan passed.

## Decision Log

- Use one generated exhaustive manifest and one dedicated owner job; do not add
  the slow rows to generic unit shards.

## Review Log

- 2026-08-11: Frozen-v2 test review rejected closure. Confirmed findings:
  generic unit-shard overlap and no receipt owner; CI count selection was not
  manifest-driven; named lost-ack/reuse/rollback/mixed-version rows were
  behavior aliases without discriminating failure signals. The manifest-driven
  runner, exclusive unit-shard exclusion, deterministic owner budget, per-shard
  receipts, and eight-receipt aggregate are implemented; lifecycle and
  migration scenario remediation remains.

## Blockers And Limits

No external blocker or accepted runtime limitation.

## Current Exact Next Action

Validate the updated 4200-second receipt budget and 90-minute workflow timeout
with the selector/topology tests, freeze the test-architecture delta, and run a
targeted independent test review.  The discriminating lost-ack, reuse-arm,
terminal-locator, rollback, and mixed-version scenarios are implemented and
the manifest is current.

## Outcome And Retrospective

Active; no completion claim.
