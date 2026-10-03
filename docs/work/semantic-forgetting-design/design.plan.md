# Semantic Forgetting (Revocation) Design

- Work ID: semantic-forgetting-design
- Work type: design
- Delivery fidelity: Level 2 (early real-world testing) — see `AGENTS.md`; the
  design must make real forget journeys work across happy scenarios and common
  operational failures while preserving authorization, persistence, recovery,
  and universal invariants. Adversarial tamper matrices, hostile-storage
  hardening, performance budgets, and exact-release evidence are recorded
  Level 3 deferrals.
- Status: complete
- Coordinator: main Codex thread
- Created: 2026-10-01
- Last updated: 2026-10-02
- Parent WorkPlan: docs/work/durable-memory-implementation/implementation.plan.md
  (requirement DUR-09 recorded the epoch open item this design closes)
- Related WorkPlans: docs/work/durable-runtime-design/design.plan.md (governing
  control-plane design authoring operation)
- Canonical inputs:
  - docs/design/durable_execution_and_solver_runtime.md (forgetting/erasure/
    retention section lines 349-357; epoch/Tier A lines 234-236, 275)
  - docs/design/memorii_spec.md (backtracking is revision, not deletion)
  - docs/design/event_model.md (7.3 delete marks, never physically removes)
  - memorii/core/semantic_ingestion/event_replay.py (replay fold, registry)
  - memorii/core/memory_evolution/atomic_store.py (replay authority,
    publication CAS)
  - memorii/core/storage_administration/operator_governance.py (current forget)
- Expected outputs:
  - docs/design/semantic_forgetting.md (new canonical design)
  - amendment to docs/design/durable_execution_and_solver_runtime.md forget
    paragraph (epoch contract correction)
  - this WorkPlan with review and closure evidence

## Objective

Produce the approved canonical design for logical forgetting as replayable
revocation: an owner-only operation that durably guarantees a named semantic
identity (entity, relation, fact, or source) is never served again through any
production serving path, while append-only history, audit, and restore
guarantees are preserved. Replace the current task-id-only suppression journal
enforcement with enforcement derived from a single revocation authority that
every serving path inherits, and close the recorded eligibility-epoch open
item with a pending-increment-riding-publication contract.

## Completion Contract

The design is complete when:

1. docs/design/semantic_forgetting.md exists with every design section listed
   in `.agents/PLANS.md` (problem, requirements ledger with stable IDs and
   measurable acceptance criteria, non-goals, existing-system analysis,
   alternatives with rejection rationale, feasibility evidence, failure and
   operational analysis, verification strategy covering every requirement).
2. The serving-path inventory in the design covers every production path
   enumerated by the repository survey (replay plane, evolution-record plane,
   solver/execution plane, control/export plane) and names the enforcement
   mechanism for each.
3. The epoch contract amendment is written into
   docs/design/durable_execution_and_solver_runtime.md and reconciles the
   Tier A finalized-tuple equality (service.py `_verified_snapshot_locked`)
   with forget-driven epoch increments.
4. The three standard reviewers (spec_auditor, correctness_reviewer,
   test_reviewer) reviewed the frozen draft; every finding is dispositioned
   per the classification contract; no validated P1/P2 design defect remains.
5. An implementation WorkPlan can be created from the design without hidden
   conversational context (self-containment check by a fresh reader).

## Scope

Included:

- semantic-plane revocation event contract and replay/projection semantics
- evolution-record plane tombstone contract
- solver/execution-plane revalidation contract
- control-plane forget plan/apply sequencing, journal typing, epoch pending
  increments, restore reconciliation
- schema/codec/publication authority-chain consequences
- verification strategy including the cross-path parity acceptance test
- amendment of the governing forget paragraph

Excluded (separate operations if ever needed):

- implementation of this design (separate linked implementation WorkPlan)
- physical selective record erasure (governing doc: unsupported in v1)
- AEAD key rotation ceremony (parked with the owner)
- benchmark/performance work

Explicitly deferred to Level 3+ (recorded, not blocking):

- adversarial suppression-journal tamper/spoof matrix beyond fail-closed decode
- hostile-storage hardening of journal files
- measured latency budgets for forget apply and reconciliation
- cross-version compatibility evidence beyond the fail-closed rule

## Constraints And Invariants

- Universal invariants (AGENTS.md): candidate vs committed, append-only event
  history (revision, never deletion), fail-closed closed unions, no model
  output mutates committed truth, raw observations distinct from derived
  projections.
- Replay authority: persisted `SemanticReplayState` must equal genesis
  reconstruction from event batches alone (atomic_store
  `_semantic_replay_state_from`); therefore revocation MUST be represented in
  the batch log, not only in control state.
- Fold discipline: `_apply_semantic_event_batch` is kind-agnostic and never
  removes materialized records; event_model.md 7.3 (delete marks, does not
  physically remove) governs.
- Tier A: finalized tuple epoch must equal control-state epoch at every
  verified read; no control-only epoch bump may be observable.
- Forget is owner-only (OwnerCapability), barrier-gated, and never model- or
  host-initiated.
- Suppression identifiers are content-free (opaque coordinates or
  installation-keyed tags, never source text or raw user identifiers).

## Identity And Coordinate Hygiene

| Surface | Proposed or existing identity | Class | Behavioral owner or protocol meaning | Retain, rename, migrate, or reject | Proof |
| --- | --- | --- | --- | --- | --- |
| record kind literal | `revocation_directive` | protocol | semantic event record kind marking identities never-to-be-served | new; behavioral | closed `GraphRecordKind` union, registry schema role |
| record model | `RevocationDirectiveRecord` | behavioral | pydantic carrier for the record kind | new | graph_records.py canonical owner |
| claim lifecycle member | `revoked` (ClaimLifecycleState) | protocol | persisted claim tombstone state | new enum member | models.py closed StrEnum |
| entity-link lifecycle member | `revoked` | protocol | persisted entity-link tombstone state | new enum member | state repository gate |
| control field | `pending_epoch_increments` | persisted | increments awaiting the next publication tuple | new | InstallationControlState |
| control journal operation | `logical_forget_applied` | existing protocol | forget journal entry | retain | contracts.py closed Literal |
| suppression journal content | `forget-journal` versioned envelope with `suppression_id`, `plan_digest`, `closure_digest` | persisted | durable revocation watermark | migrate from untyped dict; v1 accepted as legacy | control/suppressions files |
| event schema version | `memorii.semantic-memory-event.v2` | protocol | envelope grammar including the new record kind | new; v1 deprecated-readable with identity upcaster | SemanticEventSchemaRegistry |
| CLI | existing `forget` subcommands | existing | owner surface | retain | memorii/tools/runtime_operator.py |
| requirement IDs | `FGT-Rn` | planning/evidence coordinate | traceability only | never in code/test names | this ledger |

Mutation coverage for the identity gate is an implementation-WorkPlan
obligation; this design records the naming contract.

## Change Impact And Verification Closure

Design-only operation: expected changed surfaces are
docs/design/semantic_forgetting.md (new),
docs/design/durable_execution_and_solver_runtime.md (amended paragraph), and
this WorkPlan directory. No production code, tests, generated artifacts, or
workflows change in this operation. The design's authority-chain ledger
(section: schema and publication consequences) enumerates what a later
implementation must regenerate.

Gate ledger: documentation-only change; the applicable required gate is the
reviewer cohort plus CI green on the documentation-touching commit (no
code-path gates apply).

## Sources Of Truth

Precedence per AGENTS.md. For this operation: memorii_spec.md and
event_model.md govern semantics; durable_execution_and_solver_runtime.md
governs the control plane and is itself amended by this design (recorded
amendment, not silent selection); production code evidence as cited in the
design's existing-system analysis.

## Current State

Verified facts (2026-10-02 survey, three parallel read-only explorers plus
coordinator spot-checks):

- The replay fold is kind-agnostic; records are replaced, never removed;
  `MutationKind` is `create|update` only (event_replay.py:98, 1425-1483).
- Serving reads split across two planes: replay-fed (graph observation,
  identity lineage, entity matches) and direct evolution-record reads
  (retrieval, prefetch evolution channel, scoped context, structured facts,
  runtime step) which bypass replay entirely.
- `plan_forget` enumerates only `runtime_tasks` task ids; the suppression
  journal's only serving consumer is `read_export`
  (operator.py:144-177). No semantic enumeration or closure exists.
- `apply_forget` requires the read_only barrier, writes the journal, bumps
  control_revision only; its comment claims an epoch bump that no code
  performs (operator_governance.py:174-194).
- Tier A epoch equality is enforced at service.py:703-706; a control-only
  epoch bump breaks every verified read until a next publication realigns.
- Governing doc lines 349-357 already specify closure, content-free ids,
  revalidation_required, and an epoch increment sentence that collides with
  Tier A (the recorded open item, DUR-09).
- Adding a record kind requires: closed-union edits, codec manifest totality,
  reference-schema manifest edges, typed-value publication regeneration
  (`memorii/scripts/generate_observation_registry_publication.py`), and
  release-preparation candidate repin.

Interpretation (not fact): the dual-plane architecture is stable and must be
treated as given; revocation enforced at replay alone cannot reach the
evolution-record plane.

## Assumptions And Open Questions

Verified facts: see Current State. Working assumptions: memory-plane derived
records (claim_state, entity_link) may be version-rewritten through the
normal publication path with owner authority; restore preserves suppression
journal filenames (so derived suppression ids remain stable). Unresolved
questions: none blocking; the owner's conceptual choice (revocation distinct
from correction) was confirmed in conversation and matches the governing
four-operation separation. Decisions requiring external input: none; the
owner already approved this design delta.

## Milestones Or Experiments

1. Baseline survey (three explorers + spot-checks) — complete; evidence in
   Current State and the design's existing-system analysis.
2. Draft design + governing amendment — in progress; artifact
   docs/design/semantic_forgetting.md.
3. Reviewer cohort on the frozen draft; reconcile findings; remediate
   validated P1/P2; converge.
4. Final whole-design review; closure record; handoff summary for an
   implementation WorkPlan.

## Progress Log

- 2026-10-02: Verified repository state (branch codex/durable-memory-release
  at 67ce38a7; owner's uncommitted files untouched). Loaded build-design
  skill and PLANS.md. Ran three parallel read-only surveys (replay authority,
  serving paths, control plane/epoch) and coordinator spot-checks of the four
  load-bearing claims. Next action: write the design draft.
- 2026-10-02: Created this WorkPlan; drafting
  docs/design/semantic_forgetting.md next.
- 2026-10-02: Drafted docs/design/semantic_forgetting.md (14 sections:
  plain-language summary with worked example and jargon table, problem
  definition, sources/precedence, existing-system analysis with file:line
  evidence and feasibility evidence, four-operation distinction, contracts
  §6.1-§6.10 for the directive record / replay projection / tombstones +
  reader-edit ledger / closure / solver marking / control-plane sequence /
  revoked-identity view / serving matrix / epoch / authority chain, failure
  analysis, security analysis, non-goals, verification strategy incl. the
  parity family, seven alternatives with rejection rationale, requirements
  ledger FGT-R1..R17, open questions, governing amendment). Applied the §14
  amendment to durable_execution_and_solver_runtime.md (epoch sentence).
  Candidate frozen for review. Next action: launch the three-reviewer
  cohort on the frozen draft.
- 2026-10-02: Round 1 (three reviewers, parallel): nine validated P2 design
  defects (lineage audit leak, plan input contract, suppression-id
  stability, unreachable authoring path, tombstone reader edits, epoch
  finalize crash window, view ownership, entity-match contradiction,
  query-surface enumeration) + P3 evidence actions. Remediation batch
  applied (full rewrite); all details in the Review Log. Next action:
  delta review.
- 2026-10-02: Round 2 (delta, three reviewers): every round-1 finding
  verified resolved at file:line; all new findings P3; no new validated
  P1/P2 → converged per the non-convergence rule. Applied the reviewers'
  one-clause P3 prescriptions (13 items, Review Log round 2). Next action:
  Phase 7 closure.
- 2026-10-02: Phase 7 closure — fresh-reader self-containment check
  (verdict: self-contained; three stops + seven inconsistencies all
  resolved by determinate edits, recorded in the self-containment table);
  evidence-log closure record appended; design status header finalized;
  WorkPlan marked complete. Next operation: separate linked implementation
  WorkPlan.

## Decision Log

- 2026-10-02: Revocation is a first-class replayable record kind, not a
  MutationKind extension and not a per-path read filter. Alternatives and
  rationale in the design's Alternatives section. (Coordinator; grounded in
  the replay-equality invariant and event_model.md 7.3.)
- 2026-10-02: Delivery fidelity Level 2 for this design; adversarial and
  performance families recorded as deferrals.

## Review Log

### Round 1 (2026-10-02, frozen draft @ 67ce38a7 + dirty design surfaces)

Reviewers: spec_auditor, correctness_reviewer, test_reviewer (parallel,
read-only; each given the frozen draft, governing sources, and code entry
points). Coordinator validated the load-bearing refutations directly
(`retrieval_runtime.py:85,113`; `record_projection.py:216-223`;
`graph_records.py:262-278`; `event_replay.py:99-119`;
`provider/service.py:2047-2096`) before remediating.

Validated P2 findings → one remediation batch (remediation eligibility:
`eligible_p1_p2`):

| # | Finding (reviewer) | Classification | Disposition |
| --- | --- | --- | --- |
| 1 | Identity-lineage audit view is host-grant-backed, not owner-forensic; retaining revoked records there serves revoked literal text (spec_auditor 1; confirmed at provider/service.py:2047-2096) | P2 / changes_required / security + design completeness | confirmed → remediated: §6.8 lineage row (view applied to host-grant reads; complete retained view owner-capability only), §8, new R16 |
| 2 | `forget plan` scope resolution undefined; worked example implied free-text matching which cannot exist (spec_auditor 2) | P2 / changes_required / design completeness | confirmed → remediated: §6.4 typed selector union (mirrors revoked_targets), scope_note annotation-only; non-goal §9; alternative 7 |
| 3 | `suppression_id` derived from undefined "journal file identity" (timestamps) — retry circularity, restore/compaction instability; overlapping-scope rule missing (spec_auditor 5; correctness 7; test 4) | P2 / changes_required / architecture + compatibility | confirmed → merged and remediated: §6.1 content-coordinate derivation (installation id + plan_digest + closure_digest), retry by plan_digest lookup, union rule for overlapping directives, receipt counts newly-revoked only; §7 rows; §10.2 |
| 4 | Enforcement publication not reachable: no governance entry through OperationKind/carrier/delta/planning chain; four per-kind tables reject unknown kinds (correctness 1) | P2 / changes_required / architecture | confirmed (validated graph_record_id map + carrier tables) → remediated: §6.10 item 1 governance-owned delta entry (native group-commit precedent, writer enrollment, freeze guard, no OperationKind member); §4 authoring-path paragraph |
| 5 | Tombstone inheritance false at three reader/writer sites (denylist, RecordLifecycleState conversion, record_projection exhaustive dict) (correctness 2) | P2 / changes_required / runtime behavior | confirmed (validated all three) → remediated: §6.3 reader-edit ledger table; R3 criteria |
| 6 | Epoch finalize is a new control write with an unhandled crash window; resolve_pending_publication is an extra finalize site (correctness 3) | P2 / changes_required / failure handling | confirmed → remediated: §6.9 one-transaction finalize, recovery-site coverage, boot completion rule; §7 crash row; §10.3 |
| 7 | In-window revoked-identity view ownership/injection unspecified; tension with rejected alternative 1 (correctness 4) | P2 / changes_required / integration boundary | confirmed → remediated: new §6.7 single-owner view component (refresh points, injection roots, fail-closed composition) |
| 8 | §6.2.1 vs §6.2.2 contradiction: entity matching reads the integrity snapshot that retains revoked records (correctness 5) | P2 / changes_required / design completeness | confirmed → remediated: §6.8 entity-matching row (view check at reader, not lifecycle); §6.2.2 wording |
| 9 | Memory-plane query-surface matrix row circular ("paths this design touches") (test 1) | P2 / changes_required / verification | confirmed → remediated: §6.8 row binds every record-query endpoint without exception (scan/pagination/lookup/cursor) |

Non-P1/P2 findings (dispositions per the product-impact gate):

| # | Finding (reviewer) | Remediation eligibility | Disposition |
| --- | --- | --- | --- |
| 10 | No-un-forget irreversibility lacks requirement/test (spec_auditor 3) | evidence_action | accepted → §5 paragraph + new R17 (cheap, same edit) |
| 11 | §14 quote not literal; §3 precedence omissions (spec_auditor 4) | contract_conformance_action | confirmed → §14 exact applied text; §3 adds storage_details + IMPLEMENTATION_RULES |
| 12 | "consistent snapshot" undefined (spec_auditor 6) | record_only → folded | accepted → §6.4 names the mechanism (single partition read transaction) |
| 13 | Barrier release "or by apply completion" half-false; reconciliation owner + doctor read-only contract (spec_auditor 7; correctness 6) | record_only → folded | confirmed → §6.6 owner-resume-only release; boot resume hook owns reconciliation; doctor reports only |
| 14 | Version-rewrite presented as fact while WorkPlan held it as assumption (spec_auditor 9) | evidence_action | resolved → correctness reviewer verified mechanics (partition.py:890-933; factory.py:101-141); §6.3 + §12 now cite it |
| 15 | Matrix omitted legacy graph queries + derived index rows (spec_auditor 10) | record_only → folded | accepted → §6.8 rows added |
| 16 | Canonical-prefetch mechanism under-defined (RUNTIME_CONTEXT is visibility, not kind) (spec_auditor 11) | record_only → folded | accepted → §6.8 row: assembly-time view exclusion |
| 17 | R14/R5/R2 criteria vagueness (spec_auditor 12) | evidence_action | accepted → R14 fields enumerated; R5 selector contract; R2 view clauses |
| 18 | Absence oracle not operationalized (test 2) | evidence_action | accepted → §10.1 exhaustion + serialized scan + count arithmetic |
| 19 | Authorization negatives missing (test 3) | evidence_action | accepted → R6 criterion + §10.6 |
| 20 | Empty-plan + drift + barrier rows lacked test routes (test 5, 6) | evidence_action | accepted → §10.5 + §7 rows |
| 21 | Old-binary row honesty (test 7) | record_only | accepted → §6.3/§7 proxy-verification wording; Level 3 deferral recorded |
| 22 | CI gate names + file-list mechanics + family-vs-single-test (test 8) | evidence_action | accepted → §10 names durable-storage-integration + durable-runtime-integration, explicit lists, shared-fixture family |
| 23 | Citation fixes: script path, codec_by_kind typed failure (correctness 8) | contract_conformance_action | confirmed → §4/§6.10 corrected |
| 24 | Directive count exposed in integrity snapshot; logical_entity_id content-free verification (correctness 9) | record_only | accepted → §7 disclosure + §6.10 item 10 / §10.7 hygiene row |
| 25 | journal_version enumeration, retry-receipt recompute, registry-mismatch route (test 10) | evidence_action | accepted → §10.3 routes |

No unsupported or duplicate findings beyond the merges noted (3 = SA5+CR7+TR4).
No `blocks_approval` findings. Reviewer verdicts converged: not approvable
before remediation; all blocking findings determinate.

Remediation: one writer batch (2026-10-02) — full rewrite of
docs/design/semantic_forgetting.md incorporating all remediations (new §6.7
view component; renumbered 6.8 matrix / 6.9 epoch / 6.10 authority chain;
reader-edit ledger; governance entry; typed selectors; suppression-id
stability; epoch finalize recovery; R16/R17 added). Delta review pending.

### Round 2 — delta review (2026-10-02, post-remediation tree)

Reviewers: all three roles, targeted on the remediation delta against the
same code evidence. Verdicts: spec_auditor — all 12 round-1 findings
resolved, 5 new findings all P3/follow_up, "spec-complete for Level 2
approval"; correctness_reviewer — all 5 round-1 P2 findings mechanically
resolved (each verified at file:line, incl. the native group-commit
precedent at atomic_store.py:16571-16590 proving the governance delta
entry is constructible, the one-transaction control-write precedent at
control.py:232-255, and constructor-injection seams reaching every serving
root), 4 new findings all P3/follow_up, "implementation-handoff ready";
test_reviewer — 9/9 round-1 findings resolved, 6 new findings all
P3/follow_up, "testable as designed"; in-window parity confirmed drivable
with zero new hooks (read_only holds the post-journal/pre-publication
state deterministically).

No new validated P1/P2 defect → no further product-remediation round
(convergence rule). Coordinator classification of the new P3s:

| # | Finding (reviewer) | Disposition |
| --- | --- | --- |
| 1 | §3 mischaracterized storage_details / IMPLEMENTATION_RULES content (spec) | confirmed → applied as prescribed (descriptions corrected) |
| 2 | Idempotence layers (b)/(c) lacked ledger criteria (spec) | confirmed → applied (R6 criteria extended) |
| 3 | View fail-closed composition property lacked a requirement (spec) | confirmed → applied (R2 criterion) |
| 4 | Owner-forensic surface never specified; R16 "or" weakened determinism (spec + test) | confirmed → applied (§6.8 lineage row names the governance-operator forensic surface + OwnerCapability; R16 criteria split per-surface) |
| 5 | Epoch finalize unconditional clear could consume a later forget's pending increment in a crash interleaving (spec) | confirmed → applied (§6.9 decrement-by-consumed) |
| 6 | §4 prose implied structured_fact_read ALL_VERSIONS branch already safe (correctness) | confirmed → applied (prose corrected: :603-611 excludes only CANDIDATE) |
| 7 | View must not filter internal integrity readers sharing list_records (correctness) | confirmed → applied (§6.7 serving-endpoints-only clause; genesis-equality rationale) |
| 8 | Cursor-filter placement + no-counts-on-this-surface (correctness) | confirmed → applied (§6.8 row: pre-slice in-transaction; count arithmetic scoped to count-bearing endpoints) |
| 9 | Governance entry's OperationFenceBinding + SemanticWriterCommitBinding unspecified (correctness) | confirmed → applied (§6.10 item 1) |
| 10 | Per-path count deltas; serialization recipe; owner-surface carve-out (test) | confirmed → applied (§10.1 oracle pinned) |
| 11 | R17 probe set not enumerable (test) | confirmed → applied (R17 criteria) |
| 12 | unit-shards.json registration for unit-tier additions (test) | confirmed → applied (§10 CI placement) |
| 13 | Post-release enforcement trigger unnamed for live process (test) | confirmed → applied (§6.6 step 3: mode-resume drain owns it; boot hook + doctor report unchanged) |

Every new P3 was applied as prescribed (all were one-clause corrections
inside already-frozen boundaries; none changed product semantics beyond
the reviewers' prescriptions), so no third review round is warranted —
cost-awareness and non-convergence rules in `.agents/PLANS.md` apply.

### Phase 7 closure checks (2026-10-02)

- Requirements ledger rebuilt independently by the test reviewer's
  requirement-by-requirement table (round 1 + delta) and reconciled: 15+2
  requirements, every §6-§8 behavior covered or explicitly excluded
  (§9).
- Contract and evidence-maturity boundaries verified: all `specified`,
  derived artifacts `derivable` per §6.10, implementation/CI states
  explicitly deferred to the implementation WorkPlan.
- Every confirmed finding family closed: round-1 P2s remediated and
  delta-verified; all P3s applied or recorded above; no unsupported,
  duplicate (beyond recorded merges), or blocked findings remain.
- Identity ledger reconciled: no planning/evidence coordinate entered a
  behavioral or protocol identity (record kind, field names, enum members,
  journal versions, CLI names all behavioral; FGT-Rn/DUR-09 occur only as
  ledger/traceability values).
- Amendment authority chain: governing doc sentence replaced exactly; §14
  records the verbatim applied text (character-for-character match
  verified by the spec auditor).
- Self-containment: verified by an independent fresh-reader check (below).

### Self-containment check (fresh reader, 2026-10-02)

A reader with only AGENTS.md, PLANS.md, the design, this WorkPlan, and the
governing forget section produced a 6-milestone implementation outline
(schema authority chain → governance entry + view → tombstones/reader
ledger → control plane plan/apply/journal/epoch/reconciliation → serving
matrix completion + solver marking + forensic surface → parity/crash/CI
closure, each requirement allocated) and judged the design self-contained
for WorkPlan drafting, with three bounded semantic stops and seven
bookkeeping inconsistencies. Coordinator dispositions — all three stops
resolved by determinate design edits (no owner decision required):

| Stop / inconsistency | Disposition |
| --- | --- |
| runtime-task class-6 enforcement mechanism/predicate unwritten; predicate drifted §6.4 vs §6.5 | confirmed → unified predicate (observations' source ids, exact-id rule); §6.8 operator-inspection row added (view's revoked task-id set, export mechanism extended) |
| owner coordinate-discovery surface scope undecided | confirmed → bounded: verify an existing export/operator surface exposes selector coordinates (R5 criterion); no new discovery surface in scope |
| post-clean-abort enforcement liveness unwritten | confirmed → mode-resume drain retries until quiescent (§6.6 step 3 + §7 row) |
| design/WorkPlan state disagreement (headers said review pending) | confirmed → both finalized in this closure edit |
| dangling self-containment reference | confirmed → this record |
| script path citation (design vs WorkPlan vs disk) | confirmed against disk (`memorii/scripts/generate_observation_registry_publication.py`); design corrected; note: the round-2 correctness reviewer's "repo-root" prescription was wrong — reverted with direct `ls` evidence |
| §6.2.2 overstated the forensic surface scope | confirmed → wording scoped to retained lineage for named coordinates |
| missing Feasibility Evidence section (PLANS.md design-sections list) | confirmed → added to §4 (verified mechanics incl. governance-entry constructibility, one-transaction control-write precedent, injection seams) |
| memory-plane row enumeration incomplete vs governing query variants | confirmed → neighborhood/evidence/catalog-history variants added |
| R1..R15 progress-log reference vs R17 ledger | confirmed → progress log updated below |

## Evidence Log

```yaml
base_revision: 67ce38a7
reviewed_revision: worktree (docs-only candidate; see changed_surface_inventory_complete)
tested_revision: not_applicable (design-only operation; no code or test execution claimed)
tested_tree_digest: not_applicable
tree_state: design surfaces only — docs/design/semantic_forgetting.md (new),
  docs/design/durable_execution_and_solver_runtime.md (one amended sentence),
  docs/work/semantic-forgetting-design/ (this WorkPlan); owner's unrelated
  uncommitted files excluded from the candidate and untouched
changed_surface_inventory_complete: true
scope_delta_resolved: true
authority_chains_complete: true (design-level; §6.10 enumerates the
  implementation chain: per-kind tables, codec manifest, reference manifest,
  registry v2 + upcaster, publication regeneration via
  memorii/scripts/generate_observation_registry_publication.py, candidate repin)
required_local_jobs: [] (documentation-only change; no code path gates apply)
passed_local_jobs: []
known_local_failures: []
failure_exclusions: []
workflow_identities: [] (no workflow changes)
ci_event: pending commit (docs-only commit rides the PR's existing gates)
ci_executed_sha: not_applicable
ci_executed_ref: not_applicable
remaining_validated_p1_p2: []
remaining_blocks_approval: []
remaining_changes_required: []
local_ci_parity: not_applicable
acceptance_gate_inventory: [spec_auditor round 1, correctness_reviewer round 1,
  test_reviewer round 1, spec_auditor delta, correctness_reviewer delta,
  test_reviewer delta, fresh-reader self-containment check]
github_run_urls: []
pr_head_sha: pending commit
pr_base_sha: 67ce38a7
merge_base_sha: 67ce38a7
required_checks_green: not_applicable_for_design_operation
```

Review evidence: round-1 and round-2 (delta) reviewer reports are recorded
in the Review Log with per-finding dispositions; coordinator validated
load-bearing claims directly (fold/retrieval gates/projection map/identity
map/carrier tables/lineage surface/Tier A/forget flow/ClaimState enum,
plus the `ls` verification of the regeneration-script path).


## Blockers And Limits

None. Iteration budget: three review rounds before blocking.

## Next Action

None — the design operation is complete. The next operation is a separate
linked implementation WorkPlan (work type `implementation`) created from
docs/design/semantic_forgetting.md (baseline: this design at its committed
revision; requirement IDs FGT-R1..R17; the fresh reader's 6-milestone
outline in the self-containment record is a starting sketch, not a
constraint).

## Outcome And Retrospective

Final result: canonical design for revocation-based semantic forgetting
delivered and reviewed to convergence — docs/design/semantic_forgetting.md
(14 sections, requirements FGT-R1..R17), one recorded amendment to the
governing forget paragraph (epoch contract), and this WorkPlan. Two review
rounds (initial + delta) plus a fresh-reader self-containment check; nine
validated P2 design defects remediated in round 1 and delta-verified;
all round-2 P3 findings applied as prescribed or recorded; zero validated
P1/P2 remain.

Remaining limitations: Level 2 fidelity — old-binary refusal is verified
by strict-decode proxy only; adversarial tamper matrices, performance
budgets, and exact-release evidence are recorded Level 3 deferrals; the
in-flight-disclosure limitation (content already rendered into a host
conversation) is inherent and disclosed.

Follow-up work: the implementation WorkPlan (next operation); owner review
of the design before implementation begins is prudent but was pre-approved
in principle ("Let's do that design delta properly").

Lessons: (1) the two-plane serving architecture means replay-level
enforcement alone never reaches retrieval — designs must enumerate every
serving path before claiming an authority "gates everything"; (2) reviewer
prescriptions still need coordinator validation against disk (the
script-path correction was itself wrong); (3) the pending-epoch counter
dissolves the DUR-09 epoch problem because forget requires a publication
anyway — the crash-window analysis (decrement, not clear) is where the
real subtlety lived.
