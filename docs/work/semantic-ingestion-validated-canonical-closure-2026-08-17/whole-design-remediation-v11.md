# Whole-Design Contract Remediation V11

This design-only remediation closes full-review findings `DREV-001` and
`DREV-002`. It changes no production code or repository tests.

The machine-readable operation contract freezes one lifecycle owner, complete
states and transitions, exact capacity limits, sealed-only capability exposure,
scope identity, metric allowlisting, privacy exclusions, and sink-failure
policy. The full 16 MiB envelope is reserved before staging. Staged evidence is
invisible until seal; any refusal discards the whole closure and releases before
the full path begins. Sealed slice leases make close linearizable and release
the reservation exactly once after the final lease drains.

One terminal content-free snapshot is owned by `ProviderMemoryService` and its
repository-owned dispatcher. It excludes semantic content and scope identity;
sink unavailability cannot alter ingestion or durable outcomes.

The executable reference consumes the machine-readable contract and proves
disabled allocation absence, concurrent process reservations, exact and over-
limit behavior, sealed-only capability exposure, close/lease ordering,
exact-once release, forgery and stale-scope rejection, exact metric fields,
content exclusion, sink unavailability isolation, and unique terminal emission.
Its maturity is local reference evidence only.
