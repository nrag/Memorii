# Design Review: Source-Grounded Semantic Ingestion Architecture

## Review Metadata

- Review ID: `semantic-ingestion-round-02`
- Review mode: `full`
- Review outcome: `Changes required`
- Design path: `docs/design/semantic_ingestion_architecture.md`
- Design baseline: SHA-256
  `dc676c8943a3ef5e3d1e7be8d2e26e391ce0710ed8936f82e54dab759a2defe5`
- Implementation baseline: `f76850fc45f09d21a40b5a7302d173ce642ec9d6`
- Review date: 2026-07-26
- Reviewers: independent spec-audit lane (`Beauvoir`), correctness lane
  (`Ptolemy`), dedicated `test_reviewer` (`Aristotle`), coordinator validation
- Scope: complete semantic-ingestion design; retrieval redesign and production
  implementation remain excluded

The dedicated `spec_auditor` and `correctness_reviewer` roles again failed
before repository access because their fixed `gpt-5.6` model is unavailable for
this account. Fresh `gpt-5.4` agents executed those exact independent mandates.
The dedicated `test_reviewer` ran normally. No reviewer saw another lane's
findings before completing.

## Executive Assessment

Revision 01 closes all fifteen round-01 findings. The provider topology, prompt
authority, dual-analyzer consensus, event coverage, temporal algebra, canonical
event emission, writer admission, acceptance authority, statistics, and
monitoring contracts are materially stronger and internally coherent.

Approval remains blocked by four P1 and three P2 findings. Three P1 findings
preserve explicit C3, C12, and C13 hardening obligations in the replacement
architecture. The fourth closes an undefined record-version source in canonical
event replay. The P2 findings remove an oracle contradiction and make the
requirements ledger genuinely canonical and independently traceable.

## Confirmed Findings

### DREV-016: Normal production composition is not acceptance-bound

- Severity: High / P1
- Governing requirement: C3
- Evidence: the owner map names `memory_evolution/service.py`, but neither it
  nor Gate F identifies `ProviderMemoryService` /
  `ProviderIngestionCoordinator` as the normal composition root or requires a
  default-constructor integration test.
- Root cause: the design specifies the new subsystem composition but does not
  bind the ordinary provider entrypoint to it.
- Impact: direct construction tests may pass while default production
  composition still invokes legacy ingestion.
- Required correction: add a stable requirement and name the normal production
  composition root, dependency ownership, and cutover invariant.
- Completion evidence: default filesystem/provider builders exercise accepted
  and evidence-only sources through Steps 1-8, writer admission, canonical
  events, and persistence; legacy writer/fallback is unreachable.

### DREV-017: Lease ownership, stale recovery, and exhaustion are absent

- Severity: High / P1
- Governing requirement: C13
- Evidence: the design defines operation fences, writer epochs, attempts, CAS,
  and replay but no owner token, ownership epoch, lease expiry/renewal, reclaim
  rule, bounded recovery count, or terminal exhaustion state. Current
  `operation_models.py` and `operation_lease.py` already carry these semantics.
- Root cause: the replacement coordinator retained transaction fencing but
  omitted the durable work-ownership lifecycle surrounding long-running stages.
- Impact: stale workers may commit after transfer, abandoned work may never
  recover, or recovery may continue indefinitely.
- Required correction: define one typed lease contract bound to every durable
  stage write, attempt, group persistence request, and CAS.
- Completion evidence: fake-clock and two-process tests cover renewal during
  slow stages, stale reclaim, token/epoch fencing, restart without learned-stage
  recall, lost acknowledgement, bounded recovery, and terminal exhaustion.

### DREV-018: Supported stores lack semantic-ingestion atomic-batch conformance

- Severity: High / P1
- Governing requirement: C12
- Evidence: Step 8 requires graph, event, delta, idempotency, and outcome
  atomicity, but the validation strategy does not require each supported
  backend, especially filesystem/JSONL, to pass that multi-record contract
  under real processes and reopen.
- Root cause: the design states the atomic invariant at the abstract repository
  boundary without binding it to backend conformance.
- Impact: in-memory tests can pass while the supported filesystem store exposes
  a partial semantic group after crash or concurrency.
- Required correction: define a semantic-ingestion atomic-batch store protocol
  and require every supported backend to pass one conformance suite.
- Completion evidence: multiprocess same/distinct delivery, failed replace,
  lost acknowledgement, reopen, corruption, and retry tests observe either the
  previous snapshot or one complete graph/event/outcome set.

### DREV-019: Canonical event versions have no durable source

- Severity: High / P1
- Governing requirement: SIA-R10; canonical event model Sections 8-10
- Evidence: `MemoryEventMetadata.version`, event-ID derivation, and replay use a
  record version, while the canonical record/change contracts expose only
  digests.
- Root cause: revision 01 introduced canonical event replay without adding a
  monotonic version to the durable record envelope and delta.
- Impact: create/update/delete ordering and same-version conflict behavior are
  left to implementer invention.
- Required correction: add a store-owned monotonic `record_version` to durable
  records, snapshot/change preconditions, tombstones, and events; define exact
  advancement semantics.
- Completion evidence: create/update/delete, duplicate, reorder, regression,
  same-version conflict, tombstone, and checkpoint replay tests.

### DREV-020: Cohort selection contradicts safe production coalescing

- Severity: Medium / P2
- Governing requirement: SIA-R17; ING-P2-11 rationale
- Evidence: the oracle must not predict the production transaction partition,
  but the observation request must already contain the complete co-committed
  source/operation closure.
- Root cause: the selector confuses independent seed identity with the
  server-resolved production cohort.
- Impact: a legal larger production group either forces the oracle to learn
  planner output or causes a false failure.
- Required correction: make the request carry independently authored seed IDs;
  the server returns the complete co-committed closure and its proof.
- Completion evidence: safe coalescing and split-group tests prove independence,
  while unexpected extra semantic effects still fail closed-world comparison.

### DREV-021: Requirement namespaces compete for implementation authority

- Severity: Medium / P2
- Governing requirement: `.agent/PLANS.md` design completion contract
- Evidence: Section 1 calls SIA-R normative, while Section 5.13 independently
  requires every CFP and ING item to be implemented and passing.
- Root cause: historical findings remain phrased as a second completion ledger.
- Impact: implementation can drift among overlapping SIA, CFP, and ING rows.
- Required correction: make SIA-R the sole normative namespace; map every CFP
  and ING rationale row to owning SIA-R requirements.
- Completion evidence: a static traceability audit has no unmapped rationale
  row and Section 5.13 gates only on SIA-R completion.

### DREV-022: Several SIA requirements cite only internal or vague sources

- Severity: Medium / P2
- Governing requirement: source precedence in `agents.md`; review-design
  traceability contract
- Evidence: SIA-R05, R06, R11, R13-R15, R17, and R18 cite CFP/ING labels or
  broad descriptions rather than stable document sections.
- Root cause: the first ledger was reconstructed from review findings without
  fully replacing review-local references with governing-source locators.
- Impact: future reviewers cannot independently reconstruct material
  requirements without this document's historical inventory.
- Required correction: cite concrete governing document sections for every
  SIA row and retain CFP/ING only as secondary rationale.
- Completion evidence: every SIA row has at least one stable governing source;
  no requirement depends solely on an internal finding label.

## Rejected Findings

- Missing semantic/unit/held-out verification: rejected; Sections 5.2-5.6
  specify independent minimal-pair, mutation, metamorphic, replay, structural,
  and statistical evidence.
- Mirrored hidden oracle: rejected; expected state is pre-ingest, production
  semantic imports are forbidden, and field/key/page mutations prove closure.
- Unsound statistical activation: rejected; independent scenario clusters,
  constrained exact-binomial use, weighted Hoeffding, Holm-Bonferroni, frozen
  manifests, and independent recomputation are explicit.
- NLI acceptance bypass: rejected; NLI cannot approve and remains
  capability-bound veto/shadow evidence.
- Universal language or long-range discourse coverage: rejected as explicitly
  unsupported, fail-closed behavior.

## Residual Risks

- Human-authored expected semantics still require independent review.
- Learned lanes can share unseen common-mode errors before delayed labels
  arrive; monitoring limits duration and blast radius but cannot prevent the
  first novel error.
- The architecture has high operational complexity. Approval depends on keeping
  the typed ownership boundaries and conformance suites intact during
  implementation.

## Outcome

`Changes required`. Resolve DREV-016 through DREV-022, freeze a new checksum,
and run a fresh whole-design review with new reviewer instances.
