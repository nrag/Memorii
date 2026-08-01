# Design Review: Source-Grounded Semantic Ingestion Architecture

## Review Metadata

- Review ID: `semantic-ingestion-2026-07-26-restart-round-03`
- Review mode: `full`
- Review outcome: `Changes required and externally blocked`
- Design baseline SHA-256:
  `1662665b471b6c821773101eae4a627df2034729eab384bff532496d35b1cacf`
- Implementation baseline:
  `44cd7773a75ac8545ddcf799c76dc94c0240f788`
- Reviewers: fresh independent `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer`, followed by coordinator validation

## Executive Assessment

Revision 02 closes the round-02 fence, production/acceptance isolation, and
decision-identity defects. The specification auditor found no additional
internal design gap. Coordinator validation confirms two correctness findings:
the semantic-result accessor lacks authenticated authorization, and the
capability baseline has deployment authorization but no independently signed
ML-acceptance approval.

The test review's five findings are rejected as design findings: they state that
the current implementation and tests do not yet implement the proposed target.
That is expected before an implementation WorkPlan and is outside this design
review. Their suggested tests are already materially represented in the target
verification strategy.

The three registered external blockers remain valid.

## Confirmed Findings

### DREV-R3-001: Semantic result lookup is not authenticated or scope-authorized

- Product priority: `P2`
- Approval disposition: `changes_required`
- Finding type: security and public contract
- Affected scenario and prevalence evidence: semantic-aware result retrieval is
  an important supported post-ingest path, though not every caller uses it.
- Evidence: lines 8640-8644 define
  `semantic_ingestion_outcome(operation_id)` and load by unqualified operation
  ID. Lines 2344-2373 otherwise require authenticated context/key-bound,
  non-disclosing lookup and result access.
- Root cause: lifecycle compatibility added a separate accessor without
  composing the authenticated ingress/result authorization contract.
- Impact: another principal with an operation ID can receive another source's
  semantic result, or implementations must invent a rejection rule.
- Smallest complete correction: replace the scalar accessor contract with a
  purpose-bound `SemanticIngestionOutcomeLookupRequest` carrying trusted
  out-of-band host ingress plus opaque operation/delivery coordinates. Resolve
  and authorize context before repository lookup; tenant, scope, delivery key,
  and fence must match. Every denial uses one non-disclosing shape.
- Verification: two-principal same-ID, guessed operation ID, forged context,
  expired/revoked session, cross-tenant/scope, mismatched delivery key/fence,
  outage, and valid caller tests; denied requests expose no existence, result,
  digest, or coordinate.

### DREV-R3-002: Capability baseline lacks independent ML-approval evidence

- Product priority: `P2`
- Approval disposition: `changes_required`
- Finding type: ML acceptance governance and security
- Affected scenario and prevalence evidence: capability release and activation
  are important supported operational paths.
- Evidence: `ApprovedCapabilityBaselineArtifact` at lines 2469-2479 has content
  and deployment-authorization digests but no independent approval identity,
  time, signed release, trust coordinate, or signature. Lines 2582-2588 require
  an independently approved baseline.
- Root cause: revision 02 correctly separated production deployment authority
  from acceptance code but removed the typed evidence that independent ML
  acceptance occurred.
- Impact: arbitrary policy bytes can be deployment-authorized without proof
  that the product/ML acceptance owner approved their metrics and thresholds.
- Smallest complete correction: define an acceptance-owned signed
  `CapabilityBaselineApprovalRelease` containing approver identity, purpose,
  target baseline digest, capability/dependency coordinates, issue time,
  acceptance trust/release coordinates, and signature. Bind the independently
  verified release digest into the production deployment-authorization issuance
  request. Production trusts only its resulting deployment authorization and
  imports no acceptance schema.
- Verification: independent signature/lifecycle validation plus missing,
  wrong-purpose, wrong-target, stale, expired, revoked, compromised, substituted,
  and rollback release mutations; deployment authorization issuance must fail
  before production activation.

## External Blockers

### SIA-ED-TOPOLOGY-001

- Product priority: `Not applicable`
- Approval disposition: `blocks_approval`
- Required action: product/spec/deployment owner publishes the registered signed
  topology/ownership artifact and completes its constructor, no-network,
  package/profile, unsupported-host, and rollback verification.

### SIA-ED-REPLAY-001

- Product priority: `P2`
- Approval disposition: `blocks_approval`
- Required action: event-model owner selects and governs one
  genesis/checkpoint-consistent equal-version replay algebra, updates
  `docs/design/event_model.md`, and completes all replay permutations.

### SIA-ED-POLICY-001

- Product priority: `Not applicable`
- Approval disposition: `blocks_approval`
- Required action: product/ML acceptance owner publishes the registered signed
  initial statistical/monitoring policy and independent recomputation evidence.

## Rejected Findings

- Missing production implementation of the proposed contracts is not a design
  defect. It belongs to the later implementation workflow.
- Existing tests exercising the current path rather than the target are not a
  new design gap where the design already names the required production-boundary,
  process, security, multilingual, temporal, and statistical verification.
- No retrieval/query or agent-integration finding is admitted.

## Final Outcome

**Changes required and externally blocked.** Two determinate P2 corrections
remain. The user allowed at most three revision rounds; only two revisions have
been used, so one final bounded revision followed by a fresh whole-design review
is permitted. No further revision is allowed after that review.
