# Dedicated Native Reference Capacity Qualification

- Work type: testing
- Delivery fidelity: Level 3
- Status: both Linux runs completed and failed the startup budget. Dedicated macOS is scheduled.
- Branch: `codex/durable-delivery-implementation`
- Starting head: `ba1e7baab0626aaa32c36a350876c0c3b952b337`
- Parent: [reference capacity milestone](../durable-delivery-implementation/milestones/reference-capacity.plan.md)

## Objective And Completion Contract

Qualify an exact installed wheel for owner-staged v8 on dedicated native Linux and macOS machines with local SSDs. Complete the balanced and concentrated workload on each host. Keep v7 as the installation default. Require one candidate SHA and matching wheel and driver identity in all four reports, audited fixture and checkpoint identities, the full warm, cold, contended, and growth series, error and retry accounting, and every design budget met. The capacity contract is in [the durable runtime design](../../design/durable_execution_and_solver_runtime.md#capacity-and-service-envelope).

## Scope And Invariants

The GitHub workflow and test-only fixture and measurement drivers own this evidence. Keep product defaults, budgets, counts, formats, and authorized storage owners unchanged. Stage v8 through an exact-current backup, restore plan, preview, and owner-authorized cutover before creating source receipts or checkpoint state. Include the cutover event in the verified mandatory count, then fill to exactly 100,000 events with the last 1,000 in single-event batches. Make the measurement driver reject the wrong format before timing. Retain v7 diagnostic coverage. Dedicated idle attestation must report actual hardware and scheduling conditions. A shared Mac or a Docker guest provides diagnostic evidence only.

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
- The [complete Linux evidence](linux/8e570195/README.md) records a 11.54 s concentrated startup p95 and two contended source capture errors. Both Linux fixtures retained the exact source and replay counts. The browser requires action-time confirmation to permanently delete the disposable host and release its IPv4 allocation.

## Blockers And Next Action

After action-time confirmation, deprovision the disposable Linux host and billed IPv4 allocation. The native macOS run is scheduled on the owner-reserved workstation. Keep v7 as default while the release gate is open.
