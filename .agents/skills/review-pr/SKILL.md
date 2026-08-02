---
name: review-pr
description: Independently review a Memorii pull request as an approval unit across the complete base-to-head diff, governing requirements, P1/P2 product risk, required checks, review threads, generated artifacts, and revision identity. Use when asked whether a PR is ready to approve or merge, for a final PR audit, or to review an arbitrary branch after implementation is complete.
---

# Review A Memorii Pull Request

Read root `AGENTS.md`, `.agents/PLANS.md`, governing documents, related
WorkPlans, the complete base-to-head diff, and current PR metadata, reviews,
threads, required checks, and workflow definitions.

Create or resume a `pr-review` WorkPlan when the review is long-running. Remain
read-only with respect to PR code and external state unless the user separately
asks for corrections. Maintaining the review WorkPlan is permitted. Route
corrections to the appropriate implementation, testing, or debugging workflow
and review the new head only after those changes complete.

## 1. Freeze The Review Identity

Record repository, PR number, base branch and SHA, head branch and SHA,
merge-base SHA, local tree state, and workflow file identities. Record each CI
event, run URL, executed SHA, and executed ref separately. A `pull_request`
merge SHA, PR head SHA, and `merge_group` SHA are not interchangeable.

Any head, base, merge result, merge-group composition, code, test,
generated-artifact, dependency, or workflow change invalidates approval and
requires review of the new approval unit.

## 2. Reconstruct Scope And Requirements

Inspect the complete diff, commits, changed files, related designs, WorkPlans,
issues, and review threads. Reconstruct requirements independently rather than
trusting the PR description or milestone ledger alone.

Identify intended behavior and non-goals; public, persisted, security,
compatibility, migration, rollback, and operational effects; generated-artifact
authority; unrelated or unexplained changes; overstated evidence maturity; and
the complete `.agents/PLANS.md` identity ledger for every changed durable
surface.

## 3. Review The Complete PR

Run concurrently when available:

- `spec_auditor` for governing-requirement and scope fidelity
- `correctness_reviewer` for runtime, architecture, security, concurrency, and
  integration defects
- `test_reviewer` for behavioral proof, gate placement, and failure signals

Require complete-current-state inspection and the classification contract in
`AGENTS.md`. Every P1/P2 finding must name the affected supported scenario and
justify why it is mainstream or important.

Reconcile every finding as confirmed, duplicate, unsupported, already
resolved, accepted limitation, design ambiguity, or blocked by missing
evidence. Reviewer silence is not approval evidence.

Independently scan the complete diff and current affected families for planning/
evidence coordinates in files, symbols, public or persisted IDs, tests, fixtures,
generators, goldens, registries, diagnostics, commands, evidence groups, timing
data, and workflow labels. Verify exact typed traceability/migration exceptions
and require the field-aware gate plus representative mutations. Classify a
violation as `identity-governance`, `Not applicable`, `changes_required`, and
`contract_conformance_action` unless product impact independently supports
P1/P2.

## 4. Verify CI And Revision Parity

Read current GitHub workflows directly. Inventory every required job, matrix
entry, shard, aggregate dependency, environment variable, working directory,
interpreter version, warning mode, and generated or timing artifact.

For local command-equivalence evidence:

1. run the repository deterministic commands selected by the workflow
2. record workflow identity, command, environment, cwd, status, SHA, and tree
3. fail equivalence for skipped commands, missing matrix entries, incomplete
   shard or timing inventories, and hand-written substitutes
4. treat GitHub-only actions, artifact transport, setup, expressions, and
   network steps as CI-only evidence
5. require a clean detached worktree, including untracked files; dirty-tree or
   different-runtime results are diagnostic only

GitHub required checks are authoritative for CI enforcement. Confirm every
required check and aggregate passes on its actual current executed SHA/ref.

Build a scope-specific acceptance-gate inventory before deciding. Include
required checks and any governing manual, scheduled, live, release, or external
gate. For each, record applicability and revision-bound run, artifact,
certificate, and clean-tree or package identity. A non-required GitHub check can
still be mandatory for the reviewed scope.

## 5. Verify Review And Merge State

Confirm no unresolved actionable thread remains; requested changes are resolved
or dispositioned; approvals apply to the current head; branch protection and
required checks pass; and mergeability, dependencies, generated artifacts, and
release notes match scope.

If required-check contexts, branch protection, reviews, threads, mergeability,
or acceptance-gate evidence cannot be retrieved authoritatively, decide
`blocked`; do not substitute an empty response or assumption.

Keep product priority independent from approval disposition. A governance or
evidence blocker can prevent approval without being P1/P2.

Use this fail-closed decision table as normative precedence. Apply identity and
access rows before check conclusions. Do not downgrade `blocked` to
`changes_required`, and never describe a synthetic merge or merge-group check
as a check on the PR head.

| Observed state | Required decision |
| --- | --- |
| Required GitHub metadata, protection, threads, or checks unavailable or forbidden | `blocked` |
| Check evidence belongs to a stale or mismatched executed SHA/ref | `blocked` |
| Current required check is failed, cancelled, skipped, neutral, or incomplete | `changes_required` |
| An actionable review thread remains unresolved | `changes_required` |
| Applicable manual or external gate is unavailable | `blocked` |
| All approval predicates and revision identities are satisfied | `approve` |

## 6. Produce The Approval Decision

Report findings first, then exactly one decision:

- `approve`: no confirmed P1/P2, `blocks_approval`, or `changes_required`
  finding remains; every required check and aggregate passes on its actual
  current executed ref; every applicable acceptance gate has revision-bound
  evidence; the identity ledger, exact exceptions, and field-aware gate are
  complete
- `changes_required`: determinate corrections or evidence actions remain
- `blocked`: approval needs an external decision, unavailable evidence, access,
  or resolution of a source-of-truth conflict

Record:

```yaml
reviewed_revision:
tested_revision:
pr_base_sha:
pr_head_sha:
merge_base_sha:
tree_state:
workflow_identities: []
ci_event:
ci_executed_sha:
ci_executed_ref:
remaining_validated_p1_p2: []
remaining_blocks_approval: []
remaining_changes_required: []
local_ci_parity:
acceptance_gate_inventory: []
github_run_urls: []
required_checks_green:
unresolved_review_threads: []
decision:
```

Never approve conditionally or infer approval from tests alone.
