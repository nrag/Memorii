# Design catalog inspection and structured recall

- Work ID: ontology-catalog-inspection-design
- Work type: design
- Delivery fidelity: Level 2, for manual work and household use with normal failures and scoped access. Release certification and broad historical overlay migration are deferred.
- Status: complete
- Coordinator: main Codex task
- Created: 2026-11-26
- Last updated: 2026-11-26
- Parent WorkPlan: design-recall-diagnosis.plan.md
- Related WorkPlans: design.plan.md, implementation.plan.md
- Canonical inputs: Git baseline `9d661a3b22695a75b398b18ddccc58c1086b3ac7`, prior reviewed working-tree design SHA-256 `521fe95e3c5e850c5eae3c62b6f411194da0e96a08e0f89cc372944a439678f5`, user request and code-based comparison
- Expected outputs: revised gap analysis and combined workflow in `docs/design/learned_ontology.md`, with cohort evidence here

## Objective and Completion Contract

An authenticated host can find a relation's meaning and use it for protected
recall with no Memorii model credentials. The design is complete when the
requirements and installed binding plans below are determinate, reference and
baseline checks pass, and a frozen design clears the three independent design
reviewers, including closure of confirmed findings.

## Scope, Non-Goals, and Invariants

Exact relation ID and normalized name lookup in the selected semantic catalog,
followed by the previously scoped current structured recall. The first manual
path is the verified packaged default. Inspection supports the verified seed
and default packages. No free-text parser, entity name search,
browse endpoint, candidate review UI, learned-overlay migration, host tool
registration, or new persisted format. No read can commit a fact, record
learning evidence, grant visibility, or reinterpret prior assertions.

## Sources Of Truth and Problem Definition

Follow `memorii_spec.md`, `memorii_storage_details.md`, `event_model.md`,
`docs/IMPLEMENTATION_RULES.md` and then the learned ontology and its base
ledger, scoped memory context, temporal retrieval, and semantic forgetting
designs. The prior reviewed Section 12 governs direct recall; the additive
catalog inspection contract shares its protected boundary.

NVIDIA [MCP glossary tool code](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/mcp/auto_ontology_mcp/tools.py#L60-L132)
exposes concept inspection, and its [coverage scorer](https://github.com/NVIDIA/auto-ontology/blob/086b25ec1dbaa8f5911fb746f691d113654b650c/auto_ontology/retrieval/entity_coverage/agents/coverage.py#L172-L209)
scores column matches, not data availability. In Memorii, the
`ProductionRetrievalDecision` and scoped context already expose abstention,
resolution and provenance; the missing product surface is selected-catalog
inspection plus an accurate outcome on the direct structured read.

## Requirements Ledger

| ID | Requirement and source | Acceptance | State |
| --- | --- | --- | --- |
| OCI-01 | Inspect the effective typed relation declarations by ID or normalized name (user, NVIDIA glossary) | Unique and ambiguous results show authorized definitions, typed endpoints and read behavior; absent and invalid inputs yield distinct closed results | Specified in candidate |
| OCI-02 | Keep the lookup-to-recall workflow usable without a model or API key (user, prior diagnosis) | Two verified roots run work and household journeys without write tool, current capture, credentials or egress; an intervening catalog change after inspection cannot silently use a different version | Specified in candidate |
| OCI-03 | Preserve the selected catalog and protected read boundaries (Section 6, Section 12, governing scoped retrieval) | Foreign and inactive catalogs produce no definitions or version identifiers; stale grants fail closed, broken selected closure stays unavailable, and recall preserves prior grant and history checks | Specified in candidate |
| OCI-04 | Keep inspection and recall read only (event and ontology contracts) | Every outcome and retry leaves durable records and learning counters unchanged; inspection examines no fact or transcript payloads to form its result | Specified in candidate |

## Current State and Entrypoint Bindings

The revised contracts are design only, with zero callers today. Baseline
reader and two verified local adapter paths are inventoried in the prior plan.
Use that exact root map, including five explicit direct-reader calls plus the
Hermes bridge's dynamic dispatch. No existing read route is changed here.

The independent mapper reproduced the map at the Git baseline. The packaged
entrypoint is `memorii/pyproject.toml:43` through
`integrations/hermes_factory.py:422` to `MemoriiHermesMemoryProvider`.
The verified local generic root begins at `hermes_factory.py:427`, calls
`build_authenticated_source_runtime` in `integrations/authenticated_source.py:148`,
and currently forwards its read at `hermes_factory.py:480` through the
completed-turn runtime. This existing generic callback is writer coupled;
the new read binding must avoid it. The separate capture consumer at
`production_capture.py:212` supplies no read binding. There are zero
production-tree matches for either proposed method. Shared seams are
`core/provider/service.py:1309` (pure ingress),
`core/scoped_context/authority.py:60,124` (host authority),
`core/memory_plane/service.py:220` (linearized release), and
`core/semantic_ingestion/catalog_capture_pin.py:152` (selected locator).
Do not call write preflight, the writer-coupled local selection resolver,
or the legacy base resolver that can establish registry genesis.

| Trigger and root | Proposed callsite and owner chain | Failure and evidence |
| --- | --- | --- |
| Direct read on `MemoriiHermesMemoryProvider` or `AuthenticatedSourceRuntime` | Each verified factory forwards `inspect_catalog_relation` or `diagnose_structured_recall` with its server-issued `AuthenticatedHostIngress` and closed request to the matching `ProviderMemoryService` method. Reuse Section 12's configured read authority, semantic scope and same-store current grants. | Absent composition unavailable, absent grant denied. Prove both actual surfaces, with no completed-turn requirement on the generic port. |
| Inspection in provider | Pure ingress then `MemoryPlaneService.read_snapshot_linearized`, existing package-indexed selected locator and its authenticated owner/grant checks, read-only declaration projection, deterministic lookup, and host release reauthorization under partition fence. | No current or historical fact-query stage. Missing selected or projection authority unavailable. |
| Diagnosis from inspection result | Host passes user-resolved canonical subject ID, selected relation ID and expected version digest. Same authority path and fresh selected closure, then version comparison, common protected reader and release under existing checks. | Stale version returns catalog_changed; current denial overrides retry. Independent raw and historical paths keep their contracts. |

Both factories use an explicit operator read opt-in, session-bound scoped
handle and exact retained grant references as specified in Section 12.
Neither port calls completed-turn or write-tool providers. Existing setup
and startup recovery happen before the read port and retain their own
failure modes. The intended installed test starts with an authorized,
quiescent, provisioned local store.

## Feasibility and Alternatives

A local read-only probe loaded `SeedCatalogBundleLocator.locate`,
`load_packaged_reports_to_release`, `load_packaged_default_catalog_release`
and the typed base corpus using `env PYTHONPATH=memorii .venv/bin/python -`.
Membership was 3, 4 and 56 respectively. The default version is exactly the
three seed IDs plus the 53 corpus rows, and shares the seed catalog digest
while its immutable version digest differs. The historical four-relation
artifact is nonselectable. The probe confirmed endpoint and read-form fields
for project ownership and the two due-date relations. It does not prove the
new read port.

The mapper confirmed 53 corpus definitions, 47 entity and six literal
object rows, and 37 set, 10 current, and six history forms. Two rows permit
symmetric reads. Verified seed metadata uses the profile and adapter
(`project_assertions_profile.py:188`, `project_assertions.py:111,151,157`);
default metadata uses `default_catalog_package.py:133` and closed
`DefaultCatalogCorpusRow` (`default_catalog_corpus.py:93`). Seed manifest
and default projection need no new stored row. The coverage validator's
existing project-owner synonym collision is experimental evidence of
plausible ambiguity, not a source of public aliases.

Alternatives: model search brings broader paraphrase support at the cost of
determinism and no-key availability. Exact ID lookup alone cannot solve
discovery. Two operations permit clarification across turns. Passing the
checked digest on the second operation rejects a stale choice with no
multi-call transaction, pointer mutation, file migration or persisted token.

## Verification, Failure and Operational Analysis

An offline lookup probe applied the proposed exact normalization and
presentation alias map to actual packaged inventories. `Project Owner`
matched the seed's single ID and both default IDs. `Bill_due-date` and
`work item due date` resolved separately, and `bill` had no match.

| Requirement | Focused proof and equivalence classes | Owner |
| --- | --- | --- |
| OCI-01 | Validate all three seed and all 56 default descriptors, including seed-profile endpoints alongside corpus types, entity/literal arms, symmetric/directed and set/current/history. Missing, substituted or duplicate authority for a nonqueried row makes lookup unavailable. Check exact response fields, label/alias dedup of one ID, two distinct project-owner matches in ID order, bill and work dates, unknown name/ID and strict ID case. Reject blank, oversized, disallowed characters, unknown tags, extra/mixed or missing fields and null. | Core grammar and projection tests |
| OCI-02 | Both verified factories on the default: inspect project owner, clarify and select; inspect bill due date and get found and empty recall. Reopen a provisioned quiescent store with no model, network, valid write tool or capture. Tripwire invocation of completed-turn callback and writer-coupled resolver. Exercise seed-to-default separately using the existing package installation owner's CAS on one initialized core store. Reinspect and retry on the selected default. | Installed integration and controlled core transition |
| OCI-03 | In the core transition, an old seed version expectation with a shared predicate yields catalog_changed before membership/facts, despite the same catalog digest. Repeat with a syntactically valid absent predicate to distinguish precedence from a fresh unsupported request. With version unchanged but facts corrected, recall returns the current fact from the second snapshot. With a stale expectation and revoked selected grant or corrupt authorized state, expect denied or unavailable, respectively. Probe malformed/null expectations after authorization. | Core transition and reader tests |
| OCI-03 | Existing grant without read opt-in denies; opt-in with durable grant and no write tool works. Session/account/agent substitution and denied selected child with a valid parent deny before catalog body, with no fallback. Absent child can select authorized parent; foreign-only records behave like absence; corrupt currently granted local child is unavailable after initialization. Test inactive learned/unused package, redacted statuses, authenticated malformed shape with zero selection/projection, and barriers for same-store fact and catalog revocation, selection and separate host release revocation. Prove legacy and historical reads unchanged. | Scoped core and installed integration |
| OCI-04 | Take durable baseline after setup/reopen, immediately before calling. Compare store/catalog/admission/observations/proposals before and after every result and retry. Tripwire model, recovery, writer, learner and, for inspection, fact/legacy/transcript/source-endpoint probes. No stored handles or aliases after either call. | Core and installed integration |

Use local Python and supported installed local storage at the existing
baseline. No live model or deployment evidence is needed for design. A
combined benchmark or rollout matrix is a future task.

## Identity And Coordinate Hygiene

| Surface | Identity and classification | Proof |
| --- | --- | --- |
| Design docs | Catalog inspection and structured recall (behavioral) | Canonical heading and linked WorkPlan |
| Proposed port/types | `inspect_catalog_relation`, `CatalogRelationInspectionRequest`, `CatalogRelationInspectionResponse`, `CatalogRelationDescriptor`, `expected_catalog_version_digest`, closed fields and status names in Section 13 (behavioral) | Field-aware static gate and closed parser |
| Existing | `diagnose_structured_recall`, current host roots, existing version identifiers (behavioral/protocol; retained) | Prior review, unchanged persisted bytes |
| Planning | OCI-01 through OCI-04 (traceability only) | No runtime identifiers, diagnostics, fixture names or workflow names contain these values |
| Generated/persisted | None new at design time | Scoped diff and authority check |

Future implementation uses the existing PR `memorii.tools.identity_hygiene`
gate, with supported `StrEnum` declarations and narrow typed checks for
actual constructor and fixture positions in `kind`, `status`,
`read_form`, `read_direction` and literal `value_type`. The existing
visitor does not cover all those positions. Mutate each actual behavioral
declaration and structured value with M1, M2, M3, C2, R22 and SIA-R22.
Keep the positive corpus for protocol versions, compatibility IDs and BM25.
Caller `name`, definition text and opaque IDs are data. Prove the same input
is accepted as a lookup value without introducing planning-derived schema
values or broad exemptions. No new allowlist exceptions.

## Change Impact and Verification Closure

Only the canonical design and this linked WorkPlan belong to the operation.
The prior reviewed diagnosis WorkPlan and pre-existing untracked
`docs/work/virtualemployee-integration/` directory are baseline artifacts.
Inspection projects the existing verified declaration closure and a bounded
read-only presentation mapping. It changes no catalog version digest,
descriptor, manifest, resource bytes, CI pin or generated fixture in this
design diff. Future projection must prove inventory equality against each
supported selected version. Prior implementation-plan hashes refer to their
original frozen revisions.

| Surface | Chain and verification |
| --- | --- |
| `docs/design/learned_ontology.md` | Original reviewed digest -> additive gap analysis and two read contracts -> planned pure projection of existing packaged authority; `git diff --check`, read-path validation, cohort freeze |
| This plan | Requirements and preflight -> acceptance ledger and frozen reviewer scope; whitespace plus reviewer fingerprint comparison |
| Package resources and CI pins | Search for canonical-doc consumers in `.github`, `.agents` and `memorii` found no generated or CI inputs referencing this prose. Catalog inventory checks retain existing cardinalities. |

## Assumptions, Decision and Progress Log

Hosts can supply a canonical subject ID or report it unresolved. Presentation
names are for lookup only and cannot grant semantic aliases to the learner or
writer. Candidate review visibility is deferred. Code-based gap analysis and
offline catalog feasibility probe complete. No unresolved user decision.

## Evidence Log

Offline packaged catalog and metadata probe passed. Independent mapper
passed 36 catalog-authority and capture-pin tests and confirmed no
production callers. The coordinator ran both suites plus structured fact
read and scoped context activation with
`env PYTHONPATH=memorii PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -q`
on their four unit modules, 66 tests passed. From `memorii/`,
`../.venv/bin/python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json`
passed. Both documentation paths passed whitespace checks. The unit and
identity checks establish baseline behavior only.

## Review Log

Draft cohort freeze at baseline `9d661a3b22695a75b398b18ddccc58c1086b3ac7`.
Design SHA-256 `3fe8cc76d91e597cc19854955d080a9633980a576836b4252919dc355a970b46`,
Git-scoped canonical-design diff SHA-256
`830196c441565d789a50563b2de66484c12e28de9ae4c5b6d977b43367183300`,
and WorkPlan prefix before Review Log SHA-256
`3ae87147c9b32aba8268cb7c13ab579104ebe0cc8bac27275a490f36d6cb256a`.
No writer active. Scope, verification, prospectively mapped design entrypoints
and historical exclusions are recorded above. New ports have zero callers.

The draft cohort requested changes. The coordinator confirmed and reconciled
the findings as one revision:

| Finding family | Disposition and closure |
| --- | --- |
| Explicit read authority | Contract conformance. Both controlled roots require operator opt-in, verified ingress tied to session and exact current durable grants, an ephemeral scoped read handle with release validation, and no writer/tool prerequisite. |
| Seed endpoint authority in a default projection | Contract conformance. Seed and corpus use their verified owning declarations and separate type vocabularies; tests cover all descriptors and omission of a nonqueried row. |
| Factory startup and stale inspection | Entrypoint conformance and evidence action. Separate ordinary authorized startup from the read call, live failure from initialization rejection, and owned core seed-to-default transition from the installed default proof. Require distinct precedence witnesses and current fact contents. |
| Inspection and release verification | Evidence action. Add scope/authority/response sibling outcomes, tripwires across both installed roots, and separate grant and release barriers. |
| Identity enforcement | Contract conformance. Explicitly map static enum and typed fixture/constructor fields with mutation and positive-corpus checks. |

No demonstrated new P1/P2 defect remains. First installed inspection is
packaged only; projection of learned descriptions and suppression authority
is a follow-up. Earlier exact diagnosis rules for learned closure still apply.

Final cohort freeze at the same Git baseline:
design SHA-256 `66daeb911884d4f3cf9a5ffb70115040b6a226bd00249a63dcd73281a65ff93a`,
scoped Git diff SHA-256 `5127b992ed22b21cef6ae4665439f687ba3cc5566110842c081947441ae2141d`,
and WorkPlan prefix SHA-256 `fda3096379215437a6fc6a9b970b7c399bd6de4ef6a1170977cda79765627ff3`.
Whitespace checks passed; the existing baseline and unchanged package authority
evidence remain applicable. No writer active.

| Final reviewer | Verdict |
| --- | --- |
| Spec auditor | Approved. Independently reconstructed the four requirements and the behavioral identity ledger. All three draft findings closed. |
| Correctness reviewer | Approved. Verified startup versus live failure, the owned transition, read authority and declaration closure. No remaining findings. |
| Test reviewer | Approved. Reproduced the package and exact-name probes. Verified the acceptance cases distinguish stale catalog, current data, grant, and lookup outcomes. No remaining findings. |

Final design bytes match the recorded freeze. The reviewed WorkPlan prefix
digest precedes completion bookkeeping. All 66 baseline tests and the
existing identity check passed. No production code, version authority,
generated resource or CI pin changed.

## Blockers And Limits

Exact parent evidence remains required for early learned versions. A verified
active catalog without it cannot be inspected or used by exact diagnosis.
Existing historical and scoped retrieval remains separate.

## Next Action

None. Design complete; a separate implementation operation can consume the
frozen workflow and its acceptance matrix.

## Outcome And Retrospective

No unresolved validated design gap remains within the recorded scope and
review method. OCI-01 through OCI-04 are specified and reviewed. Both ports
and the installed no-key proof remain implementation work.
