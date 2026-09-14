# Package 1: Evidence Retention And M0 Reconciliation

- Parent WorkPlan: `docs/work/semantic_ingestion/engineering-closure/implementation.plan.md`
- Status: paused (partial; parent closure blocked)
- Requirements: R01, R02, R03, R04, R07, R09, R10, R11, R12, R13, R18, R20, R21, R22, R23

Retain completed evidence, crosswalk stale M0 allocation to the July 31
replacement, and map owners/gates. No product change. The binding ledger cannot
claim runtime completion.

## Next Action

Include the retained proof crosswalk in the final whole-candidate gate and
review matrix after the remaining implementation packages freeze.

## Reconciled Proof Crosswalk

| Prior concern | Current owner/evidence | Closure treatment |
| --- | --- | --- |
| Recursive CTV/enum closure and independent structural derivation | `semantic_ingestion_ctv_reference_compiler.compile_authority`; `semantic_ingestion_traceability_checker.rebuild_structural_manifest_bytes`; corrected July 31 M0 packet | Retain corrected implementation; rejected C2 bytes remain rejected |
| Lifecycle/genesis authority and exact preimages | `semantic_ingestion_traceability_release` current validators; same M0 packet | Preserve validators; package 2 adds concrete crypto and signing tools |
| Request-selected acceptance authority | `RegisteredApprovalExecutor.from_resolver` and fixed-authority `execute`; M0 final request-boundary review | Retain isolation; new Ed25519 integration must execute this public boundary |
| Atomic publication and rollback | `FileTraceabilityReleasePublicationStore` and monotonic fence contract; M0 publication regressions | Retain semantics; new fixtures must provision valid predecessor state |
| Immutable provider compatibility | completed M1/provider-compatibility proof and protected fixtures | Retain; do not reopen based on the stale M0 parent allocation |
| Missing historical logs | retained 49 logs, `evidence-retention.json`, `verify_retained_evidence.py` | Clean 191826c export verifies 152 reviewed and 21 source files; missing/tampered logs reject |
| Current coordination identity | linked coordination-identity testing plan | v2 public-path success/mutation proof independently approved; final capture pending |

The corrected M0 WorkPlan records 183 acceptance regressions and final
independent reviews at its July 31 revision. This is historical retained proof,
not a claim that the changing M5 candidate has rerun those gates. Its external
activation-input limitation explicitly does not block deterministic engineering.

The all-23 allocation remains the table in
`docs/work/semantic_ingestion_completion_readiness/closure-plan.md`: R01, R02,
R04-R07, R09-R12, R18, R20-R23 retain completed milestone behavior; R03, R08,
R13-R17 and R19 require the current packages. R05/R06 also enter statistical
coverage. Final candidate regression and independent review remain required
for every retained claim; there is no 23/23 completion declaration here.

Coordinator reproduced split fidelity and the complete v1/v2 self-test on
2026-09-06; the public v2 test checks staged/unstaged/untracked/artifact
tampering. Historical retention checks are recorded separately in
`docs/work/semantic_ingestion_completion_readiness/evidence-retention-checks.json`.
Later source/dependency edits correctly invalidate that old revision-bound
retention check on the current tree. Never replace its historical source pins.
