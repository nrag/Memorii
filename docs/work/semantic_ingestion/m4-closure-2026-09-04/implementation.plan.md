# M4 Event History Completion Operation

- Work ID: semantic_ingestion_m4_completion_2026_09_04
- Work type: implementation
- Status: active
- Coordinator: Codex main thread
- Created: 2026-09-04
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Active milestone packet: `docs/work/semantic_ingestion/milestones/m4-event-history.plan.md`
- Linked debugging WorkPlan: `docs/work/semantic_ingestion/conflict-authority-proof-failures-2026-08-04/debug.plan.md` (sole detailed owner of the clarification-lifecycle changed surface until it closes)
- Approved linked design: `docs/work/semantic_ingestion/semantic-conflict-introduction-authority-2026-08-04/design.plan.md`
- Unblocked by: M3.1 final closure recorded 2026-09-04 at HEAD `bd1ebf0` (append-only source/group plan lineage and exact terminal binding now exist in production)

## Objective

Complete SIA-R10 and SIA-R18 end-to-end: production-owned clarification-winner
replan on append-only plan lineage, bounded conflict-attention exposure through
provider, factory, filesystem, derived-cache, composite, and Hermes
composition, and byte-equivalent genesis/checkpoint replay with deterministic
fail-closed behavior across all adversarial families.

## Completion Contract

Complete only when:

- the linked debug WorkPlan records closure of production-owned
  clarification-winner replan with empty remaining arrays at a frozen revision;
- provider, factory, cache, composite, and Hermes pulls expose bounded
  conflict attention without a proactive core callback and without guessing a
  winner;
- every M4 packet completion-evidence row in
  `milestones/m4-event-history.plan.md` passes at one frozen revision,
  including both clarification-win and projection-win orders, exact retry,
  real JSONL reopen, corruption, migration, trust-decay, and lineage families;
- the M4 packet's frozen arrays (`semantic-conflict-introduction-unreachable`,
  `semantic-conflict-introduction-authority`) are cleared by revision-bound
  debug closure and milestone review — never by a narrower slice;
- fresh specification, correctness, and test reviews leave
  `remaining_validated_p1_p2: []`, `remaining_blocks_approval: []`, and
  `remaining_changes_required: []`.

## Constraints

- The frozen equal-version replay decision is not reopened; no
  newest-timestamp auto-winner; no non-atomic after-commit conflict-file
  append.
- Planned state remains one-way; replan appends typed lineage and never
  performs a planned-to-preplanning regression.
- The file ledger stays a recoverable listing/clarification projection; the
  canonical introduction owner is the same memory-plane CAS as the contested
  projection.
- One writer for overlapping production/test/document edits; reviewers run
  only after the candidate freeze gate is satisfied.

## Milestones

| Milestone | Deliverable | Dependency |
| --- | --- | --- |
| M4-A Replan closure | Resume the linked debug: wire clarification-winner replan onto the completed M3 plan lineage, rerun the exact reproducer and affected families, perform frozen three-role debug closure review with empty arrays | M3.1 closure (done) |
| M4-B Conflict-attention composition | Bounded user-attention items on provider, factory, filesystem, derived-cache, composite listing, and Hermes pulls; exact retry through the verifier; core remains callback-free | M4-A |
| M4-C Replay and history closure | Byte-equivalent genesis/checkpoint replay across every active read schema; permutation, duplicate, corruption, late-arrival, trust-decay, rekey/merge/split, and migration-race families; real JSONL reopen evidence | M4-B |
| M4-D Milestone closure | Freeze candidate identity, run repository deterministic gates and workflow-selected CI, fresh whole-milestone three-role review, clear the M4 packet arrays, update index/resume | M4-C |

## Current Exact Next Action

Run the frozen three-role closure reviews: first the linked semantic-conflict
debug operation (M4-A replan evidence is complete), then the M4 milestone
(including the composite listing slice below).  The child-binding API,
composite repository, and provider/builder wiring are complete.

## Progress Log

- 2026-09-04: Operation created; M3.1 closure recorded (v81 disposition plus
  successor identity v82 re-pinning all artifacts at HEAD `bd1ebf0`).
- 2026-09-04: Coordinator mapping of the replan owner boundary complete
  (read-only); sole writer dispatched for the implementation slice.
- 2026-09-04: M4-B composite wiring complete.  The file ledger gained
  `create_composite_child_bindings` (one retained v1 child snapshot per
  audience side at one watermark, per-member keys binding the introduction
  revision and immutable ledger entry digest), `retain/load_composite_snapshot`
  (new strictly validated `composite_snapshot` ledger record kind), and
  `composite_snapshot_items` (watermark-bounded re-derivation).
  `CompositeConflictListingRepository` pages the frozen member sequence
  through v2 composite cursors with reopen-safe continuation.
  `ProviderMemoryService` routes `_attention_page` through the composite owner
  under the fail-closed opt-in `conflict_attention_composite` flag (requires
  the file-ledger child; direct v1 behavior is unchanged by default), with the
  flag forwarded through the factory and filesystem builders.  Integration
  proof: `tests/unit/core/test_composite_conflict_listing_repository.py`
  `5 passed in 5.95s`; full conflict-attention family `104 passed in 7.98s`;
  clarification plus composition `25 passed in 181.03s`; provider service
  `41 passed`; full Ruff and diff hygiene clean.
- 2026-09-04: M4-B composite contract slice complete:
  `memorii/core/memory_evolution/composite_conflict_listing.py` owns the five
  typed design contracts (member key, child binding, listing member,
  composite snapshot, v2 cursor claims) with domain-separated digest
  validation; the v2 cursor codec (grammar, MAC domain, key-ring lifecycle,
  900-second expiry, cross-principal/tenant/scope and downgraded-protocol
  rejection); snapshot assembly with child-ordered contiguous ordinals,
  duplicate-member-key and both-children-same-conflict-ID
  `semantic_conflict_replay_integrity_failure`; continuation snapshot/binding
  digest validation; and metadata routing (semantic to repository, integrity
  to `operator_action_required`).  Equivalence-class matrix:
  `tests/unit/core/test_composite_conflict_listing.py` `17 passed in 11.13s`.
  This is a contract-owner slice: child-repository binding APIs and provider
  wiring are the recorded next action, and no production listing behavior
  change is claimed.
- 2026-09-04: M4-B builder enablement complete: `build_provider_memory_service_from_env`
  and `build_filesystem_provider`/`FilesystemStorageBundle.build_provider_memory_service`
  now forward `conflict_attention_repository`, `conflict_attention_enabled`,
  and `conflict_attention_observability_sink`; the filesystem bundle gained
  `build_conflict_attention_repository(keys)`; Hermes self-built services
  inherit the wiring.  The fail-closed default (disabled without explicit
  authority) and the enabled-without-repository rejection are pinned by
  `tests/unit/core/test_conflict_attention_composition.py` (`5 passed in
  10.79s`); provider families `47 passed`; full Ruff, compilation, and diff
  hygiene clean.  Composite listing and derived-cache surfaces remain
  (see Exact Next Action).
- 2026-09-04: M4-A end-to-end proof complete: production-owner tests
  `2 passed in 57.55s` (one replan, terminal completion at the derived
  coordinate, fail-closed second staleness); exposed and fixed the replan
  arena rebinding defect with a fresh provider-factory canonical evidence
  arena; regression `47 passed`, configured-root node `1 passed in 64.16s`.
- 2026-09-04: M4-A production replan owner implemented in
  `ProviderIngestionCoordinator._ingest_semantic_source` with the reserved
  `conflict-replan:v1:` delivery coordinate; contract proof `4 passed`,
  reproducer both orders `2 passed in 243.10s`, provider families
  `47 passed` and `61 passed`, Ruff/compile/diff clean.  Remaining M4-A
  evidence: the end-to-end configured-profile replan race proof recorded in
  the linked debug plan.

## Delegation And Review Gate

Spark-class readers for mapping and family inventory; one Terra-class writer
per slice; the standard `spec_auditor`, `correctness_reviewer`, and
`test_reviewer` cohort runs once per coherent milestone after candidate
freeze, with targeted delta review for bounded remediation.
