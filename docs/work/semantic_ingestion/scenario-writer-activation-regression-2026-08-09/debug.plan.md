# Scenario Writer Activation Regression

- Work ID: scenario_writer_activation_regression_2026_08_09
- Work type: debugging
- Status: ready_for_independent_review
- Coordinator: Codex main thread
- Created: 2026-08-09
- Last updated: 2026-08-09
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/scenario-v1-runtime-closure-2026-08-09/design.plan.md`; `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md`
- Candidate identity: `docs/work/semantic_ingestion/scenario-writer-activation-regression-2026-08-09/debug-activation-candidate-identity.json` (`review_pending`)
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md`; `memorii/memorii/core/semantic_ingestion/capability.py`; `memorii/memorii/core/memory_evolution/writer_admission.py`; `memorii/memorii/core/memory_evolution/atomic_store.py`
- Expected outputs: root-cause classification, smallest safe activation correction or explicit scenario-host activation, focused regression proof, and updated M3 boundary.

## Objective

Restore the scenario host's ability to persist an accepted local semantic terminal without weakening evidence-only writer protection or regenerating authority artifacts from a failing runtime.

## Completion Contract

Complete only after: the smallest public-ingress reproducer is deterministic; at least two hypotheses have a recorded discriminator; the causal writer-mode transition is proved; a focused regression fails before and passes after the correction; the evidence-only rejection sibling remains protected; and no scenario or CTV artifact is regenerated before the green reproducer.

## Scope

Included: scenario-test host capability construction, built-in local runtime writer activation, and direct focused tests of writer mode versus accepted terminal persistence.

Excluded: persistence performance, authority/CTV regeneration, production root provisioning, M4 behavior, and broad terminal suites.

## Expected And Observed Behavior

Expected: verified scenario-test host material plus the built-in local capability reaches an accepted terminal for `Atlas owner is Alice.` and persists its permitted graph/event effects.

Observed: the same path reaches terminal persistence with the writer still in `evidence_only` mode and fails with `PreplanningStoreError: evidence-only writer cannot publish graph or event effects`.

## Reproducer

Run the scenario public ingress runner against the four-case fixture. Its first accepted observation deterministically reaches the writer-mode rejection before emitting an output artifact. The narrow signal is the exact `evidence-only writer cannot publish graph or event effects` exception.

## Hypothesis Ledger

| ID | Hypothesis | Mechanism | Discriminator | Status |
| --- | --- | --- | --- | --- |
| H1 | Built-in local capability creates only epoch-one evidence-only admission and never activates verified semantic mode. | Accepted terminal effects are correctly rejected by writer policy. | The capability called `create_initial_evidence_only` and had no transition, while the accepted composition helper performs a certified empty migration. | confirmed |
| H2 | Bootstrap writer handoff should itself activate the writer but omits a valid migration authority. | The handoff starts terminal work with an evidence-only binding. | The handoff owns operation start, not writer lifecycle; activating there would bypass host-held migration authority. | disproved |

## Causal Chain And Correction

1. The scenario fixture supplied verified bootstrap and deployment authority, so
   provider ingress reached accepted terminal persistence.
2. `BuiltInLocalHostSemanticIngestionCapability` nevertheless created only its
   evidence-only writer epoch. The atomic store correctly rejected the terminal
   graph/event effects with `evidence-only writer cannot publish graph or event
   effects`.
3. The smallest safe correction is an optional host-owned
   `HostSemanticWriterActivation` hook. It is absent by default, retaining the
   conservative production/evidence-only behavior. The sealed `scenario_test`
   fixture supplies a certified empty migration and is the only caller that
   activates its initial writer.

## Focused Evidence

- Before the correction, the four-case public ingress runner failed 1/1 on its
  first accepted observation with the exact evidence-only rejection.
- After the correction, `PYTHONPATH=memorii .venv/bin/pytest -q
  memorii/tests/unit/tools/test_scenario_public_ingress_runner.py` passed `2`
  tests in `13.43s`. The sibling proves that removing the scenario host
  activation leaves the writer `evidence_only`.
- The deterministic public ingress runner then produced five rendered
  observations with `match`, `match`, `match`, `abstain`, and `match` outcomes.
  Independent elaborators A and B produced byte-identical manifests and
  spools; `validate_scenario_manifest.py --self-test` passed. These were
  temporary proof artifacts only; no authority, CTV, manifest, or spool was
  regenerated or pinned.

## Reopened Review Remediation (2026-08-09)

- Confirmed trust-domain gap: `trust_domain` had been a mutable material field
  and a `ProviderMemoryService` caller selector, rather than a signed release
  fact. The release evidence now binds it into its digest; bootstrap verification
  rejects a relabeled material/evidence pair, and the service no longer accepts
  a caller-selected domain. Initial writer activation additionally rejects any
  release not verified for `scenario_test`.
- Confirmed opaque-ID gap: the runner previously used one-based ordinal,
  ad-hoc JSON, and a noncanonical `sf-` spelling. It now constructs the exact
  zero-based typed-value CTV preimage and `scenario-event-` truncated spelling.
- Confirmed ambiguity gap: the ordered two-segment owner input is one public
  event. After both analyses it now closes as
  `protected_multi_segment_owner_ambiguity`, retaining two candidates/analyses
  but publishing no sealed operation or accepted carrier.
- Focused checks: opaque-ID agreement/mutation test passed in `5.08s`; explicit
  scenario activation/evidence-only sibling passed in `17.99s`; scoped Ruff
  passed. The one-event ambiguity scenario smoke run passed, but the local
  aggregated pytest harness did not preserve a terminal report after printing
  progress, so it is not recorded as a full-suite pass.
- JSONL reopen/retry/substitution remains a testing-plan follow-up: this debug
  slice does not start a potentially parked serialization run.

## Multi-Segment Route Remediation (2026-08-09)

- Confirmed implementation gap: pipeline validation accepted only one prepared
  segment and compared every analysis to the first route. A valid two-segment
  ambiguity therefore failed before the protected non-promoting outcome, while
  a copied span could be validated against the wrong sibling route.
- The pipeline now resolves the exact prepared child by the analysis segment
  identifier. Its route digest and every copied predicate/argument span must
  bind that child route's parent and local artifact. The protected ambiguity
  classification additionally requires one source/digest and two distinct
  `(segment_id, route_digest)` coordinates.
- Focused proof: `PYTHONPATH=memorii .venv/bin/python -m pytest
  memorii/tests/unit/tools/test_scenario_public_ingress_runner.py::test_multi_segment_route_selection_rejects_swapped_duplicate_and_wrong_source_evidence
  -p no:cacheprovider` passed `1` test in `5.02s`; it proves the valid second
  child, swapped sibling route, duplicate coordinate, equal owner value, and
  separate-source cases. Scoped Ruff, `py_compile`, and `git diff --check`
  passed. The existing runner smoke did not yield a terminal pytest report in
  this local harness, so the direct deterministic proof is recorded rather
  than a suite-pass claim.

## Assertion-Span And Source-Order Remediation (2026-08-09)

- Confirmed second-child span gap: the analyzer correctly located the second
  clause inside the child segment but emitted the whole child segment as its
  `assertion_span`. For the second clause that retained the leading separator
  space and triggered `independent_source_analysis_substitution` before the
  protected ambiguity closure.
- Confirmed canonical-order gap: the pipeline canonicalized local candidates
  by `candidate_id`, but the protected ambiguity classifier still compared the
  tuple in source-text order. The live public event therefore missed the
  protected closure and could persist an accepted terminal when the source text
  still spelled the exact `Alice` then `Bob` pair.
- Correction: the analyzer now binds `assertion_span` to the matched quote
  offsets, terminal candidates are canonicalized before rejected/evidence-only
  emission, and the protected ambiguity classifier orders paired
  candidate/analysis tuples by authenticated `assertion_span` coordinates
  rather than candidate-id order.
- Focused proof: `PYTHONPATH=memorii .venv/bin/pytest -q
  memorii/tests/unit/core/semantic_ingestion/test_bootstrap_text_preparation_producer.py::test_local_analyzer_binds_assertion_span_to_matched_quote_within_second_segment
  memorii/tests/unit/core/semantic_ingestion/test_bootstrap_text_preparation_producer.py::test_protected_owner_pair_uses_source_order_not_candidate_id_order
  memorii/tests/unit/core/semantic_ingestion/test_semantic_pipeline.py::test_local_rejected_terminal_canonicalizes_noncanonical_candidate_order
  -p no:cacheprovider -x` passed `3` tests in `12.68s`. `py_compile` passed
  for the changed analyzer, pipeline, and focused test files.
- Live direct public-ingress evidence changed from a wrong accepted terminal
  (`2` candidates, `2` analyses, `2` sealed operations, `2` accepted
  carriers) to the intended protected path entering terminal persistence.
  The remaining blocker is slow replay-authority dependency reconstruction
  during persisted terminal decode; that runtime cost is parked under the
  linked testing WorkPlan and is not further debugged in this slice.

## Exact Next Action

Obtain the coordinator's independent debug review, then hand the remaining
live replay-authority decode slowdown to the linked testing WorkPlan before
using the revision to regenerate any frozen authority artifact.
