# Design Review: Layer 1 Validator Collection Grammar Closure

## Review Metadata

- Review ID: semantic-ingestion-layer1-validator-collection-closure-delta-06
- Review mode: delta
- Review outcome: Changes required
- Design path: `docs/design/semantic_ingestion_architecture.md` plus the linked executable validator and checker
- Design baseline: architecture SHA-256 `67bf2620a0379761853861e416efba0816045ef4bf88e4808e701a9ac3bc993e`; validator candidate SHA-256 `facdcbd13c3149b5e481ab5d676a24694882d9a1c16200e2b51016222de97d44`; checker candidate SHA-256 `a79736c0df54e6952f452c3004b22d6107457636566238dbf03e92fc3256257b`
- Implementation baseline: `945d6ea03649ca13c800e84bcb9972797e0f0a31` with the current working-tree Layer1 candidate
- Review date: 2026-07-29
- Reviewers: fresh `spec_auditor`, `correctness_reviewer`, and substitute fresh `test_reviewer`; coordinator reconciliation
- Included scope: captured-snapshot execution, audit denial, interpreter isolation, directory-open state, and content-addressed handoff
- Excluded scope: implementation consumer repins and remote CI execution

## Executive Assessment

Snapshot-only execution, directory-open state proof, atomic publication, and
the substantive audit boundary are correct. Two isolation changes remain:
the authoritative checker command starts outside Python isolated mode, allowing
same-directory stdlib shadowing before self-hash verification, and the negative
audit assertion does not bind its expected failure to the exact injected path.

## Governing Sources

- Root `AGENTS.md`, `.agent/PLANS.md`, and the build/review Design Skills
- `docs/design/semantic_ingestion_architecture.md`, Section 3.23.4.2.1
- `docs/work/semantic_ingestion/layer1-validator-collection-closure-2026-07-29/design.plan.md`
- Immutable delta reports 01 through 05

## Independently Reconstructed Requirements

| Requirement | Source | Design coverage | Acceptance criteria | Verification | Status |
| --- | --- | --- | --- | --- | --- |
| VLC-001 | Closed unary collections | Complete | Invalid shapes reject | Self-test and exact checker | locally verified |
| VLC-002 | Closed tuple grammar | Complete | All finite/variadic/boundary forms proved | Self-test and exact checker | locally verified |
| VLC-003 | Content-addressed isolated checker | Partial | Interpreter isolated before imports; exact audit known-answer path | Isolated entrypoint and exact-path negative probe | changes required |
| VLC-004 | Fail-closed compatible publication | Complete | Complete failure and filesystem-state matrix | Deterministic self-test | locally verified |

## Contract And Evidence Boundaries

Python interpreter isolation must exist before the checker imports any module,
because checker self-hash validation occurs afterward. Negative audit evidence
must identify the exact attempted path so an unrelated denial cannot produce a
false known-answer result.

## Confirmed Findings

### DREV-013: Checker starts outside Python isolated mode

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: security / authority isolation
- Affected scenario and prevalence evidence: The documented checker command executed from a checkout containing a same-directory stdlib-shadowing module; this is trust tooling without a product-prevalence claim.
- Design location: `docs/development/static_tooling.md` checker invocation and checker startup
- Governing source or requirement: VLC-003 content-addressed, stdlib-only isolation
- Expected behavior: The interpreter excludes the script directory and environment/user import paths before the checker imports dependencies or validates its own bytes.
- Design behavior: The documented command invokes `python3.12 checker.py` without `-I`; imports execute before self-hash validation.
- Evidence: Python script execution prepends the script directory to `sys.path` without isolated mode. A sibling `hashlib.py` can execute before checker identity verification. The validator child already uses `-I`.
- Impact: An unpinned sibling can alter or bypass checker behavior before any content-addressed assertion.
- Root invariant or contract boundary: Verifier bootstrap isolation precedes verifier identity and dependency use.
- Equivalence class and adjacent bypasses inspected: Script-directory shadowing, environment Python paths, user site, validator child isolation, deliberate checker-source modification, and parent workflow handoff.
- Positive behavior that must remain valid: Plain Python 3.12 stdlib operation, exact checker self-hash, two replicas, and readable diagnostics.
- Recommended invariant-level resolution: Make the canonical command use `python3.12 -I`, require `sys.flags.isolated` in the checker, and add a same-directory shadow-module regression probe. Carry `-I` into the parent implementation handoff.
- Verification needed: Exact pinned command under a deliberate sibling stdlib shadow, plus normal authority reproduction.
- Evidence maturity affected: VLC-003 approval

### DREV-014: Audit negative proof is not bound to the injected path

- Product priority: Not applicable
- Approval disposition: changes_required
- Confidence: high
- Finding type: verification / authority isolation
- Affected scenario and prevalence evidence: Checker negative known-answer execution where another audit event fails before or instead of the injected read; this is verification behavior without a product-prevalence claim.
- Design location: Checker `validate_audit_denial()`
- Governing source or requirement: VLC-003 negative audit evidence
- Expected behavior: The seeded file, injected read, and asserted denial diagnostic identify the same resolved path.
- Design behavior: The injected validator reads `root/undeclared-probe.txt`, while the checker seeds `parent/undeclared-probe.txt` and accepts any stderr containing `undeclared file access`.
- Evidence: Direct comparison of probe injection, file creation, and generic diagnostic assertion.
- Impact: An unrelated denial can satisfy the test while the intended path is allowed.
- Root invariant or contract boundary: A negative known-answer result must be bound to the exact operation under test.
- Equivalence class and adjacent bypasses inspected: Probe identity, bootstrap installation, exact read path, generic denial, authority mutation, and temporary cleanup.
- Positive behavior that must remain valid: Import-valid probe, real bootstrap, nonzero exit, unchanged authority, and no temporary sibling.
- Recommended invariant-level resolution: Seed `root/undeclared-probe.txt` and require stderr to include `undeclared file access: <resolved exact path>`.
- Verification needed: Real probe execution with exact-path assertion; an unrelated denial must not satisfy the result.
- Evidence maturity affected: VLC-003 negative audit proof

## Requirements Coverage

VLC-001, VLC-002, and VLC-004 are locally verified. VLC-003 requires the two
bounded isolation corrections.

## Architecture And Feasibility

The changes are narrow: canonical `-I` invocation, an early isolated-mode
assertion, one interpreter shadow known-answer, and exact audit-path binding.
No normative architecture, validator behavior, authority, or implementation
runtime changes are required.

## Failure, Security, And Operations

`-I` protects against script-directory, environment-path, and user-site import
influence. It does not make deliberately changed checker bytes trustworthy;
the external expected checker hash remains required.

## Verification And Evidence Maturity

The exact checker otherwise passes at `facdcbd1...` / `a79736c0...`, with
unchanged authority `89a98fc1...`, 56 schemas, 240 enum rows, and profile
`20edd38a...`.

## Risk Register

| Risk | Trigger | Impact | Mitigation | Residual risk | Status |
| --- | --- | --- | --- | --- | --- |
| Pre-hash import shadow | Sibling stdlib-named module | Checker bypass | Canonical `-I` startup and regression probe | Low | open |
| False audit known-answer | Unrelated denied operation | Isolation regression hidden | Exact seeded/injected/diagnostic path | Low | open |

## Rejected Or Consolidated Findings

DREV-011 and DREV-012 are resolved. The original test reviewer inspected an
unrelated production checker and was not counted; a fresh substitute reviewed
the exact design checker and approved the bounded evidence. Parent consumer
repins remain deferred implementation work.

## Required Changes Before Approval

Close DREV-013 and DREV-014, rerun exact isolated gates, then conduct the final
fresh three-role delta review within the remaining budget.

## Non-Blocking Follow-Ups

After approval, the parent implementation must use the exact isolated command,
repin all consumers, run the public CLI matrix, and obtain remote CI evidence.

## Final Outcome

Changes required.

## Review Limitations

Remote CI was not executed.
