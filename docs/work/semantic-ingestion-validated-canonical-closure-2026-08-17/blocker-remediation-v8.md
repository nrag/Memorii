# Blocker Remediation V8

This normative delta closes the `VCC-DREV-008B` source grammar as one exact,
typed AST contract. It changes no production code or repository tests.

The independent oracle freezes the normalized AST of
`HermesMemoryProvider.__init__`, the exact injected-service annotation, the two
branch predicates plus final `else`, and the normalized return AST of
`build_filesystem_provider`. The validator separately rejects any direct,
annotated, augmented, named, deleted, subscripted, or reflective `_service`
write outside the frozen constructor state machine.

The filesystem instance bridge is no longer a free-form label. Every filesystem
root path names a frozen chained-call bridge whose return receiver is
`FilesystemStorageBundle.from_root(...)`, whose method is
`build_provider_memory_service(...)`, and whose authority expressions are
exact.

R08 uses a frozen non-durable call allowlist and exact call multiset for
`CanonicalEvidenceArena`. Added, removed, substituted, aliased, reflected, or
dispatch-table calls fail even when their terminal name is not statically
recognizable as durable.

The attack matrix runs all prior attacks through this stricter validator and
adds widened/container annotations, guard replacement, `setattr`,
`object.__setattr__`, `__dict__` writes, detached filesystem return dataflow,
and dispatch-table persistence. Oracle and production inputs stay fixed.
