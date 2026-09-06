# Semantic Ingestion Validation-Boundary Performance Design

- Work ID: semantic-ingestion-validation-boundary-performance-2026-08-17
- Work type: design
- Status: blocked
- Coordinator: Codex
- Created: 2026-08-17
- Last updated: 2026-08-17
- Parent WorkPlan: docs/work/semantic-ingestion-canonical-evidence-performance-2026-08-15/implementation.plan.md
- Related WorkPlans: docs/work/semantic-ingestion-codec-owned-attestation-2026-08-16/design.plan.md; docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16/debug.plan.md; docs/work/semantic-ingestion-canonical-evidence-performance-2026-08-15/design.plan.md
- Canonical inputs: docs/design/semantic_ingestion_canonical_evidence_performance.md; docs/work/semantic-ingestion-codec-owned-attestation-2026-08-16/evidence/coa-exp-001-exact-preimage-inventory-v1.json; docs/work/semantic-ingestion-codec-owned-attestation-2026-08-16/evidence/coa-exp-002-trusted-issuance-v1.json; docs/work/semantic-ingestion-codec-owned-attestation-2026-08-16/evidence/coa-exp-002b-propagation-inventory-v1.json; candidate lock `24da95523b9a050266034cd6f3b923d52a4d8cc97cf83d32d83c1285bb2d99c3`
- Expected outputs: docs/design/semantic_ingestion_validation_boundary_performance.md; validation-boundary inventory and reference experiments; requirement/evidence and attack matrices; frozen candidate design; independent design review decision

## Objective

Design a closed semantic-ingestion validation architecture that performs complete validation at every trust, serialization, persistence, reload, recovery, provider, and public boundary while eliminating demonstrably redundant internal reconstruction and revalidation of already validated values. The design must preserve exact canonical bytes, digests, errors, durable effects, transaction behavior, and fail-closed semantics and must show a credible measured path to the frozen M3.1 performance objective before implementation approval.

## Problem And Evidence Baseline

The safe operation-local canonical arena improved an unprofiled same-revision legacy-fallback comparison by only `5.87%`. The production workload performs 1,898 contract digest calls with 53 unique outputs. Content-addressed validation accounts for 1,303 calls, 1,281 of which repeat 22 exact identities.

The opaque-attestation feasibility operation proved that a runtime-only handle can reject direct forgery and context attacks, but production propagation is not bounded: the five dominant contract types execute 998 validations across 82 runtime origins. Only 292 occur beneath `encode_semantic_contract`; 706 occur outside it. Of 400 production `model_validate` callsites, only one supplies validation context. Continuing with automatic attestation lookup would require prohibited digest, identity, equality, or secondary-fingerprint authority.

The selected direction is therefore to classify validation boundaries explicitly and remove only internal repeated reconstruction whose input authority is already a validated, operation-local typed value. This direction must not convert an external, persisted, decoded, recovered, copied, constructed, or mutable value into trusted internal state.

## Completion Contract

This operation completes only when:

- every semantic-ingestion validation origin is classified by input authority and required validation stage;
- the accepted transition grammar between untrusted bytes, decoded values, validated typed values, canonical bytes, persisted values, reloaded values, and durable effects is closed;
- public, provider, adapter, codec, persistence, reload, recovery, transaction, and internal composition boundaries have exact owners and fail-closed behavior;
- no optimization depends on caller digests, object identity, equality, shallow freezing, hidden context, or a second canonical representation;
- positive, negative, mutation, concurrency, retry, cancellation, replay, reload, persistence, capacity, compatibility, and rollback evidence is specified;
- bounded reference experiments prove exact behavioral equivalence and isolate the removable cost at representative high-impact boundaries;
- a production-shaped feasibility run demonstrates a credible path to the frozen 75% reduction without counting profiled/unprofiled or same-revision fallback evidence as certification;
- the identity, changed-surface, authority-chain, gate, and evidence-maturity ledgers are complete;
- one frozen candidate passes independent `spec_auditor`, `correctness_reviewer`, and `test_reviewer` review with every finding reconciled;
- implementation requires no hidden semantic or scope decision.

## Scope

Included:

- classification of all semantic-ingestion validation and reconstruction boundaries;
- typed runtime states distinguishing untrusted, decoded, fully validated, canonicalized, persisted, and reloaded values where necessary;
- internal APIs that preserve validated authority explicitly without exposing it publicly or durably;
- canonical codec, Pydantic validation, persistence, recovery, provider, and adapter integration contracts;
- deterministic equivalence, mutation, attack, and performance feasibility evidence;
- rollout, rollback, observability, and interaction with the current operation-local arena.

Excluded:

- production implementation or test changes during this design operation;
- weakening validation at public, provider, decoded-byte, persisted, reload, recovery, or transaction boundaries;
- changes to canonical bytes, digest domains, persisted schemas, public APIs, or durable records;
- framework-specific coupling or cross-operation validated-value sharing;
- unrelated cold-start distribution scanning and capture-supervisor work;
- changing the 75% target without a separate explicit external decision.

Explicitly deferred:

- implementation, migration, and M3.1 certification until design approval;
- removal of the current safe arena unless an approved design proves replacement behavior and rollback.

## Constraints And Universal Invariants

- Raw, decoded, model-produced, validated, candidate, committed, persisted, and reloaded states remain distinct.
- Provider transport parsing does not imply domain-semantic validation.
- Canonical bytes remain owned exclusively by the existing CTV encoder.
- Content digest validation remains owned by the semantic contract type and its literal domain/excluded-field contract.
- Persistence and durable recovery always validate bytes and typed semantics afresh; runtime validation state is never serialized or reconstructed from a flag.
- `model_construct`, `model_copy`, direct constructors, adapters, fixtures, and integrations cannot manufacture validated authority.
- Internal validation authority is operation-local, private, non-serializable, capability-bound, and unavailable after error, cancellation, retry exhaustion, teardown, or later invocation.
- Missing or mismatched authority executes the complete existing validation path.
- Optimization may remove repeated work only when exact authority provenance is explicit and mechanically checkable.
- Existing canonical bytes, digest values, error classes/messages where contractual, persisted payloads, durable effects, transaction ordering, and fail-closed outcomes remain identical.

## Initial Requirements Ledger

| ID | Requirement | Acceptance criterion | State |
| --- | --- | --- | --- |
| VBP-001 | Complete boundary inventory | Every production semantic-ingestion `model_validate`, direct constructor, `model_copy`, `model_construct`, decode, encode, persistence, reload, and recovery origin is classified. | specified |
| VBP-002 | Closed validation-state grammar | Only enumerated typed transitions are legal; unknown or missing authority runs full validation or rejects. | specified |
| VBP-003 | Trust-boundary validation | Public, provider, decoded-byte, persisted, reload, recovery, and transaction inputs always complete all applicable validation stages. | specified |
| VBP-004 | Internal authority provenance | Any reusable validated state is issued only after complete validation and carries private operation, owner, type, profile, codec, domain, and purpose authority. | specified |
| VBP-005 | No caller manufacture | Digests, equality, object identity, flags, wrappers, copies, constructs, serialized data, and integrations cannot manufacture validated state. | locally verified for selected edge |
| VBP-006 | Behavioral equivalence | Enabled, unavailable, saturated, and rollback paths produce identical bytes, digests, errors, persistence, terminal outcomes, and durable effects. | locally verified for selected edge |
| VBP-007 | Lifecycle isolation | Success, error, cancellation, retry, concurrency, later invocation, reload, and recovery cannot leak validation authority. | locally verified for selected edge |
| VBP-008 | Bounded resources | Runtime validation state has deterministic entry, byte, operation, and process limits with no eviction, overwrite, or negative caching. | partial; process boundary verified, entry/byte closure open |
| VBP-009 | Compatibility and rollback | Rollout can disable the optimization and return to full validation without data migration or persisted-format change. | locally verified in reference path |
| VBP-010 | Performance feasibility | Reference and production-shaped experiments isolate removed validations and show a credible path to the frozen target before implementation. | blocked; current design is not a credible 75% route |
| VBP-011 | Evidence separation | Deterministic, reference, same-revision fallback, profiled diagnostic, latency, and certification evidence remain distinct. | locally verified in design evidence |
| VBP-012 | Thin proof fixtures | Test fixtures supply inputs and observe outputs only; production owners execute validation, canonicalization, persistence, and lifecycle behavior. | locally verified in reference experiments |

## Validation-State Grammar To Close

Provisional states:

- `UntrustedBytes`: external or persisted bytes with no semantic authority.
- `DecodedValue`: closed CTV decoding completed; domain semantics unproven.
- `ValidatedSemanticValue`: exact typed/domain/content/provenance validation completed for one operation and purpose.
- `CanonicalSemanticBytes`: existing CTV owner emitted exact bytes from a validated value.
- `PersistedSemanticValue`: canonical bytes committed transactionally; runtime authority is not persisted.
- `ReloadedSemanticValue`: persisted bytes decoded and fully revalidated; receives new operation-local authority only after success.

No state transition may be inferred from a field name, digest, object type alone, or historical validation in another operation.

## Boundary Classification

Mandatory full-validation boundaries:

- public/provider ingress;
- model/provider output and adapter input;
- raw or canonical byte decode;
- persistence admission and transaction commit;
- persisted read, reload, replay, and recovery;
- cross-operation, concurrent-operation, or process boundary;
- any copied, constructed, mutated, context-free, wrong-purpose, or capacity-fallback value.

Candidate internal-reuse boundaries:

- repeated composition of an unchanged private validated value within the same owner, operation, purpose, and transaction attempt;
- repeated canonical encoding requested by the same owner before persistence when exact validated authority remains explicit;
- nested reconstruction caused solely by internal `model_dump` followed by same-type `model_validate`, when no trust, serialization, persistence, or mutation boundary intervenes.

Every candidate must be proven individually by the inventory and then generalized only through a closed owner/state rule.

## Alternatives

- `A` Boundary-indexed validated-value capability: explicit private typed state flows only across classified internal edges. Recommended for feasibility because authority is visible and missing capability falls back.
- `B` Eliminate internal dump/revalidate pairs by retaining original validated frozen values. Risk: shallow freezing and mutation/construct bypass; eligible only where deep immutability and owner provenance are proven.
- `C` Custom Pydantic core schema/context propagation for all semantic contracts. Risk: broad framework coupling, hidden context, reload ambiguity, and migration complexity.
- `D` Automatic digest/object/equality/fingerprint cache. Prohibited.
- `E` Keep current behavior and revise M3.1. Excluded by the user’s selected direction unless feasibility later proves no safe architecture.

## Feasibility Experiments

### VBP-EXP-001: Boundary Census

Build a field-aware AST and runtime inventory classifying every relevant origin as ingress, construction, internal reconstruction, codec, persistence admission, reload/recovery, adapter, or unknown. Record input form, owner, purpose, context propagation, persisted crossing, and runtime frequency. Unknown origins block optimization.

### VBP-EXP-002: High-Impact Edge Proof

Select the smallest internal edge family accounting for material repeated validation. Build a reference-only capability flow that leaves mandatory boundaries unchanged. Mutate type, nested value, domain, purpose, operation, copy/construct state, persistence/reload source, and lifecycle context. Any accepted attack is `NO-GO`.

### VBP-EXP-003: Behavioral Equivalence

Run legacy and reference paths over identical production-shaped input. Require byte-identical canonical and persisted outputs, identical errors and terminal outcomes, and complete full-validation counts at mandatory boundaries. Recompute outputs independently.

### VBP-EXP-004: Performance Discrimination

Run isolated same-mode legacy, reference, missing-authority, saturation, and rollback cells. Measure removed validation families and wall time. A `GO` requires enough isolated benefit to make the 75% target credible; otherwise stop for an external decision.

## Attack Matrix

| Family | Mutations | Required result |
| --- | --- | --- |
| State forgery | caller flag, digest, wrapper, object identity, equality, copied capability | full validation or reject |
| Construction | direct constructor, `model_construct`, `model_copy`, subclass, sibling type | full validation or reject |
| Content | scalar/nested mutation, collection reorder/duplicate, excluded-field change | full validation or legacy-equivalent reject |
| Context | wrong operation, owner, purpose, type, profile, codec, domain, nonce | full validation; no reuse |
| Serialization | encode/decode, persistence, reload, replay, recovery | new full validation; no restored authority |
| Lifecycle | success, exception, cancellation, retry, concurrent/later invocation | teardown and isolation |
| Capacity | exact and first-above entry/item/operation/process limits | deterministic full-validation fallback |
| Compatibility | disabled optimization, mixed rollout, rollback | no data migration; identical behavior |
| Evidence | mixed revision/mode, same-revision fallback certification, fixture business logic | reject claim |

## Identity And Coordinate Hygiene

| Identity | Class | Allowed surface |
| --- | --- | --- |
| `VBP-*`, experiment and review IDs | planning/evidence coordinate | WorkPlan/evidence only |
| validation state names | provisional behavioral code identities | canonical design and future private runtime types only after approval |
| operation/owner/purpose capability | ephemeral security identity | private runtime only |
| canonical profile, codec, type, domain, digest | behavioral protocol/content identity | existing owners and persisted/runtime contracts |
| persisted record and transaction identity | durable behavioral identity | existing persistence owners only |

Planning coordinates never enter production names, serialized values, public APIs, events, or durable records.

## Evidence Maturity

- Current arena: implemented and locally targeted-tested; insufficient performance; not M3.1-certified.
- Opaque attestation: reference-prototyped, attacked, and abandoned for propagation infeasibility.
- Validation-boundary architecture: specified at initial requirement level; one bounded private-authority edge is reference-prototyped.
- Boundary census: locally verified for experiment selection; classifications are not implementation authority.
- Reference experiments: `VBP-EXP-002` establishes bounded feasibility at `TextPreparationService.prepare`; `VBP-EXP-002B` locally verifies the selected edge's authority attack families; `VBP-EXP-003` locally verifies behavioral equivalence; `VBP-EXP-004` measures a 13.31% same-mode median improvement and rejects this design as a credible route to the frozen 75% target.
- Canonical design and independent review: not started.

## Changed-Surface Ledger

This design operation may change only:

- this WorkPlan;
- `docs/design/semantic_ingestion_validation_boundary_performance.md`;
- reference-only experiment/evidence artifacts under this WorkPlan directory;
- review artifacts under `docs/reviews/`;
- status/link records in related WorkPlans.

Production code, production tests, public or persisted schemas, and the current candidate lock remain unchanged.

## Decisions And Blockers

- External decision 2026-08-17: pursue the broader validation-boundary design; do not revise M3.1 at this time.
- Confirmed predecessor finding: opaque-handle propagation is infeasible as a bounded codec change.
- `VBP-EXP-002` decision: `REFERENCE_EDGE_SECURITY_AND_EQUIVALENCE_PASS`. The exact registered built-in producer can carry one-use private authority to `TextPreparationService.prepare`; injected forged/constructed producers reject, while copied proxy, missing context, and capacity saturation execute the complete validation path.
- `VBP-EXP-002B` decision: `FAMILY_ATTACKS_PASS`. The selected edge's reference authority is one-use, operation-local, owner- and purpose-bound; it is absent from persistence/reload callsites and fails closed across mutation, type substitution, replay, later invocation, exception, cancellation, concurrency, and process-capacity boundaries.
- `VBP-EXP-003` decision: `BEHAVIORAL_EQUIVALENCE_PASS`. Enabled, unavailable, saturated, and rollback cells emitted identical production-shaped output bytes and boundary value digests; unavailable and rollback retained legacy counts, symmetric saturation retained full counts, and nested mutation retained identical direct rejection, handled provider terminal result, and durable records.
- `VBP-EXP-004` decision: `FROZEN_TARGET_NOT_CREDIBLE_FROM_VALIDATION_BOUNDARY_DESIGN`. Thirty randomized isolated children completed without timeout or equivalence/count mismatch. The selected safe edge improved median elapsed time by 13.31%; all 453 classified candidate calls are only 44.37% of the 1,021 normal legacy validation calls. Call fraction is not a latency ceiling, but current evidence does not establish a credible 75% path.
- Performance limitation: the reference removed 188 content validations (`1,021` to `833`) and one production-shaped sample improved from `1.300430431s` to `1.036960119s` (about `20.26%`). This is feasibility evidence only and does not make the frozen 75% objective credible by itself.
- External decision 2026-08-17: preserve the frozen 75% target and resume the separate linked production-performance debugging operation to identify broader warmed-path bottlenecks. This design remains blocked pending that operation's causal result; it may not absorb the broader debugging scope or claim M3.1 closure.

## Next Action

Resume `docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16/debug.plan.md` and return its revision-bound causal result before deciding whether this validation-boundary design remains part of a combined M3.1 solution.

## VBP-EXP-001 boundary census (2026-08-17)

- Decision: `PASS_FOR_BOUNDED_EDGE_SELECTION`; no repository-wide optimization is authorized.
- Evidence: `docs/work/semantic-ingestion-validation-boundary-performance-2026-08-17/evidence/vbp-exp-001-boundary-census-v1.json` SHA-256 `4a30f02bdfe00eee0327625410e02f9dcccf09a5f640b6964c131418393cfd6a`; probe SHA-256 `a723be090f6098d36aca63f67495dd449e1ee79dc365d4e17517c4abee9fa480`.
- Runtime: 1,303 content validations across 148 origins; 470 persistence/transaction, 192 provider, and 188 reload/recovery calls remain mandatory; 453 calls are candidate internal composition.
- Static: 1,163 relevant callsites; 111 decode, 42 construct, 182 persistence/transaction, 149 reload/recovery, 38 provider, 187 copy/unknown, 203 codec/repeat, 52 candidate internal/dump-revalidate, and 199 unknown. Only one callsite passes Pydantic context. Unknown origins remain ineligible.
- Selected edge: `TextPreparationService.prepare` in `core/semantic_ingestion/source_preparation.py` triggers 188 nested validations across 10 types from one dump/revalidate boundary.
- Trust caveat: `TextPreparationService` accepts an injectable producer callable. Skipping validation based on return type alone is prohibited; the experiment must distinguish private built-in producer authority from arbitrary producer output and preserve field-level substitution checks.
- Evidence boundary: classifications are experiment-selection heuristics, not implementation authority. Mandatory and unknown categories retain the complete legacy path.

## VBP-EXP-002 preparation capability (2026-08-17)

- Decision: `REFERENCE_EDGE_SECURITY_AND_EQUIVALENCE_PASS`; this authorizes continued design experimentation only, not production implementation or M3.1 closure.
- Evidence: `docs/work/semantic-ingestion-validation-boundary-performance-2026-08-17/evidence/vbp-exp-002-preparation-capability-v1.json` SHA-256 `8faa480e20d3d5e56ad3ce672078284963a3eae543cc48f1182462f42a5c9896`; reference probe SHA-256 `7db331b92bd14e0cef3dcaf07333c1105c48f009e9d867722d4063b2f824d6cd`.
- Thin-fixture boundary: the scenario fixture supplies deterministic ingress and composition; actual production `sync_event`, semantic-ingestion preparation, field-substitution checks, canonical contracts, memory-plane persistence, and output serialization execute. The private producer proxy and `PreparedSource.model_validate` interception exist only in the reference probe and are not production evidence.
- Equivalence: enabled and legacy runs emitted identical result-plus-record bytes, SHA-256 `ae485a5f913853b4e99c138713621bd5713cc4313a339280e154d751527485ef`. Saturated reference and saturated legacy paths also emitted identical bytes and each executed 1,303 content validations.
- Cost discrimination: the enabled reference executed 833 content validations versus 1,021 in the same-mode legacy cell, removing the selected edge's 188 nested validations. Single-sample elapsed time was `1.036960119s` versus `1.300430431s`; timing is diagnostic, not certification.
- Security observations: injected forged and `model_construct` producer outputs were rejected. A copied proxy and a call outside operation context received no authority and took ordinary validation. Capacity exhaustion took ordinary validation with exact output equivalence.
- Evidence gap closed by `VBP-EXP-002B` for this selected edge. This remains reference-only feasibility and does not generalize authority to another boundary or certify performance.

## VBP-EXP-002B authority-family attacks (2026-08-17)

- Decision: `FAMILY_ATTACKS_PASS` for the selected preparation edge only; production implementation and M3.1 certification remain unauthorized.
- Evidence: `docs/work/semantic-ingestion-validation-boundary-performance-2026-08-17/evidence/vbp-exp-002b-authority-families-v1.json` SHA-256 `5754a49cbd5110ba21acd8945e24e64cb7b5a46a67a86ade90aa827a96cfff19`; probe SHA-256 `173bca8b2d2edcb0998247a9f6a982d7b441312e1a33ef28521d401056878054`.
- Passed families: nested mutation rejection; sibling and `PreparedSource` subclass full validation; serialized-copy authority loss; one-use replay rejection; wrong operation, owner, and purpose; later invocation; exception and cancellation teardown; 16 concurrent operation-local consumptions; exact 64-reservation capacity; first-above fallback; and persistence/reload authority absence.
- Production callsite trace: registered authority was consumed only by `TextPreparationService.prepare`. `publish_bootstrap_prepared_source_if_absent`, `encode_semantic_contract`, `_bootstrap_prepare_and_handoff`, `decode_semantic_contract`, `publish_prepared_source`, and repository `publish` observed ordinary values and retained full validation.
- Output identity: the production-shaped result-plus-record output retained SHA-256 `ae485a5f913853b4e99c138713621bd5713cc4313a339280e154d751527485ef`, matching `VBP-EXP-002`.
- Evidence boundary: the probe uses the actual production composition and owners but reference-only interception and introspection. It proves feasibility and attack behavior for one edge, not an implementation, generalized architecture, CI gate, operational result, or M3.1 closure.

## VBP-EXP-003 behavioral equivalence (2026-08-17)

- Decision: `BEHAVIORAL_EQUIVALENCE_PASS`; this is locally verified reference evidence, not an independent implementation, production implementation, CI gate, or M3.1 certification.
- Evidence: `docs/work/semantic-ingestion-validation-boundary-performance-2026-08-17/evidence/vbp-exp-003-behavioral-equivalence-v1.json` SHA-256 `294aa5e4e6e17b8192a57297059d4d9457213bbb8899bdc75f741ae3a9b9db38`; probe SHA-256 `65387b4989b89518bb8f1649031ea11a5710fb7c1c217ee7b07c4c6df48c2cb0`.
- Success equivalence: legacy, enabled, unavailable, saturated legacy, saturated enabled, and true rollback emitted output SHA-256 `ae485a5f913853b4e99c138713621bd5713cc4313a339280e154d751527485ef`; every output independently decoded and re-encoded to identical bytes.
- Boundary equivalence: `prepare`, bootstrap publication, canonical encode, handoff, canonical decode, semantic publication, and repository publication each emitted the same typed `PreparedSource` snapshot digest `14096128aaedcc613063dd0a46ca865c6426748ecc8055280d368bf56d1d4217` across observed cells. Snapshot multiplicity is checked separately because saturation intentionally repeats complete validation.
- Validation accounting: legacy, unavailable, and rollback each executed 1,021 content validations; saturated legacy and saturated enabled each executed 1,303; enabled executed 833 and removed only the selected edge's 188 validations.
- Failure equivalence: both modes directly rejected nested semantic-context substitution with the same Pydantic `ValidationError` and message, then produced the same handled provider terminal bytes SHA-256 `1c8f44316843cf57708f166891f99009104b453bc07cd8f4794560a4ae4f8482` and durable-record bytes SHA-256 `1476bd746779820f8be50e29dd4df36ad35228f0865da24092c55fdbbcea6554`.
- Timing boundary: single-cell elapsed values are diagnostic only. Repeated randomized isolated measurement belongs to `VBP-EXP-004`; no latency or target claim is made here.

## VBP-EXP-004 performance discrimination (2026-08-17)

- Decision: `FROZEN_TARGET_NOT_CREDIBLE_FROM_VALIDATION_BOUNDARY_DESIGN`; the safe selected edge remains implementable in principle, but this design cannot be approved as M3.1 closure without an external target/scope decision.
- Evidence: `docs/work/semantic-ingestion-validation-boundary-performance-2026-08-17/evidence/vbp-exp-004-performance-discrimination-v1.json` SHA-256 `fde5263d93c2c7f8c65141b72e772818d6dbc3a109c5eb55234a4146f0ecc24a`; manifest-backed probe SHA-256 `48d7a6cc14009f26066197255fe9a82bdf7cb02c0a997b8e73b81ebdc539f4ad`.
- Isolation: five samples per mode, 30 fresh child processes, fixed randomized order seed `20260817`, 120-second per-child kill boundary, and production setup excluded from each measured interval. All children completed and emitted output SHA-256 `ae485a5f913853b4e99c138713621bd5713cc4313a339280e154d751527485ef`.
- Validation accounting: every enabled run executed 833 content validations; legacy, unavailable, and rollback executed 1,021; saturated legacy and saturated enabled executed 1,303. The selected edge removes 18.41% of normal legacy validation calls.
- Timing result: legacy median `1.191564219s`; enabled median `1.032980366s`; median reduction `13.3089%`. Enabled samples were noisy (`1.002792669s` to `4.148329432s`), so these measurements are diagnostic and do not certify a stable latency percentile.
- Credibility result: all 453 census-classified candidate calls represent 44.3683% of the 1,021 normal legacy validation calls. This ratio does not prove a wall-time upper bound, but neither the repeated selected-edge result nor the remaining call inventory demonstrates that validation-boundary work owns enough elapsed time to reach 75%.
- Evidence boundary: this rejects the current validation-boundary design as a credible M3.1 route. It does not prove 75% impossible through a different production optimization, revise the target, authorize broader profiling, or certify production performance.
