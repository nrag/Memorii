# Benchmark certification

Live benchmark evidence is valid only for the exact clean commit that produced it. The
`Scheduled Benchmark Reports` workflow enforces this by checking out one full commit SHA,
verifying `git rev-parse HEAD`, requiring a clean source tree, and exporting the same value
as `MEMORII_SOURCE_REVISION` to every benchmark process.

For a release candidate, dispatch the workflow with the full commit SHA in
`source_revision`. Leaving the input empty certifies the workflow's triggering revision.
Scheduled runs certify the scheduled default-branch revision.

The matrix jobs upload source-bound reports. The aggregation job rejects mixed revisions,
dirty or unversioned source states, insufficient seeds or replicates, provider/fallback
rates above policy, weak confidence bounds, and inadequate simulated interval coverage.
It then validates `live_runtime_gate_summary.json` as `LiveGateSummary` and requires both
the gate summary and its coverage certificate to name the requested commit.

PR gates remain deterministic and credential-free. They run unit, static, packaging, prompt,
and fake-oracle benchmark contract checks against `${{ github.sha }}`. Live certification is
an explicit post-commit gate because a statistically meaningful run is costly and requires
provider credentials; it must never be inferred from a developer's dirty working tree.
