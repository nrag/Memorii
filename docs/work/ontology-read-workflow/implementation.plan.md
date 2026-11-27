# Implement catalog inspection and recall diagnosis

- Work ID: ontology-read-workflow
- Work type: implementation
- Delivery fidelity: Level 2, for manual testing with real local host bindings, ordinary failures and scope protection
- Status: active (v8 acceptance and PR verification)
- Coordinator: main Codex task
- Created: 2026-11-27
- Last updated: 2026-11-27
- Parent WorkPlan: [approved read workflow design](../learned-ontology/design-catalog-inspection.plan.md)
- Related WorkPlans: [prior recall diagnosis design](../learned-ontology/design-recall-diagnosis.plan.md), [earlier ontology implementation](../learned-ontology/implementation.plan.md)
- Canonical inputs: `docs/design/learned_ontology.md` Sections 6, 12 and 13, SHA-256 `66daeb911884d4f3cf9a5ffb70115040b6a226bd00249a63dcd73281a65ff93a`; reviewed code baseline `d62a3abd51e4a80e5acef157af236a6ccfcdab1b` on `codex/durable-delivery-implementation`
- Expected outputs: one runnable local inspect → clarify → recall workflow, protected tests, and implementation evidence in this plan

## Objective and Completion Contract

An authenticated host can inspect the active relation definition, clarify an
ambiguous match, and retrieve a current authorized fact or a typed diagnosis.
The installed default workflow runs through both the packaged bridge and the
generic authenticated source root from reopened, pre-provisioned storage with
no model configuration, API key, network, write-tool authorization, or turn
capture. This WorkPlan owns one bounded vertical milestone with ordered
checkpoints. Neither port is a separately delivered milestone.

Close only when all four requirements have production callers and the required
evidence below, the manual trial passes for both work and home, applicable
gates run at the candidate revision, and focused independent review leaves
`remaining_validated_p1_p2: []` with no required evidence or conformance
findings. Use the existing authorized startup path. Record initialization
rejection separately from typed results on an already composed read port.

## Scope, Sources and Invariants

Use the repository source precedence: `memorii_spec.md`,
`memorii_storage_details.md`, `event_model.md`, `docs/IMPLEMENTATION_RULES.md`,
then the frozen ontology design and its base catalog and installed addendum,
plus the scoped context, semantic temporal retrieval and semantic forgetting
contracts. The frozen design is normative; acceptance examples are witnesses.
No approved deviations or open product decisions are recorded.

Scope is current catalog-bound semantic recall and relation inspection. Seed
and default packages have inspection projections; the installed manual path
uses the default. Exact recall for a learned catalog still needs the verified
closure in Section 12. Unproved early overlays are unavailable; learned
description inspection is deferred. No unscoped search, subject name
resolution, new agent tool registration, model/prompt changes, learning,
activation or replay changes, persisted format migration, or legacy reader
redesign. Packaging and compatibility breadth for production rollout,
exhaustive adversarial matrices and operational certification remain Level 3.

## Current State and Baseline

**4/4 requirements implemented. 0/1 milestone closed.** The managed-host
workflow and local Package Smoke passed on the corrected candidate.
Remaining verification and gate evidence are tracked below. The prior
review froze design bytes at code base `9d661a3b`. Initial planning inspected
`7c6a3a94a135ffc75dec9761595b337c0f4b7de5`, which advances new partitions
to raw payload storage v8. The review baseline adds publication recovery and
quarantine checks in `StorageAdministrationService.partition()` and its
tests. The design hash and both mapped host seams are unchanged. Use the
managed SQLite generation guard in addition to the snapshot fence regression.
No storage migration is proposed.

Before planning, the working tree already held the approved canonical design
edit, two untracked design WorkPlans under `docs/work/learned-ontology/`, and
the untracked `docs/work/virtualemployee-integration/` directory. This plan is
the only new change owned here. A concurrent diff to
`memorii/tests/integration/test_runtime_source_authority.py` covers runtime
source revocation across restore and is outside this plan and its evidence.
Preserve these artifacts and reconcile ownership before implementation
commits. The code baseline does not select a future publication branch.

## Requirement Coverage Ledger

Reconstructed from the two public contracts and the complete serving path.
These requirements carry the underlying ORD-01 through ORD-04 obligations
from the earlier recall design, including the mandatory protected reader
eligibility and release safeguards.

| Requirement | Implementation obligation | Strongest planned evidence | Status |
| --- | --- | --- | --- |
| OCI-01 | Inspect the exact selected package by strict ID or entire normalized name. Return the complete visible descriptor matches with typed endpoints, aliases and read behavior. Preserve ambiguity, seed type authority and unavailable on incomplete projection. | Typed serialization, full 3/56 inventory and exact normalization tests, both factory lookups. | Implemented. Focused catalog and both host inspection checks passed. |
| OCI-02 | Perform inspection, clarification and current diagnosis without credentials through both real hosts. Compare the optional expected selected version before membership/facts in diagnosis. | Installed work and household flows after reopen; same-store seed-to-default install CAS; same version with changed fact. | Implemented. Work and home flows and the same-store stale-version guard passed. Historical and same-version changed-fact witnesses remain open. |
| OCI-03 | Authorize both at entry and release. Verify exact catalog/version/runtime, historical fact authority, current temporal eligibility and suppression, with scoped status precedence. | Scope/role and read-history regressions, barrier controlled selection and revocation, both reader carriers/directions and native suppression window. | Implemented. Retained provenance, late host authorization, live suppression, and the SQLite selection and durable revocation fence passed. Remaining carrier and scope witnesses are open. |
| OCI-04 | Pure request-time path. Inspection does not query facts; neither call writes state, calls a model or affects learning. | Real-root before/after bytes and dispatch tripwires for success, denial, failure and retry. | Implemented. Both host paths preserved the read snapshot with network, model and legacy writer-route tripwires enabled. |

## Production Entrypoint Bindings

The `read_workflow_mapper` read-only preflight and coordinator review used
the live baseline. No product writer was delegated in this planning turn.
`git grep -n -E '(\.read_structured_facts\(|read_structured_facts"|locate_selected\(|inspect_catalog_relation|diagnose_structured_recall)' HEAD -- memorii/memorii`
found five static legacy reader calls plus one dynamic bridge dispatch, six
existing selected-locator calls, and zero new port implementations or callers.
The verified generic factory is externally callable and exercised by tests;
it has no internal production caller. Prove that external entry path directly
without introducing a test-only intermediary. The unrelated
`production_capture.py:212` builder call supplies no read binding.
The table records the intended call chain.

| Trigger/root | Current seam → intended binding | Proof required |
| --- | --- | --- |
| Packaged adapter | Existing entrypoints in `memorii/pyproject.toml` → `integrations/hermes_factory.py:422` → `MemoriiHermesMemoryProvider`. Add direct methods on the bridge and exact read callbacks in `hermes_runtime_binding.py`; the factory passes the closed request and freshly server-issued `AuthenticatedHostIngress`. | Named actual calls on the reopened bridge, no delegation through `HermesCompletedTurnRuntime` or its structured write-tool resolver. |
| Generic authenticated adapter | `hermes_factory.py:427` → `build_authenticated_source_runtime` → `AuthenticatedSourceRuntime` in `integrations/authenticated_source.py`. Install the read binding independently of the existing callback through completed turns. Other consumers without a read binding fail closed. | Named actual generic factory calls with separate host ingress; omit read binding and verify unavailable, omit configured read opt-in on a composed port and verify denial. |
| Shared core authorization and selection | Both callbacks call `ProviderMemoryService.inspect_catalog_relation` or `diagnose_structured_recall`. Pure `_resolve_ingress` → trusted installation/account/agent/session and request-local scoped handle → `MemoryPlaneService.read_snapshot_linearized` → current grant pairs and `PackageIndexedCatalogBundleLocator.locate_selected` from those records. Use `core/scoped_context/authority.py` for scoped grant resolve/release; invalidate the handle on return/abort. | Nonzero production callers at both service methods. Verify one authority-bound snapshot per call, release even for empty/ambiguous outcomes, and no write-side preflight, nested snapshot or selection fallback. |
| Inspection and exact recall | Inspection uses complete selected declaration projection only. Diagnosis compares expected version digest, checks predicate/read capability and calls the common protected reader on the same snapshot. Reuse scoped provenance/history verification, lifecycle eligibility and the injected storage administration view at final serving. | Method probes confirm no fact reader from inspection; recall source/endpoint suppression and temporal eligibility validated in both read carriers and directions. |

Persisted grants are references used by the trusted operator's explicit
read configuration, never client authority. Existing grant publication
remains with the authorized setup owners. Use startup setup state only as an
input to the test and account for it separately. A write-shaped grant, a
historical binding and an expected catalog digest each serve distinct roles.
The old generic callback uses a fixed session label. Use actual verified
session binding on both new paths. The verified factory owns a typed
read-only opt-in input in trusted host configuration. Bind it to verified
installation and storage root, signed-in account and agent, exact semantic
rows, and the per-coordinate fact/catalog grant IDs and versions. The issuer
reads the current session from verified host context before issuing a
request-local handle. Never derive authority from a caller session override
or the old bridge's `_effective_session_id` convenience path. Normalize known
ingress failures (including the local resolver's malformed-input exception)
to denial. At release, rejoin the handle to the live session, operator opt-in
and exact grants under the existing partition fence. The host recheck must
be pure and must not reopen the partition. Do not reuse the delegated
write-side authority check that can reenter storage. Release denial always
discards the response and cleanup invalidates the handle on every exit.

Filter by requesting semantic scope and applicable owner before fact
validation. Join exact keyed current grant states using the canonical control
envelope (`atomic_store.py:3622–3662` at the reviewed baseline), rather than
using the legacy reader's global control scan. Match both claim-state and
native projection paths after scope and relevance checks. A hidden
claim-state match cannot prevent an otherwise valid native projection
match. At the composed-port boundary, handle the known managed generation,
snapshot integrity and SQLite read failures as payload-free `unavailable`.
Use narrow exception handling for the documented provider/store failures,
with handle cleanup, and preserve startup rejection as a separate result.

At final diagnosis release, sample the canonical storage administration
view once: current live/archived suppression journal plus its directive
records from the same fenced partition snapshot. Treat authoritative
normal absence as empty, and unreadable or unverified state as unavailable.
Do not sample cached per-coordinate results or acquire a control lock inside
the partition transaction. Inspection never invokes this sampling path.

## One Vertical Milestone and Checkpoints

| Order | Checkpoint and observable result | Evidence maturity when passed |
| --- | --- | --- |
| 1 | Land a walking path through the packaged factory: operator read opt-in on provisioned default storage, inspect `bill due date`, pass the selected version and canonical bill ID to recall, get an authorized date and an empty case with no credentials. Scope, grants, protected release and side effect protections apply from the first path. | Implemented and locally verified for this path only; OCI-01 through OCI-04 remain incomplete at the parent. |
| 2 | Bind the generic factory to the same core. Exercise both with `project owner` ambiguity, bill and work-item dates, authorized symmetric recall and distinct found/no-match/unsupported/clarification/error outcomes. Complete the full descriptor inventories and ordinary failure paths. | Locally verified on both real roots, pending complete proof set. |
| 3 | Close version handoff, visibility/temporal/suppression, legacy preservation, and read-only witnesses. Run applicable gates once for the coherent candidate and get focused review. Update current-state docs from observed evidence. | Level 2 readiness after all criteria pass. CI-enforced and operational evidence are tracked separately. |

Do not start a second milestone for the two ports. Update the checkpoint
result, requirement ledger, changed surfaces and sole next action after
every material finding or proof. Record exact implementation base/head or
scoped dirty digest for test and review evidence. At closure record one
revision-bound approval for the workflow, with deferred work listed.

## Change Map, Identity and Authority Chain

| Surface | Expected owner and identities | Boundary |
| --- | --- | --- |
| Typed public read requests and results | Core semantic ingestion read contracts. `CatalogRelationInspectionRequest`, `CatalogRelationInspectionResponse`, `CatalogRelationDescriptor`, `StructuredRecallDiagnosisRequest`, `StructuredRecallDiagnosisResponse`, `expected_catalog_version_digest`; exact union fields and outcomes per design. | Read-only public contract, no new persisted type, event or migration. |
| Relation projection | Behavioral module `core/semantic_ingestion/catalog_inspection.py`, or the existing canonical owner if review identifies it. Project verified seed profile and default corpus through their own type namespaces. Exact labels/aliases from Section 13. | No changed package metadata, corpus bytes, version digest, manifests or capability source fingerprints intended. If a source hash is affected, reconcile descriptor, release and package checks before closure. |
| Protected orchestration | `core/provider/service.py`, policy and claim assembly in `structured_fact_read.py` and existing scoped-context/forgetting owners. | Request-local state only. Legacy entrypoints and write-side paths retain their behavior. |
| Host/configuration | Existing `hermes_memory_provider.py`, `hermes_runtime_binding.py`, `hermes_factory.py` and `authenticated_source.py`; trusted host read opt-in, no new CLI, plugin or MCP registration. | Adapters translate. All releases use the core service. |
| Feature tests | Behavioral names such as `test_catalog_inspection.py`, `test_structured_recall_diagnosis.py`, and bounded real-root cases at the existing bridge/integration owners. | No CI change planned. Keep the five-case fixed Hermes product inventory unless a separately authorized testing operation changes it. |
| Planning traceability | OCI/ORD IDs, checkpoint numbers and plan names. | WorkPlan fields only. No planning-derived executable, persisted, diagnostic, fixture or workflow identities. |

Inventory actual modules and typed fields before the first implementation
edit. Reuse `StrEnum` declarations covered by the current identity gate.
Extend `memorii/tools/identity_hygiene.py` with narrow checks for actual
typed constructor and structured fixture positions for `kind`, `status`,
`read_form`, `read_direction`, and literal `value_type`; the generic field
list does not cover every case. Add mutations with M1, M2, M3, C2, R22 and
SIA-R22 through those declarations and positions to the existing identity
tool test owner. Retain the positive protocol and compatibility corpus and
prove that the same spelling in caller lookup text is accepted as data.
Definitions and opaque IDs are also data. No broad exceptions.

Baseline changed-surface ledger: this WorkPlan only. Design and old WorkPlans
listed above are pre-existing, plus the unrelated untracked directory. The
expected code authority chain is selected pointer → exact verified
version/runtime → package/profile or typed corpus → metadata or protected
claim read → host release. Test/CI chain is changed source → affected
required test jobs and package manifest member digests. Before closure,
verify every actually changed wheel member against Observation Ledger
release-preparation `candidate.json`, companion digest, and installed
proof pins. Distinguish derived authority refresh needed by CI from optional
release certification. Reconcile actual affected jobs and touched manifests
from the live diff. The active Package Smoke baseline dependency is recorded
in the gate ledger below. Unrun jobs are not presumed green.

## Validation Matrix

| Behavior and test witness | Defect detected / observable failure |
| --- | --- |
| Inspect all 3 seed and 56 default descriptors; preserve `ProjectId`/`PersonName` separately from corpus types, exact ID and normalized full-name forms, alias collision/dedup, entity/literal, direction and read form. Omit a nonqueried declaration. | Wrong descriptor or scope, silent partial projection, or a missing ambiguity. Unknown/null/mixed tags, oversized fields, wildcard and planned-coordinate mutations exercise closed boundary and status-only failures. |
| On both real factory surfaces after authorized provisioning and reopen, inspect project owner → clarify → select/recall; inspect bill due date → found/empty; get a `work_item_due_on` hit and an authorized native symmetric hit. Also exercise explicit inspection no-match and denial, and induce selected-closure and managed-generation failure after startup for live unavailable and handle cleanup. Use actual installed Hermes entry-point discovery (no metadata stub), separate generic factory, and tripwires for network/model, writer resolver, capture and completed-turn callbacks. | Wrong status or fake factory proof. Test retained grants without opt-in and compare exact response fields on both hosts. Startup rejection remains a separate proof. |
| Use `SelectedCatalogAuthorityRepository.install_default_catalog_release` for the controlled seed → default CAS on the same store. Test stale guard for shared and absent predicates before membership or fact lookup. Retry after fresh inspection; correct a fact without a catalog change. Verify authorized catalog-bound historical recall across the controlled change. Separately reopen an early selected learned overlay with no exact parent after base rotation: both new ports unavailable, existing authorized read behavior preserved. | Wrong digest, stale fact, fallback, false exact-parent proof or regression in historical reads. Keep unbound legacy read as a separate witness. |
| Verify precedence for malformed/unresolved, stale version, corrupt authorized selection, revoked grants, absent vs denied/invalid child, foreign account and peer agent. On authorized malformed/unresolved arms assert zero selection, projection or fact probes. Use barriers with independent managed SQLite handles for selection and each durable fact and catalog grant revocation: if read wins release its old authorized result then observe new selection or denial; if mutation wins observe the new selection or denial immediately. Separately block host release and withdraw the opt-in or change verified session; deny and clean up the handle. Test mismatched installation, storage root, account, agent and session. | Disclosure, stale authorization, snapshot mixing, or denied-child fallback. Hidden-only equals absent; visible plus hidden equals visible-only, including foreign claim-state rows alongside visible native projections. Non-success payloads stay empty. |
| Protected current read checks half-open validity, correction/retraction, both carriers and directions, seed-bound and pinned authority. Race journal suppression before the final sample without tombstone, and reverse order (next request sees suppression). Exercise a directive-only suppression, an authoritative empty view and an unreadable journal. Distinguish a removed but known suppressed dependency from unknown authorized provenance. | Expired/future facts, suppression leakage or silent omission of corruption. Suppression-first excludes, read-first returns prior lawful result then new absence; unreadable authority returns unavailable. |
| Compare store and counters immediately before/after calls once setup ends. Trap inspection fact/legacy/transcript/suppression probes and both calls' writer/recovery/model/learner dispatch. Verify failure responses, reopen and retry. | Read path mutates state, grows recurring gap counts, or does unrelated reads. |

Use small deterministic unit tests for grammar and inventory, installed tests
for real binding, authority and no-egress proof, and backend/barrier tests
for one transactional snapshot. No live model evaluation is needed.
Targeted test reviewer checks this matrix before coding the authority/fence
path; focused correctness review at the runnable candidate covers
authorization, availability and integrity. Additional suite architecture or
CI changes go through a separate linked testing operation if needed.

## Commands and Gate Ledger

From `memorii/`, use the current PR workflow's Python 3.11,
`pip install -e '.[local,dev]'`, warnings-as-errors where indicated, and
record local interpreter/tool versions and candidate identity. Local baseline
environment is Python 3.12.16 and is not PR runner parity.

```sh
python -W error -m pytest -p no:cacheprovider -q tests/unit/core/semantic_ingestion/test_catalog_authority.py tests/unit/core/semantic_ingestion/test_catalog_capture_pin.py tests/unit/core/semantic_ingestion/test_structured_fact_read.py tests/unit/core/test_scoped_context_activation.py tests/unit/core/test_sqlite_memory_plane_store.py
ruff check memorii tests
python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json
pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
python -m memorii.tools.test_shards verify --config tests/ci/unit-shards.json
pytest -W error tests/integration/test_scoped_context_production_binding.py -p no:cacheprovider
```

| Gate in `.github/workflows/pr-gates.yml` | Candidate evidence |
| --- | --- |
| Static Analysis, Unit Test Shards 0–5 and Unit Timing Inventory | Add exact new node IDs once implemented. Use workflow shard commands including timing outputs, aggregate timings and `MEMORII_SOURCE_REVISION`. Verify collection and all relevant required shard/aggregate jobs once. |
| Scoped Context Integration | Add compact real-factory cases to `tests/integration/test_scoped_context_production_binding.py` and prove the exact command above collects them. Require the real package metadata route in the Hermes case, without changing the fixed legacy product suite inventory. |
| Package Smoke | Run the workflow wheel build, preparation, installed proof, rejection and smoke steps or record their current green PR execution. Required package proof remains distinct from release certification. |
| Hermes Level 2 Product and Hermes Installed Image Lifecycle | Check current job commands and fixed collection. Record required current runner results with `Semantic Ingestion` aggregate. Docker-specific evidence requires the corresponding environment. |
| Unit Tests aggregate and other required PR jobs | Reconcile current `needs` and branch protections against final changed surfaces. Record event, executed SHA and run URL. A focused result or a local runner with different Python does not establish CI parity. |

No implementation-specific command, broad job, release artifact or external
certification was run in the planning turn. Time existing owner cases at the
first implementation checkpoint before adding slower installed coverage.
Initial map baseline: the five unit modules passed 81 tests under Python
3.12.16 at `7c6a3a94`. Reviewed baseline: the same command plus
`tests/integration/test_partition_generation_selection.py` passed 92 tests
under Python 3.12.16 at `d62a3abd`. Neither proves feature behavior or PR
parity. The scoped Markdown diff passed whitespace checks.

### Known Package Smoke baseline failure

Package Smoke runs
`python ../docs/work/semantic_ingestion/observation-ledger/release-preparation/run_installed_proof.py "$PREPARED" "$PROOF"`
from `memorii/`. The test reviewer reran this entrypoint with disposable
directories. It exited 1 before reading prepared input:
`proof_candidate_member_changed:docs/design/durable_execution_and_solver_runtime.md`.
The manifest sidecar matches its manifest. Of its 1,934 members, six no
longer match, reproduced against committed bytes at both `7c6a3a94` and
`d62a3abd`:

- `docs/design/durable_execution_and_solver_runtime.md`
- `memorii/memorii/core/persistence/runtime_checkpoint.py`
- `memorii/memorii/core/persistence/runtime_repository.py`
- `memorii/memorii/core/storage_administration/operator_governance.py`
- `memorii/memorii/core/storage_administration/service.py`
- `memorii/memorii/tools/runtime_operator.py`

The implementation coordinator assigned the active inventory and digest to
the package proof owner. The full offline workflow now passes on the
isolated ontology candidate. The integrated branch inventory and its
Package Smoke run are tracked in the implementation progress below.
Historical proof and closure records are preserved.

## Compatibility, Rollout and Rollback

Operator-controlled read opt-in after authorized provisioning. Close the new
read binding to withdraw the feature without changing existing reads, stored
grants or fact history. Use only the existing catalog version installation
owner in controlled tests; no new runtime rollback capability. Keep status
diagnostics typed and free of hidden data. Preserve existing authorized
startup behavior, no mutation within either read, and no egress fallback.

## Progress, Evidence and Review Log

- 2026-11-27: Checked approved design checksum, reconstructed four
  requirements, inspected live code baseline and CI jobs, and prepared one
  vertical implementation path. Code mapper mapped both real entrypoints
  and shared protection seams. No runtime changes.
- Plan-review cohort: spec, correctness and test reviewers read plan
  SHA-256 `985e1de28e9cc958ce0efda25950ba6c3b046c52ea7733503c0e46b4b42231ef`
  and design SHA-256 from the header at `d62a3abd`. Plan findings required
  changes to authority binding, managed failure/suppression handling, the
  host journey and compatibility witnesses, race and identity evidence, and
  the baseline/gate ledgers. Reconciled overlapping findings by contract or
  evidence family. Correctness risks describe reachable failure paths if
  implementation omitted the clarified protections; no feature defect or
  verified requirement is claimed for the unimplemented ports.
- Targeted delta: all three reviewers approved the revised planning
  candidate at `d62a3abd`, plan SHA-256
  `442090b728092c2fd6ae5f754b7932ebeb3bc96fbff4090ff70fcf5ea3b9e2d5`
  before this bookkeeping entry. Spec confirmed the installed work and
  historical cases, correctness confirmed authority and serving safeguards,
  and test review confirmed the gate dependency and discriminating proofs.
  Planning review has no remaining required findings. The known Package
  Smoke dependency remains open for implementation closure.
- Plan and baseline commands record readiness evidence only. Feature review,
  milestone closure and exact implementation evidence remain pending.
- Implementation starts from `bc01cc2e004078c8b1114fe3ed7f2f47061292f7`.
  The intervening commits are managed host intake and rehearsal; the frozen
  design digest and two ontology entrypoint seams still match. The earlier
  runtime-source test diff is now committed in the baseline. The sole
  production writer owns the paired read methods and their compositions.
  The coordinator owns verification and this plan. A separate read-only
  investigator has exclusive edit ownership of active Package Smoke pins
  if required. The recorded design, related plans and unrelated untracked
  directory remain baseline inputs. No runtime callers have been verified.
- Initial implementation evidence: three catalog contract tests passed
  with warnings treated as errors, including both verified inventories,
  preservation of seed endpoint types, strict request parsing and rejection
  of a missing nonqueried declaration. The installed acceptance case now
  provisions bill, work-item, project-owner and symmetric facts through
  the existing writer and reopens both read hosts without the write tool.
  Its runtime result is still pending.
- Package Smoke baseline recheck on `bc01cc2e` reproduced eight stale pins:
  the six recorded above plus `core/harness_state/service.py` and
  `core/harness_state/sidecar.py`. The active manifest and its companion
  digest were refreshed. An isolated macOS Python 3.12.16 run passed the
  19 package prerequisite tests, wheel build, deployment preparation,
  installed proof, five rejection cases, imports and runtime artifact
  validation. This is resolved baseline evidence only. The implementation
  candidate needs its own run. Parallel managed-harness work is excluded
  from the ontology candidate.
- The seed-to-default handoff test passed against the real install owner:
  a shared catalog digest did not bypass the changed version, and neither
  stale, unsupported, malformed nor unresolved input entered fact lookup.
  The isolated Linux arm64 Python 3.12.16 baseline also passed the full
  Package Smoke command block; GitHub Ubuntu Python 3.11 evidence is still
  separate. All 152 identity hygiene tests passed, including the six
  coordinate mutations and the accepted lookup-data cases.
- Installed checkpoint attempt wrote all four corpus facts, then failed
  during real host reopen after removal of write-tool authorization:
  `PreplanningStoreError: observation ledger activation reload is partial
  or mismatched` (underlying successor/inventory mismatch). Preserved the
  disposable store to discriminate the failing validation rule without
  another complete ingestion run. No installed checkpoint promoted.
- Reproduced the restart on the disposable store under the debugger. The
  stored and current package-derived writer, observation schema and codec
  fingerprints differed after source edits during the run; writer epoch,
  predecessor, graph schema and draining state matched. The system correctly
  refused a mixed package. The reusable store is not valid candidate
  evidence. No activation check was weakened.
- Froze a feature-only export on `bc01cc2e`, excluding concurrent native
  harness intake and retaining only the exact grant-key hunk of the shared
  atomic store. Frozen package root digest:
  `fa69a4d231d7c64f9daba1663c7abc279beffed39d1d6868fe78dbfe63bc6c9c`.
  Launched the installed host suite, deterministic regressions and
  independent package proof against that source. Both deployed adapter
  methods and both core entrypoints are now mapped in production; feature
  verification and review remain pending.
- That first stable export passed all 146 scoped-context integration cases
  (325 seconds), including both installed host bindings from reopened JSONL
  with no write tool, credential, or egress. Local Linux Package Smoke
  passed on the same production bytes. The provenance review then required
  the ordinary-history joins, endpoint authority, and correct treatment of
  known suppressed but absent history. The remediated reader reuses the
  existing atomic store verifier and identifies required dependencies before
  checking for their presence. The final isolated run includes managed
  SQLite and the absent-then-suppressed fanout witness. Earlier evidence is
  retained at its own package identity only.
- Whole-tree Ruff 0.17.6 on the provenance candidate reported `SIM102` in
  `memorii/core/solver/verifier.py:52` and `I001` in
  `tests/integration/test_runtime_sidecar.py:3`. The same command reproduced
  both failures on the isolated committed `bc01cc2e` baseline. The files
  are outside the feature. Scoped lint and full local Pyright passed; this
  is not a green whole-tree Static Analysis claim.
- On the final isolated candidate (package root digest
  `d38b9aa4026e4a95443cabb85576a8f9f27c4da35ade1a21e18bd55f2cd21323`),
  the focused regression set passed 253 tests, Pyright reported zero
  errors, and the six-shard inventory verifier passed with 5,329 collected
  tests. The correctness re-review cleared the final suppression fix.
  The managed installed host run remains in progress.
- The same final feature source passed the full Package Smoke command
  block on offline Linux arm64 Python 3.12.16. The installed proof covered
  the 1,939-member inventory, 19 prerequisites, wheel preparation, five
  installed mutation rejections, imports and benchmark artifact validation.
  Active candidate digest:
  `4fecedb0d122e954ef05c416d71a435da26df2ff817e893ce7b765227beb4f9f`.
  Linux wheel digest:
  `9bcaee59ce93fc81d041bebd9877eaa9dba0bef91bc8b16b25c3f62a6c280803`.
  The local setup used cached dependencies. GitHub's Ubuntu Python 3.11
  job remains unverified.
- The shared branch advanced to `0bbc68a2e519b26371ffa5eab9f63bd6d8dc332c`
  via two concurrent native-harness commits. The PR workflow bytes are
  unchanged. The package owner is reconciling all active pins and rerunning
  Package Smoke on the integrated source. Isolated results remain bound to
  their original snapshots.
- The managed provenance run provisioned all four claims and reopened
  Hermes, then returned `unavailable` for the authorized bill. The other
  145 scoped-context cases passed. Saved-store tracing isolated the original
  capture fence versus derived retained-source fence comparison. The
  [debugging plan](debug-retained-source-recall.plan.md) records the
  reproduction and the fix using the existing retained-source proof with
  the fenced snapshot. Managed acceptance must rerun with that fix.
  The correctness reviewer verified the corrected proof against the saved
  managed store, then removed the retained-operation link from the snapshot
  and confirmed that proof fails closed. The regression affects the default
  retained bill path (P1, changes required, runtime behavior). Targeted
  remediation review passed.
- Integrated Package Smoke passed before the fence fix. It reconciled four
  newly stale and nine previously unpinned wheel inputs across both
  deltas. Candidate `7bbe431054d3c72a609c7fcbca7a9a5c79a829fb69ee4846734d9672df1257ac`
  bound 1,948 pins to wheel
  `ddac34d5b2b138ac50c6d605c79a024aeedb1f4cafde327215eeedc8562a984e`.
  The package owner is refreshing the one changed atomic store pin and
  rerunning on the corrected candidate.
- On the corrected integrated snapshot, the catalog, read authority,
  revocation, identity, SQLite and managed-generation regressions passed
  253 focused tests with warnings as errors. The full scoped-context suite
  and all six local unit shards with timing collection are running from
  the same source. Whole-tree Pyright
  reported four attribute errors in the concurrent native-source admission
  module. Whole-tree Ruff reported three diagnostics in the solver verifier
  and the native-source capture and runtime sidecar tests. Both commands
  reproduced those exact locations and diagnostics on a clean archive of
  `0bbc68a2`. Changed-file Ruff, repository identity hygiene and the
  5,329-case unit shard inventory passed on the corrected candidate.
- Package Smoke passed on the corrected integrated snapshot. The exact
  workflow block passed 19 prerequisites, protected installed-wheel
  proof, five installed rejections and artifact validation. Candidate
  `0dff4ed60430836aa513b5747610eb6ac3f40fe369c6313b60596bd7aa8e0402`
  binds all 1,948 pins to wheel
  `e2d1db313b1e6f3867144d770bf349233bd20337c693c31a30bbbae2662a042e`.
  The local log is
  `/private/tmp/memorii-package-retained-fence.gAeg7o/evidence/workflow.log`.
  Runner: Linux arm64 with Python 3.12.16 and cached dependencies. The
  GitHub Ubuntu Python 3.11 job remains unverified.
- Compared the 22 changed Python and package-proof paths against the
  corrected integrated snapshot at
  `/private/tmp/memorii-package-retained-fence.gAeg7o/source`. All bytes
  matched. The sorted path and content digest is
  `60da70235eccce0c924c3edc83d28b013588f8f2fb8a0c2672faa4fb8c7c2880`.
- The final corrected integrated candidate passed all 146 scoped-context
  integration cases in 407.53 seconds under macOS Python 3.12.16 with
  warnings as errors. The 401.56-second managed SQLite case reopened the
  installed Hermes bridge and generic authenticated source after authorized
  provisioning. Both passed bill and work due dates, ambiguous project-owner
  selection, and symmetric recall without any API key, egress, or write
  tool. The case also passed late session change, opt-in withdrawal,
  suppression before release and removed history with and without a
  suppression journal entry. The Hermes base class was the sole host ABI
  test double. Log: `/private/tmp/memorii-retained-fence-integration.log`.
- Replaced injected grant records in the unit regression with the canonical
  writer's durable states. The managed cases now check that an independent
  exclusive lock attempt is refused while the read pauses at release.
  The actual catalog install and both grant-revocation writes enter their
  transactions after the old read authorizes release. The next request sees
  the new catalog version or denial. The test reviewer identified an
  initial scheduler-dependent assertion and cleared the replacement.
  Both managed cases failed at the lock assertion with the fence bypassed
  in a disposable test copy. The corrected tests passed within the
  255-case focused run. Identity hygiene, changed-file Ruff and the
  5,331-case shard inventory passed.
- The final scoped dirty tree digest is
  `647ee391b28767439adb5d0c17d6e0bcaf228f4e205a4e76a211a73936c3c022`.
  Only `tests/unit/core/semantic_ingestion/test_catalog_read_workflow.py`
  changed after the passing host and package snapshot. No wheel input,
  package inventory pin or host integration test changed. Stopped the
  local unit matrix attempt on the superseded test inventory before a
  shard completed. No full unit matrix or timing aggregate is claimed.

## Blockers, Decisions and Limits

The user confirmed that ontology ships on the shared
`codex/durable-delivery-implementation` branch for v8. The concurrent
runtime-overlay and capture work is included in combined branch verification.
Its current working tree already resolves the previously recorded whole-tree
Ruff and Pyright failures. Both checks passed locally on the combined tree.
GitHub confirmed the branch has no existing pull request and the current
remote main and v8 heads are `885c7db7` and `0bbc68a2`, respectively.

No unresolved approved-design choice. The bill workflow and package gate
have local verification. Milestone closure still requires the remaining
acceptance witnesses and scope-required checks, including actual PR runner
evidence. The unit shards and timing aggregate are separate from successful
inventory collection. Clean-baseline Ruff and Pyright failures are recorded
as branch-level gate evidence.

## Next Action

Finish the bounded Level 2 acceptance witnesses, then verify and publish
the integrated v8 candidate on the existing branch.

## Outcome and Retrospective

Both host bindings are implemented and the first end-to-end workflow
passes on the managed local store. The milestone remains open for the
remaining acceptance and gate evidence.
