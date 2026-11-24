# Host Result And Decision

- Parent: [durable delivery implementation](../implementation.plan.md)
- Status: proposed
- Requirements: DUR-03/05/06/07/13/14
- Dependencies: Durable intent and output
- Closure identity: unset, record actual base, code head, dirty state and artifact/run digests before claim

## Observable Acceptance

An authenticated host reads scoped consolidation after restart, round-trips exact selectors and can accept or decline without modifying graph lifecycle.

## Owners And Contract Changes

RuntimeSidecar, HermesRuntimeStatePorts and installed Hermes factory, runtime repository, OpenClaw and Pi clients, tools/runtime_schema_export.py, sdk/typescript.

Compose explicit read and decision routes and embedded equivalents. Read authorizes before lookup and release, binds cursor and omits suppressed IDs/counts. Accept publishes once-only decision, receipt and queue with fixed payload; decline creates no delivery. Keep skill scope separate. Extend generated OpenAPI/client contracts, prepare context and declared host support.

## Verification

Real callback and loopback requests, cross-task and cross-target denial, stale cursor and offer version/digest, suppression race, exact retry and divergent intent. An untrusted model cannot decide, and accepted staging does not occur before target publication. Compile, test, package and install the SDK against the updated schema.

Existing regression anchors from memorii/ in the applicable pinned CI environment:

```bash
python -W error -m pytest tests/integration/test_runtime_sidecar.py tests/unit/core/test_harness_state_contract.py tests/unit/tools/test_runtime_schema_export.py tests/unit/core/test_runtime_command_dispatch.py -p no:cacheprovider
```

New path proof commands and exact test names must be registered through the [validation ledger](../validation.md) before implementation. Include the affected workflow job and artifact evidence. Review against the exact commit. Evidence maturity is design specified at this baseline. This packet is complete only with local and applicable enforced proof and reviewed closure. It satisfies only its bounded portion of the parent requirements.

## Scope Boundary

Use the approved design and existing semantic owners. Keep unsupported roots visibly unavailable. Record compatibility and rollout deltas at the actual candidate. Parent owns release authorization and aggregate gate outcome.

## Progress And Review

Proposed. No product edits, tests or milestone approvals recorded.
