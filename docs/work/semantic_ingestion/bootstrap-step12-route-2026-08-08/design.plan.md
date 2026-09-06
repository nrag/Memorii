# Bootstrap Step-1/Step-2 Route Authority

- Work ID: semantic_ingestion_bootstrap_step12_route_2026_08_08
- Work type: design
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-08-08
- Last updated: 2026-08-09
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/bootstrap-local-profile-2026-08-01/design.plan.md`; `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md`
- Canonical inputs: `AGENTS.md`; `.agents/PLANS.md`; `.agents/skills/build-design/SKILL.md`; `docs/design/semantic_ingestion_architecture.md` Sections 3.23.0, 4.1, and 4.2; `memorii/memorii/core/memory_evolution/bootstrap_profile.py`; `memorii/memorii/core/memory_evolution/source_admission.py`; `memorii/memorii/core/memory_evolution/source_governance.py`; `memorii/memorii/core/memory_evolution/semantic_analysis/language_router.py`; `memorii/memorii/core/semantic_ingestion/source_preparation.py`
- Expected outputs: a reviewable canonical authority correction for the frozen local English Step-1/Step-2 route; no production, test, generated-artifact, or implementation-plan conversion.

## Objective

Authorize the already named deterministic local bootstrap components to carry a
trusted host-declared English source through the closed Step-1/Step-2 handoff.
The route is persisted, content-addressed, externally release-authorized, and
nonpromoting for every missing, untrusted, mismatched, non-English, mixed, or
unsupported input.

## Completion Contract

Complete: the final frozen identity is reproduced, independent specification,
correctness, and test reviews have no unresolved validated P1/P2 or required
contract-conformance finding, and this record supplies the exact
implementation/evidence handoff. This approves implementation to the frozen
canonical design hash, not artifact generation or deployment.

## Scope

Included: regeneration of the unreleased V1 profile, corpus, capability,
anchor, release, and manifest bytes as one atomic pre-release authority;
exact Step-1/Step-2 route behavior; and positive/attack evidence.

Excluded: general language detection, classifier scoring, non-English routing,
remote proposal, model/tokenizer/download assets, a configurable registry, new
external dependencies, production code, tests, CTV generation, and traceability
release issuance. Deferred: implementation and evidence regeneration under the
approved design handoff.

## Sources Of Truth

Precedence is `docs/design/memorii_spec.md`, storage/event/implementation
governing documents, then `docs/design/semantic_ingestion_architecture.md`.
This WorkPlan does not amend the external-root or traceability authorities.

## Actors And Current State

The host capability verifies the external root, V1 release, and lifecycle before
core receives bytes. Core verifies the three V1 artifacts and eight component
owners; source admission retains the immutable delivery/fence identity and
closed ingress-language evidence; preparation owns source-only CAS; the typed
bootstrap writer handoff is the only boundary that starts existing writer work.

## Architecture And Data Flow

`HostVerifiedBootstrapMaterial` -> `VerifiedBootstrapProfile` -> atomic source
admission/pending outcome -> deterministic preparation and grammar proof ->
prepared-publication CAS -> typed bootstrap writer handoff -> existing
writer-bound preplanning. Every retry uses the
same V1 release evidence, language evidence, delivery identity, and fence.

## Requirements Ledger

| ID | Priority | Requirement | Source | Acceptance evidence | Status |
| --- | --- | --- | --- | --- | --- |
| BSD-R01 | P1 | Trusted host declaration `en` can select only the frozen local route. | SIA-R08/R16/R19; 3.23.0; 4.1/4.2 | Exact route schema and positive matrix row | approved design |
| BSD-R02 | P1 | Missing/untrusted/mismatched/non-English/mixed/unsupported input remains retained, fail-closed, and nonpromoting. | SIA-R01/R04/R08; 3.23.0 | Exhaustive negative matrix | approved design |
| BSD-R03 | P1 | Persisted route authority is typed, digest-bound, externally anchored, and migration-safe. | SIA-R03/R13/R22; implementation rules | Regenerated unreleased V1 three-artifact profile plus existing V1 anchor/release chain | approved design |
| BSD-R04 | P1 | Eight real component owners are fingerprinted and real host composition uses only the verified profile. | `bootstrap_profile.py`; source owners | Exact eight-symbol inventory and composition/mutation matrix | approved design |

## Contract And Authority Boundaries

The existing V1 `BootstrapLocalProfileManifest` remains at
`BootstrapProfileCoordinate("memorii.bootstrap_local_english_rule", 1)` and
is regenerated before release. It preserves the three-artifact graph and folds
the Step-1/Step-2 owner symbols into its one component root. It binds the embedded frozen
`TextPreparationPolicy`, literal `en`, and exactly these additional production
symbols: `ProviderEventNormalizer`, `require_complete_scope_authorization`,
`TextPreparationService`, and `ProductionLocalSemanticAnalyzer`. Its ordered
`ComponentSymbolFingerprint` inventory is exactly the four existing bootstrap
symbols plus these four additions. No classifier,
generic language router, provider, or resource is ceremonially authorized.

The host trust boundary remains external. Existing V1 anchor/release metadata
binds the regenerated V1 profile manifest and expanded component root. Runtime
verifies the external root, active release, V1 anchor, the three V1 CTV
artifacts, one component root, and exact owner bytes before construction. Any
failure is `profile_unavailable`.

The route reads only trusted host language evidence and exact persisted segment
governance. Atomic admission retains the existing immutable delivery/fence
identity but writes no semantic candidate, writer binding, lease, allocation, or
graph state. Step 2 may publish only a route-bound prepared source.
No route invokes a remote client, classifier, registry, downloader, or fallback.
It consumes only the existing `AuthenticatedIngressContext` language tuple,
bound to its existing `DeliveryPrincipalBinding` and complete segment-governance
set; it creates no caller/host input or new language authority. The ordinary
caller `declared_language` remains untrusted.

## Migration, Rollback, And Compatibility

Regenerate all unreleased V1 artifacts atomically before enabling Step 1/Step 2.
There is no published compatibility, migration, or old-reader burden. Crash or
partial pre-release generation fails closed; release rollback is explicit
disablement to evidence-only retention and never restores remote behavior.

## Verification And Attack Matrix

| Family | Proof |
| --- | --- |
| Positive route | Trusted, governance-agreeing `en` plus entire grammar match produces exact admitted-to-prepared route bindings; only exact typed handoff may create writer work. |
| Declaration failures | Missing, untrusted, mismatched, non-English, and mixed declarations retain evidence only; no prepared publication or semantic effect. |
| Form failures | Partial, malformed, mixed-residue, and unlisted grammar forms have the same nonpromoting outcome. |
| Authority mutations | Every signed release coordinate/profile-anchor field, lifecycle entry, one of the three artifact digests, symbol, fingerprint/root ordering, policy field/fingerprint, language-evidence carrier digest, and route digest mutation rejects before publication or handoff. |
| Current authority | Pre-lookup expired/revoked/mismatched session or incomplete scopes, missing/revoked/stale release assertion, and external-root/lifecycle outage return coordinate-free in-memory `BootstrapHandoffAccessDenied` with no mutation; only a post-access in-CAS revalidation race may persist the retained-pending or prepared-published `ProfileAuthorityUnavailable` terminal. Neither assertion enters durable identity or replay equality. |
| Schema/digest closure | Unknown field, alias, default insertion, absent required field, and one-field request/marker/result digest mutations reject; recovery validates current authority before marker/terminal lookup, then matching lost-ack handoff returns the same marker and every competing tuple rejects. |
| Ephemeral retry and terminality | Fresh valid session/release assertions can retry the same prepared tuple without changing durable bytes or equality. Pre-lookup denial is only in-memory `BootstrapHandoffAccessDenied`; only an in-CAS revalidation denial persists one retained-pending or prepared-published `ProfileAuthorityUnavailable` terminal, and every later handoff rejects even when reauthorized. |
| Capability isolation | Socket/DNS/HTTP, ambient LLM, remote selector, classifier, registry, and downloader construction traps prove zero invocation. |
| Regeneration/recovery | Atomic unreleased V1 regeneration, partial-generation failure, disablement, revocation, restart, and recovery preserve the stated authority boundary. |

## Evidence Maturity

| Claim | State | Owner |
| --- | --- | --- |
| Existing owner symbols/fingerprint mechanism exist | implemented | current production modules |
| Route authority contract | approved design | this WorkPlan |
| Artifact, migration, and attack execution | not implemented | later linked implementation WorkPlan |

## Constraints And Invariants

Existing V1 decode/selection and release machinery are regenerated as one
unreleased authority set with exactly three content artifacts and one eight-symbol
root. Host language evidence derives solely from
existing authenticated ingress and stable principal binding. Negative outcomes
retain source/fence evidence but cannot acquire writer binding, lease, preplanning or
semantic state. No scope expansion permits a remote path, detection model,
registry, downloader, or external dependency.

The complete durable bootstrap outcome set is `selected_pipeline_pending`,
`disabled`, `unavailable`, `ProfileAuthorityUnavailable`, `unsupported_input`,
and `abstained`. `unavailable` is profile activation failure only;
`ProfileAuthorityUnavailable` wraps only the retained-pending or
prepared-published in-CAS terminal. Coordinate-free
`BootstrapHandoffAccessDenied` is an ephemeral pre-lookup response and is not a
durable outcome.

## Alternatives And Feasibility

Rejected alternatives: a second profile coordinate or decoder path (creates an
unnecessary compatibility boundary); a fourth route artifact (creates an unnecessary mixed
authority chain); generic classifier-route reuse (would falsely authorize
unverified resources); and injected preparation producers (lets callers select
semantic authority). Repository mapping confirms the V1 bootstrap symbols,
Step-1 normalizer/governance symbols, `TextPreparationService`, and
`ProductionLocalSemanticAnalyzer` already exist; implementation must add only the specified factory, verifier, and
durable publication path.

## Assumptions And Open Questions

The existing external traceability root/witness is independently provisioned and
must be consumed as fixed bytes; neither production nor test code may recompute
it. The future independent V1 oracle asset owner is
`memorii/tests/independent/bootstrap_profile_codec_oracle.py`: a test-only
encoder/decoder with no imports from any `memorii.core` CTV/bootstrap/schema/
digest/checker module, and no reciprocal production import. Its vectors are
signed/pinned static bytes plus the external root/witness, which it does not
recompute. No open product-semantic decision remains; implementation
ownership and artifact generation remain deferred.

## Gate And Test Ownership

Existing focused owners are `memorii/tests/unit/core/semantic_ingestion/test_semantic_provider_composition.py`,
`memorii/tests/unit/core/semantic_ingestion/test_semantic_pipeline.py`, and
`memorii/tests/unit/core/semantic_ingestion/test_semantic_terminal_persistence.py`.
New bounded owners are
`memorii/tests/unit/core/memory_evolution/test_bootstrap_local_english_route_profile.py`,
`memorii/tests/unit/core/memory_evolution/test_bootstrap_local_english_route_profile_oracle.py`,
and `memorii/tests/unit/core/semantic_ingestion/test_bootstrap_local_english_route_admission.py`.
The independent checker is the future owned path
`memorii/memorii/tools/check_bootstrap_local_english_route_profile.py`; its sole argv is
`python -m memorii.tools.check_bootstrap_local_english_route_profile --profile ../docs/design/semantic_ingestion/bootstrap_profile/manifest-v1.ctv --capability ../docs/design/semantic_ingestion/bootstrap_profile/grammar-capability-v1.ctv --corpus ../docs/design/semantic_ingestion/bootstrap_profile/corpus-v1.ctv --anchor ../docs/design/semantic_ingestion/bootstrap_profile/trust-anchor-v1.ctv --external-root ../docs/design/semantic_ingestion/bootstrap_profile/external-root-v1.ctv --release ../docs/design/semantic_ingestion/bootstrap_profile/release-v1.ctv --lifecycle ../docs/design/semantic_ingestion/bootstrap_profile/lifecycle-v1.ctv`.
The new `bootstrap-local-english-route-profile` job in `.github/workflows/pr-gates.yml`
runs that argv in cwd `memorii` with `timeout-minutes: 5`; it is a direct
`needs` dependency of both `semantic-terminal-persistence` and the aggregate
`unit-tests`, and `semantic-terminal-persistence` must complete after it. A
workflow-structure guard at
`memorii/tests/unit/tools/test_pr_gates_bootstrap_local_english_route.py`
asserts that exact job, cwd, argv, timeout, direct dependencies/order, aggregate
result, seven-shard matrix/count, `target_seconds: 600`, exact collection,
timing inventory, and no-node-drop policy. Its own node must have exact unit
shard ownership and timing entries in `memorii/tests/ci/unit-shards.json` and
`memorii/tests/ci/unit-test-durations.json`, separately from the 224-node
terminal-persistence inventory. The current terminal
job uses `python -m memorii.tools.test_shards verify/run` with
`memorii/tests/ci/semantic-terminal-persistence-shards.json`, seven matrix
indices, and `timeout-minutes: 15`; implementation must update collection and
timing inventory together, never relax the budget. Unit-test node ownership is
exclusive: the checker dedicated job owns no duration-sharded unit node, while
all JSONL admission/CAS/failpoint cases live under the terminal-persistence
selector. Its current inventory must be recaptured from 224 nodes, timing merged
across all seven shards, and verified before any final gate claim. The
deterministic workflow owner is `.github/workflows/pr-gates.yml`; the standalone
checker is recorded in
`memorii/tests/ci/deterministic-job-owners.json` with exclusive owner,
five-minute budget, measured duration, and at least one-minute headroom. The
guard fails a missing owner, budget, headroom, matrix count, timing inventory,
or aggregate dependency.
`memorii/tests/ci/deterministic-job-owners.json` and the unit guard are the
distinct deterministic-command ledger/guard for this non-pytest checker. They
record and mutate-test its exact job name, argv, cwd, owner, timeout, measured
duration, headroom, direct dependencies, and aggregate. Broad-unit collection
must equal the complete key set of `unit-test-durations.json` exactly--no
median/default fallback--and the guard itself must be assigned to exactly one
unit shard. Separately, terminal persistence pins the workflow's seven-shard
count, static assertion, and manifest key set to the same complete 224-node
inventory; missing, extra, count, ownership, and timing mutations fail.
The composition test must exercise real `ProviderMemoryService`, the default and
explicit `HermesMemoryProvider`, and the filesystem builder with fixed verified
V1 material; it must reject injected preparation producers. The independent
oracle owns fixed signed V1 bytes plus the external root and lifecycle witness,
and imports neither `memorii.core` CTV/bootstrap/schema/digest/checker code nor
any code that imports it. JSONL failpoint/CAS tests belong only to
`test_semantic_terminal_persistence.py`; they cover conflict, authority change,
partial V1 regeneration, release/lifecycle revocation, and reopen with the
original release evidence, language evidence, delivery identity, and fence, plus
lost acknowledgement, restart, and competing bootstrap writer handoff.
They also prove a positive retry with fresh valid session/release assertions
returns byte-identical durable bytes and equality, while denial/reopen and every
authorization, release, unknown-field, and digest mutation follow the terminal
or reject behavior defined by the CAS. Revoked/expired lost-ack and terminal
reopen first return the strict in-memory coordinate-free
`BootstrapHandoffAccessDenied` without marker/terminal lookup or mutation.
The assertion A/B/C matrix uses three independently issued valid assertions with
distinct nonce/digests and strict verifier order: only A is accepted for prepared
publication, only B for the pre-handoff retry/check, and only C for writer
handoff after fresh-process reopen. A stale phase/nonce/digest rejects before
lookup or mutation. Memory and JSONL assertions prove all three are absent from
persisted bytes and replay equality yet are freshly revalidated at each use.

## Failpoint Matrix

| Store | Failpoint | Required assertion |
| --- | --- | --- |
| memory | before admission / after admission before prepared CAS | no durable later stage / exact pinned pending recovery with immutable fence identity only |
| memory | after prepared CAS before writer handoff / after handoff before ack | no writer effect before handoff / byte-identical marker and handoff recovery |
| JSONL | each memory failpoint plus reopen | prior-or-complete generation only; proof tuple, release/language evidence, delivery identity, and fence reopen byte-identically |
| JSONL | V1 partial regeneration, authority change, conflict, disablement, revocation | `ProfileAuthorityUnavailable`/conflict terminalization after activation; no newer authority selection and no writer effect before CAS |
| JSONL | expired/revoked session, incomplete scope, stale/revoked release assertion, unknown field/digest mutation | pre-lookup `BootstrapHandoffAccessDenied` with no durable write, or post-access CAS race terminalization; assertions never persist or affect replay equality |
| JSONL | fresh-valid A/B/C assertion sequence; revoked/expired lost-ack; terminal reopen; post-denial reauthorization | A->B->fresh-process reopen->C, byte-identical durable bytes, coordinate-free denial before lookup, one terminal record/no marker-pending-writer, and later handoff rejection |

## Blockers And Limits

This is a design-only closure. Artifact generation, external signing/root
provisioning, production factory/CAS implementation, test creation, timing
inventory updates, and CI job creation are deliberately not evidence yet.

## Implementation Handoff

The later implementation WorkPlan must regenerate all unreleased V1 bytes as one
set, implement no alternate coordinate/registry/release schema, and record the
real-composition, oracle, checker, JSONL, 224-node collection, and seven-shard
timing evidence named here before claiming the route is implemented.

## Outcome And Retrospective

The earlier candidate left release-body membership, registry generation,
admission CAS, and proof identity under-specified. This reconstruction replaces
those repeated boundary gaps with one closed contract batch rather than further
example-level amendments.

## Changed-Surface And Authority-Chain Ledger

| Path | Surface | Authority chain | Required evidence | Status |
| --- | --- | --- | --- | --- |
| `docs/design/semantic_ingestion_architecture.md` | normative contract | design -> regenerated V1 CTV/anchor/release -> verified factory -> retained/prepared route | independent reviews; artifact checker | approved design baseline |
| this WorkPlan and identity JSON | design governance | requirements -> matrix -> frozen identity -> reviews | identity reproduction | complete |
| V1 CTV artifacts, checker, production factory | future derived/production surfaces | design -> regeneration/verification -> tests -> PR gate | later implementation WorkPlan | not implemented |

## Gate Ledger

| Gate | Command or CI action | Required | Current result |
| --- | --- | --- | --- |
| diff hygiene | `git diff --check` | yes | pass at final design closure |
| profile checker | future `bootstrap-local-english-route-profile` job and exact argv below | yes | not implemented |
| terminal persistence | existing seven-shard `semantic-terminal-persistence` job | yes after implementation | not run for design-only closure |
| aggregate | existing `unit-tests` plus new dependency | yes after implementation | not implemented |

## Requirement-To-Evidence Matrix

| Requirement | Deterministic proof owner | Required future gate | Current state |
| --- | --- | --- | --- |
| BSD-R01 | bootstrap profile/factory unit tests and grammar-proof vectors | `memorii.tools.check_bootstrap_local_english_route_profile`; `bootstrap-local-english-route-profile` PR job | specified |
| BSD-R02 | negative admission/retry/crash matrix through JSONL and in-memory stores | semantic terminal-persistence shards | specified |
| BSD-R03 | independent V1 oracle, signed release/profile-anchor/lifecycle/artifact mutation checker, and handoff CAS matrix | `memorii.tools.check_bootstrap_local_english_route_profile`; `bootstrap-local-english-route-profile` PR job | specified |
| BSD-R04 | component-root/factory substitution and no-network construction tests | `bootstrap-local-english-route-profile` job and no-network matrix | specified |

The independent artifact checker at `memorii/memorii/tools/check_bootstrap_local_english_route_profile.py` must decode the three regenerated V1 envelopes with their
existing binding/fingerprint/decoder identities, verify the signed V1 release,
external root, anchor, lifecycle/revocation state, recompute all digests/roots,
verify the original release-evidence binding, and validate
route/proof cardinality. It runs before provider
construction and in the existing PR gate. Collection and timing ownership stays
with `memorii/tests/ci/semantic-terminal-persistence-shards.json` and
`.github/workflows/pr-gates.yml`: the implementation must collect all selected
nodes, refresh timing data for any new node, retain the seven-shard budget, and
fail rather than drop over-budget work. JSONL proof includes pre-observation,
post-observation/prepared, post-prepared/pre-handoff, and post-terminal/
pre-ack failpoints; rollback/reopen proves V1 disablement and byte-identical
retry under the original verified-profile pin.

The existing `memorii.tools.identity_hygiene` gate runs against every new
schema, fixture, command, job, and artifact field. Its mutation corpus rejects
`BSD-REV-*`, work-plan paths, and milestone/review coordinates in persisted or
executable identities while allowing the behavioral V1 coordinate and schema
versions.

## Review Reconciliation

| Finding | Classification | Disposition | Correction |
| --- | --- | --- | --- |
| BSD-REV-001 (reviewer DREV-001) | P2, changes_required, architecture/compatibility | corrected and accepted | signed existing V1 release binds bootstrap coordinate/profile anchor; host evidence derives only from that chain |
| BSD-REV-002 (reviewer DREV-002) | P2, changes_required, persisted-contract/verification | corrected and accepted | existing V1 bindings/decoders, eight-owner root, and atomic regeneration remain authoritative |
| BSD-REV-003 (reviewer DREV-003) | P2, changes_required, runtime/verification | corrected and accepted | closed factory, language/proof identities, current-authority CAS, terminal prepared denial, and marker-backed writer handoff contract |
| Final specification review | no validated finding | approved | V1 release/activation, outcome, transition, and protected terminal-reopen contracts are internally closed |
| Final correctness review | no validated finding | approved | authority pin, CAS, retry/recovery, and writer-handoff boundaries are reachable and fail closed |
| Final test review | no validated finding | approved | future checker, composition, failpoint, JSONL, collection, timing, and workflow evidence are assigned to implementation |

`remaining_validated_p1_p2`: []

`remaining_blocks_approval`: []

`remaining_changes_required`: []

Final targeted approval: the corrected unreleased V1 authority design is
approved for bounded implementation at canonical design SHA-256
`43550572621383259ed31c3dd7942c2e5cf43e0acd4692cd50abefede6afd1bd`.

## Known-Failure Ledger

No design-local command failure is known. Current production/test failures and
timing-inventory gaps are excluded from this design closure and must be
reproduced/dispositioned by the later implementation WorkPlan before any gate
claim.

## Decision Log

- Regenerate the unreleased V1 profile, grammar artifacts, anchor, release metadata, and signed release bytes atomically; introduce no second coordinate or decoder path.
- Reuse the existing authenticated ingress language tuple, not a new declaration or authority source.
- Admission owns pre-writer prepared publication; semantic writer state starts after its CAS.

## Review Log

The reviewer mapping is preserved in `BSD-REV-001` through `BSD-REV-003`.
Their canonical design `DREV-*` coordinates are not reused as WorkPlan IDs.
On 2026-08-09, final targeted specification, correctness, and test review
reconciled every validated finding as corrected and accepted; no P1/P2,
`blocks_approval`, or `changes_required` item remains.

## Progress And Decisions

- 2026-08-08: Direct mapping found an existing bootstrap profile and real Step-1/Step-2 owners, but no persisted manifest authorizes their joint route. This is a design gap, not authorization to fabricate source/carrier authority in M3.
- 2026-08-08: The prior alternative authority model is superseded. The authorized correction regenerates the unreleased V1 bytes atomically and keeps the existing V1 coordinate, decoder, anchor, and release machinery.
- 2026-08-08: Rejected language detection/classifier routing, remote fallback, and registry lookup because they exceed the closed bootstrap scope and weaken fail-closed behavior.

## Identity Ledger

`BSD-R*` and this WorkPlan ID are planning-only identifiers. Persisted identities
are the behavioral schema IDs, CTV domains, bootstrap coordinate, artifact
paths, and fully qualified owner symbols stated in the canonical design. No M3
or review coordinate is serialized into product data.

## Exact Implementation Handoff

The parent implementation WorkPlan's sole next action is to implement the
approved corrected V1 authority at canonical design SHA-256
`43550572621383259ed31c3dd7942c2e5cf43e0acd4692cd50abefede6afd1bd`, then
collect the checker, composition, failpoint, JSONL, collection, timing, and CI
evidence specified here. Do not alter the V1 coordinate, release architecture,
or scope exclusions without a new design operation.

## Candidate Freeze

The closure identity is `bootstrap-step12-route-candidate-identity.json` in
this WorkPlan directory. Its recorded design, WorkPlan, dirty-tree, and binary
diff hashes bind the approved design; any semantic edit requires a new design
operation and review scope.

## Superseded Review History (2026-08-08)

The earlier alternative authority-model findings are retained under their
planning-only `BSD-REV-*` coordinates for reviewer traceability. They do not
authorize a second profile coordinate, bootstrap registry, release member, or
decoder. Their V1-only remediation is accepted; implementation evidence remains
an obligation of the parent implementation WorkPlan.
