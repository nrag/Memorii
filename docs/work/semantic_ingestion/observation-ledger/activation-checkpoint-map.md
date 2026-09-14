# Observation Ledger Activation And Checkpoint Map

Status: prerequisite map only. It identifies reusable production authority and
missing observation-ledger contracts; it does not approve the draft proposal or
claim that a shared ledger, migration, checkpoint, or rollback path exists.

## Activation: usable authority

`SemanticWriterAdmissionStore` is the current writer-admission authority. Its
single current admission record is
`writer_admission_memory_id()` at
`memorii/memorii/core/memory_evolution/writer_admission.py:146-147`; a commit
binding carries the admission digest, expected writer epoch, implementation
fingerprint, and graph schema fingerprint at
`memorii/memorii/core/memory_evolution/writer_admission.py:248-257`.
`require_current()` rejects missing, stale, and mismatched bindings at
`memorii/memorii/core/memory_evolution/writer_admission.py:259-267`.

The closest usable cutover mechanism is
`SemanticWriterAdmissionStore.advance_policy_epoch()` at
`memorii/memorii/core/memory_evolution/writer_admission.py:472-552`. It compares
the current admission binding, increments `writer_epoch`, and conditionally
writes both the successor admission and caller-supplied records under the old
admission authorization. Its existing `policy_activation_digest` is only an
opaque 64-hex binding (`:482-489`), not an observation-ledger grammar or
checkpoint certificate.

The governed-write policy already prevents a draining epoch from starting a new
operation: it rejects an absent operation control when the current admission
record has `draining=True` at
`memorii/memorii/core/memory_evolution/writer_admission.py:814-829`. Full
admission transition first writes that draining marker, verifies every retiring
operation is terminal or exhausted and lease-free, then conditionally advances
the admission at
`memorii/memorii/core/memory_evolution/writer_admission.py:400-469`.
This is usable evidence for a no-new-old-epoch operation fence.

`SemanticGovernedWritePolicy.validate()` is the enforcement seam: its allowed
record kinds and store methods are fixed at
`memorii/memorii/core/memory_evolution/writer_admission.py:60-101`, and it
rejects a governed write that does not match a recognized atomic control grammar
at `:780-805`. Existing group/checkpoint/terminal recognizers are specifically
accepted at `:841-850`. Consequently, a new shared-ledger grammar needs an
explicit record-kind/method admission and a new recognizer that requires the
shared-head entry, not an additional permissive path beside the source-local
group or terminal recognizers.

`SemanticIngestionAtomicStore` supplies relevant linearization and recovery
patterns but not the desired global head. The source-local V3 epoch transition
is `transition_or_find_bootstrap_graph_control_epoch_v3()` at
`memorii/memorii/core/memory_evolution/atomic_store.py:8833-8860`; it reads a
per-request epoch head at `:8862-8892`. The V3 checkpoint writer validates a
sealed native request and runs under the store linearizer at
`memorii/memorii/core/memory_evolution/atomic_store.py:9111-9171`. Source
terminal publication validates authenticated delivery/scope/fence/lease/writer
and control-epoch coordinates before reading control at `:10774-10795`, then
advances the source-local `observation_revision` in its one conditional write
at `:10943-10969`. None is a cross-source observation append head.

## Activation: missing contract

No existing admission field binds a writer implementation to a shared
observation-ledger grammar, ledger schema fingerprint, or checkpoint trust
state. The current admission's `accepted_graph_schema_fingerprint` and runtime
mode are constructed at
`memorii/memorii/core/memory_evolution/writer_admission.py:206-218`; they do not
establish ledger compatibility. The design must therefore define a new
activation record/precondition whose digest binds the new grammar and the
verified ledger checkpoint/head, and make the successor writer binding require
it. It must also change the governed-write policy so an old binding cannot
publish source-local observation effects after that activation. These are
required design and implementation work, not properties of `advance_policy_epoch()`.

The existing writer drain prevents new operation controls but does not prove
that all legacy terminal/group publication paths are unable to append after a
new-ledger epoch. Those paths are currently recognized independently by the
governed-write policy. The proposal must select an exact cutover rule and prove
that every old observation-writing recognizer rejects the post-activation
binding before an approval claim.

## Signed checkpoint lifecycle: usable authority

The closest complete signed-checkpoint lifecycle is semantic event replay.
`encode_replay_checkpoint_lifecycle()` and
`decode_replay_checkpoint_lifecycle()` provide a closed CTV envelope at
`memorii/memorii/core/semantic_ingestion/event_replay.py:1249-1271`.
`create_replay_checkpoint()` only signs a state at its final committed event
batch boundary (`:2341-2372`), binds repository, graph revision, writer epoch,
watermark batch/delta, materialized snapshot, registry/history, key and trust
policy coordinates (`:2410-2445`), and obtains the signature through the
configured authority rather than caller data.

`validate_replay_checkpoint()` validates lifecycle registry/trust values against
the live authority and rejects stale, substituted, or rolled-back coordinates at
`memorii/memorii/core/semantic_ingestion/event_replay.py:2460-2502`. It then
requires exactly one trusted key, verifies its fingerprint and both issue-time
and current-use validity/revocation/retirement/compromise windows, and verifies
the signature at `:2512-2539`. `replay_semantic_checkpoint_tail()` validates the
checkpoint before replaying the tail at `:2584-2603`.

The writer policy already recognizes `semantic_ingestion_checkpoint_lifecycle`,
replay authority, and schema-registry history as atomic replay-authority
records at `memorii/memorii/core/memory_evolution/writer_admission.py:1768-1779`
and requires replay-authority closure when an event member is present at
`:880-894`.

## Signed checkpoint lifecycle: missing contract

There is no observation-ledger checkpoint schema, lifecycle envelope, signing
authority adapter, trust-policy binding, replay-state type, or store caller.
The semantic replay checkpoint binds `SemanticReplayState` and
`SemanticMemoryEventBatch`; its `graph_revision` and batch watermark are not a
shared observation-ledger sequence/head. Reusing its lifecycle/trust/rollback
validation pattern is feasible, but reusing its checkpoint bytes or claiming it
validates observation entries would be incorrect.

No observed store method invokes `create_replay_checkpoint()`,
`validate_replay_checkpoint()`, or `replay_semantic_checkpoint_tail()` for a
shared observation ledger. A future store-owned append/checkpoint transaction
must define that caller and atomically bind the observation head, entry prefix,
selected graph/reference revisions, and checkpoint receipt. It must separately
specify mixed-version behavior: legacy V1/V2 bytes remain readable under their
existing paths but cannot be promoted into a fabricated signed global prefix.
