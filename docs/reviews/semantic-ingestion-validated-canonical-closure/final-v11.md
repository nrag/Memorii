# Design Review: Semantic Ingestion Validated Canonical Closure

## Review Metadata

- Review ID: `semantic-ingestion-validated-canonical-closure-final-v11`
- Review mode: `full`
- Review outcome: `Changes required`
- Design path: `docs/design/semantic_ingestion_validated_canonical_closure.md`
- Design baseline: candidate v11, SHA-256 `e98fd2358b719bd2fb44e172612688ca2f211dca87704640fa9658b5a8302d8a`
- Implementation baseline: source-hash-bound production paths recorded by candidate v11; proposed closure is not implemented
- Review date: `2026-08-17`
- Reviewers: `spec_auditor`, `correctness_reviewer`, `test_reviewer`, and coordinator reconciliation
- Included scope: all `VCC-R01` through `VCC-R12`, architecture, authority, lifecycle, capacity, security, rollback, operability, evidence, and implementation readiness
- Excluded scope: implementation, production or test edits, and unsupported expansion beyond the frozen production grammar

## Executive Assessment

Candidate v11 is content-addressed and all 103 tracked hashes validate. It
closes the prior production-binding blocker and provides credible reference
feasibility for exact canonical reuse, a 99.8923 percent repeated-digest
reduction, compact capacity, security attacks, and rollback equivalence.

The design is not yet implementation-ready. It promises operation-atomic
capacity fallback without specifying the lifecycle and reservation state
machine that makes that promise enforceable. It also requires content-free
metrics without specifying an owned typed observability contract. An
implementer would otherwise have to invent authority, concurrency, rollback,
and privacy behavior.

## Governing Sources

The review applied the precedence in root `AGENTS.md`, including
`docs/design/memorii_spec.md`, `docs/design/memorii_storage_details.md`,
`docs/design/event_model.md`, `docs/IMPLEMENTATION_RULES.md`, the target design,
the production-entrypoint binding addendum, applicable hardening and
integration-readiness plans, `.agents/PLANS.md`, and the `$review-design`
finding and convergence contracts.

No governing-source conflict was found. The findings arise from incomplete
target-design contracts rather than competing authority.

## Independently Reconstructed Requirements

| Requirement | Source | Design coverage | Acceptance criteria | Verification | Status |
| --- | --- | --- | --- | --- | --- |
| `VCC-R01` | WorkPlan and target problem | Complete | At most 4,272 repeated and 4,510 total full digests | `VCC-EXP-002` | Satisfied at reference level |
| `VCC-R02` | Canonical codec ownership | Complete | Traversal emits exact bytes, digest, binding, and member spans once | `VCC-EXP-001A/B` and owner proof | Satisfied at design level |
| `VCC-R03` | Typed handoff constraint | Complete | No ambient or caller-supplied reuse authority | Binding ledger and attacks | Satisfied at design level |
| `VCC-R04` | Exact member identity | Complete | Path/span/binding validation rejects ambiguous byte search | Inventory and attacks | Satisfied at reference level |
| `VCC-R05` | Semantic validation invariant | Complete | All semantic stages still execute | Counterfactual and binding rows | Satisfied at design level |
| `VCC-R06` | Writer boundary | Partial | Every writer performs fresh local admission; closure cannot waive it | Writer and retry matrix | Blocked by `DREV-001` lifecycle detail |
| `VCC-R07` | Scope and provenance | Partial | Stale, foreign, wrong-generation, wrong-fence, and forged capabilities fail closed | Security matrix | Blocked by `DREV-001` lifecycle detail |
| `VCC-R08` | Capacity and coherence | Partial | Immutable operation mode, bounded reservation, no partial authority, exact release | Boundary and concurrency matrix | `DREV-001` confirmed |
| `VCC-R09` | Persistence and replay | Complete | No schema change; durable bytes and replay are identical | `VCC-EXP-004` | Satisfied at reference level |
| `VCC-R10` | Production reachability | Complete | All four roots and nine triggers carry typed authority to outcomes | v11 ledger, oracle, 32 attacks | Satisfied at design level |
| `VCC-R11` | Content-free observability | Partial | Owned typed events, exact emission semantics, privacy and sink-failure policy | Sink contract and lifecycle sequences | `DREV-002` confirmed |
| `VCC-R12` | Rollback and mode selection | Partial | Disabled, enabled, and rejected modes are selected before reuse and remain immutable | Mode-transition and equivalence matrix | Blocked by `DREV-001` |

## Contract And Evidence Boundaries

The canonical codec owns canonical bytes, root digest, and traversal-issued
member spans. Semantic validation owns issuance of an operation-local closure.
Consumers may reuse only exact certified slices after complete binding and
scope checks. Persistence writers retain independent admission authority.

Reference programs establish feasibility and deterministic local properties;
they do not establish production implementation, CI enforcement, live runtime
performance, or operational behavior. Candidate v11's static binding proof
establishes production ownership and mutation-corpus completeness, not future
runtime closure behavior.

## Confirmed Findings

### DREV-001: Closure capacity and rollback lack an enforceable operation state machine

- Product priority: `Not applicable`
- Approval disposition: `changes_required`
- Remediation eligibility: `contract_conformance_action`
- Confidence: `high`
- Finding type: `architecture / security / concurrency / operability`
- Affected scenario and prevalence evidence: Every enabled operation through the nine mapped provider triggers can approach an entry, root, path, operation, or process limit; no shipped defect is claimed because the closure is not implemented.
- Design location: `docs/design/semantic_ingestion_validated_canonical_closure.md`, sections `Contracts`, `Coherence And Capacity`, and `Failure, Compatibility, And Rollback`; `production-entrypoint-bindings-v1.md`, sections `Enabled, disabled, and fallback precedence` and `Capacity migration contract`.
- Governing source or requirement: `VCC-R06`, `VCC-R07`, `VCC-R08`, `VCC-R10`, and `VCC-R12`; root `AGENTS.md` fail-closed authority and lifecycle rules; review lanes for explicit transitions, concurrency, capacity, and recovery.
- Expected behavior: One internal owner must issue an unforgeable operation-local capability and deterministically select `disabled`, capacity-rejected full path, or reserved/enabled mode before any substitution. Reserve, stage, seal, lookup, close, and release must have explicit linearizable transitions; mode cannot change after reuse begins; every terminal path releases exactly once.
- Design behavior: The design asserts sealing, immutable pre-operation mode selection, rejection before partial authority, and release on close, but does not define issuance/sealing mechanics, typed constructor and handoff signatures, transition ownership, preflight estimation or reservation algorithm, close-versus-reader behavior, or exact release ordering. The v11 ledger marks mode selection as planned.
- Evidence: The design freezes per-root, path, operation, and process limits while saying exhaustion declines new evidence; it separately says capacity rejection occurs before partial authority. Without preflight charge estimation or full reservation, later traversal exhaustion can occur after earlier substitutions. Current `CanonicalEvidenceArena.admit_success` refuses a later entry while retaining prior entries, demonstrating why the future contract cannot inherit incremental behavior implicitly. `VCC-EXP-004` selects whole reference modes independently and does not prove the transition.
- Impact: An implementer must choose whether a late refusal preserves prior substitutions, clears authority, or requires up-front estimation. That choice changes authority, concurrency, rollback equivalence, and resource-release semantics and can permit stale/partial evidence or double release.
- Root invariant or contract boundary: Validated canonical reuse is an operation-scoped capability whose authority and resource admission must be atomic before first use.
- Equivalence class and adjacent bypasses inspected: Direct, composite, and memory-write paths; all Hermes hooks; injected, filesystem, factory, and direct composition roots; entry, root, path, operation, and process limits; disabled, reserved, active, capacity-rejected, closing, and closed behavior; stale/foreign capabilities and reservation release.
- Positive behavior that must remain valid: Exact canonical bytes, complete semantic validation, fresh writer-local admission, no persisted capability, no migration, full-path fail-closed behavior, disabled equivalence, and the frozen performance gate when enabled.
- Recommended invariant-level resolution: Define one typed private closure-scope owner, unforgeable issuer token, explicit handoff signatures, and a closed transition table covering disabled selection, preflight charge estimation, process reservation, staging, sealing, lookup, capacity refusal, close, and exact-once release. Require refusal before first substitution and disabled mode to allocate neither capability nor reservation.
- Verification needed: Constructor/forgery attacks; all nine trigger propagation tests; exact-limit and one-over-limit tests before first reuse; concurrent reserve/admit/lookup/close races; stale and foreign token tests; exact-once release on success, rejection, exception, and cancellation; enabled/disabled/rejected byte, digest, writer, replay, and durable-outcome equivalence.
- Evidence maturity affected: The lifecycle and capacity contract is not fully `specified`; existing evidence is reference/local feasibility, not implementation or CI evidence.

### DREV-002: Content-free closure observability has no typed owner or emission contract

- Product priority: `Not applicable`
- Approval disposition: `changes_required`
- Remediation eligibility: `contract_conformance_action`
- Confidence: `high`
- Finding type: `operability / verification`
- Affected scenario and prevalence evidence: Every enabled, disabled, rejected, invalidated, or closed operation covered by `VCC-R11`; no shipped defect is claimed because the feature is not implemented.
- Design location: `docs/design/semantic_ingestion_validated_canonical_closure.md`, section `Failure, Compatibility, And Rollback`; the v11 `VCC-R11` binding row.
- Governing source or requirement: `VCC-R11`, the WorkPlan completion contract, and review-lane requirements for observability, privacy, and failure behavior.
- Expected behavior: A typed content-free event and sink contract must identify its owner and composition point, exact counters and dimensions, lifecycle emission points, aggregation/reset behavior, privacy exclusions, and sink-failure policy.
- Design behavior: The design only says metrics expose counts and retained sizes without content. The v11 row is `planned_observability`, uses a conceptual runtime bridge, and has no production segment, schema, owner, emission sequence, or failure behavior.
- Evidence: Existing arena snapshots are an implementation-local diagnostic and include a nonce; existing provider observability concerns another behavior. Neither defines the new closure's operational contract. Two implementations could omit fallback/close events, emit different dimensions, leak identifiers, or let sink failures alter ingestion while both satisfy the current prose.
- Impact: Operators cannot reliably verify reduction, detect fallback or reservation pressure, or audit invalidation, and implementation would invent privacy and failure semantics.
- Root invariant or contract boundary: Observability is an owned, typed, content-free operational contract and cannot be inferred from implementation-local counters.
- Equivalence class and adjacent bypasses inspected: Hit, miss, validation failure, capacity refusal, disabled selection, reservation release, invalidation, close, exception, cancellation, and all mapped trigger families; byte, path, value, operation, tenant, and capability identifiers as prohibited content.
- Positive behavior that must remain valid: Metrics contain no canonical or semantic content and observability failure never changes validation, persistence, replay, or public outcomes.
- Recommended invariant-level resolution: Define a behaviorally named private observability event and sink, its injection owner, exact aggregate fields and permitted dimensions, one terminal emission sequence, reset semantics, strict content exclusions, and a non-authoritative sink-failure policy.
- Verification needed: Typed sink contract tests; event sequence for every lifecycle exit; enabled/disabled/rejected parity; privacy and redaction attacks; sink exception tests proving unchanged ingestion and durable outcomes.
- Evidence maturity affected: `VCC-R11` is partially specified and has no implementation, local contract proof, CI enforcement, or operational evidence.

## Requirements Coverage

Nine requirements are sufficiently specified for design approval at their
claimed maturity. `VCC-R08`, `VCC-R11`, and `VCC-R12` remain partial. `VCC-R06`,
`VCC-R07`, and `VCC-R10` are structurally mapped but their future closure
handoff depends on the state-machine correction in `DREV-001`.

## Architecture And Feasibility

The canonical codec, semantic validator, writer-admission, and persistence
ownership split is coherent. The compact-index and digest counterfactuals make
the target technically plausible. Production roots and triggers are bound by
the v11 ledger and independent oracle. The two confirmed findings are missing
contracts, not evidence that the architecture is infeasible.

## Failure, Security, And Operations

Binding, path, scope, provenance, and writer failures are designed to fall back
or reject before persistence. Persisted schemas and replay remain unchanged.
The unresolved state machine prevents a determinate judgment for concurrent
close, late capacity refusal, and exact-once resource release. The unresolved
observability contract prevents a determinate privacy and sink-failure judgment.

## Verification And Evidence Maturity

The candidate correctly labels experiments as reference feasibility. It does
not claim production implementation, CI, live, or operational evidence. The
implementation verification matrix must retain all test reviewer's gates,
including nine-trigger propagation, writer-local retries, adversarial scope and
binding failures, concurrent capacity boundaries, rollback equivalence, and
revision-bound CI enforcement.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Residual risk | Status |
| --- | --- | --- | --- | --- | --- |
| Partial reuse authority | Capacity refusal after an earlier hit | Mixed enabled/full-path operation and ambiguous rollback | Closed operation state machine with preflight reservation | None if transition proof passes | Open, `DREV-001` |
| Reservation race or double release | Concurrent close, exception, or cancellation | Capacity leakage or underflow | Linearizable owner and exact-once terminal release | Scheduling defects remain implementation risk | Open, `DREV-001` |
| Forged or stale closure | Conventional object construction or cross-scope handoff | Invalid digest substitution | Issuer token, typed handoffs, state and scope checks | Implementation defects remain test risk | Open, `DREV-001` |
| Content leakage in metrics | Content-bearing fields or labels | Privacy and provenance exposure | Typed allowlisted event fields and attack tests | Sink implementation risk | Open, `DREV-002` |
| Metrics alter ingestion | Sink failure propagates | Availability or durable-outcome regression | Explicit non-authoritative failure policy | Lost telemetry during sink outage | Open, `DREV-002` |
| Performance target misses production | Reference model differs from implemented path | Less than 90 percent reduction | Revision-bound production counters and CI gate | Environment variance | Implementation gate |

## Rejected Or Consolidated Findings

- The specification reviewer's capacity/mode/rollback observation and the
  correctness reviewer's capability lifecycle finding are `confirmed` and
  consolidated into `DREV-001` because they share one operation-authority state
  machine.
- The correctness reviewer's metrics observation is `confirmed` as `DREV-002`.
- The test reviewer reported no finding and recommended approval. Its proposed
  implementation gates are retained as required handoff verification, not
  evidence that the two missing design contracts already exist.
- Arbitrary external post-definition monkeypatching remains `unsupported` and
  outside the accepted source-hash-bound grammar. No reviewer supplied a new
  governing requirement or reachable counterexample that reopens that family.
- Missing production implementation and CI enforcement are `already addressed`
  as phase-correct evidence maturity, not design defects by themselves.

## Required Changes Before Approval

1. Specify the closed operation capability, reservation, lifecycle, rollback,
   concurrency, and exact-once release state machine described by `DREV-001`.
2. Specify the typed content-free observability owner, event, emission sequence,
   privacy boundary, and sink-failure policy described by `DREV-002`.
3. Freeze executable positive, boundary, race, forgery, privacy, and failure
   evidence for both corrected contracts, then freeze a new candidate and run a
   bounded delta review followed by a fresh final whole-design review if the
   correction materially changes the authority or lifecycle contract.

## Non-Blocking Follow-Ups

No separate P3 follow-up was accepted. Implementation must preserve the test
reviewer's revision-bound production gates, but those gates are already part of
the implementation handoff rather than deferred design polish.

## Final Outcome

`Changes required`.

Candidate v11 is not approved for implementation. `DREV-001` and `DREV-002`
are determinate contract-conformance actions. No P1 or P2 product-remediation
round is authorized because the proposed feature is not yet shipped and no
incorrect current product behavior was demonstrated.

## Review Limitations

This is a design-readiness judgment for frozen candidate v11. It does not prove
an implementation, production speedup, CI enforcement, live provider behavior,
or operational reliability. The review did not edit the canonical design,
production code, or repository tests.
