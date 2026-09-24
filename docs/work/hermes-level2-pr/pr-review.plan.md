# Hermes Level 2 Pull Request Review

- Work ID: `hermes-level2-pr-review`
- Work type: pr-review
- Delivery fidelity: Level 2 early real-world testing
- Status: active
- Coordinator: `/root`
- Created: 2026-09-24
- Base branch: `main`
- Base revision: `d0c96305397f03c1e4a09e548f0fbd62602b3f95`
- Head branch: `codex/hermes-level2`
- Parent WorkPlan: `docs/work/hermes-conversation-memory-trial/implementation.plan.md`
- Testing WorkPlan: `docs/work/hermes-level2-test-gate/testing.plan.md`

## Objective

Review, publish, and merge the Level 2 Hermes conversation-memory candidate as
one complete base-to-head approval unit after deterministic local gates,
independent review, GitHub checks, and the applicable Windows Docker acceptance
evidence all bind to the final revision.

## Approval Contract

- The complete `origin/main...HEAD` diff is owned and free of unresolved P1/P2,
  `blocks_approval`, or `changes_required` findings.
- Ruff, full configured Pyright, unit collection/shard verification, the
  dedicated Hermes product gate, and all GitHub required checks pass.
- The current Windows image is built from the reviewed revision, runs the sole
  first-party factory, commits and recalls two eligible facts after a
  same-volume restart, and records the full Hermes image RepoDigest.
- Review threads are resolved and GitHub reports the current head mergeable.

## Scope

Included: HCM-01 through HCM-06, the current Bootstrap V3 runtime, first-party
Hermes factory and bridge, Docker build path, current test/gate topology, and
Level 2 retry/recovery/persistence behavior.

Excluded: production signing, release certification, learned ontology support,
hostile-storage/adversarial matrices, and shipped-product compatibility.

## Current Findings

- The original candidate review found unstable callback timestamps, legacy
  lifecycle callbacks entering the completed runtime, an unpinned image tag,
  incomplete timing/gate ownership, and stale broad tests. Corrections are in
  the working candidate and await final frozen-revision review.
- Restoring current-profile tests exposed a missing writer-admission case for
  an atomic V3 claim lease renewal. That debugging operation is active in
  `docs/work/bootstrap-v3-recovery-renewal-debug/debug.plan.md`.

## Acceptance Gate Inventory

| Gate | Owner | State |
| --- | --- | --- |
| Ruff and full Pyright | local + PR workflow | pending final candidate |
| exhaustive unit collection and shard plan | unit shards | collection and balancing verified; final run pending |
| Hermes Level 2 deterministic product module | `hermes-level2-product` | dedicated job wired; final run pending |
| independent spec/correctness/test cohort | coordinator | pending candidate freeze |
| Windows two-fact live OpenAI restart recall | user environment | pending pushed revision |
| full Hermes base image RepoDigest | user environment | pending pushed revision |
| GitHub required checks and mergeability | GitHub | pending PR |

## Next Action

Close the Bootstrap V3 renewal debugging operation and freeze one candidate revision.
