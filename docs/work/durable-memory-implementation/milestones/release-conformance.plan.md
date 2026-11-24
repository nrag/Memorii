# Release Conformance

- Parent WorkPlan: [durable-memory implementation](../implementation.plan.md)
- Delivery fidelity: Level 3 first production release
- Status: active. Closeout plan recorded November 23, 2026. All work below awaits current-candidate evidence.
- Requirements: DUR-01 through DUR-18, with specific gap allocations below
- Repository baseline: clean codex/durable-memory-release at 4c390de14d63fd1e13961e77bcca2f6b82f693f5
- Release candidate: unset until implementation gaps and support decisions close

The [durable-memory design](../../../design/durable_execution_and_solver_runtime.md) and [coverage ledger](../coverage.md) govern acceptance. OpenAPI generation landed at 99e334e2, the TypeScript SDK and CI integration jobs landed later, and pinned host container and macOS conformance jobs now exist. The [October 5 semantic-forgetting readiness record](../../semantic-forgetting-implementation/implementation.plan.md#first-release-readiness-statement-confirmed-2026-10-05-12ecb2f4-and-bf63c8bd-full-suite-ci-green) records 58/58 CI jobs on code head 12ecb2f4. Treat that run as historical evidence. Establish current PR #124 head, base, required checks and reviews before binding any evidence to a release candidate. The remote PR state was unavailable during planning.

## Order And Ownership

| Work | Owner role | Dependency and exit evidence |
| --- | --- | --- |
| Production delivery | Runtime and provider owners | Start here. Installed path delivers both outbox kinds and recovers safely. |
| Operator workflow | Storage administration and release owners | Start migration and key preparation alongside delivery. Run the packaged workflow once the delivery changes are integrated. |
| Supported hosts and capacity | Harness and storage owners | Prepare fixtures in parallel. Make support decisions and finish proofs before candidate freeze. |
| Quickstart and release conformance | Documentation and release owners | Draft against the actual install paths in parallel. Validate the quickstart and sign and qualify artifacts after scope and implementation settle. |

These are role assignments. The implementation coordinator assigns people and keeps one writer for overlapping files. The parent index owns the single current next action.

## Production Delivery

The [durable-delivery implementation WorkPlan](../../durable-delivery-implementation/implementation.plan.md) owns this bounded work against approved design SHA a51ec4e0. It supersedes the earlier outbox implementation assumptions and records the existing code paths and verification limits. Status is proposed. Require its signed delivery and older-restore closure before enabling the managed worker and qualifying release. Reference capacity belongs to the same child. This release packet retains installed operator, host support, artifact and release closure obligations.

## Operator Workflow

**DUR-08 through DUR-13 and DUR-18.** Reconcile the migration packet against the current CLI and authority paths. Close any missing supported staging, external key/catalog validation and rollback commands. Rehearse installation from the wheel, owner-authorized JSONL adoption and cutover, backup verification and restore into a fresh installation with the current independent control anchor. Prove unchanged canonical history, legacy snapshots retained for rollback, safe pre-write rollback and refusal to return to stale JSONL after new SQLite writes. Verify that revocations and forgetting still apply after restore. Retain the existing crash-cut and all-writer fence tests.

Revalidate the recorded eligibility-epoch item against the current pending-epoch publication code. Close it with a real-path proof that a mode or grant change racing a delivery, write or restart cannot expose stale state. Record the current result instead of carrying the old open label forward.

The installation owner supplies the approved backup and signing configuration through the existing key owner and release environment. Record the status of backup encryption key rotation and release asset signing separately. Rehearse rotation and restore with disposable keys first. The release evidence records key identifiers, archive compatibility and successful restore across the supported rotation boundary. Keep secret material in the key owner. Production rotation and publication are scheduled owner operations.

## Supported Hosts And Capacity

**DUR-06, DUR-11, DUR-13, DUR-17.** Reuse the existing pinned journeys for OpenClaw, Pi and Hermes. Confirm the final artifact and version for each. Add or confirm the OpenClaw forwarded-input assertion in the real journey. For Hermes, prefer a supported surface that demonstrably sends completed-turn evidence. Certify automatic capture across two turns and restart on that surface. If the pinned primary CLI still omits the callback and no supported alternative passes, obtain an explicit scope decision before advertising automatic capture and make the limitation visible in the support table and quickstart.

Run the design reference workload on Linux and macOS and publish workload sizes, latency percentiles, replay and reopen times, verification acquisition, backup pause and storage growth. Use the existing 200-task test as a regression check. If the full reference workload misses a published budget, optimize and retest or obtain explicit approval for a smaller measured support envelope and update the design and release claims. Record environment, fixture version and artifacts for comparison.

## Quickstart And Release Evidence

**DUR-13, DUR-14 and aggregate closure for DUR-01 through DUR-18.** Update the README with one certified installed harness journey. A new user can install, connect that harness, save a fact, restart and recall it by following the instructions on a clean machine. Document supported versions and surfaces, backup and restore, migration and rollback cutoff, status and diagnostics, and the difference between logical forgetting and physical erasure. Run the instructions verbatim against the release build.

Once the changes above and any owner decisions are closed, freeze the reviewed revision and build the wheel, sidecar distribution and SDK package. Verify generated schema and tool parity and package contents, record artifact hashes and signing evidence, and run installed checks outside the checkout on supported platforms. Bind required CI jobs, host proof, migration and recovery artifacts, capacity measurements and governing live component certification to the exact candidate or explicitly identified execution SHA. Use the current workflow definitions and record run URLs. Complete the fresh spec, correctness and test review of the whole branch, reconcile every requirement and record the empty remaining validated P1/P2 list only after closure. Refresh affected evidence if the candidate changes.

The agent-benefit benchmark and the three endpoint-level forgetting walks retain their recorded post-release deferrals. Existing component certification remains in scope under the [certification policy](../../../development/benchmark_certification.md).

## Verification Anchors

Run from memorii/ with the appropriate CI interpreter and dependencies. These are existing regression anchors. Add the real production delivery and installed journey tests to the applicable enforced gate through the linked testing workflow when implementation begins.

```bash
python -W error -m pytest tests/unit/core/test_runtime_command_dispatch.py tests/unit/core/test_storage_administration_operator.py tests/unit/core/test_control_format_migration.py -p no:cacheprovider
python -W error -m pytest tests/integration/test_memory_plane_migration_recovery.py tests/integration/test_measured_capacity_envelope.py -p no:cacheprovider
python -W error -m pytest tests/integration/hostcompat/test_container_certification_journeys.py -p no:cacheprovider -ra
```

Check that the native-host journeys actually ran. A skip does not qualify an advertised host. Use the [gate ledger](../gates.md) and current workflows for full deterministic and installed checks. Record evidence separately for implemented, locally verified, CI enforced and operationally verified paths.
