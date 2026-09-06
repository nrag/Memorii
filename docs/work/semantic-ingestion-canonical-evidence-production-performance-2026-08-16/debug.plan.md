# Semantic Ingestion Production Performance Debugging

- Work ID: semantic-ingestion-canonical-evidence-production-performance-2026-08-16
- Work type: debugging
- Status: active
- Coordinator: Codex
- Created: 2026-08-16
- Parent WorkPlan: docs/work/semantic-ingestion-canonical-evidence-performance-2026-08-15/implementation.plan.md
- Frozen requirements-first design lock: `24da95523b9a050266034cd6f3b923d52a4d8cc97cf83d32d83c1285bb2d99c3`

## Objective

Measure and isolate production work responsible for canonical-evidence ingestion
latency without treating test-runner duration as the product defect.

## Scope

Included: one warmed in-memory public `ProviderMemoryService.sync_event`,
production coordinator, semantic runtime, canonical contract validation, and
production persistence owners.

Excluded: pytest runtime, broad test reorganization, proof-harness execution,
arena implementation, and M3.1 certification.

The diagnostic composition uses existing scenario-owned authority only to reach
the real production call path. It is causal profiling evidence, not final
production-authority or benchmark certification.

## Reproducer

One turn from `scenario-first-v1.json` invokes public `sync_event` once after
imports and service construction. Profiling is enabled only around that call.
The operation identity is
`scenario-event-84e8a0327f5b941e0eadbb8bb4fe8cf6`.

## Competing Hypotheses

- H1, confirmed contributor but insufficient as the sole M3.1 cause: nested
  content-addressed validation repeatedly recomputes canonical bytes and
  digests for identical immutable values during one operation. A safe
  representative edge removes 188 validations but improves repeated isolated
  median latency by only 13.31 percent.
- H2, confirmed but separate: cold bootstrap-profile construction repeatedly
  scans installed package distributions.
- H3, weakened: persistence I/O is the dominant warmed-operation cost. The
  in-memory reproducer still spends most cumulative time in canonical encoding,
  digest validation, and typed model validation.
- H4, strengthened: cumulative profiler attribution overstates avoidable validation
  cost because inclusive canonical/validation frames overlap substantial
  semantic-pipeline construction and traversal work that remains after reuse.
- H5, confirmed as a distributed residual: multiple non-validation and still-mixed semantic preparation,
  handoff, execution, or persistence-composition stages dominate the remaining
  warmed latency and can be isolated without weakening trust boundaries.
- H6, active noise control: process scheduling or environment variance explains
  outliers but not the stable gap between the 13.31 percent median improvement
  and the frozen 75 percent objective.
- H7, active: the common persistence-composition kernel, rather than memory I/O,
  dominates bootstrap publication, atomic writer handoff, and semantic
  persistence through repeated typed reconstruction, canonical encoding,
  record construction, and authority checks.
- H8, confirmed for the exercised pre-pipeline family: the bootstrap path performs duplicate Step-2 lifecycle work. It
  prepares and publishes in `_bootstrap_prepare_and_handoff`, then
  `_run_semantic_ingestion` prepares and publishes the same source again before
  the pipeline reloads it. Replacing only the second cycle with a fully
  validated persisted reload may remove producer and publication composition
  without weakening bootstrap publication or pipeline reload boundaries.
- H9, disproved: exact-object-reference digest reuse can capture the dominant
  repeated canonical-evidence family. The full V3 path reconstructs
  equal-content contracts as distinct model objects; a bounded exact-reference
  counterfactual avoids only 55 of 42,955 digest computations and increases
  elapsed time.

## Evidence

The warmed event completed in 10.204 seconds under cProfile with 4,688,592
function calls. The call tree records:

- `encode_typed_value`: 2,279 calls and 8.485 cumulative seconds
- `contract_digest`: 1,901 calls and 7.588 cumulative seconds
- `validate_content_digest`: 1,303 calls and 4.120 cumulative seconds
- Pydantic schema validation: 94 `model_validate` calls and 6.572 cumulative seconds
- `_bootstrap_prepare_and_handoff`: 5.257 cumulative seconds
- `_run_semantic_ingestion`: 4.114 cumulative seconds

Times are cumulative and overlap; they must not be added or reported as
independent percentages.

A separate semantics-preserving counter wrapped only `contract_digest` and
observed 1,898 calls producing 53 unique digest outputs. Of those calls, 1,845
(97.2 percent) recomputed an identity already produced in the same operation;
45 identities repeated and the most frequent identity was recomputed 215 times.

A second diagnostic measured the canonical bytes for those 53 unique outputs:
133,444 bytes total, 759-byte median, 5,708-byte nearest-rank p95, and a
59,405-byte maximum entry. This supports a proposed initial bound of 128
entries, 65,536 canonical bytes per entry, 1,048,576 charged bytes per
operation, and 67,108,864 aggregate process reservation bytes. These are
evidence-derived proposed design values, not implemented or approved limits.

The cold whole-process profile separately records eight
`_component_distribution_identity` calls spending 36.280 cumulative seconds
in `importlib.metadata.packages_distributions`. This is a distinct production
composition inefficiency and is not the arena root cause.

### PBD-EXP-001 exclusive owner attribution (2026-08-17)

- Decision: `RESIDUAL_STAGE_LOCALIZED`, with the important qualification that residual cost is distributed and no measured owner approaches 75 percent alone.
- Evidence: `docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16/evidence/pbd-exp-001-exclusive-attribution-v1.json` SHA-256 `bbc0dcdbf4ca21fe67581af889a30a4a7a4aa24f4fd92be4daa9fecc7d0d19da`; probe SHA-256 `270def46a32206d0ace23074c599c30cf998344dadb092effc2335552d0ac7c0`.
- Method: three isolated samples per mode, fixed randomized order, 120-second child timeout, setup excluded, identical output SHA-256 `ae485a5f913853b4e99c138713621bd5713cc4313a339280e154d751527485ef`, and exact 1,021 legacy versus 833 safe-reference validation counts.
- Safe-reference median exclusive owner times: bootstrap handoff `0.245750398s`, semantic persistence `0.178186073s`, bootstrap persistence `0.174530786s`, preparation `0.171322942s`, provider orchestration `0.111310486s`, preparation publication `0.064569593s`, semantic coordinator `0.039287730s`, and memory write `0.007825724s`.
- Discrimination: preparation is the only owner with a material median reduction (`0.128113614s`). Bootstrap handoff self-time is the largest residual but changes by `-0.019180837s`, meaning the safe preparation authority does not remove its work. Persistence owner medians likewise remain within noisy small deltas.
- Instrumentation boundary: Pydantic's schema-compiled validator callable did not route through the post-construction Python method wrapper, so validator cost remains charged to the production owner executing it. The evidence is exclusive owner attribution, not a standalone validation-self-time decomposition.
- Causal implication: the prior cumulative profile correctly found expensive validation activity but overstated how much one safe reuse boundary could remove. Remaining warmed latency is spread across bootstrap handoff, two persistence compositions, preparation, and provider orchestration.

### PBD-EXP-002 bootstrap handoff decomposition (2026-08-17)

- Decision: `BOOTSTRAP_HANDOFF_CHILDREN_AND_ENCODING_DISCRIMINATED`; bootstrap handoff is material but internally distributed, and repeated handoff encoding is not its dominant cause.
- Evidence: `docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16/evidence/pbd-exp-002-bootstrap-handoff-v1.json` SHA-256 `a11435e8cc305542179c2b6e4aee423245202070f2af04235f18b85521bae582`; probe SHA-256 `66b945f9d5c92135949252f84d0f373d35dab6943fe30ee6b78fa9266f649a0f`.
- Method: three isolated samples per safe-reference and captured-encode mode, fixed randomized order, 120-second child timeout, exact output SHA-256 `ae485a5f913853b4e99c138713621bd5713cc4313a339280e154d751527485ef`, exact 833 validation calls, and exactly one capture plus one reuse in every counterfactual child.
- Safe-reference median handoff children: bootstrap publication `0.173415850s`, atomic writer handoff `0.130238466s`, preparation `0.090401176s`, published-value validation `0.060175053s`, observation reload `0.027521086s`, handoff canonical encoding `0.017516152s`, writer admission read `0.004227301s`, and release assertions `0.001580120s`.
- Counterfactual: replacing the later handoff encode with exact bytes captured from bootstrap publication reduced total handoff median from `0.519184419s` to `0.484803108s`, or `6.6222%`. This is a non-implementable causal upper bound and does not confer reusable authority.
- Hypothesis result: handoff encoding is disproved as a dominant residual. Bootstrap publication and atomic writer handoff lead the child costs, while preparation and mandatory published-value validation remain material.

### PBD-EXP-003 persistence composition (2026-08-17)

- Decision: `PERSISTENCE_COMPOSITION_KERNEL_DISCRIMINATED`; persistence owner cost is CPU reconstruction/composition, not memory writes, and prepared-wire encoding alone remains insufficient.
- Evidence: `docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16/evidence/pbd-exp-003-persistence-composition-v1.json` SHA-256 `da2c032852a0b3a12e09e2fa40c3519dcbdd5c6a38d0ec755e5761869220e128`; probe SHA-256 `4c6bd318e96402f6fe61642ec131131f8072522ee757fd277af530dd15e1e541`.
- Method: three isolated samples per safe-reference and captured-wire mode, fixed randomized order, 120-second timeout, exact output SHA-256 `ae485a5f913853b4e99c138713621bd5713cc4313a339280e154d751527485ef`, exact 833 validation calls, one capture, and two later reuses per counterfactual child.
- Safe-reference combined parent median: `0.488929825s` across bootstrap publication, atomic writer handoff, and semantic persistence. Shared child medians are typed reconstruction `0.313276974s`, canonical encoding `0.069756655s`, prepared-record reload `0.064439659s`, writer `require_current` `0.007412270s`, conditional writes `0.004129921s`, writer authorization `0.003445994s`, bootstrap access checks `0.003061159s`, writer current `0.002524931s`, record reads `0.001738818s`, and all remaining measured kernels below one millisecond each.
- Causal shares: typed reconstruction is approximately 64.1 percent of the combined owners; canonical encoding is approximately 14.3 percent; prepared-record reload is approximately 13.2 percent; conditional writes are below one percent.
- Counterfactual: retaining every full persistence validation while reusing exact prepared wire bytes in later owners reduced combined median from `0.488929825s` to `0.454018711s`, or `7.1403%`. Canonical serialization is material but not the primary cause.
- Hypothesis result: H3 is further weakened; H7 is confirmed. The next structural candidate is duplicated Step-2 preparation/publication across bootstrap handoff and semantic execution, not store I/O.

### PBD-EXP-004 duplicate Step-2 lifecycle (2026-08-17)

- Decision: `DUPLICATE_STEP2_PRE_PIPELINE_CONFIRMED`; the ordinary exercised path repeats producer and publication work after bootstrap publication, but the fixture terminates before `SemanticIngestionPipeline.run`.
- Evidence: `docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16/evidence/pbd-exp-004-duplicate-step2-v1.json` SHA-256 `2b214a948cf021358391f5babf56aa74c3c8d633bf76e007d6a7861b363be73b`; probe SHA-256 `76782c72f4d7a3279efa5b6009b4577fd4efdd8c49694bbba067f4095f22f7cb`.
- Method: three isolated samples each for safe reference, persisted reload, and rollback; fixed randomized order; 120-second timeout; exact output SHA-256 `ae485a5f913853b4e99c138713621bd5713cc4313a339280e154d751527485ef`; one bootstrap publication in every cell; no private authority outside `prepare`.
- Counterfactual ownership: the persisted repository performs full reload validation, then a fresh production `TextPreparationService.prepare` performs full typed validation and existing source/policy substitution checks. Only the second producer invocation and semantic publication attempt are replaced.
- Result: safe-reference median `0.940835499s`; persisted-reload median `0.807339595s`; reduction `14.1891%`. Content-validation calls fall from 833 to 777; rollback restores 833. The persisted-reload distribution is tight (`0.798164136s` to `0.820485752s`).
- Lifecycle accounting: baseline and rollback invoke the producer twice and semantic publication once; persisted reload invokes the producer once, semantic publication zero times, and the persisted reload once. Bootstrap publication remains once.
- Coverage boundary: this scenario reaches the handled pre-pipeline terminal path and does not execute `SemanticIngestionPipeline.run` or its repository reload. No pipeline-family or end-to-end M3.1 claim follows.

### PBD-EXP-006 exact-reference digest counterfactual (2026-08-17)

- Decision: `EXACT_REFERENCE_REUSE_DISPROVED`; this mechanism preserves the
  exercised promise projection but cannot reach the equal-content,
  distinct-instance repetition responsible for the measured amplification.
- Evidence:
  `docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16/evidence/pbd-exp-006-reference-digest-counterfactual-v1.json`.
  The reference harness changed no production code or tests and does not
  certify M3.1.
- Method: two isolated unchanged baseline children first established the
  deterministic promise projection and the nondeterminism of complete
  cross-process output hashes. A third isolated child enabled only the bounded
  reference counterfactual. The projection retained blocked reasons, graph and
  normalization outcomes, authority-clause diagnostics, production-path call
  counts, validation counts and validation-family counts; it excluded elapsed
  time, process-local object identities, profiler rows and cache counters.
- Coherence boundary: reuse required the same strongly held frozen model
  reference, concrete type, digest domain, declared digest and recursively
  unchanged immutable reference shape. Mutable values, changed shapes,
  equal-but-distinct objects, non-admitted values and capacity exhaustion fell
  back to the complete production digest calculation. All 42,955 content
  validators still executed.
- Capacity proof: the operation-local counterfactual admitted exactly 128
  entries, charged 80,943 bytes against a 1,048,576-byte limit, performed no
  eviction, and recorded 42,772 capacity fallbacks. Coherence rejections were
  zero.
- Performance result: unchanged baselines completed in 80.7534 and 78.3089
  seconds, with a 79.5311-second median. The counterfactual completed in
  88.6077 seconds, a negative 11.4126-percent change. It produced only 55 hits
  and reduced digest computations from 42,955 to 42,900.
- Assertion correction: complete output SHA-256 is not a valid cross-process
  assertion for this fixture because both unchanged baseline children emitted
  different hashes. The explicit promise projection was identical across both
  controls and the counterfactual, with SHA-256
  `dc5dbe7332048614e0801f73312860d246ea0e0daa67573450d131a9c7a5825f`.
- Causal implication: the earlier measurement of 42,717 repeated validations
  across 238 `(concrete type, declared content digest)` identities describes
  content repetition, not object-reference repetition. Any viable optimization
  must prevent or safely bridge reconstruction at an authenticated production
  boundary; a digest-keyed shortcut remains forbidden.

### PBD-EXP-007 seven-family reconstruction trace (2026-08-17)

- Decision: `RECONSTRUCTION_BOUNDARIES_LOCALIZED`; the seven dominant
  content-addressed families are not repeatedly validated primarily because
  their explicit constructors are called again. They are overwhelmingly
  rebuilt as equal-content, distinct model instances at semantic envelope,
  decode/reload and graph boundaries.
- Evidence:
  `docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16/evidence/pbd-exp-007-seven-family-reconstruction-trace-v1.json`.
  The bounded probe changed no production code or tests and does not certify
  M3.1. Instrumented elapsed time was 223.0494 seconds and is not a performance
  comparison.
- Method: one isolated full V3 operation assigned generation-safe weak-reference
  tokens to target model instances, grouped them by concrete family and
  successfully verified declared digest, and aggregated bounded production
  stacks. Weak references avoided retaining production object graphs and
  distinguished object-ID reuse.
- Aggregate result: 31,851 validations covered 31,720 distinct object instances
  but only 24 family-local content identities. Equal-content reconstruction
  accounted for 31,696 instances; only 131 validations reused an object instance
  already observed by the probe.
- Boundary attribution: semantic envelope revalidation accounts for 14,382
  validations (45.15 percent), semantic envelope decode for 8,601 (27.00
  percent), and graph execution outside those codec frames for 6,726 (21.12
  percent). Together they account for 93.28 percent. Normalization accounts for
  1,368 (4.30 percent), Step-2 explicit construction for 525 (1.65 percent),
  bootstrap publication for 87, admission explicit construction for 18, and
  other production stacks for 144.
- Family completeness: `SemanticProjectionTextArtifact` records 5,330
  validations and 5,309 equal-content reconstructions;
  `SegmentLocalTextArtifact` 5,309 and 5,288;
  `RetainedSourceTextArtifact` 5,275 and 5,252; `ProjectionTextSpan` 5,331 and
  5,299; `SegmentLocalTextSpan` 5,309 and 5,278;
  `VerbatimTextArtifactMappingProof` 2,658 and 2,635; and
  `RetainedSourceTextSpan` 2,639 and 2,635.
- Static construction map: source admission explicitly creates all seven
  families once per admitted bundle. Step 2 and linguistic adapters explicitly
  create only new projection/local span coordinates. These legitimate new
  values are not the dominant amplification and must remain fully validated.
- Causal implication: optimizing `.create()` methods or exact-reference lookup
  cannot address the defect. The next experiment must discriminate why
  `encode_semantic_contract`, `decode_semantic_contract`, and graph-owner
  composition reconstruct nested models, and whether an authenticated owner can
  carry validated canonical evidence across one of those boundaries without a
  caller-declared-digest lookup.

### PBD-EXP-008 concrete reconstruction owners (2026-08-17)

- Decision: `CONCRETE_OWNERS_AND_MINIMIZATION_BOUNDARIES_IDENTIFIED`.
  Repeated construction is concentrated in a small set of owner transitions;
  it is not necessary to weaken writer admission or persisted-record decoding
  to remove most of the avoidable work.
- Governing trace: the concrete stack sites retained in
  `docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16/evidence/pbd-exp-007-seven-family-reconstruction-trace-v1.json`.
  The second bounded trace reproduced the exact 42,955 total validations and
  family counts; its 198.748-second instrumented duration is not performance
  evidence.
- `BootstrapV3SourceNormalizationStage.build_request` is the largest single
  stack site at 3,204 target-family validations. Its artifact member generator
  calls `encode_semantic_contract(value)` once for `canonical_payload` and a
  second time to compute `sha256(encode_semantic_contract(value))`. Computing
  bytes once and hashing those exact bytes is a determinate, coherence-safe
  construction minimization; it does not cross a trust boundary.
- `AtomicStoreSourceNormalizationRepository.publish_and_reload` performs a
  same-process `request.model_dump` plus `request_type.model_validate` before
  publication (1,320 target-family validations), then validates the committed
  member closure, decodes retained members, re-encodes decoded contracts for
  canonicality, and finally dump/rebuilds the result. The committed-member
  decode is mandatory; the same-process request/result reconstructions and
  post-decode re-encoding are candidates for authenticated evidence threading.
- `AtomicStoreSourceNormalizationRepository.validate_bootstrap_v3_reloaded_members`
  is invoked independently through
  `AtomicStore.recover_bootstrap_v3_source_normalization` by
  `reload_bootstrap_recovery_replay_v3`,
  `reload_bootstrap_semantic_reduction_authority_v3`, and
  `reload_bootstrap_graph_normalization_authority_v3`. Each path decodes the
  same generation closure. The concrete trace records 1,524 target-family
  decode validations in each of these three paths, before their additional
  canonical re-encoding checks.
- `AtomicStoreBootstrapGraphTransactionAuthorityRepositoryV3.publish_or_reload`
  dump/rebuilds a typed request before the atomic store repeats validation.
  `_bootstrap_graph_v3_authority_record` then encodes the reload for storage;
  writer admission `_is_bootstrap_graph_v3_authority_write` decodes and
  re-encodes it; and `_bootstrap_graph_v3_authority_from_record` repeats the
  decode/re-encode on reload. Writer admission and record decode remain
  mandatory; already-certified canonical bytes can remove the paired
  re-encodes without trusting record metadata.
- `AtomicStoreBootstrapGraphGroupCommitRepositoryV3.commit_or_reload`
  dump/rebuilds the request, `AtomicStore.commit_or_reload_bootstrap_graph_group_v3`
  dump/rebuilds it again, and the repository dump/rebuilds the returned reload.
  `_bootstrap_graph_v3_group_commit_primary_record` independently encodes the
  request and reload, while writer admission decodes and re-encodes both. The
  same-process reconstructions are avoidable; independent writer decode is not.
- `AtomicStoreBootstrapGraphTerminalPersistencePortV3.persist_and_reload`
  dump/rebuilds the terminal publication request before
  `AtomicStore.persist_bootstrap_graph_terminal_v3` repeats request validation.
  `_bootstrap_graph_v3_terminal_members` then encodes nested payloads for the
  durable closure. One sealed request handoff and one encode per terminal member
  can preserve the publication boundary without duplicate construction.
- Mandatory-boundary classification: persisted bytes must still undergo
  bounded typed decode, digest verification, closure/substitution checks and
  writer-admission authorization. An optimization may carry decoder-produced
  canonical bytes and typed values forward, but may not accept a
  caller-declared digest, treat an in-memory object as persisted truth, or use
  an operation-local result after its generation/fence scope ends.
- Recommended structural target: one private immutable
  generation-bound normalization reload bundle, produced only after the atomic
  store has loaded one exact generation and
  `validate_bootstrap_v3_reloaded_members` has completed. It binds namespace,
  operation fence, generation, ordered member IDs, payload digests, exact
  canonical bytes, concrete types and decoded values. Recovery replay,
  semantic-reduction authority and graph-normalization authority may derive
  their views from that bundle after checking the same bound identity. No
  process-global cache or eviction policy is involved.

### PBD-EXP-009 generation-bound normalization reload bundle (2026-08-17)

- Decision: `SHARED_GENERATION_VALIDATION_CONFIRMED_BUT_INSUFFICIENT`.
  One validated committed-generation bundle safely removes repeated full-closure
  reconstruction across recovery replay, semantic-reduction authority and
  graph-normalization authority, but the isolated gain does not approach the
  frozen M3.1 objective.
- Evidence:
  `docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16/evidence/pbd-exp-009-normalization-reload-bundle-counterfactual-v1.json`.
  The reference harness changed no production code or tests and does not
  certify M3.1.
- Method: the unchanged baseline and generation-bound bundle each ran in an
  isolated child with a 300-second timeout. Admission occurred only after the
  existing complete production committed-generation validation. Before each
  reuse, the harness re-read the recovery index and generation-member envelopes
  and required the same atomic-store owner, recovery key, namespace, generation,
  atomic request digest, result digest, ordered member IDs, kinds, declared
  payload digests, actual payload SHA-256 values and payload lengths.
- Lifecycle proof: the baseline performed three complete generation
  validations. The counterfactual performed one complete validation, one
  admission and two coherence-checked hits. It recorded zero coherence
  rejections and zero capacity fallbacks. Authority-specific member decodes,
  writer admission and persisted-byte validation remained active.
- Construction result: content-addressed validations fell from 42,955 to
  36,465, eliminating 6,490 validations or 15.11 percent of the full exercised
  path.
- Performance result: the unchanged reference completed in 82.1190 seconds and
  the generation-bound bundle in 70.9656 seconds, a 13.5819-percent reduction.
  This is one paired reference-only causal measurement, not certification.
- Promise proof: the explicit terminal, graph, normalization, authority-clause,
  production-path and installation-identity projection was equal, with SHA-256
  `af8438fcee1e0bb94e56063cf020e1511403b13e76e8306e02215590058e354f`.
- Size proof: the single operation-scoped bundle referenced 27 retained member
  payloads totaling 1,514,577 bytes against the counterfactual's 33,554,432-byte
  hard limit. A production design should charge incremental retained ownership,
  not automatically copy those bytes, and must freeze a substantially tighter
  evidence-derived bound before implementation.
- Causal implication: consolidating full-generation validation is a valid
  construction-minimization component. It must be combined with independent
  elimination of duplicate encoding and same-owner dump/rebuild validation;
  treating this 13.58-percent result as M3.1 closure would be unsupported.

### PBD-EXP-010 mandatory-validation identity floor census (2026-08-17)

- Decision: `SUB_200_IDENTITY_FLOOR_PLAUSIBLE_NOT_YET_PROVEN_SAFE`.
  The measured identity partition supports a theoretical 130-identity floor
  under complete hierarchical closure coverage, but mandatory boundary
  occurrences and in-process identity roles require one more classification
  before this can become an implementation target.
- Evidence:
  `docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16/evidence/pbd-exp-010-mandatory-validation-floor-census-v1.json`.
  The harness changed no production code or tests and does not certify M3.1.
- Method: one isolated full V3 operation classified every successfully verified
  `(concrete family, content digest)` identity by runtime codec root and stack.
  A mandatory boundary root is itself the expected root type of a persisted or
  writer-admission decode. An aggregate-coverable candidate is nested under such
  a root but is never itself observed as that root. An in-process-only candidate
  is not observed under persisted or writer-admission decode in this operation.
- Population proof: 42,955 validations contain 238 unique content identities
  and 42,717 repeats, reproducing the prior census exactly.
- Identity partition: 17 mandatory boundary-root identities account for 816
  validations; 108 aggregate-coverable candidates account for 41,745
  validations; and 113 in-process-only candidates account for 394 validations.
  Aggregate-coverable candidates therefore account for 97.18 percent of all
  content-addressed validations.
- Mandatory root families: four distinct `BootstrapAnalysisLaneResultV3`
  identities and one identity each for proposal payload, interpretation bundle,
  source alignment, normalization request, manifest, result, normalization
  core, reduction authority, graph normalization authority, graph transaction
  authority reload, group-commit request, group-commit reload and operation
  result form the 17 measured roots.
- Theoretical floor: if one authenticated closure proof safely covers all 108
  nested identities and each remaining identity is validated once, the exposed
  identity count is 130 (`17 + 113`), below 200. This is a contract-identity
  lower bound, not a runtime or boundary-occurrence guarantee.
- Remaining uncertainty: the 17 root identities produce 816 validations because
  roots cross or revisit multiple boundaries. Independent writer and persisted
  inputs may still require separate validation even when content is equal. The
  113 in-process identities also require classification as static reusable,
  necessary operation-derived, or eliminable transient before assigning a
  per-operation floor.
- Causal implication: the earlier `238–500` target remains architecturally
  plausible and a sub-200 identity count is now evidence-supported. Claiming
  fewer than 200 actual validation executions remains premature until boundary
  occurrence and in-process-role censuses close the remaining uncertainty.

### PBD-EXP-011 security-adjusted boundary-occurrence floor (2026-08-17)

- Decision: `SUB_200_SECURITY_ADJUSTED_FLOOR_SUPPORTED`.
  The measured conservative floor is 169 content-validation executions when
  writer admissions remain independent, non-writer roots consolidate only
  within one concrete trust event, every necessary operation-derived identity
  validates once, and authenticated roots cover nested identities.
- Evidence: the occurrence-level extension in
  `docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16/evidence/pbd-exp-010-mandatory-validation-floor-census-v1.json`.
  The harness changed no production code or tests and does not certify M3.1.
- Boundary occurrence result: the 17 mandatory root identities have 74 actual
  persisted/writer decode occurrences in the exercised operation. They comprise
  52 event/identity pairs and 22 repeated same-identity validations within an
  event. The remaining validations attributed to those identities occur in
  non-boundary construction or encoding contexts.
- Writer floor: graph group-commit admission performs six root validations and
  graph transaction-authority admission performs two. All eight remain
  independently required; equal bytes do not permit cross-write consolidation.
- Non-writer floor: normalization publication reload contributes seven unique
  event/identity pairs, recovery replay 12, semantic-reduction authority 12,
  graph-normalization authority 13, graph-authority record reload one and graph
  group-commit atomic reload three. Counting one validation per identity within
  each event yields 48; no trust is shared across these events in this floor.
- In-process floor: all 113 in-process-only identities are observed as necessary
  operation-derived constructions. None qualifies from this trace as
  pre-existing static reusable or reconstruction-only transient. Assigning one
  validation to each contributes 113.
- Conservative floor equation: eight independent writer occurrences plus 48
  non-writer event/identity validations plus 113 necessary operation-derived
  identities equals 169. This is below 200 without merging writer boundaries,
  eliminating unique operation-derived contracts or trusting caller-declared
  digests.
- Required assumption: the 108 nested aggregate-coverable identities can avoid
  independent content-digest recomputation only after a root closure has fully
  validated their semantic invariants and issued an exact typed canonical
  evidence proof scoped to the same event or generation. PBD-EXP-011 measures
  the target population; it does not implement or approve that proof contract.
- Performance boundary: reducing content validations to 169 does not imply a
  99.6-percent runtime improvement. Graph algorithms, persistence I/O, canonical
  parsing, semantic validators and orchestration remain. Runtime must be measured
  after each safely implemented component.

### PBD-EXP-012 authenticated hierarchical closure proof (2026-08-17)

- Decision: `HIERARCHICAL_DIGEST_COVERAGE_CONFIRMED`.
  One exact generation proof can cover nested content-digest recomputation while
  retaining later bounded decode, concrete typing, semantic validators,
  cross-member closure checks, canonical re-encoding comparisons,
  authority-specific decodes and writer admission.
- Evidence:
  `docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16/evidence/pbd-exp-012-hierarchical-closure-counterfactual-v1.json`.
  The reference harness changed no production code or tests and does not
  certify M3.1.
- Admission and scope: one proof was issued only after the existing complete
  production validation of a committed normalization generation. Before each
  covered revalidation, the harness re-read and matched the recovery index,
  atomic-store owner, recovery key, namespace, generation, atomic request
  digest, result digest, ordered member IDs, member kinds, declared payload
  digests, actual payload SHA-256 values and payload lengths.
- Lifecycle proof: one full admission validation was followed by two exact
  generation coherence checks and two proof-covered complete revalidations.
  There were zero coherence rejections and zero capacity fallbacks. The proof
  retained 27 member payload identities totaling 1,514,577 bytes against a
  one-proof 33,554,432-byte reference limit.
- Validation result: all 42,955 content-validator methods still executed, but
  full digest computations fell from 42,955 to 36,465. The proof covered exactly
  6,490 nested digest validations, matching the construction population removed
  wholesale by PBD-EXP-009.
- Performance result: the unchanged reference completed in 83.6189 seconds and
  the hierarchical proof in 75.8513 seconds, a 9.2894-percent reduction. This
  is one paired reference-only causal measurement, not certification.
- Promise proof: the terminal, graph, normalization and authority-clause
  projection was equal, with SHA-256
  `204514bc04d4ee551323db7dc1a4ab15e4da4c4cb79fce751d84dcceabd6ffdb`.
- Comparison with PBD-EXP-009: the generation bundle improves runtime by 13.58
  percent because it avoids two complete reload validations. The hierarchical
  proof improves runtime by 9.29 percent while deliberately rerunning decoders
  and every semantic validator and covering only nested digest computation.
  They demonstrate different permissible optimization layers and must not be
  reported as additive without a combined experiment.
- Architectural implication: authenticated hierarchical coverage is feasible,
  and PBD-EXP-011's sub-200 validation target has a demonstrated mechanism.
  Productionizing that mechanism changes validation authority, proof lifecycle,
  codec integration and operation/generation scope. Repository workflow therefore
  requires a separate linked build-design operation before production changes.

### PBD-EXP-013 family-complete exact-root closure proof (2026-08-17)

- Decision: `EXACT_ROOT_PROOFS_MATERIAL_BUT_90_PERCENT_TARGET_NOT_MET`.
  Extending exact-byte root proofs across loaded Memorii codec call sites removes
  more than one third of repeated digest computation and improves runtime by
  16.99 percent, but root equality is too narrow to cover equal nested contracts
  reconstructed beneath different parent roots.
- Evidence:
  `docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16/evidence/pbd-exp-013-family-complete-closure-counterfactual-v1.json`.
  The reference harness changed no production code or tests and does not
  certify M3.1.
- Security scope: a miss performed complete production validation before
  admitting exact root bytes and concrete type within one trust-event scope. A
  hit required byte-for-byte root equality. Writer scopes included the concrete
  writer-admission invocation and could not authorize another write. All
  semantic validators, decoder bounds, closure checks and writer admissions
  executed; only nested content-digest recomputation was covered.
- Capacity proof: the counterfactual admitted 90 roots and charged 10,262,837
  bytes against limits of 512 entries, 2,097,152 bytes per root and 33,554,432
  bytes total. It recorded zero capacity fallbacks, so capacity did not prevent
  target attainment.
- Hit proof: 59 of 123 encode calls and 30 of 56 decode calls reused an exact
  root proof. Four hits were writer-invocation scoped. The proof covered 15,371
  digest validations.
- Digest result: full computations fell from 42,955 to 27,584. Repeated
  computations fell from 42,717 to 27,346, a 35.9833-percent reduction. The
  required 90-percent threshold is at most 4,272 repeated computations and was
  not met.
- Performance result: the unchanged reference completed in 79.7618 seconds and
  the family-complete proof in 66.2121 seconds, a 16.9877-percent reduction.
  This is one paired causal diagnostic, not certification.
- Promise proof: the terminal, graph, normalization and authority-clause
  projection was identical, with SHA-256
  `204514bc04d4ee551323db7dc1a4ab15e4da4c4cb79fce751d84dcceabd6ffdb`.
- Causal implication: the remaining 27,346 repeated computations are not mainly
  exact-root repeats. They arise when equal nested contracts are reconstructed
  under distinct parent roots and same-owner dump/rebuild transitions. Raising
  root-proof capacity cannot solve this. Reaching 90 percent requires either
  eliminating parent reconstruction through sealed typed handoffs or issuing
  authenticated member/path evidence that can be consumed across different
  roots without a digest-only lookup.
- Architecture boundary: cross-root member evidence requires codec-produced
  canonical member spans or an equivalent exact membership proof, concrete
  type/domain/profile/codec binding, parent closure and path binding,
  operation/generation/fence scope, and fail-closed fallback. This is a material
  validation-authority design change and is outside the debugging operation.

## Root Cause

The trigger is one ordinary semantic-ingestion event. Nested Pydantic validators
validate content-addressed contracts independently at each construction,
handoff, persistence, reload, and terminal stage. Each validation recomputes
`contract_digest`, which recursively invokes `encode_typed_value`, even when
the same immutable contract identity was already successfully validated during
the current `sync_event`. No operation-scoped validated-result authority is
threaded through these stages. The duplicate work propagates through bootstrap
preparation and semantic execution and accounts for 1,845 redundant digest
computations in the reproducer. Existing correctness checks validate outputs,
not per-operation recomputation counts, so they did not detect the amplification.

This remains a confirmed contributing cause, not a complete M3.1 root cause.
`VBP-EXP-004` shows that safely removing one 188-validation family reduces
same-mode median latency by 13.31 percent, while all 453 classified candidate
validations comprise only 44.37 percent of the normal legacy validation calls.
The broader warmed-path cause remains open and must explain the residual latency
without relying on overlapping cumulative profiler times.

## Decision

The measured evidence confirms the canonical-evidence arena target for warmed
event latency. Cold package-distribution scanning remains a separate follow-up
and must not be silently folded into the arena. On 2026-08-16 the user replaced
the baseline-first gate with requirements-first post-fix evidence because the
known faulty implementation makes the original capture prohibitively
expensive. The source-bound diagnostic manifest preserves the uncached
production identities and measurements but is not an M3.1 baseline. Capacity
limits are now frozen by the canonical design; implementation and evidence
remain pending.

The earlier conclusion that canonical-evidence reuse supplied the complete
warmed-event performance route is superseded by `VBP-EXP-004`. On 2026-08-17
the user selected the recommended scope decision: preserve the 75 percent target
and resume this debugging operation for broader production bottlenecks rather
than revise M3.1 or implement the safe edge as closure. Governing evidence:
`docs/work/semantic-ingestion-validation-boundary-performance-2026-08-17/evidence/vbp-exp-004-performance-discrimination-v1.json`
SHA-256 `fde5263d93c2c7f8c65141b72e772818d6dbc3a109c5eb55234a4146f0ecc24a`.

## Next Action

Await the linked validated-canonical-closure design approval, owned by
`docs/work/semantic-ingestion-validated-canonical-closure-2026-08-17/design.plan.md`;
then resume this debugging operation for implementation after-state and family-
complete regression proof. The debugging packet remains the baseline authority.
