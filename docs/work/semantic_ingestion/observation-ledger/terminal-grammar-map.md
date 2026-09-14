# Source Terminal Grammar Boundary

Coordinator read-only reconstruction; proposed changes remain unapproved.

Current `contracts.py:11716` BootstrapGraphTerminalPublicationIntentV3 seals
member_intents and includes terminal_member_schema_version 1/2. Its locator is
derived from intent_digest. Source observation is currently the tenth kind at
ordinal nine; lineage and group result may repeat. `contracts.py:11966`
BootstrapGraphTerminalPublicationRequestV3 includes the entire source delta,
handoff/intent, predecessor generation and exact delivery/fence/lease/writer.
`contracts.py:11867` reload retains that delta and matching grammar version.

`bootstrap_graph_terminal_preparation.py:450-522` derives the source delta before
building member intents. `bootstrap_graph_artifact_assembler.py:1331-1345` requires
that member's construction digest to equal the prepared delta digest. Store
`atomic_store.py:14005` materializes each member and requires that same equality.
Therefore merely assigning different revisions in the store invalidates the
sealed request/member contract. New grammar needs an explicit intent/receipt
split; treating the old delta as a mutable proposal is not compatible.

Under the draft selected split, the first nine semantic intent kinds retain
current semantics. A new source-observation-intent kind at ordinal nine binds a
typed revision-free source outcome plus frozen schema authority. Store receipt
member kind remains the canonical source-finalization delta, with its native
codec; its construction proof is the typed semantic intent plus assigned ledger
entry, not equality with a preassigned delta digest. Validation must explicitly
map the one intent kind to the one receipt kind. Unknown/mixed source-intent and
source-delta grammar combinations reject; old V1/V2 serializers remain literal.

Current identity binds actual member_manifest_digest separately from
atomic_write_digest=request.publication_request_digest. Preserve that distinction:
request identity remains stable across head-only retries, while manifest and
ledger entry reflect successful store assignment. Current terminal conditional
write (`atomic_store.py:10960`) applies absence conditions to every non-control
record. A mutable shared head must instead have one explicit expected-digest
precondition; never accidentally apply an absence precondition to an existing
head. Entries and immutable manifests still require absence. All authority and
lease checks repeat before the retry batch.

The current catch converts conflict without locator into generic PreplanningStoreError.
A new head-only retry must classify the failed head against unchanged control,
writer/fence/lease and graph coordinates, re-read under the same linearizer and
retry within a protected finite budget. Other stale authority remains an error.
Durable locator found after any conflict takes exact reload first. Reload checks
entry reachability through the current head, not equality with the latest head,
so later unrelated source appends do not invalidate a committed result.

Remaining design work is explicit: closed intent/receipt and activation schema,
checkpoint lifecycle binding, generated authority-chain inventory, full boundary
verification matrix and independent readiness review. The feasibility model is
not the real MemoryPlane conditional batch or public host retry path.
