# Acceptance Authority Durable Publication

## Contract Boundary

The acceptance environment owns one durable authority repository and one
configured evaluator runtime. The public command supplies only candidate
release, baseline, policy, evidence, certificate, and deployment-manifest
digest. The runtime supplies the clock, bootstrap limits, trust
anchor, immutable authority repository, numeric binding, receipt repository,
and deployment publisher from host-owned installation configuration.

The authority repository exposes decoded acceptance objects only after it has
bounded and independently validated their canonical bytes. It never returns a
caller-selected current pointer or accepts caller-provided trust material.

## Closed Artifact Family

All bodies are closed canonical-map values under the canonical ingestion typed
value profile and a registered complete schema binding. Maps sort keys by
encoded UTF-8 JSON-string bytes; integers use the registered decimal-integer
form; timestamps use normalized UTC RFC 3339 with explicit offset; raw
signatures use the profile's registered byte form. Statistical decimal values
retain their separately registered canonical decimal encoding-policy identifier;
the authority schemas cannot infer a decimal representation from a language
runtime.
Every decoder rejects duplicate/unknown/missing fields, wrong native types,
unknown enum values, noncanonical encodings, and values outside protected
ceilings before constructing a domain object.

The registry declares these schemas and purposes:

| Schema | Required semantic content | Digest/signature ownership |
| --- | --- | --- |
| `AcceptanceTrustSnapshot` | schema version, purpose, snapshot sequence, predecessor, complete static key declarations with purposes and validity, trust-policy digest, issued time, snapshot digest, root signer, signature | acceptance root authority |
| `KeyLifecycleEvent` | key reference, state, effective time, global sequence, predecessor event digest, issuance trust snapshot, event digest, signer, signature | acceptance status authority |
| `AcceptanceApprovalIssuanceSnapshot` | trust snapshot, ordered nonempty key-event digests, exact key head/sequence, signing key coordinate, snapshot digest, signature | approval issuer |
| `CapabilityBaselineApprovalRelease` | the exact canonical SIA fields | approval issuer |
| `AcceptanceCurrentCheckpoint` | capability, generation, authority snapshot, release and key heads, active pointer, ordered production-revocation receipt/production-epoch-checkpoint digest pairs, observed time, checkpoint digest, signer, signature | acceptance status authority |
| `ProductionRevocationReceipt` | prior approval release, requested time, prior and advanced production epochs, completion time, receipt digest, production signer, signature | production deployment authority; acceptance reads serialized bytes only |
| `ProductionEpochCheckpoint` | production authority snapshot, generation and predecessor, active epoch, active authorization digests, revocation receipt digests, observed time, checkpoint digest, signer, signature | production deployment authority; acceptance persists and independently revalidates serialized bytes |
| `AcceptanceEvaluationReceipt` | verified approval, certificate, policy, evidence, deployment authorization, evaluation time, evaluator identity, receipt digest, signer, signature | acceptance evaluator authority |
| `AcceptanceAuthorityCommit` | schema version, purpose, transaction sequence, predecessor commit, authority snapshot, key and release heads/sequences, active release pointer, checkpoint, optional all-or-none issuance pair, ordered production-revocation receipt/production-epoch-checkpoint digest pairs, commit digest | protected repository fence authority; not a release signature |

`AcceptanceStaticKeyDeclaration` is a closed nested type containing key
reference, public-key bytes, half-open static validity interval, and a nonempty
sorted set of allowed purpose literals. `AcceptanceTrustSnapshot` contains a
nonempty tuple of unique declarations. `AcceptanceAuthorityCommit` contains
exactly `schema_version`, `purpose`, `transaction_sequence`,
`predecessor_commit_digest`, `authority_snapshot_digest`,
`key_history_head_digest`, `key_history_head_sequence`,
`release_history_head_digest`, `release_history_head_sequence`,
`active_release_digest`, `active_release_epoch`, `active_release_sequence`,
`current_checkpoint_digest`, `issuance_snapshot_digest`,
`approval_release_digest`, `production_revocation_evidence`, and
`commit_digest`. Each closed `production_revocation_evidence` member contains
exactly one revocation receipt digest and one production epoch checkpoint
digest. The two issuance fields are both null or both present. The
active release fields are all null only for a genesis state and otherwise all
present. Every head digest and sequence joins the referenced artifact history.

Each schema has a unique purpose literal, digest domain, signature domain, and
complete profile-binding identifier. For a signed body `U`, artifact digests
omit only that artifact's own digest and signature and equal
`SHA256(LP(ASCII(domain)) || LP(profile_binding_bytes) || LP(CTV(U)))`, where
`LP` is an unsigned 64-bit big-endian byte length followed by the value. The
Ed25519 message is the canonical encoding of the closed map containing purpose,
complete profile binding, signer coordinate, recomputed body digest, and the
unsigned canonical content. The commit omits only `commit_digest` from its
digest body and has no artifact signature; the protected independent fence
authenticates selection. It cannot replace artifact signatures.

The release schema remains byte-for-byte compatible with canonical SIA. The
other schemas implement the already accepted successor and issuance-prefix
contracts. Existing aliases such as `CurrentStatusCheckpoint` and generic
`EvaluationReceipt` are implementation names only and must converge on the
behavioral persisted names before publication.

`KeyLifecycleEvent`, `AcceptanceApprovalIssuanceSnapshot`,
`AcceptanceCurrentCheckpoint`, and `ProductionRevocationReceipt` use the exact
closed members and chronology already approved in the authority-successor and
issuance-prefix proposals. `AcceptanceEvaluationReceipt` contains exactly
`schema_version`, `purpose`, `authority_commit_digest`,
`verified_approval_digest`, `certificate_digest`, `policy_digest`,
`evidence_digest`, `deployment_authorization_digest`, `evaluated_at`,
`evaluator_subject_id`, `receipt_digest`, `signing_key_coordinate`, and
`signature`.

`ProductionEpochCheckpoint` contains exactly `schema_version`, `purpose`,
`production_authority_snapshot_digest`, `checkpoint_generation`,
`predecessor_checkpoint_digest`, `active_production_epoch`,
`active_authorization_digests`, `revocation_receipt_digests`, `observed_at`,
`checkpoint_digest`, `signing_key_coordinate`, and `signature`.
`AcceptanceCurrentCheckpoint` and `AcceptanceAuthorityCommit` contain the same
ordered receipt/checkpoint digest pairs for every acknowledged terminal
transition.

## Durable Repository And Transactions

The normative repository operation is:

```text
compare_and_publish(prepared_objects,
                    expected_commit_digest,
                    expected_key_head,
                    expected_status_generation,
                    next_commit)
```

The repository holds an exclusive backend lock, reloads and validates the
external fence, current index, selected commit, and every referenced object,
then checks all expected coordinates. It writes missing immutable objects by
temporary-file write, file fsync, atomic replace, and directory fsync. Existing
digest paths are accepted only when bytes match exactly. It then writes the
immutable commit object, replaces and fsyncs the advisory current index, and
last advances the append-only independent monotonic fence with the transaction
sequence and commit digest. Only a commit named by the fence is authoritative.

The fence is the commit point. An index ahead of the fence is prepared state and
is repaired back to the fenced commit on restart. A fence ahead of the index is
committed state and repairs the index forward after validating the named commit
and all objects. A missing, malformed, forked, truncated, substituted, or
noncontiguous fence/commit chain makes the repository unavailable. It never
searches for a plausible latest object.

The production fence port exposes linearizable `load_current` and
`compare_and_advance` with byte-identical idempotent retry. Its records bind the
repository namespace, registered backend identity and failure domain,
transaction sequence, commit digest, predecessor fence digest, and record
digest. The runtime verifies a protected signed backend registration binding
that namespace and backend to the authority repository and a credential
reference. The standard local adapter is a separately managed SQLite database
using an immediate serializable transaction and full durability; its registered
failure domain must differ from the immutable-object repository. The existing
file fence remains test-only. Unavailable or indeterminate fence state makes the
repository unavailable and produces no evaluation success.

An approval issuance transaction contains exactly one
`AcceptanceApprovalIssuanceSnapshot` and one
`CapabilityBaselineApprovalRelease`; the commit names both and their mutual
references must join. The CAS additionally requires the captured key head and
status generation. A stale CAS commits neither. Byte-identical retry of the
same next commit succeeds idempotently; a coordinate or byte substitution
rejects.

Key events, release lifecycle records, checkpoints, and production revocation
receipts are append-only objects selected by later commits. The checkpoint
generation and transaction sequence increase by exactly one. Release and key
heads are contiguous and predecessor-linked. A checkpoint cannot acknowledge a
terminal approval transition until every required production revocation
receipt is durable and named; it cannot select a replacement release before
that acknowledgement.

`AcceptanceEvaluationReceipt` is stored by digest, but the store never writes
directly to the final digest path. Under its cross-process lock it writes a
same-directory unique temporary file, fsyncs complete bytes, atomically
replaces an absent final path, and fsyncs the directory. It removes or ignores
unselected temporary debris on recovery. An existing final path is idempotent
only when its bytes are identical; malformed or truncated final bytes make the
store unavailable. Remote adapters must provide equivalent create-if-absent,
exact-read, and durable-acknowledgement semantics. The receipt is not part of the
authority checkpoint transaction and cannot change authority currentness. The
evaluator prepares the production authorization, durably publishes the signed
evaluation receipt, and only then makes the prepared authorization visible.
Failure before durable receipt publication leaves no visible authorization.
Failure after receipt durability but before visibility is retryable from the
same receipt and prepared authorization bytes. A durable evaluation receipt
proves the evaluation result, not production visibility, and the command does
not report success until visibility is confirmed.

One acceptance-owned publication coordinator serializes every authority commit
and deployment publication under the repository's exclusive transaction lease.
After receipt durability it retains the evaluation snapshot's already-held
lease, revalidates the exact authority commit, and invokes the digest-idempotent
production publisher while lifecycle transitions are excluded. It never
reacquires a reentrant lease. On an indeterminate publisher result it
queries visibility for the exact authorization digest before either retrying or
returning failure, and releases the lease only after confirmed publication or a
reconciled terminal failure. A transition committed before the lease rejects stale
publication. A transition after publication must durably revoke the visible
authorization before an acceptance checkpoint acknowledges it.

## Reads, Bounds, And Recovery

Opening the repository validates the complete fenced commit chain and selected
heads before serving a current value. Reads use the one selected commit as a
snapshot so a verification cannot mix generations. The repository resolves
content-addressed artifacts with per-object and cumulative byte/count/depth
ceilings. Repeated references, cycles, extra unreachable objects in a commit,
and inconsistent profile or schema coordinates reject.

`AcceptanceEvaluationSnapshot` is an opaque acceptance-internal capability
created only by `begin_evaluation`. Under the repository's exclusive
transaction lease, that operation loads the fence-selected commit and signed
checkpoint, validates their complete current state, samples the configured
clock, requires the checkpoint observation time not to exceed the evaluation
instant, and returns the selected commit digest, checkpoint digest, instant,
and held lease without publishing authority. The caller
cannot construct the capability or select any coordinate. The normal evaluator
retains it through approval verification, numeric evaluation, receipt
publication, and deployment publication. The evaluation receipt binds the
snapshot commit and instant. A verification-only public method that opens a
short snapshot cannot create a receipt or deployment authorization.

This rule supersedes the predecessor feasibility model's exact
checkpoint/evaluation timestamp equality. The protected monotonic fence,
complete commit validation, and lease establish currentness; creating a new
checkpoint merely to evaluate rejected candidate bytes would violate the
no-mutation failure contract. Candidate decode, signature, expiry, numeric,
receipt-store, and publisher failures therefore cannot advance the authority
commit, checkpoint, or fence.

The evaluator samples its evaluation time while holding one repository snapshot
and requires the selected checkpoint not to be later than that instant.
Repository or clock failure produces no verified result.
No concurrent authority publication can occur while the evaluation snapshot
lease is held. The deployment publisher still revalidates the exact commit
before making authorization bytes visible; crash recovery either reconciles
that same digest-idempotent publication or rejects if a later lifecycle commit
won after the abandoned lease was released.

Prepared, unreferenced immutable objects are harmless. Garbage collection is
optional and cannot remove any object reachable from any committed fence
record. Operators may inspect state classifications `empty`, `current`,
`legacy`, `mixed`, or `corrupt`; only `current` serves verification.

## Installed Runtime Bootstrap

The distribution defines command `memorii-acceptance-evaluate`, discovery
group `memorii.acceptance_evaluator_runtime`, and exactly one standard provider
entry `acceptance.host_runtime:InstalledAcceptanceRuntime`. Its zero-argument
provider reads one closed host-owned configuration from the platform data
directory at `etc/memorii/acceptance/runtime-v1.json` and returns a configured runtime that
constructs:

- one protected repository rooted at a host-owned absolute path;
- one protected bootstrap limit set and canonical schema authority;
- one acceptance trust anchor and status signer policy;
- one held numeric binding and transport limit set;
- one immutable evaluation-receipt repository;
- one deployment publisher implementing the serialized digest-only boundary;
- one protected production revocation-evidence reader and trust anchor;
- one timezone-aware host clock.

The public command callable has no evaluator injection parameter and the command
has no authority, config-path, plugin-name, key, history, limit,
clock, issuer, or approval-override flags. Candidate input paths do not select
trust. Environment variables cannot override the provider, configuration path,
or protected values. Zero, multiple, unloadable, wrong-protocol, or mutable providers fail
before reading candidate evidence. The provider validates directories are not
symlinks, authority files are not group/world writable, and repository,
receipt, and deployment publication roots do not alias.

The standard provider contains no permissive defaults: a missing or invalid
configuration fails closed. Alternative host providers require a separately
reviewed distribution that replaces, rather than accompanies, the standard
entry so discovery still finds exactly one. Installed tests exercise the real
standard provider with fixed temporary resources; test authority cannot be used
as release evidence.

## One-Way Production Boundary

Acceptance may import only its canonical, cryptographic, numeric, repository,
and CLI owners. It must not import `memorii.core` semantic, routing,
reconciliation, observation construction, or production arithmetic. The
deployment publisher crosses process/package ownership using canonical
serialized `DeploymentAuthorizationArtifact` bytes plus stable digests.

Production owns decoding, signature verification, trust/currentness, and final
publication for that artifact. No production source imports `acceptance` or
acceptance schemas. Acceptance independently decodes the prepared production
bytes before receipt publication; production independently decodes them before
visibility. Frozen cross-decoder vectors and substitutions prove agreement.

Production revocation evidence crosses a separate serialized reader boundary.
For an expected prior approval release, the production-owned reader returns the
canonical `ProductionRevocationReceipt` and signed current production epoch
checkpoint that contains its digest. Acceptance independently decodes both with
constructor-held production trust, verifies signatures, purposes, digest joins,
epoch increase, generation/predecessor currentness, and time ordering, then
admits their exact digest pair to its checkpoint. Both canonical objects are
persisted content-addressed in the same acceptance commit and revalidated on
every reopen. Raw bytes, a receipt digest alone, a stale or missing production
checkpoint, reader outage, or a conflicting epoch cannot acknowledge the
transition. A later production checkpoint does not replace this historical
proof; it must extend the authenticated checkpoint chain.

## Registry And Promotion Chain

The canonical source is the acceptance-owned packaged resource
`acceptance/resources/authority-schema-registry-v1.json`; it is distinct from
the design-traceability registry at
`docs/design/semantic_ingestion/traceability_registry/registry-v1.json`.
The latter binds SIA requirements and evidence and does not authorize runtime
wire decoding. The acceptance registry lists the complete artifact inventory,
field order/optionality, enum sets, profile identifiers, purpose literals,
digest/signature domains, and parser ceilings. Generation must be deterministic
and produce:

1. `acceptance/generated/authority-schema-manifest-v1.json` for runtime
   schema/profile authority and the exact registry source digest;
2. `docs/design/semantic_ingestion/acceptance_authority_vectors/v1.json` as
   independently authored expected-byte vectors for every schema, including Unicode map
   ordering and integer/timestamp boundaries;
3. `docs/design/semantic_ingestion/acceptance_authority_vectors/manifest-v1.json`
   containing source, generated artifact, and vector digests plus
   exact schema/profile/domain cardinalities;
4. package resource inclusion;
5. workflow arguments and checksum pins.

The generator and independent checker may share only the normative schema
source bytes. They may not share an encoder, decoder, normalizer, digest helper,
fixtures, or derived manifest. Generation admission fails on an added or
removed schema/profile/domain, stale vector, cardinality change, checksum drift,
or undeclared package resource.

The required `acceptance-authority-runtime` PR job has a 20-minute timeout. It
builds the actual Memorii wheel, installs it into an isolated target, provisions
the standard provider's protected temporary configuration, and invokes the
installed command by subprocess through success and rejection paths. It runs
`memorii/tests/unit/acceptance/test_acceptance_schema_authority.py`,
`memorii/tests/unit/acceptance/test_acceptance_authority_repository.py`, and
`memorii/tests/integration/test_acceptance_authority_runtime.py`. The
semantic-ingestion aggregate lists this job as a required dependency. A
workflow-structure test in
`memorii/tests/unit/tools/test_acceptance_authority_workflow.py` deletes or
renames the job, aggregate dependency, provider registration, installed-command
step, schema/vector validation step, or warnings-as-errors setting and requires
rejection. The installed runtime matrix also deletes each constructor-held
authority, adds a second or wrong provider, attempts environment replacement,
and restores an evaluator argument or fallback; each exits nonzero before
candidate reads and leaves no receipt or authorization.

The job also checks both forbidden import directions, validates generated authority and
vectors independently, exercises the crash/restart matrix, and runs identity
hygiene. CI evidence is revision-bound; local tests do not substitute for it.

Implementation ownership is fixed before coding: `acceptance/schema_registry.py`
loads and validates the packaged source and manifest;
`acceptance/authority_repository.py` owns bounded decode, immutable objects,
commit recovery, snapshots, and the external-fence port;
`acceptance/runtime.py` owns the configured runtime protocol and protected
composition helpers; `acceptance/capability_baseline_approval.py` owns domain
verification; `acceptance/evaluator.py` owns evaluation and publication order;
and `acceptance/cli.py` stays a thin command. The generator and independent
vector checker live under
`docs/design/semantic_ingestion/acceptance_authority_vectors/` so acceptance
runtime code cannot import them. `.github/workflows/pr-gates.yml` owns the
installed-package and aggregate CI bindings.

## Migration, Rollout, And Rollback

There is no compatibility decoder for unregistered drafts. Empty repositories
may initialize only from a complete signed genesis transaction. Legacy,
mixed, or corrupt repositories remain unavailable until an operator archives
them and provisions a new repository through fresh issuance. Historical
release, snapshot, event, checkpoint, receipt, or commit bytes are never
rewritten.

The authoritative inventory matrix covers empty storage, complete signed
genesis, legacy-only, mixed legacy/current, corrupt objects, incomplete issuance
pair, an index edited to an older commit, and a deleted, reordered, forked, or
truncated fence record. Only empty storage awaiting genesis and a complete
current chain have defined non-error outcomes; only the complete signed genesis
can begin serving. Every other case is unavailable, invokes neither evaluator
nor publisher, and requires archive plus reissuance. Rollback is accepted only
as a later signed lifecycle record and later fenced commit; index edits and
fence deletion never select it.

Rollout first publishes schema authority and installed-package gates, then
provisions host authority, then enables evaluator publication. Production
activation remains fail closed until the later host-integration stage consumes
the resulting authorization. Rollback disables the evaluator entry point or
publishes a later signed/fenced lifecycle transition; it never selects an older
commit by editing the index or deleting a fence record.

## Verification Matrix

| Family | Required proof |
| --- | --- |
| Closed schemas | Generate every one-field omission/addition/type/enum/duplicate-key mutation for each artifact and nested member; trusted re-signing still rejects semantic mutations. |
| Canonical bytes | Independent encoders agree on ASCII/Unicode key order, byte strings, timestamps, minimum/maximum integers, null optionals, and complete digest/signature preimages. |
| Issuance atomicity | Stale key head/status generation, concurrent issuers, pair omission/substitution, exact retry, and lost acknowledgement expose either the complete pair or neither. |
| Recovery | Interrupt before/after every object/index/fence fsync; restart selects exactly the fence commit or reports unavailable, never prepared debris. |
| Histories | Gap, fork, reorder, truncation, alternate predecessor, head substitution, equal-time event, terminal replacement, revocation-receipt ordering, missing/stale/replaced production epoch checkpoint, and production reader outage fail closed before and after restart. |
| Snapshot consistency | Mutating the verified release, checkpoint, commit, or evaluation instant independently rejects; same-release status changes and authority advancement at every handoff cannot interleave with the held lease; every candidate/schema/signature/expiry/numeric/receipt/publisher failure and crash preserves the authority commit/checkpoint/fence; abandoned-lease retry/restart preserves or rejects the exact sealed context. |
| Receipt publication | Competing writers and interruption before/after temporary creation, write, file fsync, atomic replace, and directory fsync; malformed/truncated final bytes; first write, same-byte retry, conflicting retry, collision, symlink/path substitution, fresh-process restart, lost acknowledgement, and prepared-authorization retry preserve one immutable receipt or fail with no visible authorization. |
| Bootstrap | Installed success plus zero/multiple/unloadable/wrong providers, environment/config injection, writable authority, aliased roots, and missing resources fail before evaluation. |
| Isolation | Static and runtime import probes plus independent deployment artifact decoders enforce the one-way byte/digest bridge. |
| Promotion | Independent regeneration, cardinality, checksum, package-resource, workflow-pin, identity-hygiene, and aggregate-gate mutations fail. |
| Migration and rollback | Empty, signed genesis, legacy-only, mixed, corrupt, incomplete pair, older-index edit, deleted/reordered/forked/truncated fence, and later-transition rollback prove only complete current authority serves. |

## Operational Limits

All protected ceilings are finite positive integers and are supplied by the
host provider. The schema source defines safe maxima but does not select release
policy thresholds or evidence sample sizes. Lock acquisition and filesystem
errors are terminal for that invocation. Logs name failure categories and
artifact digests only; they do not emit keys, signatures, evidence content, or
protected paths. A successful invocation emits the evaluation receipt digest.

## Evidence Limits

This design and its deterministic tests can establish engineering behavior.
They do not create a trusted PKI, select policy values, sign a production
release, supply statistically qualifying evidence, or certify an exact
revision. Those remain the release operation the user is preparing with a
YubiKey.
