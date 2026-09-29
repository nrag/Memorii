# Runtime Recovery

- Parent WorkPlan: [implementation index](../implementation.plan.md)
- Work type: implementation milestone packet
- Delivery fidelity: Level 3, bounded slice only
- Status: proposed
- Requirements: DUR-01,02,03,04,05,07; regression DUR-15,16
- Dependencies: storage-foundation; semantic-ontology parity baseline
- Baseline revision: bad9eeefb43f7f42fb95d583b11859e2f2ca9eb8 (planning snapshot)
- Implementation base/head: unset; record before edits and at closure

## Observable Acceptance

Create a task with competing hypotheses, candidates, overlays, unresolved work and dispatched action; terminate and resume through an authenticated persistent API in another process without losing state or repeating the tool.

## Owners, Contracts And Expected Files

Under memorii/memorii/: api/service.py; api/models.py; core/execution/service.py; core/persistence/{contracts,repository,factory,replay,resume}.py; solver update/frontier owners; runtime repository views.

Closed commands and full-state events; atomic domain batches/indexes/receipts; durable attempts, fences, budgets and outbox; authenticated checkpoints/tails; independent reference reducer with no production reducer/normalizer imports. Legacy bare-ID APIs restricted to explicit ephemeral roots; no model/tool execution during replay.

Exact new symbols, payload/source-kind schemas, SQL catalogs, entrypoints and generated artifacts must match [identity ledger](../identity-and-changes.md) and approved design; expand the actual inventory before creating additional identifiers. [Bindings](../production_entrypoint_bindings.md) supplies current precursor -> proposed callsite/authority -> proof. Zero proposed callers cannot close this packet.

## Compatibility, Migration, Rollout And Rollback

Only explicit initialized/selected backend roots serve managed traffic. Preserve original domain APIs unless design declares the version boundary. No generic runtime grant, JSONL fallback, partial publication or speculative semantic truth. Relevant generation changes use exact old/new recovery and current control authority. Failed publication/validation leaves prior verified state; post-new-write downgrade requires tested compatibility or read_only forward repair. Release exposure stays limited until all allocated parent requirements close. Domain-specific obligations are in the contract above and [validation](../validation.md).

## Exact Validation Commands

Cwd memorii/. Interpreter is the CI-selected Python 3.11 or 3.12 environment from [gates](../gates.md), with editable `.[local,dev]` dependencies for local code tests. These **planned** new paths are not present/executed yet; create under linked approved test architecture, never add empty files just to make commands pass.

```bash
python -W error -m pytest tests/unit/core/test_runtime_state_repository.py -p no:cacheprovider
python -W error -m pytest tests/integration/test_runtime_process_recovery.py -p no:cacheprovider
python -m ruff check memorii tests
python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json
pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
```

Run existing owner regressions mapped in validation.md, then every applicable live-workflow gate once on the coherent candidate (do not replace broad required coverage with these focused commands). Additional same-family tests/files are inventoried before writing. Subprocess/package/host/migration matrices remain in explicit slower tiers. Capture cwd, interpreter/dependency/SQLite versions, warnings, environment, command, exit code, logs, exact base/head and dirty-tree status. Required external/OS cases cannot be inferred from local success.

## Proof, Maturity And Completion

Acceptance requires the observable journey plus applicable positive/negative/boundary/retry/concurrency/crash/revocation/compatibility cases in validation.md. Failures must be asserted at real public roots, with no leaked data or partial durable state. Evidence target: implemented and locally verified for the bounded slice; CI-enforced only with actual run evidence, independently reproduced only for a separately authored reducer, operationally verified only for pinned real host/platform/restore journeys. Present maturity: specified only; historical design probes remain separate.

At candidate freeze update live diff, identities, generated authority descendants, root callsites/arguments/caller counts and gates; run spec/correctness/test reviewers once for the coherent milestone. Reconcile all findings before sole-writer remediation. Record exact revision and `remaining_validated_p1_p2: []` only after proof, never prefill it. Any required missing external proof keeps that acceptance open. Parent requirements remain partial until [coverage](../coverage.md) aggregates all allocated packets and release gates.

## Non-Goals

No host automatically executes a restored recommendation; no semantic promotion bypass; no in-memory default in managed API. Shared-store revisions change only for their own domain. Runtime and migration edits remain serial if storage owners overlap.

## Progress, Review And Closure

Not started. No production/test edits, validation execution or implementation review exists for this packet. No implementation base/head or approval is claimed. The index owns the single global next action.
