# Storage Owner Boundary Proof

- Operation: implementation
- Fidelity: Level 2 exclusive custody proof in a disposable Linux container
- Baseline: `c26aaa5f` on `codex/durable-delivery-implementation`
- Design: [Production Custody](../../design/sealed_startup_custody.md)
- Status: three final isolated trials passed and independently reviewed. Production enrollment and native qualification remain open.

## Scope

Test VC-01 against an actual Linux kernel with distinct effective UIDs, a fresh private data inode, and an independently supervised process retaining the SQLite VFS connection. Probe direct file access, kernel socket peer authentication, admission before readiness, owner contention, and takeover after process exit. Keep the packaged v7 default and production sealed mode disabled. All data is disposable.

The supervisor binds the endpoint in its protected parent; it gives each worker only the listener and its startup gate. The service UID owns the 0700 enrolled tree and an exclusive lock outside the replaceable partition. The worker obtains the lock before opening its VFS connection and enables serving after a successful retained read. The authorized peer is a second UID. A third UID holds and mutates its own prior writable descriptor, attempts to open the enrolled data directly, and is separately denied by the socket peer check. A competing process under the service UID must fail before acquiring the live owner's lock. Restart requires observing predecessor exit and reacquiring the lock before opening a new SQLite view.

The probe uses a tiny synthetic database and expected byte root from fixture setup. It does not install a service on the host, enroll an existing production tree, run authenticated Memorii restore, or exercise signed publication, grant, and credential rotation at the transport boundary. The Docker VM is Linux evidence for this custody mechanism. It is not a replacement for dedicated native Linux and native macOS acceptance.

## Observed Results

All [three trials](owner-boundary-linux-container.jsonl) passed with CPython 3.12.16 and SQLite 3.40.1 on the Linux arm64 Docker VM. The supervisor captured the old actor's live inode before copying the fixture into the newly owned tree. The old actor changed bytes through its retained descriptor and the new image still matched its expected root and served the original bytes. Both the authorized client and legacy client received `EACCES` on direct read and write and `SQLITE_CANTOPEN` from SQLite. All worker and client processes had zero effective capabilities.

An actual request queued before acquisition received zero bytes until the supervisor opened the startup gate and the worker verified the retained view. The kernel peer check refused the same request from the legacy UID. A separate process running as the service UID exited on lock conflict while the first worker was still alive. The supervisor waited for the first worker's SIGKILL exit before starting the replacement, which acquired the same lock, authenticated the image, and served the authorized client. Closing the supervisor channel while the replacement was idle made it close the view and exit normally.

Independent reviews confirmed the evidence for fresh-inode isolation and cooperating-worker lock handoff. The prior open writer had no alias into the fresh tree. The probe makes no claim about arbitrary code already running under the trusted service UID, loss of an actual supervisor process during an in-flight response, or recovery of a pending signed publication. The idle channel-close case is a narrower shutdown proof. Ruff and whitespace checks passed.

## Reproduction

Use the cached arm64 image `memorii-linux-validation:97493402-fixtures` with local image ID `sha256:ffb85c7262b0df64a9f78e583d126b50d75e03d78259336921ff41cf695d1273`. Run with pull disabled, no network, a read-only root filesystem, limited PIDs and memory, and a disposable executable tmpfs at `/tmp`. Drop all capabilities and admit only CHOWN, DAC_OVERRIDE, SETUID, SETGID and KILL for the fixture supervisor. The test verifies that the children lose effective capabilities. Bind the proof directory and header copies read-only. No Docker volume or service-owned account on the host is created.

Inside the container, build the existing VFS using the copied SQLite extension and OpenSSL headers at `/sqlite-headers` and `/crypto-headers`, then run the custody probe:

```sh
cc -std=c11 -D_GNU_SOURCE -shared -fPIC -Wall -Wextra -Werror \
  -I/sqlite-headers -I/crypto-headers /probe/retained_vfs.c \
  -Wl,-z,defs -l:libcrypto.so.3 -o /tmp/retainedvfs.so
python -B -W error /probe/owner_boundary_probe.py supervise /tmp/retainedvfs.so
```

This run reused the local Homebrew header copies for compilation against the subset of the extension ABI used by the prototype. The VFS calls the container's SQLite API table and links the container's `libcrypto.so.3`, with no separate SQLite dependency. Building and proving a released native artifact against its own packaged headers remains a separate gate.

## Next Action

Extend the controlled owner endpoint with current signed publication, credential and grant checks at release. Test credential rotation and owner loss while a response is in flight, then apply the production handoff and erasure protocols.
