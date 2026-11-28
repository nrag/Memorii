# Managed replacement-host recovery

State partial. Requirement REL-02.

Use the [authority table](../validation.md#authority-mutations-and-durable-contracts)
and existing signed backup, restore and generation owners. Persist independent
pending and sealed authority, verify the archive history prefix and stage the
new root inert. Prove normal and older readers refuse before the independent
seal. Current suppression and holds survive. Require fresh issued authority.

Run older restore, backup fence, governance, installed loss-of-host,
interruptions, unavailable custody and rollback proof. Record exact caller
and evidence families before freezing the milestone.

## Local implementation evidence

Typed independent custody now verifies signed pending/complete authority,
checks exact predecessor and participant effects and refuses stale or
unsealed input. The control bundle format binds signed member inventory to
the anchor and reuses encrypted snapshot custody. This lower-level mechanism
supports a tested replacement from an older archive after moving the old root
away. The integration proof independently holds the latest signed state,
interrupts at pending publication, retries the exact transition, rejects
opening the inert root, retains suppressions and activates only after seal.
The focused recovery suite passed 18 tests. Managed backup manifests bind
the selected spool identity and high-water in the same snapshot barrier.

The maintenance composition now exports current signed control, finalized
tuple, suppression and terminal read-grant denial state under independent
custody. An unavailable custodian prevents the prepared read-grant
transition. The integration test interrupts after the epoch write and after
the audit write, then retries the exact operation and verifies one effect in
the sealed bundle. A replacement after loss of the live root preserves
actual postarchive suppression and grant denial. Reusable bearer material
and owner capability are absent from the bundle. The 56 focused recovery,
operator and backup tests passed.

Installed replacement recovery still needs the complete authoritative live
deny-state writers and codecs, independently configured custody and isolation,
historical signer rotation, a bounded streaming journal reader, and process
cuts through each public opener and rollback path. The current offline
reader fails closed above its 16 MiB metadata bound. The installed
operator does not expose replacement bootstrap from this partial state.
