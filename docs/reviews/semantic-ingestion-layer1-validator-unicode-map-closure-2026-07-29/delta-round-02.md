# Design Review: Layer 1 Validator Unicode And Map Grammar Closure

## Review Metadata

- Review ID: semantic-ingestion-layer1-validator-unicode-map-closure-delta-02
- Review mode: delta
- Review outcome: Approved
- Design path: `docs/design/semantic_ingestion_architecture.md` plus the linked executable validator and checker
- Design baseline: architecture SHA-256 `67bf2620a0379761853861e416efba0816045ef4bf88e4808e701a9ac3bc993e`; validator SHA-256 `830c63e33e8da7787aba57879e08587ecbbe583e25f00c225be3e24a19637d9c`; checker SHA-256 `2ca3da2c69b453e2107ab4e901345b4b5420288666561c566732849d56c811c1`
- Implementation baseline: `945d6ea03649ca13c800e84bcb9972797e0f0a31` with the current working-tree Layer1 candidate
- Review date: 2026-07-29
- Reviewers: fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer`; coordinator reconciliation
- Included scope: complete VUM-001 through VUM-006 correction and DREV-001/DREV-002 remediation
- Excluded scope: parent reference compiler, public implementation tests, CI job partitioning, remote CI, branch protection, and later semantic-ingestion milestones

## Executive Assessment

Approved. All three fresh reviewers found no confirmed `blocks_approval` or
`changes_required` finding. DREV-001 and DREV-002 are closed with
family-complete accepted-path evidence. The exact isolated checker, validator
self-test, static checks, unchanged authority/profile identities, and
content-addressed static-tooling command support the bounded design-tooling
claims.

## Governing Sources

- Root `AGENTS.md`, `.agent/PLANS.md`, and the build/review Design Skills
- `docs/design/semantic_ingestion_architecture.md`, especially Section 3.23.4.2.1
- `docs/development/static_tooling.md`
- `docs/work/semantic_ingestion/layer1-validator-unicode-map-closure-2026-07-29/design.plan.md`
- Immutable prior report `docs/reviews/semantic-ingestion-layer1-validator-unicode-map-closure-2026-07-29/delta-round-01.md`

## Independently Reconstructed Requirements

| Requirement | Source | Design coverage | Acceptance criteria | Verification | Status |
| --- | --- | --- | --- | --- | --- |
| VUM-001 | Exact recursive Unicode scalar preservation | Complete | Nested keys/values preserve composed/decomposed sequences; invalid scalars reject | Validator self-test and final review probes | approved |
| VUM-002 | Strict UTF-8 marked payloads | Complete | Valid non-ASCII is exact; invalid UTF-8/surrogates reject | Marked-payload self-test and checker | approved |
| VUM-003 | Exact canonical UTF-8 JSON | Complete | Literal UTF-8, sorted compact JSON, no normalization, one LF | Exact byte vector and composed/decomposed distinction | approved |
| VUM-004 | Exact two-argument map grammar | Complete | Invalid arities reject across all routes; valid sibling routes accept | Complete positive/negative route family | approved |
| VUM-005 | Preserve collection/publication compatibility | Complete | `tuple[()]`, modes, failure cleanup, and concurrency remain valid | Validator self-test and static checks | approved |
| VUM-006 | Exact hermetic handoff | Complete | Frozen pins and two isolated replicas reproduce authority | Exact `python3.12 -I` checker | approved |

## Contract And Evidence Boundaries

The two checker replicas establish hermetic deterministic reproducibility of
the reviewed validator; they are not independently authored compilers.
Independent compilation remains the parent implementation milestone. This
review does not claim remote CI or branch-protection enforcement.

## Confirmed Findings

None.

## Requirements Coverage

VUM-001 through VUM-006 are approved. DREV-001 and DREV-002 are resolved
without changing the architecture, registry, authority, profile, checker,
public runtime, or persisted semantics.

## Architecture And Feasibility

The correction keeps one design validator and one content-addressed checker.
Unicode and map behavior are recursive scalar and grammar invariants rather
than fixture-specific production branches. No parallel source of truth,
framework dependency, or speculative abstraction was added.

## Failure, Security, And Operations

Surrogate and invalid UTF-8 input reject before publication. Invalid map
declarations reject before projection can skip them. Existing exact-write,
flush, file-sync, atomic replacement, directory-sync, access-mode,
temporary-cleanup, and concurrent-reader controls remain green. Rollback
restores the prior validator/checker/static-tooling bundle and requires no data
migration because authority and profile bytes are unchanged.

## Verification And Evidence Maturity

The exact isolated checker reproduced authority SHA-256 `89a98fc1...`, 56
schemas, 240 enum rows, and two byte-identical replicas. Validator self-test,
Ruff, Pyright with zero findings, `py_compile`, both immutable report
validators, and `git diff --check` passed. All final reviewers inspected the
complete current files.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Residual risk | Status |
| --- | --- | --- | --- | --- | --- |
| Parent consumer retains historical validator pin | Implementation handoff is not completed | Approved correction is absent from PR enforcement | Parent repin plus public compiler/validator matrix | Low after handoff | parent-owned |
| Remote enforcement unavailable | CI or branch protection is not provisioned | Local evidence is not hosted enforcement | Obtain revision-bound remote evidence separately | External | open |
| Checker replicas mistaken for independent compiler | Evidence wording overstates maturity | Circular validation claim | Record hermetic reproducibility only; keep independent compiler requirement | Low | controlled |

## Rejected Or Consolidated Findings

DREV-001 and DREV-002 are resolved. The final test reviewer supplied one
non-blocking wording follow-up: describe the checker replicas as hermetic
reproducibility, not independent reproduction. This report uses the corrected
language. Parent tuple, Protocol, metadata, compiler dictionary, and CI timing
gaps remain implementation-owned.

## Required Changes Before Approval

None.

## Non-Blocking Follow-Ups

The parent implementation must repin the approved validator, align its
independent compiler map and tuple grammar, complete Protocol and
Literal/Annotated parity evidence, partition the fixed-time PR checks without
weakening selection, and run fresh whole-Layer1 reviews.

## Final Outcome

Approved.

## Review Limitations

Remote CI, branch protection, parent implementation consumers, and later
semantic-ingestion runtime milestones were not reviewed.
