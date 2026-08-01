# Design Review: Source-Grounded Semantic Ingestion Architecture

## Review Metadata

- Review ID: `semantic-ingestion-round-15`
- Review mode: `full`
- Review outcome: `Changes required`
- Design path: `docs/design/semantic_ingestion_architecture.md`
- Design baseline: SHA-256
  `9559322a6cf8beb4d35568a36712471baee7e41b557751d1d36f7a56083d1e87`
- Implementation baseline: `f76850fc45f09d21a40b5a7302d173ce642ec9d6`
- Review date: 2026-07-26
- Reviewers: fresh `spec_auditor` (`Meitner`), fresh
  `correctness_reviewer` (`Hegel`), fresh `test_reviewer` (`Gauss`),
  coordinator validation
- Scope: complete semantic-ingestion design; no reviewer read a prior report

## Executive Assessment

The design is not approved. Revision 11 closes DREV-074 through DREV-076, and
the verification strategy remains complete at the design level. Coordinator
validation confirms one new medium internal finding: authenticated source
intervals retain their numeric value but lose their authenticated provenance
identity after source governance. The governing event-model conflict DREV-077
also remains an external blocker.

Revision 12 is limited to preserving authenticated source-interval evidence
end-to-end and its direct verification consequences. It may not silently choose
the persisted same-version event semantics blocked by DREV-077.

## Confirmed Medium Finding

### DREV-078: Authenticated source-interval provenance is lost after governance

- Requirements: SIA-R06, SIA-R12, SIA-R17, SIA-R18.
- Evidence: `SourceSemanticContext`, `TemporalEvidenceAssessment`, and
  `AcceptedTemporalEvidence` carry the authenticated source interval only as a
  bare `TimeInterval`. `ObservedClaimAssertion` exposes the resolved interval
  and optional event/document reference but no authenticated source-interval
  evidence.
- Failure: a source interval authorized by one metadata field, authority basis,
  or principal can be replaced after governance by a numerically equal interval
  with different or absent provenance. Acceptance, replay, and direct graph
  comparison cannot detect the substitution.
- Root cause: event/document references were modeled as authenticated evidence
  objects, while authenticated source intervals were modeled only as values.
- Required correction: introduce a closed
  `AuthenticatedSourceIntervalEvidence` contract containing interval, source
  field, authority basis, provenance digest, and evidence digest. Preserve it
  byte-for-byte through source context, assessment, accepted IR, durable
  records, replay, expected fixtures, and observed records.
- Independent verification: hold interval endpoints constant while
  independently swapping field, basis, provenance digest, and evidence digest
  at every boundary. Each substitution must fail at its first boundary with no
  graph visibility.

## Continuing External Blocker

### DREV-077: The governing event model has contradictory same-version replay rules

- Requirements: SIA-R03, SIA-R10.
- Evidence: `docs/design/event_model.md` Section 8.2 gives equal-version events
  deterministic `event_id` precedence, while Section 9.2 skips an event when
  the entity already has the same version.
- Required external decision: the event-model owner must define canonical
  behavior for byte-identical duplicates, conflicting historical equal-version
  events, and current-writer equal-version submissions.
- Disposition: unchanged external blocker. The target design cannot resolve a
  contradiction in its higher-precedence governing source.

## Reviewer Dispositions

- The spec lane confirmed only DREV-077.
- The correctness lane's authenticated source-interval finding is confirmed as
  DREV-078.
- The test lane reported absence of the proposed architecture's future tests in
  the current implementation. Those findings are rejected as design findings:
  this review evaluates whether the design specifies measurable independent
  verification, not whether a future implementation already exists. The design
  already requires independent evidence for source analysis, temporal
  construction, production boundaries, atomic replay, migration, and oracle
  import separation.
- No retrieval-layer, benchmark-pass, or unrelated implementation finding was
  accepted.

## Approval Decision

**Changes required.** Revision 12 may resolve DREV-078. Final approval remains
blocked until DREV-077 receives an authoritative owner decision and the target
design is reconciled to the amended governing event model.
