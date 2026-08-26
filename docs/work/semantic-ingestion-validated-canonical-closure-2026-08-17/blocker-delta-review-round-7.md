# Blocker Delta Review Round 7

## Review Metadata

- Review mode: targeted delta review.
- Review outcome: `CHANGES_REQUIRED`.
- Candidate manifest: `candidate-manifest-v8.json`.
- Candidate lock:
  `3cfd9324608b5fa18c4426e391017f0a2eccbcc7917c2ef1176de3a587cca078`.
- Parent candidate lock:
  `c7fa947ce54e9fa6efb5088dd4b0a96188a0135688401f5489a19c469cd1f108`.
- Review date: `2026-08-17`.
- Independent reviewers: `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer`.
- Included scope: the complete frozen `VCC-DREV-008B` typed composition-chain
  grammar and adjacent bypasses inside that boundary.
- Excluded scope: unrelated design lanes, production or repository-test edits,
  implementation or operational evidence, and whole-design approval.

All three reviewers independently verified the candidate lock and all `82`
tracked hashes. The coordinator repeated manifest validation with zero failures.
Candidate inputs remained read-only throughout review.

## Reconciled Status

| Finding | Coordinator classification | Status | Product priority | Approval disposition | Remediation eligibility |
| --- | --- | --- | --- | --- | --- |
| `VCC-DREV-008B` | confirmed | `OPEN` | Not applicable | changes_required | contract_conformance_action |

## Confirmed Finding

### VCC-DREV-008B: Source grammar validates leaves but not executable ownership

- Product priority: `Not applicable`.
- Approval disposition: `changes_required`.
- Remediation eligibility: `contract_conformance_action`.
- Confidence: `high`.
- Finding type: governance / verification / production ownership.
- Affected scenario and prevalence evidence: every refrozen candidate relying
  on the Hermes and filesystem composition proof, plus R08 no-write evidence.
  This is an approval-evidence defect; no deployed product failure is shown.
- Design location: `blocker-remediation-v7.md`,
  `production-owner-oracle-v5.json`,
  `production-entrypoint-bindings-v8.json`, and
  `validate_production_entrypoint_bindings_v8.py`.
- Governing source or requirement: the frozen `VCC-DREV-008B` correction
  requires an exact typed injected source, guarded constructor branches, no
  unproven receiver reassignment, real root/instance/field bridges, and closed
  direct/aliased/dynamic R08 durable-dispatch rejection.
- Expected behavior: the validator accepts only the exact constructor type and
  branch state machine; identifies every direct or indirect `_service` write;
  proves each instance receiver originates from its root; and admits only an
  explicit non-durable arena call grammar.
- Design behavior: annotation validation is substring-based. Assignment
  validation ignores branch predicates and indirect writes through `setattr`,
  `object.__setattr__`, or equivalent attribute dictionaries. The filesystem
  instance bridge is declarative path metadata rather than receiver dataflow.
  R08 rejects selected call spellings but does not use a closed call allowlist.
- Evidence: read-only source mutations with hash enforcement disabled returned
  no failures after widening `service: ProviderMemoryService | None`, replacing
  `if service is not None` with `if True`, appending
  `setattr(self, "_service", object())`, or invoking `persist` through a
  dictionary dispatch table. Independent review also demonstrated a detached
  filesystem bundle receiver bridge with no semantic failure.
- Impact: candidate v8 can certify a widened or `None` receiver, bypass factory
  fallback, accept later receiver mutation, declare a disconnected root bridge,
  or reach a durable sink through unrecognized dispatch while still claiming a
  closed source-resolved ownership proof.
- Root invariant or contract boundary: production ownership requires exact
  typed control flow and receiver dataflow from root through trigger to outcome;
  selected token checks and frozen path labels are insufficient.
- Equivalence class and adjacent bypasses inspected: exact and widened unions,
  generic/container annotations, valid and constant branch predicates, direct/
  annotated/augmented/named attribute writes, `setattr`,
  `object.__setattr__`, `__dict__`/`vars` writes, valid and detached filesystem
  receiver flow, and direct/aliased/getattr/import/dictionary-dispatched durable
  calls. All nineteen frozen attacks remain valid; the adjacent forms above are
  one shared grammar boundary.
- Positive behavior that must remain valid: the exact optional injected service
  type, three guarded Hermes branches, exact factory authority, six Hermes hook
  triggers, three direct service triggers, valid filesystem bundle chaining,
  all twenty-seven root paths, and arena-local non-durable operations.
- Recommended invariant-level resolution: freeze normalized AST contracts for
  exact annotations and constructor predicates; validate the complete branch
  state machine and exhaustiveness; inventory every direct or reflective
  `_service` write and reject all outside the three owned assignments; prove
  filesystem receiver def-use from `from_root` through
  `build_provider_memory_service`; replace R08 call-name blacklists with an
  explicit allowed-owner/call grammar.
- Verification needed: retain all nineteen attacks and reject widened/container
  annotations, guard replacement, `setattr`, `object.__setattr__`,
  `__dict__`/`vars` writes, detached/unreachable filesystem receiver flow, and
  dictionary/callable-indirected durable dispatch. Every failure must come from
  a named semantic predicate with oracle and production inputs fixed.
- Evidence maturity affected: source hashes, trigger census, and the existing
  attacks are locally verified; the claimed closed typed-control-flow,
  receiver-dataflow, and R08 call grammar are not locally verified.

## Reviewer Observation Reconciliation

- Exact annotation, branch guard, reflective field writes, instance bridge, and
  dynamic dispatch observations are consolidated into one source-grammar
  finding. Separate example patches would violate the convergence contract.
- Runtime execution through every root remains implementation evidence and is
  not added as a blocker to this design delta.
- Candidate hash pinning remains necessary but cannot replace semantic mutation
  predicates because source-level attacks intentionally disable hash checking.

## Final Outcome

- `VCC-DREV-008B`: `OPEN`.
- Targeted decision: `CHANGES_REQUIRED`.
- Candidate v8 remains the immutable identity of this review and is not
  approved for implementation.
- This bounded review makes no whole-design approval claim.
