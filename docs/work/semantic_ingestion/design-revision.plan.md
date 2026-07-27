# Semantic Ingestion Architecture Design Revision

- Work ID: semantic-ingestion-design-revision
- Work type: design
- Status: blocked
- Coordinator: Codex main thread
- Created: 2026-07-26
- Last updated: 2026-07-26
- Parent WorkPlan: `docs/work/semantic_ingestion/design-review.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/design-review.plan.md`
- Canonical inputs: validated findings in `docs/reviews/semantic_ingestion/review-round-XX.md`
- Expected outputs: revised `docs/design/semantic_ingestion_architecture.md` baselines

## Objective

Resolve every validated blocking, high, and medium semantic-ingestion design
finding with the smallest complete correction supported by governing
requirements and repository evidence, while preserving already-correct
contracts and the ingestion-only scope.

## Completion Contract

This revision operation is complete only when:

- every validated approval-blocking finding has a documented resolution;
- every material requirement has a stable identifier, traceable source,
  measurable acceptance criteria, and verification strategy;
- schemas, prose, workflows, failure behavior, rollout, and verification agree;
- implementation requires no invented material semantics;
- a fresh whole-design review of the final immutable baseline is approved with
  no validated blocking, high, or medium finding;
- no requirement was weakened merely to obtain approval.

## Scope

Included:

- corrections required by validated review findings for the canonical semantic
  ingestion design;
- consistency updates required to propagate those corrections through contracts,
  workflow, acceptance criteria, requirement coverage, risks, and verification.

Excluded:

- production implementation and tests;
- retrieval/query redesign;
- agent integration;
- unrelated architectural cleanup;
- changes based only on reviewer preference.

Explicitly deferred:

- implementation WorkPlan creation after design approval.

## Constraints And Invariants

- This plan remains proposed until round-01 findings are validated.
- Exactly one writer edits the canonical design.
- The design-review WorkPlan remains the authority for finding dispositions.
- Revisions are limited to confirmed findings and direct consistency
  consequences.
- A new checksum is frozen after each revision before a fresh review.
- At most three revision rounds may be used.
- Unrelated dirty-worktree changes are preserved.

## Sources Of Truth

Use the precedence and repository evidence listed in
`docs/work/semantic_ingestion/design-review.plan.md`. Each active revision also
uses the immediately preceding immutable review report as an input, not as a
governing product specification.

## Current State

Verified facts:

- Round-01 review reconciliation is complete.
- Initial design baseline:
  `a0a9252d226a698eaca4273a5292aa4f04be42bb66c674a77046108fa2ef4e30`.
- `docs/reviews/semantic_ingestion/review-round-01.md` confirms DREV-001 through
  DREV-015 and requires changes.

Working interpretation:

- The design is substantial and already contains many explicit contracts;
  revisions should repair contradictions or missing guarantees without replacing
  the architecture wholesale.

## Assumptions And Open Questions

Verified facts:

- Reviewer findings must be validated by the coordinator.

Working assumptions:

- Confirmed findings can be resolved without expanding into retrieval.

Unresolved questions:

- DREV-077 has no non-invented answer in the current governing sources.
- DREV-088 has no non-invented answer while the Memorii spec assigns model
  invocation and persistence authorization to the host but this design assigns
  semantic proposal execution and validated graph commit to Memorii.

Decisions requiring external input:

- The event-model owner must choose and record one same-version replay rule for
  identical duplicates, conflicting historical events, and current-writer
  submissions before DREV-077 can close.
- The product/spec owner must choose one complete host-owned or Memorii-owned
  semantic-inference and durable-writeback authority model, then amend the
  governing spec before DREV-088 can close.

## Problem Definition

The design must be implementation-ready for safe source-grounded semantic
ingestion. A material contradiction, missing lifecycle rule, unverifiable
acceptance criterion, or undefined contract forces implementers to invent
semantics and therefore blocks approval.

## Requirements Ledger

The ledger will be populated from the independently reconstructed requirements
and validated findings in the first review report. No reviewer recommendation
becomes a requirement without coordinator validation.

| ID | Requirement | Source | Priority | Acceptance criteria | Status |
| -- | ----------- | ------ | -------- | ------------------- | ------ |
| REV-001 | Resolve every validated approval-blocking finding without weakening governing requirements | `$build-design`; round-01 review | Required | Every validated finding has a traceable correction and a fresh approved review | Blocked after bounded non-convergence |
| REV-002 | Preserve ingestion scope and already-correct Memorii invariants | `AGENTS.md`; target design | Required | No retrieval, agent-integration, or unrelated redesign changes | Complete for revision 01 |
| REV-003 | Make all material semantics implementable and verifiable | `.agent/PLANS.md` | Required | Stable requirements, measurable acceptance, and verification coverage are complete | Complete for revision 01 |
| REV-004 | Close proposal identity, event disposition, prompt registration, dual-analysis, scope, and temporal contract gaps | DREV-002/003/004/009/014/015 | Required | Upstream/downstream schemas compose and invalid combinations fail closed | Complete for revision 01 |
| REV-005 | Close local-first, egress, event-replay, and mixed-writer platform gaps | DREV-006/007/008/010 | Required | Local certified path, current-policy egress, canonical events, and writer fence are explicit | Complete for revision 01 |
| REV-006 | Close acceptance, statistical, monitoring, dependency, and traceability gaps | DREV-001/005/011/012/013 | Required | One topology and complete measurable acceptance/monitoring contracts | Complete for revision 01 |
| REV-007 | Distinguish durable source admission from rejection and indeterminate retention | DREV-037; SIA-R01 | Required | Only an accepted source starts derivation; failpoint behavior is discriminated and measurable | Complete for revision 06 |
| REV-008 | Derive reported-source attribution through exact source and canonical identity evidence | DREV-038; SIA-R04/R05 | Required | Every accepted reported fact has one independently agreed, grounded, canonical bearer | Complete for revision 06 |
| REV-009 | Separate production commit-time facts from acceptance signing authority | DREV-039; SIA-R13 | Required | Atomic production attestations feed independently signed acceptance witnesses with reciprocal import boundaries | Complete for revision 06 |
| REV-010 | Make execution and expected-graph algebras complete | DREV-040/041; SIA-R04/R17 | Required | Every workflow stage and observed operation introduction has a closed typed expected/verification path | Complete for revision 06 |
| REV-011 | Close ordinary default, event mutation, atomic storage, provider normalization, and C11 replay semantics | DREV-042 through DREV-046 | Required | Default, mapping, storage protocol, adapter normalization, and delivery recovery are total and measurable | Complete for revision 07 |
| REV-012 | Close verification gaps without production test hooks | DREV-047 and DREV-048 | Required | Valid redaction and deterministic filesystem schedules have independent evidence | Complete for revision 07 |
| REV-013 | Separate proposal authority from operation certification and complete deployment/temporal inputs | DREV-049 through DREV-052 | Required | Every runtime authority is selected at the correct stage and all dependencies/policies are explicit | Complete for revision 07 |
| REV-014 | Separate retryable progress from terminal source results and preserve lease exhaustion | DREV-053 and DREV-054 | Required | No retryable failure becomes committed and every terminal operation has one typed semantic result | Complete for revision 07 |
| REV-015 | Give introductions and zero-mutation terminal outcomes canonical atomic persistence, replay, observation, and comparison semantics | DREV-055 and DREV-056; SIA-R10/R17/R21/R22 | Required | Every source-visible operation has one replayable introduction and terminal outcome; committed outcomes link one graph delta and non-committing outcomes forbid one | Complete for revision 08 |
| REV-016 | Make witness-fence alignment total without allowing fixture IDs to control production identity | DREV-057; SIA-R04/R13/R17 | Required | Logical fence equivalence maps uniquely through observed introductions and rejects every ambiguous or inconsistent mapping | Complete for revision 08 |
| REV-017 | Bind independently reviewed hand-authored semantics into acceptance evidence | DREV-058; SIA-R03/R17 | Required | Every hand-authored acceptance fixture has current two-reviewer adjudicated evidence bound to its exact content; simulator latent fixtures use generator evidence | Complete for revision 08 |
| REV-018 | Make operation, fence, source-introduction, and entity alignment one total independent procedure | DREV-059 and DREV-060; SIA-R04/R13/R17/R21 | Required | A unique global operation/fence bijection exists before source/entity alignment; zero or multiple solutions fail | Complete for revision 09 |
| REV-019 | Separate production source-outcome integrity from fixture-authored semantic equality | DREV-061; SIA-R03/R10/R17/R21 | Required | Runtime-only coordinates pass an independent consistency assessment and fixture comparison uses only pre-ingest authorable semantics | Complete for revision 09 |
| REV-020 | Atomically publish replay authority and model pre-planning progress | DREV-062 and DREV-063; SIA-R02/R10/R18/R20/R21 | Required | No visible state references absent artifacts; pre-planning failures resume exactly without sentinel plans or repeated acknowledged learned work | Complete for revision 09 |
| REV-021 | Fence every semantic write at the shared persistence boundary | DREV-067; SIA-R11/R19/R20/R21 | Required | Stale legacy and target writes at every boundary fail after epoch change with no partial state | Complete for revision 10 |
| REV-022 | Close temporal reference provenance and evidence precedence | DREV-068 and DREV-070; SIA-R04/R06/R12/R17/R18 | Required | Every temporal mode/evidence combination has one result and every accepted basis remains replayable and observable | Complete for revision 10 |
| REV-023 | Separate stable allocation identity from renewable lease authority | DREV-069; SIA-R04/R10/R20/R21 | Required | Recovery preserves deterministic IDs and rejects stale lease owners | Complete for revision 10 |
| REV-024 | Pin legacy wire compatibility and close admission/provider-input handoffs | DREV-071 through DREV-073; SIA-R01/R03/R04/R20/R22/R23 | Required | Old wire bytes remain frozen; admission and structured provider inputs compose without inferred IDs or adapter-specific bytes | Complete for revision 10 |
| REV-025 | Separate global storage-writer authority from operation capability authority | DREV-074; SIA-R04/R11/R19/R21 | Required | Source admission is globally fenced before capability selection; later group promotion requires both global writer and selected capability authority | Complete for revision 11 |
| REV-026 | Separate retained structured envelopes from reversible semantic text | DREV-075; SIA-R01/R04/R05/R23 | Required | Only declared content fields reach semantic lanes and every projected span maps exactly to retained typed provenance | Complete for revision 11 |
| REV-027 | Make source and graph normalization contracts match their declared DAG scopes | DREV-076; SIA-R02/R04/R19/R20 | Required | Source normalization is graph-free and reusable; graph conflict reruns only graph-bound artifacts | Complete for revision 11 |
| REV-028 | Preserve authenticated source-interval evidence end to end | DREV-078; SIA-R06/R12/R17/R18 | Required | Equal intervals with different source fields, authority bases, provenance, or evidence digests remain distinguishable through replay and direct observation | Complete for revision 12 |
| REV-029 | Separate source dependency grouping from graph-sensitive transaction grouping | DREV-079; SIA-R02/R04/R19/R20 | Required | Graph revision changes cannot alter source groups, capability selection, or NLI artifacts | Complete for revision 13 |
| REV-030 | Separate immutable reservations from renewable use authority | DREV-080; SIA-R04/R20/R21 | Required | Reclaim preserves reservation bytes while rotating an independently verified use authorization | Complete for revision 13 |
| REV-031 | Preserve complete temporal evidence for every transition operation and correct mutation outcomes | DREV-081/DREV-082; SIA-R06/R12/R17/R18 | Required | Every transition remains provenance-distinct; production and oracle mutations have boundary-correct outcomes | Complete for revision 13 |
| REV-032 | Make production-surface and real-egress verification independent | DREV-083/DREV-086; SIA-R09/R21 | Required | Shipped contracts contain no test control plane and denied production composition creates no wire activity | Complete for revision 13 |
| REV-033 | Add ordered replay positions and continuity validation | DREV-084; SIA-R10 | Required | Checkpoint replay identifies every later batch exactly once across backends | Complete for revision 13 |
| REV-034 | Close statistical coverage and fixture-review independence | DREV-085/DREV-087; SIA-R14/R17 | Required | Activation has complete independent lane coverage and hidden-oracle review cannot be self-approved | Complete for revision 13 |

## Non-Goals

- Implementing the architecture.
- Making live benchmark calls.
- Solving downstream retrieval behavior.
- Reducing design rigor or deleting difficult requirements.

## Existing-System Analysis

The design revision must remain grounded in the current production composition,
memory-evolution schemas, extraction and validation path, prompt contracts,
transaction and persistence boundaries, runtime benchmark oracle, and tests.
Specific evidence will be added for each validated finding.

## Alternatives Considered

- Apply reviewer recommendations verbatim: rejected because reviewers are
  advisory and may propose broader or conflicting changes.
- Replace the architecture wholesale: rejected because it would discard
  already-correct contracts and expand scope.
- Smallest complete contract correction: selected, subject to evidence for each
  finding.

## Feasibility Evidence

Pending validated findings. Each correction must cite governing requirements and
current repository ownership or identify a bounded unresolved feasibility risk.

## Failure And Operational Analysis

Each revision must explicitly preserve or repair fail-closed behavior,
authorization, privacy, idempotency, concurrency, replay, migration, rollback,
mixed-version behavior, observability, and resource limits where implicated by
the validated finding.

## Verification Strategy

- Validate each correction against its cited requirement and repository owner.
- Search the complete design for stale terms and contradictory duplicate
  contracts after every edit.
- Rebuild requirement coverage and risk views.
- Freeze a new SHA-256 baseline.
- Run fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer`
  instances against the complete revised design.

## Milestones Or Experiments

### Milestone 1: Reconcile round-01 findings

- Purpose: freeze the authorized revision inventory.
- Bounded scope: disposition every proposed finding.
- Expected artifacts: round-01 report and populated requirements ledger.
- Verification method: direct source and repository evidence.
- Status: complete.

### Milestone 2: Perform coherent validated design revisions

- Purpose: resolve all confirmed approval blockers with one writer.
- Bounded scope: validated findings and required consistency propagation.
- Expected artifacts: revised canonical design and updated WorkPlan.
- Verification method: contract searches, traceability audit, new checksum.
- Status: complete for revisions 01 through 06.

### Milestone 3: Iterate only when fresh review finds a validated blocker

- Purpose: converge within the fixed budget.
- Bounded scope: at most three revision rounds.
- Expected artifacts: immutable review reports and final approved baseline or
  unresolved-findings report.
- Verification method: fresh whole-design reviews.
- Status: complete with bounded non-convergence.

## Progress Log

- 2026-07-26: A new three-revision cycle is authorized. Revision work remains
  proposed until the fresh round-13 full review is complete and the coordinator
  validates a closed inventory. No canonical design edits are authorized during
  that initial review.
- 2026-07-26: Round 13 validated DREV-067 through DREV-073. Revision 10 is
  active and limited to those seven findings and direct consistency updates.
- 2026-07-26: Completed revision 10 with one writer. Every governed semantic
  storage method now requires one common writer binding; cutover drains the
  retiring epoch; stable allocation namespaces are separate from renewable
  leases; admission returns a complete operation/namespace/writer handoff;
  temporal reference provenance and the mode/evidence matrix are closed through
  durable and oracle contracts; structured provider inputs use canonical
  versioned envelopes; and the complete legacy lifecycle model is pinned to an
  immutable baseline and independent fixtures. Static validation found 42
  syntactically valid Python blocks, 100 balanced Markdown fences, no stale
  superseded temporal/allocation terms, and a clean diff check. Frozen design
  SHA-256:
  `487f5e88281c443722b9172d15cadb734f4d263d0fb764a69ff9ebf9b7ca8673`.
- 2026-07-26: Round 14 approved the verification architecture and validated
  DREV-074 through DREV-076 as internal high findings. It also validated
  DREV-077 as a pre-existing conflict in the higher-precedence event model that
  requires an external owner decision. Completed revision 11 with one writer:
  one global writer namespace now precedes and composes with later operation
  capability selection; structured sources retain canonical envelope bytes but
  feed semantic lanes only through a reversible content-only projection; and
  Step 5 now has graph-free source normalization plus graph-bound normalization
  contracts matching the execution DAG. Static validation found 42 valid
  Python blocks, 100 balanced fences, no superseded contract names, and a clean
  diff check. Frozen design SHA-256:
  `9559322a6cf8beb4d35568a36712471baee7e41b557751d1d36f7a56083d1e87`.
- 2026-07-26: Round 15 validated DREV-078 and retained DREV-077 as an external
  governing-source blocker. Completed revision 12 with one writer:
  `AuthenticatedSourceIntervalEvidence` now binds interval, source field,
  authority basis, provenance digest, and evidence digest and remains
  byte-identical through source context, temporal assessment, accepted IR,
  durable replay, expected fixtures, and observed claim/action records.
  Equal-value provenance-substitution tests are explicit at every boundary.
  Static validation found 42 valid Python blocks, 100 balanced fences, no stale
  bare authenticated-source interval fields, and a clean diff check. Frozen
  design SHA-256:
  `a632772d2b7485a9b105d7e7c02dbf76881d8f1e8da4f33430f6931c86f2b029`.
- 2026-07-26: Round 16 validated DREV-079 through DREV-083 and retained
  DREV-077. No fourth revision was made because the authorized three-revision
  budget is exhausted. The exact required architectural corrections and
  external event-model decision are recorded in
  `docs/reviews/semantic_ingestion/review-round-16.md`.
- 2026-07-26: A new three-revision cycle is authorized. Revision work remains
  proposed until the fresh round-17 full review is complete and the coordinator
  freezes its validated inventory.
- 2026-07-26: Round 17 froze DREV-077 and DREV-079 through DREV-087. Revision
  13 is active for internal findings DREV-079 through DREV-087 only. One writer
  will propagate each invariant through every producer, consumer, persistence,
  replay, expected/observed, acceptance, and verification boundary before the
  next baseline is frozen.
- 2026-07-26: Completed revision 13 with one writer. Source-only dependency
  groups are graph-free and expand only later into transaction groups;
  immutable identity/action reservations use separately renewable lease-bound
  authorizations; correction, retraction, and identity transitions preserve
  complete temporal evidence through durable records, replay, and direct
  observation; oracle-only mutations fail comparison rather than claiming
  graph rollback; artifact-surface and real-wire egress checks are independent;
  event checkpoints use contiguous repository log positions; statistical
  coverage is closed by a signed capability-derived manifest; and hidden
  fixtures require blinded, domain-independent review commitments. Static
  validation found 43 syntactically valid Python blocks, 102 balanced fence
  markers, no superseded grouping names, and a clean diff check. Frozen design
  SHA-256:
  `3d7f1f045d32a8c13504fc501d8265c1c62f2ef1b5d3d76e4a061efece39d957`.
- 2026-07-26: Round 18 validated revision 13 and found no further internally
  resolvable approval blocker. Revision is stopped pending DREV-077 and
  DREV-088, both of which require higher-precedence governing-source decisions.
  No second revision round is consumed.

- 2026-07-26: Activated a newly authorized cycle with three available revision
  rounds. Round 09 froze DREV-042 through DREV-054 as the complete bounded
  inventory. Revision 07 is authorized for those findings and their direct
  consistency consequences only.
- 2026-07-26: Completed revision 07 with one writer. The design now fixes the
  network-free local default; canonical create/update mutation flow; explicit
  admission/progress/group/finalization atomic-store protocol; closed provider
  normalization and C11 fan-out recovery; independent redaction and filesystem
  schedule verification; separate proposal/semantic capabilities; one complete
  deployment manifest; typed temporal-policy input; closed effective-time
  encoding; retryable progress; and lease-exhaustion result mapping.
- 2026-07-26: Round 10 validated DREV-055 through DREV-058 against revision 07.
  Revision 08 is authorized only for canonical introduction/outcome
  observation, fence alignment, hand-authored semantic-review evidence, and
  their direct consistency consequences.
- 2026-07-26: Completed revision 08 with one writer. Added a canonical
  ingestion-observation ledger and source-finalization outcomes; terminal-
  outcome-first cohort resolution; closed committed/non-committing result
  variants; exact logical-fence alignment; content-bound hand-authored fixture
  review; and independent replay, mutation, atomicity, and import-boundary
  evidence. Frozen design SHA-256:
  `a30ff65fb3947ef3c8f73dc6d07db214cb77eed9238b4794e596a652c0e9bd07`.
- 2026-07-26: Round 11 validated DREV-059 through DREV-063 against revision 08.
  Revision 09, the final permitted revision, is authorized only for the closed
  alignment procedure, independent source-outcome consistency, atomic replay-
  artifact publication, pre-planning progress, and direct consistency updates.
- 2026-07-26: Completed revision 09 with one writer. The design now specifies a
  unique operation/fence-first bipartite alignment, independently validates
  runtime-only source outcome integrity, publishes replay artifacts and their
  first references in one atomic generation, and models pre-planning versus
  planned recovery without sentinel identities. Frozen design SHA-256:
  `da450ce335ce8caad62c9496a5a4dd690803907186437f81a05c080012daeeaf`.
  This is the third and final revision in the authorized cycle.
- 2026-07-26: Round 12 validated DREV-064 through DREV-066. No revision 10 was
  attempted because the authorized three-revision budget is exhausted. This
  WorkPlan is blocked pending explicit authorization for a new bounded cycle
  limited to those three findings and their direct consistency consequences.

- 2026-07-26: Created as a linked proposed design WorkPlan. No design changes
  are authorized until round-01 review reconciliation.
- 2026-07-26: Activated after the round-01 report confirmed one blocking, seven
  high, and seven medium findings. Selected one coherent revision spanning the
  required contract and consistency updates.
- 2026-07-26: Completed revision 01 with one writer. Added the canonical
  requirements ledger; provider-neutral registered proposer contracts with a
  certified local path; dual-analyzer role, scope, and temporal-attachment
  consensus; source-derived event dispositions; canonical memory events and
  atomic replay; store-owned writer admission; current-policy egress;
  discriminated temporal coordinates; lifecycle-bound acceptance evidence;
  mandatory statistical lane coverage; and executable monitoring decisions.
- 2026-07-26: Round 02 validated DREV-016 through DREV-022. Completed revision
  02 with the same writer: bound the ordinary provider/filesystem composition,
  preserved renewable lease and bounded-recovery semantics, required
  backend-level atomic-batch conformance, sourced event versions from monotonic
  durable record envelopes, separated cohort seeds from server-resolved
  co-commit closure, and made SIA-R the sole sourced normative requirement
  namespace.
- 2026-07-26: Round 03 validated DREV-023 through DREV-027. Completed revision
  03 with the same writer: defined certified event-schema decoding and
  deterministic upcasting, separated concrete event identity from logical
  retry deduplication, specified signed replay checkpoints and trust/rollback
  validation, narrowed C12 to the filesystem memory plane, and removed the last
  non-governing SIA source citation.
- 2026-07-26: Fresh round-04 review approved the spec and verification lanes
  but validated DREV-028 and DREV-029 in the correctness lane. No fourth edit
  was made because the three-revision budget is exhausted.
- 2026-07-26: The user authorized a new cycle with at most three additional
  revisions, limited to findings validated by fresh whole-design reviews. The
  design remains unchanged pending the new read-only review.
- 2026-07-26: Round 05 validated DREV-028 through DREV-031. Revision 04 is
  authorized for those four findings and their direct cross-contract,
  acceptance, and verification consequences only.
- 2026-07-26: Completed revision 04 with one writer. Deletion changes and
  events now carry complete prior state and authorization; canonical event
  identity equals compiler record identity; source summaries retain
  append-only attempt/plan/authorization lineage; and the existing provider
  lifecycle envelope composes atomically with a separate typed semantic-result
  accessor. Rollout, risks, prohibited shortcuts, and measurable acceptance
  criteria carry the same invariants.
- 2026-07-26: Round 06 validated DREV-032 through DREV-036. Completed revision
  05 with the same writer: removed physical deletion from semantic ingestion;
  separated envelope, retry, and record identity; made historical same-version
  replay deterministic under the canonical event model; re-anchored dependency
  topology to product sources and selected architecture decisions; and bound
  graph-observation authorization into cohorts, cursors, pagination, and
  independent production-boundary verification.
- 2026-07-26: Round 07 validated DREV-037 through DREV-041 and rejected the
  provider-hook fan-out claim after confirming that adapter expansion precedes
  the one-event semantic-ingestion boundary. Completed revision 06 with the
  same writer: discriminated source admission; exact attribution-bearer
  consensus and canonical binding; production-owned atomic time attestations
  plus acceptance-side signed witnesses; explicit source/graph alignment,
  capability, and identity-reservation DAG stages; and pre-ingest expected
  operation-introduction records.
- 2026-07-26: Round 08 validated DREV-042 through DREV-048. No fourth revision
  was made because the newly authorized three-revision budget is exhausted.
  The exact unresolved corrections and required external authorization are
  recorded in `docs/reviews/semantic_ingestion/review-round-08.md`.

## Evidence Log

- Initial baseline and repository state are recorded in the linked review plan.
- Revision-01 design baseline:
  `dc676c8943a3ef5e3d1e7be8d2e26e391ce0710ed8936f82e54dab759a2defe5`.
- Static evidence: Markdown fences are balanced, `git diff --check` passes, and
  stale round-01 contradiction/undefined-contract searches return no matches.
- Revision-02 design baseline:
  `cb776d08a469bf3c5f2930318301466986109c7e32418d09883802ef01be30aa`.
- Revision-02 static evidence: balanced Markdown fences, clean diff check,
  complete CFP/ING-to-SIA mapping, and no stale cohort, temporal, trace, or
  proposer contradictions.
- Revision-03 design baseline:
  `82e21dc7fb2670c8649149b58e8dd61c2e614de7480e0e7eccc9ae21bb3ed320`.
- Revision-03 static evidence: balanced Markdown fences, clean diff check,
  filesystem-scoped C12 language, governing-only SIA sources, and explicit
  event dedupe/schema/checkpoint contracts with measurable verification.
- Revision-04 design baseline:
  `b8ad145b87a92acbc0ca0d919f571ce7226390d13fa2baf8e35f214dadd9305c`.
- Revision-04 static evidence: 96 balanced Markdown fence lines, clean diff
  check, SIA-R01-through-SIA-R22 coverage, and no contradictory stale
  single-plan, thin-delete, or event-identity contract.
- Revision-05 design baseline:
  `b3fcaeda962cfc2866915cac0957b87ff6c71b263e0a0b95373ce2df6190f303`.
- Revision-05 static evidence: 96 balanced Markdown fence lines, clean diff
  check, and no physical-deletion contract types or stale references.
- Revision-06 design baseline:
  `51aba79c1bce4ca2ac15dbccfd6b5a1f9c8d633a923fcd35715f5b4082b478c2`.
- Revision-06 static evidence: 96 balanced Markdown fence lines, clean diff
  check, closed admission/attribution/stage/expected-record unions, reciprocal
  production/acceptance authority boundaries, and no stale generic
  `proposal_alignment` stage or production-signed witness contract.
- Revision-07 design baseline:
  `45b738d27280ec3fd730c65e7cd5c1078891f9536252697aa8d3a6bf7b8ad78d`.
- Revision-08 design baseline:
  `a30ff65fb3947ef3c8f73dc6d07db214cb77eed9238b4794e596a652c0e9bd07`.
- Revision-09 design baseline:
  `da450ce335ce8caad62c9496a5a4dd690803907186437f81a05c080012daeeaf`.
- Revision-09 static evidence: 41 syntactically valid Python blocks, 98
  balanced Markdown fences, clean diff check, no stale progress or alignment
  names, and explicit traceability for DREV-059 through DREV-063.

## Decision Log

- Decision: Use one coherent writer and the smallest complete corrections.
  Date: 2026-07-26. Rationale: prevents conflicting edits and review-driven
  scope expansion.

## Review Log

- Round-01 baseline review: `Changes required`; confirmed DREV-001 through
  DREV-015. Report:
  `docs/reviews/semantic_ingestion/review-round-01.md`.

## Blockers And Limits

- Historical revision rounds used: three.
- Prior additional revision-round budget used: three.
- Current newly authorized revision-round budget: three.
- Current newly authorized revision rounds used: one.
- Current blockers: DREV-077 and DREV-088.

## Next Action

Wait for the event-model and product/spec owner decisions recorded in
`docs/reviews/semantic_ingestion/review-round-18.md`.

## Outcome And Retrospective

Revision 13 is the current frozen baseline and closes all internally
resolvable findings. DREV-077 and DREV-088 block approval externally.
