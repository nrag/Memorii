# Semantic Ingestion Legacy-Path Removal Design WorkPlan

- Work type: `design` (substantial revision; `$build-design` process).
- Status: `active; user decision recorded, census complete, slice plan
  drafted; implementation not started`.
- Created: `2026-08-26`.
- Related operations:
  - `../semantic-ingestion-suite-reconciliation-2026-08-26/design.plan.md`
    (the 47-failure reconciliation whose ordinary-pipeline families are
    resolved by this removal)
  - `../semantic-ingestion-validated-canonical-closure-2026-08-17/implementation.plan.md`
    (the recovery repair round whose marker-keyed reconcile admission this
    removal simplifies)

## User Decision (2026-08-26)

The product is unreleased. Leave no legacy behind: remove the legacy
source-normalization/pipeline path entirely and ensure everything uses the
V3 path. This supersedes the A/B/C options recorded in the suite
reconciliation: the 26 ordinary-pipeline tests are resolved by removing the
dead path and re-anchoring the surviving security contracts to the V3
boundary.

## Census (2026-08-26)

Reachability established empirically (see the reconciliation WorkPlan):
`pipeline.run` — the only consumer of `SemanticIngestionPipeline` and the
egress policy provider — is unreachable except through a full legacy
normalization publication. Production surfaces carrying the legacy path:

1. `provider/ingestion.py`:
   - the ordinary nested path inside `ingest` (plan checkpointing, ordinary
     lease session, `_run_semantic_ingestion` with `bootstrap_handoff=None`)
     — dead since V3 handoffs always carry markers;
   - the legacy branches of `_run_semantic_ingestion` (claimed+legacy result
     at the `pipeline.run` near line 1984; found+legacy conditions near
     1822);
   - `reconcile`'s `execution_plan`-gated branch (plans are written only by
     the dead ordinary path).
2. `source_normalization_execution.py`: `SourceNormalizationExecutionOwner`
   instantiates BOTH `GraphFreeSourceNormalizationStage` (legacy) and
   `BootstrapV3SourceNormalizationStage` over one shared publisher; the
   legacy stage and its producers are the removable half.
3. `source_normalization_stage.py`: `GraphFreeSourceNormalizationStage`,
   `GraphFreeSourceNormalizationInputs`,
   `validate_reloaded_source_normalization_result`.
4. `contracts.py`: legacy `SourceNormalizationResult`, -`Request`,
   -`EvidenceManifest`, -`EvidenceEntry`, `SourceProposalAlignment`, and
   any consensus-tower types orphaned by the above. Per-type usage census
   required during implementation: some nested types
   (`CapabilityRegistrySnapshot` family, `SourceNormalizationPublicationCoordinate`)
   may be shared with V3 authority members.
5. `pipeline.py` + `egress.py` + `capability.py` + `provider/service.py`:
   `SemanticIngestionPipeline`, its transport/analyzer wiring, and the
   `egress_policy_provider` plumbing become dead once both `pipeline.run`
   sites are removed. `ProductionLocalSemanticAnalyzer` needs its own
   census: it is built into every runtime and may feed V3 lanes.
6. The egress security contract survives re-anchored: the authorization
   read-set binds `egress_policy_revision`/`egress_decision_digest`
   (`authorization.py:187-209`) and `ProviderEgressBinding`/`Decision`
   are signed contracts.

## Design Rules

- No compatibility shims, no deprecation aliases: delete.
- Every removed behavioral contract gets an explicit test disposition:
  re-targeted to the V3 boundary, or deleted with a recorded justification
  in this plan.
- The identity-hygiene allowlist entry pinning
  `test_semantic_pipeline.py`'s legacy rejection moves or dies with that
  test file; the gate must pass at every slice boundary.
- Slices land green: focused suites per slice; the full broad suite at the
  final revision (the suite-reconciliation operation's clean-suite goal is
  this operation's completion gate).
- The reconcile redesign lands here as the marker-keyed admission already
  agreed with the user (retained-state gate: marker + found index +
  loadable prepared source + current writer; scope from retained records),
  replacing the removed plan-gated branch.

## Slice Plan

1. Coordinator simplification: `ingest` keeps metadata-poor/ingress/empty
   gates, classification, and the V3 path; non-pending outcomes return
   directly. Remove the ordinary nested path. Focused: composition +
   coordinator suites.
2. `_run_semantic_ingestion` becomes V3-only (legacy branches removed;
   legacy result types rejected as foreign). Reconcile becomes
   marker-keyed (recovery repair convergence). Focused: recovery proofs +
   replay/reopen.
3. Execution owner and stage: drop the legacy stage/producers; V3 stage
   only. Focused: normalization repository/stage tests migrated.
4. Contract deletions with per-type orphan census (contracts.py +
   semantic_analysis decision_contracts where V3 shares nothing).
   Identity-hygiene allowlist updated. Focused: contracts unit suites.
5. Pipeline/egress removal from runtime composition and service plumbing;
   re-anchor the egress mutation tests (18) to the authorization read-set
   boundary; delete or migrate pipeline-specific tests. Focused: egress +
   authorization suites.
6. Test reconciliation completion for the remaining V3-era families (the
   suite-reconciliation operation's list), full broad gate, WorkPlan
   closures.

## Next Action

Confirm this plan (or amend slices), then execute slice 1.
