# Semantic Ingestion Bootstrap Local Profile

- Work ID: semantic_ingestion_bootstrap_local_profile_2026_08_01
- Work type: design
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-08-01
- Last updated: 2026-08-01
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/m0-scenario-first-c2-implementation-2026-07-30/implementation.plan.md`
- Canonical inputs: `docs/design/memorii_spec.md`, `docs/design/memorii_storage_details.md`, `docs/design/event_model.md`, `docs/IMPLEMENTATION_RULES.md`, `docs/design/semantic_ingestion_architecture.md`
- Expected outputs: an approved canonical architecture revision resolving `SIA-ED-TOPOLOGY-001` for the unshipped bootstrap profile; an implementation handoff only after approval.

## Objective

Define one out-of-box, network-denied local semantic-ingestion profile that a
normal Memorii construction selects automatically. It must use only repository
components already shippable today, preserve provider schema and independent
legacy-reader compatibility, and state truthful local outcomes rather than
replaying obsolete lifecycle bytes.

## Problem Definition

The requested ordinary local bootstrap path conflicted with an unresolved
topology decision and historical dynamic outcome fixtures. The design must make
one deterministic profile truthful and verifiable without claiming M2 resource
admission or M3 semantic promotion.

## Requirements Ledger

| ID | Requirement | Source | Priority | Acceptance criteria | Status |
| --- | --- | --- | --- | --- | --- |
| BLP-R01 | M1 is source-only | SIA-R19/R20/R21; Section 3.23.0 | P1 | No M1 fence/resource/reservation/lease/writer/allocation artifact or projection | addressed |
| BLP-R02 | Bootstrap artifacts resist substitution | SIA-R08/R13; traceability release authority | P2 | Independently rooted active signed release binds anchor, coordinate, profile, capability, corpus, and component root before construction | addressed |
| BLP-R03 | Corpus behavior is closed | SIA-R08/R22; Section 3.23.0 | P2 | Validator rejects every tuple outside the language/disposition/reason matrix and stages map deterministically | addressed |
| BLP-R04 | M1 remains truthful and compatible | SIA-R22; provider contract | P1 | Five M1 outcomes; protected full outcome and unchanged coarse provider envelope | addressed |
| BLP-R05 | Regeneration is controlled | SIA-R03/R13; traceability release authority | P2 | Exact design digest and coordinated release-anchor-artifact evidence are repinned before implementation resumes | linked follow-up prerequisite |

## Non-Goals

This work does not implement M1, change tests, authorize M2 resource admission,
authorize M3 candidate/terminal behavior, activate remote execution, or
regenerate traceability artifacts.

## Existing-System Analysis

Repository inspection established the deterministic English rule extractor,
compiler, validator, service, and ordinary provider roots. It did not establish
shippable learned-language assets. Existing `LocalAdmissionOutcome` includes an
operation fence and resource profile, so it is explicitly deferred to M2.

## Alternatives

| Alternative | Disposition | Reason |
| --- | --- | --- |
| Learned/local model bootstrap | rejected | No verified packaged asset/dependency evidence |
| Remote fallback | rejected | Violates local-first and no-fallback boundary |
| Reuse `LocalAdmissionOutcome` in M1 | rejected | Imports M2 resource/fence semantics |
| Deterministic English-rule profile | selected | Existing bounded dependency-free path |

## Feasibility Evidence

The named components exist in the repository and need no model download. The
design requires a future consistency gate with construction spies and socket,
DNS, and HTTP traps; this is planned verification, not evidence that the gate
already exists.

## Failure And Operational Analysis

Anchor, manifest, corpus, component, ordering, remote-selector, language, and
grammar failures fail closed to `unavailable`, `unsupported_input`, or
`abstained` as applicable while retaining source evidence. M1 never claims
resource admission. Explicit disablement remains evidence-only.

## Verification Strategy

| Requirement | Verification |
| --- | --- |
| BLP-R01 | Static persisted-kind/projection audit plus M1 negative tests for fence/resource/lease/allocation |
| BLP-R02 | Active-release/lifecycle/root verification plus coordinated release-anchor-artifact substitution, CTV mutation, duplicate, ordering, and component-root tests |
| BLP-R03 | Corpus cases and invalid-tuple mutations for missing, untrusted, mismatched, non-English, supported, rejected, and unlisted inputs |
| BLP-R04 | Protected-accessor union, provider-envelope compatibility, and exact M1 outcome matrix |
| BLP-R05 | Controlled traceability regeneration binding the exact reviewed design digest |

## Completion Contract

- The architecture names one owner, profile ID/version, component inventory,
  startup verification, selection, disablement, failure behavior, rollout,
  rollback, and deterministic acceptance matrix.
- It explicitly resolves the `SIA-ED-TOPOLOGY-001` and R08/R19/R22 conflict
  without selecting absent model assets or a remote fallback.
- The revised text distinguishes public wire/schema compatibility from obsolete
  runtime outcome bytes, and leaves semantic-result disclosure on the protected
  accessor.
- The plan records design checksum and traceability/registry impact, and a
  review classifies all findings under `AGENTS.md` before approval.

## Scope

Included: the initial built-in profile, normal-root selection, explicit
disablement, local/network/failure semantics, R22 compatibility interpretation,
and deterministic acceptance design.

Excluded: production implementation, provider-envelope migration, M2 writer or
generation work, remote capability activation, Stanza/spaCy/model packaging,
policy threshold selection, and traceability authority regeneration.

## Constraints And Invariants

- The profile coordinate is `memorii.bootstrap_local_english_rule` version `1`
  (`.v1` is display-only) and is a bootstrap
  contract, not a claim of globally certified language or learned capability.
- It composes `EnglishRuleMemoryExtractor`, the existing deterministic compiler,
  validator/reconciler, and `MemoryEvolutionService` through the canonical
  provider/memory-plane path; network access is denied.
- Only supported English rule forms may produce semantic candidates. Unsupported
  language/forms, missing/corrupt implementation prerequisites, or explicit
  disablement retain governed evidence and return a typed no-semantic outcome.
- Remote remains an explicit operator-selected capability and never a fallback.
- Candidate state remains distinct from committed state. This design does not
  authorize M2 lease, writer, fence, or atomic-generation semantics.

## Sources Of Truth

The precedence is `memorii_spec.md`, `memorii_storage_details.md`,
`event_model.md`, `IMPLEMENTATION_RULES.md`, then
`semantic_ingestion_architecture.md`. User authority on 2026-08-01 resolves the
previous external topology decision for this narrow unshipped bootstrap profile.

## Current State

Verified facts: the repository contains `EnglishRuleMemoryExtractor`,
`SemanticIngestionCompiler`, `MemoryEvolutionValidator`, and
`MemoryEvolutionService`; it does not establish bundled Stanza/spaCy/model
assets as a shippable prerequisite. The current architecture checksum before
this revision is `70ace2b99c4db79911f45555f72cde43278ccaac69c1fc11530e2d474f1fa26c`.

Interpretation: the former evidence-only default contradicts the requested
unshipped out-of-box product behavior and makes historical execution outcomes
the only way to satisfy the frozen R22 corpus. The bootstrap profile resolves
that contradiction by making truthful deterministic local execution normal.

## Assumptions And Open Questions

Verified facts: normal provider construction already owns the relevant local
components, although its current implementation must be revised in a later
implementation WorkPlan.

Working assumptions: static Python module integrity and exact profile component
identifiers are sufficient startup prerequisites for this dependency-free rule
profile; no model-asset hash is claimed.

Unresolved questions: none that alter the narrow bootstrap semantics. Whether a
later profile may add learned/local model assets remains a separately approved
profile revision.

Decisions requiring external input: none for this user-authorized bootstrap
profile. Traceability digest/registry regeneration remains a later controlled
artifact operation.

## Milestones

### D1 - Feasibility and contract boundary

- Purpose: establish the smallest real local component set and its unsupported
  boundary.
- Expected artifacts: evidence in this plan and architecture revision.
- Verification: repository symbol/dependency inventory and document audit.
- Status: complete.

### D2 - Canonical profile resolution

- Purpose: replace the unresolved external topology default with the bounded
  built-in profile contract.
- Expected artifacts: architecture sections and R22 compatibility rule.
- Verification: architecture grep/audit and design checksum.
- Status: complete.

### D3 - Design review and implementation handoff

- Purpose: validate the acceptance and attack matrix before any code resumes.
- Expected artifacts: review report and updated implementation baseline.
- Verification: spec/correctness/test review.
- Status: complete. Final spec, correctness, and test reviews found no remaining
  design defect at digest `aae9faa1d7fce59c658308114286a33250245b764b2cef3dde51ad3a47f2f785`;
  the outstanding spec-evidence item is resolved by those review records.

## Verification And Attack Matrix

| Scenario | Expected result | Failure signal |
| --- | --- | --- |
| Normal English supported form | automatic local deterministic path, network denied | no local outcome or network attempt |
| Unsupported language/form | evidence retained, explicit abstention/no-semantic result | semantic candidate/graph mutation |
| Explicit disablement | evidence retained, disabled outcome | local or remote execution |
| Corrupt/missing bootstrap code prerequisite | fail closed, evidence retained | fallback or partial promotion |
| Remote unset | no remote transport | any remote call |
| Remote selected | explicit separate capability only | implicit selection/fallback |
| Provider reader | unchanged public schema/reader decoding | schema/reader incompatibility |
| Historical incompatible outcome corpus | does not override truthful bootstrap execution | fabricated lifecycle fields |

## Progress Log

- 2026-08-01: Final spec, correctness, and test reviewer results at design
  digest `aae9faa1d7fce59c658308114286a33250245b764b2cef3dde51ad3a47f2f785`
  found no remaining design defect. The coordinator accepted those results and
  resolved the spec-evidence item. D3 and this design WorkPlan are complete;
  controlled regeneration/review is a linked implementation prerequisite, not
  pending design work. No canonical design, code, or test artifact changed.

- 2026-08-01: Design remediation round 5 made corpus disposition stage-neutral,
  closed the cross-field language/disposition/reason matrix, and independently
  rooted the bootstrap anchor through the active signed traceability release.
  No code or test was edited. Next action: final design review, then controlled
  traceability/artifact regeneration for the reviewed exact digest.

- 2026-08-01: Design remediation round 4 separated M1 governed-source
  admission from the M2 resource protocol; added the immutable trust-anchor
  contract, unambiguous capability/corpus/profile artifact graph, closed
  corpus language/evidence behavior, and live-input digest rule. No code or
  test was edited. Next action: controlled traceability/artifact regeneration
  for the resulting exact digest; final design review follows that gate.

- 2026-08-01: Design remediation round 3 made the M1 outcome set, typed
  coordinate, resource/semantic mapping, fingerprint/corpus schemas, and
  required future consistency gate closed. The post-round design digest is
  `39afbdcc269dd921235e2dd9b397daf90ad8fb92d59269903de4629da8f5b0fd`.
  No code or test was edited. Next action: final design delta review, then the
  controlled traceability/artifact regeneration gate before M1 resumes.

- 2026-08-01: Design remediation round 2 closed the profile outcome algebra,
  manifest verification authority, bootstrap remote exclusion, whole-segment
  language grammar rule, exact root/confinement matrix, and remaining topology
  references. The frozen post-round design digest is
  `f899eedb017cb48d1f67854839a08a2aba7bf241184ac8b3370f2391f1abb579`.
  No code or test was changed. Next action: execute the controlled traceability
  repin/regeneration gate for this exact digest, then obtain fresh independent
  design review before M1 resumes.

- 2026-08-01: User authorized the bounded bootstrap-profile design and prohibited
  production/test edits in this operation. Inspected current local components
  and dependency reality; drafted the canonical resolution. Next action:
  independent design review of this bounded architecture change.

## Evidence Log

- `rg` located `EnglishRuleMemoryExtractor` in
  `memorii/memorii/core/memory_evolution/extraction.py`, compiler in
  `semantic_compilation.py`, validator in `validation.py`, service in
  `service.py`, and normal provider factory in `core/provider/factory.py`.
- The initial architecture SHA-256 is recorded in Current State.

## Decision Log

- D1: choose the deterministic English rule path rather than an unverified
  learned/local-model profile because it is the only named, dependency-free
  current implementation. Consequence: the first profile explicitly abstains
  outside supported English rule forms.
- D2: R22 preserves public schema/legacy-reader compatibility, not historical
  runtime outcomes that misrepresent actual bootstrap execution. Consequence:
  compatibility fixtures must be reclassified or regenerated only after this
  design is approved; no implementation may fabricate their outcomes.

## Traceability And Registry Impact

This canonical design revision changes normative R08/R19/R22, topology, and
bootstrap-release binding. The revised semantic-ingestion design SHA-256 is
`aae9faa1d7fce59c658308114286a33250245b764b2cef3dde51ad3a47f2f785`; any registry, CTV, profile binding,
active signed bootstrap release, traceability authority, and execution evidence
that bind the old design digest are stale until the controlled
regeneration/review operation. No authority artifact is regenerated here.

## Next Action

No design action remains. The linked follow-up is controlled
traceability/artifact regeneration and review for digest
`aae9faa1d7fce59c658308114286a33250245b764b2cef3dde51ad3a47f2f785`
before implementation resumes.

## Review Reconciliation

- DR1 (`Not applicable / changes_required / compatibility`): confirmed. The
  initial wording preserved obsolete dynamic outcome bytes too broadly. The
  R22 ledger now freezes only schema/declaration/enum/default/nullability/
  validator/legacy-reader compatibility and contains the explicit historical
  reader versus profile-versioned behavior transition matrix.
- DR2 (`Not applicable / changes_required / architecture`): confirmed. The
  first draft left scattered topology-unresolved language and implied core
  self-authorization. Section 3.23.0 now resolves bootstrap everywhere,
  assigns host adapters selection/writeback authority, and requires a static
  contradiction audit.
- DR3 (`P1 / changes_required / runtime behavior`): confirmed. Ordinary roots
  lacked a staged M1-to-M3 contract. The revised section names
  `selected_pipeline_pending` for M1 and withholds semantic writeback
  until M2/M3.
- DR4 (`P2 / changes_required / security`): confirmed. “Network denied” was
  too broad. The revised confinement rule prohibits network-capable dependency
  construction and proves it with subprocess socket/DNS/HTTP traps rather than
  claiming a process sandbox.
- DR5 (`P2 / changes_required / verification`): confirmed. Accepted language,
  roots, attacks, and traceability regeneration were underspecified. The
  manifest/corpus, root matrix, and pre-resumption regeneration gate are now
  normative.
- DR6 (`P1 / changes_required / lifecycle`): confirmed in design remediation
  round 2. The outcome vocabulary was open and stage legality was implicit.
  Section 3.23.0 now owns the discriminated extra-forbid
  `BootstrapProfileOutcome`, total coarse-envelope projection, exact M1/M2/M3
  transition table, and M1 persisted-kind exclusion list.
- DR7 (`P2 / changes_required / configuration/security`): confirmed. The first
  manifest had arbitrary digest strings and a bootstrap remote selector. The
  revised manifest pins schema/profile literals, CTV preimage/digest,
  package-root/component fingerprints, corpus verification ordering, and
  `remote_selector: Literal[None]`; future remote is explicitly outside this
  contract.
- DR8 (`P2 / changes_required / verification`): confirmed. Construction and
  confinement claims now name root callables, construction spies, subprocess
  transport traps, and executable consistency-audit inputs/failure rules.
- DR9 (`P2 / changes_required / contract closure`): confirmed in design
  remediation round 3. The M1 outcome set, resource-versus-semantic lifecycle
  projection, coordinate spelling, and artifact schemas were not fully closed.
  The revised design makes the five M1 outcomes authoritative, introduces the
  typed coordinate, and defines ordered fingerprint/corpus CTV authorities and
  suffix/add/remove/reorder/duplicate mutation proof.
- DR10 (`P1 / changes_required / lifecycle`): confirmed in design remediation
  round 4. M1 was incorrectly mapped to M2 `LocalAdmissionOutcome` resource
  decisions. The canonical design now has a separate governed-source admission
  fact and prohibits fence, reservation, lease, writer, allocation, and
  resource-profile state in M1.
- DR11 (`P2 / changes_required / security`): confirmed. Supplied artifact
  digests could bootstrap themselves and grammar/corpus binding was ambiguous.
  The immutable trust anchor now verifies the exact three-artifact graph before
  any component construction.
- DR12 (`P2 / changes_required / verification`): confirmed. Corpus and live
  unsupported behavior did not cover missing/untrusted/mismatched/non-English
  declarations or unlisted inputs. The closed corpus and live normalized-digest
  contract now state those cases and exact-match-only corpus IDs.
- DR13 (`P2 / changes_required / contract closure`): confirmed in design
  remediation round 5. Corpus entries incorrectly encoded stage outcomes and
  the bootstrap anchor lacked independent release-chain authority. The design
  now uses grammar dispositions with a closed tuple matrix and verifies the
  anchor through the active signed traceability release and lifecycle root.
- DR14 (`Not applicable / changes_required / external decision`): confirmed in
  design remediation round 6. Package-provisioned trust-root wording violated
  the independent root boundary. Runtime now accepts authority only from the
  externally provisioned host/OS trust store or host-executable capability;
  package bytes are cache/hint only and must equal that external root.

## Review Log

| Round | Reviewers | Scope | Findings | Coordinator disposition | Evidence | Product impact/remediation eligibility | Resulting action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Coordinator design review | Topology/default compatibility | DR1-DR5 | confirmed | Canonical-section and component inventory audit | compatibility/architecture/runtime/security/verification; changes required | Resolve profile topology, staging, confinement, and compatibility boundary |
| 2 | Coordinator design review | Outcome, manifest, confinement, verification closure | DR6-DR8 | confirmed | Outcome algebra and root/attack matrix audit | lifecycle/configuration/verification; changes required | Close outcome, manifest, and consistency-gate contracts |
| 3 | Coordinator design review | Coordinate, artifacts, outcome/stage closure | DR9 | confirmed | Coordinate/CTV/artifact audit | contract closure; changes required | Add typed coordinate and deterministic artifact binding |
| 4 | Coordinator design review | M1 boundary, anchor, corpus, WorkPlan completeness | DR10-DR12 | confirmed | M1 persisted-kind and corpus/anchor audit | lifecycle/security/verification; changes required | Separate M1 admission and add trust/corpus closure |
| 5 | Coordinator design review | Grammar disposition and independent anchor root | DR13 | confirmed | Cross-field matrix and traceability-release authority audit | contract closure/security; changes required | Final review, then regenerate signed release/anchor/artifact evidence |
| 6 | Spec auditor and coordinator design review | External trust-source boundary | DR14 | confirmed | Trust-root source and SIA-ED-TRACEABILITY audit | external decision; changes required | Require authenticated installer/host provisioning and reject package-only/mismatched/missing root |
| final | Spec, correctness, and test reviewers; coordinator | Final whole-design closure at `aae9faa1` | No remaining design defect; prior spec-evidence item | accepted; evidence item resolved | Final reviewer records bound to exact digest | no remediation eligible or required | Close D3/design WorkPlan; hand off controlled regeneration as linked follow-up |

## Blockers And Limits

The bounded design-review budget is six remediation rounds and all six are
consumed. Final design approval is recorded. Implementation remains gated by
the required controlled traceability and artifact regeneration/review evidence.
The current environment has no authenticated installer/host trust-store
provisioning evidence, signed release/anchor artifacts, or implementation gate
execution resources; this document does not claim those artifacts or their
execution evidence already exist. Resume implementation only when controlled
regeneration/review evidence binds the exact approved revision.

## Remediation Evidence

- Architecture revision SHA-256 after design remediation round 6:
  `aae9faa1d7fce59c658308114286a33250245b764b2cef3dde51ad3a47f2f785`.
- `git diff --check` passes for the design-only revision.
- No production or test artifact was edited in this design remediation round.
