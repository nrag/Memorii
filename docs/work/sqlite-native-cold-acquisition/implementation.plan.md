# Native SSD Cold SQLite Acquisition

- Work type: implementation
- Status: active
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

## Next Action

Finish full native comparisons of the bounded raw read path, then freeze and rerun the installed candidate.
