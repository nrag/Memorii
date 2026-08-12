# Design Review: Graph-Dependent Transaction Coordinator Remediation 1

## Review Metadata

- Review ID: semantic-ingestion-graph-dependent-transaction-coordinator-remediation-1-2026-08-09
- Review mode: full
- Review outcome: Changes required
- Design path: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/design.plan.md`
- Design baseline: SHA-256 `28f8d0ced95f6711bc8ca84b1fbba415c7b808b0cea98abdd7baf61fa15137d4`
- Implementation baseline: Git HEAD `4691c0374b3b01617a6a50fd83d4e3ff8a61aa84`
- Review date: 2026-08-09
- Reviewers: independent `spec_auditor`, `correctness_reviewer`, and `test_reviewer`; Codex reconciliation
- Included scope: GTC-R01 through GTC-R13 and DREV-001 through DREV-006 remediation
- Excluded scope: implementation, M4, performance optimization, external signing, and unrelated dirty-tree changes

## Executive Assessment

Changes required. The remediation closes the earlier owner, migration, and
tenant intent, but four contract families remain incomplete: durable
intermediate planning states, durable execution-policy authority, authorized
plan reload, and executable CI ownership. The correctness review labeled the
first two P1; reconciliation changes their product priority to Not applicable
because the graph-bound path is not yet implemented or supported. Their
`changes_required` disposition and contract impact remain confirmed.

## Governing Sources

`AGENTS.md` precedence; `.agents/PLANS.md`; the frozen candidate identity;
`docs/design/semantic_ingestion_architecture.md`; current transaction,
persistence, provider, plan-repository contracts; tests; and PR workflow.

## Independently Reconstructed Requirements

| Requirement | Source | Design coverage | Acceptance criteria | Verification | Status |
| --- | --- | --- | --- | --- | --- |
| GTC-R01--R05 | canonical architecture and WorkPlan | semantic behavior specified | real root plus authority and atomic closure | executable required gate | partial: gate owner incorrect |
| GTC-R06--R08 | planning/attempt/lineage contracts | intended order specified | representable durable state at each crash boundary | memory/JSONL recovery | contradictory |
| GTC-R09 | CAS/retry contract | specified | exact authorized CAS and retry | required integration gate | complete at design intent |
| GTC-R10--R12 | result/replay/composition | specified intent | authorized reload and no bypass | root/replay matrix | partial: plan-read authority absent |
| GTC-R13 | execution policy | values specified | policy bytes and counters durable through replay | N/N+1/restart | partial: carriers absent |

## Contract And Evidence Boundaries

The reviewed state machine has only preplanning and planned durable progress,
but the proposed recovery sequence introduces plan-published and attempt-
published crash points. The execution policy is normative only if its bytes or
closed reference occur in every replay-authoritative carrier. Continuous
tenant authority applies to plan reload as well as snapshot and CAS. A test is
CI-owned only when its exact file is collected by a required job and aggregate.

## Confirmed Findings

### DREV-007: Planning recovery lacks representable intermediate states

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: lifecycle and transactional consistency
- Affected scenario and prevalence evidence: Every initial graph-bound plan and replan can crash after plan or attempt publication.
- Design location: architecture graph-dependent implementation profile and source progress contracts
- Governing source or requirement: GTC-R06--R11; atomic progress and recovery invariants
- Expected behavior: Every acknowledged generation has one valid durable progress variant and deterministic next action.
- Design behavior: Plan and attempt are published in separate generations before lineage, while only preplanning-before-plan and planned-with-lineage states exist.
- Evidence: `PrePlanningSourceIngestionProgress` forbids a fixed plan; `PlannedSourceIngestionProgress` requires lineage; current atomic planned closure expects the complete authority set.
- Impact: Crash recovery cannot truthfully encode or resume plan-published or attempt-published state.
- Root invariant or contract boundary: Every durable publication boundary needs a closed state-machine image.
- Equivalence class and adjacent bypasses inspected: crash/lost ack after plan, attempt, lineage, CAS, group result; stale-owner takeover; initial and replan attempts.
- Positive behavior that must remain valid: Reload-before-authorization and reload-before-lineage; no same-generation caller-object authorization.
- Recommended invariant-level resolution: Add exact `plan_published` and `attempt_published` progress variants, member closures, transitions, and recovery rules before `planned` lineage state.
- Verification needed: Memory/JSONL crash, lost-ack, and stale-owner recovery at every state transition.
- Evidence maturity affected: specified and derivable

### DREV-008: Execution policy is absent from replay-authoritative durable carriers

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: recovery and persisted authority
- Affected scenario and prevalence evidence: Every restart, replan, resource exhaustion, and replay of graph-bound work.
- Design location: execution-policy profile versus attempt, lineage, progress, and replay contracts
- Governing source or requirement: GTC-R13 and no-live-lookup replay rules
- Expected behavior: Persisted policy bytes or a closed loadable reference and observed counters bind attempts, lineage, progress, and replay.
- Design behavior: Prose requires the binding, but canonical schemas omit it.
- Evidence: `GraphDependentValidationAttempt`, `SourceTransactionPlanLineage`, progress variants, and `ReplayArtifactBundle` have no policy authority.
- Impact: Replay cannot distinguish the original limits from changed live configuration.
- Root invariant or contract boundary: Resource authorization is immutable persisted input, not ambient configuration.
- Equivalence class and adjacent bypasses inspected: initial/replan attempt, lineage, progress, replay bundle, registry changes, each N/N+1 counter, rollback.
- Positive behavior that must remain valid: Registry remains sole byte/count authority where selected; policy copies and validates those values.
- Recommended invariant-level resolution: Add one typed loadable policy authority/reference and observed counters to every required carrier and digest closure.
- Verification needed: Changed-runtime replay, field/reference/digest substitution, and N/N+1 restart cases.
- Evidence maturity affected: specified and derivable

### DREV-009: Canonical plan reload cannot enforce continuous tenant authority

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: security and repository integration
- Affected scenario and prevalence evidence: Every plan reload before authorization, lineage, CAS, terminalization, or replay.
- Design location: coordinator profile plan-repository boundary
- Governing source or requirement: GTC-R06--R07, R10--R12 and continuous tenant/principal/scope authority
- Expected behavior: Plan read validates ingress, required scopes, fence, and lease before lookup and returns a non-disclosing failure.
- Design behavior: The profile selects `TransactionSemanticGroupPlanRepository.get(reference)`, whose existing protocol accepts only the reference and has only a constructor-bound fence.
- Evidence: repository protocol and implementation do not receive principal, scopes, or lease.
- Impact: The stated continuous authority rule is not implementable at the canonical plan read.
- Root invariant or contract boundary: Authorization precedes every sensitive repository read and binds its returned authority.
- Equivalence class and adjacent bypasses inspected: plan creation, checkpoint, reload, authorization, attempt, lineage, CAS, result, replay, and graph-free outcomes.
- Positive behavior that must remain valid: Same-tenant authorized reads and graph-free non-committing outcomes.
- Recommended invariant-level resolution: Define one authorized plan-read request/protocol carrying the existing authority bindings and non-disclosing denial; use it for every reload.
- Verification needed: All-root cross-tenant, forged-scope, stale-lease, restart, and replay mutations with zero plan disclosure/effect.
- Evidence maturity affected: specified and derivable

### DREV-010: Declared CI jobs do not collect most required GTC proofs

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: evidence_action
- Confidence: high
- Finding type: verification and CI governance
- Affected scenario and prevalence evidence: GTC-R01--R09 and R11--R13 implementation closure.
- Design location: requirement evidence and gate ledger
- Governing source or requirement: `.agents/PLANS.md` gate ownership and DREV-004
- Expected behavior: Each named proof is collected by its named required job and aggregate, with explicit count/timing ownership.
- Design behavior: Multiple unit files are assigned to generation/projection jobs that do not collect them; new tests lack timing/topology ownership.
- Evidence: Current workflow commands use fixed file lists and counts; `Semantic Ingestion` does not depend on generic `Unit Tests`.
- Impact: Required tests could be absent or failing while the claimed semantic aggregate remains green.
- Root invariant or contract boundary: Evidence ownership must be executable and fail closed.
- Equivalence class and adjacent bypasses inspected: generation, projection, terminal shards, unit shards, aggregate dependencies, new-file timing fallback.
- Positive behavior that must remain valid: Existing job scope and separate performance WorkPlan remain explicit.
- Recommended invariant-level resolution: Select one actual required job/aggregate for the root-triggered suite, specify exact files, collection contract, timeout/timing owner, and update rules; align every ledger row to it.
- Verification needed: Workflow mutation proving omission/skipping/failure blocks the aggregate.
- Evidence maturity affected: CI enforced

## Requirements Coverage

GTC-R09 is complete at design level. Other rows remain partial until the four
families above are closed. Current production zero-caller counts remain an
implementation baseline, not a review defect.

## Architecture And Feasibility

The selected coordinator remains feasible. The required remediation is a
closed state-machine and authority-carrier expansion, not a new semantic path.

## Failure, Security, And Operations

Crash recovery and tenant-safe plan reads are approval-critical. The selected
resource values are acceptable only after they are durably carried through
replay.

## Verification And Evidence Maturity

The mapping artifact reproduces. Exact tests remain future implementation
work, but their CI owner and failure signal must be correct at design time.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Residual risk | Status |
| --- | --- | --- | --- | --- | --- |
| unrepresentable crash state | loss after plan/attempt publication | unrecoverable or fabricated authority | explicit progress variants | low after crash matrix | open |
| changed replay limits | policy absent from bytes | nondeterministic recovery | persisted policy reference/counters | low | open |
| cross-tenant plan read | reference-only get | disclosure/authorization bypass | authorized read request | low | open |
| false-green aggregate | job omits test | incomplete implementation approved | one executable required gate | timing remains separate | open |

## Rejected Or Consolidated Findings

- Correctness-review P1 classifications were rejected because no implemented
  supported graph-bound product path exists; approval impact remains
  `changes_required`.
- Current zero production callers and legacy calls remain known implementation
  absence.
- DREV-001, DREV-005, and the broader DREV-006 intent are otherwise closed.

## Required Changes Before Approval

Close DREV-007 through DREV-010 as one state-machine/authority/evidence
remediation, freeze a new candidate, and run another fresh full review.

## Non-Blocking Follow-Ups

Performance optimization, operational signing, and M4 remain separate.

## Final Outcome

Changes required.

## Review Limitations

Read-only review of the frozen design candidate; no production implementation
or performance execution was assessed.
