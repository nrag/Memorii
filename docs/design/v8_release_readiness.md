# Memorii v8 release readiness

This design covers the remaining first-production-release gaps for the local,
single-active-owner installation. It extends the
[durable runtime design](durable_execution_and_solver_runtime.md) with concrete
entrypoints, recovery custody, bounded reads and release evidence. The
[design WorkPlan](../work/v8-release-readiness/design.plan.md) records the code
baseline, decisions and review. v8 stays the default. The existing 11-second
verified acquisition budget stands.

## Scope and sequence

An installation owner must be able to get from a verified artifact to durable
capture and restart recall in Pi and OpenClaw, operate it with documented
controls, and recover it when the original host is lost. Retain existing
Hermes behavior at shared storage, authorization and ontology boundaries.
Support the pinned dedicated Pi and local OpenClaw session surfaces. Shared
channels, remote sidecars, distributed authority, automatic failover and
unbounded multiwriter operation are outside this design.

| Supported host | Required installed path |
| --- | --- |
| Pi, version pinned by the host asset | Exact session/branch binding, user capture and recall, signed resume, bounded task/solver state and explicit paging, fork/settle and restart behavior. |
| OpenClaw, version pinned by the host asset | Exact local gateway session, user capture and recall, signed resume, bounded task/solver state and explicit paging. Real CLI tests deny forwarded/system or unbound sources. |
| Hermes | Use the pinned installed profile from its release recipe. Prove managed task mapping, typed state and checkpoint/next-step through real callbacks, protected memory/catalog reads, no-key and advertised model bindings, and restart. |

Each release root preserves candidate versus committed state, signed delivery
holds and explicit action reconciliation. Any unsupported production root
within the governing host contract requires an approved scope change.

1. Make the supported artifacts installable and safe to distribute. Ship one
   operator-provisioned managed journey and make it exercisable in CI.
2. Close independent recovery custody and rehearse same-installation and
   replacement-host restore, revocation, interrupted recovery and rollback.
3. Bound native capture/recall, host latency and managed ontology reads without
   weakening signed storage or release authorization. Dependency and bounded
   query work can proceed independently of recovery implementation.
4. Freeze and qualify the exact artifacts. Require separate evidence of
   agent-task benefit before advocating critical adoption. The comparative
   benchmark design follows release hardening, as previously agreed.

The installed permissions, private operator files, redaction and SDK alert
fixes remain regression requirements. Physical erasure is limited to already
governed whole, isolated custody with a complete copy inventory and receipt.
Qualify the supported action before claiming it. Keep logical forget and
retention distinct. Broad formatting, speculative refactors, sealed startup
and historical rollout breadth for nonexistent public installations are
outside this design.

## Installed operator journey and distribution

Provide an installed owner entrypoint through `memorii-operator` that initializes
a private root, provisions a task using the typed runtime command/publication
owner, enrolls one exact `(credential, task, native source)` binding, and starts
the existing managed sidecar on loopback in the foreground. A normal process
supervisor owns restart and stop. Reuse `memorii-consume --managed --drain`
and current status, doctor, mode, backup and grant commands. The runbook starts
with a wheel and the version-pinned host asset, uses only supported entrypoints
and includes a rollback and recovery transcript. Status must expose readiness,
verified generation, effective mode, pending/held counts and age, last verified
backup age, custody state and installed artifact identity without source text,
credentials or reusable grant material.

Reuse `RuntimeCommandService` or its canonical owner-authorized task creation
method after tracing the current authority. Preserve stable operation IDs and
command receipts. Do not reproduce the test fixture's direct task-row insert.
Serialize owner enrollment with existing control-owner fencing. A stable
operation ID is bound to the exact requested enrollment. Retry returns the
same committed task/binding, or rejects changed inputs. A raw host secret is
issued only to an operator-selected owner-only file via exclusive creation and
atomic publication. After a crash before credential handoff, explicitly revoke
or rotate the unfinished credential and use fresh issuance. Retain IDs,
digests and custody state for diagnosis. Admission and release are unavailable
while enrollment is incomplete.

Persist a typed read authorization owned by the grant registry, bound to
installation, selected generation, host credential identity, principal,
exact task and source, epoch and finite expiry. The installed resolver uses
the authenticated credential and verified route scope, and rechecks the epoch
at release. Implement that binding at the state, native recall and any other
advertised sidecar roots that share the current principal-only callback.
Restrict command grants to the required operations and exact source. Explicit
renewal, rotation and revocation advance existing authority. Only the
operator may mint a task, credential, read scope or grant. Wrong or unavailable
scope yields content-free denial. Reuse private file and diagnostics code.

The sidecar transport is the final release owner. A typed release permit binds
the bounded bytes to exact credential/task/source, verified publication and
current grant and suppression coordinates. Revalidate immediately before each
nonblocking protected write to the socket, ordered with cooperating revocations
under current owner locks. A stalled socket waits outside those locks.
Revocation after assembly and before the first protected byte yields zero
content. Already accepted socket bytes are outside recall. Recheck before
sending any remainder and abort an incomplete response after denial. Apply
this ordering to every protected advertised route.

Ship the base wheel and separate versioned, digest-bound Pi and OpenClaw host
assets with their exact dependency locks. Docker images are validation
environments outside the v8 distribution scope, as approved by the owner on
2026-11-27. The validation recipes must install the same wheel and verify the
host member digests against the packaged manifests. The current `local` profile is
excluded from the supported release unless its entire resolution and model
loading path are qualified. Remove the affected profile from distributed
artifacts and instructions if retaining it would ship the vulnerable pin.
Prove every advertised provider/Hermes profile still functions with its exact
dependencies. A stack necessary for an advertised path must be fixed or its
support scope explicitly narrowed before freezing artifacts. In a retained NLP
profile require a safe resolved version, verify trusted model manifests by
digest before load, and reject unregistered model assets. A single historical
advisory fix version does not qualify the current dependency set. Scan the
wheel's resolved closures, SDK tarball, shipped host assets and model assets
by digest, and record SBOM, build provenance, scan and supported platform/profile
manifest. No unresolved Critical or High finding in the supported closure
passes release review without a specific documented disposition and owner.
[PyTorch advisory](https://github.com/pytorch/pytorch/security/advisories/GHSA-53q9-r3pm-6pq6)

## Recovery authority and cutover

### Independent authority

Treat the backup as a historical data snapshot. Its decrypted control
participant provides source proof only. The current backup writes metadata
stubs beside the archive. Replace that mechanism for managed recovery with the
durable runtime design's signed and separately encrypted
`InstallationControlRecoveryBundle` and independently retained typed
`InstallationRecoveryAnchor`. A backup may reference the recovery coordinate.
It cannot point the verifier to an authority it is allowed to trust.

The bundle carries the complete typed control snapshot and journal, trust
history, registered participant inventory, current deny state and finalized
tuples. Name each validated member in a closed manifest with owner, schema,
size, digest and exact snapshot coordinate. Include the owners' sealed
suppression journals and terminal denials from read, command, source-release,
writer or provider authority where those owners participate. Neither reusable
credentials/grants nor private keys are restored into the serving registries.
Validate the exact owner inventory against installed composition, with a
closed unsupported state for ambiguity or missing required members. Sign with
a recovery-specific purpose using existing canonical digest/signature
conventions. Bind installation and repository identity, control revision,
signed journal ordinal and tip, authority epoch, current signer fingerprint,
trust-registry digest and bundle digest. Distinguish control revision from
journal position. Keep decryption and signing-key custody separate. Add a
read-only public historical verifier behind the key owner. Supplied private
signer material or authorized rotation must match the current trust policy
before creating a new publication.

The owner registers an independent recovery custody directory during setup,
outside the installation and backup trees and under a separate failure domain.
For this release use an operator-managed, single-writer POSIX filesystem
supporting local locks, file and directory fsync and atomic rename. Qualify two
failure domains and reject unsupported mounts before calling recovery healthy.
A content-free currentness record at the independent custodian binds the
exact registered installation and latest sealed anchor, or a pending operation
with predecessor coordinate and operation digest. Its entrypoints operate on
the configured custodian, never an anchor path selected by the data archive.
The operator authenticates that channel independently on the replacement host.

Serialize security-sensitive owner operations with the existing publication
and participant locks in a documented order. Under that barrier compare the
expected independent head and durably publish a pending marker before a
mutation can invalidate a sealed anchor. This covers control mode or signer
changes, owner reconfiguration, revocations, forget/suppression and changes
to authority participant membership. Capture the complete successor view
under the relevant owners, verify and seal successor bytes, then atomically
advance the independent head before acknowledging the operation as complete.
Route all mutations in the [authority table](../work/v8-release-readiness/validation.md#authority-mutations-and-durable-contracts)
through one custody composition.
Take the backup lifetime guard first where applicable, then custody writer
lease, publication fence, and participating registry locks in stable owner-ID
order. No participant callback may acquire an earlier lock while holding a
later one. Persist a signed pending record with predecessor anchor digest,
operation kind and digest, and exact per-participant pre-state
revision/digest and expected post-state receipt/proof. The local operation
journal and each mutating participant use this same opaque operation digest,
including file-backed epoch and audit writes. Pin verified views under the
short fence, copy outside it, and recheck authority before seal. Pending can
block later security operations without holding the publication fence over
copy I/O.
Ordinary data writes keep their existing transaction path. Historical backed-up
data heads are addressed by signed archive proofs. Independently sealed
control tuples define the recovery authority and ordinal floor. A data backup
refreshes the sealed bundle from its protected view before reporting
replacement-host recoverability. A backup artifact can still have a separately
reported data watermark and age.

An unavailable custodian denies protected control transitions before mutation.
An interrupted transition after pending remains unavailable for fresh-host
activation until the exact live operation is reconciled. An existing locally
effective denial remains effective while export is repaired. Operators can stop
serving if authority cannot be changed safely. Reconcile an interrupted update
only with exact live journal, participant state and the matching pending
coordinate. Never drop or roll back pending by timestamp. If live evidence is
gone, recovery stays unavailable. A malicious rollback of both independent
custody and bundle is outside the trust model. These constraints trade recovery
availability for confidentiality and monotonic revocation.

An authenticated abort seals a recorded no-effect successor only after exact
pre-state and proof of no participant effect. Exact partial transitions
finish forward from durable receipts and apply only missing effects. Fully
applied transitions seal without redispatch. Missing or unrecognizable
participant state requires offline reconciliation. Report pending, effective
local denial, sealed and unavailable as distinct outcomes.

### Plan, stage, activate

Add a managed replacement-host operation to the existing backup owner and
installed operator. The old `boot_restored_installation` remains legacy only.
Stage into an owner-only sibling of a new destination on the same filesystem.
Preflight held live-writer isolation, capacity, independent custody and key
access. Owner confirms prior host fencing, by decommission or verified
isolation from the storage/sidecar authority. If isolation cannot be
established, allow offline verification and refuse activation. The design
assumes a single legitimate owner and cannot fence an unrelated copy that
retains private signing keys and ignores the operator.

1. Verify the current independently sealed anchor and full bundle, including
   manifest closure, trust and current deny state. Verify the archive AEAD,
   marker, signed source publication and full replay/materialization closure
   using historical trust. Prove the archived control journal tip/ordinal is an
   exact prefix member of the current anchored chain and the source tuple
   belongs to that installation/repository and lineage. A signed divergent
   tuple or a source newer than independently sealed recoverable authority is
   unavailable.
2. Materialize the source data in private staging. Reapply current
   suppression and deny policy before user release. Reuse the existing
   generation preparation and `DeliveryRestoreHold` behavior. Bind the new
   signed tuple to the staged source prefix, current authority epoch and a
   successor ordinal. The owner plan binds anchor, archive, destination,
   intended signer, source loss preview, reviewed fencing evidence and explicit
   older-data acknowledgment. Absence of later delivery evidence places the
   prior generation under hold. Historical or unknown external effects are
   never automatically resent. The owner can explicitly reject held work or
   create a new authorized operation after reconciliation.
   Choose a successor ordinal greater than the latest anchored tuple. The
   new generation disambiguates any lost unsealed ordinal values. Report the
   recovered watermark and uncertainty beyond it.
3. Prepare current control, matching data selector, hold and terminal recovery
   journal entry inside the inert staging root. Reverify the independent
   currentness record and claim its next pending operation for the exact target
   and plan. Atomically publish the complete private root, then seal its
   independent successor. A signed local activation-pending record binds
   installation, new generation, plan, custody identity and exact expected
   successor. Persist it with a quarantine reason understood by existing
   readers before rename. The common storage owner gate used by direct managed
   factory, sidecar, consume, workers and operator activation denies protected
   reads, releases and writes. The offline recovery entrypoint alone may
   reopen privately to validate and seal. It clears that quarantine only after
   verifying the authentic exact successor seal and recording it durably
   under the fence. An older binary cannot clear the new activation state.
   Verify downgrade denial with actual old binaries before rollout. Reopen
   read-only for smoke checks. Issue fresh
   credentials and grants explicitly, then activate. Repeat with the same plan
   reconciles a known prepared or published successor. A different successor
   or mismatched root refuses without modifying live bytes.

Crash cuts before private publication leave no ready root. Cuts between root
publication and custody seal leave a recoverable non-serving root. Resume
rechecks root bytes and pending identity, and never picks the older authority.
An ordinary same-installation restore continues through its existing reviewed
selector. Roll back an application package only to a verified compatible
reader with the same monotonic control history. When compatibility or the lost
host cannot be proven, leave the installation offline. Never use a prior data
backup as current security control. Report actual restore wall time, last
recoverable data watermark and hold counts. The adopter chooses RTO/RPO against
their workload with that evidence.

## Bounded turn paths

### Native capture and recall

Move `ManagedRuntimeSpool` behind its existing owner to a separate private SQLite
database. Preserve the exact signed delivery/operation bytes and full original
coordinate as identity. Partition receipts remain effect truth. Admission,
state and derived dispatch index change atomically in one spool transaction.
Register the expected spool UUID in signed installation participant state.
A missing previously registered store denies startup instead of creating an
empty queue. Include the spool in the control/data backup cut. Fence admission
while pinning its verified SQLite view, then copy outside the fence. Inventory
spool digest, high-water mark, pending IDs and exact signed bytes. Restore
retained older-generation entries under hold, never as ready commands.
Parent-generation proof or absence of receipt cannot reauthorize delivery.
Report work admitted after the archive cut as unknown from that archive.
Retain the original signed entry for owner reconciliation.
Live spool durability assumes owner-private storage and SQLite crash recovery.
The signed store UUID identifies the store and the sealed backup inventories
its cut. Detection of offline rollback to a valid older live spool with the
same UUID would require an independently committed live admission watermark
and is outside this release's storage trust model. Recover from a reviewed
archive through the restore owner if live spool custody is lost.
The pending query indexes installation, repository, generation, principal,
namespace, task, kind and stable order. Capture asks for the one exact task's
relevant pending resume while under the existing task guard, and revalidates
authority before dispatch. Global drain pages by stable key and closes the
spool transaction before dispatch. Never hold a spool write lock during a
publication or external call. Mark committed only after exact signed durable
receipt. Retry preserves identity when commit succeeds and acknowledgment fails.
Enforce existing admission limits while checking pending rows in the same
transaction. Corrupt rows, or missing rows whose presence is required by an
existing receipt, proof or sealed inventory, deny. Derived columns cannot
recreate a signed entry.

Import old spool entries once under owner-exclusive stop/lock into a staged
database. Compare complete coordinates, original bytes and states, then
atomically select the verified store. Legacy bytes stay private and inert.
Interruption before selection is retryable. The old binary must stay offline
once the new spool accepts work. Roll forward or use an independently verified
export under quiescence. Preserve the operator's source-release workflow by
exporting the original committed entry to an owner-only file at an exact
reviewed operation coordinate, with existing source grant checks intact.

Use SQLite-maintained receipt indexes for exact namespace/task and descending
source revision with stable ties, and for authorized observation source-pair
admission. Avoid global JSON scans and temporary sorting. Validate all required
receipts and current native/read grants and suppression at release inside the
existing verified operation boundary. Keep up to four eligible messages in the
current order. The 64-source limit is on unique task sources, so duplicates can
produce more receipts. Preserve eligible duplicates and test sparse permitted
tails. Iterate candidates in indexed order with a 256-candidate per
request scan bound. Verify it on the frozen native workloads. Exhaustion
before establishing the answer returns closed retryable `unavailable` and no
partial success. Empty is valid only after proof of exhaustion of eligible
history. Build indexes offline or through the existing reviewed generation
path, verify exact signed-byte parity and plans before opening, and avoid a
storage version change unless the existing verified schema contract requires it.
Verify the expected DDL and forced-index query. For relevant Tier B
acquisitions compare exact base-table and forced-index key/row ID parity and
invalidate the trust cookie on schema, database identity or relevant external
change. Use existing materialization/SQLite verification ownership. Verify
derived tables from canonical rows in the same acquired image. A dropped,
stale or incomplete index makes the scoped operation unavailable until a
verified rebuild. Do not substitute a silent empty result or a full production
scan. Normal in-process writes maintain indexes and derived materialization
in the owning transaction. No claim of hostile after-open mutable-file custody
is added.

### Host transport

At both native adapters and the shared SDK, validate loopback HTTP destination
before reading or attaching the bearer. Accept only canonical loopback
host forms, fail closed on credentials in URL, redirect and remote targets.
Preserve the SDK path where it supports a validated loopback base prefix.
Use a single absolute monotonic budget per host hook, including resume and
any chained requests or body decoding. Use two seconds per warm host hook
and a 1 MiB response ceiling before closed decode. A cold or
unavailable sidecar returns content-free failure within the budget. A resumed
or submitted operation retains its original retry ID after timeout. Retain
the exact prepared resume coordinate and proof until acknowledged in a
private adapter retry record with no transcript text. Permit one in-flight
hook per binding and bound waiting on that same deadline. Never acknowledge
capture or clear still-retryable work on ambiguous network failure.

After durable sidecar admission, the spool and signed receipt own restart
and duplicate resolution. Before admission, Pi may redrive only an original
persisted entry identified through its exact pinned branch API, with no
speculative backfill. OpenClaw may retry while its pinned callback provides
the original `runId:user` and payload. After death before durable admission,
where the pinned host cannot furnish that exact entry, report the attempt
as unknown and leave the host transcript untouched. Neither host invents a
delivery ID or reads another session. Automated historical catch-up is
outside this release. Once the sidecar durably accepts a capture, the
no-acknowledgment process-restart test must prove recovery without a second
host mutation. Log safe counts and reason codes through the host
logger. Keep exact enrolled scope and server authority. Use owner-controlled
loopback deployment with explicit local trust. Remote transport and peer
authentication for untrusted co-tenants require separate design.

### Catalog inspection and recall

Reuse the existing protected browse, inspection, and exact recall response
schemas from the current ontology work. Add a scoped read on the managed
SQLite memory-plane owner and retain the same callback/release transaction.
Resolve exact current host and catalog authority, selected catalog pointer,
selected version and required definitions by canonical IDs. Load no fact
bodies for browse/inspection. Candidate, selected and retired
versions remain distinct. Child selection must preserve current precedence
and deny when required child data is missing. If an index
is missing, out of date, or cannot prove closure within the scoped budget,
return the existing unavailable response before emitting fact bytes.
For managed browsing and inspection enforce 4,096 visited candidate
rows and 16 MiB aggregate decoded input per operation, stopping before
decoding an oversized closure. Keep existing public page and response
semantics. Count closure records and bytes across all owner lookups. Verify
coverage and stale-coordinate invalidation under the same Tier B rules as
receipt selection.

Exact ontology recall retains the existing full verified snapshot path and
all current authorization, lifecycle, provenance and suppression checks. It
preserves predicate and subject matching, including symmetric direction.
Exact recall latency and decoded work can grow with snapshot size. The owner
approved deferring bounded exact recall on 2026-11-27. A scoped mode requires
a separate versioned proof that preserves the same integrity guarantees.
Compatibility paths for other stores preserve semantics and carry no claim
to the managed SQLite performance envelope. Use the existing ontology
ownership and artifact rules and do not create new public catalog grammar.

## Evidence and rollout

Bind qualification to a clean revision and exact wheel, SDK tarball, host
asset/image and dependency hashes. Use required static, unit, storage,
integration, package, host, Benchmark Contracts and CodeQL gates. Run the
existing exact-candidate live component certification where the governing
release policy requires it. Record the provider/prompt manifest and validated
`LiveGateSummary` under the benchmark certification policy. Sign release
artifacts and the digest manifest with the approved project release signer,
verify signatures from a clean consumer, and publish only those bytes. Audit
credential, grant and log surfaces, publish SBOM and build provenance, and
rehearse rollback using these exact artifacts. Maintain configured Ruff and
Pyright plus scoped owner-by-owner type checking for changed persistence,
storage, harness and operator code. Touched-file formatting is a ratchet.
Review private authority reach-through, duplicate policy, unbounded lock work,
raw exception payloads and acknowledgment before durability in changed paths.
Authorize a shared publication refactor only if a changed path needs it and
proves recovery, mode, quarantine and revocation parity.

Use the existing balanced and concentrated reference workloads on dedicated
native Linux and macOS SSD runners, on fresh default-v8 stores. Preserve any
required staged-upgrade matrix separately. Reuse the governing sample counts,
warmup and failure accounting. Budgets are p95 verified acquisition at most
11 seconds, warm state at most 250 ms, durable no-model commit at most 500 ms,
validated checkpoint resume at most 5 seconds, and exclusive backup pause at
most 5 seconds. Report capture and recall p50/p95/p99 end to end plus lock
wait/hold, retries, IO and candidate counts under sustained writes. Compare
spool and catalog queries while varying unrelated history independently of
authorized data. Prove stable visited rows and decoded bytes at fixed authorized
scope. Validate the host deadline and candidate bound independently
of the acquisition budget. Publish scope, limitations, and failing samples.
For the native hook grid use 20 warmups and 100 measured turns per host and
fixture, at 0, 10,000 and 100,000 unrelated completed entries with the same
selected task, then repeat with concurrent writes. Use native-sized payloads
up to the existing 16,384-character limit. In the healthy warm fixture every
capture and recall hook must complete successfully within its two-second
budget. Report per-hook p95 and p99 and whole stubbed turn time separately.
Exclude model time from hook budgets. Bind evidence to each supported host
and OS pair. Run negative deadline and authorized-overflow cases separately.
For catalog use the same unrelated row grid with fixed selected authority.
Include exact row/byte ceilings
and just-over cases. At fixed authorized closure, unrelated rows decoded
must be zero, and selected row and byte counts must agree with the oracle.

Release approval requires the operator and security rehearsal on installed
artifacts, confirmed recovery with missing original host, current permissions
and revocation regressions, exact artifact verification and
independent review. Critical adoption additionally requires a named operating
owner, incident/degraded-mode rehearsal, target workload and SLO/RPO/RTO
decision, and a preregistered comparative agent evaluation. Define memory-off
control, task success, cost/latency, privacy regressions and representative
workload before collecting agent results. Keep this evaluation distinct from
deterministic tests and storage measurements. Plan its public protocol after
release hardening. [Production launch planning](https://sre.google/resources/practices-and-processes/production-launch-planning/)
