# Authenticated Observation Query Validation Matrix

Status: preimplementation proof requirements, not executed evidence.
Parent: milestones/05-authenticated-observer-comparator.plan.md.
Governing contract: SIA GraphObservationResponse, cohort resolution and pagination
(sections around 31785-31980). The native group persistence prerequisite remains
under implementation; tests cannot substitute fixture-selected membership.

| Boundary | Required observable behavior | Defect detected / proof level |
| --- | --- | --- |
| Authorize before lookup | Context, narrowing scope, seed IDs, purpose and current policy enter the real authorizer before any seed/index/storage access; denial/outage performs zero reads and emits only failure/correlation | Public owner with instrumented read port; prevents existence disclosure |
| Context vs request | Forged or broader scope cannot authorize; request includes no caller key, authorization flag, expected graph IDs or digest | Strict request negatives and real authorizer scope subset tests |
| Cohort source membership | Exactly one accepted source and terminal source delta with complete operations/group results; missing, duplicate, nonterminal or out-of-scope seed fails | Real persisted source/group reload with adversarial missing/substituted joins |
| Cohort operation membership | Exactly one introduction/outcome pair, close all co-committed operations/groups/sources; caller cannot prune closure | Multi-operation persisted group, source-only terminal, zero-effect operation and partially committed source |
| Graph and boundary closure | Join exact graph delta to group result and base-record digests; follow only bound reference-ledger edges; exclude unrelated records | Actual materialized records, referenced pre-existing entity and unrelated entity; corrupt delta/base/ledger independently |
| Observed projection | Closed payload variants retain production IDs, source spans, temporal and provenance coordinates; no text or labels used to reconstruct membership | Each supported record kind, unknown kind, mismatched outer/payload kind/key/digest |
| Total-stream paging | One sorted stream by kind/key; inclusive policy size bounds, half-open positions, exact concatenation, empty final page only for empty stream | Sizes at min/max and outside, cross-kind boundary, more than two pages, no gap/duplicate/overlap |
| Cursor authenticity | Canonical signed cursor binds all declared context, authorization, cohort, snapshot, position, preceding triple, policy and time fields | Trusted byte-substitution matrix; no caller offset or unsigned fallback |
| Reauthorization | Every page rechecks current policy and caller; revoke/expire/change policy between pages produces the exact non-disclosing failure | Real paged public path with policy transition, cross-principal cursor and outage |
| Snapshot stability | Cursor age, graph/observation revision or page-policy change cannot silently rebuild a new stream | Concurrent commit between pages and expired snapshot; exact stale_cursor response |
| Failure taxonomy and disclosure | Prelookup denial/outage/out-of-range size = denied; malformed/altered/mismatched cursor = invalid_cursor; expired snapshot or changed revisions/page policy = stale_cursor; current authorization expiry/revocation = revoked_access | Assert exactly kind, reason, fresh request_correlation_token; no page/cohort/record/digest/replacement cursor/seed signal; zero reads at every required prelookup denial |
| View semantics | Current selects projections at valid/system time; historical retains visible assertion/transition history; lineage preserves predecessors | Real graph lifecycle records; no generic view-independent dump |
| Attestation purpose and closure | Authorizer receives ingestion_time_attestation; include exactly reachable source-retention and committed-group attestations in canonical kind/source/fence/group-or-empty/attestation-ID order; never signs or grants acceptance | Exclude noncommitting/unrelated/foreign-scope attestations; exercise the same cursor/page-chain/policy transition and per-page reauthorization families as graph observation |
| Packaging/independence | Production owner imports no acceptance/fixture/oracle data; comparator authenticates complete page chain before structural matching | Import/static ownership check plus altered page-chain comparison failures |

Tests use synthetic protected authorization and cursor keys only at documented
host boundaries. They must retain real store membership, record/delta codecs and
signature verification. An index or fake oracle never supplies cohort authority.
Run expensive persistence/restart combinations in the appropriate acceptance tier;
keep parser/closed-shape/cursor negatives isolated. Independent test review must
confirm the exact implementation matrix and placement before query coding.

Independent test consultation accepted the matrix after the two explicit rows
above were added. This authorizes bounded construction, not implementation approval.
Each runtime/persistence/authorization/cohort/page family must have a real-store,
real-codec behavioral test through every future binding-ledger trigger. Keep
restart/tamper/page-transition cases in persistent integration or acceptance;
independent comparator page-chain and import-boundary checks belong in acceptance.
