# Durable Intent And Output

- Parent: [durable delivery implementation](../implementation.plan.md)
- Status: active
- Requirements: DUR-01/02/03/05/06/07/12
- Dependencies: Readiness preflight and test-matrix review
- Closure identity: unset, record actual base, code head, dirty state and artifact/run digests before claim

## Observable Acceptance

The authenticated installed producer prepares and persists one origin proof before transmission. A valid command traverses runtime dispatch and publishes sealed output and required work-projection payload together. Reopening from a new process returns exactly the persisted result.

## Owners And Contract Changes

core/persistence/runtime_contracts.py, runtime_api.py, runtime_repository.py, runtime_events.py. core/harness_state/sidecar.py and consumer.py, tools/runtime_consume.py, core/consolidation, checkpoint and retention owners.

Close generation-scoped receipt identity and proof across HTTP header, embedded owner and spool. Derive typed outputs and omissions from verified producer evidence. Persist origin revision, canonical payload/digest, ordinals, manifest-backed archive closure and projection payload. Preserve task terminal semantics and actual owner fences. Fold versioned entity families into canonical replay and checkpoint coverage.

## Verification

Valid real prepare and dispatch plus restart. Unknown schema, missing/stale proof, divergent digests, reused operation across namespaces, duplicate output identity and missing archive must fail explicitly. Valid same-kind siblings with distinct ordinals survive replay. Prove full-state replay and no partial state on publication failure. Legacy digest-only rows retain identity and cannot be worker candidates.

Existing regression anchors from memorii/ in the applicable pinned CI environment:

```bash
python -W error -m pytest tests/unit/core/test_runtime_command_dispatch.py tests/unit/core/test_runtime_event_consumer.py tests/unit/core/test_runtime_event_replay.py tests/integration/test_runtime_sidecar.py tests/integration/test_runtime_process_recovery.py -p no:cacheprovider
```

New path proof commands and exact test names must be registered through the [validation ledger](../validation.md) before implementation. Include the affected workflow job and artifact evidence. Review against the exact commit. Evidence maturity is design specified at this baseline. This packet is complete only with local and applicable enforced proof and reviewed closure. It satisfies only its bounded portion of the parent requirements.

## Scope Boundary

Use the approved design and existing semantic owners. Keep unsupported roots visibly unavailable. Record compatibility and rollout deltas at the actual candidate. Parent owns release authorization and aggregate gate outcome.

## Progress And Review

Base fd74fc49. The independent test reviewer approved the bounded matrix and its fixture distinctions. 65600ca5 implements authenticated fixed-generation origin and sealed catalog storage. 32b39180 connects control-issued grants to managed embedded, HTTP and spool paths. Managed start saves the execution root and source-free pause and complete publish a signed root archive and an explicit omission set. Restart retains the authenticated receipt and sealed result. Full runtime event batch persistence and replay, source-backed output, all managed command roots, legacy rollout and exact candidate approval remain open.

Independent review reproduced an unsigned CLI admission path. The CLI now rejects unsigned producer admission and drain on managed catalogs. The old OpenClaw and Pi host certification journeys still rely on that legacy drain and require migration to managed issuance before they can certify. The managed request, origin signature and proof digests now use canonical typed encoding. Proofs from the preliminary branch revisions require reconciliation if they were already used. Existing legacy command digests and their namespace remain stable.

The runtime event codec now binds the complete envelope, including solver scope and commit status, with canonical typed encoding. The in-memory replay reducer detects conflicts against historical record-version reservations. Signed SQL append, the persisted replay indexes, typed catalog projection, and independently reconstructed replay remain open.

Continuation at 16d5b23c. An independent test reviewer approved the persistence matrix before coding. It covers signed-head/index/row co-commit, exact retry, materialization equality on reopen, both publication crash cuts, historical batch and index tamper and legacy catalog preservation. The delegated batch writer owns the SQLite DAO, journal, common publisher, acquisition and focused tests. The writer found that a memory-only publication reset the runtime head to genesis and wired preservation of the previous signed head. A new installation uses the v4 runtime catalog inventory. Existing v1-v3 formats keep their exact inventories, and an older populated partition is not represented as having a complete replay history.

The v4 runtime owner now appends signed chained batches and all three SQL binding indexes in the same transaction as the changed materializations. Acquisition verifies the batch chain, every index and exact current materializations. Pending-intent finalization verifies the prospective data before control advances. The bounded local check passed 89 tests including journal, managed lifecycle, smaller capacity, storage, command, recovery and forget coverage. Source-backed production consolidation, independently specified business-event payloads, older-generation activation and incremental manifest performance remain acceptance work.

Independent review reproduced same-connection unsigned writes surviving cached verification and a forged runtime revision escaping replay verification. The acquisition cache now checks both SQLite data version and local change count. Replay verifies the runtime revision and preserves it for no-op publication. Graph event payloads validate execution node and edge schema/key identity, solver edge schema/key identity and the closed solver node content union on append and on replay. Managed resume of a source-free root verifies its retained signed pause archive and receipt before updating the task and execution state. This does not extend resume to source-backed or solver-bearing managed tasks.

Checkpoint format v2 signs the content of every current checkpoint member from one SQLite snapshot. Earlier identifier-only checkpoints remain decodable but cannot serve as authenticated checkpoint evidence. Validation rejects altered member content even when IDs and counts match. The full checkpoint and authenticated tail owner remains open.

Continuation at 46fd5ea2. An independent test reviewer approved the native-source path with exact current ingress, provider admission index/fence, trusted runtime task and provider delivery binding, and source suppression checks. The provider adapter reconstructs authority from the installed signed partition rather than trusting public event task metadata. The embedded managed observation entry commits a metadata-only admission receipt and task version together. The provider source retains its original protected visibility. Actual Hermes provider capture, managed observation, restart, retry and source suppression are exercised in the durable-runtime test family.

Decision needed for the disconnected provider case. A live provider authorization works for the embedded observation and its retry. Later archive and offer reads, host decisions and the enrolled delivery worker need a provider-authorized release boundary of their own. An exact task/source grant with durable revocation and a requirement for fresh provider authorization on every use are distinct cross-session release policies. Until selected, source-backed pause and offer exposure stay unavailable.
