# Recovery/Reconcile Baseline Debugging WorkPlan

- Work ID: `semantic-ingestion-recovery-reconcile-baseline-debug-2026-08-18`
- Work type: `debugging`
- Status: `under-review`
- Coordinator: Codex sole writer
- Created: `2026-08-18`
- Last updated: `2026-08-19`
- Parent WorkPlan: `../semantic-ingestion-validated-canonical-closure-2026-08-17/implementation.plan.md`
- Related WorkPlans: `../semantic-ingestion-validated-canonical-closure-2026-08-17/milestones/recovery-reconciliation-fresh-owner-propagation.md`
- Canonical inputs: root `AGENTS.md`, `.agents/PLANS.md`,
  `.agents/skills/debug-problem/SKILL.md`,
  `docs/design/semantic_ingestion_validated_canonical_closure.md`,
  `docs/work/semantic-ingestion-validated-canonical-closure-2026-08-17/implementation-acceptance-v12.md`
- Expected outputs: causal signatures, confirmed or disproved root causes,
  minimal correction scope, and revision-bound focused regression evidence

## Objective

Deterministically isolate and, only after causal confirmation, correct the two
recovery baseline blocker families that prevent proof of fresh-owner
reconciliation:

1. Public JSONL reopen invokes
   `ProviderMemoryService._ensure_writer_admission_record` and raises
   `SemanticWriterAdmissionError: writer admission is already bound differently`.
2. No-lease `reload_bootstrap_recovery_replay_v3` returns `None`; V3 reopen
   controls/claims diverge (`preplanning` versus `terminal`, `foreign` versus
   `consumed`).

The families are independently investigated; this WorkPlan does not assume a
shared root cause.

## Completion Contract

This debugging operation completes only when each family has a documented,
discriminated causal chain or a precise external blocker; any implemented fix
has a deterministic reproducer that failed before and passes after, appropriate
sibling coverage, focused checks, and an updated authority/identity ledger.
It does not complete the parent implementation milestone. A revision-locked
debug candidate may authorize only independent closure review of these two
bounded causal families.

## Scope

Included:

- deterministic reproduction and causal isolation of the two named baseline
  failure families;
- writer-admission composition/reopen state, V3 marker/recovery/replay reload
  state, and their immediate authority chains;
- the smallest safe correction only after discriminating experiments establish
  a root cause.

Excluded:

- fresh-owner recovery feature expansion, unrelated trigger families,
  performance measurement unrelated to a focused reproducer, broad suites, CI, and final
  implementation approval;
- changing public or persisted schemas, migration behavior, or validators to
  suppress the observed failures.

## Constraints And Invariants

- Keep public/persisted schemas, writer policy, recovery keys, operation fences,
  and transaction semantics unchanged unless a governing design decision is
  required.
- Preserve the parent milestone's implemented-but-unverified fresh-owner wiring;
  no capability may be fabricated, persisted, or reused.
- Treat current dirty-tree behavior as in scope until a discriminating
  experiment proves otherwise; do not label a failure pre-existing from a prior
  run alone.
- Use only the focused reproducer commands below until causal signatures are
  captured.

## Expected And Observed Behavior

| Family | Expected | Observed | Impact |
| --- | --- | --- | --- |
| Writer-admission reopen | A provider reopened over an existing durable writer record preserves its existing current admission and reaches reconciliation. | `_ensure_writer_admission_record` attempts evidence-only initialization and raises `writer admission is already bound differently` before recovery. | Public JSONL recovery cannot reach fresh-owner or ordinary reconciliation. |
| V3 no-lease replay | Valid retained found recovery bytes decode, validate, and return one replay record; foreign key returns `None`. | Valid key returns `None`; V3 reopen also sees control/claim state divergence. | Cannot establish replay baseline or enabled/disabled equivalence. |
| Span-cost candidate (SC) | The focused valid V3 replay reproducer should finish within its ordinary deterministic test budget without changing byte or span semantics. | After its fixture correction, it remained in `encode_typed_value_with_spans` for more than 315 seconds and was interrupted at `ingestion_contracts.py:688`. | Blocks the focused VR proof; it is not yet classified as an implementation defect. |

First observed current-tree commands and signals:

```text
cd memorii
../.venv/bin/python3.12 -W error -m pytest \
  tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py::test_public_jsonl_reconcile_resumes_preplanning_outage_without_redelivery \
  --maxfail=1 -p no:cacheprovider

FAILED ...[policy_read]
SemanticWriterAdmissionError: writer admission is already bound differently
at ProviderMemoryService._ensure_writer_admission_record

../.venv/bin/python3.12 -W error -m pytest \
  tests/unit/core/semantic_ingestion/test_bootstrap_v3_recovery_reopen.py \
  tests/unit/core/semantic_ingestion/test_bootstrap_recovery_replay_v3.py \
  -p no:cacheprovider

4 failed, 3 passed in 146.07s
- valid no-lease reload returned None for memory and JSONL backends
- consumed claim reported foreign
- reopened control reported preplanning rather than terminal
```

## Affected Identity And Authority Chains

| Family | Identity/authority chain | Risk boundary |
| --- | --- | --- |
| Writer admission | persisted writer-admission record -> `SemanticWriterAdmissionStore` -> `ProviderMemoryService._ensure_writer_admission_record` -> public `sync_event`/reconcile root | A reopened service must not overwrite or silently reinterpret an existing durable writer identity. |
| V3 replay | exact operation fence -> persisted `BootstrapWriterHandoffMarkerV3` -> recovery key/index -> retained normalization members -> `reload_bootstrap_recovery_replay_v3` -> graph/reconcile consumer | Recovery must use exact retained bytes and reject foreign/stale controls without changing terminal or claim semantics. |

No planning coordinate is permitted in runtime, persisted, or test identities.

## Reproducer Plan

| Reproducer | Environment/input | Expected causal signal |
| --- | --- | --- |
| Writer-admission minimal reopen | The existing single parametrized `policy_read` JSONL case, isolated with `--maxfail=1` | Establish whether the error originates during service composition, existing-record decode, or an incompatible initializer choice before reconciliation. |
| V3 no-lease reload | The existing exact replay test's in-memory case only | Capture the first failed retained-record/member/re-encode predicate and distinguish decoder, index/recovery lookup, or control/claim state causes. |

## Hypothesis Ledger

### Writer-admission family

| ID | Hypothesis | Supporting evidence | Contradicting evidence | Discriminating experiment |
| --- | --- | --- | --- | --- |
| WA-1 | Service ownership metadata incorrectly treats a durable runtime writer as locally owned and invokes evidence-only initialization on reopen. | Failure occurs in `_ensure_writer_admission_record` before reconciliation. | The exact stored record/ownership flags have not been inspected in the failing process. | Record construction flags, runtime writer source, and existing record identity immediately before the initializer. |
| WA-2 | The durable record is valid but its manifest/fingerprint intentionally differs from the evidence-only initializer, and the service lacks an idempotent preserve-current branch. | Exception text says the writer is already bound differently. | The mismatch could instead be malformed persistence or fixture setup. | Decode current record and compare manifest/fingerprint against the initializer's expected values without writing. |

### V3 replay family

| ID | Hypothesis | Supporting evidence | Contradicting evidence | Discriminating experiment |
| --- | --- | --- | --- | --- |
| VR-1 | The no-lease replay reload rejects a valid retained member because one decode/re-encode or digest predicate is no longer byte-equivalent. | Valid key returns `None` for both memory and JSONL. | The first failing predicate is not yet observed. | Wrap public replay dependencies/read-only values to record the first `None` or mismatch predicate. |
| VR-2 | Recovery index/control/claim transition state is inconsistent with the persisted marker, so the valid key does not reach member reconstruction. | Reopen reports `preplanning`/`foreign` where tests expect `terminal`/`consumed`. | The direct replay failure might be independent of control transitions. | Compare index state, marker digest, recovered generation, and claim/control records between initial and reopened handles. |
| VR-3 | The semantic-reduction authority's `*_canonical_bytes` preimages differ from the validator's encoding, causing the pre-publication failure. | The validator's single error says the authority bytes are not canonical. | The error predicate also covers empty, unordered, duplicated, or incomplete `operation_inputs`. | Intercept the real constructor, recompute each typed preimage with the validator expression, decode both values, and evaluate the preceding structural predicates in order. |
| SC-1 | The span encoder regressed by repeatedly serializing a large normalized tree or repeatedly sorting the same keys. | The interruption stack lands in `_json` beneath `encode_typed_value_with_spans`; the span implementation was added by the current canonical-evidence remediation. | Disproved by the exact production input timing: its span walk is bounded and the delay occurs between calls. | Do not modify the span walker in this debugging operation; defer cumulative closure-cost measurement to the parent VCC-R01 acceptance boundary. |

## Experiment Ledger

| Experiment | Hypotheses distinguished | Command and result | Causal signature | Ledger update |
| --- | --- | --- | --- | --- |
| A: policy-read writer ownership after service construction | WA-1 versus WA-2 | Read-only Python reproduction constructed the exact `_verified_runtime_store` and patched `_InstalledCapabilityEntryPoint(_AuthorizedCapability(_runtime_for_outage(..., stage="policy_read")))`, then inspected state before `sync_event`. | `bootstrap_profile_is_none=True`; coordinator `semantic_runtime_is_none=True`; `owns_writer_admission_record=True`; service writer is not helper writer (`False`), although both current records are `semantic-ingestion:verified`, `verified_semantic`, `writer:verified`; patched capability was not loaded into runtime (`False`); no verified profile/material verifier result exists; `writer_record_initialized=False`. | WA-1 strengthened: the bootstrap profile/runtime gate ignores the patched runtime, then service falls back to a separate locally-owned store over the same durable record. WA-2 remains possible only as the downstream mismatch mechanism. |
| B: in-memory no-lease replay first false | VR-1 versus VR-2 | Read-only Python reproduction used the public in-memory replay setup, then inspected index, called `recover_bootstrap_v3_source_normalization`, and would have evaluated members/decode/roundtrip/digest/link predicates in production order. | Index is `semantic_ingestion_bootstrap_v3_recovery_index`, key matches, but state is `claimed`; recovery raises `PreplanningStoreError: bootstrap V3 recovery index is corrupt`; public reload returns `None`. No member/decode predicate executes. | VR-2 strengthened: first false condition is `state == "found"`, not a decode/re-encode or digest predicate. VR-1 is not yet exercised and remains open only as a possible later failure after transition repair. JSONL repetition is unnecessary because in-memory is conclusive at an earlier common predicate. |
| C: installed capability/profile gate versus base source | WA-1 versus WA-2 | Read-only protocol and `git show b9daf00a` trace inspected `InstalledHostBootstrapCapabilityProvider.load`, `_AuthorizedCapability`, and the service construction chain. The provider follows `entry_point.load() -> _CapabilityLoader -> capability`; the capability offers runtime construction but this fixture invocation supplies no `host_bootstrap_material_verifier`, so no verified material/profile exists and the runtime-builder guard is false. | The test's patched capability is selected as `host_bootstrap_capability`, but absent verifier/material means profile and runtime are both absent. Base also gated runtime construction on a verified profile and did not initialize a writer when that profile was absent. Current source added `_owns_writer_admission_record`, `_writer_admission_record_initialized`, and `_ensure_writer_admission_record`, then invokes the initializer from `_ingest_event`. | WA-1 confirmed as the first current-tree behavioral divergence: deferred evidence-only initialization is production service ownership logic and conflicts with an existing durable writer. The fixture's lack of verified material is a separate composition precondition; it explains why the supplied runtime is not used, but it does not justify the new conflicting write. Smallest correct correction candidate is service ownership logic that preserves an already-bound durable writer when no verified profile/runtime exists, not weakening the fixture or profile gate. |
| D: V3 claim-to-found producer trace versus base source | VR-1 versus VR-2 | Read-only public setup wrapped only `authority_provider.build` and `execution_owner.normalize_after_recovery_claim`, returning original results. Source comparison covered `ProviderIngestionCoordinator._run_semantic_ingestion`, V3 claim repository, and normalization execution/publication surfaces. | Authority build returns `SourceNormalizationAuthorityBundle`; normalization returns `SourceNormalizationNonCommit(reason="publication_conflict")`; public result is `source_alignment_authority_unavailable`; index remains `claimed`. The claim-to-found record is produced only by the successful publication CAS. The recovery wiring diff changes reconciliation and replay lease plumbing, not this claim/publication path. | VR-2 confirmed as the earliest candidate: a publication conflict prevents the found-index CAS. The no-lease reload failure and reopen control/claim divergences are downstream symptoms. VR-1 remains untested because no found generation exists. The next causal boundary is the publication conflict's exact precondition or write collision, not graph-host/terminal completion. |
| E: in-memory V3 publication-CAS and stage exception trace | VR-1 versus VR-2 | Read-only wrapper observed every `MemoryPlaneService.conditionally_write_records` call, evaluated each supplied absent/digest/fence precondition against the current record, and called the original unchanged. A second read-only wrapper captured the exception escaping `BootstrapV3SourceNormalizationStage.normalize`. | All observed conditional writes succeeded; repeated recovery-index claim-renewal preconditions were true. No Found-publication CAS was attempted, so there is no false CAS precondition, no competing proposed record, and no stale expected generation selected at the storage boundary. Before publisher invocation, `BootstrapSemanticReductionAuthorityMemberV3` raises a validation error: `bootstrap semantic reduction authority bytes are not canonical`. | VR-2 is refined: `publication_conflict` is a lossy wrapper for a pre-CAS canonical-bytes validation failure, not a write collision. The retained index stays `claimed` because the source-normalization stage never produces a publication request. VR-1 remains deferred until this preimage/validator mismatch is isolated. |
| F: semantic-reduction canonical preimage | VR-3 versus structural-closure alternative | Read-only production composition wrapped only `BootstrapSemanticReductionAuthorityMemberV3.create`, recorded its original keyword arguments, called the original unchanged, then independently evaluated the validator's three `encode_typed_value(canonical_contract_value(...))` expressions and decoded each actual/expected payload with span reporting. | All three bytes are byte-identical to the validator expectation: core `47,442` bytes, SHA-256 `6f7cc501c0cd048f284ee622525ec4c9e9830c41b0f40dac15e2138344ca9f80`, decoded `dict`, `2,289` spans, root `() [0,47442)`; policy `1,100` bytes, SHA-256 `b632f0baa212389c5245bbe6cff1cad4fef2762ceca70ef88edbf7b2f64c93ca`, `79` spans, root `() [0,1100)`; registry `347` bytes, SHA-256 `c8a2ba21816cbe7573957bae9d328a5e5540f5f8c69253dc6d9caadfdcda9679`, `23` spans, root `() [0,347)`. Each decoded actual/expected pair is the same typed `dict`; no byte path, type, or value differs. The first failed validator predicate is instead `not self.operation_inputs`: constructor input `operation_inputs` is an empty `tuple` at path `operation_inputs`, while the member contract requires at least one operation input. | VR-3 is disproved for the three canonical-byte fields. The error text conflates byte equality with the earlier structural-closure check. The upstream issue is the selected corpus/alignment yielding no complete dependency operations; its failure is wrapped as `publication_conflict`, leaving the index `claimed`. |
| G: graph-free invocation to reduction input closure | VR-2/VR-3 and fixture-versus-production alternative | Read-only production composition repeated the exact recovery-test setup and observed the real authority-member constructor. Static chain tracing covered `ProviderIngestionCoordinator` preparation checks -> `GraphFreeSourceNormalizationInvocation` -> V3 proposal/evidence/interpreter -> `BootstrapV3SourceNormalizationStage` -> `_native_reduction_inputs`; base/current comparison covered that chain and the replay fixture. | The prepared source is complete and all five V3 lane callbacks run once. The recovery test calls `_v3_normalization_host_builder()` with no proposal; that helper explicitly selects `ProviderSemanticProposal(abstained=True)`. `bootstrap_v3_proposal.py` therefore creates an abstained normalized proposal with no operation members; `expand_pre_alignment_subjects`/the V3 interpreter consequently yields zero subjects, alignments, and complete dependency groups; `_native_reduction_inputs` correctly returns `()`. In contrast, existing successful graph-root fixtures for the identical text pass two mentions plus a positive `owner_is(atlas,bob)` fact with `abstained=False`, producing the required operation. | VR root cause is complete for the replay baseline: its asserted Found/reload success is incompatible with its own abstained fixture. The V3 stage catches the resulting structural `ValueError` as `publication_conflict`, so the claim remains `claimed` and no-lease reload correctly returns `None`. `git diff b9daf00a --` reports no changed file across the helper, replay test, proposal conversion, alignment, V3 stage, or execution owner; this is not introduced by the current remediation. |
| H: focused replay cost classification | SC-1 versus cumulative closure-cost alternative | The exact first input has 1,710 nodes, 1,425 strings, and 40,680 string characters: normalization `0.004041s`, ordinary `_json` `0.010513s` for 58,474 bytes, and span walk `0.021102s` for 3,102 spans. A complete valid sync made 122 span calls in `93.497319s`; the largest individual span call was 682,789 bytes/21,114 spans in `0.14-0.33s`, while post-call gaps reached `13.667015s`. | The direct span-walker hypothesis is disproved. The observed cost is cumulative work outside the span walker, so it is a parent VCC-R01 acceptance/performance-measurement concern, not a third defect family in this WorkPlan. The speculative span-walker edits were reverted. |
| I: corrected policy-read outage boundary | verified preparation fixture versus production-validation failure | A read-only wrapper over the corrected public root recorded `release -> CurrentBootstrapReleaseAssertion`, `prepare -> PreparedSource`, `publish -> tuple`, second `release`, `handoff -> BootstrapWriterHandoffResult(started)`, then `policy -> OSError(policy unavailable)`. The public result is `source_alignment_authority_unavailable`. | The earlier fixture's synthetic preparation produced no exact grammar proofs. `_ProfileBoundOutageCapability` now binds `TextPreparationService.for_verified_bootstrap_profile` to the exact profile received through capability composition, matching production construction without bypassing the release, grammar, writer, or handoff checks. | The planned policy outage is reached. The remaining red assertion assumes `semantic_ingestion_generation_member`, while this composition retains preplanning control/artifact records and has no complete V3 normalization/graph-host fixture to produce the asserted generation members. |
| J: policy-read checkpoint identity trace | split store/plane versus pre-checkpoint control-flow mismatch | Read-only `SemanticIngestionLeaseSession.checkpoint_execution_plan` wrapper recorded entry/return/exception while the corrected public policy-read root recorded result and every plane record. `id(plane)`, injected store plane, runtime store plane, and coordinator store plane are identical; `checkpoint` trace is empty. The result is `source_alignment_authority_unavailable`; records include prepared source, preplanning control/artifacts, handoff marker, and V3 recovery index, but no generation member. | There is no alternate store or plane. `ProviderIngestionCoordinator.ingest` sees the V3 handoff marker, invokes `_run_semantic_ingestion` before ordinary checkpointing, and returns at the mandatory source-normalization gate when `runtime.source_normalization_host_bundle is None`; execution never reaches `checkpoint_execution_plan`. | The source-normalization fixture was subsequently completed under the governing ordering decision; the checkpoint remains absent, so the mismatch is not the missing normalization bundle. |
| K: complete V3 normalization outage fixture | missing normalization bundle versus post-normalization early return | All three outage parameters use `_v3_normalization_host_builder(proposal=_atlas_owner_proposal())` inside the profile-bound runtime. The run produced `3 passed, 3 failed in 103.03s`: writer tests passed; policy-read had no generation members, and proposal/analysis persisted V3 normalization members including `bootstrap_analysis_lane_result`, `bootstrap_graph_free_interpretation_bundle`, `bootstrap_graph_normalization_authority`, and `bootstrap_normalization_request_core`, but none persisted `execution_plan`. | The verified V3 source-normalization authority is now supplied and active. The remaining missing checkpoint occurs after V3 normalization, before the ordinary retry-plan path, so it cannot be corrected by the requested normalization fixture alone. | The governing instruction rules out reordering or source-alignment bypass and says no graph fixture is required. Current runtime evidence still contradicts the checkpoint contract. Replay tests were not run because the required outage gate remains red. |

## Causal Signatures Captured

- Writer ownership signature: a patched installed capability does not produce a
  verified bootstrap profile or semantic runtime. The provider chooses local
  writer ownership despite the durable record already being verified, then its
  later evidence-only initializer conflicts with that record.
- Replay signature: a valid recovery key references a `claimed` index, while
  the no-lease reload contract requires `found`; the first failure is the
  recovery-state predicate and member decoding is not reached.
- V3 producer signature: the authority bundle is available, but its
  `normalize_after_recovery_claim` call returns `publication_conflict`; the
  Found transition has not run. Graph-host/terminal completion is later in the
  flow and is not the cause of this baseline failure.
- Publication-CAS signature: every observed claim/renewal conditional write
  had satisfied preconditions. No publication CAS was reached. The precise
  pre-CAS exception is `BootstrapSemanticReductionAuthorityMemberV3` rejecting
  its canonical bytes as noncanonical.
- Semantic-reduction preimage signature: producer and validator both use
  `encode_typed_value(canonical_contract_value(...))`, not
  `encode_semantic_contract`. The three retained preimages are equal after
  independent typed decode and span traversal. The first predicate that is
  actually false is the empty `operation_inputs` tuple, not a byte mismatch.
- Input-closure signature: `GraphFreeSourceNormalizationInvocation` is formed
  only after the prepared source is checked complete and exact. Its V3
  authority then runs proposal, stanza, spaCy, predicate, and temporal lanes
  once. The earliest removal is not a lane filter: the recovery fixture itself
  supplies `ProviderSemanticProposal(abstained=True)`, whose contract forbids
  operation members. The later zero-subject/zero-group state is required.
- Span-cost signature: 122 bounded span walks occur during the valid sync; the
  direct 1,710-node preimage is millisecond-scale and the largest observed
  span walk is below one third of a second. The delay is in cumulative
  post-call closure work, so SC-1 is disproved and no performance edit belongs
  in this debugging WorkPlan.
- Corrected outage signature: the profile-bound preparation fixture passes
  release assertion, exact grammar-proof publication, and writer handoff before
  the intended policy exception. The remaining public `source_only`-style
  expectation is blocked by missing complete V3 normalization/graph-host
  fixture composition, not by writer admission or preparation validation.
- Checkpoint identity signature: all runtime/coordinator/injected atomic-store
  identities share the same memory plane. The checkpoint method is not called;
  an early mandatory V3 source-alignment return, not misplaced persistence,
  prevents the required generation member.
- Complete-normalization signature: the valid Atlas/Bob V3 bundle produces
  retained normalization members for proposal and analysis failures, proving
  the gate is no longer absent. `execution_plan` remains absent in all three
  stages, isolating the mismatch to the later early-return flow.

## Causal Chain Candidates

| Family | Earliest divergent condition | Candidate correction owner | Why not the alternative |
| --- | --- | --- | --- |
| Writer admission | Current `ProviderMemoryService._ensure_writer_admission_record` writes evidence-only admission at first ingress when local ownership is inferred, even though the memory plane already contains a verified durable record. Base only initialized when a verified profile existed. | `ProviderMemoryService` ownership/initialization logic, subject to exact durable-record validation. | Reworking the fixture to supply verified material would make the runtime gate pass but would conceal the service's newly introduced conflicting fallback write. |
| V3 replay | The old Found/reload tests supplied the abstaining default proposal, which correctly has no operation members and remains `claimed`. | Test fixture contract: Found/consumed assertions must provide the existing non-abstaining Atlas/Bob `owner_is` proposal; abstaining behavior must assert claimed/no replay. | The production source-alignment gate, reduction closure, CAS, and replay rejection are correct for abstention. No production bridge change is justified. |

The V3 correction is test-contract-only: Found/consumed proof now supplies the
complete existing Atlas/Bob proposal, and explicit abstention proof asserts
claimed/no replay. The old outage/reconcile parametrization and its
profile-bound capability were removed because they encoded a legacy
`execution_plan` expectation that conflicts with governing V3
graph-dependent/redelivery ordering.

### V3 Replay Root-Cause Model

| Element | Evidence-backed model |
| --- | --- |
| Trigger | `test_reload_bootstrap_recovery_replay_v3_is_exact_and_rejects_foreign_key` invokes `_v3_normalization_host_builder()` without a proposal, then expects a retained Found record and a non-`None` replay. |
| Defective assumption | The test treats supported input text as sufficient for a V3 graph operation even though its host proposal factory explicitly returns `ProviderSemanticProposal(abstained=True)`. Supported grammar permits an operation; it does not fabricate one after an authoritative abstention. |
| Propagation | Complete prepared source -> `GraphFreeSourceNormalizationInvocation` -> abstained normalized proposal with zero operation members -> zero pre-alignment subjects -> zero complete dependency groups -> `_native_reduction_inputs == ()` -> reduction authority structural validation raises -> execution owner maps the `ValueError` to `publication_conflict` -> recovery index remains `claimed` -> no-lease reload correctly returns `None`. |
| Earliest filter/validation | `ProviderSemanticProposal.validate_abstention` forbids operations when `abstained=True`; V3 proposal normalization preserves that status and `BootstrapNormalizedProposalV3` enforces that an abstained proposal has no operation members. No parser, scope, temporal, or alignment filter removes a valid operation. |
| Expected fixture comparison | Existing successful graph-root tests use the same text with a complete proposal: mentions `atlas`/`bob`, positive `owner_is` fact, and `abstained=False`. The replay/reopen tests instead use the helper default abstention. |
| Base/current comparison | `git diff b9daf00a --` is empty for the helper, replay/reopen tests, V3 proposal conversion, source alignment, V3 stage, and execution owner. The base replay test has the same default-builder call and Found expectation. This is a baseline fixture-contract mismatch, not a current remediation production regression. |
| Correction and risks | The replay and reopen Found/consumed tests now use the complete existing `Atlas owner is Bob.` proposal; the replay module separately asserts abstained claimed/no-replay behavior. The obsolete JSONL outage test and its test-only profile-bound capability were deleted. No authority-member invariant, publication behavior, schema, or recovery gate changed. The broad `publication_conflict` diagnostic remains a separate follow-up, not a defect in this bounded replay contract. |

## Semantic-Reduction Authority Family Map

An AST inventory of every semantic-ingestion contract class with a
`*_canonical_bytes` field finds exactly this sibling family. Both constructor
sites are in `source_normalization_stage.py`, and both validators use the same
typed-value preimage rather than semantic-contract envelopes.

| Member constructor | Producer and byte expression | Validator expression | Current proof status |
| --- | --- | --- | --- |
| `BootstrapSemanticReductionAuthorityMemberV3` | `BootstrapV3SourceNormalizationStage.normalize`, `encode_typed_value(canonical_contract_value(core/policy/registry))` | `validate_reduction_bytes`, the same three expressions plus nonempty/sorted/complete `operation_inputs` closure | Directly probed. All three byte fields match; empty operation inputs is the first false predicate. |
| `BootstrapGraphNormalizationAuthorityMemberV3` | `BootstrapV3SourceNormalizationStage.normalize`, `encode_typed_value(canonical_contract_value(policy/registry))` | `validate_canonical_bytes`, the same two expressions | Same encoding pattern and producer family, but it is created before the failing reduction member; no separate live mutation/probe is yet required because the captured policy/registry preimages already match its exact expressions. |

`git show b9daf00a` comparison finds the two authority constructor calls and
both validators unchanged at this boundary. The current canonical-evidence
remediation changed the later general `encode_semantic_contract_result` path,
not these typed-value producer/validator expressions; therefore this baseline
failure is not explained by a current-tree byte-codec drift.

## Writer-Admission Root-Cause Model

| Element | Evidence-backed model |
| --- | --- |
| Trigger | Public JSONL provider construction receives an installed capability that lacks verified-material verification; at first `sync_event`, the current service calls `_ensure_writer_admission_record`. |
| Defective assumption | `runtime_writer is None` is treated as local ownership even when the memory plane already holds a durable verified writer record; deferred evidence-only initialization assumes it may safely establish a local record. |
| Propagation | Profile/runtime gate remains false -> service constructs a separate `SemanticWriterAdmissionStore` over the same plane -> `_owns_writer_admission_record=True` -> first ingress calls `create_initial_evidence_only` -> manifest mismatch raises `SemanticWriterAdmissionError`. |
| Why validation/test missed it | The deferred initializer was introduced after base and the existing reopen fixture exercises an installed capability without a material verifier, exposing the fallback path only at ingress rather than construction. |
| Symptom | Reconciliation setup fails before admitted source, recovery, or fresh-owner code executes. |
| Candidate smallest fix | In `ProviderMemoryService`, validate/preserve an existing current durable writer record before treating fallback state as locally owned; only create evidence-only admission when no record exists and the governing profile authorizes it. |
| Risks | Must not silently accept malformed, revoked, incompatible, or foreign writer records; preserve the verified-profile/runtime authority gate and existing no-write behavior for unauthenticated construction. |

## Changed-Surface Ledger

| Surface | Status | Reason |
| --- | --- | --- |
| `memorii/memorii/core/provider/service.py` | changed and focused-verified | At first authenticated ingress, a locally owned fallback validates/preserves an existing durable writer admission; it initializes evidence-only only when no durable record exists. |
| `memorii/tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py` | changed and focused-verified | Adds three writer preservation/default/corruption regressions; removes obsolete legacy outage/reconcile parametrization and its dedicated fixture/imports. |
| `memorii/memorii/core/memory_evolution/ingestion_contracts.py` | no owned change | speculative span-walker optimization was manually reverted after SC-1 was disproved |
| `memorii/tests/unit/core/test_ingestion_contracts.py` | no owned change | speculative span-walker unit proof was manually reverted with the optimization |
| `memorii/tests/unit/core/semantic_ingestion/test_bootstrap_recovery_replay_v3.py` | changed and focused-verified | Found/reload proof supplies a complete non-abstaining proposal; sibling abstention proof requires claimed/no replay. |
| `memorii/tests/unit/core/semantic_ingestion/test_bootstrap_v3_recovery_reopen.py` | changed and focused-verified | Found/consumed reopen cases supply the same complete proposal; pending-claim cases retain default abstention. |

## Production Entrypoint Bindings

| Requirement | Canonical trigger and composition root | Exact owner chain | Proof and caller count | Status or explicit blocker |
| --- | --- | --- | --- | --- |
| Preserve existing durable writer admission on fallback ownership | Public `ProviderMemoryService.sync_event`, composed by the existing provider service/factory path | authenticated ingress -> `_ingest_event` -> `_ensure_writer_admission_record` -> existing `SemanticWriterAdmissionStore.current()` -> existing admission/fail-closed error | Three focused service-root regressions exercise the public ingress boundary. This debugging slice did not refresh the parent production-entrypoint mapper, so a non-test caller count is not claimed here. | Locally verified correction; parent runtime acceptance and its binding ledger remain required before an implementation-complete claim. |
| V3 Found/reload versus abstained replay | Public `ProviderMemoryService.sync_event` -> existing V3 source-normalization/recovery chain -> `reload_bootstrap_recovery_replay_v3` | authenticated ingress -> complete or abstained host proposal -> V3 reduction -> claimed/Found index -> replay reload | `test_bootstrap_recovery_replay_v3.py` passes both in-memory and JSONL Found/reload and abstained no-replay cases; `test_bootstrap_v3_recovery_reopen.py` passes durable reopen/claim cases. | Test-contract correction only; no new production trigger or persisted behavior is claimed. Parent recovery fresh-owner binding remains partial. |

## Authority And Identity Ledger

| Item | Exact identity/authority | Current result |
| --- | --- | --- |
| Durable writer admission | Existing `writer_admission_memory_id()` record -> `SemanticWriterAdmissionStore.current()` | Existing valid identity is retained byte-for-byte; malformed records raise; missing records receive exactly one existing evidence-only initialization at authenticated ingress. No record schema changes. |
| V3 proposal authority | Host-provided `ProviderSemanticProposal`: complete Atlas/Bob positive `owner_is` for Found/consumed; explicit `abstained=True` for noncommit | Tests now express the authoritative distinction without fabricating an operation after abstention. No proposal, recovery-key, control, fence, or marker identity changed. |
| Candidate identity | `debug-candidate-identity-v1.json` and its validator | Revision-bound dirty-tree and scoped-file hashes are recorded for review only; the artifact excludes itself and its validator from status hashing to avoid a self-reference cycle. |

## Evidence And Gate Ledger

- Obsolete `test_public_jsonl_reconcile_resumes_preplanning_outage_without_redelivery`
  was removed. Its `execution_plan` assertion is a baseline fixture-contract
  mismatch against governing V3 graph-dependent/redelivery design, not a
  production bridge defect. Its profile-bound outage helper and local proposal
  helper were removed with it.
- `PYTHONPATH=memorii .venv/bin/python3.12 -W error -m pytest`
  `memorii/tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py::test_profileless_service_preserves_existing_durable_writer_at_ingress_and_reconcile`
  `memorii/tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py::test_profileless_service_creates_default_writer_once_at_first_ingress`
  `memorii/tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py::test_profileless_service_fails_closed_for_corrupt_durable_writer -p no:cacheprovider`
  passed: `3 passed in 5.35s`.
- `PYTHONPATH=memorii .venv/bin/python3.12 -W error -m pytest`
  `memorii/tests/unit/core/semantic_ingestion/test_bootstrap_recovery_replay_v3.py -p no:cacheprovider`
  passed: `4 passed in 239.56s` (complete Found/reload and abstained claimed/no-replay across memory and JSONL).
- `PYTHONPATH=memorii .venv/bin/python3.12 -W error -m pytest`
  `memorii/tests/unit/core/semantic_ingestion/test_bootstrap_v3_recovery_reopen.py -p no:cacheprovider`
  was split after the prior interrupted aggregate: its first four cases passed
  in `197.36s` before manual interruption; the remaining
  `test_jsonl_fresh_provider_reopens_v3_found_without_reinvoking_any_lane`
  then passed under a hard 600-second subprocess bound in `121.22s`.
- `.venv/bin/ruff check memorii/memorii/core/provider/service.py`
  `memorii/tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py`
  `memorii/tests/unit/core/semantic_ingestion/test_bootstrap_recovery_replay_v3.py`
  `memorii/tests/unit/core/semantic_ingestion/test_bootstrap_v3_recovery_reopen.py` passed; `git diff --check` passed.
- Focused arena/v11 evidence remains historical parent evidence, not proof of
  this debug closure. No CI, broad-suite, replay-fresh-owner, or parent
  implementation-complete claim is made.

## Delegation Ledger

| Task | Role | Ownership | Status |
| --- | --- | --- | --- |
| Causal isolation and any fix | sole writer | debugging operation surfaces | active |
| Read-only mapping from parent | code-mapper capacity fallback to read-only explorer | prior input | consumed |
| Test-review consultation | test reviewer | unavailable due inappropriate freeze gating; parent acceptance matrix retained | unavailable |
| Correctness-reviewer Phase-5 refusal | correctness reviewer | candidate freeze is Phase 8, while Phase 5 was pre-fix causal isolation | unsupported; not a root-cause finding |

## Next Action

Run independent delta review against debug candidate v3.

## Closure-Finding Reconciliation Round 2

- Debug candidate v1 is superseded by this ingress-order correction and must
  not be reviewed as current evidence.
- WA is confirmed: `_ingest_event` previously created or validated durable
  writer admission before resolving host ingress. That let an absent or
  rejected request create durable writer state without crossing the
  authenticated boundary.
- The correction resolves ingress first and invokes `_ensure_writer_admission_record`
  only for a resolved ingress. Existing valid records still use `current()`;
  malformed records still raise; a missing record is created exactly once at
  the first resolved ingress.
- The compact focused matrix runs both memory and JSONL for resolved-create and
  valid-preserve; it proves missing and resolver-rejected no-write before the
  same resolved service creates once. Corrupt-record fail-closed remains a
  durable JSONL corruption proof because governed in-memory storage refuses a
  synthetic unauthorized corruption write.
- V3 atomic-store/reconcile findings are confirmed but deliberately not
  modified in this debugging round. They are transferred to the paused parent
  recovery/reconciliation packet for the fresh-owner implementation operation.

### Round-2 Authority And Identity Ledger

| Item | Authority/identity result |
| --- | --- |
| Ingress gate | `AuthenticatedHostIngress` -> configured resolver -> non-`None` authenticated context is now the sole condition before a fallback writer record may be touched. Absent/rejected input has no writer-admission durable outcome. |
| Writer record | The existing `writer_admission_memory_id()` remains unchanged. Resolved ingress preserves a valid record through `current()`, creates the existing evidence-only record only when absent, and fails closed for malformed content. |
| Production reachability | Generated v12 map records one non-test factory composition occurrence and four Hermes `sync_event` occurrences, then hashes the resolver-before-writer source edge and durable/no-write outcomes. This is a map/validation proof, not parent recovery completion. |
| Candidate identity | `debug-candidate-identity-v2.json` replaces v1 and is scoped to WA plus the prior V3 fixture-contract correction. Parent replay/reconcile implementation and all other dirty paths remain excluded. |

### Round-2 Evidence

- `PYTHONPATH=memorii .venv/bin/python3.12 -W error -m pytest`
  `test_semantic_provider_composition.py::test_profileless_service_preserves_existing_durable_writer_at_ingress_and_reconcile`
  `test_semantic_provider_composition.py::test_profileless_service_waits_for_resolved_ingress_then_creates_default_once`
  `test_semantic_provider_composition.py::test_profileless_service_fails_closed_for_corrupt_durable_writer -p no:cacheprovider`
  passed `5` cases (`memory` and `JSONL` where the mutation boundary is public).
- v12 builder and validator passed with six source edges, factory caller count
  `1`, Hermes caller count `4`, and no hash/edge failures.

## Closure-Finding Reconciliation Round 3

- Candidates v1 and v2 are superseded. Construction of profileless,
  verified-profile/no-runtime, and built-in semantic runtime paths now creates
  no durable writer record.
- The canonical writer store is initialized or validated only after resolved
  ingress and before coordinator ingestion. Valid existing records preserve;
  corrupt or foreign records fail closed; absent/rejected ingress writes none.
- The direct service, factory, Hermes `sync_turn`, and filesystem roots were
  observed no-write at construction and create-once after authenticated
  forwarding. V3 authority/reconcile findings are unchanged and transferred to
  the paused parent packet.

### Round-3 Binding/Identity Evidence

| Evidence | Result |
| --- | --- |
| v13 map | Six hash-bound service/capability/factory/Hermes/filesystem edges; caller counts factory `1`, Hermes `11`, filesystem `1`. |
| Focused nodes | `test_builtin_local_capability_wires_provider_hermes_and_filesystem_without_entrypoint_patch`, `test_profileless_service_preserves_existing_durable_writer_at_ingress_and_reconcile`, `test_profileless_service_waits_for_resolved_ingress_then_creates_default_once`, and `test_profileless_service_fails_closed_for_corrupt_durable_writer` passed `6` cases in `32.20s`. |
| Candidate | `debug-candidate-identity-v3.json` is the only current review identity after hash validation. |

## Writer-Admission Delta Evidence

- The corrupt and well-formed foreign-manifest durable-writer cases now use a
  resolved public `sync_event` ingress over JSONL. Both raise
  `SemanticWriterAdmissionError` before coordinator ingestion, preserve the
  exact JSONL bytes and full record snapshot, retain exactly one unchanged
  writer record, and add no non-writer ingestion records.
- A service-free `HermesMemoryProvider` now exercises its real constructor
  arguments (`memory_plane`, host bootstrap capability, and material verifier)
  with the resolver embedded in verified host material: construction and a
  resolver rejection are write-free; an authenticated `sync_turn` creates one
  writer record. The existing direct/Hermes `on_memory_write` focused case
  continues to cover missing, rejected, and resolved ingress.
- Focused command (from `memorii/`):
  `../.venv/bin/python3.12 -W error -m pytest tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py::test_configured_hermes_constructs_write_free_then_creates_once_after_authenticated_turn tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py::test_profileless_service_rejects_invalid_or_foreign_durable_writer_without_writes tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py::test_memory_write_preflights_ingress_before_writer_creation tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py::test_profileless_service_preserves_existing_durable_writer_at_ingress_and_reconcile tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py::test_profileless_service_waits_for_resolved_ingress_then_creates_default_once -p no:cacheprovider`
  passed `9` cases in `15.65s` on Python `3.12.14`.
- No production-entrypoint binding ledger or governance artifact was changed in
  this bounded test-only slice; it establishes regression evidence but does
  not claim the parent runtime/persistence milestone complete.

## Next Action

Run independent delta review against debug candidate v3, including this
writer-admission evidence update.

## V14 Production-Binding Evidence

- `production-entrypoint-bindings-v14.json` supersedes v13 as the structured,
  source-derived `production_entrypoint_bindings` evidence for authenticated
  writer admission. It covers direct `sync_event` and `apply_memory_write`,
  the repository factory, configured Hermes `sync_turn` and `on_memory_write`,
  and the filesystem root. Each row records requirement IDs, real trigger and
  composition owner, exact authority/ingress forwarding, ordered validation
  chain, durable or no-write outcome, fail-closed behavior, AST caller census,
  and focused behavioral nodes.
- `validate_production_entrypoint_bindings_v14.py` passed all five self-test
  mutations: omitted root, omitted trigger, authority forwarding,
  pre-resolution order, and unrelated fake caller count. The validator also
  pins hashes for service, capability, production authority, factory, Hermes,
  filesystem, production capture, and the focused composition tests.
- This refresh is evidence only. `debug-candidate-identity-v3.json` remains
  unfrozen and was intentionally not regenerated.
