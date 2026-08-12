# Design Review: Graph-Dependent Transaction Coordinator Remediation 4

## Review Metadata

- Review ID: semantic-ingestion-graph-dependent-transaction-coordinator-remediation-4-2026-08-09
- Review mode: full
- Review outcome: Changes required
- Design path: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/design.plan.md`
- Design baseline: SHA-256 `f2d7095de01c5e1b939b1ba324c34bcb44453dd21511d759f12d9e65e9c519ac`
- Implementation baseline: Git HEAD `4691c0374b3b01617a6a50fd83d4e3ff8a61aa84`
- Review date: 2026-08-09
- Reviewers: independent `spec_auditor`, `correctness_reviewer`, and `test_reviewer`; Codex reconciliation
- Included scope: GTC-R01 through GTC-R13 and DREV-001 through DREV-016 remediation
- Excluded scope: implementation, M4, performance optimization, external signing, and unrelated dirty-tree changes

## Executive Assessment

Changes required. The complete-plan model still conflates reused predecessor
authority with new-plan authorization, omits final non-committing results from
replan closure, and depends on a terminal-topology handoff that is not frozen.

## Governing Sources

`AGENTS.md`; `.agents/PLANS.md`; v4 candidate; canonical architecture; current
authorization, lineage, result, replay, CI, and terminal-testing WorkPlans.

## Independently Reconstructed Requirements

| Requirement | Acceptance criteria | Status |
| --- | --- | --- |
| GTC-R06--R11 | Reused predecessor and replacement successor authority are typed distinctly | incomplete |
| GTC-R09--R11 | Every final result variant survives replacement planning | incomplete |
| GTC-R01--R13 | Paired test-owner handoff is acknowledged and frozen | blocked |

## Contract And Evidence Boundaries

Authority reuse is a reference to predecessor bytes, not a new-plan
authorization. Finality includes committed and non-committing terminal results.
Cross-WorkPlan evidence transfer must be in one frozen review scope.

## Confirmed Findings

### DREV-017: Successor attempt cannot represent reused predecessor authority

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: persisted authority and recovery
- Affected scenario and prevalence evidence: Every complete successor plan that reuses at least one committed or untouched group.
- Design location: `GroupPlanningAuthorization`, `GraphDependentValidationAttempt`, and successor effective-plan authorization rules.
- Governing source or requirement: GTC-R06--R11.
- Expected behavior: Reused groups prove immutable predecessor authority; replacement groups carry successor-plan authorization; the successor attempt validates a complete group bijection.
- Design behavior: Reused authorizations must be byte-identical but also occur as successor-plan authorizations, while the existing type embeds the predecessor plan reference.
- Evidence: Attempt validation requires each `GroupPlanningAuthorization.group_plan` to equal its attempt plan, which byte-identical predecessor authorization cannot satisfy.
- Impact: Any mixed reused/replacement successor attempt is unrepresentable.
- Root invariant or contract boundary: Reused authority and newly issued authority are distinct typed variants with one complete effective-group bijection.
- Equivalence class and adjacent bypasses inspected: committed reuse, unfinished reuse, replacement, reopen, replay, substitution, and result binding.
- Positive behavior that must remain valid: Predecessor authorization bytes remain immutable and only replacements receive new authority.
- Recommended invariant-level resolution: Define a discriminated successor-attempt authority union: predecessor-lineage authorization reference for reused groups and successor-plan `GroupPlanningAuthorization` for replaced groups, with exact digest/reload/result/replay joins.
- Verification needed: Mixed successor vectors and predecessor/plan/group/authorization substitution tests in memory and JSONL.
- Evidence maturity affected: specified and derivable.

### DREV-018: Replan closure omits final non-committing group results

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: lifecycle, result integrity, and replay
- Affected scenario and prevalence evidence: A group finishes evidence-only, rejected, unresolved, or failed before another group replans.
- Design location: Replan closure and intermediate progress final-result fields.
- Governing source or requirement: GTC-R09--R11.
- Expected behavior: Every final predecessor group result remains immutable and referenced across successor states.
- Design behavior: Replan intermediates retain committed-result references only; final non-committing groups are neither retained nor unfinished.
- Evidence: Prior planned progress carries all terminal result digests, but the successor closure narrows them to `CommittedTransactionGroupResultReference`.
- Impact: Recovery may omit, rerun, or reconstruct a final group from unspecified history.
- Root invariant or contract boundary: Predecessor groups partition completely into final and unfinished, with replanned a subset of unfinished.
- Equivalence class and adjacent bypasses inspected: all terminal variants, zero/some commits, crash/lost ack/stale owner, rollback and finalization.
- Positive behavior that must remain valid: Only unfinished retryable groups are replaced; committed authority stays immutable.
- Recommended invariant-level resolution: Use a canonical typed final-result reference union for committed and non-committing variants in both replan intermediates and replay closure; validate complete predecessor partition and bind all digests.
- Verification needed: Every terminal-variant A/B conflict matrix in memory and JSONL with exact no-rerun/no-omission checks.
- Evidence maturity affected: specified and derivable.

### DREV-019: Paired terminal-topology handoff is outside the frozen candidate

- Product priority: Not applicable
- Approval disposition: blocks_approval
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: verification governance
- Affected scenario and prevalence evidence: Every graph test node transferred from the active terminal-persistence owner.
- Design location: Graph CI handoff dependency, terminal-persistence testing WorkPlan, and candidate identity.
- Governing source or requirement: DREV-013/DREV-016 and fixed-scope review rules.
- Expected behavior: The old owner acknowledges the exact transfer and both plans are pinned in one candidate.
- Design behavior: The graph plan requires the handoff, while the terminal plan remains unchanged and unpinned.
- Evidence: The terminal plan still records unresolved 224-collected/156-timed topology and no graph handoff.
- Impact: Review cannot prove one atomic, exclusive owner transition.
- Root invariant or contract boundary: Evidence ownership moves only through an acknowledged, content-addressed handoff.
- Equivalence class and adjacent bypasses inspected: transferred/residual nodes, timing inventory, seven shards, owner ledger, aggregate.
- Positive behavior that must remain valid: The terminal performance effort retains residual ownership and graph correctness remains separate.
- Recommended invariant-level resolution: Add a narrow dependency acknowledgment and recalculation acceptance contract to the terminal testing WorkPlan, then pin that file in the next candidate identity.
- Verification needed: Candidate hash reproduction and paired topology review.
- Evidence maturity affected: specified and CI enforced.

## Requirements Coverage

Other DREV-001--016 contracts remain materially addressed. These three items
prevent bounded approval.

## Architecture And Feasibility

The fixes refine existing unions and ownership records; no new semantic owner is
required.

## Failure, Security, And Operations

Reused authority must never be silently reissued, and every final result must
survive recovery. Current authorization-before-lookup remains intact.

## Verification And Evidence Maturity

The v4 identity reproduced. The paired topology input did not exist in scope.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Status |
| --- | --- | --- | --- | --- |
| predecessor authority masquerades as successor | mixed replan | invalid attempt | authority union | open |
| final noncommit result disappears | later group conflict | replay/finalization mismatch | final-result union | open |
| test owner handoff unreviewable | topology transfer | duplicate/orphan evidence | paired frozen plans | blocked |

## Rejected Or Consolidated Findings

- The reviewer P2 label for DREV-017 is reconciled to Not applicable because the graph-bound path is not implemented; `changes_required` remains.
- The test review blocker is DREV-019, distinct from runtime design findings.

## Required Changes Before Approval

Close DREV-017--DREV-019, freeze a fifth candidate including the paired terminal
WorkPlan, and run a fresh full review.

## Non-Blocking Follow-Ups

Runtime performance optimization, M4, signing, and unrelated repairs remain separate.

## Final Outcome

Changes required.

## Review Limitations

Read-only v4 design review; no implementation or runtime certification.
