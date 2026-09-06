# Behavioral Identity Enforcement

- Work ID: behavioral-identity-enforcement-2026-08-02
- Work type: testing
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-08-02
- Last updated: 2026-08-02
- Parent WorkPlan: docs/work/process/behavioral-identity-governance-2026-08-02/design.plan.md
- Related WorkPlans: None
- Canonical inputs: .agents/PLANS.md Identity And Coordinate Hygiene
- Expected outputs: field-aware repository checker, exact exception authority, mutation tests, required CI step, and workflow-structure proof

## Objective

Make planning/evidence-coordinate leakage fail deterministically before merge
without rejecting durable behavioral names, real protocol versions, or domain
terms such as `DeliveryCoordinate` and `BM25`.

## Completion Contract

Complete when one repository-owned checker scans Python paths/identifiers and
identity-bearing structured fields, workflows, registries, fixtures, and
generated JSON; exact exceptions are machine-readable and narrowly typed; the
fixed rejection and acceptance corpora pass; the current repository passes;
and a required static-analysis step plus workflow-structure test pin the exact
command.

## Scope

Included: checker, exception authority, unit/mutation tests, PR workflow step,
and static-tooling documentation. Excluded: product semantic changes and the
separate full semantic-ingestion historical identity migration.

## Constraints And Invariants

The checker is field-aware, not a blanket text search. It must distinguish the
domain concept `DeliveryCoordinate`, `BM25`, real `.v1` protocols, and shipped
migrations from planning-derived identities. Exceptions are exact occurrences,
never directory or whole-file exclusions.

## Identity And Coordinate Hygiene

| Surface | Proposed or existing identity | Class | Behavioral owner or protocol meaning | Retain, rename, migrate, or reject | Proof |
| ------- | ----------------------------- | ----- | ------------------------------------ | --------------------------------- | ----- |
| Checker module and CLI | `identity_hygiene` | behavioral identity | Enforces repository identity policy | retain | checker tests and PR command |
| Checker mutation suite | `test_identity_hygiene.py` | behavioral identity | Proves accepted and rejected identity families | retain | 148 checker tests |
| PR step | `Verify behavioral identity hygiene` | behavioral identity | Required pre-merge enforcement | retain | workflow-structure assertion |
| Scenario raw-member namespace | `governed-source-admission` | behavioral identity | Governed raw source closure | rename from planning-derived segment | scenario design mapping and checker |
| Scenario generation namespace | `writer-safe-preplanning` | behavioral identity | Writer-safe generation closure | rename from planning-derived segment | scenario design mapping and checker |
| Scenario closure format | `memorii-sia-scenario-first-closure-v1` | protocol identity | Scenario closure wire shape version | rename from planning-derived format | paired elaborators and validator |
| Provider envelope capture | `memorii.provider-envelope-capture.v4` | protocol identity | Retained provider compatibility capture | retain | real manifest and compatibility test |

The Work ID and numbered steps in this document are planning/evidence
coordinates and do not escape into the implementation.

## Sources Of Truth

The parent design and `.agents/PLANS.md` govern. Current Python ASTs, JSON/YAML
field ownership, and `.github/workflows/pr-gates.yml` define executable scope.

## Current State

The repository has a field-aware Python and JSON/YAML checker, exact
content-bound exception authority, fixed negative and positive corpora, and a
required PR static-analysis command pinned by a workflow-structure test. The
current tree passes the checker; focused lint, type, and test evidence is
recorded below. Specification, correctness, and test closure reviews are clean.

## Assumptions And Open Questions

Verified: PyYAML is a core dependency. Working assumption: Python AST plus
structured JSON/YAML traversal covers current executable identity surfaces. No
external decision is required.

## Milestones Or Experiments

1. Implement checker and exact exception schema. Status: complete.
2. Add positive/negative surface mutations and current-tree proof. Status:
   complete.
3. Add and pin required CI invocation and documentation. Status: complete.

## Progress Log

- 2026-08-02: Independent review proved documentation-only governance cannot
  prevent recurrence. Next action: implement the canonical field-aware checker.
- 2026-08-02: Implemented AST/structured-data scanning, exact typed exception
  authority with stale-entry rejection, 15 positive/negative tests, current-
  tree proof, required static-analysis step, and workflow command assertion.
  Next action: run focused and workflow verification at the declared cwd.
- 2026-08-02: Closed delta-review escapes for imports, f-strings, concatenated
  values, diagnostics, nested paths, generic identity fields, numeric planning
  fields, design generators, structured keys, and workflow job keys. Exceptions
  now require exact repository proof. Next action: obtain final independent
  closure review.
- 2026-08-02: Final review found constant-alias, enum, custom-raise,
  diagnostic-keyword, bare-ID, numeric phase/review, and proof-content gaps.
  Added local constant propagation, enum and all-raise contexts, the missing
  field/surface mutations, and content-bound traceability, compatibility, and
  rejection proofs. Next action: run final focused evidence and delta review.
- 2026-08-02: Delta review found lexical-lookalike and same-line proof
  collisions plus a transient missing-helper failure. Replaced proof-name
  heuristics with exact import-owner resolution, matched exact source columns,
  checked positional coordinates directly, and added all three regressions.
  Next action: obtain explicit clean closure from all three reviewers.
- 2026-08-02: Completed adversarial exception-proof closure for import
  shadowing, wildcards, pattern captures, module monkeypatching, and dynamic
  namespace mutation. The final checker suite, combined focused suite, and all
  three independent reviews are clean. Next action: none; completion contract
  satisfied.

## Evidence Log

- `148 passed` in the checker mutation and current-tree suite.
- `187 passed` for the checker suite, exact workflow command assertion,
  affected traceability contracts, and benchmark diagnostic contract from the
  declared `memorii/` cwd.
- Canonical checker command exits zero on the current repository.
- Focused Ruff passes and Pyright reports zero errors for the checker.
- All six repository skills pass the skill-creator structural validator.
- The scenario input's independent four-case semantic validator passes. The
  broader scenario authority suite remains blocked by the separate in-progress
  registry having fewer than its frozen 150 heading defaults; this is not an
  identity-checker failure.

## Decision Log

- Use AST and structured field ownership rather than substrings.
- Keep the checked-in exception authority occurrence-exact and content-bound;
  permit only genuine typed traceability, retained compatibility, or explicit
  legacy-rejection occurrences that the checker can prove in their canonical
  context.

## Review Log

Parent design review findings are recorded in its WorkPlan.

Final `spec_auditor`, `correctness_reviewer`, and `test_reviewer` delta reviews
all returned clean approval with no remaining actionable findings.

## Blockers And Limits

No blocker.

## Next Action

None. Completion contract satisfied.

## Outcome And Retrospective

The executable gate now rejects planning coordinates on every owned durable
surface while retaining real behavioral, protocol, migration, and typed
traceability identities. Exceptions are exact, stale-sensitive, bound to
canonical proof content, and fail closed under Python name shadowing or dynamic
namespace mutation.
