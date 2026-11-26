# Supervisor Process Recovery

- Operation: implementation
- Fidelity: Level 2 isolated custody experiment, with native macOS reference measurements
- Baseline: `a041d4d0` of `codex/durable-delivery-implementation`
- Contract: [Sealed startup custody](../../design/sealed_startup_custody.md)
- Predecessor: [Signed authority at socket release](release.plan.md)

Exercise supervisor process death with the same signed publication, authenticated
retained view, OS-authenticated client and socket release guard as the predecessor
experiment. A fresh supervisor may bind the endpoint only after authenticating
an independent host witness's durable exit record for the exact predecessor and
acquiring the anchored owner lock. Reopen the same signed publication and serve a
complete response through the new worker. Observe both before-first-byte and real
socket backpressure cuts. Check missing or altered witness authority, a still
live predecessor, and an independently held owner lock.

The prototype gives the observer a Linux pidfd while the original supervisor
and worker are alive, then kills the actual supervisor. The independent observer
may persist the witnessed exit only after its pinned kernel handle reports exit.
The record binds the fixture enrollment and publication. Its signing identity
is provisioned independently of the installation signer. The test orders socket
bytes against observed fenced closure and checks the exact prefix.

The bounded entrypoint is private harness code under this directory. The
production custody ledger, installed broker, enrollment, erasure and writable
transition recovery, or recovery after loss of the independent witness require
separate evidence. Keep v7 as the default. Capture fresh cold macOS native VFS
measurements on both preserved exact workload distributions. Record dedicated
native Linux and packaged integrated native qualification separately.

## Supervisor Evidence

The [isolated Linux results](supervisor-recovery-linux-container.jsonl) show an
actual `SIGKILL` of the supervisor that created the listener, started the
descriptor-owning worker and held the only liveness-pipe writer. Both service and
client retained their distinct unprivileged UIDs. The witness acquired its pidfd
before the death. At the backpressure cut the signed pending record was durable
before the crash. At the before-first-byte cut an attempted restart first showed
that missing state closes startup. The signed record uses the fixture witness's
separate key and an exact pending-to-exited compare-and-swap with SQLite FULL
sync. A surviving trusted fixture controller supplies the enrollment and pinned
witness identity to the successor.

| Crash cut | Bytes already queued | Total bytes received on interrupted socket | Successor bytes |
| --- | ---: | ---: | ---: |
| Before first byte | 0 | 0 | 180,663 |
| Backpressure | 8,064 | 8,064 | 180,663 |

The client verified the exact content of both interrupted prefixes and both
complete responses. The successor verified the witnessed signed publication
against the retained view. It acquired and passed the very same locked open
file description to its worker, which kept it until native view teardown.
Attempts using a missing or pending record, a bad signature, a different
enrollment or key, a held owner lock, or a reused bootstrap or handoff never
replaced the endpoint. The one-use handoff deliberately requires new proof for
any further recovery. Reboot, witness loss and a crash while activating the
successor remain outside this experiment.

The Linux run reused the offline container and compiler from [the owner
experiment](owner.plan.md#reproduction), with
`python -B -W error /probe/supervisor_recovery_linux.py run /tmp/retainedvfs.so`
after building the extension. Both crash cases and all eight original Linux
socket-release cases passed. Independent spec, correctness and test review
identified watcher-failure drain ordering, cleanup before pidfd capture and
successor identity evidence. The fixture drains even when the watcher raises,
cleans running supervisor groups on unexpected failure, and records both
supervisor and worker process identities. Evidence maturity is locally verified
for the isolated path. No installed runtime entrypoint consumes this ledger.

## Next Action

Record the native exact-fixture measurements and remaining qualification gates.
