# Package 5: Authenticated Observer And Comparator

- Parent WorkPlan: `docs/work/semantic_ingestion/engineering-closure/implementation.plan.md`
- Status: active; authenticated public observation and independent comparator closure
- Requirements: R03, R13, R17

Implement scoped observer and independent comparator with pagination and revocation failure proof.

## Active Native Persistence Slice

`source-finalization-integration-map.md` identifies the actual bootstrap terminal
transaction; generic `finalize_source` is not its caller. The current writer
owns the terminal preparation/assembler/contracts/atomic store/writer admission
integration and focused tests. The coordinator retains the observation builder
and record contracts. Server-derived IDs and revisions implement the existing
SIA ownership rule using explicit domain-separated canonical hashes; the schema
fingerprint must derive from the actual observation schema, following the
graph codec convention. Historical terminal bytes require explicit grammar
dispatch and may never gain synthesized audit evidence on reload.

The pure builders pass seven focused tests after coordinator corrections for
delivery-key/principal substitution, canonical record identity reuse, and
duplicate materialization rejection; Pyright and Ruff pass. This is not a
persistence entrypoint proof. The independent pre-coding test review requires
real sync-path normal and zero-group failure, same-CAS membership, lost-ack and
restart, request/recovery reload, persisted rehash/tamper, stale CAS/auth,
historical grammar, and absence of fabricated historical observations. Group
observation persistence and authenticated query/comparison remain pending.

The initial integration diagnostic run failed for direct/factory/filesystem
roots before delta assertions (`graph_transaction_authority_unavailable`), then
was interrupted to inspect the failures (3 failures, 176.05 seconds; fourth root
not completed). This is construction evidence, not a passing gate. Coordinator
review independently found historical preimage drift from added default fields
and missing store-side coordinate recomputation; the writer is correcting both.
The coordinator now owns all pytest execution after recovering and stopping two
duplicate runs whose handles were lost by the delegate. No pass result is
inferred from an unobserved process completion.

## Next Action

Resolve the linked graph-transaction authority rejection at
`../../graph-transaction-authority-debug/debugging.plan.md`, then exercise the
comparator through the real host-composed ProviderMemoryService with configured
caller denial, scope isolation and revocation between continuation pages.

## Public Comparator Foundation

Commit `eccb5bfc` adds the first bounded acceptance-owned comparator slice. It
collects a complete public GraphObservationPage chain, independently validates
frozen snapshot coordinates, half-open continuity, global ordering/uniqueness
and exact cohort closure, and surfaces typed public failures between pages. Its
pre-ingest ExpectedOperation declaration contains logical operation/fence keys
and source-visible coordinates only. Alignment proves a unique global fence
partition and unique operation bijection by removing selected matching edges;
production IDs and later graph records cannot resolve ambiguity.

Coordinator verification at `eccb5bfc` passed six focused cases under
warnings-as-errors, Ruff and supported first-party Pyright with zero findings.
The cases cover two-page collection, cohort/continuity mismatch, revocation
between pages, stable unique matching, zero solutions, and ambiguous operation
and fence mappings. This establishes only the comparator foundation. R17
remains partial until source/entity alignment, all schema-specific comparisons,
ingestion-time witnesses, structural mutation families and configured real-root
authorization/revocation proof pass.

Delegation record: `r17_comparator_slice` was the sole Terra writer for
`acceptance/structural_comparator.py` and its focused unit test. The coordinator
owned requirements reconciliation and independently reran its checks. No
production, integration, or planning file overlapped the writer's ownership.

Comparator slice 2 stopped before editing when it proved that
ObservedSourceIntroduction exposes only opaque
`independently_asserted_type_evidence_ids`. The approved design requires
fixture-authored type-proof coordinates during source-introduction alignment,
before later type-evidence records may participate, and forbids production IDs
in expected fixtures. A read-only mapper's suggestion to compare those IDs was
rejected because it contradicts that contract. This is a determinate production
schema and persistence gap, not a new policy decision. The sole writer
`r17_source_type_proof_publication` was assigned the canonical/public contract,
commit-time derivation, registered artifacts and focused production tests; it
stopped before editing when the required validated upstream authority proved
absent.

That production correction stopped before editing after tracing the sealed
authority to its source. The current proposal contains only model-supplied
`proposed_type` and no validated type assertion that binds an asserted type,
exact evidence span and proof class. Canonical identity planning deliberately
emits empty type-proof digests, records and candidate evidence IDs. Treating the
model proposal as certified evidence would violate the repository's
model-output validation invariant. Therefore R17 comparison supports the
actual empty type-proof set and rejects nonempty opaque bindings as
unverifiable; it does not create a hidden type-certification feature. This is a
fail-closed implementation boundary. A future source-type capability must add
its own validated evidence contract before producing such bindings.

Commit `61f12cff` completes the next comparator layer. Source introductions
align only after operation/fence alignment; repeated introductions may identify
one logical entity only when they resolve to the same revision/logical-ID pair,
and distinct logical entity keys cannot collapse many-to-one. Operation and
source terminal outcomes join only through established operation mappings and
compare exact status, effect shape, reason set and complete operation set. The
logical observation membership and per-kind counts must equal the complete
public cohort. Twenty focused warnings-as-errors cases plus Ruff and supported
Pyright pass, including missing, substituted, ambiguous and many-to-one
alignment; terminal mismatch; missing/extra outcomes; and membership/count
mutations. This remains bounded evidence until the real configured public route
and remaining schema-specific record comparators pass.

The first real-route integration attempt retained no draft. Three authoritative
fixture combinations produced the same causal result: writer and observation
activation authority were valid, but source sync returned
`graph_transaction_authority_unavailable` before the configured graph authority
provider was invoked, leaving one undrained preplanning control. Reversing the
cutover order correctly refused ledger activation. The causal investigation is
owned by the linked debugging WorkPlan; R17 remains partial.

The linked `../../terminal-publication/closure.md` records bounded source closure
with all three independent approvals, public same-CAS/restart/tamper/authority
loss proof and authentic historical V1 replay. It does not close this packet.

## Group Retention Implementation Slice

The coordinator validated the existing fact planner's subject/entity-object
candidate selection and source-normalization evidence/temporal construction.
The missing mapping is retained upstream, then dropped before the fact effect.
No new product membership policy is required for that accepted arm. The sole
Terra writer first implements the typed planner/reducer carrier and focused
compatibility checks; group CAS/reload follows sequentially. Root owns tests.
An initial overbroad writer assignment produced no retained implementation; its
scope was reduced to these coherent slices, not treated as an external blocker.
Current source closure remains pinned historical evidence, not approval of later
contract changes. Every affected source/codec check must be repeated after them.

Authenticated query mapping proceeds independently read-only. Its preimplementation
matrix is `../observation-query-validation-matrix.md`; neither a map nor a helper
will be reported as a production observation API.

The first bounded carrier implementation adds a typed selected-mention binding,
planner retention, reducer completeness checks and explicit legacy serializers.
Root ran its two new tests plus six authentic historical compatibility/reload
cases. All six historical cases pass; both new tests fail in their own setup:
one reads target_resolution_authority from an input that intentionally lacks it,
the other passes schema_version twice to a factory. Evidence is retained in
`../group-retention-initial.log` (65.91s). The writer is correcting the tests,
capturing the real planner request for its independent expected candidates and
adding missing/substituted/duplicate carrier negatives. No parent closure claim.
The writer's earlier Pyright missing-dependency run is invalid environment
parity evidence, not proof of pre-existing product errors.

`observation_authority_owner` (Terra worker) owns only new observation contract,
authority and cursor modules plus new focused tests, independently of the group
writer's existing files. The pre-coding test consultation required an explicit
failure taxonomy/disclosure row and complete attestation-stream closure; both
are now in the matrix. This is a bounded authority foundation, not a claimed
provider/query implementation. Any unresolved canonical signing/schema binding
must be reported rather than replaced by a private codec. Root owns tests and
all progress documents. The Spark query map was reconciled and rewritten by root
with exact verified paths; speculative neighboring infrastructure was removed.

## Verified Retention And Current Construction

Root reproduced the retained planner authority through one real public sync test
with inline substitution, omission, duplicate, admission and downgrade negatives:
1 passed in 33.85s (`../group-retention-verified.log`). The test checks every
matching planner execution because deterministic verification legitimately plans
again. Root Pyright of planner, reducer and test reports zero errors using the
repository Python 3.12 environment (`../group-retention-pyright.log`). The earlier
six historical cases passed before the final carrier-validator strengthening;
affected compatibility checks remain required at the group candidate boundary.

The existing Terra group writer now owns the native group CAS/reload projection
slice: actual before/after graph and reference mutations, canonical introduction
and outcome conversion, same-CAS typed observation, and explicit legacy grammar.
It does not own the retention test or the separate authenticated-query foundation.
Root owns all pytest execution and progress documents. This is construction, not
independent approval or full R17 closure.

The initial isolated observation foundation passed four root-run checks in 4.26s
(`../observation-foundation-initial.log`). That evidence predates a coherent
construction correction for typed cursor input, bounded decoding, complete
authorization preimages and configured Ed25519 public verification. The separate
Terra foundation writer owns those four new files; current verification is pending.

## Shared Revision Discovery

Native group CAS reads a source-local observation predecessor, while the source
terminal request seals that same local chain upstream. The canonical design
requires shared replayable observation order across sources. The group writer
made no CAS edits that would mislabel a local chain as global. This integration
slice is paused for linked `../../observation-ledger/design.plan.md`; foundation
verification and independent record projection mapping continue. This is an
internal transaction design prerequisite, not missing user policy or signing.

The corrected foundation now passes all seven focused tests in 4.32s, including
separate public-key verification, wrong-key/signed-coordinate rejection, exact
wire/raw ceilings and proper CTV depth semantics. Root retained both construction
failure logs and the final run (`../observation-foundation-final.log`). This
proves the bounded foundation, with no production caller or full cohort claim.
The first shared-ledger feasibility run failed 3/7 cases because dataclass
flattening erased the nested payload type; one coherent grammar/replay correction
is in progress under the linked design, with no production write changes.

Final current evidence: authenticated foundation seven tests/Pyright/identity gate
pass with file hashes in `../observation-foundation-evidence.json`. The separate
ledger ordering/DAG model passes 19 checks, and independent test delta consultation
closes its six evidence actions. Parent persistence/API/acceptance closure remains
unapproved; shared-ledger registered contracts are the stated next dependency.
