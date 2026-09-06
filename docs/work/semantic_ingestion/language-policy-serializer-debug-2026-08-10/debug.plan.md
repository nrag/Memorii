# Language Policy Serializer Debug

- Work ID: `language-policy-serializer-debug-2026-08-10`
- Work type: `debugging`
- Status: `active`
- Coordinator: `Codex main thread`
- Created: `2026-08-10`
- Last updated: `2026-08-10`
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md`; `docs/work/semantic_ingestion/source-normalization-authority-bundle-2026-08-10/design.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md`; `memorii/memorii/core/memory_evolution/ingestion_contracts.py`; `memorii/memorii/core/memory_evolution/semantic_analysis/policies.py`; `memorii/tests/fixtures/semantic_ingestion/source_normalization_fixture_builder.py`; `memorii/tests/unit/core/semantic_ingestion/test_slice_b_policy_authorities.py`
- Expected outputs: exact root-cause record for the `model_dump(mode="python")` failure, the smallest invariant-preserving serializer correction, and focused regression proof for the policy/bundle family

## Objective

Restore valid Python-mode serialization for `PredicateSemanticPolicy` and the
request-owned `LanguageConstructionPolicyAuthorityBundle` without changing the
published CTV wire image, digest domains, or typed model contracts.

## Completion Contract

Complete only after: the failure is reproduced deterministically; at least two
hypotheses are recorded; the causal serializer boundary is proved; the fix
preserves exact CTV encoding for the affected family; the direct policy and
bundle sibling roundtrips are covered by tests; and focused pytest, Ruff,
`py_compile`, and `git diff --check` evidence are recorded.

## Scope

Included: `PredicateSemanticPolicy` Python-mode dumping, the nested
construction-family set member shape, shared CTV mapping encoding required by
that dump, and Slice B policy/bundle regression coverage.

Excluded: authority design changes, persisted schema redesign, source
normalization workflow semantics, and unrelated semantic-ingestion plan state.

## Expected And Observed Behavior

Expected: the request-owned policy family named in
`docs/design/semantic_ingestion_architecture.md` should support valid strict
`model_dump(mode="python")` output, and the publication fixture should be able
to carry those values through digest/CTV serialization without special cases.

Observed: `PredicateSemanticPolicy.model_dump(mode="python")` raised
`TypeError: unhashable type: 'dict'`. The same failure surfaced when dumping
`LanguageConstructionPolicyAuthorityBundle`, which contains the same policy
shape under parser bindings. The publication fixture reaches that boundary when
the derivation authority is materialized for digest computation.

Classification: `implementation`.

## Reproducer

Exact deterministic reproducer before the fix:

```bash
PYTHONPATH=memorii .venv/bin/python - <<'PY'
from tests.unit.core.semantic_ingestion.test_slice_b_policy_authorities import _leaves, _codec_values
predicate = _leaves()[-1]
predicate.model_dump(mode="python")
for value in _codec_values():
    if type(value).__name__ == "LanguageConstructionPolicyAuthorityBundle":
        value.model_dump(mode="python")
        break
PY
```

Expected signal: both calls return valid Python values.

Observed signal before the fix: both calls raised
`TypeError: unhashable type: 'dict'`.

## Hypothesis Ledger

| ID | Hypothesis | Mechanism | Discriminator | Status |
| --- | --- | --- | --- | --- |
| H1 | The custom policy serializer emits dict-shaped set members that Pydantic reserializes back into plain `dict` objects before rebuilding the `frozenset`. | Plain `dict` members are unhashable, so Python-mode dump fails while reconstructing the serialized set. | Replace those members with immutable `Mapping` values that survive Python-mode serialization and verify the same dump path becomes valid without changing CTV bytes. | confirmed |
| H2 | The failure originates in digest canonicalization rather than Python-mode serialization, so `model_dump` only exposes a pre-existing invalid CTV shape. | `_canonical` or `encode_typed_value` would reject the family even if Pydantic preserved set-member hashability. | Reproduce the failure directly at `model_dump(mode="python")`; if it fails before `encode_typed_value` is called, the immediate fault is serializer reconstruction rather than digesting. | disproved |

## Causal Chain And Correction

1. `PredicateSemanticPolicy` owns `supported_constructions` as a
   `frozenset[ConstructionFamily]`.
2. Its custom serializer lowered each `ConstructionFamily` member into a
   hashable `dict` subclass so the policy could still encode as a CTV map.
3. Pydantic's Python-mode serializer re-walked those returned members through
   the `dict[str, Any]` return schema and rebuilt them as plain `dict` values.
4. The enclosing `frozenset` reconstruction then failed with
   `TypeError: unhashable type: 'dict'` before the publication fixture could
   finish deriving its authority bundle.
5. The smallest safe fix is:
   - use an immutable custom `Mapping` for canonical policy map members so
     Python-mode serialization preserves member hashability
   - let the shared CTV encoder accept generic `Mapping` values so those
     immutable members still encode as exact canonical maps

This preserves the existing digest formulas and typed wire shape while fixing
the serializer boundary instead of adding call-site workarounds.

## Focused Evidence

- Direct reproducer after the fix:
  - `PredicateSemanticPolicy.model_dump(mode="python")` returned a `frozenset`
    whose members are immutable `_CanonicalMap` values.
  - `LanguageConstructionPolicyAuthorityBundle.model_dump(mode="python")`
    returned a valid tuple of two policy authorities.
- Regression proof:
  - `PYTHONPATH=memorii .venv/bin/python -m pytest -q memorii/tests/unit/core/semantic_ingestion/test_slice_b_policy_authorities.py`
    passed `53` tests in `6.76s`.
  - `PYTHONPATH=memorii .venv/bin/python -m pytest -q memorii/tests/unit/core/semantic_ingestion/test_source_normalization_authority_contracts.py`
    passed `3` tests in `2.85s`.
- Static hygiene:
  - `PYTHONPATH=memorii .venv/bin/python -m ruff check memorii/memorii/core/memory_evolution/ingestion_contracts.py memorii/memorii/core/memory_evolution/semantic_analysis/policies.py memorii/tests/unit/core/semantic_ingestion/test_slice_b_policy_authorities.py`
    passed.
  - `PYTHONPATH=memorii .venv/bin/python -m py_compile memorii/memorii/core/memory_evolution/ingestion_contracts.py memorii/memorii/core/memory_evolution/semantic_analysis/policies.py memorii/tests/unit/core/semantic_ingestion/test_slice_b_policy_authorities.py`
    passed.
  - `git diff --check -- memorii/memorii/core/memory_evolution/ingestion_contracts.py memorii/memorii/core/memory_evolution/semantic_analysis/policies.py memorii/tests/unit/core/semantic_ingestion/test_slice_b_policy_authorities.py`
    passed.

## Residual Risk And Follow-Up

- Residual risk: the fix broadens the shared CTV encoder from plain `dict` to
  generic `Mapping`. Focused authority and policy tests passed, but broader
  suite coverage still belongs to the coordinator if this change lands with
  adjacent serialization work.
- Required follow-up: link this debugging record from the parent milestone
  packet and run the coordinator's closure-review cohort before marking the
  debugging slice complete.

## Exact Next Action

Have the coordinator reconcile this debug slice into the parent M3/M4 planning
state and decide whether to launch independent closure review on the current
serializer candidate.
