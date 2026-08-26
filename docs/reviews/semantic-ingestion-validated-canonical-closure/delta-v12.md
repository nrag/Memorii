# Design Review: Semantic Ingestion Validated Canonical Closure V12 Delta

## Review Metadata

- Review ID: `semantic-ingestion-validated-canonical-closure-delta-v12`
- Review mode: `delta`
- Review outcome: `Changes required`
- Design path: `docs/design/semantic_ingestion_validated_canonical_closure.md`
- Design baseline: candidate v12, lock `fb86952737f2e004ba1e1e92da258c7041f5dc44ca6fd7edea11f471e58bcca4`
- Implementation baseline: proposed closure remains unimplemented; current source reality used only for ownership and feasibility
- Review date: `2026-08-17`
- Reviewers: `spec_auditor`, `correctness_reviewer`, `test_reviewer`, and coordinator reconciliation
- Included scope: complete affected families of full-review `DREV-001` and `DREV-002`
- Excluded scope: unrelated closed findings, external monkeypatching, production implementation, and whole-design approval

## Executive Assessment

Candidate v12 remained byte-identical after an initial review-procedure breach;
the coordinator's read-only manifest validation passed the frozen lock and all
109 hashes before a fresh reviewer cohort started. The restarted cohort made no
writes and executed no repository entrypoint.

The v12 remediation materially improves lifecycle and observability ownership,
but the bounded delta is not approved. Two family-level conformance gaps remain:
the lifecycle reference and binding do not fully enforce the normative no-owner,
idempotent-close, transition, capacity, and owner-projection contract; and the
metrics contract constrains names but not values or deferred terminal-reason
truthfulness.

## Governing Sources

Root `AGENTS.md`, `.agents/PLANS.md`, the `$review-design` finding and
convergence contracts, the target design, immutable full review `final-v11.md`,
the production-entrypoint binding addendum, the machine-readable operation
contract, the executable reference source and frozen result, and relevant
production ownership paths.

## Independently Reconstructed Requirements

| Requirement | Source | Design coverage | Acceptance criteria | Verification | Status |
| --- | --- | --- | --- | --- | --- |
| Closed capability lifecycle | Full-review `DREV-001`, `VCC-R06/R07/R08/R12` | Partial | No owner before enabled reservation; sealed-only authority; idempotent linearizable close; exact-once release | Contract projection and lifecycle matrix | `DREV-003` |
| Complete bounded capacity | `VCC-R08` | Partial | Exact and one-over root count, root bytes, paths, operation and process charge; reacquisition after release | Boundary matrix | `DREV-003` |
| Production owner binding | `VCC-R10` | Partial | Existing service reaches the exact coordinator owner without invented symbol | Source-bound map | `DREV-003` |
| Content-free observability | Full-review `DREV-002`, `VCC-R11` | Partial | Closed field and value schema; truthful immutable terminal reason; sink isolation | Value attacks and terminal matrix | `DREV-004` |

## Contract And Evidence Boundaries

The JSON operation contract is the executable projection of normative prose;
the reference model must consume and discriminate every claimed owner, scope,
state, transition, limit, metric type, value domain, emission rule, and failure
policy. Local reference evidence is sufficient for design feasibility when it
closes that projection. It is not production, CI, live, or operational proof.

## Confirmed Findings

### DREV-003: Lifecycle contract and reference proof remain incomplete

- Product priority: `Not applicable`
- Approval disposition: `changes_required`
- Remediation eligibility: `contract_conformance_action`
- Confidence: `high`
- Finding type: `architecture / concurrency / verification`
- Affected scenario and prevalence evidence: Disabled rollout, initial process-capacity refusal, all enabled operations with leases during repeated teardown, and every exact capacity boundary; the feature is unimplemented, so no shipped product defect is claimed.
- Design location: target design lifecycle and capacity sections; `canonical-closure-operation-contract-v1.json`; `canonical_closure_lifecycle_reference.py`; `production-entrypoint-bindings-v1.md`.
- Governing source or requirement: full-review `DREV-001`; `VCC-R06`, `VCC-R07`, `VCC-R08`, `VCC-R10`, and `VCC-R12`; repository requirements for explicit authority, lifecycle, concurrency, and production ownership.
- Expected behavior: Disabled and initial reservation-refused selection occur before scope-owner, issuer, index, lock, capability, or reservation creation. Every accepted transition is closed; repeated close in `closing` is idempotent; the final lease releases exactly once; all five scope fields and every exact/one-over limit are contract-derived and discriminated; the binding names the real coordinator owner.
- Design behavior: `ScopeOwner.__init__` creates issuer, entries, and lock before disabled selection or reservation refusal. The transition table and reference do not accept repeated close in `closing`. The proof hardcodes scope fields rather than validating `capability.scope_fields`, omits exact/one-over root-count and path-count cells and several pre-seal/post-seal attacks, and proves only concurrent reservation. The binding addendum names `ProviderIngestion` where production owns `ProviderIngestionCoordinator`.
- Evidence: A disabled owner and the fifth refused owner already contain issuer/index/lock state. Seal, acquire one lease, close to `closing`, then close again raises. Removing `writer` or `fence` from the JSON leaves the 16 recorded checks unchanged. Changing root-count or path-count limits can also evade the current cells. The production source owner is `ProviderIngestionCoordinator.ingest` reached through `ProviderMemoryService._provider_ingestion`.
- Impact: An implementer must still invent no-allocation selection, repeated-close semantics, complete capacity acceptance, and exact production ownership; the local proof can pass after contract drift.
- Root invariant or contract boundary: One machine-readable closed lifecycle must be the authority for construction, scope, state, capacity, close, and release, and its reference proof must fail for every material contract mutation.
- Equivalence class and adjacent bypasses inspected: Disabled and initial refusal; reservation, staging, seal, lookup, closing and closed; repeat close with and without leases; all five scope coordinates; root count, root bytes, path count, operation and process charge; lookup before seal, admission/fallback after seal, fifth reservation and post-release reacquisition; cancellation, validation failure, exception, and normal completion.
- Positive behavior that must remain valid: Pre-staging 16 MiB reservation, no substitution before seal, no fallback after substitution, sealed five-coordinate authority, full-path fallback, writer-local admission, unchanged persistence/replay/public outcomes, and exact-once release.
- Recommended invariant-level resolution: Move disabled and initial reservation refusal into a factory/selection result that constructs no scope owner. Add explicit `closing + close -> closing` idempotence and terminal-reason precedence. Derive scope and limits from the JSON contract, reject contract drift, add the complete boundary/transition mutation matrix, and correct the binding to `ProviderIngestionCoordinator.ingest` and `_run_semantic_ingestion`.
- Verification needed: No-owner assertions for disabled and process refusal; exact and one-over every limit; fifth refusal and post-release reacquisition; lookup-before-seal and admission/fallback-after-seal rejection; repeat close while closing; deterministic close/release and reserve races; every terminal release path; all five scope mutations; contract owner/scope/limit/transition mutations.
- Evidence maturity affected: Lifecycle remains specified with incomplete local reference verification; no implementation, CI, live, or operational evidence is claimed.

### DREV-004: Observability contract lacks closed values and truthful deferred terminal reasons

- Product priority: `Not applicable`
- Approval disposition: `changes_required`
- Remediation eligibility: `contract_conformance_action`
- Confidence: `high`
- Finding type: `operability / security / verification`
- Affected scenario and prevalence evidence: Every disabled, rejected, completed, validation-failed, exception, cancelled, or retried operation, especially close with outstanding leases; the feature is unimplemented, so no shipped defect is claimed.
- Design location: target design observability section; operation-contract `metrics`; reference `Metrics`, `close`, `abort`, `release_lease`, and privacy checks.
- Governing source or requirement: full-review `DREV-002`, `VCC-R11`, and unchanged validation, persistence, replay, durable-state, and public outcomes.
- Expected behavior: A closed typed schema enumerates modes, terminal reasons, and sink outcomes; bounds every integer; requires a boolean release value; rejects content-bearing values before dispatch; latches one terminal reason when close begins and emits it unchanged after leases drain.
- Design behavior: The contract allowlists field names only. `mode` and `terminal_reason` are unrestricted strings, numeric ranges are unspecified, and sink outcome is prose. `abort` and `close` accept arbitrary reason text. Deferred close discards its reason and final lease release always emits `completed`. The proof compares field-name sets and does not consume emission or failure-policy declarations.
- Evidence: `abort("customer transcript")` passes the current content-free check and emits that text. Acquiring a lease, calling `close("cancelled")`, then releasing emits `completed`. Unknown modes, negative/oversized counters, invalid booleans, and unknown sink outcomes lack rejection proof.
- Impact: Metrics can leak semantic or identifying content and can misreport cancellation or exception as successful completion; implementations can disagree while satisfying current prose.
- Root invariant or contract boundary: Terminal observability is a typed, content-free, truthful immutable projection of the lifecycle owner's selected terminal cause.
- Equivalence class and adjacent bypasses inspected: Every string-capable field, all integer and boolean fields, recorded/unavailable outcomes, disabled, initial and staging rejection, completion, cancellation, validation failure, exception, retry, zero/nonzero leases, repeated close, and sink unavailability.
- Positive behavior that must remain valid: Exactly one terminal attempt, exact field allowlist, no scope/content identifiers, non-authoritative sink behavior, and unchanged validation/persistence/replay/public outcomes.
- Recommended invariant-level resolution: Freeze field types, integer bounds, closed `mode`, `terminal_reason`, and sink-result enums, plus reason-latching and precedence rules. Validate snapshots before dispatch, retain the chosen reason through `closing`, and reject every unknown or content-bearing value.
- Verification needed: Positive and negative value-schema vectors; sentinel content in every string-capable position; unknown enums; wrong types and ranges; every reason with zero and nonzero leases; repeated-close reason precedence; recorded/unavailable parity; validation-failure, exception, cancellation, retry, and duplicate-close terminal cardinality.
- Evidence maturity affected: Observability remains partially specified with incomplete local reference verification; no implementation, CI, live, or operational evidence is claimed.

## Requirements Coverage

The v12 remediation advances all affected requirements but does not close the
two full-review families. `DREV-003` blocks closure of the lifecycle/capacity
family; `DREV-004` blocks closure of the observability/privacy family.

## Architecture And Feasibility

The reserve-stage-seal-lease architecture remains feasible. The findings
require a closed selection factory, idempotent closing rule, complete executable
projection, corrected production owner, and typed metric values. They do not
require production changes during design remediation.

## Failure, Security, And Operations

The intended fail-closed and full-path behavior remains coherent. Current gaps
allow reference proof inflation, content-bearing terminal values, and incorrect
deferred terminal causes. Sink unavailability isolation remains a valid design
choice but needs value- and outcome-level proof.

## Verification And Evidence Maturity

Candidate v12 correctly labels its result as a locally verified reference
model. Requiring the unimplemented closure to execute through production before
design approval is unsupported and phase-inappropriate. However, the reference
must fully consume and attack the frozen normative contract before the design
can be approved.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Residual risk | Status |
| --- | --- | --- | --- | --- | --- |
| Authority allocation in disabled/refused path | Selection after owner construction | Violates rollback/no-allocation contract | Pre-owner selection factory | None in reference | Open |
| Non-idempotent close | Repeat teardown with active lease | Unexpected failure and invented recovery | Explicit closing self-transition | Scheduling remains implementation risk | Open |
| Contract drift | Scope/limit mutation not consumed | Passing stale proof | Exact projection and mutations | None if complete | Open |
| Metric content leakage | Arbitrary string enum value | Privacy breach | Closed typed values and sentinels | Sink implementation risk | Open |
| Wrong terminal cause | Deferred cancellation/exception | Misleading operations evidence | Reason latch and precedence | None in model | Open |

## Rejected Or Consolidated Findings

- The initial reviewer-procedure breach is `already resolved`: fresh read-only
  validation proved candidate v12 unchanged, and a new reviewer cohort performed
  the complete delta without executing repository entrypoints.
- All lifecycle, capacity, repeated-close, scope-projection, and owner-name
  observations are `confirmed` and consolidated as `DREV-003`.
- All metric value-schema, privacy, terminal-reason, emission, and sink-result
  observations are `confirmed` and consolidated as `DREV-004`.
- The demand for production-trigger execution of the unimplemented closure is
  `unsupported`; production behavioral and CI evidence belong to implementation.
  The bounded reference and static production-owner map must nevertheless be
  complete before design approval.
- No P1 or P2 finding is admitted; these are determinate contract-conformance
  actions for an unimplemented feature.

## Required Changes Before Approval

1. Close `DREV-003` with pre-owner disabled/refused selection, idempotent
   closing, corrected production owner identity, contract-derived scope/limits,
   and complete transition/boundary/concurrency/terminal mutation proof.
2. Close `DREV-004` with a fully typed value schema, terminal-reason latch and
   precedence, snapshot validation, and complete privacy/terminal/sink vectors.
3. Freeze a new candidate and run a bounded delta review of these two families.

## Non-Blocking Follow-Ups

Production-trigger behavioral execution, CI enforcement, live performance, and
operational telemetry remain implementation milestones and are not prerequisites
for design-level delta closure.

## Final Outcome

`Changes required`.

Candidate v12 remains the immutable identity of this bounded decision. Neither
`DREV-001` nor `DREV-002` is closed by v12, and no whole-design approval claim
is made.

## Review Limitations

This review inspected design contracts, reference source, frozen results, and
production ownership read-only. It did not execute the proposed unimplemented
closure, establish CI/live/operational maturity, or modify production code or
repository tests.
