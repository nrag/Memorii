# M0 Lifecycle-Root Genesis Signer-Provenance Correction

- Work ID: semantic-ingestion-m0-lifecycle-root-genesis-signer-provenance-correction-2026-07-30
- Work type: design
- Status: complete
- Coordinator: Codex
- Created: 2026-07-30
- Last updated: 2026-07-31
- Parent WorkPlan: `docs/work/semantic_ingestion/m0-canonical-genesis-structural-contract-correction-2026-07-30/design.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/m0-canonical-genesis-structural-contract-implementation-2026-07-31/implementation.plan.md`
- Canonical inputs: `AGENTS.md`; `.agent/PLANS.md`; `.agent/skills/build-design/SKILL.md`; `docs/design/semantic_ingestion_architecture.md`; `docs/design/semantic_ingestion/traceability_golden_vectors/ctv-binding-authority-v2.json`; `validate_ctv_binding_authority_v2.py`; `check_ctv_binding_authority_v2.py`; `check_cgs_structural_contract_v1.py`; `structural_manifest_derivation_ledger-v1.json`; `cgs_verification_attack_matrix-v1.json`; `lifecycle-root-signer-provenance-witness-v1.json`; `validate_lifecycle_root_signer_provenance_v1.py`; `check_lifecycle_root_signer_provenance_v1.py`
- Expected outputs: one owner-specific closed lifecycle-root signer-provenance union; matching architecture and CTV authority; a dependency-free semantic witness/validator/checker; hermetic checker pins and mutation evidence.

## Objective

Resolve the lifecycle-root sequence-one contradiction without broadening the generic signer coordinate: the first signed lifecycle root can be attested by the independently provisioned bootstrap anchor, while every successor remains rooted only in a prior verified lifecycle root.

## Completion Contract

- LRG-01 through LRG-05 have stable, measurable acceptance criteria.
- The architecture, CTV authority, checker pins, and CGS matrix specify exactly the same owner-specific closed union and legality rules.
- Hermetic CTV authority and CGS checks accept the frozen correction and reject the documented genesis/successor mutation family.
- No production module, generic `TraceabilitySignerCoordinate`, RP contract, or M1 artifact changes.
- A clean three-lane independent review hands the approved baseline back to the
  active M0 implementation lifecycle replay.
- A design-owned witness executes both legal lifecycle-root variants and every
  field, owner, sequence, binding, and historical-reference negative required by
  LRG-05.

## Scope

Included: lifecycle-root envelope signer coordinates and lifecycle-root signature preimage only; their CTV schemas, authority/checker pins, and frozen attack matrix. Excluded: production implementation, generic signer-coordinate semantics, BA/RR/RP provenance, lifecycle-record signer bindings, structural ledger semantics, persistence, migration execution, release activation, and M1. Explicitly deferred: production consumer implementation and all integration tests beyond design-artifact hermetic checks.

## Constraints And Invariants

- `TraceabilitySignerCoordinate` remains prior-verified-lifecycle-root-only.
- `TraceabilityLifecycleRootGenesisSignerProvenance` is legal only at sequence one of `TraceabilityTrustLifecycleRoot.signer_coordinates` and its matching root signature preimage.
- The genesis variant identifies an independently provisioned bootstrap anchor; it never carries a lifecycle root or record coordinate.
- The existing coordinate remains the only legal successor variant; sequence two and later cannot downgrade to the genesis variant.
- Unknown tags, mixed fields, wrong purpose, root/record self-reference, candidate-held authority, and signature/preimage mismatch fail closed before signature verification or state publication.

## Sources Of Truth

Precedence is `AGENTS.md`: Memorii spec, storage details, event model, implementation rules, the semantic-ingestion architecture, then frozen design artifacts. The completed parent design is the baseline; the active M0 implementation plan provides the confirmed contradiction and does not redefine the correction.

## Current State

Verified fact: the pre-correction lifecycle-root envelope and preimage used the
prior-root-only generic coordinate, making sequence one unrepresentable. The
current architecture and CTV authority now use the owner-specific closed union;
the dependency-free witness accepts the sequence-one genesis and sequence-two
successor and rejects all 33 required root mutations plus four malformed
historical-coordinate mutations. Successor evidence now binds
the verified-history authority, exact final-action signer coordinate, and
issuance-time containment; the checker pins its own bytes and requires isolated
execution. Eight persisted interval-boundary witnesses additionally prove that
both genesis and successor accept either inclusive endpoint and reject one
microsecond outside it. One shared strict validator checks both successor and
historical authorized coordinates before equality. Independent three-lane
review found no remaining strict finding. This is approved design evidence,
not production implementation evidence.

## Assumptions And Open Questions

- Verified facts: the frozen CTV authority derives schemas from the architecture and the current CGS checker pins design, ledger, matrix, prototype, and vector identities.
- Working assumptions: no published corrected-v2 lifecycle-root envelope exists; the existing corrected-v2-before-publication rule permits an in-place design correction.
- Unresolved questions: none within this bounded correction.
- Decisions requiring external input: none. Broader signer-coordinate or RP changes require a separate design operation.

## Problem Definition

The lifecycle-root verifier must validate an ordinary sequence-one genesis root, but its envelope and signature preimage only accept a signer that names a prior root and terminal record. Fabricating those coordinates violates the append-only and independently-provisioned genesis invariants; rejecting every genesis root leaves lifecycle activation unavailable.

## Requirements Ledger

| ID | Requirement | Source | Priority | Acceptance criteria | Status |
| --- | --- | --- | --- | --- | --- |
| LRG-01 | Define the closed root-owner union. | confirmed M0 contradiction | P2 | Only `TraceabilityLifecycleRootGenesisSignerProvenance` or `TraceabilitySignerCoordinate` decodes at lifecycle-root envelope/preimage owners. | locally verified |
| LRG-02 | Bind the independent bootstrap source exactly. | SIA-ED-TRACEABILITY-001 | P2 | Genesis carries purpose, authority/channel, exact bootstrap anchor, issuer/key/profile, and eligibility interval; no lifecycle root/record fields decode. | locally verified |
| LRG-03 | Enforce sequence legality. | lifecycle append-only invariant | P2 | Genesis is accepted only for sequence one; successors require the existing prior-root coordinate. | locally verified |
| LRG-04 | Preserve exact signature binding. | Section 3.23.4 | P2 | The complete union value is in the lifecycle-root signature preimage and must equal the envelope coordinate. | locally verified |
| LRG-05 | Freeze rejection coverage. | build-design verification contract | P2 | Authority/CGS checks reject mixed fields, wrong owner/purpose, sequence-one successor, and sequence-two genesis downgrade. | locally verified |

## Non-Goals

This operation does not implement verification, alter generic signer metadata, make RP use the new type, alter lifecycle-record eligibility, publish a release, or claim production evidence.

## Existing-System Analysis

The architecture's generic coordinate is intentionally a successor-only historical lookup. RP already demonstrates an owner-specific bootstrap-anchor union, but its purpose and owner are RP-only. The CTV validator extracts the architecture's typed declarations into frozen authority schemas; the hermetic checker pins the source identities. The CGS matrix and semantic witness carry one exact lifecycle-root negative inventory; the active second-round correction expands it from 22 to 29 cases.

## Alternatives Considered

| Approach | Advantages | Risks | Decision |
| --- | --- | --- | --- |
| Add genesis to `TraceabilitySignerCoordinate` | Fewer types | Broadens every signer owner and permits provenance leakage. | rejected |
| Reuse RP genesis signer provenance | Similar fields | Wrong purpose/owner; couples two independent authorization rules. | rejected |
| Allow nullable/fabricated prior root coordinates | Small schema diff | Invents history and weakens replay verification. | rejected |
| Add lifecycle-root-only closed union | Preserves existing successor contract and binds independent bootstrap anchor. | Requires matching authority regeneration. | accepted |

## Feasibility Evidence

The validator already derives nested closed unions from the architecture and the parent correction used this pattern for RP. The CTV self-test and CGS checker provide deterministic source-mutation checks; no production feasibility claim is made.

## Failure And Operational Analysis

Typed decode rejects unknown/mixed variants. Verification first checks the root sequence and selected variant, recomputes the root digest, resolves either the independently provisioned bootstrap anchor or the prior verified lifecycle view, then compares purpose/authority/channel/anchor/key/profile/interval and only then invokes the signature verifier. A failed lookup or mismatch does not advance lifecycle, release, pointer, or watermark state. Pre-publication v2 correction remains fail-closed for legacy or mixed artifacts; rollback never creates an alternate genesis history.

## Milestones Or Experiments

1. **Freeze owner-specific contract.** Purpose: amend architecture and CTV schema source. Scope: LRG-01..04 only. Expected artifacts: root-genesis type, union aliases, exact legality/preimage/verification text. Verification: source inspection and validator generation. Status: complete.
2. **Freeze evidence artifacts.** Purpose: regenerate authority and update pins/matrix. Scope: LRG-05 only. Expected artifacts: authority, checker expected identities, lifecycle-root mutation cases. Verification: hermetic CTV and CGS commands. Status: complete.
3. **Close executable semantic evidence.** Purpose: execute the lifecycle-root
   genesis/successor state machine independently of production code. Scope:
   witness fixture, stdlib validator/checker, explicit matrix rows, and current
   published identity reconciliation. Expected artifacts: two accepted roots,
   complete negative corpus, hermetic semantic gate. Verification: CTV, CGS,
   semantic checker self-tests and diff check. Status: complete.

## Verification Strategy

LRG-01..04 use architecture/CTV schema inspection plus the hermetic authority checker. LRG-05 uses matrix presence/schema validation, authority mutation self-test, and CGS self-test. These establish specified and locally verified design evidence only; production lifecycle verification remains deferred.

## Progress Log

- 2026-07-30: created as a linked design correction after a confirmed P2 lifecycle-root genesis signer-provenance contradiction. Evidence: architecture root envelope/preimage currently embed the prior-root-only generic coordinate. Next action: freeze the owner-specific contract.
- 2026-07-30: defined `TraceabilityLifecycleRootGenesisSignerProvenance` and
  `TraceabilityLifecycleRootSignerProvenance`; only the lifecycle-root envelope
  and preimage use the union. Architecture legality requires the independently
  provisioned bootstrap-anchor variant at sequence one and the existing
  prior-root coordinate thereafter. The generic coordinate and RP remain
  unchanged. Next action: regenerate frozen authority and derived artifacts.
- 2026-07-30: regenerated the CTV authority (56 schemas, 249 enum rows),
  structural known-answer vector, and all necessary CTV/CGS pins. The CTV
  hermetic checker and CGS checker self-test exited 0. Next action: independent
  review.
- 2026-07-30: resolved the review evidence action with a dependency-free
  witness, semantic validator, and hermetic checker. Two positive roots and 22
  negatives execute across two isolated replicas. Updated the matrix, CTV/CGS
  authority cascade, static workflow, current implementation WorkPlan, and
  completion-time historical labels. CTV, CGS, and semantic gates exited 0.
  Next action: independent review.
- 2026-07-31: reopened after second-round review confirmed that successor
  witness history did not prove authority equality or exact final-action signer
  authorization, and that the semantic checker did not pin its own bytes or
  reject non-isolated invocation. Added a seven-case successor mutation family
  and began checker hardening. Next action: regenerate identities and execute
  all hermetic gates.
- 2026-07-31: completed second-round evidence remediation. Regenerated the CTV
  authority and structural vector, reconciled all design/checker/workflow/test
  pins, and passed the CTV, CGS, and 29-case lifecycle-root semantic gates.
  Next action: independent three-lane review.
- 2026-07-31: completed final interval-boundary evidence remediation. Persisted
  and executed eight genesis/successor boundary witnesses, regenerated the full
  identity cascade, and passed all hermetic and focused gates with six accepted
  and 33 rejected witnesses. Next action: independent three-lane review.
- 2026-07-31: completed strict-verifier remediation. Added one shared structural
  validator before equality, persisted eight malformed presented/history
  coordinate cases, regenerated every bound identity, and passed the complete
  gate set with six accepted and 41 rejected witnesses. Next action:
  independent three-lane review.
- 2026-07-31: independent `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer` review completed with no remaining strict finding. The
  coordinator accepted the final design and evidence state. Next action:
  resume the active M0 implementation lifecycle replay.

## Evidence Log

- Pre-correction evidence: `TraceabilitySignerCoordinate` was and remains
  `prior_verified_lifecycle_root` only; the old lifecycle-root preimage and
  envelope used it directly, creating the genesis contradiction.
- Current design evidence: `TraceabilityTrustLifecycleRootSignaturePreimage`
  and `TraceabilityTrustLifecycleRoot` use only
  `TraceabilityLifecycleRootSignerProvenance`, while lifecycle sequence one is
  bootstrap-provisioned with no prior root/record.
- Frozen CTV authority: authority SHA-256
  `c119345548166fd99e7aefe963d62a9b73e6c98c7cac84b7d6f8759b2ceb5633`,
  profile digest `9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f`,
  56 schemas, and 249 enum rows.
- Frozen CGS artifacts: design SHA-256
  `70ace2b99c4db79911f45555f72cde43278ccaac69c1fc11530e2d474f1fa26c`;
  matrix SHA-256
  `a3375bd0d8d01cf7a7c9d7d16d90945d792d932eca7161097f6ee5ba44d3f604`;
  prototype SHA-256
  `b28c681d60faa10f31d4e9a5e0e15c442554ac6b35d5198ff7e67c1ec051434c`;
  known-answer vector SHA-256
  `b5a4d9fb6e4f7d7c7222a8541abd30c092c6fc54d363c66ac5a324e036d6f0a3`;
  CGS checker SHA-256
  `026c9495e6fe732e57f4703f421b4b11420ee8cae4f8e268ed8974a4d7d0056c`.
- Lifecycle-root semantic artifacts: witness SHA-256
  `d3c1dce10624365647cbb00926f63b6deabe681e51a138bc3de88d7c60faef69`,
  validator SHA-256
  `46bbda1afb6ccbec5a49ea668752c19a7b1354b94515a33365191cee01745edb`,
  and checker SHA-256
  `8c219ad322277abfe5e969a2153eaf050971187af619713b3f4ffb58dd942038`.
- The hermetic CTV checker exited 0 with the pinned authority and reports 56
  schemas, 249 enum rows, and two identical isolated replicas. The CGS checker
  self-test exited 0 and rejected its domain mapping, stale 25-field WorkPlan,
  and outer-envelope mutations.
- The semantic checker self-test exited 0 with exactly six accepted and 41
  rejected witnesses across two identical isolated replicas. It executed both
  inclusive endpoints and both one-microsecond-outside rejections for genesis
  and successor, and rejected a mutated accepted-genesis witness, deleted
  boundary witness, deleted matrix witness row, checker identity drift, and
  non-isolated invocation.
- Strict-verifier final gates: CTV exited 0 with 56 schemas, 249 enum rows, and
  two replicas; CGS `--self-test` exited 0; lifecycle-root semantic
  `--self-test` exited 0 with 6 accepted/41 rejected/2 replicas. The focused
  PR-gate suite passed 19 tests, Ruff passed, workflow YAML parsed, and
  `git diff --check` exited 0.
- Boundary-evidence completion gates (historical, superseded by the strict
  verifier evidence above): CTV exited 0 with 56 schemas, 249 enum rows,
  and two replicas; CGS `--self-test` exited 0; lifecycle-root semantic
  `--self-test` exited 0 with 6 accepted/33 rejected/2 replicas. The focused
  PR-gate suite passed 19 tests, Ruff passed, workflow YAML parsed, and
  `git diff --check` exited 0.
- Second-round completion evidence (historical, superseded by the current pins
  above): the hermetic CTV checker exited 0 with authority
  SHA-256 `5c370c59ebc8329b252ba2832677164c9cc451a159ef42d65b7085640d7edad4`,
  56 schemas, 249 enum rows, and two replicas; CGS `--self-test` exited 0;
  lifecycle-root semantic `--self-test` exited 0 with 2 accepted/29 rejected/2
  replicas. The focused PR-gate suite passed 19 tests, Ruff passed the changed
  test, workflow YAML parsed, and `git diff --check` exited 0.

## Decision Log

- 2026-07-30: chose a lifecycle-root-only union rather than widening the generic coordinate or reusing the RP type. This preserves owner-specific purpose, source, and replay semantics.

## Review Log

- Confirmed finding: Product priority P2; approval disposition `changes_required`; finding type architecture/security. Supported scenario: ordinary first lifecycle-root issuance. Evidence: prior-root-only envelope and preimage schemas conflict with sequence-one no-predecessor legality. Remediation eligibility: `eligible_p1_p2`. The correction is the smallest owner-specific union and matching verification evidence.
- 2026-07-30 pre-review reconciliation: the completed remediation covers every
  known sibling mutation in the frozen matrix: genesis field smuggling,
  bootstrap-anchor substitution, sequence-one successor use, successor genesis
  downgrade, and envelope/preimage mismatch. Independent review is required
  before design approval; no implementation evidence is claimed.
- 2026-07-30 review evidence action: confirmed that the matrix rows were
  declarative only and did not execute lifecycle-root semantics. Product
  priority: Not applicable; approval disposition: `changes_required`; finding
  type: verification; remediation eligibility: `evidence_action`. Reopened the
  plan for one dependency-free witness/validator/checker and current-identity
  reconciliation; product semantics remain unchanged.
- 2026-07-30 evidence-action disposition: resolved. Direct execution now covers
  every requested field, union, sequence, owner, envelope/preimage, and
  self/forward-reference sibling. This remains `evidence_action`, not a new
  product-remediation round.
- 2026-07-31 second-round evidence findings: Product priority Not applicable;
  approval disposition `changes_required`; finding type verification. Confirmed
  both gaps and reopened the bounded evidence loop without changing the
  lifecycle-root product schema.
- 2026-07-31 second-round evidence disposition: resolved. The witness carries
  explicit verified successor history and final-action authorization; all seven
  successor authority/signer substitutions reject. The checker externally pins
  `Path(__file__)` and rejects both drift and non-isolated invocation.
- 2026-07-31 final test-evidence finding: Product priority Not applicable;
  approval disposition `changes_required`; finding type verification. The
  inclusive interval endpoints were specified but lacked persisted witnesses
  for both provenance variants. Reopened the evidence loop for eight exact
  boundary cases without changing product semantics.
- 2026-07-31 final test-evidence disposition: resolved. The persisted fixture,
  matrix, validator, and checker execute all eight exact genesis/successor
  boundary cases. Exact endpoints accept; one microsecond outside either end
  rejects. Boundary deletion is an explicit checker self-test.
- 2026-07-31 strict-verifier finding: Product priority Not applicable; approval
  disposition `changes_required`; finding type verification. Successor equality
  was reached before fully validating both the presented and historical
  coordinates. Reopened for one shared structural validator and persisted
  malformed-coordinate evidence; product semantics remain unchanged.
- 2026-07-31 strict-verifier disposition: resolved. Both coordinate sources now
  pass the same exact shape, source, purpose, non-empty issuer/profile,
  key/root/record digest, and timestamp interval-order checks before equality.
  Four malformed presented and four malformed historical cases reject.
- 2026-07-31 final independent review: `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer` reported no remaining strict
  finding. Coordinator disposition: accepted. Product priority: Not
  applicable; approval disposition: `follow_up`; finding type:
  verification/integration; remediation eligibility: `record_only`.

## Blockers And Limits

- No external blocker. Budget: two bounded design milestones and one subsequent independent review; another finding on this same boundary requires a closed grammar reconstruction rather than a third variant patch.

## Next Action

Resume the active M0 implementation WorkPlan at current-shape lifecycle replay:
`docs/work/semantic_ingestion/m0-canonical-genesis-structural-contract-implementation-2026-07-31/implementation.plan.md`.
