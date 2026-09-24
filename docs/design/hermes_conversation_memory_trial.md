# Hermes Conversation Memory Trial

## Status and purpose

The active governing split is: Section 8 of
`semantic_ingestion_architecture.md` defines Bootstrap V3 runtime composition,
and Section 9 defines free-form admission before its existing proposal
transport. This trial adds neither a second runtime nor a second coordinator.

This is the Level 2 design for testing Memorii as the memory provider of a
local Hermes command-line session in Windows Docker. It uses the normal
provider composition with explicit local Level 2 authority for this test. It
is a design contract; it neither creates a production authorization nor claims
that the OpenAI transport is approved, installed, or working.

The trial proves one user journey: a real, naturally phrased project assertion
from Hermes is retained, independently validated, committed through the
governed semantic writer, and recalled with source provenance in a later
Hermes session after a container restart. A transcript search hit, seeded
record, fixed proposal, or direct service invocation does not satisfy this
claim.

The deterministic Bootstrap V3 runtime remains the sole runtime. This trial
adds only a local installation authorization for its fixed project-assertions
resource policy. It is not a test authority, development connector, or
separate trust domain.

## Requirements

| Requirement | Observable Level 2 result |
| --- | --- |
| HCM-01 | The installed Hermes provider loads one first-party Bootstrap V3 factory and reports unavailable when its local authorization or resource policy is absent or invalid. |
| HCM-02 | A completed Hermes user/assistant pair is admitted as one atomic operation with replay-stable turn identity. Equal text in separate turns remains distinct; redelivery is idempotent. |
| HCM-03 | Two fresh free-form project assertions can create source-quoted candidate proposals and only validated candidates become committed semantic facts. |
| HCM-04 | A later session for the same local installation receives current committed semantic facts only through the protected scoped-context reader, with complete source provenance. |
| HCM-05 | Restart, timeout, retry, and interrupted writes yield one durable terminal outcome or a recoverable pending operation; no partial fact is visible. |
| HCM-06 | Operator diagnostics identify Bootstrap V3 resource policy, operation status, graph/projection state, and recall result without treating raw-source counts as proof of recall. |

Hermes owns its conversation and session lifecycle. The Hermes bridge only
translates callbacks. The production provider factory owns resource-policy verification,
host-issued ingress and read authority, storage, proposal transport, and worker
lifecycle. Core owns raw-source admission, routing, candidate validation, writer
fencing, semantic commit, provenance, retrieval, and persistence. No adapter or
model response writes graph truth directly.

## Historical profile-selection draft (superseded)

### Active Bootstrap V3 correction

Bootstrap V3 is the sole production semantic runtime and interface for this
trial. The name `memorii.project_assertions@1` identifies only the installed
predicate catalog and extraction resources used inside Bootstrap V3; it is not
a semantic runtime profile, a trust domain, or an alternate writer/read path.
`local_level2_operator` is only an installation-bound host authorization mode
that supplies the same required Bootstrap V3 host material before production
signing. Every paragraph after this correction through `## Eligible free-form
facts` is historical and non-normative. Section 8 of
`docs/design/semantic_ingestion_architecture.md` owns runtime composition,
local authorization, completed-turn admission, recovery, and scoped read;
Section 9 owns current-release free-form admission. The Level 2 rollout uses a
new clean data volume for the selected image digest.

The first-party factory must verify the existing `VerifiedBootstrapProfile`,
then have `HermesBootstrapV3LocalAuthorizationAdapter` verify the local sidecar
and installed project-assertions resource digests. The adapter builds the
existing complete Bootstrap V3 source-normalization bundle, normal graph-host
authority, existing writer/worker dependencies, normal scoped-read authority,
and authenticated ingress/read issuers. It fails closed before source
admission, egress, or write on any mismatch. It does not create a profile
union, a local runtime, a parallel coordinator, or a new graph/projection/read
protocol.

All pre-egress, pre-commit, recovery, and scoped-read checks reissue a fresh
typed local-authorization use that binds the sidecar digest, Bootstrap profile
verification digest, and resource-policy digest. The `local_level2` execution
class is persisted as operation provenance only; it never changes fact meaning
or selects a different core pipeline. Completed turn admission, retry/fencing,
restart, and protected recall use the existing Bootstrap V3 contracts as
specified in Section 8.

The profile coordinate is `("memorii.project_assertions", 1)`. It names the
bounded project-assertion ontology and proposal contract, not a model vendor.
It is an explicit non-bootstrap production profile. Its first transport binding
uses OpenAI `gpt-4.1-nano`; the exact endpoint, credential resolver reference, prompt,
output schema, predicate catalog, component fingerprints, timeouts, retry
budget, and egress policy are fields of production-certified material or the
fixed local-Level-2 authorization. No Hermes environment setting, request, or
turn may override those fields. Credential material stays inside the host's
existing OpenAI credential resolver and is never included in a source,
operation, graph record, log, or manifest digest.

The semantic profile and its provider transport are separate identities. The
profile owns supported predicates, typed values, quote-hint interpretation,
validation, and memory-domain routing. A provider binding owns the model,
endpoint, credentials, request/response transport, retention settings, and
provider-specific limits. A different model may implement the same proposal
contract, but requires a new explicit, verified provider binding and its own
behavioral evidence. Switching models must not silently change the ontology
version or the meaning of an already committed fact. The current OpenAI
transport is one implementation, not a dependency of the framework-neutral
memory contracts.

The installed bundle has separate digests for the semantic contract and the
complete provider-bound manifest. The semantic digest covers profile
coordinate, predicate catalog, typed value and routing policy, and adapter
semantic revision; it excludes model, endpoint, credentials, transport, and
prompt bytes. Candidate IDs use the semantic digest with source/segment and
quote content, so an equivalent provider binding does not rename the same
fact. The full manifest digest still authorizes the exact model and request
path used for this local run.

Production-certified activation uses the ordinary production host capability,
the existing `DeploymentAuthorizationVerifier`, and its externally provisioned
trust store. Level 2 local activation uses a separate, closed local authority
variant through the same first-party factory and semantic pipeline. Neither
path uses a trial release hierarchy:

```text
production trust store -> active deployment authorization -> approved profile
manifest -> normal provider factory

or, for this bounded Level 2 run:

explicit local operator authorization -> normal provider factory
  -> source-bound egress decision -> candidate validation
  -> fenced semantic transaction -> protected recall
```

This means a local Docker test exercises the same factory, ingress,
source-bound egress, validation, writer, storage, recovery, and protected-read
path as a normal deployment. It does not represent production-certified
authority. Section 3.25 defines the local authorization as an explicit,
installation-bound configuration record with authority kind
`local_level2_operator`, execution class `local_level2`, the fixed profile
coordinate, fixed model, exact component/prompt/predicate/egress digests,
Hermes-home binding, expiry, and the operator acknowledgement
`local_level2_openai_egress`. It is created only by the first-party
`memorii-hermes` console script after the operator explicitly enables the
profile; it has no API-key field and uses the existing Hermes credential
resolver.

The practical configuration is deliberately small: keep Hermes configured with
`memory.provider=memorii`, then run `memorii-hermes authorize-local-level2
--hermes-home <path> --acknowledge-openai-egress`. That script atomically
writes `<hermes-home>/memorii/local-level2.json` with the fixed profile
selection, local-enable flag, and authorization. It prints its digest and
expiry, not credentials. The factory rejects a missing, expired, altered,
wrong-home, wrong-installation, unknown-field, endpoint/model/profile mismatch,
or non-local CLI authorization with `profile_unavailable`, zero remote calls,
and zero semantic writes. Environment variables, a prompt, a Hermes request,
or arbitrary Hermes config keys cannot select the profile. A Level 2 run
produces operational learning only; it cannot issue `DeploymentAuthorizationArtifact`,
`CapabilityBaselineApprovalRelease`, acceptance evidence, held-out evaluation,
or an SIA-R14 certification claim. A true production rollout must obtain a
fresh signed production authorization; it cannot promote or convert the local
record.

The sidecar is strict canonical JSON with duplicate-key and unknown-field
rejection. It carries an opaque installation ID, a canonical home-path digest,
and separate domain-separated authorization and sidecar digests. The script
creates the installation ID at `<hermes-home>/memorii/installation-id`, then
writes the sidecar by same-directory temporary file, fsync, atomic replace, and
parent-directory fsync where supported. Startup, every egress check, and the
pre-commit check reload and validate it. A corrupted, truncated, or copied-only
sidecar at a different home, plus an expired or changed sidecar, is
`profile_unavailable` and makes zero remote calls/writes. A complete copied
Hermes home at the same canonical path cannot be distinguished without an
external host anchor, which is outside Level 2. The local file writer is trusted
as the local operator for Level 2; its digest detects corruption and does not
claim hostile local tamper protection.

The installed `memorii` package supplies the one exact
`project_assertions.v1` bundle: a manifest, fixed prompt, strict output
schema, three-predicate catalog, source-bound egress policy, and component
fingerprint list. The factory loads and recomputes the installed bundle digest
before startup and each egress. It uses OpenAI Responses with `gpt-4.1-nano`,
`store=false`, no tools, and no background request; it sends only the approved
source segment and bounded fixed prompt context. A missing or altered bundle,
component drift, or digest mismatch is `profile_unavailable` with no remote
call. The script discloses that API data is not used for training by default,
that default abuse-monitoring logs may retain content for up to 30 days, and
that provider-default routing offers no residency guarantee. Project-specific
provider data controls are not inferred by this profile.

The schema returns only untrusted quote hints: predicate ID plus assertion,
subject, predicate-anchor, and value quotes. The active production route is
Bootstrap V3, whose remote boundary is `BootstrapV3ProposalTransport` returning
`ProviderSemanticProposal`, not `SemanticCandidate`. The profile adapter must
derive mentions, predicate-fixed object representation, local IDs, positive
asserted fact fields, and abstention deterministically from those quotes, then
the existing V3 normalizer resolves each quote against the immutable authorized
projection. The model supplies no entity ID, literal type/value, polarity,
commitment, attribution, scope, or truth authority.

The first-party factory must provide a complete non-fixture V3 host bundle:
profile-bound authority and payload limits, OpenAI proposal transport, verified
no-download Stanza and spaCy lanes, project-predicate detector, temporal
resolver, request constructors, and a non-scenario graph-host authority with
policies for all three predicates. Current bootstrap V3 material does not
provide that bundle, so it cannot commit project facts. Until it exists, startup
must be unavailable or outcomes evidence-only; a parallel coordinator would not
exercise the production persistence and recovery path.

The factory accepts the normal configuration surface for selecting the profile
coordinate and normal Hermes data root. Its verified semantic-profile material
is a closed union of bootstrap, production-certified, and local-Level-2
authority variants. Only the factory host boundary may construct the local
variant; core never accepts a caller-provided mode, signature, trust domain, or
model configuration. Bootstrap stays network-denied and default when no
explicit profile is selected. The selected profile has no fallback to bootstrap
after selection: authorization or transport failure is a truthful
non-committing outcome.

The new profile requires only the smallest generalization of the current
bootstrap-specific composition contract: the production factory receives a
host-verified semantic-profile material object whose coordinate, manifest,
typed authority variant, egress policy, component fingerprints, ingress
resolver, and transport builder are bound together. Bootstrap, production, and
local-Level-2 material implement that contract. The local variant is restricted
to one local CLI installation and rejects gateway, shared-profile, delegated,
cron, and multi-user execution before admission. This keeps the core
framework-neutral and avoids a Hermes-specific profile system.

## Eligible free-form facts

Automatic promotion is limited to direct, reusable project assertions. An
eligible assertion has an identifiable project subject, one registered
predicate, a typed value, direct speaker attribution, and one unique verbatim
source quote. The initial profile catalog contains:

| Predicate | Subject | Value | Current-value policy |
| --- | --- | --- | --- |
| `project_owner` | normalized `ProjectId` | normalized `PersonName` | one current value |
| `project_status` | normalized `ProjectId` | source-grounded `StatusText` | one current value |
| `project_deadline` | normalized `ProjectId` | unambiguous ISO `LocalDate` | one current value |

Natural language is free-form within these relations. For example, “Rhea is
leading Atlas”, “Atlas moved into planning”, and “We set Atlas's deadline to
2027-03-04” can be eligible; the fixed sentences from the development connector
are not privileged. The model may propose a predicate and quoted spans but
cannot create a predicate, identity, scope, or truth value.

These three predicates are a bounded Level 2 vertical slice, not Memorii's
complete ontology. Expansion uses versioned, content-bound domain catalogs:
each supported relation declares its entity/value types, scope, cardinality,
temporal and correction policies, evidence requirements, and read behavior.
The active catalog joins the appropriate memory-domain policy and graph writer.
Fact ingestion selects registered relations. A separate ontology-learning
process may propose new concepts or relations; only validated, activated
ontology versions become available to fact ingestion. An added or changed
relation gets a new catalog version and explicit upgrade/read-compatibility
handling for persisted facts.

Personal memory and enterprise knowledge require separate catalog and routing
work. A stable personal preference belongs to user-context memory with user
scope and its own candidate/confirmation rules; it is not promoted by adding a
`preference` predicate to this global semantic profile. Organization facts may
use semantic predicates with tenant scope, while tasks, decisions, episodes,
and solver observations remain in their respective domains. Future packs can
cover those use cases through the same source, proposal, validation, commit,
and protected-read interfaces. Unsupported relations remain source evidence
until their domain contract and policy are implemented and verified. The
Hermes and OpenClaw adapters translate conversation events into these shared
contracts; neither adapter owns the ontology.

Questions, commands, hypotheticals, quotations, reported claims, pasted text,
assistant-only statements, ambiguous references, unsupported languages,
uncertain dates, and unsupported relations remain retained evidence without a
semantic fact. An ordinary user preference remains transcript evidence;
preference memory needs an explicit user-memory request and its separate
validation path. Corrections follow the existing typed correction policy or
remain contested/evidence-only.

## Ontology learning beyond the initial seed

Workflow status: direction captured; full build-design workflow incomplete.
The earlier Hermes cohort and provider/ontology identity review do not approve
this ontology-learning lifecycle. Its phase audit is recorded in the linked
`docs/work/hermes-conversation-memory-trial/design.plan.md` WorkPlan.

### Product intent and scope

Memorii must learn and evolve ontologies from the domains encountered by agent
harnesses. A finite, manually enumerated catalog cannot cover personal and
enterprise activity. The three project predicates are the initial integration
seed, not the permanent limit or the complete ontology. Manually authored
catalogs may bootstrap learning, but adding catalogs by hand is not the sole
extension mechanism.

Hermes and OpenClaw are agent harnesses. A user request may involve delegated
subagents, tools, documents, databases, or a bot channel such as Slack. These
activities can contribute evidence about missing concepts and relations.
Harness callbacks and channel adapters carry authenticated scope and provenance
into framework-neutral core contracts; a channel name or a subagent's statement
does not itself authorize shared knowledge. The first Level 2 test remains a
single local CLI session. Delegation and bot-channel ingestion require their
own implemented identity and scope bindings before activation.

### Distinct learning operations

Fact learning instantiates an existing concept or relation. Ontology learning
proposes changes to the concepts, relations, definitions, aliases, constraints,
or mappings used to interpret future evidence. Both have candidate and committed
states, but their validation and activation are distinct. A fact proposal cannot
silently extend the active schema, and an accepted ontology change does not by
itself make any source assertion true.

The target learning loop is:

1. Retain scoped source evidence and interaction outcomes, including unfamiliar
   concepts, unsupported relations, ambiguous mappings, and recurring retrieval
   or validation failures. Repeated subagent copies retain their common source
   lineage and do not count as independent corroboration.
2. Diagnose whether the limitation concerns missing content, the ontology's
   representation, or how existing knowledge is exposed to the agent. A failed
   answer alone does not establish that the ontology needs to change.
3. Produce a bounded typed change proposal with its parent ontology version,
   supporting source references, intended scope, proposed meaning and types,
   constraints, and expected effect on agent behavior. The proposer has no
   authority to activate it.
4. Validate grounding, compatibility with existing concepts, identity and alias
   ambiguity, memory-domain routing, temporal and correction behavior, scope,
   and persisted-data consequences. Evaluate the candidate against its parent
   on the same representative tasks and budgets, including regressions and
   withheld evaluation cases. Improved answer scores cannot override a failed
   authorization, provenance, or data-integrity check.
5. Publish an accepted immutable ontology version through a scope-authorized
   activation owner. Retain rejected proposals and reasons. In-flight ingestion
   pins its ontology version; activation must not reinterpret an existing
   operation or historical fact in place. Supersession and rollback preserve
   history and explicit compatibility rules.
6. Reconsider eligible retained evidence under the new version through normal
   fact ingestion, with fresh authorization and idempotent replay. Schema
   acceptance does not bypass the semantic validator or writer.

An ontology learned in a private user scope or one enterprise tenant remains
in that scope. Publication into a wider catalog requires a separate authorized
promotion and review of supporting evidence for disclosure. Subagents inherit
only their granted access; they cannot widen it by proposing an ontology edit.
Model-specific prompts, retrieval presentation, and tool behavior may be tuned
and evaluated separately while canonical semantic meanings remain provider
independent. A model change requires behavioral evaluation, not an automatic
change to the ontology's meaning.

### Evidence, delivery, and implementation boundary

This direction draws on [EvoOntology](https://arxiv.org/html/2609.15779v1): its
separation of schema, content, and tool exposure; evidence-grounded construction;
and trajectory-informed typed edits with paired evaluation. These are design
inputs. Its data-agent results are not evidence that Memorii's implementation
already supports ontology learning or that a particular proposed edit is safe.

After the real Hermes integration test, a linked design must specify the core
proposal, catalog, evaluation, activation, migration, and replay contracts and
map them to actual production callers. Required scenarios include discovering
a previously unsupported relation, rejecting an unsupported or harmful edit,
preserving tenant/user boundaries, treating correlated subagent evidence
correctly, preserving historical meaning, and safely replaying retained sources
after activation. Exact evaluation thresholds, schema-change support, and
operator-versus-automatic activation policy remain to be designed before that
implementation; this section does not authorize arbitrary runtime schema edits.

Ontology learning is required product direction, currently unimplemented. It
does not add a prerequisite to the first Level 2 conversation-to-fact-to-recall
test. That test produces the real interaction evidence needed to guide the
subsequent ontology-learning work.

## Turn admission and semantic commit

Hermes does not supply an immutable user principal or turn identifier. This
Level 2 local CLI profile therefore supports one operator for one local
installation. `turn_author`, `author_id`, and other raw Hermes strings are
not identity authority. Multi-user, gateway, delegated, cron, and shared-profile
use fail closed for automatic promotion.

The bridge promotes only a completed pair with its ordered `messages` snapshot.
It derives a delivery coordinate from the verified profile coordinate, opaque
installation principal, opaque session handle, completed user-turn ordinal,
user and assistant content digests, and a prefix-chain digest. The source
ledger retains this coordinate and snapshot digest. Equal content at different
ordinals has different coordinates. Exact redelivery with matching content and
prefix returns the existing operation; the same coordinate with a different
body/prefix, a missing snapshot, a rewind, or reordered history creates no
semantic operation. The initial real-loader test must demonstrate that the
pinned Hermes version supplies the required completed snapshot.

`sync_turn` calls one production-core completed-turn admission operation. Under
one writer fence it persists the delivery ledger, both raw child sources, and a
pending semantic operation in one transaction. It does not use the current
sequential child fan-out. A failure before commit exposes none of that group;
the worker can never process a half-turn. User text is the only automatic
semantic source; assistant text is retained evidence.

Routing is typed and explicit: eligible direct project assertions enter the
governed semantic candidate path; explicit user-memory requests enter the user
path; all other normal turns remain raw evidence. The ordinary chat blocking
policy continues to prohibit direct semantic commits. The prepared source
segment is sent only after a current source-and-segment-bound
`allow_verbatim` egress decision. The profile transport uses one host-built
OpenAI client with the signed binding. It sends the authorized segment and
bounded prompt context, never a whole transcript, and has no model fallback.

Remote output is untrusted candidate data. Malformed output, unmatched or
invented quotes, unsupported predicates, attribution/scope disagreement,
invalid types, duplicate candidate content, timeout, or provider failure
cannot commit. Existing source analysis, role/scope/attribution validation,
candidate lifecycle, and the single semantic transaction writer remain the
canonical owners. The old `LLMMemoryExtractor` and development connector are
not writers for this profile.

One semantic transaction publishes the graph delta, canonical event, terminal
outcome, and a current `SEMANTIC` Memory Plane projection with provenance
references. A projection is a read view of the committed graph transaction, not
a second writer. Replay reconstructs the same projection; a graph record
without it is not retrieval-visible to Hermes.

## Protected recall, recovery, and operation limits

Transcript sources retain their original local-installation and session scope.
A committed reusable project fact has a global semantic projection inside that
same installation's normal Memorii root. The production runtime issues a fresh
outer read capability bound to the installation principal, Hermes session, query
digest, `semantic_recall` purpose, current authorization epoch, expiry, and a
finite set of allowed projection IDs. It validates that capability before
issuing the existing opaque `ScopedHostReadAuthority` to
`ProviderMemoryService.retrieve_context`.

The request asks only for `SEMANTIC` records. The reader takes one snapshot,
checks committed current status and provenance closure, then releases only
authorized semantic content. Transcript records can close provenance only
through the narrow exact-grant source-closure rule; they are never recall
candidates or rendered context. Empty, expired, revoked, wrong-session,
wrong-purpose, or substituted grants return empty non-disclosing context. The
legacy prefetch path cannot satisfy semantic recall and is not used by the new
bridge.

`sync_turn` waits only for atomic raw admission and durable pending state. One
production worker holds a renewable writer lease for remote proposal and semantic
commit. Its durable states are `pending`, `running`, `committed`,
`abstained`, `retryable_failure`, `terminal_failure`, and
`authority_unavailable`. The verified profile material fixes a 60-second
renewable recovery claim with renewal at every stage boundary, two total
provider attempts, a 10-minute renewable
operation lease, and a 20-second read budget. The longer operation lease is a
Level 2 bound for the existing sealed Bootstrap V3 graph transaction, whose
filesystem commit path can exceed 60 seconds; it does not add another graph
protocol or bypass lease validation.
Each retry and commit rechecks profile authorization, egress, lease, and writer
epoch. Restart reclaims only expired leases and resumes from durable attempt
state. A commit, graph event, projection, and outcome become visible together;
an acknowledgement loss reloads by delivery coordinate. Authority loss is
non-retrying for that delivery and never becomes a later second commit.

## Docker rollout and trial evidence

The Docker image installs the first-party production Hermes integration and
exactly one `memorii.hermes.provider_service` entry point. It removes
`memorii-hermes-development-connector`; image startup fails if development and
production factories are both present. The existing `hermes-memorii` container
must be recreated from the rebuilt image because an editable package added to
an image is not replaced by a `docker restart`. The Level 2 trial creates a new
named `/opt/data` volume for the current image digest and discards prior local/
development volumes. Restart uses that same new volume.

The first-party operator surface is:

```text
hermes config set memory.provider memorii
memorii-hermes authorize-local-level2 --hermes-home /opt/data --acknowledge-openai-egress
memorii-hermes status --hermes-home /opt/data
hermes memory status
python -m memorii.hermes.inspect summary --hermes-home /opt/data
```

The authorization command requires the fixed egress acknowledgement and writes
the installation-bound local sidecar under `/opt/data/memorii`. It reports its
digest and expiry. `memorii-hermes status` reports `authority: local_level2`,
coordinate, expiry, and `not production certified`. `hermes memory status`
continues to report the active Memorii provider; inspection reports authority
kind, operation state, graph/projection counts, and protected recall result.
These surfaces never print credential material or raw transcript text.

The Windows Docker test uses the pinned installed Hermes loader, not a direct
Python call. Before a live provider request it records the Bootstrap V3 resource
policy coordinate, authority kind, and authority digest, then uses two preselected fresh facts and
later recall queries. It must inspect delivery, source, operation, graph,
projection, and protected recall results after each run. A real OpenAI result
is operational evidence only for the exact image and authorization revision;
fake transport remains deterministic plumbing evidence.

| Proof family | Required result |
| --- | --- |
| Factory and authority | Bootstrap V3 remains the one runtime. Its project-assertions resource policy with fixed OpenAI binding starts only through a complete host-input envelope from the production verifier or exact local-Level-2 sidecar/resources; missing, corrupt, truncated, moved-home, sidecar-only copy, expired, altered authority, or resource/component digest drift makes zero remote calls/writes. Crash/restart observes the old valid sidecar, a complete replacement, or unavailable. A complete home clone at the same canonical path needs an external host anchor and is outside Level 2. Local authority cannot pass a production-certification or held-out-evaluation gate. |
| Real Hermes path | Installed loader -> factory -> real `sync_turn` -> atomic pending operation -> worker -> committed semantic projection -> protected `prefetch`; direct bridge calls do not count. |
| Positive recall | Two fresh free-form eligible assertions recall in a later session and after restart with source provenance; disabling semantic projection makes the assertion fail. |
| Routing and exclusion | Preference, question, command, quote, ambiguity, unsupported relation/language, assistant claim, and malformed proposal retain evidence without semantic commit; determinate pre-egress cases make zero calls. The authorized call uses fixed Responses `store=false`, no tools/background mode, fixed prompt/schema/catalog, and only the approved source segment. Bootstrap V3 remains unavailable until its complete host-input envelope is installed. |
| Identity and scope | Equal text at distinct ordinals remains distinct; exact replay is one operation; changed/missing/reordered snapshot denies. Wrong installation/session/query/purpose/grant returns no context or existence hint. |
| Retry and recovery | Timeout, retry, crash before/after transaction, acknowledgement loss, and restart yield one terminal outcome and either the entire graph/event/projection group or none. |
| Packaging | One uniquely named image digest and clean named data volume contain the first-party factory; baseline has zero semantic operations/graph/projections/retrieval-visible records, and the same new volume survives restart. |

## Implementation handoff and limits

| Trigger | Canonical handoff | Required outcome |
| --- | --- | --- |
| Hermes loader -> installed bridge `initialize` | Bootstrap V3 factory verifies its Bootstrap profile and constructs one opaque host-input envelope through production verifier or local adapter, then creates worker and opaque ingress/read issuers | started runtime or `profile_unavailable` |
| Hermes `sync_turn` | bridge -> atomic completed-turn admission -> candidate worker -> existing semantic writer | raw pair/pending operation, then one terminal graph/event/projection/outcome |
| Hermes `prefetch` | bridge -> outer capability validation -> `ProviderMemoryService.retrieve_context` | source-grounded semantic context or empty result |
| restart/inspection | factory startup reconciliation and protected outcome accessor | reclaimed work and bounded diagnostics |

The implementation must update the production-entrypoint binding ledger with
the exact installed call sites and caller counts. It must add the one opaque
Bootstrap V3 host-input envelope without an ambient model selector or
caller-constructed authority. Until these changes exist, this design is specified only; no test
result should be described as semantic ingestion.

Level 3 follow-up: broad multi-operator/platform coverage, hostile-storage and
forged-authority matrices, production rollout approval, and certification scope
for a signed production deployment authorization. The local Level 2
authorization is never a rollout artifact.
