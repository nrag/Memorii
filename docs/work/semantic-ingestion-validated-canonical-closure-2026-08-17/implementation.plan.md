# Validated Canonical Closure Implementation WorkPlan

## Operation And Baseline

- Work type: `implementation`.
- Status: `complete (final closure 2026-09-03 at 7c5152b; see the Final
  Closure Record; live/operational and executed-CI evidence remain
  explicitly unclaimed)`.
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
  (performance evidence recorded; final-closure items in progress).
- Completed milestone packets: `direct-ingress-closure-slice.md`,
  `complete-trigger-and-durable-path-propagation.md` (family-proof closure
  2026-08-26), and `recovery-reconciliation-fresh-owner-propagation.md`
  (redelivery-door closure 2026-08-26; reconcile-branch disposition resolved
  2026-08-29 by the linked removal operation).
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
| `VCC-R01` digest reduction | digest-verification reuse landed 2026-08-26 (production-bound census 49,054 → 2,054 calls, 95.8% total / 96.5% repeated); default-on enablement and codec-level construction elimination landed through the linked default-on, encoder-hot-path, and member-reuse operations (successor v2 harness: 43,756 → 237 digest calls per delivery, 99.46%) | mode-parity diametric proofs; family and recovery production-root proofs | performance packet census; default-on PBD-EXP-014 v1/v2; member-reuse CE slice evidence | verified: reduction gate met with margin at every measured layer |
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
| Performance, rollout, gates, and final closure | 90 percent production-bound reduction met with margin (96.5 percent repeated; successor layers reach 99.46 percent); broad-gate baseline reconciled through the linked removal and suite-reconciliation operations (final broad gate 4038 passed / 12 dispositioned at `21dcaf3`); default-on rollout landed with diametric parity gate; final-closure items (acceptance-matrix gap fills, gate repair, refreeze, reviews, CI parity, docs) active 2026-09-03 | All | active |

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
| CI and command identities | `identity_hygiene` command invocation, shard-plan verification, diametric parity workflow, and benchmark/acceptance matrix rows | behavioral with evidence scope | Behavioral command identities only; the field-aware identity gate is green and the representative coordinate mutation corpus (6 spellings x 18 surfaces plus the traceability and concealment corpora) passes with behavioral node IDs (2026-09-03); CI execution evidence stays unclaimed until a workflow runs at a reviewed revision |

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
- Rollout contract as amended by the 2026-08-27 user decision (recorded in
  `docs/design/semantic_ingestion_validated_canonical_closure.md`): the
  substitution is enabled by default for every verified runtime; an explicit
  `canonical_evidence_enabled=False` constructor request is the only disabled
  path and is also the rollback switch (migration-free).
- Disabled mode allocates no evidence capability, index charge, or process
  reservation and executes the current full path.
- Capacity rejection occurs before substitution and executes the same full path.
- Rollback disables closure creation and substitution together.
- Mixed-version behavior is unchanged because no wire or persisted schema is
  introduced; process-local typed objects do not cross version boundaries.
- Observability is content-free and non-authoritative; sink unavailability cannot
  alter ingestion or durable outcomes.
- The diametric enabled/disabled parity gate runs on a four-hour scheduled
  cadence (`.github/workflows/canonical-evidence-parity-scheduled.yml`); its
  executed-CI evidence stays unclaimed until the branch reaches the default
  branch.

## Evidence Maturity Ledger

| Evidence | Current maturity | Required maturity for implementation closure |
| --- | --- | --- |
| Design and operation contract | specified and approved | unchanged approved baseline |
| Codec/span, capacity, security, rollback references | locally verified reference | corroborated by production implementation tests |
| Production binding | implemented and focused-proven for every mapped family (direct, composite, memory-write, Hermes turn/write, redelivery recovery) at revisions `4560d29`/`02502eb` | unchanged: implemented, source-bound, nonzero callers, focused path proof |
| Digest reduction | production-bound census (49,054 → 2,054; 95.8/96.5 percent) plus successor v2-harness evidence (43,756 → 237; 99.46 percent) recorded 2026-08-26 through 2026-09-02 | unchanged: locally verified production-bound implementation evidence and required CI if workflow-owned (CI execution not yet claimed; no workflow run at a reviewed revision) |
| Lifecycle and observability | deterministic tests including per-family exactly-once terminal snapshots; production-root capacity-refusal (reservation exhaustion), in-flight concurrent-writer lease isolation, and full-sentinel snapshot-privacy proofs added 2026-09-03 in `test_canonical_evidence_production_limits.py`; arena member-path-envelope, first-cause-latching, and hostile-sink cells added the same day | deterministic implementation tests including concurrency/privacy at production roots |
| CI | not claimed | exact applicable required jobs passing at reviewed revision |
| Live and operational | not claimed | separately identified; not inflated from local evidence |

## Gate And Known-Failure Ledger

Current known facts (reconciled 2026-09-03):

- Performance is landed and measured at every layer: the 2026-08-26
  production-bound census (49,054 → 2,054 digest calls, 95.8% total / 96.5%
  repeated) and the linked default-on/encoder-hot-path/member-reuse operations
  (v2 harness: 43,756 → 237 calls per delivery, 99.46%); the 90 percent gate is
  met with margin.
- The 47 pre-existing broad failures were resolved by the linked legacy-path
  removal operation plus its suite-reconciliation work; that operation's final
  broad gate at `21dcaf3` records 4038 passed / 12 dispositioned / 2 skipped,
  and the member-reuse CE-9 broad gate at `c9995a1` records 4070 passed /
  4 dispositioned.
- Gate repairs made 2026-09-03 during final closure: (1) the identity-hygiene
  gate, re-broken after the durations regeneration exposed 124 planning
  coordinates inside regenerated test node IDs, is green again — the three
  scanner corpus parametrizations now carry behavioral `ids=` and the durations
  artifact keys were remapped 1:1 (124 keys, values preserved); (2) the unit
  shard plan, red at ~730s estimated per shard against the 600s target after
  the corpus re-measurement, now uses six shards (~487s estimated, 19 percent
  headroom, matrix and config updated together); (3) the CI pyright command
  was discovered red with 868 errors against a clean merge base
  (`2a7a55e`, 0 errors, identical config) — all branch-introduced, dominated
  by `object`/`BaseModel`-loose annotations in `atomic_store.py` and
  `writer_admission.py`; resolved to 0 errors at `633307f` by a
  delegated annotation-precision writer. The remediation also surfaced and
  repaired one latent runtime crash: the matched retained-pending branch of
  `bootstrap_writer_handoff` built its authority-unavailable outcome with a
  terminal shape the result contract rejected, so a matching retry raised a
  pydantic `ValidationError` instead of failing closed;
  `BootstrapWriterHandoffResult.authority_unavailable` now accepts either
  authority-unavailable terminal (a runtime result contract, not a persisted
  schema; the digest body is computed over dumped runtime values and the
  crashing path never produced valid instances, so existing encodings are
  unchanged), with regression test
  `test_writer_handoff_result_carries_either_authority_unavailable_terminal`.
  Capacity-accounting precision note: the production arena charges the
  conservative flat approximation of the design's packed representation
  (`ENTRY_METADATA_CHARGE = 512` plus 64 bytes per member path); all frozen
  limits are enforced exactly, and the approximation is at least as large as
  the packed layout for the measured corpus.
- Candidate v12 reference evidence remains reference-class; production proof
  is carried by the milestone packets and linked-operation evidence above.
- Remaining implementation follow-ups: candidate refreeze, independent
  milestone and final reviews, CI parity record, and current-state
  documentation updates.
- Focused evidence recorded 2026-08-26 at `4560d29`/`02502eb`: family proofs
  `4 passed in 923.04s`; recovery proofs
  (`test_redelivery_recovery_uses_a_fresh_owner_and_leases_exact_prepared_bytes`,
  `test_redelivery_recovery_rejects_mutated_lease_coordinates`,
  `test_redelivery_recovery_outcomes_are_identical_across_enabled_and_disabled_modes`)
  each passing (~2-4 minutes each); replay/reopen modules `9 passed in
  752.70s` at `5bd516b`; arena suite green (62 passed 2026-09-03 including the
  new member-path-envelope, first-cause-latching, and hostile-sink cells);
  writer-admission focused matrix `9 passed`; ruff clean on all changed files.

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
- `2026-08-27` through `2026-09-02` (linked successor operations, recorded
  here as the performance-milestone link-record required by the member-reuse
  plan's CMR-008): the default-on operation landed enable-by-default with the
  amended rollout contract and the diametric parity gate; the legacy-path
  removal operation closed (final broad gate `21dcaf3`: 4038 passed, 12
  dispositioned); the suite-reconciliation debugging operation closed; the
  encoder-hot-path and member-reuse (construction-elimination) operations
  landed the codec-level reuse layers (CE-9 broad gate `c9995a1`: 4070
  passed, 4 dispositioned; digest calls per delivery 43,756 → 237); the
  test-runtime-reduction operation landed the production-roots family split,
  the race batching, the xdist equivalence proof (all four configurations
  equivalent at `253cee9`), and the durations regeneration. The member-reuse
  and test-runtime operations remain active on their own quiet-host
  measurement, review-closure, and GC-policy items; they are not blockers for
  this plan's 90 percent gate.
- `2026-09-03`: Final closure opened. Gate repairs: identity-hygiene 124
  findings resolved via behavioral corpus node IDs plus a 1:1 durations-key
  remap; unit shard capacity raised 4 → 6 shards on the re-measured corpus
  (~487s estimated per shard, under the unchanged 600s target); CI pyright
  command discovered red with 868 branch-introduced errors against the clean
  merge base and resolved to 0 by a delegated annotation-precision writer.
  Acceptance-matrix gap fills: production-root reservation-exhaustion
  capacity refusal, in-flight concurrent-writer lease isolation, and
  full-sentinel snapshot-privacy proofs added
  (`test_canonical_evidence_production_limits.py`); arena member-path
  envelope (exact/one-over at 32,768), first-cause latching through
  conflicting closes, and hostile-observability-sink cells added. Both
  binding validators (v11/v14) failed on source-hash drift and were
  regenerated at the frozen revision (32/32 and 5/5 mutations).
- `2026-09-03` (independent final review round, frozen candidate `542cd86`):
  `spec_auditor` APPROVED (`remaining_validated_p1_p2: []`; three P3
  follow-ups: stale next-action text, an under-recorded repair, and a
  charge-model precision note — the first fixed in this update, the latter
  two recorded above). `test_reviewer` found one `changes_required`
  verification defect: the CI pin refresh missed its mirrored assertions in
  `test_static_tooling_config.py`, leaving three unit-gate nodes red at the
  frozen revision — fixed at `78f844e` (module 18 passed).
  `correctness_reviewer` found one validated P2 (`changes_required`,
  runtime/verification): the reservation-exhaustion proof failed
  intermittently at the frozen revision, appearing as a wedged holder thread.
  Coordinator diagnosis (validated against the failure signature): a test
  protocol defect, not a product race — the holder release events were
  indexed by handoff-arrival order while the join loop iterated threads by
  start order; under load the orders diverge, so the loop released one
  thread's event while joining a different, still-paused holder, a
  guaranteed spurious join timeout. Fixed at `1b07094`: the wrapper captures
  the pausing thread under the same guard that assigns the arrival index and
  the release/join loop pairs them strictly; the reviewer's follow-ups
  (four-arena precondition before the fifth delivery; profile/codec/domain/
  schema sentinels in the privacy scan) are included. Green-run evidence at
  the fixed revision: module `3 passed in 244.91s` under load 7-10 (a second
  stability run recorded with the closure evidence). The reviewer's two P3
  follow-ups are recorded below.
- `2026-09-03` (recorded follow-ups, non-blocking):
  1. Path-level proof for the retained-pending arm of
     `bootstrap_writer_handoff` (five-field match/mismatch through the real
     method; the result-contract regression test covers the repaired crash
     site) — verification follow-up.
  2. A rare recovery-race corner in `_run_semantic_ingestion` now opens one
     bounded lease session before returning the same authority-unavailable
     outcome the pre-annotation code produced via an AttributeError (outcome
     and reason codes identical; identified by the correctness review of
     `633307f`) — runtime follow-up.
  3. `RetainingCanonicalClosureObservabilityDispatcher` retains terminal
     snapshots without bound in long-lived service processes (hundreds of
     bytes per delivery) — operability follow-up: bound it or default the
     production sink to the non-retaining dispatcher.
  4. The unit durations manifest lacks this session's eight new fast unit
     nodes until the next CI timing merge (default duration applies; shard
     estimates unaffected).

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

None. The operation is complete under the Final Closure Record below; the
recorded follow-ups are non-blocking and owned by their listed surfaces.

## Final Closure Record (2026-09-03)

The completion contract is satisfied at frozen revision `7c5152b` (manifest
`implementation-candidate-manifest-v2.json`, validator 9/9 mutations, clean
tree):

- every `VCC-R01`..`VCC-R12` row is implemented and verified (requirement
  coverage ledger; the 2026-09-03 gap fills complete the production-root
  capacity, concurrency, and privacy cells);
- the acceptance matrix passes through real production owners (v11 bindings
  32/32 mutations, v14 5/5, regenerated at the frozen tree; family,
  recovery, parity, production-limits, and arena owners cited in the
  milestone packets);
- the reduction gate is met with margin at every measured layer
  (95.8/96.5 percent production-bound census; 99.46 percent successor v2
  harness);
- enabled, disabled, and capacity-refused modes produce identical outcomes
  (diametric parity proofs plus the reservation-exhaustion root proof);
- every mapped root has a nonzero production caller and an exact typed
  authority chain (v11/v14 ledgers);
- all changed identities are behavioral; the field-aware identity gate and
  the representative coordinate mutation corpus pass (behavioral node IDs);
- the frozen-revision gate set: ruff clean; CI pyright command 0 errors;
  identity hygiene exit 0; both shard plans verify (6 x ~487s and 7 x ~569s
  against the unchanged 600s target); package smoke green; all workflow
  collection pins and their mirrors consistent; selector manifest valid;
  the broad unit gate recorded below;
- independent final reviews: `spec_auditor` APPROVED; `test_reviewer`
  APPROVED after the mirror-pin remediation; `correctness_reviewer`
  APPROVED after the reservation-protocol remediation — all three with
  `remaining_validated_p1_p2: []`, `remaining_blocks_approval: []`,
  `remaining_changes_required: []` (delta reviews 2026-09-03);
- production code, tests, evidence, ledgers, binding artifacts, and the
  candidate manifest agree; live/operational evidence and executed-CI
  evidence are explicitly unclaimed (no pull request exists; the parity and
  cadence workflows are wired and fire from the default branch only).

Broad unit gate at the frozen revision (adopted xdist command
`../.venv/bin/python3.12 -m pytest tests/unit -W error -p no:cacheprovider
-q -n 8 --dist loadfile`): two runs, `5 failed, 4081 passed, 2 skipped`
(1:45:46 and 2:08:50; junit preserved at
`evidence/final-broad-gate-junit.xml`). Every failure is dispositioned with
its exact signature:

1. `test_shipped_manifests_verify_real_local_english_assets` —
   `LinguisticAdapterUnavailable: local analyzer asset root is missing` —
   environmental on this host (stable across every recorded run and
   configuration; previously dispositioned by the CE and removal
   operations);
2. `test_exact_scenario_generation_closure_is_accepted` —
   `generation verification deadline exceeded` (wall-clock monotonic
   deadline);
3. `test_scenario_fixture_authority_passes_only_when_installed_as_explicit_authority` —
   `structural_derivation_unavailable`;
4. `test_registered_scenario_publishes_sequence_two_after_sequence_one` —
   `structural_derivation_unavailable`;
5. `test_jsonl_egress_repository_is_process_safe_reopenable_and_idempotent` —
   spawned-process exitcode timeout.

Nodes 2-5 are load-conditioned wall-clock/subprocess-timeout failures: the
host carried sustained external load 17-70 through both runs (recorded at
launch and in the run logs); the same nodes passed in the 2026-09-02
equivalence runs at representative load (all four configurations, 3 failures
total, two of which this closure fixed) and in today's isolation runs at
load ~8 where they were re-executed; their authoritative environment is the
isolated CI shard runner, which the wired six-shard gate enforces. This
matches the recorded dispositions of the removal operation's final gate
(deadline pins and slow-but-correct race timeouts under load).

```yaml
base_revision: 2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93
reviewed_revision: 7c5152b0b2a8977a9fb572e6805c956141e0e606
tested_revision: 7c5152b0b2a8977a9fb572e6805c956141e0e606
tested_tree_digest: clean working tree at launch; junit preserved
tree_state: clean
changed_surface_inventory_complete: true
scope_delta_resolved: true
authority_chains_complete: true
required_local_jobs:
  - ruff check memorii tests
  - pyright (CI command, memorii/ cwd)
  - memorii.tools.identity_hygiene
  - test_shards verify (unit, 6 shards)
  - test_shards verify (semantic-terminal-persistence, 7 shards)
  - package smoke (wheel + imports + dry-run eval + artifact validation)
  - broad unit gate (adopted xdist command)
  - bindings validators v11 (32 mutations) and v14 (5 mutations)
  - candidate manifest v2 validator (9 mutations)
  - workflow collection pins (10 / 87 / 224 / 3 / 2) plus mirrors
  - bootstrap graph transaction selector manifest validation
passed_local_jobs: same as required; broad gate 4081/4086 passed with the
  five failures dispositioned above
known_local_failures:
  - stanza local-analyzer-assets node (environmental, stable)
  - four load-conditioned deadline/subprocess nodes (dispositioned above)
failure_exclusions:
  - environmental: identical signature across every recorded run and
    configuration; assets absent on this host by design of the check
  - load-conditioned: prior representative-load green (equivalence record,
    all four configurations) plus isolation greens at load ~8; isolated CI
    shard runner is the wired authoritative environment
workflow_identities:
  - .github/workflows/pr-gates.yml (static-analysis, package-smoke,
    unit-test-shards 0-5, semantic-terminal-persistence 0-6, aggregates,
    provider-compatibility, semantic-ingestion family, benchmark gates)
  - .github/workflows/canonical-evidence-parity-scheduled.yml (mode parity
    + production admission limits, 4-hour cadence, exact count pins)
ci_event: not_applicable (no pull request; branch not on the default branch;
  scheduled workflows execute from the default branch only)
ci_executed_sha: not_applicable (same reason)
ci_executed_ref: not_applicable
remaining_validated_p1_p2: []
remaining_blocks_approval: []
remaining_changes_required: []
local_ci_parity: all workflow-selected deterministic commands reproduced
  locally green; GitHub-only behavior (matrix scheduling, artifact upload,
  runner isolation) unexecuted and unclaimed
acceptance_gate_inventory: implementation-acceptance-v12.md rows mapped to
  owners in the milestone packets; identity mutation corpus green
github_run_urls: []
pr_head_sha: not_applicable
pr_base_sha: not_applicable
merge_base_sha: 2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93
required_checks_green: not_applicable with reason (no pull request exists;
  execution of the wired gates is the promotion step recorded below)
```

Promotion note: opening the pull request and letting `pr-gates.yml` execute
at this head is the recorded next repository action; per
`.agents/PLANS.md`, that execution converts the wired-but-unclaimed CI
enforcement into executed evidence and is the entry point for `$review-pr`.

### Promotion Executed (2026-09-03/04)

Pull request #116 (`semantic-indexing-m4` -> `main`) was opened and
`pr-gates.yml` executed. The first run exposed two gate-integrity defects
that local runs could not see: the frozen traceability chains (CTV exact,
lifecycle-root, structural) had been desynchronized by the traceability
registry cascade's design edit without regenerating their pinned hashes and
known-answer vector, and the stanza analyzer-asset witness failed on every
environment without the provisioned asset root. Both were repaired at
`0d928fa` (chain regeneration with the compiler verifying the authority
byte-identical; the witness gated on asset availability with adversarial
coverage retained) and the full workflow then completed green:

- PR: https://github.com/nrag/Memorii/pull/116
- Run: https://github.com/nrag/Memorii/actions/runs/33832592411
  (event `pull_request`, head `0d928fa`, conclusion `success`, all jobs)
- The executed evidence covers the previously unclaimed CI items: the
  static-analysis type gate (CI's floating pyright agrees, 0 errors), the
  six-shard unit gate (the four load-conditioned deadline/subprocess nodes
  pass on isolated runners, completing their disposition), the CTV exact
  chain, package smoke, provider compatibility recapture, the semantic
  ingestion families, the bootstrap-graph transaction matrix, and the
  benchmark artifact gates.

The closure record's revision-bound evidence stands at `7c5152b`; the
`0d928fa` gate-integrity repair is recorded here per the
post-closure-change rule, with every affected gate re-executed green by the
run above. `$review-pr` on PR #116 is the remaining approval step.
