# Diagnose unavailable bill recall after managed reopen

- Work ID: ontology-read-retained-source-recall
- Work type: debugging
- Delivery fidelity: Level 2
- Status: complete (Level 2)
- Coordinator: main Codex task
- Created: 2026-11-27
- Last updated: 2026-11-27
- Parent WorkPlan: [catalog inspection and recall implementation](implementation.plan.md)
- Canonical inputs: `docs/design/learned_ontology.md` Sections 12 and 13, and the retained-source admission and seal contracts enforced by `SemanticIngestionAtomicStore`

## Objective

Recall a current bill from authorized retained source history after a managed
store reopen. Preserve corruption, authorization and suppression behavior.

## Reproducer and Causal Evidence

`tests/integration/test_scoped_context_production_binding.py::test_installed_catalog_read_workflow_needs_no_key_or_write_tool`
provisions four facts through the packaged Hermes bridge, disables the write
tool and reopens both read roots with no key. In the provenance candidate
`/private/tmp/memorii-ontology-verified-ap2d9qt2`, the first inspection
matched and bill diagnosis returned `unavailable`. The remaining 145 tests
passed. The copied SQLite partition from that failed case let the correctness
reviewer trace the verifier without another capture.

| Hypothesis | Observation | Decision |
| --- | --- | --- |
| Missing source, commit history or endpoint evidence blocks recall. | Source authority, group entry, group seal and stored endpoint checks passed. | Excluded for the reproduced case. |
| Analogous original and derived admission fences differ legitimately. | The index binds the original captured-turn fence. The immutable bill commit binds the derived retained-source fence. Source, principal and delivery coordinates match. Their distinct fence IDs fail the equality check. | Confirmed. |

## Correction and Verification

Pass the immutable snapshot lookup to the existing retained-source fence
validator from the catalog-bound path. It checks the stored link, admission
digest, original and derived source and delivery identity, and required
scope set. Keep the legacy exact-fence requirement and register the retained
link as a suppression dependency. Reuse the same validator with its live
getter for the existing writer-side caller.

The correctness reviewer reran the native proof against a copy of the
managed SQLite store from the final pre-fix candidate. The complete snapshot
verified successfully. Removing the retained operation links from the
same in-memory snapshot failed closed and retained their suppression
coordinates. The fixture and repository storage were unchanged.

The corrected integrated candidate passed the 146-case scoped-context
suite, including managed bill recall after reopen through each host.
The 401.56-second acceptance case used no API key, outbound transport or
write-tool authorization during reads. It also checked suppression after
assembly and missing versus suppressed fanout evidence. Full local Package
Smoke passed with the corrected source pinned. The checked source is
`0bbc68a2` plus the scoped dirty tree digest
`60da70235eccce0c924c3edc83d28b013588f8f2fb8a0c2672faa4fb8c7c2880`.

## Outcome

The original-to-retained fence proof now permits authorized recall on the
managed store. The focused correctness re-review confirmed fail-closed
behavior on a missing retained link. The parent implementation plan owns
the remaining branch gates.
