# Hermes Semantic Profile Runtime Contract

- Work ID: hermes-semantic-profile-runtime-contract
- Work type: design
- Delivery fidelity: Level 2 early real-world testing
- Status: complete
- Coordinator: `/root`
- Created: 2026-09-23
- Last updated: 2026-09-23
- Parent WorkPlan: `docs/work/hermes-conversation-memory-trial/design.plan.md`
- Related WorkPlans: `docs/work/hermes-conversation-memory-trial/implementation.plan.md`
- Canonical inputs: `AGENTS.md`, `.agents/PLANS.md`, `docs/design/memorii_spec.md`, `docs/design/memorii_storage_details.md`, `docs/design/event_model.md`, `docs/IMPLEMENTATION_RULES.md`, `docs/design/semantic_ingestion_architecture.md`, and `docs/design/hermes_conversation_memory_trial.md`
- Expected outputs: a closed Bootstrap V3 host-input envelope contract, exact Hermes composition, Level 2 migration/recovery/verification rules, and a frozen design candidate for cohort review

## Objective And Completion Contract

Resolve the bootstrap-only runtime-composition blocker without introducing a Hermes-specific core, a second semantic persistence path, or a second semantic runtime. The completed design must permit one first-party Hermes factory to use an installation-bound local authorization adapter to create the same complete Bootstrap V3 host material used by the production route, then reach the canonical source admission, normalization, candidate validation, fenced writer, projection, and protected scoped-read owners.

Completion requires that a later implementation writer can implement the Level 2 journey without deciding any resource-policy selection, authority carrier, transaction boundary, retry/recovery rule, reader grant, or factory handoff. The design is not production approval. Production certificate issuance, hostile local-storage resistance, multi-user and gateway support, broad provider qualification, and release signing remain deferred.

## Baseline, Scope, And Decision

The linked implementation plan is blocked because its existing runtime types accept only `VerifiedBootstrapProfile`; the local sidecar carries digests but does not carry the host-built semantic runtime material needed by source normalization, graph commit, and protected retrieval. The current first-party factory therefore fails closed before ingress. This design owns the contract correction only; it does not edit product code.

The selected solution preserves `VerifiedBootstrapProfile` and Bootstrap V3 as the sole runtime/interface. `memorii.project_assertions@1` is a catalog/extraction resource set inside Bootstrap V3. The first-party factory host verifies the local sidecar and constructs the existing-shape Bootstrap V3 host capabilities; core does not branch on Hermes configuration, environment-selected model fields, or caller-provided trust mode.

### Serious Alternative Rejected

A separate Hermes trial coordinator could call the OpenAI transport and graph writer directly. It is rejected because it would create a second source/admission/recovery/read path, force two implementations of replay and fencing, and let the user test a path that production composition does not call. A generalized multi-profile runtime union was also explored and rejected after product clarification: it would change the production interface even though the only needed variation is the host authorization source. The narrow adapter preserves Bootstrap V3 and rejects incomplete material before source, egress, or graph operation.

## Requirement Matrix

| Requirement | Normative behavior | Evidence needed before implementation resumes |
| --- | --- | --- |
| SPRC-01 | The factory keeps one Bootstrap V3 runtime and accepts local authorization only as a host-material construction input. | Construction tests prove no runtime/profile substitution is possible. |
| SPRC-02 | Production verifier and local adapter construct the same opaque `BootstrapV3HostInputEnvelope`; neither requires `VerifiedProductionHostAuthority` locally. | Envelope completeness/substitution/serialization-denial tests before remote call or write. |
| SPRC-03 | A completed Hermes turn has a canonical complete-messages delivery coordinate, stable operation key, two ordered source records, and atomic operation/outcome admission. | Canonical/tool/missing/mismatch/truncation, exact replay, later-position equal-text, collision, every failpoint, uncertain-ack, retry, and restart tests. |
| SPRC-04 | Only a fresh in-process opaque read binding can expose committed facts; its internally built request/handle binds installation/task/user/agent/query/resource/budget and is revoked after one read. | Mapping, cross-session success, changed scope denial, copied/forged/post-revoke/restart-handle denial, mutation impossibility, and one-caller tests. |
| SPRC-05 | Retry and restart use fenced writer activation and recover one pending operation without double commit. | Lease loss, timeout, restart, and completed replay tests. |
| SPRC-06 | The first-party Hermes entry point has one non-test factory caller and no development connector on the active path. | Entry-point mapping, installed image inspection, and Windows Docker journey. |

## Identity Ledger

| Identity | Kind | Owner | Rule |
| --- | --- | --- | --- |
| `VerifiedBootstrapProfile` | existing runtime material | bootstrap verifier | Sole semantic runtime material; no local replacement or union. |
| `BootstrapV3HostInputEnvelope` | opaque runtime envelope | host integration boundary | Same complete Bootstrap V3 inputs from production verifier or local adapter; never persisted/serialized. |
| `VerifiedLocalBootstrapV3Authorization` | local authorization | first-party factory host | Binds sidecar, installed Bootstrap/resources, and installation; never accepted from Hermes callback data. |
| `BootstrapV3LocalAuthorizationUse` | runtime authorization assertion | local adapter | Reissued at startup, egress, commit, recovery, and scoped read. |
| `SemanticExecutionClass` | persisted metadata enum | semantic operation owner | `bootstrap_local`, `local_level2`, or `production_certified`; it does not select a runtime or resource policy. |
| existing Bootstrap V3 writer lease | persisted lease binding | atomic semantic writer owner | Existing writer epoch/lease; local adapter adds revalidation only. |
| `HermesCompletedTurnAdmissionRequest` | runtime request | Hermes bridge | Requires canonical complete messages through final assistant, authenticated facts, and fixed Bootstrap/resource bindings. |
| `HermesSemanticReadBinding` | in-process request/handle | Hermes bridge / host issuer | Exact `ScopedContextRequest` plus opaque fresh handle; never serialized and always revoked. |
| project-assertions namespace tuple | persisted/read scope | operation, projection, and scoped-read owners | Stable installation/resource task ID; reusable projection row has session `None`; normalized-or-absent user and canonical-or-absent agent match on write/read. |

Planning IDs such as `SPRC-01` occur only in this WorkPlan and design traceability tables. They are not protocol fields, paths, enum values, or fixtures.

## Authority And Production Entrypoint Matrix

| Trigger | Composition owner and exact handoff | Authority binding | Durable result |
| --- | --- | --- | --- |
| Hermes provider `initialize` | `MemoriiHermesMemoryProvider.initialize` -> discovered first-party factory -> `build_hermes_bootstrap_v3_runtime(context)` | factory verifies existing Bootstrap profile, installed resources, and local sidecar then creates existing Bootstrap V3 host inputs | started runtime or `profile_unavailable`; zero remote calls/writes on denial |
| `sync_turn` | bridge -> `CompletedTurnIngressService.admit(HermesCompletedTurnAdmissionRequest)` -> source admission -> semantic-operation repository | canonical full-messages delivery coordinate plus ingress binds session/user/installation/agent and Bootstrap/resource policy | two ordered sources, one operation, one initial outcome, or no write |
| worker attempt | existing Bootstrap V3 worker -> normalizer -> candidate validator -> fenced writer -> projection/outcome repository | local adapter revalidates authorization and supplies Bootstrap V3 source/graph host authority; existing atomic store fences epoch | one terminal outcome and all-or-nothing graph/event/projection changes |
| semantic `prefetch` | bridge `issue_scoped_read` -> `ProviderMemoryService.retrieve_context` -> `revoke` in `finally` | private binding has exact request plus fresh opaque handle; stable task/user/agent/resource scope and finite semantic-only budget | rendered committed semantic facts with source provenance, or empty/unavailable result; legacy prefetch has zero callers |
| startup/restart | factory -> reconciliation worker | material revalidated; lease claims use persisted operation/activation data | reclaims only unexpired/recoverable pending operation and produces one terminal outcome |

There must be one discovered `memorii.hermes.provider_service` factory for `memorii`; its production caller count is one entry-point discovery path. The development connector may remain installed for development work but is not selectable by the first-party provider entry point. The factory has zero fallback from a denied local authorization to a transcript, development, or alternate semantic path.

## Changed-Surface Ledger

| Path or pattern | Surface class | Owner | Authority chain | Required later gate | Status |
| --- | --- | --- | --- | --- | --- |
| `docs/design/semantic_ingestion_architecture.md` | normative design | this design operation | local authorization adapter -> unchanged Bootstrap V3 runtime -> tests | design cohort | changed |
| `docs/design/hermes_conversation_memory_trial.md` | normative integration design | this design operation | Hermes callbacks -> opaque host envelope -> Bootstrap V3 commit/read | design cohort | changed |
| `docs/work/hermes-semantic-profile-runtime-contract/design.plan.md` | design WorkPlan | this design operation | requirement/identity/authority/evidence traceability | WorkPlan review | changed |
| future `memorii/memorii/core/semantic_ingestion/*` | product code | linked implementation | design -> typed runtime -> atomic store -> tests | focused unit/integration gates | deferred |
| future `memorii/memorii/integrations/hermes_*` | integration code | linked implementation | discovered factory -> bridge -> core | focused bridge/install gates | deferred |

## Evidence And Gate Matrix

| Evidence class | Exact proof | Current state |
| --- | --- | --- |
| Design | closed contracts below and independent cohort review on one frozen candidate | specified; cohort pending |
| Deterministic | envelope completeness/no-serialization/substitution, canonical-full-message admission/failpoints/replay, opaque-handle scoped-read mapping/revoke denial, namespace scope, phase mutation, fencing/recovery, and exact factory caller mapping | deferred to implementation |
| Installed integration | package entry point exposes first-party factory and excludes dev-factory selection | deferred to implementation |
| Operational | Windows Docker: conversation -> committed fact -> new session -> restart -> recalled provenance | deferred to implementation and operator |

### ABI And Test-Review Evidence Addendum

The official Hermes ABI has no message IDs. Required implementation evidence is
therefore the pinned-image real-loader ABI test; canonical full-message delivery
coordinate tests (including tool structure, absence, mismatch, truncation, exact
replay, and later-position equal text); absent-agent constant/factory-context
tests; every atomic-admission failpoint, uncertain-ack, collision, and restart
test; exact `ScopedContextRequest` mapping and stable task-scope cross-session
test; query/budget mutation impossibility; copied/forged/post-revoke/restart
handle denial; and one selected-path protected-read caller test. These are
required implementation and operational evidence. Their current absence is not
a design defect because no implementation is claimed.

Required phase-mutation evidence additionally proves: sidecar alteration or
expiry after egress and before commit yields `authority_unavailable`, no
candidate/graph/event/projection visibility, and no remote retry; and a pending
operation with altered/expired sidecar before restart makes no remote call or
commit while a stale lease cannot publish. Namespace evidence proves
same-principal/agent Session A -> B recall and denial for changed user, agent,
or a session-bound reusable projection row.

## Open Risks And Level 2 Deferrals

The local sidecar protects against accidental corruption, wrong home, expiry, and malformed configuration; it does not claim resistance to a hostile local operator. The local authorization is single-installation and single-user. Gateway, Slack, delegated agents, shared resource policies, tenant/user scopes, unsupported predicates, ontology learning activation, production certification, and broad migration compatibility are not activated by this design.

## Final Cohort Review And Completion

The final delta cohort reviewed the frozen governing design identities below.
The spec, correctness, and test reviewers approved the bounded Level 2 design
remediation after the final ABI, opaque-envelope, canonical-delivery,
installation-local namespace, in-process scoped-read, and phase-mutation
corrections. No remaining confirmed finding requires a design change at this
delivery fidelity.

The completion contract is satisfied for design only: the semantic runtime
remains Bootstrap V3; project assertions are resource policy inside it; the
local operator mode is a host authorization adapter; and the exact entrypoint,
admission, read, persistence, recovery, and verification contracts are
specified. The deterministic, installed-image, and Windows Docker evidence
remains implementation work and is not claimed by this completed design plan.

The resumption target is the linked
`docs/work/hermes-conversation-memory-trial/implementation.plan.md` WorkPlan.
It must use these frozen contracts and reopen its own readiness, changed-surface,
authority-chain, and evidence ledgers before product edits.

## Next Action

None. The bounded Level 2 design remediation is complete.

## Candidate Freeze Record

The previous candidate was invalidated by four confirmed specification findings.
The frozen normative candidate consists of the two governing design documents;
this WorkPlan records their identity and is not self-hashed:

| Candidate file | SHA-256 |
| --- | --- |
| `docs/design/semantic_ingestion_architecture.md` | `a16d5adc3728d76efdffe3c526bc16476917904b86855a8dcd93f0fa02baee05` |
| `docs/design/hermes_conversation_memory_trial.md` | `81d893d94b0405033f91aa5c67b1de9b5884d4c544174ffb123b959df081152e` |
Cohort reviewers must reject a mismatched file identity and review the exact
typed envelope, admission, and read contracts.
