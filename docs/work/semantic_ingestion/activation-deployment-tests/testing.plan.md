# Activation Deployment Verification

- Work ID: activation-deployment-tests
- Work type: testing
- Status: active implementation; partial subprocess proof
- Coordinator: root
- Created: 2026-09-07
- Last updated: 2026-09-07
- Parent WorkPlan: ../observation-ledger/implementation.plan.md
- Related WorkPlans: ../observation-ledger/milestones/target-authority.plan.md
- Canonical inputs: docs/design/semantic_ingestion_activation_target.md; ../activation-target-identity/verification.md
- Expected outputs: fresh-process bootstrap/release tests, exact path-to-gate map, required package gate wiring and measured evidence

## Objective

Prove the installed deployment checks execute before Memorii import and preserve
all startup/package failure families without placing repeated process or package
construction in fast unit shards.

## Completion Contract

Every matrix family has executable positive/negative proof through the standalone
bootstrap or release command; exact-candidate local package/process checks pass;
Python 3.11 package-smoke CI selects those tests and its required aggregate retains
the dependency. Test reviewer approves final coverage and no accepted existing
case is weakened. CAS success remains in the separate activation packet.

## Scope

Include bootstrap, distribution/RECORD closure, launch/cache/origin policy,
release preparation/signing integration and installed provider target forwarding.
Exclude actual ledger CAS/retrieval implementation and live provider evaluation.
Real production keys/signatures are explicitly deferred; use isolated test keys.

## Constraints And Invariants

No package imports before bootstrap, no mocked canonical verification, no installer
invocation at runtime, and no new signed deployment format. Fresh-process tests
use import/installer sentinels plus exit/error identity; clean wheel tests prove
real installed boundaries. Existing unit vectors keep independent literal bytes.
No claim of CI enforcement until workflow wiring exists and runs.

## Baseline And Inventory

HEAD 191826cd3afb38bf605a337a71d576063b3bae5e, authorized dirty tree. Existing
package-smoke uses Python 3.11, installs one wheel into a target with ambient
dependencies, and lacks no-compile; it cannot prove the new closure. Six unit
shards own isolated core tests. Existing provider composition suite owns actual
provider registry forwarding; new target forwarding cases extend it. Local
Python is 3.12.14. No whole-environment bootstrap test exists yet.

## Matrix And Gate Allocation

| Family | Proof / defect signal | Owner / proposed required gate |
| --- | --- | --- |
| Valid native/package-data/empty files and RECORD scripts | Complete pinned site and script closure passes before import, receipt E matches independent literal recipe | tests/integration/test_observation_activation_bootstrap.py; package-smoke |
| Environment and RECORD integrity | Changed/omitted/extra file, metadata, distribution, duplicate owner, traversal and disallowed external destination reject with import sentinel absent | same integration module; package-smoke |
| Canonical filesystem | Equal/nested/aliased anchors, symlink or special file reject; descriptors bounded and closed | same integration module; package-smoke; isolated lexical cases remain unit |
| Startup/cache/origin | Preloaded package, editable/zip/shadow source, stale package/private-prefix bytecode reject; same-size/same-mtime fresh-prefix control loads current bytes; installed namespace/native roots pass | same integration module; package-smoke |
| Resource limits | At each protected positive cap, exact cap accepts without truncation and cap+1 rejects before import/drain; zero-byte files are accepted and pinned; bounded reads avoid oversized allocation | isolated bootstrap cases plus integration boundary; package-smoke |
| No automatic activation | Start from initialized legacy JSONL, bootstrap and compose with valid target without invoking activation; full storage snapshot remains identical, no activation/head/successor exists | installed integration; package-smoke |
| Read-only startup | Installer sentinel never called during valid/invalid bootstrap | same integration module; package-smoke |
| Prepared release | Verified wheel inputs/no-compile install, exact target bytes/preimage, real isolated signature/public key, tamper rejects | tests/integration/test_observation_activation_release.py; package-smoke |
| Installed provider | Actual installed bootstrap -> host config -> provider shares target; invalid target fails without storage mutation | integration package runner; package-smoke; successful successor deferred to CAS packet |

The design's illustrative unit-shard placement for subprocess families is refined
here to the dedicated package gate under design-tests; behavior/coverage remains
unchanged. Exact local commands and machine-readable path map will be frozen
once callable bootstrap/release interfaces and test files exist. Planned commands
are not executed evidence. Package-smoke is already a required dependency of the
existing aggregate; no new optional-only gate is acceptable.

## Delegation And Cost

Root owns this test plan, test files, workflow edits and all long commands.
Terra bootstrap_writer owns only standalone bootstrap source and deployment docs
under the implementation parent. Standard test reviewer reviews this matrix
before substantial test coding, then one frozen test delta after evidence exists.
No concurrent test writer. No duplicate broad suite runs without new changes.

## Evidence And Open Work

Core target tests currently prove signature/package/parser mechanics; actual
provider forwarding has three passing cases (17.40s). These use temporary package
files and isolated host metadata, so do not establish installed startup policy.
No bootstrap/package subprocess proof, release tool or CI changes exists yet.

## Next Action

Complete missing installed-wheel, release, boundary-cap and no-trigger families in the approved matrix.


## Implemented Subprocess Evidence

Root implemented tests/integration/test_observation_activation_bootstrap.py with
one positive two-distribution/script/namespace/empty-file closure and13negative
cases. Final14cases pass9.55s. These are synthetic installed fixtures in real fresh
processes, not whole-candidate wheel certification. Runtime import guard inspects
normal finder results before execution and verifies preloaded selected dependency
origins. Exact local command, current package-smoke selection and explicit missing
families are recorded in path-to-gate.json. The package job remains required by
its existing aggregate; GitHub execution has not been observed here.

Matrix reviewer changes (exact cap accepts, cap+1rejects; no-trigger JSONL snapshot
unchanged) were confirmed and incorporated before subprocess tests. Their full
execution proof remains open. No testing-operation closure is claimed.

## Release Preparation Verification

Five operator subprocess cases reject wrong wheel pins, existing destinations,
wrong launcher pins, missing process isolation and symlink modules before side
effects. Combined with existing bootstrap and conversion checks: 21 passed in
15.79s. Package-smoke wiring includes the operator tests; CI is unobserved.
The real wheel proof verified 21 distributions, 5632 installed files and 1772
Memorii payload files, full publication/target resolution, valid/corrupt signatures,
and four protected-pin/installed-file mutations. Evidence and reproducible drivers
live under ../observation-ledger/release-preparation/. Full cap/no-trigger matrix
and overall testing-operation closure remain open.
