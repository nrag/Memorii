# Source-Finalization Native Observation Integration Map

Status: current binding map plus a preserved, superseded pre-implementation
feasibility record. This is not R17 or parent-milestone closure evidence.

## Current State (HEAD `191826cd3afb38bf605a337a71d576063b3bae5e`)

The native source-finalization observation is now a V2 terminal-manifest
member. The live path neither calls generic `finalize_source` nor wraps the
source record in `BootstrapGraphObservationDeltaEffectV3`.

### Production binding and authority

There is one production composition path for this feature:

```
ProviderMemoryService sync/event terminal path
  (core/provider/ingestion.py:1269, :1359)
  -> BootstrapGraphHostBundle.execute
     (core/semantic_ingestion/bootstrap_graph_host.py:57)
  -> build_builtin_bootstrap_graph_execution_v3
     (core/semantic_ingestion/bootstrap_graph_builtin.py:540)
  -> BootstrapGraphDependentCoordinatorV3._finalize_attempt
     (core/semantic_ingestion/bootstrap_graph_coordinator.py:1076)
  -> DeterministicBootstrapGraphTerminalPreparationV3.prepare
     (core/semantic_ingestion/bootstrap_graph_terminal_preparation.py:456)
  -> BootstrapGraphArtifactAssemblerV3.build_terminal_publication_request
     (core/semantic_ingestion/bootstrap_graph_artifact_assembler.py:1264)
  -> AtomicStoreBootstrapGraphTerminalPersistencePortV3.persist_and_reload
     (core/semantic_ingestion/bootstrap_graph_repository.py:437)
  -> SemanticIngestionAtomicStore.persist_bootstrap_graph_terminal_v3
     (core/memory_evolution/atomic_store.py:10596)
  -> _persist_bootstrap_graph_terminal_v3_linearized CAS
     (core/memory_evolution/atomic_store.py:10745)
  -> _reload_bootstrap_graph_terminal_exact_v3
     (core/memory_evolution/atomic_store.py:11010)
```

The production root passes a real `BootstrapGraphAuthorityRequestV3`: the
replay and prepared source, required scopes, fence, current lease binding, and
writer binding come from the admitted operation/control at
`provider/ingestion.py:1359-1367`. The built-in composer converts those into
the sealed terminal host authority at `bootstrap_graph_builtin.py:515-540`.
The coordinator retains the authenticated request, control epoch/current
generation, final attempt/plan/evidence, lineage, group constructions, and
that host authority when it calls preparation at
`bootstrap_graph_coordinator.py:1076-1088`.

Preparation derives the source observation only from those retained
authorities: canonical source outcome/result, the fence ID, and the actual
predecessor observation revision. Its predecessor is the last persisted group
revision or the store's `"genesis"` control value for a zero-group terminal
(`bootstrap_graph_terminal_preparation.py:446-467`; `atomic_store.py:339`).
`observation_persistence.py:46-71` owns the framed CTV ID, successor revision,
and frozen-schema fingerprint derivations. The assembler receives the typed
delta explicitly and verifies/binds it into the V2 publication request
(`bootstrap_graph_terminal_preparation.py:517-530`; `bootstrap_graph_artifact_assembler.py:1264`).

At the canonical mutation owner, the store authenticates delivery/scope/fence,
lease, writer, epoch, and generation; requires the delta predecessor equal the
control revision; then recomputes the ID, successor revision, schema
fingerprint, and canonical outcome before materializing members
(`atomic_store.py:10769-10853`). One `conditionally_write_records` CAS stores
the source member, manifest, terminal control, identity, locator, request and
recovery indexes; the successor control revision is updated in that same CAS
(`atomic_store.py:10908-10949`).

Reload is version-dispatched, not permissive: a found V1 terminal uses its
historical nine-member grammar and returns no fabricated source observation;
new publication is rejected unless V2. V2 requires and natively decodes the
one source member, joins it to the canonical source result/control revision,
and recomputes its server-owned coordinates
(`atomic_store.py:10769-10772`, `:11010-11256`).

### Production caller counts and reproducible queries

Counts below exclude definitions and tests, and are from the tree at the HEAD
named above.

| Query | Production call sites | Result |
| --- | ---: | --- |
| `rg -n "build_source_finalization_observation_delta\\(" memorii/memorii -g '*.py'` | 1 | terminal preparation at `bootstrap_graph_terminal_preparation.py:456` |
| `rg -n "build_terminal_publication_request\\(" memorii/memorii -g '*.py'` | 1 | terminal preparation at `bootstrap_graph_terminal_preparation.py:517` |
| `rg -n "persist_bootstrap_graph_terminal_v3\\(" memorii/memorii -g '*.py'` | 1 | sealed terminal repository port at `bootstrap_graph_repository.py:437` |
| `rg -n "_reload_bootstrap_graph_terminal_exact_v3\\(" memorii/memorii -g '*.py'` | 3 internal entry paths | persist found-first, request reload, and recovery reload in `atomic_store.py` |

The public root also reaches recovery reload via
`BootstrapGraphHostBundle.reload_terminal` at
`bootstrap_graph_host.py:82-105`, called from `provider/ingestion.py:1295-1304`.
That supplies the replay, scopes, and fence independently of an in-memory
publication object.

`production_entrypoint_bindings` remains the coordinator-owned closure ledger;
this map supplies the current source path and authority evidence for its entry,
but does not itself mark that ledger or R17 closed.

## Superseded Pre-Implementation Feasibility Record

The sections below were captured before the V2 implementation. They are kept
for traceability only. Statements that an input or server derivation was
absent are superseded by the current-state section above.

## Superseded Canonical Transaction Boundary

The bootstrap V3 path does not call the generic
`SemanticIngestionAtomicStore.finalize_source` method at
`memorii/core/memory_evolution/atomic_store.py:11844`. That method remains the
legacy/general `SourceFinalizationAtomicWriteRequest` boundary and currently
serializes its existing `SemanticObservationDelta` summary through
`semantic_ingestion/persistence.py`.

The relevant native boundary is instead:

```
BootstrapGraphTerminalPreparationV3.prepare
  -> BootstrapGraphArtifactAssemblerV3.build_terminal_publication_request
  -> BootstrapGraphTerminalRepositoryV3.persist_and_reload
  -> SemanticIngestionAtomicStore.persist_bootstrap_graph_terminal_v3
  -> _persist_bootstrap_graph_terminal_v3_linearized
  -> _bootstrap_graph_v3_terminal_payloads / _bootstrap_graph_v3_terminal_members
  -> one conditionally_write_records CAS containing terminal member records,
     manifest, terminal control, identity, locator, request and recovery indexes
```

The store's terminal write begins at `atomic_store.py:10596`; the CAS is in
`_persist_bootstrap_graph_terminal_v3_linearized` at approximately 10890. A
typed source-finalization delta must be a member of that terminal manifest and
CAS. Adding it to generic `finalize_source`, or reusing a group-effect wrapper,
would leave the bootstrap source terminal unmodified and split source/group
lifecycle ownership.

## Superseded Existing Native Inputs

`BootstrapGraphTerminalPreparationV3.prepare` creates
`CanonicalSourceTerminalOutcomeRecord` at
`bootstrap_graph_terminal_preparation.py:412-415`, then embeds it in
`BootstrapGraphCanonicalSourceResultInputV3.completed_canonical_source_result`
and `BootstrapGraphCanonicalSourceResultV3.canonical_source_result`.

These are the exact inputs for
`build_source_finalization_observation_delta`:

| Builder input | Current authoritative origin |
| --- | --- |
| `source_outcome` | `BootstrapGraphCanonicalSourceResultInputV3.completed_canonical_source_result`, created from the terminal host authority and completed group constructions in `bootstrap_graph_terminal_preparation.py:390-415` |
| source ID/digest, delivery-principal/key digests, governance carriers/artifact, scopes, fence, operation IDs | fields of that canonical source outcome; its constructor verifies them against `BootstrapGraphTerminalHostAuthorityV3` |
| `observation_revision_before` | not retained by `BootstrapGraphCurrentGenerationV3`, terminal preparation, publication intent, handoff, or canonical source result. For a source with groups, the last terminal-group reload core has an `observation_revision_after`; for the zero-group failed route there is no such group. It is not yet a common, request-bound authority. |
| `observation_revision_after` | no source-finalization transition rule or stored successor is defined in current V3 contracts. The terminal store currently leaves `PreplanningOperationControl.observation_revision` unchanged. |
| `observation_delta_id` | no canonical source-finalization ID derivation or retained caller-supplied identity exists. |
| `observation_schema_fingerprint` | no native observation-schema authority is retained in terminal preparation, publication intent, or bootstrap graph control. |

The last four rows are blocking contract inputs. They cannot be manufactured in
the store from a summary, ambient state, or a group delta. A minimal complete
implementation must first add one explicit, immutable source-finalization
observation authority to terminal preparation and bind it to the publication
request; otherwise the helper cannot be called without inventing identifiers
or revisions.

## Superseded Minimal Contract And Store Delta

The new authority should carry the completed
`SourceFinalizationObservationDelta` (or the exact four inputs and a
deterministic construction whose result is embedded before intent hashing).
It must be present on `BootstrapGraphTerminalPublicationRequestV3`, included
in `BootstrapGraphTerminalPublicationIntentV3.member_intents`, and included in
the handoff/request digest closure. The constructor must verify its
`source_outcome` is byte-equal to
`canonical_source_result_input.completed_canonical_source_result` and its
before-revision equals the predecessor/control observation revision at the
CAS boundary.

The smallest member extension is an additive V3 terminal member kind, for
example `bootstrap_graph_source_finalization_observation_delta`; it must not
be `BootstrapGraphObservationDeltaEffectV3`. That existing type is explicitly
the compulsory *group* CAS carrier: it has a `transaction_group_id` and only
accepts `IngestionObservationDelta`, never `SourceFinalizationObservationDelta`.

Required coordinated edits:

1. In `semantic_ingestion/contracts.py`, add the source-finalization member
   kind to `BootstrapGraphPlanAtomicMemberKindV3`,
   `BOOTSTRAP_GRAPH_V3_ATOMIC_MEMBER_CODECS`,
   `BootstrapGraphTerminalMemberIntentV3`, and terminal intent ordering.
   Add the typed delta to the terminal publication request and validation
   closure. Extend `rebuild_bootstrap_graph_effect_contracts` namespace/model
   rebuilding for `SourceFinalizationObservationDelta` if the new request uses
   the forward-referenced graph-effect type.
2. In `bootstrap_graph_terminal_preparation.py`, construct the delta only from
   the canonical source outcome and the new immutable revision/identity/schema
   authority, then append its member intent after the canonical source-result
   intent. In `bootstrap_graph_artifact_assembler.py`, pass it through
   `build_terminal_publication_request` and reject substitution.
3. In `atomic_store.py`, add the supplied typed delta to
   `_bootstrap_graph_v3_terminal_payloads`, give it its canonical
   `delta_digest` field in `_bootstrap_graph_v3_terminal_members`, and extend
   `_reload_bootstrap_graph_terminal_exact_v3`'s expected kind set, ordering,
   count checks, payload decode, and equality check against the canonical
   source result. The member digest must participate in the existing manifest,
   `BootstrapGraphPlanAtomicWriteIdentityV3.required_member_digests`, locator,
   request, and recovery records automatically through the current tuple/digest
   paths.
4. Update `writer_admission.py` only where it validates the closed bootstrap
   terminal member grammar or exact expected effect/member kinds. Do not add
   the source-finalization delta to its per-operation group fanout logic at
   3324-3365; that fanout is group-only.

The terminal member grammar is currently exactly nine kinds (with the one
failed-source exception that omits `transaction_group_result`), asserted by
`_reload_bootstrap_graph_terminal_exact_v3` at `atomic_store.py:10959+`.
Every construction and reload test that asserts this fixed tuple needs the
new tenth source member and the preserved failed-source exception.

## Superseded Compatibility And Reload Requirements

- Preserve all current `SemanticObservationDelta` bytes and the existing
  group `observation_delta` effect records. Neither is a native source delta.
- Do not widen `BootstrapGraphObservationDeltaEffectV3` or
  `BootstrapGraphGroupEffectCarrierV3`; source finalization has no transaction
  group and must remain a terminal-manifest member.
- The V3 terminal publication intent, manifest digest, atomic identity,
  locator/reload records, and canonical request bytes will legitimately change
  for newly written terminals because the new immutable member is included.
  Existing terminal bytes must remain decodable by an explicit historical
  grammar/version path; a new reader may not simply relax the nine-kind check.
- `reload_bootstrap_graph_terminal_by_request_v3`,
  `reload_bootstrap_graph_terminal_by_recovery_v3`, and
  `reload_bootstrap_graph_terminal_v3` all converge on
  `_reload_bootstrap_graph_terminal_exact_v3`; validating the typed member
  there is the one recovery proof point. The returned
  `BootstrapGraphTerminalReloadV3` should expose the retained delta or a
  typed, validated reference to it so later observer cohort resolution need
  not decode a raw member independently.

## Superseded Required Focused Proof

1. Native normal and zero-group failed source finalization write the typed
   source delta in the same CAS as source result/control/manifest.
2. Lost acknowledgement reloads the exact delta through request and recovery
   paths; member removal, digest substitution, source-result substitution, and
   observation revision substitution fail closed.
3. Existing terminal-group summary/effect bytes retain their old digest and
   decode unchanged; a source delta is never accepted by the group wrapper.
4. A production bootstrap caller reaches the updated terminal preparation and
   atomic-store owner with the newly explicit source-finalization authority.
   Record this exact path in `production_entrypoint_bindings.json` before any
   R17 completion claim.
