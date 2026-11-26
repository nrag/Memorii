# Dedicated Native Reference Capacity Qualification

- Work type: testing
- Delivery fidelity: Level 3
- Status: both dedicated ordinary-v8 Linux workloads meet the owner's revised 11 s budget. Exact-candidate native macOS qualification remains open.
- Branch: `codex/durable-delivery-implementation`
- Starting head: `ba1e7baab0626aaa32c36a350876c0c3b952b337`
- Parent: [reference capacity milestone](../durable-delivery-implementation/milestones/reference-capacity.plan.md)

## Objective And Completion Contract

Qualify an exact installed wheel for owner-staged v8 on dedicated native Linux and macOS machines with local SSDs. Complete the balanced and concentrated workload on each host. Keep v7 as the installation default. Require one candidate SHA and matching wheel and driver identity in all four reports, audited fixture and checkpoint identities, the full warm, cold, contended, and growth series, error and retry accounting, and every design budget met. The capacity contract is in [the durable runtime design](../../design/durable_execution_and_solver_runtime.md#capacity-and-service-envelope).

## Scope And Invariants

The GitHub workflow and test-only fixture and measurement drivers own this evidence. Apply the governing capacity budgets. Keep product defaults, counts, formats, and authorized storage owners unchanged. Stage v8 through an exact-current backup, restore plan, preview, and owner-authorized cutover before creating source receipts or checkpoint state. Include the cutover event in the verified mandatory count, then fill to exactly 100,000 events with the last 1,000 in single-event batches. Make the measurement driver reject the wrong format before timing. Retain v7 diagnostic coverage. Dedicated idle attestation must report actual hardware and scheduling conditions. A shared Mac or a Docker guest provides diagnostic evidence only.

## Test Portfolio And Failure Matrix

| Contract | Canonical path | Owner | Failure signal |
| --- | --- | --- | --- |
| Both formats retain local source and replay closure | Signed fixture and owner-staged v8 cutover | `test_reference_capacity_fixture.py` | Counts, source receipts, checkpoint or exact tail differ after fresh open |
| The target format reaches the real warm and cold roots | Existing installed capacity test driver | `test_reference_capacity_measure.py` | Warm attempts, write growth, cold sample, checkpoint or backup measurement fails |
| Platform and admission envelope | Platform preflight and workflow attestation | `test_reference_capacity_measure.py`, `reference-capacity.yml` | Wrong OS, unattested runner, or wrong stored format fails before timing |
| Staged authorization, failure, and rollback | Production backup and generation change owners | `test_raw_memory_payload_upgrade.py` | Wrong preview or authority accepted, tampering released, or rollback path lost |
| Release budgets and exact attempt accounting | Existing four-cell GitHub matrix output | `reference-capacity.yml` | Setup, sample, retry or budget violation fails the report |

## Workflow And Runtime

The manual workflow builds one wheel and runs both distributions serially on each profile. Its qualification job requires `self-hosted`, the matching OS label and `memorii-reference-capacity`, plus `MEMORII_REFERENCE_RUNNER_DEDICATED_IDLE=true`. Provision one idle host per OS with at least four logical cores, 16 GiB memory, and adequate local SSD scratch for both fixtures and their per-series copies and archives. Provide native ICU development headers and `pkg-config`. Keep the toolchain and dependency locks from the selected revision. The two runner jobs each have a 2,880-minute timeout.

The formal driver starts every acquisition sample from a fresh fixture copy in a new process as defined by the design. Its results reflect that procedure. The earlier native SSD diagnostic separately verified zero resident main-database pages before each timed acquisition.

## Progress And Evidence

- GitHub repository runner inventory returned zero registered runners on 2026-11-24. The dedicated-idle variable was absent. The workflow lookup returned 404 and the repository's default branch `main` did not contain its workflow file. No qualification job was dispatched.
- The former workflow would have measured v7 because the fixture began from default initialization. The branch now passes the staged-format option to preflight, fixture preparation and every timed qualification. The fixture reopens after cutover and creates generation-bound source receipts and a checkpoint in the selected generation.
- Format numbers remain persisted schema identities. `--raw-payloads` reuses the existing owner CLI terminology and applies only to these test-driver invocations.
- The 28 focused fixture, driver, upgrade, and capacity regression tests passed locally and again from an isolated installation of `9d3436378321719a650329bb26165ac65c6d7e60`. The driver matched the installed inventory to wheel SHA-256 `25b040fa8a570ce7247dfcd7e24562c6e6b0bea9ec15e672e83ed64861f83b65`. Scoped Ruff, Pyright, and repository identity checks passed. An independent correctness reviewer found no validated P1/P2 in the format wiring. The formal run was unavailable and remains unverified.
- The owner reserved this native Mac for a direct run and authorized one disposable PhoenixNAP host for Linux. Both use the same frozen `8e570195` candidate and wheel. The [Linux balanced report](linux/8e570195/README.md) records 11.52 s startup acquisition p95 against the 5 s budget. The remaining dedicated measurements still apply even though the Linux balanced release gate failed.
- The [complete Linux evidence](linux/8e570195/README.md) records an 11.54 s concentrated startup p95 and two contended source capture errors. Both Linux fixtures retained the exact source and replay counts. After action-time confirmation on November 25, the provider inventories showed the disposable host and its billed IPv4 allocation were gone.
- The [native macOS evidence](macos/8e570195/README.md) records 9.61 s balanced and 9.66 s concentrated startup p95, plus three balanced contended source-capture errors with the same pending-publication recovery signal as Linux. The two original reports survived an overnight launcher publication failure and were collected manually.
- On both platforms and distributions, checkpoint resume, exclusive backup pause, and sequential state read and command commit passed. Startup acquisition took 9.61 to 11.54 s p95. Contended command commit took 32.42 to 44.85 s p95. The small backup pause measures only publication fences. The earlier custom Mac cold diagnostic used a different fixture preparation and measurement procedure. These runs establish the full acquisition miss without isolating its component-level cause.
- The [exact-fixture debugging results](../reference-capacity-debugging/debugging.plan.md) isolate startup components and repeated full verification under contention. The ordinary publication race has a deterministic correction. This does not close the performance gate, and all four qualification cells remain bound to the original candidate.

## Ten-Second Acquisition Reassessment

On November 25, 2026 the release owner approved a 10 s verified acquisition
p95 budget at the same workload and sample count. The timed region still
starts at the verified snapshot request. Tier A/Tier B checks, backup pause
and checkpoint resume budgets, error accounting, and fixture sizes are
unchanged. The updated driver re-scored the ten original acquisition samples
per workload after checking each report hash. The archived reports retain
their original budget, statuses, and exact revision.

| Native workload | Archived acquisition p95 | At 10 s | Other failed series in that report |
| --- | ---: | --- | --- |
| Linux balanced | 11.52 s | Fail | None |
| Linux concentrated | 11.54 s | Fail | Two contended source capture errors |
| macOS balanced | 9.61 s | Pass | Three contended source capture errors |
| macOS concentrated | 9.66 s | Pass | None |

The [later native macOS startup recheck](../sealed-custody/supervisor-sealed-startup-macos.jsonl)
includes ordinary, exact-v8 acquisition of 8.63 s balanced and 9.01 s
concentrated, one sample each. Treat that as diagnostic support for qualifying
ordinary v8 under the revised budget. The historical publication error has a
deterministic fix and needs confirmation in the complete contended series on
the new candidate. Sealed startup has its own approval and qualification path.

Default promotion also requires a real fresh-v8 initialization and lifecycle
proof. The current initializer writes the v7 schema, and the v8 raw catalogs
are installed through the explicit staging route. Preserve the legacy-to-v7
staging target and archive compatibility when implementing fresh v8. Verify
first publication, reopen, backup, restore and owner-authorized existing-v7
cutover, including its documented rollback behavior. See the
[raw-format migration contract](../../design/sqlite_memory_payload_storage.md).

## Owner Sign-off At Eleven Seconds

The [dedicated Linux rerun](linux/f5786d12/README.md) on `f5786d12` recorded
10.89 s balanced and 10.97 s concentrated startup acquisition p95. On
November 26, 2026 the release owner accepted 11 s p95 at the existing workload
and deferred further startup optimization until after release. The updated
driver re-scored the ten original acquisition samples per workload after
verifying the original report hashes. Both meet the revised limit. All other
budgeted series passed and every series recorded zero errors and retries,
including contended source capture. The concentrated p95 clears the new
limit by 26 ms. The original signed evidence coordinates, report budgets and
verdicts are preserved.

The same wheel passed 63 installed-wheel smoke checks on native macOS,
including staged fixture generation, migration recovery, and operator
controls. The revised reference driver passed 14 focused checks, including
the exact acquisition-budget boundary.

The release scope is ordinary v8 through owner-authorized staged upgrade.
Keep v7 as the installation default. Tier A and Tier B integrity, workload
sizes, sample counts and other budgets remain unchanged. Sealed startup and
further startup optimization are deferred. Fresh-v8 initialization and
default promotion have their own gates.

## Next Action

Qualify both dedicated native macOS workloads with the immutable Linux-tested
`f5786d12` wheel and driver. Adjudicate acquisition against the approved
11 s policy transparently, keeping the original tool output and candidate
identity. The older Mac reports used a different wheel. Reusing the
Linux-tested artifact avoids repeating the Linux measurements for a
threshold-only change. The parent release conformance packet owns installed
owner and harness journeys, exact artifact verification and release review.
