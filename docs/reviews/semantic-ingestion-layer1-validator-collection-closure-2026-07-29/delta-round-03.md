# Design Review: Layer 1 Validator Collection Grammar Closure

## Review Metadata

- Review ID: semantic-ingestion-layer1-validator-collection-closure-delta-03
- Review mode: delta
- Review outcome: Changes required
- Design path: `docs/design/semantic_ingestion_architecture.md` plus the linked executable validator
- Design baseline: architecture SHA-256 `67bf2620a0379761853861e416efba0816045ef4bf88e4808e701a9ac3bc993e`; validator candidate SHA-256 `3d5e215de91481a1c549f7cc9e753dfa193a9d31e814fc69ce3f562d941e5bff`
- Implementation baseline: `945d6ea03649ca13c800e84bcb9972797e0f0a31` with the current working-tree Layer1 candidate
- Review date: 2026-07-29
- Reviewers: fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer`; coordinator reconciliation
- Included scope: final collection/type/data classifier, validator publication behavior, static-tooling pin, and parent implementation handoff
- Excluded scope: unrelated semantic-ingestion behavior and remote CI execution

## Executive Assessment

The final classifier closes the previously reported collection/type grammar
bypasses and preserves the frozen authority. Approval still cannot be granted:
the validator publishes directly to the target path, so an interrupted or
failed write can destroy an existing valid authority. Tuple quoted-child and
zero-item boundary evidence is also incomplete, and the parent implementation
handoff is not yet revision-bound or executable.

## Governing Sources

- Root `AGENTS.md`, `.agent/PLANS.md`, and the build/review Design Skills
- `docs/design/semantic_ingestion_architecture.md`, Section 3.23.4.2.1
- `docs/work/semantic_ingestion/layer1-validator-collection-closure-2026-07-29/design.plan.md`
- `docs/reviews/semantic-ingestion-layer1-validator-collection-closure-2026-07-29/delta-round-01.md`
- `docs/reviews/semantic-ingestion-layer1-validator-collection-closure-2026-07-29/delta-round-02.md`

## Independently Reconstructed Requirements

| Requirement | Source | Design coverage | Acceptance criteria | Verification | Status |
| --- | --- | --- | --- | --- | --- |
| VLC-001 | Closed unary collections | Complete | Exactly one valid type argument; ellipsis and metadata-as-type reject | Validator self-test and direct code inspection | locally verified |
| VLC-002 | Closed tuple grammar | Behavior complete; evidence partial | Finite valid items or exact native `tuple[T, ...]`; every spelling and boundary is proved | Tuple position/cardinality/quoted-child matrix | changes required |
| VLC-003 | Content-addressed validator | Complete for design tooling | Exact validator pin reproduces unchanged authority | Exact two-replica checker | locally verified |
| VLC-004 | Fail-closed publication | Incomplete | Invalid input and publication failure cannot alter an absent or existing authority | Atomic writer failure tests and parent public CLI matrix | changes required |

## Contract And Evidence Boundaries

The design validator owns compilation and atomic publication of the checked
authority. The parent implementation owns the clean-room compiler, coordinated
consumer repin, and black-box PR-gate matrix. A helper-level rejection does not
prove publication safety, and a deferred handoff must still name the exact
candidate identity and observable pass/fail signals.

## Confirmed Findings

### DREV-005: Validator publication can corrupt an existing authority on failure

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: transactional consistency / failure recovery
- Affected scenario and prevalence evidence: Design-authority generation interrupted or failed after opening an existing output path; this is a trust-artifact publication concern without a product-prevalence claim.
- Design location: `validate_ctv_binding_authority_v2.py` `main()` publication path
- Governing source or requirement: VLC-004 and the linked WorkPlan invariant that failure cannot publish or damage authority
- Expected behavior: Compilation and validation finish before publication; an absent target remains absent and an existing authority remains byte-identical on any write, flush, replace, or validation failure; readers never observe a partial artifact.
- Design behavior: `Path.write_bytes(computed_bytes)` opens the authority path with truncating `wb` semantics, then the validator reads the path twice and validates only after publication.
- Evidence: Direct inspection of `main()` shows target mutation precedes canonical parsing and candidate validation. Interruption, short write, ENOSPC, or another I/O failure after open can leave the prior authority empty or partial, and the double read admits a concurrent-writer TOCTOU.
- Impact: A failed verification command can destroy the previously trusted checked authority or expose partial bytes.
- Root invariant or contract boundary: Content-addressed authority publication must be crash-safe, same-directory atomic, and validated before visibility.
- Equivalence class and adjacent bypasses inspected: Absent target, pre-seeded target, write/flush/replace failure, post-write validation, concurrent reader, and concurrent target mutation.
- Positive behavior that must remain valid: A successful write publishes the exact canonical checked-authority bytes and the no-write validation path remains read-only.
- Recommended invariant-level resolution: Validate `computed_bytes` before publication; write to a unique same-directory temporary file, flush and fsync it, atomically replace the destination, fsync the directory where supported, clean the temporary file on failure, and validate one immutable read snapshot.
- Verification needed: Injected write/flush/replace failures with absent and pre-seeded targets, concurrent-reader observation, successful exact-byte replacement, and exact checker reproduction.
- Evidence maturity affected: VLC-004 and final design approval

### DREV-006: Tuple quoted-child and zero-item boundaries lack explicit self-test proof

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: verification / declaration-grammar trust boundary
- Affected scenario and prevalence evidence: Malformed tuple annotations with quoted ellipsis children, plus the explicitly recorded zero-item finite-tuple boundary; this is design-authority evidence, not a product-prevalence claim.
- Design location: Validator adversarial self-test collection corpus and linked WorkPlan assumptions
- Governing source or requirement: VLC-002 and Section 3.23.4.2.1's finite-or-exact-variadic tuple grammar
- Expected behavior: Quoted ellipsis in every tuple position rejects across direct, whole-quoted, nested, alias, inherited, reachable, and unprojected forms; the recorded `tuple[()]` boundary has an explicit accepted normalized control.
- Design behavior: The classifier rejects quoted ellipsis recursively, but the self-test's quoted-child loop covers only list, set, and frozenset. Native tuple ellipsis and whole-expression quote cases do not exercise tuple-specific quoted children. The zero-item assumption has no acceptance assertion.
- Evidence: No explicit self-test cases cover `tuple["...", str]`, `tuple[str, "..."]`, `tuple["...", ...]`, `tuple[..., "..."]`, or normalized `tuple[()]`.
- Impact: A tuple-specific recursion or punctuation regression can pass the claimed complete family proof.
- Root invariant or contract boundary: Every authorized or rejected boundary of the closed tuple grammar needs an observable, non-circular assertion.
- Equivalence class and adjacent bypasses inspected: Direct, whole-quoted, quoted-child, nested, alias, inherited, reachable/unprojected, native/multiple ellipsis, finite tuple, and `tuple[T, ...]`.
- Positive behavior that must remain valid: Unary collections, finite tuples, exact native variadic tuple, valid quoted forward references, Literal data, and Annotated/Field metadata.
- Recommended invariant-level resolution: Add the missing tuple quoted-child family across the existing representation loops and assert the recorded zero-item normalized form.
- Verification needed: Validator self-test, exact authority reproduction, and exact checker.
- Evidence maturity affected: VLC-002 local verification

### DREV-007: Parent implementation handoff is not revision-bound or executable

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: verification / authority-publication handoff
- Affected scenario and prevalence evidence: Repository PR enforcement after the design validator changes identity; this is review-governance and CI evidence without a product-prevalence claim.
- Design location: Parent implementation WorkPlan, workflow, and Layer1 gate tests
- Governing source or requirement: VLC-003, VLC-004, SIA-R03, L1-008, and L1-009
- Expected behavior: The parent milestone pins validator `3d5e215de91481a1c549f7cc9e753dfa193a9d31e814fc69ce3f562d941e5bff` and names a public `--write` matrix that proves absent-output preservation, pre-seeded byte preservation, valid exact publication, and workflow consumer identity.
- Design behavior: The parent WorkPlan and implementation consumers still pin the superseded validator and describe only key invalid cases. Existing collection CLI tests prove absent output for two reference-compiler cases, not the final design-validator family or seeded preservation.
- Evidence: `.github/workflows/pr-gates.yml`, `test_ctv_binding_authority_pr_gate.py`, and `test_semantic_ingestion_ctv_reference_compiler.py` still contain `f0f74bc...`; the parent ledger lacks the final candidate and complete public publication family.
- Impact: The reviewed design candidate cannot yet be enforced or validated through the repository's canonical implementation gate.
- Root invariant or contract boundary: Every content-addressed design handoff must bind all consumers and behavior evidence to the same reviewed revision.
- Equivalence class and adjacent bypasses inspected: Workflow pin, gate-test pin, independent-compiler pin, absent/pre-seeded invalid output, valid output, and remote CI execution.
- Positive behavior that must remain valid: The clean-room compiler remains separately authored and the exact checked authority remains byte-identical.
- Recommended invariant-level resolution: Record the exact parent matrix and candidate identity now; after design approval, repin all implementation consumers and implement the public subprocess proof before claiming Layer1 completion.
- Verification needed: Focused public CLI matrix, workflow structure test, clean-checkout exact checker, and remote CI/branch-protection evidence when available.
- Evidence maturity affected: Parent Layer1 implementation milestone

## Requirements Coverage

VLC-001 and VLC-003 are locally verified. VLC-002 remains evidence-incomplete.
VLC-004 has a confirmed design-local publication defect and an incomplete
parent handoff.

## Architecture And Feasibility

The required publication correction is bounded to the validator's output
transaction and tests. It does not require changing normative architecture,
registry, checked authority, checker, profile, or production runtime.

## Failure, Security, And Operations

The current direct write violates crash-safe trust-artifact publication.
Rollback is restoration of the prior reviewed validator and static-tooling pin;
the unapproved candidate must not be repinned into implementation consumers.

## Verification And Evidence Maturity

The final classifier, self-test baseline, and two-replica exact checker pass.
Atomic failure recovery, complete tuple boundary proof, parent public
publication proof, remote CI execution, and required branch protection do not.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Residual risk | Status |
| --- | --- | --- | --- | --- | --- |
| Existing authority is truncated | Interrupted or failed direct write | Trusted artifact loss/corruption | Same-directory atomic publication | Low after failpoint proof | open |
| Tuple regression escapes self-test | Quoted-child or zero-item path changes | Invalid grammar accepted or valid boundary rejected | Explicit tuple boundary matrix | Low | open |
| Mixed validator identities | Parent consumers repin incompletely | PR gate proves a different candidate | Coordinated content-addressed repin | Low after implementation proof | open |

## Rejected Or Consolidated Findings

DREV-004 is resolved by the final classifier. The spec review's publication
handoff and the test review's stale pins are consolidated in DREV-007. The
correctness review's publication finding is distinct and design-local, so it is
recorded separately as DREV-005.

## Required Changes Before Approval

Implement atomic, crash-safe validator publication and the missing tuple
boundary self-tests in a reopened bounded design round. Record the exact parent
handoff, then rerun fresh three-role design review.

## Non-Blocking Follow-Ups

After design approval, the parent implementation must repin its three consumers,
implement the complete public CLI absent/pre-seeded/valid matrix, and obtain
remote CI/branch-protection evidence when available.

## Final Outcome

Changes required. The linked design round budget is exhausted, so the WorkPlan
must stop as blocked rather than continue speculative correction.

## Review Limitations

The review did not execute remote CI or inspect unrelated semantic-ingestion
subsystems.
