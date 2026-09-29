# Projection-Era Compatibility Design WorkPlan

- Work type: design
- Delivery fidelity: Level 2 for the first installed no-key journey and common upgrade read
- Status: complete for the bounded Level 2 design correction; implementation proof remains milestone 1 work
- Coordinator: `/root`
- Created: 2026-09-26
- Parent: `implementation.plan.md`, milestone `milestones/structured-fact-no-key.plan.md`
- Related completed design: `design-compatibility-and-hermes.plan.md`
- Canonical output: a narrow correction to `docs/design/learned_ontology_hermes_and_legacy_addendum.md`

## Problem And Evidence

The reviewed addendum demands a persisted schema-1 `bootstrap_v3_claim_assertion` projection produced by its original writer. The projection type first appears in `memorii/core/memory_evolution/record_projection.py` at historical commit `ea64d2c0` (the preceding `32cd8b7d` writer has no such projection). At `ea64d2c0`, the group writer selects `group_result_schema_version=2` or `3` when it emits native observations and their runtime projections. The current writer likewise selects 2 or 3 for that path. Its unadorned schema-1 group can exist without the native projection path. Therefore the required positive fixture is not a valid historical acceptance target for this record type.

The original approved design's OLE-05 behavior remains: pre-catalog facts retain their historical meaning and original fact grant, and a missing or corrupt proof returns unavailable with zero items/counts. New retained structured operations never fall back to a legacy path. No catalog owner/digest is inferred from the current package.

## Bounded Decision And Alternatives

Correct the legacy reader to accept the authentic projection-era group versions 2 and 3, using each version's own typed native projection publication and immutable group closure. Do not synthesize or downgrade a modern record to schema 1. A second possibility, leaving all old reads unavailable, fails the approved compatibility requirement. A migration that assigns the new seed to old facts would invent historical meaning. Schema-1 group records with no runtime projection need no runtime-projection reader; the initial reader does not create them.

The correction must specify exact versioned receipts and ledgers, source/admission, group/effect/event joins, original fact grant, mixed-history behavior, and fail-closed handling. No public name, persisted field, or new authority is introduced by this design delta; the identity ledger remains the existing group/result/projection grammar. The first-party Hermes tool contract is unchanged. The current partial schema-1 reader is implementation evidence only and must not be treated as a positive compatibility proof.

## Verification And Completion

Use a genuine current or original projection-era writer to persist a pre-catalog claim, then read it through the actual protected production root beside a new catalog-bound claim. Verify current-grant denial, single-snapshot use, restart, missing/corrupt version-specific proof, and unrelated scope isolation. A synthetic object returning `verified` does not prove compatibility. Freeze the corrected addendum digest and run independent spec, correctness and test delta reviews; reconcile all P1/P2 findings. Only then resume implementation. Level 3 migration, rollback and release evidence remain with the parent implementation WorkPlan.

## Progress And Next Action

2026-09-26: historical source search disproved the schema-1 positive fixture premise after two bounded historical fixture attempts. The existing addendum is reviewed but its schema-1 projection acceptance paragraph is superseded pending this correction. Milestone 1 remains the only active implementation milestone, with 0/6 complete. No later milestone has begun.

The coordinator replaced the schema-1 runtime-reader contract with a projection-era schema-2/3 proof: original source/admission and group/effects, immutable observation ledger, native projection receipt/replay evidence, graph delta/event batch and exact regenerated projection; schema 3 additionally requires its immutable commit attestation. The frozen semantic candidate was SHA-256 `540fa12e3ae622ee49d583a130bad3c7d8b31b592264d6b3aa9845259b6fe333`; a subsequent status-line-only edit does not change the contract. Targeted spec audit found no concrete gap and confirmed the historical version evidence. Targeted correctness and test reviews remain pending. The existing partial code still checks schema 1 only; no product old-read proof is claimed.

Targeted cohort classification: spec audit found no concrete design gap. Test review's absent authentic positive, closure mutation, restart and grant proofs are confirmed implementation gaps already owned by milestone 1; they do not invalidate the design. Its separate schema-2 and schema-3 fixture request is a confirmed P2 `changes_required` design matrix gap, now added. Correctness review found a confirmed P2 `changes_required` historical checkpoint issue: the ordinary native conflict verifier compares the old signed binding to today's mutable conflict tip, which would reject an old claim after a later unrelated conflict update. The addendum now specifies signature/digest/repository validation of immutable historical conflict binding without a current-tip comparison, retained temporal/trust prefix validation, and both-version positive and corruption fixtures after a later conflict transition. Revised addendum SHA-256 `74913836324138f2f7bbc9f3466edbd7a747e89199ed404ba33f5d5b2a0e578f`; targeted correctness and test rechecks are pending. No implementation legacy-reader acceptance is claimed.

Final targeted rechecks: the test reviewer found three further P2 matrix omissions (single snapshot/release grant race, source-admission-index corruption, and malformed historical checkpoint/binding plus nonmutating reopen). All were added. At frozen addendum SHA-256 `c4862606ccd0d5973ff064eece0914de993986252566a97d2221c48226466703`, the targeted correctness reviewer confirmed the signed v2 checkpoint covers the typed repository-bound historical conflict binding and found no residual P1/P2; the test reviewer found no residual P1/P2 in the bounded matrix. The earlier spec audit found no gap in the corrected schema-2/3 authority chain. `remaining_validated_p1_p2: []` for this design delta only. The first implementation milestone remains active and unapproved; code still needs an authentic projection-era positive read and installed Hermes journey.

**Handoff action:** resume the sole implementation milestone using the reviewed projection-era contract; prove separate authentic schema-2 and schema-3 protected reads after the installed Hermes slice reaches its bounded checkpoint.
