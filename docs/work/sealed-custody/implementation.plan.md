# Retained SQLite VFS Prototype

- Operation: implementation
- Fidelity: Level 2 feasibility of the native read and integrity gate
- Baseline: `771f4d84`, `codex/durable-delivery-implementation`
- Design: [Production Custody](../../design/sealed_startup_custody.md)
- Status: native feasibility prototype complete. Production custody and release qualification remain open.

## Scope

Implement and test the VC-02 byte-view mechanism. The trusted, single-threaded runner supplies the already measured expected image root. It does not authorize a production seal or hold a service/transport lease. No production startup, library dependencies, compilation or packaging defaults, operator routes, or persisted state change. v7 remains default.

Use the current SQLite instance's extension API to register a private nondefault read-only VFS. Authenticate the block table against the expected root before pinning. A native connection takes ownership of one read-only duplicated FD and never resolves a data path. Hash each physical block before copying it into SQLite. Integrity failure latches until view teardown. Buffer each application result and check that latch immediately before releasing it, even if SQLite supplied all its inputs from cache.

The design's supervisor and socket handoff remain open. A clean cached response can remain valid until a later physical read detects corruption. The prototype enforces denial from detection onward. It performs no background scrub and exposes no connection or arbitrary SQL to an external client.

## Evidence

Six focused tests passed on macOS arm64 with CPython 3.12.16 and SQLite 3.54.1, with warnings treated as errors and native compilation using `-Wall -Wextra -Werror`. They exercise a covering index and SQLite's incremental BLOB API after pathname replacement, detection of a preserved-size byte change on a late BLOB or covering index read, denial of a later cached result, and discarding a result buffered before a second read trips the latch. They also cover digest mismatch before pinning, short read inside the signed size, and attach denial.

The [reference reads](retained-vfs-macos.jsonl) used the [previously recorded roots](block-hash-macos.jsonl) for both retained macOS images. Select the key in a separate base-row step, then require the actual `memory_payloads_digest` covering query and compare the BLOB with its original logical digest. The index lookup ran three authenticated native reads on each image. The BLOB overflows ran 306 authenticated native reads each, over approximately 1.26 MB of returned bytes. These are read-path observations. They do not qualify startup or establish unique block counts because the prototype can authenticate one physical block on several page reads.

The extension was compiled against the local SQLite headers and OpenSSL `libcrypto`. It dispatches through the hosting CPython module's SQLite extension table. Native linker inspection confirmed no separate SQLite dependency. Pytest builds the test-only extension from `retained_vfs.c` using `SQLITE_PREFIX` and `OPENSSL_PREFIX`, defaulting to the local Homebrew prefixes. Use a CPython environment with SQLite loadable extensions and `dbstat` enabled. The reference runner takes the retained fixture directory, measured roots file, and path to that native extension.

Independent review confirmed the current hash, descriptor, and fail-closed assumptions for this scope and identified an extension initialization failure hazard and pending-pin cleanup gap. Registration now publishes the global VFS only after installing private controls, preserves module lifetime if rollback cannot detach callbacks, and registers cleanup before allocating a pin. The final test and reference runs used that code. Ruff and whitespace checks passed.

## Next Action

Design the next bounded proof of supervisor ownership and grant-ordered release, then test retained-view drain, writable handoff and erasure against that owner. Keep the production feature disabled.
