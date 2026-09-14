# Bounded Activation Correctness Review

- Candidate: `activation-evidence/candidate.json` SHA-256 `aefaac2d4c3a655d2be8e3570926f6b0923347f9adefc09eacdacf6663c03b28`.
- Candidate source hashes: verified current for `atomic_store.py`, `writer_admission.py`, `observation_activation_runtime.py`, `provider/service.py`, `capability.py`, and the two activation test files listed by the candidate.
- Scope: explicit cutover, drain, detached full-write snapshot, native retired inventory, one-CAS trio, repeat/restart recovery, historical bytes, and governed old grammar. Append, retrieval, and checkpoints remain excluded and unimplemented.
- Evidence: code and artifact inspection only. No tests or gates were run by this reviewer. Root-retained focused evidence records `241 passed in 541.44s`; this review remains bounded activation evidence, not parent-milestone or release approval.

## Findings

### ACT-COR-001 — Old-binding recovery loses a concurrent successful activation

- Product priority: `P2`
- Approval disposition: `changes_required`
- Finding type: `runtime behavior / concurrency`
- Affected scenario: two equivalent explicit activation requests overlap, or a caller retries with the predecessor binding while the first caller commits between the retry's initial reload and its drain/CAS step. This is an important operational recovery path; ordinary ingestion remains unaffected.
- Evidence: `SemanticIngestionAtomicStore.activate_observation_ledger()` reloads only at `atomic_store.py:1175-1180` and at the start of each loop (`:1186-1191`). A winner may commit at `writer_admission.py:685-690` after the loser has seen the old admission. If the loser then enters `_begin_observation_ledger_drain()` or `_activate_observation_ledger()`, `require_current(expected)` at `writer_admission.py:696` or `:648` rejects the old binding. The caller converts that `SemanticWriterAdmissionError` directly to `PreplanningStoreError` at `atomic_store.py:1181-1184` or `:1216-1217`; it never rereads and verifies the now-complete trio. The existing lost-ACK test is sequential (`test_observation_ledger_activation.py:254-258`) and does not force this interleaving.
- Reproduction: pause a first caller immediately after its initial `_reload_observation_ledger_activation()` returns `None`; let a second caller activate successfully with the same predecessor binding; resume the first caller. It raises `PreplanningStoreError("observation ledger writer drain failed")` or `PreplanningStoreError("observation ledger activation transaction failed")` although the exact successor, activation, and head are durable.
- Required contract: the milestone requires repeated identical intent to return the same immutable activation (`milestones/activation.plan.md:41-42`) and explicitly assigns old-binding lost-ACK recovery to the predecessor metadata (`:202-207`); the target design likewise requires a completed lost-ACK retry to return the exact successor (`semantic_ingestion_activation_target.md:13`, `:95-97`).
- Smallest valid fix: when either pre-CAS writer operation reports a stale/mismatched admission, take a fresh detached write snapshot and call `_reload_observation_ledger_activation()` with the original expected binding. Return only an exact verified successor; otherwise preserve the original failure. Add forced winner-before-loser coverage for predecessor and current bindings, including the required persisted-backend race family.

### ACT-GOV-001 — The consumed production-binding artifact still describes the pre-cutover state

- Product priority: `Not applicable`
- Approval disposition: `changes_required`
- Finding type: `governance / integration evidence`
- Affected scenario: review and release-readiness consumers use the binding artifact to decide whether the protected provider entrypoint has a durable effect.
- Evidence: `production_entrypoint_bindings.json:156-163` says `protected_target_provider_path_locally_verified_cutover_unavailable`, reports that the atomic owner still raises before drain/write, and sets `durable_activation_implemented` to `false`. The frozen candidate instead implements `ProviderMemoryService.activate_observation_ledger()` through runtime, atomic store, writer admission, and a three-record conditional write (`provider/service.py:632-636`, `capability.py:187-198`, `atomic_store.py:1156-1219`, `writer_admission.py:635-691`). The governing target design deliberately makes that payload-free provider method the external trusted-host trigger and forbids automatic startup/configuration activation (`semantic_ingestion_activation_target.md:9`); no extra launcher is required by this contract.
- Reproduction: read the binding artifact and compare its stated unavailable outcome to the current candidate's bound source hashes and call chain. They disagree on whether the explicit trigger has a durable implementation.
- Smallest valid fix: refresh the activation entry in `production_entrypoint_bindings.json` against this frozen candidate: preserve `ProviderMemoryService.activate_observation_ledger()` as the explicit trigger, record the runtime authorization/target/binding checks and conditional trio effect, and update candidate-bound evidence coordinates. This is an evidence correction, not a new product behavior or parent closure.

## Bounded-Slice Approval

**Bounded-slice approval: changes required.** `ACT-COR-001` and `ACT-GOV-001` are determinate corrections. The activation candidate is not approved for this bounded slice until they are resolved and the frozen candidate/evidence is refreshed.

This does not close parent requirements R17/R19, the parent milestone, append/retrieval/checkpoint work, compatibility evidence, or release readiness.

## Correction Delta Review

- Candidate: `activation-evidence/correction-candidate.json` SHA-256 `8a826f6cc2052cdf2b293560890d888730b0f0984186536801f954cca6b3fb53`.
- Scope: only the ACT-COR-001 retry boundary, its focused public/JSONL tests, and ACT-GOV-001 evidence refresh. All candidate-listed source hashes matched at review time.
- Evidence inspected: root-retained `final-integration.log` and `activation-results.xml` record `24 passed in 218.82s`; correction Ruff, configured Pyright, and identity logs match the candidate. No tests or gates were run by this reviewer.

### ACT-COR-001 disposition: resolved

The corrected `atomic_store.py:1181-1234` puts drain inside the finite rescan loop, reloads an exact detached trio after a stale-admission failure at either writer seam, and continues only for a drain revision conflict that did not reveal a completed cutover. The two forced public JSONL interleavings at `test_observation_ledger_activation.py:346-375` cover a winner immediately before the losing drain and commit seam; `:548-568` covers a competing drain CAS. The correction preserves fail-closed behavior when the fresh snapshot cannot verify the exact successor.

### ACT-GOV-001 remains open

- Product priority: `Not applicable`
- Approval disposition: `changes_required`
- Finding type: `governance / integration evidence`
- Evidence: the corrected activation entry in `production_entrypoint_bindings.json:156-168` sets `durable_activation_implemented` to `true`, but its `outcome` still says the atomic owner "still raises transaction unavailable before drain/write." That statement contradicts the same entry's authority/effect chain and the candidate implementation. In addition, candidate-pinned `observation-ledger-tests/testing.plan.md:43-52` says final integration timing remains to be recorded and instructs the already-completed run/freeze as the next action, despite the retained 24-pass final log and XML.
- Smallest valid fix: state the successful conditional activation/genesis/successor effect and its fail-closed unavailable cases in the binding artifact; update the testing packet's recorded final result and next action, then refresh the correction candidate hashes.

**Bounded-slice approval: changes required.** The runtime correction is approved for the reviewed delta, but the current-evidence governance correction remains incomplete. This remains neither parent-milestone closure nor release approval.

## Evidence Reconciliation Delta

- Candidate: `activation-evidence/reconciled-candidate.json` SHA-256 `c816b608e6436ba42ae9a7ecfc95dba53d3e4d678ae37c21a9ae7c011597269b`.
- Scope: evidence-only reconciliation of ACT-GOV-001. Candidate-listed hashes match the current binding artifact, testing packet, runtime/test sources, workflow, and retained logs. No runtime or test code changed from the approved correction delta.

### ACT-GOV-001 disposition: resolved

`production_entrypoint_bindings.json` now describes the actual protected authorization, drain, detached inventory, and atomic successor-trio effect, including concurrent exact-trio recovery. `observation-ledger-tests/testing.plan.md` now records the retained `24 passed in 218.82s` result and names the bounded review reconciliation as its current action. These statements agree with the candidate-bound JUnit XML and final integration log.

**Bounded-slice approval: approved.** ACT-COR-001 and ACT-GOV-001 are resolved for the frozen reconciled activation delta. This approval covers only the stated activation correction scope; it does not close parent requirements R17/R19, append/retrieval/checkpoint work, CI execution, or release readiness.

## Final Evidence-Only Reconciliation

- Candidate: `activation-evidence/final-candidate.json` SHA-256 `41f423726e74930827a1b927e62b0e5ba093f6aeaa0fa018196c8ea9e67077b7`.
- Scope: the final status, proof, and remaining-work reconciliation only. Candidate-listed hashes match current files; no activation runtime, test, workflow, or retained-log identity changed from the approved correction delta.

No additional finding. The binding artifact now accurately records bounded local activation verification and names the still-open append/replay, checkpoint, retrieval, packaging, and CI obligations without implying parent closure.

**Bounded-slice approval: approved.** ACT-COR-001 and ACT-GOV-001 remain resolved for this final frozen evidence-only successor. This is not parent-milestone completion, CI approval, or release approval.
