# Durable Delivery Verification

- Work type: testing
- Delivery fidelity: Level 3 first production release
- Status: active
- Coordinator: durable delivery implementation task
- Created and updated: 2026-11-23
- Parent: [durable delivery implementation](../durable-delivery-implementation/implementation.plan.md)
- Canonical inputs: design a51ec4e0, implementation baseline fd74fc49, live workflow .github/workflows/pr-gates.yml
- Expected outputs: reusable contract, installed paths, concurrency, restore and qualification evidence

## Objective And Boundaries

Prove that origin and effect authority run through installed roots, with complete persistent output and no duplicate effect after restart or restore. Keep semantic, provider and legacy fixture paths distinct. Use the linked validation ledger for all requirement families. The release fixture stays in the engineering qualification tier. This operation owns test placement and runner/gate changes. Product contracts belong to the linked design/implementation.

## Phase One Test Matrix And Existing Anchors

| Behavior | Proof layer and oracle | Existing owner and intended gate |
| --- | --- | --- |
| Authenticated origin, canonical intent and operation identity | Unit: verify exact closed proof fields and signature; stale/divergent intent refuses with unchanged signed revision and rows | test_runtime_command_dispatch.py under unit-test-shards |
| Recorder and spool normalized intent | Unit: keep pure digest/spool fixtures; managed tests assert matching durable proof and no overwrite for equal IDs in distinct namespaces/generations | test_runtime_event_consumer.py under unit-test-shards |
| Prepared and signed managed dispatch | Installed HTTP/embedded/CLI: valid authority, bounded scope and matching proof; malformed/proofless/forged/stale request leaves queue and store unchanged | test_runtime_sidecar.py under durable-runtime-integration |
| Durable consolidation | Restart via managed public pause/completion/resolution; inspect signed result bytes and evidence closure, valid same-kind siblings, exact retry, no automatic candidate staging | test_runtime_process_recovery.py and test_runtime_event_replay.py under existing durable and unit gates |
| Public API body and client compatibility | Generated Python/TS parity and installed package test; test proof header/context but keep wire bodies and original receipt presentation | test_runtime_schema_export.py and sdk-typescript |
| Explicit compatibility fixtures | Seeded replay/checkpoint/capacity helpers remain storage probes unless they use managed issuance. Migrate actual host certification positives to the managed path. | test_runtime_resume_checkpoint.py, test_measured_capacity_envelope.py and hostcompat |

Independent test reviewer checked these paths at fd74fc49. The existing command and spool digests differ in treatment of expected_revision, so managed proof tests compare the same full canonical intent across all carriers. Retrying a valid proof cannot change its authenticated digest. Pure legacy fixture compatibility is acceptable only in a visibly separate nonmanaged constructor or on an unbound storage fixture. No proofless bypass through registered production roots. Verify installed roots with actual control-issued authority instead of treating the existing CLI allowlist as authority.

## Execution And Evidence

Phase one first slice is embedded origin proof and receipt dispatch. Extend the existing unit owner or add a small named origin suite under unit-test-shards. Before closure list exact new tests and timings, verify shard ownership and capture an applicable workflow result. Subsequent slices extend the installed roots and cover host decision, target effect and receipt, current mode and revocation races, and old-generation holds. Populate precise target tests and gate assignments before those edits. The current capacity probe remains a regression. A new production-shaped reference driver and OS jobs require their own reproducibility, runtime and scope proof before gating.

Use Python environment matching each workflow job. New dependencies or changed CI gates must be explicitly recorded. The SDK matrix and pre-existing release proofs are retained. Store executed command, cwd, Python/SQLite/toolchain, exit, candidate SHA, run ID and artifacts in the affected packet. A test suite passing locally does not advance CI evidence. All applicable reviewers confirm the coherent frozen candidate and any actual CI job changes before marking the parent requirement verified.

## Next Action

Qualify the reference capacity workload through installed owners once the fixture audit and authenticated checkpoint/tail path are complete.

## Gate Changes

The continuation uses the existing durable-runtime-integration job for `test_runtime_journal.py` and `test_managed_candidate_delivery.py`. They exercise the signed transaction, reopen and recovery paths, so they belong with the existing installed managed sidecar and runtime checks. This extends the selection without changing its 15-minute timeout or other gates. Local macOS runs used `pytest -W error -p no:cacheprovider` with Python 3.12. The GitHub job remains the Linux Python 3.11 owner.

The storage integration job now covers exact-current restore selection and stale handle fencing through `test_partition_generation_selection.py`. The runtime integration job covers the embedded host projection read through `test_managed_work_projection_recall.py`, including out-of-order target effects, reopen and origin-grant revocation.
