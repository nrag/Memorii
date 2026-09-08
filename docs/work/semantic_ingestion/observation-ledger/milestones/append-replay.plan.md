# Observation Ledger Append And Replay

Work type: implementation milestone. Status: active; exact preimages accepted and promoted; activation handed off.
Parent: ../implementation.plan.md. Governing design: semantic_ingestion_observation.md
Terminal Intent And Receipt Grammar, Group Append And Replay, Replay State Grammar,
and native-projection-binding.md. Scope: R17/R19 partial; no statistical acceptance.

## Actual Owners And Required Behavior

BootstrapGraphTerminalPublicationIntentV3 currently permits terminal member schema
1/2. BootstrapGraphTerminalPublicationRequestV3 and ReloadV3 retain an optional
preassigned local source delta. The approved schema3 uses SourceObservationIntent
instead; no caller assigns a global revision. Canonical owners are contracts.py,
bootstrap_graph_terminal_preparation.py, bootstrap_graph_artifact_assembler.py and
the actual atomic store terminal publication/reload. Preserve exact schema1/2
serialization, hashes and historical reload. The first nine semantic members
stay exact; the intent maps to one assigned delta member, not an extra fake
semantic entry/head member.

Native group commit is commit_or_reload_bootstrap_graph_group_v3. It already
creates canonical result, graph delta/events and native replay evidence. Assign
one shared observation head transition in that same conditional batch for every
terminal group outcome, including noncommitting outcomes. Source finalization
assigns its transition at its own linearization. All existing request/result/
fence/delivery/lease/governance checks remain. The active target schema and
registry select every new body/envelope; no label hash or guessed field exists.

A cohesive ledger owner derives semantic payload, registered payload/delta/entry/
head commitments and stable result locator. CAS binds current head and exact
source authority. Concurrent source retries reload fresh head with a finite
protected bound. Lost acknowledgement resolves immutable delta/result/entry
identity under a later head, not a stale mutable genesis comparison.

Replay consumes one complete detached memory-plane snapshot, exact activation
and independently loaded current head. It validates contiguous unique entries,
before/after revisions, commitments and exact immutable source/group/result/graph
joins. It never infers missing audit from historical local deltas. Genesis is an
explicit supported route; checkpoint authority remains a separate implementation
boundary and cannot be silently accepted by structural resemblance.

## Verification

Actual source/group production triggers; two interleaved sources; CAS loss with
no partial members; lost acknowledgement after later append; JSONL reopen;
zero-group terminal and noncommitting group; missing/extra/reordered/substituted
entry/result/graph; complete-prefix versus short-valid-prefix; schema1/2 byte
preservation; current admission and all governed write route checks. Reuse the
approved parent matrix and place persistence/restart proofs in integration gates.
Root owns gates and selected decoder-source/publication/vector refresh after
contract edits. One writer owns overlapping native/atomic paths.

## Next Action

Complete the closed activated-writer transaction grammar and verify actual
source/group append and recovery through the canonical atomic store.

## 2026-09-08 Pending Construction

Schema-3 needs one registered artifact owner for canonical
`SourceObservationIntent`, with atomic assignment of the source delta, ledger
entry, and successor head. Existing schema-1/2 serialization and reload remain
historical-only after activation. Group append and detached complete replay are
still pending; no implementation claim is made here.

## Readiness Reconciliation

Independent spec consultation confirmed that canonical prose does not fix the
semantic-payload or successor revision domain bytes/preimage order. Ordinary
payload declaration roles supply no such algorithm. Provisional append and
artifact-helper changes were withdrawn; root verified every frozen activation
source pin, and restored terminal preparation/assembler exactly against the
retained preparation candidate and wheel. The reviewed activation boundary is
intact. No weakened writer policy or partial source intent implementation remains.
The linked design operation proposes exact framing for owner acceptance; no
new signing or decimal-format decision is needed. Delegated append construction
did not converge; root owns the next implementation construction after design
acceptance. Mapper claims about nonexistent group-request introduction fields
were rejected against direct source searches.

## Owner Acceptance

User accepted the reviewed exact preimage amendment with "Go ahead". The
canonical design now contains its complete byte recipe. No further decision is
needed for those hashes. Terra sole writer owns bounded registered emission/hash
code and feature tests; root owns promotion, source integration mapping and gates.

## Construction Evidence

Root implemented the accepted LP recipes through selected registry artifacts;
ordinary native delta fields remain unchanged. Four feature cases passed8.34s.
Schema3 intent/request/reload contracts now retain revision-free source intent
and assigned receipt coordinates; root corrected the initial required-kind set
and versioned digest omissions at the common canonical owner. Three new codec
cases passed35.85s; nine existing captured-history/assembler cases passed16.04s.
No atomic append, replay or retrieval delivery is claimed from these contracts.
Registry decoder-source/package evidence must be refreshed for contracts.py.
The new tests use real publication authoring and captured terminal documents,
so they moved to integration and the existing dedicated ledger PR job. Root
owns the expanded gate and source-authority refresh before bounded review.

The expanded activation/artifact/terminal-contract gate passed 34 cases in
228.84s (`../append-evidence/integration-final.log`). Registry refresh and
independent vectors passed: 179 entries, 1255 roles, 58 vectors. Pyright passed;
one test import-order finding was corrected. These are local construction
results, not native append/retrieval closure or installed-writer authority.

Root now owns `observation_ledger_replay.py` and its dedicated integration tests;
Terra durable_activation_writer owns source preparation/assembler/atomic
integration. These are disjoint writing surfaces. The correctness reviewer gave
a bounded read-only algorithm consultation, with no concrete finding; it
explicitly excludes atomic snapshot/result callback ownership and approval.
Replay construction first passed eight negative/genesis cases but rejected the
valid full replay because the activation-only depth32 ceiling was too small for
the nested replay state. Artifact helpers now accept explicit protected reader
limits, preserving the existing activation default; replay requires the caller's
protected limits. Small-limit rejection tests accompany the valid full prefix.
No production replay caller is claimed until the atomic integration is verified.

Focused replay now passes14 cases in28.47s, including zero-operation source,
duplicate finalization and total-prefix limits (`../append-evidence/replay-complete.log`).
The first mapping consultation overstated missing constructors as design
ambiguities; root verified retained target candidates already expose exact
entity/type coordinates and requested a narrower authority check. Terra
native_group_audit owns only a new `bootstrap_group_observation.py` construction
owner and its mapping note; it may not edit atomic/contracts/preparer files.
It derives audit mutations from the actual native request, codec snapshots and
reference-ledger suffix while the source writer finishes its disjoint owner.
Root owns all tests, generated artifacts and coordinator reconciliation.

Source reload now retains the sealed schema-3 request and reconstructs the
assigned members from that request; full-prefix replay uses one detached
snapshot. Root also added finite source head-contention retry. These changes
remain construction work pending activated production tests and review.

The public-provider native group audit fixture passes one case in45.68s,
including actual changed-record and mention-authority matching and incomplete
mutation rejection. The assembler historical default fix passes six cases in
5.97s. Two existing missing-member tests were updated to corrupt the detached
snapshot now consumed by reload, rather than an unused individual-read seam;
both pass in76.67s (`../append-evidence/snapshot-member-rejection.log`). The earlier compatibility run remains pending with
three observed failures, so no compatibility completion is claimed.

The registered cursor owner now signs and reads the exact profile-3 envelope
using the selected signature-only policy and separately supplied public key.
One focused integration case passes in5.60s, including wrong key, wire limits,
invalid Unicode and malformed envelope rejection. It has no public paging
caller yet; authorization, snapshot retention and complete retrieval remain
pending. Native projection receipt and replay evidence roots now use the same
registered emitter.

Delegation: the previous Terra source writer yielded all production files and
could not complete the projection extraction within its remaining context;
no atomic edits were made in that assignment. A fresh Terra group_append_writer
is sole writer for atomic_store and shared projection extraction. Root owns
registered runtime, tests and evidence. prep_spec produced a bounded retrieval
ownership map; activation_correctness is consulting on closed post-activation
writer grammar. Neither is a milestone review. Generated registry/source pins,
installed-package evidence and final gate results must be refreshed after the
candidate stops changing.

## Native Group Assembly Construction

Root completed group assembly beyond the delegated partial projection slice:
the activated branch computes the audited native group delta, assigns the
registered global successor, regenerates per-operation receipts with those
coordinates, seals a schema-2 group result, and assembles immutable graph audit,
projection receipt/evidence, ledger entry and mutable head in the same CAS.
Historical group construction remains on its existing grammar. The generic and
native paths now share projection preparation; per-operation effect generation
is also shared by publication and detached reload verification.

Detached group verification joins the original request/result, complete native
effects, fanouts, graph mutation/event/reference histories, registered receipt
and native checkpoint. It uses a read-only memory-plane adapter and a separate
retained projection-prefix validator so a later projection tip does not replace
an old immutable receipt. Activation reload now separates retired inventory
from new-epoch controls and verifies the current prefix after append.
These are construction changes, not a verified activated write path: the
post-activation writer grammar remains closed. Complete writer classification/
admission, actual activated source/group tests and independent review remain
required before enabling writes or promoting any parent requirement.

New focused evidence: native group delta construction1passed40.09s;
detached snapshot suite20passed1.17s; retained historical projection prefix
1passed5.04s. The compatibility run completed40passed/3failed1151.62s; all
three observed failures are the assembler argument and two obsolete individual-
read fault seams already corrected by the recorded6-case and2-case reruns.
Do not report that old mixed run as a clean current-candidate result.
Current expanded50-case integration gate and targeted native-owner type check
are running in `append-evidence/integration-native.log` and
`append-evidence/pyright-native-owners.log`. Registry/installed-source evidence
must be regenerated after the current construction settles.

## Recovery And Paging Construction Checkpoint

The expanded integration gate completed50passed307.70s in
`append-evidence/integration-native.log`. This predates the final recovery join
and paging-owner additions; it is not whole-candidate approval. Root confirmed
both bounded correctness findings (P2, changes_required): receipt reload must
resolve its own immutable entry after complete-prefix replay, and native
evidence construction must require the checkpoint watermark batch to equal the
published event batch. Both corrections are implemented. The isolated recovery
join regression passes2 cases4.46s; registered native receipt/aggregate/checkpoint
emission and stale-watermark rejection pass with actual canonical models and
independent protected artifact validation.

Terra observation_paging_writer completed the new graph paging owner and yielded
ownership to root. Root review required exact registered authority validation,
decision/page-policy joins, original snapshot/request/context/write-token joins,
and first-page detached-cohort validation. Those corrections are implemented.
The paging and native-evidence integration cases pass2 cases13.90s in
`append-evidence/paging-native-construction.log`. Paging uses a fixture cohort
provider: it proves two contiguous pages, per-page authorization, changed-scope
rejection, denial before malformed cursor processing, intervening-write
invalidation, and rejection of a substituted snapshot revision. It does not
prove production graph selection or provider/factory integration. Root added
both integration files to the existing PR gate; CI execution remains unobserved.

The native evidence test needed a larger publication fixture because its complete
transitive schema closure exceeds the old60KB fixture manifest bound. The fixture
now consistently uses its configured protected limit at authoring and parsing;
production limits and rejection behavior are unchanged.

An actual design inconsistency was confirmed for ingestion-time continuation:
the shared registered cursor requires a graph-record discriminator and graph
view/time coordinates, while the ingestion-time request and stream expose
neither. No enum widening, fabricated graph kind, or wire change was made.
The exact contracts are cited in `../retrieval-runtime-map.md`; a separate linked
design correction is needed before implementing that continuation. Graph paging
construction can proceed independently, but is not publicly composed yet.

Delegation outcome: group_append_writer could not complete the bounded new
native-evidence test assignment; it made no test edits. Root implemented and
verified that slice. activation_correctness is checking the two corrections
and the new paging continuity boundary read-only; this is not milestone approval.
Activated writer admission, production retrieval, installed release package,
full candidate CI and closure review remain open; no R17/R19 promotion is made.

Bounded correctness correction review completed with no remaining finding:
both recovery/evidence findings are resolved and the graph paging authorization/
cursor-continuity slice has no additional concrete issue. This is not milestone
approval. Full repository Pyright reports0 errors; selected Ruff checks pass.
Registry publication was regenerated and independent normalized output agrees
for179 entries/1255 roles. Installed release/activation pins are not refreshed
or authorized by this construction run.

Snapshot/native-publication/recovery regression check passes29 cases7.91s
(`append-evidence/snapshot-recovery-regression.log`). All58 independent registry
vectors pass after regeneration (`append-evidence/registry-vectors.log`).
The expanded integration job passed52 cases306.79s in
`append-evidence/integration-paging-candidate.log`; it does not change
activated-writer or public-provider readiness. No background verification
commands remain running for this construction checkpoint.
