# Design Review: Semantic Ingestion Result-Access Closure, Round 02

## Review Metadata

- Review ID: `semantic-ingestion-result-access-closure-round-02`
- Review mode: `full`
- Review outcome: `Changes required; external decisions remain blocked`
- Design baseline SHA-256:
  `bc37df958aa2b778c8fe1298394e9fb4a1bd8b3fc035ef91fc6439b8855c6772`
- Design size: 14,535 lines
- Implementation baseline:
  `44cd7773a75ac8545ddcf799c76dc94c0240f788`
- Reviewers: fresh independent `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer`, followed by coordinator reproduction and validation

## Executive Assessment

The specification and verification reviewers approved the complete revised
design. The correctness reviewer found three internal contradictions that the
coordinator reproduced. Each is a P2 because the ordinary unchanged-session,
single-scope, canonical-ID path remains representable, while important
recovery, governed multi-scope, and cross-adapter retry cases are unsafe or
undefined.

Revision 01 correctly resolves RAC-001 and RAC-002. The new inventory below
does not reopen those findings. It closes direct contradictions exposed by
their stable-identity and complete-scope invariants.

## Confirmed Internal Findings

### DREV-001: Volatile session context remains in durable operation identity

- Product priority: `P2`
- Approval disposition: `changes_required`
- Requirements: SIA-R01, SIA-R20, SIA-R21, SIA-R22, and SIA-R23
- Evidence: the design says `AuthenticatedIngressContext.context_digest`
  includes current authorized scopes, session, policy, trust, revocation, and
  time evidence and is not a durable coordinate. Other sections still derive
  `allocation_namespace_id` and `operation_fence_id` from that digest and
  require it during checkpoint/group/finalization equality checks.
- Violated invariant: renewed authorization must reauthorize the same stable
  delivery, fence, allocation namespace, recovery identity, and result.
- Reproduction: admit a delivery, renew the session or rotate current policy,
  and recover the same operation. The current context digest changes even
  though immutable provider/principal/tenant/delivery coordinates do not.
- Root cause: revision 01 separated scope membership from
  `DeliveryPrincipalBinding` but did not remove the enclosing volatile context
  digest from all downstream durable derivations.
- Smallest complete correction: derive durable operation/fence/allocation
  identity only from the stable delivery identity, immutable admitted source
  coordinates, and operation ID. Persist admission authorization evidence as
  audit evidence only and use newly resolved evidence solely for current-use
  authorization.
- Independent verification: session renewal, policy/trust rotation, current
  scope expansion/contraction, checkpoint, stale-owner reclaim, recovery, and
  result-access tests must preserve byte-identical durable coordinates while
  revoked or insufficient current authorization remains mutation-free.

### DREV-002: Semantic admission does not authorize the complete governed scope set

- Product priority: `P2`
- Approval disposition: `changes_required`
- Requirements: SIA-R01, SIA-R04, SIA-R09, SIA-R22, and SIA-R23
- Evidence: admission authorizes one `requested_scope`, while a governed
  snapshot can carry per-message scope bindings and atomically persist a
  multi-member `RequiredOutcomeScopeSet`. Complete-set subset authorization is
  explicit only for later result access.
- Violated invariant: no segment may enter semantic promotion or graph mutation
  unless the current trusted authorization covers every scope represented by
  that admitted source.
- Reproduction: current authorization is `{A}`; the scalar admission scope is
  `A`; a governed snapshot contains a server-derived message context in scope
  `B`. The design does not define a pre-promotion full-set rejection.
- Root cause: scalar source admission and later complete outcome authorization
  were not connected by one pre-semantic admission proof.
- Smallest complete correction: derive the canonical complete required scope
  set from validated segment governance before semantic admission, require
  same-tenant subset coverage by the trusted current scope set, and atomically
  persist the proof with admission. Insufficient coverage rejects or retains
  evidence-only according to the existing governed-source policy and produces
  no semantic promotion, remote call, reservation, or graph effect.
- Independent verification: exact, strict-superset, partial, zero,
  cross-tenant, stale, and revoked admission cases over multi-message governed
  sources, with repository/provider spies proving denied cases have no semantic
  or graph side effect.

### DREV-003: Delivery-ID normalization is part of identity but is undefined

- Product priority: `P2`
- Approval disposition: `changes_required`
- Requirements: SIA-R01, SIA-R20, SIA-R21, and SIA-R23
- Evidence: `normalize_delivery_id` determines durable delivery keys and
  composite child IDs, but the design specifies neither a versioned input/output
  contract nor exact Unicode, whitespace, delimiter, and rejection behavior.
- Violated invariant: every adapter and retry must derive byte-identical,
  collision-free durable identity from the same provider delivery ID.
- Reproduction: two adapters trim or Unicode-normalize differently, or one
  accepts a parent ID colliding with the reserved child namespace.
- Root cause: the design names normalization as shared authority without
  defining its canonical algorithm and independent vectors.
- Smallest complete correction: define one owned, versioned contract that
  validates strict UTF-8 scalar input, preserves accepted scalar sequences
  byte-for-byte, rejects empty or all-whitespace input and reserved composite
  collisions, and forbids trimming, case folding, Unicode normalization, or
  delimiter rewriting. Bind the contract version to delivery identity.
- Independent verification: cross-adapter golden vectors for Unicode
  normalization pairs, case, leading/trailing whitespace, non-ASCII IDs,
  reserved delimiters, empty/all-whitespace values, parent/child fan-out, and
  restart/retry identity stability.

## Rejected Findings

- RAC-001 is closed: `SemanticIngestionOutcomeLookupRequest` is now the sole
  result-access request and authorizer input.
- RAC-002 is closed: current authorized scopes are typed and session-bound,
  while stable principal identity excludes mutable scope membership.
- Missing target implementation and executed conformance evidence remain future
  implementation work, not target-design findings.

## External Blockers

The following remain unchanged with `Not applicable` product priority and
`blocks_approval` disposition:

- `SIA-ED-TOPOLOGY-001`
- `SIA-ED-REPLAY-001`
- `SIA-ED-POLICY-001`

## Round Outcome

**Changes required.** Revision 02 is limited to DREV-001, DREV-002, and
DREV-003 plus the minimum consistency and verification edits required to close
them. A fresh full review by new reviewer instances is required afterward.
