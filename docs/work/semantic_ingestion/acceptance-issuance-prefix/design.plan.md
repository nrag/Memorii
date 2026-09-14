# Acceptance Issuance Prefix Reconstruction

- Work ID: semantic_ingestion/acceptance-issuance-prefix
- Work type: design
- Status: complete (bounded issuance-prefix correction only)
- Coordinator: root
- Parent WorkPlan: ../engineering-closure/implementation.plan.md
- Related WorkPlans: ../acceptance-authority-successor/design.plan.md
- Canonical inputs: SIA acceptance contract; preserved acceptance-authority and successor packets.
- Expected outputs: issuance-prefix amendment and bounded proof.

## Objective

Bind each approval release to one complete, authenticated key-history prefix at
issuance, while retaining a separate current-history reduction at evaluation.
No canonical or production behavior is changed by this packet.

## Completion Contract

The proposal must define closed shapes, a total order, head/sequence binding,
issuer selection, verification order, migration and artifact chain. The proof
must cover equal-time append, future-effective records inside an issuance
prefix, missing/head/sequence substitution, revocation after issuance, bounded
raw bytes and receipt-compatible lifecycle input. Root owns execution and review.

## Scope

Only this directory is writable. Existing acceptance models remain preserved;
the proof is a composed adapter design, not a production verifier.

## Next Action

Resume the parent engineering-closure WorkPlan for acceptance production
implementation and the separately pending canonical artifact promotion.

## Coordinator Reconstruction

2026-09-08: the delegated initial draft and its conformance action were rejected
on inspection: tests targeted a removed API, and neither variant exercised the
preserved verifier or bounded snapshot input. Root took sole ownership and replaced
them with an explicit composition of the preserved implementation. The raw public
entry now enforces the release snapshot reference and current-prefix continuation.
69 tests pass (56 unchanged predecessor, 13 new). This is model evidence only;
proposal limitations explicitly include protected repository traversal and crypto.
No approval, canonical promotion, production implementation or closure-row change
is claimed. A review must assess the coherent root candidate before more edits.

The first substantive review confirmed two determinate contract/verification
findings. Root corrected them in one consolidated action; 79 tests now pass
(56 preserved plus 23 new) in 0.64 seconds. Corrected candidate review is next;
old candidate.json remains preserved as the initial review identity.

Spec review confirmed the need for an atomic capture-to-issuance publication
rule; its suggested effective-time suffix prohibition was not adopted because
effective time is not append time. Root made the exact head/generation CAS rule
explicit and modeled successful/failed publication plus later equal-time append.
Test review's four coverage findings were confirmed and addressed together.
100 tests pass in 0.72s (56 preserved and 44 new); final bounded review pending.

## Completion

Final frozen candidate and all three independent approvals are recorded in
closure.md. 103 tests, Ruff and configured Pyright pass. Committed-pair lookup and
status-only CAS evidence close the final confirmed verification finding. This
packet has no remaining in-scope work; parent runtime/registry work stays open.
