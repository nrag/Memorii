# Design Review: Graph-Dependent Transaction Coordinator Remediation 7

## Review Metadata

- Review ID: semantic-ingestion-graph-dependent-transaction-coordinator-remediation-7-2026-08-10
- Review mode: full
- Review outcome: Changes required
- Design path: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/design.plan.md`
- Design baseline: SHA-256 `657d15fcfaacd31b686027f871171b4339e36c065d3f39f6f5d43393c8c8d284`
- Implementation baseline: Git HEAD `4691c0374b3b01617a6a50fd83d4e3ff8a61aa84`
- Review date: 2026-08-10
- Reviewers: independent `spec_auditor`, `correctness_reviewer`, and `test_reviewer`; Codex reconciliation
- Included scope: GTC-R01 through GTC-R13 and DREV-001 through DREV-024 remediation
- Excluded scope: implementation, M4, performance execution, external signing, and unrelated dirty-tree changes

## Executive Assessment

Changes required. The typed proof still needs an explicit verified lifecycle
cutoff predicate, and the CI aggregate must explicitly propagate producer and
receipt-aggregator failures despite `if: always()`.

## Governing Sources

`AGENTS.md`; `.agents/PLANS.md`; v7 candidate; execution-manifest lifecycle and
authority contracts; current PR aggregate behavior; paired terminal WorkPlan.

## Independently Reconstructed Requirements

| Requirement | Acceptance criteria | Status |
| --- | --- | --- |
| GTC-R07, R10--R11 | Proof establishes a manifest-backed before-planning lifecycle fact | incomplete |
| GTC-R01--R13 | Failed/skipped/cancelled graph evidence makes semantic aggregate fail | incomplete |

## Contract And Evidence Boundaries

Typed evidence must prove its semantic predicate, not only internal equality.
An `if: always()` aggregate is fail-closed only through explicit result checks.

## Confirmed Findings

### DREV-025: Proof does not establish the before-planning lifecycle predicate

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: lifecycle, authorization, recovery, and replay
- Affected scenario and prevalence evidence: Every no-authority final group in a successor replan.
- Design location: `TerminalBeforePlanningProof`, its repository load validation, and no-authority arm admission.
- Governing source or requirement: SIA-R04 and GTC-R07/R10/R11.
- Expected behavior: The exact group attempt terminally stopped at an allowed stage before planning; later stages never started; authority/compilation are absent; the outcome is in the sealed manifest.
- Design behavior: The proof carries an unconstrained stage outcome and equality joins but no cutoff, stage allowlist, attempt/group scope checks, manifest membership, or later-stage absence rule.
- Evidence: A post-planning or unrelated outcome can be internally self-consistent and accepted.
- Impact: Planned work can be misclassified as no-authority and replayed under the wrong arm.
- Root invariant or contract boundary: Phase exceptions are verified against the canonical lifecycle DAG and sealed manifest.
- Equivalence class and adjacent bypasses inspected: wrong scope/group/attempt, post-planning stage, nonterminal status, nonempty authority, completed compilation, missing successors, recovery/replay.
- Positive behavior that must remain valid: Legitimate no-authority terminals remain immutable, CAS-forbidden, and not rerun.
- Recommended invariant-level resolution: Define a closed planning-cutoff predicate and allowed terminal stage/status set; load exact attempt and manifest; prove canonical membership, matching coordinates, empty authority/compilation, and every planning-or-later stage not started.
- Verification needed: Memory/JSONL lifecycle and manifest mutation matrix before successor publication/read/CAS.
- Evidence maturity affected: specified and derivable.

### DREV-026: Graph evidence failure is not explicitly propagated by the aggregate

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: evidence_action
- Confidence: high
- Finding type: verification and CI governance
- Affected scenario and prevalence evidence: Any failed, skipped, or cancelled graph measurement/receipt job.
- Design location: receipt aggregator and `Semantic Ingestion` dependency contract.
- Governing source or requirement: GTC-R01--R13 and current `if: always()` aggregate semantics.
- Expected behavior: Aggregator diagnoses every producer result and publishes only after three successes; semantic aggregate explicitly asserts aggregator success.
- Design behavior: Dependency edges are specified without mandatory result environment/assertion rules.
- Evidence: Existing aggregate can remain green under `if: always()` when a new dependency result is omitted from its assertion chain.
- Impact: A failed graph gate can be success-shaped at the required aggregate.
- Root invariant or contract boundary: Required aggregate explicitly checks every dependency result.
- Equivalence class and adjacent bypasses inspected: failed/skipped/cancelled producer, missing aggregator always/check, retained edge with removed assertion, aggregate omission.
- Positive behavior that must remain valid: Diagnostics run under `always()` and no inventory is published from incomplete evidence.
- Recommended invariant-level resolution: Require aggregator `if: always()` plus explicit success checks for all three producers; require `GRAPH_RECEIPT_AGGREGATE_RESULT` and exact success assertion in `Semantic Ingestion`; add static mutations.
- Verification needed: Workflow structure and failure-propagation mutation suite.
- Evidence maturity affected: CI enforced.

## Requirements Coverage

DREV-001--024 otherwise remain materially addressed. These two gaps prevent approval.

## Architecture And Feasibility

Both changes are narrow validation/enforcement additions.

## Failure, Security, And Operations

Lifecycle proof and aggregate failure propagation must remain fail closed.

## Verification And Evidence Maturity

The v7 hashes and paired scope reproduced; no implementation claim exists.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Status |
| --- | --- | --- | --- | --- |
| post-planning outcome accepted | forged proof | wrong authority arm | cutoff/manifest predicate | open |
| failed graph evidence hidden | aggregate always runs | false green | explicit result checks | open |

## Rejected Or Consolidated Findings

- Specification approved v7; correctness DREV-025 and test review's independently numbered DREV-025 are distinct, with the latter renumbered DREV-026.

## Required Changes Before Approval

Close DREV-025 and DREV-026, freeze an eighth candidate, and run fresh full review.

## Non-Blocking Follow-Ups

Performance execution, M4, signing, and unrelated repairs remain separate.

## Final Outcome

Changes required.

## Review Limitations

Read-only v7 review; no implementation or runtime certification.
