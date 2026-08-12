# Design Review: Graph-Dependent Transaction Coordinator Remediation 3

## Review Metadata

- Review ID: semantic-ingestion-graph-dependent-transaction-coordinator-remediation-3-2026-08-09
- Review mode: full
- Review outcome: Changes required
- Design path: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/design.plan.md`
- Design baseline: SHA-256 `4286bfe7fdea2a8971cca8792f2e93917226227b0cc78d0a697fdafc8c5d9f74`
- Implementation baseline: Git HEAD `4691c0374b3b01617a6a50fd83d4e3ff8a61aa84`
- Review date: 2026-08-09
- Reviewers: independent `spec_auditor`, `correctness_reviewer`, and `test_reviewer`; Codex reconciliation
- Included scope: GTC-R01 through GTC-R13 and DREV-001 through DREV-013 remediation
- Excluded scope: implementation, M4, performance optimization, external signing, and unrelated dirty-tree changes

## Executive Assessment

Changes required. Current plan-read authority and exclusive gate ownership are
materially improved, but conflict replanning still lacks one complete plan
algebra and the pre-commit conflict variant. The gate also needs the repository's
required measured-budget ledger and an explicit handoff from the active terminal
test-topology owner.

## Governing Sources

`AGENTS.md`; `.agents/PLANS.md`; the v3 frozen candidate; canonical architecture;
current plan, lineage, test-owner, timing, and workflow contracts; and the active
design and terminal-persistence WorkPlans.

## Independently Reconstructed Requirements

| Requirement | Acceptance criteria | Status |
| --- | --- | --- |
| GTC-R06, R08--R11 | Every initial and replacement plan is one complete effective partition with durable recovery | incomplete |
| GTC-R08, R09, R11 | First related conflict and post-commit conflict each have one legal bounded replan path | incomplete |
| GTC-R01--R13 | Dedicated gate has exclusive nodes, measured budget/headroom, and closed owner handoff | incomplete |
| Other DREV-001--013 contracts | Previously identified owner, authority, policy, compatibility, and state boundaries | materially addressed |

## Contract And Evidence Boundaries

A `TransactionSemanticGroupPlan` is complete or must be replaced by a separately
typed effective-plan algebra. Zero committed groups is a valid conflict state,
not an absence of predecessor lineage. CI timeout, measured budget, and ownership
handoff are distinct contracts.

## Confirmed Findings

### DREV-014: Conflict replan lacks one complete effective-plan algebra

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: lifecycle, transaction semantics, and recovery
- Affected scenario and prevalence evidence: Every pre-commit or partial-commit related-conflict replan.
- Design location: Later-plan lineage invariants, `PlanPublishedSourceIngestionProgress`, `AttemptPublishedSourceIngestionProgress`, and conflict-replan transition rules.
- Governing source or requirement: GTC-R06, GTC-R08, GTC-R09, and GTC-R11.
- Expected behavior: Every successor plan authority resolves to one complete snapshot-bound partition while committed groups retain original immutable authority and only retryable groups gain replacement entries.
- Design behavior: The replacement value remains a `TransactionSemanticGroupPlanReference` but is allowed to cover only replanned groups, contradicting the complete-plan and later-plan preservation rules.
- Evidence: No distinct fragment/effective-union type defines whether committed and non-replanned groups belong to the successor plan, predecessor authority, or both.
- Impact: Authorization cardinality, lineage, result bijection, and replay cannot validate one unambiguous complete plan.
- Root invariant or contract boundary: One source attempt has exactly one complete effective operation-to-group partition and no group is dropped, duplicated, or reauthorized silently.
- Equivalence class and adjacent bypasses inspected: initial plan; pre-commit and partial-commit replans; dropped/added/regrouped groups; plan/attempt crash; replay and rollback.
- Positive behavior that must remain valid: Initial plans are complete; committed authority is byte-immutable; replacement authority applies only to retryable groups.
- Recommended invariant-level resolution: Choose either a complete successor plan with immutable reused committed entries or a distinct typed replacement-fragment plus predecessor union. Define exact membership, authorization, compiler, lineage, result, and replay rules consistently.
- Verification needed: Memory/JSONL complete-partition mutations and recovery at replan plan/attempt boundaries.
- Evidence maturity affected: specified and derivable.

### DREV-015: Pre-commit related conflict has no legal replan variant

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: lifecycle, concurrency, and recovery
- Affected scenario and prevalence evidence: The first group receives its one permitted related CAS conflict before any group commits.
- Design location: `planned -> plan_published` conflict transition and committed-result cardinality rules.
- Governing source or requirement: GTC-R08, GTC-R09, and GTC-R11.
- Expected behavior: The retry reacquires graph-dependent context and durably replaces only retryable authority without repeating semantic analysis.
- Design behavior: The only replan edge requires a nonempty committed-result tuple and is explicitly partial-commit.
- Evidence: Zero committed groups cannot satisfy the transition and cannot legally return to preplanning.
- Impact: A supported first conflict must fail early or bypass the durable state machine.
- Root invariant or contract boundary: Every allowed related conflict has exactly one durable bounded retry/recovery path.
- Equivalence class and adjacent bypasses inspected: zero/some/all committed; first and second conflicts; lost ack; stale owner; rollback.
- Positive behavior that must remain valid: Second related conflict exhausts the bounded policy; predecessor lineage remains required.
- Recommended invariant-level resolution: Discriminate `pre_commit_conflict` and `partial_commit_conflict` replan closures, permitting empty committed results only for the former while retaining exact unfinished/replanned sets and predecessor lineage.
- Verification needed: In-memory/JSONL crash, reopen, stale-owner, first-conflict success, and N+1 exhaustion tests.
- Evidence maturity affected: specified and derivable.

### DREV-016: Dedicated graph gate lacks measured-budget and owner-handoff closure

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: evidence_action
- Confidence: high
- Finding type: verification and CI governance
- Affected scenario and prevalence evidence: Every graph-bound PR proof and every terminal node transferred from the active seven-shard owner.
- Design location: Graph-Dependent CI Gate Contract, deterministic job-owner ledger, and linked terminal-persistence testing WorkPlan.
- Governing source or requirement: GTC-R01--R13, DREV-013, and `design-tests` timing/topology rules.
- Expected behavior: The job has one concrete ledger entry, measured budget with positive timeout headroom, exact timing universe, and an atomic transfer from the active terminal owner.
- Design behavior: The design sets a timeout and separate artifacts but does not specify the required ledger entry/budget/headroom or closure dependency on residual terminal topology.
- Evidence: Current static tooling validates dedicated jobs through `deterministic-job-owners.json`; terminal collection/timing ownership is separately active and presently incomplete.
- Impact: Node transfer may strand or duplicate evidence, and a timeout alone cannot prove the five-minute budget.
- Root invariant or contract boundary: Each required job has one measured budget and every moved node has an acknowledged old-owner/new-owner handoff.
- Equivalence class and adjacent bypasses inspected: unit, terminal, graph manifests; timing receipts; owner ledger; aggregate; orphan/duplicate/over-budget mutations.
- Positive behavior that must remain valid: Graph correctness remains within five minutes while long persistence performance stays separate.
- Recommended invariant-level resolution: Name the graph entry in `deterministic-job-owners.json`, budget and headroom calculation, concrete validator inputs, and an explicit dependency requiring the terminal WorkPlan to recalculate and validate its residual collection/timing/budget in the same implementation change.
- Verification needed: Over-budget, missing-ledger/headroom, duplicate/orphan node, incomplete handoff, and aggregate-removal mutations.
- Evidence maturity affected: CI enforced.

## Requirements Coverage

DREV-012 current-authority and DREV-013 exclusive-universe intent remain closed.
The three findings above prevent bounded design approval.

## Architecture And Feasibility

All changes are determinate refinements of the selected coordinator and evidence
topology; no new product path or external decision is required.

## Failure, Security, And Operations

Conflict retries must preserve a complete effective partition at every durable
boundary. Current authorization before plan lookup remains intact.

## Verification And Evidence Maturity

The v3 hashes and mapping counts reproduce. No implementation or parent M3
completion is claimed.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Status |
| --- | --- | --- | --- | --- |
| ambiguous replacement-plan authority | partial plan under complete-plan type | invalid lineage/result/replay | one complete effective-plan algebra | open |
| first conflict cannot retry | zero committed groups | valid path fails or bypasses durability | pre-commit conflict variant | open |
| timing/owner transition incomplete | graph nodes moved from active owner | false or broken gate | ledger budget and atomic handoff | open |

## Rejected Or Consolidated Findings

- The spec review's partial-plan conflict and correctness review's zero-commit conflict are related but independent contract gaps, DREV-014 and DREV-015.
- The test review's independently numbered DREV-014 is renumbered DREV-016.
- Unrelated dirty-tree failures and zero production callers are not findings in this design-only review.

## Required Changes Before Approval

Close DREV-014 through DREV-016, freeze a fourth candidate, and run a fresh
full independent review.

## Non-Blocking Follow-Ups

Performance optimization, operational signing, M4, and unrelated repairs remain
separate.

## Final Outcome

Changes required.

## Review Limitations

Read-only review of the frozen v3 design candidate; no implementation or runtime
certification was assessed.
