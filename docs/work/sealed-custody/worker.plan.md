# Retained Worker And Erasure Recovery Prototypes

- Operation: implementation
- Fidelity: Level 2, private native macOS fixture experiments
- Baseline: `a67563f2` on `codex/durable-delivery-implementation`
- Design: [Production Custody](../../design/sealed_startup_custody.md)
- Status: bounded prototypes implemented and verified. Production enrollment and deployment custody remain open.

## Scope

Continue the [descriptor VFS experiment](implementation.plan.md) across the response boundary, storage owner handoff and signer deletion cuts. Keep all production roots, v7 default, packages and ordinary acquisition unchanged.

| Design surface | Bounded evidence |
| --- | --- |
| Retained owner and response release | SQLite has one owner thread and real response tasks use local sockets. Use the native integrity latch mutex for each nonblocking send and the installation publication fence for grant epoch verification and writes to the existing grant registry. Complete another read or revoke while a response waits. Force socket backpressure and prove revocation can advance before the unsent suffix is retried. |
| Writable handoff | Stop admission and time out while a live response holds custody. A competing lock attempt cannot take the lifetime guard while the publication fence remains free. Retire SQLite, then use the existing exclusive lifetime, exact verification and owner mode change to write and reopen a staged v8 fixture. |
| Erasure recovery | Use an isolated two-file inventory and an authenticated ledger signed with a separate supervisor key. A real child process creates the installation signer proof and exits. Crash subsequent processes before signer removal, after removal and directory fsync, and after terminal receipt commit. Startup remains denied. The original fixture owner coordinate and operation return the same independently verifiable signed receipt after restart, including the exact pre-crash receipt after a lost acknowledgement. |

The worker uses trusted in-process calls and an already measured root. It proves grant and native-latch ordering for local response bytes, with no shipped peer authentication, transport framing, credential rotation, complete Tier A check or native service supervisor. The erasure harness represents just the signer-loss cut against synthetic keys and image bytes. It does not replace real installation erasure, enumerate backups or external copies, or authenticate OS peers. The fixture runner supplies a trusted owner/operation coordinate and observes the temporary key-owning process exit before recording authority for unlink. The proof subprocess signs using the installation key and never opens the supervisor ledger. All subprocesses run under one OS principal. Privilege isolation, cached-key eviction across arbitrary process cuts, interruption between unlink and directory fsync, and power-loss durability remain unverified. Neither harness is reachable from production.

## Verification

Sixteen focused tests passed against the installed macOS artifact with warnings treated as errors. Native compilation used `-Wall -Wextra -Werror`. Independent review confirmed the grant/latch and drain order and identified the need to keep role isolation outside the claim and compare the pre-crash receipt to the first post-restart result. The final test checks an already committed authenticated receipt before retry. The release gate checks actual socket output from both the parked and detecting requests. Ruff and whitespace checks passed.

## Next Action

See the [storage owner boundary proof](owner.plan.md) for the bounded Linux UID, readiness, and process-handoff evidence. Credential rotation, full Tier A framing, and real installation inventory recovery remain open before production wiring.
