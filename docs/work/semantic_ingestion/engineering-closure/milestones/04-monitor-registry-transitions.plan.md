# Capability Monitor And Atomic Status Transitions

- Parent WorkPlan: `docs/work/semantic_ingestion/engineering-closure/implementation.plan.md`
- Status: complete at `6224935e989f5880aba8afb1aa69d48d25e549a1`
- Base revision: `4c838477`
- Requirements: R15 primary; R08, R16 and R19 related
- Design baseline: `docs/design/semantic_ingestion_architecture.md` Section 5.6.1

## Observable Outcome

A production composed, server clock driven monitor evaluates one immutable
event level evidence window against an externally supplied typed policy. It
persists a digest bound decision and atomically changes an unsafe or stale
capability from `active` to `evidence_only`. Every normal semantic group commit
checks the exact capability status records named by its operation bindings in
the same storage CAS, so work captured before demotion cannot commit afterward.
Repeated ticks are idempotent. Fresh evidence after demotion never reactivates a
capability; recovery requires the existing separately authorized activation
path.

## Canonical Owners And Boundaries

- A cohesive module under `memorii.core.memory_evolution` owns typed monitoring
  policy, evidence window, metric decision, freshness and capability status
  contracts plus deterministic evaluation. It receives all thresholds,
  durations, alpha budgets, implementation fingerprints and timestamps; it
  defines no substantive defaults.
- `SemanticWriterAdmissionStore` owns capability status persistence and the
  atomic monitor transition. A demotion writes the status successor, immutable
  decision and writer admission successor in one conditional memory plane
  write. The writer successor retains the current activated ledger authority,
  changes runtime mode only to `evidence_only`, increments epoch and chains the
  predecessor digest.
- `SemanticIngestionAtomicStore.commit_or_reload_bootstrap_graph_group_v3`
  resolves operation capability bindings, validates each exact current status
  revision/digest and includes those record digests as write preconditions. The
  existing writer admission precondition remains mandatory.
- `ProviderMemoryService` exposes the production monitor tick and is composed
  with the monitor controller and protected clock. The tick runs without ingest
  traffic. The host scheduler calls this bounded tick like the existing
  clarification scheduler tick; no background thread or wall clock is added.
- The existing ID/fingerprint only `CapabilityRegistrySnapshot` remains byte
  compatible. Capability status is a separate mutable authority and does not
  reinterpret historical registry snapshots.

## Contract And Transaction Rules

Policies and windows are frozen typed values with closed shapes and canonical
digests. A window lists unique event and cluster identities, declared metric
membership, bounded observations, label/canary times, traffic state and label
pipeline state. Evaluation rejects missing gates, unknown metrics, duplicate or
cross assigned clusters, non finite values, implementation mismatch and family
alpha overflow. Every metric uses the declared sequential method and records
estimate, lower/upper bounds, alpha spent and disposition.

Freshness uses only supplied server time. Stale labels demote even when canaries
are fresh. Zero traffic does not pause label age. A declared traffic pause and
label pipeline outage may retain activity only inside their separately supplied
bounded grace intervals; expiry demotes. Warning records a decision but retains
active. Breach, invalid authority, stale evidence and insufficient required
evidence demote.

Status successors are monotonic and content addressed. `active` may transition
to `evidence_only`; identical retries reload the winner. The monitor cannot
transition `evidence_only` to `active`. A CAS loss reloads current authority and
either recognizes the identical decision or fails for reevaluation. No fallback
to legacy semantic writing is permitted.

## Validation Matrix

- Unit contract tests cover closed decoding, digest substitution, duplicate
  clusters, unknown/missing metrics, alpha overflow, non finite input, method
  fingerprint mismatch, warning and breach decisions.
- Fake clock boundary tests cover immediately before, exactly at and after label,
  canary, pause and outage deadlines, including zero traffic and healthy canary
  with stale labels.
- Repository tests cover active to evidence only, exact retry, CAS loss,
  persistence/reload, invalid automatic reactivation and unchanged state after
  rejected input.
- Production integration exercises `ProviderMemoryService` tick through the real
  memory plane, then starts or interleaves a normal group commit. Demotion must
  conflict stale writer/status preconditions and subsequent ingestion remains
  evidence only.
- Independent recomputation uses only the frozen event fixture and declared
  formulas; it imports neither monitor evaluator nor its serialization helper.

## Compatibility, Rollout And Rollback

Existing capability registry V2 bytes and historical records remain unchanged.
Hosts without approved monitoring inputs cannot claim an active monitored
capability. The implementation is additive until host composition supplies the
policy and initial status authority. Rollback leaves the writer in
`evidence_only`; it never restores legacy permissive behavior. Production keys,
policy values and qualifying evidence windows remain release inputs.

## Completion Contract

Focused unit and integration gates, Ruff and supported first party Pyright pass.
The production entrypoint ledger names a non test tick caller, status owner,
normal group commit caller and exact authority/precondition path. Independent
specification, correctness and test reviews of one frozen revision report
`remaining_validated_p1_p2: []`, no unresolved `changes_required`, and no
`blocks_approval`. Only R15 is promoted by this packet; R08, R16 and R19 remain
partial until every supported host root composes the status authority.

## Delegation And Ownership

`r15_monitor_preflight` is the required read only code mapper. One implementation
worker owns the monitor module, writer admission integration, atomic store
preconditions, provider service composition, focused tests and this packet until
handoff. The coordinator owns reconciliation, broad gates, reviews, closure
records, commits and pushes.

## Next Action

R15 is complete. Continue the parent campaign through the authenticated
observer/comparator packet; R08, R16 and R19 remain assigned to host closure.

## Exact-Revision Review Remediation Round 5 (2026-09-13)

Review of `34ae0a91d398c71f5f92fe07dfe1096af2a93450` confirmed four
bounded production gaps. The current candidate corrects them without changing
the public revocation wire format:

- the fixed reader factory now returns a read/lease-only object with no storage
  mutation method. A separate publisher-only storage capability owns object and
  mapping publication, and it is constructed only behind the registered
  authenticated publisher;
- the production-owned verifier now enforces the frozen parser ceilings and
  receipt/checkpoint descriptor constraints, including 64-bit integer maxima,
  string and signature bounds, array bounds, node/depth limits, and rejection of
  non-integer JSON numbers. Signed invalid artifacts rejected by acceptance are
  also rejected before production storage;
- the shared current-use lease translates only lock-acquisition failures.
  Exceptions raised by the protected group operation retain their original type
  and message;
- mapping publication writes until the complete canonical payload is durable,
  rejects zero or invalid progress, removes interrupted temporary files, and
  permits an exact retry rather than leaving an unrecoverable coordinate.

The focused production boundary suite reports 21 passing tests under
warnings-as-errors. It includes reader-capability absence, signed schema-parity
mutations, caller exception preservation, partial-write completion, zero-write
failure, and successful recovery. The consolidated monitor, acceptance-host,
and revocation-boundary gate reports 111 passing tests in 514.97 seconds under
warnings-as-errors. Ruff and first-party Pyright are clean. R15 remains
candidate complete pending fresh three-role review of the eventual exact
revision.

The first review of `046fb232` confirmed the runtime corrections and found one
governance-only stale binding: the production-entrypoint ledger still named the
removed reader mutation method. The ledger now records the registered publisher
factory, its authenticated `publish_verified` boundary, and the separate
publisher-only storage owner. The next action remains to freeze this
documentation correction and complete fresh exact-revision reviews.

## R15 Compatibility And Trust-Linearization Remediation (2026-09-13)

The candidate now closes the final confirmed review gaps without changing
registry bytes:

- capability status, monitor decision, and evidence freshness have explicit
  V1/V2 digest domains. Both pre-field V1 and the e0/c9 extended-but-still-V1
  wire shapes validate against their exact original V1 preimage before
  deterministic upcast; only newly emitted records use explicit V2;
- an actual pre-checkpoint JSONL batch containing V1 status, decision and
  freshness payloads/digests reopens successfully. The legacy active status
  has no authorization checkpoint and its V1 freshness lacks transition
  instants, so the missing-window path atomically demotes it and advances the
  writer to `evidence_only` rather than reconstructing grace or admitting
  learned work;
- an actual e0-era JSONL batch containing the extended V1 status, decision,
  freshness and authorization-checkpoint shapes reopens under their V1
  digests. It continues monitoring into an explicit V2 successor and retains
  both status and checkpoint preconditions for group admission;
- group commit authority uses a host-owned current-use lease held from live
  deployment-authorization verification through the final writer validation
  and conditional group write. A deterministic two-thread production ingress
  proof pauses after lease acquisition and before the group CAS, shows a
  concurrent revocation cannot publish while that CAS is paused, then proves
  the completed revocation fences and demotes every later group attempt;
- the external evidence-provider boundary catches every ordinary `Exception`
  (never `BaseException`) and converts it to complete-inventory typed provider
  failure. Signed public-factory coverage includes `RuntimeError`, `KeyError`,
  and a custom ordinary exception.

Evidence on the dirty candidate:

- `PYTHONPATH=memorii .venv/bin/pytest -q -W error
  memorii/tests/unit/core/semantic_ingestion/test_capability_monitoring.py`
  from repository root: 47 passed in 108.42 seconds;
- targeted Ruff over the six changed runtime/test files: clean;
- `../.venv/bin/pyright --pythonpath ../.venv/bin/python` from `memorii/`:
  0 errors, 0 warnings, 0 informations;
- `PYTHONPATH=memorii .venv/bin/python -m py_compile` over the five changed
  runtime modules and `git diff --check`: clean.
- the consolidated affected-family gate covering capability monitoring,
  provider composition, writer admission, writer migration, policy migration,
  and bootstrap graph atomic storage: 290 passed under warnings-as-errors in
  1048.94 seconds.

The sole next action is to commit and push this candidate, then obtain fresh
specification, correctness, and test reviews of that exact revision. R15
remains `candidate_complete_pending_exact_revision_review` until all three
reviews converge.

## Exact-Revision Review Remediation Round 2 (2026-09-13)

The review of `88a20765` confirmed two production gaps and six proof gaps. The
coordinator corrected them as one bounded R15 revision:

- a signed baseline now binds both the monitoring-policy digest and the exact
  initial evidence-window digest. Service construction revalidates the closed
  policy/window models, independently evaluates freshness and every metric,
  rejects stale, insufficient, breached, future, unknown-metric or
  implementation-mismatched input, and atomically persists the initial
  freshness record with the active status;
- `ProviderMemoryService.reconcile_memory_evolution` invokes the bounded
  monitoring scheduler before the existing clarification and evolution
  reconciliation work. A fake-clock test advances a healthy signed baseline to
  expiry without any ingress call and proves atomic demotion with no source,
  accepted-operation or graph-group publication;
- the negative matrix now covers malformed authorization, forged signature,
  signed wrong target, expiry, forged policy binding, stale initial evidence,
  exact before/at/after label, canary, pause and outage boundaries, zero
  observations, insufficient clusters, implementation mismatch, unknown
  metric, nonfinite values and post-demotion ingress;
- exact retry proof now compares memory-plane revision, every record digest and
  writer epoch. The real graph race performs another normal ingress after the
  monitor wins and proves no group primary can appear;
- the architecture-byte change is propagated through the CTV authority,
  equal-version decision, lifecycle checker, structural known-answer vector,
  checker identities, workflow pins, tests and static-tooling documentation.

Verification on the dirty round-2 candidate:

- monitor plus equal-version decision: 63 passed under warnings-as-errors;
- provider service and semantic provider composition: 86 passed under
  warnings-as-errors;
- admission, migration, monitor and bootstrap atomic-store family: 229 passed
  under warnings-as-errors;
- CTV gate reports 56 schemas and 249 enum rows; lifecycle provenance reports
  six accepted and 41 rejected witnesses; CGS structural self-test passes;
- CTV PR-gate and independent reference-compiler family: 279 passed under
  warnings-as-errors.

The next action is to run Ruff, scoped first-party Pyright and diff checks,
freeze and push the revision, then obtain the required exact-revision
specification, correctness and test reviews. R15 remains candidate complete
until those reviews converge.

## R15 Live-Trust Remediation Complete (2026-09-13)

The current exact-revision review found that the bounded scheduler only
evaluated windows returned by the host and that signed capability-baseline
authority was checked only during composition. The active remediation now has
the policy-owned scheduler inventory, durable-freshness deadline evaluation on
missing windows/provider failures, rejection of unknown/duplicate/oversized
provider output, and a distinct deployment-artifact live-current-trust port
that combines canonical artifact verification with a host signer lifecycle,
revocation and compromise decision. `VerifiedCapabilityMonitoringAuthority`
retains the raw artifact and live verifier; `ProviderMemoryService` invokes it
before monitor work and authenticated learned ingress, atomically demoting the
capability through the existing writer fence when trust fails.

The remediation durably binds a typed authorization checkpoint containing the
artifact/raw digests, approval, expiry, signer/key, snapshot and epoch with
the active status. Group commit retains that checkpoint as a CAS precondition
and invokes the host-linearized current-trust guard before its storage write;
a false result uses the normal atomic monitor demotion and writer fence. The
real signed `sync_event` lifecycle proves one persisted group, exact retained
normalization-authority V2 registry bytes through demotion and JSONL reopen,
and guard-driven revocation without a deadlock. Scheduler proof covers missing
windows (`missing_window`) and provider exceptions across 17 active policies
(`provider_failure`).

Exact-review remediation validation reports 43 passed in 86.80 seconds under
warnings-as-errors. It adds signed public-factory coverage for direct supplied
healthy evidence after revocation and malformed provider shapes (non-tuple,
non-window, unknown, identical duplicate and oversized); each malformed poll
is retained as a diagnostic `provider_failure` and evaluates the full policy
inventory at its deadline. The >16 inventory proof now composes 17 signed
capability authorities with one failing provider. The provider-composition
suite reports 45 passed in 302.40 seconds, and the preceding consolidated
monitor, provider composition, writer admission and migration, policy
migration, and bootstrap atomic-store gate remains 280 passed in 764.06
seconds. Ruff, scoped first-party Pyright, and `git diff --check` are clean.
The next action is to freeze/push the exact revision and request exact-revision
specification, correctness and test reviews.

## Exact-Revision Review Remediation Round 3 (2026-09-13)

Review of `8f5a969c` produced one confirmed production bypass, two confirmed
test-depth gaps, one unsupported timing claim and one disputed integration
request:

- **Confirmed P2 / architecture:** status-only active initialization remained
  possible below the signed composition. The coordinator removed the public
  initializer, made the internal persistence helper require a freshness record,
  and changed writer admission to accept exactly one validated initial
  freshness record plus one digest-bound active status in the same CAS. A
  direct governed status-only write now proves rejection and no publication.
- **Confirmed P2 / compatibility:** the signed lifecycle test now freezes a
  `CapabilityRegistrySnapshot` canonical byte representation and digest before
  activation, then proves exact equality after monitoring, demotion and JSONL
  reopen. Mutable monitoring state remains outside the immutable registry.
- **Confirmed P2 / independent verification:** the standalone standard-library
  oracle and frozen raw fixture now reconstruct eligible events, unique cluster
  membership, label-window selection, freshness, implementation binding,
  metric count, estimate/bounds, alpha, warning/breach disposition, action and
  reasons from event-level inputs. It still imports no Memorii code.
- **Unsupported / operability:** the reviewer combined multiple expensive
  families and interrupted them after five minutes. The CI-owned CTV PR-gate
  family run in isolation exits normally with 20 passed in 224.18 seconds,
  inside its five-minute workflow budget; no leaked subprocess or product
  correction was reproduced.
- **Disputed P2 / multi-operation public fixture:** the ordinary supported
  source fixture produces one default graph operation, and the real public race
  proves the status precondition on that normal group plus later ingress. The
  store-level shared-capability test supplies two operation bindings and proves
  one deduplicated status precondition. Attempts to manufacture a second fact
  changed source-normalization authority rather than exercising an ordinary
  supported root. The coordinator did not weaken source validation to satisfy
  a test shape. Fresh review must decide whether the existing public-path plus
  typed-store boundary is family-complete for R15 or identify a valid canonical
  multi-operation fixture owned by the graph contract.

Focused remediation verification passes: 34 monitor cases under
warnings-as-errors, 20 isolated CTV PR-gate cases in 224.18 seconds, Ruff,
diff-check and scoped first-party Pyright with zero diagnostics. The next action
is to freeze and push this remediation, then rerun all three exact-revision
reviews. R15 is not promoted before review convergence.

## Exact-Revision Review Remediation (2026-09-13)

The first review of `a8ed3fa1` found four production-composition defects and
five proof gaps. The coordinator confirmed them and implemented one converged
remediation:

- the default built-in graph execution now resolves the registered proposal
  capability, requires its active status, and seals the exact status, policy,
  freshness, route, registry and arbitration coordinates into every accepted
  operation; the store requires bindings for all accepted operations and
  deduplicates shared capability coordinates across a multi-operation group;
- `VerifiedCapabilityMonitoringAuthority` is issued only after the existing
  production deployment-artifact verifier authenticates a signed
  `capability_baseline` authorization whose target digest and capability
  fingerprint match the closed monitoring policy. The public arbitrary-status
  initializer was removed;
- `build_provider_memory_service_from_env` now composes verified monitoring
  authority and the host evidence provider. `process_capability_monitoring` is
  the bounded no-ingest scheduler entrypoint;
- future authority timestamps fail closed, pause and label-pipeline expiry are
  evaluated independently, and a repeated evidence/outcome coordinate reloads
  the prior decision while crossing a freshness boundary creates a new
  evaluation and demotion;
- a real default built-in graph race proves the status digest is in the group
  CAS, demotion blocks the stale publication, no group primary is written, and
  subsequent durable state remains `evidence_only`; a standalone
  standard-library oracle reads a frozen raw vector and recomputes the numeric
  result without importing monitor code.

Verification on the dirty remediation candidate:

- monitor suite: 17 passed under warnings-as-errors;
- provider service and semantic provider composition: 102 passed under
  warnings-as-errors;
- consolidated writer admission, policy migration, writer migration, monitor
  and bootstrap atomic-store gate: 211 passed under warnings-as-errors;
- Ruff, `git diff --check`, and scoped first-party Pyright: clean, with Pyright
  reporting 0 errors, 0 warnings and 0 informations.

The next action remains freezing this revision and running the three required
independent reviews. R15 is not promoted until those reviews converge.

## R15 Writer Progress (2026-09-12)

Implemented a bounded local R15 vertical slice without changing immutable
`CapabilityRegistrySnapshot` bytes:

- `memorii.core.memory_evolution.capability_monitoring` owns closed,
  digest-bound policy, sequential manifest, gates, evidence window, freshness,
  metric decision, decision and mutable status contracts. All values are
  supplied; it has no policy or clock defaults. Decimal strings reject
  nonfinite values before evaluation.
- `CapabilityMonitor.tick` uses the supplied protected clock, treats stale
  labels as stale even with a fresh canary, applies separate pause/outage
  grace deadlines, rejects duplicate/cross-assigned clusters, persists no
  automatic reactivation, and turns an unsafe/stale active status into
  `evidence_only`.
- `SemanticWriterAdmissionStore.demote_capability_monitor` writes the status
  successor and decision with a writer-admission successor in one CAS. The
  epoch advance invalidates all pre-demotion writer bindings.
- `SemanticIngestionAtomicStore.commit_or_reload_bootstrap_graph_group_v3`
  now loads sealed capability binding coordinates, rejects a non-active or
  substituted status revision/digest/policy/freshness record, and retains every
  loaded status digest as a `RecordDigestPrecondition` in its group CAS.
- `ProviderMemoryService.run_capability_monitor_tick` is the bounded production
  callable and uses the service's protected clock; it performs no sleep or
  background work. `initialize_capability_monitor_status` requires an explicit
  supplied policy and freshness digest.

Local proof on the dirty R15 candidate:

- The capability-monitor suite passes 12 cases. It covers closed policy and
  evidence contracts, family alpha and cluster rejection, fake-clock freshness,
  warning/breach behavior, verified-writer demotion, no automatic reactivation,
  JSONL restart, injected monitor CAS loss, and independent recomputation of the
  declared confidence sequence.
- A real `ProviderMemoryService.sync_event` path now carries a nonempty sealed
  `OperationCapabilityExecutionBinding`. The test interleaves the production
  monitor after the group commit has retained the prior status digest and
  before its storage CAS. The CAS rejects publication, persists the demotion,
  and a fresh JSONL reader observes `evidence_only` with no group primary.
- The consolidated admission, migration, monitor, and bootstrap atomic-store
  gate passes 178 tests under warnings-as-errors.
- Ruff, `git diff --check`, `py_compile`, and the repository scoped Pyright gate
  pass; Pyright reports `0 errors, 0 warnings, 0 informations`.

The implementation candidate now satisfies the deterministic R15 engineering
behaviors. Product policy approval, real evidence, and production signatures
remain release inputs. R15 stays **candidate complete** until all three exact-
revision reviews converge. R08, R16 and R19 remain partial because configured
host activation and deployment-authority consumption are later packets.

## Installed Monitoring Authority Remediation (2026-09-13)

The public factory now has a strict installed monitoring configuration path.
It accepts only operator-owned absolute paths for the signed deployment
authorization, closed monitoring policy, baseline evidence, bounded ongoing
evidence source and independent revocation-reader root, together with a fixed
Ed25519 public-key map. No private key is accepted or retained. The builder
verifies the exact signed artifact before it creates the opaque monitoring
authority; an absent configuration leaves the service with no configured
capability, while malformed configuration fails closed. Direct, factory,
filesystem and Hermes production-capture composition roots propagate the same
verified configuration into their canonical services.
The installed revocation reader owns a shared POSIX `flock` at a fixed
revocation-root coordinate through the durable group CAS and treats a present
malformed revocation coordinate as non-current. Its canonical publisher takes
the exclusive lock and uses durable publish-if-absent hard-link publication:
byte-identical retries are idempotent and different coordinates are conflicts.

Focused proof: the capability-monitor suite passes 59 cases under
warnings-as-errors in 159.21 seconds. The new installed path proves valid
activation and rejection of unknown-key, tampered, expired and revoked
authorization material, path substitution, the no-configuration state, and
direct/factory/filesystem/Hermes root propagation. A forked child proves an external
publication blocks while a current-use lease is held, then completes after the
lease; it also proves byte-identical retry and conflicting-coordinate rejection.
Ruff, JSON and diff checks pass. Scoped first-party Pyright reports `0 errors, 0 warnings and 0
informations` using the repository virtual environment. The next action is to
run the provider/root composition suites, then freeze this candidate for
exact-revision review.

## R15 Historical Ingress Proof Correction (2026-09-13)

The historical compatibility tests now exercise their stated public path rather
than an internal precondition helper. Both write exact historical JSONL batch
envelopes, reopen them, compose a signed monitoring authority and call
`ProviderMemoryService.sync_event` through the built-in graph host and group
CAS:

- a pre-checkpoint V1 active status reaches the group boundary, is denied for
  the unavailable checkpoint with no accepted operation, effect or group
  primary, then the policy-owned scheduler atomically persists the V2
  `evidence_only` successor;
- an extended-V1 status with the exact retained typed checkpoint reaches a V2
  monitor successor, then public ingress writes exactly one group. The final
  group CAS captures both the exact V2 status-record and checkpoint-record
  digests as preconditions, and a fresh JSONL reader validates the V2 status.

The monitor module keeps a matching historical active status readable during
signed service composition only when its persisted freshness (and, when
present, checkpoint) record exactly matches the retained digest. It does not
invent a new baseline. Public group admission still rejects missing or stale
checkpoint authority, and the scheduler remains the only transition path.

Focused proof from repository root:

- `PYTHONPATH=memorii .venv/bin/pytest -q -W error
  memorii/tests/unit/core/semantic_ingestion/test_capability_monitoring.py::test_pre_checkpoint_v1_jsonl_restart_upcasts_and_fences_legacy_active_state`:
  1 passed in 26.33 seconds;
- `PYTHONPATH=memorii .venv/bin/pytest -q -W error
  memorii/tests/unit/core/semantic_ingestion/test_capability_monitoring.py::test_extended_v1_jsonl_restart_preserves_v1_preimages_and_group_authority`:
  1 passed in 37.28 seconds;
- from `memorii/`, `.venv/bin/pyright --pythonpath .venv/bin/python
  memorii/core/memory_evolution/capability_monitoring.py
  tests/unit/core/semantic_ingestion/test_capability_monitoring.py`: 0 errors,
  0 warnings, 0 informations; `git diff --check` is clean.

The full capability-monitor suite passes 59 cases under warnings-as-errors in
159.21 seconds. The consolidated capability-monitor, provider-composition,
writer-admission, writer-migration, policy-migration and bootstrap-graph
atomic-store gate passes 302 cases under warnings-as-errors in 1096.26 seconds.

## R15 Revocation Publisher And Lease-Expiry Remediation (2026-09-13)

At this historical remediation revision, the installed production command
temporarily reached a mutation method on the revocation reader. Round 5
supersedes that ownership: `memorii-semantic-ingestion-revocation-publish` now
reaches `InstalledProductionRevocationPublisher.from_fixed_configuration`, then
the authenticated `_SerializedProductionRevocationPublisher.publish_verified`
boundary, and finally the separate publisher-only
`_FileProductionRevocationPublisherStorage.publish_revocation_evidence` owner.
The fixed reader exposes only current-read and shared-lease behavior. Both the
acceptance verifier and the independent production verifier validate exact
schema, parser, digest, signature, join, and history constraints before the
publisher fsyncs immutable content-addressed objects and publishes the mapping
under the exclusive lock. Failed or partial publication cannot expose a
mapping; identical retries are idempotent and conflicts fail closed. Current-use
samples the protected host clock after acquiring its shared lease, making expiry
while waiting unavailable before group CAS.

The sole next action is to run the focused installed publisher and monitoring
proof, then freeze and push the candidate for exact-revision reviews.

## R15 Protected-Clock And Publisher Failure Delta (2026-09-13)

Installed monitoring composition now passes one host `now_provider` from the
factory into the fixed revocation reader. The post-lease current-use sample
therefore never falls back to an ambient wall clock. Filesystem, Hermes, and
canonical capture roots propagate that same clock to their provider service.

Focused proof on the uncommitted candidate:

- a genuinely Ed25519-signed artifact issued at T0 and expiring at T1 is
  rejected at protected T2 without status or checkpoint publication (1 passed,
  5.72 seconds);
- each direct, factory, filesystem, and Hermes root invokes the public monitor
  scheduler and has one durable active status plus matching checkpoint (1
  passed, 5.53 seconds);
- missing receipt, noncanonical/tampered receipt, and conflicting receipt
  join each leave no current mapping and accept the repaired exact retry (3
  independently invoked cases passed, about 15 seconds each);
- a recomputed-checksum JSONL journal with a forged V2 status checkpoint,
  decision evaluation kind, or freshness timestamp rejects signed service
  construction before accepted-operation, effect, or graph-group publication
  (3 passed, 11.43 seconds).

The malformed pre-field and extended-V1 journal cases now reject forged
status-checkpoint, decision-evaluation-kind, and freshness-timestamp fields
before signed service ingress. An installed initial-activation race pauses the
status CAS after lease entry, proves revocation publication remains blocked,
then proves the live service demotes and subsequent installed construction is
fenced. Focused checks for those deltas pass. The complete R15 monitor suite
passes 74 cases under warnings-as-errors in 245.87 seconds. The installed CLI
help path, Ruff, scoped first-party Pyright, JSON validation, and diff checks
pass.

The consolidated capability-monitor, provider-composition, writer-admission,
writer-migration, policy-migration and bootstrap-graph atomic-store gate passes
317 cases under warnings-as-errors in 1186.97 seconds.

The sole next action is to freeze and push this candidate, then obtain fresh
exact-revision specification, correctness and test reviews.

## R15 Fixed Revocation Publisher Remediation (2026-09-13)

The installed `memorii-semantic-ingestion-revocation-publish` command no
longer accepts a caller-selected storage root. It reads one fixed
platform-data configuration file containing only the absolute reader root and
an Ed25519 public-key map. The configuration rejects symlink or writable
ancestry and contains no private key.

Before the production reader creates either immutable object or the current
mapping, the command invokes acceptance's independently owned production
revocation verifier with its current-reader check disabled. That verifier
checks the pinned registered schemas, canonical bytes, exact digest and
signature preimages, fixed signer coordinate, Ed25519 signature, receipt and
checkpoint join, monotonic epoch and time rules, and any retained checkpoint
history. The same verified byte strings are then handed to the core reader,
eliminating file replacement between verification and publication.

Focused proof now creates real Ed25519 signed registered receipt/checkpoint
artifacts and proves successful publication plus failed missing, noncanonical
tamper, forged signature, unknown-key, extra-field and conflicting-join
inputs with no mapping; `--root` is rejected by the public CLI parser. The
activation race now signals exclusive-publication attempt before lock
acquisition and waits for the status-CAS release. The forked interprocess test
signals attempted publication before entering the shared-lock contention and
proves that no mapping appears until the lease releases, without timing-based
negative waits.

Focused validation on the dirty candidate:

- `PYTHONPATH=memorii .venv/bin/pytest -q -W error
  memorii/tests/unit/core/semantic_ingestion/test_capability_monitoring.py -k
  'revocation_publish_cli or interprocess_linearized or initial_activation_holds
  or forged_v2_monitor_wire_fields or forged_legacy_monitor_wire_fields'`:
  18 passed in 57.78 seconds;
- targeted Ruff and scoped Pyright for the publisher and monitor suite: clean,
  0 errors and 0 warnings.

The forged V1/V2 proof now begins from a checkpoint-bound signed composed
service, emits the genuine decision and freshness state, mutates only the
selected persisted record, recomputes only the JSONL checksum, and exercises
the public construction or scheduler path. Status and freshness fail during
composition; the scheduler deliberately does not reload historical decisions,
so that target is rejected by its canonical persisted-contract decoder while
the scheduler is also exercised. All paths assert zero accepted operations,
effects and group publications. The nine target/wire cases pass in 100.45
seconds.

Final candidate validation after the discriminating forged-wire rewrite:

- `PYTHONPATH=memorii .venv/bin/pytest -q -W error
  memorii/tests/unit/core/semantic_ingestion/test_capability_monitoring.py`:
  77 passed in 261.08 seconds;
- targeted Ruff is clean and scoped Pyright from `memorii/` reports 0 errors
  and 0 warnings;
- CLI `--help`, `git diff --check`, and binding-ledger JSON parsing pass.

The sole next action is to freeze and push this candidate, then obtain
independent specification, correctness, and test reviews against that exact
revision.

## R15 Isolation And Storage Remediation (2026-09-13)

The revocation publication trust boundary is now correctly split. The public
`memorii-semantic-ingestion-revocation-publish` command is owned by
`acceptance.revocation_cli`; its fixed, public-only acceptance configuration
selects the trusted Ed25519 keys and one serialized storage configuration
passed identically to both reader and publisher bridges. Acceptance rejects a
split reader/publisher configuration before either path is opened, then verifies registered canonical receipt/checkpoint
schemas, digest and signing preimages, signatures, timestamp/epoch/history,
and the receipt/checkpoint join before it passes those exact bytes through the
registered production publisher bridge. Production owns only the opaque object
and current-mapping transaction and contains no static or dynamic acceptance
import. Import-boundary tests now detect literal `import_module` and
`__import__` bypasses.

The production revocation root, lock, object and mapping paths reject
symlinks, group/world-writable or foreign-owned existing coordinates; missing
private leaves are created with mode 0700. The reader applies this validation
before every read, lease, lock and publication. Tests prove insecure roots and
ancestors fail before a mapping is visible. The interprocess lease proof now
uses a child nonblocking exclusive `flock` probe that reports `EWOULDBLOCK`
while production holds the shared current-use lease, followed by the real
blocking publisher and immutable retry/conflict checks.

Persisted monitoring decisions are replay/idempotency records read only by the
policy scheduler; normal `sync_event` group authorization consumes the current
status and authorization checkpoint instead. The canonical scheduler reader
rejects a malformed retained decision and atomically writes the normal
`evidence_only` status/writer successor before returning the corruption error.
A real `sync_event` that had previously committed a group then fails closed
with `graph_transaction_authority_unavailable` and creates no accepted
operation, effect or group. This replaces the previous overstatement that
ingress itself decoded retained decisions.

Focused proof on the candidate reports 10 passed under warnings-as-errors for
the acceptance bridge, valid/forged signed CLI publication, digest-consistent
but join-mismatched checkpoint rejection before object/mapping creation,
byte-identical idempotent retry, secure-path rejection, the OS lock boundary,
and scheduler/ingress persisted-decision behavior.

Final validation on this bounded delta:

- `PYTHONPATH=memorii .venv/bin/pytest -q -W error
  memorii/tests/unit/core/semantic_ingestion/test_capability_monitoring.py
  memorii/tests/unit/acceptance/test_production_revocation_boundary.py
  memorii/tests/unit/acceptance/test_acceptance_host_runtime.py`: 93 passed in
  361.17 seconds;
- targeted Ruff: clean; scoped first-party Pyright: 0 errors, 0 warnings and
  0 informations; acceptance bridge modules compile successfully;
- binding-ledger JSON parsing and `git diff --check`: clean.

## R15 Coordinator-Review Refinement (2026-09-13)

The acceptance CLI now has exactly one `storage` configuration member. It
passes that same object to both registered bridges; legacy or mismatched
`reader`/`publisher` configurations are rejected before either root can be
created or receive a mapping. The focused acceptance publisher test proves
both configured roots remain unpublished.

The retained-decision proof now starts with a real checkpoint-bound service
that successfully calls `sync_event` and publishes one group. When the
canonical scheduler rereads a malformed retained decision, the monitor first
uses its existing untrusted-authority demotion path to persist the
`evidence_only` writer/status fence, then reports the corruption. A second
real `sync_event` returns `graph_transaction_authority_unavailable`, and exact
accepted-operation, effect and group counts remain unchanged.

Focused validation after this refinement reports 10 passed under
warnings-as-errors, including malformed and digest-valid identity-substituted
replay decisions. The two retained-decision variants pass in 92.24 seconds.
Targeted Ruff is clean and scoped
first-party Pyright reports 0 errors and 0 warnings.

The sole next action is for the coordinator to freeze this candidate and
obtain the required exact-revision specification, correctness and test
reviews.

## R15 Exact-Review Provisioning And Durability Remediation (2026-09-13)

The configured revocation root is now provisioning-only: it must already
exist as a secure, operator-owned private directory before reader construction
or installed monitoring composition. Runtime may create only secure children
under that root. Missing configured roots fail before status/checkpoint
activation or group mutation. First creation of `objects` or `current` fsyncs
the parent/root directory entry before child use; object links and current
mapping links retain their own directory fsyncs. The first-publication proof
records root-before-child fsync ordering, exact retry re-fsyncs both object
coordinates and the current mapping directory before success, and recovery
from surviving objects plus an absent mapping does the same before returning.

Acceptance CLI negatives now use valid signed inputs and prove that symlinked
config files, writable config files, and writable containing directories fail
before object/mapping publication. Its default config coordinate is absolute,
fixed under platform data, and unaffected by an environment variable. The
serialized import scanner now also recognizes literal
`importlib.import_module(...)` and `builtins.__import__(...)` calls.

Focused validation after the remediation reports 20 passed under
warnings-as-errors for installed monitoring, publisher, first/recovered
publication durability, production-reader and import-boundary proofs. Ruff,
scoped Pyright, acceptance module compilation, JSON and diff checks pass.

Final candidate validation after this exact-review remediation:

- `PYTHONPATH=memorii .venv/bin/pytest -q -W error
  memorii/tests/unit/core/semantic_ingestion/test_capability_monitoring.py
  memorii/tests/unit/acceptance/test_production_revocation_boundary.py
  memorii/tests/unit/acceptance/test_acceptance_host_runtime.py`: 104 passed
  in 496.00 seconds;
- focused static validation remains clean: Ruff, scoped first-party Pyright,
  acceptance module compilation, binding-ledger JSON and diff checks.

The sole next action is for the coordinator to freeze this candidate and
obtain exact-revision specification, correctness and test reviews.

## R15 Final Publisher And Trust-Outage Delta (2026-09-13)

The registered production publisher now independently decodes both exact
canonical revocation artifact shapes, recomputes their registered CTV digests,
and verifies their Ed25519 preimages against fixed production public keys before
any object or mapping write. The reader exposes only current-read and lease
operations. Production trust-port failures are unavailable authority outcomes,
so the existing service path atomically demotes the capability before later
group admission. Durability proof records each child mkdir, root fsync, and
link visibility boundary: root fsync follows each child creation and precedes
the first link under that child.

The sole next action is for the coordinator to freeze this candidate and
obtain exact-revision specification, correctness and test reviews.
