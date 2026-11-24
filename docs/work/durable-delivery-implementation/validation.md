# Delivery Validation, Identity And Change Ledger

## Changes And Authority Inventory

The approved design identity ledger and the parent [identity and change ledger](../durable-memory-implementation/identity-and-changes.md) are the baseline. Before writing, enumerate exact artifacts and registered fields from the live code below. The list defines affected families. It does not certify current generated parity.

| Family | Existing owners and affected descendants | Identity/classification and proof |
| --- | --- | --- |
| Origin, host result and decision | runtime_contracts, runtime_api, sidecar, core/harness_state/client.py, spool and runtime_consume | Behavioral OperationOrigin, Memorii-Operation-Origin, prepare/read/decision routes and closed result/digest fields. Keep historical v1 bodies. Add explicit managed proof requirement with fail-closed legacy behavior. |
| Canonical result, scope and payload | Consolidator, runtime event schemas and replay | Behavioral ConsolidationOutput, ArchivePackageRef, ProtectedSkillCandidate, output discriminators, exact selector fields, canonical digest domains and closed target variants from design. Verify exact roundtrip and reject unknown fields/discriminators. |
| Signed partition and backup | runtime_repository, partition catalog definitions, StorageAdministrationService, SQLite memory batch and control/restore | Behavioral consolidation_results, writeback_decisions, runtime_work_projections, runtime_target_receipts, runtime_skill_candidates and delivery_restore_holds. Inventory every catalog in manifest, signing, checkpoint, replay and backup. Preserve legacy queue bytes via reviewed format-version path. |
| Real owner composition and installed surface | work-state, provider candidate owner, managed sidecar/embedded/spool, host factories, runtime_schema_export, sdk/typescript, package metadata | Regenerate OpenAPI/client/tool metadata. Pin exact digests, union cardinalities and installation inventories. Plan/requirement IDs are traceability only. |
| Reference fixture and evidence | current smaller capacity test and Linux/macOS gates | Behavioral reference_capacity, balanced and concentrated, generator and manifest hashes, fixture coordinate/digests and output metrics. Preserve existing smaller regression. |

Existing canonical semantic schemas, provider native capture, promotion policy and benchmark policy remain controlling. Parser coverage includes wrong discriminator, unknown or duplicate keys, missing fields/credentials, wrong digest, wrong domain/scope, altered wire context, numeric limits and canonical form parity. Field-aware hygiene mutation families include planning coordinates in every affected schema/SQL/route/client/test/gate field and valid v1/behavioral controls. No new exceptions. Establish exact output file names and registry cardinalities before coding using actual generated ownership, rather than assigning them from milestone numbering.

## Test Families And Failure Signals

| Proof | Layer | Observed failure if implementation violates design |
| --- | --- | --- |
| Origin authenticity, stable digest and non-rebinding | Unit plus installed HTTP/embedded/spool parity | A malformed, missing, mismatched or old proof dispatches or a valid identical receipt is rewritten |
| Full-state output, producer evidence and same-kind identity | Contract and restart integration | Unverified producer inputs emit output, archive has missing closure, persisted bytes drift or replay differs |
| Host selectors, current eligibility and explicit accept/decline | Public integration and SDK contract | Unauthorized offer, ID or count leaks, conflict overwrites decision, decline enqueues or accepted effect appears before publication |
| Projection and candidate targets, claim lease and scope | Public integration and independent-process concurrency | Wrong target writes, skill leaks into ordinary retrieval, obsolete projection wins, stale lease commits or mode/revoke loses the ordering guarantee |
| Commit, lost acknowledgement, exact receipt and tamper | Subprocess and signed publication/reopen | Partial effect/receipt/queue state is served, retry duplicates effect, damaged closure is accepted |
| Older/current/fresh restore and digest-only upgrade | Installed release/operator journey | Generation rewrites an old intent, queue drains under hold, original bytes are lost or stale state overrides grant/forget authority |
| Capacity at approved workload, both distributions and OSes | Installed engineering qualification | Counts/digests diverge, timed scope changes, failed operations disappear or unsupported threshold claimed |

Before substantial additions use a linked design-tests WorkPlan for placement, failure cut harness, shard timings, runtime budget and required gates. Keep contract unit cases fast. Use real owner boundaries and process isolation for atomic publication, restore and evidence. For independently reproduced replay, a separate implementation must not import or copy the production reducer or projector. Shared frozen canonical input bytes are allowed where approved.

## Verification Commands And Evidence

Each milestone lists existing exact Python regression commands. From memorii/ use the workflow-matched interpreter and dependency extras. For static and identity checks use:

```bash
python -m ruff check memorii tests
pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
python -m memorii.tools.identity_hygiene --root .. --allowlist ../.agents/identity_hygiene_allowlist.json
```

From sdk/typescript on the pinned workflow matrix:

```bash
npm ci
npm run check:generated
npm run typecheck
npm test
npm run build
npm pack --dry-run
npm run test:installed
```

The current .github/workflows/pr-gates.yml contains package-smoke, durable-storage-integration, durable-runtime-integration, sdk-typescript, host-container-certification and macos-platform-conformance. Match current job definitions and aggregate dependencies. Durable integration uses Python 3.11, and schema regeneration and host/OS jobs use Python 3.12 where declared. SDK CI currently tests Node 24 and 26. Establish the exact candidate script/environment/working directory and capture all applicable job families and artifacts. Existing gate inventory is a baseline and does not include the new suites. Run exact candidate suites once after readiness. Document known unavailable dependencies and CI access separately from failures. No clean-base failure exemption is asserted. Existing CI results and old probes do not certify the new product.

Before release run the installed reference capacity generator and runner approved in the linked testing WorkPlan, then record exact command, fixture/input hashes, both distributions on both platforms, independent sample evidence and status. Neither runner nor command exists today. The parent owns the exact-release candidate. Any generated or code change after final review invalidates affected proof.

## Planning Fingerprints And Review

Read-only current artifact fingerprints at 4c390de1:

| Artifact | SHA-256 |
| --- | --- |
| .github/workflows/pr-gates.yml | e0bc6d3f356a6be4232ad3f5f92baadf963eb718f0aec54a6ce0cec96ecbc328 |
| memorii/pyproject.toml | 584b0c4a0ff8a64387b73ccbc73cd77de1df3eec032f79749bf1be26f3539b5d |
| sdk/typescript/package-lock.json | 4ca656fca847db175406497ddcd5a64332f34b733b833704b18c6481f48c43a9 |
| sdk/typescript/generated/openapi.json | aac8fbfdfca395d25630787d844144c72d0de9582b9ddeadddd751b8db6a4c46 |

These are source identities, not a parity result. The coordinator verified the design SHA, five milestone packets, document links and every named existing regression path. The independent test reviewer identified a verification wording error about distinct same-kind outputs. The coordinator corrected the packet to accept distinct ordinals and reject duplicate identities or divergent replays. The rollout gate now explicitly follows delivery and restore proof. Future exact new test and gate identities stay with the linked test-architecture work.

The test reviewer approved the corrected planning delta. This closes the plan-only consultation. High-risk product work still requires review of the actual proposed test inventory and current bindings before coding, then the candidate review required by the implementation skill. This operation did not run product or release tests.

## Local Implementation Evidence

- The intermediate 494508d3-based worktree ran 139 Python tests. This covered the durable-runtime integration selection, the existing measured capacity regression, and focused managed, storage and schema suites.
- After review fixes, the local macOS Python 3.12 check ran 85 focused tests from `memorii/` with warnings as errors and the pytest cache provider disabled. The selection covered `test_consolidation_read_sidecar`, `test_runtime_sidecar`, `test_managed_work_projection`, `test_managed_delivery`, `test_storage_administration_operator`, `test_managed_operation_origin`, `test_managed_task_lifecycle`, `test_runtime_candidate_stage`, `test_runtime_consolidation_outputs`, `test_consolidation_catalog`, `test_reference_capacity`, and `test_runtime_schema_export`.
- The Node 26 clean temporary SDK install passed typecheck, nine tests and package dry run. The checked-in OpenAPI document passed byte parity with the live Python generator. The identity audit passed on the preceding worktree.
- The bounded correctness and specification reviews reproduced the older-backup replay, pre-pause claim reuse and unsigned CLI path. Follow-up patches cover these cases and add task suppression, exact terminal claim matching and closed read errors. They are interim product proof. The final three-role phase reviews, applicable CI and Linux/macOS installed capacity qualification are still open.
- At committed 91fd5720, 144 Python tests passed on macOS, covering the complete durable-runtime job's test selection, the existing smaller capacity integration regression, the operator suite and focused managed unit tests. This local run used Python 3.12. The CI durable-runtime job uses Python 3.11 on Linux.
- On the subsequent codec and historical-reservation patch, all 13 focused replay tests passed on macOS, including tampered solver scope, a divergent version behind the current head and mixed repository batches.
- At a1493f12, the same combined Python selection passed 147 tests. The OpenAPI byte comparison and identity audit passed on that revision. This is local regression evidence. Host container certification and release qualification remain open.

## SQLite Journal And Delivery Continuation

| Increment | Revision | Local evidence and limits |
| --- | --- | --- |
| Signed SQLite journal and replay indexes | 52eeaa56, cc000844, c90b9210 | Actual root/solver projection replay after reopen, memory interleave, conflict rollback and pending-intent verification before finalization. Reproduced cache and signed-revision discrepancies and added regressions. V1-v3 catalog bytes remain readable without synthetic history. Full business-event coverage and signed migration ancestry remain open. |
| Bounded managed resume | c004994f, 98099c48, ee3d92ee | Source-free root resume verifies an exact pause archive and receipt. General checkpoint counters and current member bytes are authenticated. General checkpoint-plus-tail serving remains open. |
| Host accept and decline | 890fd5c0 | Signed loopback requests, exact retry, opposing requests, rollback and suppression. Tool-facing decision path remains separate from model tools. SDK typecheck, ten tests, package dry run and installed tarball passed. Generated OpenAPI byte parity passed. Fixture result used for the source-bearing test. |
| Local target effects | 65d6a139 | Four candidate kinds through the explicit enrolled target worker. Independent tests covered atomic rollback, exact receipt retry, forbidden generic writes and promotion, suppression and stale claim refusal. Signed digest-only legacy rows cannot call the old callback. |
| Restore staging | c9499043, e97e5d60 | Verified signed watermark, signed capture and staging refusal for stale, swapped or corrupted input, and owner CLI staging. Managed backup activation and delivery hold reconciliation remain open. |
| Capacity diagnostics | be72d24f | Installed wheel match and small signed fixture smoke. Exact reference qualification unavailable until native source receipts and signed checkpoint-tail replay exist. No platform timing evidence. |

The continuation runs used macOS arm64 and Python 3.12, with warning promotion and the pytest cache provider disabled. The workflow selections remain responsible for Linux Python 3.11 CI evidence. The existing durable-runtime integration job now names both new journal and candidate suites. Scoped reads, CLI staging, signed delivery and diagnostic fixture runs do not satisfy host container, release-branch or capacity certification on their own.

At clean product revision ee3d92ee, the final focused Python selection passed 211 tests in 15.21 seconds. It included the durable-runtime integration selection, runtime and partition recovery, migration recovery, operator and writeback suites, and the smaller capacity regression plus reference fixture tests. The repository identity audit and pinned artifact byte check also passed.
