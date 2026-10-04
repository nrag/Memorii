# Runtime Recovery

- Parent WorkPlan: [implementation index](../implementation.plan.md)
- Work type: implementation milestone packet
- Delivery fidelity: Level 3, bounded slice only
- Status: implemented and reviewed — sub-slices 1-4 landed, review round 1 completed with the false-success P1 and five P2s remediated (ff45a6c0). Non-blocking follow-ups recorded below.
- Requirements: DUR-01,02,03,04,05,07; regression DUR-15,16
- Dependencies: storage-foundation; semantic-ontology parity baseline
- Baseline revision: bad9eeefb43f7f42fb95d583b11859e2f2ca9eb8 (planning snapshot)
- Implementation base: ffe26367; current head ff45a6c0

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

Sub-slice 1 (2026-09-29, base ffe26367, commit 8f040c2f): memorii/core/persistence/runtime_contracts.py — closed records (TaskRecord/SolverRunRecord/SolverJustificationRecord/RuntimeOverlayVersion/ActionAttemptRecord/RuntimeCommandReceipt), the 16-kind solver node content union validated at the boundary, the complete 11-kind command union (task lifecycle with completion evidence; four-member proposal union incl. justification-bound belief update and gate-checked merge), all extra=forbid. Partition: eleven runtime catalogs + runtime revision state, manifest-covered with full-row folds; typed upsert/read APIs. RuntimeStateRepository view; publish_runtime_change (verified-state anchor, runtime-head batch position, memory heads unchanged, intent-before-commit, exact-old/new recovery, read_only gate). Tests: tests/unit/core/test_runtime_state_repository.py (6) and tests/integration/test_runtime_process_recovery.py (2) including the packet's observable acceptance: fresh-process restore of three hypotheses/observation/overlay/justification/dispatched action with verified state and no rerun. Evidence: 37-test battery green; ruff/pyright/identity gates pass.

Sub-slice 2 (2026-09-29, commit 80cfa918): memorii/core/persistence/runtime_events.py — closed event grammar (legal combination matrix; entity-id aliasing, ID-only payloads, candidate+committed rejected; domain-separated envelope/batch digests with a canonical factory), replay (batch-position ordering; byte-identical redelivery idempotent; event-id reuse with different envelope fails closed — a real gap the tests exposed; divergent dedupe reuse and equal-version non-identical fail closed; stale versions ignored; delete = logical retirement with full state; complete-batch atomicity), and the eighteen-label business inventory. Independent reference reducer (naive arrival-order consumer, no production imports) agrees on the frozen corpus. Tests: tests/unit/core/test_runtime_event_replay.py (10).

Sub-slice 3 (2026-09-29, commit c59ffddd): memorii/core/persistence/runtime_api.py — RuntimeCommandService (idempotent durable dispatch of the closed command union with divergent-reuse conflict, deterministic task allocation, lifecycle gating incl. unresolved-action completion block and terminal closure, stale-revision conflict), RuntimeOperationAttempt + RuntimeOutboxDelivery contracts and the runtime_operation_attempts/outbox catalogs (manifest-covered), fenced-takeover terminal cause, dispatch reservation per (task, recommendation, revision). Tests: tests/unit/core/test_runtime_command_dispatch.py (9). A flock self-deadlock was caught and fixed with connection-scoped reads.

Sub-slice 4 (2026-09-29, commit e6a51e7f): memorii/core/persistence/runtime_checkpoint.py — RuntimeCheckpoint (revision-bound canonical manifest with counts + member digest, domain-separated signature purpose memorii.runtime-checkpoint.v1 via an injected signer; counts validated at parse; creation requires a committed revision) and build_resume_envelope (one consistent view; dispatched/outcome-unknown actions pend under reconcile_required without rerun; future-revision checkpoints refuse; missing tasks not_found). Tests: tests/integration/test_runtime_resume_checkpoint.py (6) incl. cross-process pause/resume.

Remaining in this packet: staleness revalidation of time-dependent assumption content inside checkpoint members (DUR-04 — the envelope plumbing is in place, the temporal walk is a recorded follow-up as assumption content lands in checkpoint members); runtime event-batch publication integration; legacy bare-ID API restriction; the milestone review cohort (in flight).


## Milestone review round 1 + remediation (2026-09-29)

Combined cohort on candidate b2eca501: foundations approved (publication crash-cut protocol traced cut-by-cut and sound; closed grammars verified against the design's tables cell-for-cell; reference reducer genuinely independent; journeys real). One P1 and five P2s confirmed and remediated in ff45a6c0: unimplemented command kinds committing false-success receipts now fail closed (P1); receipt revisions pin the runtime head; dispatch idempotency and the dispatch reservation moved inside the publication fence with a unique reservation index; attempt stages gained terminal values with fenced takeover landing in needs_reconciliation and the attempt catalog keyed on (receipt_id, ordinal). Recorded follow-ups (unchanged blocking posture, owned by later sub-slices/packets): command payload carriers (host_binding, source-admission receipt, action identity/evidence fields, start acceptance evidence) before the effects for observation/proposal/dispatch/result land; read views (RuntimeStateRequest) and merge duplication gates + consolidation triggers + pre-pause checkpoint; checkpoint manifest binding of full member digests, repository identity, schema/policy digests and trust-lifecycle verification; single-transaction snapshot assembly for checkpoint/resume; replay binding persistence for stale-skipped events; event-label/EventType schema metadata when batches publish; attempt/outbox/action transition matrix tests and a crash cut through publish_runtime_change; publication-flow deduplication onto one shared candidate owner. DUR-01 (state restore journey), DUR-02 (atomic publication), DUR-03 (idempotent dispatch, fenced attempts, reservations) are slice-evidenced; DUR-04 temporal revalidation and DUR-05 scoped runtime authority remain staged.
