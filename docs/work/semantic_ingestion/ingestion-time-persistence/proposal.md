# Atomic Ingestion-Time Attestation Binding

Status: implementation-ready design under the owner-approved direction of
2026-09-11 (owner-decision.md: Option 1 — store-persisted seals minted at
admission/group-commit CAS under the protected clock; typed denial for
legacy/unsealed cohorts; per-source-retention plus per-group-commit
granularity; external trusted time permanently excluded from the production
write path). Every contract below cites the production code it changes. No
canonical, registry, or production bytes have changed yet; feasibility proof
on the real backend precedes implementation (see Implementation Milestones).

Public objective: make `ProviderMemoryService.observe_ingestion_time_attestations`
(memorii/core/provider/service.py:669-681) return real pages. The public wire
is byte-frozen: `SourceRetentionTimeAttestation` /
`TransactionGroupCommitTimeAttestation`
(graph_ingestion_time_contracts.py:24-63), the request/cursor/page models
(graph_observation_public_contracts.py:111-124, 127-170, 338-374), and the
response union (graph_observation_public_contracts.py:381-384). Only the
persisted producer is missing; today `ingestion_time_input` fails closed
(graph_observation_materialization.py:193-202).

## Seal-Minting Entry Points (readiness finding: publish_admitted_source
enumeration)

Complete enumeration of write paths that can admit a source or commit a
group, and their seal rule:

| Entry point | Production callers | Mints a seal? |
| --- | --- | --- |
| `SemanticIngestionAtomicStore.publish_admitted_source` (atomic_store.py:2182-2253) | Both provider admission paths: metadata-poor (provider/ingestion.py:301-314) and full (provider/ingestion.py:491-515), both via `_admit_with_writer_retry` (provider/ingestion.py:847-858) | Yes — one source-retention seal per admission CAS, always |
| `SemanticIngestionAtomicStore.admit_source` (atomic_store.py:2352-2417) | No production caller today; tests/fixtures (tests/unit/core/semantic_ingestion/test_semantic_generation_transactions.py:799, tests/integration/test_semantic_ingestion_process_safety.py:134, tests/fixtures/semantic_ingestion/semantic_terminal_fixture.py:598) | Yes — identical seal rule; the combined records+generation CAS (atomic_store.py:2396-2406) includes the seal member |
| `GovernedSourceAdmissionService.admit` (admission.py:89-212) | None found; guarded to raise once a writer admission exists (admission.py:105-106) | No — the pre-atomic unit-of-work path never mints; its writes are legacy cohorts and are denied by the reader rule below |
| `commit_or_reload_bootstrap_graph_group_v3` (atomic_store.py:12628-13390) | Bootstrap graph coordinator | Yes, one group-commit seal, exactly when the winning CAS constructs a committed schema-3 core; noncommitting results carry an explicit null field; the reload branch (atomic_store.py:12681-12683) and every CAS loser (atomic_store.py:13372-13384) mint nothing |
| `reload_exact_bootstrap_graph_group_v3` (atomic_store.py:13392-13417) | Recovery paths | No — reload returns original artifacts only |
| `finalize_source` (atomic_store.py:13470+) and terminal preparation (bootstrap_graph_terminal_preparation.py:432-450) | Terminal pass (provider/ingestion.py:545-639) | No new seal — the terminal binds back to the admission seal via the schema-2 field below |
| `bootstrap_writer_handoff`, `persist_terminal_group`, `reconcile` (provider/ingestion.py:672-709) | Writer/lease/recovery boundaries | No — no admission or group CAS occurs there |

`publish_admitted_source` and `admit_source` must mint under the same rule so
the store contract does not depend on which admission entry point a host uses.
The current production discrepancy (only `publish_admitted_source` is called,
before handoff) is preserved and made explicit: the seal belongs to the
admission CAS, which exists before writer handoff, matching SIA 24679's
bootstrap admission without writer binding.

## Admission Anchor Contract (readiness finding: admission anchoring before a
terminal exists)

The admission-time immutable anchor is the pair written in one admission CAS:

1. The retained source record itself: the `CanonicalMemoryRecord` built by
   `build_admitted_source_record` (source_admission.py:654-692; memory_id
   `semantic_ingestion:source:{delivery_key_digest}`, provider/ingestion.py:392),
   committed verbatim in `prepared.records` (admission.py:280).
2. A new immutable seal-member execution record with memory_id
   `semantic_ingestion:admission:{delivery_key_digest}:retention_attestation`
   (the admission-evidence family convention of admission.py:550-551, 598-607),
   source_kind `semantic_ingestion_source_retention_attestation`, domain
   EXECUTION, visibility INTERNAL_CONTROL, content exactly
   `{"semantic_ingestion_kind": "source_retention_attestation", "artifact":
   <registered canonical bytes>}` — the member-record shape already used for
   bootstrap graph audit members (atomic_store.py:13233-13240) and preplanning
   artifacts (atomic_store.py:16965-16981).

The seal-member artifact is one `SourceRetentionTimeAttestation`
(graph_ingestion_time_contracts.py:24-38) with fields bound as:

- `attestation_id` = the member memory_id above.
- `source_id`, `operation_fence_id` = the `OperationFenceBinding` minted by
  `prepare_atomic` (admission.py:238-241); the fence digest excludes any time
  value, so the anchor is stable across the clock fix.
- `retained_at` = the single protected-clock sample that is also the retained
  record timestamp (source_admission.py:689) — see the clock contract below.
- `graph_revision` = `semantic_replay_state().graph_revision` sampled at seal
  construction inside the same admission call (the same source
  `admit_source` already reads for its control, atomic_store.py:2391). It is a
  descriptive binding: readers validate it only against the sealed artifact,
  never against live state; there is no CAS precondition on it in
  `publish_admitted_source`.
- `clock_identity` = the protected clock identity (below).
- `source_record_digest` = `record_digest(retained_source)` (memory_plane/store.py:817-819)
  over the exact committed record — NOT `source_admission_source_digest`
  (admission.py:473-484), which deliberately excludes the retention timestamp
  and identifies the logical source for retry. The two digests are not
  interchangeable.
- `attestation_digest` = registered self-digest under the existing profile
  domain `memorii.semantic_ingestion.observation.SourceRetentionTimeAttestation.v1`,
  preimage = all fields except `attestation_digest`. No bespoke trailing-NUL
  domain is introduced.

The seal member joins the same `conditionally_write_records` CAS as the five
prepared admission records, with `RecordAbsentPrecondition` on itself
(atomic_store.py:2232-2242 for `publish_admitted_source`; 2396-2406 for
`admit_source`). Retry exactness reuses `_same_admission_record`
(atomic_store.py:16999-17006) extended to the member: on redelivery the member
must exist and match byte-for-byte — a mismatched or partial member is the
existing `PreplanningStoreError("atomic admission evidence is partial or
mismatched")`.

How the later terminal binds back, without cycles: the terminal core
`CanonicalSourceTerminalOutcomeCore` (graph_effect_contracts.py:139-179) is
constructed much later in terminal preparation
(bootstrap_graph_terminal_preparation.py:432-446) and already carries
`source_id`, `source_digest` (the same step-one source digest), and
`operation_fence_id` from host authority. Schema 2 adds exactly
`source_retention_attestation_digest: Digest` (non-null required), whose value
is the admission seal artifact's `attestation_digest`. The dependency edge is
one-directional — admission seal (t0) -> terminal core schema 2 (t1) ->
outcome_id -> source_result_digest -> record_digest — because the seal's
preimage contains no terminal field. The seal is never recomputed at
terminal time. `SourceFinalizationObservationDelta`
(graph_effect_contracts.py:576-619) embeds the completed record and is the
reader's resolution entry: finalization delta -> source_outcome
(schema 2) -> `source_retention_attestation_digest` -> member memory_id ->
registered artifact -> validate `attestation.source_record_digest ==
record_digest(retained source record read from the same snapshot)` and fence
identity equality. An admission member with no schema-2 terminal binding is
evidence but not cohort-reachable (matching owner-decision.md Compatibility).

## Protected Clock And Redelivery Contract (readiness finding: protected
clock at raw-source construction)

New closed contract `IngestionTimeClock` (no production class exists today;
`IngestionTimeClock` appears nowhere in memorii/memorii):

- `identity: Identifier` — a stable protected configuration identifier
  (not a caller string, not a hostname guess).
- `now_utc() -> datetime` — timezone-aware UTC only; non-UTC and naive values
  raise.
- Strict, frozen, extra-forbidden, mirroring the closed wire contracts
  (graph_ingestion_time_contracts.py:20-22).

Routing — one authority, three injection points:

1. Provider raw-source construction: `ProviderIngestionService` currently
   defaults `now_provider` to `datetime.now(UTC)` (provider/ingestion.py:245,
   256). The constructor takes a required `IngestionTimeClock` (no ambient
   default; factory wiring at provider/factory.py:113-132). At
   `_ingest_semantic_source`, the line `retained_at = delivery_event.timestamp`
   (provider/ingestion.py:396, with its caller-time comment at 393-395) is
   replaced by one sample `retained_at = clock.now_utc()`; that single sample
   supplies, unchanged in one value: the retained record timestamp
   (source_admission.py:689), and both `received_at` and `retained_at` to
   `derive_source_governance_material` (provider/ingestion.py:403-410;
   source_governance.py:130-148 requires `retained_at >= received_at`, which
   one equal sample satisfies). The caller event timestamp remains delivery
   identity (it still feeds `DeliveryIdentity.create`,
   provider/ingestion.py:291) but is no longer authenticated as server
   retention time.
2. The metadata-poor path (provider/ingestion.py:301-314) constructs its
   source via `_governed_source` (provider/ingestion.py:1638-1668), copying
   the event-timestamped raw record; it must stamp the same protected sample
   as the copied record's `timestamp` (which also fixes the admission index
   timestamp, admission.py:578) before `prepare_atomic`, because it flows
   through the same admission CAS and mints the same seal.
3. The atomic store: `SemanticIngestionAtomicStore.__init__` takes the same
   clock instance as its `now_provider` (atomic_store.py:1080), so the group
   CAS instants and lease arithmetic share one authority.

Redelivery rule (exact reuse of the winner's retained material): the provider
must attempt authorized retained-source recovery BEFORE re-deriving material
with a fresh clock sample. On redelivery, after authenticated ingress, the
provider reads the admission index (`semantic_ingestion:admission:{delivery_key_digest}`,
admission.py:550-551); if the retained source and seal member exist, it reuses
the winner's retained record, governance/step-one material, and seal artifact
bytes verbatim and returns the recovered admission — it never re-samples time
and never relabels a new sample as the winner. Fresh derivation with a new
clock sample is permitted only when no retained record exists. This is
required, not optional: a re-sampled `retained_at` changes the governance
material and `step_one_material_ctv` bytes inside the record content
(source_admission.py:669-685), so `_same_admission_record`
(atomic_store.py:16999-17006, which ignores only the top-level record
timestamp) would correctly reject the re-derived attempt as "not an exact
committed retry"; recovery-before-derivation is the only path that preserves
exact redelivery. `_admit_with_writer_retry` (provider/ingestion.py:847-858)
continues to retry only its one typed writer mismatch; it is not a clock
retry. `GovernedSourceAdmissionService.lookup` (admission.py:312-405) is the
authorization pattern but is not an API that returns original material; the
new recovery seam must be a purpose-built authorized source-replay accessor
that validates principal, delivery key, tenant, and stored scope set before
returning bytes, and must not reuse an outcome lookup as an unchecked
source-byte accessor.

Legacy records keep their original caller-time bytes and never receive a
synthetic server-time seal (confirmed production gap recorded against SIA
4.1.5; see Provider Clock Discovery below).

## Group Seal And Acyclic Batch Binding (readiness finding: acyclic
committed_batch_digest)

Verified against production: `committed_batch_digest` is
`SemanticMemoryEventBatch.source_event_batch_digest` (event_replay.py:427-429)
of the canonical event batch built inside the winning group CAS
(`build_semantic_memory_event_batch`, atomic_store.py:12966-12980) and
persisted as the batch record `_semantic_event_batch_record(...)` in the same
CAS (atomic_store.py:13016-13022). The batch's own digest preimage is exactly
its fields minus the digest itself (event_replay.py:457-461): repository_id,
log_position, source_id, transaction_group_id, operation_fence_id, writer_epoch,
event_schema_registry_revision, event_schema_registry_digest, graph_delta_digest,
events — none of which reference the group result, the seal, or any later
artifact. `source_event_batch_digest` equals `event_batch_digest` on fresh
creation (event_replay.py:1018; private attr defaults to None,
event_replay.py:425) and preserves the original persisted digest across
reader upcasts (decode verifies the supplied digest over the original payload
at event_replay.py:1144-1148 and retains it at 1181-1187). Therefore the
proposed dependency order inside `write()`:

    canonical graph delta (atomic_store.py:12945-12964)
      -> canonical event batch (12966-12980; committed_batch_digest source)
      -> group time attestation (new; binds batch + delta + instants + clock)
      -> versioned result core (13245-13257; schema 3 binds attestation digest)
      -> receipt (13258-13266; binds core_digest)
      -> result (13267)
      -> ledger entry (13275-13291; binds result_digest)

is acyclic. The physical store batch checksum and `atomic_write_digest`
(atomic_store.py:13241-13244, a digest of request_ctv_digest and generation
only) are not substitutes: the former would create the cycle, the latter
binds no batch.

Exact group seal field bindings, all sampled/derived inside the winning CAS
construction:

- `attestation_id` = group member memory_id `{primary_id}:group_commit_attestation`
  (the `primary_id + ":suffix"` member convention, atomic_store.py:13233-13240).
- `source_id`, `operation_fence_id`, `transaction_group_id` =
  `request.operation_fence_binding.source_id`, `.operation_fence_id`,
  `request.transaction_group_id`.
- `operation_ids` = the core's ordered operation ids
  (contracts.py:11511-11513 ordering), equal to `request.operation_ids`.
- `transaction_started_at` = protected-clock sample at entry to `write()`,
  after the reload discrimination (atomic_store.py:12681-12683) and before any
  effect construction; `transaction_committed_at` = the existing single
  `committed_at = self._now()` sample (atomic_store.py:12796) that already
  supplies PlanningCommitValues, batch, and ledger timestamps. The wire
  contract enforces `committed >= started`
  (graph_ingestion_time_contracts.py:57-63). A CAS retry re-enters `write()`
  (atomic_store.py:13384) and re-samples both; only the winning attempt's
  artifacts persist.
- `graph_revision_before` / `graph_revision_after` = `before_graph` /
  `after_graph` (atomic_store.py:12702, 12788-12791) — equal to the core's
  fields.
- `applied_graph_delta_digest` = `canonical_graph_delta.delta_digest`
  (atomic_store.py:12956-12964).
- `committed_batch_digest` = `canonical_event_batch.source_event_batch_digest`
  as defined above.
- `clock_identity` = the protected clock identity.
- `attestation_digest` = registered self-digest under the existing profile
  domain `memorii.semantic_ingestion.observation.TransactionGroupCommitTimeAttestation.v1`,
  preimage = all fields except `attestation_digest`.

The seal member (shape per Admission Anchor Contract, source_kind
`semantic_ingestion_transaction_group_commit_attestation`) joins `records`
(atomic_store.py:13338-13353) with `RecordAbsentPrecondition`. Only committed
groups have this seal; noncommitting groups have no batch and carry the
explicit null field. The SIA text names the attestation field but does not
state the `source_event_batch_digest` equality; this section is the proposed
normative clarification for design review.

Reload validation (`_reload_bootstrap_graph_group_receipt`) extends, in order:
result digest -> member identity (`{primary_id}:group_commit_attestation` when
core schema 3 and committed) -> registered artifact -> typed attestation ->
equality of transaction_group_id, operation_ids, graph revisions, clock
identity, and `committed_batch_digest` against the persisted batch record
read back from the same image (decode via
`decode_semantic_memory_event_batch`, event_replay.py:1124-1192). Any
mismatch is the existing typed reload error, never a re-mint.

## Persisted Schema Changes And Digest-Chain Coverage (readiness finding:
complete digest-chain coverage)

Exact list of persisted-schema changes the implementation must make:

A. `CanonicalSourceTerminalOutcomeCore` and
   `CanonicalSourceTerminalOutcomeRecord` (graph_effect_contracts.py:139-271)
   each gain:

   ```text
   source_result_schema_version: Literal[1, 2] = 1
   source_retention_attestation_digest: str | None = Field(default=None, pattern=_DIGEST)
   ```

   Preimage rules (the complete existing chain is core -> outcome_id ->
   source_result_digest -> record_digest, graph_effect_contracts.py:205-248):

   - Schema 1 (legacy, byte-exact): both fields are excluded from
     `core_digest`'s preimage (the `model_dump(exclude={"core_digest"})` at
     graph_effect_contracts.py:174-176), from the record body and
     `source_result_digest` preimage (graph_effect_contracts.py:222-241), from
     `record_digest`'s preimage (graph_effect_contracts.py:266-268), and from
     serialization. The `outcome_id` formula
     (graph_effect_contracts.py:211-221) is unchanged — it digests only
     source/fence/preparation fields plus `core_digest`, and a schema-1
     `core_digest` is unchanged because the new fields are excluded from its
     preimage.
   - Schema 2: both fields are included in every preimage above;
     `source_retention_attestation_digest` must be non-null in the core and
     the record and exactly equal between them (the same equality pattern as
     every duplicated field, graph_effect_contracts.py:253-265); the value is
     the admission seal's `attestation_digest`.
   - Mechanism: `_Addressed` (graph_effect_contracts.py:38-49) currently has
     no versioned-exclusion hooks, unlike `_ContentAddressedContract`
     (contracts.py:4217-4273). Add the same three hooks there —
     `_versioned_digest_excluded_fields` (used by digest validation and
     `create`), `_canonical_contract_field_names` (used by CTV lowering,
     contracts.py:137-150), and a wrap serializer that pops the excluded
     fields at schema 1 — defaulting to no-op so every other graph-effect
     contract keeps identical bytes.
   - Nested embeddings need no own change and keep legacy bytes through the
     nested serializer: `BootstrapGraphCanonicalSourceResultInputV3` /
     `BootstrapGraphCanonicalSourceResultV3`
     (bootstrap_graph_terminal_preparation.py:451-471),
     `SourceFinalizationObservationDelta` (graph_effect_contracts.py:576-619),
     `IngestionObservationRecordMutation` (graph_effect_contracts.py:453-480).

B. `BootstrapGraphGroupCommitResultCoreV3` (contracts.py:11454-11545) gains:

   ```text
   group_result_schema_version: Literal[1, 2, 3]   # widened from Literal[1, 2]
   transaction_group_commit_attestation_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
   ```

   - Schema 1 (legacy, byte-exact): the new field joins the existing
     `_legacy_v1_digest_excluded_fields` set (contracts.py:11473-11476), so it
     is excluded from `core_digest` (validation path
     contracts.py:4237-4254 via `_versioned_digest_excluded_fields`,
     contracts.py:11482-11488; creation path contracts.py:4256-4273), from
     canonical field-name selection (contracts.py:11490-11499; CTV lowering
     contracts.py:137-150), and from serialization
     (contracts.py:11501-11507). The existing schema-1 ledger-field
     exclusions are retained exactly.
   - Schema 2 (legacy, byte-exact — this is the exclusion the earlier draft
     missed): `_versioned_digest_excluded_fields` returns
     `{"transaction_group_commit_attestation_digest"}` for version 2, and the
     field-name selection and serializer pop it for version 2 as well.
     Without this, adding the field to the class would silently change every
     existing schema-2 `core_digest` (the class currently excludes nothing at
     version 2, contracts.py:11487). Schema 2 keeps its existing ledger
     fields (contracts.py:11518-11544) and gains no attestation requirement.
   - Schema 3: excludes nothing beyond `core_digest`; requires
     `transaction_group_commit_attestation_digest` non-null exactly when
     `disposition == "committed"` and explicit null when noncommitting
     (validated alongside the existing schema branches, contracts.py:11509-11545);
     retains every schema-2 ledger requirement.
   - `BootstrapGraphAtomicEffectReceiptV3` (contracts.py:11548-11562) and
     `BootstrapGraphGroupCommitResultV3` (contracts.py:11565-11582) gain no
     fields: the receipt already binds `result_core_digest = core.core_digest`
     (validated contracts.py:11572-11582) and the result digest covers the
     nested core, so legacy schema-1/2 bytes are preserved by the nested core
     serializer and schema-3 binding rides the core digest.

C. `BootstrapGraphGroupCommitReloadV3` (contracts.py:12811-12902):
   `group_result_schema_version: Literal[1, 2, 3]`; version 3 requires a core
   with `group_result_schema_version == 3` and every schema-2 ledger
   requirement (extending the version coupling at contracts.py:12873-12901);
   version 2 continues to require exactly core schema 2; version 1 exclusions
   are retained exactly (contracts.py:12826-12841). The reload gains no own
   attestation field — the seal digest reaches it through
   `persisted_result.core`.

D. New seal-member execution records and the registered artifacts they carry
   (both kinds above). Registry regeneration is coordinated with the
   already-pending publication refresh that adds ProjectionObservationIdentity.v1
   (owner-decision.md administrative default); the two profile domains named
   above are the registration coordinates for the artifact encoder, following
   the registered-artifact emission pattern (e.g.
   `emit_registered_observation_artifact`, atomic_store.py:13229-13232).

E. No paging or public-contract change of any kind
   (graph_observation_public_contracts.py stays byte-frozen).

## Normative Reader Rule: Typed Denial For Legacy And Unsealed Cohorts

The ingestion-time cohort provider replaces the current fail-closed stub
(graph_observation_materialization.py:193-202) with selection-only-from-bound-
digests: from the resolved cohort membership, select a source seal only
through the terminal record's schema-2 `source_retention_attestation_digest`,
and a group seal only through the core's schema-3
`transaction_group_commit_attestation_digest`; then validate the exact joins
(member identity, registered artifact, typed attestation,
`source_record_digest` / `committed_batch_digest` reachability, fence/group/
operation/graph-revision/clock-identity equality).

For legacy and unsealed cohorts the rule is typed denial, not an empty page
(owner decision): if the resolved cohort contains any source finalization
whose outcome record is schema 1 (or whose seal member is missing, duplicated,
substituted, or join-mismatched), or any group result at core schema 1 or 2
within the selected cohort, the provider raises
`ObservationCohortUnavailableError` (graph_observation_paging.py:87-88),
which the paging runtime already maps to the frozen non-disclosing
`GraphObservationFailure(reason="denied")` (graph_observation_paging.py:352-353;
reason Literal at graph_observation_contracts.py:27). No new failure reason,
cursor state, or synthetic attestation is introduced. A cohort whose resolved
membership contains no ingestion results at all may still return a valid
empty first page (the page contract permits an empty page only at position
zero with no continuation, graph_observation_public_contracts.py:358-368).

## Membership And Recovery

Source retention binds source ID, operation fence, source-record digest, graph
revision and clock identity. Group commit binds source/fence/group IDs, sorted
operation IDs, start/commit instants, graph revisions, applied graph delta,
committed batch digest and clock identity. The detached ingestion-time reader
selects only registered artifacts whose result-bound digest is reachable from
the resolved source finalization/group entry and validates those exact joins.
Missing, duplicate, substituted, mixed-fence/source/group, invalid time order,
or absent result digest makes the cohort unavailable (typed denial above).
Partial member/result publication fails closed; lost acknowledgement reloads
the immutable winner (reload paths mint nothing). Read-only snapshot stores
deny timed authority outright.

## Compatibility

No retroactive attestations: legacy schema-1 source bytes, schema-1/2 group
core bytes, and their field exclusions remain exact (per the preimage rules
above); existing stores simply have no seals and read as typed denial.
Migration writes only source schema 2 and group core schema 3; it never
rewrites history or derives time from a later record timestamp. An orphan
admission member remains evidence but is not cohort-reachable until schema-2
terminal binding. Immutable seal-member execution records are retained
without compaction (owner-decision.md administrative default).

## Implementation Milestones

1. M0 (prerequisite, owner-decision.md administrative default): protected
   clock fix — introduce `IngestionTimeClock`, route it through the provider
   constructor and both raw-source construction sites, governance derivation,
   and the atomic store `now_provider`; implement recovery-before-derivation
   redelivery. No seals yet; existing schemas unchanged.
2. M1: schema-2/3 contract extension (items A-C above) riding the
   ProjectionObservationIdentity.v1 publication refresh.
3. M2: seal minting at both admission CAS entry points and the group CAS;
   reload validation extensions.
4. M3: reader — `ingestion_time_input` cohort selection with the typed-denial
   rule.

Feasibility proof on the real backend precedes M0; independent design review
precedes implementation (owner-decision.md Next).

## Required Implementation Proof

Cover source admission, committed and non-committing groups; duplicate/retry,
CAS race, crash between construction and write, lost acknowledgement, JSONL
reopen, clock identity/time/source/fence/group/operation/delta/batch mutations,
and legacy decoding. Prove source/group result digest substitution fails
before detached selection, no seal is emitted for a failed CAS or inferred
from an execution-record timestamp, and redelivery reuses the winner's bytes
after M0. Discharge ITP-01..04 (design.plan.md). This design does not choose
clock service, retention duration, polling policy, or any time value.

## Resolved Readiness Findings Map

| Finding (2026-09-08) | Resolution |
| --- | --- |
| Admission-time immutable anchor before a terminal exists | Admission Anchor Contract (retained source record + seal member in one CAS; terminal binds back via schema-2 digest) |
| Acyclic `committed_batch_digest` | Group Seal section; verified against event_replay.py:410-462, 1124-1192 |
| Enumerate `publish_admitted_source` as well as `admit_source` | Seal-Minting Entry Points table |
| Protected clock at raw-source construction | Protected Clock And Redelivery Contract (replaces provider/ingestion.py:396) |
| Complete core -> outcome ID -> source-result digest -> record digest coverage | Persisted Schema Changes, item A; group-side items B-C |

## Open Questions For Design Review

1. SIA admission-request-digest alignment: SIA 24692+ defines an immutable
   admission request digest (including the retention-attestation digest) for
   `SourceAdmissionAtomicWriteRequest` / `PendingSemanticOperation`, which
   have no production class (confirmed 2026-09-08, Legacy Group Core Field
   Exclusion below). This design binds real persisted artifacts (retained
   record + admission index + fence + seal member) instead of introducing
   those classes. Either SIA is amended to the artifact-bound anchor, or a
   separate design introduces the closed request owner before this contract
   is frozen. Not blocking for feasibility proof; blocking for SIA
   conformance claims.
2. `IngestionTimeClock.identity` provisioning (operator configuration surface
   and lifetime policy) is out of scope here by the existing non-goal; the
   contract fixes only that it is a stable protected configuration identifier
   recorded verbatim in every seal.

## Recorded Code-Inspection Evidence (2026-09-08, retained)

### Canonical Admission Reconciliation

SIA lines 24391-24407 already require a retention attestation in the non-bootstrap
atomic admission request. Lines 24692 onward define its immutable request digest,
including the retention-attestation and pending-operation digests while excluding
current authorization evidence. The implementation's authorization index digest
(admission.py:536-537) is not that immutable request digest. This revision does
not invent a second admission anchor; see Open Questions 1.

SIA 24679 separately requires bootstrap admission without a writer binding or
pending operation until handoff. Current provider ingestion calls the writer-bound
`publish_admitted_source` before handoff; the seal belongs to that admission CAS,
which exists before writer binding, so the seal design is compatible with the
canonical bootstrap pre-writer path while that path discrepancy itself is tracked
by the architecture documents.

`source_admission_source_digest` deliberately excludes the retention timestamp;
it identifies the logical source for retry. Attestation `source_record_digest`
uses `record_digest(source)` for the complete persisted record. Clock identity
is absent from the retained record and cannot be inferred from its timestamp.

### Provider Clock Discovery

Direct coordinator inspection of `core/provider/ingestion.py` lines 393-410
found that `retained_at = delivery_event.timestamp` (line 396), expressly
documented there as a caller-owned immutable delivery timestamp, and that this
same value supplies both `received_at` and `retained_at` to governance
derivation (lines 403-410). Keeping that value and adding a protected clock
identity would falsely authenticate caller time. Confirmed production-path gap
against SIA 4.1.5; resolved by the Protected Clock And Redelivery Contract.

### Validated Retry Owner Map

The read-only retry trace confirms no retained-source lookup before provider
governance derivation. `GovernedSourceAdmissionService.lookup` (admission.py:312-405)
checks principal, delivery key, tenant and the complete stored scope set before
outcome access; it is a reusable authorization pattern, not an API that returns
original StepOne material. `prepare_atomic` only constructs its five prepared
records (admission.py:214-280); it does not perform `_recover_exact_admission`
(admission.py:282-310), which belongs to the non-atomic `admit` path.
`_same_admission_record` (atomic_store.py:16999-17006) ignores only the
top-level record timestamp; all content remains exact, so any governance or
material digest depending on retention time must reuse the winning retained
material — hence recovery-before-derivation. `_admit_with_writer_retry`
(provider/ingestion.py:847-858) retries one specific writer-admission
mismatch, not general retention conflicts.
