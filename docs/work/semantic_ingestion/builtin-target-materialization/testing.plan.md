# Built-In Target Materialization Verification

- Work ID: builtin_target_materialization_verification
- Work type: testing
- Status: active
- Coordinator: Codex main thread
- Created: 2026-09-04
- Last updated: 2026-09-05
- Parent WorkPlan: `docs/work/semantic_ingestion/builtin-target-materialization/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/bootstrap-v3-source-progress-bridge-2026-09-04/implementation.plan.md`
- Canonical inputs: the parent implementation WorkPlan; `docs/design/semantic_ingestion_architecture.md` Sections 4.8.2.17 through 4.8.2.20; current CI workflows and transaction selector manifests
- Expected outputs: non-fixture proof for supported accepted facts, failure families, contention, exact recovery, public roots, and gate ownership

## Objective

Prove that a supported entity-object fact is accepted only through the genuine
built-in production planner and atomic graph transaction, while incomplete or
substituted authority remains effect-free, and that an ordinary competing
ingestion activates the typed original-fence successor.

## Completion Contract

Complete only when every parent requirement has a distinct failure signal at
the strongest practical level; test authority cannot manufacture accepted
materialization; direct/factory/filesystem/Hermes memory and JSONL paths are
covered without private scenario composition; restart and lost-ack recovery
reuse exact bytes; tests have measured runtime and one CI owner; relevant
selector, timing, workflow, and identity-hygiene artifacts are current; and
independent test/correctness review has no remaining approval finding.

## Scope

Included: focused pure planner/reducer contract tests, adversarial authority
mutations, production-root integration, real two-ingestion scheduling at the
atomic boundary, independent JSONL reopen, exact graph-effect inspection,
selector/gate/timing ownership.

Excluded: tests for unsupported correction, retraction, action-state, or
identity-operation acceptance beyond confirming they remain effect-free;
benchmarks, live providers, broad unrelated unit-suite reorganization.

Deferred: exhaustive testing for other accepted operation arms.

## Constraints And Invariants

- No scenario host, injected graph authority provider, fabricated accepted
  materialization, fake store, or direct graph-state seeding may satisfy a
  production acceptance claim.
- Concurrency uses deterministic events around the real group CAS, never sleeps.
- The oracle inspects accepted terminal/effect records and graph revision, not
  the existence of a group primary record alone.
- Reopen occurs through a fresh service/process over the same durable store.
- Existing failure families and required selector rows may not be weakened.

## Identity And Coordinate Hygiene

| Surface | Identity | Class | Owner/meaning | Disposition | Proof |
| --- | --- | --- | --- | --- | --- |
| new test/helper names | derived from accepted fact or real related conflict behavior | behavioral | executable invariant | add | identity-hygiene mutation gate |
| WorkPlan ID | value in this file only | planning/evidence coordinate | testing operation | retain here only | repository search |

## Change Impact And Verification Closure

| Test level | Behavior | Defect detected | Failure signal | Expected gate | Status |
| --- | --- | --- | --- | --- | --- |
| pure unit | exact target/record/seed/reducer construction | fabricated or cross-request authority | typed rejection or byte mismatch | unit shard | mapping |
| mutation | missing/duplicate/substituted cluster, target, record, provenance, read set | fail-open accepted effect | unresolved/rejection and zero effects | unit shard | mapping |
| integration | each public root uses exact production host | scenario authority alias | exact host type and accepted durable records | transaction boundary | failing baseline |
| contention | B advances graph revision while A is paused | unreachable or unbounded successor | 2 admissions, 3 CAS, 9 progress, 2 accepted commits | transaction boundary | failing baseline |
| recovery | fresh process returns exact terminal/progress and does no work | replay/replan duplication | zero CAS/effects/lanes; exact bytes | dedicated JSONL gate | mapping |

## Delegation And Cost Ledger

| Task | Role | Ownership | Rationale | Status |
| --- | --- | --- | --- | --- |
| pre-implementation matrix review | `test_reviewer` | read-only | validate oracle and gate placement before code | complete |
| test implementation | parent implementation `worker` | sole writer | keep behavior and proof coherent | active |
| final test/correctness review | standard reviewers | read-only | closure requirement | pending |

## Verification Dependency

The persisted normalization authority currently lacks the v75 typed
construction input, but the approved design assigns the normalization owner to
seal the concrete existing sources. Tests must prove that the production path,
not transient invocation objects, scenario authority, a generic compiler, or
fabricated planning fields, constructs accepted materialization.

## Prior Next Action (Completed)

After the parent implementation persists the exact v75 inputs, add the
pure/unit, production-root contention, and independent-JSONL rows described
here.

## Resolved Schema Blocker Evidence

- The native target request now joins its effective `GraphReadSet` to the
  canonical graph read set inside the sealed snapshot, rather than to the
  transaction read-set token; a foreign canonical read set must reject.
- The authorized schema completion now carries `PredicateStateRule` and full
  `SourceAuthorityEvidence` and constructs a non-null `AcceptedClaimIdentity`.
  This removes the prior authority blocker without extending non-fact arms.

## Race Evidence

- The earlier two-ingestion vector used byte-identical graph writes. Under the
  corrected target-level CAS contract those writes rebase without a related
  conflict; global graph revision alone is not a stale-winner signal.
- The corrected identical-write race passes with two CAS attempts, two
  admissions, two group primaries, two accepted graph effects, and six normal
  progress checkpoints. The dedicated typed related-conflict pair passes 2
  tests in 127.84s and remains the original-fence successor proof.
- The one-group fixture injects the canonical typed
  `BootstrapGraphRelatedConflictError`, not generic storage failure; its direct
  root successor test passes. The former multi-group direct-root oracle has
  been reclassified as effect-free for the bounded fact-only source shape; its
  real partial-group retention proof remains pending focused test review and is
  not claimed by this slice.

## Exact Next Action

Obtain a focused test-review disposition for the pending multi-group retention
proof without changing the accepted-fact race oracle or expanding into deferred
conflict-attention/replay work.

## Current Evidence

- The authorized typed planning closure is present, record construction and
  coordinator execution no longer throw, but the coordinator returns a
  non-success group result which the provider collapses to
  `graph_transaction_authority_unavailable`. It is not an accepted-effect
  oracle and does not satisfy any proof row.

## Prior Safe-State Verification

- The direct built-in production-root regression is closed: the incomplete
  planning authority is withheld rather than serialized through the durable
  unresolved plan, so strict graph checkpoint reload does not fail on partial
  governance carrier decoding.
- Focused direct-root proof passed with its original `source_only` unresolved
  terminal. Grammar and source-normalization authority checks passed (6
  tests); changed production modules passed Ruff and `py_compile`.

## Pre-Implementation Review

- Scope disposition: fact-only is a valid bounded bridge prerequisite, but it
  cannot close the ordinary planner or parent M3.1 contract. Non-fact arms must
  retain typed effect-free failure.
- Pure plan proof must assert exact subject/object target roles, lawful new
  first-use entity seeds, entity/claim/projection/relation/evidence records,
  canonical state fold, and deterministic bytes using an independent oracle.
- Reducer/store proof must inspect accepted terminals, intent/record bijection,
  durable graph record kinds and shared graph revision. A group primary record
  is not an accepted-effect oracle because unresolved operations also write it.
- Negative proof must cover missing/ambiguous/cross-request targets, authority,
  read-set, state, precondition, codec, predicate, temporal, coverage and
  evidence substitutions with zero partial effects.
- Recovery proof must cover memory and independent JSONL exact reload, lost
  acknowledgement, lease reclaim and persisted member corruption without
  replanning after an unknown acknowledgement.
- Contention proof must use only the real production host and public roots,
  pausing at the real atomic group CAS. The expected observable is two
  admissions, three CAS attempts, two accepted commits, nine progress members,
  original-fence reuse and zero reopen work.
- Gate finding: the transaction selector's related-conflict oracle still says
  one CAS/one effect while the binding requires three/two/two. Update and
  regenerate it only after production accepted materialization exists.
