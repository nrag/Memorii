# Semantic Ingestion Traceability Registry Completion

- Work ID: semantic_ingestion-traceability
- Work type: design
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-07-27
- Last updated: 2026-07-27
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/traceability-registry-closure-2026-07-27/design-revision.plan.md`; `docs/work/semantic_ingestion/traceability-registry-closure-2026-07-27/design-review.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md` at SHA-256 `f94e76033f06e10c0f7b8fd6d0905c7d9f70202f3e7e39d11b2ce65588c3aed0`
- Expected outputs: approved content-addressed R03 traceability registry/trust package and a reviewed revised design baseline

## Objective

Complete the design-level instance data required by SIA-R03 so an implementation can deterministically generate and independently verify the full Section 1-5 traceability manifest without semantic inference from prose, blanket mappings, self-approval, or hidden conversational context.

## Completion Contract

The design completion contract in `.agent/PLANS.md` applies. The revised design/package must provide:

- exactly one complete nonempty requirement default for every extracted Section 1-5 heading;
- canonical owner, assertion template/version, and test-evidence group for every R01-R23 mapping;
- complete closed structural secondary rules and selectors;
- every exceptional override and explicit anchor binding;
- all ledger self-mappings and many-to-many secondary mappings;
- content-bound coverage approvals from externally authorized reviewers;
- canonical profile/schema/signature bindings and lifecycle-aware trust/revocation/compromise/supersession material;
- exact artifact bytes/digests and measurable mutation acceptance criteria;
- fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer` approval with no confirmed `blocks_approval` or `changes_required` finding.

## Scope

Included: only R03 registry contents, approval/trust ownership, canonical bindings, and their verification semantics.

Excluded: implementing the registries; changing ingestion, provider, persistence, replay, semantics, or external topology/policy decisions; inferring mappings from prose.

Deferred: implementation resumes in the parent WorkPlan after design approval.

## Constraints And Invariants

- Do not use English keywords, regex semantics, broad catch-all defaults, or all-requirements-to-all-headings mappings.
- Coverage approval is distinct from implementation execution evidence.
- Parser agreement alone cannot approve coverage or execution.
- Trust and approval identities are externally owned and cannot be self-issued by the implementation worker.
- The design baseline cannot move until the full design review workflow approves it.

## Sources Of Truth

Source precedence follows `AGENTS.md`. The immediate governing contract is Section 3.23.4 and SIA-R03 of the frozen semantic-ingestion design, plus `.agent/PLANS.md` and `$build-design`.

## Current State

Verified:

- Section 3.23.4 defines the required schemas and validation rules.
- It does not contain the required per-heading default registry, structural rule registry contents, assertion registry contents, overrides, anchors, coverage approval records, reviewer identities, trust snapshots, or key lifecycle artifacts.
- Repository search finds those identifiers only in the design's schema/prose, not as canonical artifacts.
- Three independent M0 reviewers found that the implementation cannot prove traceability without these artifacts.

Interpretation:

- Creating these contents requires semantic coverage judgment and external approval. It is design work, not a mechanical implementation detail.

## Assumptions And Open Questions

- Verified facts: the missing contents are mandatory and no fallback/default is authorized.
- Working assumptions: the product/spec/review owner will provide or approve the registry contents and trust identities.
- Unresolved questions: exact heading-to-requirement sets, secondary selectors, assertion ownership/versioning, exceptional overrides, reviewer identities, trust roots, lifecycle/revocation state, and artifact publication owner.
- Decisions requiring external input: all unresolved questions above.

## Requirements Ledger

| ID | Requirement | Source | Priority | Acceptance criteria | Status |
| --- | --- | --- | --- | --- | --- |
| SIA-TR-D01 | Supply complete per-heading requirement defaults | SIA-R03 / Section 3.23.4 | Required | One explicit reviewed entry per extracted heading; no inheritance/catch-all | blocked |
| SIA-TR-D02 | Supply closed secondary structural rules | SIA-R03 / Section 3.23.4 | Required | Deterministic selectors over parser outputs cover all secondary mappings | blocked |
| SIA-TR-D03 | Supply owner/assertion/test registry | SIA-R03 / Section 3.23.4 | Required | Every mapping resolves one canonical owner and measurable versioned assertion | blocked |
| SIA-TR-D04 | Supply overrides and anchors | SIA-R03 / Section 3.23.4 | Required | All exceptional additions/replacements and SIA-I bindings are explicit and reviewed | blocked |
| SIA-TR-D05 | Supply coverage approvals and trust lifecycle | SIA-R03 / Section 3.23.4 | Required | Every heading has one content-bound approval under lifecycle-valid trust | blocked |
| SIA-TR-D06 | Bind canonical artifact bytes | SIA-R03 / canonical profile | Required | Exact schema/profile/signature preimages and content digests are reproducible | blocked |

## Problem Definition

The approved design requires executable reverse traceability while prohibiting semantic inference from prose. Implementation discovered that the design provides the data-model shape but not the actual mapping and approval data. Without those contents, an implementation must either omit the manifest or invent semantic coverage, both of which violate SIA-R03.

Affected actors are implementation coordinators, independent reviewers, release/acceptance owners, and future operators who depend on revision-bound completion evidence.

Desired outcome: a new agent can generate and verify the complete manifest using only repository artifacts, with no hidden judgment or chat history.

## Non-Goals

- Do not implement parser, checker, evidence verifier, or ingestion behavior here.
- Do not select topology, replay, policy, model, resource, or statistical values.
- Do not weaken R03 or replace approvals with self-signed implementation fixtures.

## Existing-System Analysis

Initial M0 artifacts under `memorii/memorii/tools/semantic_ingestion_*` demonstrate feasibility of independent parsing and evidence verification but are incomplete and unapproved. They are evidence for this gap, not a source of design authority.

## Alternatives Considered

1. Infer mappings from prose or keywords. Rejected: explicitly forbidden and circular.
2. Map all requirements to every heading. Rejected: hides missing secondary mappings and makes approval meaningless.
3. Let the implementation worker author and self-sign registries. Rejected: violates external coverage/trust ownership and independence.
4. Provide reviewed explicit registries and trust bindings. Selected in principle; blocked pending owner input.

## Feasibility Evidence

Two independent parser approaches can produce structural units, and immutable baseline capture is feasible. Reviewer mutations demonstrate that complete registry contents are the remaining semantic input, not a tooling feasibility issue.

## Failure And Operational Analysis

Missing, extra, stale, duplicate, orphaned, owner-mismatched, self-map-missing, secondary-map-missing, unapproved, expired, revoked, compromised, superseded, or wrong-revision registry/approval content must fail closed. Registry publication must be content-addressed and immutable; rollback cannot restore an unapproved registry.

## Verification Strategy

- independent parser/checker byte equality;
- exact registry/manifest regeneration;
- per-heading approval validation;
- lifecycle-aware trust/signature verification;
- mutations for every default, rule, owner, assertion, override, anchor, approval, trust state, content key, design digest, and artifact digest;
- fresh independent design reviews.

## Milestones Or Experiments

### D-M1 - External registry and trust decision

- Purpose: obtain the authoritative mapping/approval contents.
- Scope: SIA-TR-D01 through D06.
- Expected artifacts: canonical registry package and owner/trust decision.
- Verification: independent reconstruction and mutation review.
- Status: blocked.

## Progress Log

- 2026-07-27: Parent M0 implementation and three independent reviews exposed the missing registry contents. Opened this linked design WorkPlan and stopped implementation rather than inventing mappings.

## Evidence Log

- Frozen design Section 3.23.4 lines approximately 4482-4697 defines required registries and approvals but no instances.
- Repository `rg` finds `SectionTraceabilityDefaultRegistry`, `StructuralRequirementMappingRuleRegistry`, and coverage approval identifiers only in the design.
- M0 reviews recorded in the parent WorkPlan reproduce unresolved parents, continuation omissions, incomplete coverage acceptance, and arbitrary evidence acceptance.

## Decision Log

- 2026-07-27: Treat missing registry contents as a design ambiguity. Alternatives were semantic inference, blanket mappings, or self-approval; all contradict the frozen design.

## Review Log

No design review round can begin until an external owner supplies the registry/trust contents.

## Blockers And Limits

- Blocker: externally authorized semantic coverage and trust contents are unavailable.
- Resume condition: product/spec/review owner supplies the complete package described in the Completion Contract.

## Next Action

Obtain the externally approved per-heading traceability registry, assertion/rule/override/anchor package, and coverage trust material.

## Outcome And Retrospective

Superseded and completed by the linked revision/review WorkPlans. The approved revision-3 design is SHA-256 `b88cf96b985210f55333643b8f62e628baedd02e7fe15f0ed53ca8c19aa7e1f6`; canonical registry SHA-256 is `19c15d0a0a93656daca9bffb87e77cef497f165f8c1171f5d6428d72a04a6259`. External trust values remain registered under `SIA-ED-TRACEABILITY-001`, while implementation can resume with determinate fail-closed behavior.
