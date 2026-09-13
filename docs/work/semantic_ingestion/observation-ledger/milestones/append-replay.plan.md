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

Complete the activated provider failure-family proofs (lost acknowledgement,
contention, authorization failure and noncommitting outcomes).

## Production Completion Round

Final checkpoint result:281 consolidated tests passed1108.52s; separate full
activated-provider test passed1269.55s, including two sources/four entries,
JSONL reopen and acknowledged retry after the later head without duplicates.
Compatibility delta160 passed69.31s;58 independent registry vectors passed;
Ruff, Pyright and identity hygiene passed. Source/test/generated files remained
unchanged during these final runs and independent review. The dedicated CI
timeout was increased to30 minutes with the same command and assertions; the
test reviewer approved that bounded delta. CI remains unobserved and local
Python3.12.14 does not establish CI Python3.11 parity.

Review results: no remaining validated P1/P2 or concrete spec defect was found.
The test reviewer requires activated public lost-acknowledgement, contention,
authorization/fallback failure and zero-group/noncommitting proofs before full
append/replay approval. These are confirmed evidence actions, not claimed
production defects or completed tests. See production-review-results.md and
production-execution-results.json. Earlier frozen document contents are retained
in production-reviewed-documents.json; final metadata/document refresh does not
change reviewed production behavior. This is a production-fix checkpoint, not
append/replay or M5 closure. Public retrieval remains unimplemented.

Current review identity: append-evidence/production-candidate.json. Corrected
production binding preflight: append-evidence/production-binding-review.md.
All delegate writers handed off; root owns the frozen candidate. The prior
provider discriminator reached two sources/four entries before JSONL reopening
exposed tuple/list comparison of fanout operation IDs. Comparing the canonical
JSON content fixes this without changing persisted bytes or relaxing values.
Final compatibility delta:160 passed69.31s; Ruff, Pyright and identity hygiene
passed. Full provider recovery and consolidated regression are running. The
standard spec/correctness/test cohort is reviewing this bounded round; no
whole-milestone or whole-branch approval is claimed.

User requested production fixes across as many open requirements as practical,
followed by consolidated tests. Baseline is clean8785d9f3. Root will not label
helper construction as completion. Observable target: ordinary provider
activation, accepted ingestion, global group/source entries, restart/recovery,
and authenticated graph retrieval using the real detached cohort backend.
The current round prioritizes the complete activated write/recovery path. The
partial graph projector was removed before candidate verification because it
had no production caller and covered only four graph variants; public retrieval
remains explicit unfinished work, not an approved or shipped helper slice.
Ingestion-time cursor design and acceptance-authority design remain separate
explicit contracts; do not invent new wire fields to bypass them.

Delegation and ownership: Terra activated_writer owns atomic_store,
writer_admission, semantic_control and native group/evidence production owners;
Spark production_bindings maps remaining retrieval helpers read-only; Terra
production_test_matrix reviews actual-provider validation seams read-only;
Terra observation_projector owns only the new typed native-to-observed projection
module. Root owns provider/factory, concrete cohort/authorization composition,
tests, generated artifacts, all long commands and commits. This separates
nonoverlapping writers while keeping the actual end-to-end route as the target.

The initial actual-provider test authors the full registry, activates through
ProviderMemoryService, and calls sync_event with a normal graph proposal. It
reproduced the post-activation blanket mutation rejection in16.30s. The fixture
isolates installed target metadata and host/model transport, not writer admission,
native graph construction, registry validation or canonical persistence. It
does not establish installed-wheel or external provider certification.
The read-only test matrix requires success, interleaving/CAS no-partial-write,
lost acknowledgement after later progress, reopen, protected authority rejection,
and public retrieval without fixture cohorts. Focused construction checks may
discriminate failures; broad gates run once after production construction settles.

The actual-provider discriminator exposed two production root causes: the
activated writer rejected the prerequisite admission/planning/handoff transactions,
and the atomic owner used body-depth80 while admission used body-depth32 for the
same registered ledger entry. The latter was isolated by tracing the failed
entry read after the legacy native-group closure had validated successfully.
The correction must share the protected configured reader limits, including
explicit overrides, rather than loosen an isolated validator.

Bounded correctness consultation identified required transaction joins for native
receipt/group identity, source locator/member identity, and selected publication
bytes. These are confirmed validation-boundary corrections. The worker is
remediating them before the consolidated candidate; this consultation is not
milestone approval. Existing activation/paging evidence predates these edits.

The next production discriminator persisted the native group and its first
ledger entry, then exposed Python-mode decoding of JSON terminal receipts.
Publication stores `reload.model_dump(mode="json")`; terminal publication,
request/recovery lookup, exact reload and ledger replay now use strict JSON
model decoding. This preserves typed validation without coercing arbitrary
Python values. The candidate provider test checks two sources, original entry
preservation, JSONL reopen and replay of the first request under the later head.

Canonical binding: `ProviderMemoryService.sync_event` reaches provider ingestion,
the existing graph coordinator/repository, and atomic group/source publication.
`SemanticGovernedWritePolicy.validate` requires the exact active binding and
closed transaction grammar, then invokes the callback registered for that
atomic capability. The callback uses one detached merged snapshot and the
existing full ledger replay plus immutable native/source evidence validators.
There is no permissive callback fallback. The two configured-limit consistency
tests passed (7.35s); full candidate provider and consolidated proofs remain due.

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
