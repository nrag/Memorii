# Durable Intent And Output

- Parent: [durable delivery implementation](../implementation.plan.md)
- Status: proposed
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

Proposed. No product edits, tests or milestone approvals recorded.
