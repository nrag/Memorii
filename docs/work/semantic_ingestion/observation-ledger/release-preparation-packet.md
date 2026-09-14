# Deployment And Target Preparation

Implementation continuation, baseline HEAD191826cd3afb38bf605a337a71d576063b3bae5e
plus existing authorized dirty tree. Governing target design unchanged. Parent:
milestones/target-authority.plan.md. Testing: ../activation-deployment-tests/testing.plan.md.

## Bounded Interfaces

Standalone tools/observation_activation_prepare.py owns protected WheelInput rows
(path, expected SHA256, explicit top-level roots), offline no-compile installation
into a fresh prefix, and installed RECORD/file inventory. Wheel name/version come
from the already digest-verified METADATA. Destination must not exist. It invokes
pip with --no-deps --no-compile --no-index --ignore-installed --prefix and only
verified private wheel copies; no environment install occurs at runtime bootstrap.
It emits a Python host configuration module using validated frozen constructor
literals, plus a byte-identical copy of the independently pinned bootstrap module.
This is trusted deployment code for operator review, not JSON or a new signed
configuration format. Existing files never overwrite silently. A fresh process
loads that protected module, verifies deployment and installs the origin guard
before importing any Memorii module. The host supplies protected configuration;
requests/environment never select it.

Core observation_activation_preparation.py owns explicit structural protocols for
bootstrap row/config/facts conversion to existing core typed config/receipt,
receipt identity validation, and unsigned manifest construction from an actual
installed payload plus VerifiedTypedValuePublication. It reuses exact identity,
manifest parser/preimage, package and receipt owners. No authority or persistence
is granted by preparation. PreparedObservationActivationTarget retains exact raw
manifest/preimage and identities, with explicit fields and no mutable dict blob.
ObservationActivationPreparationInputs holds core configuration, receipt and
verified publication for the protected release-host factory.

Packaged memorii.tools.semantic_ingestion_activation_target_release is the thin
operator adapter. prepare --host-factory module:callable --target-id ID
--signature-profile-id ID --public-key-digest SHA --output-directory NEW writes
new target-manifest.json and target-preimage.bin. The trusted factory returns
ObservationActivationPreparationInputs; it is not a runtime request plugin or
JSON config. The host launcher must bootstrap/guard before loading this CLI when
proving installed execution. verify --manifest PATH --signature PATH --public-key
PEM --profile-id ID --public-key-digest SHA --digest-domain-file PATH uses existing
PEM/key binding and exact preimage verification. Signatures are provided by the
existing offline sign-preimage command; no keys are created by production code.

## Proof And Ownership

Root owns standalone installer/preparer, docs, all integration tests/commands,
workflow, generated artifacts and evidence. One Terra worker owns the three
new core/packaged-tool/unit-test files only. Existing bootstrap is root-owned.
No other writers. Frozen design/test matrix already requires these boundaries.
New process/wheel tests stay in package-smoke under the linked testing operation.
Positive proof must build/install the current wheel and required dependency
closure, bootstrap fresh, convert typed facts, prepare manifest, exercise isolated
signature verification, and reject wheel/payload/pin tampering. Synthetic files
alone cannot complete full installed proof. Production signing and CAS remain
explicitly deferred to their existing boundaries.

## Preflight Reconciliation

Spark identified reusable parser/identity/signing APIs. Its claimed existing
conversion owner and production prep caller counts are unsupported: conversion
and prep are missing and implemented here. Existing resolver checks already
constructed core config/receipt and grants no conversion. Atomic CAS remains
unimplemented. No local wheel cache inventory was delivered by mapper; root owns
that check. No owner decision or actual-signature blocker exists.

## Next Action

Resume the durable activation CAS packet with the locally verified prepared
target context; this bounded release preparation slice is complete.

## Current Candidate And Review Reconciliation

Candidate release-preparation/candidate.json SHA256
9c679101db12999a3edb9d38b07be612384ba97bdc9ad57e6eea8afef4e5cfc1 pins
1912 files including package, registry inputs, proof drivers and CI workflow.
The initial review candidate is retained as candidate-initial.json. Root owns all
writes/commands after the Terra worker handoff. New protected launcher executes
only hash-verified bytes under -I -S and bootstrap before host imports.

Spec and test reviewers independently confirmed missing real-wheel CI enforcement,
proof-input identity binding and production-triggered authority mutation coverage.
These are confirmed Not applicable / changes_required / verification findings.
The assertion that the rejection driver was absent became stale during root's
parallel construction; it now exists and tests recorded payload, dependency,
protected configuration and host pins with an untouched host sentinel.
Consolidated remediation adds full package-smoke execution and retained evidence,
a pre-install mutation of the real candidate wheel, full verify argument failures,
and candidate-bound source/driver/generated-host/module/wheel/log identities.
Root also corrected pre-IO aggregate limits and an anchor descriptor failure path;
exact-limit/cap+1 tests are included. Final local focused suite:25passed16.41s;
Pyright:0errors0warnings. Final real-wheel refresh and delta review are active.

A distinct correctness reviewer could not be restarted because the agent service
returned "agent thread limit reached". The initial attempt inspected nothing due
to an overly restrictive task instruction, which root corrected immediately.
The active independent spec reviewer also inspects concrete correctness; do not
claim three distinct completed reviewer roles from this combined review.

The existing Terra activation_target_writer agent was successfully reassigned
to read-only correctness duties for the new preparation files it did not author,
after creation of a fresh correctness agent failed. It is not reviewing its
earlier target-owner implementation as a new approval unit. Root retains all
writing/testing ownership. This restores independent correctness coverage without
claiming a new agent or hiding the resource constraint.

## Bounded Completion

Final candidate0c75be24918302760a7e91c091896b786cf5d28187947d0b6d37a41a5ab88039
is approved by independent spec and test reviewers, with independent correctness
coverage recorded in release-preparation/review.md. All confirmed findings are
resolved. Final real-wheel run and five installed mutations passed. The test
portfolio reports25focusedpasses plus5finaloperatorpasses after the cleanup-only
delta; both Pyright runs and Ruff pass. closure.json binds retained evidence,
including a portable archive of generated protected modules and public test
artifacts. No private key is persisted. CI is wired; execution is unobserved.
This supersedes earlier active-review/refresh paragraphs. It closes only the
preparation slice, not target-authority, activation CAS, R17, or M5.
