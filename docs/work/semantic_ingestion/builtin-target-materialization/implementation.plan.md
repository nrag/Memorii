# Built-In Target Materialization Implementation

- Work ID: builtin_target_materialization_implementation
- Work type: implementation
- Status: under-review; implementation and complete parent-owned root matrix
  are green, with shared-candidate review pending
- Coordinator: Codex main thread
- Created: 2026-09-04
- Last updated: 2026-09-06
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/bootstrap-v3-source-progress-bridge-2026-09-04/implementation.plan.md`; `docs/work/semantic_ingestion/builtin-target-materialization/testing.plan.md`; `docs/work/semantic_ingestion/group-commit-storage-retry/debug-001.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md` Sections 4.8.2.17 through 4.8.2.20; `docs/design/memorii_spec.md`; `docs/design/memorii_storage_details.md`; `docs/design/event_model.md`; `docs/IMPLEMENTATION_RULES.md`
- Expected outputs: a real production built-in accepted entity-object fact path and revision-bound proof that ordinary competing ingestion triggers the native related-conflict successor

## Objective

Make a supported, fully evidenced entity-object fact reach accepted native V3
target materialization through `BootstrapGraphHostBundle` at the direct,
factory, filesystem, and Hermes roots. The resulting ordinary graph commit must
advance shared graph authority so a paused older ingestion observes the typed
group conflict and resumes its exact original fence once.

## Completion Contract

Complete only when production code constructs graph targets, canonical planning
records, a validated accepted reduction, and store-owned durable entity/fact
effects without fixture authority; unsupported or incomplete inputs remain
typed unresolved and write no graph effects; the actual four public roots pass
memory and independent JSONL first/reopen proof; the original-fence race records
two admissions, three group-CAS attempts, two accepted graph commits, nine
native progress checkpoints, and zero replay work after reopen; applicable
static, identity, selector, and transaction-boundary gates pass at one frozen
candidate; and independent specification, correctness, and test review leaves
no remaining P1/P2, `blocks_approval`, or `changes_required` finding.

## Scope

Included: the approved built-in planner path for evidence-complete entity-object
facts; source-wide canonical new-identity authority for their referenced
clusters; exact target bindings; deterministic entity, claim, projection,
optional relation, citation, provenance, and temporal planning records required
by that fact; reducer integration; planning-state fold; production-root
composition; focused and bridge acceptance proof; current binding/gate records.

Excluded: corrections, retractions, action-state and identity-operation accepted
materialization; semantic search; name-only identity reuse; generic compiler
reuse; provider API redesign; conflict-attention redesign; M5; unrelated
performance or storage work.

Deferred: the other four designed operation arms and full parent M3.1/M4
closure. Unsupported arms must retain the existing fail-closed unresolved
behavior.

## Constraints And Invariants

- A model proposal cannot directly create committed truth. Retained coverage,
  consensus, provenance, source-local identity, canonical allocation, target,
  planning and store validation remain separate stages.
- The planner is pure: no store, provider, clock, fixture, generic compiler or
  ambient graph access.
- Durable graph bytes and commit coordinates are materialized only inside the
  atomic group CAS.
- New identity allocation must be source-wide and deterministic. Missing or
  unresolved cluster proof remains `graph_target_missing` with zero effects.
- Existing native V3 generations remain the only progress/recovery authority.
- No public root may expose or use the scenario host/authority injection seam.
- Scope does not silently expand to another operation arm.

## Identity And Coordinate Hygiene

| Surface | Identity | Class | Owner/meaning | Disposition | Proof |
| --- | --- | --- | --- | --- | --- |
| planner implementation | `BuiltInBootstrapGraphTargetMaterializationPlannerV3` | behavioral | pure ordinary native target/materialization planner | retain and implement | identity-hygiene gate plus direct import/use search |
| accepted fact tests | behavioral scenario names only | behavioral | supported entity-object fact behavior | add | field-aware identity gate |
| WorkPlan IDs | values in this file only | planning/evidence coordinate | operation tracking | retain here only | repository search before closure |

## Change Impact And Verification Closure

| Path or pattern | Surface class | Scope owner | Authority chain | Required gates | Status |
| --- | --- | --- | --- | --- | --- |
| `memorii/memorii/core/memory_evolution/bootstrap_graph_planning.py` | product code | this WorkPlan | retained source authority -> canonical identity/target -> plan | focused planner/reducer tests, Ruff, Pyright | mapping |
| `memorii/memorii/core/semantic_ingestion/bootstrap_graph_builtin.py` | product code | this WorkPlan | production host acquisition -> planner/reducer -> checkpoint | four-root and race proof | mapping |
| `memorii/tests/unit/core/semantic_ingestion/` | tests/fixtures | linked testing WorkPlan | public roots -> real host -> atomic CAS/reopen | focused, selector, independent JSONL | mapping |
| transaction selector and binding ledgers | gate/generated evidence | this WorkPlan | test node -> selector -> required job/binding | validator/self-test/checksum owners | mapping |

## Evidence And Gate Ledger

- Baseline revision: `821b0bc7fd47ca0c55a18ccebb4b1628fa13689b` with a dirty coordinated M3.1/M4 candidate; existing changes are user/previous-operation work and must be preserved.
- Current failing discriminator: genuine direct production root produces two
  admissions, two CAS attempts, two unresolved group primary records, six
  progress checkpoints, zero accepted graph effects, and no graph revision
  advance because every built-in reduction is `graph_target_missing`.
- Required focused proof and workflow ownership will be finalized after the
  code-mapper and pre-implementation test review report.
- Evidence maturity: specified; partial contracts/projectors implemented;
  ordinary accepted fact path not implemented.

## v75 Authority Boundary

The required v75 planning-construction authority is not yet available from the
persisted normalization closure. This was verified directly in
`BootstrapV3SourceNormalizationStage.build_request` and
`_native_reduction_inputs` on 2026-09-04. `BootstrapNormalizationRequestCoreV3`
and every persisted `BootstrapNativeOperationReductionInputV3` retain only the
proposal, lane receipts, graph-free interpretation/alignment, payload-limit
authority, recovery key, coverage bindings, and the identity-specific
graph-free input. They do not retain any of the exact typed v75 sources:

- accepted operation governance and `MessageAdmissionIdentity` values;
- `SourceAuthorityEvidence` for evidence construction;
- a `PredicateTrustRule` for the proposed predicate;
- `AcceptedTemporalEvidence` with its `OperationTemporalDecisionBinding`;
- `CanonicalGraphRecordCodecEntry` values sealed for planning construction; or
- the identity authority record/verifier fields.

The live invocation has transient `source_authority_evidence`,
`source_interval_evidence`, and `policy_bundle`, but
`GraphFreeSourceNormalizationInvocation` declares them as untyped `BaseModel`
or `object` and `BootstrapV3SourceNormalizationInputs` does not receive or
persist them. The only sealed runtime policy is graph-dependent execution
policy; `CapabilityRegistrySnapshot` contains capability IDs/fingerprints, not
the missing predicate, temporal, admission, codec, or verifier authority.

Section 4.8.2.26 expressly forbids defaulting or recovering these values from
digests. The approved architecture already assigns normalization as the
construction owner, so the missing typed boundary is an implementation gap:
carry the existing concrete invocation, prepared-source, policy, temporal, and
codec sources into the sealed core and native operation input. For the bounded
nonidentity fact arm, `identity_construction` is required to be null.

The first pure projection is now present in
`source_normalization_stage._source_span_from_reference`: it derives
`SourceSpan(source_id, projection_span.start, projection_span.end)` only after
rechecking the retained source reference's projection/local length and artifact
join. It establishes that the v75 evidence/temporal span path is derivable; it
does not yet make an accepted fact path available.

The contract layer now has the complete planning-construction authority shape,
including governance, admission, predicate, action, codec, temporal, evidence,
and nullable identity construction subcontracts. The native input enforces that
a present authority is source/operation/group-bound and that nonidentity inputs
carry no identity construction. Backward decode remains nullable; the pending
normalization projector and built-in planner must require it for new accepted
fact work.

## Delegation And Cost Ledger

| Task | Role | Ownership | Rationale | Status |
| --- | --- | --- | --- | --- |
| production path and canonical helper map | `code-mapper` | read-only | establish exact binding and avoid duplicate planners | complete |
| pre-implementation validation matrix | `test_reviewer` | read-only | prevent fixture authority from satisfying production proof | complete |
| implementation slice | `worker` | sole writer | one coherent production/test/doc delta | active |
| final conformance/correctness/test review | three standard reviewers | read-only | required independent closure | pending |

## Decisions And Risks

- This is a separately bounded prerequisite, not an enlargement of the typed
  progress bridge.
- The narrow fact-only boundary is acceptable only if unsupported arms preserve
  their current typed unresolved result and the design does not require
  all-or-nothing activation of every arm. Readiness review must resolve this
  before coding.
- The greatest implementation risk is constructing apparently valid planning
  records from incomplete provenance or source-local identity. The planner must
  fail closed rather than default any semantic field.

## Readiness Result

- The production binding is one path shared by all public roots:
  `ProviderMemoryService` -> `BuiltInLocalHostSemanticIngestionCapability` ->
  `BootstrapGraphHostBundle` ->
  `build_builtin_bootstrap_graph_execution_v3` -> coordinator -> atomic group
  commit. Production graph authority injection is correctly unavailable.
- `BootstrapNativePlanningConstructionAuthorityV3` and its evidence, temporal,
  and identity construction subcontracts are absent from production contracts.
  The normalization owner therefore cannot persist the v75 field authority that
  the target planner is forbidden to infer or default.
- `BuiltInBootstrapGraphTargetMaterializationPlannerV3` exists only as the
  intentional unresolved implementation and is not called by the built-in
  compiler. `BootstrapNativeIdentityAdmissionPortV3` also has no production
  implementation, but the bounded fact path must keep identity-operation
  materialization unresolved and does not require that port.
- The approved design resolves the ownership decision: normalization must build
  and persist complete same-generation planning-construction authority inside
  each native operation input; the graph owner then projects canonical new
  identity authority, occurrence-bound targets, fact planning records, and a
  reducer result without ambient access. No new semantic decision is needed for
  the bounded fact path.
- Parent status remains partial. The ordinary planner's other operation arms
  are explicitly deferred and cannot be inferred complete from this slice.

## Prior Next Action (Completed)

Implement the typed normalization carrier for the bounded entity-object fact
arm, then use its sealed values to construct the pure target/materialization
plan and prove the direct production-root related-conflict race.

## Latest Diagnostic Evidence

- Reproduced the direct-root normalization failure with the publication catch
  temporarily re-raised. `BootstrapSourceNormalizationAtomicWriteRequestV3`
  rejected the stage's digest with `bootstrap V3 atomic request digest is
  invalid`.
- Cause: the stage derived `request_digest` from
  `canonical_contract_value(base)`, while the request validator uses
  `generation_request_digest(request)`, whose preimage is the typed request's
  `model_dump(..., exclude={"request_digest"})`. The two byte preimages differ.
- Corrected `BootstrapV3SourceNormalizationStage.build_request` to construct a
  provisional typed request and seal it with `generation_request_digest`; the
  normal publication `ValueError -> publication_conflict` catch was restored.
- Command: `PYTHONPATH=memorii .venv/bin/python -m pytest
  memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_root_composition.py
  -k 'builtin_native_graph and direct' -xq -p no:cacheprovider`.
  Result: normalization now succeeds; the direct root advances to the next
  existing gate, `graph_transaction_authority_unavailable`.

## Resolved Schema Blocker

- The native target request had a determinate join correction: its effective
  `GraphReadSet` now binds `sealed_snapshot.canonical_graph.read_set`, not the
  distinct transaction-level `GraphReadSetToken`. A foreign canonical graph
  read set remains rejected.
- The user authorized the narrow persisted schema completion. The fact path now
  carries the host-owned `PredicateStateRule` and `SourceAuthorityEvidence`,
  constructs `AcceptedClaimIdentity`, and obtains scope identity from the
  canonical identity authority. No nullable compatibility arm is used.
- Non-fact arms remain outside this bounded slice and retain typed zero-effect
  failure.

## Race Closure Evidence

- The earlier ordinary two-ingestion vector used byte-identical target writes;
  its third CAS attempt was caused by the obsolete global-revision conflict
  rule. It is now correctly classified as a no-false-successor proof: two CAS
  attempts and six ordinary progress checkpoints.
- A contradictory fact already committed through normal ingestion enters the
  conflict/clarification lifecycle before group CAS. The group-CAS successor
  proof therefore starts at the exact typed related-conflict emitted after that
  committed clarification makes an existing plan stale. The direct typed pair
  passes 2 tests in 127.84s and proves original-fence reuse with no readmission
  or renormalization.
- This closes only the direct race row. It does not complete this implementation
  WorkPlan, M3.1, or M4, and it does not substitute for the required public-root
  and JSONL reopen evidence.

## Exact Next Action

Freeze this bounded fact-path implementation with the shared M3.1/M4 candidate
and obtain exact-SHA hosted checks plus independent specification,
correctness, and test review; do not expand the fact-only scope.

## Active Schema And Persistence Evidence

- Authorized completion now carries the host-owned exact `PredicateStateRule`
  and `SourceAuthorityEvidence` in the native planning authority. The planner
  constructs `AcceptedClaimIdentity` with scope identity and lineage snapshot
  from canonical identity authority, rather than admission fingerprints.
- Canonical allocation persistence required three determinate corrections:
  sealed snapshot state/read-set joins, explicit governance bindings in the
  `GraphReadSetExtension` digest preimage, and codec registrations for the
  canonical identity authority/reload. Writer admission now validates its one
  exact canonical-identity authority record.
- Direct root construction and coordinator execution no longer throw. The
  coordinator returns a non-success result which the provider maps to the
  generic `graph_transaction_authority_unavailable` reason:
  `PYTHONPATH=memorii .venv/bin/python -m pytest memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_root_composition.py -k 'builtin_native_graph and direct' -xq -p no:cacheprovider` (1 failed, 41 deselected). No accepted effect or M3.1/M4 completion is claimed.

## Prior Safe-State Verification

- The direct built-in production root previously regressed because a partially
  constructed fact authority was serialized into an otherwise unresolved plan.
  Strict reload then rejected `SegmentGovernanceBinding.modality` after wire
  decode. Normalization now retains null planning authority until the full
  ClaimAssertion closure is persisted; this restores the existing durable
  unresolved compiler path.
- `PYTHONPATH=memorii .venv/bin/python -m pytest
  memorii/tests/unit/core/semantic_ingestion/test_bootstrap_graph_root_composition.py
  -k 'builtin_native_graph and direct' -xq -p no:cacheprovider`: passed
  (1 selected, 41 deselected), with the prior `source_only` behavior.
- `test_bootstrap_normalization_v3_grammar.py` and
  `test_source_normalization_authority_contracts.py`: 6 passed. Focused Ruff
  and `py_compile` passed for changed production modules.

## Superseding Resolution 2026-09-06

The complete parent-owned exact selector matrix subsequently passed all 232
public-root/backend cases, including direct, factory, filesystem, and Hermes
over memory and independent JSONL. The real public clarification race now
provides the missing target-aware overlapping-winner proof without a fixture
authority or a second source admission. Earlier pending-review and
non-success notes are preserved as history and no longer describe current
behavior.
