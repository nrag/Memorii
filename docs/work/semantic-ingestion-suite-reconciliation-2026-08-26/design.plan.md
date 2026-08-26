# Semantic Ingestion Test-Suite Reconciliation WorkPlan

- Work type: `debugging` (test-contract reconciliation; `$debug-problem`
  process, `$design-tests` skills apply to the fixture architecture).
- Status: `active; root cause pinned, repair architecture partially
  validated, fixture construction in progress`.
- Created: `2026-08-26`.
- Coordinator: sole writer.
- Parent context: the validated-canonical-closure implementation
  (`docs/work/semantic-ingestion-validated-canonical-closure-2026-08-17/implementation.plan.md`)
  classified these failures for a dedicated operation after verifying they
  are not regressions of that branch.
- User decision (2026-08-26): a clean suite is required; these tests broke
  during the M3.1-era work and must be restored against the current
  contracts.

## Objective

Restore the 47 failing pre-existing tests (43 in
`test_semantic_provider_composition.py`, 4 in
`test_bootstrap_graph_coordinator_v3.py`) as a clean suite without weakening
any validation, schema, or selection gate.

## Root Cause (pinned by bisection, 2026-08-26)

Bisection over branch history (worktree runs of
`test_public_coordinator_rejects_every_egress_authority_mutation_without_wire[tenant_id]`):

| Revision | Result |
| --- | --- |
| `2a7a55e` (pre-branch M3 merge) | pass (8.6s) |
| `bdc7dc9` (partial M4) | pass |
| `21b1c26` | pass |
| `4691c03` ("Fix the M3 gaps") | broken commit: syntax error in `contracts.py:1556`; not a valid comparison point |
| `eb70c9d` ("Fix the things left in M3...") | FAIL — the breaking change |
| `b9daf00`..HEAD | FAIL (verified unrelated to the closure branch's changes by file isolation) |

`eb70c9d` introduced the V3 source-normalization machinery (8,130 insertions)
and changed the ingestion contract in three specific ways:

1. **Pending-only processing.** In `ProviderIngestionCoordinator.ingest`,
   only sources classified `selected_pipeline_pending` (exact grammar-corpus
   literal matches with trusted language evidence) receive any pipeline
   processing. Every other classification (`unsupported_input`, `abstained`,
   `disabled`, `unavailable`) is admitted and retained but returns
   `source_only` at the fall-through (ingestion.py:942) with no preplanning
   control and no pipeline run. Corpus literals: see `_bootstrap_cases()`
   ("Atlas owner is Bob.", "Receipt is confirmed.").
2. **Normalization-bundle gate.** `_run_semantic_ingestion` requires
   `runtime.source_normalization_host_bundle` (the line-1583 gate:
   `bootstrap_handoff is None or host_bundle is None` →
   `source_alignment_authority_unavailable`). Hand-built minimal
   `AuthorizedSemanticIngestionRuntime`s (pipeline/policy/egress/assessor
   only) fail here and never reach `pipeline.run`.
3. **Pipeline reached via a validated normalization result.** After the
   normalization authority/owner round trip: a legacy
   `SourceNormalizationResult` continues to `pipeline.run` (where the egress
   policy boundary lives); a `BootstrapSourceNormalizationResultV3` routes
   to the graph flow. Both pass through
   `validate_reloaded_source_normalization_result` /
   `validate_reloaded_bootstrap_v3_source_normalization_result`, which bind
   the result to the prepared source, fence, and publication coordinate.

The failing tests encode the pre-`eb70c9d` contract (any admitted source →
ordinary pipeline → egress boundary) and were never migrated. Off-corpus
content is NOT a repair: non-pending sources never pipeline-process.

## Repair Architecture (validated 2026-08-26 up to the recovery-claim boundary)

For the ordinary-pipeline families (egress ×18, local analyzer, accepted
control, stops-before-owner, untyped normalization ×2, hermes
clarification ×3, and related):

1. Build the runtime via `build_authorized_local_semantic_runtime(...)`
   then `replace(runtime, pipeline=..., egress_policy_provider=...,
   candidate_assessor=..., source_normalization_host_bundle=...)` —
   pattern proven by `_LocalRuntimeCapability`.
2. `SourceNormalizationHostBundle` requires `authority_provider`,
   `execution_owner`, `recovery_repository=
   AtomicStoreBootstrapRecoveryClaimRepository(atomic_store=store)`, and
   `trusted_time=InjectedSourceNormalizationTrustedTime(...)`.
3. The authority provider returns an object exposing
   `.publication.publication_coordinate` (a real
   `SourceNormalizationPublicationCoordinate.create(...)` bound to the
   marker fence and prepared-source fingerprint); the execution owner
   returns a real legacy `SourceNormalizationResult` built from the loaded
   prepared source. Every nested contract
   (`SourceProposalAlignment`, `SourceLocalIdentityResolution`,
   `ProposalCoverageAudit`, `SourceNormalizationEvidenceManifest`,
   `CoveredPredicateEvent`) has a working `create()`; a scratch prototype
   constructed all of them successfully against their validators.
4. **Open seam (next step):** the stretch of `_run_semantic_ingestion`
   between the prepared-source load and the authority/owner calls performs
   a recovery claim through `recovery_repository` (probe / renew_or_abort
   over the V3 recovery index). Its fixture requirements are mapped but not
   yet exercised end to end; the prototype stopped exactly at
   `SourceNormalizationHostBundle.__init__` argument completion.

For the V3-era families (lost-ack ×3, recovery-authority-change ×3,
redelivery-after-rotation, reload-bootstrap, frozen-wire,
reconcile-exhaustion, and the coordinator module's graph-terminal and
corruption-reopen 4): repair by completing their fixtures against the
current V3 flow, reusing the proven
`_v3_normalization_host_builder(proposal=...)` + graph-bundle patterns from
the now-passing recovery/family proofs in
`test_bootstrap_graph_coordinator_v3.py`.

## Rules

- Do not weaken validators, schemas, classification, or gates to make
  tests pass; migrate fixtures to the current contracts.
- Tests whose subject no longer exists as product behavior must be
  re-decided explicitly (rewrite against the V3 contract or delete with a
  recorded justification), never silently skipped.
- Each family lands with its focused proof green before moving on; the full
  broad suite runs once at the frozen final revision.

## Evidence Log

- 2026-08-26: bisection table above (worktree `/tmp/memorii-hist`).
- 2026-08-26: off-corpus repair disproven (classification
  `unsupported_input/unsupported_grammar` → admitted, `source_only`, no
  control — pending-only processing confirmed).
- 2026-08-26: full-runtime repair advanced past StopIteration (control
  created) and stopped at empty terminals because the minimal runtime had
  no normalization bundle (alignment-unavailable early return).
- 2026-08-26: scratch prototype built every legacy normalization contract
  via `create()`; blocked only on completing the host-bundle arguments
  (recovery repository and trusted time wired but the recovery-claim
  stretch not yet exercised).

## Next Action

Complete the scratch prototype's `SourceNormalizationHostBundle` (wire
`AtomicStoreBootstrapRecoveryClaimRepository` and
`InjectedSourceNormalizationTrustedTime`), drive one egress case to
`pipeline.run`, then promote the prototype into a shared fixture helper in
the composition module and repair the ordinary-pipeline families with it.
