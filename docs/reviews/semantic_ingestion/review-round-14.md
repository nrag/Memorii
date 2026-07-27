# Design Review: Source-Grounded Semantic Ingestion Architecture

## Review Metadata

- Review ID: `semantic-ingestion-round-14`
- Review mode: `full`
- Review outcome: `Changes required`
- Design path: `docs/design/semantic_ingestion_architecture.md`
- Design baseline: SHA-256
  `487f5e88281c443722b9172d15cadb734f4d263d0fb764a69ff9ebf9b7ca8673`
- Implementation baseline: `f76850fc45f09d21a40b5a7302d173ce642ec9d6`
- Review date: 2026-07-26
- Reviewers: fresh `spec_auditor` (`Zeno`), fresh
  `correctness_reviewer` (`Huygens`), fresh `test_reviewer` (`Bernoulli`),
  coordinator validation
- Scope: complete semantic-ingestion design; no reviewer read a prior report

## Executive Assessment

The design is not approved. The verification lane approved. Coordinator
validation confirms three high findings that are direct consistency
consequences of revision 10 and one pre-existing governing-source conflict that
requires an external owner decision. Revision 11 is limited to the three
internally resolvable findings and their direct consistency consequences. The
event-model conflict may be documented but cannot be silently decided by this
lower-precedence design.

## Confirmed High Findings

### DREV-074: Source admission cannot select the capability-scoped writer binding

- Requirements: SIA-R04, SIA-R11, SIA-R19, SIA-R21.
- Evidence: writer admission is keyed by `SemanticCapabilityKey`, while source
  admission now requires a writer binding before operation capability selection,
  which occurs only after source proposal alignment.
- Failure: admission must guess a later predicate/construction capability or
  bind to an unrelated capability. Independent per-capability epochs also fail
  to fence generic shared-record writes globally.
- Root cause: global storage-writer authority and later operation-capability
  authority were represented by one admission record.
- Required correction: introduce one global semantic-writer epoch admission
  used by every source/control/graph write. Keep capability admission/status as
  a separate group-time authorization selected from source-derived semantics.
- Independent verification: admission before capability selection,
  multi-capability sources, in-flight global cutover, per-capability demotion,
  and stale global/capability binding mutations.

### DREV-075: Structured provider envelopes have no semantic-text projection

- Requirements: SIA-R01, SIA-R04, SIA-R05, SIA-R23.
- Evidence: canonical envelope JSON becomes `original_text`, and preparation,
  proposal, and analyzers consume it without a contract identifying semantic
  fields or mapping spans back to message/task/result content.
- Failure: IDs, roles, source references, or result status can be extracted as
  semantic truth, while real content receives only opaque JSON offsets.
- Root cause: retention bytes and semantic-analysis text were conflated.
- Required correction: retain the exact canonical envelope, derive one
  versioned deterministic `SourceSemanticTextProjection` containing only
  allowed content fields, and preserve a reversible segment/path/span map.
- Independent verification: content promotes with exact typed provenance;
  identical text in metadata never promotes; order/reference/version and
  replay mutations preserve or reject projection identity exactly.

### DREV-076: Step 5 conflates source-scoped and graph-scoped normalization

- Requirements: SIA-R02, SIA-R04, SIA-R19, SIA-R20.
- Evidence: the execution registry declares separate graph-free
  `source_proposal_alignment` and graph-bound `graph_proposal_alignment`, but
  `EvidenceNormalizationRequest` requires a graph snapshot and operation fence
  while also performing source alignment and capability selection.
- Failure: implementations must leak graph state into a supposedly immutable
  source artifact or repeat source-only analysis after unrelated graph writes.
- Root cause: the DAG was split without splitting the Step 5 data contracts.
- Required correction: define a graph-free source-normalization request/result
  and a graph-bound request/result. Select operation capability from the sealed
  source result; perform canonical identity, reservation, and graph grouping
  only in the graph-bound attempt.
- Independent verification: reuse a sealed source artifact across unrelated
  graph revisions, rerun only graph-bound stages after related conflict, and
  statically forbid graph imports/inputs in source-scoped stages.

### DREV-077: The governing event model has contradictory same-version replay rules

- Requirements: SIA-R03, SIA-R10.
- Evidence: `docs/design/event_model.md` Section 8.2 says equal-version events
  use `event_id` precedence, while Section 9.2 says an entity with the same
  version is skipped. The target design selects greatest-event-ID precedence
  for historical replay and rejects current-writer collisions.
- Failure: two conflicting same-record/same-version events produce different
  results by input order under Section 9.2 but a greatest-ID result under
  Section 8.2 and the target design.
- Root cause: the higher-precedence source contains two incompatible persisted
  semantics and no recorded owner decision.
- Required correction: an owner must amend or disambiguate the canonical event
  model for byte-identical duplicates, conflicting historical events, and
  current-writer submissions. The target must then bind SIA-R10 to that rule.
- Independent verification: independently authored fixtures exercise both
  orders, identical duplicates, conflicting same-version envelopes, and current
  writes without using the replay reducer as their oracle.
- Disposition: valid external blocker. It is pre-existing and not authorized for
  silent resolution in revision 11.

## Reviewer Dispositions

- The test lane approved with no blocking, high, or medium findings.
- The correctness lane's three findings are confirmed as DREV-074 through
  DREV-076.
- The spec lane's event conflict is confirmed as DREV-077. Because it changes
  persisted replay semantics in a higher-precedence governing document,
  `AGENTS.md` requires an external decision.
- No implementation-absence or retrieval finding was accepted.

## Approval Decision

**Changes required.** Revision 11 may resolve DREV-074 through DREV-076. Even
after those corrections, final approval remains blocked until DREV-077 receives
an external owner decision or repository evidence of a prior authoritative
decision.
