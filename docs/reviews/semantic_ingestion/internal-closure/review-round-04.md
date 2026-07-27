# Design Review: Semantic Ingestion Internal Closure, Round 04

## Review Metadata

- Review ID: `semantic-ingestion-internal-closure-round-04`
- Review mode: `full`
- Review outcome: `Not approved; revision budget exhausted`
- Design baseline SHA-256:
  `4c8884214e73b580aa4f9ae0ee21cf62a4bc1b1e284121c6560dd063c1b29f19`
- Design size: 14,497 lines
- Implementation baseline:
  `44cd7773a75ac8545ddcf799c76dc94c0240f788`
- Reviewers: fresh independent `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer`, followed by coordinator validation

## Executive Assessment

The spec auditor and test reviewer independently approved the complete target
design with no internal finding. The correctness reviewer found one concrete
P2 integration-contract contradiction. The coordinator reproduced it directly.

The design is not internally approved. Three of three permitted revisions have
been consumed, so this operation stops without modifying the frozen baseline.
No P1 finding remains. One P2 finding and the three registered external
decisions remain.

## Unresolved Internal Finding

### SIC-011: Result-access prose invokes the authorizer with the wrong request type

- Product priority: `P2`
- Approval disposition: `changes_required`
- Finding type: security and integration contract
- Requirement: SIA-R22
- Evidence: `DeliveryAuthorizationRequest` contains one `requested_scope` and
  permits `purpose="result_access"`; `SemanticIngestionOutcomeAuthorizer`
  accepts `SemanticIngestionOutcomeLookupRequest`; result-access prose then
  directs the service to call the authorizer with a
  `DeliveryAuthorizationRequest(purpose="result_access")`.
- Violated invariant: the result authorizer must consume the opaque lookup
  request and derive the complete required-scope set only from the protected
  admission authorization index before any result or artifact lookup.
- Failure scenario: an implementation follows the prose and constructs the
  scalar-scope delivery request. It must invent an adapter to the declared
  protocol or authorize only one scope of a mixed-scope outcome.
- Prevalence: mixed-scope governed snapshots are important supported lifecycle
  cases, not the dominant single-turn path.
- Root cause: the admission/recovery authorization DTO was left in the
  result-access prose after result access moved to its own opaque, all-scope
  protocol.
- Exact architectural correction required:
  1. Remove `"result_access"` from `DeliveryAuthorizationRequest.purpose` so
     that type is admission/recovery only.
  2. State that the service calls
     `SemanticIngestionOutcomeAuthorizer.authorize(context,
     SemanticIngestionOutcomeLookupRequest, server_time)` directly.
  3. State that the authorizer derives `RequiredOutcomeScopeSet` exclusively
     from `AdmissionAuthorizationIndexEntry`; neither request type carries a
     caller-selected scope or scope set.
  4. Add a static contract check that result access never constructs or imports
     `DeliveryAuthorizationRequest`, while admission/recovery never consumes
     `SemanticIngestionOutcomeLookupRequest`.
  5. Retain the existing two-scope behavior test: A-only authorization is
     non-disclosing with zero result/artifact reads; A+B authorization succeeds.
- Independent completion evidence: fresh whole-design review of a new exact
  baseline plus static request-type ownership and mixed-scope repository-spy
  acceptance tests.

## Rejected Findings

* Absence of the proposed implementation and executed implementation evidence
  remains future conformance work, not a target-design defect.
* No additional text-coordinate, segment-language, traceability, codec,
  retrieval/query, agent-integration, or provider-migration finding was
  validated.

## External Blockers

The following remain unchanged with `Not applicable` product priority and
`blocks_approval` disposition:

* `SIA-ED-TOPOLOGY-001`
* `SIA-ED-REPLAY-001`
* `SIA-ED-POLICY-001`

## Final Outcome

**NOT APPROVED.** The workflow exhausted three permitted revisions with one
internal P2 contract contradiction remaining. A new explicitly authorized
revision operation is required to apply SIC-011 and run a fresh complete review.
