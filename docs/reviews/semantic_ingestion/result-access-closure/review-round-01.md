# Design Review: Semantic Ingestion Result-Access Closure, Round 01

## Review Metadata

- Review ID: `semantic-ingestion-result-access-closure-round-01`
- Review mode: `full`
- Review outcome: `Changes required; external decisions remain blocked`
- Design baseline SHA-256:
  `4c8884214e73b580aa4f9ae0ee21cf62a4bc1b1e284121c6560dd063c1b29f19`
- Design size: 14,497 lines
- Implementation baseline:
  `44cd7773a75ac8545ddcf799c76dc94c0240f788`
- Reviewers: fresh independent `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer`, followed by coordinator reproduction and validation

## Executive Assessment

The spec auditor found no internal gap. The correctness and verification
reviewers independently confirmed the result-access request-type contradiction.
The correctness reviewer also exposed a directly related scope-superset
contradiction, which the coordinator reproduced from the durable identity and
authorization schemas.

The frozen internal inventory is two P2 findings and no P1 finding. Both are
important mixed-scope/recovery and authorization cases; the ordinary
single-scope turn remains representable. The three registered external
decisions remain separate and unchanged.

## Confirmed Internal Findings

### RAC-001: Result access invokes the authorizer with an incompatible request type

- Product priority: `P2`
- Approval disposition: `changes_required`
- Finding type: security and integration contract
- Requirements: SIA-R01, SIA-R04, SIA-R22, and SIA-R23
- Evidence: `SemanticIngestionOutcomeAuthorizer.authorize` accepts
  `SemanticIngestionOutcomeLookupRequest`, whose purpose is
  `semantic_ingestion_outcome_lookup`. The execution prose instead directs the
  service to call that protocol with
  `DeliveryAuthorizationRequest(purpose="result_access")`. The latter has one
  requested scope and no opaque operation/delivery references.
- Violated invariant: result access must have one typed, purpose-bound request
  whose opaque references resolve through the protected admission index before
  any result/artifact read; no caller-selected scope may authorize lookup.
- Failure scenario: an implementation must invent an adapter between
  incompatible schemas or reuse a scalar-scope admission DTO, allowing only one
  represented scope to control a complete mixed-scope outcome.
- Prevalence: complete mixed-scope lifecycle outcomes are important supported
  cases, while ordinary single-scope turns remain unaffected.
- Root cause: the admission/recovery authorization request remained in
  result-access prose after result access gained its own opaque protocol.
- Smallest complete correction: make
  `SemanticIngestionOutcomeLookupRequest` the sole service/authorizer request;
  remove `result_access` from `DeliveryAuthorizationRequest`; derive required
  scopes only from the protected index; prohibit overloads, aliases, alternate
  lookup routes, and caller-supplied scopes.
- Independent verification: static ownership/import checks prove result access
  never constructs or consumes `DeliveryAuthorizationRequest`; a two-scope
  repository-spy test proves partial authorization returns the same unavailable
  response as a guessed reference with only the protected-index read, while
  complete authorization permits result reads.

### RAC-002: Durable delivery identity conflicts with authorized scope supersets

- Product priority: `P2`
- Approval disposition: `changes_required`
- Finding type: durable identity and authorization semantics
- Requirements: SIA-R01, SIA-R22, and SIA-R23
- Evidence: `DeliveryPrincipalBinding` includes
  `authorized_delivery_scope_set_digest`, and that binding contributes to
  `delivery_key_digest`. Result access promises that a fresh current authorized
  scope superset may access an admitted required-scope subset while also
  requiring the freshly resolved binding and delivery key to equal admission.
  A strict superset changes the scope-set digest and therefore cannot satisfy
  equality. `AuthenticatedIngressContext` exposes only a scope-set digest, not
  the trusted typed set needed for subset authorization.
- Violated invariant: durable delivery identity must remain stable across
  ordinary session/policy scope expansion or contraction, while each operation
  independently authorizes its persisted required scopes against the current
  trusted scope set.
- Failure scenario: source `{A}` is admitted, then the same principal/tenant
  receives current authorization `{A,B}`. Required behavior says lookup may
  succeed, but binding/key equality rejects it because the scope-set digest
  changed.
- Prevalence: scope renewal, expansion, contraction, and composite outcomes are
  important authorization/recovery cases; one unchanged session remains valid.
- Root cause: mutable authorization membership is embedded in durable principal
  identity, while only its digest is exposed for current authorization.
- Smallest complete correction: derive durable `DeliveryPrincipalBinding` only
  from stable provider, principal, and tenant authority; represent the current
  authorized scope set as one typed, canonical, trusted set in
  `AuthenticatedIngressContext` and bind its digest into session authorization
  evidence rather than durable identity. Persist admission-required scopes in
  the protected index. Admission/recovery validates its server-derived or
  persisted required scopes; result access performs
  `required_scopes subset_of current_authorized_scopes` before any result or
  artifact repository read. Requests contain no caller-selected scope set.
- Independent verification: exact, strict-superset, partial, zero, stale,
  expired, revoked, and cross-tenant scope cases; identity stability across
  current-set changes; current-set/session-evidence substitution; and repository
  spies proving denied cases read no result/artifact repository.

## Rejected Findings

* Absence of the proposed target implementation and executed evidence is future
  conformance work, not a target-design defect.
* No additional codec, traceability, text-coordinate, language-routing,
  retrieval/query, agent-integration, or provider-migration finding was
  validated.

## External Blockers

The following remain unchanged with `Not applicable` product priority and
`blocks_approval` disposition:

* `SIA-ED-TOPOLOGY-001`
* `SIA-ED-REPLAY-001`
* `SIA-ED-POLICY-001`

## Round Outcome

**Changes required.** Revision scope is frozen to RAC-001 and RAC-002. One
design writer may make the smallest complete corrections. The exact revised
baseline must then receive a fresh full review by new reviewer instances.
