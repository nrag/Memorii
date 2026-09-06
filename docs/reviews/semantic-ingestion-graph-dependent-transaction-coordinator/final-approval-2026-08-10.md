# Design Review: Graph-Dependent Transaction Coordinator Final Approval

## Review Metadata

- Review ID: semantic-ingestion-graph-dependent-transaction-coordinator-final-approval-2026-08-10
- Review mode: delta
- Review outcome: Approved
- Design path: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/design.plan.md`
- Design baseline: SHA-256 `b28ddddfd24ed04e83c4aa9acb829b38f2a2a7feb6840ee2dbf6200330282674`
- Implementation baseline: Git HEAD `4691c0374b3b01617a6a50fd83d4e3ff8a61aa84`
- Review date: 2026-08-10
- Reviewers: independent `spec_auditor`, `correctness_reviewer`, and `test_reviewer`; Codex reconciliation
- Included scope: bounded M3.1 Steps 5--8 coordinator design, GTC-R01--R13, DREV-001--DREV-027, and paired terminal-test ownership handoff
- Excluded scope: production implementation, M4, terminal-performance execution, external signing, and unrelated dirty-tree changes

## Executive Assessment

Approved for implementation as a bounded design. The v8 full review approved
the complete semantic, lifecycle, authorization, replay, and recovery contract;
the v9 frozen delta then corrected and approved the sole remaining CI
producer/consumer ordering clause. No validated design finding remains.

## Governing Sources

`AGENTS.md`; `.agents/PLANS.md`; canonical semantic-ingestion architecture; v8
and v9 candidate identities; production-entrypoint binding map; paired terminal
testing WorkPlan; all immutable review rounds in this directory.

## Independently Reconstructed Requirements

| Requirement family | Approved contract | Evidence owner |
| --- | --- | --- |
| GTC-R01--R05 | root-reachable sealed alignment, grouping, graph snapshot, reconciliation, pure compilation | graph-dependent required job |
| GTC-R06--R08 | complete plans, authorized reload, typed attempt authority, append-only lineage and replans | repository/coordinator tests |
| GTC-R09--R11 | CAS, all terminal variants, crash/reopen/replay and no-authority proof closure | graph integration and persistence tests |
| GTC-R12 | mandatory direct/factory/filesystem/Hermes composition with no legacy fallback | composition tests |
| GTC-R13 | persisted policy/counters and bounded replay/resource behavior | coordinator and receipt evidence |

## Contract And Evidence Boundaries

The implementation must preserve the approved four-state initial lifecycle and
typed conflict-replan cycle, current authorization before sensitive reads,
complete effective-plan authority algebra, typed terminal-before-planning proof,
and the exclusive graph/terminal test-ownership handoff. Design approval is not
evidence that those production callers, contracts, tests, or jobs exist.

## Confirmed Findings

No active findings. DREV-001 through DREV-027 are closed in the approved design.

## Requirements Coverage

GTC-R01 through GTC-R13 are fully specified and mapped to positive, adversarial,
restart, composition-root, and CI evidence. The production map intentionally
retains zero graph-dependent callers as the implementation baseline.

## Architecture And Feasibility

The selected owner is the existing
`SemanticIngestionTransactionCoordinator`. The design defines its required
repositories, compiler, policy, progress states, plan/attempt/lineage ordering,
authorization, result and replay closure, conflict-replan variants, migration
behavior, and fail-closed composition. No unresolved semantic decision is left
for the implementation WorkPlan.

## Failure, Security, And Operations

Every durable publication has a recoverable state. Plan reads validate current
typed authority before lookup. Reused, replaced, and final-no-authority groups
have disjoint authority arms. Lost acknowledgement, stale-owner takeover,
revocation, replay substitution, retry exhaustion, rollback, and partial commit
have explicit outcomes.

## Verification And Evidence Maturity

The production mapping queries reproduce `1,1,4,0,0,0,0,0,1,4,1`. Candidate
artifact hashes reproduce. Required implementation evidence is predefined but
not yet executed. The graph job has exclusive node/timing ownership, three
parallel revision-bound receipt producers, a fail-closed aggregator, explicit
semantic-aggregate propagation, and a paired residual terminal-topology handoff.

## Risk Register

| Risk | Trigger | Mitigation | Residual risk | Status |
| --- | --- | --- | --- | --- |
| implementation bypasses coordinator | optional/legacy terminal fallback | production-root mutation gate | low after implementation proof | implementation-owned |
| recovery diverges | crash at plan/attempt/lineage/CAS | typed state and JSONL matrix | low after evidence | implementation-owned |
| authority or tenant substitution | forged/stale read input | current pre-lookup validation | low after attack matrix | implementation-owned |
| CI false green | missing/skipped graph evidence | explicit producer/aggregator/aggregate checks | low after workflow tests | implementation-owned |
| performance exceeds BVT | graph selector over ceiling | immutable 270-second ceiling and paired timing handoff | separately measured | testing-owned |

## Rejected Or Consolidated Findings

- Reviewer P2 labels on unimplemented graph-bound scenarios were reconciled to
  Not applicable while retaining `changes_required` during remediation.
- Duplicate reviewer numbering was consolidated into the canonical DREV-001--027 sequence.
- Unrelated dirty-tree failures, external signing, M4, and terminal serialization performance were not treated as design defects in this slice.

## Required Changes Before Approval

None.

## Non-Blocking Follow-Ups

Create a separate implementation WorkPlan and implement the approved design in
bounded vertical milestones. Execute the paired terminal-topology handoff in the
same revision that transfers graph test nodes.

## Final Outcome

Approved.

## Review Limitations

This approves design readiness only. It does not approve implementation,
production reachability, test results, CI receipts, M3 parent completion, or M4.
