# Design Review: Graph-Dependent Transaction Coordinator Remediation 2

## Review Metadata

- Review ID: semantic-ingestion-graph-dependent-transaction-coordinator-remediation-2-2026-08-09
- Review mode: full
- Review outcome: Changes required
- Design path: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/design.plan.md`
- Design baseline: SHA-256 `0348890d5da2ab565dcffb3783239380931e33a8ab996d8acda084bf4dc09985`
- Implementation baseline: Git HEAD `4691c0374b3b01617a6a50fd83d4e3ff8a61aa84`
- Review date: 2026-08-09
- Reviewers: independent `spec_auditor`, `correctness_reviewer`, and `test_reviewer`; Codex reconciliation
- Included scope: GTC-R01 through GTC-R13 and DREV-001 through DREV-010 remediation
- Excluded scope: implementation, M4, performance optimization, external signing, and unrelated dirty-tree changes

## Executive Assessment

Changes required. The second remediation closes the initial durable planning
states, persisted policy, plan-read protocol intent, and named gate, but three
implementability gaps remain: partial-commit replanning has no preserving
transition/authority closure, plan reload cannot prove current authorization
from digests alone, and the proposed gate conflicts with existing collection
and timing owners.

## Governing Sources

`AGENTS.md`; `.agents/PLANS.md`; the v2 frozen candidate identity; the canonical
semantic-ingestion architecture; current ingress, persistence, repository,
test-sharding, and PR-workflow contracts; and the active design WorkPlan.

## Independently Reconstructed Requirements

| Requirement | Design coverage | Acceptance criteria | Status |
| --- | --- | --- | --- |
| GTC-R01--R07 | selected coordinator, typed authorities, publication sequence | real-root fail-closed execution | complete at design level |
| GTC-R08--R11 | lineage, CAS, replan, recovery | partial commit survives every replan boundary | incomplete |
| GTC-R06, R10--R12 | authorized reload and composition | current authority before lookup | incomplete |
| GTC-R01--R13 | required evidence | one exclusive executable CI/timing owner | incomplete |
| GTC-R13 | persisted execution policy | identical limits through replay | complete at design level |

## Contract And Evidence Boundaries

Initial planning and partial-commit replanning are distinct state-machine
families. A digest identifies authority but does not prove that authority is
current. A required test node must have exactly one collection and timing owner.

## Confirmed Findings

### DREV-011: Partial-commit replanning has no preserving durable transition

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: lifecycle, replay, and transactional consistency
- Affected scenario and prevalence evidence: Any graph-bound source where group A commits and unfinished group B receives its permitted related conflict and replans.
- Design location: `SourceTransactionPlanLineage`, `PlanPublishedSourceIngestionProgress`, `AttemptPublishedSourceIngestionProgress`, and their transition rules in the graph-dependent architecture profile.
- Governing source or requirement: GTC-R08, GTC-R09, and GTC-R11.
- Expected behavior: `planned` may enter a new plan/attempt/lineage cycle while preserving A's original committed lineage and replacing only unfinished authority.
- Design behavior: Allowed transitions contain only initial `pre_planning -> plan_published`; intermediate replan images omit predecessor lineage, committed-result closure, and the unfinished/replanned group set.
- Evidence: The architecture requires later plans to preserve committed group IDs, membership, and final lineage entries, but declares no `planned -> plan_published` edge and gives the two intermediate images no predecessor-lineage or committed-result field.
- Impact: A valid replan cannot start, or restart must reconstruct committed authority from unspecified history.
- Root invariant or contract boundary: Every acknowledged replan generation retains the exact predecessor authority needed to protect committed groups.
- Equivalence class and adjacent bypasses inspected: initial planning; loss after plan, attempt, lineage, and CAS; A-committed/B-replan; pre-commit replan; retry exhaustion; rollback.
- Positive behavior that must remain valid: Initial planning has no predecessor lineage and preplanning remains plan-free.
- Recommended invariant-level resolution: Add a typed `planned -> plan_published` replan transition. Bind authorized predecessor-lineage closure, committed group-result references, and exact unfinished/replanned groups into replan `plan_published` and `attempt_published` images; validate preservation before disclosure or CAS.
- Verification needed: In-memory and JSONL crash, lost-ack, reopen, stale-owner, drop/substitution, and immutable-A/replanned-B cases.
- Evidence maturity affected: specified and derivable.

### DREV-012: Authorized plan read cannot prove current authority

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: security and authorization
- Affected scenario and prevalence evidence: Every plan reload after authorization changes, including recovery, replay, CAS preflight, and terminalization.
- Design location: `AuthorizedTransactionSemanticGroupPlanReadRequest`, `get_authorized`, and the continuous ingress/scope authority rules in the graph-dependent architecture profile.
- Governing source or requirement: GTC-R06, GTC-R07, and GTC-R10--R12.
- Expected behavior: The repository validates authenticated current tenant, principal, required scopes, fence, and lease before plan lookup.
- Design behavior: The read request carries principal/scope digests but no `AuthenticatedIngressContext` or equivalent server-resolved current authority.
- Evidence: The declared request can reproduce retained principal and scope identities but contains no typed current authorized-scope set, so a revoked invocation is byte-indistinguishable at the repository boundary.
- Impact: Revoked authority is indistinguishable from the originally admitted request at the declared boundary.
- Root invariant or contract boundary: Authorization precedes sensitive lookup and must be current, typed, and authenticated rather than self-asserted by digest.
- Equivalence class and adjacent bypasses inspected: initial and replan reload; attempt, lineage, CAS, result, terminal, recovery, replay; revocation, forged scope, cross-tenant reference, stale lease.
- Positive behavior that must remain valid: Non-disclosing unavailable results and digest closure for persisted identity.
- Recommended invariant-level resolution: Carry the existing authenticated ingress/current-scope authority, or an equally typed server-resolved capability, plus required scopes in the authorized read request; persist only canonical digests while validating current authority before lookup.
- Verification needed: Direct, factory, filesystem, and Hermes revocation/forgery/cross-tenant/stale-lease tests proving zero target lookup/effect and identifier-free denial.
- Evidence maturity affected: specified and derivable.

### DREV-013: Proposed CI gate has no exclusive collection and timing owner

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: evidence_action
- Confidence: high
- Finding type: verification and CI governance
- Affected scenario and prevalence evidence: Every GTC-R01--R13 implementation approval.
- Design location: The WorkPlan's Graph-Dependent CI Gate Contract, current unit timing merge, unit shard manifest, and terminal-persistence job ownership.
- Governing source or requirement: `.agents/PLANS.md`, DREV-004, and DREV-010.
- Expected behavior: Every selected node belongs to exactly one required-job collection universe and one compatible timing receipt/merge.
- Design behavior: The proposed graph job adds a fifth receipt to a four-receipt unit merge and selects nodes already owned by unit and terminal-persistence jobs.
- Evidence: The existing unit timing merge accepts exactly the four unit-shard receipts and the node universe in `unit-shards.json`; proposed graph selectors overlap generic unit and dedicated terminal-persistence collections.
- Impact: The gate either fails structurally or duplicates nodes, so evidence ownership is not implementable as specified.
- Root invariant or contract boundary: CI evidence has one fail-closed collection, timing, and aggregate owner.
- Equivalence class and adjacent bypasses inspected: unit shards, terminal-persistence selectors, integration selectors, timing merge, aggregate dependency, missing job/path/selector mutations.
- Positive behavior that must remain valid: Five-minute correctness gate and separate long performance work.
- Recommended invariant-level resolution: Give the graph gate its own collection/timing universe and explicitly exempt its selected nodes from every other required owner, or reassign them with equivalent closed topology. Define exact receipt/merge and disjointness validation.
- Verification needed: Manifest equality/disjointness, exact timing receipt coverage, zero-selection failure, and workflow mutation proving removal blocks the aggregate.
- Evidence maturity affected: CI enforced.

## Requirements Coverage

DREV-001--010 are otherwise materially addressed. The zero production callers
remain an honest implementation baseline rather than a design defect.

## Architecture And Feasibility

The selected coordinator remains feasible. The required changes extend the
same state machine and authority boundaries; they do not require a new product
path.

## Failure, Security, And Operations

Partial-commit replan recovery and current-authority validation remain approval
critical. The dedicated correctness gate remains appropriate once ownership is
exclusive and mechanically validated.

## Verification And Evidence Maturity

The candidate hashes and production-map counts reproduce exactly. No parent M3
or production-completion claim was assessed.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Status |
| --- | --- | --- | --- | --- |
| committed authority lost during replan | crash after replacement plan/attempt | overwrite or nondeterministic recovery | predecessor closure in replan states | open |
| revoked authority reuses plan | reload with stale digests | disclosure or unauthorized effect | current typed authority before lookup | open |
| false or structurally broken gate | duplicate/missing timing owner | incomplete approval evidence | exclusive manifest and receipt universe | open |

## Rejected Or Consolidated Findings

- The spec and correctness replan findings are one root defect, DREV-011.
- The test review's independently numbered DREV-011 is renumbered DREV-013.
- Current zero production callers and unrelated dirty-tree test failures are not design findings.

## Required Changes Before Approval

Close DREV-011 through DREV-013 coherently, freeze a third candidate, and run a
fresh independent full review.

## Non-Blocking Follow-Ups

Performance optimization, operational signing, M4, and unrelated dirty-tree
repairs remain separate.

## Final Outcome

Changes required.

## Review Limitations

Read-only review of the frozen v2 design candidate; no production implementation
or performance certification was assessed.
