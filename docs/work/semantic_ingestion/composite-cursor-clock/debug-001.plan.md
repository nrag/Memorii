# Composite Cursor Clock Debugging

- Work ID: composite_cursor_clock_debug_001
- Work type: debugging
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-09-05
- Last updated: 2026-09-05
- Parent WorkPlan: `docs/work/semantic_ingestion/m4-closure-2026-09-04/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/acceptance-evidence-closure-2026-09-05/testing.plan.md`; `docs/work/semantic_ingestion/milestones/m4-event-history.plan.md`
- Canonical inputs: `docs/design/memorii_spec.md`; `docs/design/memorii_storage_details.md`; `docs/design/event_model.md`; `docs/design/semantic_ingestion_architecture.md`
- Expected outputs: one clock-consistent composite cursor owner and family-complete pagination/reopen proof

## Objective

Restore deterministic composite conflict pagination so a repository configured
with an injected clock issues and validates composite cursors against that same
clock across initial listing and reopen.

## Completion Contract

Complete only when the six reproduced composite-pagination failures pass, the
expired-key negative remains fail-closed, the complete conflict-attention family
passes, the root cause is independently challenged, and a revision-bound scoped
closure record contains empty required-finding arrays.

## Scope

Included: clock ownership between `FileConflictAttentionRepository` and
`CompositeConflictListingRepository`, cursor issuance/verification, focused
tests, and linked WorkPlan evidence.

Excluded: cursor protocol changes, key lifetime changes, conflict-attention API
redesign, replan/replay semantics, M5, and unrelated timing cleanup.

Deferred: whole-branch gates and hosted CI to the parent completion operation.

## Constraints And Invariants

- One logical repository composition must use one authoritative injected clock.
- Cursor issuance remains fail-closed when no key covers the full cursor life.
- Reopen must validate retained snapshots and cursors without ambient-time
  substitution.
- No compatibility fallback may silently extend an expired key.

## Identity And Coordinate Hygiene

No product or protocol identity change is expected. The WorkPlan identifier is
a planning/evidence coordinate retained only here. Closure will run the existing
field-aware identity gate for changed surfaces.

## Change Impact And Verification Closure

| Path | Surface | Owner | Authority chain | Gates | Status |
| --- | --- | --- | --- | --- | --- |
| `memorii/memorii/core/memory_evolution/composite_conflict_listing.py` | product code | composite listing owner | ledger clock -> snapshot/cursor issue -> continuation validation | focused repository family; full attention family | corrected and verified |
| `memorii/memorii/core/memory_evolution/conflict_attention_repository.py` | product code | file ledger/key owner | configured clock -> key window | focused repository family | corrected and verified |
| `memorii/tests/unit/core/test_composite_conflict_listing_repository.py` | regression tests | this debug | injected clock -> positive pagination and expired-key negative | exact file | 10 passed |
| `docs/design/semantic_ingestion_canonical_evidence/production-entrypoint-bindings-v1.json` | runtime binding ledger | canonical evidence owner | public prefetch -> attention page -> composite -> ledger clock/key | mapping and focused path proof | updated |

## Expected And Observed Behavior

Expected: `_seeded_repository` supplies `now_provider=lambda: NOW`; composite
listing issues a cursor under the active key valid from `NOW-1d` through
`NOW+1d`, and reopen verifies it at `NOW`.

Observed: six pagination tests raise
`ConflictAttentionReadError("conflict_cursor_key_unavailable")` because
`CompositeConflictListingRepository` defaults to ambient
`datetime.now(UTC)` instead of the file ledger's configured clock. The negative
test with only 1000 seconds of remaining key lifetime must continue to fail.

Classification: supported deterministic pagination/reopen runtime defect.

## Hypothesis Ledger

| Hypothesis | Mechanism | Discriminator | Status |
| --- | --- | --- | --- |
| split clock ownership | composite issues against ambient time while ledger key was selected against injected time | explicitly pass `now_provider=lambda: NOW` or share ledger clock; six failures pass | supported by code and date-sensitive failure |
| invalid active-key selection | ledger selects a non-signing, revoked, or short-lived key | inspect `_active` and `_key_may_sign` at identical `NOW` | weakened: fixture key is signing and covers full lifetime at `NOW` |
| corrupt retained snapshot | snapshot persistence changes key or time bindings | failure occurs before cursor is returned on first page | rejected |

## Experiments

### Failing family reproduction

- Procedure: run all conflict-attention, composite, Hermes, and persistence
  families.
- Result: 137 collected; 131 passed and six composite repository tests failed
  at initial cursor encoding with `conflict_cursor_key_unavailable` in 331.51s.
- Conclusion: failure is isolated to composite cursor issuance.

### Direct-composition discriminator and correction

- Procedure: run `PYTHONPATH=memorii .venv/bin/python -m pytest memorii/tests/unit/core/test_composite_conflict_listing_repository.py -q` before and after the correction.
- Before result: six failures and three passes in 7.91s; each failure reached v2 cursor emission and raised `conflict_cursor_key_unavailable`.
- Correction: `FileConflictAttentionRepository.cursor_clock()` exposes its configured cursor-key clock. A composite without an explicit clock now uses that accessor, and its v2 claims carry `issued_at=self._now()` rather than invoking the cursor codec's ambient fallback.
- After result: 10 passed in 8.96s. The added explicit-override discriminator proves an override at `NOW + 200s` remains authoritative and rejects a key that cannot cover the full 900-second v2 lifetime. The existing moving-ledger-clock short-lived-key negative also remains closed.
- Conclusion: the first edit alone did not clear the failure because `encode_composite_cursor` has a documented ambient fallback for callers that omit `issued_at`; the composite owner had omitted it. Supplying the owner clock at that callsite completes the invariant without changing the shared codec fallback or key protocol.

## Root-Cause Statement

Trigger: a composite listing is created from a file ledger whose injected time
differs from wall time. Defective assumption: the composite wrapper creates a
second ambient clock instead of inheriting the child repository's clock.
Propagation: the snapshot and cursor issuance use ambient time, the active key
was configured for the ledger's time window, and `_key_may_sign` rejects the key
before returning page one. Existing tests missed the defect while wall time
happened to overlap the fixed fixture window.

## Evidence And Gate Ledger

| Gate | Command | Status |
| --- | --- | --- |
| exact reproducer | `PYTHONPATH=memorii .venv/bin/python -m pytest memorii/tests/unit/core/test_composite_conflict_listing_repository.py -q` | before: 6 failed, 3 passed in 7.91s; after: 10 passed in 8.96s |
| complete attention family | `PYTHONPATH=memorii .venv/bin/python -m pytest -W error` over the complete conflict-attention, composite-listing, Hermes, and persistence family | final candidate: 147 passed in 588.82s |
| scoped Ruff/compile/JSON/diff | `ruff check` on three changed Python files; `py_compile` on those files; `python -m json.tool` on the binding ledger; `git diff --check` | passed |
| identity hygiene | `PYTHONPATH=memorii .venv/bin/python -m memorii.tools.identity_hygiene --root . --allowlist .agents/identity_hygiene_allowlist.json` | passed |

## Delegation And Cost Ledger

| Task | Role | Ownership | Rationale | Status |
| --- | --- | --- | --- | --- |
| coordinator triage | coordinator | read-only | isolate failure and hypotheses | complete |
| invariant correction | `worker` / Terra-class | sole writer | one clock owner plus proof | complete |
| closure review | spec/correctness/test reviewers | read-only | required debugging closure | complete; all required-finding arrays empty |

## Progress Log

- 2026-09-05: M4 Operation 2 full family reproduced six cursor-signing-key
  failures after 131 passing tests. Code inspection isolated split ambient and
  injected clocks before cursor emission.
- 2026-09-05: The direct-composition discriminator reproduced 6 failures and
  3 passes in 7.91s. The invariant correction and explicit-override regression
  made the focused file pass 10 tests in 8.96s; the complete 138-test affected
  family passed in 436.43s.

## Evidence Log

- Failure site: `CompositeConflictListingRepository.list_conflicts` calls
  `encode_composite_cursor` with claims derived from `self._now()`; default
  construction binds `self._now` to ambient UTC time.
- Fixture key is valid for the full composite cursor lifetime at injected
  `NOW`, proving the key itself is not unavailable at the repository clock.
- The production caller map has one public attention trigger:
  `ProviderMemoryService.prefetch_with_attention` -> `_attention_page` ->
  `_composite_attention_repository` -> `CompositeConflictListingRepository`
  -> file-ledger clock and signing key. The enabled composite branch requires
  the file-ledger child and carries authenticated conflict access; disabled and
  wrong-child branches remain closed.

## Decision Log

- Decision: preserve cursor/key protocol and correct clock ownership only.
  Rationale: key lifetime and fail-closed behavior are already explicit and the
  defect is the composition of two different clocks.
- Decision: retain `encode_composite_cursor`'s standalone ambient fallback for
  its other callers, but make the composite repository supply its authoritative
  `issued_at`. Rationale: changing the codec default would widen this debugging
  slice; the composite owner is the only path that owns both the ledger clock
  and v2 listing lifetime.

## Review Log

Independent specification, correctness, and test reviewers examined candidate
manifest diff
`b1f487559a5e8222ace6f7d1f8aae1629edfb4ef58ec01d2a7f15c97bc987700`.
All three returned empty required-finding arrays. This closes only the bounded
debug slice; parent M4 completion remains governed by its own final gates.

## Blockers And Limits

No external blocker. Experiment budget: three; one used.

## Next Action

None in this debugging operation. Return the final 147-test evidence and clean
review disposition to the parent M4 closure WorkPlan.

## Outcome And Retrospective

Independent review confirmed and this slice corrected additional causes:
provider composition had overridden the ledger clock, and fresh-list failure
could retain snapshots before cursor-key rejection. Public v2 cursor parsing
now admits either grammar for routing; each repository still rejects the other
grammar. Focused provider/composite proof passes 43 tests in 8.98s. The full
affected family was rerun before the parser-test expectation correction and
reported 137 passed, one expected-outcome mismatch in 361.78s; it must be
rerun from the final tree. Final focused evidence now includes 47 passing
composite/provider tests: empty and one-page listings need no signing key,
paginated short-key failures retain byte-identical ledger state, and public
v1/v2 cross-protocol submissions reject without fallback. Residual risk is
the final full-family rerun plus independent closure review.

Final review found the membership/key preflight split race. The ledger now
prepares one composite listing under one exclusive file lock from one decoded
record image, conditionally preflights only paginated listings, and appends
both child snapshots through `_append_locked` after preflight. Focused
repository/provider proof: 50 passed in 7.62s; scoped Ruff and compilation
passed. The deterministic locked-read barrier proves a page-boundary append
waits until one-page preparation linearizes; public authenticated zero/one
short-key prefetch returns no cursor.

The final review also found that the atomic preparation path did not translate
malformed ledger rows through the established non-disclosing read-error
boundary. It now preserves typed repository errors and maps decode, replay,
open, and append failures to `conflict_attention_corrupt`. Direct and public
malformed-ledger tests prove the typed/opaque result and byte-identical durable
state. The full final affected family passed 145 tests under `-W error` in
341.94s; the final focused composite/provider set passed 51 tests in 9.04s.

A subsequent correctness challenge reproduced a cursor whose timestamp was
captured before a lock wait and was therefore expired when returned. Fresh
listing now selects its clock instant and signing key, assembles both child
snapshots and the composite snapshot, encodes the first cursor, and appends all
three snapshots within one exclusive-lock transaction. A deterministic test
advances the injected clock by 901 seconds while preparation is paused and
proves immediate public continuation succeeds. The separate page-boundary
test now observes the writer's real `LOCK_EX` attempt rather than relying on a
sleep. The focused repository file passes 19 tests under `-W error`.

Continuation now also resamples the authoritative clock after its complete
locked read and rejects an already-expired successor instead of emitting it.
The final focused repository file passes 20 tests under `-W error`; the final
complete affected family passes 147 tests under `-W error` in 588.82s. The
frozen manifest review is clean across specification, correctness, and test
coverage. No residual local blocker remains in this debugging slice.

The same challenge exposed the continuation half of the clock-wait family:
page two could validate and sign with a timestamp sampled before a blocked
snapshot read. Continuations now resample after the complete retained-snapshot
read, revalidate expiration, and use that same instant for successor signing.
A public regression pauses the locked read, advances time by 901 seconds, and
proves the request fails closed instead of returning an already-expired cursor.
The focused repository file now passes 20 tests under `-W error`.
