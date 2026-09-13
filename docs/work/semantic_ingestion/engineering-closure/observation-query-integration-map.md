# Authenticated Observation Query Integration Map

Status: coordinator-reconciled readiness map, not implementation or approval.
The Spark exploration identified related owners but included speculative paths;
the coordinator stopped further exploration and retained only verified facts here.

## Current Entrypoints

No production `GraphObservationRequest`, `GraphObservationAuthorizer`, page policy,
cursor payload, cohort resolver or page endpoint exists. Governing schemas and
behavior are in SIA 31320-32030. Production caller count for that API is zero.

`ProviderMemoryService.read_identity_lineage` in `core/provider/service.py:846`
is a related, distinct graph-audit endpoint. Direct service callers and the Hermes
adapter can reach it; Hermes is not the only composition root. It resolves host
ingress and obtains a grant-derived scope before reading. It resolves/authorizes
again, checks tenant/principal/scope equality and scope expiry, then dispatches to
the scoped lineage reader. `core/provider/factory.py:88-126` wires that reader and
authorizer from explicit identity-lineage inputs. It does not compose graph
observation. No new observer may treat GRAPH_AUDIT as its request purpose.

`ProviderMemoryService.lookup_semantic_ingestion_outcome` is a separate
non-disclosing authenticated delivery outcome lookup. Its index response does
not establish graph-observation membership, completeness or paging authority.

## Reusable Authentication Mechanisms And Limits

`core/memory_evolution/identity_lineage.py:123-192` implements
`GrantBackedIdentityLineageAuditAuthorizer`. It looks up grants by authenticated
principal binding, validates tenant/principal, revocation and issue/expiry time,
intersects granted IDs with current ingress scope IDs, and narrows scoped requests.
Its revalidation requires the retained scope IDs to remain a subset of the grant.
These are reusable ownership patterns, not an observation authorization decision.

`AtomicStoreScopedIdentityLineageAuditReader` in the same file at line 249 checks
store tenant, scope mode/key and current grant before reading scoped event IDs
and replay state. It does not resolve ingestion cohorts or enforce observation
page policy/cursor fields.

`core/memory_evolution/ingestion_contracts.py` defines:

- `DeliveryPrincipalBinding` (line 368): principal subject, tenant, provider and
  stable digest; explicitly excludes session authority.
- `AuthenticatedIngressContext` (line 513): principal and current/required scopes,
  but no authenticated session ID.
- `AuthenticatedHostIngress` (line 648): opaque principal/session handles.

The observation context must therefore come from a trusted host context/resolver
port. Do not derive its authentication_session_id from repr/hash of an opaque
handle, delivery ID or request argument. Scope_constraint only narrows the
protected current scope; it cannot authenticate or grant access.

## Actual Storage Read Authorities

`SemanticIngestionAtomicStore` owns `graph_state_snapshot`,
`reference_integrity_snapshot`, canonical group reload, and exact source terminal
reload. `BootstrapGraphHostBundle.reload_terminal` calls
`reload_bootstrap_graph_terminal_by_recovery_v3` with normalization replay, fence
and required scope authority. Recovery validates the persisted terminal closure;
it is not a public seed/cohort API and its input contracts cannot be replaced by
caller-claimed seeds.

The approved source-finalization slice provides immutable source outcome/delta
closure at its pinned candidate. Group observations are still being integrated.
The future cohort resolver must join accepted source and terminal delta, exact
operation introduction/outcome pairs, group results, graph deltas and actual
base records, then follow the bound reference ledger for boundary records.
Provenance indexes may locate candidates but never certify membership.

## Required New Owners

Implementation still needs explicit, protected observation context/authorization,
page-policy and cursor-signing ports; canonical request/response/cursor models;
store-backed cohort resolution and typed record projection; stable snapshots;
paging with per-request reauthorization; and ordinary provider/factory dispatch.
These are missing implementation owners, not evidence of missing user policy
values. Configured production inputs may be absent and fail closed; tests supply
synthetic protected authority without replacing store or signature validation.

The server must bind each cursor/page to the exact context, authorization decision,
policy, cohort, graph/observation revision, view/time and stream position. A
separate attestation purpose is required. Schema bindings/CTV and independent
comparison are additional parent obligations, not implied by this map.
See `observation-query-validation-matrix.md` for required failure families.
