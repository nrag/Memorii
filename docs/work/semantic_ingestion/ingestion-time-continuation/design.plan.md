# Ingestion-Time Continuation Contract

Work type: design. Status: complete (bounded amendment). Coordinator and sole writer: root.
Created:2026-09-08. Baseline:d17466d5, clean at campaign start.
Parent: ../observation-ledger/implementation.plan.md.
Related: ../observation-ledger/retrieval-runtime-map.md; consolidated closure-plan.

## Objective And Completion

Specify an ingestion-time cursor whose coordinates match its existing request
and two attestation variants. Preserve graph cursor bytes, authorization before
lookup, reauthorization per page, detached-snapshot consistency and replay
fences. An approved amendment, explicit registry/promotion chain, executable
boundary proof and independent spec/correctness/test reviews are required before
production changes. R17/R19 stay partial until real retrieval integration.

## Sources, Scope And Constraints

Use AGENTS.md precedence and semantic_ingestion_observation.md, its request,
snapshot/public contracts, registered cursor implementation and paging owner.
No new graph-view coordinates may be invented for ingestion-time requests.
Only continuation semantics change; scope membership and attestation truth remain
governed by existing design. Real signing keys/production issuance are excluded.

## Ownership And Identity

Root owns this directory and later the canonical amendment. A read-only mapper
may identify exact registry/generator/CI consumers. Every new persisted schema,
purpose and signature domain is behavioral and explicitly inventoried in the
proposal; none derives from milestone or evidence coordinates. Promotion affects
the canonical observation design, typed registered schema declarations, source
inventory/decoder manifest, publication/vectors and relevant gates. No promotion
before approval, and no graph wire-format mutation.

## Verification And Risks

Prove both attestation variants, exact cursor-free request binding, ordered
predecessor digest, scope/policy/context substitution, stale write revision,
expiry/revocation, wrong purpose/key, unknown kind/field, malformed encoding and
resource ceilings. Retain accepted first/final pages and byte-identical graph
cursor compatibility. Public runtime binding must name ProviderMemoryService,
trusted factory configuration, detached cohort owner, registered cursor codec,
and complete typed page result; an uncalled helper is not implementation.
Root owns focused commands and records interpreter/result/hash. Final review
uses a frozen packet; local feasibility is not runtime or CI certification.

## Current State And Limits

Confirmed gap: existing graph cursor requires graph kind/view/valid_at/system_as_of;
ingestion-time request has none and attestation stream uses a different kind.
Choice to evaluate: distinct registered cursor versus versioning a shared union.
Budget: one coherent proposal and one consolidated correction. No open external
decision is currently known. No code or canonical contract changed yet.

## Next Action

Implement the approved amendment in the linked observation-ledger runtime
packet; no further design action is pending under this bounded operation.

## Evidence And Delegation

2026-09-08: root authored proposal/model/proof; selected separate registered
cursor with complete typed request and existing attestation predecessor triple.
Spark continuation_binding_map was read-only; root corrected unsupported names
and historical witness inventory by direct inspection. Proposal names exact
production binding targets and source/decoder/vector/CI consequences. Existing
public observer bindings are absent and remain implementation obligations.

Root ran PYTHONPATH=memorii .venv/bin/python -W error -m pytest
docs/work/semantic_ingestion/ingestion-time-continuation/test_cursor_feasibility.py
-p no:cacheprovider -q:20 passed8.20s. Initial run19 passed1 failed due deprecated
instance model_fields access in the test; corrected to class access, no warning
suppression. Model-only Pyright:0 errors/warnings; directory Ruff passed.
The proof covers strict proposed shape and retained-state comparisons using
real request/attestation types. It does not prove new registered bytes,
cryptography, runtime auth or production retrieval; these remain explicit
implementation gates. Root freezes this design and governing source hashes
before independent review. No writer remains active on this directory.

## Consolidated Review Correction

Spec finding confirmed: explicit endpoint supersession and canonical failure
dispatch were missing. Proposal now names the SIA paragraphs and distinguishes
revoked_access, invalid_cursor, stale_cursor and denied with precedence. The
correctness resource finding is confirmed as Not applicable/changes_required
design conformance (there is no deployed new endpoint yet); one host-protected
shared tenant/global byte/count budget covers graph and ingestion-time retention,
including reservations during construction. The test audit's duplicate-key
coverage gap is confirmed and resolved. No production P1/P2 claim is inferred.

Corrected proof:32 passed5.42s, directory Ruff passed, model Pyright0 errors and
warnings. New checks cover endpoint/failure dispatch, duplicate order keys,
tenant/global bytes/counts and concurrent reservation. Actual registered
encoding, full retention lifecycle and public endpoint proof remain explicitly
required implementation gates. Final bounded design delta review is next.
The test-audit role was performed read-only by the available Terra agent
observation_projector because a new test_reviewer agent could not be created
under the agent limit; no projector or production edits were delegated.
