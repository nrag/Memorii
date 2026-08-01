# Design Review: Source-Grounded Semantic Ingestion Architecture

## Review Metadata

- Review ID: `semantic-ingestion-round-06`
- Review mode: `full`
- Review outcome: `Changes required`
- Design path: `docs/design/semantic_ingestion_architecture.md`
- Design baseline: SHA-256
  `b8ad145b87a92acbc0ca0d919f571ce7226390d13fa2baf8e35f214dadd9305c`
- Implementation baseline: `f76850fc45f09d21a40b5a7302d173ce642ec9d6`
- Review date: 2026-07-26
- Reviewers: independent spec-audit lane (`Leibniz`), correctness lane
  (`Halley`), dedicated `test_reviewer` (`Raman`), coordinator validation
- Scope: complete semantic-ingestion design; retrieval redesign and production
  implementation remain excluded

The dedicated `spec_auditor` and `correctness_reviewer` roles failed before
repository access because their fixed `gpt-5.6` model is unavailable for this
account. Fresh `gpt-5.4` high-reasoning agents executed those exact independent
mandates. The dedicated `test_reviewer` ran normally. All three reviewed the
complete frozen design without reading prior reports or another lane's
findings.

## Executive Assessment

Revision 04 resolves DREV-028 through DREV-031 at their immediate contract
boundaries. The fresh whole-design review found five remaining inconsistencies:
one conflicts with higher-precedence graph-retention requirements, three leave
identity, replay, or requirement authority ambiguous, and one leaves the
acceptance observation boundary without required authorization evidence.

One P1 and four P2 findings block approval. All are inside the existing
ingestion, event, persistence, or acceptance scope.

## Reconstructed Requirement Coverage

| Requirement area | Coverage | Finding |
| --- | --- | --- |
| Append-only memory history and graph retention | Contradictory | DREV-032 |
| Canonical event identity and retry identity | Partial | DREV-033 |
| Canonical replay for same-version events | Contradictory | DREV-034 |
| Initial dependency topology traceability | Unclear | DREV-035 |
| Structural observation authorization | Partial | DREV-036 |
| Attempt-specific plan lineage | Complete | None |
| Provider lifecycle compatibility | Complete | None |
| Full-state update and logical-delete replay | Complete subject to DREV-032 | None |

## Confirmed Findings

### DREV-032: Semantic graph records can be physically deleted

- Severity: High / P1
- Governing requirements: `memory_evolution_runtime.md` claim lifecycle and
  graph-retention contracts; `memorii_spec.md` append-only backtracking;
  `event_model.md` logical delete replay
- Evidence: the design defines `GraphRecordPhysicalDeletion`, deletion
  authorizations, and codec modes that permit physical removal. Higher-
  precedence sources require old claims and graph records to remain retained
  and represent stale state through lifecycle/status transitions.
- Root cause: storage lifecycle deletion was generalized into the semantic
  graph mutation algebra even though this architecture owns durable memory
  history, not an out-of-band storage-compaction protocol.
- Impact: an implementation must choose between the target design and the
  governing retention/replay contract; current, historical, and lineage views
  can lose required records.
- Required correction: remove physical deletion from semantic-ingestion graph
  changes, planning, events, codec contracts, authorization, rollout, and
  verification. Retraction, invalidation, retirement, and supersession remain
  complete typed updates with immutable historical records. Any future storage
  compaction protocol is separately governed and outside this design.
- Independent verification: schema/static tests forbid a physical-delete graph
  change or deletion policy in semantic ingestion; genesis/checkpoint replay and
  `ALL_VERSIONS` observation retain superseded, invalidated, retracted, and
  archived records.

### DREV-033: SIA-R10 conflates event, retry, and record identity

- Severity: Medium / P2
- Governing requirement: canonical event model Sections 3-5 and 9; SIA-R10
- Evidence: SIA-R10 says “event identity equals compiler record identity,”
  while the detailed contract correctly separates envelope `event_id`, logical
  retry `dedupe_key`, and payload `entity_id`/`record_id`.
- Root cause: a shorthand acceptance phrase collapsed three deliberately
  distinct identity domains.
- Impact: implementation and acceptance can equate the wrong identifiers.
- Required correction: define all three identities in SIA-R10 and require only
  `payload.entity_id == payload.record_id ==
  GraphRecordChange.record_id`.
- Independent verification: a static definition/reference audit and mutation
  tests separately exercise event, dedupe, and record identity.

### DREV-034: Same-version replay contradicts the canonical event rules

- Severity: Medium / P2
- Governing requirement: canonical event model Sections 8.2 and 9.2; SIA-R10
- Evidence: the target classifies any same-record/version conflicting content
  as corruption, while the governing model gives same-version precedence to
  `event_id` ordering and says already-materialized same versions are skipped.
- Root cause: current-writer integrity rules and mixed-version historical replay
  rules were collapsed into one check.
- Impact: a historical or mixed-schema stream requires an implementer-selected
  replay policy.
- Required correction: current semantic-ingestion writes reject a conflicting
  same-version record before commit. Canonical replay first groups historical
  events by entity/version and selects the greatest `event_id`, then applies
  the ordinary skip/lower/higher-version rules. Duplicate event IDs or dedupe
  keys with conflicting content remain corruption.
- Independent verification: replay same-version fixtures in both input orders;
  the greatest event ID wins deterministically, a later materialized same
  version skips, and current-writer collision tests fail before visibility.

### DREV-035: SIA-R16 cites process policy as product authority

- Severity: Medium / P2
- Governing requirement: `AGENTS.md` source precedence
- Evidence: SIA-R16 cites `.agent/PLANS.md`, which `AGENTS.md` explicitly says
  is not a source of product behavior.
- Root cause: a design-consistency requirement inherited the WorkPlan completion
  contract as its authority rather than the architecture decisions and product
  requirements that selected the dependency topology.
- Impact: topology disagreements cannot be resolved through the declared source
  hierarchy.
- Required correction: source SIA-R16 from the selected architecture decisions
  implementing the governing local-first, independent-evidence, and
  certification requirements; retain `.agent/PLANS.md` only as process policy.
- Independent verification: the normative ledger contains no product
  requirement whose authority is a process artifact.

### DREV-036: Structural observation authorization lacks acceptance evidence

- Severity: Medium / P2
- Governing requirement: scoped storage access; SIA-R17
- Evidence: the observation API says authorization derives from the
  authenticated principal, but SIA-R17 and its verification strategy omit
  cross-principal, cross-scope, cursor, and revocation tests.
- Root cause: structural correctness tests were specified independently, while
  the production authorization boundary was left as prose.
- Impact: a privileged acceptance harness can pass while the production API
  leaks cohort existence, records, boundary records, digests, or pages across
  scopes.
- Required correction: make authorization a measurable SIA-R17 acceptance
  condition and require real-boundary tests for authorized access, cross-scope
  and mixed-seed denial, forged cursors, pagination reauthorization, and
  revocation with no partial or existence disclosure.
- Independent verification: seed two scopes through ordinary ingestion and use
  the production observation API/storage adapter without production cohort
  helpers or a privileged test bypass.

## Coordinator Disposition

All five findings are confirmed. DREV-032 is not a request to redesign general
storage deletion; it removes an ingestion capability forbidden by governing
memory-retention contracts. DREV-036 does not redesign retrieval; it verifies
the existing acceptance-only structural observation boundary.

No finding based solely on absence of the future implementation was accepted.
No retrieval-query, agent-integration, or unrelated architecture work is
included.

## Material Risk Register

| Risk | Required design response |
| --- | --- |
| Historical memory loss | Remove physical delete from semantic ingestion and prove retained replay/views |
| Identity-domain confusion | Name and test envelope, retry, and record identities separately |
| Nondeterministic mixed-version replay | Separate write-time collision rejection from canonical replay precedence |
| Unsourced topology choice | Re-anchor SIA-R16 to governing requirements and selected design decisions |
| Cross-scope acceptance-data disclosure | Add fail-closed authorization and pagination/revocation verification |

## Outcome

`Changes required`. Resolve DREV-032 through DREV-036 with one writer, freeze a
new baseline, and run a fresh full review using new reviewer instances.
