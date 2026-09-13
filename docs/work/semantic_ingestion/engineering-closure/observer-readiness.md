# Observer Read Boundary Preflight

Baseline: 191826cd3afb38bf605a337a71d576063b3bae5e. Read-only coordinator
validation of the bounded Spark map; not implementation or closure evidence.

- `atomic_store.py:7975` graph_state_snapshot reads replay state, reference
  ledger and replay state again; rejects mismatch/absent audit certificate and
  returns typed complete GraphStateSnapshot with record payloads, revisions,
  schema fingerprints and read set. This is internal global storage authority,
  not the authenticated public audit surface.
- `atomic_store.py:8081` reference_integrity_snapshot decodes canonical retained
  ledger bytes, verifies its digest and converse against replay state. It is
  the reference-edge authority, not a provenance-index shortcut.
- `atomic_store.py:11844` finalize_source requires exactly one terminal_operation,
  source_summary, source_result, observation_delta and lifecycle member. It
  accepts pre_graph summary only with no group results and graph_bound only
  with group results. Therefore zero-effect source-finalization authority is
  explicitly retained; absence of a named reader does not establish missing
  persistence.
- `atomic_store.py:2277` generation_members exposes retained generation members
  for a known fence. A public cohort resolver still needs an authorized,
  complete source/operation discovery and fixed-revision read path.
- `persistence.py:109` recover_terminal_artifact returns only
  SemanticTerminalOutcome from source_result/terminal_artifact. The initial
  mapper's suggestion that it exposes graph/observation delta payloads is
  unsupported and must not be used as the observer read binding.

Required next ownership proof for the observer packet: authenticate before any
lookup, resolve seed/finalization/terminal-group closure using immutable
observation deltas, bind graph+observation+reference snapshots, and expose every
required typed record through the new public observer. No existing source
normalization reader is an authenticated structural audit API. Root/factory/
filesystem/Hermes integration and all page/revocation tests remain pending.

## Validated V3 Recovery Trace

Coordinator inspection on 2026-09-06 confirms provider ingestion calls
`BootstrapGraphHostBundle.reload_terminal` after normalization replay recovery,
passing required outcome scopes and the operation fence. The atomic store's
`reload_bootstrap_graph_terminal_by_recovery_v3` looks up the exact recovery
index, validates replay/result digests and delivery-principal, scope and fence
bindings, then calls `_reload_bootstrap_graph_terminal_exact_v3`. That reader
checks locator, control, identity and member manifest and the closed terminal
member-kind set before returning the retained result.

This establishes internal known-recovery-key access only. It does not establish
source/operation cohort enumeration or authorization before the first lookup.
The mapper's production caller-frequency and external-deployment questions are
outside this bounded code map; neither is a prerequisite for designing the
missing scoped reader. No observer production binding or closure is claimed.

## Native Observation Persistence Distinction

Coordinator inspection after the new map found that the generic terminal-group
reader at atomic_store.py:12448 decodes `SemanticObservationDelta`, a six-field
summary defined in semantic_ingestion/contracts.py:2174. The bootstrap native
commit at atomic_store.py:11507 likewise writes a CTV summary with operation,
disposition, reason, digest and revision coordinates. Neither is a serialized
`IngestionObservationDelta` with native observation record mutations.

The native model exists in graph_effect_contracts.py:295 and its bootstrap
effect wrapper exists in semantic_ingestion/contracts.py:11355. Their existence
does not establish a write path. Moreover, the current
`CanonicalIngestionObservationRecord` alias at graph_effect_contracts.py:266
contains only `CanonicalSourceTerminalOutcomeRecord`; the canonical observer
also requires source introductions, operation introductions and operation
terminal outcomes. The current map's broader persistence claim is therefore
not accepted as closure evidence.

The observer needs completion of the already specified native observation
record/persistence path as well as authenticated cohort lookup and paging.
This is implementation work under the existing design, not a request for a
new user policy decision. Existing summary formats must retain their identity;
do not relabel their bytes as the native delta or fabricate historical records.

## Record Contract Implementation

The prerequisite leaf now defines all four canonical observation record variants
and the discriminated terminal-group/source-finalization delta union. Mutation
validation binds kind, record ID and digest. Operation-bearing group deltas bind
source, fence, group and operation membership; committed operation outcomes must
name the group's graph delta. Source-terminal-only compatibility retains its
old format while still requiring matching source coordinates.

Owner: `memorii/core/memory_evolution/graph_effect_contracts.py`; focused proof:
`memorii/tests/unit/core/memory_evolution/test_observation_record_contracts.py`.
Coordinator reproduced 16 tests across the new suite and existing graph-effect
suite under warnings-as-errors, in 6.25s. Ruff passes. This is local type/codec
evidence only: native persistence, authenticated reads, paging, revocation and
independent structural comparison remain unimplemented.

Future source-finalization serialization must use its own appropriate boundary.
Do not broaden the terminal-group-only `BootstrapGraphObservationDeltaEffectV3`
merely to transport source-finalization data. The next implementation must bind
the canonical source-finalization record to the existing source-finalization
transaction, preserving group/source lifecycle separation.
