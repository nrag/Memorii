# Operation Alignment Persisted Schema

- Work ID: semantic-ingestion-operation-alignment-schema
- Work type: design
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-08-05
- Last updated: 2026-08-05
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md`, source-alignment production contracts and focused tests
- Expected outputs: one approved exact `OperationAlignment` persisted schema,
  one graph-free pre-alignment operation-subject owner, one closed normalized
  semantic-proposal contract family, one request-owned minimal
  consensus-policy selection boundary, one distinct request-owned
  language/construction policy authority bundle, one graph-free retained
  evidence manifest for source normalization, and one closed verification
  matrix over replay, abstention, selector normalization, and persistence-byte
  recovery

## Objective

Close the design holes where `SourceProposalAlignment` names
`OperationAlignment` without defining its exact persisted fields or digest
preimage, where replay lacks typed selected-policy authority, where the
pre-alignment semantic `operation_id` lacks one exact graph-free owner, and
where normalized proposal and policy leaves remain named but undefined, so
implementation and replay require no inferred semantics, no live policy
lookup, no implicit abstention behavior, and no object-only replay proof.

## Completion Contract

The canonical architecture defines every field, type, equality join,
canonicalization rule, digest domain/preimage, unsupported form, compatibility
rule, and positive/negative proof for the eight-field row, the pre-alignment
subject owner, the normalized semantic-proposal contract family, the required
selection bundle, the distinct language/construction policy authority bundle,
and the retained evidence manifest. Frozen independent reviews leave no
required finding, and the user approves the persisted-contract choices.

## Scope

Included: the operation-to-source/proposal/segment/route/parser/scope/temporal
join record used inside `SourceProposalAlignment`, and the request-owned typed
consensus-policy selection bundle needed to replay its policy equality joins.
Included as adjacent design closure: request-owned language/construction policy
content authority, source-normalization retained-evidence manifest ownership,
provider selector normalization, abstention algebra, and persistence-byte
replay proof for this boundary. Excluded: changing parser, scope, or temporal
algorithms; graph-bound planning; or M4 conflict behavior.

## Constraints And Invariants

The record is graph-free, source-derived, strict, content-addressed, and cannot
invent canonical graph identity, graph revision, plan, attempt, or provider-
local authority. Every referenced consensus artifact must be loadable and bind
the same source, source digest, segment, proposal, route, policy, and analysis
bundle where applicable.

## Identity And Coordinate Hygiene

`OperationAlignment` is a durable behavioral identity prescribed by the design.
No planning or evidence coordinate enters its fields, discriminator, digest
domain, tests, or diagnostics.

| Identifier or value | Classification | Disposition |
| --- | --- | --- |
| `OperationAlignment` and `SourceProposalAlignment` | behavioral contract names | Retained only as canonical design contract names. |
| `memorii.semantic-ingestion.operation-alignment.v1` | durable digest domain | Retained exactly; no version alias or legacy preimage is introduced. |
| `source_id`, parent source digest, route, proposal, segment, consensus artifact digests, request-dependency fingerprints, and selected-policy fingerprints | source-derived or content-addressed identities | Bound by exact outer joins and exact artifact-to-selection bijection; no inferred, live, or provider-local replacement is allowed. |
| Review and WorkPlan coordinates | planning/evidence coordinates | Confined to this WorkPlan; absent from the persisted schema, CTV preimage, vectors, and diagnostics. |

## Change Impact And Verification Closure

Potential surfaces are the canonical architecture, semantic contracts/codecs,
source alignment validation, focused tests, trace fixtures, and downstream
lineage/persistence schemas. The implementation remains blocked from approval
until the chosen schema and all dependents agree.

Changed in this operation: only
`docs/design/semantic_ingestion_architecture.md` and this WorkPlan. Production,
tests, generated authority, fixtures, and the existing
`source_alignment_fingerprint` semantics remain unchanged. The architecture
change is limited to the source-normalization request contract, its policy
selection types and invariants, and source-alignment validation strategy; it
does not alter the eight `OperationAlignment` fields.

## Sources Of Truth

The source-grouping and source-alignment prose and adjacent exact class
definitions in the semantic-ingestion architecture govern intent. Existing
provisional implementation is feasibility evidence only, not design authority.

## Current State

The approved design now defines the exact eight-field `OperationAlignment`
immediately before `SourceProposalAlignment`. It additionally requires one
graph-free `PreAlignmentSemanticOperationSubject` owner for every retained
semantic proposal operation, six closed normalized `Proposed*` contracts plus
their provider-to-normalized mapping, the request-owned typed
`ConsensusPolicySelectionBundle` needed to make every minimal consensus witness
replayable, the separate request-owned
`LanguageConstructionPolicyAuthorityBundle` needed to replay Step 5 semantic
policy application without registries, and the
`SourceNormalizationEvidenceManifest` needed to enumerate all retained aligned
and terminal-unaligned evidence under one atomic publication coordinate.
Production remains provisional feasibility evidence only; this design
operation does not modify it.

Read-only architecture analysis compared three serious alternatives. It
recommends an explicit content-addressed join record containing `operation_id`,
`proposal_id`, `segment_id`, the exact segment-route, parser-consensus,
scope-consensus, and temporal-consensus digests, plus `alignment_digest` over
the other fields under
`memorii.semantic-ingestion.operation-alignment.v1`. The enclosing source
alignment owns source ID/digest and must verify every referenced artifact binds
that same source and the row's proposal, segment, and route.

Deriving the join implicitly was rejected because coverage and retry contracts
refer to alignment digests. Embedding the full consensus artifacts per row was
rejected because it duplicates canonical truth and increases drift/migration
risk.

## Assumptions And Open Questions

Verified: the omission is real. Working assumption: an explicit content-
addressed join record is preferable to embedding repeated consensus objects.
User decision: approved on 2026-08-05: "Minimal is good for now." The approved
contract is the recommended explicit eight-field content-addressed join record
and exact digest rule; no additional row fields are authorized.

User approval: on 2026-08-05 the user approved continuation of the minimal
request-owned `ConsensusPolicySelectionBundle`. It preserves the existing
ten-field `ConsensusPolicySelection` outer wire and freezes only the minimal
inner parser/scope/temporal consensus rule records for each
operation/proposal/segment/route coordinate without adding a ninth
`OperationAlignment` field.

User approval: on 2026-08-05 the user approved the final missing
`SemanticScopePolicy.policy_fingerprint` rule. The selected domain is
`memorii.semantic-ingestion.semantic-scope-policy.v1`; the preimage contains
every declared field except `policy_fingerprint`, uses canonical CTV map/set
ordering, orders the three policy pattern tuples by `pattern_digest`, and
preserves nested path-step traversal order.

## Milestones Or Experiments

1. Reconstruct all required joins and serious alternatives from governing prose.
2. Draft one minimal exact schema and attack matrix.
3. User approval obtained; update the canonical design, run design hygiene, and
   obtain targeted frozen review.

## Progress Log

- 2026-08-05: Frozen implementation review found the referenced persisted type
  undefined in the approved design and blocked contract approval.
- 2026-08-05: Architecture analysis recommends the explicit minimal join
  record above. Independent consultation found no substantive schema objection,
  but approval-quality review requires freezing the later design draft.
- 2026-08-05: User approved the minimal contract. The canonical architecture
  now defines `OperationAlignment` immediately before `SourceProposalAlignment`
  with exactly `operation_id`, `proposal_id`, `segment_id`,
  `segment_language_route_digest`, `parser_consensus_digest`,
  `scope_consensus_digest`, `temporal_attachment_consensus_digest`, and
  `alignment_digest`; it also closes wire validation, CTV digest identity,
  outer joins, coverage, and source-dependency-group completeness.
- 2026-08-05: Delta review confirmed the eight-field receipt and deterministic
  projection rules, but found the requested policy-equality replay check
  unrepresentable because the normalization request lacks typed selected-policy
  authority. Architecture analysis rejected deriving it from existing fields
  and recommends one minimal source-level selection bundle.
- 2026-08-05: Frozen-review remediation keeps the exact eight-field schema and
  makes its collection projection, request-input joins, strict-v1-only
  compatibility, replay, and independent CTV proof requirements explicit.
- 2026-08-05: User approved the adjacent minimal bundle. The canonical design
  now requires `SourceNormalizationRequest.consensus_policy_selections` with
  strict frozen `ConsensusPolicySelection` and
  `ConsensusPolicySelectionBundle` wires; request-dependency equality,
  canonical selection order, typed digest recomputation, exact
  artifact-to-selection bijection, replay/recovery reload, graph/capability
  isolation, and unshipped strict-v1-only migration behavior are explicit.
  `OperationAlignment` remains exactly eight fields.
- 2026-08-05: Targeted correctness review confirmed one runtime design defect:
  the selection coordinate allowed only one parser/scope/temporal selection per
  `(proposal_id, segment_id, route)` even though one segment proposal may carry
  multiple semantic operations. The canonical design now carries a deterministic
  pre-alignment semantic `operation_id` through the three consensus artifacts
  and `ConsensusPolicySelection`, preserving the eight-field
  `OperationAlignment` receipt while allowing one exact selection per operation
  subject. The same remediation also makes route-language and shared
  scope/temporal field coherence explicit at that operation subject.
- 2026-08-05: Follow-up frozen review found the new semantic `operation_id`
  still non-derivable because its exact pre-alignment owner omitted source
  identity. The canonical design now defines
  `PreAlignmentSemanticOperationSubject` as a strict graph-free owner over
  `kind`, exact `source_id`, exact `source_digest`, exact
  `proposal_id`/`proposal_digest`, exact segment/route context, exact
  zero-based proposal-member index, and `operation_id`.
- 2026-08-05: Targeted frozen review then found two remaining conformance gaps:
  the design tried to hash undefined normalized proposal-member schemas, and
  the new subject authority still lacked an explicit fail-closed wire contract.
  The canonical design now closes both by making
  `PreAlignmentSemanticOperationSubject` an exact proposal-coordinate owner:
  it expands the five retained proposal operation arrays in canonical persisted
  order,
  binds each subject to the retained validated `proposal_digest` plus one
  `proposal_member_index`, and rejects missing, extra, out-of-range,
  cross-context, alias, inferred, legacy/predecoder, migration-reader,
  digest-format, duplicate-`operation_id`, or non-bijective subject bindings.
- 2026-08-05: Follow-up spec review found `proposal_digest` itself still
  undefined. The canonical design now defines `SemanticProposal.proposal_digest`
  as the content address of the exact validated normalized proposal bytes under
  `memorii.semantic-ingestion.semantic-proposal.v1` and requires every non-null
  `SegmentProposalOutcome.proposal_digest` to equal the one matching validated
  proposal for that segment and exact route.
- 2026-08-05: The user approved the narrow design expansion needed to close the
  remaining derivability hole. The canonical design now defines exact closed
  contracts for `ProposedMention`, `ProposedFact`, `ProposedCorrection`,
  `ProposedRetraction`, `ProposedActionState`, and
  `ProposedIdentityOperation`, their provider-to-normalized mapping, supporting
  object/action/reference helper types, and the closed policy leaves needed by
  `PredicateSemanticPolicy`, `SemanticScopePolicy`, and the consensus-policy
  wrappers.
- 2026-08-05: Frozen remediation superseded the earlier inner-wrapper design
  without changing the outer wire. `SourceNormalizationRequest` no longer
  carries `PredicateRegistry` or `ScopePolicyRegistry`; the sealed
  `ConsensusPolicySelectionBundle` is now the sole persisted minimal
  consensus-policy witness boundary. `ConsensusPolicySelection` still has ten
  declared fields and a
  nine-field digest preimage, but its inner `ParserConsensusPolicy`,
  `ScopeConsensusPolicy`, and `TemporalAttachmentConsensusPolicy` records are
  now minimal closed rule witnesses containing only `kind`, the exact v1
  algorithm literal, `required_independent_analyzers=2`, and
  `policy_fingerprint`.
- 2026-08-05: The same remediation closes the remaining equality and proof
  gaps. Each distinct operation row now owns exactly one parser artifact, one
  scope artifact, and one temporal artifact; no retained consensus artifact may
  satisfy multiple distinct rows. Canonical nested tuple rules are now explicit
  for temporal qualifier spans, role bindings, participants, grounding spans,
  predecessor/successor mention digests, reference assignments, and assignment
  successor digests. The proof matrix now covers
  `ProposedEntityObject`/`ProposedLiteralObject`, independent
  `logical_action_digest` and `execution_branch_digest` vectors, the actual
  provider-to-normalized replay boundary, canonical map-field equivalence for
  subject maps, and fail-fast live-lookup sentinels.
- 2026-08-05: Final frozen remediation closes the remaining Step 5 and replay
  authority holes without changing the eight-field row or the ten-field outer
  selection wire. The canonical design now adds a distinct request-owned
  `LanguageConstructionPolicyAuthorityBundle` carrying exact
  `PredicateSemanticPolicy` and `SemanticScopePolicy` content by
  operation/proposal/segment/route coordinate; a graph-free
  `SourceNormalizationEvidenceManifest` owned by `SourceNormalizationResult`
  that enumerates all retained aligned and terminal-unaligned artifacts plus
  their exact selections and atomic publication coordinate; explicit
  abstention algebra; same-proposal selector normalization; split-only
  reference assignments; top-level duplicate-digest rejection; and
  persistence-byte replay obligations with fail-fast sentinels and
  foreign-generation rejection.
- 2026-08-05: Slice B implementation review exposed one final design omission:
  `SemanticScopePolicy` was described as fingerprinted but its digest domain
  and canonical preimage were unspecified. The user approved the recommended
  strict rule. The canonical architecture now publishes the exact domain,
  excluded field, CTV map/frozenset ordering, canonical pattern-tuple order,
  nested traversal-order semantics, and fail-closed legacy/default behavior.

## Evidence Log

- `SourceProposalAlignment` class reference: architecture near line 13066.
- No `class OperationAlignment` definition occurs in the canonical design.
- 2026-08-05 design text proof: the canonical class now occurs immediately
  before `SourceProposalAlignment`; its domain is
  `memorii.semantic-ingestion.operation-alignment.v1`; no production or
  generated-authority artifact was modified.
- 2026-08-05 remediation proof: `git diff --check --
  docs/design/semantic_ingestion_architecture.md
  docs/work/semantic_ingestion/operation-alignment-schema/design.plan.md`
  exits zero. From `memorii/`, `.venv/bin/python -m
  memorii.tools.identity_hygiene --root .. --allowlist
  ../.agents/identity_hygiene_allowlist.json` exits zero. These checks establish
  document hygiene only, not implementation or replay evidence.
- 2026-08-05 bundle-design proof: canonical text names every retained aligned
  and terminal unaligned consensus coordinate, forbids a missing bundle or
  inferred/live policy lookup, and preserves the existing
  `source_alignment_fingerprint` semantics. Final command evidence is recorded
  in Review Log after this edit.
- 2026-08-05 inner-policy closure proof: canonical text now defines exact
  `ParserConsensusPolicy`, `ScopeConsensusPolicy`, and
  `TemporalAttachmentConsensusPolicy` class shapes as minimal rule witnesses,
  preserves the ten-field outer `ConsensusPolicySelection` wire, removes the
  undefined `PredicateRegistry` and `ScopePolicyRegistry` request fields, and
  makes `selected_policy.policy_fingerprint`,
  `selected_policy_fingerprint`, and the artifact
  `consensus_policy_fingerprint` one exact equality class.
- 2026-08-05 operation-subject closure proof: canonical text now defines exact
  `PreAlignmentSemanticOperationSubject` fields, copies exact source/proposal/
  segment/route context from the validated proposal, binds one retained
  `proposal_digest` plus one zero-based member index, hashes the subject under
  a dedicated digest domain, declares the wire strict/frozen/`extra="forbid"`,
  and requires validator recomputation of the complete subject set from the
  five retained proposal operation arrays in canonical persisted order.
- 2026-08-05 proposal-digest closure proof: canonical text now defines
  `SemanticProposal.proposal_digest` as a dedicated content-addressed digest of
  exact validated proposal bytes and requires an exact bijection between
  validated proposals and non-null `SegmentProposalOutcome.proposal_digest`
  values for the same segment and route.
- 2026-08-05 normalized-proposal closure proof: canonical text now defines
  exact closed provider helper types, normalized `Proposed*` member contracts,
  per-type digest domains, provider-to-normalized span/reference mapping, local
  ID invariants, branch-pairing rules, same-segment correction/retraction
  rules, and identity-reference constraints sufficient to derive
  `SemanticProposal.proposal_digest`.
- 2026-08-05 canonical-order closure proof: canonical text now defines exact
  duplicate-free tuple order for temporal qualifier spans, role bindings,
  participants, grounding spans, predecessor/successor mention digests,
  reference assignments, and assignment successor digests, and corrects the
  map-member permutation proof to canonical equivalence rather than rejection.
- 2026-08-05 policy-leaf closure proof: canonical text now defines exact
  closed `ConstructionFamily`, `UdPathPattern`, `QuotationBoundaryPolicy`, and
  `UdRoleSchema` owners, making `PredicateSemanticPolicy`,
  `SemanticScopePolicy`, and the three consensus-policy wrappers fully
  implementable without named undefined leaves. The accompanying prose now
  states explicitly that `UdPathStep` is not independently content-addressed
  and contributes only through `UdPathPattern.pattern_digest`.
- 2026-08-05 language-policy authority proof: canonical text now defines a
  request-owned `LanguageConstructionPolicyAuthorityBundle` with exact
  `OperationSemanticPolicyKey`, `ParserOperationPolicyAuthority`, and
  `ScopeOperationPolicyAuthority` entries. The key covers all five normalized
  subject kinds, including typed action/identity coordinates without invented
  predicates, with exact policy-content applicability and no live registry
  join.
- 2026-08-05 evidence-manifest proof: canonical text now defines a
  graph-free `SourceNormalizationEvidenceManifest` and
  `SourceNormalizationEvidenceEntry` family owned by
  `SourceNormalizationResult`, with complete aligned plus terminal-unaligned
  retained-artifact enumeration, exact selection linkage, non-circular
  operation-fence/current-next-generation publication coordinate, and replay/
  load obligations through the existing atomic generation/checkpoint path.
- 2026-08-05 abstention-and-selector proof: canonical text now removes
  `ProviderReferenceAssignment.record_kind`, requires same-proposal selector
  normalization, requires empty assignments for alias/rekey/merge and
  source-grounded assignments only for split, makes
  `ProposedFact.temporal_qualifier_spans` canonical and duplicate-free, rejects
  duplicate top-level normalized member digests before sealing, and closes the
  abstention algebra from provider output through source-level run status.

## Decision Log

- Approved: explicit minimal content-addressed join record using the exact
  eight fields and digest domain recorded in Current State. The canonical CTV
  preimage contains all body fields in declaration order except
  `alignment_digest`; all digests are lowercase 64-hex.
- Approved: parser, scope, and temporal tuples are exact one-per-row
  projections ordered by operation/proposal/segment/route coordinate. Every
  distinct row has exactly one retained artifact of each kind, and no retained
  consensus artifact may satisfy multiple distinct rows. Unaligned terminal
  consensus artifacts remain replay evidence outside those projections.
- Approved: joined consensus artifacts must bind the exact normalization
  request's analysis bundle, selected consensus policy, or temporal-resolution
  input and receive the same checks on recovery and replay.
- Approved: add one strict/frozen request-owned consensus-policy selection
  bundle with exactly one parser, scope, and temporal-attachment selection per
  retained aligned or terminal unaligned consensus coordinate. The bundle
  contains exact typed selected-policy rule content, request-dependency
  fingerprint, selected-policy fingerprint, selection digest, canonical
  ordering, and a bundle digest; recovery/replay recompute all of them with no
  live lookup.
- Approved: `SourceNormalizationRequest` removes the undefined
  `PredicateRegistry` and `ScopePolicyRegistry` fields. The sealed
  `ConsensusPolicySelectionBundle` is the sole persisted consensus-policy
  witness boundary for source normalization and replay.
- Approved: `ParserConsensusPolicy`, `ScopeConsensusPolicy`, and
  `TemporalAttachmentConsensusPolicy` remain the compatible inner selection
  types, but each is now a minimal exact rule record over `kind`, one exact
  v1 algorithm literal, `required_independent_analyzers=2`, and
  `policy_fingerprint`.
- Approved: `selected_policy.policy_fingerprint`,
  `selected_policy_fingerprint`, and the matched artifact
  `consensus_policy_fingerprint` must be identical; replay performs no
  predicate/scope/temporal registry join to reconstruct or reinterpret them.
- Approved: `ConsensusPolicySelection` and the three consensus artifacts carry
  one deterministic source-derived semantic `operation_id` before alignment
  finalization. Bundle uniqueness, ordering, and artifact-selection bijection
  now bind `(kind, operation_id, proposal_id, segment_id,
  segment_language_route_digest)` rather than segment proposal coordinates
  alone. `OperationAlignment` remains exactly eight fields because its existing
  row `operation_id` already names the same subject.
- Approved: `PreAlignmentSemanticOperationSubject` is the sole graph-free
  authority for semantic `operation_id` before alignment and acceptance. It
  carries exact `source_id`, `source_digest`, `proposal_id`, retained validated
  `proposal_digest`, `segment_id`, `segment_language_route_digest`, one
  zero-based `proposal_member_index`, and `operation_id`; validators recompute
  the complete subject set from the five retained proposal operation arrays in
  canonical persisted order and reject missing, extra, out-of-range, cross-context,
  alias, inferred, legacy/predecoder, migration-reader, digest-format,
  duplicate-`operation_id`, non-bijective, or independently re-derived
  bindings.
- Approved: `SemanticProposal.proposal_digest` is the exact content address of
  the validated normalized proposal bytes under
  `memorii.semantic-ingestion.semantic-proposal.v1`. Every non-null
  `SegmentProposalOutcome.proposal_digest` must equal the one matching
  validated proposal for that segment and exact route; cross-proposal,
  alternate-domain, alternate-encoding, missing, or digest-only substitution
  rejects before subject construction or run sealing.
- Approved: the six normalized proposal member families
  `ProposedMention`, `ProposedFact`, `ProposedCorrection`,
  `ProposedRetraction`, `ProposedActionState`, and
  `ProposedIdentityOperation` are closed, typed, source-grounded owners.
  Provider quotes normalize only into exact `SourceSpanReference` values;
  provider local IDs remain proposal-scoped helpers only and never become graph
  identity; proposal operation tuples are canonicalized by source-derived
  persisted order and `proposal_member_index` is over that canonical order.
- Approved: the policy-leaf concern is closed by defining exact
  `ConstructionFamily`, `UdPathPattern`, `QuotationBoundaryPolicy`, and
  `UdRoleSchema` owners rather than reopening the bundle boundary. The existing
  `PredicateSemanticPolicy`, `SemanticScopePolicy`, and
  consensus-policy wrappers remain the canonical selected-policy owners.
- Approved: Step 5 receives a distinct request-owned
  `LanguageConstructionPolicyAuthorityBundle` carrying exact
  `PredicateSemanticPolicy` and `SemanticScopePolicy` content by
  operation/proposal/segment/route coordinate. The minimal consensus witness
  never carries predicate/language/construction semantics itself; Step 5
  applies those semantics only from the sealed authority bundle, and replay
  reuses those stored bytes with no registry lookup.
- Approved: `SourceNormalizationResult` owns a graph-free
  `SourceNormalizationEvidenceManifest` that enumerates every retained parser,
  scope, and temporal artifact, both aligned and terminal-unaligned, plus the
  exact selection digests and one non-circular operation-fence plus expected
  generation publication coordinate. The aligned tuples are verified subsets of
  that manifest, not the primary inventory.
- Approved: canonical nested tuple rules are explicit and fail closed.
  Temporal qualifier spans and grounding spans are ordered by
  `reference_digest`; participants by `(mention_digest, participant_digest)`;
  role bindings by `(role_id, endpoint_kind, binding_digest)`; predecessor,
  successor, and assignment-successor mention tuples by mention digest; and
  reference assignments by `(record_selector.selector_digest,
  assignment_digest)`. Duplicates and noncanonical order reject before any
  enclosing digest is sealed.
- Approved: `ProposedFact.temporal_qualifier_spans` are canonicalized by
  `reference_digest` and reject duplicates. Duplicate normalized member digests
  in each top-level `mentions`, `facts`, `corrections`, `retractions`,
  `action_states`, and `identity_operations` tuple reject before sealing.
- Approved: `ProviderReferenceAssignment.record_kind` is removed.
  `record_selector.kind` is the sole selector discriminator; selector
  normalization is same-proposal only; alias/rekey/merge require empty
  assignments; and split alone may carry source-grounded reassignment.
- Approved: abstention is exact and closed. Provider abstention requires empty
  five-operation arrays, `SemanticProposal.status` and
  `SegmentProposalOutcome.status` must match exactly, a run is `abstained` if
  and only if every route-selected validated proposal abstains, and abstention
  yields zero subjects and zero semantic effects.
- Approved: CTV map-member permutations for `OperationAlignment`,
  `ConsensusPolicySelection`, and `PreAlignmentSemanticOperationSubject`
  canonicalize to the same bytes and digest; only semantic tuple permutations
  reject.
- Approved: replay proof must exercise the actual provider-to-normalized
  boundary and fail-fast live-lookup sentinels, not only in-memory digest
  recomputation. Durable replay must reopen exact codec/persistence bytes,
  validate the evidence manifest against one attested outer generation, and
  reject circular generation binding, foreign-generation substitution,
  missing/extra/partial retained evidence, lost acknowledgement, and
  substitution-before-output/write.
- Rejected: deriving the join implicitly from the three consensus collections,
  because coverage and retry contracts require an immutable row digest and an
  explicit operation/proposal/segment coordinate.
- Rejected: embedding full consensus artifacts in each row, because it
  duplicates canonical source truth and creates independent drift and migration
  surfaces.
- Compatibility and migration: these are unshipped provisional bytes. No
  legacy wire, alias, inferred field or policy/bundle, missing bundle, legacy
  digest preimage, predecoder bridge, or migration reader is accepted;
  implementation must decode only these strict v1 closed wires. Rollback before
  first release removes unshipped readers, writers, and bytes, rather than
  adding a compatibility reader.

## Review Log

Frozen implementation spec review identified the design ambiguity. The
user-approved design candidate is frozen for full design review:

- Git HEAD: `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`; dirty-local tree.
- Canonical design SHA-256:
  `55668911a27e6af615293d83273397dd37ddca53db9f9d80dfd811b2067bf9a5`.
- Canonical design binary-diff SHA-256:
  `3497716836309b7521ceccd76ae1750a9c9f9a590277d2f9bb2966beec612d1a`.
- Git-status SHA-256 from exact command
  `git status --porcelain=v1 -z --untracked-files=all | shasum -a 256`:
  `de3b796316dc13eab07131d2532cbe67adf7bea8e0c383e2d154cc6e55ca01b2`.
- `git diff --check` and repository identity-hygiene checks pass.
- Review scope is the new `OperationAlignment` definition and its adjacent
  normative validation, compatibility, and attack clauses. Unrelated earlier
  design changes are excluded.

Remediated candidate identity (still dirty-local):

- Git HEAD: `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`.
- Canonical design SHA-256:
  `d68cc492e9416d049a9a4f3cf5cbfd08961cf56587033dfd830501448eadcaef`.
- Canonical design binary-diff SHA-256:
  `e7de1467b9ac90a2d64d776cd75344f09198ca9572e328cd2cee357c978fd7d9`.
- Git-status SHA-256 remains
  `de3b796316dc13eab07131d2532cbe67adf7bea8e0c383e2d154cc6e55ca01b2`.

Approved bundle candidate identity (still dirty-local):

- Git HEAD remains `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`.
- Canonical design SHA-256:
  `466527dad6d414d7e639c6b8be4565b0d47e5f695546c01ca3d8a918e69f82ad`.
- Canonical architecture binary-diff SHA-256:
  `bee74776a0847c2eb4057f51565883cea4742e497075cd543c234ad409553c6e`.
- Git-status SHA-256 remains
  `de3b796316dc13eab07131d2532cbe67adf7bea8e0c383e2d154cc6e55ca01b2`.
- `git diff --check -- docs/design/semantic_ingestion_architecture.md
  docs/work/semantic_ingestion/operation-alignment-schema/design.plan.md` and
  `PYTHONPATH=memorii .venv/bin/python -m memorii.tools.identity_hygiene --root
  . --allowlist .agents/identity_hygiene_allowlist.json` exit zero. This is
  documentation and identity hygiene evidence only; it is not production or
  replay proof.

Inner-policy-closed candidate identity (still dirty-local):

- Git HEAD remains `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`.
- Canonical design SHA-256:
  `52171ef72f8b2c76956168ab5ea062d6d0a2e0deb7e32317aa3a108296a50a5f`.
- Canonical architecture binary-diff SHA-256:
  `f8abf94d85d522dbc4a501841c6343c692481bdb5f1bf040167c401ba610e904`.
- Git-status SHA-256 remains
  `de3b796316dc13eab07131d2532cbe67adf7bea8e0c383e2d154cc6e55ca01b2`.
- `git diff --check -- docs/design/semantic_ingestion_architecture.md
  docs/work/semantic_ingestion/operation-alignment-schema/design.plan.md` and
  `PYTHONPATH=memorii .venv/bin/python -m memorii.tools.identity_hygiene --root
  . --allowlist .agents/identity_hygiene_allowlist.json` exit zero.
- Historical review target: execute the targeted independent design review over the inner
  policy-owner closure and its adjacent replay boundary.

Operation-subject-remediated candidate identity (still dirty-local):

- Git HEAD remains `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`.
- Canonical design SHA-256:
  `fc0a0351a7f8d9a306cf91e696ccb33649f1435287aa223a2659ac08a6434933`.
- Canonical architecture binary-diff SHA-256:
  `1b6f65e3634fff42b66838fc98f72a9bf3a44aa2d3ec3faef8b143099d7fd006`.
- Git-status SHA-256 remains
  `de3b796316dc13eab07131d2532cbe67adf7bea8e0c383e2d154cc6e55ca01b2`.
- `git diff --check -- docs/design/semantic_ingestion_architecture.md
  docs/work/semantic_ingestion/operation-alignment-schema/design.plan.md` and
  `PYTHONPATH=memorii .venv/bin/python -m memorii.tools.identity_hygiene --root
  . --allowlist .agents/identity_hygiene_allowlist.json` exit zero.
- Historical review target: rerun the targeted independent design review against this
  operation-subject-remediated candidate.

Source-bound operation-subject-remediated candidate identity (still dirty-local):

- Git HEAD remains `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`.
- Canonical design SHA-256:
  `0d1d24d4f47068e05601b81e41c36f34605d6ebc8c75615cbd82eebbc9a933bf`.
- Canonical architecture binary-diff SHA-256:
  `e4bfda877f5f6c782ff507b6128d9c41ca58b1b3fcebeb25382fe0d9b862deb1`.
- Git-status SHA-256 remains
  `de3b796316dc13eab07131d2532cbe67adf7bea8e0c383e2d154cc6e55ca01b2`.
- `git diff --check -- docs/design/semantic_ingestion_architecture.md
  docs/work/semantic_ingestion/operation-alignment-schema/design.plan.md` and
  `PYTHONPATH=memorii .venv/bin/python -m memorii.tools.identity_hygiene --root
  . --allowlist .agents/identity_hygiene_allowlist.json` exit zero.
- Historical review target: rerun the targeted independent design review against this
  source-bound operation-subject candidate.

Proposal-coordinate operation-subject-remediated candidate identity (still dirty-local):

- Git HEAD remains `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`.
- Canonical design SHA-256:
  `6c57d9260e7ea0fdd7404382a511f2d1144dc4eaebdb26d5e08d3efaeb42ba0e`.
- Canonical architecture binary-diff SHA-256:
  `b1c5abff3af28788298140794b0c7c4fe2c5f8a40d32a5653562c339ae43adaa`.
- Git-status SHA-256 remains
  `de3b796316dc13eab07131d2532cbe67adf7bea8e0c383e2d154cc6e55ca01b2`.
- `git diff --check -- docs/design/semantic_ingestion_architecture.md
  docs/work/semantic_ingestion/operation-alignment-schema/design.plan.md` and
  `PYTHONPATH=memorii .venv/bin/python -m memorii.tools.identity_hygiene --root
  . --allowlist .agents/identity_hygiene_allowlist.json` exit zero.
- Historical review target: rerun the targeted independent design review against this
  proposal-coordinate operation-subject candidate.

Proposal-digest-defined candidate identity (still dirty-local):

- Git HEAD remains `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`.
- Canonical design SHA-256:
  `1850ad31f8c6ec549c4a5375eb60f807960408cb33e28b2e854df4109b3aef62`.
- Canonical architecture binary-diff SHA-256:
  `03e4cffce6a60f6eb65f0df8f3d3fdb21fdefd6e4acec89b8ae1589b2ffe037a`.
- Git-status SHA-256 remains
  `de3b796316dc13eab07131d2532cbe67adf7bea8e0c383e2d154cc6e55ca01b2`.
- `git diff --check -- docs/design/semantic_ingestion_architecture.md
  docs/work/semantic_ingestion/operation-alignment-schema/design.plan.md` and
  `PYTHONPATH=memorii .venv/bin/python -m memorii.tools.identity_hygiene --root
  . --allowlist .agents/identity_hygiene_allowlist.json` exit zero.
- Historical review target: rerun the targeted independent design review against this
  proposal-digest-defined candidate.

Normalized-proposal-and-policy-leaf-defined candidate identity (still dirty-local):

- Git HEAD remains `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`.
- Canonical design SHA-256:
  `5810219f0a6949245d917b393f31b2771197735e004261ebdfffed4401feb075`.
- Canonical architecture binary-diff SHA-256:
  `b591fe4d249d43babf0416e1328da0dfcac09df31a7b78cd6b3ca306aae2607c`.
- Git-status SHA-256 remains
  `de3b796316dc13eab07131d2532cbe67adf7bea8e0c383e2d154cc6e55ca01b2`.
- `git diff --check -- docs/design/semantic_ingestion_architecture.md
  docs/work/semantic_ingestion/operation-alignment-schema/design.plan.md` and
  `PYTHONPATH=memorii .venv/bin/python -m memorii.tools.identity_hygiene --root
  . --allowlist .agents/identity_hygiene_allowlist.json` exit zero.
- Historical review target: rerun the targeted independent design review against this
  normalized-proposal and policy-leaf-expanded candidate.

Minimal-consensus-policy-and-row-bijection-remediated candidate identity (still dirty-local):

- Git HEAD remains `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`.
- Canonical design SHA-256:
  `3faabfb03726597f72c996fb082fbf78d796b05d72b8b2c7af7b38f0c4ef0805`.
- Canonical architecture binary-diff SHA-256:
  `eed59b30ee495ebd7fd4aa5e1baed454447a66780dde6abca4fecd5fd81f013c`.
- Git-status SHA-256 remains
  `de3b796316dc13eab07131d2532cbe67adf7bea8e0c383e2d154cc6e55ca01b2`.
- `git diff --check -- docs/design/semantic_ingestion_architecture.md
  docs/work/semantic_ingestion/operation-alignment-schema/design.plan.md` and
  `PYTHONPATH=memorii .venv/bin/python -m memorii.tools.identity_hygiene --root
  . --allowlist .agents/identity_hygiene_allowlist.json` exit zero.
- Review scope is the frozen delta that removes the undefined request registries,
  preserves the ten-field outer selection wire, narrows inner selection content
  to minimal consensus-rule records, requires one retained artifact per
  operation row, freezes nested tuple canonicalization, and expands the replay
  and proof matrix accordingly.

Replay-authority-and-evidence-manifest-remediated candidate:

- Review scope extends the frozen delta to the distinct request-owned
  `LanguageConstructionPolicyAuthorityBundle`, the graph-free
  `SourceNormalizationEvidenceManifest`, same-proposal selector normalization,
  split-only reference assignments, explicit abstention closure, canonical
  top-level duplicate rejection, the non-circular
  `operation_fence_binding` plus current/next-generation publication
  coordinate, and persistence-byte replay/load obligations through the exact
  attested atomic store generation.
- Git HEAD remains `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`.
- Canonical design SHA-256:
  `7012ed17416b850c096095f88dda5966188d20ba8eb14c2046d1ea8c94dbe592`.
- Canonical architecture binary-diff SHA-256:
  `82b6d166fb519eeac2cc04697fec61f7cc42cc042e3335b34e5a6dd90cea33e2`.
- Git-status SHA-256 from exact command
  `git status --porcelain=v1 -z --untracked-files=all | shasum -a 256`:
  `de3b796316dc13eab07131d2532cbe67adf7bea8e0c383e2d154cc6e55ca01b2`.
- Scoped `git diff --check` and repository identity hygiene exit zero.

Frozen-review determinate finding dispositions:

| Finding | Product priority | Approval disposition | Finding type | Disposition |
| --- | --- | --- | --- | --- |
| Projection/source authority and shared-reference behavior were underspecified. | P2 | changes_required | persisted runtime behavior | Confirmed and remediated in the canonical alignment clause. |
| Joined consensus artifacts did not bind all replayed normalization inputs. | P2 | changes_required | replay/runtime behavior | Confirmed and remediated with exact request-input and recovery joins. |
| Compatibility boundary permitted interpretation drift. | P2 | changes_required | compatibility | Confirmed and remediated as unshipped strict-v1-only decoding and removal rollback. |
| Attack matrix lacked an independent CTV oracle and required mutations. | P2 | changes_required | verification | Confirmed and remediated in the validation strategy. |
| One selection coordinate could not represent multiple semantic operations in one proposal segment. | P2 | changes_required | persisted runtime behavior | Confirmed and remediated by adding pre-alignment semantic `operation_id` to the adjacent selection and consensus artifacts while preserving the eight-field receipt. |
| Route/predicate compatibility and shared scope/temporal policy coherence were implicit at one operation subject. | Not applicable | changes_required | governance / replay conformance | Confirmed and remediated with explicit subject-compatibility invariants and replay revalidation; no live registry lookup is required. |
| Pre-alignment semantic `operation_id` remained non-derivable because its subject owner did not bind exact source context. | Not applicable | changes_required | contract conformance | Confirmed and remediated by making `PreAlignmentSemanticOperationSubject` the exact source-bound owner and by requiring validator recomputation of the complete subject set from retained proposal members. |
| Subject identity depended on undefined normalized proposal-member schemas. | Not applicable | changes_required | persisted-contract / architecture | Confirmed and remediated by replacing the member-hash scheme with an exact retained `proposal_digest` plus zero-based `proposal_member_index` over the five proposal operation arrays in canonical persisted order. |
| The subject authority lacked an explicit fail-closed closed-wire rejection contract. | Not applicable | changes_required | verification / persisted-contract conformance | Confirmed and remediated by declaring `PreAlignmentSemanticOperationSubject` strict/frozen/`extra="forbid"` v1 and adding omission/extra/alias/inference/legacy/digest-format rejection obligations. |
| `proposal_digest` was referenced in the subject preimage without one exact canonical proposal-byte digest contract or outcome equality rule. | Not applicable | changes_required | persisted-contract / replay conformance | Confirmed and remediated by defining `SemanticProposal.proposal_digest` under `memorii.semantic-ingestion.semantic-proposal.v1` and by requiring every non-null `SegmentProposalOutcome.proposal_digest` to equal the one matching validated proposal for that segment and exact route. |
| `proposal_digest` still could not be derived because the six normalized proposal member types were only named. | Not applicable | changes_required | persisted-contract / replay conformance | Confirmed and remediated by defining exact closed `Proposed*` contracts, helper types, and provider-to-normalized mapping rules. |
| Selected-policy wrappers still depended on named but undefined leaf schemas. | Not applicable | changes_required | architecture / implementation readiness | Confirmed and remediated by defining `ConstructionFamily`, `UdPathPattern`, `QuotationBoundaryPolicy`, and `UdRoleSchema` as exact closed owners. |
| `SourceNormalizationRequest` still named undefined `PredicateRegistry` and `ScopePolicyRegistry` owners even though replay was meant to be bundle-driven. | Not applicable | changes_required | persisted-contract / replay conformance | Confirmed and remediated by removing both fields and declaring the sealed `ConsensusPolicySelectionBundle` the sole persisted minimal consensus-policy witness boundary. |
| The persisted inner selection content was over-specified and required impossible wrapper-level semantic joins. | Not applicable | changes_required | architecture / replay conformance | Confirmed and remediated by replacing the inner parser/scope/temporal payloads with exact minimal rule records over `kind`, algorithm literal, analyzer count, and `policy_fingerprint`, while preserving the ten-field outer `ConsensusPolicySelection` wire. |
| The design allowed one retained consensus artifact to satisfy multiple distinct operation rows. | P2 | changes_required | persisted runtime behavior | Confirmed and remediated by requiring one retained parser/scope/temporal artifact per distinct operation row and forbidding cross-row artifact reuse even when digests match. |
| Canonical nested tuple order and duplicate rejection remained implicit for multiple normalized proposal members. | Not applicable | changes_required | persisted-contract / replay conformance | Confirmed and remediated by freezing explicit canonical keys for spans, participants, bindings, predecessor/successor tuples, reference assignments, and assignment-successor tuples. |
| The proof matrix incorrectly treated subject/map-member permutations as rejection cases and missed several affected boundary vectors. | Not applicable | changes_required | verification | Confirmed and remediated by correcting map-member permutation behavior to canonical equivalence and by adding `ProposedEntityObject` / `ProposedLiteralObject`, `logical_action_digest`, `execution_branch_digest`, provider-boundary replay, and live-lookup-sentinel vectors. |
| Digest prose still implied `UdPathStep` had a standalone content address. | Not applicable | changes_required | architecture / contract clarity | Confirmed and remediated by stating explicitly that `UdPathStep` is a closed leaf embedded in `UdPathPattern` and contributes only through `pattern_digest`. |
| Replay still lacked one sealed typed policy-content authority after the registry fields were removed. | Not applicable | changes_required | replay conformance / architecture | Confirmed and remediated by adding the distinct request-owned `LanguageConstructionPolicyAuthorityBundle` with exact `PredicateSemanticPolicy` and `SemanticScopePolicy` content, coordinate applicability, and digest rules. |
| Source normalization still lacked a graph-free retained-evidence inventory and exact publication/load contract. | Not applicable | changes_required | replay conformance / persisted-contract | Confirmed and remediated by adding `SourceNormalizationEvidenceManifest` plus `SourceNormalizationEvidenceEntry`, exact selection linkage, and a non-circular operation-fence plus expected-generation publication coordinate. |
| `ProposedFact.temporal_qualifier_spans` remained noncanonical, and duplicate top-level normalized member digests could still seal. | Not applicable | changes_required | persisted-contract / replay conformance | Confirmed and remediated by canonicalizing `temporal_qualifier_spans` by `reference_digest` and rejecting duplicate digests in every top-level normalized tuple before sealing. |
| `ProviderReferenceAssignment` retained a redundant selector-kind field and under-specified selector normalization and operation applicability. | Not applicable | changes_required | normalized-contract conformance | Confirmed and remediated by removing `record_kind`, defining same-proposal selector normalization, requiring empty assignments for alias/rekey/merge, and allowing source-grounded assignments only for split. |
| Abstention semantics remained under-specified across provider proposal, normalized proposal, segment outcome, run status, and Step 5 effect boundaries. | P2 | changes_required | persisted runtime behavior | Confirmed and remediated by closing the abstention algebra exactly and forbidding any subject, alignment, capability, or graph effect from abstained proposals or fully abstained runs. |
| Replay proof still depended on in-memory objects and a circular manifest-generation binding. | Not applicable | changes_required | verification / replay conformance | Confirmed and remediated by requiring persistence-byte replay through the real codec/store boundary, using a non-circular operation-fence plus expected-generation coordinate, and rejecting circularity, foreign-generation substitution, missing/extra/partial retained evidence, lost acknowledgement, and substitution-before-output/write. |
| Policy applicability was predicate-only, leaving action-state and identity subjects without a derivable sealed policy key. | Not applicable | changes_required | persisted-contract / replay conformance | Confirmed and remediated with the closed five-variant `OperationSemanticPolicyKey` algebra, exact fact-like bindings, typed action state/role coordinates, typed identity operation/mention/assignment coordinates, and explicit parser/scope authority cardinalities. |
| `PredicateSemanticPolicy` named but did not carry its own trailing content address. | Not applicable | changes_required | persisted-contract conformance | Confirmed and remediated by adding `policy_fingerprint` as the final field and defining its exact independent CTV domain/preimage. |
| Source-normalization publication was described alongside, rather than as a specialization of, the production atomic generation/checkpoint hierarchy. | Not applicable | changes_required | architecture / replay conformance | Confirmed and remediated with `AtomicGenerationRequest` -> `SourceCheckpointAtomicWriteRequest` -> `SourceNormalizationAtomicWriteRequest`, preserving existing member kinds and adding typed normalization members to the same generation closure. |
| New sealed wires lacked one complete strict codec/rollback statement and a policy-variant replay proof. | Not applicable | changes_required | verification / compatibility | Confirmed and remediated by exact strict-v1 codec registration/rejection/rollback rules and a stable-versus-terminal-unaligned persisted-byte, fail-fast-sentinel proof. |
| The checkpoint subtype did not retain the exact originating normalization request or define its actual member/progress closure. | Not applicable | changes_required | persistence / replay conformance | Confirmed and remediated by retaining the typed request and digest in the same generation, binding manifest/request/result/coordinate equality, and defining the subtype-only progress/member/digest/CAS/lost-ack/recovery contract. |
| The normalization checkpoint inherited the ordinary checkpoint's `planned` state even though its subtype closure cannot contain the required planning artifacts. | P2 | changes_required | transactional state / persisted-contract conformance | Confirmed and remediated by constraining `SourceNormalizationAtomicWriteRequest.progress_state` to literal `preplanning`, requiring the exact pre-planning progress variant, and rejecting planned state before publication. |

## Attack And Evidence Matrix

| Attack or proof family | Required invariant | Evidence owner and result |
| --- | --- | --- |
| Wire shape and compatibility | Eight fields only; strict/frozen/extra-forbid decoding; no aliases, inference, legacy preimage, predecoder bridge, or migration reader | Future focused contract test: omit, add, alias, or infer a field and require rejection; CTV map-member permutations canonicalize, while semantic tuple permutations reject; legacy vectors reject and no compatibility reader is registered. |
| Digest identity | Every digest is lowercase 64-hex; digest covers all and only seven body fields under the approved domain | Independently hand-authored fixed CTV bytes/digest oracle, without a production helper, plus mutations of each body field, domain, digest spelling/format, and `alignment_digest`. |
| Selection wire and digest | Every selection has exactly ten declared fields and every bundle exactly `selections` plus `bundle_digest`; the selection digest preimage covers the nine declared fields other than `selection_digest`; `selected_policy.kind`, algorithm, analyzer count, and `policy_fingerprint` are closed and recomputed | Future independent CTV vectors mutate each selection field, selected-policy discriminator, algorithm literal, analyzer count, policy fingerprint, bundle member, domain, omission, extra field, alias, missing bundle, legacy form, and digest spelling; all reject. |
| Language/construction policy authority | Step 5 semantics come only from one sealed request-owned typed policy-content bundle with exact coordinate applicability and no registry lookup | Future authority-bundle vectors mutate predicate ID, language, coordinate, parser/scope/temporal linkage fingerprints, policy content, bundle order, omission, duplicate coordinate, or digest spelling; all reject. |
| Equality joins | Route-set source ID and parent source digest authority match; projected tuples are exact per-row artifact sets ordered by `(operation_id, proposal_id, segment_id, route)`; and each artifact has exactly one coordinate-matching selection with exact request dependency and selected-policy fingerprint | Future focused source-alignment validator matrix: missing, unreferenced, duplicate coordinate, duplicate digest, cross-coordinate, request-input/policy/temporal substitution, bundle/artifact cardinality mismatch, and digest-only substitution reject; no artifact may satisfy multiple distinct rows. |
| Retained evidence manifest | `SourceNormalizationResult` owns one complete graph-free retained-evidence inventory with exact selection linkage and one non-circular publication coordinate; aligned tuples are verified subsets | Future manifest vectors mutate retained-entry order, retention disposition, selection linkage, omission, duplicate entry, duplicate digest, wrong fence, wrong expected generation, foreign-generation attestation, or manifest digest; all reject. |
| Retry and replay | Recovered alignment reloads and recomputes all exact source-normalization inputs, typed selections, policy-content authorities, retained-evidence manifest members, and equality joins without live lookup | Future replay matrix persists exact codec/store bytes, then reopens with fail-fast sentinels. Identical request/result bytes accept; substituted analysis bundle, temporal resolution, selected policy, selection/bundle, language-policy authority bundle, manifest, source, route, consensus dependency, foreign generation, lost acknowledgement, missing/extra/partial retained evidence, and substitution-before-output/write all fail before reuse. |
| Checkpoint subtype closure | Normalization checkpoint is one real pre-planning atomic generation containing exactly one matching pre-planning progress member and the request/result/manifest/bundle/artifact closure | Future real-store matrix covers success; missing/wrong/duplicate or planned progress; planned state rejection; subtype-only-kind admission; forbidden/extra kind; missing/substituted request; required-digest closure; stale coordinate/generation; lost acknowledgement; and reopen under fail-fast providers. |
| Semantic policy-key matrix | Every supported subject kind has exact sealed key/cardinality and policy-rule behavior without a live lookup | Future codec/store/reopen matrix covers fact, distinct/equal-predicate corrections, retraction, multi-role action state, and identity; swapped/missing/duplicate bindings reject, while a governing policy-rule difference deterministically reproduces stable versus terminal-unaligned bytes. |
| Operation-subject derivability | One exact graph-free subject is derivable from each retained proposal operation member by `(kind, source_id, source_digest, proposal_id, proposal_digest, segment_id, route, proposal_member_index)`, where `proposal_digest` is the content address of the exact validated proposal bytes and the matching outcome digest must equal it | Future fixed vectors and validator tests mutate source identity, source digest, proposal bytes, proposal digest, proposal member index, array membership/order, omitted field, extra field, alias, inferred field, legacy/predecoder form, digest spelling, cross-context substitution, forged duplicate `operation_id`, and `operation_id`; each mutation rejects or yields a different independently computed subject or operation ID as applicable. |
| Normalized proposal closure | Every retained validated proposal byte participating in `proposal_digest` and `proposal_member_index` is owned by one closed provider helper or `Proposed*` contract with exact quote-to-span/reference mapping and explicit duplicate-free tuple keys | Future fixed vectors mutate one nested normalized helper/member field at a time, including `ProposedEntityObject`, `ProposedLiteralObject`, `logical_action_digest`, `execution_branch_digest`, `temporal_qualifier_spans`, top-level duplicate member digests, same-proposal selector normalization, and split-only reference assignment rules; one provider quote resolution; one local-ID reference target; one same-segment constraint; one branch pair; one identity assignment; or one tuple order and require rejection or the exact affected digest changes only. |
| Policy-leaf closure | Every field retained inside `PredicateSemanticPolicy`, `SemanticScopePolicy`, and the minimal consensus-policy rule records has one exact closed leaf owner | Future fixed vectors mutate one `ConstructionFamily`, `UdPathPattern`, `QuotationBoundaryPolicy`, or `UdRoleSchema` leaf and require the exact containing policy fingerprint to change while unrelated consensus-rule or sibling policy fingerprints remain byte-stable. |
| Canonical encoding order | CTV map-member order canonicalizes; only semantic tuple reordering rejects | Future fixed-vector test: permuted map members yield identical canonical bytes/digest for `OperationAlignment`, `ConsensusPolicySelection`, and `PreAlignmentSemanticOperationSubject`; permuted selection, parser, scope, temporal, or normalized semantic tuples reject. |
| Provider boundary | Provider-local proposal bytes normalize deterministically into one sealed `SemanticProposal`; provider-local identifiers never survive into persisted semantic identity; byte-different valid provider permutations collapse to one canonical sealed proposal | Future boundary vectors replay identical provider bytes and byte-different valid provider permutations through normalization for byte-identical normalized bytes/digests/subjects, then mutate one local lookup, quote-resolution, discriminator, abstention flag, or canonical-order input and require deterministic rejection or the exact affected normalized digest delta only. |
| Coverage and grouping | Covered predicates name the complete exact row set; source dependency groups cover each operation row exactly once | Future focused coverage/grouping matrix: omit, duplicate, swap, or orphan a row and require non-acceptance. |
| Isolation | No graph/capability/plan/lease/provider-local coordinate can enter the row, selection, bundle, or their preimages | Static contract/constructor audit plus negative decoding vectors; no graph-bound dependency or live policy lookup is introduced. |
| Proposal attempt two-phase authority | Exact request bytes and call-known identity are durably published before inference/transport; exact response bytes and only a later final record may satisfy an outcome; the run retains complete final-attempt history and every proposal binds the exact final attempt that deterministically produced it | Persist and reopen request/identity before any fake-provider call; crash before/after call; retry with the next contiguous attempt number; persist response/final bytes before validation; select only the last final attempt while retaining predecessors; reject identity-only promotion, cross-identity finalization, request/response/status substitution, history omission, duplicate divergent final bytes, same-number retry, proposal/attempt status mismatch, or proposal bytes not reproduced from the selected persisted response. |
| Attempt atomic recovery | The progress record that first references request/identity or response/final-attempt bytes is in the same atomic generation; acknowledged bytes are replay authority | Real-store lost-ack and reopen tests for both publications with provider fail-fast sentinels; recompute byte and artifact digests, resend only exact persisted request bytes with the persisted idempotency key, and reject partial member, stale generation, foreign fence, unacknowledged response, alternate request bytes/digest, or failed-status presence mismatch. |
| Language-neutral parser leaves | Every token/span/feature/arc/mention/clause reference is source-local, canonical, closed, and syntactic-only | Independent CTV vectors plus mutations of offsets, mapping proof, token/MWT coordinate, feature order/name, root cardinality, arc endpoint, mention head/kind metadata, clause parent cycle/containment, quotation reference, argument reference, and semantic-field injection. |
| Step-4 aggregate closure | Parser, event, and temporal artifacts are exact route/lane/per-lane-manifest bijections with independently recomputable content addresses and exact total status tables | Per-contract strict codec/domain/reopen/rollback vectors; exhaustive ordered status combinations; two-segment selected/blocked fixtures with four fail-fast adapter sentinels; two selected languages with distinct detector/resolver manifests and empty results; remove, duplicate, reorder, cross-route, cross-source, swap language/lane/resource/selected-manifest/artifact digest; forge aggregate addresses or inject a live parser object; every mutation rejects or yields the exact new address. |
| Temporal normalized value closure | Candidate value shape, exact source text, authenticated reference basis, basis-sensitive candidate identity, canonical value-and-basis uniqueness, ambiguity, and lane outcome agree | Absolute instant/interval/duration and relative-reference vectors; null/wrong reference, locale/timezone/DST boundary, exact-text mismatch, invalid interval shape, duplicate or same-value/same-basis/different-rule candidate, ambiguous-span omission/extra, and resolver-manifest substitution reject; equal interval/text/span under distinct event-time and document-time bases remains byte-distinct through reopen, candidate-ID joins, attachment, and downstream provenance. |

Evidence maturity is `specified` for the canonical design. No production,
focused-test, generated-authority, CI, or operational evidence is claimed by
this design-only revision.

## Blockers And Limits

User approval to broaden this linked design operation has been obtained and the
adjacent normalized proposal/policy leaf contracts are now defined. This
WorkPlan was reopened for the approved crash-safe proposal-attempt identity and
missing Step-4 linguistic contract closure. No implementation or CI evidence
is claimed for the reopened design delta.

## Superseded Final Remediation Freeze

- Reconciled the final policy-key, policy-fingerprint, strict-codec, atomic
  hierarchy, and persisted-replay proof findings as `Not applicable` /
  `changes_required` contract-conformance work in the review table.
- The final atomic hierarchy is `AtomicGenerationRequest` ->
  `SourceCheckpointAtomicWriteRequest` ->
  `SourceNormalizationAtomicWriteRequest`; it preserves every existing member
  kind and adds only the eight normalization member kinds, including the exact
  originating request.
- The candidate remains design-only. Scoped diff and identity-hygiene checks
  pass; neither proves production behavior or persistence replay.
- The fresh immutable candidate identity is recorded in the coordinator handoff
  after the final no-edit verification command. No edits may follow that
  command before independent review.

## Superseded Next Action

Return control to `docs/work/semantic_ingestion/implementation.plan.md` and
implement the approved strict contracts, codecs, normalization boundary, and
pre-planning atomic publication closure.

## Outcome And Retrospective

Approved for implementation. The final frozen candidate at design SHA-256
`efdf367d15d66f35cf0d18dbba01d566d2cb1175cb3d907e90eaf26cc5008290`
preserves the exact eight-field receipt and ten-field selection wire, closes
normalized proposal and per-operation policy authority, and defines the
pre-planning-only atomic replay closure. Independent specification,
correctness, and test reviewers reported no approval-relevant findings; this
is design evidence only and makes no production claim.

The final identity includes the externally approved
`SemanticScopePolicy.policy_fingerprint` CTV rule and removes Python defaults
from the two documented checkpoint discriminator fields. Those fields remain
required strict-wire literals, matching the no-default compatibility rule and
the declarative CTV authority grammar.

On 2026-08-05 the user approved the smallest correction for the previously
undefined proposal-attempt identity: `SemanticProposalAttempt` gains one
required trailing `attempt_digest`, using
`memorii.semantic-ingestion.semantic-proposal-attempt.v1` over canonical CTV
of every other declared attempt field. `SegmentProposalOutcome` copies that
digest exactly; the run enforces the attempt/outcome coordinate bijection.

That one-record correction is superseded. Independent review proved that it
cannot satisfy the existing requirement to persist attempt identity before a
paid provider call because response/status fields are unavailable pre-call.

## Reopened Design Delta (2026-08-05)

- The user approved a two-record crash-safe boundary:
  `SemanticProposalAttemptIdentity` is persisted before local inference or
  remote transport, and final `SemanticProposalAttempt` binds that identity to
  response/status/diagnostic evidence before downstream processing.
- The pre-call identity includes the exact serialized request digest. A retry
  after an identity-only crash uses a new monotonic attempt number and a new
  identity; it never treats the stranded identity as successful evidence.
- `SemanticProposalRun` and `SourceTraceArtifact` retain final attempts only;
  identity-only records remain checkpoint-history authority and cannot satisfy
  an outcome.
- The same audit found undefined language-neutral parser leaves and missing
  content-address rules for Step-4 analysis/event/temporal artifacts. This
  delta owns their exact closed schema, lifecycle, and verification contract.

## Superseded Next Action

Obtain the external decision on the prompt-catalog modality projection and
child-segment governance model, then revise the canonical design as one bounded
production-feasibility delta before implementation resumes. Superseded by the
two user decisions and the candidate design delta recorded below.

## Reopened Production-Feasibility Gap (2026-08-05)

- Production implementation proved that `SemanticProposalRequest` references
  `PredicatePromptContract`, but no governing document or production owner
  defines its fields, digest, ordering, or catalog fingerprint owner.
- Independent architecture review recommends a strict
  `PredicatePromptContract` plus capability-bound `PredicateProposalCatalog`.
  The minimal prompt-safe projection carries predicate ID, description,
  entity/literal argument shape, literal type, and supported commitments. It
  excludes source-modality eligibility and all conflict, trust, temporal,
  scope, graph, and lifecycle policy.
- Production preparation mapping also proved that Step 2 permits one projection
  segment to split into multiple child execution segments, while the current
  prepared-source, attempt, proposal, run, span, governance-carrier, and route
  validators require one identical segment ID. Any split is therefore
  unrepresentable.
- The recommended complete correction distinguishes child execution segment ID
  from parent projection/governance segment ID throughout the strict persisted
  request/attempt/proposal/run family and retains an explicit total
  child-to-parent mapping. The smaller alternative is to make oversized inputs unsupported in
  v1, contradicting the existing bounded-splitting behavior.
- No implementation may invent either persisted contract. The active design
  operation is reopened only for these two coupled production-feasibility
  decisions; prior accepted Step-4 and attempt evidence remains valid where
  unaffected.

## Approved Production-Feasibility Decisions (2026-08-05)

- The user approved the minimal capability-bound predicate prompt catalog.
  Predicate-local modality is represented by canonical
  `supported_commitments`; source `SourceModality` eligibility remains in
  source governance and is not copied into prompt vocabulary.
- The user approved complete child-segment support. Persisted contracts will
  distinguish each child execution segment from its parent projection and
  admission-governance segment, retain an explicit total child-to-parent mapping,
  and reject cross-parent substitution. Oversized input is not made
  unsupported merely to avoid this correction.
- These decisions authorize a bounded canonical design revision and independent
  delta review. They do not authorize changes to downstream graph semantics or
  reuse of current mutable policy as replay authority.

## Candidate Production-Feasibility Delta (2026-08-05)

- Canonical changed surface: `docs/design/semantic_ingestion_architecture.md`
  Sections 3.9, 4.2, 4.3, and 4.4. This WorkPlan records the decision,
  ownership, evidence maturity, and review boundary; no production, test, or
  generated artifact changes in this design operation.
- `PredicatePromptContract` and `PredicateProposalCatalog` are strict closed
  CTV wires. They bind one release-safe predicate vocabulary to the selected
  `CertifiedProposalCapability`; catalogs are release-time projections of
  `PredicatePolicy` prompt fields and certified `PredicateSemanticPolicy`
  commitments, without a live registry lookup. Source modality and all
  downstream conflict/trust/temporal/scope/lifecycle/graph policy remain out of
  the prompt authority.
- `SemanticProposalRequest.predicate_catalog` is the catalog, not a bare
  tuple. The capability's supported catalog fingerprint, request catalog,
  registered prompt, proposer manifest, and selected route bind one release.
  New request/attempt/proposal/run/Step-4 codecs validate the complete chain;
  strict-v1 rejects old bytes, has no upcast, and unshipped rollback removes
  writers/readers/registrations rather than accepting a legacy form.
- `SegmentLanguageRoute` now carries required
  `parent_projection_segment_id`. The execution child is `segment_id`; the
  parent equals governance, span projection, and segment-artifact projection
  coordinates. Carrier sets and `GovernanceCarrierArtifact` remain immutable
  parent-keyed. Their closure is UNIQUE-PARENT membership under a total
  child-to-parent mapping: children may share a parent and every parent is
  covered. Route-set order is prepared source order, never inferred from child
  ID lexical order.
- Required design evidence is specified, not implemented: independent CTV
  vectors/mutations for both contracts, equality-chain and live-lookup
  sentinels, unsplit and multi-child parent closure, cross-parent/sibling
  substitutions, codec/replay recovery, strict-v1 old-byte rejection, and
  rollback removal. Existing implementation evidence proves neither this delta
  nor a shipped compatibility claim.

## Current Exact Next Action

Return control to `docs/work/semantic_ingestion/implementation.plan.md` and
implement the approved prepared-source, predicate-catalog, parent/child,
proposal-execution, Step-4, and replay contracts at canonical design SHA-256
`495e3c5cd95ca68eb2f3bca5c47870092c148d785fc57688127e9802ba93ddae`.

## Text-Preparation-Policy Remediation Freeze (2026-08-05)

- Git HEAD: `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`.
- Canonical design SHA-256:
  `495e3c5cd95ca68eb2f3bca5c47870092c148d785fc57688127e9802ba93ddae`.
- Pre-freeze design WorkPlan SHA-256:
  `28ec83a3c7fca098f101c538365e9c848a0863859b5fc0ce9ac2d8f2f613ce6d`.
- M3 packet SHA-256:
  `7b479b5f123ac19624aca0fb886d289ccca48994c7de9cdb24940b0409782e5c`.
- Resume packet SHA-256:
  `8f68970df2df99974eac18fa266f3e8aee0f27df07a451a90e53809bc49d2914`.
- Clean-room compiled-authority SHA-256:
  `4b59acfff5aa144ca977bae8011ab65e3e7cd54e25104e88eaaef8d4cad128f6`.
- Prompt-manifest validation/self-test, identity hygiene, opaque-policy audit,
  global post-Step-2 span audit, and scoped diff hygiene pass. Review is
  limited to DREV-024 and direct regressions from its closed policy owner.

## Final Production-Feasibility Design Outcome (2026-08-05)

Approved for implementation at canonical design SHA-256
`495e3c5cd95ca68eb2f3bca5c47870092c148d785fc57688127e9802ba93ddae`.
The final whole-design and bounded remediation reviews accepted the
capability-bound predicate catalog, exact catalog schema manifest, total
child-to-parent execution mapping, global post-Step-2 source-reference
invariant, complete prepared-source identity, and strict persisted
`TextPreparationPolicy` with no remaining confirmed finding. Manifest
validation/self-test, clean-room authority compilation, identity hygiene,
focused audits, Ruff, `py_compile`, and diff hygiene pass. This is design
evidence only; production, codec, persistence, test, CI, and operational
maturity belong to the linked implementation WorkPlan.

## Production-Feasibility Whole-Design Remediation Freeze (2026-08-05)

- Git HEAD: `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`.
- Canonical design SHA-256:
  `ceea4b698367a35f13e1297cf52879cb266a3f3d81da67f4d2d0c06e38f9286b`.
- Prompt-catalog manifest raw SHA-256:
  `57d3a0d7cf71198f838cbf71b694024f13cb558e1aff19623fe677d1a32567fa`;
  domain content address:
  `b135f05197acf3270c2200f2c7aca82a7790b26ff4ee6e356248c8494655a79b`.
- Manifest validator SHA-256:
  `c6074b123ac3a992ea437ba26bfe081c9f66872d678e9c4eb149bfab95bbd437`.
- Pre-freeze design WorkPlan SHA-256:
  `15f1c565068f6df2ea61d1d1199561b838cbd2413b71fd662d2ef4d1cc595106`.
- M3 packet SHA-256:
  `54412fd4a38acca921acdf5cd7560f0a1415da1dfd1daa481e1643123ca65508`.
- Resume packet SHA-256:
  `44a2898f8d734af8e6c0969670420ad9a9d449068f755578b7977a00092ac7ba`.
- Clean-room compiled-authority SHA-256:
  `8a330525183e5475d6305edfcaa9125fd748213dc655d819fbfc49eec45f7e85`.
- Manifest validation/self-test, Ruff, `py_compile`, identity hygiene, global
  post-Step-2 span audit, preparation-identity audit, and scoped diff hygiene
  pass. The only bare post-Step-2 projection spans are the two documented
  `PreparedSegment` structural construction fields. Review is limited to the
  three whole-design findings remediated in this round.

## Production-Feasibility Final Remediation Freeze (2026-08-05)

- Git HEAD: `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`.
- Canonical design SHA-256:
  `fbdd20c5b57a2766198ae46740b28412742db83a9a173194f9ac443431f63f93`.
- Prompt-catalog schema-manifest raw SHA-256:
  `3ff79f7b5a5cd87318d8375e41c00cc729e3138d7c211cfa9081565d413a0928`;
  domain content address:
  `d5c4cf1386f26f1cbb9140b24c5e466553794afaafe41d6f1dc9626aea1b1237`.
- Manifest validator SHA-256:
  `22c5e0c78d8a29fbe47a22b859db5ef229e7871fb9f06396f21401dd1561af6e`.
- Pre-freeze design WorkPlan SHA-256:
  `209ad2596fa8fb27d8eb4c0d05a4d95dae7a15565e7f9fb05a4b6083bd4a6edf`.
- M3 packet SHA-256:
  `7091eb2bc8d0c0c7e811ee03be8b09d3ae0699a8cff89064bff096597eef5234`.
- Resume packet SHA-256:
  `c9cfc46072bb70949750d93c69f4dffb8871438faed36ea3356804074ba3bd9e`.
- Clean-room compiled-authority SHA-256:
  `11009d1d553eeefd5bcb1cde0256866b9f95c8367ea0018797e8224a304b218e`.
- Manifest validation and self-test, Ruff, `py_compile`, identity hygiene,
  copied-span/schema/preimage audits, and scoped diff hygiene pass. Review is
  limited to the three exact residuals from the preceding targeted round. No
  edit may follow before reviewer reconciliation.

## Frozen Review Remediation (2026-08-05)

| Finding | Product priority | Approval disposition | Finding type | Disposition |
| --- | --- | --- | --- | --- |
| Any ordinary Step-3 request/attempt/replay could substitute unaddressed request bytes, while catalog schemas had no runtime-independent owner. | P2 | changes_required | persisted contract / replay | Confirmed and remediated: trailing `semantic_request_fingerprint`, closed CTV schema-manifest fingerprints for both catalogs, release equality, renderer/decoder recanonicalization, and replay recomputation are now explicit. This affects every catalog-bearing proposal request. |
| A split prepared source could conflate child-keyed run members with parent-keyed governance/admission carriers. | P2 | changes_required | runtime behavior / architecture | Confirmed and remediated: child route/attempt/proposal/outcome bijections are distinct from unique parent carrier equality, with a total surjective child-to-parent inverse. Split sources are an approved Step-2 path, not an unsupported edge case. |
| A multi-child Step-4 event or temporal candidate could retain a bare projection span from a sibling parent. | P2 | changes_required | provenance / replay | Confirmed and remediated: all candidate and copied consensus/attachment spans now use `SourceSpanReference` with parent/artifact/proof/text closure. This affects every routed event/temporal candidate in a split source. |
| The verification matrix did not prove multi-predicate catalog replay or a two-parent/three-child split topology. | Not applicable | changes_required | verification | Confirmed and remediated as specified evidence: real renderer/transport/reopen/replay and `P0->{C0,C1}`, `P1->{C2}` mutation families are required before implementation approval. |
| Attribution and temporal evidence retained three final bare projection-span bypasses, and the catalog schema manifest was prose rather than reproducible bytes. | P2 | changes_required | provenance / persisted contract | Confirmed and remediated: attribution bearer plus temporal candidate/assessment spans now join exact upstream source references; the checked-in closed manifest and validator pin all catalog/embedded schemas, token vocabulary, artifact digest, and per-catalog schema fingerprints. These affect split-source Step-4/5 replay and every catalog-bearing request. |
| Renderer and split-topology proof text did not require every catalog field or an independent preparation-fingerprint oracle. | Not applicable | changes_required | verification | Confirmed and remediated as specified evidence: literal entity/literal rendering, poisoned-registry zero-call replay, and P0/P1 clean-room CTV mutation oracle are required. |
| Parent-sensitive spans remained bare projection spans in NLI, assessment, temporal attachment, and certified-time paths. | P2 | changes_required | provenance / replay | Confirmed and remediated by the global post-Step-2 `SourceSpanReference` invariant, explicit structural-only exceptions, exact upstream equality, and P0/P1 sibling-parent mutations. These paths are exercised by every semantic assessment following preparation. |
| Catalog literal-domain tokens could be exchanged without an exact manifest grammar check. | P2 | changes_required | persisted contract / activation | Confirmed and remediated: four distinct literal-domain tokens, exact expected record-field maps, per-domain self-test mutations, and release model-grammar comparison now reject a semantic runtime change without a manifest/fingerprint change. |
| Prepared source bytes lacked a first-class preparation-policy identity propagated through all downstream carriers. | P2 | changes_required | persisted contract / replay | Confirmed and remediated: `PreparedSource` now owns the closed prepared-source CTV address and policy fingerprint; request, attempt, proposal, run, analysis, consensus, NLI, and normalization joins retain exact equality. The approved split-source execution path requires this identity. |
| DREV-024: preparation policy was an opaque copied fingerprint, permitting identical output bytes to conceal a changed segmentation policy. | P2 | changes_required | persisted contract / replay | Confirmed and remediated: `TextPreparationPolicy` is the one strict v1 owner, embedded byte-for-byte in request and prepared source; prepared-source identity includes the full record. Fixed algorithm literals, canonical languages, no-output-change mutations, strict codecs, rollback, and persisted replay are now specified. This affects every prepared semantic source. |

The candidate remains design-only. The clean-room compiler and document hygiene
checks establish syntax/authority hygiene, not implementation, codec, vector,
or operational evidence.

The new canonical artifact is
`docs/design/semantic_ingestion/prompt-catalog-schema-manifest-v1.json`
(raw SHA-256 `57d3a0d7cf71198f838cbf71b694024f13cb558e1aff19623fe677d1a32567fa`,
domain content address
`b135f05197acf3270c2200f2c7aca82a7790b26ff4ee6e356248c8494655a79b`).
`docs/design/semantic_ingestion/validate_prompt_catalog_schema_manifest.py`
is the deterministic design-only validator/self-test owner; its raw SHA-256 is
`c6074b123ac3a992ea437ba26bfe081c9f66872d678e9c4eb149bfab95bbd437`.

## Production-Feasibility Remediation Freeze (2026-08-05)

- Git HEAD: `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`.
- Canonical design SHA-256:
  `c4b2e048a0ef9e7bd09277f8708a0051ef3d3f777ce46d2b0b0bfdc483671567`.
- Pre-freeze design WorkPlan SHA-256:
  `9d0d0820ad42d8b531c1eb75e626d167b9e9335c54945fbbe8cdb2a3791b7f54`.
- M3 packet SHA-256:
  `833f857e155d2ae72ccddabf6a5ae2d3002e720d8022d4a76eec0bcd0e353155`.
- Resume packet SHA-256:
  `31358625ce6af91984ac924a426ba43dceb63948e4a0178a6b1f38cae370e1d4`.
- Clean-room compiled-authority SHA-256:
  `48f6f021313c91a029dd070c1569de4c3ec480a5b1882611c940cc1b0fb957ff`.
- Identity hygiene, no-bare-Step-4-span audit, stale-cardinality/contract
  wording audits, and scoped diff hygiene pass. Delta review is limited to the
  four reconciled finding clusters above. No edit may follow before the
  targeted reviewers report against this exact identity.

## Production-Feasibility Candidate Freeze (2026-08-05)

- Git HEAD: `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`.
- Canonical design SHA-256:
  `bba560b52b6678eadac9416431006668aca31e0ecc0deb952f81f3e989d7a6ca`.
- Pre-freeze design WorkPlan SHA-256:
  `1470d2d56c31013c97d7b07e7add894c8d744668b577b39b320986ac5253522c`.
- M3 packet SHA-256:
  `ca753962181e41603a92b389d39c6d76a312442ee2ffc3eff2931f37282ee56d`.
- Resume packet SHA-256:
  `341a97de6c3428eef9139fc9347a7c9f1dba26354dd21ce1132d60db629a52c1`.
- Clean-room compiled-authority SHA-256:
  `02870b0dab4dd1037deeb9782efbdc3d5f992638a3fa54dbfe27df398d65f73b`.
- Identity hygiene, targeted undefined/bare-contract audits, and scoped diff
  hygiene pass. Review scope is exactly the predicate prompt/catalog authority
  and total child-to-parent execution mapping. No edit may follow this freeze
  before independent review reconciliation.

## Reopened Review Reconciliation (2026-08-05)

All reported findings were confirmed and remediated as one coherent contract
batch:

- `P2` / `changes_required` / failure recovery: the run now retains the complete
  ordered final-attempt history and each outcome selects only the last attempt.
- `Not applicable` / `changes_required` / replay conformance: exact request and
  response bytes now have closed persisted artifacts and atomic reopen rules;
  response presence makes every final status representable.
- `P2` / `changes_required` / resource binding: every Step-4 result now retains
  and equals its lane-specific selected manifest and selected language,
  including empty detector/resolver results.
- `P2` / `changes_required` / runtime behavior: all linguistic, event, and
  temporal aggregate statuses now have exact total functions, including
  partial results.
- `P2` / `changes_required` / temporal conformance: the canonical
  value-and-basis key rejects duplicates while preserving equal values under
  distinct authenticated bases.
- `Not applicable` / `changes_required` and `P2` / `changes_required` /
  verification: the matrix now requires per-contract strict codec/reopen/
  rollback vectors, full status tables, four blocked-route fail-fast adapter
  sentinels, identity-first crash/retry history, and the equal-value/
  different-basis positive case.

No unsupported or duplicate finding remains. This remediation materially
changes the reviewed candidate and therefore requires a fresh freeze and
targeted delta review.

## Reopened Remediation Freeze (2026-08-05)

- Git HEAD: `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`.
- Canonical design SHA-256:
  `7eb110ba60a213d3ece62d56450167b9553851dd87289eee22f2c4be3ebb1e53`.
- Scoped design-and-WorkPlan binary-diff SHA-256 before this freeze record:
  `32aaba49616682128165927aef8a5bfe31334d74d8aa96f6f72ba37448ecba71`.
- Git-status SHA-256:
  `3d234e26e05f2bff74eedf5744fe5c4019e62c9e5e3c542ad8d447b739653196`.
- Clean-room compiled-authority SHA-256:
  `2c8f965be96fda483ab16dc6186b6fb292951d44dedb849e2deea61832be7621`.
- The clean-room CTV compiler and scoped `git diff --check` both exit zero.
- Delta review scope is exactly the six reconciled root causes above. No edit
  may follow this freeze until targeted review completes; a confirmed new
  issue requires another recorded candidate.

## Reopened Delta Review Reconciliation (2026-08-05)

- The test reviewer accepted all six verification remediations with no
  residual finding.
- Specification review confirmed the manifest/language and aggregate-status
  roots but found that source-level singular detector/resolver manifest fields
  could not represent mixed-language route sets. This `P2` /
  `changes_required` persisted-contract finding is confirmed; the exact
  selected manifest is now retained per lane outcome, including empty results.
- Specification review also found that temporal candidate identity omitted the
  authenticated value basis even though downstream joins use candidate IDs.
  This `P2` / `changes_required` temporal-provenance finding is confirmed; the
  identity preimage now includes the complete value-and-basis key.
- Correctness review confirmed the original three roots but found that a
  normalized proposal did not identify or reproduce from its final attempt.
  This `P2` / `changes_required` provenance finding is confirmed;
  `originating_attempt_digest` and exact persisted-response normalization now
  close the proposal/attempt/outcome join.
- These three related joins form one bounded second remediation. The prior
  remediation freeze is superseded for approval purposes; its accepted test
  evidence remains valid for unchanged verification clauses.

## Reopened Second Remediation Freeze (2026-08-05)

- Git HEAD: `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`.
- Canonical design SHA-256:
  `fa32e2246da8188e7899cc033892b9c396a1805761d0d041e4fd10eadf6a4488`.
- Scoped design-and-WorkPlan binary-diff SHA-256 before this freeze record:
  `0b02700b768cb7fc574f6d821e9dc55f3736e7893f3f264146b610c8b24511d2`.
- Git-status SHA-256:
  `3d234e26e05f2bff74eedf5744fe5c4019e62c9e5e3c542ad8d447b739653196`.
- Clean-room compiled-authority SHA-256:
  `7589a3960c13384bb3aac23823ea04244432e69cd6a565077a58d950c8f63a27`.
- The clean-room CTV compiler and scoped `git diff --check` both exit zero.
- Final targeted delta scope is the per-route selected-manifest witness,
  basis-sensitive temporal candidate identity, and exact originating-attempt
  proposal join. No edit may follow until specification and correctness review
  accept or identify a new confirmed issue.

## Reopened Candidate Freeze (2026-08-05)

- Git HEAD: `2a7a55e2f1ea265a5c7f824db1a38ce07cd9fb93`.
- Canonical design SHA-256:
  `e18d3a4a19cd220ce82bb1ff302d23d2c30ad15a4efc51bed3b3139323984053`.
- Scoped design-and-WorkPlan binary-diff SHA-256 before this freeze record:
  `69b90ac4e8145f7f2461401222b493cbeaca304572ebeb1cfa3866f0192c57fe`.
- Git-status SHA-256 from `git status --porcelain=v1 | shasum -a 256`:
  `3d234e26e05f2bff74eedf5744fe5c4019e62c9e5e3c542ad8d447b739653196`.
- The clean-room CTV reference compiler accepted the canonical design and
  registry, and `git diff --check` exited zero.
- Review scope is the complete reopened delta: the pre-call
  `SemanticProposalAttemptIdentity`, post-call `SemanticProposalAttempt`,
  their crash/retry/atomic replay lifecycle, and the closed Step-4
  parser/event/temporal leaf and aggregate schemas with exact CTV addresses.
- No design or WorkPlan edit may follow this freeze until all three reviewers
  report against the exact design and WorkPlan hashes supplied by the
  coordinator. Any confirmed correction requires a new freeze identity.

## Reopened Design Outcome (2026-08-05)

Approved for implementation at canonical design SHA-256
`fa32e2246da8188e7899cc033892b9c396a1805761d0d041e4fd10eadf6a4488`.
The full specification, correctness, and test review followed by bounded delta
reviews converged with no remaining confirmed finding. The clean-room CTV
compiler and scoped diff hygiene pass. This is design evidence only; production,
codec, persistence, focused-test, CI, and operational maturity remain to be
established by the implementation WorkPlan.
