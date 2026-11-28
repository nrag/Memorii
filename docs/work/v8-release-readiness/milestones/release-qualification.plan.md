# Exact release qualification

State specified. Requirement REL-06.

Freeze the reviewed implementation after the earlier milestones. Run the
current deterministic, host, installed-package, CodeQL and live component
gates. Measure both fresh default-v8 workload distributions on dedicated
native Linux and macOS SSD. Preserve separate staged-upgrade evidence.
Bind signed artifacts, dependency results, restore and rollback outcomes,
runner metadata and check status to the candidate and reconcile independent
whole-branch reviews.

The reference driver now has an explicit fresh-default v8 check and labels
fixture origin. The dedicated workflow requires that check for both profiles.
The repository runners inventory returned no registered runners with the
qualification label on 2026-11-27. The owner authorized a disposable
PhoenixNAP runner under a $10 total cap. Both
[fresh-v8 Linux workloads](../../reference-capacity-qualification/linux/f2b1e25a/README.md)
completed on `f2b1e25a`. Balanced passed. Concentrated missed the approved
11 s startup p95 gate by 47.36 ms. Every other budgeted series passed, and
all samples completed without errors or driver retries. Exact-candidate
native macOS qualification and final review remain open.

The reference driver and measured-capacity suite passed 38 deterministic
tests. The live component design preflight passed on the local checkpoint.
The 80-replicate live gate still needs the reviewed exact head.
