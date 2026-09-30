# Additional Harnesses

- Parent WorkPlan: [implementation index](../implementation.plan.md)
- Work type: implementation milestone packet
- Delivery fidelity: Level 3, bounded slice only
- Status: active (sub-slices 1-3 landed; RUNTIME CERTIFICATION for LangGraph/AutoGen(AG2)/OpenAI Agents landed with pinned real-framework journeys; real OpenClaw/Pi host installs remain the external prerequisite)
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
