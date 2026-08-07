# Design Review: Layer 1 Validator Collection Grammar Closure

## Review Metadata

- Review ID: semantic-ingestion-layer1-validator-collection-closure-delta-05
- Review mode: delta
- Review outcome: Changes required
- Design path: `docs/design/semantic_ingestion_architecture.md` plus the linked executable validator and checker
- Design baseline: architecture SHA-256 `67bf2620a0379761853861e416efba0816045ef4bf88e4808e701a9ac3bc993e`; validator candidate SHA-256 `7a0f9563827ca7aa4a7683493914f00bcbd71e73d1d6c9924f80f446001002a4`; checker candidate SHA-256 `9e7e28196e9bb7ca7b50365937266d8330e6f26b16b43b94b8b0b588629fb240`
- Implementation baseline: `945d6ea03649ca13c800e84bcb9972797e0f0a31` with the current working-tree Layer1 candidate
- Review date: 2026-07-29
- Reviewers: fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer`; coordinator reconciliation
- Included scope: publication-invariant remediation, content-addressed replica execution, checker audit isolation, and deterministic evidence
- Excluded scope: implementation consumer repins and remote CI execution

## Executive Assessment

The validator's publication behavior now closes DREV-008 through DREV-010 and
the spec audit supports approval of that boundary. Approval still cannot be
granted because the checker verifies input bytes and later rereads their paths
for hermetic execution, allowing a concurrent substitution. Two smaller proof
gaps also remain for real directory-open failure state and negative
filesystem-audit enforcement.

## Governing Sources

- Root `AGENTS.md`, `.agent/PLANS.md`, and the build/review Design Skills
- `docs/design/semantic_ingestion_architecture.md`, Section 3.23.4.2.1
- `docs/work/semantic_ingestion/layer1-validator-collection-closure-2026-07-29/design.plan.md`
- Immutable delta reports 01 through 04 in this review directory

## Independently Reconstructed Requirements

| Requirement | Source | Design coverage | Acceptance criteria | Verification | Status |
| --- | --- | --- | --- | --- | --- |
| VLC-001 | Closed unary collections | Complete | Invalid collection shapes reject | Self-test and exact checker | locally verified |
| VLC-002 | Closed tuple grammar | Complete | Finite or exact variadic forms; all boundaries proved | Self-test and exact checker | locally verified |
| VLC-003 | Content-addressed validator/checker | Partial | Replicas execute exactly the captured verified bytes; audit denies undeclared reads | Snapshot-race and negative audit proof | changes required |
| VLC-004 | Fail-closed compatible publication | Behavior complete; evidence partial | All real/unsupported directory-open outcomes assert complete filesystem state | Deterministic failpoint matrix | changes required |

## Contract And Evidence Boundaries

Identity verification and replica execution are one content-addressed
transaction. The checker must capture each source once, validate that snapshot,
and materialize only those captured bytes. Path rereads cannot participate in
execution. The runtime audit hook is part of the trust boundary and requires a
negative known-answer probe, not only positive executions.

## Confirmed Findings

### DREV-011: Checker hashes inputs but executes later, unverified path contents

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: security / concurrency / content-addressed authority boundary
- Affected scenario and prevalence evidence: Concurrent replacement of the validator, design, or registry path between checker identity verification and hermetic replica materialization; this is trust-tooling behavior without a product-prevalence claim.
- Design location: Checker `main()` identity capture and replica construction
- Governing source or requirement: VLC-003 and the content-addressed hermetic handoff
- Expected behavior: Both replicas execute exactly the design, registry, and validator byte snapshots whose hashes were accepted.
- Design behavior: The checker stores verified bytes, then uses `shutil.copyfile()` on the three source paths for each replica.
- Evidence: Direct code inspection at the identity reads and later replica copies. A source path can be atomically substituted after hashing and restored before the final design/registry reread; the validator has no final reread.
- Impact: The checker can report reviewed identities while executing different bytes, defeating the content-addressed evidence claim.
- Root invariant or contract boundary: Capture, verification, and execution must share one immutable byte snapshot per input.
- Equivalence class and adjacent bypasses inspected: Validator, design, registry, authority, checker self-hash, both replicas, source restoration, and final rereads.
- Positive behavior that must remain valid: Two isolated replicas, closed imports/filesystem audit, exact checked-authority equality, and input identity diagnostics.
- Recommended invariant-level resolution: Materialize the already captured `design`, `registry`, and `validator` byte variables into replicas; remove path rereads and add a deterministic source-swap seam proving execution is snapshot-bound.
- Verification needed: Swap each source path after capture and prove the replica inputs remain the captured bytes; retain exact two-replica equality and content-addressed output.
- Evidence maturity affected: VLC-003 approval

### DREV-012: Directory-open failure and audit-denial evidence are incomplete

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: verification / transactional recovery and authority isolation
- Affected scenario and prevalence evidence: A real directory-open error after replacement and an import-valid validator attempting an undeclared filesystem read; these are trust-boundary evidence cases without a product-prevalence claim.
- Design location: Validator post-replace test matrix and checker replica audit
- Governing source or requirement: VLC-003 and VLC-004
- Expected behavior: A real directory-open error surfaces after exact new bytes, preserved mode, existing target, and no temporary sibling; an import-valid validator with an undeclared read is denied by the replica audit.
- Design behavior: Real directory-fsync error is covered, but real directory-open error and post-replace existence/mode assertions are not. The checker runs positive audited replicas but no negative audit probe.
- Evidence: Fresh test-review inspection of `assert_post_replace_behavior()` and the checker bootstrap/audit execution path.
- Impact: A regression in open-error classification or audit-hook enforcement can pass all current evidence.
- Root invariant or contract boundary: Each trust-boundary branch must have an observable known-answer failure or state assertion.
- Equivalence class and adjacent bypasses inspected: Unsupported/real directory open and fsync; bytes, existence, mode, temp cleanup; import-valid undeclared read; validator hash recomputation; authority preservation.
- Positive behavior that must remain valid: Current complete publication matrix, narrow audit allowlist, exact replicas, and deferred parent public subprocess proof.
- Recommended invariant-level resolution: Add real directory-open EIO with complete post-replace state assertions; add a checker-owned adversarial replica probe that uses an allowed import but attempts an undeclared read and must fail specifically at the audit hook.
- Verification needed: Deterministic validator failpoint and checker negative known-answer probe, followed by exact two-replica checker.
- Evidence maturity affected: VLC-003 and VLC-004 local verification

## Requirements Coverage

VLC-001 and VLC-002 are locally verified. VLC-003 is blocked by the snapshot
TOCTOU and negative audit-proof gap. VLC-004 behavior is locally correct but
requires the final real-open state assertion.

## Architecture And Feasibility

The correction is bounded: replace checker path copies with writes from already
verified memory, add checker-owned deterministic adversarial evidence, and
complete one validator state case. No normative architecture, registry,
authority, profile, or implementation-runtime change is required.

## Failure, Security, And Operations

The checker must not depend on source-path stability after capture. Negative
audit evidence must not weaken the allowlist or introduce a production bypass.

## Verification And Evidence Maturity

Validator self-test and the exact checker pass at `7a0f9563...` /
`9e7e2819...`, reproducing authority `89a98fc1...`, 56 schemas, 240 enum rows,
and profile `20edd38a...`. Snapshot binding and audit denial remain unproved.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Residual risk | Status |
| --- | --- | --- | --- | --- | --- |
| Verified/executed bytes diverge | Concurrent source-path replacement | False content-addressed approval | Execute captured snapshots only | Low | open |
| Audit hook is ineffective | Undeclared read in allowed-import validator | Hermetic isolation bypass | Negative audit known-answer probe | Low | open |
| Real directory-open error regresses | Cross-filesystem I/O error | Incorrect publication state claim | Complete state assertions | Low | open |

## Rejected Or Consolidated Findings

The spec reviewer found no remaining publication or handoff gap. The test
reviewer's real-open and audit-denial observations are consolidated in
DREV-012. Parent workflow/test pins remain an explicit post-approval
implementation handoff, not a design-local finding.

## Required Changes Before Approval

Close DREV-011 and DREV-012 in one snapshot-and-isolation correction, rerun all
deterministic gates, then perform fresh three-role delta review.

## Non-Blocking Follow-Ups

After design approval, repin all implementation consumers, run the public CLI
matrix, and obtain remote CI/branch-protection evidence when available.

## Final Outcome

Changes required.

## Review Limitations

Remote CI and adversarial production filesystems were not exercised.
