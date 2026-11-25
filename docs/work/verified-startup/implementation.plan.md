# Sealed Startup Feasibility Prototype

- Operation: implementation
- Fidelity: Level 2, private synthetic fixture copies on native macOS
- Design: [Verified Startup](../../design/verified_startup.md)
- Baseline: `0f66fc11` of `codex/durable-delivery-implementation`
- Status: prototype implemented and focused tests passed. Native comparison in progress.

## Scope And Authority

Prove seal issuance and admission on the selected staged v8 read-only SQLite image, including physical image identity and denial of tampered images. Measure verification acquisition and service-open-through-ready on each retained signed qualification workload. Preserve v7 default and all production entry points. The prototype has no production read fallback, launcher, lease draining or custody provider. It emits readiness evidence only and does not serve a writable handle or harness traffic.

The installed wheel is unchanged. The prototype uses the current signed control selector and publication, original catalog rebuild, raw verification, and original replay verifier before issuance. A test-only key-owner subclass uses the currently active fixture publication key to issue the seal under its separate signature purpose. The standard key-owner allowlist remains unchanged. The fixture artifact is managed by the test runner, not restored or loaded by production.

Eleven installed tests passed with warnings treated as errors. Independent review confirmed the host-local descriptor proof and identified missing explicit seal version and current trust binding. Both are enforced and tested, including a trust change after hashing. The expanded tests also refuse issuance on a corrupt payload and refuse readiness on a changed binding row. The exact fixture runner flips one raw body byte on each disposable staged image after timing and then verifies readiness denies with the publication row unchanged.

## Verification Ledger

| Design requirement | Prototype evidence |
| --- | --- |
| VS-01 | Current installed wheel and composition remain unchanged. The benchmark exercises ordinary acquisition from the same wheel. |
| VS-03 | On a private named read-only v8 copy, freeze the image and its containing namespace, hash the pinned native descriptor, then confirm SQLite opened an actual descriptor for that same file identity. Mutate signed-head-preserving raw data, event history and checkpoint bytes, and verify readiness denies. |
| VS-04 | Confirm regular single-link owner-held path, unchanged inode, flags, size and timestamps at both ends. Actual native writes and renames under the flag are denied. An owner-controlled same-byte inode swap between hash and SQLite open is rejected. Reject known SQLite side files. Production cross-process leases, independently pinned control snapshot semantics, and erasure remain out of scope. |
| VS-05 | Use re-staged original fixture copies preserving generation, manifest, checkpoint and runtime position. Alternate baseline and sealed mode in fresh installed subprocesses, require zero resident main-file pages, and report the exact 5 s acquisition gate. Record service open and one-time seal issue separately. |

## Next Action

Finish the native comparison, reconcile independent reviewer findings, and publish the test-only result.
