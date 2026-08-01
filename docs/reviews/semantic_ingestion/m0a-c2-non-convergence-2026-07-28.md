# M0A-C2 Bounded Non-Convergence Review

- Date: 2026-07-28
- Scope: SIA-R03/R13 C2 golden-package materialization
- Result: not approved; M0A-C2 blocked after three bounded remediation passes
- Architecture SHA-256: `e2ba649d86481e9be437a86c6227b0933891f0f5294fb312887d8881c2bb7d1f`
- Registry SHA-256: `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`
- Candidate source SHA-256: `b91599eee3eef49584db27a6b94b91eccbf560077466a94023b4eab5b3a504ec`
- Fail-closed validator SHA-256: `5ba50b5eaf3e8ce2bf31d2348f5f034f05e47baa5c5b9d8932ce09c9cb74dd83`
- Preserved materializer SHA-256: `ea3896b82b6fd67a5e3d455d3f94fb97df19b5bc8ce0016bcac81ee0cfc28db6`

## Reconciled Findings

| ID | Reviewer | Product priority | Approval disposition | Finding type | Confirmed evidence |
| --- | --- | --- | --- | --- | --- |
| C2-SPEC-01 | spec | Not applicable | changes_required | verification-governance | Signatures derive per-fixture SHA-256 seeds instead of resolving the four fixed RFC 8032 table keys and coordinates. |
| C2-SPEC-02 | spec | Not applicable | changes_required | verification-governance | Typed bodies use plain SHA-256 rather than the required schema-specific digest domains. |
| C2-SPEC-03 | spec | Not applicable | changes_required | verification-governance | Generic values and empty tuples do not instantiate finite ancestry/G1-G3; body references are not cross-bound to dependency edges. |
| C2-SPEC-04 | spec | Not applicable | changes_required | verification-governance | Datetimes are plain strings rather than tagged UTC CTV, and materializer/validator code sharing leaves no two independent elaborators. |
| C2-CORR-01 | correctness | Not applicable | blocks_approval | verification | CTV is incomplete for datetime, map ordering, and canonical decode/re-encode validation. |
| C2-CORR-02 | correctness | Not applicable | blocks_approval | verification-lifecycle | Placeholder values, empty members, wrong fixed scalars/sequences, and incomplete DAG closure cannot establish lifecycle semantics. |
| C2-CORR-03 | correctness | Not applicable | blocks_approval | security-verification | Invented seeds have no published key, purpose, or signer-coordinate resolution. |
| C2-TEST-01 | test | Not applicable | changes_required | verification | Runner fixtures use `CanonicalEncodedArtifact.v1` as inner schema instead of the runner body schemas; no kind-to-schema assertion detects it. |
| C2-TEST-02 | test | Not applicable | changes_required | verification-trust | Invented signatures, weak CTV checks, and accepted evidence are not executed independently. |
| C2-TEST-03 | test | Not applicable | blocks_approval | verification-trust | The materializer imports validator helpers; no independent second elaborator or C2 test exists. |
| C2-TEST-04 | test | Not applicable | changes_required | verification-coverage | No exact 37-ID assertion, dynamic execution of all 25 vectors, or end-to-end execution of the claimed 29 mutations exists. |

Every finding is confirmed. None is duplicate, unsupported, already resolved,
or an accepted limitation. The findings prevent approval but do not establish
a product-impact priority because this package is pre-implementation
verification authority.

## Exact Gaps

| Gap | Attempts | Why unresolved | Smallest next step |
| --- | ---: | --- | --- |
| Complete CTV and schema-domain digest authority | 3 | Required datetime, ordering, decode/re-encode, and digest-domain values are absent or contradicted | External design author supplies exact canonical rules and domains |
| Fixed signing authority | 3 | Candidate invents seeds and cannot resolve the four required keys/purposes/coordinates | External design author supplies fixed keys, purposes, and coordinates |
| Finite ancestry and G1/G2/G3 package | 3 | Placeholder and empty values do not determine exact bodies, graph members, sequences, or dependency closure | External design author supplies every exact finite value and edge |
| Independent executable proof | 3 | Shared helpers and static assertions cannot prove independent elaboration or vector execution | Supply two independent elaborators plus executable 37/25 mutation evidence |

The candidate and tooling remain preserved as nonconvergence evidence.
`validate_source.py` raises `C2_INCOMPLETE_PACKAGE` for the frozen source so it
cannot be mistaken for an approved package. This is a fail-closed evidence
change, not semantic remediation.

## Disposition

M0A-C2 is blocked. Exactly one next action remains: obtain either an external
design-author-provided complete canonical package, or a newly approved smaller
design WorkPlan that explicitly supplies exact finite G1/G2/G3 values and two
independent elaborators.
