# Sealed Startup Feasibility Prototype

- Operation: implementation
- Fidelity: Level 2, private synthetic fixture copies on native macOS
- Design: [Verified Startup](../../design/verified_startup.md)
- Baseline: `0f66fc11` of `codex/durable-delivery-implementation`
- Status: scoped prototype and native comparison complete. Production activation remains open.

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

## Native Results

The [eight acquisition samples and two tamper checks](sealed-startup-macos.jsonl) use prototype revision `b9cb4883` and installed wheel SHA-256 `e5686aca067eb6152791c150f7bb3eb82616a0c9ea2f997cf6187cd468441beb`. Both private copies retained their original exact signed tuple, manifest, runtime position, checkpoint, and generation. Every timed subprocess started with zero resident main-file pages. Each fixture had two ordinary and two sealed acquisitions in alternating order.

| Fixture | Ordinary acquisition | Sealed acquisition | Sealed service open through ready | One-time seal issue |
| --- | ---: | ---: | ---: | ---: |
| Balanced | 9.08-9.19 s | 3.47-3.49 s | 4.82-4.86 s | 12.87 s |
| Concentrated | 9.01-9.57 s | 3.73-3.78 s | 5.12-5.26 s | 13.17 s |

All sealed observations met the 5 s acquisition target, which is timed after service construction. All four made zero logical verifier calls at startup. Including service construction, concentrated exceeded five seconds in both samples. The timings count current control checks and actual SQLite admission, and exclude fixture copying, residency measurement and setup of the frozen namespace. The native provider in this experiment uses owner-settable file and directory flags with independent descriptor checks in a private single-threaded process. [macOS file flags](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/chflags.2.html)

After timing each fixture, a one-byte raw-body mutation left the same publication row and denied readiness. The focused tests also verify actual SQLite read-only behavior and reject an identical-byte inode substitution after hashing. The reader closes the image before returning its acquisition result. These observations establish the prototype's acquisition behavior. They do not qualify post-ready serving, writable starts, native Linux, or the full release matrix. v7 remains the installed default.

## Next Action

Design and qualify the production provider's retained view, transition and erasure custody before integrating the optional sealed mode into the storage factory.
