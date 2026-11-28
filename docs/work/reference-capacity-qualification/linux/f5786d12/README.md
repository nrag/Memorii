# Dedicated Native Linux Staged v8 Rerun

- Tested revision `f5786d127101ff5f828f9ababa40964f6915a503`
- Wheel SHA-256 `2f227a683f722e4b9c30db16eb6ce29cc997f9047eed6f2bb87fdd3090683d3f`
- PhoenixNAP `s1.c1.medium`, Amsterdam, Ubuntu 24.04, Xeon E-2276G, 128 GB RAM and local NVMe/ext4
- Both serial workloads completed on November 25, 2026 Pacific time
- Staged format v8 with ordinary verification. v7 remains the installation default.

| Operation | p95 budget | Balanced p95 | Concentrated p95 |
| --- | ---: | ---: | ---: |
| Startup acquisition | 10 s | **10.89 s** | **10.97 s** |
| Checkpoint resume | 5 s | 2.72 s | 2.76 s |
| Backup publication pause | 5 s | 5.30 ms | 5.20 ms |
| Sequential state read | 250 ms | 4.85 ms | 4.45 ms |
| Sequential command commit | 500 ms | 33.91 ms | 34.16 ms |

Both workloads failed only startup acquisition. All ten acquisition attempts
per distribution succeeded and counted toward nearest-rank p95. All other
series completed with zero sample errors and zero driver retries. Contended
source capture p95 was 21.92 s balanced and 21.97 s concentrated, with zero
capture errors. Contended command commit p95 was 22.39 s and 22.57 s. The
contended series have no latency budgets.

On November 26, the owner accepted an 11 s acquisition p95 budget for the
release. Both recorded acquisition series meet that budget. The table and
JSON retain the original 10 s qualification decision.

Compared with the original Linux measurements, acquisition improved from
11.52 s and 11.54 s. The rerun used the same CPU model and a larger memory
and storage configuration, so comparison describes the observed runs and
cannot isolate the effect of code changes. Startup missed the original 10 s
limit by 0.89 s balanced and 0.97 s concentrated.

Both fixture audits matched the reports' signed tuple, checkpoint, graph and
source inventories. Each selected v8 fixture had 4,096 retained sources,
100,000 runtime events and a 1,000-event tail. The local collection verified
the three report checksums, wheel, driver, dependency lock and builder lock
identities, and all attempt counts. The fixture builder's diagnostic status
describes the untimed fixture preparation. The qualification verdict comes
from the separate timed driver.

[Native preflight](preflight.json), [balanced report](balanced-measurement.json),
and [concentrated report](concentrated-measurement.json).
