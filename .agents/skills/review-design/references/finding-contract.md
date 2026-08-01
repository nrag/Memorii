# Finding Contract

## Required Fields

Every proposed finding must include:

- Finding ID
- Title
- Product priority
- Approval disposition
- Remediation eligibility
- Confidence
- Finding type
- Affected scenario and prevalence evidence
- Design location
- Governing source or requirement
- Expected behavior
- Design behavior
- Evidence
- Impact
- Root invariant or contract boundary
- Equivalence class and adjacent bypasses inspected
- Positive behavior that must remain valid
- Recommended invariant-level resolution
- Verification needed
- Evidence maturity affected

Return incomplete findings to the reviewer. The coordinator must not infer
missing classification fields.

Use immutable IDs in the form `DREV-001`, `DREV-002`, and so on. The durable
report validator requires `DREV-` followed by exactly three digits.

## Classification

Use the canonical product-priority and approval-disposition definitions and
allowed combinations in root `AGENTS.md`. Do not copy or redefine them here.

Use confidence:

- `high`
- `medium`
- `low`

Low-confidence observations cannot block approval without more evidence.

Use remediation eligibility from `.agents/PLANS.md`:

- `eligible_p1_p2`
- `evidence_action`
- `record_only`
- `external_blocker`

Only `eligible_p1_p2` findings enter design or implementation remediation.
Approval disposition is not a shortcut around the product-impact evidence
required for P1/P2.

## Family-Complete Findings

A finding about one representation must inspect readily adjacent forms before
submission. Depending on the contract, inspect:

- direct and indirect references
- aliases and shadowing
- quoted and unquoted forms
- nested and inherited forms
- declaration ordering and duplicates
- fast paths and normal paths
- serialization and deserialization
- positive forms that must remain valid

Report the shared invariant once. List sibling examples as evidence, not as
separate future findings.

For a proposed parser or validator fix, state whether the correction closes a
grammar production, typed rule, state transition, property, or only one example.
Do not recommend one special-case branch when a closed rule is available.

## Finding Acceptance Test

Before confirming a finding, require:

1. a governing requirement or explicit approval contract
2. an observable contradiction or unsupported claim
3. a bounded affected scenario
4. direct evidence or a reproducible counterexample
5. a correction within scope
6. a behavioral failure signal

Do not convert style preferences, hypothetical future flexibility, or evidence
from the wrong maturity state into blocking requirements.

Before assigning P1 or P2, additionally require:

1. a supported scenario that reaches the canonical product path
2. demonstrated wrong or absent product behavior
3. evidence or a reasoned explanation that the scenario is mainstream or
   important under `AGENTS.md`

A missing test alone is an evidence gap, not a product defect. An unsupported
malformed input is not P1/P2 unless it crosses a reachable trust boundary and
causes incorrect authorization, persistence, availability, or rejection of
valid supported behavior.
