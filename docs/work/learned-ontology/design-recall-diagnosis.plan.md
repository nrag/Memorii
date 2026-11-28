# Design structured recall diagnosis

- Work ID: ontology-recall-diagnosis-design
- Work type: design
- Delivery fidelity: Level 2, for manual work and household validation with ordinary failures and scope isolation. Release packaging, exhaustive platform and tamper matrices, and operational certification are deferred.
- Status: complete for design
- Coordinator: main Codex task
- Created: 2026-11-26
- Last updated: 2026-11-26
- Parent WorkPlan: design.plan.md
- Related WorkPlans: implementation.plan.md
- Canonical inputs: baseline `9d661a3b22695a75b398b18ddccc58c1086b3ac7`, governing design and verified repository paths below, user request for agent-agnostic no-key diagnosis and cohort review
- Expected outputs: additive recall diagnosis in `docs/design/learned_ontology.md` and cohort evidence in this plan

## Objective

Give hosts a reliable reason for a structured semantic recall hit, miss, or
abstention. Let a signed-in user try the same workflow for a project or bill
with no model credentials configured in Memorii.

## Completion Contract

All requirements below are specified in the normative design, covered by the
verification matrix and mapped to existing or proposed entrypoints with
maturity labeled. Reconcile three independent reviewers against a frozen
revision, close confirmed design defects and determinate conformance issues,
and run the final whole-change cohort. Confirm no product, persisted, or
generated authorities changed.

## Scope and Non-Goals

One current catalog-bound semantic fact query with a canonical subject ID and
predicate ID, plus an explicit unresolved input. The first installed target
is a verified packaged catalog. Learned selections with a provable exact
parent closure use the same contract. Existing learned versions without that
proof return unavailable, and a compatibility binding or rebase is deferred.
Historical recall and unbound legacy retrieval remain separate operations.
Automatic name resolution, raw-text analysis, new host tool registration,
schema mutation, coverage event persistence, and review UI are excluded.

## Sources Of Truth and Constraints And Invariants

Precedence: `docs/design/memorii_spec.md`, `docs/design/memorii_storage_details.md`,
`docs/design/event_model.md`, `docs/IMPLEMENTATION_RULES.md`, then the ontology
design, its base catalog and installed addendum,
`docs/design/semantic_temporal_retrieval.md`, `docs/design/scoped_memory_context.md`
and `docs/design/semantic_forgetting.md`. Preserve scoped identities,
current fact and catalog grants, historical fact interpretation, candidate/
committed separation, and pure retrieval. The user owns household facts in
their signed-in account. NVIDIA's [architecture](https://github.com/NVIDIA/auto-ontology/blob/main/docs/architecture.md#check-answerability)
is inspiration; its fraction of matched concepts provides no activation evidence.

## Problem Definition and Current State

The structured reader can return successful empty results, but its predicate
recognizer catalogs packaged IDs and a special learned relation independently
of the caller's exact selected version. Unknown IDs and errors can both return
unavailable. A host cannot reliably distinguish absent facts from unsupported
requests. The provider ingress preflight also has writer side effects. The new
operation is design-only and has zero current runtime callers.

## Requirements Ledger

| ID | Requirement | Source | Priority | Acceptance criteria | Status |
| --- | --- | --- | --- | --- | --- |
| ORD-01 | Agent-neutral structured, no-key read | User, ontology no-key path | Required | Two verified host surfaces return identical outcomes on retained facts with write tool, capture and model configuration absent and outbound network denied, and both independently fail closed without a read grant | Specified |
| ORD-02 | Explain hit, readable miss, unsupported predicate and unresolved input | User, NVIDIA answerability | Required | Known hit/empty, valid absent predicate, unresolved reference, malformed input and unverified selection produce their exact response arms and fields with stated precedence | Specified |
| ORD-03 | Select and read through one protected authority boundary | Spec, storage, ontology scope, temporal/forgetting | Required | Current grants, same snapshot selection and exact history, current validity, hidden-only equals absent, pre-tombstone suppression, and invalid visible authority fail closed | Specified |
| ORD-04 | Preserve learning and storage boundaries | Ontology Sections 5 to 8, event model | Required | Every outcome leaves sources, observations, candidates, facts, and catalog untouched; repeat reads and unsupported questions never count as recurrence | Specified |

## Existing-System Analysis and Production Entrypoint Bindings

The independent mapper searched the baseline with
`git grep -n -E '\.read_structured_facts\(' HEAD -- memorii/memorii` and
`rg -n 'locate_selected\(' memorii/memorii --glob '*.py'`. It found five
direct reader calls and one dynamic Hermes bridge dispatch, six selected
bundle locator calls, and zero diagnosis callers. The existing local generic
adapter is callable through a verified factory and exercised in tests, but
Hermes is the only packaged plugin entrypoint. This design creates no
production callsite. The design review checks
determinacy of the proposed binding and the baseline seams, and claims zero
implemented reachability for the new operation. Actual caller count and path
proof are implementation prerequisites.

| Baseline owner | Concrete evidence and design consequence |
| --- | --- |
| `integrations/hermes_memory_provider.py:213` and `integrations/hermes_factory.py:480` | Installed bridge and generic local binding call `HermesCompletedTurnRuntime.read_structured_facts` (`hermes_completed_turn_runtime.py:2087`), which issues ingress using session, pinned author and time and passes the host's authority request to the provider service. The standalone generic runtime without the injected binding fails closed. New production bindings must pass fresh verified read ingress without routing through the captured-tool surface. |
| `core/provider/service.py:1317,1696` | Existing reader runs writer-admission preflight, resolves write-shaped authority and takes a protected snapshot. Refactor/reuse pure ingress (`_resolve_ingress`) and snapshot release, with a read-only authority binding and no preflight side effects. |
| `core/semantic_ingestion/catalog_capture_pin.py:152` and `learned_relation.py:1298` | Selected locator resolves installed base or authenticated agent-local version from supplied records. Reuse it within the protected snapshot. The host's existing resolver takes an earlier snapshot and can return seed authority when the actual packaged pointer selects a child, so its catalog digest cannot establish support. |
| `core/semantic_ingestion/structured_fact_read.py:95,214,498,618` and `core/scoped_context/service.py:710` | Current reader uses static relation recognition and tests grant equality after matching some claim paths. Foreign matching facts can cause unavailable. The new path needs scope pruning with the existing protected verifier and declaration-based policy. This is also the seam for the seed IDs, which are selected in the catalog but absent from the current direct reader table. |
| `core/scoped_context/authority.py:60,124`, `core/provider/service.py:1131`, `core/storage_administration/revoked_identity_view.py:117,326` | Scoped host grant reauthorization and the partition callback are reusable separately. The storage administration view owns suppression lookup. Its raw record filter is insufficient for projection provenance. Diagnosis must test the verified closure against a single refreshed view before serving. |
| `core/semantic_ingestion/learned_relation.py:736,1184,1298` and `core/semantic_ingestion/catalog_capture_pin.py:230` | First learned version lacks a pinned packaged parent and its proposal's catalog digest can identify either seed or child. No supporting immutable bundled parent proof found. |

| Requirement | Trigger/root | Proposed owner chain and exact authority | Status |
| --- | --- | --- | --- |
| ORD-01, ORD-02 | Direct `diagnose_structured_recall` on packaged `MemoriiHermesMemoryProvider` or generic `AuthenticatedSourceRuntime` | Verified host binding forwards the request and server-issued `AuthenticatedHostIngress` to the same provider method. The configured read authority resolves ingress to the partition and current grant references separately from write tooling. | Proposed |
| ORD-03 | Same protected snapshot in provider | Existing types for fact and catalog visibility, resolved semantic rows and trusted UTC time -> core selection -> selected predicate and capability -> same-snapshot current read and historical joins -> host release reauthorization and storage admin suppression sample | Proposed |
| ORD-04 | Any attempt or retry | Pure ingress, selection, and retrieval; no writer, capture, bootstrap, observer or replay dispatch | Proposed |

## Alternatives Considered and Decision Log

Use a combined, typed result rather than a separate check followed by a read:
separate calls could see different pointer/grant versions and raise agent
latency. Keep the existing historical read separate instead of redefining a
previous response. Use exact selectors and explicit unresolved input instead
of model/embedding inference or matching across unscoped aliases. A blank
result cannot safely infer a missing type or relationship.

## Assumptions And Open Questions

The host can supply a canonical subject ID or report unresolved input. This is
the same structured input assumption as the existing reader. A host may use
its own interpretation tools upstream. The design makes no claim of universal
no-key free-text name resolution. No open product decision at draft.

## Feasibility Evidence

Baseline protected reader unit command:
`env PYTHONPATH=memorii .venv/bin/python -m pytest -q memorii/tests/unit/core/semantic_ingestion/test_structured_fact_read.py`
passed 7 cases. It proves current/history, symmetric rendering, revocation,
and integrity behavior on scoped fixtures. The scoped-context baseline command
`env PYTHONPATH=memorii .venv/bin/python -m pytest -q memorii/tests/unit/core/test_scoped_context_activation.py`
passed 23 cases. Neither exercises diagnosis.
The separate scope/selection seam and verified read-only ingress are explicit
new design work, rather than assumptions about the existing reader.

## Failure And Operational Analysis and Verification Strategy

Deterministic fixtures start from the same authorized local data and compare
returned discriminators and existing protected items. No live provider or
production deployment is required for this design. Implementation owns
behavioral proofs below.

| Requirement | Test cases and boundary | Evidence owner |
| --- | --- | --- |
| ORD-01 | On reopen after ordinary validated write and grant provisioning, call both the packaged Hermes bridge and the generic authenticated root with separately supplied host ingress/read binding. Remove write-tool configuration, capture, and model credentials, block outbound traffic; compare the two responses for `obligation_due_on` on a Bill and `work_item_due_on` on a WorkItem. Omit read authority and verify fail-closed behavior despite data being present. Inspect both paths for direct binding to the shared core. | Installed integration |
| ORD-02 | Assert exact serialization of all seven arms and protected metadata on forward/reverse hits. Exercise empty and retracted facts, more than one visible value, seed versus default, the installed unproved overlay after reopen/base rotation, valid unknown predicate, unresolved subject/relation/both, and malformed/mixed arms and wildcard. Missing ingress or grant takes precedence over malformed/unresolved/unknown. Authorized malformed or unresolved inputs make zero catalog-content and fact probes. Exercise active/corrupt child versus absent child and denied child on exact requests. | Protected reader, installed integration |
| ORD-03 | Hidden-only equals absent and visible-plus-hidden equals visible-only, for both other-account and same-user other-agent facts in forward/reverse paths. Test schema-1 seed-bound and schema-2 pinned reads with unrelated unbound legacy present; test missing visible binding versus unrelated corrupt data. State-backed and projection-only cases cover exclusive end, inclusive start, future start, open and retracted validity. Verify current pre-tombstone suppression for claim, record, source and either entity endpoint, without shrinking authoritative snapshots. Use ledger barriers, not timing: switch between verified selections that disagree on the queried predicate, proving either old found then unsupported or unsupported when pointer change wins. Fact and catalog grant revocations each prove denied if first or old allowed result followed by denial. Assert one partition snapshot and separate host/serving release checks. | Protected reader, scoped context, installed integration |
| ORD-04 | Begin zero-write observation after setup and reopen. Repeat every result with the write tool absent; assert unchanged scope/grant/catalog/record bytes and no writer admission, sidecar repair, capture/pin, recovery work, observation, inference, or recurrence dispatched by the call. Verify retained history and separate authorized unbound legacy reads across selection change. | Core composition and installed integration |

For the ORD-03 suppression race, pause after candidate closure assembly and
before the final view sample. Apply through the journal without publishing a
tombstone, then resume. Require the absent-equivalent result in both directions
and preserve an unaffected visible match. Reverse the order and require
suppression on the next call. Also distinguish a suppressed, known provenance
coordinate whose artifact was removed (exclude) from a missing required
coordinate without verified suppression (unavailable). A failed serving-view
refresh returns unavailable.

## Identity And Coordinate Hygiene

| Surface | Identity | Class | Disposition and proof |
| --- | --- | --- | --- |
| Canonical section and plan | Structured recall diagnosis, design-recall-diagnosis.plan.md | Behavioral | Add; heading/link review |
| Proposed core/public | diagnose_structured_recall, StructuredRecallDiagnosisRequest, StructuredRecallDiagnosisResponse, request/result enums and fields inventoried in normative section | Behavioral | Names describe read behavior independently of delivery order; future parser and identity checks |
| Existing | StructuredFactReadRequest, StructuredFactReadItem, StructuredFactReadAuthority | Behavioral | Reuse without changing existing protocol |
| Ledger | ORD-01 through ORD-04 | Planning | WorkPlan traceability only |
| Persisted, generated, workflow, fixture IDs and wire versions | None introduced | Not applicable | Repository diff and reference search |

Future implementation uses the field-aware `memorii.tools.identity_hygiene`
gate in `.github/workflows/pr-gates.yml` for actual `kind`, `status` and
`reference` declaration, constructor, and structured fixture slots. The
current scanner recognizes `StrEnum` members but misses some `Literal`
annotations and constructor values, so require supported enum declarations
and extend typed field recognition only where actual introduced shapes need
it. Mutate each form with M1, M2, M3, C2, R22 and SIA-R22 in the checker and
closed runtime grammar. Treat existing entity IDs as opaque behavioral
values. The positive corpus retains BM25, wire versions, and compatibility
identifiers. No new identity allowlist entries.

## Change Impact And Verification Closure

| Path | Surface | Authority chain and gate | Status |
| --- | --- | --- | --- |
| docs/design/learned_ontology.md | Normative prose | Governing sources -> new structured recall contract -> future implementation requirements; no compiled authority input or pin found | Reviewed |
| docs/work/learned-ontology/design-recall-diagnosis.plan.md | Design evidence | WorkPlan requirements -> review freeze and recorded evidence | Complete |
| docs/work/virtualemployee-integration/ | Pre-existing untracked work | Outside ontology operation at baseline; excluded from candidate fingerprint | Recorded |

Gate ledger: design diff whitespace and changed-surface/identity inspection,
reference search, baseline reader and scoped-context tests, independent reviews. Existing
static gate reproduced successfully from `memorii/` with
`../.venv/bin/python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json`.
No current-revision production CI gate is asserted for new behavior. Known failure
ledger: no failure observed in the baseline reader test.

## Milestones Or Experiments, Progress Log And Evidence Log

- 2026-11-26: Mapped the baseline protected reader and compared NVIDIA's
  answerability, retrieval and certification notes with Memorii's design.
- 2026-11-26: Existing protected read unit suite passed, 7 tests.
- 2026-11-26: Independent baseline mapper mapped both installed adapters,
  selection, and release ownership. Drafted the canonical contract from
  those observations.
- 2026-11-26: Three draft reviews reconciled into one contract revision below.

## Review Log

Draft cohort freeze: baseline `9d661a3b22695a75b398b18ddccc58c1086b3ac7`,
canonical design SHA-256 `2eb2ae8927b674f23163c395e59769990a6109728718236a5913bc3bba9db09b`,
scoped binary diff SHA-256 `9568fe3680e79b24ac18674d03e93b8dfb5aeef0add2df75233bc0ac01f059a4`,
plan requirements/path/evidence section (before Review Log) SHA-256
`6ea191238d5314c1010cafdcfcb2c2df0484d0c01c9a6d6192ea9c2282297f21`.
No active writer. Scope is the additive diagnosis and its stated exclusions.
Whitespace and baseline-reader checks pass. The preflight map is recorded
above. Application tests for new proposed behavior are implementation work.

Draft cohort: spec, correctness, and verification each requested changes.
Reconciled all findings against the baseline; overlapping observations are
grouped by root cause:

| Finding family | Coordinator disposition and closure in the revised candidate |
| --- | --- |
| Learned parent proof | Confirmed P2 in the proposed ordinary overlay flow. First activation lacks a packaged parent version and the digest is shared. Restrict first installed diagnosis to verified packaged catalogs and any version with a provable exact closure. Earlier unproved overlays are explicitly unavailable, with current protected retrieval separate. Reopen after pointer change is a negative proof. A later binding/rebase is outside this operation. |
| Projection suppression and release | Confirmed P2 in the common journal-before-tombstone path. Require the injected view, explicit claim/endpoint/provenance closure in both directions, and separate same-store, host, and serving checks at release. |
| Temporal eligibility | Confirmed P2; correctness reviewer reproduced an expired active `partner_of` through both baseline carriers and directions with only historical verification stubbed. Require half-open current eligibility and verify both carriers and directions. |
| Item schema, legacy eligibility, status and scope precedence, host binding | Confirmed conformance. Define item vs envelope metadata, seed/pinned/legacy classification, data-independent authorization order, and both direct host read bindings independent of writing. Update the design status and spell out the tested path. |
| Discriminating two-root, scope and release tests | Confirmed evidence action. Add no-write-tool reopen, both composite-scope equivalences, and barrier-controlled races with different expected outcomes. Runtime proofs remain implementation work. |
| Identity check coverage | Confirmed conformance. Reviewer probed the visitor and found blind spots. Bind implementation mutations to the existing field-aware gate and name the narrow extension. |

Revised final-cohort freeze: same baseline, canonical design SHA-256
`521fe95e3c5e850c5eae3c62b6f411194da0e96a08e0f89cc372944a439678f5`,
scoped binary diff SHA-256
`20ce84a45b4791c367786d6b9477114cf7ed6e29bc71b349ed9ca830d074f5e1`,
and plan requirements/path/evidence prefix SHA-256
`dc29e85fe24ed5d84613e6340e725c611f072efc25b9659b21b9c1949af21a4f`.
Updated authority map above, whitespace and applicable baseline checks pass,
and no active writer.

Final cohort found no new product defect. Verification requested one bounded
evidence action: the anticipated journal-before-release test must publish
suppression between candidate assembly and the final view sample, or a stale
view could pass. The ORD-03 witness above adds both orderings, the failure
response and known-versus-unknown provenance. The reviewed design digest is
unchanged.

| Final reviewer | Verdict |
| --- | --- |
| Spec auditor | Approved. Independently reconstructed ORD-01 through ORD-04 and the behavioral identity ledger against the agreed packaged scope. |
| Correctness reviewer | Approved. Verified closure of all four draft finding families and the design/runtime evidence boundary. |
| Test reviewer | Approved after targeted delta. Verified all draft verification findings and the final journal-before-release case. Reviewed evidence prefix SHA-256 before closure bookkeeping: `9c2e41139eb29c9f17637fa4ee7832c50b99b98f149dbbc37b7351d56669a57f`. |

Final design SHA-256 remains
`521fe95e3c5e850c5eae3c62b6f411194da0e96a08e0f89cc372944a439678f5`.
The two baseline suites passed 30 tests together and static identity hygiene
passed. These prove baseline behavior and tooling, not diagnosis. Final
change inspection found two owned documentation paths and the recorded,
pre-existing untracked directory. Historical implementation-plan digests
remain references to their original approved revisions.

## Blockers And Limits

Runtime behavior is specified only. Existing local installations must
already have current grants. An earlier learned version without exact
parent evidence is outside the first installed diagnosis path. No format or
grant-provisioning migration is proposed.

## Next Action

None. A later implementation operation can plan against the frozen Section 12.

## Outcome And Retrospective

No unresolved validated design gap remains within the agreed packaged scope
and review method. All four requirements are specified. No diagnosis port,
new runtime evidence, or rollout approval is claimed. The exact-parent
limitation for earlier learned overlays is recorded in the design and its
verification matrix.
