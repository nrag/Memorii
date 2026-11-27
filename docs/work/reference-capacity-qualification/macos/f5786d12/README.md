# Dedicated Native macOS Staged v8 Qualification

- Tested revision `f5786d127101ff5f828f9ababa40964f6915a503`
- Wheel SHA-256 `2f227a683f722e4b9c30db16eb6ce29cc997f9047eed6f2bb87fdd3090683d3f`, identical to [the native Linux run](../../linux/f5786d12/README.md)
- Dedicated Apple M6, 12 logical cores, 32 GiB RAM, native APFS SSD, Python 3.12.16 and SQLite 3.54.1
- Both workloads ran serially between 09:41 and 11:45 Pacific on November 26, 2026
- Ordinary owner-staged v8. The installed default remains v7.

| Operation | Approved p95 budget | Balanced p95 | Concentrated p95 |
| --- | ---: | ---: | ---: |
| Startup acquisition | 11 s | 8.06 s | 9.01 s |
| Checkpoint resume | 5 s | 1.42 s | 1.46 s |
| Backup publication pause | 5 s | 5.55 ms | 4.65 ms |
| Sequential state read | 250 ms | 2.60 ms | 4.54 ms |
| Sequential command commit | 500 ms | 22.57 ms | 23.34 ms |

Every budgeted series passed. Both workloads completed with zero sample
errors and zero driver retries. Contended source capture p95 was 11.19 s
balanced and 14.34 s concentrated. Contended commit p95 was 11.43 s and
10.93 s, respectively. Contended series report latency without a budget.

Report checksums, candidate and driver identities, dependency locks, sample
counts and fixture audits were verified. Both selected v8 fixtures had
4,096 retained sources, 100,000 runtime events and a 1,000-event checkpoint
tail. The original reports retain the frozen driver's 10 s gate. The
[macOS adjudication](adjudication.json) and [Linux adjudication](../../linux/f5786d12/adjudication.json)
apply the approved 11 s gate from `9d661a3b` to the unchanged samples. All four
workloads pass under that policy.

[Native preflight](preflight.json), [balanced measurement](balanced-measurement.json),
and [concentrated measurement](concentrated-measurement.json).
