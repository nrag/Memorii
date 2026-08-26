# Blocker Delta Review Round 5

## Review Metadata

- Review mode: targeted delta review.
- Review outcome: `CHANGES_REQUIRED`.
- Candidate manifest: `candidate-manifest-v6.json`.
- Candidate lock:
  `3614ff26697d93c6fc643358d3d85eea147283cb4bdbb83160b20c5e21d4a158`.
- Parent candidate lock:
  `b6656979388e39924e2873ae33108d63cf2f86c0fe8b776c05c6d9337bff031d`.
- Review date: `2026-08-17`.
- Independent reviewers: `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer`.
- Included scope: `VCC-DREV-001D`, `VCC-DREV-001E`, and `VCC-DREV-008B`,
  including adjacent forms inside their already frozen semantic boundaries.
- Excluded scope: unrelated design lanes, production or repository-test edits,
  implementation approval, and whole-design approval.

All three reviewers independently verified the candidate lock and all `68`
tracked hashes. The coordinator repeated the manifest validation with zero
failures. Candidate inputs remained read-only throughout review.

## Reconciled Status

| Finding | Coordinator classification | Status | Product priority | Approval disposition | Remediation eligibility |
| --- | --- | --- | --- | --- | --- |
| `VCC-DREV-001D` | already resolved | `CLOSED` | Not applicable | follow_up | record_only |
| `VCC-DREV-001E` | already resolved | `CLOSED` | Not applicable | follow_up | record_only |
| `VCC-DREV-008B` | confirmed | `OPEN` | Not applicable | changes_required | contract_conformance_action |

## Closed Findings

### VCC-DREV-001D

The frozen correction required reorder, omission, and extra attacks to execute
an externally supplied stateful `check`, record callback identity at invocation
time independently of `writer.events`, and detect exact sequence/count changes
while preserving bytes. `vcc_exp_008_stateful_callback_attacks.py` does this
with an external arm/check/disarm probe. Reorder preserves `104` callbacks but
changes the sequence; omission records `103`; extra records `105`.

The reviewer request to invoke the unimplemented design through a production
trigger is unsupported for this delta. The frozen correction concerns the
executable reference callback seam. The separately frozen v7 normal-path proof
already compares that proposed span schedule with the production codec's
normalization and JSON callback schedules. Requiring production implementation
execution would incorrectly promote design feasibility evidence to implemented
or operational evidence.

### VCC-DREV-001E

The result contains independent fixture-keyed matrices for
`decoded_mixed_wrapper_set` and `decoded_mixed_wrapper_frozenset`. Each matrix
uses fresh probe state and independently detects reorder, omission, and extra
invocation. Both required outer-container families are therefore closed.

## Confirmed Finding

### VCC-DREV-008B: Production ownership graph remains self-declared at its roots

- Product priority: `Not applicable`.
- Approval disposition: `changes_required`.
- Remediation eligibility: `contract_conformance_action`.
- Confidence: `high`.
- Finding type: governance / verification / production ownership.
- Affected scenario and prevalence evidence: every source-bound production
  trigger, composition root, and authority-bearing semantic-ingestion ingress
  represented by the twelve requirement rows. This is an approval-evidence
  defect; no wrong deployed product behavior is demonstrated.
- Design location: `blocker-remediation-v5.md`,
  `production-owner-oracle-v3.json`,
  `production-entrypoint-bindings-v6.json`, and
  `validate_production_entrypoint_bindings_v6.py`.
- Governing source or requirement: the confirmed round-4 correction for
  `VCC-DREV-008B`, which requires complete actual direct/factory/filesystem/
  Hermes trigger classification, exact authority arguments, connected
  root-to-outcome evidence, fixed independent expectations, and source-bound
  mutation rejection.
- Expected behavior: every trigger and composition-root ID binds to its exact
  source symbol and reachable owner path; every public semantic-ingestion path
  is classified; exact authority expressions and receiver provenance are
  mutation-sensitive.
- Design behavior: the validator compares only trigger/root ID sets with the
  oracle, not their mapped source symbols. It does not attach those declared
  roots to row paths. Hermes authority calls are checked for keyword presence,
  not exact values, and field ownership is inferred from initializer text.
  The inventory omits `HermesMemoryProvider.sync_turn` through
  `ProviderMemoryService._sync_composite_event` and
  `HermesMemoryProvider.on_memory_write` through
  `ProviderMemoryService.apply_memory_write`, although both open or reach the
  same arena-backed semantic-ingestion path.
- Evidence: replacing `triggers.direct_sync` or
  `composition_roots.provider_factory` with `"forged"` returns no validation
  failure. Replacing a Hermes `authenticated_host_ingress` expression with
  `None` also returns no failure. Source inspection confirms the omitted
  `_sync_composite_event` and `apply_memory_write` arena/ingest paths.
- Impact: candidate v6 can certify a fabricated or incomplete production-root
  inventory and substituted authority while claiming exact source-bound
  ownership and complete production reachability.
- Root invariant or contract boundary: production ownership evidence must be
  derived from a complete source census and fixed authority dataflow, not from
  self-declared root labels or call spelling.
- Equivalence class and adjacent bypasses inspected: direct `sync_event`; all
  four listed Hermes sync hooks; `sync_turn`; `on_memory_write`; provider,
  filesystem, and Hermes construction; capture-harness exclusion; exact,
  omitted, `None`, and substituted authority; receiver reassignment; same-name
  targets; disconnected rows; and direct/aliased R08 durable sinks.
- Positive behavior that must remain valid: callback closures above; current
  `sync_event` edges; valid provider/filesystem/Hermes construction; explicit
  dynamic bridges; fail-closed optional authority; capture-harness exclusion;
  and direct/aliased R08 no-durable-write rejection.
- Recommended invariant-level resolution: freeze exact trigger and composition-
  root `(id, path, qualified symbol)` mappings independently; AST-resolve each
  mapping and attach it to a connected affected row; enumerate
  `_sync_composite_event`/`sync_turn` and
  `apply_memory_write`/`on_memory_write`; require exact authority expressions
  and receiver/field provenance for every affected edge.
- Verification needed: independent mutations must reject forged trigger and
  root values, removal of either omitted ingress family, receiver reassignment,
  and `None` or substituted authority at every affected trigger/root. The
  oracle, ledger, and frozen production inputs must remain read-only.
- Evidence maturity affected: the production source hashes and narrow R08
  predicate are locally verified; complete source-bound ownership,
  reachability, and authority evidence is not locally verified.

## Rejected Or Consolidated Reviewer Observations

- The proposed requirement that the callback attack itself execute through a
  production trigger is `unsupported`; it exceeds the frozen design-evidence
  correction and confuses design feasibility with implementation evidence.
- The proposed dynamic `importlib`/`getattr` durable-sink attack is
  `outside scope` for this bounded matrix. Round 4 froze direct and aliased R08
  attacks; recursively expanding it after those pass would violate the review
  convergence contract. The design may still prohibit dynamic ownership forms
  explicitly during the `008B` correction.
- Trigger/root retargeting, authority substitution, receiver reassignment, and
  omitted public ingress paths are consolidated into the one root-cause
  `VCC-DREV-008B` finding rather than split into sibling remediation rounds.

## Final Outcome

- `VCC-DREV-001D`: `CLOSED`.
- `VCC-DREV-001E`: `CLOSED`.
- `VCC-DREV-008B`: `OPEN`.
- Targeted decision: `CHANGES_REQUIRED`.
- Candidate v6 remains the immutable identity of this review and is not
  approved for implementation.
- This bounded delta review makes no whole-design approval claim.
