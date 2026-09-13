# Graph Transaction Authority Rejection

- Work ID: semantic-ingestion-graph-transaction-authority-debug
- Work type: debugging
- Status: active
- Coordinator: root
- Created: 2026-09-13
- Last updated: 2026-09-13
- Parent WorkPlan: `../engineering-closure/implementation.plan.md`
- Related WorkPlans: `../engineering-closure/milestones/05-authenticated-observer-comparator.plan.md`, `../engineering-closure/milestones/06-host-composition-closure.plan.md`
- Canonical inputs: current branch, semantic-ingestion architecture, configured observation integration fixture
- Expected outputs: causal correction, regression proof, exact-revision independent closure review

## Objective

Restore the canonical graph transaction path required to seed a committed
cohort for authenticated public observation. Preserve writer, monitor,
preplanning, lease, registry and observation-ledger authority boundaries.

## Expected And Observed Behavior

The configured observer must use the existing built-in graph execution with a
complete typed registry, an activated observation ledger, and a current signed
capability-monitor authority for proposal fingerprint
`38a5be91af79d7e5ba9809bf383c699b6864ee50446239fe56a45e32b84638fe`.
That authority initializes the fresh evidence-only writer's capability status;
the ledger then activates that existing writer. A supported source can then
reach the graph terminal and append its observation delta.

The former fixture activated a manually seeded writer without that signed
monitor authority. Built-in graph execution correctly could not read an active
capability status and returned the public
`graph_transaction_authority_unavailable` result before graph-group commit.
The initial generic reason therefore described a deliberate guard outcome,
not a graph authority, lease, registry, or replay defect.

After the monitor-authorized route reached terminal persistence, repeated
validation rescanned every compiled declaration for each nested CTV model.
The compiled registry now supplies immutable lazy coordinate indexes for
entries and parsed roles; body validation and model materialization use those
indexes for entry, role, reachable-closure, and enum lookup. Focused poisoned-
source regressions prove nested validation and codec conversion no longer read
the original entry or declaration sequences after the indexes are built.

## Hypotheses

1. **Disproved:** observation-ledger activation changes writer or lease
   coordinates. The unsigned route activates successfully before refusing the
   graph group; no group primary is persisted.
2. **Confirmed:** the fixture omitted the mandatory signed capability-monitor
   authority. With no current capability status for the proposal fingerprint,
   the built-in graph route rejects before group commit. A factory-issued
   verified authority supplies the initial evidence and status through the
   normal constructor path.
3. **Disproved for the observed rejection:** registry/activation replacement
   changes a replay digest. The positive composition passes registry and
   activation construction and enters full terminal validation after the
   signed authority is supplied; it no longer reproduces the original
   immediate authority rejection.
4. **Confirmed and corrected:** typed body validation and model conversion
   rebuilt role maps and closure inputs by scanning the full compiled registry
   at nested-model boundaries. The canonical immutable indexes remove those
   scans while retaining typed missing and duplicate-coordinate rejection.
5. **Confirmed, correction pending:** activated graph writes repeatedly run the
   complete retained observation-prefix verifier. Its selected-artifact path
   still scans all parsed declaration roles to select one digest/signature
   policy and then fully materializes and re-encodes each byte-identical
   registered artifact. This occurs inside governed-write admission before the
   same graph write can commit; it is separate from terminal construction.

## Changed Surfaces And Ownership

The retained correction is a fixture/test gap, not a product defect:

- `memorii/tests/integration/test_observation_ledger_activation.py` extends
  `_provider_factory` with an empty-default typed tuple of verified monitoring
  authorities and forwards it into the canonical service constructor.
- `memorii/tests/integration/test_composed_graph_observation_service.py`
  issues a signed authority for the fixed proposal fingerprint, removes the
  incompatible manual seed from the positive fixture, and adds the unsigned
  no-group fail-closed sibling.

The parent implementation WorkPlan retains comparator and host-closure state.

## Verification Matrix

- Reproducer before correction: `PYTHONPATH=memorii .venv/bin/python -W error
  -m pytest memorii/tests/integration/test_composed_graph_observation_service.py
  -q` produced four fixture setup failures in 24.00 seconds because no
  `IngestionObservationDelta` existed.
- Failure sibling after correction: the unsigned monitor test passed under
  warnings-as-errors in 40.40 seconds. It observes the public
  `graph_transaction_authority_unavailable` reason and proves no
  `semantic_ingestion_bootstrap_graph_v3_group_commit_primary` record exists.
- Typed-registry regression proof: `PYTHONPATH=memorii .venv/bin/python -W
  error -m pytest memorii/tests/unit/core/memory_evolution/test_typed_value_registry_compilation.py
  memorii/tests/unit/core/memory_evolution/test_typed_value_body_validation.py
  memorii/tests/unit/core/memory_evolution/test_typed_value_model_codec.py -q`
  passed 56 tests in 8.19 seconds. Ruff passed. Scoped Pyright with the venv
  interpreter passed with 0 errors and 0 warnings.
- Positive discriminating experiment after the indexed-registry correction:
  `PYTHONPATH=memorii .venv/bin/python -W error -m pytest
  memorii/tests/integration/test_composed_graph_observation_service.py::test_configured_service_observe_graph_returns_real_page
  -q` remained running after the five-minute ceiling and was interrupted at
  320.05 seconds. The bounded traceback stopped in
  `canonical_contract_value` while recursively lowering a dictionary in
  `semantic_ingestion/contracts.py:152`. The typed-registry scan is therefore
  corrected, but a separate terminal-persistence performance boundary remains.
- A 90-second cumulative profile of the same signed route reached native group
  publication. Registered typed-value encode/decode and canonical emission
  dominated the sample; the graph group writer spent 40.49 seconds under the
  profiler and native projection evidence spent 27.15 seconds. A subsequent
  uninstrumented run was still active after 191.62 seconds.
- A 60-second faulthandler snapshot located the uninstrumented run in governed
  writer admission: `_validate_activated_observation_snapshot` replayed the
  complete schema-3 prefix, `_selected_value` validated and then emitted a
  registered artifact, and typed-value materialization re-ran a semantic
  contract digest while decoding a byte-identical ledger artifact. This
  disproves the narrower terminal-only hypothesis and identifies retained
  ledger verification as the active cost center.
- Static evidence: Ruff passes on both changed Python files. Direct Pyright on
  those integration modules reports ten existing test-environment/type-narrowing
  findings (including unresolved pytest and cryptography imports); this command
  cannot establish a clean changed-surface Pyright result.

## Root Cause And Classification

Trigger: the configured observer fixture used a complete registry and ledger
target but supplied no verified capability-monitor authority.

Defective assumption: ledger activation and a manually seeded writer were
assumed to make a built-in proposal eligible for graph execution. The built-in
planner instead requires an active, fingerprint-matched capability status.

Propagation: absent monitor initialization leaves that status unavailable;
the planner rejects before graph-group persistence and intentionally projects
the non-disclosing graph-authority-unavailable result. Existing tests had a
normal positive observation assertion but no paired monitor-authorized setup
or unsigned route check.

Classification: fixture/test gap. No production guard was weakened or changed.

The repeated typed-registry scan was a production performance defect. Its
correction preserves registry bytes, digests, equality, wire schema, and
fail-closed missing or duplicate-coordinate behavior. Remaining parsed-role
scans in registered-artifact policy selection and repeated full verification
of identical artifact bytes keep the positive production route above the
bounded integration-test window. Any reuse correction must be operation-local,
bound to exact bytes and the exact registry/publication/verification-key
authority, and must never let a changed snapshot or substituted artifact
inherit a result.

The governed-write admission path now creates one
`ActivatedObservationArtifactProofContext` for each policy validation and
passes that exact typed context synchronously to the registered snapshot
validator. Each
proof begins with the full protected read, exact native materialize/reencode,
and registered integrity policy verification; it binds the raw bytes, root
schema, complete history publication identity, selected target publication,
binding, and callback token. The context is not persisted or retained by the
store. It reuses only byte-identical raw/schema selections within that callback
and rejects foreign or stale proof state. Prefix membership, locator joins, and
sequence validation remain in the complete replay path.

The compiled registry also derives an immutable indexed digest-signature role
table. Runtime artifact, activation, and checkpoint policy selection checks the
policy's recomputed closure digest against the published entry before returning
it, so an indexed lookup cannot weaken the committed declaration policy.

Focused verification on the current dirty candidate:

- `PYTHONPATH=memorii .venv/bin/pytest -q -W error memorii/tests/unit/core/memory_evolution/test_typed_value_registry_compilation.py memorii/tests/unit/core/memory_evolution/test_typed_value_artifact_integrity.py memorii/tests/unit/core/memory_evolution/test_observation_checkpoint_integrity.py memorii/tests/integration/test_observation_ledger_replay.py` passed 65 tests in 27.84 seconds. The writer-admission seam regression proves a fresh context per validation, exact identity into the synchronous callback, and false-callback rejection.
- Ruff passed on the changed runtime and focused-test files; `git diff --check` passed.
- Scoped Pyright passed with 0 errors and 0 warnings for the changed leaf runtime modules, including `writer_admission.py`. Pyright on `atomic_store.py` retains 23 pre-existing diagnostics outside this change's methods, so it is not a clean file-level gate.

The signed configured-observer route now passes under warnings-as-errors in
279.25 seconds. This is a correctness result rather than a bounded-runtime
claim: it proves the monitor-authorized, activated-ledger route reaches the
public detached observation path without weakening the retained artifact
checks.

After both detached-read lexical scopes were installed, the same signed route
passed under warnings-as-errors in 213.72 seconds. Setup completed before the
180-second diagnostic sample and the remaining work was in authenticated
public paging. This freezes the performance remediation: the route is 65.53
seconds faster than the first passing candidate and no longer exceeds the
original five-minute ceiling.

The detached observation reader had no lexical emission scope of its own, so
the same raw registered artifact could repeat the final canonical re-encode at
each detached authority consumer. `canonical_emission_scope` is now the codec
owner's reusable lifecycle helper: it reuses an enclosing scope, or otherwise
pushes one fresh bounded scope and pops and purges it in `finally`. The entire
`read_detached_observation_authority` execution is enclosed. Unlimited
byte-identical raw values can replay only their already-proved final re-encode
verdict within that read; strict parse and complete typed decode still run on
every call. Limited decodes remain outside the replay path, and no result is
retained after a detached read returns or raises.

The signed-observer route took 245.21 seconds before lexical digest-scope
reuse was available. Its detached replay repeatedly validated
content-addressed semantic contracts reconstructed from the same retained raw
artifact. `canonical_digest_verification_scope()` now owns only that lexical
validation reuse: it reuses an enclosing scope without owning it, or pushes a
fresh thread-local scope and always pops and purges it. The detached reader
nests it with `canonical_emission_scope` across the complete replay. It does
not construct a `CanonicalEvidenceArena`, retain a result beyond the read,
relax limited decoding, or allow an altered equal-declared-digest instance to
inherit validation.

Focused proof for that boundary:

- `PYTHONPATH=memorii .venv/bin/python -W error -m pytest -q memorii/tests/unit/core/test_ingestion_contracts.py memorii/tests/unit/core/semantic_ingestion/test_canonical_evidence_arena.py memorii/tests/unit/core/memory_evolution/test_detached_observation_emission_scope.py` passed 79 tests in 5.72 seconds. It includes byte-identical, changed-byte, limited-decode, purge-on-success-and-error, nested-scope identity, new-invocation recomputation, thread-local isolation, decode-then-encode digest reuse, forged equal-declared-digest rejection, and detached-read push/pop/no-arena proofs while retaining map/set/wrapper/bool-int codec adversaries.
- Ruff and `cd memorii && ../.venv/bin/pyright --pythonpath ../.venv/bin/python memorii/core/memory_evolution/ingestion_contracts.py memorii/core/memory_evolution/atomic_store.py` passed with 0 diagnostics; `git diff --check` passed.
- A direct scoped Pyright run over the newly touched arena and detached-store
  modules reports 22 existing diagnostics in `canonical_evidence_arena.py`
  (the generic arena owner and pre-existing optional-scope typing); it reports
  no diagnostic at the lexical helper or detached-read scope boundary.
- The consolidated affected suite passed 165 tests in 40.23 seconds under
  warnings-as-errors, covering typed-registry compilation/body/model/integrity,
  observation checkpoint and ledger replay, canonical codec/arena lifecycle,
  detached scope lifecycle, and the unsigned monitor fail-closed integration.

## Historical Next Action At `57669a0a`

Remediate the exact-revision review findings in one bounded writer round:
support only the identified historical V2 manifest as an activation-migration
predecessor, supply signed monitor authority to the live-drain success fixture,
and add real composed-service proofs for callback rejection, immutable-ledger
tampering, fresh call-local proof contexts, configured scope denial, and
emission-scope thread isolation.

## Exact-Revision Review At `57669a0a`

- The specification auditor approved the bounded debug mechanisms and found no
  wire-format, authority, replay, index, or lexical-scope regression.
- The correctness reviewer confirmed a P2 compatibility defect: the exact
  retained V2 manifest digest `88ac...` predates the four capability-monitor
  record kinds and is rejected before activation. The correction must recognize
  only that exact predecessor and atomically rotate it to the current manifest.
- The correctness reviewer also confirmed a verification-fixture defect: the
  live-drain success route omits the signed capability-monitor authority that
  the production graph transaction now correctly requires.
- The test reviewer required end-to-end R17 proof through real `sync_event`,
  atomic snapshot validation, immutable ledger joins, detached observation,
  callback rejection with unchanged state, fresh call-local proof contexts,
  configured authorization denial before snapshot reads, and emission-scope
  thread isolation.
- The test review's parent-scope observation that R03, R08, R16, and R19 remain
  unmapped is confirmed but belongs to the parent engineering-closure WorkPlan;
  it does not expand this debug remediation slice.

## Remediation Progress

- The writer now recognizes exactly one retained pre-monitor V2 manifest:
  `88acb5940fb93c7807a17ef6af0765df019c6b1f384be2d362b80a15b9f5a104`.
  Its complete kinds/methods body is reconstructed and digest-pinned; no
  arbitrary `semantic-generation-v2` manifest is accepted. Activation accepts
  that predecessor only during the normal draining CAS and writes the current
  observation-ledger manifest in the same cutover transaction.
- The live-drain success fixture now supplies the matching signed
  capability-monitor authority and complete registry. Its real held-operation
  drain/activation regression passed in 83.93 seconds, proving both terminal
  operations reach the activated graph path while the unsigned sibling remains
  a denial proof.
- A JSONL reopen regression replaces only the fixture's persisted writer
  manifest with that retained predecessor, then proves public activation rotates
  it to the current manifest. The focused predecessor plus detached-scope suite
  passed: 4 tests in 9.59 seconds under the package virtual environment.
- The composed public-observation fixture now supplies the signed
  capability-monitor authority for its successful live drain and records the
  real group and source-terminal callback proof-context identities. It also
  exercises callback rejection and configured pre-read scope denial. Callback
  rejection leaves the activated ledger plus group-primary CAS set unchanged
  and emits no group primary. Source-normalization controls may already be
  committed before that callback, so they are intentionally outside this
  atomic-boundary assertion.
- A detached immutable-group substitution initially propagated a
  `PreplanningStoreError` through the public graph read. The paging runtime now
  maps deterministic `ValueError` validation failures from both initial public
  page routes to the existing non-disclosing `denied` response. The real
  timed-snapshot tamper proof passed in 159.72 seconds; it changes the retained
  group primary's reload bytes, proves no payload leaks, and preserves the
  normal fencing read.
- The earlier broad composed module was capped after 332.64 seconds as
  required; before interruption it had 7 passes and one test-only
  `dataclasses.replace` error on a Pydantic record. The focused corrected
  replacement proof above supersedes that test-only failure.
- Canonical emission scopes now have an explicit two-thread regression: each
  thread receives a separate lexical scope and exits without a retained scope.
- Ruff, `git diff --check`, and scoped Pyright for `writer_admission.py` pass
  cleanly. Full-file Pyright for `atomic_store.py` remains outside the clean
  leaf scope because of pre-existing diagnostics.
- Ruff and `git diff --check` pass after the live-drain fixture correction.
  Scoped Pyright on the complete activation integration module reports five
  existing optional-digest and decoded-BaseModel narrowing diagnostics; none
  are on the new signed-authority setup.

## Next Action

Hand the durable monitor-baseline recovery remediation and focused evidence to
fresh independent reviewers before refreezing the debug candidate.

## Exact-Revision Review At `43281a9e`

- The specification auditor approved the bounded remediation and found no
  additional contract gap.
- The correctness reviewer confirmed a P2 compatibility/authority defect:
  including the historical predecessor in general supported-manifest checks
  lets normal `current()` and `require_current()` authorization initialize
  capability-monitor records before ledger cutover. The predecessor must be
  readable only by the dedicated drain/activation migration path.
- The test reviewer confirmed three missing public proofs: a recomputed foreign
  body with the same V2 revision must fail without persisted change; the public
  cutover must be observed as one JSONL batch containing successor writer,
  activation, and genesis head; immutable-group tampering must return the exact
  non-disclosing response through ingestion-time paging as well as graph paging.

## Exact-Revision Remediation Evidence

- General `current()` and `require_current()` acceptance now excludes the
  pinned retained predecessor. A dedicated activation binding/read path alone
  accepts it for the drain and cutover CAS; the governed-write policy permits
  that manifest only for the private transition owner. The normal current
  observation-ledger successor remains readable for idempotent public
  activation reload.
- `ProviderMemoryService` detects only the exact retained predecessor and
  defers verified capability-monitor initialization. Construction performs no
  writes; successful ledger activation commits the successor/activation/head
  batch before the separately validated monitor baseline is persisted.
- New public JSONL regressions prove: a recomputed same-revision foreign body
  fails activation with byte-identical storage and no activation/head; exactly
  one batch contains successor writer, activation, and genesis head with no
  earlier successor activation digest; and signed-monitor reopen makes zero
  pre-cutover writes or capability records before one cutover batch.
- The immutable retained-group tamper proof now covers both public graph and
  ingestion-time routes. Each response is the exact non-disclosing denial, and
  an untampered request immediately after each failure returns its real page,
  proving the denied request did not retain paging capacity.
- Focused verification: the activation regression set initially exposed an
  idempotent reopened-successor defect, which was corrected rather than
  treated as evidence; the five-test retained-predecessor, foreign-body,
  one-batch, signed-construction, and live-drain replay selector then passed
  in 99.66 seconds. The public graph/ingestion tamper regression passed in
  227.43 seconds, below the six-minute cap. Ruff, `git diff --check`, and
  scoped Pyright for `writer_admission.py`, `provider/service.py`, and
  `semantic_ingestion/capability.py` passed cleanly (`0 errors, 0 warnings,
  0 informations`).

## Exact-Revision Review At `70e94615`

- The specification auditor approved the bounded contract and reported no
  remaining P1/P2 in its scope.
- The correctness reviewer confirmed a P2 recovery/concurrency defect in
  deferred multi-capability initialization: the complete tuple remains pending
  until every sequential baseline succeeds and initialization is not
  serialized. A later failure or concurrent activation can replay an already
  persisted baseline at a new clock sample and strand the failed suffix.
- The test reviewer required a normal production monitor trigger while the
  retained predecessor is installed, with unchanged storage and no capability
  records, plus explicit proof that all capability initialization batches occur
  strictly after the atomic successor/activation/head cutover batch.
- Because this exposes a second failure mode at deferred initialization, the
  root-cause model now includes per-item progress and concurrency, not only the
  predecessor authorization boundary.

## Deferred Initialization Remediation Evidence

- `ProviderMemoryService` now holds an instance-local reentrant lock through
  deferred monitor initialization. It consumes each front item only after its
  baseline succeeds or its authority is intentionally non-current; an exception
  retains that item and the unattempted suffix, while completed prefixes cannot
  replay on a later clock sample.
- The retained-predecessor JSONL proof now invokes the normal monitor tick
  before activation, verifies its unavailable-status failure and byte-identical
  storage, then proves the same tick works after cutover. It also proves every
  batch through the successor/activation/head cutover has no capability record,
  and initialization appears strictly later.
- New public integration regressions cover two signed authorities with a
  second-baseline failure, advancing the service clock before retry, and two
  concurrent public activation calls. The failed-suffix retry passed in 26.30
  seconds; the signed pre-cutover and concurrent initialization selectors passed
  in the preceding focused run. No capability baseline is duplicated.

## Exact-Revision Review At `8c4d6e04`

- The specification auditor approved the bounded lifecycle contract with no
  P1/P2 finding.
- The correctness reviewer confirmed a P2 restart/multi-host recovery defect:
  pending progress is only instance-local. After one baseline persists and a
  later baseline fails, a new service rebuilds the full tuple and replays the
  first baseline at a new clock value; byte reconciliation then rejects it and
  strands the remaining suffix.
- The test reviewer confirmed the retry test can miss prefix replay because it
  replaces a private initializer and checks only final equality, while the
  concurrency test lacks a barrier at the real conditional-write boundary.
- The root cause now includes durable baseline identity and cross-instance
  recovery. Instance-local queue progress remains only an optimization, not the
  source of recovery truth.

## Durable Deferred Initialization Evidence

- `CapabilityMonitor.has_verified_initialization` accepts a completed baseline
  only from schema-2 active status, digest-linked freshness bound to the exact
  evidence/capability/policy, and the matching signed checkpoint. Partial or
  mismatched provenance fails closed.
- The JSONL two-authority retry test now discards and reopens the service after
  a second-baseline failure, advances the clock, and resumes the suffix through
  public activation while preserving the first immutable trio. It passed in
  21.42 seconds; Ruff and `git diff --check` passed.
- The independent-host JSONL race now holds host A at the real capability-status
  conditional-write boundary, starts host B's public activation, then releases.
  Both hosts converge without deadlock on one persisted status/trio and can
  replay public activation without byte-divergent initialization; it passed in
  18.65 seconds. The test removes only the host trust linearizer so both
  independently composed hosts reach the real JSONL conditional-write race;
  durable store CAS and loser reload remain under test.
