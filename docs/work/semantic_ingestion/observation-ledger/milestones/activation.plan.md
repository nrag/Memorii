# Observation Ledger Activation

Work type: implementation milestone. Status: bounded local implementation/review complete2026-09-08; CI and release evidence open.
Parent: ../implementation.plan.md. Requirements: R17 and R19 partial.
Baseline: HEAD191826cd3afb38bf605a337a71d576063b3bae5e, authorized dirty tree.
Source contracts: canonical semantic_ingestion_observation.md Activation And
Writer Fencing and Snapshot Ownership And Activation Preconditions; parent
approved design-candidate-final.json.

## Observable Acceptance

An explicit store-owned activation drains the current writer without forcing
ongoing operations terminal, scans the entire detached old inventory, and
conditionally publishes exactly activation, genesis head and successor admission
under the full-write revision and old admission/absence conditions. The successor
admission/binding commits the activation digest. A stale snapshot retries from
fresh authority within a finite protected limit; incompatible intent fails.
Post-activation old mutation grammars reject across governed routes. Historical
read bytes remain unchanged. Registry configuration by itself never activates.

## Owners And Boundaries

Canonical admission and binding types: ingestion_contracts.py. Admission current/
commit_binding/transition authority and governed grammar: writer_admission.py.
Explicit activation trigger belongs to the atomic store, which owns the native
writer pair. Profile3 artifact emission reuses source-directed candidate encoding
and fixed outer envelope; never double-encode already canonical body bytes.
New activation helper may be cohesive and typed but must have an actual store
caller. No permissive fallback to old mutations after activation.

Existing delivery transition and projection policy cutover are not observation
activation. No public retrieval, append or checkpoint authority is claimed by
this milestone. Future append grammar is a dependent milestone; hosts must
explicitly request activation, never receive it from mere registry config.

## Required Proof Before Closure

- Legacy admission/binding encodings/digests unchanged when activation absent;
  new coordinate roundtrips, changes digest, propagates through commit_binding.
- Actual store activation with real registry package commits three joined records
  and advances writer epoch exactly once; repeated identical intent returns same
  immutable activation and verifies persisted successor/head.
- Live/leased old operations block; draining prevents new old operations.
- Insertion or any root batch after inventory read loses full revision CAS,
  publishes no partial activation and forces complete rescan.
- Different activation intent, stale binding, corrupt inventory, missing history
  and absent/mismatched genesis or activation reload fail closed.
- Governed ordinary/conditional/UOW/atomic old mutation routes cannot bypass
  activated grammar; old record reload remains readable.
- Bounded resource/retry exhaustion surfaces an explicit failure.

Root owns pytest, source declaration refresh, generated pins and package evidence.
One Terra writer owns production and feature-local tests; no overlapping edits.
Readiness test consultation precedes coding. One coherent frozen review by the
three standard roles, then one consolidated eligible correction. No invented
policy or signing decision; actual release signatures remain deferred.

## Next Action

Hand off the reviewed activation boundary to append/replay; retain exact-candidate
CI and refreshed release packaging as parent evidence obligations.

## Readiness Findings And Required Evidence

Test consultation adds held-lease drain with completion under old rules; real
JSONL precommit/postcommit lost-outcome reopen; configuration-only nonactivation;
byte-identical legacy terminal/group reload; and complete distinct-control
inventory membership. These are finite evidence actions within the activation
contract, not requests for unrelated append/retrieval proof.

The Spark map confirms known admission/transition seams but does not provide the
requested nested codec closure; its claim that checkpoint integrity consumes an
ObservationLedgerActivation object is unsupported (only the digest coordinate
is consumed). Root relies on actual code and Terra's subsequent codec inspection.
Existing wrap model serializers in semantic_ingestion/contracts.py omit only
absent compatibility fields and preserve nested legacy model dumps.

Root rejects a proposed unchanged ownership manifest after activation. Although
the runtime classifier is separate, SIA1086 declares the manifest the sole
inventory and SIA33588 requires an atomic manifest update before new kinds or
methods are used. Globally extending the current computed manifest would instead
break old admission reopen before explicit cutover. A bounded spec consultation
is resolving the determinate frozen-old/explicit-successor transition. No
activation code is written until this authority-chain detail is settled.
The actual inventory CAS is expected_write_revision over the complete detached
snapshot; no separate partition token exists.

## Readiness Decision And Ownership

Spec consultation confirms a determinate dual-manifest implementation: preserve
the exact v2 builder/bytes; introduce one finite compiled successor manifest;
validate the exact old/new pair and persist the successor only in the activation
CAS. Reopen accepts only these exact manifests paired with their admission
grammar. No host-configured inventory and no extra field in fixed activation
preimage. Ordinary unrelated transitions retain exact-manifest equality.
The unchanged-successor-manifest proposal is classified confirmed governance
changes_required and replaced before coding. This is a conformance action, not
a product-remediation round or a new product-policy choice.

Terra registered_artifact_integrity is now the sole activation writer. It owns
admission/binding contracts, writer admission/governed policy, explicit atomic
store trigger, static semantic classification, genesis head invariant, cohesive
activation/emission helpers if necessary and feature-local tests. Root owns
tests, generated registry/source refresh, evidence and these packets. No public
retrieval or ledger append is implemented in this slice; activation is explicit
and old writes fail closed afterward until the dependent append milestone.

The original Terra writer delivered only compatibility foundation and then stopped
twice despite continuation instructions: optional legacy-omitted activation
digest, propagation/admission digest, and head genesis iff sequence zero. Root
records this as partial, not completion. Fresh artifact-context Terra worker
ledger_activation_writer now exclusively owns the remaining complete activation
transaction and tests. Prior writer is completed and has no overlapping authority.
The new worker receives the same scope/matrix and all settled readiness facts.
No user input, external blocker or release signature is required.

## Confirmed External Contract Blocker

The target writer/schema/codec fingerprint authority is unspecified. Production
writer identities are descriptive strings; activation fields requireSHA256.
Spec consultation confirms Not applicable / blocks_approval / governance.
No arbitrary label hash, activation-only decoder digest or hostprovidedhex
substitutes for a protected target identity. Parent design operation:
../../activation-target-identity/design.plan.md, with concrete direction proposal
in decision.md. Public activation fails before drain/snapshot/write pending
that authority. Partial private transaction preparation is not approved and
cannot be counted as implementation or persistence proof.

Root rejected an added raw-model activation digest validator because registered
self-digest requires exact domain/binding/preimage; native shape validation must
not invent a second digest. Root also corrected the new genesis test to prove
bothdirections using the correct positive/negative revisions.

Cleanup verification initially fails collection: the new top-level atomic-store
import of observation_ledger_contracts creates a cycle through semantic_ingestion
authorization back to partially initialized atomic_store. Root records the exact
three collection errors; the sole writer fixes only the introduced import
boundary and verifies missing-authority failure before any storage mutation.
Static checks were insufficient to prove import viability. No candidate closure
is claimed until root reruns these checks.

Safe checkpoint verified: the introduced import cycle is corrected; all three
activation entrypoints fail before drain or write and unsafe private transaction
bodies are removed. Root executes166ledger/replay/checkpoint/writer-admission
cases in7.91s plus1actual-store no-write case in5.03s. Scoped Ruff and configured
five-production-file Pyright pass. activation-safe-checkpoint.json pins this
blocked state. No transaction/activation success, target authority or parent
closure is claimed. Source package refresh is construction evidence only.

## Resumption2026-09-08

Target identity ambiguity is resolved by the approved canonical target design;
release-preparation/closure.json records the completed prerequisite. Earlier
blocked/partial-writer entries are historical, not current decision requests.
The user authorizes ledger activation and retrieval integration. Proceed in the
parent's dependent milestones; do not expose automatic activation.

Root mapped current stubs in atomic_store.py and writer_admission.py. Existing
raw activation/head record helpers and reload checks are provisional and must be
replaced with registered profile-3 bytes/self-digests and complete joins. Reuse
typed_value_model_codec/artifact_reader/artifact_integrity; no raw dictionary hash
may substitute for a registered root digest. The governed successor manifest is
explicit and preserves exact legacy manifests. Full snapshot fence already exists.

One Terra worker owns activation production paths, cohesive helper and feature
local tests; root owns all commands, generated registry/source refresh and work
evidence. Spark maps fresh execution paths independently. The previously reviewed
activation matrix remains governing, including JSONL restart, held leases,
latecontrol/unrelated-root CAS races, no-trigger, and all legacy write routes.
Parent R17/R19 remain partial and retrieval follows durable activation/append.

The inherited activation_target_writer declined without edits due its own context
budget. A fresh Terra durable_activation_writer owns the complete bounded slice;
no overlap exists. Prior approved release preparation evidence plus its actual
wheel/root tools is preserved in release-preparation-baseline.tar.gz with SHA.
Current CI source pins must be refreshed at the new candidate after production
edits; historical preparation approval is not certification for new bytes.

## Construction Checkpoint

Fresh worker delivered registered artifact emission and an initial CAS path, then
stopped with required families unfinished. Root resumed the same writer explicitly;
there is no user time limit or external blocker. Root identified and required
full-trio current/predecessor-binding idempotence, preserved drain metadata,
JSON-safe persisted artifact encoding, exact legacy-control inventory separately
from full snapshot fence, protected retry configuration and JSONL/race/lease proof.
The worker reports focused tests but ran them contrary to root command ownership;
those unretained claims are not accepted as root verification or candidate closure.
Root will run the frozen complete slice and reconcile exact outputs.

## Construction Reconciliation 2026-09-08

Root took production ownership after the Terra handoff remained incomplete in
three repeated attempts. The earlier worker completion summaries are not closure
evidence. Root replaced the duplicated live-read reload paths with one detached
snapshot verifier, shared inventory hashing, and native terminal/member validation
using snapshot-only lookups through the existing reload owner. Captured historical
records demonstrate that request/recovery aliases share both source kind AND
content kind with terminal roots: select the native terminal-locator ID namespace,
not content kind alone. The consultation's content-kind discriminator was incorrect.

The successor record retains a typed `activation_predecessor_binding` in internal
admission metadata. The activation and public admission model field inventories
remain unchanged; the old wrapper omits this metadata. The transition policy
checks this binding against the exact predecessor, and repeated calls validate
its complete coordinates and target/admission joins. This supplies lost-ACK old
binding recovery even for an empty legacy inventory. Independent review must
check this internal metadata boundary.

Construction evidence: fourteen activation cases passed, followed by two captured
native-terminal cases (valid history and missing member). These are integration
fixtures with real registry/crypto owners and synthetic installed-package content;
they are not actual-wheel or provider-quality certification. Full focused current
candidate suite is running in activation-evidence/focused.log. Root Pyright from
memorii/ passed with zero errors; an earlier invocation from repository root did
not load the governed pyproject configuration and is not the applicable gate.

Changed surfaces: atomic_store.py, writer_admission.py,
observation_activation_runtime.py, integration/test_observation_ledger_activation.py;
prior provider registry-missing-schema expectation was adjusted during worker
construction. Native terminal v1/v2 bytes are not rewritten. Full write CAS and
registered publication binding remain required. Old-grammar writes intentionally
reject after activation; append/retrieval remains the next dependent packet, so
this branch must not be described as release-ready activation.

Production binding: ProviderMemoryService.activate_observation_ledger() ->
AuthorizedSemanticIngestionRuntime.activate_observation_ledger() (current protected
bootstrap/deployment authority, current writer binding) ->
SemanticIngestionAtomicStore.activate_observation_ledger() (target/history,
read_write_snapshot, native inventory validation) ->
SemanticWriterAdmissionStore._activate_observation_ledger() -> one conditional
root batch with exact full write revision, predecessor digest and absent head/
activation. Repeated entry revalidates the target and complete detached trio.
The public-provider positive integration test proves this route; configuration
and initial admission leave ledger records absent.

## Independent Review And Consolidated Correction

Initial frozen candidate aefaac2d4c3a655d2be8e3570926f6b0923347f9adefc09eacdacf6663c03b28
matches candidate.json. Root verification.json records241passed541.44s, configured
Pyright/Ruff/identity success. Review readiness was withheld until that aggregate
terminated, then spec's evidence-only delta confirmed the blocker resolved.

Correctness ACT-COR-001 is confirmed P2/changes_required/runtime concurrency:
equivalent callers could lose the successful cutover at drain or commit admission
checks. Root reconstructed the whole bounded retry boundary, moving drain CAS
inside the finite rescan loop, resolving equivalent completed cutovers from fresh
snapshots at both seams, and retaining typed rejection for mismatches. The sibling
competing-drain CAS also rescans instead of surfacing a raw contention failure.
No external/public trigger change or new policy decision is introduced.

ACT-GOV-001 is confirmed Not applicable/changes_required/governance evidence:
the parent production binding JSON was stale; its activation entry is updated.
The initial proposed extra CLI requirement was unsupported and removed: canonical
activation_target.md:9 explicitly selects the payload-free ProviderMemoryService
method as the trusted-host entrypoint and forbids automatic startup activation.

Test review repeats the concurrency defect. Its remaining four missing-test
findings are reclassified Not applicable/changes_required/verification, since
absence of evidence alone is not demonstrated P2 product impact. These are finite
matrix evidence actions: public JSONL pre/postcommit interruption plus child-process
reload; public live-operation drain/new-admission refusal/old-work completion;
conditional write rejection; literal captured JSONL byte preservation and two
native terminal inventories. Root's expanded integration file implements these
families. The first interrupted-worker test used a new admission instead of a
held original invocation; it was replaced by a bounded public-call barrier. A
later reopen failure was a fixture lease authority reused across provider roots;
rebuilding that fixture per root corrects the test, not product semantics.

Construction correction:21passed87.76s before the final public live/history/drain-
CAS additions. The dedicated final24-case integration command is currently running;
no final correction pass or independent approval is claimed yet. Test/CI topology
is owned by ../observation-ledger-tests/testing.plan.md and path-to-gate.json.
The new required PR job isolates these process/JSONL cases from fast unit shards.

## Final Bounded Handoff

Final candidate41f423726e74930827a1b927e62b0e5ba093f6aeaa0fa018196c8ea9e67077b7
records24passed218.82s with retained JUnit, lint/type/identity success. All three
standard reviewer deltas approve the bounded slice after ACT-COR-001 and
ACT-GOV-001 reconciliation. Remaining validated P1/P2: none. This supersedes
the construction-time pending statements above. Exact-candidate CI, current
release-wheel preparation, append/replay, checkpoints and authenticated retrieval
remain open. See activation-evidence/bounded-handoff.json. No parent closure.
