# M3 Temporal Evidence Trust Resolution

- Work ID: semantic_ingestion_m3_temporal_trust_resolution_2026_08_02
- Work type: design
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-08-02
- Last updated: 2026-08-02
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/design-revision.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md`; user decision recorded 2026-08-02
- Expected outputs: closed temporal evidence trust-resolution semantics, typed contract updates, verification matrix, and implementation-ready M3 handoff

## Objective

Replace the formerly undefined source/text bound-combination behavior with a closed,
provenance-preserving rule: only trust-policy-eligible temporal evidence may
resolve valid time; the uniquely highest-trust eligible evidence governs;
byte-semantically equal evidence co-supports; equally ranked non-identical
evidence remains contested with both sources retained and creates no committed
temporal assertion.

## Completion Contract

The design completion contract in `.agents/PLANS.md` applies. The design must
define the complete ranking, eligibility, equality, disagreement, absence,
open-bound, and provenance algebra; typed persisted outcomes; compatibility and
migration behavior; measurable acceptance tests; and leave no hidden semantic
choice for M3 implementation. Fresh spec, correctness, and test review must
leave no unresolved approval blocker or validated P1/P2 design defect.

## Scope

Included: SIA-R06 temporal evidence selection when authenticated source and
certified textual evidence coexist; required interactions with SIA-R05 and
SIA-R12; accepted/unresolved outcome contracts; verification and M3 handoff.

Excluded: changing general trust decay, graph conflict arbitration, replay
winner semantics, statistical policy values, or M4/M5 behavior.

Deferred: operational trust-policy values remain externally provisioned. The
design uses the existing typed eligible-authority and rank policy rather than
inventing thresholds.

## Constraints And Invariants

- Raw temporal evidence and provenance remain immutable and distinct.
- Eligibility and rank come only from the selected server-owned trust policy.
- No caller, proposer, or analyzer may self-assign trust.
- Equal values under different provenance remain separate evidence even when
  they co-support one resolved interval.
- Equally ranked non-identical evidence is contested, never tie-broken by
  receipt order, source order, identifier, or model confidence.
- Candidate evidence cannot mutate committed truth before validation and the
  atomic transaction boundary.

## Sources Of Truth

1. `docs/design/memorii_spec.md`
2. `docs/design/memorii_storage_details.md`
3. `docs/design/event_model.md`
4. `docs/IMPLEMENTATION_RULES.md`
5. `docs/design/semantic_ingestion_architecture.md`
6. User decision of 2026-08-02: humans prefer sufficiently trusted evidence,
   choose the higher-trust source, and preserve equal-high-trust disagreement
   as two sourced contradictory answers.

## Current State

Verified: the prior design exposed a source/text bound-combination outcome but defined no
construction policy, allowed bound pairs, algorithm, or fingerprint. Existing
`PredicateTrustRule` already defines eligible authority classes, ranks,
incomparability, equal-rank conflict behavior, and co-support for equal values.

Interpretation: "high enough" maps to policy eligibility, avoiding a new
implicit numeric threshold. Complementary open bounds are not stitched; each
evidence item is evaluated as its own interval under the same selection rule.

## Assumptions And Open Questions

- Verified facts: trust eligibility/rank are server-owned typed policy data.
- Working assumptions: non-identical includes any different open/closed bound,
  instant, basis, or interval; semantically equal interval values can co-support
  while provenance remains distinct.
- Unresolved questions: none currently.
- Decisions requiring external input: none currently.

## Requirements Ledger

| ID | Requirement | Source | Priority | Acceptance criteria | Status |
| --- | --- | --- | --- | --- | --- |
| M3-TR-01 | Use only policy-eligible temporal evidence. | User; SIA-R06 | Required | Ineligible evidence never resolves valid time. | specified |
| M3-TR-02 | Select the uniquely highest-ranked eligible interval. | User; trust policy | Required | Lower-ranked disagreement is retained but cannot override the selected interval. | specified |
| M3-TR-03 | Co-support equal interval values without collapsing provenance. | User; SIA-R12 | Required | One interval resolves and every evidence item remains distinct. | specified |
| M3-TR-04 | Preserve equal-rank non-identical evidence as contested. | User; trust policy | Required | Both sourced alternatives persist; no temporal assertion commits. | specified |
| M3-TR-05 | Never stitch complementary bounds implicitly. | Ambiguity closure | Required | Non-identical open/closed intervals use ranking or contest rules only. | specified |
| M3-TR-06 | Bind every temporal decision to one complete trust and temporal policy snapshot at one server-owned coordinate. | M3-DREV-001; SIA-R06/R12 | Required | Snapshot bytes/digest/fingerprint and coordinate revalidate unchanged through CAS. | specified |
| M3-TR-07 | Use one authoritative content-addressed temporal decision closure. | M3-DREV-004; SIA-R12 | Required | No duplicated result fields may diverge; all persisted consumers compare the closure first. | specified |
| M3-TR-08 | Retain every independently certified textual candidate. | M3-DREV-002; SIA-R05/R06 | Required | Multiple textual candidates enter the same selection closure with no positional choice. | specified |
| M3-TR-09 | Preserve complete temporal closure in committed and non-committing artifacts. | M3-DREV-003; SIA-R10/R12 | Required | Claim/action, planning, event/replay, expected/observed, and terminal output retain exact closure membership. | specified |
| M3-TR-10 | Reject all pre-closure and legacy accepted temporal bytes. | M3-DREV-004 | Required | No upcast, fallback, or synthetic compatibility outcome is accepted. | specified |
| M3-TR-11 | Bind each temporal closure to exactly one operation and its sealed scope/semantic assessments. | M3-DREV-005; SIA-R05/R06/R10/R12 | Required | Cross-operation closure, span, assessment, order, or digest substitution fails before graph effect. | specified |
| M3-TR-12 | Carry exact role-bound operation temporal bindings through every temporal transition and terminal carrier. | M3-DREV-006; SIA-R06/R10/R12 | Required | Correction replacement/transition, retraction, identity, planning, event/replay, expected/observed, and terminal forms reject omission or role/binding swaps. | specified |
| M3-TR-13 | Make assessment and durable/planning record ownership role-specific and closed. | M3-DREV-007; SIA-R05/R06/R10/R12 | Required | Multi-role operations reject role cross-wiring; authoritative claim/action/identity schemas preserve exact binding bytes through events and replay. | specified |
| M3-TR-14 | Seal post-alignment attachment and planning-coordinate semantics. | M3-DREV-008/009; SIA-R05/R06/R10/R12 | Required | Proposal-scoped analysis binds only after alignment; planning valid intervals remain exact and identity recorded time materializes deterministically. | specified |
| M3-TR-15 | Make attachment preimages and lineage planning materialization replay-recomputable. | M3-DREV-010; SIA-R05/R06/R10/R12 | Required | Scope embeds attachment; attachment/decision canonical preimages reject mutation/self-inclusion; only lineage recorded time changes at commit. | specified |
| M3-TR-16 | Make scope attachment consensus and candidate projection exact. | M3-DREV-011; SIA-R05/R06/R12 | Required | Scope digest, embedded attachment consensus, candidate IDs, and spans reject any A/B substitution through replay. | specified |

## Non-Goals

- Choosing concrete authority classes or ranks.
- Combining partial intervals into a new interval not asserted by one evidence
  source.
- Selecting a winner between equal-rank conflicting evidence.
- Altering graph-wide historical conflict or replay policy.

## Existing-System Analysis

The canonical temporal and trust schemas live in the semantic-ingestion design.
M3 production contracts do not yet exist. M1 retains authenticated source
temporal evidence; M2 can persist closed typed terminal artifacts. The design
revision must therefore freeze the M3 resolver and accepted-artifact contract
before implementation begins.

## Alternatives Considered

- Exact equality only: safe but discards the user's requested higher-trust
  resolution behavior.
- Stitch complementary bounds: rejected because it synthesizes a range no
  single source asserted and the authorization semantics are undefined.
- Trust-ranked selection with equal-rank contest: selected because it follows
  the user decision and reuses existing policy authority.

## Failure And Operational Analysis

Missing policy, no eligible evidence, incomparable top evidence, ambiguous
rank, equal-rank disagreement, invalid interval, provenance mismatch, and
unknown variants fail to unresolved with immutable evidence and zero graph
effect. Policy revisions do not reinterpret prior accepted artifacts; migration
requires a new explicit projection. Rollback restores the prior policy and does
not rewrite historical evidence.

## Verification Strategy

Use a complete matrix over eligibility, higher/lower/equal/incomparable ranks,
equal/different/open intervals, source/text order permutations, provenance and
basis substitutions, missing/stale policy, and unknown variants. Assert exact
selected or contested typed output, retained evidence, deterministic bytes, and
zero graph effect for unresolved outcomes.

## Frozen Contract And Handoff

### Inputs and authority

The M3 resolver takes only independently validated, immutable temporal
candidates: an authenticated source interval and zero or more independently
certified textual intervals. Each contains a whole `TimeInterval`, provenance, and the
authenticated `SourceAuthority` for the evidence-bearing source. Its predicate
and scope select one server-owned `PredicateTrustRule`; its temporal validity
selects one server-owned `PredicateTemporalRule`. Both policy snapshots use the
same server-owned `arbitration_as_of` and carry exact fingerprint and snapshot
digest. Proposer fields, caller preference, evidence arrival order, source
count, identifier, and model confidence are not resolver inputs.

An absent interval creates no candidate. A `TimeInterval` has a required start
and optional open end; an allowed open end is a complete assertion, while a
disallowed one is invalid rather than a partial fragment. Missing/invalid
provenance or authority, stale/ambiguous policy selection, unknown class,
unknown variant, duplicate candidate ID, or non-canonical candidate order is a
typed non-promoting failure.

### Deterministic resolution

1. Retain all candidates and validate their policy binding.
2. Exclude policy-ineligible candidates from selection but retain them in the
   terminal artifact.
3. Partition eligible candidates by semantic interval equality: same start and
   same end variant/value; `None` equals only `None`.
4. Compute maximal candidates under the predicate/scope-local immutable base rank
   and explicit incomparability relation. A candidate is maximal only if no
   comparable candidate has strictly higher rank.
5. With no eligible candidate, emit `unresolved`. If every maximal candidate
   has the same interval, emit `pass` and select exactly that asserted interval;
   all candidates of that equal interval remain separately recorded
   co-supporters. If maximal candidates contain different intervals, emit
   `contested`, enumerate each top candidate, and emit no accepted temporal
   evidence or graph assertion.

The result never constructs an interval. In particular it never fills, joins,
intersects, unions, narrows, widens, or otherwise combines open or finite
bounds asserted by different evidence items. A high-ranked interval may govern
a different lower-ranked interval; equal-ranked or incomparable non-equal top
intervals remain contradictory alternatives with every source visible.

### Typed persistence and compatibility

`TemporalEvidenceDecisionClosure` is the sole authoritative status, selected/
contested set, resolved interval, rule, policy identity, and arbitration
coordinate. `TemporalEvidenceAssessment` and `AcceptedTemporalEvidence` carry
only the closure plus source evidence required to reproduce its candidates.
The accepted, durable, expected, observed, replay, and comparator paths compare
the closure before every derived visible field. Only `outcome="pass"` may
produce accepted evidence. `contested`, `unknown`, `fail`, and unresolved
operations retain their complete closure in the non-committing terminal artifact
and have zero graph effect.

`OperationTemporalDecisionBinding` is the sole cross-operation carrier. Its
preimage is constructed after separately sealed scope and semantic assessments,
so it contains their digests without a self-cycle. Every finite, open-end, and
atemporal M3 accepted claim/action has a structurally required (non-null)
binding; terminal non-committing outcomes carry the complete ordered binding
set for their operation. No loose closure list, nullable accepted binding, or
cross-operation candidate span is legal.

### M3-DREV-006 carrier inventory

Every cross-boundary carrier is closed as follows: accepted fact/action uses an
`assertion` binding; accepted correction uses distinct `replacement` and
`transition` bindings; accepted retraction and identity use `transition`.
The same role-bound binding is mandatory on source-authorized temporal
transitions, identity-lineage transitions, durable and planning temporal
transition records, canonical event payload/replay artifacts, expected and
observed transition records, compiled/planned/persistence binding sets, and
canonical/expected/observed operation terminal outcomes. `DerivedTemporalTransition`
has no accepted temporal evidence and is therefore outside this carrier family.
All binding sequences are ordered by `(operation_id, temporal_role, binding_digest)` and must
be byte-identical across group persistence, replay, and observation.

This is an unshipped M3 contract revision. There is no legacy accepted
bound-combination artifact to migrate. An implementation must reject every
pre-closure accepted byte and legacy serialized resolution tag before decode,
publication, replay, or upcast; no M3 compatibility upcast exists. A later
trust-policy migration may explicitly reproject an already accepted assertion,
but it cannot mutate its historical candidate evidence or turn a contested M3
terminal artifact into an accepted operation without a new source operation.
Rollback restores the preceding active policy for future arbitration and keeps
historical artifacts bound to their original fingerprints.

### Acceptance and attack matrix

| Family | Required proof | Expected result |
| --- | --- | --- |
| Eligibility | none, all ineligible, one eligible plus ineligible, policy-class substitution | only eligible candidates influence selection; all inputs remain retained |
| Rank | one unique highest, equal top, explicit incomparable top, lower conflicting evidence | unique top resolves; non-equal equal/incomparable top is contested; lower evidence cannot override |
| Equality | equal finite values, equal open ends, finite/open-end mismatch, start/basis/provenance substitution | exact values co-support without provenance collapse; every non-equal value follows rank/contest rules |
| Bound safety | source start/text end, source end/text start, overlapping, disjoint, contained, inverse arrival order | no derived interval is emitted in any case |
| Policy identity | stale, missing, duplicate, cross-scope, fingerprint/digest/coordinate mutation | typed non-promoting failure with zero graph effect |
| Contract closure | unknown enum, impossible candidate-kind fields, duplicate/unsorted IDs, selected/contested overlap | deserialization or semantic validation fails closed |
| Persistence | accepted/co-supported, contested, unresolved, retry/replay byte comparison | accepted artifacts reproduce all candidate/provenance/policy bytes; non-accepted paths write no temporal assertion |
| Compatibility | legacy tag, policy activation, rollback, migration/reprojection | legacy tags reject; historical evidence remains immutable and policy-bound |

Deterministic component/property tests establish this matrix. M3 does not claim
live trust-policy calibration or decay, M4 replay/event implementation, or
graph-wide claim arbitration evidence.

### Named M3 Evidence Ledger

| ID / requirements | Level | Oracle / fixture | Failure signal | Planned node / file | Gate |
| --- | --- | --- | --- | --- | --- |
| `SIA-T06-TR-ELIGIBILITY` / M3-TR-01, M3-TR-06 | unit + property | hand-authored policy/candidate matrices: none, all-ineligible, mixed, class substitution | result differs from closure-selected set or retained evidence is lost | `TemporalEvidenceResolver`; `memorii/tests/unit/core/semantic_ingestion/test_temporal_trust_resolution.py` | required M3 unit gate |
| `SIA-T06-TR-RANK` / M3-TR-02 | unit + property | unique high, lower conflict, equal/triple tie, all arrival permutations | any ordering-derived winner or lower override | same resolver/test file | required M3 unit gate |
| `SIA-T06-TR-INCOMPARABILITY` / M3-TR-02, M3-TR-06 | policy-validation + unit | canonical pair plus reversed, duplicate, self, and unknown-class mutations | policy activation or resolver accepts malformed pair; non-equal top does not contest | `TrustPolicySnapshot` validator; `test_temporal_trust_resolution.py` | required M3 contract gate |
| `SIA-T06-TR-EQUALITY` / M3-TR-03, M3-TR-07 | unit + serializer | equal finite/open-end intervals, unequal-rank equal-interval co-support without authority amplification, and equal values with basis/provenance substitutions | co-support merges provenance, amplifies authority, or closure/value mismatch passes | resolver + canonical codec; `test_temporal_trust_resolution.py` | required M3 unit/codec gate |
| `SIA-T06-TR-NOSTITCH` / M3-TR-05 | unit + property | open-end/finite disagreement, overlap, contained, disjoint, inverse text/source order; `end == start`, `end < start`, forbidden open end | invalid interval accepted or any output interval lacks one exact candidate source | interval validator/resolver; `test_temporal_trust_resolution.py` | required M3 unit gate |
| `SIA-T06-TR-TEXT-MANY` / M3-TR-08 | component | zero/one/many independently certified textual candidates, equal/different values | positional/confidence choice, omitted candidate, or unstated contestant | temporal attachment + resolver; `memorii/tests/unit/core/semantic_ingestion/test_temporal_attachment.py` | required M3 component gate |
| `SIA-T06-TR-SCHEMA` / M3-TR-06, M3-TR-07 | codec + contract | unknown tag, impossible field set, duplicate/unsorted IDs, stale policy/digest/coordinate, caller/proposer/model authority or provenance substitution at authenticated ingress | decode/semantic validation succeeds or any downstream call/mutation occurs | source-governance and canonical codec; `test_semantic_ingestion_contracts.py` | required M3 contract gate |
| `SIA-T06-TR-CLOSURE` / M3-TR-07, M3-TR-09, M3-TR-11 | integration + comparator | A/B interval, resolution-rule swap, selected/contested subset, two-operation binding/closure swap, binding reorder/permutation/digest, expected/observed terminal-membership mutations across reconciliation/CAS/replay/comparison | any mutation compares equal, commits, or produces an incomplete/cross-operation terminal binding | planner/compiler/event/replay/comparator; `memorii/tests/integration/test_semantic_ingestion_pipeline.py` | required M3 integration gate |
| `SIA-T06-TR-TRANSITIONS` / M3-TR-09, M3-TR-12 | integration + genesis/checkpoint replay | correction replacement/transition role swap, retraction, identity, planning/durable/event/replay/expected/observed transition and committed/non-committing terminal remove/reorder/swap | any transition/terminal carrier omits, reorders, or substitutes a role-bound binding without rejection | compiler/event/replay/comparator; `memorii/tests/integration/test_semantic_ingestion_replay.py` | required M3 replay gate |
| `SIA-T06-TR-ROLE-SCHEMA` / M3-TR-13 | contract + integration | one correction with distinct replacement and transition candidates; role assessment/binding, durable/planning claim/action/identity, mutation/event/replay role swaps | any role or authoritative-schema substitution survives codec, CAS, or replay | record codec/compiler/replay; `memorii/tests/integration/test_semantic_ingestion_replay.py` | required M3 schema gate |
| `SIA-T06-TR-ATTACH-PLAN` / M3-TR-14 | contract + fixed-point/replay | post-alignment attachment swap/candidate span mutation; planned interval coordinate substitution; identity commit-coordinate retry/replay mutation | raw analyzer operation invention, attachment mismatch, non-exact planning interval, or non-deterministic materialization survives | aligner/planner/compiler/replay; `memorii/tests/integration/test_semantic_ingestion_replay.py` | required M3 planning gate |
| `SIA-T06-TR-PREIMAGE` / M3-TR-15 | fixed vectors + codec/replay | attachment/decision every-field mutation, self-inclusion, domain swap, scope attachment omission, and every lineage-field preservation mutation | canonical digest/vector mismatch or any non-`recorded_at` lineage change reaches commit/replay | canonical codec/planner/replay; `memorii/tests/integration/test_semantic_ingestion_replay.py` | required M3 preimage gate |
| `SIA-T06-TR-CONSENSUS` / M3-TR-16 | component + replay | A/B stable-consensus, candidate-ID, candidate-span, and digest-only substitutions | scope/attachment equality mismatch reaches reconciliation, persistence, or replay | scope validator/replay; `memorii/tests/integration/test_semantic_ingestion_replay.py` | required M3 consensus gate |
| `SIA-T06-TR-STORE` / M3-TR-06, M3-TR-09 | backend conformance | real serializer, in-memory/filesystem store, composition root, CAS mismatch, retry | hidden lookup, stale closure, or partial publication | semantic store/coordinator; `memorii/tests/integration/test_semantic_ingestion_pipeline.py` | required M3 backend gate |
| `SIA-T06-TR-POLICY` / M3-TR-06, M3-TR-09 | integration + migration | rotation between attempts, explicit reprojection, rollback, unavailable/stale snapshot | historical closure rewrites or different snapshot commits | policy coordinator/compiler; `test_semantic_ingestion_pipeline.py` | required M3 policy gate |
| `SIA-T06-TR-LEGACY` / M3-TR-10 | codec + publication | pre-closure accepted bytes and every prior resolution tag under active/retired registry | decode, upcast, publication, or replay succeeds | event/replay schema registry; `test_semantic_ingestion_contracts.py` | required M3 compatibility gate |

## Milestones Or Experiments

### D1 - Freeze the temporal trust algebra

- Purpose: make M3 implementation determinate.
- Bounded scope: canonical design, this WorkPlan, and M3 implementation handoff.
- Expected artifacts: revised normative matrix and typed contracts.
- Verification method: direct source inspection plus independent reviews.
- Status: complete; canonical contract, typed outcomes, compatibility boundary,
  and verification matrix are drafted and await independent review.

### D2 - Review-remediation closure

- Purpose: close the reviewed snapshot, candidate-cardinality, and durable
  evidence-chain defects without changing the selected user semantics.
- Status: complete pending delta review.
- Evidence: canonical trust snapshot digest and canonical incomparability-pair
  algebra; exact snapshot/coordinate threading; plural text candidates;
  content-addressed decision closure through accepted/non-committing,
  planning/event/replay, and expected/observed paths; sole-closure authority
  with pre-closure rejection; named evidence ledger.

### D3 - Operation-bound temporal closure

- Purpose: prevent one valid temporal decision from being applied to a different
  accepted operation.
- Status: complete pending final delta review.
- Evidence: ordered operation binding with acyclic scope/semantic preimages,
  exact attachment/span ownership, binding-only cross-boundary carriers, and
  non-null accepted claim/action expected/observed bindings.

## Progress Log

- 2026-08-02: Confirmed the undefined complementary-bounds blocker. User chose
  trust-ranked human-style resolution with sourced equal-trust contradiction.
  Created this linked design operation. Next action: draft the closed canonical
  design revision and attack matrix.
- 2026-08-02: Replaced the undefined bound-combination path in the canonical
  design. The draft uses policy eligibility as "high enough", a partial-order
  top-evidence rule, interval-value co-support, and a non-committing contested
  outcome. It expressly forbids synthetic bound construction. Next action:
  independent spec, correctness, and test review of the frozen draft.
- 2026-08-02: Applied one coherent remediation batch for confirmed M3-DREV-001
  (P1), M3-DREV-002 (P2), and M3-DREV-003 (P2). The design now freezes trust snapshot
  digest derivation and boundary revalidation, canonical incomparability pairs,
  plural certified text candidates, and a durable content-addressed decision
  closure. Next action: delta review these changes against the named ledger.
- 2026-08-02: Applied targeted remediation for confirmed M3-DREV-004/P2:
  `TemporalEvidenceDecisionClosure` is now the sole authority for temporal
  outcome/value/rule/selection/policy/coordinate; pre-closure accepted bytes
  reject with no M3 upcast. Next action: focused delta review of closure
  authority, terminal expected/observed membership, and the expanded ledger.
- 2026-08-02: Applied final remediation for confirmed M3-DREV-005/P2:
  operation-bound temporal decisions replace loose closure tuples in every
  cross-boundary contract; the preimage order is explicit and accepted M3
  claim/action bindings are structurally non-null. Next action: final focused
  delta review of operation binding and the no-authority-amplification fixture.
- 2026-08-02: Applied consolidated carrier-family remediation for confirmed
  M3-DREV-006/P2. The complete inventory now carries role-bound operation
  bindings through transition and terminal forms, with correction
  replacement/transition swaps forbidden. Next action: final delta review of
  the carrier inventory and replay mutation matrix.
- 2026-08-02: Applied consolidated M3-DREV-007/P2 role/schema remediation.
  Scope and semantic assessments now bind `(operation_id, temporal_role)`;
  authoritative durable/planning claim, action, and identity schemas are
  defined with exact temporal bindings. Next action: final delta review of
  role-specific correction and schema propagation cases.
- 2026-08-02: Applied M3-DREV-008/009 and planning-coordinate remediation:
  post-alignment attachment bindings preserve analyzer ownership boundaries,
  while planning intervals and identity recorded time have closed deterministic
  representations. Next action: final delta review of attachment and planning
  fixed-point contracts.
- 2026-08-02: Applied M3-DREV-010/P2 attachment/preimage closure: scope now
  embeds replayable attachment bindings, event/replay carries their ordered set,
  and planning lineage preserves every durable field except recorded time.
- 2026-08-02: Corrected the binding-preimage wording: the decision-binding
  digest covers exactly its six non-digest fields and omits only
  `binding_digest`; no semantic contract changed. Next action remains the final
  focused delta review of M3-DREV-010 and the named evidence ledger.
- 2026-08-02: Applied M3-DREV-011/P2: scope attachment consensus and the
  embedded attachment projection are now exact-equality/replay-recomputed.
  Next action: final focused delta review of M3-DREV-011 and the named ledger.

## Evidence Log

- `docs/design/semantic_ingestion_architecture.md`: temporal matrix and
  `PredicateTemporalRule` lack a complementary-bound construction owner.
- Pre-implementation M3 test review independently reproduced the ambiguity.
- 2026-08-02 focused consistency check: all accepted, expected, and assessment
  resolution variants now use the trust-selection algebra; no prior undefined
  bound-combination tag remains in the canonical design or linked WorkPlans.
- 2026-08-02 remediation evidence: the exact closure is specified for source
  normalization, capability binding, assessment, reconciliation, compile/CAS,
  persistence, event/replay, and observation/comparison; contested output uses
  the same closure but is non-committing.
- 2026-08-02 binding evidence: every cross-boundary carrier now uses canonical
  ordered `OperationTemporalDecisionBinding` values rather than loose closures;
  the ledger exercises two-operation swap, reorder, permutation, and digest
  mutations through reconciliation, CAS, replay, and comparison.

## Decision Log

- Decision: map "trust high enough" to existing policy eligibility and select a
  unique highest-ranked eligible interval; equal-rank disagreement is contested.
  Date: 2026-08-02. Alternatives: equality-only and synthetic bound stitching.
  Rationale: user direction plus existing typed trust authority. Consequence:
  remove the prior undefined bound-combination outcome from accepted M3 semantics.
- Decision: interval equality is exact semantic `TimeInterval` equality (same
  start and same end variant/value), not byte identity and not provenance
  equality. Date/time basis and provenance are still separately immutable
  evidence and substitutions fail validation. Date: 2026-08-02. Rationale:
  permits sourced corroboration while preserving the SIA-R12 distinction.
- Decision: the resolution unit is a complete asserted interval; an allowed
  open end remains a whole interval. Date: 2026-08-02. Rationale: prevents
  implicit synthesis from partial-looking temporal evidence.

## Review Log

Review round 1 confirmed M3-DREV-001/P1 (snapshot authority chain), M3-DREV-002/P2
(candidate cardinality/no-stitch closure), and M3-DREV-003/P2 (durable decision
closure). All three are `changes_required`, implementation/design, and are
remediated by D2 pending independent delta verification. Review round 2 then
confirmed M3-DREV-004/P2 (duplicated temporal decision fields could diverge),
also `changes_required` / design / persistence compatibility. It is remediated
by the sole-closure contract above. Review round 3 confirmed M3-DREV-005/P2
(closure-to-operation identity was not closed), `changes_required` / design /
runtime integrity. It is remediated by D3. Review round 4 confirmed
M3-DREV-006/P2 (the carrier family was incomplete), `changes_required` / design
/ replay integrity. It is remediated by the carrier inventory above. Rounds
used: four. Review round 5 confirmed M3-DREV-007/P2 (multi-role assessment and
durable/planning schema family incomplete), `changes_required` / design /
durability. It is remediated above. Review rounds 6 and 7 confirmed
M3-DREV-008/P2 (post-alignment attachment identity) and M3-DREV-009/P2
(planning-coordinate representation); both are remediated above. Rounds used:
seven. Review round 8 confirmed M3-DREV-010/P2 (attachment absent from scope
preimage and planning lineage incomplete), remediated above. Rounds used: eight.
Review round 9 confirmed M3-DREV-011/P2 (scope attachment consensus could
diverge from embedded projection), remediated above. Final focused spec,
correctness, and test delta reviews approved canonical design revision
`5451fb354f79256cd95bf3d6ca2ec0796c40952b5d025bdb040b8ff2b08f94e8` at tree
baseline `42671e90f35edfc006583e5ddf889927d2602717`; all M3-DREV findings are
resolved and no new validated P1/P2 design defect was found.

Implementation-time publication audit found that M3 prose had been inserted
inside Python schema fences, making the already approved text unparsable by
the frozen traceability grammar. The coordinator classified this as a
syntax-only publication defect (`Not applicable` / `changes_required` /
generated-authority parsing) and authorized delimiter-only repair. No semantic
text or ordering changed. The original semantic-review checksum above is
superseded solely for implementation and generated-authority binding by raw
design SHA-256
`45727e6870e2087823bfe6250c3c3319a3d540e45fb66c686267409b087b2c1c`.

## Blockers And Limits

- Current blockers: none.
- Remaining validated P1/P2: `[]`.
- Remaining `changes_required`: `[]`.
- Iteration budget: bounded convergence under the parent implementation budget.
- Rounds used: nine design review rounds.
- Environment limits: no operational trust artifacts are required for design.

## Next Action

None. This design operation is complete; the linked implementation WorkPlan
owns the next action.

## Outcome And Retrospective

The M3 temporal trust-resolution design is complete and implementation-ready.
It closes policy eligibility/ranking, no-stitch safety, role-bound operation
attachment, durable/planning schema ownership, deterministic replay, and the
complete `SIA-T06-TR-*` evidence ledger. The canonical revision checksum above
is the implementation baseline; no external decision or validated P1/P2 design
gap remains within scope.
