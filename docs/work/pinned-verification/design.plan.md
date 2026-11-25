# Pinned Verification Feasibility

- Work type: design
- Delivery fidelity: Level 2 experiment for the Level 3 capacity gate
- Baseline: `a5f2e623`, `codex/durable-delivery-implementation`
- Related: [reference capacity debugging](../reference-capacity-debugging/debugging.plan.md)
- Status: experimenting

## Objective And Scope

Measure how long a prewarmed managed command waits when a separate service acquires a held-out exact qualification tuple. Compare the normal production acquisition with a test-only pinned acquisition on independent copies of both retained v8 fixtures. Preserve v7 default, schemas, production release authority, recovery, and release budgets.

## Contract And Feasibility

Pin a read-only SQLite WAL view under the publication fence and establish its snapshot by reading the exact signed publication row. Capture the operational control state, finalized tuple, journal tip, signer fingerprint and participant file identities. A separate, autocommit observer detects same-head SQLite commits with its own connection-local cookie. Take its identity and version before pinning. Under the release fence, reread the authority and live row, compare the same observer's cookie, and require exact equality before returning the snapshot. Underlying participant locks follow the existing publication-fence then partition order. Pinning and revalidation perform metadata checks. Existing exact raw, catalog and replay verification runs outside both advisory locks on the pinned view.

A stale attempt drops its WAL pins and retries at most three times. An exact-current verification failure or exhausted attempts refuses release. This prototype uses synthetic copies and returns the snapshot at acquisition only. It does not seed the production cache, service normal command/read entry points, perform recovery, or quarantine. Production adoption would require cache transfer on the receiving connection, live-op authority checks, erasure coordination, bounded pin lifetime and WAL growth, and an explicit policy for repeated competing publications. Releasing an old tuple to avoid retries would violate the current contract.

Compare real managed writer wall time, exclusive fence wait/hold, acquisition wall time, stale work, and release outcome. Start the writer at the reader's full verification entry and wait there until the writer reaches its first exclusive-lock attempt in both arms. Require the writer commits and a distinct new signed head is visible. The prototype must discard that stale pin and acquire the writer's tuple on retry. The baseline may verify the previous head because it linearizes acquisition before the writer. Also test successful release without a writer, current preserved-head corruption refusal, and bounded invalidation. These are controlled overlap diagnostics rather than sustained-contention qualification.

## Next Action

Run the test-only pinned verifier and baseline against the signed retained macOS fixture copies.
