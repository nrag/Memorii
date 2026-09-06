# Event History, Replay, Trust, And Identity Milestone

- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Status: active; candidates through `223e0cba` are superseded and the bounded
  read-set/owned-prefix correction is locally green pending one final freeze,
  hosted run, and independent review
- Requirements: SIA-R10, SIA-R18
- Active linked debugging WorkPlan: `docs/work/semantic_ingestion/conflict-authority-proof-failures-2026-08-04/debug.plan.md`
- Approved linked design: `docs/work/semantic_ingestion/semantic-conflict-introduction-authority-2026-08-04/design.plan.md`
- Historical authority: archive M4 headings and review rounds

## Objective

Reconstruct byte-equivalent authoritative graph, operations, observations,
artifact closure, temporal/trust overlays, and identity lineage from genesis
and signed checkpoints. Historical equal-version conflict must fail closed and
be exposed to agent harnesses as bounded user-attention items without guessing
a winner.

## Scope And Owners

Own the M4 boundary and eventual semantic event authority, observation ledger,
replay/checkpoint authority, projection history and scheduling, trust evolution,
identity lineage, conflict-attention materialization, provider/factory/cache/
Hermes composition, and required migrations. While the linked debugging
WorkPlan is active, it is the sole detailed owner of the in-flight
clarification-lifecycle changed surface, authority chain, gates, experiments,
known failures, and evidence. This packet retains only the link, current
status, compact summary, and completion dependency.

Exclude changing the frozen equal-version decision, choosing a newest timestamp
as an automatic winner, and any non-atomic after-commit conflict-file append.

## Required Behavior

- Genesis and checkpoint replay reconstruct exact active state.
- All record kinds, order permutations, exact duplicates, current-writer
  collisions, historical conflict, corruption, late arrival, trust decay,
  rekey/merge/split, and migration races are deterministic and fail closed.
- Semantic conflict introduction is committed in the same memory-plane CAS as
  the contested projection.
- The file ledger is a recoverable listing/clarification projection, not the
  canonical introduction owner.
- Provider and Hermes pulls include bounded conflict attention so the harness
  can ask the user; core Memorii never relies on a proactive callback.
- Clarification submission, claim, completion, supersession, retry, and recovery
  share canonical authority and serialize with natural projection successors.

## Completed Slices

- Temporal/policy projection and trust-decay contracts.
- Canonical graph and identity-lineage authority.
- Projection-history slices and reader/list pagination/remediation.
- Clarification/recovery and replay integration rounds recorded in the archive.
- Core typed conflict-authority input, same-store introduction/pointer
  preparation, v2 replay/checkpoint binding, and empty-authority v1 read path.
- Focused core evidence recorded in the archive includes projection/scheduler
  `25 passed` and policy-migration plus event-replay `64 passed`.

## Corrected Debugging Boundary

The 2026-09-04 closure audit found that the production replan proof encoded a
new delivery/source admission instead of an append-only replacement on the
original fence and that the coordinator caught a generic replay/integrity
exception instead of a dedicated stale-winner signal. Both confirmed P2
defects are corrected locally. Retained-attempt proof now covers exact
predecessor/successor result closure, execution-domain writes outside the
sealed read set, and typed semantic conflicts across memory and independent
JSONL. Accepted semantic winners advance globally sealed graph/ledger
partitions and therefore never use an unrelated-rebase path.

Earlier frozen review remediation closed
canonical supersession wire/retry, both submission-versus-projection orders,
clarification lost acknowledgements, and real reopened conflict-checkpoint
validation. That evidence remains regression input but does not close the newly
confirmed delivery-identity and exception-boundary defects.

The 2026-08-05 design-to-production audit proved this prerequisite belongs to
approved M3 transaction planning and was omitted from M3 production and
closure evidence. M3 is explicitly reopened; M4 is dependency-blocked rather
than adding a conflict-specific reset.

Until immutable candidate review, the historical unresolved closure arrays
remain:

- `remaining_validated_p1_p2: [semantic-conflict-introduction-unreachable]`
- `remaining_blocks_approval: [semantic-conflict-introduction-authority]`
- `remaining_changes_required: [semantic-conflict-introduction-unreachable]`

These arrays may be cleared only by revision-bound debug closure and milestone
review; passing a narrower slice is insufficient.

The linked debugging WorkPlan owns the detailed correction evidence. These
arrays may be cleared only by the final revision-bound review, not by the local
passing runs alone.

## Completion Evidence

- Every active read schema reconstructs byte-equivalent state from genesis and
  signed checkpoint.
- Equal-version permutations reject before exposure and create one durable,
  authorized attention item where user input is possible.
- Both forced clarification-win and projection-win orders prove one linearized
  outcome, correct supersession/replan behavior, exact retry, and no partial
  receipt/effect.
- Real JSONL reopen, lost acknowledgement, corruption, migration, trust,
  lineage, provider, factory, cache, composite, and Hermes paths pass.
- Complete workflow-selected M4 gates, generated artifacts, static checks, and
  revision/tree identities are recorded.
- Frozen specification, correctness, and test reviews leave no remaining
  validated P1/P2 or approval-required finding.

## Current Exact Next Action

Freeze the bounded replacement, then run the exact-SHA hosted checks and
whole-candidate reviews without adding scope. The first final-tree run passed
414 tests and found only a stale architecture hash; after its correction the
complete 415-case family passed under warnings-as-errors in 2142.04s.

Candidate `e13df701` is superseded because that preflight did not carry the
complete sealed `GraphReadSet` and the clarification JSONL case reopened only
inside the original interpreter. The bounded correction retains and validates
the full typed read set and runs the public winner/reopen proof in separate
interpreters. Positive external
activation remains an M5 obligation, not an M4 closure dependency.

Candidates `04a7303` and `223e0cba` are also superseded. The first lacked the
persisted read-set/token join; the second exposed that consecutive replacement
groups could conflict with the same attempt's own first effect. The corrected
boundary replans every unfinished group when the sealed snapshot advances and
accepts only the exact durable same-attempt revision prefix between consecutive
groups. It still rejects every intervening semantic writer.

## Delegation And Review Gate

Use the root resume packet plus this file and the linked debug plan. One
Terra-class writer owns overlapping edits; Spark roles handle distinct mapping
or triage. Do not launch the full Terra reviewer cohort until the candidate
freeze gate in `.agents/PLANS.md` is satisfied.
