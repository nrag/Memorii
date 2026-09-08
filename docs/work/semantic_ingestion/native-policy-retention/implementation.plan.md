# Native Arbitration Policy Retention

- Work type: implementation
- Status: complete, bounded retention prerequisite only
- Parent: ../engineering-closure/milestones/05-authenticated-observer-comparator.plan.md
- Related design: ../observation-ledger/design.plan.md and approved projection-observation-decision.md
- Baseline: semantic_ingestion_m5 at 191826cd3afb38bf605a337a71d576063b3bae5e, authorized dirty tree.

## Objective And Boundary

Retain the immutable arbitration bundle already supplied to the native normalization
constructor. This is a prerequisite for native projection publication; it does
not implement projection publication, registry, ledger, retrieval or M5 closure.
SIA 4.8.2.26 requires same-generation policy authority, with no ambient lookup.
The approved separate temporal/trust direction preserves that boundary.

Production: source_normalization_stage._planning_construction_authority_for_operation
already receives SemanticArbitrationPolicyBundle and uses it for predicate trust
and temporal resolution. Add the exact bundle to its retained typed construction
authority. The Spark entrypoint-preflight and native-projection-binding maps own
call paths; generic terminal and clarification paths are not native caller proof.

## Requirements And Acceptance

- Retain the exact source-supplied bundle through normalization and the native
  group request. New source construction always supplies it.
- Validate a present bundle against predicate_trust_rule and every temporal
  construction: closure temporal/trust fingerprints, both snapshot digests,
  arbitration instant, construction temporal fingerprint, and effective-time
  temporal fingerprint/snapshot. Reuse canonical model validation; no live lookup.
- Preserve absent legacy bytes and hashes with existing legacy field omission
  hooks. Absence is supported for historical decoding; future activated native
  projection publication must require presence, outside this bounded slice.
- Do not impose new temporal-construction cardinality on operation kinds merely
  because a bundle is present. Existing operation contracts own cardinality.

## Verification Matrix

A genuine nested body is captured before edits via the existing public provider
fixture. Initial capture attempted an unsupported standalone artifact root and
failed after the public path completed; corrected capture uses the native nested
CTV body. Preserve that distinction in evidence.

Focused proof: old nested body exact re-encoding; present bundle roundtrip;
self-consistent substituted policy/time/rule and every independently carried
coordinate reject; existing public provider normalization reaches its actual
native group caller with matching bundle. Negative pure construction checks use
fast fixtures; one public provider run establishes forwarding. No ledger or
publication result is inferred from these tests.

Root owns all test processes. Toolchain is root .venv Python 3.12, warnings as
errors. Run focused test file, existing observation retention and historical
terminal compatibility checks; Ruff/Pyright on changed files and identity hygiene.
Canonical SIA amendment affects the source-derived fixture chain, so no complete
slice/parent closure can be claimed until all affected source-generation and
workflow gates are refreshed and verified at the final candidate.

## Ownership And Review

One Terra worker owns contracts.py, source_normalization_stage.py, focused tests,
and the exact SIA construction-authority field/preimage paragraph only. Root owns
this plan and final evidence. Other approved dirty files are preserved.
Spec consultation confirms the retention is determinate and requires the full
coordinate relation above. Root treats the missing proposed checks as a contract
conformance action, not an established P2 runtime defect in an unimplemented new
validator. Test consultation is incorporated except unsupported new cardinality
restrictions; existing operation kinds retain their own cardinality authority.
After a frozen code candidate, independent spec/correctness/test review is required.
All parent registry/ledger/retrieval requirements remain partial.

## Next Action

Continue parent work in ../registry-publication/implementation.plan.md.
This bounded retention prerequisite is closed; see closure.md for exact scope.

## Verification Progress (2026-09-07)

The typed bundle retention and coordinate checks are implemented. The root-owned
focused run passed: 2 tests in 33.89 seconds, warnings as errors, Python 3.12,
with output in `tests-final.log`. Earlier failures in `tests.log` and
`tests-delta.log` were test construction errors; the corrected negative cases
rebuild valid nested digests before exercising the policy relation.

The exact configured repository Pyright check passes with zero errors
(`pyright-repository.log`). The supplemental explicit-file check reports 281
errors (`pyright.log`); those files lie outside the configured include set.
This extra-check gap is unresolved and has not been classified as preexisting
without clean-base reproduction. No exclusions or ignores were added to make
the check pass. Focused production Ruff passes (`ruff.log`).

The genuine before-edit fixture remains byte-identical. Public-path proof reaches
the native group's nested reduction input. Absence of a direct policy field on
BootstrapGraphAuthorityRequestV3 does not demonstrate loss of this nested input;
the initial mapper inference is rejected pending correction of its artifact.
Projection publication, registry publication, ledger and retrieval remain partial.

## Supplemental Type Baseline

The root reproduced the forced-file diagnostics against a clean archive of merge
base b4f6c24b091a28bd3d1f65102c742478fc7276b3. It had 280 diagnostics. One
additional working-tree diagnostic came from the private field-name hook result.
A typed class dispatch correction exposed an import-time initialization failure;
that attempt is retained in tests-typed-dispatch.log and was replaced by the
existing dispatch with explicit tuple validation. The final forced-file output
has the identical 280 baseline diagnostics by file, source line and message
(type-baseline-comparison.json). They are supplemental baseline debt, not a
passing forced-file check. No suppression was added. Focused compatibility is
being rerun after the correction; the configured repository check passed earlier.

## Frozen Bounded Code Review

Candidate bad11616bfd6989870d6bb5f25053e6cf22265b9295179bdaffc222992aa165d
records exact files. Final focused run: 6 passed in 67.31s; final Ruff passes.
Independent spec, correctness and test roles now inspect only retention, legacy
bytes and the tuple guard. The moving observation target is outside this review.
Final source-chain gates are root-owned and running against regenerated CTV and
structural outputs; the fixture inventory and policy profile remain unchanged.

Delegation: group_projection_owner (Terra worker) implemented retention and
then moved to disjoint design-document correction; observation_entrypoint_map
(Spark mapper) supplied and corrected nested production lineage; independent
Terra spec/correctness/test roles review the frozen code; numeric_runtime_owner
(Terra) derived source artifacts and exact pins, with root retaining gate execution.
The obsolete recipe generator is not an input to the three exact source gates.
No source pin was relaxed and no historical artifact was relabeled as global audit.

## Current Source Gates

All three exact source checks from the current PR workflow passed after derived
CTV/structural artifact regeneration and reviewed pin updates: CTV binding
authority, lifecycle-root signer provenance, structural manifest contract.
Commands, exit codes and logs are recorded in exact-gates.json, with the workflow
and SIA identities. The 56-schema fixture profile remains unchanged. Local
Python3.12/macOS execution does not establish GitHub Ubuntu runner success.

## Completion

See closure.md and candidate-final.json. All retained-policy review findings and
post-rename identity evidence are resolved. Parent M5 remains partial.
