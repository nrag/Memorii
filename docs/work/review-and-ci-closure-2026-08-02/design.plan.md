# Review and CI Closure Workflow Design

- Work ID: review-and-ci-closure-2026-08-02
- Work type: design
- Status: complete
- Coordinator: Codex
- Created: 2026-08-02
- Last updated: 2026-08-02
- Parent WorkPlan: None
- Related WorkPlans: None
- Canonical inputs: `AGENTS.md`, `.agents/PLANS.md`, repository workflow skills, `.github/workflows/pr-gates.yml`
- Expected outputs: strengthened completion contracts and a repository `review-pr` skill

## Objective

Make milestone completion require zero unresolved validated P1/P2 defects at one reviewed revision, make deterministic verification traceable to the GitHub workflow contract, and define a distinct whole-PR approval workflow.

## Completion Contract

- Existing implementation, testing, and debugging skills define revision-bound milestone closure and CI-command parity.
- `.agents/PLANS.md` defines structured review, test, CI, and PR evidence required for completion.
- A validated repository `review-pr` skill owns whole-PR approval without duplicating milestone implementation review.
- `AGENTS.md` routes PR approval work to the new skill.
- Independent spec, correctness, and test reviews identify no unresolved validated P1/P2 process defect.

## Scope

Included: repository workflow documentation and skill metadata. Excluded: product behavior, GitHub branch-protection mutation, and implementation of a new CI command runner. Deferred: consolidating workflow commands behind a single executable manifest, which requires a linked testing WorkPlan.

## Requirements Ledger

| ID | Requirement | Source | Priority | Acceptance criteria | Status |
| --- | --- | --- | --- | --- | --- |
| WCF-R01 | Every milestone closure has zero unresolved validated P1/P2 findings under the canonical definitions. | User request | Required | Common closure record is empty and implementation, testing, and debugging skills enforce it. | Implemented |
| WCF-R02 | Completion evidence proves all applicable GitHub workflow commands and gates ran without confusing local evidence, PR head, synthetic merge, or merge-group identities. | User request | Required | Local command equivalence is bounded; actual CI event/SHA/ref and scope-specific acceptance gates are recorded. | Implemented |
| WCF-R03 | Whole-PR approval has a distinct read-only workflow and completion contract. | User request and repository workflow analysis | Required | `review-pr` owns full diff, threads, checks, acceptance gates, merge state, and one fail-closed decision. | Implemented |
| WCF-R04 | Workflow instructions resolve on case-sensitive runners. | Independent review | Required | Canonical root instructions are tracked as `AGENTS.md` and all references resolve. | Implemented |

## Verification Strategy

- Validate the new skill with the skill validator.
- Forward-use the skill on a real PR and inspect its decision record.
- Run independent spec, correctness, and test reviews over all changed workflow contracts.
- Run repository static workflow-contract tests and `git diff --check`.

## Constraints And Invariants

- Use the product-priority and approval-disposition definitions in `AGENTS.md`.
- Do not equate local macOS execution with GitHub runner parity.
- Do not claim CI enforcement before required checks pass on their actual
  current executed refs and the head/base/merge relationship is validated.
- Keep milestone closure, PR approval, and GitHub enforcement distinct.

## Sources Of Truth

`AGENTS.md` priority definitions and workflow routing take precedence, followed by `.agents/PLANS.md`, repository skills, and current GitHub workflows.

## Current State

Milestone skills require independent reviewers and deterministic gates but do not require a structured zero-P1/P2 closure record. Commands are described locally rather than bound to an explicit workflow revision. No repository skill owns whole-PR approval.

## Assumptions And Open Questions

- Verified fact: PR review requires branch-diff, check, review-thread, and SHA evidence not owned by the three specialist reviewers.
- Working assumption: GitHub Actions remains the authority for runner-specific enforcement.
- Unresolved question: whether a future shared executable CI manifest should replace direct workflow-command reconciliation.
- External decisions: None.

## Milestones Or Experiments

1. Define closure evidence and PR-review boundary; status: complete.
2. Update existing skills and create `review-pr`; status: complete.
3. Validate and independently review the workflow changes; status: complete.

## Progress Log

- 2026-08-02: established the missing whole-PR approval boundary; next action is to draft the skill and completion-contract changes.
- 2026-08-02: added revision-bound zero-P1/P2 closure records, exact workflow-command evidence rules, PR-review WorkPlans, and the `review-pr` skill. Skill structure validation passed in the repository environment.
- 2026-08-02: reconciled review findings for CI executed-ref identity, base/merge invalidation, manual/live acceptance gates, dirty-tree evidence, PR decision states, canonical path casing, timing ownership, and fail-closed metadata access.
- 2026-08-02: added structural verification for workflow aggregate results, timing artifact handoff, common closure-template keys, decision precedence, and a set-complete dedicated-job budget/exemption ledger.

## Evidence Log

- Existing `implement-design` Phase 7/8 requires reviewers but lacks an explicit machine-readable zero-P1/P2 closure record.
- Current local gates are documented commands; GitHub runner success remains separate evidence.
- `.venv/bin/python .../quick_validate.py .agents/skills/review-pr` exited successfully.
- `pytest -W error tests/unit/tools/test_static_tooling_config.py -p no:cacheprovider`: 13 passed.
- PR unit shard 3: 824 passed, 1 skipped.
- Full Ruff: passed. Scoped Pyright: 0 errors.
- Adversarial forward-use: inaccessible metadata -> blocked; stale check SHA/ref -> blocked; failed/skipped check and unresolved thread -> changes_required; current complete evidence -> approve.

## Decision Log

- Decision: create `review-pr` rather than expanding `implement-design` into a GitHub approval workflow. Rationale: arbitrary PRs and non-implementation changes need the same whole-diff, check, thread, and SHA review boundary.
- Alternative rejected: rely only on `github:gh-fix-ci` and `github:gh-address-comments`; those handle failures/comments but do not establish Memorii-specific approval readiness.

## Review Log

Initial independent reviews produced process findings. All were remediated and
targeted spec, correctness, and test re-reviews reported no remaining
`changes_required` finding.

```yaml
reviewed_revision: diagnostic_dirty_tree
tested_revision: diagnostic_dirty_tree
tree_state: dirty_by_requested_work
workflow_identities:
  - .github/workflows/pr-gates.yml
ci_event: local
ci_executed_sha: not_applicable_local
ci_executed_ref: not_applicable_local
remaining_validated_p1_p2: []
remaining_blocks_approval: []
remaining_changes_required: []
local_ci_parity: diagnostic commands plus exact unit shard; GitHub-only behavior not claimed
acceptance_gate_inventory:
  - skill validation
  - static workflow-contract tests
  - unit shard 3
  - Ruff
  - Pyright
github_run_urls: []
pr_head_sha: not_applicable_design_work
pr_base_sha: not_applicable_design_work
merge_base_sha: not_applicable_design_work
required_checks_green: not_applicable_not_pushed
```

## Blockers And Limits

No blockers or exhausted limits.

## Next Action

None; the design objective is complete.

## Outcome And Retrospective

Completed with a distinct PR-review workflow, revision-bound milestone closure,
fail-closed CI identity rules, and executable structural regression checks. A
future shared local CI runner remains optional; actual GitHub runs are the
authority for CI enforcement.
