# M0 Scenario-First C2 Implementation

- Work ID: semantic-ingestion-m0-scenario-first-c2-implementation-2026-07-30
- Work type: implementation
- Status: active
- Coordinator: Codex
- Created: 2026-07-30
- Last updated: 2026-07-30
- Parent WorkPlan: `docs/work/semantic_ingestion/m0-current-pin-c2-recipe-closure-2026-07-30/design.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/implementation.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion/scenario_first_fixture_authority.md`; `docs/design/semantic_ingestion_architecture.md`; `docs/design/semantic_ingestion/traceability_golden_vectors/ctv-binding-authority-v2.json`
- Expected outputs: strict scenario/run validation, registered CTV-v2 fixture bodies, deterministic public-ingress evidence, and verified non-operational C2 closure.

## Objective

Replace the provisional scenario-first hash-wrapper path with a deterministic,
fail-closed C2 derivation that uses only registered CTV-v2 body schemas and
cannot be consumed as production authority.

## Completion Contract

- every input is closed, size-bounded, and validated before derivation;
- fixture 35 contains a registered `TraceabilityGoldenTypedInputFixtureBody.v1`
  boundary over actual public-ingress evidence;
- structural, coverage, execution, and G1/G2/G3 records use their registered
  body schemas with complete, derivable operands;
- repeated deterministic ingress and two independent elaborators reproduce the
  complete canonical bytes and fail-closed mutation behavior;
- all administrator, trust, signer, report, and generation operands required by
  registered schemas are supplied by an approved non-operational authority.

## Scope

Included: scenario validator, ingress runner, scenario elaborators, manifest
verifier, focused tests, and the linked design WorkPlan evidence.

Excluded: production release activation, operational signatures, and changes to
Layer1 schemas or registry semantics.

## Current State

Milestone 2 emits the raw/tool dependency members, byte-backed fixture 35,
and an isolated-test-trust registered closure. Default production trust
resolution contains no scenario-test root; only explicit acceptance-test
composition can install that trust. The reference elaborator uses production CTV artifact encoding;
the independent elaborator recomputes the exact CTV grammar and length-prefixed
artifact preimage without importing that codec. The stable evidence projection
selects semantic fields from extractor proposals and never rewrites raw model
dumps. Structural, execution, and generation members are intentionally absent
and rejected until their separately scoped milestone is implemented.

## Milestones

1. Emit deterministic public-ingress semantic evidence with validated source,
   run, design, registry, authority, and tool pins -- completed.
2. Emit registered fixture-35 CTV-v2 bytes with an exact canonical content
   boundary -- completed.
3. Independently re-encode and strictly verify the bounded fixture package --
   completed.
4. Implement structural, coverage, execution, and test-root G1/G2/G3 closure
   -- implementation complete. Independent A/B full-package bytes agree and
   the validator accepts the explicit isolated-trust public gate.

## Evidence Log

- `TraceabilityGoldenTypedInputFixtureBody.v1` requires a registered target
  binding and `TraceabilityCanonicalContentBoundary` fields.
- `NormativeExecutionEvidenceRecordBody.v1` requires signer, trust snapshot,
  report, runner, revision, and execution operands.
- The scenario-first files currently expose only scenario/run/design/registry
  bytes plus a non-operational root string.
- 2026-07-30: the user resolved the issuance-purpose conflict by authorizing a
  deterministic test-only trust root. Registered bodies remain
  operational-shaped, but only a scenario test trust configuration contains
  that root; default/production trust lookup rejects it before release
  authority is established.
- `ExtractedClaim` at `memorii/memorii/core/memory_evolution/models.py:362`
  has no `polarity`, `modality`, `attribution`/speaker, or claim-level
  `source_type` field. The required comparator contract explicitly requires
  those values (`scenario_first_fixture_authority.md:32-42`), so it cannot
  distinguish an otherwise identical negative, modal, or indirectly-attributed
  proposal from the admitted direct-positive scenario.
- 2026-07-30: replaced post-hoc timestamp rewriting with the explicitly named
  `scenario_semantic_persisted_projection` v1. It records only selected
  extraction semantics and binds every row to its digest, while raw persistence
  remains untouched.
- 2026-07-30: focused milestone-1 verification passed: repeat ingress bytes,
  A/B byte equality, strict production `decode_artifact` binding and
  re-encoding, fixture/body/binding/content/tool/scenario/run/extra-field
  mutations, `pytest` (1 passed), Ruff, and `git diff --check`.
- 2026-07-30: hardened acceptance generation fixtures now retain exact typed
  bootstrap/recovery/policy/lifecycle/release/history bytes, frozen per-kind
  bindings, and ordered reachable dependencies. The successor/idempotent retry
  gate passed in 338.09s; foreign verifier-held trust rejection passed without
  advancing the provisioned watermark.
- 2026-07-30: full-package A/B equality and public validator acceptance passed.
  Production exactness coverage passed 6 tests; successor/idempotency passed 1
  test; the combined focused run confirmed foreign-trust rejection.
- 2026-07-30: a composition-owned default trust resolver was added. Exact
  scenario bytes reject under default resolution with unchanged watermark;
  an explicit test-only resolver remains the only path to scenario trust.
- 2026-07-30: focused resolver evidence passed default and foreign rejection.
  The explicit-test positive gate is pending the registered-body builder's
  signer-coordinate migration: the current verifier rejects the legacy empty
  coordinate and its old manifest digest preimage.
- Decision: an extracted proposition is explicitly either a source-grounded
  world assertion or a source-grounded attributed belief.  Existing payloads
  without that information are unresolved, never silently treated as world
  assertions; unresolved and non-asserted propositions cannot promote.
- 2026-07-30: `ClaimKey` and LLM-derived claim IDs now partition assertion
  mode, epistemic status, polarity, modality, and canonical belief holder.
  Entity rekeying updates the semantic holder and mirrored key atomically.
- 2026-07-30: promotion is source-certified: reported belief/speech, negative,
  modal/ambiguous, quoted, and interrogative source text cannot become active
  world truth merely because model output labels it `world_assertion`.
- 2026-07-30: normal current/historical truth retrieval excludes unresolved,
  attributed, negative, and modal claim states, while all-version and
  evidence-only access retain them for audit and recovery.
- 2026-07-30: malformed resolved semantic context is isolated per claim during
  LLM conversion. A wrong attribution source is recorded as `claim[idx]`, the
  run becomes partial, and valid siblings remain in the returned typed proposal
  without restoring custom validators on registered transport models.
- 2026-07-30: world-assertion source certification now examines exactly one
  grounded attribution evidence quote rather than unrelated text elsewhere in
  the source envelope. Empty or multiple attribution spans fail closed.
  `ClaimState` now rejects every mismatch between its persisted key and
  semantic context, so malformed hydration aborts before normal truth
  retrieval.
- 2026-07-30: evidence phrases now only locate a uniquely derived source
  construction; classification uses that complete construction, never a
  provider-cropped embedded clause. Offset-bearing evidence must match the
  source characters exactly but cannot set construction boundaries.
- 2026-07-30: focused verification passed: 8 semantic-context tests; 109
  primitive/production-boundary tests; 5 captured-ingestion replay tests;
  targeted prompt/public-contract/runtime-artifact selection completed without
  a reported failure; and Ruff passed for changed semantic/runtime files.
- 2026-07-30: deterministic ingress repeated with byte-identical run output;
  independent A/B elaborators produced byte-identical manifests and structural
  spools; the strict manifest verifier accepted the result and rejected spool,
  pin, fixture-dependency, G3-generation, and resource-limit mutations.

## Decision Log

- 2026-07-30: preserve partial scenario-first edits; do not create new CTV
  schemas or repurpose the provisional wrapper schema as authority.
- 2026-07-30: use the frozen registered schemas and normal closure verifier
  with a deterministic test-only root. The root is test harness configuration,
  not registry authority or a production release credential.

## Review Log

- 2026-07-30: fresh correctness review found missing semantic decoding,
  nondeterministic run bytes, incomplete comparator, and text-only operation
  identities. These require remediation before approval.

## Blockers And Limits

- The contract decision authorizes adding explicit source-grounded assertion
  mode, epistemic status, polarity, modality, and attribution/belief-holder
  fields. It does not authorize changes to M0 trust-artifact closure.
- Not applicable / blocks_approval: the registered RP signer coordinate and
  BA/RR lifecycle-root coordinate have no legal genesis values. The smallest
  governing correction is an explicit `independently_provisioned_genesis`
  provenance union/variant; ordinary successors must retain the lifecycle
  coordinate.
- Not applicable / blocks_approval: full
  `NormativeTraceabilityStructuralManifestBody` derivation and preimages are
  unspecified and unimplemented. The legacy six/seven-field projection and
  approximation cannot be treated as canonical.

## Verified Progress

- Signed generation manifests/pointers, exact DAG/Kahn ordering, and strict
  noncyclic validators are implemented and exercised.
- Default-resolver and foreign-trust rejection tests prove scenario trust is
  absent from default production composition and failures leave watermark state
  unchanged.
- M1 must not begin while either governing design blocker remains unresolved.

## Next Action

Complete `m0-canonical-genesis-structural-contract-correction-2026-07-30`
design review and approval; M1 must not begin.
