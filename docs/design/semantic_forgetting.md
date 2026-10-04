# Semantic Forgetting (Revocation) Design

- Status: canonical design — Level 2 review complete (two reviewer rounds,
  no validated P1/P2 remains); ready for an implementation WorkPlan
- Delivery fidelity: Level 2 (early real-world testing)
- Governs: semantic-plane logical forgetting for entities, relations, facts,
  and sources
- Amends: `docs/design/durable_execution_and_solver_runtime.md`, section
  "Forgetting, erasure and retention" (epoch sentence; see §14)
- Related: `docs/design/event_model.md` (7.3), `docs/design/memorii_spec.md`
  (16.2, 16.23), `docs/design/memorii_storage_details.md`,
  `docs/IMPLEMENTATION_RULES.md`,
  `docs/work/semantic-forgetting-design/design.plan.md`

## 1. Plain-Language Summary

Memorii currently has ways to change its mind about a fact; this design adds
the one that is missing:

- **Correcting** says "that was wrong; here is the better answer." The old
  fact stays in history, marked superseded. A model-assisted pipeline can do
  this during normal operation.
- **Forgetting (revocation)** says "this may well be true, but it must never
  be served again" — a privacy operation. Only the installation owner can do
  it. History keeps the bytes (backups and audit survive), but no read path
  may ever surface the content again.
- **Erasing** destroys storage. Out of scope here; it stays whole-partition
  only.

**Worked example.** A user tells the owner: "forget everything the Mars
Venus 008 project told you; I'm entitled to removal." The owner resolves
the project's opaque entity coordinate (from export or operator tooling)
and runs `forget plan` with that typed selector plus a scope note for the
record. The plan enumerates, using opaque coordinates only: the project
entity, its aliases, the claims asserted from that source, the entity links
built from them, the solver justifications that cited that evidence, and
the retained runtime records derived from them. The owner reviews the
counts and applies it. After apply:

- graph observation, retrieval, structured fact reads, scoped context,
  entity matching, identity-lineage serving views, and generic record
  queries no longer return the entity, its claims, or anything derived
  solely from them;
- solver conclusions that relied on the revoked evidence are marked
  `revalidation_required`, not silently deleted;
- the append-only event log still contains the original events (the receipt
  says so explicitly), backups still contain encrypted historical bytes, and
  a restore of an older backup re-applies the revocation automatically;
- exporting the installation omits the revoked content.

If the same facts are later re-learned from a different, authorized source,
that happens through the normal validated ingestion path as new claims —
forgetting never fabricates replacements, and a revocation itself is never
un-done: there is no un-forget.

**Jargon used in this document**

| Term | Meaning |
| --- | --- |
| revocation directive | the append-only semantic record that names identities which must never be served |
| suppression id | content-free tag tying the control-plane journal entry to the semantic revocation record |
| tombstone | a new *version* of a derived record whose payload is content-free and whose lifecycle is `revoked` |
| replay | deterministic reconstruction of the semantic state from the append-only event batches |
| serving path | any code path that returns semantic or runtime content to a host, agent, or operator |
| revoked-identity view | the single derived set of revoked identities every serving gate consults (§6.7) |
| eligibility epoch | counter in control state; signed into every publication tuple; caches key off it |
| Tier A | the constant-time verified-read check that the released tuple matches control state |
| dependency closure | everything reachable from a revoked identity through provenance, claims, projections, and justification evidence |

## 2. Problem Definition

**Current behavior.** `GovernanceOperator.plan_forget` enumerates only
`runtime_tasks` task ids and ignores the scope note for matching
(`operator_governance.py:100-123`). `apply_forget` writes an untyped
suppression journal under the read-only barrier and bumps
`control_revision`. The journal's only serving consumer is
`StorageAdministrationOperator.read_export` (`operator.py:144-177`).
Semantic content — entities, claims, sources, and everything derived from
them — is untouched: retrieval, prefetch, scoped context, structured fact
reads, graph observation, entity matching, the harness envelope, resume
envelopes, and identity-lineage audit all still serve it. The code comment
at `operator_governance.py:174-175` claims an epoch invalidation that no
code performs, and a control-only epoch bump would break every Tier A
verified read (`service.py:703-706`) until some later publication realigned
the signed tuple — this is the recorded DUR-09 open item.

**Why it matters.** The governing design
(`durable_execution_and_solver_runtime.md:349-357`) promises logical
forgetting with dependency closure, ineligibility of suppressed evidence for
replay and promotion, `revalidation_required` solver recommendations, and
no cross-path disclosure. The implementation delivers none of that for
semantic memory. An owner who runs `forget apply` today and reasonably
believes content is suppressed has a system that keeps serving it from every
semantic surface — a privacy-correctness defect, not a polish gap.

**Affected actors.** Installation owners (invoke forget, must be able to
trust the receipt); host agents and their users (must not receive revoked
content); operators restoring backups (must not resurrect revoked content);
auditors (must be able to prove what was revoked and when, without the
content — through an owner-authorized path).

**Desired outcome.** One revocation authority, durably recorded in the
append-only semantic event log and mirrored by a control-plane watermark,
from which every serving path inherits suppression through a single derived
revoked-identity view; a closed, typed, tested contract end to end; and an
epoch mechanism that invalidates caches without breaking Tier A.

## 3. Normative Sources And Precedence

1. `memorii_spec.md` — backtracking is revision, not deletion (16.2, 16.23):
   undo appends compensating events and deactivates justifications.
2. `memorii_storage_details.md` — transcript memory, scoped retrieval,
   temporal validity, and storage-backend contracts.
3. `event_model.md` 7.3 — a delete event *marks*; replay must not
   physically remove. 14.1 — events are append-only, contiguous.
4. `IMPLEMENTATION_RULES.md` — implementation hard constraints and commit
   gating for repository changes.
5. `durable_execution_and_solver_runtime.md:349-357` — the four-operation
   separation; closure through provenance, justifications, projections,
   caches, writebacks, retained replay; content-free suppression ids;
   `revalidation_required`; retained-bytes disclosure; restore re-applies
   revocation before reads. Amended by §14 of this document (one sentence,
   recorded, not silent).
6. Production code as cited in §4; where code and design disagree, the
   design governs future implementation and the disagreement is the gap this
   design closes.

## 4. Existing-System Analysis (verified 2026-10-02)

**Replay authority.** `SemanticReplayState` (`event_replay.py:710-754`) is
the folded state of append-only batches: `materialized_records` (latest
version per `(record_kind, record_id)`) plus `event_bindings`. The fold
(`_apply_semantic_event_batch`, :1365-1483) is kind-agnostic: events are
`create` (target absent) or `update` (exact predecessor advance); records
are replaced, never removed. The store refuses to serve unless the persisted
state equals genesis reconstruction (`atomic_store.py:11644-11670`) — so any
revocation that must affect replay-derived state must itself be an event in
the batch log. The closed `GraphRecordKind` union has 12 members
(:93-98, duplicated in `graph_records.py:39-43`); `MutationKind` is
`create|update` (:98). **Kind-awareness does not end at the fold**: the
envelope's record-identity binding is per-kind parametric
(`event_replay.py:203-207, 241-288`), and four per-kind tables must learn a
new member — `CommittedRecord` (:99-103), `NonOwningGraphRecord`
(`graph_records.py:255-259`), `_CARRIER_UNION_MEMBER_TYPES`
(`event_replay.py:106-119`), and the `graph_record_id` names map
(`graph_records.py:262-278`, which raises
`canonical_graph_record_identity_invalid` for unknown kinds). Entity
revisions already carry `lifecycle: active|retired` (retired is never
produced today); claim projections already honor a
`retired_claim_assertion_ids` filter (`projection_history.py:5767,
6203-6209`); `OperationKind` already includes `retraction` with
`TemporalTransitionRecord` — a *correction-family* mechanism.

**Authoring path (why §6.10 item 1 exists).** Events are derived by the
store from `SemanticGraphDelta`s built from ingestion terminals or planning
intents; callers cannot supply events. `OperationKind`
(`contracts.py:1147`) has no governance member; `compile_accepted_carriers`
(`carriers.py:96-186`) produces only the four carrier families;
`SemanticGraphDelta.create` requires an accepted terminal outcome
(`contracts.py:2156-2172`); planning materialization rejects unknown kinds
(`graph_planning.py:1502-1530`). A governance-owned delta entry point is
therefore a design requirement, not an implementation nicety.

**Two serving planes.**

- Replay-fed paths: graph observation
  (`read_detached_observation_authority`, `atomic_store.py:11789-11848`),
  identity-lineage audit (`provider/service.py:2047-2096` — host-ingress,
  grant-authorizer-backed, *not* owner-capability-gated), entity matching
  (`provider/service.py:1883-1938` — reads `graph_state_snapshot()` and
  filters only `lifecycle == "active"`), the derived semantic index (no
  production reader today).
- Evolution-record paths, which bypass replay and read memory-plane records
  (`claim_state`, `entity_link`, `action`) directly: production retrieval
  (`provider/service.py:2034` → `retrieval_runtime.py:78` →
  `state_repository.py:38-57`), the prefetch evolution channel, scoped
  context (`scoped_context/service.py:132, 297-345`), structured fact reads
  (`structured_fact_read.py:95-179`), runtime-step retrieval
  (`execution/service.py:145` → `memory_plane/service.py:313`), legacy graph
  queries (`graph_queries.py` / `graph_persistence.py`), and the
  memory-plane query surface (indexed scan, pagination, lookup, cursors).

**Reader gates that a tombstone must survive (verified).** The entity-link
gate is a *denylist* — `link.lifecycle_state.value != "invalidated"`
(`retrieval_runtime.py:85`) — so an unknown `revoked` value would be served;
the same function converts the value via `RecordLifecycleState(...)`
(:113), which raises `ValueError` for a non-member; and
`record_from_claim_state` maps lifecycle through an exhaustive dict
(`record_projection.py:216-223`), which raises `KeyError` for a new member.
Claim readers with allowlist semantics (e.g. `retrieval.py:285, 320`;
`structured_fact_read.py:588-637`) exclude non-members in their
current-version branches — but they serve SUPERSEDED/INVALIDATED/EXPIRED as
context under `include_context` (`retrieval.py:296-300`), and the
ALL_VERSIONS branch of `structured_fact_read.py:603-611` excludes only
CANDIDATE, so a new member would be served there — `revoked` must be
excluded explicitly everywhere, never mapped onto those members.

**Solver/execution plane.** `SolverJustificationRecord.source_refs`
(`runtime_contracts.py:202-227`) are free-form evidence ids with no
store-side existence check. The harness envelope, resume envelope, and
checkpoints serve justifications filtered only by the `active` flag
(`harness_state/service.py:120-151`; `runtime_checkpoint.py:235-302`). The
resume walk already implements temporal revalidation (expired/not-yet-valid
assumptions append `node_id:reason` and force `revalidation_required`) —
the pattern revocation reuses.

**Control plane.** `apply_forget` (`operator_governance.py:125-198`):
capability → drift check → read-only barrier → journal write (untyped JSON,
0o600, atomic rename; filenames embed timestamp+count) → `control_revision`
bump + `logical_forget_applied` journal entry under the publication fence.
No epoch bump (comment claims one). `apply_erasure` bumps
`eligibility_epoch` but also destroys the partition. Tier A
(`service.py:693-731`) requires
`finalized.eligibility_epoch == state.eligibility_epoch`; both publication
paths take the epoch from control state at prepare
(`service.py:578-582`, `runtime_repository.py:577-590`). **No finalize path
writes control state today** — `_finalize_publication` writes only
`publication_states` + journal (`service.py:790-798`;
`control.py:286-298`), and `resolve_pending_publication`
(`service.py:629-679`) is an additional finalize site. Restore copies
current suppression journals into staging filename-preserving
(`operator_backup.py:451-461`) and boots them into the fresh host
(:519-526) — file-copy only, no semantic reconciliation. Memory-plane
version-rewrite is mechanically supported (versions-table append + current
upsert, `partition.py:890-933`; publication path accepts preconditioned
upserts, `factory.py:101-141`).

**Schema authority chain for a new record kind.** Closed-union literals
(two declarations — canonical owner is `graph_records.py`, the duplicate in
`event_replay.py` must be reconciled to one owner); per-kind pydantic record
model; the four per-kind tables above; codec manifest totality validator
(`canonical_graph_codec_manifest`, `graph_records.py:304-341` — note the
snapshot's `codec_by_kind` lookup (`atomic_store.py:11703-11706`) raises a
raw `KeyError` today and needs a typed failure);
`generated_reference_schema_manifest` edge declarations
(`reference_integrity.py:260-321`); envelope schema version and registry
history (`SemanticEventSchemaRegistry`, monotonic, batches pin revision);
typed-value publication regeneration
(`memorii/scripts/generate_observation_registry_publication.py` →
`author_typed_value_publication_package` at
`core/memory_evolution/typed_value_publication_authoring.py:63` →
grammar/registry/schema/enum/digest-signature artifacts + both manifests);
release-preparation `candidate.json` repin.

**Feasibility evidence.** The mechanics this design depends on were verified
against current code (coordinator + independent reviewers, 2026-10-02): the
native group-commit precedent constructs a `SemanticGraphDelta` without an
ingestion terminal (`atomic_store.py:16571-16590`), so the governance entry
is constructible; replay-state CAS (`atomic_store.py:16681-16699`) and the
freeze guard/writer enrollment (`service.py:517-535`,
`atomic_store.py:8626-8636`) apply unchanged; memory-plane version-rewrite
retains prior bytes and is accepted by the publication path
(`partition.py:890-930`, `factory.py:122-139`); the control database
already performs multi-object single-transaction writes
(`control.py:232-255`), so the one-transaction epoch finalize is a
composition, not a new mechanism; every §6.7 injection root is reachable
through existing constructor seams (`retrieval_runtime.py:60-76`,
`provider/service.py:336-386`, `graph_observation_host.py:58-97`,
`factory.py:124-162`). No feasibility risk remains hidden behind an
assumption.

## 5. Core Distinction: Correction, Retraction, Revocation, Erasure

| Operation | Who | Truth claim | History | Effect on serving |
| --- | --- | --- | --- | --- |
| correction / status update | validated pipeline or solver proposals | "a better answer exists" | supersession overlay, old marked | old answer demoted, still visible as history |
| retraction (existing) | validated pipeline from source signals | "the source withdrew the assertion" | `TemporalTransitionRecord`, claim marked retracted | claim ineligible, derivation replays |
| **revocation (this design)** | **owner only, barrier-gated** | **"may be true; must never be served"** | **revocation directive event + tombstone versions; bytes retained** | **every serving path excludes; dependents revalidation_required** |
| erasure | owner only, second consent | "destroy" | bytes destroyed | nothing left to serve |

Revocation is **not** modeled as a belief change: it never asserts the
revoked content is false, never supersedes it with new content, and cannot
be issued by model output or host tooling. It is a release-suspension
directive over identities. It is also **irreversible into re-serving**:
there is no un-forget operation; revoked content can only re-enter through
a new normal validated ingestion from an authorized source, as new claim
identities.

## 6. Contracts

### 6.1 Revocation directive record (semantic plane)

A new member of the closed `GraphRecordKind` union: `revocation_directive`.
Canonical owner of the union and the model: `graph_records.py` (the
duplicate declaration in `event_replay.py` is collapsed to an import —
implementation requirement, not a compatibility alias).

`RevocationDirectiveRecord` (extends the `_GraphRecord` discipline:
`operation_id`, `record_version`, `codec_fingerprint`, `record_digest`,
self-validating):

- `revocation_id` — record id
- `suppression_id` — opaque, installation-keyed tag derived
  deterministically from **stable content coordinates only**: installation
  id + `plan_digest` + `closure_digest`. It is invariant under journal
  copy, restore, boot, and any future journal compaction or rename; it is
  never derived from filenames or timestamps, and never contains source
  text.
- `revoked_targets` — closed discriminated union, at least one member:
  - `EntityRevocationTarget(logical_entity_id)` — covers every revision,
    alias, and type-evidence record of that logical entity
  - `ClaimRevocationTarget(claim_assertion_id)`
  - `SourceRevocationTarget(source_id)` — covers evidence, provenance, and
    citation records from that source
  - `RecordRevocationTarget(record_kind, record_id)` — exact-coordinate
    revocation for the remaining kinds
- `closure_manifest` — the plan-time enumeration: content-free coordinates
  of every dependent record in the dependency closure, plus
  `closure_digest` over that enumeration. The projection gates do NOT trust
  this snapshot (see 6.2); it binds the plan to the applied directive for
  audit.
- `authority` — the owner-capability presentation digest and the control
  journal position of `logical_forget_applied` (both content-free)
- `applied_at` — system UTC timestamp
- `scope_note_digest` — digest of the owner's scope note (the note itself
  lives only in the control-plane journal)

Constraints (fail-closed):

- `extra="forbid"`, frozen, strict — unknown fields or enum values reject.
- Idempotence is layered: (a) `forget apply` looks up existing journal
  entries by `plan_digest` before minting anything — a retry of the same
  plan reuses the existing `suppression_id` and re-runs only idempotent
  steps (the fold's byte-identical duplicate rule covers re-delivery of the
  same event under the same transaction coordinates); (b) the same
  `suppression_id` with divergent targets is an integrity conflict; (c) a
  **different** `suppression_id` whose targets overlap already-revoked
  identities is *accepted* — directives union (6.2) — and the receipt
  counts only newly-revoked targets.
- The directive never carries statement text, aliases as written, evidence
  spans, or any servable content.

### 6.2 Replay and projection semantics

The fold does not change. A `revocation_directive` create event materializes
like any other record; `MutationKind` stays `create|update`; no record is
ever removed from `materialized_records`; the persisted-equals-genesis
invariant is preserved because the directive is in the batch log.

A **revoked-identity view** (§6.7) is derived from the replay state: the
union of revoked logical-entity ids, claim ids, source ids, and record
coordinates across all directives — union semantics, so overlapping
directives never conflict. Projection rules:

1. **Serving projections exclude.** The native graph observation stream, the
   claim projection eligibility set (the existing
   `retired_claim_assertion_ids` mechanism gains the revoked set), observed
   entity/relation/alias/type-evidence streams, entity-match verification,
   and the derived semantic index projection omit: revoked records
   themselves, and records whose reference edges resolve to a revoked
   identity (via the reference-integrity ledger). `revocation_directive`
   records themselves are not part of any host-facing observation grammar —
   they appear only in owner/operator integrity surfaces.
2. **Integrity projections retain.** The graph state snapshot, the
   reference-integrity ledger, replay state, and identity-lineage *audit*
   keep revoked records — they verify structural truth and must reconcile
   with genesis. Readers of these projections that serve hosts must apply
   the revoked-identity view themselves (§6.8) — retention in the integrity
   projection never licenses serving; the retained audit of a revoked
   identity is reachable only through the owner-capability forensic
   surface defined in §6.8 (retained lineage for named coordinates; R16).
3. **New dependents are covered.** Because gating is by identity set, a
   record created *after* the directive that references a revoked identity
   is also excluded — the closure snapshot is not a trusted gate.
4. **Mixed-source conclusions.** A conclusion supported by revoked and
   non-revoked evidence does not drop the revoked citation and survive; it
   becomes ineligible as-is (serving exclusion), and may only re-enter
   through a new normal validated operation built without the revoked
   evidence — the governing doc's no-citation-dropping rule.

### 6.3 Evolution-record plane: tombstones and the reader-edit ledger

A compensating owner-authorized publication rewrites each affected derived
record as a new version (revision, not deletion — mechanically supported
today: versions-table append + current upsert, `partition.py:890-933`):

- `claim_state` → `lifecycle_state="revoked"` (new closed-enum member of
  `ClaimLifecycleState`), payload reduced to identity coordinates
  (`claim_id`, `claim_key` coordinates without servable text), evidence
  spans dropped, `object_value` replaced by a content-free marker digest.
- `entity_link` → lifecycle `revoked` (new member), payload content-free.
- Legacy `graph_node`/`graph_edge` records → superseding version marked
  revoked, content-free.

The version history and the semantic event batches retain the prior bytes
(backups and audit survive; the receipt discloses this). Suppression does
**not** arrive by accident of existing reader styles; the design requires an
explicit reader-edit ledger so `revoked` is excluded — never served, never
crashing — at every lifecycle consumer:

| Site | Current behavior | Required edit |
| --- | --- | --- |
| `retrieval_runtime.py:85` link gate | denylist `!= "invalidated"` — would serve `revoked` | convert to allowlist of eligible members |
| `retrieval_runtime.py:113` candidate conversion | `RecordLifecycleState(value)` — `ValueError` on non-member | add `revoked` member or map to a never-eligible representation |
| `record_projection.py:216-223` claim validity map | exhaustive dict — `KeyError` on new member | add `revoked → TemporalValidityStatus.INVALIDATED` (projection-only; servable text is already content-free on the tombstone) |
| `retrieval.py:285, 296-320` claim readers | allowlist, but SUPERSEDED/INVALIDATED/EXPIRED served as context | exclude `revoked` from every context-inclusion path |
| `structured_fact_read.py:588-637` | allowlist lifecycle checks | exclude `revoked` from projected and context items |
| scoped-context eligibility closures | lifecycle/status based | reject revoked records and records whose source closure intersects the revoked-identity view |

`revoked` must never be aliased onto `superseded`/`invalidated`/`expired`
(those remain servable as history/context); it is its own never-served
member. Unknown `revoked` values under an older binary fail closed at
strict decode — correct privacy behavior; at Level 2 this is verified via
strict-decode proxy tests (synthetic unknown values against current
readers); true old-binary evidence is a recorded Level 3 deferral.

### 6.4 Dependency closure (plan-time)

**Plan input contract.** `forget plan` takes a closed, typed
target-selector union — exactly the members of `revoked_targets`
(`entity(logical_entity_id)`, `claim(claim_assertion_id)`,
`source(source_id)`, `record(record_kind, record_id)`), at least one. The
`scope_note` is an annotation recorded in the journal; it is **never a
matcher** — free-text scope resolution is not offered, because it would
require exactly the model-driven resolution §5 forbids. Owners obtain
opaque coordinates from export or operator tooling; the implementation
must verify that at least one existing surface exposes
`logical_entity_id` / `claim_assertion_id` / `source_id` coordinates for
un-revoked content (R5 acceptance criterion) — no new discovery surface is
in scope. A plan whose closure is
empty is refused with `invalid_request` (extending today's fail-closed
behavior; `revoked_targets` requires ≥1 member, so an empty plan could not
be applied anyway).

From the selectors, `forget plan` computes — under one consistent snapshot
(a single partition read transaction over the replay-state snapshot and its
readers; the apply-time drift check is the fence against later movement) —
all coordinates content-free:

1. direct targets (the typed selectors);
2. claims whose `claim_identity` subject/object resolves to a revoked
   entity; claims derived (projection history) from revoked claims;
3. aliases, type evidence, citations, provenance, and reference
   dispositions attached to revoked entities/claims/sources;
4. `claim_state`/`entity_link`/legacy graph records for the above;
5. solver justifications whose `source_refs` match a revoked source or
   evidence id (exact id equality; unverifiable refs are unaffected);
6. runtime task records whose observations' source ids intersect the revoked
   source/evidence id set — the same exact-id rule as justifications (this
   extends today's task-id enumeration rather than replacing it);
7. learned-ontology evidence referencing revoked sources.

The plan returns counts and coordinates per class, a `plan_digest` (over
the full closure), and the `closure_manifest` that apply will bind into the
directive. Drift between plan and apply re-validates each enumerated target
still exists (extending today's conflict check); already-revoked targets are
reported, not double-counted.

### 6.5 Solver and execution plane

For every justification in the closure (class 5): the harness envelope's
hypothesis rendering and the resume envelope mark the dependent conclusion
`revalidation_required` with reason `revoked_evidence`, mirroring the
existing temporal revalidation walk (`runtime_checkpoint.py:262-277` —
appends `justification_id:revoked_evidence`). Checkpoints embed the marking
so resume after restart preserves it. Nothing is deleted: the justification
record, its overlay bindings, and history remain; they simply cannot
sponsor a served conclusion until re-derived from eligible evidence.
Runtime tasks whose observations' source ids intersect the revoked set
(closure class 6) are excluded from serving and export — the harness state
views and the operator inspection/explain surfaces (`task inspect`,
`solver inspect`, `explain`, per governing line 325) consult the view's
revoked task-id set, the same mechanism `read_export` already applies,
extended to the new enumeration.

### 6.6 Control plane: plan/apply sequence and journal contract

`forget plan` (normal mode): owner capability → typed selectors → closure
computation → content-free plan (`plan_digest`, counts, coordinates,
disclosure notice that historical bytes are retained). No state change.

`forget apply` (owner capability; plan presented by value):

1. Drift re-validation of every enumerated target.
2. **Journal first.** Under the read-only barrier: write the typed
   suppression journal entry and the control journal
   (`logical_forget_applied`, control-revision bump,
   `pending_epoch_increments` + 1). The journal entry is a versioned
   envelope: `{"journal_version": 2, "suppression_id", "plan_digest",
   "closure_digest", "suppressed": [content-free coordinates],
   "applied_at_unix"}` — readers accept v1 (legacy task-id entries) and v2,
   reject unknown versions fail-closed. **Forget is durably complete at
   this point**: the ack receipt states suppressed counts (newly revoked
   only), that historical bytes are retained, and that enforcement
   publication is pending or done.
3. Barrier release is the owner's `resume`/mode-change operation under the
   existing mode contract — apply never auto-restores write mode. **The
   mode transition out of `read_only` is also the live-process trigger for
   enforcement**: draining pending forget reconciliations (and their
   publications) is part of acknowledging the resume, and the drain
   retries until no journal entry lacks its directive (so a clean CAS
   abort mid-enforcement cannot strand a forget until the next restart) —
   no separate operator publish step exists.
4. **Enforcement publication.** After barrier release (triggered by the
   mode-resume drain or by the boot hook below), append the
   `revocation_directive` event (with tombstone rewrites for the
   evolution-record plane) through the governance-owned publication entry
   (§6.10 item 1) — owner authority, full validation stages, CAS on the
   replay-state record. This publication embeds the effective epoch
   (control epoch + pending increments) and finalizes the epoch advance
   atomically with the directive (§6.9).

Reconciliation closes any crash gap between steps 2 and 4. Its owners are
the **mode-resume drain** (live process) and the **boot resume hook**
(composition root) — not doctor: for every journal entry there must exist a
revocation directive with the same `suppression_id`; missing ones are
re-emitted by a reconciliation publication (same validation path, same
idempotence rules). Publication is denied in `read_only`, so after a crash
that left the barrier on, boot reports the pending reconciliation and waits
for the owner's mode resume — it does not force a write. `doctor` stays
contractually read-only and only *reports* parity status. An unresolvable
mismatch (journal entry whose plan no longer validates against replay)
quarantines fail-closed with an explicit diagnostic.

Read-only barrier semantics are otherwise unchanged: no publication
carve-out exists inside `read_only`. The journal (already durable) is the
serving gate of record in the window between steps 2 and 4.

### 6.7 Revoked-identity view (the single serving gate)

One component owns the derived set of revoked identities: the storage
administration service. The **revoked-identity view** is the union of:

- identities parsed from typed suppression journal entries (available
  immediately at apply, before any publication), and
- identities derived from `revocation_directive` records in the replay
  state (once the enforcement publication lands).

Mechanics:

- Single owner, derived view — this is not "N paths parsing the journal"
  (the rejected shallow alternative): each serving path receives one typed,
  injected view; none parses control files.
- Refresh points: journal write (apply), boot/reconciliation, and restore
  re-apply. Reads are plain file/record reads — no control fence or lock is
  taken inside partition transactions (journal writes are atomic-rename,
  0o600).
- Injection at composition roots: retrieval runtime, scoped-context
  assembler, structured fact reads, provider prefetch assembly, graph
  observation runtime, entity matching, identity-lineage serving view, and
  the memory-plane query surface. Absence of the view at any of these roots
  is a composition error that fails closed (empty view is valid and means
  "nothing revoked"; a *missing* view component is not constructible).
- The view applies at **host/operator-serving endpoints only**. Internal
  integrity readers that share the same read APIs (the atomic store's
  recovery-authority reads, replay reconstruction) must NOT be filtered —
  filtering them would strip integrity-retained records and break the
  persisted-equals-genesis invariant (§6.2.2 governs which projections
  retain).
- After the enforcement publication, replay-projection exclusion and
  tombstones carry the effect; the view remains as defense-in-depth and as
  the in-window authority.

### 6.8 Serving-path enforcement matrix

Every path that returns semantic or runtime content to a host, agent, or
operator consults revocation. Mechanism per path:

| Serving path | Enforcement mechanism |
| --- | --- |
| graph observation (`observe_graph`) | replay projection exclusion (6.2) + revoked-identity view |
| identity-lineage serving view | revoked-identity view applied to the host-grant-backed read; the complete retained audit is served only by the operator forensic surface — a governance-operator method (same surface family as `read_export`) requiring `OwnerCapability`, returning the retained lineage for explicitly named coordinates (R16) |
| entity matching (`current_semantic_entity_matches`) | revoked-identity view check at the reader (the integrity snapshot it reads retains revoked records by design, 6.2.2) |
| retrieval / evolution decision | tombstone lifecycle (6.3) + revoked-identity view at claim-reader eligibility |
| prefetch (evolution channel) | same as retrieval |
| prefetch (canonical channel) | assembly-time exclusion keyed on the revoked-identity view (`RUNTIME_CONTEXT` is a visibility attribute, not a lifecycle-bearing kind; tombstones do not apply here) |
| scoped context activation | tombstones + eligibility closures reject revoked and revoked-source-derived records |
| structured fact reads | tombstone lifecycle never-eligible; excluded from context items |
| runtime-step retrieval | tombstones; revoked records never enter `available_evidence_ids` |
| harness envelope / sidecar | justification revalidation marking (6.5) |
| resume envelope / checkpoints | same marking, embedded |
| operator export | existing suppression filter, extended to the new enumeration |
| operator inspection/explain surfaces (task, solver, explain) | revoked task-id set from the revoked-identity view (the export mechanism, extended); no revoked-derived task state is returned |
| memory-plane query surface | **every record-query endpoint without exception — filtered scan, pagination, record lookup, cursors, and any neighborhood/evidence/catalog-history query variants — consults the revoked-identity view before returning rows or cursors** (governing line 109); the filter applies pre-slice inside the read transaction so pages and cursors stay exact; these endpoints return no totals, so count arithmetic does not apply here |
| legacy graph queries (`query_graph` family) | tombstones + revoked-identity view (these also serve retrieval-runtime and scoped-context internals, which are covered above) |
| derived semantic index projection | projection excludes revoked identities (no production reader today; kept consistent for future readers) |
| learned-ontology coverage/index | revoked-source evidence ineligible; existing `revoked` replay outcome reused |

The **parity acceptance test** (§10) proves all paths agree.

### 6.9 Eligibility epoch: pending increments ride publication

**Problem.** Tier A requires the finalized signed tuple's epoch to equal
control state's epoch at every verified read. A control-only bump (what the
governing sentence literally prescribed) breaks every verified read until
some later publication happens to realign — recorded as the DUR-09 open
item.

**Contract.** `InstallationControlState` gains
`pending_epoch_increments: int = Field(ge=0) = 0`.

- Forget apply (and any future revocation-family operation) increments the
  pending counter under the barrier; `eligibility_epoch` itself is
  untouched, so Tier A keeps passing throughout.
- Publication prepare computes `effective_epoch = eligibility_epoch +
  pending_epoch_increments` and signs it into the tuple (both publication
  paths; the existing prepare-time control read is the consumption point).
- Publication finalize advances control state to
  `eligibility_epoch = effective_epoch`, **decrements**
  `pending_epoch_increments` by the increments this tuple consumed
  (`effective_epoch − old eligibility_epoch` — never an unconditional
  clear, so a crash-recovered earlier intent cannot consume a later
  forget's pending increment), and journals the transition inside
  `publication_finalized` (digests carry old/new epoch). **This is a new
  control-state write at finalization** — no finalize path writes control
  state today — so the control write API is extended such that the
  publication tuple, the epoch advance, and the pending decrement commit
  in **one control transaction**; `resolve_pending_publication` (crash
  recovery) is an additional finalize site and applies the same advance
  idempotently.
- Boot completion rule: if `pending_epoch_increments > 0` and the finalized
  tuple's epoch equals `eligibility_epoch + pending_epoch_increments`, boot
  completes the advance idempotently and journals it — closing the
  crash-between-tuple-write-and-control-write window that would otherwise
  wedge Tier A.
- The enforcement publication of a forget is itself a publication, so a
  normal forget finalizes its own epoch increment — no waiting for
  unrelated traffic.

**Window semantics (honest statement).** Between journal write and epoch
finalization, caches keyed to the old epoch are not yet invalidated by
epoch. Correctness in that window is carried by the serve-time
revoked-identity view (§6.7), which every serving path consults; the epoch
is the cache-invalidation and fencing hammer, not the correctness
mechanism. Content already rendered into a host conversation before apply
cannot be retracted by Memorii — recorded limitation, disclosed by the
plan.

### 6.10 Schema, codec, publication, and authoring authority chain

Implementation must regenerate, in order (the design's authority-chain
ledger):

1. **Governance-owned publication entry**: an administration-side function
   that constructs the `SemanticGraphDelta` directly (the native
   group-commit path is the precedent, `atomic_store.py:16582+`), carrying
   the `revocation_directive` record and the tombstone record versions
   under an owner-capability + `suppression_id` + `plan_digest` authority
   binding; it reuses `build_semantic_memory_event_batch`
   (`event_replay.py:946-1018`) and the replay-state
   `RecordDigestPrecondition` CAS (`atomic_store.py:16676-16701`). It is
   enrolled as a canonical writer (`service.py:523-527`) with its
   `operation_binding`, and respects the store's freeze guard
   (`atomic_store.py:8626-8640`); the entry also constructs the
   store-level `OperationFenceBinding` and `SemanticWriterCommitBinding`
   (writer epoch) that `prepare_semantic_event_batch` requires
   (`atomic_store.py:12346-12356`) — the governance authority binding is
   additional, not a replacement. No ingestion `OperationKind` member is
   added — governance is not an ingestion operation.
2. `GraphRecordKind` closed union + `RevocationDirectiveRecord` model +
   the four per-kind tables — canonical owner `graph_records.py` /
   `event_replay.py` as verified in §4; collapse the duplicate union
   declaration to one owner.
3. `canonical_graph_codec_manifest()` — new entry; totality validator
   enforces coverage; the snapshot's `codec_by_kind` lookup gains a typed
   failure for a missing entry; `manifest_fingerprint` change flows into
   read sets and snapshots.
4. `generated_reference_schema_manifest` — declare the directive's target
   reference edges; `advance_reference_integrity`/`extract_reference_edges`
   learn the kind.
5. Event envelope schema: mint `memorii.semantic-memory-event.v2` (current
   write), demote v1 to deprecated-readable with an identity upcaster
   (v0→v1 pattern), registry history stays monotonic; new batches pin the
   new registry revision.
6. Typed-value publication regeneration via
   `memorii/scripts/generate_observation_registry_publication.py`
   (production authoring path only; never hand-edit signed manifests).
7. Release-preparation `candidate.json` repin for every touched production
   file.
8. Lifecycle enums: `ClaimLifecycleState.revoked`,
   entity-link/`RecordLifecycleState` members per the §6.3 reader-edit
   ledger; `ForgetPlan`/`ForgetReceipt` upgraded contracts.
9. Control contracts: `pending_epoch_increments` field; the one-transaction
   finalize control write; journal v2 envelope reader.
10. Verification: codec/manifest tests, registry monotonicity tests,
    publication digest checks, identity-hygiene gate (including a row
    proving `logical_entity_id` minting stays content-free).

## 7. Failure And Operational Analysis

| Cut / scenario | Required behavior |
| --- | --- |
| crash after journal, before enforcement publication | serving stays gated by the revoked-identity view (journal half) the entire time; after barrier release, the boot resume hook reconciles and re-emits the directive (6.6); if the barrier was left on, boot reports and waits for owner mode resume — it never force-publishes in `read_only` |
| crash mid-enforcement publication | existing publication intent protocol resolves (exact-old abort / exact-new finalize / else quarantine); journal unchanged; after a clean exact-old abort in a live process, the mode-resume drain retries the directive — it is never stranded until restart |
| crash between tuple write (epoch advanced) and control write | one-transaction finalize makes the cut impossible in the new path; for legacy states, the boot completion rule advances idempotently and journals (6.9); test family covers the cut |
| forget apply retried with same plan | `plan_digest` lookup reuses the `suppression_id`; idempotent steps only; receipt recomputed with no double count |
| different forget overlaps earlier one | directives union; receipt counts only newly-revoked targets; never an integrity conflict |
| plan/apply drift (target changed between) | conflict, no partial application; replan |
| plan matches nothing | `invalid_request` refusal (fail-closed, as today) |
| concurrent host writes during plan | closure computed under one consistent snapshot (single partition read transaction over the replay snapshot and readers); the apply-time drift check is the fence |
| concurrent ingestion after apply | new dependents on revoked identities are excluded by identity-set gating (6.2.3), never served |
| restore of an older backup | journals travel with boot (existing); reconciliation appends missing directives into the restored log (`suppression_id` stability makes matching rename-proof); mismatch quarantines |
| journal file tampered/unknown version (v0/v3+) | decode fails closed; doctor reports; serving does not silently un-suppress |
| old binary reads new log | strict decode rejects unknown record kind / lifecycle value — refuses rather than serves; verified at Level 2 via strict-decode proxy tests (synthetic unknown values), true old-binary evidence is a recorded Level 3 deferral |
| operator error (wrong scope) | no un-forget: revocation is irreversible into re-serving; content re-enters only via new validated ingestion; the plan preview, typed selectors, and counts are the mitigation |
| read-only barrier held during apply | unchanged semantics; enforcement publication sequenced after owner release by design |
| epoch pending but no publication ever follows | Tier A unaffected; caches eventually stale — doctor reports pending increments; correctness still carried by the revoked-identity view |

Observability: `doctor` gains — journal↔directive parity status, pending
epoch increments, revoked-identity counts by class, last reconciliation
result; it remains read-only. `status` surfaces pending epoch increments
and (owner-visible) revoked-identity counts. All diagnostics are
content-free. The integrity snapshot's `exact_record_counts_by_kind`
(`atomic_store.py:11732-11736`) will expose a directive *count* on
owner/operator surfaces — disclosed here as accepted (a count, not
content).

## 8. Security And Privacy Analysis

- Owner-only issuance: `OwnerCapability` at plan and apply; model tools and
  host adapters cannot mint either (governing line 325 unchanged). The
  governance layer enforces this; the store itself checks writer
  enrollment, so the capability check must occur in the governance entry
  before the delta is constructed. Negative tests are part of R6.
- Content-free identifiers everywhere a revoked identity crosses a
  persisted or logged surface: opaque coordinates, digests,
  installation-keyed suppression ids. No titles, per-record text, aliases
  as written, or evidence spans in directives, journals, receipts, or
  diagnostics.
- No cross-path disclosure: the parity test asserts the *absence* of the
  revoked identity's coordinates and digests across every serving path,
  including counts (a count of revoked records is itself only the plan/
  receipt/doctor surface, which is owner-visible by design; the integrity
  snapshot's directive count is disclosed in §7).
- Host-grant-backed reads of integrity-retaining projections (identity
  lineage) apply the revoked-identity view; the complete retained view is
  owner-capability-forensic only (R16) — closing the gap that the current
  grant-backed audit surface would otherwise serve revoked literal text.
- History confidentiality at rest remains the documented encrypted-volume /
  owner-permissions story (governing line 355); this design changes
  *serving*, not at-rest encryption.
- Fail-closed everywhere: unknown journal versions, unknown lifecycle
  members, unknown record kinds, registry mismatches, reconciliation
  failures — refuse and diagnose, never serve.

## 9. Non-Goals

- Selective physical record erasure (v1: whole-partition only, per
  governing doc).
- Rewriting signed semantic history, backups, or audit bytes.
- Retracting content already delivered into a host conversation.
- Cross-installation revocation propagation.
- Model- or host-initiated forgetting, or free-text/model-driven scope
  resolution for plans.
- Retention-tier semantics changes (age never removes revocation state —
  unchanged).
- Performance budgets and adversarial tamper/spoof matrices beyond
  fail-closed decode (recorded Level 3 deferrals).

## 10. Verification Strategy

Deterministic (unit/integration):

1. **Cross-path parity test (canonical acceptance)** — a family with one
   shared seeded fixture, jointly satisfying R11: seed an installation with
   at least one instance of every closure class (§6.4 classes 1-7,
   including legacy `graph_node`/`graph_edge` records and ontology
   evidence); forget plan → apply → enforcement publication → restart →
   assert for **every** path in the §6.8 matrix:
   - **absence oracle, mechanically defined**: page every cursor-returning
     path to exhaustion (no page may contain the revoked coordinates);
     scan the *serialized* response of each path — the JSON the host would
     receive, produced by that surface's own encoder — for the revoked
     identities' coordinates and digests (owner-only surfaces — plan,
     receipt, doctor, forensic — are out of scope for the no-disclosure
     scan by design); and check **per-path** count arithmetic: the fixture
     derives an expected-delta table (which revoked records each path
     served before), and each count-bearing endpoint (export, status,
     integrity snapshot) must satisfy `count_after == count_before −
     expected_delta_for_this_path` — catching both leaks and
     count-disclosure;
   - envelope marks `revalidation_required`;
   - export omits; journal and directive agree on `suppression_id`;
   - replay state still equals genesis reconstruction;
   - in-window assertion: after journal write and *before* the enforcement
     publication, the same oracle holds (the revoked-identity view carries
     correctness in the window);
   - barrier sequencing: while read-only, journal present and serving
     gated; the directive appears only after release.
2. Replay-equivalence: directive in the log; persisted state == genesis
   fold; older-batch replay with v1 events + v2 batch succeeds via
   upcaster; duplicate directive handling; divergent same-`suppression_id`
   targets conflict; overlapping different-`suppression_id` directives
   union.
3. Crash-cut family: journal-without-directive → reconciliation emits
   (after mode resume; boot-with-barrier reports without force-publishing);
   mid-publication cuts resolve via intent protocol; crash between tuple
   and control write → boot completion rule; restore-old-backup → reapply +
   reconcile; tampered journal and unknown `journal_version` (v0/v3)
   rejected fail-closed; registry-mismatch fail-closed (route for the §8
   claim).
4. Epoch window: apply → Tier A still passes; the enforcement publication
   embeds effective epoch; finalize advances and clears pending
   (one-transaction control write); doctor reports pending increments.
5. Closure correctness: mixed-source conclusion becomes ineligible (no
   citation-dropping survival); post-directive dependent excluded;
   plan/apply drift conflict with zero partial application; empty-plan
   refusal; unknown enum/kind values rejected by every strict reader
   (strict-decode proxy for the old-binary row).
6. Authorization negatives: forged and host-derived capabilities refused at
   plan and at apply; no host tool can mint a directive; owner-only
   forensic audit access enforced on the lineage surface.
7. Identity-hygiene gate mutations on the new surfaces, including a row
   proving `logical_entity_id` minting stays content-free.

CI placement: the parity family and crash-cut family live under
`memorii/tests/integration/` and join `durable-storage-integration` and
`durable-runtime-integration` (`.github/workflows/pr-gates.yml`) — both
jobs run explicit pytest file lists, so implementation must add the new
test paths to those lists; any unit-tier addition elsewhere must instead be
registered in `tests/ci/unit-shards.json` (the `unit-test-shards` job
verifies that config). No gate weakening, no new gate for what an existing
job can own. Live/operational evidence (real owner journey on the owner's
install) is separately recorded, never claimed from deterministic runs.

## 11. Alternatives Considered

1. **Per-path read filters over the suppression journal** (the shallow
   fix): rejected — N serving paths × journal parsing, no replay authority,
   leaves revocation invisible to deterministic reconstruction, and the
   journal's untyped shape leaks into every reader. Root-cause rule: one
   authority (the revoked-identity view + replay directives), derived
   views. The §6.7 view is the corrected form of what this alternative
   gestured at: one typed derived component, not N parsers.
2. **A `revoke` MutationKind that removes records in the fold**: rejected —
   violates the never-remove fold discipline and event_model.md 7.3, and
   makes genesis reconstruction lose the revocation itself.
3. **Reuse correction machinery (lifecycle `retired`/`invalidated`,
   retraction transitions) for forgetting**: rejected — conflates belief
   revision with release suspension (the governing four-operation
   separation), lets non-owner flows issue it, and leaves no audit distinct
   from ordinary corrections. Verified during review: the existing reader
   styles would also *serve* revoked content (`retrieval.py:296-300` serves
   superseded/invalidated as context), confirming aliasing is unsafe.
4. **Control-plane journal as the only authority, replay consults control
   at projection**: rejected — couples partition replay to control state,
   breaking batch-log self-containment and restore reasoning.
5. **Publication carve-out inside the read-only barrier**: rejected —
   weakens the universal no-writes barrier contract every other component
   relies on; sequencing enforcement after owner release with journal-first
   durability achieves the same guarantee.
6. **Epoch bump at apply with a Tier A tolerance window**: rejected — every
   verified read fails until the next publication; the pending counter
   preserves Tier A continuously.
7. **Free-text scope resolution for plans** (worked example's surface
   temptation): rejected — requires model-driven matching on content the
   system must no longer even serve; typed selectors only.

## 12. Requirements Ledger

| ID | Requirement | Source | Priority | Acceptance criteria | Status |
| --- | --- | --- | --- | --- | --- |
| FGT-R1 | Revocation directive is a closed, typed, content-free record kind in the append-only semantic log | governing 353/355; event_model 7.3 | P1 | strict model rejects unknown fields/enums; directive field set is exactly §6.1's enumeration with digest/coordinate-shaped values; fold materializes it without removing anything | specified |
| FGT-R2 | Revoked-identity view derived from directives ∪ journal gates every replay-fed serving projection | governing 353 | P1 | observation streams, claim projections, entity matching (view check, not lifecycle), lineage serving view exclude revoked identities incl. post-directive dependents; integrity projections retain; host-grant lineage reads excluded, owner-forensic only; view composition fails closed (a serving root without the view is not constructible; internal integrity readers unfiltered) | specified |
| FGT-R3 | Evolution-record plane tombstones make revoked records never-eligible | governing 353 | P1 | `revoked` lifecycle members + the §6.3 reader-edit ledger applied (denylist→allowlist, conversion, projection map, context exclusions); retrieval/prefetch/scoped-context/structured/runtime-step exclude — absence, not crash; old binaries fail closed (strict-decode proxy at Level 2) | specified |
| FGT-R4 | Solver justifications citing revoked evidence become revalidation_required | governing 353 | P1 | envelope + resume + checkpoint marking `justification_id:revoked_evidence`; nothing deleted | specified |
| FGT-R5 | forget plan takes typed selectors and computes content-free dependency closure with plan_digest | governing 353 | P1 | closed selector union (no free-text matching); closure classes 1-7 enumerated under one consistent snapshot; empty plan refused; drift conflict at apply; counts owner-visible only; an existing export/operator surface verifiably exposes the selector coordinates for un-revoked content | specified |
| FGT-R6 | apply is journal-first, barrier-gated, owner-only, idempotent | governing 353/325 | P1 | typed v2 journal envelope (v1 legacy accepted, v0/v3+ rejected); durably complete at journal write; retry by `plan_digest` reuses `suppression_id`, no double count; same `suppression_id` with divergent targets conflicts; different `suppression_id` overlapping targets unions with receipt counting newly-revoked only; forged/host capabilities refused at plan and apply | specified |
| FGT-R7 | Enforcement publication appends the directive + tombstones via the governance-owned entry with full validation | AGENTS invariants | P1 | governance entry constructs the delta under owner authority; CAS on replay state; writer enrolled with operation binding; no model-authored content; concurrent-update CAS conflict aborts cleanly | specified |
| FGT-R8 | Boot-resume reconciliation guarantees journal↔directive parity; doctor reports only | governing 335 | P1 | missing directives re-emitted after mode resume; barrier-on crash → report, no force-publish; unresolvable mismatch quarantines fail-closed with a diagnostic observable | specified |
| FGT-R9 | Epoch increments ride publications via pending counter; Tier A never breaks | DUR-09 open item | P1 | pending field; effective epoch signed at prepare; one-transaction finalize advances+clears; `resolve_pending_publication` repeats idempotently; boot completion rule; Tier A green sampled at apply-point, post-publication, and post-restart | specified |
| FGT-R10 | Restore re-applies revocation, including older backups | governing 335 | P1 | restore + reconcile leaves no servable revoked identity (parity oracle on a pre-forget backup); `suppression_id` stability under copy/restore | specified |
| FGT-R11 | Cross-path parity acceptance family | this design | P1 | §10.1 family (shared fixture, all §6.8 paths, exhaustion+serialized-scan+count oracle, in-window assertion, restart, export) green in the two named durable CI jobs | specified |
| FGT-R12 | Schema/codec/publication authority chain regenerated end to end | IMPLEMENTATION_RULES | P1 | per-kind tables extended (unions, carrier tuple, identity map); codec manifest total with typed failure; registry v2 + identity upcaster; publication regenerated via authoring path; candidate repinned | specified |
| FGT-R13 | Mixed-source conclusions never survive by dropping a citation | governing 353 | P2 | ineligible-as-is; re-entry only via new validated operation; deterministic test | specified |
| FGT-R14 | Operator receipt and diagnostics disclose retained bytes; content-free everywhere | governing 355 | P2 | receipt fields enumerated: newly-revoked counts per class, retained-bytes disclosure, enforcement pending/done, `suppression_id`; doctor additions content-free; directive count in integrity snapshot disclosed | specified |
| FGT-R15 | Ontology evidence from revoked sources ineligible | governing 353 | P2 | coverage/index exclude; existing `revoked` outcome reused | specified |
| FGT-R16 | Complete retained audit is owner-forensic only; host-grant reads are revoked-excluded | governing 353 (owner forensic path) | P2 | host-grant lineage reads: revoked-excluded (deterministic assertion, not "denied or"); operator forensic surface: requires `OwnerCapability`, serves retained lineage for named coordinates, refuses without capability | specified |
| FGT-R17 | Revocation is irreversible into re-serving (no un-forget) | this design §5 | P2 | probe set: the §10.1 parity oracle holds indefinitely after apply (incl. post-restart), and no un-forget entry point exists on the governance/public API surface (deterministic surface introspection); re-ingestion of the same facts creates new claim identities that are not suppressed | specified |

Evidence maturity: all requirements `specified` (this document). Derived
artifacts (governance publication entry, codec manifest entries, registry
v2, control finalize write) are `derivable` from §6.10. The memory-plane
version-rewrite mechanism underlying R3 is verified against current code
(`partition.py:890-933`, `factory.py:101-141`). Implementation,
verification, and CI states belong to the implementation WorkPlan.

## 13. Open Questions And External Decisions

None blocking. Recorded for implementation judgment (bounded, no semantic
choice hidden): the hash construction for `suppression_id` (input set is
fixed in §6.1; the function is detail); whether `status` exposes
revoked-identity counts — default yes (owner-visible only).

## 14. Amendment To The Governing Design

In `docs/design/durable_execution_and_solver_runtime.md`, §"Forgetting,
erasure and retention", the original sentence "`forget apply` durably
writes content-free suppression identifiers and increments control epoch
under the barrier before acknowledging; invalidate cached/paged views and
fence work using affected sources." was replaced (exact applied text) by:

> `forget apply` durably writes content-free suppression identifiers and
> records a pending eligibility-epoch increment under the barrier before
> acknowledging; the increment becomes the signed tuple's epoch with the
> enforcement (or next) publication, and serve-time forget-policy checks —
> not the epoch — carry correctness in between; invalidate cached/paged
> views and fence work using affected sources. (Epoch contract amended by
> `docs/design/semantic_forgetting.md`.)

Applied by this design operation; see
`docs/work/semantic-forgetting-design/design.plan.md`.
