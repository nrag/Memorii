# Design Review: Layer1 Heading-Default Design-Slice Closure

## Review Metadata

- Review ID: semantic-ingestion-layer1-heading-default-closure-delta-round-02
- Review mode: delta
- Review outcome: Changes required
- Design path: linked design and parent implementation WorkPlans; unchanged registry/CTV authority candidate
- Design baseline: design `67bf2620...`; registry `8e6395e2...`; authority `f7c0d000...`; validator `830c63e3...`; checker `2ca3da2c...`
- Implementation baseline: repository `945d6ea03649ca13c800e84bcb9972797e0f0a31` plus intentionally staged work
- Review date: 2026-07-29
- Reviewers: fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer`
- Included scope: DREV-003 handoff provenance, zero-omission consumer inventory, transition, migration, and rollback
- Excluded scope: canonical mapping/authority edits, parent production edits, C2 regeneration, and external evidence

## Executive Assessment

The replacement provenance is now explicit, and reviewers agree no Layer1
semantic choice remains. Approval is still withheld because the handoff
inventory omitted named consumers and described rollback as restoring an old
bundle, which is invalid after a content-addressed release is published.

## Governing Sources

`AGENTS.md`, `.agent/PLANS.md`, review-design Skill/references, SIA-R03
Sections 3.23.4.1 and release/pointer progression rules, prior immutable
reports, and both active WorkPlans.

## Independently Reconstructed Requirements

| Requirement | Source | Design coverage | Acceptance criteria | Verification | Status |
| --- | --- | --- | --- | --- | --- |
| Every invalidated consumer has one disposition | DREV-003 and WorkPlan completion | Partial | Zero-omission path/symbol inventory | Direct hash/cardinality/call-site search | changes required |
| Frozen mapping is a completed decision | WorkPlan decision/assumption contract | Contradictory | No reviewed decision remains a working assumption | Cross-section comparison | changes required |
| Recovery preserves content-addressed history and monotonic pointers | SIA release/pointer contract | Incorrect generic rollback | Pre-publication abort; post-publication successor only | Release-path inspection | changes required |

## Contract And Evidence Boundaries

The review concerns design-to-implementation handoff governance. It does not
change CTV bytes. Historical signed artifacts remain immutable; a current
pointer cannot be rewound to make the invalid 147 registry current.

## Confirmed Findings

### DREV-003: Handoff Inventory And Decision State Were Incomplete

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: governance, verification, and compatibility
- Affected scenario and prevalence evidence: every parent repin and review; omitted C2 scripts and aggregate test labels could conceal stale consumers.
- Design location: linked WorkPlan assumptions and Parent Implementation Handoff table; parent active milestone
- Governing source or requirement: WorkPlan self-contained/frozen-input contract and DREV-003 resolution
- Expected behavior: a frozen decision and zero-omission file/symbol inventory with explicit actions and failure signals.
- Design behavior: the R03/R13 mapping remained a working assumption; C2 migration/rebind scripts and named registry/manifest/acceptance tests were omitted; parent active verification retained old authority.
- Evidence: old-hash/cardinality and direct-consumer search identified the omitted files and active old target.
- Impact: a worker could mix identities, omit a transitive proof, or reopen a settled semantic decision.
- Root invariant or contract boundary: one frozen authority plus a complete consumer transition.
- Equivalence class and adjacent bypasses inspected: direct hashes, cardinality guards, loaders, manifests, execution/release callers, all relevant tests, four marker families, workflow/docs, and C2 tooling.
- Positive behavior that must remain valid: exact mapping/authority, deferred production edits, and blocked C2.
- Recommended invariant-level resolution: close the inventory at file/symbol level, freeze the mapping as verified, and update active parent targets.
- Verification needed: deterministic inventory comparison and final targeted review.
- Evidence maturity affected: specified provenance and implementation readiness.

### DREV-004: Generic Bundle Rollback Violated Release Monotonicity

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: compatibility, migration/rollback, and transactional governance
- Affected scenario and prevalence evidence: every failure after a release/generation using registry source identity `6acb4736...` is published.
- Design location: handoff rollback dispositions and parent rollout/rollback contract
- Governing source or requirement: SIA registry-source binding, immutable history, signed successor, and pointer monotonicity rules
- Expected behavior: pre-publication candidate abort is distinct from post-publication recovery; published history is immutable and current pointer rewind rejects.
- Design behavior: the table said rollback restores the old 147 bundle with no release/history/pointer disposition.
- Evidence: release code binds source identity and structural digest; the old registry is invalid for the current design; loaders reject mixed states.
- Impact: an implementer could reintroduce the known design defect or corrupt authority/history semantics.
- Root invariant or contract boundary: content-addressed release state advances monotonically; recovery is an authorized successor, never reinterpretation.
- Equivalence class and adjacent bypasses inspected: unpublished candidate, published current, old history, mixed source/loaders/pins, pointer rewind, signed successor, and unavailable recovery authority.
- Positive behavior that must remain valid: old artifacts remain historical; mixed identity fails closed; C2 remains separate.
- Recommended invariant-level resolution: define closed H0-H4 transition states; abort unpublished candidates; permit post-publication recovery only through a signed higher-sequence successor.
- Verification needed: parent state-matrix tests for old-current rejection, historical retention, mixed identity rejection, pointer-rewind rejection, and authorized successor recovery.
- Evidence maturity affected: specified migration, rollback, compatibility, and implementation handoff.

### DREV-005: Verification Families Were Named Too Broadly

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: verification and implementation readiness
- Affected scenario and prevalence evidence: every registry/manifest/acceptance repin and each of four marked-block families.
- Design location: aggregate test and marker rows in the handoff table
- Governing source or requirement: WorkPlan completion and family-complete review contracts
- Expected behavior: concrete files/markers, failure signals, assertions, and rollback coupling.
- Design behavior: aggregate labels did not name direct test files or grammar V2, inventory V1, enum V2, and enum V1.
- Evidence: direct consumer search and current registry failures.
- Impact: transitive and sibling paths could remain unproved.
- Root invariant or contract boundary: complete behavioral proof for every consumer class.
- Equivalence class and adjacent bypasses inspected: canonical/independent registry, manifest, acceptance, release, workflow, and all four marker forms.
- Positive behavior that must remain valid: strict malformed/duplicate/order/fallback rejection and exact public parity.
- Recommended invariant-level resolution: enumerate each file and marker family with exact parent proof.
- Verification needed: named suites and marker matrix after implementation.
- Evidence maturity affected: implementation and local/CI verification.

## Requirements Coverage

The canonical design slice remains complete. Handoff/migration governance
requires one invariant-level remediation.

## Architecture And Feasibility

The correction is bounded and requires no new Layer1 semantic decision. A
closed state machine and consumer matrix are sufficient.

## Failure, Security, And Operations

Mixed identities fail closed. Post-publication rollback is unavailable without
authorized successor authority.

## Verification And Evidence Maturity

Mapping/CTV authority remains locally verified. Parent implementation, release
state transitions, and CI are pending.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Residual risk | Status |
| --- | --- | --- | --- | --- | --- |
| Omitted consumer | Category-level handoff | Mixed revision | Closed path/symbol inventory | Final delta review | remediated |
| Pointer rewind | Generic rollback | Invalid current authority | H0-H4 state machine | Requires parent tests | remediated in design |
| Settled mapping appears open | Stale assumption | Unnecessary redesign | Mark verified/frozen | None | remediated |

## Rejected Or Consolidated Findings

DREV-005 is consolidated with DREV-003 at the closed consumer/proof boundary.
No canonical artifact finding was confirmed.

## Required Changes Before Approval

Freeze mapping decision, enumerate omitted files/markers, update parent active
target, and replace rollback prose with the closed H0-H4 transition model.

## Non-Blocking Follow-Ups

None.

## Final Outcome

Changes required. Canonical design artifacts remain unchanged.

## Review Limitations

No production change, publication, remote CI, or C2 regeneration was reviewed.
