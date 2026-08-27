# Canonical-Encoder Hot-Path Implementation WorkPlan

- Work ID: `semantic-ingestion-canonical-encoder-hot-path-2026-08-27`
- Work type: `implementation`
- Status: `active`
- Coordinator: sole writer (main thread)
- Created: `2026-08-27`
- Parent WorkPlan:
  `../semantic-ingestion-canonical-evidence-default-on-2026-08-27/implementation.plan.md`
  (its measured ~36s residual scoped this unit)
- Related: `../semantic-ingestion-canonical-evidence-production-performance-2026-08-16/debug.plan.md`
  (H7 persistence-composition kernel)
- Canonical inputs: the current tree; PBD-EXP-014 evidence; the codec/frozen-wire suites.
- Expected outputs: materially faster canonical encoding with byte-identical
  output, proven by the frozen codec suites and re-measured delivery wall-clock.

## Objective

Reduce the ~36s per-delivery residual (post default-on, post-H8) by fixing the
measured encoder hot path, without changing one byte of canonical output.

## Profile Evidence (2026-08-27, one enabled delivery, cProfile)

- `ingestion_contracts._json`: 6.08M calls, 21.9s exclusive / 72.5s cumulative.
- `json.dumps`: 4.68M calls (one per scalar; non-default kwargs defeat the
  cached encoder each call), 12.7s exclusive.
- `isinstance`: 29.2M calls, 8.6s. `str.encode`: 11.1M calls, 6.2s.
- `_scalar`: 5.86M calls, 5.5s (validation-only full encode per string).
- Dict keys encoded twice per dict in `_json` (sort key + emit) and in `walk`.
- `walk` top-level invocations are only ~242 (via 121 with-spans encodes);
  the trees are legitimately huge — per-scalar and double-key costs dominate.

## Plan

1. String fast path in `_json`: when a string contains no `"`/`\`/control
   characters, emit `b'"' + utf8 + b'"'` directly (single encode, which also
   carries the strict-UTF-8 validation); otherwise fall back to the exact
   `json.dumps(ensure_ascii=False, separators=(",", ":"))` path. Byte-identical
   by construction; escape-scan via one precompiled regex.
2. Encode each dict key once in `_json` and `walk`: build (encoded_key, value)
   pairs, sort by encoded bytes, emit from the pairs.
3. Gate: codec/consensus/vector/frozen-wire suites green (byte identity), then
   re-run PBD-EXP-014 and record the new distributions.

## Completion Contract

Byte-identical canonical output (frozen suites green), ruff/identity gates
green, and a recorded before/after delivery measurement. If the fast path
cannot reach the target, record what remains and stop.

## Progress Log

- 2026-08-27: opened from the PBD-EXP-014 residual; profile recorded above.

## Next Action

Implement the string fast path and single-encode dict keys in
`memorii/core/memory_evolution/ingestion_contracts.py`.
