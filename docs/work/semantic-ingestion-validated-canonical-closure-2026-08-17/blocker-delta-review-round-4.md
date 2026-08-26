# Blocker Delta Review Round 4

Date: 2026-08-17

Candidate lock:
`b6656979388e39924e2873ae33108d63cf2f86c0fe8b776c05c6d9337bff031d`

Parent candidate lock:
`0cf54b92d4a06f0fa7eb005371d2603e03140bfc67e43c1f19fc7e52e662e4a5`

Mode: independent targeted delta review.

Scope: `VCC-DREV-001D`, `VCC-DREV-001E`, and `VCC-DREV-008B` only,
including adjacent bypasses inside those semantic boundaries. No production
code or repository tests changed during review.

The `spec_auditor`, `correctness_reviewer`, and `test_reviewer` independently
verified the candidate lock and all 48 tracked artifact hashes. The bounded
decision is `CHANGES_REQUIRED`.

## Reconciled Findings

| ID | Product priority | Approval disposition | Finding type | Remediation eligibility | Confidence | Coordinator classification | Status | Required correction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `VCC-DREV-001D` | Not applicable | changes_required | runtime behavior / compatibility verification | contract_conformance_action | high | confirmed | `OPEN` | Run reorder, omission, and extra attacks with an externally supplied stateful `check`. Record callback state at invocation time and assert exact sequence/count changes while bytes remain equal. The v5 attacks pass `check=None`, so they mutate only `writer.events`. |
| `VCC-DREV-001E` | Not applicable | changes_required | verification | contract_conformance_action | high | confirmed | `OPEN` | Run the corrected stateful callback attack matrix independently for both `decoded_mixed_wrapper_set` and `decoded_mixed_wrapper_frozenset`, retaining fixture-keyed results. All six wrapper classes and normal-path proofs are otherwise complete. |
| `VCC-DREV-008B` | Not applicable | changes_required | governance / verification | contract_conformance_action | high | confirmed | `OPEN` | Make validation read-only; never copy the expected graph into the ledger. Freeze relevant production-source hashes. Resolve imports, aliases, receivers, constructors, exact authority arguments, branches, and complete root-to-outcome paths. Enumerate actual direct/factory/filesystem/Hermes triggers and explicitly exclude the uncalled capture harness as a production root. Mutate the ledger or isolated source AST independently while the expected graph remains fixed. Prove R08 no-write against direct and aliased durable-sink source mutations. |

## Direct Evidence

- In `vcc_exp_007_production_callback_wrapper_proof.py`, `_attacks()` calls
  `_enabled_encode()` without `check`. `SpanWriter._checked()` therefore never
  invokes an external callback in any reorder, omission, or extra attack.
- `main()` selects only `decoded_mixed_wrapper_frozenset` as `attack_value`.
  The mixed set receives normal byte, callback, span, decoder, and writer
  checks, but not the attack matrix promised by `blocker-remediation-v4.md`.
- `validate_production_entrypoint_bindings_v5.py::_edge_present` matches only
  the caller's terminal call spelling and independent target-symbol existence.
  It does not bind the call expression to the declared target owner.
- The validator's `main()` overwrites ledger edges and rows from the expected
  graph before validation. Coordinated mutations primarily fail through the
  expected-file identity pin, not the named semantic predicate.
- Rows are not proven as connected root-to-outcome paths; factory, filesystem,
  and Hermes roots are checked only for symbol existence. Relevant production
  sources are not hash-bound into candidate v5.
- The arena is currently state-only, but the R08 attack changes ledger text
  rather than injecting direct and aliased durable sinks into an isolated copy
  of the arena source.

## Equivalence And Bypass Inventory

- Callback boundary: reorder with equal count, omission, extra invocation,
  stateful callback observation, mixed set, mixed frozenset, native and all six
  private wrapper classes.
- Graph target boundary: wrong target with the same terminal name, imports,
  aliases, local shadows, wrong receivers, constructors, context managers,
  removed intermediate callers, and disconnected row subgraphs.
- Root boundary: direct service, provider factory, filesystem factory,
  supervised capture, and all Hermes trigger methods. Capture is evidence
  tooling unless a real caller is proven.
- Authority/outcome boundary: omitted, `None`, substituted, or fallback
  authority; reachable validation and fallback branches; conditional durable
  outcomes; arena capacity fallback; direct and aliased durable sinks; and R08
  no-write scope.

Positive behavior to preserve includes canonical bytes, single final span
writing, valid callback schedules, every wrapper round trip, all valid
composition forms, fail-closed optional-authority behavior, arena-local state,
and separately owned conditional terminal persistence.

## Reviewer Observation Reconciliation

- The test reviewer's proposed closure of `VCC-DREV-001D` is `unsupported`
  after direct inspection of `check=None` in every attack cell. The spec and
  correctness observations are confirmed as one family-level finding.
- The correctness reviewer's proposed closure of `VCC-DREV-001E` is
  `unsupported` against the frozen remediation text, which names both mixed
  outer containers as callback-attack subjects. The wrapper algebra itself is
  accepted as already resolved; only the set-side attack cell remains.
- All three `VCC-DREV-008B` observations reconcile into one confirmed owner,
  authority, reachability, and mutation-semantics finding. Proposed runtime
  execution of every root remains implementation evidence; the design proof
  must nevertheless freeze the complete trigger inventory and a determinate
  runtime proof contract.

## Disposition

- `VCC-DREV-001D`: `OPEN`.
- `VCC-DREV-001E`: `OPEN`.
- `VCC-DREV-008B`: `OPEN`.
- Candidate v5 remains the immutable identity of this targeted
  `CHANGES_REQUIRED` decision and is not approved for implementation.
- This bounded delta decision does not make a whole-design approval claim.

