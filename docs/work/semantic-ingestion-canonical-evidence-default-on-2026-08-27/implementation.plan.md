# Canonical-Evidence Default-On Enablement Implementation WorkPlan

- Work ID: `semantic-ingestion-canonical-evidence-default-on-2026-08-27`
- Work type: `implementation`
- Status: `active`
- Coordinator: sole writer (main thread)
- Created: `2026-08-27`
- Parent WorkPlan:
  `../semantic-ingestion-validated-canonical-closure-2026-08-17/implementation.plan.md`
  (this operation delivers its performance milestone's enablement leg and the
  H8 remediation its linked debug operation confirmed)
- Related WorkPlans:
  - `../semantic-ingestion-canonical-evidence-production-performance-2026-08-16/debug.plan.md`
    (H1-H9 hypotheses; H8 confirmed, H7 dominant-cost, H9 disproves
    exact-reference reuse)
  - `../semantic-ingestion-legacy-path-removal-2026-08-26/implementation.plan.md`
    (paused at its slice-5 WIP boundary pending this operation)
- Canonical inputs:
  - `docs/design/semantic_ingestion_validated_canonical_closure.md`
  - `docs/design/semantic_ingestion_canonical_evidence_performance.md` (M3.1
    certification contract)
  - User decisions of 2026-08-27 (below)
- Expected outputs: substitution enabled for every verified runtime; a small
  diametric parity gate on a slow cadence; the duplicate Step-2 lifecycle work
  removed; fresh production-bound profiling that scopes the remaining
  persistence-composition cost.

## User Decisions (2026-08-27)

1. The canonical-evidence substitution (the cache) is ON by default for every
   verified runtime; an explicit switch remains for rollback and the parity
   gate.
2. Validation strategy: fewer than ten diametric ON/OFF parity tests on a
   slow GitHub cadence (roughly every few hours); every other test runs with
   the cache ON. No cross-test purge machinery is expected (arenas are
   per-operation and released in `finally`); verify, don't assume.
3. The duplicate prepare-and-publish (debug H8) is fixed now.
4. The persistence-composition churn (debug H7) is addressed after
   re-profiling with the cache ON and H8 fixed — scope it from fresh numbers,
   not from the superseded cumulative attribution (debug H4).

These decisions amend the rollout contract in
`docs/design/semantic_ingestion_validated_canonical_closure.md` ("private
disabled-by-default rollout"); the amendment is recorded there with this date.
Rollback remains migration-free: pass `canonical_evidence_enabled=False`.

## Coordinator Correction (2026-08-27, verified in source)

The coordinator's earlier statement to the user — "the switch is OFF in the
shipped default; everywhere else (including every test) the old full path
runs" — was wrong in substance. Verified: `service.py` enabled the arena for
every ordinary construction whose verified material passed profile
verification in the production trust domain (which is how the main V3 suites
and real deployments construct the service); it was disabled only for the
scenario-test fixture path (`_from_scenario_test_host`) and for services with
no verified material (which have no semantic runtime at all). What remains
true: the measured reduction evidence (parent `VCC-R01`) was never produced,
the 96.5-99.9% figures were reference/counterfactual counts, H8 and H7 are
unremediated, and no certified wall-clock improvement exists anywhere.

## Objective

Every verified runtime executes the substituted path by default; the parity
contract is enforced by a small diametric gate on a slow cadence; the
confirmed duplicate Step-2 work is gone; and the next profiling run measures
the real remaining cost so H7 work targets reality.

## Completion Contract

1. every test that builds a verified runtime executes with the substitution
   ON unless it is one of fewer-than-ten explicit parity nodes;
2. the parity gate proves byte-identical outcomes on diametric cases across
   ON/OFF and runs in the repository's slow tier on a scheduled cadence;
3. `_run_semantic_ingestion` no longer re-prepares and re-publishes the
   prepared source (H8), with a regression proof that the persisted reload
   path alone sustains every family;
4. a fresh profile of the frozen diagnostic scenario runs with ON+H8 and its
   numbers are recorded here, scoping (or closing) H7;
5. the affected design documents record the amended rollout contract; the
   removal operation's resume state is preserved untouched.

## Scope

Included: the service-level enablement change and its explicit override; the
parity gate module and its workflow cadence; the H8 deletion with focused
proofs; one profiling run and its recorded numbers. Excluded: H7 remediation
beyond scoping (separate unit once measured); benchmark/live certification
claims; any reopening of the legacy-path removal's slices.

## Milestones

| Milestone | Observable outcome | Status |
| --------- | ------------------ | ------ |
| Enable-by-default | every verified runtime substitutes; explicit `canonical_evidence_enabled=False` is the only off path; arena + service + parity suites green | complete (commit `b33a171`) |
| Parity gate | fewer-than-ten diametric nodes, slow-tier workflow cadence, gate-change log recorded | wired (module + workflow + shard exclusion; module green run pending) |
| H8 removal | single prepare-and-publish per ingestion; family proofs green | complete (47 passed) |
| Re-profile | frozen-scenario numbers with ON+H8 recorded; H7 scoped or closed | complete (63.7% wall-clock reduction measured; H7 budget = residual ~36s) |

## Progress Log

- 2026-08-27: Opened after the user's decisions; corrected the enablement
  record (above); M1 edit applied (`service.py`: override kwarg added; the
  flag no longer depends on the construction's trust domain). Verification
  (arena 29, provider service, both redelivery parity proofs) running.

- 2026-08-27 (M3 done): the duplicate Step-2 lifecycle work is removed —
  `_run_semantic_ingestion` no longer re-prepares and re-publishes the
  prepared source; the validated repository load is the single prepared-source
  authority on that path (the bootstrap handoff or the prior delivery owns the
  one publication). Evidence: provider service + replay suite + fresh-owner
  recovery proof + reopen proof = 47 passed in 8:56 at the fix revision.
- 2026-08-27 (M2 wired): dedicated diametric parity module
  `test_canonical_evidence_mode_parity.py` (two nodes: redelivery recovery and
  direct delivery, each running both modes against identical durable
  projections); the redelivery node moved out of the coordinator module so the
  PR shard shrinks; module excluded from `unit-shards.json` (shard plan
  verifies: 3439 collected); scheduled workflow
  `.github/workflows/canonical-evidence-parity-scheduled.yml` runs every four
  hours with an exact-collection-count check of 2. Gate change record: unique
  failure signal = opposed-mode outcome/projection/idempotence divergence;
  moved node preserves its proof, PR-shard wall time decreases by the moved
  node's ~8 minutes; growth path (composite/memory-write/hermes diametric
  nodes) recorded as follow-up within the <10 budget.
- 2026-08-27 (fixture repair): the slice-5 WIP had dead-coded the V3 authority
  extraction inside a raise branch of the normalization fixture
  (`build_source_normalization_authority_bundle`); restored, all three
  redelivery proofs pass under default-on (20:38).

- 2026-08-27 (M2 verified): the parity module is green — 2 passed in 6:26
  (redelivery-recovery and direct-delivery diametric nodes; opposed modes,
  identical outcomes, idempotence, and durable projections).
- 2026-08-27 (M4 procedure, located not run): the frozen diagnostic harness
  lives in
  `../semantic-ingestion-canonical-evidence-production-performance-2026-08-16/evidence/` —
  run `pbd_exp_004_duplicate_step2.py` (the H8 experiment) against the current
  revision for the fixed-vs-baseline comparison, then
  `pbd_exp_003_persistence_composition.py` (the H7 kernel) with the
  substitution ON and H8 removed to scope what actually remains. Record both
  JSON outputs here and close or open the H7 unit from those numbers.

- 2026-08-27 (M4 complete, measured): PBD-EXP-014
  (`../semantic-ingestion-canonical-evidence-production-performance-2026-08-16/evidence/pbd-exp-014-default-on-wall-clock-v1.json`,
  commit `e8dd06c`) — five shuffled samples per mode through the public
  sync_event root on the current tree, full V3 composition, post-H8
  accounting asserted per child:
  **disabled median 99.92s / 43,756 content-digest calls; enabled (default)
  median 36.22s / 237 calls** — **63.7% wall-clock reduction and 99.46%
  digest-call reduction**, both deterministic across samples. The disabled
  leg reproduces the original ~43k-validation pathology. Finding for H7
  scoping: 237 digest calls cannot account for the remaining ~36s, so the
  residual is almost entirely non-digest work (typed reconstruction,
  persistence composition, graph transaction) — that is H7's budget, to be
  attacked as its own unit from these numbers. Measurement caveats recorded
  in the evidence JSON: durable bytes vary cross-process by design
  (per-delivery unique identities), so parity is carried by the diametric
  gate; the 2026-08-16 frozen-scenario rendering no longer exists, so the
  historical 0.90s anchor is context, not a controlled comparison. Also
  recorded: the scenario harness's initial-writer activation fails on a
  fresh writer store (pre-existing on this branch, independent of this
  operation) — the measurement uses the production-domain composition
  instead.

## Next Action

All four milestones are complete. Resume the paused legacy-path removal
operation (slice-5 failure classification first), and open the H7 unit
(persistence-composition kernel, ~36s residual per delivery) as its own
linked operation when ready.
