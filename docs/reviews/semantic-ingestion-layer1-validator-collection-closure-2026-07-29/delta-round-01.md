# Design Review: Layer 1 Validator Collection Grammar Closure

## Review Metadata

- Review ID: semantic-ingestion-layer1-validator-collection-closure-delta-01
- Review mode: delta
- Review outcome: Changes required
- Design path: `docs/design/semantic_ingestion_architecture.md` plus the linked executable validator
- Design baseline: architecture SHA-256 `67bf2620a0379761853861e416efba0816045ef4bf88e4808e701a9ac3bc993e`; validator candidate SHA-256 `221f9e2c57135ff2f833b4eff40418e1366fd306d5b163a404e878bcf8694a5b`
- Implementation baseline: `945d6ea03649ca13c800e84bcb9972797e0f0a31` with the current working-tree Layer1 candidate
- Review date: 2026-07-29
- Reviewers: fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer`; coordinator reconciliation
- Included scope: complete CTV collection declaration, alias, normalization, authority-publication, and validator-pin boundary
- Excluded scope: unrelated semantic-ingestion behavior, production runtime behavior, registry or authority semantics, and external GitHub branch protection

## Executive Assessment

The shared collection-argument validator correctly closes the direct unquoted
arity and ellipsis defect and preserves the frozen authority. Approval is not
yet supported because quoted unprojected type expressions bypass the rule, the
candidate validator is not yet pinned by its canonical consumers, and the
public no-publication behavior lacks family-complete black-box proof.

## Governing Sources

- Root `AGENTS.md` and `.agent/PLANS.md`
- `.agent/skills/build-design/SKILL.md` and `.agent/skills/review-design/SKILL.md`
- `docs/design/semantic_ingestion_architecture.md`, Section 3.23.4.2.1
- `docs/development/static_tooling.md`
- `docs/work/semantic_ingestion/layer1-validator-collection-closure-2026-07-29/design.plan.md`
- Parent `docs/work/semantic_ingestion/implementation.plan.md`

## Independently Reconstructed Requirements

| Requirement | Source | Design coverage | Acceptance criteria | Verification | Status |
| --- | --- | --- | --- | --- | --- |
| VLC-001 | Architecture closed collection grammar | Partial | Every list/set/frozenset type position has one non-ellipsis item | Direct, alias, quoted, nested, inherited mutation matrix | changes required |
| VLC-002 | Architecture tuple projection | Partial | Finite tuple items or exactly `tuple[T, ...]` | Positive controls and complete invalid ellipsis family | changes required |
| VLC-003 | Content-addressed authority chain | Partial | All canonical consumers pin validator `221f9e2c...`; other identities remain stable | Exact checker and pin-drift tests | changes required |
| VLC-004 | Fail-closed authority publication | Partial | Invalid input creates no output and preserves seeded output bytes | Public CLI `--write` black-box matrix | changes required |

## Contract And Evidence Boundaries

The normative design bytes remain unchanged. The validator is executable design
authority, and its SHA-256 is an input to the documented checker, PR workflow,
and black-box tests. Collection syntax must be rejected in every type-position
representation before the selected 56-root projection, while ordinary literal
strings and `Field(...)` metadata strings remain data rather than forward
references. Local self-test evidence is not CI enforcement or remote
operational evidence.

## Confirmed Findings

### DREV-001: Quoted unprojected type expressions bypass collection closure

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: verification / declaration-grammar trust boundary
- Affected scenario and prevalence evidence: Any quoted forward-reference field or alias outside the 56-root projection can contain invalid collection arity or ellipsis. This is an authority-input concern; no product prevalence is claimed.
- Design location: `docs/design/semantic_ingestion_architecture.md` Section 3.23.4.2.1 and validator `validate_alias_expression`
- Governing source or requirement: VLC-001, VLC-002, and the architecture's closed static declaration language
- Expected behavior: Direct, alias, quoted, nested, inherited, reachable, and unprojected invalid collection type expressions reject before publication.
- Design behavior: Unquoted forms reach the shared validator, but `ast.Constant` quoted forms are accepted before projection; unprojected quoted declarations never reach recursive normalization.
- Evidence: Fresh reviewers reproduced exit `0` plus authority publication for quoted unprojected `list[str, int]`, list/set/frozenset ellipsis forms, and invalid tuple ellipsis placements. Reachable quoted and unquoted forms reject.
- Impact: Invalid declarative authority can produce a new authority artifact despite the closed grammar.
- Root invariant or contract boundary: Every type-position representation must be parsed and validated before projection, without treating literal/default payload strings as types.
- Equivalence class and adjacent bypasses inspected: Direct and indirect, quoted and unquoted, reachable and unprojected, alias, nested, inherited, valid finite tuple, and valid variadic tuple forms.
- Positive behavior that must remain valid: Valid forward references, ordinary string literals, `Literal[...]` members, `Field(...)` string metadata, finite tuples, and `tuple[T, ...]`.
- Recommended invariant-level resolution: Add context-aware quoted type-expression validation in field and alias type positions and reuse the same recursive collection grammar.
- Verification needed: Complete quoted direct/alias/nested negative family, valid quoted controls, baseline self-test, and public no-publication tests.
- Evidence maturity affected: implemented and locally verified VLC-001/VLC-002 claims

### DREV-002: Candidate validator identity is stale in canonical gate consumers

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: operability / verification
- Affected scenario and prevalence evidence: Every documented local or PR checker invocation with the current candidate validator; no product prevalence applies.
- Design location: `docs/development/static_tooling.md`, `.github/workflows/pr-gates.yml`, and both Layer1 test modules
- Governing source or requirement: VLC-003 and the content-addressed authority-chain contract
- Expected behavior: Canonical consumers pin validator SHA-256 `221f9e2c...` while preserving all other frozen identities.
- Design behavior: Consumers still pin `f0f74bc...`, so the exact checker exits on validator identity mismatch.
- Evidence: The documented checker fails with the stale pin and succeeds when only the expected validator SHA is changed to `221f9e2c...`.
- Impact: The corrected validator cannot pass the required deterministic gate or CI job.
- Root invariant or contract boundary: Every authority-chain consumer must bind the exact reviewed verifier revision.
- Equivalence class and adjacent bypasses inspected: Static-tooling command, PR workflow, reference compiler test, PR-gate test, parent WorkPlan, and unchanged design/registry/authority/checker/profile pins.
- Positive behavior that must remain valid: All non-validator pins and all drift/tamper rejection.
- Recommended invariant-level resolution: Update the static-tooling command in the design handoff, then perform one coordinated validator-only repin in the parent implementation milestone.
- Verification needed: Exact checker, workflow structure test, full compiler matrix, and validator drift tests using the new pin.
- Evidence maturity affected: local deterministic gate and CI-enforced maturity

### DREV-003: Collection rejection proof does not cover the public publication boundary

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: verification
- Affected scenario and prevalence evidence: Malformed collection declarations supplied to validator `--write`; no product prevalence claim applies.
- Design location: Linked WorkPlan VLC-004 and validator adversarial self-test
- Governing source or requirement: VLC-001, VLC-002, VLC-004, and fail-closed authority publication
- Expected behavior: Every invalid family member exits nonzero without creating output and preserves pre-existing output bytes; all valid sibling forms publish the expected authority.
- Design behavior: The self-test exercises `compile_authority` for a limited direct/alias set and does not exercise public CLI publication.
- Evidence: Reviewers inventoried direct, alias, quoted, nested, inherited, zero/multiple arity, and leading/trailing/duplicate ellipsis siblings; current self-tests do not cover the complete set or seeded-output behavior.
- Impact: A projection or CLI ordering regression could pass helper-level tests while publishing invalid authority.
- Root invariant or contract boundary: Grammar rejection and atomic publication are one behavioral contract at the public CLI boundary.
- Equivalence class and adjacent bypasses inspected: All collection owners; direct, quoted, alias, nested, inherited; absent and seeded output; finite and variadic positive controls.
- Positive behavior that must remain valid: Baseline byte equality and all valid unary/finite/variadic collection forms.
- Recommended invariant-level resolution: Expand validator-owned family self-tests and add a parent implementation black-box CLI matrix after the new validator pin is approved.
- Verification needed: Python 3.12 public `--write` runs for every representative family with absent and pre-seeded outputs.
- Evidence maturity affected: locally verified VLC-004 and independent-reproduction handoff

## Requirements Coverage

VLC-001 through VLC-004 remain open. The root grammar correction is viable and
bounded; no new product semantic decision is required.

## Architecture And Feasibility

The candidate uses one syntax-level collection rule in alias validation and
normalization. The remaining quoted bypass requires type-position context, not
a second independent grammar. The validator can be repinned without changing
design, registry, authority, checker, or profile bytes.

## Failure, Security, And Operations

The affected failure is authority publication for malformed declarative input.
Rollback restores the prior complete validator pin set. Mixed old/new validator
pins must fail closed. Remote CI and branch protection remain a later,
revision-bound operational evidence state.

## Verification And Evidence Maturity

The candidate is specified, derivable, implemented, and partially locally
verified. It is not yet independently approved, consistently repinned, CI
enforced, or operationally verified.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Residual risk | Status |
| --- | --- | --- | --- | --- | --- |
| Literal strings parsed as types | Overbroad quoted-form correction | Valid enums/default metadata reject | Restrict parsing to annotation and alias type positions | Low after positive controls | open |
| Mixed validator identity | Partial repin | Gate fails before reproduction | Coordinated validator-only pin update | Remote branch protection still external | open |
| Helper-only proof | CLI write ordering regression | Invalid authority publication | Public absent/seeded-output matrix | Remote CI still external | open |

## Rejected Or Consolidated Findings

Requests to add an authority-validation API to the independent compiler remain
unsupported and outside this design correction. The three findings above
consolidate all reported syntax siblings and evidence-state observations.

## Required Changes Before Approval

1. Close quoted type-position collection validation without parsing data strings.
2. Expand the complete affected collection family evidence.
3. Repin the validator in canonical consumers and prove public no-publication behavior.

## Non-Blocking Follow-Ups

Remote GitHub Actions execution and required branch-protection configuration
remain external operational evidence for the parent implementation milestone.

## Final Outcome

Changes required. No semantic ambiguity blocks a bounded remediation.

## Review Limitations

This delta review did not evaluate unrelated semantic-ingestion architecture,
production behavior, or external GitHub configuration.
