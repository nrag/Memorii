# Design Review: Layer1 Heading-Default Design-Slice Closure

## Review Metadata

- Review ID: semantic-ingestion-layer1-heading-default-closure-delta-round-01
- Review mode: delta
- Review outcome: Changes required
- Design path: linked design WorkPlan plus unchanged registry/CTV authority candidate
- Design baseline: design `67bf2620...`; registry `8e6395e2...`; authority `f7c0d000...`; validator `830c63e3...`; checker `2ca3da2c...`
- Implementation baseline: repository `945d6ea03649ca13c800e84bcb9972797e0f0a31` plus intentionally staged work
- Review date: 2026-07-29
- Reviewers: fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer`
- Included scope: DREV-001/002 disposition, frozen-baseline provenance, parent consumer handoff, rollback, and C2 block
- Excluded scope: canonical mapping/authority semantics, production edits, C2 regeneration, and external evidence

## Executive Assessment

DREV-001 and DREV-002 are resolved: the operation legitimately separates the
Layer1 normative design slice from parent implementation and from blocked C2
authority. Approval remains unavailable because the WorkPlan and parent handoff
still expose contradictory old/new baselines and an incomplete transition
inventory.

## Governing Sources

`AGENTS.md`, `.agent/PLANS.md`, build/review Skills, SIA-R03 Section 3.23.4.1,
the linked WorkPlan, and the immutable full-round-01 report.

## Independently Reconstructed Requirements

| Requirement | Source | Design coverage | Acceptance criteria | Verification | Status |
| --- | --- | --- | --- | --- | --- |
| Frozen replacement provenance is unambiguous | WorkPlan and review-design baseline contracts | Partial | Header, evidence, report, and parent name identical candidate hashes | Direct cross-file comparison | changes required |
| Every consumer has a transition and rollback disposition | Design completion contract | Partial | File-level action, failure signal, evidence, and atomic rollback | Direct call-site/hash/cardinality inventory | changes required |
| C2 remains excluded and fail closed | DREV-002 disposition | Complete | No Layer1 repin or readiness claim | Current C2 command fails closed | verified |

## Contract And Evidence Boundaries

The canonical two-file candidate is unchanged. This delta concerns only the
authority handoff from an approved design slice to a later implementation
worker and the prohibition on treating blocked C2 inputs as Layer1 consumers.

## Confirmed Findings

### DREV-003: Replacement Baseline And Consumer Handoff Were Contradictory

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: governance, verification, compatibility, and rollback readiness
- Affected scenario and prevalence evidence: every parent Layer1 repin; the header named the old registry while evidence named the new one, and all implementation consumers remained on old pins/cardinality.
- Design location: linked WorkPlan header, Current State, Evidence Log, Review Log, Blockers, Next Action, and parent Design Baseline
- Governing source or requirement: `.agent/PLANS.md` self-contained canonical-input contract; review-design frozen-baseline contract; SIA-R03 content-addressed authority
- Expected behavior: one replacement baseline plus exhaustive consumer action, failure, evidence, and rollback dispositions.
- Design behavior: historical and candidate facts were mixed; the parent could select old pins; C2 blocked consumers were generic rather than enumerated.
- Evidence: current hashes are registry `8e6395e2...` and authority `f7c0d000...`; both loaders reject 148; workflow/docs/tests use old pins; C2 validators retain incompatible/incomplete authority.
- Impact: a mixed 148-source/147-loader or new-source/old-pin transition could be mistaken for an approved implementation.
- Root invariant or contract boundary: content-addressed authority and every consumer must move and roll back atomically.
- Equivalence class and adjacent bypasses inspected: both loaders; registry/manifest/execution/acceptance callers; compiler; workflow/static docs/tests; C2 recipe/package/validators/elaborators/verifier.
- Positive behavior that must remain valid: exact R03/R13 mapping, 148/148 set, regenerated CTV authority, deferred implementation, and blocked C2.
- Recommended invariant-level resolution: freeze all replacement identities in the header and parent candidate record; separate historical facts; add exhaustive file-level handoff and atomic rollback tables; prohibit Layer1 C2 repinning.
- Verification needed: targeted delta re-review and exact old-hash/cardinality disposition search.
- Evidence maturity affected: specified provenance, implementation handoff, compatibility, rollback, local verification, and CI enforcement.

## Requirements Coverage

Canonical design-slice requirements remain covered. Handoff governance required
remediation before approval.

## Architecture And Feasibility

No new semantic decision is needed. The parent correction is bounded and C2
remains separately blocked.

## Failure, Security, And Operations

Mixed revisions must fail closed. Rollback must restore registry, authority,
loader cardinalities, pins, workflow/docs, and tests as one bundle.

## Verification And Evidence Maturity

Design-slice authority remains locally verified. Parent implementation and CI
remain pending and must not inherit that maturity.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Residual risk | Status |
| --- | --- | --- | --- | --- | --- |
| Parent selects superseded header pin | Ambiguous WorkPlan | Mixed authority | Freeze replacement and label historical inputs | None after delta re-review | remediated |
| Consumer omitted | Partial inventory | False-green or fail-closed release | File-level transition table | Review must verify inventory | under review |
| C2 accidentally repinned | Shared registry hash search | Invalid authority | Explicit do-not-repin table row | C2 remains blocked | controlled |

## Rejected Or Consolidated Findings

DREV-001 and DREV-002 were verified resolved and are not repeated.

## Required Changes Before Approval

Freeze replacement identities in both plans, separate historical/candidate
state, enumerate every Layer1 and blocked C2 consumer, and state atomic
transition/rollback.

## Non-Blocking Follow-Ups

None.

## Final Outcome

Changes required. Canonical design artifacts remain frozen and unchanged.

## Review Limitations

No production edits, remote CI, branch protection, or C2 regeneration were in
scope.
