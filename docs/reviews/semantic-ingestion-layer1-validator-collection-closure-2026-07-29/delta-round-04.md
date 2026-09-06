# Design Review: Layer 1 Validator Collection Grammar Closure

## Review Metadata

- Review ID: semantic-ingestion-layer1-validator-collection-closure-delta-04
- Review mode: delta
- Review outcome: Changes required
- Design path: `docs/design/semantic_ingestion_architecture.md` plus the linked executable validator and checker
- Design baseline: architecture SHA-256 `67bf2620a0379761853861e416efba0816045ef4bf88e4808e701a9ac3bc993e`; validator candidate SHA-256 `46af2e98583c524b21fe3202de695053dc6d939285604524e603c463f891e64c`; checker candidate SHA-256 `9e7e28196e9bb7ca7b50365937266d8330e6f26b16b43b94b8b0b588629fb240`
- Implementation baseline: `945d6ea03649ca13c800e84bcb9972797e0f0a31` with the current working-tree Layer1 candidate
- Review date: 2026-07-29
- Reviewers: fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer`; coordinator reconciliation
- Included scope: atomic authority publication, tuple boundary proof, checker isolation, content-addressed handoff, and deterministic evidence
- Excluded scope: unrelated semantic-ingestion behavior, implementation consumer repins, and remote CI execution

## Executive Assessment

The collection/type grammar, tuple boundary, pre-validation ordering, atomic
replacement core, and checker isolation are correct. Changes remain required
before approval: the failure matrix does not prove all claimed publication
outcomes, replacement silently changes an existing authority's access mode,
and an unsupported directory-open-for-sync is misreported as publication
failure after successful replacement.

## Governing Sources

- Root `AGENTS.md`, `.agent/PLANS.md`, and the build/review Design Skills
- `docs/design/semantic_ingestion_architecture.md`, Section 3.23.4.2.1
- `docs/work/semantic_ingestion/layer1-validator-collection-closure-2026-07-29/design.plan.md`
- Immutable delta reports 01 through 03 in this review directory

## Independently Reconstructed Requirements

| Requirement | Source | Design coverage | Acceptance criteria | Verification | Status |
| --- | --- | --- | --- | --- | --- |
| VLC-001 | Closed unary collections | Complete | Exactly one valid type argument; invalid shapes reject | Self-test and exact checker | locally verified |
| VLC-002 | Closed tuple grammar | Complete | Finite items or exact native `tuple[T, ...]`; quoted-child and zero-item boundaries proved | Self-test and exact checker | locally verified |
| VLC-003 | Content-addressed validator/checker | Complete | Exact identities reproduce unchanged authority under closed isolation | Exact two-replica checker | locally verified |
| VLC-004 | Fail-closed compatible publication | Partial | Validated bytes publish atomically; all failure states, cleanup, access mode, and unsupported-sync behavior are explicit | Deterministic failpoint and filesystem-state matrix | changes required |

## Contract And Evidence Boundaries

Pre-replace failures preserve an absent or pre-existing target. Successful
replacement exposes complete validated bytes. A real post-replace directory
sync failure is surfaced with complete new bytes already visible and no
rollback claim. Unsupported directory sync is not a publication failure. A
successful rewrite must preserve a pre-existing target's access mode, and a new
target must have an explicit documented mode.

## Confirmed Findings

### DREV-008: Publication evidence omits claimed failure and transition boundaries

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: verification / transactional failure recovery
- Affected scenario and prevalence evidence: Design-authority publication during partial-progress write, file sync, post-replace directory sync, invalid public input, and concurrent observation; this is trust-artifact verification without a product-prevalence claim.
- Design location: Validator `adversarial_self_test()` publication matrix
- Governing source or requirement: VLC-004 and the linked WorkPlan's explicit publication outcomes
- Expected behavior: Every pre-replace failure preserves the target and removes its temporary sibling; real directory-sync failure surfaces after complete replacement; public invalid `--write` never mutates the target; coordinated readers observe a proven old-to-new transition with no absent or partial state.
- Design behavior: Tests inject immediate write failure, zero progress, flush failure, and replace failure. They omit partial-progress-then-error, file-fsync failure, post-replace directory-fsync failure, and explicit temporary-sibling cleanup. The invalid case invokes a compile helper rather than the public process, and the reader can pass without proving both old and new observations.
- Evidence: Direct inspection of the failpoint table and reader synchronization; fresh reviewer executions of self-test and exact checker still pass with these branches unproved.
- Impact: The candidate can claim locally verified publication semantics while regressions in unexercised failure windows or cleanup remain undetected.
- Root invariant or contract boundary: Every publication state transition needs an external filesystem assertion independent of helper structure.
- Equivalence class and adjacent bypasses inspected: Absent/seeded target; immediate, zero-progress, partial-progress, flush, file-fsync, replace, and directory-fsync failures; temp cleanup; public invalid input; old/new reader transition.
- Positive behavior that must remain valid: Exact successful replacement, pre-validation, zero-progress rejection, unchanged canonical authority, and readers seeing only complete artifacts.
- Recommended invariant-level resolution: Add deterministic seams for file fsync and coordinated reader phases; complete the failure/cleanup matrix; run invalid input through the public `--write` entry point in a subprocess or equivalently isolated process boundary.
- Verification needed: The complete matrix above with target bytes, target existence, mode, temporary sibling inventory, raised/returned status, and both old/new reader digests.
- Evidence maturity affected: VLC-004 local verification

### DREV-009: Atomic replacement changes an existing authority's access mode

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: backward compatibility / public CLI behavior
- Affected scenario and prevalence evidence: Rewriting the repository's existing checked authority or another shared authority path; this is compatibility behavior without a product-prevalence claim.
- Design location: Validator `publish_authority_atomically()`
- Governing source or requirement: VLC-004 and the WorkPlan constraint that this tooling correction is not a compatibility change
- Expected behavior: Rewriting an existing regular target preserves its access mode; creation uses an explicitly documented mode.
- Design behavior: `tempfile.mkstemp()` creates mode `0600`; `os.replace()` installs that inode, changing the current `0644` authority to `0600`.
- Evidence: Fresh reproduction seeded a `0644` target, invoked the atomic publisher, and observed `0600`.
- Impact: Group/world readers can lose access even though content is correct.
- Root invariant or contract boundary: Atomic content replacement must preserve the compatible filesystem metadata that downstream readers rely on.
- Equivalence class and adjacent bypasses inspected: Existing regular target, absent target, restrictive target, resolved symlink target, and same-directory temporary inode.
- Positive behavior that must remain valid: Exact bytes, same-directory atomicity, private temporary visibility before replacement, and pre-replace target preservation.
- Recommended invariant-level resolution: Snapshot the existing regular target's access mode and apply it to the temporary file before replacement; define a deterministic created-target mode for absent targets.
- Verification needed: Seeded `0644` and restrictive-mode rewrites plus absent-target creation, asserting exact bytes and exact modes.
- Evidence maturity affected: VLC-004 compatibility

### DREV-010: Unsupported directory open for sync is reported as publication failure

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: failure recovery / cross-filesystem operability
- Affected scenario and prevalence evidence: A supported runtime on a filesystem that cannot open directories for fsync; this is cross-filesystem design tooling without a product-prevalence claim.
- Design location: Validator `_fsync_directory()`
- Governing source or requirement: VLC-004 and the WorkPlan's "where supported" directory-sync rule
- Expected behavior: `EINVAL`, `ENOTSUP`, or equivalent unsupported results from directory open or fsync are classified as unsupported; real I/O failures are surfaced after complete replacement.
- Design behavior: Unsupported errors are handled only around `os.fsync()`. An unsupported `os.open(directory, flags)` propagates after replacement.
- Evidence: Deterministic reproduction made directory open raise `ENOTSUP`; publication raised although the complete new target was visible.
- Impact: A successful publication is reported as failed, inviting unsafe or confusing retries.
- Root invariant or contract boundary: Unsupported durability enhancement is distinct from a real persistence failure and must be classified consistently across open and fsync.
- Equivalence class and adjacent bypasses inspected: Normal directory open/fsync, unsupported open, unsupported fsync, real open/fsync failure, and post-replace visibility.
- Positive behavior that must remain valid: Real post-replace I/O failures remain visible and never claim rollback.
- Recommended invariant-level resolution: Classify the platform's equivalent unsupported errnos for both open and fsync; retain failure for all other errors.
- Verification needed: Deterministic open and fsync unsupported/real-error cases with exact status and visible target assertions.
- Evidence maturity affected: VLC-004 operability

## Requirements Coverage

VLC-001 through VLC-003 are locally verified. VLC-004 remains partially
verified pending the consolidated publication correction.

## Architecture And Feasibility

The corrections are determinate and bounded to one publication owner, its
self-test seams, checker audit paths if process-level proof requires them, and
content-addressed documentation. They require no normative architecture,
registry, authority, profile, or production-runtime change.

## Failure, Security, And Operations

Private same-directory temporary files and atomic replacement are retained.
Mode preservation occurs only immediately before replacement. Unsupported sync
classification must remain narrow; real errors continue to surface.

## Verification And Evidence Maturity

The exact two-replica checker passes at validator `46af2e98...` and checker
`9e7e2819...`, reproducing authority `89a98fc1...`, 56 schemas, 240 enum rows,
and profile `20edd38a...`. Publication evidence and compatibility remain below
approval maturity.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Residual risk | Status |
| --- | --- | --- | --- | --- | --- |
| Unproved cleanup/failure branch | Partial write or sync fault | Stale temp or false completion claim | Complete deterministic failpoint matrix | Low | open |
| Reader permissions regress | Replacement inherits `0600` | Shared reader loses access | Preserve existing mode; define new mode | Low | open |
| Unsupported sync is retried as failure | Directory open lacks sync support | Duplicate/confusing execution | Narrow unsupported classification | Low | open |

## Rejected Or Consolidated Findings

The reviewers agree the tuple grammar, content-addressing, and checker isolation
are correct. DREV-007 is a parent implementation handoff, not a design defect;
the coordinator records the exact final candidate pair and consumer/matrix
actions in the parent WorkPlan without repinning implementation code before
approval.

## Required Changes Before Approval

Complete DREV-008 through DREV-010 in one publication-invariant correction,
rerun deterministic gates, then perform fresh three-role delta review.

## Non-Blocking Follow-Ups

After design approval, repin the workflow and both implementation test
consumers, implement the full public CLI matrix, and obtain remote CI and
branch-protection evidence when available.

## Final Outcome

Changes required.

## Review Limitations

Remote CI and production filesystems were not exercised.
