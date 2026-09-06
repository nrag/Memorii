# M0 Canonical Genesis And Structural Contract Correction

- Work ID: semantic-ingestion-m0-canonical-genesis-structural-contract-correction-2026-07-30
- Work type: design
- Status: complete
- Coordinator: Codex
- Created: 2026-07-30
- Last updated: 2026-07-31
- Parent WorkPlan: `docs/work/semantic_ingestion/m0-scenario-first-c2-implementation-2026-07-30/implementation.plan.md`; `docs/work/semantic_ingestion/m0-current-pin-c2-recipe-closure-2026-07-30/design.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/implementation.plan.md`
- Canonical inputs: `docs/design/memorii_spec.md`; `docs/design/memorii_storage_details.md`; `docs/design/event_model.md`; `docs/IMPLEMENTATION_RULES.md`; `docs/design/semantic_ingestion_architecture.md`; `docs/design/semantic_ingestion/scenario_first_fixture_authority.md`; `docs/design/semantic_ingestion/traceability_golden_vectors/ctv-binding-authority-v2.json`
- Expected outputs: approved typed genesis provenance contract, complete canonical structural-manifest derivation contract, compatibility rules, and implementation-ready verification matrix.

## Objective

Make M0 implementable without inventing genesis provenance or structural-manifest
bytes. A pre-lifecycle root must have a typed independently provisioned genesis
source; ordinary successors must remain lifecycle-rooted. Every field of the
normative structural body must have an authoritative source and domain-separated
canonical derivation.

## Completion Contract

- Requirements CGS-01 through CGS-12 have measurable acceptance criteria.
- The architecture defines typed variants, preimages, validation, migration,
  rollback, limits, and compatibility behavior for both boundaries.
- The authority file names all affected registered schemas/bindings consistently.
- The attack and verification matrices cover genesis substitution, lifecycle
  downgrade, structural-field omission/order/substitution, replay, and resource
  exhaustion.
- A fresh three-lane design review records no validated P1/P2 design defect,
  unresolved semantic authority, or remaining approval finding.

## Scope

Included: canonical design, scenario authority, CTV authority, WorkPlans, and
static design validation. Excluded: production code, tests, schema migration
implementation, release activation, and M1. Explicitly deferred: implementation
of the frozen contract, CTV consumer migration, historical recipe rebind or
migration, CI enforcement, and operational release issuance.

## Constraints And Invariants

- Candidate test authority never becomes default production trust.
- Unknown provenance variants, coordinates, fields, or enum values fail closed.
- Genesis is not represented by fabricated lifecycle coordinates.
- Structural graph bytes remain distinct from versioned belief/status overlays.
- Legacy six/seven-field projections are noncanonical and cannot authorize.

## Sources Of Truth

Precedence follows repository `AGENTS.md`: Memorii spec, storage details, event
model, implementation rules, then the semantic-ingestion architecture and frozen
authority. The parent plans record the two confirmed approval blockers.

## Current State

Completion-time verified facts (historical): the architecture, CTV authority,
29-field derivation ledger, attack matrix, and stdlib-only known-answer
prototype were checked in at this WorkPlan's completion identities. At that
time the CTV authority contained 56 schemas and 247 enum rows, and the CGS
checker verified the then-current known-answer vector. These are not current
gate identities. The current pins are owned by
`docs/work/semantic_ingestion/m0-lifecycle-root-genesis-signer-provenance-correction-2026-07-30/design.plan.md`
and `docs/development/static_tooling.md`.

Interpretation: these artifacts make the semantics and deterministic reference
inputs implementation-ready; they do not prove the production consumer,
transactional persistence, migration, CI integration, or independent runtime
implementation exists.

## Assumptions And Open Questions

- Verified facts: CGS-01 through CGS-12 are specified by the frozen artifacts
  and the final static checks in the Evidence Log.
- Working assumptions: the linked implementation operation can make the
  authority consumers conform without changing the approved semantics.
- Unresolved questions: deployment timing and operational release issuance are
  outside this design; they require their own approved activation inputs.
- Decisions requiring external input: none prevents this design approval. Any
  future change to provenance variants, canonical body bytes, or compatibility
  dispatch reopens design rather than being inferred during implementation.

## Problem Definition

The release/approval model has no legal value for pre-lifecycle BA/RR and RP
signer provenance, while structural-manifest construction lacks complete field
derivation. Implementations therefore either invent references or serialize a
legacy projection, both of which break fail-closed authorization.

## Requirements Ledger

| ID | Requirement | Source | Priority | Acceptance criteria | Status |
| --- | --- | --- | --- | --- | --- |
| CGS-01 | Genesis provenance is explicit and typed. | M0 blocker | P2 | Closed BA/RR union accepts only independent genesis or lifecycle successor. | approved design |
| CGS-02 | Ordinary successors retain lifecycle provenance. | lifecycle invariant | P2 | Validator rejects genesis after activation and successor before activation. | approved design |
| CGS-03 | RP signer uses correct provenance semantics. | M0 blocker | P2 | RP preimage contains only its closed provenance union. | approved design |
| CGS-04 | Structural body has a source for every field. | M0 blocker | P2 | Validator-owned 29-field ledger is complete and reconstructible. | approved design |
| CGS-05 | Structural collection ordering is canonical. | CTV invariant | P2 | All field orders and anchor-to-unit rule are explicit. | approved design |
| CGS-06 | Every derived digest is domain separated. | implementation rules | P2 | Ledger defines all digest domains and length-prefixed preimages. | approved design |
| CGS-07 | Outer structural artifact is independently reconstructible. | SIA-R03 | P2 | A/B compare complete body, envelope, and spool. | approved design |
| CGS-08 | Legacy projection cannot authorize. | compatibility | P2 | Diagnostic reader never dispatches authorization. | approved design |
| CGS-09 | Limits bound structural reconstruction. | operability | P2 | Numeric byte/count/depth/time/retry caps fail closed. | approved design |
| CGS-10 | Migration/rollback preserve auditability. | storage details | P2 | Corrected unshippable v2 decision and future version dispatch are explicit. | approved design |
| CGS-11 | Ledger and attack matrix are immutable authority. | review round 2 | P2 | Raw ledger SHA-256 pin is distinct from domain-derived `derivation_ledger_digest` and `derivation_ledger_coordinate`, and the checked-in matrix has required keys. | locally verified prototype; approved design |
| CGS-12 | Feasibility evidence does not overclaim independence. | build-design skill | P2 | Stdlib-only prototype verifies frozen 29-field vector; CTV A/B remains future evidence. | locally verified prototype; approved design |

## Non-Goals

This design does not define operational key enrollment, modify production trust
defaults, migrate stored artifacts, or begin M1.

## Existing-System Analysis

`verify_registered_approval_execution` validates typed release closure; the
current release coordinate schemas require lifecycle values for a state that
precedes lifecycle. `NormativeTraceabilityStructuralManifestBody` is named in
the architecture, but the existing verifier consumes a legacy byte wrapper.
The parent plans confirm A/B package and resolver evidence but block approval.

## Alternatives Considered

| Alternative | Decision | Rationale |
| --- | --- | --- |
| Null lifecycle coordinates | rejected | Ambiguous and weakens fail-closed decoding. |
| Reuse a fabricated genesis lifecycle record | rejected | Invents signed history and permits substitution. |
| Independent genesis provenance union | accepted | Carries audited provision source without claiming lifecycle state. |
| Continue legacy structural projection | rejected | Omits normative body fields and has no canonical preimage. |
| Define full field ledger and reconstruction | accepted | Enables independent deterministic derivation. |

## Feasibility Evidence

- Existing CTV v2 bindings support closed typed variants and signed preimages.
- Existing independent A/B closure work proves deterministic byte comparison is
  operationally feasible once complete operands are specified.
- The failed public gate is discriminating evidence that empty signer metadata
  and approximated structural bodies cannot pass the hardened boundary.

## Milestones Or Experiments

1. Define CGS genesis union and signer/root preimages; verify closure against
   existing lifecycle rules. Status: completed.
2. Define full structural field ledger, digest domains, reconstruction and
   limits. Status: completed.
3. Align scenario authority/CTV binding descriptions and run static validators.
   Status: completed.
4. Reconcile first review against the canonical contract and rerun static checks. Status: completed.
5. Run fresh three-lane design review. Status: completed.
6. Add immutable ledger/matrix authority and bounded feasibility prototype. Status: completed.

## Failure And Operational Analysis

Unknown variants, mixed-version artifacts, missing preimage operands, duplicate
or unsorted entries, oversized/deep expansion, replayed genesis records,
lifecycle-to-genesis downgrade, and rollback to a legacy projection reject
before authorization. Migration writes a new versioned artifact and retains old
history; rollback disables selection of the new version rather than deleting it.

## Verification Strategy

CGS-01..03: typed round trips and genesis/successor substitution tests.
CGS-04..07: independent reconstruction, mutation corpus, CTV/preimage checks.
CGS-08..10: mixed-version, replay, limits, migration/rollback, and watermark
nonmutation tests. Design validators must confirm authority identity/binding
closure after the frozen document changes.

## Attack Matrix

| Family | Invariant | Required rejection/evidence |
| --- | --- | --- |
| forged genesis | provenance union | mismatched independent provision digest |
| successor downgrade | lifecycle continuity | genesis variant after activation |
| coordinate substitution | signed preimage | signer/root coordinate mismatch |
| structural omission | complete body | absent field/entry/default |
| structural reorder | canonical order | unsorted/duplicate collection |
| digest collision/substitution | domain separation | wrong domain or referenced digest |
| resource exhaustion | bounded reconstruction | byte/count/depth limit |
| rollback/mixed version | compatibility | noncanonical legacy authorization |

## Progress Log

- 2026-07-30: created from two M0 approval blockers; next action is to draft
  the canonical architecture amendment.
- 2026-07-30: amended canonical models with explicit genesis/successor
  provenance unions and the full structural reconstruction contract; regenerated
  CTV authority after adding five closed enum rows.
- 2026-07-30: hermetic checker pins were reconciled for 245 enum rows and the
  new profile digest; first review is now the only remaining design milestone.
- 2026-07-30: review reconciliation corrected BA/RR and RP provenance ownership,
  version dispatch, migration/rollback behavior, the 29-field structural ledger,
  numeric C2 limits, and A/B independence requirements. The existing reference
  compiler rejects 245 enum rows because its stale 240-row assertion is outside
  this docs-only operation; the authority validator remains authoritative here.
- 2026-07-30: round 2 bound the raw ledger into the 29-field body, added the
  checked-in verification matrix, and ran a stdlib-only known-answer prototype.
- 2026-07-30: round 3 switched the persisted outer envelope to CTV-encoded
  `CanonicalEncodedArtifact.v1`, resolved all artifact digests from the ledger
  `outer_envelope` domain, separated raw ledger SHA-256 from the domain-derived
  `derivation_ledger_digest`/`derivation_ledger_coordinate`, and made CGS
  checker self-test mutations interruption-safe by operating only on copied
  artifacts.
- 2026-07-31: final spec, correctness, and test review lanes completed against
  CGS-01 through CGS-12. No lane identified a remaining approval finding; the
  design baseline is complete and implementation is delegated to the linked
  CGS implementation WorkPlan. Next action: none in this completed operation.

## Evidence Log

- Historical-identity note (2026-07-30): the 247-row CTV profile and
  `cd87dc705ae951ce9f9cef36bd267f8692340b58c16dd5321ee707087dc49b49`
  prototype-vector identity below are immutable completion-time evidence for
  this closed parent operation, not current gate identities. The linked
  `m0-lifecycle-root-genesis-signer-provenance-correction-2026-07-30` WorkPlan
  and `docs/development/static_tooling.md` exclusively publish the current
  249-row authority, semantic witness, matrix, checker, and vector identities.
- Parent M0 plans: confirmed blockers and verified implementation evidence.
- `semantic_ingestion_execution_evidence.py`: hardened closure exposes missing
  signer/preimage and structural operands through fail-closed errors.
- `validate_ctv_binding_authority_v2.py --write --self-test`: authority SHA-256
  `3c23aef413dc3b7cf9dc17fed4e5315c0104108a165e79bc700409aa1212f41c`,
  56 schemas, 247 enum rows, profile digest
  `c425fa6823f42fdd0d83ff444699bfd4c2b5fc9468812ff2b60c158a04ad254f`.
- Hermetic authority checker passed with design SHA-256
  `a8011f96255415d00a3cd09a1e6b7aa80d2d498c69ee822e3f7568641d33099a`,
  registry SHA-256
  `8e6395e2657eb1a51e5eef7d9b88b5d43b974a58f7f786ed135f6758262bfec1`,
  validator SHA-256
  `826541e7864583bbe3c32e3f153c008f07a881f33d38861237dfac80d9f3657e`,
  and checker SHA-256
  `a9a11df718be86dbc18f630e1b3089af68c638b9cb53b347d1927fa75069b157`.
- `python3.12 -m json.tool` accepted the structural derivation ledger and
  `git diff --check` passed.
- Historical completion-time CGS known-answer vector pins raw ledger SHA-256
  `085921e6c4e995f0d6259c9f6f6eabeec3f1455bba344105ef0e16d24eb81671`,
  domain-derived `derivation_ledger_digest`
  `3e15e60d3a89de6a9b11ab3996cd9c103aa76852f3660069bbc3fc70a63922de`, and
  `derivation_ledger_coordinate`
  `structural_manifest_derivation_ledger/TraceabilityStructuralManifestDerivationLedger.v1/1/3e15e60d3a89de6a9b11ab3996cd9c103aa76852f3660069bbc3fc70a63922de`.
- Pinned CGS checker and the stdlib prototype's known-answer verification
  passed; the checked-in prototype vector SHA-256 is
  `cd87dc705ae951ce9f9cef36bd267f8692340b58c16dd5321ee707087dc49b49`.
- Final CGS checker SHA-256 is
  `d6131aeeb30411902ecd92e728e908a27dd3728697e6d528a12a1ef5ec0e9571`;
  its pinned `--self-test` passed on 2026-07-31. It accepted the frozen vector
  and rejected domain-mapping, stale-legacy-field-WorkPlan, and outer-envelope
  mutations. The prototype SHA-256 is
  `8e8ef2e799abb906cd66abe243a7171d8c446133834d9ecf210ceaf63f81b117`.
- Historical completion-time CTV authority validator self-test passed with authority SHA-256
  `3c23aef413dc3b7cf9dc17fed4e5315c0104108a165e79bc700409aa1212f41c`,
  design SHA-256
  `a8011f96255415d00a3cd09a1e6b7aa80d2d498c69ee822e3f7568641d33099a`,
  registry SHA-256
  `8e6395e2657eb1a51e5eef7d9b88b5d43b974a58f7f786ed135f6758262bfec1`,
  validator SHA-256
  `826541e7864583bbe3c32e3f153c008f07a881f33d38861237dfac80d9f3657e`,
  checker SHA-256
  `a9a11df718be86dbc18f630e1b3089af68c638b9cb53b347d1927fa75069b157`,
  56 schemas, 247 enum rows, and profile digest
  `c425fa6823f42fdd0d83ff444699bfd4c2b5fc9468812ff2b60c158a04ad254f`.
- Final static hygiene: `git diff --check` exited 0 on the documentation
  candidate on 2026-07-31.
- Reference compiler parser run: rejected solely at its stale
  `enum registry must contain 240 rows` assertion although the current authority
  validator produces and validates 245 rows. No code change is authorized.
- Historical `validate_recipe.py --self-test` run rejected at its current
  `incompatible design hash` pin (`402090...` versus the corrected design). The
  recipe and its migration evidence are outside this correction's authority;
  retargeting them without regenerating the recipe would weaken the gate.

## Decision Log

- 2026-07-30: use a closed independently-provisioned genesis union rather than
  nullable/fabricated lifecycle coordinates.
- 2026-07-30: legacy structural projections are explicitly incompatible.
- 2026-07-30: correct unshippable CTV v2 in place because no durable/released
  artifact exists; block activation rather than reinterpret any discovered
  prior-profile artifact.

## Review Log

- Review round 1 reconciled: provenance ownership, genesis/successor legality,
  version dispatch, reconstruction field ledger, caps, and clean-room evidence
  requirements are now specified. Fresh review remains required.
- 2026-07-31 final three-lane review: `spec_auditor` checked complete CGS-01..12
  requirement coverage and source precedence; `correctness_reviewer` checked
  lifecycle, authorization, deterministic reconstruction, limits, migration,
  rollback, and A/B boundaries; `test_reviewer` checked measurable acceptance
  and the checked-in attack matrix. Findings: none remaining for approval.
  Coordinator disposition: no finding remains open. Product priority: Not
  applicable; approval disposition: follow_up for implementation-only evidence;
  finding type: verification and integration. Remediation eligibility:
  `record_only`; those items are explicitly owned by the linked implementation
  plan rather than this complete design operation.

## Blockers And Limits

- No design blocker remains. Four bounded design milestones and one final
  three-lane review were used; no implementation changes occurred in this
  operation.
- The reference compiler's stale 240-row assertion, historical recipe rebind,
  CTV consumer migration, CI enforcement, and operational release issuance are
  implementation or migration follow-up, not ambiguity in this design.
- Future implementation evidence must cover typed ledger generation closure,
  each 29-field mutation/order/reference/domain, body/envelope distinction,
  provenance variants, cap boundaries/timeouts/interruption, resolver/watermark/
  replay, migration/rollback, and clean-room full CTV body/envelope/spool output.

## Next Action

None. This design WorkPlan is complete; the linked implementation WorkPlan owns
the single next action for implementation.

## Outcome And Retrospective

Final result: CGS-01 through CGS-12 are an approved, explicit, typed canonical
genesis and 29-field structural-contract baseline. The final authority,
ledger, matrix, known-answer vector, and static check results are pinned in the
Evidence Log, and all three review lanes have no remaining approval finding.

Remaining limitations: no production consumer, migration execution, CI
enforcement, clean-room runtime implementation, or operational release has
been claimed. These are intentionally not evidence substitutes for the design.

Follow-up: `docs/work/semantic_ingestion/m0-canonical-genesis-structural-contract-implementation-2026-07-31/implementation.plan.md`
implements the approved baseline. A separate migration WorkPlan is required if
historical recipe data must be rebound or transformed.

Lesson: raw artifact identity, domain-derived identity, and deployment
evidence answer different questions. Keeping them separate made the canonical
bytes reviewable without misrepresenting a reference prototype as a production
or independent implementation.
