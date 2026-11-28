# Verify a recurring transcript coverage gap

- Order: 3. Status: queued. Baseline: `80fc5852`; design and candidate head pending.
- Requirements: partial OLE-01/02/07/08/11/12/14.
- Dependencies: learned review and recovery, approved capability binding and attribution design.

## Execution boundary

Route Hermes retention and generic authenticated source intake through the
existing provider observation path. Extend the `OntologyObserverCapability`
binding and reuse the durable `CoverageObserverRunner` and recurrence CAS
repository. Freeze one host-supplied or local binding, exact version and
egress policy, evidence attribution, status shape and second-relation
witness. The adapter admits authorized sources. Core verifies spans, identity,
lineage, scope, alias coverage and whether the problem is catalog coverage.
Carry forward the existing pending and attempt recovery contract. Binding
changes must preserve earlier observation history; disabling the binding
leaves the packaged workflow usable and eligible observations pending.

## Acceptance and verification

- Two actual adapters feed one scoped group. Three independent lineages
  across two sessions qualify the gap. Repeated delivery, verified copies,
  alias hits, quoted/untrusted text, ambiguous roles, extraction failure,
  protected recall miss and agent exposure failure do not inflate counts.
- Authorized scoped status shows accepted evidence count, exclusion reasons
  and pending/unavailable state without exposing an unrelated source.
  Check duplicate and rejection suppression. Retry and reopen preserve
  evidence counts. No key, remote fallback or speculative committed facts.
- Verify capability authorization and outage/recovery through an installed
  local or host binding. Scripted classifier outputs establish plumbing.
  Record manual capability behavior separately. Candidate creation and
  independent withheld evaluation follow in the next packet.

```sh
python -W error -m pytest -q -p no:cacheprovider \
  tests/unit/core/semantic_ingestion/test_coverage_observation.py \
  tests/unit/core/semantic_ingestion/test_coverage_observer.py \
  tests/unit/core/semantic_ingestion/test_coverage_recurrence.py \
  tests/unit/integrations/test_hermes_memory_provider_bridge.py
```

Close with durable group and binding proof, applicable gates and focused
review of attribution, scope and ordinary failure handling.
