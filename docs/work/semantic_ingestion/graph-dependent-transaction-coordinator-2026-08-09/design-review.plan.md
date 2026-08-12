# Graph-Dependent Transaction Coordinator Design Review

- Work ID: semantic-ingestion-graph-dependent-transaction-coordinator-design-review-2026-08-09
- Work type: investigation
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-08-09
- Last updated: 2026-08-09
- Review mode: full
- Target design: `docs/work/semantic_ingestion/graph-dependent-transaction-coordinator-2026-08-09/design.plan.md`
- Target SHA-256: `2a362762be83c3c1d0d73a74d2c8b1b1a2c80af8096093e623ce7c6e0471e8a9`
- Canonical architecture: `docs/design/semantic_ingestion_architecture.md`
- Architecture SHA-256: `786c9f22c33db76bb16518cfa6da57ae95084b126e36d6462d6cd122d75fa17e`
- Approved receipt design: `docs/work/semantic_ingestion/operation-alignment-schema/design.plan.md`
- Receipt design SHA-256: `ea34c1ae11c7507896cb9adf9844a9f7916594f43d7acf2f4dab982010a8b078`
- Implementation baseline: Git HEAD `4691c0374b3b01617a6a50fd83d4e3ff8a61aa84`; dirty-tree status SHA-256 `deb26709863fc9216e90598dcf06ecbbc83eea71369d487208cf54a9782ea930`; binary-diff SHA-256 `e7fa49b2c2bbb3d732bf0226c85196868cfb8389005ee55b1410a1ea18328983`
- Report target: `docs/reviews/semantic-ingestion-graph-dependent-transaction-coordinator/full-review-2026-08-09.md`

## Objective

Independently determine whether the M3.1 design is complete, internally
consistent, feasible, production-reachable, transactionally safe, and
verifiable enough to begin implementation without hidden semantic decisions or
another schema-only approval gap.

## Completion Contract

Complete when the frozen target is reviewed across all review lanes; the
requirements and authority chain are independently reconstructed; specification,
correctness, and test reviewers finish independent passes; every finding is
validated and classified; one immutable validated report records the outcome;
and any required changes are handed back to the linked design WorkPlan without
editing the reviewed baseline.

## Included Scope

- GTC-R01 through GTC-R13 and their acceptance criteria.
- Steps 5--8 source normalization, graph snapshot/reconciliation, planning,
  attempt/authorization/lineage, CAS/retry, terminal binding, restart/replay,
  production reachability, observability, and bounded resources.
- Existing canonical contracts, production composition, repositories, tests,
  gates, evidence maturity, identity hygiene, and implementation slicing.
- The complete adjacent authority chain and bypass/fallback family.

## Excluded Scope

- M4 conflict presentation and clarification semantics.
- Persistence performance optimization and PR-gate duration.
- New grammar, learned-model behavior, retrieval, ranking, external signing,
  and unrelated dirty-tree changes.
- Editing the target design, canonical architecture, production code, or tests.

## Governing Sources

Apply `AGENTS.md` precedence. Primary sources are
`docs/design/memorii_spec.md`, `docs/design/memorii_storage_details.md`,
`docs/design/event_model.md`, `docs/IMPLEMENTATION_RULES.md`, and
`docs/design/semantic_ingestion_architecture.md`. The approved minimal
`OperationAlignment` decision is binding. Production and tests are reality and
feasibility evidence, not authority over conflicting design semantics.

## Review Lanes

1. Problem, scope, requirements, actors, and measurable success.
2. Internal consistency, typed contracts, ownership, authority, and identity.
3. Data lifecycle, atomicity, CAS, retry, replay, recovery, and partial commit.
4. Security, failure, operability, migration, rollback, and resource bounds.
5. Verification, evidence maturity, production-entrypoint bindings, and
   implementation readiness.

## Frozen Baseline And Readiness

The review target is the exact design SHA above. The design and architecture
must not change during independent review. The candidate is intentionally a
design-plan candidate rather than an implementation candidate: production
bindings may be recorded as absent when the design specifies a determinate
owner and fail-closed path. Reviewers must distinguish a known implementation
gap from a missing design decision.

The current production preflight has been coordinator-validated:

- ordinary root: `ProviderMemoryService.sync_event` ->
  `ProviderIngestionCoordinator` -> semantic pipeline ->
  `SemanticTerminalPersistenceService.persist`;
- four production persistence callsites omit `transaction_group_plan`;
- no production constructor/consumer exists for the complete
  `SourceProposalAlignment` -> graph attempt -> authorization -> lineage chain;
- the atomic transaction-plan repository exists but is not a derivation owner;
  and
- the legacy committing path must not be treated as satisfying graph-bound
  reachability.

## Delegation And Cost Ledger

| Reviewer | Role | Scope | Status |
| --- | --- | --- | --- |
| specification | `spec_auditor` / Terra | reconstructed requirements, contradictions, undefined terms, scope and acceptance | complete; changes required |
| correctness | `correctness_reviewer` / Terra | architecture, feasibility, transactions, concurrency, recovery, security and integration | complete; changes required |
| verification | `test_reviewer` / Terra | evidence matrix, attack families, CI/gates, failure signals and maturity | complete; changes required |

The reviewers receive the same frozen baseline and do not see each other's
findings before completing. Earlier Spark maps are advisory; reviewers must
challenge the coordinator-validated production binding without repeating
undirected mapping.

## Known Constraints

- The shared tree is dirty; the three content-addressed design inputs above are
  frozen for this review.
- The broader WorkPlan split manifest is stale due earlier process/plan edits.
  Review whether that is a design-approval conformance issue, but do not treat
  it as product behavior or silently refresh it in this read-only operation.
- No performance command is required or authorized by this review.

## Exact Next Action

Hand DREV-001 through DREV-006 from
`docs/reviews/semantic-ingestion-graph-dependent-transaction-coordinator/full-review-2026-08-09.md`
to the linked `build-design` operation as one coherent authority-boundary
remediation. Do not edit this frozen review or begin implementation. Because
the required corrections materially affect composition, transaction ordering,
migration, security, and resource-policy contracts, freeze a new candidate and
run a fresh full review afterward.

## Outcome

Changes required. All three independent lanes completed against the unchanged
frozen SHA. Coordinator reconciliation confirmed six findings: canonical
ownership/composition; authorization-before-attempt ordering; replayable
resource limits; executable production-path evidence and CI ownership; strict
migration/rollback; and continuous tenant/caller authorization proof. No P1/P2
product defect was assigned because graph-bound behavior is not yet an
implemented supported path. All findings are determinate conformance or
evidence actions.
