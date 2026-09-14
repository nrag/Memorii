# Observation Ledger Runtime Implementation

Work type: implementation. Status: active; exact preimage amendment accepted; bounded activation locally verified and independently approved.
Parent: ../engineering-closure/milestones/05-authenticated-observer-comparator.plan.md.
Related prerequisite: ../registry-publication/implementation.plan.md.
Approved design: design-candidate-final.json,
215ab5f272d7b27589da04c9c1dd4a9fa0f1d8f01413d542ea72bffa4c924b9e.
Baseline: semantic_ingestion_m5, HEAD191826cd3afb38bf605a337a71d576063b3bae5e,
authorized dirty tree. Preserve prior work and unrelated scoped-context evidence.

## Scope And Authority

Implement the approved globally ordered observation ledger through existing
writer admission and atomic store owners, then durable replay/checkpoints and
public authenticated snapshots. Registry construction is a prerequisite, not
activation authority. R17/R19 remain partial until reachable production paths,
independent comparison and final candidate evidence close their requirements.
The acceptance-authority R14 design remains separately blocked; production
release signing is deferred by user instruction.

Read canonical semantic_ingestion_observation.md and governing spec/storage/event/
implementation rules before edits. closed-contracts.md, replay-snapshot-contract.md
and native-projection-binding.md supply approved construction details. The old
transaction-boundary.md explicitly labels its circular proposal superseded; do
not implement that draft. Reject the previously incorrect activation map report.

## Milestones And Boundaries

1. Registry-selected artifact emission and activation: explicit typed admission/
   binding activation coordinate, legacy byte preservation, store-owned draining,
   complete inventory from read_write_snapshot, exact full revision CAS, atomic
   activation/genesis/successor admission, finite rescan retries and idempotent
   reload. No forced completion of live operations.
2. Global append through actual group/source atomic store routes: immutable
   receipt and complete native projection/event/replay evidence in one CAS,
   source intent retained, exact head ordering and lost-acknowledgement reload
   after later groups. Governed policy disables old mutation grammar after
   activation across all write routes.
3. Durable replay and checkpoint authority: independently loaded expected head,
   complete prefix/results/graph links, lifecycle chain/floor/key/clock checks,
   signed fixed preimage and atomic bundle/receipt publication. Pure integrity
   helpers alone grant none of these authorities.
4. Public authorized snapshot/paging through ProviderMemoryService, separate
   temporal/trust selection, complete streams and independent comparison.

Use one indexed milestone packet per bounded implementation unit before edits.
No persisted identity may be named after these work milestones.

## Verified Starting Boundaries

MemoryPlaneService.read_write_snapshot() returns the full detached inventory and
write revision; conditionally_write_records(expected_write_revision=...) forwards
that guard to the existing store and rejects UOW use. The primitive is previously
independently approved. WriterAdmissionStore.transition() is delivery migration,
and advance_policy_epoch() is specifically constrained to projection publication
by governed policy. Neither is a ledger activation route. Existing admission
and commit binding types have no observation activation coordinate.

Registry history is verified by the built-in capability and shared by paired
writer/store. Reader/candidate/integrity helpers need actual ledger runtime
callers. Canonical observation activation/head/entry/replay types exist but no
durable activation/replay owner is claimed.

## Verification Portfolio

| Boundary | Required proof |
| --- | --- |
| Activation | Live/leased controls block; late control or unrelated root batch breaks full-snapshot CAS; retry rescans; identical activation reloads; conflicting intent fails |
| Writer compatibility | Exact historical admission/binding bytes retained; all legacy post-activation mutations reject through ordinary, UOW and atomic routes |
| Append and reload | Concurrent sources share one head; failed CAS publishes no members; lost acknowledgement after later append returns original immutable receipt |
| Replay | Missing/extra/reordered/duplicate entries and substituted result/graph links reject; a valid short prefix cannot claim expected-head completeness |
| Checkpoint | Wrong repo/activation/lifecycle/key/time/floor reject; failed snapshot CAS publishes neither bundle nor receipt; signing alone cannot activate |
| Observation | Authorization before lookup; one snapshot for all authorities; separate projection histories; changed revision or expired cursor rejects without partial page |

Root owns pytest/long processes/generated evidence. Exactly one Terra writer
owns overlapping changes; Spark may map a narrow read-only caller question.
Standard spec/correctness/test reviewers inspect a frozen coherent milestone
once, followed only by affected finite deltas. Each delegation records scope,
model tier, evidence and result in its milestone packet.

## Completion And Budget

User instruction: commit and push each completed, verified round of fixes to
the current remote branch. Preserve unrelated working-tree changes and record
remaining implementation work without claiming parent closure.

One construction pass and one consolidated correction per bounded milestone;
confirmed new contract ambiguity stops for a design decision rather than a
permissive fallback. Required local jobs follow current workflows, not this
handwritten portfolio. Final closure needs exact-candidate CI, all authority
chains/generated pins, compatibility, portable evidence and whole-branch review.
No parent completion from focused tests or helper approval.

## Next Action

Complete both registered paging endpoints and their detached production cohort
and provider binding in `milestones/continuation-runtime.plan.md`, including the
pending activated failure-family proofs from `milestones/append-replay.plan.md`.

## Current Construction Boundary (2026-09-08)

Registered global append assembly, detached group/source replay joins, retained
native projection evidence, snapshot-only projection readers and graph paging
mechanics are implemented. The current production candidate enables activated
mutations through closed writer validation and canonical detached replay. Two
ordinary provider sources produced four ledger entries; corrected JSONL
reopen/retry passes1 test1269.55s, consolidated regression passes281 tests1108.52s
and compatibility delta passes160 tests69.31s. Code/spec reviews found no further
concrete defect; activated failure-family proof remains required. Graph paging has a
fixture cohort integration test, not a production backend/provider binding.
Ingestion-time continuation's cursor/request mismatch is resolved by the approved
`../ingestion-time-continuation/closure.md` amendment, now promoted to the governing
observation design. Registered runtime and real detached cohort integration are
active; design approval alone does not close those production requirements.
R17/R19 and all parent closure claims remain partial. The active packet records
local checks, bounded independent correction review, and evidence still needed.

## Preflight Delegation

Spark code-mapper observation_activation_bindings receives one read-only question:
exact admission/binding codec, digest and validation consumers for the approved
activation coordinate, plus existing legacy-byte omission mechanisms. At most
12 focused reads/searches and 900 words; no tests or writes. Root independently
checks symbols and call paths. This can proceed while the registry worker finishes
its disjoint checkpoint tests; it is not authorization to modify activation code
before the bounded readiness packet is ready.
