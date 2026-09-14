# Current Coordination Identity Verification

- Work ID: semantic-ingestion-coordination-identity
- Work type: testing
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-09-06
- Last updated: 2026-09-06
- Parent WorkPlan: `docs/work/semantic_ingestion/engineering-closure/implementation.plan.md`
- Canonical inputs: `.agents/scripts/verify_workplan_split.py`; historical v1 identity and pin
- Expected outputs: v2 current identity capture and fail-closed verification

## Objective

Repair only current dirty-tree identity verification. Preserve historical v1
identity bytes and validation unchanged while a v2 identity excludes exactly
its own JSON path and its SHA-256 pin from Git-derived evidence.

## Test Contract

The v2 verifier must reject broad or renamed exclusions, self-listed
coordination artifacts, changes to any other tracked, staged, untracked, or
artifact file, and identity/pin rename. The v1 self-test remains unchanged.
The focused owner is the verifier self-test; expected runtime is under ten
seconds and it is not a product or hosted-CI gate.

## Capture Helper

`capture_current_candidate_identity(root, relative_path, artifacts, created=...)`
creates a v2 identity and pin. `relative_path` excludes only itself and
`relative_path + ".sha256"`; artifact paths must never include either path.

## Result

The v2 pathspec uses `:(exclude,literal)` for status and both diff commands.
It validates normalized, contained identity and pin paths before capture I/O,
rejects self aliases and non-object artifact entries, and preserves v1
validation. The focused self-test covers literal `*?` identity filenames with
sibling tamper detection, staged and ordinary unstaged tracked mutation,
untracked mutation, artifact tampering, broad exclusions, self aliases,
traversal without outside writes, malformed artifact entries, and rename.

Classification: `Not applicable` / `changes_required` / verification. This is
a bounded contract-conformance action and creates no product behavior claim.

## Review Reconciliation

Correctness and test review confirmed one evidence action: the v2 fixture must
bind a copied temporary manifest to a v2 identity and pin, then call public
`verify(manifest)` successfully. It must also prove a staged tracked-file
change that leaves porcelain unchanged fails at tracked/staged diff comparison,
and artifact mutation fails at the artifact digest. The prior dead-code claim
is unsupported and retracted: both identity versions are invoked by self-test.

## Evidence

Run:

```bash
python3 -c "... mod.verify(manifest, verify_candidate=False); mod.self_test(manifest)"
python3 -m ruff check .agents/scripts/verify_workplan_split.py
git diff --check
```

The historical v1 candidate remains frozen and is not used to claim
current-tree verification.

Final focused evidence: the public copied-manifest v2 verification, v1/v2
self-tests, and isolated fidelity verification passed. Ruff and
`git diff --check` passed; historical v1 identity and pin bytes are unchanged.

## Next Action

No further action in this testing operation. A later linked closure may capture
a v2 current identity for its exact candidate.
