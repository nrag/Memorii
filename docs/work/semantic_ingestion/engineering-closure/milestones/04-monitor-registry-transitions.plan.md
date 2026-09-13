# Capability Monitor And Atomic Status Transitions

- Parent WorkPlan: `docs/work/semantic_ingestion/engineering-closure/implementation.plan.md`
- Status: active
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

Freeze the R15 candidate revision and run independent specification,
correctness, and test reviews against that exact revision. Reconcile every
finding before deciding whether R15 is engineering complete.

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

Final focused monitor validation reports 37 passed in 83.83 seconds under
warnings-as-errors. It includes the 17-policy provider-failure inventory,
typed missing-window outcome, duplicate-window rejection, pause/outage
missing-window grace boundary, signed expiry with a provider that constructs a
healthy current window, checkpoint reuse across JSONL reconstruction, and the
real signed `sync_event` registry-byte lifecycle. The consolidated monitor,
provider composition, writer admission and migration, policy migration, and
bootstrap atomic-store gate reports 280 passed in 764.06 seconds. Ruff, scoped
first-party Pyright, and `git diff --check` are clean. The next action is to
freeze/push the exact revision and request exact-revision specification,
correctness and test reviews.

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
