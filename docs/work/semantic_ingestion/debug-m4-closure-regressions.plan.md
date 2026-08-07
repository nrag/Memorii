# M4 Closure Deterministic Regressions

- Work ID: m4_closure_deterministic_regressions
- Work type: debugging
- Status: completed
- Coordinator: Codex main thread
- Created: 2026-08-04
- Last updated: 2026-08-04
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/testing.plan.md`; `docs/work/semantic_ingestion/debug-clarification-recovery-corruption.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md`; `docs/design/event_model.md`; frozen public JSONL contract and current identity planning/commit implementation
- Expected outputs: causal classification for both deterministic failures, narrow corrections or authority-chain refresh, family-complete proof, and independent closure review

## Objective

Restore sequential rekey acceptance and reconcile the frozen public JSONL
identity without weakening identity authority, retry/reopen semantics, or
byte-level compatibility governance.

## Completion Contract

Complete only when both exact nodes pass; sequential rekey preserves one
logical identity without a second logical reservation; the frozen JSONL change
is either rejected as a regression or regenerated through the full authorized
authority chain with an exact byte-diff explanation; sibling retry/reopen and
frozen-member tests pass; and targeted independent review has no required
finding.

## Incident Or Symptom

- The second terminal in the sequential rekey test is unresolved with
  `identity_lineage_compilation_failed`.
- The public JSONL service test retains exact wire and member digests but whole-
  file SHA-256 changed from `94f0b866...` to `201cbdb2...`.
- The invalid timing runs were discarded; no timing evidence was merged.

## Hypothesis Ledger

| ID | Hypothesis | Experiment | Status |
| -- | ---------- | ---------- | ------ |
| H1 | second rekey reuses stale frozen authority/reservation state after the first committed materialization | expose swallowed compiler exception and compare first/second artifacts and CAS bindings | rejected: the compiler was reprojecting embedded historical lineage coordinates |
| H2 | store-owned verifier or reference ledger rejects legitimate same-logical-ID reuse | run the exact second planner boundary with direct exception capture | confirmed secondary defect: equal logical predecessor/successor coordinates were treated as mutations and required a synthetic after-record |
| H3 | whole JSONL difference is the intended durable schema/control-record change from commit-time materialization | canonical-decode expected/actual records and produce record/field diff | confirmed after deterministic clock correction; public wire/member identities remain unchanged and only the authorized whole-file pin changes |
| H4 | whole JSONL contains an unintended nondeterministic or duplicate record despite stable public members | repeat isolated generation twice and compare bytes/record identities | rejected after final manifest correction: two clean outputs compared byte-identical at SHA-256 `fdc79b62bf0d29be05e7cd8dad7d0860b93095d110ad58930f9a4f95b6b32bbc` |

## Scope

Included: sequential rekey planner/publication/persistence/replay, frozen public
JSONL record identity and checksum authority, exact sibling tests and artifacts.
Excluded: CI topology/timings, unrelated product behavior, and weakening frozen
or writer validation.

## Delegation And Cost Ledger

| Phase | Task | Role/tier | Ownership | Status |
| ----- | ---- | --------- | --------- | ------ |
| reproduce | expose exact second-rekey and JSONL byte-diff signatures | Spark explorers/error detective | read-only | complete |
| fix | apply root-cause product correction and/or authorized golden refresh | worker, Terra-class | sole writer | complete |
| review | targeted spec/correctness/test closure | Terra-class reviewers | read-only | complete: no required findings |

## Next Action

Return the completed debug evidence to the parent M4 implementation WorkPlan
and resume its next incomplete milestone action.

## Blockers And Limits

Budget: three discriminating experiments, one fix/refresh batch, one targeted
remediation round. No external blocker.

## Outcome And Retrospective

The deterministic clock defect was in reference-integrity advancement: it
sampled the process wall clock after the atomic store had already selected the
transaction timestamp. Bootstrap and advancement now use the store's single
injected timestamp for the certificate and ledger record. A mutable-clock test
binds both values explicitly.

The sequential-rekey defect had two layers. Embedded predecessor/successor
coordinates in an `identity_lineage` record are historical facts, so all four
physical/logical manifest paths now use `immutable_revision`. Generic
reprojection now ignores a provable equal predecessor/successor coordinate,
and frozen-plan completeness makes the same narrow exemption while retaining
the output requirement for every actual mutable change.

The required populated merge/split proof exposed three additional members of
the same defect family. Claim-assertion coordinates explicitly named `at_recording`
are immutable under the governing design and can never be rewritten as current
logical projections. Successor completeness must count only created entity
revisions, not legitimate updates to an existing entity revision's mutable
logical projection. Finally, exact closure equality belongs at each transition's
pre-batch state: final materialized state cannot reconstruct an overwritten
record version. Genesis replay, checkpoint-tail replay, and file append/reopen
now validate the exact closure before applying each lineage batch; the final
lineage view retains chain, cycle, disposition, and still-visible-reference
checks without requiring unavailable overwritten versions.

Focused evidence: four original regressions passed in 81.16 seconds; the
successful populated rekey-to-merge and rekey-to-split JSONL reopen cases pass
in 189.97 seconds; missing, extra, and substituted historical closure batches
are rejected across genesis, signed checkpoint-tail, and raw JSONL reopen in
6.72 seconds. The broader first sibling round passed 39 tests in 352.48
seconds. After the final manifest correction, two clean frozen generations
again compared byte-for-byte identical at SHA-256
`fdc79b62bf0d29be05e7cd8dad7d0860b93095d110ad58930f9a4f95b6b32bbc`;
all existing wire and member pins remained unchanged. Only the authorized
whole-file SHA pin was refreshed. The final combined focused run passed 37
tests in 366.13 seconds. Ruff, Pyright (zero errors/warnings/informations), and
`git diff --check` pass. Independent delta remediation review reported no
required runtime findings. A final test review identified one
`Not applicable`/`changes_required` verification gap: fresh-run determinism was
proved by separate commands rather than by the frozen test itself. The public
frozen node now executes the identical flow against two independent empty
JSONL roots, asserts complete bytes and SHA equality before frozen pins, then
asserts exact wire bytes and the full generation-member map equal before their
frozen pins, and finally proves reopen makes no change. Two independent
invocations of this strengthened node passed in 55.36 and 58.29 seconds. Ruff,
Pyright, and `git diff --check` remain clean. The debugging completion contract
is satisfied.
