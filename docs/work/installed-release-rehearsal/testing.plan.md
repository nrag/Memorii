# Installed Release Rehearsal

- Work type: testing
- Fidelity: Level 3 first release, bounded to installed host and operator journeys
- Tested product revision: `d62a3abd`
- Parent: [Release conformance](../durable-memory-implementation/milestones/release-conformance.plan.md)
- Scope: native installed-wheel operator, pinned Hermes/Pi/OpenClaw, offline model stub, and current v8 default
- Status: rehearsal complete. Operator and Hermes checks passed. Pi and OpenClaw release gates remain open.

## Acceptance

Exercise capture through a real host, reopen its state on restart, and
demonstrate which recall surface can read committed data. Test backup and
signed older restore on a fresh v8 installation. Prove an archived active
source grant cannot regain release authority after a live owner revokes it
and the installation selects the older generation.

Run the pinned host Dockerfiles and existing host programs. Replace the
editable package with the frozen wheel and take the source package off the
import path. The Dockerfiles supply the pinned host binaries and adapter
assets. The browser, cloud credentials, and external model providers are
outside the run. Distinguish provider-contract recall from recall through
the actual host CLI, and record refused or skipped paths explicitly.

The additional restore oracle lives in
[the existing source authority integration suite](../../../memorii/tests/integration/test_runtime_source_authority.py).
It uses real source admission, an owner-issued release and a subprocess
operator revocation receipt. It proves the original source still exists
after restore and the restored active row still binds the superseded
generation. The installed serving owner must release zero sources for that
grant after reopen. The durable-runtime integration job already owns the
test family.

## Installed Evidence

The clean wheel was built from `d62a3abd51e4a80e5acef157af236a6ccfcdab1b`
and installed outside the checkout. Its SHA-256 is
`bac85bc8f049be3e1f20f0cc307400895a4854a30b75c122bfafb8dd7be908ec`.
Every pinned container reported the wheel's installed Python import path and
asserted that the default format is v8.

- Native macOS passed 71 installed operator, source authority, migration
  and restore checks with warnings treated as errors. The source grant was
  live before backup, then the CLI revoked it and a reopened installation
  confirmed the terminal revocation. The older restored generation still
  contained the source and the archived active grant row. That row could
  release nothing because it was bound to the superseded generation.
- With localhost listeners enabled, 38 installed managed HTTP, sidecar
  and host adapter checks passed. The sandboxed pilot denied loopback bind.
- The installed Hermes provider completed-turn test captured, committed,
  replayed and recalled a fact after reopen. It substitutes the extraction
  provider response. The real pinned Hermes CLI independently retained both
  exact entered messages as source records across its process restart. The
  plane grew from 29 to 42 records, and the host journey passed. Its model
  stub does not establish CLI fact recall.
- Pi 0.99.2 started and continued the same session in a new process and
  denied an unauthorized fork. Two observation envelopes carried the
  empty-string digest rather than the entered messages. The legacy drain
  was refused by v8 and committed zero of four envelopes.
- OpenClaw 2026.9.7 ran both turns with a gateway restart between them.
  Both observation digests matched the exact user input. Its legacy drain
  also committed zero of four envelopes. A successful state read in each
  JavaScript journey served the pre-provisioned task.

Pi and OpenClaw currently submit to the legacy intake route. Ordinary v8
requires the signed managed prepare, intake and drain flow. This failure
also reproduces in the installed sidecar boundary test by design. Neither
host has passing durable continuation or captured-content recall evidence
on the installed path. The local operator proof covers same-installation
restore to a new generation, which is distinct from disaster recovery on
a new host.

The test review confirmed the restore assertion proves zero source release
from an old generation. It does not claim that the active archival row is
rewritten to carry the live revocation tombstone. The regression also proves
that the live grant was revoked with a durable v2 record before restore.

## Next Action

For a release that advertises Pi or OpenClaw, wire the managed host transport
and rerun the installed journey through committed capture, restart and
recall. The Pi host also needs to capture its actual user text. Carry the
Hermes and installed operator results into final release review.
