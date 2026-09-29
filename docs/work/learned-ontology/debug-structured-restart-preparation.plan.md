# Structured Submission Restart Preparation Debugging WorkPlan

- Work ID: `learned-ontology-structured-restart-preparation` (planning coordinate only)
- Work type: debugging
- Delivery fidelity: Level 2, early real-world testing of the ordinary public no-key restart path; defer hostile-storage and exhaustive release matrices to the parent Level 3 milestone
- Status: complete at Level 2
- Coordinator: `/root`
- Created: 2026-09-26
- Last updated: 2026-09-26
- Parent WorkPlan: `docs/work/learned-ontology/implementation.plan.md`
- Related WorkPlans: `docs/work/learned-ontology/design.plan.md`, `docs/work/learned-ontology/debug-native-graph-authority.plan.md`
- Canonical inputs: approved `docs/design/learned_ontology.md` Section 5 and `docs/work/learned-ontology/milestones/structured-fact-no-key.plan.md`
- Expected outputs: deterministic public JSONL restart reproducer, causal diagnosis, smallest invariant-level repair, focused retry/status/revocation/no-network evidence and targeted independent closure review

## Expected And Observed

An exact authenticated structured submission that committed on a verified-production `ProviderMemoryService` must recover its same operation and terminal after reopening the same JSONL memory plane, under current grants and without a model or network call. A focused dirty-tree experiment removed `OPENAI_API_KEY`, denied socket DNS/connect, and got `committed` initially. A fresh verified-production service returned `denied/source_span_denied` on exact retry before terminal recovery. The attempted test was removed after its 61.67-second failure; no regression or product edit from that experiment was retained. This is a new-feature restart defect on the implementation branch, not a proven baseline failure.

## Boundary And Hypotheses

`ProviderMemoryService.submit_structured_fact` validates exact spans before operation allocation/recovery. Its `_validate_structured_source_spans` calls `runtime.prepared_source_repository.load` without an operation fence. `AtomicStorePreparedSourceRepository` delegates to the durable store. Existing source preparation can have a source-keyed or fence-keyed record; their allocation and lookup must match across restart. The root cause has not been confirmed.

| Hypothesis | Prediction | Discriminating observation |
| --- | --- | --- |
| Prepared record is durable under a fence-specific key while public validation reads the source-keyed key | JSONL snapshot contains matching prepared wire under a different ID and same source/digest | Compare all prepared record IDs/content and the source operation fences before and after reopen |
| Production reopen changes or loses the prepared-source repository/runtime authority | Record exists at expected key but the reopened repository is absent or points at a different store/profile | Compare repository type/store identity and exact `load_prepared_source` result under both service instances |
| JSONL encoding/reload changes typed prepared bytes or source digest | Record exists but decode/join rejects or reconstructs a different digest | Run exact typed loader and report its exception or mismatch, without falling back to an inferred source |

## Experiments And Repair Rule

First retain a deterministic failing public test with bounded diagnostics, then compare exact memory IDs and typed source/fence joins across the two service instances. Select the causal hypothesis and change the canonical owner, not a test-only bypass. The repair must preserve pre-allocation exact-span denial for a new operation, same-envelope retry identity, current-grant terminal authorization, source/fact/catalog commit fence, and no extra records after reopen. A post-reopen revocation must deny terminal disclosure. The clean-source public read proof and existing internal direct JSONL retry are siblings.

## Evidence, Identity And Review

Current command from `memorii/`: `.venv/bin/python -m pytest tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py::test_verified_production_public_structured_fact_jsonl_recovery_denies_revoked_retry_without_network -vv -s -p no:cacheprovider` under Python 3.14.7/pytest 9.1.1 failed at reopened retry; the test no longer exists. The branch is `codex/learned-ontology-implementation`, HEAD `5716ba1143a124f98df4c9701f1420a4ee71b0f2` plus dirty implementation and preserved user design files. Changed-surface candidate: `core/provider/service.py`, `core/memory_evolution/atomic_store.py`, prepared-source repository and feature-local composition test; final owner is determined by the experiment. No new persisted identity is authorized by this plan. Track exact commands and outcomes below. At candidate freeze, obtain targeted correctness and test review of restart/revocation behavior; classify findings under root `AGENTS.md`. `remaining_validated_p1_p2` is not yet a closure claim.

## Progress And Next Action

2026-09-26: the public restart probe found a committed first call and a denied exact retry after JSONL reopen. A read-only source inspection confirms the span check precedes terminal recovery and that the durable repository supports source-keyed and fence-keyed prepared records. No causal hypothesis is yet proven. The parent implementation remains on milestone 1 and pauses overlapping product edits for this linked debugging operation.

2026-09-26 discriminating composition result: the reopened service had no `_semantic_runtime` even though the durable writer record remained. Constructing it directly exposed `ValueError: fixture publication lease authority is already bound` from the stateful test-only source-normalization builder. Reusing one builder across two service instances selected hypothesis 2 and ruled out a demonstrated persisted prepared-record loss or digest/key mismatch. Reconstructing a fresh verified host capability and normalization builder for each process made the exact public JSONL retry pass in the retained reproducer. The worker is finishing status, revocation, no-duplicate and zero-network assertions; no production code change is justified by this observation.

2026-09-26 focused proof: the retained verified-production JSONL test now constructs a fresh host capability/normalization builder per service process. With `OPENAI_API_KEY` absent and socket DNS/connect blocked, it passed first commit/status, reopened exact retry/status, one event-batch increment, one catalog binding and native runtime claim, then fact-grant revocation on the reopened service denied status and retry without a second proposal. The new test passed alone in 51.91 seconds; it and public clean-source/internal restart siblings passed 3 in 166.35 seconds. Targeted Ruff, compilation and `git diff --check` passed. No production code was changed. Targeted correctness and test reviewers are checking the frozen fixture/test delta before closure; no CI or Level 3 claim is made.

2026-09-26 first targeted review reconciliation: the test reviewer confirmed the fixture-lifecycle root cause but identified two concrete P2 `changes_required` verification gaps: no affirmative reopened public status lookup before revocation, and no exact normalized record-map equality across retry. The sole test writer is adding those two assertions and rerunning focused checks. The correctness reviewer flagged absence of an installed adapter caller as `Not applicable / blocks_approval`; that gap is confirmed for the parent implementation milestone and already recorded with installed caller count zero. It does not contradict the linked debugging question, which is whether a fresh verified-production service recovers the durable public terminal. The cited prior engineering-closure binding JSON is not this ontology WorkPlan's binding ledger. A targeted re-evaluation is pending; no debug closure is claimed yet.

2026-09-26 bounded test remediation: the reopened service now calls the public status API before retry/revocation and asserts `committed` with the original operation ID. The test also snapshots `memory_id -> record_digest` after first commit and requires exact equality after reopened retry, retaining event/binding/projection and revoked-denial checks. The focused test passed in 57.18 seconds, targeted Ruff and whitespace passed. A correctness re-review was requested while the candidate was still moving and correctly withheld judgment on freeze grounds; no substantive product finding came from that attempt. All writers have now stopped; record the candidate identities and run one targeted frozen delta review.

Frozen targeted candidate: HEAD `5716ba1143a124f98df4c9701f1420a4ee71b0f2`; tracked dirty diff SHA-256 `e8fafd1397ecc13365a266cd6f40f19ad986c9b721b5ac6df9557f59560065e9`; test file SHA-256 `ebbd157682431ace7c735d23e46818304ed71d33bce30e15c05085c68735a8fc`. The untracked approved design and WorkPlan files are separately preserved, not included in the tracked diff digest. The exact debugging-plan SHA-256 is supplied to reviewers after this line is saved. The frozen review concerns this one new test and the fixture-lifecycle root cause, not the incomplete parent milestone.

2026-09-26 frozen targeted review and coordinator reproduction: correctness and test reviewers rechecked HEAD, tracked diff, test and pre-closure plan digests and found no remaining Level-2 defect in the bounded fixture/restart claim. The test reviewer confirmed both prior P2 verification findings closed. The coordinator independently ran `./.venv/bin/python -W error -m pytest tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py::test_verified_production_public_structured_fact_jsonl_recovery_denies_revoked_retry_without_network -q -p no:cacheprovider` from `memorii/`: 1 passed in 56.23 seconds under root `.venv` Python 3.12.14. The worker's sibling run passed 3 in 166.35 seconds under Python 3.14.7. No production code fix was warranted: the trigger was fixture reuse, the defective assumption was that a stateful host builder could bind to two services, and the resulting runtime-construction failure propagated to `source_span_denied` before durable recovery. A fresh per-process host builder restores the production-shaped composition and exact retained terminal read. The parent implementation still has no installed Hermes structured caller and no verified schema-1 mixed-history reader; this debugging closure does not approve that milestone, CI, or Level 3 release.

## Closure

- Root-cause class: test fixture lifecycle, not persisted JSONL data loss.
- Changed artifact: focused feature-local composition regression test only; no production code or persisted schema change for this debugging operation.
- Verified outcome: exact public commit/status/retry after JSONL reopen, no extra normalized records, current-grant revocation denial, no API key and no socket egress.
- Reviewer disposition: targeted correctness and test reviews approved the frozen bounded delta; `remaining_validated_p1_p2: []` for this linked Level-2 debugging operation.
- Deferred to parent Level 3: installed adapter caller, schema-1 compatibility decision, package/CI/release evidence.

**Next action:** return to the parent milestone and open the linked design delta for Hermes authenticated structured submission and schema-1 legacy compatibility.
