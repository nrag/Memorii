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
| 25 ruff findings at clean HEAD (`b258e91`, worktree-verified 2026-08-26 with full code-class coverage; an earlier count of 9 used a code-class-filtered grep and was wrong) across `memory_evolution/__init__.py`, graph-plane production import sorts (`assembler`, `builtin`, `terminal_preparation`, `pipeline.py`, `source_normalization_repository.py`), and legacy test/fixture files (`test_event_replay.py`, `test_bootstrap_text_preparation_producer.py`, `bootstrap_graph_v3_fixture.py` ×8, `test_bootstrap_graph_v3_fixture.py`, `semantic_terminal_test_support.py`, `test_semantic_ingestion_pipeline.py`) | pre-existing; every file is touched or deleted in slices 2-6; slice 2 added zero new findings (24 after one auto-fix); the final revision must be ruff-clean |

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
- 2026-08-26 (slice 1, commit `0ebc160`): the ordinary nested ingest path
  (~200 lines, provably unreachable — every handoff marker is V3) and
  `_build_execution_plan` deleted. Evidence: provider service 41 passed
  (baseline 41); coordinator V3 selection 3 passed + the same pre-existing
  `test_direct_provider_root_reaches_bootstrap_graph_terminal` failure
  (identical signature, HEAD-verified); ruff clean on the changed file;
  identity gate pass.
- 2026-08-26 (slice 2, commit `5dc8cd5`): `_run_semantic_ingestion` is
  V3-only (both `pipeline.run` branches deleted; foreign result types
  rejected); the graph plane (host, builtin, repository, coordinator,
  terminal preparation, assembler, store methods) carries the fence-derived
  binding digest and retained tenant instead of `AuthenticatedIngressContext`;
  `reload_bootstrap_recovery_replay_v3` takes `tenant_partition_id`;
  reconcile is marker-keyed (marker + recovery index + loadable prepared
  source + current writer; no reconstructed ingress; unpublished
  normalizations stay with the redelivery door); the persistence plan ports
  are deleted. Two silent-TypeError regressions (host reload params, assembler
  kwargs) were caught by the reopen proof and fixed; the fresh-owner proof's
  capture assertion was re-anchored to the retained tenant. Evidence:
  replay + reopen + coordinator proofs + provider service = 54/54 passed
  (16m57s); ruff zero new findings; identity gate pass.
- 2026-08-26 (slice 3, commit `f11e4df`): execution owner V3-only (legacy
  stage, producer seams, reservation machinery deleted; absent V3 runtime
  authority fails closed); host builder loses legacy fields; stage module
  keeps only the V3 stage + shared invocation + V3 validator; repository
  V3-only; `sealed_proposal_producer.py` and
  `sealed_source_normalization_evidence_producer.py` deleted. Test
  dispositions executed (4 suites deleted; repository suite 4 V3 tests kept;
  fixture builder V3-only; composition builders migrated; construction test
  uses one fresh builder per root — the dynamic authority provider binds its
  publication lease once). Evidence: 50/50 focused passed; collection 4220;
  identity gate pass; ruff zero new.
- 2026-08-26 (slice 4, commit `f83a1f4`): legacy contract tower deleted with
  per-type census (see commit message and the census section above); V3-shared
  `TemporalResolution`/`PredicateEventInventory` retained; alignment family
  and pipeline-tower types deferred to slice 5 with their last consumer;
  replay-surface types retained. Evidence: 75 passed + 1 pre-existing
  environmental failure
  (`test_linguistic_adapters.py::test_shipped_manifests_verify_real_local_english_assets`,
  HEAD-verified failing — model-asset check) + 1 skipped; collection 4166;
  identity gate pass; ruff zero new.
- 2026-08-26 (slice-5 verified facts, coordinator-confirmed in source — do not
  re-derive): (1) `TemporalEvidenceResolver` has LIVE production consumers
  (`policy_migration.py:56,1990` and `projection_history.py:6059,6083`) — it
  must move to a new behavioral module (e.g.
  `temporal_evidence_resolution.py`) before `pipeline.py` is deleted;
  `LearnedStageRenewalScheduler`, `require_complete_graph_free_analysis`, and
  `build_graph_free_source_alignment` have no consumers outside pipeline and
  its dying tests. (2) `SemanticAnalysisOutage` is raised by nothing after the
  pipeline dies and is an `OSError` subclass — delete it and simplify
  ingestion.py's two `except (OSError, SemanticAnalysisOutage)` clauses to
  `except OSError`. (3) `SemanticProposalRun._validate_member_closure`
  (contracts.py ~6448-6580) and its `segment_language_route_digest` property
  (~6582) are defined on `SemanticProposalRun` and monkey-patched onto
  `SemanticProposal` at ~6602-6603 (`SemanticProposal` is LIVE via
  `proposal_adapter` and the V3 proposal producer) — move both definitions
  onto `SemanticProposal` when deleting `SemanticProposalRun`.
  (4) `source_alignment.py`'s only production importer is pipeline.py; its
  `resolve_source_local_identity` has one test-only consumer
  (`test_source_alignment_derivation.py`), so the module, the alignment
  family (`SourceProposalAlignment` etc.), and that test die together.
  (5) `test_temporal_trust_resolution.py` imports contract types via
  pipeline's re-export list — redirect to contracts (plus the new resolver
  module) when pipeline.py is deleted.
- 2026-08-26: slice 5 prepared but not started (context boundary; recorded
  for exact resumption). Its plan:
  delete `SemanticIngestionPipeline` + `resolve_context` + the clarification
  adapter (service stops default-constructing it; clarifications remain
  pending, fail-closed); remove `pipeline`/`egress_policy_provider`/
  `semantic_pipeline` plumbing from `AuthorizedSemanticIngestionRuntime`,
  `build_authorized_local_semantic_runtime`, `ProviderIngestionCoordinator`,
  and `service.py`; move `_analysis_spans_are_valid`/
  `_is_protected_scenario_owner_pair` to a surviving owner; migrate
  `semantic_terminal_test_support.py` (hub for 8 suites) and
  `test_scenario_public_ingress_runner.py`; delete
  `test_semantic_pipeline.py`, `tests/integration/test_semantic_ingestion_pipeline.py`,
  and `test_source_proposal_run_contracts.py` with the deferred contract
  types (`SourceProposalAlignment`, `GraphFreeInterpretationBundle`,
  `SemanticProposalRun` — moving its shared member-closure validator onto
  `SemanticProposal` — `UnresolvedPredicateEvent`, `SemanticTerminalBindingSet`,
  `SemanticProposalRequest`); re-anchor the 18-mode egress mutation test and
  the four pipeline-egress tests in `test_prompt_and_egress_authority.py` to
  the authorization read-set boundary (`authorization.py` `_matches` +
  `verify_current_egress`); update the two identity-hygiene allowlist entries
  when their pinned test files die. Focused: egress + authorization suites +
  provider service + coordinator selection.

- 2026-08-26 (slice 5, IN PROGRESS — production complete, test migration
  remains; working tree carries the WIP): production surface is fully migrated
  and the package imports: `TemporalEvidenceResolver` extracted to
  `temporal_evidence_resolution.py` (policy_migration + projection_history
  repointed); the scenario-runner predicates moved onto `local_analyzer.py`;
  `capability.py` lost the clarification adapter/context/protocol and the
  runtime `pipeline`/`egress_policy_provider`/`candidate_assessor`/
  `local_proposal_producer`/clarification fields (builder identity composition
  was pipeline-only and is gone); `ingestion.py` lost `resolve_context`, the
  pipeline/egress/assessor constructor params, and the guard's egress inputs
  (`SemanticAnalysisOutage` deleted; its two except clauses are now plain
  `except OSError`); `service.py` passes only policy+runtime to the
  coordinator and constructs a clarification processor only for an explicitly
  supplied host pipeline (clarifications otherwise stay pending);
  `SemanticProposal` owns its member-closure validators (monkey-patch gone);
  `pipeline.py`, `source_alignment.py`, and the deferred contracts
  (`SemanticProposalRun`, `SourceProposalAlignment`,
  `GraphFreeInterpretationBundle`, `UnresolvedPredicateEvent`,
  `CoveredPredicateEvent`, `PredicateEventDisposition`, `SemanticProposalRequest`,
  `SemanticProposalRequestArtifact`, `ProposalCoverageAudit`) are deleted.
  RETAINED: `SemanticTerminalBindingSet` (live field of the retained
  `SemanticTerminalOutcome`). The clean-room test hub now exposes
  `CleanRoomRequestMaterial`/`build_clean_room_proposal_catalogs`.
  REMAINING (in order): (1) `semantic_terminal_test_support.py` — its
  `SemanticIngestionPipeline(...).run(...)` engine (line ~676) must be
  replaced with direct `seal_semantic_operation` + `compile_accepted_carriers`
  outcome construction (the eight consumer suites test persistence/replay,
  not the engine); drop the runtime kwargs at ~262. (2)
  `test_scenario_public_ingress_runner.py` statics -> local_analyzer.
  (3) `test_temporal_trust_resolution.py` imports -> contracts +
  `temporal_evidence_resolution`. (4) `test_bootstrap_text_preparation_producer.py`
  pipeline-engine helper -> analyzer-direct. (5) `test_prompt_and_egress_authority.py`
  re-anchor (see below). (6) `test_semantic_provider_composition.py`: delete the
  ordinary families (analyzer, accepted-control, stops-before-owner successors,
  untyped-normalization, hermes clarification, deployment-denial, same-pipeline)
  and re-anchor the 18-mode mutation test against
  `SemanticAuthorizationReadSet.create(egress_policy_revision=...,
  egress_decision_digest=...)` + `authorization.py` `_matches` equality +
  `verify_current_egress` rejection modes (binding field mutations, signature,
  signer, expiry, outage, policy id/revision/fingerprint, decision digest),
  asserting no egress decision may enter an authority record whose read-set
  digest disagrees. (7) `test_consensus_contract_codecs.py`/
  `test_source_group_plan_contracts.py` trim deleted-type fixtures.
  (8) fixture builder residual `SemanticProposalRequest` annotations
  (lines ~609/634/831/965 in `build_source_normalization_authority_bundle`'s
  V3 path — pass-through only; retype to the material or V3 request).
  (9) Allowlist: remove the two `legacy_rejection_vector` entries (their files
  are deleted). (10) Gates: egress+authorization suites, provider service,
  coordinator selection; then slice 6.

- 2026-08-26 (user follow-up): after slices 5-6, revisit the parent
  operation's recovery milestone packet
  (`../semantic-ingestion-validated-canonical-closure-2026-08-17/milestones/recovery-reconciliation-fresh-owner-propagation.md`,
  the "M3.1 packet") — its pending reconcile-branch disposition
  ("repair via V3 execution-plan persistence, or remove") is resolved by this
  operation's slice 2 (marker-keyed retained-state admission, no plan
  persistence, no reconstructed ingress); the packet and the parent
  implementation plan's roadmap/next-action rows must be updated to record
  that resolution, and the parent's "Final branch review" milestone inherits
  this operation's broad-gate evidence.

- 2026-08-26 (slice 6 input, verified): the `test_conflict_clarification.py`
  failures (10+ tests failing at `verifier.bind` with zero admitted sources)
  are PRE-EXISTING at slice-4 `f83a1f4` and therefore at the branch base —
  the same `eb70c9d` governance contract family as the 47 but outside that
  census's two files. Root cause: the suite's `_Resolver()` builds an ingress
  without `semantic_egress_governance` (and likely `semantic_source_authority`),
  so `derive_source_governance_material` returns nonpromoting
  (`semantic_egress_governance_unavailable`) and the user-turn source is
  never admitted. Repair: extend the suite's resolver/ingress fixture to
  supply both authenticated metadata members (mirroring composition's
  `_host_ingress()`), not a governance change. The three adapter-lane tests
  in that file were already deleted with the adapter (slice 5).

- 2026-08-26 (slice 5 execution, continued): production complete per the
  recorded plan; the test migration landed: the terminal-support hub engine is
  a direct seal/carriers/lineage builder (the eight consumer suites now build
  terminals without the pipeline); the scenario-runner and text-preparation
  predicates import from local_analyzer; temporal-trust imports from contracts
  plus the resolver module; the codec suites dropped their deleted-type tests
  and the clean-room hub exposes CleanRoomRequestMaterial with source
  coordinates; the egress authority suite is re-anchored (binding-field
  substitution ×10 via verify_current_egress, server-time expiry denial,
  rotation invalidating the prior read-set digest, lifecycle CAS retained);
  the composition suite lost its nine ordinary-family tests (18 egress modes
  re-anchored above) and all dead runtime kwargs; the fixture builder's
  legacy request branch fails closed; the allowlist is pruned to 4 entries
  and the identity gate passes; full tree collects 4051 tests with zero
  errors. Batch evidence: egress/authorization/clarification/temporal/
  codecs/group-plan/provider-service ran (provider service 41 passed; the
  pre-existing clarification family partially repaired — resolver metadata,
  projectable scope, and admitted-source bind shape fixed; 12 tests remain
  failing inside the canonical conflict bridge, pre-existing at base, next
  layer isolated). The slow hub-consumer batch (scenario runner,
  text-prep, terminal persistence, event replay, identity lineage, graph
  planning, policy migration, transaction group plans, generation
  transactions) was still executing at this entry; record its numbers in
  the closure row before the slice-5 commit.

- 2026-08-27: PAUSED at the slice-5 WIP boundary by user decision — the
  canonical-evidence default-on operation
  (`../semantic-ingestion-canonical-evidence-default-on-2026-08-27/implementation.plan.md`)
  lands first. Resume state is unchanged: production migration complete and
  committed; hub batch finished 130 failed / 246 passed with the failure list
  lost to output truncation (3 policy-migration failures identified; fast-file
  rerun with saved output is the classification step); slice-5 commit awaits
  that classification, then slice 6.

- 2026-08-27 (resumed, classification progress): the fast hub-consumer
  files rerun with saved output: transaction-group-plan, generation-
  transactions, and text-preparation suites are GREEN (8 failures / 36
  passed were all in `test_scenario_public_ingress_runner.py`). All 8
  scenario-runner failures share one signature — `SemanticWriterAdmissionError:
  semantic writer is unbound` at the SERVICE-level writer store — verified
  pre-existing at the pre-M1 commit (same signature reproduced at the
  capability level in a clean worktree during the perf work; the debug
  operation's no-auto-create writer change was never migrated into the
  scenario harness). The capability-level activation fixture now creates
  the initial evidence-only epoch when the store is fresh (committed);
  the service-level binding migration is slice-6 scope. Remaining
  classification: rerun the five slow hub files (terminal persistence,
  event replay, identity lineage, graph planning, policy migration) — many
  of the original 130 likely resolved with the `proposer_fingerprint` and
  resolver fixture fixes already landed; then conflict-attention's 12
  canonical-bridge failures.

- 2026-08-27 (classification COMPLETE): slow-batch rerun (output saved,
  1:11:50): terminal-persistence 72 + event-replay 43 + policy-migration 7
  failed; identity-lineage and graph-planning GREEN. Together with the 12
  conflict-attention failures, **134 failures share one root-cause family:
  the canonical conflict-clarification transaction CAS bridge**
  (`commit_conflict_clarification_transaction` -> "clarification semantic
  transaction requires canonical CAS") — verified PRE-EXISTING at the
  pre-operation commit `c0bbc8e` (worktree, 1-test probe). This is the
  eb70c9d-era contract change that was never migrated into the
  clarification fixtures: the canonical CAS expects a canonical conflict
  attention record and canonical retained context that the test fixtures do
  not create. Non-clarification tests in those files (210) pass. Repair
  belongs to the canonical conflict bridge family (slice 6, or a dedicated
  linked unit if it proves larger than a family repair); it is NOT a
  regression of this operation's slices 1-5.

- 2026-08-27 (SLICE 5 CLOSED): production migration (pipeline/egress/clarification-adapter
  removal, deferred contract deletions) and test migration (hub engine,
  fixture builder, clean-room hub, codec suites, egress re-anchor, composition
  trim, allowlist) are complete and committed across the WIP series
  (`dee4e89`..`12b6a67`). Boundary evidence: hub-consumer suites green
  except the two commit-verified pre-existing families (134 clarification-CAS
  + 8 scenario writer binding — both slice-6 scope, neither a slice-1..5
  regression); identity/graph/transaction/generation/text-prep fully green;
  ruff, identity gate, and full collection green throughout. Slice 6 now
  owns: the clarification-CAS family repair, the scenario-harness service
  binding migration, the composition/coordinator V3-era families (17+4), the
  linguistic environmental disposition, full broad gate, durations regen,
  and the three WorkPlan closures.

- 2026-08-27 (slice 6a diagnosis complete; fixture construction remains):
  the 134 failing tests call `commit_conflict_clarification_transaction`
  with the PRE-eb70c9d signature (no `clarification_cas`), and **no test in
  the repository drives the real CAS today** — the four passing processor
  tests use an in-file fake pipeline that never touches the store
  transaction. The repair is new fixture construction through the real
  owners, in `_commit_accepted_clarification`
  (`test_semantic_terminal_persistence.py:638`) and its policy-migration /
  event-replay siblings:
  1. create an active semantic conflict in projection history (the record
     family behind `_projection_history._current_semantic_conflicts()`),
  2. `submit_canonical_conflict_clarification` for the proposal,
  3. claim it (`AtomicStoreConflictClarificationProcessingRepository.claim_next_clarification`
     with a real lease/owner token),
  4. `store.build_conflict_clarification_cas_input(claim)`,
  5. pass `clarification_cas=` plus the existing arguments to
     `commit_conflict_clarification_transaction`.
  The `processing_operation_id` in the CAS must match the helper's. The 12
  conflict-attention service-level failures follow the same lifecycle via
  the Hermes resolution path.

- 2026-08-27 (slice 6a progress + blocker): (1) FIXED family — the 14
  artifact-index-mutation tests: JSONL reopen returns list-typed content
  where in-memory records keep tuples; added `_json_round_tripped` and
  normalized the four reopen comparisons (family green, 14/14). (2) The
  retry-idempotence drift is understood: the union return
  (`Receipt | AttemptResult`) is the declared contract; retry assertions
  comparing `== receipt` must compare `downstream_receipt_digest` instead
  (7+ sites pending). (3) The canonical commit helper
  `_commit_accepted_clarification` was migrated to the real lifecycle
  (contest -> introduction -> submission generation -> claim -> CAS ->
  commit) with call sites updated; it advances through proposal/terminal
  binding (terminal must bind the claim proposal's source at record
  version >= 2) and is now blocked at
  `writer_admission._validate_conflict_authority_atomic_closure`
  ("semantic conflict authority closure is invalid") — the commit's write
  batch must satisfy the pointer-history/coordinate discipline; next step
  is to capture the batch records the PASSING completion test writes
  (its `capture_completion_write`) and diff them against the helper's to
  align the hand-appended submission transition (pointer
  last_record_coordinate bookkeeping). All affected tests were failing
  before this change; net state strictly better.

## Next Action

Repair the clarification-CAS family (134 tests): make
`_commit_accepted_clarification` and its siblings create the canonical
conflict attention record and retained context the CAS requires, beginning
from `atomic_store.py:6391`. in the Progress Log (pipeline/egress
removal from composition; re-anchor the 18 egress mutation tests to the
authorization read-set boundary; allowlist update with the dying test files),
then slice 6 (V3-era family repairs + full broad gate + WorkPlan closures).
