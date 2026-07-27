# Design Review: Source-Grounded Semantic Ingestion Architecture

## Review Metadata

- Review ID: `semantic-ingestion-round-01`
- Review mode: `full`
- Review outcome: `Changes required`
- Design path: `docs/design/semantic_ingestion_architecture.md`
- Design baseline: SHA-256 `a0a9252d226a698eaca4273a5292aa4f04be42bb66c674a77046108fa2ef4e30`
- Implementation baseline: `f76850fc45f09d21a40b5a7302d173ce642ec9d6`
- Review date: 2026-07-26
- Reviewers: independent spec-audit lane (`Ohm`), correctness lane
  (`Galileo`), dedicated `test_reviewer` (`Hume`), coordinator validation
- Included scope: complete semantic-ingestion architecture from immutable source
  retention through proposal, source analysis, reconciliation, compilation,
  persistence, replay, migration, operations, and acceptance
- Excluded scope: query/retrieval redesign, agent integration, production
  implementation, paid live execution

The dedicated `spec_auditor` and `correctness_reviewer` tool roles could not
start because their fixed `gpt-5.6` model is unavailable for this account.
Fresh `gpt-5.4` agents executed the exact role mandates independently. The
dedicated `test_reviewer` role ran normally. No reviewer received another
reviewer's findings before finishing.

## Executive Assessment

The design has a sound central direction: raw source remains authoritative, the
LLM proposes rather than commits, independent source analysis constrains
meaning, deterministic reconciliation fails closed, and graph persistence is
validated through a structural boundary rather than retrieval. Its treatment of
type evidence, identity lineage, bitemporal projection, trust migration,
transaction planning, and hidden-oracle isolation is unusually rigorous.

The baseline is not implementation-ready. One blocking schema contradiction and
eleven high or medium findings remain. The most serious gaps are missing
proposal/event disposition identity, incomplete requirement traceability,
prompt-registry bypass risk, contradictory parser topology, conflict with the
local-first requirement, absent canonical memory-event integration, no
mixed-version writer fence, incomplete dual-parser scope/temporal consensus, and
security/acceptance contracts whose prose claims exceed their typed data.

## Governing Sources

Precedence follows `AGENTS.md`:

1. `docs/design/memorii_spec.md`
2. `docs/design/memorii_storage_details.md`
3. `docs/design/event_model.md`
4. `docs/IMPLEMENTATION_RULES.md`
5. `docs/design/semantic_ingestion_architecture.md`
6. `docs/design/memory_evolution_runtime.md`
7. `docs/design/prompt_contracts.md`
8. `docs/plans/engineering_hardening_closure_matrix.md`
9. `AGENTS.md`, `.agent/PLANS.md`, and `$review-design` for process and
   completion requirements

Repository reality was checked in current memory-evolution production modules,
prompt contracts, runtime benchmark/oracle code, and unit/integration tests. The
absence of a future design contract in current code was not treated as a design
defect by itself.

## Independently Reconstructed Requirements

| ID | Reconstructed requirement | Source | Design coverage | Acceptance criteria | Finding |
| -- | ------------------------- | ------ | --------------- | ------------------- | ------- |
| SIA-R01 | Retain immutable verbatim source and provenance before derivation | storage details; Memorii spec | covered | Every failure preserves one byte-identical source record and provenance | None |
| SIA-R02 | Model output remains untrusted until typed semantic and provenance validation | Memorii spec; implementation rules; C2 | partially covered | No model field alone can authorize committed graph truth | DREV-003 |
| SIA-R03 | Every material behavior has a stable requirement, source, measurable acceptance, and verification path | `.agent/PLANS.md`; `$review-design` | missing | Closed requirement ledger has no uncovered row | DREV-001 |
| SIA-R04 | Proposal, source-analysis, and reconciliation contracts compose without invented identifiers or statuses | implementation rules | contradictory | Every downstream field is produced by one named upstream contract | DREV-002, DREV-004 |
| SIA-R05 | Semantic scope and role decisions require the declared independent evidence lanes | fail-closed invariant; CFP-03/05 | partial | Parser disagreement or unsupported scope yields unresolved with zero graph effect | DREV-008 |
| SIA-R06 | Textual valid time is independently detected, attached, and authenticated | CFP-13; ING-P1-20 | partial | Omitted/misattached temporal evidence cannot be promoted | DREV-009, DREV-015 |
| SIA-R07 | Checked-in prompt registration, schema, redaction, and visibility policy form one provider-call authority | prompt contracts | partial | Registration substitution blocks transport before network egress | DREV-003 |
| SIA-R08 | Core behavior remains available without mandatory external services | storage details local-first requirement | contradictory | A certified local capability can ingest without cloud access | DREV-006 |
| SIA-R09 | Remote egress requires current, source-bound, deny-by-default authorization | storage details; security boundary; ING-P1-19 | partial | Revoked or stale policy snapshots cause zero transport calls | DREV-010 |
| SIA-R10 | Memory mutations participate in canonical event-sourced replay | Memorii spec; event model | missing | Graph state reconstructs deterministically from canonical memory events | DREV-007 |
| SIA-R11 | Exactly one certified writer authority exists across mixed-version packaging modes | Memorii spec packaging and run independence | partial | Stale writers fail store admission after cutover | DREV-008 |
| SIA-R12 | Persisted correction, retraction, identity, and temporal records form closed discriminated algebras | implementation rules; C1 | partial | Impossible timestamp/basis combinations fail schema validation | DREV-015 |
| SIA-R13 | Acceptance signatures and releases are lifecycle- and anti-rollback-bound | ING-P2-18 | partial | Revoked, compromised, superseded, or stale authority cannot validate evidence | DREV-011 |
| SIA-R14 | Capability certification gates every critical learned and deterministic lane with valid statistics | ING-P2-04/08/12 | partial | Routing, consensus, event, temporal, safety, utility, and abstention gates are mandatory | DREV-012 |
| SIA-R15 | Runtime monitoring policy is executable and deterministically demotes unsafe or stale capabilities | ING-P2-04 | partial | Same observations and policy always yield the same activation decision | DREV-013 |
| SIA-R16 | Initial dependency topology, rollout, and certification set are unambiguous | design completion contract | contradictory | One declared initial analyzer set appears consistently throughout the design | DREV-005 |
| SIA-R17 | Independent acceptance compares a pre-ingest expected graph with direct structural observations | CFP-08/09; ING-P1-07 | covered | One-field and extra/missing-record mutations fail without production semantic helpers | None |
| SIA-R18 | Historical truth, trust decay, and entity lineage remain immutable and replayable | CFP-13/14/15 | covered except temporal input gap | Required historical/current/lineage views compare exactly | DREV-009 |

## Confirmed Findings

### DREV-001: Material requirements lack a stable traceability ledger

- Severity: High
- Confidence: high
- Category: requirements completeness
- Design location: Sections 1.5, 5.10, and 5.13
- Governing source: `.agent/PLANS.md` design completion contract
- Expected behavior: Every material requirement has a stable ID, source,
  priority, measurable acceptance criterion, and verification strategy.
- Design behavior: Twenty-nine numbered outcomes, CFP rows, ING rows, and final
  acceptance bullets are not connected by one authoritative ledger.
- Evidence: Section 1.5 uses unstable ordinal numbering; CFP and ING IDs
  represent failure patterns and prior findings rather than the complete
  requirement set.
- Impact: Implementers and reviewers cannot prove that all outcomes are owned,
  accepted, and verified without reconstructing hidden mappings.
- Recommended resolution: Add one canonical `SIA-Rxx` requirements ledger and
  map CFP/ING rows and final acceptance to it.
- Verification needed: A static ledger audit with no missing source, owner,
  acceptance, or verification cell.

### DREV-002: Proposal identity and event-level dispositions are not produced

- Severity: Blocking
- Confidence: high
- Category: schema completeness
- Design location: `SemanticProposal`, `ParserConsensusAssessment`,
  `SemanticScopeAssessment`, and predicate-event coverage contracts
- Governing source: implementation rules and fail-closed architecture invariant
- Expected behavior: Every downstream proposal/event reference resolves to a
  stable upstream identifier and typed disposition.
- Design behavior: `SemanticProposal` has no `proposal_id`; downstream
  assessments require one. Segment/run-level abstention exists, but coverage
  requires explicit abstention for one certified event.
- Evidence: Design lines 2663-2691, 3177-3254, and 3286-3292.
- Impact: An implementation must invent proposal identity and omission semantics
  or cannot construct Step 5.
- Recommended resolution: Define stable proposal/operation identity and a
  source-derived `PredicateEventDisposition` union that records covered or
  unresolved outcomes without letting the proposer invent detector event IDs.
- Verification needed: Mixed-source tests with accepted operations and one
  independently detected unsupported event.

### DREV-003: The proposer is not bound to the canonical prompt registration

- Severity: High
- Confidence: high
- Category: security and ownership
- Design location: `SemanticProposalRequest` and Step 3 validation
- Governing source: `docs/design/prompt_contracts.md`
- Expected behavior: Registered prompt text, schema, visibility/redaction
  policy, owner, and digest are one immutable provider-call authority.
- Design behavior: The request carries detached prompt and output-schema
  fingerprints and introduces a predicate prompt contract without binding the
  registered prompt contract.
- Evidence: Design lines 2454-2468 and 2799; prompt contracts require
  `RegisteredPromptContract` and atomic registration.
- Impact: A conforming implementation could create a second prompt authority or
  bypass no-leakage policy.
- Recommended resolution: Bind the registered prompt identity and registration
  digest to request, transport, attempt, trace, and capability contracts.
- Verification needed: Prompt/YAML/schema/visibility/owner/digest substitutions
  must fail before transport.

### DREV-004: Reconciliation drops the dual-analysis bundle it claims to use

- Severity: Medium
- Confidence: high
- Category: internal consistency
- Design location: `EvidenceNormalizationRequest`, `ReconciliationRequest`,
  and reconciliation algorithm
- Governing source: implementation-readiness and fail-closed invariants
- Expected behavior: Reconciliation receives exactly the analyses and consensus
  artifacts named by its algorithm.
- Design behavior: Normalization receives `LinguisticAnalysisBundle`, but
  reconciliation receives singular `analysis: LinguisticAnalysis` while
  validating “both normalized analyses.”
- Evidence: Design lines 3101, 3530-3546, and 3952-3959.
- Impact: Implementers must invent whether one analysis, both analyses, or only
  consensus is authoritative.
- Recommended resolution: Carry the immutable bundle and explicit consensus
  assessment in `ReconciliationRequest`; define and type the coverage audit it
  consumes.
- Verification needed: Replay and mutation tests for partial, disagreeing, and
  agreeing analyzer bundles.

### DREV-005: Initial Stanza/spaCy topology is contradictory

- Severity: Medium
- Confidence: high
- Category: dependency and rollout consistency
- Design location: Sections 2.1, 3.4, 3.14, 4.4, and Gate C
- Governing source: design implementation-readiness contract
- Expected behavior: One initial analyzer topology governs packages, runtime,
  certification, and rollout.
- Design behavior: The main path and module map require Stanza plus spaCy, while
  Section 3.4 says spaCy is future-only.
- Evidence: Design lines 251-254, 517-519, 823, and 2823-2827.
- Impact: Build and certification scope must be invented.
- Recommended resolution: Make both analyzers mandatory for the initial active
  capability, or consistently redesign the consensus requirement.
- Verification needed: One dependency and certification matrix throughout.

### DREV-006: Mandatory remote proposal conflicts with local-first operation

- Severity: High
- Confidence: high
- Category: compatibility
- Design location: Sections 2.1, 2.3, 3.2, 4.3
- Governing source: `docs/design/memorii_storage_details.md` local-first
  requirement
- Expected behavior: Core semantic ingestion operates without external services.
- Design behavior: Active open-vocabulary promotion requires OpenAI; denied or
  unavailable egress becomes evidence-only.
- Evidence: Design lines 247-249 and 359-363; storage details require all core
  functionality without external services and cloud backends to be optional.
- Impact: Air-gapped or policy-denied deployments lose active semantic ingestion.
- Recommended resolution: Define a provider-neutral proposer protocol and at
  least one certifiable local proposer deployment. Capabilities bind one exact
  proposer; no fallback occurs within an ingestion attempt.
- Verification needed: Local-only end-to-end promotion and explicit remote-deny
  zero-call tests.

### DREV-007: Semantic mutations bypass the canonical memory event model

- Severity: High
- Confidence: high
- Category: replay and recovery
- Design location: Step 8 persistence and replay
- Governing source: `docs/design/event_model.md` and Memorii spec Section 18
- Expected behavior: Committed memory mutations emit canonical, deduplicated,
  replayable `graph_type="memory"` events.
- Design behavior: Step 8 defines graph deltas, traces, summaries, and an
  append-only transaction log but no canonical event envelope or event-to-state
  reconstruction contract.
- Evidence: Event model lines 25-90 and 138-143 include memory graphs; the design
  contains no `EventRecord`, event type, or dedupe-key binding.
- Impact: Memory evolution would create a second replay authority incompatible
  with framework-neutral event processing.
- Recommended resolution: Define canonical semantic-ingestion memory events,
  their payload union, idempotency identity, atomic commit relation, and replay
  ordering.
- Verification needed: Full and mid-stream replay, duplicate delivery, unknown
  event, partial commit, and event/delta substitution tests.

### DREV-008: Mixed-version deployments can retain multiple commit authorities

- Severity: High
- Confidence: high
- Category: migration and compatibility
- Design location: Sections 3.13 and 5.9
- Governing source: Memorii packaging modes and run independence
- Expected behavior: A stale sidecar, embedded library, or event consumer cannot
  commit after capability cutover.
- Design behavior: The design states “exactly one path” but supplies no
  store-enforced writer-admission epoch or capability fence.
- Evidence: Design lines 798-806 and rollout gates; Memorii supports embedded,
  sidecar, and event-consumer packaging.
- Impact: Legacy and verified writers can concurrently mutate one store,
  invalidating certification and migration safety.
- Recommended resolution: Add a store-owned semantic writer-admission record and
  require every group CAS to match its capability, mode, schema, and epoch.
- Verification needed: Mixed-version shared-store tests before, during, and
  after cutover and rollback.

### DREV-009: Scope and temporal attachment are not independently complete

- Severity: High
- Confidence: high
- Category: semantic correctness
- Design location: `SemanticScopeAssessment`, temporal resolution, and coverage
- Governing source: CFP-05, CFP-13, ING-P1-20
- Expected behavior: Both analyzers contribute explicit scope/attachment
  interpretations; source-derived temporal events cannot disappear because the
  proposer omitted a qualifier.
- Design behavior: One `SemanticScopeAssessment` has no per-analyzer
  interpretations or consensus identity. `certified_text_interval` is admitted
  only when a resolver span equals a proposer temporal qualifier. The resolver
  accepts `authenticated_document_time`, but `SourceSemanticContext` does not
  provide it.
- Evidence: Design lines 3244-3284, 2852/2938, and 928-948.
- Impact: Negation, attribution, or historical time can be promoted incorrectly,
  and `historical_fact_lost` is not closed for proposer omission/misattachment.
- Recommended resolution: Define source-only scope and temporal-attachment
  assessments per analyzer, an exact consensus contract, a temporal-event
  coverage/disposition obligation independent of proposals, and a typed
  authenticated document-time source.
- Verification needed: Omitted/misattached date, parser scope disagreement,
  relative time, attribution, negation, and historical replay tests.

### DREV-010: Egress authorization has no current-policy anti-rollback proof

- Severity: High
- Confidence: high
- Category: security
- Design location: `ProviderEgressPolicySnapshot` and transport recomputation
- Governing source: current-source-bound authorization acceptance criterion
- Expected behavior: A revoked or superseded allow policy cannot authorize a
  later provider call.
- Design behavior: Transport recomputes against the retained snapshot but never
  proves it equals the current active policy at call time.
- Evidence: Design lines 906-926, 1388-1404, and 8325-8327.
- Impact: Previously retained permissive policy can outlive revocation.
- Recommended resolution: Add a store-owned active egress-policy revision/epoch,
  expiry and supersession semantics, and a pre-transport compare operation.
- Verification needed: Rotation, revocation, expiry, stale snapshot, rollback,
  and concurrent policy-change zero-call tests.

### DREV-011: Acceptance signing lifecycle is inconsistent and replayable

- Severity: Medium
- Confidence: high
- Category: trust evidence
- Design location: time witnesses, signed registry releases, and
  `IngestionGraphPassed`
- Governing source: ING-P2-18 and final acceptance requirements
- Expected behavior: Every acceptance signature identifies a lifecycle-checked,
  purpose-authorized key and current release.
- Design behavior: Registry releases identify keys, but time witnesses and the
  final artifact carry free `signing_identity`; supersession lacks a monotonic
  active-release rule.
- Evidence: Design lines 6169-6196, 6624-6636, and 7357-7386.
- Impact: A stale or compromised identity/release can produce apparently valid
  acceptance evidence.
- Recommended resolution: Use one acceptance signing-authority snapshot and
  key-ID contract for witnesses and artifacts, plus active-release anti-rollback.
- Verification needed: Rotation, retirement, revocation, compromise-time,
  supersession, purpose, and cross-artifact replay tests.

### DREV-012: Statistical gates omit critical source-analysis metrics

- Severity: Medium
- Confidence: high
- Category: statistical acceptance
- Design location: Sections 5.2 and 5.6
- Governing source: ING-P2-08/12 and design component acceptance claims
- Expected behavior: Every behavior-affecting learned/deterministic lane has a
  mandatory predeclared gate.
- Design behavior: The test-layer table names routing error, parser disagreement,
  event recall, and temporal accuracy, but the normative metric list does not.
- Evidence: Design lines 6000 and 7487-7500.
- Impact: A capability may activate while a critical analyzer is statistically
  unsafe.
- Recommended resolution: Add mandatory metric IDs and estimands for routing,
  analyzer consensus, event coverage, temporal resolution/attachment, and
  end-to-end promotion.
- Verification needed: Manifest completeness and independent recomputation tests.

### DREV-013: Monitoring decisions are not executable from the typed policy

- Severity: Medium
- Confidence: high
- Category: operations
- Design location: `CapabilityMonitoringPolicy`
- Governing source: ING-P2-04
- Expected behavior: One typed policy deterministically defines monitored
  metrics, thresholds, direction, alpha/error budget, estimand, and breach action.
- Design behavior: The contract includes freshness windows and an opaque
  sequential-test fingerprint but omits the actual decision rules described in
  prose.
- Evidence: Design lines 7588-7600 and 7626-7629.
- Impact: Implementations can demote capabilities differently from identical
  evidence.
- Recommended resolution: Embed a closed tuple of monitoring metric gates and
  explicit atomic state-transition action.
- Verification needed: Independent decision recomputation, boundary, staleness,
  race, and recovery tests.

### DREV-014: Referenced coverage and trace contracts are undefined

- Severity: Medium
- Confidence: high
- Category: schema completeness
- Design location: `ReconciliationRequest` and `SourceTracePersistenceRequest`
- Governing source: implementation-readiness contract
- Expected behavior: Every public or persisted type referenced by normative
  schemas is defined once with ownership and invariants.
- Design behavior: `ProposalCoverageAudit` and multiple `*Trace` DTOs are used
  but never defined.
- Evidence: Design lines 3538 and 5613-5627; complete-document symbol search.
- Impact: Implementers must invent persisted evidence shape and compatibility.
- Recommended resolution: Define the canonical contracts or replace them with
  already-defined immutable stage results.
- Verification needed: Definition/reference audit and round-trip compatibility
  tests for every persisted union.

### DREV-015: Temporal basis contracts admit impossible states

- Severity: Medium
- Confidence: high
- Category: type and lifecycle safety
- Design location: accepted correction, retraction, identity, expected, and
  observed temporal records
- Governing source: implementation rules and C1
- Expected behavior: Timestamp basis and value form a closed discriminated union.
- Design behavior: Nullable timestamp and independent basis permit contradictory
  combinations; expected/observed contracts use open `str` basis fields.
- Evidence: Design lines 3753-3771, 3843-3851, 6510, and 7024.
- Impact: Reconciliation, persistence, and independent comparison can interpret
  the same record differently.
- Recommended resolution: Define one shared discriminated temporal-coordinate
  union and reuse it in accepted, durable, expected, and observed records.
- Verification needed: Exhaustive variant round trips and malformed-combination
  rejection.

## Requirements Coverage

The reconstructed ledger above is the round-01 requirements coverage matrix.
Status summary:

- Covered: SIA-R01, SIA-R17
- Covered except a linked finding: SIA-R18
- Partial: SIA-R02, R05-R07, R09, R11-R16
- Missing: SIA-R03, R10
- Contradictory: SIA-R04, R08, R16

## Architecture And Feasibility Assessment

The architecture fits Memorii's separation of raw observations, derived
semantics, candidate state, committed graph state, and benchmark oracle. The
selected analyzers and language-owned policy boundaries are feasible, but the
initial dependency set must be made consistent. The principal sequencing risks
are event-model integration, store-enforced writer admission, provider-neutral
local/remote proposal composition, and introducing the new typed contracts
without allowing the legacy heuristic path to remain a second authority.

## Failure, Security, And Operational Assessment

Fail-closed semantic handling is strong in intent. Provider egress and acceptance
signing need anti-rollback authority, not only content binding. Canonical event
emission and mixed-version writer fencing are required for crash recovery,
framework-neutral replay, and migration. Monitoring needs executable decision
data rather than prose plus fingerprints.

## Verification Assessment

The design contains unusually broad test ideas, but traceability is not closed.
The normative statistical and monitoring contracts omit several metrics and
decision parameters named elsewhere. Current legacy tests do not prove the
future design, but their absence is an implementation gap rather than a defect
in an otherwise complete design requirement.

## Risk Register

| Risk | Trigger | Impact | Mitigation in design | Residual risk | Status |
| ---- | ------- | ------ | -------------------- | ------------- | ------ |
| Common-mode parser error | both analyzers misparse one construction | false promotion | consensus, held-out labels, abstention | scope consensus contract is incomplete | open |
| Proposal omission | proposer omits an event or date | lost fact/history | source-only event detector | temporal-event disposition missing | open |
| Egress rollback | policy changes after source retention | unauthorized disclosure | retained snapshot and recomputation | no current-policy proof | open |
| Mixed writers | old and new packages share a store | uncertified commits | staged cutover prose | no store fence | open |
| Event divergence | graph delta and event log differ | non-deterministic replay | append-only transaction log | canonical event integration missing | open |
| Acceptance replay | stale signing identity/release | false certification | signatures and trust policy | authority binding inconsistent | open |
| Availability collapse | any required lane unavailable | evidence-only ingestion | explicit abstention/degradation | needs capacity and SLO evidence | accepted residual |
| Operational cost | dual parsers, local temporal/NLI, rich traces | latency/storage growth | parallelism, caching, bounded lanes | requires capacity validation | accepted residual |

## Rejected Or Consolidated Findings

- Test reviewer DREV-001 through DREV-007 were based primarily on the current
  implementation not yet containing future target modules or tests. They are
  rejected as design findings: a design may specify implementation work that
  does not yet exist. The valid traceability concern is consolidated into
  DREV-001; valid oracle, egress, transaction, statistical, and observability
  requirements already exist in the design and must be implemented later.
- Test reviewer concern that the current oracle is production-coupled is an
  implementation gap already explicitly replaced by Sections 5.4.1-5.4.4. It
  does not show a defect in that replacement design.
- “The design is too complex” is unsupported. The identity, temporal, trust,
  migration, and transaction complexity is proportional to the documented
  failure modes.
- “Using an LLM proposer is inherently unsafe” is unsupported. Proposer-only
  authority with deterministic acceptance is coherent; the confirmed issue is
  local-first availability and prompt/egress binding.
- Retrieval deficiencies are outside this ingestion-only review.

## Required Changes Before Approval

Resolve DREV-001 through DREV-015. No item may be closed solely by adding prose;
the corrected contract, ownership, acceptance criterion, and verification
strategy must agree throughout the complete document.

## Non-Blocking Follow-Ups

No low-severity follow-up is required before the next full review.

## Final Outcome

Changes required. The round-01 baseline is directionally strong but cannot be
safely implemented without invented semantics and does not yet satisfy all
higher-precedence platform requirements.

## Review Limitations

- This was a static design review; no paid provider call, live workflow, or
  target implementation test was run.
- The two dedicated reviewer role implementations were unavailable due account
  model support; fresh independent agents executed their mandates instead.
- Current code was inspected for ownership and feasibility, not used to reject
  explicitly planned future implementation.
