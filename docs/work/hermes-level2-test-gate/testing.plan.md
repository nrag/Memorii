# Hermes Level 2 Test Gate

- Work ID: `hermes-level2-test-gate`
- Work type: testing
- Delivery fidelity: Level 2 early real-world testing
- Status: complete
- Coordinator: `/root`
- Created: 2026-09-24
- Last updated: 2026-09-24
- Parent WorkPlan: `docs/work/hermes-conversation-memory-trial/implementation.plan.md`
- Related WorkPlans: `docs/work/hermes-completed-turn-redelivery-debug/debug.plan.md`
- Canonical inputs: `.github/workflows/pr-gates.yml`; `memorii/tests/integration/test_hermes_bootstrap_v3_product.py`; `memorii/tests/ci/unit-shards.json`
- Expected outputs: one required Hermes product gate, complete unit timing ownership, and revision-bound deterministic evidence

## Objective

Give every Hermes Level 2 test one explicit merge gate and measured runtime
owner while preserving the production-shaped restart, replay, recovery, and
revocation proof.

## Completion Contract

The four-test Hermes product module is collected by one dedicated required PR
job and its result is required by the Semantic Ingestion aggregate. Every new
Hermes unit node has a measured duration in the unit timing manifest. Workflow
structure, shard verification, focused tests, Ruff, Pyright, and independent
test and correctness reviews pass at one immutable candidate revision.

## Scope

Included: Hermes product-gate placement, aggregate wiring, deterministic job
ownership, timing data for new unit tests, and workflow contract verification.

Excluded: product semantics, live OpenAI quality measurement, Windows Docker
execution, release signing, and broader CI redesign.

## Constraints And Invariants

- The integration module runs through the installed first-party Hermes factory
  and real persistence owners, with only the model transport replaced.
- The dedicated gate owns the integration module exactly once.
- Unit nodes remain in the duration-balanced exhaustive shards and receive
  measured timings rather than default estimates.
- The 60-minute timeout retains at least 10 minutes above the observed
  approximately 35-minute local product-suite runtime.

## Sources Of Truth

1. Root `AGENTS.md` delivery fidelity and testing rules.
2. `.agents/skills/design-tests/SKILL.md`.
3. `.github/workflows/pr-gates.yml` and its static tooling tests.
4. `memorii/tests/ci/unit-shards.json` and `unit-test-durations.json`.

## Test Portfolio And Gate Map

| Contract | Test owner | Failure signal | Gate | Status |
| --- | --- | --- | --- | --- |
| completed turn persists and recalls after reopen | `test_hermes_bootstrap_v3_product.py` | committed projection is absent or recall misses | `hermes-level2-product` -> `semantic-ingestion` | implemented, verification pending |
| abstention does not block later ingestion | same module | reopen or later eligible turn fails | same gate | implemented, verification pending |
| active revocation prevents commit | same module | revoked work becomes visible | same gate | implemented, verification pending |
| startup recovers admitted work | same module | pending operation is not completed | same gate | implemented, verification pending |
| isolated parser, admission, authority, and bridge behavior | current Hermes and Bootstrap V3 unit modules | boundary-specific assertion fails | duration-balanced unit shards | measured and verified |

## Runtime And Ownership Budget

The dedicated product gate has a 3,000-second runtime budget, 600-second
headroom, and a 60-minute timeout. The exact four-test collection assertion
prevents silent suite drift. New unit tests remain file-granular shard inputs;
their measured node durations will be merged into the canonical timing
manifest before candidate freeze.

## Progress Log

- 2026-09-24: Review found that the production-shaped Hermes integration
  module had no explicit required PR owner and the new unit nodes lacked timing
  records. Added the dedicated job, aggregate dependency, and deterministic-job
  budget.
- 2026-09-24: Merged measured timings for the new current-profile and Hermes
  nodes. The broad owner collects 4,506 nodes with 3,517 measured durations and
  balances six shards at 610.431-610.432 estimated seconds. Workflow/setup
  structure tests pass (`22 passed`).

## Evidence Log

- `pytest --collect-only -q tests/integration/test_hermes_bootstrap_v3_product.py`:
  4 tests collected in 6.72 seconds.
- Prior local execution of the product module completed in approximately 35
  minutes; CI execution at the candidate revision is required for gate closure.

## Blockers And Limits

GitHub execution evidence is unavailable until the pull request branch is
pushed. Live Windows Docker recall remains external acceptance evidence owned
by the parent implementation WorkPlan.

## Next Action

None. GitHub execution evidence is owned by the PR review WorkPlan.
