# Package 5: Authenticated Observer And Comparator

- Parent WorkPlan: `docs/work/semantic_ingestion/engineering-closure/implementation.plan.md`
- Status: active separate projection observation integration; bounded source-finalization debugging complete
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

Implement operational registry publication under
../registry-publication/implementation.plan.md, starting with the closed
raw-declaration parser and then complete source/decoder publication. Design
candidate215ab5f272d7b27589da04c9c1dd4a9fa0f1d8f01413d542ea72bffa4c924b9e
is approved; native ledger/projection/retrieval runtime remains partial.

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
