# Design Review: Source-Grounded Semantic Ingestion Architecture

## Review Metadata

- Review ID: `semantic-ingestion-round-07`
- Review mode: `full`
- Review outcome: `Changes required`
- Design path: `docs/design/semantic_ingestion_architecture.md`
- Design baseline: SHA-256
  `b3fcaeda962cfc2866915cac0957b87ff6c71b263e0a0b95373ce2df6190f303`
- Implementation baseline: `f76850fc45f09d21a40b5a7302d173ce642ec9d6`
- Review date: 2026-07-26
- Reviewers: independent spec-audit lane (`Kierkegaard`), correctness lane
  (`Locke`), dedicated `test_reviewer` (`Harvey`), coordinator validation
- Scope: complete semantic-ingestion design; retrieval redesign and production
  implementation remain excluded

The dedicated `spec_auditor` and `correctness_reviewer` roles failed before
repository access because their fixed `gpt-5.6` model is unavailable for this
account. Fresh `gpt-5.4` high-reasoning agents executed those exact independent
mandates. The dedicated `test_reviewer` ran normally. All three reviewed the
complete frozen design without reading prior reports or another lane's
findings.

## Executive Assessment

Revision 05 resolves DREV-032 through DREV-036. The fresh whole-design review
found two material semantic ownership gaps and three verification-contract
gaps. The design does not yet define how a reported-source attribution becomes
an exact canonical bearer, and it incorrectly requires production persistence
to sign acceptance evidence. It also overstates source retention before durable
acceptance, omits graph-dependent stages from its closed execution algebra, and
cannot author the operation-introduction records that its observation API
requires.

Two P1 and three P2 findings block approval. All are inside the existing
ingestion or ingestion-acceptance scope.

## Reconstructed Requirement Coverage

| Requirement area | Coverage | Finding |
| --- | --- | --- |
| Immutable source retention and pre-retention failure | Contradictory | DREV-037 |
| Reported-source attribution grounding | Incomplete | DREV-038 |
| Production/acceptance time-evidence ownership | Contradictory | DREV-039 |
| Closed execution DAG and attempt scopes | Incomplete | DREV-040 |
| Expected operation-introduction records | Incomplete | DREV-041 |
| Provider hook fan-out | Complete after boundary clarification | None |
| Append-only event history and replay | Complete | None |
| Structural observation authorization | Complete | None |

## Confirmed Findings

### DREV-037: Source-retention acceptance includes failures before durable acceptance

- Severity: Medium / P2
- Governing requirements: SIA-R01; source-governance and source-store boundary
- Evidence: SIA-R01 requires every failure path to retain a byte-identical
  source, while Step 1 correctly allows invalid envelopes and source-store
  failures to terminate before durable source acceptance.
- Root cause: the requirement collapses pre-acceptance rejection, failed
  retention, and post-retention semantic failure into one lifecycle state.
- Impact: implementations must either report retention success when no durable
  record exists or violate the stated acceptance criterion.
- Required correction: scope the invariant to every delivery durably accepted
  by the source store. Define explicit non-success dispositions for envelope
  rejection and retention failure; no downstream stage may run in either case.
- Independent verification: failpoint tests cover invalid envelope, failure
  before source write, failure after source write before acknowledgement,
  conflicting replay, and every post-retention stage failure. They prove exact
  retained bytes only when durable acceptance occurred and prove no
  success-shaped retention result otherwise.

### DREV-038: Reported-source attribution has no canonical bearer derivation

- Severity: High / P1
- Governing requirements: SIA-R04 and SIA-R05
- Evidence: `ProviderFact.attributed_to_entity_ref` is candidate-only;
  `StableSemanticScope` records only `speaker` or
  `quoted_or_reported_source`; `LanguageNeutralFact.attributed_to` requires an
  exact `CanonicalEntityReference`. No typed artifact binds the reported-source
  span and provider reference through source-local identity, parser consensus,
  and canonical identity.
- Root cause: attribution scope classification and attribution-bearer identity
  were treated as the same decision.
- Impact: an implementer must invent a bearer, silently use the speaker, or
  drop attribution. Quoted and reported claims can therefore be committed under
  the wrong authority.
- Required correction: introduce a closed, source-grounded attribution
  consensus artifact that identifies the exact bearer mention/cluster for
  reported-source scope, bind it through canonical identity resolution, and
  require the resulting canonical bearer in accepted facts. Disagreement,
  missing evidence, non-entity bearers, or candidate/analysis mismatch is
  unresolved with zero graph effect.
- Independent verification: direct speech, nested quotation, reported speech,
  omitted bearer, ambiguous bearer, pronoun/coreference, analyzer disagreement,
  provider substitution, and canonical-identity substitution tests mutate each
  link independently.

### DREV-039: Production persistence is required to sign acceptance evidence

- Severity: High / P1
- Governing requirements: SIA-R01, SIA-R13, and the acceptance import boundary
- Evidence: production persistence owns signed source-retention and group-commit
  witnesses issued under the acceptance authority snapshot, while the design
  also forbids production from importing the acceptance package or comparator.
- Root cause: production commit-time facts and acceptance trust attestations
  were collapsed into one signed type.
- Impact: implementation must leak acceptance keys/policy into production or
  leave live system-time comparison unverifiable.
- Required correction: production atomically emits immutable typed commit-time
  attestations under production ownership. The acceptance harness reads those
  attestations through a public, scope-authorized boundary and independently
  signs acceptance witnesses that bind the complete attestation digest and
  production coordinates. Production never imports acceptance schemas, keys,
  or policy.
- Independent verification: crash-atomic attestation tests, public-boundary
  authorization tests, independent witness construction/signature tests, and
  attestation/witness substitution mutations prove the ownership split.

### DREV-040: The closed execution-stage algebra omits required stages

- Severity: Medium / P2
- Governing requirements: SIA-R04 and the execution-DAG contract
- Evidence: prose requires capability selection, capability-status binding
  validation, and planned-identity reservation at explicit scopes, but
  `IngestionStage` has no corresponding variants. The single
  `proposal_alignment` label also conflates source-only
  `SourceProposalAlignment` with graph-bound `ProposalAlignment`.
- Root cause: the execution enum lagged behind the typed workflow decomposition.
- Impact: manifests cannot represent or validate every required stage,
  cardinality, dependency, retry, or first divergence.
- Required correction: add distinct closed stage variants for source proposal
  alignment, graph proposal alignment, capability selection,
  capability-status binding validation, and planned-identity reservation; map
  each to its exact scope and dependencies.
- Independent verification: exhaustively enumerate the stage registry; reject
  omitted, duplicated, wrong-scope, wrong-dependency, and cross-attempt stage
  outcomes.

### DREV-041: The expected graph cannot represent operation introductions

- Severity: Medium / P2
- Governing requirements: SIA-R17 and closed-world structural comparison
- Evidence: `GraphObservationPage` and cohort closure require
  `ObservedOperationIntroduction`, but `ExpectedGraphRecordKind` and
  `ExpectedGraphRecord` omit an expected counterpart.
- Root cause: the observation schema gained operation provenance without a
  matching independent expected-record variant.
- Impact: the comparator must ignore observed operation introductions or invent
  expected records after ingest, violating direct closed-world comparison.
- Required correction: add `ExpectedOperationIntroduction`, include it in the
  expected kind and record unions, author it pre-ingest from fixture operations,
  and include it in exact counts, boundary profiles, key mapping, and mutation
  tests.
- Independent verification: missing, extra, wrong-source, wrong-operation-kind,
  wrong-predicate, wrong-span, and boundary mutations fail exact comparison.

## Rejected Finding

### One provider hook delivery can create multiple operations

The claim is rejected as a semantic-ingestion defect. The current
`HermesMemoryProvider.sync_turn` adapter expands one hook invocation into two
independently identified `ProviderMemoryService.sync_event` calls. Each call
constructs one `ProviderEvent` and enters the semantic-ingestion boundary as a
separate delivery. The design's one-delivery/one-operation invariant applies
after that expansion. Pulling hook aggregation into this document would expand
scope into agent integration. The design should clarify the boundary and retain
the existing deterministic child IDs; it should not define a new multi-event
operation.

## Coordinator Disposition

DREV-037 through DREV-041 are confirmed. The hook-fan-out claim is rejected
after direct code inspection; a terminology clarification is sufficient and
does not add agent-integration scope.

No finding based solely on absence of future implementation was accepted. No
retrieval-query, agent-integration, compatibility API, or unrelated
architecture work is included.

## Material Risk Register

| Risk | Required design response |
| --- | --- |
| Wrong claim authority | Typed attribution-bearer consensus and canonical binding |
| Acceptance trust leakage into production | Production attestation plus acceptance-side signed witness |
| False retention success | Explicit pre-retention failure dispositions |
| Incomplete causal manifests | Closed stage algebra matching every typed workflow stage |
| Hidden-oracle repair | Expected operation-introduction records authored before ingest |

## Outcome

`Changes required`. Resolve DREV-037 through DREV-041 with one writer, freeze a
new baseline, and run a fresh full review using new reviewer instances.
