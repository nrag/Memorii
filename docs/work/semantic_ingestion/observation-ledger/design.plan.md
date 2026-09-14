# Shared Observation Ledger Design WorkPlan

- Work type: design
- Status: complete, design approved for implementation
- Parent: ../engineering-closure/milestones/05-authenticated-observer-comparator.plan.md
- Baseline: branch semantic_ingestion_m5 at 191826cd3afb38bf605a337a71d576063b3bae5e, authorized dirty implementation tree.
- Canonical source: docs/design/semantic_ingestion_architecture.md, sections 4/5.4.3; SHA-256 b469653e3ef92e9cc1bf45e797a2c7dff8eac4d9ee792ad94ada3a54bfbe05da.

## Objective And Current Evidence

Complete the shared observation-ledger transaction ownership required by SIA
23230-23240 and 25380-25389, before wiring authenticated cohort retrieval.
Current native group commit advances source-local PreplanningOperationControl
observation_revision; source finalization seals a successor from that control in
the host-prepared request. Neither is a shared append head. No production ledger
replay/checkpoint owner was found. A per-source chain cannot establish the one
requested cross-source observation revision of the public API. The bounded
source codec/debug closure remains valid for its stated scope, not ledger closure.

This operation does not change source/operation membership policy, invent missing
historical audit, choose external acceptance policy, or issue signing artifacts.
The authority-signature design remains separately blocked; it is not amended here.
No external decision is currently identified. Resolve implementation ownership
from governing contracts and test transaction feasibility before promotion.

## Requirements And Verification

| Requirement | Source / acceptance |
| --- | --- |
| Shared order | SIA23230: one store-owned monotonic observation chain across interleaved sources, group and source commits. |
| Atomicity | SIA23216/25385: exact delta, linked result, source/control effects and head advance are one conditional write; crash before/after yields none/all. |
| Retry identity | Same committed request reloads exact bytes without another entry; stale head causes determinate retry with no duplicate source outcome or graph work. |
| Replay closure | SIA23235: genesis/checkpoint reconstruct exact revision/records and verify linked results/graph deltas; missing/reordered/duplicate/cross-source/corrupt input rejects. |
| Compatibility | Historical V1 and source-only V2 evidence is never rewritten or promoted into fabricated global audit; mixed-version write admission fails closed. |
| Read consistency | SIA31870/31934: one authenticated snapshot binds graph, ledger, global observation revision, exact selected records and source closure. |

Tests/probes must cover two interleaved sources, noncommitting/zero-operation
source finalization, stale preparation, lost acknowledgement, restart, concurrent
CAS, byte-identical legacy reads, changed/missing entries and invalid checkpoint
trust. Deterministic proof is distinct from signing release or external quality.

## Boundaries And Alternatives

The atomic store owns shared revision assignment and conditional persistence.
Host preparation currently owns sealed terminal member bytes; those bytes cannot
be silently changed after its intent/request digest. Evaluate store-finalized
terminal observations against trusted head read plus re-preparation on a failed
head CAS. A new append record is production audit, separate from semantic graph
facts and acceptance artifacts. Keep authenticated retrieval independent of
writer leases while validating durable result/member authority.

Canonical public schema, registry/profile and downstream generated chain remain
unchanged until the proposal is approved. Inventory affected host/service roots,
writer schema admission, CTV bindings, replay trust/checkpoint schemas, manifests,
golden bytes and gate consumers in the proposal before review.

## Ownership, Identity And Budget

Root coordinates the proposal, requirement/evidence ledger and design decision.
Existing Terra group worker is read-only on production and writes only
transaction-boundary.md, to map exact source/group paths and alternatives.
Existing authority worker independently maps observation record projections in
the parent operation. Separate foundation worker remains limited to its four
new files. Root owns all test processes. No concurrent writers overlap.

Proposed durable identities must describe observation ledger entries, heads,
checkpoints and snapshot authority; requirement/package coordinates are planning
metadata only. Full identity inventory is required before candidate freeze.

Budget: one transaction-boundary reconstruction, one bounded feasibility model,
one full independent review and one consolidated determinate correction. If
required decisions remain or this budget is exhausted, record exact blocker;
do not silently reopen or claim implementation readiness.

## Next Action

Resume implementation under ../registry-publication/implementation.plan.md.
The reviewed design is complete; runtime registry/ledger/retrieval remain partial.

## Frozen Review (2026-09-07)

The canonical target is docs/design/semantic_ingestion_observation.md, linked
from SIA. Candidate digest
698874b5b29c9abce7623b3b3c4150639762cdd038f8ccd815521c28eaca2cd3
records exact files and known evidence gaps. Root verified policy retention
through the public native group input (2 focused tests) and historical/public
compatibility (4 tests); these are feasibility evidence, not ledger completion.
The Spark preflight's initial direct-field inference was rejected and corrected:
the policy is present through nested persisted reduction inputs. Spec consultation
independently agrees. No duplicate policy carrier is required.

The first full design review is now dispatched to the independent role cohort.
The frozen target has no active writer. Source-derived fixture refresh remains
pending: regenerate_recipe_v19.py fails on the current recipe schema with
KeyError direct_negative_cases. No canonical generated bytes or pins were
replaced by that failed candidate-only experiment. This is recorded evidence
work, not a new external-owner approval requirement.

## Current Evidence

The root-run closed ordering model passes 14 checks in 0.10s (`feasibility.log`):
interleaved sources, stale head with zero writes and successful retry, lost ack,
changed duplicate content, empty-operation source finalization, prefix/head
anchoring, reordering/duplicate/corruption and nested typed payload rejection.
Initial failure is retained. This uses a minimal JSON hash model, not production
CTV, complete audit membership, actual backend CAS or checkpoint trust.

`terminal-grammar-map.md` records exact sealed intent/receipt coupling and the
head-precondition conflict with current blanket immutable-record absence checks.
`activation-checkpoint-map.md` is an inspected authority map, not a new contract.
One independent spec readiness consultation is running; this is not candidate
approval. A simultaneous test-review spawn hit agent capacity and is deferred
until a slot becomes available. No production group persistence was changed.

The digest consultation found and resolved the model's ambiguous group result
input. Final model evidence is 19 passing checks in 0.13s, with all six required
test evidence actions closed by targeted independent consultation. This is a
locally verified ordering/DAG component; full ledger design is not approved.
`closed-contracts.md` specifies the proposed boundaries; exact registered bindings,
activation/backend proof and checkpoint contract approval remain outstanding.

## Production Registry Discovery

Root distinguished normative runtime registration (SIA2676-2730/2825-2868) from
the nonoperational 56-root fixture compiler (SIA9288). The former full registry
owner is not implemented; existing envelope equality checks and bootstrap fixed
bindings do not replace it. `binding-authority-map.md` is coordinator-corrected.
Do not extend the fixture's closed inventory as a runtime registration shortcut.
The real-backend feasibility worker owns only backend_feasibility.py and its
test file; root owns pytest and all other current artifacts.

## Real Backend Feasibility

Root ran the JSONL MemoryPlane probe through its public conditional batch API.
Initial run: one pass and one test-regex mismatch (genesis uses absence, not
digest precondition). Root split genesis/existing-head cases and added a final
immutable-result collision case. Final: four passed in 0.93s. Exact files and
command are in backend-evidence.json. Snapshot equality proves no partial writes;
reopening a new backend proves persisted entry/result recovery. Neutral records
intentionally prove backend mechanics only, not semantic governed admission.

Current construction findings: the typed full production profile registry is
specified but absent. Existing envelope primitives and fixed bootstrap bindings
can be reused, but they cannot declare a new observation binding trusted. The
56-root compiler is explicitly nonoperational fixture authority. Runtime schema
registration must be resolved at its canonical owner before this draft is
implementation-ready. No user policy or real signature is required for that work.

## Registry Contract And Profile Identity Check

`runtime-registry-contract.md` defines protected ownership, embedded-binding
selection before body decode, exact read/write status handling, schema inputs,
the observation registration inventory and its discrimination matrix. It remains
a construction proposal; replay/page field closure and profile byte authority
are not falsely marked complete.

A read-only executable probe retained in `profile-identity-discrimination.json`
shows that the current runtime profile digest equals the test-only fixture's
published digest, but the prescribed encodings differ for the same map:
encoded JSON key order versus scalar key order, and no LF versus terminal LF.
The current primitive codec cannot simply be declared the full registered
profile. An independent spec consultation is assessing the governing authority
and compatibility boundary. No production or canonical design bytes changed.
Backend probe Ruff checks pass; its four-test evidence is retained.

Delegation: `registry_contract_consult`, spec_auditor, read-only bounded
construction consultation on Section 3.15.1, current codec, test-only fixture
boundary and proposed registry API. Root is sole document writer and test owner.
This is not a full candidate review or approval.

Consultation completed: two findings confirmed, both Not applicable /
blocks_approval / persisted-contract governance. The operational profile and
outer-envelope compatibility policy require an owner decision; neither is
resolved by the generic registry specification. `profile-decision.md` contains
the recommended new operational profile with exact historical preservation and
a fixed outer-envelope dispatch boundary. The smallest unblock is approval of
that compatibility direction, not release keys, signatures or quality thresholds.
The earlier no-external-decision statement is superseded by this discovery.

## Owner Decision Accepted

The user approved profile-decision.md on 2026-09-06. The profile/envelope
choice is unblocked; exact published grammar and downstream contracts still
require review. Root owns replay/snapshot construction and all canonical files.
The existing group_projection_owner is the sole writer of operational-profile.md
only; this is a bounded design drafting task, with no production edits or tests.
A new worker spawn hit capacity; the idle worker was reused.

## Approved-Direction Construction Evidence

Root completed replay-snapshot-contract.md and readiness.md, including exact
memory-plane snapshot CAS forwarding and concrete provider/capability roots.
The profile writer completed operational-profile.md. Root corrected literal
types and transitive nested policy commitments; all candidate files are now
root-owned. The full candidate is not yet frozen: registry consultation is
running and concrete schema publication inputs remain to be reconciled.

Independent numeric_runtime_owner authored independent-profile-derivation.json
without reading the root derivation. Root compared literal grammar bytes, the
entire 1168-byte LP preimage and final profile digest: all match. This proves
only profile-source construction, not registry/compiler parity or runtime use.
Grammar digest: 960df37a00b887f009941cc3ada0a5b84276de6af626bced51dc7747e890b822.
Proposed profile digest: a6da0b15af67134cf5199b4d925e6d3c225ff1c239c6e1c9d039753b5342ebe0.
Source identity is recorded in both derivation artifacts.

Whitespace checks pass. WorkPlan split verification initially reported the
changed resume hash; root refreshed that declared artifact and bundle/pin.
The subsequent verifier/self-test remains blocked by the retained historical
candidate identity's HEAD mismatch. No historical identity was rewritten into
current certification. The already-required final current-candidate capture
and verifier run remain open in the parent coordination evidence package.

## Storage Prerequisite Completed

The linked snapshot-revision slice is independently approved at
e84b6eaae5242b5cc94d7e032675b558993f30fc079833112ef20f6439514ea3.
It implements the full-write token and guard through service/store APIs and
preserves existing data revision and UOW no-op behavior. Parent ledger remains
partial. Resume profile/schema publication from operational-profile.md and
readiness.md; no user decision or production signing is required for this step.

## Registry And Retrieval Construction Checkpoint

The user requested completion of registry publication and ledger/retrieval
integration. The finite publication inventory now exists in schema-publication.md;
it is not a published registry. Root closed exact native result locator fields
and identity recomputation, purpose-specific snapshot models, revision-free
payload model alternatives, cursor purpose/domain and deployment manifest pins.
The original proposed manifest had extra fields inconsistent with the profile
grammar; the source-role manifest and protected deployment pins are now distinct.

The existing group worker authored the inventory and then reconstructed the
policy language in operational-profile.md as its sole writer. Root verified
the changes and added explicit external-preimage dependency closure. The finite
policies distinguish ordinary, self-digest, signature-only cursor and the fixed
checkpoint preimage. The literal grammar-role bytes are unchanged; complete
registry and decoder/vector outputs are still implementation obligations.

Spec consultation SPUB-01 and SPUB-02 are confirmed Not applicable /
blocks_approval / architecture, handled as determinate contract-conformance
actions: union aliases cannot be model roots, and a snapshot cannot infer a
union discriminator from an enclosing purpose. Both now have explicit model
alternatives. Targeted verification is pending. These were construction checks,
not a frozen review; the full design review allowance remains unused.

The authority worker mapped retrieval-authority.md. Root verified native claim
authority fields and existing projection-history current/historical validators,
but challenged its cited native publication callsite and mixed temporal/trust
generation interval derivation. A bounded followup is checking those exact
claims. Compact graph records alone do not prove missing source authority;
retained native plan/evidence and persisted projection generations must be
traced before introducing any new persisted truth.

Root owns all documents after worker completion and all test processes. No
production changes or new test results belong to this construction checkpoint.
Prior snapshot/terminal test evidence retains its previously bounded identity.
No new external decision or production signing is requested.

## Confirmed Public Contract Blocker

The preceding no-external-decision statement is superseded by the completed
projection-authority reconstruction. Root verified the native group commit
entrypoint at atomic_store.py:11409 and event/replay/reference publication at
11720-11870. It does not publish projection-history generations. The generic
terminal publication helper at 12735 does. Earlier delegate claims using the
clarification or preflight calls as proof of native publication are withdrawn
and corrected in retrieval-authority.md.

More importantly, SIA31530 exposes a single claim selection and interval, while
production owns independently advancing temporal/trust selections. The source
design does not define their combination. Root inspected temporal selection
changes at projection_history.py:6150-6198 and the separate pointer selectors;
independent spec consultation confirmed Not applicable / blocks_approval /
external decision. Tests or a registry declaration cannot select a new public
semantic rule. No full candidate review was launched on this unresolved shape.

projection-observation-decision.md gives the concrete recommended correction:
separate typed temporal/trust observed records, each with its own native
generation and ordered publication authority, and matching comparator contracts.
The alternative needs a new canonical combined projection owner. The smallest
unblock is the owner's choice between these public semantics; actual release
signing, keys and statistical thresholds are unrelated.

The registry compatibility consultation also confirmed a determinate correction:
native digest-bearing values use ordinary profile-3 fields and their pinned
native validators, never profile-3 rehashing. schema-publication.md records that
rule and its required mutation families. Raw registry role files, publication,
native projection/ledger CAS and public retrieval remain unimplemented. This
construction checkpoint changed documents only and does not close M5.

## Design Closure

Coordinator approval binds design-candidate-final.json, digest
215ab5f272d7b27589da04c9c1dd4a9fa0f1d8f01413d542ea72bffa4c924b9e.
The full independent cohort and targeted conformance reviews have no remaining
validated P1/P2 or required governance/evidence finding. The determinate
corrections specify immutable status permissions, source-manifest raw-byte hash,
whole-file source snapshots, immutable native publication evidence and historical
prefix derivation, and production-entrypoint test owners/counterfactuals.

Remaining implementation outputs are raw profile source files, registry compiler
and independently authored vectors, concrete runtime owners and bindings, and
all runtime/restart/compatibility proof. None is claimed by design approval.
The existing three source gates passed after legitimate CTV/structural derivation;
this does not certify future runtime changes or external statistical acceptance.
