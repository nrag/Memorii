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
qualification label on 2026-11-27. Native Linux capacity takes an authorized
host at qualification time. No host was provisioned.
