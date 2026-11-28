# Release design verification and entrypoint bindings

Current code and fixtures are baseline evidence. Every proposed callsite below
requires an installed witness in the implementation plan. Trace authority to
its verified owner before changing schema or signing formats.

## Entrypoint bindings

| Trigger | Current binding | Proposed owner arguments and durable outcome | Failure behavior |
| --- | --- | --- | --- |
| Installed owner initialization/enrollment | Operator parser and `StorageAdministrationService.initialize` exist. `hostcompat/managed_host_journey.py` constructs the task and read callback directly. | Operator principal/capability, stable operation ID, exact selected task and native source, expiry, private handoff path -> task creation/publication owner, credential and grant registries -> signed command receipt and committed scoped enrollment. | Missing/wrong owner or binding, incomplete issuance or nonprivate path deny. Exact retries reconcile issued or revoked credentials without disclosing old bearer bytes. |
| Start, state and source read | `RuntimeSidecar.for_managed_installation`, `serve_loopback`, `NativeSourceService` accept a principal-only grant callback. | Installed operator passes verified storage and authenticated credential-bound resolver. Payload release uses the exact current task/source/epoch. | Verify modes, source mismatch, expiry and revocation again before release. |
| Independent control export, backup, restore | `BackupRestoreOperator` pins verified WAL views. Archive metadata provides integrity stubs. Legacy boot refuses managed storage. | Admin owner + configured independent head -> validated participant owners and key owner -> sealed bundle/anchor, read-only checked restore plan, authorized stage and private cutover -> signed selected generation, delivery hold, current security epoch. | Missing signer, forked/stale/pending authority, unverified old-host isolation, incomplete snapshots or plan drift deny activation. |
| Signed native capture and owner drain | `NativeSourceService.capture` scans `ManagedRuntimeSpool.pending`. Legacy CLI argument profiles exist. | Exact proof coordinate, typed task scope/state and prior durable receipt -> indexed private spool / public command owner -> admitted or committed receipt through current authorization. | No ack before durable admission. Refuse stale/revoked dispatch and preserve expected pending evidence. |
| Recall/admission | Runtime receipt JSON query uses namespace/prefix filters and sorting. | Verified generation + authorized namespace/task/source -> explicit verified SQLite index, ordered bounded receipts -> existing release-time grant and source eligibility. | No unsafe fallback or partial response when required proof is unavailable. |
| Catalog tool | `ProviderMemoryService` through `catalog_read_workflow` and SQLite owner's full validated snapshot. | Current authenticated subject and selected scope/version -> typed bounded closure and existing catalog/fact owner validators -> unchanged response models protected at release. | Grant denial, missing child proof, corrupt or out-of-budget closure fail closed. Legacy backend retains semantic parity. |
| Packaging and release | `memorii/pyproject.toml`, host Dockerfiles, `pr-gates.yml`, reference-capacity workflow. | Clean commit + pinned sources, exact wheel/SDK/image/dependency hashes -> existing build owners, scan, platform and host gates -> release manifest with whole-candidate approval. | Missing or mismatched artifacts, runner or decision leave release unqualified. |

## Authority mutations and durable contracts

Managed serving requires registry membership and all advertised mutators to
have a custody entrypoint. Value validation precedes pending publication.
Protected acknowledgement follows local effect and independent seal. Each
row gets a distinct installed partial-write test.

| Participant | Current mutation owner | Local proof and required binding |
| --- | --- | --- |
| Read grant and credential | `GrantEpochRegistry.revoke`, `SidecarCredentialStore`, installed enrollment/rotation | Expected epoch and credential ID, resulting denial/issuance and audit record. Link split epoch and journal writes before either takes effect. Bundle excludes secrets. |
| Command and native source release | `HostCommandGrantRegistry`, signed source-release owner through `runtime-grant` / `runtime-source-grant` | Owner capability, exact task/source and signed before/after registry/event reference. Unknown scope never widens. |
| Forget and erasure | `GovernanceOperator`, suppression journal, backup lifetime guard | Exact suppression sequence, pending epoch increment and signed retention or erasure receipt where supported. |
| Mode, trust and storage selection | `StorageAdministrationOperator.change_mode`, `StorageAdministrationService`, trust/key owner, `BackupRestoreOperator` | Control revision and signed journal before and after mode/trust/participant change and every same-installation or fresh-host selector change. |
| Provider, writer and catalog authorization | `WriterEnrollmentRegistry`, provider authority owners, `SemanticIngestionAtomicStore` structured grant mutation | Sealed current owner membership, terminal denials and structured grant revocation rows through the signing publication owner. Ordinary facts stay on their data path. |

New recovery and spool grammars use `protocol_version: Literal[1]`, typed IDs
and positions, canonical lower-case digest/signature encodings and existing
generation/signer validators. Freeze these field groups before coding.

| Boundary type | Required fields and transitions |
| --- | --- |
| `InstallationControlRecoveryBundle` | Installation/repository, generation/publication ref, control revision, journal ordinal/tip, eligibility epoch, trust digest/fingerprint, signer key ID, canonical member vector and signature. Each member names owner, enumerated kind, schema, byte size, digest and exact source coordinate. Required kinds are control snapshot/journal, public trust and finalized tuple set, participant inventory and each configured owner's terminal deny/suppression view. Encrypted envelope binds bundle digest, key-wrapping metadata and AEAD manifest. Purpose `installation-control-recovery`. |
| `InstallationRecoveryAnchor` and independent head | Installation/repository, custody identity, control revision, journal ordinal/tip, eligibility epoch, signer fingerprint, publication and bundle digests. Sealed head binds predecessor and operation digest. Pending head binds predecessor, installation, operation kind/digest and canonical unique participant ID, expected revision, pre-state digest and expected effect identity. Sign transitions with `installation-recovery-head`. Verify current signer or trusted successor policy. |
| Restore plan and `InstallationRecoveryActivation` | Plan digest binds archive, anchor, destination identity, signer, isolation evidence, loss acknowledgment and prior-data inventory. Local record binds plan, predecessor anchor, new generation, selected tuple, custody identity and expected operation digest. States pending and sealed. Sealed includes matching successor anchor digest. Purpose `installation-recovery-activation`. Journal coverage gates the quarantine transition. |
| Enrollment, read authorization and release permit | Stable owner operation ID and request digest, credential identity, principal, task/source/generation, read/command grant IDs, expiry, pending/active/revoked state and private handoff/signed task receipt references. Read authorization adds epoch. Ephemeral release permit binds selected publication and authority coordinates, response digest and monotonic deadline. None carry bearer bytes. |
| `ManagedRuntimeSpool` and adapter retry | Store UUID and version, unique full signed operation coordinate, original command/proof bytes, task/source/kind/generation, stable ordering and pending/committed/held state. Admission creates pending, exact receipt permits committed, and restore holds prior-generation work. Private retry record holds host binding, native coordinate where available, original prepared resume ID/proof and pending/acknowledged outcome. No transcript text in retry record. |

Direct consumers are the signing purpose registry in `key_owner.py`, control
journal model/validator, backup manifest participant registry and digest
coverage. Update format guards, archive parsers, installed CLI/schema checks
and package inventory when the affected format changes. These are operator
contracts. Public runtime wire and catalog grammar remain on their existing
versions. Return this boundary to design first if a new public protocol is
required.

## Verification families

| Requirement | Positive evidence | Negative, crash or boundary evidence |
| --- | --- | --- |
| REL-01 | Two clean native host journeys, state/capture/drain/restart/recall, exact role/status/diagnostics. Actual installed hooks, supported pins, supervised stop/start. | Wrong host/session/task/source/credential/generation, expired/revoked/rotated grant. Simultaneous retry and enrollment handoff cuts. Blocked turns preserve expected processing and privacy. |
| REL-02 | Same-installation exact + older restore retained. Fresh host with no prior root, latest independent custody versus older data, signed old-to-new lineage, verified reopen, current revoke/forget, fresh credentials, signed delivery hold and owner reconciliation. | Missing/mismatched inputs, replayed/stale/pending anchor, same-revision fork, different installation or trust, tamper of singleton/manifest/member/AEAD/chunk/pointer/plan, wrong key, incomplete locks, interrupted update/copy/atomic-publish/seal/reopen, concurrent successors, lost old host isolation, ENOSPC and compatibility rollback. Check actual externally durable pending and successor status with subprocess kill cuts, never fake clock freshness. |
| REL-03 | Build/install/test supported base and retained provider profiles across reference platform locks. Validation runs the same approved wheel and compares copied host bytes to the shipped archive. SBOM and scanner see the actual shipped closures. Docker images are validation-only. | Stale/divergent inventories, diminished required provider behavior, stale advisory evidence, editable load, mismatched version and unsupported model assets fail qualification. |
| REL-04 | Exact IDs, original spool proof export/retry and complete preselection migration. Compare receipt order and filtering in production SQL. Use `EXPLAIN QUERY PLAN` and count work as unrelated state grows. | Interrupted legacy spool import, concurrent duplicate/divergent delivery, commit vs ack, unknown proof, paused task/revocation/in-flight timeout, missing/malformed/stale derived authority, slow headers/body, response oversize, lost reply and retry, nonlocal destination/redirect, sparse revoked receipt tails and bound exhaustion. Include admission counting and explicit plan enforcement. |
| REL-05 | Differential browse and inspection vs full-snapshot reference, unchanged aliases and paging, metadata-only browse. Exact recall keeps full snapshot verification, lifecycle and provenance checks, and inverse/symmetric semantics. | Child cannot borrow parent authority, wrong session/subject/epoch, obsolete index version, invalid CTV digest, suppression affecting release, missing/retracted/ambiguous record, browse or inspection closure budget, or fail-closed retention on rebuild. Compare exact response and privacy on each negative. |
| REL-06 | Storage owner permissions + second UID Linux and macOS ACL coverage, backup/restore, existing static/type/security gates, exact artifact regression, operational rollback, reference workload grid. | Sibling file/descriptor access cases and malformed redaction, chosen failure matrix, tampered artifact evidence, nonnative substitution, slower samples and all retries preserved. |
| REL-07 | Preregistered paired memory-on/off agent outcomes on target tasks, costs and latency, adverse-memory cases, operating owner and incident exercise. | Exclude simulator oracle data from production paths. Report fake-provider, live component and agent results separately. Follow dedicated benchmark design after hardening. |

Use two current credentials with the same principal and different exact
tasks/sources to detect principal-wide resolution. Test same-principal
rotation immediately before first protected socket byte and under a partial
write. Test every ordinary opener in a fresh process after root rename and
before independent seal, including direct factory, old binary, sidecar,
consume and operator mode. Assert zero protected reads, releases and writes.
Verify the archived spool after an admission without a partition receipt and
assert old-proof dispatch stays held. Exercise live SQLite crash cuts around
row and index commits and authenticate the backup inventory independently.
On index mismatch preserve the signed
base rows while omitting/staling a selector, test warm invalidation and cold
reopen, and require unavailable. For host-kill tests distinguish pre-admission
unknown from accepted-but-unacknowledged, with same-ID proof and no duplicate.

Normative sources are the approved design, typed validators and the governing
contracts. Rehearsal code, query probes and examples are illustrative. Use
typed grammars already owned by runtime, ontology and key owners. New recovery
manifest is closed, unique and canonical-ordered by member owner and kind.
Reject unknown/duplicate fields or members, unrecognized versions, traversal
names, wrong digest shape or cardinality. No aliases or inheritance at the
recovery boundary. The pending marker and sealed state are discriminated and
mutually exclusive. Old resume plans or indexes are never current authority.
Use full source authority plus exact signed row semantics for independent
differential tests. The oracle calls the baseline path and does not reuse the
new selector or SQL. This establishes differential query evidence. Signing
verification continues through the existing stack.

## Environments and artifacts

- Deterministic gates use current PR workflows and pinned toolchain per
  profile. Run format and touched type scopes alongside the configured gates.
  Extend `test_identity_hygiene.py` to each new public, persisted and artifact
  selector with field-aware mutations. Assert reject copied requirements,
  milestones and review coordinates in behavioral names. Legitimate protocol
  numerals, actual version/value fields and typed evidence coordinates pass.
- Installed rehearsal uses a clean HOME, no checkout imports, actual wheel
  and native assets, pinned real Pi/OpenClaw, and a deterministic model stub.
  Include affected Hermes provider/ontology tests. Run a full host outage
  rehearsal without old root and an independent custody failure exercise.
- Native depth uses balanced and concentrated reference workloads on Linux and
  macOS local SSD with existing hardware profile and sample rules. Require
  default-v8 proof. Preserve staged upgrade evidence where the supported
  surface requires it and report separately. Docker results can demonstrate
  functional permission behavior only.
- Exact-artifact evidence is owned by the release coordinator, with digest
  ties from source revision and locks to build products, host installs, scan,
  SBOM/provenance and capacity evidence. Record gate/workflow identity,
  commands and results. Existing gate names stay stable. Restore and
  permission evidence includes external process/restart results, not
  uncontrolled production traffic or approval.
- Run exact-candidate component certification via the existing
  `benchmark-scheduled.yml` policy. Record the validated `LiveGateSummary`.
  Sign artifacts and manifest, verify them in an independent clean install,
  and check publication uses the same digests.

## Identity ledger

| Surface | Behavioral identities / retained source | Enforcement |
| --- | --- | --- |
| Owner commands | `memorii-operator` and existing backup/mode/grant routes, plus proposed `init`, `serve`, `runtime-grant enroll-native`, `backup restore-bootstrap` and `runtime-spool export-entry` under their respective owners | Parser inventories, CLI help/error tests, authority and exact artifact smoke |
| Recovery artifacts | `InstallationControlRecoveryBundle`, `InstallationRecoveryAnchor`, `InstallationGenerationChangeIntent` / `DeliveryRestoreHold`, `pending` / `sealed`, independent recovery head | Canonical typed manifests and signed version grammar, injected invalid identities, public history and ordered owner inventory |
| Managed state and metadata | `ManagedRuntimeSpool`, signed receipt/candidate selectors, protected catalog response schemas | File, schema, authority and event registry check, exact replay and release witnesses |
| Evidence and tests | Existing unit/static and integration suites, `reference_capacity`, behavioral tests for replacement host and exact host enrollment, `balanced` / `concentrated` | Stable job inventory and semantic fixture lineage, name mutation checks and exact artifact hashes |
| Planning coordinates | `REL-01` through `REL-07` | WorkPlan and typed evidence traceability fields only |

Implementation records each concrete changed code/test/fixture/artifact name,
registry consumer and workflow pin before freeze. Exact registry cardinality
or schema identities are taken from the canonical published owners. Unknown
name or unexpected downstream consumer stops approval of the affected slice.
