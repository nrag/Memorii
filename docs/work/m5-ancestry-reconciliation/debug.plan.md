# Semantic Ingestion M5 Ancestry Reconciliation

- Work ID: `m5-ancestry-reconciliation`
- Work type: debugging
- Delivery fidelity: Level 2 early real-world testing
- Status: under-review
- Coordinator: `/root`
- Created: 2026-09-25
- Last updated: 2026-09-25
- Parent WorkPlan: `docs/work/hermes-conversation-memory-trial/implementation.plan.md`
- Related WorkPlans: `docs/work/hermes-level2-pr/pr-review.plan.md`; `docs/work/hermes-level2-test-gate/testing.plan.md`
- Canonical inputs: merge commit `d0c96305397f03c1e4a09e548f0fbd62602b3f95`; M5 merged head `410ce4a817903a6670e268061b22744d7c7d806b`; M5 descendant head `63658193b8a4c296b553bb6c3e7fd89392566b2a`; Level 2 transplant `e42cc905c8c583ee99f83777cce25026e6c11041`; current main `2eefb39e7c80ab609961f3db78fbc16401f9d675`
- Expected outputs: ancestry-preserving reconciliation merge, durable causal/equivalence evidence, green required checks, and independent closure review

## Objective

Make current `main` record `semantic_ingestion_m5` head `63658193` as incorporated
without changing the already reviewed and tested `main` tree. Future branch and
history operations must no longer treat the incorporated M5 work as an unrelated
line of development.

## Completion Contract

Complete only when:

- the M5 post-PR history and the Level 2 transplant are causally accounted for;
- the repair commit has current `main` and `63658193` as parents while retaining
  the current `main` tree exactly;
- a deterministic verifier rejects missing or substituted parent/tree identity;
- the complete PR diff contains only the reconciliation record and its verifier;
- targeted independent spec, correctness, and test review report no required
  findings;
- exact-head required GitHub checks pass and the reconciliation PR is merged.

## Expected And Observed Behavior

Expected: after incorporating work from a long-lived branch, `main` contains the
incorporated branch head as an ancestor or records an explicit reviewed
supersession merge.

Observed: PR #120 merged M5 only through `410ce4a`; the branch then gained 18
commits through `63658193`. PR #121 started from PR #120 merge commit `d0c96305`
and transplanted the M5 tree into `e42cc905` without retaining `63658193` as a
parent. Neither current `main` nor M5 contains the other. A normal merge
simulation reports 225 conflicts.

Classification: repository integration and governance defect. Product code is
not missing: `e42cc905` and `63658193` differ only in three `docs/work` evidence
files, so all application, test, workflow, and design content at the M5 head was
incorporated before later Level 2 corrections.

## Scope And Invariants

Included: Git ancestry reconciliation, exact parent/tree verification, durable
explanation, PR checks, and branch supersession evidence.

Excluded: changing product behavior, replaying M5 patches over newer Level 2
code, rewriting published history, deleting the M5 branch, or altering release
semantics.

The repair must preserve the exact current `main` tree. A content merge is
forbidden because the old M5 side predates reviewed Level 2 corrections.

## Hypothesis Ledger

| ID | Hypothesis | Evidence | Result | Status |
| --- | --- | --- | --- | --- |
| H1 | PR #121 omitted post-PR #120 M5 product changes | `e42cc905..63658193` differs only in three WorkPlan/evidence files | M5 product tree was transplanted | disproved |
| H2 | PR #121 incorporated M5 content but lost its ancestry | `e42cc905` parent is `d0c96305`; neither final branch is ancestor of the other; normal merge has 225 conflicts | Explains the misleading unmerged branch and conflict family | confirmed |
| H3 | A normal merge can safely repair history | merge simulation has 225 conflicts across generated contracts, runtime code, tests, Docker, workflows, and evidence | A content merge risks restoring stale state | disproved |
| H4 | An ancestry-only merge can record incorporation without changing product bytes | Git `ours` merge semantics retain first-parent tree while adding the M5 parent | Must be proven by exact parent and tree verifier | active |

## Experiment Log

1. Compared PR #120 merged head with current M5 head: exactly 18 later commits.
2. Compared M5 head `63658193` with Level 2 transplant `e42cc905`: three changed
   files, all under `docs/work`; no product, test, workflow, or governing design
   difference.
3. Simulated merging current main with M5: exit 1 and 225 conflict records.
4. Selected an ancestry-only merge plus deterministic verifier as the smallest
   safe correction.
5. Created reconciliation merge `a74ebcb0db7d808ab0010cfe893c1e1b76aa6bbe`
   with ordered parents `2eefb39e7c80ab609961f3db78fbc16401f9d675` and
   `63658193b8a4c296b553bb6c3e7fd89392566b2a`. Its tree is
   `228736f174b4723cc95a3599eb84c040f045c1c9`, exactly the first-parent tree.

## Changed Surface And Verification

| Surface | Purpose | Required evidence | State |
| --- | --- | --- | --- |
| Git merge commit | record both current main and M5 as parents while retaining main tree | exact parent order and tree equality | complete: `a74ebcb0` |
| `docs/work/m5-ancestry-reconciliation/` | durable causal and verification record | verifier positive and mutation self-tests | in progress |
| GitHub PR | review and integrate ancestry repair | exact-head checks and mergeability | pending |

## Root Cause

The Level 2 publication branch was created from PR #120's merge commit and
populated from the later M5 working tree as a squash-like transplant. Review
verified the resulting bytes and Level 2 behavior but did not verify that the
source branch head appeared in the candidate ancestry. The merge therefore
published the intended content while leaving Git unable to recognize the M5
line as incorporated.

## Review And Closure

```yaml
remaining_validated_p1_p2: []
remaining_blocks_approval:
  - independent closure review
  - exact-head GitHub checks
level_2_disposition: under-review
```

## Verification Evidence

The durable record is `reconciliation-record.json`; `verify_reconciliation.py`
must verify the actual merge's ordered parents, its tree identity, equality with
the first-parent tree, and the exact three-file transplant/M5 equivalence fact.
It also rejects representative parent, tree, and equivalence substitutions with
`--self-test`. The verification commands and their exit status are recorded
after the verifier is added to this WorkPlan's child documentation commit.

## Next Action

Run independent closure review and exact-head CI for the ancestry-only merge and
its reconciliation evidence.
