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
- Expected outputs: ancestry-preserving reconciliation merge, durable causal/equivalence evidence, a dependency-free PR gate, green required checks, and independent closure review

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
- a deterministic verifier binds the reviewed target to the reconciliation merge
  and both parents, and rejects substituted parent, tree, source-transplant,
  target, and equivalence identity;
- the base-to-head PR diff is restricted to five surfaces: the reconciliation
  WorkPlan; `tools/semantic_ingestion_history_reconciliation.json`;
  `tools/verify_semantic_ingestion_history.py`; the PR workflow gate and its
  `Unit Tests` aggregate wiring; and the focused static workflow regression
  test. The ancestry merge itself changes zero product bytes;
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

Included: Git ancestry reconciliation, exact parent/tree and reachability
verification, durable explanation, a dependency-free PR check, focused static
workflow coverage, and branch supersession evidence.

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
| H4 | An ancestry-only merge can record incorporation without changing product bytes | exact parent/tree and reachability verifier passed at `c102fedb` | preserves main tree while recording M5 as ancestry | confirmed |

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
6. Review found that the original record did not bind the repair to a reviewed
   target and allowed the record to redefine the equivalence paths. The verifier
   now requires the source transplant to precede the first parent; the merge and
   both parents to precede the invocation target; and a stable review anchor to
   precede that target. It constrains the three permitted evidence rows in code.
7. Added the dependency-free `Semantic Ingestion History Reconciliation` PR job and made the
   `Unit Tests` aggregate require it. Focused static workflow coverage verifies
   the isolated Python command and aggregate dependency.

## Changed Surface And Verification

| Surface | Purpose | Required evidence | State |
| --- | --- | --- | --- |
| Git merge commit | record both current main and M5 as parents while retaining main tree | exact parent order and tree equality | complete: `a74ebcb0` |
| `tools/verify_semantic_ingestion_history.py` and `tools/semantic_ingestion_history_reconciliation.json` | durable causal and verification record | verifier, reachability checks, and mutation self-tests | complete at `c102fedb` |
| `.github/workflows/pr-gates.yml` | execute verifier on every PR and make the aggregate gate fail closed | isolated `python3.12 -I` job required by `Unit Tests` | complete at `c102fedb` |
| `memorii/tests/unit/tools/test_static_tooling_config.py` | prove workflow job and aggregate dependency remain exact | two focused static workflow tests | complete at `c102fedb` |
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

Correctness and test review evaluated clean candidate
`02dec70609e41c2eb977b77927b442d5f495b614`; specification inspection's only
requested correction is this closure-evidence update. GitHub CI has not run for
this branch and is not claimed here.

## Verification Evidence

The durable record is `tools/semantic_ingestion_history_reconciliation.json`;
`tools/verify_semantic_ingestion_history.py`
must verify the actual merge's ordered parents, its tree identity, equality with
the first-parent tree, and the exact three-file transplant/M5 equivalence fact.
It also rejects representative parent, tree, and equivalence substitutions with
`--self-test`.

- Documentation/verifier child commit: `cfa5dcbb792134a45976d8d64218cfc76e45f859`.
- `python3 tools/verify_semantic_ingestion_history.py`
  exited 0 and reported merge `a74ebcb0`, its ordered parents, first-parent
  tree `228736f174b4723cc95a3599eb84c040f045c1c9`, and three equivalence rows.
- `python3 tools/verify_semantic_ingestion_history.py --self-test`
  exited 0 and proved that substituted second-parent, tree, and equivalence-row
  values are rejected.
- `/Users/nandaraghunathan/Code/Memorii/Memorii/.venv/bin/ruff check
  tools/verify_semantic_ingestion_history.py` exited 0.
- `git diff --no-ext-diff --check` exited 0 before the child commit.

At remediation candidate `c102fedb9c2396195a2f9f2f4e56791011d86c5e`:

- `python3 -I tools/verify_semantic_ingestion_history.py
  --repo . --self-test` exited 0. Its target was `c102fedb`; it verified that
  `a74ebcb0`, both ordered parents, and review anchor `c6e7e6a7` are ancestors
  of that target. It rejected valid alternate parent/merge, tree, nonempty
  equivalence, transplant, and target substitutions at their decisive checks.
- `PYTHONPATH=/Users/nandaraghunathan/.codex/worktrees/m5-ancestry-repair/Memorii/memorii /Users/nandaraghunathan/Code/Memorii/Memorii/.venv/bin/python
  -m pytest -W error tests/unit/tools/test_static_tooling_config.py::test_pr_unit_gate_is_complete_duration_balanced_and_timeout_bounded
  tests/unit/tools/test_static_tooling_config.py::test_semantic_ingestion_history_gate_is_isolated_and_required
  -p no:cacheprovider -q` exited 0: `2 passed`.
- `/Users/nandaraghunathan/Code/Memorii/Memorii/.venv/bin/ruff check --no-cache
  tools/verify_semantic_ingestion_history.py
  memorii/tests/unit/tools/test_static_tooling_config.py` exited 0 from the
  repository root. The focused pytest parses the
  workflow with PyYAML and confirms the required command and aggregate wiring.
- `git diff --no-ext-diff --check` exited 0 at `c102fedb`.

## Identity Impact

No behavioral, persisted, protocol, public API, or production-entrypoint
identifier changes. The historical WorkPlan retains the incident coordinate for
traceability. The durable verifier, record, CI job, environment key, and test
identifier use semantic-ingestion-history names and do not enter product data
or harness behavior.

```yaml
base_revision: 2eefb39e7c80ab609961f3db78fbc16401f9d675
reviewed_revision: 02dec70609e41c2eb977b77927b442d5f495b614; correctness/test reviewed this clean candidate and spec inspection requested only this closure-evidence correction
tested_revision: c102fedb9c2396195a2f9f2f4e56791011d86c5e
tested_tree_digest: c5cea63b1aa1e5d83286cff1441cde7848c3b198
tree_state: clean after c102fedb; later commits are WorkPlan-only evidence updates
changed_surface_inventory_complete: true
scope_delta_resolved: true
authority_chains_complete: not_applicable; no product authority chain changed
required_local_jobs:
  - reconciliation verifier
  - reconciliation verifier self-test
  - Ruff
  - git diff check
  - focused workflow contract test
passed_local_jobs:
  - reconciliation verifier
  - reconciliation verifier self-test
  - Ruff
  - git diff check
  - focused workflow contract test
known_local_failures: []
failure_exclusions: []
workflow_identities: []
ci_event: pending PR creation
ci_executed_sha: pending PR creation
ci_executed_ref: pending PR creation
remaining_validated_p1_p2: []
remaining_blocks_approval:
  - independent closure review
  - exact-head GitHub checks
remaining_changes_required: []
local_ci_parity: focused static proof covers the dependency-free PR command; exact GitHub event remains pending
acceptance_gate_inventory:
  - Semantic Ingestion History Reconciliation PR gate
  - Unit Tests aggregate dependency
  - targeted independent review
  - exact-head GitHub checks
github_run_urls: []
pr_head_sha: pending PR creation
pr_base_sha: 2eefb39e7c80ab609961f3db78fbc16401f9d675
merge_base_sha: 2eefb39e7c80ab609961f3db78fbc16401f9d675
required_checks_green: pending PR creation
```

## Next Action

Run independent closure review and exact-head CI for the ancestry-only merge and
its reconciliation evidence.
