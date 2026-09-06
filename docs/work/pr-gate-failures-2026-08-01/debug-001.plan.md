# PR Gate Failures At Revision ae163919

- Work ID: pr-gate-failures-2026-08-01
- Work type: debugging
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-08-01
- Last updated: 2026-08-01
- Parent WorkPlan: docs/work/test-gate-architecture/testing.plan.md
- Related WorkPlans: docs/work/semantic_ingestion/implementation.plan.md
- Canonical inputs: GitHub Actions run 30721582991; revision ae163919376be9ad8e5f9106bb4ecb925fb9dfef; .github/workflows/pr-gates.yml
- Expected outputs: Deterministic root-cause fixes for every originating failure, regression proof, and green affected local gates

## Objective

Make every originating failure in GitHub Actions run 30721582991 pass without
weakening semantic-ingestion, compatibility, traceability, timing, or umbrella
failure-propagation contracts.

## Completion Contract

Complete only when the three originating failures (CTV Binding Authority PR
Gate, Provider Compatibility Recapture, and Unit Test Shard 2) have confirmed
causal explanations, smallest safe fixes, deterministic local regression
proof, surrounding gate verification, and independent spec, correctness, and
test reviews with every finding reconciled. `Unit Tests` is derivative and must
remain fail closed on dependency failure.

## Scope

Included: the four linked jobs in run 30721582991, their test/runtime support,
workflow composition, fixtures, and diagnostics. Excluded: unrelated product
semantics and M2. Deferred: GitHub rerun evidence until the user pushes.

## Constraints And Invariants

- Preserve all tests and fail-closed branch-protection behavior.
- Preserve exact traceability and provider compatibility authority bindings.
- Do not make Linux-only failures pass by weakening validation.
- Keep every PR job within 15 minutes.
- Follow `docs/IMPLEMENTATION_RULES.md`, `docs/development/static_tooling.md`,
  and the semantic-ingestion governing design.

## Sources Of Truth

1. GitHub job metadata and available annotations for run 30721582991.
2. Exact test code and workflow at revision ae163919.
3. Local deterministic reproductions and generated authority artifacts.
4. Governing repository design documents under the precedence in AGENTS.md.

## Current State

Verified: the PR Gate tamper suite, provider recapture integration test, and
unit shard 2 are originating failures. The `Unit Tests` umbrella fails because
its dependencies failed. GitHub CLI authentication is unavailable inside this
task, so complete hosted logs are not yet available; public job metadata is.

## Assumptions And Open Questions

- Verified fact: local HEAD equals the failed revision.
- Disproved assumption: the CTV/shard failure is Linux-specific. The exact
  assertion reproduces locally.
- Verified fact: the pinned compatibility commit is reachable on GitHub but is
  not an ancestor of the PR revision; full current-ref history does not include
  it.
- Unresolved: none for the confirmed originating failure families.
- External decisions: none.

## Milestones Or Experiments

### Experiment 1: Exact local gate reproduction

- Hypothesis: failures reproduce at the same revision through the documented
  workflow commands.
- Discriminating observation: identical failing test and exception locally.
- Procedure: run the exact three originating commands independently.
- Expected outcomes: reproduction identifies causal boundary; a pass narrows
  the cause to Linux, checkout, dependency, or runner environment.
- Actual result: CTV gate reproduced with one stale `unit-tests.needs`
  assertion; shard 2 reproduced the identical single failure. Provider
  recapture passed locally because the local clone contains the unrelated
  baseline branch object.
- Conclusion: CTV and shard 2 are one workflow-contract test defect. Provider
  recapture requires a repository-state experiment.
- Evidence location: this plan Evidence Log.

### Experiment 2: Environment and authority discrimination

- Hypothesis: hosted failures are caused by runner-specific path, Git state,
  interpreter, or generated-authority assumptions rather than product logic.
- Discriminating observation: minimal simulation changes only the suspected
  environmental variable and reproduces the hosted symptom.
- Procedure: selected after Experiment 1.
- Expected outcomes: one causal mechanism explains each failure family.
- Actual result: GitHub API returns the pinned commit, local branch containment
  shows it exists on `live-benchmark-repair`, and `git merge-base --is-ancestor`
  returns false for the PR revision. Checkout `fetch-depth: 0` therefore cannot
  guarantee the object.
- Conclusion: the provider gate must fetch the exact pinned revision explicitly.
- Evidence location: this plan Evidence Log.

### Milestone 1: Root-cause correction and family proof

- Purpose: correct confirmed invariant violations without reducing coverage.
- Bounded scope: affected workflow, test support, fixtures, and regression tests.
- Expected artifacts: implementation patch and deterministic regression proof.
- Verification method: exact affected gates plus surrounding static/planner checks.
- Status: complete; independent closure review approved.

## Progress Log

- 2026-08-01: Mapped job metadata. Three originating failures and one derived
  umbrella failure confirmed. Next action is exact local reproduction.
- 2026-08-01: Exact CTV gate reproduced: 18 passed and one stale workflow
  assertion failed. Exact shard 2 reproduced the same failure: 731 passed, one
  skipped, one failed. Provider recapture passed locally. GitHub reachability
  and ancestry checks isolated its failure to an unrelated pinned commit not
  included by full current-ref history. Next action is implement both confirmed
  invariant-level corrections.
- 2026-08-01: Updated the stale workflow assertion, replaced broad history
  checkout with an exact shallow fetch of the tool-owned pinned SHA, and added
  structural tests for fetch source, object verification, and ordering. A fresh
  temporary Git repository fetched that exact SHA from GitHub with `--depth=1`
  and verified the commit object. Next action is independent closure review.
- 2026-08-01: Reconciled closure review findings by documenting the exact pinned
  fetch and complete umbrella dependency set, guarding provider-result binding
  and fail-closed propagation, and leaving the new documentation test unmeasured
  until CI records real timing. All independent reviewers approved the delta.
- 2026-08-01: Hosted rerun 30722833501 failed immediately in the new pinned
  fetch step. Exact execution of its Python lookup reproduced
  `ModuleNotFoundError`: the workflow named `memorii.tools`, but repository tools
  are imported from top-level `tools` when running in `memorii/`. Next action is
  replace the invalid namespace and add executable regression proof.
- 2026-08-01: Replaced the invalid namespace and strengthened the regression to
  execute the exact `BASELINE_REVISION` assignment from the workflow-declared
  working directory, comparing its output to the canonical tool constant.
  Focused contracts and recapture passed; all closure reviewers approved.

## Evidence Log

- GitHub run 30721582991, revision ae163919376be9ad8e5f9106bb4ecb925fb9dfef.
- Job 91426149469: `Run CTV PR-gate tamper tests` failed.
- Job 91426149481: `Verify deterministic historical provider recapture` failed.
- Job 91426149518: `Run deterministic unit shard` failed for shard 2.
- Job 91426701874: umbrella dependency assertion failed as designed.
- Local CTV gate: 18 passed, one failed in 119.94 seconds; failure at
  `test_ctv_binding_authority_pr_gate.py:219`.
- Local shard 2: 731 passed, one skipped, one identical failure in 239.30
  seconds.
- GitHub commit API for pinned revision f76850f returned HTTP 200; local branch
  containment places it on `live-benchmark-repair`, not the PR ancestry.
- Fresh GitHub fetch experiment: `git fetch --no-tags --depth=1 origin
  f76850f...` succeeded and `git cat-file -e <sha>^{commit}` passed in a new
  shallow repository.
- Final CTV and workflow contract suites: 30 passed in 121.55 seconds.
- Repaired shard 2: 732 passed, one skipped in 240.57 seconds.
- Final shard planner: 2,383 collected, 2,382 measured, one fallback-planned;
  longest predicted shard 288.942 seconds against the 600-second target.
- Provider compatibility recapture: one passed in 11.05 seconds.
- Hosted run 30722833501 job 91429288841: install passed; pinned fetch step
  failed immediately; recapture was skipped. The exact lookup fails locally as
  `No module named 'memorii.tools.extract_provider_compatibility_fixture'`, while
  `from tools.extract_provider_compatibility_fixture import BASELINE_REVISION`
  returns the pinned SHA.
- Final workflow contracts plus provider recapture: 12 passed in 9.68 seconds;
  Ruff and diff whitespace checks passed.
- Ruff and scoped Pyright: zero findings.

## Decision Log

- 2026-08-01: Treat the umbrella failure as derivative; preserve it unchanged
  unless evidence shows propagation is incorrect.
- 2026-08-01: Replace broad current-ref history checkout with an explicit fetch
  of the tool-owned pinned revision. This is narrower, deterministic, and does
  not depend on a temporary branch name.

## Review Log

- Spec audit: stale complete-history guidance required correction. Confirmed,
  corrected to exact shallow pinned fetch, guarded, and approved on delta review.
- Correctness review: incomplete umbrella documentation was P3/follow-up.
  Confirmed, corrected to include provider recapture and timing inventory, and
  approved on delta review with no remaining findings.
- Test review: synthetic fallback timing entry and missing provider-result
  propagation guards were P3/follow-up. Confirmed; the synthetic entry was
  removed, explicit binding/success assertions were added, and delta closure
  approved with no remaining code or test findings.
- Hosted-import closure: spec and correctness reviewers found no gap. Test
  review required binding the executable proof to the exact assignment,
  workflow working directory, and canonical SHA; remediated and approved on
  delta review with no remaining findings.

## Blockers And Limits

Hosted log bodies are unavailable because the Codex `gh` credential is invalid.
Exact-revision reproduction and GitHub repository-state evidence were
sufficient to confirm the earlier root causes. The first hosted rerun exposed
an invalid Python namespace in the new fetch command; complete hosted log text
remains unavailable, but exact command reproduction and step timing identify
the failure before any Git operation.

## Next Action

User pushes the two-file correction and observes the hosted provider gate.

## Outcome And Retrospective

Complete after hosted-failure remediation. Two originating failures shared one stale workflow-contract
expectation; the provider failure came from assuming full current-ref history
contained an unrelated pinned commit. Exact object fetch is both narrower and
more reliable. The derived umbrella still fails closed, and all affected local
gates, planner checks, and independent reviews are green. Hosted confirmation
is intentionally deferred until push.
