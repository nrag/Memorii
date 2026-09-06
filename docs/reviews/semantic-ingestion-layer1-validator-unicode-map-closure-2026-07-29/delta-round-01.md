# Design Review: Layer 1 Validator Unicode And Map Grammar Closure

## Review Metadata

- Review ID: semantic-ingestion-layer1-validator-unicode-map-closure-delta-01
- Review mode: delta
- Review outcome: Changes required
- Design path: `docs/design/semantic_ingestion_architecture.md` plus the linked executable validator and checker
- Design baseline: architecture SHA-256 `67bf2620a0379761853861e416efba0816045ef4bf88e4808e701a9ac3bc993e`; validator SHA-256 `04ce1b5a1f9843954f9b7b540dd71efc32165c440dea9cdf94b1a709e5d89c19`; checker SHA-256 `2ca3da2c69b453e2107ab4e901345b4b5420288666561c566732849d56c811c1`
- Implementation baseline: `945d6ea03649ca13c800e84bcb9972797e0f0a31` with the current working-tree Layer1 candidate
- Review date: 2026-07-29
- Reviewers: fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer`; coordinator reconciliation
- Included scope: VUM-001 through VUM-006 and the complete bounded D1 correction
- Excluded scope: reference-compiler consumer remediation, parent public-CLI matrix, CI job partitioning, remote CI, and later semantic-ingestion milestones

## Executive Assessment

Changes required. The correction implements the normative Unicode and map
rules without changing the frozen authority, and the spec and correctness
reviewers approved it. The test reviewer identified two family-completeness
gaps in validator-owned evidence. The coordinator confirmed both against the
WorkPlan completion contract and direct self-test inspection. Neither finding
requires new product semantics or broader scope.

## Governing Sources

- Root `AGENTS.md`, `.agent/PLANS.md`, and the build/review Design Skills
- `docs/design/semantic_ingestion_architecture.md`, especially Section 3.23.4.2.1
- `docs/development/static_tooling.md`
- `docs/work/semantic_ingestion/layer1-validator-unicode-map-closure-2026-07-29/design.plan.md`

## Independently Reconstructed Requirements

| Requirement | Source | Design coverage | Acceptance criteria | Verification | Status |
| --- | --- | --- | --- | --- | --- |
| VUM-001 | Exact Unicode scalar preservation | Implemented | Recursive keys/values preserve exact scalar sequences; surrogates reject | Current self-test proves rejection but only one accepted non-ASCII enum value | changes required |
| VUM-002 | Strict UTF-8 marked payloads | Implemented | Valid non-ASCII accepts; invalid UTF-8/surrogates reject | Current self-test proves one precomposed value and invalid cases | changes required |
| VUM-003 | Exact canonical UTF-8 JSON | Implemented | No normalization/escaping drift; one final LF | Composed/decomposed and nested-key controls missing | changes required |
| VUM-004 | Exact two-argument map grammar | Implemented | Invalid arities reject and all valid sibling routes accept | Rejection family complete; valid projected routes incomplete | changes required |
| VUM-005 | Preserve valid collection/publication behavior | Implemented | `tuple[()]`, atomic failure, mode, and concurrency controls pass | Validator self-test and exact checker | approved |
| VUM-006 | Exact hermetic handoff | Implemented | Pins and two isolated replicas reproduce frozen authority | Exact checker and direct hash verification | approved |

## Contract And Evidence Boundaries

The architecture is not reopened. This review concerns whether the executable
design validator proves exact scalar preservation and the complete map grammar
family. Parent reference-compiler parity and PR workflow timing remain
implementation-owned. Remote CI is unavailable and is not represented as
design approval evidence.

## Confirmed Findings

### DREV-001: Unicode proof does not establish recursive exact preservation

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: verification
- Affected scenario and prevalence evidence: any valid non-ASCII nested string or object key, especially canonical-equivalent composed/decomposed sequences; this is a required canonical profile boundary, not a measured product-prevalence claim
- Design location: validator self-test accepted Unicode controls near the coordinated `NormativeExecutionEvidenceRecordBody.execution_result` mutation
- Governing source or requirement: architecture exact Unicode scalar/no normalization contract; VUM-001, VUM-002, and VUM-003
- Expected behavior: valid scalar sequences in keys and nested values remain byte-exact, composed and decomposed forms remain distinct, non-ASCII remains literal UTF-8, and output has exactly one LF
- Design behavior: implementation is recursive, but accepted evidence checks only one precomposed `café` enum substring; negative recursive surrogate controls do not prove valid recursive preservation
- Evidence: direct inspection of validator-owned Unicode self-tests and the successful exact checker
- Impact: a future normalization, escaping, or path-specific regression could pass the design self-test while violating exact-byte authority semantics
- Root invariant or contract boundary: canonical Unicode-scalar serialization
- Equivalence class and adjacent bypasses inspected: object key, nested value, marked payload, precomposed value, decomposed value, escaped output, and terminal-LF behavior
- Positive behavior that must remain valid: current coordinated `café` declaration/registry compilation and frozen ASCII authority identity
- Recommended invariant-level resolution: add canonical nested key/value controls containing both precomposed `café` and decomposed `cafe\u0301`; assert literal exact UTF-8, unequal encodings, compact sorted JSON, and one LF; extend the marked mutation as needed to prove no normalization
- Verification needed: validator self-test and exact two-replica checker
- Evidence maturity affected: deterministic design verification

### DREV-002: Map evidence proves rejection but not the valid sibling family

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: verification
- Affected scenario and prevalence evidence: valid two-argument maps in quoted, nested, reachable-alias, inherited, Protocol, and unprojected declaration routes; these are acceptance routes explicitly named by the WorkPlan
- Design location: validator map self-test following collection controls
- Governing source or requirement: VUM-004 and VUM-005 completion criteria
- Expected behavior: every listed route accepts an exact two-argument `dict[str, T]`; projected routes normalize to the expected map graph and unprojected routes compile without entering projection
- Design behavior: invalid one/three-argument routes are comprehensive, while positive normalization is direct-only plus unprojected alias and Protocol
- Evidence: direct inspection of the map rejection and valid-control loops
- Impact: an over-rejecting regression in a valid sibling route could pass the self-test and checker
- Root invariant or contract boundary: closed binary map declaration grammar
- Equivalence class and adjacent bypasses inspected: direct, whole-quoted, nested, reachable alias, inherited, Protocol parameter, and unprojected alias
- Positive behavior that must remain valid: current invalid arity rejection, direct map normalization, string-key projection policy, and `tuple[()]`
- Recommended invariant-level resolution: add valid controls for every sibling route and assert normalized map shape for projected fields or successful non-projection for Protocol/unprojected declarations
- Verification needed: validator self-test and exact two-replica checker
- Evidence maturity affected: deterministic design verification

## Requirements Coverage

VUM-005 and VUM-006 are approved. VUM-001 through VUM-004 remain implemented
but not yet completely evidenced. The correction remains bounded and the
architecture, registry, authority, checker, and profile identities are stable.

## Architecture And Feasibility

Both findings are self-test additions around already implemented invariants.
No runtime owner, public schema, persisted value, or independent implementation
changes. One writer can close both in one bounded remediation.

## Failure, Security, And Operations

Existing surrogate/invalid-UTF-8 rejection and atomic publication evidence
remain valid. The remediation adds accepted-path evidence and does not alter
failure ordering, target visibility, mode preservation, or checker audit
isolation.

## Verification And Evidence Maturity

Coordinator independently reran validator self-test, the exact two-replica
checker, Ruff, Pyright, `py_compile`, and `git diff --check`; all passed.
Passing evidence demonstrates current behavior but not the two missing
equivalence families, so approval remains withheld.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Residual risk | Status |
| --- | --- | --- | --- | --- | --- |
| Valid Unicode normalization regression | Only precomposed enum substring is checked | Exact scalar identity can drift | Add composed/decomposed nested key/value bytes | Low after remediation | active |
| Valid map route over-rejection | Negative family dominates self-test | Compatible declaration stops compiling | Add all valid sibling routes with graph assertions | Low after remediation | active |
| Parent consumer remains on old pin | Design correction approves without implementation handoff | PR gate does not enforce reviewed validator | Parent repin and full Layer1 review | External to this plan | parent-owned |

## Rejected Or Consolidated Findings

The spec and correctness reviewers reported no additional confirmed finding.
The correctness probe that an unprojected `dict[int, str]` compiles is not a
gap: this bounded preprojection rule governs arity, while string-key
compatibility remains a projected CTV map rule. Parent tuple, Protocol,
Literal/Annotated, and CI timing findings are implementation-owned and were
not duplicated here.

## Required Changes Before Approval

- Close DREV-001 with recursive exact-preservation and normalization-distinction controls.
- Close DREV-002 with the complete valid two-argument map route family.

## Non-Blocking Follow-Ups

After design approval, the parent implementation must repin the validator,
correct its own dictionary arity and tuple behavior, close Protocol and
metadata parity, partition the fixed-time CI proof, and rerun fresh whole
Layer1 reviews.

## Final Outcome

Changes required.

## Review Limitations

Remote CI, branch protection, parent implementation consumers, and later
semantic-ingestion runtime milestones were not reviewed.
