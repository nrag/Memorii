# Dedicated Native macOS Reference Capacity

The reserved Apple M6 workstation ran both workloads on its native APFS SSD with the same `8e57019533f1d28497253da370765561168ed8f0` candidate and wheel SHA-256 `db4fc4db38c6ace39dbbfdc27bbf5ae6621f04386bf587214abc1d33d48cda8e` as Linux. The overnight measurements finished on November 24, 2026, at 11:10 p.m. Pacific. Both reports include audited staged v8 fixtures with 4,096 sources, 100,000 runtime events, and 1,000 checkpoint-tail events.

| Operation | Budget | Balanced p95 | Concentrated p95 |
| --- | ---: | ---: | ---: |
| Startup acquisition | 5 s | 9.61 s | 9.66 s |
| Checkpoint resume | 5 s | 1.41 s | 1.41 s |
| Backup publication pause | 5 s | 5.56 ms | 7.24 ms |
| Sequential state read | 250 ms | 2.14 ms | 3.25 ms |
| Sequential command commit | 500 ms | 21.74 ms | 27.61 ms |

Both workloads failed startup acquisition. The balanced run also recorded three contended source-capture errors requiring pending publication recovery. Contended command commit p95 reached 33.07 s balanced and 32.42 s concentrated. The contention series have no separate latency budget.

The overnight launcher failed after measurement while formatting the evidence summary. An unquoted shell heredoc interpreted Markdown backticks as commands and the failed publication caused repeated launches. The launcher was removed. The two original timed reports and matching hashes survived. The restarts replaced the separate fixture output files and preflight report, so the signed fixture audit embedded in each original measurement report is the retained evidence. No timing from the restarts is included.

[Balanced report](balanced-measurement.json) and [concentrated report](concentrated-measurement.json).
