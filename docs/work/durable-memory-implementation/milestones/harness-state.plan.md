# Harness State Exchange

- Parent WorkPlan: [implementation index](../implementation.plan.md)
- Work type: implementation milestone packet
- Delivery fidelity: Level 3, bounded slice only
- Status: active (sub-slices 1-4 landed: envelope/service, Hermes ports, spool consumer, loopback sidecar; Python client, consume CLI, TS SDK, six model tools, milestone review remain)
- Requirements: DUR-05,06,07,13; regression DUR-01,04
- Dependencies: runtime-recovery and legacy-migration
- Baseline revision: bad9eeefb43f7f42fb95d583b11859e2f2ca9eb8 (planning snapshot)
- Implementation base: 2c8d0bee; current head 2ce70b84

## Observable Acceptance

Installed Hermes resumes a persisted task, receives bounded structured/text state, pages authorized details, records tool dispatch/results and reports unavailable/paused/reconciliation states clearly. Embedded API, loopback sidecar and durable spool deliver the same protocol.

## Owners, Contracts And Expected Files

Under memorii/memorii/: core/harness_state/; api request/result models; integrations/hermes_memory_provider.py; integrations/hermes_factory.py; new sidecar/event-consumer/SDK owners; package entrypoints.

HarnessStateEnvelope and six model tools; host-only dispatch/admin boundaries; finite runtime write grants distinct from memory read/source authorities; 2000-token default/context omissions; HTTP/OpenAPI/Python/TypeScript schemas; local-spool durable intake/deduplication and poison handling.

Exact new symbols, payload/source-kind schemas, SQL catalogs, entrypoints and generated artifacts must match [identity ledger](../identity-and-changes.md) and approved design; expand the actual inventory before creating additional identifiers. [Bindings](../production_entrypoint_bindings.md) supplies current precursor -> proposed callsite/authority -> proof. Zero proposed callers cannot close this packet.

## Compatibility, Migration, Rollout And Rollback

Only explicit initialized/selected backend roots serve managed traffic. Preserve original domain APIs unless design declares the version boundary. No generic runtime grant, JSONL fallback, partial publication or speculative semantic truth. Relevant generation changes use exact old/new recovery and current control authority. Failed publication/validation leaves prior verified state; post-new-write downgrade requires tested compatibility or read_only forward repair. Release exposure stays limited until all allocated parent requirements close. Domain-specific obligations are in the contract above and [validation](../validation.md).

## Exact Validation Commands

Cwd memorii/. Interpreter is the CI-selected Python 3.11 or 3.12 environment from [gates](../gates.md), with editable `.[local,dev]` dependencies for local code tests. These **planned** new paths are not present/executed yet; create under linked approved test architecture, never add empty files just to make commands pass.

```bash
python -W error -m pytest tests/unit/core/test_harness_state_contract.py -p no:cacheprovider
python -W error -m pytest tests/integration/test_installed_hermes_runtime_state.py -p no:cacheprovider
python -m ruff check memorii tests
python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json
pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
```

Run existing owner regressions mapped in validation.md, then every applicable live-workflow gate once on the coherent candidate (do not replace broad required coverage with these focused commands). Additional same-family tests/files are inventoried before writing. Subprocess/package/host/migration matrices remain in explicit slower tiers. Capture cwd, interpreter/dependency/SQLite versions, warnings, environment, command, exit code, logs, exact base/head and dirty-tree status. Required external/OS cases cannot be inferred from local success.

## Proof, Maturity And Completion

Acceptance requires the observable journey plus applicable positive/negative/boundary/retry/concurrency/crash/revocation/compatibility cases in validation.md. Failures must be asserted at real public roots, with no leaked data or partial durable state. Evidence target: implemented and locally verified for the bounded slice; CI-enforced only with actual run evidence, independently reproduced only for a separately authored reducer, operationally verified only for pinned real host/platform/restore journeys. Present maturity: specified only; historical design probes remain separate.

At candidate freeze update live diff, identities, generated authority descendants, root callsites/arguments/caller counts and gates; run spec/correctness/test reviewers once for the coherent milestone. Reconcile all findings before sole-writer remediation. Record exact revision and `remaining_validated_p1_p2: []` only after proof, never prefill it. Any required missing external proof keeps that acceptance open. Parent requirements remain partial until [coverage](../coverage.md) aggregates all allocated packets and release gates.

## Non-Goals

No OpenAI implementation; other required frameworks receive contract fixtures later. No remote binding/browser-origin access or credential exposure. Actual Hermes version pin required; translation mocks do not certify callbacks.

## Progress, Review And Closure

Sub-slice 1 (2026-09-29, base 2c8d0bee, commit 96dcb409): memorii/core/harness_state/{__init__,envelope,service}.py — closed HarnessStateEnvelope (bounded budgets 32/16/64, exclusive candidate/committed labels, discriminated non-executable recommendations, explicit omissions, domain-separated digest via one shared build_envelope factory validated at parse), deterministic HarnessTextRenderer, HarnessStateService over the verified runtime partition with the finite revocable RuntimeReadGrant (denial before lookup — no task-existence disclosure; expired/out-of-scope deny; unsupported views fail closed; frontier truncation recorded as omission). Tests: tests/unit/core/test_harness_state_contract.py (6). Evidence: gates green.

Sub-slice 2 (2026-09-29, commit 1321714d): memorii/core/harness_state/binding.py — HermesRuntimeStatePorts (explicit task-to-principal RuntimeTaskBinding, native session id never authority; bounded envelope text into prefetch; model-tool state view that states plainly when it is a provider work-state summary rather than a durable runtime view; finite short-lived read grants per read). Sub-slice 3 (2026-09-29, commit 12e32046): memorii/core/harness_state/consumer.py — HostEventDelivery closed delivery + LocalDurableSpool (fsync'd atomic intake before acknowledgement, idempotent same-digest redelivery, divergent-duplicate dead-letter, storage-failure never writes, untrusted producer denies without intake). Tests: harness contract suite 8 + consumer suite 5.

Sub-slice 4 (2026-09-29, commit 2ce70b84): memorii/core/harness_state/sidecar.py — RuntimeSidecar (loopback-only bind via serve_loopback daemon thread; browser-origin rejection before any task-derived data; installation-issued bearer credentials mapped server-side to finite read grants; content-free unauthenticated responses; closed error envelope with design error codes; content-free logging) + tests/integration/test_runtime_sidecar.py (6 journeys incl. real loopback HTTP round trip).

Remaining in this packet: Python client over the sidecar; `memorii consume` CLI wiring the spool to the command service; generated HTTP/OpenAPI schemas; TypeScript SDK (pin toolchain first — external prerequisite); six memorii_* model tools as thin wrappers; then the milestone review cohort.

Additional concrete wrapper owners: integrations/authenticated_source.py::build_authenticated_source_runtime and integrations/hermes_provider.py::HermesMemoryProvider. Cover service-injection, memory-plane and storage-root branches with verified managed selection, outer callbacks, restart receipts and missing/wrong selector/control denial. Explicit diagnostic injections remain nonmanaged; no implicit fallback.

TypeScript SDK: proposed sdk/typescript package with pinned Node/npm/lockfile and generated-contract owner. Before code choose supported runtime/package manager and record it; execute every exact planned npm command in gates.md once manifest/scripts exist, including clean out-of-checkout installed-client smoke. Python-only success cannot close the client requirement.
