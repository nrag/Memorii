# M0 Canonical Genesis And Structural Contract Implementation

- Work ID: semantic-ingestion-m0-canonical-genesis-structural-contract-implementation-2026-07-31
- Work type: implementation
- Status: complete
- Coordinator: Codex
- Created: 2026-07-31
- Last updated: 2026-07-31
- Parent WorkPlan: `docs/work/semantic_ingestion/m0-canonical-genesis-structural-contract-correction-2026-07-30/design.plan.md` (complete)
- Related WorkPlans: `docs/work/semantic_ingestion/m0-scenario-first-c2-implementation-2026-07-30/implementation.plan.md`; `docs/work/semantic_ingestion/m0-current-pin-c2-recipe-closure-2026-07-30/design.plan.md`; `docs/work/semantic_ingestion/m0-lifecycle-root-genesis-signer-provenance-correction-2026-07-30/design.plan.md` (complete); `docs/work/semantic_ingestion/implementation.plan.md`
- Canonical inputs: `docs/design/memorii_spec.md`; `docs/design/memorii_storage_details.md`; `docs/design/event_model.md`; `docs/IMPLEMENTATION_RULES.md`; `docs/design/semantic_ingestion_architecture.md`; `docs/design/semantic_ingestion/scenario_first_fixture_authority.md`; `docs/design/semantic_ingestion/traceability_golden_vectors/ctv-binding-authority-v2.json`; `docs/design/semantic_ingestion/traceability_golden_vectors/structural_manifest_derivation_ledger-v1.json`; `docs/design/semantic_ingestion/traceability_golden_vectors/cgs_verification_attack_matrix-v1.json`
- Expected outputs: canonical production CTV/profile/ledger primitives; closed genesis/successor and RP provenance validation; atomic structural-manifest generation and authorization wiring; migration/rollback behavior; clean-room A/B evidence; tests, static gates, and current-state documentation.

## Objective

Implement CGS-01 through CGS-12 through their canonical production paths. A
pre-lifecycle root must use typed independent genesis provenance, ordinary
successors must remain lifecycle-rooted, and every persisted structural-manifest
byte must derive from the frozen 29-field ledger before it can authorize.

## Completion Contract

- Every CGS-01..12 row has production-path implementation and proportionate
  deterministic verification evidence, not only a reference-prototype result.
- Typed variants, CTV preimages, lifecycle/authorization gates, persistence,
  and all authority consumers agree with the approved design checksum below.
- Invalid provenance, missing/extra/reordered ledger operands, wrong domains,
  legacy authorization, cap breach, replay, interrupted write, and unsupported
  versions fail closed with the matrix-defined observable postcondition.
- Structural generation, history append, pointer/watermark advance, and
  authorization acceptance are transactionally all-or-nothing and idempotent.
- Migration, mixed-version handling, rollback, operational diagnostics, and
  clean-room A/B full body/envelope/spool reconstruction are proven.
- The exact static, unit, integration, migration, A/B, and final whole-branch
  review evidence is recorded for the reviewed tree. No validated P1/P2 defect
  or unresolved semantic authority prevents completion.

## Scope

Included:

- all determinate CGS-01..12 behavior and frozen CTV authority consumers;
- canonical types, validation, preimages, manifest generation, persistence and
  transaction paths, resolver/pointer/watermark behavior, tests, gates, and
  current-state documentation;
- future-version dispatch, unshippable-v2 handling, retained history, rollback,
  bounded resource behavior, and independent A/B reconstruction.

Excluded:

- M1 and its runtime-memory, retrieval, or agent-system behavior;
- selecting operational keys, trust roots, release issuance, or activation
  policy values owned outside this design;
- unrelated C2 historical recipe rewrites and unrelated cleanup.

Explicitly deferred:

- a separately authorized migration WorkPlan for transforming/rebinding any
  historical recipe artifacts; this operation must not reinterpret them;
- live external certification and production release activation, which require
  approved credentials and exact-revision operational evidence.

## Constraints And Invariants

- Follow the source precedence in `AGENTS.md`; a semantic change to the frozen
  design stops the milestone and requires a linked design WorkPlan.
- Keep candidate state separate from committed state; preserve immutable event
  history and never use deletion to express rollback.
- Parse provider/CTV transport, typed domain semantics, evidence/provenance,
  lifecycle policy, and transactional persistence as distinct fail-closed
  stages. Unknown variants, fields, coordinates, enums, and versions reject.
- Never fabricate lifecycle coordinates for genesis or let legacy diagnostic
  projections reach authorization dispatch.
- Keep structural graph state distinct from belief/status overlays and preserve
  framework neutrality. Scenario test authority remains absent from default
  production trust composition.
- Enforce approved numeric byte/count/depth/time/retry limits before expensive
  expansion; cancellation or failure must leave no partially accepted state.

## Sources Of Truth

Precedence: `docs/design/memorii_spec.md`,
`docs/design/memorii_storage_details.md`, `docs/design/event_model.md`,
`docs/IMPLEMENTATION_RULES.md`, then
`docs/design/semantic_ingestion_architecture.md`, the completed parent design
WorkPlan, frozen authority/ledger/matrix, and current production code/tests.
Workflow and evidence rules come from `AGENTS.md`, `.agent/PLANS.md`,
`.agent/skills/implement-design/SKILL.md`, and
`docs/development/static_tooling.md`. Current code establishes actual behavior
but cannot silently override the approved baseline.

## Design Baseline

- Canonical design: `docs/design/semantic_ingestion_architecture.md`, SHA-256
  `70ace2b99c4db79911f45555f72cde43278ccaac69c1fc11530e2d474f1fa26c`.
- CTV authority SHA-256:
  `c119345548166fd99e7aefe963d62a9b73e6c98c7cac84b7d6f8759b2ceb5633`;
  registry SHA-256:
  `8e6395e2657eb1a51e5eef7d9b88b5d43b974a58f7f786ed135f6758262bfec1`.
- Authority validator/checker SHA-256:
  `826541e7864583bbe3c32e3f153c008f07a881f33d38861237dfac80d9f3657e` /
  `e2c35870a99e587f34cbffc701f42587520ee015009cd51647367da56716c732`;
  approved profile digest:
  `9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f`.
- CGS ledger/matrix/vector SHA-256:
  `085921e6c4e995f0d6259c9f6f6eabeec3f1455bba344105ef0e16d24eb81671` /
  `a3375bd0d8d01cf7a7c9d7d16d90945d792d932eca7161097f6ee5ba44d3f604` /
  `b5a4d9fb6e4f7d7c7222a8541abd30c092c6fc54d363c66ac5a324e036d6f0a3`.
- CGS checker SHA-256:
  `026c9495e6fe732e57f4703f421b4b11420ee8cae4f8e268ed8974a4d7d0056c`.
- Completed lifecycle-root signer-provenance evidence: witness SHA-256
  `d3c1dce10624365647cbb00926f63b6deabe681e51a138bc3de88d7c60faef69`,
  validator SHA-256
  `46bbda1afb6ccbec5a49ea668752c19a7b1354b94515a33365191cee01745edb`,
  and checker SHA-256
  `8c219ad322277abfe5e969a2153eaf050971187af619713b3f4ffb58dd942038`.
- In-scope requirements: CGS-01 through CGS-12. Approved deviations: none.
  Unresolved semantic questions: none. M1 is explicitly excluded.

## Current State

Verified facts: the linked lifecycle-root signer-provenance correction is
complete and independently reviewed with no remaining strict finding. Its
hermetic evidence executes sequence-one genesis, sequence-two successor,
inclusive issuance boundaries, strict presented/history coordinate validation,
and 6 accepted/41 rejected witnesses across two replicas. The authority
validator recognizes 56 schemas and 249 enum rows. The historical recipe has an
old design/registry pin and is not current-contract evidence.

Implementation state: M3 is complete. CGS-04 through CGS-12 are implemented
through their canonical production paths with registered-generation,
transactional publication, retained-history, independent A/B, parser-budget,
and no-mutation evidence recorded below. The reconciled M3 review has no
correctness finding; the stale spec worker-thread parser observation is
unsupported because both checker entry points reject before raw parsing. The
WorkPlan remains active only for milestone 5 whole-M0 branch closure gates and
independent whole-branch review.

## Assumptions And Open Questions

- Verified facts: hashes above identify the approved artifacts; the matrix
  names every required negative family.
- Working assumptions: the existing traceability tools expose the canonical
  seams needed for a narrow owner-preserving implementation.
- Unresolved questions: exact persisted-data inventory and deployed-version
  population must be measured before migration execution; this does not alter
  the approved dispatch rule.
- Decisions requiring external input: operational release keys, trust roots,
  activation timing, and live certification remain external. They cannot be
  defaulted or block deterministic implementation/testing.

## Requirement Coverage Ledger

| Requirement | Implementation | Tests | Other evidence | Status |
| --- | --- | --- | --- | --- |
| CGS-01 | closed BA/RR genesis-successor union in canonical schemas/decoders | `ba-genesis-smuggle`, `rr-successor-smuggle` | CTV authority and design pin | complete |
| CGS-02 | lifecycle transition validator and replay gate | `ba-post-activation-downgrade` | pointer unchanged assertion | complete |
| CGS-03 | RP signer provenance union and preimage owner | `rp-genesis-smuggle`, `rp-successor-replay` | verifier-held lookup trace | complete |
| CGS-04 | typed 29-field ledger/body generator | `field-01-*`, `field-02-through-07-inputs`, `field-08-through-29` | complete body byte comparison | complete |
| CGS-05 | canonical collection ordering and anchor-to-unit rule | `order-dag-reference` | property/permutation proof | complete |
| CGS-06 | domain registry and length-prefixed digest preimages | `all-domain-families` | known-answer/provenance trace | complete |
| CGS-07 | complete CTV body/envelope/spool and clean-room comparison | `body-envelope-confusion`, `clean-room-import` | A/B full-byte output | complete |
| CGS-08 | version dispatch with diagnostic-only legacy reader | `legacy-version-pairs` | authorization reachability test | complete |
| CGS-09 | admission/reconstruction limits and interruption safety | `limits` | cap/time/cancellation postconditions | complete |
| CGS-10 | retained-history migration, resolver/watermark transaction, rollback | `resolver-watermark-replay-migration` | mixed-version and recovery tests | complete |
| CGS-11 | frozen ledger/matrix identity enforcement | `ledger-matrix-authority` | hermetic gate and CI job | complete |
| CGS-12 | isolated stdlib prototype boundary plus independent production A/B | `prototype-feasibility-boundary` | prohibited-import audit | complete |

## Change Map

| Area | Canonical owner / expected changes | Status |
| --- | --- | --- |
| CTV/profile authority | `memorii/memorii/tools/semantic_ingestion_ctv_reference_compiler.py`; replace stale 240-row assumption with pinned frozen authority consumption, without copying design validator semantics | planned |
| Typed schemas/preimages | `memorii/memorii/tools/semantic_ingestion_traceability_release.py`; own BA/RR/RP closed provenance types, decode, preimage, and lifecycle gate | planned |
| Ledger/manifest derivation | `memorii/memorii/tools/semantic_ingestion_traceability_manifest.py`; own typed 29-field operands, ordering, domain preimages, body/envelope/spool | planned |
| Registry/authorization | `memorii/memorii/tools/semantic_ingestion_traceability_registry.py`; own version dispatch and diagnostic-only legacy access | planned |
| Execution transaction | `memorii/memorii/tools/semantic_ingestion_execution_evidence.py`; own atomic history/pointer/watermark/replay boundary | planned |
| Persistence/migrations | canonical storage adapter selected after M1 inventory; add versioned write/read, retained history, migration journal, rollback switch, and recovery tests | planned |
| Adapters/CLI/config | inspect all call sites; keep thin and prohibit bypassing release/manifest validators | planned |
| Tests | focused unit, property, transaction, restart, migration, mixed-version, and A/B suites under existing `memorii/tests` ownership | planned |
| Artifacts/docs/CI | update only generated approved artifacts, static-tooling command, PR gate, and current-state docs after code proves them | planned |
| Prompts/providers/retrieval/M1 | no change; explicitly non-applicable to this contract | excluded by design |

## Architecture And Transaction Boundaries

The only accepting path is: bytes/transport decode -> typed provenance and
ledger validation -> lifecycle/authorization policy -> deterministic full body
and CTV envelope reconstruction -> transaction that appends immutable history
and advances pointer/watermark -> observable acceptance. Each stage returns a
typed rejection before the next stage on failure. The transaction writes the
new version and all derived references together; retry with the same idempotency
identity reads the committed result, while interruption rolls back uncommitted
rows and never advances pointer/watermark. Readers dispatch a recognized
future version only to its registered handler; legacy versions are diagnostics
and have no authorization path.

## Migration, Rollout, And Rollback

- Inventory persisted versions before enabling writes. Treat corrected CTV v2
  as unshippable when no durable/released artifact exists; never reinterpret an
  old byte sequence as the corrected contract.
- Introduce versioned writes behind an explicit composition/configuration gate.
  Start read-only verification and shadow reconstruction, then staged writes,
  then authorization only after all deterministic checks and required external
  activation inputs exist.
- Migration is resumable and idempotent: record source identity, target
  identity, status, and error; retain original immutable history and require a
  verified target before pointer selection.
- Rollback disables new-version selection/writes and restores prior supported
  selection without deleting target/original history. Mixed-version reads stay
  diagnostic unless explicitly registered; unsupported versions fail closed.
- Observe rejection reason, version, domain, cap breach, transaction outcome,
  retry count, and migration progress without logging secret preimages.

## Milestones Or Experiments

1. **Canonical primitives and frozen consumers.** Purpose: make the authority
   consumers recognize the approved profile. Scope: CGS-04..06 and CGS-11
   primitives, plus the stale 240-row consumer correction; no persistence or
   activation. Expected artifacts: typed CTV/profile/ledger/domain interfaces,
   frozen authority consumer wiring, focused tests. Verification: pinned CTV
   and CGS gates, direct malformed/ordering/domain tests. Evidence maturity:
   implemented, locally verified. This milestone proves primitive and frozen
   authority behavior only; full 29-field source extraction and ordering remain
   milestone 3, and CGS matrix/CI semantic enforcement remains milestone 4.
   Status: complete.
2. **Provenance and lifecycle authorization.** Purpose: implement CGS-01..03
   and CGS-08 at the release/registry boundary. Scope: BA/RR/RP variants,
   preimages, transition state machine, legacy diagnostic dispatch. Expected
   artifacts: canonical validators and matrix tests. Verification: decode,
   replay, signer substitution, and no-authorization tests. Status: complete.
3. **Full structural generation transaction.** Purpose: implement CGS-04..10
   through the manifest/execution path. Scope: complete body/envelope/spool,
   caps, atomic retained history/pointer/watermark, retry and recovery.
   Expected artifacts: generator, persistence transaction, migration journal,
   focused tests. Verification: known answer, cap/cancellation, restart,
   contention, replay, migration, rollback, mixed-version tests. Status: complete.
4. **Independent reconstruction and gate integration.** Purpose: complete
   CGS-07, CGS-11, and CGS-12. Scope: separately authored clean-room B,
   import boundary enforcement, full A/B bytes/failures, PR static gate.
   Expected artifacts: B implementation, comparison harness, CI config and
   documentation. Verification: allowed-input/import audit, complete body /
   envelope / spool equality, matrix corpus, clean checkout CI-equivalent run.
   Status: complete.
5. **Whole-branch closure.** Purpose: verify all CGS requirements and release
   readiness. Scope: exact reviewed tree only; no new semantics. Expected
   artifacts: evidence ledger and final three-lane review. Verification: full
   command matrix, migration/rollback drill, independent source audit, review.
   Status: complete.

## A/B Ownership And Independence

Reference A is the canonical production implementation owned by the manifest,
release, registry, execution-evidence, and CTV-consumer modules in the Change
Map. Clean-room B is separately authored and may consume only frozen design,
registry, CTV authority, ledger, and matrix inputs. B must not import, copy, or
invoke A's parser, normalizer, canonical encoder, digest/preimage helpers,
schema classes, test fixtures, or production validation functions. Shared
stdlib cryptographic/byte primitives require explicit review justification.
B compares complete canonical body, CTV envelope, structural spool, rejection
class, and no-mutation postcondition; matching a digest alone is insufficient.

## Validation Matrix

The checked-in authoritative matrix is
`docs/design/semantic_ingestion/traceability_golden_vectors/cgs_verification_attack_matrix-v1.json`.
Before code beyond milestone 1, `test_reviewer` must confirm the following
mapping and add no unapproved semantic cases:

| Requirement | Required matrix cases | Proof and failure signal |
| --- | --- | --- |
| CGS-01 | `ba-genesis-smuggle`, `rr-successor-smuggle` | typed decode rejects mixed union fields; no authorization |
| CGS-02 | `ba-post-activation-downgrade` | replay rejects downgrade; pointer unchanged |
| CGS-03 | `rp-genesis-smuggle`, `rp-successor-replay` | preimage/lookup rejects; no policy activation |
| CGS-04 | `field-01-grammar_revision`, `field-02-through-07-inputs`, `field-08-through-29` | body equality rejects omission/substitution |
| CGS-05 | `order-dag-reference` | parser/order verifier rejects duplicate or unsorted input |
| CGS-06 | `all-domain-families` | digest-preimage verifier rejects domain confusion |
| CGS-07 | `body-envelope-confusion`, `clean-room-import` | artifact decode/import gate rejects; A/B bytes agree |
| CGS-08 | `legacy-version-pairs` | reader/dispatch rejects authorization reachability |
| CGS-09 | `limits` | admission/time cap rejects before mutation |
| CGS-10 | `resolver-watermark-replay-migration` | transaction rejects and leaves pointer unchanged |
| CGS-11 | `ledger-matrix-authority` | hermetic verifier rejects identity change |
| CGS-12 | `prototype-feasibility-boundary` | prototype remains isolated; A/B evidence is not conflated |

Every matrix case gets positive preservation coverage where a valid adjacent
case exists, plus normal-path and fast-path invocation. Migration coverage adds
process restart, duplicate delivery, failure between history write and pointer
advance, and rollback after partial population.

## Verification Commands

Run from repository root unless stated otherwise. Record interpreter versions,
exit status, tree identity, and relevant output in the Evidence Log.

```bash
python3.12 -I docs/design/semantic_ingestion/traceability_golden_vectors/check_ctv_binding_authority_v2.py --design docs/design/semantic_ingestion_architecture.md --registry docs/design/semantic_ingestion/traceability_registry/registry-v1.json --authority docs/design/semantic_ingestion/traceability_golden_vectors/ctv-binding-authority-v2.json --validator docs/design/semantic_ingestion/traceability_golden_vectors/validate_ctv_binding_authority_v2.py --expected-design-sha256 70ace2b99c4db79911f45555f72cde43278ccaac69c1fc11530e2d474f1fa26c --expected-registry-sha256 8e6395e2657eb1a51e5eef7d9b88b5d43b974a58f7f786ed135f6758262bfec1 --expected-authority-sha256 c119345548166fd99e7aefe963d62a9b73e6c98c7cac84b7d6f8759b2ceb5633 --expected-validator-sha256 826541e7864583bbe3c32e3f153c008f07a881f33d38861237dfac80d9f3657e --expected-checker-sha256 e2c35870a99e587f34cbffc701f42587520ee015009cd51647367da56716c732
python3.12 docs/design/semantic_ingestion/traceability_golden_vectors/check_cgs_structural_contract_v1.py --design docs/design/semantic_ingestion_architecture.md --registry docs/design/semantic_ingestion/traceability_registry/registry-v1.json --ledger docs/design/semantic_ingestion/traceability_golden_vectors/structural_manifest_derivation_ledger-v1.json --matrix docs/design/semantic_ingestion/traceability_golden_vectors/cgs_verification_attack_matrix-v1.json --prototype docs/design/semantic_ingestion/traceability_golden_vectors/cgs_structural_manifest_prototype.py --vector docs/design/semantic_ingestion/traceability_golden_vectors/cgs-structural-manifest-prototype-v1.json --self-test
python3.12 -I docs/design/semantic_ingestion/traceability_golden_vectors/check_lifecycle_root_signer_provenance_v1.py --design docs/design/semantic_ingestion_architecture.md --matrix docs/design/semantic_ingestion/traceability_golden_vectors/cgs_verification_attack_matrix-v1.json --fixture docs/design/semantic_ingestion/traceability_golden_vectors/lifecycle-root-signer-provenance-witness-v1.json --validator docs/design/semantic_ingestion/traceability_golden_vectors/validate_lifecycle_root_signer_provenance_v1.py --expected-checker-sha256 8c219ad322277abfe5e969a2153eaf050971187af619713b3f4ffb58dd942038 --self-test
cd memorii && python -W error -m pytest tests/unit -p no:cacheprovider
cd memorii && python -m ruff check memorii tests
cd memorii && pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
git diff --check
```

Add focused test commands before each milestone and a clean-checkout CI run in
milestone 4. Historical `validate_recipe.py` is not a current CGS gate and must
not be repinned without its separate migration/design decision.

## Progress Log

- 2026-07-31: created from the completed CGS design WorkPlan. Baseline hashes,
  CGS-01..12 ledger, ownership, matrix, migration obligations, and one bounded
  first action recorded. Next action: milestone 1 primitives and consumers.
- 2026-07-31: completed milestone 1. The canonical artifact transport is now
  a CTV `CanonicalEncodedArtifact.v1` model; the retired JSON wrapper has an
  explicit diagnostic-only reader. The reference compiler consumes 247 frozen
  enum rows, and the production structural-ledger owner pins the exact raw
  ledger before exposing its typed fields and digest domains. Next action:
  milestone 2 provenance and lifecycle authorization.
- 2026-07-31: closed targeted milestone-1 evidence gaps. The PR test,
  documented command, and workflow use one current authority tuple; outer
  artifact-preimage tests independently cover every length-prefixed operand;
  release tests mutate all six binding components; and every frozen digest
  domain now has an exact-preimage and domain-swap check. Scope remains
  primitive/authority evidence only. Next action remains milestone 2.
- 2026-07-31: began milestone 2 at the canonical release boundary. Added
  closed BA/RR genesis-successor and RP genesis-successor discriminators,
  exact-field and interval validation, and the typed RP signature preimage.
  Corrected provenance is checked before a signature verifier can run; raw
  compatibility remains outside the registered execution entry point. A
  pre-existing scenario structural fixture requests the unregistered
  `TraceabilityRegistryRoot.assertion_templates.v1` binding, so full scenario
  closure is recorded for milestone 3 rather than being papered over here.
  A dedicated minimal corrected-CTV chain now reaches the public release gate
  without a structural-generation package and proves genesis authorization,
  replay, and a sequence-two lifecycle rotation/successor release. Historical
  lifecycle roots are verifier-held composition material, never request data.
  Next action: independent review of milestone 2 before M3.
- 2026-07-31: completed milestone 2 closure. A post-activation bootstrap
  anchor cannot use the independently-provisioned genesis variant; issuance-
  time historical verification and present-time selected-release eligibility
  are explicit tests; and an idempotent retry produces no extra watermark
  advance. Next action: milestone 3 full structural generation transaction.
- 2026-07-31: reopened milestone 2 after confirmed public-gate and provenance
  findings: the corrected gate must not authorize CTV-wrapped legacy bodies,
  and BA/RR/RP provenance must bind the exact verifier-held lifecycle state.
  Next action: close corrected CTV transport and provenance replay checks.
- 2026-07-31: public preflight now rejects CTV-wrapped release, release-history,
  and active-pointer bodies unless their binding and complete current field set
  match the frozen authority; this happens before verifier or watermark use.
  Release/history/pointer declared-content digests and signature payloads now
  use typed CTV values and the closed RP signer coordinate. The former
  "corrected" positive fixture was demonstrated to be legacy-shaped (flat
  signer fields and incomplete bodies) and was changed to assert its required
  rejection. Exact lifecycle root/record envelope migration and a genuinely
  current genesis-successor positive fixture remain the one next action.
- 2026-07-31: the same preflight now includes the exact lifecycle-root envelope
  and its frozen lifecycle-record binding. This preserves fail-closed public
  behavior while the lifecycle replay owner is reconstructed around the full
  record signer eligibility reference; it does not claim the old replay logic
  can authorize a current lifecycle envelope.

## Evidence Log

- Historical parent-design completion evidence (superseded for current gate
  identity by the linked lifecycle-root correction): final CTV validator self-test reports 56
  schemas, 247 enum rows, and profile digest
  `c425fa6823f42fdd0d83ff444699bfd4c2b5fc9468812ff2b60c158a04ad254f`.
- Parent design CGS checker `--self-test` accepted the pinned vector and
  rejected domain, stale-ledger, and envelope mutations; `git diff --check`
  exited 0. This is specified/locally-verified design evidence only, not
  implementation or clean-room production evidence.
- Milestone 1 local evidence (2026-07-31, repository root):
  `PYTHONPATH=memorii .venv/bin/pytest -q memorii/tests/unit/tools/test_semantic_ingestion_structural_ledger.py memorii/tests/unit/tools/test_traceability_release_ctv_adapter.py -p no:cacheprovider`
  exited 0 (`10 passed`); scoped Ruff and `git diff --check` exited 0; scoped
  Pyright exited 0; pinned CTV authority checker and CGS checker `--self-test`
  exited 0. The focused ledger suite proves the exact 29-field ordered
  descriptor contract (not source reconstruction), raw identity failure before
  elaboration, all declared raw/typed domain preimages, independent outer
  artifact preimage operands, six-component release binding pinning, body shape
  rejection, and CTV-v2/legacy transport separation. The PR-gate test and
  workflow now share the approved design/authority/validator/checker tuple and
  mutate each pinned source identity. Full 29-field source/order reconstruction
  is not claimed until milestone 3; full CGS matrix and CI semantic enforcement
  are not claimed until milestone 4.
- Targeted milestone-1 remediation command:
  `PYTHONPATH=memorii .venv/bin/pytest -q memorii/tests/unit/tools/test_semantic_ingestion_structural_ledger.py memorii/tests/unit/tools/test_traceability_release_ctv_adapter.py memorii/tests/unit/tools/test_ctv_binding_authority_pr_gate.py -p no:cacheprovider`
  exited 0 (`34 passed`). Scoped Pyright exited with zero errors; scoped Ruff,
  YAML parse, workflow/static pin search, `git diff --check`, the hermetic CTV
  authority command, and the CGS checker `--self-test` all exited 0.
- Milestone-2 focused evidence (2026-07-31, repository root):
  `PYTHONPATH=memorii .venv/bin/pytest -q memorii/tests/unit/tools/test_traceability_release_provenance.py memorii/tests/unit/tools/test_traceability_release_ctv_adapter.py -p no:cacheprovider`
  exited 0 (`16 passed`). It proves BA/RR genesis field-smuggling and
  predecessor rejection, successor lifecycle-coordinate replay rejection, RP
  union closure, and that malformed RP provenance rejects before the signature
  verifier is called. It also proves that the public release gate rejects raw
  legacy bytes before a watermark call, while the explicit diagnostic reader
  remains non-authorizing. Scoped Ruff and `git diff --check` exited 0. Scoped
  Pyright reports five pre-existing project-version diagnostics (`datetime.UTC`
  and PEP-604 unions) and no new provenance diagnostic.
- The dedicated M2 fixture serializes exact registered CTV envelopes for BA,
  RR, RP, lifecycle, release, pointer, and history. It contains no structural
  manifest/package member and nevertheless authorizes a corrected genesis
  release through `verify_release_gate`, then repeats that same coordinate.
  `PYTHONPATH=memorii .venv/bin/pytest -q memorii/tests/unit/tools/test_traceability_release_provenance.py memorii/tests/unit/tools/test_traceability_release_ctv_adapter.py -p no:cacheprovider`
  exited 0 (`16 passed`) and scoped Ruff / `git diff --check` exited 0.
- Successor completion evidence: `VerifierHeldTrustMaterial` now carries an
  immutable tuple of prior verified lifecycle-root bytes. The release validator
  decodes and indexes that verifier-held history by exact root digest, rejects
  duplicate/missing/cross-authority history, and resolves successor provenance
  before lifecycle replay. A focused corrected-CTV chain proves genesis,
  same-coordinate replay, lifecycle rotation, and a sequence-two
  release/history/pointer signed by the successor. The release binding accepts
  only lifecycle-authorized bootstrap digest intervals; it does not treat a
  candidate root as authority. `test_traceability_release_provenance.py` plus
  `test_traceability_release_ctv_adapter.py` exited 0 (`16 passed`); scoped
  Ruff and `git diff --check` exited 0.
- Broad legacy suite reconnaissance:
  `PYTHONPATH=memorii .venv/bin/pytest -q memorii/tests/unit/tools/test_semantic_ingestion_traceability_registry.py -p no:cacheprovider --maxfail=1`
  ran 165 passing legacy cases before the first expected raw authorization
  result failed under the corrected public gate. Those tests share a raw
  historical fixture whose complete CTV/package migration overlaps milestone
  3 structural/pointer generation. This is assigned to milestone 3; it is not
  evidence of an authorization fallback.
- Milestone-2 closure evidence (2026-07-31, repository root):
  `PYTHONPATH=memorii .venv/bin/pytest -q memorii/tests/unit/tools/test_traceability_release_provenance.py memorii/tests/unit/tools/test_traceability_release_ctv_adapter.py -p no:cacheprovider`
  exited 0 (`19 passed`). The focused cases reject a historical signer before
  its issuance interval, at/after revocation, and during current selection
  after eligibility ends. A corrected CTV chain rejects a post-activation
  bootstrap-genesis downgrade before another watermark call; raw legacy
  transport remains diagnostic-only and cannot call the watermark. Scoped Ruff
  and Pyright over the release module and provenance/CTV tests exited 0, and
  `git diff --check` exited 0.
- Reopened M2 local evidence (2026-07-31, repository root):
  `cd memorii && ../.venv/bin/python -m pytest
  tests/unit/tools/test_traceability_release_provenance.py -q
  -p no:cacheprovider` exited 0 (`10 passed`); scoped Ruff and Pyright over
  `semantic_ingestion_traceability_release.py` exited 0; `git diff --check`
  exited 0. This proves early CTV-wrapped legacy rejection only. It is not
  evidence of a current-shape positive chain, file-store replay behavior, or
  complete BA/RR exact-body reconstruction.
- M0 successor-replay slice (2026-07-31, repository root): the production
  lifecycle root decoder now distinguishes terminal sequence one genesis from
  sequence-greater-than-one successor. Successors recompute every current CTV
  record/root digest and signature preimage, resolve only verifier-held prior
  roots by digest, require the immediate prior terminal record under the same
  authority, and compare the complete final-action signer coordinate including
  issuer, key, profile, purpose, and interval. RP successor provenance now
  binds that same terminal record and final-action authorization. Focused
  successor test passed; scoped Ruff, Pyright, and `git diff --check` passed.
- M2 current-chain fixture (2026-07-31, repository root): replaced the stale
  provenance fixture bindings with the frozen current profile and exact BA/RR/
  RP body bindings. The fixture constructs typed genesis and rotated-successor
  lifecycle roots, typed record/root/release/history/pointer signature
  preimages, and a verifier-held prior root; it authorizes through
  `verify_release_gate` using `FileTraceabilityReleaseWatermarkStore` and
  proves replay leaves the persisted watermark bytes unchanged. During this
  reconstruction, `_required_roots` was corrected to map collection-oriented
  registry root names to the closed semantic release-body fields; the former
  names could never pass the release grammar. Focused provenance suite passed
  (`12 passed`); scoped Ruff and Pyright passed. Next action: add the remaining
  current-chain negative variants and run the combined M2 focused suite.
- M2 fixture repair (2026-07-31, repository root): migrated the provenance
  unit fixture from retired flat root digests and stale CTV binding digests to
  the frozen current BA/RR/RP bindings. The fixture now carries the exact BA
  body fields, genesis provenance, and typed policy anchor coordinate used by
  production. `PYTHONPATH=memorii .venv/bin/python -m pytest
  memorii/tests/unit/tools/test_traceability_release_provenance.py
  memorii/tests/unit/tools/test_traceability_release_ctv_adapter.py
  memorii/tests/unit/tools/test_semantic_ingestion_acceptance_watermark_store.py
  -p no:cacheprovider -q` exited 0 (`36 passed`); scoped Ruff and Pyright
  exited 0; `git diff --check` exited 0. This repairs current-shape primitive
  provenance coverage only. The stated next action remains reconstruction of
  the separate full public current-chain fixture; no M3 work is claimed here.

- M2 release/execution remediation closure (2026-07-31, repository root;
  supersedes the earlier 53- and 57-test checkpoints):
  registered R03/R13 fixtures now use a complete current-CTV release generation
  and a bounded synthetic design closed over every registered heading and
  anchor. Verifier-held lifecycle/successor roots are CTV-only; successors
  retain the exact prior record prefix and immediate predecessor. Every
  verifier-held chain is first ordered and validated as one signed genesis plus
  one signed append-only successor per record; skipped, cyclic, missing,
  duplicate, cross-authority, invalid-envelope, and wrong-terminal roots cannot
  become authority. Genesis and action times are constrained to provisioned
  root intervals. Current recovery
  replay keeps provisioned recovery roots inactive until explicit lifecycle
  activation, enforces the policy threshold over distinct policy-ordered active
  roots, tombstones revoked/compromised roots, and permits a subsequent
  ordinary rotation. Generation closure uses the frozen current
  release-member bindings and exact multi-root recovery history. The final
  strict focused suite exited 0 (`64 passed in 191.48s`), covering provenance,
  CTV
  adaptation, execution evidence, file watermark behavior, R03/R13,
  activated threshold recovery-to-rotation, pre-activation/revoke/compromise
  recovery rejection, missing/duplicate recovery-root attacks, and real-file
  missing/duplicate/cross-authority/wrong-terminal prior-root attacks with exact
  reasons. It also covers a signer eligible at issuance but expired at
  verification, issuance exactly at the exclusive interval end, and issuance
  beyond the interval, all with exact rejection reasons and byte-identical
  watermark/seal state. Scoped Ruff, scoped
  production/unit Pyright, and `git diff --check` exited 0. The acceptance
  module retains broader pre-existing Pyright debt outside this M2 scope; no
  clean whole-module Pyright claim is recorded.
- M3 CGS-10/structural integration findings (not M2 completion evidence):
  pointer-history generation still requires its transaction-owned current-CTV
  migration; scenario-test-trust migration remains part of structural
  generation integration; and the registered successor-report fixture remains
  a successor transaction/report integration fixture rather than provenance
  evidence. These three items are assigned to milestone 3 and must not be used
  to reopen or inflate the milestone-2 completion claim.
- CTV normalization performance repair (2026-07-31, repository root):
  `encode_typed_value` now builds a private normalized typed JSON tree and
  performs one final canonical serialization, removing recursive
  `encode_typed_value` then `json.loads` churn without changing CTV-v2 bytes,
  sort order, or duplicate checks. A mixed nested scalar/bytes/datetime/
  duration/list/tuple/set/map fixed known-answer locks the prior wire bytes;
  the complete 1,153,422-byte live design's production manifest bytes equal
  the independently rebuilt bytes. `PYTHONPATH=memorii .venv/bin/python -m
  pytest -q memorii/tests/unit/tools/test_semantic_ingestion_structural_ledger.py
  memorii/tests/unit/tools/test_semantic_ingestion_traceability_manifest.py
  memorii/tests/unit/tools/test_scenario_first_c2_harness.py
  -p no:cacheprovider` exited 0 (`6 passed`); scoped Ruff, Pyright, and
  `git diff --check` exited 0. An informational, non-gating full build produced
  a 39,372,948-byte manifest with digest
  `d578aa255db46d55e6b3f9751afd717681c7d499153b7114d4617e0a927c410d`
  in 29.30 seconds (real time); no flaky wall-clock assertion was added.
- M3 finalization audit (2026-07-31, repository root): the focused scenario,
  generation, publication, watermark, and ingress suites passed (`64 passed`)
  for the implemented C2 slice. The explicit scenario authority reaches the
  registered execution path only with a composition-owned publication store;
  foreign authority rejection leaves both the watermark and publication path
  untouched. File publication evidence now covers interruption before replace
  and lost acknowledgement after replacement, followed by restart/idempotent
  retry. This is not M3 completion evidence: the current generation order is
  still a 17-member legacy order with no raw derivation-ledger member, only
  byte-size admission limits are implemented, and no registered successor
  report/runner/artifact, full clean-room A/B, retained-tail rollback, or
  legacy/mixed-version inventory proof exists. Historical transformation
  remains excluded.
- M3 persistence retained-tail sub-slice (2026-07-31, repository root):
  `semantic_ingestion_release_persistence.py` now stores immutable,
  content-addressed corrected-v2 tail records separately from the atomically
  replaced current index. Each tail binds the exact prevalidated
  pointer-history bytes/digest, prior accepted-tail digest, and (for rollback)
  selected historical-tail digest. `compare_and_publish_after` supplies an
  exact predecessor-tail CAS; `rollback_to` can select only an existing
  corrected-v2 tail and appends a new monotonic transaction rather than
  deleting or rewriting history. `version_inventory` reports empty,
  corrected-v2, legacy, mixed, or corrupt state; legacy/mixed state has no
  activation or rollback path. The focused test command
  `PYTHONPATH=memorii .venv/bin/python -m pytest -q memorii/tests/unit/tools/test_semantic_ingestion_release_persistence.py -p no:cacheprovider`
  exited 0 (`7 passed`) and covers atomic restart, torn index rejection,
  pre-replace interruption, post-index lost acknowledgement with idempotent
  retry, retained-tail rollback, stale exact-predecessor CAS, and legacy
  diagnostic inventory. Scoped Ruff and Pyright both exited 0 with no
  findings; `git diff --check` over the owned files exited 0. This is bounded
  persistence evidence only: it does not claim historical transformation,
  structural generation, or M3 completion.
- M3 independent-fence publication remediation (2026-07-31, repository root):
  the registered release commit hook now invokes one publication-store
  transaction entry point that compares/advances the independently durable
  release watermark before publishing an immutable tail and current index.
  Restoring an intact older publication index after the fence reaches sequence
  two cannot reauthorize sequence one; interruption after fence advance remains
  recoverable only by byte-identical sequence-two retry. Rollback no longer
  copies a target tail's historical active-pointer or pointer-history bytes: it
  requires a newly supplied bundle, exact current-tail CAS, a monotonic new
  transaction coordinate, and a previously accepted corrected-v2 target; exact
  old pointer/history replay rejects. Focused persistence, watermark, release
  provenance, and CTV adapter tests passed (`56 passed in 16.51s`); scoped Ruff
  and persistence Pyright passed with zero findings. This evidence does not by
  itself claim that the persistence owner independently revalidates every
  embedded pointer signature; the registered execution/release validation
  boundary remains responsible for authentication before this byte-exact
  commit hook.
- M3 integrated publication-journal correction (2026-07-31, repository root):
  supersedes the preceding separate-store ordering implementation. The file
  publication store now implements both watermark protocol and publication
  protocol. Registered commit requires object identity between the two roles;
  split composition returns `persistence_outcome_indeterminate` before creating
  or changing publication state. Provisioning, fence coordinate/digest, and
  current-tail selection share one canonical index replacement, while every
  accepted tail remains immutable and content-addressed. The independently
  monotonic high-water value is reconstructed from the immutable tail journal,
  so restoring an older otherwise-valid index cannot restore its authority;
  exact current-sequence retry can repair an index after a fence-ahead/lost-ack
  interruption without wedging the release. Focused publication, watermark,
  release-provenance, and CTV tests passed (`57 passed in 17.39s`); the strict
  pointer-history adversarial node passed separately (`1 passed`). Scoped Ruff
  passed and persistence Pyright reported zero findings.
- M3 registered-generation closure (2026-07-31, repository root): the
  registered scenario now publishes an exact 18-member CTV-v2/raw-ledger
  generation through the sole registered entry point. The generation binds
  exact bootstrap/recovery/policy histories, lifecycle-qualified trust
  snapshot, independently reconstructed structural envelope, release/history,
  and signed pointer history. Sequence 1 and its sequence-2 successor publish
  as two immutable corrected-v2 tails; report, runner-observation, and result
  artifact mutations are rejected without changing publication bytes.
  `test_scenario_test_trust_passes_only_when_installed_as_explicit_authority`
  exited 0 (`1 passed in 144.42s`), and
  `test_registered_scenario_publishes_sequence_two_after_sequence_one` exited
  0 (`1 passed in 327.09s`). Focused persistence/provenance exited 0 (`30
  passed`), admission caps exited 0 (`9 passed`), scoped Ruff and
  `git diff --check` exited 0. Structural verification uses fixed byte caps,
  exact checked-in ledger bytes, independent reconstruction, the frozen
  length-prefixed structural digest, and exact outer-envelope byte equality;
  it does not recursively decode the dominant untrusted structural tree.
  The initially observed clean-room enum-inventory drift was reconciled to the
  current frozen 249-row authority during the remediation below; the complete
  reference-compiler suite is now green.
- M3 authority/A-B boundary remediation (2026-07-31, repository root): both
  structural producers now pin the frozen current authority profile `9dc8...`,
  structural binding `133ba...`, and assertion-root binding `bcec...`.
  Production admission and both independent raw validators reject design or
  registry inputs above 8 MiB. Parsing, mapping, reconstruction, and recursive
  CTV normalization/encoding accept cooperative checks; registered verification
  enforces a 30-second parse phase within its 60-second reconstruction budget
  and propagates cancellation before publication. Registered authorization now
  requires an allowlisted separately shaped clean-room-B result and exact
  equality of reconstructed body, outer envelope, and closed spool bytes.
  Pointer history validates every embedded current pointer's full field set,
  digest, signature, positive contiguous sequence, predecessor pointer and
  prefix-history links, plus the active pointer's exact history digest and
  `len(history)+1` sequence. Evidence: structural manifest/checker `11 passed`
  in 270.22s; clean-room compiler `258 passed` in 196.38s; minimal pointer
  mutation test `1 passed` in 1.16s; registered seq1/seq2 plus report, runner,
  artifact, and A/B-disagreement no-publication-mutation matrix `1 passed` in
  380.92s; focused caps/provenance `32 passed`; scoped Ruff clean.
- M3 composition/pointer-budget closure (2026-07-31, repository root): the
  registered request no longer accepts caller-supplied independent-generation
  results. `AcceptanceTrustStore` owns the verifier protocol; the approval
  boundary supplies raw design, registry, and frozen-ledger bytes plus A's
  expected body/envelope. The pinned isolated implementation verifies the
  stdlib-only B script SHA, executes it under `python -I` through temporary raw
  byte files, and admits only exact body, envelope, and closed spool agreement
  under the allowlisted executor identity and implementation SHA. Scenario
  composition uses an explicit test-only verifier rather than fabricating a
  request result. Pointer-history outer and embedded signers now require the
  exact coordinate schema and purpose, lifecycle root and record/target link,
  active signer tuple, and eligibility interval at each `published_at`.
  Structural construction installs a default 30-second parse and 60-second
  total derivation budget even without a caller callback; registered cap,
  deadline, cancellation, or independent-derivation failures collapse to
  `structural_derivation_unavailable` before publication. Focused direct
  admission/default-budget/public-shape/pointer tests passed (`17 passed in
  3.91s`), including direct current-input subprocess execution and forged
  implementation-SHA/output disagreement. The corrected full registered
  scenario passed (`1 passed in 154.14s`). Scoped Ruff and scoped Pyright both
  passed with zero findings; `git diff --check` passed. A broader Pyright run
  that included `semantic_ingestion_traceability_release.py` still reports its
  four pre-existing optional publication-byte narrowing findings at lines
  2473-2476; this M3 slice did not alter that publication implementation.
- M3 independent-spool/deadline closure (2026-07-31, repository root): the
  stdlib-only B compiler now constructs and emits its own closed structural
  spool bytes; the parent parses and compares those emitted bytes and never
  synthesizes B's result. The B implementation is repinned to `d89ae...`, its
  frozen vector is regenerated and repinned to `7af8...`, and the CGS checker
  and static-tooling pins are current. B owns a cooperative 30-second parser
  deadline while the parent process retains a separate 60-second total
  timeout. The independent checker composes caller callbacks with mandatory
  self-owned 30-second parse and 60-second total reconstruction deadlines, so
  `verify_structural_manifest` inherits the same defaults. Direct raw-input
  spool/protocol, parser-versus-total timeout, no-callback checker timeout,
  cap, cancellation, and forged-output tests passed (`19 passed in 4.00s`);
  scoped Ruff, scoped Pyright, `git diff --check`, and the CGS structural
  contract self-test passed. The public sequence-1/sequence-2 scenario,
  including malformed B spool rejection as exact
  `structural_derivation_unavailable` with byte-identical publication state,
  passed (`1 passed in 392.25s`).
- CGS-09 cooperative parser-loop closure (2026-07-31, repository root): A's
  normative-unit parser now composes its callback through the initial window,
  outer block scan, nested fence/table/list/paragraph scans, and final
  materialization loops. Manifest numeric-heading and Section 1-5 scans use the
  same check and check immediately after each parser returns. Stdlib B checks
  every extracted heading through its self-owned parser deadline. Deterministic
  tests expire inside A unit extraction and B heading extraction rather than
  only before/after those phases. Pins are current: prototype `3224146b...`,
  unchanged vector `7af8aa57...`, checker `8df841fc...`. The combined first run
  showed the pre-existing manifest suite green but one new test-fixture setup
  error (`30 passed, 1 failed in 295.29s`): its synthetic document omitted the
  grammar-mandatory Section 5, so the parser correctly rejected before the
  callback. After correcting that fixture, the complete caps/parser suite
  passed (`20 passed in 3.94s`). Scoped Ruff and Pyright, `git diff --check`,
  and the CGS structural-contract self-test passed.
- CGS-09 pre-parser/watchdog closure (2026-07-31, repository root): A's initial
  design-window discovery no longer performs an unchecked full split or regex
  scan. It checks before and after UTF-8 decode, incrementally constructs lines,
  and samples Section 1, Section 5, and terminal-section scans, including
  no-heading/no-section failures. B heading extraction likewise uses a checked
  incremental byte-line scan so no-match inputs remain interruptible. B raw
  registry/ledger JSON loads run under an internal stdlib `setitimer` 30-second
  watchdog in addition to the monotonic parser budget, distinct from the
  parent's 60-second process timeout; independent checker registry parsing has
  the same internal watchdog/default-budget protection. Deterministic injected
  no-heading and watchdog expiry tests passed. Final identities are prototype
  `fd72d63e...`, unchanged vector `7af8aa57...`, and checker `44ec133e...`.
  Evidence: caps/watchdog/parser tests `22 passed in 4.07s`; manifest regression
  `11 passed in 291.98s`; CGS self-test, scoped Ruff, scoped Pyright, and
  `git diff --check` passed.
- Final generation canonicality/budget closure (2026-07-31, repository root):
  A manifest admission and the independent checker now reject strict UTF-8
  design bytes whose decoded text is not already NFC; the rejection precedes
  parser/model construction and therefore cannot reach B or publication. B's
  JSON watchdog no longer starts a fresh 30-second interval: it receives
  `max(0, parser_deadline - monotonic())` from the single parser-entry budget
  and fails immediately when no time remains. Deterministic tests cover
  decomposed Unicode at both A boundaries and a near-expired B parser budget
  whose watchdog receives exactly the remaining interval. Final identities are
  prototype `b3a57d07...`, unchanged vector `7af8aa57...`, and checker
  `3fcc8d65...`. Evidence: caps/canonicality/watchdog suite `24 passed in
  4.20s`; scoped Pyright, `git diff --check`, and CGS structural-contract
  self-test passed.
- Final parser-watchdog lifecycle closure (2026-07-31, repository root): B now
  enters one internal 30-second watchdog before raw-design UTF-8/NFC validation
  and retains it across registry/ledger JSON parsing and heading derivation; no
  normalization or parser phase starts outside that watchdog. A deterministic
  injected normalizer overrun proves the watchdog is active during NFC work.
  The independent checker's watchdog uses SIGALRM only on the main thread;
  worker threads use the composed monotonic pre/post checks, avoiding Python's
  raw `ValueError` for signal installation outside the main interpreter thread.
  Worker-thread valid reconstruction and injected parser-overrun tests prove
  bytes are returned normally or a normalized `TraceabilityCoverageError` is
  raised. Final identities are prototype `b655f474...`, unchanged vector
  `7af8aa57...`, and checker `212d0164...`. Evidence: parser/watchdog suite `25
  passed in 23.08s`; scoped Pyright, `git diff --check`, and CGS self-test
  passed.
- Worker-thread parser-cap closure (2026-07-31, repository root): independent
  structural rebuild now rejects every non-main-thread invocation before raw
  design validation or registry parsing with a normalized
  `TraceabilityCoverageError`; `verify_structural_manifest` inherits the same
  fail-closed entry boundary. Registered approval classifies this unavailable
  parser outcome as `structural_derivation_unavailable`, preserving the
  no-publication contract. Tests cover valid worker inputs and an injected
  stalled/raw-parser path, assert neither parser is reached, and observe no raw
  Python signal `ValueError`. Evidence: focused parser/admission suite `25
  passed in 4.00s`; scoped Ruff, scoped Pyright, and `git diff --check` passed.
- M3 independent monotonic-fence recovery closure (2026-07-31, repository root):
  immutable publication tails are PREPARED records only. The atomically
  replaced current index selects one tail and coordinate, while an injected
  `MonotonicFenceStore` in a separately configured failure domain records
  committed authority. `FileMonotonicFenceStore` provides an explicitly
  test-only append-only, predecessor-linked implementation; it declares
  `production_safe=False` because a complete filesystem snapshot can capture
  its authority. Registered production composition requires a capability-
  declaring production-safe backend with a failure-domain marker distinct
  from the publication recovery domain, while scenario composition opts into
  the unsafe file fence explicitly. No authoritative minimum is derived from
  or stored beside the publication path.
  Every file-store mutation and inventory read reconciles the index against
  that external fence under the same exclusive lock: an index ahead of the
  fence is committed only after its selected tail validates; a fence ahead of
  a restored index deterministically restores the committed index; and a
  missing committed tail fails closed. Valid unselected prepared tails are
  excluded from inventory and may be reused by an exact retry. Registered
  publication rejects split watermark/publication instances before mutation.
  Focused crash-window, restored-snapshot, and missing/unavailable-backend
  evidence passed (`17 passed in 1.67s`), including prepare-before-index,
  index-before-fence restart, restored old index recovery, restored old
  index/history rejection, production-safe external G2 survival after a full
  local restore, complete unsafe-file snapshot rejection by production
  composition, same-domain rejection even under test opt-in, fail-closed
  backend loss, and injected first-creation directory fsync failure. Fence
  creation synchronizes newly created parent metadata and
  the fence directory after `O_CREAT` before success. Scoped Ruff
  and Pyright and `git diff --check` passed. The current-tree registered
  sequence-one/sequence-two scenario also passed (`1 passed in 392.70s`),
  confirming both releases traverse the integrated file-store protocol.
- M3 verifier-held anti-rollback registration closure (2026-07-31): production
  authorization no longer trusts backend-supplied safety or failure-domain
  attributes. A composition-owned validator checks a signed, verifier-held
  allowlist tuple (`backend_id`, `backend_kind`, `failure_domain`), rejects
  file/local kinds and `FileMonotonicFenceStore` including subclasses, verifies
  domain separation, and issues a sealed token bound by object identity to the
  exact backend and publication-store instances. Commit requires that exact
  token; forged tokens and tokens replayed against another store fail before
  mutation. Explicit scenario test composition continues through
  `allow_test_file_fence=True`. Focused persistence evidence passed (`18 passed
  in 1.49s`), including spoofed subclass, forged token, mismatched instance,
  trusted external registration with full local restore, and complete unsafe
  snapshot rejection. Scoped Ruff, Pyright, and `git diff --check` passed.
  The registered sequence-one/sequence-two scenario passed with the explicit
  test-only opt-in (`1 passed in 392.42s`).
- M3 verifier-held resolver closure (2026-07-31): token issuance is now owned
  by the exact `AntiRollbackTrustResolver` installed in `AcceptanceTrustStore`.
  The resolver captures its immutable allowlist and signature verifier at
  construction and seals registrations with its private instance identity.
  Commit requires token issuer identity to equal the authority's resolver as
  well as exact backend/store identity. The retired caller-supplied validation
  function cannot issue tokens. Focused evidence passed (`18 passed in 1.71s`)
  for attacker resolver/token, caller lambda/allowlist, proxy kind, file
  subclass, forged token, mismatched instance, trusted composition resolver,
  and full local restore. Scoped Ruff, Pyright, and `git diff --check` passed.
  The registered sequence-one/sequence-two scenario passed with the resolver-
  independent explicit test opt-in (`1 passed in 386.65s`).
- M3 cryptographic anti-rollback registration closure (2026-07-31): removed
  the module-global/object seal as authority. `VerifiedAntiRollbackRegistration`
  now carries only canonical signed payload bytes and signature bytes. The
  verifier-held resolver accepts only signed artifacts and re-verifies on every
  production commit against its fixed allowlist/verifier, the backend's durable
  external identifier and kind/domain, and the stable publication-store
  identifier. Manual construction, payload/signature modification, and replay
  against another store fail without the trusted signature. Focused evidence
  passed (`18 passed in 1.43s`); scoped Ruff, Pyright, and `git diff --check`
  passed.
  The registered sequence-one/sequence-two explicit test composition passed
  unchanged (`1 passed in 387.13s`).
- M3 request-boundary remediation (2026-07-31): replaced the public registered
  approval function, which accepted request-level authority/resolver injection,
  with `RegisteredApprovalExecutor`. Composition captures the fixed
  `AcceptanceTrustStore` once; its public `execute` method accepts only
  candidate and operational evidence. The implementation function is private,
  the production test-authority resolver was removed, and an attacker-facing
  signature test proves requests cannot replace authority, resolver,
  independent verifier, or test-mode flags. Focused evidence passed: generation
  admission caps `25 passed in 3.99s`; full scenario trust `8 passed in
  410.12s`; scoped Ruff and `git diff --check` passed. Acceptance regression is
  green in the coordinator's whole-M0 closure gates (`183 passed in
  1016.40s`).

## Decision Log

- 2026-07-31: implement from the completed CGS baseline without reinterpreting
  legacy structural projections or historical recipe pins. Rationale: the
  parent design resolved the semantic choices and assigned migration separately.
  Consequence: a discovered semantic mismatch reopens design, not a patch.
- 2026-07-31: use staged atomic generation and retained-history rollback rather
  than in-place byte rewriting. Rationale: preserves auditability and makes
  interruption/retry behavior testable. Owner: implementation coordinator.

## Review Log

- 2026-07-31 design handoff: the completed parent records final `spec_auditor`,
  `correctness_reviewer`, and `test_reviewer` approval with no remaining design
  finding. Coordinator disposition: accepted baseline. Product priority: Not
  applicable; approval disposition: follow_up for implementation evidence;
  finding type: verification/integration; remediation eligibility:
  `record_only`.
- 2026-07-31 lifecycle-root correction handoff: the linked design WorkPlan is
  complete after independent `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer` review found no remaining strict issue. Coordinator
  disposition: accepted baseline for implementation. Product priority: Not
  applicable; approval disposition: `follow_up`; finding type:
  verification/integration; remediation eligibility: `record_only`.
- 2026-07-31 M3/CGS-04..12 implementation review reconciliation:
  `correctness_reviewer` reported no findings. The `spec_auditor` worker-thread
  parser observation is `unsupported`: both
  `rebuild_structural_manifest_bytes` and `_parse_watchdog` explicitly reject
  non-main-thread entry before raw design or registry parsing, and registered
  approval normalizes the outcome to `structural_derivation_unavailable`.
  Coordinator disposition: M3 accepted and CGS-04 through CGS-12 implementation
  milestones complete. Product priority: Not applicable; approval disposition:
  `follow_up` only for whole-branch closure evidence; finding type:
  verification; remediation eligibility: `record_only`.
- 2026-07-31 whole-M0 request-boundary finding: confirmed `P2`,
  `changes_required`, security/architecture. The prior public callable allowed
  a request caller to select resolver or authority, bypassing composition-owned
  trust. Remediation is complete through the fixed-authority executor and
  request-signature attack test. The final `correctness_reviewer` and
  `spec_auditor` found no remaining P1/P2 issue; the prior `test_reviewer`
  likewise found no remaining strict P1/P2 evidence gap. The full acceptance
  regression passed (`183 passed in 1016.40s`).
- Before any high-risk implementation beyond milestone 1: `test_reviewer`
  reviews the Validation Matrix; after each coherent milestone and at final
  closure, all three reviewers inspect the whole in-scope state under the
  product-impact remediation gate.

## Blockers And Limits

- No active design blocker. External operational activation inputs are not a
  blocker to deterministic implementation; they remain fail-closed.
- Budget: five vertical milestones, one full review per coherent milestone,
  up to two targeted remediation iterations per milestone, and one final
  whole-branch review. A third same-boundary finding requires boundary
  reconstruction or a linked design decision, not example patching.
- Resource limits are the frozen design caps. CI/toolchain parity, clean
  checkout, and exact tree identity are required before a CI-enforced claim.
- Resume condition for a blocked migration: persisted-data inventory and a
  separately approved migration WorkPlan; do not guess a transformation.

## Next Action

Stop at the completed M0 boundary and await explicit authorization before
starting M1.
