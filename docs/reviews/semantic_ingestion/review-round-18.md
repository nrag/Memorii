# Design Review: Source-Grounded Semantic Ingestion Architecture

## Review Metadata

- Review ID: `semantic-ingestion-round-18`
- Review mode: `full`
- Review outcome: `Blocked on external governing decisions`
- Design path: `docs/design/semantic_ingestion_architecture.md`
- Design baseline: SHA-256
  `3d7f1f045d32a8c13504fc501d8265c1c62f2ef1b5d3d76e4a061efece39d957`
- Implementation baseline: `f76850fc45f09d21a40b5a7302d173ce642ec9d6`
- Review date: 2026-07-26
- Reviewers: fresh `spec_auditor` (`Copernicus`), fresh
  `correctness_reviewer` (`Hypatia`), fresh `test_reviewer`
  (`Chandrasekhar`), coordinator validation
- Scope: complete semantic-ingestion design; retrieval remains excluded
- Prior-report rule: reviewers did not read prior review reports

## Executive Assessment

Revision 13 closes DREV-079 through DREV-087. The fresh full review found no
additional internally resolvable blocking, high, or medium design defect.
Approval remains blocked by two conflicts in higher-precedence governing
sources. The semantic-ingestion design cannot choose either answer without
inventing material product semantics.

No further design revision is authorized until the owners make the two
decisions below. Once recorded in the governing sources, one bounded
consistency revision and fresh full review are required.

## Validated External Findings

### DREV-077: Governing same-version replay semantics conflict

- Severity: blocking.
- Requirements: SIA-R03, SIA-R10, SIA-R18.
- Governing evidence: `docs/design/event_model.md` Section 8.2 gives
  same-version events `event_id` precedence, while Sections 9.2 and 10.2 skip
  an event when the materialized entity already has that version.
- Target evidence: Section 4.8 of the reviewed design selects the
  lexicographically greatest `event_id` for historical same-version conflicts.
- Root cause: the canonical event model defines incompatible outcomes for the
  same valid input.
- Consequence: delivery order can change materialized state. A checkpoint made
  after event A also cannot converge with genesis replay if a later equal-
  version event B would win under `event_id` precedence but tail replay skips
  equal versions.
- Required external decision: the event-model owner must choose and record one
  rule for:
  1. byte-identical duplicate envelopes;
  2. non-identical historical envelopes for one record/version;
  3. current-writer attempts to submit an already materialized version; and
  4. checkpoint-tail replay when a later equal-version envelope appears.
- Smallest coherent option: exact duplicates are idempotently skipped;
  non-identical equal-version envelopes are corruption and block readiness;
  current writers must reject equal-version collisions before commit. The
  alternative is a deterministic winner rule plus a signed checkpoint winner
  index and equal-version replacement semantics.
- Required verification after the decision: all permutations of identical and
  conflicting equal-version events from genesis and signed checkpoints across
  every supported backend must converge byte-for-byte or fail before exposing
  state.

### DREV-088: Semantic model invocation and durable writeback ownership conflict

- Severity: blocking.
- Requirements: SIA-R03, SIA-R08, SIA-R09, SIA-R19.
- Governing evidence: `docs/design/memorii_spec.md` Section 19.1 assigns model
  invocation to the host harness. Section 21.2 requires Memorii to emit
  normalized writeback candidates and says the host adapter decides whether to
  persist them.
- Target evidence: Sections 2.1 and 4.3 of the reviewed design make Memorii run
  pinned in-process llama.cpp or direct OpenAI proposal calls. Sections 4.7 and
  4.8 let the Memorii coordinator compile and atomically persist accepted graph
  mutations.
- Root cause: the governing spec and the ingestion design assign credentials,
  model execution, persistence authorization, and retry/audit ownership to
  different components.
- Consequence: a framework-neutral host cannot implement both contracts. Moving
  only the API call but not request identity, credentials, retries, candidate
  provenance, and commit authorization would leave split authority and
  unverifiable behavior.
- Required external decision: the product/spec owner must choose and record one
  complete ownership model:
  1. **Host-owned inference and persistence authorization.** Memorii emits a
     content-bound semantic request and schema; the host invokes the selected
     model and returns a provenance-bound candidate envelope. Memorii validates
     and compiles it, but commits only under an explicit host writeback
     authorization.
  2. **Memorii-owned internal semantic inference and persistence.** Amend
     Sections 19.1 and 21.2 to distinguish host agent-model invocation from
     certified internal memory-analysis inference and to authorize Memorii's
     validated semantic transaction to persist directly.
- Required verification after the decision: run the selected composition with
  the non-owner stripped of credentials and commit authority; prove complete
  ingestion succeeds only through the selected owner and that the rejected
  ownership path cannot call a model or mutate durable state.

## Coordinator Dispositions

- The spec lane independently confirmed DREV-077.
- The correctness lane independently confirmed DREV-077, identified its
  checkpoint consequence, and proposed the ownership conflict now recorded as
  DREV-088.
- The checkpoint consequence is part of DREV-077 rather than a separate
  internally fixable finding because its correct schema depends on the
  governing equal-version decision.
- The test lane's five findings are rejected as design findings. They report
  absence of the future architecture in the current implementation, while this
  task reviews the architecture document. The design already requires an
  implementation coverage ledger, production composition tests, public
  structural observation, external crash supervision, and independent
  certification. Those claims belong to a later implementation review and do
  not authorize design changes.
- No retrieval, agent-integration, compatibility, or unrelated cleanup issue
  was admitted.

## Revision-13 Closure

Fresh whole-design review found no remaining internal defect in the revision-13
corrections for:

- graph-free source dependency grouping;
- immutable reservations with renewable use authorization;
- correction, retraction, and identity transition temporal provenance;
- production-boundary versus oracle-only mutation outcomes;
- independent production-surface verification;
- ordered event-batch positions and checkpoint suffix replay;
- capability-derived statistical coverage;
- real-composition zero-egress verification; and
- fixture-author and reviewer-domain independence.

## Approval Decision

**Blocked, not approved.** DREV-077 and DREV-088 require explicit governing-
source decisions. No additional internal revision can close them without
inventing material semantics.

