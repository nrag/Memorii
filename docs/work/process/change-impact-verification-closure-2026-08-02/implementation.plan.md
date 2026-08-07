# Change Impact Verification Closure

- Work ID: change-impact-verification-closure-2026-08-02
- Work type: implementation
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-08-02
- Last updated: 2026-08-02
- Parent WorkPlan: docs/work/process/behavioral-identity-governance-2026-08-02/design.plan.md
- Related WorkPlans: docs/work/process/behavioral-identity-governance-2026-08-02/testing.plan.md
- Canonical inputs: .agents/PLANS.md; .agents/skills/*/SKILL.md; PR 115 failure analysis
- Expected outputs: mandatory live-diff, authority-chain, gate, and known-failure closure rules

## Objective

Prevent a focused local test run or an unsupported “pre-existing failure”
classification from closing work whose actual diff affects additional
artifacts or PR gates.

## Completion Contract

Complete when the common WorkPlan contract makes the live diff authoritative,
requires complete source-to-gate authority chains, records exact affected local
jobs, requires clean-merge-base reproduction for excluded failures, and every
repository workflow skill applies the rule at its own decision point.

## Scope

Included: `.agents/PLANS.md` and all six repository workflow skills. Excluded:
the separate corrections for PR 115, which belong to a linked debugging
WorkPlan.

## Constraints And Invariants

Do not weaken existing identity, evidence-maturity, CI revision, or independent
review rules. Keep shared policy centralized in `.agents/PLANS.md` and keep
skill-specific additions concise.

## Identity And Coordinate Hygiene

| Surface | Identity | Class | Owner or meaning | Action | Proof |
| ------- | -------- | ----- | ---------------- | ------ | ----- |
| WorkPlan section | Change Impact And Verification Closure | behavioral identity | Repository closure policy | add | `.agents/PLANS.md` |
| Closure fields | changed surface, authority chain, gate, and failure ledgers | behavioral identity | Revision-bound verification evidence | add | skill validation and diff inspection |

The Work ID and PR number remain planning/evidence coordinates inside this
WorkPlan only.

## Change Impact And Verification Closure

| Path or pattern | Surface class | Intended scope owner | Authority chain | Required gates | Status |
| --------------- | ------------- | -------------------- | --------------- | -------------- | ------ |
| `.agents/PLANS.md` | process contract | coordinator | policy -> closure schema -> work-type contracts | skill validation; diff check | complete |
| `.agents/skills/*/SKILL.md` | workflow instructions | coordinator | central policy -> phase-specific enforcement | validate all six skills; diff check | complete |

All changed surfaces are owned. No generated or frozen artifact follows from
these Markdown instruction changes.

## Sources Of Truth

Root `AGENTS.md`, `.agents/PLANS.md`, the six repository skills, and the
observed PR 115 mismatch between the live diff, local command set, and failed
CI jobs.

## Current State

The common contract and every workflow skill now enforce live-diff scope,
complete authority-chain closure, exact gate coverage, and merge-base proof for
excluded failures. All six skill packages validate.

## Assumptions And Open Questions

Verified: all six skills read `.agents/PLANS.md`. No unresolved question or
external decision remains.

## Design Baseline

The approved process direction is the user's instruction following the PR 115
root-cause analysis. No product-semantic requirement is changed.

## Requirement Coverage Ledger

| Requirement | Implementation | Tests | Other evidence | Status |
| ----------- | -------------- | ----- | -------------- | ------ |
| Live diff controls scope | `.agents/PLANS.md` and all applicable skills | skill validation | diff inspection | verified |
| Authority chains close end to end | central contract and design/implementation/review skills | skill validation | diff inspection | verified |
| Exact gates replace focused-test inference | central contract and implementation/testing/debug/review skills | skill validation | diff inspection | verified |
| Failure exclusion requires merge-base proof | central contract and debugging/review skills | skill validation | diff inspection | verified |

## Change Map

Only repository agent instructions and this WorkPlan changed. Product code,
schemas, persistence, prompts, adapters, deployment, and runtime behavior are
not applicable.

## Migration, Rollout, And Rollback

The instructions apply to subsequent work immediately. No persisted-data or
mixed-version behavior exists.

## Verification Commands

All six directories passed `quick_validate.py`. `git diff --check --
.agents/PLANS.md .agents/skills` passed.

## Milestones Or Experiments

1. Centralize change-impact closure. Status: complete.
2. Apply phase-specific rules to all six skills. Status: complete.
3. Validate all revised skills. Status: complete.

## Progress Log

- 2026-08-02: Added the live-diff, authority-chain, gate, and failure ledgers;
  updated all six workflow skills; validated every skill. Next action: complete
  this linked process WorkPlan and begin the separate PR-gate debugging work.

## Evidence Log

```yaml
base_revision: 2cf7fde9f969b2a2fda1f4719c307ae0c7df2c09
reviewed_revision: working-tree process delta
tested_revision: working-tree process delta
tested_tree_digest: not_applicable (instruction files validated directly)
tree_state: dirty with owned process changes
changed_surface_inventory_complete: true
scope_delta_resolved: true
authority_chains_complete: true
required_local_jobs: [six skill validations, git diff check]
passed_local_jobs: [six skill validations, git diff check]
known_local_failures: []
failure_exclusions: []
workflow_identities: []
ci_event: not_applicable (local process change)
ci_executed_sha: not_applicable (local process change)
ci_executed_ref: not_applicable (local process change)
remaining_validated_p1_p2: []
remaining_blocks_approval: []
remaining_changes_required: []
local_ci_parity: not_applicable (skill package validation has no CI job)
acceptance_gate_inventory: [skill validation, diff check]
github_run_urls: []
pr_head_sha: not_applicable (not yet published)
pr_base_sha: not_applicable (not yet published)
merge_base_sha: not_applicable (not yet published)
required_checks_green: not_applicable (not yet published)
```

## Decision Log

- 2026-08-02: Centralize the invariant in `.agents/PLANS.md` and add only the
  workflow-specific decision points to skills, avoiding divergent copies.

## Review Log

Structural validation passed for every repository skill. Independent product
review is not applicable because no product or test behavior changed.

## Blockers And Limits

None.

## Next Action

None; this WorkPlan is complete.

## Outcome And Retrospective

The process no longer permits closure from a narrow test selection when the
actual diff reaches broader artifacts or gates. The prior failure came from
missing mechanical reconciliation, not a lack of general advice to run tests.
