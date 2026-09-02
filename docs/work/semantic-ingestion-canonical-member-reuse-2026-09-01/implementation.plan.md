# Canonical Member Reuse And Revalidation Elimination Implementation WorkPlan

- Work ID: `semantic-ingestion-canonical-member-reuse-2026-09-01`
- Work type: `implementation`
- Status: `active`
- Coordinator: sole writer (main thread)
- Created: 2026-09-01
- Last updated: 2026-09-01
- Parent WorkPlan:
  `../semantic-ingestion-canonical-encoder-hot-path-2026-08-27/implementation.plan.md`
  (its completion record scoped this unit: reaching <5s needs member-level reuse
  plus revalidation reduction as its own reviewed operation)
- Related WorkPlans:
  - `../semantic-ingestion-validated-canonical-closure-2026-08-17/design.plan.md`
    and its canonical design
    `docs/design/semantic_ingestion_validated_canonical_closure.md` (approved
    candidate v12, `Approved with follow-ups`; the Cross-Root Reuse and
    Writer Boundary sections govern the reuse contracts implemented here)
  - `../semantic-ingestion-validated-canonical-closure-2026-08-17/implementation.plan.md`
    (its active performance milestone — codec-level child-slice reuse and the
    production-bound digest counter — is executed by this successor operation)
  - `../semantic-ingestion-canonical-evidence-production-performance-2026-08-16/`
    (parent performance operation; owns the PBD-EXP-014 instrument and evidence
    directory this operation re-baselines as v2)
  - `../semantic-ingestion-validation-boundary-performance-2026-08-17/design.plan.md`
    (blocked on its own M3.1 route, but its frozen boundary classification —
    which boundaries are mandatory full-validation — governs which
    revalidation sites are eligible for internal reuse)
  - `../semantic-ingestion-canonical-evidence-default-on-2026-08-27/implementation.plan.md`
    (landed the default-on substitution whose ~36s residual this operation
    removes)
- Canonical inputs: the current tree at branch `semantic-indexing-m4`; the
  approved closure design and `implementation-acceptance-v12.md`; PBD-EXP-014
  v1 evidence; the frozen codec/proposal-vector/provider-compatibility/arena/
  provider-service suites; the encoder hot-path profile recorded in the parent
  plan.
- Expected outputs: member-level canonical reuse and same-trust-domain
  revalidation elimination on the enabled delivery path with byte-identical
  canonical output, all mandatory validation boundaries intact, and re-measured
  wall-clock evidence (v2) showing enabled median < 5s per delivery.

## Objective

Reduce the median enabled-mode wall clock per semantic delivery from the
recorded ~36s to under 5 seconds by (a) reusing already-validated canonical
members keyed by member digest across roots within one operation, per the
approved Cross-Root Reuse contract, and (b) eliminating redundant pydantic
revalidation of members proven identical by content digest within the same
trust domain, without weakening any validator, gate, accounting assertion, or
the canonical-evidence substitution contract.

## First Decision Record (2026-09-01)

The recorded direction is implementable as an implementation WorkPlan under
`$implement-design`; no bounded design pass is required first. Basis:

1. Member-level canonical reuse is an approved design:
   `docs/design/semantic_ingestion_validated_canonical_closure.md` (candidate
   v12 `Approved with follow-ups`) specifies the codec result, traversal-issued
   member index, certified child-slice consumption, writer boundary, capacity,
   and rollback contracts. The VCC implementation plan's own ledger records
   "codec-level child-slice reuse and the production-bound digest counter are
   not yet implemented (performance milestone)" — this operation executes that
   milestone as its successor.
2. Revalidation elimination, as scoped here, is inside the approved contract:
   the design freezes "only proven reconstruction and digest work is skipped"
   and `implementation-acceptance-v12.md` requires "semantic validators and
   every writer admission still execute in all modes". Digest-keyed reuse that
   bypasses revalidation only for content already validated in the same
   operation/trust domain (same concrete type plus structural equality with a
   certified instance, operation-local scope) is the already-landed, reviewed
   `CanonicalDigestVerificationScope` substitution pattern extended from
   digest-recompute skipping to reconstruction skipping.
3. The acceptance matrix's escalation boundary is not triggered by the planned
   shape: no public or persisted schema, canonical identity, trust ownership,
   capacity limit, rollback semantic, or production composition model changes.
4. The blocked validation-boundary design does not govern this mechanism: its
   blocked status concerns its own capability-threading route and the former
   M3.1 percentage debate; its frozen mandatory-boundary classification is an
   input this operation respects, not a competing mechanism.

Escalation back to `$build-design` is required if reaching <5s would need any
of: skipping semantic validators at first admission, validating untrusted
input by digest proximity, changing the arena's trust/capability semantics,
or altering public/persisted schemas or canonical identity.

## Completion Contract

The operation completes only when:

- STEP ZERO evidence exists: both modes re-baselined at the pre-change HEAD
  with the PBD-EXP-014 harness (v2 evidence alongside v1), digest-count
  determinism and post-H8 per-child accounting asserted.
- Enabled median per delivery is < 5s at the final revision, measured by the
  same v2 harness with the same protocol (samples, seed, run order manifest).
- Disabled-mode behavior and accounting are unchanged (digest-call counts and
  lifecycle accounting within their recorded values).
- Digest-count determinism across samples holds in both modes; structural
  output equality across modes is carried by the diametric parity gate
  (`test_canonical_evidence_mode_parity.py`) staying green (cross-mode byte
  equality is not well-formed: per-delivery unique identities).
- Encoder byte identity is gated by the frozen suites (consensus codecs,
  proposal vector, provider compatibility, arena, provider service) green.
- Every mandatory validation boundary still executes full validation:
  public/provider ingress, transport decode, persistence admission and
  transaction commit, reload/replay/recovery, writer admission, and
  cross-operation boundaries. The six staged validations remain separate.
- First-admission semantic validators are never skipped; reuse only replaces
  reconstruction/digest/revalidation of content certified within the same
  operation scope.
- Focused suites pass during construction; the broad gate runs once at the
  final revision; ruff and the identity-hygiene gate are clean at the final
  revision.
- The linked VCC implementation plan's performance-milestone status is updated
  with this operation's evidence, and current-state documentation is updated
  if implementation changes make it stale.
- If <5s is not reachable without a contract change, the exact blocker,
  measured residual, and the required decision are recorded and the operation
  stops as blocked — no silent weakening to make a number pass.

## Scope

Included:

- member-digest-keyed reuse of certified canonical bytes, spans, and validated
  instances across roots within one operation (codec-owned);
- elimination of redundant pydantic revalidation at internal composition
  boundaries where the input authority is an already-validated operation-local
  typed value and no trust, serialization, persistence, or mutation boundary
  intervenes;
- removal of whole-object re-encodes that re-encode identical members
  (duplicate per-member encodes, reload-comparison re-encodes, sort-key
  re-encodes) where a certified equivalent exists in the operation scope;
- measurement evidence (v2), profiles, and the linked-plan status records.

Excluded:

- any change to canonical bytes, digest algorithms/domains, persisted or
  public schemas, replay meaning, writer policy, or transaction semantics;
- cross-operation, cross-process, or process-global caches;
- digest-proximity validation of untrusted input in any form;
- the six validation stages merging or reordering;
- unrelated performance refactors outside the delivery hot path;
- live-provider or operational certification.

Deferred:

- any contract change that the escalation boundary triggers returns to
  `$build-design` as a separate operation;
- follow-up performance work outside canonical reconstruction/revalidation.

## Constraints And Invariants

- User mandate: "For Memorii to be broadly used, it needs to be highly
  performant." Target: enabled median < 5s per delivery.
- The six validation stages (prompt schema, transport parse, domain-semantic,
  provenance, lifecycle/commit, transactional persistence) remain separate.
- Digest-keyed reuse may only bypass revalidation of content already validated
  in the same trust domain; never validate untrusted input by digest
  proximity. Same concrete type plus structural equality with a certified
  operation-local instance is the minimum hit condition (the landed
  substitution-contract shape).
- Candidate vs committed state, provenance, per-operation stage/seal/lease
  semantics, and the specialized digest owner rule
  (`BootstrapGraphTerminalPublicationIntentV3` retains its concrete owner-issued
  validation provenance) stay intact.
- Mandatory full-validation boundaries per the validation-boundary census:
  public/provider ingress; model/provider output and adapter input; raw or
  canonical byte decode; persistence admission and transaction commit;
  persisted read, reload, replay, and recovery; cross-operation and process
  boundaries; any copied, constructed, mutated, or capacity-fallback value.
- Writers always perform fresh local admission on exact committed bytes.
- Canonical output remains byte-identical; frozen suites gate it.
- Evidence classes stay distinct: deterministic tests, fake-oracle plumbing,
  and this wall-clock measurement are never reported as provider success.
- Environment: run from `memorii/` with
  `../.venv/bin/python3.12 -W error -m pytest <selection> -p no:cacheprovider`;
  long measurement runs execute in the background with output saved to files.

## Identity And Coordinate Hygiene

| Identity | Class | Allowed surface |
| --- | --- | --- |
| `CMR-*` requirement/experiment IDs, milestone labels, v2 evidence names | planning/evidence coordinate | WorkPlan, evidence, review records only |
| Member-reuse runtime symbols (codec result accessors, member-evidence lookup, certified-instance memo) | behavioral identity | Named for the owned contract; production/test code |
| Measurement harness and evidence file names (`pbd-exp-014-...-v2.json`) | evidence identity | The production-performance evidence directory |
| Existing canonical/arena identities (`CanonicalEvidenceArena`, `CanonicalCodecResult`, `CanonicalMemberEvidence`, `encode_typed_value_with_spans`) | behavioral identity | Unchanged meaning; no drift |

No planning coordinate enters production or test filenames, symbols, schemas,
fixtures, diagnostics, CI jobs, or serialized outputs.

## Requirements Ledger

| ID | Requirement | Acceptance criterion | Status |
| --- | --- | --- | --- |
| CMR-001 | Re-baseline both modes pre-change | v2 evidence JSON recorded at the pre-change revision; determinism and accounting assertions pass | complete |
| CMR-002 | Revision-bound reuse map | Profile confirms remaining cost attribution and lists every whole-object re-encode and internal round-trip site with mandatory/internal classification before production edits | complete |
| CMR-003 | Member-level canonical reuse | Certified member bytes/spans/instances are reused across roots within the operation; identical members are encoded once; canonical bytes unchanged | complete (fused splicing emitter + lowering/string/canonicity memos) |
| CMR-004 | Revalidation elimination (internal only) | Same-trust-domain certified-instance reuse replaces internal `model_dump`/`model_validate` round-trips; mandatory boundaries unchanged; first-admission validators always run | landed for the prepare edge, prepared-source repositories, and provider post-boundary wrappers; graph-planning/event-replay clusters remain follow-up candidates |
| CMR-005 | Accounting and parity | Disabled-mode digest counts and lifecycle accounting unchanged; digest-count determinism holds; parity gate green | pending |
| CMR-006 | Performance target | Enabled median < 5s per delivery on the v2 harness at the final revision | pending |
| CMR-007 | Gates | Frozen byte-identity suites green; broad gate once at final revision; ruff and identity hygiene clean | pending |
| CMR-008 | Linked-plan and docs currency | VCC implementation plan performance-milestone status updated; stale current-state docs corrected | pending |

## Milestone Roadmap

| Milestone | Observable vertical outcome | Requirements | Status |
| --- | --- | --- | --- |
| STEP ZERO re-baseline | v2 wall-clock evidence for both modes at the pre-change HEAD | CMR-001 | complete |
| Reuse map and profile | Revision-bound cost attribution and site-by-site mandatory/internal classification recorded; production edits authorized only after `ready` | CMR-002 | active |
| Member-level reuse slice | Certified member reuse lands on the encode hot path with frozen-suite gates green | CMR-003 | pending |
| Revalidation-elimination slice | Internal round-trips replaced by certified-instance reuse; focused suites green | CMR-004 | pending |
| Measurement and gates | v2 re-measurement at final revision; broad gate once; all gates clean | CMR-005, CMR-006, CMR-007 | pending |
| Closure | Linked-plan status, docs currency, completion record | CMR-008 | pending |

## Measurement Protocol

- Instrument: the PBD-EXP-014 harness
  (`../semantic-ingestion-canonical-evidence-production-performance-2026-08-16/evidence/pbd_exp_014_default_on_wall_clock.py`),
  re-pointed to a v2 evidence path alongside v1, measurement-identical
  (samples, seed, child timeout, assertions, manifest shape).
- Long runs in the background with output saved to files; never piped through
  a consuming filter.
- Paired same-machine-state probes supplement batch medians when load makes
  batch runs incomparable (recorded caveat from the parent plan).

## Progress Log

- 2026-09-01: opened. Preconditions verified: legacy-path-removal plan CLOSED
  (completion record 2026-09-01; broad gate green at `21dcaf3`; header status
  corrected to `complete` in `34a5230`); encoder-hot-path plan complete (body
  record; header corrected in `34a5230`); ruff clean at `5aac9af`+`34a5230`.
  First Decision recorded above: `$implement-design`.
- 2026-09-01 (STEP ZERO complete): v2 harness
  (`../semantic-ingestion-canonical-evidence-production-performance-2026-08-16/evidence/pbd_exp_014_default_on_wall_clock_v2.py`,
  measurement-identical to v1, output re-pointed to
  `pbd-exp-014-default-on-wall-clock-v2.json`; script sha256
  `19153b6931e6a3983e7aa2a94c887dbcdb9b5a4e2264f1ac254ce4c1d30f9cf6`) at
  `34a5230`: **enabled median 49.00s** (min 36.62 / max 62.94), **disabled
  median 109.87s** (min 73.38 / max 130.50); digest calls exactly the recorded
  **237 vs 43,756**, deterministic across samples; post-H8 accounting asserted
  in every child. Run log: `evidence/step-zero-baseline-run.log`. The current
  HEAD is ~13s slower than the pre-slice-6 recording — confirms that every
  prior number predates the final revision. Target <5s requires ~10x.
- 2026-09-01 (CMR-EXP-001 census, `evidence/cmr-exp-001-census-v1.json-line`):
  one enabled delivery with pure counters: **120 `encode_semantic_contract_result`
  calls, 79 unique `(type, id)` pairs** — an object-identity memo alone saves
  only 41 calls (34%). Dominant same-instance multiplicities:
  `BootstrapAnalysisLaneResultV3` 24 calls / 12 unique (the stage's per-member
  double encode), `BootstrapNormalizationRequestCoreV3` 9/7,
  `BootstrapSemanticReductionAuthorityMemberV3` 9/7,
  `BootstrapSourceNormalizationResultV3` 6/5. Decodes: 14 calls / 10 unique
  `(type, bytes)` pairs. Conclusion: identity memoization is necessary but far
  from sufficient; the remaining cost is per-encode pipeline depth (double
  byte-emission cross-check, per-span member digests, whole-tree codec
  revalidation) and non-codec pydantic round-trips.

- 2026-09-01 (CMR-EXP-004/004b shared-instance census,
  `evidence/cmr-exp-004*-v1.json-line`): 75,325 model-lowering visits across
  22,833 unique instances — **69.7% of visits are same-instance repeats**,
  concentrated in the deep prepared-source tree members (text artifacts,
  spans, proofs; thousands of visits each). Member-granular identity reuse
  has the coverage the whole-object memo lacked.
- 2026-09-01 (member-reuse slices landed; profiles CMR-EXP-005..007 in
  `evidence/`):
  - **Fused member-splicing emitter**: `encode_typed_value` (unbudgeted
    path) now emits in one normalize+emit walk (`_emit_canonical`) whose
    operation-scoped memo replays bytes previously emitted for the same
    container node — the approved Cross-Root Reuse contract's child-slice
    consumption. A first two-phase memo attempt saturated its entry bound
    (measured 32,768/32,768 entries, 15.4MB) and broke node identity
    mid-tree; the fused form retains only emitted bytes (12MiB cap,
    256B recording floor, no eviction) and post-order recording fills the
    deep high-multiplicity members first. The reference two-phase traversal
    remains authoritative for budgeted (`check`-carrying) encodes, the
    with-spans pipeline, and the decode canonicity cross-check; the decode
    check runs unmemoized. Byte identity is gated by a differential suite
    (all container/wrapper/leaf families, in-scope repeats, shared
    subtrees) plus the frozen codec/vector/compatibility suites.
  - **Value-keyed string memo** (strings immutable → value key sound) and
    **byte-exact canonicity-verdict replay** for `decode_typed_value`
    (94 decode calls over 28 unique byte strings per delivery; parse and
    typed validation still run fresh every call — only the redundant
    re-encode comparison for already-verified bytes replays; bounded
    variants keep exact behavior).
  - **Lowering memo** on the digest-verification scope
    (id-keyed, member-path bound) and an **identity fast path** in
    `_digest_verification_hit`.
  - **Lazy schema completion**: `_BootstrapV3Contract.create` resolves its
    own class from module globals before falling back to the family-wide
    namespace cascade (15 distinct classes tripped the guard per delivery,
    each paying a ~114-model rebuild they did not need).
  - **Certified round-trip replay** (`certified_roundtrip`): the
    internal-composition `model_validate(model_dump())` sites whose input
    is an already-validated same-operation instance — the
    `TextPreparationService.prepare` edge (the validation-boundary design's
    reference-proven selection), the in-memory and atomic-store prepared
    source repositories, and the two provider-ingestion post-boundary
    round-trips — reuse the proven result by identity; any other instance
    pays the full path. Writer admissions, decode boundaries, and all
    mandatory boundaries are untouched.
  - Measured progression (enabled children, quiet machine unless noted):
    49.0s baseline → ~15.8s (whole-object memo + lean bytes path) →
    ~9.7s (fused emitter) → ~9.1s (string/canonicity memos + lazy
    completion). Digest calls exactly **237** in every probe; post-H8
    accounting asserted in every child. In-process A/B: gc disabled
    5.8-5.9s vs enabled 6.7-8.6s — the residual is dominated by
    generational GC over the delivery's live container population
    (10-22 gen2 collections per delivery), not codec compute.
  - Machine-load finding: host load average 57-80 from unrelated user
    processes invalidated later timing probes (38-72s readings); all
    post-load measurements are deferred to a quiet machine.

- 2026-09-01/02 (gates at `585d51c`, under external load ~8-80): arena 46
  passed (including the differential fused-vs-reference families, memo
  lifecycle, forged-copy fail-closed, and duplicate-staging refusal),
  consensus codecs + proposal vector + provider compatibility +
  provider service + mode parity 56 passed, bootstrap coordinator V3
  family 19 passed; ruff clean; identity hygiene clean apart from the 124
  known `tests/ci/unit-test-durations.json` CI-artifact keys dispositioned
  in the legacy-path removal completion record.  `__eq__` attribution
  (CMR-EXP-007): 41,212 of the calls are the digest-verification hit
  checks themselves — the landed substitution contract's verification
  price, not removable without weakening it.
- 2026-09-02 (blocker recorded): final wall-clock evidence (v2 full run)
  and the once-only broad gate require a quiet host.  External load
  (57-80, later ~8.5 of 16 logical cores) invalidated every timing probe
  after the ~9.1s quiet-machine reading; at load ~8.5 the mode is
  11.6-12.2s.  Remaining compute levers are small (graph-planning
  quadruple validation, event-replay carrier adapter, dispatch ordering);
  the decisive residual is generational GC over the delivery's live
  container population (gc-disabled in-process A/B: 5.8-5.9s vs
  6.7-8.6s).  Closing to <5s likely requires an explicit, reviewed
  operability decision on GC policy for the arena's operation lifecycle
  (deferring generational collection to operation end), which touches
  global interpreter state from library code and is not taken
  unilaterally.

- 2026-09-02 (CMR-006 interim measurement, v2 harness at `585d51c` under
  recorded external load ~8-13 of 16 logical cores,
  `evidence/post-slice-v2-run.log` + `evidence/post-slice-load-context.txt`):
  **enabled median 12.47s** (min 11.89 / max 13.44), disabled median
  74.68s; **digest calls exactly 237 vs 43,756, deterministic**; post-H8
  accounting asserted in every child; enabled median reduction vs
  disabled 83.3%.  Quiet-host probes at the same revision measured
  ~9.1s; the load context is part of the evidence because the absolute
  acceptance number (<5s) cannot be judged under load.  The disabled leg
  also got faster (109.9 -> 74.7 under different load; the lean bytes
  path applies in both modes) with its accounting exactly unchanged.
  Acceptance status: **not yet met** — measured residual is
  GC-dominated (gc-disabled floor ~5.8s compute); closing the last gap
  requires the recorded GC-policy decision plus the remaining
  graph-planning/event-replay round-trip clusters, then a quiet-host
  re-measurement and the once-only broad gate.

## Next Action

Obtain the GC-policy decision for the arena's operation lifecycle (defer
generational collection to operation end — global interpreter state from
library code, therefore explicit and reviewed, not unilateral), land the
remaining graph-planning/event-replay round-trip conversions if approved
scope allows, then re-run the v2 harness on a quiet host and run the
once-only broad gate at the final revision.
