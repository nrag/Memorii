# Acceptance Authority Design Review

Round one: all three independent reviewers request changes. Four source hashes
and governing SIA hash match the initial candidate. One feasibility test passes;
its bounded DAG/current-pointer result is not full verifier evidence.

Coordinator reconciliation (all Not applicable / changes_required):

1. Confirmed security/lifecycle gap: checkpoint lacks a current issuance-trust
   head; old unexpired key-status prefixes can bypass later revocation. Bind
   the protected current trust head and replay complete key-status transitions.
2. Confirmed schema/state gap: absent active pointer cannot supply required
   active epoch/sequence. Make all three active coordinates required-nullable
   with an exact all-present/all-null invariant.
3. Confirmed signature contract gap: checkpoint signer reference/profile/purpose
   and preimage are missing. Define the full anchor-held coordinate and exact
   preimage; choose unsigned replay-derived pointers authenticated by checkpoints.
4. Confirmed lifecycle ambiguity: release issuance coordinates and effective
   lifecycle state/sequence are conflated. Freeze complete transition inputs,
   outputs, nullability, monotonic counters and immutable release relationships.
5. Confirmed CTV description error: SIA 2783-2786 and existing encoder order keys
   by encoded UTF-8 JSON-string bytes. The coordinator's earlier scalar-order
   interpretation relied on a grammar label and was incorrect. Retain encoded
   byte ordering for the proposed new inventory/profile; do not change semantics.
6. Confirmed resource bootstrap ambiguity: distinguish protected initial decode
   ceilings from signed effective limits, validate no expansion, and specify
   bounded parsing before verification without an unbounded bootstrap step.
7. Confirmed evidence ledger error: record the existing local feasibility test
   precisely instead of saying no test exists.

Duplicate current-key findings from spec/correctness and checkpoint/lifecycle
findings from spec/test review are consolidated above. The spec review's P2
classification for the key-status gap is reduced to Not applicable because this
candidate is an unimplemented acceptance-only design; its approval disposition
remains changes_required. No parent criterion is waived.

Next remediation is one coherent correction of all seven families, with scoped
executable vectors for lifecycle/current-key/checkpoint/resource behavior. The
initial frozen candidate remains preserved. No canonical promotion is approved.

## Successor Review Reconciliation

Candidate 36fc5f46416de4667b0a02e7d300af3427155a7b1f3d400073f60e61819be5e0
has all four source files archived and seven passing feasibility tests. All
three reviewers still require changes. Coordinator confirms these invariant
families as Not applicable / changes_required contract-conformance or evidence
actions, not product defects in an implemented verifier:

1. Canonical SIA 1209-1268 already gives immutable signed releases lifecycle
   fields and calls superseded/revoked releases lifecycle records. The proposal
   must preserve that meaning or explicitly propose a canonical amendment;
   omitting those fields from the proof does not resolve the conflict.
2. Multi-key authorization needs a total global key-state reduction, explicit
   initial states, allowed purposes and complete signer coordinates. Rejecting
   every foreign key is not valid rotation evidence. Fingerprint and distinct
   status-key authorization require proof.
3. Lifecycle reduction must resolve same-target immutable subjects, define
   post-revocation replacement and repeated terminal transitions, and re-derive
   pointer head coordinates after every transition. SIA 3947 also requires
   durable production revocation before replacement activation acknowledgement.
4. Bootstrap parsing must enforce every named dimension before unbounded
   parsing; current json.loads proof only enforces total bytes. Full signer
   preimages must include the promised binding and coordinate.
5. Add exact independently specified CTV expected-byte vectors; describe all
   limited feasibility evidence accurately.

The correctness review's lifecycle blocks_approval classification is narrowed
to changes_required: the user already authorizes engineering design corrections,
and the canonical source gives a determinate immutable-record constraint.
No external key or policy decision resolves these engineering omissions.
Because two reviews identify the same authority/lifecycle boundary, stop
example patches and reconstruct it as one closed state machine. Preserve this
candidate unchanged in its archive. No canonical/runtime promotion is approved.

## Closed Reconstruction Conformance Review

Candidate `7d4d19e2ade112a4102492b9cf27029b0bae9de35c917bc510275c139a1f3af4`
was checked by spec, correctness and test reviewers. All pinned files matched;
16 focused tests, Ruff and Pyright (zero errors/warnings) passed. The exact
candidate and four inputs are archived under `history/<candidate-sha>.tar`.
No role approved the reconstructed design.

Coordinator classification:

- DREV-001 confirmed, with three duplicate reports: Not applicable /
  changes_required / design-lifecycle. The proposal requires authorization at
  issue time but specifies no total temporal ordering/cutoff connecting release
  issuance to key-state history. Current-state reduction and static signature
  verification cannot establish that relation. The correctness probe's ordering
  alone does not establish chronology because the model lacks time; it supports
  the missing relation rather than a demonstrated production authorization bug.
  Required successor scope: key-event ordering/ties, issue/evaluation cutoffs,
  static validity boundaries, historical rotation, compromise and receipt times.
- Bounded-parser byte-entry proof: confirmed evidence gap, Not applicable /
  changes_required / verification. Scanner helper checks are real, but no public
  byte-entry model calls them before verifying the chain. No runtime vulnerability
  is claimed. Required proof must compose the declared limited byte subset.
- Closed modeled artifact shapes: confirmed evidence gap, Not applicable /
  changes_required / verification. The model intentionally excludes complete
  registered schemas, but even compact signed bodies accept unused extra fields.
  A successor must close its own compact shapes and prove trusted re-signing
  cannot bypass required modeled fields/types.

The explicit one-reconstruction/one-conformance-verification budget is exhausted.
Stop this linked operation; do not silently start another patch/review loop.
The blocker is incomplete engineering design/evidence, not production signatures,
external policy thresholds, unavailable PKI or credentials. Smallest additional
work is a bounded temporal/byte-entry authority design with the stated matrix;
canonical promotion and parent R14 remain incomplete. Other independent parent
work can continue without altering this rejected candidate.
