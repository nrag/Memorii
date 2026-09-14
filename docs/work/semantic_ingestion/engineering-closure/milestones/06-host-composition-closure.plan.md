# Package 6: Host Composition And Whole-Program Closure

- Parent WorkPlan: `docs/work/semantic_ingestion/engineering-closure/implementation.plan.md`
- Delivery fidelity: Level 2 - early real-world testing
- Status: complete at Level 2; Level 3 release work deferred
- Requirements: R01-R23

Wire and prove the real Hermes root across intended happy scenarios and common
operational failures for early testing. Exhaustive root/tamper matrices and
final exact-candidate gates are Level 3 follow-up.

## Completion State

No Level 2 work remains. The bounded correction review approved the configured
Hermes startup root at production revision `4497325b`.

## Level 2 Candidate

Hermes now reaches ingestion, retrieval, observation, ingestion-time
attestation, activation, monitoring, and reconciliation through the public
provider service. The consolidated 36-scenario pass covers intended happy
scenarios and common configuration, caller/scope, provider/extractor,
partial/retry, restart, stale-cursor, duplicate, and no-work behavior. Exact
commands and results are recorded in the parent WorkPlan.

The first targeted review found that the concrete host had no lifecycle trigger.
The corrected Hermes startup hook now performs configured activation followed
by recovery and bounded monitoring. The explicit configured builder cannot
return a provider before that sequence succeeds. Fast ordering checks pass, and
the real configured Hermes observation/comparator flow uses this builder and
passes in 329.64s.

Final package breadth, production evidence assembly, exhaustive host and tamper
matrices, operational key provisioning, qualifying measurements, and release
signatures remain Level 3 work.
