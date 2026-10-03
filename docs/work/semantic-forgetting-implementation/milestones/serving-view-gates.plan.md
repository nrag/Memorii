# Milestone: serving-view-gates

- Parent: docs/work/semantic-forgetting-implementation/implementation.plan.md
- Requirements: FGT-R2 (view core + provider gates), FGT-R4 (marking)
- Status: complete (slice 1, landed in c06de831)
- Base revision: 652387c1

## Delivered

- `RevokedIdentityView` + `RevokedIdentities` +
  `RevokedIdentityServingGate` protocol
  (core/storage_administration/revoked_identity_view.py): one derived,
  typed serving gate composed from the journal identities (immediately at
  apply) unioned with directive index-record identities (once the
  enforcement publication lands). Empty view = nothing revoked; internal
  integrity readers are never filtered (design §6.7).
- Injections (constructor param, default None = suppress nothing; the
  composition roots pass the real view): retrieval runtime (links before
  the lifecycle allowlist + claims by claim/entity identity),
  MemoryEvolutionService passthrough, ProviderMemoryService
  (scoped-context record filter, structured-facts snapshot filter,
  entity-match refusal for revoked entities), factory param, sidecar
  default-composes the view from control state for the harness envelope.
- Solver marking: HarnessStateService.read_state omits revoked
  justifications from candidate/committed hypotheses and forces
  revalidation_required when any revoked justification would have
  sponsored a conclusion; build_resume_envelope appends
  `justification_id:revoked_evidence` and forces the same status
  (mirrors the temporal walk).
- Tests: tests/unit/core/test_revoked_identity_view.py (journal
  derivation + record filtering; retrieval exclusion via the view;
  envelope + resume marking) green; blast radius green (94 unit across
  retrieval/harness/repository/dispatch/factory + 23 sidecar/resume
  integration); ruff clean; pyright 0 new errors.

## Deferred within the milestone

- R16 positive leg (owner forensic lineage surface returning retained
  lineage from version history) and the provider prefetch canonical
  channel record-filter land with the governance entry slice (M2),
  which writes the directive index records the view's second half
  consumes; recorded here, not silently dropped.
