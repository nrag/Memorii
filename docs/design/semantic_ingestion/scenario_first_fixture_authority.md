# Scenario-First scenario-first closure Fixture Authority

## Status and scope

This is the normative replacement for scenario-first closure's field-by-field expected-output
authority. It applies only to non-operational semantic-ingestion fixtures. It
does not provision production trust, activate a production release, certify an
operational run, or change M1 behavior.

The fixture emits operational-shaped registered CTV bodies so the normal
decoder, DAG, and release-closure verifier exercise their production wire
contracts. Every such body is signed by a dedicated deterministic test-only
trust root. That root exists only in the separately bounded `scenario_test`
host trust-domain capability and is absent from default/production capability
discovery. Production trust lookup must reject the same bytes before release
authority can be established; the scenario runner must likewise reject the
production and unrelated roots.

Genesis fixture roots use the typed `independently_provisioned_genesis`
provenance variant defined by the architecture. It names a verifier-held
provisioned channel, root digest, provision time, and provisioning signer; it
does not fabricate a lifecycle record. Once the fixture's lifecycle activates a
root, all successor fixture bodies use `prior_verified_lifecycle_root` and the
exact lifecycle root/record coordinate. Unknown variants and mixed legacy
structural projections reject before the scenario test resolver can advance a
watermark.

The scenario structural member is the complete
`NormativeTraceabilityStructuralManifestBody` reconstruction, not the legacy
six/seven-field byte wrapper. The two elaborators must separately derive all
field/default/rule/mapping/entry/override/anchor values, apply the architecture
limits, and compare the outer CTV bytes. A missing authority binding or any
field without a declared domain is a fail-closed fixture rejection.

The authoritative input is a closed `memorii-sia-scenario-first-v1` document.
The initial finite document is
`traceability_golden_vectors/scenario-first-v1.json`. It is deliberately small
and supports only the runtime's deterministic English-rule subset: positive,
directly attributed `owner` and `status` assertions. A scenario outside that
subset is retained as an explicit negative, ambiguous, or insufficient-evidence
case; it cannot be mislabeled as a passing round-trip case.

## Authority and isolation

The scenario file is split into two views. The renderer receives only entities,
claim references, turn metadata, and the rendering grammar. The extractor sees
only `SourceObservation` values produced by the renderer. It receives neither
scenario IDs, expected projections, expected verdicts, hidden entity IDs, nor
the comparison result. Persistence receives only the extractor's ordinary
proposal. The comparator is the sole consumer of hidden scenario truth.

No LLM, production extractor, persistence result, generated digest, signature,
or existing golden artifact may author scenario truth. The production local
ingestion path is a system under test. The feasibility run invokes ordinary
`ProviderMemoryService` ingress with a scenario-test-material
`BuiltInLocalHostSemanticIngestionCapability`, not a direct extractor callback,
fixture proposal, or an oracle-shaped fake. The capability uses the corrected
V1 finite corpus and local analyzer described in Section 3.23.0; scenario test
material is rejected by default and production host trust boundaries.

Scenario traversal is zero-based and declaration ordered: the validator walks
the root `scenarios` array from index `0`, then each selected scenario's
`interaction.turns` array from index `0`. `traversal_ordinal` is the resulting
zero-based global position; it is not a scenario ID, turn ID, verdict, or
hidden entity identity. For each rendered turn, renderer A emits this exact
declaration-ordered typed-value body, with no aliases, defaults, omitted nulls,
or additional fields:

```text
schema_id = "memorii.scenario_first.public_ingress_id"
schema_version = 1
traversal_ordinal = <non-negative integer>
rendered_source_sha256 = <64 lowercase hex SHA-256 of exact rendered UTF-8 bytes>
user_id = <non-empty public scope string>
session_id = <non-empty public scope string>
task_id = <non-empty public scope string>
```

The preimage is `encode_typed_value` of that declaration-ordered body using
the existing `semantic_ingestion_typed_value` canonical profile, prefixed by
the exact ASCII domain bytes
`memorii.scenario-first.public-ingress-id.v1\0`. The opaque event ID spelling
is exactly `scenario-event-` followed by the first 32 lowercase hexadecimal
characters of SHA-256 over those prefixed bytes. The host-visible normalized
source ID is exactly `tx:` plus that opaque event ID. No private scenario field
is an operand.

Renderer B independently reproduces the traversal, declaration-ordered CTV
bytes, digest, event ID, and normalized source ID without importing renderer
A or its ID helper; their byte-for-byte agreement is required before ingress.
The mutation matrix changes each preimage field, field order, typed-value
profile, domain byte, output prefix, truncation length, hex case, `tx:` source
spelling, traversal order, and duplicate/reused event ID; each mutation must
fail before host ingress. Its private renderer/comparator map is the sole
mapping from the opaque event/source pair to a scenario turn. The host sees
neither a scenario ID, classification, expectation, hidden entity ID, nor a
reversible mapping value. Trace and persistence proof rejects attempts to pass
the private map through event fields, ingress, host material, traces, or
persisted records.

Opaque runtime IDs and output ordering are intentionally not compared. The
comparator preserves, and fails on a difference in, claim multiplicity, entity
role, entity-versus-literal object, predicate, polarity, modality, direct
attribution, half-open temporal bounds, complete scope, source type/ID, exact
evidence quote/byte offsets, terminal run status, and abstention. Equal
duplicate evidence is a cardinality failure; `ambiguous` requires distinct
values for one declared single-valued semantic key.
The current runtime proposal cannot represent every one of those fields. The
scenario validator therefore admits only the supported direct-positive subset
to `supported_roundtrip`; the missing semantic dimensions are schema-required
and are comparison obligations before their values may enter that class.

## Closed schema

A scenario has exactly `scenario_id`, `classification`, `entities`, `claims`,
`interaction`, and `expectation`. IDs are stable and unique within a scenario.
Each entity has `id`, `name`, and type. Each claim has an explicit subject,
predicate, object, polarity, modality, attribution, temporal interval, scope,
and provenance. Each interaction turn names its speaker, source kind,
timestamp, and every claim it renders exactly once.

The accepted classifications are:

- `supported_roundtrip`: normalized extraction must equal the hidden scenario
  projection exactly.
- `ambiguous`: multiple otherwise valid values for one single-valued semantic
  key must produce the comparator result `ambiguous`, never a silently chosen
  winner.
- `insufficient_evidence` and `negative`: the renderer exposes no admissible
  source assertion and the extractor must abstain.

The schema is closed and fails unknown fields, duplicate IDs, missing or
multiply rendered claims, claim/turn source-ID disagreement, non-UTC RFC3339
timestamps, invalid intervals, speaker/provenance mismatch, unsupported
predicates, non-direct attribution, incomplete scope/provenance, and mismatched
classification/verdict. `supported_roundtrip` has exactly one value per
single-valued key; `ambiguous` has two or more distinct values for one key; and
`negative`/`insufficient_evidence` contain no admitted claim. Expanding the
supported subset is a reviewed design change: it requires a declared renderer
grammar, an extractor capability, and a comparator projection for each new
polarity, modality, attribution, temporal, and scope form.

## Rendering and span contract

Renderer A maps one private scenario turn to one `RenderedScenarioObservation`.
Its private `turn_id` remains only in the renderer/comparator view. For ordinal
`n`, the renderer derives the host-visible opaque event ID exactly as Section
3.23.0 requires; the public provider event operation ID is that value, and the
host-visible normalized source ID is the normal `tx:<opaque-event-id>` form.
The `SourceObservation`, authenticated ingress, host capability, provider
result, trace, and persisted records receive only the opaque IDs and ordinary
public source bytes/metadata. The renderer/comparator keeps the only private
map from `(opaque-event-id, tx:<opaque-event-id>)` to `turn_id`; that map is
not serialized, returned by the runner, included in a CTV body, or passed to
any production owner.

It uses only the fixed grammar `Subject owner is Person.` or `Subject status is
value.`; a non-assertion becomes the fixed insufficient-evidence sentence. The
source kind is `user`, language is `en`, and scope/timestamp are copied from
the scenario. Speaker is bound in the source envelope and must match direct
attribution. Before comparison, and only in comparator-private state, actual
host source IDs are remapped through the private map to the scenario provenance
turn ID. The extracted evidence quote and byte offsets are checked against the
rendered UTF-8 source bytes after that remap. Rendered texts, speaker/turn
ordering, private mapping, and span map are run artifacts, not scenario
authority.

The runner must prove one positive opaque-ID/remap execution; rejection before
ingress for a missing map member, an injected opaque ID, or an ID reused for a
different ordinal/source-digest/scope tuple; and exact same-ID retry/reopen
equality for the same tuple. A trace-and-persistence leak proof inspects public
event fields, authenticated ingress, host material, provider result, trace
records, and persisted artifacts and rejects any private `turn_id`, scenario
ID, classification, expectation, or private-map value. Comparator remapping is
also exercised for every owner/status/abstain/ambiguous outcome and must reject
an absent, extra, swapped, or non-`tx:` source coordinate.

Metamorphic variants are generated from the same hidden world: opaque scenario
and entity IDs are permuted; independent turns are reordered; unrelated
insufficient-evidence turns are inserted; and equivalent source chunking is
applied only where the declared grammar preserves unique spans. Each must keep
the normalized result unchanged. A changed claim, provenance, scope, temporal
boundary, polarity, or cardinality must fail.

## scenario-first closure derivation

Fixture 35 becomes a current-v2 typed input containing the rendered interaction
bytes, source-envelope metadata, span map, extractor identity, and actual
normalized extraction evidence for one named `supported_roundtrip` scenario.
Its CTV body is generated from that run and is never a primitive v1 byte blob.
Fixture 35 remains non-operational and cannot be used as a trust artifact.

The structural manifest derives from the pinned design, registry, scenario
schema, scenario bytes, renderer/checker source, and actual run bytes. Coverage
records derive from requirement-to-scenario coverage and the comparator result.
Execution evidence derives from exact runner command, environment profile,
rendered observations, extractor output, normalized output, and checker result.
G1/G2/G3 manifests, release/pointer histories, and CTV-v2 envelopes derive
from those content-addressed run artifacts plus a fixed test-only
administrative state. Their registered issuance-purpose values remain
operational-shaped because the existing schemas require them; authority is
constrained solely by the injected test root. No expected digest, signature
preimage, root, or verdict is manually copied into a primitive fixture table.

The administrator state is finite and declares the deterministic test signer,
generation order, predecessor rules, fixed clock, and test-only key material.
It must be separate from scenario truth. A generation fails if
any content address, scenario validation, extraction run, comparator result,
CTV-v2 decode, or predecessor binding differs.

## Alternative rejected

A direct expected-artifact table was considered. It can cover all output bytes
but requires selecting 1,452 field-level operands/preimages and permits the
same authoring path to manufacture expected evidence and verify itself. It is
rejected because it provides no independent semantic cause for those bytes and
reintroduces the prior design-authority blocker. Scenario-first authority fixes
the semantic cause, while generated artifacts retain byte-level checks.

## Migration, resources, and rollback

The historical recipe and v1 fixture 35 are provenance only. New scenario-first closure consumers
accept only current-v2 scenario-derived outputs. During migration, run both
legacy inspection (read-only) and scenario-first generation; do not compare
their bytes as compatibility evidence. Rollback disables the scenario-first
gate and leaves no production active pointer changed. Test-root pointer state
is isolated in the test trust store and cannot be resolved by the
production/default store.

Generation caps are canonical: scenarios <= 10,000; turns <= 100,000; rendered
source bytes per turn <= 64 KiB; total rendered bytes <= 64 MiB; structural spool
bytes <= 128 MiB; extractor/ingress wall time <= 30 seconds; structural
reconstruction wall time <= 60 seconds; and automatic retries = 0. The scenario
authority has no larger implicit cap. It uses public provider composition and
ingress through the built-in capability; an oracle spy proves hidden truth is
absent from constructor arguments, prompt variables, source envelopes,
persistence payloads, and traces. It spools large structural members and
records per-member digests.
Timeout, cap exhaustion, or interruption fails closed and rollback changes no
active pointer; it is never truncation or retry.

## Feasibility evidence

Run from repository root:

```sh
PYTHONPATH=memorii .venv/bin/python docs/design/semantic_ingestion/traceability_golden_vectors/validate_scenario_first.py docs/design/semantic_ingestion/traceability_golden_vectors/scenario-first-v1.json
```

The validator is independent from the renderer/runtime output comparison: it
validates hidden truth before rendering, then the built-in host capability
receives only authenticated public observations, and the comparator projects
only actual protected terminal/output evidence. The initial four-case spike
proves `match`, `ambiguous`, and `abstain` paths. It does not claim live-LLM
quality or production persistence certification.

The public-ingress and clean-room elaboration feasibility command is:

```sh
run_dir=$(mktemp -d /private/tmp/memorii-scenario-first-closure.XXXXXX)
PYTHONPATH=memorii .venv/bin/python docs/design/semantic_ingestion/traceability_golden_vectors/run_scenario_ingress.py docs/design/semantic_ingestion/traceability_golden_vectors/scenario-first-v1.json "$run_dir/run.json" --design docs/design/semantic_ingestion_architecture.md --registry docs/design/semantic_ingestion/traceability_registry/registry-v1.json
.venv/bin/python docs/design/semantic_ingestion/traceability_golden_vectors/elaborate_scenario_a.py docs/design/semantic_ingestion/traceability_golden_vectors/scenario-first-v1.json "$run_dir/run.json" docs/design/semantic_ingestion_architecture.md docs/design/semantic_ingestion/traceability_registry/registry-v1.json "$run_dir/a.json"
.venv/bin/python docs/design/semantic_ingestion/traceability_golden_vectors/elaborate_scenario_b.py docs/design/semantic_ingestion/traceability_golden_vectors/scenario-first-v1.json "$run_dir/run.json" docs/design/semantic_ingestion_architecture.md docs/design/semantic_ingestion/traceability_registry/registry-v1.json "$run_dir/b.json"
cmp "$run_dir/a.json" "$run_dir/b.json" && cmp "$run_dir/a.structural.spool" "$run_dir/b.structural.spool"
```

Elaborator A may be the production/reference compiler. Elaborator B is
clean-room: it may share only command inputs, frozen JSON/SHA-256/CTV
specifications, and the ledger; it must not import elaborator A, production
derivation code, generated A output, or A's mapping/normalization helpers. The
pair is credible only when an import gate compares complete decoded body,
envelope bytes/digest, and structural spool, and the adversarial corpus covers
field order, domains, provenance variants, resolver/watermark paths, legacy and
mixed-generation migration, rollback, and interruption. Later full-generation
work derives RFC8032 signatures from an isolated test root. Those signatures are
accepted only by the scenario-test trust-domain capability and rejected by
production/default lookup. The three-root domain proof also rejects production
and unrelated roots at the scenario runner, and scenario-test and unrelated
roots at production/default entry points.
