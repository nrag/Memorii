# Monitor Validation Matrix

Scope: pre-coding validation design for the paused monitor/registry package.
This is not implementation evidence or a package approval.  It uses the shared
production-entrypoint map and `monitor-readiness.md`; it does not infer a new
owner, scheduler API, persisted schema, policy value, or recovery workflow.

## Current Evidence And Boundary

The active index records `R08`, `R15`, `R16`, and `R19` as `unmapped` in
`production_entrypoint_bindings.json`.  `CapabilityRegistrySnapshot` currently
names only a capability ID and fingerprint.  Its existing unit contract test
proves canonical snapshot bytes, not certified status, freshness, a scheduler,
or a shared status-record CAS.  `SemanticAuthorizationReadSet` and the source
authorization tests prove a different authority chain.  They cannot be reused
as proof of per-capability demotion.

Consequently no existing test is behavioral proof for this slice.  The future
binding ledger must identify the actual non-test monitor trigger, the exact
registry/status owner, the authority passed into monitor evaluation and commit,
and the normal provider/ingest caller that consumes the active status revision.
Each integration case below must start at that registered production trigger,
use its real persistence/CAS adapter through the external boundary, and observe
the persisted decision and subsequent ingest outcome.  A direct model, codec,
repository, fixture, helper, or statistic test may supplement that proof only.

Required mutation signals for every registered caller are: (1) remove the
caller, (2) omit the status authority/revision argument, and (3) replace the
normal-path status check with a success-shaped fallback.  The behavioral test
must fail in each mutation.  This prevents a passing test that only exercises a
standalone monitor or a mock bypass.

## Required Deterministic Matrix

All time in these cases comes from an injected server clock owned by the real
scheduler/control composition.  No case reads wall time, sleeps, uses a random
ID, or relies on task ordering.  Policies and event-level fixtures are explicit
test inputs; this matrix deliberately supplies no substantive threshold or
duration defaults.

| Contract and requirement | Production-trigger behavioral scenario | Required assertions and failure signal | Supplemental proof only |
| --- | --- | --- | --- |
| Missing approval inputs fail closed (`R08`, `R15`, `R16`, `R19`) | Invoke the registered scheduled monitor trigger with a capability whose policy, declared gate, eligible observation, or sequential manifest is respectively absent, mismatched, or unapproved; then invoke the normal provider ingestion trigger. | One persisted decision has `action=evidence_only` and the applicable reason; active status is not retained; normal ingestion retains governed evidence and creates no semantic promotion or legacy/remote fallback.  Removing the caller or status authority must make this integration assertion fail. | Strict typed decoding and digest/domain mismatch vectors for policy, gate, observation, manifest, and registry records. |
| Immutable single-window evaluation (`R15`) | Feed the trigger one event-level window spanning multiple declared metrics and attempt mutation/substitution of the window after the first gate is evaluated. | Every metric decision, decision digest, and action derives from the same immutable evidence-window digest.  A substituted/mixed window or unknown metric is `evidence_only`; no partial result retains active status. | Unit recomputation of digest canonicalization and gate enumeration. |
| Independent cluster accounting (`R15`) | Use event-level fixtures containing repeated paraphrases in one source/template family, a duplicate cluster, and a cluster assigned to two metrics; execute through the monitor trigger. | Independent count reflects unique eligible clusters only; duplicate/multiply assigned clusters are rejected/fail closed rather than counted twice; the persisted decision cannot report healthy solely because duplication enlarged the sample. | Independent fixture-side cluster reconstruction that imports no monitor clustering/reduction helper. |
| Sequential bound and alpha integrity (`R15`) | Execute the real trigger with fixture event values whose independently recomputed bounded, time-uniform result is healthy, warning, and unsafe, plus non-finite statistic, implementation-fingerprint mismatch, and gate alpha total over the family budget. | Valid unsafe-bound crossing demotes; warning alone records alert behavior while status remains active; invalid/non-finite/fingerprint/alpha inputs demote.  Assertions compare persisted estimate/bounds/alpha spent/status to an independent fixture oracle, never to monitor-returned expected values. | Deterministic numerical vectors for the approved sequential implementation.  They do not establish that a statistical policy or its substantive alpha/threshold values are externally approved. |
| Label/canary deadline boundaries (`R15`) | Advance the server clock to exactly before, exactly at, and exactly after each maximum label age and maximum canary-success age, through scheduled ticks without new ingest. Include healthy canaries with stale labels. | At every declared inclusive/exclusive boundary the persisted freshness/action is deterministic.  Fresh canaries never extend a label deadline; stale labels demote even with passing canaries.  Delete the tick caller and the post-boundary observation must be absent, proving zero-traffic scheduling rather than ingest-driven evaluation. | Unit boundary classification for a supplied timestamp and evidence set. |
| Minimum window and zero traffic (`R15`, `R19`) | Start active with a valid prior status, stop all ingestion, and fire scheduled ticks across the label-age and minimum-labeled-cluster conditions. | The scheduler persists freshness during quiet time; low volume/zero traffic cannot leave the status active indefinitely.  On expiry, the next normal provider ingestion sees `evidence_only`, retains governed evidence, and has zero semantic promotion/fallback. | Fixture construction for an empty event stream. |
| Paused traffic grace (`R15`) | Set the externally supplied traffic state to paused and advance across its separately supplied grace boundary, both with no new labels and with canaries succeeding. | Pause neither resets label age nor manufactures clusters.  Status may follow the stated policy only until grace expiry, then atomically demotes.  A status that becomes fresh merely because traffic is paused fails. | Unit freshness state classifier for supplied states. |
| Label-pipeline outage grace (`R15`) | Set label pipeline state to outage while traffic, labels, agreement, and canaries otherwise look healthy; tick before and after its separate grace limit. | An operational incident is emitted/recorded at outage observation; only the policy-defined bounded grace can retain activity; expiry demotes.  Traffic/canary health cannot suppress the expiry action. | Incident record schema and pure freshness classifier tests. |
| Delayed-label recovery requires activation (`R15`, `R19`) | Demote on stale evidence, then supply delayed fresh independent labels that satisfy the same supplied policy and fire a further scheduled tick; exercise normal provider ingestion before and after explicit activation. | Monitor records fresh evidence but does not change `evidence_only` back to active.  Ingest remains evidence-only until a separately authorized explicit activation action succeeds.  Removing the explicit activation authority or replacing it with monitor auto-activation must fail the case. | Direct state-machine rejection vector for `evidence_only -> active` absent an activation authorization. |
| Atomic active-to-evidence-only transition (`R15`, `R19`) | Begin a real normal ingestion/commit under a captured active status revision; interleave the real scheduled demotion immediately before that commit CAS resolves. | Demotion changes the shared status record and decision atomically.  The in-flight run whose read set names the prior revision/digest fails deterministic revalidation and cannot commit semantic promotion after demotion; retry behavior, if any, rereads status and ends evidence-only rather than committing under the stale revision.  The final store contains no split-brain active status/committed post-demotion run. | Unit construction/validation of the status binding and deterministic interleaving harness. |
| Commit does not bypass status authority (`R08`, `R19`) | Parameterize each normal production composition root registered in the binding ledger (including provider/service path and supported host builder) and invoke a governed source after a demotion. | Every path carries the same shared status revision/digest to the commit owner and yields the same evidence-only/no-promotion outcome.  Stripping the binding or supplying an old revision must reject, never synthesize an active/default/legacy outcome. | Constructor/contract tests for each adapter’s required parameter shape. |
| Persist/reload and compatibility (`R15`, `R16`, `R19`) | Persist a decision/freshness/status sequence including demotion, restart/reload the real store/composition, then invoke tick and ingest.  Also load an existing V2 capability-registry snapshot fixture. | Reload preserves the exact status revision/digest and remains evidence-only; no constructor migration silently treats the old ID/fingerprint-only V2 snapshot as a certified active status.  Unknown/legacy/mixed record forms fail closed and leave the verified pointer/status unchanged. | Codec round trips and read-only legacy diagnostic fixtures. |
| Demotion retry/idempotence (`R15`) | Deliver the same due scheduled evaluation twice and inject one CAS loss using the real status-owner conflict mechanism. | At most one successor status revision/decision is published for the same evidence window; a retried operation either recognizes the byte-identical winner or reevaluates from current authority.  It never creates two demotions, skips a stale check, or reactivates. | Repository-level CAS conflict test, provided it is paired with this trigger-to-store proof. |

## Proof Placement And Gate Shape

One deterministic integration suite should own the trigger-to-store cases,
real fake-clock scheduling, provider/ingest composition, restart, and controlled
CAS interleaving.  A second independent fixture-oracle suite may own event-level
cluster and sequential-bound recomputation.  It must not import the production
monitor implementation, its reduction helper, serializer, or transaction owner.
Contract/codec tests remain narrow supplements.  This separates runnable
deterministic correctness from external statistical policy acceptance.

The implementation packet must add one entry per affected requirement to
`production_entrypoint_bindings.json` before calling any result evidence.  Each
entry must name the concrete monitor caller and normal ingest caller, canonical
status owner, supplied authority, and the exact behavioral test selector.  The
same selector must demonstrate all three mutation signals above.  Dedicated
slow/exhaustive permutations (all deadline edges, duplicate-cluster forms, and
restart/CAS schedules) need a single named CI owner and budget; the fast gate
keeps one representative stale-label, zero-traffic, and concurrent-demotion
case.  No timing, shard, or job is assigned here because current workflow and
runtime measurement evidence were outside this pre-coding consultation.

## Policy And Readiness Boundaries

Deterministic fake-policy fixtures may prove the implementation obeys supplied
values.  They cannot approve actual thresholds, grace durations, alpha budgets,
minimum sample sizes, the sequential spending rule, a capability baseline, a
dependency bundle, root-cause review, held-out recertification, or explicit
activation authority.  Those are external/statistical-policy decisions under
SIA-ED-POLICY-001 and remain separate evidence.

The concrete status-record schema, current V2 snapshot reconciliation, exact
monitor scheduler/control entrypoint, explicit-activation authority, canonical
transaction owner, and final production-entrypoint binding are deliberately
unresolved.  They are implementation/readiness inputs, not test defaults.
This matrix proves the bounded future monitor/registry slice only; it does not
establish Package 4 or the parent engineering-closure milestone as complete.
