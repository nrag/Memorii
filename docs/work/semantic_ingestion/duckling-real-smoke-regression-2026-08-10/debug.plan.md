# Duckling Real Smoke Regression

- Work ID: duckling_real_smoke_regression_2026_08_10
- Work type: debugging
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-08-10
- Last updated: 2026-08-10
- Parent WorkPlan: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/implementation.plan.md`; `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md`; `memorii/memorii/core/memory_evolution/semantic_analysis/temporal/duckling_adapter.py`; `memorii/tests/unit/core/semantic_ingestion/test_duckling_temporal_adapter.py`; `memorii/containers/duckling/build-manifest.v1.json`; `memorii/memorii/core/semantic_ingestion/resources/duckling_sidecar.v1.json`
- Expected outputs: expected-vs-observed classification, confirmed root cause for the live Duckling smoke failure, smallest safe adapter/test correction, focused regression proof, and explicit live-smoke command or environment limitation

## Objective

Restore the real local Duckling temporal smoke for the sealed temporal resolver
without weakening the fail-closed authority contract. The corrected adapter
must accept documented Duckling time rows for one exact unambiguous instant,
ignore irrelevant non-time rows, and continue rejecting ambiguous or malformed
temporal output.

## Completion Contract

Complete only when: the real-smoke failure boundary is reproduced or explained
from recorded evidence; at least two plausible hypotheses are discriminated;
the causal adapter assumptions are traced from request to `None` result; the
smallest safe contract-aligned fix lands with focused regression tests; the
fake-sidecar suite passes; and the live-smoke command is either run against a
local attested sidecar or recorded as an environment-limited next step with the
exact command.

## Scope

Included: Duckling temporal adapter request/response handling, the local
Duckling build/resource manifest attestation decision, focused unit and
integration-smoke regression coverage, and this linked debugging record.

Excluded: semantic-ingestion architecture redesign, parent implementation-plan
editing, source-normalization design work, and unrelated semantic pipeline
changes.

## Constraints And Invariants

- `docs/design/semantic_ingestion_architecture.md` requires a pinned local
  Duckling temporal resolver that emits one typed `TemporalResolution` only for
  exact unambiguous temporal evidence and fails closed otherwise.
- The resolver is temporal-only authority. Non-time Duckling rows are not
  durable evidence and must not become accepted temporal candidates.
- The build manifest and packaged resource intentionally leave
  `produced_image_digest` unverified until a local build attestation binds a
  concrete image digest; no file should claim an unattested runtime digest.
- This debugging slice is the sole detailed owner of the live-smoke failure
  boundary while the parent implementation writer remains active.

## Incident Or Symptom

- Observed behavior: the optional live local smoke for
  `tests/unit/core/semantic_ingestion/test_duckling_temporal_adapter.py::test_live_loopback_sidecar_smoke_when_explicitly_attested`
  returns `None` for text `mañana 2026-01-02` against a locally built Duckling
  sidecar with image digest
  `cf8d2a7b0982ad0be904a5fe2ae00c638867b6e05e7f61f0910427b928bf3fd0`.
- Expected behavior: the same request should produce one exact typed temporal
  candidate for `2026-01-02` because the date span is explicit and unambiguous.
- Impact: the certified local temporal lane cannot pass its real smoke and
  therefore cannot be trusted as an enabled production authority.
- Frequency: deterministic for the supplied payload shape.
- First known occurrence: 2026-08-10 during local sidecar smoke after the new
  Duckling adapter landed.
- Affected environments: local loopback Duckling sidecar built from pinned
  commit `59a13ff87b1aa8be6b93d387244f8636b26185c5`.
- Affected versions: current dirty tree carrying the new temporal adapter.
- Known working environments: fake transport unit tests with the adapter's
  original synthetic byte-offset payload.
- Available reports: live payload evidence showing character offsets
  `start=7,end=17`, one `dim=time` row whose nested `value` includes `values`,
  and one non-time row; current adapter code; current focused unit tests.

## Reproduction Contract

- Environment: repository dirty tree plus local Python test environment; live
  smoke additionally requires a locally built loopback Duckling sidecar and
  explicit env vars.
- Reproduction steps:
  1. Call `DucklingTemporalResolver.resolve(...)` with the existing smoke
     request text `mañana 2026-01-02`.
  2. Feed the resolver a payload matching the live Duckling response family:
     character offsets `7..17`, a time row whose nested value includes
     `values`, and a second non-time row.
  3. Observe the resolver return `None` and record `last_failure_reason`.
- Expected signal: one complete `TemporalResolution` with one candidate for the
  exact date span.
- Actual signal before fix: `None`, first with
  `Duckling returned an inexact temporal span`; after correcting only the
  offset interpretation, the same family would still fail on either
  `Duckling temporal value has an unsupported shape` or
  `Duckling returned an unsupported temporal value`.
- Reproducibility rate: deterministic with fake transport payloads.
- Sources of nondeterminism: live local smoke depends on Docker/local sidecar
  availability, but the causal payload family is deterministic under fake
  transport.

## Timeline

- 2026-08-10: parent implementation added the sealed local Duckling sidecar,
  adapter, and optional live smoke.
- 2026-08-10: local image was built and attested out-of-band with digest
  `cf8d2a7b0982ad0be904a5fe2ae00c638867b6e05e7f61f0910427b928bf3fd0`.
- 2026-08-10: real local smoke returned `None` for `mañana 2026-01-02`.
- 2026-08-10: debugger inspected the live payload family and reproduced the
  failure under fake transport.

## Hypothesis Ledger

| ID | Hypothesis | Supporting evidence | Contradicting evidence | Experiment | Result | Status |
| -- | ---------- | ------------------- | ---------------------- | ---------- | ------ | ------ |
| H1 | The adapter interprets Duckling offsets as UTF-8 bytes, but the real API returns character offsets. | The live payload uses `start=7,end=17` for the ten-character date after `mañana `; the current adapter fails first with `Duckling returned an inexact temporal span`; the existing positive unit test hard-codes byte offsets. | None yet. | Replay the real payload family under fake transport and compare failure reasons for scalar versus byte offsets. | Scalar-offset payload fails with `inexact temporal span`; legacy byte-offset payload succeeds. | supported |
| H2 | The adapter rejects documented Duckling time payload shape because nested `value.values` is treated as an unknown field. | Duckling README examples show time values containing `values`; the current parser only permits `type`, `value`, and `grain`. | A payload with byte offsets but no `values` succeeds today. | Replay the same row with byte offsets and nested `values`, keeping all else equal. | The adapter fails with `Duckling temporal value has an unsupported shape`. | supported |
| H3 | The adapter fails because the resolver asks Duckling for every dimension and then rejects the returned non-time rows instead of constraining or ignoring them. | Duckling enables all dimensions by default; current request omits `dims`; real payload family includes a phone-number row; current parser raises on any non-time row. | Even without the phone row, scalar offsets alone already fail first. | Replay a byte-offset time row plus one non-time row with the current parser. | The adapter fails with `Duckling returned an unsupported temporal value`. | supported |

## Experiment Log

- 2026-08-10, E1, hypotheses `H1` vs all others:
  Procedure: replay a fake Duckling payload matching the live shape exactly.
  Expected discriminator: if `H1` is true, the first failure reason should be
  span mismatch before value-shape or mixed-dimension handling.
  Actual result: resolver returned `None` with `Duckling returned an inexact
  temporal span`.
  Conclusion: offset interpretation is a confirmed part of the causal chain.
  Evidence: local Python reproducer against the current adapter.
- 2026-08-10, E2, hypotheses `H2` and `H3`:
  Procedure: isolate the remaining variables by replaying (a) byte offsets plus
  nested `value.values`, and (b) byte offsets plus a non-time row.
  Expected discriminator: the parser should fail separately on the nested value
  shape and on mixed dimensions if those are independent defects.
  Actual result: case (a) failed with `Duckling temporal value has an
  unsupported shape`; case (b) failed with `Duckling returned an unsupported
  temporal value`.
  Conclusion: both assumptions are independently incompatible with the real API
  family and must be corrected or constrained by the request.
  Evidence: local Python reproducer against the current adapter.

## Root-Cause Statement

The live smoke failed because the adapter encoded three incorrect Duckling API assumptions:
character offsets are treated as UTF-8 byte offsets, documented nested
`value.values` is rejected, and the temporal-only resolver calls `/parse`
without constraining `dims`, then treats returned non-time rows as fatal. Those
assumptions propagate from `_call_sidecar` and `_parse_rows` into an early
`None` result before any `TemporalResolution` can be emitted. The original fake
transport tests missed the defect because they modeled only the adapter's
invented byte-offset, time-only, no-`values` payload shape.

## Fix Strategy

- Smallest safe correction: send `dims=["time"]` to Duckling, interpret
  offsets as exact text-character positions, accept nested `value.values` only
  when they reduce to the same single unambiguous instant as the primary time
  value, and ignore irrelevant non-time rows if they still appear.
- Alternatives considered:
  - Preserve byte offsets and special-case only this smoke string. Rejected:
    contradicts the real payload family and leaves the general contract wrong.
  - Accept any `values` list regardless of multiplicity. Rejected: would hide
    ambiguous temporal output instead of preserving fail-closed semantics.
  - Only send `dims=["time"]` and leave the parser otherwise unchanged.
    Rejected: live payloads would still fail on character offsets and nested
    `value.values`.
- Expected side effects: real Duckling time rows matching the documented shape
  become admissible; ambiguous multi-value time rows remain rejected.
- Compatibility risks: callers expecting invented byte-offset payloads will
  fail in tests and must be updated to the authoritative contract.
- Migration implications: none for persisted state because this fix affects
  ephemeral temporal analysis only.
- Rollback: revert the adapter/test delta and restore the previous unit payload
  contract if a contradictory authoritative Duckling contract is later proven.

## Regression Proof

- The fake-sidecar family passes: `7 passed, 1 skipped`.
- Ruff passes for the adapter and focused test.
- The built image is attested as
  `sha256:cf8d2a7b0982ad0be904a5fe2ae00c638867b6e05e7f61f0910427b928bf3fd0`.
- The first corrected live request exposed a fourth operability assumption: a
  two-second client timeout is shorter than the pinned sidecar's cold request.
  The bounded default is now ten seconds; transport timeout remains explicit
  and caller-overridable.
- The exact live command passes against the loopback-only container.

## Blockers And Limits

- Iteration budget: one focused causal isolation round, one fix batch, one
  focused verification batch.
- Current blockers: none.
- Conditions required to resume if blocked: access to a runnable local Docker
  daemon or equivalent sidecar host if the optional live smoke cannot be
  executed from this environment.

## Next Action

Resume the parent implementation only after its separately frozen authority
packet design completes review.
