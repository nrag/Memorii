# Blocker Delta Review Round 6

## Review Metadata

- Review mode: targeted delta review.
- Review outcome: `CHANGES_REQUIRED`.
- Candidate manifest: `candidate-manifest-v7.json`.
- Candidate lock:
  `c7fa947ce54e9fa6efb5088dd4b0a96188a0135688401f5489a19c469cd1f108`.
- Parent candidate lock:
  `3614ff26697d93c6fc643358d3d85eea147283cb4bdbb83160b20c5e21d4a158`.
- Review date: `2026-08-17`.
- Independent reviewers: `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer`.
- Included scope: the complete frozen `VCC-DREV-008B` production-ownership
  family and adjacent bypasses inside that boundary.
- Excluded scope: unrelated design lanes, production or repository-test edits,
  implementation approval, operational evidence, and whole-design approval.

All three reviewers independently verified the candidate lock and all `75`
tracked hashes. The coordinator repeated manifest validation with zero failures.
Candidate inputs remained read-only throughout review.

## Reconciled Status

| Finding | Coordinator classification | Status | Product priority | Approval disposition | Remediation eligibility |
| --- | --- | --- | --- | --- | --- |
| `VCC-DREV-008B` | confirmed | `OPEN` | Not applicable | changes_required | contract_conformance_action |

## Confirmed Finding

### VCC-DREV-008B: Composition-root and receiver provenance are declarative

- Product priority: `Not applicable`.
- Approval disposition: `changes_required`.
- Remediation eligibility: `contract_conformance_action`.
- Confidence: `high`.
- Finding type: governance / verification / production ownership.
- Affected scenario and prevalence evidence: all composition-root claims and,
  concretely, all six Hermes ingress hooks whose receiver is assigned by
  `HermesMemoryProvider.__init__`. This is an approval-evidence defect; no
  deployed product failure is demonstrated.
- Design location: `blocker-remediation-v6.md`,
  `production-owner-oracle-v4.json`,
  `production-entrypoint-bindings-v7.json`, and
  `validate_production_entrypoint_bindings_v7.py`.
- Governing source or requirement: the round-5 `VCC-DREV-008B` correction
  requires every exact composition root to attach to owner edges, construction
  bridges, triggers, and affected connected rows while preserving exact
  authority and receiver provenance.
- Expected behavior: a composition root begins at its mapped owner; every
  accepted constructor branch resolves to the declared service owner with exact
  authority; its assigned receiver field connects to trigger edges and affected
  rows. Substituted right-hand-side values or later reassignment fail.
- Design behavior: provider/filesystem roots have constructor/factory edges,
  but `hermes_constructor` anchors only six hook methods. No edge starts at
  `HermesMemoryProvider.__init__` or covers its injected-service and two factory
  branches. Root validation checks only owner existence, anchor-ID existence,
  and trigger-ID membership. Field validation checks assignment-name presence
  plus class-name text, not the assignment value or reassignment chain.
- Evidence: replacing all Hermes constructor
  `verified_production_host_authority` values with `None` returns no validation
  failures. Replacing the `self._service` assignment value with `object()` while
  preserving the field and all hook callsites also returns no failures. The
  declared Hermes root owner is `HermesMemoryProvider.__init__`, while every
  declared root anchor begins at a hook method.
- Impact: candidate v7 can certify an authority-free or unrelated Hermes
  service assignment and a disconnected root-to-trigger bridge while claiming
  source-bound composition ownership.
- Root invariant or contract boundary: production ownership must derive each
  receiver from an allowed root-owned assignment chain and connect that chain
  to its trigger and requirement outcome; membership of independent labels is
  insufficient.
- Equivalence class and adjacent bypasses inspected: all four roots, all nine
  triggers, all twenty-three edges, all twelve rows, injected service, provider
  factory, filesystem factory, `None` and substituted constructor authority,
  receiver target rename, receiver-value substitution, later reassignment,
  forged root mapping, detached anchors/bridges, capture exclusion, and direct,
  aliased, and dynamic R08 durable dispatch.
- Positive behavior that must remain valid: the complete nine-trigger census,
  exact provider/filesystem root mappings, valid injected
  `ProviderMemoryService`, valid Hermes factory branches, exact authority
  forwarding, capture-harness exclusion, and all R08 no-write attacks.
- Recommended invariant-level resolution: add owner-qualified constructor edges
  for the Hermes injected-service branch and both factory branches; freeze exact
  authority expressions; AST-resolve `self._service` assignment values to only
  those branches; reject subsequent unproven reassignment; require every root
  anchor to originate at its mapped owner and connect through the assigned field
  to each declared trigger anchor and affected row.
- Verification needed: reject `None` and substituted constructor authority,
  unrelated receiver RHS, later receiver reassignment, root-owner/anchor swap,
  detached construction bridge, and disconnected root-to-trigger/row paths
  while the independent oracle and production sources remain fixed.
- Evidence maturity affected: trigger census, source hashes, and the existing
  mutation predicates are locally verified; composition-root ownership and
  receiver provenance are not locally verified.

## Rejected Or Consolidated Reviewer Observations

- Requests to construct every root and execute every trigger as part of this
  design delta are `unsupported` as an approval blocker. Round 5 explicitly
  retained runtime execution as implementation evidence while requiring a
  determinate static production-binding contract. The implementation workflow
  must later execute that contract through production composition.
- A coordinated mutation of both the independently frozen oracle and ledger is
  `unsupported`; candidate identity already binds the oracle, and semantic
  mutation checks intentionally keep it fixed. Root-owner/anchor and bridge
  attacks remain required with the oracle unchanged.
- Absence of an ordinary in-tree caller for the public Hermes integration does
  not make its constructor test-only. The integration is an external composition
  surface. The uncalled private capture harness remains correctly excluded.
- Constructor authority, receiver-value substitution, root-owned anchors, and
  root-to-trigger connectivity are consolidated into this one ownership-chain
  finding rather than split into additional review rounds.

## Final Outcome

- `VCC-DREV-008B`: `OPEN`.
- Targeted decision: `CHANGES_REQUIRED`.
- Candidate v7 remains the immutable identity of this review and is not
  approved for implementation.
- This bounded review makes no whole-design approval claim.
