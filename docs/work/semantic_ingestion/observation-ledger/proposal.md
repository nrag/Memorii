# Shared Observation Ledger Transaction Proposal

Status: draft; no canonical schema or production change approved.
Parent: design.plan.md. This replaces ambiguous/circular portions of the initial
transaction-boundary.md. All changes are internal audit authority; ordinary
semantic membership, user memory visibility and acceptance authority are unchanged.

## Hash And Ownership Boundary

The shared ledger belongs to the same atomic-store partition as canonical graph
state, with one conditional head and append-only entries. Sequence is a positive
integer; revision is an opaque content address. Neither is a timestamp. All
fields have closed typed contracts and unknown kinds/versions reject.

A terminal identity is stable across a head conflict: group identity binds the
sealed request/group, source identity binds the operation fence/canonical source
result. The semantic payload contains the exact canonical observation delta
fields except observation_revision_before, observation_revision_after and
delta_digest. Compute payload_commitment from that closed typed payload under
a distinct registered CTV binding. Then compute successor from the exact
repository identity, activation digest, predecessor revision and payload_commitment
(which already includes the stable delta identity). Finally form
the delta with predecessor/successor and compute delta_digest. The immutable
entry binds sequence, delta, commit result locator/digest and entry digest.
The head binds sequence, successor, last entry identity and entry digest.
No hash depends on itself: successor does not contain final delta_digest.

A new append atomically compares the whole current head digest (or absence at
genesis), current writer/lease/control and applicable graph/reference authority,
then writes head, entry, result and all existing effects. Exact duplicate identity
reloads its original entry only after comparing immutable semantic/result inputs.
Changed content under an existing identity rejects before any write. A failed
head CAS publishes nothing. Retry rereads authority and reconstructs assigned
coordinates; it never reruns provider analysis merely to obtain a new head.

## Source Terminal Sealing

The current V2 source request includes a fully prepared revision-bearing delta;
it cannot be rewritten after sealing. New terminal grammar therefore separates
semantic intent from store-assigned receipt data. Preparation seals the existing
canonical source result and all existing semantic terminal members plus one typed
source-outcome intent. That intent contains the exact outcome and observation
schema binding, but no assigned revision, delta digest or caller-selected head.
The stable publication locator derives from that semantic intent and authority.

Inside terminal linearization, the store authenticates and validates the sealed
intent, reads the head, constructs the source delta and its final native member,
and writes its complete actual member manifest, terminal control, identity,
locator/recovery indexes, delta entry and head together. Receipt/reload retain
actual delta and manifest, linked to the original intent. The request digest
identifies intended work; the actual manifest/entry digests identify committed
bytes. Reload must verify both relationships explicitly, never equate request
bytes with a delta that did not exist when the request was sealed.

A terminal retry first checks durable locator/request/recovery identity; an
already committed terminal reloads exact entry bytes even if the global head
advanced. Otherwise it retries through the existing lease/generation policy
with fresh head authority. A head-only conflict does not fabricate a graph
conflict or discard the canonical source result. Exhaustion is typed retryable
progress, never a durable failed source observation.

## Group Append And Replay

Group materialization constructs actual graph/reference mutations and canonical
introductions/outcomes before its atomic batch. Source mention authority comes
from retained planner bindings. A noncommitting delta has exact operation
introduction/outcome pairs and no source introduction or graph delta. A committed
group links its one exact same-transaction GraphRevisionDelta. Group result and
reload retain the assigned delta; all effect/member reads verify byte equality,
not only primary metadata. Local control revision becomes a last-published
checkpoint and may lag the global head; it is never append authority.

Genesis replay walks entries in sequence, verifies exact predecessor/successor,
all payload/entry/head hashes, duplicate identity rejection, terminal operation
pair/source-finalization membership and immutable result/graph links. Graph
record keys and historical before/after versions remain explicit. A checkpoint
must be verified under the existing graph replay trust/rollback principles before
using its prefix; the precise checkpoint authority binding remains to be mapped.
The feasibility model proves only ordering/idempotency/hash acyclicity, not
production checkpoint trust or complete observation schema validation.

## Compatibility, Activation And Snapshot Reads

Legacy terminal V1/V2 and legacy group contracts retain exact bytes and their
existing public result/recovery behavior. No legacy record is silently entered
into the new audit ledger. A legacy source lacking a complete global observation
closure cannot satisfy authenticated structural observation. New writer admission
must require the new grammar and shared-head batch after activation; old writers
cannot continue appending source-local-only audit during a new-ledger epoch.
The exact writer activation marker and checkpoint migration must be mapped before
review; merely creating a head on first write is insufficient mixed-version proof.

Authenticated cohort reads must pin graph/reference/observation authority from
one consistent store snapshot. Seed indexes are only locators, never completeness
authority. Graph snapshot tokens currently omit observation head and therefore
cannot themselves identify the required observation snapshot. A read either
verifies one consistent revision set or returns typed stale failure. Page caches
must retain immutable creation time for age checks without caller authority.

## Alternatives And Remaining Evidence

Store-finalized source audit is preferred because it separates semantic intent
from commit coordinates and retries within the atomic owner. A trusted preparer
could read a head, propose coordinates and have the store independently validate
and CAS them; that is not inherently unsafe, but would require a separate
re-preparation path and change sealed intent on every competing append. The
initial note incorrectly dismissed that alternative solely as untrusted.

Before approval: freeze full terminal intent/reload grammar and field sources;
map exact activation and checkpoint authority; inventory registry/CTV/schema,
profile/golden/writer-gate consumers; run bounded interleaving/retry/replay model;
obtain independent specification, correctness and test review. No runnable API,
full replay or M5 completion is claimed by this draft.

## Digest Consultation Reconciliation

Independent correctness consultation confirmed that the minimal model's generic
result_digest was ambiguous: a final group result that contains the assigned
observation delta cannot enter its own revision-free semantic payload. The model
now names that input precommit_result_digest and derives a separate final group
result after the delta; its source result remains pre-delta. Fifteen tests pass,
including identical semantic inputs under different ledger heads yielding distinct
deltas/final results without changing payload commitment.

The production terminal-group delta already declares no generic group-result
field, so adding a new precommit-result type is not automatically required. Its
closed revision-free field projection is the actual semantic authority. The
immutable ledger entry binds the final canonical result downstream; the result
must not bind its own entry digest. A source may reference already committed
group results: these are earlier DAG nodes and do not by themselves form a source
cycle. Do not reinterpret the existing public group-result digest family merely
to match the illustrative model. Exact joins remain under design construction.
