# Sealed Startup Custody Design

- Operation: design
- Fidelity: Level 3 production contract design, with Level 2 feasibility evidence so far
- Baseline: `9761d726` on `codex/durable-delivery-implementation`
- Canonical proposal: [Production Custody](../../design/sealed_startup_custody.md)
- Related evidence: [Sealed acquisition prototype](../verified-startup/implementation.plan.md)
- Status: architecture proposal and independent review complete. Native implementation, governing amendment approval and production qualification are pending.

## Authority And Scope

Keep v7 default, all normal startup and verification paths on unenrolled roots, and current Tier B semantics until the proposed whole-image equivalence is approved. The optional provider must retain a descriptor-bound SQLite view during runtime release, serialize owner transitions through the existing publication and lifetime boundaries, and prove managed erasure despite a crash or loss of the installation signing key.

The existing code review covered the factory, generation guard, sidecar repository lifetime, mode change, staged restore and upgrade, backup lifetime lock, forget suppression, and physical erasure ordering. The current erasure deletes the installation keys before finishing the independent control journal and receipt. A custody-independent supervisor ledger is proposed to record consent, progress and a terminal deletion result across that cut.

## Evidence And Identity Ledger

| Surface | Authority and maturity |
| --- | --- |
| `verified_image.json` version 2 and `memorii.verified-image.v2` | Proposed closed authenticated seal profile. Existing v1 fixture seals carry no production authority. |
| `memorii.sealed-image-block.v2` and `memorii.sealed-image-root.v2` | Proposed physical digest domains. An independent sequential Python reproduction on copied fixture bytes measured the root/table cost. |
| Storage worker, retained lease, supervisor custody ledger | Component roles and lifecycle are specified in the design. No public launcher, transport route, persisted filename, SQL table, or CLI name is assigned in this proposal. Require installation/trust and ABI proofs before any enabled package. |
| Mode, operation receipts, erase consent, and existing public runtime operations | Existing authority paths stay authoritative. The supervisor ledger cannot resolve a runtime publication or issue a data receipt. It owns process custody and recoverable erasure progress. |

The [hash spike](block-hash-macos.jsonl) used the exact native macOS main-file fixture copies and existing uncached copy/residency helpers. One reading process computed the proposed 64 KiB ordered SHA-256 block digests and root of each zero-residency file using `os.pread`. Custody, SQLite reads, verification, and owner operation timing were outside the interval. No production sources were changed.

The [ABI spike](sqlite-abi-macos.json) used a disposable C extension compiled against the installed SQLite headers and the locked CPython/SQLite process. It registered a nondefault VFS with a rejecting `xOpen` via SQLite's extension API table. The named VFS returned `SQLITE_CANTOPEN` and the default VFS still worked. No retained descriptor binding, real query, cross-platform support or packaging trust was inferred.

## Review Disposition

Specification, correctness and test review independently evaluated the frozen draft. Confirmed gaps concerned prior writable descriptors at enrollment, native SQLite identity, the backup path's second SQLite open, the socket release boundary, and receipt authorization after installation-key deletion. The revised architecture requires a fresh enrolled tree with verified restore for existing data, defines the extension and read contracts, drains to ordinary backup or audit, orders transport admission against revocation and the integrity latch, and records signer eviction and terminal receipt in independently authenticated supervisor state. A targeted delta review also found that grant registry changes currently take only their own lock. The design now requires all grant and credential writers to share the publication fence with the release operation. These are design closures. The verification ledger in the canonical proposal lists the remaining implementation and native proof obligations.

## Next Action

Prototype the native retained descriptor VFS against the packaged SQLite instance, with real BLOB and index reads, injected late corruption, and denial of unauthenticated release. Keep the production feature disabled until the custody, transition, erasure and Tier B approval gates pass.
