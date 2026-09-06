# Graph Record Version Fixture Warning Closure

- Work ID: graph_record_version_fixture_warning_2026_09_05
- Work type: debugging
- Status: complete
- Coordinator: Codex main thread
- Parent WorkPlan: `docs/work/semantic_ingestion/m4-closure-2026-09-04/implementation.plan.md`
- Governing evidence: `memorii/tests/unit/core/semantic_ingestion/test_event_replay.py`; `memorii/tests/unit/core/semantic_ingestion/graph_record_test_support.py`

## Objective

Restore the existing all-record-kind signed-checkpoint replay proof under
`-W error` without changing production graph-record semantics.

## Scope

Included: the fixture helper that advances canonical graph-record versions and
the exact replay regression. Excluded: production schemas, replay policy,
non-M4 behavior, and broad fixture redesign.

## Hypotheses And Discriminator

Primary hypothesis: `next_canonical_graph_record_versions` converts nested
typed evidence to dictionaries with `model_dump`, then passes those dictionaries
through `model_construct` inside record factories, causing Pydantic's serializer
to warn for `AliasRevision.source_evidence` under `-W error`.

Discriminator: preserve each record's already validated nested typed members
while changing only version/digest fields. The exact failing selector must pass
without suppressing warnings, and the all-record-kind replay assertions must
remain unchanged.

## Evidence Log

- 2026-09-05: exact reproduction failed in 8.76s with
  `PydanticSerializationUnexpectedValue` for `AliasRevision.source_evidence`;
  the helper supplied a dictionary where `LineageEvidenceReference` was
  required.
- 2026-09-05: confirmed root cause. The helper dumped each record before
  version advancement, replacing nested validated models with dictionaries;
  `_GraphRecord.create` then serialized that provisional unvalidated shape.
  The correction copies the model's stored typed fields, changes only the
  version/identity transition values, and derives temporal record digests from
  the model's canonical serialized representation before validation.
  Production graph-record code and replay assertions remain unchanged.
- 2026-09-05: exact reproducer passed with `-W error` in 18.73s:
  `PYTHONPATH=memorii .venv/bin/python -m pytest -W error
  memorii/tests/unit/core/semantic_ingestion/test_event_replay.py::test_all_graph_record_kinds_survive_signed_checkpoint_tail_and_genesis_replay
  -p no:cacheprovider`.
- 2026-09-05: `py_compile`, scoped Ruff, and `git diff --check` passed.
  Event-replay collection found 65 tests in 7.47s.
- 2026-09-05: added a direct all-12-kind regression proving nested model
  values and exact types remain stable, only documented version/digest and
  identity-lineage transition fields change, and every advanced record
  validates after a persisted-shape round trip with its digest intact.

## Completion Contract

Complete when the exact selector passes with `-W error`, adjacent graph-record
fixture tests pass, scoped lint/compile pass, and independent correctness/test
review finds no remaining P1/P2 or required correction.

## Next Action

None for this completed slice. The parent M4 closure owns the broader
replay/history family gate.

## Review Log

Final correctness and test review both approved the frozen six-file fixture
chain with no remaining findings. The direct and signed-checkpoint selectors
passed together under `-W error` (2 passed in 19.20s); the reviewers
independently repeated the bounded proof and verified the manifest base,
scoped diff, and every dependency hash.
