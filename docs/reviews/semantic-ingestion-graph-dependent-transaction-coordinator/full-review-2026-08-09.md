# Design Review: Graph-Dependent Transaction Coordinator

## Review Metadata

- Review ID: semantic-ingestion-graph-dependent-transaction-coordinator-full-review-2026-08-09
- Review mode: full
- Review outcome: Changes required
- Design path: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/design.plan.md`
- Design baseline: SHA-256 `2a362762be83c3c1d0d73a74d2c8b1b1a2c80af8096093e623ce7c6e0471e8a9`
- Implementation baseline: Git HEAD `4691c0374b3b01617a6a50fd83d4e3ff8a61aa84`; dirty-tree status SHA-256 `deb26709863fc9216e90598dcf06ecbbc83eea71369d487208cf54a9782ea930`; binary-diff SHA-256 `e7fa49b2c2bbb3d732bf0226c85196868cfb8389005ee55b1410a1ea18328983`
- Review date: 2026-08-09
- Reviewers: independent `spec_auditor`, `correctness_reviewer`, and `test_reviewer`; Codex main-thread reconciliation
- Included scope: GTC-R01 through GTC-R13; Steps 5--8 ownership, production composition, atomic persistence, CAS/retry, lineage, replay/recovery, authorization, bounded resources, verification, and implementation readiness
- Excluded scope: M4 conflict presentation/clarification semantics, persistence performance, new grammar or learned behavior, retrieval/ranking, external signing, and unrelated dirty-tree changes

## Executive Assessment

The candidate accurately diagnoses the missing Steps 5--8 production chain and
rejects fabricated authority, but it is not yet implementation-ready. It is a
sound plan for completing the design, not the completed design. The three
independent lanes converged on missing canonical ownership/composition, missing
resource-policy authority, and insufficient executable verification ownership.
Correctness review additionally found a concrete lifecycle error in the
candidate's proposed order: a complete planning authorization set must be
derived from store-reloaded plan/artifact/certificate authority before the
`GraphDependentValidationAttempt` that embeds it is persisted.

No P1/P2 product defect is assigned because the graph-bound path is not yet an
implemented supported product path. Six determinate design-conformance and
evidence actions block design approval.

## Governing Sources

Repository precedence from `AGENTS.md` applies. The review used
`docs/design/memorii_spec.md`, `docs/design/memorii_storage_details.md`,
`docs/design/event_model.md`, `docs/IMPLEMENTATION_RULES.md`,
`docs/design/semantic_ingestion_architecture.md`, the approved
`operation-alignment-schema/design.plan.md`, `.agents/PLANS.md`, production
provider/semantic-ingestion/persistence code, focused contracts and tests, and
the PR-gate workflow.

## Independently Reconstructed Requirements

| Requirement | Source | Design coverage | Acceptance criteria | Verification | Status |
| --- | --- | --- | --- | --- | --- |
| GTC-R01 source-normalization authority | architecture Step 5 | Closure described; owner/interface incomplete | same-generation complete closure, reload, substitution rejection | provider-root publication/reload and mutations | partial |
| GTC-R02 source grouping | architecture Step 5 | Contract described; producer/composition incomplete | exact operation/group bijection and graph-free determinism | root-triggered grouping family | partial |
| GTC-R03 snapshot authority | architecture Steps 5--8 | Snapshot semantics exist; repository/composition unresolved | one fenced snapshot and tracked read extensions | token/scope/fence/second-lookup matrix | partial |
| GTC-R04 reconciliation | architecture Step 6 | Required artifacts stated; owner boundary unselected | complete typed attempt-bound closure | real-root positive and substitution cases | partial |
| GTC-R05 planning artifacts/compiler | architecture Step 7 | Pure behavior stated; APIs/repository profile missing | deterministic loadable artifact/certificate closure | independent vectors plus production path | partial |
| GTC-R06 fixed plan | architecture Step 7 | Plan/repository contracts exist; producer absent | fixed-point complete plan atomically published/reloaded | grouping/fixed-point/substitution matrix | partial |
| GTC-R07 attempt authorization | architecture Steps 7--8 | Candidate sequence is incorrect | authorization derived first, complete attempt persisted before use | crash/reopen/substitution at each boundary | contradictory |
| GTC-R08 append-only lineage | architecture Step 8 | Invariants stated; repository/update owner absent | monotone attempts and preserved committed authorization | partial-commit/replan/restart family | partial |
| GTC-R09 CAS/retry | architecture coordinator sequence | Semantics stated; executor/policy profile incomplete | exact read-set CAS, bounded related-conflict retry | concurrent related/unrelated/stale-owner cases | partial |
| GTC-R10 terminal binding | architecture persistence/results | Required joins stated; production owner/path absent | exact reload-derived attempt/plan/auth/result bijection | committed/noncommitting and coercion mutations | partial |
| GTC-R11 recovery/replay | architecture persistence/recovery | Families named; migration table and boundary oracles missing | byte-identical retry or fail before visibility | memory and JSONL crash/reopen matrix | partial |
| GTC-R12 production reachability | `.agents/PLANS.md`, provider architecture | Current absence documented; target profile missing | nonzero mandatory callers and no committing fallback | direct/factory/filesystem/Hermes composition | partial |
| GTC-R13 bounded resources/observability | architecture coordinator limits | Categories named; authority/values/outcomes deferred | replay-bound limits and typed exhaustion | N/N+1, restart, privacy-safe trace tests | partial |

## Contract And Evidence Boundaries

The normative authority is the canonical architecture and approved receipt
design. Production types and repository helpers prove feasibility but not
reachability. The current real chain is `ProviderMemoryService.sync_event` to
`ProviderIngestionCoordinator` to the semantic pipeline and
`SemanticTerminalPersistenceService.persist`. Four production persistence
calls omit `transaction_group_plan`. No production caller constructs and uses
the complete alignment, graph attempt, authorization, and lineage chain.

Valid pre-graph non-committing outcomes must remain distinct from graph-bound
success. A plan repository is a typed read view, not a derivation owner.
Caller-supplied digests, fixtures, live lookups, optional defaults, and the
legacy opaque marker cannot supply commit authority. Review evidence remains
at specified or isolated-contract maturity for the complete chain.

## Confirmed Findings

### DREV-001: Canonical ownership and production composition remain undecided

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: architecture and integration
- Affected scenario and prevalence evidence: Every future ordinary graph-bound provider event; this is the sole intended production path, though it is not implemented today.
- Design location: target lines 150--188, 341--360, and 446--452
- Governing source or requirement: GTC-R01 through GTC-R12; architecture coordinator sequence; `.agents/PLANS.md` production-entrypoint contract
- Expected behavior: One behavioral coordinator and exact constructor/composition profile own every typed input, repository, atomic transition, fail-closed outcome, reload, and final result across provider, factory, filesystem, and Hermes roots.
- Design behavior: The target supplies role arrows and grouped provisional bindings but leaves the coordinator module, snapshot/read-set protocols, compiler boundary, migration boundary, and exact per-owner callsites open.
- Evidence: `ProviderIngestionCoordinator` owns the live path; four calls to `SemanticTerminalPersistenceService.persist` omit `transaction_group_plan`; graph-dependent contracts have zero production constructors/consumers; the existing transaction coordinator is a narrower snapshot/retry helper.
- Impact: Implementers must invent the pivotal authority and atomic ownership boundary, risking duplicate coordinators or legacy-terminal fabrication/bypass.
- Root invariant or contract boundary: A runtime requirement needs one named mandatory production owner chain; schemas, repositories, and fixtures are not reachability evidence.
- Equivalence class and adjacent bypasses inspected: direct provider, factory, filesystem, Hermes, ingest/reconcile, four persistence calls, optional plan, legacy marker, repository-only and fixture-only construction.
- Positive behavior that must remain valid: Authenticated pre-graph evidence-only, rejected, and unresolved outcomes remain non-committing when graph authority is absent.
- Recommended invariant-level resolution: Add the D2--D4 implementation-facing profile selecting the architecture-owned coordinator (or explicitly amending that ownership), exact protocols and constructor arguments, generation transitions/member sets, composition changes, and typed absence outcomes; replace grouped binding rows with per-owner entries.
- Verification needed: Revision-bound production map and direct in-memory/filesystem/provider/factory/Hermes composition tests proving every owner in order and no committing fallback.
- Evidence maturity affected: specified to derivable, implemented, and CI enforced

### DREV-002: Attempt and authorization lifecycle is ordered incorrectly

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: lifecycle and transactional consistency
- Affected scenario and prevalence evidence: Every initial graph-bound plan and every graph-dependent replan.
- Design location: target lines 154--166 and production-binding row GTC-R07--R09
- Governing source or requirement: GTC-R07; architecture planning repository and coordinator sequence
- Expected behavior: Publish plan/artifacts/certificates, reload and validate them, derive the exact per-group authorization bijection, construct and persist the complete attempt embedding those authorizations, reload the attempt, append lineage, then use it for CAS.
- Design behavior: The arrow and ledger say persisted attempt precedes reload-derived authorization.
- Evidence: `GraphDependentValidationAttempt` requires a nonempty canonical authorization set bound to its exact plan; architecture explicitly derives authorizations from reloaded plan/execution/artifact/certificates and embeds them in the attempt.
- Impact: Literal implementation cannot construct a valid attempt, or it mutates/attaches authority after persistence and breaks attempt identity.
- Root invariant or contract boundary: Commit authority is a complete reload-derived closure embedded in the persisted-before-use attempt.
- Equivalence class and adjacent bypasses inspected: initial attempt, later group attempt, empty/detached/cross-plan/cross-group/post-persistence authorization, and valid pre-plan non-committing outcomes.
- Positive behavior that must remain valid: Pre-plan non-committing outcomes need no planning authorization; graph-bound attempts require the complete set.
- Recommended invariant-level resolution: Freeze the correct generation-by-generation sequence and recovery point for plan/artifact/certificate publication, reload-derived authorization, attempt publication/reload, lineage, pre-CAS reload, and CAS.
- Verification needed: Construction rejection without complete authorization plus memory/JSONL crash and substitution tests at every boundary.
- Evidence maturity affected: specified and derivable

### DREV-003: Resource limits lack replayable policy authority and exhaustion semantics

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: operability and resource safety
- Affected scenario and prevalence evidence: Oversized sources, closure expansion, fixed-point planning, retries, persisted artifacts, and lineage growth.
- Design location: target GTC-R13 and Resource And Performance Constraints
- Governing source or requirement: GTC-R13 and architecture coordinator limits
- Expected behavior: One immutable acquired policy identifies every limit, fingerprint, accounting unit, enforcement owner, and exact exhaustion state/reason.
- Design behavior: Limit categories are listed, but values and the policy/experiment that selects them are deferred.
- Evidence: The target says exact budgets must be selected later; existing local retry constants are not a coherent graph-bound authority.
- Impact: Implementations can diverge, silently truncate, loop without a bound, or disagree on terminal versus retryable behavior and replay.
- Root invariant or contract boundary: Resource exhaustion is a typed replayable state transition, never a process-local default or truncation.
- Equivalence class and adjacent bypasses inspected: operation/group count, fixed-point rounds, related conflicts, extensions, reservations, artifacts/certificates, lineage, payload/decode depth, and paid-stage reuse.
- Positive behavior that must remain valid: In-bound processing and the architecture's one-related-conflict behavior remain valid; acknowledged learned work is not repeated.
- Recommended invariant-level resolution: Select one immutable budget-policy owner and exact values/outcomes, or make a bounded feasibility experiment and frozen policy a prerequisite to implementation.
- Verification needed: N-1/N/N+1 tests, restart/replay equality, policy-fingerprint substitution, no truncation, and privacy-safe exhaustion traces.
- Evidence maturity affected: specified to derivable

### DREV-004: Production-path evidence and CI ownership are not executable

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: evidence_action
- Confidence: high
- Finding type: verification and CI governance
- Affected scenario and prevalence evidence: Every GTC requirement and every ordinary graph-bound composition root.
- Design location: target Production Entrypoint Bindings and Verification And Attack Matrix
- Governing source or requirement: GTC-R01 through GTC-R13; `.agents/PLANS.md` binding/gate ledgers
- Expected behavior: Each requirement names the exact trigger, durable observable, test level, fake boundary, mutation signal, required workflow job/shard/aggregate, and revision-bound reusable production map.
- Design behavior: The candidate names attack families but not concrete test owners, oracles, commands, CI jobs, shards, aggregates, or the durable mapper artifact; some binding rows still say counts are pending.
- Evidence: Existing contract/repository tests construct models and plans directly; provider tests exercise the legacy source-only path; no current test proves the complete root-to-lineage chain.
- Impact: Schemas and isolated tests can stay green while the production caller or authority argument is removed or the legacy fallback commits.
- Root invariant or contract boundary: Required evidence must fail when production reachability or durable authority is absent.
- Equivalence class and adjacent bypasses inspected: all roots, optional plan, legacy fallback, in-memory/JSONL, direct fixtures, helpers, repositories, and current PR jobs.
- Positive behavior that must remain valid: Direct contract and repository tests remain useful supplemental evidence; valid pre-graph outcomes remain testable separately.
- Recommended invariant-level resolution: Add a per-requirement evidence/gate ledger and a pinned mapping artifact with exact queries, roots, authority arguments, outcomes, caller counts, and fallback classification.
- Verification needed: Root-triggered positive and mutation families for R01--R13, memory/JSONL lost-ack tests at every boundary, composition-removal failure signals, and a named required PR aggregate.
- Evidence maturity affected: locally verified, independently reproduced, and CI enforced

### DREV-005: Strict migration and rollback behavior is not derivable

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: compatibility and persisted-state lifecycle
- Affected scenario and prevalence evidence: Reopening legacy opaque graph-bound state, valid pre-graph state, and rollback before or after partial graph commit.
- Design location: target Migration, Rollout, And Rollback and Open Design Questions
- Governing source or requirement: GTC-R10--R11 and event replay compatibility rules
- Expected behavior: A versioned table classifies every old state and defines exact decode, visibility, retained bytes, rejection, recovery, and rollback behavior.
- Design behavior: The candidate prohibits legacy opaque graph-bound success but leaves the smallest strict migration open and supplies no byte fixtures or visibility rule.
- Evidence: Missing/opaque/null/empty/sentinel graph-plan states, valid pre-graph variants, and post-commit rollback cannot be assigned deterministic oracles from the candidate.
- Impact: A permissive fallback or rejection of valid pre-graph outcomes could satisfy the current prose.
- Root invariant or contract boundary: Persisted compatibility is a closed typed state machine; committed lineage is immutable and visible only after full validation.
- Equivalence class and adjacent bypasses inspected: opaque, missing, null, empty, sentinel, cross-repository, valid pre-graph outcomes, rollback before commit, and rollback after partial commit.
- Positive behavior that must remain valid: Valid explicit pre-graph variants remain readable; committed lineage is preserved and never rewritten.
- Recommended invariant-level resolution: Freeze a versioned migration table and fixture corpus, including typed incompatibility before graph visibility and promotion-disable rollback that retains lineage.
- Verification needed: In-memory and JSONL replay for every row, byte and visibility assertions, and pre/post-partial-commit rollback cases.
- Evidence maturity affected: specified and derivable

### DREV-006: Tenant and caller authorization lacks a graph-bound attack proof

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: evidence_action
- Confidence: medium
- Finding type: security and authorization verification
- Affected scenario and prevalence evidence: A principal authorized for tenant A requests snapshot, reservation, reconciliation, or CAS state from tenant B.
- Design location: target snapshot/reconciliation/CAS verification families
- Governing source or requirement: repository tenant isolation plus GTC-R03, R04, R07, R09, and R12
- Expected behavior: The same authenticated source/principal/tenant authority binds snapshot acquisition through CAS and replay; cross-tenant, omitted, or forged authority rejects without disclosing or mutating the other tenant.
- Design behavior: Scope, policy, identity, token, and fence mutations are named, but caller/tenant authorization and no-read/no-reservation/no-CAS evidence are not.
- Evidence: Existing ingress authority tests do not traverse the new graph-bound owner chain; the target contains no explicit cross-tenant root case or restart/concurrency sibling.
- Impact: The verification plan could miss a trust-boundary substitution even if structural snapshot checks pass.
- Root invariant or contract boundary: Tenant/caller authorization is continuous authority from ingress through graph read and write.
- Equivalence class and adjacent bypasses inspected: valid A, forged B, omitted tenant, cross-tenant scope, concurrent A/B, restart, and legacy fallback.
- Positive behavior that must remain valid: Valid same-tenant graph-bound work and non-disclosing pre-graph rejection remain available.
- Recommended invariant-level resolution: Add the cross-tenant authority chain to the contract and attack matrix, including no-read and no-effect observables at every root.
- Verification needed: Direct/factory/filesystem/Hermes A-positive and A-to-B-negative cases, restart, concurrent admissions, and absence of legacy commitment.
- Evidence maturity affected: verification and CI enforcement

## Requirements Coverage

All GTC requirements are traceable. None is complete. GTC-R07 is
contradictory in the candidate ordering; R13 is not derivable; R01--R06 and
R08--R12 remain partial because the exact implementation profile, migration,
and executable evidence ownership are absent.

## Architecture And Feasibility

The canonical architecture supplies most semantic contracts, and existing
models/repositories make the direction feasible. The remaining work is not a
new product model: it is an exact implementation-facing authority profile plus
the corrected authorization/attempt ordering. No evidence currently requires
changing the minimal `OperationAlignment` receipt.

## Failure, Security, And Operations

The candidate appropriately requires fail-closed behavior, append-only
lineage, no partial graph visibility, and bounded recovery. Approval is blocked
until migration/rollback is a closed state table, resource exhaustion is
policy-bound, and tenant/caller authority is continuous through graph read and
CAS.

## Verification And Evidence Maturity

Current evidence is strong for isolated source-group/lineage schemas, the
transaction-plan repository, and generic atomic persistence. It is insufficient
for production graph-dependent orchestration, graph-specific replan, exact
attempt/plan/authorization terminal binding, or root-to-replay behavior. No
complete-chain claim is above `specified`; some constituent contracts are
implemented and locally verified.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Residual risk | Status |
| --- | --- | --- | --- | --- | --- |
| duplicate or bypassing coordinator | implementer chooses an unstated owner | fabricated or optional authority | exact ownership/composition profile | low after binding tests | open |
| invalid attempt identity | authorization derived after attempt persistence | unusable or mutable authority | correct atomic sequence | low after crash matrix | open |
| unbounded/divergent retries | implicit local constants | availability and replay divergence | immutable budget policy | policy tuning remains | open |
| legacy state coercion | opaque marker treated as plan | unauthorized graph-bound success | strict migration table | old fixture inventory | open |
| contract-only false confidence | tests bypass production root | missing caller ships | per-requirement gate ledger | CI duration separately owned | open |
| cross-tenant graph access | incomplete authority propagation | disclosure or mutation | continuous tenant binding and negative matrix | operational configuration | open |

## Rejected Or Consolidated Findings

- Zero current production callers is known implementation absence and evidence
  for DREV-001/DREV-004, not a separate product defect.
- The stale broader WorkPlan split manifest is a separate planning-governance
  reconciliation item and does not change the frozen design semantics.
- Existing direct model/repository tests remain valid supplemental tests; only
  their use as sole production proof is rejected.
- Legacy terminal performance and fixture duration are outside this review.
- No identity-coordinate leakage was found in the candidate's durable names.

## Required Changes Before Approval

1. Select and specify the exact coordinator, protocols, composition roots,
   atomic generations, typed arguments/outcomes, and mandatory fail-closed path.
2. Correct and fully specify the plan/reload/authorization/attempt/lineage/CAS
   sequence.
3. Freeze graph-bound resource policy values, fingerprints, owners, and
   exhaustion transitions.
4. Add the durable revision-bound production map and per-requirement test/gate
   ledger with executable oracles.
5. Freeze strict migration and rollback tables with persisted fixture classes.
6. Add continuous tenant/caller authority and the complete cross-tenant attack
   family.

## Non-Blocking Follow-Ups

Performance optimization, timing inventory, shard balancing, and operational
production signing remain in their existing operations. They do not reduce the
required deterministic design proof.

## Final Outcome

Changes required. The candidate should return to the linked `build-design`
operation for one coherent remediation of the ownership/authority boundary,
then receive a full review because composition, transaction ordering,
migration, security, and resource-policy contracts are material.

## Review Limitations

The review is scoped to the frozen target hashes and the recorded dirty-tree
implementation baseline. It did not run performance suites, modify design or
code, validate external signing, or approve parent M3/M4. The medium-confidence
tenant finding remains required because it concerns a reachable future trust
boundary, but its exact test adapters depend on the owner profile selected in
remediation.
