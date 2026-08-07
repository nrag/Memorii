# Design Review: Layer1 Heading-Default Design-Slice Closure

## Review Metadata

- Review ID: semantic-ingestion-layer1-heading-default-closure-full-round-01
- Review mode: full
- Review outcome: Changes required
- Design path: docs/design/semantic_ingestion_architecture.md plus canonical registry and CTV authority
- Design baseline: design `67bf2620a0379761853861e416efba0816045ef4bf88e4808e701a9ac3bc993e`; registry `8e6395e2657eb1a51e5eef7d9b88b5d43b974a58f7f786ed135f6758262bfec1`; authority `f7c0d00080b02343f57fc69adee47ef0d7db1846641b1a7bb11fc7bc0b97c74e`
- Implementation baseline: repository `945d6ea03649ca13c800e84bcb9972797e0f0a31` with intentionally staged pre-review changes and an unstaged two-file design overlay
- Review date: 2026-07-29
- Reviewers: fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer`
- Included scope: direct heading-default completeness, R03/R13 mapping authority, registry-to-CTV authority derivation, downstream-consumer inventory, and design-slice implementation readiness
- Excluded scope: CTV value semantics, M0A-C2 recipe/package regeneration, M0A-C3-C5, production consumer edits, remote CI, branch protection, and operational certification

## Executive Assessment

The canonical two-file correction is sound: the registry adds exactly one
direct `3.23.4.2.1 -> [SIA-R03,SIA-R13]` member and the regenerated CTV
authority changes only the registry identity. The round did not approve the
operation because its WorkPlan claimed stronger closure than the evidence:
production structural consumers still enforce 147 defaults, and the normative
C2 recipe/package remains stale against current design/registry identities.

## Governing Sources

- `AGENTS.md`
- `.agent/PLANS.md`
- `.agent/skills/build-design/SKILL.md`
- `.agent/skills/review-design/SKILL.md`
- `docs/design/semantic_ingestion_architecture.md`, especially Sections
  3.23.4.1 and 3.23.4.2.1
- `docs/design/semantic_ingestion/traceability_registry/registry-v1.json`
- CTV authority validator/checker and structural registry implementations

## Independently Reconstructed Requirements

| Requirement | Source | Design coverage | Acceptance criteria | Verification | Status |
| --- | --- | --- | --- | --- | --- |
| Every numeric Sections 1-5 heading has one explicit direct default | SIA-R03, Section 3.23.4.1 | Complete in corrected registry | Exact heading-path set equality; unique nonempty direct entries; no fallback | Independent extraction reports 148/148, no missing/extra | verified for design slice |
| `3.23.4.2.1` maps to the requirements governing C2 traceability authority | SIA-R03/R13, Sections 3.23.4.2-4 | Complete | Explicit reviewed R03/R13 member | Three reviewers inspected mapping context and adjacent defaults | verified |
| Registry-bound CTV authority is content addressed and reproducible | SIA-R03, CTV v2 authority contract | Complete | Validator and separate exact checker reproduce bytes and identities | 56 schemas, 240 enum rows, two replicas | verified |
| Downstream evidence claims name every stale consumer | WorkPlan completion contract and evidence-maturity rules | Partial before remediation | Each consumer is repinned, blocked, or explicitly excluded | Direct hash/cardinality search and failing registry suite | changes required |

## Contract And Evidence Boundaries

The registry is normative design input. The CTV authority is a deterministic
design-owned derivative. Production loaders, tests, workflow, and static
tooling are implementation consumers and must be repinned after design
approval. The C2 recipe/package is a separate normative design authority; it
is not consumed by Layer1, but its stale identity must be explicit and cannot
be described as regenerated or approved.

## Confirmed Findings

### DREV-001: Closed Heading Contract Exceeded The Implemented Consumer Baseline

- Product priority: P1
- Approval disposition: changes_required
- Confidence: high
- Finding type: verification and evidence-maturity governance
- Affected scenario and prevalence evidence: every ordinary or independent structural registry load of the corrected 148-member source fails at the stale 147-member guard; the registry suite reports 20 failures and 6 passes.
- Design location: linked design WorkPlan completion contract, scope, evidence, and handoff sections
- Governing source or requirement: SIA-R03 Section 3.23.4.1; build/review evidence-maturity contracts
- Expected behavior: design approval distinguishes a reviewed 148-member normative handoff from implementation and CI enforcement and enumerates every stale consumer.
- Design behavior: the canonical mapping is correct, but the WorkPlan claimed both structural rebuilds and registry tests already passed while deferring the code that still rejects 148.
- Evidence: both structural loaders contain exact 147 checks; registry tests fail before manifest reconstruction; the CTV checker passes because it validates a different authority boundary.
- Impact: the parent could overstate local verification or CI readiness and approve a bundle ordinary consumers cannot load.
- Root invariant or contract boundary: normative design authority must be separated from implemented, locally verified, and CI-enforced consumer maturity.
- Equivalence class and adjacent bypasses inspected: canonical loader, independent loader, generator/independent manifests, registry tests, release callers, CTV compiler/checker, workflow, static tooling, and hash-pinned tests.
- Positive behavior that must remain valid: explicit R03/R13 mapping, exact 148/148 set, strict malformed/duplicate/empty rejection, and deferred single-writer implementation.
- Recommended invariant-level resolution: narrow design completion to a normative 148-member handoff, enumerate stale implementation consumers, and require the parent implementation to update both loaders, exact-set/mutation tests, and all pins before local/CI claims.
- Verification needed: targeted review of the corrected WorkPlan; parent registry/manifest suites and complete Layer1 gates after repinning.
- Evidence maturity affected: implemented, locally verified, and CI-enforced structural-registry claims.

### DREV-002: C2 Authority Was Incorrectly Included In The Closure Claim

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: governance and authority-chain verification
- Affected scenario and prevalence evidence: every C2 recipe/package validation against the current design and corrected registry; this is a design-approval boundary, not an ordinary production request path.
- Design location: linked WorkPlan objective, completion contract, included scope, and expected outputs
- Governing source or requirement: SIA-R03 normative C2 recipe source-identity contract
- Expected behavior: every claimed regenerated design-owned dependent validates against the frozen inputs, or is explicitly excluded and blocked.
- Design behavior: the WorkPlan claimed all registry-dependent design artifacts were closed, but `recipe-v1.json` and derived `v1.json` retain older design/registry authority and fail current validation.
- Evidence: current C2 validation fails against design `67bf2620...` and registry `8e6395e2...`; historical M0A-C2 remains blocked.
- Impact: a Layer1-only correction could be mistaken for C2 design readiness or whole-M0 authority closure.
- Root invariant or contract boundary: a content-addressed authority may not be silently carried across changed source identities.
- Equivalence class and adjacent bypasses inspected: recipe source, derived package, both elaborators, recipe/source validators, verification command, static-tooling pins, and Layer1 consumers.
- Positive behavior that must remain valid: the regenerated CTV authority and Layer1 compiler/gate remain independent of the C2 recipe/package.
- Recommended invariant-level resolution: explicitly exclude and block C2 authority in this WorkPlan, preserve its stale status, and require a separate linked C2 design operation before consumption.
- Verification needed: targeted review of the blocked disposition; later full C2 regeneration and independent review.
- Evidence maturity affected: C2 derivable and locally verified claims.

## Requirements Coverage

The direct mapping and CTV authority requirements are covered. Production
consumer compatibility and C2 authority are not completed by this design
operation and must be represented as implementation handoff and separate
blocked design work, respectively.

## Architecture And Feasibility

No fallback, parent inference, duplicate truth, or CTV semantic change was
introduced. The two-file correction is feasible. Production repinning is
bounded. Full C2 regeneration is separately substantial and must not be hidden
inside this correction.

## Failure, Security, And Operations

Fail-closed loader behavior remains intact. The corrected registry is
unapproved source data and carries no trust material, so rollback is the
two-file content-addressed reversion. Remote CI and operational certification
remain unavailable.

## Verification And Evidence Maturity

The mapping and CTV authority are locally verified. Structural consumers are
specified but not yet updated or locally verified. CI jobs are wired but still
pin the prior identities. C2 is explicitly not derivable from the current
checked-in recipe/package.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Residual risk | Status |
| --- | --- | --- | --- | --- | --- |
| Stale consumer pin | Parent omits a registry/authority reference | Layer1 gate fails or validates old authority | Closed hash/cardinality search plus complete parent gates | Remote branch protection unavailable | open for implementation |
| C2 stale authority is consumed | C2 proceeds from old recipe/package | Invalid trust evidence | Explicit blocker and separate linked design operation | M0 remains incomplete | blocked |
| Mapping requirement set is wrong | R03/R13 does not govern subsection | Incorrect coverage | Direct contextual review by three roles | None identified | closed |

## Rejected Or Consolidated Findings

The correctness review treated stale production consumers as expected parent
implementation debt rather than a design finding. The coordinator consolidated
that view with DREV-001: editing production code remains deferred, but the
WorkPlan's stronger verification claim required correction.

## Required Changes Before Approval

- Narrow the WorkPlan completion and scope claims to the Layer1 design slice.
- Enumerate production consumer repinning as parent implementation work.
- Mark the C2 recipe/package stale, excluded, and blocked.
- Run targeted three-role delta review of those dispositions.

## Non-Blocking Follow-Ups

None within the design correction. The parent implementation and separate C2
design blocker are required downstream work, not optional polish.

## Final Outcome

Changes required. The canonical registry/authority delta remains frozen and
unchanged while the WorkPlan claims receive targeted delta review.

## Review Limitations

No remote Actions, branch-protection, or operational evidence was available.
This review did not approve C2 or any production consumer change.
