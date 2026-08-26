# Blocker Remediation V6

This normative delta closes `VCC-DREV-008B` as one production-ownership
family. It does not change production code or repository tests.

The accepted ingress grammar contains three service entry families:
`sync_event`, `_sync_composite_event`, and `apply_memory_write`. Their Hermes
surfaces are `sync_event`, `on_session_end`, `on_pre_compress`,
`on_delegation`, `sync_turn`, and `on_memory_write`. The production capture
harness remains explicitly excluded because it has no ordinary in-tree caller.

Trigger and composition-root identities are independently frozen as exact
`(id, path, qualified symbol)` mappings. Every mapping must resolve in the
frozen production AST, attach to one or more owner-qualified edges, and reach
an affected connected requirement row. Provider, filesystem, and Hermes
composition roots are bridged only to the trigger families their constructed
service exposes.

Authority-sensitive edges freeze exact AST expressions for authenticated host
ingress, verified production-host authority, arena identity, and arena nonce.
Field receivers require a concrete `self.<field>` assignment in the owning
constructor; textual class-name co-occurrence is insufficient. Dynamic import
or `getattr` dispatch to durable methods is outside the accepted ownership
grammar and fails closed.

The independent mutation family keeps the oracle and ledger immutable. It
attacks forged trigger/root mappings, removed composite and memory-write
triggers, detached root/row anchors, `None` authority, receiver rebinding, and
direct, aliased, or dynamic arena durable sinks. Each attack must fail a named
semantic predicate with source-hash enforcement disabled only for the isolated
shadow source under attack.
