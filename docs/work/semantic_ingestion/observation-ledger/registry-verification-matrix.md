# Operational Profile Registry Verification Matrix

Status: bounded implementation/test preparation. This is neither a registry
publication nor runtime activation. It maps the fixed profile-3 declaration
inputs in `operational-profile.md` and the current fixed-envelope boundary in
`memorii/memorii/core/memory_evolution/ingestion_contracts.py` to finite tests.

## Boundary

Decoder-source manifest evidence includes exact raw-byte digest recomputation;
terminal-LF, noncanonical serialization, profile/type mismatch and changed
manifest rows with otherwise identical selected-file snapshots must reject.
Native historical receipt evidence includes a valid but different prefix binding
substitution and unequal direct reload/core receipt copies; both must reject
after later publications advance the current head.

The profile-3 compiler consumes exact UTF-8 declaration source bytes. It must
not inspect Python classes, annotations, module names, import side effects,
callback identity, source file names, or an existing decoder implementation to
derive a role digest or binding. A decoder implementation digest is declared
source data; it is verified as a pinned source dependency after declaration
validation and does not select a decoder.

The writer emits the fixed four-field envelope before any body decoder runs:
`binding`, `canonical_value_bytes`, `canonical_value_digest`, and
`artifact_digest`. The reader parses only that outer scalar/map/bytes subset,
checks its two native digests and complete six-field binding, resolves one
protected historical registry entry authorized by its immutable read status, and only then invokes the body
decoder. Profile 2 remains on its existing historical route with its original
bytes and digests; profile-3 tests do not regenerate or accept fixture-v2 as
profile-3 authority.

## Raw source grammar matrix

| Family | Positive construction | Negative cases that must reject before registry construction |
| --- | --- | --- |
| Source bytes | One no-terminal-LF RFC 8785 JSON source per declared role, ASCII nonempty keys, encoded-JSON-string key order | terminal LF, invalid UTF-8, duplicate/reordered keys, JSON number, non-ASCII key, empty key, extra role field |
| Grammar role | Exact published literal grammar bytes and independently expected grammar/profile LP hashes | changed tag, envelope field, profile revision, or rule ID; self `grammar_digest`/`profile_digest` field |
| Schema/TypeExpr | Exact closed recursive schema with unique field names and valid `ModelRef`/`EnumRef` closure | unknown kind, `Any`, callable/class/reference-by-import, implicit union, unresolved/self/cyclic model reference, duplicate coordinate or field |
| Enum/optional/numeric | Complete enum table; optional field set equals schema fields; numeric rows match only wrappers | alias/duplicate enum, omitted/extra optional row, wrapper without numeric row, decimal/binary64 nullability/range mismatch |
| Integrity policy | Exactly one closed ordinary/self-digest/signature-only policy; checkpoint-only external preimage uses literal coordinate/purpose | arbitrary exclusions/members, multiple integrity fields, mismatched field role, external-preimage use outside checkpoint, altered literal purpose/domain |
| Decoder/upcast | Exact decoder ID/root kind/source hash; v3 null-only upcast role | missing/extra decoder fields, unknown root kind, changed source hash, non-null v3 upcast or callback-loaded implementation |
| Manifest/registry role | Complete unique role set, sorted role list, matching role hashes/profile record, and external whole-file decoder-source manifest/snapshot pins | missing/extra/duplicate role, wrong order/hash, source role repeats, registry profile digest mismatch, source-region selector, or missing decoder snapshot pin |

## Registry and pin closure matrix

| Family | Required positive proof | Required negative proof |
| --- | --- | --- |
| Profile identity | Independently authored compiler computes grammar digest then `SHA256(LP(domain, profile_id, version, revision, grammar_bytes))` | altered member, order, length prefix, UTF-8 bytes, or domain changes the result and rejects the declared profile |
| Schema closure | Root fingerprint includes ordered reachable schema-role bytes and declared external checkpoint-preimage edge | nested role/policy/enum change, missing edge, unresolved reference, cycle, or reordered closure changes/rejects binding |
| Policy closure | Enum, optional, numeric, and integrity policies pin the complete reachable closure | a structurally identical root with one nested policy difference cannot retain entry/binding digest |
| Decoder pin | Registry verifies declared implementation source digest against independently supplied pinned source bytes before decoder registration | substituted bytes, same decoder ID with different source hash, unavailable source, or decoder not named by selected entry rejects |
| Protected registry | Composition supplies immutable registry history; one complete embedded binding resolves to exactly one byte-identical original entry under its declared status permission | caller-selected registry/profile/decoder, missing/conflicting same-coordinate entry, duplicate binding, non-active writer entry, or ambiguous/current fallback rejects |
| Native digest preservation | Existing `CanonicalEncodedArtifact` native canonical-value and artifact digest algorithms recompute over exact bytes | profile-3 publication must not replace native artifact digest domains, normalize bytes, or reinterpret profile-2 artifacts |

## Fixed-envelope-before-body matrix

| Stage | Positive vector | Negative vector |
| --- | --- | --- |
| Outer parse | Four exact fields and six exact binding fields with strict scalar spellings | extra/missing field, alternate tag, number/bool where integer/string is required, noncanonical base64, duplicate map key |
| Native checks | Exact `canonical_value_bytes`, canonical-value digest, artifact digest, profile digest, and binding digest | alter any byte/digest/binding coordinate; reject before body decoding |
| Entry selection | Protected registry returns one exact historical entry after full binding equality and status authorization | body hint, schema ID alone, current-profile fallback, filename dispatch, replay-only write, retired public read, unknown or duplicate binding |
| Body decode | Selected registered decoder accepts then re-encodes byte-identically | body decoder invocation before native checks, unknown tag/field, default insertion, schema mismatch, decode/re-encode mismatch |

Instrumentation for these vectors must make decoder invocation observable: every
outer-envelope rejection asserts zero body-decoder calls. A selected decoder
receives only opaque canonical bytes plus the resolved entry, never a caller
binding or registry mutation handle.

The protected-reader prerequisite has two stages: outer parsing/history/native
digest verification, then selected body validation/materialization/reencoding.
Instrument the real delegates separately, with wrappers that forward to the
original functions. Malformed outer syntax or exhausted outer limits must make
zero history, body-validator and materializer calls. Binding/status/digest
rejections make one history call and zero body calls. A valid composed read
makes one call to each stage. Patch the legacy body-first `decode_artifact`
with a failing sentinel on the positive path to prove it is not a fallback.

Use an independently constructed literal profile-3 outer map and literal body
bytes with independently calculated SHA-256/LP digests, never a positive vector
generated through the reader or legacy serializer. Preserve/reencode the body
byte-identically. Test exact byte/node/depth limits and one unit below each;
each of the six syntactically valid binding substitutions; coherent envelope
digests around an invalid body; and a narrowly induced reencoding mismatch.

Reader status proof is the complete three-status by three-read-route matrix:
active permits all routes, replay_only permits internal replay and retained
verification, retired permits only retained verification. Writer permission is
owned by later activation/admission composition, not this reader prerequisite.
The materialized result explicitly remains unauthenticated pending registered
integrity and native-authority verification. These tests cannot establish
signatures, persistence authority, service composition or registry publication.

## Independently authored compiler inputs

The independent compiler may reuse only the normative literal grammar bytes,
SIA length-prefix/SHA-256 definition, and the explicit profile-3 declaration
source package. It must independently implement strict UTF-8 source intake,
source JSON restrictions, encoded JSON-string key ordering, role grammar,
closure traversal, and LP hashing.

It must not reuse `ingestion_contracts.py` codec/registry functions, runtime
models, reflection, generated registry output, fixture-v2 inventory, existing
profile-2 bindings/digests, test fixtures that embed expected profile-3 output,
or decoder callbacks. The runtime implementation may consume the compiler's
frozen source package and independently authored expected vectors, but cannot
make its own output a compiler input.

## Feasibility and limits

Raw source role syntax is finite and statically checkable: every role has an
exact object shape, all identifiers/digests have lexical rules, and all cross-
role references are finite graph edges. No runtime reflection is needed to
validate or hash it. This matrix does not itself select the source package,
publish a profile, approve a decoder implementation, implement the registry,
or certify observation-ledger activation.

## Historical Registry And Decoder-Source Matrix

| Family | Required positive proof | Required negative proof |
| --- | --- | --- |
| Entry status | `active` emits and decodes, `replay_only` decodes only an embedded retained binding for internal replay, and `retired` verifies only retained bytes naming its exact entry | writer selects non-active entry; public caller selects replay-only/retired; status update of a retained entry; body/default/current-profile fallback all reject |
| Protected history | History resolves one byte-identical entry by complete embedded binding and its original decoder | same coordinate with changed status, source snapshot, decoder, schema closure, or binding; duplicate coordinate; absent historical entry; conflicting registry history all reject |
| Original bytes | Retained active, replay-only, and retired artifacts decode then re-encode byte-identically with their original named decoder | replacement decoder, upcast, default insertion, normalized body bytes, or current entry substituted for embedded binding rejects |
| Decoder source manifest | Whole named UTF-8 files below the canonical source-package root produce the declared ordered LP snapshot with canonical unsigned-decimal file count for each declared decoder ID | region selector, reflection/import-derived file, path escape/absolute path/backslash/Unicode escape/symlink, duplicate path/ID, omitted native validator/encoder dependency, changed file digest/order/bytes, or generated constants as an eligible row rejects |
| Publication/deployment pin | External publication manifest binds source roles, decoder-source-manifest digest, ordered decoder snapshots, and final registry without a registry self-cycle | manifest field/order/domain change, registry-to-manifest edge, missing deployment pin, or pin mismatch rejects before registry publication |

The independent compiler receives the raw declaration package and the same
whole-file decoder-source manifest, but no runtime registry object, generated
registry constants, callbacks, or reflection. Its source snapshot algorithm is
the LP construction in the governing observation contract. A test must mutate
one complete named source file and show that only the affected decoder snapshot,
entry binding, and publication/deployment verification fail; it must not accept
a regenerated current decoder for historical bytes.

## Native Group Publication Receipt Matrix

| Family | Required positive proof | Required negative proof |
| --- | --- | --- |
| Accepted group CAS | One public `ProviderMemoryService.sync_event` accepted group writes graph delta/event batch, both complete projection publications, exact replay bindings, immutable aggregate/checkpoint evidence, receipt, and mutable current pointers in one JSONL-backed CAS | remove any receipt/evidence member, use a generic member binding, or split a member into a later batch; commit/replay rejects with no partial group closure |
| Lost acknowledgement | Commit A, advance mutable aggregate/checkpoint with B, then reload A through its primary | reload must validate A's immutable receipt/evidence bytes and never compare A to B's mutable current aggregate/checkpoint |
| Receipt closure | Receipt's typed full `SemanticGraphDelta`/`SemanticMemoryEventBatch`, temporal/trust publications, stable publication identity, deterministic target IDs, and exact aggregate/checkpoint typed evidence match result/reload | swapped certificate/generation/pointer/binding, substituted evidence ID/digest, changed aggregate/checkpoint body, missing group delta, cyclic ID/digest construction, or result without activated receipt rejects |
| Legacy dispatch | Existing legacy group primary/result bytes reload without a receipt and never gain projection authority | legacy byte accepted as activated publication, synthesized receipt, or absent receipt on an activated accepted group rejects |

These are entrypoint-bound integration proofs. Helper-only preparation tests do
not establish native publication or historical reload behavior.

## Native Candidate Encoding Prerequisite

The candidate path begins with a native model and one explicitly supplied
verified publication/entry, emits from source-owned fields through the bounded
writer, then performs actual source-body validation and selected native
materialization with byte-identical roundtrip. Its result remains unauthenticated.
It neither chooses a writer entry nor grants persistence permission.

| Behavior | Defect detected | Proof level and failure signal |
| --- | --- | --- |
| Real ordinary and nested native candidate emits the same canonical bytes as the reader's valid body | Candidate path invents another representation or bypasses finite native selection | Feature-local unit using real declarations and native model; exact body equality and selected class |
| Invalid native field, missing required field or wrong selected entry rejects | Defaults, permissive dumping or wrong schema hides invalid candidate input | Focused negative unit; typed codec error before candidate return |
| Substituted publication/source snapshot rejects | Candidate uses ambient registry or unverified decoder | Focused identity mutation; existing publication join error |
| Exact byte/node/depth caps pass and one lower fails | Emission bypasses protected resource bounds | Small deterministic boundary fixture; exact output or bounded failure |
| Existing reader/native reencoder behavior is retained | Candidate API changes historical or protected read semantics | Combined codec/reader regression at source freeze |

These proofs are construction evidence. Registered root integrity and native
authority checks, activation, transactional storage and public reads have their
own later acceptance obligations.
