# Native Linux Fresh v8 Qualification

- Tested revision `f2b1e25a87e03dfe821e450ecd834fadadd854fc`, frozen before either timed workload.
- Wheel SHA-256 `2a8afdeca9e61bd908aee857464976e82748f0916919763b2f9c7473bf6da51d`.
- PhoenixNAP `s1.c1.small` in Ashburn, Ubuntu 24.04, Xeon E-2276G, 64 GB RAM, and local 1 TB NVMe with ext4.
- Both workloads ran serially from November 27 to 28, 2026 Pacific time. Each initialized v8 directly and used the full verified acquisition path.

| Operation | Approved p95 budget | Balanced p95 | Concentrated p95 |
| --- | ---: | ---: | ---: |
| Startup acquisition | 11 s | 10.961 s | **11.047 s** |
| Checkpoint resume | 5 s | 2.764 s | 2.782 s |
| Backup publication pause | 5 s | 44.84 ms | 74.50 ms |
| Sequential state read | 250 ms | 2.97 ms | 3.22 ms |
| Sequential command commit | 500 ms | 25.25 ms | 24.63 ms |

Balanced passed. Concentrated exceeded the startup budget by 47.36 ms.
Every other budgeted series passed. Every foreground and background sample
completed without an error or driver retry. Both acquisition series include
all ten attempts. Contended source capture p95 was 22.12 s balanced and
22.10 s concentrated. Contended command commit p95 was 22.75 s and 22.62 s.
The contended series are recorded without a latency budget.

Both signed fixture inventories matched the timed reports and contained
4,096 retained sources, 100,000 runtime events, and a 1,000-event checkpoint
tail. The collected reports matched their transport and driver checksums,
wheel identity, dependency lock and builder lock. The branch advanced while
the frozen workloads ran. The results apply to `f2b1e25a`.

[Native preflight](preflight.json), [balanced fixture](balanced-fixture.json),
[balanced measurements](balanced-measurement.json),
[concentrated fixture](concentrated-fixture.json), and
[concentrated measurements](concentrated-measurement.json).
