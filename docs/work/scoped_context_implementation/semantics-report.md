# Scoped Context Semantics Report

2026-09-06 bounded writer completion report for the production scoped-context
slice. This is local implementation evidence; the parent implementation plan
and M5 acceptance remain active.

## Implemented behavior

`core/scoped_context/service.py` resolves mandatory records from one authorized
snapshot before optional ranking. Mandatory and lexical paths enforce exact
namespace rows, committed runtime visibility, half-open canonical validity,
and typed current claim state; the structured runtime receives the authorized
snapshot so historical and interval lifecycle selection remains in its existing
temporal owner. It also enforces mandatory item/content limits, deterministic
BM25 optional selection, and typed omission caps. Owned malformed evolution
payloads become the empty `UNAVAILABLE` envelope. The structured path composes
`EvolutionStateRepository.from_snapshot`, `ClaimStateQueryService`, local
`EnglishLexicalQueryAnalyzer`, anchors, predicates, and
`MemoryEvolutionRetrievalRuntime`; it has no memory-plane live-reader fallback
and the guard rejects execution and belief temporal frames before runtime
branching. Assembly stores no per-instance result state.

`core/scoped_context/contracts.py` validates closed structured answer,
no-match, and abstention shapes. `core/scoped_context/authority.py` retains
opaque process identities by identity rather than equality while preserving
lock-linearized resolve/release checks.

## Production binding

The non-test caller is
`memorii/integrations/hermes_provider.py:HermesMemoryProvider.retrieve_context`.
It forwards request and opaque authority ingress to the canonical provider
owner. Factory and filesystem composition forward the separately injected
authority. The integration test executes both filesystem and Hermes roots with
an actual `InProcessScopedReadAuthority`, reaches the canonical method, and
observes an authority receipt and snapshot-derived mandatory item.

## Focused evidence

From `memorii/` using `../.venv/bin/python`:

```
python -m ruff check memorii/core/scoped_context tests/unit/core/test_scoped_context_activation.py
python -m pytest tests/unit/core/test_scoped_context_activation.py tests/integration/test_scoped_context_production_binding.py -q -p no:cacheprovider
```

Both passed: Ruff reported no violations and pytest reported `7 passed`.
The focused tests cover pre-snapshot denial, release/revoke behavior, both real
roots, whole optional byte-limit omission, and malformed owned payloads.

## Changed paths

- `memorii/memorii/core/scoped_context/contracts.py`
- `memorii/memorii/core/scoped_context/authority.py`
- `memorii/memorii/core/scoped_context/service.py`
- `memorii/tests/unit/core/test_scoped_context_activation.py`
- `docs/work/scoped_context_implementation/implementation.plan.md`

## Residual evidence boundary

The complete temporal/provenance closure matrix and all owner-stripping CI
matrix are not part of this focused writer proof. They remain explicit testing
plan and parent-milestone work; this report does not mark the parent milestone
or M5 complete.
