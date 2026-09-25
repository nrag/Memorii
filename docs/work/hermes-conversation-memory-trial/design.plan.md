# Hermes Conversation Memory Trial Design

- Work ID: hermes-conversation-memory-trial
- Work type: design
- Delivery fidelity: Level 2 early real-world testing
- Status: active
- Coordinator: `/root`
- Created: 2026-09-22
- Last updated: 2026-09-22
- Parent WorkPlan: None
- Related WorkPlans: `docs/work/hermes-memory-provider-integration/implementation.plan.md`
- Canonical inputs: `docs/design/memorii_spec.md`, `docs/design/memorii_storage_details.md`, `docs/design/event_model.md`, `docs/IMPLEMENTATION_RULES.md`, `docs/design/semantic_ingestion_architecture.md`, `docs/design/memory_evolution_runtime.md`, `docs/work/hermes-memory-provider-integration/production-entrypoint-preflight.md`
- Expected outputs: `docs/design/hermes_conversation_memory_trial.md`, reviewed Level 2 acceptance and implementation handoff

## Objective

Specify an installed Hermes free-form conversation-to-committed-memory-to-later-recall
path that can be tested on the user's Windows Docker setup without test
authority or a fixed proposal. A real supported turn must yield inspectable
governed outcome, durable fact, and scoped next-session answer.

## Completion Contract

The design is complete when every requirement in the canonical design has a
measurable proof, exact runtime composition and authority owner, failure and
recovery behavior, identity hygiene, implementation handoff, and no unresolved
validated P1/P2 or external semantic decision. Candidate freeze and all three
independent reviewer roles are required. No operational success is claimed
until an implementation and a real Hermes trial run produce evidence.

## Scope

Included: the Level 2 first-party Hermes runtime composition, explicit opt-in
model-backed profile, real completed-turn ingestion, governed promotion, scoped recall, persistence,
retry/recovery, CLI observability, and a practical Windows Docker trial.
Excluded: core ownership transfer to Hermes, test-connector promotion, direct
unvalidated writes, an open-ended language-quality guarantee, and production rollout.
Deferred Level 3: release ceremony, broad platform/version matrices,
hostile-storage testing, and exhaustive attack families. Selected Level 2
still requires a verified profile authority chain and basic scope safety.

## Constraints And Invariants

Preserve raw/derived and candidate/committed separation, single governed
semantic writer, source provenance, explicit ingress authorization, scope
isolation, typed persisted contracts, and no remote fallback. Section 3.23.0
of the semantic architecture governs the local bootstrap profile; an opt-in
non-bootstrap profile needs its own approved authority and egress contract. The older
`memory_evolution_runtime.md` and readiness plan describe default-on evolution
that current `ProviderMemoryService` no longer composes; follow current code
and the newer semantic-ingestion design pending a documentation correction.

## Problem Definition And Existing System

Current Hermes plugin discovery, bridge, completed-turn forwarding, and JSONL
capture work. Current development factory imports a test factory with fixed
`Atlas owner is Bob.` proposal. User's container shows two captured sources,
zero observation-ledger entries, zero graph records, and zero retrieval-visible
records. The first-party service factory has zero production implementations.
`ProviderMemoryService` leaves its legacy evolution service absent, so the
prefetch evolution channel is empty. Existing tests seed recall separately
from turn capture. The canonical design details these boundaries.

## Requirements Ledger

| Requirement | Owner | Acceptance |
| --- | --- | --- |
| HCM-01 | Installed Hermes runtime package | Real-loader startup with one non-test factory; missing authority fails |
| HCM-02 | Hermes bridge and ingress issuer | Actual turn text/source span, stable ID and correct participant scope |
| HCM-03 | Governed semantic pipeline | Two fresh free-form assertions commit; excluded forms retain non-promoting outcomes |
| HCM-04 | Provider retrieval | Same-scope fresh-session prefetch returns fact; cross-scope does not |
| HCM-05 | Atomic store and reconciliation | Reopen/replay produce exactly one committed effect |
| HCM-06 | CLI inspector | Exact source/outcome/graph/context trace for trial |

## Identity And Coordinate Hygiene

`HCM-*` and this Work ID are planning values only. Candidate behavioral
identities are `hermes_conversation_runtime` for installed composition and
`conversation_memory_status` for CLI inspection; final implementation names
must pass the durability test. Existing `memorii` provider and both entry-point
group strings are protocol identities. Existing source IDs, delivery identities,
graph IDs, and profile version are domain/protocol identities. No plan number
may enter a Python module, symbol, fixture, test, persisted value, command, CI
job, or diagnostic. The implementation must run the field-aware identity gate
and mutations showing rejection of plan coordinates but acceptance of genuine
protocol versions.

## Changed-Surface Ledger

| Path | Class | Owner | Status |
| --- | --- | --- | --- |
| `docs/design/hermes_conversation_memory_trial.md` | canonical proposed design | this plan | revised for production-path profile |
| `docs/work/hermes-conversation-memory-trial/design.plan.md` | WorkPlan | this plan | active |
| `docs/work/hermes-conversation-memory-trial/cohort-review.md` | frozen diagnostic findings | prior cohort | retained unchanged |
| `docs/design/semantic_ingestion_architecture.md` | governing Level 2 Hermes production-path extension, Section 3.25 | this design revision | amended |
| `memorii.core.semantic_ingestion.resources/project_assertions.*.v1.json` bundle | future installed package data: manifest, prompt, schema, predicate catalog, egress policy, component fingerprints | separate implementation WorkPlan | specified, not present; wheel-install smoke required |
| `ProjectAssertionProviderProposalAdapter` and complete Bootstrap V3 host bundle | future `ProviderSemanticProposal` normalization, authority, four lanes, policies, and graph host | separate implementation WorkPlan | specified, not present |
| Hermes factory, provider retrieval, tests, CLI docs | future implementation | separate implementation WorkPlan | not edited |

## Production Entrypoint Bindings

The revision-bound preflight is
`docs/work/hermes-memory-provider-integration/production-entrypoint-preflight.md`
at historical revision `a862b361`, refreshed by the read-only mapper on
`3cfc1efc`. Its search covers the Hermes provider entry-point, service-factory
entry-point, bridge, canonical provider, and test connector.

| Requirement | Trigger and composition | Authority/owner chain and result | Production callers | Status |
| --- | --- | --- | ---: | --- |
| HCM-01 | Hermes plugin loader -> bridge `initialize(context)` -> service factory -> `build_started_hermes_memory_provider` | verified selected profile, ingress issuer, persistent service -> activated runtime | 0 service factories; 1 external loader | design target |
| HCM-02/03/05 | Hermes `sync_turn` -> canonical adapter -> provider ingestion coordinator -> atomic store | authenticated ingress, stable delivery, quote/source validation -> retained outcome and possible committed graph | 1 external manager after init | bridge exists, semantic root absent |
| HCM-04 | Hermes `prefetch` -> fresh trial read handle -> `ProviderMemoryService.retrieve_context` | exact operator/session/query/purpose authority -> current committed semantic projection with full source closure or no context | 1 external manager after init | protected core reader exists; trial projection/binding absent |
| HCM-06 | Protected inspection CLI -> detached verified store snapshot | local operator access -> source/outcome/graph diagnostics | 0 new callers | design target |

No existing zero-caller path is counted as implemented. The future
implementation must refresh the map and prove each callsite and authority
through the installed package.

## Sources Of Truth

Use repository `AGENTS.md` precedence. Product and semantic requirements come
from core spec, storage details, event model, implementation rules, then the
current semantic-ingestion design. Runtime docs and integration plans are
baseline evidence only where current code confirms them. The user's actual
Docker counts are operational evidence for capture without semantic commit.

## Assumptions And Open Questions

- Confirmed user requirement: the first trial must recall facts from free-form
  conversation, not only fixed fact sentences. The initial profile catalog
  accepts project owner, status, and deadline facts expressed in arbitrary
  wording.
- Selected restriction: one local CLI installation. Hermes author strings
  cannot authenticate multiple people; gateway and shared operation are
  unsupported.
- The user selected normal production authority and provider composition. The
  profile is `("memorii.project_assertions", 1)`, initially
  `gpt-4.1-nano`; the host credential resolver and endpoint are deployment
  artifact inputs, not an API-key investigation.
- Implementation evidence remains open: generic production profile composition,
  source-to-projection transaction, and real Hermes `messages` delivery must
  be built and exercised before the trial.

## Alternatives And Feasibility Evidence

The canonical design compares the test connector, the legacy evolution path,
the governed local profile, and a future model-backed profile. A read-only
preflight mapped one external Hermes loader and zero first-party factories.
Current local analyzer regex is broader than the signed v1 corpus, so that
regex alone is not proof of authorized general coverage. The current
`BootstrapV3ProposalTransport` is bootstrap-specific and cannot authorize
remote calls for v1. No experiment has yet demonstrated trial profile
composition or local trust provisioning. A bounded read-path feasibility check
passed all 145 existing `test_scoped_context_production_binding.py`
integration cases on 2026-09-22; it proves the core protected reader but not
the new graph-to-SEMANTIC projection, Hermes adapter, or live provider behavior.

## Failure, Operations, And Verification

The canonical design defines denial, abstention, retry, restart, rollback,
scope isolation, and operator-visible outcomes. Its HCM table maps each
requirement to installed-wheel, real-loader, deterministic, and Windows Docker
evidence. Level 2 attack classes: wrong-domain or missing authority, invalid
ingress, wrong participant/scope, duplicate delivery, unsupported grammar,
model/provider failure if one is used, and partial transaction. Do not promote
raw transcript or test fixture hits as semantic evidence.

## Progress, Evidence, Decisions, And Review Log

- 2026-09-22: Selected Level 2 because the user needs an early real Hermes
  trial with common failure safety, not production rollout.
- 2026-09-22: Repository preflight established working bridge/capture, missing
  first-party factory, test-only fixed proposal, and absent evolution retrieval.
- 2026-09-22: Initially drafted a narrow local-profile trial. User clarified
  that free-form conversation is required. Superseded the local-profile trial
  with an explicit opt-in model-backed profile proposal; v1 remains default.
  Trust provisioning and graph retrieval remain feasibility questions. Review
  not yet launched; no finding classification yet.
- 2026-09-22: Bounded correctness feasibility review found three approval
  blockers (product priority Not applicable; disposition blocks_approval;
  type architecture/security/integration): non-bootstrap model authority,
  ordinary-turn promotion eligibility, and authenticated cross-session recall.
  The canonical draft now proposes explicit contract amendments for all three;
  their governing incorporation and composition proof are still open.
- 2026-09-22: Candidate-freeze check: no three-role cohort has run. The
  requirement scope is selected, but the non-bootstrap authority and
  user-scope/read contracts have no governing approved binding, the first-party
  service factory has zero production callers, and there is no composition
  spike. Under `.agents/PLANS.md` Candidate Freeze Gate, this is a design
  readiness blocker. The bounded correctness review above is not cohort
  approval. Required next evidence is the governing contract amendment and
  a real authority/ingress/retrieval composition proof.
- 2026-09-22: User requested cohort review of the current draft despite the
  documented readiness gap. Review-only freeze: base commit
  `3cfc1efc521c98ba4c8dfa048af8546cf4ec0d3e`; canonical design SHA-256
  `37c2415ec22b5843f31fb37c359da1ae2db9c572ed3de19fe954b1530adaae61`;
  only the design and this WorkPlan are untracked. The three reviewers receive
  this same design identity, HCM-01 through HCM-06, Level 2 scope, and known
  authority/eligibility/recall blockers. This is a diagnostic cohort, not a
  claim that the normal candidate-freeze gate passed.
- 2026-09-22: Diagnostic cohort completed on the frozen design digest above.
  `spec_auditor`, `correctness_reviewer`, and `test_reviewer` each returned a
  non-approval result. The coordinator reconciled 13 individual observations
  into seven confirmed finding clusters in `cohort-review.md`: one governance
  blocker, one primary-journey identity/read blocker, and five required
  architecture, runtime, integration, and verification corrections. The
  canonical design was not edited during review. No final approval cohort has
  run.
- 2026-09-22: Reconciled C01-C07 into one Level 2 revision. The initial
  revision used an isolated trial authority; the current production-path
  revision supersedes it. It retains ordinary-turn eligibility, three
  predicates, ordered turn identity, protected cross-session read, durable
  asynchronous outcome, and one-factory image migration. Existing protected
  scoped-context integration suite passed: 145 tests in 24.54 seconds. This is
  a bounded feasibility check, not end-to-end proof.
- 2026-09-22: Targeted delta reviewers identified remaining release rollback,
  internal-control provenance, atomic child admission, factory-context,
  worker lifecycle, and verification gaps. The coordinator accepted the
  concrete findings and revised the contract with a signed monotonic release
  head, narrow provenance closure, one completed-turn transaction, explicit
  CLI/rewind/shutdown binding, outer query-bound read wrapper, and signed
  run-start evidence. These are diagnostic reviews under the candidate-freeze
  gate, not final approval.
- 2026-09-22: Second targeted challenge found that verbatim raw sources have
  `INTERNAL_CONTROL` origin, so the current scoped assembler would omit them
  before provenance closure. The canonical design now requires a narrow
  source-only closure rule and a real co-resident finite-grant proof. The
  binding table was corrected to require replacing sequential child fan-out.
  A signed release-head/high-water-mark chain and signed run-start manifest
  close the remaining rollback and post-run-substitution design gaps. No
  final whole-design cohort ran because new production callsites still have
  zero callers.
- 2026-09-22: Linked implementation readiness found that core profile material
  and runtime composition are bootstrap-specific. A bridge-only activation was
  removed after review because it could not provide atomic turn admission or
  governed semantic recall.
- 2026-09-22: The user selected production-like operation for the real Docker
  trial and rejected a separate trial authority. The canonical revision uses
  the existing `production` host capability, normal provider composition,
  normal data root, and deployment-authorization verifier for one explicit
  project-assertions profile `("memorii.project_assertions", 1)`, initially
  `gpt-4.1-nano`. The prior `operator_trial` domain, isolated root, and
  separate release hierarchy are superseded proposals. Bootstrap remains local
  and default. The non-bootstrap profile needs an active signed production
  deployment authorization; a Docker trial cannot self-issue it or claim
  SIA-R14 certification.
- 2026-09-22: The user supplied the Dockerfile and container inspection:
  `hermes-memorii` installs the development connector and mounts the named
  volume `hermes-memorii-data` at `/opt/data`. They confirmed their OpenAI
  credentials work in Hermes and instructed us not to investigate the key.
  Credential availability is no longer an external blocker; the remaining
  work is the production profile and ingestion/retrieval composition.
- 2026-09-22: The production-path revision was checked by three diagnostic
  reviewers. All reported the same review-readiness blocker: the new factory,
  semantic worker, projection, and protected Hermes prefetch have zero real
  callers, so the candidate-freeze gate cannot support a final design or
  implementation approval. No product correctness finding was issued. The
  user has been asked to choose between existing signed approval artifacts
  and an explicit Level 2 activation-rule change. No implementation decision
  had been inferred from silence.
- 2026-09-22: The user chose the explicit Level 2 activation-rule change while
  retaining the same production factory and semantic pipeline. Section 3.25
  now defines a closed, installation-bound `local_level2_operator` authority
  for the one Hermes OpenAI profile. It is operator-controlled configuration,
  not a signature or a disguised production authorization; it carries an
  execution class that production-certification and acceptance paths reject.
  The profile remains explicit, fixed, source-egress-bound, and unavailable on
  absent, expired, altered, or out-of-scope local authority.
- 2026-09-22: Resource-bundle feasibility found that digest fields alone cannot
  select a functional model profile. Section 3.25 now names one exact
  package-owned `project_assertions.v1` bundle: fixed Responses transport,
  `gpt-4.1-nano`, `store=false`, no tools/background mode, fixed prompt/schema,
  three-predicate catalog, source-bound egress policy, and installed-byte
  component fingerprints. No content digest is invented in the design; the
  first-party loader computes and binds it at authorization, startup, and
  egress. API data-use and default-retention/residency limits are disclosed to
  the local operator. Project-specific OpenAI data controls and residency remain
  external configuration rather than a claimed profile property.
- 2026-09-22: The user challenged the vendor-named semantic profile and narrow
  ontology. Before any local sidecar or factory activation, its coordinate
  changed to `memorii.project_assertions@1`; OpenAI remains the first explicit
  transport binding. The design now distinguishes this three-predicate Level 2
  proof slice from versioned personal and enterprise domain catalogs.
- 2026-09-22: Targeted spec review exposed OpenAI-named proposal-ID domains
  and inclusion of the provider manifest in those IDs. The design now binds a
  separate semantic-contract digest for candidate identity; the full manifest
  continues to bind the exact model transport. No final design approval or
  installed factory is claimed.

## Cohort Finding Disposition

| Finding | Revision closure | Remaining proof maturity |
| --- | --- | --- |
| C01 | SIA Section 3.25 binds the project-assertions profile and its first OpenAI transport through exact local-Level-2 or production-certified material, source-bound egress, and fixed component identities. The local variant is installation-bound and cannot type-confuse into production authority. | Specified; production-profile composition not implemented. |
| C02 | One local installation, CLI/primary-only admission, ignored author strings, opaque write/read handles, exact scoped read grants. | Specified; real Hermes/Windows scope proof pending. |
| C03 | Completed transcript ordinal plus content/prefix ledger; equal text at two ordinals distinct; missing or conflicting snapshot non-promoting. | Specified; pinned Hermes callback proof pending. |
| C04 | Separate semantic, user, transient/evidence routing; global semantic projection inside the normal installation root, with finite record-ID read grants and core-issued source-bound promotion. | Specified; transaction/projection proof pending. |
| C05 | Durable pending acknowledgment, leased worker, bounded attempts, terminal states, restart reconciliation, committed-only recall. | Specified; failpoint proof pending. |
| C06 | One new installed factory; old development connector removed from trial image, old root preserved and rollback explicit. | Specified; installed-wheel inventory pending. |
| C07 | Acceptance matrix covers real loader, fresh free-form facts, exclusions, authority mutation, retries, crash points, image/volume rollback, and live Docker trial. | Specified; tests and operations pending implementation. |

## Evidence And Authority Chain

Requirement coordinates `HCM-*` appear only as traceability values. Behavioral
identities are independently named in the canonical design. Authority order is
either production trust store -> active deployment authorization -> exact
profile manifest, or explicit installation-bound local-Level-2 authorization
-> exact profile manifest. Both then flow through the same host-built OpenAI
transport and source-bound egress -> admitted source and ordered delivery
ledger -> proposal schema and source/semantic validation -> fenced
graph/event/projection/outcome batch -> fresh protected scoped read. No derived
artifact in that chain has been generated by this design operation. The future
implementation must map registry, manifest, compiled policy, frozen vectors,
checksums, workflow pins, and aggregate gates against SIA Section 3.25 and
record exact cardinalities.

Evidence maturity: production-path contract **specified**; protected reader
**implemented and locally verified** by the focused existing suite; generic
profile composition, authorization, worker, projection, and Hermes binding
**not implemented**; real Windows Docker result **not operationally verified**.

The bundle's response contract supplies only predicate and source-quote hints,
but the active production route normalizes them into `ProviderSemanticProposal`
for Bootstrap V3, not `SemanticCandidate`. A required adapter derives mentions,
literal/entity object representation, IDs, and fact fields without model
authority. The factory also needs the complete profile-bound V3 authority,
Stanza, spaCy, predicate, temporal, request, and non-fixture graph-host bundle.
Current bootstrap material cannot commit these predicates. This is a specified
implementation dependency, not an unresolved semantic decision. It is material:
the existing host builder requires all eight V3 leaves and current authority/
provenance types bind the bootstrap profile, so a closed profile-bound V3
runtime-material generalization is required before any local OpenAI path can be
active.

## Blockers And Limits

The user resolved the profile direction in favor of a Level 2 local authority
using the production path. The governing revision permits one explicit,
installation-bound local authorization for the exact OpenAI profile. It is
created by the first-party `memorii-hermes` command after explicit egress acknowledgement,
uses the existing Hermes credential resolver, and is unavailable when absent,
expired, altered, or used outside one local CLI installation. It does not
satisfy a production deployment authorization, baseline approval, acceptance,
held-out evaluation, or SIA-R14 certification. The normal candidate-freeze
gate still sees zero production callers for the factory, worker, and semantic
projection. No bounded experiment has shown normal production profile
composition with the real CLI hook or the graph projection in protected
prefetch. Per `.agents/PLANS.md`, a final approval cohort cannot treat these
planned paths as reachable.

## Next Action

Refresh the implementation readiness packet and implement the installed
production factory's local-Level-2 authority, atomic completed-turn admission,
and protected recall path.

## Ontology Learning Direction Captured

On 2026-09-22 the user clarified that agent harnesses can delegate work and
serve bot channels, and that manually expanding a fixed ontology cannot cover
Memorii's intended domains. The canonical trial design now contains "Ontology
learning beyond the initial seed", linked from SIA Section 3.25. It separates
fact learning from schema learning and records the evidence -> diagnosis ->
typed proposal -> validation/evaluation -> scoped version activation -> source
reconsideration loop. It preserves source lineage, memory domains, tenant/user
isolation, historical meanings, and candidate/commit boundaries.

This is a recorded product direction and follow-on design scope, not an
implementation-ready ontology-evolution specification or an activation grant.
Exact contracts, thresholds, migration support, and activation policy require
a linked design after the first real Hermes test. The current next action and
Level 2 test scope remain the installed factory, semantic commit, and protected
recall. The fixed project predicates are a seed, not the full ontology.

### Build-design audit for ontology learning

On 2026-09-22 the user explicitly asked whether this extension had followed
`.agents/skills/build-design/SKILL.md`. The coordinator reread the skill and
audited the ontology-learning section separately from the earlier Hermes
design and provider-identity reviews. The full workflow has not been completed
for ontology learning; documentation capture and whitespace checks are not
design approval.

| Skill phase | Ontology-learning evidence | Remaining work |
| --- | --- | --- |
| 1. Problem and baseline | User intent, harness/channel actors, initial seed, and delivery sequence recorded | Dedicated requirements/acceptance and identity ledgers; production baseline map |
| 2. Contract and authority boundaries | Fact/schema separation, scope, provenance, and versioning principles stated | Typed proposal/activation contracts, lifecycle transitions, accepted edit grammar, ownership and caller bindings |
| 3. Reality and feasibility | Existing memory domains and paper examined | Compare serious alternatives; test catalog evolution, activation, historical reads, and replay feasibility against actual core owners |
| 4. Verification model | Required scenarios listed | Requirement-to-evidence matrix, common-failure/recovery cases, environment matrix, and identity checks |
| 5. Complete draft | Directional lifecycle recorded | Complete evaluation policy, migrations, compatibility, concurrency, resource limits, diagnostics, and operational behavior |
| 6. Independent review | No ontology-learning cohort conducted | Freeze a ready candidate; run spec, correctness, and test reviewers; reconcile findings |
| 7. Final review | Not conducted | Independently reconstruct requirements and evidence; final three-role review and completion check |

The earlier targeted spec review covered the provider-neutral profile identity
only. It does not cover ontology evolution. Delivery remains Level 2 and the
user's sequence remains real Hermes testing before ontology expansion. The
audit identifies the future linked design's work; it does not add a new
approval prerequisite to the Hermes test or activate ontology learning.

## Outcome

Diagnostic cohort findings have design corrections. This design WorkPlan is
active for implementation-ready design review; it is not approved and makes no
operational-success claim.
