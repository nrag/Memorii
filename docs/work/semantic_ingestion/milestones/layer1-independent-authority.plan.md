# Layer1 Independent Authority Milestone

- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Status: complete
- Requirements: SIA-R03, L1-008, L1-009
- Historical authority: archive heading `Layer1 - Independent CTV compiler and enforced hermetic gate`

## Objective

Provide a separately authored compiler that consumes only the frozen design and
registry, derives the byte-identical complete authority, rejects invalid
authority families equivalently, and is enforced by the hermetic PR gate.

## Scope And Owners

Own the independent reference compiler, behavioral mutation proof, existing PR
workflow invocation, and current-state documentation. Do not change product
runtime behavior, public schemas, reviewed design/registry/authority bytes, or
reuse the design parser/normalizer.

## Completion Evidence

- Full authority equals the frozen expected bytes and digest.
- Independent rejection covers syntax, declaration, enum, graph, profile,
  fingerprint, and binding families.
- The exact hermetic checker runs in PR CI and fails on drift, disagreement,
  mutation acceptance, or nonzero checker status.
- Focused Ruff, configured Pyright, compilation, and diff hygiene pass.
- Frozen milestone review leaves no validated P1/P2, `blocks_approval`, or
  `changes_required` finding.

## Recorded Result

Complete for the bounded replacement milestone. Exact commands, hashes,
review-round evidence, current-pin corrections, and remaining historical C2
limitations remain verbatim in the archive and linked Layer1 design plans.

## Dependencies And Limits

This milestone does not approve or consume the rejected M0A-C2 authority and
does not establish external certification.

