# Design Review: Semantic Ingestion Result-Access Closure, Round 03

## Review Metadata

- Review ID: `semantic-ingestion-result-access-closure-round-03`
- Review mode: `full`
- Review outcome: `Changes required; final revision authorized`
- Design baseline SHA-256:
  `765151d07dcfc8df49d8c58871f49be3164ece815e4084340e8ea08689edda05`
- Design size: 14,764 lines
- Implementation baseline:
  `44cd7773a75ac8545ddcf799c76dc94c0240f788`
- Reviewers: fresh independent `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer`, followed by coordinator reproduction and validation

## Executive Assessment

The specification and verification reviewers approved revision 02. The
correctness reviewer found two P2 contradictions that the coordinator
reproduced against current provider behavior and the complete target contract.
Both affect important rollout or governed multi-scope cases rather than the
dominant fresh single-source path.

This authorizes the third and final design revision. It must close these
findings without creating a permanent compatibility path.

## Confirmed Internal Findings

### R3-001: Delivery-coordinate cutover can duplicate pre-cutover retries

- Product priority: `P2`
- Approval disposition: `changes_required`
- Requirements: SIA-R01, SIA-R20, SIA-R21, and SIA-R23
- Evidence: current `DeliveryId` strips whitespace and current composite fanout
  persists raw `parent:user` and `parent:assistant` IDs. The target preserves
  accepted bytes and uses typed composite coordinates, while its existing
  legacy cutover does not deterministically migrate either identity form.
- Violated invariant: a retry spanning writer activation must resolve to the
  same admitted source and graph effect, never a new delivery coordinate.
- Reproduction: persist `sync_turn(operation_id="X")` before activation and
  retry after activation; or persist `"  X  "` under the old stripped form and
  retry the original bytes under the new byte-preserving form.
- Root cause: the target identity algebra is complete for new deliveries but
  its activation protocol does not migrate current persisted delivery keys and
  fanout records into that algebra.
- Smallest complete correction: add a pre-activation, state-backed,
  content-addressed migration that deterministically maps unambiguous legacy
  public and composite identities to typed coordinates, records collision and
  provenance evidence, and blocks activation on ambiguity. After atomic epoch
  activation, runtime accepts only target coordinates; there is no parser,
  alias, fallback, or permanent dual-read path.
- Independent verification: frozen pre-cutover fixtures for whitespace,
  delimiter-like IDs, two-child fanout, partial-child completion, collision,
  crash/restart, rollback, and retry across activation. Assert one source and
  one graph effect or fail-closed activation.

### R3-002: Mixed-scope snapshots conflict with singular source governance

- Product priority: `P2`
- Approval disposition: `changes_required`
- Requirements: SIA-R01, SIA-R04, SIA-R09, SIA-R22, and SIA-R23
- Evidence: governed snapshots allow per-message scope, authority,
  classification, modality, and egress bindings and persist their complete
  scope set. `SourceAdmissionRequest.requested_scope` and
  `SourceSemanticContext` still carry one source-wide value for those
  segment-varying authorities, and downstream requests continue to consume
  that singular context.
- Violated invariant: no component may invent a representative governance
  value for a multi-message source or use one segment's authority for another.
- Reproduction: admit a two-message snapshot under the same tenant with scope
  A and scope B and valid authorization for both. Complete-scope authorization
  succeeds, but no truthful singular `requested_scope` or source context exists.
- Root cause: segment-level governance became authoritative without narrowing
  the source-wide context to truly source-invariant fields.
- Smallest complete correction: make the complete
  `RequiredOutcomeScopeSet` and exact segment carrier set the sole authorities
  for segment-varying governance. Restrict source-wide context to genuinely
  invariant source identity/time/policy coordinates. Every downstream
  segment/operation must select and carry its exact segment binding; no
  representative or fallback source value exists.
- Independent verification: accepted/replay/recovery/result-access and
  per-segment provider/reconciliation/compiler tests over mixed scope,
  classification, modality, authority, and egress values. Mutation tests must
  detect swapped, missing, extra, or source-wide substituted bindings.

## Rejected Findings

- RAC-001, RAC-002, and DREV-001 through DREV-003 remain closed.
- A permanent v0/v1 runtime bridge is rejected. Migration must complete before
  target-writer activation and runtime must have one authority afterward.
- Missing implementation remains future conformance work, not a design finding.

## External Blockers

- `SIA-ED-TOPOLOGY-001`
- `SIA-ED-REPLAY-001`
- `SIA-ED-POLICY-001`

## Round Outcome

**Changes required.** Revision 03 is limited to R3-001 and R3-002 plus direct
consistency and verification edits. It is the final permitted revision. A fresh
full review of the resulting exact baseline determines approval or produces an
unresolved-findings report.
