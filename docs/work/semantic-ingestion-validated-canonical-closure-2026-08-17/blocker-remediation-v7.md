# Blocker Remediation V7

This normative delta closes the remaining `VCC-DREV-008B` composition-chain
gap without changing production code or repository tests.

`HermesMemoryProvider.__init__` owns exactly three accepted `_service` sources:
the typed injected `service` parameter, `build_filesystem_provider`, and
`build_provider_memory_service_from_env`. Both factory branches carry the exact
frozen `verified_production_host_authority` expression; the filesystem branch
also carries the exact `storage_root` expression. No other assignment leaf and
no later `_service` reassignment is accepted.

Composition roots use root-owned anchors rather than hook-method labels. Each
root has an independently frozen path from its mapped owner through a call or
constructor branch, any explicit instance/field bridge, a declared trigger,
and an affected connected requirement row. Hermes paths connect each of the
three constructor branches through the proven `_service` field to all six
public hooks.

The fixed-oracle attack family preserves every valid name and callsite while
substituting constructor authority, the receiver assignment value, its type
annotation, or a later reassignment. It also swaps root anchors, detaches
bridges and rows, removes trigger families, substitutes hook authority, and
injects direct, aliased, or dynamic durable dispatch. Every attack must fail a
named semantic predicate.
