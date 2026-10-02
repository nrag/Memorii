# Harness State Exchange

- Parent WorkPlan: [implementation index](../implementation.plan.md)
- Work type: implementation milestone packet
- Delivery fidelity: Level 3, bounded slice only
- Status: implemented, review round 1 remediated — sub-slices 1-10 landed incl. paging cursors (e0759024), credential store (1c9e4e2b), consume CLI (dfaff8df) and the TypeScript SDK (bf549f12) with every gates.md command green and CI Node 24/26 jobs green. Open closure items: grant-epoch revocation registry, closing review round.
- Requirements: DUR-05,06,07,13; regression DUR-01,04
- Dependencies: runtime-recovery and legacy-migration
- Baseline revision: bad9eeefb43f7f42fb95d583b11859e2f2ca9eb8 (planning snapshot)
- Implementation base: 2c8d0bee; current head dfaff8df

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

Sub-slices 5-6 (2026-09-29, commits 500339f3, 4feb684c): RuntimeStateClient (typed Python client over the sidecar with URL-parsed loopback guard, closed error mapping, credential-free URLs/logs) and RuntimeModelTools (closed six-tool registry; read tools serve durable views; unimplemented effect kinds state unavailable; denials carry no data; unknown names fail closed).

Remaining in this packet: `memorii consume` CLI wiring the spool to the command service; generated HTTP/OpenAPI schemas; paging-cursor contract (P2 before closure); credential provisioning with owner-only files + grant epochs; TS SDK (external toolchain prerequisite); then the closing review round.

Additional concrete wrapper owners: integrations/authenticated_source.py::build_authenticated_source_runtime and integrations/hermes_provider.py::HermesMemoryProvider. Cover service-injection, memory-plane and storage-root branches with verified managed selection, outer callbacks, restart receipts and missing/wrong selector/control denial. Explicit diagnostic injections remain nonmanaged; no implicit fallback.

TypeScript SDK: proposed sdk/typescript package with pinned Node/npm/lockfile and generated-contract owner. Before code choose supported runtime/package manager and record it; execute every exact planned npm command in gates.md once manifest/scripts exist, including clean out-of-checkout installed-client smoke. Python-only success cannot close the client requirement.


## Milestone review round 1 + remediation (2026-09-29)

Combined cohort on candidate ff4678d3: foundations sound (denial-before-lookup, digest self-consistency, closed grammars, loopback posture, consumer intake durability all verified); no P1. Four P2s confirmed and remediated (216fd06c..56f6e37f): token budget + overflow degrade (render_bounded: 2000-token approx-char/4 budget, minimal bounded reconcile_required summary with paging marker — never falsely complete), omission recorded for every collection truncation, single-snapshot envelope assembly (one partition read transaction via connection-scoped helpers), durable dead-letter path (atomic fsync'd rewrite/append; internal reads no longer re-acquire held locks — a self-deadlock the tests caught), aware-UTC binding grants, URL-parsed client loopback guard with robust error mapping, history-view pass-through noted, tool summary distinguishing refusal from unbound. Recorded follow-ups (C5-C12): paging-cursor contract (must be P2 before packet closes), credential provisioning with owner-only files + grant-epoch machinery, typed pending-action records vs bare ids, recommendation assumption/expected-observation refs, suspended branches, Host-header hardening, subprocess consumer redelivery journey, concurrency family, sidecar body-size cap, credential-mode tests on both OSes (Level 3 gate), TS SDK external prerequisite.

## Sub-slices 7-9 (2026-09-30)

Sub-slice 7 (e0759024): authenticated continuation cursors - HarnessPageCodec (HMAC, purpose harness-continuation-cursor, five-minute expiry) binding task/principal/grant id+epoch/runtime revision/view/offset; the service pages the frontier 16-per-page, validates every page (forged/other-query/other-principal reject; revision change -> stale_cursor; expiry -> re-read); the sidecar maps stale_cursor to closed 409. Closes review follow-up C5, the packet's declared P2-before-closure item. Sub-slice 8 (1c9e4e2b): SidecarCredentialStore - issue-once secrets with SHA-256 digests stored (constant-time lookup), fsync'd atomic index writes, 0700/0600 enforced with fail-closed verify_permissions; the sidecar composes the store. Closes the issuance half of C6. Sub-slice 9 (dfaff8df): memorii-consume CLI (registered entry point) admitting typed deliveries through the spool with the producer binding as allowlist and dispatching durably; idempotent repeats; malformed -> invalid_request exit 2; untrusted/divergent -> denied exit 3 without execution.

Remaining in this packet: generated HTTP/OpenAPI schemas (design's generator chain - belongs with the release-conformance generated-artifact work); TS SDK (external toolchain prerequisite: Node/npm version pin needed from the owner); grant-epoch revocation registry (epoch field now bound in cursors; a registry flipping epochs is the remaining half of C6); the closing review round.


## Sub-slice 10: TypeScript SDK (2026-09-30)

sdk/typescript: @memorii/runtime-client v1.0.0 — typed RuntimeStateClient mirroring the Python client (loopback-only URL guard with IPv6 bracket normalization, bearer credentials in headers only, closed error codes on RuntimeClientError, continuation-cursor support). Supported runtimes per owner's corrected policy: Node 24 THROUGH 26 (engines >=24 <27, npm >=11); out-of-range UX: npm engines refusal at install + README documents the window + runtime unsupported_version error — never silent degradation. gates.md command set all green locally on Node 26.7.0/npm 11.19.0: npm ci (lockfile committed), check:generated (byte parity against memorii-runtime-schema regeneration + closed-union inventory parity: recommendation 7, status 5, error codes 12 — SidecarError.code became a closed Literal so the schema carries the union), typecheck, test (node:test, 5 journeys incl. IPv6/prefix-spoof/userinfo guard and non-object error body), build, pack --dry-run (7 files), test:installed (tarball installed outside checkout, authorized+denied smoke; async exec keeps the harness server reachable). CI: sdk-typescript job on Node matrix [24, 26] with Python for schema regeneration, wired into the unit-tests aggregate. Remaining in this packet: grant-epoch revocation registry; closing review round.

## Design delta: authenticated sidecar intake route (2026-10-01, owner-approved)

Owner approved the recommended service boundary for non-Python hosts: the loopback sidecar gains one authenticated write route, POST /v1/runtime/intake. Contract: the request is a closed SidecarIntakeRequest {protocol_version: 1, command: RuntimeCommandRequest} — the closed 11-kind runtime command union validates server-side (unknown kinds and kind/payload mismatches fail closed as invalid_request). Producer authority is SERVER-DERIVED: the bearer credential maps through an intake factory to a HostIntakeBinding {spool, producer_binding, allowlisted_producers}; message fields never choose authority, mirroring the consumer's binding rules. Admission goes through LocalDurableSpool.admit unchanged (fsync-before-ack, idempotent by operation_id+digest, divergent duplicate dead-letters as 409 conflict). Transport posture identical to the read route: loopback host check, browser-origin rejection before any body parse, content-free 401s, bounded body. Rationale recorded against the alternatives (TS reimplementation of the spool file protocol rejected: duplicates durability/dead-letter semantics in a second language; per-event CLI shim rejected: process-spawn per event, same protocol duplicated at argv level). This unblocks the Pi/OpenClaw extension bodies and the container-driven certification journeys.

Grant-epoch revocation registry landed (2026-10-01): GrantEpochRegistry (harness_state/grant_registry.py) — file-backed, owner-only (0o700/0o600 from first append), append-only and monotone: revoke() advances the grant's epoch, fsyncs the revocations journal, and never lowers; require_current() fails closed with the closed stale_grant reason for superseded epochs; revocations() replays the durable journal across process restarts. HarnessStateService.read_state consults the registry before serving when one is composed (denied: stale_grant at the service boundary; cursors minted under superseded epochs were already rejected by the codec's epoch binding). Tests: monotone revoke, fail-closed stale epoch, reopen durability, empty-reason refusal (4 green; 32 across the harness suites).
