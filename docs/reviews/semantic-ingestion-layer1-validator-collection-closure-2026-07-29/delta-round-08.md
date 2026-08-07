# Design Review: Layer 1 Validator Collection Grammar Closure

## Review Metadata

- Review ID: semantic-ingestion-layer1-validator-collection-closure-delta-08
- Review mode: delta
- Review outcome: Approved
- Design path: `docs/design/semantic_ingestion_architecture.md` plus the linked executable validator and checker
- Design baseline: architecture SHA-256 `67bf2620a0379761853861e416efba0816045ef4bf88e4808e701a9ac3bc993e`; validator SHA-256 `538a01f1a37772b71b224cb4d1456509f0644850eb7ebbc67a64374f4a3d13fc`; checker SHA-256 `2ca3da2c69b453e2107ab4e901345b4b5420288666561c566732849d56c811c1`
- Implementation baseline: `945d6ea03649ca13c800e84bcb9972797e0f0a31` with the current working-tree Layer1 candidate
- Review date: 2026-07-29
- Reviewers: replacement fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer`; coordinator reconciliation
- Included scope: complete VLC-001 through VLC-004 design-tooling boundary and DREV-015/DREV-016 remediation
- Excluded scope: implementation consumer repins, public implementation CLI matrix, and remote CI execution

## Executive Assessment

Approved. All three independent reviewers verified the five frozen identities
at review start and end and found no confirmed `blocks_approval` or
`changes_required` gap. The exact isolated checker, validator self-test, static
checks, collection grammar, snapshot isolation, startup and audit controls, and
atomic publication evidence support the bounded design claims.

## Governing Sources

- Root `AGENTS.md`, `.agent/PLANS.md`, and the build/review Design Skills
- `docs/design/semantic_ingestion_architecture.md`, Section 3.23.4.2.1
- `docs/development/static_tooling.md`
- `docs/work/semantic_ingestion/layer1-validator-collection-closure-2026-07-29/design.plan.md`
- Immutable delta reports 01 through 07

## Independently Reconstructed Requirements

| Requirement | Source | Design coverage | Acceptance criteria | Verification | Status |
| --- | --- | --- | --- | --- | --- |
| VLC-001 | Closed unary collections | Complete | Direct, quoted, nested, alias, inherited, and unprojected invalid shapes reject while valid controls remain | Validator self-test and exact checker | approved |
| VLC-002 | Closed tuple grammar | Complete | Finite, variadic, zero-item, duplicate-ellipsis, and quoted-child boundaries are explicit | Validator self-test and exact checker | approved |
| VLC-003 | Content-addressed isolated checker | Complete | Five hashes, captured snapshots, actual-entry rejection, shadow exclusion, exact audit denial, and two replicas agree | Exact `python3.12 -I` checker | approved |
| VLC-004 | Fail-closed compatible publication | Complete | Failure preservation, cleanup, modes, replacement, directory sync, and reader transition are proved | Validator self-test, Ruff, Pyright, and `py_compile` | approved |

## Contract And Evidence Boundaries

The reviewed security boundary is the canonical `python3.12 -I` invocation plus
the externally supplied checker hash. The post-import guard supplies an exact
clean non-isolated diagnostic but is not claimed to secure imports that already
ran. Replicas are materialized only from captured, verified bytes. Public
implementation execution and remote enforcement remain separate evidence.

## Confirmed Findings

None.

## Requirements Coverage

VLC-001 through VLC-004 are approved for the frozen design-tooling identities.
DREV-015 and DREV-016 are closed without changing the architecture, registry,
authority, profile, grammar semantics, or publication ordering.

## Architecture And Feasibility

The final design keeps one content-addressed authority path, one validator, and
one checker. It introduces no parallel source of truth or framework coupling.
The parent implementation can now repin its canonical workflow and tests to the
approved pair.

## Failure, Security, And Operations

Negative startup, undeclared access, mutation, write, flush, file-sync,
replacement, directory-sync, mode, cleanup, and concurrent-reader behavior are
represented by deterministic controls. The authority remains unchanged at
`89a98fc1e545f38c234ce42dbd164c85e3ddc6358856cca70e59dad7b1addc7b`.

## Verification And Evidence Maturity

The exact isolated checker reproduced 56 schemas, 240 enum rows, and two
byte-identical replicas. Validator self-test, Ruff, Pyright with zero findings,
`py_compile`, report validation, and `git diff --check` passed. All reviewers
reported identical start/end hashes.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Residual risk | Status |
| --- | --- | --- | --- | --- | --- |
| Consumer retains historical pins | Parent implementation is not updated | Approved design gate is not enforced | Revision-bound implementation repin and public CLI matrix | Low after parent gate | parent-owned |
| Remote enforcement unavailable | CI or branch protection is not provisioned | Local evidence is not repository-host enforcement | Obtain separate remote CI evidence | External | open |

## Rejected Or Consolidated Findings

DREV-015 and DREV-016 are resolved. A prior round-10 attempt reported transient
source movement, but no second digest or persistent changed bytes supported the
claim. The coordinator stopped that attempt, the user confirmed no external
edit, the exact candidate was refrozen, and all replacement reviewers verified
identical start/end hashes. That invalid attempt was not counted as a completed
review.

## Required Changes Before Approval

None.

## Non-Blocking Follow-Ups

The parent implementation must repin the workflow and both test consumers to
the approved validator/checker identities, require `python3.12 -I`, execute the
public absent/pre-seeded/valid publication matrix, and keep remote CI evidence
explicitly unavailable until observed.

## Final Outcome

Approved.

## Review Limitations

Implementation consumer repins, public implementation CLI execution, and
remote CI were not part of this design approval.
