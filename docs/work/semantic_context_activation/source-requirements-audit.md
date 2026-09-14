# Independent Source Requirements Reconstruction

Coordinator reconstruction from user request, archived notes, governing spec and
pending deployment packet, before reading the canonical writer draft.
This is an input-coverage audit, not a claim that all research ideas are approved.

| Source obligation | Expected disposition in design | Evidence needed |
| --- | --- | --- |
| Improve storage organization | In scope: explicit domains/namespaces, authority versus indexes, directory/read ownership | Same canonical rows; scoped index reconstruction; no new unified memory domain |
| Improve retrieval | In scope: mandatory references plus optional knowledge search | Mandatory survives irrelevant query/top_k; semantic ambiguity cannot be replaced by lexical truth |
| Work through pending M5 | In scope: ordered acceptance slices, dependencies and external boundary | All eight inherited requirements preserved |
| Execution state is distinct from memory | Preserve existing execution/solver ownership | No transcript-derived authoritative state or automatic state transitions |
| State entry is a context boundary | Bounded host-triggered read API | Host explicitly supplies declared reference set; no false completeness of obligations |
| State exit is a checked contract | Separate execution-control design | This read API cannot enforce completion or prove validators passed |
| Durable resume without transcript replay | Use durable source references/current memory snapshot; identify wider existing resume subsystem | No claim that current separate graph stores form one atomic checkpoint |
| Solver only when needed | Preserve optionality of new context API | No solver creation on context retrieval; do not claim current runtime-step auto-solver changed |
| Semantic/episodic/user/raw/skill knowledge | Existing domains and candidate policy | Skills are not new core domain; raw evidence and reusable knowledge remain distinct |
| Deterministic mandatory activation | In scope for declared references | Denied/missing/stale/oversized required item cannot become ready context |
| Search-triggered retrieval | In scope | Scope, lifecycle, temporal, entity, provenance and budgets precede usable results |
| Knowledge learning | Existing ingestion/consolidation; consume validated results | Retrieval does not promote candidates |
| Learned checks/guards/recovery/routing | Separate control-policy design and authority decision | Never execute memory text as code, hook, validator or configuration |
| Candidate practice support/counterexamples/shadow/regression/promotion | Roadmap | No implicit automatic or global promotion |
| Lightweight complexity levels | Design principle | No mandatory DAG/solver for simple reads; no new competing status vocabulary |
| Evidence-backed completion receipts | Existing evidence retrieval only; completion enforcement deferred | Returned citations are evidence references, not completion receipts |
| Recovery, failures, rollback | In-scope read consistency and rebuild behavior; wider controller deferred | Reopen, corruption, stale authority and no mutation |
| Quality evaluation | Separate retrieval metrics and agent metrics | Recall/precision/ranking/latency distinct from completion/recovery/repeated failures |
| Ablations | Roadmap + bounded retrieval comparison | Same model/attempt/token conditions; no component-to-agent quality inference |

## Pending Deployment Requirement Audit

Source: `docs/design/semantic_ingestion_architecture.md:216-232` and
`docs/work/semantic_ingestion/milestones/m5-deployment-acceptance.plan.md`.

| Traceability value | Preserved acceptance |
| --- | --- |
| SIA-R03 | complete structure/coverage/evidence identity and independent verification |
| SIA-R08 | default verified deterministic local bootstrap, no remote fallback |
| SIA-R13 | trust lifecycle, purpose, active release, no acceptance authority in production |
| SIA-R14 | independently recomputed predeclared statistics across mandatory lanes |
| SIA-R15 | deterministic typed monitoring; atomic evidence-only on breach/staleness |
| SIA-R16 | exact dependency topology/profile, package/assets/no-network startup |
| SIA-R17 | authenticated direct structural observation, global bijection, zero-mutation outcomes, no retrieval oracle |
| SIA-R19 | real direct/factory/filesystem/Hermes composition and owner-stripping |

Policy/trust provisioning is not a local default. Bootstrap topology resolution
does not resolve the separately registered policy or traceability decisions.

## Reconciliation

The first frozen `spec_auditor` independently reconstructed all 19 source
obligations and eight inherited acceptance obligations and found no source
coverage omission. Its findings concern closed contracts and implementation
bindings, not missing research inputs. Those findings are recorded in
`reviews.md`. Final candidate review must confirm this still holds after
conformance corrections; no parent deployment completion is inferred.


Final reconciliation: the fresh specification review reconfirmed source coverage;
its targeted delta approved canonical SHA-256
`f43d2cca76a57776cc2223ec1e9d413cb0deb6e94a5981263b0b43deae04386e`.
All 19 source obligations and eight M5 acceptance obligations have explicit
in-scope, preserved, or deferred dispositions. No omitted source obligation or
unresolved required correction remains within this design's recorded scope.
