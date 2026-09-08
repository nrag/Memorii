> Construction note, not an approved contract. Coordinator found a circular
> successor/delta hash below and incomplete terminal-intent and migration closure.
> The successor proposal.md supersedes those portions. This original analysis is
> retained as evidence, not implementation authority.

# Observation Ledger Transaction Boundary

## Purpose and scope

This note designs the storage boundary required by SIA 23230-23240 and 25380:
one store-owned, replayable observation sequence shared by terminal group and
source-finalization transactions.  It does not alter the sealed graph request,
graph-planning semantics, or source-finalization result semantics.

The current `PreplanningOperationControl.observation_revision` is source/fence
local.  It remains useful as that control's lifecycle checkpoint, but it cannot
be the global observation API revision: two controls can legitimately advance
from the same value concurrently.

## Current concrete paths

| Path | Current linearization and durable authority | Required ledger addition |
| --- | --- | --- |
| Group | `SemanticIngestionAtomicStore.commit_or_reload_bootstrap_graph_group_v3`; existing primary record gives request-idempotency, then one `MemoryPlaneService.conditionally_write_records` commits control, group primary/fanout/effects and graph/event/reference state. | Read and CAS a single observation-ledger head; append one immutable terminal-group delta entry in that same batch. |
| Source finalization | `_persist_bootstrap_graph_terminal_v3_linearized`; terminal locator gives idempotency, then one conditional write commits control, terminal members/manifest/locators. | Read and CAS the same ledger head; append one immutable source-finalization delta entry in that same batch. |
| Reload/recovery | Group primary reload currently decodes only `reload_hex`; terminal reload decodes terminal members and source-finalization V2 member. | Both reload owners must read, decode, re-encode and join the ledger entry to the persisted delta field before returning success. |

`BootstrapGraphTerminalPreparationV3` and the artifact assembler may prepare
the immutable source-outcome and terminal request, but neither may assign a
ledger revision.  Assignment occurs only after the store has read the current
ledger head inside its successful-CAS attempt.

## New store-owned records

Introduce two execution-domain records, owned only by `atomic_store.py`:

1. `semantic_ingestion:observation-ledger:head` holds `{generation,
   observation_revision, last_delta_id, last_delta_digest}`. Genesis has
   generation zero and revision `genesis`.
2. `semantic_ingestion:observation-ledger:entry:<delta-id>` holds the canonical
   encoded `CanonicalIngestionObservationDelta`, its digest, predecessor
   revision, successor revision, generation, and the primary/terminal locator
   that committed it.

The entry ID is server-derived from the terminal identity, not from a mutable
generation: group identity is `(request_ctv_digest, transaction_group_id)`;
source identity is `(operation_fence_id, canonical_source_result_digest)`.
The successor revision is a domain-separated hash of `(prior revision, delta
id, delta digest)`.  The head's generation is the monotonic ordering coordinate;
the hash revision is the opaque API/replay token.  Both are persisted in the
entry so replay proves adjacency rather than relying on wall-clock order.

## Group algorithm

Within the existing `write()` closure, after the group has materialized actual
canonical records and after `advance_reference_integrity` has supplied the
actual next ledger, the store:

1. Reads the global head record.  It is absent only for genesis and then uses a
   `RecordAbsentPrecondition`; otherwise it uses its exact record digest.
2. Builds `GraphRevisionDelta` from current `GraphStateSnapshot.records`, the
   materialized after records, and the difference between the previous and next
   `ReferenceEdgeLedgerSnapshot.entries`.  Changes use actual before records,
   actual `SnapshotGraphRecord` after envelopes, and per-record added/removed
   edge tuples.  `read_set_digest` is the sealed group read set; `write_set_digest`
   is derived from sorted actual changes.
3. Builds source introductions only from the retained
   `BootstrapNativeFactEffectV3.observation_mention_bindings`; each binding has
   the selected candidate, mention span, governance binding and exactly one
   admission.  The group pre-execution manifest supplies the exact governance
   carrier artifact.  It emits no invented source introduction for non-fact or
   noncommitting arms.
4. Builds one operation introduction and outcome for every ordered operation.
   Operation governance/evidence/temporal authority comes from
   `planning_construction_authority`; `temporal_constructions` contains the
   authoritative `OperationTemporalDecisionBinding`.  Future accepted arms
   lacking this closure fail closed.
5. Derives the terminal-group delta ID, schema fingerprint, revision before and
   successor from the head.  It includes the graph delta only for a committed
   group.  The existing group result/reload receives this exact delta as its
   sole group-observation authority.
6. Writes replacement head, immutable entry, group primary/reload and all
   existing records in the current conditional batch.  The entry and head
   preconditions join the existing control/writer/graph/reference preconditions.

The per-control `observation_revision` is updated to the assigned global
successor only as a local last-observed checkpoint.  It is never used to assign
the next global revision.

## Source-finalization algorithm

The terminal preparation keeps producing the sealed canonical source result and
the terminal publication request.  The store replaces the prepared
source-finalization observation's revision fields with store assignment only;
therefore the request needs a preimage/intent that identifies the source
outcome, not a caller-assigned revision.  In the terminal linearized method:

1. Read and CAS the same global head after authenticating the terminal request.
2. Build the source-finalization delta from the sealed canonical source outcome
   and assign its ID/revisions at the head.
3. Add entry/head to the existing terminal member/manifest/locator batch and
   retain the exact assigned delta in the reload/member grammar.
4. Update the local control checkpoint to that successor with its existing
   terminal transition.

This preserves terminal request sealing: preparation binds every semantic input
and source outcome, while the store binds the only server-owned coordinate.

## Idempotency, conflicts, and reload

Before allocating a revision each path first checks its existing idempotency
primary/locator.  If found, reload validates the immutable ledger entry and
returns it; it does not append or advance the head.  On a failed batch CAS:

* if the path's primary/locator now exists, reload and verify the same entry;
* otherwise reread head and all existing graph/control authority, rebuild the
  delta from those actual values, and retry only through the current group
  related-conflict or terminal stale-generation policy;
* never reuse a stale delta/revision preimage after a head conflict.

Group reload must validate primary request/reload bytes, entry bytes, entry
predecessor/successor, head reachability, delta identity and the primary ID.
Terminal reload must additionally validate its V2 member against the ledger
entry and source outcome.  Writer admission must require exactly one matching
entry/head replacement for both write families, reject duplicate entry IDs,
orphan entries, mismatched predecessor, and an observation effect whose bytes
do not re-encode.

## Compatibility and migration

Add explicit grammar versions to group reload/result and terminal publication
reload.  Legacy group and terminal bytes decode under their current grammar and
must re-encode byte-identically; their reload path reports no ledger delta and
must not synthesize audit records or advance/create a ledger head.  New grammar
requires exactly one joined delta entry.  A migration is append-only: historical
records stay historical, while the first new transaction creates genesis head
if absent.

## Alternatives evaluated

**Store-finalized source observation.** This is selected.  It keeps semantic
source-result preparation sealed, but moves only the server-owned global
revision assignment to the authority that already owns the conditional write.
It supports head CAS retry and lost-ack reload without trusting a preparer with
an ambient head snapshot.

**Trusted preparation reads head and supplies successor.** Rejected.  The
preparer runs before the terminal store CAS and can race another source.  A
store retry would either accept a stale successor or require re-preparation,
changing a sealed request.  Treating the prepared head as trusted also violates
the store-sole-assignment requirement.

## Required ownership changes

| Owner | Change |
| --- | --- |
| `atomic_store.py` | Head/entry records, store assignment, actual graph delta projection, same-CAS writes, reload verification. |
| `observation_persistence.py` | Pure construction accepts store-issued coordinates and actual before/after/reference material; no head reads. |
| `contracts.py` | New grammar dispatch and exact delta/entry joins on new group/terminal reload types; legacy omission serializers. |
| `writer_admission.py` | Validate complete group and terminal batches including head/entry joins. |
| terminal preparation/assembler | Bind source outcome intent, remove caller-owned source observation revisions from the sealed request. |

## Remaining determinate implementation questions

No product-policy decision is missing.  The implementation must settle these
mechanical details in the new contract grammar: exact record IDs/domains,
whether `generation` is exposed by the API or only replay metadata, and how the
initial head is authorized in the governed write policy.  Each has a single
safe default: deterministic store-derived IDs, opaque revision API token with
generation retained in entry metadata, and the existing writer capability plus
absent-record precondition for genesis.
