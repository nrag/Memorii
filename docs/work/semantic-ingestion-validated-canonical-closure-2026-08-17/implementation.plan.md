# Validated Canonical Closure Implementation WorkPlan

## Operation And Baseline

- Work type: `implementation`.
- Status: `in progress; trigger-family and recovery milestones complete 2026-08-26; performance milestone active`.
- Repository: `Memorii`.
- Approved design:
  `docs/design/semantic_ingestion_validated_canonical_closure.md`.
- Approved candidate manifest:
  `docs/work/semantic-ingestion-validated-canonical-closure-2026-08-17/candidate-manifest-v12.json`.
- Candidate lock:
  `1e314415930bd43b176b50c28ba8f8b8250a7fa5d959758bc60acd47fc47b2ca`.
- Candidate tracked artifacts: `109`.
- Implementation candidate freeze: `implementation-candidate-manifest-v1.json`
  is superseded by the current remediation edits; no current implementation
  candidate is claimed.
- Design SHA-256:
  `57a422e0366bf5792283ca71c0d8af08f0215677dfe8139138e1f75097b51474`.
- Approval addendum SHA-256:
  `2bb9fb741528dc1813719340cc7c62bbe3f5b69c2c7242d73205b6d7969d68d2`.
- Implementation acceptance matrix SHA-256:
  `620b15c947cb6497e749db43ed38465acd01c36a3ce7796a35c4b657ba4958fd`.
- Parent design WorkPlan:
  `docs/work/semantic-ingestion-validated-canonical-closure-2026-08-17/design.plan.md`.
- Active milestone packet:
  `docs/work/semantic-ingestion-validated-canonical-closure-2026-08-17/milestones/performance-rollout-gates-and-final-closure.md`
  (to be created at performance-milestone start; until then the recovery and
  trigger-family packets record the latest completed evidence).
- Completed milestone packets: `direct-ingress-closure-slice.md`,
  `complete-trigger-and-durable-path-propagation.md` (family-proof closure
  2026-08-26), and `recovery-reconciliation-fresh-owner-propagation.md`
  (redelivery-door closure 2026-08-26, reconcile-branch disposition pending).
- Active linked operation:
  `docs/work/semantic-ingestion-recovery-reconcile-baseline-debug-2026-08-18/debug.plan.md`
  (complete 2026-08-26; closure reviewed by `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer` with
  `remaining_validated_p1_p2: []`; follow-ups transferred into the active
  milestone packet and the later trigger-family milestone).

## Objective

Implement operation-scoped validated canonical closure through real production
composition roots so duplicate canonical reconstruction and full digest work
falls by at least 90 percent while canonical bytes, semantic validation, writer
admission, persistence, replay, failure behavior, rollback, and public outcomes
remain identical.

## Completion Contract

The operation completes only when:

- every `VCC-R01` through `VCC-R12` row is implemented and verified against the
  exact approved candidate and implementation revision;
- the complete acceptance matrix in `implementation-acceptance-v12.md` passes
  through real production owners with thin fixtures;
- enabled execution records at least 90 percent fewer repeated full digest
  computations than the frozen reference family while retaining mandatory
  independent validation and writer work;
- enabled, disabled, and capacity-rejected modes have byte-identical canonical,
  digest, promise, replay, admission, durable, and public outcomes;
- every mapped root and trigger has a nonzero production caller and exact typed
  authority chain to validation and durable or explicit no-write outcome;
- all changed identities are behavioral, the field-aware identity gate and
  representative mutations pass, and no planning coordinate leaks into code,
  tests, schemas, artifacts, diagnostics, or CI labels;
- focused, broad deterministic, static, type, performance, rollback, package,
  and applicable CI gates pass at one frozen implementation revision;
- independent milestone and final reviewers leave
  `remaining_validated_p1_p2: []` and no unresolved required
  `blocks_approval` or `changes_required` finding;
- production code, tests, generated evidence, binding ledgers, current-state
  documentation, and workflow pins agree; and
- any unavailable live or operational evidence remains explicitly unclaimed.

## Scope

Included:

- canonical codec results, traversal-issued member paths and exact spans;
- validated operation closure, scope capability, reservation, capacity,
  lifecycle, leases, teardown, and terminal observability;
- typed closure propagation through provider, Hermes, normalization, graph,
  atomic-store, writer, persistence, retry, and replay paths;
- removal or bypass only of duplicate reconstruction and full digest work after
  exact authority checks;
- private disabled-by-default rollout and migration-free rollback;
- focused production-path tests, adversarial and concurrency matrices,
  performance evidence, static/type checks, and required CI wiring.

Excluded:

- digest algorithm, canonical codec/profile meaning, public or persisted schema,
  event, replay, semantic validation, writer policy, or transaction changes;
- global or cross-operation caching;
- model-, adapter-, provider-, or caller-supplied proof authority;
- broad test-suite redesign unrelated to this feature;
- live-provider or operational certification unless promoted explicitly later;
- unrelated performance refactors.

## Approved Deviations And Decisions

- No pre-fix multi-hour baseline rerun is required; the frozen requirement and
  reference census is the comparison authority approved by the user.
- Candidate v12 is `Approved with follow-ups`; `DREV-003` and `DREV-004` are
  implementation acceptance checks, not design blockers or product-remediation
  authority.
- The current arena is an existing interim implementation, not permission to
  weaken or reinterpret the approved closure contract.
- No material semantic question is currently unresolved. A required change to
  public/persisted semantics, trust ownership, frozen limits, rollback, or
  production composition returns to `$build-design`.

## Requirement Coverage Ledger

| Requirement | Implementation | Tests | Other evidence | Status |
| --- | --- | --- | --- | --- |
| `VCC-R01` digest reduction | substitution wired at writer handoff and replay reload for all families; codec-level child-slice reuse and production-bound measurement not started | None | Approved reference counterfactual (42,955 baseline vs 176 counterfactual) | not started (performance milestone is next) |
| `VCC-R02` one-pass canonical result | prepared-source staging is explicit through every trigger family; lease reaches both durable consumers | family + recovery production-root proofs | milestone packets | supported in production for all families |
| `VCC-R03` typed non-ambient authority | explicit sealed-only binding; fresh arena per delivery through every family root | arena tests, v11, family proofs | milestone packets | supported in production for all families |
| `VCC-R04` exact path/span identity | traversal-issued member evidence including equal-value paths | arena tests | remediation slice | supported locally |
| `VCC-R05` complete semantic validation | staging occurs only after preparation/publication validation on every family path | family + recovery production-root proofs | milestone packets | supported in production for all families |
| `VCC-R06` fresh writer admission | atomic handoff and replay reload recheck current writer on every family path | family + recovery production-root proofs | milestone packets | supported in production for all families |
| `VCC-R07` scope and provenance rejection | five-coordinate sealed checks at both lease consumers | arena tests + v11 + production mutation proof (`test_redelivery_recovery_rejects_mutated_lease_coordinates`) | milestone packets | supported in production |
| `VCC-R08` bounded coherent capacity and lease drain | four reservations/fifth refusal/reacquisition; unique lease tokens drain after close | 29 focused arena tests | remediation slice | supported locally |
| `VCC-R09` persistence and replay identity | redelivery recovery preserves prepared/marker bytes, reloads through the leased atomic consumer, and matches enabled/disabled outcomes and durable projections | redelivery recovery proofs (fresh-owner, mutation, mode-parity) | recovery packet | supported in production for the redelivery family |
| `VCC-R10` complete production reachability | direct, composite, memory-write, Hermes turn/write, and redelivery recovery roots all stage, seal, lease, and consume | family production-root proofs (4 cases), recovery proofs (3 cases) | milestone packets | supported in production for all mapped families; reconcile-door structural finding recorded |
| `VCC-R11` content-free observability | service-owned retaining dispatcher emits exactly one content-free terminal snapshot per delivery on every family | arena terminal tests plus per-family production-root assertions | milestone packets | supported in production for all families |
| `VCC-R12` disabled/rejected rollback | local disabled/refused full-path behavior; redelivery mode-parity proof (outcomes, durable projections, idempotence) | arena tests + mode-parity production proof | recovery packet | supported locally plus redelivery parity |

## Milestone Roadmap

| Milestone | Observable vertical outcome | Requirements | Status |
| --- | --- | --- | --- |
| Readiness and production-path map | One revision-bound map of owners, callers, tests, gates, dirty-tree ownership, and exact validation commands; no writer starts before approval | All | complete |
| Direct ingress closure slice | Prepared-source `sync_event` stages, seals, leases, and reaches atomic handoff | R02-R10 partial; R03/R04/R07/R08/R11/R12 locally supported | complete |
| Complete trigger and durable-path propagation | Direct, composite, memory-write, and Hermes hooks each proven to stage, seal, lease, and consume at both durable consumers | R02-R12 | complete (2026-08-26, `02502eb`); builder-blocked writer-preservation cells recorded as follow-ups |
| Recovery/reconciliation fresh-owner propagation | V3 mid-ingestion recovery proven through the redelivery door with fresh owner, sealed lease into the replay reload, five-coordinate rejection, and enabled/disabled parity; reconcile branch structural finding recorded with pending repair-or-remove decision | R02/R03/R05-R12; R01 measurement contribution only | complete for the redelivery door (2026-08-26, `4560d29`); reconcile branch disposition pending |
| Performance, rollout, gates, and final closure | 90 percent production-bound reduction met with margin (96.5 percent repeated); broad-gate reconciliation partially complete (provider-service green, identity gate green, +3 composition fixes); 47 pre-existing legacy-fixture failures classified for a dedicated operation; acceptance matrix, refreeze, reviews, CI, and docs remain | All | active |

Milestone labels organize work only and may not appear in production or test
filenames, symbols, schemas, fixtures, artifacts, diagnostics, or workflow jobs.

## Expected Change Map

The readiness milestone must confirm this list before edits. Expected production
owners include:

| Area | Expected files and owners | Planned behavior |
| --- | --- | --- |
| Semantic codec | `memorii/memorii/core/semantic_ingestion/contracts.py` | Return one immutable canonical result with exact root bytes, digest, binding, and traversal member index |
| Typed memory codec | `memorii/memorii/core/memory_evolution/ingestion_contracts.py` | Share the same traversal/span authority without second serialization |
| Closure lifecycle | `memorii/memorii/core/semantic_ingestion/canonical_evidence_arena.py` or one adjacent behavioral owner selected in preflight | Scope owner, reservation coordinator, sealed capability, slice leases, limits, teardown, metrics |
| Provider composition | `memorii/memorii/core/provider/service.py`, `memorii/memorii/core/provider/ingestion.py` | Private mode selection, operation ownership, typed handoffs, real `ProviderIngestionCoordinator` path |
| Hermes integration | `memorii/memorii/integrations/hermes_provider.py` | Thin propagation through all supported hooks without new authority |
| Source normalization | `source_normalization_stage.py`, `source_normalization_execution.py` | Consume exact certified slices while preserving recovery and validation |
| Graph execution | `bootstrap_graph_host.py`, `bootstrap_graph_builtin.py` | Carry non-authoritative closure data through existing host authority |
| Atomic memory writes | `memorii/memorii/core/memory_evolution/atomic_store.py` | Reuse exact construction only after existing transaction and writer admission |
| Terminal persistence | `memorii/memorii/core/semantic_ingestion/persistence.py` | Preserve precommit, authorization, durable identity, and replay |
| Tests | Nearby unit/integration owners confirmed by preflight | Behavioral, boundary, failure, retry, concurrency, privacy, rollback, and performance proof |
| Tooling and CI | Existing static tooling, benchmark, and workflow owners confirmed by preflight | Revision-bound gates without planning-derived job names |
| Documentation | Current architecture, binding ledger, implementation WorkPlan and evidence | Accurate implemented state and evidence maturity |

Non-applicable unless a discovery reopens design: prompts, model schemas,
public APIs, persisted schemas, migrations, command-line interfaces, and external
adapter protocols.

## Production Entrypoint Binding Ledger

| Trigger family | Composition root and ingress | Required closure outcome | Status |
| --- | --- | --- | --- |
| `direct_sync` | `ProviderMemoryService.sync_event` | prepared-source stage/seal/lease/handoff, exact redelivery, and service-owned terminal snapshot | proven: writer-handoff lease proof, fresh-redelivery-lease proof, and the recovery packet's redelivery family (fresh owner, mutation rejection, mode parity) |
| `direct_composite_sync` | `ProviderMemoryService._sync_composite_event` | per-child stage/seal/lease into both durable consumers with exactly-once terminal snapshots | proven: `test_every_trigger_family_stages_seals_and_leases_prepared_bytes[composite]` (2026-08-26, `02502eb`) |
| `direct_memory_write` | `ProviderMemoryService.apply_memory_write` | stage/seal/lease into both durable consumers with exactly-once terminal snapshots | proven: same family proof `[memory_write]` plus Hermes `[hermes_write]` |
| `hermes_sync` through `hermes_memory_write` | `HermesMemoryProvider` hooks | per-hook sealed proof through composite fan-out and direct write | proven: same family proof `[hermes_turn]` (both composite children) and `[hermes_write]`; 4 cases passed in 923s |
| redelivery recovery (cross-family) | `ProviderMemoryService.sync_event` over a retained marker + found index | fresh owner and sealed lease into `reload_bootstrap_recovery_replay_v3` | proven by the recovery packet's three production-root proofs; the reconcile-door variant is structurally unreachable (finding recorded in the recovery packet) |

Historical “implemented”/“incomplete” text is superseded by the 2026-08-26
family-proof closure in the M2 packet and the recovery packet's validation
matrix results.

Validation checkpoint note:
- `milestones/source-bound-production-entrypoint-map.md` was produced at revision `b9daf00a0e6956e51106756f1baaf23190c688bb`.
- `readiness-and-production-path-map.md` records the earlier frozen map.
- The current-tree v11 builder regenerated its ledger/oracle after the
  token/dispatcher correction and `validate_production_entrypoint_bindings_v11.py`
  passed all 32 required mutations. It is source-shape evidence for the direct
  prepared-source family, not all-root reachability proof.

## Authority Chain

Approved chain:

1. Canonical codec traversal owns canonical bytes, root digest, binding, paths,
   and spans.
2. Semantic validation owns sealed operation-capability issuance.
3. Provider service owns private operation mode and lifetime.
4. Consumers verify issuer and all five scope coordinates before leasing a
   certified slice.
5. Existing semantic, provenance, lifecycle, policy, transaction, authorization,
   and writer stages always execute.
6. Each writer performs fresh local admission on exact committed bytes.
7. Persistence and replay retain existing bytes, identities, outcomes, and
   transaction behavior.
8. Terminal observability receives only the approved content-free projection
   and cannot affect authority or outcomes.

Any optional handoff, zero-caller owner, ambient authority, caller proof,
success-shaped fallback, or test-only composition root fails readiness.

## Identity Ledger

| Surface | Identity | Class | Decision and proof |
| --- | --- | --- | --- |
| Production runtime identities | `ProviderMemoryService`, its private retaining dispatcher, `ProviderIngestionCoordinator`, `CanonicalEvidenceArena`, tokenized `CanonicalEvidenceLease`, `SemanticIngestionAtomicStore`, `_composed_semantic_runtime` | behavioral | Proven for every mapped family and the redelivery recovery door at `4560d29`/`02502eb`; token uniqueness, enabled/disabled root snapshots, and content-free terminal snapshots are focused-tested; see milestone packets |
| Evidence identities | `canonical_evidence_arena.py`, `canonical_evidence_lock_resolver.py`, `canonical_evidence_performance_runner.py`, `test_canonical_evidence_arena.py` and fixture helpers | behavioral | Behavioral fixture names and helper modules are not planning/evidence coordinate names; validated by `milestones/readiness-identity-ledger.md` |
| Persisted/public values | `CanonicalCodecResult`, `CanonicalMemberIndex`, `ValidatedCanonicalClosure` | behavioral | No persisted/public identity drift introduced; governed by canonical contract files noted in `changed-surface-ownership-ledger.md` |
| Traceability coordinates | `VCC-R01` through `VCC-R12` | planning/evidence (non-behavioral) | Allowed only in WorkPlan, design, evidence, and review records; explicitly excluded from production tests, fixtures, symbols, workflow jobs, and serialized outputs |
| CI and command identities | `identity_hygiene` command invocation and benchmark/acceptance matrix rows | behavioral with evidence scope | Behavioral command identities only; follow-up required is running the field-aware identity gate and representative mutation rows in `implementation-acceptance-v12.md` after identity drift reconciliation |

## Validation Matrix

The complete normative matrix is
`implementation-acceptance-v12.md`. Milestone closure must record exact command,
working directory, runtime, revision/tree identity, exit status, and evidence
maturity. Minimum proof families are:

- codec byte/span/digest identity and decoder/re-encoder compatibility;
- typed propagation through every real root, trigger, validator, writer, durable
  outcome, retry, and replay path;
- disabled, enabled, process-refused, and every exact/one-over capacity boundary;
- all five scope-coordinate attacks, capability forgery, pre-seal lookup,
  post-seal mutation/fallback, stale lease, duplicate close, and release races;
- every terminal reason with zero and active leases, exact metric types/ranges,
  sentinel privacy, recorded/unavailable parity, and exactly one emission;
- two-writer and retry-local admission;
- at least 90 percent repeated full-digest reduction with mandatory work retained;
- enabled/disabled/rejected promise, bytes, digest, replay, durable, and public
  outcome equivalence;
- field-aware identity hygiene and representative rejected coordinate mutations.

## Provisional Verification Commands

The readiness packet must confirm exact test node owners before replacing the
focused placeholders. Broad commands, run once at the appropriate frozen
revision from `memorii/`, are expected to include:

```bash
../.venv/bin/python -W error -m pytest tests/unit -p no:cacheprovider
../.venv/bin/python -m ruff check memorii tests
../.venv/bin/pyright --pythonpath "$(../.venv/bin/python -c 'import sys; print(sys.executable)')"
../.venv/bin/python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json
```

The preflight must read current workflow and development documentation before
declaring these commands equivalent to repository or CI gates. Expensive
performance and exhaustive matrices belong in dedicated bounded gates, not the
fast unit suite.

## Migration, Rollout, Rollback, And Compatibility

- No persisted-data migration or replay conversion.
- Private mode is disabled by default.
- Disabled mode allocates no evidence capability, index charge, or process
  reservation and executes the current full path.
- Capacity rejection occurs before substitution and executes the same full path.
- Rollback disables closure creation and substitution together.
- Mixed-version behavior is unchanged because no wire or persisted schema is
  introduced; process-local typed objects do not cross version boundaries.
- Observability is content-free and non-authoritative; sink unavailability cannot
  alter ingestion or durable outcomes.

## Evidence Maturity Ledger

| Evidence | Current maturity | Required maturity for implementation closure |
| --- | --- | --- |
| Design and operation contract | specified and approved | unchanged approved baseline |
| Codec/span, capacity, security, rollback references | locally verified reference | corroborated by production implementation tests |
| Production binding | implemented and focused-proven for every mapped family (direct, composite, memory-write, Hermes turn/write, redelivery recovery) at revisions `4560d29`/`02502eb` | unchanged: implemented, source-bound, nonzero callers, focused path proof |
| Digest reduction | locally verified reference counterfactual | locally verified production-bound implementation evidence and required CI if workflow-owned |
| Lifecycle and observability | deterministic implementation tests including per-family exactly-once terminal snapshots; concurrency/privacy remain arena-local | deterministic implementation tests including concurrency/privacy at production roots |
| CI | not claimed | exact applicable required jobs passing at reviewed revision |
| Live and operational | not claimed | separately identified; not inflated from local evidence |

## Gate And Known-Failure Ledger

Current known facts:

- The current production path exhibits severe duplicate reconstruction/digest
  cost; the frozen reference family records 42,955 full computations and the
  approved counterfactual records 176.
- The arena is the approved closure owner for lifecycle/leases; codec-level
  child-slice reuse and the production-bound digest counter are not yet
  implemented (performance milestone).
- Candidate v12 reference evidence passes but is not production proof.
- Remaining implementation follow-ups: performance reduction, broad-gate
  baseline reconciliation, candidate refreeze, and independent review.
- Focused evidence recorded 2026-08-26 at `4560d29`/`02502eb`: family proofs
  `4 passed in 923.04s`; recovery proofs
  (`test_redelivery_recovery_uses_fresh_owner_and_leases_exact_prepared_bytes`,
  `test_redelivery_recovery_rejects_mutated_lease_coordinates`,
  `test_redelivery_recovery_outcomes_are_identical_across_enabled_and_disabled_modes`)
  each passing (~2-4 minutes each); replay/reopen modules `9 passed in
  752.70s` at `5bd516b`; arena `29 passed`; writer-admission focused matrix
  `9 passed`; provider-service module `39 passed` with one pre-existing
  failure; ruff clean on all changed files.
- Pre-existing broad failures verified against clean base
  `b9daf00a0e6956e51106756f1baaf23190c688bb` (isolated worktree, 2026-08-26):
  `test_semantic_provider_composition.py` failed 45 of 59 at base vs 43 of 65
  on the current branch (this work net-fixed 8);
  `test_bootstrap_graph_coordinator_v3.py` has 4 failures verified pre-existing
  at `5f61c9c` via stash-revert; `test_provider_service.py::
  test_provider_preserves_caller_owned_event_time` is pre-existing. These
  belong to broad-gate reconciliation, not to closure-feature regressions.
- `memorii.tools.identity_hygiene` currently fails during allowlist
  validation: two `legacy_rejection_vector` exceptions pin exact
  line:column locations in `test_semantic_ingestion_pipeline.py` (modified by
  this branch's original dirty tree, commit `5bd516b`) and
  `test_semantic_pipeline.py` that no longer match
  (`legacy rejection exception requires an exact rejecting test proof`). The
  allowlist itself is unmodified since `eb70c9d`. Reconciling the pinned
  locations (or the field-aware identity gate follow-up below) belongs to
  broad-gate reconciliation.

No existing failure may be dismissed without identical clean-baseline evidence;
no broad suite should run repeatedly during construction.

## Delegation And Cost Ledger

| Task | Role | Ownership | Rationale | Status |
| --- | --- | --- | --- | --- |
| Production path and caller map | `code-mapper` | read-only consultation | Exact binding preflight | consulted |
| Test, runtime, and workflow inventory | `test-review` | read-only consultation | Focused proof boundary | consulted |
| This remediation slice | sole writer | overlapping files | Coherent implementation/governance ownership | active |
| Milestone review | `spec_auditor`, `correctness_reviewer`, `test_reviewer` | read-only | Independent bounded judgment at frozen candidate | not started |

The coordinator owns scope, plans, evidence, finding classification, and final
completion; the named consultations were read-only and this agent is sole writer.

## Risks And Stop Conditions

| Risk | Control | Stop condition |
| --- | --- | --- |
| Hidden duplicate serialization remains | Instrument owner-level construction and digest counts | Cannot reach 90 percent without changing approved trust or identity semantics |
| Closure bypasses validators or writers | Typed handoffs and real production path tests | Required owner cannot be reached without weakening validation/admission |
| Capacity or concurrency leaks authority | Closed lifecycle, locks/leases, exact boundaries and races | Approved limits or rollback semantics must change |
| Metrics leak content or affect outcomes | Closed types, sentinels, sink-unavailable parity | Required operational contract conflicts with governing privacy/failure rules |
| Scope expands into adjacent refactor | Changed-surface ledger and sole-writer packets | Completion requires unrelated subsystem redesign |
| Existing user changes overlap | Dirty-tree ownership map before edits | Ownership cannot be determined safely |

Stop and return to design for a material semantic or authority decision. Stop as
blocked only under `.agents/PLANS.md`; ordinary implementation uncertainty is
resolved inside this WorkPlan.

## Decisions And Progress

- `2026-08-17`: Approved candidate v12 and convergence addendum accepted as the
  implementation baseline.
- `2026-08-17`: Implementation acceptance matrix imported without promoting
  reference evidence to production maturity.
- `2026-08-17`: Four vertical milestones selected; no production/test edit or
  implementation validation has run.
- `2026-08-26`: Linked debugging operation closed under independent review
  (`remaining_validated_p1_p2: []`); its writer-admission and V3 replay
  corrections are the accepted baseline (commit `5f61c9c`).
- `2026-08-26`: Recovery milestone closed through the redelivery door
  (commit `4560d29`): the sealed lease now propagates from the writer handoff
  through `_run_semantic_ingestion` into the replay reload on the direct V3
  path; three production-root proofs (fresh owner, five-coordinate mutation
  rejection, enabled/disabled parity) pass. Decision recorded, not unilateral:
  the reconcile leased branch is retained unchanged because repairing it
  requires persisting a V3 execution plan (a durable record-content change
  that returns to `$build-design`) while removal is behavior-neutral cleanup;
  the coordinator defers that disposition to the user.
- `2026-08-26`: Trigger-family milestone closed (commit `02502eb`): composite,
  memory-write, and both Hermes hooks have family-specific sealed proofs; the
  writer-admission family gaps for Hermes/factory/filesystem roots are covered
  and the runtime-validation bridge cleanup landed with a focused deferral
  test. Builder-blocked cells (factory/filesystem existing-record preservation
  and JSONL variants) are recorded as follow-ups in the M2 packet.

## Remediation Reopening (2026-08-18)

(Historical record as of 2026-08-18; the "remain unproven" claims below were
superseded on 2026-08-26 by the family-proof and recovery milestones.)

- Coverage: the bounded lifecycle/dispatcher correction is recorded in
  `milestones/sealed-authority-lifecycle-remediation.md`; it supports local
  R08/R11 behavior and leaves parent-milestone requirements partial.
- Production-entrypoint bindings: direct prepared-source redelivery uses a new
  owner and lease before idempotent marker return; composite, memory-write,
  Hermes, replay, and other durable families remain unproven.
- Identity ledger: tokenized `CanonicalEvidenceLease`, the private retaining
  dispatcher, and `CanonicalMemberEvidence` are behavioral private runtime
  identities; no persisted or public schema changed.
- Changed surface: this correction owns `canonical_evidence_arena.py`,
  `provider/service.py`, focused arena/provider/production-root tests, the
  generated v11 governance artifacts, and the active remediation/index packets;
  all other dirty files remain shared/unmodified here.
- Gates: 29 focused arena tests passed in 9.94s; the enabled production-root
  dispatcher/lease proof passed in 32.72s; the disabled service-root dispatcher
  proof passed in 9.34s; v11 passed all 32 mutations; Ruff passed on the changed
  Python files. Candidate v1 is superseded; no broad suite ran.
- Known limitation: replay and other durable families have no sealed lease
  consumer proof.
- Delegation: code-mapper consultation inspected production callers and
  test-review consultation inventoried the focused proof; this agent remains
  sole writer for the overlapping arena/provider/test/governance slice. The
  independent candidate review confirmed the lease and observability findings;
  its overlapping coverage finding is deduplicated in the active M3 packet.
- Progress and evidence: `MAX_PROCESS_RESERVED_BYTES` is 67,108,864 and the
  fifth reservation refuses; every sealed lookup now has a unique token; close
  drains without aliasing; the service-owned dispatcher records content-free
  snapshots for enabled and disabled roots; v11 passed its current 32-mutation
  contract. Recovery, all-root, and replay evidence is now production-proven
  (2026-08-26 sections above); performance evidence remains the open item.

## Next Action

Decide the two open dispositions — the unreachable reconcile branch
(repair via a V3 execution-plan persistence design change, or remove the
dead branch) and whether to open the dedicated legacy-fixture
reconciliation operation for the 47 remaining pre-existing failures — then
run the final closure items: full acceptance matrix, candidate refreeze,
independent milestone and final reviews, CI wiring, and current-state
documentation updates.
