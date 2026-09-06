# Scenario V1 Runtime Closure Design Delta

- Work ID: semantic-ingestion-scenario-v1-runtime-closure-2026-08-09
- Work type: design
- Status: under-review
- Coordinator: Codex main thread
- Created: 2026-08-09
- Last updated: 2026-08-09
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/bootstrap-step12-route-2026-08-08/design.plan.md`; `docs/work/semantic_ingestion/milestones/m3-semantic-pipeline.plan.md`; `docs/work/semantic_ingestion/terminal-persistence-performance-2026-08-09/testing.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md`; `docs/design/semantic_ingestion/scenario_first_fixture_authority.md`; `docs/design/semantic_ingestion/traceability_golden_vectors/scenario-first-v1.json`; `memorii/memorii/core/memory_evolution/bootstrap_profile.py`; `memorii/memorii/core/semantic_ingestion/local_analyzer.py`; `memorii/memorii/core/semantic_ingestion/source_preparation.py`; `memorii/memorii/core/semantic_ingestion/capability.py`; `docs/design/semantic_ingestion/traceability_golden_vectors/run_scenario_ingress.py`
- Expected outputs: approved V1 corpus/analyzer/runner contract, implementation evidence matrix, and regenerated current authority only after implementation.

## Objective

Reconcile the normative four-case scenario authority with the corrected
unreleased V1 bootstrap runtime without introducing a second semantic path,
remote dependency, or test root into production. A production-shaped built-in
host capability must be the runner composition boundary; the scenario root is
test-only authority and never production authority.

## Completion Contract

Complete this design operation only when the design delta is independently
reviewed against the governing architecture and scenario authority; every
requirement below has an implementation owner and deterministic evidence; no
reviewer identifies a validated P1/P2 or required contract-conformance change;
and the M3 packet links this delta as the current prerequisite. This design
does not claim production code, regenerated authority, or live certification.

## Scope

Included:

- the exact V1 corpus values and closed multi-segment ambiguity rule;
- `ProductionLocalSemanticAnalyzer`'s V1 public predicate/result contract;
- runner composition through `BuiltInLocalHostSemanticIngestionCapability`;
- authority-chain and regeneration obligations.

Excluded:

- additional English grammar, temporal inference, model/tokenizer support,
  release-policy changes, production trust-root provisioning, persistence
  performance, and M4 conflict/replay behavior.

Explicitly deferred: signing/publishing a release and PR-gate performance;
those begin only after deterministic implementation evidence and remain owned
by their existing operations.

## Requirements And Owners

| Requirement | Observable requirement | Canonical implementation owner | Required proof |
| --- | --- | --- | --- |
| V1SC-R01 | Four literal inputs have exactly the owner, status, abstain, and ambiguity behavior declared in Section 3.23.0. | `BootstrapGrammarCorpus` and `BootstrapTextPreparationProducer` | corpus completeness plus byte/route/proof/span mutations |
| V1SC-R02 | Only the two exact owner segments form ambiguity; no value is chosen. | `ProductionLocalSemanticAnalyzer` and `SemanticIngestionPipeline` | ordering, duplicate-value, separator, source, and route/proof matrix |
| V1SC-R03 | Scenario ingress exercises ordinary provider composition with the built-in capability, never a direct extractor callback; opaque renderer IDs and their private map cannot leak scenario truth. | `run_scenario_ingress.py` and `BuiltInLocalHostSemanticIngestionCapability` | independent zero-based traversal/CTV/domain/output-spelling agreement plus private-map mutation matrix and no-direct-owner static test |
| V1SC-R04 | Changed V1 grammar bytes cannot be mixed with old anchor/release/scenario/CTV evidence. | bootstrap artifact generator and existing release/CTV tooling | complete regenerated artifact graph and pin/checker parity |
| V1SC-R05 | Production/default accepts only production-root material and the bounded scenario runner accepts only scenario-test-root material. | host trust-domain capability and composition roots | three-root production/scenario-test/unrelated acceptance and rejection matrix |

## Normative Contract

Section 3.23.0 is amended with the authoritative literal corpus and execution
rule. The only new supported normalized segment bytes are:

```text
Atlas owner is Alice.
Atlas owner is Bob.
Orion status is running.
No source-grounded assertion is available.
```

The last form is `abstain_form` with `extractor_abstained`; the first three are
`supported_form`.
Existing corpus cases that establish the closed reason/disposition inventory
remain required. The ambiguity scenario is an ordered pair of the first two
owner forms from one source, separated by one retained ASCII space. It has two
semantic segments and no synthetic whole-source corpus case.

The analyzer emits `owner` with a person-valued object and `status` with a
literal-valued object. It uses one candidate and one independent analysis for
each proven segment. It returns no candidate for the abstain form. It produces
the ambiguity result only when the two bound owner values differ and their
scope, source, direct attribution, and temporal evidence match the scenario
contract. This is a result classification; it never selects a winner or
commits a semantic fact for the ambiguous case.

## Authority And Failure Boundaries

The scenario root can build host-verified V1 material only in the separately
bounded `scenario_test` host trust-domain capability.
`BuiltInLocalHostSemanticIngestionCapability` remains a production owner: it
receives that material, externally held authorization, policy, and current
release verifier and builds the same writer/store/preparation/analyzer path as
provider, Hermes, and filesystem roots. Missing, mismatched, revoked, or
scenario-root-as-production authority remains evidence-only or rejected before
source preparation. No direct call may bypass provider ingress, atomic store,
or protected result access.

The runner has no expected-output input at runtime. It uses the scenario
authority's exact zero-based declaration traversal, declaration-ordered CTV
preimage, profile, domain bytes, digest truncation, and `scenario-event-` /
`tx:` output spellings. Only the renderer and comparator retain the
opaque-ID-to-turn map. It runs one public event for each
renderer observation, then reads the protected terminal/output evidence to
create an aggregate comparator input. Scenario truth remains only in
renderer/comparator process state. Its tool pins include runner, provider
composition, capability, bootstrap profile, source preparation, local analyzer,
and comparator source bytes.

Production/default composition receives only a non-forgeable host capability
for the `production` trust domain. The scenario runner receives only its
separately bounded `scenario_test` capability. A three-root proof with
production, scenario-test, and unrelated roots establishes both positive paths
and all cross-domain/unknown negatives before any runtime construction.

## Implementation And Regeneration Sequence

1. Implement the four literal corpus additions, exact multi-segment preparation
   mapping, and analyzer public-vocabulary behavior.
2. Replace the direct-extractor runner with built-in capability provider ingress
   and protected-result aggregation; add root-isolation tests.
3. Pass the closed deterministic matrix and freeze a candidate identity.
4. Regenerate V1 corpus/capability/profile/anchor/release inputs, scenario run,
   elaborated manifests/spools, CTV authority, and all exact pins together.
5. Conduct independent implementation/spec/correctness/test review before M3
   closure. Do not generate any signed production authority in this operation.

## Evidence Matrix

| Family | Must prove |
| --- | --- |
| Literal corpus | exact bytes accepted; one-byte/case-ID/language/route/proof change rejects |
| Owner/status | exact predicate/object kind/quote/span/timestamp/scope/source output |
| Abstain | `abstain_form`/`extractor_abstained`, no candidate, abstained terminal, no semantic delta |
| Ambiguity | two differing values, one source/context, no winner/effect; every sibling substitution rejects |
| Built-in host | provider, Hermes, filesystem use paired writer/store/current verifier; missing/mismatched authority is non-promoting |
| Trust domains | production/default accepts production only; scenario runner accepts scenario-test only; both reject the other and an unrelated root |
| Opaque ingress IDs | independent zero-based traversal and declaration-ordered CTV preimage/digest/output agreement; every field/order/profile/domain/spelling/reuse mutation rejects and private map never reaches host, public event, trace, or persistence |
| Replay | retry and filesystem reopen reproduce identical terminal/result artifacts |
| Authority regeneration | all V1 and scenario/CTV artifacts bind one fresh design identity; old/new mixing rejects |

## Alternatives Rejected

- Retiring the scenario contract: rejected because it is already normative and
  would remove the only owner/status/abstain/ambiguous conformance evidence.
- A test-only extractor callback: rejected because it bypasses the normal host
  composition and cannot prove provider integration.
- A generic English grammar: rejected because it broadens bootstrap semantics
  beyond the finite reviewed corpus.
- Treating two owner sentences as two independent unambiguous inputs: rejected
  because it silently loses the required ambiguity outcome.

## Identity And Coordinate Hygiene

`V1SC-R01` through `V1SC-R05` are planning traceability coordinates only. They
must not appear in production symbols, persisted payloads, corpus case IDs,
release bytes, runner output, or workflow selectors. The behavioral corpus IDs
in the architecture are the only new durable identities.

## Scoped Candidate Identity

The review candidate is
`scenario-v1-runtime-closure-candidate-identity.json` beside this WorkPlan. It
pins exactly this WorkPlan, the normative architecture, the scenario authority,
and the scenario input. It is deliberately scoped: it does not identify the
shared dirty tree, unrelated M3 remediation, production code, generated
authority, or any later implementation candidate. The architecture SHA-256 and
the WorkPlan SHA-256 are recorded in distinct named fields; neither substitutes
for the other.

## Current Evidence

- Normative architecture SHA-256:
  `786c9f22c33db76bb16518cfa6da57ae95084b126e36d6462d6cd122d75fa17e`.
- Scenario authority SHA-256:
  `cfe5e0742b7a2072527eeb9efc452f695146840e0cc93e3d15911d406324d5e5`.
- Scenario input SHA-256:
  `4cb5bfd804ac1d0639dc4e419b1a33f8ecea0666ffebc4c1407348d85f021dbe`.
- The independent scenario validator passed on the historical authoritative
  four-case bytes: `4` scenarios produced `match`, `match`, `abstain`, and
  `ambiguous`.
- The current bootstrap runtime cannot satisfy that contract: its corpus admits
  only `Atlas owner is Bob.`, its local analyzer has no `status` form, and the
  runner uses a retired direct `EnglishRuleMemoryExtractor` callback.
- The built-in host capability already provides the correct production-shaped
  composition boundary and has focused provider/Hermes/filesystem evidence;
  this delta specifies its scenario-test material mapping rather than a new
  runtime abstraction.
- `py_compile` and Ruff passed for the current runner source and `git diff
  --check` passed. The CTV checker is intentionally not rerun against this
  candidate: its expected design digest must change only in the later atomic
  regeneration step, alongside its authority bytes and workflow pins.

## Exact Next Action

Run the required independent delta review of this frozen design change. If it
is approved, create the linked implementation slice beginning with the exact
corpus/analyzer/preparation contract; do not regenerate authority artifacts or
modify M4 in the design operation.

## Implementation Evidence Boundary (2026-08-09)

The approved composition slice is now implemented through the ordinary
`BuiltInLocalHostSemanticIngestionCapability` and `ProviderMemoryService`; the
retired direct extractor path is absent from the scenario runner. The
scenario-only capability is explicitly sealed to `scenario_test`, emits opaque
public event IDs, and keeps renderer IDs in a private comparator map. A
writer-activation regression exposed during implementation is recorded in the
linked debugging WorkPlan
`docs/work/semantic_ingestion/scenario-writer-activation-regression-2026-08-09/debug.plan.md`.
Its focused proof is green, including the negative evidence-only sibling and
the temporary A/B elaboration parity run. This is implementation evidence only:
it does not regenerate, sign, or pin V1/CTV authority artifacts.
