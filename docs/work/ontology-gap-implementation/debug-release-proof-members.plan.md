# Restore the installed release proof member hashes

- Work ID: release-proof-member-refresh
- Work type: debugging
- Delivery fidelity: Level 2, current PR installed-package gate
- Status: active
- Coordinator: Codex
- Created: 2026-11-27
- Last updated: 2026-11-27
- Parent WorkPlan: [packaged catalog discovery](milestones/packaged-catalog-discovery.plan.md)
- Related WorkPlans: [earlier PR gate repair](../learned-ontology/debug-pr-gates.plan.md)
- Canonical inputs: `.github/workflows/pr-gates.yml`, observation-ledger release preparation manifest, installed proof driver
- Expected outputs: exact candidate member and manifest pins with hosted Package Smoke evidence

## Failure and reproducer

[Package Smoke](https://github.com/nrag/Memorii/actions/runs/46094271168/job/140821939595)
on PR #126 head `665319c0` built and installed its wheel and dependencies.
`run_installed_proof.py` then rejected the checkout with
`proof_candidate_member_changed:memorii/memorii/core/memory_plane/file_lock.py`.
The failure occurs before the protected test host starts. Reproduce by
running the proof driver's manifest/member validation on the exact
candidate bytes. The original candidate self-pin matched.

## Causal evidence and repair

- A failed wheel build, dependency install or new tool runtime was an
  alternative hypothesis. The log shows successful build and install and
  the rejection occurs before the proof host invocation, in the checkout
  SHA-256 comparison.
- Compared all 1,955 existing manifest members to committed bytes at
  `665319c0`. The 18 mismatches are all among the files changed since
  `80fc5852`. Eleven came from storage hardening at `c0fa889a` and seven
  from the ontology candidate. The verifier stops on the first mismatch.
- Refresh the 18 affected entries and the adjacent self-pin.
  Preserve the member set, provenance metadata, installed process,
  acquisition, checks and failure behavior. The replacement manifest
  SHA-256 is `aa8b961815950c75c3607e2602ae76d93403769ab9737c079f2bea6d2b12a6ac`.
  Related historical installed proof and review artifacts keep their
  historical revision identity.

## Verification

The original manifest had zero mismatches against the `80fc5852` Git
archive, 11 against `c0fa889a`, and 18 against `665319c0`. The refreshed
manifest has zero against the latter. The independent reviewer recomputed
all hashes, confirmed no validator or manifest membership changes, and
checked that the live proof and rejection driver carry the new digest.
From `memorii/`, Python 3.12.16 with warnings as errors ran
`python -W error -m pytest tests/integration/test_observation_activation_bootstrap.py tests/integration/test_observation_activation_release_tools.py -p no:cacheprovider -q`.
All 19 tests passed. The hosted `package-smoke` step remains the authoritative full
Linux Python 3.11 acquire, prepare, install, proof, rejection and
benchmark dry-run check. Record the tested PR head, merge SHA and run.

## Next action

Verify the updated installed release proof through Package Smoke on the
pushed repair.
