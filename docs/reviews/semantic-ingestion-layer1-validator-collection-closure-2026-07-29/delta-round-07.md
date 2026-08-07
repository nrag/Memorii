# Design Review: Layer 1 Validator Collection Grammar Closure

## Review Metadata

- Review ID: semantic-ingestion-layer1-validator-collection-closure-delta-07
- Review mode: delta
- Review outcome: Changes required
- Design path: `docs/design/semantic_ingestion_architecture.md` plus the linked executable validator and checker
- Design baseline: architecture SHA-256 `67bf2620a0379761853861e416efba0816045ef4bf88e4808e701a9ac3bc993e`; validator candidate SHA-256 `facdcbd13c3149b5e481ab5d676a24694882d9a1c16200e2b51016222de97d44`; checker candidate SHA-256 `ed90fb681c520cfb86dff67381cf3a664ab2f50044b5f7513860b24668cdc7cb`
- Implementation baseline: `945d6ea03649ca13c800e84bcb9972797e0f0a31` with the current working-tree Layer1 candidate
- Review date: 2026-07-29
- Reviewers: fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer`; coordinator reconciliation
- Included scope: interpreter startup, audit-path binding, deterministic checker evidence, static validation, and regression of the complete affected validator/checker boundary
- Excluded scope: implementation consumer repins and remote CI execution

## Executive Assessment

DREV-013 and DREV-014 are behaviorally closed: isolated startup, sibling-shadow
exclusion, and exact-path audit denial pass against the frozen candidate.
Approval still requires two narrow evidence corrections. The checker-owned
suite does not itself execute the actual checker entry point without `-I`, and
the validator candidate fails scoped Pyright because one publication-test local
is not provably initialized.

## Governing Sources

- Root `AGENTS.md`, `.agent/PLANS.md`, and the build/review Design Skills
- `docs/design/semantic_ingestion_architecture.md`, Section 3.23.4.2.1
- `docs/development/static_tooling.md`
- `docs/work/semantic_ingestion/layer1-validator-collection-closure-2026-07-29/design.plan.md`
- Immutable delta reports 01 through 06

## Independently Reconstructed Requirements

| Requirement | Source | Design coverage | Acceptance criteria | Verification | Status |
| --- | --- | --- | --- | --- | --- |
| VLC-001 | Closed unary collections | Complete | Invalid shapes reject | Self-test and exact checker | locally verified |
| VLC-002 | Closed tuple grammar | Complete | All finite, variadic, and boundary forms proved | Self-test and exact checker | locally verified |
| VLC-003 | Content-addressed isolated checker | Partial evidence | Actual checker rejects clean non-isolated entry; isolated replicas and exact audit path pass | Checker-owned entry control plus exact checker | changes required |
| VLC-004 | Fail-closed compatible publication | Complete at runtime; static proof fails | Runtime matrix passes and scoped static gate has no findings | Self-test, Pyright, Ruff | changes required |

## Contract And Evidence Boundaries

The canonical `python3.12 -I` invocation is the pre-import security boundary;
the post-import guard supplies a clean diagnostic but cannot secure imports that
already ran. Evidence for that guard must execute the actual checker entry
point. The executable design artifact must also pass the repository's scoped
static gate rather than relying only on runtime branch correlation.

## Confirmed Findings

### DREV-015: Actual non-isolated checker entry lacks checker-owned evidence

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: verification / security boundary
- Affected scenario and prevalence evidence: Clean non-isolated invocation of the design authority checker; this is trust-tooling evidence without a product-prevalence claim.
- Design location: `docs/design/semantic_ingestion/traceability_golden_vectors/check_ctv_binding_authority_v2.py`
- Governing source or requirement: VLC-003 and the DREV-013 closure claim
- Expected behavior: The deterministic checker gate executes the actual checker without `-I` and proves nonzero exit, empty stdout, and the exact isolation diagnostic before argument or authority processing.
- Design behavior: The guard is correct, and separate coordinator/reviewer invocations observe the correct rejection, but the checker-owned suite only launches a generic startup probe.
- Evidence: Direct inspection of `validate_isolated_startup()` and `main()`; a direct non-isolated command exited `1` with `CTV v2 authority checker requires Python isolated mode; invoke with -I`.
- Impact: Future execution of the canonical positive gate can pass without re-proving that the actual checker entry retains its negative behavior.
- Root invariant or contract boundary: Revision-bound process-entry evidence must exercise the executable entry point it certifies.
- Equivalence class and adjacent bypasses inspected: Actual checker entry, generic probe, isolated canonical entry, sibling stdlib shadow, argument parsing, stdout, stderr, and recursive invocation.
- Positive behavior that must remain valid: Canonical `python3.12 -I`, exact self-hash, sibling-shadow exclusion, two hermetic replicas, and authority reproduction.
- Recommended invariant-level resolution: Add a checker-owned subprocess control that copies the checker into clean scratch state, launches the copied checker without `-I`, and asserts the complete exit/stdout/stderr contract.
- Verification needed: Exact isolated checker command must execute the negative control and still reproduce authority `89a98fc1...` from two replicas.
- Evidence maturity affected: VLC-003 deterministic startup evidence

### DREV-016: Validator candidate fails scoped static validation

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: verification / deterministic tooling
- Affected scenario and prevalence evidence: Static validation of the executable design validator's seeded publication-failure branch; this is repository tooling rather than a product-prevalence claim.
- Design location: `docs/design/semantic_ingestion/traceability_golden_vectors/validate_ctv_binding_authority_v2.py`, publication self-test local `initial_mode`
- Governing source or requirement: Root type-safety rule, deterministic tooling gate, and VLC-004 evidence
- Expected behavior: The scoped Pyright command reports zero findings while preserving the seeded-target mode assertion.
- Design behavior: `initial_mode` is assigned only under `initial is not None`, while its later correlated `else` use is not proven by Pyright.
- Evidence: `.venv/bin/pyright` reports `reportPossiblyUnboundVariable` at validator line 2477; the runtime self-test, Ruff, and `py_compile` pass.
- Impact: The candidate cannot satisfy its deterministic static completion gate, and the publication-mode proof depends on an implicit correlation rather than an explicit typed state.
- Root invariant or contract boundary: Executable design tooling must retain both behavior-level evidence and static type closure.
- Equivalence class and adjacent bypasses inspected: Absent target, seeded target, mode capture, failure before replacement, failure after replacement, runtime assertion, and static branch correlation.
- Positive behavior that must remain valid: Exact absent/seeded bytes, mode preservation, temporary cleanup, failure matrix, and unchanged authority output.
- Recommended invariant-level resolution: Initialize the mode state explicitly and require it to be non-`None` in the seeded branch before comparison, without weakening or deleting the assertion.
- Verification needed: Scoped Pyright, Ruff, `py_compile`, validator self-test, and exact isolated checker all pass on the new content-addressed revision.
- Evidence maturity affected: VLC-004 deterministic static evidence

## Requirements Coverage

VLC-001 and VLC-002 are locally verified. VLC-003 behavior is correct but needs
checker-owned negative entry evidence. VLC-004 runtime behavior is correct but
its executable validator must pass scoped Pyright.

## Architecture And Feasibility

Both corrections are local to evidence code and do not change normative
architecture, authority semantics, collection grammar, or publication
ordering. They will change validator and checker identities and therefore
require coordinated static-tooling and parent-handoff hash updates.

## Failure, Security, And Operations

The canonical `-I` boundary, external expected checker hash, exact audit path,
private temporary, and atomic replacement behavior remain required. The new
negative control must avoid recursive positive-gate execution by invoking the
copied checker without isolation so its guard exits immediately.

## Verification And Evidence Maturity

Coordinator execution passed the exact isolated two-replica checker, actual
clean non-isolated rejection, validator self-test, Ruff, `py_compile`, prior
report validation, and `git diff --check`. Scoped Pyright produced the one
confirmed error above. Two independent reviewers approved the behavioral
boundary; the test reviewer proposed DREV-015.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Residual risk | Status |
| --- | --- | --- | --- | --- | --- |
| Actual guard regresses while substitute probe passes | Checker entry changes | Non-isolated execution is no longer fail closed | Checker-owned actual-entry control | Low | open |
| Static branch correlation remains implicit | Validator refactor or stricter gate | Candidate fails deterministic tooling | Explicit optional mode state and assertion | Low | open |

## Rejected Or Consolidated Findings

DREV-013 and DREV-014 are resolved. The spec and correctness reviewers found no
additional changes-required issue. Direct one-off execution of the non-isolated
checker supports current behavior but does not replace the checker-owned
revision-sensitive negative control required by DREV-015. Parent consumer
repins and remote CI remain implementation work.

## Required Changes Before Approval

Close DREV-015 and DREV-016 in one bounded correction, update all affected
content-addressed pins, rerun the exact gates, and use round 10 for a fresh
three-role final delta review.

## Non-Blocking Follow-Ups

After approval, the parent implementation must use the final exact isolated
command, repin all consumers, run the public CLI matrix, and obtain remote CI
evidence.

## Final Outcome

Changes required.

## Review Limitations

Remote CI was not executed.
