# Dedicated Native Linux Reference Capacity

- Tested revision `8e57019533f1d28497253da370765561168ed8f0`
- Wheel SHA-256 `db4fc4db38c6ace39dbbfdc27bbf5ae6621f04386bf587214abc1d33d48cda8e`
- Host PhoenixNAP `s1.c1.small`, Ubuntu 24.04, Intel Xeon E-2276G, 64 GB RAM, local 1 TB NVMe, ext4
- Format v8 through the owner-staged fixture cutover. v7 stays the installation default.

## Balanced

The full balanced suite finished with 100 measured calls per warm series, 10 per cold series, and zero sample errors or driver retries. Startup acquisition exceeded its five-second limit. All other budgeted series passed.

| Operation | p95 | Budget | Result |
| --- | ---: | ---: | --- |
| Sequential state read | 4.92 ms | 250 ms | Pass |
| Sequential command commit | 34.60 ms | 500 ms | Pass |
| Startup acquisition | 11.52 s | 5 s | Fail |
| Checkpoint resume | 2.64 s | 5 s | Pass |
| Backup publication pause | 5.38 ms | 5 s | Pass |

Sequential source capture p95 was 82.47 ms. Under contention, state read p95 was 10.74 s, source capture p95 was 44.10 s, and command commit p95 was 44.67 s. These series have no separate latency budget. The dominant elapsed cost was the contended command series, where the foreground thread was observed waiting on a file lock while background commands had committed. A live database count of 4,096 retained sources was expected for that command series and does not establish failed source captures.

[Balanced fixture audit](balanced-fixture.json) and [complete measurements](balanced-measurement.json).

## Concentrated

The second distribution started fixture preparation after the balanced report completed. Its evidence remains pending.
