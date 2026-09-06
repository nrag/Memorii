# Design Review: Canonical Evidence Performance Observability

## Review Metadata

- Review ID: semantic-ingestion-canonical-evidence-performance-observability-full-2026-08-16
- Review mode: full
- Review outcome: Changes required
- Design path: `docs/design/semantic_ingestion_canonical_evidence_performance.md` and its frozen normative artifacts
- Design baseline: candidate lock SHA-256 `9a92cba79bbdb84ff6bab43351a45ceefd528bec0fe1a5fd482dda47bcf2d82b`
- Implementation baseline: current repository state inspected as feasibility evidence only; the candidate claims no implementation
- Review date: 2026-08-16
- Reviewers: independent spec, correctness, and test passes reconciled by the coordinator
- Included scope: public 4x2 construction and authority, executable lock/gate authority, diagnostic cardinality/budgets, arena lifecycle, fixture integrity, baseline/tooling sequencing, and observability measurement ownership
- Excluded scope: canonical-design edits, schemas, manifests, lock changes, production/test/runner edits, baseline mutation, and parent WorkPlan changes

## Executive Assessment

The material schema and measurement-contract change requires a full review. The frozen candidate has useful design intent but is not implementation-ready: it lacks an executable, public production authority path; its lock and proof tooling are not self-verifying; the diagnostic contract cannot mechanically establish its proposed per-arena facts; lifecycle ownership is not bound; the fixture pin is stale; and its gate sequencing is circular. The existing baseline remains invalid.

No P1/P2 product defect is validated. These are determinate implementation-readiness and contract-conformance defects: DREV-001 blocks approval and DREV-002 through DREV-006 are changes required.

## Governing Sources

Precedence follows root `AGENTS.md`: `docs/design/memorii_spec.md`, `docs/design/memorii_storage_details.md`, `docs/design/event_model.md`, `docs/IMPLEMENTATION_RULES.md`, the frozen canonical-evidence performance design and normative artifacts, then WorkPlans and current code as feasibility evidence. Review process and finding fields follow `.agents/PLANS.md` and `.agents/skills/review-design/`.

## Independently Reconstructed Requirements

| Requirement | Source | Design coverage | Acceptance criteria | Verification | Status |
| --- | --- | --- | --- | --- | --- |
| Public 4x2 construction reaches canonical runtime authority | `.agents/PLANS.md` production-entrypoint bindings | partial | exact production trigger, composition root, arguments, owner chain, and non-test caller proof | behavior-named harness maps all eight cells | changes required |
| Frozen lock binds every executable authority | change-impact closure | partial | harness, root recipe, and validator have paths and SHA-256 pins; no WorkPlan identity | lock-resolution and mismatch mutation | changes required |
| Diagnostic evidence establishes scoped arithmetic | verification/evidence maturity rules | partial | per-cell identity keys and budgets make one-per-identity and aggregate cap falsifiable | adversarial duplicated/copy/partition mutations | changes required |
| Arena lifecycle is a real runtime contract | lifecycle and production-entrypoint binding rules | partial | construction, pass, nonce/retry/recovery/concurrency/capacity, and `finally` teardown bind to exact owner chain | production-path lifecycle proof | changes required |
| Frozen fixture is reproducible | authority-chain closure | contradictory | fixture source bytes match manifest pin before baseline starts | hash resolution | changes required |
| Feasibility gating does not prohibit required tooling | implementation readiness and convergence rules | contradictory | evidence tooling can prove feasibility before baseline; production arena edits wait for valid baseline | staged gate proof | changes required |

## Contract And Evidence Boundaries

The required authority chain is behavior-named source bytes -> root recipe -> executable public 4x2 harness -> validator -> per-cell diagnostic/latency artifacts -> lock-bound aggregate decision. A WorkPlan path or revision identity is a planning coordinate and cannot be executable authority. `production_entrypoint_bindings` must prove a non-test caller reaches the canonical owner with required authority; private composition, fixtures, constructors without an executed public call, defaults, and fallbacks do not satisfy it.

Eight fresh arenas require each diagnostic observation to carry a cell/arena partition key and each cell to state its local identity and digest budgets. A fixed `executed_combinations` field, opaque IDs, and counters without uniqueness/partition equations cannot prove the global count or one-per-identity claim. Diagnostic and latency modes must retain their distinct measurement semantics.

## Confirmed Findings

### DREV-001: No executable pinned public 4x2 production constructor and authority chain

- Product priority: Not applicable
- Approval disposition: blocks_approval
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: architecture
- Affected scenario and prevalence evidence: the required four-root by two-backend public production matrix; every intended baseline/candidate measurement depends on one authoritative construction for each of its eight cells. No P1/P2 product defect is asserted because this candidate is not implemented.
- Design location: production-entrypoint bindings, performance measurement contract, and lock boundary
- Governing source or requirement: `.agents/PLANS.md` Production Entrypoint Bindings; root `AGENTS.md` canonical-owner and thin-integration rules
- Expected behavior: an exact executable harness constructs each public production service/backend/ingress/request combination, invokes the public trigger once with stated authority, and reaches the canonical arena owner through a non-test caller.
- Design behavior: the runner always aborts; the described composition is private or test-only and is not an executable authority chain.
- Evidence: `production-entrypoint-bindings-v1.json` declares design-only inventory and no caller propagation; current runner behavior aborts; there is no exact pinned public 4x2 executable constructor/authority chain.
- Impact: a baseline or candidate could measure a private, fixture, fallback, or absent path while being presented as production evidence.
- Root invariant or contract boundary: runtime authority exists only through a real public composition root carrying required authority to the canonical owner.
- Equivalence class and adjacent bypasses inspected: direct, factory, filesystem, and Hermes roots; memory and JSONL backends; public `sync_event`; private roots; fixture-only entrypoints; optional/default composition; fallback and abort paths.
- Positive behavior that must remain valid: the public APIs and existing authority checks remain unchanged; missing authority must fail closed with no fabricated measurement.
- Recommended invariant-level resolution: define and pin a behavior-named public 4x2 harness/root recipe that constructs fresh production state per cell, invokes `ProviderMemoryService.sync_event`, records exact authority and reached canonical owner, and rejects any absent, private, test-only, defaulted, or fallback chain.
- Verification needed: a non-test production-caller mapping and executed path evidence for all eight cells, including authority arguments, canonical-owner arrival, and fail-closed absent-authority mutations.
- Evidence maturity affected: specified, derivable, implemented, locally verified, CI enforced, and operationally verified.

### DREV-002: Lock omits executable harness and validator, and binds an unverifiable WorkPlan coordinate

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: verification
- Affected scenario and prevalence evidence: every baseline/candidate acceptance decision depends on resolving the exact harness, root recipe, and validator against the frozen lock.
- Design location: `candidate-lock-v1.json`, revision-hash fields, and runner selection
- Governing source or requirement: `.agents/PLANS.md` change-impact/authority-chain closure and identity hygiene
- Expected behavior: the lock binds every behavior-named executable authority by path and hash; revision identities are independently resolvable; the runner selects current behavior, not a stale implementation plan.
- Design behavior: the lock omits the executable harness and validator; `revision_hashes.workplan` is pathless and unverifiable; and the runner uses the stale implementation plan.
- Evidence: frozen lock lists normative design artifacts but no harness/root recipe/validator executable identities; the current binding is design-only; runner selection is stale.
- Impact: lock equality can coexist with changed executable behavior or an unresolvable planning coordinate, invalidating reproducibility.
- Root invariant or contract boundary: frozen acceptance authority must include every executable source-to-decision node and must not depend on planning/evidence coordinates.
- Equivalence class and adjacent bypasses inspected: lock artifact entries, executable harness, root recipe, validator, runner selection, `revision_hashes.workplan`, self-exclusion rule, and stale implementation-plan route.
- Positive behavior that must remain valid: lock self-exclusion and legitimate normative artifact pins remain intact; WorkPlans may remain human traceability records but not executable identity.
- Recommended invariant-level resolution: remove WorkPlan identity from executable revision hashes; bind behavior-named harness, root recipe, and validator with canonical paths and SHA-256 values; make runner selection resolve those locked paths and reject stale or missing entries.
- Verification needed: lock resolver plus missing/path/hash/substitution/stale-runner mutations, proving an acceptance run cannot begin unless all executable authorities resolve to the lock.
- Evidence maturity affected: specified, derivable, locally verified, and CI enforced.

### DREV-003: Diagnostic proof is neither mechanically closed nor per-arena/per-cell scoped

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: verification
- Affected scenario and prevalence evidence: all eight fresh arena cells contribute to the claimed one-full-digest-per-identity and at-most-1,000 aggregate diagnostic properties.
- Design location: verification contract, performance schema, and diagnostic mode description
- Governing source or requirement: `.agents/PLANS.md` verification closure; review-design evidence-maturity and operations lanes
- Expected behavior: diagnostic events carry an unforgeable cell/arena partition key, local identity set and budget equations, aggregate equations, unique event identity, and a mode label consistent with profiling semantics.
- Design behavior: one-per-identity and the aggregate cap are impossible to establish across eight fresh arenas without per-cell key/budget; fixed `executed_combinations` can be fabricated; opaque IDs/counters omit partition and uniqueness equations; and the diagnostic mode label contradicts profiling.
- Evidence: the candidate declares eight fresh arenas, a global cap, opaque counters/IDs, fixed combinations, and a diagnostic label that conflicts with its profile claim.
- Impact: fabricated, copied, or cross-cell evidence can satisfy shape checks while failing the required arithmetic or measuring a different quantity.
- Root invariant or contract boundary: diagnostic proof is a closed, cell-scoped algebra, not an unscoped record shape or asserted aggregate.
- Equivalence class and adjacent bypasses inspected: all four roots, both backends, fresh arenas, per-identity/full/reused/capacity/legacy counters, aggregate cap, `executed_combinations`, profile labels, copied rows, duplicate events, missing partitions, and cross-cell merges.
- Positive behavior that must remain valid: diagnostic observations may retain valid public-codec fallback and legacy/capacity behavior; unprofiled latency remains distinct.
- Recommended invariant-level resolution: define a per-cell key including root/backend/arena nonce, declared local eligible identity cardinality and local budgets, unique event/identity equations, aggregate roll-up from validated cells, and mode semantics that unambiguously state whether profiling occurred.
- Verification needed: validator mutations for duplicate/cross-cell/copied/missing partitions, fabricated combination count, local and aggregate budget violations, uniqueness failure, and mode-label/profile mismatch.
- Evidence maturity affected: specified, derivable, locally verified, independently reproduced, and CI enforced.

### DREV-004: Arena lifecycle and ownership are not bound to an exact production owner chain

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: architecture
- Affected scenario and prevalence evidence: every public matrix invocation needs deterministic arena construction, passage, teardown, and retry/recovery/concurrency behavior before any diagnostic or performance result is meaningful.
- Design location: arena lifecycle prose and production-entrypoint bindings
- Governing source or requirement: root `AGENTS.md` lifecycle/recovery invariants; `.agents/PLANS.md` production-entrypoint bindings
- Expected behavior: exact canonical owners define arena creation, argument pass to codecs/validators, nonce reuse for same-invocation retry, new nonce on later invocation, `finally` teardown, recovery behavior, concurrency isolation, and capacity ownership.
- Design behavior: those lifecycle responsibilities are described but not bound to one exact production owner/call chain.
- Evidence: the binding inventory is design-only, has no caller propagation, and does not establish all construction/pass/teardown/retry/recovery/concurrency/capacity transitions at exact callsites.
- Impact: implementation can leak arena state, reuse a nonce across invocation boundaries, dispose it too early, bypass it on recovery, or accidentally share capacity across concurrent requests.
- Root invariant or contract boundary: invocation-local arena state is private lifecycle state with exact owner, authority, isolation, and terminal teardown.
- Equivalence class and adjacent bypasses inspected: initial invocation, same-invocation retry, acknowledgement-loss recovery, later invocation, terminal and retry reloads, graph-absent continuation, concurrent calls, capacity boundary, exception path, and `finally` teardown.
- Positive behavior that must remain valid: public codec APIs remain unchanged; foreign/stale/copied context fails closed and retains no arena state.
- Recommended invariant-level resolution: add an exact production owner-chain table assigning construction, codec/validator pass, nonce policy, retry/recovery behavior, concurrency isolation, capacity accounting, and `finally` teardown to each canonical callsite, with no optional fallback.
- Verification needed: path proofs and fault/retry/recovery/concurrency/capacity traces showing construction once per cell invocation, correct nonce reuse/newness, teardown on success and exception, and zero cross-invocation retention.
- Evidence maturity affected: specified, derivable, implemented, locally verified, and operationally verified.

### DREV-005: Manifest pins a stale bootstrap fixture hash, so the baseline cannot start

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: verification
- Affected scenario and prevalence evidence: every required baseline sample reads the standard fixture before measurement.
- Design location: `standard-fixture-manifest-v1.json` fixture pin and baseline gate
- Governing source or requirement: `.agents/PLANS.md` complete authority-chain closure; frozen-artifact integrity requirement
- Expected behavior: the manifest SHA-256 equals the current canonical `bootstrap_graph_v3_fixture` bytes before a baseline command can begin.
- Design behavior: the manifest pins a stale `bootstrap_graph_v3_fixture` hash while current bytes differ.
- Evidence: direct current-byte/hash comparison recorded by the review packet contradicts the manifest pin; the existing baseline is invalid.
- Impact: the baseline cannot reproducibly identify its workload and any capture started from it is untrustworthy.
- Root invariant or contract boundary: a frozen fixture manifest is executable workload authority only when its pin matches its source bytes.
- Equivalence class and adjacent bypasses inspected: fixture path, manifest hash, lock artifact hash, baseline receipt reference, changed source bytes, and hash-mismatch start gate.
- Positive behavior that must remain valid: a correct pin and all other fixed workload identities remain strictly required; mismatch must fail closed.
- Recommended invariant-level resolution: regenerate or correct the manifest and dependent lock from the current intended fixture bytes in the linked remediation, then require validator rejection of the old/stale hash before baseline capture.
- Verification needed: positive exact-byte resolution plus stale, substituted, missing, and lock-mismatch fixture mutations; no baseline start on any mismatch.
- Evidence maturity affected: specified, derivable, locally verified, and CI enforced.

### DREV-006: Circular baseline gate excludes the tooling required to satisfy it

- Product priority: Not applicable
- Approval disposition: changes_required
- Remediation eligibility: contract_conformance_action
- Confidence: high
- Finding type: governance
- Affected scenario and prevalence evidence: the only path to the required baseline depends on the harness and validator that the candidate says cannot be implemented before baseline and explicitly excludes.
- Design location: approval boundary, scope exclusions, and baseline-capture gate
- Governing source or requirement: `.agents/PLANS.md` completion/stop rules and review-design convergence guidance
- Expected behavior: the gate sequence permits bounded evidence-tooling feasibility implementation and review before baseline capture, while preserving the prohibition on production behavior changes before the baseline is valid.
- Design behavior: implementation cannot begin until baseline, while the required harness and validator are unimplemented and excluded from the candidate.
- Evidence: the candidate labels harness/validator work unimplemented or excluded, requires their execution for the baseline, and prohibits implementation until that baseline.
- Impact: no authorized action can produce the prerequisite baseline, leaving the design non-executable.
- Root invariant or contract boundary: prerequisites must be achievable through an explicitly authorized, bounded sequence; baseline evidence cannot bootstrap itself.
- Equivalence class and adjacent bypasses inspected: evidence harness, root recipe, validator, baseline capture, candidate capture, design-only scope, production arena edits, and feasibility review.
- Positive behavior that must remain valid: production arena edits remain prohibited until baseline validity is established; no invented baseline or bypassed validation is allowed.
- Recommended invariant-level resolution: explicitly permit evidence-tooling feasibility implementation and its review before baseline capture; prohibit production arena edits until the corrected fixture and valid baseline gate are complete.
- Verification needed: staged authorization matrix proving tooling feasibility is allowed, baseline rejects absent/stale tooling or fixture authority, and production arena edits remain blocked before baseline validity.
- Evidence maturity affected: specified, derivable, implemented, locally verified, and CI enforced.

## Requirements Coverage

All reconstructed requirements are partial or contradictory. The candidate has no complete production-entrypoint binding, executable lock closure, mechanically closed diagnostic algebra, full lifecycle table, valid fixture pin, or acyclic staged gate.

## Architecture And Feasibility

The proposed private arena may remain architecture-compatible only after DREV-001 and DREV-004 bind it to the public owner chain. The design currently demonstrates vocabulary and intended constraints, not an executable production construction. Child RSS is not implemented in the current runner despite the mapper claim; this is implementation evidence relevant to DREV-001/DREV-002, not a separate finding.

## Failure, Security, And Operations

Absent public authority, stale lock entries, stale fixture bytes, missing diagnostic partitions, and invalid lifecycle transitions must fail closed without a result. Teardown, retry, recovery, concurrency, and capacity have insufficient bound ownership to support operational claims. The existing baseline remains invalid.

## Verification And Evidence Maturity

The candidate is specified in places and partially derivable, but executable tooling, current-runner behavior, baseline capture, child RSS, local validation, independent reproduction, CI enforcement, and operational proof are not established. Parent timing/RSS/`Queue.empty`/schema-output observations are later implementation evidence under DREV-001/DREV-002. Missing tests/runtime proof are expected lower maturity and do not independently block this design absent an incomplete algorithm. Historic 330/42013/42343 equivalence is already correctly blocked by this material delta and creates no separate finding.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Residual risk | Status |
| --- | --- | --- | --- | --- | --- |
| Non-production measurement | private/test/fallback construction | invalid performance conclusion | DREV-001 public 4x2 harness and caller proof | none after fresh full review | open |
| Unpinned executable behavior | harness/validator changes outside lock | irreproducible acceptance | DREV-002 executable pins | none after lock mutation proof | open |
| Fabricated diagnostic arithmetic | cross-cell/copy/opaque counters | false budget compliance | DREV-003 scoped algebra | observer defects require later implementation proof | open |
| Lifecycle leakage | retry/recovery/concurrency exception | invalid reuse or retention | DREV-004 owner/lifecycle table | production proof deferred | open |
| Invalid workload | stale fixture hash | baseline cannot start | DREV-005 corrected pin | none after resolution gate | open |
| Deadlocked readiness gate | tooling excluded before baseline | no lawful progress | DREV-006 staged sequence | production edits remain gated | open |

## Rejected Or Consolidated Findings

- Parent timing, RSS, `Queue.empty`, and schema-output defects are implementation evidence under DREV-001/DREV-002 and required later evidence actions, not separate design findings because the child boundary is already specified.
- The coordinator corrects a mapper claim: child RSS is not implemented in the current runner.
- Missing tests or runtime proof are expected lower maturity and do not independently block design unless they reveal an incomplete algorithm.
- Historic 330/42013/42343 equivalence is already correctly blocked by the material delta; no separate finding is issued.

## Required Changes Before Approval

1. Correct DREV-001 through DREV-006 in a linked `$build-design` remediation WorkPlan and freeze a new lock.
2. Permit only evidence-tooling feasibility implementation and its review before baseline; retain the prohibition on production arena edits until the baseline is valid.
3. Submit the new frozen lock to a fresh full review; do not treat this report as approval for implementation.

## Non-Blocking Follow-Ups

None. All identified concerns are consolidated into the six required invariant families.

## Final Outcome

Changes required. `remaining_validated_p1_p2: []`. `blocks_approval: [DREV-001]`. `changes_required: [DREV-002, DREV-003, DREV-004, DREV-005, DREV-006]`. The existing baseline remains invalid. This bounded review is complete but does not complete its parent design milestone.

## Review Limitations

This was a read-only review reconciliation against the stated frozen baseline. No canonical artifacts were changed and no validation commands were run by assigned scope. It records independent spec/correctness/test findings as reconciled evidence; the required later proof remains implementation and fresh-review work.
