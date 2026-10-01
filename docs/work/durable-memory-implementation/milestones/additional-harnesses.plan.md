# Additional Harnesses

- Parent WorkPlan: [implementation index](../implementation.plan.md)
- Work type: implementation milestone packet
- Delivery fidelity: Level 3, bounded slice only
- Status: active, externally blocked for full closure — sub-slices 1-3 landed incl. pinned host-contract adapters (ab9af959) and real-framework runtime certification (eea7147a). Open: real OpenClaw/Pi host installs (owner external prerequisite).
- Requirements: DUR-06,13 (DUR-14 host/platform evidence contributed to release-conformance, the allocation owner in [coverage](../coverage.md))
- Dependencies: harness-state
- Baseline revision: bad9eeefb43f7f42fb95d583b11859e2f2ca9eb8 (planning snapshot)
- Implementation base: 6be15eb3; sub-slice head ab9af959

## Observable Acceptance

Pinned real OpenClaw plugin and Pi extension capture authentic sources and continue the same authorized task across restart/session branch changes with bounded state and safe action reconciliation.

## Owners, Contracts And Expected Files

Under memorii/memorii/: integrations/openclaw/; integrations/pi/; host package manifests/examples; Python/TypeScript protocol clients; real-host fixtures.

Host-specific lifecycle/identity mapping outside core; native stable delivery IDs; explicit task selection; Pi branch/fork authority; OpenClaw sender/channel and memory-slot integration; conformance fixtures use shared versioned contract. LangGraph/AutoGen/OpenAI examples remain explicitly contract-only.

Exact new symbols, payload/source-kind schemas, SQL catalogs, entrypoints and generated artifacts must match [identity ledger](../identity-and-changes.md) and approved design; expand the actual inventory before creating additional identifiers. [Bindings](../production_entrypoint_bindings.md) supplies current precursor -> proposed callsite/authority -> proof. Zero proposed callers cannot close this packet.

## Compatibility, Migration, Rollout And Rollback

Only explicit initialized/selected backend roots serve managed traffic. Preserve original domain APIs unless design declares the version boundary. No generic runtime grant, JSONL fallback, partial publication or speculative semantic truth. Relevant generation changes use exact old/new recovery and current control authority. Failed publication/validation leaves prior verified state; post-new-write downgrade requires tested compatibility or read_only forward repair. Release exposure stays limited until all allocated parent requirements close. Domain-specific obligations are in the contract above and [validation](../validation.md).

## Exact Validation Commands

Cwd memorii/. Interpreter is the CI-selected Python 3.11 or 3.12 environment from [gates](../gates.md), with editable `.[local,dev]` dependencies for local code tests. These **planned** new paths are not present/executed yet; create under linked approved test architecture, never add empty files just to make commands pass.

```bash
python -W error -m pytest tests/unit/core/test_host_runtime_translation.py -p no:cacheprovider
python -W error -m pytest tests/integration/test_installed_host_runtime_conformance.py -p no:cacheprovider
python -m ruff check memorii tests
python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json
pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
```

Run existing owner regressions mapped in validation.md, then every applicable live-workflow gate once on the coherent candidate (do not replace broad required coverage with these focused commands). Additional same-family tests/files are inventoried before writing. Subprocess/package/host/migration matrices remain in explicit slower tiers. Capture cwd, interpreter/dependency/SQLite versions, warnings, environment, command, exit code, logs, exact base/head and dirty-tree status. Required external/OS cases cannot be inferred from local success.

## Proof, Maturity And Completion

Acceptance requires the observable journey plus applicable positive/negative/boundary/retry/concurrency/crash/revocation/compatibility cases in validation.md. Failures must be asserted at real public roots, with no leaked data or partial durable state. Evidence target: implemented and locally verified for the bounded slice; CI-enforced only with actual run evidence, independently reproduced only for a separately authored reducer, operationally verified only for pinned real host/platform/restore journeys. Present maturity: specified only; historical design probes remain separate.

At candidate freeze update live diff, identities, generated authority descendants, root callsites/arguments/caller counts and gates; run spec/correctness/test reviewers once for the coherent milestone. Reconcile all findings before sole-writer remediation. Record exact revision and `remaining_validated_p1_p2: []` only after proof, never prefill it. Any required missing external proof keeps that acceptance open. Parent requirements remain partial until [coverage](../coverage.md) aggregates all allocated packets and release gates.

## Non-Goals

No new harness-specific core semantics or claim of installed support for contract-only frameworks. Native APIs/versions verified and pinned during this milestone; absence blocks that advertised host, never replaced with mock approval.

## Progress, Review And Closure

Sub-slice 1 (2026-09-30, base 6be15eb3, commit ab9af959): memorii/integrations/{openclaw,pi}/adapter.py — contract-faithful adapters per the design's concrete host bindings, explicitly NOT certified installed support (the design's own rule: actual framework-version certification required before advertising installed adapters). OpenClaw: closed plugin manifest pinning openclaw-memory-plugin/v1 with supported major versions and permitted hooks (unknown hooks reject); channel account/sender identity; input classification where system/forwarded inputs never become source authority (mutation denied), unbound senders yield explicit unavailable, authorized senders get the bounded runtime block in their explicit memory slot. Pi: closed extension manifest pinning pi-coding-agent-extension/v1; session/branch coordinates never user authority; fork denies without explicit continue-same-task authorization or create-new-task; pre-compaction maps to checkpoint; final-settle maps to settle; abandoned branches never committed source evidence. Tests: tests/unit/integrations/test_host_adapters.py (8). Sub-slice 2 (2026-09-30, commit 6f5e38b2): memorii/integrations/compatibility_examples.py — the spec-22.2 obligation closed with contract-only fixtures: LangGraph (graph/thread/checkpoint; own checkpoint authority retained), AutoGen (conversation/participant, finite per-participant scope), OpenAI Agents (session/run), all mapping to the same versioned host-binding fields under a contract-labeled envelope that structurally cannot claim installed support. Tests: tests/unit/integrations/test_compatibility_examples.py (5).

Remaining in this packet: real-host certification journeys (external prerequisite — actual OpenClaw/Pi installs); milestone review.


## Runtime certification landed (2026-09-30)

Owner directive: "We need the runtime certification." Delivered for the three spec-22.2 frameworks as tests/integration/hostcompat/test_framework_certification.py: each journey imports the REAL framework at an exact pin (langgraph 1.0.10 via real RunnableConfig thread coordinates; AG2 1.1.1 via real AgentSpec — the legacy `pyautogen` 0.10 name proved to be a transition stub with an empty surface, and `autogen-agentcore` is not on the accessible index, so the active `ag2` line certifies the AutoGen contract; openai-agents 0.22.3 via real RunConfig), maps native coordinates through the compatibility wrappers, and drives a real durable start_task round trip plus model-tool state read. Pins live in tests/integration/hostcompat/requirements.txt (not the runtime manifest); MEMORII_HOSTCERT=1 makes missing pins a hard failure (CI), absent pins skip in ordinary local venvs (verified: 1 passed, 3 skipped). CI: new host-compatibility-certification job (Python 3.12, installs pins, runs with MEMORII_HOSTCERT=1) wired into the unit-tests aggregate. Certified evidence: 4/4 green in the pinned /tmp/hostcert venv. OpenClaw/Pi runtime certification still requires the actual host installs (external prerequisite); upgrading any pin requires a fresh certification run.

## Docker validation profiles slice (2026-10-01, owner-authorized)

Owner directive: install the real hosts in Docker to kick off validation — manual validation does not scale; Docker profiles with different agent harnesses are the validation substrate. Research pinned (2026-10-01): OpenClaw = npm `openclaw` current 2026.9.7 (date-versioned; ClawHub package CLI; npm-based plugin/hook system). Pi = npm `@earendil-works/pi-coding-agent` current 0.99.2 (TypeScript extensions default-exported from `.pi/extensions/`, `pi.on("tool_call"|"tool_result"|...)` event surface, `pi.registerTool/registerCommand`, session tree JSONL with id/parentId branching via /tree //fork //clone, `PI_SESSION_ID`/`PI_SESSION_FILE` env, `--mode json` event stream, `--session <id>` resume, RPC socket, and custom providers via models.json pointing at OpenAI-compatible endpoints — which allows fully offline deterministic journeys against a stub provider, no API keys). Docker Engine 29.7.2 available locally; daemon verified up.

Slice plan: (1) host-side packages — `memorii/integrations/pi/extension/` (TS extension translating Pi events/session coordinates to the memorii loopback sidecar via the same protocol the TS SDK speaks, credential from an owner-only file per the manifest contract) and `memorii/integrations/openclaw/plugin/` (JS memory plugin registering the permitted hooks prompt_inject/session_start/session_switch/tool_call with channel/sender identity classification, memory slot bound to the sidecar); (2) Docker profiles — `Dockerfile.pi` and `Dockerfile.openclaw` on pinned digests: node base + pinned host + python3 + memorii editable (prepare_memorii_docker_context pattern) + sidecar + our package installed + stub LLM provider for offline journeys; (3) certification journeys as container-driven integration tests (start/stop containers, drive pi --mode json / openclaw gateway, assert memorii state: authentic source capture, authorized-task continuation across restart, session-branch denial without explicit authorization, bounded state, dispatch/result recording). Python adapters remain the pinned translation contracts; the host packages call through them via the sidecar protocol, never around it.

Design gap surfaced by the Docker slice (2026-10-01): the sidecar's only HTTP route is GET /v1/runtime/state; the durable write path (LocalDurableSpool.admit with HostEventDelivery's closed command union + allowlisted producer bindings) is a Python API. A TS-speaking host (Pi extension, OpenClaw plugin) therefore has no authenticated write bridge. Options: (a) extend the sidecar with an authenticated POST intake route validating the same closed command union server-side, composing the existing credential store and spool poison handling — recommended: one protocol boundary, no protocol duplication; (b) a thin in-container Python shim CLI the host package shells out to; (c) reimplementing the spool intake file protocol in TS (rejected: duplicates the durability/dedup/dead-letter contract in a second language). The Pi extension scaffold (package.json, Dockerfile.pi) is committed with dispatch stubs REMOVED — it binds only the existing GET surface until the intake-route decision lands. Extension code against an invented route would be dead code pretending a contract exists.

Docker Pi profile built and verified (2026-10-01): Dockerfile.pi on pinned node:24-bookworm@sha256:64af3819... builds memorii-pi-validation:pr (manifest list sha256:ffc5e58a450b558410652e7030e3353da152346c5434239c0327c9ac68dfc4fc). In-container proof: pi 0.99.2, Node v24.21.0 (inside the supported 24-26 window), memorii editable with the sidecar and client importable from /opt/memorii-venv. Build warns SecretsUsedInArgOrEnv on ENV MEMORII_CREDENTIAL_PATH — spurious (it names a file path, not a secret); kept for clarity. The extension body and certification journeys remain gated on the intake-route decision recorded above.
