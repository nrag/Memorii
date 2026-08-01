# M0A-C2 Round-10 Final Non-Convergence

Date: 2026-07-28

Status: blocked after the authorized tenth and final remediation round.

## Frozen Baseline

- Architecture SHA-256:
  `93570981d938285ac5201044a365108a0f9d688dd3c78e50d16f15d95a8a88d8`
- Recipe SHA-256:
  `92ed8a14788a4ea6213f5778f0307a37983468e1bea01858f27eb88759dd6d07`
- Validator before the closure sentinel SHA-256:
  `8354a23f4f10e9f86d0012f9b3494b34a5815e9ef1e677a143f2805326537b63`
- Validator with the closure sentinel SHA-256:
  `e93ebf3665e6e4126bc5ba2daedf111c2f301cc69e3b56e4024aca204fb1446e`
- Registry SHA-256:
  `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`

The validator now rejects this exact recipe with
`ROUND10_INCOMPLETE_AUTHORITY`. The pre-sentinel validator hash is preserved
because it is the exact artifact reviewed in round 10; the closure-only
sentinel necessarily changes the working-file hash.

## Confirmed Findings And Dispositions

| Finding | Product priority | Approval disposition | Finding type | Coordinator disposition |
| --- | --- | --- | --- | --- |
| Recursive declared schema types and enum applications are not enforced | Not applicable | blocks_approval | verification | confirmed |
| Terminal, replacement, reference, mutation-kind, boundary, reason, and outcome compatibility remain unenforced as closed executable matrices | Not applicable | blocks_approval | verification | confirmed |
| CTV profile, body binding, and recipe source-identity preimages are not recomputed | Not applicable | blocks_approval | architecture/verification | confirmed |
| The 11-row marked enum registry is not proven transitively exhaustive | Not applicable | blocks_approval | verification-governance | confirmed |
| Nested authority equality skips structured values | P2 | changes_required | runtime behavior | confirmed; important nested substitution and ancestry cases can diverge |
| Full-input adversarial denominator is representative rather than exhaustive | Not applicable | changes_required | verification | confirmed |
| No stable repository gate executes the validator and negative corpus | Not applicable | changes_required | operability | confirmed |

No finding is duplicate, unsupported, already resolved, or an accepted
limitation. All prevent approval of the C2 authority package.

## Gap And Attempt Record

| Gap | Round-10 attempt | Why unresolved |
| --- | --- | --- |
| Recursive schema typing | Parsed direct class field names and checked top-level field sets | Field-name equality does not evaluate nested annotations, unions, Literals, or collection element types |
| Closed mutation/outcome matrices | Resolved 66 paths and checked owner/path existence, reference examples, and no-op values | Declared terminal labels and outcome triples are still trusted recipe strings |
| Binding recomputation | Bound caller-supplied raw design/registry hashes and documented an enum-registry profile extension | The recipe does not carry the new source identity and the validator does not recompute the complete profile/body preimages |
| Enum exhaustiveness | Added a marked closed registry of 11 module-level traceability Literal aliases and exact member checks | No transitive walk proves that every Literal reachable from the 56-schema inventory is represented exactly once |
| Nested authority equality | Compared complete stored authority/expansion trees and selected direct scalar fields | The supplemental authority overlay still skips dict/list values and therefore cannot independently prove nested source equality |
| Adversarial denominator | Added callable full-candidate validation and deep-copy tests for denominator, missing owner, no-op, and source hash | Required malformed tag, schema, structured-leaf, replacement, reference, and outcome families are not all exercised through full candidate inputs |
| Stable repository gate | Ran the validator, compilation, static tools, and diff checks manually | No checked-in deterministic gate fixes the exact command, identities, and negative denominator |

## Evidence

Before insertion of the closure sentinel, the exact frozen inputs completed the
validator and its representative self-tests. After insertion, the exact inputs
failed with `ROUND10_INCOMPLETE_AUTHORITY`, as required. Repository-local Ruff
reported `All checks passed`; repository-local Pyright reported `0 errors, 0
warnings, 0 informations`; Python 3.12 `py_compile` and `git diff --check`
passed.

No production or C1 artifact was changed.

## Blocker And Smallest Next Step

The authorized ten-round budget is exhausted. Continuing would be unauthorized
semantic remediation, not closure work.

Exactly one next action remains: obtain explicit authorization for a new narrow
design iteration that supplies the seven missing executable authorities above,
or provide externally corrected design authority that resolves them. Until
then, C2 and every implementation milestone depending on it remain blocked.
