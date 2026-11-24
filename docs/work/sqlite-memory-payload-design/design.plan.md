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

## Sequential Raw Verification

The rowid projection retains a unique digest index for lookups and reads physical payloads by rowid. Each scan compares compact catalog roots derived from the base tables, checks that the digest index matches the base-table mapping, rejects broken links and orphan bodies, and hashes each raw BLOB exactly once. The conversion verified the original three v7 catalog commitments again after changing the layout. This runs in scratch with an in-memory expected manifest. Production must authenticate that manifest through the selected signed tuple and verify the closed physical schema before querying it.

| Sources | v7 acquisition | Raw select scan | Raw BLOB scan | v7 first point read | Projected first point read |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 128 | 0.301 s | 0.070 s | 0.067 s | 0.255 s | 0.228 s |
| 512 | 1.242 s | 0.274 s | 0.266 s | 1.015 s | 0.935 s |

These are medians from three samples per measurement, with no mmap in the table. The BLOB variant uses 256 KiB chunks. The scan omits unchanged runtime catalogs and checkpoint replay, which are included in the v7 acquisition. The projected first read validates the original batch checksums, ordered members and signed revisions before returning a record equal to the installed v7 store result. The operating-system cache was uncontrolled. Each baseline sample used a new service handle in the same process. The [runner](run_sequential_probe.py) and [samples](linux-sequential-results.jsonl) pin the revision and fixture digests. The projected 512-source scan with mmap was 0.235 s. Prefer the bounded BLOB variant without mmap to avoid depending on mapped-file behavior.

Independent review reproduced a matched body and digest mutation on only a table page, leaving the lookup index unchanged. The original scratch verifier accepted that split because SQLite satisfied the manifest scan from the old covering index. Commit `f0d8e8a0` roots metadata in the base table and compares the complete base-to-index mapping before either scan mode. Independent retesting confirmed rejection of table-page substitution and index-only corruption in both modes. The focused projection test also preserves a signed zero-member batch and its unchanged data revision.

The first-read trace identified an independent memory cost in v7. The store loaded all batch JSON before validating the first requested record. Commit `0fa7c12d` streams those rows inside the same transaction and keeps checksum, visibility and revision checks. Its regression tests corruption in the last batch before release of a record from the first batch. Three fresh macOS Python processes per version showed 65.33 MiB peak Python allocation before the change and 1.33 MiB after it for a point read over 256 historical batches containing one 256 KiB record each. Tracing began after the store opened and measured Python allocations only. The Linux comparison still uses the previous immutable wheel as the baseline.

The combined storage, provider authority, migration and probe suite passed 208 cases. The pending-publication third-state quarantine case and managed-partition factory case failed identically on the clean pre-change `e5878975` archive. Both baseline failures remain open.

The current record also contains two literal copies of each source body plus two more inside base64-encoded Step-1 evidence. This accounts for the residual size after eliminating the three catalog copies. Changing those logical fields would change existing evidence and hash contracts. Any physical encoding experiment must recover those exact bytes.

## Full Concentrated Linux Diagnostic

The installed reference fixture driver built and audited 200 tasks, 4,096 native sources totaling 1 GiB, 10,000 execution nodes, 50,000 solver nodes and 100,000 signed events with a 1,000-event checkpoint tail. It used the approved concentrated allocation. The [fixture audit](linux-reference-fixture.json) binds the exact signed tuple, source receipts, graph and event inventory. The buffered sequential projection retained 4.849 GiB and matched all three original signed v7 memory catalog roots. The timing samples use the same pinned wheel, probe and runner as the reduced diagnostics.

| Operation | Median | Maximum |
| --- | ---: | ---: |
| Installed v7 acquisition | 18.674 s | 19.944 s |
| Installed v7 first point read after acquisition | 11.353 s | 13.767 s |
| Projected raw catalog verification with 256 KiB BLOB reads | 2.269 s | 2.278 s |
| Projected first point read with original batch checksums | 7.346 s | 7.443 s |

These are three same-process samples per operation with uncontrolled cache state. The raw verification timing includes the reference and digest-index checks. It excludes the full runtime catalogs and signed checkpoint/head replay. The first point read still walks every historical memory batch. The [full-size samples](linux-reference-results.jsonl) preserve all timings. The guest, one workload distribution, sample count, and experimental projection do not meet the production qualification contract.

A separate traced v7 acquisition on the same signed 14.899 GiB partition spent 20.188 of 23.511 seconds scanning the three memory catalogs. A SQLite statement trace measured from each catalog's ordered query to the next statement. The remaining 3.323 seconds covered other catalog, control, and runtime-history work. Combining that single residual sample with the 2.269-second projection median gives a rough budget estimate of 5.592 seconds. The paths ran separately with different cache states, so the estimate establishes acquisition risk and provides no installed result. Raw deduplication is the candidate for staged integration, with no demonstrated margin against the five-second budget. The newer generation must be timed as a whole, and the non-memory phase is an optimization target if it still consumes most of the margin.

To rerun the full diagnostic, use the installed fixture driver's `_prepare` with `task_allocations("concentrated")` and `event_fill_inputs` in `/work/baseline-4096`. Keep the resulting signed fixture immutable and run `run_sequential_probe.measure(4096, audit.partition_tuple_digest)` in the same isolated image. Fresh setups produce different signed tuple IDs. The preceding reduced-fixture run records the same probe and runner identities used for the full timing run.

## Next Action

Freeze and review the staged raw format contract so an owner-authorized implementation can measure complete acquisition, first read and actual backup pause on the full fixture.
