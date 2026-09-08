# Target Identity Verification Contract

Status: design evidence, not implementation or release certification.
Scope: the missing authority for the three fixed observation activation
fingerprints. Parent requirements remain open until production integration.

## Requirements And Evidence

| Planning ID | Source / invariant | Required behavioral proof |
| --- | --- | --- |
| T01 | Observation design: fixed activation fingerprints | Exact domain-separated byte recipes; independent literal preimages agree; no label or graph-schema substitution |
| T02 | Owner decision: protected installed target | Complete package/environment identity; copied source and import shadow cannot stand in for installed execution |
| T03 | Registry design: complete original publication | Every active entry and source role participates; omissions, extra roles, mixed publications and changed schema/codec fail |
| T04 | Owner decision: signing readiness | Exact unsigned bytes can be prepared, signed and verified with isolated Ed25519 keys; protected wrong key/pin/signature rejects; real signatures deferred |
| T05 | Observation design: verify before drain | Canonical protected runtime supplies verified target to writer/store; invalid authority leaves the complete store snapshot unchanged |
| T06 | Observation design: atomic activation | Complete inventory CAS, successor admission/manifest and genesis agree with verified target; lost ACK and restart identify the same complete result |
| T07 | Compatibility / source precedence | Legacy nested admission and terminal bytes remain exact, graph schema separate, no automatic activation or downgrade |
| T08 | AGENTS authority and identity rules | Closed schemas, explicit owners/limits, finite installed payload and dependency selection, reproducible gate inputs, requirement IDs only in traceability |

## Attack Families

| Family | Siblings / boundary cases | Expected result |
| --- | --- | --- |
| Raw control grammar | Missing/extra/duplicate keys; invalid UTF-8; alternate whitespace; numeric instead of string version; trailing bytes; exact and over byte/node/depth/row limits | Reject before authority or mutation |
| Package selection | Copied root, PYTHONPATH shadow, editable/zip install, duplicate metadata, omitted/extra file, symlink, traversal, changed RECORD, dependency version/payload mutation | No verified current target |
| Loaded execution | Stale timestamp pyc; preloaded old module; package mutation between reads and after startup | Supported startup policy prevents stale load; detected changes invalidate target |
| Fingerprint grammar | Reordered/duplicated/omitted rows; ambiguous concatenation; integer version representation; domain substitution; label hash; graph ID; one-decoder substitution | Independent exact-byte oracle rejects or changes the specified identity |
| Cryptographic authority | Wrong key/profile/digest/domain, truncated signature, altered unsigned bytes, unconfigured target, request-injected target | Reject; no drain |
| Historical identity | Current/historical publication mix; absent retained target; duplicate triple with inconsistent identity; renewal signature | Exact retained identity only; signature renewal semantics explicit |
| Transaction | Held lease, new operation during drain, root revision conflict, exhaustion, partial trio, lost ACK, restart, stale predecessor, conflicting target | Preserve documented drain/CAS/recovery state machine |
| Compatibility | Registry configuration only; legacy positive load; absent activation field inside nested models; old writer mutation after activation | No implicit cutover; exact old bytes; enforce successor fence |

## Feasibility Evidence

`feasibility.json` records a read-only inventory of the previously built wheel:
1,771 files and 11,124,966 uncompressed bytes. Its 1,257 registry JSON files alone
exceed the first draft's 512-row limit. The wheel RECORD has a deliberately
unhashed self-row, so hashing RECORD cannot be treated as a recursive complete
payload verification algorithm. This wheel is historical construction evidence,
not the final activation candidate or a signed release.

A fresh temporary Python module was compiled with VALUE=1, then changed on disk
to VALUE=2 while preserving source size and modification time. A separate Python
process executed VALUE=1. This discriminates package-byte evidence from executed
source and requires an explicit supported startup/cache policy. Repeating with
a fresh private `-X pycache_prefix` executes VALUE=2, providing a positive
control for the proposed cache isolation. Reproduce with
`.venv/bin/python docs/work/semantic_ingestion/activation-target-identity/probe_package.py <wheel>`.
It does not
justify a claim to attest arbitrary hostile in-process Python modifications.

`install-feasibility.json` records a clean temporary installation of the same
wheel using `pip --no-deps --no-compile --no-index --target`: 1,774 RECORD rows,
no bytecode files, and only RECORD itself without a per-row hash. The three
installer-added rows demonstrate why the installed RECORD pin is deployment
specific. This is a single-wheel feasibility check, not verification of a full
production dependency environment.

## Environment And Evidence Maturity

Current local probe: Python 3.12.14 on macOS; governing package supports Python
3.11+, and required PR package/static/unit gates use Python 3.11. Deterministic
implementation evidence must cover the minimum supported version and installed
wheel path. Provider live evaluation, external acceptance witnesses, deployed
filesystem immutability and real signing remain separate operational evidence.
The matrix specifies future implementation tests; none is reported as already
passing merely because it appears here.

## Planned Owners And Authority Chain

Release preparation derives an external control artifact from the final package,
environment and verified registry. Protected host configuration pins its bytes
and verification keys. The built-in semantic runtime composes the verifier,
writer admission and atomic store. The explicit activation entrypoint verifies
the target before drain and the final full-inventory CAS preserves its three
fingerprints. Historical verification uses retained protected inputs.

The exact new symbols and artifact grammar are frozen in proposal.md. Existing
owners are `memory_evolution/atomic_store.py`, `writer_admission.py`, registry
publication/history, `semantic_ingestion/capability.py`, and `provider/service.py`.
No production reachability is claimed for this design. Implementation must update
the parent `production_entrypoint_bindings.json` with actual callsites and an
independent mapper preflight before its milestone review.

Changes to selected registry decoder sources require regeneration of the source
manifest, publication, 179-entry independent output, frozen vectors and package
evidence; cardinalities must be measured again. New tests require shard/timing
inventory reconciliation. Existing required PR gates remain authoritative; the
design adds no invented CI enforcement or signed release store.

### Target-Specific Test-To-Gate Map

These are required additions to `.github/workflows/pr-gates.yml` and its existing
test selection during implementation, not claims that the current jobs enforce
the new contract. Each row names the removal signal so a helper-only substitute
cannot satisfy its evidence.

| Requirements / level | Real trigger and authority | Durable assertion / removal signal | Required job |
| --- | --- | --- | --- |
| T01,T03 / independent recipe | Frozen raw inputs -> separate Python and JavaScript LP implementations, no production imports | Exact preimage hex and P/E/three fingerprints; removal of any bound field changes the expected mutation result | `unit-test-shards`, via target recipe golden-vector tests; preserve independent outputs as literal fixtures |
| T02,T04,T05 / installed integration | Deployment preparation verifies/installs candidate wheels with no-compile policy -> fresh read-only bootstrap -> explicit `ProviderMemoryService.activate_observation_ledger()` with host target/key/history | Exact complete write snapshot unchanged on missing target, wrong key, or disabled forwarding; valid target produces the joined successor trio | `package-smoke`, extended with a clean isolated no-compile installation and bootstrap/provider subprocess |
| T02,T08 / startup subprocess | Actual bootstrap with shadow/preloaded package, stale package/private-prefix bytecode, editable/zip install, RECORD escape, or inter-read file mutation | Reject before first Memorii import; import sentinel absent and store snapshot unchanged; pinned ordinary dependency entrypoint scripts pass | `package-smoke` plus bounded subprocess cases selected by `unit-test-shards` |
| T01,T02,T04,T08 / typed and real-file boundary | Core parser/verifier with isolated keys and actual zero-byte files; exact/over bytes, nodes, depth, row, per-file and total-file limits | Accepted empty file participates in P; every over-limit input rejects before drain; wrong profile/key cross-pair and ASCII `00` delimiter reject | `unit-test-shards`, new target-verifier test module |
| T05,T06,T07 / JSONL integration | Explicit provider activation -> actual writer drain -> full store CAS -> fresh process reopen, using retained host records | Exact retention/re-sign conflict rejection; held lease completion; root CAS conflict/exhaustion has no partial trio; post-durable lost ACK returns identical successor; legacy reload exact; old mutation paths fenced | `unit-test-shards`, new activation integration module; existing `semantic-terminal-persistence` remains required regression coverage |
| T04,T08 / release subprocess | Thin release prepare -> existing offline signer -> assemble/verify with configured public key | Independent preimage equality; wrong/missing signatures cannot produce verified target; no production key needed | `package-smoke` and `unit-test-shards` release-command cases |
| T08 / governance | Field-aware identity checker plus target-field mutations, shard/timing inventory and installed-wheel inclusion | Planning IDs rejected on new durable/control identity fields; missing test selection or packaged owner fails | `static-analysis`, `unit-timing-inventory`, `unit-tests`, `package-smoke` |

Preparation and runtime bootstrap require separate subprocess assertions: preparation verifies wheel hashes before installation; runtime bootstrap with absent/mismatched installed files must reject with an installer-invocation sentinel untouched. Runtime bootstrap never installs.

The final integration proof must remove the production forwarding call and show
the positive provider activation test fails. It must not treat an evidence-only
fallback as a successful negative assertion. Configuration alone is tested to
leave admission/ledger unchanged.

### Independent Recipe Feasibility

The clean-room Python oracle `identity_oracle.py` was written by a separate
delegate from this contract and hand-authored `identity-input.json` only. Root
wrote `identity_reference.mjs` without reading that oracle. Neither imports
target code, production parsers, registry compilers, codecs, fixtures, or vector
generators. They share only the normative recipe, raw synthetic input and
standard SHA-256 primitive. The fixture includes two distributions, an empty
package file, multiple roots, and lexical schema versions 1, 10, 2.

`identity-expected.json` freezes every exact preimage as literal hex and its hash
after independent agreement. `verify_identity_recipes.py` compares both against
those literals and mutates every individual input field, requiring the precise
changed/unchanged identity set; `identity-feasibility.json` records the result.
This proves bounded recipe feasibility, not independently validated package,
signature, or publication acceptance. In a coherent release, coupled changes
(for example decoder source and package payload) must update all affected inputs;
isolated recipe mutations are not valid release artifacts.

## Identity Ledger

`T01` through `T08` and parent R/SIA coordinates are planning metadata only.
ObservationActivationTargetManifest and its explicit version are behavioral
protocol identities. Writer/schema/codec digests are derived coordinates, never
milestone labels. Proposal, verification, feasibility and review artifacts are
work evidence outside runtime packages. Implementation must extend the existing
field-aware identity checker and mutation corpus for every new persisted/control
identity field, accepting genuine protocol versions and rejecting planning IDs.
