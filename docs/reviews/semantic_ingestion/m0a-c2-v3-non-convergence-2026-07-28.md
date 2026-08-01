# M0A-C2 V3 Final Non-Convergence Review

Date: 2026-07-28

This report is immutable evidence for the exact frozen baseline:

- architecture:
  `f70611d0879bd9daa8dc0c80beab50250d6c99e67b633e37bc6ae9376bfe9f5b`
- oracle-free recipe:
  `44698181d560e7a0a5d133ec142448ab247445af4197dbadd27bc7b3ca366291`
- rejected historical output:
  `e4875ec3e8afcc8a8410b2dceac8b00b50c296711652695fce80f2eaa46463be`
- registry:
  `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`

The third and final authorized design-review round did not converge. The
linked design WorkPlan budget is exhausted. No finding below is approval
evidence, and no prior execution claim applies to this baseline.

## Findings

### C2-V3-SPEC-01

- Product priority: P2
- Approval disposition: changes_required
- Finding type: verification
- Affected scenario: required mutation verification for the important failure
  cases in the C2 approval package.
- Evidence: 20 of the 25 vector records declare `mutation_kind=none`.
  Consequently the advertised denominator is not executable: only five vector
  mutations, 29 nested substitutions, and 11 distinct effective direct-negative
  categories produce 45 concrete mutations.
- Required correction: replace all 20 no-op vectors with exact concrete state
  mutations and freeze one honest denominator.

### C2-V3-SPEC-02

- Product priority: Not applicable
- Approval disposition: changes_required
- Finding type: governance
- Evidence: WorkPlans and review text retained superseded architecture, recipe,
  and derived-package hashes and continued to cite M1-M3 success.
- Required correction: repin the exact v3 baseline and invalidate all evidence
  produced for earlier recipes.

### C2-V3-TEST-01

- Product priority: Not applicable
- Approval disposition: changes_required
- Finding type: verification
- Evidence: the purported oracle-free primitive fixture bodies retain derived
  artifact coordinates and digest-shaped values. An elaborator can therefore
  consume expected outputs rather than derive them.
- Required correction: primitive graph inputs use fixture-ID references only;
  coordinates and all digests are derived outputs.

### C2-V3-TEST-02

- Product priority: Not applicable
- Approval disposition: changes_required
- Finding type: governance
- Evidence: test and WorkPlan baselines still identify the rejected historical
  `v1.json` output as successful execution evidence.
- Required correction: retain that file only as explicitly rejected historical
  evidence and require new isolated evidence after recipe approval.

### C2-V3-CORR-01

- Product priority: Not applicable
- Approval disposition: changes_required
- Finding type: runtime behavior
- Evidence: primitive body templates preserve lifecycle and G1/G2/G3 values
  from the superseded output package that disagree with `primitive_authority`,
  including action, sequence, predecessor, and generation relationships.
- Required correction: every primitive body field must equal the single
  lifecycle/generation authority before any digest is derived.

### C2-V3-CORR-02

- Product priority: Not applicable
- Approval disposition: changes_required
- Finding type: architecture
- Evidence: top-level vectors, nested substitutions, and direct-negative cases
  use different untyped target/path dialects. A verifier cannot apply them
  through one determinate mutation operation without inventing dispatch rules.
- Required correction: define one typed, closed mutation target grammar and
  express every case through it.

### C2-V3-CORR-03

- Product priority: Not applicable
- Approval disposition: changes_required
- Finding type: governance
- Evidence: structural design-side validation reported acceptance despite the
  authority contradictions and stale evidence above.
- Required correction: preserve structural diagnostics but reject this exact
  recipe as `V3_INCOMPLETE_AUTHORITY`.

## Attempt Ledger

| Gap | Attempts | Result |
| --- | ---: | --- |
| Canonical primitive authority | 3 | Still contains derived/output-shaped values |
| Lifecycle and G1/G2/G3 agreement | 3 | Authority and primitive bodies disagree |
| Executable mutation closure | 3 | Only 45 concrete mutations; target dialects conflict |
| Independent evidence | 3 | Earlier M1-M3 evidence binds superseded inputs |
| Governance baselines | 3 | Corrected only by this closure; semantic findings remain |

## Disposition

All findings are confirmed. None is duplicate, unsupported, already resolved,
or an accepted limitation. The operation is blocked because the revision
budget is exhausted, not because the remaining corrections are indeterminate.

Exactly one next action remains: an external design author supplies a corrected
complete oracle-free recipe whose bodies exactly equal its authority, whose 25
vectors contain 20 concrete mutations, whose graph uses fixture-ID references
only, and whose mutations use one typed common target grammar; or the user
explicitly authorizes a fourth design remediation beyond the exhausted budget.
