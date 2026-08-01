# Design Review: Layer 1 Validator Collection Grammar Closure

## Review Metadata

- Review ID: semantic-ingestion-layer1-validator-collection-closure-delta-02
- Review mode: delta
- Review outcome: Changes required
- Design path: `docs/design/semantic_ingestion_architecture.md` plus the linked executable validator
- Design baseline: architecture SHA-256 `67bf2620a0379761853861e416efba0816045ef4bf88e4808e701a9ac3bc993e`; validator candidate SHA-256 `128bf582014d6fcb5bf59a8e227f726a83f673722133042c8a870cfb77089b4f`
- Implementation baseline: `945d6ea03649ca13c800e84bcb9972797e0f0a31` with the current working-tree Layer1 candidate
- Review date: 2026-07-29
- Reviewers: fresh targeted `spec_auditor`, `correctness_reviewer`, and `test_reviewer`; coordinator reconciliation
- Included scope: DREV-001 remediation, collection type/data classification, static-tooling pin, and parent CLI-proof handoff
- Excluded scope: unrelated design and external CI execution

## Executive Assessment

Whole-expression quoted forward references are now validated and data strings
remain data, but the type/data classifier is not closed. Quoted ellipsis child
arguments and bare `Field(...)` calls can still occupy collection type
positions. One final invariant-level grammar correction is required.

## Governing Sources

- Root `AGENTS.md`, `.agent/PLANS.md`, and the design/review Skills
- `docs/design/semantic_ingestion_architecture.md`, Section 3.23.4.2.1
- `docs/work/semantic_ingestion/layer1-validator-collection-closure-2026-07-29/design.plan.md`
- `docs/reviews/semantic-ingestion-layer1-validator-collection-closure-2026-07-29/delta-round-01.md`

## Independently Reconstructed Requirements

| Requirement | Source | Design coverage | Acceptance criteria | Verification | Status |
| --- | --- | --- | --- | --- | --- |
| VLC-001 | Closed unary collections | Partial | One valid type argument; ellipsis, metadata, and invalid type expressions reject | Complete type/data family | changes required |
| VLC-002 | Closed tuple grammar | Partial | Finite valid types or exact native `tuple[T, ...]` | Position/cardinality/quoted ellipsis matrix | changes required |
| VLC-003 | Content-addressed validator | Complete for design handoff | Static tooling pins exact validator | Exact checker | locally verified |
| VLC-004 | Fail-closed publication | Measurable parent handoff | Absent and seeded output unchanged for invalid input | Parent public CLI matrix | pending implementation |

## Contract And Evidence Boundaries

String values are parsed only when they spell a type-position forward
reference. Ellipsis is grammar punctuation, not a quoted type. `Field(...)` is
metadata only inside the authorized `Annotated` context or a separately
validated data context; it is never a collection item type.

## Confirmed Findings

### DREV-004: Collection arguments are validated before complete type/data classification

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: verification / declaration-grammar trust boundary
- Affected scenario and prevalence evidence: Malformed schema-fence collection annotations using quoted ellipsis children or `Field(...)` in type positions; this is authority-input behavior with no product-prevalence claim.
- Design location: Validator `validate_type_expression` and `validate_collection_arguments`
- Governing source or requirement: VLC-001, VLC-002, VLC-004, and Section 3.23.4.2.1's closed type and metadata grammar
- Expected behavior: Collection arguments are closed type expressions; only native position-two ellipsis in exact `tuple[T, ...]` is admitted; `Field(...)` is admitted only as authorized metadata/data.
- Design behavior: Shape validation observes the raw outer AST. Quoted `"..."` is not counted as ellipsis and later recurses to an accepted constant, while the generic `ast.Call` branch accepts `Field(...)` as a type.
- Evidence: Fresh public `--write` probes published authority for list/set/frozenset quoted ellipsis arguments, invalid tuple quoted ellipsis positions, nested variants, and `list[Field(default=None)]`. The same recursive paths cover aliases, inherited fields, and all collection owners.
- Impact: Malformed declarative authority can pass and publish despite the closed grammar.
- Root invariant or contract boundary: Type positions require a closed classifier before collection shape validation; metadata/data constructs cannot be accepted by the type classifier.
- Equivalence class and adjacent bypasses inspected: Direct, quoted, alias, nested, inherited, reachable, unprojected, all four collection owners, ellipsis position/cardinality, `Literal` data, `Annotated` metadata, and dynamic metadata.
- Positive behavior that must remain valid: Whole valid quoted forward references, native `tuple[T, ...]`, finite tuples, unary containers, `Literal["..."]`, authorized `Annotated[..., Field(...)]`, and prior `ast.Name` data-expression syntax.
- Recommended invariant-level resolution: Reject quoted expressions that parse to ellipsis; remove bare `Field` calls from the type-expression grammar and admit them only through explicit metadata/data validation; validate every recursive collection argument as a type.
- Verification needed: Complete quoted-child ellipsis and Field-as-type negative families across all representations; add multiple native ellipsis cases; retain valid type/data controls; run self-test, exact checker, and parent absent/seeded-output CLI matrix.
- Evidence maturity affected: VLC-001/VLC-002 local verification and VLC-004 handoff completeness

## Requirements Coverage

VLC-003 is design-locally verified. VLC-004 is explicitly measurable parent
implementation work. VLC-001 and VLC-002 require the final design correction.

## Architecture And Feasibility

The correction is a bounded grammar classification change. It requires no
normative design, registry, authority, checker, profile, or production change.

## Failure, Security, And Operations

Invalid authority input must fail before publication. Rollback restores the
prior complete validator pin. Mixed validator pins continue to reject.

## Verification And Evidence Maturity

The static-tooling pin and exact checker are locally verified. CI and public
publication proof remain parent implementation evidence and are not claimed.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Residual risk | Status |
| --- | --- | --- | --- | --- | --- |
| Over-reject valid data strings | Type parser applied in data context | Existing valid authority breaks | Explicit Literal/Field controls | Low | open |
| Miss another ellipsis spelling | Raw-AST-only shape check | Invalid authority publishes | Parsed type classification plus full matrix | Low | open |
| Exhaust design budget | Another sibling-only patch | Non-convergence | Final round must close the classifier invariant | Material if recurrence | open |

## Rejected Or Consolidated Findings

DREV-001 is resolved except for the deeper classifier root captured by
DREV-004. DREV-002 is closed for design documentation. DREV-003 is a valid,
measurable parent implementation handoff rather than a design-local defect.

## Required Changes Before Approval

Close DREV-004 at the type/data grammar boundary and add the complete sibling
proof in the final design remediation round.

## Non-Blocking Follow-Ups

Parent implementation must repin workflow/tests and prove absent and seeded
public CLI output behavior. Remote CI remains external evidence.

## Final Outcome

Changes required.

## Review Limitations

This targeted delta did not review unrelated semantic-ingestion behavior.
