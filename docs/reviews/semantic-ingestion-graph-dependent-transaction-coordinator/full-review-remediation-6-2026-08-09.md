# Design Review: Graph-Dependent Transaction Coordinator Remediation 6

## Review Metadata

- Review ID: semantic-ingestion-graph-dependent-transaction-coordinator-remediation-6-2026-08-09
- Review mode: full
- Review outcome: Changes required
- Design path: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/design.plan.md`
- Design baseline: SHA-256 `3983d07495cfa30d12ee8975108446b62312356d00917fc8b9c28839f4a610f7`
- Implementation baseline: Git HEAD `4691c0374b3b01617a6a50fd83d4e3ff8a61aa84`
- Review date: 2026-08-09
- Reviewers: independent `spec_auditor`, `correctness_reviewer`, and `test_reviewer`; Codex reconciliation
- Included scope: GTC-R01 through GTC-R13 and DREV-001 through DREV-021 remediation
- Excluded scope: implementation, M4, performance execution, external signing, and unrelated dirty-tree changes

## Executive Assessment

Changes required. The no-authority exemption needs a typed loadable proof and an
arm-specific reverse join. The three-sample CI budget also needs a feasible
producer/consumer topology and immutable ceiling semantics.

## Governing Sources

`AGENTS.md`; `.agents/PLANS.md`; v6 candidate; canonical typed-artifact and
replay rules; workflow owner schema; paired terminal WorkPlan.

## Independently Reconstructed Requirements

| Requirement | Acceptance criteria | Status |
| --- | --- | --- |
| GTC-R07, R10--R11 | No-authority exemption is justified by typed replay-loadable evidence | incomplete |
| GTC-R08, R10--R11 | Immutable predecessor result is reverse-linked, never backfilled | incomplete |
| GTC-R01--R13 | Budget samples and immutable ceiling have feasible artifact flow | incomplete |

## Contract And Evidence Boundaries

A digest identifies evidence but is not the evidence. A later closure can point
back to immutable prior bytes; prior bytes cannot point forward. Runtime policy
ceilings are stable while observations vary.

## Confirmed Findings

### DREV-022: Terminal-before-planning proof is not a typed loadable artifact

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: architecture, recovery, replay, and evidence integrity
- Affected scenario and prevalence evidence: Every final non-committing group using the no-authority successor arm.
- Design location: `terminal_before_planning_proof_digest` projections and no-authority rules.
- Governing source or requirement: SIA-R04, GTC-R07, GTC-R10, and GTC-R11.
- Expected behavior: One typed atomic artifact proves the exact group ended before planning and binds attempt, stage outcome, final result, lineage, plan member, fence, policy, and digest.
- Design behavior: Only equal nonempty digest strings exist; no model, domain, producer, repository, artifact kind, decoder, or validator exists.
- Evidence: An arbitrary shared digest satisfies all current equality joins without proving the causal fact.
- Impact: The critical no-authority exemption is self-asserted and unverifiable on replay.
- Root invariant or contract boundary: Security-relevant evidence is typed and loadable before its digest authorizes behavior.
- Equivalence class and adjacent bypasses inspected: all terminal statuses, attempts, fences, policies, corrupt/missing payload, crash/reopen/replay.
- Positive behavior that must remain valid: The no-authority arm stays immutable and CAS-forbidden.
- Recommended invariant-level resolution: Define and publish a strict `TerminalBeforePlanningProof` artifact with canonical digest/preimage, producer, repository/registry, atomic membership and decoded validation across every carrier.
- Verification needed: Omission, arbitrary digest, wrong coordinate, corrupt payload, bundle reorder, and recovery mutations.
- Evidence maturity affected: specified and derivable.

### DREV-023: No-authority result join incorrectly points immutable bytes forward

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: persisted authority and recovery
- Affected scenario and prevalence evidence: Terminal-before-planning A followed by B conflict replan.
- Design location: Universal result-to-successor-authority join and no-authority arm.
- Governing source or requirement: GTC-R08, GTC-R10, and GTC-R11.
- Expected behavior: The later arm reverse-links exactly one immutable closure final-result reference while the predecessor result retains null authority.
- Design behavior: Universal prose says every result names the matching successor authority digest, which would require mutating predecessor bytes.
- Evidence: The arm has a new non-null digest created after the old null-authority result.
- Impact: Exact replay either mutates history or violates the universal join.
- Root invariant or contract boundary: Append-only successor artifacts reference predecessors, never the reverse.
- Equivalence class and adjacent bypasses inspected: omitted/duplicate/mismatched arm, attempted backfill, reopen and replay.
- Positive behavior that must remain valid: Standard reused/replacement results retain their direct authority joins.
- Recommended invariant-level resolution: Make joins arm-specific; exempt the no-authority result from forward authority, require exact reverse equality from arm to sole closure member across group, lineage, member, result, status, and proof.
- Verification needed: Byte-identity and reverse-link substitution matrices.
- Evidence maturity affected: specified and derivable.

### DREV-024: Three-run budget topology is infeasible and nondeterministic

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: evidence_action
- Confidence: high
- Finding type: verification and CI governance
- Affected scenario and prevalence evidence: Every graph-dependent PR budget proof.
- Design location: Graph job owner budget/receipt contract.
- Governing source or requirement: GTC-R01--R13 and DREV-016/DREV-021.
- Expected behavior: Three exact revision-bound observations establish evidence against a stable declared ceiling within a feasible workflow.
- Design behavior: Three full runs occur sequentially inside one five-minute job and ledger budget must equal fresh wall-clock maximum.
- Evidence: Three valid 270-second runs need up to 810 seconds; later runner variance cannot equal a checked-in value.
- Impact: The required job times out or flakes; receipt validation has no producer-before-consumer lifecycle.
- Root invariant or contract boundary: Immutable policy ceiling and variable observed evidence are distinct with explicit artifact handoff.
- Equivalence class and adjacent bypasses inspected: parallel/sequential, missing/extra run, foreign SHA/selector/environment, stale receipt, over-budget, aggregate omission.
- Positive behavior that must remain valid: Five-minute per-run ceiling, 30-second headroom, exact three observations, separate graph timing ownership.
- Recommended invariant-level resolution: Use three parallel measurement jobs or a separate measurement workflow plus named receipt aggregator; declare a checked-in ceiling greater than or equal to observed maximum, not equal future samples; define receipt schema/order/retention and fail-closed mutations.
- Verification needed: Workflow topology and receipt mutation suite.
- Evidence maturity affected: CI enforced.

## Requirements Coverage

DREV-001--021 otherwise remain materially addressed; these findings prevent approval.

## Architecture And Feasibility

The changes add one evidence artifact, one corrected join direction, and one
feasible measurement topology.

## Failure, Security, And Operations

No-authority exemptions cannot rely on self-asserted strings. Budget variance
must not produce false gate failures.

## Verification And Evidence Maturity

The v6 candidate and paired input hashes reproduced. No runtime claim exists.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Status |
| --- | --- | --- | --- | --- |
| forged exemption proof | arbitrary digest | unauthorized closure | typed artifact | open |
| predecessor history backfilled | successor replan | replay mutation | reverse join | open |
| budget job flakes/times out | sequential/variable samples | unusable gate | parallel evidence + ceiling | open |

## Rejected Or Consolidated Findings

- Spec and correctness no-authority observations split into DREV-022 and DREV-023.
- Test review's independently numbered DREV-022 is DREV-024.

## Required Changes Before Approval

Close DREV-022--DREV-024, freeze a seventh candidate, and run fresh full review.

## Non-Blocking Follow-Ups

Performance execution, M4, signing, and unrelated repairs remain separate.

## Final Outcome

Changes required.

## Review Limitations

Read-only v6 review; no implementation or runtime certification.
