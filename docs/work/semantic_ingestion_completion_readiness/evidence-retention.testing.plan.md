# Scoped Evidence Retention Repair

- Work type: testing
- Status: complete (local packaging overlay; not yet committed)
- Parent: investigation.plan.md
- Baseline: scoped final-source.json and immutable final-review-candidate.json at191826c
- Scope: retain49ignored logs; map3post-review metadata paths to exact archived bytes; add portable integrity verification

## Contract And Proof

Do not rewrite historical logs, old manifests, gate status, test outputs or source
identity. Add narrow ignore exceptions and a versioned retention map resolving
only metadata whose exact archived bytes hash-match. Verify all152review entries
plus final source hashes from a fresh exported checkout overlaid with only the
intended packaging changes. Missing/corrupted retained bytes must fail. This
repair restores access to historical local evidence, not current hosted success.
No product/test/fixture/dependency or existing workflow mutation. No broad suite
rerun needed for byte retention. Reviewer independently checks portable result.

## Next Action

None for local repair. Include the frozen packaging overlay in the next commit to make it available in PR checkouts.

## Outcome

The verifier checks 152 reviewed files, 21 source files and 49 logs. Coordinator clean
export, corruption, missing-log and restoration checks passed; Ruff/diff checks
passed. Independent test reviewer reproduced a clean archive overlay and missing-
log rejection and found no remaining retention defect. No product/gate outputs
or historic manifests were rewritten. Exact 56-file freeze: evidence-package-candidate.json.
