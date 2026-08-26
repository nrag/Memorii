# Codec-Owned Canonical Attestation Design

- Work ID: semantic-ingestion-codec-owned-attestation-2026-08-16
- Work type: design
- Status: abandoned
- Coordinator: Codex
- Created: 2026-08-16
- Last updated: 2026-08-16
- Parent WorkPlan: docs/work/semantic-ingestion-canonical-evidence-performance-2026-08-15/implementation.plan.md
- Related WorkPlans: docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16/debug.plan.md; docs/work/semantic-ingestion-canonical-evidence-performance-2026-08-15/design.plan.md
- Canonical inputs: docs/design/semantic_ingestion_canonical_evidence_performance.md; docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16/evidence/safe-byte-reuse-feasibility-v1.json; candidate lock `24da95523b9a050266034cd6f3b923d52a4d8cc97cf83d32d83c1285bb2d99c3`
- Expected outputs: docs/design/semantic_ingestion_codec_owned_attestations.md; executable feasibility artifacts; requirement/evidence and attack matrices; frozen design candidate; independent design review decision

## Objective

Design a codec- and semantic-validator-owned mechanism that produces reusable canonical digest preimages during the complete trusted validation traversal, without allowing callers, persisted data, object identity, mutable values, or a second codec to authorize reuse. The design succeeds only if bounded experiments show that the mechanism preserves exact existing bytes, errors, and durable effects and has enough measured production-path impact to make the M3.1 performance objective feasible.

## Problem And Baseline

The implemented operation-local arena safely reuses complete semantic contract encodes, but the same-mode feasibility comparison improved one production `ProviderMemoryService.sync_event` from `2.637856s` to `2.483143s`, only `5.87%` versus the required `75%`. The candidate still performs 1,523 `contract_digest` calls with 53 unique outputs and 1,470 redundant calls. Of the profiled candidate calls, 1,021 originate in `_ContentAddressedContract.validate_content_digest`.

The current canonical CTV owner, `memorii.core.memory_evolution.ingestion_contracts.encode_typed_value`, emits only whole-value bytes. It exposes no trusted subtree bytes or semantic-validator attestation. The semantic contract owner knows concrete model type, digest domain, digest-excluded fields, profile, codec, and validation context, but currently reconstructs digest bodies repeatedly.

## Completion Contract

This design operation is complete only when:

- all requirements have stable acceptance criteria and an evidence owner;
- canonical ownership between generic CTV encoding and semantic content-addressed validation is explicit;
- the attestation grammar, issuance, consumption, lifecycle, capacity, concurrency, retry, reload, failure, and teardown behavior are closed;
- caller digests, object identity, mutation, model construction/copy, wrong type/profile/codec/domain/nonce, path substitution, duplicate subtree, replay, persistence, and cross-operation attacks are covered by executable mutations;
- a bounded reference experiment proves byte-for-byte equality with the existing codec and measures projected production impact;
- at least one serious alternative is evaluated and rejected or selected with evidence;
- the requirement/evidence, identity, changed-surface, authority-chain, and attack ledgers are complete;
- one frozen candidate receives a full independent `spec_auditor`, `correctness_reviewer`, and `test_reviewer` review, with every finding reconciled under the repository classification contract;
- no unresolved validated design gap remains and implementation requires no hidden semantic decision.

## Scope

Included:

- runtime-only canonical preimage or subtree attestation ownership;
- exact integration boundary between semantic canonical traversal, CTV encoding, Pydantic validation context, and the operation-local arena;
- capacity, lifecycle, concurrency, retry, reload, and failure behavior;
- compatibility with current canonical bytes, digests, errors, persistence, and public APIs;
- deterministic feasibility and adversarial evidence;
- the M3.1 measurement boundary and evidence maturity.

Excluded:

- production implementation or test modification during this design operation;
- changes to canonical CTV bytes, digest domains, public schemas, persisted schemas, or durable records;
- caller-visible attestation APIs;
- cross-operation or process-persistent caches;
- changes to provenance, lifecycle, transaction, persistence, recovery, or authorization semantics;
- production capture supervisor and unrelated cold-start distribution scanning.

Explicitly deferred:

- implementation, rollout, and M3.1 certification until this design is independently approved;
- any performance-threshold revision, which requires an explicit external decision rather than design inference.

## Constraints And Invariants

- The generic CTV encoder remains the sole authority for canonical CTV bytes.
- The semantic contract owner remains the sole authority for concrete contract type, digest domain, digest-excluded fields, and typed validation.
- An attestation is runtime-only, private, non-serializable, non-deserializable, non-public, and non-persisted.
- A caller-provided digest, byte string, object identity, equality result, or model instance can never issue or authorize an attestation.
- Missing, malformed, stale, copied, wrong-nonce, wrong-owner, capacity-rejected, or failed attestations execute the complete legacy path.
- Persisted reload and durable recovery never restore an attestation.
- Existing canonical bytes, digests, validation errors, persistence bytes, durable effects, transaction behavior, and public behavior remain byte-for-byte and behavior-for-behavior identical.
- No second normalizer, serializer, structural fingerprint, or shadow contract grammar is permitted.
- The existing arena limits and process reservation remain upper bounds unless a reviewed design explicitly proves a stricter bound.
- Diagnostic, deterministic, live latency, and M3.1 certification evidence remain distinct.

## Initial Requirements Ledger

| ID | Requirement | Acceptance criterion | Source | State |
| --- | --- | --- | --- | --- |
| COA-001 | Canonical ownership | Every reusable byte sequence is emitted by the existing CTV encoder from the same normalized value that the legacy path consumes. | Repository invariants; NO-GO evidence | specified |
| COA-002 | Semantic authority | Concrete type, digest domain, excluded fields, profile, codec, and validation purpose are supplied only by the semantic contract owner. | Current contracts architecture | specified |
| COA-003 | Unforgeable issuance | Only a successful complete typed validation may issue an attestation; callers and decoded/persisted data cannot construct one. | Security boundary | specified |
| COA-004 | Exact consumption | Consumption requires exact operation nonce, owner capability, type, profile, codec, domain, canonical bytes, and semantic validation purpose. | Existing arena contract | specified |
| COA-005 | Failure closure | Invalid, partial, mutated, copied, constructed, reloaded, stale, saturated, or failed values run the complete legacy path and cannot populate reusable success. | Existing performance design | specified |
| COA-006 | Behavioral identity | Accepted bytes, digests, errors, persisted artifacts, terminal receipts, and durable effects are identical with attestations enabled or unavailable. | Memorii invariants | specified |
| COA-007 | Lifecycle isolation | Success, error, cancellation, retry exhaustion, concurrent invocation, and later invocation cannot leak attestations; durable recovery synthesizes none. | Existing arena lifecycle | specified |
| COA-008 | Bounded resources | Attestation entries and charged bytes obey deterministic per-entry, per-operation, and process-wide limits with no eviction or overwrite. | Frozen capacity contract | specified |
| COA-009 | Performance feasibility | A source-bound experiment isolates attestation benefit and demonstrates a credible path to the frozen 75% reduction before implementation approval. | M3.1 contract | specified |
| COA-010 | Evidence separation | Reference experiments and same-revision fallback comparisons cannot certify M3.1; certification remains revision-bound and independently reviewed. | Evidence contract | specified |

## Identity And Coordinate Hygiene

| Identity | Class | Durability | Owner |
| --- | --- | --- | --- |
| `COA-*`, experiment IDs, review IDs | planning/evidence coordinate | WorkPlan and evidence only | design operation |
| canonical contract type | behavioral runtime identity | existing runtime contract | semantic contract owner |
| canonical profile and codec revision | behavioral protocol identity | existing runtime binding | canonical codec owner |
| digest domain and excluded-field set | behavioral validation identity | existing runtime contract | semantic contract owner |
| operation nonce and private issuer capability | ephemeral security identity | runtime-only | invocation/attestation owner |
| canonical bytes and digest | behavioral content identity | existing persisted/runtime surfaces | CTV and semantic contract owners |
| proposed attestation type/name | unresolved behavioral code identity | runtime-only | design decision pending experiment |

Planning coordinates must not appear in runtime types, serialized fields, persisted values, event names, diagnostics consumed as product behavior, or public APIs.

## Authority Chain

Current chain:

`typed semantic value -> canonical_contract_value -> encode_typed_value -> canonical bytes -> domain-separated SHA-256 -> typed digest validator -> downstream provenance/lifecycle/transaction/persistence`

Candidate chain to test:

`typed semantic value + private validation context -> semantic owner declares exact digest body/type/domain -> existing encode_typed_value emits exact preimage bytes -> complete typed validation succeeds -> private operation-bound attestation issued -> repeated validator consumes exact attested preimage -> unchanged downstream provenance/lifecycle/transaction/persistence`

No attestation may enter the chain before canonical byte production and complete typed validation.

## Alternatives To Evaluate

- `A`: codec observer emits normalized-node byte attestations. Risk: generic CTV nodes do not know semantic digest-excluded fields or validation purpose.
- `B`: semantic traversal requests exact digest-body bytes from the existing CTV encoder and issues private attestations after successful validation. Current recommendation for experiment because ownership remains split correctly.
- `C`: immutable validated wrapper carries whole-contract bytes only. Existing arena approximates this and measured insufficient coverage.
- `D`: digest-, object-identity-, equality-, or secondary-fingerprint-authorized cache. Prohibited; cannot enter feasibility testing.

## Feasibility Experiments

### COA-EXP-001: Exact Preimage Inventory

Instrument a reference-only semantic traversal to record, for every `_ContentAddressedContract`, concrete type, domain, excluded-field set, canonical digest-body bytes, occurrence count, byte size, and legacy digest. The experiment passes only if independently recomputed legacy bytes and digests match every recorded identity and no caller digest participates in identity construction.

### COA-EXP-002: Trusted Issuance Prototype

Build a non-production reference prototype of alternative `B`. The semantic owner supplies the exact digest body to the existing encoder, completes legacy validation, then issues an opaque operation-bound result. A repeated validator may consume it only through a private capability and exact context. The experiment must reject every attack family before measuring performance.

### COA-EXP-003: Discriminating Performance Run

Run fresh isolated same-mode cells for legacy, reference attestation, wrong-context fallback, and saturation fallback. Record full-digest counts and wall time separately. `GO` requires byte/error/durable-output equality, all attacks rejected, and a measured credible path to 75%; otherwise the design stops `NO-GO` or requests an external threshold decision.

## Attack Matrix

| Family | Required mutations | Required outcome |
| --- | --- | --- |
| Issuer forgery | caller bytes, caller digest, deserialized token, copied token, arbitrary object | complete legacy validation; no admission |
| Content substitution | scalar, nested field, excluded field, collection order, duplicate subtree | miss or reject exactly as legacy |
| Contract substitution | sibling type, subclass, `model_copy`, `model_construct`, wrong schema | miss or reject exactly as legacy |
| Context substitution | wrong nonce, capability, profile, codec, domain, purpose, operation | complete legacy validation; no shared value |
| Lifecycle | success, exception, cancellation, retry exhaustion, later call, concurrent call | teardown and isolation |
| Persistence/recovery | serialize, reload, replay, durable recovery | no restored attestation; full validation |
| Capacity | exact limit and first value above entry/count/operation/process limits | deterministic fallback without eviction |
| Evidence | mixed revision, profiled/unprofiled comparison, same-revision fallback certification | reject certification claim |

## Evidence Maturity

- Existing arena: implemented and locally verified for its targeted tests; not independently reviewed or M3.1-certified.
- Codec-owned attestation: specified at requirement level only.
- Feasibility experiments: not run.
- Canonical design: not drafted.
- Independent review: not started.

## Decisions And Findings

- Confirmed finding: `Not applicable / blocks_approval / architecture and verification`. The approved implementation design lacks a codec-owned semantic preimage attestation boundary, and the current arena cannot meet the frozen performance target safely.
- Decision: production optimization remains paused. No shortcut based on digest, object identity, shallow immutability, equality, or a second fingerprint is eligible for implementation.

## Changed-Surface Ledger

Design operation changes may include only:

- `docs/work/semantic-ingestion-codec-owned-attestation-2026-08-16/design.plan.md`
- `docs/design/semantic_ingestion_codec_owned_attestations.md`
- reference-only feasibility artifacts under the design WorkPlan directory
- review artifacts under `docs/reviews/`
- links/status in the parent implementation WorkPlan

Production code, production tests, persisted schemas, public APIs, and current candidate lock are unchanged until a later approved implementation operation.

## Next Action

Handoff complete to `docs/work/semantic-ingestion-validation-boundary-performance-2026-08-17/design.plan.md`; no further work is authorized in this abandoned opaque-attestation operation.

## External decision and handoff (2026-08-17)

- The user selected the recommended broader validation-boundary design rather than revising M3.1.
- This operation is abandoned because its bounded opaque-handle architecture is infeasible, not because its security requirements were relaxed.
- The linked validation-boundary design owns all further requirements, experiments, attack analysis, and design decisions. Production implementation remains blocked.

## COA-EXP-001 exact-preimage inventory (2026-08-16)

- Decision: `PASS`; alternative `B` has sufficient exact coverage to enter the trusted-issuance prototype, but performance feasibility and design approval remain unproven.
- Evidence: `docs/work/semantic-ingestion-codec-owned-attestation-2026-08-16/evidence/coa-exp-001-exact-preimage-inventory-v1.json` SHA-256 `6f563e52903388b3f7d7e59300c768f7a509008e628b7534fedcaa33447596be`; probe SHA-256 `489689c17fde0dd0b3833b0f9b000019237a2f9a1cc5b91e5c0f882c977f3cc8`.
- Coverage: 1,303/1,898 digest calls (`68.6512%`), 22 unique identities, 1,281 redundant calls, maximum repetition 214.
- Capacity: 42,773 total unique canonical bytes and 5,650-byte maximum entry, within the frozen arena item and operation limits before metadata charge.
- Exactness: every reference preimage recomputed the legacy digest; no exactness failure or digest-to-type/domain/excluded-field/bytes ambiguity occurred.
- Top type coverage: `memorii.core.semantic_ingestion.contracts.SemanticProjectionTextArtifact` 214 calls/1 identities; `memorii.core.semantic_ingestion.contracts.ProjectionTextSpan` 213 calls/5 identities; `memorii.core.semantic_ingestion.contracts.SegmentLocalTextArtifact` 199 calls/1 identities; `memorii.core.semantic_ingestion.contracts.SegmentLocalTextSpan` 197 calls/5 identities; `memorii.core.semantic_ingestion.contracts.RetainedSourceTextArtifact` 175 calls/1 identities.
- Evidence boundary: this is reference-only, same-revision feasibility. It does not prove unforgeable issuance, consumption safety, runtime improvement, independent reproduction, or M3.1.

## COA-EXP-002 trusted-issuance prototype (2026-08-16)

- Decision: `SECURITY_PROTOTYPE_PASS_INTEGRATION_UNPROVEN`. The opaque runtime handle is viable as a security primitive; no production integration or performance claim is established.
- Evidence: `docs/work/semantic-ingestion-codec-owned-attestation-2026-08-16/evidence/coa-exp-002-trusted-issuance-v1.json` SHA-256 `c361435f691f49204bee72a9448b4c3e55fff0245df7e92e68e1ea9b8854227c`; probe SHA-256 `bc3603ad273834ad0432007b18a9fcabc171e07f9a64c3f99436e1e8171979cf`.
- Rejected 15 attacks: caller digest, forged construction, caller bytes, copied/serialized/arbitrary handles, wrong nonce/type/profile/codec/domain/purpose, cross-issuer use, mutated-value reissuance, and replay after issuer close.
- Snapshot behavior: issuance completed the legacy typed/digest validation first; later source mutation could not alter issued bytes and the mutated source could not be reissued.
- Reference overhead only: 100000 exact handle consumptions completed in `0.408127` seconds. This is not production-path or M3.1 evidence.
- Integration blocker: nested Pydantic validators receive reconstructed raw models rather than the registered handle. Automatic matching by claimed digest, model identity, equality, or a second fingerprint remains prohibited; canonical-byte reconstruction would preserve security but not remove the dominant work.
- Evidence maturity: trusted issuance is reference-prototyped and locally attacked; explicit production propagation, nested validation semantics, capacity integration, concurrency, cancellation, retry, persistence identity, and performance remain specified or unproven.

## COA-EXP-002B propagation decision (2026-08-17)

- Decision: `NO-GO_OPAQUE_HANDLE_PROPAGATION`; status is blocked on an external scope/performance-contract decision.
- Evidence: `docs/work/semantic-ingestion-codec-owned-attestation-2026-08-16/evidence/coa-exp-002b-propagation-inventory-v1.json` SHA-256 `1185e4f58635b41198c05431ab804138c5692af8d921af74b2af2414fe965485`; probe SHA-256 `b327cffbf8385bb85e7f8327579caa423a2c0a20c8c7352c79037d3f4fa3ca55`.
- Runtime coverage: 998 validations for the five dominant types across 82 distinct origin/type/line/context coordinates; 292 execute beneath `encode_semantic_contract`, while 706 execute outside it.
- Static boundary: 400 production `model_validate` callsites exist, only 1 supplies `context`; 18 direct create/validate/construct callsites name the target types.
- Dominant origin paths: `core/memory_evolution/atomic_store.py` 511 calls/30 origins; `core/semantic_ingestion/source_preparation.py` 297 calls/23 origins; `core/provider/ingestion.py` 146 calls/10 origins; `core/memory_evolution/record_projection.py` 30 calls/5 origins; `core/memory_evolution/source_admission.py` 14 calls/14 origins.
- Architectural conclusion: a private handle can be safe when explicitly consumed, but the production graph does not carry it. Retrofitting explicit propagation across raw nested reconstruction, persistence/reload, adapters, and context-free validation is a material validation-architecture redesign, not a bounded codec-owned attestation mechanism.
- Rejected continuation: automatic digest, object-identity, equality, or secondary-fingerprint matching remains prohibited; canonical-byte matching retains security but cannot remove canonical construction cost.
- Finding classification: `Not applicable / blocks_approval / architecture and external decision`. The current operation cannot produce an implementation-ready attestation design without expanding scope or changing the performance contract.
