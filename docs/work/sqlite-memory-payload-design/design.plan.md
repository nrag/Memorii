# SQLite Memory Payload Design

- Work type: design
- Delivery fidelity: Level 3 first production release
- Status: active
- Coordinator: main task
- Baseline: 693b87d9, with installed product wheel from 97493402
- Related implementation: [durable delivery](../durable-delivery-implementation/implementation.plan.md)
- Design: [SQLite memory payload storage](../../design/sqlite_memory_payload_storage.md)

## Objective

Test whether partition-local content addressing reduces verified acquisition and backup costs without changing the canonical records that Memorii releases, authenticates, or replays. Compare raw and bounded compressed encodings over identical signed source fixtures. Keep the measured prototype out of the installation lifecycle.

## Evidence And Boundaries

The canonical inputs are the storage and event specifications, the durable execution design, the v7 catalog and publication code, and the two frozen fixture shapes in the implementation validation ledger. Inputs to the prototype must be authenticated installation snapshots. Record legacy reconstruction, projected verification, SQLite copy time, and size separately. Production qualification still requires the actual installed storage format and the approved full Linux and macOS workload.

The coordinator owns the draft and measurement. A separate writer owns the isolated payload probe. An independent read-only reviewer maps persisted bytes and downstream owners. SQLite payload deduplication changes physical storage, so the approved implementation plan remains separate from this design work.

## Feasibility Result

The read-only experiment reproduced all three memory catalog commitments for both encodings. The [runner](run_probe.py) compared each original catalog entry to the full manifest authenticated by the installed acquisition path, then compared the reconstructed entries to the originals. It ran on the same diagnostic workload shapes as the [Linux capacity measurements](../durable-delivery-implementation/validation.md#larger-linux-capacity-diagnostic).

| Native sources | Encoding | Three memory catalogs (MiB) | SQLite copy median (s) | Catalog or payload scan (s) | Exact v7 reconstruction (s) |
| ---: | --- | ---: | ---: | ---: | ---: |
| 128 | v7 | 463.1 | 0.175 | 0.198 | — |
| 128 | Raw deduplication | 155.6 | 0.062 | 0.347 | 0.938 |
| 128 | Adaptive zlib | 87.5 | 0.040 | 0.492 | 1.575 |
| 512 | v7 | 1,852.7 | 1.068 | 0.792 | — |
| 512 | Raw deduplication | 622.3 | 0.251 | 1.324 | 3.611 |
| 512 | Adaptive zlib | 350.1 | 0.134 | 2.403 | 7.147 |

The v7 size column counts catalog pages. Its copy timing covers the full 474 or 1,895 MiB SQLite partition. Scratch sizes and copy times cover the projected catalogs and their indexes. Each copy is a fresh destination file on the same guest disk, with three sequential samples. The v7 scan rebuilds the three legacy catalog roots once. The scratch scan is the median of three passes that verify foreign-key integrity and hash each unique decoded body once. This scan omits signed reference reconstruction, the orphan check, logical batch-chain verification, and runtime replay. The exact reconstruction timing includes the scratch proof against the v7 roots. Copy time excludes the production backup fence and any concurrent load. Cache state was uncontrolled. The tests used reduced synthetic fixtures in a shared Colima Linux arm64 guest, so these are diagnostics with neither full reference workload nor native platform qualification.

The physical projection retains 641 and 2,561 exact unique records respectively. The 512-source fixture has 128 MiB of original source bodies and about 616 MiB of unique serialized record bytes. Raw deduplication removes cross-catalog copies while leaving that serialization overhead. Adaptive zlib saves disk space but made the verification cost worse in this test. Keep raw storage as the candidate for the next experiment.

Evidence identity is in [fixture audits](linux-fixtures.jsonl) and [raw timing samples](linux-results.jsonl). The installed product wheel is from `97493402` with SHA-256 `bf201518dff8c6742ad66d4508a0162dd58bbda15d44072a32a326078ef86bc6`. The guest ran Python 3.12.16 and SQLite 3.40.1. To rerun on the audited snapshots, mount the volume holding `baseline-128` and `baseline-512` at `/work`, supply the probe module on the test package path, and place the fixture audit beside `run_probe.py` as `fixtures.jsonl`. Run as the unprivileged fixture owner with scratch space in that volume. The runner refuses a changed signed tuple or size. Six local warning-as-error tests passed, including changed ordinal, invalid size, dangling or retargeted reference, changed metadata, and source overwrite prevention. Ruff and scoped Pyright passed.

Independent contract tracing confirmed that the v7 manifest binds exact stored UTF-8 bytes and typed selectors, while the logical batch checksum uses normalized model content. Reconstruction must preserve both checks. The trace also identified archive task selection, source admission, forensic export, logical chain validation, and staged migration as release verification boundaries. These are captured in the draft. This was a targeted feasibility review, with whole-design approval still pending.

## Next Action

Measure a production-shaped raw verifier with sequential payload reads and signed reference closure, including the first memory-plane read, against the existing acquisition budget before proposing a format change.
