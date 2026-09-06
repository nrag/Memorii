# Bootstrap V3 Recovery Renewal Debug

- Work ID: bootstrap-v3-recovery-renewal-2026-08-10
- Work type: debugging
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-08-10
- Last updated: 2026-08-10
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md`; `docs/design/memorii_storage_details.md`; `memorii/core/memory_evolution/atomic_store.py`; `memorii/core/memory_evolution/writer_admission.py`
- Expected outputs: exact sequential bootstrap-V3 recovery-renewal admission invariant, deterministic regression proof, and an updated M3 boundary note.

## Objective

Allow a valid, CAS-preconditioned bootstrap V3 recovery claim to renew
sequentially through its bounded counter, while rejecting replay, skipped
counter, foreign nonce, mixed-record, and substituted key/fence/generation
updates.

## Completion Contract

The recovery-renewal causal hypothesis is either confirmed and corrected with
the stated proof, or disproved by an exact discriminating trace and handed
back to M3 with the next concrete blocker. This debug slice does not complete
the parent V3 root acceptance criterion.

## Scope

Included: recovery index CAS, writer-admission validation, focused unit tests,
and the public-root reproducer. Excluded: changing V3 payload schemas,
authority routing, generic V2 reservation semantics, or broad persistence
redesign.

## Expected And Observed Behavior

- Expected: every valid renewal is an isolated update of one retained recovery
  index record, advances its counter by exactly one, preserves recovery
  identity and claim nonce, and is protected by the atomic-store record digest
  precondition.
- Observed: direct `ProviderMemoryService.sync_event` reaches proposal and
  stanza but fails before spacy. The recovery record advances through count 4,
  then an admission `ValueError` is converted to V3 fail-closed noncommit.
- Classification: implementation defect. Reproducibility: deterministic.

## Reproducer

`.venv/bin/pytest memorii/tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py -k direct_provider_root_publishes_and_reloads_bootstrap_v3_normalization -q`

Expected: proposal and all four lanes execute once and V3 publication reloads.
Actual before this debug fix: proposal=1, stanza=1, spacy=0, recovery count=4,
and `source_alignment_authority_unavailable`.

## Hypothesis Ledger

| ID | Hypothesis | Evidence | Discriminating experiment | Status |
| --- | --- | --- | --- | --- |
| H1 | The admission predicate rejects a valid claimed-to-claimed successor because persisted times are JSON strings while a new claim has different representation. | Direct trace records four consecutive `BootstrapRecoveryRenewedV3` results, counters 0 through 3. | Trace the recovery repository during the public root reproduction. | disproved |
| H2 | Atomic renewal computes an invalid claim digest or counter transition. | The same trace shows each CAS result is typed renewed; no `ValueError` is raised. | Trace the recovery repository during the public root reproduction. | disproved |
| H3 | CAS membership/current-record lookup is unstable after the first update. | Four exact sequential successor writes succeed against the persisted record. | Trace the recovery repository during the public root reproduction. | disproved |

## Experiments And Evidence

- E1 (before debug): direct root repro reaches proposal and stanza only; recovery count is 4.
- E2: repository instrumentation captured renewals 0, 1, 2, and 3, all
  returning `BootstrapRecoveryRenewedV3`. H1--H3 are disproved.
- E3: direct invocation of the stanza fixture lane raised `LinguisticAnalysis`
  validation because an empty `complete` analysis cannot form the required
  rooted dependency tree. The fixture now returns one syntactic token and its
  root arc. The repro reaches proposal plus all four lane calls and recovery
  count 9.
- E4: the native owner returns `BootstrapSourceNormalizationResultV3`, but
  coordinator validation accepts only generic `SourceNormalizationResult`.
  The coordinator therefore fails closed before V3 publication/reload. This is
  the next M3 implementation blocker, outside the recovery-renewal hypothesis.

## Changed-Surface And Authority Chain

- `SemanticIngestionAtomicStore.renew_or_abort_bootstrap_v3_recovery` creates the successor and owns CAS.
- `SemanticWriterAdmissionPolicy.validate` delegates isolated recovery-index writes to `_is_bootstrap_v3_recovery_claim_write`.
- `SourceNormalizationExecutionOwner._renew` maps an admission failure to a V3 noncommit.
- The production caller is `ProviderMemoryService.sync_event` through `ProviderIngestionCoordinator`.

## Exact Next Action

Completed: the repeated-renewal hypothesis was disproved. M3 must correct the
native V3 result validation and pipeline handoff before resuming its public
root proof.
