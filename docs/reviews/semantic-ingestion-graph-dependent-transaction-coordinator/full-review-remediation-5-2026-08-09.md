# Design Review: Graph-Dependent Transaction Coordinator Remediation 5

## Review Metadata

- Review ID: semantic-ingestion-graph-dependent-transaction-coordinator-remediation-5-2026-08-09
- Review mode: full
- Review outcome: Changes required
- Design path: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/design.plan.md`
- Design baseline: SHA-256 `b13906988c4265afc4ad9358e0834c65bd371d87f0a0a8d1d9926af993f29f36`
- Implementation baseline: Git HEAD `4691c0374b3b01617a6a50fd83d4e3ff8a61aa84`
- Review date: 2026-08-09
- Reviewers: independent `spec_auditor`, `correctness_reviewer`, and `test_reviewer`; Codex reconciliation
- Included scope: GTC-R01 through GTC-R13 and DREV-001 through DREV-019 remediation
- Excluded scope: implementation, M4, performance execution, external signing, and unrelated dirty-tree changes

## Executive Assessment

Changes required. One supported final-before-planning group lacks a representable
successor closure arm, and the proposed CI owner entry does not match the
repository's enforced job-ID/schema contract.

## Governing Sources

`AGENTS.md`; `.agents/PLANS.md`; v5 candidate; canonical architecture; current
group-result/authority contracts; deterministic owner ledger and static tests;
paired terminal WorkPlan.

## Independently Reconstructed Requirements

| Requirement | Acceptance criteria | Status |
| --- | --- | --- |
| GTC-R07, R09--R11 | Final no-authority groups survive replans without gaining CAS authority | incomplete |
| GTC-R01--R13 | Dedicated job identity and owner entry match enforced repository schema | incomplete |

## Contract And Evidence Boundaries

Finality does not imply authorization. Workflow machine ID, display name, runtime
budget, timeout, headroom, and timing ownership are separate fields.

## Confirmed Findings

### DREV-020: Final-before-planning group lacks a no-authority successor arm

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: lifecycle, persisted authority, recovery, and replay
- Affected scenario and prevalence evidence: A terminal non-committing group finishes before planning, then another group enters pre-commit or partial-commit conflict replan.
- Design location: successor group-authority union, non-committing final-result reference, and null-authority terminal rules.
- Governing source or requirement: GTC-R07 and GTC-R09--R11.
- Expected behavior: The final group remains in successor/replay closure, never reruns, and never gains compilation or CAS authority.
- Design behavior: The final result permits null authority, but its reference and both successor authority arms require non-null predecessor or replacement authority.
- Evidence: The group must otherwise be omitted, assigned fabricated predecessor authority, or reauthorized after finality.
- Impact: A supported multi-group replan is unrepresentable and cannot recover exactly.
- Root invariant or contract boundary: Final no-authority state is a typed immutable closure, not authorization.
- Equivalence class and adjacent bypasses inspected: all non-committing statuses before/after planning, zero/some commits, crash/reopen/replay/rollback.
- Positive behavior that must remain valid: Existing reused and replacement arms remain exact; only unfinished replanned groups gain new authority.
- Recommended invariant-level resolution: Add a strict third reused-final-no-authority arm bound to predecessor final lineage, plan member, final result, and explicit null authority; make nullable final-result authority legal only for this arm and forbid compilation/CAS.
- Verification needed: Memory/JSONL A-final/B-conflict and C-committed/A-final/B-conflict matrices with substitution and recovery mutations.
- Evidence maturity affected: specified and derivable.

### DREV-021: CI owner identity and schema do not match enforced tooling

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: evidence_action
- Confidence: high
- Finding type: verification and CI governance
- Affected scenario and prevalence evidence: Every graph-dependent required PR run.
- Design location: graph CI owner-ledger contract and current static owner validation.
- Governing source or requirement: GTC-R01--R13, DREV-016, and DREV-019.
- Expected behavior: The ledger is keyed by workflow job ID and supplies every required current field with measured budget/headroom semantics.
- Design behavior: It names the display name as the key and specifies only a new measured-budget field.
- Evidence: Existing validation requires `timeout_minutes`, `runtime_budget_seconds`, `timeout_headroom_seconds`, and `timing_exemption_reason` under machine job IDs.
- Impact: Literal implementation fails static topology validation or silently requires an unspecified global migration.
- Root invariant or contract boundary: Design targets the actual enforced owner schema exactly.
- Equivalence class and adjacent bypasses inspected: ID/display mismatch, missing/extra owner, budget maximum, timeout/headroom, timing mode, aggregate and topology mutations.
- Positive behavior that must remain valid: Three candidate runs determine the budget and graph timing remains independently owned.
- Recommended invariant-level resolution: Specify job ID `graph-dependent-semantic-ingestion`, display name separately, full existing ledger fields, runtime budget as max of three runs, headroom equation, and explicit timing-exemption/owned-receipt interpretation or a versioned migration.
- Verification needed: Static mutations for every field, mapping, budget, headroom, receipt, aggregate, overlap and orphan case.
- Evidence maturity affected: CI enforced.

## Requirements Coverage

DREV-001--019 otherwise remain materially addressed; these two gaps prevent
bounded approval.

## Architecture And Feasibility

Both fixes are closed schema corrections with no new owner or external decision.

## Failure, Security, And Operations

No-authority terminal groups must remain visible for recovery but forever
ineligible for graph effects.

## Verification And Evidence Maturity

The four v5 hashes and paired scope reproduced. Implementation remains absent.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Status |
| --- | --- | --- | --- | --- |
| final group gains or loses authority | successor replan | replay/CAS violation | no-authority arm | open |
| owner ledger cannot validate | workflow implementation | false/broken gate | exact current schema | open |

## Rejected Or Consolidated Findings

- Spec and correctness findings are the same DREV-020.
- The test review's independently numbered DREV-020 is DREV-021.
- Reviewer P2 was reconciled to Not applicable because the path is not implemented; approval remains changes_required.

## Required Changes Before Approval

Close DREV-020 and DREV-021, freeze a sixth candidate, and run a fresh full review.

## Non-Blocking Follow-Ups

Performance execution, M4, signing, and unrelated repairs remain separate.

## Final Outcome

Changes required.

## Review Limitations

Read-only v5 review; no implementation or runtime certification.
