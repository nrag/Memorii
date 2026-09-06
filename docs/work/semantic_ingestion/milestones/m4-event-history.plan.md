# Event History, Replay, Trust, And Identity Milestone

- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Status: complete at candidate
  `58ec5cc5a1e463a934681facc81630c956c2197b`
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

## Final Candidate History And Closure Preconditions

Exact-SHA hosted run `34042442561` completed successfully at candidate
`58ec5cc`. Every required check is green and all three final reviewer approval
arrays are empty.
The first final-tree run passed 414 tests and found only a stale architecture
hash; after its correction the complete 415-case family passed under
warnings-as-errors in 2142.04s.

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

Candidate `21432be` is superseded: hosted checks found a private-symbol import
at the composite conflict-listing boundary, and public recovery proof found
that corrupt persisted progress could be mistaken for absence. The narrow
replacement exposes the shared validators publicly and makes corrupt checkpoint
recovery a typed noncommit while preserving the valid genesis path.

Candidate `53b5363` is superseded only for verification operability: the
corrected recovery module had no measured unit-shard duration and was assigned
to an already loaded shard. Its 17 node timings are now recorded, isolating the
601.629-second module within the existing 15-minute bound.

Candidate `7174670` is superseded after hosted full-suite execution exposed
stale test expectations for exact replay errors and fixture authority. The
tests now preserve the reviewed error identity and coordinator/host refresh
ownership rather than restoring retired wrappers or test-only runtime behavior.

Candidate `966cd15` is superseded only for verification operability. Its hosted
run cleared 44 jobs but the independent-process filesystem shard exposed a
process-local harness mutex and incoherent outer timeout. Candidate `58ec5cc`
uses two filesystem services over one JSONL store, leaves physical JSONL CAS as
the ordering authority, and passes the formerly failing selector locally and
in two independent reviewer reproductions. Its exact-SHA hosted run is
`34042442561`.

## Delegation And Review Gate

Use the root resume packet plus this file and the linked debug plan. The final
Terra reviewer cohort completed after the candidate freeze gate and returned
empty approval arrays.

## 2026-09-06 Revision-Bound Closure

The milestone is complete at the shared clean candidate after exact-SHA hosted
verification and final specification, correctness, and test review. The
administrative closure delta changes coordination records only and does not
alter the reviewed or tested candidate tree.

```yaml
base_revision: 2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93
reviewed_revision: 58ec5cc5a1e463a934681facc81630c956c2197b
tested_revision: 58ec5cc5a1e463a934681facc81630c956c2197b
tested_tree_digest: f66c7abf1f391b59fd8ea28f52576f301e3261f6
tree_state: clean committed candidate; later coordination-record-only closure artifacts are self-excluded
changed_surface_inventory_complete: true
scope_delta_resolved: true
authority_chains_complete: true
required_local_jobs:
  - repaired independent-process filesystem graph selector
  - production-entrypoint v14 ledger validation and five mutation probes
  - static and shard contract checks
  - configured Pyright, Ruff, compilation, and diff hygiene
passed_local_jobs:
  - repaired filesystem selector passed in 108.87s; independent reviewers reproduced it in 105.74s and 116.00s
  - production-entrypoint v14 ledger passed all five mutation probes
  - static and shard contracts passed 29 of 29 checks
  - configured Pyright reported 0 errors and 0 warnings; Ruff, compilation, and diff hygiene passed
historical_local_evidence:
  - earlier stabilization trees passed the broad acceptance, generation, scenario, projection-history, replay, source-progress, CTV, workflow, and canonical-evidence families
  - this historical local evidence is regression context, not exact-candidate certification
hosted_exact_sha_jobs:
  - all eight graph root/backend receipt jobs and their aggregate
  - semantic-ingestion acceptance, generation, scenario, projection-history, and umbrella jobs
  - all unit and terminal-persistence shards and aggregates
  - static analysis, package smoke, CTV, benchmark, and CodeQL checks
known_local_failures: []
failure_exclusions: []
workflow_identities:
  - PR Gates at .github/workflows/pr-gates.yml
  - CodeQL check rollup for PR 116
ci_event: pull_request
ci_executed_sha: 58ec5cc5a1e463a934681facc81630c956c2197b
ci_executed_ref: semantic-indexing-m4 at PR 116
remaining_validated_p1_p2: []
remaining_blocks_approval: []
remaining_changes_required: []
local_ci_parity: deterministic job owners passed locally; GitHub-only receipt and timing aggregation passed in the hosted run
acceptance_gate_inventory:
  - eight Bootstrap Graph Transaction Boundary jobs
  - Bootstrap Graph Transaction Boundary Aggregate
  - Semantic Ingestion Generation Closure
  - Semantic Ingestion Scenario Authority
  - Semantic Ingestion Acceptance
  - Semantic Projection History
  - Semantic Ingestion
  - Unit Tests and timing inventory
  - Semantic Terminal Persistence shards and timing inventory
  - Static Analysis, Package Smoke, CTV gates, benchmark gates, and CodeQL
github_run_urls:
  - https://github.com/nrag/Memorii/actions/runs/34042442561
pr_head_sha: 58ec5cc5a1e463a934681facc81630c956c2197b
pr_base_sha: 2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93
merge_base_sha: 2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93
required_checks_green: true
```
