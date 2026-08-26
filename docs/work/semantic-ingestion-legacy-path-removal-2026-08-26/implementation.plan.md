# Semantic Ingestion Legacy-Path Removal Implementation WorkPlan

- Work ID: `semantic-ingestion-legacy-path-removal-2026-08-26-implementation`
- Work type: `implementation`
- Status: `active`
- Coordinator: sole writer (main thread)
- Created: `2026-08-26`
- Last updated: `2026-08-26`
- Parent WorkPlan: `../semantic-ingestion-legacy-path-removal-2026-08-26/design.plan.md`
  (same directory; the design plan is the governing design record and is not
  converted — this file is the separate linked implementation operation)
- Related WorkPlans:
  - `../semantic-ingestion-suite-reconciliation-2026-08-26/design.plan.md`
    (47-failure reconciliation; its ordinary-pipeline families are resolved by
    this removal, its V3-era families are slice 6 here)
  - `../semantic-ingestion-validated-canonical-closure-2026-08-17/implementation.plan.md`
    (parent operation; user decisions on host-independent recovery and
    marker-keyed reconcile admission recorded in
    `milestones/recovery-reconciliation-fresh-owner-propagation.md`)
- Canonical inputs:
  - `docs/work/semantic-ingestion-legacy-path-removal-2026-08-26/design.plan.md`
    at commit `c0bbc8e` (user decision, census, six-slice plan, design rules)
  - `docs/design/semantic_ingestion_architecture.md` (SIA-R20 lease/fence,
    SIA-R23 delivery/redelivery identity)
  - `docs/design/semantic_ingestion_validated_canonical_closure.md`
- Expected outputs: legacy source-normalization/ordinary-pipeline path deleted
  (no shims), reconcile marker-keyed, egress security contract re-anchored to
  the authorization read-set boundary, clean broad suite, slice commits.

## Objective

Everything semantic-ingest sources through the V3 path: the ordinary nested
ingest path, the legacy source-normalization stage/contracts, the ordinary
`SemanticIngestionPipeline` and its egress-policy plumbing are deleted; the
recovery reconcile door becomes marker-keyed admission from retained durable
records; the 18 egress-mutation security tests are re-anchored to the
authorization read-set boundary (`authorization.py` `_matches`, binding
`egress_policy_revision`/`egress_decision_digest`); the suite-reconciliation
operation's clean-suite goal is met at the final revision.

## Design Baseline

- Canonical design path: `design.plan.md` in this directory (frozen at `c0bbc8e`).
- In-scope requirements: the six slices exactly as specified, plus the design
  rules (no shims; per-test dispositions recorded; identity gate green at every
  slice boundary; slices land green; marker-keyed reconcile per the recorded
  user decision).
- Approved deviations: none. The design grants an in-flight census for
  `contracts.py` nested types and `ProductionLocalSemanticAnalyzer`.
- Unresolved design questions: none may be reopened from the decided set
  (no compatibility shims; test deletions with justification; allowlist entry
  moves or dies with `test_semantic_pipeline.py`; recovery provenance from
  retained durable records under process write exclusivity).

## Completion Contract

The operation completes only when:

1. every design-plan census item 1-6 is deleted or retained with recorded
   per-type/per-symbol census evidence;
2. every removed behavioral contract has an explicit test disposition in this
   WorkPlan (re-targeted to the V3 boundary or deleted with justification);
3. the focused suites named per slice pass at each slice boundary and the full
   broad deterministic gate passes at the final revision with the 47
   pre-existing failures resolved (43 in `test_semantic_provider_composition.py`,
   4 in `test_bootstrap_graph_coordinator_v3.py`) and no new failures;
4. `ruff check memorii tests` and the identity-hygiene gate pass at every slice
   boundary and at the final revision;
5. the reconcile door implements marker-keyed admission (marker + found index +
   loadable prepared source + current writer; scope from retained records)
   consistent with the recorded user decision, with focused recovery proofs;
6. the closure record is appended with `remaining_validated_p1_p2: []` and the
   changed-surface ledger matches the final live diff.

## Scope

Included: the six slices of the design plan; test migration/deletion with
dispositions; identity-hygiene allowlist reconciliation for moved/deleted test
files; slice commits; WorkPlan closure for this operation and the two linked
operations' affected families.

Excluded: any V3 behavior redesign; persisted-schema changes beyond deleting
dead contract types (no persisted bytes are migrated — the product is
unreleased and legacy publications are unreachable by the retained runtime);
performance-milestone work of the parent closure operation; live/CI-only
evidence claims.

## Constraints And Invariants

- No compatibility shims, aliases, or deprecation paths.
- Fail closed: every removed branch's absence must not create a new silent
  success path; unknown/insufficient outcomes remain valid.
- SIA-R20 (lease/fence/exhaustion) and SIA-R23 (delivery identity, exact
  redelivery/replay) behavior is preserved on the retained V3 path.
- Writer admission, authorization read-set, provenance, and transaction stages
  on the retained path are not weakened.
- Egress contracts (`ProviderEgressBinding`, `ProviderEgressDecision`, signed
  commands, repositories, `verify_current_egress`) survive; only the pipeline
  plumbing of `egress_policy_provider` is removed.
- One writer; focused checks during construction; each required broad gate once
  at the final revision.

## Identity And Coordinate Hygiene

| Surface | Identity | Class | Decision |
| ------- | -------- | ----- | -------- |
| Deleted symbols (`SemanticIngestionPipeline`, `GraphFreeSourceNormalizationStage`, legacy `SourceNormalization*` contracts, reservation machinery, `SemanticExecutionRetryPlan` if orphaned) | behavioral identities being removed | behavioral | Delete outright; no aliases. Record each in the deletion census |
| `ProductionLocalSemanticAnalyzer` | pinned in `bootstrap_profile.py` verified-release material (`local_analyzer_symbol`) | behavioral + pinned release identity | **Retain the class** (bootstrap profile verification pins its symbol at `memorii.core.semantic_ingestion.local_analyzer.ProductionLocalSemanticAnalyzer`); its ordinary-pipeline consumers die |
| Identity-hygiene allowlist entries pinning `test_semantic_pipeline.py` / `test_semantic_ingestion_pipeline.py` | gate exceptions | governance | Move or delete exactly with the test files; gate green at every boundary |
| Slice numbering (`slice 1`-`slice 6`) | planning coordinates | planning/evidence | Only in WorkPlans/commit messages/this ledger; never in code, tests, filenames, or CI |

## Production Entrypoint Bindings

Initialized from direct code reading (coordinator preflight; refreshed per slice
when a mapped trigger or owner changes):

| Requirement | Canonical trigger and composition root | Status |
| ----------- | --------------------------------------- | ------ |
| V3 ingest path | `ProviderMemoryService.sync_event` -> `ProviderIngestionCoordinator.ingest` -> `_bootstrap_prepare_and_handoff` -> `_run_semantic_ingestion` (V3 branches) | implemented; retained through all slices |
| Exact-redelivery recovery | `sync_event` over retained marker + found index -> `reload_bootstrap_recovery_replay_v3` | implemented; untouched |
| Reconcile door | `ProviderMemoryService.reconcile_memory_evolution` -> `ProviderIngestionCoordinator.reconcile` | currently plan-gated (unreachable); becomes marker-keyed in slice 2 |
| Conflict clarification | `ConflictClarificationProcessor` -> `ConflictClarificationSemanticPipelineAdapter.process_clarification` -> `pipeline.run` (local proposals, no egress) | third `pipeline.run` consumer discovered in preflight; disposition recorded in slice 5 census |
| Egress security boundary | authorization read-set `_matches` binding `egress_policy_revision`/`egress_decision_digest` (`authorization.py:187-209`) + `verify_current_egress` | survives; mutation tests re-anchored (slice 5) |

## Changed-Surface Ledger

Maintained per slice; final reconciliation against the live diff before closure.

| Path or pattern | Surface class | Intended scope owner | Status |
| --------------- | ------------- | -------------------- | ------ |
| `memorii/core/provider/ingestion.py` | product code | slices 1-2 | pending |
| `memorii/core/semantic_ingestion/source_normalization_execution.py` | product code | slice 3 | pending |
| `memorii/core/semantic_ingestion/source_normalization_stage.py` | product code | slice 3 | pending |
| `memorii/core/semantic_ingestion/source_normalization_host.py` | product code | slice 3 | pending |
| `memorii/core/semantic_ingestion/contracts.py` | product code | slice 4 | pending |
| `memorii/core/semantic_ingestion/pipeline.py` | product code | slice 5 (delete or reduce) | pending |
| `memorii/core/semantic_ingestion/capability.py` | product code | slice 5 | pending |
| `memorii/core/semantic_ingestion/egress.py` | product code | slice 5 (plumbing only) | pending |
| `memorii/core/provider/service.py` | product code | slices 1,5 | pending |
| `memorii/tests/unit/core/semantic_ingestion/*` | tests | all slices | pending |
| `.agents/identity_hygiene_allowlist.json` | gate config | slice 4 (with its test) | pending |

## Gate Ledger

| Gate | Exact local command (from `memorii/`) | Required |
| ---- | ------------------------------------- | -------- |
| Focused per-slice suites | `../.venv/bin/python3.12 -W error -m pytest <slice selection> -p no:cacheprovider` | each boundary |
| Ruff | `../.venv/bin/ruff check memorii tests` | each boundary |
| Identity hygiene | `../.venv/bin/python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json` | each boundary |
| Broad unit gate | `../.venv/bin/python3.12 -W error -m pytest tests/unit -p no:cacheprovider` | final revision |

## Known-Failure Ledger

| Failure | Disposition |
| ------- | ----------- |
| 43 failures in `test_semantic_provider_composition.py` | pre-existing at merge base (verified in the suite-reconciliation operation); resolved by this removal (ordinary-pipeline families deleted/re-targeted) + slice 6 (V3-era families) |
| 4 failures in `test_bootstrap_graph_coordinator_v3.py` | pre-existing; slice 6 V3-era family repairs |
| pyright ~374 pre-existing errors in `contracts.py` | out of scope; expected to drop with legacy contract deletion; no opportunistic fixes |
| 9 ruff errors at clean HEAD (`b258e91` worktree-verified 2026-08-26) in `memory_evolution/__init__.py`, `test_event_replay.py`, `test_bootstrap_text_preparation_producer.py`, `test_bootstrap_graph_v3_fixture.py`, `semantic_terminal_test_support.py`, `test_semantic_ingestion_pipeline.py` | pre-existing; all in legacy-test/fixture surfaces scheduled for migration or deletion in slices 3-6; final revision must be ruff-clean |

## Requirement Coverage Ledger

| Design-plan slice | Implementation | Tests | Status |
| ----------------- | -------------- | ----- | ------ |
| 1. Coordinator ordinary nested path removal | `ingest` keeps metadata-poor/ingress/empty gates, classification, V3 path; non-pending returns directly | composition + coordinator suites | not started |
| 2. V3-only `_run_semantic_ingestion` + marker-keyed reconcile | legacy branches removed; legacy result types rejected as foreign; reconcile marker-keyed | recovery proofs + replay/reopen | not started |
| 3. Execution owner/stage V3-only | legacy stage, producers, reservation machinery removed from owner/builder | normalization repository/stage tests migrated | not started |
| 4. Contract deletions + per-type orphan census | legacy contracts deleted; shared nested types retained with census proof | contracts unit suites | not started |
| 5. Pipeline/egress removal + composition cleanup | runtime/service plumbing removed; 18 egress tests re-anchored to authorization read-set boundary | egress + authorization suites | not started |
| 6. V3-era family repair + broad gate | remaining reconciliation families fixed | full broad suite | not started |

## Change Map

See the design-plan census items 1-6 and the changed-surface ledger above.
Non-applicable areas (no changes expected): persisted data migration (none —
unreachable legacy publications are not read by the retained runtime), CLI,
prompts beyond the removed `semantic_ingestion_proposal` pipeline usage
(retained for V3 if referenced by V3 lanes — census in slice 4/5), external
adapters.

## Migration, Rollout, And Rollback

The product is unreleased; no persisted data migrates. Legacy publication
records, if any exist in old stores, are never read by the retained runtime
(the reload validators for legacy results are deleted with the path). Rollback
is the slice commits. Mixed-version behavior: none (no wire or persisted schema
survives the deletion).

## Sources Of Truth

1. `design.plan.md` (this directory) — the operation contract.
2. `docs/design/semantic_ingestion_architecture.md` — SIA-R20/R23.
3. `docs/design/semantic_ingestion_validated_canonical_closure.md`.
4. Production code and tests at each slice boundary.

Conflicts return to the design plan's recorded decisions; a genuine semantic
conflict stops the operation per AGENTS.md.

## Current State

Branch `semantic-indexing-m4` (slice commits appended after `b258e91`). The
delegated read-only census completed 2026-08-26 (agent output recorded in the
Delegation Ledger; coordinator validated the load-bearing claims directly in
code). Production preflight findings, all verified in source:

- `ingest`'s ordinary nested path (`ingestion.py` ~749-941) is **already
  unreachable dead code**: `bootstrap_writer_handoff` only ever returns
  `BootstrapWriterHandoffMarkerV3` markers (existing markers validated as V3 at
  `atomic_store.py:1223`; new markers created as V3 at `:1284`), so the V3
  marker guard at `ingestion.py:626` is always true when a handoff exists.
  Slice 1 is dead-code removal, not behavior change.
- A third `pipeline.run` consumer exists: `ConflictClarificationSemanticPipelineAdapter.process_clarification`
  (`capability.py:178`), installed as the default clarification pipeline by
  `provider/service.py:564` (Hermes conflict-clarification lane; local
  proposals, no egress). Disposition (slice 5): removed with the pipeline —
  the lane is ordinary-pipeline machinery; the conflict-attention
  retention/submission machinery survives; service stops default-constructing
  the adapter and clarifications remain pending (fail-closed, no fabricated
  outcomes). The failing hermes-clarification family (×3) asserted the removed
  semantic-evaluation leg and is deleted with justification.
- `ProductionLocalSemanticAnalyzer` is pinned by the verified bootstrap-profile
  contract (`bootstrap_profile.py:479,505,904,951`); the class survives; only
  its ordinary-pipeline consumers die. Its span/owner-pair statics live on
  `SemanticIngestionPipeline` (`_analysis_spans_are_valid`,
  `_is_protected_scenario_owner_pair`) and are used by
  `test_scenario_public_ingress_runner.py` — they move to a surviving owner in
  slice 5.
- `GraphFreeSourceNormalizationInvocation` is shared by the V3 flow; it
  survives the legacy-stage deletion.
- Same-name hazard: `SourceNormalizationEvidenceManifest`/`Entry` also exist in
  `memory_evolution/semantic_analysis/decision_contracts.py` (distinct classes
  used by the publication-coordinate family); the ingestion-contracts versions
  are deleted, the decision-contracts versions get their own orphan census in
  slice 4. `SourceNormalizationPublicationCoordinate` (decision_contracts) is
  used by V3 authority members and survives.
- `semantic_terminal_test_support.py` is the runtime-fixture hub for 8
  surviving suites (terminal persistence, graph planning, policy migration,
  transaction group plans, graph record support, event replay, generation
  transactions, identity lineage); it must be migrated before pipeline
  deletion (slice 5).
- Traceability registry/checkers: decoupled from every deleted symbol.
- CI coupling: `memorii/tests/ci/unit-test-durations.json` carries 43 stale
  node IDs for `test_semantic_provider_composition.py`; regenerate after test
  removals (slice 6).

### Test disposition census (from the delegated census, coordinator-validated)

| Test file | Disposition |
| --------- | ----------- |
| `test_source_normalization_stage.py` (3) | delete — subject is the removed legacy stage; V3 stage has its own suites |
| `test_source_normalization_normal_vector.py` (2) | delete — legacy canonical-request vectors |
| `test_source_proposal_run_contracts.py` (9) | delete — subject contract `SemanticProposalRun` is removed |
| `test_semantic_pipeline.py` (13) | delete with the pipeline; `test_production_local_analyzer_requires_and_consumes_prepared_source_authority` migrates to the analyzer suite; allowlist-pinned `test_closed_codec_round_trip_rejects_legacy_and_wrong_contract_kind` dies with the file (rejection proof re-anchored if the codec surface retains a legacy-bytes vector) |
| `tests/integration/test_semantic_ingestion_pipeline.py` (~30) | delete — organized around the pipeline engine; allowlist-pinned `test_legacy_rejects_preclosure_terminal_bytes` dies with the file |
| `test_prompt_and_egress_authority.py` | split — egress repository/CAS/lifecycle tests survive; the four pipeline-egress boundary tests re-anchor with the ×18 mutation family (slice 5) |
| `test_semantic_provider_composition.py` | ordinary families (egress ×18 re-anchor; analyzer, accepted-control, stops-before-owner, untyped-normalization ×2, hermes ×3, deployment-denial ×4, same-pipeline ×1 — delete with justification); V3-era families repair in slice 6 |
| `semantic_terminal_test_support.py` + 8 consumers | migrate hub construction off the removed runtime fields |
| `test_scenario_public_ingress_runner.py` | migrate — pipeline statics move to a surviving owner |
| `test_source_normalization_repository.py` | legacy publish/reload tests (3) die with the legacy repository branch; V3 tests survive |
| `test_consensus_contract_codecs.py`, `test_source_group_plan_contracts.py` | re-target alignment fixtures to surviving types per slice-4 census |
| `test_bootstrap_text_preparation_producer.py` | analyzer tests survive; pipeline-engine helper gets a replacement |
| `tests/fixtures/semantic_ingestion/source_normalization_fixture_builder.py` | legacy tower builder; dying consumers delete; V3 consumers (`test_bootstrap_v3_payload_contracts.py`, `test_bootstrap_v3_native_lane_contracts.py`, composition V3 tests) migrate to V3 builders |

### Failing-test baseline (43 + 4)

Ordinary-pipeline families (26, resolved by removal): egress mutation ×18
(`test_public_coordinator_rejects_every_egress_authority_mutation_without_wire`
parametrized over tenant_id, source_id, source_digest, segment_id,
classification, provider, model, region, retention_mode, training_use,
signature, signer, expiry, outage, policy_id, policy_revision,
policy_fingerprint, decision_digest); local analyzer ×1
(`test_ordinary_provider_root_uses_production_local_analyzer_without_wire`);
accepted control ×1 (`test_normal_provider_accepted_control_commits_complete_effect_group`);
stops-before-owner ×1; untyped normalization ×2
(`test_normal_provider_root_rejects_untyped_or_missing_normalization_result_before_terminal`);
hermes clarification ×3
(`test_normal_hermes_clarification_uses_retained_event_and_local_pipeline`);
deployment denial ×4 (`test_external_deployment_authorization_failure_is_zero_wire`);
same-pipeline ×1 (`test_hermes_and_filesystem_roots_use_the_same_semantic_pipeline`).

V3-era families (17 + 4, slice 6): lost-ack ×3
(`test_public_jsonl_lost_ack_reopens_without_duplicate_effects`);
recovery-authority-change ×3 + foreign plan ×1
(`test_jsonl_recovery_authority_change_is_zero_learned_calls`,
`test_foreign_recovery_plan_is_rejected_before_lease_or_learned_calls`);
redelivery-rotation ×1
(`test_identical_redelivery_after_authority_rotation_reuses_plan_without_calls`);
reconcile ×~3 + exhaustion ×1; frozen-wire ×1
(`test_public_jsonl_service_matches_frozen_wire_and_member_bytes_across_reopen`);
corruption recovery ×1
(`test_real_filesystem_hermes_corruption_recovery_restart_and_racing_write`);
coordinator module ×4 (corruption-reopen ×2
`test_terminal_request_reload_rejects_in_memory_corrupt_closure` /
`..._corrupt_jsonl_closure_after_reopen`; graph-terminal
`test_direct_provider_root_reaches_bootstrap_graph_terminal` and one of the
verified-production-root pair — exact nodes confirmed at repair time).

## Assumptions And Open Questions

Verified facts: recorded above under Current State.

Working assumptions:

- The ordinary-pipeline families' failing tests are deleted with justification
  (their subject machinery is removed); only the 18 egress-mutation tests are
  re-targeted. Confirmed against the census before deletion.
- The conflict-clarification semantic-processing leg is ordinary-pipeline
  machinery and is removed with it; the conflict-attention retention machinery
  survives; no fabricated outcomes replace it. Confirmed against the census and
  the hermes-clarification family's assertions in slice 5.

Unresolved questions: none blocking slice 1.

Decisions requiring external input: none (all user decisions recorded in the
design plan and parent operation).

## Milestones

The six slices of the design plan are the milestones. Each slice: bounded scope
in the design plan; focused suites named there; status tracked in the
Requirement Coverage Ledger; commit at each boundary.

## Verification Commands

```bash
../.venv/bin/python3.12 -W error -m pytest <focused selection> -p no:cacheprovider
../.venv/bin/ruff check memorii tests
../.venv/bin/python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json
```

Broad gate (once, at the final revision):

```bash
../.venv/bin/python3.12 -W error -m pytest tests/unit -p no:cacheprovider
```

## Delegation And Cost Ledger

| Task | Role | Ownership | Status |
| ---- | ---- | --------- | ------ |
| Test-file census of legacy symbols; failing-family node IDs; allowlist entries; traceability coupling | Explore agent (read-only) | read-only | in flight 2026-08-26 |
| All production/test edits | coordinator (sole writer) | overlapping files | active |

## Progress Log

- 2026-08-26: Opened this linked implementation WorkPlan after reading all
  required documents and completing the production-code preflight. Routing
  decision recorded: implementation proceeds under this linked WorkPlan; the
  design plan is not converted. Next action: consume the test census, then
  execute slice 1.

## Decision Log

- 2026-08-26: Open a linked implementation WorkPlan (this file) rather than
  converting the design plan — AGENTS.md forbids silent type conversion.
- 2026-08-26 (preflight): `ProductionLocalSemanticAnalyzer` is retained because
  the verified bootstrap profile pins its symbol; only its ordinary-pipeline
  consumers die. Evidence: `bootstrap_profile.py:479,505,904,951`.
- 2026-08-26 (retained-state mapping, slice 2 design): the marker-keyed
  reconcile drives the **found** path only. Evidence: the found path's every
  ingress consumption is redundant with retained records — graph host and store
  read only `delivery_principal_binding.binding_digest` (already on
  `OperationFenceBinding`, `ingestion_contracts.py:506`) and the canonical-lease
  tenant (retained in the prepared source's
  `governance_carrier_artifact.required_outcome_scopes.tenant_partition_id`);
  the claimed path's `GraphFreeSourceNormalizationInvocation.source_authority_evidence`
  is NOT reconstructable from retained records (authority body survives only as
  digests per the governance derivation), so completing an unpublished
  normalization remains the redelivery door's job (SIA-R23), which the design
  gate ("marker + found index + loadable prepared source + current writer")
  already reflects. No `AuthenticatedIngressContext` is ever fabricated for
  recovery (user decision); instead the graph request/reload contracts are
  narrowed to fence-derived binding digest + retained tenant/scope values
  ("recovery repair convergence"). The bounded maintenance tick beyond the
  existing explicit `reconcile_memory_evolution` entry point remains the parent
  operation's repair-round scope, not this removal's.

## Review Log

None yet (review rounds at coherent milestone boundaries per the
implement-design skill).

## Blockers And Limits

Iteration budget: six slice rounds plus one remediation round per slice; if a
slice cannot land green without weakening a gate or inventing semantics, stop
as blocked with the exact conflict.

## Next Action

Consume the delegated test census, then execute slice 1 (remove the ordinary
nested path from `ProviderIngestionCoordinator.ingest`; focused: composition +
coordinator suites; ruff + identity gate; commit).
