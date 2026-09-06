# Bootstrap graph JSONL trust-domain mismatch

## Objective

Restore the independent-process bootstrap graph selector family after the
private scenario-test host began correctly rejecting a production-domain
capability in the `coordinator_removed` scenario.

## Parent

This debugging operation is linked from the active M3.1 implementation gate in
`docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/implementation.plan.md`.

## Expected and observed behavior

- Expected: every JSONL selector enters through the private scenario-test host,
  exercises its declared graph scenario, and writes a revision-bound receipt.
- Observed: `coordinator_removed` exits before graph coordination because
  `_resolve_ingress` returns `None`.
- Classification: test-fixture trust-domain mismatch; production isolation is
  behaving correctly.

## Hypotheses and experiment

1. The JSONL store/reopen path rejects the ingress. Prediction: the failure
   persists with matching scenario-test authority.
2. The runner supplies a production capability to a scenario-test host only
   when the graph coordinator is removed. Prediction: using the same
   scenario-test capability as every sibling reaches the declared graph path.

The single-scenario reproducer showed the rejection occurs on the first process
before any reopen or graph assertion. Static comparison with the passing memory
sibling confirmed the JSONL-only cross-domain construction.

## Root cause

The runner always calls `ProviderMemoryService._from_scenario_test_host`, but
conditioned `host_bootstrap_capability` on `coordinator_removed`. That one branch
therefore paired a production-domain capability with a scenario-test host.
Trust-domain validation rejected ingress before the scenario could prove graph
coordinator absence.

## Correction and evidence

Use a scenario-test capability for every private scenario-test runner branch.
Do not weaken production trust validation or add a compatibility fallback.

Evidence:

- Before correction, the exact direct JSONL `coordinator_removed` selector
  failed first at ingress rejection, then (after aligning the trust domain)
  returned `source_only` because omission selected the production built-in.
- The explicit removed-coordinator scenario fixture passes the exact first and
  reopen selector: `1 passed in 114.31s`.
- Production trust validation and built-in default composition are unchanged.

Next action: run the complete four-root JSONL manifest family and aggregate
receipt validator as part of the parent implementation gate.
