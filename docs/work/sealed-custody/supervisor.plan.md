# Supervisor Process Recovery

- Operation: implementation
- Fidelity: Level 2 isolated custody experiment, with native macOS reference measurements
- Baseline: `a041d4d0` of `codex/durable-delivery-implementation`
- Contract: [Sealed startup custody](../../design/sealed_startup_custody.md)
- Predecessor: [Signed authority at socket release](release.plan.md)
- Status: isolated recovery and native macOS prototype recheck complete. Installed production recovery and native qualification remain open.

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

## Native macOS Evidence

The [cold VFS samples](supervisor-native-macos.jsonl) use the preserved v8
main images from the prior native capacity workloads. The originals were
untouched. Each sample read a separate uncached SSD copy with zero resident
main-file pages. The VFS authenticated every byte against the precomputed
fixture root before it opened SQLite, then authenticated the SQLite blocks
used by a covering-index lookup and a 1.25 MB BLOB read. The native extension
was freshly compiled against the same SQLite 3.54.1 ABI.

| Workload | Image bytes | VFS open through first authenticated reads |
| --- | ---: | ---: |
| Balanced | 5,655,961,600 | 2.19-3.27 s |
| Concentrated | 5,660,487,680 | 2.18-2.20 s |

These samples cover cold file residency with process reuse. The timed region
includes whole-image hashing, VFS initialization and native reads. Fixture
copying, process launch, control authority and socket release have separate
costs. Two samples per workload size establish diagnostic timings.

Reproduce on native macOS with the [private extension build](conftest.py),
the installed reference wheel environment and:

```bash
python -B -W error docs/work/sealed-custody/reference_vfs_reads.py \
  --fixtures "$fixtures" --roots docs/work/sealed-custody/block-hash-macos.jsonl \
  --extension "$extension" --cold-work "$scratch" --samples 2
```

The [fresh-process startup recheck](supervisor-sealed-startup-macos.jsonl)
used the same installed wheel and signed fixture identities as the
[earlier sealed startup experiment](../verified-startup/implementation.plan.md).
Each timed subprocess opened a separate zero-residency copy. This experiment
uses the frozen-image startup prototype and measures one matched pair per
distribution. It runs separately from the retained VFS and socket experiment.

| Workload | Ordinary acquisition | Sealed acquisition | Sealed service open through ready |
| --- | ---: | ---: | ---: |
| Balanced | 8.63 s | 3.37 s | 4.60 s |
| Concentrated | 9.01 s | 3.54 s | 4.80 s |

Both sealed acquisitions met the five-second acquisition target and made zero
logical scan calls during startup. Both fresh raw-body mutations blocked
readiness at the same signed publication. The earlier concentrated
service-inclusive samples took 5.12-5.26 seconds, so these measurements leave
the full service-start distribution open. All 16 focused native macOS custody
tests passed with warnings treated as errors.

## Remaining Qualification

Production qualification requires a packaged, host-enrolled supervisor and
VFS with independently pinned witness authority, reboot and actor-loss
recovery, and production transition/erasure wiring. The governing design
still requires approval of the Tier B byte-equivalence amendment before
sealed startup can be routed in that artifact. Run the installed artifact's
full balanced and concentrated matrix on dedicated native macOS and Linux
SSD runners after those gates. The previous dedicated Linux host was deleted.
The offline Linux container proves the crash path and cannot supply the native
SSD measurements. This branch keeps the installed v7 default.

## Next Action

Obtain approval of the governing Tier B amendment for an installed supervisor and VFS qualification candidate.
