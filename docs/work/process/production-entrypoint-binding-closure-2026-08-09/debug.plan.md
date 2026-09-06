# Production Entrypoint Binding Closure

- Work ID: production-entrypoint-binding-closure-2026-08-09
- Work type: debugging
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-08-09
- Last updated: 2026-08-09
- Parent WorkPlan: None
- Related WorkPlans: `docs/work/semantic_ingestion/implementation.plan.md`
- Canonical inputs: `AGENTS.md`; `.agents/PLANS.md`; `.agents/skills/implement-design/SKILL.md`; repository reviewer skills; `~/.codex/agents/*.toml`; `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md`; `docs/design/semantic_ingestion_architecture.md`
- Expected outputs: reusable reachability ledger, candidate-freeze/closure gate, and workflow-skill enforcement

## Objective

Prevent implementation approval when an in-scope runtime or persistence
requirement has types and focused tests but no real production entrypoint that
can carry its required authority to a durable outcome.

## Completion Contract

Complete when the common process contract requires a revision-bound
`production_entrypoint_bindings` ledger, one cheap mapping artifact, exact
callsite authority, nonzero production callers, and fail-closed treatment of
missing or fallback composition; implementation and design review skills apply
the rule; and the parent-milestone versus bounded-slice distinction is explicit.

## Scope

Included: repository process documents and durable agent definitions. Excluded:
M3/M4 product design, production code, test changes, and any claim that the
missing graph-plan path is solved.

## Constraints And Invariants

The rule must improve proof without turning every review into repeated expensive
mapping. Spark maps one frozen execution boundary; Terra uses that artifact for
semantic judgment. No process rule may authorize fabricated authority or make a
slice approval satisfy a parent milestone.

## Sources Of Truth

`AGENTS.md` requires canonical execution paths and forbids integrations from
bypassing validators or store contracts. The M3 design requires graph-dependent
alignment, snapshot, planning artifact, authorization, and CAS ownership. The
M3 remediation audit found the atomic plan repository but no production source
alignment, graph snapshot, planner, authorization, or graph CAS path.

## Current State

Verified causal chain: the prior process required changed-surface and authority
ledgers but did not require a requirement-to-composition-root reachability
ledger. Bootstrap Step-1/2 focused evidence proved its bounded path; the
broader M3 completion claim was therefore not mechanically prevented from
relying on schemas and repository boundaries for graph-dependent Steps 5-8.
The final audit exposed that the required runtime chain had zero production
callers rather than a small wiring omission.

## Assumptions And Open Questions

Verified: the repository agent definitions already reserve Spark for mapping
and Terra for writers/reviewers. Assumption: one mapping artifact remains
sufficient until its trigger, owner, authority, or persistence boundary changes.
No product-semantic decision is made here.

## Milestones Or Experiments

1. Causal inspection: compare existing closure rules with the missing M3 chain.
   Status: complete.
2. Add common entrypoint ledger, candidate gate, and parent/slice rule. Status:
   complete.
3. Apply concise design/implementation/review-skill routing and validate. Status:
   complete.

## Progress Log

- 2026-08-09: Confirmed the missing control is runtime reachability, not merely
  reviewer count or model choice. Next action: validate the process delta and
  close this debugging WorkPlan.
- 2026-08-09: Added the binding ledger to the common contract, made its absence,
  zero callers, and bypass fallbacks fail candidate freeze and implementation
  closure, and routed one Spark preflight into design, implementation, and
  review. Diff and deterministic presence checks pass. Next action: none.
- 2026-08-09: Tightened mapper, worker, spec, correctness, test, and escalation
  reviewer definitions to consume the shared ledger, distinguish slice from
  parent closure, and reject contract-only or fixture-only evidence. Removed
  two stale process terms found in independent review. Next action: none.

## Evidence Log

- `docs/work/semantic_ingestion/implementation.plan.md` records that the plan
  repository exists but the accepted provider path has no sealed alignment,
  graph snapshot, graph-dependent planning artifact, authorization, or graph
  CAS owner.
- `docs/design/semantic_ingestion_architecture.md` defines those as required
  coordinator inputs and independent publication boundaries.
- Existing `.agents/PLANS.md` candidate-freeze criteria required a current
  changed-surface/evidence ledger but not a production caller or composition
  binding for each runtime requirement.
- `git diff --check -- .agents/PLANS.md .agents/skills/implement-design/SKILL.md
  .agents/skills/build-design/SKILL.md .agents/skills/review-design/SKILL.md`
  exited zero. The same check against this new WorkPlan exited zero.
- Deterministic `rg` assertions confirmed the ledger, zero-caller/fallback,
  parent/slice, Spark-preflight, design, and design-review clauses are present.
- Python `tomllib` parsed all eighteen durable agent definitions; the six
  changed definitions also passed targeted presence checks.

## Decision Log

- 2026-08-09: Add a structured ledger rather than a blanket static checker:
  source-to-owner authority is semantic and needs exact human-reviewed paths.
- 2026-08-09: Require one Spark preflight artifact per frozen execution
  boundary; reviewers reuse it, preserving Terra capacity for correctness.

## Review Log

- Three independent Spark audits reconstructed the agent-definition, skill,
  and M3-history failure surfaces. They agreed that bounded review scope, not
  reviewer count or model tier, caused the false completion signal.
- Independent architecture review found the remediation sound and token
  efficient, with two terminology corrections: stale `ExecPlan` wording and
  an undefined `design-review` WorkPlan type. Both were corrected.
- Independent test review confirmed the new rule would block the current M3
  candidate until it gains a fresh identity and complete production binding
  ledger. That is the intended next application of this process rule, not a
  defect in the rule itself.

## Blockers And Limits

No blocker. A generic script would only check headings and cannot validate
runtime reachability, so it would add false confidence and is intentionally
not created.

## Next Action

None. Completion contract satisfied.

## Outcome And Retrospective

The gap was not too few reviewers or the wrong model tier. It was that the
existing approval contract had no mandatory proof that every runtime-affecting
requirement reached a real composition root. The new ledger makes that proof
explicit, requires a single inexpensive mapping pass, and preserves expensive
review capacity for evaluating the mapped authority chain. A slice can now close
only itself; parent completion remains independently evidenced.
