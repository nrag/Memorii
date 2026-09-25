# Hermes Level 2 Test Gate

- Work ID: `hermes-level2-test-gate`
- Work type: testing
- Delivery fidelity: Level 2 early real-world testing
- Status: active
- Coordinator: `/root`
- Created: 2026-09-24
- Last updated: 2026-09-24
- Parent WorkPlan: `docs/work/hermes-conversation-memory-trial/implementation.plan.md`
- Candidate product revision: `ef187110ca53d10cab6e4bfa0f3c7f65149a475b`
- Canonical inputs: `.github/workflows/pr-gates.yml`; `memorii/tests/integration/test_hermes_bootstrap_v3_product.py`; `memorii/tests/ci/unit-shards.json`; `memorii/tests/ci/unit-test-durations.json`

## Objective

Give every Hermes Level 2 scenario an explicit merge gate and measured runtime
owner while preserving production-shaped restart, replay, rejection, recovery,
revocation, and recall proof.

## Completion Contract

The five-scenario Hermes product module is collected by one dedicated required
PR job and required by the Semantic Ingestion aggregate. Every changed Hermes
unit node has a measured duration in the unit timing manifest. Workflow
structure, shard verification, focused regressions, Ruff, Pyright, GitHub
execution, and independent test review pass for one frozen product revision.

## Test Portfolio And Gate Map

| Contract | Test owner | Gate | State |
| --- | --- | --- | --- |
| completed turn persists and recalls after reopen | `test_hermes_bootstrap_v3_product.py` | `hermes-level2-product` -> `semantic-ingestion` | implemented |
| abstention does not block later ingestion | same module | same gate | implemented |
| active revocation prevents commit | same module | same gate | implemented |
| startup recovers admitted work | same module | same gate | implemented |
| rejected unknown, ungrounded, duplicate, and malformed candidates terminate evidence-only and do not block a later valid turn | same module | same gate | implemented; isolated pass |
| equal text at distinct transcript positions is distinct; redelivery at the same position is idempotent | bridge unit module | duration-balanced unit shards | implemented; isolated pass |
| installed first-party Hermes loader persists, reopens, recalls, inspects, shuts down, and denies missing authority | Docker context module | `hermes-installed-image-lifecycle` -> `semantic-ingestion` | implemented; isolated pass |

## Runtime And Ownership Budget

The dedicated product gate has a 3,000-second runtime budget, 600-second
headroom, and a 60-minute timeout. The installed-image gate has a 2,400-second
runtime budget, 1,200-second headroom, and a 60-minute timeout. The workflow
asserts exactly five collected product scenarios. The broad unit owner collects
4,509 tests across six node-balanced shards under the 1,200-second target. Changed
Hermes nodes have explicit timing records, including 826.52 seconds for the
production-shaped equal-text bridge regression.

## Evidence Log

- Product collection: 5 tests collected in 12.51 seconds.
- Rejected-candidate product regression: 1 passed in 835.55 seconds.
- Equal-text bridge regression: 1 passed in 826.52 seconds.
- Project assertion adapter/profile focus: 9 passed in 18.85 seconds.
- Installed default-image Hermes `MemoryManager` lifecycle: 1 passed in 1867.18 seconds.
- Completed-turn close and post-close admission: 1 passed in 397.02 seconds.
- Unit shard verification: 4,509 collected across six node-balanced shards; maximum estimated shard 826.520 seconds.
- Static tooling contract: 19 passed in 140.18 seconds.
- Ruff passed for `memorii` and `tests`; configured Pyright reported 0 errors.
- GitHub execution of the complete five-scenario job remains the final gate.
- Abstained recovery replay regression: 4 passed in 82.56 seconds. Exact unit
  shard 2 exercised all 740 assigned tests; all recovery cases passed. Its one
  local benchmark identity failure passed separately with the CI source
  revision binding, leaving no product failure in the shard.
- Exact unit shard 3 exercised all 962 assigned tests and passed in 2,297.89
  seconds. The focused expired-claim, three lost-ack boundaries, three
  reused-commit production roots, and two clarification reopen cases all pass.

## Blockers And Limits

The complete five-scenario product job is intentionally delegated to the
required GitHub job because its expected runtime is approximately 45 minutes.
That job must pass at the pushed evidence head before merge.

## Next Action

Push the replacement frozen evidence head and verify the required `hermes-level2-product`,
`hermes-installed-image-lifecycle`, and `semantic-ingestion` GitHub checks.
