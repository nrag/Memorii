# Design Review: Source-Grounded Semantic Ingestion Architecture

## Review Metadata

- Review ID: `semantic-ingestion-round-10`
- Review mode: `full`
- Review outcome: `Changes required`
- Design path: `docs/design/semantic_ingestion_architecture.md`
- Design baseline: SHA-256
  `45b738d27280ec3fd730c65e7cd5c1078891f9536252697aa8d3a6bf7b8ad78d`
- Implementation baseline: `f76850fc45f09d21a40b5a7302d173ce642ec9d6`
- Review date: 2026-07-26
- Reviewers: independent spec-audit lane (`Avicenna`), correctness lane
  (`Mendel`), dedicated `test_reviewer` (`Curie`), coordinator validation
- Scope: complete semantic-ingestion design; retrieval redesign, agent
  integration, production implementation, and unrelated cleanup remain excluded

The dedicated `spec_auditor` and `correctness_reviewer` role launches failed
before repository access because their fixed model was unavailable for this
account. Fresh high-reasoning agents executed those exact read-only mandates.
The dedicated `test_reviewer` ran normally. All three reviewed the complete
frozen design without consulting prior reviewer outputs.

## Executive Assessment

The design is not approved. Two high and two medium findings are validated.
The findings are one coherent acceptance-boundary defect family: source-visible
introductions and terminal zero-mutation outcomes lack a complete canonical
persistence and observation model; logical witness fence keys lack a total
runtime mapping; and hand-authored oracle semantics lack content-bound
independent review evidence.

These findings remain inside semantic-ingestion architecture. They do not
require query/retrieval redesign, agent integration, compatibility APIs, or
production implementation changes in this operation.

## Confirmed Findings

### DREV-055: Introduction records have no canonical persistence and replay owner

- Severity: High / P1
- Requirements: SIA-R03, SIA-R04, SIA-R10, SIA-R17, and SIA-R21
- Evidence: `GraphRecordKind` and `CanonicalGraphRecordPayload` omit source and
  operation introductions, while the expected and observed schemas require
  them and the closed-world comparator counts them. `GraphRevisionDelta` is
  described as the authoritative cohort source, but it contains only graph
  record mutations. The observation prose says operation introductions are
  retained from provenance without assigning an atomic store, event, replay,
  or corruption-failure contract.
- Root cause: source-visible alignment artifacts were added to acceptance after
  the canonical persistence and replay algebra had been closed.
- Impact: an implementation must invent a side channel or reconstruct records
  on read, so direct structural observation, crash atomicity, and replay cannot
  all be satisfied.
- Required correction: assign both introduction records to one canonical,
  content-addressed ingestion-observation ledger persisted atomically with the
  source/group outcome that creates them. Define schemas, mutations, deltas,
  replay, cohort membership, observation, corruption behavior, and exact
  relationship to graph revisions. They remain production audit records, not
  acceptance-only or graph-semantic records.
- Completion evidence: static ownership audit plus genesis/checkpoint replay,
  lost-acknowledgement, omission, corruption, and exact observation tests prove
  introductions are reproduced and never reconstructed by the API.

### DREV-056: Terminal zero-mutation outcomes cannot be observed or compared

- Severity: High / P1
- Requirements: SIA-R17, SIA-R21, and SIA-R22
- Evidence: `evidence_only`, `rejected`, and `unresolved` are valid durable
  terminal group/source outcomes with no graph delta. Cohort resolution,
  however, requires every seed operation to appear in exactly one committed
  `GraphRevisionDelta`, while expected operation introductions and exact
  operation counts include every source-visible operation. A partially
  committed source therefore cannot satisfy both contracts.
- Root cause: the observation contract equates semantic terminality with graph
  mutation even though the result algebra intentionally separates them.
- Impact: correct abstention/rejection is either unobservable or falsely fails
  acceptance, and mixed committed/non-committing sources have no deterministic
  oracle meaning.
- Required correction: resolve cohorts from canonical source/group outcome
  deltas as well as graph deltas. Define a closed zero-mutation observation
  shape that includes the immutable operation introduction and terminal result
  but no graph mutations. Committed outcomes additionally link exactly one
  graph delta; non-committing outcomes forbid one.
- Completion evidence: fixtures covering all three terminal non-committing
  dispositions and a mixed partially committed source return complete,
  authorized cohorts with exact zero-effect comparison and stable replay.

### DREV-057: Logical witness fence keys have no total runtime alignment

- Severity: Medium / P2
- Requirements: SIA-R04, SIA-R13, and SIA-R17
- Evidence: `ExpectedTimeWitnessRequirement.operation_fence_key` is authored
  before ingestion, while post-ingest matching refers to a mapped production
  `operation_fence_id`; no schema or algorithm defines that mapping or validates
  shared versus distinct fences.
- Root cause: operation alignment is defined, but fence alignment was left as
  prose after witness contracts were introduced.
- Impact: replayed deliveries, composite-hook children, and multi-group sources
  can be matched differently by different implementations.
- Required correction: make the logical fence key a fixture-side equivalence
  class derived from operation keys. Map it only through canonically observed
  operation introductions and their persisted production fence IDs; define
  exact same/different class validation and forbid direct expected-to-production
  ID injection.
- Completion evidence: same-fence, different-fence, replay, composite-child,
  split-commit, zero-match, and ambiguous-match tests deterministically agree.

### DREV-058: Hand-authored expected semantics lack independent review evidence

- Severity: Medium / P2
- Requirements: SIA-R03 and SIA-R17
- Evidence: hand-authored expected graphs are structurally validated and kept
  outside production imports, but their semantic content can be approved by the
  same author. The risk register acknowledges that wrong expected semantics
  require independent review, yet no artifact, freshness rule, or pass binding
  implements that requirement.
- Root cause: independence is enforced at the software boundary but not at the
  semantic-authoring boundary.
- Impact: a structurally valid but semantically wrong oracle can sign a false
  pass or reject correct production behavior.
- Required correction: for hand-authored acceptance fixtures only, require a
  content-bound, acceptance-only semantic-review attestation from two distinct
  qualified reviewers with adjudication. Bind source, fixture, operation/view
  coverage, reviewer identities, decision, and digests into the pass artifact.
  Simulator latent-state fixtures retain their generator/release evidence and
  do not require this human attestation.
- Completion evidence: missing, stale, same-reviewer, incomplete-view,
  unadjudicated, cross-fixture, and digest-substitution attestations fail before
  ingest; production packages cannot import the contract.

## Rejected And Consolidated Reviewer Proposals

- The two introduction-persistence reports were consolidated as DREV-055.
- The partial-commit conflict and inability to observe non-committing terminal
  outcomes were consolidated as DREV-056.
- Absence of the future implementation or its tests was not treated as a design
  defect where the design already specifies measurable evidence.
- The correction will not add introductions to `GraphRecordKind`: they are
  canonical ingestion-observation records, not semantic graph facts. They must,
  however, share the relevant atomic transaction and replay authority.

## Approval Decision

**Changes required.** DREV-055 through DREV-058 must be resolved and the entire
revised design must pass a fresh independent review before approval.
