# Native SSD Cold SQLite Acquisition

- Work type: implementation
- Status: native diagnostic delivered. Level 3 release qualification remains open in the parent.
- Delivery fidelity: Level 3 release target with native diagnostic evidence
- Baseline: `8ffe0f65` on `codex/durable-delivery-implementation`
- Parent: [durable delivery](../durable-delivery-implementation/implementation.plan.md)
- Prior evidence: [Linux acquisition remediation](../sqlite-capacity-remediation/implementation.plan.md)

## Scope And Proof

Reduce cold startup time for an owner-staged v8 selection while preserving exact signed BLOB, manifest, selector and replay verification. Preserve v7 as the default. Keep the full retained 1 GiB concentrated fixture, its generation-local v8 checkpoint, and its exact 1,000-event signed tail. Native macOS diagnostics measure the actual installed acquisition operation. Native qualification under both distributions and dedicated runner conditions remains separate.

| Milestone | Proof owed |
| --- | --- |
| Native baseline | Native SSD attestation, exact prior installed wheel, fresh no-cache fixture copies, page residency measured before each acquisition, and unchanged signed tuple |
| Raw payload path | Bounded raw buffers, exact digest and reference parity, malformed length and body rejection, and measured comparisons on the same full data file |
| Installed acquisition | Rebuild candidate wheel from an exact revision, pass corruption and legacy tests, and repeat full native cold samples. Retain all outcomes and the residual five-second gate. |

The coordinator owns native export, baseline, installed measurement and integration. The raw I/O writer owns bounded payload reads and targeted checks. The platform reviewer confirms the storage and cache protocol and reviews any proposed same-snapshot overlap.

## Native Baseline

The local host reports an Apple M6, 12 logical CPUs, 32 GiB RAM and a local Apple SSD backing the APFS data volume. The tested host is shared. Python 3.12.16 links SQLite 3.54.1. The prior wheel from `5af58275` was copied from the isolated test guest and verified by wheel hash `15cefaf62102a7b5343c6cdca2aae8548a97fa7d01680f44ca3736cf0259c2ca`. The native driver verified its installed inventory and the same signed checkpointed tuple. The exported synthetic fixture contains its selected partition and control state. The v7 rollback copy stayed in the guest.

The runner copies into a fresh file with Darwin `F_NOCACHE` during untimed setup. A read-only file mapping and `mincore` observe cache residency without touching file bytes. All three [baseline samples](macos-baseline.jsonl) reported zero resident main-database pages before the timed request and 339,294 of 354,519 afterward. SSD device cache and host background activity are uncontrolled. No system-wide cache purge was used.

| Metric | Median | Maximum |
| --- | ---: | ---: |
| Complete acquisition | 7.043 s | 7.061 s |
| Raw payload verification | 2.999 s | 3.009 s |
| Complete manifest rebuild | 5.492 s | 5.507 s |
| Runtime replay verification | 1.535 s | 1.542 s |

## Implementation

`749230e0` reads eligible payload bodies from the ordered SQLite row cursor in one pass. SQLite checks the storage class and length before projecting each bounded body. Larger bodies still stream through `blobopen`. The verifier recomputes the same domain-separated SHA-256 digest and checks base-table and index parity. An isolated full-database walk went from 2.846 s to 2.413 s median with zero starting page residency.

`dfe5039b` prototyped Darwin `F_RDADVISE` ahead of the exact v8 raw verifier. Independent review reproduced a P2 SQLite lock loss when closing a second file descriptor for the same inode in the SQLite owner's process. `ebd1725a` moves the read advice into a child process with a two-second timeout. A native WAL regression checks lock ownership before and after the actual dispatch and verifies release when SQLite closes. Focused delta review found no remaining validated P1/P2 in the slice (`remaining_validated_p1_p2: []`).

The helper advises the regular main database file in 32 MiB ranges up to 6 GiB, which covers the current 5.41 GiB reference database. SQLite still verifies every payload, including those beyond the advised range. Hint failures fall through to the same verifier. The implementation leaves the signed format and v7 default unchanged. A separate concurrent verification probe on one SQLite connection failed the recovery catalog check and was discarded.

## Installed Reruns

The [bounded-read wheel run](macos-bounded-read.jsonl) used `749230e0` and passed 107 focused installed tests. Its three full acquisitions took 6.693 s, 6.581 s and 6.566 s. Median raw verification took 2.599 s. Each run started with zero resident main-database pages and verified the same signed checkpoint and tail.

The [rejected same-process advice run](macos-rejected-advice.jsonl) used `dfe5039b`. These measurements preserve the experiment history. The lock loss invalidates them as candidate acceptance evidence.

The lock-isolated `ebd1725a` wheel SHA-256 is `367a977ed1dce901876ededb6794fd83c78736a8adcca98b202fba4b07ae953e`. The isolated driver verified the installed wheel inventory and presence of the helper. All 110 tests passed from that wheel with warnings treated as errors. Coverage included payload and index corruption, malformed payload size, read-ahead timeout and range limits, SQLite lock safety, staged upgrade, older restore, partition recovery and selection, checkpoint and tail replay, source authority, and backup fencing. Focused Ruff and Pyright checks also passed.

All five [lock-isolated samples](macos-final.jsonl) verified signed tuple `b7a7b8690ef9b918a178e84a2948ce2f8a90b9af9a199a19b90f7836005eb83c`. Every main database copy started with zero of 354,519 pages resident. The complete acquisitions took 4.860 s, 4.885 s, 4.963 s, 4.892 s and 4.911 s. There were no timed failures or retries.

| Metric | Median | Maximum |
| --- | ---: | ---: |
| Complete acquisition | 4.892 s | 4.963 s |
| Raw payload verification | 1.813 s | 1.838 s |
| Complete manifest rebuild | 3.505 s | 3.544 s |
| Runtime replay verification | 1.365 s | 1.395 s |

Complete acquisition improved by 30.5% at the median. Raw verification improved by 39.5%, including the time spent advising reads. All samples met the five-second startup budget on this shared native macOS host and the concentrated reference fixture. The formal capacity gate needs ten acquisition samples per distribution and platform, the other required series, and dedicated native runners.

## Next Action

Use the parent reference-capacity milestone to qualify both distributions on dedicated native Linux and macOS runners before considering default activation.
