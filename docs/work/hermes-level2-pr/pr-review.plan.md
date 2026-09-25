# Hermes Level 2 Pull Request Review

- Work ID: `hermes-level2-pr-review`
- Work type: pr-review
- Delivery fidelity: Level 2 early real-world testing
- Status: active
- Coordinator: `/root`
- Created: 2026-09-24
- Last updated: 2026-09-24
- Base revision: `d0c96305397f03c1e4a09e548f0fbd62602b3f95`
- Candidate product revision: `a85d2980f144da210a0f743826c81d47e58380da`
- Head branch: `codex/hermes-level2`
- Pull request: `https://github.com/nrag/Memorii/pull/121`
- Parent WorkPlan: `docs/work/hermes-conversation-memory-trial/implementation.plan.md`
- Testing WorkPlan: `docs/work/hermes-level2-test-gate/testing.plan.md`

## Objective

Review, publish, and merge the complete Level 2 Hermes conversation-memory
candidate after deterministic gates, independent review, GitHub checks, and an
installed-image acceptance proof bind to the frozen product revision.

## Approval Contract

- The complete `origin/main...HEAD` diff has no unresolved P1/P2,
  `blocks_approval`, or `changes_required` findings.
- Ruff, configured Pyright, unit collection and shard verification, the five
  Hermes product scenarios, and GitHub required checks pass.
- The installed Hermes loader discovers Memorii from the image pinned by full
  RepoDigest, and the completed-turn bridge persists and recalls through the
  production factory and same-volume reopen path.
- The candidate manifest includes every non-`docs/work` change, including
  deletions, and validates against an immutable product revision.
- GitHub reports the current head mergeable.

## Scope

Included: HCM-01 through HCM-06, current Bootstrap V3 runtime, first-party
Hermes factory and bridge, Docker build path, callback replay identity,
rejected-candidate terminalization, persistence, retry, recovery, and recall.

Excluded: production signing, release certification, learned ontology support,
hostile-storage matrices, and shipped-product compatibility.

## Finding Disposition

- The canonical semantic-ingestion design was restored to its frozen bytes;
  Hermes Level 2 requirements remain in the dedicated extension design.
- Candidate output that was received but invalid now becomes a durable
  evidence-only terminal. Transport unavailability alone remains retryable.
- The bridge product test now proves equal text at distinct transcript
  positions produces distinct operations while replaying the second position
  is idempotent.
- The current Hermes entrypoint, production caller counts, recovery renewal,
  and source hashes are recorded in the canonical binding ledger and validated
  by the revision-bound preflight.
- Candidate manifest v2 includes the deleted legacy preparation test and all
  277 non-work changed paths.

## Acceptance Gate Inventory

| Gate | Evidence | State |
| --- | --- | --- |
| Ruff | full `memorii tests` run, no cache | passed locally |
| configured Pyright | 0 errors, 0 warnings | passed locally |
| unit collection and shard plan | 4,508 collected; six balanced shards under the 1,200-second target | passed locally |
| frozen replay vectors | 30 passed | passed locally |
| CTV compiler parity | 259 passed | passed locally |
| static tooling contract | 19 passed | passed locally |
| Hermes product collection | exactly 5 scenarios | passed locally |
| rejected-candidate product regression | 1 passed in 835.55s | passed locally |
| equal-text bridge replay regression | 1 passed in 826.52s | passed locally |
| completed-turn close and post-close regression | 1 passed in 397.02s | passed locally |
| installed Hermes `MemoryManager` lifecycle | 1 passed in 1867.18s | passed locally; required PR job |
| entrypoint/preflight validator | every production caller count is 1 | passed locally |
| candidate manifest validator | 282 paths; deletion included | passed locally |
| pinned installed image | Hermes `v0.21.4` (`2026.9.21`), base RepoDigest `sha256:6bece0644e29a347e5ae17db43c36938c86f171c6f5e0cef18aa2075d331f3a3`, candidate image `sha256:d1525f997595fa3feb7085f66aa52174ff8065f42159a40f735920872c1265cf`; Hermes reports Memorii installed, available, and active | passed locally |
| independent spec/correctness/test delta review | final evidence revision | pending |
| GitHub checks and mergeability | PR #121 | pending current-revision push |

## Next Action

Commit and push the evidence-only head, request final independent delta review,
then require green GitHub checks before merge.
