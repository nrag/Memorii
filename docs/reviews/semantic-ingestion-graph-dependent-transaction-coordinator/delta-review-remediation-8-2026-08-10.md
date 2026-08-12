# Design Review: Graph-Dependent Transaction Coordinator CI Ordering Delta

## Review Metadata

- Review ID: semantic-ingestion-graph-dependent-transaction-coordinator-ci-ordering-2026-08-10
- Review mode: delta
- Review outcome: Changes required
- Design path: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/design.plan.md`
- Design baseline: SHA-256 `5b1ca47f66b775b3885abb4d08ef043764f469f73a403877a4f1c2f84a2e874b`
- Implementation baseline: Git HEAD `4691c0374b3b01617a6a50fd83d4e3ff8a61aa84`
- Review date: 2026-08-10
- Reviewers: independent `test_reviewer`; Codex reconciliation; spec and correctness reviewers approved v8
- Included scope: DREV-027 graph evidence producer/consumer ordering
- Excluded scope: implementation, M4, performance execution, and unrelated changes

## Executive Assessment

Changes required. One stale sentence requires fresh timing evidence to exist
before the producers that create it.

## Governing Sources

The v8 frozen candidate, graph CI gate contract, current workflow semantics, and
paired terminal WorkPlan.

## Independently Reconstructed Requirements

| Requirement | Acceptance criteria | Status |
| --- | --- | --- |
| GTC-R01--R13 CI evidence | Collection validates before execution; fresh receipts and inventory validate after execution | contradictory |

## Contract And Evidence Boundaries

Committed topology is a precondition. Runtime receipts are outputs. The
aggregated inventory can only be produced from current successful outputs.

## Confirmed Findings

### DREV-027: Producer pre-run validation requires not-yet-produced timing evidence

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: verification and CI governance
- Affected scenario and prevalence evidence: Every graph-dependent CI run.
- Design location: Graph job pre-run validation and receipt aggregator lifecycle.
- Governing source or requirement: GTC-R01--R13 and DREV-024/DREV-026.
- Expected behavior: Producers prevalidate collection/topology, run tests, upload current receipts; aggregator validates receipts and publishes current inventory.
- Design behavior: A stale clause requires each graph job to validate receipt/inventory before running tests.
- Evidence: The receipt and inventory do not exist until producers and aggregator finish.
- Impact: Fresh evidence is impossible or stale evidence can be consumed.
- Root invariant or contract boundary: Runtime output cannot be a precondition of its producer.
- Equivalence class and adjacent bypasses inspected: stale/foreign receipt, old inventory, missing producer, early aggregator, current revision mismatch.
- Positive behavior that must remain valid: Collection and ownership topology remain pre-run fail-closed checks.
- Recommended invariant-level resolution: State the four-phase lifecycle explicitly; name three receipt artifacts and one post-run inventory; forbid producer reads of prior timing output.
- Verification needed: Static mutations for pre-existing receipt/inventory reads, stale inventory reuse, and early aggregation.
- Evidence maturity affected: CI enforced.

## Requirements Coverage

All other DREV-001--026 contracts were approved or materially closed in v8.

## Architecture And Feasibility

The fix is removal of contradictory ordering, not a new topology.

## Failure, Security, And Operations

Fresh revision binding and producer-before-consumer order remain fail closed.

## Verification And Evidence Maturity

v8 hashes reproduced. CI remains unimplemented.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Status |
| --- | --- | --- | --- | --- |
| stale timing accepted | pre-run receipt read | false gate | explicit output lifecycle | open |

## Rejected Or Consolidated Findings

- Spec and correctness reviewers approved v8; no additional finding was inferred.

## Required Changes Before Approval

Close DREV-027 and run a focused frozen delta review.

## Non-Blocking Follow-Ups

Implementation and performance execution remain separate.

## Final Outcome

Changes required.

## Review Limitations

Read-only CI ordering delta review only.
