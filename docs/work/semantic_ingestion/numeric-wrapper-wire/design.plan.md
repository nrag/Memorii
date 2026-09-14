# Numeric Wrapper Wire Contract

- Work type: design
- Status: complete for the bounded specification amendment; implementation handed back
- Parent implementation: ../registry-publication/implementation.plan.md
- Baseline: semantic_ingestion_m5 at 191826cd3afb38bf605a337a71d576063b3bae5e,
  authorized dirty tree; observation design candidate
  215ab5f272d7b27589da04c9c1dd4a9fa0f1d8f01413d542ea72bffa4c924b9e.
- Coordinator owns the amendment and evidence; observation design promotion is
  recorded in promotion-verification.json. SIA and historical artifacts are unchanged.

## Problem And Scope

The approved TypeExpr grammar admits decimal and binary64 primitives. SIA names
their logical members and lexical rules but never fixes their wire shape. The
decimal numeric role lacks the encoding_spec_id required by the logical body.
The independent bounded source consultation confirmed both omissions. Existing
runtime searches find no numeric wrapper owner or codec to preserve. The old
CTV codec also lacks schema-selected enum decoding, so it cannot silently serve
as the new profile's body decoder.

This operation supplies only the missing wrapper forms and source association.
It does not change numeric precision, rounding, statistical acceptance, signing,
native digests, or the separate projection decision. The registry implementation
continues unaffected model construction; dependent numeric body-codec work waits.

## Proposed Decision

See proposal.md. Prefer exact model-map forms using the existing CTV map tag,
with explicit source-authored decimal encoding_spec_id. The serious alternative
is adding two new tags, which changes the literal profile grammar and adds outer
tag cases without improving the typed field selection needed in either approach.
Neither alternative is silently implemented or normative before approval.

## Acceptance And Evidence

Before promotion: approve one complete form; establish byte-exact feasibility
with independent literal examples and malformed cases; freeze proposal, source
baseline, matrix and experiment; obtain independent spec/correctness/test review.
After promotion, a separate implementation continuation updates parser/compiler,
schema codec, source package and vectors; it must not claim implementation from
design evidence. No live-provider evaluation is needed for this wire decision.

Authority chain: this amendment edits semantic_ingestion_observation.md only.
Its exact per-field numeric grammar feeds future profile-3 raw role authoring,
parser/compiler commitments and source/publication/deployment pins. The full
package and static decoder producer remain implementation work. The existing
SIA model-map algebra already accommodates the selected forms; architecture,
profile-2 CTV authority and structural fixtures remain byte-identical. The
verification matrix defines both branches and an unchanged-source regression.
No operational profile-3 publication exists to migrate in this tree.

Identity ledger: proposed code and wire names describe numeric wrappers and
encoding specifications; review identifiers occur only in this WorkPlan.
No planning coordinate enters a body, schema identifier or encoding-spec ID.

Budget: one coherent proposal, one full independent review and one consolidated
determinate correction. An unresolved user-owned wire decision blocks promotion.

## Next Action

None in this completed design operation. Implementation continues under
../registry-publication/implementation.plan.md.

## Feasibility Checkpoint

Root executed feasibility.py successfully with Python 3.12.14. feasibility.json
records five positive and fourteen negative cases, including byte-exact literal
forms and policy-ID mismatch rejection. This is proposal-only lexical evidence;
it does not establish production numeric range validation or independent compiler
parity. The user explicitly selected the existing-map recommendation on
2026-09-07. Both exact wrapper forms and the explicit decimal encoding-spec ID
are authorized. No external decision remains for this amendment. Independent
amendment review and source-chain refresh remain required before design closure.
Unaffected registry model checks continue in the parent implementation.
